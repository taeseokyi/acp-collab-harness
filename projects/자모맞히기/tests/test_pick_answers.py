"""tools/pick_answers.py 검사 (unittest) - `trend_news.pick` 을 가짜로 바꿔 네트워크 없이 돕니다."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import pick_answers  # noqa: E402
import trend_store  # noqa: E402


def good(days, source, start, **kw):
    good.calls.append((days, source, start, kw))
    return {"ok": True, "titles": 10, "candidates": 4, "checked": 4, "source": source,
            "picks": [{"date": "2026-11-15", "word": "지원"}, {"date": "2026-11-17", "word": "협력"}]}


good.calls = []


def run(argv, **kw):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = pick_answers.main(argv, **kw)
    return rc, out.getvalue(), err.getvalue()


class TestPickAnswers(unittest.TestCase):
    def setUp(self):
        good.calls.clear()
        self.dir = tempfile.TemporaryDirectory()
        self.trend = Path(self.dir.name) / "trend.txt"
        self.meta = Path(self.dir.name) / "trend_meta.json"  # trend 옆 - 진짜 data/ 가 아님

    def tearDown(self):
        self.dir.cleanup()

    def test_dry_run_prints_and_does_not_write(self):
        rc, out, _ = run(["--days", "2", "--dry-run"], pick=good, trend_path=self.trend, rebuild=lambda: 0)
        self.assertEqual(rc, 0)
        self.assertIn("2026-11-15 지원", out)
        self.assertIn("2026-11-17 협력", out)
        self.assertFalse(self.trend.exists())
        self.assertFalse(self.meta.exists())

    def test_writes_rows_and_rebuilds(self):
        rebuilt = []
        rc, out, _ = run(["--days", "2", "--start", "2026-11-15"], pick=good, trend_path=self.trend,
                         rebuild=lambda: rebuilt.append(1) or 0)
        self.assertEqual(rc, 0)
        lines = self.trend.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines[0].startswith("#"))
        self.assertEqual(lines[1:], ["2026-11-15 지원", "2026-11-17 협력"])
        self.assertEqual(rebuilt, [1])
        self.assertIsNotNone(trend_store.last_run(self.meta))
        self.assertIn("2줄 덧붙였습니다", out)

    def test_default_paths_are_the_stores(self):
        self.assertEqual(pick_answers.TREND_PATH, trend_store.TREND_PATH)
        self.assertIn("pick_and_store", (TOOLS / "pick_answers.py").read_text(encoding="utf-8"))

    def test_existing_dates_are_skipped_and_file_appended(self):
        self.trend.write_text("# 머리\n2026-11-16 가나다", encoding="utf-8")  # 끝 개행 없음
        run(["--days", "2"], pick=good, trend_path=self.trend, rebuild=lambda: 0)
        self.assertEqual(good.calls[0][3]["skip_dates"], ["2026-11-16"])
        self.assertEqual(self.trend.read_text(encoding="utf-8").splitlines(),
                         ["# 머리", "2026-11-16 가나다", "2026-11-15 지원", "2026-11-17 협력"])

    def test_args_passed_to_pick(self):
        run(["--days", "3", "--source", "wikipedia", "--start", "2026-12-01", "--dry-run"],
            pick=good, trend_path=self.trend)
        self.assertEqual(good.calls[0][:3], (3, "wikipedia", "2026-12-01"))

    def test_failure_is_rc1_with_reason_and_no_write(self):
        def bad(*a, **k):
            return {"ok": False, "error": "연합뉴스 제목을 받지 못했습니다"}
        rc, _, err = run([], pick=bad, trend_path=self.trend, rebuild=lambda: 0)
        self.assertEqual(rc, 1)
        self.assertIn("연합뉴스", err)
        self.assertFalse(self.trend.exists())

    def test_bad_arguments_rc1(self):
        self.assertEqual(run(["--days", "0"], pick=good, trend_path=self.trend)[0], 1)
        self.assertEqual(run(["--days", "15"], pick=good, trend_path=self.trend)[0], 1)
        self.assertEqual(run(["--start", "2026-13-40"], pick=good, trend_path=self.trend)[0], 1)
        self.assertEqual(good.calls, [])

    def test_no_gemini_left(self):
        text = (TOOLS / "pick_answers.py").read_text(encoding="utf-8")
        self.assertNotIn("GEMINI", text)
        self.assertNotIn("google_search", text)


if __name__ == "__main__":
    unittest.main()
