# -*- coding: utf-8 -*-
"""T-051 상세조회 계약 테스트 (요청 8d8d, 슬롯 S2).

표준 라이브러리 unittest 만 사용한다.
HTTP 계약은 127.0.0.1 의 임시 포트(0번)에 띄운 서버로만 검증한다.

`run_detail` 이 아직 없을 때의 스킵 조건은 `hasattr(reader, "run_detail")`
하나뿐이다. 그 외 실패를 스킵으로 덮지 않는다. 서버의 `/api/runs/` 라우트가
없을 때는 서버 계약 테스트만 스킵한다. `collect_graphs`/`collect_state`
회귀 테스트는 아직 고쳐지지 않았으면 실패로 남긴다.
"""

import datetime
import http.server
import inspect
import json
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

try:
    from aimem_monitor import GRAPH_DIR, SERVER_KEYS, STATE_KEYS
    from aimem_monitor import reader, server
except ImportError:
    reader = None
    server = None
    GRAPH_DIR = ".aimem/graph"
    STATE_KEYS = {}
    SERVER_KEYS = {}


RUN_ID = "20261109-172618-S3"

DETAIL_KEYS = (
    "id", "found", "slot", "harness", "model", "label", "status", "rc", "elapsed_s",
    "started", "ended", "brief", "report", "stderr_tail", "paths", "errors",
)
#: 서버가 `reader.run_events()` 로 덧붙이는 키 - reader.run_detail 자체는 16개, `/api/runs/<id>` 는 17개
SERVER_DETAIL_KEYS = DETAIL_KEYS + ("events",)
PATH_KEYS = {"dir", "out", "err", "rc", "brief"}
VALID_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-S[0-9]+(-[0-9]+)?$")


def add_run(
    root,
    run_id,
    *,
    slot="S3",
    harness="opencode",
    model="test-model",
    label="상세 계약 테스트",
    started="2026-11-09T17:26:18",
    rc=None,
    elapsed=None,
    out=None,
    err=None,
    brief=None,
    pid=None,
):
    runs_dir = root / ".aimem" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": run_id,
        "slot": slot,
        "harness": harness,
        "model": model,
        "label": label,
        "rev": 110,
        "write": ["tests/test_aimem_monitor_detail.py"],
        "started": started,
    }
    if pid is not None:
        meta["pid"] = pid
    (runs_dir / f"{run_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
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
    if err is not None:
        (runs_dir / f"{run_id}.err").write_text(err, encoding="utf-8")
    if brief is not None:
        (runs_dir / f"{run_id}.brief.md").write_text(brief, encoding="utf-8")


def snapshot_runs(runs_dir):
    return sorted(
        (p.name, p.stat().st_mtime_ns)
        for p in runs_dir.iterdir()
    )


def detail_shape_ok(test, detail, served=False):
    test.assertIsInstance(detail, dict)
    test.assertEqual(set(detail), set(SERVER_DETAIL_KEYS if served else DETAIL_KEYS))
    if served:
        test.assertIsInstance(detail["events"], str)    # 세션 실행의 사건 보기 (옛 실행은 빈 문자열)

    test.assertIsInstance(detail["id"], str)
    test.assertIsInstance(detail["found"], bool)
    test.assertTrue(
        detail["rc"] is None
        or (isinstance(detail["rc"], int) and not isinstance(detail["rc"], bool))
    )
    test.assertTrue(
        detail["elapsed_s"] is None
        or (isinstance(detail["elapsed_s"], int) and not isinstance(detail["elapsed_s"], bool))
    )
    for key in ("started", "ended"):
        test.assertTrue(detail[key] is None or isinstance(detail[key], str))
    for key in ("slot", "harness", "model", "label", "status",
                "brief", "report", "stderr_tail"):
        test.assertIsInstance(detail[key], str)
    test.assertIsInstance(detail["paths"], dict)
    test.assertEqual(set(detail["paths"]), PATH_KEYS)
    test.assertIsInstance(detail["errors"], list)
    for item in detail["errors"]:
        test.assertIsInstance(item, str)


class TestRunDetailContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        add_run(
            self.root,
            RUN_ID,
            rc=0,
            elapsed=30,
            out="DONE 보고 본문\n둘째 줄",
            err="stderr 한 줄",
            brief="지시 본문",
        )
        self.real_root = pathlib.Path(__file__).resolve().parents[1]

    def tearDown(self):
        self.tmp.cleanup()

    def require_run_detail(self):
        if not hasattr(reader, "run_detail"):
            self.skipTest("run_detail 미구현")

    def test_top_level_keys_and_types(self):
        self.require_run_detail()
        detail = reader.run_detail(RUN_ID, self.root)
        detail_shape_ok(self, detail)
        self.assertTrue(detail["found"])
        self.assertEqual(detail["id"], RUN_ID)
        self.assertEqual(detail["rc"], 0)
        self.assertGreater(detail["elapsed_s"], 0)
        self.assertNotEqual(detail["report"], "")
        self.assertIsInstance(detail["started"], str)
        self.assertIsInstance(detail["ended"], str)

    def test_missing_id_has_found_false_and_all_keys(self):
        self.require_run_detail()
        detail = reader.run_detail("20990101-000000-S9", self.root)
        detail_shape_ok(self, detail)
        self.assertFalse(detail["found"])

    def test_invalid_ids_never_raise(self):
        self.require_run_detail()
        bad_ids = [
            "../../etc/passwd",
            "",
            None,
            "x" * 10000,
            "20261109-172618-S3/../..",
        ]
        for run_id in bad_ids:
            with self.subTest(run_id=repr(run_id)[:80]):
                try:
                    detail = reader.run_detail(run_id, self.root)
                except Exception as e:
                    self.fail(
                        f"run_detail({run_id!r}) 가 예외를 던졌습니다: "
                        f"{type(e).__name__}: {e}"
                    )
                detail_shape_ok(self, detail)
                self.assertFalse(detail["found"])
                # 계약: 잘못된 id 는 found=False + errors 비어있지 않음.
                self.assertTrue(detail["errors"])

    def test_valid_id_format_regex(self):
        for value in (
            "20261109-172618-S3",
            "20261109-172618-S3-1",
            "20261109-172618-S30",
        ):
            self.assertTrue(VALID_ID_RE.fullmatch(value), value)
        for value in (
            "",
            "20261109-172618-S3/../..",
            "20261109-172618-s3",
            "20261109-172618-S3-",
            "2026110-172618-S3",
        ):
            self.assertFalse(VALID_ID_RE.fullmatch(value), value)

    def test_real_record_reads_rc_and_report(self):
        self.require_run_detail()
        run_json = self.real_root / ".aimem" / "runs" / f"{RUN_ID}.json"
        if not run_json.exists():
            self.skipTest(f"실제 기록 없음: {RUN_ID}")

        detail = reader.run_detail(RUN_ID)  # 기본 root = 저장소 루트
        detail_shape_ok(self, detail)
        self.assertTrue(detail["found"])
        self.assertEqual(detail["rc"], 0)
        self.assertGreater(detail["elapsed_s"], 0)
        self.assertNotEqual(detail["report"], "")

    def test_read_only_before_after(self):
        self.require_run_detail()
        runs_dir = self.real_root / ".aimem" / "runs"
        run_json = runs_dir / f"{RUN_ID}.json"
        if not run_json.exists():
            self.skipTest(f"실제 기록 없음: {RUN_ID}")

        before = snapshot_runs(runs_dir)
        reader.run_detail(RUN_ID)
        for bad_id in ("../../etc/passwd", "", None, "x" * 10000,
                       "20261109-172618-S3/../.."):
            reader.run_detail(bad_id)
        after = snapshot_runs(runs_dir)
        self.assertEqual(before, after, "run_detail 이 .aimem/runs 를 바꿨습니다")


def handler_has_runs_route():
    if server is None:
        return False
    try:
        source = inspect.getsource(server.Handler)
    except (OSError, TypeError):
        return False
    return "/api/runs" in source


class TestServerContract(unittest.TestCase):
    def setUp(self):
        if server is None:
            self.skipTest("server.py 미구현")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        add_run(
            self.root,
            RUN_ID,
            rc=0,
            elapsed=30,
            out="DONE 보고 본문\n둘째 줄",
            err="stderr 한 줄",
            brief="지시 본문",
        )

        self.runs_route = handler_has_runs_route()

        class FakeServer:
            server_address = ("127.0.0.1", 0)
            server_name = "localhost"
            protocol_version = "HTTP/1.1"

        class QuietHandler(server.Handler):
            root = self.root

            def log_message(self, fmt, *args):
                pass

        self.handler_cls = QuietHandler
        self.fake_server = FakeServer()
        self.httpd = None
        self.thread = None
        self.port = None
        self.no_tcp_mode = False
        try:
            self.httpd = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), QuietHandler
            )
        except PermissionError:
            # 이 샌드박스는 AF_INET 소켓 생성과 send 를 금지합니다. 임시 포트 대신
            # 같은 Handler 를 파이프 위에서 돌려 HTTP 계약을 검증한다.
            self.no_tcp_mode = True
        if not self.no_tcp_mode:
            self.port = self.httpd.server_address[1]
            self.thread = threading.Thread(
                target=self.httpd.serve_forever, daemon=True
            )
            self.thread.start()

    def tearDown(self):
        if getattr(self, "httpd", None) is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            if getattr(self, "thread", None) is not None:
                self.thread.join(timeout=2)
        if getattr(self, "tmp", None) is not None:
            self.tmp.cleanup()

    def get(self, path):
        if self.no_tcp_mode:
            return self.get_over_pipes(path)
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def get_over_pipes(self, path):
        req_r, req_w = os.pipe()
        resp_r, resp_w = os.pipe()

        class PipeConnection:
            def __init__(self, read_fd, write_fd):
                self.read_fd = read_fd
                self.write_fd = write_fd

            def makefile(self, mode, buffering=-1):
                fd = self.read_fd if "r" in mode else self.write_fd
                return os.fdopen(os.dup(fd), mode, buffering)

            def sendall(self, data):
                os.write(self.write_fd, data)

            def close(self):
                for fd in (self.read_fd, self.write_fd):
                    try:
                        os.close(fd)
                    except OSError:
                        pass

        request = (
            f"GET {path} HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        os.write(req_w, request.encode("ascii"))
        os.close(req_w)
        try:
            # BaseHTTPRequestHandler 는 생성자에서 바로 handle() 을 부른다.
            # 요청을 먼저 파이프에 넣은 뒤 생성한다.
            self.handler_cls(
                PipeConnection(req_r, resp_w),
                ("127.0.0.1", 0),
                self.fake_server,
            )
        finally:
            os.close(resp_w)

        with os.fdopen(resp_r, "rb") as stream:
            raw = stream.read()
        os.close(req_r)

        head, _, body = raw.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        status = int(lines[0].decode("ascii", "replace").split()[1])
        headers = {}
        for line in lines[1:]:
            if not line:
                continue
            key, value = line.decode("latin-1").split(":", 1)
            headers[key.strip()] = value.strip()
        length = int(headers.get("Content-Length", "0"))
        body = body[:length]
        return status, headers, body

    def require_runs_route(self):
        if not self.runs_route:
            self.skipTest("server 에 /api/runs/ 라우트가 없음")

    def test_valid_id_200_json_detail(self):
        self.require_runs_route()
        status, headers, raw = self.get("/api/runs/" + RUN_ID)
        self.assertEqual(status, 200)
        ctype = headers.get("Content-Type", "").split(";")[0].strip()
        self.assertEqual(ctype, "application/json")
        body = json.loads(raw.decode("utf-8"))
        detail_shape_ok(self, body, served=True)
        self.assertTrue(body["found"])
        self.assertEqual(body["id"], RUN_ID)
        self.assertEqual(body["rc"], 0)

    def test_missing_id_404_with_error(self):
        self.require_runs_route()
        status, _, raw = self.get("/api/runs/20990101-000000-S9")
        self.assertEqual(status, 404)
        body = json.loads(raw.decode("utf-8"))
        self.assertIsInstance(body, dict)
        self.assertIn("error", body)
        self.assertIsInstance(body["error"], str)
        self.assertNotEqual(body["error"], "")

    def test_invalid_id_not_500(self):
        self.require_runs_route()
        bad_ids = [
            "../../etc/passwd",
            "20261109-172618-S3/../..",
            "",
        ]
        for bad_id in bad_ids:
            path = "/api/runs/" + urllib.parse.quote(bad_id, safe="")
            with self.subTest(bad_id=bad_id):
                status, _, _ = self.get(path)
                self.assertIn(status, (400, 404), f"잘못된 id 에 {status} 응답")

class TestGraphAndStateDefense(unittest.TestCase):
    def setUp(self):
        if server is None:
            self.skipTest("server.py 미구현")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.graph_dir = self.root / GRAPH_DIR
        self.graph_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_graph(self, name, payload):
        (self.graph_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_collect_graphs_bad_nodes_list(self):
        self.write_graph("bad-nodes.json", {"nodes": ["x"]})
        errors = []
        try:
            result = server.collect_graphs(self.root, errors)
        except Exception as e:
            self.fail(
                "collect_graphs 가 모양이 틀린 그래프에서 예외를 던졌습니다: "
                f"{type(e).__name__}: {e}"
            )
        self.assertIsInstance(result, list)
        self.assertEqual(len(errors), 1, f"errors: {errors}")
        self.assertIsInstance(errors[0], str)

    def test_collect_graphs_bad_attempts(self):
        self.write_graph(
            "bad-attempts.json",
            {"nodes": [{"attempts": [None]}]},
        )
        errors = []
        try:
            result = server.collect_graphs(self.root, errors)
        except Exception as e:
            self.fail(
                "collect_graphs 가 모양이 틀린 attempts 에서 예외를 던졌습니다: "
                f"{type(e).__name__}: {e}"
            )
        self.assertIsInstance(result, list)
        # attempts 원소가 dict 가 아닌 것은 "읽을 수 없는 파일"이 아니라
        # "마지막 run id 를 모르는 노드"다. 그래프를 통째로 버리면 멀쩡한
        # 나머지 노드까지 화면에서 사라지므로 노드는 살려 둔다.
        # errors 건수는 단언하지 않는다 (0 이든 1 이든 허용).
        self.assertEqual(len(result), 1, f"result: {result}")
        item = result[0]
        self.assertEqual(item["id"], "bad-attempts")
        self.assertEqual(len(item["nodes"]), 1, f"nodes: {item['nodes']}")
        node = item["nodes"][0]
        self.assertIsNone(node["last_run"])
        self.assertIsInstance(node["attempts"], int)

    def test_collect_state_survives_bad_graph(self):
        self.write_graph("bad-nodes.json", {"nodes": ["x"]})
        try:
            state = server.collect_state(self.root)
        except Exception as e:
            self.fail(
                "collect_state 가 모양이 틀린 그래프에서 예외를 던졌습니다: "
                f"{type(e).__name__}: {e}"
            )
        self.assertIsInstance(state, dict)
        self.assertIn("graphs", state)
        self.assertIsInstance(state.get("errors"), list)
        self.assertTrue(state["errors"])

    def test_collect_state_failure_branch_keys_match_normal(self):
        expected = set(STATE_KEYS) | set(SERVER_KEYS)
        normal = server.collect_state(self.root)
        self.assertEqual(set(normal), expected, "정상 분기 키 집합이 계약과 다릅니다")

        with mock.patch.object(reader, "collect", side_effect=RuntimeError("boom")):
            raised = server.collect_state(self.root)
        self.assertIsInstance(raised, dict)
        self.assertEqual(set(raised), expected, "reader.collect 예외 분기 키 집합이 다릅니다")
        self.assertIsInstance(raised.get("errors"), list)
        self.assertTrue(raised["errors"])

        with mock.patch.object(reader, "collect", return_value=["not", "dict"]):
            non_dict = server.collect_state(self.root)
        self.assertIsInstance(non_dict, dict)
        self.assertEqual(
            set(non_dict), expected,
            "reader.collect 가 dict 가 아닌 값을 돌려준 분기의 키 집합이 다릅니다",
        )
        self.assertIsInstance(non_dict.get("errors"), list)
        self.assertTrue(non_dict["errors"])


if __name__ == "__main__":
    unittest.main()
