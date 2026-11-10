"""Checks for the generated web/js/words.js word lists."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


WORDS_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "words.js"
ARRAY_RE = re.compile(r"export const (ANSWERS|ALLOWED) = \[(.*?)\];", re.S)
STRING_RE = re.compile(r'"([^"]*)"')
WORD_RE = re.compile(r"[a-z]{5}")


class WordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        text = WORDS_JS.read_text(encoding="utf-8")
        cls.arrays = {
            name: STRING_RE.findall(body)
            for name, body in ARRAY_RE.findall(text)
        }

    def words(self, name: str) -> list[str]:
        self.assertIn(name, self.arrays)
        return self.arrays[name]

    def test_all_words_are_lowercase_five_letters(self) -> None:
        for name in ("ANSWERS", "ALLOWED"):
            words = self.words(name)
            self.assertTrue(words)
            for word in words:
                self.assertTrue(
                    WORD_RE.fullmatch(word), msg=f"bad word in {name}: {word!r}"
                )

    def test_counts(self) -> None:
        self.assertGreaterEqual(len(self.words("ANSWERS")), 2_000)
        self.assertLessEqual(len(self.words("ANSWERS")), 3_000)
        self.assertGreaterEqual(len(self.words("ALLOWED")), 5_000)
        self.assertLessEqual(len(self.words("ALLOWED")), 6_500)

    def test_answers_are_subset_of_allowed(self) -> None:
        self.assertLessEqual(set(self.words("ANSWERS")), set(self.words("ALLOWED")))

    def test_no_duplicates_and_sorted(self) -> None:
        for name in ("ANSWERS", "ALLOWED"):
            words = self.words(name)
            self.assertEqual(len(words), len(set(words)), msg=f"duplicates in {name}")
            self.assertEqual(words, sorted(words), msg=f"not sorted: {name}")

    def test_answers_do_not_end_in_s(self) -> None:
        for word in self.words("ANSWERS"):
            self.assertFalse(word.endswith("s"), msg=f"plural-looking answer: {word}")

    def test_expected_answers_present(self) -> None:
        answers = set(self.words("ANSWERS"))
        for word in ("crane", "about", "ghost", "vivid"):
            self.assertIn(word, answers)


if __name__ == "__main__":
    unittest.main()
