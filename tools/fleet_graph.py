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

노드 형식 (nodes.json 배열):
  {"id":"T1","title":"서버 골격","slot":"S1","write":["tools/aimem_monitor/server.py"],
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
import statistics
import subprocess
import threading
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fleet  # noqa: E402

ROOT = fleet.ROOT
GRAPHS = ROOT / ".aimem" / "graph"
TERMINAL = ("done", "failed", "blocked")
DEFAULT_NODE_TIMEOUT_SEC = 1800
KILL_GRACE_SEC = 5


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
        meta = fleet._run_meta(rid) or {}
        state, rc = fleet._run_state(rid)
        rcf = fleet.RUNS / f"{rid}.rc"
        if state != "done" or not meta.get("started") or not rcf.exists():
            continue
        started = _parse_started(meta["started"])
        if started is None:
            continue
        ended = dt.datetime.fromtimestamp(rcf.stat().st_mtime)
        out.setdefault(meta.get("harness", "?"), []).append(max(1.0, (ended - started).total_seconds()))
    return out


def estimate_seconds(node, durations, roster):
    h = node.get("harness") or roster.get(node["slot"], ("", "", ""))[1]
    xs = durations.get(h) or [v for vs in durations.values() for v in vs]
    base = statistics.median(xs) if xs else 120.0
    # 쓰기가 있는 태스크는 읽기 프로브보다 길다 - 쓰기 경로 수만큼 가중
    return base * (1.0 + 0.5 * len(node.get("write", [])))


def progress(g):
    """진행율(%)·ETA(초)·임계 경로. 웹 UI 가 그대로 쓰는 구조."""
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
    conc = max(1, int(g.get("concurrency", 3)))
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
    busy = set()
    for rid in fleet._list_runs():
        try:
            state, _ = fleet._run_state(rid)
        except Exception:  # noqa: BLE001 - 기록 하나가 깨져도 스케줄러는 돌아야 한다
            continue
        if state != "running":
            continue
        meta = fleet._run_meta(rid) or {}
        if meta.get("slot"):
            busy.add(meta["slot"])
    return busy


def _spawn_node(g, n, attempt_no):
    prior = ""
    if attempt_no > 1:
        last = n["attempts"][-1]
        prior = (f"\n\n[재시도 {attempt_no}/{n.get('max_attempts', 2)}] 직전 시도(run {last['run_id']}) 는 "
                 f"rc={last.get('rc')} / 검증 rc={last.get('verify_rc')} 로 실패했다. 산출물이 남아 있을 수 있으니 "
                 f"먼저 확인하고 이어서 하라. 직전 검증 출력 꼬리:\n{(last.get('verify_tail') or '')[-600:]}")
    task_file = GRAPHS / f"{g['id']}-{n['id']}-a{attempt_no}.task.md"
    GRAPHS.mkdir(parents=True, exist_ok=True)
    task_file.write_text(n["task"].rstrip() + prior + "\n", encoding="utf-8")
    # 식별자 체계(18:15): 노드 id 가 T-0xx 면 그것이 태스크 id 다. 실행 id = T-050-S1-a2-HHMMSS (fleet.py 가 만든다)
    tid = n["id"] if re.fullmatch(r"T-\d+[A-Z]?", str(n["id"])) else None
    ns = argparse.Namespace(slot=n["slot"], harness=n.get("harness"), model=n.get("model"),
                            task_id=tid, attempt=attempt_no,
                            label=f"{n.get('title','')} ({g['id']})".strip(),
                            write=list(n.get("write", [])), task=None, task_file=str(task_file))
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fleet.cmd_spawn(ns)
    run_id = buf.getvalue().strip().splitlines()[-1]
    n.setdefault("attempts", []).append({"run_id": run_id, "started": _now()})
    n["status"] = "running"
    _log(g, f"spawn {n['id']} attempt {attempt_no} -> {run_id} ({n['slot']})")
    return run_id


def _verify(n):
    cmd = n.get("verify")
    if not cmd:
        return 0, "(검증 명령 없음 - rc 만 봄)"
    try:
        r = subprocess.run(["bash", "-lc", cmd], cwd=ROOT, capture_output=True, text=True, timeout=600)
        return r.returncode, (r.stdout + r.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return 124, "검증 타임아웃(600s)"


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
        att.update({"timeout": True, "kill_outcome": "refused", "kill_reason": reason,
                    "timeout_at": _now(), "timeout_elapsed_s": int(elapsed)})
        n["status"] = "blocked"
        _log(g, f"timeout {n['id']} - 죽이지 못했습니다 (pid {pid if pid is not None else '?'}, {reason}). "
                f"사람이 확인해야 합니다")
        return True
    _mark_lost(att["run_id"])
    att["kill_outcome"] = outcome
    att.update({"ended": _now(), "rc": 124, "state": "timeout", "timeout": True})
    if outcome == "foreign":
        _log(g, f"timeout {n['id']} - pid {pid} 가 그 실행의 것이 아닙니다 (죽이지 않음)")
    _log(g, f"timeout {n['id']} after {int(elapsed)}s (run {att['run_id']}, pid {pid if pid is not None else '?'}, {outcome})")
    _retry_or_fail(g, n, "rc=124 (timeout)")
    return True


def step(g, concurrency=None):
    """한 틱: 끝난 실행을 거두어 검증하고, 실패면 재시도(한정), 준비된 노드를 띄웁니다.

    `validate_graph` 는 여기서 돌리지 않습니다 - 수십 분 도는 루프의 매 틱마다 명부·소유권을
    다시 읽게 됩니다. `cmd_run`/`cmd_step` 이 시작 전에 한 번 돌립니다.
    """
    conc = concurrency or int(g.get("concurrency", 3))
    changed = False
    # 1) 거두기 (+ 노드별 타임아웃, + 보고 첫 줄 BLOCKED 판정)
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
        if state == "running":
            if _check_timeout(g, n, att):
                changed = True
            continue
        att["ended"], att["rc"], att["state"] = _now(), rc, state
        att["report"] = fleet.run_report(att["run_id"])[:4000]
        block = report_block_reason(att["report"]) if rc == 0 else None
        if block:
            # 사람이 풀어야 할 일 - 재시도해도 같은 벽에 부딪히므로 바로 blocked (AIMEM 8.0-4-3).
            att["report_status"] = block
            att["verify_rc"], att["verify_tail"] = None, f"검증 생략: 보고 상태 {block}"
            n["status"] = "blocked"
            first = next((l.strip() for l in att["report"].splitlines() if l.strip()), "")
            _log(g, f"BLOCKED {n['id']} - {first[:60]}")
            changed = True
            continue
        vrc, vtail = (_verify(n) if rc == 0 else (-1, "실행 rc != 0"))
        att["verify_rc"], att["verify_tail"] = vrc, vtail
        if rc == 0 and vrc == 0:
            n["status"] = "done"
            _log(g, f"done {n['id']} ({att['run_id']})")
        else:
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
    # 3) 띄우기 (fan-out, 동시성 상한, **슬롯 바쁨 검사**)
    running = sum(1 for n in g["nodes"] if n.get("status") == "running")
    busy = _busy_slots(g)
    for n in _ready(g):
        if running >= conc:
            break
        slot = n.get("slot")
        if slot in busy:
            _log(g, f"skip {n['id']} - 슬롯 {slot} 이(가) 이미 바쁩니다")
            continue
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
        changed = True
        _save(g)
    if changed:
        _save(g)
    return all(n.get("status") in TERMINAL for n in g["nodes"])


# ---------------------------------------------------------------- CLI
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
    g = {"id": a.id, "request": a.request, "created": _now(), "rev": fleet.read_rev(),
         "concurrency": a.concurrency, "nodes": nodes}
    probs = validate_graph(g)
    if probs:
        print("그래프를 만들지 않았습니다:", file=sys.stderr)
        for p in probs:
            print("  -", p, file=sys.stderr)
        return 2
    _save(g)
    _log(g, f"created {len(nodes)} nodes, request={a.request!r}")
    print(GRAPHS / f"{a.id}.json")
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


def cmd_run(a):
    with graph_lock(a.id, "run"):
        g = _load(a.id)
        if not _validate_or_report(g):
            return 2
        deadline = time.time() + a.timeout
        while time.time() < deadline:
            if step(g, a.concurrency):
                break
            time.sleep(a.poll)
        g = _load(a.id)
        p = progress(g)
        print(f"{g['id']}: {p['percent']}%  남은 ETA {p['eta_seconds']}s  상태 {p['counts']}")
        for n in g["nodes"]:
            last = n["attempts"][-1] if n.get("attempts") else {}
            print(f"  {n['id']:<6} {n.get('status','todo'):<8} {n['slot']:<3} 시도 {len(n.get('attempts',[]))}  "
                  f"run {last.get('run_id','-')}  rc {last.get('rc','-')}/{last.get('verify_rc','-')}  {n.get('title','')}")
        return 0 if all(n.get("status") == "done" for n in g["nodes"]) else 1


def cmd_status(a):
    g = _load(a.id)
    out = {"id": g["id"], "request": g.get("request"), "created": g.get("created"), "updated": g.get("updated"),
           **progress(g),
           "nodes": [{"id": n["id"], "title": n.get("title"), "slot": n["slot"],
                      "harness": n.get("harness") or fleet.roster().get(n["slot"], ("", "", ""))[1],
                      "status": n.get("status", "todo"), "deps": n.get("deps", []),
                      "attempts": len(n.get("attempts", [])),
                      "last_run": (n["attempts"][-1].get("run_id") if n.get("attempts") else None)}
                     for n in g["nodes"]]}
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
    n.add_argument("--concurrency", type=int, default=3)
    for name in ("validate", "status"):
        sub.add_parser(name).add_argument("id")
    s = sub.add_parser("step")
    s.add_argument("id")
    s.add_argument("--concurrency", type=int)
    r = sub.add_parser("run")
    r.add_argument("id")
    r.add_argument("--timeout", type=int, default=3600)
    r.add_argument("--poll", type=int, default=10)
    r.add_argument("--concurrency", type=int)
    sub.add_parser("list")
    a = p.parse_args()
    return {"new": cmd_new, "validate": cmd_validate, "step": cmd_step, "run": cmd_run,
            "status": cmd_status, "list": cmd_list}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
