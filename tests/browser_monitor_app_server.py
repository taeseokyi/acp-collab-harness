#!/usr/bin/env python3
"""R32 끝에서 끝 브라우저 검사: 모니터의 '앱 열기' 에서도 자모맞히기의 serve.py 가 이어져 정답 정하기가 되는가.

진짜 모니터(`python3 -m aimem_monitor --auth`)를 임시 루트·임시 포트에 띄우고, 임시 루트에는 이 저장소의
`projects/자모맞히기` **복사본**만 둔다(진짜 `data/` 는 쓰지 않는다). 복사본의 `serve_fake.py` 가 뉴스 고르기를
가짜(오늘부터 N일 낱말)로 바꾼다. 선언을 지운 두 번째 복사본은 '서버 없음' 글을 확인한다.
끝나면 모니터를 내리고 앱 서버 자식 pid 가 남지 않았는지 본다. 화면은 그려진 것(is_visible·글)을 본다.
"""
import json
import os
import pathlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import server          # noqa: E402

NAME = "자모맞히기"
NAME_NOSERVER = "자모맞히기b"
SRC = ROOT / "projects" / NAME

FAKE_SERVE = '''"""검사용 - serve 의 뉴스 고르기를 가짜(오늘부터 N일 낱말)로 바꿔 띄운다."""
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import serve  # noqa: E402

WORDS = %(words)s


def fake_pick(days, source="wiktionary", start=None, *, skip_dates=(), **_):
    day = date.fromisoformat(start) if start else date.today()
    skip = set(skip_dates or ())
    picks = []
    for _ in range(400):
        if len(picks) >= days:
            break
        if day.isoformat() not in skip:
            picks.append({"date": day.isoformat(), "word": WORDS[len(picks) %% len(WORDS)]})
        day += timedelta(days=1)
    return {"ok": True, "picks": picks, "titles": 42, "candidates": 10}


serve.Handler.trend_pick = staticmethod(fake_pick)
raise SystemExit(serve.main())
'''


class Checks:
    def __init__(self):
        self.results = []

    def ok(self, goal, cond, detail=""):
        self.results.append((bool(cond), goal, detail))
        return bool(cond)

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


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:                                    # 좀비(끝났지만 거두지 않음)는 없는 것으로 친다
        return pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def fake_words():
    """정적 TREND 의 낱말(이미 자모 6칸·사전 확인됨)에서 서로 다른 것을 고른다."""
    text = (SRC / "web" / "js" / "words.js").read_text(encoding="utf-8")
    m = re.search(r"export const TREND = (\{.*?\});", text, re.S)
    values = list(dict.fromkeys(json.loads(m.group(1)).values()))
    return values[1:9]                       # 첫 낱말은 오늘 정적 정답일 수 있어 건너뜀


def build_root(tmp, words):
    """임시 루트에 복사본 둘: 서버 선언(serve_fake.py)을 가진 것과 선언을 지운 것."""
    ignore = shutil.ignore_patterns("__pycache__", "tests", "screenshots", "node_modules", ".git")
    p1 = tmp / "projects" / NAME
    shutil.copytree(SRC, p1, ignore=ignore)
    (p1 / "data" / "trend.txt").write_text("# 검사용 빈 정답표\n", encoding="utf-8")
    (p1 / "data" / "trend_meta.json").unlink(missing_ok=True)
    (p1 / "serve_fake.py").write_text(FAKE_SERVE % {"words": json.dumps(words, ensure_ascii=False)},
                                      encoding="utf-8")
    app = json.loads((p1 / "app.json").read_text(encoding="utf-8"))
    app["server"] = "serve_fake.py"
    (p1 / "app.json").write_text(json.dumps(app, ensure_ascii=False), encoding="utf-8")
    p2 = tmp / "projects" / NAME_NOSERVER
    shutil.copytree(p1, p2)
    app.pop("server")
    app["title"] = NAME_NOSERVER
    (p2 / "app.json").write_text(json.dumps(app, ensure_ascii=False), encoding="utf-8")
    return p1, p2


class Monitor:
    """진짜 모니터 프로세스(임시 루트·임시 포트·인증 켬)."""

    def __init__(self, root):
        self.root = root
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log = open(root / "monitor.out", "w", encoding="utf-8")
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TZ") if k in os.environ}
        env["PYTHONPATH"] = str(ROOT / "tools")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "aimem_monitor", "--root", str(root), "--port", str(self.port), "--auth"],
            cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT)

    def wait_up(self, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError("모니터가 떴다가 죽음: " + (self.root / "monitor.out").read_text()[-300:])
            try:
                urllib.request.urlopen(self.base + "/api/authinfo", timeout=2).read()
                return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("모니터가 뜨지 않음")

    def token(self):
        tok, _ = server.ensure_access_token(self.root, create=False)
        return tok

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()


def child_pids(root):
    out = []
    d = root / ".aimem" / "appservers"
    for f in d.glob("*.json") if d.exists() else []:
        try:
            out.append(int(json.loads(f.read_text(encoding="utf-8"))["pid"]))
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- 화면 도우미


def dismiss_help(page):
    if page.locator("#modal-help:not([hidden])").count():
        page.keyboard.press("Escape")
        page.wait_for_function("() => document.getElementById('modal-help').hidden === true")


def open_settings(page):
    dismiss_help(page)
    if not page.locator("#modal-settings:not([hidden])").count():
        page.click("#btn-settings")
        page.wait_for_selector("#modal-settings:not([hidden])", timeout=5000)
    page.wait_for_timeout(80)


def since_text(page):
    return (page.locator("#trend-since").text_content() or "").strip()


def status_text(page):
    return (page.locator("#trend-status").text_content() or "").strip()


def wait_status(page, needle, timeout=20000):
    try:
        page.wait_for_function(
            "(n) => document.getElementById('trend-status').textContent.includes(n)", arg=needle, timeout=timeout)
        return True
    except Exception:
        return False


def type_word(page, word):
    units = page.evaluate("async (w) => { const j = await import('./js/jamo.js'); return j.toUnits(w); }", word)
    rev = page.evaluate(
        "async () => { const j = await import('./js/jamo.js'); const out = {};"
        " for (const [code, pair] of Object.entries(j.KEYMAP)) {"
        "   out[pair[0]] = [code, false]; if (pair[1] !== pair[0]) out[pair[1]] = [code, true]; } return out; }")
    for unit in units:
        code, shifted = rev[unit]
        page.keyboard.press(("Shift+" if shifted else "") + code)


def won_with(page, word):
    type_word(page, word)
    page.keyboard.press("Enter")
    try:
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#board .row:nth-child(1) .tile'))"
            ".every((t) => ['correct', 'present', 'absent'].includes(t.dataset.state))", timeout=8000)
    except Exception:
        return False
    states = page.evaluate("() => Array.from(document.querySelectorAll('#board .row:nth-child(1) .tile'))"
                           ".map((t) => t.dataset.state)")
    return set(states) == {"correct"}


def open_app_top(ctx, base, name, errors=None):
    """'앱 열기' 주소를 최상위로 열어(서버가 티켓 경로로 302) 불러온 페이지를 돌려준다."""
    page = ctx.new_page()
    if errors is not None:
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto(f"{base}/app/{name}/", wait_until="load")
    page.wait_for_selector("#board .tile", timeout=15000)
    return page


# ---------------------------------------------------------------- 시나리오


def scenario(browser, mon, p1, p2, words, checks):
    base = mon.base
    ctx = browser.new_context(viewport={"width": 1000, "height": 900})
    r = ctx.request.post(base + "/api/login", data={"token": mon.token()},
                         headers={"Content-Type": "application/json"})
    checks.ok("모니터에 로그인", r.status == 200, f"status={r.status}")

    # 1. 모니터 화면의 '앱 열기'(실행) → iframe 이 티켓 경로로 뜬다 (자모맞히기 한 줄)
    host = ctx.new_page()
    host.goto(base + "/", wait_until="load")
    host.click("#tab-projects")
    host.wait_for_selector("#projects-list .proj-item", timeout=10000)
    item = host.locator("#projects-list .proj-item", has_text=NAME).first
    run = item.locator(".proj-run").first
    run.wait_for(state="attached", timeout=10000)
    run.click()
    frame_el = host.locator("iframe.proj-app-frame")
    frame_el.wait_for(state="visible", timeout=10000)
    fl = host.frame_locator("iframe.proj-app-frame")
    fl.locator("#board .tile").first.wait_for(state="attached", timeout=15000)
    furls = [f.url for f in host.frames if f != host.main_frame]
    checks.ok("앱 열기: iframe 이 티켓 경로로 뜬다", any("/app/~" in u for u in furls), f"frame={[u[:50] for u in furls]}")
    checks.ok("앱 열기: 자모맞히기 보드가 그려졌다", fl.locator("#board .tile").first.is_visible())
    if fl.locator("#modal-help:not([hidden])").count():
        fl.locator("#modal-help .modal-close").click()
        fl.locator("#modal-help[hidden]").wait_for(state="attached", timeout=5000)
    fl.locator("#btn-settings").click()
    fl.locator("#modal-settings:not([hidden])").wait_for(timeout=5000)
    # 서버가 이어져 있으면 GET api/trend 가 되어 '서버 없이…' 글이 아니다
    fl.locator("#trend-since").wait_for(state="visible", timeout=5000)
    txt_iframe = (fl.locator("#trend-since").text_content() or "").strip()
    checks.ok("앱 열기(iframe) 설정 창: 정한 때 글이 서버 없는 글이 아니다",
              txt_iframe == "아직 정한 적 없음", f"글={txt_iframe!r}")
    host.close()

    # 2. 최상위로 연 앱 - 정답 정하기 흐름
    errors = []
    page = open_app_top(ctx, base, NAME, errors)
    checks.ok("티켓 경로로 열렸다", "/app/~" in page.url, page.url[:60])
    open_settings(page)
    checks.ok("정답 정하기 단추가 보인다", page.locator("#trend-pick").is_visible())
    checks.ok("정하기 전: '아직 정한 적 없음'", since_text(page) == "아직 정한 적 없음", f"글={since_text(page)!r}")

    today = time.strftime("%Y-%m-%d")
    page.click("#trend-pick")
    got = wait_status(page, "일치 정답을 골랐습니다")
    checks.ok("단추: 상태 글에 일수가 나온다", got and "7일치" in status_text(page), f"글={status_text(page)!r}")
    checks.ok("단추: 정한 때가 '방금 정함'", since_text(page) == "방금 정함", f"글={since_text(page)!r}")
    trend_txt = (p1 / "data" / "trend.txt").read_text(encoding="utf-8")
    lines = [ln for ln in trend_txt.splitlines() if ln and not ln.startswith("#")]
    checks.ok("복사본 data/trend.txt 에 덧붙음", len(lines) == 7 and lines[0].split()[1] == words[0],
              f"줄 {len(lines)}개 첫 줄={lines[:1]}")
    meta = p1 / "data" / "trend_meta.json"
    ok_meta = meta.exists() and bool(json.loads(meta.read_text(encoding="utf-8")).get("last_run"))
    checks.ok("복사본 data/trend_meta.json 이 생김", ok_meta)

    # 3. 새로 고친 뒤에도 서버가 정본
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=15000)
    open_settings(page)
    checks.ok("새로 고친 뒤에도 '방금 정함'(서버가 정본)", since_text(page) == "방금 정함", f"글={since_text(page)!r}")

    # 4. 빈 오늘 판이면 오늘 정답은 가짜의 낱말 - 그 낱말을 내면 이긴다
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")
    checks.ok("오늘 정답이 가짜 낱말(그 낱말을 내면 이김)", won_with(page, words[0]), f"낱말={words[0]!r} 오늘={today}")

    # 5. 같은 출처 길: GET api/trend(사전 요청 없는 단순 요청)·사전 조회 api/sources
    info = page.evaluate(
        """async () => {
          const t = await fetch('api/trend');
          const s = await fetch('api/sources');
          return { t: t.status, tj: await t.json(), s: s.status, sj: await s.json() };
        }""")
    checks.ok("GET api/trend 가 사전 요청 없이 된다",
              info["t"] == 200 and info["tj"].get("ok") is True and len(info["tj"]["trend"]) == 7
              and bool(info["tj"].get("last_run")), f"status={info['t']}")
    checks.ok("사전 조회 api/sources 도 이어진다", info["s"] == 200 and isinstance(info["sj"].get("sources"), list),
              f"status={info['s']} 사전 {len(info['sj'].get('sources') or [])}개")
    checks.ok("자바스크립트 오류 없음", not errors, "; ".join(errors[:3]))
    page.close()

    # 6. 선언을 지운 앱: 단추가 서버 없음 글
    nosrv = open_app_top(ctx, base, NAME_NOSERVER)
    open_settings(nosrv)
    nosrv.click("#trend-pick")
    got = wait_status(nosrv, "serve.py 로 열었을 때만", timeout=10000)
    checks.ok("선언 없는 앱: 단추가 서버 없음 글", got, f"글={status_text(nosrv)!r}")
    checks.ok("선언 없는 앱: 정한 때를 모른다는 글",
              since_text(nosrv) == "서버 없이 열어 정한 때를 모릅니다", f"글={since_text(nosrv)!r}")
    untouched = (p2 / "data" / "trend.txt").read_text(encoding="utf-8")
    checks.ok("선언 없는 앱: 정답 파일은 그대로", untouched == "# 검사용 빈 정답표\n"
              and not (p2 / "data" / "trend_meta.json").exists())
    nosrv.close()
    ctx.close()


def main():
    checks = Checks()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="browser-monitor-app-server-"))
    mon = None
    pids = []
    try:
        words = fake_words()
        p1, p2 = build_root(tmp, words)
        mon = Monitor(tmp)
        mon.wait_up()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                scenario(browser, mon, p1, p2, words, checks)
            finally:
                browser.close()
        pids = child_pids(tmp)
        checks.ok("앱 서버 자식이 떴었다(기록 있음)", len(pids) >= 1 and all(alive(p) for p in pids), f"pid={pids}")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
        pids = pids or child_pids(tmp)
    finally:
        if mon:
            mon.stop()
        time.sleep(0.3)
        left = [p for p in pids if alive(p)]
        checks.ok("모니터를 내린 뒤 자식 pid 가 없음", not left and mon is not None, f"남은 pid={left} (기록 {pids})")
        for p in left:                      # 남았으면 pid 로 정리(pkill -f 안 씀)
            try:
                os.killpg(p, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
