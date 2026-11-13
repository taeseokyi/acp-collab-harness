#!/usr/bin/env python3
"""AIMEM 운영 상태 저장소 - SQLite (표준 라이브러리만). 태석님 결정 2026-11-09 18:25.

AIMEM.md 는 **규약 본문**만 남기고, 운영 상태(명부·보드·큐·소유권·로그·요청·세션)는 `.aimem/aimem.db` 가 정본이다.
`AIMEM-state.md` 는 `render` 가 DB 에서 뽑는 읽기 전용 스냅샷(명부·보드·큐·소유권·요청)이다.

  python3 tools/aimem_db.py init                  # 스키마 생성 (멱등)
  python3 tools/aimem_db.py migrate               # 파일에서 DB 를 맞춘다: 요청 JSON·handoff.md·세션 폴더 (멱등 upsert)
  python3 tools/aimem_db.py render                # AIMEM-state.md 스냅샷 생성
  python3 tools/aimem_db.py check --slot S2 --token d27e93 --rev 112   # 작업자 0.1 세 줄 검사
  python3 tools/aimem_db.py state                 # 웹 UI 용 JSON 한 덩어리
  python3 tools/aimem_db.py event --kind note --body "..."           # 이벤트 추가 (REV 가 하나 오른다)
"""
import argparse
import contextlib
import datetime as dt
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fleet_rt.harness import REAL as HARNESSES  # noqa: E402 - 하네스 목록의 정본
from fleet_rt import sessions as _rt_sessions  # noqa: E402 - 세션 폴더 → 색인 행의 정본

try:    # 시각은 설정 시간대 하나로 (`fleet.toml` `[time] zone`)
    from fleet_rt import timezone as _rt_tz
    _rt_tz.apply(pathlib.Path(__file__).resolve().parent.parent)
except Exception:  # noqa: BLE001
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / ".aimem" / "aimem.db"
AIMEM = ROOT / "AIMEM.md"
#: 핸드오프 로그의 정본은 DB `events(kind='handoff')` 하나다. `.aimem/handoff.md` 는 최신 HANDOFF_MAX 건 생성물이고,
#: 창에서 밀려난 항목은 같은 쓰기 트랜잭션에서 월별 아카이브로 내보낸다.
HANDOFF = ROOT / ".aimem" / "handoff.md"
HANDOFF_MAX = 12          # handoff.md 에 보이는 최신 항목 수 (AIMEM.md 5절)
HANDOFF_ENTRY_MAX = 1200  # 항목당 문자 수 상한 (5절). `handoff add --allow-long` 으로만 넘긴다
HANDOFF_ENTRY_RE = re.compile(r"^- `(\d{4}-\d{2}-\d{2} \d{2}:\d{2})`")
_ARCHIVE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
HANDOFF_HEADER = ("# Handoff Log (generated)\n\n"
                  "Generated from `events(kind=handoff)` in `.aimem/aimem.db` - **do not edit; edits are overwritten.** "
                  "Add an entry with `python3 tools/aimem_db.py handoff add`. Newest first, latest "
                  f"{HANDOFF_MAX}; older entries are exported to `.aimem/archive/handoff-YYYY-MM.md`. "
                  "The protocol is AIMEM.md Section 4.\n\n")


#: 태스크·요청 상태 어휘 (CLI choices 와 검사가 같이 쓴다)
TASK_STATUSES = ("TODO", "ASSIGNED", "IN-PROGRESS", "REVIEW", "DONE", "BLOCKED")
REQUEST_STATUSES = ("NEW", "PLANNED", "IN-PROGRESS", "DONE", "REJECTED")


def _write_atomic(path, text):
    """같은 폴더의 고유 임시 파일에 쓰고 바꿔 넣는다 - 동시에 쓰는 이끼리 임시 파일을 밟지 않게."""
    path = pathlib.Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def parse_handoff_entries(text):
    """`- \`YYYY-MM-DD HH:MM\` …` 로 시작하는 항목(2칸 들여쓴 이어지는 줄 포함)을 파일 순서대로 돌려준다 (복구용 `migrate` 가 쓴다)."""
    entries, cur = [], None
    for line in text.splitlines():
        if HANDOFF_ENTRY_RE.match(line):
            if cur:
                entries.append(cur)
            cur = line
        elif cur is not None and line.startswith("  "):
            cur += "\n" + line
        else:
            if cur:
                entries.append(cur)
            cur = None
    if cur:
        entries.append(cur)
    return entries


def _handoff_line(row):
    """events 행 → 로그 한 줄. 옛 행은 본문에 머리(`- \`시각\` 작성자:`)가 들어 있어 그대로 쓴다."""
    body = row["body"] or ""
    if HANDOFF_ENTRY_RE.match(body):
        return body
    stamp = str(row["at"])[:16].replace("T", " ")
    return f"- `{stamp}` {row['actor'] or '관리자'}: {body}"


def _handoff_rows(con):
    """최신 먼저. REV 가 실제 순서다(옛 항목의 시각은 손으로 적은 값이라 어긋난 것이 있다); 같은 REV 는 시각·seq 순."""
    rows = con.execute("SELECT seq, at, actor, rev, body FROM events WHERE kind='handoff'").fetchall()
    return sorted(rows, key=lambda r: (r["rev"] if r["rev"] is not None else -1,
                                       str(r["at"])[:16].replace("T", " "), r["seq"]), reverse=True)


def handoff_entries(con=None):
    """DB 의 핸드오프 항목 전부, 최신 먼저."""
    if con is not None:
        return [_handoff_line(r) for r in _handoff_rows(con)]
    with contextlib.closing(connect()) as c:
        return [_handoff_line(r) for r in _handoff_rows(c)]


def render_handoff_text(con):
    lines = [_handoff_line(r) for r in _handoff_rows(con)[:HANDOFF_MAX]]
    return HANDOFF_HEADER + ("\n".join(lines) + "\n" if lines else "")


@contextlib.contextmanager
def _write_txn():
    """쓰기 잠금을 먼저 잡는 트랜잭션(`BEGIN IMMEDIATE`). 이 안에서 읽고 쓰는 것은 다른 작성자와 겹치지 않는다."""
    con = connect()
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            yield con
        except BaseException:
            con.execute("ROLLBACK")
            raise
        con.execute("COMMIT")
    finally:
        con.close()


def _sync_handoff_files(con):
    """DB → `.aimem/handoff.md`(최신 창) + 창 밖 항목의 월별 아카이브 내보내기. **호출자가 쓰기 트랜잭션을 쥐고 있어야 한다** -
    그래서 파일 쓰기까지 DB 쓰기 잠금 하나로 직렬화된다. 내보낸 건수를 돌려준다."""
    con.execute("CREATE TABLE IF NOT EXISTS handoff_archived(seq INTEGER PRIMARY KEY)")
    rows = _handoff_rows(con)
    done = {r[0] for r in con.execute("SELECT seq FROM handoff_archived")}
    exported = 0
    arch = ROOT / ".aimem" / "archive"
    handoff = ROOT / ".aimem" / "handoff.md"
    for r in reversed(rows[HANDOFF_MAX:]):   # 오래된 것부터
        if r["seq"] in done:
            continue
        line = _handoff_line(r)
        f = arch / f"handoff-{line[3:10]}.md"
        arch.mkdir(parents=True, exist_ok=True)
        old = f.read_text(encoding="utf-8") if f.exists() else f"# Handoff log archive - {line[3:10]}\n\n"
        if line not in old.splitlines():      # 내보낸 뒤 커밋 전에 죽었다가 다시 도는 경우에도 두 번 붙지 않는다
            f.write_text(old.rstrip("\n") + "\n" + line + "\n", encoding="utf-8")
        con.execute("INSERT OR IGNORE INTO handoff_archived(seq) VALUES(?)", (r["seq"],))
        exported += 1
    text = render_handoff_text(con)
    if not handoff.exists() or handoff.read_text(encoding="utf-8") != text:
        handoff.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(handoff, text)
    return exported


def handoff_sync():
    """`render` 와 `handoff sync` 가 부른다 - 생성 파일을 DB 에 맞춘다."""
    with _write_txn() as con:
        return _sync_handoff_files(con)


def _import_handoff_entries(con, entries):
    """복구용: 파일의 항목을 events(kind='handoff') 로 적재한다(DB 를 잃었을 때 `migrate`). 이미 있는 항목은 건너뛴다."""
    n = 0
    ordered = list(reversed(list(entries)))  # 오래된 것부터 seq 가 커지도록
    last_rev = None
    for i, e in enumerate(ordered):
        m = HANDOFF_ENTRY_RE.match(e)
        at = m.group(1)
        text = e[m.end():].lstrip()   # 머리(시각)를 뗀 본문
        rm = re.search(r"\*\*REV (\d+)", e)
        if rm:
            rev = int(rm.group(1))
        elif last_rev is not None:
            rev = last_rev  # 바로 앞(더 오래된) 항목의 REV 를 물려받는다
        else:
            rev = 0  # 앞에 아무것도 없고 뒤에도 REV 가 없을 때
            for later in ordered[i + 1:]:
                lm = re.search(r"\*\*REV (\d+)", later)
                if lm:
                    rev = int(lm.group(1))  # 뒤(더 새것)에서 처음 나오는 REV
                    break
        last_rev = rev
        exists = con.execute(
            "SELECT 1 FROM events WHERE kind='handoff' AND replace(substr(at,1,16),'T',' ')=? AND "
            "(substr(body,1,80)=? OR substr(body,1,80)=? OR substr(COALESCE(actor,'관리자')||': '||body,1,80)=?)",
            (at, text[:80], e[:80], text[:80])).fetchone()
        if not exists:
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                        (at, "관리자", rev, "handoff", e))
            n += 1
    return n


def handoff_add(body, actor="관리자", bump=False, allow_long=False, when=None, expect_rev=None):
    """핸드오프 항목 하나를 DB 에 넣고 생성 파일을 맞춘다. (REV, 아카이브로 내보낸 건수) 를 돌려준다.

    전부 쓰기 트랜잭션 하나 안이다 - REV 읽기·올리기, 행 삽입, 파일 생성이 다른 작성자와 겹치지 않고, 중간에
    실패하면 통째로 되돌아간다. `expect_rev` 를 주면 그 사이 다른 세션이 REV 를 올렸을 때 쓰지 않고 거절한다."""
    body = (body or "").strip()
    if not body:
        raise ValueError("handoff add: 본문이 비었습니다")
    if len(body) > HANDOFF_ENTRY_MAX and not allow_long:
        raise ValueError(f"handoff add: 항목 {len(body)}자 - 상한 {HANDOFF_ENTRY_MAX}자 (5절). 경위는 해당 절이나 아카이브에 쓰고 로그에는 무엇이 바뀌었나만 남기십시오. 정말 필요하면 --allow-long")
    at = when or dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with _write_txn() as con:
        cur = rev(con) or 0
        if expect_rev is not None and cur != expect_rev:
            raise ValueError(f"handoff add: REV 불일치 - 예상 {expect_rev}, 지금 {cur}. 그 사이 다른 세션이 썼습니다. "
                             f"`handoff list --last 3` 으로 무엇이 바뀌었는지 읽고 다시 하십시오 (아무것도 쓰지 않았습니다)")
        new = cur + 1 if bump else cur
        if bump:
            con.execute("INSERT INTO meta(key,value) VALUES('rev',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(new),))
        con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (at, actor, new, "handoff", body))
        exported = _sync_handoff_files(con)
    return new, exported


def cmd_handoff(a):
    """핸드오프 로그 (AIMEM.md 4절). add / list / sync."""
    if a.action == "add":
        if not a.body:
            sys.exit("handoff add 에는 --body 가 필요합니다")
        try:
            new, exported = handoff_add(a.body, a.actor, a.bump, a.allow_long, expect_rev=a.expect_rev)
        except ValueError as e:
            sys.exit(str(e))
        print(f"handoff: 항목 추가 (REV {new}) → {HANDOFF}" + (f" / 아카이브로 {exported}건" if exported else ""))
        return 0
    if a.action == "list":
        entries = handoff_entries()
        for e in entries if a.all else entries[: a.last or HANDOFF_MAX]:
            print(e)
        if not entries:
            print("handoff: 항목 없음")
        return 0
    exported = handoff_sync()
    print(f"handoff sync: {HANDOFF} 를 DB 에 맞춤 (최신 {HANDOFF_MAX}건)" + (f" / 아카이브로 {exported}건" if exported else ""))
    return 0


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS slots(slot TEXT PRIMARY KEY, token TEXT NOT NULL, harness TEXT NOT NULL,
  model TEXT, role TEXT, note TEXT, updated TEXT, origin TEXT DEFAULT 'owner', round INTEGER);
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


#: 표가 생긴 뒤에 더한 칸 (이름, 정의). 이전 마이그레이션 장치가 없어 `CREATE TABLE IF NOT EXISTS` 로는 옛 DB 에 칸이 안 생긴다 -
#: 열 때마다 없는 칸만 `ALTER TABLE` 로 더한다. `origin`: 누가 둔 슬롯인가(owner 사람 · manager 관리자), `round`: 관리자가 더한 라운드.
_ADDED_COLUMNS = {"slots": (("origin", "TEXT DEFAULT 'owner'"), ("round", "INTEGER"))}


def _ensure_columns(con):
    for table, cols in _ADDED_COLUMNS.items():
        try:
            have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        if not have:
            continue                    # 표가 아직 없다 - `init` 의 SCHEMA 가 칸까지 만든다
        for name, decl in cols:
            if name in have:
                continue
            try:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                con.commit()
            except sqlite3.OperationalError:
                pass                    # 다른 프로세스가 같은 순간 더했거나 잠김 - 다음에 열 때 다시 본다


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    _ensure_columns(con)
    return con


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def cmd_init(a=None):
    from fleet_rt.base import SESSIONS_DDL  # noqa: PLC0415 - `sessions` 표 정의는 `fleet_rt.base` 한 곳
    with connect() as con:
        con.executescript(SCHEMA)
        con.executescript(SESSIONS_DDL)
    print(f"ok: {DB}")
    return 0


# ----------------------------------------------------------------- 적재 (파일 → DB)
def load_request_files(con, now=None):
    """`.aimem/requests/*.json` 을 requests 표에 적재합니다(멱등 upsert). 적재한 건수.

    웹 요청 폼은 **파일만** 만듭니다. `request list` 는 DB 를 읽으므로, 읽기 전에 이것을 부르지 않으면
    방금 넣은 `NEW` 요청이 관리자에게 보이지 않습니다 (REV 145 - 표준 브리프의 할 일이 `request list` 다).
    """
    now = now or _now()
    d0 = ROOT / ".aimem" / "requests"
    n_req = 0
    for f in sorted(d0.glob("*.json")) if d0.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        con.execute("""INSERT INTO requests(id,title,detail,requester,status,created,updated,raw) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,detail=excluded.detail,requester=excluded.requester,
            status=excluded.status,updated=excluded.updated,raw=excluded.raw""",
                    (d.get("id") or f.stem, d.get("title"), d.get("detail"), d.get("requester"), d.get("status") or "NEW",
                     d.get("created"), d.get("updated") or now, json.dumps(d, ensure_ascii=False)))
        for st in d.get("subtasks") or []:
            if isinstance(st, dict) and st.get("id"):
                con.execute("UPDATE tasks SET request_id=? WHERE id=? AND request_id IS NULL", (d.get("id") or f.stem, st["id"]))
        n_req += 1
    return n_req


# ----------------------------------------------------------------- 세션 색인 (폴더 -> sessions 표)
def _read_json_file(p):
    try:
        d = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def session_row_from_dir(d):
    """세션 폴더 하나를 `sessions` 표의 한 행(dict)으로 - 규칙은 `fleet_rt.sessions.index_row` 한 곳. `meta.json` 이 없으면 None."""
    d = pathlib.Path(d)
    if not (d / "meta.json").is_file():
        return None
    row = _rt_sessions.index_row(d)
    return row if isinstance(row, dict) and row.get("id") else None


def index_sessions(con):
    """`<aimem>/sessions/*` 를 훑어 `sessions` 표를 다시 맞춘다 (멱등 upsert). 폴더가 정본이다.
    토큰·마지막 사건 시각은 감독이 적는 값이라 덮지 않는다. 폴더가 없는 행은 건드리지 않는다. 적재 건수를 준다."""
    sdir = ROOT / ".aimem" / "sessions"
    n = 0
    for d in sorted(sdir.iterdir()) if sdir.is_dir() else []:
        if not d.is_dir():
            continue
        row = session_row_from_dir(d)
        if not row:
            continue
        if isinstance(row.get("write_paths"), list):
            row["write_paths"] = json.dumps(row["write_paths"], ensure_ascii=False)
        cols = [c for c in row if c in _SESSION_COLS]
        con.execute(f"INSERT INTO sessions({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    + ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("id", "tokens_in", "tokens_out", "cost_usd", "last_event_at")),
                    [row[c] for c in cols])
        n += 1
    return n


_SESSION_COLS = ("id", "role", "round", "task_id", "slot", "harness", "model", "provider", "pid", "pgid",
                 "harness_session_id", "state", "started", "ended", "last_event_at", "rc", "report_status",
                 "tokens_in", "tokens_out", "cost_usd", "fail_kind", "attempt", "label", "write_paths", "dir")


def migrate(verbose=True):
    """파일에서 DB 를 맞춘다(멱등): 스키마, 비었을 때만 REV 씨앗, `.aimem/handoff.md` 복구, 요청 파일, 세션 색인."""
    cmd_init()
    text = AIMEM.read_text(encoding="utf-8") if AIMEM.exists() else ""
    now = _now()
    with connect() as con:
        # REV 의 정본은 DB 다 - 서문 값은 DB 에 REV 가 없을 때만 씨앗으로 읽는다 (덮으면 올린 REV 가 되돌아간다)
        rev_m = re.search(r"- \*\*REV: (\d+)\*\*", text)
        if rev_m and rev(con) is None:
            con.execute("INSERT INTO meta(key,value) VALUES('rev',?)", (rev_m.group(1),))
        con.execute("INSERT INTO meta(key,value) VALUES('migrated_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now,))
        entries = parse_handoff_entries(HANDOFF.read_text(encoding="utf-8")) if HANDOFF.exists() else []
        n_ev = _import_handoff_entries(con, entries)
        n_req = load_request_files(con, now)
        n_sess = index_sessions(con)
        con.commit()
    if verbose:
        print(f"migrate: events +{n_ev} / requests {n_req} / sessions {n_sess}")
    return 0


# ----------------------------------------------------------------- 질의
def rev(con):
    r = con.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
    return int(r["value"]) if r else None


def state_dict():
    with connect() as con:
        def rows(q, *p):
            return [dict(r) for r in con.execute(q, p)]

        def session_rows():
            # 읽기는 표를 만들지 않는다. 엔진 v2 이전에 만든 DB 에는 `sessions` 표가 없다 (init/migrate 가 만든다)
            try:
                return rows("SELECT * FROM sessions ORDER BY started")
            except sqlite3.OperationalError:
                return []
        out = {
            "generated": _now(), "rev": rev(con),
            "slots": rows("SELECT * FROM slots ORDER BY slot"),
            "ownership": rows("SELECT * FROM ownership ORDER BY path_pattern"),
            "tasks": rows("SELECT * FROM tasks ORDER BY id"),
            "queue": rows("SELECT * FROM queue ORDER BY pos"),
            "requests": rows("SELECT id,title,requester,status,created,updated FROM requests ORDER BY created"),
            "runs": rows("SELECT * FROM runs ORDER BY started"),
            "sessions": session_rows(),
            # 최근 50건에 핸드오프 최근 HANDOFF_MAX 건을 더한다 - 다른 이벤트에 밀려 화면의 로그가 비지 않게
            "events": rows(f"""
                SELECT seq,at,actor,rev,kind,body FROM events
                 WHERE seq IN (SELECT seq FROM events ORDER BY seq DESC LIMIT 50)
                    OR seq IN (SELECT seq FROM events WHERE kind='handoff' ORDER BY seq DESC LIMIT {HANDOFF_MAX})
                 ORDER BY seq DESC"""),
        }
        for r in out["runs"]:
            r["write_paths"] = json.loads(r["write_paths"] or "[]")
        for r in out["sessions"]:
            r["write_paths"] = json.loads(r["write_paths"] or "[]")
        # `runs` 는 옛 실행 표 + 세션을 같은 꼴로 합쳐 시작 시각 순(새것이 뒤)으로 준다
        out["runs"] += [{"id": r["id"], "task_id": r["task_id"], "slot": r["slot"], "harness": r["harness"],
                         "model": r["model"], "attempt": r["attempt"], "label": r["label"],
                         "write_paths": r["write_paths"], "pid": r["pid"], "started": r["started"], "ended": r["ended"],
                         "rc": r["rc"], "state": r["state"], "report_status": r["report_status"],
                         "brief_path": str(pathlib.Path(r["dir"]) / "brief.md") if r["dir"] else None, "rev": None}
                        for r in out["sessions"]]
        out["runs"].sort(key=lambda r: r["started"] or "")
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
    """스냅샷 본문을 문자열로 (파일은 쓰지 않는다 - 린터가 현물과 대조할 때 쓴다).

    명부·보드·큐·소유권·요청만 싣는다. 이벤트·실행·세션은 세션이 뜨고 질 때마다 바뀌어 스냅샷을 늘 낡게 만든다."""
    s = state_dict()
    L = [f"# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)",
         "", f"{STAMP_PREFIX} 이 파일을 손으로 고치지 마십시오. 생성 {s['generated']} / REV {s['rev']}", "",
         "## 2. 세션 명부", "", "| 슬롯 | 확인토큰 | 하네스 | 모델 | 역할 | 비고 |", "| --- | --- | --- | --- | --- | --- |"]
    for r in s["slots"]:
        L.append(f"| {r['slot']} | `{r['token']}` | {r['harness']} | {r['model'] or '(하네스 기본)'} | {r['role'] or ''} | {r['note'] or ''} |")
    L += ["", "## 3. 작업 보드", "", "| ID | 요청 | 태스크 | 담당 | 상태 | 산출물 |", "| --- | --- | --- | --- | --- | --- |"]
    for t in s["tasks"]:
        L.append(f"| {t['id']} | {t['request_id'] or '-'} | {t['title'] or ''} | {t['slot'] or '-'} | {t['status']} | {t['artifacts'] or ''} |")
    L += ["", "## 4.5 대기 큐", "", "| 순서 | 태스크 | 후보 슬롯 | 비고 |", "| --- | --- | --- | --- |"]
    for q in s["queue"]:
        L.append(f"| {q['pos']} | {q['task']} | {q['slot_hint'] or ''} | {q['note'] or ''} |")
    L += ["", "## 6. 파일 소유권", "", "| 경로 패턴 | 쓰기 소유 | 비고 |", "| --- | --- | --- |"]
    for o in s["ownership"]:
        L.append(f"| `{o['path_pattern']}` | {o['owner']} | {o['note'] or ''} |")
    L += ["", "## 요청", "", "| id | 제목 | 요청자 | 상태 | 생성 |", "| --- | --- | --- | --- | --- |"]
    for q in s["requests"]:
        L.append(f"| {q['id']} | {q['title'] or ''} | {q['requester'] or ''} | {q['status']} | {q['created'] or ''} |")
    return "\n".join(L) + "\n"


def sync_rev_in_aimem():
    """2단계: REV 의 정본은 DB 다. AIMEM.md 서문 6행의 REV 를 DB 값으로 맞춘다."""
    aimem = ROOT / "AIMEM.md"
    if not aimem.exists():
        return None
    with connect() as con:
        cur = rev(con)
    if cur is None:
        return None
    text = aimem.read_text(encoding="utf-8")
    new = re.sub(r"- \*\*REV: \d+\*\*", f"- **REV: {cur}**", text, count=1)
    if new != text:
        # REV 가 바뀐 그 render 가 '최종 갱신' 줄도 맞춘다
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M") + " KST"
        new = re.sub(r"^- (최종 갱신|Last updated): .*$", lambda m: f"- {m.group(1)}: {stamp}", new, count=1, flags=re.M)
        aimem.write_text(new, encoding="utf-8")
        return cur
    return None


def render(sync_aimem=True):
    body = render_text()
    state_md = ROOT / "AIMEM-state.md"

    def unstamped(text):                 # 생성 시각 줄만 다른 것은 같은 스냅샷이다
        return [ln for ln in text.splitlines() if not ln.startswith(STAMP_PREFIX)]
    try:
        old = state_md.read_text(encoding="utf-8")
    except OSError:
        old = None
    if old is None or unstamped(old) != unstamped(body):   # 내용이 같으면 다시 쓰지 않는다 - 준비 점검마다 작업 트리가 더러워지지 않게
        state_md.write_text(body, encoding="utf-8")
    bumped = sync_rev_in_aimem() if sync_aimem else None
    handoff_sync()   # .aimem/handoff.md 도 DB 에서 만드는 생성물이다
    print(f"render: {state_md} ({body.count(chr(10))} lines)"
          + (f" / AIMEM.md 서문 REV -> {bumped}" if bumped else ""))
    return 0


# ----------------------------------------------------------------- 쓰기 명령 (관리자용)
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
        load_request_files(con, now)     # 웹에서 방금 넣은 요청에도 `--request` 로 이을 수 있게
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
            if a.request:
                note_round_request(a.request)     # 라운드 도중 들어온 요청도 그 라운드 기록에
        elif a.action == "list":
            for r in con.execute("SELECT id,request_id,slot,status,title FROM tasks ORDER BY id"):
                print(f"  {r['id']:<7} {r['status']:<11} {r['slot'] or '-':<4} {r['request_id'] or '-':<22} {r['title'] or ''}")
    return 0


def _sync_request_file(req_id, status=None, title=None, detail=None, project=None):
    """요청 파일도 같은 값으로 맞춘다 (있을 때만) - `migrate` 가 파일에서 다시 적재해 DB 만 고치면 되돌아간다."""
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
        for k, v in (("status", status), ("title", title), ("detail", detail), ("project", project)):
            if v is not None:
                obj[k] = v
        _write_atomic(f, json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
        return True
    return False


from fleet_rt.base import PROJECT_NAME_RE  # noqa: E402 - 정의는 한 곳


class _NoChange(Exception):
    """`roundrec.update` 의 fn 이 쓰지 않고 빠져나갈 때."""


def note_round_request(req_id, n=None):
    """라운드 도중에 다루게 된 요청(과 그 프로젝트)을 도는 라운드의 `rounds/R<N>/round.json` 에 덧붙인다.

    도는 라운드나 기록 파일이 없거나 실패한 라운드면 아무것도 하지 않는다. 기록 보강은 덤이라 실패해도 부른 명령을 막지 않는다.
    """
    try:
        if not req_id:
            return False
        if n is None:
            import fleet  # noqa: PLC0415 - fleet 이 이 모듈을 지연 import 한다
            if pathlib.Path(fleet.ROOT) != pathlib.Path(ROOT):   # 다른 저장소(테스트의 임시 폴더)의 라운드를 건드리지 않는다
                return False
            n = fleet.current_round()
        if n is None:
            return False
        rdir = ROOT / "rounds" / f"R{int(n)}"
        if not (rdir / "round.json").is_file():
            return False
        project = ""
        qdir = ROOT / ".aimem" / "requests"
        for q in (sorted(qdir.glob("*.json")) if qdir.exists() else []):
            obj = _read_json_file(q)
            if obj and obj.get("id") == req_id:
                project = obj.get("project") if isinstance(obj.get("project"), str) else ""
                break

        def add(rec):
            if not rec or rec.get("state") == "failed":
                raise _NoChange
            reqs = rec.get("requests") if isinstance(rec.get("requests"), list) else []
            projs = rec.get("projects") if isinstance(rec.get("projects"), list) else []
            changed = False
            if req_id not in reqs:
                reqs.append(req_id); changed = True
            if project and re.match(PROJECT_NAME_RE, project) and project not in projs:
                projs = sorted(set(projs) | {project}); changed = True
            if not changed:
                raise _NoChange
            rec["requests"], rec["projects"] = reqs, projs
            return rec

        from fleet_rt import roundrec  # noqa: PLC0415 - round.json 은 엔진과 같은 잠금으로 쓴다
        roundrec.update(rdir, add)
        return True
    except Exception:  # noqa: BLE001 - _NoChange 포함. 기록 보강은 태스크·요청 쓰기를 막지 않는다
        return False


def cmd_request(a):
    project = getattr(a, "project", None)
    if project is not None:
        project = project.strip()
        if project and not re.match(PROJECT_NAME_RE, project):
            sys.exit("프로젝트 이름은 한글·영문·숫자·`-`·`_` 만, 40자 이하입니다 (공백·점·`/` 불가). 빈 문자열 = 함대 자체의 일")
    with connect() as con:
        now = _now()
        load_request_files(con, now)     # 웹 요청 폼은 파일만 만든다 - 읽기·쓰기 전에 DB 에 싣는다
        con.commit()
        if a.action == "set":
            if not a.id:
                sys.exit("request set 에는 --id 가 필요합니다")
            what = _upsert(con, "requests", "id", a.id,
                           {"title": a.title, "detail": a.detail, "requester": a.requester,
                            "status": a.status, "updated": now},
                           {"status": "NEW", "created": now})
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (now, a.actor, rev(con), "request", f"{a.id} {a.status or ''} {a.title or ''}".strip()))
            con.commit()
            synced = _sync_request_file(a.id, a.status, a.title, a.detail, project)
            if not synced and project:
                # 프로젝트는 요청 파일에 산다. 관리자가 CLI 로 만든 요청은 파일이 없으니 만들어 준다 (웹에도 보인다)
                row = con.execute("SELECT * FROM requests WHERE id=?", (a.id,)).fetchone()
                if not re.fullmatch(r"[A-Za-z0-9-]{1,40}", a.id):
                    sys.exit("--project 를 붙이려면 요청 id 가 영문·숫자·`-` 40자 이하여야 합니다 (파일 이름이 됩니다)")
                rdir = ROOT / ".aimem" / "requests"
                rdir.mkdir(parents=True, exist_ok=True)
                rec = {"id": a.id, "created": row["created"], "requester": row["requester"] or a.actor, "project": project,
                       "title": row["title"] or "", "detail": row["detail"] or "", "status": row["status"], "subtasks": []}
                (rdir / f"{a.id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                synced = True
            note_round_request(a.id)              # 관리자가 라운드 도중 만든 요청도 그 라운드 기록에
            print(f"request {a.id} {what}" + (" (요청 파일도 맞춤)" if synced else "") + (f" [프로젝트 {project}]" if project else ""))
        elif a.action == "list":
            # 프로젝트는 요청 파일(.aimem/requests/*.json)의 `project` - 결과물이 쌓일 `projects/<이름>/` (빈 값 = 함대 자체)
            proj = {}
            rdir = ROOT / ".aimem" / "requests"
            for f in (sorted(rdir.glob("*.json")) if rdir.exists() else []):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    proj[d.get("id")] = d.get("project") or ""
                except (OSError, ValueError, AttributeError):
                    continue
            for r in con.execute("SELECT id,status,requester,title FROM requests ORDER BY created"):
                pr = proj.get(r["id"]) or ""
                print(f"  {r['id']:<26} {r['status']:<12} {r['requester'] or '':<16} "
                      f"{('[' + pr + '] ') if pr else ''}{r['title'] or ''}")
    return 0


ARCHIVE_TERMINAL_NODE = ("done", "failed", "blocked")
ARCHIVE_REQUEST_CLOSED = ("DONE", "REJECTED")


_TOKEN_RE = re.compile(r"[0-9A-Za-z-]+")
_TOKEN_CACHE = {}


def _mentions(body, ident):
    """본문에 식별자가 **낱말로** 들어 있나 (앞뒤가 영숫자·`-` 가 아님).

    본문마다 식별자 꼴 낱말을 한 번만 뽑아 집합으로 본다. 예전에는 (본문 × 식별자) 마다 정규식을 새로 만들어
    기록이 쌓이자 정규식 캐시가 넘쳐 아카이브 계획 하나가 30초를 넘겼다 (2026-11-13 실측, 47만 번 컴파일).
    """
    ident = str(ident)
    if not _TOKEN_RE.fullmatch(ident):          # 영숫자·`-` 밖의 글자가 든 식별자는 옛 방식 그대로
        return re.search(r"(?<![0-9A-Za-z-])" + re.escape(ident) + r"(?![0-9A-Za-z-])", body or "") is not None
    key = body or ""
    toks = _TOKEN_CACHE.get(key)
    if toks is None:
        if len(_TOKEN_CACHE) > 20000:
            _TOKEN_CACHE.clear()
        toks = _TOKEN_CACHE[key] = frozenset(_TOKEN_RE.findall(key))
    return ident in toks


def _iso(v):
    """요청 파일의 `2026-11-09 17:01` 과 ISO `2026-11-09T17:01:55` 를 같은 자로 비교하기 위한 정규화."""
    return str(v or "").replace(" ", "T")


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def _monitor_log_held():
    """모니터 서버가 monitor.log 를 쥐고 있는지 본다. pid 경로를 못 찾으면 안전하게 쥔 것으로 본다."""
    paths = (ROOT / ".aimem" / "monitor.pid",
             ROOT / "tools" / "aimem_monitor" / "monitor.pid",
             ROOT / "tools" / "aimem_monitor" / "server.pid")
    found = False
    for path in paths:
        if not path.is_file():
            continue
        found = True
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if _pid_alive(pid):
            return True, "서버가 쥐고 있어 건너뜀"
    if not found:
        return True, "pid 파일 경로를 찾지 못해 건너뜀"
    return False, None


def archive_plan(days=14, now=None):
    """무엇을 내릴지 계산만 한다 (파일·DB 를 건드리지 않는다). 태스크·요청·그래프와 그 기록.

    기준 시각은 포함(`<=`)이라 `--days 0` 이 같은 초에 끝난 것도 내린다. 시각은 모두 초 단위 ISO 라 문자열 비교로 충분하다."""
    now = now or dt.datetime.now()
    cutoff = (now - dt.timedelta(days=days)).isoformat(timespec="seconds")
    plan = {"days": days, "cutoff": cutoff, "tasks": [], "requests": [], "graphs": [],
            "sessions": [], "events": [], "handoff": [], "relay": [], "logs": [], "total_records": 0}
    with connect() as con:
        for r in con.execute("SELECT id,title,slot,status,inherited,artifacts,updated FROM tasks "
                             "WHERE status='DONE' AND COALESCE(updated,created,'') <= ? ORDER BY id", (cutoff,)):
            plan["tasks"].append(dict(r))
        task_status = {r["id"]: r["status"] for r in con.execute("SELECT id,status FROM tasks")}
        request_ids = {r["id"] for r in con.execute("SELECT id FROM requests")}
        graph_ids = set()
        protected_ids = {r["id"] for r in con.execute(
            "SELECT id FROM requests WHERE upper(COALESCE(status,'')) NOT IN ('DONE','REJECTED')")}
        for r in con.execute("SELECT task FROM queue"):
            protected_ids.update(re.findall(r"\b(?:T-\d+|Q-\d{6}-[0-9a-f]{4}|G-\d+)\b", str(r["task"] or "")))
        for row in _handoff_rows(con)[HANDOFF_MAX:]:
            if _iso(row["at"]) <= cutoff:
                plan["handoff"].append({"seq": row["seq"], "at": row["at"], "line": _handoff_line(row)})
    rdir = ROOT / ".aimem" / "requests"
    open_request_ids = set()
    if rdir.is_dir():
        for f in sorted(rdir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            when = _iso(d.get("updated") or d.get("created"))
            rid = d.get("id") or f.stem
            request_ids.add(rid)
            status = str(d.get("status") or "").upper()
            if status not in ARCHIVE_REQUEST_CLOSED:
                open_request_ids.add(rid)
            if status in ARCHIVE_REQUEST_CLOSED and when <= cutoff:
                plan["requests"].append({"id": rid, "file": f.name, "status": d.get("status"), "title": d.get("title"), "when": when})
    gdir = ROOT / ".aimem" / "graph"
    open_graph_ids = set()
    if gdir.is_dir():
        for f in sorted(gdir.glob("*.json")):
            try:
                g = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            nodes = g.get("nodes") or []
            gid = g.get("id") or f.stem
            graph_ids.add(gid)
            archived = False
            if nodes and not all(str(n.get("status")) in ARCHIVE_TERMINAL_NODE for n in nodes):
                open_graph_ids.add(gid)
            elif nodes and all(str(n.get("status")) in ARCHIVE_TERMINAL_NODE for n in nodes):
                when = _iso(g.get("updated") or g.get("created"))
                if when <= cutoff:
                    side = sorted(x.name for x in gdir.glob(f"{gid}.*") if x.name != f.name) + sorted(x.name for x in gdir.glob(f"{gid}-*.task.md"))
                    inputs = sorted(x.name for x in (gdir / "inputs").glob(f"{gid}-*")) if (gdir / "inputs").is_dir() else []
                    for n in nodes:
                        for key in (n.get("id"), n.get("task")):
                            # `task` 는 지시 본문 전체일 수도 있어 파일 이름 꼴일 때만 찾는다
                            if not isinstance(key, str) or not _ARCHIVE_ID_RE.fullmatch(key):
                                continue
                            try:
                                if (gdir / "inputs" / f"{key}.md").exists() and f"{key}.md" not in inputs:
                                    inputs.append(f"{key}.md")
                            except OSError:
                                continue
                    plan["graphs"].append({"id": gid, "file": f.name, "request": g.get("request"), "when": when,
                                           "counts": {k: sum(1 for n in nodes if n.get("status") == k) for k in ARCHIVE_TERMINAL_NODE},
                                           "side_files": side, "inputs": inputs})
                    archived = True
            if not archived:
                protected_ids.add(gid)
                for n in nodes:
                    for key in (n.get("id"), n.get("task")):
                        # `task` 는 지시 본문 전체일 수도 있어 식별자 꼴일 때만 지킨다
                        if isinstance(key, str) and _ARCHIVE_ID_RE.fullmatch(key):
                            protected_ids.add(key)
                    for attempt in n.get("attempts") or []:
                        if isinstance(attempt, dict) and attempt.get("run_id"):
                            protected_ids.add(str(attempt["run_id"]))
                    if n.get("run_id"):
                        protected_ids.add(str(n["run_id"]))

    protected_ids = {i for i in protected_ids if isinstance(i, str) and _ARCHIVE_ID_RE.fullmatch(i)}
    plan["tasks"] = [r for r in plan["tasks"] if r["id"] not in protected_ids]
    archived_task_ids = {r["id"] for r in plan["tasks"]}
    # 세션 폴더. **end.json 이 없는 세션은 절대 안 옮긴다** (돌고 있거나 lost 판정 전이다)
    sess_dir = ROOT / ".aimem" / "sessions"
    for d in sorted(sess_dir.iterdir()) if sess_dir.is_dir() else []:
        if not d.is_dir() or not (d / "end.json").is_file() or not _ARCHIVE_ID_RE.fullmatch(d.name):
            continue
        meta = _read_json_file(d / "meta.json") or {}
        end = _read_json_file(d / "end.json") or {}
        task = meta.get("task_id")
        if d.name in protected_ids or (isinstance(task, str) and task in protected_ids):
            continue
        if isinstance(task, str) and task in task_status and task_status[task] != "DONE":
            continue
        started = _iso(meta.get("started") or meta.get("supervisor_started") or end.get("ended"))
        attached = isinstance(task, str) and task in archived_task_ids
        if not attached and (not isinstance(task, str) or task not in task_status):
            attached = bool(started) and started <= cutoff
        if attached:
            plan["sessions"].append({"id": d.name, "task": task, "when": started})

    archived_ids = set(archived_task_ids)
    archived_ids.update(r["id"] for r in plan["requests"])
    archived_ids.update(g["id"] for g in plan["graphs"])
    open_ids = {rid for rid, status in task_status.items() if status != "DONE"}
    open_ids.update(open_request_ids)
    open_ids.update(open_graph_ids)
    all_ids = set(task_status) | request_ids | graph_ids | archived_ids
    with connect() as con:
        for e in con.execute("SELECT seq,at,actor,rev,kind,body FROM events ORDER BY seq"):
            if e["kind"] == "handoff":
                continue
            body = e["body"] or ""
            if any(_mentions(body, ident) for ident in protected_ids):
                continue
            if any(_mentions(body, ident) for ident in open_ids):
                continue
            if any(_mentions(body, ident) for ident in archived_ids):
                plan["events"].append(dict(e))
                continue
            if not any(_mentions(body, ident) for ident in all_ids):
                if str(e["at"] or "") <= cutoff:
                    plan["events"].append(dict(e))

    remaining_graph_rounds = set()
    archived_graph_rounds = set()
    unknown_graph_round = False
    if gdir.is_dir():
        archived_graph_ids = {g["id"] for g in plan["graphs"]}
        for f in sorted(gdir.glob("*.json")):
            try:
                g = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if "round" not in g:
                if (g.get("id") or f.stem) not in archived_graph_ids:
                    unknown_graph_round = True
                continue
            try:
                int(g.get("round"))
            except (TypeError, ValueError):
                if (g.get("id") or f.stem) not in archived_graph_ids:
                    unknown_graph_round = True
                continue
            if (g.get("id") or f.stem) in archived_graph_ids:
                archived_graph_rounds.add(str(g.get("round")))
            else:
                remaining_graph_rounds.add(str(g.get("round")))
    relay_dir = ROOT / ".aimem" / "relay"
    if relay_dir.is_dir():
        rounds = set()
        for f in relay_dir.iterdir():
            m = re.fullmatch(r"r(\d+)\.json", f.name)
            if m:
                rounds.add(int(m.group(1)))
        if unknown_graph_round:
            rounds = set()
        max_round = max(rounds) if rounds else None
        for n in sorted(rounds):
            if n == max_round:
                continue
            if str(n) in remaining_graph_rounds:
                continue
            if str(n) not in archived_graph_rounds:
                # 그래프가 아직 생기지 않은 라운드의 전달 기록은 열린 것으로 본다.
                continue
            try:
                d = json.loads((relay_dir / f"r{n}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            at = _iso(d.get("at"))
            if at and at <= cutoff:
                files = sorted(x.name for x in relay_dir.iterdir()
                               if x.name.startswith(f"r{n}.") or x.name.startswith(f"r{n}-"))
                plan["relay"].append({"round": n, "files": files})

    for log_path in (ROOT / ".aimem" / "monitor.log", ROOT / ".aimem" / "fleet-mode.log"):
        if not log_path.is_file():
            continue
        if log_path.name == "monitor.log":
            held, reason = _monitor_log_held()
            if held:
                plan["logs"].append({"file": "monitor.log", "lines": 0, "skip": reason})
                continue
        try:
            text = log_path.read_text(encoding="utf-8")
        except OSError:
            continue
        moved = 0
        for line in text.splitlines():
            m = re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", line)
            if m and _iso(line[:19]) <= cutoff:
                moved += 1
        plan["logs"].append({"file": log_path.name, "lines": moved})

    plan["total_records"] = (len(plan["sessions"]) + len(plan["events"]) + len(plan["handoff"])
                             + len(plan["relay"]) + sum(x["lines"] for x in plan["logs"]))
    plan["total"] = len(plan["tasks"]) + len(plan["requests"]) + len(plan["graphs"])
    return plan


def archive_apply(plan, actor="관리자"):
    """계획대로 옮긴다. 태스크·이벤트는 아카이브에 먼저 쓰고 확인한 뒤 DB 에서 내린다; 요청·그래프·세션 폴더는 이동."""
    arch = ROOT / ".aimem" / "archive"
    arch.mkdir(parents=True, exist_ok=True)
    out = {"tasks": [], "requests": [], "graphs": [], "sessions": [], "events": [],
           "handoff": [], "relay": [], "log_lines": 0, "files": 0}
    moved_any = False
    cell = lambda v: str(v or "-").replace("|", "\\|").replace("\n", " ")
    rows = plan["tasks"]
    if rows:
        by_month = {}
        for r in rows:
            by_month.setdefault((r["updated"] or plan["cutoff"])[:7], []).append(r)
        for month, rs in sorted(by_month.items()):
            f = arch / f"board-{month}.md"
            if not f.exists():
                y, m = month.split("-")
                f.write_text(f"# 작업 보드 아카이브 - {int(y)}년 {int(m)}월\n\n"
                             "`DONE` 이 된 지 14일이 지나 내린 행입니다 (`aimem_db.py archive`, `8.0` 보관·폐기).\n\n"
                             "| ID    | 태스크 | 담당 슬롯 | 상태 | 이어받음 | 산출물 |\n"
                             "| ----- | ------ | --------- | ---- | -------- | ------ |\n", encoding="utf-8")
            old_lines = f.read_text(encoding="utf-8").splitlines()
            with f.open("a", encoding="utf-8") as fh:
                for r in rs:
                    marker = f"| {r['id']} |"
                    if any(line.startswith(marker) for line in old_lines):
                        continue
                    row = f"| {r['id']} | {cell(r['title'])} | {cell(r['slot'])} | DONE | {cell(r['inherited'])} | {cell(r['artifacts'])} |"
                    fh.write(row + "\n")
                    old_lines.append(row)
                    moved_any = True
            text = f.read_text(encoding="utf-8")
            lines = text.splitlines()
            missing = [r["id"] for r in rs if not any(line.startswith(f"| {r['id']} |") for line in lines)]
            if missing:
                raise RuntimeError(f"archive: {f.name} 에 {missing} 가 안 들어갔습니다 - DB 에서 내리지 않습니다")
        ids = [r["id"] for r in rows]
        with connect() as con:
            deleted = [r["id"] for r in con.execute(
                f"SELECT id FROM tasks WHERE id IN ({','.join('?' * len(ids))}) AND status='DONE'", ids)]
            con.execute(f"DELETE FROM tasks WHERE id IN ({','.join('?' * len(ids))}) AND status='DONE'", ids)
            con.commit()
        out["tasks"] = deleted
        if deleted:
            moved_any = True
        if len(deleted) != len(ids):
            print(f"archive: 태스크 계획 {len(ids)}건, 실제 삭제 {len(deleted)}건")
    rdir, gdir = ROOT / ".aimem" / "requests", ROOT / ".aimem" / "graph"
    for r in plan["requests"]:
        src = rdir / r["file"]
        if not src.exists():
            continue
        dest = arch / f"requests-{r['when'][:7] or 'undated'}"
        dest.mkdir(exist_ok=True)
        src.replace(dest / src.name)
        out["requests"].append(r["id"]); out["files"] += 1
        moved_any = True
    for g in plan["graphs"]:
        dest = arch / f"graph-{g['when'][:7] or 'undated'}"
        (dest / "inputs").mkdir(parents=True, exist_ok=True)
        for name in [g["file"]] + g["side_files"]:
            src = gdir / name
            if src.exists():
                src.replace(dest / name); out["files"] += 1; moved_any = True
        for name in g["inputs"]:
            src = gdir / "inputs" / name
            if src.exists():
                src.replace(dest / "inputs" / name); out["files"] += 1; moved_any = True
        out["graphs"].append(g["id"])

    sess_dir = ROOT / ".aimem" / "sessions"
    for r in plan.get("sessions", []):
        src = sess_dir / r["id"]
        # 계획 뒤에 되살아났거나 end.json 이 없는 폴더는 옮기지 않는다
        if not (src / "end.json").is_file():
            continue
        dest = arch / f"sessions-{(r.get('when') or plan['cutoff'])[:7] or 'undated'}"
        dest.mkdir(parents=True, exist_ok=True)
        src.replace(dest / r["id"])
        out["files"] += 1
        moved_any = True
        out["sessions"].append(r["id"])
        with connect() as con:
            con.execute("DELETE FROM sessions WHERE id=?", (r["id"],))
            con.commit()

    if plan.get("handoff"):
        confirmed = []
        for h in plan["handoff"]:
            line = h["line"]
            month = line[3:10] if line.startswith("- `") and len(line) >= 10 else str(h.get("at") or plan["cutoff"])[:7]
            f = arch / f"handoff-{month}.md"
            try:
                if not f.exists():
                    f.write_text(f"# Handoff log archive - {month}\n\n", encoding="utf-8")
                old = f.read_text(encoding="utf-8")
                if line not in old.splitlines():
                    with f.open("a", encoding="utf-8") as fh:
                        fh.write(line.rstrip("\n") + "\n")
                    moved_any = True
                text = f.read_text(encoding="utf-8")
            except OSError as e:
                print(f"archive: 핸드오프 #{h['seq']} 아카이브 실패 - 건너뜀 ({e})")
                continue
            if line in text.splitlines():
                confirmed.append(h["seq"])
        if confirmed:
            with _write_txn() as con:
                con.execute(f"DELETE FROM events WHERE seq IN ({','.join('?' * len(confirmed))})", confirmed)
                _sync_handoff_files(con)
            out["handoff"] = confirmed
            moved_any = True

    event_months = {}
    for e in plan.get("events", []):
        month = str(e.get("at") or plan["cutoff"])[:7] or "undated"
        event_months.setdefault(month, []).append(e)
    for month, events in sorted(event_months.items()):
        f = arch / f"events-{month}.jsonl"
        existing = []
        if f.exists():
            try:
                for ln in f.read_text(encoding="utf-8").splitlines():
                    if not ln.strip():
                        continue
                    d = json.loads(ln)
                    existing.append((d.get("seq"), d.get("at")))
            except (OSError, ValueError) as e:
                raise RuntimeError(f"archive: {f.name} 를 읽지 못했습니다 - DB 에서 내리지 않습니다 ({e})")
        with f.open("a", encoding="utf-8") as fh:
            for e in events:
                marker = (e.get("seq"), e.get("at"))
                if marker in existing:
                    continue
                row = {"seq": e.get("seq"), "at": e.get("at"), "actor": e.get("actor"),
                       "rev": e.get("rev"), "kind": e.get("kind"), "body": e.get("body")}
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                existing.append(marker)
                moved_any = True
        seen = set()
        try:
            for ln in f.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                d = json.loads(ln)
                seen.add((d.get("seq"), d.get("at")))
        except (OSError, ValueError) as e:
            raise RuntimeError(f"archive: {f.name} 를 확인하지 못했습니다 - DB 에서 내리지 않습니다 ({e})")
        missing = [e["seq"] for e in events if (e.get("seq"), e.get("at")) not in seen]
        if missing:
            raise RuntimeError(f"archive: {f.name} 에 {missing} 가 안 들어갔습니다 - DB 에서 내리지 않습니다")
    if plan.get("events"):
        seqs = [e["seq"] for e in plan["events"]]
        deleted = []
        with connect() as con:
            for e in plan["events"]:
                cur = con.execute("DELETE FROM events WHERE seq=? AND kind=?", (e["seq"], e.get("kind")))
                if cur.rowcount:
                    deleted.append(e["seq"])
            con.commit()
            if deleted:
                moved_any = True
        out["events"] = deleted
        if len(deleted) != len(seqs):
            print(f"archive: 이벤트 계획 {len(seqs)}건, 실제 삭제 {len(deleted)}건")

    relay_dir = ROOT / ".aimem" / "relay"
    for r in plan.get("relay", []):
        n = r["round"]
        month = plan["cutoff"][:7]
        try:
            d = json.loads((relay_dir / f"r{n}.json").read_text(encoding="utf-8"))
            at = _iso(d.get("at"))
            if at:
                month = at[:7]
        except (OSError, ValueError):
            pass
        dest = arch / f"relay-{month or 'undated'}"
        dest.mkdir(parents=True, exist_ok=True)
        for name in r.get("files", []):
            src = relay_dir / name
            if src.is_file():
                src.replace(dest / name)
                out["files"] += 1
                moved_any = True
        out["relay"].append(n)

    log_total = 0
    for log_path in (ROOT / ".aimem" / "monitor.log", ROOT / ".aimem" / "fleet-mode.log"):
        if not log_path.is_file():
            continue
        if log_path.name == "monitor.log":
            held, reason = _monitor_log_held()
            if held:
                continue
        try:
            f = log_path.open("r+", encoding="utf-8")
        except OSError:
            continue
        with f:
            try:
                text = f.read()
                end = f.tell()
            except OSError:
                continue
            kept, by_month = [], {}
            for line in text.splitlines(keepends=True):
                m = re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", line)
                if m and _iso(line[:19]) <= plan["cutoff"]:
                    by_month.setdefault(line[:7], []).append(line)
                else:
                    kept.append(line)
            if not by_month:
                continue
            for month, lines in sorted(by_month.items()):
                dest = arch / f"logs-{month}" / log_path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    chunk = "".join(line if line.endswith("\n") else line + "\n" for line in lines)
                    old_text = dest.read_text(encoding="utf-8") if dest.exists() else ""
                    before = len(old_text.splitlines())
                    if not old_text.endswith(chunk):
                        with dest.open("a", encoding="utf-8") as fh:
                            fh.write(chunk)
                        after = len(dest.read_text(encoding="utf-8").splitlines())
                    else:
                        after = before
                except OSError as e:
                    raise RuntimeError(f"archive: {dest} 에 로그를 쓰지 못했습니다 - 원본을 남깁니다 ({e})")
                if after <= before and not old_text.endswith(chunk):
                    raise RuntimeError(f"archive: {dest} 줄 수가 늘지 않았습니다 - 원본을 남깁니다")
                log_total += len(lines)
            try:
                f.seek(0, 2)
                if f.tell() != end:
                    f.seek(end)
                    kept.append(f.read())
                f.seek(0)
                f.write("".join(kept))
                f.truncate()
                f.flush()
                os.fsync(f.fileno())
                moved_any = True
            except OSError as e:
                raise RuntimeError(f"archive: {log_path} 를 같은 inode 에서 다시 쓰지 못했습니다 ({e})")
            out["files"] += 1
    out["log_lines"] = log_total

    changed = any(out[k] for k in ("tasks", "requests", "graphs", "sessions", "events", "handoff", "relay", "log_lines"))
    if changed:
        with connect() as con:
            body = (f"{plan['days']}일 경과 - 태스크 {len(out['tasks'])}건, 요청 {len(out['requests'])}건, 그래프 {len(out['graphs'])}개 아카이브"
                    + (f" (태스크 {', '.join(out['tasks'])})" if out["tasks"] else "")
                    + f", 세션 {len(out['sessions'])}건, 이벤트 {len(out['events'])}건"
                    + f", 핸드오프 {len(out['handoff'])}건, 전달 {len(out['relay'])}개, 로그 {out['log_lines']}줄")
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                        (_now(), actor, rev(con), "archive", body))
            con.commit()
        try:
            vcon = sqlite3.connect(DB, timeout=10)
            vcon.isolation_level = None
            try:
                vcon.execute("VACUUM")
            except sqlite3.Error as e:
                print(f"archive: VACUUM 실패 - 정리는 성공 ({e})")
            finally:
                vcon.close()
        except sqlite3.Error as e:
            print(f"archive: VACUUM 실패 - 정리는 성공 ({e})")
    if moved_any or changed:
        try:
            render(sync_aimem=False)
        except Exception as e:
            out["render_error"] = f"{type(e).__name__}: {e}"
    return out


def cmd_archive(a):
    """`8.0` 끝난 작업의 보관: `--days`(기본 14)일 지난 끝난 것을 `.aimem/archive/` 로. `--dry-run` 은 보여 주기만. 웹 '끝난 것 정리' 와 같은 함수."""
    plan = archive_plan(a.days)
    if not plan["total"] and not plan["total_records"]:
        print(f"archive: {a.days}일 지난 끝난 것 없음 (기준 {plan['cutoff']})")
        return 0
    if plan["tasks"]:
        print("archive: 태스크 <- " + ", ".join(r["id"] for r in plan["tasks"]))
    if plan["requests"]:
        print("archive: 요청 <- " + ", ".join(r["id"] for r in plan["requests"]))
    for g in plan["graphs"]:
        print(f"archive: 그래프 <- {g['id']} (+파일 {len(g['side_files']) + len(g['inputs'])})")
    if plan["sessions"]:
        print(f"archive: 세션 <- {len(plan['sessions'])}건")
    if plan["events"]:
        print(f"archive: 이벤트 <- {len(plan['events'])}건")
    if plan["handoff"]:
        print(f"archive: 핸드오프 <- {len(plan['handoff'])}건")
    if plan["relay"]:
        print("archive: 전달 <- " + ", ".join(f"R{r['round']}" for r in plan["relay"]))
    for log in plan["logs"]:
        print(f"archive: 로그 <- {log['file']} {log['lines']}줄")
    print(f"archive: 건수 - 핸드오프 {len(plan['handoff'])}건, 전달 {len(plan['relay'])}개, 로그 {sum(x['lines'] for x in plan['logs'])}줄")
    if a.dry_run:
        return 0
    try:
        out = archive_apply(plan, a.actor)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"archive: 태스크 {len(out['tasks'])}건, 요청 {len(out['requests'])}건, 그래프 {len(out['graphs'])}개, 세션 {len(out['sessions'])}건, 이벤트 {len(out['events'])}건, 핸드오프 {len(out['handoff'])}건, 전달 {len(out['relay'])}개, 로그 {out['log_lines']}줄 옮김 (파일 {out['files']})")
    if out.get("render_error"):
        print(f"archive: render 실패 - 생성물 갱신 안 됨 ({out['render_error']})")
    return 0


def ownership_set(path, owner, note=None, actor="관리자", db=None):
    """소유권 한 행을 쓰고 events 에 `ownership` 한 줄. `db` 를 주면 그 DB 파일에(그래프 실행기가 실행 기록 옆 DB 에 쓴다)."""
    con = sqlite3.connect(db, timeout=10) if db else connect()
    con.row_factory = sqlite3.Row
    try:
        with con:
            con.execute("""INSERT INTO ownership(path_pattern,owner,note) VALUES(?,?,?)
                ON CONFLICT(path_pattern) DO UPDATE SET owner=excluded.owner, note=COALESCE(excluded.note,ownership.note)""", (path, owner, note))
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (_now(), actor, rev(con), "ownership", f"{path} -> {owner}"))
    finally:
        con.close()


def cmd_ownership(a):
    if a.action == "set":
        ownership_set(a.path, a.owner, a.note, a.actor)
        print(f"ownership {a.path} -> {a.owner}")
        return 0
    with connect() as con:
        if a.action == "list":
            for r in con.execute("SELECT path_pattern,owner,note FROM ownership ORDER BY owner,path_pattern"):
                print(f"  {r['owner']:<10} {r['path_pattern']:<40} {r['note'] or ''}")
    return 0


#: 검수 보고서의 발견 번호 - 영문 대문자 1~2자 + 숫자 (N=결함, M=변이 시험, D=넘어온 결함, 그 밖에 검수자마다
#: P·A·S·G·C·B 같은 글자도 쓴다). **보고서마다 1부터 다시 센다** - R15 의 N5 와 R17 의 N5 는 다른 문제다.
#: 큐는 라운드를 넘어 남으므로 큐에 적을 때는 `R17-N5` 처럼 라운드를 붙인다. 같은 라운드 것을 이어 적을 때는
#: `R17-N5·N6` 처럼 첫 번호에만 붙여도 된다 (2026-11-12 태석님 지시, 같은 날 글자 제한을 없앰).
#: 예외: `R17` 자체(라운드), `S1`~`S9`(슬롯 이름).
_FINDING_QUALIFIED = re.compile(r"(?<![0-9A-Za-z])R\d+-[A-Z]{1,2}\d+(?:\s*[·,/]\s*[A-Z]{1,2}\d+)*(?![0-9A-Za-z])")
_FINDING_BARE = re.compile(r"(?<![0-9A-Za-z_-])[A-Z]{1,2}\d{1,3}(?![0-9A-Za-z])")
_FINDING_NOT_ID = re.compile(r"R\d+|S\d")


def bare_finding_ids(text):
    """라운드가 안 붙은 발견 번호 목록 (`N5`, `M13` …). 비어 있으면 통과."""
    rest = _FINDING_QUALIFIED.sub(" ", str(text or ""))
    return [x for x in _FINDING_BARE.findall(rest) if not _FINDING_NOT_ID.fullmatch(x)]


def _check_queue_text(*texts):
    bare = sorted({x for t in texts for x in bare_finding_ids(t)},
                  key=lambda x: (x.rstrip("0123456789"), int(x[len(x.rstrip("0123456789")):])))
    if bare:
        sys.exit("큐에 적는 검수 발견 번호에는 라운드를 붙이십시오: " + ", ".join(bare) +
                 " → 예) R17-N5, R17-N5·N6, R19-P2 (번호는 검수 보고서마다 1부터 다시 셉니다. 앞의 R숫자가 라운드)")


def cmd_queue(a):
    """`4.5` 대기 큐 - 유일한 큐 편집 경로. `pos` 는 1부터 연속이라 `drop` 뒤에 다시 매긴다("맨 위"가 모호해지지 않게)."""
    with connect() as con:
        # 읽고-쓰는 명령은 `BEGIN IMMEDIATE` 로 시작합니다. 기본 암묵 BEGIN 은
        # DML 에서야 열려서 앞선 `SELECT` 가 트랜잭션 밖이었고, 동시 `add` 둘이
        # 같은 `pos` 를 받아 둘째가 `IntegrityError` 로 죽었습니다 (S4 검수 9번).
        if a.action in ("add", "edit"):
            _check_queue_text(a.task, a.note)
        if a.action in ("add", "drop", "edit"):
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
        elif a.action == "edit":
            # 제자리 고치기 - drop 뒤 add 로 고치면 맨 뒤로 가서 순서가 바뀐다
            row = con.execute("SELECT task FROM queue WHERE pos=?", (a.pos,)).fetchone()
            if not row:
                print(f"큐에 {a.pos} 번이 없습니다")
                return 1
            fields = {k: v for k, v in (("task", a.task), ("slot_hint", a.slot_hint), ("inherited", a.inherited),
                                        ("note", a.note)) if v is not None}
            con.execute(f"UPDATE queue SET {', '.join(k + '=?' for k in fields)} WHERE pos=?", (*fields.values(), a.pos))
            body = f"queue ~{a.pos} {a.task or row['task']}"
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
SLOT_RE = re.compile(r"S\d{1,3}\Z")
#: 웹에서 사람이 추가한 슬롯의 역할 표식 - **역할·비고는 라운드 관리자가 정한다**(8.0-1, 태석님 2026-11-10).
#: 관리자는 라운드 시작 때 events(kind=slot)와 이 표식을 보고 `slot set --role/--note` 로 채운다.
SLOT_ROLE_UNASSIGNED = "(미배정 - 관리자가 다음 라운드에 정함)"


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


def _rt(name):
    """`fleet_rt` 의 모듈 (설정 등) - 쓸 때만 불러온다."""
    import importlib  # noqa: PLC0415
    return importlib.import_module(f"fleet_rt.{name}")


def _slot_cfg():
    """`ROOT/fleet.toml`. 못 읽으면 ValueError - 모델을 확인할 수 없으면 슬롯을 바꾸지 않는다."""
    config = _rt("config")
    try:
        return config.load(ROOT)
    except config.ConfigError as e:
        raise ValueError(f"fleet.toml 을 읽지 못해 모델을 확인할 수 없습니다: {e}") from None


def _check_model(cfg, harness, model):
    ok, why = cfg.model_allowed(harness, model)
    if not ok:
        raise ValueError(why)


#: 관리자 세션 id 의 라운드 (`M-R<N>-HHMMSS…`, `fleet_rt.manager.manager_id`)
_MANAGER_SID_RE = re.compile(r"M-R(\d+)-")


def manager_caller():
    """지금 부르는 이가 라운드 관리자 세션이면 `{"round": N 또는 None, "policy": 키}`, 아니면 None(사람·웹 - 전권).

    감독이 모든 세션에 `AIFLEET_ROLE`·`AIFLEET_SESSION` 을 넣는다(`fleet_rt.base`). 운영 방식은 그 라운드 기록
    `rounds/R<N>/round.json` 의 `policy`, 모르면 `cost`(가장 좁은 쪽).
    """
    base = _rt("base")
    if os.environ.get(base.ENV_ROLE) != "manager":
        return None
    m = _MANAGER_SID_RE.match(os.environ.get(base.ENV_SESSION, ""))
    n = int(m.group(1)) if m else None
    key = "cost"
    if n is not None:
        try:
            rec = json.loads((ROOT / "rounds" / f"R{n}" / "round.json").read_text(encoding="utf-8"))
            v = rec.get("policy") if isinstance(rec, dict) else None
            key = v if v in _rt("config").POLICIES else "cost"
        except (OSError, ValueError):
            pass
    return {"round": n, "policy": key}


def _slot_provider(cfg, row):
    return cfg.provider_of(row["harness"], row["model"] or None)


def _manager_slot_room(con, cfg, mgr, harness, model, exclude=None):
    """관리자가 (harness, model) 슬롯을 하나 더 두거나 그쪽으로 바꿔도 되나. 안 되면 ValueError (까닭 한 줄)."""
    config = _rt("config")
    key = mgr["policy"]
    lim = cfg.policy(key)
    tier = cfg.slot_tier(harness, model)
    prov = cfg.provider_of(harness, model)
    if tier not in lim["slot_tiers"]:
        allowed = "·".join(config.TIER_LABEL[x] for x in lim["slot_tiers"]) or "(없음)"
        raise ValueError(f"운영 방식 {key} 에서 관리자는 {allowed} 슬롯만 둘 수 있습니다 - "
                         f"{harness} {model or '(하네스 기본)'} 은(는) {config.TIER_LABEL.get(tier, tier)}입니다 (공급자 {prov or '모름'})")
    if prov:
        same = [r["slot"] for r in con.execute("SELECT * FROM slots") if r["slot"] != exclude and _slot_provider(cfg, r) == prov]
        cap = cfg.max_concurrent(prov)
        if len(same) >= cap:
            raise ValueError(f"공급자 {prov} 는 동시에 {cap}개까지라 슬롯을 더해도 빨라지지 않습니다 "
                             f"(이미 {', '.join(same)}) - 다른 공급자의 모델을 고르십시오")


def _slot_running(slot):
    """그 슬롯으로 지금 도는 작업자 세션 id, 없으면 None. 세션 폴더는 DB 옆(`<.aimem>/sessions`)."""
    sroot = DB.parent / "sessions"
    try:
        names = os.listdir(sroot)
    except OSError:
        return None
    sessions = _rt_sessions
    live = sessions.live_index(sroot)
    for sid in names:
        d = sroot / sid
        if sid not in live and (d / "end.json").exists():
            continue
        meta = sessions.load_meta(d) or {}
        if meta.get("role") == "manager" or meta.get("slot") != slot:
            continue
        if sessions.state(d, live=live).get("state") == "running":
            return sid
    return None


def slot_add(slot=None, harness=None, model=None, role="", note="", actor="관리자"):
    """슬롯 추가. slot 을 생략하면 다음 번호. 돌려주는 값은 새 행(dict).

    (하네스, 모델)은 누가 부르든 `fleet.toml` 이 허용한 짝이어야 한다. 라운드 관리자 세션이 부르면(`manager_caller`)
    그 라운드 운영 방식의 한도 안에서만 - 관리자가 더한 슬롯 수 < `extra_slots`, 등급이 `slot_tiers` 안, 공급자에
    작업자 자리가 남음 - 더하고 `origin='manager'`·`round` 를 적는다. 사람(웹·CLI)은 한도 없이 `origin='owner'`.
    """
    import secrets
    if not harness:
        raise ValueError("하네스가 필요합니다")
    _check_slot_args(slot, harness, model)
    cfg = _slot_cfg()
    _check_model(cfg, harness, model)
    mgr = manager_caller()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")      # 세기와 더하기 사이에 다른 관리자가 끼지 않게
        slot = slot or next_slot_id()
        if con.execute("SELECT 1 FROM slots WHERE slot=?", (slot,)).fetchone():
            raise ValueError(f"{slot} 은 이미 있습니다")
        if mgr is not None:
            cap = cfg.policy(mgr["policy"])["extra_slots"]
            mine = [r["slot"] for r in con.execute("SELECT slot FROM slots WHERE origin='manager' ORDER BY slot")]
            if len(mine) >= cap:
                raise ValueError(f"운영 방식 {mgr['policy']} 에서 관리자가 더할 수 있는 슬롯은 {cap}개이고 이미 {len(mine)}개를 더했습니다"
                                 + (f" ({', '.join(mine)})" if mine else "") + " - 더 필요하면 사람에게 요청하십시오")
            _manager_slot_room(con, cfg, mgr, harness, model)
        token = secrets.token_hex(3)
        con.execute("INSERT INTO slots(slot,token,harness,model,role,note,updated,origin,round) VALUES(?,?,?,?,?,?,?,?,?)",
                    (slot, token, harness, model or None, role or "", note or "", _now(),
                     "manager" if mgr is not None else "owner", mgr["round"] if mgr is not None else None))
        _slot_event(con, actor, f"slot add {slot} {harness} 모델 {model or '(하네스 기본)'}" + (f" - {role}" if role else "")
                    + (f" (관리자 추가 R{mgr['round']}, 운영 {mgr['policy']})" if mgr is not None else ""))
        con.commit()
        return dict(con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone())


def slot_set(slot, harness=None, model=None, role=None, note=None, actor="관리자", clear_model=False):
    """슬롯 변경 - 준 값만 바꾼다. `clear_model=True` 면 모델을 하네스 기본으로 되돌린다.

    관리자 세션은 어느 슬롯이든 역할·비고를 정하지만, 하네스·모델은 **자기가 더한 슬롯**(`origin='manager'`)만 -
    사람이 둔 엔진은 사람의 결정이다. 바꾸는 짝도 운영 방식의 등급·공급자 자리 안이어야 한다.
    """
    _check_slot_args(slot, harness, model)
    mgr = manager_caller()
    with connect() as con:
        cur = con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone()
        if not cur:
            raise ValueError(f"{slot} 이 명부에 없습니다")
        engine = bool(harness and harness != cur["harness"]) or clear_model or (model is not None and model != cur["model"])
        if engine:
            new_h = harness or cur["harness"]
            new_m = None if clear_model else (model if model is not None else cur["model"])
            cfg = _slot_cfg()
            if model is not None or harness:
                _check_model(cfg, new_h, None if clear_model else new_m)
            if mgr is not None:
                if (cur["origin"] if "origin" in cur.keys() else "owner") != "manager":
                    raise ValueError(f"{slot} 은(는) 사람이 둔 슬롯이라 관리자는 하네스·모델을 바꾸지 않습니다 - "
                                     "역할·비고만 정하고(`slot set --role/--note`), 다른 엔진이 필요하면 `slot add` 로 더하십시오")
                if cfg.provider_of(new_h, new_m) != _slot_provider(cfg, cur) or cfg.slot_tier(new_h, new_m) != cfg.slot_tier(cur["harness"], cur["model"]):
                    _manager_slot_room(con, cfg, mgr, new_h, new_m, exclude=slot)
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
            con.commit()
        return dict(con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone()), changes


def slot_open_tasks(slot):
    with connect() as con:
        return [r["id"] for r in con.execute("SELECT id FROM tasks WHERE slot=? AND status NOT IN ('DONE') ORDER BY id", (slot,))]


def slot_remove(slot, actor="관리자", force=False):
    """슬롯 삭제. 작업자가 돌고 있으면 거절, 끝나지 않은 태스크가 배정돼 있으면 `force` 없이는 거절. 소유권 행은 같이 내린다.
    관리자 세션은 자기가 더한 슬롯(`origin='manager'`)만 지운다."""
    _check_slot_args(slot, None, None)
    mgr = manager_caller()
    with connect() as con:
        cur = con.execute("SELECT * FROM slots WHERE slot=?", (slot,)).fetchone()
        if not cur:
            raise ValueError(f"{slot} 이 명부에 없습니다")
        if mgr is not None and (cur["origin"] if "origin" in cur.keys() else "owner") != "manager":
            raise ValueError(f"{slot} 은(는) 사람이 둔 슬롯이라 관리자는 지우지 않습니다 - 관리자는 자기가 더한 슬롯만 지웁니다")
        running = _slot_running(slot)
        if running:
            raise ValueError(f"{slot} 에 작업자가 돌고 있습니다 ({running}) - 끝난 뒤 삭제하십시오")
        open_tasks = [r["id"] for r in con.execute("SELECT id FROM tasks WHERE slot=? AND status NOT IN ('DONE')", (slot,))]
        if open_tasks and not force:
            raise ValueError(f"{slot} 에 끝나지 않은 태스크가 있습니다: {', '.join(open_tasks)} (force 로 강제)")
        n_own = con.execute("DELETE FROM ownership WHERE owner=?", (slot,)).rowcount
        con.execute("DELETE FROM slots WHERE slot=?", (slot,))
        _slot_event(con, actor, f"slot remove {slot} ({cur['harness']}, 모델 {cur['model'] or '-'}, 소유권 {n_own}행 내림" + (f", 미완 태스크 {len(open_tasks)}건 강제" if open_tasks else "") + ")")
        con.commit()
        return {"slot": slot, "ownership_removed": n_own, "open_tasks": open_tasks}


def slot_origin_label(r):
    """`slot list`·모니터의 작은 표식 - 관리자가 더한 슬롯만 `관리자 추가 R<N>`."""
    if (r.get("origin") if isinstance(r, dict) else None) != "manager":
        return ""
    return "관리자 추가" + (f" R{r['round']}" if r.get("round") is not None else "")


def cmd_slot(a):
    if a.action == "list":
        for r in slot_list():
            mark = slot_origin_label(r)
            print(f"  {r['slot']}  {r['token']}  {r['harness']:<9} 모델 {r['model'] or '(하네스 기본)'}  {r['role'] or ''}"
                  + (f"  [{mark}]" if mark else ""))
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
    t.add_argument("--title"); t.add_argument("--slot"); t.add_argument("--status", choices=TASK_STATUSES)
    t.add_argument("--artifacts"); t.add_argument("--actor", default="관리자")
    q = sub.add_parser("request"); q.add_argument("action", choices=["set", "list"]); q.add_argument("--id"); q.add_argument("--title")
    q.add_argument("--detail"); q.add_argument("--requester"); q.add_argument("--status", choices=REQUEST_STATUSES); q.add_argument("--actor", default="관리자")
    q.add_argument("--project", help="결과물이 쌓일 프로젝트 `projects/<이름>/` (빈 문자열 = 함대 자체의 일). 요청 파일에 적힌다")
    o = sub.add_parser("ownership"); o.add_argument("action", choices=["set", "list"]); o.add_argument("--path"); o.add_argument("--owner"); o.add_argument("--note"); o.add_argument("--actor", default="관리자")
    sl = sub.add_parser("slot", help="슬롯 추가/변경/삭제/목록 - DB 정본 (웹 함대 현황에서도 됨)")
    sl.add_argument("action", choices=["add", "set", "remove", "list"]); sl.add_argument("--slot"); sl.add_argument("--harness", choices=HARNESSES)
    sl.add_argument("--model", help="`fleet.toml` 의 공급자/모델 (예 kisti/kistillm, openrouter/deepseek/deepseek-v4.1-flash) 또는 claude 별칭(opus/sonnet/haiku)")
    sl.add_argument("--default-model", action="store_true", help="set: 모델을 하네스 기본으로 되돌린다"); sl.add_argument("--role"); sl.add_argument("--note")
    sl.add_argument("--force", action="store_true", help="remove: 미완 태스크가 있어도 삭제"); sl.add_argument("--actor", default="관리자")
    r = sub.add_parser("archive", help="N일 지난 끝난 태스크·요청·그래프와 딸린 세션·이벤트·핸드오프·전달·로그를 .aimem/archive/ 로 옮긴다 (8.0)")
    r.add_argument("--days", type=int, default=14); r.add_argument("--dry-run", action="store_true"); r.add_argument("--actor", default="관리자")
    h = sub.add_parser("handoff", help="핸드오프 로그 - 정본은 DB events, .aimem/handoff.md 는 생성물 (AIMEM.md 4절)")
    h.add_argument("action", choices=["add", "list", "sync"]); h.add_argument("--body"); h.add_argument("--actor", default="관리자")
    h.add_argument("--bump", action="store_true", help="add: REV 를 하나 올린다"); h.add_argument("--allow-long", dest="allow_long", action="store_true", help=f"add: {HANDOFF_ENTRY_MAX}자 상한을 넘긴다")
    h.add_argument("--expect-rev", dest="expect_rev", type=int, help="add: 지금 REV 가 이 값이 아니면 쓰지 않고 거절")
    h.add_argument("--last", type=int, help=f"list: 최신 N건 (기본 {HANDOFF_MAX})"); h.add_argument("--all", action="store_true", help="list: 전부")
    u = sub.add_parser("queue", help="4.5 대기 큐 (관리자만 씁니다)")
    u.add_argument("action", choices=["list", "add", "edit", "drop"])
    u.add_argument("--task"); u.add_argument("--slot-hint", dest="slot_hint"); u.add_argument("--inherited")
    u.add_argument("--note"); u.add_argument("--pos", type=int); u.add_argument("--verbose", action="store_true")
    u.add_argument("--actor", default="관리자")
    a = p.parse_args()
    if a.cmd == "queue":
        if a.action == "add" and not a.task:
            p.error("queue add 에는 --task 가 필요합니다")
        if a.action in ("drop", "edit") and a.pos is None:
            p.error(f"queue {a.action} 에는 --pos 가 필요합니다")
        if a.action == "edit" and not any((a.task, a.slot_hint, a.inherited, a.note)):
            p.error("queue edit 에는 고칠 칸(--task/--slot-hint/--inherited/--note)이 하나는 필요합니다")
    return {"init": cmd_init, "migrate": lambda a: migrate(), "render": lambda a: render(), "state": cmd_state,
            "check": cmd_check, "event": cmd_event, "task": cmd_task, "request": cmd_request,
            "ownership": cmd_ownership, "queue": cmd_queue, "archive": cmd_archive, "slot": cmd_slot,
            "handoff": cmd_handoff}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
