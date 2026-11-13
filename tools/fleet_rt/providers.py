"""공급자 문지기 (설계 3.5): 공급자별로 동시에 도는 세션 수를 세고, 준비 점검을 한다. 표준 라이브러리만.

`sessions.py` 에 기대지 않는다 - 세션 폴더 규약(`base.py`)만 보고 센다.
"""
from __future__ import annotations

import json
import pathlib
import socket
import urllib.error
import urllib.request


def running_by_provider(sessions_root):
    """지금 도는 **작업자** 세션을 공급자별로. '도는가' 는 감독기(`sessions.state`)의 판정 하나만 쓴다 -
    감독 없이 하네스만 남은 세션도 공급자 자리를 잡고 있으므로 센다. 관리자는 세지 않는다 - `max_concurrent` 는 작업자 자리다."""
    from . import sessions  # noqa: PLC0415 - 설정만 읽는 호출은 감독기를 들이지 않는다
    out = {}
    root = pathlib.Path(sessions_root)
    try:
        dirs = [d for d in root.iterdir() if d.is_dir()]
    except OSError:
        return out
    live = sessions.live_index(root)
    for d in dirs:
        meta = sessions.load_meta(d)
        if not isinstance(meta, dict) or meta.get("role") == "manager" \
                or sessions.state(d, live=live).get("state") != "running":
            continue
        prov = meta.get("provider")
        if prov:
            out[prov] = out.get(prov, 0) + 1
    return out


def has_room(cfg, sessions_root, provider):
    """공급자에 자리가 있나. provider 가 None(공급자를 모름)이면 막지 않는다."""
    if not provider:
        return True
    return running_by_provider(sessions_root).get(provider, 0) < cfg.max_concurrent(provider)


def room(cfg, sessions_root):
    """공급자별 남은 자리 {공급자: 빈 자리 수}."""
    run = running_by_provider(sessions_root)
    return {p: max(0, cfg.max_concurrent(p) - run.get(p, 0)) for p in cfg.providers()}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """넘겨주기를 따라가지 않는다 - 3xx 도 '서버가 응답했다' 로 읽는다 (따라가면 엉뚱한 곳에 요청이 간다)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        return None


def key_present(cfg, name, env):
    """공급자의 키가 `.env` 에 있나 -> (ok, 한 줄). **이름만** 본다 - 값은 읽지도 보이지도 않는다.
    키를 쓰지 않는 공급자(`env_key` 없음, 예: anthropic 은 claude 로그인)는 (True, "키 없이 씀")."""
    p = cfg.provider(name)
    if p is None:
        return False, f"공급자 '{name}' 가 fleet.toml 에 없음"
    key_name = p.get("env_key") or ""
    if not key_name:
        return True, "키 없이 씀"
    if (env or {}).get(key_name):
        return True, f"{key_name} 있음"
    return False, f"{key_name} 환경변수 없음"


def probe(cfg, name, env=None, timeout=10):
    """공급자 준비 점검 -> (ok, 한 줄). '공급자가 응답한다' = 서버가 제한 시간 안에 HTTP 로 **무엇이든** 답한다
    (401·403·3xx 포함). 연결 실패·시간 초과만 실패다.

    **키는 어떤 경우에도 보내지 않는다** (2026-11-12 검수): `base_url` 은 작업자도 고칠 수 있는 `fleet.toml` 에서
    오므로, 키를 실어 보내면 그 주소 주인에게 키를 건네게 된다. 키가 있는지는 `key_present` 가 따로 본다.
    `env` 는 옛 호출을 받으려고 남긴 인자이고 네트워크에는 쓰지 않는다.
    """
    p = cfg.provider(name)
    if p is None:
        return False, f"공급자 '{name}' 가 fleet.toml 에 없음"
    if p.get("probe") != "models":
        return True, "점검 없음"
    base = p.get("base_url")
    if not base or not str(base).lower().startswith(("http://", "https://")):
        return False, "base_url 이 없거나 http(s) 주소가 아님"
    req = urllib.request.Request(str(base).rstrip("/") + "/models", method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            code = getattr(r, "status", None) or r.getcode()
        return True, f"GET /models {code} (응답함)"
    except urllib.error.HTTPError as e:
        try:
            e.close()
        except Exception:  # noqa: BLE001
            pass
        return True, f"GET /models {e.code} (응답함)"
    except (socket.timeout, TimeoutError):
        return False, f"시간 초과 ({timeout}초)"
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return False, f"시간 초과 ({timeout}초)"
        return False, f"연결 실패: {type(reason).__name__}"
    except OSError as e:
        return False, f"연결 실패: {type(e).__name__}"
