# -*- coding: utf-8 -*-
"""tools/aimem_lint.py 테스트. 표준 라이브러리 unittest 만 사용."""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import aimem_board
from aimem_lint import (
    ADMIN_OWNER_LITERALS,
    MANAGER_SESSION_KEY,
    MAX_HANDOFF_ENTRIES,
    MAX_TOTAL_LINES,
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
# 근거·함정은 `.aimem/outbox/S1.md` [T-021] 인계 노트. 각 검사마다 위반/정상 양쪽을
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


if __name__ == "__main__":
    unittest.main()
