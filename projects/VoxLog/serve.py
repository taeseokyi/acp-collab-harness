#!/usr/bin/env python3
"""VoxLog HTTP 서버 (표준 라이브러리만): 정적 web/ + /api/*.

    python3 serve.py [--host 127.0.0.1] [--port 8790] [--data DIR] [--token T]
                     [--tls-cert C --tls-key K]

토큰은 --token 또는 환경 변수 VOXLOG_TOKEN. 루프백이 아닌 host 에 토큰이 없으면 시작을 거절합니다(코드 2).
API 표는 docs/INTERFACE.md 의 'serve.py' 절.
"""
import argparse
import datetime
import errno
import hmac
import ipaddress
import json
import math
import mimetypes
import os
import re
import shutil
import signal
import socket
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from voxlog import ask as ask_mod  # noqa: E402
from voxlog import stt as stt_mod  # noqa: E402
from voxlog.store import ALLOWED_MIME, MAX_AUDIO_BYTES, Store  # noqa: E402

WEB = HERE / "web"
VERSION = "0.1"
JSON_BODY_MAX = 1024 * 1024
DRAIN_MAX = 64 * 1024  # 413 뒤 연결을 깨끗이 닫으려고 버리는(저장 안 함) 작은 본문의 상한
BODY_GRACE_S = 30  # 본문(JSON) 마감 - 요청 시작부터 이만큼 안에 선언한 길이만큼 다 오지 않으면(느리게라도 계속 오는 경우 포함) 400 (R41-N5)
CHUNK = 64 * 1024  # 업로드를 디스크로 흘려 쓰는 단위
DISK_MARGIN = 100 * 1024 * 1024  # 업로드 크기에 더해 남겨야 하는 디스크 여유
UPLOAD_GRACE_S = 30  # 업로드 마감 = 이 여유 + 지금까지 받은 바이트 / UPLOAD_MIN_RATE(선언한 길이가 아님)
UPLOAD_MIN_RATE = 16 * 1024  # 바이트/초: 이보다 느린 업로드는 자리를 오래 잡지 못하게 408
EXTRA_MIME = {".webmanifest": "application/manifest+json", ".js": "text/javascript"}
TEXTUAL = ("text/", "application/json", "application/manifest+json")


def _is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _guess_mime(path):
    ext = path.suffix.lower()
    mime = EXTRA_MIME.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime.startswith(TEXTUAL) or mime == "text/javascript":
        mime += "; charset=utf-8"
    return mime


def _valid_recorded_at(raw):
    """클라이언트 X-Recorded-At -> 기록할 값 또는 None(서버 시각으로 대신).

    실제 ISO 날짜·시각으로 읽히고, 시간대가 붙어 있고, 서버 시계보다 하루 넘게
    미래가 아닐 때만 그 값을 쓴다. 못 쓰는 값이어도 업로드를 거절하지 않는다
    (대기열의 녹음이 영구 실패로 가면 안 됨) - None 을 주면 store 가 created 를 쓴다.
    """
    text = (raw or "").strip()
    if not text or len(text) > 64:
        return None
    probe = text[:-1] + "+00:00" if text[-1] in ("Z", "z") else text
    try:
        dt = datetime.datetime.fromisoformat(probe)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        # astimezone 은 날짜 범위 끝(0001-01-01 +14:00, 9999-12-31 -14:00)에서 OverflowError 를 낸다.
        # 못 쓰는 값이면 서버 시각을 쓰는 규칙 그대로 None 을 준다(업로드를 끊지 않는다).
        if dt.astimezone(datetime.timezone.utc) > now + datetime.timedelta(days=1):
            return None
    except (ValueError, OverflowError):
        return None
    return text


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(raw):
    """YYYY-MM-DD 이고 달력에 실제로 있는 날짜인지 (2026-13-40 은 거짓).

    fromisoformat 만 보면 3.11 은 `20261123`(기본형)·`2026-W48-1`(ISO 주)도 받는다. store 는 이 값을
    문자열로 비교하므로 정규식을 함께 통과해야 한다.
    """
    if not DATE_RE.match(raw or ""):
        return False
    try:
        datetime.date.fromisoformat(raw)
    except ValueError:
        return False
    return True


def _parse_location(raw):
    """'<lat>,<lon>,<accuracy>' -> {"lat","lon","accuracy"} 또는 None(틀린 형식·범위 밖)."""
    if not raw:
        return None
    parts = raw.strip().split(",")
    if len(parts) != 3:
        return None
    try:
        lat, lon, acc = (float(p) for p in parts)
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in (lat, lon, acc)):
        return None
    if abs(lat) > 90 or abs(lon) > 180 or acc < 0:
        return None
    return {"lat": lat, "lon": lon, "accuracy": acc}


class VoxServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self):
        for worker in (getattr(self, "transcriber", None), getattr(self, "asker", None)):
            if worker is not None:
                try:
                    worker.stop()
                except Exception:  # noqa: BLE001
                    pass
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = "VoxLog/" + VERSION
    protocol_version = "HTTP/1.1"
    timeout = 60

    # ---- 로그: 한 줄(메서드·경로·코드). 머리·쿼리는 찍지 않음 ----
    def log_request(self, code="-", size="-"):
        path = urlsplit(self.path).path
        sys.stderr.write("%s %s %s\n" % (self.command, path, getattr(code, "value", code)))

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args if args else fmt))

    # ---- 응답 도우미 ----
    def _send(self, status, body=b"", ctype=None, extra=None, close=False):
        self.send_response(status)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, obj, close=False, extra=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        hdr = {"Cache-Control": "no-store"}
        hdr.update(extra or {})
        self._send(status, body, "application/json; charset=utf-8", hdr, close)

    def _err(self, status, msg, close=False, extra=None):
        if self.command in ("POST", "PUT", "PATCH", "DELETE") and not self._body_read:
            # 본문을 안 읽은 채 답하면 keep-alive 연결에 본문이 남아 다음 요청으로 오해됨 -> 닫는다.
            # 작은 본문은 버려서(저장·해석 안 함) 응답이 RST 에 묻히지 않게 함
            close = True
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if 0 < length <= DRAIN_MAX:
                self.rfile.read(length)
            self._body_read = True
        self._json(status, {"error": msg}, close=close, extra=extra)

    # ---- 진입 ----
    _body_read = False

    def _dispatch(self):
        self._body_read = False
        u = urlsplit(self.path)
        if not self.server.token and not self._local_host():
            # DNS 리바인딩 막기: 토큰이 없으면 루프백 이름으로 온 요청만 받는다
            return self._err(403, "이 주소로는 열 수 없습니다")
        if u.path == "/api" or u.path.startswith("/api/"):
            return self._api(u)
        if self.command not in ("GET", "HEAD"):
            return self._err(405, "허용되지 않는 메서드입니다", extra={"Allow": "GET, HEAD"})
        return self._static(u.path)

    do_GET = do_HEAD = do_POST = do_DELETE = do_PUT = do_PATCH = _dispatch

    def do_OPTIONS(self):
        # 같은 출처만 쓰므로 CORS 머리는 붙이지 않는다
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- 정적 ----
    def _static(self, raw_path):
        try:
            rel = unquote(raw_path, errors="strict")
            if "\x00" in rel:
                raise ValueError
            rel = rel.lstrip("/") or "index.html"
            web = WEB.resolve()
            target = (web / rel).resolve()
            target.relative_to(web)
            if not target.is_file():
                raise ValueError
            fh = open(target, "rb")
        except (ValueError, OSError, UnicodeDecodeError):
            return self._err(404, "없는 파일입니다")
        with fh:
            data = fh.read()
        extra = {}
        if target.name == "sw.js":
            extra["Cache-Control"] = "no-cache"
        self._send(200, data, _guess_mime(target), extra)

    # ---- 인증·출처 ----
    def _authorized(self):
        token = self.server.token
        if not token:
            return True
        auth = self.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return False
        given = auth[7:].strip().encode("utf-8")
        return hmac.compare_digest(given, token.encode("utf-8"))

    def _local_host(self):
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            name = host[1:].split("]", 1)[0]
        else:
            name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        return name in ("127.0.0.1", "localhost", "::1")

    def _foreign_origin(self):
        origin = self.headers.get("Origin")
        if origin is None:
            return False
        if origin.strip().lower() == "null":
            return True  # 샌드박스 iframe 등 - 토큰이 없을 때는 거절
        host = (self.headers.get("Host") or "").strip().lower()
        return urlsplit(origin).netloc.lower() != host

    # ---- API ----
    def _api(self, u):
        path = u.path
        # HEAD 는 처리 함수를 고르기 *전에* GET 으로 바꾼다. 그러면 HEAD 는 GET 과 같은 경로·같은
        # 처리 함수·같은 상태 코드를 타고, 본문만 _send 가 빼므로, HEAD 가 지우거나 만드는 경로가 없다.
        method = "GET" if self.command == "HEAD" else self.command
        if path != "/api/health":
            if not self._authorized():
                return self._err(401, "인증이 필요합니다", extra={"WWW-Authenticate": "Bearer"})
            # 바꾸지 않는 메서드(GET·HEAD·OPTIONS)만 출처 검사에서 뺀다. 나머지는 모두 검사한다.
            if (not self.server.token and self.command not in ("GET", "HEAD", "OPTIONS")
                    and self._foreign_origin()):
                return self._err(403, "허용되지 않은 출처입니다")

        parts = [p for p in path.split("/") if p]  # ["api", ...]
        route = None  # (허용 메서드 목록, 처리 함수, 인자)
        n = len(parts)
        if parts == ["api", "health"]:
            route = (("GET",), self._health, ())
        elif parts == ["api", "recordings"]:
            route = (("GET", "POST"), self._rec_list if method == "GET" else self._rec_upload, (u,))
        elif n == 3 and parts[1] == "recordings":
            route = (("GET", "DELETE"), self._rec_get if method == "GET" else self._rec_delete, (parts[2],))
        elif n == 4 and parts[1] == "recordings" and parts[3] == "audio":
            route = (("GET",), self._rec_audio, (parts[2],))
        elif n == 4 and parts[1] == "recordings" and parts[3] == "retry":
            route = (("POST",), self._rec_retry, (parts[2],))
        elif parts == ["api", "ask"]:
            route = (("POST",), self._ask, ())
        elif parts == ["api", "answers"]:
            route = (("GET",), self._answers, ())
        elif n == 3 and parts[1] == "answers":
            route = (("GET", "DELETE"), self._answer_one if method != "DELETE" else self._answer_delete, (parts[2],))
        if route is None:
            return self._err(404, "없는 API 경로입니다")
        allowed, fn, args = route
        if method not in allowed:
            return self._err(405, "허용되지 않는 메서드입니다", extra={"Allow": ", ".join(allowed)})
        return fn(*args)

    def _health(self):
        env = self.server.env
        # 설정이 틀려도(llm_command 가 ValueError·빈 목록) health 는 200 으로 답하고 llm 칸만 false + 까닭을 준다
        llm = False
        llm_error = None
        try:
            cmd = ask_mod.llm_command(env)
        except ValueError as exc:
            llm_error = "LLM 명령 설정 오류: %s" % exc
        else:
            if not cmd:
                llm_error = "LLM 명령 설정 오류: VOXLOG_LLM_CMD 가 비어 있습니다"
            else:
                llm = shutil.which(cmd[0]) is not None
        body = {"ok": True, "auth": bool(self.server.token),
                "stt": stt_mod.backend_name(env), "llm": llm, "version": VERSION}
        if llm_error:
            body["llm_error"] = llm_error
        self._json(200, body)

    def _content_length(self, limit):
        """Content-Length 검사. 정수 길이, 아니면 이미 오류 응답을 보낸 뒤 None."""
        raw = self.headers.get("Content-Length")
        try:
            length = int(raw) if raw is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            self._err(400, "Content-Length 머리가 필요합니다", close=True)
            return None
        if length > limit:
            self._err(413, "본문이 너무 큽니다 (최대 {} 바이트)".format(limit), close=True)
            return None
        return length

    def _read_body(self, limit):
        """Content-Length 필수. 돌려주는 값은 bytes, 아니면 이미 오류 응답을 보낸 뒤 None.

        요청을 받기 시작한 때부터 body_grace 안에 선언한 길이만큼 다 오지 않으면(느리게라도 계속
        오는 경우 포함) 400 으로 답하고 연결을 닫는다. 업로드 마감은 받은 바이트/속도로 잼하는
        진행 기반이라 다르다. 마감은 server.body_grace 로 바꿔 끼울 수 있다 (R41-N5)."""
        length = self._content_length(limit)
        if length is None:
            return None
        self._body_read = True
        if not length:
            return b""
        grace = getattr(self.server, "body_grace", BODY_GRACE_S)
        deadline = time.monotonic() + grace
        chunks = []
        got = 0
        try:
            while got < length:
                left = deadline - time.monotonic()
                if left <= 0:
                    self._err(400, "본문이 중간에 끊겼습니다", close=True)
                    return None
                self.connection.settimeout(min(self.timeout, left))
                try:
                    chunk = self.rfile.read1(min(CHUNK, length - got))
                except socket.timeout:
                    self._err(400, "본문이 중간에 끊겼습니다", close=True)
                    return None
                except ConnectionError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
                got += len(chunk)
        finally:
            try:
                self.connection.settimeout(self.timeout)
            except OSError:
                pass
        if got != length:
            self._err(400, "본문이 중간에 끊겼습니다", close=True)
            return None
        return b"".join(chunks)

    def _rec_upload(self, _u):
        length = self._content_length(MAX_AUDIO_BYTES)
        if length is None:
            return
        slots = self.server.upload_slots
        if not slots.acquire(blocking=False):
            return self._err(503, "업로드가 몰렸습니다. 잠시 뒤 다시 보내 주세요", close=True,
                             extra={"Retry-After": "5"})
        try:
            self._upload_locked(length)
        finally:
            slots.release()

    @staticmethod
    def _unlink(path):
        if path is None:
            return
        try:
            os.unlink(path)
        except OSError:
            pass

    def _upload_err(self, status, msg, close=True):
        """업로드 경로의 오류 응답. 끊긴 쪽에 쓰다 난 오류는 삼키고 연결을 닫는다."""
        try:
            self._err(status, msg, close=close)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _upload_locked(self, length):
        store = self.server.store
        try:
            free = self.server.disk_free()
        except OSError:
            free = None
        if free is not None and free < length + DISK_MARGIN:
            return self._upload_err(507, "서버 디스크 여유가 부족합니다")
        mime = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        recorded_at = _valid_recorded_at(self.headers.get("X-Recorded-At"))
        try:
            duration = int(self.headers.get("X-Duration-Ms", "").strip())
            if duration < 0:
                duration = None
        except ValueError:
            duration = None
        client_id = (self.headers.get("X-Client-Id") or "").strip()[:128] or None
        location = _parse_location(self.headers.get("X-Location"))
        self._body_read = True
        path = None  # incoming_path() 가 mkdir 로 실패하면 None 인 채 OSError 처리로 간다
        got = 0
        reason = None  # 'slow'(마감 넘김) | 'cut'(연결 끊김)
        start = time.monotonic()
        try:
            try:
                path = store.incoming_path()
                with open(path, "wb") as f:
                    while got < length:
                        # 마감은 선언된 길이가 아니라 실제로 받은 바이트로 매번 다시 셈한다
                        deadline = start + self.server.upload_grace + got / self.server.upload_min_rate
                        left = deadline - time.monotonic()
                        if left <= 0:
                            reason = "slow"
                            break
                        self.connection.settimeout(min(self.timeout, left))
                        try:
                            chunk = self.rfile.read1(min(CHUNK, length - got))
                        except socket.timeout:
                            # 연결은 살아 있고 조용했을 뿐이다 - 영구 실패(400)가 아니라 다시 올릴 수 있는 408
                            reason = "slow"
                            break
                        except ConnectionError:
                            reason = "cut"
                            break
                        if not chunk:
                            reason = "cut"
                            break
                        f.write(chunk)
                        got += len(chunk)
                    if reason is None:
                        f.flush()
                        os.fsync(f.fileno())
                if reason is None:
                    meta = store.add_recording_file(
                        path, mime, recorded_at=recorded_at, duration_ms=duration,
                        client_id=client_id, location=location)
            except ValueError as exc:
                self._unlink(path)
                return self._upload_err(400, str(exc), close=False)
            except OSError as exc:
                self._unlink(path)
                if exc.errno in (errno.ENOSPC, errno.EDQUOT):
                    return self._upload_err(507, "서버 디스크 여유가 부족합니다")
                return self._upload_err(500, "서버가 녹음을 저장하지 못했습니다")
            if reason == "slow":
                self._unlink(path)
                return self._upload_err(408, "업로드가 너무 느립니다")
            if reason == "cut":
                self._unlink(path)  # 응답 전에 지운다(응답을 받은 쪽이 바로 폴더를 볼 수 있음)
                return self._upload_err(400, "본문이 중간에 끊겼습니다")
            try:
                self.connection.settimeout(self.timeout)
            except OSError:
                pass
        finally:
            self._unlink(path)  # 저장소가 옮겼거나 지웠으면 이미 없음
        if meta.get("duplicate"):
            return self._json(200, meta)
        self.server.transcriber.submit(meta["id"])
        self._json(201, meta)

    def _rec_list(self, u):
        q = parse_qs(u.query)

        def one(name):
            v = (q.get(name) or [""])[0].strip()
            return v or None

        date_from, date_to = one("from"), one("to")
        for d in (date_from, date_to):
            if d is not None and not _valid_date(d):
                return self._err(400, "날짜는 실제 날짜(YYYY-MM-DD)여야 합니다")
        limit = 200
        if one("limit") is not None:
            try:
                limit = int(one("limit"))
            except ValueError:
                return self._err(400, "limit 는 정수여야 합니다")
            limit = max(1, min(limit, 1000))
        store = self.server.store
        items = store.list(q=one("q"), date_from=date_from, date_to=date_to,
                           status=one("status"), limit=limit)
        self._json(200, {"items": items, "stats": store.stats()})

    def _rec_get(self, rid):
        meta = self.server.store.get(rid)
        if meta is None:
            return self._err(404, "없는 녹음입니다")
        self._json(200, meta)

    def _rec_audio(self, rid):
        store = self.server.store
        meta = store.get(rid)
        path = store.audio_path(rid) if meta else None
        if path is None:
            return self._err(404, "없는 녹음입니다")
        try:
            fh = open(path, "rb")
        except OSError:
            return self._err(404, "오디오 파일이 없습니다")
        with fh:
            size = os.fstat(fh.fileno()).st_size
            self.send_response(200)
            self.send_header("Content-Type", meta.get("mime") or "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                shutil.copyfileobj(fh, self.wfile)

    def _rec_retry(self, rid):
        store = self.server.store
        if store.get(rid) is None:
            return self._err(404, "없는 녹음입니다")
        tr = self.server.transcriber
        try:
            ok = tr.resubmit(rid)
        except ValueError:  # 위 get 과 resubmit 사이에 녹음이 지워짐
            return self._err(404, "없는 녹음입니다")
        if not ok:
            return self._err(409, "받아쓰는 중입니다")
        self._json(200, store.get(rid))

    def _ask(self):
        data = self._read_body(JSON_BODY_MAX)
        if data is None:
            return
        try:
            body = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = None
        if not isinstance(body, dict):
            return self._err(400, "본문은 JSON 객체여야 합니다")
        prompt = body.get("prompt", "")
        if prompt is None:
            prompt = ""
        if not isinstance(prompt, str):
            return self._err(400, "prompt 는 문자열이어야 합니다")
        kind = body.get("kind")
        if not isinstance(kind, str):
            # ask.py 가 `kind not in KINDS` 로 TypeError 를 내 연결이 끊기기 전에 여기서 거른다
            return self._err(400, "kind 는 문자열이어야 합니다")
        try:
            meta = self.server.asker.submit(kind, prompt, body.get("ids"))
        except ValueError as exc:
            return self._err(400, str(exc))
        self._json(202, meta)

    def _answers(self):
        self._json(200, {"items": self.server.store.list_answers()})

    def _answer_one(self, aid):
        ans = self.server.store.get_answer(aid)
        if ans is None:
            return self._err(404, "없는 답입니다")
        self._json(200, ans)

    def _answer_delete(self, aid):
        removed = self.server.store.delete_answer(aid)
        if removed == "running":
            return self._err(409, "아직 묻는 중인 답은 지울 수 없습니다")
        if not removed:
            return self._err(404, "없는 답입니다")
        self._json(200, {"ok": True})

    def _rec_delete(self, rid):
        try:
            removed = self.server.store.delete(rid)
        except ValueError:
            removed = False
        if not removed:
            return self._err(404, "없는 녹음입니다")
        self._json(200, {"ok": True})


def make_server(host, port, data_dir, token=None, env=None, stt_fn=None, llm_run=None,
                max_uploads=2, upload_grace=UPLOAD_GRACE_S, upload_min_rate=UPLOAD_MIN_RATE,
                body_grace=BODY_GRACE_S):
    """검사가 임시 포트(0)·임시 폴더·가짜 함수로 띄울 수 있는 서버. 일꾼은 start() 해 둔다.

    max_uploads: 동시에 받는 업로드 수(넘으면 503). server.disk_free 는 저장소 디스크 여유
    바이트를 돌려주는 함수라 검사에서 바꿔 끼울 수 있다. upload_grace·upload_min_rate: 업로드
    마감(초) = grace + 지금까지 받은 바이트 / min_rate(매 바퀴 다시 셈, 넘기면 408), server.upload_grace·upload_min_rate 로 둔다.
    body_grace: JSON 본문 마감(초). 요청 시작부터 이만큼 안에 Content-Length 만큼 다 오지 않으면
    (느리게라도 계속 오는 경우 포함) 400 (server.body_grace)."""

    class _Server(VoxServer):
        address_family = socket.AF_INET6 if ":" in host else socket.AF_INET

    server = _Server((host, port), Handler)
    try:
        server.token = token or None
        server.env = env
        server.store = Store(Path(data_dir))
        server.upload_slots = threading.BoundedSemaphore(max_uploads)
        server.upload_grace = upload_grace
        server.upload_min_rate = upload_min_rate
        server.body_grace = body_grace
        server.disk_free = lambda: shutil.disk_usage(server.store.root).free
        server.transcriber = stt_mod.Transcriber(
            server.store, env, transcribe_fn=stt_fn or stt_mod.transcribe)
        server.asker = ask_mod.Asker(server.store, env, run=llm_run or ask_mod.run_llm)
        server.transcriber.start()
        server.asker.start()
    except BaseException:
        server.server_close()
        raise
    return server


SETTINGS_FILE = HERE / "settings.json"


def load_settings(path=SETTINGS_FILE, environ=None):
    """서버 설정 = settings.json 의 `VOXLOG_*` 글 값 위에 환경 변수를 덮은 것 (환경 변수가 이긴다).

    모니터의 '앱 열기'·배포는 환경을 좁혀 띄우므로 음성인식 주소·키(`VOXLOG_STT_API_KEY`) 같은 설정은 이 파일에 둔다.
    키가 들어가므로 git 에 올리지 않고 권한은 600 으로 둔다."""
    env = {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict):
        env.update({k: v for k, v in data.items()
                    if isinstance(k, str) and k.startswith("VOXLOG_") and isinstance(v, str) and v})
    env.update(os.environ if environ is None else environ)
    return env


def main(argv=None):
    ap = argparse.ArgumentParser(description="VoxLog 서버")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--data", default=os.environ.get("VOXLOG_DATA") or str(HERE / "data"))
    ap.add_argument("--token", default=os.environ.get("VOXLOG_TOKEN") or None)
    ap.add_argument("--tls-cert")
    ap.add_argument("--tls-key")
    args = ap.parse_args(argv)

    if not _is_loopback(args.host) and not args.token:
        print("루프백이 아닌 host(%s)에는 토큰이 필요합니다: --token 또는 VOXLOG_TOKEN" % args.host,
              file=sys.stderr)
        return 2
    if bool(args.tls_cert) != bool(args.tls_key):
        print("--tls-cert 와 --tls-key 는 함께 줘야 합니다", file=sys.stderr)
        return 2

    ctx = None
    if args.tls_cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ctx.load_cert_chain(args.tls_cert, args.tls_key)
        except (OSError, ssl.SSLError) as exc:
            print("TLS 인증서를 읽을 수 없습니다: %s" % exc, file=sys.stderr)
            return 2

    server = make_server(args.host, args.port, args.data, token=args.token, env=load_settings())
    if ctx is not None:
        server.socket = ctx.wrap_socket(server.socket, server_side=True)

    def _term(_sig, _frm):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _term)
    scheme = "https" if ctx else "http"
    print("VoxLog %s://%s:%d  (인증 %s, 데이터 %s)" % (
        scheme, args.host, server.server_address[1], "켜짐" if args.token else "꺼짐", args.data),
        flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
