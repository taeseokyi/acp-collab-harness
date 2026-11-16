"""윈도우 쪽 통과 프록시 (`tools/aimem_monitor/host/aimem_proxy.py`) - 설정 파일의 배포 포트를 한 프로세스에서 같이 중계.

- 기본 길(모니터)은 PROXY 줄을 먼저 보내고, 배포 포트는 바이트만 그대로 넘긴다(앱 서버는 그 줄을 모른다)
- 설정에 적힌 포트만 열고, 잇는 곳은 늘 `포트 + 100`. 구간 밖 값·이상한 값은 버린다
- 설정이 바뀌면 몇 초 안에 열고 닫는다. 설정이 깨졌으면 열어 둔 것을 그대로 둔다
"""
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROXY = ROOT / "tools" / "aimem_monitor" / "host" / "aimem_proxy.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROXY.parent))
import aimem_proxy  # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def echo_server(port):
    """받은 첫 덩어리를 그대로 돌려주는 서버. 닫는 함수를 돌려준다."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)

    def loop():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            with c:
                c.settimeout(2)
                try:
                    c.sendall(b"got:" + c.recv(4096))
                except OSError:
                    pass
    threading.Thread(target=loop, daemon=True).start()
    return srv.close


def ask(port, data=b"hello"):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as c:
        c.sendall(data)
        c.settimeout(3)
        return c.recv(4096)


def wait_for(fn, sec=8.0):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        try:
            if fn():
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


class ReadPorts(unittest.TestCase):
    def test_only_ints_in_range(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = pathlib.Path(t) / "ports.json"
            self.assertEqual(aimem_proxy.read_ports(cfg), set())                       # 없으면 빈 것
            cfg.write_text(json.dumps({"ports": [18810, 18899, 18900, 18809, 80, "18811", True, 18812.0, None]}))
            self.assertEqual(aimem_proxy.read_ports(cfg), {18810, 18899})
            for broken in ("{", "[]", json.dumps({"ports": "18810"}), json.dumps({"other": 1})):
                cfg.write_text(broken)
                self.assertIsNone(aimem_proxy.read_ports(cfg), broken)                 # 깨졌으면 모름 = 그대로 둠


class ProxyProcess(unittest.TestCase):
    def test_app_ports_follow_the_config_file(self):
        # 서로 100 떨어진 빈 포트 쌍 - 운영 배포(18810~)와 겹치지 않게 다른 구간을 쓴다
        first = 30000 + free_port() % 20000
        listen, target = free_port(), free_port()
        with tempfile.TemporaryDirectory() as t:
            cfg = pathlib.Path(t) / "ports.json"
            cfg.write_text(json.dumps({"ports": [first, first + 99]}))                  # 뒤의 것은 구간 밖
            closers = [echo_server(target), echo_server(first + 100)]
            script = shutil.copy(PROXY, t)          # 로그가 스크립트 옆에 쌓인다 - 저장소가 아니라 임시 폴더에
            proc = subprocess.Popen([sys.executable, str(script), "--listen", str(listen), "--target", str(target),
                                     "--config", str(cfg), "--app-first", str(first)], cwd=t)
            try:
                self.assertTrue(wait_for(lambda: ask(listen).startswith(b"got:PROXY TCP4 127.0.0.1 ")), "기본 길")
                self.assertTrue(wait_for(lambda: ask(first) == b"got:hello"), "배포 포트는 바이트 그대로")
                with self.assertRaises(OSError):
                    ask(first + 99)
                cfg.write_text("{ 깨짐")
                time.sleep(aimem_proxy.CONFIG_POLL_SEC + 1)
                self.assertEqual(ask(first), b"got:hello")                             # 깨진 설정은 닫지 않는다
                cfg.write_text(json.dumps({"ports": []}))

                def closed():
                    try:
                        ask(first)
                    except OSError:
                        return True
                    return False
                self.assertTrue(wait_for(closed), "설정에서 빠지면 닫는다")
                self.assertTrue(ask(listen).startswith(b"got:PROXY"))                  # 기본 길은 그대로
            finally:
                proc.terminate()
                proc.wait(5)
                for c in closers:
                    c()


if __name__ == "__main__":
    unittest.main()
