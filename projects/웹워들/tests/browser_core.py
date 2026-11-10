#!/usr/bin/env python3
"""웹워들 핵심 한 판: 보드, 키보드, 없는 단어 거절, 판 끝."""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from browser_harness import Checks, new_page, server, set_group, shot


def dismiss_help(page):
    page.wait_for_selector("#modal-help:not([hidden])", timeout=5000)
    page.click("#modal-help .modal-close")
    page.wait_for_function("() => document.getElementById('modal-help').hidden === true")


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
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile')).map(t => ({state: t.dataset.state, text: t.textContent}))",
        row + 1,
    )


def wait_row_done(page, row, timeout=4000):
    page.wait_for_function(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile')).every(t => ['correct', 'present', 'absent'].includes(t.dataset.state))",
        arg=row + 1,
        timeout=timeout,
    )


def wait_submit_settled(page, row, guess, timeout=4000):
    wait_row_done(page, row, timeout=timeout)
    chars = sorted(set(guess))
    page.wait_for_function(
        "(chars) => chars.every(ch => { const key = document.querySelector('#keyboard .key[data-key=\"' + ch + '\"]'); return key && key.hasAttribute('data-state'); })",
        arg=chars,
        timeout=timeout,
    )


def board_signature(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .tile')).map(t => [t.dataset.state, t.textContent])"
    )


def answer_for_page(page):
    return page.evaluate(
        "async () => { const g = await import('/js/game.js');"
        " const w = await import('/js/words.js');"
        " return g.answerForDate(new Date(), w.ANSWERS); }"
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


def score_guess(guess, answer):
    guess = guess.lower()
    answer = answer.lower()
    scores = ["absent"] * len(guess)
    left = {}
    for i, char in enumerate(guess):
        if char == answer[i]:
            scores[i] = "correct"
        else:
            left[answer[i]] = left.get(answer[i], 0) + 1
    for i, char in enumerate(guess):
        if scores[i] == "correct":
            continue
        if left.get(char, 0) > 0:
            scores[i] = "present"
            left[char] -= 1
    return scores


def find_present_pair(page, answer):
    return page.evaluate(
        "async (a) => { const w = await import('/js/words.js'); const g = await import('/js/game.js');"
        " for (let j = 0; j < a.length; j++) {"
        "   const ch = a[j];"
        "   for (const word of w.ALLOWED) {"
        "     if (word === a || word[j] === ch) continue;"
        "     for (let k = 0; k < word.length; k++) {"
        "       if (k !== j && word[k] === ch) {"
        "         const scores = g.scoreGuess(word, a);"
        "         if (scores[k] === 'present' && ![...word].some((c, m) => c === ch && scores[m] === 'correct')) return { char: ch, index: k, first: word, second: a };"
        "       }"
        "     }"
        "   }"
        " }"
        " return null; }",
        answer,
    )


def toast_text(page):
    locator = page.locator("#toasts .toast")
    if locator.count() == 0:
        return ""
    return locator.first.text_content() or ""


JS_OVERLAP = (
    "() => {"
    "  const t = document.querySelector('#toasts .toast');"
    "  if (!t) return null;"
    "  const tr = t.getBoundingClientRect();"
    "  const hit = [];"
    "  document.querySelectorAll('#board .tile').forEach((el, i) => {"
    "    const r = el.getBoundingClientRect();"
    "    if (tr.left < r.right && tr.right > r.left && tr.top < r.bottom && tr.bottom > r.top)"
    "      hit.push(i);"
    "  });"
    "  return { text: t.textContent, hit: hit };"
    "}"
)


WATCH_FLIP_JS = (
    "() => {"
    "  window.__flips = [];"
    "  document.querySelectorAll('#board .row:nth-child(1) .tile').forEach((t, i) => {"
    "    new MutationObserver(() => {"
    "      if (!t.classList.contains('flip')) return;"
    "      const s = getComputedStyle(t);"
    "      window.__flips.push({i: i, at: performance.now(),"
    "                           name: s.animationName, dur: s.animationDuration});"
    "    }).observe(t, {attributes: true, attributeFilter: ['class']});"
    "  });"
    "}"
)


WATCH_ANIM_JS = (
    "() => {"
    "  window.__anims = [];"
    "  document.querySelectorAll('#board .row:nth-child(1) .tile').forEach((t, i) => {"
    "    t.addEventListener('animationstart', (e) => {"
    "      window.__anims.push({i: i, name: e.animationName, at: performance.now(),"
    "                           running: t.getAnimations().map(a => a.animationName)});"
    "    });"
    "  });"
    "}"
)


def css_time_seconds(value):
    if not isinstance(value, str) or value in {"", "none"}:
        return 0.0
    if value.endswith("ms"):
        return float(value[:-2]) / 1000.0
    if value.endswith("s"):
        return float(value[:-1])
    return 0.0


def keyboard_snapshot(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#keyboard .key')).map(k => ({key: k.dataset.key, state: k.hasAttribute('data-state') ? k.dataset.state : null}))"
    )


def run_scenario(label, browser, base, checks, scenario):
    page = new_page(browser, base)
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


def scenario_board(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    wrong = wrong_words(page, answer, 1)
    guess = wrong[0]

    rows = page.locator("#board .row").count()
    tiles = page.locator("#board .tile").count()
    checks.ok("보드 - 줄 6개", rows == 6, f"실제 {rows}")
    checks.ok("보드 - 타일 30개", tiles == 30, f"실제 {tiles}")

    initial = board_signature(page)
    checks.ok(
        "보드 - 시작 상태가 모두 empty이고 글자 없음",
        len(initial) == 30
        and all(state == "empty" and text == "" for state, text in initial),
        f"첫 값 {initial[:1]}",
    )

    page.keyboard.type(guess)
    page.wait_for_function(
        "() => document.querySelector('#board .row:nth-child(1) .tile:nth-child(5)').dataset.state === 'filled'"
    )
    typed = row_snapshot(page, 0)
    checks.ok(
        "보드 - 입력 중 첫 줄 다섯 칸이 filled이고 대문자로 보임",
        all(item["state"] == "filled" for item in typed)
        and "".join(item["text"] for item in typed) == guess.upper(),
        f"실제 {''.join(item['text'] for item in typed)}",
    )

    page.keyboard.press("Backspace")
    checks.ok(
        "보드 - 한 칸 지우면 마지막 칸이 비고 앞 네 칸은 남음",
        tile_state(page, 0, 4) == "empty"
        and tile_text(page, 0, 4) == ""
        and all(tile_state(page, 0, c) == "filled" for c in range(4)),
    )
    page.keyboard.type(guess[-1])
    typed_again = row_snapshot(page, 0)
    checks.ok(
        "보드 - 다시 친 글자가 제자리에 돌아옴",
        all(item["state"] == "filled" for item in typed_again)
        and "".join(item["text"] for item in typed_again) == guess.upper(),
    )

    page.evaluate(WATCH_FLIP_JS)
    page.evaluate(WATCH_ANIM_JS)
    page.keyboard.press("Enter")
    wait_row_done(page, 0)
    flips = page.evaluate("() => window.__flips")
    anim_starts = page.evaluate("() => window.__anims")
    flip_starts_by_index = {}
    for item in anim_starts:
        if item["name"] != "flip":
            continue
        index = item["i"]
        if index not in flip_starts_by_index or item["at"] < flip_starts_by_index[index]["at"]:
            flip_starts_by_index[index] = item
    flip_starts = [flip_starts_by_index[i] for i in sorted(flip_starts_by_index)]
    flip_indexes = set(flip_starts_by_index)
    earliest = {}
    for item in flips:
        index = item["i"]
        if index not in earliest or item["at"] < earliest[index]["at"]:
            earliest[index] = item

    checks.ok(
        "보드 - 뒤집기 class가 첫 줄 다섯 칸 모두에 붙음",
        set(earliest) == {0, 1, 2, 3, 4},
        f"기록된 칸={sorted(earliest)}",
    )
    animations = [earliest[i] for i in range(5) if i in earliest]
    checks.ok(
        "보드 - .flip 에 animation 선언이 걸려 있음(이름·시간)",
        len(animations) == 5
        and all(item["name"] == "flip" and css_time_seconds(item["dur"]) > 0 for item in animations),
        f"실제 {[(item['i'], item['name'], item['dur']) for item in animations]}",
    )
    checks.ok(
        "보드 - animationstart가 첫 줄 다섯 칸 모두에서 flip로 시작됨",
        len(flip_starts) == 5
        and flip_indexes == {0, 1, 2, 3, 4}
        and all(item["name"] == "flip" for item in flip_starts),
        f"flip 기록={[(item['i'], item['name'], item['at']) for item in flip_starts]}",
    )
    checks.ok(
        "보드 - animationstart 순간 해당 칸에 flip 애니메이션이 running",
        len(flip_starts) == 5
        and flip_indexes == {0, 1, 2, 3, 4}
        and all("flip" in item["running"] for item in flip_starts),
        f"flip running={[(item['i'], item['running']) for item in flip_starts]}",
    )
    checks.ok(
        "보드 - animationstart 기록이 정확히 다섯 칸 분(빈 목록 아님)",
        len(flip_starts) == 5
        and flip_indexes == {0, 1, 2, 3, 4},
        f"flip 기록 수={len(flip_starts)}, 칸={sorted(flip_indexes)}",
    )
    flip_times = [earliest[i]["at"] if i in earliest else None for i in range(5)]
    ordered = (
        all(value is not None for value in flip_times)
        and all(flip_times[i] < flip_times[i + 1] for i in range(4))
    )
    gap = flip_times[4] - flip_times[0] if ordered else None
    checks.ok(
        "보드 - 뒤집기가 왼쪽부터 차례로 진행",
        ordered,
        f"칸별 시각={flip_times}, 첫·마지막 차이={gap}ms" if gap is not None else f"칸별 시각={flip_times}",
    )
    page.wait_for_function(
        "() => document.querySelectorAll('#board .row:nth-child(1) .tile.flip').length === 0",
        timeout=3000,
    )
    remaining_flips = page.locator("#board .row:nth-child(1) .tile.flip").count()
    checks.ok(
        "보드 - 뒤집기 class가 끝난 뒤 떨어짐",
        remaining_flips == 0,
        f"남은 flip={remaining_flips}",
    )

    states = [item["state"] for item in row_snapshot(page, 0)]
    expected = score_guess(guess, answer)
    checks.ok(
        "보드 - 제출 뒤 판정 색이 정답과 일치",
        states == expected,
        f"실제 {states} / 기대 {expected}",
    )
    checks.ok(
        "보드 - 제출 뒤 글자가 대문자로 유지됨",
        "".join(item["text"] for item in row_snapshot(page, 0)) == guess.upper(),
    )


def scenario_keyboard(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    pair = find_present_pair(page, answer)
    if not pair:
        checks.ok("키보드 - 색 누적용 두 줄 준비", False, "present→correct 쌍을 찾지 못했습니다")
        return

    checks.ok("키보드 - 화면 키 28개", page.locator("#keyboard .key").count() == 28)
    page.click('#keyboard .key[data-key="q"]')
    checks.ok(
        "키보드 - 화면 키 클릭으로 글자 입력",
        tile_state(page, 0, 0) == "filled" and tile_text(page, 0, 0) == "Q",
        f"실제 {tile_text(page, 0, 0)}",
    )
    page.keyboard.press("Backspace")
    checks.ok(
        "키보드 - 입력 지우기",
        tile_state(page, 0, 0) == "empty" and tile_text(page, 0, 0) == "",
    )

    first = pair["first"]
    page.keyboard.type(first)
    page.wait_for_function(
        "() => document.querySelector('#board .row:nth-child(1) .tile:nth-child(5)').dataset.state === 'filled'"
    )
    checks.ok(
        "키보드 - 물리 키보드 입력",
        "".join(item["text"] for item in row_snapshot(page, 0)) == first.upper(),
    )
    page.keyboard.press("Enter")
    wait_submit_settled(page, 0, first)

    first_states = [item["state"] for item in row_snapshot(page, 0)]
    expected_key = {}
    rank = {"absent": 1, "present": 2, "correct": 3}
    for char, state in zip(first, first_states):
        if rank[state] > rank.get(expected_key.get(char), 0):
            expected_key[char] = state
    key_snapshot = keyboard_snapshot(page)
    actual_key = {
        item["key"]: item["state"]
        for item in key_snapshot
        if len(item["key"] or "") == 1
    }
    checks.ok(
        "키보드 - 제출한 글자의 키 색이 타일 판정과 같음",
        all(actual_key.get(char) == state for char, state in expected_key.items()),
        f"실제 {actual_key} / 기대 {expected_key}",
    )
    checks.ok(
        "키보드 - 안 친 글자의 키에는 data-state 속성이 없음",
        all(actual_key.get(char) is None for char in "abcdefghijklmnopqrstuvwxyz" if char not in first),
    )

    chosen = pair["char"]
    checks.ok(
        "키보드 - 첫 줄에서 고른 정답 글자가 present",
        first_states[pair["index"]] == "present",
        f"{chosen} 위치 {pair['index']} = {first_states[pair['index']]}",
    )
    checks.ok(
        "키보드 - 키가 첫 줄에서 present",
        actual_key.get(chosen) == "present",
        f"{chosen} = {actual_key.get(chosen)}",
    )

    page.keyboard.type(pair["second"])
    page.keyboard.press("Enter")
    wait_submit_settled(page, 1, pair["second"])
    page.wait_for_function(
        "(ch) => document.querySelector('#keyboard .key[data-key=\"' + ch + '\"]').dataset.state === 'correct'",
        arg=chosen,
        timeout=3000,
    )
    second_key = {
        item["key"]: item["state"]
        for item in keyboard_snapshot(page)
        if len(item["key"] or "") == 1
    }
    checks.ok(
        "키보드 - 다음 줄에서 correct로 올라가고 내려가지 않음",
        second_key.get(chosen) == "correct",
        f"{chosen} = {second_key.get(chosen)}",
    )


def scenario_screen_keys(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    guess = wrong_words(page, answer, 1)[0]
    enter_key = page.locator('#keyboard .key[data-key="enter"]')
    back_key = page.locator('#keyboard .key[data-key="back"]')

    enter_box = enter_key.bounding_box()
    checks.ok(
        "키보드 - 화면 ENTER 키가 보이고 크기가 있음",
        enter_key.is_visible()
        and enter_box is not None
        and enter_box["width"] > 0
        and enter_box["height"] > 0,
        f"보임={enter_key.is_visible()}, box={enter_box}",
    )
    back_box = back_key.bounding_box()
    checks.ok(
        "키보드 - 화면 지우기 키가 보이고 크기가 있음",
        back_key.is_visible()
        and back_box is not None
        and back_box["width"] > 0
        and back_box["height"] > 0,
        f"보임={back_key.is_visible()}, box={back_box}",
    )

    for char in guess:
        page.click(f'#keyboard .key[data-key="{char}"]')
    filled = row_snapshot(page, 0)
    checks.ok(
        "키보드 - 화면 글자 키만으로 첫 줄 다섯 칸을 채움",
        all(item["state"] == "filled" for item in filled)
        and "".join(item["text"] for item in filled) == guess.upper(),
        f"실제 {''.join(item['text'] for item in filled)}",
    )

    page.click('#keyboard .key[data-key="back"]')
    after_back = row_snapshot(page, 0)
    checks.ok(
        "키보드 - 화면 지우기 키가 마지막 글자를 지움",
        after_back[4]["state"] == "empty"
        and after_back[4]["text"] == ""
        and all(item["state"] == "filled" for item in after_back[:4])
        and "".join(item["text"] for item in after_back[:4]) == guess[:4].upper(),
        f"실제 {[item['state'] for item in after_back]} / {''.join(item['text'] for item in after_back)}",
    )

    page.click(f'#keyboard .key[data-key="{guess[-1]}"]')
    page.click('#keyboard .key[data-key="enter"]')
    wait_submit_settled(page, 0, guess)
    submitted = row_snapshot(page, 0)
    checks.ok(
        "키보드 - 화면 ENTER 키로 제출하고 판정이 끝남",
        all(item["state"] in {"correct", "present", "absent"} for item in submitted)
        and "".join(item["text"] for item in submitted) == guess.upper(),
        f"실제 {[item['state'] for item in submitted]}",
    )

    empty_before = row_snapshot(page, 1)
    page.click('#keyboard .key[data-key="enter"]')
    message = toast_text(page)
    empty_after = row_snapshot(page, 1)
    checks.ok(
        "키보드 - 다섯 글자 미만에서 화면 ENTER는 제출하지 않고 안내함",
        empty_after == empty_before
        and all(item["state"] == "empty" and item["text"] == "" for item in empty_after)
        and message == "5글자를 채워 주세요",
        f"토스트={message!r}, 둘째 줄={empty_after}",
    )


def scenario_keyboard_correct_kept(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    pair = page.evaluate(
        "async (a) => { const w = await import('/js/words.js'); const g = await import('/js/game.js');"
        " for (const first of w.ALLOWED) {"
        "   if (first === a) continue;"
        "   const fs = g.scoreGuess(first, a);"
        "   for (let j = 0; j < first.length; j++) {"
        "     if (fs[j] !== 'correct') continue;"
        "     const ch = first[j];"
        "     for (const second of w.ALLOWED) {"
        "       if (second === a || second === first) continue;"
        "       const ss = g.scoreGuess(second, a);"
        "       for (let k = 0; k < second.length; k++) {"
        "         if (k === j || second[k] !== ch) continue;"
        "         if (ss[k] !== 'present' && ss[k] !== 'absent') continue;"
        "         if ([...second].some((c, m) => c === ch && ss[m] === 'correct')) continue;"
        "         return {char: ch, first_index: j, second_index: k, first: first, second: second, first_state: fs[j], second_state: ss[k]};"
        "       }"
        "     }"
        "   }"
        " }"
        " return null; }",
        answer,
    )
    if not pair:
        checks.ok(
            "키보드 - correct에서 내려가는 색 검사용 추측 쌍 준비",
            False,
            "쌍을 찾지 못했습니다",
        )
        return
    checks.ok(
        "키보드 - correct에서 내려가는 색 검사용 추측 쌍 준비",
        True,
        f"첫 줄={pair['first']} ({pair['char']} 위치 {pair['first_index']}), 둘째 줄={pair['second']} ({pair['char']} 위치 {pair['second_index']})",
    )

    page.keyboard.type(pair["first"])
    page.keyboard.press("Enter")
    wait_submit_settled(page, 0, pair["first"])
    first_states = [item["state"] for item in row_snapshot(page, 0)]
    first_key = {
        item["key"]: item["state"]
        for item in keyboard_snapshot(page)
        if len(item["key"] or "") == 1
    }
    chosen = pair["char"]
    checks.ok(
        "키보드 - 첫 줄에서 고른 글자의 타일이 correct",
        first_states[pair["first_index"]] == "correct",
        f"{chosen} 위치 {pair['first_index']} = {first_states[pair['first_index']]}",
    )
    checks.ok(
        "키보드 - 첫 줄에서 고른 글자의 키가 correct",
        first_key.get(chosen) == "correct",
        f"{chosen} = {first_key.get(chosen)}",
    )

    page.keyboard.type(pair["second"])
    page.keyboard.press("Enter")
    wait_submit_settled(page, 1, pair["second"])
    second_states = [item["state"] for item in row_snapshot(page, 1)]
    second_key = {
        item["key"]: item["state"]
        for item in keyboard_snapshot(page)
        if len(item["key"] or "") == 1
    }
    checks.ok(
        "키보드 - 다음 줄에서 같은 글자가 present 또는 absent",
        second_states[pair["second_index"]] in {"present", "absent"},
        f"{chosen} 위치 {pair['second_index']} = {second_states[pair['second_index']]}",
    )
    checks.ok(
        "키보드 - 다음 줄 판정 뒤에도 키가 correct로 유지됨",
        second_key.get(chosen) == "correct",
        f"{chosen}: 첫 줄 타일={first_states[pair['first_index']]}, 둘째 줄 타일={second_states[pair['second_index']]}, 키={second_key.get(chosen)}",
    )


def scenario_invalid(page, checks):
    dismiss_help(page)
    page.keyboard.type("zzzzz")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.querySelector('#board .row:nth-child(1)').classList.contains('shake')",
        timeout=1000,
    )
    checks.ok(
        "없는 단어 - 첫 줄에 shake가 붙음",
        page.locator("#board .row:nth-child(1)").evaluate("el => el.classList.contains('shake')"),
    )
    checks.ok(
        "없는 단어 - 거절 안내 토스트",
        toast_text(page) == "사전에 없는 단어입니다",
        f"토스트={toast_text(page)!r}",
    )
    rejected = row_snapshot(page, 0)
    checks.ok(
        "없는 단어 - 줄이 지워지지 않고 글자가 그대로 남음",
        "".join(item["text"] for item in rejected) == "ZZZZZ"
        and all(item["state"] == "filled" for item in rejected),
    )
    shot(page, "invalid-word")

    for _ in range(5):
        page.keyboard.press("Backspace")
    page.keyboard.type("abc")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.querySelector('#board .row:nth-child(1)').classList.contains('shake')",
        timeout=1000,
    )
    checks.ok(
        "없는 단어 - 다섯 글자 미만도 같은 식으로 거절",
        page.locator("#board .row:nth-child(1)").evaluate("el => el.classList.contains('shake')")
        and toast_text(page) == "5글자를 채워 주세요"
        and "".join(item["text"] for item in row_snapshot(page, 0)) == "ABC",
        f"토스트={toast_text(page)!r}",
    )


def scenario_win(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    started = time.monotonic()

    page.keyboard.type(answer)
    page.keyboard.press("Enter")
    wait_row_done(page, 0)
    states = [item["state"] for item in row_snapshot(page, 0)]
    checks.ok(
        "판 끝 - 이기는 판의 다섯 칸이 모두 correct",
        states == ["correct"] * 5,
        f"실제 {states}",
    )
    checks.ok(
        "판 끝 - 맞은 줄에 글자가 대문자로 남음",
        "".join(item["text"] for item in row_snapshot(page, 0)) == answer.upper(),
    )

    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#board .row:nth-child(1) .tile')).every(t => t.classList.contains('bounce'))",
        timeout=3000,
    )
    checks.ok(
        "판 끝 - 맞은 줄 타일에 bounce",
        page.locator("#board .row:nth-child(1) .tile.bounce").count() == 5,
    )
    praise = toast_text(page)
    checks.ok(
        "판 끝 - 칭찬 토스트",
        praise in {"천재!", "대단해요!", "훌륭해요!", "멋져요!", "좋아요!", "아슬아슬!"},
        f"토스트={praise!r}",
    )
    overlap = page.evaluate(JS_OVERLAP)
    checks.ok(
        "판 끝 - 칭찬 토스트가 떠 있음",
        overlap is not None,
        "토스트가 없습니다" if overlap is None else "",
    )
    checks.ok(
        "판 끝 - 칭찬 토스트가 타일을 가리지 않음",
        overlap is not None and overlap["hit"] == [],
        f"토스트={overlap['text']!r} 가린 타일={overlap['hit']}" if overlap is not None else "토스트가 없습니다",
    )
    checks.ok(
        "판 끝 - 통계 창이 곧바로 열리지 않음",
        page.locator("#modal-stats").get_attribute("hidden") is not None,
    )
    shot(page, "win")

    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    elapsed = time.monotonic() - started
    checks.ok(
        "판 끝 - 이김 뒤 통계 창이 자동으로 열림",
        elapsed >= 2.0,
        f"제출 후 {elapsed:.2f}초",
    )
    checks.ok(
        "판 끝 - 창이 열리면 #app에 inert",
        page.locator("#app").get_attribute("inert") is not None,
    )
    shot(page, "win-stats")

    page.click("#modal-stats .modal-close")
    page.wait_for_function("() => document.getElementById('modal-stats').hidden === true")
    before = board_signature(page)
    page.keyboard.type("abcde")
    page.keyboard.press("Enter")
    checks.ok(
        "판 끝 - 끝난 뒤 글자를 쳐도 보드가 바뀌지 않음",
        board_signature(page) == before,
    )


def scenario_lose(page, checks):
    dismiss_help(page)
    answer = answer_for_page(page)
    wrong = wrong_words(page, answer, 6)
    checks.ok(
        "판 끝 - 정답이 섞이지 않은 틀린 단어 여섯 개 준비",
        len(wrong) == 6
        and len(set(wrong)) == 6
        and all(word != answer for word in wrong),
        f"실제 {wrong}",
    )

    last_started = 0.0
    for index, guess in enumerate(wrong[:5]):
        page.keyboard.type(guess)
        page.keyboard.press("Enter")
        if index == 4:
            last_started = time.monotonic()
        wait_submit_settled(page, index, guess)

    if len(wrong) == 6:
        page.keyboard.type(wrong[5])
        page.keyboard.press("Enter")
        last_started = time.monotonic()
        wait_row_done(page, 5)
        page.wait_for_function(
            "(text) => document.querySelector('#toasts .toast')?.textContent === text",
            arg=f"정답: {answer.upper()}",
            timeout=3000,
        )
        overlap = page.evaluate(JS_OVERLAP)
        checks.ok(
            "판 끝 - 정답 공개 토스트가 떠 있음",
            overlap is not None,
            "토스트가 없습니다" if overlap is None else "",
        )
        checks.ok(
            "판 끝 - 정답 공개 토스트가 타일을 가리지 않음",
            overlap is not None and overlap["hit"] == [],
            f"토스트={overlap['text']!r} 가린 타일={overlap['hit']}" if overlap is not None else "토스트가 없습니다",
        )

    all_rows = page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .row')).map(row => Array.from(row.querySelectorAll('.tile')).map(t => ({state: t.dataset.state, text: t.textContent})))"
    )
    checks.ok(
        "판 끝 - 지는 판의 여섯 줄이 모두 판정됨",
        len(all_rows) == 6
        and all(len(row) == 5 for row in all_rows)
        and all(item["state"] in {"correct", "present", "absent"} for row in all_rows for item in row),
    )
    checks.ok(
        "판 끝 - 여섯 줄 글자가 입력한 틀린 단어와 같음",
        all(
            "".join(item["text"] for item in all_rows[i]) == wrong[i].upper()
            for i in range(6)
        ),
    )
    checks.ok(
        "판 끝 - 정답 공개 토스트에 대문자 정답이 들어 있음",
        toast_text(page) == f"정답: {answer.upper()}",
        f"토스트={toast_text(page)!r}",
    )
    checks.ok(
        "판 끝 - 통계 창이 곧바로 열리지 않음",
        page.locator("#modal-stats").get_attribute("hidden") is not None,
    )
    shot(page, "lose")

    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    elapsed = time.monotonic() - last_started
    checks.ok(
        "판 끝 - 짐 뒤 통계 창이 자동으로 열림",
        elapsed >= 1.5,
        f"마지막 제출 후 {elapsed:.2f}초",
    )
    checks.ok(
        "판 끝 - 창이 열리면 #app에 inert",
        page.locator("#app").get_attribute("inert") is not None,
    )
    checks.ok(
        "판 끝 - 정답 공개 토스트가 사라지지 않음",
        toast_text(page) == f"정답: {answer.upper()}",
    )

    page.click("#modal-stats .modal-close")
    page.wait_for_function("() => document.getElementById('modal-stats').hidden === true")
    before = board_signature(page)
    page.keyboard.type("abcde")
    page.keyboard.press("Enter")
    checks.ok(
        "판 끝 - 끝난 뒤 글자를 쳐도 보드가 바뀌지 않음",
        board_signature(page) == before,
    )


def main():
    set_group("core")
    checks = Checks()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                with server() as base:
                    run_scenario("보드", browser, base, checks, scenario_board)
                    run_scenario("키보드", browser, base, checks, scenario_keyboard)
                    run_scenario("키보드", browser, base, checks, scenario_screen_keys)
                    run_scenario("키보드", browser, base, checks, scenario_keyboard_correct_kept)
                    run_scenario("없는 단어", browser, base, checks, scenario_invalid)
                    run_scenario("판 끝", browser, base, checks, scenario_win)
                    run_scenario("판 끝", browser, base, checks, scenario_lose)
            finally:
                browser.close()
    except Exception as exc:
        print(f"브라우저 시작/실행 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
