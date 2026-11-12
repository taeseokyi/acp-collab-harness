"""어댑터 고르기. `get("codex")` 처럼 이름으로 얻는다.

`AIFLEET_HARNESS=fake` 면 무엇을 청하든 `fake` 를 준다 - 검사·변이 시험에서 진짜 하네스가
뜨는 일을 구조적으로 막는 장치다 (`tests/_fleet_env.py` 가 넣는다).
"""
import importlib
import os

from ..base import ENV_FORCE_HARNESS

NAMES = ("claude", "codex", "opencode", "fake")
REAL = ("claude", "codex", "opencode")


def get(name):
    if os.environ.get(ENV_FORCE_HARNESS) == "fake":
        name = "fake"
    if name not in NAMES:
        raise ValueError(f"알 수 없는 하네스: {name!r}")
    return importlib.import_module(f"{__name__}.{name}").ADAPTER
