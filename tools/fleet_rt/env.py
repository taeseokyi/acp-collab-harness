"""함대 설정·비밀 키: 저장소 루트의 `.env` 한 곳.

엔진(세션을 띄울 때)과 모니터(뜰 때)가 이 파일만 읽는다. 다른 도구의 설정 파일은 읽지 않는다.
권한이 600 이 아니면 읽지 않는다 - 키가 든 파일이 남에게 열려 있으면 쓰지 않는 편이 낫다.
"""
import pathlib
import re
import stat

ENV_FILE = ".env"
#: 세션에 `.env` 에서 넘겨줄 수 있는 이름의 꼴 - API 키 이름뿐이다. `BASH_ENV`·`LD_PRELOAD`·`ANTHROPIC_BASE_URL` 같은
#: 실행을 바꾸는 변수는 이 꼴이 아니라 `fleet.toml` 의 `env_key` 에 적혀도 넘어가지 않는다.
SESSION_KEY_RE = re.compile(r"\A[A-Z][A-Z0-9_]*_API_KEY\Z")


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
        k, v = k.strip().removeprefix("export ").strip(), v.strip()   # 셸에서 source 하던 꼴(`export K=v`)도 받는다
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        if k and v:
            out[k] = v
    return out


def session_key_name(root, provider):
    """세션이 `.env` 에서 받을 **단 하나의** 변수 이름 - 그 세션 공급자의 `env_key`. 없거나 꼴이 아니면 None.

    전에는 `.env` 의 모든 변수를 모든 세션에 넣었다 (2026-11-12 검수): 작업자가 `.env` 에 한 줄 더하면
    (`ANTHROPIC_BASE_URL=…`, `BASH_ENV=…`) 다음 관리자 세션의 실행이 바뀌었다. 공급자를 못 정하면 아무것도
    넣지 않는다 - 하네스가 키 없음 오류를 스스로 낸다.
    """
    if not root or not provider:
        return None
    try:
        from . import config  # noqa: PLC0415 - 키 파일만 읽는 호출(모니터)은 설정을 들이지 않는다
        p = config.load(root).provider(str(provider))
    except Exception:  # noqa: BLE001 - 설정이 깨졌으면 넘겨주지 않는다
        return None
    name = (p or {}).get("env_key") if isinstance(p, dict) else None
    return name if isinstance(name, str) and SESSION_KEY_RE.match(name) else None


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
