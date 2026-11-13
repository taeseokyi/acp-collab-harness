"""함대 런타임 규약 - 하네스 어댑터와 세션 감독이 주고받는 자료 꼴.

이 파일이 `fleet_rt` 의 **정본 규약**이다. 어댑터(`harness/*.py`)와 감독(`sessions.py`, `run.py`)은
이 파일의 이름과 뜻만 보고 짠다. 표준 라이브러리만 쓴다.

세션 폴더 (`<aimem>/sessions/<id>/`, `<aimem>` 은 `fleet.RUNS.parent`):

    meta.json     세션 명세 + 감독 프로세스 pid·pgid·시작 시각 (spawn 이 쓴다, 뒤에 안 바뀐다)
    brief.md      받은 지시문 전문
    events.jsonl  하네스 stdout 을 한 줄씩. 줄 꼴은 `<받은 시각 ISO>\\t<하네스가 낸 원문 한 줄>`
    stderr.log    하네스 stderr 원문
    report.md     끝난 뒤 `Harness.final_report()` 가 뽑은 마지막 답
    end.json      끝남 기록 `{"state","rc","ended","fail_kind","why"}` - **이 파일이 있으면 끝난 세션이다**

상태의 정본은 세션 폴더다(`meta.json` + `end.json`). DB `sessions` 표는 감독 프로세스가 시작·끝에
같이 적는 색인이고, 폴더를 훑어 다시 만들 수 있다.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
from typing import Optional, Protocol

#: 프로젝트 이름 = `projects/` 아래 폴더 하나의 이름 (정의는 여기 한 곳)
PROJECT_NAME_RE = r"\A[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]{0,39}\Z"

ROLES = ("manager", "worker", "reviewer")

#: 끝난 상태. `running` 과 `lost`(end.json 없이 감독 프로세스가 사라짐)는 폴더에서 추론한다.
#:   done     하네스가 rc 0 으로 끝남
#:   failed   하네스가 rc != 0 으로 끝남
#:   killed   사람·엔진이 끊음 (cancel)
#:   timeout  벽시계 제한을 넘겨 감독이 끊음
#:   stalled  idle_timeout 동안 사건도 읽기(`/proc/<pid>/io`)도 없어 감독이 끊음
END_STATES = ("done", "failed", "killed", "timeout", "stalled")
STATES = ("running",) + END_STATES + ("lost",)

#: 실패의 종류 (그래프의 재시도 정책이 본다). 감독이 정하는 것은 infra/timeout/limit 뿐이고,
#: `work`(보고가 BLOCKED·검증 실패)는 그래프 실행기가 보고를 읽고 정한다.
FAIL_KINDS = ("work", "infra", "limit", "timeout")

#: 노드 한 시도의 벽시계 한도 기본(초) - 그래프 실행기·spawn·SessionSpec 이 같은 값을 쓴다.
DEFAULT_NODE_TIMEOUT_SEC = 1800.0
#: TERM 뒤 KILL 까지 기다리는 시간 - 감독이 하네스에, cancel·고아 청소가 pid 에 같은 유예를 준다.
TERM_GRACE_SEC = 3.0

#: 사용 한도 문구 - 세 어댑터가 오류 사건·결과 글에 같은 식 하나를 쓴다.
LIMIT_RE = re.compile(r"\b429\b|rate[\s_-]?limit|quota|usage[\s_-]?limit|too many requests"
                      r"|(?:hour|weekly|session) limit|hit your (?:[\w-]+ )?limit", re.I)

#: 보고문 없이 끝난 세션의 보고 머리 (어댑터 `final_report` 가 stderr 꼬리 앞에 붙인다).
NO_REPORT = "(최종 보고문 없음 - 작업자가 보고 전에 끝남. stderr 꼬리:)"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_NOISE_RE = re.compile(r"^\s*(←|✗|!|\||\+|-|@|\$|>|codex$|tokens used|Reading additional)")

# 보고 첫 줄의 상태 읽기: 앞 장식(인용·목록·제목·코드·BOM)과 `상태:`/`Status:` 라벨(앞 낱말 두 개까지)을 벗긴다.
_STATUS_JUNK = r"(?:\s|[*#>`\[\]﻿-]|\d+\.)*"
_STATUS_JUNK_RE = re.compile(_STATUS_JUNK)
_STATUS_PREFIX = re.compile(
    rf"^{_STATUS_JUNK}(?P<label>(?:[^\W\d_]{{1,20}}\s*){{0,2}}?(?:상태|(?i:status))\s*[:：])?{_STATUS_JUNK}")
_STATUS_WORD_SRC = r"(DONE|PARTIAL|BLOCKED|REJECT|NEEDS-[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)*)(?![A-Za-z0-9_-])"
# 라벨이 없으면 대문자만 받는다 - `Blocked 링크 …` 같은 평문이 상태로 읽히지 않게(뒤가 `:`·줄 끝이면 대소문자 무관).
_STATUS_WORD = re.compile(_STATUS_WORD_SRC)
_STATUS_WORD_LABELED = re.compile(_STATUS_WORD_SRC, re.IGNORECASE)
_STATUS_WORD_TERMINATED = re.compile(_STATUS_WORD_SRC + r"[*`\]]*\s*(?:[:：\-–—]|$)", re.IGNORECASE)


def parse_status(report_text):
    """보고 첫 비어 있지 않은 줄의 상태 낱말(대문자) - DONE/PARTIAL/BLOCKED/REJECT/NEEDS-*. 없으면 None."""
    line = next((ln for ln in str(report_text or "").splitlines() if ln.strip()), None)
    if line is None:
        return None
    w = None
    m = _STATUS_PREFIX.match(line)
    if m and m.group("label"):
        w = _STATUS_WORD_LABELED.match(line[m.end():])
    if not w:
        body = line[_STATUS_JUNK_RE.match(line).end():]
        w = _STATUS_WORD.match(body) or _STATUS_WORD_TERMINATED.match(body)
    return w.group(1).upper() if w else None


def require_repo_cwd(cwd, harness):
    """진짜 하네스는 함대 저장소(`tools/fleet.py` 가 있는 폴더)에서만 띄운다 - /tmp 검수 사본에서 작업자가 뜨지 않게."""
    p = pathlib.Path(str(cwd or ""))
    if not cwd or not p.is_dir() or not (p / "tools" / "fleet.py").is_file():
        raise ValueError(f"함대 저장소가 아닌 작업 폴더에서는 {harness} 를 띄우지 않는다: {cwd!r}")
    return p


def one_line(s, n=120):
    """공백을 하나로 접은 한 줄, `n` 자를 넘으면 말줄임."""
    s = " ".join(str(s if s is not None else "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def no_report_tail(session_dir, extra=()):
    """보고문 없이 끝난 세션의 보고: stderr 에서 색 코드·도구 로그를 걷어낸 꼬리 25줄 + `extra` 줄. 없으면 빈 글."""
    try:
        err = (pathlib.Path(session_dir) / "stderr.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        err = ""
    kept = [ln for ln in _ANSI_RE.sub("", err).splitlines() if ln.strip() and not _NOISE_RE.match(ln)]
    tail = "\n".join(kept[-25:] + [str(x) for x in extra]).strip()
    return f"{NO_REPORT}\n{tail}" if tail else ""

EVENT_KINDS = ("text", "tool", "usage", "error", "end", "raw")

#: 모든 세션의 환경에 넣는 표식. 고아 청소가 이것으로 함대 프로세스를 알아본다.
ENV_SESSION = "AIFLEET_SESSION"
ENV_ROLE = "AIFLEET_ROLE"
#: 이 변수가 `fake` 면 어댑터 선택이 무조건 `fake` 를 준다 (검사에서 진짜 하네스 금지).
ENV_FORCE_HARNESS = "AIFLEET_HARNESS"


#: DB `sessions` 표 (색인). 정의는 여기 한 곳 - `aimem_db.SCHEMA` 와 감독 프로세스가 같이 쓴다.
SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY,
  role TEXT NOT NULL,
  round INTEGER, task_id TEXT, slot TEXT,
  harness TEXT NOT NULL, model TEXT, provider TEXT,
  pid INTEGER, pgid INTEGER, harness_session_id TEXT,
  state TEXT NOT NULL,
  started TEXT, ended TEXT, last_event_at TEXT,
  rc INTEGER, report_status TEXT,
  tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL,
  fail_kind TEXT,
  attempt INTEGER, label TEXT, write_paths TEXT, dir TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id);
"""
SESSION_COLUMNS = ("id", "role", "round", "task_id", "slot", "harness", "model", "provider", "pid", "pgid",
                   "harness_session_id", "state", "started", "ended", "last_event_at", "rc", "report_status",
                   "tokens_in", "tokens_out", "cost_usd", "fail_kind", "attempt", "label", "write_paths", "dir")

#: 고아 청소가 '어느 저장소의 세션인가' 를 가리는 표식 (세션 폴더들의 부모 경로). 임시 폴더 검사의 세션을 운영이 죽이지 않게.
ENV_ROOT = "AIFLEET_SESSIONS_ROOT"


def service_env(environ=None):
    """세션 표식을 뺀 환경. 엔진이 **오래 사는 배경 프로세스**(그래프 실행기·이어 달리기 감시·모니터)를 띄울 때 쓴다.

    세션 안에서(관리자·작업자가) 그런 프로세스를 띄우면 표식이 상속되어, 그 세션을 정리할 때
    '세션의 남은 프로세스' 로 보여 같이 끝난다 (2026-11-12 적대적 검수 7번).
    """
    import os
    env = dict(os.environ if environ is None else environ)
    for k in (ENV_SESSION, ENV_ROLE, ENV_ROOT):
        env.pop(k, None)
    return env


@dataclasses.dataclass
class SessionSpec:
    """세션 하나를 띄우는 데 필요한 것 전부. `meta.json` 에 그대로 적힌다."""
    id: str                                  # 'T-263-S2-a1-193012' (작업자) / 'M-R21-193012' (관리자)
    role: str                                # ROLES
    harness: str                             # 'claude' | 'codex' | 'opencode' | 'fake'
    brief_path: str                          # 지시문 파일 (세션 폴더의 brief.md)
    cwd: str                                 # 하네스의 작업 폴더 (저장소 루트)
    slot: Optional[str] = None
    model: Optional[str] = None              # 슬롯에 적힌 꼴 ('opus', 'kisti/kistillm'). 어댑터가 하네스 꼴로 바꾼다
    provider: Optional[str] = None           # fleet.toml 의 공급자 이름 ('kisti', 'anthropic')
    ident: str = ""                          # 지시문 머리말 한 줄 (슬롯·확인토큰·REV). stdin 을 못 받는 하네스가 메시지 앞에 붙인다
    write_paths: list = dataclasses.field(default_factory=list)
    tools: Optional[str] = None              # 허용 도구 목록 (claude `--allowedTools`). None 이면 어댑터의 역할별 기본
    settings_path: Optional[str] = None      # 하네스 설정 파일 (claude `--settings`)
    timeout: float = DEFAULT_NODE_TIMEOUT_SEC   # 벽시계 제한(초)
    idle_timeout: Optional[float] = None     # 침묵 제한(초). None 이면 침묵 감지를 안 한다
    round: Optional[int] = None
    task_id: Optional[str] = None
    attempt: int = 1
    label: str = ""
    extra: dict = dataclasses.field(default_factory=dict)   # 표시용 (project, rev, date …). 감독은 해석하지 않는다

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclasses.dataclass
class Command:
    """하네스를 띄우는 명령. 감독이 `Popen(argv, cwd=cwd, env=…, stdin=stdin_path)` 로 쓴다.

    지시문 본문은 **argv 에 넣지 않는다**(stdin 이나 '이 파일을 읽어라' 로) - 본문이 명령줄에 실리면
    `pkill -f` 같은 패턴이 자기 자신에 걸린다 (2026-11-09 실측).
    """
    argv: list
    cwd: str
    stdin_path: Optional[str] = None                             # None 이면 stdin 은 /dev/null
    env_set: dict = dataclasses.field(default_factory=dict)      # 더할 환경변수
    env_unset: tuple = ()                                        # 지울 환경변수 이름


@dataclasses.dataclass
class Event:
    """하네스 출력 한 줄을 푼 공통 사건.

    kind:
      text   모델의 말.              text = 본문
      tool   도구 호출.              text = 한 줄 요약('Bash: ls tools'), data = {"name", "input"…}
      usage  토큰·비용.              data = {"tokens_in", "tokens_out", "cost_usd"} (아는 것만)
      error  재접속·한도·시간 초과.   text = 사람이 읽을 한 줄, data = {"limit": bool, "retry": bool …}
      end    하네스가 스스로 알린 끝. data = {"ok": bool, "result": 마지막 답(있으면), "harness_session_id"…}
      raw    어댑터가 모르는 줄.     버리지 않고 남긴다 (하네스 판이 바뀌었을 때 보려고)
    """
    kind: str
    text: str = ""
    data: dict = dataclasses.field(default_factory=dict)
    raw: str = ""


@dataclasses.dataclass
class ProbeResult:
    ok: bool
    binary: Optional[str] = None      # 찾은 실행 파일 경로
    version: Optional[str] = None
    detail: str = ""                  # ok 가 아니면 까닭 한 줄


class Harness(Protocol):
    """하네스 어댑터. 상태를 갖지 않는다 - 모든 메서드는 인자만 보고 답한다."""
    name: str

    def command(self, spec: SessionSpec) -> Command:
        """비대화·사건 흐름 꼴로 띄우는 명령. `spec.cwd` 가 저장소 밖이면 `ValueError`(진짜 어댑터만)."""

    def parse_event(self, line: str) -> Optional[Event]:
        """하네스 stdout 한 줄(받은 시각 접두 없는 원문) → 사건. 빈 줄은 None, 모르는 줄은 kind='raw'."""

    def final_report(self, session_dir: pathlib.Path) -> str:
        """마지막 답(보고 본문). 없으면 stderr 꼬리로 만든 '(최종 보고문 없음 …)' 또는 빈 문자열."""

    def limit_signal(self, session_dir: pathlib.Path) -> Optional[bool]:
        """사용 한도에 걸려 끝났나. 모르면 None. 감독이 rc != 0 일 때 보고 end.json `fail_kind: limit` 로 적는다."""

    def resume_command(self, spec: SessionSpec, harness_session_id: str, message_path: str) -> Optional[Command]:
        """끝난 세션에 한 턴 더. 못 하는 하네스는 None (지금은 claude 만 한다)."""

    def probe(self) -> ProbeResult:
        """준비 점검: 실행 파일이 있고 버전을 답하는가. 공급자 응답은 `providers.py` 가 따로 본다."""


def read_event_lines(session_dir, tail=None):
    """`events.jsonl` 을 (받은 시각, 원문) 쌍으로. `tail` 이 있으면 끝의 그만큼만."""
    p = pathlib.Path(session_dir) / "events.jsonl"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if tail:
        lines = lines[-int(tail):]
    out = []
    for ln in lines:
        at, sep, raw = ln.partition("\t")
        out.append((at, raw) if sep else ("", ln))
    return out
