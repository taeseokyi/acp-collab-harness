"""관리자 세션 명세 (설계 `docs/FLEET-ENGINE-V2.md` 3.3·3.4).

관리자는 `role="manager"` 인 claude 세션일 뿐이다. 엔진(`fleet_ctl.launch_round`)이 `sessions.spawn` 으로 직접
띄우고, 여기에는 그 명세를 만드는 것만 둔다 - 의존 방향은 fleet_ctl -> fleet_rt 이라 `fleet` 은 들이지 않는다.

허용 도구 목록(`MANAGER_TOOLS`)은 **사고를 막는 난간이지 보안 경계가 아니다.** `Write` 와 `python3 -m unittest` 가
있으므로 관리자는 마음먹으면 아무 코드나 돌릴 수 있다. 목록이 하는 일은 흔한 실수 - 커밋·푸시, 지우기, 설치,
남의 프로세스 끊기, 운영 모니터 다시 띄우기 - 를 한 줄 명령으로 바로 하지 못하게 하는 것뿐이다. 그래서:
- 넣지 않은 것: `fleet_ctl.py` 의 `status`·`chain status` 밖 동작(라운드 띄우기·모드 바꾸기는 엔진과 사람 몫),
  `kill`/`pkill`(끊기는 엔진이 표식을 대조해 한다), `monitorctl.sh`(운영 모니터는 사람 몫), `node`·`timeout`·`cd`
  (아무 명령이나 감싸 돌리는 통로), `python3 projects/`(프로젝트 코드는 검사로 돌린다), `curl`
- 그래도 허용 목록이 넓어질 때를 대비해 `MANAGER_DENIED` 를 `--disallowedTools` 로 따로 건다 (거부가 허용보다 앞선다)
"""
from __future__ import annotations

import datetime
import re
import uuid

from .base import SessionSpec

#: Claude Code 권한 문법 `Bash(<접두>:*)`. 접두 뒤가 무엇이든 허용한다 - 그래서 접두를 도구 파일 이름까지 적는다.
MANAGER_TOOLS = ",".join([
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(python3 tools/fleet.py:*)", "Bash(python3 tools/fleet_graph.py:*)",
    "Bash(python3 tools/fleet_ctl.py status:*)", "Bash(python3 tools/fleet_ctl.py chain status:*)",
    "Bash(python3 tools/aimem_db.py:*)", "Bash(python3 tools/aimem_board.py:*)",
    "Bash(python3 tools/aimem_lint.py:*)",
    # 표준 브리프가 시키는 일: 노드의 verify 를 붙이기 전에 검사를 한 번 돌려 본다
    "Bash(python3 -m unittest:*)", "Bash(PYTHONPATH=tools python3 -m unittest:*)",
    # 검사 스크립트는 `Bash(python3 tests/*)` 꼴이어야 한다. `Bash(python3 tests/:*)` 는 낱말 경계에서만 맞아
    # `python3 tests/browser_x.py` 를 허용하지 않는다 (R22 에서 관리자가 브라우저 검사를 못 돌린 까닭, haiku 로 실측).
    "Bash(python3 tests/*)", "Bash(PYTHONPATH=tools python3 tests/*)",
    # 읽기 명령 - 작업자 목록(`harness.claude.WORKER_TOOLS`)의 읽기 쪽과 같다
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(grep:*)",
    "Bash(sed -n:*)", "Bash(diff:*)", "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    "Bash(pwd)", "Bash(mkdir:*)", "Bash(echo:*)", "Bash(sleep:*)",
])

#: 허용 목록과 따로 거는 거부 목록 (`--disallowedTools`) - 위임문이 늘 거절하는 것. 난간이다(머리말).
MANAGER_DENIED = ("Bash(git commit:*),Bash(git push:*),Bash(git reset:*),Bash(git checkout:*),Bash(rm:*),"
                  "Bash(pip:*),Bash(npm install:*),Bash(sudo:*)")

#: 벽시계 제한. 관리자는 그래프가 도는 내내 `fleet_graph.py run` 에 묶여 있으므로 길다.
MANAGER_TIMEOUT_SEC = 6 * 3600
#: 호출 방식(`[manager] mode = "calls"`, 설계 5.9)의 호출 하나의 벽시계 제한. 호출은 작업자를 기다리지 않으므로
#: 상주 관리자보다 훨씬 짧다 - 마감 호출이 전체 검사를 돌리는 시간까지 넉넉히 본 값이다.
CALL_TIMEOUT_SEC = 3600
#: 호출의 단계. ① 계획 ② 판정 ③ 마감 - 브리프는 `.aimem/briefs/manager-call-<단계>.md`
CALL_PHASES = ("plan", "judge", "close")
PHASE_LABEL = {"plan": "① 계획", "judge": "② 판정", "close": "③ 마감"}
MANAGER_MODEL = "opus"
MANAGER_HARNESS = "claude"
#: 관리자 세션 id `M-R<N>-<HHMMSS>` (같은 초에 둘이면 `-2`). 린터·화면이 이 꼴로 관리자를 알아본다.
ID_RE = re.compile(r"\AM-R(\d+)-\d{6}(?:-\d+)?\Z")


def manager_id(n, at=None):
    at = at or datetime.datetime.now()
    return f"M-R{int(n)}-{at.strftime('%H%M%S')}"


def round_of(sid):
    """세션 id 에서 라운드 번호. 관리자 id 꼴이 아니면 None."""
    m = ID_RE.match(str(sid or ""))
    return int(m.group(1)) if m else None


def label(n, at=None, phase=None):
    at = at or datetime.datetime.now()
    head = f"관리자 R{int(n)}" + (f" {PHASE_LABEL[phase]}" if phase else "")
    return f"{head} (Opus) {at.strftime('%Y-%m-%d')}"


def spec(sid, n, cwd, *, at=None, by="사람", brief="", workspace="", provider="anthropic", phase=None):
    """관리자 세션 명세. 침묵 제한은 두지 않는다 - 그래프가 도는 동안 관리자는 정당하게 오래 말이 없다.

    `phase` 를 주면 호출 방식의 호출 하나다(`plan|judge|close`): `extra.phase` 에 적고 벽시계 제한이 짧다.
    도구·거부 목록은 상주 관리자와 같다 - 호출이라고 권한이 달라지지 않는다.
    """
    extra = {"harness_session_id": str(uuid.uuid4()), "by": str(by)[:60], "brief": brief,
             "workspace": workspace, "disallowed_tools": MANAGER_DENIED}
    if phase is not None:
        if phase not in CALL_PHASES:
            raise ValueError(f"관리자 호출 단계가 올바르지 않습니다: {phase!r}")
        extra["phase"] = phase
    return SessionSpec(
        id=sid, role="manager", harness=MANAGER_HARNESS, brief_path="", cwd=str(cwd),
        model=MANAGER_MODEL, provider=provider, round=int(n),
        label=label(n, at, phase),
        timeout=float(MANAGER_TIMEOUT_SEC if phase is None else CALL_TIMEOUT_SEC), idle_timeout=None, tools=MANAGER_TOOLS,
        settings_path=None, extra=extra)
