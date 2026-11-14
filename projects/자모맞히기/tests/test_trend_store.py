"""trend_store.py 검사 (unittest) - 임시 폴더만 쓰고 진짜 data/ 는 건드리지 않습니다."""

from __future__ import annotations

import datetime
import json
import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import trend_store as ts  # noqa: E402


def fake_ok(picks):
    calls = []

    def fn(days, source, start, **kw):
        calls.append((days, source, start, kw))
        return {"ok": True, "picks": picks, "titles": 3, "candidates": 2, "checked": 2, "source": source}
    fn.calls = calls
    return fn


def _append_many(path, start_ordinal, n):
    for i in range(n):
        day = datetime.date.fromordinal(start_ordinal + i).isoformat()
        ts.append_picks([{"date": day, "word": "낱말"}], Path(path))


class TestTrendStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "data" / "trend.txt"
        self.meta = Path(self.dir.name) / "data" / "trend_meta.json"

    def tearDown(self):
        self.dir.cleanup()

    def write(self, text):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def test_paths_point_into_project_data(self):
        self.assertEqual(ts.TREND_PATH, ROOT / "data" / "trend.txt")
        self.assertEqual(ts.META_PATH, ROOT / "data" / "trend_meta.json")

    def test_read_missing_file_is_empty(self):
        self.assertEqual(ts.read_trend(self.path), {})

    def test_read_skips_comments_blank_and_broken_lines(self):
        self.write("# 머리\n\n2026-11-15 지원\n깨진 줄\n2026-13-40 가나다\n2026-11-16\n  2026-11-17   협력  \n")
        self.assertEqual(ts.read_trend(self.path), {"2026-11-15": "지원", "2026-11-17": "협력"})

    def test_append_creates_file_with_header(self):
        added = ts.append_picks([{"date": "2026-11-15", "word": "지원"}], self.path)
        self.assertEqual(added, [{"date": "2026-11-15", "word": "지원"}])
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines[0].startswith("#"))
        self.assertEqual(lines[1:], ["2026-11-15 지원"])

    def test_append_never_overwrites_existing_date(self):
        self.write("# 머리\n2026-11-15 지원\n")
        added = ts.append_picks([{"date": "2026-11-15", "word": "다른말"},
                                 {"date": "2026-11-16", "word": "혐의"}], self.path)
        self.assertEqual(added, [{"date": "2026-11-16", "word": "혐의"}])
        self.assertEqual(ts.read_trend(self.path), {"2026-11-15": "지원", "2026-11-16": "혐의"})

    def test_append_rejects_bad_shapes(self):
        added = ts.append_picks([{"date": "내일", "word": "가나다"}, {"date": "2026-11-15", "word": ""},
                                 {"date": "2026-11-15", "word": "두 낱말"}, {"date": "2026-02-30", "word": "가"},
                                 {"word": "없음"}, "문자열", None, {"date": "2026-11-16", "word": "혐의"}], self.path)
        self.assertEqual(added, [{"date": "2026-11-16", "word": "혐의"}])
        self.assertEqual(ts.read_trend(self.path), {"2026-11-16": "혐의"})

    def test_append_order_and_missing_trailing_newline(self):
        self.write("# 머리\n2026-11-16 가나다")  # 끝 개행 없음
        ts.append_picks([{"date": "2026-11-20", "word": "국회"}, {"date": "2026-11-18", "word": "중단"}], self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8").splitlines(),
                         ["# 머리", "2026-11-16 가나다", "2026-11-20 국회", "2026-11-18 중단"])

    def test_append_nothing_does_not_create_file(self):
        self.assertEqual(ts.append_picks([], self.path), [])
        self.assertFalse(self.path.exists())

    def test_atomic_write_leaves_no_temp_files(self):
        ts.append_picks([{"date": "2026-11-15", "word": "지원"}], self.path)
        ts.record_run(meta_path=self.meta)
        names = sorted(p.name for p in self.path.parent.iterdir())
        self.assertEqual(names, [".trend.lock", "trend.txt", "trend_meta.json"])

    def test_last_run_none_when_missing_or_broken(self):
        self.assertIsNone(ts.last_run(self.meta))
        self.meta.parent.mkdir(parents=True, exist_ok=True)
        self.meta.write_text("{깨짐", encoding="utf-8")
        self.assertIsNone(ts.last_run(self.meta))
        self.meta.write_text('{"last_run": 5}', encoding="utf-8")
        self.assertIsNone(ts.last_run(self.meta))

    def test_record_run_is_iso_with_timezone(self):
        stamp = ts.record_run(meta_path=self.meta)
        parsed = datetime.datetime.fromisoformat(stamp)
        self.assertIsNotNone(parsed.utcoffset())
        self.assertEqual(ts.last_run(self.meta), stamp)
        self.assertEqual(json.loads(self.meta.read_text(encoding="utf-8")), {"last_run": stamp})

    def test_record_run_with_given_time(self):
        when = datetime.datetime(2026, 11, 15, 1, 47, 40, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
        self.assertEqual(ts.record_run(when, self.meta), "2026-11-15T01:47:40+09:00")

    def test_pick_and_store_skips_existing_dates_and_adds(self):
        self.write("# 머리\n2026-11-16 혐의\n")
        fn = fake_ok([{"date": "2026-11-15", "word": "지원"}, {"date": "2026-11-16", "word": "덮기"}])
        out = ts.pick_and_store(3, "wikipedia", "2026-11-15", skip_dates=["2026-11-20"], pick=fn,
                                path=self.path, meta_path=self.meta)
        self.assertEqual(list(fn.calls[0][3]["skip_dates"]), ["2026-11-16", "2026-11-20"])
        self.assertEqual(fn.calls[0][:3], (3, "wikipedia", "2026-11-15"))
        self.assertTrue(out["ok"])
        self.assertEqual(out["added"], [{"date": "2026-11-15", "word": "지원"}])
        self.assertEqual(out["trend"], {"2026-11-15": "지원", "2026-11-16": "혐의"})
        self.assertEqual(out["last_run"], ts.last_run(self.meta))
        self.assertIsNotNone(out["last_run"])

    def test_pick_and_store_failure_writes_nothing(self):
        out = ts.pick_and_store(3, pick=lambda *a, **k: {"ok": False, "error": "제목 없음"},
                                path=self.path, meta_path=self.meta)
        self.assertEqual((out["ok"], out["error"], out["last_run"]), (False, "제목 없음", None))
        self.assertFalse(self.path.exists())
        self.assertFalse(self.meta.exists())

    def test_pick_and_store_failure_keeps_old_last_run(self):
        old = ts.record_run(meta_path=self.meta)
        out = ts.pick_and_store(3, pick=lambda *a, **k: {"ok": False, "error": "x"},
                                path=self.path, meta_path=self.meta)
        self.assertEqual(out["last_run"], old)

    def test_same_date_second_pick_does_not_overwrite(self):
        ts.pick_and_store(1, pick=fake_ok([{"date": "2026-11-15", "word": "지원"}]),
                          path=self.path, meta_path=self.meta)
        out = ts.pick_and_store(1, pick=fake_ok([{"date": "2026-11-15", "word": "바뀜"}]),
                                path=self.path, meta_path=self.meta)
        self.assertEqual(out["added"], [])
        self.assertEqual(out["trend"], {"2026-11-15": "지원"})

    def test_two_processes_append_without_losing_lines(self):
        base = datetime.date(2030, 1, 1).toordinal()
        ctx = multiprocessing.get_context("fork")
        procs = [ctx.Process(target=_append_many, args=(str(self.path), base + k * 100, 100)) for k in (0, 1)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
            self.assertEqual(p.exitcode, 0)
        self.assertEqual(len(ts.read_trend(self.path)), 200)
        self.assertTrue((self.path.parent / ".trend.lock").exists())


if __name__ == "__main__":
    unittest.main()
