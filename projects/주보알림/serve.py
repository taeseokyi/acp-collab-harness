#!/usr/bin/env python3
"""주보알림 HTTP 서버 (표준 라이브러리만): 정적 web/ + /api/*.

    python3 serve.py [--host 127.0.0.1] [--port 18831]

함대 모니터는 app.json 의 `server` 로 이 파일을 띄운다. 화면은 상대 경로
(`api/state`)로 부른다 - 모니터가 /app/주보알림/ 아래로 이어 준다.
"""
import argparse
import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import bulletin  # noqa: E402

WEB = HERE / "web"
PREVIEW_DIR = bulletin.DATA / "preview"
PREVIEW_NAME = re.compile(r"[A-Za-z0-9_.-]+\.jpg\Z")

EXTRA_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _inside(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "JuboAlarm/0.1"
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, value) -> None:
        self._send(code, _json_bytes(value), "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._json(code, {"ok": False, "error": message})

    def _static(self, rel: str) -> None:
        rel = unquote(rel or "")
        if not rel or rel == "/":
            rel = "index.html"
        rel = rel.lstrip("/")
        target = WEB / rel
        if not _inside(WEB, target) or target.is_symlink() or not target.is_file():
            self._error(404, f"그런 파일이 없습니다: {rel[:120]}")
            return
        try:
            body = target.read_bytes()
        except OSError:
            self._error(500, "파일을 읽지 못했습니다")
            return
        mime = EXTRA_MIME.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if mime.startswith("text/") and "charset" not in mime:
            mime += "; charset=utf-8"
        self._send(200, body, mime)

    def _preview_image(self, name: str) -> None:
        if not PREVIEW_NAME.match(name):
            self._error(400, "미리 보기 파일 이름이 올바르지 않습니다")
            return
        target = PREVIEW_DIR / name
        if not _inside(PREVIEW_DIR, target) or target.is_symlink() or not target.is_file():
            self._error(404, "그런 미리 보기 그림이 없습니다")
            return
        try:
            body = target.read_bytes()
        except OSError:
            self._error(500, "그림을 읽지 못했습니다")
            return
        self._send(200, body, "image/jpeg")

    def _api_post(self, action: str) -> None:
        if action == "check":
            result = bulletin.check()
        elif action == "preview":
            result = bulletin.preview()
        elif action == "send":
            result = bulletin.send()
        else:
            self._error(404, f"그런 API 가 없습니다: {action[:60]}")
            return
        self._json(200, {"result": result, "state": bulletin.state()})

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/api/state":
                self._json(200, bulletin.state())
            elif path.startswith("/api/preview/"):
                self._preview_image(path[len("/api/preview/"):])
            elif path.startswith("/api/"):
                self._error(404, "그런 API 가 없습니다")
            elif path == "/":
                self._static("index.html")
            else:
                self._static(path)
        except Exception as exc:
            self._error(500, f"서버 오류: {exc}")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path.startswith("/api/") and path.count("/") == 2:
                action = path[len("/api/"):]
                self._api_post(action)
            else:
                self._error(404, "그런 API 가 없습니다")
        except Exception as exc:
            self._error(500, f"서버 오류: {exc}")

    def do_HEAD(self) -> None:
        self.do_GET()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser(description="주보알림 웹 앱")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18831)
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"서버를 띄우지 못했습니다: {exc}", file=sys.stderr)
        return 1
    print(f"주보알림: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
