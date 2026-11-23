"""freebuff 어댑터 - 사람이 연 tmux 팬 하나를 거쳐 일을 시킨다 (freebuff 0.2.36 실측).

freebuff 는 화면으로만 쓰고, 한 사람이 세션 하나만 열 수 있으며, **지시는 사람이 해야 한다.** 그래서 이 하네스의
세션은 뜨자마자 일하지 않는다:

    await   팬에 넣어도 된다는 승인(`approve.json`)을 기다린다. 승인은 **사람의 행위에서만** 나온다: 모니터의 '보내기',
            사람이 켜 둔 보내기 옵션, 사람이 쓴 1차 지시. 엔진·관리자·작업자는 쓰지 않는다
    (1차)   작업 지시보다 먼저, **사람이 직접 쓴 글**(1차 지시)이 팬에 들어간다 - 모니터의 창·보내기 칸에 쓴 것,
            또는 노드에 미리 써 둔 것. 단계는 그대로 await 이고 `first_at` 이 적힌다
    sent    그 대화에 이어서 **작업 지시 한 줄**을 넣었다: 작업 요지 + 사람이 고르거나 미리 고른 문구 + 지시문 파일 경로(맨 뒤).
            지시문 본문은 팬에 치지 않는다 - 팬에 치는 글이 자유로우면 freebuff 의 `/bash` 로 명령을 치는 통로가 된다
    done    freebuff 가 디스크에 적는 대화(`<chats>/<작업 폴더 이름>/chats/<시각>/chat-messages.json`)에서 답이 끝났다
    refused freebuff 가 줄을 사용 정책(자동 사용)으로 거절했다 - 다시 보내지 않고 BLOCKED 로 끝내며,
            보내기 옵션을 끈다 (다시 켜는 것은 사람)

세션이 일하는 도중 끝나면 await 로 돌아가고(`resume`), 같은 대화에 이어 가라는 줄을 넣는다 - 1차 지시는 이미 그 대화에
있으므로 다시 받지 않는다(옵션이 켜져 있으면 사람 손 없이 이어진다). 사람이 팬에 직접 친 글은 1차 지시로 치지 않는다 -
1차 지시는 모니터를 거친 것만이다.

지금 단계는 세션 폴더의 `gate.json` 에 적는다(`phase`·`since`·`sent_at`·`by`·`error`·`error_at`·`pane`·`busy`·`first_at`·
`first_by`·`resume`·`held`) - 그래프 실행기와 모니터가 읽는다. 사람 승인 뒤에야 일하는 하네스라는 표시는
`ADAPTER.approval = True` 하나이고, 엔진은 하네스 이름이 아니라 이 표시와 `gate.json` 만 본다.

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
LINE_TEXT_MAX = 300      # 사람이 고르거나 쓴 문구의 길이 (글자)
GIST_MAX = 200           # 이어 보내는 줄 앞에 붙는 작업 요지의 길이 (글자)
DEFAULT_CHATS = "~/.config/manicode/projects"
GATE_FILE = "gate.json"
APPROVE_FILE = "approve.json"
#: 보내기를 이만큼 기다리다 스스로 끝난다 - 그래프 밖에서 띄운 세션이 영영 남지 않게 (그래프는 제 규칙으로 먼저 끊는다).
AWAIT_MAX_SEC = 12 * 3600.0
#: 보낸 뒤 이만큼 대화 파일도 안 자라고 freebuff 가 CPU 도 안 쓰면 멈춘 것으로 본다. 일하는 동안은 한도가 없다.
QUIET_SEC = base.DEFAULT_IDLE_TIMEOUT_SEC
CPU_CHECK_SEC = 10.0
POLL_SEC = 2.0
#: 대화 파일이 이만큼 안 바뀌어야 끝난 답으로 본다.
SETTLE_SEC = 3.0
RC_UNSENT, RC_TIMEOUT = 3, 124
RESUME = "resume"        # `_work` 의 답: 세션이 끝나 멈췄다 - 같은 대화에 이어 보낸다
REFUSED = "refused"      # `_work` 의 답: freebuff 가 사용 정책으로 그 줄을 거절했다 - 다시 보내지 않는다
#: freebuff 가 줄을 모델에 보내지 않고 거절할 때의 글 (2026-11-23 R39 실물: "Freebuff did not send this message to the
#: model. It breaks the usage policy (Scripted or automated use) …"). 다시 보내면 같은 일을 한 번 더 하는 셈이다.
_REFUSED_RE = re.compile(r"usage policy|did not send this message", re.I)
#: 사용 세션이 끝나 답이 멈췄을 때의 글 (R37 실물: "Your free session ended, so the agent stopped here.").
#: 이 글일 때만 같은 대화에 이어 보낸다 - 다른 오류는 실패다.
_ENDED_RE = re.compile(r"session (?:has )?(?:ended|expired)|session was released", re.I)
#: '미리 고른 문구 전송' 옵션의 상태 파일 - 모니터가 읽고 쓴다. 운전기는 거절을 만났을 때 **끄기만** 한다.
AUTO_FILE = ".aimem/pane_auto.json"
#: freebuff 사용 세션의 기록(한 줄에 한 세션) - 하루에 몇 세션을 썼는지 센다. 세션은 열리면 일을 안 해도 한 시간 뒤 끝난다.
SESSION_LOG = ".aimem/freebuff_sessions.jsonl"
SESSION_SEC = 3600
UNSENT_REPORT = "BLOCKED\n사람이 '보내기' 를 누르지 않아 freebuff 에 지시가 나가지 않았다. 한 일이 없다."
UNSENT_REPORT_FIRST = ("BLOCKED\n사람의 1차 지시는 팬에 들어갔지만 그 뒤 작업 지시가 나가지 않았다. "
                       "맡긴 일은 한 것이 없다.")

_PLACEHOLDER_RE = re.compile(r"enter a coding task", re.I)
_HELD_RE = re.compile(r"session was released|choose a model to start", re.I)     # 세션이 끝나 지시가 창에 걸려 있다
HELD_TEXT = ("freebuff 세션이 끝나 있어 지시가 팬에 걸려 있습니다 - 팬에서 Enter 를 누르면 이어집니다 "
             "(오래 열지 않으면 멈춘 것으로 보고 끊습니다)")
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


def auto_state(root):
    """'미리 고른 문구 전송' 옵션: `{"on","at","by","refused"}`.

    켜져 있으면 모니터가 절차를 밟는다: 사람의 1차 지시(창으로 받거나 노드에 써 둔 것) → 그 답이 끝남 → 몇 초 뒤 작업
    지시를 같은 대화에 이음. `refused` 는 freebuff 의 거절로 꺼졌다는 표시다.
    """
    try:
        d = json.loads((pathlib.Path(root) / AUTO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = None
    d = d if isinstance(d, dict) else {}
    return {"on": d.get("on") is True, "at": d.get("at"), "by": d.get("by"), "refused": d.get("refused") is True}


def auto_set(root, on, by, refused=False):
    """옵션을 켜거나 끈다. 켜는 것은 사람(모니터)만 - 운전기는 거절을 만나면 `refused=True` 로 끄기만 한다."""
    p = pathlib.Path(root) / AUTO_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    d = {"on": on is True, "at": _now(), "by": str(by or "")[:80]}
    if refused and not d["on"]:
        d["refused"] = True
    _write_json(p, d)
    return auto_state(root)


#: 함대가 팬에 넣는 줄에는 늘 지시문 파일 경로가 들어 있다 - 이것이 없는 사용자 메시지는 사람이 직접 쓴 것이다.
_FLEET_LINE_RE = re.compile(r"\.aimem/sessions/[^/\s]+/brief\.md")


def human_turn_done(chats_root, cwd, since=0.0, now=None):
    """사람의 1차 지시(모니터가 팬에 넣은 것)의 답이 정상으로 끝나 있으면 `(대화 파일, 바뀐 시각)`, 아니면 None.
    부르는 쪽은 1차 지시를 넣은 시각을 `since` 로 준다 - 그 전의 대화는 치지 않는다.

    가장 최근에 바뀐 대화만 본다. 마지막 사용자 메시지가 사람의 것이고(함대의 줄이 아님), 그 뒤 답이 `completionTime` 으로
    끝났고, 파일이 `since` 뒤에 바뀌어 `SETTLE_SEC` 동안 조용해야 한다. 함대가 이어 보내면 마지막 사용자 메시지가
    함대의 줄이 되므로, 사람의 지시 하나는 기다리는 지시 하나만 내보낸다.
    """
    now = time.time() if now is None else now
    base_dir = pathlib.Path(chats_root) / pathlib.Path(cwd).name / "chats"
    best, best_m = None, 0.0
    try:
        for c in base_dir.iterdir():
            try:
                m = (c / "chat-messages.json").stat().st_mtime
            except OSError:
                continue
            if m > best_m:
                best, best_m = c / "chat-messages.json", m
    except OSError:
        return None
    if best is None or best_m < since or now - best_m < SETTLE_SEC:
        return None
    msgs = [m for m in (_load_chat(best) or []) if isinstance(m, dict)]
    users = [i for i, m in enumerate(msgs) if m.get("variant") == "user"]
    if not users or users[-1] == len(msgs) - 1:
        return None
    if _FLEET_LINE_RE.search(str(msgs[users[-1]].get("content") or "")):
        return None
    last = msgs[-1]
    if last.get("variant") != "ai" or not last.get("completionTime") or last.get("userError"):
        return None
    return best, best_m


#: 관리자가 지시문에 적는 요지 줄 - `요지: <무엇을 어떻게, 끝난 기준>` (한 줄)
_GIST_LINE_RE = re.compile(r"^[ \t>*-]*요지[ \t]*[:：][ \t]*(\S.*)$", re.M)


def brief_gist(session_dir, meta=None, limit=GIST_MAX):
    """작업의 요지 한 줄(`limit` 자까지 - 짧아도 된다) - 작업 지시 줄의 **앞**에 온다.

    관리자가 지시문에 적은 `요지: …` 줄을 쓴다(노드마다 같은 꼴). 그 줄이 없으면 제목과 본문 첫머리에서 뽑는다.
    줄마다 글이 달라지게 하려는 것이다(같은 문구만 되풀이되면 freebuff 가 기계 입력으로 본다). 팬에 치는 글이므로
    한 줄로 펴고, 명령·파일 고르기로 읽힐 글자(`/` 로 시작, `@`, `!`)와 제어 글자를 뺀다. 못 뽑으면 빈 글.
    """
    meta = meta if isinstance(meta, dict) else {}
    title = re.sub(r"^\s*T-\d+\s*", "", str(meta.get("label") or ""))
    title = re.sub(r"\s*\(G-\d+\)\s*$", "", title).strip()
    body = ""
    try:
        text = (pathlib.Path(session_dir) / "brief.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    head, sep, rest = text.partition("\n\n")          # 머리(슬롯·토큰·쓰기 범위) 뒤가 일의 본문이다
    if sep:
        body = rest
    written = _GIST_LINE_RE.search(text)
    if written:
        title, body = "", written.group(1)             # 관리자가 쓴 요지 - 제목을 덧붙이지 않는다
    out = " ".join(_CTRL_RE.sub(" ", f"{title}. {body}" if title and body else title or body).split())
    out = out.replace("@", "").replace("`", "").replace("!", ".").lstrip("/ ")
    if len(out) > limit:
        cut = out[:limit]
        stop = max(cut.rfind(". "), cut.rfind("다. "), cut.rfind(" "))
        out = (cut[:stop] if stop > limit * 0.6 else cut).rstrip(" .,") + " …"
    return out


def live_session(chats_root, now=None):
    """지금 열린 freebuff 사용 세션이 끝나는 시각(epoch 초). 열린 세션이 없거나 못 읽으면 None.

    freebuff 가 `<chats 의 윗 폴더>/freebuff-live-<pid>.json` 에 `expiresAt`(ms)을 적어 둔다 (0.2.36 실측).
    화면의 '… left' 는 일하는 동안 안 보여서 이 파일을 본다. 읽기만 한다.
    """
    now = time.time() if now is None else now
    best = None
    try:
        files = list(pathlib.Path(chats_root).parent.glob("freebuff-live-*.json"))
    except OSError:
        return None
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            exp = float(d["expiresAt"]) / 1000.0
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if exp > now and (best is None or exp > best):
            best = exp
    return best


def _session_rows(root):
    rows = []
    try:
        for ln in (pathlib.Path(root) / SESSION_LOG).read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict) and isinstance(d.get("expires"), (int, float)):
                rows.append(d)
    except OSError:
        pass
    return rows


def note_session(root, chats_root, run=None, now=None):
    """열린 세션이 기록에 없으면 한 줄 적는다. `(끝나는 시각 또는 None, 새로 적었나)`.

    같은 세션인지는 끝나는 시각으로 가른다 - 앞 기록보다 반 세션 넘게 뒤면 새 세션이다(조금 늘어난 것은 같은 세션).
    """
    exp = live_session(chats_root, now)
    if exp is None:
        return None, False
    rows = _session_rows(root)
    if rows and exp - float(rows[-1]["expires"]) < SESSION_SEC / 2:
        return exp, False
    p = pathlib.Path(root) / SESSION_LOG
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"start": round(exp - SESSION_SEC), "expires": round(exp), "seen": _now(),
                                **({"run": str(run)} if run else {})}, ensure_ascii=False) + "\n")
    except OSError:
        return exp, False
    return exp, True


def session_usage(root, chats_root, now=None):
    """화면용: `{"today": 오늘 연 세션 수, "expires": 지금 세션이 끝나는 시각(ISO) 또는 None}`."""
    now = time.time() if now is None else now
    day = datetime.date.fromtimestamp(now)
    today = sum(1 for r in _session_rows(root) if datetime.date.fromtimestamp(float(r["start"])) == day)
    exp = live_session(chats_root, now)
    return {"today": today,
            "expires": datetime.datetime.fromtimestamp(exp).isoformat(timespec="seconds") if exp else None}


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


HELD_CHECKS = 4          # 보낸 뒤 몇 초 동안 '세션 끝남' 창을 살피나


def brief_ref(session_dir, cwd):
    """지시문 파일을 팬의 작업 폴더에서 본 경로."""
    brief = pathlib.Path(session_dir) / "brief.md"
    try:
        return str(brief.resolve().relative_to(pathlib.Path(cwd).resolve()))
    except ValueError:
        return str(brief)


def _one_line(text, limit=LINE_TEXT_MAX):
    """팬에 넣을 글 한 줄의 검사: `(다듬은 글, "")` 또는 `(None, 까닭)`."""
    if not isinstance(text, str) or _CTRL_RE.search(text.strip()):
        return None, "문구는 한 줄이어야 합니다"
    text = " ".join(text.split())
    if not text:
        return None, "팬에 던질 문구를 고르거나 쓰십시오"
    if len(text) > limit:
        return None, f"문구가 너무 깁니다 ({limit}자까지)"
    if text[0] in "/@!":
        return None, "문구는 / @ ! 로 시작할 수 없습니다 (freebuff 명령으로 읽힙니다)"
    return text, ""


def follow_line(gist, phrase, ref):
    """작업 지시 한 줄 = 작업 요지(앞) + 사람이 고르거나 미리 고른 문구 + 지시문 파일 경로(맨 뒤). `(줄, 까닭)`.

    문구는 기계가 정하지 않는다 - 기본값도 없다. 여기서는 한 줄인지, 명령(`/…`)으로 읽히지 않는지만 본다.
    """
    text, why = _one_line(f"{gist} {phrase}" if gist else phrase, GIST_MAX + LINE_TEXT_MAX + 10)
    if text is None:
        return None, why
    return f"{text} {_CTRL_RE.sub('', str(ref))}", ""


def pane_pids(pane):
    """팬 안에서 도는 프로세스들(팬의 셸과 같은 세션). 못 찾으면 빈 목록."""
    rc, out, _err = _tmux("display-message", "-p", "-t", pane, "#{pane_pid}")
    try:
        sid = os.getsid(int(out.strip())) if rc == 0 else None
    except (OSError, ValueError):
        sid = None
    pids = []
    for p in (os.listdir("/proc") if sid is not None else ()):
        try:
            if p.isdigit() and os.getsid(int(p)) == sid:
                pids.append(int(p))
        except OSError:
            continue
    return pids


def send_line(pane, line, new=True, info=None):
    """새 대화를 열고(`new` - 이어 보낼 때는 열지 않는다) `line` 과 엔터를 넣는다. `(됐나, 까닭)`.
    넣기 직전마다 입력 칸이 비었는지 다시 본다. `info`(dict)를 주면 '세션 끝남' 창에 엔터를 한 번 더 넣었는지
    `info["held"]` 에 적는다."""
    if "\n" in line or "\r" in line or not line.strip() or line.startswith("/"):
        return False, "보낼 줄이 올바르지 않습니다"
    for keys, wait in ((("-l", "--", "/new"), 0.6), (("Enter",), 2.0)) if new else ():
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
            if info is not None:
                info["held"] = True
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


def approve_first(session_dir, by, text):
    """사람이 모니터의 '1차 지시' 창에 쓴 글을 적는다 - 운전기가 그것을 팬에 먼저 넣는다(작업 지시는 그 답이 끝난 뒤).
    글은 사람의 것이어야 한다: 한 줄이고, 지시문 파일 경로가 들어 있으면 안 된다. `(됐나, 까닭)`."""
    d = pathlib.Path(session_dir)
    g = read_gate(d)
    if not g or g.get("phase") != "await" or (d / "end.json").exists():
        return False, "보내기를 기다리는 세션이 아닙니다"
    if g.get("busy") or (d / APPROVE_FILE).exists():
        return False, "지금 팬에 넣는 중입니다"
    text, why = _one_line(text)
    if text is None:
        return False, why
    if _FLEET_LINE_RE.search(text):
        return False, "1차 지시에는 지시문 파일 경로를 넣지 않습니다 (직접 쓰는 글입니다)"
    _write_json(d / APPROVE_FILE, {"at": _now(), "by": str(by or "")[:80], "first": text})
    return True, ""


def approve(session_dir, by, line, same_chat=False):
    """작업 지시 한 줄을 팬에 넣어도 된다고 적는다 - **모니터만 부른다**(사람의 '보내기', 또는 사람이 켠 옵션).
    기다리는 세션이 아니면 `(False, 까닭)`.
    `same_chat` 이면 새 대화를 열지 않고 지금 대화에 이어 넣는다 (사람이 직접 쓴 지시 뒤에 잇는 경우)."""
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
    _write_json(d / APPROVE_FILE, {"at": _now(), "by": str(by or "")[:80], "line": line,
                                   **({"same_chat": True} if same_chat else {})})
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


def chat_tail(msgs, marker):
    """`(우리 지시 뒤에 온 답의 수, 마지막 답)` - 답이 정상으로 끝났는지 볼 때 쓴다. 답이 없으면 `(0, {})`.

    freebuff 는 끊긴 답·세션이 끝나 멈춘 답에도 `isComplete` 를 붙인다. 정상으로 끝난 답에만 `completionTime` 이 있고,
    세션이 끝나 멈춘 답에는 `userError` 가 있다 (2026-11-23 R37 실물).
    """
    seen, n, last = False, 0, {}
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if m.get("variant") == "user":
            seen = seen or marker in str(m.get("content") or "")
        elif seen and m.get("variant") == "ai":
            n, last = n + 1, m
    return n, last


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
        self.first = False        # 사람의 1차 지시를 팬에 넣었다 - 작업 지시는 그 대화에 잇는다
        self.first_text, self.first_wall = None, 0.0     # 답을 지켜볼 1차 지시 (거절·세션 끝남을 알아채려고)
        self.refusal = None       # freebuff 가 1차 지시를 사용 정책으로 거절한 글
        self.stop = False
        # 일하는 고리의 상태 - 세션이 끝나 같은 대화에 이어 보낼 때도 그대로 이어진다
        self.chat, self.blocks, self.emitted = None, [], 0
        self.answers = 0          # 이미 끝난 것으로 본 답의 수 (이어 보낸 뒤에는 그다음 답을 기다린다)
        self.progress = -1        # 마지막으로 보낼 때의 조각 수 - 그 뒤 하나도 안 늘고 또 멈추면 그만둔다

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
                if self.first_text and self._first_trouble():
                    return False
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
            if isinstance(said.get("first"), str):
                # 사람이 쓴 1차 지시 - 팬에 넣고 계속 기다린다. 작업 지시는 그 답이 끝난 뒤 같은 대화에 온다
                info, t0, wall0 = {}, _now(), time.time()      # 넣기 **전** 시각 - 답이 몇 초 만에 끝나도 그 뒤의 것으로 친다
                ok, why = (False, st["why"]) if not st["ok"] else send_line(
                    self.pane, said["first"], new=not self.sent and not self.first, info=info)
                if ok:
                    self.first, self.first_text, self.first_wall = True, said["first"], wall0
                    # since 도 옮긴다: 그래프의 '보내지 않음' 판정과 모니터가 이 1차 지시부터 다시 센다
                    self._save(first_at=t0, since=t0, first_by=str(who)[:80], error=None, busy=False)
                    self._note(f"사람이 쓴 1차 지시를 팬에 넣음 (쓴 사람: {who or '?'}) - 답이 끝나면 작업 지시를 잇는다")
                    self._note(self._session_note(info.get("held")))
                else:
                    self._save(error=why, error_at=_now(), busy=False)
                    _out({"type": "error", "text": f"1차 지시를 보내지 못함: {why}"})
                continue
            if not isinstance(line, str) or self.d.name not in line:
                ok, why = False, "사람이 고른 문구가 없습니다"       # 문구 없이는 보내지 않는다 - 기본 문구는 없다
            else:
                info = {}
                ok, why = (False, st["why"]) if not st["ok"] else send_line(
                    self.pane, line, new=not self.sent and not self.first and said.get("same_chat") is not True, info=info)
            if ok:
                self.sent, self.first_text = True, None
                self._save(phase="sent", sent_at=_now(), by=str(who)[:80], error=None, busy=False)
                self._note(f"팬에 지시 한 줄을 넣음 (누른 사람: {who or '?'})")
                self._note(self._session_note(info.get("held")))
                return True
            self._save(error=why, error_at=_now(), busy=False)
            _out({"type": "error", "text": f"보내지 못함: {why}"})
        return False

    def _first_trouble(self):
        """넣은 1차 지시의 답이 오류로 끝났는지 본다. 사용 정책 거절이면 True(끝낸다) - 그 밖의 오류는 적고 다시 받는다."""
        chat = find_chat(self.chats, self.cwd, self.first_text, self.first_wall)
        msgs = _load_chat(chat) if chat is not None else None
        n, last = chat_tail(msgs, self.first_text) if msgs else (0, {})
        err = one_line(str(last.get("userError") or ""), 200) if n else ""
        if not err:
            return False
        self.first_text = None
        if _REFUSED_RE.search(err):
            self.refusal = err
            return True
        # 세션이 끝났거나 다른 오류 - 이 1차 지시는 없던 것으로 하고 사람의 글을 다시 받는다 (같은 대화에 잇는다)
        self._save(first_at=None, since=_now(), error=f"1차 지시의 답이 정상으로 끝나지 않았습니다: {err}", error_at=_now())
        _out({"type": "error", "text": f"1차 지시의 답이 정상으로 끝나지 않음: {err}"})
        return False

    def _session_note(self, held):
        """지시를 넣은 뒤의 사용 세션 - 새로 열렸는지 쓰던 것인지, '세션 끝남' 창을 넘겼는지. 세션 기록에도 남긴다."""
        exp, new = note_session(self.cwd, self.chats, run=self.d.name)
        if exp is None:
            text = "freebuff 세션: 끝나는 시각을 읽지 못함"
        else:
            until = datetime.datetime.fromtimestamp(exp).strftime("%H:%M:%S")
            text = f"freebuff 세션: {'새로 열림' if new else '쓰던 세션'} ({until} 까지)"
        return text + (" · '세션 끝남' 창이 떠 있어 Enter 를 한 번 더 넣음" if held else "")

    def _pane_cpu(self):
        return base.cpu_seconds(pane_pids(self.pane))

    def _work(self):
        """답이 끝나기를 기다린다. `(rc, 보고)` - rc 0 정상 종료, `RESUME` 세션이 끝나 멈춤(이어 보낸다),
        `REFUSED` freebuff 가 줄을 거절함(보고 자리에 그 글), None 끊김.

        시간 한도는 없다. 대화 파일이 자라거나 freebuff 가 CPU 를 쓰는 동안은 기다리고, 둘 다 `QUIET_SEC` 동안 없으면
        멈춘 것으로 본다 (화면은 보지 않는다 - 쉬는 동안에도 광고가 바뀐다).
        """
        marker = self.d.name
        wall0 = time.time()
        if self.chat is not None:
            # 이어 보낸 줄이 다른 대화에 들어갔을 수 있다(사람이 그 사이 새 대화를 열었다) - 그러면 그 대화를 본다
            newest = find_chat(self.chats, self.cwd, marker)
            if newest is not None and newest != self.chat:
                self.chat, self.blocks, self.emitted, self.answers, self.progress = newest, [], 0, 0, -1
        active = cpu_at = time.monotonic()
        cpu_last, mtime = self._pane_cpu(), None
        while not self.stop:
            now = time.monotonic()
            if now - cpu_at >= CPU_CHECK_SEC:
                cpu = self._pane_cpu()
                if cpu - cpu_last >= base.CPU_ACTIVE * (now - cpu_at):
                    active = now
                cpu_at, cpu_last = now, cpu
            if self.chat is None:
                self.chat = find_chat(self.chats, self.cwd, marker, wall0)
                # 대화가 아직 안 생겼다 - 세션이 끝나 지시가 창에 걸렸는지 본다(읽기만). 푸는 것은 사람이 팬에서 한다
                held = self.chat is None and pane_status(self.pane)["held"]
                if held != bool(self.gate.get("held")):
                    self._save(held=HELD_TEXT if held else None)
                    if held:
                        _out({"type": "error", "text": HELD_TEXT})
            try:
                m = self.chat.stat().st_mtime if self.chat is not None else None
            except OSError:
                m = None
            if m != mtime:
                mtime, active = m, now
            if now - active > QUIET_SEC:
                st = pane_status(self.pane)
                _out({"type": "error", "timeout": True,
                      "text": f"{QUIET_SEC:g}초 동안 답이 자라지도, freebuff 가 CPU 를 쓰지도 않음 - 멈춘 것으로 봄. 팬: "
                              + " / ".join(st["lines"][-3:])})
                return RC_TIMEOUT, self._partial("멈춤")
            msgs = _load_chat(self.chat) if self.chat is not None else None
            if msgs:
                self.blocks, done = chat_blocks(msgs, marker)
                n, last = chat_tail(msgs, marker)
                done = done and n > self.answers and m is not None and time.time() - m >= SETTLE_SEC
                upto = len(self.blocks) if done else max(len(self.blocks) - 1, 0)    # 쓰는 중인 마지막 조각은 다 쓴 뒤에
                for b in self.blocks[self.emitted:upto]:
                    _out({"type": "text", "text": b[1]} if b[0] == "text" else {"type": "tool", "name": b[1], "summary": b[2]})
                self.emitted = max(self.emitted, upto)
                if done:
                    err = one_line(str(last.get("userError") or ""), 200)
                    if err and _REFUSED_RE.search(err):
                        # 사용 정책 거절 - 다시 보내면 같은 일을 한 번 더 하는 셈이다. 멈추고 사람에게 넘긴다
                        return REFUSED, err
                    if err and _ENDED_RE.search(err) and len(self.blocks) > self.progress:
                        # 세션이 끝나 멈췄다 - 한 일이 있으니 같은 대화에 이어 보낸다 (보내는 것은 다시 사람·옵션의 몫)
                        self.answers, self.progress = n, len(self.blocks)
                        self._note(f"freebuff 가 멈춤: {err} - 같은 대화에 이어 보내기를 기다림")
                        return RESUME, ""
                    if err or not last.get("completionTime"):
                        _out({"type": "error", "text": "freebuff 답이 정상으로 끝나지 않음: " + (err or "도중에 멈춤(완료 시간이 없음)")})
                        return 1, self._partial(err or "도중에 멈춤")
                    return 0, final_text(self.blocks)
            time.sleep(POLL_SEC)
        return None, self._partial("끊김")

    def _partial(self, why):
        """끝까지 못 간 답에서 건진 글 - 대화 파일에 쓰던 데까지."""
        text = final_text(self.blocks)
        return f"({why} - 아래는 그때까지 쓴 글)\n\n{text}" if text else ""

    def _refused(self, err):
        """freebuff 가 줄을 사용 정책으로 거절했다 - 다시 보내지 않는다. 자동 전송 옵션을 끄고 BLOCKED 로 끝낸다.

        rc 는 0 이다: 한 일이 없다는 것을 보고의 `BLOCKED` 로 말한다(그래프는 다시 시도하지 않고 사람에게 넘긴다).
        """
        was_on = auto_state(self.cwd)["on"]
        try:
            auto_set(self.cwd, False, f"freebuff 사용 정책 거절 ({self.d.name})", refused=True)
        except OSError:
            pass
        self._save(phase="refused", error=err, error_at=_now(), resume=None)
        _out({"type": "error", "text": "freebuff 가 지시를 사용 정책으로 거절함 - 다시 보내지 않음: " + err})
        prior = self._partial("거절되기 전까지")
        _out({"type": "end", "ok": False, "result":
              "BLOCKED\nfreebuff 가 이 지시를 모델에 보내지 않고 사용 정책으로 거절했다. 다시 보내지 않았다.\n"
              f"freebuff 의 글: {err}\n"
              + ("'미리 고른 문구 전송' 옵션을 껐다. " if was_on else "")
              + "사람이 팬을 보고, 문구를 바꿔 직접 보낼지 정해야 한다." + (f"\n\n{prior}" if prior else "")})
        return 0

    def run(self):
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(s, self._on_term)
        while True:
            if not self._await():
                if self.refusal:
                    return self._refused(self.refusal)
                if not self.sent:
                    if self.first:
                        _tmux("send-keys", "-t", self.pane, "Escape")      # 1차 지시의 답이 돌고 있을 수 있다 - 멈춤 키 하나
                    self._save(phase="unsent")
                    _out({"type": "end", "ok": False, "result": UNSENT_REPORT_FIRST if self.first else UNSENT_REPORT})
                    return RC_UNSENT
                rc, report = None, self._partial("이어 보내지 않음")
                break
            rc, report = self._work()
            if rc != RESUME:
                break
            # 이어 가기는 사람의 글을 다시 받지 않는다 - 1차 지시는 이미 이 대화에 있다. 승인(사람의 누름이나 켜 둔 옵션)만 기다린다
            self._save(phase="await", since=_now(), resume=True, error=None)
        if rc == REFUSED:
            return self._refused(report)
        if rc is None:
            # 끊겼다(완전 중지·사람) - 팬에서 하던 일을 멈춘다. 지시가 아니라 멈춤 키 하나다.
            _tmux("send-keys", "-t", self.pane, "Escape")
            self._save(phase="cut")
            _out({"type": "end", "ok": False, "result": report})
            return 143
        self._save(phase="done" if rc == 0 else "timeout" if rc == RC_TIMEOUT else "failed")
        if rc == RC_TIMEOUT:
            _tmux("send-keys", "-t", self.pane, "Escape")
        _out({"type": "end", "ok": rc == 0, "result": report})
        return rc


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("쓰임: freebuff.py <세션 폴더>")
    sys.exit(Driver(sys.argv[1]).run())
