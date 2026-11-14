"""앱의 서버 스크립트(`serve.py`)를 모니터가 띄우고, `/api/...` 요청을 이어 주는 관리 모듈.

표준 라이브러리만. 자식은 좁은 환경·새 세션으로 띄우고, 내릴 때는 pid(프로세스 그룹)로만 내립니다.
"""
import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TZ")
_NAME_RE = re.compile(r"^[^/\\\x00-\x1f]{1,100}$")
_CTRL_RE = re.compile(r"[\x00-\x20\x7f]")


class AppServerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _narrow_env():
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port, timeout=0.5):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _gone(pid, proc=None):
    if proc is not None:
        return proc.poll() is not None
    try:
        os.waitpid(pid, os.WNOHANG)  # 이 프로세스의 자식이면 거둠
    except (ChildProcessError, OSError):
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return True


def _kill_group(pid, proc=None):
    """pid 의 프로세스 그룹에 SIGTERM, 3초 안에 안 죽으면 SIGKILL. pid 로만 부른다."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        if proc is not None:
            try:
                proc.wait(timeout=1)
            except Exception:  # noqa: BLE001
                pass
        return
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not _gone(pid, proc):
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)  # 남은 그룹 구성원까지
    except (ProcessLookupError, PermissionError):
        pass
    end = time.monotonic() + 1.0
    while time.monotonic() < end and not _gone(pid, proc):
        time.sleep(0.05)


class _Entry:
    __slots__ = ("proc", "port", "script", "last", "inflight")

    def __init__(self, proc, port, script):
        self.proc = proc
        self.port = port
        self.script = script
        self.last = time.time()
        self.inflight = 0


class AppServers:
    def __init__(self, state_dir, *, python=sys.executable, start_timeout=10.0, idle_sec=900,
                 forward_timeout=180.0, max_req_body=65536, max_resp_body=2_097_152,
                 max_inflight=4, log=None):
        self.state_dir = Path(state_dir)
        self.python = python
        self.start_timeout = start_timeout
        self.idle_sec = idle_sec
        self.forward_timeout = forward_timeout
        self.max_req_body = max_req_body
        self.max_resp_body = max_resp_body
        self.max_inflight = max_inflight
        self.log = log or (lambda *a, **k: None)
        self._entries = {}
        self._locks = {}
        self._glock = threading.Lock()

    # ---- 내부 ----
    def _lock(self, name):
        with self._glock:
            return self._locks.setdefault(name, threading.RLock())

    def _check_name(self, name):
        if not isinstance(name, str) or not _NAME_RE.match(name) or name in (".", ".."):
            raise AppServerError(404, "앱을 찾을 수 없습니다")

    def _record_path(self, name):
        return self.state_dir / f"{name}.json"

    def _write_record(self, name, entry):
        rec = {"pid": entry.proc.pid, "port": entry.port, "script": entry.script,
               "started": time.time()}
        p = self._record_path(name)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        os.replace(tmp, p)

    def _drop_record(self, name):
        try:
            self._record_path(name).unlink()
        except OSError:
            pass

    def _alive(self, entry):
        return entry.proc.poll() is None and _port_open(entry.port)

    def _spawn(self, name, script, cwd):
        script = Path(script)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        port = _free_port()
        try:
            logf = open(self.state_dir / f"{name}.log", "wb")
        except OSError:
            raise AppServerError(503, "앱 서버가 뜨지 않았습니다") from None
        try:
            proc = subprocess.Popen(
                [self.python, str(script), "--host", "127.0.0.1", "--port", str(port)],
                cwd=str(cwd), env=_narrow_env(), stdin=subprocess.DEVNULL,
                stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            raise AppServerError(503, "앱 서버가 뜨지 않았습니다") from None
        finally:
            logf.close()
        deadline = time.monotonic() + self.start_timeout
        while True:
            if proc.poll() is not None:
                break
            if _port_open(port, 0.2):
                entry = _Entry(proc, port, str(script))
                self._entries[name] = entry
                try:
                    self._write_record(name, entry)
                except OSError:
                    pass
                self.log("app-server up", name, port)
                return entry
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        _kill_group(proc.pid, proc)
        self.log("app-server failed", name)
        raise AppServerError(503, "앱 서버가 뜨지 않았습니다")

    def _drop(self, name):
        entry = self._entries.pop(name, None)
        if entry is not None:
            _kill_group(entry.proc.pid, entry.proc)
        self._drop_record(name)
        return entry is not None

    # ---- 공개 ----
    def ensure(self, name, script, cwd):
        self._check_name(name)
        with self._lock(name):
            entry = self._entries.get(name)
            if entry is not None:
                if self._alive(entry) and entry.script == str(script):
                    return entry.port
                self._drop(name)  # 죽었거나 다른 server 로 바뀜
            return self._spawn(name, script, cwd).port

    def forward(self, name, script, cwd, method, path_qs, headers, body):
        self._check_name(name)
        if (not isinstance(path_qs, str) or not path_qs.startswith("/api/")
                or _CTRL_RE.search(path_qs)):
            raise AppServerError(404, "찾을 수 없습니다")
        body = body or b""
        if len(body) > self.max_req_body:
            raise AppServerError(413, "요청이 너무 큽니다")
        lower = {str(k).lower(): v for k, v in (headers or {}).items()}
        send = {}
        for key, canon in (("content-type", "Content-Type"), ("accept", "Accept")):
            val = lower.get(key)
            if val and not _CTRL_RE.search(str(val).replace(" ", "")):
                send[canon] = str(val)
        with self._glock:
            entry = self._entries.get(name)
            if entry is not None and entry.inflight >= self.max_inflight:
                raise AppServerError(429, "요청이 많습니다. 잠시 뒤 다시 하십시오")
            if entry is not None:
                entry.inflight += 1
        counted = entry
        try:
            for attempt in (0, 1):
                port = self.ensure(name, script, cwd)
                with self._glock:
                    entry = self._entries.get(name)
                    if entry is not counted:
                        if counted is not None:
                            counted.inflight -= 1
                        if entry is not None:
                            if entry.inflight >= self.max_inflight:
                                counted = None
                                raise AppServerError(429, "요청이 많습니다. 잠시 뒤 다시 하십시오")
                            entry.inflight += 1
                        counted = entry
                    if entry is not None:
                        entry.last = time.time()
                try:
                    return self._request(port, method, path_qs, send, body)
                except ConnectionRefusedError:
                    if attempt == 1:
                        raise AppServerError(502, "앱 서버에 연결하지 못했습니다") from None
                    with self._lock(name):
                        cur = self._entries.get(name)
                        if cur is not None and cur.port == port:
                            self._drop(name)
        finally:
            with self._glock:
                if counted is not None:
                    counted.inflight -= 1
                    counted.last = time.time()
        raise AppServerError(502, "앱 서버에 연결하지 못했습니다")

    def _request(self, port, method, path_qs, send, body):
        hdrs = {"Host": f"127.0.0.1:{port}"}
        hdrs.update(send)
        if body or method.upper() in ("POST", "PUT", "PATCH"):
            hdrs["Content-Length"] = str(len(body))
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=self.forward_timeout)
        try:
            conn.request(method.upper(), path_qs, body=body or None, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read(self.max_resp_body + 1)
            ctype = resp.getheader("Content-Type") or "application/octet-stream"
            status = resp.status
        except (socket.timeout, TimeoutError):
            raise AppServerError(504, "앱 서버가 제때 응답하지 않았습니다") from None
        except ConnectionRefusedError:
            raise
        except (OSError, http.client.HTTPException):
            raise AppServerError(502, "앱 서버와 통신하지 못했습니다") from None
        finally:
            conn.close()
        if len(data) > self.max_resp_body:
            raise AppServerError(502, "앱 서버의 응답이 너무 큽니다")
        return status, ctype, data

    def stop(self, name):
        self._check_name(name)
        with self._lock(name):
            stopped = self._drop(name)
            return stopped

    def stop_all(self):
        with self._glock:
            names = list(self._entries)
        for name in names:
            try:
                self.stop(name)
            except AppServerError:
                pass

    def reap_idle(self, now=None):
        now = time.time() if now is None else now
        with self._glock:
            idle = [n for n, e in self._entries.items()
                    if e.inflight == 0 and now - e.last > self.idle_sec]
        done = []
        for name in idle:
            with self._lock(name):
                e = self._entries.get(name)
                if e is not None and e.inflight == 0 and now - e.last > self.idle_sec:
                    self._drop(name)
                    done.append(name)
        return done

    def cleanup_stale(self):
        killed = []
        if not self.state_dir.is_dir():
            return killed
        for rec_path in sorted(self.state_dir.glob("*.json")):
            try:
                rec = json.loads(rec_path.read_text(encoding="utf-8"))
                pid = int(rec["pid"])
                script = str(rec["script"])
                port = int(rec["port"])
            except (OSError, ValueError, KeyError, TypeError):
                rec_path.unlink(missing_ok=True)
                continue
            if any(e.proc.pid == pid for e in self._entries.values()):
                continue  # 이 모니터가 지금 쓰는 자식
            try:
                cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
            except OSError:
                cmd = ""
            argv = cmd.split("\x00")
            if (pid > 1 and os.path.isabs(script) and script.endswith(".py")
                    and len(argv) >= 6 and argv[1] == script
                    and argv[2:6] == ["--host", "127.0.0.1", "--port", str(port)]
                    and not _gone(pid)):
                _kill_group(pid)
                killed.append(pid)
            rec_path.unlink(missing_ok=True)
        return killed


_REGISTRY = {}
_REGISTRY_LOCK = threading.Lock()


def registry(root):
    key = str(Path(root).resolve())
    with _REGISTRY_LOCK:
        reg = _REGISTRY.get(key)
        if reg is None:
            reg = _REGISTRY[key] = AppServers(Path(key) / ".aimem" / "appservers")
        return reg
