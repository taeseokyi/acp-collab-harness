"""검증 명령(그래프 노드의 `verify`)을 가두는 울타리 - bubblewrap 으로.

까닭: 그래프 JSON(`.aimem/graph/`)은 작업자가 쓸 수 있는 곳에 있다. 실행기는 `verify` 를 제 권한·제 환경으로
돌리므로, 작업자가 검증 명령을 심으면 엔진을 거쳐 저장소 밖에 쓰거나(codex 작업자는 제 울타리로 저장소에 갇혀 있다)
모니터가 띄운 실행기의 환경에 든 공급자 키를 읽을 수 있었다. 목표는 하나다:
**엔진이 검증 명령에 작업자가 이미 가진 것보다 많은 것을 주지 않는다.**

울타리 안에서 되는 것 / 안 되는 것:
  - `/` 전체는 읽기 전용, 저장소와 `/tmp` 만 쓰기. 저장소의 `.git` 은 읽기 전용(작업자 울타리와 같다 - 훅을 심어
    사람이 다음에 git 을 칠 때 돌게 하는 길을 막는다)
  - `/tmp` 는 **진짜** `/tmp` 를 묶는다 - 작업자가 `/tmp` 에 써 둔 것을 검증이 읽는 그래프가 실제로 있다
    (`python3 /tmp/r11-host-check.py`), 그리고 codex 작업자의 울타리도 `/tmp` 쓰기를 준다. 더 주는 것이 아니다
  - 저장소의 `.env` 는 `/dev/null` 로 덮여 읽히지 않고, `.aimem/tls/`(모니터 TLS 키·접속 토큰)는 빈 tmpfs 로 덮인다
  - 새 pid 이름공간·새 세션 - 검증이 함대 프로세스(실행기·감독·관리자)에 신호를 보낼 수 없다
  - `/dev` 는 새로, `/dev/shm` 은 쓰기(크로미움이 쓴다), `/proc` 은 새 이름공간 것
  - 네트워크는 그대로 - 검사가 루프백 서버와 Playwright 를 쓴다
  - `--die-with-parent` - 실행기가 죽거나 시간 초과로 bwrap 을 죽이면 안의 것이 모두 같이 끝난다

막지 않는 것(작업자도 이미 가진 것들): 네트워크(밖으로 보내기 포함), 저장소 밖 파일 **읽기**(홈의 다른 설정 파일 포함 -
`/` 가 읽기 전용으로 보일 뿐이다), 진짜 `/tmp` 안의 남의 파일 읽고 쓰기, 저장소 안 나머지(`.aimem/aimem.db` 등) 쓰기.

bwrap 이 없거나 이 기계에서 안 돌면(사용자 이름공간이 막힌 커널 등) 원래 명령을 그대로 돌려주고 까닭을 note 로 준다 -
환경 청소(`clean_env`)는 그때도 한다. 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

from . import env as rt_env
from .base import service_env

#: 환경에서 늘 빼는 이름 꼴 - `.env` 밖(사람의 셸·모니터)에서 들어온 키도 넘기지 않는다.
SECRET_NAME_RE = re.compile(r".*_(API_KEY|TOKEN|SECRET)\Z", re.IGNORECASE)

_PROBE = {}          # bwrap 경로 -> (되나, 까닭). 프로세스마다 한 번 실제로 돌려 본다


def bwrap_path():
    return shutil.which("bwrap")


def available():
    """(되나, 까닭). 있는지만 보지 않고 아무것도 안 하는 울타리를 **실제로 한 번** 돌려 본다 - 설치돼 있어도
    사용자 이름공간이 막혀 있으면 안 돈다. 결과는 프로세스 안에서 다시 쓴다."""
    exe = bwrap_path()
    if not exe:
        return False, "bwrap 이 없습니다"
    if exe in _PROBE:
        return _PROBE[exe]
    try:
        r = subprocess.run([exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--unshare-pid",
                            "--new-session", "--die-with-parent", "true"],
                           capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
        res = (True, "") if r.returncode == 0 else \
            (False, f"bwrap 시험 실행 rc={r.returncode}: {(r.stderr or '').strip()[:200]}")
    except (OSError, subprocess.SubprocessError) as e:
        res = (False, f"bwrap 시험 실행 실패: {type(e).__name__}")
    _PROBE[exe] = res
    return res


def wrap(argv, repo, *, extra_rw=()):
    """`argv` 를 울타리 안에서 돌리는 명령줄과 한 줄 설명. (argv2, note)

    울타리를 못 쓰면 `argv` 를 그대로, note 에 까닭을 준다(호출자가 '갇히지 않음' 을 남긴다). 쓰면 note 는 빈 글.
    `repo` 는 그 순간의 저장소 루트(검사가 갈아 끼운 ROOT 도) - 쓰기와 작업 폴더가 거기다.
    """
    ok, why = available()
    if not ok:
        return list(argv), f"검증이 울타리 없이 돕니다 ({why})"
    repo = pathlib.Path(repo).resolve()
    a = [bwrap_path(),
         "--ro-bind", "/", "/",
         "--dev", "/dev",
         "--proc", "/proc",
         "--tmpfs", "/dev/shm",
         # 진짜 /tmp - 저장소가 /tmp 아래여도(검사) 아래 저장소 묶기가 같은 곳을 다시 묶을 뿐이다
         "--bind", "/tmp", "/tmp",
         "--bind", str(repo), str(repo)]
    git = repo / ".git"
    if git.exists():
        a += ["--ro-bind", str(git), str(git)]
    for p in extra_rw:
        p = pathlib.Path(p).resolve()
        a += ["--bind", str(p), str(p)]
    # 가리기는 쓰기 묶기 **뒤에** - 앞에 두면 뒤의 묶기가 덮어 다시 보인다
    dotenv = repo / rt_env.ENV_FILE
    if dotenv.is_file() and not dotenv.is_symlink():
        a += ["--ro-bind", "/dev/null", str(dotenv)]
    tls = repo / ".aimem" / "tls"
    if tls.is_dir() and not tls.is_symlink():
        a += ["--tmpfs", str(tls)]
    a += ["--chdir", str(repo), "--unshare-pid", "--new-session", "--die-with-parent", "--"]
    return a + list(argv), ""


def env_names(repo):
    """저장소 `.env` 에 적힌 변수 **이름들** (값은 버린다). 못 읽으면 빈 집합."""
    try:
        return set(rt_env.load_env(repo))
    except (OSError, UnicodeDecodeError, ValueError):
        return set()


def clean_env(environ, repo):
    """검증 명령의 환경: 세션 표식(`AIFLEET_SESSION` 등)·`.env` 에 적힌 이름·`*_API_KEY|*_TOKEN|*_SECRET` 를 뺀다.

    PATH·HOME·LANG 등 나머지는 둔다 - 검증이 python·node·Playwright 를 찾아야 한다.
    """
    env = service_env(environ)
    drop = env_names(repo)
    return {k: v for k, v in env.items() if k not in drop and not SECRET_NAME_RE.match(k)}
