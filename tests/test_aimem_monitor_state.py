"""reader.collect() 가 `.aimem/aimem.db` 를 정본으로 읽는다는 계약 (T-073 2단계).

표준 라이브러리 unittest 만 쓴다. DB 경로는 `aimem_db.DB` 모듈 전역이므로
임시 저장소를 만들고 `aimem_db.DB` 를 patch 로 갈아끼운다.
"""
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import aimem_db  # noqa: E402
from aimem_monitor import reader  # noqa: E402

TABLE_AIMEM = """\
# AIMEM

- **REV: 7** (개정 번호)
- 최종 갱신: 2026-11-09

## 1. 목표

- **목표:** 시험 목표
- **상태:** 진행

## 2. 명부

| 슬롯 | 토큰 | 하네스 | 역할 | 모델 | 비고 |
|---|---|---|---|---|---|
| SMD | `abc123` | claude | 마크다운역할 | - | 마크다운비고 |

## 3. 작업 보드

| ID | 작업 | 슬롯 | 상태 | 핸드오프 | 산출물 |
|---|---|---|---|---|---|
| T-MD | 마크다운작업 | SMD | DONE | - | md.txt |

## 4. 핸드오프 로그

- `2026-01-01 00:00` 마크다운로그 본문

## 4.5 대기 큐

| 순서 | 작업 | 슬롯 | 핸드오프 | 비고 |
|---|---|---|---|---|
| 1 | 마크다운큐 | SMD | - | md비고 |

## 6. 파일 소유권

| 경로 | 소유 |
|---|---|
| `x` | SMD |
"""

NO_TABLE_AIMEM = """\
# AIMEM

- **REV: 7** (개정 번호)
- 최종 갱신: 2026-11-09

## 1. 목표

- **목표:** 시험 목표
- **상태:** 진행

## 2. 명부

(DB 로 이관 - `.aimem/aimem.db`)

## 3. 작업 보드

(DB 로 이관)

## 4. 핸드오프 로그

(DB 로 이관)

## 4.5 대기 큐

(DB 로 이관)

## 6. 파일 소유권

(DB 로 이관)
"""


class _Base(unittest.TestCase):
    aimem_text = NO_TABLE_AIMEM

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / ".aimem").mkdir()
        (self.root / "AIMEM.md").write_text(self.aimem_text, encoding="utf-8")
        self.db = self.root / ".aimem" / "aimem.db"
        p = mock.patch.object(aimem_db, "DB", self.db)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(aimem_db, "ROOT", self.root)
        p.start()
        self.addCleanup(p.stop)

    def seed(self, with_rows=True):
        aimem_db.cmd_init()
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO meta(key,value) VALUES('rev','99')")
            if with_rows:
                con.execute("INSERT INTO slots(slot,token,harness,model,role,note) VALUES"
                            "('SDB','tok999','claude','엉터리','DB역할','DB비고')")
                con.execute("INSERT INTO tasks(id,title,slot,status,inherited,artifacts) VALUES"
                            "('T-DB','DB작업','SDB','REVIEW','T-0','db.txt')")
                con.execute("INSERT INTO queue(pos,task,slot_hint,inherited,note) VALUES"
                            "(3,'DB큐','SDB','T-DB','DB큐비고')")
                con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES"
                            "('2026-11-09T19:45:00','관리자',99,'handoff','DB핸드오프')")
        con.close()


class DbIsCanonical(_Base):
    def test_1_db_values_returned(self):
        self.seed()
        s = reader.collect(self.root)
        self.assertEqual([x["slot"] for x in s["slots"]], ["SDB"])
        self.assertEqual(s["slots"][0]["role"], "DB역할")
        self.assertEqual(s["slots"][0]["token"], "tok999")
        self.assertEqual(s["board"][0]["id"], "T-DB")
        self.assertEqual(s["board"][0]["task"], "DB작업")
        self.assertEqual(s["board"][0]["status"], "REVIEW")
        self.assertEqual(s["queue"][0]["task"], "DB큐")
        self.assertEqual(s["queue"][0]["note"], "DB큐비고")
        self.assertEqual(len(s["log"]), 1)
        self.assertIn("DB핸드오프", s["log"][0]["text"])
        self.assertEqual(s["aimem"]["rev"], 99)  # AIMEM.md 의 REV 7 이 아니라 DB

    def test_1b_db_wins_over_markdown_tables(self):
        self.aimem_text = TABLE_AIMEM
        (self.root / "AIMEM.md").write_text(TABLE_AIMEM, encoding="utf-8")
        self.seed()
        s = reader.collect(self.root)
        self.assertEqual([x["slot"] for x in s["slots"]], ["SDB"])
        self.assertEqual([x["id"] for x in s["board"]], ["T-DB"])
        self.assertEqual([x["task"] for x in s["queue"]], ["DB큐"])
        self.assertNotIn("마크다운로그", repr(s["log"]))

    def test_2_no_tables_in_aimem_no_errors(self):
        self.seed()
        s = reader.collect(self.root)
        self.assertEqual(s["errors"], [])

    def test_3_key_shapes(self):
        self.seed()
        s = reader.collect(self.root)
        self.assertEqual(set(s["slots"][0]),
                         {"slot", "token", "harness", "role", "note", "model", "model_source"})
        self.assertEqual(set(s["board"][0]),
                         {"id", "task", "slot", "status", "handoff", "artifact"})
        self.assertEqual(set(s["queue"][0]), {"order", "task", "slots", "handoff", "note"})
        self.assertEqual(set(s["log"][0]), {"when", "text"})

    def test_4_queue_order_is_str(self):
        self.seed()
        s = reader.collect(self.root)
        self.assertIsInstance(s["queue"][0]["order"], str)
        self.assertEqual(s["queue"][0]["order"], "3")

    def test_5_log_handoff_only_newest_first(self):
        self.seed()
        con = sqlite3.connect(self.db)
        with con:
            con.executemany(
                "INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                [("2026-11-09T10:00:00", "관리자", 99, "handoff", "- `2026-11-09 10:00` 관리자: 가장오래"),
                 ("2026-11-09T22:00:00", "관리자", 99, "task", "태스크이벤트"),
                 ("2026-11-09T21:00:00", "관리자", 99, "ownership", "소유권이벤트"),
                 ("2026-11-09T20:30:00", "관리자", 99, "handoff", "- `2026-11-09 20:30` 관리자: 가장최신")])
        con.close()
        s = reader.collect(self.root)
        blob = repr(s["log"])
        self.assertNotIn("태스크이벤트", blob)
        self.assertNotIn("소유권이벤트", blob)
        self.assertEqual(len(s["log"]), 3)
        whens = [e["when"] for e in s["log"]]
        self.assertEqual(whens, sorted(whens, reverse=True))
        self.assertEqual(whens[0], "2026-11-09 20:30")

    def test_6_log_when_has_no_markdown_head(self):
        self.seed(with_rows=False)
        con = sqlite3.connect(self.db)
        with con:
            con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES"
                        "('2026-11-09T19:45:00','관리자',99,'handoff',"
                        "'- `2026-11-09 19:45` 관리자(R4): 본문')")
        con.close()
        e = reader.collect(self.root)["log"][0]
        self.assertEqual(e["when"], "2026-11-09 19:45")
        self.assertTrue(e["text"].startswith("관리자(R4)"), e["text"])
        self.assertNotIn("`", e["text"])
        self.assertFalse(e["text"].startswith("-"))

    def test_8_model_from_harness_config_not_db(self):
        self.seed()
        s = reader.collect(self.root)
        self.assertNotEqual(s["slots"][0]["model"], "엉터리")
        expected = reader.harness_model("claude")[0]
        self.assertEqual(s["slots"][0]["model"], expected)

    def test_8b_fleet_slots_json_beats_harness_default(self):
        self.seed()
        (self.root / "tools").mkdir()
        (self.root / "tools" / "fleet_slots.json").write_text(
            '{"SDB": {"model": "slot-json-model"}}', encoding="utf-8")
        s = reader.collect(self.root)
        self.assertEqual(s["slots"][0]["model"], "slot-json-model")
        self.assertEqual(s["slots"][0]["model_source"], reader.SLOT_MODEL_SOURCE)


class MarkdownFallback(_Base):
    aimem_text = TABLE_AIMEM

    def test_7_missing_db_falls_back_to_markdown(self):
        self.assertFalse(self.db.exists())
        s = reader.collect(self.root)
        self.assertEqual([x["slot"] for x in s["slots"]], ["SMD"])
        self.assertEqual(s["slots"][0]["role"], "마크다운역할")
        self.assertEqual([x["id"] for x in s["board"]], ["T-MD"])
        self.assertEqual([x["task"] for x in s["queue"]], ["마크다운큐"])
        self.assertIn("마크다운로그", s["log"][0]["text"])
        self.assertGreaterEqual(len(s["errors"]), 1)
        self.assertTrue(any("DB" in e for e in s["errors"]), s["errors"])

    def test_7b_fallback_does_not_create_db(self):
        reader.collect(self.root)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
