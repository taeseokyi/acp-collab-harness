#!/usr/bin/env python3
"""자모맞히기 브라우저 검사 - 그려진 화면.

규칙은 `.aimem/graph/inputs/r24/CONTRACT.md` 의 '화면' 절을 봅니다.
속성이 아니라 실제로 보이는 것(is_visible/getComputedStyle/bounding_box)을 묻습니다.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from browser_harness import Checks, new_page, server, set_group, shot  # noqa: E402

set_group("game")

UNIT_ALPHABET = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎㅏㅐㅑㅒㅓㅔㅕㅖㅗㅛㅜㅠㅡㅣ"
EMOJI = {"correct": "🟩", "present": "🟨", "absent": "⬛"}
RANK = {"absent": 1, "present": 2, "correct": 3}
STATES = ("correct", "present", "absent")


# ---------------------------------------------------------------- 도우미


def dismiss_help(page):
    if page.locator("#modal-help:not([hidden])").count():
        page.keyboard.press("Escape")
        page.wait_for_function(
            "() => document.getElementById('modal-help').hidden === true"
        )


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


def row_units(page, row):
    return "".join(item["text"] for item in row_snapshot(page, row))


def wait_row_done(page, row, timeout=5000):
    page.wait_for_function(
        "(r) => Array.from(document.querySelectorAll('#board .row:nth-child(' + r + ') .tile'))"
        ".every((t) => ['correct', 'present', 'absent'].includes(t.dataset.state))",
        arg=row + 1,
        timeout=timeout,
    )


def wait_settled(page, row, timeout=6000):
    """판정이 끝나고 busy 가 풀릴 때까지. busy 는 마지막 뒤집기 50ms 뒤에 풀린다."""
    wait_row_done(page, row, timeout=timeout)
    page.wait_for_function(
        "() => document.querySelectorAll('#board .tile.flip').length === 0",
        timeout=timeout,
    )
    page.wait_for_timeout(140)


def toast_texts(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".map((t) => t.textContent)"
    )


def latest_toast(page):
    texts = toast_texts(page)
    return texts[0] if texts else ""


def keyboard_states(page):
    return page.evaluate(
        "() => Object.fromEntries(Array.from(document.querySelectorAll('#keyboard .key'))"
        ".map((k) => [k.dataset.key, k.hasAttribute('data-state') ? k.dataset.state : null]))"
    )


def plain_key_ids(page):
    return page.evaluate(
        "async () => { const j = await import('./js/jamo.js');"
        " return Object.values(j.KEYMAP).map((pair) => pair[0]); }"
    )


def answer_word(page):
    return page.evaluate(
        "async () => { const g = await import('./js/game.js');"
        " const w = await import('./js/words.js');"
        " return g.answerForDate(new Date(), w.ANSWERS); }"
    )


def units_of(page, word):
    return page.evaluate(
        "async (w) => { const j = await import('./js/jamo.js'); return j.toUnits(w); }",
        word,
    )


def compose_of(page, units):
    return page.evaluate(
        "async (u) => { const j = await import('./js/jamo.js'); return j.composeUnits(u); }",
        units,
    )


def puzzle_number(page):
    return page.evaluate(
        "async () => { const g = await import('./js/game.js');"
        " return g.dailyIndex(new Date()) + 1; }"
    )


def allowed_pairs(page):
    return page.evaluate(
        "async () => { const w = await import('./js/words.js');"
        " const j = await import('./js/jamo.js');"
        " return w.ALLOWED.map((word) => [word, j.toUnits(word)]); }"
    )


def allowed_unit_set(page):
    return {units for _word, units in allowed_pairs(page) if units}


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


def press_until_focus(page, element_id, max_tabs=15):
    for _ in range(max_tabs):
        focused = page.evaluate("() => document.activeElement && document.activeElement.id")
        if focused == element_id:
            return True
        page.keyboard.press("Tab")
    return page.evaluate("() => document.activeElement && document.activeElement.id") == element_id


def score_guess(guess, answer):
    """자모(한 글자=한 칸) 문자열 판정. game.js 의 scoreGuess 와 같은 규칙."""
    assert len(guess) == len(answer) == 6
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


def keyboard_state(rows):
    state = {}
    for guess, scores in rows:
        for char, score in zip(guess, scores):
            if char not in state or RANK[score] > RANK[state[char]]:
                state[char] = score
    return state


def mixed_wrong(pairs, answer_units):
    """정답과 다른, 판정 세 가지가 섞이는 낱말 하나."""
    best = None
    for word, units in pairs:
        if not units or len(units) != 6 or units == answer_units:
            continue
        scores = score_guess(units, answer_units)
        distinct = len(set(scores))
        if distinct >= 3:
            return word, units, scores
        if distinct == 2 and best is None:
            best = (word, units, scores)
    return best


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


def invalid_units(allowed, prefix, answer_units):
    for tail in ("ㄱㄱㄱ", "ㅂㅂㅂ", "ㅁㅁㅁ", "ㄲㄲㄲ", "ㅋㅋㅋ", "ㅌㅌㅌ"):
        candidate = prefix + tail
        if len(candidate) == 6 and candidate not in allowed and candidate != answer_units:
            return candidate
    for base in ("ㄱ", "ㄲ", "ㅁ", "ㅂ", "ㅅ"):
        candidate = base * 6
        if candidate not in allowed and candidate != answer_units:
            return candidate
    raise AssertionError("목록에 없는 여섯 칸을 만들지 못했습니다")


def rgb_of(value):
    parts = value[value.find("(") + 1 : value.find(")")].split(",")
    return tuple(float(p.strip()) for p in parts[:3])


def brightness(value):
    r, g, b = rgb_of(value)
    return (r * 299 + g * 587 + b * 114) / 1000


def rect_of(locator):
    return locator.bounding_box()


def within(rect, width, height):
    if not rect:
        return False
    return (
        rect["x"] >= -0.5
        and rect["y"] >= -0.5
        and rect["x"] + rect["width"] <= width + 0.5
        and rect["y"] + rect["height"] <= height + 0.5
    )


def overlap(a, b):
    if not a or not b:
        return 0.0
    left = max(a["x"], b["x"])
    right = min(a["x"] + a["width"], b["x"] + b["width"])
    top = max(a["y"], b["y"])
    bottom = min(a["y"] + a["height"], b["y"] + b["height"])
    return max(0.0, right - left) * max(0.0, bottom - top)


# ---------------------------------------------------------------- 시나리오


def scenario_help(page, checks):
    page.wait_for_selector("#modal-help:not([hidden])", timeout=5000)
    modal = page.locator("#modal-help")
    checks.ok("도움말 - 첫 방문에 보임", modal.is_visible())
    text = modal.text_content() or ""
    checks.ok(
        "도움말 - 칸 규칙과 겹모음 글자가 보임",
        "겹모음" in text and "ㅘ=ㅗㅏ" in text and "ㅢ=ㅡㅣ" in text,
    )
    checks.ok(
        "도움말 - 겹받침 글자가 보임",
        "겹받침" in text and "ㄳ=ㄱㅅ" in text and "ㅄ=ㅂㅅ" in text,
    )
    checks.ok(
        "도움말 - Shift 사용법이 보임",
        "Shift" in text and "쌍자음" in text,
    )
    examples = page.locator("#modal-help .example .tile")
    checks.ok(
        "도움말 - 예시 타일 18개가 보임",
        examples.count() == 18 and all(examples.nth(i).is_visible() for i in range(18)),
        f"실제 {examples.count()}",
    )
    states = page.evaluate(
        "() => Array.from(document.querySelectorAll('#modal-help .example .tile'))"
        ".map((t) => t.dataset.state)"
    )
    checks.ok(
        "도움말 - 예시에 맞음/자리 틀림/없음 세 색이 있음",
        {"correct", "present", "absent"} <= set(states),
        f"실제 {sorted(set(states))}",
    )
    shot(page, "help-first")

    page.locator("#modal-help .modal-close").click()
    page.wait_for_function("() => document.getElementById('modal-help').hidden === true")
    checks.ok("도움말 - 닫힘", not modal.is_visible())

    page.click("#btn-help")
    page.wait_for_selector("#modal-help:not([hidden])", timeout=3000)
    checks.ok("도움말 - #btn-help 로 다시 보임", modal.is_visible())
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-help').hidden === true")


def scenario_physical_keys(page, checks):
    dismiss_help(page)
    page.keyboard.press("KeyG")
    page.keyboard.press("KeyK")
    page.keyboard.press("KeyS")
    typed = "".join(tile_text(page, 0, c) for c in range(3))
    checks.ok(
        "실물 자판 - KeyG KeyK KeyS 가 ㅎㅏㄴ 으로 보임",
        typed == "ㅎㅏㄴ"
        and all(tile_state(page, 0, c) == "filled" for c in range(3))
        and all(tile(page, 0, c).is_visible() for c in range(3)),
        f"실제 {typed!r}",
    )
    checks.ok(
        "실물 자판 - 미리보기 '한'",
        (page.locator("#preview").text_content() or "") == "한",
        f"실제 {(page.locator('#preview').text_content() or '')!r}",
    )

    page.keyboard.press("Shift+KeyR")
    checks.ok(
        "실물 자판 - Shift+KeyR 이 ㄲ 한 칸",
        tile_text(page, 0, 3) == "ㄲ" and tile_state(page, 0, 3) == "filled",
        f"실제 {tile_text(page, 0, 3)!r}",
    )
    checks.ok(
        "실물 자판 - 미리보기 '한ㄲ'",
        (page.locator("#preview").text_content() or "") == "한ㄲ",
        f"실제 {(page.locator('#preview').text_content() or '')!r}",
    )

    page.keyboard.press("Control+KeyA")
    checks.ok(
        "실물 자판 - Ctrl+A 는 아무 칸도 넣지 않음",
        tile_state(page, 0, 4) == "empty" and tile_text(page, 0, 4) == "",
        f"5번째 칸 {tile_state(page, 0, 4)!r}/{tile_text(page, 0, 4)!r}",
    )
    checks.ok(
        "실물 자판 - Ctrl+A 뒤에도 앞 네 칸 그대로",
        "".join(tile_text(page, 0, c) for c in range(4)) == "ㅎㅏㄴㄲ",
    )


def scenario_screen_shift(page, checks):
    dismiss_help(page)
    key = page.locator('#keyboard .key[data-key="ㄱ"]')
    shift = page.locator('#keyboard .key[data-key="shift"]')
    checks.ok("화면 Shift - 처음엔 ㄱ 키 글자가 ㄱ", (key.text_content() or "") == "ㄱ")

    shift.click()
    checks.ok(
        "화면 Shift - 누르면 ㄱ 키 글자가 ㄲ 으로 보임",
        (key.text_content() or "") == "ㄲ" and key.is_visible(),
        f"실제 {key.text_content()!r}",
    )
    checks.ok(
        "화면 Shift - 켜짐 표시(data-shift/aria-pressed)",
        page.get_attribute("#keyboard", "data-shift") == "on"
        and shift.get_attribute("aria-pressed") == "true",
    )

    key.click()
    checks.ok(
        "화면 Shift - 한 번 넣으면 칸에 ㄲ",
        tile_text(page, 0, 0) == "ㄲ" and tile_state(page, 0, 0) == "filled",
        f"실제 {tile_text(page, 0, 0)!r}",
    )
    checks.ok(
        "화면 Shift - 한 번 넣은 뒤 글자가 ㄱ 으로 돌아옴",
        (key.text_content() or "") == "ㄱ" and key.is_visible(),
        f"실제 {key.text_content()!r}",
    )
    checks.ok(
        "화면 Shift - 넣은 뒤 꺼짐 표시",
        page.get_attribute("#keyboard", "data-shift") is None
        and shift.get_attribute("aria-pressed") == "false",
    )


def scenario_preview(page, checks):
    dismiss_help(page)
    preview = page.locator("#preview")
    checks.ok(
        "미리보기 - 비어 있을 때 빈 글",
        (preview.text_content() or "") == "",
    )
    checks.ok(
        "미리보기 - aria-live off",
        preview.get_attribute("aria-live") == "off",
    )
    page.keyboard.press("KeyG")
    page.keyboard.press("KeyK")
    page.keyboard.press("KeyS")
    checks.ok(
        "미리보기 - 조합 글자 '한' 이 보임",
        (preview.text_content() or "") == "한" and preview.is_visible(),
        f"실제 {(preview.text_content() or '')!r}",
    )
    page.keyboard.press("Shift+KeyR")
    checks.ok(
        "미리보기 - '한ㄲ' 이 보임",
        (preview.text_content() or "") == "한ㄲ",
        f"실제 {(preview.text_content() or '')!r}",
    )

    pairs = allowed_pairs(page)
    answer = units_of(page, answer_word(page))
    wrong = mixed_wrong(pairs, answer) or (None, None, None)
    _word, units, _scores = wrong
    if not units:
        checks.ok("미리보기 - 제출용 낱말 준비", False, "목록에 없는 낱말을 찾지 못했습니다")
        return
    for _ in range(4):
        page.keyboard.press("Backspace")
    type_units(page, units)
    checks.ok(
        "미리보기 - 제출 직전 조합 글자가 보임",
        (preview.text_content() or "") == compose_of(page, units),
        f"실제 {(preview.text_content() or '')!r} / 기대 {compose_of(page, units)!r}",
    )
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    checks.ok(
        "미리보기 - 제출 뒤 비워짐",
        (preview.text_content() or "") == "",
        f"실제 {(preview.text_content() or '')!r}",
    )


def scenario_reject(page, checks):
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    allowed = allowed_unit_set(page)

    page.keyboard.press("KeyG")
    page.keyboard.press("KeyK")
    page.keyboard.press("KeyS")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => t.textContent.includes('자모 6개를 채워 주세요'))",
        timeout=3000,
    )
    toast = page.locator("#toasts .toast").first
    checks.ok(
        "거절 - 모자란 입력에 안내 토스트가 보임",
        toast.is_visible() and "자모 6개를 채워 주세요" in (toast.text_content() or ""),
        f"실제 {(toast.text_content() or '')!r}",
    )
    remain = "".join(tile_text(page, 0, c) for c in range(6))
    checks.ok(
        "거절 - 모자란 입력이어도 친 줄은 그대로",
        remain == "ㅎㅏㄴ"
        and all(tile_state(page, 0, c) == "filled" for c in range(3))
        and all(tile_state(page, 0, c) == "empty" for c in range(3, 6)),
        f"실제 {remain!r}",
    )

    bad = invalid_units(allowed, "ㅎㅏㄴ", answer)
    type_units(page, bad[3:])
    checks.ok(
        "거절 - 목록에 없는 여섯 칸을 채움",
        "".join(tile_text(page, 0, c) for c in range(6)) == bad,
        f"실제 {''.join(tile_text(page, 0, c) for c in range(6))!r} / 기대 {bad!r}",
    )
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => t.textContent.includes('낱말 목록에 없는 낱말입니다'))",
        timeout=3000,
    )
    toast = page.locator("#toasts .toast").first
    checks.ok(
        "거절 - 목록에 없는 낱말에 안내 토스트가 보임",
        toast.is_visible() and "낱말 목록에 없는 낱말입니다" in (toast.text_content() or ""),
        f"실제 {(toast.text_content() or '')!r}",
    )
    checks.ok(
        "거절 - 목록에 없는 낱말이어도 줄과 글자가 그대로",
        "".join(tile_text(page, 0, c) for c in range(6)) == bad
        and all(tile_state(page, 0, c) == "filled" for c in range(6)),
        f"실제 {''.join(tile_text(page, 0, c) for c in range(6))!r}",
    )


def scenario_score(page, checks):
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    pairs = allowed_pairs(page)
    chosen = mixed_wrong(pairs, answer)
    if not chosen:
        checks.ok("판정 - 서로 다른 색이 섞이는 틀린 낱말 준비", False)
        return
    _word, guess, expected = chosen

    type_units(page, guess)
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    snapshot = row_snapshot(page, 0)
    actual = [item["state"] for item in snapshot]
    checks.ok(
        "판정 - 틀린 낱말의 칸 색이 기대 판정과 같음",
        actual == expected,
        f"실제 {actual} / 기대 {expected}",
    )
    checks.ok(
        "판정 - 칸 글자가 자모 그대로 남음",
        "".join(item["text"] for item in snapshot) == guess,
        f"실제 {''.join(item['text'] for item in snapshot)!r}",
    )

    groups = {}
    for col, state in enumerate(expected):
        groups.setdefault(state, set()).add(
            tile(page, 0, col).evaluate("(el) => getComputedStyle(el).backgroundColor")
        )
    checks.ok(
        "판정 - 같은 판정의 칸은 같은 색으로 칠해짐",
        all(len(colors) == 1 for colors in groups.values()),
        f"실제 { {k: sorted(v) for k, v in groups.items()} }",
    )
    checks.ok(
        "판정 - 서로 다른 판정은 다른 색으로 칠해짐",
        len({next(iter(colors)) for colors in groups.values()}) == len(groups),
        f"실제 { {k: sorted(v) for k, v in groups.items()} }",
    )
    checks.ok(
        "판정 - 판정된 칸이 모두 보임",
        all(tile(page, 0, c).is_visible() for c in range(6)),
    )

    state = keyboard_state([(guess, expected)])
    actual_keys = keyboard_states(page)
    expected_keys = {key: state.get(key) for key in plain_key_ids(page)}
    checks.ok(
        "판정 - 자판 키 색이 칸 판정과 같음",
        all(actual_keys.get(key) == value for key, value in expected_keys.items()),
        f"실제 { {k: actual_keys.get(k) for k in expected_keys if actual_keys.get(k) != expected_keys[k]} }",
    )
    colored = {key: value for key, value in expected_keys.items() if value}
    key_colors = {}
    for key, value in colored.items():
        key_colors.setdefault(value, set()).add(
            page.locator(f'#keyboard .key[data-key="{key}"]').evaluate(
                "(el) => getComputedStyle(el).backgroundColor"
            )
        )
    checks.ok(
        "판정 - 자판 키가 판정 색으로 실제로 칠해짐",
        all(len(colors) == 1 for colors in key_colors.values())
        and len({next(iter(colors)) for colors in key_colors.values()}) == len(key_colors),
        f"실제 { {k: sorted(v) for k, v in key_colors.items()} }",
    )


def scenario_win(page, checks):
    dismiss_help(page)
    word = answer_word(page)
    units = units_of(page, word)
    number = puzzle_number(page)
    type_units(page, units)
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    checks.ok("승리 - 통계 창이 보임", page.locator("#modal-stats").is_visible())
    shot(page, "win-stats")

    stats = page.eval_on_selector_all(
        "#stat-row .stat b", "els => els.map((e) => e.textContent)"
    )
    checks.ok(
        "승리 - 판수 1, 승률 100",
        stats[:2] == ["1", "100"],
        f"실제 {stats}",
    )
    checks.ok(
        "승리 - 연승 1, 최대 연승 1",
        stats[2:] == ["1", "1"],
        f"실제 {stats}",
    )
    dist = page.eval_on_selector_all(
        "#dist .bar", "els => els.map((e) => e.textContent)"
    )
    highlighted = page.eval_on_selector_all(
        "#dist .bar.hl", "els => els.map((e) => e.textContent)"
    )
    checks.ok(
        "승리 - 추측 분포 첫 칸만 1, 나머지 0",
        dist == ["1", "0", "0", "0", "0", "0"],
        f"실제 {dist}",
    )
    checks.ok(
        "승리 - 이긴 줄(1번째)만 분포에서 강조됨",
        highlighted == ["1"],
        f"실제 강조 {highlighted}",
    )
    signature = board_snapshot(page)
    checks.ok(
        "승리 - 정답 줄이 모두 correct",
        [item["state"] for item in signature[:6]] == ["correct"] * 6,
        f"실제 {[item['state'] for item in signature[:6]]}",
    )
    checks.ok(
        "승리 - 정답 낱말 번호가 오늘 번호",
        number == puzzle_number(page),
    )

    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=5000)
    after = board_snapshot(page)
    checks.ok(
        "승리 - 새로 고쳐도 끝난 판과 줄이 그대로",
        after == signature,
        f"실제 {[i['state'] for i in after[:6]]}",
    )
    stats_after = page.eval_on_selector_all(
        "#stat-row .stat b", "els => els.map((e) => e.textContent)"
    )
    checks.ok(
        "승리 - 새로 고쳐도 판수 1, 승률 100 그대로",
        stats_after[:2] == ["1", "100"],
        f"실제 {stats_after}",
    )


def scenario_share(page, checks):
    dismiss_help(page)
    answer = units_of(page, answer_word(page))
    number = puzzle_number(page)
    pairs = allowed_pairs(page)
    chosen = mixed_wrong(pairs, answer)
    if not chosen:
        checks.ok("공유 - 틀린 줄 하나 준비", False)
        return
    _word, guess, _scores = chosen
    type_units(page, guess)
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    type_units(page, answer)
    page.keyboard.press("Enter")
    wait_settled(page, 1)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    checks.ok(
        "공유 - 통계 창의 공유 단추가 보임",
        page.locator("#btn-share").is_visible(),
    )
    page.click("#btn-share")
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => t.textContent.includes('클립보드에 복사했습니다'))",
        timeout=3000,
    )
    text = page.evaluate("() => navigator.clipboard.readText()")
    lines = text.split("\n")
    checks.ok(
        "공유 - 첫 줄이 '자모맞히기 N 2/6'",
        len(lines) > 0 and lines[0] == f"자모맞히기 {number} 2/6",
        f"실제 {lines[0]!r}",
    )
    checks.ok("공유 - 둘째 줄이 빈 줄", len(lines) > 1 and lines[1] == "", f"실제 {lines[:2]}")
    grid = lines[2:]
    checks.ok(
        "공유 - 줄마다 이모지 6개",
        len(grid) == 2 and all(len(row) == 6 for row in grid)
        and all(ch in "🟩🟨⬛" for row in grid for ch in row),
        f"실제 {grid}",
    )
    word = answer_word(page)
    checks.ok(
        "공유 - 정답 낱말이 글에 없음",
        word not in text and answer not in text,
        f"실제 글={text!r}",
    )
    shot(page, "share")


def scenario_lose(page, checks):
    dismiss_help(page)
    word = answer_word(page)
    answer = units_of(page, word)
    pairs = allowed_pairs(page)
    wrongs = six_wrongs(pairs, answer)
    for row, (_guess_word, guess) in enumerate(wrongs):
        type_units(page, guess)
        page.keyboard.press("Enter")
        wait_settled(page, row)

    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('#toasts .toast'))"
        ".some((t) => (t.textContent || '').startsWith('정답: '))",
        timeout=5000,
    )
    toast = page.locator("#toasts .toast").first
    text = toast.text_content() or ""
    checks.ok(
        "패배 - 정답 안내가 보임",
        toast.is_visible() and text.startswith("정답: "),
        f"실제 {text!r}",
    )
    shown = text[len("정답: ") :] if text.startswith("정답: ") else ""
    checks.ok(
        "패배 - 정답이 한글 낱말로 보임",
        bool(shown) and all("가" <= ch <= "힣" for ch in shown),
        f"실제 {shown!r}",
    )
    checks.ok(
        "패배 - 안내가 오늘 정답 낱말과 같음",
        shown == word,
        f"실제 {shown!r} / 기대 {word!r}",
    )
    rows = page.locator("#board .row").count()
    scored = page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .row')).filter((r) =>"
        " Array.from(r.querySelectorAll('.tile')).every((t) =>"
        " ['correct','present','absent'].includes(t.dataset.state))).length"
    )
    checks.ok(
        "패배 - 여섯 줄이 모두 판정됨",
        rows == 6 and scored == 6,
        f"줄 {rows}, 판정 {scored}",
    )
    shot(page, "lose")


def scenario_practice(page, checks):
    dismiss_help(page)
    page.keyboard.press("KeyG")
    page.keyboard.press("KeyK")
    daily = board_snapshot(page)
    checks.ok(
        "연습 - 날마다 판에 친 두 칸이 있음",
        "".join(item["text"] for item in daily[:2]) == "ㅎㅏ",
    )

    page.evaluate("() => { Math.random = () => 0; }")
    page.click("#mode-practice")
    checks.ok(
        "연습 - 연습 단추가 눌림으로 표시됨",
        page.get_attribute("#mode-practice", "aria-pressed") == "true"
        and page.get_attribute("#mode-daily", "aria-pressed") == "false",
    )
    checks.ok("연습 - 빈 판", all(item["state"] == "empty" and item["text"] == "" for item in board_snapshot(page)))
    checks.ok("연습 - #btn-new 가 보임", page.locator("#btn-new").is_visible())

    practice_word = page.evaluate(
        "async () => { const w = await import('./js/words.js'); return w.ANSWERS[0]; }"
    )
    practice_units = units_of(page, practice_word)
    type_units(page, practice_units)
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    page.wait_for_selector("#modal-stats:not([hidden])", timeout=6000)
    stats = page.eval_on_selector_all(
        "#stat-row .stat b", "els => els.map((e) => e.textContent)"
    )
    checks.ok(
        "연습 - 이겨도 통계 판수가 늘지 않음",
        stats[:2] == ["0", "0"],
        f"실제 {stats}",
    )

    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-stats').hidden === true")
    page.click("#btn-new")
    checks.ok(
        "연습 - #btn-new 로 빈 새 판",
        all(item["state"] == "empty" and item["text"] == "" for item in board_snapshot(page)),
    )
    checks.ok(
        "연습 - 새 판에서도 #btn-new 가 보임",
        page.locator("#btn-new").is_visible(),
    )

    page.click("#mode-daily")
    checks.ok(
        "연습 - 날마다로 돌아가면 치던 칸까지 그대로",
        board_snapshot(page) == daily,
        f"실제 {[i['text'] for i in board_snapshot(page)[:3]]}",
    )
    checks.ok(
        "연습 - 날마다에서는 #btn-new 가 숨음",
        not page.locator("#btn-new").is_visible(),
    )


def scenario_layout(page, checks, width, height):
    label = f"폭 {width}"
    dismiss_help(page)
    page.wait_for_function("() => !document.querySelector('.modal:not([hidden])')")
    modes = page.locator("#modes")
    board = page.locator("#board")
    keyboard = page.locator("#keyboard")
    rects = {
        "modes": rect_of(modes),
        "board": rect_of(board),
        "keyboard": rect_of(keyboard),
    }
    checks.ok(
        f"{label} - 보드·자판·모드가 화면 안에 있음",
        all(within(rects[key], width, height) for key in rects),
        f"실제 {rects}",
    )
    checks.ok(
        f"{label} - 보드·자판·모드가 서로 겹치지 않음",
        overlap(rects["modes"], rects["board"]) == 0
        and overlap(rects["board"], rects["keyboard"]) == 0
        and overlap(rects["modes"], rects["keyboard"]) == 0,
        f"겹침 { {a + '-' + b: overlap(rects[a], rects[b]) for a in rects for b in rects if a < b} }",
    )

    row_counts = [10, 10, 9]
    for index in range(3):
        keys = page.locator(f"#keyboard .krow:nth-child({index + 1}) .key")
        count = keys.count()
        boxes = [keys.nth(i).bounding_box() for i in range(count)]
        last = boxes[-1] if boxes else None
        checks.ok(
            f"{label} - 자판 {index + 1}줄 {row_counts[index]}키가 잘리지 않음",
            count == row_counts[index]
            and all(box and box["width"] > 0 and box["x"] >= -0.5 and box["x"] + box["width"] <= width + 0.5 for box in boxes)
            and last is not None
            and last["x"] + last["width"] <= width + 0.5,
            f"키 {count}개, 끝 키 오른쪽={None if not last else round(last['x'] + last['width'], 1)} / 화면 {width}",
        )

    units = units_of(page, answer_word(page))
    type_units(page, units)
    tile_boxes = page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .tile'))"
        ".map((t) => { const r = t.getBoundingClientRect();"
        " return {x: r.x, y: r.y, width: r.width, height: r.height}; })"
    )
    checks.ok(
        f"{label} - 여섯 칸을 다 친 뒤에도 칸이 화면 안에 있음",
        all(within(box, width, height) for box in tile_boxes),
        f"벗어난 칸 {[i for i, box in enumerate(tile_boxes) if not within(box, width, height)]}",
    )
    checks.ok(
        f"{label} - 여섯 칸을 다 친 뒤에도 보드·자판이 화면 밖으로 안 나감",
        within(rect_of(board), width, height) and within(rect_of(keyboard), width, height),
        f"보드 {rect_of(board)}, 자판 {rect_of(keyboard)}",
    )
    if width == 320:
        shot(page, "layout-320")


def scenario_dark(page, checks):
    dismiss_help(page)
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    light = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    checks.ok(
        "어두운 테마 - 처음엔 밝은 배경",
        brightness(light) > 150,
        f"실제 {light}",
    )

    page.check("#set-dark")
    page.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
    dark = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    checks.ok(
        "어두운 테마 - 켜면 body 배경이 실제로 어두워짐",
        brightness(dark) < brightness(light) and brightness(dark) < 80,
        f"밝음 {light} / 어두움 {dark}",
    )
    shot(page, "theme-dark")

    page.keyboard.press("Escape")
    page.reload(wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    checks.ok(
        "어두운 테마 - 새로 고쳐도 어두운 속성 유지",
        page.evaluate("() => document.documentElement.dataset.theme") == "dark",
    )
    persisted = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    checks.ok(
        "어두운 테마 - 새로 고친 뒤 칠해진 배경색이 같음",
        persisted == dark,
        f"전 {dark} / 후 {persisted}",
    )
    page.click("#btn-settings")
    page.wait_for_selector("#modal-settings:not([hidden])", timeout=3000)
    checks.ok(
        "어두운 테마 - 설정 체크박스도 켜져 있음",
        page.is_checked("#set-dark"),
    )
    page.keyboard.press("Escape")


def scenario_keyboard_only(page, checks):
    page.wait_for_selector("#modal-help:not([hidden])", timeout=5000)
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-help').hidden === true")
    checks.ok("키보드만 - 첫 도움말을 Escape 로 닫음", page.evaluate(
        "() => document.getElementById('modal-help').hidden"
    ))

    checks.ok("키보드만 - Tab 으로 #btn-help 에 감", press_until_focus(page, "btn-help"))
    page.keyboard.press("Enter")
    page.wait_for_selector("#modal-help:not([hidden])", timeout=3000)
    checks.ok(
        "키보드만 - Enter 로 도움말 창이 열림",
        page.locator("#modal-help").is_visible(),
    )
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('modal-help').hidden === true")
    checks.ok(
        "키보드만 - Escape 로 창이 닫힘",
        not page.locator("#modal-help").is_visible(),
    )

    checks.ok("키보드만 - Tab 으로 모드 단추에 감", press_until_focus(page, "mode-daily"))
    units = units_of(page, answer_word(page))
    type_units(page, units)
    checks.ok(
        "키보드만 - 물리 자판만으로 여섯 칸을 채움",
        "".join(tile_text(page, 0, c) for c in range(6)) == units,
        f"실제 {''.join(tile_text(page, 0, c) for c in range(6))!r}",
    )
    page.keyboard.press("Enter")
    wait_settled(page, 0)
    live = page.get_attribute("#toasts", "aria-live")
    page.wait_for_function(
        "() => document.querySelectorAll('#toasts .toast').length > 0",
        timeout=3000,
    )
    text = latest_toast(page)
    checks.ok(
        "키보드만 - 결과가 aria-live 영역에 글로 남음",
        live == "polite" and bool(text),
        f"aria-live={live!r}, 글={text!r}",
    )


# ---------------------------------------------------------------- 실행


def run_scenario(label, checks, scenario, browser, base, viewport=None, clipboard=False):
    page = new_page(browser, base, viewport=viewport, clipboard=clipboard)
    failures_before = sum(1 for passed, _g, _d in checks.results if not passed)
    try:
        scenario(page, checks)
        errors = list(page._errors)
    except Exception as exc:  # 시나리오가 죽어도 그때까지의 검사는 남긴다
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
                run_scenario("도움말", checks, scenario_help, browser, base)
                run_scenario("실물 자판", checks, scenario_physical_keys, browser, base)
                run_scenario("화면 Shift", checks, scenario_screen_shift, browser, base)
                run_scenario("미리보기", checks, scenario_preview, browser, base)
                run_scenario("거절", checks, scenario_reject, browser, base)
                run_scenario("판정", checks, scenario_score, browser, base)
                run_scenario("승리", checks, scenario_win, browser, base)
                run_scenario("공유", checks, scenario_share, browser, base, clipboard=True)
                run_scenario("패배", checks, scenario_lose, browser, base)
                run_scenario("연습", checks, scenario_practice, browser, base)
                for width, height in ((320, 640), (375, 667), (430, 740), (1280, 900)):
                    run_scenario(
                        f"레이아웃 {width}",
                        checks,
                        lambda page, checks, w=width, h=height: scenario_layout(page, checks, w, h),
                        browser,
                        base,
                        viewport={"width": width, "height": height},
                    )
                run_scenario("어두운 테마", checks, scenario_dark, browser, base)
                run_scenario("키보드만", checks, scenario_keyboard_only, browser, base)
            finally:
                browser.close()
    failures = checks.finish()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
