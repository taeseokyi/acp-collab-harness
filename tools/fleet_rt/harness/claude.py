"""claude 하네스 어댑터 - `claude -p --output-format stream-json --verbose`.

모델은 `spec.model`(슬롯 모델, 없으면 `fleet.toml` 하네스 기본을 spawn 이 채운다)을 하네스 꼴로 받는다.
"""
from __future__ import annotations

import json
import pathlib
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
#: 작업자가 사본·임시 파일을 두는 곳 (`_argv` 의 `--add-dir`)
SCRATCH_DIR = "/tmp"

#: 한 세션이 result 를 여럿 냈을 때, 앞서 낸 것 위에 붙이는 표지 (`final_report`)
EARLIER_REPORT_MARK = "--- 앞서 낸 보고 ---"

#: 작업자의 도구. Bash 는 통째로 허용한다 (태석님 2026-11-28: "이미 python 으로 열려 있는데 bash 를 막을 필요는 없다").
#: 전에는 명령 접두사 목록이었는데, `python3` 가 이미 무엇이든 돌릴 수 있어 벽이 되지 못했고 명령을 잇는 방식
#: (`cd …; git …`·`$(…)`·`for`·스크립트 실행)에 걸려 검수자가 헛걸음만 했다 (R55 T-501: 8건 거절, 시험 11꼴 중 9꼴 거절 → 0꼴).
#: 거부 목록도 걸지 않는다 - 감싸면 지나가는 난간은 필요 없다(같은 날). 커밋·푸시·삭제·설치를 하지 말라는 말은 지시문 머리말이 한다
WORKER_TOOLS = "Read,Edit,Write,Glob,Grep,Bash,Skill"


def _tool_summary(name, inp):
    """도구 호출을 `Bash: echo x` 꼴 한 줄로. 입력에서 command/file_path/pattern 순으로 대표 값을 고른다."""
    detail = ""
    if isinstance(inp, dict):
        for key in ("command", "file_path", "path", "pattern", "url", "description"):
            if inp.get(key):
                detail = base.one_line(inp[key])
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


def result_limit_signal(res, events=()) -> Optional[bool]:
    """result 사건 하나(+ 그 앞 사건들)로 본 사용 한도: True/False/None(모름 - 호출자가 글자 판정으로 넘어간다)."""
    if not isinstance(res, dict):
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
            if isinstance(v, str) and base.LIMIT_RE.search(v[-2000:]):
                return True
    # 오류로 끝났고 그 전에 한도 거절 신호가 있었으면 한도다 (overageStatus 가 아니라 status 만 본다)
    for d in events or ():
        if isinstance(d, dict) and d.get("type") == "rate_limit_event":
            info = d.get("rate_limit_info")
            st = str((info or {}).get("status") or "").lower() if isinstance(info, dict) else ""
            if st in ("rejected", "blocked"):
                return True
    return None  # 오류인데 표지가 없다 - False 면 호출자가 글자 판정을 건너뛴다


#: 모델 API 가 잠깐 막히거나 바빴다는 HTTP 상태. 429 는 대개 사용 한도라 `result_limit_signal` 이 먼저 거른다.
TRANSIENT_STATUS = frozenset({403, 408, 409, 429})
#: 상태 숫자가 없을 때만 보는 일반적인 전송 오류 낱말 (특정 업체·문구는 넣지 않는다)
TRANSIENT_WORDS = ("timeout", "timed out", "connection", "overloaded", "econnreset", "socket hang up")


def result_transient(res, events=()) -> bool:
    """result 사건 하나가 '잠깐의 API·전송 오류로 끝남' 인가. 사용 한도면 False (한도는 기다려도 곧 안 풀린다)."""
    if not isinstance(res, dict) or not res.get("is_error"):
        return False
    if result_limit_signal(res, events) is True:
        return False
    try:
        status = int(res.get("api_error_status"))
    except (TypeError, ValueError):
        status = None
    if status is not None:
        return status in TRANSIENT_STATUS or 500 <= status <= 599
    if res.get("terminal_reason") != "api_error":
        return False
    text = " ".join(str(res.get(k) or "") for k in ("result", "api_error")).lower()
    return any(w in text for w in TRANSIENT_WORDS)


def transient_api_error(session_dir) -> bool:
    """세션의 **마지막** result 사건이 잠깐의 API·전송 오류인가. result 가 없거나 오류가 아니면 False.

    claude -p 는 이런 오류를 스스로 다시 시도하지 않고 rc 1 로 끝난다. 엔진은 이것이 참일 때만 같은 대화를
    `--resume` 으로 잇는다 - 진짜 실패·한도까지 이으면 같은 실패에 돈만 든다.
    """
    try:
        evs = ADAPTER._events(session_dir)
    except Exception:  # noqa: BLE001
        return False
    res = next((d for d in reversed(evs) if d.get("type") == "result"), None)
    return result_transient(res, evs)


def _limit_reset(events):
    """마지막 한도 사건에서 뽑은 '풀리는 시각'(유닉스 초). 거절된 창이 여럿이면 가장 늦은 것. 모르면 None."""
    info = next((d.get("rate_limit_info") for d in reversed(list(events or ()))
                 if isinstance(d, dict) and d.get("type") == "rate_limit_event" and isinstance(d.get("rate_limit_info"), dict)), None)
    if not info:
        return None

    def rejected(x):
        return isinstance(x, dict) and str(x.get("status") or "").lower() in ("rejected", "blocked")

    wins = info.get("unifiedWindows") if isinstance(info.get("unifiedWindows"), dict) else {}
    times = [x.get("resetsAt") for x in [info, *wins.values()] if rejected(x)]
    times = [float(t) for t in times if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0]
    return max(times) if times else None


def limit_end(session_dir):
    """세션의 **마지막** result 가 사용 한도로 끝났나 - `(한도인가, 풀리는 시각 또는 None)`.

    한도는 잠깐 쉰다고 풀리지 않으므로 `transient_api_error` 는 거짓이다. 엔진은 완전 자율 종주일 때만 이 시각까지
    기다렸다가 같은 대화를 잇는다.
    """
    try:
        evs = ADAPTER._events(session_dir)
    except Exception:  # noqa: BLE001
        return False, None
    res = next((d for d in reversed(evs) if d.get("type") == "result"), None)
    if result_limit_signal(res, evs) is not True:
        return False, None
    return True, _limit_reset(evs)


class ClaudeHarness:
    name = "claude"

    # -- 띄우기 ---------------------------------------------------------------------------------
    def _argv(self, spec):
        base.require_repo_cwd(spec.cwd, "claude")
        argv = ["claude", "-p", *(["--model", spec.model] if spec.model else []),
                "--output-format", "stream-json", "--verbose",
                "--permission-mode", "acceptEdits", "--allowedTools", spec.tools or WORKER_TOOLS,
                # /tmp 를 작업 폴더로 더한다 - 허용 목록에 있어도 작업 폴더 밖 쓰기(mkdir·cp·Edit)는 승인을 기다리며 막혀,
                # 검수자가 사본을 만들어 고침을 되돌려 보는 확인을 못 했다 (2026-11-28 실측: 더하면 승인 없이 됨)
                "--add-dir", SCRATCH_DIR]
        denied = (spec.extra or {}).get("disallowed_tools")
        if denied:
            # 명세가 거부 목록을 주면 붙인다 (`claude --help` 의 철자). 함대는 지금 아무 세션에도 주지 않는다 -
            # 셸·python 으로 감싸면 지나가는 난간이라 걷었다 (태석님 2026-11-28). 하지 말 것은 지시문 머리말·브리프가 말한다
            argv += ["--disallowedTools", str(denied)]
        if spec.settings_path:
            argv += ["--settings", spec.settings_path]
        return argv

    def command(self, spec: SessionSpec) -> Command:
        resume = (spec.extra or {}).get("resume_session")
        if resume:
            # 끊긴 대화를 잇는다 (`fleet_ctl.resume_manager`): 지시문(stdin)이 이어 갈 말이 되고, 도구·모델·설정은 처음과 같다.
            # `--session-id` 는 붙이지 않는다 - 대화 id 는 이어 받는 쪽이 정한다
            return self.resume_command(spec, str(resume), spec.brief_path)
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
        results = [str(d.get("result") or "").strip() for d in evs if d.get("type") == "result"]
        if results:
            # 백그라운드 알림이 오면 대화가 한 차례 더 돌아 result 가 여럿 생긴다. 마지막 것만 쓰면 알림에 답한 짧은 글이
            # 본 보고를 가리고(R51 T-458·R54 T-493), 앞의 것만 쓰면 뒤에 고친 상태를 놓친다. 그래서 마지막 말을 맨 위에
            # 두고(첫 줄 = 지금의 상태), 앞서 낸 것은 최근 것부터 아래에 붙인다
            earlier = [r for r in dict.fromkeys(reversed(results[:-1])) if r and r != results[-1]]
            if not earlier:
                return results[-1]
            return "\n\n".join([results[-1]] + [f"{EARLIER_REPORT_MARK}\n{r}" for r in earlier]).strip()
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
        return base.no_report_tail(session_dir)

    def limit_signal(self, session_dir) -> Optional[bool]:
        """마지막 result 사건으로 본 사용 한도. result 가 없으면 None(모름)."""
        try:
            evs = self._events(session_dir)
            res = next((d for d in reversed(evs) if d.get("type") == "result"), None)
            if res is None:
                return None
            return result_limit_signal(res, evs)
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
