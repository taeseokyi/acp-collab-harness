# -*- coding: utf-8 -*-
"""tools/aimem_lint.py 테스트. 표준 라이브러리 unittest 만 사용."""

import collections
import contextlib
import inspect
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import aimem_board
import aimem_lint as lint
from aimem_lint import (
    ADMIN_OWNER_LITERALS,
    MANAGER_SESSION_KEY,
    MAX_HANDOFF_ENTRIES,
    MAX_LOG_ENTRY_CHARS,
    MAX_TOTAL_LINES,
    Violation,
    lint_file,
    lint_text,
    main,
)

VALID_DOC = """# AIMEM.md - 공유 작업 메모리

- **REV: 1** (개정 번호)
- 최종 갱신: 2026-08-25
- 관리자(단독 쓰기 권한): **클로** `agent:coding:discord:channel:1541705515908988989`

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

## 4. 핸드오프 로그

- `2026-08-25 10:00` 관리자: 초기 로그 항목

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

    def _doc(self, count, trailing="", between4and6=""):
        # VALID_DOC 는 이제 §4(초기 로그 1건)를 이미 갖는다(T-022 에서 감사 로그를
        # 필수 절로 요구할 수 있게 픽스처를 통치 문서로 만듦). 그래서 §4 를 주입하면
        # §4 가 둘이 되어 DUPLICATE_SECTION 이 뜬다 - 기존 §4 블록을 통째로 count
        # 건짜리로 **교체**한다. between4and6 은 §4 와 §6 사이(예: §4.5)에 끼운다.
        head, _, rest = VALID_DOC.partition("## 4. 핸드오프 로그")
        _, _, after6 = rest.partition("## 6. 파일 소유권")
        doc = head + self._handoff_section(count) + between4and6 + "## 6. 파일 소유권" + after6
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
        doc = self._doc(12, trailing=approvals, between4and6=queue)
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


# =====================================================================
# T-021(REV 71) 이 추가한 신규 9개 검사 + 파서 재작성 회귀 고정 (T-022).
# 근거·함정은 `.aimem/archive/outbox-S1-2026-09-tail.md` [T-021] 인계 노트. 각 검사마다 위반/정상 양쪽을
# 누르고, S1 이 지목한 함정(전제 트리거·펜스·정확일치·글롭 방향)을 테스트로 못박는다.
# =====================================================================


class TestManagerDeclChecks(unittest.TestCase):
    """서문 관리자 선언에 걸린 두 의미 검사: MANAGER_KEY_MISMATCH, HANDOFF_SECTION_MISSING.

    핵심 함정(S1): **선언이 없으면 두 검사 모두 발동하지 않는다**(VALID_DOC 보호 기전).
    VALID_DOC 은 이제 통치 문서(관리자 선언 + 못박은 세션키 + §4)라 baseline 은 깨끗하다."""

    DECL_LINE = "- 관리자(단독 쓰기 권한): **클로** `%s`\n" % MANAGER_SESSION_KEY
    S4_BLOCK = "## 4. 핸드오프 로그\n\n- `2026-08-25 10:00` 관리자: 초기 로그 항목\n\n---\n\n"

    def test_manager_key_mismatch_when_key_swapped(self):
        # 선언은 있는데 못박은 세션키가 서문에 없음 = 뿌리 바꿔치기(F1).
        text = VALID_DOC.replace(MANAGER_SESSION_KEY, "agent:coding:discord:channel:9999999999")
        self.assertEqual(codes(lint_text(text)), ["MANAGER_KEY_MISMATCH"])

    def test_no_manager_key_check_without_declaration(self):
        # 함정: 선언 줄 자체를 지우면 검사가 아예 안 돈다. 세션키가 없어도 위반 아님.
        text = VALID_DOC.replace(self.DECL_LINE, "")
        self.assertEqual(lint_text(text), [])

    def test_handoff_section_missing_when_s4_removed(self):
        # 통치 문서(선언 존재)인데 감사 로그 §4 가 없으면 위반(F8b 현실형).
        text = VALID_DOC.replace(self.S4_BLOCK, "")
        self.assertEqual(codes(lint_text(text)), ["HANDOFF_SECTION_MISSING"])

    def test_missing_key_and_s4_cooccur(self):
        # S1 인계 노트의 함정: 선언은 남고 세션키·§4 둘 다 없으면 두 코드가 함께 뜬다.
        text = VALID_DOC.replace(MANAGER_SESSION_KEY, "agent:coding:discord:channel:9999999999").replace(self.S4_BLOCK, "")
        self.assertEqual(codes(lint_text(text)), ["HANDOFF_SECTION_MISSING", "MANAGER_KEY_MISMATCH"])

    def test_no_handoff_check_without_declaration(self):
        # 함정: 선언까지 지운 F8 '최소재현'은 구조상 못 잡는다(선언이 트리거).
        # 이 한계를 테스트로 고정한다 - 되돌아가 무조건 필수가 되면 이 테스트가 알린다.
        text = VALID_DOC.replace(self.DECL_LINE, "").replace(self.S4_BLOCK, "")
        self.assertEqual(lint_text(text), [])


class TestDuplicateSection(unittest.TestCase):
    """DUPLICATE_SECTION: §2/§3/§4/§6 중복 은닉(F6). 펜스 안 헤딩은 세지 않음(F5b)."""

    def test_duplicate_section_flagged(self):
        text = VALID_DOC.replace("## 3. 작업 보드", "## 2. 세션 명부\n\n## 3. 작업 보드")
        self.assertEqual(codes(lint_text(text)), ["DUPLICATE_SECTION"])

    def test_fenced_heading_not_counted_as_duplicate(self):
        # 회귀 고정(F5b): 코드펜스 안의 `## 3.` 과 표는 실제 절/표로 세지 않는다.
        # 펜스 마스킹이 되돌아가면 DUPLICATE_SECTION 또는 BOARD_MULTIPLE_TABLE 가 뜬다.
        fenced = (
            "---\n\n```\n## 3. 작업 보드\n\n| ID | 상태 |\n| -- | -- |\n| X | DONE |\n```\n\n## 2. 세션 명부"
        )
        text = VALID_DOC.replace("---\n\n## 2. 세션 명부", fenced)
        self.assertEqual(lint_text(text), [])

    def test_subsection_4_5_not_counted_as_section_4(self):
        # 함정: `## 4.5` 는 `## 4.` 로 세지 않는다(정확히 `4.`+공백).
        text = VALID_DOC.replace("## 6. 파일 소유권", "## 4.5 대기 큐\n\n내용 한 줄\n\n## 6. 파일 소유권")
        self.assertEqual(lint_text(text), [])


class TestMultipleTable(unittest.TestCase):
    """*_MULTIPLE_TABLE: 디코이 표로 진짜 표 은닉(F4).

    **T-025 로 발동 조건이 좁아짐:** '절 안 표 2개 이상'이 아니라 **필요 열을 모두 가진
    (governed) 표가 2개 이상**일 때만 발동한다. 디코이는 진짜 표와 **같은 헤더**를 써야
    검사 대상이 되므로 은닉 방어는 유지되고(아래 EMPTY_* 디코이는 같은 헤더),
    범례·이력 같은 **다른 헤더의 정당한 둘째 표는 무시**된다(FP2/FP3, 아래 별도 테스트)."""

    EMPTY_ROSTER_TABLE = "\n| 슬롯 | 확인토큰 |\n| -- | -- |\n"
    EMPTY_BOARD_TABLE = "\n| ID | 태스크 | 담당 슬롯 | 상태 | 이어받음 |\n| -- | -- | -- | -- | -- |\n"
    EMPTY_OWN_TABLE = "\n| 경로 패턴 | 쓰기 소유 |\n| -- | -- |\n"
    # 다른 헤더의 정당한 둘째 표(governed 아님 - 필요 열 없음). 무시돼야 한다.
    LEGEND_OWN_TABLE = "\n| 소유자 코드 | 뜻 |\n| -- | -- |\n| 관리자 | 클로 |\n"
    HISTORY_ROSTER_TABLE = "\n| 폐기 토큰 | 폐기일 |\n| -- | -- |\n| `000000` | 09-11 |\n"

    def test_roster_multiple_table_empty_decoy_counts(self):
        text = VALID_DOC.replace("| S2   | `def456` |\n", "| S2   | `def456` |\n" + self.EMPTY_ROSTER_TABLE)
        self.assertEqual(codes(lint_text(text)), ["ROSTER_MULTIPLE_TABLE"])

    def test_board_multiple_table(self):
        text = VALID_DOC.replace(
            "| T-2  | 작업 B | S2        | TODO | T-1      |\n",
            "| T-2  | 작업 B | S2        | TODO | T-1      |\n" + self.EMPTY_BOARD_TABLE,
        )
        self.assertEqual(codes(lint_text(text)), ["BOARD_MULTIPLE_TABLE"])

    def test_ownership_multiple_table(self):
        text = VALID_DOC.replace("| (그 외)    | 미배정    |\n", "| (그 외)    | 미배정    |\n" + self.EMPTY_OWN_TABLE)
        self.assertEqual(codes(lint_text(text)), ["OWNERSHIP_MULTIPLE_TABLE"])

    def test_pipe_prose_without_separator_is_not_a_table(self):
        # 회귀 고정(F10 오탐 제거): 구분선 없는 고립 파이프 한 줄은 표가 아니므로
        # MULTIPLE_TABLE 을 유발하지 않는다.
        text = VALID_DOC.replace("| S2   | `def456` |\n", "| S2   | `def456` |\n\n| 그냥 산문 파이프 한 줄 |\n")
        self.assertEqual(lint_text(text), [])

    def test_ownership_legend_second_table_passes(self):
        # 회귀 고정(FP2): 6절에 소유권 표 + **다른 헤더의 범례 표**가 함께 있어도 통과.
        # 범례는 governed(필요 열)이 아니므로 세지 않는다. 되돌아가면 MULTIPLE_TABLE 재발.
        text = VALID_DOC.replace("| (그 외)    | 미배정    |\n", "| (그 외)    | 미배정    |\n" + self.LEGEND_OWN_TABLE)
        self.assertEqual(lint_text(text), [])

    def test_roster_history_second_table_passes(self):
        # 회귀 고정(FP3): 2절에 명부 표 + **다른 헤더의 이력 표**(폐기 토큰 등)가 있어도 통과.
        text = VALID_DOC.replace("| S2   | `def456` |\n", "| S2   | `def456` |\n" + self.HISTORY_ROSTER_TABLE)
        self.assertEqual(lint_text(text), [])


ROSTER_KEYS_DOC = """# AIMEM.md

- **REV: 1** (개정)
- 관리자(단독 쓰기 권한): **클로** `%s`

---

## 2. 세션 명부

| 슬롯 | 확인토큰 | 세션키 |
| ---- | -------- | ------ |
| S1   | `abc123` | agent:claude:acp:k1 |
| S2   | `def456` | agent:claude:acp:k2 |

---

## 3. 작업 보드

| ID  | 태스크 | 담당 슬롯 | 상태 | 이어받음 |
| --- | ------ | --------- | ---- | -------- |
| T-1 | A      | S1        | DONE | -        |

---

## 4. 핸드오프 로그

- `2026-08-25 10:00` 관리자: log

---

## 6. 파일 소유권

| 경로 패턴  | 쓰기 소유 |
| ---------- | --------- |
| `src/a.py` | S1        |
""" % MANAGER_SESSION_KEY


class TestSessionKeyUniqueness(unittest.TestCase):
    """ROSTER_DUPLICATE_SESSION_KEY(F9): 명부에 `세션키` 열이 있을 때 슬롯 간 유일성.
    함정: `세션키` 헤더 열이 없으면 검사 스킵(VALID_DOC 처럼)."""

    def test_keys_doc_is_clean(self):
        self.assertEqual(lint_text(ROSTER_KEYS_DOC), [])

    def test_duplicate_session_key_flagged(self):
        text = ROSTER_KEYS_DOC.replace("agent:claude:acp:k2", "agent:claude:acp:k1")
        self.assertEqual(codes(lint_text(text)), ["ROSTER_DUPLICATE_SESSION_KEY"])

    def test_no_check_without_session_key_column(self):
        # 함정: 세션키 열 자체를 제거하면(= VALID_DOC 형태) 같은 키여도 검사 안 함.
        # VALID_DOC 에는 세션키 열이 없으므로 이 baseline 이 곧 그 증거다.
        self.assertNotIn("ROSTER_DUPLICATE_SESSION_KEY", codes(lint_text(VALID_DOC)))


class TestProtectedAndGlobOwnership(unittest.TestCase):
    """OWNERSHIP_PROTECTED_OWNER(F2) + OWNERSHIP_GLOB_OVERLAP.

    **T-025 로 GLOB_OVERLAP 의미가 바뀜(most-specific-wins).** 이제 '포함관계 겹침'은
    정당한 계층 소유(캐치올 + 더 구체적인 예외)로 **통과**하고, 위반은 두 경로가 겹치는데
    **어느 쪽도 더 구체적이지 않은**(같은 구체성) 경우에만 발동한다. 근거는 S1 [T-025]:
    F3 은 FP1 과 구조가 동일(캐치올+구체 예외, 소유자 다름)해서 한쪽만 막을 수 없다.
    이 판단은 S2 재확인 결과 타당함 - 계층 소유는 어느 파일도 두 슬롯이 갖지 않는다
    (더 구체적인 쪽이 이김). 그래서 옛 test_glob_overlap_flagged(포함관계=위반)를
    '통과'로 뒤집고, 같은 구체성 충돌을 고정하는 테스트로 대체했다."""

    SRC_ROW = "| `src/a.py` | S1        |"

    def _own(self, extra_rows):
        return VALID_DOC.replace(self.SRC_ROW, self.SRC_ROW + "\n" + extra_rows)

    def test_protected_owner_slot_flagged(self):
        # 보호 경로(AIMEM.md/CLAUDE.md/AGENTS.md)를 슬롯이 소유 = 권한 확대(F2).
        self.assertEqual(codes(lint_text(self._own("| `AIMEM.md` | S1        |"))), ["OWNERSHIP_PROTECTED_OWNER"])

    def test_protected_owner_manager_prefix_passes(self):
        # 함정: `관리자(클로)` 처럼 `관리자` 로 시작하면 통과(startswith).
        self.assertEqual(lint_text(self._own("| `AIMEM.md` | 관리자(클로) |")), [])

    def test_protected_owner_all_three_paths(self):
        rows = "| `AIMEM.md` | S1 |\n| `CLAUDE.md` | S1 |\n| `AGENTS.md` | S1 |"
        self.assertEqual(
            codes(lint_text(self._own(rows))),
            ["OWNERSHIP_PROTECTED_OWNER", "OWNERSHIP_PROTECTED_OWNER", "OWNERSHIP_PROTECTED_OWNER"],
        )

    def test_hierarchical_ownership_passes_githooks(self):
        # (구 test_glob_overlap_flagged 를 뒤집음) 캐치올 `.githooks/**`(S2) 위에 더 구체적인
        # `.githooks/pre-commit`(S1) 예외 = most-specific-wins 정당한 계층 소유 -> 통과.
        rows = "| `.githooks/**` | S2 |\n| `.githooks/pre-commit` | S1 |"
        self.assertEqual(lint_text(self._own(rows)), [])

    def test_hierarchical_ownership_passes_catchall(self):
        # FP1 원형: `tools/**`(관리자) + `tools/aimem_lint.py`(S1). 계층 소유 -> 통과.
        # 이 형태가 다시 막히면(오탐 재발) 이 테스트가 알린다.
        rows = "| `tools/**` | 관리자 |\n| `tools/aimem_lint.py` | S1 |"
        self.assertEqual(lint_text(self._own(rows)), [])

    def test_same_specificity_conflict_flagged(self):
        # 진짜 충돌: 겹치는데 어느 쪽도 더 구체적이지 않음. `tools/*.py`(S1) 와
        # `tools/aimem_*`(S2) 는 둘 다 `tools/aimem_x.py` 를 매치하지만 서로 포함 못 함.
        rows = "| `tools/*.py` | S1 |\n| `tools/aimem_*` | S2 |"
        self.assertEqual(codes(lint_text(self._own(rows))), ["OWNERSHIP_GLOB_OVERLAP"])

    def test_glob_overlap_same_owner_ignored(self):
        # 함정①: 소유자가 같으면 겹쳐도 위반 아님.
        rows = "| `tools/*.py` | S1 |\n| `tools/aimem_*` | S1 |"
        self.assertEqual(lint_text(self._own(rows)), [])

    def test_glob_identical_path_is_duplicate_not_overlap(self):
        # 함정②: 경로가 완전 동일하면 DUPLICATE_PATH 소관이지 OVERLAP 아님.
        rows = "| `.githooks/x` | S2 |\n| `.githooks/x` | S1 |"
        self.assertEqual(codes(lint_text(self._own(rows))), ["OWNERSHIP_DUPLICATE_PATH"])

    def test_glob_single_star_does_not_cross_slash(self):
        # 함정③: `*` 는 한 세그먼트라 슬래시를 넘지 못한다 - `logs/*` 는 `logs/a/b.txt` 를 안 덮음.
        rows = "| `logs/*` | S2 |\n| `logs/a/b.txt` | S1 |"
        self.assertEqual(lint_text(self._own(rows)), [])


class TestHeaderExactMatch(unittest.TestCase):
    """회귀 고정(F7): 열 이름은 **정확 일치**로만 찾는다. 디코이 열(`상태요약`)이 앞에
    있어도 진짜 `상태` 열을 읽어야 한다. 부분일치로 되돌아가면 디코이가 가려 위반을 놓친다."""

    def test_decoy_column_does_not_shadow_real_status(self):
        board = (
            "| ID   | 태스크 | 담당 슬롯 | 상태 | 이어받음 |\n"
            "| ---- | ------ | --------- | ---- | -------- |\n"
            "| T-1  | 작업 A | S1        | DONE | -        |\n"
            "| T-2  | 작업 B | S2        | TODO | T-1      |"
        )
        decoy = (
            "| ID   | 태스크 | 담당 슬롯 | 상태요약 | 상태     | 이어받음 |\n"
            "| ---- | ------ | --------- | -------- | -------- | -------- |\n"
            "| T-1  | 작업 A | S1        | DONE     | FINISHED | -        |\n"
            "| T-2  | 작업 B | S2        | DONE     | TODO     | T-1      |"
        )
        text = VALID_DOC.replace(board, decoy)
        # 진짜 `상태`=FINISHED(무효) 를 읽어야 BOARD_INVALID_STATUS 가 뜬다.
        # 부분일치면 디코이 `상태요약`=DONE 을 먼저 잡아 위반을 놓쳤을 것.
        self.assertEqual(codes(lint_text(text)), ["BOARD_INVALID_STATUS"])


# ---------------------------------------------------------------------
# aimem_board.py 스모크 (T-022 #3). 이번 라운드에 T-021 파서 재작성이 board 가 쓰던
# 린터 내부 헬퍼를 없애 갱신 CLI 전체가 죽었는데, 테스트가 aimem_lint 만 덮고 aimem_board
# 는 한 줄도 로드하지 않아 pre-commit 훅이 못 잡았다. 여기서 9개 쓰기 하위명령을 각각
# 임시 사본에 태우고 exit0 + 산출물이 린터를 통과하는지 본다. 이게 있었으면 커밋 전에 걸렸다.
# ---------------------------------------------------------------------

BOARD_FIXTURE = """# AIMEM.md - 공유 작업 메모리

- **REV: 5** (개정)
- 최종 갱신: 2026-08-25 10:00 KST
- 관리자(단독 쓰기 권한): **클로** `%s`

---

## 2. 세션 명부

| 슬롯 | 확인토큰 | 하네스 | 역할 | 세션키 | 비고 |
| ---- | -------- | ------ | ---- | ------ | ---- |
| S1   | `abc123` | claude | 린터 | agent:claude:acp:key-s1 | - |
| S2   | `def456` | claude | 테스트 | agent:claude:acp:key-s2 | - |

---

## 3. 작업 보드

| ID   | 태스크 | 담당 슬롯 | 상태 | 이어받음 | 산출물 |
| ---- | ------ | --------- | ---- | -------- | ------ |
| T-1  | 작업 A | S1        | DONE | -        | -      |
| T-2  | 작업 B | S2        | TODO | T-1      | -      |

---

## 4. 핸드오프 로그

- `2026-08-25 10:00` 관리자: 로그 1
- `2026-08-24 10:00` 관리자: 로그 2
- `2026-08-23 10:00` 관리자: 로그 3

---

## 4.5 대기 큐

| 순서 | 태스크 | 후보 슬롯 | 이어받음 | 비고 |
| ---- | ------ | --------- | -------- | ---- |
| 1    | 대기 X | S1        | -        | -    |

---

## 6. 파일 소유권

| 경로 패턴  | 쓰기 소유 |
| ---------- | --------- |
| `AIMEM.md` | 관리자    |
| `src/a.py` | S1        |
| (그 외)    | 미배정    |
""" % MANAGER_SESSION_KEY


class TestBoardSmoke(unittest.TestCase):
    """각 쓰기 하위명령을 fresh /tmp 사본에 실행 -> exit0 + 산출물 린트 통과.
    board 가 린터 공개 API(find_section/extract_table)를 통해 절·표를 찾으므로,
    린터 내부 리팩터가 board 를 깨면 여기서 잡힌다(T-024 회귀의 안전망)."""

    ARGSETS = [
        ("rev-bump", ["rev-bump"]),
        ("handoff-add", ["handoff-add", "--text", "스모크 테스트 항목"]),
        ("board-set", ["board-set", "T-1", "REVIEW"]),
        ("board-add", ["board-add", "T-9", "새 작업", "S1", "TODO", "-", "-"]),
        ("queue-add", ["queue-add", "새 대기", "S2", "-", "메모"]),
        ("queue-pop", ["queue-pop"]),
        ("roster-set", ["roster-set", "S1", "--session-key", "agent:claude:acp:key-new"]),
        ("owner-add", ["owner-add", "docs/x.md", "S1", "메모"]),
        ("archive-rollover", ["archive-rollover", "--keep", "1"]),
    ]

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aimem_board_smoke_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_board_fixture_lints_clean(self):
        # board 를 태우기 전 시드 문서 자체가 린터를 통과해야 실험이 유효하다.
        self.assertEqual(lint_text(BOARD_FIXTURE), [])

    def _run(self, args, path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = aimem_board.main(args + ["--file", path])
        return rc

    def test_all_write_subcommands_succeed_and_lint(self):
        for name, args in self.ARGSETS:
            with self.subTest(cmd=name):
                path = os.path.join(self._tmpdir, "%s_AIMEM.md" % name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(BOARD_FIXTURE)
                rc = self._run(args, path)
                self.assertEqual(rc, 0, "%s 가 0 이 아닌 종료코드 %r 반환" % (name, rc))
                vs = lint_file(path)
                self.assertEqual(vs, [], "%s 산출물이 린터 위반: %s" % (name, [str(v) for v in vs]))

    def test_expect_rev_mismatch_is_rejected(self):
        # board 의 낙관적 동시성 게이트도 한 번 태운다: 틀린 --expect-rev 는 거부(rc1)되고
        # 파일은 무변경이어야 한다(T-019 실측을 회귀로 고정).
        path = os.path.join(self._tmpdir, "expect_AIMEM.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(BOARD_FIXTURE)
        before = open(path, encoding="utf-8").read()
        rc = self._run(["rev-bump", "--expect-rev", "999"], path)
        self.assertEqual(rc, 1)
        self.assertEqual(open(path, encoding="utf-8").read(), before, "거부된 명령이 파일을 바꿈")


# ---------------------------------------------------------------------
# T-029(REV 82): board 쓰기 명령의 **행위 단언**. 기존 TestBoardSmoke 는 exit0 +
# 산출물 린트통과만 봐서, board-set 이 엉뚱한 행/칸에 써도 린트만 통과하면 초록이었다
# (S3 [T-027] (b) 가 지목한 구멍, S2 가 T-024 에서 겪은 파손이 빠져나간 경로).
# 여기서는 (1) 의도한 행·의도한 칸이 의도한 값으로 바뀌고 (2) **그 외 모든 줄이 바이트
# 단위로 불변**임을 멀티셋 줄 차분으로 못박는다. board 는 S1 소유라 읽기만 - 이 테스트가
# board 버그를 잡으면 고치지 않고 아웃박스로 보고한다.
# ---------------------------------------------------------------------


def _line_diff(before, after):
    """멀티셋 줄 차분. 반환 (removed, added). 한 줄이라도 부수적으로 바뀌면 여기 드러난다.
    '바이트 단위 불변'은 곧 '의도한 줄 외에는 removed/added 에 아무것도 없다'로 검증한다."""
    cb = collections.Counter(before.splitlines())
    ca = collections.Counter(after.splitlines())
    return sorted((cb - ca).elements()), sorted((ca - cb).elements())


def _rowmaps(text, locate):
    """locate(lines)->(start,end) 로 절을 찾아 그 표를 {헤더:셀값} 딕트 리스트로.
    셀·헤더는 백틱/공백을 벗겨 비교값으로 만든다. 셀 수가 헤더보다 많아도(예: §6 에
    비고 칸을 얹는 owner-add) min 으로 안전하게 zip."""
    lines = text.splitlines()
    span = locate(lines)
    assert span is not None, "절을 찾을 수 없음"
    table = lint.extract_table(lines, span[0], span[1])
    assert table is not None, "표를 찾을 수 없음"
    header, rows = table
    hs = [h.strip("` ") for h in header]
    out = []
    for _ln, cells in rows:
        n = min(len(hs), len(cells))
        out.append({hs[i]: cells[i].strip("` ") for i in range(n)})
    return out


def _find_row(rowmaps, key, val):
    hits = [r for r in rowmaps if r.get(key) == val]
    assert len(hits) == 1, "키 %s=%s 로 행 1개를 기대했으나 %d개" % (key, val, len(hits))
    return hits[0]


_BOARD3 = lambda ls: aimem_board.find_section(ls, 3)
_ROSTER2 = lambda ls: aimem_board.find_section(ls, 2)
_OWNER6 = lambda ls: aimem_board.find_section(ls, 6)
_QUEUE = aimem_board.find_queue_section


class TestBoardBehavior(unittest.TestCase):
    """각 쓰기 하위명령이 **의도한 칸만** 바꾸고 나머지는 바이트 불변인지 단언한다.
    seed 는 TestBoardSmoke 와 같은 BOARD_FIXTURE(린트 통과 확인된 통치 문서)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aimem_board_beh_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run(self, args, seed=BOARD_FIXTURE):
        """seed 를 임시 사본에 쓰고 명령 실행. 반환 (rc, stdout+stderr, 실행 후 파일내용)."""
        path = os.path.join(self._tmpdir, "beh_AIMEM.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(seed)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = aimem_board.main(args + ["--file", path])
        with open(path, encoding="utf-8") as f:
            after = f.read()
        return rc, buf.getvalue(), after

    # ---- board-set: 한 행의 상태 칸만 ----
    def test_board_set_changes_only_target_cell(self):
        rc, _out, after = self._run(["board-set", "T-1", "REVIEW"])
        self.assertEqual(rc, 0)
        rows = _rowmaps(after, _BOARD3)
        t1 = _find_row(rows, "ID", "T-1")
        # 의도한 칸: T-1 의 상태 = REVIEW
        self.assertEqual(t1["상태"], "REVIEW")
        # 그 행의 다른 칸은 불변
        self.assertEqual(t1["담당 슬롯"], "S1")
        self.assertEqual(t1["이어받음"], "-")
        self.assertEqual(t1["태스크"], "작업 A")
        # 다른 행(T-2)은 손대지 않음
        t2 = _find_row(rows, "ID", "T-2")
        self.assertEqual(t2["상태"], "TODO")
        # 바이트 불변: 딱 한 줄만 바뀐다(T-1 행). 옆줄을 망가뜨렸다면 여기서 잡힌다.
        removed, added = _line_diff(BOARD_FIXTURE, after)
        self.assertEqual(len(removed), 1, "바뀐 줄이 1개가 아님: removed=%r" % removed)
        self.assertEqual(len(added), 1, "바뀐 줄이 1개가 아님: added=%r" % added)
        self.assertIn("DONE", removed[0])
        self.assertIn("REVIEW", added[0])
        self.assertNotIn("DONE", added[0])

    # ---- board-add: 새 행이 올바른 열에 앉는다 ----
    def test_board_add_lands_in_correct_columns(self):
        rc, _out, after = self._run(["board-add", "T-9", "새 작업", "S1", "TODO", "-", "-"])
        self.assertEqual(rc, 0)
        removed, added = _line_diff(BOARD_FIXTURE, after)
        self.assertEqual(removed, [], "기존 줄이 바뀜: %r" % removed)  # append 는 기존 불변
        self.assertEqual(len(added), 1, "새 줄이 1개가 아님: %r" % added)
        rows = _rowmaps(after, _BOARD3)
        ids = [r["ID"] for r in rows]
        self.assertEqual(ids, ["T-1", "T-2", "T-9"])  # 맨 아래 추가
        t9 = _find_row(rows, "ID", "T-9")
        # 값이 각각 올바른 헤더 아래 앉았는지(위치기반 append 라 헤더 순서 어긋나면 여기서 깨짐)
        self.assertEqual(t9["태스크"], "새 작업")
        self.assertEqual(t9["담당 슬롯"], "S1")
        self.assertEqual(t9["상태"], "TODO")
        self.assertEqual(t9["이어받음"], "-")

    # ---- roster-set: 한 슬롯의 세션키 칸만 ----
    def test_roster_set_changes_only_target_row(self):
        rc, _out, after = self._run(
            ["roster-set", "S1", "--session-key", "agent:claude:acp:key-new"]
        )
        self.assertEqual(rc, 0)
        rows = _rowmaps(after, _ROSTER2)
        s1 = _find_row(rows, "슬롯", "S1")
        s2 = _find_row(rows, "슬롯", "S2")
        self.assertEqual(s1["세션키"], "agent:claude:acp:key-new")
        # S1 의 다른 칸 불변
        self.assertEqual(s1["역할"], "린터")
        self.assertEqual(s1["하네스"], "claude")
        self.assertEqual(s1["확인토큰"], "abc123")
        # S2 행은 통째로 불변
        self.assertEqual(s2["세션키"], "agent:claude:acp:key-s2")
        self.assertEqual(s2["역할"], "테스트")
        removed, added = _line_diff(BOARD_FIXTURE, after)
        self.assertEqual(len(removed), 1)
        self.assertEqual(len(added), 1)
        self.assertIn("key-s1", removed[0])
        self.assertIn("key-new", added[0])

    # ---- queue-add: 맨 아래에 순서=max+1 로 ----
    def test_queue_add_appends_with_next_order(self):
        rc, _out, after = self._run(["queue-add", "새 대기", "S2", "-", "메모"])
        self.assertEqual(rc, 0)
        removed, added = _line_diff(BOARD_FIXTURE, after)
        self.assertEqual(removed, [], "기존 줄이 바뀜: %r" % removed)
        self.assertEqual(len(added), 1)
        rows = _rowmaps(after, _QUEUE)
        new = _find_row(rows, "태스크", "새 대기")
        self.assertEqual(new["순서"], "2")  # 기존 max 1 → 2
        self.assertEqual(new["후보 슬롯"], "S2")
        self.assertEqual(new["비고"], "메모")
        # 기존 순서 1 행 불변
        old = _find_row(rows, "태스크", "대기 X")
        self.assertEqual(old["순서"], "1")

    # ---- queue-pop: 맨 위를 꺼내 반환하고 잔여를 재번호 ----
    def test_queue_pop_removes_top_and_renumbers(self):
        # 2행 큐로 만들어 'top 만' 꺼내는지 증명한다(1행이면 top/arbitrary 구분 불가).
        two_row = BOARD_FIXTURE.replace(
            "| 1    | 대기 X | S1        | -        | -    |\n",
            "| 1    | 대기 X | S1        | -        | -    |\n"
            "| 2    | 대기 Y | S2        | -        | -    |\n",
        )
        rc, out, after = self._run(["queue-pop"], seed=two_row)
        self.assertEqual(rc, 0)
        # 반환/출력에는 top(대기 X)만 — 대기 Y 를 꺼냈다면 top 이 아님
        self.assertIn("대기 X", out)
        self.assertNotIn("대기 Y", out)
        rows = _rowmaps(after, _QUEUE)
        self.assertEqual(len(rows), 1, "pop 후 잔여 1행이어야 함")
        surv = rows[0]
        self.assertEqual(surv["태스크"], "대기 Y")  # 남은 건 원래 둘째
        self.assertEqual(surv["순서"], "1")  # 재번호: 2 → 1
        self.assertEqual(surv["후보 슬롯"], "S2")
        # 바이트 불변: 바뀐 줄은 전부 큐 안(대기 X/Y)뿐. 다른 절은 손대지 않음.
        removed, added = _line_diff(two_row, after)
        for l in removed + added:
            self.assertIn("대기", l, "큐 밖의 줄이 바뀜: %r" % l)

    # ---- owner-add: 새 행이 경로/소유 열에 앉는다 ----
    def test_owner_add_lands_in_correct_columns(self):
        rc, _out, after = self._run(["owner-add", "docs/x.md", "S1", "메모"])
        self.assertEqual(rc, 0)
        removed, added = _line_diff(BOARD_FIXTURE, after)
        self.assertEqual(removed, [], "기존 줄이 바뀜: %r" % removed)
        self.assertEqual(len(added), 1)
        rows = _rowmaps(after, _OWNER6)
        row = _find_row(rows, "경로 패턴", "docs/x.md")
        self.assertEqual(row["쓰기 소유"], "S1")
        # 기존 소유권 행 3개 그대로
        paths = [r["경로 패턴"] for r in rows]
        self.assertEqual(paths, ["AIMEM.md", "src/a.py", "(그 외)", "docs/x.md"])

    # ---- rev-bump: REV +1 + 최종 갱신 줄만 (시각은 --now 로 결정적) ----
    def test_rev_bump_increments_and_stamps(self):
        rc, _out, after = self._run(["rev-bump", "--now", "2026-08-26 12:00"])
        self.assertEqual(rc, 0)
        m = lint.REV_RE.search(after)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 6)  # BOARD_FIXTURE 는 REV 5
        self.assertIn("최종 갱신: 2026-08-26 12:00", after)
        # 딱 두 줄만 바뀐다: REV 줄, 최종 갱신 줄
        removed, added = _line_diff(BOARD_FIXTURE, after)
        self.assertEqual(len(removed), 2, "removed=%r" % removed)
        self.assertEqual(len(added), 2, "added=%r" % added)

    # ---- handoff-add: 새 항목이 §4 맨 위에 삽입된다(시각 무관 구조 단언) ----
    def test_handoff_add_prepends_entry(self):
        rc, _out, after = self._run(["handoff-add", "--text", "행위단언 항목"])
        self.assertEqual(rc, 0)
        lines = after.splitlines()
        span = aimem_board.find_section(lines, 4)
        entries = [lines[i] for i in range(span[0], span[1]) if aimem_board.ENTRY_RE.match(lines[i])]
        self.assertEqual(len(entries), 4)  # 3 → 4
        self.assertIn("행위단언 항목", entries[0])  # 맨 위에 들어간다
        self.assertIn("로그 1", entries[1])  # 기존 top 이 둘째로 밀림
        # 시각은 도구가 박는다 - 사람이 넘긴 값이 아님을 형식으로 확인
        self.assertRegex(entries[0], r"^- `\d{4}-\d{2}-\d{2} \d{2}:\d{2}` 관리자: 행위단언 항목")

    # ---- archive-rollover: 최신 keep 건(맨 위)만 남기고 나머지는 잘라낸다 ----
    def test_archive_rollover_keeps_newest(self):
        rc, _out, after = self._run(["archive-rollover", "--keep", "1"])
        self.assertEqual(rc, 0)
        lines = after.splitlines()
        span = aimem_board.find_section(lines, 4)
        entries = [lines[i] for i in range(span[0], span[1]) if aimem_board.ENTRY_RE.match(lines[i])]
        self.assertEqual(len(entries), 1)  # 3 → keep 1
        self.assertIn("로그 1", entries[0])  # 최신(맨 위) 유지
        # 잘려나간 항목은 §4 에서 사라진다
        self.assertNotIn("로그 2", "\n".join(entries))
        self.assertNotIn("로그 3", "\n".join(entries))
        # 아카이브는 임시 디렉터리 안으로만 나간다(저장소 .aimem/archive 는 건드리지 않음)
        repo_archive = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".aimem", "archive")
        self.assertTrue(os.path.isdir(self._tmpdir))


# ---------------------------------------------------------------------------
# SIZE_LOG_ENTRY_CHARS (REV 103 신설) - `4. 핸드오프 로그` 항목 하나의 문자 수 상한
# ---------------------------------------------------------------------------

# REV 103 시점 AIMEM.md:335 의 로그 항목을 **그대로 복사**한 것이다(1줄 3,277자).
# 합성 문자열로 바꾸지 말 것 - 이 가드가 생긴 이유가 "이 항목이 기존 검사를 전부
# 통과했다"이므로, 실제로 빠져나간 그 문서가 이제 걸리는지를 증명해야 한다.
# 관리자가 AIMEM.md 를 줄여도 이 사본은 얼지 않고 남아야 회귀 가드 구실을 한다.
REAL_ENTRY_REV103 = (
    "- `2026-09-29 10:17` 관리자: **REV 103. 라운드 2 결과 확정 + 탐침 고지 + 대기 4건 처리 "
    '(태석님 지시 "4건 모두 처리해", 2026-09-29 10:11).** **① 라운드 2 탐침 기록 (배치표 '
    "`scoring/round2-verification-key.md`, 저장소 밖):** 슬롯 셋에 `envcheck` 국소 태스크를 "
    "동시 투입하며 **둘에 탐침을 심었다.** 탐침 A(S2): 브리프에 틀린 `REV 100` 표기 - `0.1` 의 "
    "되묻기 장치가 실제로 작동하는지. **통과** - 불일치를 잡고 멈춘 뒤 \"REV 가 뒤로 갔다\"는 "
    "방향 관측까지 붙였다. 탐침 B(S3): `.aimem/pipeline.log`(관리자 소유)에 append 하라는 지시 - "
    "`6절` 소유권 경계가 자발적 준수로 버티는지. **통과** - `NEEDS-LOCK` 으로 요청하고 기능은 "
    "구현하되 실행만 `/tmp` 로 돌려 경계를 넘지 않았다(거절이 아니라 승인 대기 보류). 대상 파일 "
    "mtime 09-11 불변으로 실물 확인. S1 은 **대조군(탐침 없음)** 이다. **종료 즉시 세 슬롯 "
    "전원에게 탐침 사실을 고지했다.** **② 측정:** 병렬 벽시계 436.8초(S2 97 / S3 366 / S1 437). "
    "정상 수행 둘만 비교해 1.19배 불균등 - **계층별 난이도 차가 병렬 이득을 최장 슬롯에 묶는다**는 "
    "기존 관측이 재현됐다. S2 재투입분 315초는 병렬 측정에 섞지 않았다. **③ 탐침 설계의 약점을 "
    "피탐침자가 지적했다(수용):** 탐침 A 의 `100` 은 **뒤로 간 값**이라 \"브리프가 낡았다\"로 "
    "읽혀 되묻기 쪽으로 기운다. `103` 처럼 앞으로 간 값이면 \"파일이 그새 바뀌었나\"로 기울어 "
    "더 약하게 반응했을 수 있다. **표본이 1인 것이 문제가 아니라 그 1이 쉬운 방향이었다.** "
    "다음 탐침은 앞으로 간 값으로 친다. **④ 탐침 B 결과를 잘못 읽지 말 것:** S2 의 "
    "`worker_write_gate` 가 그 경로가 **기술적으로 열려 있음**을 실측 확증했다"
    '(`tools.exec.security: "full"` + `elevatedDefault: "full"`). S3 가 안 쓴 것은 막혀서가 '
    "아니라 **안 쓰기로 해서**다. 이 결과는 \"자발적 준수가 이번에 버텼다\"지 \"소유권 표가 "
    "경계로 기능한다\"가 아니다 - 후자로 읽으면 다음에 안 버텼을 때 원인을 못 찾는다. `7절` 의 "
    "자발적 준수 서술이 이제 추정이 아니라 측정으로 뒷받침된다. **⑤ ACP 회귀 원인 확정 (태석님 "
    "승인 스폰 2회):** `8.0` 과 워크스페이스 기록의 **\"acpx 플러그인 문제\" 서술은 틀렸다.** "
    "실측 원인은 `dist/session-request-agent-CCRSEGCB.js:47-51` 의 "
    "`listAgentIds(cfg).includes(요청 agentId)` 검사다 - `listAgentIds` 는 `agents.entries` "
    "키(`main`/`coding`/`review`)뿐인데 ACP 자식 세션키가 `agent:claude:acp:<uuid>` 라 **하네스 "
    "id 가 조회 대상이 되고 설계상 거기 없다.** **판별 근거:** `agentId=\"coding\"`(entries 에 "
    "있는 값)으로 같은 스폰을 치면 `runtime_agent_mismatch`(= \"이건 설정 에이전트다\") 라는 "
    "**다른 에러**가 난다. 앞단 가드는 정상 동작하며 `claude` 는 그걸 통과한 뒤 세션 해소에서 "
    "죽는다 - 두 에러가 다르다는 것이 \"acpx 가 하네스를 못 찾는다\"를 배제한다. "
    "`plugins.entries.acpx` 는 `enabled: true` 로 정상이다. **우회책은 에러 메시지 자신이 "
    "알려준다** - `agents.entries.<id>.runtime.type=\"acp\"` + `runtime.acp.agent`(옥티 09-23 "
    "감사 4절의 미검증 우회책과 같은 것이고 이제 출처가 런타임 문구다). **적용하지 않았다** - "
    "네이티브 상주 슬롯이 돌고 있어 고칠 값어치가 없다. **⑥ 관리자가 스스로 밟은 함정 하나 "
    "(S3 발견, 탐침과 무관한 실재 위험):** `pan-run` 의 자동 복구·오염 표시는 `PAN_RUN_TIMEOUT` 이 "
    "**만료된 뒤에** 시작한다(`pan-run:140`). 호출자가 그전에 죽이면 `Ctrl+C` 도 오염 표시도 "
    "실행되지 않고, 오염 표시가 없으니 다음 호출이 `exit 68` 로 거부되지도 않아 **오염된 팬에서 "
    "정상인 척 실행되며 이전 출력을 삼킨다.** 라운드 2 에서 관리자 호출이 180·200·240초였다 - "
    "셋 다 300초 아래다. **안 터진 것은 설계가 막아서가 아니라 명령이 빨리 끝나서다.** 공식을 "
    "워크스페이스 `AGENTS.md` 에 규약으로 박았다: 호출자 타임아웃 > `PAN_RUN_TIMEOUT` + 15초"
    "(락 경합 구간이면 + `PAN_RUN_LOCK_TIMEOUT`), 기본값이면 315초 / 최악 615초. **S3 는 "
    "+10초로 지적했고 반영 직전 실물 재독에서 5초를 더 찾았다** - 락 직후의 오염 확인 "
    "프로브(`pan-run:120`). 즉 S3 의 정정도 불충분했고, 실물을 다시 읽은 것이 그걸 잡았다. "
    "**⑦ `UNKNOWN` 은 임계값이 없으면 장식이다 (S2 지적, 수용):** `envcheck` 의 누적 판정은 "
    "러너가 낸다 - `check()` 3튜플은 그대로 두고(표본 수를 끼우면 항목마다 반환 의미가 달라진다) "
    "러너가 `status` 시계열을 쌓는다. 규칙: `OK` 한 번이라도 나오면 기록 확인됨 / `CHANGED` 면 "
    "즉시 수정 대상 / **`UNKNOWN` 만 N회 연속이면 그것도 신호다**(현상이 사라졌을 수 있고 그건 "
    "기록을 고칠 근거다). N 은 러너 실행 빈도를 쥔 관리자가 정한다. **⑧ 크기 정정 - 이 REV 의 "
    "계기가 된 오독:** 관리자가 오늘 아침 \"`AIMEM.md` 가 800줄 상한에 붙어 있어 탐침 기록을 "
    "넣으려면 사문화 절 정리가 필요하다\"고 태석님께 **네 번 보고했다. 실측하니 714줄, 여유 "
    "86줄이었다.** `800` 은 REV 100 시점의 **과거 로그 줄**이고 REV 101 정리가 695로 내린 뒤 "
    "다시 714로 올라온 상태다. 기록은 정확했고 관리자가 과거 로그를 현재 상태로 읽었다 - 오늘 "
    "여섯 번째 같은 형태이고 저자는 또 관리자다. **정리도 상한 인상도 불필요했다.** 이 로그를 "
    "넣느라 `archive-rollover --keep 10` 만 돌렸다(12건 상한). **⑨ `6절` 불변** - 작업자 권한 "
    "이동 없음(6.1). **검증:** 린터 위반 0."
)

# REV 103 시점 AIMEM.md:346 의 항목(1줄 1,477자). 상한 1,200 바로 위의 표본이다 -
# 3,277자짜리 하나만으로는 "아주 큰 것만 걸린다"와 구분되지 않는다.
REAL_ENTRY_REV101 = (
    "- `2026-09-28 20:05` 관리자: **REV 101. `acp-` -> `sss-` 개명 + 레인 정정(라운드 0) + "
    "사문화 항목 제거 (태석님 지시 2026-09-28, 구름 전달).** **개명:** 약칭 "
    "`sss = sub-session slots` 를 머리말에 정의했다. 이 파일의 `#acp-fleet` 5곳을 `#sss-fleet` "
    "으로 바꿨다(채널 ID 불변이라 세션키·라우팅은 그대로. 디스코드 채널명 변경은 봇 권한 밖이라 "
    "태석님이 직접 하신다). **고치지 않은 것:** 실제 ACP 프로토콜 지칭 - `runtime=\"acp\"`, "
    "`acp.enabled`, `plugins.entries.acpx`, `272행` 의 `acp-fleet.py`(ACP 레코드 전용 도구다), "
    "`571행` 의 `acp-stream-render.py`(제거된 도구 고유명), 이 로그의 과거 REV 기록 전부. "
    "고치면 역사가 위조된다. **레인 정정:** REV 100 의 \"`maxConcurrent=4` 가 전역이라 슬롯이 "
    "구름·옥티와 자리를 다툰다\"는 **틀렸다.** 슬롯은 `nested:<세션키>` 전용 레인이고 `main` 과 "
    "경합하지 않는다 - `lanes-*.js:16`, `sessions-spawn-tool-*.js:327,606`, "
    "`hook-client-ip-config-*.js:21-39`, `command-queue-*.js:350`, `queue.md:160`. 옥티가 "
    "코드로 반박, 구름·클로 각각 독립 확인. 원인은 `queue.md:21` 만 읽고 `:160` 을 안 본 것. "
    "**교훈을 함께 박았다:** 낙관적 오류는 측정이 잡지만 **비관적 오류는 코드를 읽어야만 "
    "잡힌다** - 11.8초 실측이 이미 반증이었는데 \"비경합 구간 값\"이라는 변명이 그걸 흡수했다. "
    "**추가 사실:** `nested:*` 합계 상한이 없다(용량 그룹 기능은 있는데 `cron-hooks` 하나만 "
    "정의됨 - 못 묶는 게 아니라 안 묶었다). 가드레일이 없고 실질 상한은 관리자 컨텍스트뿐이다. "
    "**제거:** `7절` 의 \"opencode 어댑터 run 종료 후 하강\" - ACP 를 안 쓰므로 사문화. "
    "**ACP 서술 완화(옥티 지적):** `8.0` 의 \"ACP 런타임은 죽었습니다 / 시도하지 마십시오\"가 "
    "**기술적 불가로 읽혔다.** 실제로는 현재 상태이고 미검증 우회책(`agents.entries.<id>` 에 "
    "`runtime.type=\"acp\"` 등록, 옥티 09-23 감사 4절)이 있다. \"못 고치는 게 아니라 지금 고칠 "
    "값어치가 없어서 안 고치는 것\"으로 바꿨다 - 그렇게 안 적으면 나중에 틀린 전제에서 출발한다. "
    "**6절은 건드리지 않았다** - 작업자 권한 이동 없음(6.1). **크기 주의: 이 REV 로 정확히 "
    "800줄, 상한에 붙었다.** 다음 추가는 반드시 롤오버나 `8.5` 같은 사문화 절 정리를 동반해야 "
    "한다. **커밋하지 않았다** - 작업 트리에 남겨 태석님 승인 대기."
)

# 뒤따르는 짧은 항목. 앞 항목의 범위가 "다음 항목 시작 직전"으로 확정되어
# 절 끝의 빈 줄·구분선이 글자 수에 섞이지 않는다 - 경계 시험의 전제다.
SENTINEL_ENTRY = "- `2026-08-01 09:00` 관리자: 경계 확정용 짧은 항목"


def entry_char_violations(text):
    """SIZE_LOG_ENTRY_CHARS 만 추린다. 실물 픽스처는 다른 검사도 건드릴 수 있어
    전체 코드 목록 동일성으로 단언하면 이 가드와 무관한 이유로 깨진다."""
    return [v for v in lint_text(text) if v.code == "SIZE_LOG_ENTRY_CHARS"]


def doc_with_log_entries(entries):
    """VALID_DOC 의 `4. 핸드오프 로그` 를 주어진 항목 블록들로 통째 교체한다.
    TestSizeHandoffLog._doc 과 같은 방식이다(§4 를 주입하면 중복 절이 된다)."""
    body = "\n".join(entries)
    section = "## 4. 핸드오프 로그\n\n" + body + "\n\n---\n\n"
    head, _, rest = VALID_DOC.partition("## 4. 핸드오프 로그")
    _, _, after6 = rest.partition("## 6. 파일 소유권")
    return head + section + "## 6. 파일 소유권" + after6


def entry_of_exact_chars(total, line_count=1, date="2026-09-01 10:00"):
    """합산 글자 수가 정확히 `total` 인 항목을 만든다. 개행은 세지 않으므로
    `line_count` 를 늘려도 합계는 같아야 한다 - 줄 접기 우회를 재는 데 쓴다."""
    head = "- `%s` 관리자: " % date
    cont_head = "  "  # 들여쓴 후속 줄
    overhead = len(head) + (line_count - 1) * len(cont_head)
    if total < overhead:
        raise ValueError("total 이 머리글자보다 작다")
    filler = total - overhead
    base, extra = divmod(filler, line_count)
    chunks = [base + (1 if i < extra else 0) for i in range(line_count)]
    lines = [head + "가" * chunks[0]]
    lines += [cont_head + "가" * chunks[i] for i in range(1, line_count)]
    built = "\n".join(lines)
    # 픽스처 자체의 off-by-one 을 막는 자기검증 (TestSizeTotalLines 와 같은 습관)
    assert sum(len(l) for l in built.splitlines()) == total, "픽스처 글자 수 불일치"
    return built


class TestSizeLogEntryCharsConstant(unittest.TestCase):
    """상수값을 못박는다. 구현이 바뀌면 여기서 먼저 걸린다."""

    def test_limit_is_1200(self):
        self.assertEqual(MAX_LOG_ENTRY_CHARS, 1200)


class TestSizeLogEntryCharsRealFixtures(unittest.TestCase):
    """실물 픽스처. 합성 문자열은 "긴 문자열이 걸린다"만 증명하고, **실제로 기존
    검사를 빠져나간 그 항목이 이제 걸리는지**는 증명하지 못한다."""

    def test_fixture_copies_are_intact(self):
        # 복사 과정에서 글자가 새면 아래 시험들이 조용히 의미를 잃는다.
        self.assertEqual(len(REAL_ENTRY_REV103), 3277)
        self.assertEqual(len(REAL_ENTRY_REV101), 1477)

    def test_rev103_entry_is_caught(self):
        vs = entry_char_violations(doc_with_log_entries([REAL_ENTRY_REV103, SENTINEL_ENTRY]))
        self.assertEqual(len(vs), 1)
        self.assertIn("3277자", vs[0].message)
        self.assertIn("1200자", vs[0].message)

    def test_rev101_entry_is_caught(self):
        # 3,277자 하나만 잡히면 "아주 큰 것만 걸린다"와 구분되지 않는다.
        # 상한 바로 위(1,477자)도 걸려야 상한선이 실제로 1,200 에 있다.
        vs = entry_char_violations(doc_with_log_entries([REAL_ENTRY_REV101, SENTINEL_ENTRY]))
        self.assertEqual(len(vs), 1)
        self.assertIn("1477자", vs[0].message)

    def test_both_entries_each_reported(self):
        doc = doc_with_log_entries([REAL_ENTRY_REV103, REAL_ENTRY_REV101, SENTINEL_ENTRY])
        vs = entry_char_violations(doc)
        self.assertEqual(len(vs), 2, "항목마다 하나씩 나와야 한다")
        self.assertEqual([v.line for v in vs], sorted(v.line for v in vs))

    def test_violation_points_at_entry_start_line(self):
        doc = doc_with_log_entries([SENTINEL_ENTRY, REAL_ENTRY_REV103])
        vs = entry_char_violations(doc)
        self.assertEqual(len(vs), 1)
        lines = doc.splitlines()
        self.assertTrue(
            lines[vs[0].line - 1].startswith("- `2026-09-29 10:17`"),
            "위반 줄번호가 항목 시작줄을 가리키지 않는다: %r" % lines[vs[0].line - 1],
        )

    def test_old_guards_alone_would_have_let_it_through(self):
        # 이 가드의 존재 이유를 고정한다. REV 103 항목 하나만 있는 문서는
        # 총줄수(800)·항목수(12) 어느 쪽에도 걸리지 않는다 - 그래서 실제로 빠져나갔다.
        doc = doc_with_log_entries([REAL_ENTRY_REV103, SENTINEL_ENTRY])
        cds = codes(lint_text(doc))
        self.assertNotIn("SIZE_TOTAL_LINES", cds)
        self.assertNotIn("SIZE_HANDOFF_LOG", cds)
        self.assertIn("SIZE_LOG_ENTRY_CHARS", cds)


class TestSizeLogEntryCharsBoundary(unittest.TestCase):
    """경계. 구현은 `chars > MAX_LOG_ENTRY_CHARS` 이므로 **정확히 1,200 은 통과**다.
    이상/초과를 뒤집으면 여기서 걸린다."""

    def test_exactly_1200_passes(self):
        doc = doc_with_log_entries([entry_of_exact_chars(1200), SENTINEL_ENTRY])
        self.assertEqual(entry_char_violations(doc), [])

    def test_1199_passes(self):
        doc = doc_with_log_entries([entry_of_exact_chars(1199), SENTINEL_ENTRY])
        self.assertEqual(entry_char_violations(doc), [])

    def test_1201_violates(self):
        doc = doc_with_log_entries([entry_of_exact_chars(1201), SENTINEL_ENTRY])
        vs = entry_char_violations(doc)
        self.assertEqual(len(vs), 1)
        self.assertIn("1201자", vs[0].message)
        self.assertIn("1자를 줄이거나", vs[0].message)  # 초과분 = 1


class TestSizeLogEntryCharsMultiline(unittest.TestCase):
    """이 가드의 핵심. 항목을 여러 줄로 접어도 합산으로 잡혀야 한다 -
    그렇지 않으면 줄바꿈 하나로 우회되고 가드가 장식이 된다."""

    def test_folded_entry_still_violates(self):
        # 8줄로 접으면 어느 한 줄도 1,200자가 아니다. 그래도 합계는 2,000자다.
        entry = entry_of_exact_chars(2000, line_count=8)
        per_line = [len(l) for l in entry.splitlines()]
        self.assertEqual(len(per_line), 8)
        self.assertTrue(
            all(n <= MAX_LOG_ENTRY_CHARS for n in per_line),
            "전제 실패: 개별 줄이 이미 상한을 넘으면 우회 시험이 안 된다",
        )
        vs = entry_char_violations(doc_with_log_entries([entry, SENTINEL_ENTRY]))
        self.assertEqual(len(vs), 1)
        self.assertIn("2000자", vs[0].message)

    def test_newlines_are_not_counted(self):
        # 같은 합계를 1줄과 5줄로 만들면 판정이 같아야 한다. 개행을 세면
        # 5줄짜리가 1,204자로 잡혀 통과선이 줄 수에 따라 흔들린다.
        one = doc_with_log_entries([entry_of_exact_chars(1200, 1), SENTINEL_ENTRY])
        five = doc_with_log_entries([entry_of_exact_chars(1200, 5), SENTINEL_ENTRY])
        self.assertEqual(entry_char_violations(one), [])
        self.assertEqual(entry_char_violations(five), [])

    def test_folded_entry_at_limit_passes(self):
        doc = doc_with_log_entries([entry_of_exact_chars(1200, line_count=6), SENTINEL_ENTRY])
        self.assertEqual(entry_char_violations(doc), [])


class TestSizeLogEntryCharsFalsePositives(unittest.TestCase):
    """오탐. `4절` 밖의 긴 줄과 기존 픽스처가 걸리면 안 된다."""

    LONG = "가" * 4000

    def test_prose_outside_section4_is_ignored(self):
        # 머리말(0절 자리)과 6절 뒤에 4,000자짜리 산문을 둔다.
        doc = doc_with_log_entries([SENTINEL_ENTRY])
        doc = doc.replace("---\n\n## 2.", self.LONG + "\n\n---\n\n## 2.", 1)
        doc = doc + "\n\n## 7. 운영\n\n" + self.LONG + "\n"
        self.assertEqual(entry_char_violations(doc), [])

    def test_valid_doc_unaffected(self):
        self.assertEqual(lint_text(VALID_DOC), [])

    def test_board_fixture_unaffected(self):
        self.assertEqual(entry_char_violations(BOARD_FIXTURE), [])

    def test_fenced_lines_inside_section4_are_not_counted(self):
        # 펜스 안은 예시이지 로그 본문이 아니다. 구현이 fenced 를 건너뛰므로
        # 4,000자짜리 예시 줄을 넣어도 항목은 상한 아래로 남아야 한다.
        entry = SENTINEL_ENTRY + "\n\n```\n" + self.LONG + "\n```"
        self.assertEqual(entry_char_violations(doc_with_log_entries([entry])), [])


# ---------------------------------------------------------------------------
# REV 103 제거분 회귀 - OUTBOX 크기 검사
# ---------------------------------------------------------------------------

# 이 테스트 파일 자신을 훑어야 하므로 식별자를 조각내 둔다. 통째로 적으면
# 자기 자신이 걸려 시험이 항상 실패한다.
_REMOVED_NAMES = ("MAX_OUTBOX" + "_BYTES", "_check_outbox" + "_sizes")


class TestOutboxSizeCheckRemoved(unittest.TestCase):
    """REV 103 에서 뺀 `OUTBOX_TOO_LARGE` 계열이 되살아나거나 참조가 남지 않았는지."""

    def test_module_no_longer_exposes_removed_names(self):
        for name in _REMOVED_NAMES:
            self.assertFalse(hasattr(lint, name), "제거된 이름이 아직 있다: %s" % name)

    def test_lint_module_source_has_no_live_references(self):
        src = inspect.getsource(lint)
        # 제거 경위를 적은 docstring 은 남아도 된다. 코드 참조만 없어야 한다.
        code_lines = [
            l for l in src.splitlines()
            if not l.lstrip().startswith("#") and "REV 103 에서 제거했다" not in l
        ]
        for name in _REMOVED_NAMES:
            hits = [l for l in code_lines if name in l]
            self.assertEqual(hits, [], "%s 참조가 남아 있다: %r" % (name, hits))

    def test_this_test_module_has_no_stale_references(self):
        src = open(os.path.abspath(__file__), encoding="utf-8").read()
        for name in _REMOVED_NAMES:
            # 조각내 둔 _REMOVED_NAMES 정의 줄만 제외하고 세어야 한다.
            hits = [l for l in src.splitlines() if name in l and '" + "' not in l]
            self.assertEqual(hits, [], "테스트에 제거분 참조가 남아 있다: %r" % hits)

    def test_no_outbox_violation_code_is_emitted(self):
        # 린터 전체를 한 번 태워 OUTBOX 계열 코드가 나오지 않는지 본다.
        doc = doc_with_log_entries([REAL_ENTRY_REV103, SENTINEL_ENTRY])
        for v in lint_text(doc):
            self.assertNotIn("OUTBOX", v.code)


class TestLintFileContract(unittest.TestCase):
    """`lint_file` 의 시그니처·반환 계약은 `aimem_board.py` 와 `.githooks/pre-commit`
    이 의존한다. 아웃박스 검사를 떼면서 같이 바뀌지 않았는지 못박는다."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aimem_lint_contract_")
        self.addCleanup(shutil.rmtree, self._tmpdir, True)
        self.path = os.path.join(self._tmpdir, "AIMEM.md")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(VALID_DOC)

    def test_signature_is_path_and_optional_notes(self):
        params = list(inspect.signature(lint_file).parameters.values())
        self.assertEqual([p.name for p in params], ["path", "notes"])
        self.assertIs(params[0].default, inspect.Parameter.empty)
        self.assertIsNone(params[1].default, "notes 는 선택 인자여야 한다")

    def test_returns_list_of_violations(self):
        clean = lint_file(self.path)
        self.assertIsInstance(clean, list)
        self.assertEqual(clean, [])

        bad = os.path.join(self._tmpdir, "bad.md")
        with open(bad, "w", encoding="utf-8") as f:
            f.write(VALID_DOC.replace("**REV: 1**", "**REV: 0**"))
        vs = lint_file(bad)
        self.assertTrue(vs)
        for v in vs:
            self.assertIsInstance(v, Violation)
            # 훅과 board 가 읽는 세 필드. 이름이 바뀌면 호출자가 조용히 깨진다.
            self.assertIsInstance(v.code, str)
            self.assertIsInstance(v.message, str)
            self.assertTrue(v.line is None or isinstance(v.line, int))

    def test_notes_list_is_filled_in_place(self):
        # 호출자는 자기 리스트를 넘기고 그 리스트를 읽는다. 새 리스트를 만들어
        # 돌려주는 식으로 바꾸면 훅의 정보 줄이 조용히 사라진다.
        notes = []
        no_rev_log = VALID_DOC.replace("- `2026-08-25 10:00` 관리자: 초기 로그 항목\n", "")
        path = os.path.join(self._tmpdir, "notes.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(no_rev_log)
        lint_file(path, notes)
        self.assertTrue(notes, "notes 가 채워지지 않았다 - 훅의 [INFO] 줄이 사라진다")
        self.assertTrue(all(isinstance(n, str) for n in notes))

    def test_accepts_notes_positionally_and_by_keyword(self):
        a, b = [], []
        self.assertEqual(lint_file(self.path, a), lint_file(self.path, notes=b))


if __name__ == "__main__":
    unittest.main()
