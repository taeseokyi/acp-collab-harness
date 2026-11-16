#!/usr/bin/env python3
"""가짜 음성인식 명령.

사용: python3 fake_stt.py <wav경로>
표준 출력에 `가짜 받아쓰기 <파일 바이트 수>바이트` 한 줄.
환경 변수 FAKE_STT_FAIL=1 이면 stderr 에 '가짜 실패' 를 쓰고 코드 3 으로 끝난다.
"""

import os
import sys


def main(argv):
    if os.environ.get("FAKE_STT_FAIL") == "1":
        sys.stderr.write("가짜 실패\n")
        return 3
    if len(argv) < 2:
        sys.stderr.write("사용: fake_stt.py <wav경로>\n")
        return 2
    try:
        size = os.path.getsize(argv[1])
    except OSError as exc:
        sys.stderr.write("파일을 읽을 수 없습니다: %s\n" % exc)
        return 2
    sys.stdout.write("가짜 받아쓰기 %d바이트\n" % size)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
