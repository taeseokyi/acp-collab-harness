# -*- coding: utf-8 -*-
"""tools/aimem_lint.py 테스트. 표준 라이브러리 unittest 만 사용."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from aimem_lint import ADMIN_OWNER_LITERALS, lint_file, lint_text, main

VALID_DOC = """# AIMEM.md - 공유 작업 메모리

- **REV: 1** (개정 번호)
- 최종 갱신: 2026-08-25

---

## 2. 세션 명부

| 슬롯 | 확인토큰 |
| ---- | -------- |
| S1   | `abc123` |
| S2   | `def456` |

---

## 3. 작업 보드

| ID   | 태스크 | 담당 슬롯 | 상태 | 이어받음 |
| ---- | ------ | --------- | ---- | -------- |
| T-1  | 작업 A | S1        | DONE | -        |
| T-2  | 작업 B | S2        | TODO | T-1      |

---

## 6. 파일 소유권

| 경로 패턴  | 쓰기 소유 |
| ---------- | --------- |
| `src/a.py` | S1        |
| (그 외)    | 미배정    |
"""


def codes(violations):
    return sorted(v.code for v in violations)


class TestValidDoc(unittest.TestCase):
    def test_valid_fixture_has_no_violations(self):
        self.assertEqual(lint_text(VALID_DOC), [])

    def test_real_aimem_md_has_no_violations(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "AIMEM.md")
        vs = lint_file(path)
        self.assertEqual(vs, [], "실제 AIMEM.md 에서 위반 발생: %s" % [str(v) for v in vs])


class TestRevViolations(unittest.TestCase):
    def test_rev_missing(self):
        text = VALID_DOC.replace("- **REV: 1** (개정 번호)\n", "")
        self.assertEqual(codes(lint_text(text)), ["REV_MISSING"])

    def test_rev_multiple(self):
        text = VALID_DOC.replace("## 2.", "- **REV: 2**\n\n## 2.")
        self.assertEqual(codes(lint_text(text)), ["REV_MULTIPLE"])

    def test_rev_invalid_zero(self):
        text = VALID_DOC.replace("**REV: 1**", "**REV: 0**")
        self.assertEqual(codes(lint_text(text)), ["REV_INVALID"])


class TestRosterViolations(unittest.TestCase):
    def test_roster_section_missing(self):
        idx = VALID_DOC.index("## 2. 세션 명부")
        end = VALID_DOC.index("---", idx)
        text = VALID_DOC[:idx] + VALID_DOC[end:]
        self.assertIn("ROSTER_SECTION_MISSING", codes(lint_text(text)))

    def test_roster_duplicate_slot(self):
        extra = "| S1   | `aaa111` |\n"
        anchor = "| S1   | `abc123` |\n"
        text = VALID_DOC.replace(anchor, anchor + extra)
        self.assertIn("ROSTER_DUPLICATE_SLOT", codes(lint_text(text)))

    def test_roster_token_invalid(self):
        text = VALID_DOC.replace("`abc123`", "`zzzzzz`")
        self.assertEqual(codes(lint_text(text)), ["ROSTER_TOKEN_INVALID"])

    def test_roster_duplicate_token(self):
        text = VALID_DOC.replace("`def456`", "`abc123`")
        self.assertEqual(codes(lint_text(text)), ["ROSTER_DUPLICATE_TOKEN"])

    def test_roster_table_missing(self):
        # 절 내부(다음 '## ' 전)의 표 행만 제거
        lines = VALID_DOC.splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("## 2."))
        end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
        out = [l for i, l in enumerate(lines) if not (start < i < end and l.strip().startswith("|"))]
        text = "\n".join(out) + "\n"
        self.assertIn("ROSTER_TABLE_MISSING", codes(lint_text(text)))


class TestBoardViolations(unittest.TestCase):
    def test_board_invalid_status(self):
        text = VALID_DOC.replace("| S1        | DONE |", "| S1        | FINISHED |")
        self.assertEqual(codes(lint_text(text)), ["BOARD_INVALID_STATUS"])

    def test_board_unknown_slot(self):
        text = VALID_DOC.replace("| T-1  | 작업 A | S1        |", "| T-1  | 작업 A | S9        |")
        self.assertEqual(codes(lint_text(text)), ["BOARD_UNKNOWN_SLOT"])

    def test_board_handoff_unknown_task(self):
        text = VALID_DOC.replace("| TODO | T-1      |", "| TODO | T-99     |")
        self.assertEqual(codes(lint_text(text)), ["BOARD_HANDOFF_UNKNOWN_TASK"])

    def test_board_duplicate_task_id(self):
        text = VALID_DOC.replace("| T-2  | 작업 B |", "| T-1  | 작업 B |")
        self.assertEqual(codes(lint_text(text)), ["BOARD_DUPLICATE_TASK_ID"])


class TestOwnershipViolations(unittest.TestCase):
    def test_ownership_duplicate_path(self):
        text = VALID_DOC.replace(
            "| (그 외)    | 미배정    |",
            "| `src/a.py` | 관리자    |",
        )
        self.assertIn("OWNERSHIP_DUPLICATE_PATH", codes(lint_text(text)))

    def test_ownership_invalid_owner(self):
        text = VALID_DOC.replace("| `src/a.py` | S1        |", "| `src/a.py` | 누군가    |")
        self.assertEqual(codes(lint_text(text)), ["OWNERSHIP_INVALID_OWNER"])

    def test_admin_owner_literals_accepted(self):
        for owner in ADMIN_OWNER_LITERALS | {"관리자"} | {"S1", "S2"}:
            text = VALID_DOC.replace("| `src/a.py` | S1        |", "| `src/x_%s.py` | %s      |" % (owner, owner))
            self.assertEqual(lint_text(text), [], "소유자 %r 을 거부해서는 안 됨" % owner)


class TestMainExitCodes(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aimem_lint_test_")

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write(self, name, text):
        path = os.path.join(self._tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_exit_0_on_clean_file(self):
        path = self._write("good.md", VALID_DOC)
        self.assertEqual(main([path]), 0)

    def test_exit_1_on_violations(self):
        path = self._write("bad.md", VALID_DOC.replace("**REV: 1**", "**REV: 0**"))
        self.assertEqual(main([path]), 1)

    def test_exit_2_on_wrong_args(self):
        self.assertEqual(main([]), 2)
        self.assertEqual(main(["a", "b"]), 2)

    def test_exit_1_on_missing_file(self):
        self.assertEqual(main([os.path.join(self._tmpdir, "nope.md")]), 1)


if __name__ == "__main__":
    unittest.main()
