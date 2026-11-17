#!/usr/bin/env python3
"""VoxLog 끝에서 끝 브라우저 검사 (크롬만, 파이썬 Playwright).

실행: python3 projects/VoxLog/tests/browser_voxlog.py
서버는 이 검사가 임시 data 폴더로 직접 띄우고(subprocess) 끝나면 내린다.
마지막 줄 `N/M 통과`, 하나라도 실패면 종료 코드 1.
"""
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = []  # (이름, 통과, 까닭)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(data_dir, token=None, stt_cmd=None):
    port = free_port()
    env = dict(os.environ)
    env["VOXLOG_STT"] = "command"
    env["VOXLOG_STT_CMD"] = stt_cmd or "%s %s {wav}" % (sys.executable, HERE / "fake_stt.py")
    env["VOXLOG_LLM_CMD"] = "%s %s" % (sys.executable, HERE / "fake_llm.py")
    env.pop("VOXLOG_TOKEN", None)
    cmd = [sys.executable, str(ROOT / "serve.py"), "--host", "127.0.0.1", "--port", str(port),
           "--data", str(data_dir)]
    if token:
        cmd += ["--token", token]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1).read()
            break
        except urllib.error.HTTPError:
            break  # 토큰 서버는 401 - 떠 있다는 뜻
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError("서버가 바로 종료됨")
            time.sleep(0.1)
    return proc, base


def stop_server(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def api_get(base, path, token=None):
    req = urllib.request.Request(base + path)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))


def wait_for(fn, timeout, step=0.2, pg=None):
    """fn 이 참이 될 때까지 폴링. fn 이 파이썬 값만 보고(route 처리기가 채우는 값 등) route 가 걸린
    페이지가 있으면 pg 를 넘길 것 - 동기 Playwright 는 Playwright 호출 중에만 처리기를 돌린다."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = fn()
            if last:
                return last
        except Exception as exc:  # noqa: BLE001 - 폴링 중 일시 오류는 무시
            last = None
            _ = exc
        if pg is not None:
            pg.wait_for_timeout(int(step * 1000))
        else:
            time.sleep(step)
    return False


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print("통과  %s" % name, flush=True)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        RESULTS.append((name, False, msg))
        print("실패  %s - %s" % (name, msg), flush=True)


def need(cond, msg):
    if not cond:
        raise AssertionError(msg)


def queue_n(page):
    return page.evaluate("window.VoxQueue.pending().then(a => a.length)")


def rec_cycle(page, seconds=2):
    page.click("#rec")
    need(wait_for(lambda: page.get_attribute("#rec", "aria-pressed") == "true", 5), "녹음이 켜지지 않음")
    time.sleep(seconds)
    page.click("#rec")
    need(wait_for(lambda: page.get_attribute("#rec", "aria-pressed") == "false", 5), "녹음이 꺼지지 않음")


def list_count(page):
    return page.locator("#list .rec-item").count()


def open_tab(page, name):
    page.click("#tabbtn-" + name)


def overlap(a, b):
    return not (a["x"] + a["width"] <= b["x"] + 0.5 or b["x"] + b["width"] <= a["x"] + 0.5 or
                a["y"] + a["height"] <= b["y"] + 0.5 or b["y"] + b["height"] <= a["y"] + 0.5)


def main():
    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp(prefix="voxlog-e2e-"))
    procs = []
    try:
        data = tmp / "data"
        proc, base = start_server(data)
        procs.append(proc)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=[
                "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
            try:
                run_all(browser, base, data, tmp, procs)
            finally:
                browser.close()
    finally:
        for p in procs:
            stop_server(p)
        shutil.rmtree(tmp, ignore_errors=True)

    ok = sum(1 for _, p, _ in RESULTS if p)
    bad = [(n, m) for n, p, m in RESULTS if not p]
    for n, m in bad:
        print("실패한 항목: %s - %s" % (n, m))
    print("%d/%d 통과" % (ok, len(RESULTS)))
    return 0 if not bad else 1


def run_all(browser, base, data, tmp, procs):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, permissions=["microphone"])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/")
    page.wait_for_selector("#rec")

    def t1():
        need(wait_for(lambda: page.evaluate(
            "navigator.serviceWorker.getRegistration().then(r => !!(r && r.active))"), 10),
            "서비스 워커가 활성화되지 않음")
    check("1 서비스 워커 등록·활성화", t1)

    def t2():
        need(page.is_enabled("#rec"), "#rec 가 꺼져 있음(지원 안 됨 안내?)")
        rec_cycle(page)
        need(wait_for(lambda: queue_n(page) == 0, 15), "대기 수가 0 으로 돌아오지 않음")
        open_tab(page, "list")
        need(wait_for(lambda: list_count(page) == 1, 10), "기록 목록 항목 수 %d (기대 1)" % list_count(page))
    check("2 녹음→대기 0→목록 1개", t2)

    def t3():
        need(wait_for(lambda: page.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20),
             "상태가 '완료' 가 되지 않음: " + page.locator("#list .rec-item .status").first.inner_text())
        page.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: "가짜 받아쓰기" in page.inner_text("#transcript"), 10), "글에 '가짜 받아쓰기' 없음")
        need(page.is_visible("#transcript"), "#transcript 가 보이지 않음")
    check("3 상태 '완료' + 상세 글", t3)

    def t4():
        files = list(data.glob("transcripts/*/*.txt"))
        need(len(files) == 1, "txt %d개 (기대 1)" % len(files))
    check("4 서버 transcripts txt 1개", t4)

    def t5():
        ctx.set_offline(True)
        open_tab(page, "rec")
        rec_cycle(page)
        need(wait_for(lambda: page.is_visible("#queue-count"), 5), "#queue-count 가 보이지 않음")
        need(wait_for(lambda: queue_n(page) == 1, 5), "대기 수 %s (기대 1)" % queue_n(page))
        txt = page.inner_text("#queue-count")
        need("1" in txt, "대기 표시 글에 1 이 없음: " + txt)
        ctx.set_offline(False)
        need(wait_for(lambda: queue_n(page) == 0, 30), "온라인 뒤 30초 안에 대기 0 이 되지 않음")
        open_tab(page, "list")
        need(wait_for(lambda: list_count(page) == 2, 15), "목록 %d개 (기대 2)" % list_count(page))
    check("5 오프라인 대기열→복구 후 업로드", t5)

    def t6():
        time.sleep(2)
        items = api_get(base, "/api/recordings?limit=50")["items"]
        need(len(items) == 2, "서버 목록 %d개 (기대 2)" % len(items))
    check("6 중복 업로드 없음", t6)

    def t7():
        open_tab(page, "ask")
        page.select_option("#ask-scope", "today")
        page.select_option("#ask-kind", "summary")
        page.click("#ask-go")
        need(wait_for(lambda: "가짜 답" in page.inner_text("#answer"), 20), "#answer 에 '가짜 답' 없음: " +
             page.inner_text("#answer")[:80] + " / " + page.inner_text("#answer-status")[:80])
        need(page.is_visible("#answer"), "#answer 가 보이지 않음")
        # 답은 마크다운으로 그려진다
        n = lambda sel: page.locator("#answer " + sel).count()
        need(page.inner_text("#answer h4") == "요약", "제목이 h4 로 그려지지 않음")
        need(n("ul > li") >= 2 and n("ul > li > ul > li") == 1, "글머리 목록·겹친 목록이 아님")
        need(n("ol > li") == 2, "번호 목록이 아님")
        need(page.inner_text("#answer strong") == "굵은" and page.inner_text("#answer li code") == "코드", "굵게·코드가 아님")
        a = page.locator("#answer a")
        need(a.get_attribute("href") == "https://example.org/a" and "noopener" in a.get_attribute("rel"), "링크가 아님")
        need(n("table th") == 2 and n("table td") == 2, "표가 아님")
        need(page.inner_text("#answer td >> nth=1") == "<b>나</b>" and n("td b") == 0, "표 안 HTML 이 글자로 남지 않음")
        need(page.inner_text("#answer blockquote").strip() == "인용", "인용이 아님")
        need(page.inner_text("#answer pre code") == "code *그대로*" and n("pre em") == 0, "코드 블록 안이 그대로가 아님")
        need(n("img") == 0 and "onerror" in page.inner_text("#answer") and page.title() != "XSS", "답의 HTML 이 실행됨")
        need("**" not in page.inner_text("#answer") and "##" not in page.inner_text("#answer"), "마크다운 표시가 그대로 보임")
    check("7 묻기(오늘·요약) 답", t7)

    def t8():
        p2 = ctx.new_page()
        p2.goto(base + "/?action=toggle")
        need(wait_for(lambda: p2.get_attribute("#rec", "aria-pressed") == "true", 8), "?action=toggle 로 녹음이 켜지지 않음")
        time.sleep(1)
        p2.click("#rec")
        need(wait_for(lambda: p2.get_attribute("#rec", "aria-pressed") == "false", 5), "다시 눌러도 꺼지지 않음")
        time.sleep(0.5)
        p2.close()
    check("8 ?action=toggle 켜짐·다시 누르면 꺼짐", t8)

    ctx.close()

    def t9():
        long_word = "가" * 300
        bad = []
        for w in (320, 390, 1280):
            c = browser.new_context(viewport={"width": w, "height": 800}, permissions=["microphone"])
            pg = c.new_page()

            def fake_list(route, _req=None, _lw=long_word):
                item = {"id": "r-20261116-000000-abcd", "status": "done", "recorded_at": "2026-11-16T00:00:00",
                        "created": "2026-11-16T00:00:00", "duration_ms": 1000, "title": _lw, "snippet": _lw,
                        "chars": 300}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"items": [item], "stats": {"count": 1, "chars": 300, "by_date": {}}}))

            def fake_one(route, _req=None, _lw=long_word):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"id": "r-20261116-000000-abcd", "status": "done", "title": _lw, "transcript": _lw,
                     "chars": 300, "recorded_at": "2026-11-16T00:00:00", "duration_ms": 1000}))
            pg.route("**/api/recordings?*", fake_list)
            pg.route("**/api/recordings/r-*", fake_one)
            pg.goto(base + "/")
            pg.wait_for_selector("#rec")

            def overflow(tag):
                sw, cw = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                if sw > cw + 1:
                    bad.append("%dpx %s: 가로 넘침 %d>%d" % (w, tag, sw, cw))

            def no_overlap(tag):
                boxes = []
                for sel in ("#rec", "#tabbtn-rec", "#tabbtn-list", "#tabbtn-ask"):
                    if pg.locator(sel).is_visible():
                        boxes.append((sel, pg.locator(sel).bounding_box()))
                for i in range(len(boxes)):
                    for j in range(i + 1, len(boxes)):
                        if boxes[i][1] and boxes[j][1] and overlap(boxes[i][1], boxes[j][1]):
                            bad.append("%dpx %s: %s 와 %s 겹침" % (w, tag, boxes[i][0], boxes[j][0]))

            overflow("녹음 탭"); no_overlap("녹음 탭")
            open_tab(pg, "list")
            pg.wait_for_selector("#list .rec-item")
            pg.locator("#list .rec-item .rec-main").first.click()
            wait_for(lambda: pg.inner_text("#transcript").startswith("가"), 5)
            overflow("기록 탭(긴 글)"); no_overlap("기록 탭(긴 글)")
            pg.fill("#search", long_word)
            time.sleep(0.6)
            overflow("검색 입력(긴 글)")
            open_tab(pg, "ask")
            pg.fill("#ask-prompt", long_word)
            overflow("묻기 탭"); no_overlap("묻기 탭")
            open_tab(pg, "rec")
            pg.click("#settings-btn")
            pg.fill("#token", "a" * 300)
            overflow("설정"); no_overlap("설정")
            c.close()
        need(not bad, "; ".join(bad[:4]))
    check("9 폭 320·390·1280 넘침·겹침 없음", t9)

    def t10():
        c = browser.new_context(viewport={"width": 390, "height": 800}, color_scheme="dark")
        pg = c.new_page()
        pg.goto(base + "/")
        pg.wait_for_selector("#rec")
        bg, fg = pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.body).color]")
        c.close()
        need(bg != fg, "배경과 글자색이 같음 %s" % bg)
        need(bg != "rgb(245, 246, 248)", "어두운 모드인데 밝은 배경 %s" % bg)
    check("10 어두운 모드 색 다름", t10)

    def t11():
        d2 = tmp / "data2"
        proc2, base2 = start_server(d2, token="t1")
        procs.append(proc2)
        req = urllib.request.Request(base2 + "/api/recordings", data=b"RIFF" + b"\0" * 64, method="POST")
        req.add_header("Content-Type", "audio/wav")
        req.add_header("Authorization", "Bearer t1")
        urllib.request.urlopen(req, timeout=5).read()
        c = browser.new_context(viewport={"width": 390, "height": 800}, permissions=["microphone"])
        pg = c.new_page()
        pg.goto(base2 + "/")
        pg.wait_for_selector("#rec")
        pg.click("#settings-btn")
        pg.click("#health-check")
        need(wait_for(lambda: "토큰을 넣어야 합니다" in pg.inner_text("#health-out"), 8),
             "토큰 없이 '연결 확인' 이 토큰을 넣으라고 하지 않음: " + pg.inner_text("#health-out"))
        need("인증 필요" in pg.inner_text("#conn"), "토큰 없이 '연결 확인' 뒤 연결 표시가 '인증 필요' 가 아님: " + pg.inner_text("#conn"))
        pg.fill("#token", "wrong")
        pg.dispatch_event("#token", "change")
        pg.click("#health-check")
        need(wait_for(lambda: "토큰이 틀립니다" in pg.inner_text("#health-out"), 8),
             "틀린 토큰으로 '연결 확인' 이 틀렸다고 하지 않음: " + pg.inner_text("#health-out"))
        pg.fill("#token", "t1")
        pg.dispatch_event("#token", "change")
        pg.click("#health-check")
        need(wait_for(lambda: "인증: 통과" in pg.inner_text("#health-out"), 8),
             "맞는 토큰으로 '연결 확인' 이 통과라고 하지 않음: " + pg.inner_text("#health-out"))
        pg.fill("#token", "")
        pg.dispatch_event("#token", "change")
        open_tab(pg, "list")
        need(wait_for(lambda: "인증 필요" in pg.inner_text("#conn"), 8), "목록에서 '인증 필요' 안내가 없음: " + pg.inner_text("#conn"))
        need(wait_for(lambda: pg.is_visible("#toast") and pg.inner_text("#toast").strip(), 5), "오류 토스트가 보이지 않음")
        need(list_count(pg) == 0, "토큰 없이 목록이 읽힘")
        pg.click("#settings-btn") if not pg.is_visible("#token") else None
        pg.fill("#token", "t1")
        time.sleep(0.5)
        open_tab(pg, "rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10), "토큰을 넣어도 목록이 읽히지 않음 (%d)" % list_count(pg))
        c.close()
    check("11 토큰 서버: 없이 오류·넣으면 목록", t11)

    def new_server(name, **kw):
        pr, b = start_server(tmp / name, **kw)
        procs.append(pr)
        return b, tmp / name

    def new_ctx(**kw):
        kw.setdefault("viewport", {"width": 390, "height": 844})
        kw.setdefault("permissions", ["microphone"])
        return browser.new_context(**kw)

    def server_items(b):
        return api_get(b, "/api/recordings?limit=50")["items"]

    def t12():
        b, _ = new_server("d12")
        c = new_ctx()
        c.add_init_script("Object.defineProperty(window, 'launchQueue', "
                          "{configurable: true, value: {setConsumer(f){window.__lq = f}}})")
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        need(wait_for(lambda: pg.evaluate("typeof window.__lq === 'function'"), 5), "launchQueue 소비자가 등록되지 않음")
        pg.click("#settings-btn")
        pg.check("#auto-record")
        time.sleep(0.5)
        url = b + "/?source=launch"
        pg.evaluate("u => window.__lq({targetURL: u})", url)
        need(wait_for(lambda: pg.get_attribute("#rec", "aria-pressed") == "true", 8), "launchQueue 신호로 녹음이 켜지지 않음")
        time.sleep(1.5)
        pg.evaluate("u => window.__lq({targetURL: u})", url)
        need(wait_for(lambda: pg.get_attribute("#rec", "aria-pressed") == "false", 8), "launchQueue 두 번째 신호로 꺼지지 않음")
        time.sleep(1)
        # 같은 출처의 새 페이지를 ?source=launch 로 열고 첫 신호를 3초 안에 두 번 보낸다 → 녹음은 한 번만 켜져야 함
        p2 = c.new_page()
        p2.goto(url)
        p2.wait_for_selector("#rec")
        need(wait_for(lambda: p2.get_attribute("#rec", "aria-pressed") == "true", 8), "?source=launch 로 녹음이 켜지지 않음")
        p2.evaluate("u => { window.__lq({targetURL: u}); window.__lq({targetURL: u}); }", url)
        time.sleep(1.5)
        need(p2.get_attribute("#rec", "aria-pressed") == "true", "열린 직후 같은 신호 두 번에 녹음이 꺼짐(한 번만 켜져야 함)")
        c.close()
    check("12 launchQueue 자동 녹음 켜짐·다시 부르면 꺼짐", t12)

    def t13():
        cmd = "%s -c %s" % (sys.executable, shlex.quote("print('<img src=x onerror=window.__x=1>')"))
        b, _ = new_server("d13", stt_cmd=cmd)
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 15), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20), "받아쓰기가 끝나지 않음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: "<img" in pg.inner_text("#transcript"), 10), "상세 글에 태그 글자가 그대로 보이지 않음")
        open_tab(pg, "rec")
        open_tab(pg, "list")
        time.sleep(0.5)
        need(pg.locator("#list img").count() == 0, "목록에 img 요소가 생김")
        need(pg.locator("#detail img").count() == 0, "상세에 img 요소가 생김")
        need(pg.evaluate("window.__x === undefined"), "XSS 가 실행됨(window.__x)")
        c.close()
    check("13 XSS: 받아쓰기 글의 태그는 글자로만", t13)

    def t14():
        from datetime import datetime
        from zoneinfo import ZoneInfo
        b, d = new_server("d14")
        c = new_ctx(timezone_id="Pacific/Honolulu")
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        need(wait_for(lambda: len(server_items(b)) == 1, 15, pg=pg), "올라가지 않음")   # 대기 0 은 넣기 전에도 참
        today = datetime.now(ZoneInfo("Pacific/Honolulu")).strftime("%Y-%m-%d")
        it = server_items(b)[0]
        need(it["recorded_at"].endswith("-10:00"), "recorded_at 이 -10:00 으로 끝나지 않음: " + it["recorded_at"])
        need(it["recorded_at"][:10] == today, "recorded_at 날짜 %s (기대 %s)" % (it["recorded_at"][:10], today))
        need(wait_for(lambda: (d / "transcripts" / today).is_dir(), 15), "transcripts/%s 폴더가 없음: %s" % (
            today, [x.name for x in (d / "transcripts").glob("*")] if (d / "transcripts").exists() else "없음"))
        open_tab(pg, "list")
        need(wait_for(lambda: pg.inner_text("#stat-today").strip() == "1", 10), "stat 오늘 %s (기대 1)" % pg.inner_text("#stat-today"))
        c.close()
    check("14 시간대 Honolulu: -10:00·지역 날짜 폴더·오늘 1", t14)

    def t15():
        b, _ = new_server("d15")
        c = new_ctx(service_workers="block")
        pg = c.new_page()

        def too_big(route):
            if route.request.method == "POST":
                route.fulfill(status=413, content_type="application/json", body=json.dumps({"error": "너무 큼"}))
            else:
                route.continue_()
        pg.route("**/api/recordings", too_big)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        need(wait_for(lambda: pg.locator("#failed-list .failed-item").count() == 1, 15), "'올리지 못한 녹음' 칸에 1 줄이 보이지 않음")
        need(pg.is_visible("#failed-box"), "#failed-box 가 숨겨져 있음")
        need(not pg.is_visible("#queue-count"), "대기 수가 보임: " + pg.inner_text("#queue-count"))
        need("너무 큼" in pg.inner_text("#failed-list"), "까닭이 보이지 않음: " + pg.inner_text("#failed-list"))
        pg.once("dialog", lambda dlg: dlg.accept())
        pg.click("#failed-list .f-remove")
        need(wait_for(lambda: pg.locator("#failed-list .failed-item").count() == 0, 10), "지우기 뒤에도 줄이 남음")
        need(queue_n(pg) == 0, "대기열에 남음")
        c.close()
    check("15 413 → 실패 칸 1줄·대기 0·지우기", t15)

    def t16():
        b, _ = new_server("d16")
        c = new_ctx(geolocation={"latitude": 35.1796, "longitude": 129.0756, "accuracy": 15},
                    permissions=["microphone", "geolocation"])
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.click("#rec")
        need(wait_for(lambda: pg.get_attribute("#rec", "aria-pressed") == "true", 5), "녹음이 켜지지 않음")
        time.sleep(6.5)
        pg.reload()
        pg.wait_for_selector("#rec")
        need(wait_for(lambda: len(server_items(b)) == 1, 30), "리로드 뒤 30초 안에 서버에 녹음이 올라오지 않음")
        need(wait_for(lambda: queue_n(pg) == 0, 10), "대기열이 비지 않음")
        loc = server_items(b)[0].get("location")
        need(loc and abs(loc["lat"] - 35.1796) < 0.01 and abs(loc["lon"] - 129.0756) < 0.01,
             "새로고침으로 살린 녹음에 위치가 없음: %s" % loc)
        c.close()
    check("16 녹음 중 새로고침 → 초안 살려 업로드", t16)

    def t17():
        b, _ = new_server("d17")
        c = new_ctx(geolocation={"latitude": 37.5665, "longitude": 126.978, "accuracy": 20},
                    permissions=["microphone", "geolocation"])
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        need(wait_for(lambda: len(server_items(b)) == 1, 20), "올라가지 않음")
        loc = server_items(b)[0].get("location")
        need(loc and abs(loc["lat"] - 37.5665) < 0.01 and abs(loc["lon"] - 126.978) < 0.01, "location %s" % loc)
        open_tab(pg, "list")
        need(wait_for(lambda: pg.locator("#list .rec-item .loc-pin").count() == 1, 10), "목록에 📍 표시가 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-map"), 10), "지도 링크가 보이지 않음")
        href = pg.get_attribute("#detail-map", "href")
        need("openstreetmap.org" in href and "mlat=37.5665" in href, "지도 링크 이상: " + href)
        need(pg.get_attribute("#detail-map", "rel") == "noopener" and pg.get_attribute("#detail-map", "target") == "_blank",
             "target/rel 이상")

        # 서버 응답의 location 이 이상한 글자여도 지도 링크가 위험한 주소가 되지 않음
        def evil(route):
            resp = route.fetch()
            body = resp.json()
            body["location"] = {"lat": "javascript:alert(1)", "lon": "javascript:alert(2)", "accuracy": 5}
            route.fulfill(response=resp, body=json.dumps(body), content_type="application/json")
        pg.route("**/api/recordings/r-*", evil)
        pg.locator("#list .rec-item .rec-main").first.click()
        # 조작된 값(숫자 아님)이면 링크가 숨거나, 남더라도 href 에 위험한 글자가 없어야 한다
        need(wait_for(lambda: pg.locator("#detail-map").count() == 0 or pg.is_hidden("#detail-loc"), 8)
             or "javascript" not in (pg.locator("#detail-map").first.get_attribute("href", timeout=2000) or "").lower(),
             "조작된 location 으로 지도 링크가 위험함")
        need(pg.locator("#detail-map[href*='javascript' i]").count() == 0, "href 에 javascript 가 들어감")
        pg.unroute("**/api/recordings/r-*", evil)
        time.sleep(0.3)
        c.close()
        b2, _ = new_server("d17b")
        c2 = new_ctx(permissions=["microphone"])
        p2 = c2.new_page()
        p2.goto(b2 + "/")
        p2.wait_for_selector("#rec")
        rec_cycle(p2)
        need(wait_for(lambda: len(server_items(b2)) == 1, 30), "위치 권한 없이 녹음이 올라가지 않음")
        need(server_items(b2)[0].get("location") is None, "위치 권한이 없는데 location 이 있음")
        c2.close()
    check("17 위치: 서버 meta·지도 링크 / 권한 없으면 None", t17)

    def t18():
        b, _ = new_server("d18")
        c = new_ctx(geolocation={"latitude": 36.35, "longitude": 127.38, "accuracy": 10},
                    permissions=["microphone", "geolocation"])
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        for i in range(2):  # 멈춤 직후 바로 다시 시작
            pg.click("#rec")
            need(wait_for(lambda: pg.get_attribute("#rec", "aria-pressed") == "true", 5), "녹음 %d 가 켜지지 않음" % (i + 1))
            time.sleep(1.5)
            pg.click("#rec")
            need(wait_for(lambda: pg.get_attribute("#rec", "aria-pressed") == "false", 5), "녹음 %d 가 꺼지지 않음" % (i + 1))
        need(wait_for(lambda: len(server_items(b)) >= 2, 30), "서버 목록이 2건이 되지 않음: %d" % len(server_items(b)))
        time.sleep(3)
        need(len(server_items(b)) == 2, "서버 목록 %d건 (기대 정확히 2)" % len(server_items(b)))
        need(wait_for(lambda: queue_n(pg) == 0, 10), "대기열이 비지 않음")
        for it in server_items(b):
            need(it.get("location") is not None, "녹음에 위치가 없음(섞임?)")
        pg.reload()  # draftRecover 가 돈 뒤에도 늘지 않아야 함
        pg.wait_for_selector("#rec")
        time.sleep(4)
        need(len(server_items(b)) == 2, "다시 열고 나니 서버 목록 %d건 (기대 2)" % len(server_items(b)))
        need(queue_n(pg) == 0, "다시 열고 나니 대기열이 비지 않음")
        c.close()
    check("18 연속 녹음 2건 → 서버 정확히 2건·다시 열어도 그대로", t18)

    def t19():
        b, _ = new_server("d19")
        req = urllib.request.Request(b + "/api/recordings", data=b"RIFF" + b"\0" * 64, method="POST")
        req.add_header("Content-Type", "audio/wav")
        urllib.request.urlopen(req, timeout=5).read()

        def open_detail(ctx_):
            p = ctx_.new_page()
            p.goto(b + "/")
            p.wait_for_selector("#rec")
            open_tab(p, "list")
            need(wait_for(lambda: list_count(p) == 1, 10), "목록 항목이 없음")
            p.locator("#list .rec-item .rec-main").first.click()
            need(wait_for(lambda: p.is_visible("#detail"), 5), "상세가 열리지 않음")
            time.sleep(0.8)
            return p
        c1 = new_ctx()
        p1 = open_detail(c1)
        need(p1.is_visible("#detail-delete"), "보통 출처인데 지우기 단추가 보이지 않음")
        c1.close()
        # 격리된 출처 흉내: indexedDB 에 닿으면 던지게 해서 앱이 쓰는 판정(supported().indexedDB)을 거짓으로 만든다
        c2 = new_ctx()
        c2.add_init_script("Object.defineProperty(window, 'indexedDB', {configurable: true, get() { throw new Error('denied'); }})")
        p2 = open_detail(c2)
        need(not p2.is_visible("#detail-delete"), "격리된 출처인데 상세의 지우기 단추가 보임")
        need(p2.is_disabled("#rec"), "격리된 출처인데 녹음 단추가 꺼지지 않음")
        c2.close()
    check("19 격리된 출처 흉내: 상세 지우기 단추 숨김", t19)

    def t20():
        b, _ = new_server("d20")
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.click("#settings-btn")
        need(not pg.is_visible("#api-base"), "설정에 #api-base 가 보임")
        pg.evaluate("window.VoxQueue.setConfig({apiBase: 'https://elsewhere.invalid'})")
        before = len(server_items(b))
        rec_cycle(pg)
        need(wait_for(lambda: len(server_items(b)) == before + 1, 20), "예전 apiBase 가 있는데 같은 출처로 올라가지 않음")
        need(wait_for(lambda: queue_n(pg) == 0, 10), "대기열이 비지 않음")
        c.close()
    check("20 서버 주소 설정 없음·저장된 apiBase 무시(같은 출처)", t20)

    def t21():
        b, _ = new_server("d21")
        c = new_ctx(service_workers="block")
        pg = c.new_page()
        hits = {"n": 0}

        def busy(route):
            if route.request.method == "POST" and hits["n"] == 0:
                hits["n"] += 1
                route.fulfill(status=503, headers={"Retry-After": "1"}, content_type="application/json",
                              body=json.dumps({"error": "동시 업로드 자리 없음"}))
            else:
                route.continue_()
        pg.route("**/api/recordings", busy)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        before = len(server_items(b))
        rec_cycle(pg)
        need(wait_for(lambda: hits["n"] == 1, 15, pg=pg), "503 이 돌려지지 않음")
        pg.wait_for_timeout(300)
        need(queue_n(pg) == 1, "503 뒤 대기열 %d (기대 1)" % queue_n(pg))
        need(pg.evaluate("window.VoxQueue.pending().then(a => a[0].state)") == "waiting", "503 이 영구 실패 상태로 감")
        need("서버가 받지 않았습니다" not in pg.inner_text("#failed-list"), "503 이 영구 실패 문구로 보임")
        need(len(server_items(b)) == before, "503 인데 서버에 올라감")
        # 직접 flush 하지 않음 - queue.js 가 Retry-After(1초) 뒤 스스로 다시 올려야 함(R34-N5)
        need(wait_for(lambda: len(server_items(b)) == before + 1, 15, pg=pg), "Retry-After 뒤 재시도로 올라가지 않음")
        need(wait_for(lambda: queue_n(pg) == 0, 10), "대기열이 비지 않음")
        c.close()
    check("21 업로드 503 → 대기열에 남고 다음 시도에 올라감", t21)

    def t22():
        # 실제 서버가 내는 503(업로드 자리 2개 모두 사용 중) - route.fulfill 가짜가 아님(R34-N4)
        token = "t22"
        pr, b = start_server(tmp / "d22", token=token)
        procs.append(pr)
        port = int(b.rsplit(":", 1)[1])
        socks = []
        c = None
        try:
            for _ in range(2):
                s = socket.create_connection(("127.0.0.1", port), timeout=5)
                head = ("POST /api/recordings HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                        "Content-Type: audio/webm\r\nContent-Length: 5000000\r\n"
                        "Authorization: Bearer %s\r\nX-Client-Id: hold-%d\r\n\r\n" % (port, token, len(socks)))
                s.sendall(head.encode("ascii") + b"\0" * 1024)
                socks.append(s)
            time.sleep(1.0)  # 서버가 두 자리를 잡을 시간
            c = new_ctx(service_workers="block")
            pg = c.new_page()
            seen = {}

            def on_resp(r):
                if r.request.method == "POST" and r.url.endswith("/api/recordings"):
                    seen["status"] = r.status
                    seen["retry"] = r.headers.get("retry-after")

            def on_fail(r):
                if r.method == "POST" and r.url.endswith("/api/recordings"):
                    seen["failed"] = r.failure
            pg.on("response", on_resp)
            pg.on("requestfailed", on_fail)
            pg.goto(b + "/")
            pg.wait_for_selector("#rec")
            pg.evaluate("t => window.VoxQueue.setConfig({token: t})", token)
            rec_cycle(pg)
            need(wait_for(lambda: pg.evaluate(
                "window.VoxQueue.pending().then(a => a.length === 1 && !!a[0].lastError)"), 15, pg=pg),
                "대기열 줄에 lastError 가 생기지 않음")
            row = pg.evaluate("window.VoxQueue.pending().then(a => a[0])")
            if "status" in seen:
                got = "503 문구 수신(status %s, Retry-After %s)" % (seen["status"], seen.get("retry"))
            else:
                got = "연결 실패(%s)" % seen.get("failed")
            print("    22 페이지가 받은 것: %s · lastError=%r" % (got, row.get("lastError")), flush=True)
            need(row["state"] == "waiting", "대기열 줄 state=%s (waiting 이어야 함)" % row["state"])
            need(len(api_get(b, "/api/recordings?limit=50", token)["items"]) == 0, "자리가 없는데 서버 기록이 생김")
            for s in socks:
                s.close()
            socks = []
            # Retry-After(5초) 뒤 스스로 다시 올림. 안 되면 flush 로 재촉
            def uploaded():
                return len(api_get(b, "/api/recordings?limit=50", token)["items"]) == 1
            if not wait_for(uploaded, 10, pg=pg):
                pg.evaluate("window.VoxQueue.flush().catch(() => null)")
                need(wait_for(uploaded, 15, pg=pg), "소켓을 닫은 뒤에도 서버 기록이 1건이 되지 않음")
            need(wait_for(lambda: queue_n(pg) == 0, 10, pg=pg), "올라간 뒤 대기열이 비지 않음")
            need(len(api_get(b, "/api/recordings?limit=50", token)["items"]) == 1, "서버 기록이 1건이 아님")
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
            if c:
                c.close()
            stop_server(pr)
    check("22 실제 서버 503(업로드 자리 가득) → 대기열 waiting·소켓 닫으면 올라감", t22)

    def t23():
        # 서버를 아예 내린 뒤(폰의 '연결 없음') 앱을 다시 연다 - 껍데기는 서비스 워커 캐시에서 나와야 함
        pr, b = start_server(tmp / "d23")
        procs.append(pr)
        c = new_ctx()
        try:
            pg = c.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(b + "/")
            pg.wait_for_selector("#rec")
            need(wait_for(lambda: pg.evaluate("!!navigator.serviceWorker.controller"), 10, pg=pg),
                 "서비스 워커가 페이지를 맡지 않음")
            shell = pg.evaluate("caches.keys().then(ks => caches.open(ks.filter(k => k.indexOf('voxlog-shell-') === 0)[0]))"
                                ".then(c => c.keys()).then(rs => rs.map(r => new URL(r.url).pathname))")
            for f in ("/index.html", "/style.css", "/app.js", "/api.js", "/md.js", "/queue.js",
                      "/manifest.webmanifest", "/icons/icon-192.png"):
                need(f in shell, "캐시에 %s 가 없음: %s" % (f, shell))
            stop_server(pr)
            pg.goto(b + "/")                       # 서버 없음 - 캐시로만 열려야 함
            pg.wait_for_selector("#rec", timeout=10000)
            need(pg.is_visible("#rec"), "서버가 없을 때 녹음 단추가 보이지 않음")
            need(pg.evaluate("typeof window.VoxQueue === 'object' && typeof window.VoxMd === 'object'"),
                 "서버가 없을 때 스크립트가 다 실리지 않음")
            need(pg.evaluate("getComputedStyle(document.body).margin") == "0px" or
                 pg.evaluate("document.styleSheets.length") >= 1, "서버가 없을 때 스타일이 실리지 않음")
            need(pg.evaluate("!!navigator.serviceWorker.controller"), "다시 연 페이지를 서비스 워커가 맡지 않음")
            pg.goto(b + "/?action=toggle")         # 바로가기 주소로도 열림(검색어 무시) - 녹음이 저절로 켜짐
            pg.wait_for_selector("#rec", timeout=10000)
            need(wait_for(lambda: pg.get_attribute("#rec", "aria-pressed") == "true", 8, pg=pg),
                 "서버 없이 ?action=toggle 로 열었을 때 녹음이 켜지지 않음")
            time.sleep(2)
            pg.click("#rec")                       # 연결 없이 녹음을 멈춤 → 대기열에 남음
            need(wait_for(lambda: queue_n(pg) >= 1, 10, pg=pg), "서버 없이 녹음한 것이 대기열에 없음")
            need(not errs, "페이지 오류: %s" % errs[:2])
        finally:
            c.close()
            stop_server(pr)
    check("23 PWA 오프라인: 서버를 내려도 앱이 열리고 녹음이 대기열에 남음", t23)

    def t24():
        # 408(업로드 너무 느림)도 영구 실패가 아님 - waiting 으로 남고 Retry-After 뒤 저절로 다시 올라감(R35-N2)
        b, _ = new_server("d24")
        c = new_ctx(service_workers="block")
        pg = c.new_page()
        hits = {"n": 0}

        def slow(route):
            if route.request.method == "POST" and hits["n"] == 0:
                hits["n"] += 1
                route.fulfill(status=408, headers={"Retry-After": "1"}, content_type="application/json",
                              body=json.dumps({"error": "업로드가 너무 느립니다"}))
            else:
                route.continue_()
        pg.route("**/api/recordings", slow)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        before = len(server_items(b))
        rec_cycle(pg)
        need(wait_for(lambda: hits["n"] == 1, 15, pg=pg), "408 이 돌려지지 않음")
        pg.wait_for_timeout(300)
        need(queue_n(pg) == 1, "408 뒤 대기열 %d (기대 1)" % queue_n(pg))
        need(pg.evaluate("window.VoxQueue.pending().then(a => a[0].state)") == "waiting", "408 이 영구 실패 상태로 감")
        need(pg.evaluate("window.VoxQueue.pending().then(a => a[0].lastError)") == "업로드가 너무 느립니다",
             "408 의 lastError 가 서버 문구가 아님")
        need("서버가 받지 않았습니다" not in pg.inner_text("#failed-list"), "408 이 영구 실패 문구로 보임")
        need(len(server_items(b)) == before, "408 인데 서버에 올라감")
        # 다른 신호 없이 Retry-After(1초) 뒤 스스로 다시 올라가야 함
        need(wait_for(lambda: len(server_items(b)) == before + 1, 15, pg=pg), "Retry-After 뒤 408 줄이 다시 올라가지 않음")
        need(wait_for(lambda: queue_n(pg) == 0, 10, pg=pg), "대기열이 비지 않음")
        need(len(server_items(b)) == before + 1, "서버 기록이 1건이 아님")
        c.close()
    check("24 업로드 408 → waiting 으로 남고 Retry-After 뒤 저절로 올라감", t24)


if __name__ == "__main__":
    sys.exit(main())
