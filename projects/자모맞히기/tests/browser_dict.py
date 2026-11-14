#!/usr/bin/env python3
"""자모맞히기 외부 사전 조회(R31) 브라우저 검사.

그려진 화면을 묻습니다: is_visible(), is_checked(), getComputedStyle(), bounding_box().
외부망은 모두 page.route 로 가짜입니다(서버 /api/* 도, 위키·Gemini·사용자 LLM 도). 진짜 외부망을 부르지 않습니다.
"""
import json
import sys
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from browser_harness import Checks, new_page, server, set_group, shot  # noqa: E402

set_group("dict")

CJSON = "application/json"
CORS = {"access-control-allow-origin": "*"}
LOOKUP_URL = "**/api/lookup**"
EXTERNAL_PATTERNS = (
    "https://*.wikipedia.org/**",
    "https://*.wiktionary.org/**",
    "https://generativelanguage.googleapis.com/**",
    "https://openrouter.ai/**",
    "https://example.com/**",
)
FOUND = {"ok": True, "found": True, "source": "wiktionary", "via": "server", "evidence": "테스트 가짜"}
NOT_FOUND = {"ok": True, "found": False, "source": "wiktionary", "via": "server", "evidence": "테스트 가짜"}

# 고정 폭 320 의 가로 한계. 스크롤바를 뺀 안쪽 폭보다 이 이상 넘으면 넘침으로 본다.
VP_SMALL = {"width": 320, "height": 640}


# ---------------------------------------------------------------- 도우미


def fulfill_json(route, payload, status=200):
    try:
        route.fulfill(status=status, content_type=CJSON, headers=CORS, body=json.dumps(payload))
    except Exception:  # noqa: BLE001  페이지가 닫히거나 다시 열려 이미 끝난 요청
        pass


def route_lookup(page, payload=None, status=200, counter=None):
    """서버 조회를 고정 답으로. 돌려주는 ctl 의 payload·status 를 바꾸면 이어서 다른 답을 한다(라우트는 하나만 건다).

    counter(리스트)에 요청 URL 을 쌓는다.
    """
    ctl = {"payload": payload, "status": status, "counter": counter}

    def handler(route):
        if ctl["counter"] is not None:
            ctl["counter"].append(route.request.url)
        fulfill_json(route, ctl["payload"] if ctl["status"] == 200 else {}, status=ctl["status"])

    page.route(LOOKUP_URL, handler)
    return ctl


def route_wiki_fail(page, counter=None):
    def handler(route):
        if counter is not None:
            counter.append(route.request.url)
        route.abort()
    for pattern in EXTERNAL_PATTERNS:
        page.route(pattern, handler)


def watch_requests(page):
    """조회로 보이는 요청(서버 조회·위키·LLM)을 모두 센다."""
    seen = []

    def on_request(req):
        url = req.url
        if "/api/lookup" in url or any(
            host in url for host in ("wiktionary.org", "wikipedia.org", "googleapis.com", "openrouter.ai", "example.com")
        ):
            seen.append(url)

    page.on("request", on_request)
    return seen


def toast_texts(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#toasts .toast')).map((t) => t.textContent)"
    )


def wait_toast(page, needle, timeout=4000):
    try:
        page.wait_for_function(
            "(n) => Array.from(document.querySelectorAll('#toasts .toast')).some((t) => t.textContent.includes(n))",
            arg=needle,
            timeout=timeout,
        )
        return True
    except Exception:
        return False


def row_states(page, row):
    return page.evaluate(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile'))"
        ".map((t) => t.dataset.state)",
        row + 1,
    )


def row_text(page, row):
    return page.evaluate(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile'))"
        ".map((t) => t.textContent).join('')",
        row + 1,
    )


def filled_rows(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .row')).filter((row) =>"
        " Array.from(row.querySelectorAll('.tile')).every((t) =>"
        " ['correct', 'present', 'absent'].includes(t.dataset.state))).length"
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
    page.wait_for_timeout(140)


def row_done(page, row, timeout=2500):
    """줄이 칠해질 때까지 기다리고 됐는지 돌려준다(안 되면 False, 시나리오는 죽지 않음)."""
    try:
        wait_row_done(page, row, timeout=timeout)
        return True
    except Exception:
        return False


def units_of(page, word):
    return page.evaluate(
        "async (w) => { const j = await import('./js/jamo.js'); return j.toUnits(w); }", word
    )


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


def unlisted_words(page):
    """낱말 목록(ALLOWED)에 없고 오늘 정답도 아닌, 자모 6칸 한글 낱말 몇 개를 페이지 안에서 고른다."""
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


def tile_bg(page, row, col):
    return page.evaluate(
        "([r, c]) => getComputedStyle(document.querySelector("
        "'#board .row:nth-child(' + r + ') .tile:nth-child(' + c + ')')).backgroundColor",
        [row + 1, col + 1],
    )


def box(page, selector):
    return page.locator(selector).first.bounding_box()


def inside(inner, outer, slack=1.0):
    return (
        inner["x"] >= outer["x"] - slack
        and inner["y"] >= outer["y"] - slack
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + slack
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + slack
    )


def overlaps(a, b):
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


def stored(page, key):
    return page.evaluate("(k) => localStorage.getItem(k)", key)


def page_errors_ok(checks, page, name):
    errors = [e for e in page._errors if "Failed to load resource" not in e and "net::ERR" not in e]
    checks.ok(f"{name}: 페이지 오류 없음", not errors, "; ".join(errors[:3]))


def run(name, checks, scenario, browser, base, **kw):
    page = new_page(browser, base, **kw)
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
    sec = page.locator("#set-dict")
    checks.ok("설정 창에 외부 사전 절 #set-dict 가 보임", sec.is_visible())
    checks.ok("#dict-on 이 기본 켜짐", page.locator("#dict-on").is_checked())
    checks.ok("#dict-on 은 role=switch", page.get_attribute("#dict-on", "role") == "switch")
    options = page.evaluate(
        "() => Array.from(document.querySelectorAll('#dict-source option')).map((o) => o.textContent)"
    )
    joined = " | ".join(options)
    for needle in ("위키낱말사전", "표준국어대사전", "KISTI", "EXAONE", "Gemini"):
        checks.ok(f"#dict-source 에 {needle}", any(needle in o for o in options), joined)
    checks.ok(
        "기본으로 고른 출처는 위키낱말사전",
        "위키낱말사전" in page.evaluate("() => document.getElementById('dict-source').selectedOptions[0].textContent"),
    )
    modal = box(page, "#modal-settings .modal-card, #modal-settings > *")
    select_box = box(page, "#dict-source")
    switch_box = box(page, "#dict-on")
    checks.ok("출처 상자가 보이고 설정 창 안에 있음", bool(select_box and modal and inside(select_box, modal)))
    checks.ok(
        "스위치와 출처 상자가 서로 안 겹침",
        bool(select_box and switch_box and not overlaps(select_box, switch_box)),
    )
    # gemini 는 키 입력이 보이고 위키는 안 보임
    page.select_option("#dict-source", "gemini")
    page.wait_for_timeout(60)
    checks.ok("gemini 를 고르면 #dict-key 가 보임", page.locator("#dict-key").is_visible())
    key_box = box(page, "#dict-key")
    sel_box = box(page, "#dict-source")
    checks.ok(
        "#dict-key 가 출처 상자와 안 겹치고 절 안에 있음",
        bool(key_box and sel_box and not overlaps(key_box, sel_box) and inside(key_box, box(page, "#set-dict"))),
    )
    checks.ok("#dict-key 는 비밀번호 입력", page.get_attribute("#dict-key", "type") == "password")
    page.select_option("#dict-source", "wiktionary")
    page.wait_for_timeout(60)
    checks.ok("위키낱말사전을 고르면 #dict-key 가 안 보임", not page.locator("#dict-key").is_visible())
    shot(page, "settings-dict")


def scenario_found(checks, page, base):
    words = unlisted_words(page)
    checks.ok("목록에 없는 6칸 낱말을 페이지에서 골랐음", len(words) >= 2, str(words))
    word = words[0]
    seen = []
    ctl = route_lookup(page, FOUND, counter=seen)
    type_word(page, word)
    page.keyboard.press("Enter")
    ok = wait_toast(page, "에서 찾았습니다")
    checks.ok("'있음' 이면 `…에서 찾았습니다` 토스트", ok, str(toast_texts(page)))
    done = row_done(page, 0)
    checks.ok("줄이 하나 들어감(받아들인 낱말로 다시 제출됨)", done and filled_rows(page) == 1,
              f"states {row_states(page, 0)}, `찾았습니다` 토스트 {sum('찾았' in t for t in toast_texts(page))}개(1개여야 함)")
    checks.ok("낱말이 그대로 적힘", row_text(page, 0) == units_of(page, word), row_text(page, 0))
    empty_bg = tile_bg(page, 5, 0)
    checks.ok(
        "낸 줄의 칸에 색이 칠해짐(빈 칸과 다름)",
        all(tile_bg(page, 0, c) != empty_bg for c in range(6)),
        f"{tile_bg(page, 0, 0)} vs {empty_bg}",
    )
    checks.ok("조회 요청은 한 번", len(seen) == 1, str(seen))
    extra = json.loads(stored(page, "jamo.extraWords") or "[]")
    checks.ok("받아들인 낱말이 jamo.extraWords 에 저장됨", word in extra, str(extra))
    # 새로 고친 뒤 같은 낱말이 사전 조회 없이 받아들여짐(조회는 '없음' 으로 바꿔 둠)
    # 되풀이 조회가 돌고 있어도 멈추도록 먼저 오류로 바꾼 뒤 새로 고친다(제품이 멀쩡하면 이미 끝나 있음)
    ctl.update(payload=None, status=500)
    route_wiki_fail(page)
    page.wait_for_timeout(500)
    after = []
    ctl.update(payload=NOT_FOUND, status=200, counter=after)
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(120)
    dismiss_help(page)
    base_rows = filled_rows(page)
    type_word(page, word)
    page.keyboard.press("Enter")
    try:
        page.wait_for_function(
            "(n) => Array.from(document.querySelectorAll('#board .row')).filter((row) =>"
            " Array.from(row.querySelectorAll('.tile')).every((t) =>"
            " ['correct', 'present', 'absent'].includes(t.dataset.state))).length > n",
            arg=base_rows, timeout=4000)
        accepted = True
    except Exception:
        accepted = False
    page.wait_for_timeout(200)
    checks.ok("새로 고친 뒤 같은 낱말을 조회 없이 받아들임(extraWords)", accepted and len(after) == 0,
              f"조회 {len(after)}번, 줄 {base_rows}->{filled_rows(page)}")


def scenario_not_found(checks, page, base):
    word = unlisted_words(page)[0]
    route_lookup(page, NOT_FOUND)
    type_word(page, word)
    page.keyboard.press("Enter")
    ok = wait_toast(page, "낱말 목록에 없는 낱말입니다")
    checks.ok("'없음' 이면 `낱말 목록에 없는 낱말입니다` 토스트", ok, str(toast_texts(page)))
    page.wait_for_timeout(300)
    checks.ok("줄이 안 들어감", filled_rows(page) == 0, str(row_states(page, 0)))
    checks.ok("치던 글자는 그대로", row_text(page, 0) == units_of(page, word), row_text(page, 0))
    checks.ok("받아들인 낱말 저장 없음", json.loads(stored(page, "jamo.extraWords") or "[]") == [])


def scenario_error(checks, page, base):
    word = unlisted_words(page)[0]
    route_lookup(page, None, status=500)
    route_wiki_fail(page)
    type_word(page, word)
    page.keyboard.press("Enter")
    ok = wait_toast(page, "사전 조회 실패")
    checks.ok("라우트가 오류(500/abort)면 `사전 조회 실패` 토스트", ok, str(toast_texts(page)))
    page.wait_for_timeout(300)
    checks.ok("판은 그대로(줄 없음, 글자 남음)", filled_rows(page) == 0 and row_text(page, 0) == units_of(page, word))
    # 서버가 ok:false 를 200 으로 돌려주는 경우(키 없음 등)도 같은 토스트, 까닭이 보임
    route_lookup(page, {"ok": False, "source": "wiktionary", "via": "server", "error": "키가 없습니다: STDICT_API_KEY"})
    page.keyboard.press("Enter")
    ok2 = wait_toast(page, "키가 없습니다: STDICT_API_KEY")
    checks.ok("서버의 오류 까닭이 토스트에 그대로 나옴", ok2, str(toast_texts(page)))
    checks.ok("그래도 판은 그대로", filled_rows(page) == 0)


def scenario_off(checks, page, base):
    word = unlisted_words(page)[0]
    open_settings(page)
    page.locator("#dict-on").uncheck()
    checks.ok("#dict-on 을 끄면 꺼진 채로", not page.locator("#dict-on").is_checked())
    saved = json.loads(stored(page, "jamo.dict") or "{}")
    checks.ok("꺼짐이 jamo.dict 에 저장됨", saved.get("on") is False, str(saved))
    close_settings(page)
    seen = watch_requests(page)
    route_lookup(page, FOUND)
    type_word(page, word)
    page.keyboard.press("Enter")
    ok = wait_toast(page, "낱말 목록에 없는 낱말입니다")
    checks.ok("끄면 바로 기존 거절 토스트", ok, str(toast_texts(page)))
    page.wait_for_timeout(300)
    checks.ok("끄면 조회 요청이 안 나감(요청 수 0)", len(seen) == 0, str(seen))
    checks.ok("줄이 안 들어감", filled_rows(page) == 0)


def scenario_double_enter(checks, page, base):
    word = unlisted_words(page)[0]
    pending = []
    seen = []

    def hold(route):
        seen.append(route.request.url)
        pending.append(route)

    page.route(LOOKUP_URL, hold)
    type_word(page, word)
    page.keyboard.press("Enter")
    checks.ok("조회 중 토스트 `사전 확인 중…`", wait_toast(page, "사전 확인 중"), str(toast_texts(page)))
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    page.keyboard.press("Backspace")
    page.wait_for_timeout(300)
    checks.ok("Enter 를 더 눌러도 조회 요청은 하나", len(seen) == 1, str(seen))
    checks.ok("조회 중 지우기는 받지 않음", row_text(page, 0) == units_of(page, word), row_text(page, 0))
    for route in pending:
        fulfill_json(route, FOUND)
    row_done(page, 0)
    page.wait_for_timeout(300)
    checks.ok("줄은 하나만 들어감", filled_rows(page) == 1, str(filled_rows(page)))
    checks.ok("둘째 줄은 비어 있음", set(row_states(page, 1)) <= {"empty"}, str(row_states(page, 1)))
    checks.ok("끝내 요청 하나", len(seen) == 1, str(seen))


def scenario_customs(checks, page, base):
    open_settings(page)
    page.locator("#set-dict details.dict-add-box summary").click()
    page.wait_for_timeout(60)
    checks.ok("더하기 칸이 열려 보임", page.locator("#dict-add-url").is_visible())
    page.fill("#dict-add-name", "내 모델")
    page.fill("#dict-add-url", "http://example.com/v1")
    page.fill("#dict-add-model", "test-model")
    page.fill("#dict-add-key", "sk-test")
    page.click("#dict-add")
    page.wait_for_timeout(60)
    status = page.locator("#dict-status").text_content() or ""
    checks.ok("http:// 주소는 거절 글", "https://" in status and page.locator("#dict-customs li").count() == 0, status)
    checks.ok("거절하면 저장하지 않음", not (json.loads(stored(page, "jamo.dict") or "{}").get("customs")))
    page.fill("#dict-add-url", "https://example.com/v1")
    page.click("#dict-add")
    page.wait_for_timeout(80)
    checks.ok("https:// 는 #dict-customs 에 줄이 생김", page.locator("#dict-customs li").count() == 1)
    checks.ok("줄이 보이고 이름이 적힘", page.locator("#dict-customs li").first.is_visible()
              and "내 모델" in (page.locator("#dict-customs li").first.text_content() or ""))
    saved = json.loads(stored(page, "jamo.dict") or "{}")
    checks.ok("저장됨(jamo.dict.customs)", len(saved.get("customs", [])) == 1, str(saved))
    options = page.evaluate(
        "() => Array.from(document.querySelectorAll('#dict-source option')).map((o) => o.textContent)"
    )
    checks.ok("출처 목록에 더한 모델이 들어가 고른 상태", any("내 모델" in o for o in options)
              and "내 모델" in page.evaluate(
                  "() => document.getElementById('dict-source').selectedOptions[0].textContent"))
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(120)
    open_settings(page)
    checks.ok("새로 고쳐도 줄이 남음", page.locator("#dict-customs li").count() == 1)
    del_box = box(page, "#dict-customs li .dict-del")
    li_box = box(page, "#dict-customs li")
    checks.ok(".dict-del 이 보이고 줄 안에 있음",
              page.locator("#dict-customs li .dict-del").is_visible() and bool(del_box and li_box and inside(del_box, li_box)))
    page.locator("#dict-customs li .dict-del").first.click()
    page.wait_for_timeout(80)
    checks.ok(".dict-del 로 지워짐", page.locator("#dict-customs li").count() == 0)
    saved = json.loads(stored(page, "jamo.dict") or "{}")
    checks.ok("지운 뒤 저장도 비고 출처는 기본으로 돌아감",
              not saved.get("customs") and saved.get("source") == "wiktionary", str(saved))


def scenario_narrow(checks, page, base):
    open_settings(page)
    page.locator("#set-dict details.dict-add-box summary").click()
    page.fill("#dict-add-name", "아주긴이름의모델아주긴이름의모델아주긴이름의모델")
    page.fill("#dict-add-url", "https://example.com/v1/아주/긴/주소/아주/긴/주소/아주/긴/주소")
    page.fill("#dict-add-model", "very-long-model-name-for-layout-check-0123456789")
    page.click("#dict-add")
    page.select_option("#dict-source", "gemini")
    page.wait_for_timeout(100)
    vw = page.evaluate("() => document.documentElement.clientWidth")
    sw = page.evaluate("() => document.documentElement.scrollWidth")
    checks.ok("320px: 문서가 가로로 넘치지 않음", sw <= vw, f"scrollWidth {sw} > clientWidth {vw}")
    over = page.evaluate(
        """() => {
          const modal = document.getElementById('modal-settings');
          const bad = [];
          for (const el of modal.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            if (r.left < -1 || r.right > document.documentElement.clientWidth + 1) {
              bad.push((el.id || el.className || el.tagName) + ':' + Math.round(r.left) + '~' + Math.round(r.right));
            }
          }
          const sc = Array.from(modal.querySelectorAll('*')).filter((e) => e.scrollWidth > e.clientWidth + 1
            && getComputedStyle(e).overflowX === 'visible' && e.clientWidth > 0)
            .map((e) => (e.id || e.className || e.tagName) + ':' + e.scrollWidth + '>' + e.clientWidth);
          return {bad, sc};
        }"""
    )
    checks.ok("320px: 설정 창 안 요소가 모두 화면 폭 안", not over["bad"], str(over["bad"][:4]))
    checks.ok("320px: 안쪽에서 삐져나오는 글·입력이 없음", not over["sc"], str(over["sc"][:4]))
    for sel in ("#dict-source", "#dict-key", "#dict-test", "#dict-add", "#dict-on"):
        b = box(page, sel)
        checks.ok(f"320px: {sel} 가 화면 안에 보임",
                  page.locator(sel).first.is_visible() and bool(b and b["x"] >= -1 and b["x"] + b["width"] <= vw + 1),
                  str(b))
    shot(page, "settings-dict-320")


def scenario_test_button(checks, page, base):
    route_lookup(page, {**FOUND, "evidence": "가짜 근거"})
    open_settings(page)
    checks.ok("#dict-status 는 aria-live=polite", page.get_attribute("#dict-status", "aria-live") == "polite")
    page.click("#dict-test")
    try:
        page.wait_for_function(
            "() => /한국/.test(document.getElementById('dict-status').textContent)", timeout=4000
        )
    except Exception:
        pass
    status = page.locator("#dict-status").text_content() or ""
    checks.ok("#dict-test 가 #dict-status 에 결과를 씀", "한국" in status and "있음" in status, status)
    checks.ok("근거 글이 함께 나옴", "가짜 근거" in status, status)
    checks.ok("#dict-status 가 보임", page.locator("#dict-status").is_visible())
    route_lookup(page, None, status=500)
    route_wiki_fail(page)
    page.click("#dict-test")
    page.wait_for_timeout(600)
    status2 = page.locator("#dict-status").text_content() or ""
    checks.ok("조회가 오류면 결과 글에 실패가 적힘", "실패" in status2, status2)


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
                run("있음", checks, scenario_found, browser, base)
                run("없음", checks, scenario_not_found, browser, base)
                run("오류", checks, scenario_error, browser, base)
                run("끔", checks, scenario_off, browser, base)
                run("Enter 두 번", checks, scenario_double_enter, browser, base)
                run("사용자 LLM", checks, scenario_customs, browser, base)
                run("320px", checks, scenario_narrow, browser, base, viewport=VP_SMALL)
                run("확인해 보기", checks, scenario_test_button, browser, base)
            finally:
                browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(main())
