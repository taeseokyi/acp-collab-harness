"""시간대 하나로 통일: `fleet.toml` `[time] zone` (기본은 `config.DEFAULT_TIME_ZONE`).

엔진 프로세스가 뜰 때 `apply(root)` 를 한 번 부르면 이 프로세스와 그 자식(감독·하네스·작업자의 명령)이 모두
같은 시간대로 시각을 적는다 - `datetime.now()`·로그·`date` 가 기계 설정과 상관없이 같은 시계를 쓴다.
이미 같은 값이면 아무것도 하지 않는다. 이름이 틀리면 건드리지 않는다(기계 시간대 그대로).
"""
import os
import time


def zone_name(root):
    try:
        from . import config  # noqa: PLC0415
        return config.load(root).time_zone()
    except Exception:  # noqa: BLE001 - 설정이 깨져도 시간 때문에 엔진이 멈추면 안 된다
        from .config import DEFAULT_TIME_ZONE  # noqa: PLC0415
        return DEFAULT_TIME_ZONE


def apply(root):
    """`TZ` 를 설정 시간대로. 돌려주는 값은 적용한 이름(못 했으면 None)."""
    name = zone_name(root)
    try:
        import zoneinfo  # noqa: PLC0415
        zoneinfo.ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return None
    if os.environ.get("TZ") != name:
        os.environ["TZ"] = name
        try:
            time.tzset()
        except AttributeError:      # tzset 이 없는 곳(윈도)은 환경변수만
            pass
    return name
