#!/usr/bin/env python3
"""VoxLog 끝에서 끝 브라우저 검사 (크롬만, 파이썬 Playwright).

실행: python3 projects/VoxLog/tests/browser_voxlog.py
      python3 projects/VoxLog/tests/browser_voxlog.py --only 67,75-78
      python3 projects/VoxLog/tests/browser_voxlog.py --match "기본값 읽기"
서버는 이 검사가 임시 data 폴더로 직접 띄우고(subprocess) 끝나면 내린다.
검사는 모두 77개입니다.

`--only` 는 번호를 쉼표 목록·`a-b` 닫힌 범위로 받고(예: `--only 67,75-78`) 여러 번 줄 수
있습니다. `--match` 는 검사 이름에 들어 있는 글을 받고 여러 번 줄 수 있습니다(대소문자 그대로).
둘 다 주면 합집합이고, 인자가 없으면 지금처럼 전체를 돕니다.
앞 검사의 상태(같은 page·ctx·서버 자료 수)에 기대는 검사는 그 앞 검사까지 함께 돌립니다
(예: `--only 3` 은 2 까지, `--only 7` 은 2·3 까지). 그래서 검사 하나만 골라도 1분 안에 돕니다.

끝줄은 전체 실행이면 `N/M 통과`, 일부 실행이면
`부분 실행: n/77 돌림 · m 건너뜀 · p/n 통과 (전체 통과 아님)` 입니다 - 일부 실행은 전체
통과가 아닙니다. 실패가 있거나 고른 검사가 하나도 없으면(그때는 끝줄 앞에
`고른 검사가 없습니다`) 종료 코드 1, 돌린 검사가 있고 실패가 없으면 0.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = []  # (이름, 통과, 까닭)
SELECTION = None  # None 이면 전체, set[int] 이면 고른 번호만
SKIPPED = 0  # 고르지 않아 부르지 않은 검사 수

# 앞 검사의 상태(같은 page·ctx·서버 자료 수)에 기대는 검사 → 먼저 돌아야 할 번호들.
# t2 만든 녹음·t3 연 상세·t5 더한 녹음이 뒤 검사의 '목록/서버 자료 수' 를 이룬다.
NEEDS = {
    3: (2,),      # 목록 1개의 '완료' 상태 + 그 상세 글
    4: (3,),      # transcripts txt 1개 - 받아쓰기가 끝나야 생기므로 t3 의 '완료' 기다림이 필요
    5: (2,),      # 목록 2개 = t2 의 1개 + 새 1개
    6: (2, 5),    # 서버 목록 2개 = t2·t5 의 두 건
    7: (3,),      # '받아 적은 글이 있는 녹취' 가 있어야 묻기가 400 이 아님
}


def test_number(name):
    """검사 이름 맨 앞 번호."""
    m = re.match(r"\s*(\d+)", name)
    if not m:
        raise ValueError("검사 이름에 번호가 없습니다: %r" % name)
    return int(m.group(1))


def _parse_only(value):
    """`67,75-78` 같은 --only 값을 번호 집합으로. 틀린 값은 argparse 오류."""
    nums = set()
    for part in value.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise argparse.ArgumentTypeError("잘못된 --only 값: %r" % part)
        start = int(m.group(1))
        if m.group(2) is None:
            nums.add(start)
            continue
        end = int(m.group(2))
        if end < start:
            raise argparse.ArgumentTypeError("잘못된 --only 범위: %r" % part)
        nums.update(range(start, end + 1))
    return nums


def parse_selection(argv):
    """명령줄 인자 → (only: set[int] | None, match: list[str])"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--only", action="append", type=_parse_only, default=None)
    parser.add_argument("--match", action="append", default=None)
    ns = parser.parse_args(argv)
    only = None
    if ns.only:
        only = set()
        for group in ns.only:
            only |= group
    return only, list(ns.match or [])


def expand_needs(selected, needs=NEEDS):
    """기대는 번호를 거듭 따라가 모두 더한 집합(고리가 있어도 끝난다)."""
    out = set(selected)
    todo = list(selected)
    while todo:
        for dep in needs.get(todo.pop(), ()):
            if dep not in out:
                out.add(dep)
                todo.append(dep)
    return out


def summary_line(ran, total, passed, skipped):
    """전체 실행이면 `N/M 통과`, 일부 실행이면 `부분 실행: … (전체 통과 아님)`."""
    if skipped == 0:
        return "%d/%d 통과" % (passed, total)
    return "부분 실행: %d/%d 돌림 · %d 건너뜀 · %d/%d 통과 (전체 통과 아님)" % (
        ran, total, skipped, passed, ran)


def exit_code(ran, failed):
    """돌린 검사가 1개 이상이고 실패가 0 이면 0, 아니면 1."""
    return 0 if (ran > 0 and failed == 0) else 1


def _known_names():
    """--match 를 번호로 풀려고 이 파일의 check("N 이름", ...) 줄에서 이름을 모은다."""
    try:
        src = Path(__file__).read_text(encoding="utf-8")
    except OSError:
        return {}
    return {int(num): rest for num, rest in re.findall(r'^\s*check\("(\d+)\s+([^"]*)"', src, re.M)}


def resolve_selection(only, match):
    """--only·--match 를 번호 집합으로 풀고 NEEDS 로 넓힌다. 인자가 없으면 None(전체)."""
    if only is None and not match:
        return None
    chosen = set(only or ())
    if match:
        for num, rest in _known_names().items():
            if any(text in "%d %s" % (num, rest) for text in match):
                chosen.add(num)
    return expand_needs(chosen)


def apply_selection(argv):
    """명령줄 인자로 SELECTION 을 정하고 돌려준다. 인자가 없으면 None(전체)."""
    global SELECTION
    only, match = parse_selection(argv)
    SELECTION = resolve_selection(only, match)
    return SELECTION


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(data_dir, token=None, stt_cmd=None, llm_cmd=None, env_extra=None):
    port = free_port()
    env = dict(os.environ)
    env["VOXLOG_STT"] = "command"
    env["VOXLOG_STT_CMD"] = stt_cmd or "%s %s {wav}" % (sys.executable, HERE / "fake_stt.py")
    env["VOXLOG_LLM_CMD"] = llm_cmd or "%s %s" % (sys.executable, HERE / "fake_llm.py")
    if env_extra:
        env.update(env_extra)
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


def api_patch(base, rid, body):
    req = urllib.request.Request(base + "/api/recordings/" + rid,
                                 data=json.dumps(body).encode("utf-8"), method="PATCH")
    req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))


def api_post_wav(base, path):
    req = urllib.request.Request(base + "/api/recordings", data=Path(path).read_bytes(), method="POST")
    req.add_header("Content-Type", "audio/wav")
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))


def api_post_json(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))


def api_put_json(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"), method="PUT")
    req.add_header("Content-Type", "application/json")
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
    global SKIPPED
    if SELECTION is not None and test_number(name) not in SELECTION:
        SKIPPED += 1
        return
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


def detail_ready(page):
    """상세의 첫 GET 이 끝나 편집 칸이 서버 값으로 채워졌는가(그 전에 타이프하면 덮어쓴다)."""
    try:
        return page.is_visible("#detail") and "불러오는 중" not in page.inner_text("#detail-meta")
    except Exception:  # noqa: BLE001 - 아직 없으면 아직 아님
        return False


def stt_fields_ready(page, prefix):
    """기본값 새로 읽기가 끝나 칸과 단추가 모두 풀렸는가."""
    fields = [prefix + "-" + k for k in ("preprocess", "speakers", "context", "auto", "review")]
    button = "#detail-stt-run" if prefix == "detail-stt" else "#stt-defaults-save"
    try:
        return (page.is_visible("#" + prefix + "-fields") and
                page.is_enabled(button) and
                all(page.is_enabled("#" + f) for f in fields))
    except Exception:  # noqa: BLE001 - 아직 없으면 아직 아님
        return False


STT_OPTIONS_HOLD_JS = """
(() => {
  const orig = window.fetch.bind(window);
  const held = [];
  let holdNext = 0;
  window.__releasedFetchCount = 0;
  window.__releasedFetchDone = false;
  window.__releasedFetchAborted = false;
  window.__heldFetchAborted = 0;
  window.__holdNextSttOptions = (n) => { holdNext = n || 1; return true; };
  window.__sttOptionsHeld = () => held.length > 0;
  window.__sttOptionsHeldCount = () => held.length;
  // 실제 fetch 처럼 - 쥔 요청의 신호가 끊기면 그 약속은 AbortError 로 거절된다.
  function settleAborted(h) {
    if (h.settled) return;
    h.settled = true;
    h.aborted = true;
    window.__heldFetchAborted += 1;
    h.reject(new DOMException('The operation was aborted.', 'AbortError'));
  }
  window.__releaseSttOptions = (index) => {
    if (!held.length) return false;
    const i = (index === undefined) ? 0 : index;
    if (i < 0 || i >= held.length) return false;
    const h = held.splice(i, 1)[0];
    window.__releasedFetchAborted = !!h.aborted;
    // 이미 끊겨 거절된 읽기 - 실제 요청은 가지 않는다. 놓은 것으로만 세고 그대로 둔다.
    if (h.settled) {
      window.__releasedFetchCount += 1;
      return true;
    }
    window.__releasedFetchDone = false;
    orig(h.input, h.init).then(function (res) {
      h.settled = true;
      window.__releasedFetchDone = true;
      window.__releasedFetchCount += 1;
      h.resolve(res);
    }, function (err) {
      h.settled = true;
      if (err && err.name === 'AbortError') {
        h.aborted = true;
        window.__heldFetchAborted += 1;
      }
      window.__releasedFetchAborted = !!h.aborted;
      h.reject(err);
    });
    return true;
  };
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const method = (init && init.method) || 'GET';
    if (holdNext > 0 && method === 'GET' && url.split('?')[0].endsWith('/api/stt-options')) {
      holdNext -= 1;
      return new Promise(function (resolve, reject) {
        const h = {input, init, resolve, reject, settled: false, aborted: false};
        held.push(h);
        const sig = init && init.signal;
        if (sig) {
          if (sig.aborted) { settleAborted(h); return; }
          sig.addEventListener('abort', function () { settleAborted(h); }, {once: true});
        }
      });
    }
    return orig(input, init);
  };
})();
"""


RETRY_HOLD_JS = """
(() => {
  const orig = window.fetch.bind(window);
  let held = null;
  let holdNext = false;
  window.__releasedRetryDone = false;
  window.__holdNextRetry = () => { holdNext = true; return true; };
  window.__retryHeld = () => !!held;
  window.__releaseRetry = () => {
    if (!held) return false;
    const h = held; held = null;
    window.__releasedRetryDone = false;
    orig(h.input, h.init).then(function (res) {
      window.__releasedRetryDone = true;
      h.resolve(res);
    }, h.reject);
    return true;
  };
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const method = (init && init.method) || 'GET';
    if (holdNext && method === 'POST' && url.split('?')[0].endsWith('/retry')) {
      holdNext = false;
      return new Promise(function (resolve, reject) { held = {input, init, resolve, reject}; });
    }
    return orig(input, init);
  };
})();
"""


STT_SAVE_HOLD_JS = """
(() => {
  const orig = window.fetch.bind(window);
  let held = null;
  let holdNext = false;
  window.__releasedSaveDone = false;
  window.__holdNextSave = () => { holdNext = true; return true; };
  window.__saveHeld = () => !!held;
  window.__releaseSave = () => {
    if (!held) return false;
    const h = held; held = null;
    window.__releasedSaveDone = false;
    orig(h.input, h.init).then(function (res) {
      window.__releasedSaveDone = true;
      h.resolve(res);
    }, h.reject);
    return true;
  };
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const method = (init && init.method) || 'GET';
    if (holdNext && method === 'PUT' && url.split('?')[0].endsWith('/api/stt-options')) {
      holdNext = false;
      return new Promise(function (resolve, reject) { held = {input, init, resolve, reject}; });
    }
    return orig(input, init);
  };
})();
"""


def open_tab(page, name):
    page.click("#tabbtn-" + name)


def overlap(a, b):
    return not (a["x"] + a["width"] <= b["x"] + 0.5 or b["x"] + b["width"] <= a["x"] + 0.5 or
                a["y"] + a["height"] <= b["y"] + 0.5 or b["y"] + b["height"] <= a["y"] + 0.5)


def main():
    apply_selection(sys.argv[1:])

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
    ran = len(RESULTS)
    total = ran + SKIPPED
    if ran == 0:
        print("고른 검사가 없습니다")
    print(summary_line(ran, total, ok, SKIPPED))
    return exit_code(ran, len(bad))


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

    def upload_rec(b, name, options=None):
        """검사용 녹음 하나를 서버에 넣고 받아쓰기가 끝날 때까지 기다린다."""
        p = tmp / (name + ".wav")
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\0\0" * 16000)
        item = api_post_wav(b, p)
        rid = item["id"]
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid).get("status") == "done", 20),
             "녹음 %s 첫 받아쓰기가 끝나지 않음: %r" %
             (name, api_get(b, "/api/recordings/" + rid).get("status")))
        if options is not None:
            api_post_json(b, "/api/recordings/" + rid + "/retry", {"options": options})
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid).get("status") == "done", 20),
             "녹음 %s 가 완료되지 않음: %r" % (name, api_get(b, "/api/recordings/" + rid).get("status")))
        return rid

    def db_drafts(pg):
        """IndexedDB 의 [초안 수, 조각 수]"""
        return pg.evaluate(
            "new Promise(function (res) { var r = indexedDB.open('voxlog', 2);"
            " r.onsuccess = function () { var db = r.result;"
            " var tx = db.transaction(['drafts', 'chunks'], 'readonly');"
            " var d = tx.objectStore('drafts').count(), c = tx.objectStore('chunks').count();"
            " tx.oncomplete = function () { res([d.result, c.result]); };"
            " tx.onerror = function () { res([-1, -1]); }; };"
            " r.onerror = function () { res([-1, -1]); }; })")

    def draft_recover_done(pg):
        """탭의 draftRecover 가 실제로 끝날 때까지 기다릴 때 쓴다."""
        return pg.evaluate("window.VoxQueue.draftRecover().then(function () { return true; })")

    def draft_info(pg):
        """가장 최근 초안의 {id, lock, aliveAtInf} - 없으면 None."""
        return pg.evaluate(
            "new Promise(function (res) { var r = indexedDB.open('voxlog', 2);"
            " r.onsuccess = function () { var db = r.result;"
            " var tx = db.transaction('drafts', 'readonly');"
            " var g = tx.objectStore('drafts').getAll();"
            " tx.oncomplete = function () { var rows = g.result || []; var d = rows[0];"
            " res(d ? {id: d.draftId, lock: d.lock === true, aliveAtInf: d.aliveAt === Infinity} : null); };"
            " tx.onerror = function () { res(null); }; };"
            " r.onerror = function () { res(null); }; })")

    def lock_names(pg, kind='held'):
        """이 출처의 navigator.locks.query() 이름 목록(held 또는 pending)."""
        return pg.evaluate("""async (kind) => {
            var q = await navigator.locks.query();
            return (q[kind] || []).map(function (l) { return l.name; });
        }""", kind)

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

    def t25():
        # 다른 앱으로 녹음한 m4a 를 '녹음 파일 올리기' 로 - 녹음과 같은 대기열을 거쳐 서버에 m4a 로 쌓임
        b, d = new_server("d25")
        src = tmp / "phone.m4a"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=3", "-c:a", "aac", str(src)], check=True, capture_output=True)
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        need(pg.is_visible("#file-btn"), "'녹음 파일 올리기' 단추가 보이지 않음")
        pg.set_input_files("#file-input", str(src))
        need(wait_for(lambda: len(server_items(b)) == 1, 15, pg=pg), "파일이 서버에 올라가지 않음")
        need(wait_for(lambda: queue_n(pg) == 0, 10, pg=pg), "대기열이 비지 않음")
        it = server_items(b)[0]
        need(it.get("mime") == "audio/mp4", "mime %r (기대 audio/mp4)" % it.get("mime"))
        need(2500 <= (it.get("duration_ms") or 0) <= 3500, "길이 %r ms (기대 약 3000)" % it.get("duration_ms"))
        need(len(list(d.glob("audio/*.m4a"))) == 1, "서버 audio 폴더에 m4a 가 없음")
        os.utime(src, (0, 86400 * 365))            # 파일 날짜가 옛날이어도 기록은 올린 날(작업한 날)로
        pg.set_input_files("#file-input", str(src))
        need(wait_for(lambda: len(server_items(b)) == 2, 15, pg=pg), "두 번째 파일이 올라가지 않음")
        today = time.strftime("%Y-%m-%d")
        need(all((x.get("recorded_at") or "")[:10] == today for x in server_items(b)),
             "기록 날짜가 오늘이 아님: %r" % [x.get("recorded_at") for x in server_items(b)])
        (tmp / "note.txt").write_text("x")
        pg.set_input_files("#file-input", str(tmp / "note.txt"))
        pg.wait_for_timeout(500)
        need(len(server_items(b)) == 2 and queue_n(pg) == 0, "소리 파일이 아닌 것이 대기열·서버에 들어감")
        c.close()
    check("25 녹음 파일 올리기: m4a 가 대기열을 거쳐 서버에 쌓임·다른 파일은 거절", t25)

    def t26():
        # 묻기 결과 지우기: 지난 답 목록의 '지우기' → 목록·펼친 답에서 사라지고 녹취는 남음
        b, d = new_server("d26")
        c = new_ctx(permissions=["microphone", "clipboard-read", "clipboard-write"])
        pg = c.new_page()
        pg.on("dialog", lambda dlg: dlg.accept())
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        need(wait_for(lambda: [x.get("status") for x in server_items(b)] == ["done"], 20, pg=pg), "녹취가 완료되지 않음")
        # 녹취 상세의 복사·공유: 받아쓴 글 그대로 나간다
        open_tab(pg, "list")
        need(wait_for(lambda: pg.locator("#list li").count() == 1, 10, pg=pg), "목록에 녹취가 없음")
        need(not pg.is_visible("#detail-copy"), "상세를 열기 전에 '복사' 단추가 보임")
        pg.locator("#list li .rec-main").first.click()
        text = api_get(b, "/api/recordings/" + server_items(b)[0]["id"])["transcript"]
        need(text and wait_for(lambda: pg.is_visible("#detail-copy"), 10, pg=pg), "상세에 '복사' 단추가 보이지 않음")
        pg.click("#detail-copy")
        need(wait_for(lambda: pg.evaluate("navigator.clipboard.readText()") == text, 5, pg=pg), "클립보드가 받아쓴 글이 아님")
        need(not pg.is_visible("#detail-share"), "공유를 지원하지 않는 기기에 '공유' 단추가 보임")
        pg.evaluate("window.__shared = null; navigator.share = function (d) { window.__shared = d; return Promise.resolve(); }")
        pg.click("#detail-close")
        pg.locator("#list li .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-share"), 5, pg=pg), "상세에 '공유' 단추가 보이지 않음")
        pg.click("#detail-share")
        need(pg.evaluate("window.__shared && window.__shared.text") == text, "공유한 글이 받아쓴 글이 아님")
        box = pg.locator("#detail-copy").bounding_box()
        need(box["height"] >= 44 and box["x"] + box["width"] <= 390, "복사 단추가 작거나 화면 밖")
        pg.evaluate("delete navigator.share")
        open_tab(pg, "ask")
        pg.select_option("#ask-scope", "today")
        pg.select_option("#ask-kind", "summary")
        pg.click("#ask-go")
        need(wait_for(lambda: "가짜 답" in pg.inner_text("#answer"), 20, pg=pg), "답이 오지 않음")
        need(wait_for(lambda: pg.locator("#answers .answer-del").count() == 1, 10, pg=pg), "'지우기' 단추가 없음")
        label = pg.inner_text("#answers .answer-open .rec-text").strip()
        need(" 녹취 “가짜 받아쓰기" in label, "지난 답 제목에 녹취의 때·첫마디가 없음: %r" % label)
        # 복사·공유: 답의 마크다운 원문이 나간다
        need(pg.is_visible("#answer-copy"), "'복사' 단추가 보이지 않음")
        full = api_get(b, "/api/answers")["items"][0]["answer"]
        pg.click("#answer-copy")
        need(wait_for(lambda: pg.evaluate("navigator.clipboard.readText()") == full, 5, pg=pg), "클립보드가 답의 원문이 아님")
        pg.evaluate("window.__shared = null; navigator.share = function (d) { window.__shared = d; return Promise.resolve(); }")
        pg.locator("#answers .answer-open").click()        # 다시 펼치면 공유 단추가 보인다(공유를 지원하는 기기)
        need(wait_for(lambda: pg.is_visible("#answer-share"), 5, pg=pg), "'공유' 단추가 보이지 않음")
        pg.click("#answer-share")
        need(pg.evaluate("window.__shared && window.__shared.text") == full, "공유한 글이 답의 원문이 아님")
        box = pg.locator("#answers .answer-del").bounding_box()
        need(box["width"] >= 44 and box["height"] >= 44 and box["x"] + box["width"] <= 390, "지우기 단추가 작거나 화면 밖")
        pg.click("#answers .answer-del")
        need(wait_for(lambda: pg.locator("#answers .answer-item").count() == 0, 10, pg=pg), "목록에서 사라지지 않음")
        need(pg.inner_text("#answer").strip() == "" and pg.is_visible("#answers-empty"), "펼친 답이 남아 있음")
        need(not pg.is_visible("#answer-actions"), "답을 지웠는데 복사·공유 단추가 남음")
        need(api_get(b, "/api/answers")["items"] == [], "서버에 답이 남아 있음")
        need(not list(d.glob("answers/*.json")), "answers 폴더에 파일이 남음")
        need(len(server_items(b)) == 1, "녹취까지 지워짐")
        c.close()
    check("26 묻기 결과 복사·공유·지우기: 원문이 나가고, 지우면 목록·펼친 답에서 사라지고 녹취는 남음", t26)


    def t27():
        # R40-N1: 탭1 이 녹음 중일 때 탭2 를 열어도 그 초안을 가져가지 않고, 탭1 의 녹음이 온전히 한 건 올라간다
        b, _ = new_server("d27")
        c = new_ctx()
        try:
            p1 = c.new_page()
            p1.goto(b + "/")
            p1.wait_for_selector("#rec")
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p1), "탭1 녹음이 켜지지 않음")
            time.sleep(7)
            need(db_drafts(p1)[1] >= 1, "녹음 중 조각이 초안에 쌓이지 않음: %s" % db_drafts(p1))
            p2 = c.new_page()
            p2.goto(b + "/")
            p2.wait_for_selector("#rec")
            need(wait_for(lambda: draft_recover_done(p2), 10, pg=p2), "탭2 의 draftRecover 가 끝나지 않음")
            left = db_drafts(p1)
            need(left[0] == 1, "탭2 가 녹음 중인 초안을 가져감 [초안, 조각]=%s" % left)
            need(queue_n(p2) == 0, "탭2 가 녹음 중인 초안을 대기열에 넣음")
            need("끝나지 않은 녹음" not in p2.inner_text("#toast"), "탭2 가 살렸다고 알림: " + p2.inner_text("#toast"))
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "false", 5, pg=p1), "탭1 녹음이 꺼지지 않음")
            need(wait_for(lambda: len(server_items(b)) == 1, 30, pg=p1), "탭1 녹음이 서버에 올라가지 않음")
            it = server_items(b)[0]
            need((it.get("duration_ms") or 0) >= 6000, "녹음이 잘려 올라감: %s ms" % it.get("duration_ms"))
            need(wait_for(lambda: db_drafts(p1) == [0, 0], 10, pg=p1), "고아 초안·조각이 남음: %s" % db_drafts(p1))
            need(wait_for(lambda: queue_n(p1) == 0, 10, pg=p1), "대기열이 비지 않음")
        finally:
            c.close()
    check("27 녹음 중 새 탭이 초안을 가져가지 않음 → 녹음 온전히 1건·고아 조각 없음", t27)

    def t28():
        # R40-N2: 업로드가 늦는 동안 넣은 두 번째 녹음도 첫 업로드가 끝난 뒤 올라간다
        b, _ = new_server("d28")
        c = new_ctx(service_workers="block")
        try:
            pg = c.new_page()

            def slow(route):
                if route.request.method == "POST" and route.request.url.endswith("/api/recordings"):
                    time.sleep(3)
                route.continue_()
            pg.route("**/api/recordings", slow)
            pg.goto(b + "/")
            pg.wait_for_selector("#rec")
            pg.evaluate("""() => {
                function blob() { return new Blob([new Uint8Array(64)], { type: 'audio/wav' }); }
                window.VoxQueue.enqueue({ blob: blob(), mime: 'audio/wav', clientId: 'n2-a' }).catch(() => {});
                setTimeout(function () {
                    window.VoxQueue.enqueue({ blob: blob(), mime: 'audio/wav', clientId: 'n2-b' }).catch(() => {});
                }, 1000);
            }""")
            need(wait_for(lambda: len(server_items(b)) == 2, 30, pg=pg),
                 "두 건이 다 올라가지 않음: 서버 %d건 · 대기 %s" % (len(server_items(b)), queue_n(pg)))
            need(wait_for(lambda: queue_n(pg) == 0, 10, pg=pg), "대기열이 비지 않음")
        finally:
            c.close()
    check("28 업로드 진행 중 넣은 두 번째 녹음도 올라감", t28)

    def t29():
        # R40-N3/R41: 200 이지만 JSON 이 아닌 응답(캐티브 포털·프록시), 빈 200, 500 text/html 을 '연결됨' 으로 받지 않는다
        b, _ = new_server("d29")
        c = new_ctx(service_workers="block")
        try:
            cases = [
                (200, "<html><body>로그인이 필요합니다</body></html>"),
                (200, ""),
                (500, "<html><body>서버 오류</body></html>"),
            ]
            for status, body in cases:
                pg = c.new_page()
                pg.route("**/api/**", lambda route, _req=None, st=status, bd=body: route.fulfill(
                    status=st, content_type="text/html", body=bd))
                pg.goto(b + "/")
                pg.wait_for_selector("#rec")
                label = "status %d body %r" % (status, body[:24])
                need(wait_for(lambda: pg.inner_text("#conn").strip() != "연결됨", 10, pg=pg),
                     label + " 인데 '연결됨' 으로 표시: " + pg.inner_text("#conn"))
                open_tab(pg, "list")
                need(wait_for(lambda: pg.is_visible("#toast") and pg.inner_text("#toast").strip(), 8, pg=pg),
                     label + " 오류 토스트가 보이지 않음")
                need(pg.inner_text("#conn").strip() != "연결됨",
                     label + " 목록을 열어도 '연결됨' 그대로: " + pg.inner_text("#conn"))
                need(list_count(pg) == 0, label + " 인데 목록 항목이 생김")
                pg.close()
        finally:
            c.close()
    check("29 JSON 아닌 200·빈 200·500 text/html → '연결됨' 아님·오류 표시", t29)

    def t30():
        # R44: 웹 잠금이 없는 탭에서는 초안 자체를 만들지 않는다 - 녹음·올리기는 그대로
        b, _ = new_server("d30")
        c = new_ctx()
        try:
            p1 = c.new_page()
            p1.add_init_script("Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });")
            p1.goto(b + "/")
            p1.wait_for_selector("#rec")
            need(p1.evaluate("window.VoxQueue.supported().draftLocks === false"),
                 "웹 잠금이 없는데 supported().draftLocks 가 false 가 아님")
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p1), "탭1 녹음이 켜지지 않음")
            time.sleep(7)
            need(db_drafts(p1) == [0, 0], "웹 잠금 없는 탭이 초안을 만듦: %s" % db_drafts(p1))
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "false", 5, pg=p1), "탭1 녹음이 꺼지지 않음")
            need(wait_for(lambda: len(server_items(b)) == 1, 30, pg=p1), "탭1 녹음이 서버에 올라가지 않음")
            it = server_items(b)[0]
            need((it.get("duration_ms") or 0) >= 6000, "녹음이 잘려 올라감: %s ms" % it.get("duration_ms"))
            need(db_drafts(p1) == [0, 0], "초안·조각이 남음: %s" % db_drafts(p1))
            need(wait_for(lambda: queue_n(p1) == 0, 10, pg=p1), "대기열이 비지 않음")
        finally:
            c.close()
    check("30 웹 잠금 없는 탭: 초안 없음·녹음 온전히 1건", t30)

    def t31():
        # R41: 200 text/html·id 없는 JSON 은 업로드 성공이 아니다 - 대기열에 남고 정상 응답에서 올라간다
        b, _ = new_server("d31")
        c = new_ctx(service_workers="block")
        try:
            pg = c.new_page()
            state = {"mode": "html"}

            def rec(route):
                if state["mode"] == "html":
                    route.fulfill(status=200, content_type="text/html",
                                  body="<html><body>로그인이 필요합니다</body></html>")
                elif state["mode"] == "no-id":
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
                else:
                    route.continue_()

            pg.route("**/api/recordings", rec)
            pg.goto(b + "/")
            pg.wait_for_selector("#rec")
            pg.evaluate("""() => {
                window.VoxQueue.enqueue({
                    blob: new Blob([new Uint8Array(20000)], { type: 'audio/wav' }),
                    mime: 'audio/wav', clientId: 'bad-resp-a'
                }).catch(() => {});
            }""")
            need(wait_for(lambda: queue_n(pg) == 1, 15, pg=pg), "200 text/html 뒤 대기열이 비었음")
            need(len(server_items(b)) == 0, "200 text/html 인데 서버에 기록이 생김")
            need(wait_for(lambda: pg.evaluate(
                "window.VoxQueue.pending().then(a => a[0] && a[0].lastError === '서버 응답이 올바르지 않음')"),
                15, pg=pg), "lastError 가 '서버 응답이 올바르지 않음' 이 아님")
            state["mode"] = "no-id"
            pg.evaluate("window.VoxQueue.flush().then(() => true)")
            need(wait_for(lambda: queue_n(pg) == 1, 10, pg=pg), "200 JSON id 없음 뒤 대기열이 비었음")
            need(len(server_items(b)) == 0, "200 JSON id 없음 인데 서버에 기록이 생김")
            state["mode"] = "ok"
            pg.evaluate("window.VoxQueue.flush().then(() => true)")
            need(wait_for(lambda: len(server_items(b)) == 1, 20, pg=pg), "정상 응답 뒤 올라가지 않음")
            need(wait_for(lambda: queue_n(pg) == 0, 10, pg=pg), "정상 응답 뒤 대기열이 남음")
        finally:
            c.close()
    check("31 200 text/html·id 없는 JSON 은 대기열에 남고 정상 응답에서 올라감", t31)

    def t32():
        # R41-N13: 탭2 가 먼저 열린 뒤 탭1 이 녹음하고 닫히면, 탭2 의 기다리는 요청이 회수해야 한다
        b, _ = new_server("d32")
        c = new_ctx()
        try:
            p2 = c.new_page()
            p2.goto(b + "/")
            p2.wait_for_selector("#rec")
            p1 = c.new_page()
            p1.goto(b + "/")
            p1.wait_for_selector("#rec")
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p1), "탭1 녹음이 켜지지 않음")
            time.sleep(7)
            need(db_drafts(p1)[0] == 1, "탭1 녹음 중 초안이 없음: %s" % db_drafts(p1))
            n = p2.evaluate("window.VoxQueue.draftRecover()")
            need(n == 0, "탭2 의 즉시 판정이 0 이 아님: %s" % n)
            p1.close()
            need(wait_for(lambda: len(server_items(b)) == 1, 10, pg=p2),
                 "탭1 을 닫은 뒤 10초 안에 탭2 가 초안을 회수하지 못함")
            need(wait_for(lambda: db_drafts(p2) == [0, 0], 10, pg=p2), "탭2 회수 뒤 초안·조각이 남음: %s" % db_drafts(p2))
            need(wait_for(lambda: "끝나지 않은 녹음 1건" in p2.inner_text("#toast"), 5, pg=p2),
                 "탭2 토스트에 '끝나지 않은 녹음 1건' 이 없음: " + p2.inner_text("#toast"))
            need(wait_for(lambda: queue_n(p2) == 0, 10, pg=p2), "탭2 대기열이 비지 않음")
        finally:
            c.close()
    check("32 탭2 먼저 열림·탭1 닫힘 → 기다리던 요청이 10초 안에 회수", t32)

    def t33():
        # R41-N15: 녹음 중 새로고침하면 22초 재시도 없이 곧바로 초안을 살린다
        b, _ = new_server("d33")
        c = new_ctx()
        try:
            p = c.new_page()
            p.goto(b + "/")
            p.wait_for_selector("#rec")
            p.click("#rec")
            need(wait_for(lambda: p.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p), "녹음이 켜지지 않음")
            time.sleep(7)
            need(db_drafts(p)[0] == 1, "새로고침 전 초안이 없음: %s" % db_drafts(p))
            p.reload()
            p.wait_for_selector("#rec")
            need(wait_for(lambda: len(server_items(b)) == 1, 10, pg=p),
                 "새로고침 뒤 10초 안에 초안이 올라가지 않음")
            need(wait_for(lambda: db_drafts(p) == [0, 0], 10, pg=p), "새로고침 뒤 초안·조각이 남음: %s" % db_drafts(p))
            need(wait_for(lambda: queue_n(p) == 0, 10, pg=p), "새로고침 뒤 대기열이 비지 않음")
        finally:
            c.close()
    check("33 녹음 중 새로고침 → 10초 안에 초안 회수·업로드", t33)

    def t34():
        # R41-N16: 조각 0개 새 세대 초안은 '살렸습니다' 로 세지 않고 지운다
        b, _ = new_server("d34")
        c = new_ctx()
        try:
            p = c.new_page()
            p.goto(b + "/")
            p.wait_for_selector("#rec")
            p.evaluate("""async () => {
                await new Promise((resolve, reject) => {
                    var req = indexedDB.open('voxlog', 2);
                    req.onsuccess = () => {
                        var db = req.result;
                        var tx = db.transaction('drafts', 'readwrite');
                        tx.objectStore('drafts').put({
                            draftId: 'empty-1', lock: true, aliveAt: Infinity,
                            mime: 'audio/webm', recordedAt: new Date().toISOString()
                        });
                        tx.oncomplete = resolve;
                        tx.onerror = () => reject(tx.error);
                    };
                    req.onerror = () => reject(req.error);
                });
            }""")
            n = p.evaluate("window.VoxQueue.draftRecover()")
            need(n == 0, "조각 0개 초안을 %s건으로 셈" % n)
            need(db_drafts(p) == [0, 0], "조각 0개 초안이 지워지지 않음: %s" % db_drafts(p))
        finally:
            c.close()
    check("34 조각 0개 새 세대 초안: 회수 0·초안 삭제", t34)

    def t35():
        # R41-N18: draftAppend 실패로 draftOk=false 인 길도 DB 초안·잠금을 정리한다
        b, _ = new_server("d35")
        c = new_ctx()
        try:
            p1 = c.new_page()
            p1.goto(b + "/")
            p1.wait_for_selector("#rec")
            p1.evaluate("() => { window.VoxQueue.draftAppend = () => Promise.reject(new Error('x')); }")
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p1), "녹음이 켜지지 않음")
            time.sleep(7)
            need(db_drafts(p1)[0] == 1, "녹음 중 초안이 없음: %s" % db_drafts(p1))
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "false", 5, pg=p1), "녹음이 꺼지지 않음")
            need(wait_for(lambda: len(server_items(b)) == 1, 30, pg=p1), "draftAppend 실패 뒤 녹음이 올라가지 않음")
            need((server_items(b)[0].get("duration_ms") or 0) >= 6000,
                 "녹음이 잘려 올라감: %s ms" % server_items(b)[0].get("duration_ms"))
            need(wait_for(lambda: db_drafts(p1) == [0, 0], 10, pg=p1), "초안·조각이 남음: %s" % db_drafts(p1))
            need(wait_for(lambda: queue_n(p1) == 0, 10, pg=p1), "대기열이 비지 않음")
            p2 = c.new_page()
            p2.goto(b + "/")
            p2.wait_for_selector("#rec")
            held = lock_names(p2, "held")
            need(not any(name.startswith("voxlog-draft-") for name in held),
                 "다른 탭의 held 에 초안 잠금이 남음: %s" % held)
        finally:
            c.close()
    check("35 draftAppend 실패 → 서버 1건·초안 0·잠금 없음", t35)

    def t36():
        # R43-N6 전환기: 잠금 표식 없는 구세대 초안은 신선하면 건너뛰고, 오래되면 회수한다
        b, _ = new_server("d36")
        c = new_ctx()
        try:
            p = c.new_page()
            p.goto(b + "/")
            p.wait_for_selector("#rec")
            p.evaluate("""async () => {
                await new Promise((resolve, reject) => {
                    var req = indexedDB.open('voxlog', 2);
                    req.onsuccess = () => {
                        var db = req.result;
                        var tx = db.transaction(['drafts', 'chunks'], 'readwrite');
                        tx.objectStore('drafts').put({
                            draftId: 'old-1', mime: 'audio/webm',
                            recordedAt: new Date().toISOString(), aliveAt: Date.now()
                        });
                        tx.objectStore('chunks').add({
                            draftId: 'old-1', seq: 0,
                            blob: new Blob([new Uint8Array(4096)], { type: 'audio/webm' })
                        });
                        tx.oncomplete = resolve;
                        tx.onerror = () => reject(tx.error);
                    };
                    req.onerror = () => reject(req.error);
                });
            }""")
            n = p.evaluate("window.VoxQueue.draftRecover()")
            need(n == 0, "신선한 구세대 초안을 %s건으로 셈" % n)
            need(db_drafts(p) == [1, 1], "신선한 구세대 초안이 지워짐: %s" % db_drafts(p))
            p.evaluate("""async () => {
                await new Promise((resolve, reject) => {
                    var req = indexedDB.open('voxlog', 2);
                    req.onsuccess = () => {
                        var db = req.result;
                        var tx = db.transaction('drafts', 'readwrite');
                        var st = tx.objectStore('drafts');
                        var g = st.get('old-1');
                        g.onsuccess = () => {
                            var d = g.result;
                            d.aliveAt = Date.now() - 60000;
                            st.put(d);
                        };
                        tx.oncomplete = resolve;
                        tx.onerror = () => reject(tx.error);
                    };
                    req.onerror = () => reject(req.error);
                });
            }""")
            n = p.evaluate("window.VoxQueue.draftRecover()")
            need(n == 1, "오래된 구세대 초안을 %s건으로 셈" % n)
            need(wait_for(lambda: len(server_items(b)) == 1, 20, pg=p), "오래된 구세대 초안이 서버에 올라가지 않음")
            need(wait_for(lambda: db_drafts(p) == [0, 0], 10, pg=p), "회수 뒤 초안·조각이 남음: %s" % db_drafts(p))
        finally:
            c.close()
    check("36 구세대 전환기: 신선하면 남김·오래되면 회수", t36)

    def t37():
        # R44: 새 초안 줄은 lock=true·aliveAt=Infinity, 녹음 탭이 실제 잠금을 쥐고 있다
        b, _ = new_server("d37")
        c = new_ctx()
        try:
            p1 = c.new_page()
            p1.goto(b + "/")
            p1.wait_for_selector("#rec")
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p1), "녹음이 켜지지 않음")
            time.sleep(7)
            info = draft_info(p1)
            need(info is not None, "녹음 중 초안이 없음")
            need(info["lock"] is True, "초안 lock 표식이 true 가 아님: %s" % info)
            need(info["aliveAtInf"] is True, "초안 aliveAt 이 Infinity 가 아님: %s" % info)
            p2 = c.new_page()
            p2.goto(b + "/")
            p2.wait_for_selector("#rec")
            name = "voxlog-draft-" + info["id"]
            held = lock_names(p2, "held")
            need(name in held, "탭2 의 held 에 %s 가 없음: %s" % (name, held))
        finally:
            c.close()
    check("37 녹음 초안의 lock 표식·다른 탭에서 보이는 잠금", t37)

    def t38():
        # R41-N13/R44: 기다리는 요청은 freeze 에서 abort 되고 resume 에서 다시 걸린다
        b, _ = new_server("d38")
        c = new_ctx()
        try:
            p1 = c.new_page()
            p1.goto(b + "/")
            p1.wait_for_selector("#rec")
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p1), "녹음이 켜지지 않음")
            time.sleep(7)
            info = draft_info(p1)
            need(info is not None and info["lock"] is True, "녹음 중 새 세대 초안이 없음: %s" % info)
            name = "voxlog-draft-" + info["id"]
            p2 = c.new_page()
            p2.goto(b + "/")
            p2.wait_for_selector("#rec")
            need(wait_for(lambda: lock_names(p2, "pending").count(name) == 1, 10, pg=p2),
                 "탭2 의 pending 에 %s 가 1개가 아님: %s" % (name, lock_names(p2, "pending")))
            p2.evaluate("document.dispatchEvent(new Event('freeze'))")
            need(wait_for(lambda: lock_names(p2, "pending").count(name) == 0, 5, pg=p2),
                 "freeze 뒤 pending 에 %s 가 남음: %s" % (name, lock_names(p2, "pending")))
            p2.evaluate("document.dispatchEvent(new Event('resume'))")
            need(wait_for(lambda: lock_names(p2, "pending").count(name) == 1, 10, pg=p2),
                 "resume 뒤 pending 에 %s 가 다시 1개가 아님: %s" % (name, lock_names(p2, "pending")))
            p1.click("#rec")
            need(wait_for(lambda: p1.get_attribute("#rec", "aria-pressed") == "false", 5, pg=p1), "녹음이 꺼지지 않음")
            need(wait_for(lambda: len(server_items(b)) == 1, 20, pg=p1), "녹음이 정상 저장되지 않음")
            need(wait_for(lambda: db_drafts(p2) == [0, 0], 10, pg=p2), "초안·조각이 남음: %s" % db_drafts(p2))
            need("끝나지 않은 녹음" not in p2.inner_text("#toast"), "탭2 가 살렸다고 알림: " + p2.inner_text("#toast"))
        finally:
            c.close()
    check("38 기다리는 요청: freeze abort→resume 재요청·녹음 탭 정상 저장", t38)

    def t39():
        # R44-N1: mr.start 예외 때 초안·잠금·녹음 상태를 정리하고 다시 녹음할 수 있다
        b, _ = new_server("d39")
        c = new_ctx()
        try:
            p = c.new_page()
            p.goto(b + "/")
            p.wait_for_selector("#rec")
            p.evaluate("() => { window.__mrStart = MediaRecorder.prototype.start;"
                       " MediaRecorder.prototype.start = function () { throw new Error('start 실패'); }; }")
            p.click("#rec")
            need(wait_for(lambda: "녹음을 시작하지 못했습니다" in p.inner_text("#toast"), 5, pg=p),
                 "녹음 시작 실패 토스트가 없음: " + p.inner_text("#toast"))
            need(p.get_attribute("#rec", "aria-pressed") == "false", "녹음 시작 실패 뒤 녹음 중으로 보임")
            need(not p.evaluate("document.getElementById('rec').classList.contains('recording')"),
                 "녹음 단추가 recording 상태임")
            need(p.inner_text("#rec-result") != "녹음 중…", "녹음 중 안내가 남음")
            need(wait_for(lambda: db_drafts(p) == [0, 0], 10, pg=p), "실패 뒤 초안·조각이 남음: %s" % db_drafts(p))
            held = lock_names(p, "held")
            need(not any(name.startswith("voxlog-draft-") for name in held),
                 "실패 뒤 초안 잠금이 남음: %s" % held)
            time.sleep(0.5)
            p.evaluate("() => { MediaRecorder.prototype.start = window.__mrStart; }")
            p.click("#rec")
            need(wait_for(lambda: p.get_attribute("#rec", "aria-pressed") == "true", 5, pg=p),
                 "원래 start 복원 뒤 다시 녹음이 시작되지 않음")
            p.click("#rec")
            need(wait_for(lambda: p.get_attribute("#rec", "aria-pressed") == "false", 5, pg=p),
                 "다시 시작한 녹음이 멈추지 않음")
        finally:
            c.close()
    check("39 녹음 시작 실패 때 초안·잠금 정리·다시 녹음 가능", t39)

    def t40():
        # R44-N3: pageshow 회수는 bfcache 복원(persisted)일 때만 - 첫 로드 회수는 app.js init 이 한다
        b, _ = new_server("d40")
        c = new_ctx()
        try:
            p = c.new_page()
            p.goto(b + "/")
            p.wait_for_selector("#rec")
            time.sleep(2)  # 첫 로드의 draftRecover 가 끝난 뒤
            p.evaluate("""async () => {
                await new Promise((resolve, reject) => {
                    var req = indexedDB.open('voxlog', 2);
                    req.onsuccess = () => {
                        var db = req.result;
                        var tx = db.transaction(['drafts', 'chunks'], 'readwrite');
                        tx.objectStore('drafts').put({
                            draftId: 'orphan-1', lock: true, aliveAt: Infinity,
                            mime: 'audio/webm', recordedAt: new Date().toISOString()
                        });
                        tx.objectStore('chunks').add({
                            draftId: 'orphan-1', seq: 0,
                            blob: new Blob([new Uint8Array(4096)], { type: 'audio/webm' })
                        });
                        tx.oncomplete = resolve;
                        tx.onerror = () => reject(tx.error);
                    };
                    req.onerror = () => reject(req.error);
                });
            }""")
            need(db_drafts(p) == [1, 1], "넣은 초안·조각이 없음: %s" % db_drafts(p))
            p.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: false }))")
            time.sleep(1.5)
            need(db_drafts(p) == [1, 1], "persisted:false pageshow 가 초안을 회수함: %s" % db_drafts(p))
            p.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))")
            need(wait_for(lambda: db_drafts(p) == [0, 0], 10, pg=p),
                 "persisted:true pageshow 가 초안을 회수하지 않음: %s" % db_drafts(p))
            need(wait_for(lambda: p.is_visible("#toast") and
                           "끝나지 않은 녹음 1건을 살렸습니다" in p.inner_text("#toast"), 5, pg=p),
                 "회수 토스트가 보이지 않음: " + p.inner_text("#toast"))
        finally:
            c.close()
    check("40 pageshow 는 bfcache 복원(persisted)일 때만 초안 회수", t40)

    def t42():
        # 이름·태그 저장 → 목록 이름·칩 2개+`+N`, 칩 거르기·풀기, 이름 검색, 다시 받아쓰기 뒤 이름 유지,
        # 320px 넘침·겹침, 받아쓰는 중 폴링이 쓰던 입력 보존, 격리 출처에서 편집 칸 숨김
        stt_file = tmp / "t42-stt.txt"
        stt_file.write_text("첫 받아쓰기", encoding="utf-8")
        stt_py = "print(open(%r, encoding='utf-8').read(), end='')" % str(stt_file)
        b, _ = new_server("d42", stt_cmd="%s -c %s" % (sys.executable, shlex.quote(stt_py)))
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "받아쓰기가 끝나지 않음")
        rid = server_items(b)[0]["id"]
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "done", 20),
             "자동 태그가 끝나기 전이라 사람 편집이 자동 태그에 덮일 수 있음")
        label = "가" * 40
        tags = ["태그%02d" % i for i in range(1, 11)]
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        pg.fill("#detail-label", label)
        pg.fill("#detail-tags", ", ".join(tags))
        pg.click("#detail-save")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["label"] == label, 10, pg=pg),
             "이름이 저장되지 않음: %r" % api_get(b, "/api/recordings/" + rid)["label"])
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["tags"] == tags, 10, pg=pg),
             "태그가 저장되지 않음: %r" % api_get(b, "/api/recordings/" + rid)["tags"])

        # 거르기가 실제로 거르는지 보려면 태그가 다른 녹취가 하나 더 있어야 한다
        wav = tmp / "t42-second.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=1", "-c:a", "pcm_s16le", str(wav)],
                       check=True, capture_output=True)
        rid2 = api_post_wav(b, wav)["id"]
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid2)["status"] == "done", 20),
             "두 번째 녹취가 받아쓰기되지 않음")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid2)["autotag"] == "done", 20),
             "두 번째 녹취의 자동 태그가 끝나지 않음")
        api_patch(b, rid2, {"label": "다른 녹취", "tags": ["다른태그"]})
        pg.click("#detail-close")
        open_tab(pg, "rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록이 2개가 아님: %d" % list_count(pg))

        item = pg.locator("#list .rec-item[data-id='%s']" % rid)
        got_text = item.locator(".rec-text").inner_text().strip()
        need(got_text == label, "목록 제목이 이름이 아님: %r" % got_text)
        chips = item.locator(".rec-tags .tag-chip")
        need(chips.count() == 3, "목록 칩 %d개 (칩 2개+`+N` 기대)" % chips.count())
        got_chips = [chips.nth(i).inner_text() for i in range(3)]
        need(got_chips == [tags[0], tags[1], "+8"], "목록 칩 글자가 다름: %r" % got_chips)

        chips.first.click()
        need(wait_for(lambda: pg.is_visible("#tag-filter-row"), 5, pg=pg), "칩 클릭 뒤 #tag-filter-row 가 보이지 않음")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "칩 거르기 뒤 목록 %d개 (기대 1)" % list_count(pg))
        need(pg.locator("#list .rec-item").first.get_attribute("data-id") == rid,
             "거른 목록이 그 태그 녹취가 아님")
        need(pg.is_hidden("#detail"), "목록 칩 클릭이 상세를 엶")
        need(tags[0] in pg.inner_text("#tag-filter-label"),
             "#tag-filter-label 에 태그가 없음: " + pg.inner_text("#tag-filter-label"))
        pg.click("#tag-filter-clear")
        need(wait_for(lambda: pg.is_hidden("#tag-filter-row"), 5, pg=pg), "거르기 풀기 뒤 #tag-filter-row 가 숨지 않음")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "거르기 푼 뒤 목록 %d개 (기대 2)" % list_count(pg))

        pg.fill("#search", label)
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "이름 검색 결과 %d개 (기대 1)" % list_count(pg))
        match = pg.locator("#list .rec-item .rec-match").first.inner_text().strip()
        need(match == "이름에서 맞음", "이름에서 맞음 표시가 없음: %r" % match)
        pg.fill("#search", "")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "검색을 지운 뒤 목록이 2개가 아님")

        # 다시 받아쓰기: 글은 바뀌고 이름·태그는 남아야 한다
        stt_file.write_text("두번째 받아쓰기", encoding="utf-8")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid).click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음(다시 받아쓰기)")
        pg.click("#detail-retry")
        need(wait_for(lambda: "두번째 받아쓰기" in pg.inner_text("#transcript"), 30, pg=pg),
             "다시 받아쓰기 결과가 글에 반영되지 않음: " + pg.inner_text("#transcript")[:60])
        need(wait_for(lambda: pg.inner_text("#detail-title").strip() == label, 10, pg=pg),
             "다시 받아쓰기 뒤 상세 제목이 이름이 아님: " + pg.inner_text("#detail-title"))
        got = api_get(b, "/api/recordings/" + rid)
        need(got["label"] == label and got["tags"] == tags,
             "다시 받아쓰기 뒤 이름·태그가 바뀜: %r / %r" % (got["label"], got["tags"]))

        # 받아쓰는 중 폴링이 쓰던 입력칸을 지우지 않아야 한다
        slow = "%s -c %s" % (sys.executable, shlex.quote("import time; time.sleep(6); print('느린 받아쓰기')"))
        b2, _ = new_server("d42b", stt_cmd=slow)
        c2 = new_ctx()
        pg2 = c2.new_page()
        detail_hits = {"n": 0}

        def count_detail_get(r):
            if "/api/recordings/r-" in r.url and "?" not in r.url:
                detail_hits["n"] += 1
        pg2.on("request", count_detail_get)
        pg2.goto(b2 + "/")
        pg2.wait_for_selector("#rec")
        rec_cycle(pg2)
        open_tab(pg2, "list")
        need(wait_for(lambda: list_count(pg2) == 1, 15, pg=pg2), "느린 서버에서 목록 항목이 없음")
        pg2.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg2.is_visible("#detail-edit") and detail_ready(pg2), 10, pg=pg2),
             "느린 서버 상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        pg2.fill("#detail-label", "쓰던 이름")
        pg2.fill("#detail-tags", "쓰던, 태그")
        pg2.evaluate("document.activeElement && document.activeElement.blur()")
        start_hits = detail_hits["n"]
        need(wait_for(lambda: detail_hits["n"] > start_hits, 15, pg=pg2),
             "받아쓰는 동안 상세를 다시 읽지 않아(폴링 없음) 입력 보존을 잴 수 없음")
        need(pg2.input_value("#detail-label") == "쓰던 이름",
             "폴링이 쓰던 이름을 지움: %r" % pg2.input_value("#detail-label"))
        need(pg2.input_value("#detail-tags") == "쓰던, 태그",
             "폴링이 쓰던 태그를 지움: %r" % pg2.input_value("#detail-tags"))
        c2.close()

        # 320px: 이름 40자·태그 10개 표본에서 칩이 컨테이너를 넘지 않고, 편집 칸이 오디오·글과 겹치지 않는다
        c3 = new_ctx(viewport={"width": 320, "height": 800})
        p3 = c3.new_page()
        p3.goto(b + "/")
        p3.wait_for_selector("#rec")
        open_tab(p3, "list")
        need(wait_for(lambda: p3.locator("#list .rec-item").count() == 2, 10, pg=p3), "320px 목록이 2개가 아님")
        sw, iw = p3.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        need(sw <= iw + 1, "320px 목록에서 가로 넘침 %d>%d" % (sw, iw))
        lboxes = p3.evaluate("""(rid) => {
            var li = document.querySelector("#list .rec-item[data-id='" + rid + "'] .rec-tags");
            return {box: li.getBoundingClientRect().toJSON(),
                    chips: Array.from(li.querySelectorAll('.tag-chip')).map(function (e) {
                        return e.getBoundingClientRect().toJSON(); }) };
        }""", rid)
        for i, box in enumerate(lboxes["chips"]):
            need(box["right"] <= lboxes["box"]["right"] + 1, "320px 목록 칩 %d 가 컨테이너 밖: %r" % (i, lboxes))
            need(box["left"] >= lboxes["box"]["left"] - 1, "320px 목록 칩 %d 가 컨테이너 왼쪽 밖" % i)
        p3.locator("#list .rec-item[data-id='%s'] .rec-main" % rid).click()
        need(wait_for(lambda: p3.is_visible("#detail-edit") and p3.locator("#detail-chips .tag-chip").count() == 10, 10, pg=p3),
             "320px 상세 편집 칸이 보이지 않거나 칩 10개가 그려지지 않음: %d" % p3.locator("#detail-chips .tag-chip").count())
        boxes = p3.evaluate("""() => {
            var r = function (sel) { var e = document.querySelector(sel); return e ? e.getBoundingClientRect().toJSON() : null; };
            return {edit: r('#detail-edit'), audio: r('#detail-audio'), tr: r('#transcript'),
                    chipsBox: r('#detail-chips'), labelW: r('#detail-label').width, editW: r('#detail-edit').width,
                    chips: Array.from(document.querySelectorAll('#detail-chips .tag-chip')).map(function (e) {
                        return e.getBoundingClientRect().toJSON(); }) };
        }""")
        need(len(boxes["chips"]) == 10, "320px 상세 칩 %d개 (기대 10)" % len(boxes["chips"]))
        for i, box in enumerate(boxes["chips"]):
            need(box["right"] <= boxes["chipsBox"]["right"] + 1,
                 "320px 상세 칩 %d 가 컨테이너 밖: right %s > %s" % (i, box["right"], boxes["chipsBox"]["right"]))
        need(boxes["labelW"] <= boxes["editW"] + 1, "320px 이름 입력칸이 편집 칸보다 넓음")
        need(not overlap(boxes["edit"], boxes["audio"]), "320px #detail-edit 과 #detail-audio 가 겹침")
        need(not overlap(boxes["edit"], boxes["tr"]), "320px #detail-edit 과 #transcript 가 겹침")
        sw, iw = p3.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        need(sw <= iw + 1, "320px 상세에서 가로 넘침 %d>%d" % (sw, iw))
        c3.close()

        # 격리된 출처 흉내: 편집 칸은 숨고 칩은 그대로 보인다
        c4 = new_ctx()
        c4.add_init_script("Object.defineProperty(window, 'indexedDB', {configurable: true, get() { throw new Error('denied'); }})")
        p4 = c4.new_page()
        p4.goto(b + "/")
        p4.wait_for_selector("#rec")
        open_tab(p4, "list")
        need(wait_for(lambda: p4.locator("#list .rec-item").count() == 2, 10, pg=p4), "격리 출처에서 목록이 읽히지 않음")
        p4.locator("#list .rec-item[data-id='%s'] .rec-main" % rid).click()
        need(wait_for(lambda: p4.is_visible("#detail"), 5, pg=p4), "격리 출처에서 상세가 열리지 않음")
        time.sleep(0.5)
        need(p4.is_hidden("#detail-edit"), "격리 출처인데 #detail-edit 이 보임")
        need(p4.locator("#detail-chips .tag-chip").count() == 10, "격리 출처에서 칩이 보이지 않음")
        c4.close()
        c.close()
    check("42 이름·태그 저장·칩·거르기·이름 검색·다시 받아쓰기·320px·폴링 입력·격리 편집 숨김", t42)

    def t43():
        # 자동 태그: 점선 AI 칩, 사람이 지운 태그 보호, '태그 다시 달기', LLM 실패 때 조용한 표시
        stt_file = tmp / "t43-stt.txt"
        stt_file.write_text("회의 녹취", encoding="utf-8")
        stt_py = "print(open(%r, encoding='utf-8').read(), end='')" % str(stt_file)
        stt_cmd = "%s -c %s" % (sys.executable, shlex.quote(stt_py))
        llm_py = ("import sys, time; sys.stdin.read(); time.sleep(1.5); "
                  "sys.stdout.write('회의\\n가짜 태그\\n- 세번째')")
        llm_cmd = "%s -c %s" % (sys.executable, shlex.quote(llm_py))
        b, _ = new_server("d43", stt_cmd=stt_cmd, llm_cmd=llm_cmd)
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: len(server_items(b)) == 1, 25, pg=pg),
             "녹음이 서버에 올라가지 않음(대기 %s, 실패 칸 %r)" % (queue_n(pg), pg.inner_text("#failed-list")))
        need(wait_for(lambda: list_count(pg) == 1, 15, pg=pg), "목록 항목이 생기지 않음")
        rid = server_items(b)[0]["id"]
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "pending", 20),
             "받아쓰기 뒤 자동 태그가 pending 이 되지 않음")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "done", 20),
             "자동 태그가 끝나지 않음")
        it = api_get(b, "/api/recordings/" + rid)
        need(it["status"] == "done", "자동 태그가 받아쓰기 상태를 바꿈: " + it["status"])
        need(it["tags"] == ["회의", "가짜 태그", "세번째"], "자동 태그가 아님: %r" % it["tags"])
        need(it["tags_auto"] == it["tags"], "자동 태그가 tags_auto 에 없음: %r" % it["tags_auto"])

        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.locator("#detail-chips .tag-chip").count() == 3 and detail_ready(pg), 10, pg=pg),
             "상세 칩이 3개가 아니거나 첫 읽기가 끝나지 않음: %d" % pg.locator("#detail-chips .tag-chip").count())
        ai = pg.evaluate("""() => Array.from(document.querySelectorAll('#detail-chips .tag-chip')).map(function (e) {
            return {text: e.textContent, auto: e.classList.contains('tag-auto'), title: e.title,
                    style: getComputedStyle(e).borderTopStyle, visible: e.getBoundingClientRect().width > 0};
        })""")
        need([x["text"] for x in ai] == ["회의", "가짜 태그", "세번째"], "상세 칩 글자가 다름: %r" % ai)
        need(all(x["auto"] and x["style"] == "dashed" and x["title"] == "AI 가 단 태그" and x["visible"] for x in ai),
             "AI 칩이 점선·title·보임이 아님: %r" % ai)

        # 사람이 '회의' 를 지우고 저장하면 tags_human=true, 남긴 AI 태그 표시는 유지
        pg.fill("#detail-tags", "가짜 태그, 세번째, 사람태그")
        pg.click("#detail-save")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["tags"] == ["가짜 태그", "세번째", "사람태그"], 10, pg=pg),
             "사람이 고친 태그가 저장되지 않음: %r" % api_get(b, "/api/recordings/" + rid)["tags"])
        it = api_get(b, "/api/recordings/" + rid)
        need(it["tags_human"] is True, "태그를 고쳤는데 tags_human 이 아님")
        need(it["tags_auto"] == ["가짜 태그", "세번째"], "남긴 AI 태그 표시가 아님: %r" % it["tags_auto"])

        # 다시 받아쓰기 뒤에도 사람이 지운 '회의' 가 돌아오지 않는다.
        # 자동 태그는 상세 폴링보다 먼저 끝나므로 pending 은 재받아쓰기 직후에 잡는다.
        stt_file.write_text("다시 받아쓴 회의", encoding="utf-8")
        pg.click("#detail-retry")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "pending", 15),
             "다시 받아쓰기 뒤 자동 태그가 다시 돌지 않음")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "done", 20),
             "다시 받아쓰기 뒤 자동 태그가 끝나지 않음")
        need(wait_for(lambda: "다시 받아쓴 회의" in pg.inner_text("#transcript"), 30, pg=pg),
             "다시 받아쓰기 결과가 글에 반영되지 않음")
        it = api_get(b, "/api/recordings/" + rid)
        need(it["status"] == "done", "다시 받아쓰기 뒤 상태가 완료가 아님: " + it["status"])
        need(it["tags"] == ["가짜 태그", "세번째", "사람태그"],
             "사람 손댐 뒤 자동 태그가 태그를 바꿈: %r" % it["tags"])
        need("회의" not in it["tags"], "사람이 지운 '회의' 가 다시 붙음: %r" % it["tags"])
        need(wait_for(lambda: "회의" not in pg.evaluate("document.querySelector('#detail-chips').innerText"), 10, pg=pg),
             "상세 칩에 지운 '회의' 가 남음")

        # '태그 다시 달기': 사람 태그는 남고 예전 AI 태그만 새 AI 태그로
        need(wait_for(lambda: pg.is_visible("#detail-retag"), 10, pg=pg), "'태그 다시 달기' 가 보이지 않음")
        pg.click("#detail-retag")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "pending", 15),
             "'태그 다시 달기' 가 pending 을 만들지 않음")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "done", 20),
             "'태그 다시 달기' 가 끝나지 않음")
        it = api_get(b, "/api/recordings/" + rid)
        need(it["tags"] == ["사람태그", "회의", "가짜 태그", "세번째"],
             "다시 달기 결과가 사람 태그 먼저 + 새 AI 태그가 아님: %r" % it["tags"])
        need(it["tags_auto"] == ["회의", "가짜 태그", "세번째"], "다시 달기 AI 표시가 아님: %r" % it["tags_auto"])
        need(it["tags_human"] is True, "'태그 다시 달기' 가 tags_human 을 바꿈")
        need(wait_for(lambda: "회의" in pg.evaluate("document.querySelector('#detail-chips').innerText"), 10, pg=pg),
             "다시 달기 뒤 상세 칩에 '회의' 가 없음")
        auto = pg.evaluate("""() => Array.from(document.querySelectorAll('#detail-chips .tag-chip'))
            .filter(function (e) { return e.classList.contains('tag-auto'); }).map(function (e) { return e.textContent; })""")
        need(auto == ["회의", "가짜 태그", "세번째"], "다시 달기 뒤 AI 칩 표시가 다름: %r" % auto)
        c.close()

        # LLM 실패: 녹취는 done, 태그 없음, 상세에 작은 실패 안내만
        b2, _ = new_server("d43b", env_extra={"FAKE_LLM_FAIL": "1"})
        c2 = new_ctx()
        p2 = c2.new_page()
        p2.goto(b2 + "/")
        p2.wait_for_selector("#rec")
        rec_cycle(p2)
        open_tab(p2, "list")
        need(wait_for(lambda: len(server_items(b2)) == 1, 25, pg=p2),
             "실패 LLM 서버에 녹음이 올라가지 않음(대기 %s)" % queue_n(p2))
        need(wait_for(lambda: p2.locator("#list .rec-item").count() == 1, 15, pg=p2), "실패 LLM 서버에서 목록 항목이 없음")
        rid2 = server_items(b2)[0]["id"]
        need(wait_for(lambda: api_get(b2, "/api/recordings/" + rid2)["status"] == "done", 20),
             "LLM 실패가 받아쓰기 상태를 바꿈: " + api_get(b2, "/api/recordings/" + rid2)["status"])
        need(wait_for(lambda: api_get(b2, "/api/recordings/" + rid2)["autotag"] == "failed", 20),
             "자동 태그가 failed 가 아님: %r" % api_get(b2, "/api/recordings/" + rid2)["autotag"])
        it2 = api_get(b2, "/api/recordings/" + rid2)
        need(it2["tags"] == [], "자동 태그 실패인데 태그가 생김: %r" % it2["tags"])
        p2.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: p2.inner_text("#detail-tag-state").strip() == "자동 태그를 달지 못했습니다", 10, pg=p2),
             "실패 안내가 없음: %r" % p2.inner_text("#detail-tag-state"))
        need(p2.locator("#detail-chips .tag-chip").count() == 0, "자동 태그 실패인데 상세에 칩이 있음")
        c2.close()
    check("43 자동 태그 점선 칩·사람 손댐 보호·태그 다시 달기·LLM 실패 표시", t43)

    def t44():
        # LLM 없음: 자동 태그 칩 없음·'태그 다시 달기' 숨김, 손 이름·태그·검색·거르기는 그대로
        missing = str(tmp / "no-such-llm-command")
        b, _ = new_server("d44", llm_cmd=missing)
        health = api_get(b, "/api/health")
        need(health["llm"] is False, "LLM 없는 서버인데 health llm 이 참: %r" % health)
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: len(server_items(b)) == 1, 25, pg=pg),
             "LLM 없는 서버에 녹음이 올라가지 않음(대기 %s)" % queue_n(pg))
        need(wait_for(lambda: list_count(pg) == 1, 15, pg=pg), "LLM 없는 서버에서 목록 항목이 없음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "LLM 없는 서버에서 받아쓰기가 끝나지 않음")
        rid = server_items(b)[0]["id"]
        time.sleep(1.0)
        it = api_get(b, "/api/recordings/" + rid)
        need(it["tags"] == [] and it["tags_auto"] == [] and it["autotag"] is None,
             "LLM 없이 자동 태그가 생김: %r" % it)
        need(pg.locator("#list .rec-tags .tag-chip").count() == 0, "LLM 없이 목록에 태그 칩이 생김")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "LLM 없이 편집 칸이 숨거나 첫 읽기가 끝나지 않음")
        need(pg.locator("#detail-chips .tag-chip").count() == 0, "LLM 없이 상세에 자동 태그 칩이 생김")
        need(pg.is_hidden("#detail-retag"), "LLM 없는데 '태그 다시 달기' 가 보임")

        pg.fill("#detail-label", "손으로 붙인 이름")
        pg.fill("#detail-tags", "손태그, 둘째")
        pg.click("#detail-save")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["label"] == "손으로 붙인 이름", 10, pg=pg),
             "LLM 없이 손 이름이 저장되지 않음")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["tags"] == ["손태그", "둘째"], 10, pg=pg),
             "LLM 없이 손 태그가 저장되지 않음: %r" % api_get(b, "/api/recordings/" + rid)["tags"])
        pg.click("#detail-close")
        need(wait_for(lambda: pg.locator("#list .rec-item .rec-text").first.inner_text().strip() == "손으로 붙인 이름", 10, pg=pg),
             "LLM 없이 목록 제목이 손 이름이 아님")

        pg.fill("#search", "손으로 붙인")
        need(wait_for(lambda: list_count(pg) == 1 and
                      pg.locator("#list .rec-item .rec-match").first.inner_text().strip() == "이름에서 맞음", 10, pg=pg),
             "LLM 없이 이름 검색이 안 됨")
        pg.fill("#search", "")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "검색을 지운 뒤 목록이 1개가 아님")
        pg.locator("#list .rec-item .rec-tags .tag-chip").first.click()
        need(wait_for(lambda: pg.is_visible("#tag-filter-row"), 5, pg=pg), "LLM 없이 태그 거르기가 안 됨")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "거른 목록이 1개가 아님")
        need(pg.locator("#list .rec-item .rec-tags .tag-chip").count() == 2, "LLM 없이 손 태그 칩이 2개가 아님")
        pg.click("#tag-filter-clear")
        need(wait_for(lambda: pg.is_hidden("#tag-filter-row"), 5, pg=pg), "거르기 풀기가 안 됨")
        c.close()
    check("44 LLM 없음: 자동 태그 칩·다시 달기 숨김, 손 편집·검색·거르기는 그대로", t44)

    def t45():
        # R49-N1: 이름만 저장해도 자동 태그가 이어짐(태그를 사람 손댐으로 치지 않음)·pending 중 이름 저장에도 AI 태그가 붙음
        def chips_of(pg):
            return pg.evaluate("""() => Array.from(document.querySelectorAll('#detail-chips .tag-chip'))
                .map(function (e) { return {text: e.textContent, auto: e.classList.contains('tag-auto')}; })""")

        b, _ = new_server("d45", env_extra={"FAKE_LLM_TAG_DELAY": "1.5"})
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: len(server_items(b)) == 1, 25, pg=pg),
             "녹음이 서버에 올라가지 않음(대기 %s, 실패 칸 %r)" % (queue_n(pg), pg.inner_text("#failed-list")))
        need(wait_for(lambda: list_count(pg) == 1, 15, pg=pg), "목록 항목이 생기지 않음")
        rid = server_items(b)[0]["id"]
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "done", 25),
             "자동 태그가 끝나지 않음")
        it = api_get(b, "/api/recordings/" + rid)
        need(it["tags"] == ["회의", "가짜 태그", "세번째"], "처음 자동 태그가 아님: %r" % it["tags"])
        need(it["tags_auto"] == it["tags"] and it["tags_human"] is False, "처음 태그 상태가 다름: %r" % it)

        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.locator("#detail-chips .tag-chip").count() == 3 and detail_ready(pg), 10, pg=pg),
             "상세 칩이 3개가 아니거나 첫 읽기가 끝나지 않음: %d" % pg.locator("#detail-chips .tag-chip").count())
        chips = chips_of(pg)
        need([x["text"] for x in chips] == ["회의", "가짜 태그", "세번째"] and all(x["auto"] for x in chips),
             "처음 AI 칩 표시가 아님: %r" % chips)

        # (1) 이름만 바꿔 저장: 서버 태그 상태는 그대로(tags_human=false), 칩은 여전히 AI 표시
        pg.fill("#detail-label", "이름만 바꾼 녹취")
        pg.click("#detail-save")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["label"] == "이름만 바꾼 녹취", 10, pg=pg),
             "이름이 저장되지 않음")
        it = api_get(b, "/api/recordings/" + rid)
        need(it["tags_human"] is False, "이름만 고쳤는데 tags_human 이 참이 됨: %r" % it)
        need(it["tags"] == ["회의", "가짜 태그", "세번째"] and it["tags_auto"] == it["tags"],
             "이름만 고쳤는데 태그가 바뀜: %r" % it)
        chips = chips_of(pg)
        need([x["text"] for x in chips] == ["회의", "가짜 태그", "세번째"] and all(x["auto"] for x in chips),
             "이름만 저장한 뒤 AI 칩 표시가 사라짐: %r" % chips)

        # 그 뒤 다시 받아쓰기 → 자동 태그가 다시 돌고 AI 칩이 유지된다
        pg.click("#detail-retry")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "pending", 15),
             "다시 받아쓰기 뒤 자동 태그가 다시 돌지 않음")
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "done", 25),
             "다시 받아쓰기 뒤 자동 태그가 끝나지 않음")
        it = api_get(b, "/api/recordings/" + rid)
        need(it["status"] == "done", "다시 받아쓰기 뒤 상태가 완료가 아님: " + it["status"])
        need(it["tags_human"] is False, "다시 받아쓰기 뒤 tags_human 이 참: %r" % it)
        need(it["tags"] == ["회의", "가짜 태그", "세번째"] and it["tags_auto"] == it["tags"],
             "다시 받아쓰기 뒤 AI 태그가 아님: %r" % it)
        need(wait_for(lambda: pg.locator("#detail-chips .tag-chip.tag-auto").count() == 3, 15, pg=pg),
             "다시 받아쓰기 뒤 AI 칩이 3개가 아님: %r" % chips_of(pg))
        c.close()

        # (2) 자동 태그가 pending 인 동안 이름만 저장: 곧 도착할 AI 태그가 버려지지 않는다
        b2, _ = new_server("d45b", env_extra={"FAKE_LLM_TAG_DELAY": "4"})
        c2 = new_ctx()
        p2 = c2.new_page()
        p2.goto(b2 + "/")
        p2.wait_for_selector("#rec")
        rec_cycle(p2)
        open_tab(p2, "list")
        need(wait_for(lambda: len(server_items(b2)) == 1, 25, pg=p2),
             "pending 서버에 녹음이 올라가지 않음(대기 %s)" % queue_n(p2))
        rid2 = server_items(b2)[0]["id"]
        need(wait_for(lambda: api_get(b2, "/api/recordings/" + rid2)["autotag"] == "pending", 20, pg=p2),
             "자동 태그가 pending 이 되지 않음")
        need(wait_for(lambda: list_count(p2) == 1, 10, pg=p2), "pending 서버에서 목록 항목이 없음")
        p2.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: detail_ready(p2), 10, pg=p2), "상세 첫 읽기가 끝나지 않음")
        need(p2.locator("#detail-chips .tag-chip").count() == 0,
             "pending 인데 상세에 칩이 있음: %r" % chips_of(p2))
        p2.fill("#detail-label", "기다리며 붙인 이름")
        p2.click("#detail-save")
        need(wait_for(lambda: api_get(b2, "/api/recordings/" + rid2)["label"] == "기다리며 붙인 이름", 10, pg=p2),
             "pending 중 이름이 저장되지 않음")
        it2 = api_get(b2, "/api/recordings/" + rid2)
        need(it2["tags_human"] is False, "pending 중 이름만 저장했는데 tags_human 이 참: %r" % it2)
        need(it2["tags"] == [] and it2["tags_auto"] == [], "pending 중 이름만 저장했는데 태그가 생김: %r" % it2)
        need(wait_for(lambda: api_get(b2, "/api/recordings/" + rid2)["autotag"] == "done", 25, pg=p2),
             "지연 뒤 자동 태그가 끝나지 않음")
        it2 = api_get(b2, "/api/recordings/" + rid2)
        need(it2["tags"] == ["회의", "가짜 태그", "세번째"], "pending 중 저장한 뒤 AI 태그가 버려짐: %r" % it2["tags"])
        need(it2["tags_auto"] == it2["tags"], "pending 중 저장한 뒤 AI 표시가 없음: %r" % it2["tags_auto"])
        need(wait_for(lambda: p2.locator("#detail-chips .tag-chip.tag-auto").count() == 3, 25, pg=p2),
             "pending 중 저장한 뒤 AI 칩이 보이지 않음: %r" % chips_of(p2))
        chips = chips_of(p2)
        need([x["text"] for x in chips] == ["회의", "가짜 태그", "세번째"] and all(x["auto"] for x in chips),
             "pending 중 저장한 뒤 AI 칩 글자·표시가 다름: %r" % chips)
        c2.close()
    check("45 이름만 저장해도 자동 태그가 이어짐 · pending 중 이름 저장에도 AI 태그가 붙음", t45)

    def t46():
        # R48-N24: 가짜 마이크 3초 webm - 상세의 오디오 길이가 유한(2~5초)이고,
        # 같은 파일을 '녹음 파일 올리기' 로 올려도 목록에 길이가 보인다
        b, _ = new_server("d46")
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg, seconds=3)
        need(wait_for(lambda: len(server_items(b)) == 1, 25, pg=pg),
             "녹음이 서버에 올라가지 않음(대기 %s)" % queue_n(pg))
        rid = server_items(b)[0]["id"]
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 15, pg=pg), "목록 항목이 생기지 않음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-audio"), 10, pg=pg), "상세 오디오가 보이지 않음")

        def audio_seconds():
            return pg.evaluate("() => { var a = document.getElementById('detail-audio');"
                               " return isFinite(a.duration) && a.duration > 0 ? a.duration : null; }")
        need(wait_for(lambda: audio_seconds() is not None, 15, pg=pg),
             "상세 오디오 길이가 유한값이 되지 않음(Infinity/NaN)")
        secs = audio_seconds()
        need(2.0 <= secs <= 5.0, "상세 오디오 길이 %r 초 (기대 2~5)" % secs)

        blob = urllib.request.urlopen(b + "/api/recordings/" + rid + "/audio", timeout=10).read()
        need(blob[:4] == b"\x1aE\xdf\xa3", "서버 오디오가 webm 이 아님: %r" % blob[:8])
        same = tmp / "t46-same.webm"
        same.write_bytes(blob)
        pg.set_input_files("#file-input", str(same))
        need(wait_for(lambda: len(server_items(b)) == 2, 20, pg=pg), "같은 webm 파일이 서버에 올라가지 않음")
        rid2 = [x["id"] for x in server_items(b) if x["id"] != rid][0]
        it2 = api_get(b, "/api/recordings/" + rid2)
        need(2000 <= (it2.get("duration_ms") or 0) <= 5000,
             "올린 webm 의 서버 길이 %r ms (기대 2~5초)" % it2.get("duration_ms"))

        open_tab(pg, "rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 15, pg=pg), "목록이 2개가 되지 않음: %d" % list_count(pg))
        dur = pg.locator("#list .rec-item[data-id='%s'] .dur" % rid2)
        need(dur.count() == 1, "올린 파일의 목록 줄이 없음")
        txt = wait_for(lambda: (dur.inner_text() or "").strip(), 10, pg=pg)
        need(txt, "올린 webm 의 목록 길이가 비어 있음")
        m = re.match(r"^(\d+):(\d\d)$", txt)
        need(m, "목록 길이 표시가 시계 형식이 아님: %r" % txt)
        need(2 <= int(m.group(1)) * 60 + int(m.group(2)) <= 5, "목록 길이 %r (기대 2~5초)" % txt)
        box = dur.bounding_box()
        need(box and box["width"] > 0 and box["height"] > 0, "목록 길이가 화면에 보이지 않음: %r" % box)
        c.close()
    check("46 webm 길이: 상세 오디오 유한(2~5초)·올린 같은 파일도 목록에 길이", t46)

    def t47():
        # R49-N5: 받아쓰기가 끝나는 순간(transcribing→done, autotag null)을 한 번 잘못 받아도
        # 2초 뒤 상세를 다시 읽어, 곧 도착한 AI 태그가 새로고침 없이 보인다
        slow = "%s -c %s" % (sys.executable, shlex.quote("import time; time.sleep(6); print('끝난 받아쓰기')"))
        b, _ = new_server("d47", stt_cmd=slow, env_extra={"FAKE_LLM_TAG_DELAY": "1.5"})
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: len(server_items(b)) == 1, 25, pg=pg),
             "녹음이 서버에 올라가지 않음(대기 %s)" % queue_n(pg))
        rid = server_items(b)[0]["id"]
        need(wait_for(lambda: list_count(pg) == 1, 15, pg=pg), "목록 항목이 생기지 않음")
        pg.locator("#list .rec-item .rec-main").first.click()
        # 실제 응답으로 받아쓰는 중(prevStatus)을 먼저 본다
        need(wait_for(lambda: "받아쓰는 중" in pg.inner_text("#transcript"), 15, pg=pg),
             "상세가 받아쓰는 중이 아님: " + pg.inner_text("#transcript")[:40])

        hits = {"n": 0}

        def detail_route(route):
            req = route.request
            if req.method != "GET" or "/audio" in req.url or "?" in req.url:
                route.continue_()
                return
            hits["n"] += 1
            if hits["n"] == 1:  # 받아쓰기가 끝나는 순간: 상태는 done, autotag 는 아직 null
                route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"id": rid, "status": "done", "autotag": None, "transcript": "끝난 받아쓰기",
                     "title": "끝난 받아쓰기", "chars": 7, "duration_ms": 2000,
                     "recorded_at": server_items(b)[0].get("recorded_at")}))
            else:
                route.continue_()
        pg.route("**/api/recordings/r-*", detail_route)
        need(wait_for(lambda: hits["n"] >= 1, 20, pg=pg), "상세를 다시 읽지 않아 끝나는 순간을 넣지 못함")
        need(wait_for(lambda: pg.locator("#detail-chips .tag-chip.tag-auto").count() == 3, 25, pg=pg),
             "새로고침 없이 AI 칩이 보이지 않음 - 칩 %r / 상태 %r" %
             (pg.inner_text("#detail-chips"), pg.inner_text("#detail-tag-state")))
        for i in range(3):
            box = pg.locator("#detail-chips .tag-chip.tag-auto").nth(i).bounding_box()
            need(box and box["width"] > 0 and box["height"] > 0, "AI 칩 %d 가 화면에 보이지 않음: %r" % (i, box))
        st = pg.inner_text("#detail-tag-state").strip()
        need(st == "", "태그가 붙은 뒤에도 상태 글이 남음: %r" % st)
        pg.unroute("**/api/recordings/r-*", detail_route)
        c.close()
    check("47 받아쓰기 끝 순간 상세를 잘못 받아도 새로고침 없이 AI 칩", t47)

    def t48():
        # R49-N6: 자동 태그가 pending 인 동안 상세 GET 한 번이 실패(abort)해도,
        # 그 뒤 태그가 붙으면 'AI 가 태그를 다는 중…' 이 사라지고 칩이 보인다
        b, _ = new_server("d48", env_extra={"FAKE_LLM_TAG_DELAY": "4"})
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: len(server_items(b)) == 1, 25, pg=pg),
             "녹음이 서버에 올라가지 않음(대기 %s)" % queue_n(pg))
        rid = server_items(b)[0]["id"]
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["autotag"] == "pending", 20),
             "자동 태그가 pending 이 되지 않음")
        need(wait_for(lambda: list_count(pg) == 1, 15, pg=pg), "목록 항목이 생기지 않음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.inner_text("#detail-tag-state").strip() == "AI 가 태그를 다는 중…", 10, pg=pg),
             "상세에 'AI 가 태그를 다는 중…' 이 보이지 않음: %r" % pg.inner_text("#detail-tag-state"))

        aborted = {"n": 0}

        def detail_route(route):
            req = route.request
            if req.method != "GET" or "/audio" in req.url or "?" in req.url:
                route.continue_()
                return
            aborted["n"] += 1
            if aborted["n"] == 1:
                route.abort()
            else:
                route.continue_()
        pg.route("**/api/recordings/r-*", detail_route)
        need(wait_for(lambda: aborted["n"] >= 1, 15, pg=pg), "상세를 다시 읽지 않아 실패를 넣지 못함")
        need(wait_for(lambda: pg.locator("#detail-chips .tag-chip.tag-auto").count() == 3, 25, pg=pg),
             "실패 뒤 태그가 붙어도 AI 칩이 보이지 않음: %r" % pg.inner_text("#detail-chips"))
        st = pg.inner_text("#detail-tag-state").strip()
        need(st == "", "'AI 가 태그를 다는 중…' 이 사라지지 않음: %r" % st)
        box = pg.locator("#detail-chips .tag-chip.tag-auto").first.bounding_box()
        need(box and box["width"] > 0 and box["height"] > 0, "AI 칩이 화면에 보이지 않음: %r" % box)
        pg.unroute("**/api/recordings/r-*", detail_route)
        c.close()
    check("48 폴링 오류(abort) 뒤에도 태그가 붙으면 안내가 사라지고 AI 칩", t48)


    def t49():
        b, _ = new_server("d49")
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        opts_get = {"n": 0}

        def track_opts_get(resp):
            if resp.request.method == "GET" and resp.url.endswith("/api/stt-options"):
                opts_get["n"] += 1

        pg.on("response", track_opts_get)
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults") and pg.is_visible("#stt-defaults-fields"), 10, pg=pg),
             "설정 칸의 받아쓰기 옵션 묶음이 보이지 않음")
        need(wait_for(lambda: opts_get["n"] >= 1, 10, pg=pg), "설정 칸이 GET /api/stt-options 를 읽지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "설정 칸의 입력 칸·저장 단추가 풀리지 않음")
        pg.select_option("#stt-defaults-preprocess", "denoise")
        pg.fill("#stt-defaults-speakers", "2")
        pg.click("#stt-defaults-save")
        expected = {"preprocess": "denoise", "num_speakers": 2}
        need(wait_for(lambda: api_get(b, "/api/stt-options")["options"] == expected, 10, pg=pg),
             "저장한 기본값이 서버 GET 에 없음: %r" % api_get(b, "/api/stt-options")["options"])
        pg.reload()
        pg.wait_for_selector("#rec")
        pg.click("#settings-btn")

        def reloaded_values():
            return (pg.is_visible("#stt-defaults-fields") and
                    pg.evaluate("document.querySelector('#stt-defaults-preprocess').value") == "denoise" and
                    pg.evaluate("document.querySelector('#stt-defaults-speakers').value") == "2")

        need(wait_for(reloaded_values, 10, pg=pg),
             "새로고침 뒤 설정 칸에 denoise·화자 2 가 그대로가 아님")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "새로고침 뒤 설정 칸의 입력 칸·저장 단추가 풀리지 않음")
        need(api_get(b, "/api/stt-options")["options"] == expected,
             "새로고침 뒤 서버 GET 값이 바뀜: %r" % api_get(b, "/api/stt-options")["options"])
        c.close()
    check("49 설정 칸 저장 → 새로고침·서버 GET 에 그대로", t49)


    def t50():
        b, _ = new_server("d50")
        c = new_ctx()
        pg = c.new_page()
        bodies = []
        pg.add_init_script(STT_OPTIONS_HOLD_JS)

        def track_retry(req):
            url = req.url.split("?")[0]
            if req.method == "POST" and "/api/recordings/" in url and url.endswith("/retry"):
                bodies.append(req.post_data)

        pg.on("request", track_retry)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "받아쓰기가 끝나지 않음")
        rid = server_items(b)[0]["id"]
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        locked = pg.evaluate("""() => ({
            visible: !document.querySelector('#detail-stt').hidden,
            fields: ['preprocess', 'speakers', 'context', 'auto', 'review'].map(function (k) {
                return document.querySelector('#detail-stt-' + k).disabled;
            }),
            run: document.querySelector('#detail-stt-run').disabled,
            state: document.querySelector('#detail-stt-state').textContent
        })""")
        need(locked["visible"], "옵션 바꿔 다시 받아쓰기 묶음이 열리지 않음: %r" % locked)
        need(all(locked["fields"]), "기본값 응답 전 상세 입력 칸이 잠기지 않음: %r" % locked)
        need(locked["run"], "기본값 응답 전 상세 실행 단추가 잠기지 않음: %r" % locked)
        need(locked["state"] == "불러오는 중…", "기본값 응답 전 상세 상태가 '불러오는 중…' 이 아님: %r" % locked["state"])
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "상세 옵션 칸의 기본값 GET 응답이 쥐어지지 않음")
        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 상세 기본값 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchDone"), 5, pg=pg),
             "놓은 상세 기본값 응답이 도착하지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 8, pg=pg),
             "기본값 응답 뒤 상세 입력 칸·실행 단추가 풀리지 않음")
        pg.select_option("#detail-stt-preprocess", "denoise")
        pg.click("#detail-stt-run")
        need(wait_for(lambda: len(bodies) >= 1, 10, pg=pg), "옵션 바꿔 다시 받아쓰기 POST 가 나가지 않음")
        first_body = bodies[0]
        need(first_body is not None, "옵션 바꿔 다시 받아쓰기 POST 본문이 없음")
        need(json.loads(first_body) == {"options": {"preprocess": "denoise"}},
             "옵션 바꿔 다시 받아쓰기 본문이 다름: %r" % first_body)
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid)["stt_options"] == {"preprocess": "denoise"}, 10, pg=pg),
             "상세 GET 의 stt_options 가 denoise 가 아님: %r" % api_get(b, "/api/recordings/" + rid)["stt_options"])
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("document.querySelector('#detail-stt-preprocess').value") == "denoise" and
                      stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "상세 옵션 묶음이 녹음의 stt_options 로 채워지지 않음")

        open_tab(pg, "rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 20, pg=pg), "두 번째 녹취가 목록에 없음")
        rid2 = [item["id"] for item in server_items(b) if item["id"] != rid][0]
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid2).click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "두 번째 녹취 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "두 번째 녹취의 옵션 묶음이 열리지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 8, pg=pg),
             "두 번째 녹취의 옵션 입력 칸·실행 단추가 풀리지 않음")
        start = len(bodies)
        pg.click("#detail-stt-run")
        need(wait_for(lambda: len(bodies) > start, 10, pg=pg), "기본 옵션 POST 가 나가지 않음")
        empty_body = bodies[start]
        need(json.loads(empty_body) == {"options": {}},
             "아무것도 안 고른 옵션 POST 본문이 {} 가 아님: %r" % empty_body)

        start = len(bodies)
        pg.click("#detail-retry")
        need(wait_for(lambda: len(bodies) > start, 10, pg=pg), "기존 다시 받아쓰기 POST 가 나가지 않음")
        plain_body = bodies[start]
        need(plain_body in (None, ""), "기존 다시 받아쓰기가 본문을 보냄: %r" % plain_body)
        c.close()
    check("50 옵션 바꿔 다시 받아쓰기 본문·상세 GET·기존 재시도 본문 없음", t50)


    def t51():
        counter = tmp / "t51-count.txt"
        stt_code = ("import pathlib, sys\n"
                    "p = pathlib.Path(sys.argv[1])\n"
                    "n = int(p.read_text(encoding='utf-8')) if p.exists() else 0\n"
                    "p.write_text(str(n + 1), encoding='utf-8')\n"
                    "print('첫 받아쓰기' if n == 0 else '두 번째 받아쓰기')\n")
        stt_cmd = "%s -c %s %s" % (sys.executable, shlex.quote(stt_code), shlex.quote(str(counter)))
        b, _ = new_server("d51", stt_cmd=stt_cmd)
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        rid = server_items(b)[0]["id"]
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.inner_text("#transcript").strip() == "첫 받아쓰기", 20, pg=pg),
             "첫 받아쓰기 글이 상세에 없음: %r" % pg.inner_text("#transcript"))
        pg.click("#detail-retry")
        need(wait_for(lambda: pg.inner_text("#transcript").strip() == "두 번째 받아쓰기", 30, pg=pg),
             "두 번째 받아쓰기 글이 상세에 없음: %r" % pg.inner_text("#transcript"))
        need(wait_for(lambda: pg.is_visible("#detail-prev"), 10, pg=pg), "#detail-prev 가 보이지 않음")
        pg.click("#detail-prev summary")
        need(wait_for(lambda: pg.locator("#detail-prev-list .prev-item").count() == 1, 5, pg=pg),
             "#detail-prev 를 펼쳐도 지난 글 벌이 보이지 않음")
        pg.locator("#detail-prev-list .prev-item summary").first.click()
        prev_text = pg.locator("#detail-prev-list .prev-item pre.transcript").first
        need(wait_for(lambda: prev_text.is_visible(), 5, pg=pg), "지난 글 벌을 펼쳐도 글칸이 보이지 않음")
        need(prev_text.inner_text().strip() == "첫 받아쓰기",
             "지난 글이 앞 글과 다름: %r" % prev_text.inner_text())
        got = api_get(b, "/api/recordings/" + rid)
        prevs = got.get("prev_transcripts")
        need(got["transcript"] == "두 번째 받아쓰기" and isinstance(prevs, list) and
             len(prevs) == 1 and prevs[0]["text"] == "첫 받아쓰기",
             "서버의 새 글·지난 글 벌이 다름: %r / %r" % (got["transcript"], prevs))
        need("transcript_prev" not in got and "prev_stt_used" not in got,
             "서버 응답에 없앤 키가 남음: %r" % sorted(got))

        def inject_used(route):
            if route.request.method != "GET" or "/audio" in route.request.url:
                route.continue_()
                return
            data = api_get(b, "/api/recordings/" + rid)
            data["stt_used"] = {"preprocess": "denoise", "speakers": 1, "auto": True, "review": False}
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(data, ensure_ascii=False))

        pg.route("**/api/recordings/r-*", inject_used)
        pg.reload()
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "새로고침 뒤 목록 항목이 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-stt-used") and "전처리 denoise" in pg.inner_text("#detail-stt-used"), 10, pg=pg),
             "#detail-stt-used 가 보이지 않거나 옵션 문구가 없음: %r" % pg.inner_text("#detail-stt-used"))
        need(pg.is_visible("#detail-prev"), "주입한 상세 응답에서 #detail-prev 가 보이지 않음")
        pg.unroute("**/api/recordings/r-*", inject_used)
        c.close()
    check("51 두 번 받아쓰기 뒤 이전 글·받아쓴 옵션 표시", t51)


    def t52():
        b, _ = new_server("d52")
        c = new_ctx(viewport={"width": 320, "height": 800})
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "받아쓰기가 끝나지 않음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "상세 옵션 묶음이 열리지 않음")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults") and pg.is_visible("#stt-defaults-fields"), 10, pg=pg),
             "설정 옵션 묶음이 보이지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "설정 옵션 묶음의 입력 칸·저장 단추가 풀리지 않음")
        need(pg.is_visible("#detail-stt"), "상세 옵션 묶음이 설정을 열 때 숨겨짐")

        rects = pg.evaluate("""() => {
            function r(sel) { var e = document.querySelector(sel); if (!e) return null; var b = e.getBoundingClientRect();
                return {x: b.x, y: b.y, width: b.width, height: b.height, right: b.right, bottom: b.bottom}; }
            return {defaults: r('#stt-defaults'), detail: r('#detail-stt'), vw: window.innerWidth};
        }""")
        vw = rects["vw"]
        for name, key in (("설정", "defaults"), ("상세", "detail")):
            box = rects[key]
            need(box is not None and box["width"] > 0 and box["height"] > 0,
                 "320px %s 옵션 묶음이 보이지 않음: %r" % (name, box))
            need(box["x"] >= -0.5 and box["right"] <= vw + 0.5,
                 "320px %s 옵션 묶음이 화면 밖으로 넘침: %r (폭 %s)" % (name, box, vw))
        need(not overlap(rects["defaults"], rects["detail"]), "320px 두 옵션 묶음이 겹침")
        children_out = pg.evaluate("""() => {
            var out = [];
            ['#stt-defaults', '#detail-stt'].forEach(function (sel) {
                var box = document.querySelector(sel), br = box.getBoundingClientRect();
                box.querySelectorAll('input, select, textarea, button').forEach(function (e) {
                    var r = e.getBoundingClientRect();
                    if (r.left < br.left - 1 || r.right > br.right + 1) out.push(sel + ':' + (e.id || e.tagName));
                });
            });
            return out;
        }""")
        need(not children_out, "320px 옵션 묶음 안의 입력칸이 묶음 밖으로 넘침: %r" % children_out)

        def put_400(route):
            if route.request.method != "PUT":
                route.continue_()
                return
            route.fulfill(status=400, content_type="application/json",
                          body=json.dumps({"error": "받아쓰기 옵션 저장 거절 - 서버 글"}, ensure_ascii=False))

        pg.route("**/api/stt-options", put_400)
        pg.click("#stt-defaults-save")
        need(wait_for(lambda: pg.is_visible("#toast") and "받아쓰기 옵션 저장 거절 - 서버 글" in pg.inner_text("#toast"), 5, pg=pg),
             "PUT 400 뒤 서버 글이 토스트로 보이지 않음: %r" % pg.inner_text("#toast"))
        pg.unroute("**/api/stt-options", put_400)
        c.close()
    check("52 320px 두 옵션 묶음 넘침·겹침 없음, PUT 400 서버 글 토스트", t52)


    def t53():
        # 폴링이 상세를 다시 그리는 동안 열어 둔 옵션 입력을 지우지 않는다(F3)
        slow = "import sys, time\nprint('느린 받아쓰기', flush=True)\ntime.sleep(22)\n"
        b, _ = new_server("d53", stt_cmd="%s -c %s" % (sys.executable, shlex.quote(slow)))
        c = new_ctx()
        pg = c.new_page()
        detail_gets = {"n": 0}
        opts_gets = {"n": 0}

        def track(resp):
            if resp.request.method != "GET":
                return
            url = resp.url.split("?")[0]
            if url.endswith("/api/stt-options"):
                opts_gets["n"] += 1
            elif re.search(r"/api/recordings/[^/]+$", url) and "/audio" not in url:
                detail_gets["n"] += 1

        pg.on("response", track)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() in ("대기", "받아쓰는 중"),
                      15, pg=pg), "받아쓰기가 끝나 버려 상세 폴링이 돌지 않음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "옵션 묶음이 열리지 않음")
        need(wait_for(lambda: opts_gets["n"] >= 1, 5, pg=pg),
             "옵션 묶음이 기본값 GET 을 마치기 전에 채워짐")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "옵션 묶음의 입력 칸·실행 단추가 풀리지 않음")
        pg.fill("#detail-stt-context", "회의 참석자: 김, 박")
        pg.fill("#detail-stt-speakers", "2")
        before = detail_gets["n"]
        need(wait_for(lambda: detail_gets["n"] >= before + 2, 16, pg=pg),
             "상세 폴링이 두 번 다시 그리지 않음(%d회)" % (detail_gets["n"] - before))
        pg.wait_for_timeout(160)
        need(pg.evaluate("document.querySelector('#detail-stt-context').value") == "회의 참석자: 김, 박",
             "폴링 뒤 문맥 입력이 지워짐: %r" % pg.evaluate("document.querySelector('#detail-stt-context').value"))
        need(pg.evaluate("document.querySelector('#detail-stt-speakers').value") == "2",
             "폴링 뒤 화자 수 입력이 지워짐: %r" % pg.evaluate("document.querySelector('#detail-stt-speakers').value"))
        need(pg.is_visible("#detail-stt"), "폴링 뒤 옵션 묶음이 닫힘")
        c.close()
    check("53 받아쓰는 중 상세 폴링이 옵션 입력을 지우지 않음", t53)


    def t54():
        # 전체 기본값 denoise: 옵션 없는 녹취의 묶음은 denoise 로 채워지고,
        # 전부 기본으로 실행하면 녹취별 stt_options 는 저장되지 않는다(N3)
        b, _ = new_server("d54")
        c = new_ctx()
        pg = c.new_page()
        bodies = []
        opts_gets = {"n": 0}

        def track_opts(resp):
            if resp.request.method == "GET" and resp.url.split("?")[0].endswith("/api/stt-options"):
                opts_gets["n"] += 1

        def track_retry(req):
            url = req.url.split("?")[0]
            if req.method == "POST" and "/api/recordings/" in url and url.endswith("/retry"):
                bodies.append(req.post_data)

        pg.on("response", track_opts)
        pg.on("request", track_retry)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults") and pg.is_visible("#stt-defaults-fields"), 10, pg=pg),
             "설정 칸의 받아쓰기 옵션 묶음이 보이지 않음")
        need(wait_for(lambda: opts_gets["n"] >= 1, 10, pg=pg),
             "설정 칸이 기본값 GET 을 마치기 전에 채워짐")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "설정 칸의 입력 칸·저장 단추가 풀리지 않음")
        pg.select_option("#stt-defaults-preprocess", "denoise")
        pg.click("#stt-defaults-save")
        need(wait_for(lambda: api_get(b, "/api/stt-options")["options"] == {"preprocess": "denoise"}, 10, pg=pg),
             "전체 기본값 denoise 가 저장되지 않음: %r" % api_get(b, "/api/stt-options")["options"])
        pg.click("#settings-btn")

        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "받아쓰기가 끝나지 않음")
        rid = server_items(b)[0]["id"]
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "옵션 묶음이 열리지 않음")
        need(wait_for(lambda: pg.evaluate("document.querySelector('#detail-stt-preprocess').value") == "denoise" and
                      stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "옵션 없는 녹취의 묶음이 전체 기본값 denoise 로 채워지지 않음")

        pg.select_option("#detail-stt-preprocess", "")
        start = len(bodies)
        pg.click("#detail-stt-run")
        need(wait_for(lambda: len(bodies) > start, 10, pg=pg), "기본 옵션 재시도 POST 가 나가지 않음")
        need(json.loads(bodies[start]) == {"options": {}},
             "전부 기본인 재시도 본문이 {} 가 아님: %r" % bodies[start])
        got = api_get(b, "/api/recordings/" + rid)
        need(got.get("stt_options") is None,
             "기본만 실행했는데 녹취별 stt_options 가 남음: %r" % got.get("stt_options"))
        c.close()
    check("54 옵션 없는 녹취는 전체 기본값으로 열리고, 기본 실행 뒤 stt_options 없음", t54)


    def t55():
        # 재시도 400 의 토스트는 고정 문구가 아니라 서버가 준 error 글(F5)
        b, _ = new_server("d55")
        c = new_ctx()
        pg = c.new_page()
        server_text = "재시도 거절 - 서버가 준 문구"

        def retry_400(route):
            req = route.request
            url = req.url.split("?")[0]
            if req.method == "POST" and "/api/recordings/" in url and url.endswith("/retry"):
                route.fulfill(status=400, content_type="application/json",
                              body=json.dumps({"error": server_text}, ensure_ascii=False))
            else:
                route.continue_()

        pg.route("**/api/recordings/*/retry", retry_400)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "받아쓰기가 끝나지 않음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "옵션 묶음이 열리지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "옵션 묶음의 실행 단추가 풀리지 않음")
        pg.click("#detail-stt-run")
        need(wait_for(lambda: pg.is_visible("#toast") and server_text in pg.inner_text("#toast"), 5, pg=pg),
             "재시도 400 뒤 서버 글이 토스트로 보이지 않음: %r" % pg.inner_text("#toast"))
        pg.unroute("**/api/recordings/*/retry", retry_400)
        c.close()
    check("55 재시도 400 뒤 서버 error 글을 토스트로 보임", t55)


    def t56():
        counter = tmp / "t56-count.txt"
        stt_code = ("import pathlib, sys\n"
                    "p = pathlib.Path(sys.argv[1])\n"
                    "n = int(p.read_text(encoding='utf-8')) if p.exists() else 0\n"
                    "p.write_text(str(n + 1), encoding='utf-8')\n"
                    "print('글 ' + chr(ord('A') + n))\n")
        stt_cmd = "%s -c %s %s" % (sys.executable, shlex.quote(stt_code), shlex.quote(str(counter)))
        b, _ = new_server("d56", stt_cmd=stt_cmd)
        c = new_ctx(timezone_id="Asia/Seoul")
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "받아쓰기가 끝나지 않음")
        rid = server_items(b)[0]["id"]
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 첫 읽기가 끝나지 않음")
        need(wait_for(lambda: pg.inner_text("#transcript").strip() == "글 A", 20, pg=pg),
             "첫 받아쓰기가 글 A 가 아님: %r" % pg.inner_text("#transcript"))

        for expected in ("글 B", "글 C"):
            pg.click("#detail-retry")
            need(wait_for(lambda exp=expected: pg.inner_text("#transcript").strip() == exp, 30, pg=pg),
                 "다시 받아쓴 글이 %s 가 아님: %r" % (expected, pg.inner_text("#transcript")))

        need(wait_for(lambda: pg.is_visible("#detail-prev") and
                      pg.inner_text("#detail-prev-summary").strip() == "지난 글 2벌", 10, pg=pg),
             "#detail-prev 요약이 '지난 글 2벌' 이 아님: %r" % pg.inner_text("#detail-prev-summary"))
        got = api_get(b, "/api/recordings/" + rid)
        prevs = got.get("prev_transcripts")
        need(got["transcript"] == "글 C" and isinstance(prevs, list) and
             [p["text"] for p in prevs] == ["글 B", "글 A"],
             "서버의 새 글·지난 글 벌 순서가 다름: %r / %r" % (got["transcript"], prevs))

        injected = [
            {"text": "글 B", "stt_used": {"preprocess": "denoise", "speakers": 2},
             "at": "2026-11-20T10:15:00+09:00"},
            {"text": "글 A", "stt_used": {"preprocess": "none", "auto": True},
             "at": "2026-11-20T09:30:00+09:00"},
        ]
        seen = {"n": 0}

        def inject(route):
            req = route.request
            url = req.url.split("?")[0]
            if req.method != "GET" or "/audio" in url or not re.search(r"/api/recordings/[^/]+$", url):
                route.continue_()
                return
            data = api_get(b, "/api/recordings/" + rid)
            data["prev_transcripts"] = injected
            data["autotag"] = "pending"
            seen["n"] += 1
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(data, ensure_ascii=False))

        pg.route("**/api/recordings/*", inject)
        pg.reload()
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "새로고침 뒤 목록 항목이 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: detail_ready(pg) and
                      pg.inner_text("#detail-prev-summary").strip() == "지난 글 2벌", 10, pg=pg),
             "주입한 상세 응답의 지난 글 요약이 '지난 글 2벌' 이 아님: %r" % pg.inner_text("#detail-prev-summary"))
        pg.click("#detail-prev summary")
        items = pg.locator("#detail-prev-list .prev-item")
        need(wait_for(lambda: items.count() == 2, 5, pg=pg), "지난 글 벌이 2개가 아님")
        pg.locator("#detail-prev-list .prev-item summary").nth(0).click()
        pg.locator("#detail-prev-list .prev-item summary").nth(1).click()
        pre = pg.locator("#detail-prev-list .prev-item pre.transcript")
        need(wait_for(lambda: pre.nth(0).is_visible() and pre.nth(1).is_visible(), 5, pg=pg),
             "지난 글 벌을 펼쳐도 글칸이 보이지 않음")
        need(pre.nth(0).inner_text().strip() == "글 B" and pre.nth(1).inner_text().strip() == "글 A",
             "지난 글 벌 순서/글자가 다름: %r / %r" % (pre.nth(0).inner_text(), pre.nth(1).inner_text()))
        summaries = pg.locator("#detail-prev-list .prev-item summary")
        s0, s1 = summaries.nth(0).inner_text(), summaries.nth(1).inner_text()
        need("받아쓴 때 2026-11-20 10:15" in s0 and "전처리 denoise" in s0 and "화자 2" in s0,
             "첫 지난 글 벌 요약에 받아쓴 때/옵션이 없음: %r" % s0)
        need("받아쓴 때 2026-11-20 09:30" in s1 and "전처리 none" in s1 and "자동 추정 켬" in s1,
             "둘째 지난 글 벌 요약에 받아쓴 때/옵션이 없음: %r" % s1)

        baseline = seen["n"]
        need(wait_for(lambda: seen["n"] >= baseline + 2, 10, pg=pg),
             "지난 글 상세가 폴링으로 두 번 다시 읽히지 않음 (%d)" % (seen["n"] - baseline))
        open_states = pg.evaluate("Array.from(document.querySelectorAll('#detail-prev-list .prev-item details')).map(d => d.open)")
        need(open_states == [True, True], "폴링 뒤 펼친 지난 글 벌이 접힘: %r" % open_states)

        pg.set_viewport_size({"width": 320, "height": 800})
        pg.wait_for_timeout(100)
        rects = pg.evaluate("""() => {
            var vw = window.innerWidth;
            var ol = document.querySelector('#detail-prev-list');
            var box = document.querySelector('#detail-prev').getBoundingClientRect();
            var items = Array.from(document.querySelectorAll('#detail-prev-list .prev-item')).map(function (li) {
                var r = li.getBoundingClientRect();
                return {left: r.left, right: r.right, scrollW: li.scrollWidth, clientW: li.clientWidth};
            });
            return {vw: vw, boxLeft: box.left, boxRight: box.right,
                    listScroll: ol.scrollWidth, listClient: ol.clientWidth, items: items};
        }""")
        need(rects["boxLeft"] >= -0.5 and rects["boxRight"] <= rects["vw"] + 0.5,
             "320px 지난 글 묶음이 화면 밖으로 넘침: %r" % rects)
        need(rects["listScroll"] <= rects["listClient"] + 1,
             "320px 지난 글 목록이 가로로 넘침: %d > %d" % (rects["listScroll"], rects["listClient"]))
        for item in rects["items"]:
            need(item["left"] >= -0.5 and item["right"] <= rects["vw"] + 0.5,
                 "320px 지난 글 벌이 화면 밖으로 넘침: %r" % item)
            need(item["scrollW"] <= item["clientW"] + 1,
                 "320px 지난 글 벌 안이 가로로 넘침: %r" % item)

        pg.unroute("**/api/recordings/*", inject)
        c.close()
    check("56 A→B→C 지난 글 2벌 순서·주입 옵션·폴링 뒤 펼침 유지·320px 넘침 없음", t56)


    def t57():
        b, d = new_server("d57")
        c = new_ctx(timezone_id="Asia/Seoul")
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        rec_cycle(pg)
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 20, pg=pg), "목록 항목이 생기지 않음")
        need(wait_for(lambda: pg.locator("#list .rec-item .status").first.inner_text().strip() == "완료", 20, pg=pg),
             "받아쓰기가 끝나지 않음")
        rid = server_items(b)[0]["id"]
        need(wait_for(lambda: api_get(b, "/api/recordings/" + rid).get("autotag") in ("done", "failed"), 10, pg=pg),
             "자동 태그가 끝나지 않아 메타를 고치기 전에 상태가 흔들림")

        transcript_paths = list(d.glob("transcripts/*/%s.txt" % rid))
        need(len(transcript_paths) == 1, "녹취 글 파일이 하나가 아님: %r" % transcript_paths)
        txt = transcript_paths[0]
        (txt.parent / (rid + ".prev.txt")).write_text("옛 글", encoding="utf-8")
        meta_path = d / "meta" / (rid + ".json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["prev_stt_used"] = {"preprocess": "denoise", "at": "2026-11-20T09:15:00+09:00"}
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail-edit") and detail_ready(pg), 10, pg=pg),
             "상세 편집 칸이 보이지 않거나 읽기가 끝나지 않음")
        need(wait_for(lambda: pg.is_visible("#detail-prev") and
                      pg.inner_text("#detail-prev-summary").strip() == "지난 글 1벌", 10, pg=pg),
             "#detail-prev 요약이 '지난 글 1벌' 이 아님: %r" % pg.inner_text("#detail-prev-summary"))
        pg.click("#detail-prev summary")
        need(wait_for(lambda: pg.locator("#detail-prev-list .prev-item").count() == 1, 5, pg=pg),
             "옛 .prev.txt 가 지난 글 벌로 보이지 않음")
        pg.locator("#detail-prev-list .prev-item summary").first.click()
        prev_text = pg.locator("#detail-prev-list .prev-item pre.transcript").first
        need(wait_for(lambda: prev_text.is_visible(), 5, pg=pg), "옛 지난 글 벌을 펼쳐도 글칸이 보이지 않음")
        need(prev_text.inner_text().strip() == "옛 글",
             "옛 .prev.txt 글자가 다름: %r" % prev_text.inner_text())
        summary = pg.locator("#detail-prev-list .prev-item summary").first.inner_text()
        need("전처리 denoise" in summary and "받아쓴 때 2026-11-20 09:15" in summary,
             "옛 지난 글 벌 요약에 옵션/받아쓴 때가 없음: %r" % summary)
        got = api_get(b, "/api/recordings/" + rid)
        need(isinstance(got.get("prev_transcripts"), list) and len(got["prev_transcripts"]) == 1 and
             got["prev_transcripts"][0]["text"] == "옛 글" and
             got["prev_transcripts"][0]["stt_used"]["preprocess"] == "denoise",
             "서버 응답의 옛 지난 글 벌이 다름: %r" % got.get("prev_transcripts"))
        c.close()
    check("57 옛 .prev.txt·prev_stt_used 가 지난 글 1벌로 보임", t57)


    def t58():
        # 격리 출처(VoxQueue/IndexedDB 없음): 설정 기본값 묶음과 상세 옵션 단추가 보이면 안 된다(F4).
        b, _ = new_server("d58")
        upload_rec(b, "t58-rec")
        c = new_ctx()
        pg = c.new_page()
        stub = """
        window.VoxQueue = {
          supported: function () { return { indexedDB: false }; },
          pending: function () { return Promise.resolve([]); },
          draftRecover: function () { return Promise.resolve(0); },
          flush: function () { return Promise.resolve(); },
          retry: function () { return Promise.resolve(); },
          remove: function () { return Promise.resolve(); },
          getConfig: function () { return Promise.resolve({ token: '', autoRecord: false, saveLocation: true }); },
          setConfig: function () { return Promise.resolve(); },
          onchange: function () {},
          onrecover: function () {}
        };
        """
        pg.route("**/queue.js", lambda route: route.fulfill(
            status=200, content_type="application/javascript", body=stub))
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#settings"), 5, pg=pg), "설정 칸이 열리지 않음")
        need(not pg.is_visible("#stt-defaults"), "격리 출처에서 #stt-defaults 가 보임")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "상세가 준비되지 않음")
        need(not pg.is_visible("#detail-retry-opts"),
             "격리 출처에서 '옵션 바꿔 다시 받아쓰기' 단추가 보임")
        need(not pg.is_visible("#detail-stt"), "격리 출처에서 상세 옵션 칸이 보임")
        c.close()
    check("58 격리 출처에서 설정 기본값·상세 옵션 단추 안 보임", t58)


    def t59():
        # 재시도 400 서버 글에 <img ...> 가 있어도 토스트는 글자로 보이고 img 가 생기지 않는다(F6).
        b, _ = new_server("d59")
        upload_rec(b, "t59-rec")
        c = new_ctx()
        pg = c.new_page()
        payload = "<img src=x onerror=alert(1)>"
        pg.route("**/api/recordings/*/retry", lambda route: route.fulfill(
            status=400, content_type="application/json",
            body=json.dumps({"error": payload}, ensure_ascii=False)))
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "상세가 준비되지 않음")
        pg.click("#detail-retry")
        need(wait_for(lambda: pg.is_visible("#toast") and payload in pg.inner_text("#toast"), 5, pg=pg),
             "토스트에 서버 글이 글자로 보이지 않음: %r" % pg.inner_text("#toast"))
        need(pg.locator("#toast img").count() == 0, "토스트 안에 img 요소가 생김")
        need(pg.evaluate("document.querySelector('#toast').innerHTML").find("&lt;img") >= 0,
             "토스트가 글자가 아니라 HTML 로 들어감")
        c.close()
    check("59 재시도 400 의 <img> 서버 글: 토스트 글자·img 요소 없음", t59)


    def t60():
        # 지난 글 본문이 <img ...> 꼴이어도 펼친 .prev-item 에 글자로 보이고 img 가 없다(W2).
        b, _ = new_server("d60")
        rid = upload_rec(b, "t60-rec")
        c = new_ctx()
        pg = c.new_page()
        payload = "<img src=x onerror=alert(2)>지난 글"

        def inject(route):
            req = route.request
            url = req.url.split("?")[0]
            if req.method != "GET" or "/audio" in url or not re.search(r"/api/recordings/[^/]+$", url):
                route.continue_()
                return
            data = api_get(b, "/api/recordings/" + rid)
            data["prev_transcripts"] = [{
                "text": payload,
                "at": "2026-11-20T09:15:00+09:00",
                "stt_used": {},
            }]
            data["autotag"] = "done"
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(data, ensure_ascii=False))

        pg.route("**/api/recordings/*", inject)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "상세가 준비되지 않음")
        pg.click("#detail-prev summary")
        need(wait_for(lambda: pg.locator("#detail-prev-list .prev-item").count() == 1, 5, pg=pg),
             "지난 글 벌이 보이지 않음")
        pg.locator("#detail-prev-list .prev-item summary").first.click()
        pre = pg.locator("#detail-prev-list .prev-item pre.transcript").first
        need(wait_for(lambda: pre.is_visible(), 5, pg=pg), "지난 글 벌을 펼쳐도 글칸이 보이지 않음")
        need(pre.inner_text().strip() == payload, "지난 글 본문이 글자로 보이지 않음: %r" % pre.inner_text())
        need(pg.locator("#detail-prev-list .prev-item img").count() == 0,
             "지난 글 안에 img 요소가 생김")
        c.close()
    check("60 지난 글 <img> 본문: 글자로 보이고 img 요소 없음", t60)


    def t61():
        # 상세 옵션 칸 빈 값 이름·설정 칸 '서버 기본'·'합치지 않음' 안내(N13).
        b, _ = new_server("d61")
        rid_plain = upload_rec(b, "t61-plain")
        rid_opts = upload_rec(b, "t61-opts", options={"num_speakers": 2})
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults-fields"), 10, pg=pg),
             "설정 칸의 옵션 묶음이 보이지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "설정 칸의 입력 칸·저장 단추가 풀리지 않음")
        pre_label = pg.evaluate("document.querySelector('#stt-defaults-preprocess').selectedOptions[0].textContent")
        need("서버 기본" in pre_label, "설정 전처리 빈 값 이름이 '서버 기본' 이 아님: %r" % pre_label)
        for key in ("auto", "review"):
            label = pg.evaluate("document.querySelector('#stt-defaults-%s').selectedOptions[0].textContent" % key)
            need(label == "서버 기본", "설정 %s 빈 값 이름이 '서버 기본' 이 아님: %r" % (key, label))
        pg.click("#settings-btn")

        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록 항목이 2개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_plain).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "옵션 없는 녹음 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "상세 옵션 묶음이 열리지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "상세 옵션 묶음의 입력 칸·실행 단추가 풀리지 않음")
        labels_plain = pg.evaluate("""() => ['preprocess', 'auto', 'review'].map(function (k) {
            return document.querySelector('#detail-stt-' + k).selectedOptions[0].textContent;
        })""")
        need(labels_plain == ["기본(앱 설정 따름)"] * 3,
             "옵션 없는 녹음의 빈 값 이름이 '기본(앱 설정 따름)' 이 아님: %r" % labels_plain)
        need("합치지 않음" in pg.inner_text("#detail-stt"), "'합치지 않음' 안내가 없음")

        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_opts).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "옵션 있는 녹음 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "상세 옵션 묶음이 열리지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "상세 옵션 묶음의 입력 칸·실행 단추가 풀리지 않음")
        labels_opts = pg.evaluate("""() => ['preprocess', 'auto', 'review'].map(function (k) {
            return document.querySelector('#detail-stt-' + k).selectedOptions[0].textContent;
        })""")
        need(labels_opts == ["기본(서버 기본)"] * 3,
             "옵션 있는 녹음의 빈 값 이름이 '기본(서버 기본)' 이 아님: %r" % labels_opts)
        need("합치지 않음" in pg.inner_text("#detail-stt"), "'합치지 않음' 안내가 없음")
        c.close()
    check("61 상세 옵션 빈 값 이름·설정 '서버 기본'·'합치지 않음' 안내", t61)


    def t62():
        # 설정 칸을 닫았다 여는 사이 다른 기기가 기본값을 바꾸면 다시 열 때 새 값으로 채운다(N6).
        b, _ = new_server("d62")
        c = new_ctx()
        pg = c.new_page()
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults-fields"), 10, pg=pg),
             "설정 칸의 옵션 묶음이 보이지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "설정 칸의 입력 칸·저장 단추가 풀리지 않음")
        pg.wait_for_timeout(200)
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "denoise", "num_speakers": 3}})
        pg.click("#settings-btn")
        need(not pg.is_visible("#settings"), "설정 칸이 닫히지 않음")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults-fields"), 10, pg=pg),
             "설정 칸을 다시 열어도 옵션 묶음이 보이지 않음")
        def reopened():
            return (stt_fields_ready(pg, "stt-defaults") and
                    pg.evaluate("document.querySelector('#stt-defaults-preprocess').value") == "denoise" and
                    pg.evaluate("document.querySelector('#stt-defaults-speakers').value") == "3")
        need(wait_for(reopened, 10, pg=pg),
             "다시 열 때 새 기본값이 아님: %r / %r" % (
                 pg.evaluate("document.querySelector('#stt-defaults-preprocess').value"),
                 pg.evaluate("document.querySelector('#stt-defaults-speakers').value")))
        c.close()
    check("62 설정 칸 다시 열기: 다른 기기 PUT 새 값 반영", t62)


    def t63():
        # 실패 + chars 상세 줄은 '이전 글 그대로 N자', 까닭 문구, '다시 받아쓰기' 단추(N8·N10).
        b, _ = new_server("d63")
        rid = upload_rec(b, "t63-rec")
        c = new_ctx()
        pg = c.new_page()
        empty_error = ("받아 적은 글이 비었습니다 - 소리가 없거나 말소리가 잡히지 않았을 수 있습니다"
                       "(옵션을 바꿔 다시 받아써 볼 수 있음)")

        def inject(route):
            req = route.request
            url = req.url.split("?")[0]
            if req.method != "GET" or "/audio" in url or not re.search(r"/api/recordings/[^/]+$", url):
                route.continue_()
                return
            data = api_get(b, "/api/recordings/" + rid)
            data.update({
                "status": "failed",
                "chars": 42,
                "error": empty_error,
                "transcript": "이전 글",
                "autotag": "done",
            })
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(data, ensure_ascii=False))

        pg.route("**/api/recordings/*", inject)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "상세가 준비되지 않음")
        meta = pg.inner_text("#detail-meta")
        need("이전 글 그대로 42자" in meta, "실패 줄에 '이전 글 그대로 42자' 가 없음: %r" % meta)
        need("소리가 없거나" in meta, "실패 줄에 '소리가 없거나' 문구가 없음: %r" % meta)
        need(pg.is_visible("#detail-retry"), "'다시 받아쓰기' 단추가 보이지 않음")
        c.close()
    check("63 실패+chars 상세 줄: 이전 글 그대로·까닭 문구·다시 받아쓰기", t63)


    def t64():
        # 받아쓰는 중 폴링은 ?prev=0, 끝나면 ?prev=0 없는 읽기 뒤 지난 글 묶음이 보인다(N5).
        b, _ = new_server("d64")
        rid = upload_rec(b, "d64-rec")
        c = new_ctx()
        pg = c.new_page()
        urls = []
        phase = {"n": 0}
        poll_n = {"n": 0}
        prev = [{"text": "옛 글", "at": "2026-11-20T09:15:00+09:00", "stt_used": {}}]

        def inject(route):
            req = route.request
            url = req.url
            path = url.split("?")[0]
            if req.method != "GET" or "/audio" in path or not re.search(r"/api/recordings/[^/]+$", path):
                route.continue_()
                return
            urls.append(url)
            data = api_get(b, "/api/recordings/" + rid)
            if "prev=0" in url:
                poll_n["n"] += 1
                data.update({
                    "status": "transcribing",
                    "transcript": "",
                    "autotag": "pending",
                })
                # 실제 서버의 ?prev=0 응답에는 prev_transcripts 키가 없다(R53-N3).
                data.pop("prev_transcripts", None)
                if poll_n["n"] > 1:
                    data.update({
                        "status": "done",
                        "transcript": "새 글",
                        "autotag": "done",
                    })
            elif phase["n"] == 0:
                phase["n"] = 1
                data.update({
                    "status": "transcribing",
                    "transcript": "",
                    "autotag": "pending",
                    "prev_transcripts": prev,
                })
            else:
                data.update({
                    "status": "done",
                    "transcript": "새 글",
                    "autotag": "done",
                    "prev_transcripts": prev,
                })
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(data, ensure_ascii=False))
        pg.route("**/api/recordings/*", inject)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 없음")
        pg.locator("#list .rec-item .rec-main").first.click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "상세가 준비되지 않음")
        need(wait_for(lambda: pg.is_visible("#detail-prev") and
                      pg.inner_text("#detail-prev-summary").strip() == "지난 글 1벌", 10, pg=pg),
             "첫 읽기의 지난 글 묶음이 보이지 않음: %r" % pg.inner_text("#detail-prev-summary"))
        pg.click("#detail-prev summary")
        need(wait_for(lambda: pg.evaluate("document.querySelector('#detail-prev').open"), 5, pg=pg),
             "지난 글 묶음이 펼쳐지지 않음")
        pg.locator("#detail-prev-list .prev-item summary").first.click()
        prev_pre = pg.locator("#detail-prev-list .prev-item pre.transcript").first
        need(wait_for(lambda: prev_pre.is_visible() and prev_pre.inner_text().strip() == "옛 글", 5, pg=pg),
             "지난 글 벌 본문이 보이지 않거나 다름: %r" % prev_pre.inner_text())
        need(wait_for(lambda: any("prev=0" in u for u in urls), 10, pg=pg),
             "받아쓰는 중 폴링 요청이 ?prev=0 이 아님: %r" % urls)
        pg.wait_for_timeout(200)
        need(pg.is_visible("#detail-prev") and
             pg.evaluate("document.querySelector('#detail-prev').open") and
             pg.locator("#detail-prev-list .prev-item details").first.get_attribute("open") is not None and
             prev_pre.is_visible() and prev_pre.inner_text().strip() == "옛 글",
             "키 없는 ?prev=0 응답 뒤 펼친 지난 글 묶음이 바뀜")
        first_omit = next(i for i, u in enumerate(urls) if "prev=0" in u)
        need(wait_for(lambda: any("prev=0" not in u for u in urls[first_omit + 1:]), 10, pg=pg),
             "끝난 뒤 ?prev=0 없는 읽기가 없음: %r" % urls)
        need(wait_for(lambda: pg.is_visible("#detail-prev") and
                      pg.inner_text("#detail-prev-summary").strip() == "지난 글 1벌", 10, pg=pg),
             "끝난 뒤 지난 글 묶음이 보이지 않음: %r" % pg.inner_text("#detail-prev-summary"))
        c.close()
    check("64 받아쓰는 중 폴링 ?prev=0(키 없음), 펼친 지난 글 유지·끝난 뒤 묶음", t64)


    def t65():
        # 옵션 재시도 응답 전에 다른 녹음으로 옮기면 새 녹음의 옵션 칸을 닫지 않는다(N7).
        b, _ = new_server("d65")
        rid_a = upload_rec(b, "t65-a")
        rid_b = upload_rec(b, "t65-b")
        c = new_ctx()
        pg = c.new_page()
        retry_responses = {"n": 0}

        def slow_retry(route):
            time.sleep(0.6)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        def track_retry(resp):
            url = resp.url.split("?")[0]
            if resp.request.method == "POST" and "/api/recordings/" in url and url.endswith("/retry"):
                retry_responses["n"] += 1

        pg.route("**/api/recordings/*/retry", slow_retry)
        pg.on("response", track_retry)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록 항목이 2개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "A 옵션 칸이 열리지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "A 옵션 칸의 입력 칸·실행 단추가 풀리지 않음")
        # 같은 JS 작업 안에서 재시도를 보내고 곧바로 B 로 옮긴다. 응답은 route 가 늦게 준다.
        pg.evaluate("""() => {
            document.querySelector('#detail-stt-run').click();
            document.querySelector("#list .rec-item[data-id='%s'] .rec-main").click();
        }""" % rid_b)
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "B 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "B 옵션 칸이 열리지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "B 옵션 칸의 입력 칸·실행 단추가 풀리지 않음")
        need(wait_for(lambda: retry_responses["n"] >= 1, 10, pg=pg),
             "A 옵션 재시도 응답이 오지 않음")
        need(pg.is_visible("#detail-stt"), "A 재시도 응답 뒤 B 옵션 칸이 닫힘")
        need(pg.evaluate("document.querySelector('#detail-retry-opts').getAttribute('aria-expanded')") == "true",
             "B 옵션 단추가 접힘 상태로 바뀜")
        c.close()
    check("65 재시도 응답 전 녹음 이동: 새 녹음 옵션 칸 유지", t65)


    def t66():
        # 설정 칸의 기본값 GET 을 늦춰, 응답 전 입력·저장 단추가 잠기고 응답 뒤 고른 값이 PUT 본문에 실리는지 본다.
        b, _ = new_server("d66")
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        put_bodies = []

        def track_put(req):
            if req.method == "PUT" and req.url.split("?")[0].endswith("/api/stt-options"):
                put_bodies.append(req.post_data)

        pg.on("request", track_put)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#settings-btn")
        locked = pg.evaluate("""() => ({
            visible: !document.querySelector('#settings').hidden && !document.querySelector('#stt-defaults').hidden &&
                     !document.querySelector('#stt-defaults-fields').hidden,
            fields: ['preprocess', 'speakers', 'context', 'auto', 'review'].map(function (k) {
                return document.querySelector('#stt-defaults-' + k).disabled;
            }),
            save: document.querySelector('#stt-defaults-save').disabled,
            state: document.querySelector('#stt-defaults-state').textContent
        })""")
        need(locked["visible"], "설정 칸의 옵션 묶음이 보이지 않음: %r" % locked)
        need(all(locked["fields"]), "기본값 응답 전 설정 입력 칸이 잠기지 않음: %r" % locked)
        need(locked["save"], "기본값 응답 전 설정 저장 단추가 잠기지 않음: %r" % locked)
        need(locked["state"] == "불러오는 중…", "기본값 응답 전 설정 상태가 '불러오는 중…' 이 아님: %r" % locked["state"])
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "설정 칸의 기본값 GET 응답이 쥐어지지 않음")
        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 설정 기본값 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchDone"), 5, pg=pg),
             "놓은 설정 기본값 응답이 도착하지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 8, pg=pg),
             "기본값 응답 뒤 설정 입력 칸·저장 단추가 풀리지 않음")
        pg.select_option("#stt-defaults-preprocess", "denoise")
        pg.fill("#stt-defaults-speakers", "2")
        pg.click("#stt-defaults-save")
        need(wait_for(lambda: len(put_bodies) >= 1, 10, pg=pg),
             "설정 저장 PUT 가 나가지 않음")
        need(json.loads(put_bodies[0]) == {"options": {"preprocess": "denoise", "num_speakers": 2}},
             "풀린 뒤 고른 값이 설정 저장 본문에 그대로가 아님: %r" % put_bodies[0])
        need(wait_for(lambda: api_get(b, "/api/stt-options")["options"] ==
                      {"preprocess": "denoise", "num_speakers": 2}, 10, pg=pg),
             "저장한 기본값이 서버 GET 에 없음: %r" % api_get(b, "/api/stt-options")["options"])
        c.close()
    check("66 설정 칸 늦은 기본값 응답: 입력·저장 잠김, 풀린 뒤 고른 값 저장", t66)


    def t67():
        # 옵션 없는 A 의 기본값 GET 응답을 쥔 채 옵션 있는 B 로 옮겨 같은 칸을 연다(R53-N6).
        b, _ = new_server("d67")
        rid_a = upload_rec(b, "t67-a")
        rid_b = upload_rec(b, "t67-b", options={"preprocess": "denoise"})
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록 항목이 2개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "A 기본값 GET 응답이 쥐어지지 않음")
        need(not pg.is_enabled("#detail-stt-preprocess") and not pg.is_enabled("#detail-stt-run"),
             "A 기본값 응답 전 칸·실행 단추가 잠기지 않음")
        need(pg.inner_text("#detail-stt-state") == "불러오는 중…",
             "A 기본값 응답 전 상태가 '불러오는 중…' 이 아님: %r" % pg.inner_text("#detail-stt-state"))
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_b).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "B 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt"), 5, pg=pg), "B 옵션 묶음이 열리지 않음")
        keys = ("preprocess", "speakers", "context", "auto", "review")
        need(all(pg.is_enabled("#detail-stt-" + k) for k in keys), "B 입력 칸이 enabled 가 아님")
        need(pg.is_enabled("#detail-stt-run"), "B 실행 단추가 enabled 가 아님")
        need(pg.input_value("#detail-stt-preprocess") == "denoise",
             "B 의 옵션 값이 보이지 않음: %r" % pg.input_value("#detail-stt-preprocess"))
        need(pg.inner_text("#detail-stt-state").strip() == "",
             "B 상태 글에 이유 없이 글이 남음: %r" % pg.inner_text("#detail-stt-state"))

        def snapshot():
            return {
                "fields": [pg.is_enabled("#detail-stt-" + k) for k in keys],
                "run": pg.is_enabled("#detail-stt-run"),
                "values": [pg.input_value("#detail-stt-" + k) for k in keys],
                "state": pg.inner_text("#detail-stt-state"),
            }

        before = snapshot()
        # 이동이 A 의 읽기를 끊었으므로, 놓아도 그 요청은 AbortError 로 끝난다(응답이 오지 않는다).
        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 A 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchAborted"), 5, pg=pg),
             "놓은 A 읽기가 끊긴 것으로 기록되지 않음")
        pg.wait_for_timeout(300)
        after = snapshot()
        need(before == after, "A 응답을 놓은 뒤 B 칸이 바뀜: %r -> %r" % (before, after))
        need(not pg.evaluate("window.__sttOptionsHeld()"), "A 응답이 아직 쥐어져 있음")
        c.close()
    check("67 기본값 응답을 쥔 채 녹음 이동: B 칸 유지·A 읽기 끊김", t67)


    def t68():
        # 기본값 GET 이 500 으로 실패하면 상세·설정 칸이 잠긴 채 남지 않고 실패 글이 보인다(N8).
        b, _ = new_server("d68")
        rid_a = upload_rec(b, "t68-a")
        c = new_ctx()
        pg = c.new_page()

        def fail_options(route):
            req = route.request
            if req.method == "GET" and req.url.split("?")[0].endswith("/api/stt-options"):
                route.fulfill(status=500, content_type="application/json", body=json.dumps({"error": "boom"}))
            else:
                route.continue_()

        pg.route("**/api/stt-options", fail_options)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 1개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        keys = ("preprocess", "speakers", "context", "auto", "review")

        def detail_failure_ready():
            try:
                return (pg.is_visible("#detail-stt") and
                        all(pg.is_enabled("#detail-stt-" + k) for k in keys) and
                        pg.is_enabled("#detail-stt-run") and
                        pg.is_visible("#detail-stt-state") and
                        "기본값을 불러오지 못했습니다" in pg.inner_text("#detail-stt-state"))
            except Exception:  # noqa: BLE001 - 아직 없으면 아직 아님
                return False

        need(wait_for(detail_failure_ready, 10, pg=pg),
             "읽기 실패 뒤 상세 칸이 풀리지 않거나 실패 글이 없음: %r" % pg.inner_text("#detail-stt-state"))
        txt = pg.inner_text("#detail-stt-state").strip()
        need(txt.startswith("기본값을 불러오지 못했습니다"), "상세 실패 글 첫 줄이 아님: %r" % txt)

        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults-note") and
                      "받아쓰기 옵션을 불러오지 못했습니다" in pg.inner_text("#stt-defaults-note"), 10, pg=pg),
             "설정 기본값 읽기 실패 글이 보이지 않음: %r" % pg.inner_text("#stt-defaults-note"))
        need(all(pg.is_enabled("#stt-defaults-" + k) for k in keys), "설정 입력 칸이 잠긴 채 남음")
        need(pg.is_enabled("#stt-defaults-save"), "설정 저장 단추가 잠긴 채 남음")
        c.close()
    check("68 기본값 읽기 실패: 칸 풀림·실패 글", t68)


    def t69():
        # GET 을 쥔 채 page.clock 으로 15초를 넘기면 시간 제한이 칸을 풀고 시간 초과 글을 보인다(R53-N6).
        b, _ = new_server("d69")
        rid_a = upload_rec(b, "t69-a")
        c = new_ctx()
        pg = c.new_page()
        pg.clock.install()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 1개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "A 기본값 GET 응답이 쥐어지지 않음")
        keys = ("preprocess", "speakers", "context", "auto", "review")
        need(not pg.is_enabled("#detail-stt-preprocess") and not pg.is_enabled("#detail-stt-run"),
             "시간이 지나기 전 칸·실행 단추가 잠기지 않음")
        pg.clock.fast_forward(15000)
        need(wait_for(lambda: all(pg.is_enabled("#detail-stt-" + k) for k in keys) and
                      pg.is_enabled("#detail-stt-run") and
                      "시간이 지났습니다" in pg.inner_text("#detail-stt-state"), 5, pg=pg),
             "15초 뒤 칸이 풀리지 않거나 시간 초과 글이 없음: %r" % pg.inner_text("#detail-stt-state"))
        need("기본값을 불러오지 못했습니다" in pg.inner_text("#detail-stt-state"),
             "시간 초과 실패 글 첫 줄이 아님: %r" % pg.inner_text("#detail-stt-state"))
        pg.evaluate("window.__releaseSttOptions()")
        pg.wait_for_timeout(200)
        need("시간이 지났습니다" in pg.inner_text("#detail-stt-state"),
             "늦게 온 응답이 시간 초과 글을 지움: %r" % pg.inner_text("#detail-stt-state"))
        c.close()
    check("69 기본값 15초 시간 제한: 칸 풀림·시간 초과 글", t69)


    def t70():
        # A 의 옵션 재시도 POST 응답을 쥔 채 옵션 없는 B 칸을 열어, A 응답이 B 의 상태 글·잠금을 건드리지 않는지 본다(N12).
        b, _ = new_server("d70")
        rid_a = upload_rec(b, "t70-a")
        rid_b = upload_rec(b, "t70-b")
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.add_init_script(RETRY_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록 항목이 2개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "A 옵션 칸의 입력 칸·실행 단추가 풀리지 않음")
        pg.evaluate("window.__holdNextRetry()")
        pg.click("#detail-stt-run")
        need(wait_for(lambda: pg.evaluate("window.__retryHeld()"), 5, pg=pg),
             "A 옵션 재시도 POST 응답이 쥐어지지 않음")

        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_b).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "B 상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt") and pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "B 기본값 GET 응답이 쥐어지지 않거나 칸이 열리지 않음")
        keys = ("preprocess", "speakers", "context", "auto", "review")
        need(not all(pg.is_enabled("#detail-stt-" + k) for k in keys) and not pg.is_enabled("#detail-stt-run"),
             "B 칸이 기본값 응답 전 잠기지 않음")
        need(pg.inner_text("#detail-stt-state") == "불러오는 중…",
             "B 상태가 '불러오는 중…' 이 아님: %r" % pg.inner_text("#detail-stt-state"))

        need(pg.evaluate("window.__releaseRetry()"), "쥔 A 재시도 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedRetryDone"), 5, pg=pg),
             "놓은 A 재시도 응답이 도착하지 않음")
        pg.wait_for_timeout(200)
        need(pg.is_visible("#detail-stt"), "A 재시도 응답 뒤 B 옵션 칸이 닫힘")
        need(pg.evaluate("document.querySelector('#detail-retry-opts').getAttribute('aria-expanded')") == "true",
             "A 재시도 응답 뒤 B 옵션 단추가 접힘 상태로 바뀜")
        need(pg.inner_text("#detail-stt-state") == "불러오는 중…",
             "A 재시도 응답이 B 의 '불러오는 중…' 글을 지움: %r" % pg.inner_text("#detail-stt-state"))
        need(not all(pg.is_enabled("#detail-stt-" + k) for k in keys) and not pg.is_enabled("#detail-stt-run"),
             "A 재시도 응답이 B 칸을 풀음")

        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 B 기본값 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchDone"), 5, pg=pg),
             "놓은 B 기본값 응답이 도착하지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "B 기본값 응답 뒤 칸·실행 단추가 풀리지 않음")
        need(pg.inner_text("#detail-stt-state").strip() == "",
             "B 기본값 응답 뒤 상태 글이 남음: %r" % pg.inner_text("#detail-stt-state"))
        c.close()
    check("70 재시도 응답 쥔 채 옵션 없는 B 칸: 상태 글·잠금 유지", t70)


    def t71():
        # 설정 칸을 닫은 사이 온 기본값 응답은 칸을 채우지 않고, 다시 열면 새 값을 읽는다(N8).
        b, _ = new_server("d71")
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "denoise"}})
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults-fields") and pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "설정 기본값 GET 응답이 쥐어지지 않음")
        need(not pg.is_enabled("#stt-defaults-preprocess"), "설정 입력 칸이 기본값 응답 전 잠기지 않음")
        pg.click("#settings-btn")
        need(pg.evaluate("document.querySelector('#settings').hidden"), "설정 칸을 닫지 못함")
        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 설정 기본값 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchDone"), 5, pg=pg),
             "놓은 설정 기본값 응답이 도착하지 않음")
        pg.wait_for_timeout(200)
        need(pg.evaluate("document.querySelector('#settings').hidden"), "닫은 설정 칸이 다시 열림")
        need(pg.evaluate("document.querySelector('#stt-defaults-preprocess').value") == "",
             "닫은 사이 온 응답이 설정 칸을 채움: %r" %
             pg.evaluate("document.querySelector('#stt-defaults-preprocess').value"))

        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "none", "num_speakers": 2}})
        pg.click("#settings-btn")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults") and
                      pg.input_value("#stt-defaults-preprocess") == "none" and
                      pg.input_value("#stt-defaults-speakers") == "2", 10, pg=pg),
             "다시 열었을 때 새 기본값이 채워지지 않음: %r / %r" %
             (pg.input_value("#stt-defaults-preprocess"), pg.input_value("#stt-defaults-speakers")))
        c.close()
    check("71 설정 칸 닫은 사이 응답: 채우지 않음·다시 열면 새 값", t71)


    def t72():
        # B 칸을 열지 않고 이동만 한 뒤 A 로 돌아와 열면, 쥔 기본값 응답이 풀어 채운다(N11).
        b, _ = new_server("d72")
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "denoise"}})
        rid_a = upload_rec(b, "t72-a")
        rid_b = upload_rec(b, "t72-b")
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록 항목이 2개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "A 기본값 GET 응답이 쥐어지지 않음")
        need(not pg.is_enabled("#detail-stt-preprocess") and not pg.is_enabled("#detail-stt-run"),
             "A 칸이 기본값 응답 전 잠기지 않음")

        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_b).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "B 상세가 준비되지 않음")
        need(not pg.is_visible("#detail-stt"), "B 칸을 열지 않았는데 옵션 칸이 보임")

        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세로 돌아오지 못함")
        # 이동이 A 의 쥔 읽기를 끊었다 - 다시 열면 그 읽기를 쓰지 않고 새 GET 을 건다(N9·N11).
        need(pg.evaluate("window.__heldFetchAborted") >= 1,
             "A 로 옮길 때 쥔 기본값 읽기가 끊기지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt") and
                      pg.input_value("#detail-stt-preprocess") == "denoise", 10, pg=pg),
             "A 를 다시 열어 새로 읽은 기본값이 채워지지 않음: %r" % pg.input_value("#detail-stt-preprocess"))
        before = pg.evaluate("document.querySelector('#detail-stt-preprocess').value")
        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 A 기본값 응답을 놓지 못함")
        need(pg.evaluate("window.__releasedFetchAborted"), "쥔 A 기본값 읽기가 끊긴 것으로 기록되지 않음")
        pg.wait_for_timeout(200)
        need(pg.is_enabled("#detail-stt-preprocess") and
             pg.input_value("#detail-stt-preprocess") == before == "denoise",
             "낡은 A 응답을 놓은 뒤 칸이 바뀜: %r" % pg.input_value("#detail-stt-preprocess"))
        c.close()
    check("72 B 칸 없이 이동 뒤 A 다시 열기: 앞 읽기 끊김·새로 읽어 채워짐", t72)


    def t73():
        # 옵션 없는 B 칸이 새 기본값 GET 을 기다리는 동안 A 의 시간 초과 뒤 늦은 응답이 와도 B 를 풀지 않는다(N11).
        b, _ = new_server("d73")
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "denoise"}})
        rid_a = upload_rec(b, "t73-a")
        rid_b = upload_rec(b, "t73-b")
        c = new_ctx()
        pg = c.new_page()
        pg.clock.install()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록 항목이 2개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeldCount()") == 1, 5, pg=pg),
             "A 기본값 GET 응답이 쥐어지지 않음")
        keys = ("preprocess", "speakers", "context", "auto", "review")
        need(not pg.is_enabled("#detail-stt-preprocess") and not pg.is_enabled("#detail-stt-run"),
             "A 칸이 기본값 응답 전 잠기지 않음")
        pg.clock.fast_forward(15000)
        need(wait_for(lambda: all(pg.is_enabled("#detail-stt-" + k) for k in keys) and
                      pg.is_enabled("#detail-stt-run") and
                      "시간이 지났습니다" in pg.inner_text("#detail-stt-state"), 5, pg=pg),
             "A 시간 제한 뒤 칸이 풀리지 않음: %r" % pg.inner_text("#detail-stt-state"))

        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_b).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "B 상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeldCount()") == 2, 5, pg=pg),
             "B 기본값 GET 응답이 쥐어지지 않음")
        need(not all(pg.is_enabled("#detail-stt-" + k) for k in keys) and not pg.is_enabled("#detail-stt-run"),
             "B 칸이 기본값 응답 전 잠기지 않음")
        need(pg.inner_text("#detail-stt-state") == "불러오는 중…",
             "B 상태가 '불러오는 중…' 이 아님: %r" % pg.inner_text("#detail-stt-state"))

        need(pg.evaluate("window.__releaseSttOptions(0)"), "쥔 A 늦은 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchCount") >= 1, 5, pg=pg),
             "놓은 A 늦은 응답이 도착하지 않음")
        pg.wait_for_timeout(200)
        need(not all(pg.is_enabled("#detail-stt-" + k) for k in keys) and not pg.is_enabled("#detail-stt-run"),
             "A 의 늦은 응답이 B 칸을 풀음")
        need(pg.inner_text("#detail-stt-state") == "불러오는 중…",
             "A 의 늦은 응답이 B 상태 글을 바꿈: %r" % pg.inner_text("#detail-stt-state"))

        need(pg.evaluate("window.__releaseSttOptions(0)"), "쥔 B 기본값 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchCount") >= 2, 5, pg=pg),
             "놓은 B 기본값 응답이 도착하지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt") and
                      pg.input_value("#detail-stt-preprocess") == "denoise", 10, pg=pg),
             "B 칸이 풀려 기본값으로 채워지지 않음: %r" % pg.input_value("#detail-stt-preprocess"))
        c.close()
    check("73 옵션 없는 B 칸 잠금: A 의 늦은 응답이 풀지 않음", t73)


    def t74():
        # 시간 제한 뒤 사람이 입력한 값은 늦게 온 기본값 응답이 덮지 않는다(N11).
        b, _ = new_server("d74")
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "denoise", "num_speakers": 1}})
        rid_a = upload_rec(b, "t74-a")
        c = new_ctx()
        pg = c.new_page()
        pg.clock.install()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 1개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "A 기본값 GET 응답이 쥐어지지 않음")
        keys = ("preprocess", "speakers", "context", "auto", "review")
        need(not pg.is_enabled("#detail-stt-preprocess") and not pg.is_enabled("#detail-stt-run"),
             "A 칸이 기본값 응답 전 잠기지 않음")
        pg.clock.fast_forward(15000)
        need(wait_for(lambda: all(pg.is_enabled("#detail-stt-" + k) for k in keys) and
                      pg.is_enabled("#detail-stt-run") and
                      "시간이 지났습니다" in pg.inner_text("#detail-stt-state"), 5, pg=pg),
             "시간 제한 뒤 칸이 풀리지 않음: %r" % pg.inner_text("#detail-stt-state"))
        pg.select_option("#detail-stt-preprocess", "basic")
        pg.fill("#detail-stt-speakers", "3")
        pg.fill("#detail-stt-context", "테스트 문맥")
        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 늦은 기본값 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchCount") >= 1, 5, pg=pg),
             "놓은 늦은 기본값 응답이 도착하지 않음")
        pg.wait_for_timeout(200)
        need(pg.input_value("#detail-stt-preprocess") == "basic" and
             pg.input_value("#detail-stt-speakers") == "3" and
             pg.input_value("#detail-stt-context") == "테스트 문맥",
             "늦은 응답이 사람이 입력한 값을 덮음: %r / %r / %r" %
             (pg.input_value("#detail-stt-preprocess"), pg.input_value("#detail-stt-speakers"),
              pg.input_value("#detail-stt-context")))
        need("시간이 지났습니다" in pg.inner_text("#detail-stt-state"),
             "늦은 응답이 시간 초과 글을 지움: %r" % pg.inner_text("#detail-stt-state"))
        c.close()
    check("74 시간 제한 뒤 늦은 응답: 사람이 입력한 값 유지", t74)


    def t75():
        # 같은 녹음에서 재시도 POST 를 쥔 채 칸을 닫았다 다시 열면, 성공 응답이 다시 연 칸을 닫지 않는다(R54-N4).
        b, _ = new_server("d75")
        rid = upload_rec(b, "t75-a")
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(RETRY_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 1개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt") and stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "옵션 칸의 입력 칸·실행 단추가 풀리지 않음")
        pg.evaluate("window.__holdNextRetry()")
        pg.click("#detail-stt-run")
        need(wait_for(lambda: pg.evaluate("window.__retryHeld()"), 5, pg=pg),
             "재시도 POST 응답이 쥐어지지 않음")
        need(pg.inner_text("#detail-stt-state") == "요청 중…",
             "재시도 응답 전 상태가 '요청 중…' 이 아님: %r" % pg.inner_text("#detail-stt-state"))

        pg.click("#detail-retry-opts")
        need(pg.evaluate("document.querySelector('#detail-stt').hidden"), "옵션 칸을 닫지 못함")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: not pg.evaluate("document.querySelector('#detail-stt').hidden") and
                      stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "옵션 칸을 다시 열지 못함")

        need(pg.evaluate("window.__releaseRetry()"), "쥔 재시도 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedRetryDone"), 5, pg=pg),
             "놓은 재시도 응답이 도착하지 않음")
        need(wait_for(lambda: pg.is_visible("#toast") and
                      "다시 받아쓰기를 요청했습니다" in pg.inner_text("#toast"), 5, pg=pg),
             "재시도 성공 토스트가 보이지 않음: %r" % pg.inner_text("#toast"))
        need(not pg.evaluate("document.querySelector('#detail-stt').hidden"),
             "다시 연 옵션 칸이 재시도 성공 응답에 닫힘")
        need(pg.evaluate("document.querySelector('#detail-retry-opts').getAttribute('aria-expanded')") == "true",
             "다시 연 옵션 단추가 접힘 상태로 바뀜")
        c.close()
    check("75 같은 녹음 재시도 응답 전 닫았다 다시 연 칸: 성공해도 유지", t75)


    def t76():
        # 칸을 그대로 둔 채 성공하면 칸이 닫히고 상태 글이 비며, 400 실패면 서버 까닭이 토스트로 가고 상태 글이 빈다(R54-N5).
        b, _ = new_server("d76")
        rid_a = upload_rec(b, "t76-a")
        rid_b = upload_rec(b, "t76-b")
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(RETRY_HOLD_JS)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 2, 10, pg=pg), "목록 항목이 2개가 아님")

        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_a).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "A 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt") and stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "A 옵션 칸의 입력 칸·실행 단추가 풀리지 않음")
        pg.evaluate("window.__holdNextRetry()")
        pg.click("#detail-stt-run")
        need(wait_for(lambda: pg.evaluate("window.__retryHeld()"), 5, pg=pg),
             "A 재시도 POST 응답이 쥐어지지 않음")
        need(pg.evaluate("window.__releaseRetry()"), "쥔 A 재시도 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedRetryDone"), 5, pg=pg),
             "놓은 A 재시도 응답이 도착하지 않음")
        need(wait_for(lambda: pg.is_visible("#toast") and
                      "다시 받아쓰기를 요청했습니다" in pg.inner_text("#toast"), 5, pg=pg),
             "A 성공 토스트가 보이지 않음: %r" % pg.inner_text("#toast"))
        need(pg.evaluate("document.querySelector('#detail-stt').hidden"),
             "칸을 그대로 둔 채 성공했는데 옵션 칸이 닫히지 않음")
        need(pg.evaluate("document.querySelector('#detail-retry-opts').getAttribute('aria-expanded')") == "false",
             "성공했는데 옵션 단추가 펼침 상태로 남음")
        need(pg.evaluate("document.querySelector('#detail-stt-state').textContent") == "",
             "성공했는데 상태 글이 비지 않음: %r" %
             pg.evaluate("document.querySelector('#detail-stt-state').textContent"))

        server_text = "재시도 거절 - 서버가 준 까닭"

        def retry_400(route):
            req = route.request
            url = req.url.split("?")[0]
            if req.method == "POST" and "/api/recordings/" in url and url.endswith("/retry"):
                route.fulfill(status=400, content_type="application/json",
                              body=json.dumps({"error": server_text}, ensure_ascii=False))
            else:
                route.continue_()

        pg.route("**/api/recordings/*/retry", retry_400)
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid_b).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "B 상세가 준비되지 않음")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.is_visible("#detail-stt") and stt_fields_ready(pg, "detail-stt"), 10, pg=pg),
             "B 옵션 칸의 입력 칸·실행 단추가 풀리지 않음")
        pg.click("#detail-stt-run")
        need(wait_for(lambda: pg.is_visible("#toast") and server_text in pg.inner_text("#toast"), 5, pg=pg),
             "B 400 실패 뒤 서버 까닭이 토스트로 보이지 않음: %r" % pg.inner_text("#toast"))
        need(pg.evaluate("document.querySelector('#detail-stt-state').textContent") == "",
             "B 400 실패 뒤 상태 글이 비지 않음: %r" %
             pg.evaluate("document.querySelector('#detail-stt-state').textContent"))
        pg.unroute("**/api/recordings/*/retry", retry_400)
        c.close()
    check("76 칸 그대로 성공: 닫힘·상태 글 빔 / 400 실패: 서버 까닭 토스트·상태 글 빔", t76)


    def t77():
        # 설정 칸 저장 중 다섯 칸·저장 단추가 잠기고, 저장 중 다시 열어도 새 기본값 읽기가 나가지 않으며
        # '저장 중…' 이 그 읽기에 덮이지 않고 저장 응답 값으로 칸이 채워진다(R53-N7).
        b, _ = new_server("d77")
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        pg.add_init_script(STT_SAVE_HOLD_JS)
        gets = []

        def track_get(req):
            url = req.url.split("?")[0]
            if req.method == "GET" and url.endswith("/api/stt-options"):
                gets.append(url)

        pg.on("request", track_get)
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "denoise"}})
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")

        # 읽기를 쥔 채 저장하면 저장이 그 읽기를 끊어 '저장 중…' 이 그 읽기에 덮이지 않는다.
        # 읽는 동안에는 저장 단추가 잠겨 있어 사람이 누를 수 없다 - 저장 쪽 abort 를 보려고만 이벤트를 보낸다.
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.is_visible("#stt-defaults-fields") and
                      pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "설정 기본값 GET 응답이 쥐어지지 않음")
        need(not pg.is_enabled("#stt-defaults-preprocess") and not pg.is_enabled("#stt-defaults-save"),
             "기본값 응답 전 설정 칸·저장 단추가 잠기지 않음")
        pg.evaluate("window.__holdNextSave()")
        pg.evaluate("document.querySelector('#stt-defaults-save').dispatchEvent(new MouseEvent('click'))")
        need(wait_for(lambda: pg.evaluate("window.__saveHeld()"), 5, pg=pg),
             "읽기를 쥔 채 보낸 설정 저장 PUT 이 쥐어지지 않음")
        need(pg.evaluate("document.querySelector('#stt-defaults-state').textContent") == "저장 중…",
             "읽기를 쥔 채 저장했는데 상태가 '저장 중…' 이 아님: %r" %
             pg.evaluate("document.querySelector('#stt-defaults-state').textContent"))
        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 설정 기본값 읽기를 놓지 못함")
        need(pg.evaluate("window.__releasedFetchAborted"), "저장이 쥔 기본값 읽기를 끊지 않음")
        pg.wait_for_timeout(200)
        need(pg.evaluate("document.querySelector('#stt-defaults-state').textContent") == "저장 중…",
             "끊긴 기본값 읽기가 '저장 중…' 을 덮음: %r" %
             pg.evaluate("document.querySelector('#stt-defaults-state').textContent"))
        need(not pg.is_enabled("#stt-defaults-preprocess") and not pg.is_enabled("#stt-defaults-save"),
             "저장 중 설정 칸·저장 단추가 풀림")
        need(pg.evaluate("window.__releaseSave()"), "쥔 설정 저장 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedSaveDone"), 5, pg=pg),
             "놓은 설정 저장 응답이 도착하지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "저장 응답 뒤 설정 입력 칸·저장 단추가 풀리지 않음")
        need(pg.evaluate("document.querySelector('#stt-defaults-state').textContent") == "",
             "읽기를 끊은 저장 응답 뒤 상태 글이 비지 않음: %r" %
             pg.evaluate("document.querySelector('#stt-defaults-state').textContent"))

        keys = ("preprocess", "speakers", "context", "auto", "review")
        pg.select_option("#stt-defaults-preprocess", "denoise")
        pg.fill("#stt-defaults-speakers", "2")
        pg.evaluate("window.__holdNextSave()")
        before_gets = len(gets)
        pg.click("#stt-defaults-save")
        need(wait_for(lambda: pg.evaluate("window.__saveHeld()"), 5, pg=pg),
             "설정 저장 PUT 응답이 쥐어지지 않음")

        def locked():
            return pg.evaluate("""() => ({
                fields: ['preprocess', 'speakers', 'context', 'auto', 'review'].map(function (k) {
                    return document.querySelector('#stt-defaults-' + k).disabled;
                }),
                save: document.querySelector('#stt-defaults-save').disabled,
                state: document.querySelector('#stt-defaults-state').textContent
            })""")

        state = locked()
        need(all(state["fields"]), "저장 응답 전 설정 입력 칸이 잠기지 않음: %r" % state)
        need(state["save"], "저장 응답 전 설정 저장 단추가 잠기지 않음: %r" % state)
        need(state["state"] == "저장 중…", "저장 응답 전 상태가 '저장 중…' 이 아님: %r" % state["state"])

        # 저장 중 설정을 닫았다 다시 연다 - 기본값 읽기를 새로 시작하면 안 된다.
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#settings-btn")
        need(pg.evaluate("document.querySelector('#settings').hidden"), "설정 칸을 닫지 못함")
        pg.click("#settings-btn")
        need(not pg.evaluate("document.querySelector('#settings').hidden"), "설정 칸을 다시 열지 못함")
        pg.wait_for_timeout(200)
        need(not pg.evaluate("window.__sttOptionsHeld()"), "저장 중에 기본값 읽기가 새로 나가 쥐어짐")
        need(len(gets) == before_gets, "저장 중에 기본값 GET 이 새로 나감: %r" % gets[before_gets:])
        state = locked()
        need(all(state["fields"]), "저장 중 다시 열자 설정 입력 칸이 풀림: %r" % state)
        need(state["save"], "저장 중 다시 열자 설정 저장 단추가 풀림: %r" % state)
        need(state["state"] == "저장 중…", "저장 중 다시 열자 상태가 덮임: %r" % state["state"])

        need(pg.evaluate("window.__releaseSave()"), "쥔 설정 저장 응답을 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedSaveDone"), 5, pg=pg),
             "놓은 설정 저장 응답이 도착하지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults"), 10, pg=pg),
             "저장 응답 뒤 설정 입력 칸·저장 단추가 풀리지 않음")
        need(pg.input_value("#stt-defaults-preprocess") == "denoise" and
             pg.input_value("#stt-defaults-speakers") == "2",
             "저장 응답 값이 설정 칸에 채워지지 않음: %r / %r" %
             (pg.input_value("#stt-defaults-preprocess"), pg.input_value("#stt-defaults-speakers")))
        need(pg.inner_text("#stt-defaults-state") == "",
             "저장 응답 뒤 상태 글이 비지 않음: %r" % pg.inner_text("#stt-defaults-state"))
        need(wait_for(lambda: pg.is_visible("#toast") and "저장했습니다" in pg.inner_text("#toast"), 5, pg=pg),
             "설정 저장 성공 토스트가 보이지 않음: %r" % pg.inner_text("#toast"))
        c.close()
    check("77 설정 저장 중 잠금·다시 열어도 새 읽기 없음·저장 응답 값 채움", t77)


    def t78():
        # 상세 칸 기본값 읽기를 쥔 채 닫았다 다시 열면 새 GET 이 나가 그 응답으로 채우고, 앞 읽기는 끊긴다(R53-N9).
        b, _ = new_server("d78")
        rid = upload_rec(b, "t78-a")
        c = new_ctx()
        pg = c.new_page()
        pg.add_init_script(STT_OPTIONS_HOLD_JS)
        gets = []

        def track_get(req):
            url = req.url.split("?")[0]
            if req.method == "GET" and url.endswith("/api/stt-options"):
                gets.append(url)

        pg.on("request", track_get)
        pg.goto(b + "/")
        pg.wait_for_selector("#rec")
        open_tab(pg, "list")
        need(wait_for(lambda: list_count(pg) == 1, 10, pg=pg), "목록 항목이 1개가 아님")
        pg.locator("#list .rec-item[data-id='%s'] .rec-main" % rid).click()
        need(wait_for(lambda: pg.is_visible("#detail") and detail_ready(pg), 10, pg=pg),
             "상세가 준비되지 않음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeld()"), 5, pg=pg),
             "첫 기본값 GET 응답이 쥐어지지 않음")
        need(not pg.is_enabled("#detail-stt-preprocess") and not pg.is_enabled("#detail-stt-run"),
             "첫 기본값 응답 전 칸·실행 단추가 잠기지 않음")

        pg.click("#detail-retry-opts")
        need(pg.evaluate("document.querySelector('#detail-stt').hidden"), "옵션 칸을 닫지 못함")
        need(pg.evaluate("window.__heldFetchAborted") >= 1, "닫을 때 쥔 기본값 읽기가 끊기지 않음")
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "denoise"}})

        before_gets = len(gets)
        pg.click("#detail-retry-opts")
        need(wait_for(lambda: len(gets) >= before_gets + 1, 10, pg=pg),
             "다시 열었는데 새 기본값 GET 이 나가지 않음: %r" % gets[before_gets:])
        need(wait_for(lambda: stt_fields_ready(pg, "detail-stt") and
                      pg.input_value("#detail-stt-preprocess") == "denoise", 10, pg=pg),
             "다시 연 칸이 새 GET 응답으로 채워지지 않음: %r" % pg.input_value("#detail-stt-preprocess"))

        need(pg.evaluate("window.__releaseSttOptions()"), "쥔 첫 기본값 응답을 놓지 못함")
        need(pg.evaluate("window.__releasedFetchAborted"), "놓은 첫 기본값 읽기가 끊긴 것으로 기록되지 않음")
        pg.wait_for_timeout(200)
        need(pg.is_enabled("#detail-stt-preprocess") and
             pg.input_value("#detail-stt-preprocess") == "denoise",
             "앞 읽기를 놓은 뒤 칸이 바뀜: %r" % pg.input_value("#detail-stt-preprocess"))

        # 같은 장치의 설정 묶음: 닫을 때는 읽기를 끊지 않고, 다시 열 때 새 읽기가 앞 읽기를 끊는다.
        api_put_json(b, "/api/stt-options", {"options": {"preprocess": "basic"}})
        aborted_before = pg.evaluate("window.__heldFetchAborted")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeldCount()") == 1, 5, pg=pg),
             "설정 첫 기본값 GET 이 쥐어지지 않음")
        pg.click("#settings-btn")
        need(pg.evaluate("document.querySelector('#settings').hidden"), "설정 칸을 닫지 못함")
        need(pg.evaluate("window.__heldFetchAborted") == aborted_before, "설정 칸을 닫을 때 읽기를 끊음")
        pg.evaluate("window.__holdNextSttOptions()")
        pg.click("#settings-btn")
        need(wait_for(lambda: pg.evaluate("window.__sttOptionsHeldCount()") == 2, 5, pg=pg),
             "설정을 다시 열어도 새 기본값 GET 이 나가지 않음")
        need(pg.evaluate("window.__heldFetchAborted") >= aborted_before + 1,
             "설정을 다시 열 때 앞 읽기를 끊지 않음")
        need(pg.evaluate("window.__releaseSttOptions(0)"), "설정 앞 읽기를 놓지 못함")
        need(pg.evaluate("window.__releasedFetchAborted"), "설정 앞 읽기가 끊긴 것으로 기록되지 않음")
        need(pg.evaluate("window.__releaseSttOptions(0)"), "설정 새 읽기를 놓지 못함")
        need(wait_for(lambda: pg.evaluate("window.__releasedFetchDone"), 5, pg=pg),
             "설정 새 기본값 응답이 도착하지 않음")
        need(wait_for(lambda: stt_fields_ready(pg, "stt-defaults") and
                      pg.input_value("#stt-defaults-preprocess") == "basic", 10, pg=pg),
             "설정을 다시 열어 새로 읽은 기본값이 채워지지 않음: %r" %
             pg.input_value("#stt-defaults-preprocess"))
        c.close()
    check("78 상세·설정 칸 닫았다 다시 열기: 앞 읽기 끊김·새 GET 으로 채움", t78)


if __name__ == "__main__":
    sys.exit(main())
