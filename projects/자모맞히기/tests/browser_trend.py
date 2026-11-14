#!/usr/bin/env python3
"""자모맞히기 뉴스로 정답 고르기(R31 2부, T-325) 브라우저 검사.

그려진 화면을 묻습니다. 서버 경로 api/trend/pick 은 모두 page.route 가짜입니다(진짜 서버·뉴스·사전을 부르지 않습니다).
"""
import json
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from browser_harness import Checks, install_dict_routes, server, set_group, shot  # noqa: E402

set_group("trend")

CJSON = "application/json"
CORS = {"access-control-allow-origin": "*"}
PICK_URL = "**/api/trend/pick"
GET_URL = "**/api/trend"
# 시계 고정: 이 순간이 브라우저의 '지금' (오늘 = 2026-11-15, 정적 TREND 의 오늘 정답은 지원)
FIXED = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone(timedelta(hours=9)))
TODAY = "2026-11-15"
EMPTY_TREND = {"ok": True, "trend": {}, "last_run": None}
VP_SMALL = {"width": 320, "height": 640}


# ---------------------------------------------------------------- 도우미


def fulfill_json(route, payload, status=200):
    try:
        route.fulfill(status=status, content_type=CJSON, headers=CORS, body=json.dumps(payload))
    except Exception:  # noqa: BLE001  페이지가 닫히거나 다시 열려 이미 끝난 요청
        pass


def route_pick(page, payload, status=200):
    """api/trend/pick 을 고정 답으로. 요청 본문을 ctl['bodies'] 에 쌓는다."""
    ctl = {"payload": payload, "status": status, "bodies": []}

    def handler(route):
        try:
            ctl["bodies"].append(json.loads(route.request.post_data or "{}"))
        except Exception:  # noqa: BLE001
            ctl["bodies"].append(None)
        fulfill_json(route, ctl["payload"], status=ctl["status"])

    page.route(PICK_URL, handler)
    return ctl


def day_keys(page, n=3):
    """브라우저 시계 기준 오늘부터 n 일의 날짜 글."""
    return page.evaluate(
        "(n) => Array.from({length: n}, (_, i) => { const d = new Date();"
        " d.setDate(d.getDate() + i); const p = (x) => String(x).padStart(2, '0');"
        " return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); })",
        n,
    )


def unlisted_words(page):
    """낱말 목록에 없고 오늘 정답도 아닌 자모 6칸 한글 낱말 몇 개."""
    return page.evaluate(
        """async () => {
          const w = await import('./js/words.js');
          const j = await import('./js/jamo.js');
          const g = await import('./js/game.js');
          const answer = g.answerForDate(new Date(), w.ANSWERS, w.TREND ?? {});
          const listed = new Set(w.ALLOWED);
          const out = [];
          const finals = ['강', '난', '달', '람', '맘', '밤', '삼', '잔', '찬', '칸', '탄', '팜', '한'];
          for (const a of finals) for (const b of finals) {
            const word = a + b;
            const u = j.toUnits(word);
            if (u && u.length === 6 && !listed.has(word) && word !== answer) out.push(word);
          }
          return out.slice(0, 8);
        }"""
    )


def wrong_listed_word(page):
    """낱말 목록에 있고 오늘 정답이 아닌 낱말 하나."""
    return page.evaluate(
        """async () => {
          const w = await import('./js/words.js');
          const g = await import('./js/game.js');
          const answer = g.answerForDate(new Date(), w.ANSWERS, w.TREND ?? {});
          return w.ALLOWED.find((x) => x !== answer);
        }"""
    )


def keyboard_reverse(page):
    return page.evaluate(
        "async () => { const j = await import('./js/jamo.js'); const out = {};"
        " for (const [code, pair] of Object.entries(j.KEYMAP)) {"
        "   out[pair[0]] = [code, false];"
        "   if (pair[1] !== pair[0]) out[pair[1]] = [code, true];"
        " } return out; }"
    )


def type_word(page, word):
    units = page.evaluate(
        "async (w) => { const j = await import('./js/jamo.js'); return j.toUnits(w); }", word
    )
    rev = keyboard_reverse(page)
    for unit in units:
        code, shifted = rev[unit]
        page.keyboard.press(("Shift+" if shifted else "") + code)


def row_states(page, row):
    return page.evaluate(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile'))"
        ".map((t) => t.dataset.state)",
        row + 1,
    )


def wait_row_done(page, row, timeout=6000):
    page.wait_for_function(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile'))"
        ".every((t) => ['correct', 'present', 'absent'].includes(t.dataset.state))",
        arg=row + 1,
        timeout=timeout,
    )
    page.wait_for_function(
        "() => document.querySelectorAll('#board .tile.flip').length === 0", timeout=timeout
    )


def won_with(page, word):
    """낱말을 내서 첫 줄이 모두 correct 면 True."""
    type_word(page, word)
    page.keyboard.press("Enter")
    try:
        wait_row_done(page, 0)
    except Exception:  # noqa: BLE001
        return False
    return set(row_states(page, 0)) == {"correct"}


def dismiss_help(page):
    if page.locator("#modal-help:not([hidden])").count():
        page.keyboard.press("Escape")
        page.wait_for_function("() => document.getElementById('modal-help').hidden === true")


def open_settings(page):
    dismiss_help(page)
    if not page.locator("#modal-settings:not([hidden])").count():
        page.click("#btn-settings")
        page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    page.wait_for_timeout(60)


def close_settings(page):
    if page.locator("#modal-settings:not([hidden])").count():
        page.keyboard.press("Escape")
        page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")


def status_text(page):
    return page.locator("#trend-status").text_content() or ""


def wait_status(page, needle, timeout=4000):
    try:
        page.wait_for_function(
            "(n) => document.getElementById('trend-status').textContent.includes(n)",
            arg=needle,
            timeout=timeout,
        )
        return True
    except Exception:
        return False


def pick_ok(dates, words, titles=123, last_run=None, base=None):
    """serve.py 의 pick 응답 꼴: added(덧붙인 것)·trend(서버 전체)·last_run. base 는 이미 있던 줄."""
    added = [{"date": d, "word": w} for d, w in zip(dates, words)]
    trend = dict(base or {})
    trend.update({a["date"]: a["word"] for a in added})
    return {
        "ok": True,
        "picks": added,
        "added": added,
        "trend": trend,
        "last_run": last_run or FIXED.isoformat(),
        "titles": titles,
        "candidates": 40,
        "checked": 30,
        "source": "wiktionary",
    }


def stored(page, key):
    return page.evaluate("(k) => localStorage.getItem(k)", key)


def box(page, selector):
    return page.locator(selector).first.bounding_box()


def inside(inner, outer, slack=1.0):
    return (
        inner["x"] >= outer["x"] - slack
        and inner["y"] >= outer["y"] - slack
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + slack
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + slack
    )


def page_errors_ok(checks, page, name):
    errors = [e for e in page._errors if "Failed to load resource" not in e and "net::ERR" not in e]
    checks.ok(f"{name}: 페이지 오류 없음", not errors, "; ".join(errors[:3]))


def open_page(browser, base, get=None, get_status=200, viewport=None, init_script=None):
    """시계를 2026-11-15 12:00(서울)에 고정하고 GET api/trend 를 가짜로 건 새 페이지(진짜 serve.py 의 data/ 를 읽지 않음).

    page._trend 로 GET 응답(payload·status·calls)을 시나리오가 중간에 바꿀 수 있다.
    """
    context = browser.new_context(viewport=viewport or {"width": 420, "height": 900},
                                  timezone_id="Asia/Seoul", locale="ko-KR")
    install_dict_routes(context)
    state = {"payload": get if get is not None else dict(EMPTY_TREND), "status": get_status, "calls": 0}

    def handler(route):
        if route.request.method != "GET":
            return route.fallback()
        state["calls"] += 1
        try:
            if state["status"] is None:
                return route.abort()
            if state["status"] == "html":
                return route.fulfill(status=200, content_type="text/html", headers=CORS, body="<html>x</html>")
            if state["status"] != 200:
                return route.fulfill(status=state["status"], content_type="text/plain", headers=CORS, body="no")
            return route.fulfill(status=200, content_type=CJSON, headers=CORS, body=json.dumps(state["payload"]))
        except Exception:  # noqa: BLE001
            return None

    context.route(GET_URL, handler)
    page = context.new_page()
    page._errors = []
    page._context = context
    page._trend = state
    page.on("pageerror", lambda e: page._errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: page._errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.clock.set_fixed_time(FIXED)
    if init_script:
        page.add_init_script(init_script)
    page.goto(base + "/index.html", wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    return page


def run(name, checks, scenario, browser, base, **kw):
    page = open_page(browser, base, **kw)
    try:
        page.wait_for_timeout(80)
        dismiss_help(page)
        scenario(checks, page, base)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        checks.ok(f"{name} - 시나리오 실행", False, repr(exc))
    finally:
        page_errors_ok(checks, page, name)
        page._context.close()


# ---------------------------------------------------------------- 시나리오


def scenario_form(checks, page, base):
    open_settings(page)
    checks.ok("설정 창에 #set-trend 절이 보임", page.locator("#set-trend").is_visible())
    checks.ok("#trend-pick 단추가 보이고 켜져 있음",
              page.locator("#trend-pick").is_visible() and page.locator("#trend-pick").is_enabled())
    checks.ok("단추 글 `지금 뉴스에서 정답 고르기`",
              "지금 뉴스에서 정답 고르기" in (page.locator("#trend-pick").text_content() or ""))
    checks.ok("#trend-status 는 aria-live=polite", page.get_attribute("#trend-status", "aria-live") == "polite")
    sec = box(page, "#set-trend")
    btn = box(page, "#trend-pick")
    checks.ok("단추가 절 안에 있음", bool(sec and btn and inside(btn, sec)))
    checks.ok("작은 안내 글이 보임", "연합뉴스" in (page.locator("#set-trend small").first.text_content() or ""))
    shot(page, "settings-trend")


def scenario_progress_and_success(checks, page, base):
    words = unlisted_words(page)
    dates = day_keys(page, 3)
    pending = []
    bodies = []

    def hold(route):
        try:
            bodies.append(json.loads(route.request.post_data or "{}"))
        except Exception:  # noqa: BLE001
            bodies.append(None)
        pending.append(route)

    page.route(PICK_URL, hold)
    open_settings(page)
    page.click("#trend-pick")
    checks.ok("누르면 #trend-pick 이 비활성", wait_disabled(page))
    checks.ok("상태 글 `고르는 중`", wait_status(page, "고르는 중"), status_text(page))
    answer_payload = pick_ok(dates, words[:3], titles=321)
    for route in pending:
        fulfill_json(route, answer_payload)
    checks.ok("끝나면 상태 글에 날짜·일수·제목 수",
              wait_status(page, "3일치") and dates[0] in status_text(page) and "321" in status_text(page),
              status_text(page))
    checks.ok("끝나면 단추가 다시 켜짐", page.locator("#trend-pick").is_enabled())
    body_text = page.evaluate("() => document.body.innerText + '\\n' + document.body.textContent")
    checks.ok("낱말 글자가 화면 어디에도 없음", not any(w in body_text for w in words[:3]), status_text(page))
    checks.ok("브라우저에는 jamo.trend 를 저장하지 않음", stored(page, "jamo.trend") is None)
    checks.ok("끝나면 #trend-since 가 `방금 정함`", page.locator("#trend-since").text_content() == "방금 정함",
              page.locator("#trend-since").text_content() or "")
    checks.ok("비어 있던 오늘 판의 요청 start 는 오늘", bodies and bodies[0] and bodies[0].get("start") == dates[0],
              str(bodies))
    close_settings(page)
    checks.ok("빈 오늘 판은 새 정답으로 바뀜(그 낱말을 내면 이김)", won_with(page, words[0]),
              str(row_states(page, 0)))
    # 새로 고친 뒤: 서버(GET)가 정답을 다시 줌 - 브라우저 저장은 없음
    page._trend["payload"] = answer_payload
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(120)
    dismiss_help(page)
    checks.ok("새로 고친 뒤에도 이긴 판이 그대로", row_states(page, 0)[0] == "correct", str(row_states(page, 0)))
    checks.ok("새로 고친 뒤에도 jamo.trend 는 없음", stored(page, "jamo.trend") is None)
    page.evaluate("(k) => localStorage.removeItem('jamo.daily.' + k)", TODAY)
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(120)
    dismiss_help(page)
    checks.ok("새로 고친 뒤 새 판에서도 저장된 정답이 오늘 정답", won_with(page, words[0]),
              str(row_states(page, 0)))


def wait_disabled(page, timeout=2000):
    try:
        page.wait_for_function("() => document.getElementById('trend-pick').disabled === true", timeout=timeout)
        return True
    except Exception:
        return False


def scenario_played_today(checks, page, base):
    words = unlisted_words(page)
    today, tomorrow, third = day_keys(page, 3)
    wrong = wrong_listed_word(page)
    checks.ok("오늘 판에 줄을 하나 냄", won_with(page, wrong) is False and row_states(page, 0)[0] != "empty",
              str(row_states(page, 0)))
    page.wait_for_timeout(300)
    daily_key = "jamo.daily." + today
    before = json.loads(stored(page, daily_key) or "{}").get("answer")
    ctl = route_pick(page, pick_ok([tomorrow, third], words[:2]))
    open_settings(page)
    page.click("#trend-pick")
    ok = wait_status(page, "2일치")
    checks.ok("줄을 낸 날은 요청 start 가 내일", ok and ctl["bodies"] and ctl["bodies"][0]
              and ctl["bodies"][0].get("start") == tomorrow, str(ctl["bodies"]))
    checks.ok("요청 본문 days·skip 꼴", ctl["bodies"][0].get("days") == 7 and ctl["bodies"][0].get("skip") == [],
              str(ctl["bodies"]))
    after = json.loads(stored(page, daily_key) or "{}").get("answer")
    checks.ok("오늘 정답과 낸 줄은 그대로", before and before == after, f"{before} -> {after}")
    checks.ok("브라우저에는 jamo.trend 를 저장하지 않음", stored(page, "jamo.trend") is None)
    close_settings(page)
    checks.ok("낸 줄도 화면에 그대로", row_states(page, 0)[0] != "empty")


def scenario_404(checks, page, base):
    ctl = route_pick(page, {}, status=404)
    before = stored(page, "jamo.daily." + day_keys(page, 1)[0])
    open_settings(page)
    page.click("#trend-pick")
    checks.ok("404 → `serve.py 로 열었을 때만` 글", wait_status(page, "serve.py 로 열었을 때만"), status_text(page))
    checks.ok("404 → 요청은 한 번", len(ctl["bodies"]) == 1)
    checks.ok("404 → 저장 없음·판 그대로",
              stored(page, "jamo.trend") is None and stored(page, "jamo.daily." + day_keys(page, 1)[0]) == before)
    checks.ok("404 → 단추가 다시 켜짐", page.locator("#trend-pick").is_enabled())


def scenario_fail(checks, page, base):
    route_pick(page, {"ok": False, "error": "뉴스 제목을 가져오지 못했습니다"})
    open_settings(page)
    page.click("#trend-pick")
    checks.ok("ok:false → `정답 고르기 실패`", wait_status(page, "정답 고르기 실패"), status_text(page))
    checks.ok("까닭이 글에 나옴", "뉴스 제목을 가져오지 못했습니다" in status_text(page), status_text(page))
    checks.ok("실패 → 저장 없음", stored(page, "jamo.trend") is None)
    checks.ok("실패 → 단추가 다시 켜짐", page.locator("#trend-pick").is_enabled())


def scenario_source(checks, page, base):
    words = unlisted_words(page)
    dates = day_keys(page, 1)
    ctl = route_pick(page, pick_ok(dates, words[:1]))
    open_settings(page)
    page.click("#trend-pick")
    wait_status(page, "1일치")
    checks.ok("기본(위키낱말사전) → source wiktionary", ctl["bodies"][-1].get("source") == "wiktionary",
              str(ctl["bodies"]))
    page.select_option("#dict-source", "stdict")
    page.click("#trend-pick")
    page.wait_for_function("() => document.getElementById('trend-pick').disabled === false", timeout=3000)
    page.wait_for_timeout(200)
    checks.ok("표준국어대사전을 고르면 source stdict", ctl["bodies"][-1].get("source") == "stdict",
              str(ctl["bodies"]))
    page.select_option("#dict-source", "gemini")
    page.click("#trend-pick")
    page.wait_for_timeout(300)
    checks.ok("키 직접 출처(gemini)면 source wiktionary", ctl["bodies"][-1].get("source") == "wiktionary",
              str(ctl["bodies"]))
    page.locator("#set-dict details.dict-add-box summary").click()
    page.fill("#dict-add-name", "내 모델")
    page.fill("#dict-add-url", "https://example.com/v1")
    page.fill("#dict-add-model", "test-model")
    page.click("#dict-add")
    page.wait_for_timeout(80)
    page.click("#trend-pick")
    page.wait_for_timeout(300)
    checks.ok("사용자 LLM 이면 source wiktionary", ctl["bodies"][-1].get("source") == "wiktionary"
              and len(ctl["bodies"]) == 4, str(ctl["bodies"]))


def scenario_narrow(checks, page, base):
    words = unlisted_words(page)
    dates = day_keys(page, 7)
    route_pick(page, pick_ok(dates, words[:7], titles=1234567))
    open_settings(page)
    page.click("#trend-pick")
    wait_status(page, "7일치")
    page.wait_for_timeout(100)
    vw = page.evaluate("() => document.documentElement.clientWidth")
    sw = page.evaluate("() => document.documentElement.scrollWidth")
    checks.ok("320px: 문서가 가로로 넘치지 않음", sw <= vw, f"scrollWidth {sw} > clientWidth {vw}")
    over = page.evaluate(
        """() => {
          const sec = document.getElementById('set-trend');
          const bad = [];
          for (const el of [sec, ...sec.querySelectorAll('*')]) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            if (r.left < -1 || r.right > document.documentElement.clientWidth + 1) {
              bad.push((el.id || el.className || el.tagName) + ':' + Math.round(r.left) + '~' + Math.round(r.right));
            }
          }
          const sc = Array.from(sec.querySelectorAll('*')).filter((e) => e.scrollWidth > e.clientWidth + 1
            && getComputedStyle(e).overflowX === 'visible' && e.clientWidth > 0)
            .map((e) => (e.id || e.className || e.tagName) + ':' + e.scrollWidth + '>' + e.clientWidth);
          return {bad, sc};
        }"""
    )
    checks.ok("320px: 뉴스 절 안 요소가 모두 화면 폭 안", not over["bad"], str(over["bad"][:4]))
    checks.ok("320px: 안쪽에서 삐져나오는 글이 없음", not over["sc"], str(over["sc"][:4]))
    b = box(page, "#trend-pick")
    checks.ok("320px: #trend-pick 이 화면 안에 보임",
              page.locator("#trend-pick").is_visible() and bool(b and b["x"] >= -1 and b["x"] + b["width"] <= vw + 1),
              str(b))
    shot(page, "settings-trend-320")


def since_text(page):
    return page.locator("#trend-since").text_content() or ""


def row_all_correct(page, row, word):
    type_word(page, word)
    page.keyboard.press("Enter")
    try:
        wait_row_done(page, row)
    except Exception:  # noqa: BLE001
        return False
    return set(row_states(page, row)) == {"correct"}


def scenario_get_today(checks, page, base):
    checks.ok("GET api/trend 를 시작 때 불렀음", page._trend["calls"] >= 1, str(page._trend["calls"]))
    checks.ok("GET 의 오늘 정답(강당)이 빈 오늘 판의 정답 - 정적 오늘 정답(지원)이 아님",
              won_with(page, "강당"), str(row_states(page, 0)))
    open_settings(page)
    checks.ok("#trend-since `3시간 전에 정함` (08:30 → 12:00)", since_text(page) == "3시간 전에 정함", since_text(page))
    checks.ok("#trend-since 가 단추와 같은 절 안에서 보임",
              page.locator("#trend-since").is_visible() and inside(box(page, "#trend-since"), box(page, "#set-trend")))
    checks.ok("jamo.trend 저장 없음", stored(page, "jamo.trend") is None)
    shot(page, "settings-trend-since")


def scenario_never(checks, page, base):
    open_settings(page)
    checks.ok("정한 적 없으면 `아직 정한 적 없음`", since_text(page) == "아직 정한 적 없음", since_text(page))
    close_settings(page)
    checks.ok("서버 줄이 없으면 정적 오늘 정답(지원)이 그대로", won_with(page, "지원"), str(row_states(page, 0)))


def scenario_no_server(checks, page, base):
    open_settings(page)
    checks.ok("GET 404 → `서버 없이 열어 정한 때를 모릅니다`", since_text(page) == "서버 없이 열어 정한 때를 모릅니다",
              since_text(page))
    close_settings(page)
    checks.ok("GET 이 없어도 게임은 정적 정답(지원)으로 됨", won_with(page, "지원"), str(row_states(page, 0)))
    checks.ok("GET 실패는 조용함(오류 토스트 없음)", page.locator("#toasts").text_content() in ("", None)
              or "서버" not in (page.locator("#toasts").text_content() or ""))


def scenario_pick_no_server(checks, page, base):
    ctl = route_pick(page, {"ok": False}, status=501)
    open_settings(page)
    page.click("#trend-pick")
    checks.ok("501 → `serve.py 로 열었을 때만` 글", wait_status(page, "serve.py 로 열었을 때만"), status_text(page))
    ctl["status"] = 405
    page.click("#trend-pick")
    page.wait_for_timeout(250)
    checks.ok("405 → 같은 글", "serve.py 로 열었을 때만" in status_text(page), status_text(page))
    page.route(PICK_URL, lambda r: r.fulfill(status=200, content_type="text/html", headers=CORS, body="<html>x</html>"))
    page.click("#trend-pick")
    page.wait_for_timeout(250)
    checks.ok("JSON 이 아닌 200 → 같은 글", "serve.py 로 열었을 때만" in status_text(page), status_text(page))
    checks.ok("끝나면 단추가 다시 켜짐", page.locator("#trend-pick").is_enabled())


def scenario_reopen(checks, page, base):
    open_settings(page)
    checks.ok("처음 열 때 `1시간 전에 정함`", since_text(page) == "1시간 전에 정함", since_text(page))
    close_settings(page)
    page.clock.set_fixed_time(FIXED + timedelta(hours=2, minutes=30))
    open_settings(page)
    checks.ok("닫았다 다시 열면 지금 기준 `3시간 전에 정함`", since_text(page) == "3시간 전에 정함", since_text(page))
    close_settings(page)
    page.clock.set_fixed_time(FIXED + timedelta(hours=11))
    open_settings(page)
    checks.ok("한 번 더 열면 `12시간 전에 정함`", since_text(page) == "12시간 전에 정함", since_text(page))


def scenario_n8(checks, page, base):
    today, tomorrow, _ = day_keys(page, 3)
    pending = []
    page.route(PICK_URL, lambda route: pending.append(route))
    open_settings(page)
    page.click("#trend-pick")
    checks.ok("고르는 중", wait_status(page, "고르는 중"), status_text(page))
    close_settings(page)
    wrong = wrong_listed_word(page)
    type_word(page, wrong)
    page.keyboard.press("Enter")
    wait_row_done(page, 0)
    page.wait_for_timeout(200)
    daily_key = "jamo.daily." + today
    before = json.loads(stored(page, daily_key) or "{}")
    checks.ok("고르는 중에 줄을 하나 냄", len(before.get("rows", [])) == 1 and bool(before.get("answer")), str(before)[:120])
    payload = pick_ok([today, tomorrow], ["강당", "한국"])
    page._trend["payload"] = payload
    for route in pending:
        fulfill_json(route, payload)
    checks.ok("오늘이 든 응답이 옴", wait_status(page, "2일치"), status_text(page))
    after = json.loads(stored(page, daily_key) or "{}")
    checks.ok("낸 줄과 정답은 그대로(저장 판)", after.get("answer") == before.get("answer")
              and len(after.get("rows", [])) == 1, str(after)[:120])
    checks.ok("화면의 낸 줄도 그대로", row_states(page, 0)[0] != "empty")
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(150)
    dismiss_help(page)
    checks.ok("새로 고쳐도 낸 줄이 그대로", row_states(page, 0)[0] != "empty", str(row_states(page, 0)))
    reloaded = json.loads(stored(page, daily_key) or "{}")
    checks.ok("새로 고쳐도 저장 정답이 그대로", reloaded.get("answer") == before.get("answer"), str(reloaded)[:120])
    checks.ok("새로 고친 판의 정답은 처음 정답(지원) - 서버의 새 오늘 정답(강당)이 아님",
              row_all_correct(page, 1, "지원"), str(row_states(page, 1)))


def scenario_legacy_key(checks, page, base):
    checks.ok("남아 있던 localStorage jamo.trend 는 시작 때 지워짐", stored(page, "jamo.trend") is None,
              str(stored(page, "jamo.trend")))
    checks.ok("게임은 정상(보드가 그려짐)", page.locator("#board .tile").count() == 36
              or page.locator("#board .tile").count() > 0)


# ---------------------------------------------------------------- 실행


def main():
    checks = Checks()
    with server() as base:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except Exception as exc:  # noqa: BLE001
                print(f"브라우저를 띄우지 못했습니다: {exc}")
                return 2
            try:
                run("설정 창 모양", checks, scenario_form, browser, base)
                run("진행·성공", checks, scenario_progress_and_success, browser, base)
                run("오늘 판에 줄", checks, scenario_played_today, browser, base)
                run("404", checks, scenario_404, browser, base)
                run("실패", checks, scenario_fail, browser, base)
                run("출처", checks, scenario_source, browser, base)
                run("320px", checks, scenario_narrow, browser, base, viewport=VP_SMALL)
                run("GET 의 오늘 정답", checks, scenario_get_today, browser, base,
                    get={"ok": True, "trend": {TODAY: "강당", "2026-11-16": "한국"},
                         "last_run": "2026-11-15T08:30:00+09:00"})
                run("정한 적 없음", checks, scenario_never, browser, base)
                run("서버 없음", checks, scenario_no_server, browser, base, get_status=404)
                run("501·405·JSON 아님", checks, scenario_pick_no_server, browser, base)
                run("창을 다시 열면", checks, scenario_reopen, browser, base,
                    get={"ok": True, "trend": {}, "last_run": "2026-11-15T11:00:00+09:00"})
                run("고르는 중에 줄을 냄(R31-N8)", checks, scenario_n8, browser, base)
                run("남은 jamo.trend 키", checks, scenario_legacy_key, browser, base,
                    init_script="localStorage.setItem('jamo.trend', JSON.stringify({'2026-11-20': '지원'}));")
            finally:
                browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(main())
