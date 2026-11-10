"""AIMEM 모니터 데이터 계층 (T-036, 슬롯 S1 소유).

파일 -> 딕셔너리. **읽기 전용**이다: 어떤 파일도 쓰지 않고 디렉터리도 만들지 않는다.
파싱 실패로 예외를 던지지 않고 `state["errors"]` 에 한국어 문자열로 쌓는다.
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import statistics
from datetime import datetime, timedelta

from . import PROGRESS_WEIGHTS, REQUEST_CLOSED_STATES
from . import RUN_ID_RE as _RUN_ID_PATTERN

LOG_MAX = 400   # (더는 자르는 데 쓰지 않는다 - 하위 호환용 상수)
REPORT_HEAD = 200
_OPENCODE_PROGRESS = re.compile(r"^\s*>\s*\w+\s*·")


# --------------------------------------------------------------- 공통 도구

def _read(path: pathlib.Path, errors: list, what: str | None = None) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        errors.append(f"{what or path.name} 을(를) 읽지 못했습니다: {str(e)[:80]}")
        return ""


def _section(lines: list[str], head_re: str) -> list[str]:
    """`## <head_re>` 로 시작하는 절의 본문 줄들 (다음 `## ` 직전까지)."""
    out, inside = [], False
    pat = re.compile(r"^##\s+" + head_re)
    for ln in lines:
        if inside:
            if ln.startswith("## "):
                break
            out.append(ln)
        elif pat.match(ln):
            inside = True
    return out


def _table_rows(body: list[str], ncols: int, errors: list, label: str) -> list[list[str]]:
    """마크다운 표의 데이터 행. 헤더·구분선은 건너뛴다. 칸이 넘치면 마지막 칸에 합친다."""
    rows, header_seen = [], False
    for ln in body:
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and any(cells):
            header_seen = True
            continue
        if not header_seen:  # 구분선 앞 = 헤더 행
            continue
        if len(cells) < ncols:
            errors.append(f"{label}: 칸이 {len(cells)}개인 행을 건너뜀 ({s[:40]})")
            continue
        if len(cells) > ncols:
            cells = cells[: ncols - 1] + ["|".join(cells[ncols - 1:])]
        rows.append(cells)
    return rows


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------- AIMEM.md

def _parse_aimem(lines: list[str], errors: list, need_rev: bool = True) -> dict:
    text = "\n".join(lines)
    m = re.search(r"- \*\*REV: (\d+)\*\*", text)
    rev = int(m.group(1)) if m else None
    if m is None and lines and need_rev:
        errors.append("AIMEM.md 에서 REV 행을 찾지 못했습니다")
    m = re.search(r"^- (?:최종 갱신|Last updated):\s*(.+?)\s*$", text, re.M)
    updated = m.group(1) if m else ""

    goal_text, goal_status = "", ""
    body = _section(lines, r"1\.")
    i = 0
    while i < len(body):
        ln = body[i]
        gm = re.match(r"^- \*\*(?:목표|Goal)[^:]*:\*\*\s*(.*)$", ln)
        if gm and not goal_text:
            parts = [gm.group(1).strip()]
            i += 1
            while i < len(body) and body[i].startswith(" ") and body[i].strip():
                parts.append(body[i].strip())
                i += 1
            goal_text = " ".join(p for p in parts if p)
            continue
        sm = re.match(r"^- \*\*(?:상태|Status):\*\*\s*(.*)$", ln)
        if sm and not goal_status:
            goal_status = sm.group(1).strip()
        i += 1
    return {"rev": rev, "lines": len(lines), "updated": updated,
            "goal": {"text": goal_text, "status": goal_status}}


def _parse_log(lines: list[str], root: pathlib.Path | None = None) -> list[dict]:
    """핸드오프 로그. `.aimem/handoff.md` 가 있으면 그 파일(REV 129, 정본), 없으면 AIMEM.md 4절(옛 자리)을 읽는다."""
    hf = (root / ".aimem" / "handoff.md") if root else None
    if hf is not None and hf.is_file():
        try:
            body = hf.read_text(encoding="utf-8").splitlines()
        except OSError:
            body = _section(lines, r"4\.\s")
    else:
        body = _section(lines, r"4\.\s")
    entries, cur = [], None
    for ln in body:
        m = re.match(r"^- `([^`]+)`\s*(.*)$", ln)
        if m:
            cur = {"when": m.group(1), "text": m.group(2).strip()}
            entries.append(cur)
        elif cur is not None and ln.startswith(" ") and ln.strip():
            cur["text"] += " " + ln.strip()
        else:
            cur = None
    return entries   # 자르지 않는다 - 목록은 CSS 가 말줄임하고 상세는 전문을 보인다 (2026-11-10)


# --------------------------------------------------------------- 하네스 모델

def harness_model(harness: str) -> tuple[str, str]:
    """`tools/fleet.py` `harness_model()` 과 같은 자리를 읽는다."""
    home = pathlib.Path.home()
    try:
        if harness == "claude":
            # 슬롯별 모델의 정본은 `tools/fleet_slots.json` 이고 `slot_model()` 이 먼저 읽는다.
            # 여기 값은 **그 파일에 슬롯 항목이 없을 때의 마지막 기본값**일 뿐이다.
            # openclaw.json entries.claude 는 관리자 ACP 세션용(opus)이라 작업자 모델로 읽지 않는다.
            return ("anthropic/claude-sonnet-5-5",
                    "fleet.py spawn 기본 --model sonnet (관리자는 openclaw.json entries.claude = opus)")
        if harness == "codex":
            import tomllib
            cfg = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))
            m, p = cfg.get("model"), cfg.get("model_provider")
            return (f"{p}/{m}" if p and m else m or "(하네스 기본)", "~/.codex/config.toml")
        if harness == "opencode":
            text = (home / ".config" / "opencode" / "opencode.jsonc").read_text(encoding="utf-8")
            mm = re.search(r'^\s*"model"\s*:\s*"([^"]+)"', text, re.M)
            return (mm.group(1) if mm else "(하네스 기본)", "~/.config/opencode/opencode.jsonc")
    except Exception as e:  # 읽기 실패는 절대 터뜨리지 않는다 (OSError/ValueError/TOMLDecodeError ...)
        return ("(읽기 실패)", str(e)[:60])
    return ("(알 수 없는 하네스)", "-")


SLOT_MODEL_SOURCE = "tools/fleet_slots.json (슬롯별 기본 모델)"


def _load_slot_models(root: pathlib.Path, errors: list) -> dict:
    """`tools/fleet_slots.json` -> {슬롯: 모델}. `fleet.py` `SLOT_DEFAULT_MODEL` 과 같은 파일이다.

    없으면 빈 딕셔너리(슬롯마다 `harness_model()` 로 떨어진다). 깨졌으면 `errors` 에 한 줄 남긴다.
    """
    p = root / "tools" / "fleet_slots.json"
    try:
        if not p.is_file():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        errors.append(f"tools/fleet_slots.json 을(를) 읽지 못했습니다: {str(e)[:60]}")
        return {}
    if not isinstance(data, dict):
        errors.append("tools/fleet_slots.json 이(가) 객체가 아닙니다")
        return {}
    out = {}
    for slot, v in data.items():
        m = v.get("model") if isinstance(v, dict) else None
        if isinstance(m, str) and m.strip():
            out[slot] = m.strip()
    return out


# --------------------------------------------------------------- runs

def _report_body(harness: str, out_path: pathlib.Path) -> str:
    try:
        raw = out_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not raw.strip():
        return ""
    if harness == "claude":
        try:
            data = json.loads(raw)
            res = data.get("result") if isinstance(data, dict) else None
            return res if isinstance(res, str) else raw
        except ValueError:
            return raw
    if harness == "opencode":
        return "\n".join(l for l in raw.splitlines() if not _OPENCODE_PROGRESS.match(l))
    return raw


def _lost_end(rdir: pathlib.Path, run_id: str, errors: list) -> datetime | None:
    """lost 실행의 끝 시각 - `tools/fleet.py` `_run_last_mtime()` 을 **그대로** 쓴다.

    규칙(`.lost` 마커의 `ended` -> 없거나 깨졌으면 기록 파일들의 마지막 mtime)을 여기서
    다시 짜면 CLI 표와 웹 화면이 다른 숫자를 말하게 된다. 그 함수는 모듈 전역 `RUNS` 를
    읽으므로, 전역을 바꿔치지 않고(서버는 스레드로 돈다) `RUNS` 만 `rdir` 로 바꾼 함수
    사본을 만들어 부른다. 읽기 전용이다 - 마커를 쓰는 것은 `fleet.py reap` 이다.
    """
    try:
        import types
        import fleet  # noqa: PLC0415 - tools/ 가 sys.path 에 있어야 한다 (server/테스트와 같다)
        fn = fleet._run_last_mtime
        bound = types.FunctionType(fn.__code__, {**fn.__globals__, "RUNS": rdir}, fn.__name__)
        end = bound(run_id)
    except Exception as e:  # noqa: BLE001 - 화면은 떠야 한다
        errors.append(f"lost 실행 {run_id} 의 끝 시각을 구하지 못했습니다(경과가 계속 늘어납니다): {str(e)[:60]}")
        return None
    if end is not None and end.tzinfo is not None:
        end = end.astimezone().replace(tzinfo=None)  # started 는 naive 로컬 시각이다
    return end


def _collect_runs(root: pathlib.Path, now: datetime, errors: list) -> list[dict]:
    rdir = root / ".aimem" / "runs"
    runs = []
    try:
        metas = sorted(rdir.glob("*.json")) if rdir.is_dir() else []
    except OSError as e:
        errors.append(f".aimem/runs 를 읽지 못했습니다: {str(e)[:80]}")
        return []
    for mp in metas:
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                raise ValueError("객체가 아님")
        except (OSError, ValueError) as e:
            errors.append(f"실행 기록 {mp.name} 을(를) 읽지 못했습니다: {str(e)[:60]}")
            continue
        rid = meta.get("id") or mp.stem
        harness = meta.get("harness") or ""
        rc_path = mp.with_suffix(".rc")
        state, rc, end = "unknown", None, None
        if rc_path.exists():
            try:
                rc = int(rc_path.read_text(encoding="utf-8").strip())
                state = "done"
                end = datetime.fromtimestamp(rc_path.stat().st_mtime)
            except (OSError, ValueError):
                state, rc = "unknown", None
        else:
            pid = meta.get("pid")
            if isinstance(pid, int):
                try:
                    os.kill(pid, 0)
                    state = "running"
                except PermissionError:
                    state = "running"  # 프로세스는 존재한다
                except OSError:
                    state = "lost"
                    end = _lost_end(rdir, rid, errors)  # lost 는 마지막 흔적에서 멈춘다
        started = meta.get("started")
        st = _parse_iso(started)
        elapsed = None
        if st is not None:
            elapsed = int(round(((end or now) - st).total_seconds()))
            if elapsed < 0:
                elapsed = 0
        head = _report_body(harness, mp.with_suffix(".out")).strip()[:REPORT_HEAD]
        runs.append({
            "id": rid, "slot": meta.get("slot"), "harness": harness,
            "model": meta.get("model"), "label": meta.get("label"),
            "rev": meta.get("rev"), "write": meta.get("write") or [],
            "started": started, "state": state, "rc": rc,
            "elapsed_sec": elapsed, "report_head": head,
        })
    runs.sort(key=lambda r: str(r["id"]))
    return runs


SMOKE_LABEL = re.compile(r"스모크|smoke", re.IGNORECASE)


def _is_smoke(run: dict) -> bool:
    return bool(SMOKE_LABEL.search(str(run.get("label") or "")))


def median_durations(runs: list[dict]) -> dict:
    """성공(done, rc==0)하고 경과가 있는 실행만 표본으로 쓴다.

    라벨에 `스모크`/`smoke` 가 든 실행은 뺀다 (T-055, 4.5 큐 5번). 15~83초짜리 하네스
    점검이 섞이면 실작업(수백 초) 중앙값이 끌려 내려가 ETA 가 낙관적이 된다.
    '쓰기 경로가 있는 실행만' 으로 거르지 않은 이유: 읽기 전용 검수(S4 적대적 검수
    189~224s)도 실작업이라, 그걸 빼면 claude 중앙값이 오히려 내려간다.
    """
    by: dict[str, list] = {}
    for r in runs:
        if _is_smoke(r):
            continue
        if r.get("state") == "done" and r.get("rc") == 0 and r.get("elapsed_sec") is not None:
            by.setdefault(r.get("harness") or "?", []).append((r["id"], r["elapsed_sec"]))
    if not by:
        return {"by_harness": {}, "overall": {"median_sec": None, "samples": 0}}
    allv = [v for lst in by.values() for _, v in lst]
    return {
        "by_harness": {
            h: {"median_sec": int(statistics.median(v for _, v in lst)),
                "samples": len(lst), "source": [i for i, _ in lst]}
            for h, lst in sorted(by.items())
        },
        "overall": {"median_sec": int(statistics.median(allv)), "samples": len(allv)},
    }


# --------------------------------------------------------------- requests

def _estimate(req: dict, runs_by_id: dict, slot_harness: dict, eta: dict, now: datetime) -> dict:
    subs = [s for s in (req.get("subtasks") or []) if isinstance(s, dict)]
    if subs:
        w = [PROGRESS_WEIGHTS.get(s.get("status"), 0.0) for s in subs]
        pct = round(sum(w) / len(subs) * 100, 1)
    else:
        pct = 0.0

    # 닫힌 요청(DONE/REJECTED)은 **요청 상태가 정본**입니다 - 서브태스크가 REVIEW 로 남아 있어도
    # 85% 와 "ETA 525초 남음" 을 내지 않습니다(2026-11-10 점검: 요청 10건 전부 DONE 인데 진행율
    # 0~90%·ETA 잔여가 떠서 화면이 "끝났다"와 "남았다"를 동시에 말했습니다).
    status = str(req.get("status") or "").upper()
    if status in REQUEST_CLOSED_STATES:
        return {"progress_pct": 100.0 if status == "DONE" else pct, "eta_sec": None, "eta_at": None,
                "eta_basis": f"요청 {status} - 종료된 요청은 ETA 를 내지 않습니다", "eta_over": []}

    by_h, overall = eta["by_harness"], eta["overall"]["median_sec"]
    remaining = [s for s in subs if s.get("status") != "DONE"]
    ests, used = [], []
    over: list[dict] = []
    floor: dict = {}  # 하네스 -> 초과 중인 실행의 elapsed_sec 최댓값 (미착수 추정의 바닥값)
    pending = []      # (med, h, info) - 아직 시작하지 않은 서브태스크
    for s in remaining:
        h = s.get("harness") or slot_harness.get(s.get("slot"))
        info = by_h.get(h)
        med = info["median_sec"] if info else overall
        if med is None:
            continue
        run = runs_by_id.get(s.get("run_id")) if s.get("run_id") else None
        if run and run.get("state") == "running" and run.get("elapsed_sec") is not None:
            el = run["elapsed_sec"]
            if el > med:
                # 같은 run 을 가리키는 서브태스크가 여럿이어도 초과 항목은 한 번만 (4.5 큐 4번)
                if all(o["run_id"] != s.get("run_id") for o in over):
                    over.append({"slot": s.get("slot"), "run_id": s.get("run_id"),
                                 "over_sec": el - med, "median_sec": med})
                floor[h] = max(floor.get(h, 0), el)
                med = max(1, int(med * 0.5))
            else:
                med = med - el
            ests.append(med)
            used.append(h if info else "전체")
        else:
            pending.append((med, h, info))
    for med, h, info in pending:
        ests.append(max(med, floor.get(h, 0)))
        used.append(h if info else "전체")

    if not remaining:
        eta_sec = 0
        basis = "남은 서브태스크 없음" if subs else "서브태스크 없음 - 분담 후 추정됩니다"
    elif not ests:
        eta_sec = None
        basis = "표본 없음 - .aimem/runs 에 성공 실행 기록이 쌓이면 추정됩니다"
    else:
        eta_sec = max(ests)
        parts = []
        for h in dict.fromkeys(used):
            if h == "전체":
                parts.append(f"전체 중앙값 {overall}s(표본 {eta['overall']['samples']})")
            else:
                parts.append(f"{h} 중앙값 {by_h[h]['median_sec']}s(표본 {by_h[h]['samples']})")
        basis = " · ".join(parts) + " 중 최댓값, 병렬 가정"
        if len(ests) < len(remaining):
            basis += f" (추정 불가 {len(remaining) - len(ests)}건 제외)"
        if over:
            basis += " · 초과 중: " + ", ".join(
                f"{o['slot']}(run {o['run_id']}) 중앙값 {o['median_sec']}s 를 {o['over_sec']}초 초과"
                for o in over)
    eta_at = (now + timedelta(seconds=eta_sec)).isoformat(timespec="seconds") if eta_sec is not None else None
    return {"progress_pct": pct, "eta_sec": eta_sec, "eta_at": eta_at, "eta_basis": basis,
            "eta_over": over}


def _collect_requests(root, runs, slots, eta, now, errors) -> list[dict]:
    qdir = root / ".aimem" / "requests"
    if not qdir.is_dir():
        return []
    runs_by_id = {r["id"]: r for r in runs}
    slot_harness = {s["slot"]: s["harness"] for s in slots}
    out = []
    try:
        files = sorted(qdir.glob("*.json"))
    except OSError as e:
        errors.append(f".aimem/requests 를 읽지 못했습니다: {str(e)[:80]}")
        return []
    for p in files:
        try:
            req = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(req, dict):
                raise ValueError("객체가 아님")
        except (OSError, ValueError) as e:
            errors.append(f"요청 파일 {p.name} 을(를) 읽지 못했습니다: {str(e)[:60]}")
            continue
        req.update(_estimate(req, runs_by_id, slot_harness, eta, now))
        out.append(req)
    return out


# --------------------------------------------------------------- 운영 상태 DB (T-069)

_DB_LOG_HEAD = re.compile(r"^-\s*`([^`]+)`\s*")
# (2026-11-10) aimem_db.state_dict() 가 events.body 를 더는 자르지 않는다 - 로그 상세가 전문을 보여야 해서


def _s(v) -> str:
    return "" if v is None else str(v)


def _load_db_state(root: pathlib.Path, errors: list) -> dict | None:
    """`aimem_db.state_dict()` 한 번. 못 쓰면 None (+ errors 한 줄) -> 호출부가 마크다운 표로 내려간다.

    DB 파일이 없으면 부르지 않는다 - `aimem_db.connect()` 는 없는 DB 를 만들어 버리는데
    이 모듈은 읽기 전용이다. `aimem_db.DB` 는 모듈 전역(저장소 고정)이라 `root` 가 다른
    저장소(테스트 픽스처 등)면 그 DB 를 읽을 수 없으므로 역시 폴백한다.
    """
    db_path = root / ".aimem" / "aimem.db"
    if not db_path.is_file():
        errors.append("운영 상태 DB(.aimem/aimem.db)가 없어 AIMEM.md 표로 읽었습니다")
        return None
    try:
        import sys
        tools = str(pathlib.Path(__file__).resolve().parent.parent)
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import aimem_db
        if pathlib.Path(aimem_db.DB).resolve() != db_path.resolve():
            errors.append("운영 상태 DB 가 이 저장소의 것이 아니어서 AIMEM.md 표로 읽었습니다")
            return None
        state = aimem_db.state_dict()
        if not isinstance(state, dict):
            raise TypeError(f"state_dict() 가 dict 가 아님: {type(state).__name__}")
        return state
    except Exception as e:  # 서버가 죽으면 안 된다
        errors.append(f"운영 상태 DB 를 읽지 못해 AIMEM.md 표로 읽었습니다: {type(e).__name__}: {str(e)[:80]}")
        return None


def _db_when(at: str) -> str:
    """ISO `2026-11-09T19:42:03` -> 로그 표기 `2026-11-09 19:42`. 모양이 다르면 그대로."""
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?", at.strip())
    return f"{m.group(1)} {m.group(2)}" if m else at


def _db_log(events: list) -> list[dict]:
    """events 중 kind=='handoff' 만, 받은 순서(seq 내림차순 = 최신 먼저) 그대로 `_parse_log()` 모양으로."""
    out = []
    for ev in events:
        if not isinstance(ev, dict) or ev.get("kind") != "handoff":
            continue
        body = _s(ev.get("body"))
        m = _DB_LOG_HEAD.match(body)
        if m:  # 마크다운 원문 `- \`<시각>\` 관리자(R4): ...`
            when, text = m.group(1), body[m.end():]
        else:  # 원문 머리가 없는 이벤트 - 시각은 at, 화자는 actor 로 보충
            when = _db_when(_s(ev.get("at")))
            actor = _s(ev.get("actor"))
            text = f"{actor}: {body}" if actor else body
        text = " ".join(text.split())
        out.append({"when": when, "text": text})
    return out


# --------------------------------------------------------------- 진입점

def collect(root: pathlib.Path | None = None) -> dict:
    root = pathlib.Path(root) if root else pathlib.Path(__file__).resolve().parent.parent.parent
    now = datetime.now()
    errors: list[str] = []

    lines: list[str] = []
    ap = root / "AIMEM.md"
    if ap.is_file():
        lines = _read(ap, errors, "AIMEM.md").splitlines()
    else:
        errors.append("AIMEM.md 가 없습니다")

    # 운영 상태(명부·보드·큐·로그)의 정본은 `.aimem/aimem.db` 다 (T-069). 마크다운 표는 폴백.
    db = _load_db_state(root, errors)

    if lines:
        aimem = _parse_aimem(lines, errors, need_rev=not (db and db.get("rev") is not None))
    else:
        aimem = {"rev": None, "lines": 0, "updated": "", "goal": {"text": "", "status": ""}}
    if db and db.get("rev") is not None:
        aimem["rev"] = db["rev"]

    slot_models = _load_slot_models(root, errors)
    if db is not None:
        slot_rows = [[_s(r.get("slot")), _s(r.get("token")), _s(r.get("harness")),
                      _s(r.get("role")), "", _s(r.get("note")), _s(r.get("model"))] for r in db.get("slots") or []]
    else:
        slot_rows = [c + [""] for c in _table_rows(_section(lines, r"2\."), 6, errors, "2절 명부")]
    slots = []
    for c in slot_rows:
        harness = c[2]
        if len(c) > 6 and c[6]:   # DB `slots.model` 이 정본 (웹/CLI `slot set`, 2026-11-10)
            model, src = c[6], "aimem.db slots.model (슬롯 지정 모델)"
        elif c[0] in slot_models:  # 슬롯별 거울 파일이 하네스 하나당 모델 하나보다 우선 (claude 에 S1 opus / S4 sonnet)
            model, src = slot_models[c[0]], SLOT_MODEL_SOURCE
        else:
            model, src = harness_model(harness)
        slots.append({"slot": c[0], "token": c[1].strip("`"), "harness": harness,
                      "role": c[3], "note": c[5], "model": model, "model_source": src})

    if db is not None:
        board = [{"id": _s(r.get("id")), "task": _s(r.get("title")), "slot": _s(r.get("slot")) or "-",
                  "status": _s(r.get("status")), "handoff": _s(r.get("inherited")) or "-",
                  "artifact": _s(r.get("artifacts"))} for r in db.get("tasks") or []]
        queue = [{"order": _s(r.get("pos")), "task": _s(r.get("task")), "slots": _s(r.get("slot_hint")),
                  "handoff": _s(r.get("inherited")), "note": _s(r.get("note"))} for r in db.get("queue") or []]
        # 계약은 `when` 기준 최신 먼저다. events.seq 는 삽입 순서라 migrate/과거 시각 event 로 어긋난다 (T-077).
        # 정렬 키에서만 ISO 의 'T' 를 공백으로 (0x54 > 0x20 이라 같은 날 ISO 가 늘 위로 감). 안정 정렬 -> 동시각은 seq 순 유지.
        # REV 132~: handoff.md 와 같은 순서 - **REV 가 먼저**, 같은 REV(또는 REV 없음) 안에서는 `when`. 옛 항목의 시각은 손으로
        # 적은 값이라 실제 순서와 어긋난 것이 있다(REV 126 이 131 보다 늦은 시각). REV 가 없는 이벤트끼리는 예전처럼 `when` 순이다.
        def _rev_of(ev):
            try:
                return int(ev.get("rev"))
            except (TypeError, ValueError, AttributeError):
                return -1
        pairs = [(_rev_of(ev), e) for ev in (db.get("events") or []) for e in _db_log([ev])]
        log = [e for _, e in sorted(pairs, key=lambda p: (p[0], p[1]["when"].replace("T", " ")), reverse=True)]
    else:
        board = [{"id": c[0], "task": c[1], "slot": c[2], "status": c[3], "handoff": c[4], "artifact": c[5]}
                 for c in _table_rows(_section(lines, r"3\."), 6, errors, "3절 작업 보드")]
        queue = [{"order": c[0], "task": c[1], "slots": c[2], "handoff": c[3], "note": c[4]}
                 for c in _table_rows(_section(lines, r"4\.5"), 5, errors, "4.5 대기 큐")]
        log = _parse_log(lines, root)

    runs = _collect_runs(root, now, errors)
    eta = median_durations(runs)
    requests = _collect_requests(root, runs, slots, eta, now, errors)

    return {
        "generated": now.isoformat(timespec="seconds"),
        "root": str(root),
        "aimem": aimem, "slots": slots, "board": board, "queue": queue, "log": log,
        "runs": runs, "eta": eta, "requests": requests, "errors": errors,
    }


# --------------------------------------------------------------- 실행 상세 (T-050, 요청 8d8d)
#
# 실행 기록은 `tools/fleet.py` `cmd_spawn` 이 남긴다. **디렉터리가 아니라 평면 파일**이다:
#   .aimem/runs/<id>.json      메타 (id/slot/harness/model/label/rev/write/pid/started/brief)
#   .aimem/runs/<id>.brief.md  작업자에게 준 지시 본문 (머리말 + task)
#   .aimem/runs/<id>.out       stdout (claude 는 --output-format json 포장)
#   .aimem/runs/<id>.err       stderr
#   .aimem/runs/<id>.rc        종료 코드 (있으면 끝난 것, mtime = 종료 시각)
# 이 함수는 읽기만 한다.

# run id 규칙의 정본은 패키지 `__init__.RUN_ID_RE`(문자열) 하나다 - 옛 꼴 `20261109-172618-S3` 과
# 새 꼴 `T-053-S3-a3-181328` / `ADHOC-S3-a1-181328` 를 둘 다 받는다. 여기서는 다시 적지 않고
# 가져다 컴파일만 한다. `re.ASCII` 는 전각 숫자 등 유니코드 `[0-9]` 외 문자를 막기 위한 것이고,
# 아래에서 `fullmatch` 로 거르므로 끝의 `\n` 도 통과하지 못한다.
RUN_ID_RE = re.compile(_RUN_ID_PATTERN, re.ASCII)
STDERR_TAIL = 2000   # (더는 자르는 데 쓰지 않는다 - 하위 호환용 상수)
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
DETAIL_KEYS = ("id", "found", "slot", "harness", "model", "label", "status", "rc", "elapsed_s",
               "started", "ended", "brief", "report", "stderr_tail", "paths", "errors")


def _empty_detail(run_id) -> dict:
    return {
        "id": run_id if isinstance(run_id, str) else ("" if run_id is None else str(run_id)[:100]),
        "found": False, "slot": "", "harness": "", "model": "", "label": "", "status": "",
        "rc": None, "elapsed_s": None, "started": None, "ended": None,
        "brief": "", "report": "", "stderr_tail": "",
        "paths": {"dir": "", "out": "", "err": "", "rc": "", "brief": ""},
        "errors": [],
    }


def _str(v) -> str:
    return v if isinstance(v, str) else ""


# 비밀 가림 (T-064, S4 검수 1번). 웹 UI 가 외부에 공개되므로 작업자 기록 원문에 찍힌 비밀을 가린다.
# **값만** `***` 로 바꾸고 이름(Bearer / 변수명 / 확인토큰)은 남긴다 - 무엇이 가려졌는지 보여야 한다.
# 40자 hex 는 git SHA 라 건드리지 않는다(64자만). 패턴을 하나로 묶어 필드당 한 번만 훑는다.
_SECRET_RE = re.compile(
    r"(?P<hex>\b[0-9a-f]{64}\b)"
    r"|(?P<bearer_n>Bearer\s+)[A-Za-z0-9._\-]{8,}"
    r"|(?P<gh>gh[pousr]_[A-Za-z0-9]{20,})"
    r"|(?P<sk>sk-[A-Za-z0-9_\-]{12,})"
    r"|(?P<env_n>(?:KISTI_API_KEY|GITHUB_CLIENT_SECRET|ANTHROPIC_API_KEY|OPENAI_API_KEY)\s*[=:]\s*)\S+"
    r"|(?P<tok_n>확인토큰:\s*)[0-9a-f]{6}",
    re.IGNORECASE,
)


def _redact_sub(m: re.Match) -> str:
    keep = m.group("bearer_n") or m.group("env_n") or m.group("tok_n") or ""
    return keep + "***"


def _redact(text: str) -> str:
    return _SECRET_RE.sub(_redact_sub, text) if text else text


def _safe_run_file(p: pathlib.Path, rdir: pathlib.Path, errors: list) -> bool:
    """심볼릭 링크이거나 실제 위치가 `.aimem/runs` 밖이면 False (S4 검수 7번). 읽기 전에 부른다."""
    try:
        if p.is_symlink():
            ok = False
        else:
            ok = p.resolve().parent == rdir.resolve()
    except (OSError, RuntimeError):
        ok = False
    if not ok:
        errors.append(f"{p.name} 은 심볼릭 링크라 읽지 않았습니다")
    return ok


def run_detail(run_id: str, root: pathlib.Path | None = None) -> dict:
    """실행 하나의 상세. 반환 키는 `DETAIL_KEYS` 16개로 고정이고 **어떤 입력에도 예외를 던지지 않는다.**

    `run_id` 가 `RUN_ID_RE` 에 정확히 맞지 않으면 파일을 하나도 건드리지 않고 돌아온다(경로 탈출 방어).
    """
    d = _empty_detail(run_id)
    if not isinstance(run_id, str) or len(run_id) > 64 or not RUN_ID_RE.fullmatch(run_id):
        d["errors"].append("잘못된 run id")
        return d
    try:
        _fill_detail(d, run_id, root)
    except Exception as e:  # 마지막 방어선 - 화면이 깨지지 않게 키는 그대로 둔다
        d["found"] = False
        d["errors"].append(f"상세를 읽다 실패했습니다: {type(e).__name__}: {str(e)[:80]}")
    return d


def _fill_detail(d: dict, run_id: str, root) -> None:
    root = pathlib.Path(root) if root else pathlib.Path(__file__).resolve().parent.parent.parent
    rdir = root / ".aimem" / "runs"
    errors = d["errors"]
    if not rdir.is_dir():
        errors.append(".aimem/runs 디렉터리가 없습니다")
        return
    d["paths"]["dir"] = str(rdir)
    meta_p = rdir / f"{run_id}.json"
    files = {"out": rdir / f"{run_id}.out", "err": rdir / f"{run_id}.err",
             "rc": rdir / f"{run_id}.rc", "brief": rdir / f"{run_id}.brief.md"}
    for k, p in files.items():
        try:
            d["paths"][k] = str(p) if p.is_file() else ""
        except OSError:
            d["paths"][k] = ""

    # 메타
    meta = None
    try:
        if meta_p.is_file():
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                meta = None
                errors.append(f"실행 기록 {meta_p.name} 이(가) 객체가 아닙니다")
        else:
            errors.append(f"실행 기록이 없습니다: {run_id}")
    except (OSError, ValueError) as e:
        meta = None
        errors.append(f"실행 기록 {meta_p.name} 을(를) 읽지 못했습니다: {str(e)[:60]}")
    meta = meta or {}
    d["found"] = bool(meta)

    harness = _str(meta.get("harness"))
    d["slot"] = _str(meta.get("slot"))
    d["harness"] = harness
    d["label"] = _str(meta.get("label"))
    # 실행 기록의 model 이 실제로 넘긴 값이다(claude 는 슬롯별 --model). 비어 있으면 하네스 설정에서 구한다.
    if _str(meta.get("model")):
        d["model"] = meta["model"]
    elif harness in ("claude", "codex", "opencode"):
        d["model"] = harness_model(harness)[0]

    # 상태 / rc / 시각 - `_collect_runs` 와 같은 규칙
    status, rc, end = ("unknown" if d["found"] else ""), None, None
    if files["rc"].is_file():
        try:
            rc = int(files["rc"].read_text(encoding="utf-8").strip())
            status = "done"
            end = datetime.fromtimestamp(files["rc"].stat().st_mtime)
        except (OSError, ValueError) as e:
            errors.append(f"{files['rc'].name} 을(를) 읽지 못했습니다: {str(e)[:60]}")
            status, rc = ("unknown" if d["found"] else ""), None
    elif d["found"]:
        pid = meta.get("pid")
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
            try:
                os.kill(pid, 0)
                status = "running"
            except PermissionError:
                status = "running"
            except OSError:
                status = "lost"
    d["status"], d["rc"] = status, rc
    started = meta.get("started")
    d["started"] = started if isinstance(started, str) else None
    d["ended"] = end.isoformat(timespec="seconds") if end else None
    st = _parse_iso(started) if isinstance(started, str) else None
    if st is not None:
        try:
            d["elapsed_s"] = max(0, int(round(((end or datetime.now()) - st).total_seconds())))
        except (TypeError, OverflowError):
            d["elapsed_s"] = None

    # 본문 - 메타가 깨져도 파일이 있으면 보여 준다. 심볼릭 링크는 읽지 않고, 내보내기 직전에 비밀을 가린다.
    if d["paths"]["brief"] and _safe_run_file(files["brief"], rdir, errors):
        d["brief"] = _redact(_read(files["brief"], errors))
    if d["paths"]["out"] and _safe_run_file(files["out"], rdir, errors):
        d["report"] = _redact(_report_body(harness, files["out"]).strip())
    if d["paths"]["err"] and _safe_run_file(files["err"], rdir, errors):
        err = _read(files["err"], errors)
        # 자르기 전에 가린다 - 잘린 경계에 걸친 비밀이 짧은 조각으로 남아 패턴을 피하지 않게
        d["stderr_tail"] = _redact(_ANSI.sub("", err).strip())   # 키 이름은 계약대로 두되 전문 (2026-11-10, 상세는 잘리지 않는다)
