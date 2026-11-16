"""끝에서 끝 검사에 쓰는 가짜 claude 명령. 인자는 무시한다."""

import os
import sys


def main():
    data = sys.stdin.read()
    if os.environ.get("FAKE_LLM_FAIL") == "1":
        sys.stderr.write("가짜 실패")
        return 2
    n = sum(1 for line in data.splitlines() if line.startswith("<녹취 "))
    sys.stdout.write("가짜 답: %d자를 읽었습니다 녹취 %d건\n" % (len(data), n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
