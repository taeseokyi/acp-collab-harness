#!/usr/bin/env python3
"""작업자 운영 도우미 (관리자 전용).

작업자와 관리자는 엔진이 `fleet_rt` 로 띄우는 세션입니다(`.aimem/sessions/<id>/`, 하네스 claude/codex/opencode).
판단은 사람이 하고, 이 도구는 옮겨 적는 일과 대조만 합니다.

  python3 tools/fleet.py status              # REV / 슬롯 / 열린 태스크 / 미커밋
  python3 tools/fleet.py close               # 거두기 전 점검
  python3 tools/fleet.py spawn / runs / wait / report / reap / slot
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:        # `python3 -m tools.fleet_graph`·`PYTHONPATH=.` 로 불러도 `aimem_db`·`fleet_rt` 를 찾게
    sys.path.insert(0, str(HERE))
ROOT = HERE.parent

from fleet_rt.base import DEFAULT_NODE_TIMEOUT_SEC  # noqa: E402
from fleet_rt.harness import REAL as HARNESSES  # noqa: E402

try:    # 시각은 설정 시간대 하나로 (`fleet.toml` `[time] zone`) - 엔진 도구는 모두 이 모듈을 들인다
    from fleet_rt import timezone as _rt_tz
    _rt_tz.apply(ROOT)
except Exception:  # noqa: BLE001
    pass

#: 실행 기록의 기준 경로. 읽는 것은 옆의 `sessions/`·`aimem.db` 뿐이다 (`RUNS.parent` = `.aimem`, 검사가 갈아 끼운다).
RUNS = ROOT / ".aimem" / "runs"


def sh(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


# --------------------------------------------------------------- 운영 상태 (정본 `.aimem/aimem.db`)
#: (읽은 시각, 상태) 캐시 - 실패는 캐시하지 않고 성공에도 TTL 을 둔다(오래 도는 실행기가 소유 변경을 보게).
_DB_CACHE = {"at": 0.0, "state": None}
DB_CACHE_TTL_SEC = 5.0


def db_state():
    """`.aimem/aimem.db` 의 운영 상태. 읽지 못하면 `None` (스폰은 거절된다)."""
    now = time.monotonic()
    if _DB_CACHE["state"] is not None and now - _DB_CACHE["at"] < DB_CACHE_TTL_SEC:
        return _DB_CACHE["state"]
    state = None
    try:
        import aimem_db  # noqa: PLC0415
        if aimem_db.DB.exists():
            state = aimem_db.state_dict()
    except Exception as e:  # noqa: BLE001 - 원인을 찍고 None 으로 (조용히 삼키면 "명부에 없음" 만 보인다)
        print(f"[fleet] .aimem/aimem.db 를 읽지 못했습니다: {type(e).__name__}: {e}", file=sys.stderr)
    _DB_CACHE.update(at=now, state=state)
    return state


def read_rev():
    s = db_state()
    if s and s.get("rev") is not None:
        return int(s["rev"])
    sys.exit("REV 를 찾지 못했습니다 (.aimem/aimem.db)")


def roster():
    """슬롯 -> (확인토큰, 하네스)."""
    s = db_state() or {}
    return {r["slot"]: (r["token"], r["harness"]) for r in s.get("slots") or []
            if re.fullmatch(r"S\d+", r["slot"] or "")}


def board_rows():
    """(태스크 id, 제목, 담당 슬롯, 상태) 의 리스트."""
    s = db_state() or {}
    return [(t["id"], t["title"] or "", t["slot"] or "-", t["status"]) for t in s.get("tasks") or []]


def owned_paths(slot):
    """그 슬롯이 쓸 수 있는 경로 패턴 (DB `ownership`)."""
    s = db_state() or {}
    return [r["path_pattern"] for r in s.get("ownership") or [] if (r["owner"] or "").strip() == slot]


def _roster_miss(slot):
    """명부에 없을 때의 종료 메시지 - DB 를 못 읽은 것과 정말 없는 것을 가른다."""
    if db_state() is None:
        return (f"{slot} 를 확인할 수 없습니다 - `.aimem/aimem.db` 를 읽지 못했습니다(위 오류). "
                "명부는 DB 에만 있으니 DB 를 고친 뒤 다시 하십시오.")
    return f"{slot} 가 명부에 없습니다 (`python3 tools/aimem_db.py state` 로 확인하십시오)"


def path_allowed(path, pats):
    """`path` 를 허용하는 패턴, 없으면 `None`. 접두 확장은 패턴이 `*` 로 끝날 때만 (정확한 파일 패턴은 정확히)."""
    import fnmatch
    for p in pats:
        if path == p or fnmatch.fnmatch(path, p):
            return p
        if p.endswith("*") and fnmatch.fnmatch(path, p.rstrip("*") + "*"):
            return p
    return None


def cmd_status(args):
    print(f"REV {read_rev()} (.aimem/aimem.db)")
    print()
    print("슬롯:")
    for slot, (token, harness) in sorted(roster().items()):
        print(f"  {slot}  {token}  {harness}")
    open_rows = [r for r in board_rows() if r[3] != "DONE"]
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
    stuck = [r for r in board_rows() if r[3] not in ("DONE", "TODO")]
    if args.slot:
        stuck = [r for r in stuck if r[2] == args.slot]
    for tid, name, slot, st in stuck:
        problems.append(f"보드 {tid}({slot}) 가 {st} 입니다. TODO 로 되돌리십시오 - "
                        f"python3 tools/aimem_db.py task set --id {tid} --status TODO")
    dirty = sh("git", "status", "--short").stdout.strip()
    if dirty:
        problems.append("미커밋이 있습니다. 커밋해야 작업자의 git 앵커가 살아납니다:\n    "
                        + "\n    ".join(dirty.splitlines()))
    # 끝나지 않은 세션·고아 프로세스. 런타임을 못 읽어도 나머지 점검은 쓸모가 있으므로 넘어간다.
    try:
        rt = _rt_sessions()
        running = []
        for rid in _list_runs():
            d = _session_dir(rid)
            if d is None or rt.state(d).get("state") != "running":
                continue
            if args.slot and (_session_meta(d) or {}).get("slot") != args.slot:
                continue
            running.append(rid)
        for rid in running:
            problems.append(f"실행 중인 세션이 남아 있습니다: {rid}\n    "
                            f"끝나길 기다리거나(`python3 tools/fleet.py wait {rid}`) 끊으십시오 - "
                            f"python3 tools/fleet.py reap  (감독이 사라진 것만 거둡니다)")
        for o in rt.find_orphans(_sessions_root()) or []:
            if o.get("session") in running:
                continue
            problems.append(f"고아 프로세스가 있습니다 (pid {o.get('pid')}, 세션 {o.get('session')}: {o.get('why')})\n    "
                            f"python3 tools/fleet.py reap")
    except Exception:  # noqa: BLE001
        pass
    if not problems:
        print("종료 준비 완료. 걸리는 것 없습니다.")
        return 0
    print("종료 전에 정리할 것:")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    return 1


def normalize_model(harness, model):
    """슬롯에 적힌 모델을 하네스가 받는 꼴로 - claude 는 `anthropic/`·`claude-cli/` 접두를 뗀다, 나머지는 그대로."""
    if not model:
        return model
    m = str(model).strip()
    if harness == "claude":
        for pre in ("anthropic/", "claude-cli/"):
            if m.startswith(pre):
                m = m[len(pre):]
    return m


# --------------------------------------------------------------- 실행 = 세션 (`.aimem/sessions/<id>/`)
# 아래 이름(`_run_meta`·`_run_state`·`run_report` …)은 그래프 실행기·fleet_ctl·검사가 쓰는 겉면이다.
def _sessions_root():
    # 호출 시점에 계산한다 - 검사가 `RUNS` 를 임시 폴더로 갈아끼우면 세션 폴더도 따라간다.
    return pathlib.Path(RUNS).parent / "sessions"


def _session_dir(run_id):
    """그 실행의 세션 폴더, 없으면 None. meta.json 이 지워져도 brief·events 가 있으면 세션이다(슬롯이 비지 않게)."""
    try:
        d = _sessions_root() / str(run_id)
        return d if any((d / f).is_file() for f in ("meta.json", "brief.md", "events.jsonl")) else None
    except (OSError, ValueError):
        return None


def _rt_sessions():
    from fleet_rt import sessions  # noqa: PLC0415 - 상태만 읽는 명령은 감독 런타임을 들이지 않는다
    return sessions


META_LIMIT = 256 * 1024


def read_regular_bytes(path, limit):
    """일반 파일만 `limit` 바이트 이하일 때 읽어 돌려준다. FIFO·장치·너무 큰 파일·오류는 None (FIFO 에서 막히지 않게)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except (OSError, ValueError):
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return None
        chunks, left = [], limit
        while left > 0:
            b = os.read(fd, min(left, 65536))
            if not b:
                break
            chunks.append(b)
            left -= len(b)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _read_json_capped(path, limit=META_LIMIT):
    raw = read_regular_bytes(path, limit)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return None


def _session_meta(d):
    """세션 `meta.json` 을 실행 메타 꼴로 (호출부가 `slot`·`harness`·`pid`·`brief` 를 읽는다)."""
    m = _read_json_capped(d / "meta.json")
    if not isinstance(m, dict):
        return None
    extra = m.get("extra") if isinstance(m.get("extra"), dict) else {}
    return {"id": m.get("id") or d.name, "slot": m.get("slot"), "harness": m.get("harness"), "model": m.get("model"),
            "task": m.get("task_id"), "attempt": m.get("attempt"), "date": extra.get("date"),
            "label": m.get("label"), "rev": extra.get("rev"), "write": m.get("write_paths") or [],
            "pid": m.get("supervisor_pid"), "started": m.get("started"), "brief": str(d / "brief.md"),
            "project": extra.get("project", ""), "round": m.get("round"),
            "role": m.get("role"), "provider": m.get("provider"), "session": True}


def _run_meta(run_id):
    d = _session_dir(run_id)
    return _session_meta(d) if d is not None else None


def _run_last_mtime(run_id, st=None):
    """세션이 끝난 시각(end.json → 마지막 사건 → 폴더 파일 mtime). 모르면 None. `st` 는 이미 읽은 `sessions.state()`."""
    d = _session_dir(run_id)
    if d is None:
        return None
    st = st if st is not None else _rt_sessions().state(d)
    for at in (st.get("ended"), st.get("last_event_at")):
        try:
            return datetime.datetime.fromisoformat(str(at)[:19])
        except (TypeError, ValueError):
            pass
    ts = [f.stat().st_mtime for f in d.iterdir() if f.is_file()]
    return datetime.datetime.fromtimestamp(max(ts)) if ts else None


#: 감독이 끊은 세션을 `("done", rc)` 로 옮길 때 쓰는 종료코드 (하네스가 받은 신호 -15 는 뜻이 없다).
_SESSION_RC = {"timeout": 124, "stalled": 125}


def state_pair(st):
    """`fleet_rt.sessions.state()` 의 결과 -> `(state, rc)`. 그래프 실행기는 `running`/`done`/`lost` 만 가린다.

    `killed`(사람·엔진이 끊음)는 `lost`, 감독이 끊은 `timeout`·`stalled` 는 rc != 0 인 `done` - 그래야 보고를 거두고 재시도 규칙을 탄다.
    """
    state, rc = st.get("state"), st.get("rc")
    if state == "running":
        return "running", None
    if state in ("lost", "killed"):
        return "lost", None
    if state == "done":
        return "done", rc if isinstance(rc, int) and not isinstance(rc, bool) else 0
    if state in _SESSION_RC:
        return "done", _SESSION_RC[state]
    if isinstance(rc, int) and not isinstance(rc, bool) and rc != 0:
        return "done", rc
    return "done", 1


def _run_state(run_id):
    """`(state, rc)` - 세션 폴더가 없는 id 는 `("unknown", None)`."""
    d = _session_dir(run_id)
    return state_pair(_rt_sessions().state(d)) if d is not None else ("unknown", None)


def run_report(run_id):
    """작업자의 보고 본문 (`report.md`, 없으면 어댑터가 사건에서 뽑은 것)."""
    d = _session_dir(run_id)
    return (_rt_sessions().report(d) or "").strip() if d is not None else ""


from fleet_rt.base import PROJECT_NAME_RE  # noqa: E402 - 정의는 한 곳


def current_round():
    """지금 도는 라운드 번호(함대가 '실행' 일 때의 라운드). 모르면 None - 끝난 뒤 손으로 띄운 실행에 지난 번호를 붙이지 않게."""
    try:
        import fleet_ctl  # noqa: PLC0415 - 순환 import 를 피해 호출 시점에
        return fleet_ctl.active_round() if fleet_ctl.mode() == "running" else None
    except Exception:  # noqa: BLE001 - 표시용 정보다. 모르면 비운다
        return None


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


def spawn_task_id(task_id, label):
    """실행에 붙일 태스크 id. 없으면 라벨 머리의 `T-113` 을, 그것도 없으면 `ADHOC` (화면에서 태스크와 이어지게)."""
    tid = (task_id or "").strip().upper()
    if not tid:
        m = re.match(r"\s*(T-\d+[A-Za-z]?)\b", label or "", re.IGNORECASE)
        tid = m.group(1).upper() if m else "ADHOC"
    return tid


#: 감독의 벽시계 제한은 그래프 한도보다 이만큼 길다 - 그래프 실행기가 먼저 끊고, 감독은 실행기가 죽었을 때의 뒷문이다.
SPAWN_TIMEOUT_SLACK_SEC = 120


def _slot_model(slot):
    """슬롯에 적힌 모델(DB `slots.model`). 없으면 None."""
    for row in (db_state() or {}).get("slots") or []:
        if row.get("slot") == slot:
            return row.get("model") or None
    return None


def spawn_harness_model(slot, harness=None, model=None):
    """띄울 (하네스, 모델) - 인자(노드 덮어쓰기) > 명부의 하네스·슬롯 모델 > `fleet.toml` 하네스 기본 모델.

    그래프 실행기의 공급자 문지기·`move` 가 띄우기 전에 같은 답을 내야 해서 한 곳에 둔다. 슬롯이 명부에 없으면 하네스는 None.
    """
    h = harness or (roster().get(slot) or (None, None))[1] or None
    m = model or _slot_model(slot)
    if h and not m:
        try:
            from fleet_rt import config as rt_config  # noqa: PLC0415
            m = (rt_config.load(ROOT).harness(h) or {}).get("default_model") or None
        except Exception:  # noqa: BLE001 - 설정을 못 읽으면 모델 없이 (하네스 자체 기본)
            m = None
    return h, m


def _brief_text(slot, token, rev, label, write, harness, task):
    return "\n".join([
        f"SLOT={slot} {label}".rstrip(),
        f"확인토큰: {token}",
        f"AIMEM REV: {rev}",
        f"너는 {slot} 슬롯이다. 작업 폴더는 {ROOT} 다.",
        (f"쓰기는 다음 경로에만 한다: {', '.join(write)}" if write
         else "쓰기 없음(읽기 전용). 파일 생성/수정/삭제 금지."),
        "금지: git commit / push / 삭제(자기 /tmp 작업 폴더는 지워도 됨) / 의존성 설치. 보고는 응답 본문에 직접 쓴다.",
        "보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / REJECT / NEEDS-LOCK / NEEDS-APPROVAL / NEEDS-FIX), "
        "이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.",
        *(["검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, "
           "`ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. "
           "셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다."]
          if harness == "claude" else []),
        "", task.strip(), ""])


def spawn(slot, task_text, *, write=(), label="", task_id=None, attempt=1, harness=None, model=None,
          project=None, round=None, timeout=None):
    """작업자 1명을 세션으로 띄우고 run id 를 돌려준다. 즉시 돌아온다. 거절은 `SystemExit(까닭)`.

    함대 모드·명부·하네스·소유권을 여기서 한 번 대조한다. 띄우는 일은 `fleet_rt.sessions.spawn` (감독 프로세스 하나).
    """
    import fleet_ctl  # noqa: PLC0415 - fleet_ctl 이 이 모듈을 import 하므로 지연
    allowed, why = fleet_ctl.spawn_allowed()
    if not allowed:
        sys.exit(why)
    if why:
        print(f"주의: {why}", file=sys.stderr)
    r = roster()
    if slot not in r:
        sys.exit(_roster_miss(slot))
    token = r[slot][0]
    harness, model = spawn_harness_model(slot, harness, model)
    if harness not in HARNESSES:
        sys.exit(f"하네스가 올바르지 않습니다: {harness!r}")
    rev = read_rev()
    write = list(write or [])
    pats = owned_paths(slot)
    bad = [w for w in write if not path_allowed(w, pats)]
    if bad:
        sys.exit(f"{slot} 소유가 아닌 경로가 있어 띄우지 않았습니다: {', '.join(bad)}\n"
                 f"  {slot} 소유: {', '.join(pats) or '(없음)'}")
    if not (task_text or "").strip():
        sys.exit("지시 본문이 비어 있습니다 (--task 또는 --task-file)")
    # 실행 id = <태스크>-<슬롯>-a<시도>-<HHMMSS> - id 만 보고도 태스크·슬롯·시도가 읽히게. 태스크가 없으면 ADHOC.
    task_id = spawn_task_id(task_id, label)
    if not re.fullmatch(r"(T-\d+[A-Z]?|ADHOC)", task_id):
        sys.exit(f"--task-id 는 T-0xx 형식이어야 합니다: {task_id!r}")
    attempt = int(attempt or 1)
    base = f"{task_id}-{slot}-a{attempt}-{datetime.datetime.now():%H%M%S}"
    run_id, n = base, 1
    while (_sessions_root() / run_id).exists():
        n += 1
        run_id = f"{base}-{n}"
    label = (label or "").strip()
    if task_id != "ADHOC" and not label.startswith(task_id):
        label = f"{task_id} {label}".strip()
    brief = _brief_text(slot, token, rev, label, write, harness, task_text)
    # 프로젝트·라운드는 식별자에 붙이지 않고 기록에 따로 적는다 - 화면이 실행을 프로젝트별로 구분해 보인다.
    extra = {"date": datetime.date.today().isoformat(), "rev": rev}
    try:
        extra["project"] = project or task_project(task_id)
        round_n = round or current_round()
    except Exception:  # noqa: BLE001 - 표시용 정보 때문에 스폰이 죽으면 안 된다
        extra.setdefault("project", "")
        round_n = None
    from fleet_rt import config as rt_config  # noqa: PLC0415
    from fleet_rt.base import SessionSpec  # noqa: PLC0415
    try:
        cfg = rt_config.load(ROOT)
        provider = cfg.provider_of(harness, model)
        idle = cfg.idle_timeout(provider) if provider else None
    except Exception as e:  # noqa: BLE001 - 설정이 깨져도 띄우기는 한다 (침묵 감지만 꺼진다)
        print(f"주의: fleet.toml 을 읽지 못했습니다 ({e}) - 침묵 감지 없이 띄웁니다", file=sys.stderr)
        provider, idle = None, None
    spec = SessionSpec(id=run_id, role="worker", harness=harness, brief_path="", cwd=str(ROOT),
                       slot=slot, model=normalize_model(harness, model), provider=provider,
                       ident=f"[AIMEM 작업자 지시] 슬롯 {slot} · 확인토큰 {token} · AIMEM REV {rev}.",
                       write_paths=write, timeout=float(timeout or DEFAULT_NODE_TIMEOUT_SEC) + SPAWN_TIMEOUT_SLACK_SEC,
                       idle_timeout=idle, round=round_n if isinstance(round_n, int) else None, task_id=task_id,
                       attempt=attempt, label=label, extra=extra)
    db = pathlib.Path(RUNS).parent / "aimem.db"
    try:
        _rt_sessions().spawn(spec, brief, _sessions_root(), db_path=str(db) if db.exists() else None, env_root=str(ROOT))
    except (ValueError, OSError, RuntimeError) as e:
        sys.exit(f"작업자를 띄우지 못했습니다 ({run_id}): {e}")
    return run_id


def cmd_spawn(args):
    """CLI `spawn` - `spawn()` 을 부르고 run id 를 찍는다."""
    a = vars(args)
    task_file = a.get("task_file")
    task = pathlib.Path(task_file).read_text(encoding="utf-8") if task_file else (a.get("task") or "")
    print(spawn(a["slot"], task, write=a.get("write") or (), label=a.get("label") or "", task_id=a.get("task_id"),
                attempt=a.get("attempt") or 1, harness=a.get("harness"), model=a.get("model"),
                project=a.get("project"), round=a.get("round"), timeout=a.get("timeout")))
    return 0


def _list_runs(managers=False):
    """세션 id 들, 시작 시각 순. 작업자만 준다 - 관리자(슬롯 없음)가 섞이면 '슬롯 모를 실행' 으로 보여 그래프가 막힌다.
    관리자까지 보려면 `managers=True` (`fleet.py runs` 표)."""
    sroot = _sessions_root()
    pairs = []
    if sroot.is_dir():
        for d in sroot.iterdir():
            if _session_dir(d.name) is None:
                continue
            m = _read_json_capped(d / "meta.json")
            m = m if isinstance(m, dict) else {}
            if m.get("role") == "manager" and not managers:
                continue
            pairs.append((str(m.get("started") or ""), d.name))
    return [rid for _k, rid in sorted(pairs)]


def cmd_runs(args):
    """띄운 작업자들의 상태 표. 읽기 전용."""
    ids = _list_runs(managers=True)
    if not ids:
        print("실행 기록 없음 (.aimem/sessions 비어 있음)")
        return 0
    print(f"{'run id':<30} {'슬롯':<4} {'하네스':<9} {'상태':<8} {'rc':>3}  {'경과':>7}  라벨")
    for rid in ids[-(args.last or len(ids)):]:
        meta = _run_meta(rid) or {}
        state, rc = _run_state(rid)
        try:
            started = datetime.datetime.fromisoformat(meta["started"])
        except (KeyError, TypeError, ValueError):
            started = None
        if started:
            end = (_run_last_mtime(rid) if state != "running" else None) or datetime.datetime.now()
            elapsed = f"{(end - started).total_seconds():6.0f}s"
        else:
            elapsed = "?"
        print(f"{rid:<30} {meta.get('slot') or ('관리' if meta.get('role') == 'manager' else '?'):<4} {meta.get('harness') or '?':<9} {state:<8} "
              f"{'' if rc is None else rc:>3}  {elapsed:>7}  {meta.get('label') or ''}")
    return 0


def cmd_wait(args):
    """작업자들이 끝날 때까지 기다렸다가 보고 본문을 찍습니다."""
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
        print(rep if rep else "(보고 본문 비어 있음)")
        sd = _session_dir(rid)
        if rc not in (0, None) and sd is not None:
            err = (read_regular_bytes(sd / "stderr.log", 16 * 1024 * 1024) or b"").decode("utf-8", "replace")[-1500:]
            print("--- stderr 꼬리:\n" + err)
    return 1 if pending else 0


def cmd_report(args):
    print(run_report(args.id))
    return 0


def cmd_slot(args):
    """슬롯 추가/변경/삭제/목록 - 정본은 DB `slots`, `tools/aimem_db.py slot` 에 위임한다 (웹 함대 현황도 같은 함수).

      python3 tools/fleet.py slot add --slot S5 --harness claude --model anthropic/claude-opus-5-5 --role "판단형 작업자"
      python3 tools/fleet.py slot set --slot S4 --model haiku
      python3 tools/fleet.py slot remove --slot S5
      python3 tools/fleet.py slot list
    """
    import aimem_db
    ns = argparse.Namespace(action=args.action, slot=args.slot, harness=args.harness, model=args.model,
                            default_model=False, role=args.role, note=None, force=args.force, actor="fleet.py")
    return aimem_db.cmd_slot(ns)


def cmd_reap(args):
    """감독이 사라진 세션을 거둡니다 - end.json 없이 lost 인 것과 감독 없이 하네스만 남은(orphaned) 것. 파일은 지우지 않습니다.
    `cancel` 이 남은 프로세스를 끝내고 end.json(killed) 을 적어 슬롯을 비웁니다."""
    rt = _rt_sessions()
    n = 0
    for rid in _list_runs():
        sd = _session_dir(rid)
        if sd is None:
            continue
        st = rt.state(sd)
        if (st.get("state") == "lost" and not (sd / "end.json").exists()) or st.get("orphaned"):
            print(f"reaped {rid} ({rt.cancel(sd, why='reap: 감독 프로세스가 사라짐')})")
            n += 1
    print(f"{n}건 거둠" if n else "거둘 lost 실행 없음")
    return 0


def main():
    p = argparse.ArgumentParser(description="작업자 운영 도우미 (관리자 전용)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="REV / 슬롯 / 열린 태스크 / 미커밋 한눈에")
    c = sub.add_parser("close", help="거두기 전 점검 - 정리할 것을 짚어 줍니다")
    c.add_argument("--slot", help="특정 슬롯만 점검")
    sp_ = sub.add_parser("spawn", help="작업자 1명을 세션으로 백그라운드 실행")
    sp_.add_argument("--slot", required=True)
    sp_.add_argument("--harness", choices=HARNESSES, help="생략하면 명부(DB slots)의 하네스")
    sp_.add_argument("--model", help="생략하면 슬롯 모델, 그것도 없으면 fleet.toml 의 하네스 기본 모델")
    sp_.add_argument("--label", help="짧은 태스크 이름 (태스크 id 가 자동으로 앞에 붙음)")
    sp_.add_argument("--task-id", help="보드 태스크 id (T-050). 실행 id 와 라벨의 머리가 된다. 없으면 ADHOC")
    sp_.add_argument("--attempt", type=int, default=1, help="몇 번째 시도인지 (재시도면 2, 3 …)")
    sp_.add_argument("--write", nargs="*", default=[], help="이 태스크에서 쓸 경로 (DB 소유권과 대조)")
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
    sub.add_parser("reap", help="감독이 사라진 세션(lost·고아)을 끊고 끝남으로 적는다")
    sl = sub.add_parser("slot", help="슬롯 추가/변경/삭제/목록 (DB 정본, aimem_db.py 에 위임)")
    sl.add_argument("action", choices=["add", "set", "remove", "list"])
    sl.add_argument("--slot")
    sl.add_argument("--harness", choices=HARNESSES)
    sl.add_argument("--model", help="`fleet.toml` 의 공급자/모델 (예 kisti/kistillm) 또는 claude 별칭(opus|sonnet|haiku)")
    sl.add_argument("--role", help="역할 칸 문구")
    sl.add_argument("--force", action="store_true", help="remove: 미완 태스크가 있어도 삭제")
    a = p.parse_args()
    return {"status": cmd_status, "close": cmd_close, "spawn": cmd_spawn, "runs": cmd_runs,
            "wait": cmd_wait, "report": cmd_report, "slot": cmd_slot, "reap": cmd_reap}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
