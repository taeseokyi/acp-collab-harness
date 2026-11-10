#!/usr/bin/env python3
"""T-106 웹워들 브라우저 검증 2 - 좁은 폭(360x640)·낮은 창(900x420) 레이아웃.

실제 크로미움으로 두 크기를 열어 보드·키보드·타일·통계 모달이 잘리거나
화면 밖으로 넘치지 않는지 확인하고 스크린샷을 남긴다. 하네스
(browser_harness.py)는 T-105 산출물이라 고치지 않는다.
"""
from playwright.sync_api import sync_playwright

from browser_harness import Checks, new_page, server, set_group, shot

set_group("layout")

TOL = 1  # 1px 오차 허용
GOAL = "접근성/레이아웃"
SIZES = (("narrow", 360, 640), ("short", 900, 420))


def close_help_if_open(page):
    """첫 방문이면 도움말 창이 저절로 열린다 - 닫고 측정한다."""
    if page.locator("#modal-help").is_visible():
        page.locator("#modal-help .modal-close").click()


def measure(c, page, name, w, h):
    """크기 하나에 대해 레이아웃 계열 검사 1~8을 Checks 에 쌓는다."""
    # 1. 가로로 넘치지 않음
    sw = page.evaluate("document.documentElement.scrollWidth")
    c.ok(GOAL, sw <= w + TOL, f"[{name}] document.scrollWidth={sw}, 창너비 {w}")

    # 2. 보드가 다 보임 (가로)
    board = page.locator("#board").bounding_box()
    c.ok(
        GOAL,
        board is not None
        and board["x"] >= -TOL
        and board["x"] + board["width"] <= w + TOL,
        f"[{name}] #board box={board}",
    )

    # 3. 키보드가 다 보임 (가로 + 세로)
    keyboard = page.locator("#keyboard").bounding_box()
    c.ok(
        GOAL,
        keyboard is not None
        and keyboard["x"] >= -TOL
        and keyboard["x"] + keyboard["width"] <= w + TOL
        and keyboard["y"] + keyboard["height"] <= h + TOL,
        f"[{name}] #keyboard box={keyboard}",
    )

    # 4. 첫 줄 타일 다섯 개가 찌그러지지 않음
    tile_probs = []
    for i, tile in enumerate(page.locator("#board .tile").all()[:5]):
        box = tile.bounding_box()
        if box is None:
            tile_probs.append(f"tile{i}:no box")
            continue
        if box["width"] <= 8:
            tile_probs.append(f"tile{i}:width {box['width']}")
        if box["height"] <= 0 or not 0.7 <= box["width"] / box["height"] <= 1.4:
            tile_probs.append(f"tile{i}:ratio {box['width'] / box['height']}")
    c.ok(GOAL, not tile_probs, f"[{name}] first row 5 tiles: {'; '.join(tile_probs) or 'ok'}")

    # 5. 키가 누를 만함 (높이 >= 20px)
    key_probs = []
    for i, key in enumerate(page.locator("#keyboard .key").all()):
        box = key.bounding_box()
        if box is None:
            key_probs.append(f"key{i}:no box")
        elif box["height"] < 20:
            key_probs.append(f"key{i}:height {box['height']}")
    c.ok(GOAL, not key_probs, f"[{name}] key heights>=20: {'; '.join(key_probs) or 'ok'}")

    # 6. 정말 쳐진다 - 첫 줄 다섯 칸이 filled
    page.keyboard.type("crane")
    states = page.evaluate(
        "Array.from(document.querySelectorAll('#board .tile')).slice(0, 5)"
        ".map(t => t.getAttribute('data-state'))"
    )
    c.ok(GOAL, states == ["filled"] * 5, f"[{name}] first row data-state={states}")

    # 7. 글자를 친 뒤에도 보드·키보드가 창 안에 있는지 다시 잰다 (T-114)
    board = page.locator("#board").bounding_box()
    c.ok(
        GOAL,
        board is not None
        and board["x"] >= -TOL
        and board["x"] + board["width"] <= w + TOL,
        f"[{name}] 글자 친 뒤 #board box={board}",
    )

    keyboard = page.locator("#keyboard").bounding_box()
    c.ok(
        GOAL,
        keyboard is not None
        and keyboard["x"] >= -TOL
        and keyboard["x"] + keyboard["width"] <= w + TOL
        and keyboard["y"] + keyboard["height"] <= h + TOL,
        f"[{name}] 글자 친 뒤 #keyboard box={keyboard}",
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            with server() as base:
                c = Checks()
                for name, w, h in SIZES:
                    page = new_page(browser, base, viewport={"width": w, "height": h})
                    try:
                        close_help_if_open(page)
                        measure(c, page, name, w, h)
                        shot(page, name)
                        # 7. 통계 창을 눌러 열고 창 높이를 넘지 않는지 확인
                        page.locator("#btn-stats").click()
                        page.locator("#modal-stats .modal-box").wait_for(state="visible")
                        box = page.locator("#modal-stats .modal-box").bounding_box()
                        c.ok(
                            GOAL,
                            box is not None and box["y"] + box["height"] <= h + TOL,
                            f"[{name}] stats modal-box={box}",
                        )
                        shot(page, f"{name}-modal")
                        page.keyboard.press("Escape")
                    finally:
                        page._close_context()
        finally:
            browser.close()
    raise SystemExit(c.finish())


if __name__ == "__main__":
    main()
