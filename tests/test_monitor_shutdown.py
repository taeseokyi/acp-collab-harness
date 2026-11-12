import inspect
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _wait_health(port, timeout=20.0):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=1.0
            ) as response:
                if response.status == 200:
                    return True
        except Exception as exc:  # 연결 거부 등은 아직 준비 안 된 것
            last_error = exc
        time.sleep(0.1)
    return False


class MonitorShutdownTest(unittest.TestCase):
    def test_sigterm_flushes_denied_audit(self):
        root = tempfile.mkdtemp()
        pathlib.Path(root, ".aimem").mkdir()
        port = _free_port()
        code = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(TOOLS)!r})
            from aimem_monitor import server
            server._denied_cap_skipped = 5
            print("READY", flush=True)
            server.serve(host="127.0.0.1", port={port}, root={root!r}, auth=False)
        """)
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = ""
        errors = ""
        try:
            ready = _wait_health(port)
            self.assertTrue(ready, msg=f"health 200 이 되지 않았습니다. stderr={errors}")
            proc.send_signal(signal.SIGTERM)
            output, errors = proc.communicate(timeout=20)
            self.assertEqual(
                proc.returncode,
                0,
                msg=f"SIGTERM 뒤 rc={proc.returncode}\nstdout:\n{output}\nstderr:\n{errors}",
            )
            log_path = pathlib.Path(root, ".aimem", "access.log")
            self.assertTrue(
                log_path.exists(),
                msg=f"{log_path} 가 없습니다.\nstdout:\n{output}\nstderr:\n{errors}",
            )
            log_text = log_path.read_text(encoding="utf-8")
            dropped = [
                line
                for line in log_text.splitlines()
                if len(line.split("\t")) > 1 and line.split("\t")[1] == "audit-dropped"
            ]
            self.assertTrue(
                dropped,
                msg=f"audit-dropped 줄이 없습니다.\nlog:\n{log_text}\nstdout:\n{output}\nstderr:\n{errors}",
            )
            self.assertTrue(
                any("5" in line for line in dropped),
                msg=f"audit-dropped 줄에 5 가 없습니다.\nlog:\n{log_text}\nstdout:\n{output}\nstderr:\n{errors}",
            )
        finally:
            if proc.poll() is None:
                proc.kill()
                output, errors = proc.communicate(timeout=10)
            shutil.rmtree(root, ignore_errors=True)

    def test_serve_restores_sigterm_handler(self):
        root = tempfile.mkdtemp()
        pathlib.Path(root, ".aimem").mkdir()
        port = _free_port()
        code = textwrap.dedent(f"""
            import signal
            import sys
            sys.path.insert(0, {str(TOOLS)!r})
            from aimem_monitor import server
            print("BEFORE\\t" + repr(signal.getsignal(signal.SIGTERM)), flush=True)
            server.serve(host="127.0.0.1", port={port}, root={root!r}, once=True, auth=False)
            print("AFTER\\t" + repr(signal.getsignal(signal.SIGTERM)), flush=True)
        """)
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = ""
        errors = ""
        before_line = ""
        try:
            before_line = proc.stdout.readline()
            self.assertTrue(
                before_line.startswith("BEFORE\t"),
                msg=f"BEFORE 줄이 없습니다. 읽은 줄={before_line!r}",
            )
            for _ in range(20):
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/health", timeout=1.0
                    ).close()
                    break
                except Exception as exc:
                    refused = isinstance(exc, ConnectionRefusedError) or (
                        isinstance(exc, urllib.error.URLError)
                        and isinstance(getattr(exc, "reason", None), ConnectionRefusedError)
                    )
                    if refused:
                        time.sleep(0.1)
                        continue
                    break
            rest_output, errors = proc.communicate(timeout=20)
            output = before_line + rest_output
            self.assertEqual(
                proc.returncode,
                0,
                msg=f"serve(once=True) 뒤 rc={proc.returncode}\nstdout:\n{output}\nstderr:\n{errors}",
            )
            before = [line.split("\t", 1)[1] for line in output.splitlines() if line.startswith("BEFORE\t")]
            after = [line.split("\t", 1)[1] for line in output.splitlines() if line.startswith("AFTER\t")]
            self.assertTrue(before, msg=f"BEFORE 줄이 없습니다.\nstdout:\n{output}\nstderr:\n{errors}")
            self.assertTrue(after, msg=f"AFTER 줄이 없습니다.\nstdout:\n{output}\nstderr:\n{errors}")
            self.assertIn(
                "SIG_DFL",
                before[0],
                msg=f"serve 전 처리기가 SIG_DFL 이 아닙니다: {before[0]}",
            )
            self.assertIn(
                "SIG_DFL",
                after[0],
                msg=f"serve 뒤 처리기가 SIG_DFL 로 돌아오지 않았습니다: {after[0]}\nstdout:\n{output}\nstderr:\n{errors}",
            )
            self.assertNotIn(
                "_sigterm_interrupt",
                after[0],
                msg=f"_sigterm_interrupt 가 남아 있습니다: {after[0]}",
            )
            self.assertEqual(
                before[0],
                after[0],
                msg=f"serve 전후 처리기 값이 다릅니다: BEFORE={before[0]} AFTER={after[0]}\nstdout:\n{output}\nstderr:\n{errors}",
            )
        finally:
            if proc.poll() is None:
                proc.kill()
                output, errors = proc.communicate(timeout=10)
            shutil.rmtree(root, ignore_errors=True)

    def test_sigterm_handler_is_installed_right_before_the_serve_loop(self):
        from aimem_monitor import server

        lines = inspect.getsource(server.serve).splitlines()
        signal_lines = [
            i
            for i, line in enumerate(lines)
            if "signal.signal(signal.SIGTERM" in line and "_sigterm_interrupt" in line
        ]
        self.assertEqual(
            len(signal_lines),
            1,
            msg=f"SIGTERM 설치 줄이 정확히 하나가 아닙니다: {signal_lines}",
        )
        signal_index = signal_lines[0]
        loop_lines = [
            i
            for i, line in enumerate(lines)
            if "handle_request()" in line or "serve_forever()" in line
        ]
        self.assertTrue(loop_lines, msg="handle_request()/serve_forever() 줄이 없습니다.")
        loop_index = loop_lines[0]
        self.assertLess(
            signal_index,
            loop_index,
            msg=f"SIGTERM 설치({signal_index})가 serve 루프({loop_index}) 뒤에 있습니다.",
        )
        between = lines[signal_index + 1 : loop_index]
        self.assertFalse(
            [line for line in between if "log_line(" in line],
            msg="SIGTERM 설치와 serve 루프 사이에 log_line 이 있습니다.",
        )
        before_loop = [i for i in range(loop_index) if "log_line(" in lines[i]]
        self.assertTrue(before_loop, msg="serve 루프 앞에 log_line 이 하나도 없습니다.")
        last_log_before_loop = before_loop[-1]
        self.assertGreater(
            signal_index,
            last_log_before_loop,
            msg=f"SIGTERM 설치({signal_index})가 마지막 log_line({last_log_before_loop})보다 앞에 있습니다.",
        )


if __name__ == "__main__":
    unittest.main()
