"""web/js/words.js 낱말 목록 검사 (unittest)."""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
WORDS_JS = PROJECT / "web" / "js" / "words.js"
BUILD = PROJECT / "tools" / "build_words.py"
SEED = 20261113

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅗㅏ", "ㅗㅐ", "ㅗㅣ",
    "ㅛ", "ㅜ", "ㅜㅓ", "ㅜㅔ", "ㅜㅣ", "ㅠ", "ㅡ", "ㅡㅣ", "ㅣ",
]
JONG = [
    "", "ㄱ", "ㄲ", "ㄱㅅ", "ㄴ", "ㄴㅈ", "ㄴㅎ", "ㄷ", "ㄹ", "ㄹㄱ", "ㄹㅁ", "ㄹㅂ",
    "ㄹㅅ", "ㄹㅌ", "ㄹㅍ", "ㄹㅎ", "ㅁ", "ㅂ", "ㅂㅅ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ",
    "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]
UNITS = 6

BANNED = set(
    """
    염병 정욕 정액 관우 독일 경성 흑인 살인 급강 급경 멍청 먹방
    한국 북한 중국 한강 한글 금산 강간 북극 금강
    염감 염건 염밀 염옥 염온 염용 염착 염담 정탈 역복 역송
    염결 염낭 염막 염문 염물 염박 염반 염법 염복 염상 염생 염석
    염선 염성 염숙 염순 염습 염심 염안 염액 염연 염열 염욕 염육
    염음 염인 염정 염직 염질 염창 염천 염철 염총 염축 염출 염충
    염탐 염통 염판 염풍 염학 염한 염합 염행 염향 염혈 염황
    쇄약 갑작 학종 국공 과감 과중
    희한 민망 괴악 희식 화성 국전
    억울 솔직 명랑 온순 당당 씩씩 튼튼 든든 단단 쌀쌀 침울 패이다 개이다
    착실 똑똑 꼼꼼 넉넉
    """.split()
)

MUST = (
    "아버지 어머니 이야기 무지개 과학 성공 걱정 칭찬 웃음 떡국 짬뽕 "
    "아파트 낮잠 첫눈 왕자 군인 직장 성적 색깔 천둥 칫솔 책장 촛불 "
    "손톱 꽃밭 연못 작년 일년 요리사 사이다 "
    "선생 장난 운전 케이크 햇볕 풀잎 숲길 불빛 열병 복통 꿈속 진실 덧셈 "
    "뺄셈 곱셈 풀칠 급식 손뼉 울음 기지개 여권 출근 반말 벚꽃 단감 곶감 "
    "밥상 반죽 콩국 까닭"
).split()


def to_units(word: str) -> str | None:
    if not word:
        return None
    out = []
    for ch in word:
        code = ord(ch) - 0xAC00
        if not 0 <= code < 11172:
            return None
        out.append(CHO[code // 588] + JUNG[(code % 588) // 28] + JONG[code % 28])
    return "".join(out)


def read_arrays() -> dict[str, list[str]]:
    text = WORDS_JS.read_text(encoding="utf-8")
    arrays = {}
    for name in ("ANSWERS", "ALLOWED"):
        match = re.search(
            r"export const " + name + r"\s*=\s*(\[.*?\]);", text, re.S
        )
        if not match:
            raise AssertionError(f"{name} 배열을 찾지 못했습니다")
        arrays[name] = json.loads(match.group(1))
    return arrays


class WordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.arrays = read_arrays()

    def words(self, name: str) -> list[str]:
        self.assertIn(name, self.arrays)
        return self.arrays[name]

    def test_every_word_is_six_units(self) -> None:
        for name in ("ANSWERS", "ALLOWED"):
            for word in self.words(name):
                units = to_units(word)
                self.assertIsNotNone(units, msg=f"{name}: 완성형 한글이 아님 {word!r}")
                self.assertEqual(len(units), UNITS, msg=f"{name}: 6칸이 아님 {word!r}")

    def test_no_duplicates(self) -> None:
        for name in ("ANSWERS", "ALLOWED"):
            words = self.words(name)
            self.assertEqual(len(words), len(set(words)), msg=f"{name} 중복")

    def test_answers_subset_of_allowed(self) -> None:
        self.assertLessEqual(set(self.words("ANSWERS")), set(self.words("ALLOWED")))

    def test_answers_match_answers_file(self) -> None:
        path = PROJECT / "data" / "answers.txt"
        file_words = {
            w.strip()
            for w in path.read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.strip().startswith("#")
        }
        answers = self.words("ANSWERS")
        self.assertEqual(set(answers), file_words, msg="ANSWERS 가 answers.txt 와 다름")
        self.assertEqual(len(answers), 380)

    def test_counts(self) -> None:
        self.assertGreaterEqual(len(self.words("ANSWERS")), 300)
        self.assertGreaterEqual(len(self.words("ALLOWED")), 2000)

    def test_banned_words_absent(self) -> None:
        allowed = set(self.words("ALLOWED"))
        hit = sorted(BANNED & allowed)
        self.assertFalse(hit, msg=f"금칙어가 ALLOWED 에 남음: {hit}")

    def test_common_words_present(self) -> None:
        allowed = set(self.words("ALLOWED"))
        missing = [word for word in MUST if word not in allowed]
        self.assertFalse(missing, msg=f"흔한 낱말이 ALLOWED 에 없음: {missing}")

    def test_first_syllable_not_mass_generated(self) -> None:
        first = Counter(word[0] for word in self.words("ALLOWED"))
        top = first.most_common(1)[0]
        limit = max(40, len(self.words("ALLOWED")) * 4 // 100)
        self.assertLessEqual(top[1], limit, msg=f"한 첫 음절로 몰림: {top} (상한 {limit})")

    def test_branch_files_first_syllable(self) -> None:
        files = sorted((PROJECT / "data" / "words").glob("*.txt"))
        self.assertTrue(files, msg="data/words/*.txt 가 없음")
        for path in files:
            words = [
                w.strip()
                for w in path.read_text(encoding="utf-8").splitlines()
                if w.strip() and not w.strip().startswith("#")
            ]
            first = Counter(w[0] for w in words)
            if first:
                top = first.most_common(1)[0]
                self.assertLessEqual(top[1], 15, msg=f"{path.name}: 한 첫 음절로 몰림 {top}")

    def test_allowed_sorted(self) -> None:
        self.assertEqual(self.words("ALLOWED"), sorted(self.words("ALLOWED")))

    def test_answers_shuffled(self) -> None:
        answers = self.words("ANSWERS")
        expected = sorted(answers)
        random.Random(SEED).shuffle(expected)
        self.assertNotEqual(answers, sorted(answers), msg="ANSWERS 가 정렬된 채")
        self.assertEqual(answers, expected, msg="고정 씨앗 순서와 다름")

    def test_rebuild_is_byte_identical(self) -> None:
        before = WORDS_JS.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "words.js"
            subprocess.run(
                [sys.executable, str(BUILD), "--out", str(out)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(out.read_bytes(), before, msg="다시 만들면 파일이 달라짐")
        self.assertEqual(WORDS_JS.read_bytes(), before, msg="시험이 진짜 words.js 를 건드림")

    def test_unit_examples(self) -> None:
        self.assertEqual(to_units("한국"), "ㅎㅏㄴㄱㅜㄱ")
        self.assertEqual(to_units("까닭"), "ㄲㅏㄷㅏㄹㄱ")
        self.assertEqual(to_units("과자"), "ㄱㅗㅏㅈㅏ")
        self.assertEqual(len(to_units("과자")), 5)


if __name__ == "__main__":
    unittest.main()
