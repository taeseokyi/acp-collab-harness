#!/usr/bin/env python3
"""태스크 그래프 실행기 (관리자 전용) - 루프 엔지니어링 + 그래프 엔지니어링.

요청 하나를 **의존 관계가 있는 태스크 DAG** 로 적고(`.aimem/graph/<id>.json`),
준비된 노드를 한꺼번에 띄우고(fan-out), 의존이 풀리면 다음을 열며(fan-in),
노드마다 **스폰 -> 대기 -> 검증 -> 한정 재시도** 루프를 돕니다. 진행율과 완료 예정 시간은
그래프와 `.aimem/runs` 의 과거 실행 시간(하네스별 중앙값)에서 계산합니다.

  python3 tools/fleet_graph.py new  --id R-001 --request "웹 UI" --nodes nodes.json   # 그래프 파일 생성
  python3 tools/fleet_graph.py validate R-001      # DAG·6절 소유권·슬롯 검사 (실행 없음)
  python3 tools/fleet_graph.py step R-001          # 스케줄러 한 틱: 끝난 것 거두고 검증, 준비된 것 띄움
  python3 tools/fleet_graph.py run R-001 [--timeout 3600] [--concurrency 3]   # 끝날 때까지 틱 반복
  python3 tools/fleet_graph.py status R-001        # 노드별 상태·진행율·ETA (웹 UI 가 읽는 것과 같은 JSON)
  python3 tools/fleet_graph.py unblock R-001 T1    # 사람이 확인한 blocked/failed 노드를 다시 굴림 (그 뒤 run/step)
  python3 tools/fleet_graph.py move R-001 T1 --slot S5   # 막힌 노드를 다른 슬롯으로 (소유도 함께, 운영 방식의 등급 안에서)

노드 형식 (nodes.json 배열):
  {"id":"T1","title":"서버 골격","slot":"S1","project":"<프로젝트 이름, 함대 자체 일이면 생략>","write":["tools/aimem_monitor/server.py"],
   "task":"...지시 본문...","deps":[],"verify":"python3 -m py_compile tools/aimem_monitor/server.py",
   "max_attempts":2,"harness":null,"model":null}

실행은 전부 `tools/fleet.py spawn` 을 거치므로 머리말·토큰·REV·소유권 대조는 거기서 한 번 더 걸립니다.

S4 적대적 검수 두 라운드째 지적(AIMEM 4.5 대기 큐 7·8·9, T-081)으로 더한 것:
  - **단일 실행자 잠금** `graph_lock(gid)`: `run` 도중 다른 터미널의 `step`/`run` 이 같은 노드를
    또 띄웠습니다(실측: 노드 A 에 run 3개). `run`/`step` 전체를 `.aimem/graph/<gid>.lock` 의
    `flock` 으로 감싸고, 못 잡으면 rc 2 로 끝냅니다.
  - `run`/`step` 시작 전 **`validate_graph` 한 번**(손으로 고친 그래프의 오타를 스폰 전에 잡음),
    **노드별 타임아웃**(`timeout_sec` -> `node_timeout_sec` -> 1800초; pid 로만 죽임, `pkill -f` 금지).
  - **보고 첫 줄이 BLOCKED/NEEDS-*/REJECT 면 rc 0 이어도 `done` 이 아니라 `blocked`**
    (`report_block_reason`) - 사람이 풀 일이므로 재시도하지 않습니다.

엔진 v2 3단계(2026-11-13)에서 더한 것 (설계 5.3·5.4·5.7·5.8):
  - **실패의 종류** `attempt.fail_kind` ∈ None(성공)/work/infra/limit/timeout. infra(침묵·감독 소멸·재접속 오류)는
    시도로 세지 않고 `infra_attempts` 로 옮겨 다시 넣으며, `INFRA_RETRY_MAX` 번 겹치면 `blocked` + `infra`.
  - **공급자 문지기**: 공급자 자리(`fleet.toml` 의 `max_concurrent`)가 없으면 띄우지 않고 `waiting` 에 까닭을 적는다.
    같은 자리를 다투면 뒤에 걸린 노드가 많은 것부터.
  - **틱 2초**, 한 틱에 /proc 훑기 한 번, 끝난 기록은 다시 보지 않는다.
  - **보드 동기화**: 태스크 id 인 노드의 상태가 바뀌면 DB `tasks.status` 를 같이 고친다(`_board_sync`).
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
import pathlib
import re
import signal
import sqlite3
import statistics
import subprocess
import threading
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fleet  # noqa: E402
from fleet_rt.harness.claude import (  # noqa: E402
    LIMIT_PATTERNS as _LIMIT_PATTERNS, limit_text_hit as _limit_text_hit, result_limit_signal as _result_limit_signal)

ROOT = fleet.ROOT
GRAPHS = ROOT / ".aimem" / "graph"
TERMINAL = ("done", "failed", "blocked")
DEFAULT_NODE_TIMEOUT_SEC = 1800
KILL_GRACE_SEC = 5
#: 기반 장애(공급자·전송이 죽음)는 시도로 세지 않고 다시 넣는다. 이만큼 겹치면 노드를 막고 사람에게 넘긴다 (설계 5.3).
INFRA_RETRY_MAX = 3
#: 공급자 준비 점검 결과를 이만큼 재사용한다 - 죽은 공급자를 틱마다(2초) 두드리지 않게.
PROBE_TTL_SEC = 30.0
#: 공급자가 응답하지 않아(`probe:<p>`) 이만큼 넘게 기다린 노드는 `blocked`+`infra` 로 넘긴다 - 그래프가 제 시간 한도까지
#: 말없이 놀지 않고 관리자·사람이 `move`/`unblock` 으로 판단하게.
PROBE_WAIT_MAX_SEC = 600
#: `run` 의 틱 간격(초). 노드 하나가 끝난 뒤 다음이 뜨기까지 평균 절반을 기다린다 (설계 5.7: 예전 15초).
DEFAULT_POLL_SEC = 2.0


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _check_gid(gid):
    gid = str(gid)
    if "/" in gid or "\\" in gid or gid in ("", ".", ".."):
        raise ValueError(f"그래프 id 에 경로 구분자를 쓸 수 없습니다: {gid!r}")
    return gid


# ---------------------------------------------------------------- 단일 실행자 잠금 (큐 7번)
@contextlib.contextmanager
def graph_lock(gid, cmd="run"):
    """그래프 하나에 실행자(`run`/`step`)를 **한 명만** 둡니다.

    결함: `run` 이 도는 중에 다른 터미널에서 `step`/`run` 을 치면 둘 다 같은 `todo` 노드를
    보고 띄워, 실측에서 노드 A 하나에 run 3개가 붙었습니다 (S4 적대적 검수 큐 7번).
    `flock(LOCK_EX | LOCK_NB)` 를 쓰는 이유: 프로세스가 죽으면 커널이 풀어 주므로 죽은 pid
    회수 로직이 따로 필요 없습니다. **잠금 파일은 절대 unlink 하지 않습니다** - 지우면 다음
    실행자가 다른 inode 를 잡아 두 실행자가 동시에 "잡았다" 고 믿게 됩니다.
    못 잡으면 스폰 없이 stderr 에 누가 잡았는지 찍고 `SystemExit(2)` 로 끝냅니다.
    """
    gid = _check_gid(gid)
    GRAPHS.mkdir(parents=True, exist_ok=True)
    path = GRAPHS / f"{gid}.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    f = os.fdopen(fd, "r+", encoding="utf-8")
    try:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError):
            holder = {}
            try:
                f.seek(0)
                holder = json.loads(f.read() or "{}")
                if not isinstance(holder, dict):
                    holder = {}
            except (ValueError, OSError):
                holder = {}
            print(f"그래프 {gid} 를 다른 실행자가 잡고 있습니다 "
                  f"(pid {holder.get('pid', '?')}, 시작 {holder.get('started', '?')}, "
                  f"cmd {holder.get('cmd', '?')})", file=sys.stderr)
            raise SystemExit(2)
        try:
            # 잡은 **뒤에** 내용을 씁니다 - 잡기 전에 쓰면 남의 기록을 덮습니다.
            os.ftruncate(f.fileno(), 0)
            f.seek(0)
            f.write(json.dumps({"pid": os.getpid(), "started": _now(), "cmd": cmd}, ensure_ascii=False))
            f.flush()
            yield path
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()


def _load(gid):
    f = GRAPHS / f"{gid}.json"
    if not f.exists():
        sys.exit(f"그래프 파일이 없습니다: {f}")
    return json.loads(f.read_text(encoding="utf-8"))


def _save(g):
    """**원자적으로** 씁니다 - tmp 에 쓰고 `os.replace`.

    예전에는 `write_text` 직접 쓰기라 쓰다 죽으면 파일이 잘렸고(S4 실측: 215B -> 107B),
    그 뒤 `status`/`step`/`run`/`validate`/`list` 가 전부 `JSONDecodeError` 로 죽었습니다.
    스폰된 run id 목록이 같이 사라지므로 복구 수단이 없었습니다 (적대적 검수 3번, REV 111).
    """
    GRAPHS.mkdir(parents=True, exist_ok=True)
    g["updated"] = _now()
    gid = str(g["id"])
    if "/" in gid or "\\" in gid or gid in ("", ".", ".."):
        raise ValueError(f"그래프 id 에 경로 구분자를 쓸 수 없습니다: {gid!r}")
    target = GRAPHS / f"{gid}.json"
    # tmp 이름에 **pid 와 스레드 id** 를 넣습니다. 고정 이름이면 동시 저장자끼리
    # 서로의 tmp 를 `os.replace` 해 `FileNotFoundError` 가 났습니다
    # (S4 재검수 5번: 4스레드 x 300회에 571건). 반쯤 쓴 파일이 게시될 수도 있습니다.
    tmp = GRAPHS / f"{gid}.json.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        tmp.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)   # 실패하면 내 tmp 만 치운다 (원본은 그대로)
        raise


def _log(g, msg):
    GRAPHS.mkdir(parents=True, exist_ok=True)
    with (GRAPHS / f"{g['id']}.log").open("a", encoding="utf-8") as f:
        f.write(f"{_now()} {msg}\n")


# ---------------------------------------------------------------- 그래프 검사
def validate_graph(g, spawnable_only=False):
    """DAG 인지, 슬롯·소유권이 맞는지. 문제 목록을 돌려줍니다(비어 있으면 통과).

    `spawnable_only=True` (cmd_step/cmd_run 의 시작 전 검사)면 슬롯·소유권은 **`todo` 노드에만**
    봅니다. 이미 done/running 인 노드의 슬롯이 명부에서 빠졌다고 rc 2 로 끝나면 돌고 있는
    작업자를 거두지도 타임아웃으로 죽이지도 못합니다 (S4 재검수 결함 6). DAG 모양과 빈 task 는
    늘 전체를 봅니다. 기본값(False)은 예전 동작 그대로입니다 (cmd_validate·cmd_new).
    """
    problems = []
    nodes = {n["id"]: n for n in g["nodes"]}
    roster = fleet.roster()
    for n in g["nodes"]:
        for d in n.get("deps", []):
            if d not in nodes:
                problems.append(f"{n['id']}: 의존 {d} 가 그래프에 없음")
        if spawnable_only and n.get("status", "todo") != "todo":
            pass
        elif n.get("slot") not in roster:
            problems.append(f"{n['id']}: 슬롯 {n.get('slot')} 이 2절 명부에 없음")
        else:
            pats = fleet.owned_paths(n["slot"])
            for w in n.get("write", []):
                if not fleet.path_allowed(w, pats):
                    problems.append(f"{n['id']}: {w} 는 {n['slot']} 소유가 아님 (6절)")
        if not (n.get("task") or "").strip():
            problems.append(f"{n['id']}: task 본문이 비어 있음")
        pr = n.get("project")
        if pr not in (None, "") and not (isinstance(pr, str) and re.match(fleet.PROJECT_NAME_RE, pr)):
            problems.append(f"{n['id']}: project {pr!r} 는 프로젝트 이름이 아님 (`projects/` 아래 폴더 이름 하나 - 한글·영문·숫자·`-`·`_`, 40자 이하)")
    # 사이클 검사 (Kahn)
    indeg = {k: 0 for k in nodes}
    for n in g["nodes"]:
        for d in n.get("deps", []):
            if d in indeg:
                indeg[n["id"]] += 1
    ready = [k for k, v in indeg.items() if v == 0]
    seen = 0
    while ready:
        k = ready.pop()
        seen += 1
        for n in g["nodes"]:
            if k in n.get("deps", []):
                indeg[n["id"]] -= 1
                if indeg[n["id"]] == 0:
                    ready.append(n["id"])
    if seen != len(nodes):
        problems.append("의존 관계에 사이클이 있음 (DAG 아님)")
    return problems


# ---------------------------------------------------------------- 추정
def harness_durations():
    """`.aimem/runs` 에서 하네스별 완료 실행 시간(초) 목록."""
    out = {}
    for rid in fleet._list_runs():
        try:
            meta = fleet._run_meta(rid) or {}
            state, rc = fleet._run_state(rid)
            if state != "done" or not meta.get("started"):
                continue
            started = _parse_started(meta["started"])
            if started is None:
                continue
            if meta.get("session"):
                ended = fleet._run_last_mtime(rid)   # 세션은 end.json 의 끝난 시각
                if ended is None:
                    continue
            else:
                rcf = fleet.RUNS / f"{rid}.rc"
                if not rcf.exists():
                    continue
                ended = dt.datetime.fromtimestamp(rcf.stat().st_mtime)
            out.setdefault(str(meta.get("harness") or "?"), []).append(max(1.0, (ended - started).total_seconds()))
        except Exception:  # noqa: BLE001 - 기록 하나가 깨져도 진행율은 나와야 한다 (`_busy_slots` 와 같은 방어)
            continue
    return out


def estimate_seconds(node, durations, roster):
    h = node.get("harness") or roster.get(node["slot"], ("", "", ""))[1]
    xs = durations.get(h) or [v for vs in durations.values() for v in vs]
    base = statistics.median(xs) if xs else 120.0
    # 쓰기가 있는 태스크는 읽기 프로브보다 길다 - 쓰기 경로 수만큼 가중
    return base * (1.0 + 0.5 * len(node.get("write", [])))


def progress(g, durations=None):
    """진행율(%)·ETA(초)·임계 경로. 웹 UI 가 그대로 쓰는 구조.

    `durations` 는 `harness_durations()` 결과. 그래프 여럿을 한 번에 셀 때(모니터 `/api/state`) 한 번만 구해
    넘긴다 - 그래프마다 다시 구하면 실행 기록 수 × 그래프 수만큼 파일을 읽는다(2026-11-12: 41개 × 260건, 7초).
    """
    if durations is None:
        durations = harness_durations()
    roster = fleet.roster()
    nodes = {n["id"]: n for n in g["nodes"]}
    est = {k: estimate_seconds(n, durations, roster) for k, n in nodes.items()}
    done_w = sum(est[k] for k, n in nodes.items() if n.get("status") == "done")
    total_w = sum(est.values()) or 1.0
    # 실행 중인 노드는 경과만큼 부분 반영
    running_w = 0.0
    for k, n in nodes.items():
        if n.get("status") == "running" and n.get("attempts"):
            el = _elapsed_since((n["attempts"][-1] or {}).get("started"))
            if el is not None:   # 깨진 started 하나로 status/list/step 출력이 죽지 않게
                running_w += max(0.0, min(est[k], el))
    pct = round(100.0 * (done_w + running_w) / total_w, 1)
    # 임계 경로(남은 노드만) = ETA 하한. 병렬이 충분하면 이 값에 수렴한다.
    remaining = {k: (0.0 if n.get("status") == "done" else est[k]) for k, n in nodes.items()}
    longest = {}

    def lp(k):
        if k in longest:
            return longest[k]
        deps = nodes[k].get("deps", [])
        longest[k] = remaining[k] + max((lp(d) for d in deps), default=0.0)
        return longest[k]

    critical = max((lp(k) for k in nodes), default=0.0)
    conc = _graph_concurrency(g)
    serial = sum(remaining.values()) / conc
    eta_s = max(critical, serial)
    counts = {}
    for n in g["nodes"]:
        counts[n.get("status", "todo")] = counts.get(n.get("status", "todo"), 0) + 1
    return {
        "percent": pct,
        "eta_seconds": round(eta_s),
        "eta_at": (dt.datetime.now() + dt.timedelta(seconds=eta_s)).isoformat(timespec="minutes") if eta_s > 0 else None,
        "basis": {"harness_median_s": {h: round(statistics.median(v)) for h, v in durations.items()},
                  "critical_path_s": round(critical), "serial_over_concurrency_s": round(serial),
                  "concurrency": conc},
        "counts": counts,
        "estimates_s": {k: round(v) for k, v in est.items()},
    }


# ---------------------------------------------------------------- 스케줄러 (루프 한 틱)
def _ready(g):
    nodes = {n["id"]: n for n in g["nodes"]}
    out = []
    for n in g["nodes"]:
        if n.get("status", "todo") != "todo":
            continue
        deps = n.get("deps") or []
        # 모르는 의존 id 를 "충족됨" 으로 보던 것을 막습니다. `validate` 가 잡아 주지만
        # `step` 은 다시 검증하지 않아, 손으로 고친 그래프에서 오타 난 dep 하나가
        # 노드를 곧바로 띄웠습니다 (S4 적대적 검수 7번, REV 111).
        if any(d not in nodes for d in deps):
            continue
        if all(nodes[d].get("status") == "done" for d in deps):
            out.append(n)
    return out


def _busy_slots(g):
    """지금 작업자가 돌고 있는 슬롯 집합. **그래프 밖에서 띄운 실행까지 셉니다.**

    `step()` 은 전체 `running` 개수만 보고 슬롯은 보지 않았습니다. 그래서 관리자가
    손으로 띄운 S2 작업자가 살아 있는데 그래프가 같은 S2 에 노드를 또 띄우는 일이
    실제로 닿아 있었습니다 (S4 적대적 검수 2번, REV 111). `.aimem/runs` 가 정본입니다 -
    그래프 상태만 보면 그래프 밖 실행을 영원히 못 봅니다.
    """
    return _live_scan(g)[0]


def _live_scan(g):
    """`(바쁜 슬롯 집합, {공급자: 도는 세션 수})` - 스케줄러 한 틱에 한 번.

    예전 `_busy_slots` 는 틱마다 실행 기록 **전부**(`_list_runs` 가 메타를 다 읽고 정렬, 그 뒤 하나씩 상태)를
    봤습니다. 끝난 세션 500 + 옛 실행 1500 에서 한 틱 0.29초였고 거의 전부가 여기였습니다(2026-11-13 실측).
    그래서 **돌 수 있는 것만** 봅니다:
      - 옛 실행: `.rc`·`.lost` 가 없는 `.json` 만 (둘 중 하나가 있으면 `_run_state` 가 결코 running 을 주지 않는다)
      - 세션: `end.json` 이 없거나, 이 저장소 표식을 단 프로세스가 살아 있는 것(`live_index`)만.
        `state()` 가 running 을 주려면 둘 중 하나가 꼭 참이다 - 작업자가 end.json 을 미리 써 놓고 계속 도는
        경우도 그 프로세스가 색인에 있으므로 빠지지 않는다. **슬롯이 비어 보이는 쪽으로는 줄이지 않았다.**
    공급자 수는 `fleet_rt.providers.running_by_provider` 와 같은 규칙(도는 **작업자** 세션의 meta `provider`)이고,
    같은 훑기에서 같이 센다 - 그 함수는 세션 폴더 전부를 다시 보므로 틱마다 부르면 줄인 것이 도로 는다.
    관리자 세션은 공급자 자리도 슬롯도 잡지 않는다 - `max_concurrent` 는 작업자 자리 수다(관리자를 세면 유료 공급자에서
    작업자 자리 하나가 라운드 내내 사라진다). 슬롯이 없어도 '모든 슬롯 바쁨' 으로 치지 않는다 (R21 실측).
    """
    busy, by_prov = set(), {}

    def all_slots():
        busy.update(str(n.get("slot")) for n in g.get("nodes", []) if n.get("slot"))

    runs = pathlib.Path(fleet.RUNS)
    try:
        names = set(os.listdir(runs))
    except OSError:
        names = set()
    for name in names:
        if not name.endswith(".json"):
            continue
        rid = name[:-5]
        if f"{rid}.rc" in names or f"{rid}.lost" in names:
            continue
        try:
            state, _ = fleet._run_state(rid)
            if state != "running":
                continue
            meta = fleet._run_meta(rid) or {}
        except Exception:  # noqa: BLE001 - 기록 하나가 깨져도 스케줄러는 돌아야 한다
            continue
        if meta.get("session"):
            continue                    # 같은 id 의 세션 폴더가 있다 - 아래에서 센다
        if meta.get("slot"):
            busy.add(meta["slot"])
        else:
            # 돌고 있는데 어느 슬롯인지 모른다(메타가 깨짐·지워짐) - 모든 슬롯을 바쁜 것으로 본다.
            # 살아 있는 작업자 옆에 두 번째를 띄우는 쪽이 기다리는 쪽보다 나쁘다.
            all_slots()
    sroot = fleet._sessions_root()
    try:
        sids = os.listdir(sroot)
    except OSError:
        return busy, by_prov
    from fleet_rt import sessions as rt_sessions  # noqa: PLC0415
    live = rt_sessions.live_index(sroot)
    for sid in sids:
        d = sroot / sid
        try:
            if sid not in live and (d / "end.json").exists():
                continue
            if fleet._session_dir(sid) is None:
                continue
            if rt_sessions.state(d, live=live).get("state") != "running":
                continue
            meta = rt_sessions.load_meta(d)
        except Exception:  # noqa: BLE001
            continue
        meta = meta if isinstance(meta, dict) else {}
        if meta.get("role") == "manager":
            continue
        if meta.get("provider"):
            by_prov[meta["provider"]] = by_prov.get(meta["provider"], 0) + 1
        if meta.get("slot"):
            busy.add(meta["slot"])
        else:
            all_slots()
    return busy, by_prov


def _spawn_node(g, n, attempt_no):
    prior = ""
    if attempt_no > 1:
        last = n["attempts"][-1]
        prior = (f"\n\n[재시도 {attempt_no}/{n.get('max_attempts', 2)}] 직전 시도(run {last['run_id']}) 는 "
                 f"rc={last.get('rc')} / 검증 rc={last.get('verify_rc')} 로 실패했다. 산출물이 남아 있을 수 있으니 "
                 f"먼저 확인하고 이어서 하라. 직전 검증 출력 꼬리:\n{(last.get('verify_tail') or '')[-600:]}")
        # 직전 작업자가 **무엇을 알아냈는지**도 넘긴다 - 검증 출력만 주면 두 번째 작업자가 같은 조사를 처음부터 다시 한다.
        # 다만 그 판단이 틀렸을 수 있으니(R7 T-099: "기대값이 틀렸다" 는 보고가 사실은 옮겨 적기 실수) 참고로만 준다.
        rep = (last.get("report") or "").strip()
        if rep and not report_ended_in_tool_call(rep):
            prior += ("\n\n직전 작업자의 보고(참고만 하라 - 틀렸을 수 있으니 그대로 믿지 말고 직접 확인하라):\n"
                      + rep[-900:])
    task_file = GRAPHS / f"{g['id']}-{n['id']}-a{attempt_no}.task.md"
    GRAPHS.mkdir(parents=True, exist_ok=True)
    task_file.write_text(n["task"].rstrip() + prior + "\n", encoding="utf-8")
    # 식별자 체계(18:15): 노드 id 가 T-0xx 면 그것이 태스크 id 다. 실행 id = T-050-S1-a2-HHMMSS (fleet.py 가 만든다)
    tid = n["id"] if re.fullmatch(r"T-\d+[A-Z]?", str(n["id"])) else None
    ns = argparse.Namespace(slot=n["slot"], harness=n.get("harness"), model=n.get("model"),
                            task_id=tid, attempt=attempt_no,
                            label=f"{n.get('title','')} ({g['id']})".strip(),
                            write=list(n.get("write", [])), task=None, task_file=str(task_file),
                            project=n.get("project") or g.get("project") or None, round=g.get("round"),
                            timeout=_node_timeout(g, n))
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fleet.cmd_spawn(ns)
    run_id = buf.getvalue().strip().splitlines()[-1]
    n.setdefault("attempts", []).append({"run_id": run_id, "started": _now()})
    n["status"] = "running"
    _log(g, f"spawn {n['id']} attempt {attempt_no} -> {run_id} ({n['slot']})")
    return run_id


VERIFY_TIMEOUT_SEC = 600


def _verify(n):
    """노드의 `verify` 를 `bash -lc` 로 돌린다. (rc, 출력 꼬리 2000자). 시간 초과는 (124, …).

    검증 명령은 작업자가 쓸 수 있는 그래프 파일에서 온다 - 실행기의 권한·환경을 그대로 주면 작업자가 제 울타리 밖으로
    나가는 길이 된다. 그래서 울타리(`fleet_rt.sandbox.wrap`: 저장소·/tmp 만 쓰기, `.env`·`.aimem/tls` 가림, 새 pid
    이름공간) 안에서, 키·세션 표식을 뺀 환경(`clean_env`)으로 돌린다. 울타리를 못 쓰는 기계에서는 환경만 씻고 돌린다
    (실행기가 그래프마다 한 번 로그에 남긴다 - `_note_unconfined`).
    시간 초과면 프로세스 그룹째 죽인다 - 예전에는 bash 만 죽어 손자가 남았다.
    """
    cmd = n.get("verify")
    if not cmd:
        return 0, "(검증 명령 없음 - rc 만 봄)"
    from fleet_rt import sandbox  # noqa: PLC0415
    root = pathlib.Path(ROOT)
    argv, _note = sandbox.wrap(["bash", "-lc", cmd], root)
    try:
        p = subprocess.Popen(argv, cwd=str(root), env=sandbox.clean_env(os.environ, root), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                             start_new_session=True)
    except OSError as e:
        return 127, f"검증을 띄우지 못함: {type(e).__name__}: {e}"[-2000:]
    try:
        out, err = p.communicate(timeout=VERIFY_TIMEOUT_SEC)
        return p.returncode, (out + err)[-2000:]
    except subprocess.TimeoutExpired:
        # 내가 띄운 그룹(새 세션의 리더 = p.pid)만 죽인다. 울타리 안의 것은 bwrap 이 죽으면 `--die-with-parent` 로 같이 끝난다
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            # 그룹을 떠난(setsid 한) 손자가 파이프를 쥐고 있다 - 기다리지 않고 닫는다
            for f in (p.stdout, p.stderr):
                try:
                    f.close()
                except OSError:
                    pass
            p.wait()
        return 124, f"검증 타임아웃({VERIFY_TIMEOUT_SEC}s)"


def _note_unconfined(g):
    """울타리를 못 쓰는 기계면 그래프마다 한 번 로그에 남긴다 (검증 명령이 실행기 권한으로 돈다는 것을 사람이 알게)."""
    from fleet_rt import sandbox  # noqa: PLC0415
    ok, why = sandbox.available()
    if not ok:
        _log_once(g, ("verify-unconfined",), f"warn 검증 명령이 울타리 없이 돕니다 ({why}) - 환경의 키·세션 표식만 뺍니다")


# 첫 줄 앞의 마크다운 장식(인용 `>`, 목록 `-`/`*`/`1.`, 코드 `` ` ``, 괄호 `[ ]`, 제목 `#`)을
# 벗깁니다. 그 뒤 `상태:`/`Status:` 접두가 있으면 label 로 잡습니다 (S4 재검수 결함 3 거짓 음성).
# 선행 BOM(`﻿`)도 장식으로 봅니다. 라벨 앞에 낱말 한두 개(`보고 상태:`, `Report status:`)가
# 붙어도 라벨로 잡습니다 (S4 재검수 결함 9).
_BLOCK_JUNK = r"(?:\s|[*#>`\[\]﻿-]|\d+\.)*"
_BLOCK_JUNK_RE = re.compile(_BLOCK_JUNK)
_BLOCK_PREFIX = re.compile(
    rf"^{_BLOCK_JUNK}(?P<label>(?:[^\W\d_]{{1,20}}\s*){{0,2}}?(?:상태|(?i:status))\s*[:：])?{_BLOCK_JUNK}")
# 낱말 뒤 `(?![A-Za-z0-9_-])` - `REJECTED_FIX`·`BLOCKED-FREE`·`rejection` 이 상태로 읽히던 것을 막습니다.
# `NEEDS-` 는 뒤에 최소 한 글자가 있어야 합니다.
_BLOCK_WORD_SRC = r"(BLOCKED|REJECT|NEEDS-[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)*)(?![A-Za-z0-9_-])"
# 접두가 없으면 **대문자만** - `Rejected 된 항목 없음`·`Blocked 링크 …` 같은 평문은 상태가 아닙니다.
_BLOCK_WORD = re.compile(_BLOCK_WORD_SRC)
_BLOCK_WORD_LABELED = re.compile(_BLOCK_WORD_SRC, re.IGNORECASE)
# 라벨이 없어도 낱말 바로 뒤가 `:`/`：`/`-`/줄 끝(닫는 장식 `*`/`` ` ``/`]` 은 건너뜀)이면 대소문자를
# 가리지 않습니다 - `blocked`, `Blocked: 이유` 를 받고 `Blocked 링크 3개…` 같은 평문은 계속 거부 (결함 9).
_BLOCK_WORD_TERMINATED = re.compile(_BLOCK_WORD_SRC + r"[*`\]]*\s*(?:[:：\-–—]|$)", re.IGNORECASE)


def report_block_reason(report):
    """보고 첫 줄이 사람을 기다리는 상태면 그 말(대문자)을, 아니면 `None` 을 돌려줍니다.

    결함: 완료 판정이 `rc==0 && verify_rc==0` 뿐이라, 작업자가 `상태: BLOCKED - 소유가 아닌
    경로가 필요하다` 고 보고하고 **깨끗이 종료하면 `done`** 이 됐습니다 (S4 검수 큐 9번).
    AIMEM 0.3 상 상태는 보고의 **첫 줄**이므로 첫 비어 있지 않은 줄만 봅니다 - 본문 중간의
    "BLOCKED" 인용까지 잡으면 멀쩡한 DONE 보고를 막습니다.
    """
    if not report:
        return None
    for line in str(report).splitlines():
        if line.strip():
            break
    else:
        return None
    w = None
    m = _BLOCK_PREFIX.match(line)
    if m and m.group("label"):
        w = _BLOCK_WORD_LABELED.match(line[m.end():])
    if not w:
        # 라벨 없이 읽기 - 장식만 벗깁니다 (`BLOCKED 상태: …` 처럼 낱말이 라벨 앞에 오는 경우 포함).
        body = line[_BLOCK_JUNK_RE.match(line).end():]
        w = _BLOCK_WORD.match(body) or _BLOCK_WORD_TERMINATED.match(body)
    return w.group(1).upper() if w else None


_TOOLCALL_TAIL = re.compile(r"^</?(?:tool_call|function|parameter)\b|^<function=", re.IGNORECASE)


def report_limit_hit(text):
    """보고 글자에 사용 한도 꼴이 있으면 True.

    이 함수는 글자만 봅니다 - 실행 rc 는 `step()` 이 함께 판정합니다.
    한도에 걸린 시도는 재시도해도 같은 벽에 부딪히므로 평범한 실패와 구별해야 합니다.
    보고의 마지막 2000자만 봅니다 - 본문 중간에 인용된 한도 문구까지 잡지 않기 위해서입니다.
    """
    return _limit_text_hit(text)


# run id 는 폴더를 벗어날 수 없는 꼴만 받습니다(`..`·`/` 불가) - reader.RUN_ID_RE 와 같은 목적.
_RUN_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def run_limit_signal(run_id):
    """실행 기록의 구조 신호로 사용 한도를 봅니다. 모르면 None.

    claude 하네스만 JSON 을 남깁니다. True/False/None 셋을 돌려줍니다 -
    False 는 "JSON 을 읽었고 오류가 아니다"뿐입니다. 오류인데 한도 표지가 없으면 None 이어야
    `step()` 이 글자 판정으로 넘어갑니다. None 은 "구조 신호가 없다"(codex·opencode, 깨진 파일,
    run_id 꼴 불량)입니다.
    """
    if not isinstance(run_id, str) or len(run_id) > 128 or not _RUN_ID_RE.fullmatch(run_id):
        return None
    try:
        sd = fleet._session_dir(run_id)
        if sd is not None:
            from fleet_rt import harness as rt_harness  # noqa: PLC0415
            sm = fleet._read_json_capped(sd / "meta.json")
            if not isinstance(sm, dict):
                return None
            return rt_harness.get(sm["harness_effective"]).limit_signal(sd)
        meta = fleet._run_meta(run_id)
        if not isinstance(meta, dict) or meta.get("harness") != "claude":
            return None
        raw = fleet.read_regular_bytes(fleet.RUNS / f"{run_id}.out", 1024 * 1024)
        if raw is None:
            return None
        data = json.loads(raw)
        return _result_limit_signal(data)
    except Exception:
        return None


def report_ended_in_tool_call(report):
    """보고의 마지막 줄이 **글자로 찍힌 도구 호출**이면 True.

    R9 실측(T-116, codex+kistillm): 모델이 도구 호출을 본문에 `<tool_call>…</tool_call>` 글자로 내면 하네스는
    그것을 최종 답으로 받아 54초 만에 rc 0 으로 끝납니다 - 파일은 한 줄도 안 바뀌었는데, 노드의 `verify` 가
    "스크립트가 돈다" 같은 느슨한 것이면 `done` 이 됐습니다. 일을 시작도 못 한 시도이므로 실패로 보고 다시 굴립니다.
    """
    if not report:
        return False
    lines = [l.strip() for l in str(report).splitlines() if l.strip()]
    return bool(lines) and bool(_TOOLCALL_TAIL.match(lines[-1]))


def wrote_nothing(n, att):
    """첫 시도가 **쓰라고 받은 경로를 하나도 안 건드리고** 끝났으면 True.

    R9 실측(T-117·T-118): 작업자가 준비 단계에서 rc 0 으로 끝나 파일은 그대로인데, `verify` 가 이미 있던
    스크립트로 통과해 `done` 이 됐습니다(그래프 넷 중 셋). `write` 가 있는 노드의 **첫 시도**에만 봅니다 -
    재시도는 앞 시도가 남긴 것이 이미 맞을 수 있고, `write` 가 없는 노드(검수)는 쓸 것이 없습니다.
    시작 시각을 모르거나 경로를 못 읽으면 False (모르면 막지 않는다).
    """
    write = [w for w in (n.get("write") or []) if isinstance(w, str) and w.strip()]
    if not write or len(n.get("attempts") or []) != 1:
        return False
    try:
        since = dt.datetime.fromisoformat(str(att["started"])).timestamp() - 2
    except (KeyError, ValueError, TypeError):
        return False
    try:
        for w in write:
            # pathlib 의 `**` 는 폴더만 돌려준다 - `x/**` 는 그 아래 파일까지 보게 `x/**/*` 로
            hits = ROOT.glob(w + "/*" if w.endswith("**") else w) if any(c in w for c in "*?[") else [ROOT / w]
            for i, f in enumerate(hits):
                if i >= 5000:
                    return False            # 너무 많다 - 판정을 포기한다
                if f.is_file() and f.stat().st_mtime >= since:
                    return False
    except (OSError, ValueError):
        return False
    return True


_LOGGED_ONCE = set()


def _log_once(g, key, msg):
    """같은 경고를 매 틱 반복해 로그를 채우지 않게 프로세스당 한 번만 남깁니다."""
    k = (str(g.get("id")),) + tuple(key)
    if k in _LOGGED_ONCE:
        return
    _LOGGED_ONCE.add(k)
    try:
        _log(g, msg)
    except (OSError, KeyError):
        pass


def _node_timeout(g, n):
    """`n.timeout_sec` -> `g.node_timeout_sec` -> 1800. 유한한 양수만 받습니다 (S4 재검수 결함 4).

    `nan`/`0`/`-1`/`True` 가 갓 띄운 작업자를 첫 틱에 죽였습니다 (`elapsed <= nan` 은 늘 거짓).
    못 쓰는 값은 버리고 다음 후보로 가며, 오타를 알 수 있게 로그에 한 줄 남깁니다.
    """
    for src, v in (("timeout_sec", n.get("timeout_sec")), ("node_timeout_sec", g.get("node_timeout_sec"))):
        if v is None:
            continue
        x = None
        if not isinstance(v, bool):
            try:
                x = float(v)
            except (TypeError, ValueError, OverflowError):
                x = None
        if x is not None and math.isfinite(x) and x > 0:
            return x
        _log_once(g, ("timeout", n.get("id"), src, repr(v)),
                  f"warn {n.get('id')} - {src}={v!r} 는 유한한 양수가 아니라 무시합니다")
    return float(DEFAULT_NODE_TIMEOUT_SEC)


def _parse_started(s):
    """시각 문자열 -> **naive 로컬** datetime, 못 읽으면 None.

    이 저장소 시각(`_now()`)은 전부 로컬 naive 입니다 - aware 와 빼면 `TypeError` (결함 5).
    tz 가 붙은 값은 **로컬로 변환한 뒤** tz 를 뗍니다. 예전처럼 그냥 떼면 UTC 값이 로컬로
    읽혀 KST 에서 경과가 9시간 늘고, 갓 띄운 작업자가 첫 틱에 죽었습니다 (S4 재검수 결함 8).
    `…Z` 를 못 읽는 파이썬(3.10 이하)을 위해 `+00:00` 으로 바꿔 한 번 더 시도합니다.
    """
    if s is None or isinstance(s, bool):
        return None
    txt = str(s).strip()
    cands = [txt]
    if txt[-1:] in ("Z", "z"):
        cands.append(txt[:-1] + "+00:00")
    for c in cands:
        try:
            d = dt.datetime.fromisoformat(c)
            if d.tzinfo is not None:
                d = d.astimezone().replace(tzinfo=None)
            return d
        except (TypeError, ValueError, OverflowError, OSError):
            continue
    return None


def _elapsed_since(s):
    """`s` 부터 지금까지 초, 못 구하면 None. 파싱과 뺄셈을 한 `try` 로 묶습니다."""
    try:
        d = _parse_started(s)
        if d is None:
            return None
        return (dt.datetime.now() - d).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None


def _proc_state(pid):
    """`/proc/<pid>/stat` 의 상태 문자(`R`/`S`/`Z` …). 읽을 수 없으면 None."""
    try:
        raw = pathlib.Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # comm 은 괄호 안이고 공백·괄호를 품을 수 있어 **마지막** `)` 뒤에서 읽습니다.
    rest = raw[raw.rfind(")") + 1:].split()
    return rest[0] if rest else None


def _pgroup_alive(pgid):
    """그룹에 살아 있는 프로세스가 있는지. 리더가 **좀비(`Z`)** 면 죽은 것으로 봅니다 (S4 재검수 결함 10).

    `run` 은 스포너와 같은 프로세스라 죽인 래퍼가 거두어지지 않은 좀비로 남고, `killpg(pgid, 0)` 은
    좀비 그룹에도 성공해 매번 `KILL_GRACE_SEC` 전체를 기다렸습니다. 리더만 좀비이고 자식이 살아 있는
    경우를 놓치지 않도록, 리더가 좀비면 `/proc` 에서 같은 pgid 의 다른 프로세스를 찾아 봅니다.
    `/proc` 이 없으면 예전 동작 그대로입니다.
    """
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    if _proc_state(pgid) != "Z":
        return True
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return True
    for p in pids:
        if int(p) == pgid:
            continue
        try:
            raw = pathlib.Path(f"/proc/{p}/stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rest = raw[raw.rfind(")") + 1:].split()
        # rest: state ppid pgrp ...
        if len(rest) >= 3 and rest[2] == str(pgid) and rest[0] != "Z":
            return True
    return False


def _cmdline_belongs(pid, run_id, brief):
    """`/proc/<pid>/cmdline` 에 run id·brief 경로·`fleet` 중 하나라도 있는지 (S4 재검수 결함 2).

    True = 그 실행의 것으로 보임, False = 남의 프로세스(pid 재사용), None = 확인 불가(검사 건너뜀).
    완전한 신원 확인이 아니라 값싼 확인입니다.
    """
    if not os.path.isdir("/proc/self"):
        return None                      # 리눅스가 아님 - 검사 건너뜀
    try:
        raw = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
    except FileNotFoundError:
        return False                     # 그 사이 사라졌다 - 죽일 것도 없다
    except OSError:
        return None
    cmd = raw.replace(b"\0", b" ").decode("utf-8", "replace")
    needles = [str(run_id), f".aimem/runs/{run_id}.brief.md", "fleet"]
    if brief:
        needles.append(str(brief))
    return any(s and s in cmd for s in needles)


# run_id -> 마지막 `_kill_run` 이 `refused` 를 낸 이유 (로그·attempt 에 남깁니다, 결함 7).
_LAST_REFUSAL = {}


def _kill_run(run_id, with_outcome=False):
    """run 의 **프로세스 그룹**을 TERM -> (5초 뒤 남아 있으면) KILL. 쓴 pid 를 돌려줍니다.

    `with_outcome=True` 면 `(pid, outcome)` - outcome 은 `killed`/`gone`/`refused`/`foreign`.
    `refused` 는 **작업자가 살아 있을 수 있다**는 뜻이라 호출자가 슬롯을 비우면 안 됩니다
    (거부 이유는 `_LAST_REFUSAL[run_id]`).

    결함 1(S4 재검수): `fleet.py` 는 `bash -c "<CLI>; echo $? > rc"` 를 `start_new_session=True`
    로 띄우므로 `meta.pid` 는 **래퍼** pid 이고 실제 작업자는 그 자식입니다. 래퍼만 죽이면 자식이
    고아로 살아 같은 소유 경로에 계속 씁니다. 그래서 pgid(== 래퍼 pid) 에 `killpg` 합니다.
    보내기 전 안전 검사가 하나라도 어긋나면 **아무도 죽이지 않습니다**: pid 가 정수(bool 아님)·
    1 초과·내 pid 아님, `getpgid(pid) == pid`(정말 세션 리더), pgid 가 0 도 내 그룹도 아님.
    `pkill -f` 는 절대 쓰지 않습니다 (AIMEM 8.0-5).
    """
    meta = fleet._run_meta(run_id) or {}
    pid = meta.get("pid")
    _LAST_REFUSAL.pop(run_id, None)
    sd = fleet._session_dir(run_id)
    if sd is not None:
        # 새 세션은 감독(`fleet_rt.sessions.cancel`)이 끊는다 - 같은 안전 검사에 시작 시각 대조가 더해져 있다.
        from fleet_rt import sessions as rt_sessions  # noqa: PLC0415
        outcome = rt_sessions.cancel(sd, why="그래프 실행기")
        if outcome == "refused":
            _LAST_REFUSAL[run_id] = rt_sessions.LAST_REFUSAL.get(str(sd)) or "안전 검사 거부"
        return (pid, outcome) if with_outcome else pid

    def out(o, why=None):
        if o == "refused":
            _LAST_REFUSAL[run_id] = why or "안전 검사 거부"
        return (pid, o) if with_outcome else pid

    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1 or pid == os.getpid():
        return out("refused", f"pid 값이 쓸 수 없음({pid!r})")
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return out("gone")
    except OSError as e:
        return out("refused", f"getpgid 실패: {e.__class__.__name__}")
    try:
        mine = os.getpgid(0)
    except OSError as e:
        return out("refused", f"내 pgid 조회 실패: {e.__class__.__name__}")
    if pgid != pid:
        return out("refused", f"세션 리더 아님: getpgid={pgid}")
    if pgid == 0 or pgid == mine:
        return out("refused", f"내 프로세스 그룹({pgid})")
    belongs = _cmdline_belongs(pid, run_id, meta.get("brief"))
    if belongs is False:
        return out("foreign")
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return out("gone")
    except OSError as e:
        return out("refused", f"SIGTERM 실패: {e.__class__.__name__}")
    deadline = time.time() + KILL_GRACE_SEC
    while time.time() < deadline:
        if not _pgroup_alive(pgid):
            return out("killed")
        time.sleep(0.2)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass
    return out("killed")


def _mark_lost(run_id):
    """`fleet.py` 의 lost 판정·경과 고정 마커. 이미 있으면 건드리지 않습니다."""
    if fleet._session_dir(run_id) is not None:
        return   # 세션은 `end.json` 이 끝남 기록이다 (`cancel` 이 적는다). 감독이 사라진 세션은 그 자체로 lost
    lost = fleet.RUNS / f"{run_id}.lost"
    if lost.exists():
        return
    fleet.RUNS.mkdir(parents=True, exist_ok=True)
    lost.write_text(json.dumps({"ended": _now()}), encoding="utf-8")


def _retry_or_fail(g, n, why):
    """실패한 시도 뒤의 공통 규칙 - 한도 안이면 `todo`(재스폰), 넘으면 `failed`."""
    if len(n["attempts"]) < int(n.get("max_attempts", 2)):
        n["status"] = "todo"  # 다음 틱에 재스폰 (루프)
        _log(g, f"retry-queued {n['id']} {why}")
    else:
        n["status"] = "failed"
        _log(g, f"FAILED {n['id']} after {len(n['attempts'])} attempts")


# ---------------------------------------------------------------- 실패의 종류 (설계 5.3)
def _session_end(run_id):
    """새 세션이면 감독의 판정(`fleet_rt.sessions.state`), 옛 실행이면 None. 예외를 내지 않는다."""
    try:
        d = fleet._session_dir(run_id)
        if d is None:
            return None
        from fleet_rt import sessions as rt_sessions  # noqa: PLC0415
        return rt_sessions.state(d)
    except Exception:  # noqa: BLE001 - 판정을 못 하면 옛 규칙(work)으로 간다
        return None


def session_fail_kind(sinfo, cut_orphan=False):
    """끝난 세션의 감독 판정 -> `"infra"` / `"timeout"` / None(보고를 읽어 정할 일).

    infra = 일을 못 한 까닭이 작업자가 아니라 공급자·전송·감독에 있다: 침묵으로 끊김(`stalled`), 감독이 정한
    `fail_kind: infra`(재접속·시간 초과 오류만 있고 모델이 한마디도 못 함, 하네스를 못 띄움, 감독 내부 오류),
    감독이 사라짐(`lost`), 감독 없이 남은 하네스를 실행기가 끊음(`cut_orphan` 이고 `killed`).
    그 밖의 `killed`(사람이 끊음)는 옛 `.lost` 와 같이 보통 실패로 둔다. 옛 실행(`sinfo` None)은 늘 None.
    """
    if not isinstance(sinfo, dict):
        return None
    st, kind = sinfo.get("state"), sinfo.get("fail_kind")
    if st in ("stalled", "lost") or kind == "infra" or (cut_orphan and st == "killed"):
        return "infra"
    if st == "timeout" or kind == "timeout":
        return "timeout"
    return None


def _infra_count(n):
    """노드의 **사람이 아직 비우지 않은** 기반 장애 횟수 (`unblock` 이 `cleared` 로 비운다)."""
    return sum(1 for a in n.get("infra_attempts") or [] if isinstance(a, dict) and not a.get("cleared"))


def _infra_requeue(g, n, att, why):
    """기반 장애로 끝난 시도: 시도로 세지 않고(`attempts` -> `infra_attempts`) 다시 넣거나, 겹쳤으면 막는다.

    `failed` 가 아니라 `blocked` 인 까닭: 태스크에는 잘못이 없다 - 공급자가 살아나면 사람이 `unblock` 으로
    그대로 이어 가면 된다. 유료 모델로 자동 대체하지 않는다(2026-11-10 결정: 장애는 보고만).
    """
    att["fail_kind"] = "infra"
    att["verify_rc"], att["verify_tail"] = None, f"기반 장애({why}) - 시도로 세지 않는다"
    try:
        att["provider"] = (fleet._run_meta(att["run_id"]) or {}).get("provider")
    except Exception:  # noqa: BLE001
        pass
    n.setdefault("infra_attempts", []).append(n["attempts"].pop())
    k = _infra_count(n)
    if k >= INFRA_RETRY_MAX:
        att["infra"] = True
        n["infra"] = True
        n["status"] = "blocked"
        _log(g, f"INFRA {n['id']} - 공급자 {att.get('provider') or '?'} 가 {k}번 연달아 응답하지 않았습니다 ({why}). "
                f"태스크 잘못이 아닙니다. 사람이 공급자를 확인한 뒤 `fleet_graph.py unblock {g.get('id')} {n['id']}`")
    else:
        n["status"] = "todo"
        _log(g, f"infra-requeue {n['id']} ({att['run_id']}, {why}) - 시도로 세지 않음 ({k}/{INFRA_RETRY_MAX})")


def _probe_wait_block(g, n, prov, waited, line):
    """공급자가 `PROBE_WAIT_MAX_SEC` 넘게 응답하지 않아 기다리던 노드를 막는다 - `INFRA_RETRY_MAX` 에 닿은 것과 같은 꼴
    (`blocked` + `infra`)이라 `unblock` 이 그대로 풀고, 관리자는 `move` 로 다른 슬롯에 옮길 수 있다."""
    n["infra"] = True
    n["status"] = "blocked"
    n.pop("waiting", None)
    n.pop("waiting_since", None)
    last = (n.get("infra_attempts") or [None])[-1]
    if isinstance(last, dict):
        last["infra"] = True
    _log(g, f"INFRA {n['id']} - 공급자 {prov} 가 {int(waited)}초 넘게 응답하지 않아 기다리기를 그만둡니다 ({line}). "
            f"태스크 잘못이 아닙니다. `fleet_graph.py move {g.get('id')} {n['id']} --slot S<n>` 으로 다른 슬롯에 옮기거나 "
            f"공급자를 확인한 뒤 `fleet_graph.py unblock {g.get('id')} {n['id']}`")


# ---------------------------------------------------------------- 공급자 문지기 (설계 3.5·5.4)
def _rt_cfg(g):
    """`fleet.toml` (mtime 캐시). 못 읽으면 None - 문지기 없이 옛 규칙(슬롯·concurrency)으로만 띄운다."""
    try:
        from fleet_rt import config as rt_config  # noqa: PLC0415
        return rt_config.load(fleet.ROOT)
    except Exception as e:  # noqa: BLE001
        _log_once(g, ("cfg", type(e).__name__), f"warn fleet.toml 을 읽지 못해 공급자 문지기를 끕니다: {e}")
        return None


def _node_provider(cfg, n):
    """노드가 뜨면 쓸 공급자. `cmd_spawn` 과 같은 고르기(`fleet.spawn_harness_model`). 모르면 None(막지 않음)."""
    if cfg is None:
        return None
    try:
        h, m = fleet.spawn_harness_model(n.get("slot"), n.get("harness"), n.get("model"))
        return cfg.provider_of(h, m) if h else None
    except Exception:  # noqa: BLE001
        return None


#: 공급자 -> (monotonic 시각, ok, 한 줄). 프로세스 안에서만 산다.
_PROBE_CACHE = {}


def _probe_cached(cfg, provider):
    """`fleet_rt.providers.probe` 를 `PROBE_TTL_SEC` 동안 재사용한다. 예외는 '응답 없음' 으로 본다."""
    hit = _PROBE_CACHE.get(provider)
    now = time.monotonic()
    if hit and now - hit[0] < PROBE_TTL_SEC:
        return hit[1], hit[2]
    try:
        from fleet_rt import providers as rt_providers  # noqa: PLC0415
        ok, line = rt_providers.probe(cfg, provider)
    except Exception as e:  # noqa: BLE001
        ok, line = False, f"점검 오류: {type(e).__name__}"
    _PROBE_CACHE[provider] = (now, bool(ok), str(line))
    return bool(ok), str(line)


def _set_waiting(g, n, why, detail=""):
    """준비됐는데 못 뜨는 까닭을 노드에 적는다(`provider:<p>`·`probe:<p>`·`slot:<S>`·`concurrency:<n>`, 풀리면 지움).
    바뀌었으면 True. 까닭이 바뀔 때 `waiting_since` 에 그 시각을 적는다 - 얼마나 기다렸는지 보려고.

    로그는 **바뀔 때 한 번** - 틱이 2초라 매 틱 남기면 로그가 그것으로 찬다.
    """
    if n.get("waiting") == why:
        return False
    if why is None:
        n.pop("waiting", None)
        n.pop("waiting_since", None)
        return True
    n["waiting"] = why
    n["waiting_since"] = _now()
    _log(g, f"wait {n['id']} - {why}" + (f" ({detail})" if detail else ""))
    return True


def default_concurrency(nodes):
    """그래프의 기본 동시성 = 노드가 쓰는 서로 다른 슬롯 수(최소 1). 슬롯 하나는 한 번에 하나만 돌고 공급자 자리는
    문지기가 따로 지키므로, 이보다 작은 수는 라운드를 말없이 늦출 뿐이다."""
    return max(1, len({str(n.get("slot")) for n in nodes or [] if isinstance(n, dict) and n.get("slot")}))


def _graph_concurrency(g):
    try:
        v = int(g.get("concurrency") or 0)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else default_concurrency(g.get("nodes"))


def _dependents(g):
    """노드 id -> 그 노드를 (직접·간접으로) 기다리는 노드 수. 같은 자리를 다툴 때 많은 쪽을 먼저 띄운다."""
    rev = {}
    for n in g["nodes"]:
        for d in n.get("deps") or []:
            rev.setdefault(d, set()).add(n["id"])
    out = {}
    for n in g["nodes"]:
        seen, stack = set(), list(rev.get(n["id"], ()))
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            stack.extend(rev.get(k, ()))
        out[n["id"]] = len(seen)
    return out


# ---------------------------------------------------------------- 보드 동기화 (설계 5.8)
#: 노드 상태 -> 보드 `tasks.status`. `todo`(재시도·중지로 되돌아감)는 보드를 건드리지 않는다.
#: done 은 DONE 이 아니라 REVIEW - 판정(REVIEW -> DONE)은 관리자가 한다.
BOARD_STATUS = {"running": "IN-PROGRESS", "done": "REVIEW", "failed": "BLOCKED", "blocked": "BLOCKED"}
BOARD_ACTOR = "그래프 실행기"
_TASK_ID_RE = re.compile(r"T-\d+[A-Z]?")


def _board_db():
    """보드 DB 는 실행 기록 옆의 `aimem.db` - `aimem_db.DB` 가 아니라 `fleet.RUNS` 에서 얻는다
    (임시 폴더로 갈아끼운 검사가 운영 DB 를 고치지 않게)."""
    return pathlib.Path(fleet.RUNS).parent / "aimem.db"


def _board_sync(task_id, status, slot=None, g=None):
    """보드 `tasks.status` 를 `status` 로. 고쳤으면 True, 안 고쳤으면 False, 못 했으면 None.

    - `DONE`·`REJECTED` 는 덮지 않고, 행을 만들지 않고, DB 파일이 없으면 아무것도 안 한다(새로 만들지 않게 `mode=rw`)
    - 고쳤으면 `aimem_db.py task set` 처럼 `events` 에 `task` 줄을 하나 남긴다
    - 스냅샷 `AIMEM-state.md` 는 **다시 만들지 않는다** - 2초 틱마다 추적 파일을 고쳐 쓰게 된다. 낡은 스냅샷은
      린터가 `STATE_SNAPSHOT_STALE` 로 짚고 관리자가 체크포인트·라운드 마감에 render 한다
    - 실패해도 실행기를 멈추지 않는다(로그 한 번)
    """
    db = _board_db()
    if not db.is_file():
        return None
    try:
        con = sqlite3.connect(db.as_uri() + "?mode=rw", uri=True, timeout=2)
        try:
            with con:
                now = _now()
                cur = con.execute("UPDATE tasks SET status=?, updated=? WHERE id=? AND status NOT IN ('DONE','REJECTED') "
                                  "AND status != ?", (status, now, task_id, status))
                hit = cur.rowcount > 0
                if hit:
                    r = con.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
                    try:
                        rev = int(r[0]) if r else None
                    except (TypeError, ValueError):
                        rev = None
                    con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                                (now, BOARD_ACTOR, rev, "task", f"{task_id} {status} {slot or ''}".strip()))
            return hit
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001 - 보드가 잠겨도 그래프는 돈다
        if g is not None:
            _log_once(g, ("board", type(e).__name__), f"warn 보드 동기화 실패({task_id} -> {status}): {type(e).__name__}: {e}")
        return None


def _board_sync_changes(g, before):
    """틱 앞의 노드 상태 `before` 와 지금을 견줘 바뀐 태스크 노드만 보드에 옮긴다."""
    for n in g.get("nodes") or []:
        nid, st = str(n.get("id")), n.get("status", "todo")
        if before.get(nid) == st or st not in BOARD_STATUS or not _TASK_ID_RE.fullmatch(nid):
            continue
        _board_sync(nid, BOARD_STATUS[st], n.get("slot"), g)


def _check_timeout(g, n, att):
    """아직 running 인 시도가 노드 한도를 넘었으면 죽이고 실패 처리합니다. 처리했으면 True.

    결함: 작업자가 영영 안 끝나면 `run` 이 `--timeout` 전체를 그 노드 하나에 썼습니다
    (S4 검수 큐 8번). 시작 시각이 깨져 있으면 판정 자체를 건너뜁니다 - 멀쩡한 작업자를
    죽이는 쪽이 기다리는 쪽보다 나쁩니다.
    """
    elapsed = _elapsed_since(att.get("started"))
    if elapsed is None:
        _log_once(g, ("started", n.get("id"), att.get("run_id"), repr(att.get("started"))),
                  f"warn {n.get('id')} - started={att.get('started')!r} 를 읽지 못해 타임아웃 판정을 건너뜁니다")
        return False
    limit = _node_timeout(g, n)
    if elapsed <= limit:
        return False
    pid, outcome = _kill_run(att["run_id"], with_outcome=True)
    if outcome == "refused":
        # S4 재검수 결함 7: 아무도 죽이지 못했는데 `.lost` + 재시도를 하면 `_busy_slots` 에서
        # 슬롯이 빠지고 다음 틱이 **살아 있는 원래 작업자 옆에** 두 번째 작업자를 띄웁니다.
        # `.lost` 를 만들지 않고(슬롯은 계속 바쁨) 재시도 없는 터미널 `blocked` 로 둡니다.
        reason = _LAST_REFUSAL.get(att["run_id"]) or "안전 검사 거부"
        att.update({"timeout": True, "kill_outcome": "refused", "kill_reason": reason, "fail_kind": "timeout",
                    "timeout_at": _now(), "timeout_elapsed_s": int(elapsed)})
        n["status"] = "blocked"
        _log(g, f"timeout {n['id']} - 죽이지 못했습니다 (pid {pid if pid is not None else '?'}, {reason}). "
                f"사람이 확인해야 합니다")
        return True
    _mark_lost(att["run_id"])
    att["kill_outcome"] = outcome
    att.update({"ended": _now(), "rc": 124, "state": "timeout", "timeout": True, "fail_kind": "timeout"})
    # 끊긴 작업자가 그때까지 적은 말을 남긴다 - 재시도 브리프가 "직전 보고" 로 넘긴다. 전에는 한도로 끊기면 아무것도
    # 안 넘어가, 45분 동안 알아낸 것("탐침 훅을 goto 전에 걸어 죽었다")을 다음 작업자가 처음부터 다시 찾았다 (R13 T-164).
    try:
        att["report"] = (fleet.run_report(att["run_id"]) or "")[-4000:]
    except Exception:  # noqa: BLE001 - 보고를 못 읽어도 재시도는 가야 한다
        pass
    if outcome == "foreign":
        _log(g, f"timeout {n['id']} - pid {pid} 가 그 실행의 것이 아닙니다 (죽이지 않음)")
    _log(g, f"timeout {n['id']} after {int(elapsed)}s (run {att['run_id']}, pid {pid if pid is not None else '?'}, {outcome})")
    _retry_or_fail(g, n, "rc=124 (timeout)")
    return True


def _fleet_mode():
    """`fleet_ctl` 의 함대 모드. 읽지 못하면 `running`(옛 동작)으로 봅니다."""
    try:
        import fleet_ctl  # noqa: PLC0415 - fleet_ctl 이 이 모듈을 import 하므로 지연
        return fleet_ctl.mode()
    except Exception:  # noqa: BLE001
        return "running"


def halt_running(g, why="완전 중지"):
    """완전 중지: running 노드의 작업자를 죽이고 노드를 `todo` 로 되돌립니다. 바꿨으면 True.

    끊긴 시도는 `attempts` 에서 빼서 `stopped_attempts` 로 옮깁니다 - 사람이 멈춘 것이라
    **재시도 횟수로 세지 않습니다.** '실행' 으로 이어 가면 그 노드부터 다시 뜹니다.
    `_kill_run` 이 `refused` 면(작업자가 살아 있을 수 있음) 노드를 `blocked` 로 두고 사람에게 넘깁니다.
    """
    changed = False
    for n in g["nodes"]:
        if n.get("status") != "running" or not n.get("attempts"):
            continue
        att = n["attempts"][-1]
        pid, outcome = _kill_run(att["run_id"], with_outcome=True)
        if outcome == "refused":
            att.update({"kill_outcome": "refused", "kill_reason": _LAST_REFUSAL.get(att["run_id"])})
            n["status"] = "blocked"
            _log(g, f"halt {n['id']} - 죽이지 못했습니다 ({_LAST_REFUSAL.get(att['run_id'])}). 사람이 확인해야 합니다")
        else:
            _mark_lost(att["run_id"])
            att.update({"ended": _now(), "state": "stopped", "kill_outcome": outcome, "stopped_by": why})
            n.setdefault("stopped_attempts", []).append(n["attempts"].pop())
            n["status"] = "todo"
            _log(g, f"halt {n['id']} ({att['run_id']}, {outcome}) - {why}. 재시도 횟수로 세지 않음")
        changed = True
    if changed:
        _save(g)
    return changed


def step(g, concurrency=None, allow_spawn=None, hold_on_block=False):
    """한 틱: 끝난 실행을 거두어 검증하고, 실패면 재시도(한정), 준비된 노드를 띄웁니다.

    사용 한도 판정은 실행 rc != 0 이고 보고가 한도 꼴일 때만 합니다. rc == 0 이면
    보고에 한도 낱말이 있어도 보통 경로(검증 → done/재시도)로 갑니다.

    `allow_spawn` 이 None 이면 함대 모드(`fleet_ctl`)로 정합니다 - `running` 일 때만 띄우고,
    `paused`/`ready` 는 거두기만, `stopped` 는 running 노드를 정리(`halt_running`)하고 끝냅니다.

    `validate_graph` 는 여기서 돌리지 않습니다 - 수십 분 도는 루프의 매 틱마다 명부·소유권을
    다시 읽게 됩니다. `cmd_run`/`cmd_step` 이 시작 전에 한 번 돌립니다.

    틱 끝에 상태가 바뀐 태스크 노드를 보드에 옮깁니다(`_board_sync_changes`) - 도중에 예외가 나도 옮깁니다.

    `hold_on_block` 이면 이 틱에 노드가 새로 failed/blocked 된 순간 띄우기를 건너뜁니다 - 거두기와 띄우기가 한 틱이라,
    호출자가 틱 뒤에 보고 멈추면 이미 그 자리에 다음 노드가 떠 있습니다 (`run --stop-on-block`).
    """
    before = {str(n.get("id")): n.get("status", "todo") for n in g.get("nodes") or []}
    try:
        return _step(g, concurrency, allow_spawn, hold_on_block)
    finally:
        _board_sync_changes(g, before)


def _step(g, concurrency=None, allow_spawn=None, hold_on_block=False):
    conc = concurrency or _graph_concurrency(g)
    bad_before = {n.get("id") for n in g["nodes"] if n.get("status") in ("failed", "blocked")}
    if allow_spawn is None:
        m = _fleet_mode()
        if m == "stopped":
            halt_running(g, "완전 중지")
            return all(n.get("status") in TERMINAL for n in g["nodes"])
        allow_spawn = m == "running"
    changed = False
    # 한 틱에 /proc 훑기는 한 번: 여기서 만든 색인을 `fleet_rt.sessions` 가 1초 캐시로 들고 있어
    # 아래의 `fleet._run_state`·`_session_orphaned` 가 세션마다 다시 훑지 않는다 (그 함수들은 색인을 받지 않는다).
    if any(n.get("status") == "running" for n in g["nodes"]):
        try:
            from fleet_rt import sessions as rt_sessions  # noqa: PLC0415
            if fleet._sessions_root().is_dir():
                rt_sessions.live_index(fleet._sessions_root())
        except Exception:  # noqa: BLE001 - 캐시를 못 데워도 각 조회가 스스로 훑는다
            pass
    # 1) 거두기 (+ 노드별 타임아웃, + 보고 첫 줄 BLOCKED 판정, + 실패의 종류)
    for n in g["nodes"]:
        if n.get("status") != "running":
            continue
        if not n.get("attempts"):
            # running 인데 시도 기록이 없다 - 거둘 실행이 없으니 todo 로 되돌립니다 (예전엔 IndexError).
            n["status"] = "todo"
            _log(g, f"warn {n.get('id')} - running 인데 attempts 가 비어 todo 로 되돌립니다")
            changed = True
            continue
        att = n["attempts"][-1]
        state, rc = fleet._run_state(att["run_id"])
        cut_orphan = False
        if state == "running" and fleet._session_orphaned(att["run_id"]):
            # 감독 프로세스가 죽고 하네스만 남았다 - 지켜보는 이가 없으니 노드 한도까지 기다리지 않고 끊는다.
            # 끊긴 세션은 기반 장애(infra)로 다시 넣는다. 거부되면 running 인 채 둔다(슬롯 유지).
            _pid, outcome = _kill_run(att["run_id"], with_outcome=True)
            _log(g, f"orphaned {n['id']} ({att['run_id']}) - 감독 없이 남은 작업자를 끊음 ({outcome})")
            if outcome != "refused":
                state, rc = fleet._run_state(att["run_id"])
                cut_orphan = True
        if state == "running":
            if _check_timeout(g, n, att):
                changed = True
            continue
        att["ended"], att["rc"], att["state"] = _now(), rc, state
        att["report"] = fleet.run_report(att["run_id"])[:4000]
        sinfo = _session_end(att["run_id"])
        if sinfo is not None:
            att["session_state"] = sinfo.get("state")
            if sinfo.get("why"):
                att["why"] = str(sinfo["why"])[:300]
        block = report_block_reason(att["report"]) if rc == 0 else None
        if block:
            # 사람이 풀어야 할 일 - 재시도해도 같은 벽에 부딪히므로 바로 blocked (AIMEM 8.0-4-3).
            att["report_status"] = block
            att["fail_kind"] = "work"
            att["verify_rc"], att["verify_tail"] = None, f"검증 생략: 보고 상태 {block}"
            n["status"] = "blocked"
            first = next((l.strip() for l in att["report"].splitlines() if l.strip()), "")
            _log(g, f"BLOCKED {n['id']} - {first[:60]}")
            changed = True
            continue
        if rc != 0:
            sig = run_limit_signal(att["run_id"])
            limit = report_limit_hit(att["report"]) if sig is None else sig
        else:
            sig = None
            limit = False
        if limit:
            # rc 를 함께 봅니다: 250건 전수 재검에서 rc 0 의 정상 DONE 보고가 3건 오인되었고,
            # 진짜 한도(rc 1) 1건만 남깁니다. rc != 0 이면 검증을 돌리지 않고 바로 blocked.
            att["limit"] = True
            att["fail_kind"] = "limit"
            n["limit"] = True
            att["verify_rc"], att["verify_tail"] = -4, "사용 한도로 끊겼다 - 재시도하지 않는다"
            n["status"] = "blocked"
            source = "구조 신호" if sig is True else "보고 글자"
            _log(g, f"limit {n['id']} ({att['run_id']}) - 사용 한도로 끊김 ({source})")
            changed = True
            continue
        kind = session_fail_kind(sinfo, cut_orphan) if (rc != 0 or state != "done") else None
        if kind == "infra":
            # 공급자·전송이 죽은 것 - 시도로 세지 않고 다시 넣는다 (설계 5.3). 옛 실행에는 이 판정이 없다.
            _infra_requeue(g, n, att, (sinfo or {}).get("why") or (sinfo or {}).get("state") or "기반 장애")
            changed = True
            continue
        if rc == 0 and report_ended_in_tool_call(att["report"]):
            # 도구 호출을 글자로 찍고 끝난 시도 - 한 일이 없다. verify 가 느슨해도 done 이 되지 않게 (R9 T-116)
            vrc, vtail = -2, "작업자가 도구 호출을 본문에 글자로 찍고 끝났다 - 한 일이 없다. 처음부터 다시 하라"
            _log(g, f"aborted {n['id']} ({att['run_id']}) - 보고가 도구 호출 글자로 끝남")
        elif rc == 0 and wrote_nothing(n, att):
            vrc, vtail = -3, ("작업자가 쓰라고 받은 경로(" + ", ".join(n.get("write") or [])[:300] + ")를 하나도 고치지 않고 끝났다. "
                              "고칠 것이 정말 없다면 보고 첫 줄에 그 이유를 적어라")
            _log(g, f"no-op {n['id']} ({att['run_id']}) - write 경로가 하나도 안 바뀜")
        else:
            if rc == 0:
                if n.get("verify"):
                    _note_unconfined(g)
                vrc, vtail = _verify(n)
            else:
                vrc, vtail = -1, "실행 rc != 0"
        att["verify_rc"], att["verify_tail"] = vrc, vtail
        if rc == 0 and vrc == 0:
            att["fail_kind"] = None
            n["status"] = "done"
            _log(g, f"done {n['id']} ({att['run_id']})")
        else:
            att["fail_kind"] = "timeout" if kind == "timeout" else "work"
            _retry_or_fail(g, n, f"rc={rc} verify_rc={vrc}")
        changed = True
    # 2) 의존이 실패한 노드는 막힘으로
    nodes = {n["id"]: n for n in g["nodes"]}
    for n in g["nodes"]:
        if n.get("status", "todo") == "todo" and any(nodes[d].get("status") in ("failed", "blocked")
                                                     for d in n.get("deps", []) if d in nodes):
            n["status"] = "blocked"
            _log(g, f"blocked {n['id']} (의존 실패)")
            changed = True
    for n in g["nodes"]:
        if n.get("status", "todo") != "todo" and "waiting" in n:
            n.pop("waiting")           # 떴거나 끝난 노드의 대기 까닭은 지운다
            n.pop("waiting_since", None)
            changed = True
    if hold_on_block and any(n.get("status") in ("failed", "blocked") and n.get("id") not in bad_before for n in g["nodes"]):
        allow_spawn = False
    # 3) 띄우기 (fan-out, 동시성 상한, 슬롯 바쁨, **공급자 자리**) - 함대가 '실행' 일 때만.
    # 준비된 노드가 없으면 실행 기록을 훑지도 않는다 - 대부분의 틱은 여기서 싸게 끝난다.
    running = sum(1 for n in g["nodes"] if n.get("status") == "running")
    ready = _ready(g) if allow_spawn else []
    if ready and running >= conc:
        # 동시성 상한이 붙잡고 있다는 것도 다른 까닭처럼 적는다 - 말없이 늦어지지 않게
        for n in ready:
            changed |= _set_waiting(g, n, f"concurrency:{conc}")
        ready = []
    if ready:
        busy, by_prov = _live_scan(g)
        cfg = _rt_cfg(g)
        deps_on = _dependents(g)
        order = {n["id"]: i for i, n in enumerate(g["nodes"])}
        # 같은 자리를 다투면 뒤에 걸린 노드가 많은 것부터, 같으면 그래프 순서 (설계 5.4)
        ready.sort(key=lambda n: (-deps_on.get(n["id"], 0), order[n["id"]]))
    for n in ready:
        if running >= conc:
            changed |= _set_waiting(g, n, f"concurrency:{conc}")
            continue
        slot = n.get("slot")
        if slot in busy:
            changed |= _set_waiting(g, n, f"slot:{slot}")
            continue
        prov = _node_provider(cfg, n)
        if prov and by_prov.get(prov, 0) >= cfg.max_concurrent(prov):
            changed |= _set_waiting(g, n, f"provider:{prov}",
                                    f"{by_prov.get(prov, 0)}/{cfg.max_concurrent(prov)} 자리 참")
            continue
        if prov and n.get("infra_attempts"):
            ok, line = _probe_cached(cfg, prov)
            if not ok:
                changed |= _set_waiting(g, n, f"probe:{prov}", line)
                waited = _elapsed_since(n.get("waiting_since"))
                if waited is not None and waited > PROBE_WAIT_MAX_SEC:
                    _probe_wait_block(g, n, prov, waited, line)
                    changed = True
                continue
        _set_waiting(g, n, None)
        # 스폰 직후 저장합니다. 예전에는 한 틱의 끝에서 한 번만 저장해, 뒤 노드가
        # `SystemExit`(명부에 없는 슬롯 등)로 죽으면 **앞에서 띄운 작업자가 그래프에
        # 기록되지 않고 고아로 남았습니다** (S4 적대적 검수 "고아 스폰", REV 111).
        try:
            _spawn_node(g, n, len(n.get("attempts", [])) + 1)
        except SystemExit as e:
            n["status"] = "failed"
            _log(g, f"FAILED {n['id']} - 스폰 거절: {e}")
            changed = True
            _save(g)
            continue
        busy.add(slot)
        running += 1
        if prov:
            by_prov[prov] = by_prov.get(prov, 0) + 1
        changed = True
        _save(g)
    if changed:
        _save(g)
    return all(n.get("status") in TERMINAL for n in g["nodes"])


# ---------------------------------------------------------------- CLI
#: 한 라운드의 상한 (2026-11-11 REV 155). 브리프 문구로만 있을 때 R9 는 그래프 5·태스크 11 로 넘겼고, R10 은 반대로
#: 태스크 10 에 걸려 **수정 뒤 재검수**를 포기했습니다. 그래서 둘로 나눕니다:
#:  - 새 일을 벌이는 상한: 그래프 3 · 태스크 10 (관리자 컨텍스트를 지키려는 원래 뜻)
#:  - 검수가 찾은 것을 고치고 다시 검수하는 그래프(`--followup`)는 그 위로 절대 상한까지: 그래프 6 · 태스크 18
ROUND_GRAPHS, ROUND_TASKS = 3, 10
ROUND_GRAPHS_HARD, ROUND_TASKS_HARD = 6, 18


def round_usage(rnd, exclude=None):
    """그 라운드가 지금까지 만든 (그래프 수, 서로 다른 태스크 id 집합). 같은 태스크를 새 그래프로 다시 굴려도 한 번만 셉니다."""
    graphs, tasks = 0, set()
    if rnd is None or not GRAPHS.exists():
        return graphs, tasks
    for f in GRAPHS.glob("G-*.json"):
        try:
            g = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(g, dict) or g.get("round") != rnd or g.get("id") == exclude:
            continue
        graphs += 1
        tasks |= {str(n.get("id")) for n in g.get("nodes") or [] if isinstance(n, dict)}
    return graphs, tasks


def round_budget_problem(rnd, new_ids, followup, exclude=None):
    """이 그래프를 만들면 라운드 상한을 넘는가. 넘으면 사람이 읽을 한 문단, 아니면 None. 도는 라운드가 없으면 보지 않습니다."""
    if rnd is None:
        return None
    used_g, used_t = round_usage(rnd, exclude)
    g_after, t_after = used_g + 1, len(used_t | {str(i) for i in new_ids})
    now = f"R{rnd} 은 지금 그래프 {used_g}개 · 태스크 {len(used_t)}개이고, 이 그래프를 더하면 그래프 {g_after}개 · 태스크 {t_after}개입니다."
    if g_after > ROUND_GRAPHS_HARD or t_after > ROUND_TASKS_HARD:
        return (f"라운드 절대 상한(그래프 {ROUND_GRAPHS_HARD} · 태스크 {ROUND_TASKS_HARD})을 넘습니다. {now} "
                "남은 일은 요청을 PLANNED 로 두고 PROGRESS.md·보고 (5)에 적어 다음 라운드로 넘기십시오.")
    if (g_after > ROUND_GRAPHS or t_after > ROUND_TASKS) and not followup:
        return (f"라운드 상한(그래프 {ROUND_GRAPHS} · 태스크 {ROUND_TASKS})을 넘습니다. {now} "
                "**검수가 찾은 결함을 고치거나 그 수정을 다시 검수하는 그래프**라면 "
                "`--followup \"<어느 검수·어느 결함의 후속인지>\"` 를 붙여 다시 만드십시오"
                f"(절대 상한 그래프 {ROUND_GRAPHS_HARD} · 태스크 {ROUND_TASKS_HARD}). 새로 벌이는 일이면 다음 라운드로 넘기십시오.")
    return None


def graph_shape(g):
    """그래프의 병렬 모양. `{"nodes", "levels": [[노드 id …], …], "notes": [사람이 읽을 말 …]}`.

    단계 = 의존을 따라간 깊이(앞선 노드가 다 끝나야 뜰 수 있는 차례). 한 단계 안의 노드는 동시에 뜰 수 있다 -
    단, 슬롯 하나는 한 번에 하나만 돌리므로 같은 단계의 노드가 한 슬롯에 몰리면 그만큼 줄을 선다.
    판단은 관리자의 몫이라 막지 않고 알려만 준다 (`new` 가 찍는다). 순환은 `validate_graph` 가 따로 잡는다.
    """
    nodes = {str(n.get("id")): n for n in g.get("nodes", [])}
    depth = {}

    def d(nid, seen=()):
        if nid in depth:
            return depth[nid]
        if nid in seen or nid not in nodes:
            return 0
        deps = [str(x) for x in (nodes[nid].get("deps") or []) if str(x) in nodes]
        depth[nid] = 1 + max((d(x, seen + (nid,)) for x in deps), default=0)
        return depth[nid]

    for nid in nodes:
        d(nid)
    levels = [[nid for nid in nodes if depth.get(nid) == k] for k in range(1, max(depth.values(), default=0) + 1)]
    notes = []
    n = len(nodes)
    widest = max((len(lv) for lv in levels), default=0)
    if n >= 4 and widest <= 1:
        notes.append(f"일렬입니다(노드 {n}개가 {len(levels)}단계로 하나씩). 서로의 결과를 읽지 않는 노드는 deps 를 빼고, "
                     "인터페이스(파일·함수 이름과 꼴)를 브리프에 먼저 못박아 만들기·화면·검사를 같은 단계에 두십시오")
    for k, lv in enumerate(levels, 1):
        by_slot = {}
        for nid in lv:
            by_slot.setdefault(str(nodes[nid].get("slot")), []).append(nid)
        crowded = {s: ids for s, ids in by_slot.items() if len(ids) > 1}
        if crowded and len(by_slot) < len(lv):
            desc = ", ".join(f"{s} {len(ids)}개" for s, ids in crowded.items())
            notes.append(f"{k}단계의 노드가 한 슬롯에 몰렸습니다({desc}) - 슬롯은 한 번에 하나라 줄을 섭니다. "
                         "다른 슬롯(다른 공급자면 더 좋음)에 나누면 동시에 돕니다")
    return {"nodes": n, "levels": levels, "notes": notes}


def shape_line(g):
    sh = graph_shape(g)
    return (f"모양: 노드 {sh['nodes']}개 · {len(sh['levels'])}단계 · 단계별 "
            + " / ".join(str(len(lv)) for lv in sh["levels"])), sh["notes"]


def cmd_new(a):
    nodes = json.loads(pathlib.Path(a.nodes).read_text(encoding="utf-8"))
    for n in nodes:
        n.setdefault("status", "todo")
        n.setdefault("attempts", [])
        n.setdefault("deps", [])
        n.setdefault("max_attempts", 2)
    if not re.fullmatch(r"G-\d{3}", a.id):
        print(f"경고: 그래프 id 는 G-001 형식을 권장합니다 (받은 값 {a.id!r}). 라운드 R<n> 과 헷갈리지 않게.", file=sys.stderr)
    bad_ids = [n["id"] for n in nodes if not re.fullmatch(r"T-\d+[A-Z]?", str(n.get("id", "")))]
    if bad_ids:
        print(f"경고: 노드 id 는 보드 태스크 id(T-0xx) 를 그대로 쓰십시오: {bad_ids}", file=sys.stderr)
    conc = a.concurrency if getattr(a, "concurrency", None) else default_concurrency(nodes)
    g = {"id": a.id, "request": a.request, "created": _now(), "rev": fleet.read_rev(),
         "round": fleet.current_round(),      # 식별자에 붙이지 않고 따로 적는다 (화면 구분용)
         "concurrency": conc, "nodes": nodes}
    followup = (getattr(a, "followup", None) or "").strip()
    if followup:
        g["followup"] = followup[:300]
    over = round_budget_problem(g["round"], [n.get("id") for n in nodes], followup, exclude=a.id)
    if over:
        print("그래프를 만들지 않았습니다: " + over, file=sys.stderr)
        return 2
    probs = validate_graph(g)
    if probs:
        print("그래프를 만들지 않았습니다:", file=sys.stderr)
        for p in probs:
            print("  -", p, file=sys.stderr)
        return 2
    _save(g)
    _log(g, f"created {len(nodes)} nodes, request={a.request!r}")
    print(GRAPHS / f"{a.id}.json")
    line, notes = shape_line(g)
    print(line)
    for x in notes:
        print("  참고: " + x)
    return 0


def cmd_validate(a):
    probs = validate_graph(_load(a.id))
    if probs:
        for p in probs:
            print("-", p)
        return 2
    print("통과: DAG 이고 슬롯·소유권이 맞습니다")
    return 0


def _validate_or_report(g):
    """스케줄 시작 전 모양 검증 한 번 (큐 8번 B-1).

    `step()` 은 `validate_graph` 를 다시 돌리지 않아, 손으로 고친 그래프의 오타(없는 dep,
    명부 밖 슬롯, 소유가 아닌 쓰기 경로)가 스폰 단계에서야 드러났습니다. 문제가 있으면
    한 줄씩 찍고 False - 호출자는 스폰 없이 rc 2 로 끝냅니다.
    """
    probs = validate_graph(g, spawnable_only=True)
    if probs:
        print(f"그래프 {g.get('id')} 검증 실패 - 스폰하지 않았습니다:", file=sys.stderr)
        for p in probs:
            print("  -", p, file=sys.stderr)
        return False
    return True


def cmd_step(a):
    # 잠금은 load 보다 **먼저** - 잠금 밖에서 읽은 그래프는 남의 틱이 덮어쓸 수 있습니다.
    with graph_lock(a.id, "step"):
        g = _load(a.id)
        if not _validate_or_report(g):
            return 2
        finished = step(g, a.concurrency)
        print(json.dumps({"finished": finished, **progress(g), "nodes": {n["id"]: n.get("status") for n in g["nodes"]}},
                         ensure_ascii=False, indent=1))
        return 0 if finished else 1


#: 사람이 돌고 있는 라운드의 관리자에게 남기는 말 (`fleet_ctl.py tell`). 그래프 실행기는 이 파일이 바뀌면 rc 4 로 돌아와
#: 관리자가 읽게 한다 - 관리자는 `run` 에 블로킹해 있어 다른 길로는 도중에 말을 들을 수 없다.
INBOX_NAME = "INBOX.md"
RC_INBOX = 4


def inbox_path(round_n):
    try:
        return pathlib.Path(fleet.ROOT) / "rounds" / f"R{int(round_n)}" / INBOX_NAME
    except (TypeError, ValueError):
        return None


def _mtime(p):
    try:
        return p.stat().st_mtime if p is not None else None
    except OSError:
        return None


def cmd_run(a):
    with graph_lock(a.id, "run"):
        g = _load(a.id)
        if not _validate_or_report(g):
            return 2
        deadline = time.time() + a.timeout
        halted = inbox = False
        box = inbox_path(g.get("round"))
        box0 = _mtime(box)
        stop_on_block = getattr(a, "stop_on_block", None)
        if stop_on_block is None:
            # 빨리·잘 하려는 라운드는 막힌 노드를 관리자가 곧바로 옮기거나 풀어야 한다 - 무료 중심은 끝까지 돌린다
            stop_on_block = round_policy(g.get("round")) in ("speed", "quality")
        bad0 = {n["id"] for n in g["nodes"] if n.get("status") in ("failed", "blocked")}
        spawn, blocked_new = True, []
        while time.time() < deadline:
            # 띄우기를 멈춘 뒤에도 '완전 중지' 면 함대 모드에 맡긴다 - 떠 있는 작업자를 거두는 일(`halt_running`)이 거기 있다
            if step(g, a.concurrency, allow_spawn=None if spawn or _fleet_mode() == "stopped" else False,
                    hold_on_block=stop_on_block):
                break
            if _fleet_mode() == "stopped":
                halted = True
                break
            if _mtime(box) != box0:
                inbox = True
                break
            if stop_on_block and spawn:
                blocked_new = [n["id"] for n in g["nodes"] if n.get("status") in ("failed", "blocked") and n["id"] not in bad0]
                if blocked_new:
                    spawn = False        # 새 노드는 띄우지 않고 떠 있는 것만 거둔다
            if not spawn and not any(n.get("status") == "running" for n in g["nodes"]):
                break
            time.sleep(a.poll)
        g = _load(a.id)
        p = progress(g)
        m = _fleet_mode()
        if m != "running":
            # 관리자에게: 사람이 멈췄다. 체크포인트(보드·event·큐)를 남기고 PARTIAL 로 보고하라 (AIMEM 8.0)
            print(f"함대 모드: {m} - 사람이 {'완전 중지' if m == 'stopped' else '일시 중지/준비'} 했습니다. "
                  f"새 노드를 띄우지 않았습니다. 체크포인트를 남기고 PARTIAL 로 보고하십시오")
        print(f"{g['id']}: {p['percent']}%  남은 ETA {p['eta_seconds']}s  상태 {p['counts']}")
        for n in g["nodes"]:
            last = n["attempts"][-1] if n.get("attempts") else {}
            print(f"  {n['id']:<6} {n.get('status','todo'):<8} {n['slot']:<3} 시도 {len(n.get('attempts',[]))}  "
                  f"run {last.get('run_id','-')}  rc {last.get('rc','-')}/{last.get('verify_rc','-')}  {n.get('title','')}")
        if halted:
            return 3
        if inbox:
            # 떠 있는 작업자는 그대로 둔다 - 다시 `run` 하면 거둔다
            print(f"사람이 말을 남겼습니다: {box.relative_to(fleet.ROOT) if box else INBOX_NAME} - 읽고 판단한 뒤 "
                  f"`fleet_graph.py run {g['id']}` 로 이어 가십시오 (rc {RC_INBOX})")
            return RC_INBOX
        if not spawn:
            gone = [n for n in g["nodes"] if n["id"] in blocked_new]
            names = ", ".join(f"{n['id']}({n.get('status')}, {n.get('slot')})" for n in gone)
            print(f"막힌 노드: {names} - 새 노드는 띄우지 않고 "
                  f"멈췄습니다. `fleet_graph.py move {g['id']} <노드> --slot S<n>` 으로 다른 슬롯에 옮기거나 "
                  f"`unblock` 한 뒤 `fleet_graph.py run {g['id']}` 로 이어 가십시오")
            return 1
        return 0 if all(n.get("status") == "done" for n in g["nodes"]) else 1


def unblock(g, node_id):
    """사람이 확인한 뒤 `blocked`/`failed` 노드를 다시 굴립니다. (ok, 메시지)

    - 마지막 시도의 작업자가 **아직 살아 있으면 거절**합니다 - 옆에 두 번째 작업자를 띄우지 않습니다.
    - 죽이지 못해(`refused`) 막혔던 시도가 그 뒤 스스로 끝났으면 노드를 `running` 으로 돌려
      다음 틱이 그 결과를 **거두게** 합니다(보고·검증). 새로 띄우지 않습니다.
    - 그 밖에는 `todo` 로 돌립니다. 시도 한도를 다 썼으면 한 번 더 허용합니다.
    - 이 노드 때문에 '의존 실패' 로 막힌 뒤쪽 노드(시도 기록 없음)는 `todo` 로 풉니다.
    """
    nodes = {n["id"]: n for n in g["nodes"]}
    n = nodes.get(node_id)
    if n is None:
        return False, f"노드가 없습니다: {node_id}"
    if n.get("status") not in ("blocked", "failed"):
        return False, f"{node_id} 는 {n.get('status', 'todo')} 입니다 - blocked/failed 만 풉니다"
    atts = n.get("attempts") or []
    if not atts and not n.get("infra"):
        return False, f"{node_id} 는 의존 노드 때문에 막혔습니다 - 막힌 원인 노드를 푸십시오"
    last = atts[-1] if atts else (n.get("infra_attempts") or [{}])[-1]
    state, _ = fleet._run_state(last["run_id"]) if last.get("run_id") else ("done", None)
    if state == "running":
        return False, f"{node_id} 의 작업자가 아직 살아 있습니다 (run {last['run_id']}) - 끝나거나 사람이 내린 뒤에"
    if n.get("infra"):
        # 기반 장애로 막힌 노드: 사람이 공급자를 확인했다. 장애 횟수를 비우고(기록은 남김) 다시 넣는다.
        # 시도 횟수는 그대로다 - 기반 장애는 처음부터 시도로 세지 않았다.
        for a in n.get("infra_attempts") or []:
            if isinstance(a, dict):
                a["cleared"] = True
        n.pop("infra", None)
        n["status"] = "todo"
        how = "기반 장애 횟수를 비우고 다음 틱에 다시 띄웁니다(공급자 점검 뒤)"
    elif last.get("kill_outcome") == "refused" and "ended" not in last and state == "done":
        n["status"] = "running"
        how = f"끝난 실행 {last['run_id']} 을 다음 틱이 거둡니다"
    else:
        if len(atts) >= int(n.get("max_attempts", 2)):
            n["max_attempts"] = len(atts) + 1
        n["status"] = "todo"
        how = f"다음 틱에 {len(atts) + 1}번째 시도를 띄웁니다"
    freed, changed = [], True
    while changed:
        changed = False
        for m in g["nodes"]:
            if m.get("status") != "blocked" or m.get("attempts"):
                continue
            deps = [nodes[d] for d in m.get("deps", []) if d in nodes]
            if deps and not any(d.get("status") in ("failed", "blocked") for d in deps):
                m["status"] = "todo"
                freed.append(m["id"])
                changed = True
    _log(g, f"unblock {node_id} - {how}" + (f"; 뒤쪽 {', '.join(freed)} 도 todo" if freed else ""))
    return True, f"{node_id}: {how}" + (f" / 함께 푼 노드: {', '.join(freed)}" if freed else "")


def reverify(g, node_id):
    """작업자를 다시 띄우지 않고 **검증만 다시** 돌립니다. (ok, 메시지)

    `verify` 가 틀려 실패한 노드(작업은 끝났는데 검사 쪽 결함 - 출력 꼴을 잘못 읽음 등)를 관리자가 verify 를 고친 뒤
    쓰는 길입니다. 예전에는 `unblock` 으로 작업자를 또 띄워 이미 끝난 일을 다시 시켰습니다 (R24 T-281, 2026-11-13).
    마지막 시도가 rc 0 으로 끝난 `failed`/`blocked` 노드만 받습니다. 통과하면 `done`, 아니면 그대로 두고 출력 꼬리를 줍니다.
    """
    nodes = {n["id"]: n for n in g["nodes"]}
    n = nodes.get(node_id)
    if n is None:
        return False, f"노드가 없습니다: {node_id}"
    if n.get("status") not in ("blocked", "failed"):
        return False, f"{node_id} 는 {n.get('status', 'todo')} 입니다 - blocked/failed 만 다시 검증합니다"
    last = (n.get("attempts") or [None])[-1]
    if not last or last.get("rc") != 0:
        return False, f"{node_id} 의 마지막 시도가 rc 0 으로 끝나지 않았습니다 - 작업을 다시 해야 하면 unblock 을 쓰십시오"
    if not n.get("verify"):
        return False, f"{node_id} 에 verify 가 없습니다"
    vrc, vtail = _verify(n)
    last["reverify"] = {"at": _now(), "verify_rc": vrc, "verify_tail": (vtail or "")[-600:]}
    if vrc != 0:
        _log(g, f"reverify {node_id} - 여전히 실패 (verify rc {vrc})")
        return False, f"{node_id}: 다시 검증했지만 실패 (rc {vrc})\n{(vtail or '')[-600:]}"
    last["verify_rc"], last["verify_tail"], last["fail_kind"] = 0, vtail, None
    n["status"] = "done"
    freed = []
    for m in g["nodes"]:
        if m.get("status") == "blocked" and not m.get("attempts"):
            deps = [nodes[d] for d in m.get("deps", []) if d in nodes]
            if deps and not any(d.get("status") in ("failed", "blocked") for d in deps):
                m["status"] = "todo"
                freed.append(m["id"])
    _log(g, f"reverify {node_id} - 통과, done (작업자는 다시 띄우지 않음)" + (f"; 뒤쪽 {', '.join(freed)} 도 todo" if freed else ""))
    return True, f"{node_id}: 다시 검증 통과 - done" + (f" / 함께 푼 노드: {', '.join(freed)}" if freed else "")


def round_policy(rnd):
    """라운드 R<rnd> 의 운영 방식 키 (`rounds/R<N>/round.json` 의 `policy`). 모르면 `cost` - 가장 좁은 쪽."""
    try:
        from fleet_rt import config as rt_config  # noqa: PLC0415
        rec = json.loads((pathlib.Path(fleet.ROOT) / "rounds" / f"R{int(rnd)}" / "round.json").read_text(encoding="utf-8"))
        v = rec.get("policy") if isinstance(rec, dict) else None
        return v if v in rt_config.POLICIES else "cost"
    except (OSError, ValueError, TypeError):
        return "cost"


def _move_ownership(paths, slot, why):
    """노드의 쓰기 경로 소유를 새 슬롯으로 (`aimem_db.ownership_set`, events 한 줄씩). DB 가 없으면 아무것도 안 한다
    (보드 동기화와 같이 `fleet.RUNS` 옆의 DB - 임시 폴더 검사가 운영 DB 를 고치지 않게). 옮긴 경로 목록."""
    db = _board_db()
    if not db.is_file() or not paths:
        return []
    import aimem_db  # noqa: PLC0415
    done = []
    for w in paths:
        aimem_db.ownership_set(str(w), slot, note=why[:200], actor="관리자(move)", db=db)
        done.append(str(w))
    fleet._DB_CACHE["at"] = 0.0          # 바로 뒤 `run` 이 옛 소유를 캐시에서 읽지 않게
    return done


def move_node(g, node_id, slot, policy=None, why=""):
    """노드를 다른 슬롯으로 옮긴다 - 관리자가 막힌 노드를 다른 엔진에 넘기는 길. (ok, 메시지)

    - todo / failed / blocked 이고 마지막 작업자가 살아 있지 않은 노드만
    - 새 슬롯은 명부에 있어야 하고, 운영 방식(`policy`, 없으면 그 라운드의 것)이 허용하는 등급(`slot_tiers`)이어야 한다
    - 쓰기 경로의 소유를 새 슬롯으로 옮기고(events), 노드를 `todo` 로. 시도 한도를 다 썼으면 한 번 더 허용하고
      (`unblock` 과 같다), 이 노드 때문에 막힌 뒤쪽 노드도 푼다. `moves` 에 기록을 남긴다.
    """
    nodes = {n["id"]: n for n in g["nodes"]}
    n = nodes.get(node_id)
    if n is None:
        return False, f"노드가 없습니다: {node_id}"
    st = n.get("status", "todo")
    if st not in ("todo", "failed", "blocked"):
        return False, f"{node_id} 는 {st} 입니다 - todo/failed/blocked 만 옮깁니다"
    old = n.get("slot")
    if slot == old:
        return False, f"{node_id} 는 이미 {slot} 에 있습니다"
    roster = fleet.roster()
    if slot not in roster:
        return False, f"{slot} 이 명부에 없습니다 (`aimem_db.py slot list`)"
    last = ((n.get("attempts") or []) + (n.get("infra_attempts") or []) or [{}])[-1]
    if isinstance(last, dict) and last.get("run_id") and fleet._run_state(last["run_id"])[0] == "running":
        return False, f"{node_id} 의 작업자가 아직 살아 있습니다 (run {last['run_id']}) - 끝나거나 사람이 내린 뒤에"
    key = policy or round_policy(g.get("round"))
    try:
        from fleet_rt import config as rt_config  # noqa: PLC0415
        cfg = rt_config.load(fleet.ROOT)
        h, m = fleet.spawn_harness_model(slot, n.get("harness"), n.get("model"))
        tier = cfg.slot_tier(h, m)
        allowed = cfg.policy(key)["slot_tiers"]
    except Exception as e:  # noqa: BLE001 - 등급을 모르면 옮기지 않는다 (돈이 드는 쪽을 막는다)
        return False, f"fleet.toml 을 읽지 못해 {slot} 의 등급을 확인할 수 없습니다: {e}"
    if tier not in allowed:
        return False, (f"운영 방식 {key} 에서는 {'·'.join(rt_config.TIER_LABEL[x] for x in allowed) or '(없음)'} 슬롯으로만 옮깁니다 - "
                       f"{slot}({h} {m or '하네스 기본'}) 는 {rt_config.TIER_LABEL.get(tier, tier)}입니다")
    moved = _move_ownership(list(n.get("write") or []), slot, f"{g.get('id')} {node_id} {old}→{slot}")
    n["slot"] = slot
    n.setdefault("moves", []).append({"from": old, "to": slot, "at": _now(), "why": str(why or "")[:300]})
    if len(n.get("attempts") or []) >= int(n.get("max_attempts", 2)):
        n["max_attempts"] = len(n["attempts"]) + 1
    for a in n.get("infra_attempts") or []:
        if isinstance(a, dict):
            a["cleared"] = True              # 다른 공급자로 간다 - 옛 공급자의 장애 횟수는 이 노드를 막지 않는다
    n.pop("infra", None)
    n.pop("waiting", None)
    n.pop("waiting_since", None)
    n["status"] = "todo"
    freed, changed = [], True
    while changed:
        changed = False
        for m_ in g["nodes"]:
            if m_.get("status") != "blocked" or m_.get("attempts"):
                continue
            deps = [nodes[d] for d in m_.get("deps", []) if d in nodes]
            if deps and not any(d.get("status") in ("failed", "blocked") for d in deps):
                m_["status"] = "todo"
                freed.append(m_["id"])
                changed = True
    _log(g, f"move {node_id} {old} -> {slot} (운영 {key})" + (f"; 소유 {len(moved)}건 옮김" if moved else "")
         + (f"; 뒤쪽 {', '.join(freed)} 도 todo" if freed else "") + (f" - {why}" if why else ""))
    return True, (f"{node_id}: {old} → {slot}, 다음 틱에 띄웁니다" + (f" / 소유를 옮긴 경로 {len(moved)}개" if moved else "")
                  + (f" / 함께 푼 노드: {', '.join(freed)}" if freed else ""))


def cmd_move(a):
    # 실행기와 같은 잠금을 잡는다 - `run` 이 도는 동안 옮기면 실행기가 옛 그래프로 덮어쓴다
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(graph_lock(a.id, "move"))
        except SystemExit:
            print(f"`run` 이 그래프 {a.id} 를 잡고 있어 옮기지 않았습니다 - `run` 이 돌아온 뒤 다시 move 하십시오 "
                  f"(`run --stop-on-block` 은 노드가 막히면 돌아옵니다)", file=sys.stderr)
            return 2
        g = _load(a.id)
        ok, msg = move_node(g, a.node, a.slot, why=a.why or "")
        if ok:
            _save(g)
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


def cmd_unblock(a):
    with graph_lock(a.id, "unblock"):
        g = _load(a.id)
        ok, msg = (reverify if getattr(a, "reverify", False) else unblock)(g, a.node)
        if ok:
            _save(g)
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


def _status_node(n):
    node = {"id": n["id"], "title": n.get("title"), "slot": n["slot"],
            "harness": n.get("harness") or fleet.roster().get(n["slot"], ("", "", ""))[1],
            "status": n.get("status", "todo"), "deps": n.get("deps", []),
            "attempts": len(n.get("attempts", [])),
            "last_run": (n["attempts"][-1].get("run_id") if n.get("attempts") else None)}
    if n.get("limit"):
        node["limit"] = True
        node["note"] = "(사용 한도)"
    if n.get("attempts"):
        node["fail_kind"] = n["attempts"][-1].get("fail_kind")
    if n.get("infra_attempts"):
        node["infra_attempts"] = len(n["infra_attempts"])
    if n.get("infra"):
        node["infra"] = True
        node["note"] = "(공급자 장애)"
    if n.get("waiting"):
        node["waiting"] = n["waiting"]
    return node


def cmd_status(a):
    g = _load(a.id)
    out = {"id": g["id"], "request": g.get("request"), "created": g.get("created"), "updated": g.get("updated"),
           **progress(g),
           "nodes": [_status_node(n) for n in g["nodes"]]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_list(a):
    if not GRAPHS.exists():
        print("그래프 없음")
        return 0
    for f in sorted(GRAPHS.glob("*.json")):
        g = json.loads(f.read_text(encoding="utf-8"))
        p = progress(g)
        print(f"{g['id']:<10} {p['percent']:5.1f}%  ETA {p['eta_seconds']:>6}s  {p['counts']}  {g.get('request','')[:50]}")
    return 0


def main():
    p = argparse.ArgumentParser(description="태스크 그래프 실행기 (관리자 전용)")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--id", required=True)
    n.add_argument("--request", required=True)
    n.add_argument("--nodes", required=True, help="노드 배열 JSON 파일")
    n.add_argument("--concurrency", type=int, default=None,
                   help="한 번에 띄울 노드 수 (기본: 그래프가 쓰는 서로 다른 슬롯 수). 슬롯 하나에 하나·공급자 자리는 따로 지킨다")
    n.add_argument("--followup", help="라운드 상한(그래프 3·태스크 10)을 넘는 그래프가 검수 결함의 수정·재검수일 때, 무엇의 후속인지")
    for name in ("validate", "status"):
        sub.add_parser(name).add_argument("id")
    s = sub.add_parser("step")
    s.add_argument("id")
    s.add_argument("--concurrency", type=int)
    r = sub.add_parser("run")
    r.add_argument("id")
    r.add_argument("--timeout", type=int, default=3600)
    r.add_argument("--poll", type=float, default=DEFAULT_POLL_SEC)
    r.add_argument("--concurrency", type=int)
    r.add_argument("--stop-on-block", dest="stop_on_block", action=argparse.BooleanOptionalAction, default=None,
                   help="노드가 새로 failed/blocked 되면 새 노드를 띄우지 않고 떠 있는 것만 거둔 뒤 rc 1 로 돌아온다 "
                        "(관리자가 move/unblock 하고 다시 run). 기본: 라운드 운영 방식이 speed·quality 면 켜짐, cost 면 꺼짐")
    sub.add_parser("list")
    mv = sub.add_parser("move", help="todo/failed/blocked 노드를 다른 슬롯으로 옮긴다 (쓰기 경로 소유도 함께)")
    mv.add_argument("id")
    mv.add_argument("node")
    mv.add_argument("--slot", required=True, help="옮겨 갈 슬롯 (명부에 있어야 하고, 운영 방식이 허용하는 등급이어야 함)")
    mv.add_argument("--why", default="", help="옮기는 까닭 한 줄 (노드의 moves 기록에 남는다)")
    u = sub.add_parser("unblock", help="사람이 확인한 blocked/failed 노드를 다시 굴림")
    u.add_argument("id")
    u.add_argument("node")
    u.add_argument("--reverify", action="store_true",
                   help="작업자를 다시 띄우지 않고 검증만 다시 (verify 를 고쳤을 때). 통과하면 done")
    a = p.parse_args()
    return {"new": cmd_new, "validate": cmd_validate, "step": cmd_step, "run": cmd_run,
            "status": cmd_status, "list": cmd_list, "unblock": cmd_unblock, "move": cmd_move}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
