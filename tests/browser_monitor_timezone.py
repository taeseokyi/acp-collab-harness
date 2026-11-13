#!/usr/bin/env python3
"""브라우저 시간대가 한국이 아니어도 모니터가 설정 구역(state.tz) 시계로 시각을 읽고 보이는지 잽니다.

/api/state 응답을 가로채 꾸민 상태를 넣는다(서버 시각 = 한국 시계, 오프셋 없음). 브라우저는 UTC / America/New_York.
"""
import _fleet_env  # noqa: F401
import datetime
import http.server
import json
import pathlib
import re
import sys
import tempfile
import threading
from contextlib import contextmanager
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server  # noqa: E402


class Checks:
    def __init__(self): self.results = []
    def ok(self, goal, cond, detail=""): self.results.append((bool(cond), goal, detail))
    def finish(self):
        failures = sum(not p for p, _, _ in self.results)
        for p, goal, detail in self.results:
            print(f"[{'OK' if p else 'FAIL'}] {goal}" + (f" - {detail}" if detail else ""))
        print(f"통과 {len(self.results) - failures} / 전체 {len(self.results)}")
        return failures


@contextmanager
def monitor_server(root):
    handler = type("H", (server.Handler,), {"root": root, "require_auth": False, "tls": False,
                                            "access_token": None, "guard": server.LoginGuard(),
                                            "timeout": 5, "log_message": lambda *a, **k: None})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=3)


def kst(delta_sec=0, frac=False):
    t = datetime.datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None) - datetime.timedelta(seconds=delta_sec)
    return t.isoformat(timespec="milliseconds" if frac else "seconds")


def utc_z(delta_sec):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=delta_sec)
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def fabricate():
    started = kst(600)
    return {
        "generated": kst(), "tz": {"name": "Asia/Seoul", "offset": "+09:00"},
        "aimem": {"rev": 1, "lines": 1, "updated": "x"}, "slots": [], "board": [], "queue": [], "log": [],
        "runs": [{"id": "r1", "slot": "S1", "harness": "claude", "model": "m", "label": "t", "rev": 1, "write": "",
                  "started": started, "state": "running", "rc": None, "elapsed_sec": 600, "report_head": "",
                  "session_state": "running", "last_event_at": kst(30, True), "last_event": "tool"}],
        "eta": {}, "requests": [], "errors": [], "claude_usage": None, "projects": [], "fleet": {},
        "graphs": [{"id": "G1", "request": None, "created": kst(900), "updated": utc_z(600), "percent": 10,
                    "counts": {"pending": 1}, "nodes": []}],
        "managers": {"sessions": [{"id": "M-R1", "status": "running", "session_state": "running", "label": "관리자",
                                   "started": started, "updated": kst(30), "last_activity": kst(30, True),
                                   "round": 1, "steps": 3}]},
    }


def run_zone(p, base, tzid, c):
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, timezone_id=tzid)
    page = ctx.new_page()
    state = fabricate()
    ctx.route("**/api/state", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(state)))
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector(".manager-step", state="attached", timeout=8000)
        page.wait_for_timeout(300)
        text = page.inner_text("body")
        agos = [int(x) for x in re.findall(r"마지막 사건 (\d+)초 전", text)]
        c.ok(f"[{tzid}] 마지막 사건이 초 단위 (25~60초)", agos and all(25 <= a <= 60 for a in agos), str(agos))
        c.ok(f"[{tzid}] 9시간 어긋남 없음", not re.search(r"마지막 사건 \d+시간", text))
        c.ok(f"[{tzid}] 그래프가 멈춤으로 안 뜸", page.locator(".badge", has_text="멈춤").count() == 0)
        c.ok(f"[{tzid}] 관리자 시작 시각이 한국 시계 숫자", ("시작 " + state["managers"]["sessions"][0]["started"].replace("T", " ")[:16]) in text,
             state["managers"]["sessions"][0]["started"])
        g_upd = (datetime.datetime.now(ZoneInfo("Asia/Seoul")) - datetime.timedelta(seconds=600)).strftime("%Y-%m-%d %H:%M")
        c.ok(f"[{tzid}] Z 붙은 그래프 갱신 시각이 한국 시계로 변환", ("갱신 " + g_upd) in page.text_content("body"), g_upd)
    finally:
        ctx.close(); browser.close()


def main():
    c = Checks()
    with tempfile.TemporaryDirectory() as td, sync_playwright() as p:
        root = pathlib.Path(td)
        (root / ".aimem").mkdir()
        with monitor_server(root) as base:
            for tzid in ("UTC", "America/New_York"):
                run_zone(p, base, tzid, c)
    return 1 if c.finish() else 0


if __name__ == "__main__":
    sys.exit(main())
