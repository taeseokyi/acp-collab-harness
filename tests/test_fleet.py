"""`tools/fleet.py` 의 운영 상태 DB 우선 / 마크다운 폴백 경로 회귀 테스트.

표준 라이브러리 unittest + tempfile + unittest.mock 만 쓴다. 실제
`.aimem/aimem.db` 는 읽지도 쓰지도 않는다 - DB 경로와 `state_dict()` 를
임시 파일/가짜 값으로 갈아끼운다. 모든 테스트의 `setUp` 에서 모듈 전역
캐시 `fleet._DB_CACHE` 를 비워 테스트 사이 상태가 새지 않게 한다.
"""
import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import aimem_db  # noqa: E402
import fleet  # noqa: E402


class FleetDbFallbackTests(unittest.TestCase):
    def setUp(self):
        fleet._DB_CACHE.update(at=0.0, state=None)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        # `db_state()` 가 실제 DB 를 건드리지 않도록 존재하는 빈 파일로 갈아끼운다.
        self.dummy_db = self.tmp / "dummy-aimem.db"
        self.dummy_db.touch()
        p = mock.patch.object(aimem_db, "DB", self.dummy_db)
        p.start()
        self.addCleanup(p.stop)

    def _write_aimem(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_roster_db_path_filters_invalid_slot_names(self):
        state = {
            "rev": 114,
            "slots": [
                {"slot": "S1", "token": "a41f0c", "harness": "claude",
                 "model": "opus", "role": "역할", "note": "비고"},
                {"slot": "S10", "token": "b10b10", "harness": "codex",
                 "model": "gpt", "role": "역할", "note": "비고"},
                {"slot": "관리자", "token": "no", "harness": "claude",
                 "model": "opus", "role": "관리자", "note": ""},
                {"slot": "", "token": "empty", "harness": "claude",
                 "model": "opus", "role": "", "note": ""},
                {"slot": None, "token": "none", "harness": "opencode",
                 "model": "", "role": "", "note": ""},
            ],
        }
        with mock.patch.object(fleet, "db_state", return_value=state):
            result = fleet.roster()

        self.assertEqual(result, {
            "S1": ("a41f0c", "claude", ""),
            "S10": ("b10b10", "codex", ""),
        })
        self.assertTrue(all(key == "" for _, _, key in result.values()))

    def test_roster_markdown_fallback_and_empty_table(self):
        table = self._write_aimem(
            "with_table.md",
            "| S9 | `abc123` | claude | opus | 역할 | 세션키자리 |\n",
        )
        no_table = self._write_aimem(
            "no_table.md",
            "# AIMEM\n\n## 2. 명부\n\n(DB 로 이관 - `.aimem/aimem.db`)\n",
        )

        with mock.patch.object(fleet, "db_state", return_value=None):
            with mock.patch.object(fleet, "AIMEM", table):
                self.assertEqual(
                    fleet.roster(), {"S9": ("abc123", "claude", "역할")}
                )
            with mock.patch.object(fleet, "AIMEM", no_table):
                self.assertEqual(fleet.roster(), {})

    def test_read_rev_db_path_coerces_string(self):
        with mock.patch.object(fleet, "db_state", return_value={"rev": "114"}):
            rev = fleet.read_rev()
        self.assertEqual(rev, 114)
        self.assertIsInstance(rev, int)

    def test_read_rev_markdown_fallback(self):
        aimem = self._write_aimem(
            "rev.md",
            "# AIMEM\n\n- **REV: 77** (개정 번호)\n",
        )
        with mock.patch.object(fleet, "db_state", return_value=None):
            with mock.patch.object(fleet, "AIMEM", aimem):
                self.assertEqual(fleet.read_rev(), 77)

    def test_read_rev_missing_both_sources_exits(self):
        missing = self.tmp / "missing.md"
        with mock.patch.object(fleet, "db_state", return_value=None):
            with mock.patch.object(fleet, "AIMEM", missing):
                with self.assertRaises(SystemExit):
                    fleet.read_rev()

    def test_owned_paths_for_slot(self):
        state = {
            "ownership": [
                {"path_pattern": "tests/x.py", "owner": "S2", "note": ""},
                {"path_pattern": "src/<슬롯>/y.py", "owner": "해당 슬롯", "note": ""},
                {"path_pattern": "tests/other.py", "owner": "S1", "note": ""},
                {"path_pattern": "docs/<슬롯>.md", "owner": "해당 슬롯", "note": ""},
                {"path_pattern": "tools/z.py", "owner": "S3", "note": ""},
            ],
        }
        with mock.patch.object(fleet, "db_state", return_value=state):
            paths = fleet.owned_paths("S2")

        self.assertEqual(paths, ["tests/x.py", "src/S2/y.py", "docs/S2.md"])

    def test_board_rows_from_db_normalizes_none(self):
        state = {
            "tasks": [
                {"id": "T-001", "title": "제목", "slot": "S1",
                 "status": "TODO", "artifacts": ""},
                {"id": "T-002", "title": None, "slot": None,
                 "status": "DONE", "artifacts": ""},
            ],
        }
        with mock.patch.object(fleet, "db_state", return_value=state):
            rows = fleet.board_rows()

        self.assertEqual(rows, [
            ("T-001", "제목", "S1", "TODO"),
            ("T-002", "", "-", "DONE"),
        ])

    def test_path_allowed_boundaries(self):
        exact = "tests/test_aimem_lint.py"
        self.assertIsNone(fleet.path_allowed(exact + ".bak", [exact]))
        self.assertEqual(fleet.path_allowed(exact, [exact]), exact)
        self.assertEqual(
            fleet.path_allowed(".aimem/archive/x.md", [".aimem/archive/**"]),
            ".aimem/archive/**",
        )

    def test_db_state_cache_ttl(self):
        cached = {"rev": 9, "slots": [{"slot": "S9"}], "tasks": []}
        fresh = {"rev": 10, "slots": [{"slot": "S10"}], "tasks": []}
        now = 100.0

        with mock.patch.object(fleet.time, "monotonic", return_value=now):
            fleet._DB_CACHE.update(at=now, state=cached)
            with mock.patch.object(aimem_db, "state_dict", return_value=fresh) as read:
                self.assertIs(fleet.db_state(), cached)
                read.assert_not_called()

        with mock.patch.object(
            fleet.time, "monotonic", return_value=now + fleet.DB_CACHE_TTL_SEC + 1.0
        ):
            with mock.patch.object(aimem_db, "state_dict", return_value=fresh) as read:
                result = fleet.db_state()
                self.assertIs(result, fresh)
                self.assertIsNot(result, cached)
                read.assert_called_once()

    def test_db_state_does_not_cache_failure(self):
        now = 100.0
        fresh = {"rev": 120, "slots": [], "tasks": []}

        # state=None 은 TTL 이 아직 남았어도 캐시로 쓰지 않고 다시 읽는다.
        fleet._DB_CACHE.update(at=now, state=None)
        with mock.patch.object(fleet.time, "monotonic", return_value=now):
            with mock.patch.object(aimem_db, "state_dict", return_value=fresh) as read:
                self.assertIs(fleet.db_state(), fresh)
                read.assert_called_once()

        # 읽기가 예외를 던지면 조용히 삼키지 않고 stderr 에 원인을 찍고 None 을 준다.
        fleet._DB_CACHE.update(at=now, state=None)
        stderr = io.StringIO()
        with mock.patch.object(fleet.time, "monotonic", return_value=now):
            with mock.patch.object(
                aimem_db, "state_dict", side_effect=RuntimeError("boom")
            ):
                with contextlib.redirect_stderr(stderr):
                    result = fleet.db_state()

        self.assertIsNone(result)
        self.assertIn("[fleet] .aimem/aimem.db 를 읽지 못했습니다", stderr.getvalue())
        self.assertIn("RuntimeError: boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
