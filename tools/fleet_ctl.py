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
    python3 tools/fleet_ctl.py round            # ready 에서만. 새 관리자 라운드. 브리프는 그 라운드만의
                                                # 확정본이 있으면 그것, 없으면 표준 브리프(할 일 = NEW 요청)

**새 라운드는 사람이 판단해서 누릅니다** (`round`). `run` 은 진행 중이던 라운드만 이어 돌리고
새 관리자를 띄우지 않습니다. 관리자는 엔진이 **직접 세션으로** 띄웁니다 (`fleet_rt.sessions.spawn`,
`role="manager"`, id `M-R<N>-<HHMMSS>`, 설계 `docs/FLEET-ENGINE-V2.md` 3.3). 관리자가 도는지·끝났는지는
세션 폴더(`.aimem/sessions/M-…/`)가 정본입니다 - 다른 프로그램에 묻지 않습니다.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
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
#: 라운드 기록에 관리자 세션 id 를 적은 뒤 세션 폴더가 생기기까지 봐 주는 시간. 넘으면 그 관리자는 lost.
LAUNCH_GRACE_SEC = 60


def round_workspace(n):
    """그 라운드 작업 공간의 저장소 상대 경로 (`rounds/R7`)."""
    return f"{ROUNDS_DIR}/R{int(n)}"


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _round_dir(n, create=True):
    """`rounds/R<N>` 의 절대 경로. `rounds/` 나 `R<N>` 가 심볼릭 링크이거나 저장소 밖으로 풀리면 ValueError.

    작업자도 `rounds/` 에 쓸 수 있다 - 링크를 심어 두면 엔진이 브리프·기록·마감을 저장소 밖에 쓰게 된다 (2026-11-12 검수).
    """
    root = pathlib.Path(fleet.ROOT)
    top = root / ROUNDS_DIR
    d = top / f"R{int(n)}"
    for p in (top, d):
        if p.is_symlink():
            raise ValueError(f"{p.relative_to(root)} 가 심볼릭 링크라 쓰지 않습니다")
    if create:
        d.mkdir(parents=True, exist_ok=True)
    try:
        d.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"{round_workspace(n)} 가 저장소 밖으로 풀려 쓰지 않습니다") from None
    return d


def _write_text_replace(path, text):
    """임시 파일에 쓰고 옮긴다 - 그 자리에 심어 둔 링크를 따라가지 않고 링크 자체를 바꾼다."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _service_env():
    # 배경 프로세스는 세션 표식 없이 띄운다 - 세션 안에서 불려도 그 세션과 함께 정리되지 않게 (`fleet_rt.base.service_env`).
    from fleet_rt.base import service_env  # noqa: PLC0415
    return service_env()


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
    # 임시 파일은 호출마다 다른 이름 - 고정 이름이면 동시에 부른 둘 중 하나가 남이 옮긴 파일을 옮기려다 터진다
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
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
    rec = read_mode()
    m = rec["mode"]
    # 모드 파일이 없거나 깨졌으면 띄우지 않습니다. '실행' 은 사람이 눌러 파일에 적힌 것만 인정합니다 -
    # 임시 폴더에서 도는 검사·변이 시험이 기본값(실행)을 타고 진짜 하네스를 띄운 적이 있습니다 (2026-11-12).
    if m in SPAWN_MODES and not rec.get("default"):
        return True, ""
    if os.environ.get(FORCE_ENV) == "1":
        return True, f"{FORCE_ENV}=1 로 우회 (모드 {m})"
    if rec.get("default"):
        return False, ("함대 모드 파일(.aimem/fleet-mode.json)이 없거나 읽히지 않아 작업자를 띄우지 않습니다. "
                       "사람이 '준비' → '실행' 을 눌러야 합니다")
    return False, (f"함대가 '{MODE_LABEL.get(m, m)}' 상태라 작업자를 띄우지 않습니다 "
                   f"(.aimem/fleet-mode.json). 이어 가려면 사람이 '실행' 을 눌러야 합니다")


# ----------------------------------------------------------------- 조회
def running_runs():
    out = []
    # `fleet._list_runs` 는 옛 실행 파일과 새 세션 폴더를 함께 준다 - 여기서 직접 훑으면 세션을 놓쳐
    # '완전 중지' 가 그래프 밖에서 띄운 작업자를 살려 둔다 (2026-11-12 통합 검사에서 발견).
    for rid in fleet._list_runs():
        if rid.endswith(".brief"):
            continue
        try:
            state, _ = fleet._run_state(rid)
        except Exception:  # noqa: BLE001
            continue
        if state == "running":
            meta = fleet._run_meta(rid) or {}
            if meta.get("role") == "manager":
                continue   # 관리자도 같은 세션 폴더에 있다 - 작업자가 아니다 (관리자는 `manager_running`)
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
    `used` 는 이미 쓰인 라운드 번호들 - 없으면 `_used_rounds()` 로 셉니다."""
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
        # 그 라운드만의 브리프가 없다 -> 표준 브리프로 다음 번호. 번호는 지금까지 쓰인 것(브리프 파일·라운드 기록·관리자 세션) 다음.
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


def _write_round_record(n, at, brief_name, session=None):
    """`rounds/R<N>/round.json` - 이 라운드가 언제 떴고 어떤 요청·프로젝트를 다루는지 (git 에 남는 기록).

    모니터의 프로젝트 카드가 "이 프로젝트는 몇 라운드를 거쳤나" 를 여기서 셉니다 - 관리자가 `PROGRESS.md` 를
    빠뜨려도 라운드 수는 맞게. `session` 은 그 라운드의 관리자 세션 id - 띄우기 **전에** 적어 두므로 세션 폴더가
    아직 없으면 '띄우는 중' 으로 읽습니다.
    """
    reqs = _open_requests()
    rec = {"round": int(n), "at": at.isoformat(timespec="seconds"), "brief": brief_name,
           "requests": [i for i, _ in reqs], "projects": sorted({p for _, p in reqs if p})}
    if session:
        rec["session"] = str(session)
    d = _round_dir(n)
    _write_text_replace(d / "round.json", json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
    return rec


def _mark_round_record_failed(n):
    """관리자가 뜨지 않은 라운드는 `round.json` 에 `state: failed` 를 적는다 - 프로젝트 카드가 '거친 라운드' 로 세지 않게."""
    try:
        f = _round_dir(n, create=False) / "round.json"
        rec = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(rec, dict):
            return
        rec["state"] = "failed"
        _write_text_replace(f, json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
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
    out = _round_dir(b["round"]) / "brief.md"
    _write_text_replace(out, text)
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

    라운드 기록 폴더(`rounds/R<N>/`)는 R7 부터만 있으므로, 그 앞 라운드는 여기서만 셉니다 - 빠뜨리면 **이미 돈
    라운드의 브리프를 다음 라운드로 고릅니다**(2026-11-10 실측: R6 브리프가 다시 뽑혔다).
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


def _record_rounds():
    """`rounds/R<N>/round.json` 이 있는 라운드 번호. 띄운 라운드는 (관리자가 떴든 못 떴든) 모두 여기 남는다."""
    out = set()
    try:
        for f in (fleet.ROOT / ROUNDS_DIR).glob("R*/round.json"):
            m = re.fullmatch(r"R(\d+)", f.parent.name)
            if m:
                out.add(int(m.group(1)))
    except OSError:
        pass
    return out


def _used_rounds():
    """이미 쓰인 라운드 번호 = 라운드 기록 폴더 ∪ 관리자 세션 ∪ 핸드오프 로그의 관리자 라운드."""
    return _record_rounds() | {s["round"] for s in manager_sessions() if isinstance(s.get("round"), int)} | _db_rounds()


# ----------------------------------------------------------------- 관리자 세션
def _sessions_root():
    # `fleet._sessions_root()` 와 같은 곳 - 작업자·관리자가 한 저장소(표식 ENV_ROOT 하나)에 있어야 고아 청소가 둘 다 본다.
    return _aimem_dir() / "sessions"


def _rt():
    from fleet_rt import sessions  # noqa: PLC0415 - 모드만 읽는 호출(`fleet.py spawn` 의 문지기)은 런타임을 들이지 않는다
    return sessions


def manager_sessions():
    """관리자 세션들, 시작 순(가장 최근이 끝). 세션 폴더만 읽는다 - 5초마다 불려도 되게 /proc 훑기는 한 번.

    한 줄: `{id, label, round, status, started, ended, last_event_at, orphaned, by, brief, workspace}`.
    status 는 `running|done|failed|killed|timeout|stalled|lost` (`fleet_rt.sessions.state`).
    """
    root = _sessions_root()
    try:
        # 관리자 id 꼴(`M-R<N>-…`)로 먼저 거른다 - 작업자 세션 수백 개의 meta.json 을 다 읽지 않으려고.
        dirs = [d for d in root.iterdir() if d.name.startswith("M-R") and d.is_dir()]
    except OSError:
        return []
    if not dirs:
        return []
    rt = _rt()
    live = rt.live_index(root)
    out = []
    for d in dirs:
        meta = rt.load_meta(d)
        if not isinstance(meta, dict) or meta.get("role") != "manager":
            continue
        st = rt.state(d, live=live)
        extra = meta.get("extra") if isinstance(meta.get("extra"), dict) else {}
        rn = meta.get("round")
        out.append({"id": d.name, "label": meta.get("label") or d.name,
                    "round": rn if isinstance(rn, int) and not isinstance(rn, bool) else None,
                    "status": st["state"], "why": st.get("why"), "started": meta.get("started"), "ended": st.get("ended"),
                    "last_event_at": st.get("last_event_at"), "orphaned": bool(st.get("orphaned")),
                    "by": extra.get("by"), "brief": extra.get("brief"), "workspace": extra.get("workspace")})
    out.sort(key=lambda s: (str(s.get("started") or ""), s["id"]))
    return out


def manager_running():
    """지금 도는 관리자 세션들 (`manager_sessions` 가운데 running)."""
    return [s for s in manager_sessions() if s["status"] == "running"]


def active_round():
    """도는 관리자의 라운드 번호, 없으면 None. `fleet.current_round()` 가 작업자 실행에 라운드를 적을 때 부른다."""
    run = manager_running()
    return run[-1]["round"] if run else None


def _round_record(n):
    try:
        rec = json.loads((fleet.ROOT / round_workspace(n) / "round.json").read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def manager_status(sessions_list=None):
    """가장 최근 라운드의 관리자. `public_state()["manager"]` 이고, 없으면 None.

    `{round, label, session, state, by, at, ended, brief, workspace, last_event_at}`.
    state 는 세션 상태(`running|done|failed|killed|timeout|stalled|lost`)에 둘이 더해진다:
    `launching`(라운드 기록에 세션 id 는 적혔는데 폴더가 아직 없거나 감독이 막 뜨는 중), 그리고 띄우기가
    실패한 라운드는 `failed`. 이 엔진 전에 띄운 라운드(기록에 `session` 칸이 없음)는 관리자 정보가 없어 None.
    """
    mgrs = manager_sessions() if sessions_list is None else sessions_list
    rounds = _record_rounds() | {s["round"] for s in mgrs if isinstance(s.get("round"), int)}
    if not rounds:
        return None
    n = max(rounds)
    rec = _round_record(n)
    mine = [s for s in mgrs if s.get("round") == n]
    want = rec.get("session")
    s = next((x for x in reversed(mine) if x["id"] == want), None) or (mine[-1] if mine else None)
    if s is not None:
        state = s["status"]
        if state == "running" and s.get("why") == "띄우는 중":
            state = "launching"
        return {"round": n, "label": s["label"], "session": s["id"], "state": state, "by": s.get("by"),
                "at": s.get("started"), "ended": s.get("ended"), "brief": s.get("brief") or rec.get("brief"),
                "workspace": s.get("workspace") or round_workspace(n), "last_event_at": s.get("last_event_at")}
    if not want:
        return None
    try:
        age = time.time() - dt.datetime.fromisoformat(str(rec.get("at"))).timestamp()
    except (TypeError, ValueError):
        age = None
    # 기록만 있고 폴더가 끝내 안 생겼다(띄우던 프로세스가 죽음) - '띄우는 중' 으로 남겨 두면 '라운드 실행' 이 영영 꺼진다
    # 앞날의 시각(음수)도 늦은 것으로 - 작업자가 그렇게 적은 기록 하나가 '띄우는 중' 으로 남아 라운드를 막지 않게
    late = age is None or age < 0 or age > LAUNCH_GRACE_SEC
    return {"round": n, "label": None, "session": want,
            "state": "failed" if rec.get("state") == "failed" else ("lost" if late else "launching"),
            "by": rec.get("by"), "at": rec.get("at"), "ended": None, "brief": rec.get("brief"),
            "workspace": round_workspace(n), "last_event_at": None}


def _manager_busy(mgr):
    """관리자가 뜨는 중이거나 도는 중 - 이때는 작업자가 없어 보여도 라운드가 끝난 것이 아니다."""
    return isinstance(mgr, dict) and mgr.get("state") in ("launching", "running")


def public_state(manager_labels=None, manager_running_now=None):
    """`/api/state.fleet` - 서버가 5초마다 부릅니다. 관리자 정보는 세션 폴더에서 직접 읽습니다(파일 읽기뿐).

    두 인자는 옛 호출을 받아 주려고 남겼습니다: 주면 스스로 읽은 것에 **더합니다**(라벨의 라운드 번호는 '쓰인
    라운드' 로, `manager_running_now` 가 참이면 관리자가 도는 것으로).
    """
    mgrs = manager_sessions()
    used = _record_rounds() | {s["round"] for s in mgrs if isinstance(s.get("round"), int)} | _db_rounds() \
        | rounds_from_labels(manager_labels or ())
    mgr = manager_status(mgrs)
    running_now = any(s["status"] == "running" for s in mgrs) or _manager_busy(mgr) or bool(manager_running_now)
    m = read_mode()
    rr = running_runs()
    graphs = [g for g in graphs_overview() if g["unfinished"] or g["runner"]]
    b = latest_brief(used)
    md = m["mode"]
    # '실행' 인데 도는 것이 없다 = 라운드가 끝났다 (REV 153). 전에는 이 상태에서 '준비' 도 '라운드 실행' 도 꺼져 있어
    # 일시 중지 → 준비 로 돌아가야 했고, 거기서 '실행' 을 누르면 다시 이 상태로 돌아와 새 요청이 처리되지 않았다.
    idle = md == "running" and not rr and not running_now and not any(g["runner"] for g in graphs)
    resumable = any(g["unfinished"] and not g["runner"] for g in graphs)
    can = {
        "prepare": (md in ("stopped", "paused", "ready") or idle) and not running_now and not rr,
        # '실행' 은 멈춘 라운드를 잇는 단추다 - 준비 상태에서 이을 것이 없으면 누를 일이 없다 (새 라운드는 '라운드 실행')
        "run": md in ("paused", "stopped") or (md == "ready" and resumable),
        "pause": md == "running",
        # 완전 중지는 "돌고 있는 것을 죽이는" 동작 - 죽일 게 없는 ready 에선 끕니다 (2026-11-10 점검 5번)
        "stop": md in ("running", "paused") or bool(rr) or running_now,
        "round": (md == "ready" or idle) and bool(b["file"]) and not running_now,
    }
    return {"mode": md, "label": MODE_LABEL.get(md), "at": m.get("at"), "by": m.get("by"), "note": m.get("note"),
            "default": bool(m.get("default")), "running_runs": len(rr),
            "graphs": [{"id": g["id"], "runner": bool(g["runner"]), "counts": g["counts"]} for g in graphs],
            "brief": b, "prepare": last_prepare(), "manager": mgr, "can": can, "idle": idle,
            "chain_modes": ["stop", "renew", "autonomous"],     # 상한에 닿았을 때 할 일 - 화면은 서버가 아는 것만 보인다
            "last_round": _last_round(mgr),
            "chain": {k: v for k, v in chain_state().items() if k != "log"} | {"last": (chain_state().get("log") or [None])[-1]}}


def _last_round(mgr=None):
    """가장 최근에 띄운 라운드의 요약 `{round, label, at, state, report_status, report}`.

    라운드 번호는 라운드 기록 폴더와 관리자 세션에서, 상태는 관리자 세션(없으면 기록의 `state`)에서,
    보고는 `rounds/R<N>/REPORT.md` 에서 읽는다 - 관리자 세션이 없는 옛 라운드도 요약이 나온다."""
    rounds = _record_rounds()
    if isinstance(mgr, dict) and isinstance(mgr.get("round"), int):
        rounds.add(mgr["round"])
    if not rounds:
        return None
    n = max(rounds)
    rec = _round_record(n)
    same = isinstance(mgr, dict) and mgr.get("round") == n
    rep = fleet.ROOT / round_workspace(n) / "REPORT.md"
    return {"round": n, "label": mgr.get("label") if same else None,
            "at": (mgr.get("at") if same else None) or rec.get("at"),
            "state": mgr.get("state") if same else rec.get("state"),
            "report_status": round_report_status(n), "report": f"{round_workspace(n)}/REPORT.md" if rep.is_file() else None}


def round_over():
    """함대가 '실행' 인데 관리자도 작업자도 그래프 실행기도 없다 - 라운드가 끝났다."""
    return (mode() == "running" and not _manager_busy(manager_status()) and not manager_running()
            and not running_runs() and not any(g["runner"] for g in graphs_overview()))


def status():
    m = read_mode()
    return {"mode": m, "label": MODE_LABEL.get(m["mode"]), "spawn_allowed": m["mode"] in SPAWN_MODES,
            "running_runs": running_runs(), "graphs": [g for g in graphs_overview() if g["unfinished"] or g["runner"]],
            "brief": latest_brief(), "manager": manager_status()}


# ----------------------------------------------------------------- 동작
def pause(by="사람"):
    if mode() == "stopped":
        return {"ok": False, "error": "완전 중지 상태입니다 - 일시 중지할 것이 없습니다"}
    set_mode("paused", by, "새 작업자 투입 보류, 돌고 있는 작업자는 끝까지")
    return {"ok": True, "mode": "paused", "running_runs": running_runs()}


def stop(by="사람"):
    """완전 중지. 상태를 먼저 바꿔(새 투입 차단) 관리자 세션을 끊고, 그래프·작업자를 정리한 뒤, 이 저장소의
    세션 표식을 단 남은 프로세스를 거둡니다. 끊긴 관리자의 라운드에 보고가 없으면 엔진이 최소 마감을 씁니다(설계 5.10).
    이 함수가 끝나면 이 저장소 표식을 단 프로세스는 남지 않습니다 (끊기를 거부당한 세션은 `managers`·`killed` 에 refused 로 보인다)."""
    import fleet_graph  # noqa: PLC0415 - 순환 import 회피
    set_mode("stopped", by, "관리자·작업자·그래프 즉시 종료")
    rt, root = _rt(), _sessions_root()
    # 관리자부터 끊는다 - 관리자가 포그라운드로 돌리던 그래프 실행기는 관리자 세션 안의 프로세스라 같이 끝나고,
    # 그래야 아래에서 그 그래프의 잠금이 풀려 노드를 여기서 정리할 수 있다.
    managers = []
    for s in manager_running():
        managers.append({"id": s["id"], "round": s["round"], "outcome": rt.cancel(root / s["id"], f"완전 중지 ({by})")})
    watcher = _end_chain_watcher()
    st = chain_state()
    if st.get("on"):
        _chain_stop(st, "off", f"함대를 완전 중지해 이어 달리기도 내려놓았습니다 ({by})")
    halted, killed = [], []
    for gi in graphs_overview():
        if not gi["unfinished"] or gi["runner"]:
            continue   # 관리자 밖의 실행기(`run` 이 띄운 것)는 다음 틱(기본 15초)에 스스로 정리하고 끝난다
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
    # 감독 없이 남은 하네스·setsid 한 손자 - 감독이 지키는 세션은 위에서 끊었으므로 여기서는 고아만 남아 있다.
    reaped = [{"pid": o["pid"], "session": o["session"], "killed": o.get("killed", False)}
              for o in rt.reap_orphans(root, kill=True)]
    closed = []
    for m in managers:
        if m["outcome"] in ("killed", "gone") and m["round"] is not None \
                and write_minimal_close(m["round"], f"완전 중지 ({by})", session=m["id"]):
            closed.append(m["round"])
    # 끊을 것 없이 이미 사라진(lost 등 done 이 아닌) 관리자의 마지막 라운드도 보고가 없으면 마감한다 - 감시자가 없던 라운드
    last = manager_status()
    if isinstance(last, dict) and isinstance(last.get("round"), int) and last["round"] not in closed \
            and close_if_unreported(last["round"]):
        closed.append(last["round"])
    return {"ok": True, "mode": "stopped", "managers": managers, "halted_graphs": halted, "killed": killed,
            "reaped": reaped, "chain_watcher": watcher, "closed_rounds": closed,
            "note": "관리자 밖에서 띄운 그래프 실행기는 다음 틱에 정리하고 끝납니다"}


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
                                 stdin=subprocess.DEVNULL, start_new_session=True, env=_service_env())
            started.append(gi["id"])
    mgr = manager_running()
    note = ("관리자 세션이 살아 있어 그대로 이어 갑니다" if mgr else
            "실행 중인 관리자가 없습니다 - 이어 돌린 그래프의 결과 확인과 보고는 다음 관리자 몫입니다"
            if started else "이어 갈 라운드가 없습니다 - 새 라운드는 '라운드 실행' 으로")
    return {"ok": True, "mode": "running", "resumed_graphs": started, "manager_running": bool(mgr), "note": note}


def _check(name, ok, detail="", required=True):
    return {"name": name, "ok": bool(ok), "detail": str(detail)[:200], "required": required}


def _runtime_checks():
    """하네스·키 파일·공급자 점검. 슬롯이 쓰는 하네스·공급자와 관리자(claude · opus)의 것만 본다.

    공급자는 **하나에 한 줄** - 무료 공급자 하나가 죽었을 때 어느 것인지 숨기지 않으려고. 모델을 공급자에 못 잇는
    슬롯은 참고 줄(필수 아님)로만 남긴다 - 띄울 때 공급자 문지기 없이 뜰 뿐 막히지는 않는다.
    """
    from fleet_rt import config as rt_config  # noqa: PLC0415
    from fleet_rt import env as rt_env  # noqa: PLC0415
    from fleet_rt import harness as rt_harness  # noqa: PLC0415
    from fleet_rt import manager as rt_manager  # noqa: PLC0415
    from fleet_rt import providers as rt_providers  # noqa: PLC0415
    checks = []
    harn = {rt_manager.MANAGER_HARNESS: ["관리자"]}
    try:
        cfg = rt_config.load(fleet.ROOT)
    except rt_config.ConfigError as e:
        cfg = None
        checks.append(_check("fleet.toml", False, str(e)))
    prov = {}
    if cfg is not None:
        prov[cfg.provider_of(rt_manager.MANAGER_HARNESS, rt_manager.MANAGER_MODEL) or "anthropic"] = ["관리자"]
    try:
        roster = fleet.roster()
    except Exception as e:  # noqa: BLE001
        roster = {}
        checks.append(_check("슬롯 명부", False, f"{type(e).__name__}: {e}"))
    unknown = []
    for slot in sorted(roster):
        h = roster[slot][1]
        harn.setdefault(h, []).append(slot)
        if cfg is None:
            continue
        try:
            model = fleet._slot_model(slot)
        except Exception:  # noqa: BLE001
            model = None
        p = cfg.provider_of(h, model)
        if p:
            prov.setdefault(p, []).append(slot)
        else:
            unknown.append(f"{slot}({h} {model or '기본 모델'})")
    for h, users in sorted(harn.items()):
        try:
            pr = rt_harness.get(h).probe()
            ok, detail = pr.ok, (pr.version or pr.binary or "") if pr.ok else pr.detail
        except (ValueError, ImportError) as e:
            ok, detail = False, str(e)
        checks.append(_check(f"하네스 {h} ({', '.join(users)})", ok, detail))
    problem = rt_env.env_problem(fleet.ROOT)
    checks.append(_check("키 파일 .env", problem is None, problem or "읽힘"))
    if cfg is not None:
        env = rt_env.load_env(fleet.ROOT)
        for p, users in sorted(prov.items()):
            # 응답 점검은 키를 보내지 않는다(`providers.probe`). 키가 있는지는 이름만 따로 본다 - 값은 보이지 않는다.
            try:
                ok, detail = rt_providers.probe(cfg, p)
            except Exception as e:  # noqa: BLE001 - 점검 하나가 터져도 점검표는 나와야 한다
                ok, detail = False, f"{type(e).__name__}"
            checks.append(_check(f"공급자 {p} ({', '.join(users)})", ok, detail))
            if (cfg.provider(p) or {}).get("env_key"):
                kok, kdetail = rt_providers.key_present(cfg, p, env)
                checks.append(_check(f"키 {p} ({', '.join(users)})", kok, kdetail))
    if unknown:
        checks.append(_check("공급자를 모르는 슬롯", False, ", ".join(unknown), required=False))
    return checks


def _rev_lint_checks():
    """REV 일치와 린터 - 운영 DB·AIMEM.md 를 읽는다 (검사는 이 함수를 갈아끼운다)."""
    checks = []
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
    return checks


def prepare(by="사람", extra_checks=()):
    """준비. 관리자·작업자를 띄울 수 있는지 점검하고, 통과하면 `ready`. 아무것도 띄우지도 끊지도 않습니다 -
    남은 세션 프로세스가 있으면 점검이 실패하고 목록을 보입니다(끊는 것은 '완전 중지' 입니다)."""
    checks = _runtime_checks()
    mgr = manager_running()
    checks.append(_check("실행 중인 관리자 없음", not mgr, ", ".join(s["id"] for s in mgr) or "없음"))
    rr = running_runs()
    checks.append(_check("돌고 있는 작업자 없음", not rr, ", ".join(r["id"] for r in rr) or "없음"))
    busy = [g["id"] for g in graphs_overview() if g["runner"]]
    checks.append(_check("돌고 있는 그래프 실행기 없음", not busy, ", ".join(busy) or "없음"))
    try:
        orphans = _rt().find_orphans(_sessions_root())
    except Exception as e:  # noqa: BLE001
        orphans = [{"pid": "?", "session": "?", "why": f"조회 실패 {type(e).__name__}"}]
    checks.append(_check("남은 세션 프로세스 없음", not orphans,
                         "; ".join(f"pid {o['pid']} {o['session']} ({o['why']})" for o in orphans[:8])
                         + (f" 외 {len(orphans) - 8}" if len(orphans) > 8 else "") or "없음"))
    checks.extend(_rev_lint_checks())
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


# ----------------------------------------------------------------- 라운드 실행 (관리자 세션)
def _new_manager_id(n, at):
    from fleet_rt import manager as rt_manager  # noqa: PLC0415
    base = rt_manager.manager_id(n, at)
    sid, k = base, 1
    while (_sessions_root() / sid).exists():
        k += 1
        sid = f"{base}-{k}"
    return sid


def _start_watcher(n, close_only=False):
    """라운드 R<n> 의 감시자(`_chainwatch`)를 배경으로 띄운다. 세션 표식 없이 - 관리자 세션을 끊어도 살아 남아 마감을 쓴다.

    `close_only` 면 마감만 지켜보는 감시자다 - 이어 달리기 파일이 나중에 켜져도 다음 라운드를 띄우지 않는다.
    그 파일은 작업자도 쓸 수 있으므로, 사람이 켜지 않은 라운드에서 유료 관리자가 저절로 뜨면 안 된다 (2026-11-12 검수).
    방식은 파일이 아니라 명령줄로 넘긴다 - 뜬 뒤에는 바꿀 수 없게.
    """
    argv = [sys.executable, str(HERE / "fleet_ctl.py"), "_chainwatch", "--round", str(int(n))]
    if close_only:
        argv.append("--close-only")
    try:
        log = open(_aimem_dir() / "fleet-chain.log", "a", encoding="utf-8")
        with log:
            log.write(f"\n# {_now()} R{int(n)} 감시 시작" + (" (마감만)" if close_only else "") + "\n")
            log.flush()
            subprocess.Popen(argv,
                             cwd=str(fleet.ROOT), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True, env=_service_env())
        return True
    except (OSError, ValueError):
        return False


def launch_round(by="사람"):
    """새 라운드. 확정 브리프가 있고 관리자가 없을 때만. **준비(ready)** 에서, 또는 앞 라운드가 끝난 채
    '실행' 으로 남아 있을 때(`round_over`) - 그때는 준비 점검을 여기서 먼저 돌립니다 (REV 153).

    관리자는 `sessions.spawn(role="manager")` 로 바로 뜹니다(설계 3.3). 띄운 뒤에는 감시자를 하나 띄웁니다 -
    관리자가 보고 없이 끝나면 최소 마감을 쓰고(5.10), 이어 달리기가 켜져 있으면 다음 라운드를 판단합니다.

    처음부터 끝까지 `fleet-launch.lock` 을 잡는다 - 단추 두 번·감시자와 겹친 누름이 둘 다 '관리자 없음' 을 보고
    지나가면, 진 쪽이 이긴 쪽의 라운드를 실패로 적고 모드를 '준비' 로 돌려 도는 관리자가 작업자를 못 띄웠다 (2026-11-12 검수).
    """
    try:
        _aimem_dir().mkdir(parents=True, exist_ok=True)
        lock = open(_aimem_dir() / "fleet-launch.lock", "a")
    except OSError as e:
        return {"ok": False, "error": f"라운드 띄우기 잠금 파일을 열지 못했습니다: {type(e).__name__}"}
    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"ok": False, "error": "이미 라운드를 띄우는 중입니다"}
        return _launch_round_locked(by)


def _launch_round_locked(by):
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
    running = manager_running()
    if running:
        return {"ok": False, "error": "이미 실행 중인 관리자가 있습니다: " + ", ".join(s["id"] for s in running)}
    from fleet_rt import config as rt_config  # noqa: PLC0415
    from fleet_rt import manager as rt_manager  # noqa: PLC0415
    n = b["round"]
    at = dt.datetime.now()
    sid = _new_manager_id(n, at)
    try:
        brief = _round_brief_path(b, at)
        _write_round_record(n, at, b["file"], session=sid)
    except (OSError, ValueError) as e:
        # 라운드 폴더가 저장소 밖을 가리키는 등 - 아무것도 띄우지 않고 모드도 그대로 둔다
        return {"ok": False, "round": n, "error": f"R{n} 라운드 폴더를 준비하지 못했습니다: {str(e)[:200]}"}
    ws = round_workspace(n)
    try:
        provider = rt_config.load(fleet.ROOT).provider_of(rt_manager.MANAGER_HARNESS, rt_manager.MANAGER_MODEL)
    except Exception:  # noqa: BLE001 - 설정이 깨져도 관리자는 뜬다 (공급자 칸만 빈다)
        provider = None
    spec = rt_manager.spec(sid, n, fleet.ROOT, at=at, by=by, brief=b["file"], workspace=ws, provider=provider)
    # 관리자가 곧바로 `fleet_graph.py run` 으로 작업자를 띄우므로 모드를 먼저 '실행' 으로 둔다.
    set_mode("running", by, f"라운드 R{n} 실행 ({b['file']}, 관리자 {sid})")
    db = _aimem_dir() / "aimem.db"
    try:
        _rt().spawn(spec, brief.read_text(encoding="utf-8"), _sessions_root(),
                    db_path=str(db) if db.exists() else None, env_root=str(fleet.ROOT))
    except (ValueError, OSError, RuntimeError) as e:
        if isinstance(e, FileExistsError) and manager_running():
            # 같은 id 의 관리자가 이미 떠 있다 - 그 라운드를 실패로 적거나 모드를 돌리면 도는 관리자를 해친다
            return {"ok": False, "round": n, "session": sid, "mode": mode(),
                    "error": "이미 실행 중인 관리자가 있습니다: " + ", ".join(s["id"] for s in manager_running())}
        _mark_round_record_failed(n)
        set_mode("ready", by, f"R{n} 관리자를 띄우지 못함")
        err = f"R{n} 관리자를 띄우지 못했습니다 ({sid}): {type(e).__name__}: {str(e)[:200]}"
        if chain_state().get("on"):
            _chain_stop(chain_state(), "error", err, n)
        return {"ok": False, "round": n, "session": sid, "mode": mode(), "error": err}
    # 이어 달리기가 꺼진 채 띄운 라운드의 감시자는 마감만 본다 - 켜는 것은 사람의 `chain_set` 이 감시자를 갈아 끼운다
    watcher = _start_watcher(n, close_only=not chain_state().get("on"))
    return {"ok": True, "round": n, "label": spec.label, "session": sid, "brief": b["file"], "workspace": ws,
            "mode": "running", "watcher": watcher}


# ----------------------------------------------------------------- 최소 마감 (설계 5.10)
GIT_STATUS_MAX_LINES = 80


def _round_graphs(n):
    """그 라운드의 그래프(`round` 칸)와 라운드 표시가 없는 미완 그래프."""
    out = []
    d = _graphs_dir()
    try:
        files = sorted(d.glob("*.json"))
    except OSError:
        return out
    for f in files:
        try:
            g = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(g, dict) or not isinstance(g.get("nodes"), list):
            continue
        if str(g.get("round")) == str(n) or _graph_unfinished(g):
            out.append(g)
    return out


def _git_status_lines():
    try:
        r = subprocess.run(["git", "status", "--short"], cwd=str(fleet.ROOT), capture_output=True, text=True, timeout=20)
        lines = (r.stdout if r.returncode == 0 else f"(git status rc={r.returncode}) {(r.stderr or '').strip()}").splitlines()
    except (OSError, subprocess.SubprocessError) as e:
        lines = [f"(git status 실패: {type(e).__name__})"]
    if len(lines) > GIT_STATUS_MAX_LINES:
        lines = lines[:GIT_STATUS_MAX_LINES] + [f"… 외 {len(lines) - GIT_STATUS_MAX_LINES}줄"]
    return [ln[:300] for ln in lines] or ["(바뀐 파일 없음)"]


def write_minimal_close(n, why, session=None):
    """관리자가 보고(`rounds/R<N>/REPORT.md`) 없이 끝난 라운드에 **엔진이** 최소 마감을 쓴다. 썼으면 True.

    `상태: PARTIAL` 로 쓴다 - 이어 달리기(`round_report_status`)가 '사람이 봐야 함' 으로 읽고 멈춘다.
    이미 보고가 있으면 건드리지 않는다(없을 때만 만든다 - 관리자가 같은 순간에 쓴 보고를 덮지 않게).

    **REV 를 올리거나 핸드오프·보드를 DB 에 쓰지 않는다.** DB 에 쓰면 `AIMEM-state.md` 스냅샷이 어긋나 린터
    (STATE_SNAPSHOT_STALE)와 커밋 훅이 막힌다. 핸드오프는 다음 관리자가 이 파일을 읽고 남긴다.
    """
    try:
        d = _round_dir(n, create=False)
    except ValueError as e:
        print(f"{_now()} R{n}: 최소 마감을 쓰지 않았습니다 - {e}", file=sys.stderr, flush=True)
        return False
    rep = d / "REPORT.md"
    if rep.exists() or rep.is_symlink():
        return False
    mine = [s for s in manager_sessions() if s.get("round") == int(n)]
    s = next((x for x in mine if x["id"] == session), None) or (mine[-1] if mine else None)
    state = s["status"] if s else "세션 없음"
    lines = [f"# R{n} 종료 보고 (엔진이 쓴 최소 마감)", "", "상태: PARTIAL", "",
             f"관리자 없이 끝남 ({state}) - {why}", ""]
    if s:
        lines.append(f"- 관리자 세션: `{s['id']}` ({s.get('started') or '?'} ~ {s.get('ended') or '?'})"
                     + (f" - {s['why']}" if s.get("why") else ""))
    lines += [f"- 쓴 때: {_now()} · 쓴 것: 엔진(`fleet_ctl.write_minimal_close`). 관리자의 판정·핸드오프·REV 올림은 없습니다 -",
              "  다음 관리자가 이 파일과 그래프 상태를 보고 이어받아 정리합니다.", "", "## 그래프 상태", ""]
    graphs = _round_graphs(n)
    if not graphs:
        lines.append("- (이 라운드의 그래프 없음)")
    unfinished = []
    for g in graphs:
        gid = g.get("id", "?")
        counts = {}
        for node in g["nodes"]:
            st = node.get("status", "todo")
            counts[st] = counts.get(st, 0) + 1
            if st != "done":
                unfinished.append(f"- {gid} / {node.get('id', '?')} ({st}) {str(node.get('title') or '')[:120]}".rstrip())
        runner = " · 실행기 잡고 있음" if _lock_holder(gid) else ""
        lines.append(f"- {gid}: " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "노드 없음") + runner)
    lines += ["", "## 끝나지 않은 노드", ""] + (unfinished[:100] or ["- 없음"])
    if len(unfinished) > 100:
        lines.append(f"- … 외 {len(unfinished) - 100}개")
    lines += ["", "## 손댄 파일 (`git status --short`)", "", "```", *_git_status_lines(), "```", ""]
    try:
        d = _round_dir(n)               # 만들기 전에 다시 본다 - 위에서 오래 걸린 사이 링크가 심겼을 수 있다
    except (OSError, ValueError):
        return False
    tmp = d / f".REPORT.md.tmp.{os.getpid()}"
    try:
        tmp.write_text("\n".join(lines), encoding="utf-8")
        try:
            os.link(tmp, rep)       # 없을 때만 - 관리자가 그 사이 쓴 보고가 있으면 그것을 살린다
        except FileExistsError:
            return False
        return True
    except OSError:
        return False
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def close_if_unreported(n):
    """라운드 R<n> 의 관리자가 끝났는데(done 이 아닌 상태로) 보고가 없으면 최소 마감을 쓴다. 쓴 상태 이름 또는 None.

    done 으로 끝났는데 보고 파일이 없는 경우는 쓰지 않는다 - 관리자가 응답 본문에만 보고했을 수 있고
    (세션 `report.md` 에 남는다), 그 판정을 엔진이 PARTIAL 로 덮으면 안 된다. 이어 달리기는 '보고 없음' 으로 멈춘다.
    """
    if round_report_status(n) is not None or (fleet.ROOT / round_workspace(n) / "REPORT.md").exists():
        return None
    mine = [s for s in manager_sessions() if s.get("round") == int(n)]
    if not mine or mine[-1]["status"] in ("running", "done"):
        return None
    s = mine[-1]
    return s["status"] if write_minimal_close(n, f"관리자 세션이 {s['status']} 로 끝남", session=s["id"]) else None


# ----------------------------------------------------------------- 이어 달리기 (REV 155)
# 프로젝트 목표가 남아 있으면 라운드가 끝난 뒤 다음 라운드를 **함대가 스스로** 띄웁니다. 2026-11-10 밤에는 사람이
# (Claude Code 가) 손으로 이었습니다: 보고와 `PROGRESS.md` 의 `## 목표` 를 읽고 → 남은 목표를 요청으로 넣고 → 준비 → 라운드.
# 켜는 것은 사람입니다(엔진은 태석님). 유료 관리자가 라운드마다 뜨므로 **연속 상한**과 **멈춤 조건**이 꼭 있습니다.
CHAIN_MAX_ROUNDS = 10            # 사람이 고를 수 있는 연속 상한의 최대
CHAIN_HARD_ROUNDS = 30           # 상한을 새로 이어 가며(`renew`) 돌 때의 안전 상한(모두 합친 라운드 수) - 여기 닿으면 사람이 다시 켠다
CHAIN_DEFAULT_ROUNDS = 3
CHAIN_WAIT_SEC = 6 * 3600 + 600  # 한 라운드를 기다리는 최대 시간 - 관리자 벽시계 제한(6시간)보다 조금 길게 (넘으면 이어 달리기를 끈다)
CHAIN_POLL_SEC = 5               # 관리자 세션이 끝났는지는 세션 폴더 읽기라 싸다
WATCH_LOCK_WAIT_SEC = 10         # 갈아 끼울 때 앞 감시자가 잠금을 놓기를 기다리는 시간
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


def _queue_items():
    """대기 큐의 (순번, 글). 큐는 라운드가 '다음에 할 일' 로 넘긴 함대의 일이다 - 요청이 아니어도 남은 일로 센다."""
    import sqlite3  # noqa: PLC0415
    db = fleet.ROOT / ".aimem" / "aimem.db"
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            return [(int(r[0]), str(r[1] or "")) for r in con.execute("SELECT pos, task FROM queue ORDER BY pos")]
        finally:
            con.close()
    except (sqlite3.Error, ValueError, TypeError):
        return []


def chain_work(fleet_on=False, projects=(), all_=False):
    """고른 대상의 남은 일. `{requests: [열린 요청 id], goals: {프로젝트: {done, total, open}}}`.

    - 함대      : 프로젝트가 없는 열린 요청 (함대 자체의 일) + **대기 큐** (`queue`: 남은 항목 수 - 함대·전체일 때만)
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
    return {"requests": ids, "goals": goals, "queue": len(_queue_items()) if (all_ or fleet_on) else 0}


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
          "queue_left": work["queue"],                                       #        큐가 줄었는가
          "by": by, "at": _now(),
          "log": [f"{_now()} 켬 ({by}) - {chain_label(is_fleet, names, is_all)}, "
                  + f"상한 {mx} 라운드, " + ("완전 자율 종주" if autonomous else "닿으면 새 묶음으로 이어 감(끝날 때까지)" if renew else "닿으면 멈춤")]}
    _chain_write(st)
    # 라운드가 도는 중에 켰으면 그 라운드의 감시자를 이어 달리기 감시자로 갈아 끼운다 - `launch_round` 가 띄운
    # 감시자는 (꺼진 채 띄웠으면) 마감만 보는 감시자라 켜진 것을 보지 않는다. 있던 것을 끝내고(잠금이 풀린다) 새로 띄운다.
    mgr = manager_status()
    if mode() == "running" and isinstance(mgr, dict) and isinstance(mgr.get("round"), int) \
            and (_manager_busy(mgr) or not round_over()):          # 끝난 라운드에는 감시자를 붙이지 않는다
        _end_chain_watcher()
        _start_watcher(mgr["round"])
    return {"ok": True, "chain": st}


_LIMIT_LOG_LINE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}T\S+\s+)?limit ")


def _round_hit_limit(round_n):
    """그 라운드의 그래프 로그에 사용 한도로 끊긴 줄(`limit ...`)이 있으면 True.

    읽기 실패는 밖으로 내보내지 않습니다 - 까닭 문자열에 덧붙이지 않는 쪽이 낫습니다.
    """
    if round_n is None:
        return False
    try:
        graphs = _graphs_dir()
        for path in sorted(graphs.glob("G-*.json")):
            try:
                g = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if str(g.get("round")) != str(round_n):
                continue
            try:
                text = path.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(_LIMIT_LOG_LINE.match(line.strip()) for line in text.splitlines()):
                return True
        return False
    except Exception:  # noqa: BLE001 - 판정 실패는 덧붙이지 않는 것으로 끝낸다
        return False


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
    queue_left = int(work.get("queue") or 0)
    base = {"requests": open_ids, "goals": goals, "done": done, "total": total, "queue": queue_left}
    left = f"열린 요청 {len(open_ids)}건" + (f" · 목표 {done}/{total}" if goals else "") + (f" · 큐 {queue_left}건" if queue_left else "")
    status = round_report_status(round_n)
    auto = bool(st.get("autonomous"))
    second_chance = auto and int(st.get("strikes", 0)) < 1          # 완전 자율 종주: 막혀도 한 번은 더 간다
    if not open_ids and not goals_left and not queue_left and status == "DONE":
        return {**base, "action": "stop", "kind": "done", "why": f"남은 일이 없습니다 ({left}) - 끝났습니다"}
    cap = int(st.get("max_rounds") or CHAIN_DEFAULT_ROUNDS)
    renew = bool(st.get("renew")) or auto or not st.get("max_rounds")     # 옛 상태의 max_rounds 0 = 이어 감
    ran = int(st.get("rounds_done", 0)) + 1
    total = int(st.get("total_rounds", st.get("rounds_done", 0))) + 1
    if renew and total >= CHAIN_HARD_ROUNDS:
        return {**base, "action": "stop", "kind": "safety", "why": f"모두 {total} 라운드를 이어 왔습니다 - 안전 상한({CHAIN_HARD_ROUNDS})이라 멈춥니다. 계속하려면 다시 켜십시오 ({left})"}
    if status != "DONE":
        if second_chance and (open_ids or goals_left or queue_left):
            return {**base, "action": "launch", "strike": True, "why": f"R{round_n} 보고가 {status or '없음'} 입니다 - 완전 자율 종주라 한 번 더 갑니다 ({left})"}
        why = f"R{round_n} 보고가 {status or '없음'} 입니다 - 사람이 봐야 합니다"
        if auto:
            why += " (완전 자율 종주에서도 연달아 두 번째라 멈춥니다)"
        if _round_hit_limit(round_n):
            why += " - 사용 한도로 끊긴 시도가 있습니다"
        return {**base, "action": "stop", "kind": "report", "why": why}
    closed = [i for i in (st.get("open_requests") or []) if i not in open_ids]
    queue_shrank = "queue_left" in st and queue_left < int(st.get("queue_left") or 0)
    queue_new = "queue_left" not in st and queue_left > 0       # 큐를 세기 전에 켠 상태 - 처음 본 큐는 새 일이다
    if not closed and done <= int(st.get("goals_done", 0)) and not queue_shrank and not queue_new:
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


def _chain_queue_request(round_n):
    """대기 큐에 남은 일을 다음 라운드의 요청으로 넣습니다 (웹 요청 폼과 같은 길, 프로젝트 없음 = 함대의 일)."""
    here = str(HERE)
    if here not in sys.path:
        sys.path.insert(0, here)
    from aimem_monitor import server  # noqa: PLC0415
    items = _queue_items()
    lines = "\n".join(f"- 큐 {pos}번: {task[:300]}" for pos, task in items[:40])
    detail = (f"R{round_n} 이 끝났고 열린 요청은 없지만 대기 큐에 {len(items)}건이 남아 있습니다. 큐가 이번 라운드의 할 일입니다:\n\n"
              f"{lines}\n\n"
              "전문은 `python3 tools/aimem_db.py queue list` 로 읽으십시오. 끝낸 항목은 검증 뒤 큐에서 내리고, "
              "이번 라운드에 못 끝내는 항목은 **무엇이 막는지**(사람의 승인이 필요한지 포함)를 보고에 항목별로 적으십시오. "
              "큐에 새 항목을 더하는 것은 이 일들을 하다 찾은 것만입니다.\n\n"
              "(함대의 '이어 달리기' 가 자동으로 넣은 요청입니다 - 큐가 비거나 줄지 않으면 스스로 멈춥니다.)")
    return server.create_request({"title": f"대기 큐 {len(items)}건 처리 (R{round_n} 뒤 자동)",
                                  "detail": detail, "requester": "함대 이어 달리기"}, fleet.ROOT)


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
    # 큐만 남았고 함대의 열린 요청이 없으면, 큐를 비우는 요청을 넣는다
    if d.get("queue") and "" not in open_projects and not d.get("requests"):
        ok, res = _chain_queue_request(round_n)
        if not ok:
            _chain_stop(st, "error", f"요청을 못 넣었습니다(큐): {res.get('error')}", round_n)
            return {"ok": False, "launched": False, "why": st["stopped_why"]}
        filed.append(res.get("id"))
    st.update({"rounds_done": 0 if d.get("new_cycle") else int(st.get("rounds_done", 0)) + 1,      # 새 묶음은 0 부터 다시 센다
               "cycles": int(st.get("cycles", 0)) + (1 if d.get("new_cycle") else 0),
               "total_rounds": int(st.get("total_rounds", st.get("rounds_done", 0))) + 1,
               "goals_done": d["done"], "queue_left": int(d.get("queue") or 0), "at": _now(),
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


def _watch_path():
    return _aimem_dir() / "fleet-chain.watch.json"


def _end_chain_watcher():
    """감시자 프로세스를 끝낸다(완전 중지). 끝낸 pid 또는 None.

    감시자는 세션 표식 없이 뜨므로 고아 청소가 못 본다. 그래서 감시자가 뜰 때 적어 둔 pid·시작 시각을
    대조하고, 명령줄이 감시자인 것만 끊는다(pid 재사용 방지). 나와 내 조상은 끊지 않는다.
    """
    try:
        rec = json.loads(_watch_path().read_text(encoding="utf-8"))
        pid, start = int(rec["pid"]), int(rec["start"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    rt = _rt()
    if pid <= 1 or pid in rt._ancestors() or rt.proc_start(pid) != start or "_chainwatch" not in rt._proc_cmdline(pid):
        return None
    return pid if rt._signal_pids([pid], {pid: start}) else None


def _round_manager_running(n):
    return any(s["round"] == int(n) for s in manager_running())


def _chain_wait_and_step(n, poll=None, wait=None, close_only=False):
    """감시자(라운드마다 하나, `launch_round` 가 띄운다): 관리자 세션이 끝나기를 기다린다.

    - 관리자가 보고 없이(done 이 아닌 상태로) 끝났으면 최소 마감을 쓴다(`close_if_unreported`, 설계 5.10)
    - 이어 달리기가 켜져 있고 라운드가 끝났으면(작업자·실행기도 없음) `chain_step` 으로 다음 라운드를 판단한다
    - 사람이 함대를 멈추면 이어 달리기를 내려놓는다 (마감은 계속 지켜본다)
    - `close_only` (이어 달리기가 꺼진 채 띄운 라운드): 마감만 보고, 이어 달리기 파일은 읽지 않는다
    관리자 세션이 끝났는지는 세션 폴더 읽기라 몇 초마다 봐도 싸다.
    """
    with open(_aimem_dir() / "fleet-chain.lock", "w") as lock:
        # 감시자는 하나만 - 둘이면 다음 라운드를 두 번 띄운다. `chain_set` 이 앞 감시자를 끝내고 곧바로 띄우므로
        # 앞 감시자가 다 죽어 잠금이 풀리기까지 잠깐 기다린다.
        deadline = time.time() + WATCH_LOCK_WAIT_SEC
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    return 0
                time.sleep(0.2)
        return _watch(n, CHAIN_POLL_SEC if poll is None else poll, CHAIN_WAIT_SEC if wait is None else wait,
                      close_only=close_only)


def _watch(n, poll, wait, close_only=False):
    try:
        rt = _rt()
        tmp = _watch_path().with_name(_watch_path().name + ".tmp")
        tmp.write_text(json.dumps({"pid": os.getpid(), "start": rt.proc_start(os.getpid()), "round": int(n), "at": _now(),
                                   "close_only": bool(close_only)}),
                       encoding="utf-8")
        os.replace(tmp, _watch_path())
    except (OSError, ValueError):
        pass
    deadline = time.time() + wait
    closed = None
    while time.time() < deadline:
        time.sleep(poll)
        on = False if close_only else chain_state().get("on")
        if on and mode() != "running":    # 사람이 멈췄다 - 이어 달리기도 내려놓는다
            _chain_stop(chain_state(), "off", f"함대가 '{MODE_LABEL.get(mode(), mode())}' 로 바뀌어 이어 달리기도 내려놓았습니다 (사람이 멈춤)", n)
            on = False
        if _round_manager_running(n):
            continue
        if closed is None:
            closed = close_if_unreported(n) or ""
            if closed:
                print(f"{_now()} R{n}: 관리자가 {closed} 로 끝나 최소 마감을 썼습니다", flush=True)
        if not on:
            return 0                      # 꺼져 있거나 사람이 껐다 - 마감만 보고 끝
        if not round_over():
            continue                      # 관리자는 갔는데 작업자·실행기가 아직 돈다
        res = chain_step(n)
        print(f"{_now()} chain R{n}: {json.dumps({k: v for k, v in res.items() if k != 'open'}, ensure_ascii=False)}", flush=True)
        return 0
    if not close_only and chain_state().get("on"):
        _chain_stop(chain_state(), "wait", f"R{n} 이 {CHAIN_WAIT_SEC // 3600}시간이 지나도 끝나지 않아 기다리기를 그만두었습니다 - 관리자를 확인하십시오", n)
    return 1

# ----------------------------------------------------------------- CLI
def main(argv=None):
    p = argparse.ArgumentParser(description="함대 제어 (준비/실행/일시 중지/완전 중지/라운드 실행)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("status", "prepare", "run", "pause", "stop", "round"):
        s = sub.add_parser(c)
        s.add_argument("--by", default="CLI")
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
    w.add_argument("--close-only", action="store_true", help="마감만 지켜본다 - 이어 달리기는 하지 않는다")
    a = p.parse_args(argv)
    if a.cmd == "_chainwatch":
        return _chain_wait_and_step(a.round, close_only=a.close_only)
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
