#!/usr/bin/env python3
"""웹워들 브라우저 검증: 통계·공유·테마·접근성·도움말."""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from browser_harness import Checks, new_page, server, set_group, shot


STATE_LABEL = {"correct": "맞음", "present": "자리 틀림", "absent": "없음"}
PRAISE = {"천재!", "대단해요!", "훌륭해요!", "멋져요!", "좋아요!", "아슬아슬!"}


SEED_JS = (
    "(s) => {"
    "  const d = new Date(); d.setDate(d.getDate() - 1);"
    "  const p = (n) => String(n).padStart(2, '0');"
    "  s.lastDay = d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());"
    "  localStorage.setItem('webwordle.stats', JSON.stringify(s));"
    "  localStorage.setItem('webwordle.seenHelp', 'true');"
    "  return s.lastDay;"
    "}"
)


def dismiss_help(page):
    if page.locator("#modal-help").get_attribute("hidden") is None:
        page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-help').hidden === true", timeout=5000)


def tile_locator(page, row, col):
    return page.locator(
        f"#board .row:nth-child({row + 1}) .tile:nth-child({col + 1})"
    )


def row_snapshot(page, row):
    return page.evaluate(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile')).map(t => ({state: t.dataset.state, text: t.textContent, label: t.getAttribute('aria-label')}))",
        row + 1,
    )


def board_signature(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .tile')).map(t => [t.dataset.state, t.textContent, t.getAttribute('aria-label')])"
    )


def keyboard_snapshot(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#keyboard .key')).map(k => ({key: k.dataset.key, state: k.hasAttribute('data-state') ? k.dataset.state : null}))"
    )


def toast_text(page):
    locator = page.locator("#toasts .toast")
    if locator.count() == 0:
        return ""
    return locator.first.text_content() or ""


def wait_row_done(page, row, timeout=5000):
    page.wait_for_function(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile')).every(t => ['correct', 'present', 'absent'].includes(t.dataset.state))",
        arg=row + 1,
        timeout=timeout,
    )


def wait_submit_settled(page, row, guess, timeout=5000):
    wait_row_done(page, row, timeout=timeout)
    chars = sorted(set(guess))
    page.wait_for_function(
        "(chars) => chars.every(ch => { const key = document.querySelector('#keyboard .key[data-key=\"' + ch + '\"]'); return key && key.hasAttribute('data-state'); })",
        arg=chars,
        timeout=timeout,
    )


def wait_input_ready(page, row, timeout=5000):
    """busy가 풀려 입력이 다시 먹을 때까지 기다린다 (ui.js: busy 동안 handleKey가 무시된다)."""
    page.wait_for_function(
        "(r) => {"
        "  const t = document.querySelector('#board .row:nth-child(' + r + ') .tile');"
        "  if (!t || document.querySelectorAll('#board .tile.flip').length > 0) return false;"
        "  if (t.dataset.state !== 'empty') return false;"
        "  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'q', bubbles: true }));"
        "  return t.dataset.state === 'filled';"
        "}",
        arg=row + 1,
        timeout=timeout,
    )
    page.keyboard.press("Backspace")
    page.wait_for_function(
        "(r) => {"
        "  const t = document.querySelector('#board .row:nth-child(' + r + ') .tile');"
        "  return t && t.dataset.state === 'empty';"
        "}",
        arg=row + 1,
        timeout=timeout,
    )


def answer_for_page(page):
    return page.evaluate(
        "async () => { const g = await import('/js/game.js');"
        " const w = await import('/js/words.js');"
        " return g.answerForDate(new Date(), w.ANSWERS); }"
    )


def puzzle_for_page(page):
    return page.evaluate(
        "async () => (await import('/js/game.js')).dailyIndex(new Date())"
    )


def wrong_words(page, answer, count=6):
    return page.evaluate(
        "async (a) => { const w = await import('/js/words.js');"
        " const seen = new Set(); const out = [];"
        " for (const word of w.ALLOWED) {"
        "   if (word === a || out.includes(word)) continue;"
        "   if (Array.from(word).some(ch => !seen.has(ch))) {"
        "     out.push(word);"
        "     for (const ch of word) seen.add(ch);"
        "   }"
        "   if (out.length === 5) break;"
        " }"
        " for (const word of w.ALLOWED) {"
        "   if (word !== a && !out.includes(word)) { out.push(word); break; }"
        " }"
        " return out; }",
        answer,
    )


def probe_locations(page, answer):
    return page.evaluate(
        "async (a) => { const w = await import('/js/words.js'); const g = await import('/js/game.js');"
        " const found = {correct: null, present: null, absent: null};"
        " for (const word of w.ALLOWED) {"
        "   if (word === a) continue;"
        "   const scores = g.scoreGuess(word, a);"
        "   for (let i = 0; i < scores.length; i++) {"
        "     if (found[scores[i]] === null) found[scores[i]] = {word, index: i};"
        "   }"
        "   if (found.correct && found.present && found.absent) break;"
        " }"
        " return found; }",
        answer,
    )


def type_guess(page, guess):
    page.keyboard.type(guess)
    page.keyboard.press("Enter")


def blur_active(page):
    page.evaluate("() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); }")


def open_settings(page):
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=5000)


def close_modal(page, name):
    page.keyboard.press("Escape")
    page.wait_for_function(f"() => document.getElementById('modal-{name}').hidden === true", timeout=5000)


def tab_key(page, wanted, limit=80):
    for _ in range(limit):
        page.keyboard.press("Tab")
        key = page.evaluate("() => document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key || null : null")
        if key == wanted:
            return key
    return None


def parse_rgb(value):
    nums = [int(n) for n in re.findall(r"\d+", value)]
    return tuple(nums[:3])


def rgb_hue(rgb):
    r, g, b = rgb
    high = max(r, g, b)
    low = min(r, g, b)
    delta = high - low
    if delta == 0:
        return 0.0
    if high == r:
        hue = (g - b) / delta
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return (hue * 60) % 360


def _lin(c):
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def tile_colors(page, row, col):
    return page.evaluate(
        "([r, c]) => { const t = document.querySelector('#board .row:nth-child(' + r + ') .tile:nth-child(' + c + ')');"
        " const s = getComputedStyle(t); return {bg: s.backgroundColor, fg: s.color}; }",
        [row + 1, col + 1],
    )


def check_contrast(page, checks, state_locations, mode):
    for state, (row, col) in state_locations.items():
        colors = tile_colors(page, row, col)
        ratio = contrast(parse_rgb(colors["fg"]), parse_rgb(colors["bg"]))
        checks.ok(
            f"접근성 - 대비 {state} {mode}",
            ratio >= 4.5,
            f"{state} {mode} {ratio:.2f}:1 (fg={colors['fg']}, bg={colors['bg']})",
        )


def effective_colors(page, selector):
    return page.evaluate(
        "(sel) => {"
        "  const el = document.querySelector(sel);"
        "  if (!el) return null;"
        "  const fg = getComputedStyle(el).color;"
        "  let node = el;"
        "  let bg = null;"
        "  while (node) {"
        "    const value = getComputedStyle(node).backgroundColor;"
        "    const nums = (value.match(/[0-9.]+/g) || []).map(Number);"
        "    const alpha = nums.length >= 4 ? nums[3] : (value === 'transparent' ? 0 : 1);"
        "    if (alpha > 0) { bg = value; break; }"
        "    node = node.parentElement;"
        "  }"
        "  if (!bg) bg = getComputedStyle(document.body).backgroundColor;"
        "  return {fg, bg};"
        "}",
        selector,
    )


def check_effective_contrast(page, checks, label, mode, selector):
    colors = effective_colors(page, selector)
    if colors is None:
        checks.ok(f"접근성 - 대비 {label} {mode}", False, f"{selector} 없음")
        return
    ratio = contrast(parse_rgb(colors["fg"]), parse_rgb(colors["bg"]))
    checks.ok(
        f"접근성 - 대비 {label} {mode}",
        ratio >= 4.5,
        f"{label} {mode} {ratio:.2f}:1 (fg={colors['fg']}, bg={colors['bg']})",
    )


def apply_theme_mode(page, dark, colorblind):
    open_settings(page)
    if dark:
        page.check("#set-dark")
    else:
        page.uncheck("#set-dark")
    if colorblind:
        page.check("#set-cb")
    else:
        page.uncheck("#set-cb")
    close_modal(page, "settings")


def unjudged_key_selector(page):
    return page.evaluate(
        "() => {"
        "  const k = Array.from(document.querySelectorAll('#keyboard .key')).find(k => !k.hasAttribute('data-state') && !['enter', 'back'].includes(k.dataset.key));"
        "  return k ? '#keyboard .key[data-key=\"' + k.dataset.key + '\"]' : null;"
        "}"
    )


def scenario_help(page, checks):
    page.wait_for_selector("#modal-help:not([hidden])", timeout=5000)
    checks.ok("도움말 - 첫 방문에 창이 열림", page.locator("#modal-help").get_attribute("hidden") is None)
    checks.ok("도움말 - 창이 열리면 #app에 inert", page.locator("#app").get_attribute("inert") is not None)
    shot(page, "help-first")

    before = board_signature(page)
    page.keyboard.type("abcde")
    checks.ok("도움말 - 창이 열린 동안 글자를 쳐도 보드가 바뀌지 않음", board_signature(page) == before)

    close_modal(page, "help")
    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)
    checks.ok("도움말 - 새로 고치면 다시 저절로 열리지 않음", page.locator("#modal-help").get_attribute("hidden") is not None)

    page.click("#btn-help")
    page.wait_for_selector("#modal-help:not([hidden])", timeout=5000)
    checks.ok("도움말 - #btn-help로 다시 열림", page.locator("#modal-help").get_attribute("hidden") is None)
    example_count = page.locator('#modal-help .example .tile[data-state="correct"]').count()
    checks.ok(
        "도움말 - 보기 타일과 설명 글",
        example_count >= 1
        and len((page.locator("#modal-help").text_content() or "").strip()) > 0,
        f"보기 타일={example_count}",
    )


def scenario_stats(page, checks):
    dismiss_help(page)
    page.click("#btn-stats")
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)

    values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    checks.ok("통계 - 빈 상태 네 값이 모두 0", values == ["0", "0", "0", "0"], f"실제 {values}")
    checks.ok("통계 - 분포 여섯 줄", page.locator("#dist .dist-row").count() == 6, f"실제 {page.locator('#dist .dist-row').count()}")
    share = page.locator("#btn-share")
    checks.ok(
        "통계 - 빈 상태에서는 공유 단추가 hidden",
        share.get_attribute("hidden") is not None and not share.is_visible(),
        f"hidden={share.get_attribute('hidden')!r} 보임={share.is_visible()}",
    )

    close_modal(page, "stats")
    blur_active(page)
    answer = answer_for_page(page)
    type_guess(page, answer)
    wait_submit_settled(page, 0, answer)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)

    values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    checks.ok("통계 - 이긴 뒤 판수·승률·연승·최대연승", values == ["1", "100", "1", "1"], f"실제 {values}")
    first_bar = page.locator("#dist .dist-row").first.locator(".bar").text_content()
    checks.ok("통계 - 분포 첫 줄이 1", first_bar == "1", f"실제 {first_bar}")
    share = page.locator("#btn-share")
    checks.ok(
        "통계 - 판이 끝나면 공유 단추가 보임",
        share.is_visible(),
        f"보임={share.is_visible()} 상자={share.bounding_box()}",
    )
    shot(page, "stats-after-win")


def scenario_restore(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    wrong = wrong_words(page, answer, 6)
    checks.ok(
        "통계 - 틀린 단어 두 개 준비",
        len(wrong) >= 2 and len(set(wrong[:2])) == 2 and all(word != answer for word in wrong[:2]),
        f"실제 {wrong[:2]}",
    )
    for row, guess in enumerate(wrong[:2]):
        if row:
            wait_input_ready(page, row)
        type_guess(page, guess)
        wait_submit_settled(page, row, guess)

    before_board = board_signature(page)
    before_keys = keyboard_snapshot(page)
    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('#board .row:nth-child(1) .tile').dataset.state !== 'empty'",
        timeout=5000,
    )
    checks.ok("통계 - 새로 고쳐도 진행 중인 판 유지", board_signature(page) == before_board)
    checks.ok("통계 - 새로 고쳐도 키보드 색 유지", keyboard_snapshot(page) == before_keys)
    third = row_snapshot(page, 2)
    checks.ok("통계 - 세 번째 줄부터 비어 있음", all(item["state"] == "empty" and item["text"] == "" for item in third))
    checks.ok("통계 - 새로 고친 뒤 도움말이 다시 열리지 않음", page.locator("#modal-help").get_attribute("hidden") is not None)
    shot(page, "restored")


def scenario_stats_mixed(page, checks):
    page.evaluate(SEED_JS, {"played": 7, "wins": 5, "streak": 2, "maxStreak": 4,
                            "dist": [0, 1, 2, 1, 1, 0], "lastDay": ""})
    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)

    page.click("#btn-stats")
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    checks.ok("통계 - 서로 다른 네 값", values == ["7", "71", "2", "4"], f"실제 {values}")
    labels = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat span')).map(s => s.textContent)")
    expected_labels = ["판수", "승률", "연승", "최대"]
    checks.ok(
        "통계 - 네 값 이름표가 판수·승률·연승·최대 순서",
        len(labels) == 4 and all(word in labels[i] for i, word in enumerate(expected_labels)),
        f"실제 {labels}",
    )
    dist = page.evaluate("() => Array.from(document.querySelectorAll('#dist .dist-row .bar')).map(b => b.textContent)")
    checks.ok("통계 - 심은 분포 유지", dist == ["0", "1", "2", "1", "1", "0"], f"실제 {dist}")

    close_modal(page, "stats")
    blur_active(page)
    answer = answer_for_page(page)
    type_guess(page, answer)
    wait_submit_settled(page, 0, answer)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)

    values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    checks.ok("통계 - 이긴 뒤 서로 다른 네 값", values == ["8", "75", "3", "4"], f"실제 {values}")
    dist = page.evaluate("() => Array.from(document.querySelectorAll('#dist .dist-row .bar')).map(b => b.textContent)")
    checks.ok("통계 - 이긴 뒤 분포 첫 칸 증가", dist == ["1", "1", "2", "1", "1", "0"], f"실제 {dist}")
    shot(page, "stats-mixed")


def scenario_stats_nth_line(page, checks):
    page.evaluate(SEED_JS, {"played": 3, "wins": 2, "streak": 1, "maxStreak": 2,
                            "dist": [0, 0, 0, 0, 0, 0], "lastDay": ""})
    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)

    answer = answer_for_page(page)
    wrong = wrong_words(page, answer, 6)
    for row, guess in enumerate(wrong[:3]):
        if row:
            wait_input_ready(page, row)
        type_guess(page, guess)
        wait_submit_settled(page, row, guess)
        wait_input_ready(page, row + 1)
    type_guess(page, answer)
    wait_submit_settled(page, 3, answer)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)

    dist = page.evaluate("() => Array.from(document.querySelectorAll('#dist .dist-row .bar')).map(b => b.textContent)")
    checks.ok(
        "통계 - 네 번째 줄 승리 시 네 번째 칸만 증가",
        dist == ["0", "0", "0", "1", "0", "0"],
        f"실제 {dist}",
    )
    values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    checks.ok(
        "통계 - 네 번째 줄 승리 뒤 판수·승률·연승·최대 연승",
        values == ["4", "75", "2", "2"],
        f"실제 {values}",
    )
    highlighted = page.evaluate(
        "() => Array.from(document.querySelectorAll('#dist .dist-row')).map((row, i) => ({line: i + 1, hl: row.querySelector('.bar').classList.contains('hl')})).filter(row => row.hl)"
    )
    checks.ok(
        "통계 - 분포 하이라이트는 이번 판의 네 번째 줄에만",
        len(highlighted) == 1 and highlighted[0]["line"] == 4,
        f"실제 {highlighted}",
    )
    shot(page, "stats-nth-line")


def scenario_stats_after_loss(page, checks):
    page.evaluate(SEED_JS, {"played": 7, "wins": 5, "streak": 2, "maxStreak": 4,
                            "dist": [0, 1, 2, 1, 1, 0], "lastDay": ""})
    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)

    answer = answer_for_page(page)
    wrong = wrong_words(page, answer, 6)
    checks.ok(
        "통계 - 진 판 틀린 단어 여섯 개 준비",
        len(wrong) == 6 and all(word != answer for word in wrong),
        f"실제 {wrong}",
    )
    for row, guess in enumerate(wrong[:6]):
        if row:
            wait_input_ready(page, row)
        type_guess(page, guess)
        wait_submit_settled(page, row, guess)

    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast')).some(t => (t.textContent || '').startsWith('정답:'))",
        timeout=15000,
    )
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=15000)
    toasts = page.evaluate("() => Array.from(document.querySelectorAll('#toasts .toast')).map(t => t.textContent)")
    checks.ok("통계 - 진 판 뒤 정답 토스트", any(text.startswith("정답:") for text in toasts), f"실제 {toasts}")
    answer_toast = next((text for text in toasts if text.startswith("정답:")), "")
    checks.ok(
        "접근성 - 진 판 정답이 aria-live 토스트에 들어감",
        answer_toast.startswith("정답: ") and answer.upper() in answer_toast,
        f"토스트={answer_toast!r} 정답={answer.upper()!r}",
    )
    checks.ok(
        "접근성 - 진 판 정답 토스트가 #toasts aria-live 영역 안에 있음",
        page.locator("#toasts").get_attribute("aria-live") == "polite"
        and page.locator("#toasts .toast").count() > 0,
        f"aria-live={page.locator('#toasts').get_attribute('aria-live')!r} 개수={page.locator('#toasts .toast').count()}",
    )

    values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    checks.ok("통계 - 진 판 뒤 연승 0 최대 연승 4", values == ["8", "63", "0", "4"], f"실제 {values}")
    dist = page.evaluate("() => Array.from(document.querySelectorAll('#dist .dist-row .bar')).map(b => b.textContent)")
    checks.ok("통계 - 진 판 뒤 분포가 심은 그대로", dist == ["0", "1", "2", "1", "1", "0"], f"실제 {dist}")
    shot(page, "stats-after-loss")


def scenario_stats_reload_finished(page, checks):
    page.evaluate(SEED_JS, {"played": 7, "wins": 5, "streak": 2, "maxStreak": 4,
                            "dist": [0, 1, 2, 1, 1, 0], "lastDay": ""})
    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)

    answer = answer_for_page(page)
    type_guess(page, answer)
    wait_submit_settled(page, 0, answer)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    before_values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    close_modal(page, "stats")
    before_board = board_signature(page)
    before_keys = keyboard_snapshot(page)

    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('#board .row:nth-child(1) .tile').dataset.state !== 'empty'",
        timeout=5000,
    )
    checks.ok("통계 - 끝난 판 새로 고침 뒤 보드 그대로", board_signature(page) == before_board)
    checks.ok("통계 - 끝난 판 새로 고침 뒤 키보드 색 그대로", keyboard_snapshot(page) == before_keys)

    page.click("#btn-stats")
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    share = page.locator("#btn-share")
    checks.ok("통계 - 끝난 판 새로 고침 뒤 공유 단추가 보임", share.is_visible(), f"보임={share.is_visible()}")
    after_values = page.evaluate("() => Array.from(document.querySelectorAll('#stat-row .stat b')).map(b => b.textContent)")
    checks.ok(
        "통계 - 끝난 판 새로 고침 뒤 판수가 늘지 않고 네 값 그대로",
        after_values == before_values == ["8", "75", "3", "4"],
        f"전={before_values} 후={after_values}",
    )
    close_modal(page, "stats")
    before_typing = board_signature(page)
    page.keyboard.type("abcde")
    checks.ok("통계 - 끝난 판에서는 글자를 쳐도 보드가 안 바뀜", board_signature(page) == before_typing)
    shot(page, "stats-reload-finished")


def scenario_share(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    puzzle = puzzle_for_page(page)
    type_guess(page, answer)
    wait_submit_settled(page, 0, answer)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    share = page.locator("#btn-share")
    checks.ok(
        "공유 - 판이 끝나면 공유 단추가 보임",
        share.is_visible(),
        f"보임={share.is_visible()} 상자={share.bounding_box()}",
    )

    page.click("#btn-share")
    page.wait_for_function(
        "() => document.querySelector('#toasts .toast')?.textContent === '클립보드에 복사했습니다'",
        timeout=5000,
    )
    text = page.evaluate("navigator.clipboard.readText()")
    lines = text.split("\n")
    head = f"웹워들 {puzzle} 1/6"
    checks.ok("공유 - 첫 줄이 오늘 번호와 맞힌 줄수", lines and lines[0] == head, f"첫 줄={lines[0]!r} 기대={head!r}")

    emoji_lines = [line for line in lines[1:] if line]
    checks.ok("공유 - 맞힌 줄수만큼 이모지 줄", len(emoji_lines) == 1, f"실제 {len(emoji_lines)}줄 {emoji_lines}")
    checks.ok(
        "공유 - 이모지 줄마다 다섯 개",
        all(len(line) == 5 for line in emoji_lines),
        f"실제 {emoji_lines}",
    )
    checks.ok(
        "공유 - 마지막 줄은 모두 맞음",
        emoji_lines and emoji_lines[-1] == "🟩🟩🟩🟩🟩",
        f"실제 {emoji_lines[-1] if emoji_lines else None!r}",
    )
    checks.ok("공유 - 복사 토스트", toast_text(page) == "클립보드에 복사했습니다", f"토스트={toast_text(page)!r}")
    shot(page, "share")


def scenario_settings(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    locations = probe_locations(page, answer)
    probe = locations["correct"]["word"] if locations.get("correct") else None
    checks.ok("설정 - 색 비교용 correct 타일이 있는 추측 준비", probe is not None, f"실제 {locations}")
    if probe is None:
        return
    type_guess(page, probe)
    wait_submit_settled(page, 0, probe)

    row0 = row_snapshot(page, 0)
    correct_col = next(i for i, item in enumerate(row0) if item["state"] == "correct")
    normal_colors = tile_colors(page, 0, correct_col)
    body_light = page.evaluate("() => getComputedStyle(document.body).backgroundColor")

    open_settings(page)
    page.check("#set-dark")
    checks.ok("설정 - 어두운 테마가 html에 적용됨", page.locator("html").get_attribute("data-theme") == "dark")
    body_dark = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    checks.ok(
        "설정 - body 배경색이 밝을 때와 실제로 다름",
        body_dark != body_light,
        f"밝음={body_light} 어둡={body_dark}",
    )
    checks.ok(
        "설정 - 어두운 테마의 body 배경색이 실제로 더 어두움",
        luminance(parse_rgb(body_dark)) < luminance(parse_rgb(body_light)),
        f"밝음={body_light} 어둡={body_dark}",
    )
    close_modal(page, "settings")
    blur_active(page)
    shot(page, "theme-dark")

    open_settings(page)
    page.check("#set-cb")
    checks.ok("설정 - 색약 모드가 html에 적용됨", page.locator("html").get_attribute("data-colorblind") == "on")
    close_modal(page, "settings")

    blur_active(page)
    wait_input_ready(page, 1)
    type_guess(page, probe)
    wait_submit_settled(page, 1, probe)
    row1 = row_snapshot(page, 1)
    cb_col = next(i for i, item in enumerate(row1) if item["state"] == "correct")
    cb_colors = tile_colors(page, 1, cb_col)
    cb_rgb = parse_rgb(cb_colors["bg"])
    checks.ok(
        "설정 - 색약 correct 배경색이 일반과 실제로 다름",
        cb_colors["bg"] != normal_colors["bg"],
        f"일반={normal_colors['bg']} 색약={cb_colors['bg']}",
    )
    checks.ok(
        "설정 - 색약 correct가 주황 계열",
        cb_rgb[0] > cb_rgb[1] > cb_rgb[2],
        f"rgb={cb_rgb}",
    )
    cb_hue = rgb_hue(cb_rgb)
    checks.ok(
        "설정 - 색약 correct hue가 주황(0~40도)",
        0 <= cb_hue <= 40,
        f"rgb={cb_rgb} hue={cb_hue:.1f}도",
    )
    shot(page, "theme-colorblind")

    body_dark_before_reload = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)
    checks.ok("설정 - 새로 고쳐도 어두운 테마 유지", page.locator("html").get_attribute("data-theme") == "dark")
    checks.ok("설정 - 새로 고쳐도 색약 모드 유지", page.locator("html").get_attribute("data-colorblind") == "on")
    body_dark_after_reload = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    checks.ok(
        "설정 - 새로 고친 뒤 어두운 body 배경색 유지",
        body_dark_after_reload == body_dark_before_reload,
        f"전={body_dark_before_reload} 후={body_dark_after_reload}",
    )
    open_settings(page)
    checks.ok(
        "설정 - 새로 고쳐도 체크박스 두 개가 켜져 있음",
        page.locator("#set-dark").is_checked() and page.locator("#set-cb").is_checked(),
        f"dark={page.locator('#set-dark').is_checked()} cb={page.locator('#set-cb').is_checked()}",
    )

    page.uncheck("#set-dark")
    page.uncheck("#set-cb")
    checks.ok(
        "설정 - 밝은 테마로 되돌림",
        page.locator("html").get_attribute("data-theme") == "light"
        and page.locator("html").get_attribute("data-colorblind") == "off",
    )
    close_modal(page, "settings")
    shot(page, "theme-light")

    open_settings(page)
    page.click("#set-hard")
    page.wait_for_function(
        "() => document.querySelector('#toasts .toast')?.textContent.includes('하드 모드')",
        timeout=5000,
    )
    checks.ok("설정 - 판 시작 뒤 하드 모드 체크가 풀림", not page.locator("#set-hard").is_checked())
    checks.ok(
        "설정 - 하드 모드 잠금 안내 토스트",
        "하드 모드는 판이 시작된 뒤에는 바꿀 수 없습니다" in toast_text(page),
        f"토스트={toast_text(page)!r}",
    )


def scenario_settings_colorblind_present(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    locations = probe_locations(page, answer)
    present = locations.get("present")
    correct = locations.get("correct")
    checks.ok(
        "설정 - 색약 present와 correct 타일을 만들 추측 준비",
        present is not None and correct is not None,
        f"실제 {locations}",
    )
    if present is None or correct is None:
        return

    if present["word"] == correct["word"]:
        type_guess(page, present["word"])
        wait_submit_settled(page, 0, present["word"])
        present_row = correct_row = 0
    else:
        type_guess(page, present["word"])
        wait_submit_settled(page, 0, present["word"])
        wait_input_ready(page, 1)
        type_guess(page, correct["word"])
        wait_submit_settled(page, 1, correct["word"])
        present_row, correct_row = 0, 1
    present_col = present["index"]
    correct_col = correct["index"]

    open_settings(page)
    page.check("#set-cb")
    checks.ok("설정 - 색약 모드가 html에 적용됨", page.locator("html").get_attribute("data-colorblind") == "on")
    close_modal(page, "settings")

    present_colors = tile_colors(page, present_row, present_col)
    correct_colors = tile_colors(page, correct_row, correct_col)
    present_rgb = parse_rgb(present_colors["bg"])
    correct_rgb = parse_rgb(correct_colors["bg"])
    present_hue = rgb_hue(present_rgb)
    correct_hue = rgb_hue(correct_rgb)
    checks.ok(
        "설정 - 색약 present 배경이 파랑 계열",
        present_rgb[2] > present_rgb[1] > present_rgb[0],
        f"rgb={present_colors['bg']}",
    )
    checks.ok(
        "설정 - 색약 correct 배경이 주황 계열",
        correct_rgb[0] > correct_rgb[1] > correct_rgb[2],
        f"rgb={correct_colors['bg']}",
    )
    checks.ok(
        "설정 - 색약 present hue가 파랑(190~250도)",
        190 <= present_hue <= 250,
        f"rgb={present_rgb} hue={present_hue:.1f}도",
    )
    checks.ok(
        "설정 - 색약 correct hue가 주황(0~40도)",
        0 <= correct_hue <= 40,
        f"rgb={correct_rgb} hue={correct_hue:.1f}도",
    )
    checks.ok(
        "설정 - 색약 correct와 present 배경이 서로 다름",
        present_colors["bg"] != correct_colors["bg"],
        f"correct={correct_colors['bg']} present={present_colors['bg']}",
    )

    page.reload()
    page.wait_for_selector("#board .tile", timeout=10000)
    wait_row_done(page, present_row)
    wait_row_done(page, correct_row)
    after_present = tile_colors(page, present_row, present_col)
    after_correct = tile_colors(page, correct_row, correct_col)
    checks.ok(
        "설정 - 새로 고쳐도 색약 present 칠해진 색 유지",
        after_present["bg"] == present_colors["bg"],
        f"전={present_colors['bg']} 후={after_present['bg']}",
    )
    checks.ok(
        "설정 - 새로 고쳐도 색약 correct 칠해진 색 유지",
        after_correct["bg"] == correct_colors["bg"],
        f"전={correct_colors['bg']} 후={after_correct['bg']}",
    )
    shot(page, "theme-colorblind-present")


def scenario_accessibility(page, checks):
    page.wait_for_selector("#modal-help:not([hidden])", timeout=5000)
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-help').hidden === true", timeout=5000)

    first_key = tab_key(page, "q")
    checks.ok("접근성 - Tab으로 화면 키에 포커스", first_key == "q", f"activeElement.dataset.key={first_key!r}")
    page.keyboard.press("Enter")
    typed_row = row_snapshot(page, 0)
    checks.ok(
        "접근성 - 화면 키 Enter가 제출이 아니라 글자 입력",
        sum(1 for item in typed_row if item["state"] == "filled") == 1
        and typed_row[0]["text"] == "Q"
        and all(item["state"] == "empty" for item in typed_row[1:]),
        f"실제 {typed_row}",
    )
    page.keyboard.press("Backspace")

    enter_key = tab_key(page, "enter")
    checks.ok("접근성 - Tab으로 enter 키에 포커스", enter_key == "enter", f"activeElement.dataset.key={enter_key!r}")

    answer = answer_for_page(page)
    locations = probe_locations(page, answer)
    checks.ok(
        "접근성 - correct/present/absent 판정을 모두 만드는 추측 준비",
        all(locations.get(state) for state in ("correct", "present", "absent")),
        f"실제 {locations}",
    )
    if not all(locations.get(state) for state in ("correct", "present", "absent")):
        return

    probe_rows = []
    seen_words = set()
    for state in ("correct", "present", "absent"):
        item = locations[state]
        if item["word"] not in seen_words:
            seen_words.add(item["word"])
            row = len(probe_rows)
            if row:
                wait_input_ready(page, row)
            type_guess(page, item["word"])
            wait_submit_settled(page, row, item["word"])
            probe_rows.append((row, item["word"]))

    state_locations = {}
    all_states = set()
    labels_ok = True
    for row, _ in probe_rows:
        for col, item in enumerate(row_snapshot(page, row)):
            if item["state"] in STATE_LABEL:
                all_states.add(item["state"])
                state_locations.setdefault(item["state"], (row, col))
                labels_ok = labels_ok and STATE_LABEL[item["state"]] in (item["label"] or "")
    checks.ok(
        "접근성 - 판정 타일 aria-label에 맞음/자리 틀림/없음",
        labels_ok and all_states == {"correct", "present", "absent"},
        f"상태={sorted(all_states)}",
    )
    checks.ok("접근성 - #toasts에 aria-live=polite", page.locator("#toasts").get_attribute("aria-live") == "polite")

    label_letters_ok = True
    for row, _ in probe_rows:
        for item in row_snapshot(page, row):
            if item["state"] in STATE_LABEL:
                label = item["label"] or ""
                label_letters_ok = (
                    label_letters_ok
                    and item["text"].upper() in label.upper()
                    and STATE_LABEL[item["state"]] in label
                )
    checks.ok(
        "접근성 - 판정 타일 aria-label에 글자와 판정말",
        label_letters_ok,
        f"probe_rows={probe_rows}",
    )

    board = page.locator("#board")
    keyboard = page.locator("#keyboard")
    checks.ok(
        "접근성 - 보드 role=grid와 aria-label",
        board.get_attribute("role") == "grid" and (board.get_attribute("aria-label") or "").strip() != "",
        f"role={board.get_attribute('role')!r} aria-label={board.get_attribute('aria-label')!r}",
    )
    checks.ok(
        "접근성 - 화면 키보드 role=group와 aria-label",
        keyboard.get_attribute("role") == "group" and (keyboard.get_attribute("aria-label") or "").strip() != "",
        f"role={keyboard.get_attribute('role')!r} aria-label={keyboard.get_attribute('aria-label')!r}",
    )

    screen_words = wrong_words(page, answer, 6)
    screen_word = next(
        (word for word in screen_words if word not in seen_words and len(set(word)) == 5),
        None,
    )
    if screen_word is None:
        screen_word = next((word for word in screen_words if word not in seen_words), None)
    checks.ok("접근성 - 화면 키만으로 칠 단어 준비", screen_word is not None, f"실제 {screen_words}")
    if screen_word is None:
        return

    screen_row = len(probe_rows)
    wait_input_ready(page, screen_row)
    focus_ok = True
    for ch in screen_word:
        if tab_key(page, ch) != ch:
            focus_ok = False
            break
        page.keyboard.press("Enter")
    checks.ok("접근성 - 화면 키 글자에 포커스", focus_ok, f"단어={screen_word}")
    if not focus_ok:
        return

    screen_enter = tab_key(page, "enter")
    checks.ok("접근성 - 화면 키 ENTER에 포커스", screen_enter == "enter", f"activeElement.dataset.key={screen_enter!r}")
    if screen_enter != "enter":
        return
    page.keyboard.press("Enter")
    wait_submit_settled(page, screen_row, screen_word)
    screen_snapshot = row_snapshot(page, screen_row)
    checks.ok(
        "접근성 - 화면 키만으로 한 줄 제출",
        all(item["state"] in STATE_LABEL for item in screen_snapshot),
        f"실제 {screen_snapshot}",
    )

    win_row_index = len(probe_rows) + 1
    wait_input_ready(page, win_row_index)
    type_guess(page, answer)
    wait_submit_settled(page, win_row_index, answer)
    win_row = row_snapshot(page, win_row_index)
    checks.ok("접근성 - 키보드만으로 정답을 맞혀 이김", all(item["state"] == "correct" for item in win_row))
    page.wait_for_function("() => document.querySelector('#toasts .toast')?.textContent", timeout=5000)
    checks.ok("접근성 - 판이 끝나면 aria-live 영역에 글이 들어감", toast_text(page) in PRAISE, f"토스트={toast_text(page)!r}")

    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    close_modal(page, "stats")
    check_contrast(page, checks, state_locations, "밝은테마")

    open_settings(page)
    page.check("#set-dark")
    check_contrast(page, checks, state_locations, "어두운테마")
    page.uncheck("#set-dark")
    page.check("#set-cb")
    check_contrast(page, checks, state_locations, "색약모드")
    page.check("#set-dark")
    check_contrast(page, checks, state_locations, "어두움+색약")
    page.uncheck("#set-dark")
    page.uncheck("#set-cb")
    close_modal(page, "settings")


def scenario_accessibility_contrast(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    locations = probe_locations(page, answer)
    checks.ok(
        "접근성 - 대비용 correct/present/absent 타일 준비",
        all(locations.get(state) for state in ("correct", "present", "absent")),
        f"실제 {locations}",
    )
    if not all(locations.get(state) for state in ("correct", "present", "absent")):
        return

    probe_rows = []
    seen_words = set()
    for state in ("correct", "present", "absent"):
        item = locations[state]
        if item["word"] not in seen_words:
            seen_words.add(item["word"])
            row = len(probe_rows)
            if row:
                wait_input_ready(page, row)
            type_guess(page, item["word"])
            wait_submit_settled(page, row, item["word"])
            probe_rows.append((row, item["word"]))

    state_locations = {}
    for row, _ in probe_rows:
        for col, item in enumerate(row_snapshot(page, row)):
            if item["state"] in STATE_LABEL:
                state_locations.setdefault(item["state"], (row, col))
    checks.ok(
        "접근성 - 대비용 판정 타일 세 상태",
        set(state_locations) == {"correct", "present", "absent"},
        f"상태={sorted(state_locations)}",
    )
    if set(state_locations) != {"correct", "present", "absent"}:
        return

    filled_row = len(probe_rows)
    modes = (
        ("밝음", False, False),
        ("어두움", True, False),
        ("색약", False, True),
        ("어두움+색약", True, True),
    )
    for mode, dark, colorblind in modes:
        apply_theme_mode(page, dark, colorblind)
        theme = page.locator("html").get_attribute("data-theme")
        cb = page.locator("html").get_attribute("data-colorblind")
        checks.ok(
            f"접근성 - 모드 {mode} 적용",
            theme == ("dark" if dark else "light") and cb == ("on" if colorblind else "off"),
            f"theme={theme!r} colorblind={cb!r}",
        )

        check_effective_contrast(page, checks, "머리글 제목", mode, ".header h1")

        unjudged = unjudged_key_selector(page)
        checks.ok(
            f"접근성 - 대비용 판정 없는 글자 키 {mode}",
            unjudged is not None,
            f"selector={unjudged!r}",
        )
        if unjudged is not None:
            check_effective_contrast(page, checks, "판정 없는 글자 키", mode, unjudged)

        for state in ("correct", "present", "absent"):
            check_effective_contrast(
                page,
                checks,
                f"{state} 키",
                mode,
                f'#keyboard .key[data-state="{state}"]',
            )
        check_effective_contrast(page, checks, "ENTER 키", mode, '#keyboard .key[data-key="enter"]')
        check_effective_contrast(page, checks, "⌫ 키", mode, '#keyboard .key[data-key="back"]')

        blur_active(page)
        page.keyboard.type("z")
        page.wait_for_function(
            "(r) => document.querySelector('#board .row:nth-child(' + (r + 1) + ') .tile:nth-child(1)').dataset.state === 'filled'",
            arg=filled_row,
            timeout=5000,
        )
        check_effective_contrast(
            page,
            checks,
            "입력 중 칸",
            mode,
            f"#board .row:nth-child({filled_row + 1}) .tile:nth-child(1)",
        )
        page.keyboard.press("Backspace")
        page.wait_for_function(
            "(r) => document.querySelector('#board .row:nth-child(' + (r + 1) + ') .tile:nth-child(1)').dataset.state === 'empty'",
            arg=filled_row,
            timeout=5000,
        )

        blur_active(page)
        page.keyboard.type("zzzzz")
        page.keyboard.press("Enter")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#toasts .toast')).some(t => t.textContent && !t.classList.contains('out'))",
            timeout=5000,
        )
        check_effective_contrast(page, checks, "토스트", mode, "#toasts .toast:not(.out)")
        for _ in range(5):
            page.keyboard.press("Backspace")
        page.wait_for_function(
            "(r) => document.querySelector('#board .row:nth-child(' + (r + 1) + ') .tile').dataset.state === 'empty'",
            arg=filled_row,
            timeout=5000,
        )

        page.click("#btn-stats")
        page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
        check_effective_contrast(page, checks, "통계 설명 글", mode, "#stat-row .stat span")
        close_modal(page, "stats")


def run_scenario(label, browser, base, checks, scenario, clipboard=False):
    page = new_page(browser, base, clipboard=clipboard)
    errors = []
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
    checks.ok(f"{label} - 콘솔 오류 없음", not errors, "; ".join(errors))


def main():
    set_group("ui")
    checks = Checks()
    playwright = None
    try:
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(timeout=10000)
            try:
                with server() as base:
                    run_scenario("도움말", browser, base, checks, scenario_help)
                    run_scenario("통계", browser, base, checks, scenario_stats)
                    run_scenario("통계", browser, base, checks, scenario_restore)
                    run_scenario("통계", browser, base, checks, scenario_stats_mixed)
                    run_scenario("통계", browser, base, checks, scenario_stats_nth_line)
                    run_scenario("통계", browser, base, checks, scenario_stats_after_loss)
                    run_scenario("통계", browser, base, checks, scenario_stats_reload_finished)
                    run_scenario("공유", browser, base, checks, scenario_share, clipboard=True)
                    run_scenario("설정", browser, base, checks, scenario_settings)
                    run_scenario("설정", browser, base, checks, scenario_settings_colorblind_present)
                    run_scenario("접근성", browser, base, checks, scenario_accessibility)
                    run_scenario("접근성", browser, base, checks, scenario_accessibility_contrast)
            finally:
                browser.close()
        finally:
            playwright.stop()
    except Exception as exc:
        print(f"브라우저 시작/실행 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
