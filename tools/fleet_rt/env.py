"""함대 설정·비밀 키: 저장소 루트의 `.env` 한 곳.

엔진(세션을 띄울 때)과 모니터(뜰 때)가 이 파일만 읽는다. 다른 도구의 설정 파일은 읽지 않는다.
권한이 600 이 아니면 읽지 않는다 - 키가 든 파일이 남에게 열려 있으면 쓰지 않는 편이 낫다.
"""
import os
import pathlib
import stat

ENV_FILE = ".env"


def load_env(root):
    """`<root>/.env` 를 {이름: 값} 으로. 없거나 권한이 넓으면 빈 dict (까닭은 `env_problem`)."""
    if env_problem(root):
        return {}
    out = {}
    for ln in (pathlib.Path(root) / ENV_FILE).read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        if k and v:
            out[k] = v
    return out


def env_problem(root):
    """`.env` 를 못 쓰는 까닭 한 줄, 문제없으면 None."""
    p = pathlib.Path(root) / ENV_FILE
    try:
        st = p.stat()
    except OSError:
        return f"{ENV_FILE} 이 없습니다 (.env.example 을 복사해 만드십시오)"
    if stat.S_IMODE(st.st_mode) & 0o077:
        return f"{ENV_FILE} 권한이 600 이 아닙니다 (chmod 600 {ENV_FILE})"
    return None


def apply_env(root, environ=None):
    """`.env` 값을 환경에 넣는다. 이미 있는 변수는 덮지 않는다. 넣은 이름 목록을 준다."""
    environ = os.environ if environ is None else environ
    added = []
    for k, v in load_env(root).items():
        if not environ.get(k):
            environ[k] = v
            added.append(k)
    return added
