"""claude 하네스 어댑터 - `claude -p --output-format stream-json --verbose`.

옛 `fleet._worker_argv` 의 claude 가지(`--output-format json`, 끝에 한 덩이 JSON)를 사건 흐름 꼴로 바꾼 것이다.
의존 방향은 fleet -> fleet_rt 이므로 `fleet` 은 들이지 않는다 (아래 도구 목록·환경변수 이름은 거기서 복사해 왔다).
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from typing import Optional

from .. import base
from ..base import Command, Event, ProbeResult, SessionSpec

# 관리자가 Claude 세션이므로 자식 claude 는 중첩 표식을 지우고 띄운다. `env -u` 로 감싸지 않고 Command.env_unset 으로 넘긴다.
NESTED_ENV = ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ID",
              "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
              "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH")

# 작업자에 허용하는 도구. 편집은 자동 승인(acceptEdits), 셸은 읽기·검증 명령만. commit/push/rm/설치는 목록에 없다.
WORKER_TOOLS = ",".join([
    "Read", "Edit", "Write", "Glob", "Grep",
    # 권한 규칙의 접두사 문법은 `Bash(cmd:*)` (콜론). 공백 별표는 글자 그대로 비교돼 아무것도 허용하지 않는다.
    "Bash(python3:*)", "Bash(python:*)", "Bash(pytest:*)",
    # 환경변수 접두사가 붙은 호출은 별도 규칙이 필요하다
    "Bash(PYTHONPATH=tools python3:*)", "Bash(PYTHONPATH=tools python:*)", "Bash(PYTHONPATH=. python3:*)",
    "Bash(PYTHONPYCACHEPREFIX=/tmp/pyc python3:*)", "Bash(node:*)", "Bash(npm test:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(grep:*)",
    "Bash(sed -n:*)", "Bash(pwd)", "Bash(mkdir:*)", "Bash(diff:*)", "Bash(git status:*)",
    "Bash(git diff:*)", "Bash(git log:*)", "Bash(curl:*)", "Bash(cd:*)", "Bash(echo:*)",
    "Bash(timeout:*)", "Bash(sleep:*)", "Bash(ss:*)", "Bash(kill:*)",
])

_SUMMARY_MAX = 120


def _require_repo_cwd(cwd):
    """진짜 하네스는 함대 저장소(`tools/fleet.py` 가 있는 폴더)에서만 띄운다.
    2026-11-12 에 /tmp 검토 사본에서 진짜 작업자가 떠 버린 일의 재발 방지."""
    p = pathlib.Path(str(cwd)) if cwd else None
    if p is None or not p.is_dir() or not (p / "tools" / "fleet.py").is_file():
        raise ValueError(f"함대 저장소가 아닌 작업 폴더에서는 claude 를 띄우지 않는다: {cwd!r}")


def _normalize_model(model):
    """슬롯에 적힌 모델에서 `anthropic/`·`claude-cli/` 접두를 뗀다 (fleet.normalize_model 의 claude 가지)."""
    if not model:
        return "sonnet"
    m = str(model).strip()
    for pre in ("anthropic/", "claude-cli/"):
        if m.startswith(pre):
            m = m[len(pre):]
    return m or "sonnet"


def _one_line(s, n=_SUMMARY_MAX):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _tool_summary(name, inp):
    """도구 호출을 `Bash: echo x` 꼴 한 줄로. 입력에서 command/file_path/pattern 순으로 대표 값을 고른다."""
    detail = ""
    if isinstance(inp, dict):
        for key in ("command", "file_path", "path", "pattern", "url", "description"):
            if inp.get(key):
                detail = _one_line(inp[key])
                break
    return f"{name}: {detail}" if detail else str(name)


def _usage_tokens(usage):
    """result.usage 에서 (들어간, 나온) 토큰. 캐시 읽기·쓰기도 입력으로 센다 (실제로 컨텍스트에 실린 양)."""
    if not isinstance(usage, dict):
        return None, None
    tin = sum(int(usage.get(k) or 0) for k in
              ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return tin, usage.get("output_tokens")


def _parse_json(raw):
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _limit_text(value):
    v = value.lower()
    return "limit" in v or "usage" in v and "reached" in v


class ClaudeHarness:
    name = "claude"

    # -- 띄우기 ---------------------------------------------------------------------------------
    def _argv(self, spec):
        _require_repo_cwd(spec.cwd)
        argv = ["claude", "-p", "--model", _normalize_model(spec.model),
                "--output-format", "stream-json", "--verbose",
                "--permission-mode", "acceptEdits", "--allowedTools", spec.tools or WORKER_TOOLS]
        if spec.settings_path:
            argv += ["--settings", spec.settings_path]
        return argv

    def command(self, spec: SessionSpec) -> Command:
        argv = self._argv(spec)
        sid = (spec.extra or {}).get("harness_session_id")
        if spec.role == "manager" and sid:
            argv += ["--session-id", str(sid)]   # 관리자는 id 를 미리 정해 두고 나중에 --resume 으로 잇는다
        return Command(argv=argv, cwd=spec.cwd, stdin_path=spec.brief_path, env_unset=NESTED_ENV)

    def resume_command(self, spec: SessionSpec, harness_session_id: str, message_path: str) -> Optional[Command]:
        argv = self._argv(spec) + ["--resume", str(harness_session_id)]
        return Command(argv=argv, cwd=spec.cwd, stdin_path=message_path, env_unset=NESTED_ENV)

    # -- 출력 풀기 ------------------------------------------------------------------------------
    def parse_event(self, line: str) -> Optional[Event]:
        """한 줄 -> 사건 하나. assistant 한 줄에 블록이 여럿이면 가장 정보가 큰 하나만 낸다
        (도구 호출 > 본문, 같은 종류가 여럿이면 앞의 것). thinking 은 버린다. 이어 오는 줄은 어차피 따로 온다."""
        if not line or not line.strip():
            return None
        d = _parse_json(line)
        if d is None:
            return Event("raw", raw=line)
        t, sub = d.get("type"), d.get("subtype")
        if t == "assistant":
            blocks = (d.get("message") or {}).get("content")
            if not isinstance(blocks, list):
                return Event("raw", raw=line)
            tool = text = None
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and tool is None:
                    name, inp = b.get("name", ""), b.get("input") or {}
                    tool = Event("tool", _tool_summary(name, inp), {"name": name, "input": inp}, line)
                elif b.get("type") == "text" and text is None and (b.get("text") or "").strip():
                    text = Event("text", b["text"], raw=line)
            return tool or text
        if t == "result":
            tin, tout = _usage_tokens(d.get("usage"))
            return Event("end", str(d.get("result") or ""), {
                "ok": not d.get("is_error"), "result": d.get("result"),
                "harness_session_id": d.get("session_id"), "tokens_in": tin, "tokens_out": tout,
                "cost_usd": d.get("total_cost_usd"), "api_error_status": d.get("api_error_status")}, line)
        if t == "system" and sub == "init":
            return Event("raw", data={"harness_session_id": d.get("session_id")}, raw=line)
        if t == "rate_limit_event":
            info = d.get("rate_limit_info") or {}
            status = str(info.get("status") or "").lower()
            if status in ("allowed", "allowed_warning"):
                return Event("usage", f"한도 {status}", {"limit": False, "status": status}, line)
            if status in ("rejected", "blocked") or "reject" in status or "block" in status:
                return Event("error", f"사용 한도 {status}", {"limit": True, "status": status}, line)
        return Event("raw", raw=line)

    def _events(self, session_dir):
        """events.jsonl 의 JSON 줄들 (받은 시각 접두는 read_event_lines 가 뗀다)."""
        out = []
        for _at, raw in base.read_event_lines(session_dir):
            d = _parse_json(raw)
            if d is not None:
                out.append(d)
        return out

    def final_report(self, session_dir) -> str:
        evs = self._events(session_dir)
        for d in reversed(evs):
            if d.get("type") == "result":
                return str(d.get("result") or "").strip()
        # result 없이 끝남: 마지막 assistant 메시지의 본문 (같은 message id 의 줄들은 이어 붙인다)
        parts, mid = [], None
        for d in reversed(evs):
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            if mid is not None and m.get("id") != mid:
                break
            mid = m.get("id")
            texts = [b.get("text", "") for b in (m.get("content") or [])
                     if isinstance(b, dict) and b.get("type") == "text"]
            parts[:0] = texts
        text = "".join(parts).strip()
        if text:
            return text
        return self._stderr_tail(session_dir)

    @staticmethod
    def _stderr_tail(session_dir):
        """보고문이 없을 때 stderr 에서 색 코드와 도구 로그 줄을 걷어낸 꼬리 (fleet.run_report 와 같은 생각)."""
        try:
            err = (pathlib.Path(session_dir) / "stderr.log").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        err = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", err)
        kept = [l for l in err.splitlines()
                if l.strip() and not re.match(r"^\s*(←|✗|!|\||\+|-|@|\$|>|codex$|tokens used|Reading additional)", l)]
        tail = "\n".join(kept[-25:]).strip()
        return "(최종 보고문 없음 - 작업자가 보고 전에 끝남. stderr 꼬리:)\n" + tail if tail else ""

    def limit_signal(self, session_dir) -> Optional[bool]:
        """`fleet_graph.run_limit_signal` 을 마지막 result 사건에 옮긴 것. result 가 없으면 None(모름)."""
        try:
            evs = self._events(session_dir)
            res = next((d for d in reversed(evs) if d.get("type") == "result"), None)
            if res is None:
                return None
            if not res.get("is_error"):
                return False
            status = res.get("api_error_status")
            if status == 429 or str(status) == "429":
                return True
            api_error = res.get("api_error")
            ae = api_error.lower() if isinstance(api_error, str) else ""
            if "usage_limit" in ae or "rate_limit" in ae:
                return True
            if res.get("terminal_reason") == "api_error":
                for key in ("result", "api_error", "stop_reason"):
                    v = res.get(key)
                    if isinstance(v, str) and _limit_text(v):
                        return True
            # 오류로 끝났고 그 전에 한도 거절 신호가 있었으면 한도다 (overageStatus 가 아니라 status 만 본다)
            for d in evs:
                if d.get("type") == "rate_limit_event":
                    st = str((d.get("rate_limit_info") or {}).get("status") or "").lower()
                    if st in ("rejected", "blocked"):
                        return True
            return False
        except Exception:
            return None

    # -- 점검 -----------------------------------------------------------------------------------
    def probe(self) -> ProbeResult:
        exe = shutil.which("claude")
        if not exe:
            return ProbeResult(False, detail="claude 실행 파일을 PATH 에서 찾지 못함")
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            return ProbeResult(False, binary=exe, detail=f"claude --version 실패: {e}")
        ver = (r.stdout or "").strip().splitlines()
        if r.returncode != 0:
            return ProbeResult(False, binary=exe, detail=f"claude --version rc={r.returncode}")
        return ProbeResult(True, binary=exe, version=ver[0] if ver else None)


ADAPTER = ClaudeHarness()
