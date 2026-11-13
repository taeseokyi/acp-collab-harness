# -*- coding: utf-8 -*-
"""tools/aimem_lint.py 테스트. 표준 라이브러리 unittest 만 사용."""

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

import aimem_db
from aimem_lint import (
    MANAGER_SESSION_FORM,
    MANAGER_SESSION_RE,
    MAX_TOTAL_LINES,
    Violation,
    lint_file,
    lint_repo,
    lint_text,
    main,
)

# 관리자 선언이 있는 최소 픽스처 - 2·3·4·4.5·6절에는 포인터만, 위반 0.
VALID_DOC = """# AIMEM.md - 공유 작업 메모리

- **REV: 1** (개정 번호)
- 최종 갱신: 2026-08-25
- 관리자(단독 쓰기 권한): 엔진이 띄운 관리자 세션 `M-R<N>-<HHMMSS>`

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

# 관리자 선언이 없는 최소 픽스처 - STATE_* 검사는 게이팅 때문에 발화하지 않는다.
NO_DECL_DOC = VALID_DOC.replace("- 관리자(단독 쓰기 권한): 엔진이 띄운 관리자 세션 `M-R<N>-<HHMMSS>`\n", "")

TABLE = "| 슬롯 | 확인토큰 |\n| ---- | -------- |\n| S1   | `abc123` |\n"


def codes(violations):
    return sorted(v.code for v in violations)

# `python3 -m unittest … 2>&1 | tail -3` 의 마지막 줄이 `OK` 이게 합니다 (2026-11-11 R11 T-139).
# 이 파일의 시험이 부르는 명령들이 표준출력에 찍는 줄(`ok: …aimem.db`, 린터 결과)은 파이프에서 버퍼에 있다가
# unittest 요약 **뒤에** 나와, `tail -3 | grep '^OK'` 로 건 검증이 멀쩡한 작업을 실패로 판정했습니다.
_QUIET = []


def setUpModule():
    import contextlib
    import io
    cm = contextlib.redirect_stdout(io.StringIO())
    cm.__enter__()
    _QUIET.append(cm)


def tearDownModule():
    while _QUIET:
        _QUIET.pop().__exit__(None, None, None)


class TestValidDoc(unittest.TestCase):
    def test_valid_fixture_has_no_violations(self):
        self.assertEqual(lint_text(VALID_DOC), [])


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
# 규칙별 검사. 운영 상태 표는 `.aimem/aimem.db` 에 있고 AIMEM.md 에는 표가 없어야 한다.
# ---------------------------------------------------------------------


class TestSizeConstantsMatchSpec(unittest.TestCase):
    def test_total_lines_limit_is_800(self):
        self.assertEqual(MAX_TOTAL_LINES, 800)

    def test_manager_session_form_is_pinned(self):
        self.assertEqual(MANAGER_SESSION_FORM, "M-R<N>-<HHMMSS>")
        self.assertTrue(MANAGER_SESSION_RE.fullmatch("M-R21-193012"))
        for bad in ("M-R21-1930", "M-RX-193012", "agent:claude:acp:x"):
            self.assertFalse(MANAGER_SESSION_RE.fullmatch(bad), bad)


class TestManagerKeyMismatch(unittest.TestCase):
    DECL_LINE = "- 관리자(단독 쓰기 권한): 엔진이 띄운 관리자 세션 `%s`\n" % MANAGER_SESSION_FORM

    def test_mismatch_fires_when_key_swapped(self):
        text = VALID_DOC.replace(MANAGER_SESSION_FORM, "some-other-session-id-9999")
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
            "- 관리자(단독 쓰기 권한): 엔진이 띄운 관리자 세션 `M-R<N>-<HHMMSS>`\n", "")
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

    # (b) 진짜 aimem_db 로 임시 저장소를 만들어 render 한 직후는 깨끗하고, 세션·이벤트가 더해져도 낡지 않는다
    def test_rendered_temp_repo_is_clean_and_stays_clean_after_sessions_and_events(self):
        aimem = self._tmp / ".aimem"
        for target, attr, value in ((aimem_db, "ROOT", self._tmp), (aimem_db, "DB", aimem / "aimem.db"),
                                    (aimem_db, "AIMEM", self.md), (aimem_db, "HANDOFF", aimem / "handoff.md")):
            pt = mock.patch.object(target, attr, value)
            pt.start()
            self.addCleanup(pt.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.cmd_init()
            with aimem_db.connect() as con:
                con.execute("INSERT INTO meta(key,value) VALUES('rev','1')")
            aimem_db.render()
        self.assertEqual(lint_repo(self.md, root=self._tmp), [])
        with aimem_db.connect() as con:
            con.execute("INSERT INTO sessions(id,role,harness,state,started) VALUES('M-R1-000000','manager','claude','running','2026-01-01T00:00:00')")
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES('2026-01-01T00:00:00','t',1,'note','x')")
        self.assertEqual(lint_repo(self.md, root=self._tmp), [])

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


class TestLintFileContract(unittest.TestCase):
    """`lint_file`·`lint_repo` 의 시그니처·반환 계약 (`.githooks/pre-commit` 이 린터를 부른다)."""

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


class TestEnglishManagerDeclaration(unittest.TestCase):
    """REV 128: AIMEM.md 가 영어다. `Manager (sole write authority)` 선언도 한국어 선언과 같은 검사를 켠다."""
    EN_DOC = VALID_DOC.replace("- 관리자(단독 쓰기 권한): 엔진이 띄운 관리자 세션 `M-R<N>-<HHMMSS>`\n",
                               "- Manager (sole write authority): the engine-launched manager session `M-R<N>-<HHMMSS>`\n")

    def test_english_declaration_passes_with_pinned_key(self):
        self.assertNotEqual(self.EN_DOC, VALID_DOC)
        self.assertEqual(lint_text(self.EN_DOC), [])

    def test_english_declaration_gates_key_mismatch(self):
        swapped = self.EN_DOC.replace(MANAGER_SESSION_FORM, "some-other-session-id-9999")
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


if __name__ == "__main__":
    unittest.main()
