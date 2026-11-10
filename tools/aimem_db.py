#!/usr/bin/env python3
"""AIMEM 운영 상태 저장소 - SQLite (표준 라이브러리만). 태석님 결정 2026-11-09 18:25.

AIMEM.md 는 **규약 본문**만 남기고, 운영 상태(명부·보드·큐·소유권·로그·요청·그래프·실행)는 `.aimem/aimem.db` 가 정본이다.
마크다운의 2·3·4·4.5·6절은 `render` 가 DB 에서 뽑는 **읽기 전용 스냅샷**(`AIMEM-state.md`)이다.

  python3 tools/aimem_db.py init                  # 스키마 생성 (멱등)
  python3 tools/aimem_db.py migrate               # AIMEM.md 표 + .aimem/{runs,graph,requests} JSON 을 적재 (멱등 upsert)
  python3 tools/aimem_db.py render                # AIMEM-state.md 스냅샷 생성
  python3 tools/aimem_db.py check --slot S2 --token d27e93 --rev 112   # 작업자 0.1 세 줄 검사
  python3 tools/aimem_db.py state                 # 웹 UI 용 JSON 한 덩어리
  python3 tools/aimem_db.py event --kind note --body "..."           # 이벤트 추가 (REV 가 하나 오른다)
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / ".aimem" / "aimem.db"
AIMEM = ROOT / "AIMEM.md"
STATE_MD = ROOT / "AIMEM-state.md"

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS slots(slot TEXT PRIMARY KEY, token TEXT NOT NULL, harness TEXT NOT NULL,
  model TEXT, role TEXT, note TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS ownership(path_pattern TEXT PRIMARY KEY, owner TEXT NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, title TEXT, detail TEXT, requester TEXT,
  status TEXT NOT NULL DEFAULT 'NEW', created TEXT, updated TEXT, raw JSON);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, request_id TEXT REFERENCES requests(id), title TEXT,
  slot TEXT, status TEXT NOT NULL, inherited TEXT, artifacts TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS queue(pos INTEGER PRIMARY KEY, task TEXT, slot_hint TEXT, inherited TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS graphs(id TEXT PRIMARY KEY, request TEXT, concurrency INTEGER, created TEXT, updated TEXT, raw JSON);
CREATE TABLE IF NOT EXISTS nodes(graph_id TEXT REFERENCES graphs(id), node_id TEXT, task_id TEXT, title TEXT, slot TEXT,
  deps JSON, verify TEXT, max_attempts INTEGER, status TEXT, attempts INTEGER DEFAULT 0, PRIMARY KEY(graph_id, node_id));
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, task_id TEXT, slot TEXT, harness TEXT, model TEXT, attempt INTEGER,
  label TEXT, write_paths JSON, pid INTEGER, started TEXT, ended TEXT, rc INTEGER, state TEXT, report_status TEXT,
  brief_path TEXT, rev INTEGER);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT, rev INTEGER,
  kind TEXT NOT NULL, body TEXT);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_state ON runs(state);
CREATE INDEX IF NOT EXISTS idx_tasks_request ON tasks(request_id);
"""


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def cmd_init(a=None):
    with connect() as con:
        con.executescript(SCHEMA)
    print(f"ok: {DB}")
    return 0


# ----------------------------------------------------------------- 적재 (마크다운 표 → DB)
def _table_rows(text, heading_re):
    """`## N. 제목` 절 안의 첫 표를 행 리스트(셀 리스트)로. 헤더/구분선 제외."""
    m = re.search(heading_re, text, re.M)
    if not m:
        return []
    body = text[m.end():]
    nxt = re.search(r"^## ", body, re.M)
    body = body[:nxt.start()] if nxt else body
    rows = []
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"-{2,}", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def _strip_code(s):
    return s.strip().strip("`").strip()


def migrate(verbose=True):
    cmd_init()
    text = AIMEM.read_text(encoding="utf-8") if AIMEM.exists() else ""
    now = _now()
    with connect() as con:
        # **REV 는 DB 가 정본이다 (2단계, REV 114~).** 마크다운 서문에서는 DB 에 아직
        # REV 가 없을 때만 **씨앗으로** 읽는다. 예전처럼 매번 덮어쓰면 `event --bump`
        # 로 올린 REV 가 `migrate` 한 번에 되돌아간다 - 실제로 114 가 113 으로
        # 내려갔다(REV 114 실측). 서문을 DB 에 맞추는 쪽은 `render` 가 한다.
        rev_m = re.search(r"- \*\*REV: (\d+)\*\*", text)
        if rev_m and rev(con) is None:
            con.execute("INSERT INTO meta(key,value) VALUES('rev',?)", (rev_m.group(1),))
        con.execute("INSERT INTO meta(key,value) VALUES('migrated_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now,))
        # 2절 명부: 슬롯|토큰|하네스|역할|세션키|비고
        slots_json = {}
        try:
            slots_json = json.loads((ROOT / "tools" / "fleet_slots.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        n_slots = 0
        for cells in _table_rows(text, r"^## 2\. 세션 명부"):
            if len(cells) < 4 or not re.fullmatch(r"S\d+", cells[0]):
                continue
            slot, token, harness, role = cells[0], _strip_code(cells[1]), cells[2], cells[3]
            note = cells[5] if len(cells) > 5 else ""
            model = (slots_json.get(slot) or {}).get("model")
            con.execute("""INSERT INTO slots(slot,token,harness,model,role,note,updated) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(slot) DO UPDATE SET token=excluded.token,harness=excluded.harness,model=excluded.model,
                role=excluded.role,note=excluded.note,updated=excluded.updated""", (slot, token, harness, model, role, note, now))
            n_slots += 1
        # 6절 소유권: 경로|소유|비고
        n_own = 0
        for cells in _table_rows(text, r"^## 6\. 파일 소유권"):
            if len(cells) < 2:
                continue
            pat = _strip_code(cells[0])
            if not pat or pat in ("경로 패턴",):
                continue
            # `_table_rows` 는 **다음 `##` 까지**를 한 절로 본다. 6절 안에는 `### 아카이브
            # 수명주기` 가 있어 그 표(대상|옮길 곳|언제)가 소유권으로 섞여 들어왔다
            # (S4 검수 6번: `'4절` 핸드오프 로그'` 같은 쓰레기 4행). 소유 칸이 슬롯·관리자·
            # 미배정·해당 슬롯 중 하나가 아니면 소유권 행이 아니다.
            if not re.fullmatch(r"S\d+|관리자(\(.*\))?|미배정|해당 슬롯", cells[1].strip()):
                continue
            con.execute("""INSERT INTO ownership(path_pattern,owner,note) VALUES(?,?,?)
                ON CONFLICT(path_pattern) DO UPDATE SET owner=excluded.owner,note=excluded.note""",
                        (pat, cells[1], cells[2] if len(cells) > 2 else ""))
            n_own += 1
        # 3절 보드: ID|태스크|담당|상태|이어받음|산출물
        n_tasks = 0
        for cells in _table_rows(text, r"^## 3\. 작업 보드"):
            if len(cells) < 4 or not re.fullmatch(r"T-\d+\w*", cells[0]):
                continue
            con.execute("""INSERT INTO tasks(id,title,slot,status,inherited,artifacts,created,updated) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,slot=excluded.slot,status=excluded.status,
                inherited=excluded.inherited,artifacts=excluded.artifacts,updated=excluded.updated""",
                        (cells[0], cells[1], cells[2], cells[3], cells[4] if len(cells) > 4 else "",
                         cells[5] if len(cells) > 5 else "", now, now))
            n_tasks += 1
        # 4.5 큐. **표가 사라졌으면 손대지 않습니다** - 2단계에서 AIMEM.md 가 포인터 한 줄로
        # 바뀌면 `DELETE` 만 돌아 큐가 통째로 날아갑니다(마크다운이 더 이상 정본이 아닌데도).
        queue_rows = _table_rows(text, r"^## 4\.5 대기 큐")
        pos = 0
        if not queue_rows:
            pos = con.execute("SELECT COUNT(*) AS n FROM queue").fetchone()["n"]
            queue_rows = []
        else:
            con.execute("DELETE FROM queue")
        for cells in queue_rows:
            if len(cells) < 2 or not cells[1] or cells[0] in ("순서",):
                continue
            pos += 1
            con.execute("INSERT INTO queue(pos,task,slot_hint,inherited,note) VALUES(?,?,?,?,?)",
                        (pos, cells[1], cells[2] if len(cells) > 2 else "", cells[3] if len(cells) > 3 else "", cells[4] if len(cells) > 4 else ""))
        # 4절 로그 → events(kind='handoff'), 중복 방지는 (at, body 앞 80자)
        n_ev = 0
        m = re.search(r"^## 4\. 핸드오프 로그", text, re.M)
        if m:
            body = text[m.end():]
            nxt = re.search(r"^## ", body, re.M)
            body = body[:nxt.start()] if nxt else body
            entry = None
            entries = []
            for line in body.splitlines():
                if re.match(r"^- `\d{4}-\d{2}-\d{2} \d{2}:\d{2}`", line):
                    if entry:
                        entries.append(entry)
                    entry = line
                elif entry and line.startswith("  "):
                    entry += "\n" + line
            if entry:
                entries.append(entry)
            for e in reversed(entries):  # 오래된 것부터 seq 가 커지도록
                at = re.match(r"^- `([^`]+)`", e).group(1)
                rm = re.search(r"\*\*REV (\d+)", e)
                exists = con.execute("SELECT 1 FROM events WHERE kind='handoff' AND at=? AND substr(body,1,80)=?",
                                     (at, e[:80])).fetchone()
                if not exists:
                    con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                                (at, "관리자", int(rm.group(1)) if rm else None, "handoff", e))
                    n_ev += 1
        # 요청 JSON
        n_req = 0
        for f in sorted((ROOT / ".aimem" / "requests").glob("*.json")) if (ROOT / ".aimem" / "requests").exists() else []:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            con.execute("""INSERT INTO requests(id,title,detail,requester,status,created,updated,raw) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,detail=excluded.detail,requester=excluded.requester,
                status=excluded.status,updated=excluded.updated,raw=excluded.raw""",
                        (d.get("id") or f.stem, d.get("title"), d.get("detail"), d.get("requester"), d.get("status") or "NEW",
                         d.get("created"), d.get("updated") or now, json.dumps(d, ensure_ascii=False)))
            for st in d.get("subtasks") or []:
                if st.get("id"):
                    con.execute("UPDATE tasks SET request_id=? WHERE id=? AND request_id IS NULL", (d.get("id") or f.stem, st["id"]))
            n_req += 1
        # 그래프 JSON
        n_g = 0
        for f in sorted((ROOT / ".aimem" / "graph").glob("*.json")) if (ROOT / ".aimem" / "graph").exists() else []:
            if f.name.endswith("-nodes.json") or f.name.startswith("."):
                continue
            try:
                g = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if "nodes" not in g:
                continue
            con.execute("""INSERT INTO graphs(id,request,concurrency,created,updated,raw) VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET request=excluded.request,concurrency=excluded.concurrency,updated=excluded.updated,raw=excluded.raw""",
                        (g.get("id") or f.stem, g.get("request"), g.get("concurrency"), g.get("created"), g.get("updated"), json.dumps(g, ensure_ascii=False)))
            for n in g["nodes"]:
                tid = n["id"] if re.fullmatch(r"T-\d+\w*", str(n.get("id", ""))) else None
                con.execute("""INSERT INTO nodes(graph_id,node_id,task_id,title,slot,deps,verify,max_attempts,status,attempts)
                    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(graph_id,node_id) DO UPDATE SET task_id=excluded.task_id,title=excluded.title,
                    slot=excluded.slot,deps=excluded.deps,verify=excluded.verify,max_attempts=excluded.max_attempts,status=excluded.status,attempts=excluded.attempts""",
                            (g.get("id") or f.stem, n.get("id"), tid, n.get("title"), n.get("slot"), json.dumps(n.get("deps") or []),
                             n.get("verify"), n.get("max_attempts"), n.get("status"), len(n.get("attempts") or [])))
            n_g += 1
        # 실행 JSON (+ rc/lost)
        n_runs = 0
        runs_dir = ROOT / ".aimem" / "runs"
        for f in sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            rid = d.get("id") or f.stem
            rc_f, lost_f = runs_dir / f"{rid}.rc", runs_dir / f"{rid}.lost"
            rc = None
            state = "running"
            ended = None
            if lost_f.exists():
                state = "lost"
                try:
                    ended = json.loads(lost_f.read_text(encoding="utf-8")).get("ended")
                except ValueError:
                    pass
            elif rc_f.exists():
                try:
                    rc = int(rc_f.read_text().strip() or -1)
                except ValueError:
                    rc = -1
                state = "done"
                ended = dt.datetime.fromtimestamp(rc_f.stat().st_mtime).isoformat(timespec="seconds")
            else:
                pid = d.get("pid")
                if pid:
                    try:
                        import os
                        os.kill(pid, 0)
                    except OSError:
                        state = "lost"
            task = d.get("task")
            if not task:
                mm = re.match(r"(T-\d+\w*)", d.get("label") or "")
                task = mm.group(1) if mm else None
            con.execute("""INSERT INTO runs(id,task_id,slot,harness,model,attempt,label,write_paths,pid,started,ended,rc,state,brief_path,rev)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET task_id=COALESCE(excluded.task_id,runs.task_id),
                ended=excluded.ended,rc=excluded.rc,state=excluded.state,model=excluded.model,label=excluded.label""",
                        (rid, task, d.get("slot"), d.get("harness"), d.get("model"), d.get("attempt") or 1, d.get("label"),
                         json.dumps(d.get("write") or [], ensure_ascii=False), d.get("pid"), d.get("started"), ended, rc, state,
                         d.get("brief"), d.get("rev")))
            n_runs += 1
        con.commit()
    if verbose:
        print(f"migrate: slots {n_slots} / ownership {n_own} / tasks {n_tasks} / queue {pos} / events +{n_ev} / requests {n_req} / graphs {n_g} / runs {n_runs}")
    return 0


# ----------------------------------------------------------------- 질의
def rev(con):
    r = con.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
    return int(r["value"]) if r else None


def state_dict():
    with connect() as con:
        def rows(q, *p):
            return [dict(r) for r in con.execute(q, p)]
        out = {
            "generated": _now(), "rev": rev(con),
            "slots": rows("SELECT * FROM slots ORDER BY slot"),
            "ownership": rows("SELECT * FROM ownership ORDER BY path_pattern"),
            "tasks": rows("SELECT * FROM tasks ORDER BY id"),
            "queue": rows("SELECT * FROM queue ORDER BY pos"),
            "requests": rows("SELECT id,title,requester,status,created,updated FROM requests ORDER BY created"),
            "graphs": rows("SELECT id,request,concurrency,created,updated FROM graphs ORDER BY id"),
            "nodes": rows("SELECT * FROM nodes ORDER BY graph_id,node_id"),
            "runs": rows("SELECT * FROM runs ORDER BY started"),
            # 최근 50건 **더하기** 핸드오프 최근 12건. 합집합인 이유: `task`/`queue`/
            # `ownership` 이벤트가 한 라운드에 수십 건 쌓이면 `LIMIT 50` 안에서 핸드오프가
            # 밀려나, 웹 화면의 `4절` 로그가 2건으로 줄었다(REV 114 실측). 12 는
            # `5절` 의 "`4절` 로그 항목 수 12건" 상한과 같은 수다.
            "events": rows("""
                SELECT seq,at,actor,rev,kind,body FROM events
                 WHERE seq IN (SELECT seq FROM events ORDER BY seq DESC LIMIT 50)
                    OR seq IN (SELECT seq FROM events WHERE kind='handoff' ORDER BY seq DESC LIMIT 12)
                 ORDER BY seq DESC"""),
        }
        for r in out["runs"]:
            r["write_paths"] = json.loads(r["write_paths"] or "[]")
        for n in out["nodes"]:
            n["deps"] = json.loads(n["deps"] or "[]")
    return out


def cmd_state(a):
    print(json.dumps(state_dict(), ensure_ascii=False, indent=1))
    return 0


def cmd_check(a):
    """작업자 0.1 세 줄 검사: 슬롯·토큰·REV. 불일치면 rc 1 과 이유."""
    with connect() as con:
        r = con.execute("SELECT * FROM slots WHERE slot=?", (a.slot,)).fetchone()
        cur = rev(con)
        own = [row["path_pattern"] for row in con.execute("SELECT path_pattern FROM ownership WHERE owner=?", (a.slot,))]
    problems = []
    if not r:
        problems.append(f"슬롯 {a.slot} 이 명부에 없음")
    elif a.token and r["token"] != a.token:
        problems.append(f"확인토큰 불일치: 명부 {r['token']} / 지시 {a.token}")
    if a.rev is not None and cur != a.rev:
        problems.append(f"REV 불일치: 정본 {cur} / 지시 {a.rev}")
    if problems:
        print("\n".join("불일치: " + p for p in problems))
        return 1
    print(f"일치: {a.slot} 토큰 {r['token']} 하네스 {r['harness']} 모델 {r['model'] or '(하네스 기본)'} REV {cur}")
    print("소유 경로: " + (", ".join(own) if own else "(없음 - 태스크 배정 때 등재)"))
    return 0


def cmd_event(a):
    with connect() as con:
        cur = rev(con) or 0
        new = cur + 1 if a.bump else cur
        con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (_now(), a.actor, new, a.kind, a.body))
        if a.bump:
            con.execute("INSERT INTO meta(key,value) VALUES('rev',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(new),))
        con.commit()
    print(f"event 기록 (REV {new})")
    return 0


# ----------------------------------------------------------------- 렌더 (DB → 읽기 전용 마크다운 스냅샷)
#: 스냅샷의 생성 시각 줄. **린터의 바이트 일치 검사는 이 줄만 건너뜁니다**
#: (`render` 를 돌릴 때마다 달라지는 유일한 값이라 여기 한 줄에 몰아 둡니다).
STAMP_PREFIX = "- 정본은 `.aimem/aimem.db` 입니다."


def render_text():
    """스냅샷 본문을 문자열로. 파일을 쓰지 않습니다 - 린터가 현물과 대조할 때 씁니다."""
    s = state_dict()
    L = [f"# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)",
         "", f"{STAMP_PREFIX} 이 파일을 손으로 고치지 마십시오. 생성 {s['generated']} / REV {s['rev']}", "",
         "## 2. 세션 명부", "", "| 슬롯 | 확인토큰 | 하네스 | 모델 | 역할 | 비고 |", "| --- | --- | --- | --- | --- | --- |"]
    for r in s["slots"]:
        L.append(f"| {r['slot']} | `{r['token']}` | {r['harness']} | {r['model'] or '(하네스 기본)'} | {r['role'] or ''} | {r['note'] or ''} |")
    L += ["", "## 3. 작업 보드", "", "| ID | 요청 | 태스크 | 담당 | 상태 | 산출물 |", "| --- | --- | --- | --- | --- | --- |"]
    for t in s["tasks"]:
        L.append(f"| {t['id']} | {t['request_id'] or '-'} | {t['title'] or ''} | {t['slot'] or '-'} | {t['status']} | {t['artifacts'] or ''} |")
    L += ["", "## 4. 이벤트 로그 (최신 50)", ""]
    for e in s["events"]:
        L.append(f"- `{e['at']}` {e['actor'] or ''} [{e['kind']}] REV {e['rev'] or '-'}: {(e['body'] or '').replace(chr(10), ' ')[:300]}")
    L += ["", "## 4.5 대기 큐", "", "| 순서 | 태스크 | 후보 슬롯 | 비고 |", "| --- | --- | --- | --- |"]
    for q in s["queue"]:
        L.append(f"| {q['pos']} | {q['task']} | {q['slot_hint'] or ''} | {q['note'] or ''} |")
    L += ["", "## 6. 파일 소유권", "", "| 경로 패턴 | 쓰기 소유 | 비고 |", "| --- | --- | --- |"]
    for o in s["ownership"]:
        L.append(f"| `{o['path_pattern']}` | {o['owner']} | {o['note'] or ''} |")
    L += ["", "## 요청", "", "| id | 제목 | 요청자 | 상태 | 생성 |", "| --- | --- | --- | --- | --- |"]
    for q in s["requests"]:
        L.append(f"| {q['id']} | {q['title'] or ''} | {q['requester'] or ''} | {q['status']} | {q['created'] or ''} |")
    L += ["", "## 실행 (최근 30)", "", "| run id | 태스크 | 슬롯 | 하네스 | 모델 | 시도 | 상태 | rc | 시작 | 끝 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in s["runs"][-30:]:
        L.append(f"| {r['id']} | {r['task_id'] or '-'} | {r['slot']} | {r['harness']} | {r['model'] or ''} | {r['attempt']} | {r['state']} | {'' if r['rc'] is None else r['rc']} | {(r['started'] or '')[11:19]} | {(r['ended'] or '')[11:19]} |")
    return "\n".join(L) + "\n"


def sync_rev_in_aimem():
    """2단계: REV 의 정본은 DB 다. AIMEM.md 서문 6행의 REV 를 DB 값으로 맞춘다."""
    if not AIMEM.exists():
        return None
    with connect() as con:
        cur = rev(con)
    if cur is None:
        return None
    text = AIMEM.read_text(encoding="utf-8")
    new = re.sub(r"- \*\*REV: \d+\*\*", f"- **REV: {cur}**", text, count=1)
    if new != text:
        AIMEM.write_text(new, encoding="utf-8")
        return cur
    return None


def render():
    body = render_text()
    STATE_MD.write_text(body, encoding="utf-8")
    bumped = sync_rev_in_aimem()
    print(f"render: {STATE_MD} ({body.count(chr(10))} lines)"
          + (f" / AIMEM.md 서문 REV -> {bumped}" if bumped else ""))
    return 0


# ----------------------------------------------------------------- 쓰기 명령 (관리자용, 2단계에서 마크다운 편집을 대체)
def _upsert(con, table, key_col, key, fields, defaults):
    """있으면 **준 필드만** 고치고, 없으면 기본값을 채워 넣습니다.

    옛 구현은 `INSERT ... ON CONFLICT DO UPDATE` 한 문장이었는데, 갱신인데도 INSERT 쪽
    NOT NULL 검사가 먼저 걸려 `request set --id X --detail ...`(상태 생략)이 실패했고,
    `task set` 은 상태를 생략하면 기존 상태를 `TODO` 로 **덮었습니다** (2026-11-10 실측).
    """
    given = {k: v for k, v in fields.items() if v is not None}
    row = con.execute(f"SELECT 1 FROM {table} WHERE {key_col}=?", (key,)).fetchone()
    if row:
        if given:
            sets = ", ".join(f"{k}=?" for k in given)
            con.execute(f"UPDATE {table} SET {sets} WHERE {key_col}=?", (*given.values(), key))
        return "갱신"
    full = dict(defaults)
    full.update(given)
    full[key_col] = key
    cols = ", ".join(full)
    con.execute(f"INSERT INTO {table}({cols}) VALUES({', '.join('?' * len(full))})", tuple(full.values()))
    return "생성"


def cmd_task(a):
    with connect() as con:
        now = _now()
        if a.action == "set":
            if not a.id:
                sys.exit("task set 에는 --id 가 필요합니다")
            what = _upsert(con, "tasks", "id", a.id,
                           {"request_id": a.request, "title": a.title, "slot": a.slot, "status": a.status,
                            "artifacts": a.artifacts, "updated": now},
                           {"status": "TODO", "created": now})
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                        (now, a.actor, rev(con), "task", f"{a.id} {a.status or ''} {a.slot or ''} {a.title or ''}".strip()))
            con.commit(); print(f"task {a.id} {what}")
        elif a.action == "list":
            for r in con.execute("SELECT id,request_id,slot,status,title FROM tasks ORDER BY id"):
                print(f"  {r['id']:<7} {r['status']:<11} {r['slot'] or '-':<4} {r['request_id'] or '-':<22} {r['title'] or ''}")
    return 0


def _sync_request_file(req_id, status=None, title=None, detail=None):
    """`migrate` 는 `.aimem/requests/*.json` 을 다시 적재합니다 - DB 만 고치면 다음 migrate 가
    옛 값으로 되돌립니다. 그래서 요청 파일도 같은 값으로 맞춥니다 (있을 때만)."""
    d = ROOT / ".aimem" / "requests"
    if not d.exists():
        return False
    for f in d.glob("*.json"):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(obj, dict) or obj.get("id") != req_id:
            continue
        for k, v in (("status", status), ("title", title), ("detail", detail)):
            if v is not None:
                obj[k] = v
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, f)
        return True
    return False


def cmd_request(a):
    with connect() as con:
        now = _now()
        if a.action == "set":
            if not a.id:
                sys.exit("request set 에는 --id 가 필요합니다")
            what = _upsert(con, "requests", "id", a.id,
                           {"title": a.title, "detail": a.detail, "requester": a.requester,
                            "status": a.status, "updated": now},
                           {"status": "NEW", "created": now})
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (now, a.actor, rev(con), "request", f"{a.id} {a.status or ''} {a.title or ''}".strip()))
            con.commit()
            synced = _sync_request_file(a.id, a.status, a.title, a.detail)
            print(f"request {a.id} {what}" + (" (요청 파일도 맞춤)" if synced else ""))
        elif a.action == "list":
            for r in con.execute("SELECT id,status,requester,title FROM requests ORDER BY created"):
                print(f"  {r['id']:<26} {r['status']:<12} {r['requester'] or '':<16} {r['title'] or ''}")
    return 0


def cmd_archive(a):
    """`8.0` 「끝난 작업의 보관·폐기」 구현 (REV 115 결정, 요청 Q-261110-549a, 큐 12).

    `DONE` 으로 바뀐 지 `--days`(기본 14)일이 지난 태스크를 `.aimem/archive/board-<YYYY-MM>.md`
    에 **먼저 덧붙이고**, 파일에 들어간 것을 확인한 뒤에 DB 에서 내립니다(`아카이브 수명주기`).
    `--dry-run` 은 무엇을 옮길지만 보여 줍니다.
    """
    cutoff = (dt.datetime.now() - dt.timedelta(days=a.days)).isoformat(timespec="seconds")
    with connect() as con:
        rows = con.execute("SELECT id,title,slot,status,inherited,artifacts,updated FROM tasks "
                           "WHERE status='DONE' AND COALESCE(updated,created,'') < ? ORDER BY id", (cutoff,)).fetchall()
        if not rows:
            print(f"archive: {a.days}일 지난 DONE 태스크 없음 (기준 {cutoff})")
            return 0
        by_month = {}
        for r in rows:
            by_month.setdefault((r["updated"] or cutoff)[:7], []).append(r)
        for month, rs in sorted(by_month.items()):
            print(f"archive: {month} <- {', '.join(r['id'] for r in rs)}")
        if a.dry_run:
            return 0
        arch = ROOT / ".aimem" / "archive"
        arch.mkdir(parents=True, exist_ok=True)
        cell = lambda v: str(v or "-").replace("|", "\\|").replace("\n", " ")
        for month, rs in sorted(by_month.items()):
            f = arch / f"board-{month}.md"
            if not f.exists():
                y, m = month.split("-")
                f.write_text(f"# 작업 보드 아카이브 - {int(y)}년 {int(m)}월\n\n"
                             "`DONE` 이 된 지 14일이 지나 내린 행입니다 (`aimem_db.py archive`, `8.0` 보관·폐기).\n\n"
                             "| ID    | 태스크 | 담당 슬롯 | 상태 | 이어받음 | 산출물 |\n"
                             "| ----- | ------ | --------- | ---- | -------- | ------ |\n", encoding="utf-8")
            with f.open("a", encoding="utf-8") as fh:
                for r in rs:
                    fh.write(f"| {r['id']} | {cell(r['title'])} | {cell(r['slot'])} | DONE | {cell(r['inherited'])} | {cell(r['artifacts'])} |\n")
            text = f.read_text(encoding="utf-8")
            missing = [r["id"] for r in rs if f"| {r['id']} |" not in text]
            if missing:
                sys.exit(f"archive: {f.name} 에 {missing} 가 안 들어갔습니다 - DB 에서 내리지 않습니다")
        ids = [r["id"] for r in rows]
        con.execute(f"DELETE FROM tasks WHERE id IN ({','.join('?' * len(ids))})", ids)
        con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                    (_now(), a.actor, rev(con), "archive", f"DONE {a.days}일 경과 {len(ids)}건 -> board-*.md: {', '.join(ids)}"))
        con.commit()
        print(f"archive: {len(ids)}건 옮김")
    return 0


def cmd_ownership(a):
    with connect() as con:
        if a.action == "set":
            con.execute("""INSERT INTO ownership(path_pattern,owner,note) VALUES(?,?,?)
                ON CONFLICT(path_pattern) DO UPDATE SET owner=excluded.owner, note=COALESCE(excluded.note,ownership.note)""", (a.path, a.owner, a.note))
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (_now(), a.actor, rev(con), "ownership", f"{a.path} -> {a.owner}"))
            con.commit(); print(f"ownership {a.path} -> {a.owner}")
        elif a.action == "list":
            for r in con.execute("SELECT path_pattern,owner,note FROM ownership ORDER BY owner,path_pattern"):
                print(f"  {r['owner']:<10} {r['path_pattern']:<40} {r['note'] or ''}")
    return 0


def cmd_queue(a):
    """`4.5` 대기 큐. REV 114 에서 마크다운 표를 내리면서 신설했습니다.

    표를 쓰던 `aimem_board.py queue-add` / `queue-pop` 이 폐기됐으므로 **이것이
    유일한 큐 편집 경로**입니다. 없으면 `8.0-4-2`(큐 맨 위를 다음 슬롯에 배정)가
    돌지 않습니다.

    `pos` 는 1부터 연속이어야 합니다 - `drop` 뒤에 빈 번호가 남으면 "맨 위"가
    모호해지므로 **지운 뒤 다시 매깁니다.**
    """
    with connect() as con:
        # 읽고-쓰는 명령은 `BEGIN IMMEDIATE` 로 시작합니다. 기본 암묵 BEGIN 은
        # DML 에서야 열려서 앞선 `SELECT` 가 트랜잭션 밖이었고, 동시 `add` 둘이
        # 같은 `pos` 를 받아 둘째가 `IntegrityError` 로 죽었습니다 (S4 검수 9번).
        if a.action in ("add", "drop"):
            con.execute("BEGIN IMMEDIATE")
        if a.action == "list":
            for r in con.execute("SELECT pos,task,slot_hint,inherited,note FROM queue ORDER BY pos"):
                print(f"  {r['pos']:>2}  {r['slot_hint'] or '미배정':<8} {r['inherited'] or '-':<8} {r['task']}")
                if a.verbose and r["note"]:
                    print(f"      {r['note']}")
            return 0
        if a.action == "add":
            pos = (con.execute("SELECT COALESCE(MAX(pos),0) AS m FROM queue").fetchone()["m"]) + 1
            con.execute("INSERT INTO queue(pos,task,slot_hint,inherited,note) VALUES(?,?,?,?,?)",
                        (pos, a.task, a.slot_hint, a.inherited, a.note))
            body = f"queue +{pos} {a.task}"
        elif a.action == "drop":
            row = con.execute("SELECT task FROM queue WHERE pos=?", (a.pos,)).fetchone()
            if not row:
                print(f"큐에 {a.pos} 번이 없습니다")
                return 1
            con.execute("DELETE FROM queue WHERE pos=?", (a.pos,))
            # 번호 다시 매기기. `pos` 가 PRIMARY KEY 라 한 번에 `-1` 하면 충돌하므로
            # 통째로 읽어 지우고 다시 넣습니다 (큐는 수십 건이라 비용이 문제되지 않습니다).
            rest = [dict(r) for r in con.execute("SELECT task,slot_hint,inherited,note FROM queue ORDER BY pos")]
            con.execute("DELETE FROM queue")
            for i, r in enumerate(rest, 1):
                con.execute("INSERT INTO queue(pos,task,slot_hint,inherited,note) VALUES(?,?,?,?,?)",
                            (i, r["task"], r["slot_hint"], r["inherited"], r["note"]))
            body = f"queue -{a.pos} {row['task']}"
        con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                    (_now(), a.actor, rev(con), "queue", body))
        con.commit()
        print(body + f" (남은 {con.execute('SELECT COUNT(*) AS n FROM queue').fetchone()['n']}건)")
    return 0



# ---------------------------------------------------------------- slots (2026-11-10, 태석님 지시 "슬롯 하네스 추가·삭제 + 모델 지정")
HARNESSES = ("claude", "codex", "opencode")
SLOT_RE = re.compile(r"S\d{1,3}\Z")


def _slots_json_path():
    return ROOT / "tools" / "fleet_slots.json"


def _sync_slots_json(con):
    """`tools/fleet_slots.json` 은 DB 의 **거울**이다 - `fleet.py spawn`/`reader` 가 파일로 읽는 자리라 같이 맞춘다."""
    out = {}
    for r in con.execute("SELECT slot,harness,model FROM slots ORDER BY slot"):
        d = {"harness": r["harness"]}
        if r["model"]:
            d["model"] = r["model"]
        out[r["slot"]] = d
    p = _slots_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _slot_event(con, actor, body):
    con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (_now(), actor, rev(con), "slot", body))


def slot_list():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM slots ORDER BY slot")]


def next_slot_id():
    with connect() as con:
        nums = [int(r["slot"][1:]) for r in con.execute("SELECT slot FROM slots") if SLOT_RE.match(r["slot"])]
    return f"S{(max(nums) + 1) if nums else 1}"


def _check_slot_args(slot, harness, model):
    if slot is not None and not SLOT_RE.match(str(slot)):
        raise ValueError(f"슬롯 id 는 S<번호> 꼴이어야 합니다: {slot!r}")
    if harness is not None and harness not in HARNESSES:
        raise ValueError(f"하네스는 {'/'.join(HARNESSES)} 중 하나여야 합니다: {harness!r}")
    if model is not None and (not isinstance(model, str) or len(model) > 120 or not re.fullmatch(r"[A-Za-z0-9._:/\-\[\]]+", model)):
        raise ValueError(f"모델 id 꼴이 아닙니다: {model!r}")


def slot_add(slot=None, harness=None, model=None, role="", note="", actor="관리자"):
    """슬롯 추가. slot 을 생략하면 다음 번호. 돌려주는 값은 새 행(dict)."""
    import secrets
    if not harness:
        raise ValueError("하네스가 필요합니다")
    _check_slot_args(slot, harness, model)
    with connect() as con:
        slot = slot or next_slot_id()
        if con.execute("SELECT 1 FROM slots WHERE slot=?", (slot,)).fetchone():
            raise ValueError(f"{slot} 은 이미 있습니다")
        token = secrets.token_hex(3)
        con.execute("INSERT INTO slots(slot,token,harness,model,role,note,updated) VALUES(?,?,?,?,?,?,?)",
                    (slot, token, harness, model or None, role or "", note or "", _now()))
        _slot_event(con, actor, f"slot add {slot} {harness} 모델 {model or '(하네스 기본)'}" + (f" - {role}" if role else ""))
        _sync_slots_json(con)
        con.commit()
        return dict(con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone())


def slot_set(slot, harness=None, model=None, role=None, note=None, actor="관리자", clear_model=False):
    """슬롯 변경 - 준 값만 바꾼다. `clear_model=True` 면 모델을 하네스 기본으로 되돌린다."""
    _check_slot_args(slot, harness, model)
    with connect() as con:
        cur = con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone()
        if not cur:
            raise ValueError(f"{slot} 이 명부에 없습니다")
        changes = []
        if harness and harness != cur["harness"]:
            con.execute("UPDATE slots SET harness=? WHERE slot=?", (harness, slot)); changes.append(f"하네스 {cur['harness']}→{harness}")
        if clear_model:
            con.execute("UPDATE slots SET model=NULL WHERE slot=?", (slot,)); changes.append(f"모델 {cur['model'] or '-'}→(하네스 기본)")
        elif model is not None and model != cur["model"]:
            con.execute("UPDATE slots SET model=? WHERE slot=?", (model, slot)); changes.append(f"모델 {cur['model'] or '-'}→{model}")
        if role is not None and role != cur["role"]:
            con.execute("UPDATE slots SET role=? WHERE slot=?", (role, slot)); changes.append("역할")
        if note is not None and note != cur["note"]:
            con.execute("UPDATE slots SET note=? WHERE slot=?", (note, slot)); changes.append("비고")
        if changes:
            con.execute("UPDATE slots SET updated=? WHERE slot=?", (_now(), slot))
            _slot_event(con, actor, f"slot set {slot}: " + ", ".join(changes))
            _sync_slots_json(con)
            con.commit()
        return dict(con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone()), changes


def slot_open_tasks(slot):
    with connect() as con:
        return [r["id"] for r in con.execute("SELECT id FROM tasks WHERE slot=? AND status NOT IN ('DONE') ORDER BY id", (slot,))]


def slot_remove(slot, actor="관리자", force=False):
    """슬롯 삭제. 끝나지 않은 태스크가 배정돼 있으면 `force` 없이는 거절한다. 소유권 행은 같이 내린다."""
    _check_slot_args(slot, None, None)
    with connect() as con:
        cur = con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone()
        if not cur:
            raise ValueError(f"{slot} 이 명부에 없습니다")
        open_tasks = [r["id"] for r in con.execute("SELECT id FROM tasks WHERE slot=? AND status NOT IN ('DONE')", (slot,))]
        if open_tasks and not force:
            raise ValueError(f"{slot} 에 끝나지 않은 태스크가 있습니다: {', '.join(open_tasks)} (force 로 강제)")
        n_own = con.execute("DELETE FROM ownership WHERE owner=?", (slot,)).rowcount
        con.execute("DELETE FROM slots WHERE slot=?", (slot,))
        _slot_event(con, actor, f"slot remove {slot} ({cur['harness']}, 모델 {cur['model'] or '-'}, 소유권 {n_own}행 내림" + (f", 미완 태스크 {len(open_tasks)}건 강제" if open_tasks else "") + ")")
        _sync_slots_json(con)
        con.commit()
        return {"slot": slot, "ownership_removed": n_own, "open_tasks": open_tasks}


def cmd_slot(a):
    if a.action == "list":
        for r in slot_list():
            print(f"  {r['slot']}  {r['token']}  {r['harness']:<9} 모델 {r['model'] or '(하네스 기본)'}  {r['role'] or ''}")
        return 0
    try:
        if a.action == "add":
            r = slot_add(a.slot, a.harness, a.model, a.role or "", a.note or "", a.actor)
            print(f"추가: {r['slot']} {r['harness']} 모델 {r['model'] or '(하네스 기본)'} 토큰 {r['token']}")
        elif a.action == "set":
            r, ch = slot_set(a.slot, a.harness, a.model, a.role, a.note, a.actor, clear_model=bool(a.default_model))
            print(f"변경: {a.slot} " + (", ".join(ch) if ch else "바뀐 것 없음"))
        elif a.action == "remove":
            r = slot_remove(a.slot, a.actor, force=bool(a.force))
            print(f"삭제: {a.slot} (소유권 {r['ownership_removed']}행 내림)")
    except ValueError as e:
        print(f"거절: {e}")
        return 1
    return 0

def main():
    p = argparse.ArgumentParser(description="AIMEM 운영 상태 SQLite")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init"); sub.add_parser("migrate"); sub.add_parser("render"); sub.add_parser("state")
    c = sub.add_parser("check"); c.add_argument("--slot", required=True); c.add_argument("--token"); c.add_argument("--rev", type=int)
    e = sub.add_parser("event"); e.add_argument("--kind", required=True); e.add_argument("--body", required=True)
    e.add_argument("--actor", default="관리자"); e.add_argument("--bump", action="store_true", help="REV 를 하나 올린다")
    t = sub.add_parser("task"); t.add_argument("action", choices=["set", "list"]); t.add_argument("--id"); t.add_argument("--request")
    t.add_argument("--title"); t.add_argument("--slot"); t.add_argument("--status", choices=["TODO","ASSIGNED","IN-PROGRESS","REVIEW","DONE","BLOCKED"])
    t.add_argument("--artifacts"); t.add_argument("--actor", default="관리자")
    q = sub.add_parser("request"); q.add_argument("action", choices=["set", "list"]); q.add_argument("--id"); q.add_argument("--title")
    q.add_argument("--detail"); q.add_argument("--requester"); q.add_argument("--status", choices=["NEW","PLANNED","IN-PROGRESS","DONE","REJECTED"]); q.add_argument("--actor", default="관리자")
    o = sub.add_parser("ownership"); o.add_argument("action", choices=["set", "list"]); o.add_argument("--path"); o.add_argument("--owner"); o.add_argument("--note"); o.add_argument("--actor", default="관리자")
    sl = sub.add_parser("slot", help="슬롯 추가/변경/삭제/목록 - DB 정본 + tools/fleet_slots.json 거울 (웹 함대 현황에서도 됨)")
    sl.add_argument("action", choices=["add", "set", "remove", "list"]); sl.add_argument("--slot"); sl.add_argument("--harness", choices=HARNESSES)
    sl.add_argument("--model", help="openclaw 모델 키(예 anthropic/claude-opus-5-5, kisti/kistillm) 또는 claude 별칭(opus/sonnet/haiku)")
    sl.add_argument("--default-model", action="store_true", help="set: 모델을 하네스 기본으로 되돌린다"); sl.add_argument("--role"); sl.add_argument("--note")
    sl.add_argument("--force", action="store_true", help="remove: 미완 태스크가 있어도 삭제"); sl.add_argument("--actor", default="관리자")
    r = sub.add_parser("archive", help="DONE 이 된 지 N일 지난 태스크를 .aimem/archive/board-<YYYY-MM>.md 로 옮긴다 (8.0)")
    r.add_argument("--days", type=int, default=14); r.add_argument("--dry-run", action="store_true"); r.add_argument("--actor", default="관리자")
    u = sub.add_parser("queue", help="4.5 대기 큐 (관리자만 씁니다)")
    u.add_argument("action", choices=["list", "add", "drop"])
    u.add_argument("--task"); u.add_argument("--slot-hint", dest="slot_hint"); u.add_argument("--inherited")
    u.add_argument("--note"); u.add_argument("--pos", type=int); u.add_argument("--verbose", action="store_true")
    u.add_argument("--actor", default="관리자")
    a = p.parse_args()
    if a.cmd == "queue":
        if a.action == "add" and not a.task:
            p.error("queue add 에는 --task 가 필요합니다")
        if a.action == "drop" and a.pos is None:
            p.error("queue drop 에는 --pos 가 필요합니다")
    return {"init": cmd_init, "migrate": lambda a: migrate(), "render": lambda a: render(), "state": cmd_state,
            "check": cmd_check, "event": cmd_event, "task": cmd_task, "request": cmd_request,
            "ownership": cmd_ownership, "queue": cmd_queue, "archive": cmd_archive, "slot": cmd_slot}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
