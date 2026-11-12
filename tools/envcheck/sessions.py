"""세션·하네스 계층 관측 검사.

관측 전용. 표준 라이브러리만 쓴다. 설정을 바꾸거나 무엇도 설치하지 않는다.
엔진 v2(2026-11-12)부터 세션은 `fleet_rt` 가 하네스 CLI 로 직접 띄운다. 그래서 여기서 보는 것은
"그 CLI 가 있는가, 설정 파일과 키 파일이 맞는가, 슬롯이 가리키는 모델이 공급자 목록에 있는가" 다.
세션을 실제로 만들지 않는다 - `probe()` 는 `--version` 정도만 부른다 (검사에서는 `AIFLEET_HARNESS=fake`).

옛 외부 세션 도구를 보던 항목들은 그 도구와 함께 걷어냈다.
"""

from __future__ import annotations

from pathlib import Path

# Result = (name: str, status: str, evidence: str)
OK = "OK"
CHANGED = "CHANGED"
UNKNOWN = "UNKNOWN"

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- 공통 도우미


def _rt():
    """`fleet_rt` 를 들인다. `PYTHONPATH=tools` 가 아니면 못 찾을 수 있어 호출부가 UNKNOWN 으로 받는다."""
    import fleet_rt.config as config  # noqa: PLC0415
    import fleet_rt.env as env  # noqa: PLC0415
    import fleet_rt.harness as harness  # noqa: PLC0415
    return config, env, harness


def _slots() -> list[dict]:
    """DB `slots` 행들 (읽기 전용). 못 읽으면 빈 목록. 검사가 갈아끼울 수 있게 함수로 둔다."""
    try:
        import aimem_db  # noqa: PLC0415
        if aimem_db.DB.exists():
            return [r for r in (aimem_db.state_dict().get("slots") or []) if isinstance(r, dict)]
    except Exception:  # noqa: BLE001 - DB 문제로 검사가 죽으면 안 된다
        pass
    return []


# ------------------------------------------------------- 항목 1: 하네스 CLI 점검


def _check_harness(name: str):
    item = f"harness.{name}"
    try:
        _config, _env, harness = _rt()
        res = harness.get(name).probe()
    except Exception as exc:  # noqa: BLE001
        return (item, UNKNOWN, f"점검하지 못했다: {type(exc).__name__}: {exc}")
    if res.ok:
        return (item, OK, f"{res.binary} {res.version or ''}".strip())
    used_by = [r.get("slot") for r in _slots() if r.get("harness") == name]
    note = f"슬롯 {', '.join(map(str, used_by))} 가 이 하네스를 쓴다. " if used_by else "쓰는 슬롯은 없다. "
    # 쓰는 슬롯이 있는데 CLI 가 없으면 기록과 어긋난 것이고, 안 쓰면 알 수 없는 것이다
    return (item, CHANGED if used_by else UNKNOWN, note + (res.detail or "실행 파일을 찾지 못했다"))


# -------------------------------------------------------- 항목 2: fleet.toml 읽기


def _check_fleet_toml():
    name = "fleet_toml"
    try:
        config, _env, _h = _rt()
    except Exception as exc:  # noqa: BLE001
        return (name, UNKNOWN, f"fleet_rt 를 들이지 못했다: {type(exc).__name__}: {exc}")
    try:
        cfg = config.load(ROOT)
    except config.ConfigError as exc:
        return (name, CHANGED, str(exc))
    src = cfg.source or "(파일 없음 - 내장 기본값)"
    return (name, OK, f"{src}: 공급자 {sorted(cfg.providers())} / 하네스 {sorted(cfg.harnesses())}")


# ------------------------------------------------------------- 항목 3: .env 파일


def _check_env_file():
    name = "env_file"
    try:
        _c, env, _h = _rt()
    except Exception as exc:  # noqa: BLE001
        return (name, UNKNOWN, f"fleet_rt 를 들이지 못했다: {type(exc).__name__}: {exc}")
    problem = env.env_problem(ROOT)
    if problem:
        return (name, CHANGED, problem)
    return (name, OK, f"{ROOT / env.ENV_FILE} 있음, 권한 600")


# ------------------------------------------- 항목 4: 슬롯 (하네스, 모델) -> 공급자


def _check_slot_providers():
    name = "slot_providers"
    try:
        config, _e, _h = _rt()
        cfg = config.load(ROOT)
    except Exception as exc:  # noqa: BLE001
        return (name, UNKNOWN, f"fleet.toml 을 읽지 못했다: {type(exc).__name__}: {exc}")
    slots = _slots()
    if not slots:
        return (name, UNKNOWN, "DB slots 를 읽지 못했거나 슬롯이 없다")
    lines, bad = [], []
    for r in slots:
        h, m = r.get("harness"), r.get("model")
        prov = cfg.provider_of(h, m)
        allowed = (cfg.harness(h) or {}).get("providers", [])
        shown = m or f"{(cfg.harness(h) or {}).get('default_model')} (fleet.toml 기본)"
        if prov is None:
            bad.append(f"{r.get('slot')}: {h}/{shown} 의 공급자를 알 수 없다")
        elif prov not in allowed:
            bad.append(f"{r.get('slot')}: {h}/{shown} -> {prov} 는 이 하네스가 받는 공급자 {allowed} 에 없다")
        else:
            lines.append(f"{r.get('slot')}: {h}/{shown} -> {prov}")
    if bad:
        return (name, CHANGED, "\n".join(bad + lines))
    return (name, OK, "\n".join(lines))


# ------------------------------------------------------------------ 진입점


def check() -> list[tuple[str, str, str]]:
    names = ("claude", "codex", "opencode")
    try:
        names = _rt()[2].REAL
    except Exception:  # noqa: BLE001
        pass
    return [_check_harness(n) for n in names] + [_check_fleet_toml(), _check_env_file(), _check_slot_providers()]


if __name__ == "__main__":
    for item_name, status, evidence in check():
        print(f"[{status}] {item_name}")
        for line in evidence.splitlines():
            print(f"    {line}")
        print()
