"""공급자 준비 점검과 키 확인 (설계 3.5). 공급자 자리 세기는 그래프 실행기(`fleet_graph._live_scan`)가 한다."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request


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


def probe(cfg, name, timeout=10):
    """공급자 준비 점검 -> (ok, 한 줄). '공급자가 응답한다' = 서버가 제한 시간 안에 HTTP 로 **무엇이든** 답한다
    (401·403·3xx 포함). 연결 실패·시간 초과만 실패다.

    **키는 어떤 경우에도 보내지 않는다** (2026-11-12 검수): `base_url` 은 작업자도 고칠 수 있는 `fleet.toml` 에서
    오므로, 키를 실어 보내면 그 주소 주인에게 키를 건네게 된다. 키가 있는지는 `key_present` 가 따로 본다.
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
