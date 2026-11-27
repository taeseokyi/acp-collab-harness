"""VoxLog 음성인식 (백엔드 고르기 + 배경 작업자).

표준 라이브러리만 쓴다. 인터페이스는 docs/INTERFACE.md 의 'voxlog/stt.py' 절 참고.
"""

import base64
import json
import os
import pathlib
import queue
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

from . import stt_options


# "api" 백엔드: 화자 구분 받아쓰기 서버의 작업 API (맡기기 → 조회 → 결과).
#   POST VOXLOG_STT_URL (multipart `file`·`language`·`model`) → 202 {"id"}
#   GET  VOXLOG_STT_URL/<id> → {"status": queued|running|done|failed|cancelled, "result": {"text", "segments"}, "error"}
#   DELETE VOXLOG_STT_URL/<id> → 서버에 남은 결과를 지움
# 주소는 VOXLOG_STT_URL (예: https://<호스트>/v1/audio/diarize/jobs), 모델은 VOXLOG_STT_MODEL, 키는 VOXLOG_STT_API_KEY.
# 녹음은 받은 원본 그대로 통째로 보낸다 - 다시 압축하면 목소리 특징이 뭉개져 여러 사람이 한 화자로 나온다.
# 한 요청을 오래 붙들지 않으므로 긴 녹음도 중간 장비의 시간 제한에 끊기지 않는다.
DEFAULT_LANG = "ko"
SUBMIT_TIMEOUT = 600    # 맡기기 한 번(파일 올리기)의 시간 상한
POLL_TIMEOUT = 30       # 조회 한 번의 시간 상한
POLL_SECONDS = 10       # 조회 간격
POLL_MAX_ERRORS = 30    # 조회가 이만큼 잇달아 실패하면 그만둔다 (약 5분)
JOB_TIMEOUT = 6 * 3600  # 맡긴 뒤 결과까지 기다리는 상한 (서버 줄 서기 포함)

NO_BACKEND_MESSAGE = "음성인식 백엔드가 없습니다 - VOXLOG_STT_URL 또는 VOXLOG_STT_CMD"

# 서버가 주는 작업 id 는 URL 경로(GET VOXLOG_STT_URL/<id>)에 들어간다. UUID·job_1 같은 실제 꼴을 받되
# 경로를 벗어나는 글자(`/`, `..`)만 막는다. R41-N1.
_JOB_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def _job_id_ok(jid) -> bool:
    if not isinstance(jid, str) or not _JOB_ID_RE.fullmatch(jid):
        return False
    return jid not in (".", "..")


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


_UPLOAD_TYPES = {"webm": "audio/webm", "ogg": "audio/ogg", "m4a": "audio/mp4", "mp3": "audio/mpeg", "wav": "audio/wav"}

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


def _multipart(fields, filename, data, ctype="audio/mpeg"):
    boundary = "voxlog-" + base64.b16encode(os.urandom(12)).decode("ascii")
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode("utf-8"))
    out.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                "Content-Type: %s\r\n\r\n" % (boundary, filename, ctype)).encode("utf-8"))
    out.append(data)
    out.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(out), "multipart/form-data; boundary=" + boundary


def _speaker_lines(segments, names):
    """화자 구분 응답의 segments([{speaker, text}, …])를 '화자 N: 글' 줄들로. 같은 화자가 이어지면 한 줄로 잇는다.

    names 는 {서버가 준 화자 표시: 번호} - 번호는 처음 나온 차례. 서버가 화자를 정하지 못한 "?" 는 '화자 ?'.
    화자 구분이 없는 응답이면 None."""
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
        # "?" = 서버가 화자를 정하지 못한 짧은 소리 - 사람 수에 넣지 않는다
        n = "?" if label == "?" else names.setdefault(label, len(names) + 1)
        if n == last:
            lines[-1] += " " + text.strip()
        else:
            lines.append("화자 %s: %s" % (n, text.strip()))
            last = n
    return lines or None


def _call(opener, req, timeout):
    """한 번 부르고 JSON 을 돌려준다. (상태 코드, 객체) - 코드는 성공이면 200, HTTP 오류면 그 코드, 연결 실패면 0.

    HTTP 오류일 때도 본문을 읽어 JSON 객체면 함께 돌려준다. 코드는 그대로라 다른 호출의 판정은 바뀌지 않는다."""
    try:
        raw = opener(req, timeout)
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:  # noqa: BLE001 - 본문을 읽지 못하면 객체 없이 코드만 돌려준다
            raw = None
        try:
            obj = json.loads(_decode(raw))
        except ValueError:
            obj = None
        return exc.code, obj if isinstance(obj, dict) else None
    except (urllib.error.URLError, OSError):
        return 0, None
    try:
        obj = json.loads(_decode(raw))
    except ValueError:
        obj = None
    return 200, obj if isinstance(obj, dict) else None


def _http_reason(code):
    if code == 0:
        return "음성인식 서버에 연결하지 못했습니다"
    if code in (401, 403):
        return "음성인식 서버 %d - 키(VOXLOG_STT_API_KEY)를 확인하십시오" % code
    if code == 429:
        return "음성인식 서버가 붐빕니다(429) - 잠시 뒤 다시 받아쓰십시오"
    return "음성인식 서버 %d" % code


def _reject_message(obj):
    """400 본문 {"error":{"message": …}} 에서 사람이 읽을 message 를 꺼낸다. 없으면 None."""
    if not isinstance(obj, dict):
        return None
    err = obj.get("error")
    if not isinstance(err, dict):
        return None
    message = err.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    return " ".join(message.split())


def _transcribe_api(path, mime, env, opener, job=None, options=None, used=None) -> str:
    """작업으로 맡기고 끝날 때까지 조회한다. `job` 은 맡긴 작업 id 를 적어 두는 곳(get()·set(id)) -
    있으면 앱 서버가 다시 떠도 같은 작업을 이어서 기다린다."""
    url = (env.get("VOXLOG_STT_URL") or "").rstrip("/")
    if not url:
        raise SttUnavailable(NO_BACKEND_MESSAGE)
    if not url.startswith(("https://", "http://")):
        raise SttError("VOXLOG_STT_URL 이 http(s) 주소가 아닙니다")
    path = pathlib.Path(path)
    _input_format(path)                          # 모르는 확장자는 보내지 않는다
    headers = {}
    if env.get("VOXLOG_STT_API_KEY"):
        headers["Authorization"] = "Bearer " + env["VOXLOG_STT_API_KEY"]
    if opener is None:
        opener = _default_opener

    def submit():
        fields = {"language": env.get("VOXLOG_STT_LANG") or DEFAULT_LANG}
        if env.get("VOXLOG_STT_MODEL"):
            fields["model"] = env["VOXLOG_STT_MODEL"]
        fields.update(stt_options.form_fields(options or {}))
        ext = path.suffix.lower().lstrip(".")
        body, ctype = _multipart(fields, "audio." + ext, path.read_bytes(), _UPLOAD_TYPES[ext])
        req = urllib.request.Request(url, data=body, headers=dict(headers, **{"Content-Type": ctype}), method="POST")
        code, obj = _call(opener, req, SUBMIT_TIMEOUT)
        if code != 200:
            if code == 400:
                message = _reject_message(obj)
                if message is not None:
                    raise SttError("음성인식 서버가 요청을 거절했습니다 - " + message[:160])
            raise SttError(_http_reason(code))
        jid = obj.get("id") if obj else None
        if not _job_id_ok(jid):
            raise SttError("음성인식 서버 응답을 읽지 못했습니다")
        if job is not None:
            job.set(jid)
        return jid

    jid = job.get() if job is not None else None
    resumed = bool(jid)
    if not jid:
        jid = submit()
    deadline = time.monotonic() + JOB_TIMEOUT
    errors = 0
    while True:
        code, st = _call(opener, urllib.request.Request(url + "/" + jid, headers=headers, method="GET"), POLL_TIMEOUT)
        if code == 404 and resumed:              # 이어받으려던 작업이 서버에 없다(보관 기한·삭제) - 새로 맡긴다
            resumed = False
            jid = submit()
            continue
        if code != 200 or st is None:
            if code in (401, 403, 404):
                if job is not None:
                    job.set(None)
                raise SttError(_http_reason(code) if code != 404 else "음성인식 서버에 맡긴 작업이 없어졌습니다")
            errors += 1
            if errors >= POLL_MAX_ERRORS:
                raise SttError(_http_reason(code) if code != 200 else "음성인식 서버 응답을 읽지 못했습니다")
        else:
            errors = 0
            status = st.get("status")
            if status in ("done", "failed", "cancelled"):
                break
        if time.monotonic() > deadline:
            raise SttError("음성인식이 너무 오래 걸립니다")
        _sleep(POLL_SECONDS)
    if job is not None:
        job.set(None)
    # 서버에 남은 결과(24시간 보관)는 바로 지운다 - 실패해도 받아쓰기 결과에는 영향 없음
    _call(opener, urllib.request.Request(url + "/" + jid, headers=headers, method="DELETE"), POLL_TIMEOUT)
    if status != "done":
        reason = st.get("error")
        reason = (" - " + " ".join(str(reason).split())[:120]) if reason else ""
        raise SttError(("음성인식이 취소됐습니다" if status == "cancelled" else "음성인식 서버가 받아쓰지 못했습니다") + reason)
    result = st.get("result")
    if isinstance(used, dict):
        used.update(stt_options.used_from_result(result))
    if not isinstance(result, dict) or not isinstance(result.get("text"), str):
        raise SttError("음성인식 서버 응답을 읽지 못했습니다")
    lines = _speaker_lines(result.get("segments"), {})
    return "\n".join(lines) if lines else result["text"].strip()


def _sleep(seconds):
    time.sleep(seconds)


def _default_opener(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout).read()


def transcribe(path: pathlib.Path, mime: str, env=None, opener=None, job=None,
               options=None, used=None) -> str:
    """받아쓴다. options/used 는 api 백엔드만 쓴다(command 는 무시)."""
    if env is None:
        env = os.environ
    name = backend_name(env)
    if name == "command":
        return _transcribe_command(path, env)
    if name == "api":
        return _transcribe_api(path, mime, env, opener, job, options=options, used=used)
    raise SttUnavailable(NO_BACKEND_MESSAGE)


def _short(exc, n=200) -> str:
    text = str(exc).replace("\n", " ").strip()
    return text[:n] if text else type(exc).__name__


class _JobRef:
    """맡긴 작업 id 를 녹음 메타(stt_job)에 적어 둔다 - 앱 서버가 다시 떠도 같은 작업을 이어 기다리게."""

    def __init__(self, store, rid):
        self.store, self.rid = store, rid

    def get(self):
        meta = self.store.get(self.rid)
        jid = meta.get("stt_job") if isinstance(meta, dict) else None
        return jid if isinstance(jid, str) and jid else None

    def set(self, jid):
        try:
            self.store.set_job(self.rid, jid)
        except Exception:
            pass                                  # 녹음이 그새 지워졌다 - 받아쓰기 쪽에서 드러난다


class Transcriber:
    """데몬 스레드 하나로 큐를 차례로 처리한다."""

    def __init__(self, store, env=None, transcribe_fn=transcribe, on_done=None, options_fn=None):
        self.store = store
        self.env = env
        self.transcribe_fn = transcribe_fn
        self.on_done = on_done
        self.options_fn = options_fn
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
            opts = {}
            if self.options_fn is not None:
                try:
                    opts = self.options_fn(meta) or {}
                except Exception:  # noqa: BLE001 - 옵션을 읽지 못하면 옵션 없이 받아쓴다
                    opts = {}
            if self.transcribe_fn is transcribe:
                used = {}
                text = transcribe(path, mime, env, job=_JobRef(self.store, rid), options=opts, used=used)
            else:
                used = None
                text = self.transcribe_fn(path, mime, env)
        except SttUnavailable as exc:
            self.store.set_status(rid, "no-stt", _short(exc))
        except SttError as exc:
            self.store.set_status(rid, "failed", _short(exc))
        except Exception as exc:
            self.store.set_status(rid, "failed", _short(exc))
        else:
            self.store.set_transcript(rid, text, used=used)
            if (text or "").strip() and self.on_done is not None:
                try:
                    self.on_done(rid)
                except Exception:  # noqa: BLE001 - 받아쓰기 결과에는 영향이 없다
                    pass
