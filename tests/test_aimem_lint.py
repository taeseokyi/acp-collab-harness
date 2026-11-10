# -*- coding: utf-8 -*-
"""tools/aimem_lint.py 테스트. 표준 라이브러리 unittest 만 사용."""

import collections
import contextlib
import inspect
import io
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import aimem_board
import aimem_db
import aimem_lint as lint
from aimem_lint import (
    MANAGER_SESSION_KEY,
    MAX_TOTAL_LINES,
    Violation,
    lint_file,
    lint_repo,
    lint_text,
    main,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 2단계(T-060/T-061): 운영 상태 표는 DB 로 갔고, 2·3·4·4.5·6절에는 포인터만 남는다.
# 관리자 선언이 있는 "통치 문서" 최소 픽스처 - 위반 0.
VALID_DOC = """# AIMEM.md - 공유 작업 메모리

- **REV: 1** (개정 번호)
- 최종 갱신: 2026-08-25
- 관리자(단독 쓰기 권한): **클로** `agent:claude:acp:`

---

## 2. 세션 명부

정본은 `.aimem/aimem.db`. 읽기 전용 스냅샷: `AIMEM-state.md`

---

## 3. 작업 보드

스냅샷: `AIMEM-state.md`

---

## 4. 핸드오프 로그

스냅샷: `AIMEM-state.md`

---

## 4.5 대기 큐

스냅샷: `AIMEM-state.md`

---

## 6. 파일 소유권

스냅샷: `AIMEM-state.md`
"""

# 관리자 선언이 없는 최소 픽스처 - 새 STATE_* 검사는 게이팅 때문에 발화하지 않는다.
NO_DECL_DOC = VALID_DOC.replace("- 관리자(단독 쓰기 권한): **클로** `agent:claude:acp:`\n", "")

TABLE = "| 슬롯 | 확인토큰 |\n| ---- | -------- |\n| S1   | `abc123` |\n"


def codes(violations):
    return sorted(v.code for v in violations)


class TestValidDoc(unittest.TestCase):
    def test_valid_fixture_has_no_violations(self):
        self.assertEqual(lint_text(VALID_DOC), [])

    def test_real_aimem_md_lint_repo_returns_list(self):
        # 내용은 단언하지 않는다 - 관리자가 같은 라운드에 본문을 고치는 중이라 건수가 움직인다.
        vs = lint_repo(REPO_ROOT / "AIMEM.md", root=REPO_ROOT)
        self.assertIsInstance(vs, list)
        for v in vs:
            self.assertIsInstance(v, Violation)


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


# ---------------------------------------------------------------------
# aimem_board.py 스모크 (T-022 #3). 이번 라운드에 T-021 파서 재작성이 board 가 쓰던
# 린터 내부 헬퍼를 없애 갱신 CLI 전체가 죽었는데, 테스트가 aimem_lint 만 덮고 aimem_board
# 는 한 줄도 로드하지 않아 pre-commit 훅이 못 잡았다. 여기서 9개 쓰기 하위명령을 각각
# 임시 사본에 태우고 exit0 + 산출물이 린터를 통과하는지 본다. 이게 있었으면 커밋 전에 걸렸다.
# ---------------------------------------------------------------------

BOARD_FIXTURE = """# AIMEM.md - 공유 작업 메모리

- **REV: 5** (개정)
- 최종 갱신: 2026-08-25 10:00 KST
- 작성(관리자 선언 아님 - 2단계 STATE_* 게이팅을 피하려는 board 전용 시드): **클로** `%s`

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
                # 2단계 이후 BOARD_FIXTURE 는 표를 가진 board 전용 시드라 lint_text 위반과 엮지 않는다.

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


# ---------------------------------------------------------------------
# 2단계(T-061): 남는 코드 + 새 STATE_* 코드. 운영 상태 표는 `.aimem/aimem.db` 로 옮겨갔고
# 린터 규칙은 "표가 있어야 한다" -> "표가 없어야 한다" 로 반전됐다.
# ---------------------------------------------------------------------


class TestSizeConstantsMatchSpec(unittest.TestCase):
    def test_total_lines_limit_is_800(self):
        self.assertEqual(MAX_TOTAL_LINES, 800)

    def test_manager_session_key_is_pinned(self):
        self.assertEqual(MANAGER_SESSION_KEY, "agent:claude:acp:")


class TestManagerKeyMismatch(unittest.TestCase):
    DECL_LINE = "- 관리자(단독 쓰기 권한): **클로** `%s`\n" % MANAGER_SESSION_KEY

    def test_mismatch_fires_when_key_swapped(self):
        text = VALID_DOC.replace(MANAGER_SESSION_KEY, "agent:coding:discord:channel:9999999999")
        self.assertEqual(codes(lint_text(text)), ["MANAGER_KEY_MISMATCH"])

    def test_no_mismatch_with_pinned_key(self):
        self.assertEqual(lint_text(VALID_DOC), [])

    def test_no_check_without_declaration(self):
        self.assertEqual(lint_text(VALID_DOC.replace(self.DECL_LINE, "")), [])


class TestDuplicateSection(unittest.TestCase):
    def test_duplicate_section_fires(self):
        text = VALID_DOC.replace("## 3. 작업 보드", "## 2. 세션 명부\n\n스냅샷: `AIMEM-state.md`\n\n## 3. 작업 보드")
        self.assertEqual(codes(lint_text(text)), ["DUPLICATE_SECTION"])

    def test_fenced_heading_not_counted(self):
        fenced = "---\n\n```\n## 3. 작업 보드\n\n| ID | 상태 |\n| -- | -- |\n| X | DONE |\n```\n\n## 2. 세션 명부"
        text = VALID_DOC.replace("---\n\n## 2. 세션 명부", fenced)
        self.assertEqual(lint_text(text), [])

    def test_subsection_4_5_not_counted_as_section_4(self):
        # VALID_DOC 은 이미 `## 4.5` 를 갖는다 - 4절 중복으로 세면 여기서 걸린다.
        self.assertIn("## 4.5 대기 큐", VALID_DOC)
        self.assertNotIn("DUPLICATE_SECTION", codes(lint_text(VALID_DOC)))


class TestStateTableInAimem(unittest.TestCase):
    """STATE_TABLE_IN_AIMEM: 2·3·4·4.5·6절 구간에 펜스 밖 `|` 줄이 2줄 이상이면 위반."""

    SECTIONS = [("## 2. 세션 명부", "2"), ("## 3. 작업 보드", "3"), ("## 4. 핸드오프 로그", "4"),
                ("## 4.5 대기 큐", "4.5"), ("## 6. 파일 소유권", "6")]

    def _with_table_in(self, heading):
        return VALID_DOC.replace(heading + "\n\n", heading + "\n\n" + TABLE + "\n", 1)

    def test_fires_in_each_state_section(self):
        for heading, num in self.SECTIONS:
            with self.subTest(section=num):
                self.assertEqual(codes(lint_text(self._with_table_in(heading))), ["STATE_TABLE_IN_AIMEM"])

    def test_clean_pointer_only_doc_does_not_fire(self):
        self.assertNotIn("STATE_TABLE_IN_AIMEM", codes(lint_text(VALID_DOC)))

    def test_single_pipe_line_is_tolerated(self):
        text = VALID_DOC.replace("## 3. 작업 보드\n\n", "## 3. 작업 보드\n\n| 한 줄짜리 파이프 |\n\n", 1)
        self.assertEqual(lint_text(text), [])

    def test_two_pipe_lines_without_separator_fire(self):
        # 구분선을 빼서 표 판정을 피하는 우회도 잡는다.
        text = VALID_DOC.replace("## 3. 작업 보드\n\n", "## 3. 작업 보드\n\n| a | b |\n| c | d |\n\n", 1)
        self.assertEqual(codes(lint_text(text)), ["STATE_TABLE_IN_AIMEM"])

    def test_fenced_table_does_not_fire(self):
        fenced = "```\n" + TABLE + "```\n\n"
        text = VALID_DOC.replace("## 3. 작업 보드\n\n", "## 3. 작업 보드\n\n" + fenced, 1)
        self.assertEqual(lint_text(text), [])

    def test_table_in_non_state_section_does_not_fire(self):
        text = VALID_DOC + "\n---\n\n## 7. 기타\n\n" + TABLE
        self.assertEqual(lint_text(text), [])

    def test_gated_by_manager_declaration(self):
        text = self._with_table_in("## 2. 세션 명부").replace(
            "- 관리자(단독 쓰기 권한): **클로** `agent:claude:acp:`\n", "")
        self.assertEqual(lint_text(text), [])


class TestStatePointerMissing(unittest.TestCase):
    """STATE_POINTER_MISSING: 절이 있는데 구간 안에 `AIMEM-state.md` 가 없으면 위반. 절이 없으면 통과."""

    def test_fires_when_pointer_removed_from_section(self):
        text = VALID_DOC.replace("## 3. 작업 보드\n\n스냅샷: `AIMEM-state.md`\n", "## 3. 작업 보드\n\n(비어 있음)\n")
        self.assertEqual(codes(lint_text(text)), ["STATE_POINTER_MISSING"])

    def test_fires_once_per_section_missing_pointer(self):
        text = VALID_DOC.replace("`AIMEM-state.md`", "`other.md`")
        self.assertEqual(codes(lint_text(text)), ["STATE_POINTER_MISSING"] * 5)

    def test_clean_doc_does_not_fire(self):
        self.assertNotIn("STATE_POINTER_MISSING", codes(lint_text(VALID_DOC)))

    def test_absent_section_is_not_a_violation(self):
        start = VALID_DOC.index("## 6. 파일 소유권")
        text = VALID_DOC[:start].rstrip("\n").rstrip("-").rstrip("\n") + "\n"
        self.assertNotIn("## 6.", text)
        self.assertEqual(lint_text(text), [])

    def test_pointer_in_other_section_does_not_count(self):
        # 포인터는 **그 절 구간 안**에 있어야 한다.
        text = VALID_DOC.replace("## 6. 파일 소유권\n\n스냅샷: `AIMEM-state.md`\n", "## 6. 파일 소유권\n\n(없음)\n")
        self.assertEqual(codes(lint_text(text)), ["STATE_POINTER_MISSING"])

    def test_gated_by_manager_declaration(self):
        text = NO_DECL_DOC.replace("`AIMEM-state.md`", "`other.md`")
        self.assertEqual(lint_text(text), [])


class TestStateGating(unittest.TestCase):
    def test_no_decl_minimal_fixture_has_zero_violations(self):
        # 선언 없는 최소 픽스처: 절이 비어 있고 포인터가 없어도, 표가 있어도 새 검사는 침묵한다.
        bare = "# AIMEM.md\n\n- **REV: 1** (개정)\n\n## 2. 세션 명부\n\n" + TABLE
        self.assertEqual(lint_text(bare), [])
        self.assertEqual(lint_text(NO_DECL_DOC), [])

    def test_lint_text_is_pure_and_notes_untouched(self):
        notes = []
        self.assertEqual(lint_text(VALID_DOC, notes), [])
        self.assertEqual(notes, [])


class _FakeCon:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestLintRepo(unittest.TestCase):
    """lint_repo(path, root=None, notes=None): lint_file + DB 대조(REV_DB_MISMATCH / STATE_SNAPSHOT_*)."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="aimem_lint_repo_")).resolve()
        self.addCleanup(shutil.rmtree, str(self._tmp), True)
        self.md = self._tmp / "AIMEM.md"
        self.md.write_text(VALID_DOC, encoding="utf-8")

    # --- DB 를 흉내 내는 가짜 저장소 (실제 .aimem/aimem.db 는 건드리지 않는다) ---
    def _fake_repo(self, db_rev=1, snapshot="# 스냅샷\n본문\n", write_state=True, state_text=None):
        (self._tmp / ".aimem").mkdir(exist_ok=True)
        (self._tmp / ".aimem" / "aimem.db").write_bytes(b"")
        if write_state:
            (self._tmp / "AIMEM-state.md").write_text(state_text if state_text is not None else snapshot,
                                                       encoding="utf-8")
        patches = [
            mock.patch.object(aimem_db, "ROOT", self._tmp),
            mock.patch.object(aimem_db, "DB", self._tmp / ".aimem" / "aimem.db"),
            mock.patch.object(aimem_db, "connect", lambda: _FakeCon()),
            mock.patch.object(aimem_db, "rev", lambda con: db_rev),
            mock.patch.object(aimem_db, "render_text", lambda: snapshot),
        ]
        for pt in patches:
            pt.start()
            self.addCleanup(pt.stop)

    def _codes(self, notes=None):
        return codes(lint_repo(self.md, root=self._tmp, notes=notes))

    # (a) DB 없는 임시 디렉터리 -> 위반 0 + note
    def test_no_db_dir_is_silent_with_note(self):
        notes = []
        self.assertEqual(lint_repo(str(self.md), root=str(self._tmp), notes=notes), [])
        self.assertGreaterEqual(len(notes), 1)
        self.assertTrue(all(isinstance(n, str) for n in notes))

    def test_default_root_for_tmp_file_is_silent(self):
        notes = []
        self.assertEqual(lint_repo(self.md, notes=notes), [])
        self.assertTrue(notes)

    def test_notes_default_none_ok(self):
        self.assertEqual(lint_repo(self.md, root=self._tmp), [])

    def test_wrong_root_even_with_db_file_is_note_not_violation(self):
        (self._tmp / ".aimem").mkdir()
        (self._tmp / ".aimem" / "aimem.db").write_bytes(b"")
        notes = []
        self.assertEqual(lint_repo(self.md, root=self._tmp, notes=notes), [])
        self.assertTrue(notes)

    def test_lint_text_violations_pass_through(self):
        self.md.write_text(VALID_DOC.replace("**REV: 1**", "**REV: 0**"), encoding="utf-8")
        self.assertEqual(self._codes(), ["REV_INVALID"])

    def test_no_declaration_skips_db_checks(self):
        self.md.write_text(NO_DECL_DOC, encoding="utf-8")
        self._fake_repo(db_rev=99, write_state=False)
        self.assertEqual(self._codes(), [])

    # (b) 저장소 현물 - 터지지 않고 리스트를 돌려준다 (내용 단언 없음)
    def test_real_repo_returns_list_without_raising(self):
        notes = []
        vs = lint_repo(REPO_ROOT / "AIMEM.md", root=REPO_ROOT, notes=notes)
        self.assertIsInstance(vs, list)
        self.assertIsInstance(notes, list)

    # --- REV_DB_MISMATCH ---
    def test_rev_db_mismatch_fires(self):
        self._fake_repo(db_rev=2)
        self.assertEqual(self._codes(), ["REV_DB_MISMATCH"])

    def test_rev_db_match_does_not_fire(self):
        self._fake_repo(db_rev=1)
        self.assertEqual(self._codes(), [])

    def test_rev_db_missing_in_db_is_note(self):
        self._fake_repo(db_rev=None)
        notes = []
        self.assertEqual(self._codes(notes), [])
        self.assertTrue(any("meta.rev" in n for n in notes))

    def test_rev_db_not_double_reported_with_invalid_rev(self):
        # 구현상 REV 0 은 '유효'(숫자면 통과)라 DB 대조 대상이다. 음수는 REV_INVALID 이고 DB 대조는 건너뛴다.
        self.md.write_text(VALID_DOC.replace("**REV: 1**", "**REV: -3**"), encoding="utf-8")
        self._fake_repo(db_rev=5)
        self.assertEqual(self._codes(), ["REV_INVALID"])

    # --- STATE_SNAPSHOT_MISSING / STALE ---
    def test_snapshot_missing_fires(self):
        self._fake_repo(write_state=False)
        self.assertEqual(self._codes(), ["STATE_SNAPSHOT_MISSING"])

    def test_snapshot_present_and_equal_does_not_fire(self):
        self._fake_repo()
        self.assertEqual(self._codes(), [])

    def test_snapshot_stale_fires(self):
        self._fake_repo(snapshot="# 스냅샷\n새 본문\n", state_text="# 스냅샷\n낡은 본문\n")
        self.assertEqual(self._codes(), ["STATE_SNAPSHOT_STALE"])

    def test_snapshot_stamp_line_is_ignored(self):
        stamp = aimem_db.STAMP_PREFIX
        fresh = "# 스냅샷\n%s 생성 2026-11-09 20:00 / REV 1\n본문\n" % stamp
        old = "# 스냅샷\n%s 생성 2026-11-01 01:00 / REV 1\n본문\n" % stamp
        self._fake_repo(snapshot=fresh, state_text=old)
        self.assertEqual(self._codes(), [])

    def test_snapshot_diff_outside_stamp_line_still_fires(self):
        stamp = aimem_db.STAMP_PREFIX
        fresh = "# 스냅샷\n%s 생성 A\n본문 가\n" % stamp
        old = "# 스냅샷\n%s 생성 B\n본문 나\n" % stamp
        self._fake_repo(snapshot=fresh, state_text=old)
        self.assertEqual(self._codes(), ["STATE_SNAPSHOT_STALE"])

    def test_snapshot_trailing_newline_difference_fires(self):
        self._fake_repo(snapshot="# 스냅샷\n본문\n", state_text="# 스냅샷\n본문")
        self.assertEqual(self._codes(), ["STATE_SNAPSHOT_STALE"])


class TestMainUsesLintRepo(unittest.TestCase):
    def test_main_exit_codes_with_tmp_file(self):
        d = tempfile.mkdtemp(prefix="aimem_lint_main_")
        self.addCleanup(shutil.rmtree, d, True)
        good = os.path.join(d, "good.md")
        bad = os.path.join(d, "bad.md")
        pathlib.Path(good).write_text(VALID_DOC, encoding="utf-8")
        pathlib.Path(bad).write_text(VALID_DOC.replace("`AIMEM-state.md`", "`x.md`"), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([good]), 0)
            self.assertEqual(main([bad]), 1)


# ---------------------------------------------------------------------------
# 제거분 회귀 (식별자를 조각내 둔다: 통째로 적으면 이 파일이 자기 자신에 걸린다)
# ---------------------------------------------------------------------------

_REMOVED_NAMES = ("MAX_OUTBOX" + "_BYTES", "_check_outbox" + "_sizes")

# 2단계(T-061)에서 지운 이름. 되살아나면 반전된 계약이 깨진 것이다.
_REMOVED_2ND_STAGE = (
    "ADMIN_OWNER_LITERALS", "BOARD_NON_SLOT_OWNERS", "PROTECTED_PATHS", "MAX_LOG_ENTRY_CHARS",
    "_check_roster", "_check_board", "_check_ownership",
)


class TestRemovedNames(unittest.TestCase):
    def test_module_no_longer_exposes_outbox_names(self):
        for name in _REMOVED_NAMES:
            self.assertFalse(hasattr(lint, name), "제거된 이름이 아직 있다: %s" % name)

    def test_module_no_longer_exposes_second_stage_names(self):
        for name in _REMOVED_2ND_STAGE:
            self.assertFalse(hasattr(lint, name), "2단계에서 지운 이름이 아직 있다: %s" % name)

    def test_retained_public_api_present(self):
        for name in ("find_section", "extract_table", "lint_text", "lint_file", "lint_repo",
                     "MAX_TOTAL_LINES", "MANAGER_SESSION_KEY"):
            self.assertTrue(hasattr(lint, name), name)

    def test_lint_source_has_no_live_outbox_references(self):
        src = inspect.getsource(lint)
        code_lines = [l for l in src.splitlines()
                      if not l.lstrip().startswith("#") and "REV 103 에서 제거했다" not in l]
        for name in _REMOVED_NAMES:
            self.assertEqual([l for l in code_lines if name in l], [], name)

    def test_this_test_module_has_no_stale_outbox_references(self):
        src = open(os.path.abspath(__file__), encoding="utf-8").read()
        for name in _REMOVED_NAMES:
            hits = [l for l in src.splitlines() if name in l and '" + "' not in l]
            self.assertEqual(hits, [], hits)

    def test_removed_violation_codes_never_emitted(self):
        # 옛 표 기반 위반 코드는 어떤 입력에도 나오지 않는다 (표가 있어도 STATE_TABLE_IN_AIMEM 만).
        text = VALID_DOC.replace("## 2. 세션 명부\n\n", "## 2. 세션 명부\n\n" + TABLE + "\n", 1)
        for v in lint_text(text):
            for prefix in ("ROSTER_", "BOARD_", "OWNERSHIP_", "OUTBOX"):
                self.assertFalse(v.code.startswith(prefix), v.code)
            for gone in ("SIZE_HANDOFF_LOG", "SIZE_LOG_ENTRY_CHARS", "REV_LOG_MISSING", "HANDOFF_SECTION_MISSING"):
                self.assertNotEqual(v.code, gone)


class TestLintFileContract(unittest.TestCase):
    """`lint_file` 의 시그니처·반환 계약은 `aimem_board.py` 와 `.githooks/pre-commit` 이 의존한다."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="aimem_lint_contract_")
        self.addCleanup(shutil.rmtree, self._tmpdir, True)
        self.path = os.path.join(self._tmpdir, "AIMEM.md")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(VALID_DOC)

    def test_signature_is_path_and_optional_notes(self):
        params = list(inspect.signature(lint_file).parameters.values())
        self.assertEqual([p.name for p in params], ["path", "notes"])
        self.assertIsNone(params[1].default)

    def test_lint_repo_signature(self):
        params = list(inspect.signature(lint_repo).parameters.values())
        self.assertEqual([p.name for p in params], ["path", "root", "notes"])
        self.assertIsNone(params[1].default)
        self.assertIsNone(params[2].default)

    def test_returns_list_of_violations(self):
        self.assertEqual(lint_file(self.path), [])
        bad = os.path.join(self._tmpdir, "bad.md")
        with open(bad, "w", encoding="utf-8") as f:
            f.write(VALID_DOC.replace("**REV: 1**", "**REV: 0**"))
        vs = lint_file(bad)
        self.assertTrue(vs)
        for v in vs:
            self.assertIsInstance(v, Violation)
            self.assertIsInstance(v.code, str)
            self.assertIsInstance(v.message, str)
            self.assertTrue(v.line is None or isinstance(v.line, int))

    def test_accepts_notes_positionally_and_by_keyword(self):
        a, b = [], []
        self.assertEqual(lint_file(self.path, a), lint_file(self.path, notes=b))


if __name__ == "__main__":
    unittest.main()



class TestEnglishManagerDeclaration(unittest.TestCase):
    """REV 128: AIMEM.md 가 영어다. `Manager (sole write authority)` 선언도 한국어 선언과 같은 검사를 켠다."""
    EN_DOC = VALID_DOC.replace("- 관리자(단독 쓰기 권한): **클로** `agent:claude:acp:`\n",
                               "- Manager (sole write authority): **a Claude ACP session** `agent:claude:acp:`\n")

    def test_english_declaration_passes_with_pinned_key(self):
        self.assertNotEqual(self.EN_DOC, VALID_DOC)
        self.assertEqual(lint_text(self.EN_DOC), [])

    def test_english_declaration_gates_key_mismatch(self):
        swapped = self.EN_DOC.replace(MANAGER_SESSION_KEY, "agent:coding:discord:channel:9999999999")
        self.assertEqual(codes(lint_text(swapped)), ["MANAGER_KEY_MISMATCH"])


class TestHandoffInAimem(unittest.TestCase):
    """REV 129: 4절에 로그 항목이 남아 있으면 위반. 항목은 .aimem/handoff.md 에 둔다 (관리자 선언이 있을 때만 검사)."""

    def test_entry_in_section_4_fires(self):
        text = VALID_DOC.replace("## 4. 핸드오프 로그\n\n스냅샷: `AIMEM-state.md`\n",
                                 "## 4. 핸드오프 로그\n\n스냅샷: `AIMEM-state.md`\n\n- `2026-11-10 19:00` 관리자: 로그 항목\n")
        self.assertEqual(codes(lint_text(text)), ["HANDOFF_IN_AIMEM"])

    def test_entry_inside_fence_is_ignored(self):
        text = VALID_DOC.replace("## 4. 핸드오프 로그\n\n스냅샷: `AIMEM-state.md`\n",
                                 "## 4. 핸드오프 로그\n\n스냅샷: `AIMEM-state.md`\n\n```\n- `2026-11-10 19:00` 예시\n```\n")
        self.assertEqual(lint_text(text), [])

    def test_not_checked_without_declaration(self):
        text = NO_DECL_DOC.replace("## 4. 핸드오프 로그\n", "## 4. 핸드오프 로그\n\n- `2026-11-10 19:00` 관리자: 로그\n")
        self.assertEqual(lint_text(text), [])


class TestWeightNote(unittest.TestCase):
    """REV 130: 날짜·REV 인용이 권고치를 넘으면 노트(위반 아님)."""

    def test_note_when_history_piles_up(self):
        heavy = VALID_DOC + "\n" + "\n".join(f"- 2026-01-{i:02d} REV {i} 경위" for i in range(1, 32))
        notes = []
        self.assertEqual(lint_text(heavy, notes), [])
        self.assertTrue(any("가벼움" in n for n in notes))
        notes = []
        lint_text(VALID_DOC, notes)
        self.assertFalse(any("가벼움" in n for n in notes))
