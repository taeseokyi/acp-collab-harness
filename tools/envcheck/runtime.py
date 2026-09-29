"""envcheck - 실행 환경 계층 (슬롯 S2).

관측 전용. 설정을 바꾸거나 무언가를 설치하지 않는다. 표준 라이브러리만 쓴다.

판정 근거는 OpenClaw 런타임에서만 취한다 - 설치된 `dist/**`, 같은 경로의
`docs/**`, `~/.openclaw/openclaw.json` 같은 런타임 설정, 그리고 실제 실행 결과.
우리 저장소와 워크스페이스는 "무엇을 검사할지" 정하는 데만 쓰였고 판정에는 쓰지 않는다.

노출하는 것은 `check()` 하나뿐이다. 결과는 3튜플 `(name, status, evidence)` 이고
status 는 `OK` / `CHANGED` / `UNKNOWN` 중 하나다.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from importlib.util import find_spec
from pathlib import Path

Result = tuple[str, str, str]

OK = "OK"
CHANGED = "CHANGED"
UNKNOWN = "UNKNOWN"

CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"

# 설치 위치는 환경마다 다르다. 실물로 찾고, 못 찾으면 그 항목은 UNKNOWN 이다.
_ROOT_CANDIDATES = (
    Path.home() / ".local/share/pnpm/global/5/node_modules/openclaw",
    Path("/usr/local/lib/node_modules/openclaw"),
    Path.home() / ".npm-global/lib/node_modules/openclaw",
)


# --------------------------------------------------------------------------
# 공통 도우미
# --------------------------------------------------------------------------


def _openclaw_root() -> Path | None:
    """설치된 OpenClaw 패키지 루트. `openclaw` 실행파일을 따라가는 것을 우선한다."""
    exe = shutil.which("openclaw")
    if exe:
        target = Path(exe).resolve()
        for parent in target.parents:
            if (parent / "dist").is_dir() and (parent / "package.json").is_file():
                return parent
    for candidate in _ROOT_CANDIDATES:
        if (candidate / "dist").is_dir():
            return candidate
    return None


def _load_config() -> tuple[dict, list[str]]:
    """런타임 설정과 그 원본 줄 목록. 없으면 `({}, [])`."""
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        return json.loads(text), text.splitlines()
    except (OSError, ValueError):
        return {}, []


def _config_line(lines: list[str], key: str, value: str | None = None) -> str:
    """설정 원본에서 `key`(+선택적 value)가 처음 나오는 줄을 `경로:행` 으로 인용."""
    for number, line in enumerate(lines, start=1):
        if f'"{key}"' in line and (value is None or f'"{value}"' in line):
            excerpt = line.strip()
            # 값이 다음 줄로 넘어가는 배열/객체면 한 줄 더 붙여야 근거가 된다.
            if excerpt.endswith(("[", "{")) and number < len(lines):
                excerpt += " " + lines[number].strip()
            return f"{CONFIG_PATH}:{number} {excerpt}"
    return f"{CONFIG_PATH}: (`{key}` 없음 - 기본값 적용)"


def _doc_line(root: Path, relative: str, needle: str) -> str | None:
    """문서에서 `needle` 이 들어간 첫 줄을 `경로:행 발췌` 로 인용."""
    path = root / "docs" / relative
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for number, line in enumerate(lines, start=1):
        position = line.find(needle)
        if position < 0:
            continue
        # 긴 줄은 찾은 문구를 중심으로 잘라야 인용이 근거 구실을 한다.
        start = max(0, position - 60)
        end = min(len(line), position + len(needle) + 60)
        excerpt = ("..." if start else "") + line[start:end].strip() + ("..." if end < len(line) else "")
        return f"{path}:{number} {excerpt}"
    return None


def _dig(mapping: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(mapping, dict):
            return None
        mapping = mapping.get(key)
    return mapping


# --------------------------------------------------------------------------
# 항목 1 - 파이썬 실행 환경이 conda `openclaw` 인가
# --------------------------------------------------------------------------

REQUIRED_PACKAGES = ("bs4", "requests")


def _check_python_env() -> Result:
    name = "python_env"
    config, lines = _load_config()

    # 기대값을 우리 기록이 아니라 런타임 설정에서 끌어온다.
    # `tools.exec.pathPrepend` 가 팬/exec 의 PATH 앞단을 고정하는 실제 장치다.
    prepend = _dig(config, "tools", "exec", "pathPrepend")
    prepend = [p for p in prepend if isinstance(p, str)] if isinstance(prepend, list) else []
    pinned = [p for p in prepend if "/envs/" in p]

    executable = Path(sys.executable).resolve()
    version = platform.python_version()
    resolved_python3 = shutil.which("python3")
    resolved_python3 = str(Path(resolved_python3).resolve()) if resolved_python3 else "(없음)"

    missing = [pkg for pkg in REQUIRED_PACKAGES if find_spec(pkg) is None]

    facts = [
        f"sys.executable = {executable}",
        f"python 버전 = {version}",
        f"which python3 -> {resolved_python3}",
        f"CONDA_PREFIX = {os.environ.get('CONDA_PREFIX', '(미설정)')}",
        f"패키지 가용: " + ", ".join(
            f"{pkg}={'있음' if find_spec(pkg) else '없음'}" for pkg in REQUIRED_PACKAGES
        ),
        _config_line(lines, "pathPrepend"),
    ]

    if not pinned:
        facts.append(
            "런타임 설정에 `/envs/` 를 담은 pathPrepend 항목이 없어 "
            "기대 환경을 런타임 근거로 특정할 수 없다."
        )
        return name, UNKNOWN, "\n".join(facts)

    env_root = Path(pinned[0]).parent  # .../envs/<name>/bin -> .../envs/<name>
    facts.insert(0, f"설정이 고정한 환경 = {env_root}")

    problems: list[str] = []
    if env_root not in executable.parents:
        problems.append(f"실행 인터프리터가 고정 환경 밖이다 ({executable})")
    if str(executable).startswith("/usr/bin/"):
        problems.append("시스템 python 이 잡혔다 (/usr/bin)")
    if not str(resolved_python3).startswith(str(env_root)):
        problems.append(f"PATH 상의 python3 가 고정 환경 밖을 가리킨다 ({resolved_python3})")
    if not version.startswith("3.11."):
        problems.append(f"버전이 3.11.x 가 아니다 ({version})")
    if missing:
        problems.append(f"작업이 의존하는 패키지 누락: {', '.join(missing)}")

    if problems:
        return name, CHANGED, "\n".join(facts + ["어긋남: " + "; ".join(problems)])
    return name, OK, "\n".join(facts + ["고정 환경·버전·패키지 모두 기대와 일치."])


# --------------------------------------------------------------------------
# 항목 2 - WSL DNS 첫 조회 실패가 여전한가
# --------------------------------------------------------------------------

_PROBE_HOSTS = ("one.one.one.one", "dns.google", "example.com")
_LOOKUP_TIMEOUT = 6.0


def _resolve_once(host: str) -> tuple[bool, str]:
    """getaddrinfo 1회. 리졸버 자체는 타임아웃을 주지 못하므로 스레드로 상한을 건다."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(socket.getaddrinfo, host, 443, socket.AF_INET, socket.SOCK_STREAM)
        try:
            infos = future.result(timeout=_LOOKUP_TIMEOUT)
        except TimeoutError:
            return False, f"{_LOOKUP_TIMEOUT:.0f}초 내 응답 없음"
        except socket.gaierror as err:
            return False, f"gaierror: {err}"
        except OSError as err:  # noqa: BLE001 - 관측기이므로 삼키고 기록만 한다
            return False, f"{type(err).__name__}: {err}"
    return True, infos[0][4][0]


def _check_wsl_dns() -> Result:
    name = "wsl_dns_first_lookup"
    release = platform.uname().release

    if "microsoft" not in release.lower():
        return name, UNKNOWN, f"WSL 이 아니다 (uname release = {release}). 이 검사는 해당 없음."

    facts = [f"uname release = {release}"]
    try:
        head = Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="replace").splitlines()
        generated = any("generated by WSL" in line or "auto-generated" in line for line in head[:5])
        nameservers = [line.strip() for line in head if line.strip().startswith("nameserver")]
        facts.append(f"/etc/resolv.conf 자동생성 표시 = {generated}, {'; '.join(nameservers) or '(nameserver 없음)'}")
    except OSError as err:
        facts.append(f"/etc/resolv.conf 읽기 실패: {err}")

    first_failures = 0
    recovered = 0
    for host in _PROBE_HOSTS:
        ok, detail = _resolve_once(host)
        if ok:
            facts.append(f"{host}: 1차 성공 -> {detail}")
            continue
        first_failures += 1
        facts.append(f"{host}: 1차 실패 ({detail})")
        ok2, detail2 = _resolve_once(host)
        if ok2:
            recovered += 1
            facts.append(f"{host}: 재시도 성공 -> {detail2}")
        else:
            facts.append(f"{host}: 재시도도 실패 ({detail2})")

    facts.append(
        f"집계: 조회 대상 {len(_PROBE_HOSTS)}개, 1차 실패 {first_failures}건, "
        f"그 중 재시도 회복 {recovered}건 (호스트당 최대 2회, 총 최대 {len(_PROBE_HOSTS) * 2}회)"
    )

    if first_failures == 0:
        facts.append(
            "판정 근거: 기록이 말하는 것은 '간헐적' 실패다. 전부 1차 성공한 것은 "
            "부재의 증거가 아니라 이번 표본에서 재현되지 않았다는 뜻일 뿐이므로 UNKNOWN 이다."
        )
        return name, UNKNOWN, "\n".join(facts)

    if first_failures == recovered:
        facts.append("판정 근거: 1차 실패가 관측됐고 전부 재시도로 통과했다 - 기록과 같은 모양이다.")
        return name, OK, "\n".join(facts)

    facts.append(
        "판정 근거: 재시도로 회복되지 않은 실패가 있다. "
        "기록('재시도하면 통과한다')보다 상태가 나쁘므로 기록을 고쳐야 한다."
    )
    return name, CHANGED, "\n".join(facts)


# --------------------------------------------------------------------------
# 항목 3 - 작업자의 쓰기를 막는 기전이 실제로 무엇인가
# --------------------------------------------------------------------------


def _check_write_gate() -> Result:
    name = "worker_write_gate"
    config, lines = _load_config()
    if not config:
        return name, UNKNOWN, f"{CONFIG_PATH} 를 읽지 못했다."

    root = _openclaw_root()
    if root is None:
        return name, UNKNOWN, "설치된 OpenClaw 패키지(dist/docs)를 찾지 못해 값의 의미를 확인할 수 없다."

    exec_cfg = _dig(config, "tools", "exec")
    exec_cfg = exec_cfg if isinstance(exec_cfg, dict) else {}
    mode = exec_cfg.get("mode")
    security = exec_cfg.get("security")
    ask = exec_cfg.get("ask")
    elevated_default = _dig(config, "agents", "defaults", "elevatedDefault")
    elevated_enabled = _dig(config, "tools", "elevated", "enabled")
    acpx_mode = _dig(config, "plugins", "entries", "acpx", "config", "permissionMode")

    facts = [
        "-- 실효 설정값 (런타임 설정에서 직접 읽음) --",
        f"tools.exec.mode = {mode!r}, tools.exec.security = {security!r}, tools.exec.ask = {ask!r}"
        + (" (ask 미설정 -> 문서상 기본 'off')" if ask is None else ""),
        _config_line(lines, "security", "full") if security == "full" else _config_line(lines, "security"),
        f"agents.defaults.elevatedDefault = {elevated_default!r}",
        _config_line(lines, "elevatedDefault"),
        f"tools.elevated.enabled = {elevated_enabled!r}",
        f"plugins.entries.acpx.config.permissionMode = {acpx_mode!r}",
    ]

    citations = {
        "exec.mode full 의 의미": _doc_line(
            root, "tools/exec-approvals.md", "Run host exec without approval prompts"
        ),
        "exec.security full 의 의미": _doc_line(
            root, "tools/exec-approvals.md", "allow everything (equivalent to elevated)"
        ),
        "exec.ask 기본값": _doc_line(root, "tools/exec-approvals.md", "Default is `off`."),
        "security/ask 쌍은 은퇴 표면": _doc_line(
            root, "tools/exec-approvals.md", "retired persisted"
        ),
        "elevatedDefault full 이 건너뛰는 것": _doc_line(
            root, "tools/elevated.md", "exec approvals are skipped"
        ),
        "elevated 전역 게이트": _doc_line(root, "tools/elevated.md", "tools.elevated.enabled"),
        "서브에이전트 권한 상속": _doc_line(
            root, "tools/subagents.md", "inherits the requester's effective tool-policy ceiling"
        ),
    }

    facts.append("-- 그 값이 실제로 무엇을 건너뛰게 하는지 (설치된 문서) --")
    missing_docs = []
    for label, citation in citations.items():
        if citation is None:
            missing_docs.append(label)
            facts.append(f"{label}: (문서에서 찾지 못함)")
        else:
            facts.append(f"{label}: {citation}")

    if missing_docs:
        facts.append(
            "판정 근거: 값의 의미를 문서로 확인하지 못한 항목이 있어 단정하지 않는다 - "
            + ", ".join(missing_docs)
        )
        return name, UNKNOWN, "\n".join(facts)

    permissive_exec = mode == "full" or (security == "full" and ask in (None, "off"))
    permissive_elevated = elevated_default == "full" and elevated_enabled is True

    facts.append("-- 판정 --")
    if permissive_exec and permissive_elevated:
        facts.append(
            "실효 기전은 `tools.exec`(승인 프롬프트 없이 호스트 exec 실행)와 "
            "`agents.defaults.elevatedDefault: full`(exec 승인 생략)이다. "
            "서브에이전트는 호출자의 실효 도구 정책 상한을 물려받으므로 작업자 쪽에서도 같다. "
            "즉 작업자의 쓰기를 막는 기술적 장치는 없다."
        )
        facts.append(
            f"`acpx.permissionMode`({acpx_mode!r})는 설정에 남아 있으나 ACP 플러그인 경로의 값이다. "
            "위 exec/elevated 두 값만으로 이미 승인이 생략되므로, acpx 를 잠가도 이 경로는 닫히지 않는다. "
            "(acpx 가 네이티브 슬롯에 관여하지 않는다는 점까지는 이 검사가 증명하지 않는다 - "
            "증명한 것은 exec/elevated 가 단독으로 충분하다는 것이다.)"
        )
        return name, OK, "\n".join(facts)

    facts.append(
        "기록은 '기술적으로 막히지 않는다'인데 실효 값이 그렇지 않다: "
        f"exec 완전허용={permissive_exec}, elevated 완전허용={permissive_elevated}. 기록을 고쳐야 한다."
    )
    return name, CHANGED, "\n".join(facts)


# --------------------------------------------------------------------------


def check() -> list[Result]:
    """실행 환경 계층 검사 3종. 관측만 하고 아무것도 바꾸지 않는다."""
    return [_check_python_env(), _check_wsl_dns(), _check_write_gate()]


if __name__ == "__main__":
    for item_name, status, evidence in check():
        print(f"[{status}] {item_name}")
        for line in evidence.splitlines():
            print(f"    {line}")
        print()
