"""끝에서 끝 검사에 쓰는 가짜 claude 명령. 인자는 무시한다."""

import os
import sys
import time


def main():
    data = sys.stdin.read()
    if os.environ.get("FAKE_LLM_FAIL") == "1":
        sys.stderr.write("가짜 실패")
        return 2
    if data.startswith("이 녹취에 붙일 주제 태그"):
        try:
            time.sleep(float(os.environ.get("FAKE_LLM_TAG_DELAY", "0")))
        except (ValueError, OverflowError):
            pass
        sys.stdout.write(os.environ.get("FAKE_LLM_TAGS", "회의\n가짜 태그\n- 세번째"))
        return 0
    n = sum(1 for line in data.splitlines() if line.startswith("<녹취 "))
    sys.stdout.write("가짜 답: %d자를 읽었습니다 녹취 %d건\n" % (len(data), n))
    # 화면이 마크다운으로 그리는지 보는 본문 (HTML 은 글자로 남아야 한다)
    sys.stdout.write("\n## 요약\n\n- **굵은** 항목과 `코드`\n  - 안쪽 항목\n- [링크](https://example.org/a)\n\n"
                     "1. 첫째\n2. 둘째\n\n| 이름 | 값 |\n|---|---|\n| 가 | <b>나</b> |\n\n"
                     "> 인용\n\n```\ncode *그대로*\n```\n\n<img src=x onerror=\"document.title='XSS'\">\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
