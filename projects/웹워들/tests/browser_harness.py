#!/usr/bin/env python3
"""웹워들 브라우저 검증용 공용 하네스."""
import functools
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


def new_page(browser, base, viewport=None, clipboard=False):
    context_options = {
        "viewport": viewport or {"width": 420, "height": 900},
    }
    if clipboard:
        context_options["permissions"] = ["clipboard-read", "clipboard-write"]
    context = browser.new_context(**context_options)
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
