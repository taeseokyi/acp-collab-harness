#!/usr/bin/env python3
"""함대 제어 - 준비 / 실행 / 일시 중지 / 완전 중지 / 라운드 실행 (태석님 지시 2026-11-10).

상태는 `.aimem/fleet-mode.json` 하나에 둡니다 (git 제외 - 운영 상태).

    ready    준비 완료. 점검을 통과했고 새 라운드를 띄울 수 있다. 작업자 투입 X
    running  실행. 진행 중 라운드를 돌린다. 작업자 투입 O
    paused   일시 중지. 새 작업자 투입 X, 돌고 있는 작업자는 끝까지 둔다
    stopped  완전 중지. 돌고 있는 작업자·그래프 실행기를 즉시 종료한다. 작업자 투입 X

**지키는 쪽**은 `fleet.py spawn`(투입 거절)과 `fleet_graph.py`(스폰 보류 / 중지 시 정리)입니다.
파일이 없으면 `running` 으로 봅니다 - 이 도구가 생기기 전과 같은 동작이고, 테스트처럼
`fleet.RUNS` 를 임시 디렉터리로 바꾼 환경도 그대로 돕니다.

    python3 tools/fleet_ctl.py status
    python3 tools/fleet_ctl.py prepare          # 점검 → 통과하면 ready
    python3 tools/fleet_ctl.py run              # running + 주인 없는 미완 그래프를 이어 돌림
    python3 tools/fleet_ctl.py pause
    python3 tools/fleet_ctl.py stop             # 작업자·그래프 즉시 종료
    python3 tools/fleet_ctl.py round            # ready 에서만. 확정 브리프로 새 관리자 라운드 (클로 경유)

**새 라운드는 사람이 판단해서 누릅니다** (`round`). `run` 은 진행 중이던 라운드만 이어 돌리고
새 관리자를 띄우지 않습니다. 관리자 투입은 지금처럼 **클로(전달자) 경유**입니다
(`openclaw agent --agent coding`, 클로가 `sessions_spawn`).
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import fleet  # noqa: E402

MODES = ("ready", "running", "paused", "stopped")
MODE_LABEL = {"ready": "준비", "running": "실행", "paused": "일시 중지", "stopped": "완전 중지"}
SPAWN_MODES = ("running",)
FORCE_ENV = "AIMEM_FLEET_FORCE"   # 스모크 등 사람이 직접 하는 1회 실행용 우회 (기록에 남는다)
BRIEF_RE = re.compile(r"\Amanager-round(\d+)-(\d{4}-\d{2}-\d{2})\.md\Z")
RELAY_TIMEOUT_SEC = 900
RELAY_NUDGE_WAIT_SEC = 90


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _aimem_dir():
    # 호출 시점에 계산합니다 - 테스트가 `fleet.RUNS` 를 갈아끼우면 상태 파일도 따라갑니다.
    return pathlib.Path(fleet.RUNS).parent


def mode_path():
    return _aimem_dir() / "fleet-mode.json"


def read_mode():
    p = mode_path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("mode") in MODES:
            return d
    except (OSError, ValueError):
        pass
    return {"mode": "running", "at": None, "by": None, "note": "상태 파일 없음 - 기본값(실행)", "default": True}


def mode():
    return read_mode()["mode"]


def set_mode(m, by="사람", note=""):
    if m not in MODES:
        raise ValueError(f"모드가 올바르지 않습니다: {m!r}")
    prev = read_mode()
    rec = {"mode": m, "at": _now(), "by": str(by)[:60], "note": str(note)[:300], "prev": prev.get("mode")}
    p = mode_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    # 기록은 DB 이벤트가 아니라 별도 로그에 남깁니다 - DB 에 쓰면 `AIMEM-state.md` 스냅샷이
    # 어긋나 린터(STATE_SNAPSHOT_STALE)와 커밋 훅이 막힙니다 (2026-11-10 실측).
    try:
        with open(p.parent / "fleet-mode.log", "a", encoding="utf-8") as fh:
            fh.write(f"{rec['at']} {rec['by']} {prev.get('mode')} -> {m} ({MODE_LABEL[m]}) {note}".rstrip() + "\n")
    except OSError:
        pass
    return rec


def spawn_allowed():
    """(허용, 이유). `fleet.py spawn` 이 맨 앞에서 부릅니다."""
    m = mode()
    if m in SPAWN_MODES:
        return True, ""
    if os.environ.get(FORCE_ENV) == "1":
        return True, f"{FORCE_ENV}=1 로 우회 (모드 {m})"
    return False, (f"함대가 '{MODE_LABEL.get(m, m)}' 상태라 작업자를 띄우지 않습니다 "
                   f"(.aimem/fleet-mode.json). 이어 가려면 사람이 '실행' 을 눌러야 합니다")


# ----------------------------------------------------------------- 조회
def running_runs():
    out = []
    runs = pathlib.Path(fleet.RUNS)
    if not runs.exists():
        return out
    for f in runs.glob("*.json"):
        if f.name.endswith(".brief.json"):
            continue
        rid = f.stem
        try:
            state, _ = fleet._run_state(rid)
        except Exception:  # noqa: BLE001
            continue
        if state == "running":
            meta = fleet._run_meta(rid) or {}
            out.append({"id": rid, "slot": meta.get("slot"), "label": meta.get("label"), "started": meta.get("started")})
    out.sort(key=lambda r: str(r.get("started") or ""))
    return out


def _graphs_dir():
    return _aimem_dir() / "graph"


def _graph_unfinished(g):
    return any(n.get("status", "todo") not in ("done", "failed", "blocked") for n in g.get("nodes", []))


def _lock_holder(gid):
    """그래프 잠금을 누가 잡고 있으면 그 기록(dict), 아무도 없으면 None. 잡지 않고 확인만 합니다."""
    path = _graphs_dir() / f"{gid}.lock"
    if not path.exists():
        return None
    try:
        with open(path, "r+", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, PermissionError):
                f.seek(0)
                try:
                    d = json.loads(f.read() or "{}")
                except ValueError:
                    d = {}
                return d if isinstance(d, dict) else {"pid": "?"}
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return None
    except OSError:
        return None


def graphs_overview():
    out = []
    d = _graphs_dir()
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            g = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(g, dict) or "nodes" not in g:
            continue
        counts = {}
        for n in g["nodes"]:
            counts[n.get("status", "todo")] = counts.get(n.get("status", "todo"), 0) + 1
        out.append({"id": g.get("id", f.stem), "unfinished": _graph_unfinished(g),
                    "runner": _lock_holder(g.get("id", f.stem)), "counts": counts, "updated": g.get("updated")})
    return out


def latest_brief(used=None):
    """확정 브리프(`manager-round<N>-<날짜>.md`, 초안 제외) 중 라운드 번호가 가장 큰 것.
    `used` 를 주면 세션 조회(4초)를 건너뜁니다 - 서버는 자기 캐시의 관리자 라벨을 넘깁니다."""
    d = fleet.ROOT / ".aimem" / "briefs"
    best, drafts = None, []
    if d.exists():
        for f in d.glob("manager-round*.md"):
            m = BRIEF_RE.match(f.name)
            if not m:
                if "draft" in f.name:
                    drafts.append(f.name)
                continue
            n = int(m.group(1))
            if best is None or n > best[0]:
                best = (n, f)
    used = _used_rounds() if used is None else set(used)
    if best and best[0] in used:
        best = None   # 이미 띄운 라운드의 브리프는 다시 쓰지 않는다
    return {"round": best[0] if best else None, "file": best[1].name if best else None,
            "drafts": sorted(drafts), "used_rounds": sorted(used)}


def rounds_from_labels(labels):
    out = set()
    for lab in labels:
        m = re.search(r"\bR(\d+)\b", lab or "")
        if m:
            out.add(int(m.group(1)))
    return out


def _relay_rounds():
    used = set()
    relay = _aimem_dir() / "relay"
    if relay.exists():
        for f in relay.glob("r*.json"):
            m = re.match(r"r(\d+)", f.stem)
            if m:
                used.add(int(m.group(1)))
    return used


def public_state(manager_labels=(), manager_running_now=False):
    """`/api/state.fleet` - 서버가 5초마다 부르므로 **세션 조회를 하지 않습니다**(관리자 정보는 인자로)."""
    used = _relay_rounds() | rounds_from_labels(manager_labels)
    m = read_mode()
    rr = running_runs()
    graphs = [g for g in graphs_overview() if g["unfinished"] or g["runner"]]
    b = latest_brief(used)
    md = m["mode"]
    can = {
        "prepare": md in ("stopped", "paused", "ready") and not manager_running_now and not rr,
        "run": md in ("ready", "paused", "stopped"),
        "pause": md == "running",
        "stop": md != "stopped",
        "round": md == "ready" and bool(b["file"]) and not manager_running_now,
    }
    return {"mode": md, "label": MODE_LABEL.get(md), "at": m.get("at"), "by": m.get("by"), "note": m.get("note"),
            "default": bool(m.get("default")), "running_runs": len(rr),
            "graphs": [{"id": g["id"], "runner": bool(g["runner"]), "counts": g["counts"]} for g in graphs],
            "brief": b, "prepare": last_prepare(), "relay": relay_status(), "can": can}


def _used_rounds():
    used = set()
    relay = _aimem_dir() / "relay"
    if relay.exists():
        for f in relay.glob("r*.json"):
            m = re.match(r"r(\d+)", f.stem)
            if m:
                used.add(int(m.group(1)))
    # 관리자 세션 라벨에 남은 라운드도 사용된 것으로 본다
    for s in _manager_sessions(cache_ok=True):
        m = re.search(r"\bR(\d+)\b", s.get("label") or "")
        if m:
            used.add(int(m.group(1)))
    return used


_SESS_CACHE = {"at": 0.0, "value": []}


def _manager_sessions(cache_ok=False):
    if cache_ok and time.time() - _SESS_CACHE["at"] < 30:
        return _SESS_CACHE["value"]
    try:
        res = subprocess.run(["openclaw", "sessions", "--agent", "claude", "--json"],
                             capture_output=True, text=True, timeout=25)
        payload = json.loads(res.stdout) if res.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return _SESS_CACHE["value"]
    sessions = payload.get("sessions", []) if isinstance(payload, dict) else payload
    val = [{"label": s.get("label"), "status": s.get("status"), "key": s.get("key")}
           for s in sessions if isinstance(s, dict) and ":acp:" in str(s.get("key", ""))]
    _SESS_CACHE.update({"at": time.time(), "value": val})
    return val


def manager_running():
    return [s for s in _manager_sessions() if s.get("status") == "running"]


def status():
    m = read_mode()
    return {"mode": m, "label": MODE_LABEL.get(m["mode"]), "spawn_allowed": m["mode"] in SPAWN_MODES,
            "running_runs": running_runs(), "graphs": [g for g in graphs_overview() if g["unfinished"] or g["runner"]],
            "brief": latest_brief(), "relay": relay_status()}


# ----------------------------------------------------------------- 동작
def pause(by="사람"):
    if mode() == "stopped":
        return {"ok": False, "error": "완전 중지 상태입니다 - 일시 중지할 것이 없습니다"}
    set_mode("paused", by, "새 작업자 투입 보류, 돌고 있는 작업자는 끝까지")
    return {"ok": True, "mode": "paused", "running_runs": running_runs()}


def stop(by="사람"):
    """완전 중지. 상태를 먼저 바꿔(새 투입 차단) 그래프 실행기가 다음 틱에 스스로 정리하게 하고,
    실행기가 없는 그래프와 그래프 밖 실행은 여기서 직접 정리합니다."""
    import fleet_graph  # noqa: PLC0415 - 순환 import 회피
    set_mode("stopped", by, "작업자·그래프 즉시 종료")
    halted, killed = [], []
    for gi in graphs_overview():
        if not gi["unfinished"] or gi["runner"]:
            continue   # 실행기가 있으면 실행기가 정리한다 (다음 틱, 기본 15초)
        try:
            with fleet_graph.graph_lock(gi["id"], "stop"):
                g = fleet_graph._load(gi["id"])
                if fleet_graph.halt_running(g, f"완전 중지 ({by})"):
                    halted.append(gi["id"])
        except SystemExit:
            continue
    for r in running_runs():
        pid, outcome = fleet_graph._kill_run(r["id"], with_outcome=True)
        if outcome in ("killed", "gone"):
            fleet_graph._mark_lost(r["id"])
        killed.append({"id": r["id"], "outcome": outcome})
    return {"ok": True, "mode": "stopped", "halted_graphs": halted, "killed": killed,
            "note": "그래프 실행기가 있던 그래프는 실행기가 다음 틱에 정리하고 끝납니다"}


def resume(by="사람"):
    """실행. 진행 중이던 라운드만 이어 돌립니다 - 새 관리자는 띄우지 않습니다."""
    set_mode("running", by, "진행 중 라운드 재개")
    started = []
    for gi in graphs_overview():
        if gi["unfinished"] and not gi["runner"]:
            log = _graphs_dir() / f"{gi['id']}.runner.log"
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"\n# {_now()} fleet_ctl resume ({by})\n")
                fh.flush()
                subprocess.Popen([sys.executable, str(HERE / "fleet_graph.py"), "run", gi["id"],
                                  "--timeout", "3600", "--poll", "15"],
                                 cwd=str(fleet.ROOT), stdout=fh, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
            started.append(gi["id"])
    mgr = manager_running()
    note = ("관리자 세션이 살아 있어 그대로 이어 갑니다" if mgr else
            "실행 중인 관리자가 없습니다 - 이어 돌린 그래프의 결과 확인과 보고는 다음 관리자 몫입니다"
            if started else "이어 갈 라운드가 없습니다 - 새 라운드는 '라운드 실행' 으로")
    return {"ok": True, "mode": "running", "resumed_graphs": started, "manager_running": bool(mgr), "note": note}


def _check(name, ok, detail="", required=True):
    return {"name": name, "ok": bool(ok), "detail": str(detail)[:200], "required": required}


def prepare(by="사람", extra_checks=()):
    """준비. 관리자·작업자를 띄울 수 있는지 점검하고, 통과하면 `ready`. 작업자는 띄우지 않습니다."""
    checks = []
    for h in fleet.HARNESSES:
        path = shutil.which(h)
        checks.append(_check(f"작업자 하네스 {h}", path, path or "PATH 에 없음"))
    oc = shutil.which("openclaw")
    checks.append(_check("openclaw (클로·관리자 경로)", oc, oc or "PATH 에 없음"))
    sess_ok, mgr = True, []
    try:
        res = subprocess.run(["openclaw", "sessions", "--agent", "claude", "--json"],
                             capture_output=True, text=True, timeout=25)
        sess_ok = res.returncode == 0
        if sess_ok:
            _SESS_CACHE["at"] = 0
            mgr = manager_running()
    except (OSError, subprocess.TimeoutExpired) as e:
        sess_ok = False
        res = type("R", (), {"stderr": str(e)})()
    checks.append(_check("게이트웨이 세션 조회", sess_ok, "" if sess_ok else (getattr(res, "stderr", "") or "")[:120]))
    checks.append(_check("실행 중인 관리자 없음", not mgr, ", ".join(s["label"] or "?" for s in mgr) or "없음"))
    rr = running_runs()
    checks.append(_check("돌고 있는 작업자 없음", not rr, ", ".join(r["id"] for r in rr) or "없음"))
    busy = [g["id"] for g in graphs_overview() if g["runner"]]
    checks.append(_check("돌고 있는 그래프 실행기 없음", not busy, ", ".join(busy) or "없음"))
    try:
        import aimem_db  # noqa: PLC0415
        with aimem_db.connect() as con:
            db_rev = aimem_db.rev(con)
        md = re.search(r"- \*\*REV: (\d+)\*\*", (fleet.ROOT / "AIMEM.md").read_text(encoding="utf-8"))
        md_rev = int(md.group(1)) if md else None
        checks.append(_check("REV 일치 (DB = AIMEM.md)", db_rev is not None and int(db_rev) == md_rev, f"DB {db_rev} / md {md_rev}"))
    except Exception as e:  # noqa: BLE001
        checks.append(_check("REV 일치 (DB = AIMEM.md)", False, f"{type(e).__name__}: {e}"))
    lint = subprocess.run([sys.executable, str(HERE / "aimem_lint.py"), str(fleet.ROOT / "AIMEM.md")],
                          capture_output=True, text=True, cwd=str(fleet.ROOT))
    lint_lines = (lint.stdout or lint.stderr or "").strip().splitlines()
    checks.append(_check("AIMEM 린터", lint.returncode == 0, lint_lines[-1] if lint_lines else ""))
    b = latest_brief()
    checks.append(_check("다음 라운드 브리프 (확정본)", b["file"], b["file"] or
                         ("초안만 있음: " + ", ".join(b["drafts"]) if b["drafts"] else "없음"), required=False))
    checks.extend(extra_checks)
    ok = all(c["ok"] for c in checks if c["required"])
    if ok:
        set_mode("ready", by, "준비 점검 통과")
    rec = {"at": _now(), "by": by, "ok": ok, "checks": checks}
    try:
        (_aimem_dir() / "fleet-prepare.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return {"ok": ok, "mode": mode(), "checks": checks}


def last_prepare():
    try:
        return json.loads((_aimem_dir() / "fleet-prepare.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------- 라운드 실행 (클로 경유)
RELAY_TEMPLATE = """태석님 지시 (함대 모니터 '라운드 실행' 버튼, {at}). 너는 전달자다. 판단하지 말고 아래를 그대로 수행하라.
설명이나 계획 문장으로 턴을 끝내지 말고, 1·2 단계의 도구 호출부터 하라.

1. 파일 {brief} 를 읽어라. 그 전문이 관리자 브리프다.
2. 아래 호출을 정확히 한 번 실행하라. task 에는 1 의 파일 전문을 한 글자도 바꾸지 말고 넣어라. model 인자는 주지 말라.
   sessions_spawn(runtime: "acp", agentId: "claude", mode: "run", context: "isolated", label: "{label}", task: <파일 전문>)
3. 스폰 직후 돌아온 세션키(agent:claude:acp:...)를 첫 줄에 적어라.
4. 완료 통보가 올 때까지 기다려라. 중간에 sessions_send 로 재촉하거나 끼어들지 말라. 작업자(S1~S4)를 네가 띄우지 말라.
5. 완료되면 sessions_history(sessionKey) 로 관리자의 마지막 응답 본문 전체를 읽어 아래 형식으로 보고하라.
6. 보고를 마친 뒤, 그 관리자 세션이 done 이면 sessions.delete 로 거둬라.

보고 형식(이 외 문장 금지):
관리자 세션키: <키>
스폰 시각: <KST HH:MM> / 완료 시각: <KST HH:MM>
--- 관리자 응답 원문 시작
<관리자 마지막 응답 본문 그대로>
--- 관리자 응답 원문 끝
"""

NUDGE_TEMPLATE = """너는 앞 지시의 1단계(브리프 읽기)만 하고 턴을 끝냈다. 관리자 세션이 아직 없다.
지금 바로 앞 지시의 2단계를 실행하라: {brief} 전문을 task 로 넣어
sessions_spawn(runtime: "acp", agentId: "claude", mode: "run", context: "isolated", label: "{label}", task: <파일 전문>)
을 정확히 한 번 호출하라. 설명·계획 문장으로 턴을 끝내지 말고 도구 호출부터 하라. 이후 단계는 앞 지시대로.
"""


def _relay_dir():
    d = _aimem_dir() / "relay"
    d.mkdir(parents=True, exist_ok=True)
    return d


def relay_status():
    d = _aimem_dir() / "relay"
    if not d.exists():
        return None
    files = sorted(d.glob("r*.json"), key=lambda f: f.stat().st_mtime)
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_relay(rec):
    p = _relay_dir() / f"r{rec['round']}.json"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def launch_round(by="사람"):
    """새 라운드. **준비(ready) 상태에서만**, 확정 브리프가 있고 관리자가 없을 때만."""
    if mode() != "ready":
        return {"ok": False, "error": f"'준비' 상태에서만 새 라운드를 띄웁니다 (지금: {MODE_LABEL.get(mode())}). 먼저 '준비' 를 누르십시오"}
    b = latest_brief()
    if not b["file"]:
        return {"ok": False, "error": "확정된 다음 라운드 브리프가 없습니다 (manager-round<N>-<날짜>.md). 초안: " + (", ".join(b["drafts"]) or "없음")}
    _SESS_CACHE["at"] = 0
    if manager_running():
        return {"ok": False, "error": "이미 실행 중인 관리자가 있습니다"}
    n = b["round"]
    at = dt.datetime.now()
    label = f"관리자 R{n} (Opus) {at.strftime('%Y-%m-%d')}"
    brief = fleet.ROOT / ".aimem" / "briefs" / b["file"]
    relay = _relay_dir()
    msg = relay / f"r{n}-instruction.md"
    msg.write_text(RELAY_TEMPLATE.format(at=at.strftime("%Y-%m-%d %H:%M"), brief=brief, label=label), encoding="utf-8")
    rec = {"round": n, "label": label, "brief": b["file"], "by": by, "at": _now(), "state": "launching",
           "session_key": f"agent:coding:relay-r{n}-{at.strftime('%H%M%S')}", "nudged": False, "log": []}
    _write_relay(rec)
    set_mode("running", by, f"라운드 R{n} 실행 ({b['file']})")
    log = open(relay / f"r{n}.log", "a", encoding="utf-8")
    subprocess.Popen([sys.executable, str(HERE / "fleet_ctl.py"), "_relay", "--round", str(n)],
                     cwd=str(fleet.ROOT), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    return {"ok": True, "round": n, "label": label, "brief": b["file"], "mode": "running"}


def _relay_worker(n):
    """배경 프로세스: 클로에게 전달 → 관리자 세션이 안 생기면 한 번 재촉 (R6 실측: 클로가 읽기만 하고 끝낸 일)."""
    relay = _relay_dir()
    p = relay / f"r{n}.json"
    rec = json.loads(p.read_text(encoding="utf-8"))

    def note(s):
        rec["log"].append(f"{_now()} {s}")
        _write_relay(rec)

    def send(msgfile):
        try:
            res = subprocess.run(["openclaw", "agent", "--agent", "coding", "--session-key", rec["session_key"],
                                  "--json", "--timeout", str(RELAY_TIMEOUT_SEC), "--message-file", str(msgfile)],
                                 capture_output=True, text=True, timeout=RELAY_TIMEOUT_SEC + 60, cwd=str(fleet.ROOT))
            return res.returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            note(f"전달 실패: {type(e).__name__}")
            return -1

    def spawned():
        _SESS_CACHE["at"] = 0
        return any(s.get("label") == rec["label"] for s in _manager_sessions())

    rec["state"] = "relaying"
    note("클로에게 전달")
    rc = send(relay / f"r{n}-instruction.md")
    note(f"클로 응답 rc={rc}")
    deadline = time.time() + RELAY_NUDGE_WAIT_SEC
    while time.time() < deadline and not spawned():
        time.sleep(10)
    if not spawned():
        nudge = relay / f"r{n}-nudge.md"
        nudge.write_text(NUDGE_TEMPLATE.format(brief=fleet.ROOT / ".aimem" / "briefs" / rec["brief"], label=rec["label"]),
                         encoding="utf-8")
        rec["nudged"] = True
        note("관리자 세션이 없어 재촉 1회")
        send(nudge)
        deadline = time.time() + RELAY_NUDGE_WAIT_SEC
        while time.time() < deadline and not spawned():
            time.sleep(10)
    rec["state"] = "spawned" if spawned() else "failed"
    note("관리자 세션 확인" if rec["state"] == "spawned" else "관리자 세션이 생기지 않았습니다 - 사람이 확인해야 합니다")
    return 0 if rec["state"] == "spawned" else 1


# ----------------------------------------------------------------- CLI
def main(argv=None):
    p = argparse.ArgumentParser(description="함대 제어 (준비/실행/일시 중지/완전 중지/라운드 실행)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("status", "prepare", "run", "pause", "stop", "round"):
        s = sub.add_parser(c)
        s.add_argument("--by", default="CLI")
    r = sub.add_parser("_relay")
    r.add_argument("--round", type=int, required=True)
    a = p.parse_args(argv)
    if a.cmd == "_relay":
        return _relay_worker(a.round)
    fn = {"status": lambda: status(), "prepare": lambda: prepare(a.by), "run": lambda: resume(a.by),
          "pause": lambda: pause(a.by), "stop": lambda: stop(a.by), "round": lambda: launch_round(a.by)}[a.cmd]
    out = fn()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
