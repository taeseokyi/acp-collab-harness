#!/usr/bin/env python3
"""모니터의 프로젝트 '실행' 단추가 격리된 iframe 미리보기를 여는지 브라우저에서 잽니다."""
import datetime
import http.server
import pathlib
import re
import sys
import threading
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import server          # noqa: E402


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


@contextmanager
def monitor_server():
    """인증 끈 평문 http 모니터를 임시 포트에 띄웁니다."""
    handler = type("H", (server.Handler,), {"root": ROOT, "require_auth": False, "tls": False,
                                            "access_token": None, "guard": server.LoginGuard(),
                                            "timeout": 5, "log_message": lambda *a, **k: None})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def contains(inner, outer, tolerance=2):
    return (
        inner["x"] >= outer["x"] - tolerance
        and inner["y"] >= outer["y"] - tolerance
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + tolerance
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + tolerance
    )


def scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)

        project = page.locator("#projects-list .proj-item").filter(has_text="웹워들").first
        run_button = project.locator(".proj-run").first
        run_visible = run_button.is_visible()
        run_text = run_button.inner_text().strip() if run_visible else ""
        checks.ok(
            "'실행' 단추가 눈에 보인다",
            run_visible and run_text == "실행",
            f"visible={run_visible}, text={run_text!r}",
        )

        preview_error = ""
        if run_visible:
            run_button.click()
            try:
                page.wait_for_selector("iframe.proj-app-frame", state="visible", timeout=15000)
            except Exception as exc:
                preview_error = f"{type(exc).__name__}: {exc}"

        iframe = page.locator("iframe.proj-app-frame").first
        iframe_visible = iframe.is_visible()
        iframe_box = iframe.bounding_box()
        iframe_height = iframe_box["height"] if iframe_box is not None else None
        preview_ok = iframe_visible and iframe_height is not None and iframe_height >= 300
        detail = f"visible={iframe_visible}, box={iframe_box}"
        if preview_error:
            detail += f", 대기 오류={preview_error}"
        checks.ok("누르면 미리보기 칸이 보인다", preview_ok, detail)

        sandbox = iframe.get_attribute("sandbox") if iframe_visible else None
        tokens = sandbox.split() if sandbox else []
        checks.ok(
            "격리가 살아 있다 (allow-scripts 있고 allow-same-origin 없음)",
            "allow-scripts" in tokens and "allow-same-origin" not in tokens,
            f"sandbox={sandbox!r}",
        )

        frame = page.frame_locator("iframe.proj-app-frame")
        tiles = frame.locator("#board .tile")
        inner_ok = False
        inner_detail = ""
        try:
            tiles.first.wait_for(state="visible", timeout=20000)
            tile_count = tiles.count()
            first_visible = tiles.first.is_visible()
            inner_ok = tile_count == 30 and first_visible
            inner_detail = f"타일 {tile_count}개, 첫 칸 visible={first_visible}"
        except Exception as exc:
            inner_detail = f"대기 오류={type(exc).__name__}: {exc}"
        checks.ok("안쪽 보드가 진짜로 그려졌다", inner_ok, inner_detail)

        body_box = page.locator("#detail-body").bounding_box()
        contained = iframe_box is not None and body_box is not None and contains(iframe_box, body_box)
        checks.ok(
            "패널 밖으로 잘리지 않는다",
            contained,
            f"iframe={iframe_box}, detail-body={body_box}",
        )

        link = page.locator("#detail-body a[target=_blank]").first
        link_visible = link.is_visible()
        href = link.get_attribute("href") or ""
        rel = link.get_attribute("rel") or ""
        rel_tokens = rel.lower().split()
        checks.ok(
            "'새 탭에서 열기' 링크가 보이고 안전하게 열린다",
            link_visible and href.startswith("/app/") and "noopener" in rel_tokens,
            f"visible={link_visible}, href={href!r}, rel={rel!r}",
        )
    finally:
        ctx.close()


def narrow_scenario(browser, base, checks):
    """폰 폭(390x844)에서 미리보기가 좁은 화면 규칙대로 그려지는가."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)
        project = page.locator("#projects-list .proj-item").filter(has_text="웹워들").first
        project.locator(".proj-run").first.click()
        page.wait_for_selector("iframe.proj-app-frame", state="visible", timeout=15000)
        iframe = page.locator("iframe.proj-app-frame").first
        box = iframe.bounding_box()

        height = box["height"] if box else None
        target = min(0.70 * 844, 640)
        checks.ok(
            "폰 폭에서 미리보기 높이가 좁은 화면 규칙을 따른다",
            height is not None and abs(height - target) <= 2,
            f"height={height}px, target={target}px (기본 규칙이 이기면 658px)",
        )

        body_box = page.locator("#detail-body").bounding_box()
        contained = box is not None and body_box is not None and contains(box, body_box)
        checks.ok(
            "폰 폭에서 패널 밖으로 잘리지 않는다",
            contained,
            f"iframe={box}, detail-body={body_box}",
        )

        scroll = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        checks.ok(
            "폰 폭에서 가로 스크롤이 생기지 않는다",
            scroll <= 1,
            f"document.scrollWidth - innerWidth = {scroll}px",
        )
    finally:
        ctx.close()


def short_scenario(browser, base, checks):
    """짧은 화면(844x390)에서 미리보기 최소 높이가 결과물 키 크기를 지켜 주는가."""
    ctx = browser.new_context(viewport={"width": 844, "height": 390})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)
        project = page.locator("#projects-list .proj-item").filter(has_text="웹워들").first
        project.locator(".proj-run").first.click()
        page.wait_for_selector("iframe.proj-app-frame", state="visible", timeout=15000)
        box = page.locator("iframe.proj-app-frame").first.bounding_box()
        key = page.frame_locator("iframe.proj-app-frame").locator(".key").first
        key.wait_for(state="visible", timeout=20000)
        key_box = key.bounding_box()
        checks.ok(
            "짧은 화면에서도 결과물 키가 32px 이상이다",
            box is not None and key_box is not None and box["height"] >= 426 and key_box["height"] >= 32,
            f"iframe 높이={box and round(box['height'], 1)}, 키 높이={key_box and round(key_box['height'], 1)}",
        )
    finally:
        ctx.close()


def changed_ui_scenario(browser, base, checks):
    """바뀐 화면 다섯 가지를 브라우저에서 실제로 잽니다."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)

        card = page.query_selector("#kisti-section")
        inner_card = page.query_selector("#kisti-card")
        fleet_titles = page.eval_on_selector_all(
            "#panel-fleet .card h2", "els => els.map(e => e.textContent.trim())"
        )
        kisti_titles = [t for t in fleet_titles if t.startswith("KISTI")]
        checks.ok(
            "KISTI 카드가 화면에 없다",
            card is None and inner_card is None and not kisti_titles,
            f"#kisti-section={card}, #kisti-card={inner_card}, "
            f"함대 카드 h2={fleet_titles}, KISTI로 시작={kisti_titles}",
        )

        meta = page.locator("#aimem-meta")
        meta_text = meta.inner_text()
        label = page.locator(".meta-goal .meta-label").first
        value = page.locator(".meta-goal .goal-value").first
        label_text = label.inner_text().strip()
        value_text = value.inner_text().strip()
        checks.ok(
            "'이번 라운드'가 보이고 내용이 있다",
            meta.is_visible()
            and "현재 목표" not in meta_text
            and label.is_visible()
            and label_text == "이번 라운드"
            and value.is_visible()
            and value_text not in ("", "-"),
            f"meta visible={meta.is_visible()}, '현재 목표'={('현재 목표' in meta_text)}, "
            f"label={label_text!r}, value={value_text!r}",
        )

        page.click("#tab-requests")
        page.wait_for_selector("#requests-list .req-block", state="visible", timeout=15000)
        zero = []
        eta_texts = []
        for block in page.query_selector_all("#requests-list .req-block"):
            badge = block.query_selector(".badge")
            status = badge.inner_text().strip() if badge else ""
            etas = [e.inner_text().strip() for e in block.query_selector_all(".eta")]
            eta_texts.extend(etas)
            empty = block.query_selector(".req-body .empty")
            if empty is not None:
                zero.append((status, empty.inner_text().strip(), etas))
            elif status == "DONE":
                metas = block.query_selector_all(".req-title-wrap .req-meta")
                zero.append((status, metas[-1].inner_text().strip() if metas else "", etas))

        today = datetime.date.today().isoformat()
        has_datetime = any(
            re.search(r"ETA\s+\d", e)
            or re.search(r"ETA\s+" + re.escape(today), e)
            or re.search(r"ETA\s+\d{1,2}:\d{2}", e)
            for e in eta_texts
        )
        expected = {
            "NEW": "관리자 분담 대기",
            "PLANNED": "분담 계획됨",
            "DONE": "서브태스크 없이 끝난 요청입니다",
        }
        bad_zero = [
            (status, msg, etas)
            for status, msg, etas in zero
            if status not in expected
            or expected[status] not in msg
            or any(e not in ("ETA 미정", "종료") for e in etas)
        ]
        zero_with_eta = sum(1 for _, _, etas in zero if etas)
        checks.ok(
            "분담 전 요청의 ETA가 '미정'이다",
            bool(zero)
            and zero_with_eta > 0
            and not has_datetime
            and not bad_zero,
            f"서브태스크 0건 {len(zero)}개(ETA 표시 {zero_with_eta}개), .eta 전체={eta_texts}, "
            f"날짜·시각 붙은 ETA={has_datetime}, 상태/문구 어긋남={bad_zero}",
        )

        page.click("#tab-fleet")
        page.wait_for_selector("#runs-table-wrap", state="visible", timeout=15000)
        project_names = page.query_selector_all("#runs-table-wrap .proj-tag:not(.none) .proj-name")
        none_names = page.query_selector_all("#runs-table-wrap .proj-tag.none .proj-name")
        rounds = page.query_selector_all("#runs-table-wrap .proj-round")

        def weight(el):
            return int(el.evaluate("e=>getComputedStyle(e).fontWeight"))

        project_weights = [weight(e) for e in project_names]
        none_weights = [weight(e) for e in none_names]
        round_weights = [weight(e) for e in rounds]
        checks.ok(
            "프로젝트 칸의 볼드 기준",
            bool(project_names)
            and bool(none_names)
            and bool(rounds)
            and all(w >= 700 for w in project_weights)
            and all(w <= 500 for w in none_weights)
            and all(w <= 500 for w in round_weights),
            f"프로젝트 이름 {project_weights}, 프로젝트 없음 {none_weights}, 라운드 꼬리표 {round_weights}",
        )

        page.set_viewport_size({"width": 390, "height": 780})
        page.click("#tab-board")
        page.wait_for_selector("#panel-board", state="visible", timeout=15000)
        candidates = page.query_selector_all(
            "#board-section .elide[role=button], #queue-section .elide[role=button]"
        )
        el = None
        sw_before = cw_before = None
        for cand in candidates:
            if not cand.is_visible():
                continue
            sw = cand.evaluate("e=>e.scrollWidth")
            cw = cand.evaluate("e=>e.clientWidth")
            if sw > cw:
                el = cand
                sw_before, cw_before = sw, cw
                break

        if el is None:
            checks.ok(
                "생략된 제목을 눌러 펼칠 수 있다 (폰 폭 390px)",
                False,
                "잘린 .elide[role=button]을 보드·큐에서 찾지 못함",
            )
        else:
            box_before = el.bounding_box()
            el.click()
            page.wait_for_selector(".elide.elide-open", timeout=3000)
            class_after = el.get_attribute("class") or ""
            box_after = el.bounding_box()
            sw_after = el.evaluate("e=>e.scrollWidth")
            cw_after = el.evaluate("e=>e.clientWidth")
            overlay = page.query_selector("#detail-overlay")
            overlay_display = overlay.evaluate("e=>getComputedStyle(e).display") if overlay else "missing"
            scroll = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            checks.ok(
                "생략된 제목을 눌러 펼칠 수 있다 (폰 폭 390px)",
                box_before is not None
                and box_after is not None
                and box_after["height"] > box_before["height"]
                and "elide-open" in class_after.split()
                and sw_after <= cw_after + 1
                and overlay_display == "none"
                and scroll == 0,
                f"전: scrollWidth={sw_before}, clientWidth={cw_before}, height={box_before and round(box_before['height'], 2)}; "
                f"후: class={class_after!r}, scrollWidth={sw_after}, clientWidth={cw_after}, "
                f"height={box_after and round(box_after['height'], 2)}; overlay={overlay_display}, 가로스크롤={scroll}px",
            )
    finally:
        ctx.close()


def main():
    checks = Checks()
    try:
        with monitor_server() as base:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    scenario(browser, base, checks)
                    narrow_scenario(browser, base, checks)
                    short_scenario(browser, base, checks)
                    changed_ui_scenario(browser, base, checks)
                finally:
                    browser.close()
    except Exception as exc:
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
