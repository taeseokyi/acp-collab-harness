#!/usr/bin/env python3
"""웹워들 브라우저 검증용 공용 하네스."""
import functools
import json
import socketserver
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from serve import Handler


GROUP = "core"


def set_group(name):
    global GROUP
    GROUP = name


@contextmanager
def server():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(
        ("127.0.0.1", 0),
        functools.partial(Handler, directory=str(ROOT / "web")),
    )
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


_WIKI_MISSING = json.dumps({"query": {"pages": [{"missing": True}]}})
_NOT_FOUND = json.dumps({"ok": True, "found": False, "source": "wiktionary", "via": "server", "evidence": "테스트 가짜"})
_LLM_NO = json.dumps({"choices": [{"message": {"content": "아니오"}}]})


def install_dict_routes(context):
    """새 context 마다 외부 사전 기본 라우트를 건다: 진짜 외부망을 부르지 않고 '없음' 으로 답한다.

    시나리오가 같은 context 에 자기 라우트를 더 걸면 그것이 먼저 적용된다(Playwright 는 나중에 건 라우트 우선).
    """
    def fulfill(body):
        return lambda route: route.fulfill(
            status=200, content_type="application/json",
            headers={"access-control-allow-origin": "*"}, body=body)

    context.route("**/api/lookup**", fulfill(_NOT_FOUND))
    for pattern in ("https://*.wikipedia.org/**", "https://*.wiktionary.org/**"):
        context.route(pattern, fulfill(_WIKI_MISSING))
    for pattern in ("https://generativelanguage.googleapis.com/**", "https://openrouter.ai/**"):
        context.route(pattern, fulfill(_LLM_NO))


def new_page(browser, base, viewport=None, clipboard=False):
    context_options = {
        "viewport": viewport or {"width": 420, "height": 900},
    }
    if clipboard:
        context_options["permissions"] = ["clipboard-read", "clipboard-write"]
    context = browser.new_context(**context_options)
    install_dict_routes(context)
    page = context.new_page()
    page._errors = []
    page._context = context
    page._close_context = context.close

    def collect_pageerror(error):
        page._errors.append(f"pageerror: {error}")

    def collect_console(message):
        if message.type == "error":
            page._errors.append(f"console: {message.text}")

    page.on("pageerror", collect_pageerror)
    page.on("console", collect_console)
    page.goto(base + "/index.html", wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    return page


def shot(page, name, full_page=False):
    path = ROOT / "tests" / "screenshots" / GROUP / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full_page)
    return path


class Checks:
    def __init__(self):
        self.results = []

    def ok(self, goal, cond, detail=""):
        passed = bool(cond)
        self.results.append((passed, goal, detail))
        return passed

    def finish(self):
        failures = 0
        for passed, goal, detail in self.results:
            line = f"[{'OK' if passed else 'FAIL'}] {goal}"
            if detail:
                line += f" - {detail}"
            print(line)
            if not passed:
                failures += 1
        print(f"통과 {len(self.results) - failures} / 전체 {len(self.results)}")
        return failures
