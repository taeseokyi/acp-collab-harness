#!/usr/bin/env python3
"""배포 문지기 (2026-11-19, 태석님 지시) - 배포한 앱 앞에 서서 인증서·토큰·공개 여부를 맡는다.

프로젝트는 `app.json` 한 장만 있으면 배포된다. 앱 서버가 토큰이나 인증서를 다룰 필요가 없다 - 여기서 한다:

    폰 → 윈도우 프록시 → **문지기**(127.0.0.1:<안쪽 포트>, TLS) ─┬─ `/api/*`  → 앱 서버(app.json `server`, 있을 때만)
                                                                └─ 그 밖     → 앱 폴더(app.json `root`)의 정적 파일

- **토큰으로 막기 / 누구나** 는 배포를 켤 때 사람이 고른다. 토큰은 환경 변수 `AIMEM_DEPLOY_TOKEN` 으로 받는다(없으면 누구나).
  막을 때는 모든 경로가 막힌다. 통과하는 길은 둘: `Authorization: Bearer <토큰>` 머리(앱이 직접 붙일 때),
  또는 토큰 넣는 화면(`/~deploy/login`)이 심어 주는 쿠키(브라우저로 그냥 열 때).
- 앱 서버는 '앱 열기' 와 같은 약속으로 띄운다: `python3 <server> --host 127.0.0.1 --port <빈 포트>`. 문지기의 자식이라
  문지기가 내려가면 같이 내려간다. 죽어 있으면 다음 요청 때 다시 띄운다.
- 앱 서버로 넘길 때 `Host` 는 `127.0.0.1:<포트>`, 같은 출처의 `Origin` 은 `http://127.0.0.1:<포트>` 로 바꾼다 -
  혼자 띄울 때를 위한 앱 서버의 루프백 검사가 배포에서 걸리지 않게. 다른 출처에서 온 `/api/*` 요청은 여기서 403.
  배포 토큰(머리·쿠키)은 앱 서버로 넘기지 않는다.
- `/api/*` 는 요청 하나에 연결 하나로 그대로 흘려 보낸다(본문을 모으지 않는다 - 큰 올리기도 된다).

표준 라이브러리만. 실행은 `deploy.py` 가 한다:
    python3 deploy_gate.py --port P --root <앱 폴더> [--entry index.html] [--server <서버 파일> --cwd <프로젝트 폴더>]
                           [--tls-cert C --tls-key K]
"""
import argparse
import asyncio
import hashlib
import hmac
import html
import json
import mimetypes
import os
import re
import signal
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote

TOKEN_ENV = "AIMEM_DEPLOY_TOKEN"
LOGIN_PATH = "/~deploy/login"
HEAD_MAX = 64 * 1024
HEAD_TIMEOUT = 30            # 요청 머리를 기다리는 시간 = 쉬는 연결을 붙들어 두는 시간
IDLE_TIMEOUT = 600           # 앱 서버가 아무것도 보내지 않을 때 기다리는 시간
LOGIN_BODY_MAX = 4096
CHUNK = 64 * 1024
WRITE_TIMEOUT = 60           # 받는 쪽이 읽지 않을 때 기다리는 시간 - 넘으면 연결을 끊는다
MAX_CONNS = 256              # 한꺼번에 붙들어 두는 연결 수 - 넘으면 새 연결은 바로 닫는다
MAX_REQUESTS = 200           # 연결 하나가 보낼 수 있는 요청 수
OWN_COOKIE_PREFIX = "aimem_"  # 모니터 세션·다른 배포의 쿠키(포트를 가리지 않고 같이 온다) - 앱 서버로 넘기지 않는다
EXTRA_MIME = {".webmanifest": "application/manifest+json", ".js": "text/javascript", ".mjs": "text/javascript",
              ".wasm": "application/wasm"}
TEXTUAL = ("text/", "application/json", "application/manifest+json")
_BAD_PART = re.compile(r"[\x00-\x1f\x7f\\]")
_HOP = {"host", "connection", "keep-alive", "proxy-connection", "expect", "upgrade", "te", "trailer"}
_STATUS = {200: "OK", 303: "See Other", 304: "Not Modified", 400: "Bad Request", 401: "Unauthorized",
           403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 502: "Bad Gateway", 504: "Gateway Timeout"}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port, timeout=0.3):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def guess_mime(path):
    ext = path.suffix.lower()
    mime = EXTRA_MIME.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime.startswith(TEXTUAL) or mime == "text/javascript":
        mime += "; charset=utf-8"
    return mime


def safe_file(root, entry, raw_path):
    """요청 경로 → 앱 폴더 안의 실제 파일 또는 None. `..`·점으로 시작하는 이름·심볼릭 링크·제어 문자는 받지 않는다."""
    try:
        rel = unquote(raw_path, errors="strict")
    except UnicodeDecodeError:
        return None
    if not rel.startswith("/"):
        return None
    rel = rel[1:]
    if rel == "":
        rel = entry
    elif rel.endswith("/"):
        rel += "index.html"
    cur = root
    for part in rel.split("/"):
        if not part or part.startswith(".") or _BAD_PART.search(part):
            return None
        cur = cur / part
        try:
            if cur.is_symlink():
                return None
        except OSError:
            return None
    try:
        return cur if cur.is_file() else None
    except OSError:
        return None


class Request:
    def __init__(self, method, target, version, headers):
        self.method, self.target, self.version, self.headers = method, target, version, headers
        self.path = target.split("?", 1)[0]

    def get(self, name):
        for k, v in self.headers:
            if k.lower() == name:
                return v
        return None

    @property
    def has_body(self):
        return self.get("transfer-encoding") is not None or (self.get("content-length") or "0").strip() not in ("", "0")


def parse_head(raw):
    """요청 머리 바이트 → Request 또는 None(받지 않는 꼴)."""
    if re.search(rb"[\r\n\x00]", raw.replace(b"\r\n", b"")):
        return None                         # 홑 LF·홑 CR·NUL - 앱 서버가 줄을 다르게 끊어 읽지 않게
    try:
        lines = raw[:-4].decode("latin-1").split("\r\n")
        method, target, version = lines[0].split(" ")
    except ValueError:
        return None
    if (version not in ("HTTP/1.0", "HTTP/1.1") or not target.startswith("/") or not re.fullmatch(r"[A-Za-z]+", method)
            or not re.fullmatch(r"[\x21-\x7e]+", target)):
        return None
    headers = []
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if not sep or not name or name != name.strip() or re.search(r"[\s\x00-\x1f]", name):
            return None                     # 이어 쓴 줄(obs-fold)·이름에 빈칸이 낀 머리는 받지 않는다
        headers.append((name, value.strip()))
    req = Request(method.upper(), target, version, headers)
    names = [k.lower() for k, _ in headers]
    if names.count("content-length") > 1 or names.count("host") != 1 or names.count("origin") > 1:
        return None
    if "transfer-encoding" in names and "content-length" in names:
        return None
    return req


LOGIN_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>토큰 넣기</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0; min-height: 100vh; display: grid; place-items: center; }}
form {{ width: min(22rem, calc(100vw - 2rem)); display: grid; gap: .75rem; }}
h1 {{ font-size: 1.15rem; margin: 0; }}
p {{ margin: 0; opacity: .75; font-size: .9rem; }}
input, button {{ font: inherit; padding: .65rem .75rem; border-radius: .5rem; border: 1px solid #8888; }}
button {{ background: #2563eb; color: #fff; border-color: transparent; }}
.err {{ color: #dc2626; opacity: 1; }}
</style></head><body>
<form method="post" action="{action}">
<h1>{title}</h1>
<p>이 앱은 토큰으로 막혀 있습니다. 함대 모니터의 배포 화면에서 '토큰 보기' 로 볼 수 있습니다.</p>
{error}<input type="password" name="token" placeholder="토큰" autocomplete="current-password" autofocus required>
<button type="submit">열기</button>
</form></body></html>
"""


async def _drain(writer):
    """보낸 것이 나갈 때까지 기다린다. 받는 쪽이 읽지 않으면 TimeoutError - 연결을 붙들고 있지 않는다."""
    await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)


class Gate:
    def __init__(self, root, entry="index.html", token=None, server=None, cwd=None, port=0, tls=True,
                 title="", python=sys.executable):
        self.root = Path(root).resolve()
        self.entry = entry
        self.token = token or None
        self.server = str(server) if server else None
        self.cwd = str(cwd) if cwd else None
        self.scheme = "https" if tls else "http"
        self.title = title or "앱"
        self.python = python
        self.cookie_name = f"aimem_deploy_{port}"       # 쿠키는 포트를 가리지 않는다 - 배포마다 이름을 달리한다
        self.cookie_val = (hashlib.sha256(("aimem-deploy-cookie:" + self.token).encode("utf-8")).hexdigest()
                           if self.token else None)
        self.proc = None
        self.backend_port = None
        self._respawn = None
        self.conns = 0

    # -- 앱 서버 ----------------------------------------------------------------
    def start_backend(self, timeout=8.0):
        """앱 서버를 빈 포트에 띄우고 포트가 열릴 때까지 기다린다. 못 띄우면 RuntimeError."""
        if self.proc is not None and self.proc.poll() is None and self.backend_port and _port_open(self.backend_port):
            return
        self.stop_backend()
        port = _free_port()
        env = {k: v for k, v in os.environ.items() if k != TOKEN_ENV}
        try:
            self.proc = subprocess.Popen([self.python, self.server, "--host", "127.0.0.1", "--port", str(port)],
                                         cwd=self.cwd, env=env, stdin=subprocess.DEVNULL)
        except OSError as e:
            raise RuntimeError(f"앱 서버를 띄우지 못했습니다 ({type(e).__name__})") from None
        deadline = time.monotonic() + timeout
        while not _port_open(port, 0.2):
            if self.proc.poll() is not None:
                raise RuntimeError("앱 서버가 바로 끝났습니다 - `--host 127.0.0.1 --port <포트>` 로 뜨는 서버인지 보십시오")
            if time.monotonic() > deadline:
                self.stop_backend()
                raise RuntimeError(f"앱 서버가 {int(timeout)}초 안에 포트를 열지 않았습니다")
            time.sleep(0.1)
        self.backend_port = port

    def stop_backend(self):
        proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(2)

    # -- 응답 도우미 -------------------------------------------------------------
    @staticmethod
    def _log(req, status):
        sys.stderr.write("%s %s %s\n" % (req.method if req else "-", req.path[:200] if req else "-", status))
        sys.stderr.flush()

    async def _send(self, writer, req, status, body=b"", ctype=None, extra=None, close=False):
        head = [f"HTTP/1.1 {status} {_STATUS.get(status, 'OK')}"]
        if ctype:
            head.append(f"Content-Type: {ctype}")
        head.append(f"Content-Length: {len(body)}")
        head.append("X-Content-Type-Options: nosniff")
        for k, v in (extra or {}).items():
            head.append(f"{k}: {v}")
        if close:
            head.append("Connection: close")
        out = ("\r\n".join(head) + "\r\n\r\n").encode("latin-1")
        if not (req and req.method == "HEAD") and status != 304:
            out += body
        writer.write(out)
        await _drain(writer)
        self._log(req, status)
        return not close

    async def _json(self, writer, req, status, message, extra=None, close=False):
        body = json.dumps({"ok": False, "error": message}, ensure_ascii=False).encode("utf-8")
        return await self._send(writer, req, status, body, "application/json; charset=utf-8", extra, close)

    # -- 인증 -------------------------------------------------------------------
    def authorized(self, req):
        if not self.token:
            return True
        auth = req.get("authorization") or ""
        if auth[:7].lower() == "bearer " and hmac.compare_digest(auth[7:].strip().encode("utf-8"),
                                                                 self.token.encode("utf-8")):
            return True
        for piece in (req.get("cookie") or "").split(";"):
            name, _, value = piece.strip().partition("=")
            if name == self.cookie_name and hmac.compare_digest(value.encode("utf-8"), self.cookie_val.encode("utf-8")):
                return True
        return False

    def _login_page(self, error=""):
        err = f'<p class="err">{html.escape(error)}</p>\n' if error else ""
        return LOGIN_PAGE.format(action=LOGIN_PATH, title=html.escape(self.title), error=err).encode("utf-8")

    async def _login_response(self, writer, req, error="", close=False):
        return await self._send(writer, req, 401, self._login_page(error), "text/html; charset=utf-8",
                                {"Cache-Control": "no-store",
                                 "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"},
                                close)

    async def _login(self, req, reader, writer):
        if req.method in ("GET", "HEAD"):
            if self.authorized(req):
                return await self._send(writer, req, 303, extra={"Location": "/"}, close=req.has_body)
            return await self._login_response(writer, req, close=req.has_body)
        if req.method != "POST":
            return await self._json(writer, req, 405, "허용되지 않는 메서드입니다", {"Allow": "GET, POST"}, close=req.has_body)
        try:
            length = int(req.get("content-length") or "")
        except ValueError:
            length = -1
        if not 0 <= length <= LOGIN_BODY_MAX:
            return await self._json(writer, req, 400, "요청이 올바르지 않습니다", close=True)
        try:
            raw = await asyncio.wait_for(reader.readexactly(length), HEAD_TIMEOUT)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, OSError):
            return False
        given = (parse_qs(raw.decode("utf-8", "replace")).get("token") or [""])[0].strip()
        if not hmac.compare_digest(given.encode("utf-8"), self.token.encode("utf-8")):
            await asyncio.sleep(0.5)
            return await self._login_response(writer, req, "토큰이 맞지 않습니다", close=True)
        cookie = f"{self.cookie_name}={self.cookie_val}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax"
        if self.scheme == "https":
            cookie += "; Secure"
        return await self._send(writer, req, 303, extra={"Location": "/", "Set-Cookie": cookie, "Cache-Control": "no-store"})

    # -- 요청 하나 ---------------------------------------------------------------
    async def respond(self, req, reader, writer):
        """요청 하나를 처리한다. 돌려주는 값 = 이 연결을 계속 쓸 수 있나."""
        is_api = req.path == "/api" or req.path.startswith("/api/")
        if self.token and req.path == LOGIN_PATH:
            return await self._login(req, reader, writer)
        if not self.authorized(req):
            if is_api or req.method not in ("GET", "HEAD"):
                return await self._json(writer, req, 401, "인증이 필요합니다", {"WWW-Authenticate": "Bearer"}, close=True)
            return await self._login_response(writer, req, close=True)      # 토큰 없는 연결은 붙들어 두지 않는다
        if is_api and self.server:
            await self._proxy(req, reader, writer)
            return False
        if req.method not in ("GET", "HEAD"):
            return await self._json(writer, req, 405, "허용되지 않는 메서드입니다", {"Allow": "GET, HEAD"}, close=req.has_body)
        if req.has_body:
            return await self._json(writer, req, 400, "요청이 올바르지 않습니다", close=True)
        return await self._static(req, writer)

    async def _static(self, req, writer):
        target = safe_file(self.root, self.entry, req.path)
        if target is None:
            return await self._json(writer, req, 404, "없는 파일입니다")
        try:
            st = target.stat()
            data = target.read_bytes()
        except OSError:
            return await self._json(writer, req, 404, "없는 파일입니다")
        etag = f'W/"{st.st_mtime_ns:x}-{st.st_size:x}"'
        extra = {"Cache-Control": "no-cache", "ETag": etag}
        if req.get("if-none-match") == etag:
            return await self._send(writer, req, 304, extra=extra)
        return await self._send(writer, req, 200, data, guess_mime(target), extra)

    # -- 앱 서버로 넘기기 ---------------------------------------------------------
    def _backend_head(self, req, port):
        origin = req.get("origin")
        lines = [f"{req.method} {req.target} HTTP/1.1", f"Host: 127.0.0.1:{port}", "Connection: close"]
        if origin is not None:
            lines.append(f"Origin: http://127.0.0.1:{port}")
        for name, value in req.headers:
            low = name.lower()
            if low in _HOP or low == "origin":
                continue
            if self.token and low == "authorization":
                continue                                   # 배포 토큰은 앱 서버로 넘기지 않는다
            if low == "cookie":
                kept = [p.strip() for p in value.split(";")
                        if p.strip() and not p.strip().lower().startswith(OWN_COOKIE_PREFIX)]
                if not kept:
                    continue
                value = "; ".join(kept)
            lines.append(f"{name}: {value}")
        return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")

    async def _connect_backend(self):
        for attempt in (0, 1):
            try:
                return await asyncio.open_connection("127.0.0.1", self.backend_port, limit=HEAD_MAX)
            except OSError:
                if attempt:
                    return None
                if self._respawn is None:
                    self._respawn = asyncio.Lock()
                async with self._respawn:
                    try:
                        await asyncio.get_running_loop().run_in_executor(None, self.start_backend)
                    except RuntimeError as e:
                        sys.stderr.write(f"{e}\n")
                        return None
        return None

    async def _proxy(self, req, reader, writer):
        origin = req.get("origin")
        site = req.get("sec-fetch-site")
        if ((origin is not None and origin.lower() != f"{self.scheme}://{(req.get('host') or '').lower()}")
                or (site is not None and site.strip().lower() not in ("same-origin", "none"))):
            return await self._json(writer, req, 403, "허용되지 않은 출처입니다", close=True)
        conn = await self._connect_backend()
        if conn is None:
            return await self._json(writer, req, 502, "앱 서버에 연결하지 못했습니다", close=True)
        b_reader, b_writer = conn

        async def upload():
            try:
                while True:
                    chunk = await reader.read(CHUNK)
                    if not chunk:
                        break
                    b_writer.write(chunk)
                    await _drain(b_writer)
                if b_writer.can_write_eof():
                    b_writer.write_eof()        # 보내던 쪽이 끊겼다 - 앱 서버가 남은 본문을 기다리며 붙들려 있지 않게
            except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
                pass

        up = None
        try:
            b_writer.write(self._backend_head(req, self.backend_port))
            await _drain(b_writer)
            up = asyncio.ensure_future(upload())
            try:
                head = await asyncio.wait_for(b_reader.readuntil(b"\r\n\r\n"), IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                return await self._json(writer, req, 504, "앱 서버가 제때 응답하지 않았습니다", close=True)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
                return await self._json(writer, req, 502, "앱 서버와 통신하지 못했습니다", close=True)
            lines = head[:-4].split(b"\r\n")
            kept = [lines[0]] + [ln for ln in lines[1:]
                                 if ln.split(b":", 1)[0].strip().lower() not in (b"connection", b"keep-alive")]
            writer.write(b"\r\n".join(kept) + b"\r\nConnection: close\r\n\r\n")
            await _drain(writer)
            self._log(req, lines[0].split(b" ")[1].decode("latin-1") if lines[0].count(b" ") else "?")
            while True:
                chunk = await asyncio.wait_for(b_reader.read(CHUNK), IDLE_TIMEOUT)
                if not chunk:
                    break
                writer.write(chunk)
                await _drain(writer)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            if up is not None:
                up.cancel()
            b_writer.close()

    # -- 연결 -------------------------------------------------------------------
    async def handle(self, reader, writer):
        if self.conns >= MAX_CONNS:
            writer.close()
            return
        self.conns += 1
        try:
            for _ in range(MAX_REQUESTS):
                try:
                    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEAD_TIMEOUT)
                except (asyncio.IncompleteReadError, asyncio.TimeoutError, OSError):
                    return
                except asyncio.LimitOverrunError:
                    await self._json(writer, None, 400, "요청 머리가 너무 큽니다", close=True)
                    return
                req = parse_head(raw)
                if req is None:
                    await self._json(writer, None, 400, "요청이 올바르지 않습니다", close=True)
                    return
                if not await self.respond(req, reader, writer):
                    return
                if req.version == "HTTP/1.0" or (req.get("connection") or "").lower() == "close":
                    return
        except (OSError, asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            self.conns -= 1
            try:
                writer.close()
            except OSError:
                pass


async def serve(gate, host, port, ssl_ctx=None, ready=None):
    server = await asyncio.start_server(gate.handle, host, port, ssl=ssl_ctx, limit=HEAD_MAX,
                                        **({"ssl_handshake_timeout": 10} if ssl_ctx else {}))
    if ready is not None:
        ready(server.sockets[0].getsockname()[1])
    async with server:
        await server.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description="배포 문지기 - 인증서·토큰·공개 여부를 앱 대신 맡는다")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--root", required=True, help="앱 폴더 (app.json root)")
    ap.add_argument("--entry", default="index.html")
    ap.add_argument("--server", help="앱 서버 파일 (app.json server) - /api/* 를 넘긴다")
    ap.add_argument("--cwd", help="앱 서버를 띄울 폴더 (프로젝트 폴더)")
    ap.add_argument("--title", default="")
    ap.add_argument("--tls-cert")
    ap.add_argument("--tls-key")
    args = ap.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("문지기는 루프백에만 뜹니다 - 바깥으로는 윈도우 프록시가 잇습니다", file=sys.stderr)
        return 2
    if bool(args.tls_cert) != bool(args.tls_key):
        print("--tls-cert 와 --tls-key 는 같이 줍니다", file=sys.stderr)
        return 2
    if not Path(args.root).is_dir():
        print(f"앱 폴더가 없습니다: {args.root}", file=sys.stderr)
        return 2
    ssl_ctx = None
    if args.tls_cert:
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            ssl_ctx.load_cert_chain(args.tls_cert, args.tls_key)
        except (OSError, ssl.SSLError) as e:
            print(f"인증서를 읽지 못했습니다 ({type(e).__name__})", file=sys.stderr)
            return 2
    token = os.environ.pop(TOKEN_ENV, None) or None
    gate = Gate(args.root, args.entry, token=token, server=args.server, cwd=args.cwd or None, port=args.port,
                tls=ssl_ctx is not None, title=args.title)
    if gate.server:
        try:
            gate.start_backend()
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1

    def stop(*_):
        gate.stop_backend()
        os._exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("배포 문지기 %s://%s:%s  (%s, 앱 서버 %s)" % (
        gate.scheme, args.host, args.port, "토큰으로 막음" if token else "누구나",
        f"127.0.0.1:{gate.backend_port}" if gate.server else "없음"), file=sys.stderr, flush=True)
    try:
        asyncio.run(serve(gate, args.host, args.port, ssl_ctx))
    finally:
        gate.stop_backend()
    return 0


if __name__ == "__main__":
    sys.exit(main())
