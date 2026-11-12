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
from ..base import Command, Event, ProbeResult, SessionSpec

_BASE_ARGV = ["opencode", "run", "--format", "json"]

# 한도·시간 초과 낱말. 구조화된 코드가 없어 문구로 알아본다.
_LIMIT_RE = re.compile(r"\b429\b|rate[\s_-]?limit|quota|usage limit|too many requests", re.I)
_TIMEOUT_RE = re.compile(r"timed? ?out", re.I)

_NO_REPORT = "(최종 보고문 없음 - 작업자가 보고 전에 끝남. stderr 꼬리:)"


def _require_repo_cwd(cwd) -> pathlib.Path:
    """진짜 하네스는 함대 저장소 안에서만 띄운다.

    2026-11-12 에 /tmp 검수 사본에서 진짜 작업자가 떴던 일이 있어, `tools/fleet.py` 가 있는 폴더만 허용한다.
    """
    p = pathlib.Path(str(cwd))
    if not p.is_dir() or not (p / "tools" / "fleet.py").is_file():
        raise ValueError(f"함대 저장소가 아닌 작업 폴더에서는 하네스를 띄우지 않는다: {cwd!r}")
    return p


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
    # 슬롯·토큰·REV 를 메시지 자체에 싣는다 - 파일을 읽기 전에 '슬롯 ID 없음' 으로 빈손 종료한 전례 (fleet.py 주석)
    return (spec.ident.strip() + " ") if spec.ident and spec.ident.strip() else ""


def _one_line(s, limit=120) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= limit else s[:limit - 1] + "…"


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


def _error_messages(session_dir) -> list:
    return [_error_message(o) for o in _session_objs(session_dir) if o.get("type") == "error"]


class OpencodeHarness:
    name = "opencode"

    def command(self, spec: SessionSpec) -> Command:
        cwd = _require_repo_cwd(spec.cwd)
        argv = list(_BASE_ARGV)
        if spec.model:
            argv += ["-m", spec.model]
        msg = (_head(spec) + "다음 파일이 이 지시의 전문이다. 읽고 그 안의 지시를 그대로 수행하라"
               "(파일 자체는 수정하지 말라): " + _brief_ref(spec.brief_path, cwd))
        return Command(argv=argv + [msg], cwd=str(spec.cwd), stdin_path=None)

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
            if _LIMIT_RE.search(msg):
                data["limit"] = True
            if _TIMEOUT_RE.search(msg):
                data["timeout"] = True
            return Event("error", msg, data, raw)
        return Event("raw", raw, {}, raw)

    def final_report(self, session_dir) -> str:
        step_texts: list = []      # 마지막 step 의 text 조각들
        last_text = ""             # 스트림 전체의 마지막 비지 않은 text
        for obj in _session_objs(session_dir):
            t = obj.get("type")
            if t == "step_start":
                step_texts = []
            elif t == "text":
                s = (obj.get("part") or {}).get("text")
                if isinstance(s, str):
                    step_texts.append(s)
                    if s.strip():
                        last_text = s.strip()
        report = "".join(step_texts).strip() or last_text
        if report:
            return report
        # 보고문 없이 끝남 - stderr 에서 도구 로그를 걷어낸 꼬리와 error 사건 문구를 보여 준다
        sd = pathlib.Path(session_dir)
        try:
            err = (sd / "stderr.log").read_text(encoding="utf-8", errors="replace")
        except OSError:
            err = ""
        err = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", err)
        kept = [l for l in err.splitlines()
                if l.strip() and not re.match(r"^\s*(←|✗|!|\||\+|-|@|\$|>)", l)]
        parts = kept[-25:] + _error_messages(session_dir)
        tail = "\n".join(parts).strip()
        return f"{_NO_REPORT}\n{tail}" if tail else ""

    def limit_signal(self, session_dir) -> Optional[bool]:
        last = None
        for obj in _session_objs(session_dir):
            if obj.get("type") == "error" and _LIMIT_RE.search(_error_message(obj)):
                return True
            last = obj
        if last and last.get("type") == "step_finish" and (last.get("part") or {}).get("reason") == "stop":
            return False
        return None

    def resume_command(self, spec: SessionSpec, harness_session_id: str, message_path: str) -> Optional[Command]:
        cwd = _require_repo_cwd(spec.cwd)
        argv = list(_BASE_ARGV) + ["-s", harness_session_id]
        if spec.model:
            argv += ["-m", spec.model]
        msg = ("이어서 할 일이 다음 파일에 있다. 읽고 그대로 수행하라(파일 자체는 수정하지 말라): "
               + _brief_ref(message_path, cwd))
        return Command(argv=argv + [msg], cwd=str(spec.cwd), stdin_path=None)

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
