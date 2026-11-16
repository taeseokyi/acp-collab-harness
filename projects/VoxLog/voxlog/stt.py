"""VoxLog 음성인식 (백엔드 고르기 + 배경 작업자).

표준 라이브러리만 쓴다. 인터페이스는 docs/INTERFACE.md 의 'voxlog/stt.py' 절 참고.
"""

import base64
import json
import os
import pathlib
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request


STT_INSTRUCTION = (
    "다음 음성을 들리는 그대로 한국어로 받아 적어라. "
    "받아 적은 글만 출력하고 설명·따옴표를 붙이지 마라. 말이 없으면 빈 줄."
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"

NO_BACKEND_MESSAGE = "음성인식 백엔드가 없습니다 - VOXLOG_STT_CMD 또는 OPENROUTER_API_KEY"


class SttUnavailable(Exception):
    """백엔드가 없음 -> 메타 status "no-stt"."""


class SttError(Exception):
    """실패 -> status "failed", error 에 짧은 까닭(키·주소 없이)."""


def backend_name(env=None) -> str:
    if env is None:
        env = os.environ
    if env.get("VOXLOG_STT"):
        return env["VOXLOG_STT"]
    if env.get("VOXLOG_STT_CMD"):
        return "command"
    if env.get("OPENROUTER_API_KEY"):
        return "openrouter"
    return "none"


def _decode(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


_INPUT_FORMATS = {
    "webm": "matroska",
    "ogg": "ogg",
    "m4a": "mov",
    "mp3": "mp3",
    "wav": "wav",
}


def _input_format(src: pathlib.Path) -> str:
    ext = pathlib.Path(src).suffix.lower().lstrip(".")
    fmt = _INPUT_FORMATS.get(ext)
    if fmt is None:
        raise SttError("알 수 없는 오디오 형식입니다")
    return fmt


def to_audio(src: pathlib.Path, fmt: str) -> pathlib.Path:
    """ffmpeg 로 16kHz 모노 임시 파일을 만든다. ffmpeg 가 없으면 SttError.

    입력 형식은 확장자로 강제하고(내용으로 판별하지 않음) 프로토콜을 제한한다.
    모르는 확장자면 ffmpeg 를 부르지 않고 SttError.
    돌려준 임시 파일은 호출한 쪽이 지운다.
    """
    src = pathlib.Path(src)
    input_fmt = _input_format(src)
    if shutil.which("ffmpeg") is None:
        raise SttError("ffmpeg 가 없습니다")
    fd, name = tempfile.mkstemp(suffix="." + fmt)
    os.close(fd)
    out = pathlib.Path(name)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-protocol_whitelist", "file,pipe", "-f", input_fmt,
        "-i", str(src), "-ac", "1", "-ar", "16000", str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    if proc.returncode != 0:
        reason = _decode(proc.stderr)[-200:]
        out.unlink(missing_ok=True)
        raise SttError(reason or "ffmpeg 변환 실패")
    return out


def _transcribe_command(path, env) -> str:
    cmd_str = env.get("VOXLOG_STT_CMD")
    if not cmd_str:
        raise SttUnavailable(NO_BACKEND_MESSAGE)
    wav = to_audio(path, "wav")
    try:
        cmd = [arg.replace("{wav}", str(wav)) for arg in shlex.split(cmd_str)]
        run_env = dict(os.environ)
        run_env.update({k: v for k, v in env.items() if isinstance(v, str)})
        try:
            proc = subprocess.run(
                cmd, shell=False, timeout=600, capture_output=True, env=run_env
            )
        except FileNotFoundError:
            raise SttUnavailable("음성인식 명령을 찾을 수 없습니다") from None
        if proc.returncode != 0:
            raise SttError(_decode(proc.stderr)[-200:] or "음성인식 명령이 실패했습니다")
        text = _decode(proc.stdout).strip()
        if not text:
            raise SttError("받아 적은 글이 비었습니다")
        return text
    finally:
        wav.unlink(missing_ok=True)


def _transcribe_openrouter(path, mime, env, opener) -> str:
    key = env.get("OPENROUTER_API_KEY")
    if not key:
        raise SttUnavailable(NO_BACKEND_MESSAGE)
    mp3 = to_audio(path, "mp3")
    try:
        data = base64.b64encode(mp3.read_bytes()).decode("ascii")
        model = env.get("VOXLOG_STT_MODEL") or DEFAULT_MODEL
        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": STT_INSTRUCTION},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": data, "format": "mp3"},
                        },
                    ],
                }
            ],
        }
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
            },
            method="POST",
        )
        if opener is None:
            opener = _default_opener
        try:
            raw = opener(req, 180)
        except urllib.error.HTTPError as exc:
            raise SttError("OpenRouter %d" % exc.code) from None
        obj = json.loads(_decode(raw))
        return (obj["choices"][0]["message"]["content"] or "").strip()
    finally:
        mp3.unlink(missing_ok=True)


def _default_opener(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout).read()


def transcribe(path: pathlib.Path, mime: str, env=None, opener=None) -> str:
    if env is None:
        env = os.environ
    name = backend_name(env)
    if name == "command":
        return _transcribe_command(path, env)
    if name == "openrouter":
        return _transcribe_openrouter(path, mime, env, opener)
    raise SttUnavailable(NO_BACKEND_MESSAGE)


def _short(exc, n=200) -> str:
    text = str(exc).replace("\n", " ").strip()
    return text[:n] if text else type(exc).__name__


class Transcriber:
    """데몬 스레드 하나로 큐를 차례로 처리한다."""

    def __init__(self, store, env=None, transcribe_fn=transcribe):
        self.store = store
        self.env = env
        self.transcribe_fn = transcribe_fn
        self._queue = queue.Queue()
        self._seen = set()
        self._active = set()
        self._lock = threading.Lock()
        self._pending = 0
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        for rid in self.store.pending_ids():
            self.submit(rid)

    def submit(self, rid):
        """같은 id 는 한 번만 큐에 넣는다(시작 때 pending_ids 를 넣는 데 씀)."""
        with self._lock:
            if rid in self._seen:
                return
            self._seen.add(rid)
            self._active.add(rid)
            self._pending += 1
            self._queue.put(rid)

    def busy(self, rid) -> bool:
        """그 id 가 큐에 있거나 지금 받아쓰는 중이면 True."""
        with self._lock:
            return rid in self._active

    def resubmit(self, rid) -> bool:
        """busy 면 False. 아니면 잠금 안에서 pending 으로 바꾸고 큐에 넣고 True."""
        with self._lock:
            if rid in self._active:
                return False
            self.store.set_status(rid, "pending")
            self._seen.add(rid)
            self._active.add(rid)
            self._pending += 1
            self._queue.put(rid)
            return True

    def stop(self, timeout=5):
        self._stop.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout)

    def idle(self) -> bool:
        with self._lock:
            return self._pending == 0

    def _run(self):
        while True:
            rid = self._queue.get()
            if rid is None:
                break
            try:
                self._process(rid)
            except Exception as exc:
                try:
                    self.store.set_status(rid, "failed", _short(exc))
                except Exception:
                    pass
            finally:
                with self._lock:
                    self._active.discard(rid)
                    self._pending -= 1

    def _process(self, rid):
        meta = self.store.get(rid)
        if meta is None:
            return
        self.store.set_status(rid, "transcribing")
        path = self.store.audio_path(rid)
        if path is None:
            self.store.set_status(rid, "failed", "오디오가 없습니다")
            return
        env = self.env if self.env is not None else os.environ
        mime = meta.get("mime", "")
        try:
            text = self.transcribe_fn(path, mime, env)
        except SttUnavailable as exc:
            self.store.set_status(rid, "no-stt", _short(exc))
        except SttError as exc:
            self.store.set_status(rid, "failed", _short(exc))
        except Exception as exc:
            self.store.set_status(rid, "failed", _short(exc))
        else:
            self.store.set_transcript(rid, text)
