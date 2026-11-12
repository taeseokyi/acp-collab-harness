"""세션 띄우기·상태·끊기·고아 청소 (설계 `docs/FLEET-ENGINE-V2.md` 3.2).

상주 데몬은 없다. 세션마다 감독 프로세스(`run.py`) 하나가 뜨고, 그 프로세스가 **세션·그룹 리더**다.
하네스는 감독의 자식으로 **같은 그룹**에 뜨므로 `killpg` 한 번이 감독+하네스+하네스 자식을 끝낸다.

띄우는 길 (이중 fork):

    spawn ──Popen──> run.py --detach (중간 프로세스)
                       └─fork─> 자식: setsid → pid 한 줄을 stdout 에 → exec `python3 -m fleet_rt.run <폴더>`
                     중간 프로세스는 바로 끝나고 spawn 이 거둔다.

감독이 부른 쪽의 자식이 아니게 하는 까닭: 오래 사는 호출자(그래프 실행기·모니터)가 끝난 감독을 거두지 않으면
좀비가 쌓이고, 좀비는 `os.kill(pid, 0)` 에 '살아 있음' 으로 보인다(지금 `_run_state` 의 결함). 감독의
부모는 init 이 되어 바로 거두어진다.

meta.json 과의 경합: spawn 은 meta.json 을 pid 칸이 빈 채(null) 먼저 쓰고, 감독을 띄우고, pid·pgid·시작 시각을
채워 **다시** 쓴다(둘 다 tmp + os.replace). 감독은 meta.json 의 `supervisor_pid` 가 자기 pid 가 될 때까지
기다린 뒤에야 하네스를 띄운다(`run.META_WAIT_SEC` 안에 안 되면 하네스 없이 failed/infra 로 끝). 그래서
**신원(pid·시작 시각)이 기록되기 전에 하네스가 도는 순간이 없다** - cancel·고아 청소가 늘 알아볼 수 있다.

end.json 은 '없을 때만 만든다'(tmp 를 쓰고 `os.link`, 이미 있으면 실패) - 감독과 cancel 이 둘 다 쓰려 해도
처음 것 하나만 남는다. 예외 둘: 감독이 마감할 때 이미 end.json 이 있으면(작업자가 미리 써 둔 것) 감독 것으로
덮고, cancel 이 end.json 이 있는데도 살아 있던 프로세스를 끊었으면 killed 로 덮는다.

**프로세스 신원** (2026-11-12 적대 검수 뒤): 어떤 프로세스가 세션 폴더 `<root>/<id>` 의 것이라는 판단은
그 프로세스의 **환경 표식** `AIFLEET_SESSIONS_ROOT == <root>` 그리고 `AIFLEET_SESSION == <id>` 로만 한다.
둘 다 **폴더 경로에서** 뽑는다 - meta.json 은 작업자가 고쳐 쓸 수 있고 폴더째 복사될 수도 있어서다
(복사본에 cancel 을 걸면 원본 세션을 죽이던 결함). 명령줄 대조는 쓰지 않는다(`tail -f <폴더>/events.jsonl`
같은 남의 프로세스가 통과했다). 감독은 spawn 이 표식을 단 환경으로 띄우므로 감독 자신도 표식을 단다.
감독 pid 는 여기에 시작 시각 대조가 더해진다.

**살아 있음** 은 감독만 보지 않는다: 감독이 죽어도 하네스가 살아 있거나, 작업자가 end.json 을 미리 써 놓고
계속 돌면 슬롯이 비었다고 하면 안 된다. 그래서 `state()` 는 이 세션 표식을 단 프로세스가 하나라도 살아 있으면
running 이다. /proc 전체를 훑는 일은 `live_index()` 한 번으로 모으고, 호출마다 훑지 않게 1초 캐시를 둔다.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

from . import harness
from .env import session_key_name
from .base import (ENV_ROLE, ENV_ROOT, ENV_SESSION, END_STATES, SESSION_COLUMNS, SESSIONS_DDL, Event,
                   SessionSpec, read_event_lines)

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
#: cancel 이 SIGTERM 뒤 그룹이 사라지기를 기다리는 시간. 감독 자신의 유예(run.HARNESS_GRACE_SEC)보다 길어야
#: 감독이 하네스를 KILL 하고 end.json 을 제 손으로 쓸 틈이 생긴다.
KILL_GRACE_SEC = 5.0
#: SIGKILL 뒤 그룹이 사라지기를 기다리는 시간.
KILL_WAIT_SEC = 2.0
#: meta.json 의 pid 칸이 아직 비었을 때 '띄우는 중' 으로 봐 주는 시간. 넘으면 lost.
SPAWN_WINDOW_SEC = 15.0
#: 감독이 end.json 을 쓴 뒤 DB 를 적고 나가기까지 봐 주는 시간. 이 안이면 '끝마무리 중인 감독' 으로 보고
#: end.json 을 믿는다. 넘었는데 감독이 살아 있으면 end.json 을 믿지 않는다(running).
FINALISE_GRACE_SEC = 3.0
#: `live_index` 캐시 수명. state() 는 그래프 한 틱에 세션마다 불린다 - 호출마다 /proc 를 훑으면 느리다.
INDEX_TTL_SEC = 1.0
#: 폴더 mtime 과 색인 시각을 비교할 때의 여유 (커널 mtime 은 거친 시계라 몇 ms 늦을 수 있다).
_MTIME_SLACK = 0.05
REPORT_STATUSES = ("DONE", "PARTIAL", "BLOCKED", "REJECT", "NEEDS-LOCK", "NEEDS-APPROVAL")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

#: 세션 폴더 -> 마지막 cancel 이 refused/foreign 을 낸 까닭 (로그용).
LAST_REFUSAL = {}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _root_str(sessions_root):
    """ENV_ROOT 비교에 쓰는 정규 꼴. spawn·고아 청소가 같은 함수를 써야 같은 저장소로 알아본다."""
    return os.path.abspath(str(sessions_root))


def _check_id(sid):
    if not isinstance(sid, str) or not _ID_RE.fullmatch(sid) or ".." in sid:
        raise ValueError(f"세션 id 로 쓸 수 없는 값: {sid!r}")
    return sid


def session_dir(sessions_root, sid):
    return pathlib.Path(sessions_root) / _check_id(sid)


# ---- 파일 ----

def _read_json(p):
    """dict 가 아니거나 못 읽으면 None. 어떤 경우에도 예외를 내지 않는다."""
    try:
        d = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def write_json_atomic(p, obj):
    p = pathlib.Path(p)
    tmp = p.with_name(f".{p.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def write_end_once(session_dir_, end):
    """end.json 을 **없을 때만** 만든다. 만들었으면 True. tmp 를 다 쓴 뒤 link 하므로 반쯤 쓴 end.json 은 없다."""
    d = pathlib.Path(session_dir_)
    tmp = d / f".end.json.tmp.{os.getpid()}"
    try:
        tmp.write_text(json.dumps(end, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            os.link(tmp, d / "end.json")
            return True
        except FileExistsError:
            return False
    except OSError:
        return False
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def load_meta(session_dir_):
    return _read_json(pathlib.Path(session_dir_) / "meta.json")


def load_end(session_dir_):
    return _read_json(pathlib.Path(session_dir_) / "end.json")


# ---- /proc ----

def _stat_fields(pid):
    """`/proc/<pid>/stat` 의 comm 뒤 칸들 (rest[0]=state, [1]=ppid, [2]=pgrp, [19]=starttime). 없으면 None."""
    try:
        raw = pathlib.Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    # comm 은 괄호 안이고 공백·괄호를 품을 수 있어 **마지막** `)` 뒤에서 읽는다.
    rest = raw[raw.rfind(")") + 1:].split()
    return rest if len(rest) >= 20 else None


def proc_start(pid):
    """프로세스 시작 시각(부팅 뒤 clock tick, stat 22번째 칸). pid 재사용을 가리는 신원. 없으면 None."""
    f = _stat_fields(pid)
    return int(f[19]) if f else None


def _proc_state(pid):
    f = _stat_fields(pid)
    return f[0] if f else None


def _proc_environ(pid):
    try:
        raw = pathlib.Path(f"/proc/{int(pid)}/environ").read_bytes()
    except (OSError, ValueError):
        return None
    out = {}
    for item in raw.split(b"\0"):
        k, sep, v = item.partition(b"=")
        if sep:
            out[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return out


def _proc_cmdline(pid):
    try:
        return pathlib.Path(f"/proc/{int(pid)}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except (OSError, ValueError):
        return ""


def _live_pids():
    try:
        return [int(p) for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return []


def group_members(pgid, exclude=()):
    """pgrp 가 pgid 인, 좀비가 아닌 pid 들."""
    out = []
    for p in _live_pids():
        if p in exclude:
            continue
        f = _stat_fields(p)
        if f and f[2] == str(pgid) and f[0] != "Z":
            out.append(p)
    return out


def _pgroup_alive(pgid):
    """그룹에 살아 있는 프로세스가 있는지. 리더가 좀비면 죽은 것으로 보고 나머지 구성원을 /proc 에서 찾는다
    (`fleet_graph._pgroup_alive` 와 같은 규칙 - killpg(pgid, 0) 은 좀비 그룹에도 성공한다)."""
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    if _proc_state(pgid) not in (None, "Z"):
        return True
    return bool(group_members(pgid))


def _ancestors():
    """나와 내 조상 pid 들. 고아 청소가 이것들에는 절대 신호를 보내지 않는다."""
    out, p = set(), os.getpid()
    while p and p not in out:
        out.add(p)
        f = _stat_fields(p)
        p = int(f[1]) if f else 0
    return out


def _same_root(env_root, root_s, cache=None):
    """환경의 저장소 표식이 이 저장소인지. 글자가 같거나, 같은 폴더를 가리키면(심볼릭 링크) 같다.
    복사본은 다른 폴더라 다르다 - 그것이 이 비교의 목적이다."""
    if not env_root:
        return False
    if env_root == root_s:
        return True
    if cache is not None and env_root in cache:
        return cache[env_root]
    try:
        same = os.path.realpath(env_root) == os.path.realpath(root_s)
    except (OSError, ValueError):
        same = False
    if cache is not None:
        cache[env_root] = same
    return same


def _folder_ident(d):
    """세션 폴더에서 뽑은 신원 (저장소 정규 꼴, 세션 id). meta.json 은 보지 않는다(위조·복사 방어)."""
    d = pathlib.Path(d)
    return _root_str(d.parent), d.name


def _marked_start(pid, root_s, sid):
    """pid 가 살아 있고(좀비 아님) 이 저장소·이 세션 표식을 달았으면 그 시작 시각, 아니면 None.
    환경을 못 읽으면(남의 uid 등) 우리 것이 아니다."""
    f = _stat_fields(pid)
    if not f or f[0] == "Z":
        return None
    env = _proc_environ(pid)
    if not env or env.get(ENV_SESSION) != sid or not _same_root(env.get(ENV_ROOT), root_s):
        return None
    return int(f[19])


def _supervisor_alive(meta, d):
    """meta 의 감독 pid 가 **이 폴더 세션의** 감독인 채로 살아 있는지.

    좀비 아님 + 시작 시각이 meta 와 같음 + 환경 표식(저장소·id)이 폴더와 같음. 시작 시각이 비어 있으면
    (exec 실패 뒤 등) 살아 있다고 보지 않는다 - pid 만 보면 재사용된 pid 에 슬롯이 영영 묶인다.
    """
    pid = meta.get("supervisor_pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return False
    want = meta.get("proc_start")
    if want is None or isinstance(want, bool) or not isinstance(want, int):
        return False
    root_s, sid = _folder_ident(d)
    return _marked_start(pid, root_s, sid) == want


# ---- 살아 있는 세션 프로세스 색인 ----

class LiveIndex(dict):
    """`{세션 id: [pid, ...]}` - 한 저장소의 표식을 단 살아 있는 프로세스. `at` 은 훑기 **시작** 벽시계 시각."""
    root = ""
    at = 0.0
    mono = 0.0


_INDEX_CACHE = {}


def live_index(sessions_root):
    """/proc 를 **한 번** 훑어 이 저장소 표식(ENV_ROOT)을 단, 좀비 아닌 프로세스를 세션 id 별로 모은다.

    그래프 한 틱처럼 state() 를 여러 번 부를 때는 이것을 한 번 만들어 `state(d, live=...)` 로 넘긴다.
    만들 때마다 모듈 캐시도 갈아 끼운다(live=None 인 state() 가 1초 안에서 다시 쓴다).
    pid 목록은 후보일 뿐이다 - state() 는 쓸 때마다 pid 하나씩 표식·생존을 다시 본다.
    """
    rs = _root_str(sessions_root)
    idx = LiveIndex()
    idx.root, idx.at, idx.mono = rs, time.time(), time.monotonic()
    same = {}
    for p in _live_pids():
        env = _proc_environ(p)
        if not env:
            continue
        sid = env.get(ENV_SESSION)
        if not sid or not _same_root(env.get(ENV_ROOT), rs, same):
            continue
        if _proc_state(p) in (None, "Z"):
            continue
        idx.setdefault(sid, []).append(p)
    _INDEX_CACHE[rs] = idx
    return idx


def _index_for(root_s, live):
    """넘겨받은 색인이 이 저장소 것이면 그것, 아니면 1초 캐시, 그것도 낡았으면 새로 훑는다."""
    if isinstance(live, LiveIndex) and live.root == root_s:
        return live
    idx = _INDEX_CACHE.get(root_s)
    if idx is not None and time.monotonic() - idx.mono < INDEX_TTL_SEC:
        return idx
    return live_index(root_s)


def _mtime(p):
    try:
        return os.stat(p).st_mtime
    except OSError:
        return 0.0


def _session_alive_pids(d, live=None, skip=None):
    """이 폴더 세션의 표식을 단 살아 있는 pid → 시작 시각 (skip 은 뺀다). 색인이 낡았을 수 있어 이렇게 다룬다:

    - 색인의 후보는 pid 하나씩 지금 다시 본다 (죽었거나 남의 것이 됐으면 뺀다)
    - 후보가 있었는데 다 죽었다 → 색인 뒤에 그들이 낳은 자식이 있을 수 있다 → 새로 훑는다
    - 후보가 없었다 → 색인을 훑은 때 이 세션 프로세스가 하나도 없었다는 뜻이고, 표식은 표식 단 부모에게서만
      물려받으므로 그 뒤에도 생길 수 없다. 단, 색인이 **세션 폴더가 마지막으로 바뀐 때보다 뒤에** 훑은
      것이어야 한다(그 앞이면 막 띄운 세션이 색인에 없을 수 있다) - 아니면 새로 훑는다
    """
    root_s, sid = _folder_ident(d)
    idx = _index_for(root_s, live)
    for fresh in (False, True):
        cands = list(idx.get(sid, ()))
        alive = {}
        for p in cands:
            if p == skip:
                continue
            st = _marked_start(p, root_s, sid)
            if st is not None:
                alive[p] = st
        if alive or fresh:
            return alive
        # skip(살아 있는 감독)만 있었어도 '후보가 있었다' 로 친다 - 색인 뒤에 감독이 낳은 것이 있을 수 있다.
        if not cands and idx.at > _mtime(d) + _MTIME_SLACK:
            return {}
        idx = live_index(root_s)
    return {}


# ---- 띄우기 ----

def spawn(spec: SessionSpec, brief_text, sessions_root, *, db_path=None, env_root=None):
    """세션 폴더를 만들고 감독 프로세스를 띄운다. 세션 폴더 경로를 준다. 즉시 돌아온다.

    - 같은 id 의 폴더가 있으면 FileExistsError
    - 어댑터 `command()` 의 ValueError 는 그대로 올린다 - 그때는 방금 만든 폴더를 지우고 아무것도 띄우지 않는다
    - 감독을 못 띄우면 end.json(failed/infra) 을 남기고 RuntimeError
    """
    _check_id(spec.id)
    root = pathlib.Path(_root_str(sessions_root))
    root.mkdir(parents=True, exist_ok=True)
    d = root / spec.id
    d.mkdir()                                   # 있으면 FileExistsError
    try:
        brief = d / "brief.md"
        brief.write_text(brief_text, encoding="utf-8")
        spec.brief_path = str(brief)
        adapter = harness.get(spec.harness)
        cmd = adapter.command(spec)             # 아무것도 띄우기 전에 거절받는다
        argv = [str(a) for a in cmd.argv]
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)    # 방금 만든 폴더 - 남이 쓸 틈이 없었다
        raise
    meta = spec.to_dict()
    meta.update({
        "harness_effective": adapter.name, "command": argv,
        "stdin_path": cmd.stdin_path, "command_cwd": str(cmd.cwd),
        "env_unset": list(cmd.env_unset), "env_set_names": sorted(cmd.env_set),   # 값은 적지 않는다
        "db_path": str(db_path) if db_path else None,
        "env_root": str(env_root) if env_root else None,
        # `.env` 에서 넘겨줄 변수 이름 (값은 적지 않는다) - 공급자 키 하나뿐이다 (`env.session_key_name`)
        "env_file_names": [n for n in [session_key_name(env_root, spec.provider)] if n],
        "sessions_root": str(root), "started": _now(),
        "supervisor_pid": None, "pgid": None, "proc_start": None})
    write_json_atomic(d / "meta.json", meta)

    env = dict(os.environ)
    env[ENV_SESSION], env[ENV_ROLE], env[ENV_ROOT] = spec.id, spec.role, str(root)
    try:
        # cwd 를 tools/ 로 - `-m fleet_rt.run` 이 PYTHONPATH 없이 꾸러미를 찾는다(PYTHONPATH 를 하네스까지 물려주지 않으려고).
        p = subprocess.Popen([sys.executable, "-m", "fleet_rt.run", "--detach", str(d)], cwd=str(TOOLS_DIR),
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=env, close_fds=True)
        out, _ = p.communicate(timeout=30)
        pid = int(out.split()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as e:
        # pid 를 못 받았으면 감독이 떴더라도 meta 를 못 채운다 - 감독은 META_WAIT_SEC 뒤 스스로 끝난다.
        write_end_once(d, {"state": "failed", "rc": None, "ended": _now(), "fail_kind": "infra",
                           "why": f"감독 프로세스를 띄우지 못함: {e.__class__.__name__}"})
        raise RuntimeError(f"감독 프로세스를 띄우지 못했습니다: {e}") from e
    try:
        pgid = os.getpgid(pid)
    except OSError:
        pgid = None          # 이미 끝났다(아주 짧은 세션은 아니다 - 감독이 meta 를 기다린다). 그래도 적는다
    meta.update({"supervisor_pid": pid, "pgid": pgid, "proc_start": proc_start(pid)})
    write_json_atomic(d / "meta.json", meta)
    return d


# ---- 상태 ----

def last_event_at(session_dir_):
    """events.jsonl 마지막 줄의 받은 시각. 줄이 길 수 있어(최대 1MB) 끝에서 거꾸로 읽는다."""
    p = pathlib.Path(session_dir_) / "events.jsonl"
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            # 끝의 줄바꿈들은 건너뛴다
            while end > 0:
                f.seek(end - 1)
                if f.read(1) not in (b"\n", b"\r"):
                    break
                end -= 1
            if end == 0:
                return None
            pos, start = end, 0
            while pos > 0:
                step = min(65536, pos)
                pos -= step
                f.seek(pos)
                i = f.read(step).rfind(b"\n")
                if i >= 0:
                    start = pos + i + 1
                    break
            f.seek(start)
            head = f.read(64)
    except OSError:
        return None
    at, sep, _ = head.decode("utf-8", "replace").partition("\t")
    return at if sep else None


def state(session_dir_, live=None):
    """`{"state","rc","ended","fail_kind","why","last_event_at","orphaned"}`. 예외를 내지 않는다.

    - end.json 이 있고 이 세션 프로세스가 하나도 안 살아 있으면 그 내용(끝남). 감독이 end.json 을 쓰고
      DB 를 적는 끝마무리(FINALISE_GRACE_SEC 안, 감독 말고는 없음)도 끝남으로 본다
    - end.json 이 있는데 프로세스가 살아 있으면 running - 작업자가 end.json 을 미리 써 놓고 계속 도는 경우다
    - end.json 이 없으면: 감독이 그 감독인 채 살아 있으면 running, 띄우는 중이면 running, 감독은 없는데 이 세션
      표식을 단 프로세스(하네스·손자)가 살아 있으면 running + `orphaned: True`, 아무것도 없으면 lost
    - meta.json 이 깨졌거나 없어도 표식 단 프로세스가 살아 있으면 running(`orphaned: True`) - 끝났다고 하면
      그 슬롯에 둘째 작업자가 뜬다

    `orphaned: True` = 살아 있는 감독 없이 이 세션 프로세스가 돈다. 저절로 끝나지 않을 수 있으니 호출자는
    `cancel` 로 끊는다(pid 하나씩 끝내고 end.json 을 killed 로 적는다).

    `live` 는 `live_index(같은 저장소)` 가 준 색인. 여러 세션을 한꺼번에 볼 때 한 번만 훑으려고 받는다.
    None 이면 1초 캐시를 쓰고, 캐시로 '아무것도 안 살아 있음' 을 단정할 수 없을 때만 새로 훑는다
    (`_session_alive_pids`). 그래서 끝난 세션 수천 개를 봐도 /proc 를 훑는 일은 1초에 한 번 꼴이다.
    """
    d = pathlib.Path(session_dir_)
    out = {"state": "lost", "rc": None, "ended": None, "fail_kind": None, "why": None,
           "last_event_at": last_event_at(d), "orphaned": False}
    end = load_end(d)
    meta = load_meta(d)
    sup = meta is not None and _supervisor_alive(meta, d)
    sup_pid = meta.get("supervisor_pid") if sup else None

    def busy(why, orphaned):
        out.update({"state": "running", "rc": None, "ended": None, "fail_kind": None, "why": why,
                    "orphaned": orphaned})
        return out

    if end is not None and end.get("state") in END_STATES:
        others = _session_alive_pids(d, live, skip=sup_pid)
        if not others and (not sup or time.time() - _mtime(d / "end.json") < FINALISE_GRACE_SEC):
            for k in ("state", "rc", "ended", "fail_kind", "why"):
                out[k] = end.get(k)
            return out
        return busy("end.json 이 있는데 프로세스가 살아 있음", not sup)
    if end is not None or (d / "end.json").exists():
        out["why"] = "end.json 이 깨짐"
    if sup:
        return busy(out["why"], False)
    if meta is not None and meta.get("supervisor_pid") is None:
        try:
            age = time.time() - datetime.datetime.fromisoformat(str(meta.get("started"))).timestamp()
        except (TypeError, ValueError):
            age = None
        # 시작 시각이 앞날이면(음수) 창 안이 아니다 - 그렇게 적어 둔 폴더 하나가 '띄우는 중' 으로 영영 남아 모든 라운드를 막았다
        if age is not None and 0 <= age < SPAWN_WINDOW_SEC:
            return busy("띄우는 중", False)
    if _session_alive_pids(d, live):
        return busy("meta.json 이 없거나 깨졌는데 이 세션 프로세스가 살아 있음" if meta is None
                    else "감독 없이 하네스가 살아 있음", True)
    if meta is None:
        out["why"] = "meta.json 이 없거나 깨짐"
    elif meta.get("supervisor_pid") is None:
        out["why"] = out["why"] or "감독 pid 가 기록되지 않음"
    else:
        out["why"] = out["why"] or "end.json 없이 감독 프로세스가 사라짐"
    return out


def list_ids(sessions_root):
    """세션 id 들, 시작 시각 순."""
    root = pathlib.Path(sessions_root)
    try:
        dirs = [p for p in root.iterdir() if p.is_dir() and _ID_RE.fullmatch(p.name)]
    except OSError:
        return []
    keyed = []
    for p in dirs:
        m = load_meta(p) or {}
        keyed.append((str(m.get("started") or ""), p.name))
    return [name for _, name in sorted(keyed)]


def _adapter_for(meta):
    try:
        return harness.get((meta or {}).get("harness_effective") or (meta or {}).get("harness") or "")
    except (ValueError, ImportError):
        return None


def tail(session_dir_, n=20):
    """끝의 n 줄을 `(받은 시각, Event)` 로. 어댑터를 모르면 kind='raw'."""
    adapter = _adapter_for(load_meta(session_dir_))
    out = []
    for at, raw in read_event_lines(session_dir_, tail=n):
        ev = None
        if adapter is not None:
            try:
                ev = adapter.parse_event(raw)
            except Exception:  # noqa: BLE001 - 어댑터가 한 줄에 터져도 나머지는 보인다
                ev = Event("raw", raw=raw)
        elif raw.strip():
            ev = Event("raw", raw=raw)
        if ev is not None:
            out.append((at, ev))
    return out


def report(session_dir_):
    d = pathlib.Path(session_dir_)
    try:
        return (d / "report.md").read_text(encoding="utf-8")
    except OSError:
        pass
    adapter = _adapter_for(load_meta(d))
    if adapter is None:
        return ""
    try:
        return adapter.final_report(d) or ""
    except Exception:  # noqa: BLE001
        return ""


# ---- 끊기 ----

def _signal_pids(pids, starts):
    """pid 하나씩 TERM → (최대 3초) → KILL. 보내기 직전마다 시작 시각을 다시 본다(그 사이 pid 재사용 방지)."""
    sent = []
    for p in pids:
        if proc_start(p) == starts.get(p):
            try:
                os.kill(p, signal.SIGTERM)
                sent.append(p)
            except OSError:
                pass
    deadline = time.time() + 3.0
    while time.time() < deadline and any(_proc_state(p) not in (None, "Z") and proc_start(p) == starts.get(p)
                                         for p in sent):
        time.sleep(0.1)
    for p in sent:
        if _proc_state(p) not in (None, "Z") and proc_start(p) == starts.get(p):
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass
    return sent


def _session_remnants(d):
    """지금 살아 있는 이 폴더 세션의 프로세스 `{pid: 시작 시각}` - 새로 훑는다(캐시 안 씀). 나와 내 조상은 뺀다.

    신원은 폴더에서 뽑은 환경 표식(저장소·id) 둘 다다. meta.json 의 값은 보지 않는다 - 위조·복사된 meta 로
    남의 세션 프로세스를 끊게 하지 않으려고.
    """
    root_s, sid = _folder_ident(d)
    mine = _ancestors()
    out = {}
    for p in live_index(root_s).get(sid, ()):
        if p in mine or p <= 1:
            continue
        st = _marked_start(p, root_s, sid)
        if st is not None:
            out[p] = st
    return out


def end_remnants(session_dir_):
    """이 세션 표식을 단 남은 프로세스를 pid 하나씩 끝낸다(TERM → 3초 → KILL, 나·조상 제외). 끝낸 pid 목록.
    감독이 마감 직전에, cancel 이 그룹을 끝낸 뒤에 부른다 - setsid 로 그룹을 빠져나간 손자를 잡는 자리다."""
    rem = _session_remnants(session_dir_)
    return _signal_pids(list(rem), rem) if rem else []


def _write_killed(d, replace, why):
    """end.json 을 killed 로 남긴다. `replace` 면 이미 있는 것(작업자가 미리 쓴 것·깨진 것)을 **덮는다** -
    프로세스가 살아 있었거나 파일이 깨졌으니 그것은 끝남 기록이 아니었다. 아니면 없을 때만 만든다."""
    end = {"state": "killed", "rc": None, "ended": _now(), "fail_kind": None, "why": why}
    if not replace:
        return write_end_once(d, end)
    try:
        write_json_atomic(d / "end.json", end)
        return True
    except OSError:
        return False


def cancel(session_dir_, why=""):
    """세션을 끊는다. `killed` / `gone` / `refused` / `foreign`.

    - killed: 살아 있던 이 세션 프로세스를 끊었다. end.json(killed) 이 반드시 남는다
    - gone: 끊을 것이 없었다(이미 끝남) 또는 끊는 사이 세션이 제 손으로 끝남 - 그 end.json 은 그대로 둔다.
      end.json 없이 감독이 사라진 세션(lost)이면 killed 로 적어 슬롯을 비운다
    - refused: 안전 검사 거부 - **세션이 살아 있을 수 있다**(호출자는 슬롯을 비우면 안 된다). 까닭은 LAST_REFUSAL
    - foreign: meta 의 pid 가 이 세션 프로세스가 아님(pid 재사용·복사된 폴더·위조된 meta) - 신호를 안 보냈다

    신호를 받는 프로세스는 모두 **이 폴더의 환경 표식**(저장소·id)을 단 것뿐이다:
    1. 감독이 그 감독인 채 살아 있으면(시작 시각 + 표식) 그룹에 TERM, 5초 뒤 남으면 KILL (감독이 세션 리더일 때만)
    2. 그 뒤(또는 감독이 없으면 바로) 표식을 단 남은 프로세스를 pid 하나씩 - setsid 한 손자, 감독 없이 남은 하네스,
       meta.json 이 깨진 세션의 프로세스

    `pkill -f` 는 쓰지 않는다(AIMEM 8.0-5).
    """
    d = pathlib.Path(session_dir_)
    key = str(d)
    LAST_REFUSAL.pop(key, None)

    def refuse(o, reason):
        LAST_REFUSAL[key] = reason
        return o

    if not _ID_RE.fullmatch(d.name) or ".." in d.name:
        return refuse("refused", f"세션 폴더 이름이 세션 id 가 아님: {d.name!r}")
    reason = why or "취소"
    meta = load_meta(d)
    end = load_end(d)
    end_ok = end is not None and end.get("state") in END_STATES
    end_present = end is not None or (d / "end.json").exists()
    pid = (meta or {}).get("supervisor_pid")
    pid_ok = isinstance(pid, int) and not isinstance(pid, bool) and pid > 1 and pid != os.getpid()
    sup = meta is not None and pid_ok and _supervisor_alive(meta, d)

    if sup:
        if end_ok and not _session_alive_pids(d, None, skip=pid) \
                and time.time() - _mtime(d / "end.json") < FINALISE_GRACE_SEC:
            return "gone"           # 끝마무리 중인 감독 (end.json 뒤 DB 를 적는 몇 ms) - 끊지 않는다
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            pgid = None             # 그 사이 끝났다 - 남은 것은 아래 2단계가 본다
        except OSError as e:
            return refuse("refused", f"getpgid 실패: {e.__class__.__name__}")
        if pgid is not None:
            try:
                mine = os.getpgid(0)
            except OSError as e:
                return refuse("refused", f"내 pgid 조회 실패: {e.__class__.__name__}")
            if pgid != pid:
                return refuse("refused", f"세션 리더 아님: getpgid={pgid}")
            if pgid == 0 or pgid == mine:
                return refuse("refused", f"내 프로세스 그룹({pgid})")
            # 감독이 SIGTERM 을 받으면 이 파일에서 까닭을 읽어 end.json 에 적는다 - 신호보다 먼저 둔다.
            try:
                write_json_atomic(d / "cancel.json", {"why": reason, "at": _now()})
            except OSError:
                pass
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError as e:
                return refuse("refused", f"SIGTERM 실패: {e.__class__.__name__}")
            deadline = time.time() + KILL_GRACE_SEC
            while time.time() < deadline and _pgroup_alive(pgid):
                time.sleep(0.1)
            if _pgroup_alive(pgid):
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except OSError:
                    pass
                deadline = time.time() + KILL_WAIT_SEC
                while time.time() < deadline and _pgroup_alive(pgid):
                    time.sleep(0.1)
        end_remnants(d)             # 그룹 밖으로 나간(setsid) 이 세션 손자
        if end_present:
            # 신호 전부터 end.json 이 있었는데 감독·하네스가 살아 있었다 → 미리 써 둔(또는 깨진) end.json 이다.
            _write_killed(d, True, f"end.json 이 있었지만 프로세스가 살아 있어 끊음 ({reason})")
            return "killed"
        _write_killed(d, False, reason)
        # 신호가 닿기 전에 세션이 제 손으로 끝났으면(감독이 done 등을 먼저 적음) 그 결과를 살린다.
        return "killed" if (load_end(d) or {}).get("state") == "killed" else "gone"

    rem = _session_remnants(d)
    if rem:
        # 감독 없이 남은 이 세션 프로세스 (감독이 죽음 / meta 가 깨짐 / end.json 을 미리 써 둠).
        try:
            write_json_atomic(d / "cancel.json", {"why": reason, "at": _now()})
        except OSError:
            pass
        _signal_pids(list(rem), rem)
        end_remnants(d)             # 끝나는 사이 새로 생긴 것
        if end_present:
            w = f"end.json 이 있었지만 프로세스가 살아 있어 끊음 ({reason})"
        elif meta is None:
            w = f"meta.json 이 깨져 표식으로 찾은 프로세스를 끊음 ({reason})"
        else:
            w = f"감독 프로세스가 이미 없음 ({reason})"
        _write_killed(d, end_present, w)
        return "killed"
    if end_ok:
        return "gone"               # 끝난 세션 - 기록은 그대로
    if meta is None:
        return refuse("refused", "meta.json 이 없거나 깨짐")
    if not pid_ok:
        return refuse("refused", f"pid 값이 쓸 수 없음({pid!r})")
    if _proc_state(pid) not in (None, "Z"):
        # 살아 있는 pid 인데 이 세션 것이 아니다 - pid 재사용, 복사된 폴더, 위조된 meta.
        return refuse("foreign", "시작 시각·환경 표식이 이 세션과 다름 (pid 재사용·복사·위조)")
    # 감독도 남은 것도 없다(lost). 끊으라는 요청이었으니 끝난 것으로 적어 슬롯을 비운다.
    _write_killed(d, end_present, f"감독 프로세스가 이미 없음 ({reason})"
                  + (" - 깨진 end.json 을 덮음" if end_present else ""))
    return "gone"


# ---- 고아 ----

def find_orphans(sessions_root):
    """이 저장소(ENV_ROOT == sessions_root) 표식을 단 내 uid 의 프로세스 가운데 고아인 것.

    고아 = 세션 폴더가 없거나, 그 세션에 살아 있는 감독이 없음 - state 가 running 이 아니거나 running 이라도
    `orphaned`(감독은 갔는데 하네스·setsid 한 손자가 남음)인 경우. 살아 있는 감독이 지키는 세션의 프로세스와
    끝마무리 중인 감독 자신(end.json 을 쓴 뒤 db 를 적는 몇 ms)은 고아로 치지 않는다.
    """
    root = pathlib.Path(_root_str(sessions_root))
    idx = live_index(root)
    mine, uid = _ancestors(), os.getuid()
    out, cache = [], {}
    for sid, pids in sorted(idx.items()):
        for p in pids:
            if p in mine:
                continue
            try:
                if os.stat(f"/proc/{p}").st_uid != uid:
                    continue
            except OSError:
                continue
            f = _stat_fields(p)
            if not f or f[0] == "Z":
                continue
            try:
                d = session_dir(root, sid)
            except ValueError:
                d = None
            if d is None or not d.is_dir():
                why = "세션 폴더 없음"
            else:
                if sid not in cache:
                    cache[sid] = (state(d, live=idx), load_meta(d) or {})
                st, meta = cache[sid]
                if st["state"] == "running" and not st.get("orphaned"):
                    continue
                if p == meta.get("supervisor_pid") and int(f[19]) == meta.get("proc_start"):
                    continue            # 끝마무리 중인 감독 - 곧 스스로 끝난다
                why = "감독 없이 남음" if st["state"] == "running" else f"세션이 {st['state']}"
            out.append({"pid": p, "session": sid, "pgid": int(f[2]), "start": int(f[19]), "why": why,
                        "cmdline": _proc_cmdline(p)[:300]})
    return out


def reap_orphans(sessions_root, kill=False):
    """고아 목록. `kill=True` 면 정확히 그 pid 들에만 TERM → KILL (그룹 신호 없음, 나·조상 제외).
    각 항목에 `"killed": bool` 을 더한다."""
    orphans = find_orphans(sessions_root)
    if not kill or not orphans:
        return orphans
    mine = _ancestors()
    starts = {o["pid"]: o["start"] for o in orphans if o["pid"] not in mine and o["pid"] > 1}
    sent = set(_signal_pids(list(starts), starts))
    for o in orphans:
        o["killed"] = o["pid"] in sent
    return orphans


# ---- DB 색인 ----

def db_upsert(db_path, row):
    """`sessions` 표에 한 줄 넣거나 고친다. 실패하면 False (폴더가 정본이라 색인 실패는 넘어간다)."""
    if not db_path:
        return False
    cols = [c for c in SESSION_COLUMNS if c in row]
    if "id" not in cols:
        return False
    try:
        con = sqlite3.connect(str(db_path), timeout=10)
        try:
            con.executescript(SESSIONS_DDL)
            sets = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
            con.execute(f"INSERT INTO sessions({', '.join(cols)}) VALUES({', '.join('?' * len(cols))}) "
                        f"ON CONFLICT(id) DO UPDATE SET {sets}", [row[c] for c in cols])
            con.commit()
        finally:
            con.close()
        return True
    except (sqlite3.Error, OSError, ValueError):
        return False


def _report_status(text):
    for ln in (text or "").splitlines():
        if ln.strip():
            word = ln.split()[0].strip("*#`:.,[]()")
            return word if word in REPORT_STATUSES else None
    return None


def _num_sum(a, b):
    if b is None or isinstance(b, bool) or not isinstance(b, (int, float)):
        return a
    return b if a is None else a + b


def index_row(session_dir_, live=None):
    """폴더(meta + end + events) 에서 `sessions` 표 한 줄을 만든다. 색인을 다시 만들 때도 쓴다.
    `live` 는 `state()` 에 그대로 넘긴다(여러 폴더를 다시 색인할 때 /proc 를 한 번만 훑게)."""
    d = pathlib.Path(session_dir_)
    meta = load_meta(d) or {}
    st = state(d, live=live)
    tin = tout = cost = None
    hsid = None
    adapter = _adapter_for(meta)
    if adapter is not None:
        for _at, raw in read_event_lines(d):
            try:
                ev = adapter.parse_event(raw)
            except Exception:  # noqa: BLE001
                continue
            if ev is None:
                continue
            data = ev.data if isinstance(ev.data, dict) else {}
            if data.get("harness_session_id"):
                hsid = str(data["harness_session_id"])
            if ev.kind in ("usage", "end"):
                tin = _num_sum(tin, data.get("tokens_in"))
                tout = _num_sum(tout, data.get("tokens_out"))
                cost = _num_sum(cost, data.get("cost_usd"))
    try:
        rep = (d / "report.md").read_text(encoding="utf-8")
    except OSError:
        rep = ""
    wp = meta.get("write_paths")
    return {
        "id": meta.get("id") or d.name, "role": meta.get("role") or "worker",
        "round": meta.get("round"), "task_id": meta.get("task_id"), "slot": meta.get("slot"),
        "harness": meta.get("harness_effective") or meta.get("harness") or "?",
        "model": meta.get("model"), "provider": meta.get("provider"),
        "pid": meta.get("supervisor_pid"), "pgid": meta.get("pgid"), "harness_session_id": hsid,
        "state": st["state"], "started": meta.get("started"), "ended": st["ended"],
        "last_event_at": st["last_event_at"], "rc": st["rc"], "report_status": _report_status(rep),
        "tokens_in": tin, "tokens_out": tout, "cost_usd": cost, "fail_kind": st["fail_kind"],
        "attempt": meta.get("attempt"), "label": meta.get("label"),
        "write_paths": json.dumps(wp if isinstance(wp, list) else [], ensure_ascii=False), "dir": str(d)}
