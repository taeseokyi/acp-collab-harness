"""serve.py 검사 - 임시 폴더·임시 포트·가짜 함수. 표준 라이브러리만."""
import datetime
import errno
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

import serve  # noqa: E402

TOKEN = "t0k3n-test"


def fake_stt(path, mime, env):
    return "가짜 글 " + path.name


def fake_llm(prompt, env=None):
    return "가짜 답"


class Base(unittest.TestCase):
    token = None
    max_uploads = 2
    env = None

    def make_stt(self):
        return fake_stt

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = serve.make_server("127.0.0.1", 0, self.tmp.name, token=self.token,
                                        env=dict(self.env or {}), stt_fn=self.make_stt(), llm_run=fake_llm,
                                        max_uploads=self.max_uploads)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.tmp.cleanup()

    def req(self, method, path, body=None, headers=None, token=None):
        h = dict(headers or {})
        if token:
            h["Authorization"] = "Bearer " + token
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=h)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def jreq(self, method, path, obj=None, headers=None, token=None):
        h = dict(headers or {})
        body = None
        if obj is not None:
            body = json.dumps(obj).encode("utf-8")
            h["Content-Type"] = "application/json"
        status, hdr, raw = self.req(method, path, body, h, token)
        return status, json.loads(raw.decode("utf-8")) if raw else None

    def upload(self, data=b"RIFFfakeaudio", mime="audio/webm", client_id=None, extra=None, token=None):
        h = {"Content-Type": mime}
        if client_id:
            h["X-Client-Id"] = client_id
        h.update(extra or {})
        status, hdr, raw = self.req("POST", "/api/recordings", data, h, token)
        return status, json.loads(raw.decode("utf-8"))

    def wait_done(self, rid, token=None):
        end = time.time() + 10
        while time.time() < end:
            _, meta = self.jreq("GET", "/api/recordings/" + rid, token=token)
            if meta["status"] in ("done", "failed", "no-stt"):
                return meta
            time.sleep(0.05)
        self.fail("받아쓰기가 10초 안에 끝나지 않음")


class TestServe(Base):
    def test_health_open_even_with_token(self):
        status, body = self.jreq("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["auth"])
        self.assertEqual(body["stt"], "none")
        self.assertEqual(body["version"], "0.1")

    def test_static_index_and_types(self):
        status, hdr, raw = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", hdr["Content-Type"])
        self.assertTrue(raw)
        status, hdr, _ = self.req("GET", "/manifest.webmanifest")
        self.assertEqual(status, 200)
        self.assertIn("application/manifest+json", hdr["Content-Type"])
        status, hdr, _ = self.req("GET", "/sw.js")
        self.assertEqual(status, 200)
        self.assertEqual(hdr["Cache-Control"], "no-cache")
        self.assertIn("text/javascript", hdr["Content-Type"])

    def test_static_path_escape_refused(self):
        for p in ("/../serve.py", "/%2e%2e/serve.py", "/..%2fserve.py", "/%2e%2e%2fserve.py"):
            status, _, raw = self.req("GET", p)
            self.assertEqual(status, 404, p)
            self.assertNotIn(b"make_server", raw, p)

    def test_upload_transcribe_detail_and_stats(self):
        status, meta = self.upload(extra={"X-Duration-Ms": "1234", "X-Recorded-At": "2026-11-16T09:00:00+09:00"})
        self.assertEqual(status, 201)
        self.assertEqual(meta["status"], "pending")
        self.assertEqual(meta["duration_ms"], 1234)
        done = self.wait_done(meta["id"])
        self.assertEqual(done["status"], "done")
        self.assertTrue(done["transcript"].startswith("가짜 글 "))
        status, lst = self.jreq("GET", "/api/recordings")
        self.assertEqual(status, 200)
        self.assertEqual(len(lst["items"]), 1)
        self.assertEqual(lst["stats"]["count"], 1)
        self.assertEqual(lst["stats"]["done"], 1)
        status, lst = self.jreq("GET", "/api/recordings?q=%EA%B0%80%EC%A7%9C")
        self.assertEqual(len(lst["items"]), 1)
        status, lst = self.jreq("GET", "/api/recordings?q=zzz-none")
        self.assertEqual(lst["items"], [])

    def test_bad_duration_is_none(self):
        status, meta = self.upload(extra={"X-Duration-Ms": "abc"})
        self.assertEqual(status, 201)
        self.assertIsNone(meta["duration_ms"])

    def test_bad_recorded_at_uses_server_time(self):
        # R38-N4: 못 쓰는 X-Recorded-At(먼 미래·형식 깨짐·시간대 없음)은 거절하지 않고
        # 서버가 받은 시각으로 기록한다 - 날짜 폴더도 메타도 서버 시각 기준.
        bads = ("9999-12-31T23:59:59+00:00", "not-a-date", "2026-11-23T09:00:00")
        for i, bad in enumerate(bads):
            today = datetime.datetime.now().astimezone().strftime("%Y-%m-%d")
            status, meta = self.req_upload(bytes([i]) + b"rec", {"X-Recorded-At": bad})
            self.assertEqual(status, 201, bad)
            self.assertEqual(meta["recorded_at"], meta["created"], bad)
            self.assertEqual(meta["recorded_at"][:10], today, bad)
            self.wait_done(meta["id"])
            path = Path(self.tmp.name) / "transcripts" / today / (meta["id"] + ".txt")
            self.assertTrue(path.is_file(), bad)
        _, lst = self.jreq("GET", "/api/recordings")
        self.assertNotIn("9999", json.dumps(lst["stats"]["by_date"]))

    def test_past_recorded_at_with_offset_kept(self):
        status, meta = self.req_upload(b"ok", {"X-Recorded-At": "2026-11-16T09:00:00+09:00"})
        self.assertEqual(status, 201)
        self.assertEqual(meta["recorded_at"], "2026-11-16T09:00:00+09:00")

    def test_recorded_at_timezone_overflow_uses_server_time(self):
        # R39-N2: 범위 끝 + 시간대 변환이 OverflowError 를 내도 업로드는 201, 서버 시각으로 기록된다.
        bads = ("0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00")
        for i, bad in enumerate(bads):
            today = datetime.datetime.now().astimezone().strftime("%Y-%m-%d")
            status, meta = self.req_upload(bytes([i]) + b"ovf", {"X-Recorded-At": bad})
            self.assertEqual(status, 201, bad)
            self.assertEqual(meta["recorded_at"], meta["created"], bad)
            self.assertEqual(meta["recorded_at"][:10], today, bad)
            self.wait_done(meta["id"])

    def test_bad_date_filter_is_400(self):
        # R39-N1: fromisoformat 이 받아 주는 기본형(20261123)·ISO 주(2026-W48-1)는 400 이어야 한다
        # (정규식 없이는 200 + store 의 문자열 비교로 틀린 목록이 나왔다).
        for q in ("from=2026-13-40", "to=2026-13-40", "from=2026-02-30", "from=2026-1-1",
                  "from=20261123", "to=20261123", "from=2026-W48-1", "to=2026-W48-1"):
            status, body = self.jreq("GET", "/api/recordings?" + q)
            self.assertEqual(status, 400, q)
            self.assertIn("error", body)
        status, _ = self.jreq("GET", "/api/recordings?from=2026-01-01&to=2026-12-31")
        self.assertEqual(status, 200)

    def test_duplicate_client_id(self):
        s1, m1 = self.upload(client_id="c-1")
        s2, m2 = self.upload(client_id="c-1")
        self.assertEqual((s1, s2), (201, 200))
        self.assertEqual(m1["id"], m2["id"])
        self.wait_done(m1["id"])
        _, lst = self.jreq("GET", "/api/recordings")
        self.assertEqual(len(lst["items"]), 1)

    def test_too_large_413(self):
        with mock.patch.object(serve, "MAX_AUDIO_BYTES", 10):
            status, hdr, raw = self.req("POST", "/api/recordings", b"x" * 100, {"Content-Type": "audio/webm"})
        self.assertEqual(status, 413)
        self.assertIn("error", json.loads(raw.decode("utf-8")))
        _, lst = self.jreq("GET", "/api/recordings")
        self.assertEqual(lst["items"], [])

    def test_missing_length_and_unknown_mime(self):
        status, body = self.upload(mime="text/plain")
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/recordings")
        conn.putheader("Content-Type", "audio/webm")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()

    def test_audio_bytes_same(self):
        data = bytes(range(256)) * 4
        _, meta = self.upload(data=data, mime="audio/ogg; codecs=opus")
        status, hdr, raw = self.req("GET", "/api/recordings/%s/audio" % meta["id"])
        self.assertEqual(status, 200)
        self.assertEqual(hdr["Content-Type"], "audio/ogg")
        self.assertEqual(raw, data)

    def test_retry(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.server.store.set_transcript(meta["id"], "예전 글")
        status, again = self.jreq("POST", "/api/recordings/%s/retry" % meta["id"])
        self.assertEqual(status, 200)
        self.assertEqual(again["id"], meta["id"])
        end = time.time() + 10
        while time.time() < end and not (self.server.transcriber.idle()):
            time.sleep(0.05)
        done = self.wait_done(meta["id"])
        self.assertTrue(done["transcript"].startswith("가짜 글 "))
        status, _ = self.jreq("POST", "/api/recordings/r-20200101-000000-abcd/retry")
        self.assertEqual(status, 404)

    def test_delete_then_404(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        status, body = self.jreq("DELETE", "/api/recordings/" + meta["id"])
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual(self.jreq("GET", "/api/recordings/" + meta["id"])[0], 404)
        self.assertEqual(self.jreq("DELETE", "/api/recordings/" + meta["id"])[0], 404)
        self.assertEqual(self.req("GET", "/api/recordings/%s/audio" % meta["id"])[0], 404)

    def test_head_detail_does_not_delete(self):
        data = b"RIFFfakeaudio"
        _, meta = self.upload(data)
        self.wait_done(meta["id"])
        status, hdr, raw = self.req("HEAD", "/api/recordings/" + meta["id"])
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"")
        self.assertGreater(int(hdr["Content-Length"]), 0)  # GET 과 같은 머리(길이는 본문 기준)
        status, detail = self.jreq("GET", "/api/recordings/" + meta["id"])
        self.assertEqual(status, 200)
        self.assertEqual(detail["id"], meta["id"])
        status, _, audio = self.req("GET", "/api/recordings/%s/audio" % meta["id"])
        self.assertEqual((status, audio), (200, data))

    def test_head_list_same_as_get_not_upload(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        get_status, get_hdr, get_raw = self.req("GET", "/api/recordings")
        head_status, head_hdr, head_raw = self.req("HEAD", "/api/recordings")
        self.assertEqual((get_status, head_status), (200, 200))
        self.assertEqual(head_raw, b"")
        self.assertEqual(head_hdr["Content-Length"], get_hdr["Content-Length"])
        self.assertEqual(head_hdr["Content-Type"], get_hdr["Content-Type"])
        self.assertEqual(json.loads(get_raw.decode("utf-8"))["items"][0]["id"], meta["id"])
        self.assertEqual(self.jreq("GET", "/api/recordings/" + meta["id"])[0], 200)

    def test_head_foreign_origin_does_not_delete(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        status, _, raw = self.req("HEAD", "/api/recordings/" + meta["id"],
                                  headers={"Origin": "https://evil.example"})
        self.assertEqual((status, raw), (200, b""))
        self.assertEqual(self.jreq("GET", "/api/recordings/" + meta["id"])[0], 200)
        _, lst = self.jreq("GET", "/api/recordings")
        self.assertEqual([r["id"] for r in lst["items"]], [meta["id"]])
        self.assertEqual(self.req("GET", "/api/recordings/%s/audio" % meta["id"])[0], 200)

    def test_delete_still_deletes(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.assertEqual(self.jreq("DELETE", "/api/recordings/" + meta["id"])[0], 200)
        self.assertEqual(self.jreq("GET", "/api/recordings/" + meta["id"])[0], 404)
        self.assertEqual(self.req("HEAD", "/api/recordings/" + meta["id"])[0], 404)

    def test_ask_and_answers(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        status, ans = self.jreq("POST", "/api/ask", {"kind": "summary", "prompt": "", "ids": [meta["id"]]})
        self.assertEqual(status, 202)
        end = time.time() + 10
        got = None
        while time.time() < end:
            _, got = self.jreq("GET", "/api/answers/" + ans["id"])
            if got["status"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(got["status"], "done")
        self.assertEqual(got["answer"], "가짜 답")
        _, lst = self.jreq("GET", "/api/answers")
        self.assertEqual([a["id"] for a in lst["items"]], [ans["id"]])
        self.assertEqual(self.jreq("GET", "/api/answers/a-20200101-000000-abcd")[0], 404)
        self.assertEqual(self.jreq("DELETE", "/api/answers/" + ans["id"]), (200, {"ok": True}))
        self.assertEqual(self.jreq("GET", "/api/answers/" + ans["id"])[0], 404)
        self.assertEqual(self.jreq("DELETE", "/api/answers/" + ans["id"])[0], 404)
        self.assertEqual(self.jreq("GET", "/api/answers")[1]["items"], [])
        self.assertEqual(self.jreq("GET", "/api/recordings/" + meta["id"])[0], 200)   # 녹취는 그대로

    def test_ask_bad_kind_400(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        status, body = self.jreq("POST", "/api/ask", {"kind": "nope", "prompt": "", "ids": [meta["id"]]})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_ask_nonstring_kind_400_json_then_ok(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        for kind in ([], {}):
            status, body = self.jreq("POST", "/api/ask", {"kind": kind, "prompt": "", "ids": [meta["id"]]})
            self.assertEqual(status, 400, kind)
            self.assertIn("error", body)
        # 거절한 뒤에도 같은 연결 규약으로 정상 요청이 된다
        status, ans = self.jreq("POST", "/api/ask", {"kind": "summary", "prompt": "", "ids": [meta["id"]]})
        self.assertEqual(status, 202)
        self.assertIn("id", ans)

    def test_unknown_api_404_and_method_405(self):
        self.assertEqual(self.jreq("GET", "/api/nothing")[0], 404)
        status, hdr, _ = self.req("PUT", "/api/recordings", b"x")
        self.assertEqual(status, 405)
        self.assertEqual(self.req("POST", "/api/health", b"")[0], 405)
        self.assertEqual(self.req("OPTIONS", "/api/recordings")[0], 204)

    def test_foreign_origin_write_403(self):
        for origin in ("http://evil.example", "https://127.0.0.1:1"):
            status, _, _ = self.req("POST", "/api/recordings", b"abc",
                                    {"Content-Type": "audio/webm", "Origin": origin})
            self.assertEqual(status, 403, origin)
        _, lst = self.jreq("GET", "/api/recordings")
        self.assertEqual(lst["items"], [])
        # 바꾸는 메서드는 하나도 빠짐없이 출처 검사를 받는다 (405 보다 403 이 먼저)
        for method in ("PUT", "PATCH"):
            status, _, _ = self.req(method, "/api/recordings", b"abc",
                                    {"Content-Type": "audio/webm", "Origin": "https://evil.example"})
            self.assertEqual(status, 403, method)
        same = "http://127.0.0.1:%d" % self.port
        status, _, _ = self.req("POST", "/api/recordings", b"abc", {"Content-Type": "audio/webm", "Origin": same})
        self.assertEqual(status, 201)
        status, _, _ = self.req("POST", "/api/recordings", b"abd", {"Content-Type": "audio/webm", "Origin": "null"})
        self.assertEqual(status, 403)  # R33-N9: 토큰이 없으면 null 출처도 거절

    def test_location_header_in_detail(self):
        status, meta = self.upload(extra={"X-Location": "37.566500,126.978000,25"})
        self.assertEqual(status, 201)
        _, detail = self.jreq("GET", "/api/recordings/" + meta["id"])
        self.assertEqual(detail["location"], {"lat": 37.5665, "lon": 126.978, "accuracy": 25.0})

    def test_bad_location_is_none(self):
        for i, bad in enumerate(("abc", "91,0,5", "0,181,5", "1,2,-3", "1,2", "nan,1,1")):
            status, meta = self.req_upload(bytes([i]) + b"loc", {"X-Location": bad})
            self.assertEqual(status, 201, bad)
            self.assertIsNone(meta.get("location"), bad)
        status, meta = self.upload()
        self.assertIsNone(meta.get("location"))

    def req_upload(self, data, extra):
        h = {"Content-Type": "audio/webm"}
        h.update(extra)
        status, _, raw = self.req("POST", "/api/recordings", data, h)
        return status, json.loads(raw.decode("utf-8"))

    def raw_host(self, method, path, host, body=None, extra=None):
        h = dict(extra or {})
        h["Host"] = host
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=h)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def test_foreign_host_refused_without_token(self):
        for host in ("evil.example", "evil.example:%d" % self.port, "127.0.0.1.evil.example"):
            for path in ("/api/recordings", "/api/health", "/", "/app.js"):
                self.assertEqual(self.raw_host("GET", path, host)[0], 403, (host, path))
            st, _ = self.raw_host("POST", "/api/recordings", host, b"abc", {"Content-Type": "audio/webm"})
            self.assertEqual(st, 403, host)
            st, body = self.raw_host("GET", "/api/recordings", host)
            self.assertIn("이 주소로는 열 수 없습니다", body.decode("utf-8"))
        _, lst = self.jreq("GET", "/api/recordings")
        self.assertEqual(lst["items"], [])

    def test_loopback_hosts_ok_without_token(self):
        for host in ("127.0.0.1:%d" % self.port, "localhost:%d" % self.port, "[::1]:%d" % self.port,
                     "localhost", "::1"):
            self.assertEqual(self.raw_host("GET", "/api/recordings", host)[0], 200, host)
            self.assertEqual(self.raw_host("GET", "/", host)[0], 200, host)


class TestHealthWhitespaceLlmCmd(Base):
    """VOXLOG_LLM_CMD 가 공백뿐이면 llm_command 가 빈 목록 -> health 가 IndexError 로 끊기지 않아야 한다."""
    env = {"VOXLOG_LLM_CMD": "   "}

    def test_health_200_llm_false(self):
        status, body = self.jreq("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["llm"])
        self.assertIn("llm_error", body)


class TestHealthBadQuoteLlmCmd(Base):
    """따옴표가 안 맞는 VOXLOG_LLM_CMD 는 llm_command 가 ValueError -> health 는 200."""
    env = {"VOXLOG_LLM_CMD": 'claude -p "'}

    def test_health_200_llm_false(self):
        status, body = self.jreq("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["llm"])
        self.assertIn("llm_error", body)


class TestRetryUpload(Base):
    """N13 retry 409/resubmit · N14 업로드 흘려 쓰기·동시 수·디스크 여유."""

    def make_stt(self):
        self.calls = []
        self.gate = threading.Event()
        self.gate.set()
        self.started = threading.Event()

        def stt(path, mime, env):
            self.calls.append(path.name)
            self.started.set()
            self.gate.wait(10)
            return "글 " + str(len(self.calls))
        return stt

    def incoming(self):
        d = Path(self.tmp.name) / "incoming"
        return sorted(p.name for p in d.iterdir()) if d.exists() else []

    def drain(self):
        end = time.time() + 10
        while time.time() < end and not self.server.transcriber.idle():
            time.sleep(0.02)
        self.assertTrue(self.server.transcriber.idle())

    def test_retry_while_transcribing_409_once(self):
        self.gate.clear()
        _, meta = self.upload()
        self.assertTrue(self.started.wait(5))
        status, body = self.jreq("POST", "/api/recordings/%s/retry" % meta["id"])
        self.assertEqual(status, 409)
        self.assertIn("받아쓰는 중", body["error"])
        self.gate.set()
        self.drain()
        self.assertEqual(len(self.calls), 1)

    def test_retry_busy_by_transcriber_even_if_status_not_transcribing(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.drain()
        # 메타는 done 이지만 전사기가 잡고 있으면(큐에 있음) 409
        self.gate.clear()
        self.assertEqual(self.jreq("POST", "/api/recordings/%s/retry" % meta["id"])[0], 200)
        self.assertTrue(self.started.wait(5))
        self.server.store.set_status(meta["id"], "done")
        self.assertTrue(self.server.transcriber.busy(meta["id"]))
        status, _ = self.jreq("POST", "/api/recordings/%s/retry" % meta["id"])
        self.assertEqual(status, 409)
        self.gate.set()
        self.drain()
        self.assertEqual(len(self.calls), 2)

    def test_retry_resubmit_false_409(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.drain()
        with mock.patch.object(self.server.transcriber, "resubmit", return_value=False):
            status, _ = self.jreq("POST", "/api/recordings/%s/retry" % meta["id"])
        self.assertEqual(status, 409)

    def test_retry_resubmit_valueerror_404_json(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.drain()
        # get 으로 404 를 거른 뒤 resubmit 사이에 지워진 경우
        with mock.patch.object(self.server.transcriber, "resubmit",
                               side_effect=ValueError("없는 녹음입니다")):
            status, body = self.jreq("POST", "/api/recordings/%s/retry" % meta["id"])
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_retry_finished_runs_again(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.drain()
        status, again = self.jreq("POST", "/api/recordings/%s/retry" % meta["id"])
        self.assertEqual(status, 200)
        self.drain()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.wait_done(meta["id"])["status"], "done")

    def test_retry_after_set_transcript_oserror_is_200(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.drain()
        rid = meta["id"]
        store = self.server.store
        with mock.patch.object(store, "set_transcript", side_effect=OSError("disk full")):
            self.assertEqual(self.jreq("POST", "/api/recordings/%s/retry" % rid)[0], 200)
            self.drain()
        self.assertEqual(store.get(rid)["status"], "failed")
        # set_status 도 못 해서 transcribing 에 갇혀도 busy 가 아니면 retry 가 통한다
        store.set_status(rid, "transcribing")
        self.assertFalse(self.server.transcriber.busy(rid))
        n = len(self.calls)
        status, _ = self.jreq("POST", "/api/recordings/%s/retry" % rid)
        self.assertEqual(status, 200)
        self.drain()
        self.assertEqual(len(self.calls), n + 1)
        self.assertEqual(self.wait_done(rid)["status"], "done")

    def test_upload_leaves_no_incoming_litter(self):
        self.assertEqual(self.upload()[0], 201)
        self.assertEqual(self.upload(client_id="c1")[0], 201)
        status, dup = self.upload(client_id="c1")
        self.assertEqual((status, dup.get("duplicate")), (200, True))
        self.assertEqual(self.upload(mime="text/plain")[0], 400)
        self.assertEqual(self.upload(data=b"")[0], 400)
        self.drain()
        self.assertEqual(self.incoming(), [])

    def test_truncated_body_400_no_litter(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/recordings")
        conn.putheader("Content-Type", "audio/webm")
        conn.putheader("Content-Length", "200000")
        conn.endheaders()
        conn.send(b"x" * 70000)
        conn.sock.shutdown(1)  # 쓰기 끝: 서버는 덜 온 본문을 본다
        resp = conn.getresponse()
        self.assertEqual(resp.status, 400)
        resp.read()
        conn.close()
        self.assertEqual(self.incoming(), [])
        self.assertEqual(self.jreq("GET", "/api/recordings")[1]["items"], [])

    def test_no_slot_503(self):
        slots = self.server.upload_slots
        self.assertTrue(slots.acquire(blocking=False) and slots.acquire(blocking=False))
        try:
            status, hdr, raw = self.req("POST", "/api/recordings", b"RIFFx", {"Content-Type": "audio/webm"})
        finally:
            slots.release()
            slots.release()
        self.assertEqual(status, 503)
        self.assertEqual(hdr.get("Retry-After"), "5")
        self.assertEqual(hdr.get("Connection"), "close")
        self.assertEqual(self.upload()[0], 201)  # 자리는 돌려받음
        self.assertEqual(self.incoming(), [])

    def test_disk_low_507(self):
        self.server.disk_free = lambda: 100 * 1024 * 1024 + 4  # 본문 5바이트 + 100MB 에 모자람
        status, hdr, raw = self.req("POST", "/api/recordings", b"RIFFx", {"Content-Type": "audio/webm"})
        self.assertEqual(status, 507)
        self.assertEqual(hdr.get("Connection"), "close")
        self.server.disk_free = lambda: 100 * 1024 * 1024 + 5
        self.assertEqual(self.upload(data=b"RIFFx")[0], 201)
        self.assertEqual(self.incoming(), [])
        # 507 뒤에도 자리가 새지 않음(자리 2개로 507 을 3번 받고도 업로드가 됨)
        self.server.disk_free = lambda: 0
        for _ in range(3):
            self.assertEqual(self.upload()[0], 507)
        self.server.disk_free = lambda: 10 ** 12
        self.assertEqual(self.upload()[0], 201)

    def test_list_responds_during_slow_upload(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/recordings")
        conn.putheader("Content-Type", "audio/webm")
        conn.putheader("Content-Length", "200000")
        conn.endheaders()
        conn.send(b"x" * 1000)  # 나머지는 안 보냄: 업로드가 진행 중
        try:
            time.sleep(0.2)
            t0 = time.time()
            status, body = self.jreq("GET", "/api/recordings")
            self.assertEqual(status, 200)
            self.assertLess(time.time() - t0, 2)
        finally:
            conn.close()

    def test_slow_upload_408_frees_slot(self):
        self.server.upload_grace = 1
        self.server.upload_min_rate = 10 ** 9  # 마감 ~1초
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/recordings")
        conn.putheader("Content-Type", "audio/webm")
        conn.putheader("Content-Length", "5000000")
        conn.endheaders()
        status = None
        t0 = time.time()
        try:
            for _ in range(40):  # 마감(1초)보다 느리게 조금씩
                conn.send(b"x" * 100)
                time.sleep(0.1)
        except OSError:
            pass  # 서버가 먼저 닫음
        try:
            resp = conn.getresponse()
            status = resp.status
            self.assertIn("너무 느립니다", json.loads(resp.read().decode("utf-8"))["error"])
        except (OSError, http.client.HTTPException):
            pass
        finally:
            conn.close()
        self.assertLess(time.time() - t0, 6)
        self.assertIn(status, (408, None))
        self.assertEqual(self.incoming(), [])
        self.server.upload_grace = 30
        self.server.upload_min_rate = 16 * 1024
        self.assertEqual(self.upload()[0], 201)
        self.assertEqual(self.upload()[0], 201)
        self.assertEqual(self.upload()[0], 201)  # 자리가 새지 않음
        self.assertEqual(self.incoming(), [])

    def test_normal_speed_upload_201(self):
        self.server.upload_grace = 1
        self.assertEqual(self.upload(data=b"RIFF" + b"a" * 200000)[0], 201)
        self.assertEqual(self.incoming(), [])

    def test_store_oserror_507_500(self):
        store = self.server.store
        for err, want in ((errno.ENOSPC, 507), (errno.EIO, 500)):
            with mock.patch.object(store, "add_recording_file", side_effect=OSError(err, "boom")):
                status, hdr, raw = self.req("POST", "/api/recordings", b"RIFFx",
                                            {"Content-Type": "audio/webm"})
            self.assertEqual(status, want)
            self.assertEqual(hdr.get("Connection"), "close")
            self.assertEqual(self.incoming(), [])
            self.assertEqual(self.upload()[0], 201)
        self.assertEqual(self.incoming(), [])

    def _trickle(self, declared, chunk, pause, count, limit=6):
        """긴 길이를 선언하고 chunk 바이트씩 count 번 보낸 뒤 응답을 기다린다. (상태, 걸린 초)"""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=limit)
        conn.putrequest("POST", "/api/recordings")
        conn.putheader("Content-Type", "audio/webm")
        conn.putheader("Content-Length", str(declared))
        conn.endheaders()
        t0 = time.time()
        status = None
        try:
            try:
                for _ in range(count):
                    conn.send(b"x" * chunk)
                    time.sleep(pause)
            except OSError:
                pass  # 서버가 먼저 닫음
            try:
                resp = conn.getresponse()
                status = resp.status
                resp.read()
            except (OSError, http.client.HTTPException):
                pass
        finally:
            conn.close()
        return status, time.time() - t0

    def test_deadline_counts_received_bytes_not_declared(self):
        self.server.upload_grace = 1  # min_rate 는 기본 16KB/s: 10MB 선언이면 옛 공식은 ~640초
        status, took = self._trickle(10 * 1024 * 1024, 10, 0, 1)  # 10바이트 보내고 멈춤
        self.assertEqual(status, 408)
        self.assertLess(took, 3.5)
        self.assertEqual(self.incoming(), [])
        self.server.upload_grace = 30
        for _ in range(3):
            self.assertEqual(self.upload()[0], 201)  # 자리가 반납됨

    def test_trickle_below_min_rate_408(self):
        self.server.upload_grace = 1
        self.server.upload_min_rate = 1000  # 초당 1000B 요구, 실제는 ~100B/s
        status, took = self._trickle(1024 * 1024, 10, 0.1, 60)
        self.assertEqual(status, 408)
        self.assertLess(took, 4)
        self.assertEqual(self.incoming(), [])
        self.assertEqual(self.upload()[0], 201)

    def test_stalled_upload_with_grace_left_is_408_not_400(self):
        # 여유가 읽기 timeout 보다 길게 남은 채 회선이 멈춤: 연결은 살아 있으므로 408(다시 올림)이지 400(영구 실패)이 아니다
        self.server.upload_grace = 30
        with mock.patch.object(serve.Handler, "timeout", 0.5):
            status, took = self._trickle(1024 * 1024, 1000, 0, 1)
        self.assertEqual(status, 408)
        self.assertLess(took, 4)
        self.assertEqual(self.incoming(), [])
        self.assertEqual(self.upload()[0], 201)

    def test_upload_above_min_rate_201(self):
        self.server.upload_grace = 1
        self.server.upload_min_rate = 1000
        body = b"RIFF" + b"a" * 3996
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/recordings")
        conn.putheader("Content-Type", "audio/webm")
        conn.putheader("Content-Length", str(len(body) * 10))
        conn.endheaders()
        try:
            for i in range(10):  # 초당 ~40KB, 요구(1KB/s)보다 훨씬 빠름
                conn.send(body if i == 0 else b"b" * len(body))
                time.sleep(0.1)
            resp = conn.getresponse()
            self.assertEqual(resp.status, 201)
            resp.read()
        finally:
            conn.close()
        self.assertEqual(self.incoming(), [])

    def test_incoming_mkdir_oserror_507_500(self):
        store = self.server.store
        for err, want in ((errno.ENOSPC, 507), (errno.EDQUOT, 507), (errno.EACCES, 500)):
            with mock.patch.object(store, "incoming_path", side_effect=OSError(err, "boom")):
                status, hdr, raw = self.req("POST", "/api/recordings", b"RIFFx",
                                            {"Content-Type": "audio/webm"})
            self.assertEqual(status, want)
            self.assertIn("error", json.loads(raw.decode("utf-8")))
            self.assertEqual(self.upload()[0], 201)  # 자리가 새지 않고 다음 업로드 정상
        self.assertEqual(self.incoming(), [])


class TestServeToken(Base):
    token = TOKEN

    def test_token_required_except_health(self):
        status, body = self.jreq("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["auth"])
        self.assertEqual(self.jreq("GET", "/api/recordings")[0], 401)
        self.assertEqual(self.jreq("GET", "/api/recordings", token="wrong")[0], 401)
        self.assertEqual(self.jreq("GET", "/api/nothing")[0], 401)
        status, lst = self.jreq("GET", "/api/recordings", token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(lst["items"], [])
        status, _ = self.upload(token=TOKEN)
        self.assertEqual(status, 201)
        self.assertEqual(self.upload()[0], 401)
        # 정적 파일은 토큰 없이 열림(앱 껍데기)
        self.assertEqual(self.req("GET", "/")[0], 200)

    def test_foreign_host_and_null_origin_ok_with_token(self):
        h = {"Authorization": "Bearer " + TOKEN, "Host": "evil.example"}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/api/recordings", headers=h)
            self.assertEqual(conn.getresponse().status, 200)
        finally:
            conn.close()
        status, _ = self.upload(token=TOKEN, extra={"Origin": "null"})
        self.assertEqual(status, 201)


class TestMain(unittest.TestCase):
    def test_non_loopback_without_token_refused(self):
        env = {k: v for k, v in os.environ.items() if k != "VOXLOG_TOKEN"}
        proc = subprocess.run([sys.executable, str(PROJECT / "serve.py"), "--host", "0.0.0.0", "--port", "0"],
                              capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("토큰", proc.stderr)


class SettingsTest(unittest.TestCase):
    def test_settings_file_gives_voxlog_values_and_environment_wins(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "settings.json"
            f.write_text(json.dumps({"VOXLOG_STT_URL": "https://a/v1", "VOXLOG_STT_MODEL": "m",
                                     "PATH": "/evil", "VOXLOG_X": 3, "VOXLOG_EMPTY": ""}), encoding="utf-8")
            env = serve.load_settings(f, environ={"PATH": "/bin", "VOXLOG_STT_MODEL": "from-env"})
            self.assertEqual(env, {"VOXLOG_STT_URL": "https://a/v1", "VOXLOG_STT_MODEL": "from-env", "PATH": "/bin"})
            f.write_text("not json", encoding="utf-8")
            self.assertEqual(serve.load_settings(f, environ={}), {})
            self.assertEqual(serve.load_settings(Path(d) / "none.json", environ={"A": "b"}), {"A": "b"})


if __name__ == "__main__":
    unittest.main()
