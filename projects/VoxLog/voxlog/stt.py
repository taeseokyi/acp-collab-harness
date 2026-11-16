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


# "api" 백엔드: OpenAI 꼴 받아쓰기 엔드포인트(POST multipart `file`·`model`·`language` → {"text": …}).
# 주소는 VOXLOG_STT_URL (예: https://<호스트>/v1/audio/transcriptions), 모델은 VOXLOG_STT_MODEL.
DEFAULT_LANG = "ko"
DIARIZE_TIMEOUT = 3600  # 화자 구분은 녹음 전체를 한 번에 보낸다 (서버가 전체에서 화자를 나눠야 끝까지 같은 번호) - 오래 기다린다
CHUNK_SECONDS = 600     # 긴 녹음은 이 길이로 잘라 차례로 보낸다 (받아쓰기 서버 권장: 한 요청 10분·25MB 이하. 32kbps mp3 10분 ≈ 2.4MB)

NO_BACKEND_MESSAGE = "음성인식 백엔드가 없습니다 - VOXLOG_STT_URL 또는 VOXLOG_STT_CMD"


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
    if env.get("VOXLOG_STT_URL"):
        return "api"
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


def split_audio(src: pathlib.Path, seconds=None):
    """ffmpeg 로 16kHz 모노 mp3 조각들을 임시 폴더에 만든다. (폴더, [조각 경로 - 시간 차례]).

    입력 형식·프로토콜 제한은 to_audio 와 같다. 폴더는 호출한 쪽이 지운다."""
    src = pathlib.Path(src)
    input_fmt = _input_format(src)
    if shutil.which("ffmpeg") is None:
        raise SttError("ffmpeg 가 없습니다")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="voxlog-stt-"))
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-protocol_whitelist", "file,pipe", "-f", input_fmt,
        "-i", str(src), "-ac", "1", "-ar", "16000", "-b:a", "32k",
        "-f", "segment", "-segment_time", str(int(seconds or CHUNK_SECONDS)), "-reset_timestamps", "1",
        str(tmp / "part-%04d.mp3"),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    parts = sorted(tmp.glob("part-*.mp3"))
    if proc.returncode != 0 or not parts:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SttError(_decode(proc.stderr)[-200:] or "ffmpeg 변환 실패")
    return tmp, parts


def _multipart(fields, filename, data):
    boundary = "voxlog-" + base64.b16encode(os.urandom(12)).decode("ascii")
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode("utf-8"))
    out.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                "Content-Type: audio/mpeg\r\n\r\n" % (boundary, filename)).encode("utf-8"))
    out.append(data)
    out.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(out), "multipart/form-data; boundary=" + boundary


def _speaker_lines(segments, names):
    """화자 구분 응답의 segments([{speaker, text}, …])를 '화자 N: 글' 줄들로. 같은 화자가 이어지면 한 줄로 잇는다.

    names 는 {서버가 준 화자 표시: 번호} - 번호는 처음 나온 차례. 화자 구분이 없는 응답이면 None."""
    if not isinstance(segments, list):
        return None
    lines = []
    last = None
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("speaker") is None:
            continue
        text = seg.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        label = str(seg["speaker"])[:40]
        n = names.setdefault(label, len(names) + 1)
        if n == last:
            lines[-1] += " " + text.strip()
        else:
            lines.append("화자 %d: %s" % (n, text.strip()))
            last = n
    return lines or None


def _transcribe_api(path, mime, env, opener) -> str:
    url = env.get("VOXLOG_STT_URL")
    if not url:
        raise SttUnavailable(NO_BACKEND_MESSAGE)
    if not url.startswith(("https://", "http://")):
        raise SttError("VOXLOG_STT_URL 이 http(s) 주소가 아닙니다")
    fields = {"language": env.get("VOXLOG_STT_LANG") or DEFAULT_LANG}
    if env.get("VOXLOG_STT_MODEL"):
        fields["model"] = env["VOXLOG_STT_MODEL"]
    diarize = (env.get("VOXLOG_STT_DIARIZE") or "").strip().lower() in ("1", "true", "yes", "on")
    if diarize:
        fields["response_format"] = "diarized_json"   # 응답에 segments([{speaker, start, end, text}, …])가 실린다
    headers = {}
    if env.get("VOXLOG_STT_API_KEY"):
        headers["Authorization"] = "Bearer " + env["VOXLOG_STT_API_KEY"]
    if opener is None:
        opener = _default_opener
    if diarize:
        whole = to_audio(path, "mp3")
        tmp, parts, timeout = whole.parent, [whole], DIARIZE_TIMEOUT
    else:
        (tmp, parts), timeout = split_audio(path), 180
    try:
        texts = []
        names = {}
        by_speaker = False
        for part in parts:
            body, ctype = _multipart(fields, part.name, part.read_bytes())
            req = urllib.request.Request(url, data=body, headers=dict(headers, **{"Content-Type": ctype}), method="POST")
            try:
                raw = opener(req, timeout)
            except urllib.error.HTTPError as exc:
                raise SttError("음성인식 서버 %d" % exc.code) from None
            except (urllib.error.URLError, OSError):
                raise SttError("음성인식 서버에 연결하지 못했습니다") from None
            try:
                obj = json.loads(_decode(raw))
                text = obj["text"]
            except (ValueError, KeyError, TypeError):
                raise SttError("음성인식 서버 응답을 읽지 못했습니다") from None
            lines = _speaker_lines(obj.get("segments"), names) if diarize else None
            if lines:
                by_speaker = True
                texts.extend(lines)
            elif isinstance(text, str) and text.strip():
                texts.append(text.strip())
        return ("\n" if by_speaker else " ").join(texts)
    finally:
        if diarize:
            parts[0].unlink(missing_ok=True)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def _default_opener(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout).read()


def transcribe(path: pathlib.Path, mime: str, env=None, opener=None) -> str:
    if env is None:
        env = os.environ
    name = backend_name(env)
    if name == "command":
        return _transcribe_command(path, env)
    if name == "api":
        return _transcribe_api(path, mime, env, opener)
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
