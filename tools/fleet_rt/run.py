"""세션 감독 프로세스 - 세션마다 하나. `python3 -m fleet_rt.run <세션 폴더>`.

`sessions.spawn` 이 `--detach` 로 띄우면 fork + setsid 로 새 세션의 리더가 되어 exec 한다(자세한 길은
`sessions.py` 머리말). 하는 일:

1. meta.json 의 `supervisor_pid` 가 자기 pid 가 될 때까지 기다린다 (신원이 기록되기 전엔 하네스를 안 띄운다)
2. 하네스를 **같은 프로세스 그룹**의 자식으로 띄운다. argv 는 meta.json 에 적힌 것 그대로 - spawn 이
   검사한 것이 도는 것이다. 어댑터는 `harness_effective` 로 다시 찾아 env_set 값·사건 해석·보고에만 쓴다
3. stdout 을 한 줄씩 `<받은 시각>\\t<원문>` 으로 events.jsonl 에 (줄마다 flush, 한 줄 최대 1MB)
4. 벽시계(timeout)·침묵(idle_timeout)을 1초 안 간격으로 본다. 넘으면 하네스와 그룹의 나머지를 끝낸다
5. SIGTERM/SIGINT/SIGHUP 를 받으면 하네스를 끝내고 killed 로 마감한다 (까닭은 cancel.json)
6. 하네스가 끝나면 그룹에 남은 손자도 끝낸다. 그룹을 빠져나간(setsid)
   손자도 이 세션 환경 표식으로 찾아 pid 하나씩 끝낸다 → report.md → end.json → DB 색인. 그리고 0 으로 나간다.
   end.json 이 이미 있으면(작업자가 미리 써 둔 것) 감독 판정으로 덮는다 - end.json 의 주인은 감독이다

환경 표식(AIFLEET_SESSION·AIFLEET_SESSIONS_ROOT)은 spawn 이 `--detach` 를 띄울 때 넣어 감독 자신도 단다.
하네스에게도 같은 값을 **폴더 경로에서** 뽑아 준다(meta.json 값이 아니라 - `sessions.py` 머리말의 신원 규칙).
"""
from __future__ import annotations

import datetime
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time

from . import harness, sessions
from .base import ENV_ROLE, ENV_ROOT, ENV_SESSION, TERM_GRACE_SEC, SessionSpec, read_event_lines
from .env import load_env, session_key_name

#: spawn 이 meta.json 에 pid 를 채우기를 기다리는 시간.
META_WAIT_SEC = 10.0
#: 하네스가 끝난 뒤 stdout 파이프를 마저 읽는 시간 (손자가 파이프를 붙잡고 있을 수 있다).
DRAIN_SEC = 1.0
LINE_CAP = 1 << 20
TICK = 0.1
#: 침묵 판정에서 사건 말고도 살아 있음으로 치는 것: 세션 프로세스가 데이터를 읽고 있는가(`/proc/<pid>/io` rchar) -
#: 긴 생성 중인 하네스는 사건 없이 토큰만 받는다. 연결 유지 신호(수십 바이트)는 문턱보다 훨씬 작다.
IO_CHECK_SEC = 10.0
IO_PROGRESS_BYTES = 4096


def _now_ms():
    return datetime.datetime.now().isoformat(timespec="milliseconds")


class Supervisor:
    def __init__(self, session_dir):
        self.d = pathlib.Path(session_dir)   # resolve 하지 않는다 - spawn 이 준 꼴 그대로(표식의 저장소 경로와 맞게)
        self.meta = None
        self.adapter = None
        self.proc = None
        self.reader = None
        self.stop_sig = None
        self.finishing = False
        self.last_activity = time.monotonic()
        self.lock = threading.Lock()

    # -- 신호: 표시만 한다. 실제 처리는 주 고리에서 (처리기 안에서 무거운 일을 하면 끝마무리와 엉킨다)
    def _on_signal(self, signum, _frame):
        if self.stop_sig is None and not self.finishing:
            self.stop_sig = signum

    def _wait_meta(self):
        me = os.getpid()
        deadline = time.monotonic() + META_WAIT_SEC
        while time.monotonic() < deadline:
            m = sessions.load_meta(self.d)
            if m and m.get("supervisor_pid") == me:
                return m
            time.sleep(0.02)
        return None

    def _build_env(self):
        m = self.meta
        unset = set(m.get("env_unset") or ())
        env = dict(os.environ)
        # `.env` 에서는 이 세션 공급자의 키 **하나만** 받는다 (`env.session_key_name`). 이름은 spawn 이 meta 의
        # `env_file_names` 에 적어 두었고, 여기서는 meta 의 이름을 믿지 않고 같은 규칙으로 다시 정한다.
        key = session_key_name(m.get("env_root"), m.get("provider"))
        if key and not env.get(key):
            v = load_env(m["env_root"]).get(key)
            if v:
                env[key] = v
        for k in unset:
            env.pop(k, None)
        # 표식은 폴더에서 뽑는다 - 감독 자신의 표식(spawn 이 넣음)과 같고, 끊기·고아 청소가 같은 규칙으로 알아본다.
        env[ENV_SESSION] = self.d.name
        env[ENV_ROLE] = str(m.get("role"))
        env[ENV_ROOT] = sessions._root_str(self.d.parent)
        names = m.get("env_set_names") or []
        if names:
            # 값은 meta 에 적지 않았다 - 어댑터로 명령을 다시 만들어 이름이 같은 것만 가져온다.
            cmd = self.adapter.command(SessionSpec.from_dict(m))
            if sorted(cmd.env_set) != sorted(names):
                raise RuntimeError("env_set 이름이 spawn 때와 다름")
            env.update({k: str(v) for k, v in cmd.env_set.items()})
        return env

    # -- stdout → events.jsonl
    def _pump(self, out, sink):
        skipping = False
        try:
            while True:
                chunk = out.readline(LINE_CAP)
                if not chunk:
                    break
                self.last_activity = time.monotonic()
                whole = chunk.endswith(b"\n")
                if skipping:                    # 1MB 를 넘은 줄의 나머지는 버린다
                    skipping = not whole
                    continue
                if not whole and len(chunk) >= LINE_CAP:
                    skipping = True
                text = chunk.rstrip(b"\r\n").decode("utf-8", "replace").replace("\r", " ")
                if not text.strip():
                    continue
                with self.lock:
                    sink.write(f"{_now_ms()}\t{text}\n".encode("utf-8"))
                    sink.flush()
        except (OSError, ValueError):
            pass

    def _others(self):
        """우리 그룹의 나 말고 살아 있는 구성원."""
        return sessions.group_members(os.getpgid(0), exclude=(os.getpid(),))

    def _terminate(self):
        """하네스와 그룹의 나머지에 TERM → TERM_GRACE_SEC → KILL. 하네스는 거둔다(좀비 안 남김).

        그룹 전체 신호(killpg)는 나 자신도 맞히므로 쓰지 않고, /proc 에서 같은 그룹의 pid 를 하나씩 찾는다.
        """
        pg = os.getpgid(0)
        targets = set(self._others())
        if self.proc is not None and self.proc.poll() is None:
            targets.add(self.proc.pid)
        for p in targets:
            try:
                if os.getpgid(p) == pg:          # 보내기 직전 다시 확인 (그 사이 끝나고 재사용됐을 수 있다)
                    os.kill(p, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.monotonic() + TERM_GRACE_SEC
        while time.monotonic() < deadline:
            if self.proc is not None:
                self.proc.poll()
            if not self._others():
                break
            time.sleep(TICK)
        for p in self._others():
            try:
                if os.getpgid(p) == pg:
                    os.kill(p, signal.SIGKILL)
            except OSError:
                pass
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def _cancel_why(self):
        c = sessions._read_json(self.d / "cancel.json")
        return str(c.get("why")) if c and c.get("why") else None

    def _outcome_after_exit(self, rc):
        if rc == 0:
            return "done", None, None
        why = f"하네스 rc {rc}"
        try:
            if self.adapter.limit_signal(self.d) is True:
                return "failed", "limit", "사용 한도"
        except Exception:  # noqa: BLE001 - 판정 실패가 마감을 막으면 안 된다
            pass
        # 재접속·시간 초과 오류만 있고 모델이 한마디도 못 했다면 기반 장애다.
        infra = False
        try:
            for ev in self._all_events():
                if ev.kind == "text" and ev.text.strip():
                    return "failed", None, why
                if ev.kind == "error" and (ev.data.get("timeout") or ev.data.get("retry")):
                    infra = True
        except Exception:  # noqa: BLE001
            pass
        return "failed", ("infra" if infra else None), why

    def _all_events(self):
        for _at, raw in read_event_lines(self.d):
            ev = self.adapter.parse_event(raw)
            if ev is not None:
                yield ev

    def _group_rchar(self):
        """이 세션 프로세스들(나 말고 - 그룹 + 그룹을 벗어난 표식 단 백그라운드 명령)이 읽은 바이트 합. 못 읽으면 0."""
        me, total = os.getpid(), 0
        pids = set()
        try:
            pids.update(sessions.group_members(os.getpgid(0), exclude=(me,)))
        except OSError:
            pass
        try:
            pids.update(sessions._session_remnants(self.d))
        except Exception:  # noqa: BLE001 - 훑기가 실패해도 그룹만으로 판정한다
            pass
        pids.discard(me)
        for p in pids:
            try:
                for line in open(f"/proc/{p}/io", encoding="ascii"):
                    if line.startswith("rchar:"):
                        total += int(line.split()[1])
                        break
            except (OSError, ValueError):
                continue
        return total

    def run(self):
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(s, self._on_signal)
        end = {"state": "failed", "rc": None, "ended": None, "fail_kind": "infra", "why": "감독 내부 오류"}
        try:
            self.meta = self._wait_meta()
            if self.meta is None:
                end["why"] = "meta.json 에 감독 pid 가 채워지지 않음 (spawn 중단)"
                return 0
            if os.getpgid(0) != os.getpid():
                end["why"] = "감독이 프로세스 그룹 리더가 아님"
                return 0
            self.adapter = harness.get(self.meta.get("harness_effective") or self.meta.get("harness"))
            end.update(self._supervise())
        except Exception as e:  # noqa: BLE001 - 무엇이 터져도 end.json 은 남긴다
            end.update({"state": "failed", "fail_kind": "infra", "why": f"감독 오류: {e.__class__.__name__}: {e}"})
        finally:
            self.finishing = True
            if self.proc is not None and self.proc.poll() is None:
                try:
                    self._terminate()
                except Exception:  # noqa: BLE001
                    pass
            try:
                # setsid 로 그룹을 빠져나간 손자 등 이 세션 표식을 단 남은 프로세스 (나·조상은 빠진다).
                sessions.end_remnants(self.d)
            except Exception:  # noqa: BLE001 - 청소 실패가 end.json 을 막으면 안 된다
                pass
            self._finish(end)
        return 0

    def _supervise(self):
        m = self.meta
        if self.stop_sig is not None:
            return {"state": "killed", "fail_kind": None, "why": self._cancel_why() or "시작 전에 끊김"}
        env = self._build_env()
        stdin = None
        if m.get("stdin_path"):
            try:
                stdin = open(m["stdin_path"], "rb")
            except OSError as e:
                return {"state": "failed", "fail_kind": "infra", "why": f"stdin 파일을 못 엶: {e}"}
        sink = open(self.d / "events.jsonl", "ab")
        errf = open(self.d / "stderr.log", "ab")
        try:
            try:
                self.proc = subprocess.Popen(
                    [str(a) for a in m["command"]], cwd=m.get("command_cwd") or m.get("cwd"),
                    stdin=stdin if stdin is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=errf, env=env, close_fds=True)   # 같은 그룹 (새 세션 아님)
            except OSError as e:
                return {"state": "failed", "fail_kind": "infra", "why": f"하네스를 띄우지 못함: {e}"}
            started = self.last_activity = time.monotonic()
            self.reader = threading.Thread(target=self._pump, args=(self.proc.stdout, sink), daemon=True)
            self.reader.start()
            sessions.db_upsert(m.get("db_path"), sessions.index_row(self.d))
            timeout = float(m.get("timeout") or 0) or None
            idle = m.get("idle_timeout")
            idle = float(idle) if idle else None
            verdict = None
            io_at, io_last = time.monotonic(), self._group_rchar()
            while True:
                if self.stop_sig is not None:
                    verdict = {"state": "killed", "fail_kind": None,
                               "why": self._cancel_why() or f"신호 {signal.Signals(self.stop_sig).name}"}
                    break
                rc = self.proc.poll()
                if rc is not None:
                    break
                now = time.monotonic()
                if timeout and now - started > timeout:
                    verdict = {"state": "timeout", "fail_kind": "timeout", "why": f"벽시계 {timeout:g}초 넘김"}
                    break
                if idle and now - io_at >= min(IO_CHECK_SEC, idle / 3):   # 침묵 한도 안에 세 번은 본다
                    io_at = now
                    rchar = self._group_rchar()
                    if rchar - io_last >= IO_PROGRESS_BYTES:
                        self.last_activity = now
                    io_last = rchar
                if idle and now - self.last_activity > idle:
                    verdict = {"state": "stalled", "fail_kind": "infra", "why": f"침묵 {idle:g}초 넘김 (사건도 읽기도 없음)"}
                    break
                time.sleep(TICK)
            if verdict is None:
                # 스스로 끝남. 파이프를 마저 읽고, 그룹에 남은 손자를 치운다(그래야 파이프도 닫힌다).
                self.reader.join(DRAIN_SEC)
                if self._others():
                    self._terminate()
                self.reader.join(DRAIN_SEC * 3)
                rc = self.proc.returncode
                # cancel 의 killpg 는 하네스와 나를 같이 맞힌다 - 하네스가 먼저 죽어 poll 에 잡혀도 끊긴 것이다.
                # 끊김의 증거는 **내가 받은 신호**뿐이다. cancel.json 만 있는 것은 아니다 - 작업자가 제 폴더에
                # cancel.json 을 쓰고 rc != 0 으로 나가면 실패가 killed(재시도 규칙이 다름)로 둔갑했다.
                if self.stop_sig is not None:
                    return {"state": "killed", "rc": rc, "fail_kind": None,
                            "why": self._cancel_why() or "신호로 끊김"}
                state, kind, why = self._outcome_after_exit(rc)
                return {"state": state, "rc": rc, "fail_kind": kind, "why": why}
            self._terminate()
            self.reader.join(DRAIN_SEC * 3)
            verdict["rc"] = self.proc.returncode
            return verdict
        finally:
            for f in (stdin, errf):
                if f is not None:
                    f.close()
            with self.lock:
                sink.close()

    def _finish(self, end):
        """report.md → end.json(한 번만) → DB. 신호가 와도 처리기는 표시만 하므로 여기는 끊기지 않는다."""
        try:
            rep = self.adapter.final_report(self.d) if self.adapter is not None else ""
        except Exception:  # noqa: BLE001
            rep = ""
        try:
            (self.d / "report.md").write_text(rep or "", encoding="utf-8")
        except OSError:
            pass
        end = {k: end.get(k) for k in ("state", "rc", "ended", "fail_kind", "why")}
        end["ended"] = sessions._now()
        if not sessions.write_end_once(self.d, end) and sessions.load_end(self.d) != end:
            # 이미 있다. 감독이 살아 있는 동안 end.json 을 먼저 쓰는 것은 하네스(작업자)뿐이다 - cancel 은 감독을
            # 끝낸 뒤에 쓰고, spawn 은 감독 pid 를 못 받았을 때만 쓴다(그때 이 감독의 판정도 실패다).
            # 미리 써 둔 'done' 이 실패를 덮지 않게 감독 판정으로 덮는다.
            end["why"] = ((end.get("why") or "") + " (먼저 있던 end.json 을 감독 판정으로 덮음)").strip()
            try:
                sessions.write_json_atomic(self.d / "end.json", end)
            except OSError:
                pass
        if self.meta is not None:
            sessions.db_upsert(self.meta.get("db_path"), sessions.index_row(self.d))


def _detach(session_dir):
    """spawn 이 부르는 중간 단계: fork → 자식이 setsid 하고 pid 를 알린 뒤 감독으로 exec. 부모는 바로 끝난다."""
    d = pathlib.Path(session_dir)
    pid = os.fork()
    if pid:
        return 0
    try:
        os.setsid()                                     # 새 세션·그룹의 리더 (pid == pgid == sid)
        os.write(1, f"{os.getpid()}\n".encode())        # setsid 뒤에 알린다 - spawn 이 읽는 pgid 가 확정값
        null = os.open(os.devnull, os.O_RDWR)
        os.dup2(null, 0)
        os.dup2(null, 1)                                # spawn 의 파이프를 놓아 줘야 spawn 이 EOF 를 본다
        log = os.open(str(d / "supervisor.log"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.dup2(log, 2)                                 # 감독 자신이 터질 때의 흔적
        os.execv(sys.executable, [sys.executable, "-m", "fleet_rt.run", str(d)])
    except BaseException:  # noqa: BLE001
        pass
    os._exit(127)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "--detach":
        return _detach(argv[1])
    if len(argv) != 1:
        print("쓰임: python3 -m fleet_rt.run <세션 폴더>", file=sys.stderr)
        return 2
    return Supervisor(argv[0]).run()


if __name__ == "__main__":
    sys.exit(main())
