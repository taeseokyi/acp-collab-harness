"""함대 검사 공통 설정. 함대 검사 파일은 맨 위에서 `import _fleet_env` 한다.

검사에서 진짜 하네스(codex exec / opencode run / claude -p)가 뜨면 안 된다 - 2026-11-12 에 변이 시험이
띄운 codex 가 고아로 남아 공급자 줄을 49분 잡았다. 이 모듈을 들이면 어댑터 선택이 무조건 `fake` 다.
"""
import os
import pathlib
import sys

os.environ["AIFLEET_HARNESS"] = "fake"

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


_MARKED = []


def marked_pid(sessions_root, sid):
    """그 세션의 살아 있는 감독처럼 보이는 프로세스의 pid (세션 표식을 단 `sleep`). 검사가 끝나면 죽인다.

    감독기는 pid 만으로 '살아 있다' 고 치지 않는다 - 환경에 그 세션·그 루트의 표식이 있어야 한다.
    그래서 '실행 중' 세션을 꾸미는 검사는 이것으로 pid 를 얻는다. 메타에는 `proc_start` 도 적어야 한다
    (`fleet_rt.sessions.proc_start(pid)`).
    """
    import atexit
    import subprocess
    p = subprocess.Popen(["sleep", "300"], env={**os.environ, "AIFLEET_SESSION": str(sid),
                                               "AIFLEET_SESSIONS_ROOT": os.path.abspath(str(sessions_root))})
    if not _MARKED:
        atexit.register(_kill_marked)
    _MARKED.append(p)
    return p.pid


def _kill_marked():
    for p in _MARKED:
        try:
            p.kill()
            p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
