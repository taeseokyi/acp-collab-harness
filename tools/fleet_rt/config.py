"""`fleet.toml` 읽기 - 공급자·하네스 설정 한 곳 (설계 3.6). 표준 라이브러리만.

파일이 없으면 내장 기본값(저장소의 `fleet.toml` 과 같은 내용)을 쓴다. 꼴이 깨졌으면 `ConfigError`.
비밀 키는 여기 없다: `env_key` 는 환경변수 **이름**이고 값은 `env.load_env` 가 `.env` 에서 읽는다.
"""
from __future__ import annotations

import pathlib
import tomllib

FILE = "fleet.toml"

#: 파일이 없을 때의 기본값. `fleet.toml` 과 같게 유지한다 (검사가 둘을 대조한다).
DEFAULTS = {
    "providers": {
        "kisti": {"base_url": "https://aida.kisti.re.kr:10430/v1", "env_key": "KISTI_API_KEY",
                  "max_concurrent": 1, "idle_timeout_sec": 240, "probe": "models", "models": ["kistillm"]},
        "exaone": {"base_url": "https://api.exaone.ai/v1", "env_key": "EXAONE_API_KEY",
                   "max_concurrent": 1, "idle_timeout_sec": 240, "models": ["k-exaone_v2.5"]},
        "openrouter": {"base_url": "https://openrouter.ai/api/v1", "env_key": "OPENROUTER_API_KEY",
                       "max_concurrent": 3, "idle_timeout_sec": 240, "models": ["deepseek/deepseek-v4.1-flash"]},
        "anthropic": {"max_concurrent": 3, "idle_timeout_sec": 600, "models": ["opus", "sonnet", "haiku"]},
    },
    "harness": {
        "claude": {"binary": "claude", "providers": ["anthropic"], "default_model": "sonnet"},
        "codex": {"binary": "codex", "providers": ["kisti", "openrouter"], "default_model": "kisti/kistillm"},
        "opencode": {"binary": "opencode", "providers": ["kisti", "exaone", "openrouter"], "default_model": "kisti/kistillm"},
    },
    "manager": {"mode": "resident"},
}

#: 관리자 운용 방식 (설계 5.9). `resident` 는 관리자 하나가 라운드 내내 산다(지금까지의 방식).
#: `calls` 는 관리자가 계획·판정·마감 세 곳에서만 짧게 뜨고, 그 사이 그래프는 엔진(`fleet_ctl` 의 라운드 구동기)이 돌린다.
MANAGER_MODES = ("resident", "calls")

#: claude CLI 가 받는 모델 별칭·꼴: 이런 이름은 공급자 접두 없이도 anthropic 이다
_CLAUDE_ALIASES = ("opus", "sonnet", "haiku", "fable")
_CLAUDE_PREFIXES = ("claude-", "anthropic/", "claude-cli/")


class ConfigError(Exception):
    """fleet.toml 을 못 읽거나 꼴이 틀림. 메시지는 사람이 읽을 한 줄."""


class Config:
    def __init__(self, data, source=None):
        self.data = data
        self.source = source          # 읽은 파일 경로 (기본값이면 None)

    # ---- 조회
    def providers(self):
        return self.data.get("providers", {})

    def provider(self, name):
        return self.providers().get(name)

    def harnesses(self):
        return self.data.get("harness", {})

    def harness(self, name):
        return self.harnesses().get(name)

    def idle_timeout(self, provider):
        v = (self.provider(provider) or {}).get("idle_timeout_sec")
        return float(v) if v is not None else None

    def max_concurrent(self, provider):
        """모르는 공급자는 1 - 모르면 직렬로 가두는 쪽이 안전하다."""
        v = (self.provider(provider) or {}).get("max_concurrent")
        return int(v) if v is not None else 1

    def provider_of(self, harness, model):
        """슬롯의 (하네스, 모델) -> 공급자 이름. 모르면 None. model 이 None 이면 하네스 기본 모델로 본다."""
        h = self.harness(harness)
        if not model:
            model = (h or {}).get("default_model")
            if not model:
                return None
        model = str(model)
        head, sep, rest = model.partition("/")
        if sep and head in self.providers():
            return head
        low = model.lower()
        if low in _CLAUDE_ALIASES or low.startswith(_CLAUDE_PREFIXES):
            return "anthropic"
        # 접두 없는 모델 이름('kistillm' - codex 설정이 이렇게 쓴다): 그 하네스가 받는 공급자 중 가진 곳
        for p in (h or {}).get("providers", []):
            if model in (self.provider(p) or {}).get("models", []):
                return p
        return None

    def manager_mode(self):
        """`[manager] mode` - `resident`(기본) 또는 `calls`. 표가 없으면 기본값 - 옛 설정 파일도 그대로 돈다."""
        return str((self.data.get("manager") or {}).get("mode") or "resident")

    def models_for(self, harness):
        """모니터 모델 선택기용 목록. claude 는 공급자 접두 없는 별칭, 나머지는 `공급자/모델`."""
        out = []
        for p in (self.harness(harness) or {}).get("providers", []):
            for m in (self.provider(p) or {}).get("models", []):
                key = m if p == "anthropic" else f"{p}/{m}"
                out.append({"key": key, "name": m, "provider": p})
        return out


_cache = {}


def load(root):
    """`<root>/fleet.toml` -> Config. 같은 파일을 mtime 이 같으면 다시 읽지 않는다."""
    path = pathlib.Path(root) / FILE
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return Config(_copy(DEFAULTS))
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{FILE} 꼴이 틀렸습니다: {e}") from e
    except OSError as e:
        raise ConfigError(f"{FILE} 을 읽지 못했습니다: {e}") from e
    _validate(data)
    cfg = Config(data, str(path))
    _cache[path] = (mtime, cfg)
    return cfg


def _copy(d):
    import copy
    return copy.deepcopy(d)


def _validate(data):
    for sec in ("providers", "harness", "manager"):
        if not isinstance(data.get(sec, {}), dict):
            raise ConfigError(f"{FILE}: [{sec}] 가 표가 아닙니다")
    for name, p in data.get("providers", {}).items():
        if not isinstance(p, dict):
            raise ConfigError(f"{FILE}: providers.{name} 가 표가 아닙니다")
        for key in ("max_concurrent", "idle_timeout_sec"):
            if key in p and (isinstance(p[key], bool) or not isinstance(p[key], (int, float))):
                raise ConfigError(f"{FILE}: providers.{name}.{key} 는 숫자여야 합니다")
        if "models" in p and not isinstance(p["models"], list):
            raise ConfigError(f"{FILE}: providers.{name}.models 는 목록이어야 합니다")
    for name, h in data.get("harness", {}).items():
        if not isinstance(h, dict):
            raise ConfigError(f"{FILE}: harness.{name} 가 표가 아닙니다")
        for pn in h.get("providers", []):
            if pn not in data.get("providers", {}):
                raise ConfigError(f"{FILE}: harness.{name} 가 모르는 공급자 '{pn}' 를 가리킵니다")
    mode = data.get("manager", {}).get("mode", "resident")
    if mode not in MANAGER_MODES:
        # 모르는 값을 기본값으로 삼키지 않는다 - 'call' 같은 오타로 사람이 고른 방식과 다르게 돌면 비용이 달라진다
        raise ConfigError(f"{FILE}: manager.mode 는 {' · '.join(MANAGER_MODES)} 가운데 하나여야 합니다 (받은 값 {mode!r})")
