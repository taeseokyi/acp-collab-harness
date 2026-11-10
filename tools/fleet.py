#!/usr/bin/env python3
"""작업자 운영 도우미 (관리자 전용).

`AIMEM.md` `8.0` 의 **ACP 일회성 자식** 체제(2026-11-09, claude/codex/opencode)를
전제합니다. 판단은 사람이 하고, 이 도구는 옮겨 적는 일과 대조만 합니다.

  python3 tools/fleet.py status              # REV / 슬롯 / 열린 태스크 / 미커밋
  python3 tools/fleet.py brief --slot S1 ... # 브리프 머리말 + 쓰기 경로 6절 대조
  python3 tools/fleet.py close               # 거두기 전 점검
  python3 tools/fleet.py children            # ACP 자식 세션 + 실행 모델(하네스 설정 기준)

2026-09-22 (REV 91) 에 `open` / `prepare` 를 폐기했습니다. 둘 다 상주 슬롯을
여는 절차(`8.5`)의 도우미였고, 지금은 관리자가 일회성 자식을 직접 띄웁니다.
2026-11-09 (REV 107) 부터 자식은 ACP 하네스이고 `brief` 가 스폰 호출문을 같이 찍습니다.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
AIMEM = ROOT / "AIMEM.md"


def sh(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


# --------------------------------------------------------------- 운영 상태 (DB 우선, 마크다운 폴백)
#
# 2단계(REV 114~)에서 명부·보드·소유권·REV 의 정본은 `.aimem/aimem.db` 다. `AIMEM.md`
# 2·3·4.5·6절의 표는 내려갔고 `AIMEM-state.md` 는 읽기 전용 스냅샷이다.
#
# **마크다운 폴백은 지금 빈 값을 돌려준다.** 표가 사라졌으니 당연하다 - 전환 중
# (REV 113)에만 쓸모가 있었다. 남겨 두는 이유는 두 가지뿐이다: (1) REV 113 이전
# 커밋을 체크아웃하면 표가 있고 그때는 실제로 동작한다, (2) 폴백이 빈 값을 주면
# `spawn` 이 **거절**한다(fail-closed) - 소유가 아닌 파일에 쓰게 되는 길은 없다.
# 그러니 "DB 가 깨져도 작업자를 띄울 수 있다" 고 기대하지 말 것. 띄울 수 없고,
# `_roster_miss()` 가 그 사실을 말한다 (S4 검수 5번).
#: (읽은 시각, 상태) 캐시. **실패는 캐시하지 않고 성공에도 TTL 을 둡니다** -
#: `fleet_graph run` 은 한 프로세스로 수십 분 돌기 때문입니다. 실패를 영구
#: 캐시했더니 첫 읽기에서 `database is locked` 한 번만 나도 그 실행 내내
#: `roster()` 가 `{}` 여서 **모든 노드가 "명부에 없음" 으로 실패**했습니다
#: (S4 검수 4번 실측). 같은 이유로 성공값도 고정하지 않습니다 - 도는 중에
#: `ownership` 이 바뀌면 반영돼야 합니다.
_DB_CACHE = {"at": 0.0, "state": None}
DB_CACHE_TTL_SEC = 5.0


def db_state():
    """`.aimem/aimem.db` 의 운영 상태. 읽지 못하면 `None` (호출자가 마크다운으로 내려간다)."""
    now = time.monotonic()
    if _DB_CACHE["state"] is not None and now - _DB_CACHE["at"] < DB_CACHE_TTL_SEC:
        return _DB_CACHE["state"]
    state = None
    try:
        # `python3 -m tools.fleet_graph` 나 `PYTHONPATH=.` 로 부르면 `tools/` 가
        # `sys.path` 에 없어 `import aimem_db` 가 조용히 실패했습니다 (S4 검수 4번
        # 재현 2). 자기 디렉터리를 직접 넣습니다.
        here = str(pathlib.Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import aimem_db  # noqa: PLC0415 - 지연 import. 없어도 폴백으로 돈다
        if aimem_db.DB.exists():
            state = aimem_db.state_dict()
    except Exception as e:  # noqa: BLE001 - DB 문제로 스폰이 막히면 안 된다
        # 조용히 삼키면 "명부에 없습니다" 만 보여 원인을 못 찾습니다.
        print(f"[fleet] .aimem/aimem.db 를 읽지 못했습니다: {type(e).__name__}: {e}", file=sys.stderr)
    _DB_CACHE.update(at=now, state=state)
    return state


def _aimem_lines():
    return AIMEM.read_text(encoding="utf-8").splitlines() if AIMEM.exists() else []


def read_rev():
    s = db_state()
    if s and s.get("rev") is not None:
        return int(s["rev"])
    for line in _aimem_lines():
        m = re.match(r"- \*\*REV: (\d+)\*\*", line)
        if m:
            return int(m.group(1))
    sys.exit("REV 를 찾지 못했습니다 (.aimem/aimem.db 도 AIMEM.md 서문도)")


def roster():
    """슬롯 -> (확인토큰, 하네스, 세션키). 세션키는 일회성 작업자라 늘 빈 문자열입니다."""
    s = db_state()
    if s and s.get("slots"):
        return {r["slot"]: (r["token"], r["harness"], "") for r in s["slots"]
                if re.fullmatch(r"S\d+", r["slot"] or "")}
    out = {}
    for line in _aimem_lines():
        m = re.match(r"\|\s*(S\d)\s*\|\s*`([0-9a-f]+)`\s*\|\s*([^|]*?)\s*\|[^|]*\|\s*([^|]*?)\s*\|", line)
        if m:
            out[m.group(1)] = (m.group(2), m.group(3).strip(), m.group(4).strip())
    return out


def board_rows():
    """(태스크 id, 제목, 담당 슬롯, 상태) 의 리스트."""
    s = db_state()
    if s and s.get("tasks"):
        return [(t["id"], t["title"] or "", t["slot"] or "-", t["status"]) for t in s["tasks"]]
    rows = []
    for line in _aimem_lines():
        m = re.match(r"\|\s*(T-\d+\w*)\s*\|\s*([^|]*?)\s*\|\s*(S\d|-)\s*\|\s*(\w[\w-]*)\s*\|", line)
        if m:
            rows.append(m.groups())
    return rows


def cmd_status(args):
    rev = read_rev()
    lines = len(AIMEM.read_text(encoding="utf-8").splitlines())
    print(f"AIMEM.md  REV {rev} / {lines}줄")
    print()
    print("슬롯:")
    for slot, (token, harness, key) in sorted(roster().items()):
        print(f"  {slot}  {token}  {harness:<9} {key or '(비어 있음)'}")
    open_rows = [r for r in board_rows() if r[3] not in ("DONE", "상태")]
    print()
    print(f"열린 태스크 {len(open_rows)}건" if open_rows else "열린 태스크 없음")
    for tid, name, slot, st in open_rows:
        print(f"  {tid}  {st:<12} {slot}  {name}")
    dirty = sh("git", "status", "--short").stdout.strip()
    print()
    print("미커밋:\n" + ("\n".join("  " + l for l in dirty.splitlines()) if dirty else "  (없음)"))


def cmd_close(args):
    """종료 전 점검. 파일을 고치지 않고, 사람이 할 일을 짚어 줍니다."""
    problems = []
    rows = board_rows()
    stuck = [r for r in rows if r[3] not in ("DONE", "TODO", "상태")]
    if args.slot:
        stuck = [r for r in stuck if r[2] == args.slot]
    for tid, name, slot, st in stuck:
        problems.append(
            f"보드 {tid}({slot}) 가 {st} 입니다. TODO 로 되돌리십시오 - "
            f"python3 tools/aimem_board.py board-set {tid} TODO"
        )
    dirty = sh("git", "status", "--short").stdout.strip()
    if dirty:
        problems.append("미커밋이 있습니다. 커밋해야 작업자의 git 앵커가 살아납니다:\n    "
                        + "\n    ".join(dirty.splitlines()))
    # 거두지 않은 ACP 일회성 자식이 남아 있는지 (`8.0`. 정상이면 턴 끝에 사라집니다).
    # 조회에 실패하면 조용히 넘어갑니다 -
    # 게이트웨이가 안 떠 있어도 나머지 점검은 쓸모가 있습니다.
    try:
        res = sh("openclaw", "gateway", "call", "sessions.list", "--json")
    except OSError:
        res = None  # openclaw 바이너리가 PATH 에 없는 환경(cron 등)
    if res is not None and res.returncode == 0:
        try:
            payload = json.loads(res.stdout)
        except ValueError:
            payload = None
        sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
        if not isinstance(sessions, list):
            sessions = []
        left = [s.get("key", "") for s in sessions
                if isinstance(s, dict) and ":acp:" in s.get("key", "")]
        for key in left:
            problems.append(f"ACP 세션이 남아 있습니다: {key}\n    "
                            f"openclaw gateway call sessions.delete "
                            f"--params '{{\"key\":\"{key}\"}}' --timeout 60000 --json")
    if not problems:
        print("종료 준비 완료. 걸리는 것 없습니다.")
        return 0
    print("종료 전에 정리할 것:")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    return 1


HARNESSES = ("claude", "codex", "opencode")
# 슬롯별 기본 모델 (태석님 2026-11-09 17:45). claude 하네스는 슬롯마다 다른 모델을 쓴다:
# S1 = opus(=claude-opus-5-5, 판단 비중 큰 일), S4 = sonnet(=claude-sonnet-5-5, 속도용 병렬 작업자).
# codex·opencode 는 하네스 설정(kistillm)을 그대로 쓴다. `spawn --model` 이 이 표보다 우선한다.
SLOTS_FILE = ROOT / "tools" / "fleet_slots.json"   # 슬롯별 모델 정본. `fleet.py slot add/set` 이 쓴다 (클로 가능)


def _load_slot_models():
    try:
        d = json.loads(SLOTS_FILE.read_text(encoding="utf-8"))
        return {k: v.get("model") for k, v in d.items() if isinstance(v, dict) and v.get("model")}
    except (OSError, ValueError):
        return {"S1": "opus", "S4": "sonnet"}


SLOT_DEFAULT_MODEL = _load_slot_models()
SLOT_MODEL_LABEL = {"opus": "anthropic/claude-opus-5-5", "sonnet": "anthropic/claude-sonnet-5-5", "haiku": "anthropic/claude-haiku-5-5"}


def harness_model(harness):
    """하네스가 실제로 쓰는 모델을 **하네스 설정**에서 읽습니다 (`8.0` 정본).

    `sessions_list` 의 `model` 은 OpenClaw 기본 모델이 찍힌 표기라 ACP 자식에서는
    실행 모델이 아닙니다. 그래서 여기서는 그 값을 아예 읽지 않습니다.
    """
    home = pathlib.Path.home()
    try:
        if harness == "claude":
            # 작업자 Claude 는 `fleet.py spawn` 이 `claude -p --model sonnet` 으로 띄운다(= claude-sonnet-5-5).
            # openclaw.json 의 agents.entries.claude.model 은 **관리자 ACP 세션**(opus) 용이라 여기서 읽지 않는다
            # (11-09 태석님 지적: S4 를 sonnet 으로 배정했는데 opus 로 표시됨).
            per_slot = ", ".join(f"{k}={SLOT_MODEL_LABEL.get(v, v)}" for k, v in SLOT_DEFAULT_MODEL.items())
            return (per_slot, "fleet.py SLOT_DEFAULT_MODEL (관리자 ACP 세션은 openclaw.json entries.claude = opus)")
        if harness == "codex":
            import tomllib
            cfg = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))
            m = cfg.get("model")
            p = cfg.get("model_provider")
            return (f"{p}/{m}" if p and m else m or "(하네스 기본)", "~/.codex/config.toml")
        if harness == "opencode":
            text = (home / ".config" / "opencode" / "opencode.jsonc").read_text(encoding="utf-8")
            mm = re.search(r'^\s*"model"\s*:\s*"([^"]+)"', text, re.M)
            return (mm.group(1) if mm else "(하네스 기본)", "~/.config/opencode/opencode.jsonc")
    except (OSError, ValueError) as e:
        return ("(읽기 실패)", str(e)[:60])
    return ("(알 수 없는 하네스)", "-")


def cmd_children(args):
    """ACP 자식 세션을 하네스 · 실행 모델 · 상태로 보여 줍니다. 읽기 전용입니다."""
    try:
        res = sh("openclaw", "sessions", "--all-agents", "--limit", "all", "--json")
    except OSError:
        sys.exit("openclaw 바이너리를 찾지 못했습니다")
    if res.returncode != 0:
        sys.exit("세션 조회 실패: " + (res.stderr or res.stdout).strip()[:200])
    try:
        payload = json.loads(res.stdout)
    except ValueError:
        sys.exit("세션 조회 결과가 JSON 이 아닙니다")
    sessions = payload.get("sessions", []) if isinstance(payload, dict) else payload
    kids = [s for s in sessions if isinstance(s, dict) and ":acp:" in s.get("key", "")]
    models = {h: harness_model(h) for h in HARNESSES}
    print("실행 모델 정본 = 하네스 설정 (sessions_list.model 은 표기일 뿐, 읽지 않음):")
    for h in HARNESSES:
        m, src = models[h]
        print(f"  {h:<9} {m:<28} <- {src}")
    print()
    if not kids:
        print("ACP 자식 세션 없음")
        return 0
    print(f"ACP 자식 세션 {len(kids)}건:")
    for s in kids:
        h = s.get("agentId") or s.get("key", "").split(":")[1]
        m = models.get(h, ("?", ""))[0]
        if h == "claude":
            m = "(관리자 세션) opus[1m]"
        print(f"  {s.get('label') or '(라벨 없음)':<18} {h:<9} {m:<28} {s.get('status') or '?':<8} {s.get('key')}")
    return 0


def owned_paths(slot):
    """그 슬롯이 쓸 수 있는 경로 패턴. 정본은 DB 의 `ownership`, 폴백은 6절 표입니다."""
    s = db_state()
    if s and s.get("ownership"):
        pats = []
        for r in s["ownership"]:
            path, owner = r["path_pattern"], (r["owner"] or "").strip()
            if owner == slot:
                pats.append(path)
            elif owner == "해당 슬롯":
                pats.append(path.replace("<슬롯>", slot))
        return pats
    pats = []
    for line in _aimem_lines():
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        path, owner = m.group(1), m.group(2)
        if owner == slot:
            pats.append(path)
        elif owner == "해당 슬롯":
            pats.append(path.replace("<슬롯>", slot))
    return pats


def _roster_miss(slot):
    """명부에 없을 때의 종료 메시지. **원인을 구분해 말합니다.**

    예전에는 DB 를 못 읽어도 "명부에 없습니다" 만 나와 진단이 불가능했습니다
    (S4 검수 5번). `AIMEM.md` 의 표는 REV 114 에서 내려갔으므로, DB 를 못 읽으면
    폴백은 **빈 값**이고 그 사실 자체를 말해야 합니다.
    """
    if db_state() is None:
        return (f"{slot} 를 확인할 수 없습니다 - `.aimem/aimem.db` 를 읽지 못했고 "
                "`AIMEM.md` 에는 명부 표가 없습니다(REV 114 에서 내림). "
                "`python3 tools/aimem_db.py migrate` 로 DB 를 복구하십시오.")
    return f"{slot} 가 명부에 없습니다 (`python3 tools/aimem_db.py state` 로 확인하십시오)"


def path_allowed(path, pats):
    """`path` 를 허용하는 패턴, 없으면 `None`.

    **정확한 파일 패턴은 정확히 맞아야 합니다.** 예전에는 무조건
    `fnmatch(path, p.rstrip("*") + "*")` 까지 봐서 `tests/test_aimem_lint.py` 소유자가
    `tests/test_aimem_lint.py.bak` 과 `.pyc` 에도 쓸 수 있었습니다 (S4 검수 7번).
    접두 확장은 **패턴이 `*` 로 끝날 때만** 적용합니다 - `.aimem/archive/**` 같은
    디렉터리 패턴에 `.aimem/archive/x.md` 를 맞추기 위한 장치였습니다.
    """
    import fnmatch
    for p in pats:
        if path == p or fnmatch.fnmatch(path, p):
            return p
        if p.endswith("*") and fnmatch.fnmatch(path, p.rstrip("*") + "*"):
            return p
    return None


def cmd_brief(args):
    """지시문을 만듭니다. 보내기 전에 슬롯/토큰/REV/쓰기경로를 6절과 대조합니다."""
    slot = args.slot
    r = roster()
    if slot not in r:
        sys.exit(_roster_miss(slot))
    token, harness, _key = r[slot]
    # 세션키는 요구하지 않습니다. 일회성 자식은 매번 새 세션이고 명부의 세션키 칸은
    # 비어 있는 것이 정상입니다 (`8.0`). 대조에 쓰는 것은 슬롯 ID / 확인토큰 / REV 입니다.
    if harness not in ("claude", "codex", "opencode"):
        sys.exit(f"{slot} 의 하네스 칸이 ACP 하네스가 아닙니다: {harness!r} (2절을 고치십시오)")
    rev = read_rev()
    pats = owned_paths(slot)

    bad = [w for w in args.write if not path_allowed(w, pats)]
    if bad:
        print(f"지시를 만들지 않았습니다. {slot} 소유가 아닌 경로입니다:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        print(f"  {slot} 소유: {', '.join(pats) or '(없음)'}", file=sys.stderr)
        return 2

    print(f"# 스폰: sessions_spawn(runtime:\"acp\", agentId:\"{harness}\", mode:\"run\", "
          f"context:\"isolated\", label:\"{slot} ...\", task:<아래 본문>)")
    print(f"슬롯 {slot} / 확인토큰 {token} / 하네스 {harness} / AIMEM REV {rev}")
    if args.task:
        print(f"쓰기는 {', '.join(args.write)} 에만 하십시오." if args.write else "")
        print()
        print(args.task)
    print()
    print("보고는 이 응답 본문에 직접 쓰십시오. 아웃박스에 쓰지 마십시오.")
    print()
    print(f"# 쓰기 경로 {len(args.write)}건 전부 6절상 {slot} 소유")
    return 0


# ---------------------------------------------------------------------------
# REV 109: 작업자를 관리자가 **하네스 CLI 로 직접** 띄웁니다 (게이트웨이 스폰 아님).
# 관리자(Claude ACP 세션)는 `spawn` 으로 여러 작업자를 한 번에 내보내고 `wait` 로 거둡니다.
# 기록은 `.aimem/runs/<id>.*` (brief.md / out / err / rc / json). 재생성 가능하므로 .gitignore.
# 원칙(태석님 2026-11-09 17:30): 작업자는 단위 업무마다 백지에서 시작하고 끝나면 컨텍스트를 비운다 -
# CLI 일회성 프로세스라 메모리는 저절로 비워지고, codex 는 --ephemeral 로 세션 파일도 남기지 않는다.
# 관리자만 예외다(컨텍스트 유지).
# ---------------------------------------------------------------------------
RUNS = ROOT / ".aimem" / "runs"
_CLAUDE_NESTED_ENV = ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID",
                      "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                      "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH")
# 작업자 Claude 에 허용하는 도구. 편집은 자동 승인(acceptEdits), 셸은 읽기·검증 명령만.
# commit/push/rm/설치는 AIMEM 0.2 하드리밋이라 목록에 없습니다 - 필요하면 NEEDS-APPROVAL 로 올립니다.
_CLAUDE_WORKER_TOOLS = ",".join([
    "Read", "Edit", "Write", "Glob", "Grep",
    # Claude Code 권한 규칙의 접두사 문법은 `Bash(cmd:*)` (콜론) 이다. 공백 별표는 글자 그대로 비교되어
    # 아무것도 허용하지 않는다 (11-09 T-036 S1 이 python3 을 한 번도 못 돌린 원인).
    "Bash(python3:*)", "Bash(python:*)", "Bash(pytest:*)",
    # 환경변수 접두사가 붙은 호출은 별도 규칙이 필요하다 (`PYTHONPATH=tools python3 ...` 가 11-09 두 번 막힘)
    "Bash(PYTHONPATH=tools python3:*)", "Bash(PYTHONPATH=tools python:*)", "Bash(PYTHONPATH=. python3:*)",
    "Bash(PYTHONPYCACHEPREFIX=/tmp/pyc python3:*)", "Bash(node:*)", "Bash(npm test:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(grep:*)",
    "Bash(sed -n:*)", "Bash(pwd)", "Bash(mkdir:*)", "Bash(diff:*)", "Bash(git status:*)",
    "Bash(git diff:*)", "Bash(git log:*)", "Bash(curl:*)", "Bash(cd:*)", "Bash(echo:*)",
    "Bash(timeout:*)", "Bash(sleep:*)", "Bash(ss:*)", "Bash(kill:*)",
])


def normalize_model(harness, model):
    """슬롯에 적힌 모델(openclaw 키 `provider/model` 또는 claude 별칭)을 하네스가 받는 꼴로.
    claude CLI 는 `claude-opus-5-5`(id) 또는 `opus`(별칭) - `anthropic/` 접두는 뗀다. opencode 는 `provider/model` 그대로.
    codex 는 호출부에서 `-m model -c model_provider=provider` 로 쪼갠다."""
    if not model:
        return model
    m = str(model).strip()
    if harness == "claude":
        if m.startswith("anthropic/"):
            m = m[len("anthropic/"):]
        if m.startswith("claude-cli/"):
            m = m[len("claude-cli/"):]
    return m


def _worker_argv(harness, model, brief_path):
    """하네스별 비대화식 실행 명령. **브리프 본문은 argv 에 넣지 않습니다** - stdin 이나 파일 경로로 넘깁니다.
    (11-09 R-002/N3: 브리프에 든 `aimem_monitor` 글자가 작업자 argv 에 있어 `pkill -f aimem_monitor` 로
    작업자가 자기 자신을 죽였다. 경로만 넘기면 그런 자기 참조가 없다.)
    돌려주는 값은 (argv, stdin_path) 이고 stdin_path 가 None 이 아니면 그 파일을 표준입력으로 붙입니다."""
    brief_path = str(brief_path)
    model = normalize_model(harness, model)
    if harness == "codex":
        argv = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-C", str(ROOT), "--sandbox", "workspace-write"]
        if model:
            # openclaw 키 `kisti/kistillm` → codex 는 모델과 공급자를 따로 받는다 (config.toml 의 model_provider 이름과 같다)
            prov, _, mid = model.rpartition("/")
            argv += ["-m", mid]
            if prov:
                argv += ["-c", f"model_provider={prov}"]
        return argv + ["-"], brief_path  # `-` = 프롬프트를 stdin 에서 읽는다
    if harness == "opencode":
        argv = ["opencode", "run"]
        if model:
            argv += ["-m", model]
        rel = str(pathlib.Path(brief_path).resolve().relative_to(ROOT)) if str(brief_path).startswith(str(ROOT)) else brief_path
        return argv + [f"다음 파일을 읽고 그 안의 지시를 그대로 수행하라(파일 자체는 수정하지 말라): {rel}"], None
    if harness == "claude":
        # 관리자가 Claude 세션이므로 작업자 Claude 는 중첩 표식을 지우고 띄웁니다. 프롬프트는 stdin.
        return ["env"] + [f"-u{k}" for k in _CLAUDE_NESTED_ENV] + [
            "claude", "-p", "--model", model or "sonnet", "--output-format", "json",
            "--permission-mode", "acceptEdits", "--allowedTools", _CLAUDE_WORKER_TOOLS], brief_path
    sys.exit(f"알 수 없는 하네스: {harness}")


def _run_meta(run_id):
    f = RUNS / f"{run_id}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _run_last_mtime(run_id):
    """실행 기록 파일들 중 가장 늦은 수정 시각 - lost 실행의 '끝난 시각' 으로 쓴다."""
    import datetime
    lost = RUNS / f"{run_id}.lost"
    if lost.exists():
        try:
            return datetime.datetime.fromisoformat(json.loads(lost.read_text(encoding="utf-8"))["ended"])
        except (ValueError, KeyError, OSError):
            pass
    ts = [f.stat().st_mtime for f in RUNS.glob(f"{run_id}.*") if f.suffix not in (".seen", ".lost")]
    return datetime.datetime.fromtimestamp(max(ts)) if ts else None


def _run_state(run_id):
    rc = RUNS / f"{run_id}.rc"
    if (RUNS / f"{run_id}.lost").exists():
        return "lost", None
    if rc.exists():
        try:
            return "done", int(rc.read_text().strip() or "-1")
        except ValueError:
            return "done", -1
    meta = _run_meta(run_id) or {}
    pid = meta.get("pid")
    # 깨진 메타(`pid` 가 문자열·bool·음수)는 `os.kill` 에 넣지 않습니다 - 예전엔 `TypeError` 하나로
    # `fleet_graph progress/status/list` 가 통째로 죽었고, 음수는 프로세스 그룹에 신호를 보내는 뜻입니다.
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        try:
            import os
            os.kill(pid, 0)
            return "running", None
        except (OSError, OverflowError):
            return "lost", None
    return "unknown", None


def run_report(run_id):
    """작업자의 보고 본문만 뽑습니다 (하네스별 로그 머리말·JSON 포장 제거)."""
    meta = _run_meta(run_id) or {}
    out_f = RUNS / f"{run_id}.out"
    out = out_f.read_text(encoding="utf-8", errors="replace") if out_f.exists() else ""
    h = meta.get("harness")
    if h == "claude":
        try:
            d = json.loads(out)
            return (d.get("result") or "").strip()
        except ValueError:
            return out.strip()
    if h == "opencode":
        lines = [l for l in out.splitlines() if not re.match(r"^\s*>\s*\w+\s*·", l)]
        out = "\n".join(lines).strip()
    else:
        out = out.strip()  # codex exec: stdout = 마지막 메시지, 진행 로그는 stderr
    if out:
        return out
    # 최종 보고문 없이 끝난 경우(11-09 S3: 권한 자동 거부 뒤 종료). stderr 에서 도구 로그를 걷어낸 꼬리를 보여 준다.
    err_f = RUNS / f"{run_id}.err"
    if not err_f.exists():
        return ""
    err = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", err_f.read_text(encoding="utf-8", errors="replace"))
    kept = [l for l in err.splitlines()
            if l.strip() and not re.match(r"^\s*(←|✗|!|\||\+|-|@|\$|>|codex$|tokens used|Reading additional)", l)]
    tail = "\n".join(kept[-25:]).strip()
    return "(최종 보고문 없음 - 작업자가 보고 전에 끝남. stderr 꼬리:)\n" + tail if tail else ""


#: 프로젝트 이름 = `projects/` 아래 폴더 하나의 이름. `aimem_monitor.PROJECT_NAME_RE` 와 같은 식 (테스트가 대조한다)
PROJECT_NAME_RE = r"\A[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]{0,39}\Z"


def current_round():
    """지금 도는(가장 최근에 띄운) 라운드 번호. 모르면 None.

    `fleet_ctl` 이 라운드를 띄울 때 `.aimem/relay/r<N>.json` 을 남깁니다. 식별자에는 라운드를 붙이지 않고
    (2026-11-10 태석님), 실행 기록·그래프에 **따로** 적어 화면이 구분해 보이게 합니다.
    """
    best = None
    try:
        # 라운드는 함대가 '실행' 일 때만 돈다. 끝난 뒤(준비·중지) 손으로 띄운 실행에 지난 라운드 번호를 붙이지 않는다 (REV 145)
        import fleet_ctl  # noqa: PLC0415 - 순환 import 를 피해 호출 시점에
        if fleet_ctl.mode() != "running":
            return None
    except Exception:  # noqa: BLE001 - 모드를 못 읽으면 예전처럼 전달 기록만 본다
        pass
    try:
        files = list((pathlib.Path(RUNS).parent / "relay").glob("r*.json"))
    except OSError:
        return None
    for f in files:
        m = re.fullmatch(r"r(\d+)", f.stem)
        if not m:
            continue
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("state") == "failed":
                continue
        except (OSError, ValueError, AttributeError):
            continue
        best = max(best or 0, int(m.group(1)))
    return best


def task_project(task_id):
    """태스크 -> 그 요청의 프로젝트 이름. 없거나 모르면 `""`(함대 자체의 일)."""
    if not task_id or task_id == "ADHOC":
        return ""
    s = db_state() or {}
    rid = next((t.get("request_id") for t in s.get("tasks") or [] if t.get("id") == task_id), None)
    if not rid or not re.fullmatch(r"[A-Za-z0-9-]{1,40}", str(rid)):
        return ""
    try:
        for f in (ROOT / ".aimem" / "requests").glob(f"{rid}*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(rec, dict) and rec.get("id") == rid:
                pr = rec.get("project")
                return pr if isinstance(pr, str) else ""
    except (OSError, ValueError):
        pass
    return ""


def cmd_spawn(args):
    """작업자 1명을 백그라운드로 띄웁니다. 즉시 돌아오고 run id 를 찍습니다."""
    import datetime, shlex, subprocess as sp
    # 함대 모드 (fleet_ctl, 2026-11-10): '실행' 이 아니면 띄우지 않습니다 - 일시 중지·완전 중지·준비
    import fleet_ctl  # noqa: PLC0415 - fleet_ctl 이 이 모듈을 import 하므로 지연
    allowed, why = fleet_ctl.spawn_allowed()
    if not allowed:
        sys.exit(why)
    if why:
        print(f"주의: {why}", file=sys.stderr)
    r = roster()
    if args.slot not in r:
        sys.exit(_roster_miss(args.slot))
    token, harness_in_roster, _ = r[args.slot]
    harness = args.harness or harness_in_roster
    if harness not in HARNESSES:
        sys.exit(f"하네스가 올바르지 않습니다: {harness!r}")
    rev = read_rev()
    pats = owned_paths(args.slot)
    bad = [w for w in args.write if not path_allowed(w, pats)]
    if bad:
        sys.exit(f"{args.slot} 소유가 아닌 경로가 있어 띄우지 않았습니다: {', '.join(bad)}\n"
                 f"  {args.slot} 소유: {', '.join(pats) or '(없음)'}")
    task = pathlib.Path(args.task_file).read_text(encoding="utf-8") if args.task_file else (args.task or "")
    if not task.strip():
        sys.exit("--task 또는 --task-file 로 지시 본문을 주십시오")
    RUNS.mkdir(parents=True, exist_ok=True)
    # 식별자 체계 (태석님 2026-11-09 18:15): 요청 Q- / 태스크 T-0xx / 그래프 G-00x / 실행 <태스크>-<슬롯>-a<시도>-<HHMMSS> / 라운드 R<n>(기록 전용).
    # 실행 id 만 보고도 무슨 태스크·어느 슬롯·몇 번째 시도인지 읽히게 한다. 태스크가 없는 임시 실행은 ADHOC.
    task_id = (getattr(args, "task_id", None) or "").strip().upper() or "ADHOC"   # fleet_graph 가 Namespace 로 부를 때 없을 수 있다
    if not re.fullmatch(r"(T-\d+[A-Z]?|ADHOC)", task_id):
        sys.exit(f"--task-id 는 T-0xx 형식이어야 합니다: {task_id!r}")
    attempt = int(getattr(args, "attempt", None) or 1)
    stamp = datetime.datetime.now().strftime("%H%M%S")
    base = f"{task_id}-{args.slot}-a{attempt}-{stamp}"
    run_id, n = base, 1
    while (RUNS / f"{run_id}.json").exists():
        n += 1
        run_id = f"{base}-{n}"
    label = (args.label or "").strip()
    if task_id != "ADHOC" and not label.startswith(task_id):
        label = f"{task_id} {label}".strip()
    brief = "\n".join([
        f"SLOT={args.slot} {label}".rstrip(),
        f"확인토큰: {token}",
        f"AIMEM REV: {rev}",
        f"너는 {args.slot} 슬롯이다. 작업 폴더는 {ROOT} 다.",
        (f"쓰기는 다음 경로에만 한다: {', '.join(args.write)}" if args.write
         else "쓰기 없음(읽기 전용). 파일 생성/수정/삭제 금지."),
        "금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.",
        "보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.",
        *(["검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. "
           "셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다."]
          if harness == "claude" else []),
        "", task.strip(), ""])
    brief_path = RUNS / f"{run_id}.brief.md"
    brief_path.write_text(brief, encoding="utf-8")
    model = args.model or _load_slot_models().get(args.slot)   # 슬롯 모델(DB 거울 fleet_slots.json) - 하네스 불문, 없으면 하네스 기본
    argv, stdin_path = _worker_argv(harness, model, brief_path)
    out, err, rc = RUNS / f"{run_id}.out", RUNS / f"{run_id}.err", RUNS / f"{run_id}.rc"
    shell = (" ".join(shlex.quote(a) for a in argv)
             + (f" < {shlex.quote(stdin_path)}" if stdin_path else "")
             + f" > {shlex.quote(str(out))} 2> {shlex.quote(str(err))}; echo $? > {shlex.quote(str(rc))}")
    proc = sp.Popen(["bash", "-c", shell], cwd=ROOT, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                    start_new_session=True)
    meta = {"id": run_id, "slot": args.slot, "harness": harness, "model": model,
            "task": task_id, "attempt": attempt, "date": datetime.date.today().isoformat(),
            "label": label, "rev": rev, "write": args.write, "pid": proc.pid,
            "started": datetime.datetime.now().isoformat(timespec="seconds"), "brief": str(brief_path)}
    # 프로젝트·라운드는 식별자에 붙이지 않고 기록에 따로 적는다 - 화면이 실행을 프로젝트별로 구분해 보인다.
    try:
        meta["project"] = getattr(args, "project", None) or task_project(task_id)
        meta["round"] = getattr(args, "round", None) or current_round()
    except Exception:  # noqa: BLE001 - 표시용 정보 때문에 스폰이 죽으면 안 된다
        meta.setdefault("project", "")
        meta.setdefault("round", None)
    (RUNS / f"{run_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(run_id)
    _db_sync()
    return 0


def _list_runs():
    """시작 시각 순. (옛 `YYYYMMDD-HHMMSS-S#` 와 새 `T-050-S1-a1-HHMMSS` 가 섞여 있어 이름순은 안 된다)"""
    if not RUNS.exists():
        return []
    def key(m):
        try:
            return json.loads(m.read_text(encoding="utf-8")).get("started") or ""
        except (OSError, ValueError):
            return ""
    return [m.stem for m in sorted(RUNS.glob("*.json"), key=key)]


def cmd_runs(args):
    """띄운 작업자들의 상태 표. 읽기 전용."""
    import datetime
    ids = _list_runs()
    if not ids:
        print("실행 기록 없음 (.aimem/runs 비어 있음)")
        return 0
    print(f"{'run id':<30} {'슬롯':<4} {'하네스':<9} {'상태':<8} {'rc':>3}  {'경과':>7}  라벨")
    for rid in ids[-(args.last or len(ids)):]:
        meta = _run_meta(rid) or {}
        state, rc = _run_state(rid)
        started = datetime.datetime.fromisoformat(meta["started"]) if meta.get("started") else None
        end_f = RUNS / f"{rid}.rc"
        if started:
            if end_f.exists():
                end = datetime.datetime.fromtimestamp(end_f.stat().st_mtime)
            elif state == "lost":
                end = _run_last_mtime(rid) or datetime.datetime.now()  # lost 는 마지막 흔적에서 멈춘다
            else:
                end = datetime.datetime.now()
            elapsed = f"{(end - started).total_seconds():6.0f}s"
        else:
            elapsed = "?"
        print(f"{rid:<30} {meta.get('slot','?'):<4} {meta.get('harness','?'):<9} {state:<8} "
              f"{'' if rc is None else rc:>3}  {elapsed:>7}  {meta.get('label') or ''}")
    return 0


def cmd_wait(args):
    """작업자들이 끝날 때까지 기다렸다가 보고 본문을 찍습니다."""
    import time
    ids = args.id or [r for r in _list_runs() if _run_state(r)[0] == "running"]
    if not ids:
        print("기다릴 실행이 없습니다")
        return 0
    deadline = time.time() + args.timeout
    pending = list(ids)
    while pending and time.time() < deadline:
        pending = [r for r in pending if _run_state(r)[0] == "running"]
        if pending:
            time.sleep(args.poll)
    for rid in ids:
        state, rc = _run_state(rid)
        meta = _run_meta(rid) or {}
        print(f"===== {rid} [{meta.get('slot')}/{meta.get('harness')}] {state} rc={rc}")
        if state == "running":
            print("(아직 실행 중 - 타임아웃. 다시 wait 하십시오)")
            continue
        rep = run_report(rid)
        print(rep if rep else "(보고 본문 비어 있음 - .err 를 보십시오)")
        if rc not in (0, None):
            err_f = RUNS / f"{rid}.err"
            err = err_f.read_text(encoding="utf-8", errors="replace")[-1500:] if err_f.exists() else ""
            print("--- stderr 꼬리:\n" + err)
    _db_sync()
    return 1 if pending else 0


def cmd_report(args):
    print(run_report(args.id))
    return 0

def cmd_slot(args):
    """슬롯 추가/변경/삭제/목록 - 정본은 `.aimem/aimem.db` 의 slots (2026-11-10). `tools/aimem_db.py slot` 에 위임한다.
    2절 명부 표는 REV 114 에 내려가 더는 마크다운을 고치지 않는다. 웹 함대 현황에서도 같은 함수를 부른다.

      python3 tools/fleet.py slot add --slot S5 --harness claude --model anthropic/claude-opus-5-5 --role "판단형 작업자"
      python3 tools/fleet.py slot set --slot S4 --model haiku
      python3 tools/fleet.py slot remove --slot S5
      python3 tools/fleet.py slot list
    """
    import aimem_db
    ns = argparse.Namespace(action=args.action, slot=args.slot, harness=args.harness, model=args.model,
                            default_model=False, role=args.role, note=None, force=getattr(args, "force", False),
                            actor="클로드/클로(태석님 지시)")
    return aimem_db.cmd_slot(ns)


def cmd_reap(args):
    """보고 없이 사라진(lost) 실행을 거둡니다 - `.lost` 마커에 마지막 흔적 시각을 적어 표의 경과를 멈춥니다. 파일은 지우지 않습니다."""
    import datetime
    n = 0
    for rid in _list_runs():
        state, _ = _run_state(rid)
        if state != "lost" or (RUNS / f"{rid}.lost").exists():
            continue
        ended = _run_last_mtime(rid) or datetime.datetime.now()
        (RUNS / f"{rid}.lost").write_text(json.dumps({"ended": ended.isoformat(timespec="seconds"),
                                                       "reason": "작업자가 보고/종료코드 없이 사라짐 (프로세스 소멸)"},
                                                      ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"reaped {rid} (끝 {ended:%H:%M:%S})")
        n += 1
    print(f"{n}건 거둠" if n else "거둘 lost 실행 없음")
    _db_sync()
    return 0


def _db_sync(quiet=True):
    """운영 상태 DB(.aimem/aimem.db) 에 지금 파일 상태를 반영한다 - 전환기 이중 기록 (태석님 결정 2026-11-09 18:25).
    실패해도 함대 운영을 막지 않는다."""
    try:
        import aimem_db
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.migrate(verbose=False)
            aimem_db.render()
    except Exception as e:  # noqa: BLE001
        if not quiet:
            print(f"(db sync 실패: {e})", file=sys.stderr)



def main():
    p = argparse.ArgumentParser(description="작업자 운영 도우미 (관리자 전용)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="AIMEM REV / 슬롯 / 열린 태스크 / 미커밋 한눈에")
    sub.add_parser("children", help="ACP 자식 세션 + 실행 모델(하네스 설정 기준) + 상태")
    c = sub.add_parser("close", help="거두기 전 점검 - 정리할 것을 짚어 줍니다")
    c.add_argument("--slot", help="특정 슬롯만 점검")
    b = sub.add_parser("brief", help="브리프 머리말 - 슬롯/토큰/REV 자동, 쓰기 경로를 6절과 대조")
    b.add_argument("--slot", required=True)
    b.add_argument("--write", nargs="*", default=[], help="이 지시에서 쓸 경로")
    b.add_argument("--task", help="지시 본문")
    sp_ = sub.add_parser("spawn", help="작업자 1명을 하네스 CLI 로 백그라운드 실행 (REV 109)")
    sp_.add_argument("--slot", required=True)
    sp_.add_argument("--harness", choices=HARNESSES, help="생략하면 2절 명부의 하네스")
    sp_.add_argument("--model", help="하네스에 넘길 모델 id (생략하면 하네스 기본)")
    sp_.add_argument("--label", help="짧은 태스크 이름 (태스크 id 가 자동으로 앞에 붙음)")
    sp_.add_argument("--task-id", help="보드 태스크 id (T-050). 실행 id 와 라벨의 머리가 된다. 없으면 ADHOC")
    sp_.add_argument("--attempt", type=int, default=1, help="몇 번째 시도인지 (재시도면 2, 3 …)")
    sp_.add_argument("--write", nargs="*", default=[], help="이 태스크에서 쓸 경로 (6절 대조)")
    sp_.add_argument("--task", help="지시 본문")
    sp_.add_argument("--task-file", help="지시 본문 파일")
    sp_.add_argument("--project", help="결과물이 쌓이는 프로젝트 이름 (생략하면 태스크의 요청에서 찾는다)")
    rn = sub.add_parser("runs", help="띄운 작업자 상태 표")
    rn.add_argument("--last", type=int, help="최근 N 건만")
    w = sub.add_parser("wait", help="작업자 완료를 기다려 보고 본문 출력")
    w.add_argument("id", nargs="*", help="run id (생략하면 실행 중인 전부)")
    w.add_argument("--timeout", type=int, default=1800)
    w.add_argument("--poll", type=int, default=5)
    rp = sub.add_parser("report", help="끝난 작업자의 보고 본문만 출력")
    rp.add_argument("id")
    sub.add_parser("reap", help="보고 없이 사라진(lost) 실행을 거둔다 - 경과 시간 고정")
    sl = sub.add_parser("slot", help="슬롯 추가/변경/목록 - 2절 명부 + tools/fleet_slots.json (클로 실행)")
    sl.add_argument("action", choices=["add", "set", "remove", "list"])
    sl.add_argument("--slot")
    sl.add_argument("--harness", choices=HARNESSES)
    sl.add_argument("--model", help="claude: opus|sonnet|haiku (CLI 별칭). codex/opencode: 하네스 모델 id")
    sl.add_argument("--role", help="역할 칸 문구")
    sl.add_argument("--force", action="store_true", help="remove: 미완 태스크가 있어도 삭제")
    a = p.parse_args()
    return {"status": cmd_status, "close": cmd_close, "brief": cmd_brief,
            "children": cmd_children, "spawn": cmd_spawn, "runs": cmd_runs,
            "wait": cmd_wait, "report": cmd_report, "slot": cmd_slot, "reap": cmd_reap}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
