"""envcheck - 이 저장소 **밖**의 기록이 아직 맞는지 검사한다.

린터(`aimem_lint.py`)와 역할이 다르다. 린터는 **우리 문장을 우리 검사기로** 재므로
반대편이 없다 - 우리가 둘 다 쓰면 언제나 통과한다. envcheck 의 검사 대상은
하네스 CLI(claude/codex/opencode), `fleet.toml`·`.env`, `~/.local/bin/pan-run`, tmux 처럼
**우리가 쓰지 않은 것**이다. 그래서 "우리 기록이 틀렸다"고 말해 줄 수 있다.

계층은 셋이고 각각 다른 슬롯이 소유한다(`AIMEM.md` `6절`):

    sessions.py   S1   세션·하네스 계층 (하네스 CLI 점검, fleet.toml·.env, 슬롯 공급자)
    runtime.py    S2   실행 환경 계층 (파이썬 환경, WSL DNS)
    terminal.py   S3   터미널 규약 계층 (pan-run 종료코드·복구 도달성, 팬 배치)

**공통 계약 - 이 인터페이스는 관리자가 못박고 슬롯이 협의하지 않는다:**

    check() -> list[Result]
    Result = (name: str, status: str, evidence: str)

`status` 는 아래 셋 중 하나다.

    OK       기록대로다
    CHANGED  기록과 다르다 - 기록을 고쳐야 한다
    UNKNOWN  판정하지 못했다 (대상이 없거나 조회에 실패했다)

**모듈은 관측만 하고 상태를 남기지 않는다.** 누적 판정은 통합 러너(`__main__.py`,
관리자 소유)의 몫이다 - 합류점을 하나로 두기 위해서다.
"""

OK = "OK"
CHANGED = "CHANGED"
UNKNOWN = "UNKNOWN"

STATUSES = (OK, CHANGED, UNKNOWN)

#: 계층 모듈 이름. 러너가 이 순서로 import 한다.
LAYERS = ("sessions", "runtime", "terminal")

__all__ = ["OK", "CHANGED", "UNKNOWN", "STATUSES", "LAYERS"]
