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
    """지금 도는 세션을 공급자별로. '도는가' 는 감독기(`sessions.state`)의 판정 하나만 쓴다 -
    감독 없이 하네스만 남은 세션도 공급자 자리를 잡고 있으므로 센다."""
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
        if not isinstance(meta, dict) or sessions.state(d, live=live).get("state") != "running":
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


def probe(cfg, name, env, timeout=10):
    """공급자 준비 점검 -> (ok, 한 줄). 키 값은 어떤 경우에도 detail 에 넣지 않는다."""
    p = cfg.provider(name)
    if p is None:
        return False, f"공급자 '{name}' 가 fleet.toml 에 없음"
    if p.get("probe") != "models":
        return True, "점검 없음"
    key_name = p.get("env_key") or ""
    key = (env or {}).get(key_name)
    if not key:
        return False, f"{key_name or 'env_key'} 환경변수 없음"
    base = p.get("base_url")
    if not base:
        return False, "base_url 이 없음"
    req = urllib.request.Request(base.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = getattr(r, "status", None) or r.getcode()
        if 200 <= int(code) < 300:
            return True, f"GET /models {code}"
        return False, f"GET /models {code}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (socket.timeout, TimeoutError):
        return False, f"시간 초과 ({timeout}초)"
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return False, f"시간 초과 ({timeout}초)"
        return False, f"연결 실패: {type(reason).__name__}"
    except OSError as e:
        return False, f"연결 실패: {type(e).__name__}"
