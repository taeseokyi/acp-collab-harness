import contextlib
import inspect
import io
import pathlib
import re
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import browser_voxlog  # noqa: E402


class ImportTest(unittest.TestCase):
    # 1
    def test_imports_without_playwright(self):
        code = (
            "import sys; sys.path.insert(0, %r); "
            "import browser_voxlog; "
            "print('playwright' in sys.modules)"
        ) % str(HERE)
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "False")


class ParseSelectionTest(unittest.TestCase):
    # 2
    def test_no_args_selects_everything(self):
        self.assertEqual(browser_voxlog.parse_selection([]), (None, []))

    # 3
    def test_only_number_and_closed_range(self):
        only, match = browser_voxlog.parse_selection(["--only", "67,75-78"])
        self.assertEqual(only, {67, 75, 76, 77, 78})
        self.assertEqual(match, [])

    # 4
    def test_only_repeated_unions(self):
        only, _ = browser_voxlog.parse_selection(
            ["--only", "1", "--only", "3-5"])
        self.assertEqual(only, {1, 3, 4, 5})

    # 5
    def test_match_repeated_keeps_both_texts(self):
        only, match = browser_voxlog.parse_selection(
            ["--match", "기본값 읽기", "--match", "상세"])
        self.assertIsNone(only)
        self.assertEqual(match, ["기본값 읽기", "상세"])

    # 6
    def test_only_and_match_together(self):
        only, match = browser_voxlog.parse_selection(
            ["--only", "2", "--match", "상세"])
        self.assertEqual(only, {2})
        self.assertEqual(match, ["상세"])

    # 7
    def test_bad_only_values_are_argparse_errors(self):
        for bad in ("7-", "x", "5-3"):
            with self.subTest(bad=bad):
                with self.assertRaises(SystemExit) as caught:
                    browser_voxlog.parse_selection(["--only", bad])
                self.assertEqual(caught.exception.code, 2)


class TestNumberTest(unittest.TestCase):
    # 8
    def test_leading_number(self):
        self.assertEqual(browser_voxlog.test_number("67 상세 기본값"), 67)
        self.assertEqual(browser_voxlog.test_number("  12 앞 공백"), 12)

    # 9
    def test_name_without_number_rejected(self):
        with self.assertRaises(ValueError):
            browser_voxlog.test_number("번호 없음")


class ExpandNeedsTest(unittest.TestCase):
    # 10
    def test_follows_chain(self):
        needs = {3: (2,), 2: (1,)}
        self.assertEqual(browser_voxlog.expand_needs({3}, needs), {1, 2, 3})

    # 11
    def test_cycle_terminates(self):
        self.assertEqual(browser_voxlog.expand_needs({1}, {1: (2,), 2: (1,)}), {1, 2})

    # 12
    def test_no_dependencies_leaves_set_alone(self):
        self.assertEqual(browser_voxlog.expand_needs({4, 9}, {}), {4, 9})

    # 13
    def test_real_needs_numbers_sane(self):
        for num, deps in browser_voxlog.NEEDS.items():
            self.assertGreaterEqual(num, 1)
            self.assertLessEqual(num, 78)
            for dep in deps:
                self.assertGreaterEqual(dep, 1)
                self.assertLessEqual(dep, 78)
                self.assertNotEqual(dep, num)


class SummaryLineTest(unittest.TestCase):
    # 14
    def test_full_run_ends_with_full_pass(self):
        line = browser_voxlog.summary_line(77, 77, 77, 0)
        self.assertEqual(line, "77/77 통과")
        self.assertTrue(line.endswith("77/77 통과"))

    # 15
    def test_partial_run_is_not_full_pass(self):
        line = browser_voxlog.summary_line(3, 77, 3, 74)
        self.assertIn("부분 실행", line)
        self.assertIn("건너뜀", line)
        self.assertIn("전체 통과 아님", line)
        self.assertIsNone(re.search(r"\d+/\d+ 통과$", line))

    # 16
    def test_partial_run_with_failure_still_not_full_pass(self):
        line = browser_voxlog.summary_line(3, 77, 2, 74)
        self.assertIn("2/3 통과", line)
        self.assertIsNone(re.search(r"\d+/\d+ 통과$", line))


class CheckSelectionTest(unittest.TestCase):
    # 17
    def test_check_skips_unselected_without_running_it(self):
        saved_selection = browser_voxlog.SELECTION
        saved_skipped = browser_voxlog.SKIPPED
        saved_results = list(browser_voxlog.RESULTS)
        called = []
        try:
            browser_voxlog.SELECTION = {2}
            browser_voxlog.SKIPPED = 0
            del browser_voxlog.RESULTS[:]
            with contextlib.redirect_stdout(io.StringIO()):
                browser_voxlog.check("5 고르지 않은 검사", lambda: called.append(5))
                browser_voxlog.check("2 고른 검사", lambda: called.append(2))
            self.assertEqual(called, [2])
            self.assertEqual(browser_voxlog.SKIPPED, 1)
            self.assertEqual(len(browser_voxlog.RESULTS), 1)
            self.assertEqual(browser_voxlog.RESULTS[0][0], "2 고른 검사")
            self.assertTrue(browser_voxlog.RESULTS[0][1])
        finally:
            browser_voxlog.SELECTION = saved_selection
            browser_voxlog.SKIPPED = saved_skipped
            browser_voxlog.RESULTS[:] = saved_results


class ResolveSelectionTest(unittest.TestCase):
    # 18
    def test_no_args_is_none_for_full_run(self):
        self.assertIsNone(browser_voxlog.resolve_selection(None, []))

    # 19
    def test_only_is_expanded_with_real_needs(self):
        self.assertEqual(browser_voxlog.resolve_selection({7}, []), {2, 3, 7})

    # 20
    def test_match_resolves_known_name(self):
        # `기본값 읽기` 가 든 검사는 68번이다(67번은 `기본값 응답…읽기 끊김`).
        self.assertIn(68, browser_voxlog.resolve_selection(None, ["기본값 읽기"]))


class RealNeedsTest(unittest.TestCase):
    # 21
    def test_expand_uses_module_needs(self):
        self.assertEqual(browser_voxlog.expand_needs({4}), {2, 3, 4})
        self.assertEqual(browser_voxlog.expand_needs({6}), {2, 5, 6})


class KnownNamesTest(unittest.TestCase):
    # 22
    def test_collects_all_77_and_41_absent(self):
        names = browser_voxlog._known_names()
        self.assertEqual(len(names), 77)
        self.assertNotIn(41, names)


class ExitCodeTest(unittest.TestCase):
    # 23
    def test_requires_ran_at_least_one_and_no_failure(self):
        self.assertEqual(browser_voxlog.exit_code(0, 0), 1)
        self.assertEqual(browser_voxlog.exit_code(3, 0), 0)
        self.assertEqual(browser_voxlog.exit_code(3, 1), 1)

    # 24
    def test_main_uses_exit_code(self):
        self.assertIn("exit_code(", inspect.getsource(browser_voxlog.main))


class ApplySelectionTest(unittest.TestCase):
    # 25
    def test_sets_and_returns_selection(self):
        saved = browser_voxlog.SELECTION
        try:
            self.assertEqual(browser_voxlog.apply_selection(["--only", "7"]), {2, 3, 7})
            self.assertEqual(browser_voxlog.SELECTION, {2, 3, 7})
            self.assertIsNone(browser_voxlog.apply_selection([]))
            self.assertIsNone(browser_voxlog.SELECTION)
        finally:
            browser_voxlog.SELECTION = saved


if __name__ == "__main__":
    unittest.main()
