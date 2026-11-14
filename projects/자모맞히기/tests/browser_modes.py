#!/usr/bin/env python3
"""자모맞히기 모드 오가기·시스템 테마·키 입력 회귀 검사 (R24-N4~N9·N12·N13).

그려진 화면을 묻습니다: is_visible(), getComputedStyle(), bounding_box().
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from browser_harness import Checks, new_page, server, set_group  # noqa: E402

set_group("modes")

README = HERE.parent / "README.md"
PAIR_RE = re.compile(r"[ㄱ-ㅣ]{1,2}=[ㄱ-ㅣ]{1,2}")
COMPOUND_VOWELS = set("ㅘㅙㅚㅝㅞㅟㅢ")

FAKE_DATE = """(() => {
  const RealDate = Date;
  const fixed = new RealDate(2026, 10, 12, 10, 0, 0).getTime();
  class FakeDate extends RealDate {
    constructor(...args) { if (args.length === 0) super(fixed); else super(...args); }
    static now() { return fixed; }
  }
  globalThis.Date = FakeDate;
})();"""

# 날짜를 하루 밀고 focus 이벤트로 checkNewDay 를 부른다. 새 날 처리를 화면에서 그대로 겪기 위해.
NEXT_DAY_JS = """() => {
  const RealDate = Date;
  const later = new RealDate();
  later.setDate(later.getDate() + 1);
  const shifted = later.getTime();
  class FakeDate extends RealDate {
    constructor(...args) { if (args.length === 0) super(shifted); else super(...args); }
    static now() { return shifted; }
  }
  globalThis.Date = FakeDate;
  window.dispatchEvent(new Event('focus'));
}"""


# ---------------------------------------------------------------- 페이지


def open_page(browser, base, viewport=None, color_scheme=None, clipboard=False, init_scripts=()):
    if not color_scheme and not init_scripts:
        page = new_page(browser, base, viewport=viewport, clipboard=clipboard)
        page.wait_for_timeout(80)
        return page
    # N9 의 color_scheme, N13 의 Date 고정은 new_page() 가 받지 않아 문맥을 직접 만든다.
    options = {"viewport": viewport or {"width": 420, "height": 900}}
    if color_scheme:
        options["color_scheme"] = color_scheme
    if clipboard:
        options["permissions"] = ["clipboard-read", "clipboard-write"]
    context = browser.new_context(**options)
    for script in init_scripts:
        context.add_init_script(script)
    page = context.new_page()
    page._errors = []
    page._context = context

    def collect_error(error):
        page._errors.append(f"pageerror: {error}")

    def collect_console(message):
        if message.type == "error":
            page._errors.append(f"console: {message.text}")

    page.on("pageerror", collect_error)
    page.on("console", collect_console)
    page.goto(base + "/index.html", wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(80)
    return page


def dismiss_help(page):
    if page.locator("#modal-help:not([hidden])").count():
        page.keyboard.press("Escape")
        page.wait_for_function(
            "() => document.getElementById('modal-help').hidden === true"
        )


# ---------------------------------------------------------------- 도우미


def tile(page, row, col):
    return page.locator(
        f"#board .row:nth-child({row + 1}) .tile:nth-child({col + 1})"
    )


def tile_state(page, row, col):
    return tile(page, row, col).get_attribute("data-state")


def tile_text(page, row, col):
    return tile(page, row, col).text_content() or ""


def row_snapshot(page, row):
    return page.evaluate(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile'))"
        ".map((t) => ({state: t.dataset.state, text: t.textContent}))",
        row + 1,
    )


def board_snapshot(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .tile'))"
        ".map((t) => ({state: t.dataset.state, text: t.textContent}))"
    )


def row_text(page, row):
    return "".join(item["text"] for item in row_snapshot(page, row))


def toast_texts(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".map((t) => t.textContent)"
    )


def preview_text(page):
    return page.locator("#preview").text_content() or ""


def colored_key_count(page):
    return page.evaluate(
        "() => document.querySelectorAll('#keyboard .key[data-state]').length"
    )


def wait_row_done(page, row, timeout=5000):
    page.wait_for_function(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile'))"
        ".every((t) => ['correct', 'present', 'absent'].includes(t.dataset.state))",
        arg=row + 1,
        timeout=timeout,
    )


def wait_settled(page, row, timeout=6000):
    wait_row_done(page, row, timeout=timeout)
    page.wait_for_function(
        "() => document.querySelectorAll('#board .tile.flip').length === 0",
        timeout=timeout,
    )
    page.wait_for_timeout(140)


def answer_word(page):
    return page.evaluate(
        "async () => { const g = await import('./js/game.js');"
        " const w = await import('./js/words.js');"
        " return g.answerForDate(new Date(), w.ANSWERS, w.TREND); }"
    )


def units_of(page, word):
    return page.evaluate(
        "async (w) => { const j = await import('./js/jamo.js'); return j.toUnits(w); }",
        word,
    )


def allowed_pairs(page):
    return page.evaluate(
        "async () => { const w = await import('./js/words.js');"
        " const j = await import('./js/jamo.js');"
        " return w.ALLOWED.map((word) => [word, j.toUnits(word)]); }"
    )


def keyboard_reverse(page):
    return page.evaluate(
        "async () => { const j = await import('./js/jamo.js'); const out = {};"
        " for (const [code, pair] of Object.entries(j.KEYMAP)) {"
        "   out[pair[0]] = [code, false];"
        "   if (pair[1] !== pair[0]) out[pair[1]] = [code, true];"
        " } return out; }"
    )


def type_units(page, units):
    rev = keyboard_reverse(page)
    for unit in units:
        if unit not in rev:
            raise AssertionError(f"자판에 없는 칸: {unit!r}")
        code, shifted = rev[unit]
        page.keyboard.press(("Shift+" if shifted else "") + code)


def six_wrongs(pairs, answer_units):
    out = []
    seen = set()
    for word, units in pairs:
        if not units or len(units) != 6 or units == answer_units or units in seen:
            continue
        seen.add(units)
        out.append((word, units))
        if len(out) == 6:
            return out
    raise AssertionError("틀린 낱말 여섯 개를 찾지 못했습니다")


def first_wrong(pairs, answer_units):
    for word, units in pairs:
        if units and len(units) == 6 and units != answer_units:
            return word, units
    raise AssertionError("틀린 낱말을 찾지 못했습니다")


def rgb_of(value):
    parts = value[value.find("(") + 1 : value.find(")")].split(",")
    return tuple(float(p.strip()) for p in parts[:3])


def brightness(value):
    r, g, b = rgb_of(value)
    return (r * 299 + g * 587 + b * 114) / 1000


def body_color(page):
    return page.evaluate("() => getComputedStyle(document.body).backgroundColor")


def theme_name(page):
    return page.evaluate("() => document.documentElement.dataset.theme")


def empty_board(page):
    return all(item["state"] == "empty" and item["text"] == "" for item in board_snapshot(page))


def answer_toasts(page):
    return [text for text in toast_texts(page) if text.startswith("정답: ")]


def readme_rule_section():
    text = README.read_text(encoding="utf-8")
    match = re.search(r"^## 규칙.*?$(.*?)^## ", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def lose_practice(page):
    """연습 판에서 여섯 번 틀려 진 뒤 정답 토스트가 뜬 상태로 돌려준다(Math.random=0 가정)."""
    page.click("#mode-practice")
    page.wait_for_timeout(200)
    word = page.evaluate("async () => (await import('./js/words.js')).ANSWERS[0]")
    answer = units_of(page, word)
    for row, (_word, guess) in enumerate(six_wrongs(allowed_pairs(page), answer)):
        type_units(page, guess)
        page.keyboard.press("Enter")
        wait_settled(page, row)
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => (t.textContent || '').startsWith('정답: '))",
        timeout=3000,
    )
    return word, answer


# ---------------------------------------------------------------- 시나리오


def scenario_enter_buttons(page, checks):
    dismiss_help(page)

    page.focus("#mode-practice")
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    checks.ok(
        "N4 Enter - #mode-practice 가 눌림",
        page.get_attribute("#mode-practice", "aria-pressed") == "true"
        and page.get_attribute("#mode-daily", "aria-pressed") == "false",
        f"practice={page.get_attribute('#mode-practice', 'aria-pressed')}"
        f" daily={page.get_attribute('#mode-daily', 'aria-pressed')}",
    )
    checks.ok(
        "N4 Enter - 연습 새 판이 보이고 제출 안내가 없음",
        empty_board(page) and not any("자모 6개" in text for text in toast_texts(page)),
        f"토스트 {toast_texts(page)}",
    )

    type_units(page, "ㅎㅏㄴ")
    checks.ok(
        "N4 Enter - 연습 판에 세 칸을 침",
        row_text(page, 0)[:3] == "ㅎㅏㄴ",
        f"실제 {row_text(page, 0)!r}",
    )
    page.focus("#btn-new")
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    checks.ok(
        "N4 Enter - #btn-new 가 보임",
        page.locator("#btn-new").is_visible(),
    )
    checks.ok(
        "N4 Enter - #btn-new 가 새 판을 열고 제출 안내가 없음",
        empty_board(page) and not any("자모 6개" in text for text in toast_texts(page)),
        f"첫 줄 {row_text(page, 0)!r}, 토스트 {toast_texts(page)}",
    )

    page.focus("#mode-daily")
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    checks.ok(
        "N4 Enter - #mode-daily 가 눌림",
        page.get_attribute("#mode-daily", "aria-pressed") == "true"
        and page.get_attribute("#mode-practice", "aria-pressed") == "false",
        f"daily={page.get_attribute('#mode-daily', 'aria-pressed')}"
        f" practice={page.get_attribute('#mode-practice', 'aria-pressed')}",
    )
    checks.ok(
        "N4 Enter - 모드 단추에 Enter 를 쳐도 제출 안내가 없음",
        not any("자모 6개" in text for text in toast_texts(page)),
        f"토스트 {toast_texts(page)}",
    )


def scenario_answer_toast(page, checks):
    dismiss_help(page)
    page.click("#mode-practice")
    page.wait_for_timeout(200)

    word = page.evaluate(
        "async () => (await import('./js/words.js')).ANSWERS[0]"
    )
    answer = units_of(page, word)
    wrongs = six_wrongs(allowed_pairs(page), answer)
    for row, (_word, guess) in enumerate(wrongs):
        type_units(page, guess)
        page.keyboard.press("Enter")
        wait_settled(page, row)

    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => (t.textContent || '').startsWith('정답: '))",
        timeout=5000,
    )
    lost_board = board_snapshot(page)
    checks.ok(
        "N5 연습에서 짐 - 그 판의 정답 토스트가 보임",
        answer_toasts(page) == [f"정답: {word}"]
        and page.locator("#toasts .toast").first.is_visible(),
        f"실제 {toast_texts(page)} / 기대 정답: {word}",
    )

    page.click("#mode-daily")
    page.wait_for_timeout(2600)
    checks.ok(
        "N5 날마다로 가면 정답 토스트가 안 보임",
        not answer_toasts(page),
        f"실제 {toast_texts(page)}",
    )
    checks.ok(
        "N6 연습에서 진 직후 날마다로 가면 2.5초 뒤 통계 창이 안 열림",
        not page.locator("#modal-stats").is_visible(),
    )

    page.click("#mode-practice")
    page.wait_for_timeout(350)
    checks.ok(
        "N5 연습으로 돌아오면 그 판이 그대로 보임",
        board_snapshot(page) == lost_board,
        f"첫 줄 {row_text(page, 0)!r}",
    )
    checks.ok(
        "N5 연습으로 돌아오면 그 판의 정답 토스트만 보임",
        toast_texts(page) == [f"정답: {word}"],
        f"실제 {toast_texts(page)}",
    )

    page.click("#btn-new")
    page.wait_for_timeout(250)
    checks.ok(
        "N5 #btn-new 뒤 정답 토스트가 사라지고 빈 판이 됨",
        not answer_toasts(page) and empty_board(page),
        f"토스트 {toast_texts(page)}, 첫 줄 {row_text(page, 0)!r}",
    )


def scenario_new_day_practice_toast(page, checks):
    dismiss_help(page)
    word, answer = lose_practice(page)
    wrongs = six_wrongs(allowed_pairs(page), answer)

    # 날이 바뀌어도 화면은 진 연습 판 그대로다 - 정답 토스트가 사라지면 안 된다.
    page.evaluate(NEXT_DAY_JS)
    page.wait_for_timeout(300)
    answer_toast = page.locator("#toasts .toast", has_text="정답:")
    checks.ok(
        "N4 새 날 - 연습에서 진 판의 정답 토스트가 보임",
        answer_toasts(page) == [f"정답: {word}"]
        and answer_toast.count() == 1 and answer_toast.first.is_visible(),
        f"실제 {toast_texts(page)} / 기대 정답: {word}",
    )
    checks.ok(
        "N4 새 날 - 연습 단추가 눌린 채 그대로",
        page.get_attribute("#mode-practice", "aria-pressed") == "true"
        and page.get_attribute("#mode-daily", "aria-pressed") == "false",
        f"practice={page.get_attribute('#mode-practice', 'aria-pressed')}"
        f" daily={page.get_attribute('#mode-daily', 'aria-pressed')}",
    )
    checks.ok(
        "N4 새 날 - 화면은 여전히 진 연습 판",
        page.locator("#btn-new").is_visible() and row_text(page, 0) == wrongs[0][1],
        f"첫 줄 {row_text(page, 0)!r}",
    )


def scenario_btn_new_cancels_stats(page, checks):
    dismiss_help(page)
    lose_practice(page)

    # 진 직후(통계 창이 열리기 전) 새 판을 열면 예약된 통계 창이 취소돼야 한다.
    page.click("#btn-new")
    page.wait_for_timeout(2500)
    checks.ok(
        "N6 연습에서 진 직후 #btn-new - 2.5초 뒤 통계 창이 안 보임",
        not page.locator("#modal-stats").is_visible(),
    )
    checks.ok(
        "N6 연습에서 진 직후 #btn-new - 빈 새 판이 보이고 정답 토스트가 사라짐",
        empty_board(page) and not answer_toasts(page),
        f"토스트 {toast_texts(page)}, 첫 줄 {row_text(page, 0)!r}",
    )


def scenario_stats_highlight(page, checks):
    dismiss_help(page)
    page.click("#mode-practice")
    page.wait_for_timeout(200)
    word = page.evaluate("async () => (await import('./js/words.js')).ANSWERS[0]")
    type_units(page, units_of(page, word))
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    hl = page.locator("#dist .bar.hl")
    checks.ok(
        "N6 연습에서 이긴 뒤 통계 - 강조 막대가 없음",
        hl.count() == 0,
        f"강조 막대 {hl.count()}개",
    )
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-stats').hidden === true")

    page.click("#mode-daily")
    page.wait_for_timeout(200)
    type_units(page, units_of(page, answer_word(page)))
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    hl = page.locator("#dist .bar.hl")
    checks.ok(
        "N6 날마다에서 이긴 뒤 통계 - 강조 막대가 보임",
        hl.count() == 1 and hl.first.is_visible(),
        f"강조 막대 {hl.count()}개",
    )


def scenario_saved_hard_empty_daily(page, checks):
    dismiss_help(page)
    # 저장 설정은 하드=켬인데 저장된 오늘 판은 빈 판·하드 아님 - 새로 고침하면 설정을 따라야 한다.
    page.evaluate(
        """async () => {
          const W = await import('./js/words.js');
          const J = await import('./js/jamo.js');
          const G = await import('./js/game.js');
          const now = new Date();
          const answer = J.toUnits(G.answerForDate(now, W.ANSWERS, W.TREND));
          const p = (n) => String(n).padStart(2, '0');
          const key = 'jamo.daily.' + now.getFullYear() + '-' + p(now.getMonth() + 1)
            + '-' + p(now.getDate());
          localStorage.setItem(key, JSON.stringify({
            answer, rows: [], current: '', status: 'playing',
            hardMode: false, puzzleNumber: Math.max(1, G.dailyIndex(now) + 1),
            maxGuesses: 6,
          }));
          localStorage.setItem('jamo.settings', JSON.stringify({
            hardMode: true, dark: false, colorblind: false,
          }));
        }"""
    )
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(200)
    dismiss_help(page)

    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    checks.ok(
        "N6 저장 설정 하드=켬 + 빈 날마다 판 - 첫 제출 전 체크박스가 켜져 보임",
        page.locator("#set-hard").is_visible() and page.is_checked("#set-hard"),
        f"체크 {page.is_checked('#set-hard')}",
    )
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")

    type_units(page, units_of(page, answer_word(page)))
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    checks.ok(
        "N6 하드 날마다 판에서 이긴 뒤 공유 단추가 보임",
        page.locator("#btn-share").is_visible(),
    )
    page.click("#btn-share")
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => t.textContent.includes('클립보드에 복사했습니다'))",
        timeout=3000,
    )
    text = page.evaluate("() => navigator.clipboard.readText()")
    first = text.split("\n")[0]
    checks.ok(
        "N6 이긴 공유 글 첫 줄이 '*' 로 끝남(하드)",
        first.startswith("자모맞히기 ") and first.endswith("*"),
        f"실제 {first!r}",
    )


def scenario_busy_input(page, checks):
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    _word, guess = first_wrong(allowed_pairs(page), answer)
    type_units(page, guess)
    page.keyboard.press("Enter")
    page.wait_for_timeout(30)
    page.keyboard.press("KeyR")
    page.wait_for_timeout(270)

    next_row = row_snapshot(page, 1)
    checks.ok(
        "N7 뒤집는 중 실물 KeyR - 다음 줄이 빈칸 그대로",
        all(item["state"] == "empty" and item["text"] == "" for item in next_row),
        f"실제 {''.join(item['text'] for item in next_row)!r}",
    )
    checks.ok(
        "N7 뒤집기가 끝나기 전 자판 키에 색이 없음",
        colored_key_count(page) == 0,
        f"색 칠한 키 {colored_key_count(page)}개",
    )

    wait_settled(page, 0)
    checks.ok(
        "N7 뒤집기가 끝나도 다음 줄은 빈칸",
        row_text(page, 1) == "",
        f"실제 {row_text(page, 1)!r}",
    )
    checks.ok(
        "N7 제출한 첫 줄은 판정됨",
        "".join(item["text"] for item in row_snapshot(page, 0)) == guess
        and all(item["state"] in ("correct", "present", "absent") for item in row_snapshot(page, 0)),
        f"실제 {row_text(page, 0)!r}",
    )


def scenario_hard_mode(page, checks):
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    _word, guess = first_wrong(allowed_pairs(page), answer)
    type_units(page, guess)
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    checks.ok(
        "N8 날마다 판에 한 줄을 제출함",
        row_text(page, 0) == guess
        and all(item["state"] in ("correct", "present", "absent") for item in row_snapshot(page, 0)),
        f"실제 {row_text(page, 0)!r}",
    )

    page.click("#mode-practice")
    page.wait_for_timeout(200)
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    checks.ok(
        "N8 설정 - 연습 판의 하드 모드는 꺼짐으로 보임",
        page.locator("#set-hard").is_visible() and not page.is_checked("#set-hard"),
    )
    page.check("#set-hard")
    page.wait_for_timeout(250)
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")

    page.click("#mode-daily")
    page.wait_for_timeout(200)
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    checks.ok(
        "N8 날마다로 돌아오면 체크박스가 날마다 판 값(꺼짐)을 보임",
        page.locator("#set-hard").is_visible() and not page.is_checked("#set-hard"),
    )
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('jamo.settings'))")
    checks.ok(
        "N8 하드 모드 켠 값은 설정에 저장됨",
        isinstance(stored, dict) and stored.get("hardMode") is True,
        f"실제 {stored}",
    )
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")

    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(200)
    dismiss_help(page)
    checks.ok(
        "N8 새로 고침 뒤에도 날마다 판 한 줄이 그대로",
        row_text(page, 0) == guess,
        f"실제 {row_text(page, 0)!r}",
    )
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    checks.ok(
        "N8 새로 고침 뒤에도 체크박스는 날마다 판 값(꺼짐)을 보임",
        page.locator("#set-hard").is_visible() and not page.is_checked("#set-hard"),
    )
    stored_after = page.evaluate("() => JSON.parse(localStorage.getItem('jamo.settings'))")
    checks.ok(
        "N8 새로 고침 뒤에도 켠 설정값은 남아 있음",
        isinstance(stored_after, dict) and stored_after.get("hardMode") is True,
        f"실제 {stored_after}",
    )


def scenario_system_dark(page, checks):
    dismiss_help(page)
    first = body_color(page)
    checks.ok(
        "N9 어두운 시스템 문맥 - 첫 방문 body 배경이 어두움",
        brightness(first) < 80 and theme_name(page) == "dark",
        f"실제 {first} 밝기 {brightness(first):.1f}, 테마 {theme_name(page)}",
    )
    checks.ok(
        "N9 어두운 시스템 문맥 - prefers-color-scheme 가 어두움",
        page.evaluate("() => matchMedia('(prefers-color-scheme: dark)').matches"),
    )

    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    checks.ok(
        "N9 어두운 시스템 첫 방문 - 설정의 어두운 테마가 켜져 보임",
        page.is_checked("#set-dark"),
    )
    page.uncheck("#set-dark")
    page.wait_for_function("() => document.documentElement.dataset.theme === 'light'")
    light = body_color(page)
    checks.ok(
        "N9 설정에서 어두운 테마를 끄면 body 배경이 실제로 밝아짐",
        brightness(light) > 150 and theme_name(page) == "light",
        f"실제 {light} 밝기 {brightness(light):.1f}",
    )

    page.keyboard.press("Escape")
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(200)
    persisted = body_color(page)
    checks.ok(
        "N9 새로 고침 뒤에도 꺼진 테마가 유지됨(시스템이 어두워도)",
        brightness(persisted) > 150 and theme_name(page) == "light",
        f"실제 {persisted} 밝기 {brightness(persisted):.1f}, 테마 {theme_name(page)}",
    )


def scenario_system_light(page, checks):
    dismiss_help(page)
    first = body_color(page)
    checks.ok(
        "N9 밝은 시스템 문맥 - 첫 방문 body 배경이 밝음",
        brightness(first) > 150 and theme_name(page) == "light",
        f"실제 {first} 밝기 {brightness(first):.1f}, 테마 {theme_name(page)}",
    )
    checks.ok(
        "N9 밝은 시스템 문맥 - prefers-color-scheme 가 어둡지 않음",
        not page.evaluate("() => matchMedia('(prefers-color-scheme: dark)').matches"),
    )


def scenario_future_clock(page, checks):
    dismiss_help(page)
    checks.ok(
        "N13 시험용 시계가 2026-11-12 로 고정됨",
        page.evaluate(
            "() => new Date().getFullYear() === 2026"
            " && new Date().getMonth() === 10 && new Date().getDate() === 12"
        ),
        f"실제 {page.evaluate('() => new Date().toString()')}",
    )
    word = answer_word(page)
    type_units(page, units_of(page, word))
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    checks.ok(
        "N13 날마다 판에서 이긴 뒤 공유 단추가 보임",
        page.locator("#btn-share").is_visible(),
    )
    page.click("#btn-share")
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => t.textContent.includes('클립보드에 복사했습니다'))",
        timeout=3000,
    )
    text = page.evaluate("() => navigator.clipboard.readText()")
    first = text.split("\n")[0]
    checks.ok(
        "N13 공유 첫 줄이 '자모맞히기 1 …' (연습 아님)",
        first == "자모맞히기 1 1/6" and "연습" not in first,
        f"실제 {first!r}",
    )


def scenario_process_key(page, checks):
    dismiss_help(page)
    page.evaluate(
        "() => document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 'Process', code: 'KeyR', bubbles: true}))"
    )
    page.wait_for_timeout(50)
    checks.ok(
        "N12 Process 키 - KeyR 이 ㄱ 한 칸으로 보임",
        tile_text(page, 0, 0) == "ㄱ"
        and tile_state(page, 0, 0) == "filled"
        and tile(page, 0, 0).is_visible(),
        f"실제 {tile_text(page, 0, 0)!r}/{tile_state(page, 0, 0)!r}",
    )
    page.evaluate(
        "() => document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 'Process', code: 'KeyR', shiftKey: true, bubbles: true}))"
    )
    page.wait_for_timeout(50)
    checks.ok(
        "N12 Process 키 - Shift+KeyR 이 ㄲ 한 칸으로 보임",
        tile_text(page, 0, 1) == "ㄲ"
        and tile_state(page, 0, 1) == "filled"
        and tile(page, 0, 1).is_visible(),
        f"실제 {tile_text(page, 0, 1)!r}/{tile_state(page, 0, 1)!r}",
    )
    checks.ok(
        "N12 Process 키 - 두 칸이 화면에 보임",
        tile(page, 0, 0).is_visible() and tile(page, 0, 1).is_visible(),
    )


def scenario_practice_resume(page, checks):
    dismiss_help(page)
    page.click("#mode-practice")
    page.wait_for_timeout(200)
    type_units(page, "ㅎㅏㄴ")
    checks.ok(
        "N12 연습 이어 하기 - 연습 판에 세 칸을 침",
        row_text(page, 0)[:3] == "ㅎㅏㄴ",
        f"실제 {row_text(page, 0)!r}",
    )
    page.click("#mode-daily")
    page.wait_for_timeout(200)
    checks.ok(
        "N12 연습 이어 하기 - 날마다 판에는 연습 칸이 없음",
        row_text(page, 0) == "",
        f"실제 {row_text(page, 0)!r}",
    )
    page.click("#mode-practice")
    page.wait_for_timeout(250)
    checks.ok(
        "N12 연습 이어 하기 - 연습으로 돌아오면 세 칸 그대로",
        page.get_attribute("#mode-practice", "aria-pressed") == "true"
        and row_text(page, 0)[:3] == "ㅎㅏㄴ",
        f"실제 {row_text(page, 0)!r}",
    )
    checks.ok(
        "N12 연습 이어 하기 - 세 칸이 화면에 보임",
        all(tile(page, 0, c).is_visible() for c in range(3)),
    )


def scenario_flip_mode_lock(page, checks):
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    _word, guess = first_wrong(allowed_pairs(page), answer)
    type_units(page, guess)
    page.keyboard.press("Enter")
    page.wait_for_timeout(60)
    page.click("#mode-practice")
    page.wait_for_timeout(300)
    checks.ok(
        "N12 뒤집기 중 모드 바꿈 무시 - 모드가 날마다 그대로",
        page.get_attribute("#mode-daily", "aria-pressed") == "true"
        and page.get_attribute("#mode-practice", "aria-pressed") == "false",
        f"daily={page.get_attribute('#mode-daily', 'aria-pressed')}"
        f" practice={page.get_attribute('#mode-practice', 'aria-pressed')}",
    )
    checks.ok(
        "N12 뒤집기 중 모드 바꿈 무시 - 연습 새 판이 안 보임",
        not page.locator("#btn-new").is_visible(),
    )
    wait_settled(page, 0)
    row = row_snapshot(page, 0)
    checks.ok(
        "N12 뒤집기 중 모드 바꿈 무시 - 날마다 첫 줄이 판정됨",
        "".join(item["text"] for item in row) == guess
        and all(item["state"] in ("correct", "present", "absent") for item in row),
        f"실제 {''.join(item['text'] for item in row)!r}",
    )


def scenario_preview_fixed(page, checks):
    dismiss_help(page)
    type_units(page, "ㄷㅏㄹㄱ")
    checks.ok(
        "N12 미리보기 고정값 - ㄷㅏㄹㄱ 이 '닭'",
        preview_text(page) == "닭" and page.locator("#preview").is_visible(),
        f"실제 {preview_text(page)!r}",
    )
    for _ in range(4):
        page.keyboard.press("Backspace")
    type_units(page, "ㄱㅏㅂㅅㅣ")
    checks.ok(
        "N12 미리보기 고정값 - ㄱㅏㅂㅅㅣ 가 '갑시'",
        preview_text(page) == "갑시" and page.locator("#preview").is_visible(),
        f"실제 {preview_text(page)!r}",
    )


def scenario_help_table(page, checks):
    dismiss_help(page)
    page.click("#btn-help")
    page.wait_for_selector("#modal-help:not([hidden])", timeout=3000)
    modal = page.locator("#modal-help")
    checks.ok("N12 도움말↔README - 도움말 창이 보임", modal.is_visible())
    text = modal.text_content() or ""
    help_pairs = PAIR_RE.findall(text)

    rule = readme_rule_section()
    readme_pairs = PAIR_RE.findall(rule)
    readme_vowels = sorted(p for p in readme_pairs if p.split("=")[0] in COMPOUND_VOWELS)
    readme_finals = sorted(p for p in readme_pairs if p.split("=")[0] not in COMPOUND_VOWELS)
    checks.ok(
        "N12 도움말↔README - README 규칙 절에 겹모음 7·겹받침 11 짝",
        len(readme_vowels) == 7 and len(readme_finals) == 11,
        f"겹모음 {len(readme_vowels)}, 겹받침 {len(readme_finals)}: {readme_pairs}",
    )
    help_vowels = sorted(p for p in help_pairs if p.split("=")[0] in COMPOUND_VOWELS)
    help_finals = sorted(p for p in help_pairs if p.split("=")[0] not in COMPOUND_VOWELS)
    checks.ok(
        "N12 도움말↔README - 겹모음 7짝이 README 와 같음",
        help_vowels == readme_vowels,
        f"도움말 {help_vowels} / README {readme_vowels}",
    )
    checks.ok(
        "N12 도움말↔README - 겹받침 11짝이 README 와 같음",
        help_finals == readme_finals,
        f"도움말 {help_finals} / README {readme_finals}",
    )


# ---------------------------------------------------------------- 실행


def open_settings_checked(page):
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    visible = page.locator("#set-hard").is_visible()
    value = page.is_checked("#set-hard")
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")
    return visible, value


def set_hard_in_practice(page, on):
    page.click("#mode-practice")
    page.wait_for_timeout(200)
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    page.set_checked("#set-hard", on)
    page.wait_for_timeout(250)
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")


def scenario_hard_reaches_empty_board(page, checks):
    dismiss_help(page)
    set_hard_in_practice(page, True)
    page.click("#mode-daily")
    page.wait_for_timeout(200)
    visible, value = open_settings_checked(page)
    checks.ok("T-293 연습에서 하드 켬 → 빈 날마다 판 체크박스 켜짐", visible and value, f"체크 {value}")
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(200)
    dismiss_help(page)
    visible, value = open_settings_checked(page)
    checks.ok("T-293 새로 고친 뒤에도 켜짐", visible and value, f"체크 {value}")

    # 반대 방향: 하드 켠 빈 날마다 판 → 연습에서 끔 → 날마다
    set_hard_in_practice(page, False)
    page.click("#mode-daily")
    page.wait_for_timeout(200)
    visible, value = open_settings_checked(page)
    checks.ok("T-293 연습에서 하드 끔 → 빈 날마다 판 체크박스 꺼짐", visible and not value, f"체크 {value}")
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(200)
    dismiss_help(page)
    visible, value = open_settings_checked(page)
    checks.ok("T-293 반대 방향도 새로 고친 뒤 꺼짐", visible and not value, f"체크 {value}")


def scenario_hard_keeps_played_board(page, checks):
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    _word, guess = first_wrong(allowed_pairs(page), answer)
    type_units(page, guess)
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    set_hard_in_practice(page, True)
    page.click("#mode-daily")
    page.wait_for_timeout(200)
    visible, value = open_settings_checked(page)
    checks.ok(
        "T-293 한 줄 낸 날마다 판은 하드 바꿔도 판 값(꺼짐) 그대로",
        visible and not value and row_text(page, 0) == guess,
        f"체크 {value} 줄 {row_text(page, 0)!r}",
    )


def scenario_hard_reaches_empty_practice(page, checks):
    # V3: 연습 판을 먼저 만들어 두고, 날마다에서 하드를 켠 뒤 연습으로 가면 빈 연습 판도 설정을 따른다
    dismiss_help(page)
    page.click("#mode-practice")
    page.wait_for_timeout(200)
    page.click("#mode-daily")
    page.wait_for_timeout(200)
    checks.ok("T-301 연습 판을 만든 뒤 날마다 판이 빔", empty_board(page))
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    page.check("#set-hard")
    page.wait_for_timeout(250)
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")
    page.click("#mode-practice")
    page.wait_for_timeout(200)
    visible, value = open_settings_checked(page)
    checks.ok(
        "T-301 날마다에서 하드 켬 → 빈 연습 판 체크박스 켜짐",
        visible and value,
        f"체크 {value}",
    )


def scenario_typed_letters_survive_align(page, checks):
    # V6: 날마다 빈 판에 입력 중인 글자는 연습에서 하드를 바꾼 뒤 돌아와도 그대로 보인다
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    _word, guess = first_wrong(allowed_pairs(page), answer)
    typed = guess[:3]
    type_units(page, typed)
    checks.ok(
        "T-301 날마다 빈 판에 세 칸을 쳐 둠",
        row_text(page, 0) == typed,
        f"실제 {row_text(page, 0)!r} 기대 {typed!r}",
    )
    set_hard_in_practice(page, True)
    page.click("#mode-daily")
    page.wait_for_timeout(200)
    checks.ok(
        "T-301 하드를 바꾸고 돌아와도 입력 중인 세 칸이 그대로",
        row_text(page, 0) == typed,
        f"실제 {row_text(page, 0)!r} 기대 {typed!r}",
    )
    visible, value = open_settings_checked(page)
    checks.ok(
        "T-301 입력 중인 판의 체크박스가 바꾼 값(켜짐)",
        visible and value,
        f"체크 {value}",
    )


def scenario_hard_locked_after_play(page, checks):
    # V16: 줄을 낸 판에서는 같은 모드에서도 하드를 바꿀 수 없다(되돌리고 토스트, 낸 줄 유지)
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    _word, guess = first_wrong(allowed_pairs(page), answer)
    type_units(page, guess)
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    page.click("#set-hard")
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => t.textContent.includes('판이 시작된 뒤에는 바꿀 수 없습니다'))",
        timeout=3000,
    )
    toast = page.locator("#toasts .toast", has_text="판이 시작된 뒤에는 바꿀 수 없습니다")
    checks.ok(
        "T-304 낸 줄이 있으면 하드 체크가 되돌려지고 잠금 토스트가 보임",
        not page.is_checked("#set-hard") and toast.first.is_visible(),
        f"체크 {page.is_checked('#set-hard')}",
    )
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('jamo.settings'))")
    checks.ok(
        "T-304 잠금 시도 뒤 저장된 설정의 하드가 참이 아님",
        not (isinstance(stored, dict) and stored.get("hardMode") is True),
        f"실제 {stored}",
    )
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-settings').hidden === true")
    checks.ok(
        "T-304 잠금 뒤에도 첫 줄이 그대로",
        row_text(page, 0) == guess,
        f"줄 {row_text(page, 0)!r} 기대 {guess!r}",
    )
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_timeout(200)
    dismiss_help(page)
    visible, value = open_settings_checked(page)
    checks.ok(
        "T-304 새로 고친 뒤에도 첫 줄 그대로, 하드 꺼짐",
        visible and not value and row_text(page, 0) == guess,
        f"체크 {value} 줄 {row_text(page, 0)!r}",
    )
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('jamo.settings'))")
    checks.ok(
        "T-304 새로 고친 뒤에도 저장된 설정의 하드가 참이 아님",
        not (isinstance(stored, dict) and stored.get("hardMode") is True),
        f"실제 {stored}",
    )
    page.click("#mode-practice")
    page.wait_for_timeout(200)
    visible, value = open_settings_checked(page)
    checks.ok(
        "T-304 잠금 시도 뒤 빈 연습 판의 하드 체크박스가 꺼짐",
        visible and not value and empty_board(page),
        f"체크 {value}",
    )


def scenario_align_keeps_puzzle_number(page, checks):
    # V14: 연습을 연 뒤 하드를 바꾸고 날마다로 와도 빈 날마다 판의 번호가 오늘 번호(1)로 남는다
    dismiss_help(page)
    set_hard_in_practice(page, True)
    page.click("#mode-daily")
    page.wait_for_timeout(200)
    visible, value = open_settings_checked(page)
    checks.ok(
        "T-304 연습에서 하드 켠 뒤 빈 날마다 판에 설정이 닿음",
        visible and value and empty_board(page),
        f"체크 {value}",
    )
    word = answer_word(page)
    type_units(page, units_of(page, word))
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    page.click("#btn-share")
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => t.textContent.includes('클립보드에 복사했습니다'))",
        timeout=3000,
    )
    first = page.evaluate("() => navigator.clipboard.readText()").split("\n")[0]
    checks.ok(
        "T-304 맞춤으로 새로 만든 날마다 판의 공유 첫 줄 번호가 0 이 아닌 오늘 번호(1)",
        first.startswith("자모맞히기 1 ") and "연습" not in first,
        f"실제 {first!r}",
    )


def run(label, checks, scenario, browser, base, **page_options):
    page = open_page(browser, base, **page_options)
    try:
        scenario(page, checks)
        errors = list(page._errors)
    except Exception as exc:
        errors = list(page._errors)
        checks.ok(f"{label} - 시나리오 실행", False, f"{type(exc).__name__}: {exc}")
    finally:
        try:
            page._context.close()
        except Exception:
            pass
    checks.ok(f"{label} - 페이지 오류 없음", not errors, "; ".join(errors))


def main():
    checks = Checks()
    with server() as base:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except Exception as exc:
                print(f"브라우저를 띄우지 못했습니다: {exc}")
                return 2
            try:
                run("N4 Enter 단추", checks, scenario_enter_buttons, browser, base)
                run(
                    "N5·N6 정답 토스트·통계",
                    checks,
                    scenario_answer_toast,
                    browser,
                    base,
                    init_scripts=["Math.random = () => 0;"],
                )
                run(
                    "N4 새 날 연습 정답 토스트",
                    checks,
                    scenario_new_day_practice_toast,
                    browser,
                    base,
                    init_scripts=["Math.random = () => 0;"],
                )
                run(
                    "N6 #btn-new 통계 취소",
                    checks,
                    scenario_btn_new_cancels_stats,
                    browser,
                    base,
                    init_scripts=["Math.random = () => 0;"],
                )
                run(
                    "N6 통계 강조",
                    checks,
                    scenario_stats_highlight,
                    browser,
                    base,
                    init_scripts=["Math.random = () => 0;"],
                )
                run(
                    "N6 저장 하드 빈 날마다",
                    checks,
                    scenario_saved_hard_empty_daily,
                    browser,
                    base,
                    clipboard=True,
                )
                run("N7 뒤집기 중 입력", checks, scenario_busy_input, browser, base)
                run("N8 하드 모드", checks, scenario_hard_mode, browser, base)
                run(
                    "N9 시스템 어두운 모드",
                    checks,
                    scenario_system_dark,
                    browser,
                    base,
                    color_scheme="dark",
                )
                run(
                    "N9 시스템 밝은 모드",
                    checks,
                    scenario_system_light,
                    browser,
                    base,
                    color_scheme="light",
                )
                run(
                    "N13 미래 시계",
                    checks,
                    scenario_future_clock,
                    browser,
                    base,
                    clipboard=True,
                    init_scripts=[FAKE_DATE],
                )
                run("N12 Process 키", checks, scenario_process_key, browser, base)
                run(
                    "N12 연습 이어 하기",
                    checks,
                    scenario_practice_resume,
                    browser,
                    base,
                    init_scripts=["Math.random = () => 0;"],
                )
                run("N12 뒤집기 중 모드", checks, scenario_flip_mode_lock, browser, base)
                run("N12 미리보기 고정값", checks, scenario_preview_fixed, browser, base)
                run("T-293 하드 설정이 빈 판에 닿음", checks, scenario_hard_reaches_empty_board, browser, base)
                run("T-293 낸 줄 있는 판은 유지", checks, scenario_hard_keeps_played_board, browser, base)
                run("T-301 하드 설정이 빈 연습 판에 닿음", checks, scenario_hard_reaches_empty_practice, browser, base)
                run("T-301 입력 중 글자 유지", checks, scenario_typed_letters_survive_align, browser, base)
                run("T-304 낸 줄 뒤 하드 잠금", checks, scenario_hard_locked_after_play, browser, base)
                run(
                    "T-304 맞춤이 판 번호를 지킴",
                    checks,
                    scenario_align_keeps_puzzle_number,
                    browser,
                    base,
                    clipboard=True,
                    init_scripts=[FAKE_DATE],
                )
                run("N12 도움말↔README", checks, scenario_help_table, browser, base)
            finally:
                browser.close()
    failures = checks.finish()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
