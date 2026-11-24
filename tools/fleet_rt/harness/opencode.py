"""opencode 어댑터 - `opencode run --format json` 의 사건 줄을 공통 사건으로 푼다 (opencode 1.18.33 실측).

사건 종류: `step_start` / `text` / `tool_use` / `step_finish`(reason: `tool-calls` | `stop`) / `error`.
opencode 는 끝을 알리는 사건이 없다 - 어댑터도 `end` 를 지어내지 않는다 (끝은 프로세스 rc 가 말한다).
지시문 본문은 argv 에 넣지 않고 '이 파일을 읽어라' 한 문장만 넘긴다 (`base.Command` 참고).
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from typing import Optional

from .. import base
from ..base import LIMIT_RE, Command, Event, ProbeResult, SessionSpec, one_line as _one_line, require_repo_cwd

_BASE_ARGV = ["opencode", "run", "--format", "json"]
#: 작업자에게 저장소 밖에서 허용하는 자리 - `/tmp` 뿐이다. opencode 는 저장소 밖 경로를 쓰려 하면 권한을 묻는데, 사람이 없는
#: 실행이라 자동으로 거절되고 그 자리에서 대화가 끝난다 (R41 T-385: 검수 지시대로 /tmp 에 사본을 만들려다 빈손으로 끝남).
#: 다른 하네스(claude·codex·freebuff)의 작업자는 이미 /tmp 를 쓴다 - 같은 지시문이 어느 슬롯에서나 통하게 맞춘다.
#: 사용자의 opencode 설정 파일은 건드리지 않고 이 실행에만 얹는다 (opencode 1.18.33 실측).
_CONFIG_CONTENT = json.dumps({"permission": {"external_directory": {"/tmp/**": "allow"}}})
_PERMISSION_RE = re.compile(r"permission requested:.*", re.I)

_TIMEOUT_RE = re.compile(r"timed? ?out", re.I)


def _brief_ref(brief_path: str, cwd: pathlib.Path) -> str:
    """작업 폴더 안이면 상대 경로, 밖이면 절대 경로."""
    b = pathlib.Path(brief_path)
    if not b.is_absolute():
        return str(b)
    try:
        return str(b.resolve().relative_to(cwd.resolve()))
    except ValueError:
        return str(b)


def _head(spec: SessionSpec) -> str:
    # 슬롯·토큰·REV 를 메시지 자체에 싣는다 - 지시문 파일을 읽기 전에 '슬롯 없음' 으로 끝나지 않게
    return (spec.ident.strip() + " ") if spec.ident and spec.ident.strip() else ""


def _summarize_input(inp) -> str:
    if isinstance(inp, dict):
        for k in ("command", "filePath", "path", "pattern", "url", "description"):
            if inp.get(k):
                return _one_line(inp[k])
        return _one_line(json.dumps(inp, ensure_ascii=False))
    return _one_line(inp) if inp else ""


def _error_message(obj: dict) -> str:
    err = obj.get("error")
    if isinstance(err, dict):
        data = err.get("data")
        msg = data.get("message") if isinstance(data, dict) else None
        msg = msg or err.get("message")
        name = err.get("name")
        if msg and name:
            return f"{name}: {msg}"
        return str(msg or name or json.dumps(err, ensure_ascii=False))
    return str(err) if err else json.dumps(obj, ensure_ascii=False)


def _loads(line: str):
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _session_objs(session_dir):
    """events.jsonl 의 JSON 사건 객체들 (깨진 줄은 건너뜀)."""
    for _at, raw in base.read_event_lines(session_dir):
        obj = _loads(raw)
        if obj is not None:
            yield obj


def _stderr(session_dir) -> str:
    try:
        return base._ANSI_RE.sub("", (pathlib.Path(session_dir) / "stderr.log").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def _error_messages(session_dir) -> list:
    return [_error_message(o) for o in _session_objs(session_dir) if o.get("type") == "error"]


class OpencodeHarness:
    name = "opencode"

    def command(self, spec: SessionSpec) -> Command:
        cwd = require_repo_cwd(spec.cwd, "opencode")
        argv = list(_BASE_ARGV)
        if spec.model:
            argv += ["-m", spec.model]
        msg = (_head(spec) + "다음 파일이 이 지시의 전문이다. 읽고 그 안의 지시를 그대로 수행하라"
               "(파일 자체는 수정하지 말라): " + _brief_ref(spec.brief_path, cwd))
        return Command(argv=argv + [msg], cwd=str(spec.cwd), stdin_path=None,
                       env_set={"OPENCODE_CONFIG_CONTENT": _CONFIG_CONTENT})

    def parse_event(self, line: str) -> Optional[Event]:
        if not line or not line.strip():
            return None
        raw = line.rstrip("\n")
        obj = _loads(line)
        if obj is None:
            return Event("raw", raw, {}, raw)
        t = obj.get("type")
        part = obj.get("part") if isinstance(obj.get("part"), dict) else {}
        if t == "text":
            text = part.get("text")
            if not isinstance(text, str) or not text.strip():
                return None
            return Event("text", text, {}, raw)
        if t == "tool_use":
            st = part.get("state") if isinstance(part.get("state"), dict) else {}
            name = str(part.get("tool") or "tool")
            summary = _one_line(st.get("title") or "") or _summarize_input(st.get("input"))
            text = f"{name}: {summary}" if summary else name
            return Event("tool", text, {"name": name, "input": st.get("input"), "status": st.get("status")}, raw)
        if t == "step_finish":
            tk = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
            data = {"reason": part.get("reason")}
            if "input" in tk:
                data["tokens_in"] = tk["input"]
            if "output" in tk:
                data["tokens_out"] = tk["output"]
            if "cost" in part:
                data["cost_usd"] = part["cost"]
            return Event("usage", "", data, raw)
        if t == "step_start":
            return Event("raw", "", {"harness_session_id": obj.get("sessionID")}, raw)
        if t == "error":
            msg = _error_message(obj)
            data = {}
            if LIMIT_RE.search(msg):
                data["limit"] = True
            if _TIMEOUT_RE.search(msg):
                data["timeout"] = True
            return Event("error", msg, data, raw)
        return Event("raw", raw, {}, raw)

    def final_report(self, session_dir) -> str:
        step_texts: list = []      # 마지막 step 의 text 조각들
        last_text = ""             # 스트림 전체의 마지막 비지 않은 text
        last_reason, tool_error = None, ""
        for obj in _session_objs(session_dir):
            t = obj.get("type")
            part = obj.get("part") if isinstance(obj.get("part"), dict) else {}
            if t == "step_start":
                step_texts = []
            elif t == "text":
                s = part.get("text")
                if isinstance(s, str):
                    step_texts.append(s)
                    if s.strip():
                        last_text = s.strip()
            elif t == "step_finish":
                last_reason = part.get("reason")
            elif t == "tool_use":
                st = part.get("state") if isinstance(part.get("state"), dict) else {}
                tool_error = _one_line(st.get("error") or "") if st.get("status") == "error" else ""
        if last_reason == "tool-calls":
            # 도구 결과를 기다리던 걸음에서 끝났다 = 답을 맺지 못하고 끊겼다 (권한 거절 따위). 앞 걸음의 혼잣말을 보고로
            # 내지 않는다 - 그것이 done 으로 받아들여진다 (R41 T-385). 까닭을 아는 만큼 적는다
            why = [m.group(0).strip() for m in _PERMISSION_RE.finditer(_stderr(session_dir))][-3:]
            why += [tool_error] if tool_error else []
            return "\n".join([base.NO_REPORT, "작업자가 답을 맺지 못하고 도구 호출 도중에 끝났다."] + why
                             + _error_messages(session_dir))
        report = "".join(step_texts).strip() or last_text
        if report:
            return report
        return base.no_report_tail(session_dir, _error_messages(session_dir))

    def limit_signal(self, session_dir) -> Optional[bool]:
        last = None
        for obj in _session_objs(session_dir):
            if obj.get("type") == "error" and LIMIT_RE.search(_error_message(obj)):
                return True
            last = obj
        if last and last.get("type") == "step_finish" and (last.get("part") or {}).get("reason") == "stop":
            return False
        return None

    def resume_command(self, spec, harness_session_id, message_path):
        return None                     # 작업자는 일회성이라 잇지 않는다

    def probe(self) -> ProbeResult:
        exe = shutil.which("opencode")
        if not exe:
            return ProbeResult(False, None, None, "opencode 실행 파일을 PATH 에서 찾지 못함")
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            return ProbeResult(False, exe, None, f"opencode --version 실패: {e}")
        ver = (r.stdout or "").strip().splitlines()
        if r.returncode != 0 or not ver:
            return ProbeResult(False, exe, None, f"opencode --version rc={r.returncode}")
        return ProbeResult(True, exe, ver[0].strip())


ADAPTER = OpencodeHarness()
