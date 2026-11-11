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
    python3 tools/fleet_ctl.py round            # ready 에서만. 새 관리자 라운드 (클로 경유). 브리프는 그 라운드만의
                                                # 확정본이 있으면 그것, 없으면 표준 브리프(할 일 = NEW 요청)

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
#: 표준 브리프 (2026-11-10 태석님 지시 - 라운드 내용은 웹 요청으로 정한다). 그 라운드만의 확정 브리프가 없으면
#: 이 파일로 다음 번호 라운드를 띄운다. 할 일은 NEW 요청 전부, 상시 루틴은 AIMEM.md `8.0-8`.
#: `{round}` `{date}` `{rev}` `{workspace}` 를 채워 그 라운드 작업 공간의 `brief.md` 로 굳힌 뒤 그 파일을 보낸다.
STANDARD_BRIEF = "manager-round-standard.md"
#: 라운드 기록 폴더 `rounds/R<N>/` - git 에 올라간다. 띄울 때 만들고 그 라운드의 브리프(`brief.md`)를 넣고,
#: 관리자가 종료 보고(`REPORT.md`)를 쓴다. **결과물은 여기 두지 않는다** - 라운드는 과정이고 결과물은 여러
#: 라운드에 걸쳐 만들어지므로 프로젝트 폴더 `projects/<이름>/` 한 곳에 쌓인다 (2026-11-10 태석님 정정).
ROUNDS_DIR = "rounds"


def round_workspace(n):
    """그 라운드 작업 공간의 저장소 상대 경로 (`rounds/R7`)."""
    return f"{ROUNDS_DIR}/R{int(n)}"
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
    last_written = best[0] if best else 0
    if best and best[0] in used:
        best = None   # 이미 띄운 라운드의 브리프는 다시 쓰지 않는다
    if best is None and (d / STANDARD_BRIEF).is_file():
        # 그 라운드만의 브리프가 없다 -> 표준 브리프로 다음 번호. 번호는 지금까지 쓰인 것(브리프 파일·전달 기록·세션 라벨) 다음.
        n = max([last_written, *used]) + 1
        return {"round": n, "file": STANDARD_BRIEF, "standard": True, "workspace": round_workspace(n),
                "drafts": sorted(drafts), "used_rounds": sorted(used)}
    return {"round": best[0] if best else None, "file": best[1].name if best else None, "standard": False,
            "workspace": round_workspace(best[0]) if best else None,
            "drafts": sorted(drafts), "used_rounds": sorted(used)}


def _open_requests():
    """아직 안 끝난 요청의 (id, 프로젝트). 라운드를 띄울 때 '이 라운드가 다룰 것' 으로 적어 둔다."""
    out = []
    d = fleet.ROOT / ".aimem" / "requests"
    try:
        files = sorted(d.glob("*.json"))
    except OSError:
        return out
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and str(rec.get("status") or "").upper() not in ("DONE", "REJECTED"):
            pr = rec.get("project")
            out.append((str(rec.get("id") or f.stem), pr if isinstance(pr, str) else ""))
    return out


def _write_round_record(n, at, brief_name):
    """`rounds/R<N>/round.json` - 이 라운드가 언제 떴고 어떤 요청·프로젝트를 다루는지 (git 에 남는 기록).

    모니터의 프로젝트 카드가 "이 프로젝트는 몇 라운드를 거쳤나" 를 여기서 셉니다 - 관리자가 `PROGRESS.md` 를
    빠뜨려도 라운드 수는 맞게.
    """
    reqs = _open_requests()
    rec = {"round": int(n), "at": at.isoformat(timespec="seconds"), "brief": brief_name,
           "requests": [i for i, _ in reqs], "projects": sorted({p for _, p in reqs if p})}
    d = fleet.ROOT / round_workspace(n)
    d.mkdir(parents=True, exist_ok=True)
    (d / "round.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return rec


def _mark_round_record_failed(n):
    """관리자가 뜨지 않은 라운드는 `round.json` 에 `state: failed` 를 적는다 - 프로젝트 카드가 '거친 라운드' 로 세지 않게."""
    f = fleet.ROOT / round_workspace(n) / "round.json"
    try:
        rec = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(rec, dict):
            return
        rec["state"] = "failed"
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except (OSError, ValueError):
        pass


def _round_brief_path(b, at):
    """보낼 브리프의 절대 경로. 라운드 작업 공간을 만들고, 브리프를 그 안의 `brief.md` 로 굳힌다.

    표준 브리프는 번호·날짜·REV·작업 공간을 채운다. 그 라운드만의 확정 브리프는 글자 그대로 옮기고
    작업 공간 안내 한 줄을 덧붙인다. 어느 쪽이든 **보낸 그대로가 작업 공간에 남는다.**
    """
    ws = round_workspace(b["round"])
    text = (fleet.ROOT / ".aimem" / "briefs" / b["file"]).read_text(encoding="utf-8")
    if b.get("standard"):
        for k, v in (("{round}", str(b["round"])), ("{date}", at.strftime("%Y-%m-%d %H:%M")),
                     ("{rev}", str(fleet.read_rev())), ("{workspace}", ws)):
            text = text.replace(k, v)
    else:
        text = text.rstrip("\n") + (f"\n\n## 라운드 기록과 결과물\n종료 보고는 `{ws}/REPORT.md` 에도 씁니다. 결과물은 라운드 폴더가 아니라 "
                                    f"요청의 프로젝트 폴더 `projects/<프로젝트>/` 에 쌓습니다 (`8.0-8`).\n")
    d = fleet.ROOT / ws
    d.mkdir(parents=True, exist_ok=True)
    out = d / "brief.md"
    out.write_text(text, encoding="utf-8")
    return out


def rounds_from_labels(labels):
    out = set()
    for lab in labels:
        m = re.search(r"\bR(\d+)\b", lab or "")
        if m:
            out.add(int(m.group(1)))
    return out


def _db_rounds():
    """핸드오프 로그에 관리자로 남은 라운드 번호 (`관리자(R6)`, `Manager (R5)`).

    세션은 끝나면 거두고 전달 기록은 버튼으로 띄운 것만 남으므로, 그 둘만 보면 **이미 돈 라운드의 브리프를
    다음 라운드로 고릅니다**(2026-11-10 실측: 게이트웨이가 내려가 있을 때 R6 브리프가 다시 뽑혔다). DB 가 정본입니다.
    """
    out = set()
    db = _aimem_dir() / "aimem.db"
    if not db.is_file():
        return out
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            for (actor,) in con.execute("SELECT DISTINCT actor FROM events WHERE kind='handoff'"):
                m = re.search(r"(?:관리자|Manager)\s*\(R(\d+)\)", actor or "")
                if m:
                    out.add(int(m.group(1)))
        finally:
            con.close()
    except Exception:  # noqa: BLE001 - DB 를 못 읽어도 제어 화면은 떠야 한다
        pass
    return out


def _relay_rounds():
    used = _db_rounds()
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
    relay = relay_status()
    # '실행' 인데 도는 것이 없다 = 라운드가 끝났다 (REV 153). 전에는 이 상태에서 '준비' 도 '라운드 실행' 도 꺼져 있어
    # 일시 중지 → 준비 로 돌아가야 했고, 거기서 '실행' 을 누르면 다시 이 상태로 돌아와 새 요청이 처리되지 않았다.
    idle = (md == "running" and not rr and not manager_running_now and not any(g["runner"] for g in graphs)
            and not _relay_busy(relay))
    resumable = any(g["unfinished"] and not g["runner"] for g in graphs)
    can = {
        "prepare": (md in ("stopped", "paused", "ready") or idle) and not manager_running_now and not rr,
        # '실행' 은 멈춘 라운드를 잇는 단추다 - 준비 상태에서 이을 것이 없으면 누를 일이 없다 (새 라운드는 '라운드 실행')
        "run": md in ("paused", "stopped") or (md == "ready" and resumable),
        "pause": md == "running",
        # 완전 중지는 "돌고 있는 것을 죽이는" 동작 - 죽일 게 없는 ready 에선 끕니다 (2026-11-10 점검 5번)
        "stop": md in ("running", "paused") or bool(rr),
        "round": (md == "ready" or idle) and bool(b["file"]) and not manager_running_now,
    }
    return {"mode": md, "label": MODE_LABEL.get(md), "at": m.get("at"), "by": m.get("by"), "note": m.get("note"),
            "default": bool(m.get("default")), "running_runs": len(rr),
            "graphs": [{"id": g["id"], "runner": bool(g["runner"]), "counts": g["counts"]} for g in graphs],
            "brief": b, "prepare": last_prepare(), "relay": relay, "can": can, "idle": idle,
            "chain_modes": ["stop", "renew", "autonomous"],     # 상한에 닿았을 때 할 일 - 화면은 서버가 아는 것만 보인다
            "last_round": _last_round(relay),
            "chain": {k: v for k, v in chain_state().items() if k != "log"} | {"last": (chain_state().get("log") or [None])[-1]}}


def _last_round(relay):
    """가장 최근에 띄운 라운드의 요약 - 끝난 관리자 세션은 게이트웨이 목록에서 사라지므로(R7~R11 실측) 화면이
    옛 세션(R6)을 '최근 관리자' 로 보였다. 전달 기록과 보고 파일에서 직접 읽는다."""
    if not isinstance(relay, dict) or not relay.get("round"):
        return None
    try:
        n = int(relay["round"])
    except (TypeError, ValueError):
        return None
    rep = fleet.ROOT / round_workspace(n) / "REPORT.md"
    return {"round": n, "label": relay.get("label"), "at": relay.get("at"), "state": relay.get("state"),
            "report_status": round_report_status(n), "report": f"{round_workspace(n)}/REPORT.md" if rep.is_file() else None}


def _relay_busy(relay):
    """관리자에게 전달하는 중(아직 세션이 안 보이는 구간) - 이때는 도는 것이 없어 보여도 라운드가 끝난 것이 아니다."""
    return isinstance(relay, dict) and relay.get("state") in ("launching", "relaying")


def round_over():
    """함대가 '실행' 인데 작업자도 그래프 실행기도 전달도 없다 - 라운드가 끝났다. 관리자 세션은 부르는 쪽이 본다."""
    return (mode() == "running" and not running_runs() and not any(g["runner"] for g in graphs_overview())
            and not _relay_busy(relay_status()))


def _used_rounds():
    used = _relay_rounds()
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
    if mode() == "ready" and not any(gi["unfinished"] and not gi["runner"] for gi in graphs_overview()):
        # 이을 것이 없는데 '실행' 으로 바꾸면 '라운드 실행' 이 꺼져 새 요청이 처리되지 않는다 (2026-11-11 태석님)
        return {"ok": False, "mode": "ready",
                "error": "이어 갈 라운드가 없습니다 - 새 요청은 '라운드 실행' 으로 띄웁니다 ('실행' 은 멈춘 라운드를 이을 때만 씁니다)"}
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
    """새 라운드. 확정 브리프가 있고 관리자가 없을 때만. **준비(ready)** 에서, 또는 앞 라운드가 끝난 채
    '실행' 으로 남아 있을 때(`round_over`) - 그때는 준비 점검을 여기서 먼저 돌립니다 (REV 153)."""
    if round_over():
        res = prepare(by)        # 관리자가 아직 살아 있으면 여기서 막힌다 ("실행 중인 관리자 없음")
        if not res["ok"]:
            bad = [c["name"] + (f" ({c['detail']})" if c.get("detail") else "") for c in res["checks"] if c["required"] and not c["ok"]]
            return {"ok": False, "mode": mode(), "checks": res["checks"],
                    "error": "준비 점검에서 막혀 라운드를 띄우지 않았습니다: " + "; ".join(bad)[:300]}
    if mode() != "ready":
        return {"ok": False, "error": f"'준비' 상태에서만 새 라운드를 띄웁니다 (지금: {MODE_LABEL.get(mode())}). 먼저 '준비' 를 누르십시오"}
    b = latest_brief()
    if not b["file"]:
        return {"ok": False, "error": f"다음 라운드 브리프가 없습니다 (표준 브리프 .aimem/briefs/{STANDARD_BRIEF} 또는 manager-round<N>-<날짜>.md). 초안: " + (", ".join(b["drafts"]) or "없음")}
    _SESS_CACHE["at"] = 0
    if manager_running():
        return {"ok": False, "error": "이미 실행 중인 관리자가 있습니다"}
    n = b["round"]
    at = dt.datetime.now()
    label = f"관리자 R{n} (Opus) {at.strftime('%Y-%m-%d')}"
    brief = _round_brief_path(b, at)
    _write_round_record(n, at, b["file"])
    relay = _relay_dir()
    msg = relay / f"r{n}-instruction.md"
    msg.write_text(RELAY_TEMPLATE.format(at=at.strftime("%Y-%m-%d %H:%M"), brief=brief, label=label), encoding="utf-8")
    rec = {"round": n, "label": label, "brief": b["file"], "brief_path": str(brief), "workspace": round_workspace(n), "by": by, "at": _now(), "state": "launching",
           "session_key": f"agent:coding:relay-r{n}-{at.strftime('%H%M%S')}", "nudged": False, "log": []}
    _write_relay(rec)
    set_mode("running", by, f"라운드 R{n} 실행 ({b['file']})")
    log = open(relay / f"r{n}.log", "a", encoding="utf-8")
    subprocess.Popen([sys.executable, str(HERE / "fleet_ctl.py"), "_relay", "--round", str(n)],
                     cwd=str(fleet.ROOT), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    return {"ok": True, "round": n, "label": label, "brief": b["file"], "workspace": round_workspace(n), "mode": "running"}


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
        nudge.write_text(NUDGE_TEMPLATE.format(brief=rec.get("brief_path") or fleet.ROOT / ".aimem" / "briefs" / rec["brief"],
                                               label=rec["label"]),
                         encoding="utf-8")
        rec["nudged"] = True
        note("관리자 세션이 없어 재촉 1회")
        send(nudge)
        deadline = time.time() + RELAY_NUDGE_WAIT_SEC
        while time.time() < deadline and not spawned():
            time.sleep(10)
    rec["state"] = "spawned" if spawned() else "failed"
    if rec["state"] == "failed":
        _mark_round_record_failed(n)
    note("관리자 세션 확인" if rec["state"] == "spawned" else "관리자 세션이 생기지 않았습니다 - 사람이 확인해야 합니다")
    if rec["state"] != "spawned":
        if chain_state().get("on"):
            _chain_stop(chain_state(), "error", f"R{n} 관리자가 뜨지 않았습니다 - 전달 기록(.aimem/relay/r{n}.json)을 확인하십시오", n)
        return 1
    if chain_state().get("on"):
        note("이어 달리기 켜짐 - 라운드가 끝나면 목표를 보고 다음 라운드를 띄웁니다")
        return _chain_wait_and_step(n)
    return 0


# ----------------------------------------------------------------- 이어 달리기 (REV 155)
# 프로젝트 목표가 남아 있으면 라운드가 끝난 뒤 다음 라운드를 **함대가 스스로** 띄웁니다. 2026-11-10 밤에는 사람이
# (클로드 코드가) 손으로 이었습니다: 보고와 `PROGRESS.md` 의 `## 목표` 를 읽고 → 남은 목표를 요청으로 넣고 → 준비 → 라운드.
# 켜는 것은 사람입니다(엔진은 태석님). 유료 관리자가 라운드마다 뜨므로 **연속 상한**과 **멈춤 조건**이 꼭 있습니다.
CHAIN_MAX_ROUNDS = 10            # 사람이 고를 수 있는 연속 상한의 최대
CHAIN_HARD_ROUNDS = 30           # 상한을 새로 이어 가며(`renew`) 돌 때의 안전 상한(모두 합친 라운드 수) - 여기 닿으면 사람이 다시 켠다
CHAIN_DEFAULT_ROUNDS = 3
CHAIN_WAIT_SEC = 6 * 3600        # 한 라운드를 기다리는 최대 시간 (넘으면 이어 달리기를 끈다)
CHAIN_POLL_SEC = 45
_GOALS_HEAD = re.compile(r"^##[ \t]*(?:목표|goals)\b[^\n]*$", re.MULTILINE | re.IGNORECASE)   # aimem_monitor.server 와 같은 식
_GOALS_NEXT = re.compile(r"^##?[ \t]+\S", re.MULTILINE)
_GOAL_ITEM = re.compile(r"^[ \t]{0,8}[-*][ \t]+\[([ xX])\][ \t]+(\S.*)$")
_REPORT_STATUS = re.compile(r"상태\s*[:：]\s*\**\s*(DONE|PARTIAL|BLOCKED|NEEDS-[A-Z-]+)", re.IGNORECASE)


def _chain_path():
    return _aimem_dir() / "fleet-chain.json"


def chain_state():
    """`{on, project, max_rounds, rounds_done, goals_done, by, at, log}`. 파일이 없으면 `{on: False}`."""
    try:
        st = json.loads(_chain_path().read_text(encoding="utf-8"))
        return st if isinstance(st, dict) else {"on": False}
    except (OSError, ValueError):
        return {"on": False}


def _chain_write(st):
    st["log"] = (st.get("log") or [])[-30:]
    tmp = _chain_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _chain_path())


def project_goals(project):
    """`projects/<이름>/PROGRESS.md` 의 `## 목표` 체크리스트 -> [(끝났나, 글)] . 절이 없거나 비면 []."""
    try:
        text = (fleet.ROOT / "projects" / project / "PROGRESS.md").read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return []
    m = _GOALS_HEAD.search(text)
    if not m:
        return []
    nxt = _GOALS_NEXT.search(text, m.end())
    out = []
    for line in text[m.end():(nxt.start() if nxt else len(text))].splitlines()[:2000]:
        g = _GOAL_ITEM.match(line)
        if g:
            out.append((g.group(1) != " ", g.group(2).strip()))
        elif out and line[:1] in (" ", "\t") and line.strip() and not line.lstrip().startswith(("-", "*", ">", "#")):
            # 목표 한 항목이 여러 줄에 걸쳐 적힌 경우 - 이어지는 들여쓴 줄을 붙인다 (R12: 요청에 "…재검수를" 에서 끊긴 글이 갔다)
            done, t = out[-1]
            if len(t) < 600:
                out[-1] = (done, (t + " " + line.strip())[:600])
    return out[:200]


def round_report_status(n):
    """`rounds/R<N>/REPORT.md` 의 `상태: DONE|PARTIAL|BLOCKED|…`. 보고가 없거나 못 읽으면 None."""
    try:
        text = (fleet.ROOT / round_workspace(n) / "REPORT.md").read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return None
    m = _REPORT_STATUS.search(text)
    return m.group(1).upper() if m else None


def _goal_projects():
    """목표 체크리스트(`PROGRESS.md` 의 `## 목표`)가 있는 프로젝트 이름들."""
    out = []
    try:
        for d in sorted((fleet.ROOT / "projects").iterdir()):
            if d.is_dir() and not d.is_symlink() and re.match(fleet.PROJECT_NAME_RE, d.name) and project_goals(d.name):
                out.append(d.name)
    except OSError:
        pass
    return out


def chain_targets(st):
    """상태에서 대상 `(fleet, projects, all)` 을 읽습니다. 옛 상태(`project` 하나, `scope`)도 받아 줍니다."""
    if st.get("all") or st.get("scope") == "all":
        return True, [], True
    projects = [p for p in (st.get("projects") or []) if isinstance(p, str) and p]
    if not projects and st.get("project"):
        projects = [st["project"]]
    fleet_on = bool(st.get("fleet")) or st.get("scope") == "fleet"
    if not fleet_on and not projects and "fleet" not in st and "projects" not in st:
        return True, [], True                      # 대상이 안 적힌 옛 상태 = 열린 요청 전부
    return fleet_on, projects, False


def chain_label(fleet_on, projects, all_):
    if all_:
        return "전체(프로젝트+함대)"
    return " + ".join((["함대"] if fleet_on else []) + [f"프로젝트 {p}" for p in projects]) or "(대상 없음)"


def chain_work(fleet_on=False, projects=(), all_=False):
    """고른 대상의 남은 일. `{requests: [열린 요청 id], goals: {프로젝트: {done, total, open}}}`.

    - 함대      : 프로젝트가 없는 열린 요청 (함대 자체의 일)
    - 프로젝트들 : 그 프로젝트들의 열린 요청 + 체크 안 된 목표 (여러 개 고를 수 있다)
    - 전체      : 열린 요청 전부 + 목표 체크리스트가 있는 모든 프로젝트의 체크 안 된 목표 (나중에 생기는 프로젝트도)
    """
    reqs = _open_requests()
    if all_:
        ids, names = [i for i, _ in reqs], _goal_projects()
    else:
        want = set(projects)
        ids = [i for i, p in reqs if (not p and fleet_on) or (p and p in want)]
        names = list(projects)
    goals = {}
    for name in names:
        g = project_goals(name)
        if g:
            goals[name] = {"done": sum(1 for d, _ in g if d), "total": len(g), "open": [t for d, t in g if not d]}
    return {"requests": ids, "goals": goals}


def chain_set(on, project=None, max_rounds=None, by="사람", scope=None, projects=None, fleet_on=None, all_=None, autonomous=False,
              renew=False):
    """이어 달리기를 켜거나 끕니다. 대상은 **함대 · 프로젝트(여러 개) · 전체** 가운데 고릅니다 (2026-11-11 태석님).

    `fleet_on`(함대), `projects`(이름 목록), `all_`(전체 = 프로젝트+함대) 로 줍니다. 옛 인자 `project`·`scope` 도 받습니다 -
    아무것도 안 주면 전체입니다. 켤 때 지금의 열린 요청과 목표 체크 수를 기준으로 적어 둡니다.
    """
    if not on:
        st = chain_state()
        if st.get("on"):                      # 이미 스스로 멈춘 뒤라면 그 까닭을 덮지 않는다
            st["by"] = by
            _chain_stop(st, "off", f"{by} 이(가) 껐습니다")
        return {"ok": True, "chain": st}
    names = [str(p).strip() for p in (projects or []) if isinstance(p, str) and str(p).strip()]
    if project and str(project).strip() and str(project).strip() not in names:
        names.append(str(project).strip())
    if scope is not None and scope not in ("fleet", "project", "all"):
        return {"ok": False, "error": "범위는 함대(fleet) · 프로젝트(project) · 전체(all) 가운데 하나입니다"}
    is_all = bool(all_) or scope == "all"
    is_fleet = bool(fleet_on) or scope == "fleet"
    if scope == "fleet":
        names = []
    if scope == "project" and not names:
        return {"ok": False, "error": "프로젝트를 하나 이상 고르십시오. 함대만 돌리려면 '함대', 다 돌리려면 '전체' 를 고르십시오"}
    if not is_all and not is_fleet and not names:
        if scope is None and fleet_on is None and projects is None and all_ is None:
            is_all = True                           # 아무것도 안 주면 전체 (CLI 에서 `chain on` 만 쳤을 때)
        else:
            return {"ok": False, "error": "무엇을 이어 달릴지 하나 이상 고르십시오 - 함대, 프로젝트(여러 개 가능), 또는 전체"}
    bad = [n for n in names if not re.match(fleet.PROJECT_NAME_RE, n)]
    if bad:
        return {"ok": False, "error": f"프로젝트 이름이 올바르지 않습니다: {', '.join(bad)[:80]} (한글·영문·숫자·`-`·`_`)"}
    if is_all:
        is_fleet, names = True, []
    names = sorted(set(names))
    # **상한 라운드는 언제나 있다** (2026-11-11 태석님: "끝까지 옵션도 내부적으로는 상한 라운드를 지켜야 해").
    # 상한에 닿았을 때 무엇을 하느냐가 다르다: 멈춤 / 새 묶음으로 이어 감(`renew` = 끝날 때까지) / 완전 자율 종주(`autonomous`).
    # 새 묶음은 라운드 수를 0 부터 다시 세고 새 관리자로 이어 간다. 옛 호출의 `max_rounds=0` 은 "기본 상한 + 이어 감" 으로 읽는다.
    try:
        mx = int(max_rounds if max_rounds is not None else CHAIN_DEFAULT_ROUNDS)
    except (TypeError, ValueError):
        return {"ok": False, "error": "상한 라운드는 숫자여야 합니다"}
    renew = bool(renew) or bool(autonomous)
    if mx == 0:
        mx, renew = CHAIN_DEFAULT_ROUNDS, True
    if not 1 <= mx <= CHAIN_MAX_ROUNDS:
        return {"ok": False, "error": f"상한 라운드는 1~{CHAIN_MAX_ROUNDS} 입니다"}
    work = chain_work(is_fleet, names, is_all)
    st = {"on": True, "all": is_all, "fleet": is_fleet, "projects": names, "label": chain_label(is_fleet, names, is_all),
          "max_rounds": mx, "rounds_done": 0,            # 이번 묶음에서 끝난 라운드 수 (상한 `max_rounds` 까지)
          "renew": renew, "cycles": 0, "total_rounds": 0,  # 상한에 닿으면 새 묶음으로 이어 가는가 · 채운 묶음 수 · 모두 합친 라운드 수
          # 완전 자율 종주: 새 묶음으로 이어 가고, 보고가 DONE 이 아니거나 진전이 없어도 **한 번은 더** 가 본다.
          # 연달아 두 번 막히면 멈춘다(`strikes`). 안전 상한(`CHAIN_HARD_ROUNDS`)은 그대로다.
          "autonomous": bool(autonomous), "strikes": 0,
          "goals_done": sum(g["done"] for g in work["goals"].values()),     # 진전 = 이 수가 늘었거나
          "open_requests": work["requests"],                                 #        이 가운데 닫힌 요청이 생겼는가
          "by": by, "at": _now(),
          "log": [f"{_now()} 켬 ({by}) - {chain_label(is_fleet, names, is_all)}, "
                  + f"상한 {mx} 라운드, " + ("완전 자율 종주" if autonomous else "닿으면 새 묶음으로 이어 감(끝날 때까지)" if renew else "닿으면 멈춤")]}
    _chain_write(st)
    # 라운드가 이미 도는 중에 켰으면 그 라운드를 지켜볼 감시자를 따로 띄운다 (라운드를 띄울 때 켜져 있었다면 전달 작업자가 이어서 지켜본다)
    relay = relay_status() or {}
    in_flight = False
    if mode() == "running" and relay.get("state") == "spawned" and relay.get("round"):
        _SESS_CACHE["at"] = 0
        in_flight = bool(manager_running()) or not round_over()     # 끝난 라운드에는 감시자를 붙이지 않는다
    if in_flight:
        try:
            log = open(_relay_dir() / f"r{int(relay['round'])}.log", "a", encoding="utf-8")
            subprocess.Popen([sys.executable, str(HERE / "fleet_ctl.py"), "_chainwatch", "--round", str(int(relay["round"]))],
                             cwd=str(fleet.ROOT), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        except (OSError, ValueError):
            pass
    return {"ok": True, "chain": st}


def chain_decide(round_n):
    """라운드 `round_n` 이 끝난 지금 다음 라운드를 띄울까. `{action: launch|stop, why, requests, goals}` - 판정만.

    남은 일(`chain_work`)이 있고 이번 라운드에 진전이 있었으면 잇는다. 진전 = 켤 때(또는 앞 라운드 끝에) 열려 있던
    요청 가운데 닫힌 것이 생겼거나, 범위 안 프로젝트들의 목표 체크 합계가 늘었다.
    """
    st = chain_state()
    if not st.get("on"):
        return {"action": "stop", "why": "이어 달리기가 꺼져 있습니다"}
    work = chain_work(*chain_targets(st))
    open_ids, goals = work["requests"], work["goals"]
    done = sum(g["done"] for g in goals.values())
    total = sum(g["total"] for g in goals.values())
    goals_left = sum(len(g["open"]) for g in goals.values())
    base = {"requests": open_ids, "goals": goals, "done": done, "total": total}
    left = f"열린 요청 {len(open_ids)}건" + (f" · 목표 {done}/{total}" if goals else "")
    status = round_report_status(round_n)
    auto = bool(st.get("autonomous"))
    second_chance = auto and int(st.get("strikes", 0)) < 1          # 완전 자율 종주: 막혀도 한 번은 더 간다
    if not open_ids and not goals_left and status == "DONE":
        return {**base, "action": "stop", "kind": "done", "why": f"남은 일이 없습니다 ({left}) - 끝났습니다"}
    cap = int(st.get("max_rounds") or CHAIN_DEFAULT_ROUNDS)
    renew = bool(st.get("renew")) or auto or not st.get("max_rounds")     # 옛 상태의 max_rounds 0 = 이어 감
    ran = int(st.get("rounds_done", 0)) + 1
    total = int(st.get("total_rounds", st.get("rounds_done", 0))) + 1
    if renew and total >= CHAIN_HARD_ROUNDS:
        return {**base, "action": "stop", "kind": "safety", "why": f"모두 {total} 라운드를 이어 왔습니다 - 안전 상한({CHAIN_HARD_ROUNDS})이라 멈춥니다. 계속하려면 다시 켜십시오 ({left})"}
    if status != "DONE":
        if second_chance and (open_ids or goals_left):
            return {**base, "action": "launch", "strike": True, "why": f"R{round_n} 보고가 {status or '없음'} 입니다 - 완전 자율 종주라 한 번 더 갑니다 ({left})"}
        return {**base, "action": "stop", "kind": "report", "why": f"R{round_n} 보고가 {status or '없음'} 입니다 - 사람이 봐야 합니다"
                + (" (완전 자율 종주에서도 연달아 두 번째라 멈춥니다)" if auto else "")}
    closed = [i for i in (st.get("open_requests") or []) if i not in open_ids]
    if not closed and done <= int(st.get("goals_done", 0)):
        if second_chance:
            return {**base, "action": "launch", "strike": True, "why": f"R{round_n} 동안 닫힌 요청도 늘어난 목표 체크도 없습니다 - 완전 자율 종주라 한 번 더 갑니다 ({left})"}
        return {**base, "action": "stop", "kind": "stuck", "why": f"R{round_n} 동안 닫힌 요청도 늘어난 목표 체크도 없습니다 ({left}) - 같은 자리를 돌지 않게 멈춥니다"
                + (" (연달아 두 번째)" if auto else "")}
    if ran >= cap:
        if renew:
            return {**base, "action": "launch", "new_cycle": True,
                    "why": f"상한 {cap} 라운드를 채웠습니다 - 새 묶음({int(st.get('cycles', 0)) + 2}번째)으로 이어 갑니다 ({left})"}
        return {**base, "action": "stop", "kind": "cap", "why": f"연속 상한 {cap} 라운드에 닿았습니다 ({left})"}
    return {**base, "action": "launch", "why": f"{left} - 이어 갑니다"}


def _chain_request(project, round_n, open_, done, total):
    """남은 목표를 다음 라운드의 요청으로 넣습니다 (웹 요청 폼과 같은 길)."""
    here = str(HERE)
    if here not in sys.path:
        sys.path.insert(0, here)
    from aimem_monitor import server  # noqa: PLC0415 - 모니터가 이 모듈을 지연 import 하므로 여기서도 지연
    lines = "\n".join(f"- {t}" for t in open_[:40])
    detail = (f"R{round_n} 이 끝났고 `projects/{project}/PROGRESS.md` 의 목표는 {done}/{total} 입니다. 체크 안 된 목표가 이번 라운드의 할 일입니다:\n\n"
              f"{lines}\n\n"
              f"`PROGRESS.md` 의 R{round_n} '남은 일' 과 `rounds/R{round_n}/REPORT.md` (5)를 먼저 읽고 거기 적힌 순서대로 이어 가십시오. "
              "목표에 없는 일은 벌이지 않습니다. 검증까지 끝난 것만 체크하고, 닫지 못한 목표는 무엇이 막았는지 항목별로 적습니다. "
              "전부 닫히면 '남은 일' 에 \"없음 (목표 기준)\" 이라고 적습니다.\n\n"
              "(함대의 '이어 달리기' 가 자동으로 넣은 요청입니다 - 사람이 켰고, 목표가 다 체크되거나 진전이 없으면 스스로 멈춥니다.)")
    return server.create_request({"title": f"{project}: 남은 목표 {len(open_)}개 이어 가기 (R{round_n} 뒤 자동)",
                                  "detail": detail, "requester": "함대 이어 달리기", "project": project}, fleet.ROOT)


#: 멈춘 까닭의 종류 (2026-11-11 태석님: "30회 돌고 멈췄는지, 다른 이유가 있어 멈춘 건지, 다 끝낸 건지 적절한 메시지")
#:   done   남은 일이 없어 끝남          cap    상한 라운드를 채움(멈춤 방식)      safety 모두 합쳐 안전 상한(30)에 닿음
#:   stuck  진전 없는 라운드             report 관리자 보고가 DONE 이 아니거나 없음   error  요청·라운드를 띄우지 못함
#:   off    사람이 끔                    wait   라운드가 끝나기를 너무 오래 기다림
CHAIN_STOP_KINDS = ("done", "cap", "safety", "stuck", "report", "error", "off", "wait")


def _chain_stop(st, kind, why, round_n=None, left=None):
    """이어 달리기를 끄고 **왜 멈췄는지**를 남깁니다 - 화면이 종류별로 다른 안내를 보입니다."""
    st.update({"on": False, "at": _now(), "stopped_why": why, "stopped_kind": kind, "stopped_at": _now(),
               "stopped_round": round_n, "stopped_left": left})
    st.setdefault("log", []).append(f"{_now()} 멈춤[{kind}] - {why}")
    _chain_write(st)


def chain_step(round_n, by="이어 달리기"):
    """라운드가 끝난 뒤 한 번 부릅니다 - 멈추거나(끔), 남은 목표를 요청으로 넣고 다음 라운드를 띄웁니다."""
    d = chain_decide(round_n)
    st = chain_state()
    if d["action"] != "launch":
        if st.get("on"):
            _chain_stop(st, d.get("kind") or "report", d["why"], round_n,
                        {"requests": len(d.get("requests") or []), "goals_done": d.get("done"), "goals_total": d.get("total")})
        return {"ok": True, "launched": False, **d}
    # 체크 안 된 목표가 있는데 그 프로젝트의 열린 요청이 없으면, 남은 목표를 요청으로 넣는다 (열린 요청이 곧 할 일이다)
    filed = []
    open_projects = {p for _, p in _open_requests()}
    for name, g in d["goals"].items():
        if not g["open"] or name in open_projects:
            continue
        ok, res = _chain_request(name, round_n, g["open"], g["done"], g["total"])
        if not ok:
            _chain_stop(st, "error", f"요청을 못 넣었습니다({name}): {res.get('error')}", round_n)
            return {"ok": False, "launched": False, "why": st["stopped_why"]}
        filed.append(res.get("id"))
    st.update({"rounds_done": 0 if d.get("new_cycle") else int(st.get("rounds_done", 0)) + 1,      # 새 묶음은 0 부터 다시 센다
               "cycles": int(st.get("cycles", 0)) + (1 if d.get("new_cycle") else 0),
               "total_rounds": int(st.get("total_rounds", st.get("rounds_done", 0))) + 1,
               "goals_done": d["done"], "at": _now(),
               "strikes": (int(st.get("strikes", 0)) + 1) if d.get("strike") else 0,     # 진전이 있었으면 다시 0
               "open_requests": chain_work(*chain_targets(st))["requests"]})
    st.setdefault("log", []).append(f"{_now()} R{round_n} 끝 - {d['why']}" + (f" → 요청 {', '.join(filed)}" if filed else ""))
    _chain_write(st)
    out = launch_round(by)
    if not out.get("ok"):
        st = chain_state()
        _chain_stop(st, "error", f"다음 라운드를 못 띄웠습니다: {out.get('error')}", round_n)
    return {"ok": bool(out.get("ok")), "launched": bool(out.get("ok")), "request": (filed[0] if filed else None), "filed": filed,
            "round": out.get("round"), **d}


def _chain_wait_and_step(n):
    """전달 작업자가 관리자를 띄운 뒤 이어서 돕니다: 라운드가 끝나기를 기다렸다가 `chain_step`."""
    lock = open(_aimem_dir() / "fleet-chain.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)      # 감시자는 하나만 - 둘이면 다음 라운드를 두 번 띄운다
    except OSError:
        return 0
    deadline = time.time() + CHAIN_WAIT_SEC
    while time.time() < deadline:
        time.sleep(CHAIN_POLL_SEC)
        if not chain_state().get("on"):
            return 0                      # 사람이 껐다
        if mode() != "running":           # 사람이 멈췄다 - 이어 달리기도 내려놓는다
            _chain_stop(chain_state(), "off", f"함대가 '{MODE_LABEL.get(mode(), mode())}' 로 바뀌어 이어 달리기도 내려놓았습니다 (사람이 멈춤)", n)
            return 0
        _SESS_CACHE["at"] = 0
        if manager_running() or not round_over():
            continue
        time.sleep(20)                    # 관리자가 막 끝난 직후 - 보고 파일이 다 쓰이게 잠깐
        res = chain_step(n)
        print(f"{_now()} chain R{n}: {json.dumps({k: v for k, v in res.items() if k != 'open'}, ensure_ascii=False)}", flush=True)
        return 0
    _chain_stop(chain_state(), "wait", f"R{n} 이 {CHAIN_WAIT_SEC // 3600}시간이 지나도 끝나지 않아 기다리기를 그만두었습니다 - 관리자를 확인하십시오", n)
    return 1


# ----------------------------------------------------------------- CLI
def main(argv=None):
    p = argparse.ArgumentParser(description="함대 제어 (준비/실행/일시 중지/완전 중지/라운드 실행)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("status", "prepare", "run", "pause", "stop", "round"):
        s = sub.add_parser(c)
        s.add_argument("--by", default="CLI")
    r = sub.add_parser("_relay")
    r.add_argument("--round", type=int, required=True)
    c = sub.add_parser("chain", help="이어 달리기: 프로젝트 목표가 남으면 라운드가 끝난 뒤 다음 라운드를 스스로 띄운다")
    c.add_argument("action", choices=["on", "off", "status"])
    c.add_argument("--project", action="append", help="이어 달릴 프로젝트 (여러 번 줄 수 있다)")
    c.add_argument("--fleet", action="store_true", help="함대 자체의 일(프로젝트 없는 요청)")
    c.add_argument("--all", action="store_true", help="전체 = 프로젝트 전부 + 함대 (아무것도 안 주면 이것)")
    c.add_argument("--autonomous", action="store_true", help="완전 자율 종주: 새 묶음으로 이어 가고, 막혀도 한 번은 더 간다 (연달아 두 번 막히면 멈춤)")
    c.add_argument("--max", type=int, default=None, help=f"상한 라운드 (기본 {CHAIN_DEFAULT_ROUNDS}, 최대 {CHAIN_MAX_ROUNDS})")
    c.add_argument("--renew", action="store_true", help="상한에 닿으면 멈추지 않고 새 묶음으로 이어 간다 (끝날 때까지)")
    c.add_argument("--by", default="CLI")
    w = sub.add_parser("_chainwatch")
    w.add_argument("--round", type=int, required=True)
    a = p.parse_args(argv)
    if a.cmd == "_relay":
        return _relay_worker(a.round)
    if a.cmd == "_chainwatch":
        return _chain_wait_and_step(a.round)
    if a.cmd == "chain":
        out = ({"ok": True, "chain": chain_state()} if a.action == "status"
               else chain_set(a.action == "on", None, a.max, a.by, projects=a.project, fleet_on=(a.fleet or None), all_=(a.all or None),
                                    autonomous=a.autonomous, renew=a.renew))
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0 if out.get("ok", True) else 1
    fn = {"status": lambda: status(), "prepare": lambda: prepare(a.by), "run": lambda: resume(a.by),
          "pause": lambda: pause(a.by), "stop": lambda: stop(a.by), "round": lambda: launch_round(a.by)}[a.cmd]
    out = fn()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
