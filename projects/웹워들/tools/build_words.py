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
    answers = dictionary_words[0].intersection(*dictionary_words[1:])
    answers = {word for word in answers if not word.endswith("s")}

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
