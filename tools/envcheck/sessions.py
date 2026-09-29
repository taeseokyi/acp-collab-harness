"""세션·에이전트 계층 관측 검사 (S1 / 라운드 2).

관측 전용. 표준 라이브러리만 쓴다. 설정을 바꾸거나 무엇도 설치하지 않는다.
세션을 실제로 만들지 않는다 - 부작용 없는 근거(설치본 코드, 런타임 설정,
읽기 전용 CLI 출력)로만 판정한다.

근거는 OpenClaw 런타임에서만 가져온다:
  - <openclaw 설치본>/dist/**  및 같은 설치본의 docs/**
  - ~/.openclaw/openclaw.json
  - `openclaw ...` 읽기 전용 실행 결과

dist 파일명에는 내용 해시가 붙어 업그레이드마다 바뀐다. 그래서 파일명을 고정하지
않고 glob + 내용으로 찾는다. 찾지 못하면 실패가 아니라 UNKNOWN 이다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

# Result = (name: str, status: str, evidence: str)
OK = "OK"
CHANGED = "CHANGED"
UNKNOWN = "UNKNOWN"

CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"


# ---------------------------------------------------------------- 공통 도우미


def _dist_root() -> Path | None:
    """설치본 dist 디렉터리를 찾는다. 경로를 하드코딩으로 단정하지 않는다."""
    seen: list[Path] = []
    env = os.environ.get("OPENCLAW_DIST")
    if env:
        seen.append(Path(env))
    exe = shutil.which("openclaw")
    if exe:
        resolved = Path(exe).resolve()
        for parent in resolved.parents:
            seen.append(parent / "dist")
            seen.append(parent / "openclaw" / "dist")
    seen.append(
        Path.home() / ".local/share/pnpm/global/5/node_modules/openclaw/dist"
    )
    for cand in seen:
        if (cand / "extensions").is_dir():
            return cand
    return None


def _read_config() -> dict | None:
    try:
        with CONFIG_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _grep(root: Path, pattern: str, glob: str = "*.js", limit: int = 3):
    """dist 안에서 정규식에 맞는 (경로, 행번호, 행) 을 모은다."""
    rx = re.compile(pattern, re.MULTILINE)
    hits = []
    for path in sorted(root.glob(glob)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rx.search(text) is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                hits.append((path, lineno, line.strip()))
                if len(hits) >= limit:
                    return hits
    return hits


def _cite(root: Path, hit) -> str:
    path, lineno, line = hit
    try:
        rel = path.relative_to(root.parent)
    except ValueError:
        rel = path
    snippet = line if len(line) <= 120 else line[:117] + "..."
    return f"{rel}:{lineno}  {snippet}"


def _run(argv: list[str], timeout: int = 90) -> tuple[int, str] | None:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ------------------------------------------------- 항목 1: ACP 세션 생성 가능성


def _check_acp_can_create_sessions():
    name = "acp.can_create_sessions"
    root = _dist_root()
    cfg = _read_config()
    if cfg is None:
        return (name, UNKNOWN, f"설정을 읽지 못했다: {CONFIG_PATH}")

    acp = cfg.get("acp") or {}
    enabled = acp.get("enabled")
    backend = acp.get("backend") or "acpx"
    allowed = [str(a) for a in (acp.get("allowedAgents") or [])]
    default_agent = acp.get("defaultAgent")
    entries = sorted((cfg.get("agents") or {}).get("entries") or {})

    lines = [
        f"{CONFIG_PATH}: acp.enabled={enabled!r} acp.backend={backend!r} "
        f"acp.defaultAgent={default_agent!r} acp.allowedAgents={allowed!r}",
        f"{CONFIG_PATH}: agents.entries={entries!r}",
    ]

    # (1) 설정 차원에서 이미 막혀 있는가
    if enabled is not True:
        lines.append("판정: acp.enabled 가 참이 아니다. ACP 경로 자체가 닫혀 있다.")
        return (name, OK, "\n".join(lines))

    # (2) 백엔드 플러그인이 실제로 올라와 있는가 (읽기 전용 CLI)
    listing = _run(["openclaw", "plugins", "list"])
    backend_row = None
    if listing is None:
        lines.append("`openclaw plugins list` 를 실행하지 못했다 (바이너리 부재 또는 시간 초과).")
    else:
        rc, out = listing
        for line in out.splitlines():
            if re.search(rf"\|\s*{re.escape(backend)}\s*\|", line) or re.search(
                rf"│\s*{re.escape(backend)}\s*│", line
            ):
                backend_row = line.strip()
                break
        if backend_row:
            lines.append(f"`openclaw plugins list` (rc={rc}): {backend_row[:160]}")
        else:
            lines.append(
                f"`openclaw plugins list` (rc={rc}): 백엔드 {backend!r} 행을 찾지 못했다."
            )

    backend_enabled = bool(backend_row and "enabled" in backend_row)
    if backend_row and not backend_enabled:
        lines.append(f"판정: 백엔드 플러그인 {backend!r} 이 비활성이다. 세션을 만들 수 없다.")
        return (name, OK, "\n".join(lines))

    # (3) 하네스 id 를 누가 어떻게 받아들이는가 - 서로 다른 두 해석기
    if root is None:
        lines.append("dist 를 찾지 못해 코드 근거를 댈 수 없다.")
        return (name, UNKNOWN, "\n".join(lines))

    acp_resolver = _grep(
        root,
        r"is an OpenClaw config agent, not an ACP harness",
        limit=1,
    )
    strict_resolver = _grep(
        root,
        r"normalizedRequestedAgentId && !configuredAgentIds\.includes",
        limit=1,
    )
    for hit in acp_resolver + strict_resolver:
        lines.append(_cite(root, hit))

    outside_entries = [a for a in allowed if a not in entries]
    if outside_entries:
        lines.append(
            f"acp.allowedAgents 중 agents.entries 에 없는 id: {outside_entries!r} "
            "- ACP 전용 해석기는 외부 하네스 id 를 허용하지만, 세션 생성 경로의 "
            "일반 해석기는 agents.entries 밖의 id 를 거부한다. 두 해석기가 어긋난다."
        )

    lines.append(
        "판정 불가: 설정과 백엔드는 정상으로 보이고, 실패를 확증하려면 실제 스폰이 "
        "필요하다. 부작용 금지라 하지 않는다."
    )
    return (name, UNKNOWN, "\n".join(lines))


# --------------------------------------------- 항목 2: 자식 세션이 받는 큐 레인


def _check_nested_lane():
    name = "sessions_send.child_queue_lane"
    root = _dist_root()
    cfg = _read_config()
    if root is None:
        return (name, UNKNOWN, "OpenClaw dist 를 찾지 못했다.")
    if cfg is None:
        return (name, UNKNOWN, f"설정을 읽지 못했다: {CONFIG_PATH}")

    lines = []

    # (1) 레인 이름 규칙
    naming = _grep(root, r"NESTED_LANE_PREFIX\}\$\{trimmed\}", glob="lanes-*.js", limit=1)
    prefix = _grep(root, r"const NESTED_LANE_PREFIX", glob="lanes-*.js", limit=1)
    # (2) sessions_send 호출부가 어느 키로 레인을 만드는가
    call = _grep(
        root,
        r"lane: resolveNestedAgentLaneForSession\(params\.targetSessionKey\)",
        glob="sessions-spawn-tool-*.js",
        limit=1,
    )
    tool = _grep(
        root,
        r'sourceTool: "sessions_send"',
        glob="sessions-spawn-tool-*.js",
        limit=1,
    )
    # (3) 레인 기본 동시성
    default_conc = _grep(root, r"^\s*maxConcurrent: 1,", glob="command-queue-*.js", limit=1)
    # (4) 그룹 편입 금지 (= 에이전트 전역 상한과 분리)
    ineligible = _grep(root, r'"nested:",', glob="command-queue-*.js", limit=1)

    found = {
        "lane 이름 규칙": naming or prefix,
        "sessions_send 호출부": call,
        "lane 기본 동시성": default_conc,
        "그룹 편입 금지": ineligible,
    }
    missing = [k for k, v in found.items() if not v]
    for hit_list in (prefix, naming, call, tool, default_conc, ineligible):
        for hit in hit_list:
            lines.append(_cite(root, hit))

    # (5) 설정이 레인 상한을 덮어쓰는가
    queue_cfg = cfg.get("queue")
    lane_overrides = (queue_cfg or {}).get("lanes") if isinstance(queue_cfg, dict) else None
    global_max = ((cfg.get("agents") or {}).get("defaults") or {}).get("maxConcurrent")
    lines.append(
        f"{CONFIG_PATH}: queue={queue_cfg!r} (레인 상한 덮어쓰기 없음) / "
        f"agents.defaults.maxConcurrent={global_max!r}"
    )

    if missing:
        lines.append(f"근거를 찾지 못한 항목: {missing!r}")
        return (name, UNKNOWN, "\n".join(lines))

    if lane_overrides:
        lines.append(
            f"판정: queue.lanes 가 레인 상한을 덮어쓴다 {lane_overrides!r}. "
            "기본 1 이라는 기록이 이 설치본에서는 성립하지 않는다."
        )
        return (name, CHANGED, "\n".join(lines))

    lines.append(
        "판정: sessions_send 로 구동되는 자식 턴은 대상 세션키로 만든 "
        "`nested:<세션키>` 레인에 들어간다. 그 레인은 생성 시 maxConcurrent=1 "
        "이고 설정에 덮어쓰기가 없다. `nested:` 접두사는 용량 그룹에 편입될 수 "
        f"없으므로 agents.defaults.maxConcurrent({global_max}) 와 경합하지 않는다. "
        "기록과 일치한다."
    )
    return (name, OK, "\n".join(lines))


# ------------------------------------------------------------------ 진입점


def check() -> list[tuple[str, str, str]]:
    return [
        _check_acp_can_create_sessions(),
        _check_nested_lane(),
    ]


if __name__ == "__main__":
    for item_name, status, evidence in check():
        print(f"[{status}] {item_name}")
        for line in evidence.splitlines():
            print(f"    {line}")
        print()
