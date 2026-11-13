"""codex 어댑터 - `codex exec --json` 의 사건 흐름을 공통 사건으로 푼다.

codex-cli 0.162.1 의 `--json` 은 줄마다 JSON 하나다: `thread.started` / `turn.started` /
`item.started|updated|completed` / `turn.completed`(usage) / `turn.failed` / 최상위 `error`.
**명시적인 '끝' 사건은 없다** - 프로세스가 끝나면 끝이다(그래서 `end` 사건을 지어내지 않는다).
성공 표본이 없는 채로 짰으므로(공급자 장애) 모르는 모양은 예외 없이 `raw` 로 남긴다.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from typing import Optional

from ..base import (LIMIT_RE, Command, Event, ProbeResult, SessionSpec, no_report_tail, one_line as _one_line,
                    read_event_lines, require_repo_cwd)

_RETRY_RE = re.compile(r"reconnecting|stream disconnected|retrying", re.I)


def _error_event(msg, raw):
    data = {}
    if _RETRY_RE.search(msg):
        data["retry"] = True
    if LIMIT_RE.search(msg):
        data["limit"] = True
    return Event("error", msg, data, raw)


def _tool_event(item, raw):
    t = item.get("type")
    if t == "command_execution":
        cmd = item.get("command") or ""
        data = {"name": "shell", "input": {"command": cmd}, "exit_code": item.get("exit_code")}
        return Event("tool", "shell: " + _one_line(cmd), data, raw)
    if t == "file_change":
        ch = item.get("changes") or []
        names = []
        for c in ch if isinstance(ch, list) else []:
            if isinstance(c, dict) and c.get("path"):
                names.append(str(c["path"]))
        return Event("tool", "file_change: " + _one_line(", ".join(names) or "(파일 목록 없음)"),
                     {"name": "file_change", "input": {"paths": names}}, raw)
    if t == "mcp_tool_call":
        name = f"{item.get('server', '')}.{item.get('tool', '')}".strip(".")
        return Event("tool", "mcp: " + _one_line(name), {"name": "mcp", "input": {"tool": name}}, raw)
    if t == "web_search":
        q = item.get("query") or ""
        return Event("tool", "web_search: " + _one_line(q), {"name": "web_search", "input": {"query": q}}, raw)
    return None


class CodexHarness:
    name = "codex"

    def command(self, spec: SessionSpec) -> Command:
        cwd = str(require_repo_cwd(spec.cwd, "codex"))
        argv = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-C", cwd, "--sandbox", "workspace-write",
                "-c", "sandbox_workspace_write.network_access=true", "--json"]
        if spec.model:
            # 슬롯 꼴 `kisti/kistillm` → codex 는 모델과 공급자를 따로 받는다. 첫 '/' 앞이 공급자다 -
            # 모델 id 에 '/' 가 든 공급자가 있다 (`openrouter/deepseek/deepseek-v4.1-flash`).
            model = str(spec.model).strip()
            prov, mid = model.split("/", 1) if "/" in model else ("", model)
            argv += ["-m", mid]
            if prov:
                argv += ["-c", f"model_provider={prov}"]
                # 공급자가 죽었을 때 재시도로 수십 분 붙들리지 않게 한도를 1회로 (키 이름은 0.162.1 바이너리에서 확인)
                argv += ["-c", f"model_providers.{prov}.stream_max_retries=1",
                         "-c", f"model_providers.{prov}.request_max_retries=1"]
        argv.append("-")  # 프롬프트는 stdin
        return Command(argv=argv, cwd=cwd, stdin_path=spec.brief_path)

    def parse_event(self, line: str) -> Optional[Event]:
        if line is None or not str(line).strip():
            return None
        raw = str(line).rstrip("\n")
        try:
            d = json.loads(raw)
        except ValueError:
            return Event("raw", raw, {}, raw)
        if not isinstance(d, dict):
            return Event("raw", raw, {}, raw)
        typ = d.get("type")
        if typ == "thread.started":
            return Event("raw", "thread.started", {"harness_session_id": d.get("thread_id")}, raw)
        if typ == "turn.completed":
            u = d.get("usage") if isinstance(d.get("usage"), dict) else {}
            data = {}
            if u.get("input_tokens") is not None:
                data["tokens_in"] = u.get("input_tokens")
            if u.get("output_tokens") is not None:
                data["tokens_out"] = u.get("output_tokens")
            return Event("usage", "", data, raw)
        if typ == "turn.failed":
            e = d.get("error")
            msg = (e.get("message") if isinstance(e, dict) else e) or "turn.failed"
            return _error_event(str(msg), raw)
        if typ == "error":
            return _error_event(str(d.get("message") or "error"), raw)
        if typ in ("item.started", "item.updated", "item.completed"):
            item = d.get("item")
            if not isinstance(item, dict):
                return Event("raw", raw, {}, raw)
            it = item.get("type")
            if it == "agent_message":
                # 부분 갱신은 건너뛴다 - 완성본(completed)만 말로 친다
                return Event("text", str(item.get("text") or ""), {}, raw) if typ == "item.completed" else Event("raw", raw, {}, raw)
            if it == "reasoning":
                return None
            if it == "command_execution":
                return _tool_event(item, raw)
            if it in ("file_change", "mcp_tool_call", "web_search"):
                # 시작·완료가 둘 다 오므로 완료 때만 요약한다 (같은 호출이 두 줄로 안 보이게)
                return _tool_event(item, raw) if typ == "item.completed" else Event("raw", raw, {}, raw)
            if it == "error":
                return _error_event(str(item.get("message") or "error"), raw)
        return Event("raw", raw, {}, raw)

    def _events(self, session_dir):
        for _at, raw in read_event_lines(session_dir):
            ev = self.parse_event(raw)
            if ev is not None:
                yield ev

    def final_report(self, session_dir: pathlib.Path) -> str:
        last = None
        errors = []
        for ev in self._events(session_dir):
            if ev.kind == "text":
                last = ev.text
            elif ev.kind == "error" and ev.text not in errors:
                errors.append(ev.text)
        if last is not None and last.strip():
            return last.strip()
        return no_report_tail(session_dir, [f"error: {m}" for m in errors])

    def limit_signal(self, session_dir: pathlib.Path) -> Optional[bool]:
        completed = False
        for ev in self._events(session_dir):
            if ev.kind == "error" and ev.data.get("limit"):
                return True
            if ev.kind == "usage":
                completed = True
        return False if completed else None

    def resume_command(self, spec, harness_session_id, message_path):
        return None                     # `--ephemeral` 이라 이어 붙일 세션이 디스크에 없다

    def probe(self) -> ProbeResult:
        path = shutil.which("codex")
        if not path:
            return ProbeResult(False, None, None, "codex 실행 파일이 PATH 에 없다")
        try:
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            return ProbeResult(False, path, None, f"codex --version 실패: {e}")
        out = (r.stdout or r.stderr or "").strip()
        if r.returncode != 0:
            return ProbeResult(False, path, None, f"codex --version rc={r.returncode}: {_one_line(out)}")
        return ProbeResult(True, path, out.split()[-1] if out else None, "")


ADAPTER = CodexHarness()
