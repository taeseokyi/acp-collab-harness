#!/usr/bin/env python3
"""자모맞히기 로컬 실행용 서버 (표준 라이브러리만).

    python3 projects/자모맞히기/serve.py [--port 18811] [--host 127.0.0.1]

`web/` 아래 정적 파일과, 외부 사전 조회용 `/api/*` 를 냅니다. 개발 중 바뀐 파일이 바로 보이도록 캐시를 끕니다.

    GET  /api/sources                       -> {"sources": [...]}   (키 값은 없음)
    GET  /api/lookup?word=한국&source=stdict -> 조회 결과 JSON

    GET  /api/trend                         -> {"ok", "trend": {날짜: 낱말}, "last_run": ISO|null}  (data/trend.txt 정본)
    POST /api/trend/pick  {"source","days"(1~14),"start","skip"} -> 연합뉴스 RSS 로 고른 날짜별 정답 JSON.
        빈 날짜만 `data/trend.txt` 에 덧붙이고(이미 있는 날짜는 안 덮음) `data/trend_meta.json` 에 시각을 적습니다
        (trend_store.pick_and_store - tools/pick_answers.py 와 같은 함수). 응답에 added·trend·last_run 이 붙습니다.

그 밖의 POST /api/* 는 405 입니다(custom 사용자 LLM 은 화면이 브라우저에서 직접 부르므로 서버 중계 길이 없음).
`/api/*` 는 교차 출처 호출을 막습니다 - `Host` 머리가 127.0.0.1·localhost·[::1]·`--host` 값이 아니면 403(DNS 되돌림 방어),
`Origin` 머리가 있고 `http://<Host 머리>` 와 다르면 403(남의 페이지가 내 서버의 키 쓰는 길을 부르는 것 방어).

외부 사전 키는 저장소 루트 `.env`(`KEY=값` 줄) 또는 환경변수로 넣습니다. 서버만 알고 브라우저에는 나가지 않습니다.
  STDICT_API_KEY(표준국어대사전) OPENDICT_API_KEY(우리말샘) KRDICT_API_KEY(한국어기초사전)
  KISTI_API_KEY(kistillm) EXAONE_API_KEY(exaone) GEMINI_API_KEY(gemini) OPENROUTER_API_KEY(+OPENROUTER_FREE_MODEL)
위키낱말사전·위키백과는 키가 없습니다. 자세한 표와 키 받는 곳은 dict_server.py 첫머리.
"""
import argparse
import datetime
import functools
import http.server
import json
import re
import socketserver
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import dict_server  # noqa: E402
import trend_news  # noqa: E402
import trend_store  # noqa: E402

WEB = HERE / "web"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
PICK_BODY_MAX = 4096


def _is_date(text) -> bool:
    if not (isinstance(text, str) and DATE_RE.fullmatch(text)):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


_PICK_LOCK = threading.Lock()  # 뉴스 정답 고르기는 한 번에 하나만


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
    }

    # 검사가 가짜를 갈아 끼울 수 있게 클래스 속성으로 (staticmethod 라 self 가 안 붙음)
    lookup = staticmethod(dict_server.lookup)
    trend_pick = staticmethod(trend_news.pick)
    # 정답 파일 위치 - 검사가 임시 경로로 바꿔 진짜 data/ 를 쓰지 않게 함
    trend_path = trend_store.TREND_PATH
    meta_path = trend_store.META_PATH
    timeout = 30  # 느리게 붙은 연결이 스레드를 오래 붙들지 않게

    def _json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _host_name(self):
        """Host 머리에서 포트를 뺀 호스트 (없으면 빈 문자열)."""
        h = (self.headers.get("Host") or "").strip().lower()
        if h.startswith("["):
            return h[: h.find("]") + 1] if "]" in h else ""
        return h.rsplit(":", 1)[0] if ":" in h else h

    def _same_origin_ok(self):
        host_header = (self.headers.get("Host") or "").strip()
        bound = str(self.server.server_address[0]).lower()
        if self._host_name() not in LOCAL_HOSTS | {bound, f"[{bound}]"}:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://{host_header}"

    def _api(self, method):
        if not self._same_origin_ok():
            return self._json(403, {"ok": False, "error": "허용되지 않은 출처입니다"})
        if method == "POST" and urlsplit(self.path).path == "/api/trend/pick":
            return self._trend_pick()
        if method != "GET":
            return self._json(405, {"ok": False, "error": "GET 만 받습니다"})
        u = urlsplit(self.path)
        if u.path == "/api/sources":
            return self._json(200, {"sources": dict_server.available_sources()})
        if u.path == "/api/trend":
            return self._json(200, {"ok": True, "trend": trend_store.read_trend(self.trend_path),
                                    "last_run": trend_store.last_run(self.meta_path)})
        if u.path == "/api/lookup":
            q = parse_qs(u.query)
            word = (q.get("word") or [""])[0]
            source = (q.get("source") or ["wiktionary"])[0]
            return self._json(200, self.lookup(word, source))
        return self._json(404, {"ok": False, "error": "없는 경로입니다"})

    def _trend_pick(self):
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._json(400, {"ok": False, "error": "Content-Type 은 application/json 이어야 합니다"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 < length <= PICK_BODY_MAX:
            return self._json(400, {"ok": False, "error": "본문 크기가 맞지 않습니다 (4KB 이하)"})
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = None
        if not isinstance(body, dict):
            return self._json(400, {"ok": False, "error": "본문은 JSON 객체여야 합니다"})
        source = body.get("source", "wiktionary")
        days = body.get("days", 7)
        start = body.get("start")
        skip = body.get("skip", [])
        if source not in dict_server.SOURCES:
            return self._json(400, {"ok": False, "error": "알 수 없는 사전입니다"})
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 14:
            return self._json(400, {"ok": False, "error": "days 는 1~14 입니다"})
        if start is not None and not _is_date(start):
            return self._json(400, {"ok": False, "error": "start 는 YYYY-MM-DD 꼴이어야 합니다"})
        if not isinstance(skip, list) or len(skip) > 60 or not all(
                _is_date(d) for d in skip):
            return self._json(400, {"ok": False, "error": "skip 은 YYYY-MM-DD 목록이어야 합니다"})
        if not _PICK_LOCK.acquire(blocking=False):
            return self._json(429, {"ok": False, "error": "이미 고르는 중입니다"})
        try:
            result = trend_store.pick_and_store(days, source, start, skip_dates=skip, pick=self.trend_pick,
                                                path=self.trend_path, meta_path=self.meta_path)
        finally:
            _PICK_LOCK.release()
        return self._json(200, result)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        self.send_error(405)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # 조용히 - 실패만 보입니다
        if not str(args[1] if len(args) > 1 else "").startswith("2"):
            super().log_message(fmt, *args)


class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True  # 사전 조회가 느려도 다른 요청을 막지 않음


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=18811)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if not (WEB / "index.html").exists():
        print(f"없습니다: {WEB / 'index.html'}")
        return 1

    socketserver.TCPServer.allow_reuse_address = True
    with ThreadedServer(
        (args.host, args.port), functools.partial(Handler, directory=str(WEB))
    ) as httpd:
        print(f"자모맞히기 http://{args.host}:{args.port}  (Ctrl-C 로 멈춤)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
