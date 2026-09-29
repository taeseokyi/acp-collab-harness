"""터미널 규약 계층 검사 (관측 전용).

표준 라이브러리만 사용한다. 설정을 바꾸거나 무언가를 설치하지 않는다.
팬을 일부러 망가뜨려 코드를 유발하지 않는다 - 읽기와 조회만 한다.

Result = (name, status, evidence)
  status: "OK" | "CHANGED" | "UNKNOWN"

근거는 검사 대상 그 자체(`~/.local/bin/pan-run`), OpenClaw 런타임(`dist/**`,
`openclaw.json`), 실제 실행 결과에서만 가져온다. 우리 저장소의 기록은
"무엇을 검사할지" 정하는 데만 쓰고 판정 근거로는 쓰지 않는다.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
from pathlib import Path

Result = tuple[str, str, str]

OK = "OK"
CHANGED = "CHANGED"
UNKNOWN = "UNKNOWN"

# 우리 기록이 주장하는 pan-run 종료코드 규약. 무엇을 검사할지 정하는 값이며,
# 판정 근거가 아니다. 근거는 아래에서 스크립트 실물을 읽어 만든다.
RECORDED_EXIT_CODES = {
    64: "사용법",
    65: "세션 없음",
    66: "팬 제목 불일치",
    67: "락 대기 초과",
    68: "팬 오염",
    124: "실행 타임아웃",
}

# 우리 기록이 주장하는 tmux 팬 배치. 위와 같은 이유로 판정 근거가 아니다.
RECORDED_PANES = (0, 1, 2)

DIST_DIR = Path(
    "/home/tsyi/.local/share/pnpm/global/5/node_modules/openclaw/dist"
)
EXEC_RUNTIME_GLOB = "bash-tools.exec-runtime-*.js"

# 누적 로그는 기본적으로 남기지 않는다. `ENVCHECK_PIPELINE_LOG` 가 설정된
# 경우에만 그 경로에 append 한다.
#
# 이 모듈은 S3 소유이고 누적 판정은 통합 러너(관리자 소유)의 책임이다.
# 기본 경로를 두면 러너를 거치지 않은 호출이 남의 소유 파일에 조용히
# 쓰게 되므로, 기본값 자체를 없앤다. 모듈은 관측만 하고 상태를 남기지 않는다.
LOG_ENV = "ENVCHECK_PIPELINE_LOG"


def _pan_run_path() -> Path | None:
    candidate = Path(os.path.expanduser("~/.local/bin/pan-run"))
    if candidate.is_file():
        return candidate
    found = shutil.which("pan-run")
    return Path(found) if found else None


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _cite(lines: list[str], idx: int) -> str:
    """0-기준 인덱스를 'pan-run:행 "내용"' 인용으로 바꾼다."""
    return 'pan-run:{} "{}"'.format(idx + 1, lines[idx].strip())


# ── 항목 ① 종료코드 규약 ────────────────────────────────────────────────


def _check_exit_codes(script: Path) -> Result:
    name = "pan_run.exit_codes"
    lines = _read_lines(script)

    # (a) 스크립트가 실제로 반환하는 코드: 주석이 아닌 줄의 `exit N`
    actual: dict[int, int] = {}
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        for m in re.finditer(r"\bexit\s+(\d+)\b", line):
            actual.setdefault(int(m.group(1)), i)

    # (b) 스크립트 헤더 주석이 스스로 문서화한 코드
    documented: dict[int, int] = {}
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("#"):
            continue
        m = re.match(r"#\s{2,}(\d{2,3})\s+\S", line)
        if m:
            documented.setdefault(int(m.group(1)), i)

    # 명령의 종료코드를 그대로 넘기는 경로(`exit "$(cat ...)"`)는 숫자가 아니라
    # 잡히지 않는다. 0 은 정상 경로이므로 규약 비교에서 제외한다.
    actual_codes = {c for c in actual if c != 0}
    recorded = set(RECORDED_EXIT_CODES)

    missing = sorted(recorded - actual_codes)
    extra = sorted(actual_codes - recorded)
    undocumented = sorted(actual_codes - set(documented))

    cites = [_cite(lines, actual[c]) for c in sorted(recorded & actual_codes)]
    evidence = "실측 exit 코드 {} / 헤더 주석 문서화 {} | {}".format(
        sorted(actual_codes), sorted(documented), " ; ".join(cites)
    )

    if missing or extra:
        return (
            name,
            CHANGED,
            "기록에만 있음 {} / 스크립트에만 있음 {} | {}".format(
                missing, extra, evidence
            ),
        )
    if undocumented:
        return (
            name,
            CHANGED,
            "헤더 주석에 없는 코드 {} | {}".format(undocumented, evidence),
        )
    return (name, OK, evidence)


# ── 항목 ② 자동 복구 도달 조건 ──────────────────────────────────────────


def _shell_default(lines: list[str], var: str) -> tuple[int, int] | None:
    """`VAR="${ENVVAR:-300}"` 형태에서 기본값과 행 인덱스를 뽑는다."""
    pat = re.compile(r"\$\{" + re.escape(var) + r":-(\d+)\}")
    for i, line in enumerate(lines):
        m = pat.search(line)
        if m:
            return int(m.group(1)), i
    return None


def _check_recovery_reachability(script: Path) -> Result:
    name = "pan_run.recovery_reachability"
    lines = _read_lines(script)

    exec_to = _shell_default(lines, "PAN_RUN_TIMEOUT")
    lock_to = _shell_default(lines, "PAN_RUN_LOCK_TIMEOUT")
    if exec_to is None or lock_to is None:
        return (
            name,
            UNKNOWN,
            "타임아웃 기본값을 스크립트에서 찾지 못했다 "
            "(PAN_RUN_TIMEOUT={} PAN_RUN_LOCK_TIMEOUT={})".format(exec_to, lock_to),
        )

    # 복구 경로: 실행 타임아웃이 만료된 *뒤에야* 시작된다.
    gate = next(
        (i for i, l in enumerate(lines) if 'timeout "$TIMEOUT" tmux wait-for' in l),
        None,
    )
    attempts_i = next(
        (i for i, l in enumerate(lines) if re.search(r"for\s+attempt\s+in\s+1\s+2", l)),
        None,
    )
    probe = next(
        (
            (int(m.group(1)), i)
            for i, l in enumerate(lines)
            if (m := re.search(r'timeout\s+"\$\{1:-(\d+)\}"', l))
        ),
        None,
    )
    if gate is None or attempts_i is None or probe is None:
        return (
            name,
            UNKNOWN,
            "복구 경로 구조를 특정하지 못했다 "
            "(gate={} attempts={} probe={})".format(gate, attempts_i, probe),
        )

    attempts = 2
    probe_sec, probe_i = probe
    exec_sec, exec_i = exec_to
    lock_sec, lock_i = lock_to

    # 호출자가 pan-run 을 살려 두어야 하는 최소 시간
    best = exec_sec + attempts * probe_sec          # 락 무경합
    worst = lock_sec + exec_sec + attempts * probe_sec  # 락 최대 대기

    # 호출자 쪽 상한을 런타임에서 관측할 수 있는가
    caller_note = _openclaw_exec_timeout_note()

    evidence = (
        "복구 경로는 실행 타임아웃 만료 후에만 진입한다: {} ; "
        "재시도 {} ; 유휴 프로브 {}초 {} ; "
        "기본값 PAN_RUN_TIMEOUT={}초 {} / PAN_RUN_LOCK_TIMEOUT={}초 {} ; "
        "=> 복구가 끝나려면 호출자가 pan-run 을 최소 {}초(락 무경합) "
        "~ {}초(락 최대 대기) 동안 죽이지 않아야 한다. | 호출자 상한: {}"
    ).format(
        _cite(lines, gate),
        _cite(lines, attempts_i),
        probe_sec,
        _cite(lines, probe_i),
        exec_sec,
        _cite(lines, exec_i),
        lock_sec,
        _cite(lines, lock_i),
        best,
        worst,
        caller_note,
    )

    # 호출자의 실제 상한은 프로세스 안에서 관측할 수 없다. 조건만 확정하고
    # 판정은 UNKNOWN 으로 둔다 - 억지 판정을 하지 않는 것이 이 검사의 값어치다.
    return (name, UNKNOWN, evidence)


def _openclaw_exec_timeout_note() -> str:
    """OpenClaw exec 경로가 기본 타임아웃을 두는지 dist 에서 확인한다."""
    if not DIST_DIR.is_dir():
        return "dist 없음 - 확인 불가"
    hits = sorted(DIST_DIR.glob(EXEC_RUNTIME_GLOB))
    if not hits:
        return "exec 런타임 번들을 찾지 못함 - 확인 불가"
    target = hits[0]
    lines = _read_lines(target)
    for i, line in enumerate(lines):
        if "function resolveExecTimeoutMs" in line:
            body = " ".join(lines[i : i + 4])
            no_default = "return;" in body or "return ;" in body
            return (
                "{}:{} resolveExecTimeoutMs - timeoutSec 미지정 시 "
                "{} (해당 경로에서는 호출자 상한 없음: {})"
            ).format(
                target.name,
                i + 1,
                "undefined 반환" if no_default else "기본값 적용",
                no_default,
            )
    return "{} 에서 resolveExecTimeoutMs 를 찾지 못함".format(target.name)


# ── 항목 ③ tmux 팬 배치와 제목 ──────────────────────────────────────────


def _expected_titles(lines: list[str]) -> dict[int, tuple[str, int]]:
    """pan-run 의 제목 검증 case 블록에서 기대 제목을 뽑는다."""
    out: dict[int, tuple[str, int]] = {}
    for i, line in enumerate(lines):
        m = re.match(r'\s*(\d)\)\s*EXPECT="([^"]+)"', line)
        if m:
            out[int(m.group(1))] = (m.group(2), i)
    return out


def _tmux_session_name(lines: list[str]) -> tuple[str, int] | None:
    for i, line in enumerate(lines):
        m = re.match(r'\s*SESSION="([^"]+)"', line)
        if m:
            return m.group(1), i
    return None


def _check_pane_layout(script: Path) -> Result:
    name = "tmux.pane_layout"
    lines = _read_lines(script)

    session = _tmux_session_name(lines)
    expected = _expected_titles(lines)
    if session is None or not expected:
        return (name, UNKNOWN, "pan-run 에서 세션명/기대 제목을 특정하지 못했다")

    session_name, session_i = session
    if shutil.which("tmux") is None:
        return (name, UNKNOWN, "tmux 실행 파일 없음 - 조회 불가")

    cmd = [
        "tmux",
        "list-panes",
        "-t",
        session_name,
        "-F",
        "#{pane_index}|#{pane_title}",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (name, UNKNOWN, "{} 실패: {}".format(" ".join(cmd), exc))

    if proc.returncode != 0:
        return (
            name,
            UNKNOWN,
            "$ {} -> rc={} {}".format(
                " ".join(cmd), proc.returncode, proc.stderr.strip()
            ),
        )

    observed: dict[int, str] = {}
    for row in proc.stdout.splitlines():
        if "|" not in row:
            continue
        idx, title = row.split("|", 1)
        if idx.strip().isdigit():
            observed[int(idx.strip())] = title.strip()

    problems: list[str] = []
    for pane in RECORDED_PANES:
        if pane not in observed:
            problems.append("팬 {} 없음".format(pane))
            continue
        if pane not in expected:
            problems.append("팬 {} 기대 제목이 스크립트에 없음".format(pane))
            continue
        want = expected[pane][0]
        got = observed[pane]
        # pan-run 과 같은 판정: 접두사 일치
        if not got.startswith(want):
            problems.append(
                "팬 {} 제목 불일치 (기대 접두사 {!r} / 실제 {!r})".format(
                    pane, want, got
                )
            )

    surplus = sorted(set(observed) - set(RECORDED_PANES))
    if surplus:
        problems.append("기록에 없는 팬 {}".format(surplus))

    evidence = "$ {} -> {} | 기대 제목 {} ; {}".format(
        " ".join(cmd),
        "; ".join("{}={!r}".format(k, observed[k]) for k in sorted(observed)),
        {k: v[0] for k, v in sorted(expected.items())},
        _cite(lines, session_i),
    )
    status = CHANGED if problems else OK
    if problems:
        evidence = "{} | {}".format(" / ".join(problems), evidence)

    _append_log(name, status, observed)
    return (name, status, evidence)


def _log_path() -> Path | None:
    override = os.environ.get(LOG_ENV, "").strip()
    return Path(override) if override else None


def _append_log(name: str, status: str, observed: dict[int, str]) -> None:
    """판정 이력을 누적한다 - 단, 경로가 명시적으로 주어졌을 때만.

    팬 구성은 시간에 따라 변하므로 이력이 쓸모 있지만, 어디에 남길지는
    호출자가 정한다. 경로가 없으면 아무 파일도 만들지 않는다.
    """
    path = _log_path()
    if path is None:
        return
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    line = "{} | envcheck.{} | {} | panes={}\n".format(
        stamp,
        name,
        status,
        ",".join("{}:{}".format(k, observed[k]) for k in sorted(observed)) or "none",
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        # 로그를 남기지 못해도 검사 자체는 계속한다. 관측 전용 도구가
        # 쓰기 실패로 죽으면 검사기 자신이 장애 원인이 된다.
        pass


# ── 공개 진입점 ─────────────────────────────────────────────────────────


def check() -> list[Result]:
    script = _pan_run_path()
    if script is None:
        reason = "~/.local/bin/pan-run 을 찾지 못했다 (PATH 조회도 실패)"
        return [
            ("pan_run.exit_codes", UNKNOWN, reason),
            ("pan_run.recovery_reachability", UNKNOWN, reason),
            ("tmux.pane_layout", UNKNOWN, reason),
        ]
    return [
        _check_exit_codes(script),
        _check_recovery_reachability(script),
        _check_pane_layout(script),
    ]


if __name__ == "__main__":
    for item_name, item_status, item_evidence in check():
        print(f"[{item_status}] {item_name}")
        for line in item_evidence.splitlines():
            print(f"    {line}")
        print()
