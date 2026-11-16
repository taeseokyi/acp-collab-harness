"""프로젝트 앱 배포 (2026-11-16, 태석님 지시) - 앱의 자체 서버를 **자기 주소**로 계속 띄워 둔다.

모니터의 '앱 열기' 는 격리된 출처(sandbox)라 마이크·서비스 워커·IndexedDB 가 없다. 그런 것을 쓰는 앱(PWA)은
자기 주소가 있어야 한다. 배포는 그 길이다:

    폰 → https://<PC>:<공개 포트>/ → 윈도우 프록시(C:\\Temp\\aimem-proxy) → WSL 127.0.0.1:<공개 포트 + 100> 의 앱 서버

- 공개 포트는 `PORT_FIRST`(18810) 부터 차례로 하나씩(18810, 18811, …, 18899), 앱마다 하나. 한 번 받은 포트와 토큰은 내렸다 올려도 그대로다
  (폰에 설치한 앱의 주소·토큰이 바뀌지 않게). 프로젝트를 지우면 같이 잊는다.
- 앱 서버는 app.json `server` 의 그 파일이고, 이렇게 띄운다 (배포 계약 - 앱 서버는 이 인자를 받아야 한다):
      python3 <server> --host 127.0.0.1 --port <안쪽 포트> --token <토큰> --tls-cert <crt> --tls-key <key>
  인증서는 모니터의 것(`.aimem/tls/server.crt`·`.key`)을 같이 쓴다 - PC 이름·주소가 같고 포트만 다르다.
  토큰은 배포마다 따로 만든다. 모니터의 접근 토큰과 섞지 않는다. **토큰 없이** 배포할 수도 있다(켤 때 사람이 고른다,
  태석님 2026-11-16) - 그때는 `--token` 을 넘기지 않는다. 주소를 아는 누구나 쓰게 되므로 화면이 그렇게 적는다.
- 띄운 서버는 모니터와 따로 산다(새 세션) - 모니터를 내렸다 올려도 그대로 돈다. 모니터가 뜰 때 켜 둔 배포 가운데
  죽어 있는 것은 다시 띄운다(`ensure_all`, WSL 을 껐다 켠 뒤).
- 윈도우 프록시에는 **켜 둔 공개 포트 목록만** 알린다(`ports.json`). 프록시는 그 포트를 `포트 + 100` 으로만 잇는다 -
  이 파일을 쓸 수 있는 누구도 그 밖의 포트를 열거나 다른 곳으로 잇게 하지 못한다.

상태는 `.aimem/deploy/`(0700, git 제외): `deploys.json`(포트·토큰·pid, 0600), `<이름>.log`. 표준 라이브러리만.
"""
import contextlib
import fcntl
import json
import os
import pathlib
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time

PORT_FIRST = 18810
PORT_COUNT = 90               # 18810~18899 - 태석님이 공유기에서 여는 구간과 같다 (2026-11-16)
INNER_OFFSET = 100            # 안쪽(WSL) 포트 = 공개 포트 + 100. 윈도우 프록시(host/aimem_proxy.py)와 같은 값이어야 한다
STATE_DIR = ".aimem/deploy"
PROXY_CONFIG_ENV = "AIMEM_PROXY_PORTS"
PROXY_CONFIG_DEFAULT = "/mnt/c/Temp/aimem-proxy/ports.json"
_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TZ")
_NAME_RE = re.compile(r"^[^/\\\x00-\x1f]{1,100}$")
_THREAD_LOCK = threading.Lock()


class DeployError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def inner_port(port):
    return port + INNER_OFFSET


def _proc_start(pid):
    """프로세스 시작 시각(`/proc/<pid>/stat` 22번째 칸) - pid 가 재사용됐는지 가린다. 못 읽으면 None."""
    try:
        raw = pathlib.Path(f"/proc/{pid}/stat").read_bytes().decode("ascii", "replace")
        return int(raw[raw.rindex(")") + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _port_open(port, timeout=0.5):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _narrow_env():
    return {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}


class Deploys:
    def __init__(self, root, *, proxy_config=None, python=sys.executable, start_timeout=10.0, port_first=PORT_FIRST):
        self.port_first = port_first          # 검사가 운영 배포와 겹치지 않는 포트를 쓰게 (운영은 늘 PORT_FIRST)
        self.root = pathlib.Path(root)
        self.dir = self.root / STATE_DIR
        self.file = self.dir / "deploys.json"
        self.python = python
        self.start_timeout = start_timeout
        self.proxy_config = pathlib.Path(proxy_config or os.environ.get(PROXY_CONFIG_ENV) or PROXY_CONFIG_DEFAULT)

    # -- 상태 파일 -------------------------------------------------------------
    @contextlib.contextmanager
    def _locked(self):
        """상태를 읽어 주고, 블록이 끝나면 도로 쓴다. 스레드와 프로세스(모니터·명령줄) 사이를 같이 막는다."""
        with _THREAD_LOCK:
            self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.dir / "deploys.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                apps = self._read()
                try:
                    yield apps
                finally:
                    self._write(apps)        # 도중에 거절돼도 그때까지 바뀐 것(죽인 프로세스·받은 포트)은 적는다
            finally:
                os.close(fd)

    def _read(self):
        try:
            if self.file.is_symlink():
                return {}
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        apps = data.get("apps") if isinstance(data, dict) else None
        out = {}
        for name, rec in (apps.items() if isinstance(apps, dict) else ()):
            if (isinstance(name, str) and _NAME_RE.match(name) and isinstance(rec, dict)
                    and isinstance(rec.get("port"), int) and not isinstance(rec.get("port"), bool)
                    and self.port_first <= rec["port"] < self.port_first + PORT_COUNT
                    and isinstance(rec.get("token"), str) and rec["token"]):
                out[name] = rec
        return out

    def _write(self, apps):
        tmp = self.dir / "deploys.json.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"apps": apps}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, self.file)

    # -- 프로세스 ---------------------------------------------------------------
    @staticmethod
    def _alive(rec):
        pid, start = rec.get("pid"), rec.get("proc_start")
        return isinstance(pid, int) and pid > 1 and start is not None and _proc_start(pid) == start

    def _kill(self, rec):
        """우리가 띄운 그 프로세스일 때만(시작 시각 대조) 세션째 끊는다."""
        if not self._alive(rec):
            return False
        pid = rec["pid"]
        for sig, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
            try:
                os.killpg(pid, sig)
            except (ProcessLookupError, PermissionError):
                break
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline and self._alive(rec):
                try:
                    os.waitpid(pid, os.WNOHANG)      # 이 프로세스의 자식이면 거둔다 (좀비는 살아 있는 것으로 보인다)
                except (ChildProcessError, OSError):
                    pass
                time.sleep(0.1)
            if not self._alive(rec):
                break
        return True

    def _tls_files(self):
        crt, key = self.root / ".aimem/tls/server.crt", self.root / ".aimem/tls/server.key"
        if not crt.is_file() or not key.is_file():
            raise DeployError(409, "모니터 인증서(.aimem/tls/server.crt·server.key)가 없습니다 - 배포는 모니터 인증서를 같이 씁니다")
        return crt, key

    def _spawn(self, name, rec, script, cwd):
        crt, key = self._tls_files()
        port = inner_port(rec["port"])
        if _port_open(port, 0.3):
            raise DeployError(409, f"안쪽 포트 {port} 를 다른 프로세스가 쓰고 있습니다")
        log_path = self.dir / f"{name}.log"
        try:
            logf = open(log_path, "ab")
        except OSError:
            raise DeployError(500, "배포 로그 파일을 열지 못했습니다") from None
        try:
            proc = subprocess.Popen(
                [self.python, str(script), "--host", "127.0.0.1", "--port", str(port)]
                + (["--token", rec["token"]] if rec.get("auth", True) else [])
                + ["--tls-cert", str(crt), "--tls-key", str(key)],
                cwd=str(cwd), env=_narrow_env(), stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                start_new_session=True)
        except OSError:
            raise DeployError(500, "앱 서버를 띄우지 못했습니다") from None
        finally:
            logf.close()
        deadline = time.monotonic() + self.start_timeout
        while True:
            if proc.poll() is not None:
                raise DeployError(502, "앱 서버가 바로 끝났습니다 - 배포 인자(--host --port --token --tls-cert --tls-key)를 "
                                       f"받는 서버인지 보십시오 ({STATE_DIR}/{name}.log)")
            if _port_open(port):
                break
            if time.monotonic() > deadline:
                with contextlib.suppress(OSError):
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(2)
                raise DeployError(504, f"앱 서버가 {int(self.start_timeout)}초 안에 포트를 열지 않았습니다 ({STATE_DIR}/{name}.log)")
            time.sleep(0.1)
        rec.update({"pid": proc.pid, "proc_start": _proc_start(proc.pid), "script": str(script),
                    "ran_auth": bool(rec.get("auth", True)),
                    "started": time.strftime("%Y-%m-%dT%H:%M:%S")})
        threading.Thread(target=proc.wait, daemon=True).start()      # 끝나면 거둔다 (좀비로 남지 않게)

    # -- 윈도우 프록시에 알리기 -------------------------------------------------
    def _sync_proxy(self, apps):
        """켜 둔 공개 포트 목록을 프록시 설정에 쓴다. (썼나, 못 쓴 까닭). 프록시 폴더가 없는 곳(시험·다른 PC)에서는 건너뛴다."""
        cfg = self.proxy_config
        if not cfg.parent.is_dir():
            return False, f"윈도우 프록시 폴더가 없습니다 ({cfg.parent})"
        ports = sorted(rec["port"] for rec in apps.values() if rec.get("on"))
        tmp = cfg.with_name(cfg.name + ".tmp")
        try:
            tmp.write_text(json.dumps({"ports": ports}) + "\n", encoding="utf-8")
            os.replace(tmp, cfg)
        except OSError as e:
            return False, f"프록시 설정을 쓰지 못했습니다 ({type(e).__name__})"
        return True, None

    # -- 밖에서 부르는 것 -------------------------------------------------------
    @staticmethod
    def _public(name, rec, alive):
        return {"name": name, "port": rec["port"], "on": bool(rec.get("on")), "alive": alive,
                "auth": bool(rec.get("auth", True)),
                "started": rec.get("started") if alive else None}

    def status(self):
        """`{이름: {name, port, on, alive, auth, started}}` - 토큰은 싣지 않는다. 5초마다 불린다(파일 한 번 + /proc)."""
        return {name: self._public(name, rec, self._alive(rec)) for name, rec in self._read().items()}

    def on(self, name, script, cwd, auth=None):
        """배포를 켠다(이미 떠 있으면 그대로). `{name, port, on, alive, auth, started, token, proxy, proxy_note}`.
        `auth` False = 토큰 없이, True = 토큰으로, None = 지난번대로(처음이면 토큰으로). 바뀌면 다시 띄운다."""
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise DeployError(400, "프로젝트 이름이 아닙니다")
        with self._locked() as apps:
            rec = apps.get(name)
            if rec is None:
                used = {r["port"] for r in apps.values()}
                first = self.port_first
                port = next((p for p in range(first, first + PORT_COUNT) if p not in used), None)
                if port is None:
                    raise DeployError(409, f"배포 포트가 남지 않았습니다 ({first}~{first + PORT_COUNT - 1})")
                rec = apps[name] = {"port": port, "token": secrets.token_urlsafe(24), "on": False}
            if auth is not None:
                rec["auth"] = bool(auth)
            if self._alive(rec) and (rec.get("script") != str(script) or rec.get("ran_auth") != rec.get("auth", True)):
                self._kill(rec)                      # 선언이 다른 파일을 가리키거나 토큰 쓰기가 바뀌었다 - 다시 띄운다
            if not self._alive(rec):
                try:
                    self._spawn(name, rec, script, cwd)
                except DeployError:
                    rec["on"] = False            # 못 띄웠다 - 켜진 것으로 남기지 않는다 (받은 포트·토큰은 둔다)
                    for k in ("pid", "proc_start", "started", "ran_auth"):
                        rec.pop(k, None)
                    self._sync_proxy(apps)
                    raise
            rec["on"] = True
            wrote, note = self._sync_proxy(apps)
            return dict(self._public(name, rec, True), token=rec["token"] if rec.get("auth", True) else None,
                        proxy=wrote, proxy_note=note)

    def off(self, name, forget=False):
        """배포를 내린다. 포트·토큰은 남긴다(`forget` 이면 지운다 - 프로젝트 삭제). 없던 배포면 None."""
        with self._locked() as apps:
            rec = apps.get(name)
            if rec is None:
                return None
            self._kill(rec)
            rec["on"] = False
            for k in ("pid", "proc_start", "started", "ran_auth"):
                rec.pop(k, None)
            if forget:
                del apps[name]
            wrote, note = self._sync_proxy(apps)
            return dict(self._public(name, rec, False), proxy=wrote, proxy_note=note)

    def token(self, name):
        rec = self._read().get(name)
        return rec["token"] if rec and rec.get("auth", True) else None

    def ensure_all(self, resolve):
        """켜 둔 배포 가운데 죽어 있는 것을 다시 띄운다. `resolve(name)` → (script, cwd) 또는 None(선언이 없어짐 - 건너뜀).
        돌려주는 것: [(이름, 'started' | 오류 글)]. 프록시 설정도 맞춰 쓴다."""
        out = []
        with self._locked() as apps:
            for name, rec in apps.items():
                if not rec.get("on") or self._alive(rec):
                    continue
                where = resolve(name)
                if not where:
                    out.append((name, "app.json 에 server 선언이 없어 다시 띄우지 않았습니다"))
                    continue
                try:
                    self._spawn(name, rec, *where)
                    out.append((name, "started"))
                except DeployError as e:
                    out.append((name, e.message))
            self._sync_proxy(apps)
        return out
