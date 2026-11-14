#!/usr/bin/env python3
"""연합뉴스 RSS 제목에서 6칸 낱말을 골라 사전으로 확인하고 `data/trend.txt` 에 날짜별 정답으로 덧붙입니다.

    python3 projects/자모맞히기/tools/pick_answers.py [--days 7] [--source wiktionary] [--start YYYY-MM-DD] [--dry-run]

고르는 일은 `trend_news.pick` 이 하고, 이 도구는 앱 서버와 같은 `trend_store.pick_and_store` 로
`trend.txt` 에 이미 있는 날짜를 건너뛰어 빈 날짜에 덧붙이고 시각(`trend_meta.json`)을 적은 뒤 `build_words.main()` 으로 `web/js/words.js` 를 다시 만듭니다. 키는 필요 없습니다(위키 사전 기준).
날마다 정답을 새로 채우려면 이 명령을 하루에 한 번 돌리거나, 게임 설정 창의 "지금 뉴스에서 정답 고르기" 를 누르십시오.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
for _path in (PROJECT_ROOT, TOOLS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import build_words  # noqa: E402
import trend_news  # noqa: E402
import trend_store  # noqa: E402

TREND_PATH = trend_store.TREND_PATH


def main(argv=None, *, pick=None, trend_path=None, meta_path=None, rebuild=None) -> int:
    parser = argparse.ArgumentParser(description="연합뉴스 RSS 로 트렌드 정답 고르기")
    parser.add_argument("--days", type=int, default=7, help="고를 날짜 수 1~14 (기본 7)")
    parser.add_argument("--source", default="wiktionary", help="확인할 사전 id (기본 wiktionary)")
    parser.add_argument("--start", default=None, help="시작 날짜 YYYY-MM-DD (기본 오늘)")
    parser.add_argument("--dry-run", action="store_true", help="파일에 쓰지 않고 날짜·낱말만 출력")
    args = parser.parse_args(argv)

    if not 1 <= args.days <= 14:
        print("--days 는 1~14 입니다.", file=sys.stderr)
        return 1
    if args.start is not None and not build_words.is_date(args.start):
        print("--start 는 YYYY-MM-DD 꼴이어야 합니다.", file=sys.stderr)
        return 1

    trend_file = Path(trend_path) if trend_path else TREND_PATH
    meta_file = Path(meta_path) if meta_path else (
        trend_store.META_PATH if trend_file == TREND_PATH else trend_file.with_name("trend_meta.json"))
    chooser = pick or trend_news.pick
    start = args.start or date.today().isoformat()
    if args.dry_run:
        result = chooser(args.days, args.source, start, skip_dates=sorted(trend_store.read_trend(trend_file)))
    else:
        result = trend_store.pick_and_store(args.days, args.source, start, pick=chooser,
                                            path=trend_file, meta_path=meta_file)
    if not isinstance(result, dict) or not result.get("ok"):
        print((result or {}).get("error", "정답 고르기에 실패했습니다") if isinstance(result, dict)
              else "정답 고르기에 실패했습니다", file=sys.stderr)
        return 1

    picks = result.get("picks") or []
    if not picks:
        print("고른 낱말이 없습니다.", file=sys.stderr)
        return 1
    rows = [f"{item['date']} {item['word']}" for item in picks]
    for row in rows:
        print(row)
    print(f"(뉴스 제목 {result.get('titles', 0)}건, 후보 {result.get('candidates', 0)}개)")
    if args.dry_run:
        print("(dry-run: data/trend.txt 에 쓰지 않았습니다)")
        return 0

    print(f"{trend_file} 에 {len(result.get('added') or [])}줄 덧붙였습니다.")
    return (rebuild or rebuild_words)()


def rebuild_words() -> int:
    """words.js 를 다시 만듭니다. build_words.main 은 자기 인자를 sys.argv 에서 읽으므로 비워 둡니다."""
    saved = sys.argv
    sys.argv = [saved[0]]
    try:
        return build_words.main()
    finally:
        sys.argv = saved


if __name__ == "__main__":
    raise SystemExit(main())
