# -*- coding: utf-8 -*-
"""tools/aimem_lint.py 테스트. 표준 라이브러리 unittest 만 사용."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from aimem_lint import (
    ADMIN_OWNER_LITERALS,
    MAX_HANDOFF_ENTRIES,
    MAX_TOTAL_LINES,
    lint_file,
    lint_text,
    main,
)

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


class TestSizeConstantsMatchSpec(unittest.TestCase):
    """`5절`이 정한 상한값(총 800줄 / 핸드오프 12건)과 린터 상수가 일치하는지 못박는다.
    상수를 5절과 다르게 바꾸면 여기서 걸린다 - 문서와 코드가 갈라지는 것을 막는 가드."""

    def test_total_lines_limit_is_800(self):
        self.assertEqual(MAX_TOTAL_LINES, 800)

    def test_handoff_entries_limit_is_12(self):
        self.assertEqual(MAX_HANDOFF_ENTRIES, 12)


class TestSizeTotalLines(unittest.TestCase):
    """총 줄수 상한(800). 경계 800/801 을 정확히 덮는다."""

    def _doc_with_total_lines(self, target):
        base = VALID_DOC if VALID_DOC.endswith("\n") else VALID_DOC + "\n"
        n = len(base.splitlines())
        self.assertLessEqual(n, target, "패딩 대상 줄수가 기준 문서보다 작음")
        doc = base + ("\n" * (target - n))
        # 픽스처 자체의 off-by-one 을 막는 자기검증 - 실제 줄수가 목표와 같아야 한다
        self.assertEqual(len(doc.splitlines()), target)
        return doc

    def test_exactly_800_lines_passes(self):
        self.assertEqual(lint_text(self._doc_with_total_lines(800)), [])

    def test_801_lines_violates(self):
        self.assertEqual(
            codes(lint_text(self._doc_with_total_lines(801))), ["SIZE_TOTAL_LINES"]
        )


class TestSizeHandoffLog(unittest.TestCase):
    """`4. 핸드오프 로그` 항목 수 상한(12). 경계 12/13 을 덮고,
    `4.5 대기 큐`·`9절 승인 이력`의 날짜꼴 줄이 잘못 포함되지 않는지 확인한다."""

    def _handoff_section(self, count):
        entries = "\n".join(
            "- `2026-08-%02d 10:00` 관리자: 항목 %d" % ((i % 28) + 1, i)
            for i in range(count)
        )
        body = (entries + "\n\n") if entries else ""
        return "## 4. 핸드오프 로그\n\n" + body + "---\n\n"

    def _doc(self, count, trailing=""):
        # §4 를 §3 과 §6 사이에 끼운다. trailing 은 문서 끝(§6 뒤)에 붙인다.
        doc = VALID_DOC.replace(
            "## 6. 파일 소유권",
            self._handoff_section(count) + "## 6. 파일 소유권",
        )
        return doc + trailing

    def test_exactly_12_entries_passes(self):
        self.assertEqual(lint_text(self._doc(12)), [])

    def test_13_entries_violates(self):
        self.assertEqual(codes(lint_text(self._doc(13))), ["SIZE_HANDOFF_LOG"])

    def test_queue_and_approval_dates_not_counted(self):
        # §4 는 정확히 12건(통과선)으로 둔다. §4.5 대기 큐와 9절 승인 이력에
        # 날짜꼴(`- \`YYYY-MM-DD ...`) 줄을 여럿 두어도, `_find_section(4)` 경계가
        # `## 4.5` 에서 끝나므로 이들은 항목 수에 포함되면 안 된다. 포함됐다면
        # 12+3+3 = 18 > 12 로 SIZE_HANDOFF_LOG 가 잘못 떴을 것이다.
        queue = (
            "## 4.5 대기 큐\n\n"
            "- `2026-09-01 09:00` 대기 A\n"
            "- `2026-09-02 09:00` 대기 B\n"
            "- `2026-09-03 09:00` 대기 C\n\n"
            "---\n\n"
        )
        approvals = (
            "\n## 9. 승인 대기\n\n"
            "**승인 이력**\n\n"
            "- `2026-08-25 15:19` 태석님: 승인 A\n"
            "- `2026-08-26 15:19` 태석님: 승인 B\n"
            "- `2026-08-27 15:19` 태석님: 승인 C\n"
        )
        doc = VALID_DOC.replace(
            "## 6. 파일 소유권",
            self._handoff_section(12) + queue + "## 6. 파일 소유권",
        ) + approvals
        cds = codes(lint_text(doc))
        self.assertNotIn("SIZE_HANDOFF_LOG", cds)
        # 경계가 옳다면 이 문서는 완전히 깨끗하다 (다른 위반도 없어야 함)
        self.assertEqual(cds, [])


class TestBoardHandoffInvariants(unittest.TestCase):
    """T-016 이 추가한 핸드오프 불변식 두 개(`BOARD_HANDOFF_SELF`,
    `BOARD_HANDOFF_NOT_DONE`)를 덮는다. 정상 케이스와 위반 케이스 양쪽,
    그리고 S1 아웃박스([T-016])가 함정으로 지목한 네 가지 경계를 눌러 본다.

    VALID_DOC 의 보드는 `T-1(DONE, -)` ← `T-2(TODO, T-1)` 이라 두 새 코드
    어디에도 걸리지 않는다(핸드온 기준선). 아래 픽스처는 이 두 행만 치환한다."""

    # VALID_DOC 보드의 두 데이터 행(정확한 문자열 - 문서 내 유일).
    ROW_T1 = "| T-1  | 작업 A | S1        | DONE | -        |"
    ROW_T2 = "| T-2  | 작업 B | S2        | TODO | T-1      |"

    def test_self_reference_flagged(self):
        # 이어받음 이 자기 ID 를 가리키면 SELF. ID 는 유일해야 실제로 뜬다
        # (중복이면 억제됨 - test_self_suppressed_on_duplicate_id 참조).
        text = VALID_DOC.replace(
            self.ROW_T2, "| T-2  | 작업 B | S2        | TODO | T-2      |"
        )
        self.assertEqual(codes(lint_text(text)), ["BOARD_HANDOFF_SELF"])

    def test_done_handoff_to_incomplete_predecessor_flagged(self):
        # 후행이 DONE 인데 그 이어받음 선행(보드에 존재)이 DONE 이 아니면 NOT_DONE.
        text = VALID_DOC.replace(
            self.ROW_T1, "| T-1  | 작업 A | S1        | TODO | -        |"
        ).replace(
            self.ROW_T2, "| T-2  | 작업 B | S2        | DONE | T-1      |"
        )
        vs = lint_text(text)
        self.assertEqual(codes(vs), ["BOARD_HANDOFF_NOT_DONE"])
        # 아웃박스가 명시한 메시지 형식: 선행의 실제 상태를 `(상태: X)` 로 넣는다.
        nd = next(v for v in vs if v.code == "BOARD_HANDOFF_NOT_DONE")
        self.assertIn("(상태: TODO)", nd.message)

    def test_done_handoff_to_done_predecessor_is_clean(self):
        # 정상: DONE 후행이 DONE 선행을 이어받는 것은 허용(위반 0).
        text = VALID_DOC.replace(
            self.ROW_T2, "| T-2  | 작업 B | S2        | DONE | T-1      |"
        )
        self.assertEqual(lint_text(text), [])

    def test_incomplete_chain_when_successor_not_done_is_clean(self):
        # 함정 1: 후행이 DONE 이 아니면 NOT_DONE 안 뜬다. 진행 중 체인
        # (TODO 후행이 미완료 선행을 이어받음)은 정상.
        text = VALID_DOC.replace(
            self.ROW_T1, "| T-1  | 작업 A | S1        | TODO | -        |"
        )
        self.assertEqual(lint_text(text), [])

    def test_done_handoff_to_unknown_predecessor_is_unknown_only(self):
        # 함정 2: 선행이 보드에 없으면 UNKNOWN 만. NOT_DONE 은 평가하지 않는다
        # ("선행이 존재하는데 미완료"인 경우만 NOT_DONE).
        text = VALID_DOC.replace(
            self.ROW_T2, "| T-2  | 작업 B | S2        | DONE | T-99     |"
        )
        self.assertEqual(codes(lint_text(text)), ["BOARD_HANDOFF_UNKNOWN_TASK"])

    def test_self_suppressed_on_duplicate_id(self):
        # 함정 3: 자기 ID 가 중복이면 그 행의 SELF 는 일부러 생략되고,
        # 근본 결함인 DUPLICATE 만 뜬다(파생 위반 억제). 중복을 고쳐 재실행하면
        # 남은 SELF 가 드러난다.
        text = VALID_DOC.replace(
            self.ROW_T2, "| T-1  | 작업 B | S2        | TODO | T-1      |"
        )
        self.assertEqual(codes(lint_text(text)), ["BOARD_DUPLICATE_TASK_ID"])


if __name__ == "__main__":
    unittest.main()
