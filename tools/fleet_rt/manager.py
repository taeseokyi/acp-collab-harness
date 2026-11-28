"""관리자 세션 명세 (설계 `docs/FLEET-ENGINE-V2.md` 3.3·3.4).

관리자는 `role="manager"` 인 claude 세션일 뿐이다. 엔진(`fleet_ctl.launch_round`)이 `sessions.spawn` 으로 직접
띄우고, 여기에는 그 명세를 만드는 것만 둔다 - 의존 방향은 fleet_ctl -> fleet_rt 이라 `fleet` 은 들이지 않는다.

관리자의 도구는 작업자와 같다 - Bash 를 통째로 허용하고 거부 목록을 걸지 않는다 (태석님 2026-11-28: "관리자에게 더 많은
권한을 위임하고 싶어. 지나가는 난간은 필요없어"). 전에는 명령 접두사 목록과 거부 목록이 있었는데 **보안 경계가 아니었다**:
`Write` 와 `python3 -m unittest` 로 아무 코드나 돌릴 수 있었고, 목록은 명령을 잇는 방식(`;`·`$(…)`·`for`)에 걸려 관리자의
헛걸음만 만들었다(R55 7건). 관리자가 무엇을 해도 되는지는 도구가 아니라 위임문과 `AIMEM.md`·브리프가 정한다.
"""
from __future__ import annotations

import datetime
import re
import uuid

from .base import DEFAULT_IDLE_TIMEOUT_SEC, SessionSpec

MANAGER_TOOLS = "Read,Edit,Write,Glob,Grep,Bash"

MANAGER_MODEL = "opus"
MANAGER_HARNESS = "claude"
#: 관리자 세션 id `M-R<N>-<HHMMSS>` (같은 초에 둘이면 `-2`). 린터·화면이 이 꼴로 관리자를 알아본다.
ID_RE = re.compile(r"\AM-R(\d+)-\d{6}(?:-\d+)?\Z")


def manager_id(n, at=None):
    at = at or datetime.datetime.now()
    return f"M-R{int(n)}-{at.strftime('%H%M%S')}"


def label(n, at=None):
    at = at or datetime.datetime.now()
    return f"관리자 R{int(n)} ({MANAGER_MODEL.capitalize()}) {at.strftime('%Y-%m-%d')}"


def spec(sid, n, cwd, *, at=None, by="사람", brief="", workspace="", provider="anthropic"):
    """관리자 세션 명세. 작업자와 같은 기준이다 - 벽시계 한도는 없고 멈췄을 때만(침묵) 끊는다.
    그래프가 도는 동안 관리자는 정당하게 오래 말이 없으므로, 감독은 도는 작업자가 있으면 침묵으로 치지 않는다(`run.py`)."""
    extra = {"harness_session_id": str(uuid.uuid4()), "by": str(by)[:60], "brief": brief,
             "workspace": workspace}
    return SessionSpec(
        id=sid, role="manager", harness=MANAGER_HARNESS, brief_path="", cwd=str(cwd),
        model=MANAGER_MODEL, provider=provider, round=int(n), label=label(n, at),
        idle_timeout=DEFAULT_IDLE_TIMEOUT_SEC, tools=MANAGER_TOOLS,
        settings_path=None, extra=extra)


#: 이어 간 관리자 세션의 라벨 꼬리 - 몇 번 이어도 한 번만 붙인다
RESUMED_SUFFIX = " (이어 감)"


def resume_spec(old_meta, new_id, resume_session):
    """끊긴 관리자 세션(`meta.json`)을 같은 대화로 잇는 새 세션의 명세.

    라운드·모델·도구·거부 목록·침묵 한도·공급자는 처음 것을 그대로 쓴다 - 이었다고 권한이 달라지지 않게.
    `extra.resume_session` 이 하네스 어댑터에 `--resume` 을 시키고, 이은 뒤의 대화 id 도 같은 것으로 적어 둔다
    (다음에 또 끊기면 그 id 로 다시 잇는다).
    """
    spec = SessionSpec.from_dict(dict(old_meta))
    spec.id = str(new_id)
    spec.brief_path = ""
    spec.label = str(spec.label or new_id)
    if not spec.label.endswith(RESUMED_SUFFIX):
        spec.label += RESUMED_SUFFIX
    extra = dict(spec.extra or {})
    extra.update({"resume_session": str(resume_session), "harness_session_id": str(resume_session),
                  "resumed_from": str(old_meta.get("id") or "")})
    spec.extra = extra
    return spec
