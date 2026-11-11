#!/usr/bin/env python3
"""Build web/js/words.js from the system dictionaries."""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path


DICTIONARIES = (
    Path("/usr/share/dict/american-english"),
    Path("/usr/share/dict/cracklib-small"),
)
WORD_RE = re.compile(r"[a-z]{5}")

COMMON_ANSWER_KEEP = {"crane"}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "web" / "js" / "words.js"


def load_words(path: Path) -> set[str]:
    words: set[str] = set()
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            word = line.strip()
            if WORD_RE.fullmatch(word):
                words.add(word)
    return words


def load_capitalized(path: Path) -> set[str]:
    """사전에 `Crane` 처럼 대문자로 적힌 다섯 글자 낱말의 소문자 꼴."""
    words: set[str] = set()
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            word = line.strip()
            if len(word) == 5 and word[0].isupper() and word.isalpha() and word.isascii():
                words.add(word.lower())
    return words


def load_any_lowercase(path: Path) -> set[str]:
    """길이를 가리지 않고 사전에 있는 소문자 낱말 전부 (어간 조회용)."""
    words: set[str] = set()
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            word = line.strip()
            if word.islower() and word.isalpha() and word.isascii():
                words.add(word)
    return words


def filter_answers(answers: set[str], allowed: set[str], capitalized: set[str]) -> set[str]:
    """꼴만 보고 흔하지 않은 정답 후보를 거릅니다 (빈도 자료 없음).

    1. 고유명사 - 사전에 대문자 꼴이 함께 있으면 뺍니다 (`roman`/`Roman`)
       단, `crane` 은 흔한 낱말이므로 대문자 꼴 `Crane` 이 있어도 남깁니다.
    2. 복수형·3인칭 - `s` 로 끝나면 뺍니다 (전부터 있던 규칙)
    3. 굴절형 - `ed`/`er` 로 끝나고 그 어간이 허용 목록에 있으면 뺍니다 (`abler` <- `able`)
    4. 고어 꼴 - `eth`/`est` 로 끝나고 그 어간이 허용 목록에 있으면 뺍니다 (`doeth`)
    """
    kept: set[str] = set()
    for word in answers:
        if word in capitalized and word not in COMMON_ANSWER_KEEP:
            continue
        if word.endswith("s"):
            continue
        if word.endswith(("ed", "er")) and _has_stem(word[:-2], allowed):
            continue
        if word.endswith(("eth", "est")) and _has_stem(word[:-3], allowed):
            continue
        kept.add(word)
    return kept


def _has_stem(stem: str, allowed: set[str]) -> bool:
    """어간 자체, 또는 `e` 를 붙인 꼴, 또는 끝 자음을 겹친 꼴이 사전에 있는가."""
    if len(stem) < 3:
        return False
    if stem in allowed or (stem + "e") in allowed:
        return True
    return len(stem) >= 4 and stem[-1] == stem[-2] and stem[:-1] in allowed


def format_array(name: str, words: set[str]) -> str:
    lines = [f"export const {name} = ["]
    ordered = sorted(words)
    for start in range(0, len(ordered), 10):
        chunk = ordered[start : start + 10]
        lines.append("  " + ", ".join(f'"{word}"' for word in chunk) + ",")
    lines.append("];")
    return "\n".join(lines)


def main() -> int:
    missing = [str(path) for path in DICTIONARIES if not path.is_file()]
    if missing:
        for path in missing:
            print(f"missing dictionary: {path}", file=sys.stderr)
        return 1

    dictionary_words = [load_words(path) for path in DICTIONARIES]
    allowed = set().union(*dictionary_words)
    stems = set().union(*(load_any_lowercase(path) for path in DICTIONARIES))
    capitalized = set().union(*(load_capitalized(path) for path in DICTIONARIES))
    answers = dictionary_words[0].intersection(*dictionary_words[1:])
    answers = filter_answers(answers, stems, capitalized)

    generated = datetime.date.today().isoformat()
    content = "\n".join(
        [
            "// 생성물입니다 - 손으로 고치지 말고 `python3 projects/웹워들/tools/build_words.py` 로 다시 만드십시오.",
            (
                "// 출처: /usr/share/dict/american-english + "
                f"/usr/share/dict/cracklib-small ({generated} 생성)"
            ),
            format_array("ANSWERS", answers),
            format_array("ALLOWED", allowed),
        ]
    ) + "\n"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(answers)} answers, {len(allowed)} allowed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
