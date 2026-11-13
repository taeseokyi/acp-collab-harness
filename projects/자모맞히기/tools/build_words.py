#!/usr/bin/env python3
"""data/answers.txt·data/allowed.txt·data/words/*.txt 에서 web/js/words.js 를 만듭니다.

손으로 고른 낱말 원본을 읽어 완성형 한글 음절만으로 된 6칸 낱말만 남기고,
정답 후보(ANSWERS)는 고정 씨앗으로 섞고 추측 목록(ALLOWED)은 정렬합니다.
표준 라이브러리만 씁니다. `--out PATH` 로 출력 위치를 바꿀 수 있습니다.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANSWERS_IN = PROJECT_ROOT / "data" / "answers.txt"
ALLOWED_IN = PROJECT_ROOT / "data" / "allowed.txt"
WORDS_DIR = PROJECT_ROOT / "data" / "words"
OUTPUT = PROJECT_ROOT / "web" / "js" / "words.js"

SEED = 20261113
WORD_UNITS = 6

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


def units(word: str) -> str | None:
    """완성형 한글 음절만으로 된 낱말 → 칸 문자열. 아니면 None."""
    if not word:
        return None
    out: list[str] = []
    for ch in word:
        code = ord(ch) - 0xAC00
        if not 0 <= code < 11172:
            return None
        out.append(CHO[code // 588] + JUNG[(code % 588) // 28] + JONG[code % 28])
    return "".join(out)


def load_words(path: Path) -> tuple[list[str], int]:
    """앞뒤 공백·빈 줄·`#` 주석 줄을 버리고 6칸 낱말만 남깁니다.

    돌려주는 값은 (중복 없는 낱말 목록, 걸러 낸 줄 수) 입니다.
    걸러 낸 줄 수에는 빈 줄·주석 줄도 포함합니다.
    """
    words: list[str] = []
    seen: set[str] = set()
    dropped = 0
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            word = raw.strip()
            if not word or word.startswith("#"):
                dropped += 1
                continue
            if (units(word) is None) or len(units(word)) != WORD_UNITS:
                dropped += 1
                continue
            if word in seen:
                dropped += 1
                continue
            seen.add(word)
            words.append(word)
    return words, dropped


def format_array(name: str, words: list[str]) -> str:
    return f"export const {name} = {json.dumps(words, ensure_ascii=False)};"


def main() -> int:
    parser = argparse.ArgumentParser(description="낱말 목록으로 words.js 생성")
    parser.add_argument(
        "--out",
        type=Path,
        default=OUTPUT,
        help="출력 파일 경로 (기본: web/js/words.js)",
    )
    args = parser.parse_args()
    output = args.out

    for path in (ANSWERS_IN, ALLOWED_IN):
        if not path.is_file():
            print(f"missing input: {path}", file=sys.stderr)
            return 1

    answers, dropped_answers = load_words(ANSWERS_IN)
    allowed, dropped_allowed = load_words(ALLOWED_IN)
    branches = [(p, *load_words(p)) for p in sorted(WORDS_DIR.glob("*.txt"))]

    ordered_answers = sorted(answers)
    random.Random(SEED).shuffle(ordered_answers)
    union_set = set(answers) | set(allowed)
    for _, words, _ in branches:
        union_set.update(words)
    union = sorted(union_set)

    content = "\n".join(
        [
            "// 생성물 - 손으로 고치지 말고 tools/build_words.py 로 다시 만드십시오",
            format_array("ANSWERS", ordered_answers),
            format_array("ALLOWED", union),
        ]
    ) + "\n"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"answers: {len(ordered_answers)}개 (걸러 냄 {dropped_answers}줄)")
    print(f"allowed: {len(union)}개 (원본 {len(allowed)}개, 걸러 냄 {dropped_allowed}줄)")
    for path, words, dropped in branches:
        print(f"  {path.name}: {len(words)}개 (걸러 냄 {dropped}줄)")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
