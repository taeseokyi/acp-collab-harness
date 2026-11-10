# -*- coding: utf-8 -*-
"""aimem_monitor.reader 계약 테스트. 표준 라이브러리 unittest 만 사용.

reader.py 구현은 읽지 않는다. 관리자가 못박은 인터페이스와 스키마만 검증한다.
"""

import datetime
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from aimem_monitor import PROGRESS_WEIGHTS, REQUEST_DETAIL_MAX, STATE_KEYS

try:
    from aimem_monitor import reader
except ImportError:
    reader = None


EXPECTED_KEYS = {
    "generated",
    "root",
    "aimem",
    "slots",
    "board",
    "queue",
    "log",
    "runs",
    "eta",
    "requests",
    "errors",
}

SLOT_KEYS = {"slot", "token", "harness", "role", "note", "model", "model_source"}
BOARD_KEYS = {"id", "task", "slot", "status", "handoff", "artifact"}
QUEUE_KEYS = {"order", "task", "slots", "handoff", "note"}
LOG_KEYS = {"when", "text"}
RUN_KEYS = {
    "id",
    "slot",
    "harness",
    "model",
    "label",
    "rev",
    "write",
    "started",
    "state",
    "rc",
    "elapsed_sec",
    "report_head",
}

AIMEM_FIXTURE = """# AIMEM.md - 공유 작업 메모리

- **REV: 109** (개정 번호)
- 최종 갱신: 2026-11-09 16:40 KST

## 1. 현재 목표

- **목표 (라운드 3, 2026-11-09~):** 함대 모니터링 웹 UI 를 만든다
- **상태:** 진행 중

## 2. 세션 명부

| 슬롯 | 확인토큰 | 하네스   | 역할 | 세션키 | 비고 |
| ---- | -------- | -------- | ---- | ------ | ---- |
| S1 | `a41f0c` | claude | 린터 / 보드 CLI | - | CLI 작업자 |
| S2 | `d27e93` | codex | 테스트 / 파이프라인 | - | CLI 작업자 |

## 3. 작업 보드

| ID | 태스크 | 담당 슬롯 | 상태 | 이어받음 | 산출물 |
| -- | ------ | --------- | ---- | -------- | ------ |
| T-036 | 데이터 계층 | S1 | REVIEW | - | `reader.py` |
| T-039 | 서버 | 관리자 | DONE | - | `server.py` |
| T-040 | 미배정 작업 | 미배정 | TODO | - | - |

## 4. 핸드오프 로그

- `2026-11-09 16:40` 관리자: **REV 109.** 최신 항목이다
- `2026-11-09 15:00` 관리자: **REV 108.** 그 앞 항목이다

## 4.5 대기 큐

| 순서 | 태스크 | 후보 슬롯 | 이어받음 | 비고 |
| ---- | ------ | --------- | -------- | ---- |
| 1 | 통합 검수 | S3 | T-036 | 라운드 4 |
"""


def write_aimem(root, text):
    (root / "AIMEM.md").write_text(text, encoding="utf-8")


def add_run(
    root,
    run_id,
    *,
    slot="S2",
    harness="codex",
    model="kistillm",
    label="계약 테스트",
    rev="109",
    write_path="tests/test_aimem_monitor.py",
    started="2026-11-09T16:31:12",
    pid=None,
    rc=None,
    elapsed=None,
    out=None,
):
    runs_dir = root / ".aimem" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": run_id,
        "slot": slot,
        "harness": harness,
        "model": model,
        "label": label,
        "rev": rev,
        "write": write_path,
        "started": started,
        "brief": "픽스처",
    }
    if pid is not None:
        data["pid"] = pid
    (runs_dir / f"{run_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    if rc is not None:
        rc_path = runs_dir / f"{run_id}.rc"
        rc_path.write_text(f"{rc}\n", encoding="utf-8")
        if elapsed is not None:
            start = datetime.datetime.fromisoformat(started).timestamp()
            stamp = start + elapsed
            os.utime(rc_path, (stamp, stamp))
    if out is not None:
        (runs_dir / f"{run_id}.out").write_text(out, encoding="utf-8")


def add_request(root, request_id, payload):
    requests_dir = root / ".aimem" / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    (requests_dir / f"{request_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def base_request(request_id, subtasks):
    return {
        "id": request_id,
        "created": "2026-11-09 16:45",
        "requester": "관리자",
        "title": "웹 UI 계약",
        "detail": "계약 테스트용 요청",
        "status": "PLANNED",
        "subtasks": subtasks,
    }


def build_fixture(root):
    write_aimem(root, AIMEM_FIXTURE)

    add_run(
        root,
        "a",
        harness="claude",
        model="claude-sonnet",
        rc=0,
        elapsed=20,
        out=json.dumps({"result": "DONE 어쩌고"}, ensure_ascii=False),
    )
    add_run(root, "b", harness="codex", rc=0, elapsed=50, out="DONE codex 보고\n둘째 줄")
    add_run(
        root,
        "c",
        harness="claude",
        model="claude-sonnet",
        rc=0,
        elapsed=40,
        out=json.dumps({"result": "DONE 두 번째"}, ensure_ascii=False),
    )
    add_run(root, "d", harness="codex", rc=2, elapsed=10, out="FAILED 보고")
    add_run(root, "e", harness="codex", pid=os.getpid())
    add_run(root, "f", harness="codex", pid=999999)
    add_run(root, "g", harness="opencode", out="> model · 진행로그\n진행 로그 첫 줄\n본문")

    add_request(
        root,
        "R-1",
        base_request(
            "R-1",
            [
                {"task": "A", "slot": "S1", "status": "DONE"},
                {"task": "B", "slot": "S1", "status": "TODO"},
                {"task": "C", "slot": "S2", "status": "TODO"},
                {"task": "D", "slot": "S1", "status": "REVIEW"},
            ],
        ),
    )
    add_request(root, "R-2", base_request("R-2", []))
    add_request(
        root,
        "R-3",
        base_request(
            "R-3",
            [
                {"task": "A", "slot": "S1", "status": "DONE"},
                {"task": "B", "slot": "S2", "status": "DONE"},
            ],
        ),
    )


def entry_by_id(items, key, value):
    for item in items:
        if item.get(key) == value:
            return item
    raise AssertionError(f"{key}={value} 항목이 없습니다: {items}")


@unittest.skipIf(reader is None, "reader.py 아직 없음")
class TestStateContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        build_fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self):
        return reader.collect(self.root)

    def test_top_level_keys_and_basic_types(self):
        state = self.collect()
        self.assertIsInstance(state, dict)
        self.assertTrue(EXPECTED_KEYS.issubset(state.keys()))
        self.assertIsInstance(state["generated"], str)
        datetime.datetime.fromisoformat(state["generated"].replace("Z", "+00:00"))
        self.assertIsInstance(state["root"], str)
        self.assertTrue(os.path.isabs(state["root"]))
        self.assertEqual(pathlib.Path(state["root"]).resolve(), self.root.resolve())
        self.assertIsInstance(state["errors"], list)
        for item in state["errors"]:
            self.assertIsInstance(item, str)

    def test_aimem_header_and_goal(self):
        state = self.collect()
        aimem = state["aimem"]
        self.assertIsInstance(aimem, dict)
        self.assertEqual(aimem["rev"], 109)
        self.assertIsInstance(aimem["lines"], int)
        self.assertEqual(aimem["lines"], len(AIMEM_FIXTURE.splitlines()))
        self.assertIsInstance(aimem["updated"], str)
        self.assertIn("2026-11-09", aimem["updated"])
        goal = aimem["goal"]
        self.assertEqual(goal["text"], "함대 모니터링 웹 UI 를 만든다")
        self.assertEqual(goal["status"], "진행 중")

    def test_slots_discard_session_key_and_skip_table_noise(self):
        slots = self.collect()["slots"]
        self.assertEqual(len(slots), 2)
        for entry in slots:
            self.assertEqual(set(entry), SLOT_KEYS)
            for key in SLOT_KEYS:
                self.assertIsInstance(entry[key], str)
        s1 = entry_by_id(slots, "slot", "S1")
        s2 = entry_by_id(slots, "slot", "S2")
        self.assertEqual(s1["token"], "a41f0c")
        self.assertEqual(s2["token"], "d27e93")
        self.assertEqual(s1["harness"], "claude")
        self.assertEqual(s2["harness"], "codex")
        self.assertEqual(s1["role"], "린터 / 보드 CLI")
        self.assertEqual(s2["role"], "테스트 / 파이프라인")
        self.assertEqual(s1["note"], "CLI 작업자")
        self.assertNotIn("슬롯", {entry["slot"] for entry in slots})
        self.assertNotIn("----", {entry["slot"] for entry in slots})

    def test_board_includes_manager_and_unassigned_rows(self):
        board = self.collect()["board"]
        self.assertEqual(len(board), 3)
        for entry in board:
            self.assertEqual(set(entry), BOARD_KEYS)
            for key in BOARD_KEYS:
                self.assertIsInstance(entry[key], str)
        self.assertIn("관리자", {entry["slot"] for entry in board})
        self.assertIn("미배정", {entry["slot"] for entry in board})
        t036 = entry_by_id(board, "id", "T-036")
        self.assertEqual(t036["slot"], "S1")
        self.assertEqual(t036["status"], "REVIEW")
        self.assertIn("reader.py", t036["artifact"])
        t039 = entry_by_id(board, "id", "T-039")
        self.assertEqual(t039["slot"], "관리자")
        self.assertEqual(t039["status"], "DONE")
        self.assertIn("server.py", t039["artifact"])

    def test_queue_parsing(self):
        queue = self.collect()["queue"]
        self.assertEqual(len(queue), 1)
        entry = queue[0]
        self.assertEqual(set(entry), QUEUE_KEYS)
        for key in QUEUE_KEYS:
            self.assertIsInstance(entry[key], str)
        self.assertEqual(entry["order"], "1")
        self.assertEqual(entry["task"], "통합 검수")
        self.assertEqual(entry["slots"], "S3")
        self.assertEqual(entry["handoff"], "T-036")
        self.assertEqual(entry["note"], "라운드 4")

    def test_log_is_newest_first_and_truncates(self):
        long_text = "가" * 1200
        fixture = AIMEM_FIXTURE.replace(
            "## 4.5 대기 큐",
            "- `2026-11-09 14:00` 관리자: " + long_text + "\n\n## 4.5 대기 큐",
        )
        write_aimem(self.root, fixture)
        log = self.collect()["log"]
        self.assertEqual(len(log), 3)
        for entry in log:
            self.assertEqual(set(entry), LOG_KEYS)
            self.assertIsInstance(entry["when"], str)
            self.assertIsInstance(entry["text"], str)
        self.assertEqual(log[0]["when"], "2026-11-09 16:40")
        self.assertIn("최신 항목", log[0]["text"])
        self.assertEqual(log[1]["when"], "2026-11-09 15:00")
        self.assertIn("그 앞 항목", log[1]["text"])
        self.assertEqual(log[2]["when"], "2026-11-09 14:00")
        self.assertNotIn("2026-11-09", log[0]["text"])
        self.assertTrue(log[2]["text"].endswith("..."))
        self.assertEqual(len(log[2]["text"]), 403)

    def test_runs_states_and_order(self):
        runs = self.collect()["runs"]
        self.assertEqual([run["id"] for run in runs], sorted(run["id"] for run in runs))
        for entry in runs:
            self.assertTrue(RUN_KEYS.issubset(entry.keys()))
            self.assertIsInstance(entry["report_head"], str)
            self.assertIn(entry["state"], ("running", "done", "lost", "unknown"))
            self.assertTrue(entry["rc"] is None or isinstance(entry["rc"], int))
        self.assertEqual(entry_by_id(runs, "id", "a")["state"], "done")
        self.assertEqual(entry_by_id(runs, "id", "a")["rc"], 0)
        self.assertEqual(entry_by_id(runs, "id", "d")["state"], "done")
        self.assertEqual(entry_by_id(runs, "id", "d")["rc"], 2)
        self.assertEqual(entry_by_id(runs, "id", "e")["state"], "running")
        self.assertEqual(entry_by_id(runs, "id", "f")["state"], "lost")
        self.assertEqual(entry_by_id(runs, "id", "g")["state"], "unknown")
        self.assertEqual(entry_by_id(runs, "id", "a")["elapsed_sec"], 20)
        self.assertEqual(entry_by_id(runs, "id", "b")["elapsed_sec"], 50)
        self.assertEqual(entry_by_id(runs, "id", "c")["elapsed_sec"], 40)

    def test_report_head_unwraps_harness_formats(self):
        runs = self.collect()["runs"]
        claude = entry_by_id(runs, "id", "a")["report_head"]
        codex = entry_by_id(runs, "id", "b")["report_head"]
        opencode = entry_by_id(runs, "id", "g")["report_head"]
        self.assertIn("DONE 어쩌고", claude)
        self.assertNotIn('{"result"', claude)
        self.assertIn("DONE codex 보고", codex)
        self.assertIn("진행 로그 첫 줄", opencode)
        self.assertNotIn("> model", opencode)

    def test_eta_by_harness_medians(self):
        eta = self.collect()["eta"]
        self.assertEqual(set(eta), {"by_harness", "overall"})
        claude = eta["by_harness"]["claude"]
        codex = eta["by_harness"]["codex"]
        self.assertEqual(claude["median_sec"], 30)
        self.assertEqual(claude["samples"], 2)
        self.assertEqual(codex["median_sec"], 50)
        self.assertEqual(codex["samples"], 1)
        self.assertIsInstance(claude["source"], list)
        self.assertEqual(eta["overall"]["median_sec"], 40)
        self.assertEqual(eta["overall"]["samples"], 3)

    def test_progress_pct_and_empty_subtasks(self):
        requests = self.collect()["requests"]
        by_id = {entry["id"]: entry for entry in requests}
        expected_r1 = round(
            (
                PROGRESS_WEIGHTS["DONE"]
                + PROGRESS_WEIGHTS["TODO"]
                + PROGRESS_WEIGHTS["TODO"]
                + PROGRESS_WEIGHTS["REVIEW"]
            )
            / 4
            * 100,
            1,
        )
        self.assertEqual(by_id["R-1"]["progress_pct"], expected_r1)
        self.assertEqual(by_id["R-2"]["progress_pct"], 0.0)
        self.assertEqual(by_id["R-3"]["progress_pct"], 100.0)
        for request_id, expected in (("R-1", 45.0), ("R-2", 0.0), ("R-3", 100.0)):
            self.assertIsInstance(by_id[request_id]["progress_pct"], float)
            self.assertEqual(round(by_id[request_id]["progress_pct"], 1), expected)

    def test_eta_uses_max_not_sum(self):
        requests = self.collect()["requests"]
        r1 = entry_by_id(requests, "id", "R-1")
        self.assertEqual(r1["eta_sec"], 50)
        self.assertIsInstance(r1["eta_basis"], str)
        self.assertTrue(r1["eta_basis"].strip())
        self.assertTrue(r1["eta_at"] is None or isinstance(r1["eta_at"], str))
        r2 = entry_by_id(requests, "id", "R-2")
        self.assertEqual(r2["eta_sec"], 0)
        self.assertTrue(r2["eta_basis"].strip())
        r3 = entry_by_id(requests, "id", "R-3")
        self.assertEqual(r3["eta_sec"], 0)

    def test_request_payload_is_preserved_and_extended(self):
        requests = self.collect()["requests"]
        r1 = entry_by_id(requests, "id", "R-1")
        for key in ("id", "created", "requester", "title", "detail", "status", "subtasks"):
            self.assertIn(key, r1)
        for key in ("progress_pct", "eta_sec", "eta_at", "eta_basis"):
            self.assertIn(key, r1)
        self.assertEqual(r1["created"], "2026-11-09 16:45")
        self.assertEqual(r1["requester"], "관리자")
        self.assertEqual(len(r1["subtasks"]), 4)

    def test_state_is_json_serializable_without_ascii_escape(self):
        state = self.collect()
        text = json.dumps(state, ensure_ascii=False)
        self.assertIsInstance(text, str)
        self.assertIn("함대 모니터링", text)
        self.assertNotIn("\\u", text)


@unittest.skipIf(reader is None, "reader.py 아직 없음")
class TestMedianDurations(unittest.TestCase):
    def test_failed_runs_are_excluded_from_samples(self):
        runs = [
            {"id": "ok1", "harness": "claude", "state": "done", "rc": 0, "elapsed_sec": 20},
            {"id": "ok2", "harness": "claude", "state": "done", "rc": 0, "elapsed_sec": 40},
            {"id": "fail", "harness": "claude", "state": "done", "rc": 2, "elapsed_sec": 999},
            {"id": "nosample", "harness": "claude", "state": "done", "rc": 0, "elapsed_sec": None},
            {"id": "running", "harness": "claude", "state": "running", "rc": None, "elapsed_sec": 1},
        ]
        result = reader.median_durations(runs)
        self.assertEqual(result["by_harness"]["claude"]["median_sec"], 30)
        self.assertEqual(result["by_harness"]["claude"]["samples"], 2)
        self.assertEqual(result["overall"]["median_sec"], 30)
        self.assertEqual(result["overall"]["samples"], 2)
        self.assertNotIn(999, result["by_harness"]["claude"]["source"])

    def test_empty_samples_return_none_without_exception(self):
        result = reader.median_durations([])
        self.assertEqual(result["by_harness"], {})
        self.assertIsNone(result["overall"]["median_sec"])
        self.assertEqual(result["overall"]["samples"], 0)
        failed_only = reader.median_durations(
            [{"harness": "codex", "state": "done", "rc": 1, "elapsed_sec": 5}]
        )
        self.assertIsNone(failed_only["overall"]["median_sec"])
        self.assertEqual(failed_only["overall"]["samples"], 0)


@unittest.skipIf(reader is None, "reader.py 아직 없음")
class TestBrokenInputs(unittest.TestCase):
    def test_missing_aimem_is_reported_without_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            state = reader.collect(root)
            self.assertTrue(EXPECTED_KEYS.issubset(state.keys()))
            self.assertIsInstance(state["errors"], list)
            self.assertGreater(len(state["errors"]), 0)

    def test_broken_aimem_is_reported_without_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "AIMEM.md").write_text("# 깨진 파일\n섹션 없음\n", encoding="utf-8")
            state = reader.collect(root)
            self.assertTrue(EXPECTED_KEYS.issubset(state.keys()))
            self.assertIsInstance(state["errors"], list)
            self.assertGreater(len(state["errors"]), 0)


@unittest.skipIf(reader is None, "reader.py 아직 없음")
class TestRealRepositorySmoke(unittest.TestCase):
    def test_real_repository_collects_without_errors(self):
        repo = pathlib.Path(__file__).resolve().parent.parent
        state = reader.collect(repo)
        self.assertIsInstance(state, dict)
        self.assertTrue(EXPECTED_KEYS.issubset(state.keys()))
        self.assertEqual(state["errors"], [])


# ---------------------------------------------------------------------------
# 공개면 2차 계약 (T-076, REV 114 유출 검수). 위의 클래스들은 `reader.collect()` -
# **내부 계층**이 `root`/`slots[].token` 을 그대로 내는 것을 못박고, 아래는 그것이
# `server.collect_state()` / `GET /api/state` - **공개 계층**에서 빠지는 것을 못박는다.
# 둘 다 참이어야 한다: reader 가 안 내면 server 의 scrub 이 죽은 코드가 된다.
# ---------------------------------------------------------------------------

import http.client
import http.server
import subprocess
import threading
from unittest import mock

try:
    from aimem_monitor import server
except ImportError:
    server = None

REPO = pathlib.Path(__file__).resolve().parent.parent
PUBLIC_SLOT_KEYS = SLOT_KEYS - {"token"}


def _real_tokens():
    """`aimem_db.py state` 의 `slots[].token` - 공개면에 나가면 안 되는 실제 값."""
    out = subprocess.run([sys.executable, str(REPO / "tools" / "aimem_db.py"), "state"],
                         capture_output=True, text=True, timeout=60, cwd=str(REPO))
    if out.returncode != 0:
        raise unittest.SkipTest("aimem_db.py state 실패: " + out.stderr[-200:])
    return [s["token"] for s in json.loads(out.stdout)["slots"] if len(s.get("token") or "") >= 4]


class _Srv:
    """`serve()` 와 같은 모양 - 핸들러에 `RequestRateLimiter` 를 묶어 포트 0 으로 띄운다."""

    def __init__(self, root, rate=True):
        handler = type("H", (server.Handler,), {
            "root": pathlib.Path(root), "require_auth": False, "tls": False,
            "access_token": None, "guard": None, "timeout": 5,
            "rate": server.RequestRateLimiter() if rate else None,
            "log_message": lambda *a, **k: None,
        })
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {}
            data = None
            if body is not None:
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers = {"Content-Type": "application/json"}
            c.request(method, path, body=data, headers=headers)
            r = c.getresponse()
            return r.status, r.read()
        finally:
            c.close()


@unittest.skipIf(server is None, "server.py 아직 없음")
class TestPublicStateLeaks(unittest.TestCase):
    """`/api/state` 에서 `root`·`slots[].token`·`kisti.url` 이 빠진다 (항목 1~5)."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = _real_tokens()
        cls.state = server.collect_state(REPO)

    # 1
    def test_collect_state_has_no_root_key(self):
        self.assertNotIn("root", self.state)
        self.assertNotIn("paths", self.state)

    # 2
    def test_slots_have_no_token_but_keep_the_rest(self):
        slots = self.state["slots"]
        self.assertGreater(len(slots), 0)
        for entry in slots:
            self.assertNotIn("token", entry)
            self.assertTrue(set(entry) <= PUBLIC_SLOT_KEYS, f"예상 밖 키: {set(entry) - PUBLIC_SLOT_KEYS}")
            for key in ("slot", "harness", "role", "note", "model", "model_source"):
                self.assertIn(key, entry, f"{entry.get('slot')}: {key} 가 빠졌다")

    # 3
    def test_http_body_contains_neither_repo_path_nor_slot_tokens(self):
        self.assertGreater(len(self.tokens), 0, "비교할 확인토큰이 없다")
        srv = _Srv(REPO)
        try:
            status, body = srv.req("GET", "/api/state")
        finally:
            srv.close()
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        json.loads(text)   # 본문이 유효한 JSON 이다
        self.assertNotIn(str(REPO), text, "저장소 절대경로가 응답 본문 어딘가에 남았다")
        self.assertNotIn(str(REPO).replace("/", "\\/"), text)
        for tok in self.tokens:
            self.assertNotIn(tok, text, f"확인토큰 {tok[:2]}**** 이 응답 본문에 남았다")

    # 4
    def test_kisti_has_no_url_key(self):
        kisti = self.state["kisti"]
        self.assertIsInstance(kisti, dict)
        self.assertNotIn("url", kisti)
        self.assertNotIn(server.KISTI_STATUS_URL, json.dumps(self.state, ensure_ascii=False))

    def test_scrub_public_masks_values_not_only_keys(self):
        state = {"root": "/srv/secret/repo", "slots": [{"slot": "S9", "token": "abc123"}],
                 "kisti": {"url": "https://internal.example/status"},
                 "runs": [{"report_head": "pwd=/srv/secret/repo tok=abc123", "label": "x"}],
                 "errors": ["열기 실패 /srv/secret/repo/a abc123"]}
        out = server.scrub_public(state, "/srv/secret/repo")
        text = json.dumps(out, ensure_ascii=False)
        for leaked in ("/srv/secret/repo", "abc123", "internal.example"):
            self.assertNotIn(leaked, text)
        self.assertNotIn("root", out)
        self.assertNotIn("token", out["slots"][0])
        self.assertNotIn("url", out["kisti"])

    # 5
    def test_failure_branch_and_normal_branch_have_same_top_level_keys(self):
        normal = server.collect_state(REPO)
        with mock.patch.object(server, "_reader") as rd:
            rd.return_value.collect.side_effect = RuntimeError("의도된 실패")
            failed = server.collect_state(REPO)
        self.assertTrue(failed["errors"], "실패 분기가 errors 를 남기지 않았다")
        self.assertEqual(set(failed), set(normal),
                         f"어긋난 키: {sorted(set(failed) ^ set(normal))}")
        for branch in (normal, failed):
            self.assertNotIn("root", branch)
            self.assertNotIn("url", branch["kisti"])

    def test_non_dict_and_sparse_reader_results_also_match(self):
        normal = set(server.collect_state(REPO))
        for bad in ("문자열", {}, {"runs": []}):
            with self.subTest(bad=bad), mock.patch.object(server, "_reader") as rd:
                rd.return_value.collect.return_value = bad
                self.assertEqual(set(server.collect_state(REPO)), normal)


@unittest.skipIf(server is None, "server.py 아직 없음")
class TestRequestDetailTruncation(unittest.TestCase):
    """`requests[].detail` 은 공개 직전에만 잘리고, 잘린 사실을 함께 싣는다 (T-085)."""

    def scrub(self, requests, root=None):
        state = {"requests": requests}
        return server.scrub_public(state, root)

    def test_long_detail_is_truncated_with_marker(self):
        detail = "가" * 2000
        req = self.scrub([{"id": "R-1", "detail": detail}])["requests"][0]
        self.assertEqual(len(req["detail"]), REQUEST_DETAIL_MAX + 1)
        self.assertEqual(req["detail"][-1], "…")
        self.assertIs(req["detail_truncated"], True)
        self.assertEqual(req["detail_len"], 2000)

    def test_short_detail_is_unchanged(self):
        req = self.scrub([{"id": "R-1", "detail": "짧다"}])["requests"][0]
        self.assertEqual(req["detail"], "짧다")
        self.assertIs(req["detail_truncated"], False)
        self.assertEqual(req["detail_len"], 2)

    def test_exact_max_boundary_is_not_truncated(self):
        detail = "가" * REQUEST_DETAIL_MAX
        req = self.scrub([{"id": "R-1", "detail": detail}])["requests"][0]
        self.assertEqual(req["detail"], detail)
        self.assertIs(req["detail_truncated"], False)
        self.assertEqual(req["detail_len"], REQUEST_DETAIL_MAX)

    def test_max_plus_one_boundary_is_truncated(self):
        detail = "가" * (REQUEST_DETAIL_MAX + 1)
        req = self.scrub([{"id": "R-1", "detail": detail}])["requests"][0]
        self.assertEqual(len(req["detail"]), REQUEST_DETAIL_MAX + 1)
        self.assertEqual(req["detail"][-1], "…")
        self.assertIs(req["detail_truncated"], True)
        self.assertEqual(req["detail_len"], REQUEST_DETAIL_MAX + 1)

    def test_non_string_or_missing_detail_gets_markers(self):
        cases = {
            "None": {"id": "R-1", "detail": None},
            "number": {"id": "R-1", "detail": 123},
            "missing": {"id": "R-1"},
        }
        for name, payload in cases.items():
            with self.subTest(name):
                req = self.scrub([payload])["requests"][0]
                self.assertIs(req["detail_truncated"], False)
                self.assertEqual(req["detail_len"], 0)

    def test_non_list_requests_do_not_raise(self):
        for requests in (None, {}, "문자열"):
            with self.subTest(requests=requests):
                out = self.scrub(requests)
                self.assertIn("requests", out)

    def test_state_keys_document_detail_markers(self):
        contract = STATE_KEYS["requests"]
        self.assertIn("detail_truncated", contract)
        self.assertIn("detail_len", contract)

    def test_detail_is_truncated_only_at_the_public_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            request_path = root / ".aimem" / "requests" / "R-1.json"
            request_path.parent.mkdir(parents=True)
            original = "가" * 2000
            payload = {"id": "R-1", "detail": original}
            request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            state = {"requests": [json.loads(request_path.read_text(encoding="utf-8"))]}
            before = state["requests"][0]["detail"]
            self.assertEqual(before, original)

            out = server.scrub_public(state, root)

            self.assertEqual(before, original)
            self.assertEqual(json.loads(request_path.read_text(encoding="utf-8"))["detail"], original)
            self.assertEqual(len(state["requests"][0]["detail"]), REQUEST_DETAIL_MAX + 1)
            self.assertEqual(out["requests"][0]["detail_len"], 2000)
            self.assertIs(out["requests"][0]["detail_truncated"], True)


@unittest.skipIf(server is None, "server.py 아직 없음")
class TestRequestRateLimit(unittest.TestCase):
    """`POST /api/requests` 분당 제한 (항목 6~8)."""

    BODY = {"title": "속도 제한 시험", "detail": "d", "requester": "tester"}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.srv = _Srv(self.root)
        self.reqdir = self.root / ".aimem" / "requests"

    def tearDown(self):
        self.srv.close()
        self._tmp.cleanup()

    def count(self):
        return len(list(self.reqdir.glob("*.json"))) if self.reqdir.exists() else 0

    def post(self):
        return self.srv.req("POST", "/api/requests", self.BODY)

    def fill(self):
        for i in range(server.REQUEST_RATE_MAX):
            status, body = self.post()
            self.assertEqual(status, 201, f"{i + 1}번째가 거절됐다: {body!r}")

    def test_limit_constants_are_per_minute(self):
        self.assertEqual(server.REQUEST_RATE_WINDOW_SEC, 60)
        self.assertGreaterEqual(server.REQUEST_RATE_MAX, 1)

    # 6
    def test_request_over_limit_is_429_with_ok_false(self):
        self.fill()
        status, body = self.post()
        self.assertEqual(status, 429, body)
        payload = json.loads(body)
        self.assertIs(payload["ok"], False)
        self.assertTrue(payload.get("error"))

    # 7
    def test_limit_releases_after_window(self):
        self.fill()
        self.assertEqual(self.post()[0], 429)
        later = time.time() + server.REQUEST_RATE_WINDOW_SEC + 5
        with mock.patch.object(server.time, "time", return_value=later):
            status, body = self.post()
        self.assertEqual(status, 201, body)

    def test_limit_still_holds_just_inside_window(self):
        self.fill()
        inside = time.time() + server.REQUEST_RATE_WINDOW_SEC - 10
        with mock.patch.object(server.time, "time", return_value=inside):
            self.assertEqual(self.post()[0], 429)

    # 8
    def test_rejected_request_creates_no_file(self):
        self.fill()
        before = self.count()
        self.assertEqual(before, server.REQUEST_RATE_MAX)
        for _ in range(3):
            self.assertEqual(self.post()[0], 429)
        self.assertEqual(self.count(), before)
        self.assertEqual(sorted(p.name for p in self.reqdir.iterdir() if not p.name.endswith(".json")), [])

    def test_validation_failures_do_not_consume_quota(self):
        for _ in range(server.REQUEST_RATE_MAX + 2):
            status, _body = self.srv.req("POST", "/api/requests", {"title": "", "requester": "t"})
            self.assertEqual(status, 400)
        self.assertEqual(self.post()[0], 201)

    def test_limiter_unit_window_boundary(self):
        lim = server.RequestRateLimiter(limit=2, window=60)
        for _ in range(2):
            self.assertTrue(lim.allow("ip", now=1000.0)[0])   # allow 가 통과 시 센다
        ok, wait = lim.allow("ip", now=1010.0)
        self.assertFalse(ok)
        self.assertGreaterEqual(wait, 1)
        self.assertTrue(lim.allow("other-ip", now=1010.0)[0])   # IP 별로 센다
        self.assertTrue(lim.allow("ip", now=1061.0)[0])

    def test_limiter_allow_counts_on_pass_without_record(self):
        lim = server.RequestRateLimiter(limit=2, window=60)
        self.assertTrue(lim.allow("ip", now=1000.0)[0])
        self.assertTrue(lim.allow("ip", now=1000.0)[0])
        self.assertFalse(lim.allow("ip", now=1000.0)[0])   # record 없이 세 번째 거절

    def test_limiter_allow_does_not_count_rejections(self):
        lim = server.RequestRateLimiter(limit=2, window=60)
        for _ in range(2):
            self.assertTrue(lim.allow("ip", now=1000.0)[0])
        for _ in range(10):
            self.assertFalse(lim.allow("ip", now=1030.0)[0])
        # 거절이 세어졌다면 창이 지나도 버킷이 차 있을 것이다
        self.assertTrue(lim.allow("ip", now=1061.0)[0])
        self.assertTrue(lim.allow("ip", now=1061.0)[0])
        self.assertFalse(lim.allow("ip", now=1061.0)[0])

    def test_limiter_refund_returns_slot(self):
        lim = server.RequestRateLimiter(limit=2, window=60)
        self.assertTrue(lim.allow("ip", now=1000.0)[0])
        self.assertTrue(lim.allow("ip", now=1000.0)[0])
        self.assertFalse(lim.allow("ip", now=1000.0)[0])
        lim.refund("ip", now=1000.0)
        self.assertTrue(lim.allow("ip", now=1000.0)[0])
        self.assertFalse(lim.allow("ip", now=1000.0)[0])

    def test_limiter_refund_on_empty_bucket_is_safe(self):
        lim = server.RequestRateLimiter(limit=2, window=60)
        lim.refund("never-seen", now=1000.0)
        lim.refund("never-seen", now=1000.0)
        # 빈 버킷 환불이 한도를 늘려서는 안 된다
        self.assertTrue(lim.allow("never-seen", now=1000.0)[0])
        self.assertTrue(lim.allow("never-seen", now=1000.0)[0])
        self.assertFalse(lim.allow("never-seen", now=1000.0)[0])

    def test_limiter_concurrent_allow_passes_exactly_limit(self):
        # 검사와 증가가 한 락 안에 있어야 한다 (T-078 회귀)
        limit, nthreads = 5, 20
        lim = server.RequestRateLimiter(limit=limit, window=60)
        barrier = threading.Barrier(nthreads)
        results = []

        def worker():
            barrier.wait()
            results.append(lim.allow("ip", now=1000.0)[0])

        threads = [threading.Thread(target=worker) for _ in range(nthreads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), nthreads)
        self.assertEqual(results.count(True), limit)

    def test_request_fail_max_exists_and_exceeds_rate_max(self):
        self.assertTrue(hasattr(server, "REQUEST_FAIL_MAX"))
        self.assertGreater(server.REQUEST_FAIL_MAX, server.REQUEST_RATE_MAX)


if __name__ == "__main__":
    unittest.main()
