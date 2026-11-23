"""freebuff 어댑터 - 사람이 연 tmux 팬 하나를 거쳐 일을 시킨다 (freebuff 0.2.36 실측).

freebuff 는 화면으로만 쓰고, 한 사람이 세션 하나만 열 수 있으며, **지시는 사람이 해야 한다.** 그래서 이 하네스의
세션은 뜨자마자 일하지 않는다:

    await   세션 폴더에 `approve.json` 이 생기기를 기다린다. 이 파일은 **모니터의 '보내기' 단추만** 쓴다 -
            사람이 지시문을 읽고(고치고) 누른 것이 최종 지시다. 엔진·관리자·작업자는 쓰지 않는다
    sent    팬에 새 대화를 열고(`/new`) **고정된 한 줄**('이 파일을 읽고 수행하라' + 지시문 파일 경로)과 엔터를 넣었다.
            지시문 본문은 팬에 치지 않는다 - 팬에 치는 글이 자유로우면 freebuff 의 `/bash` 로 명령을 치는 통로가 된다
    done    freebuff 가 디스크에 적는 대화(`<chats>/<작업 폴더 이름>/chats/<시각>/chat-messages.json`)에서 답이 끝났다

지금 단계는 세션 폴더의 `gate.json` 에 적는다(`{"phase","since","sent_at","by","error","pane"}`) - 그래프 실행기와
모니터가 읽는다. 사람 승인 뒤에야 일하는 하네스라는 표시는 `ADAPTER.approval = True` 하나이고, 엔진은 하네스 이름이
아니라 이 표시와 `gate.json` 만 본다.

설정은 `fleet.toml [harness.freebuff]`: `pane`(tmux 팬, 기본 `freebuff:0.0`), `chats`(대화 저장 폴더, 기본
`~/.config/manicode/projects`). 이 파일은 어댑터이자 운전기다 - 감독이 `python3 freebuff.py <세션 폴더>` 로 띄운다.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time

if __package__:
    from .. import base
    from ..base import Command, Event, ProbeResult, one_line, require_repo_cwd
else:   # `python3 freebuff.py <세션 폴더>` - 꾸러미 밖이라 상대 import 가 안 된다
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from fleet_rt import base
    from fleet_rt.base import Command, Event, ProbeResult, one_line, require_repo_cwd

_SELF = str(pathlib.Path(__file__).resolve())

DEFAULT_PANE = "freebuff:0.0"
DEFAULT_CHATS = "~/.config/manicode/projects"
GATE_FILE = "gate.json"
APPROVE_FILE = "approve.json"
#: 보내기를 이만큼 기다리다 스스로 끝난다 - 그래프 밖에서 띄운 세션이 영영 남지 않게 (그래프는 제 규칙으로 먼저 끊는다).
AWAIT_MAX_SEC = 12 * 3600.0
#: 보낸 뒤 답을 기다리는 한도 기본 (`meta.extra.work_timeout` 이 있으면 그것).
WORK_TIMEOUT_SEC = base.DEFAULT_NODE_TIMEOUT_SEC
POLL_SEC = 2.0
#: 대화 파일이 이만큼 안 바뀌어야 끝난 답으로 본다.
SETTLE_SEC = 3.0
RC_UNSENT, RC_TIMEOUT = 3, 124
UNSENT_REPORT = "BLOCKED\n사람이 '보내기' 를 누르지 않아 freebuff 에 지시가 나가지 않았다. 한 일이 없다."

_PLACEHOLDER_RE = re.compile(r"enter a coding task", re.I)
_HELD_RE = re.compile(r"session was released|choose a model to start", re.I)     # 세션이 끝나 지시가 창에 걸려 있다
HELD_TEXT = ("freebuff 세션이 끝나 있어 지시가 팬에 걸려 있습니다 - 팬에서 Enter 를 누르면 이어집니다 "
             "(한도 안에 열지 않으면 시간 초과로 끝납니다)")
_LEFT_RE = re.compile(r"(\d+\s*[hm](?:\s*\d+\s*m)?)\s+left\b")
_MODEL_RE = re.compile(r"^\s*(.+?)\s+·\s+.*?/model to change")
_PANE_RE = re.compile(r"\A[A-Za-z0-9_.:@%$-]{1,80}\Z")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]+")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- 설정·팬 (모니터도 쓴다)

def settings(root):
    """`(팬, 대화 폴더)` - `fleet.toml [harness.freebuff]`. 못 읽으면 기본값."""
    h = {}
    try:
        if __package__:
            from .. import config
        else:
            from fleet_rt import config
        h = config.load(root).harness("freebuff") or {}
    except Exception:  # noqa: BLE001 - 설정이 깨져도 기본 팬으로
        h = {}
    pane = str(h.get("pane") or DEFAULT_PANE)
    if not _PANE_RE.match(pane):
        pane = DEFAULT_PANE
    return pane, pathlib.Path(os.path.expanduser(str(h.get("chats") or DEFAULT_CHATS)))


def _tmux(*args, timeout=5.0):
    try:
        r = subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", f"{e.__class__.__name__}: {e}"
    return r.returncode, r.stdout or "", (r.stderr or "").strip()


def pane_status(pane):
    """팬의 지금 모습(읽기만): `{"ok","why","input_empty","left","model","lines"}`.

    `ok` 는 '지시를 넣어도 되는가' - 팬이 있고 입력 칸이 비어 있을 때만. `left` 는 화면에 보이는 남은 세션 시간('8m'),
    없으면 None (세션이 끝났거나 아직 안 열렸다 - 막지는 않고 사람이 보고 정한다).
    """
    out = {"ok": False, "why": "", "input_empty": False, "left": None, "model": None, "lines": [], "held": False}
    rc, text, err = _tmux("capture-pane", "-p", "-t", pane)
    if rc != 0:
        out["why"] = f"tmux 팬 {pane} 을(를) 읽지 못했습니다" + (f" ({one_line(err, 80)})" if err else "")
        return out
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-14:]
    out["lines"] = [one_line(ln, 160) for ln in tail if not set(ln.strip()) <= set("╭╮╰╯│─┌┐└┘ ")][-8:]
    for ln in tail:
        if _HELD_RE.search(ln):
            out["held"] = True
        if _PLACEHOLDER_RE.search(ln):
            out["input_empty"] = True
        m = _LEFT_RE.search(ln)
        if m:
            out["left"] = " ".join(m.group(1).split())
        m = _MODEL_RE.match(ln)
        if m:
            out["model"] = m.group(1).strip()
    if not out["model"]:
        out["why"] = f"팬 {pane} 에 freebuff 화면이 보이지 않습니다"
    elif not out["input_empty"]:
        out["why"] = "freebuff 입력 칸이 비어 있지 않거나 다른 화면이 떠 있습니다"
    else:
        out["ok"] = True
    return out


LINE_TEXT_MAX = 300
HELD_CHECKS = 4          # 보낸 뒤 몇 초 동안 '세션 끝남' 창을 살피나


def brief_ref(session_dir, cwd):
    """지시문 파일을 팬의 작업 폴더에서 본 경로."""
    brief = pathlib.Path(session_dir) / "brief.md"
    try:
        return str(brief.resolve().relative_to(pathlib.Path(cwd).resolve()))
    except ValueError:
        return str(brief)


def compose_line(text, ref):
    """팬에 넣는 한 줄 = **사람이 고르거나 쓴 문구** + 지시문 파일 경로. `(줄, 까닭)`.

    문구는 기계가 정하지 않는다 - 기본값도 없다. 여기서는 한 줄인지, 명령(`/…`)으로 읽히지 않는지만 본다.
    """
    if not isinstance(text, str) or _CTRL_RE.search(text.strip()):
        return None, "문구는 한 줄이어야 합니다"
    text = " ".join(text.split())
    if not text:
        return None, "팬에 던질 문구를 고르거나 쓰십시오"
    if len(text) > LINE_TEXT_MAX:
        return None, f"문구가 너무 깁니다 ({LINE_TEXT_MAX}자까지)"
    if text[0] in "/@!":
        return None, "문구는 / @ ! 로 시작할 수 없습니다 (freebuff 명령으로 읽힙니다)"
    ref = _CTRL_RE.sub("", str(ref))
    return (text if ref in text else f"{text} {ref}"), ""


def send_line(pane, line):
    """새 대화를 열고 `line` 과 엔터를 넣는다. `(됐나, 까닭)`. 넣기 직전마다 입력 칸이 비었는지 다시 본다."""
    if "\n" in line or "\r" in line or not line.strip() or line.startswith("/"):
        return False, "보낼 줄이 올바르지 않습니다"
    for keys, wait in ((("-l", "--", "/new"), 0.6), (("Enter",), 2.0)):
        rc, _o, err = _tmux("send-keys", "-t", pane, *keys)
        if rc != 0:
            return False, f"팬에 넣지 못했습니다 ({one_line(err, 80)})"
        time.sleep(wait)
    st = pane_status(pane)
    if not st["ok"]:
        return False, "새 대화를 연 뒤 " + (st["why"] or "팬이 준비되지 않았습니다")
    for keys, wait in ((("-l", "--", line), 0.8), (("Enter",), 0.0)):
        rc, _o, err = _tmux("send-keys", "-t", pane, *keys)
        if rc != 0:
            return False, f"팬에 넣지 못했습니다 ({one_line(err, 80)})"
        time.sleep(wait)
    # 사용 세션이 끝나 있었으면 freebuff 가 'session was released … Enter: retry' 창에 그 줄을 세워 둔다.
    # 같은 줄을 마저 넣는 엔터를 한 번 더 넣는다 (2026-11-23 실물 확인: 쓰던 모델로 세션이 열리고 그 줄이 들어간다).
    for _ in range(HELD_CHECKS):
        time.sleep(1.0)
        if pane_status(pane)["held"]:
            _tmux("send-keys", "-t", pane, "Enter")
            break
    return True, ""


def read_gate(session_dir):
    """세션의 `gate.json` (없거나 깨졌으면 None)."""
    try:
        d = json.loads((pathlib.Path(session_dir) / GATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("phase") else None


def _write_json(p, obj):
    tmp = pathlib.Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def approve(session_dir, by, line):
    """사람의 '보내기' 와 그 사람이 고른 한 줄을 적는다 (**모니터의 단추만 부른다**). 기다리는 세션이 아니면 `(False, 까닭)`."""
    d = pathlib.Path(session_dir)
    g = read_gate(d)
    if not g or g.get("phase") != "await":
        return False, "보내기를 기다리는 세션이 아닙니다" + (f" (지금 {g.get('phase')})" if g else "")
    if (d / "end.json").exists():
        return False, "이미 끝난 세션입니다"
    if g.get("busy"):
        return False, "지금 팬에 넣는 중입니다"
    if not isinstance(line, str) or not line.strip():
        return False, "팬에 던질 문구가 없습니다"
    _write_json(d / APPROVE_FILE, {"at": _now(), "by": str(by or "")[:80], "line": line})
    return True, ""


# ---------------------------------------------------------------- 대화 파일 읽기

def _load_chat(p):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, list) else None


def find_chat(chats_root, cwd, marker, since=0.0):
    """`marker`(세션 id)가 든 사용자 메시지가 있는 대화 파일. 없으면 None."""
    base_dir = pathlib.Path(chats_root) / pathlib.Path(cwd).name / "chats"
    try:
        cands = sorted((c for c in base_dir.iterdir() if c.is_dir()), key=lambda c: c.name, reverse=True)
    except OSError:
        return None
    for c in cands[:12]:
        p = c / "chat-messages.json"
        try:
            if p.stat().st_mtime < since - 5:
                continue
        except OSError:
            continue
        msgs = _load_chat(p)
        if msgs and any(isinstance(m, dict) and m.get("variant") == "user" and marker in str(m.get("content") or "")
                        for m in msgs):
            return p
    return None


def chat_blocks(msgs, marker):
    """`(조각 목록, 끝났나)` - 우리 지시 뒤에 온 답(ai 메시지들)의 조각. 생각(`reasoning`)은 뺀다.

    조각은 `("text", 글)` 또는 `("tool", 이름, 요약)`.
    """
    seen, out, done = False, [], False
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if m.get("variant") == "user":
            if marker in str(m.get("content") or ""):
                seen = True
            continue
        if not seen or m.get("variant") != "ai":
            continue
        done = bool(m.get("isComplete"))
        blocks = m.get("blocks") if isinstance(m.get("blocks"), list) else []
        if not blocks and str(m.get("content") or "").strip():
            out.append(("text", str(m["content"])))
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                if b.get("textType") != "reasoning" and str(b.get("content") or "").strip():
                    out.append(("text", str(b["content"])))
            elif b.get("type") == "tool":
                inp = b.get("input")
                summary = one_line(json.dumps(inp, ensure_ascii=False) if isinstance(inp, (dict, list)) else (inp or ""))
                out.append(("tool", str(b.get("toolName") or "tool"), summary))
    return out, done


def final_text(blocks):
    """마지막 도구 호출 뒤의 글(보고 본문). 없으면 글 전부."""
    tail = []
    for b in reversed(blocks):
        if b[0] != "text":
            break
        tail.append(b[1].strip())
    if not tail:
        tail = [b[1].strip() for b in reversed(blocks) if b[0] == "text"]
    return "\n\n".join(reversed(tail)).strip()


# ---------------------------------------------------------------- 어댑터

class FreebuffHarness:
    name = "freebuff"
    #: 사람이 승인해야 일하는 하네스 - 엔진은 이 표시와 `gate.json` 으로만 다르게 다룬다.
    approval = True

    def command(self, spec):
        cwd = require_repo_cwd(spec.cwd, "freebuff")
        return Command(argv=[sys.executable, _SELF, str(pathlib.Path(spec.brief_path).parent)], cwd=str(cwd))

    def parse_event(self, line):
        line = (line or "").strip()
        if not line:
            return None
        try:
            d = json.loads(line)
        except ValueError:
            return Event("raw", raw=line)
        if not isinstance(d, dict):
            return Event("raw", raw=line)
        t = d.get("type")
        if t == "text":
            return Event("text", str(d.get("text", "")), raw=line)
        if t == "tool":
            name = str(d.get("name", ""))
            return Event("tool", f"{name}: {d.get('summary', '')}".rstrip(": "), {"name": name}, line)
        if t == "error":
            return Event("error", str(d.get("text", "")), {"timeout": bool(d.get("timeout"))}, line)
        if t == "end":
            return Event("end", "", {"ok": bool(d.get("ok")), "result": d.get("result")}, line)
        return Event("raw", raw=line)

    def final_report(self, session_dir):
        result, last_text = None, ""
        for _at, raw in base.read_event_lines(session_dir):
            ev = self.parse_event(raw)
            if ev is None:
                continue
            if ev.kind == "end" and isinstance(ev.data.get("result"), str):
                result = ev.data["result"]
            elif ev.kind == "text" and ev.text.strip():
                last_text = ev.text.strip()
        if result and result.strip():
            return result.strip()
        g = read_gate(session_dir)
        if g and g.get("phase") == "unsent":     # 기다리는 중(await)에는 보고가 없다 - 화면이 '막힘' 으로 읽지 않게
            return UNSENT_REPORT
        return last_text or base.no_report_tail(session_dir)

    def limit_signal(self, session_dir):
        return None

    def resume_command(self, spec, harness_session_id, message_path):
        return None

    def probe(self):
        exe = shutil.which("tmux")
        if not exe:
            return ProbeResult(False, None, None, "tmux 실행 파일을 PATH 에서 찾지 못함")
        pane, _chats = settings(pathlib.Path(_SELF).parents[3])
        st = pane_status(pane)
        if not st["model"]:
            return ProbeResult(False, exe, None, st["why"] or f"팬 {pane} 에 freebuff 가 없음")
        return ProbeResult(True, exe, st["model"])


ADAPTER = FreebuffHarness()


# ---------------------------------------------------------------- 운전기

def _out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class Driver:
    def __init__(self, session_dir):
        self.d = pathlib.Path(session_dir)
        self.meta = json.loads((self.d / "meta.json").read_text(encoding="utf-8"))
        self.cwd = pathlib.Path(self.meta["cwd"])
        self.pane, self.chats = settings(self.cwd)
        self.gate = {"phase": "await", "since": _now(), "pane": self.pane}
        self.sent = False
        self.stop = False

    def _save(self, **kw):
        self.gate.update(kw)
        _write_json(self.d / GATE_FILE, self.gate)

    def _on_term(self, _sig, _frame):
        self.stop = True

    def _note(self, text):
        _out({"type": "tool", "name": "freebuff", "summary": text})

    def _await(self):
        """보내기를 기다렸다가 팬에 넣는다. 넣었으면 True, 못 넣고 끝내야 하면 False."""
        self._save()
        self._note(f"사람의 '보내기' 를 기다림 (팬 {self.pane})")
        deadline = time.monotonic() + AWAIT_MAX_SEC
        ap = self.d / APPROVE_FILE
        while not self.stop and time.monotonic() < deadline:
            if not ap.exists():
                time.sleep(0.5)
                continue
            try:
                said = json.loads(ap.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                said = None
            said = said if isinstance(said, dict) else {}
            who, line = said.get("by") or "", said.get("line")
            try:
                ap.unlink()          # 한 번 누르면 한 번만 보낸다 - 못 보냈으면 사람이 다시 누른다
            except OSError:
                pass
            self._save(busy=True)        # 팬에 넣는 몇 초 동안은 승인을 또 받지 않는다 (같은 지시가 두 번 적히지 않게)
            st = pane_status(self.pane)
            if not isinstance(line, str) or self.d.name not in line:
                ok, why = False, "사람이 고른 문구가 없습니다"       # 문구 없이는 보내지 않는다 - 기본 문구는 없다
            else:
                ok, why = (False, st["why"]) if not st["ok"] else send_line(self.pane, line)
            if ok:
                self.sent = True
                self._save(phase="sent", sent_at=_now(), by=str(who)[:80], error=None, busy=False)
                self._note(f"팬에 지시 한 줄을 넣음 (누른 사람: {who or '?'})")
                return True
            self._save(error=why, error_at=_now(), busy=False)
            _out({"type": "error", "text": f"보내지 못함: {why}"})
        return False

    def _work(self):
        marker = self.d.name
        extra = self.meta.get("extra") if isinstance(self.meta.get("extra"), dict) else {}
        try:
            limit = float(extra.get("work_timeout") or 0) or WORK_TIMEOUT_SEC
        except (TypeError, ValueError):
            limit = WORK_TIMEOUT_SEC
        t0, wall0 = time.monotonic(), time.time()
        emitted, chat = 0, None
        while not self.stop:
            if time.monotonic() - t0 > limit:
                st = pane_status(self.pane)
                _out({"type": "error", "timeout": True,
                      "text": f"보낸 뒤 {limit:g}초 안에 답이 끝나지 않음. 팬: " + " / ".join(st["lines"][-3:])})
                return RC_TIMEOUT, ""
            if chat is None:
                chat = find_chat(self.chats, self.cwd, marker, wall0)
                # 대화가 아직 안 생겼다 - 세션이 끝나 지시가 창에 걸렸는지 본다(읽기만). 푸는 것은 사람이 팬에서 한다
                held = chat is None and pane_status(self.pane)["held"]
                if held != bool(self.gate.get("held")):
                    self._save(held=HELD_TEXT if held else None)
                    if held:
                        _out({"type": "error", "text": HELD_TEXT})
            msgs = _load_chat(chat) if chat is not None else None
            if msgs:
                blocks, done = chat_blocks(msgs, marker)
                try:
                    settled = time.time() - chat.stat().st_mtime >= SETTLE_SEC
                except OSError:
                    settled = False
                done = done and settled and bool(blocks)
                upto = len(blocks) if done else max(len(blocks) - 1, 0)    # 쓰는 중인 마지막 조각은 다 쓴 뒤에
                for b in blocks[emitted:upto]:
                    _out({"type": "text", "text": b[1]} if b[0] == "text" else {"type": "tool", "name": b[1], "summary": b[2]})
                emitted = max(emitted, upto)
                if done:
                    return 0, final_text(blocks)
            time.sleep(POLL_SEC)
        return None, ""

    def run(self):
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(s, self._on_term)
        if not self._await():
            self._save(phase="unsent")
            _out({"type": "end", "ok": False, "result": UNSENT_REPORT})
            return RC_UNSENT
        rc, report = self._work()
        if rc is None:
            # 끊겼다(완전 중지·그래프 한도) - 팬에서 하던 일을 멈춘다. 지시가 아니라 멈춤 키 하나다.
            _tmux("send-keys", "-t", self.pane, "Escape")
            self._save(phase="cut")
            return 143
        self._save(phase="done" if rc == 0 else "timeout")
        if rc != 0:
            _tmux("send-keys", "-t", self.pane, "Escape")
        _out({"type": "end", "ok": rc == 0, "result": report})
        return rc


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("쓰임: freebuff.py <세션 폴더>")
    sys.exit(Driver(sys.argv[1]).run())
