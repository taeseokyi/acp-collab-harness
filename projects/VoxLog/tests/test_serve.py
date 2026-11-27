"""serve.py 검사 - 임시 폴더·임시 포트·가짜 함수. 표준 라이브러리만."""
import datetime
import errno
import http.client
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

import serve  # noqa: E402

TOKEN = "t0k3n-test"


def fake_stt(path, mime, env):
    return "가짜 글 " + path.name


FAKE_TAGS = "회의\n가짜 태그\n- 세번째"


def fake_llm(prompt, env=None):
    if prompt.startswith("이 녹취에 붙일 주제 태그"):
        return FAKE_TAGS
    return "가짜 답"


def llm_true():
    return True


def llm_false():
    return False


class FakeJobPostOpener:
    """맡기기(POST)를 세는 가짜 받아쓰기 서버. 조회는 어떤 작업 id 든 done 으로 답한다."""

    def __init__(self):
        self.posts = []
        self.gets = []

    def __call__(self, req, timeout):
        if req.get_method() == "POST":
            self.posts.append(req)
            jid = "job%d" % len(self.posts)
            return json.dumps({"id": jid, "status": "queued"}).encode("utf-8")
        if req.get_method() == "DELETE":
            return json.dumps({"id": "deleted", "status": "deleted"}).encode("utf-8")
        self.gets.append(req.full_url.rsplit("/", 1)[1])
        return json.dumps({"status": "done", "result": {"text": "받아 적음"}}).encode("utf-8")


class Base(unittest.TestCase):
    token = None
    max_uploads = 2
    env = None
    llm_ready = staticmethod(llm_false)

    def make_stt(self):
        return fake_stt

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = serve.make_server("127.0.0.1", 0, self.tmp.name, token=self.token,
                                        env=dict(self.env or {}), stt_fn=self.make_stt(), llm_run=fake_llm,
                                        max_uploads=self.max_uploads, llm_ready=self.llm_ready)
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

    def wait_asker_idle(self):
        end = time.time() + 10
        while time.time() < end:
            if self.server.asker.idle():
                return
            time.sleep(0.05)
        self.fail("Asker 가 10초 안에 비지 않음")

    def wait_autotag(self, rid, token=None):
        end = time.time() + 10
        while time.time() < end:
            _, meta = self.jreq("GET", "/api/recordings/" + rid, token=token)
            if meta.get("autotag") in ("done", "failed"):
                return meta
            time.sleep(0.05)
        self.fail("자동 태그가 10초 안에 끝나지 않음")


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

    def test_list_status_filter(self):
        # R41-N3: status 는 meta 의 status 와 정확히 같은 것만 남긴다
        _, a = self.upload()
        self.wait_done(a["id"])
        _, b = self.upload()
        self.wait_done(b["id"])
        self.server.store.set_status(b["id"], "failed")
        _, done = self.jreq("GET", "/api/recordings?status=done")
        self.assertEqual([r["id"] for r in done["items"]], [a["id"]])
        _, failed = self.jreq("GET", "/api/recordings?status=failed")
        self.assertEqual([r["id"] for r in failed["items"]], [b["id"]])
        _, none = self.jreq("GET", "/api/recordings?status=no-such-status")
        self.assertEqual(none["items"], [])

    def test_list_limit_zero_is_one(self):
        # R41-N3: limit 은 1 밑으로 내려가지 않는다 (0 -> 1건)
        for _ in range(2):
            self.upload()
        status, body = self.jreq("GET", "/api/recordings?limit=0")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["items"]), 1)

    def test_list_limit_not_integer_is_400(self):
        status, body = self.jreq("GET", "/api/recordings?limit=abc")
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertEqual(self.jreq("GET", "/api/recordings?limit=2.5")[0], 400)

    def test_list_limit_capped_at_thousand(self):
        # R41-N3: limit 상한은 1000 - 넘겨도 1000건까지만
        for i in range(1001):
            self.server.store.add_recording(b"x", "audio/webm",
                                            recorded_at="2026-01-01T00:00:00")
        status, body = self.jreq("GET", "/api/recordings?limit=99999")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["items"]), 1000)
        status, body = self.jreq("GET", "/api/recordings?limit=1000")
        self.assertEqual(len(body["items"]), 1000)

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

    def test_delete_running_answer_409(self):
        # R41-N6: 아직 묻는 중(running)인 답은 404 가 아니라 409 로 거절하고 남긴다
        ans = self.server.store.add_answer("summary", "", ["r-20200101-000000-abcd"])
        self.assertEqual(ans["status"], "running")
        status, body = self.jreq("DELETE", "/api/answers/" + ans["id"])
        self.assertEqual(status, 409)
        self.assertIn("error", body)
        self.assertEqual(self.jreq("GET", "/api/answers/" + ans["id"])[0], 200)

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


class TestSttOptions(Base):
    """R51 G-108: GET/PUT /api/stt-options 와 retry 의 옵션 본문."""

    def make_stt(self):
        self.calls = []

        def stt(path, mime, env):
            self.calls.append(path.name)
            return "가짜 글 " + str(len(self.calls))
        return stt

    def drain(self):
        end = time.time() + 10
        while time.time() < end and not self.server.transcriber.idle():
            time.sleep(0.02)
        self.assertTrue(self.server.transcriber.idle())

    def test_get_defaults_and_choices(self):
        status, body = self.jreq("GET", "/api/stt-options")
        self.assertEqual(status, 200)
        self.assertEqual(body["options"], {})
        self.assertEqual(body["choices"]["preprocess"],
                         ["none", "basic", "level", "dereverb", "denoise"])
        self.assertEqual(body["choices"]["speakers_max"], 20)
        self.assertEqual(body["choices"]["context_max"], 4000)
        self.assertEqual(body["stt"], "none")

    def test_put_saves_get_shows_and_file_holds_it(self):
        opts = {"preprocess": "denoise", "num_speakers": 2,
                "context": "회의 이름", "auto": True, "review": False}
        status, body = self.jreq("PUT", "/api/stt-options", {"options": opts})
        self.assertEqual(status, 200)
        self.assertEqual(body["options"], opts)
        status, got = self.jreq("GET", "/api/stt-options")
        self.assertEqual(status, 200)
        self.assertEqual(got["options"], opts)
        path = Path(self.tmp.name) / "stt_options.json"
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text("utf-8")), opts)
        raw = json.dumps(got)
        for key in ("VOXLOG_STT_URL", "VOXLOG_STT_MODEL", "VOXLOG_STT_API_KEY"):
            self.assertNotIn(key, raw)

    def test_put_bad_value_400_korean_and_not_saved(self):
        self.jreq("PUT", "/api/stt-options", {"options": {"preprocess": "denoise"}})
        status, body = self.jreq("PUT", "/api/stt-options", {"options": {"preprocess": "wrong"}})
        self.assertEqual(status, 400)
        self.assertIn("preprocess", body["error"])
        self.assertIn("중 하나여야", body["error"])
        _, got = self.jreq("GET", "/api/stt-options")
        self.assertEqual(got["options"], {"preprocess": "denoise"})

    def test_put_missing_options_400(self):
        status, body = self.jreq("PUT", "/api/stt-options", {"preprocess": "denoise"})
        self.assertEqual(status, 400)
        self.assertIn("options", body["error"])

    def test_put_over_32k_413(self):
        raw_body = json.dumps({"options": {"context": "가" * 40000}},
                              ensure_ascii=False).encode("utf-8")
        self.assertGreater(len(raw_body), 32 * 1024)
        status, _, raw = self.req("PUT", "/api/stt-options", raw_body,
                                  {"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        _, got = self.jreq("GET", "/api/stt-options")
        self.assertEqual(got["options"], {})

    def test_put_foreign_origin_403(self):
        status, _ = self.jreq("PUT", "/api/stt-options",
                              {"options": {"preprocess": "denoise"}},
                              headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        _, got = self.jreq("GET", "/api/stt-options")
        self.assertEqual(got["options"], {})

    def test_retry_without_body_keeps_meta_options(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.server.store.set_stt_options(rid, {"preprocess": "denoise"})
        self.wait_done(rid)
        self.drain()
        _, body = self.jreq("GET", "/api/recordings/" + rid)
        for key in ("stt_options", "stt_used", "prev_stt_used", "transcript_prev"):
            self.assertIn(key, body)
        status, again = self.jreq("POST", "/api/recordings/%s/retry" % rid)
        self.assertEqual(status, 200)
        self.assertEqual(again["stt_options"], {"preprocess": "denoise"})
        self.drain()
        self.assertEqual(self.server.store.get(rid)["stt_options"],
                         {"preprocess": "denoise"})

    def test_retry_options_saved_and_transcribes_again(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.drain()
        self.assertEqual(len(self.calls), 1)
        status, again = self.jreq("POST", "/api/recordings/%s/retry" % rid,
                                  {"options": {"preprocess": "denoise"}})
        self.assertEqual(status, 200)
        self.assertEqual(again["stt_options"], {"preprocess": "denoise"})
        self.drain()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.wait_done(rid)["transcript"], "가짜 글 2")

    def test_retry_options_null_clears_key(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.server.store.set_stt_options(rid, {"preprocess": "denoise"})
        self.wait_done(rid)
        self.drain()
        status, again = self.jreq("POST", "/api/recordings/%s/retry" % rid,
                                  {"options": None})
        self.assertEqual(status, 200)
        self.assertIsNone(again["stt_options"])
        self.drain()
        self.assertIsNone(self.server.store.get(rid)["stt_options"])

    def test_retry_empty_options_follows_defaults(self):
        status, body = self.jreq("PUT", "/api/stt-options", {"options": {"preprocess": "denoise"}})
        self.assertEqual(status, 200)
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.drain()
        status, again = self.jreq("POST", "/api/recordings/%s/retry" % rid,
                                  {"options": {}})
        self.assertEqual(status, 200)
        self.assertIsNone(again["stt_options"])
        meta = self.server.store.get(rid)
        self.assertIsNone(meta["stt_options"])
        self.assertEqual(self.server.store.effective_stt_options(meta),
                         {"preprocess": "denoise"})
        self.drain()

    def test_retry_bad_options_400_and_nothing_changes(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.server.store.set_stt_options(rid, {"preprocess": "denoise"})
        self.wait_done(rid)
        self.drain()
        before = self.server.store.get(rid)
        status, body = self.jreq("POST", "/api/recordings/%s/retry" % rid,
                                 {"options": {"preprocess": "wrong"}})
        self.assertEqual(status, 400)
        self.assertIn("preprocess", body["error"])
        after = self.server.store.get(rid)
        self.assertEqual(after["stt_options"], before["stt_options"])
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(len(self.calls), 1)

    def test_retry_over_32k_413_and_options_unchanged(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.server.store.set_stt_options(rid, {"preprocess": "denoise"})
        self.wait_done(rid)
        self.drain()
        raw_body = json.dumps({"options": {"context": "가" * 40000}},
                              ensure_ascii=False).encode("utf-8")
        status, _, _ = self.req("POST", "/api/recordings/%s/retry" % rid, raw_body,
                                {"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        self.assertEqual(self.server.store.get(rid)["stt_options"],
                         {"preprocess": "denoise"})


class TestSttOptionsNoKeyLeak(Base):
    env = {
        "VOXLOG_STT_URL": "https://stt.example.org/v1/audio/diarize/jobs",
        "VOXLOG_STT_MODEL": "some-model",
        "VOXLOG_STT_API_KEY": "sk-secret-test-key",
    }

    def test_response_does_not_leak_settings(self):
        status, body = self.jreq("GET", "/api/stt-options")
        self.assertEqual(status, 200)
        self.assertEqual(body["stt"], "api")
        raw = json.dumps(body)
        for secret in ("sk-secret-test-key", "VOXLOG_STT_API_KEY",
                       "VOXLOG_STT_URL", "VOXLOG_STT_MODEL", "some-model"):
            self.assertNotIn(secret, raw)


class TestRetryStaleJobApi(Base):
    """R51-N2: 사람이 누른 재시도는 남은 stt_job 을 지우고 새 작업을 맡긴다."""

    env = {
        "VOXLOG_STT_URL": "https://stt.example.org/v1/audio/diarize/jobs",
        "VOXLOG_STT_MODEL": "test-model",
    }

    def make_stt(self):
        return None  # api 백엔드 + 가짜 opener 를 쓰게 한다

    def setUp(self):
        self.fake = FakeJobPostOpener()
        self.patch = mock.patch.object(serve.stt_mod, "_default_opener", self.fake)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        super().setUp()

    def drain(self):
        end = time.time() + 10
        while time.time() < end and not self.server.transcriber.idle():
            time.sleep(0.02)
        self.assertTrue(self.server.transcriber.idle())

    def retry_with_stale_job(self, body):
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.drain()
        self.server.store.set_job(rid, "job-stale")
        before = len(self.fake.posts)
        status, _ = self.jreq("POST", "/api/recordings/%s/retry" % rid, body)
        self.assertEqual(status, 200)
        self.drain()
        self.assertEqual(len(self.fake.posts), before + 1)
        self.assertNotIn("stt_job", self.server.store.get(rid))

    def test_retry_with_options_clears_stale_job_and_resubmits(self):
        self.retry_with_stale_job({"options": {"preprocess": "denoise"}})

    def test_retry_without_body_clears_stale_job_and_resubmits(self):
        self.retry_with_stale_job(None)


class TestSttOptionsToken(Base):
    token = TOKEN

    def test_token_required_for_get_and_put(self):
        self.assertEqual(self.jreq("GET", "/api/stt-options")[0], 401)
        self.assertEqual(self.jreq("PUT", "/api/stt-options",
                                   {"options": {"preprocess": "denoise"}})[0], 401)
        self.assertEqual(self.jreq("GET", "/api/stt-options", token="wrong")[0], 401)
        status, body = self.jreq("GET", "/api/stt-options", token=TOKEN)
        self.assertEqual(status, 200)
        status, body = self.jreq("PUT", "/api/stt-options",
                                 {"options": {"preprocess": "denoise"}}, token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body["options"], {"preprocess": "denoise"})


class TestSttOptionsPassed(Base):
    """Transcriber 가 실제 transcribe 로 전체 기본값·녹음 옵션을 넘기는지."""

    def make_stt(self):
        return None

    def setUp(self):
        self.seen = []

        def fake(path, mime, env, job=None, options=None, used=None):
            self.seen.append(dict(options or {}))
            if isinstance(used, dict):
                used.update({"preprocess": (options or {}).get("preprocess"),
                             "mode": "context", "speakers": 1,
                             "auto": False, "review": False})
            return "옵션 글 " + str(len(self.seen))

        self.transcribe_patch = mock.patch.object(serve.stt_mod, "transcribe", fake)
        self.transcribe_patch.start()
        self.addCleanup(self.transcribe_patch.stop)
        super().setUp()

    def test_default_options_then_recording_options_reach_transcribe(self):
        self.server.store.set_default_stt_options(
            {"preprocess": "level", "num_speakers": 3})
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.assertEqual(self.seen, [{"preprocess": "level", "num_speakers": 3}])
        self.assertEqual(self.server.store.get(rid)["stt_used"]["preprocess"], "level")
        status, _ = self.jreq("POST", "/api/recordings/%s/retry" % rid,
                              {"options": {"preprocess": "denoise"}})
        self.assertEqual(status, 200)
        end = time.time() + 10
        while len(self.seen) < 2 and time.time() < end:
            time.sleep(0.02)
        self.assertEqual(len(self.seen), 2)
        self.assertEqual(self.seen[1], {"preprocess": "denoise"})
        self.assertEqual(self.server.store.get(rid)["stt_options"],
                         {"preprocess": "denoise"})

    def test_no_options_sends_empty(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.assertEqual(self.seen, [{}])


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


class TestHealthLlmAvailable(Base):
    """LLM 명령이 실제로 있으면 health 의 llm 이 참이어야 한다(가짜 늘 false 변이를 잡는다)."""
    env = {"VOXLOG_LLM_CMD": shlex.quote(sys.executable) + " -p"}

    def test_health_llm_true(self):
        status, body = self.jreq("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["llm"])
        self.assertNotIn("llm_error", body)


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

    def test_retry_options_while_transcribing_409_and_options_unchanged(self):
        self.gate.clear()
        _, meta = self.upload()
        rid = meta["id"]
        self.assertTrue(self.started.wait(5))
        self.server.store.set_stt_options(rid, {"preprocess": "denoise"})
        status, body = self.jreq("POST", "/api/recordings/%s/retry" % rid,
                                 {"options": {"preprocess": "basic"}})
        self.assertEqual(status, 409)
        self.assertIn("받아쓰는 중", body["error"])
        self.assertEqual(self.server.store.get(rid)["stt_options"],
                         {"preprocess": "denoise"})
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


class TestLabelTags(Base):
    llm_ready = staticmethod(llm_false)

    def seed(self, label=None, tags=None):
        status, meta = self.upload()
        self.assertEqual(status, 201)
        self.wait_done(meta["id"])
        if label is not None or tags is not None:
            body = {}
            if label is not None:
                body["label"] = label
            if tags is not None:
                body["tags"] = tags
            st, _ = self.jreq("PATCH", "/api/recordings/" + meta["id"], body)
            self.assertEqual(st, 200)
        return meta["id"]

    def test_patch_roundtrip_and_fields(self):
        rid = self.seed()
        status, meta = self.jreq("PATCH", "/api/recordings/" + rid,
                                 {"label": "  주간 회의  ", "tags": [" 회의 ", "A사", "회의", ""]})
        self.assertEqual(status, 200)
        self.assertEqual(meta["label"], "주간 회의")
        self.assertEqual(meta["tags"], ["회의", "A사"])
        self.assertEqual(meta["tags_auto"], [])
        self.assertTrue(meta["tags_human"])
        self.assertIsNone(meta["autotag"])  # llm_ready 거짓이면 자동 태그는 맡기지 않는다
        self.assertIn("transcript", meta)
        _, got = self.jreq("GET", "/api/recordings/" + rid)
        self.assertEqual(got["label"], "주간 회의")
        self.assertEqual(got["tags"], ["회의", "A사"])
        self.assertTrue(got["tags_human"])
        _, lst = self.jreq("GET", "/api/recordings")
        item = lst["items"][0]
        for key in ("label", "tags", "tags_auto", "tags_human", "autotag"):
            self.assertIn(key, item)
        self.assertEqual(item["label"], "주간 회의")

    def test_label_only_keeps_tags_human(self):
        rid = self.seed(label="옛 이름", tags=["회의"])
        status, meta = self.jreq("PATCH", "/api/recordings/" + rid, {"label": "새 이름"})
        self.assertEqual(status, 200)
        self.assertEqual(meta["label"], "새 이름")
        self.assertEqual(meta["tags"], ["회의"])
        self.assertTrue(meta["tags_human"])  # 앞 PATCH tags 가 세운 것을 유지

    def test_empty_tags_array_clears(self):
        rid = self.seed(label="이름", tags=["회의", "A사"])
        status, meta = self.jreq("PATCH", "/api/recordings/" + rid, {"tags": []})
        self.assertEqual(status, 200)
        self.assertEqual(meta["tags"], [])
        self.assertEqual(meta["tags_auto"], [])
        self.assertTrue(meta["tags_human"])

    def test_patch_400_limits_and_types(self):
        rid = self.seed()
        cases = [
            ({"label": "가" * 41}, "이름은 40자 이하여야 합니다"),
            ({"tags": ["가" * 21]}, "태그는 하나당 20자 이하여야 합니다"),
            ({"tags": ["t%d" % i for i in range(11)]}, "태그는 최대 10개입니다"),
            ({"label": 3}, "label 은 문자열이어야 합니다"),
            ({"tags": "회의"}, "tags 는 문자열 목록이어야 합니다"),
            ({"tags": [1]}, "tags 는 문자열 목록이어야 합니다"),
            ({}, "바꿀 이름이나 태그가 없습니다"),
            ({"other": 1}, "바꿀 이름이나 태그가 없습니다"),
        ]
        for body, msg in cases:
            status, got = self.jreq("PATCH", "/api/recordings/" + rid, body)
            self.assertEqual(status, 400, body)
            self.assertEqual(got["error"], msg, body)

    def test_patch_bad_body_400(self):
        rid = self.seed()
        for raw in (b"not json", b"[]", b"null", b"3"):
            status, _, _ = self.req("PATCH", "/api/recordings/" + rid, raw,
                                    {"Content-Type": "application/json"})
            self.assertEqual(status, 400, raw)

    def test_patch_missing_length_400(self):
        rid = self.seed()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("PATCH", "/api/recordings/" + rid)
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()

    def test_patch_too_large_413(self):
        rid = self.seed()
        status, _, raw = self.req("PATCH", "/api/recordings/" + rid, b"=" * 6145,
                                  {"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        self.assertIn("6144", json.loads(raw.decode("utf-8"))["error"])

    def test_patch_missing_id_404(self):
        status, body = self.jreq("PATCH", "/api/recordings/r-20200101-000000-abcd",
                                 {"label": "이름"})
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "없는 녹음입니다")

    def test_patch_deleted_between_get_and_set_404(self):
        rid = self.seed()
        with mock.patch.object(self.server.store, "set_label_tags",
                               side_effect=ValueError("없는 녹음입니다: " + rid)):
            status, body = self.jreq("PATCH", "/api/recordings/" + rid, {"label": "이름"})
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "없는 녹음입니다")

    def test_patch_405_allow_and_origin(self):
        rid = self.seed()
        status, hdr, _ = self.req("PUT", "/api/recordings/" + rid, b"")
        self.assertEqual(status, 405)
        self.assertEqual(hdr["Allow"], "GET, PATCH, DELETE")
        status, _, _ = self.req("PATCH", "/api/recordings/" + rid, b'{"label":"x"}',
                                {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        status, _, _ = self.req("POST", "/api/recordings/%s/autotag" % rid, b"",
                                {"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        same = "http://127.0.0.1:%d" % self.port
        status, _ = self.jreq("PATCH", "/api/recordings/" + rid, {"label": "같은 출처"},
                              headers={"Origin": same})
        self.assertEqual(status, 200)


class TestTagFilter(Base):
    llm_ready = staticmethod(llm_false)

    def seed(self, label, tags, status=None):
        status_code, meta = self.upload()
        self.assertEqual(status_code, 201)
        self.wait_done(meta["id"])
        self.jreq("PATCH", "/api/recordings/" + meta["id"], {"label": label, "tags": tags})
        if status:
            self.server.store.set_status(meta["id"], status)
        return meta["id"]

    def test_tag_filter_and_with_q_and_status(self):
        a = self.seed("주간회의", ["회의"])
        b = self.seed("다른 이름", ["회의", "A사"], status="failed")
        c = self.seed("개인", ["개인"])
        _, got = self.jreq("GET", "/api/recordings?tag=" + quote("회의"))
        self.assertEqual({x["id"] for x in got["items"]}, {a, b})
        _, got = self.jreq("GET", "/api/recordings?tag=%s&q=%s" % (quote("회의"), quote("주간")))
        self.assertEqual([x["id"] for x in got["items"]], [a])
        self.assertEqual(got["items"][0]["match"], "label")
        _, got = self.jreq("GET", "/api/recordings?tag=%s&status=done" % quote("회의"))
        self.assertEqual([x["id"] for x in got["items"]], [a])
        _, got = self.jreq("GET", "/api/recordings?tag=%s&status=failed" % quote("회의"))
        self.assertEqual([x["id"] for x in got["items"]], [b])
        _, got = self.jreq("GET", "/api/recordings?tag=" + quote("없는태그"))
        self.assertEqual(got["items"], [])

    def test_tag_filter_casefold(self):
        self.seed("회의", ["Meeting"])
        _, got = self.jreq("GET", "/api/recordings?tag=meeting")
        self.assertEqual(len(got["items"]), 1)

    def test_tag_filter_too_long_400(self):
        status, body = self.jreq("GET", "/api/recordings?tag=" + "a" * 21)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "태그는 하나당 20자 이하여야 합니다")
        status, _ = self.jreq("GET", "/api/recordings?tag=" + "a" * 20)
        self.assertEqual(status, 200)

    def test_match_kinds(self):
        rid = self.seed("주간 모임", ["회의"])
        _, got = self.jreq("GET", "/api/recordings?q=" + quote("주간"))
        self.assertEqual(got["items"][0]["match"], "label")
        _, got = self.jreq("GET", "/api/recordings?q=" + quote("회의"))
        self.assertEqual(got["items"][0]["match"], "tag")
        _, got = self.jreq("GET", "/api/recordings?q=" + quote("가짜"))
        self.assertEqual(got["items"][0]["match"], "text")
        _, got = self.jreq("GET", "/api/recordings?q=" + quote("없는말"))
        self.assertEqual(got["items"], [])
        _, got = self.jreq("GET", "/api/recordings")
        self.assertNotIn("match", got["items"][0])
        self.assertEqual(got["items"][0]["id"], rid)


class TestAutoTag(Base):
    llm_ready = staticmethod(llm_true)

    def test_upload_auto_tags(self):
        status, meta = self.upload()
        self.assertEqual(status, 201)
        self.wait_done(meta["id"])
        self.wait_autotag(meta["id"])
        self.wait_asker_idle()
        _, done = self.jreq("GET", "/api/recordings/" + meta["id"])
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["tags"], ["회의", "가짜 태그", "세번째"])
        self.assertEqual(done["tags_auto"], ["회의", "가짜 태그", "세번째"])
        self.assertFalse(done["tags_human"])
        self.assertEqual(done["autotag"], "done")

    def test_patch_delete_then_retry_does_not_revive(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.wait_autotag(rid)
        status, _ = self.jreq("PATCH", "/api/recordings/" + rid, {"tags": ["가짜 태그"]})
        self.assertEqual(status, 200)
        self.assertEqual(self.jreq("POST", "/api/recordings/%s/retry" % rid)[0], 200)
        self.wait_done(rid)
        time.sleep(0.3)
        self.wait_asker_idle()
        _, got = self.jreq("GET", "/api/recordings/" + rid)
        self.assertEqual(got["status"], "done")
        self.assertNotIn("회의", got["tags"])
        self.assertEqual(got["tags"], ["가짜 태그"])
        self.assertTrue(got["tags_human"])

    def test_post_autotag_keeps_human_and_replaces_ai(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.wait_autotag(rid)
        status, _ = self.jreq("PATCH", "/api/recordings/" + rid, {"tags": ["내 태그", "회의"]})
        self.assertEqual(status, 200)
        status, body = self.jreq("POST", "/api/recordings/%s/autotag" % rid)
        self.assertEqual(status, 202)
        self.assertEqual(body, {"ok": True, "autotag": "pending"})
        got = self.wait_autotag(rid)
        self.assertEqual(got["tags"], ["내 태그", "회의", "가짜 태그", "세번째"])
        self.assertEqual(got["tags_auto"], ["회의", "가짜 태그", "세번째"])
        self.assertTrue(got["tags_human"])

    def test_post_autotag_404_409(self):
        empty = self.server.store.add_recording(b"RIFF", "audio/webm")
        status, body = self.jreq("POST", "/api/recordings/%s/autotag" % empty["id"])
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "받아 적은 글이 없습니다")
        status, body = self.jreq("POST", "/api/recordings/r-20200101-000000-abcd/autotag")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "없는 녹음입니다")

    def test_post_autotag_existing_job_still_202(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.wait_autotag(rid)
        with mock.patch.object(self.server.asker, "submit_tag", return_value=False):
            status, body = self.jreq("POST", "/api/recordings/%s/autotag" % rid)
        self.assertEqual(status, 202)
        self.assertEqual(body["autotag"], "pending")

    def test_tag_failure_does_not_change_status(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        self.wait_autotag(rid)
        def boom(prompt, env=None):
            if prompt.startswith("이 녹취에 붙일 주제 태그"):
                raise RuntimeError("태그 실패")
            return "가짜 답"
        self.server.asker.run = boom
        status = self.jreq("POST", "/api/recordings/%s/retry" % rid)[0]
        self.assertEqual(status, 200)
        self.wait_done(rid)
        end = time.time() + 10
        while time.time() < end:
            _, got = self.jreq("GET", "/api/recordings/" + rid)
            if got["autotag"] != "done":
                break
            time.sleep(0.02)
        self.wait_asker_idle()
        _, got = self.jreq("GET", "/api/recordings/" + rid)
        self.assertEqual(got["status"], "done")
        self.assertEqual(got["autotag"], "failed")
        self.assertTrue(got["transcript"].startswith("가짜 글 "))

    def test_asker_idle_includes_tag_jobs(self):
        _, meta = self.upload()
        self.wait_done(meta["id"])
        self.wait_autotag(meta["id"])
        self.wait_asker_idle()


class TestAutoTagNoLlm(Base):
    llm_ready = staticmethod(llm_false)

    def test_upload_has_no_auto_tags_and_retag_503(self):
        _, meta = self.upload()
        rid = meta["id"]
        self.wait_done(rid)
        time.sleep(0.2)
        _, got = self.jreq("GET", "/api/recordings/" + rid)
        self.assertIsNone(got["autotag"])
        self.assertEqual(got["tags"], [])
        self.assertEqual(got["tags_auto"], [])
        self.assertFalse(got["tags_human"])
        status, body = self.jreq("POST", "/api/recordings/%s/autotag" % rid)
        self.assertEqual(status, 503)
        self.assertEqual(body["error"], "묻기(LLM)가 준비되지 않았습니다")
        status, _ = self.jreq("PATCH", "/api/recordings/" + rid, {"label": "손 이름", "tags": ["손 태그"]})
        self.assertEqual(status, 200)
        _, got = self.jreq("GET", "/api/recordings/" + rid)
        self.assertEqual(got["label"], "손 이름")
        self.assertEqual(got["tags"], ["손 태그"])
        self.assertTrue(got["tags_human"])


class TestServeTokenPatchAutotag(Base):
    token = TOKEN
    llm_ready = staticmethod(llm_true)

    def test_token_required(self):
        _, meta = self.upload(token=TOKEN)
        rid = meta["id"]
        self.wait_done(rid, token=TOKEN)
        self.wait_autotag(rid, token=TOKEN)
        self.assertEqual(self.jreq("PATCH", "/api/recordings/" + rid, {"label": "x"})[0], 401)
        self.assertEqual(self.jreq("POST", "/api/recordings/%s/autotag" % rid)[0], 401)
        status, _ = self.jreq("PATCH", "/api/recordings/" + rid, {"label": "x"}, token=TOKEN)
        self.assertEqual(status, 200)
        status, body = self.jreq("POST", "/api/recordings/%s/autotag" % rid, token=TOKEN)
        self.assertEqual(status, 202)
        self.assertEqual(body["autotag"], "pending")


class TestHealthUsesLlmStatus(Base):
    def test_health_llm_status_fields(self):
        with mock.patch.object(serve.ask_mod, "llm_status", return_value=(False, "LLM 명령 설정 오류: 시험")):
            status, body = self.jreq("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertFalse(body["llm"])
        self.assertEqual(body["llm_error"], "LLM 명령 설정 오류: 시험")


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
