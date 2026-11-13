#!/usr/bin/env python3
"""웹워들 로컬 실행용 정적 서버 (표준 라이브러리만).

    python3 projects/웹워들/serve.py [--port 18811] [--host 127.0.0.1]

`web/` 아래만 내려줍니다. 백엔드가 없으므로 이 서버는 파일을 주는 일 말고는 하는 일이 없습니다.
개발 중 바뀐 파일이 바로 보이도록 캐시를 끕니다.
"""
import argparse
import functools
import http.server
import socketserver
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
    }

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # 조용히 - 실패만 보입니다
        if not str(args[1] if len(args) > 1 else "").startswith("2"):
            super().log_message(fmt, *args)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18811)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if not (WEB / "index.html").exists():
        print(f"없습니다: {WEB / 'index.html'}")
        return 1

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(
        (args.host, args.port), functools.partial(Handler, directory=str(WEB))
    ) as httpd:
        print(f"웹워들 http://{args.host}:{args.port}  (Ctrl-C 로 멈춤)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
