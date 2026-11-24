import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest import mock

PROJECT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from voxlog import stt  # noqa: E402

FAKE_STT = pathlib.Path(__file__).resolve().parent / "fake_stt.py"
HAVE_FFMPEG = shutil.which("ffmpeg") is not None


class FakeStore:
    """store.py 를 import 하지 않고 같은 메서드만 흉내내는 작은 저장소."""

    def __init__(self, metas=None, paths=None):
        self.metas = {k: dict(v) for k, v in (metas or {}).items()}
        self.paths = dict(paths or {})
        self.statuses = []
        self.transcripts = {}
        self._lock = threading.Lock()

    def pending_ids(self):
        return [
            rid
            for rid, meta in self.metas.items()
            if meta.get("status") in ("pending", "transcribing")
        ]

    def get(self, rid):
        meta = self.metas.get(rid)
        return dict(meta) if meta is not None else None

    def audio_path(self, rid):
        return self.paths.get(rid)

    def set_status(self, rid, status, error=None):
        if rid not in self.metas:
            raise ValueError(rid)
        self.metas[rid]["status"] = status
        self.metas[rid]["error"] = error
        with self._lock:
            self.statuses.append((rid, status, error))

    def set_transcript(self, rid, text):
        if rid not in self.metas:
            raise ValueError(rid)
        self.metas[rid]["status"] = "done"
        with self._lock:
            self.transcripts[rid] = text
            self.statuses.append((rid, "done", None))

    def status_of(self, rid):
        with self._lock:
            for r, status, _ in reversed(self.statuses):
                if r == rid:
                    return status
        return None

    def error_of(self, rid):
        with self._lock:
            for r, status, error in reversed(self.statuses):
                if r == rid:
                    return status, error
        return None, None


class FakeOpener:
    def __init__(self, response=b"", fail_code=None):
        self.response = response
        self.fail_code = fail_code
        self.calls = []
        self.last_req = None

    def __call__(self, req, timeout):
        self.calls.append(timeout)
        self.last_req = req
        if self.fail_code is not None:
            raise urllib.error.HTTPError(
                req.full_url, self.fail_code, "boom", {}, None
            )
        return self.response


class FakeJob:
    """맡긴 작업 id 를 적어 두는 곳(stt._JobRef 흉내)."""

    def __init__(self, jid=None):
        self.jid = jid
        self.history = []

    def get(self):
        return self.jid

    def set(self, jid):
        self.jid = jid
        self.history.append(jid)


class FakeJobIdOpener:
    """맡기기에는 정해 준 작업 id 를 주고, 조회·지우기에는 바로 done 을 준다 (작업 id 규칙 검사용)."""

    def __init__(self, jid):
        self.jid = jid
        self.urls = []

    def __call__(self, req, timeout):
        if req.get_method() == "POST":
            return json.dumps({"id": self.jid}).encode("utf-8")
        self.urls.append(req.full_url)
        return json.dumps({"status": "done", "result": {"text": "받아 적음"}}).encode("utf-8")


class FakeJobServer:
    """받아쓰기 서버의 작업 API 흉내(opener). states = 조회마다 차례로 돌려줄 것 -
    상태 글자("queued"…), 0(연결 실패) 또는 HTTP 오류 코드. 다 쓰면 마지막 것을 되풀이."""

    def __init__(self, url, states=("done",), result=None, error=None, known=None):
        self.url, self.states, self.result, self.error = url, list(states), result, error
        self.known = set(known or ())
        self.calls, self.posts, self.auths, self.slept = [], [], [], []
        self.i = 0

    def __call__(self, req, timeout):
        method = req.get_method()
        self.calls.append((method, req.full_url))
        self.auths.append(req.get_header("Authorization"))
        if method == "POST":
            self.posts.append(req)
            self.known.add("job1")
            return json.dumps({"id": "job1", "status": "queued", "status_url": "/x/job1"}).encode("utf-8")
        jid = req.full_url.rsplit("/", 1)[1]
        if jid not in self.known:
            raise urllib.error.HTTPError(req.full_url, 404, "no such job", {}, None)
        if method == "DELETE":
            return json.dumps({"id": jid, "status": "deleted"}).encode("utf-8")
        state = self.states[min(self.i, len(self.states) - 1)]
        self.i += 1
        if state == 0:
            raise urllib.error.URLError("down")
        if isinstance(state, int):
            raise urllib.error.HTTPError(req.full_url, state, "boom", {}, None)
        view = {"id": jid, "status": state, "stage": state, "error": self.error if state != "done" else None}
        if state == "done":
            view["result"] = self.result
        return json.dumps(view).encode("utf-8")


def wait_idle(transcriber, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if transcriber.idle():
            return True
        time.sleep(0.05)
    return False


class ToAudioCommandTest(unittest.TestCase):
    def _run_to_audio(self, suffix, out_fmt="wav"):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))

            class Proc:
                returncode = 0
                stderr = b""

            return Proc()

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = pathlib.Path(tmp.name) / ("src" + suffix)
        src.write_bytes(b"x")
        with mock.patch.object(stt.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(stt.subprocess, "run", side_effect=fake_run):
            out = stt.to_audio(src, out_fmt)
        return calls, out

    def test_webm_forces_input_format_and_protocol_whitelist(self):
        calls, out = self._run_to_audio(".webm")
        out.unlink(missing_ok=True)
        self.assertEqual(len(calls), 1)
        cmd = calls[0]
        i_proto = cmd.index("-protocol_whitelist")
        self.assertEqual(cmd[i_proto + 1], "file,pipe")
        i_fmt = cmd.index("-f")
        self.assertEqual(cmd[i_fmt + 1], "matroska")
        i_input = cmd.index("-i")
        self.assertLess(i_proto, i_input)
        self.assertLess(i_fmt, i_input)

    def test_extension_sets_demuxer(self):
        expected = {
            ".webm": "matroska",
            ".ogg": "ogg",
            ".m4a": "mov",
            ".mp3": "mp3",
            ".wav": "wav",
        }
        for suffix, fmt in expected.items():
            calls, out = self._run_to_audio(suffix)
            out.unlink(missing_ok=True)
            cmd = calls[0]
            self.assertEqual(cmd[cmd.index("-f") + 1], fmt, suffix)

    def test_unknown_extension_raises_without_calling_ffmpeg(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = pathlib.Path(tmp.name) / "src.xyz"
        src.write_bytes(b"x")
        calls = []
        with mock.patch.object(stt.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(
                    stt.subprocess, "run", side_effect=lambda *a, **k: calls.append(a)
                ):
            with self.assertRaises(stt.SttError):
                stt.to_audio(src, "wav")
        self.assertEqual(calls, [])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg 가 없습니다")
class ToAudioRealFfmpegTest(unittest.TestCase):
    def test_converts_webm_to_wav(self):
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "sine.webm"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "libopus", str(src),
                ],
                check=True,
                capture_output=True,
            )
            out = stt.to_audio(src, "wav")
            try:
                self.assertTrue(out.exists())
                self.assertGreater(out.stat().st_size, 0)
            finally:
                out.unlink(missing_ok=True)


class BackendNameTest(unittest.TestCase):
    def test_voxlog_stt_wins(self):
        env = {"VOXLOG_STT": "command", "VOXLOG_STT_CMD": "x", "VOXLOG_STT_URL": "https://h/v1"}
        self.assertEqual(stt.backend_name(env), "command")

    def test_command_when_cmd_set(self):
        self.assertEqual(stt.backend_name({"VOXLOG_STT_CMD": "x"}), "command")

    def test_api_when_url_set(self):
        self.assertEqual(stt.backend_name({"VOXLOG_STT_URL": "https://h/v1"}), "api")
        self.assertEqual(stt.backend_name({"OPENROUTER_API_KEY": "k"}), "none")

    def test_none_when_nothing_set(self):
        self.assertEqual(stt.backend_name({}), "none")


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg 가 없습니다")
class CommandBackendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.src = self.dir / "sine.webm"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:a", "libopus", str(self.src),
            ],
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_command_runs_fake_stt(self):
        env = {"VOXLOG_STT_CMD": "%s %s {wav}" % (sys.executable, FAKE_STT)}
        text = stt.transcribe(self.src, "audio/webm", env=env)
        self.assertTrue(text.startswith("가짜 받아쓰기 "))
        self.assertTrue(text.endswith("바이트"))

    def test_command_fail_raises_stt_error(self):
        env = {
            "VOXLOG_STT_CMD": "%s %s {wav}" % (sys.executable, FAKE_STT),
            "FAKE_STT_FAIL": "1",
        }
        with self.assertRaises(stt.SttError):
            stt.transcribe(self.src, "audio/webm", env=env)

    def test_missing_executable_raises_unavailable(self):
        env = {"VOXLOG_STT_CMD": "/nonexistent/definitely-missing-stt {wav}"}
        with self.assertRaises(stt.SttUnavailable):
            stt.transcribe(self.src, "audio/webm", env=env)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg 가 없습니다")
class ApiBackendTest(unittest.TestCase):
    URL = "https://stt.example/v1/audio/diarize/jobs"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.src = self.dir / "sine.webm"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                "-c:a", "libopus", str(self.src),
            ],
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    DONE = {"text": "A: 네 안녕하세요\nB: 저도요", "segments": [
        {"speaker": "A", "start": 0.0, "end": 1.0, "text": "네 안녕하세요"},
        {"speaker": "A", "start": 1.0, "end": 2.0, "text": " 반갑습니다 "},
        {"speaker": "B", "start": 2.0, "end": 3.0, "text": "저도요"},
        {"speaker": "B", "start": 3.0, "end": 3.1, "text": "  "},
        {"start": 3.1, "end": 3.2, "text": "화자 없음"}]}

    def run_api(self, server, env=None, job=None):
        with mock.patch.object(stt, "_sleep", lambda s: server.slept.append(s)):
            return stt.transcribe(self.src, "audio/webm", env=dict({"VOXLOG_STT_URL": self.URL}, **(env or {})),
                                  opener=server, job=job)

    def test_api_submits_a_job_polls_and_deletes_it(self):
        server = FakeJobServer(self.URL, states=["queued", "running", "done"], result=self.DONE)
        text = self.run_api(server, {"VOXLOG_STT_MODEL": "my/model"})
        self.assertEqual(text, "화자 1: 네 안녕하세요 반갑습니다\n화자 2: 저도요")
        self.assertEqual([m for m, _ in server.calls], ["POST", "GET", "GET", "GET", "DELETE"])
        self.assertEqual({u for m, u in server.calls if m != "POST"}, {self.URL + "/job1"})
        self.assertEqual(server.slept, [stt.POLL_SECONDS, stt.POLL_SECONDS])
        body = server.posts[0].data                                  # 다시 압축하지 않고 받은 원본 그대로
        self.assertIn(b'name="model"\r\n\r\nmy/model\r\n', body)
        self.assertIn(b'name="language"\r\n\r\nko\r\n', body)
        self.assertIn(b'name="file"; filename="audio.webm"\r\nContent-Type: audio/webm\r\n\r\n', body)
        self.assertIn(self.src.read_bytes(), body)
        self.assertIsNone(server.posts[0].get_header("Authorization"))
        self.assertTrue(self.src.exists())

    def test_api_key_and_language_are_optional_settings(self):
        server = FakeJobServer(self.URL, result={"text": "hi"})
        text = self.run_api(server, {"VOXLOG_STT_API_KEY": "test-key-abc", "VOXLOG_STT_LANG": "en"})
        self.assertEqual(text, "hi")                                 # segments 가 없으면 text 그대로
        self.assertEqual({a for a in server.auths}, {"Bearer test-key-abc"})   # 맡기기·조회·지우기 모두 키를 싣는다
        self.assertIn(b'name="language"\r\n\r\nen\r\n', server.posts[0].data)
        self.assertNotIn(b'name="model"', server.posts[0].data)

    def test_unknown_speaker_is_not_counted_as_a_person(self):
        result = {"text": "x", "segments": [
            {"speaker": "?", "text": "응."}, {"speaker": "A", "text": "안녕하세요"}, {"speaker": "?", "text": "아."},
            {"speaker": "?", "text": "음."}, {"speaker": "B", "text": "네"}, {"speaker": "A", "text": "그래요"}]}
        text = self.run_api(FakeJobServer(self.URL, result=result))
        self.assertEqual(text, "화자 ?: 응.\n화자 1: 안녕하세요\n화자 ?: 아. 음.\n화자 2: 네\n화자 1: 그래요")

    def test_failed_and_cancelled_jobs_are_stt_errors_and_are_deleted(self):
        for state, word in (("failed", "받아쓰지 못했습니다"), ("cancelled", "취소")):
            server = FakeJobServer(self.URL, states=[state], error="cannot decode\nthe audio")
            job = FakeJob()
            with self.assertRaises(stt.SttError) as cm:
                self.run_api(server, job=job)
            self.assertIn(word, str(cm.exception))
            if state == "failed":
                self.assertIn("cannot decode the audio", str(cm.exception))
            self.assertEqual(server.calls[-1][0], "DELETE")
            self.assertIsNone(job.jid)                               # 다음 받아쓰기는 새로 맡긴다

    def test_job_id_is_kept_so_a_restart_resumes_the_same_job(self):
        server = FakeJobServer(self.URL, states=["running", "done"], result=self.DONE)
        job = FakeJob()
        self.run_api(server, job=job)
        self.assertEqual(job.history, ["job1", None])                # 맡긴 직후 적고, 끝나면 지운다
        server = FakeJobServer(self.URL, states=["done"], result=self.DONE, known={"job1"})
        text = self.run_api(server, job=FakeJob("job1"))             # 적어 둔 id 가 있으면 다시 맡기지 않는다
        self.assertEqual([m for m, _ in server.calls], ["GET", "DELETE"])
        self.assertTrue(text.startswith("화자 1:"))

    def test_resumed_job_that_is_gone_is_submitted_again(self):
        server = FakeJobServer(self.URL, states=["done"], result=self.DONE, known={"job1"})
        job = FakeJob("oldjob")
        self.run_api(server, job=job)
        self.assertEqual([m for m, _ in server.calls], ["GET", "POST", "GET", "DELETE"])
        self.assertEqual(server.calls[0][1], self.URL + "/oldjob")
        self.assertEqual(job.history, ["job1", None])

    def test_polling_survives_short_outages_and_gives_up_after_many(self):
        server = FakeJobServer(self.URL, states=["running", 0, 502, "done"], result=self.DONE)
        self.assertTrue(self.run_api(server).startswith("화자 1:"))
        server = FakeJobServer(self.URL, states=[0] * (stt.POLL_MAX_ERRORS + 5))
        job = FakeJob()
        with self.assertRaises(stt.SttError) as cm:
            self.run_api(server, job=job)
        self.assertIn("연결하지 못했습니다", str(cm.exception))
        self.assertEqual(len([c for c in server.calls if c[0] == "GET"]), stt.POLL_MAX_ERRORS)
        self.assertEqual(job.jid, "job1")                            # 작업은 살아 있을 수 있다 - 다음에 이어받는다

    def test_job_that_never_finishes_times_out(self):
        server = FakeJobServer(self.URL, states=["running"] * 50)
        clock = iter(range(0, 10 ** 9, 3600))
        with mock.patch.object(stt.time, "monotonic", lambda: next(clock)), self.assertRaises(stt.SttError) as cm:
            self.run_api(server)
        self.assertIn("오래", str(cm.exception))

    def test_api_unreadable_responses_are_stt_errors(self):
        with self.assertRaises(stt.SttError):                        # 맡기기 답에 id 가 없음
            self.run_api(FakeOpener(response=json.dumps({"choices": []}).encode("utf-8")))
        with self.assertRaises(stt.SttError):                        # id 가 주소에 넣을 수 없는 꼴
            self.run_api(FakeOpener(response=json.dumps({"id": "../x"}).encode("utf-8")))
        with self.assertRaises(stt.SttError):                        # done 인데 결과가 없음
            self.run_api(FakeJobServer(self.URL, states=["done"], result=None))

    def test_api_rejects_non_http_url_and_unknown_extension(self):
        with self.assertRaises(stt.SttError):
            stt.transcribe(self.src, "audio/webm", env={"VOXLOG_STT_URL": "file:///etc/passwd"}, opener=FakeOpener())
        odd = self.dir / "x.flac"
        odd.write_bytes(b"x")
        server = FakeJobServer(self.URL)
        with self.assertRaises(stt.SttError):
            stt.transcribe(odd, "audio/flac", env={"VOXLOG_STT_URL": self.URL}, opener=server)
        self.assertEqual(server.calls, [])

    def test_api_http_error_hides_key_and_url(self):
        secret = "SUPER-SECRET-KEY-9999"
        for code, word in ((401, "키"), (429, "붐빕니다"), (500, "500")):
            opener = FakeOpener(fail_code=code)
            env = {"VOXLOG_STT_URL": self.URL, "VOXLOG_STT_API_KEY": secret}
            with self.assertRaises(stt.SttError) as cm:
                stt.transcribe(self.src, "audio/webm", env=env, opener=opener)
            exc = cm.exception
            self.assertIn(str(code), str(exc))
            self.assertIn(word, str(exc))
            self.assertNotIn(secret, str(exc))
            self.assertNotIn(secret, repr(exc))
            self.assertNotIn("stt.example", str(exc))
            self.assertEqual(len(opener.calls), 1)                   # 맡기기가 거절되면 조회하지 않는다


class ApiJobIdTest(unittest.TestCase):
    """작업 id 규칙(R41-N1): 실제 꼴(UUID·job_1)은 받고, URL 경로를 벗어나는 것만 SttError."""

    URL = "https://stt.example/v1/audio/diarize/jobs"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = pathlib.Path(self.tmp.name) / "sine.webm"
        self.src.write_bytes(b"x")

    def run_api(self, jid):
        opener = FakeJobIdOpener(jid)
        env = {"VOXLOG_STT_URL": self.URL}
        with mock.patch.object(stt, "_sleep", lambda s: None):
            text = stt.transcribe(self.src, "audio/webm", env=env, opener=opener)
        return text, opener

    def test_real_id_shapes_are_accepted(self):
        for jid in ("3f2a1b4c-5d6e-7f80-9a1b-2c3d4e5f6071", "job_1", "abc.def", "A" * 128):
            text, opener = self.run_api(jid)
            self.assertEqual(text, "받아 적음", jid)
            self.assertIn(self.URL + "/" + jid, opener.urls)

    def test_ids_that_escape_the_path_are_rejected(self):
        for jid in ("../x", "a/b", "", ".", "..", "A" * 129):
            opener = FakeJobIdOpener(jid)
            env = {"VOXLOG_STT_URL": self.URL}
            with self.assertRaises(stt.SttError, msg=jid):
                stt.transcribe(self.src, "audio/webm", env=env, opener=opener)
            self.assertEqual(opener.urls, [], jid)          # 받지 않은 id 로 조회하지 않는다


class TranscriberTest(unittest.TestCase):
    def _store(self, rid, status="pending"):
        return FakeStore(
            metas={rid: {"id": rid, "status": status, "mime": "audio/webm"}},
            paths={rid: pathlib.Path("/tmp/does-not-matter.wav")},
        )

    def test_marks_done_on_success(self):
        rid = "r-20260101-000000-aaaa"
        store = self._store(rid)
        calls = []

        def fake(path, mime, env):
            calls.append((path, mime))
            return "받아 적음"

        tr = stt.Transcriber(store, env={}, transcribe_fn=fake)
        tr.start()
        try:
            self.assertTrue(wait_idle(tr))
        finally:
            tr.stop()
        self.assertEqual(calls, [(pathlib.Path("/tmp/does-not-matter.wav"), "audio/webm")])
        self.assertEqual(store.status_of(rid), "done")
        self.assertEqual(store.transcripts.get(rid), "받아 적음")

    def test_marks_no_stt_when_unavailable(self):
        rid = "r-20260101-000000-bbbb"
        store = self._store(rid)

        def fake(path, mime, env):
            raise stt.SttUnavailable("백엔드 없음")

        tr = stt.Transcriber(store, env={}, transcribe_fn=fake)
        tr.start()
        try:
            self.assertTrue(wait_idle(tr))
        finally:
            tr.stop()
        self.assertEqual(store.status_of(rid), "no-stt")
        self.assertIn("백엔드 없음", store.error_of(rid)[1])

    def test_marks_failed_on_error(self):
        rid = "r-20260101-000000-cccc"
        store = self._store(rid)

        def fake(path, mime, env):
            raise stt.SttError("변환 실패")

        tr = stt.Transcriber(store, env={}, transcribe_fn=fake)
        tr.start()
        try:
            self.assertTrue(wait_idle(tr))
        finally:
            tr.stop()
        self.assertEqual(store.status_of(rid), "failed")
        self.assertIn("변환 실패", store.error_of(rid)[1])

    def test_skips_deleted_id(self):
        rid = "r-20260101-000000-dddd"
        store = FakeStore()
        called = []
        tr = stt.Transcriber(
            store, env={}, transcribe_fn=lambda *a: called.append(a)
        )
        tr.start()
        try:
            tr.submit(rid)
            self.assertTrue(wait_idle(tr))
        finally:
            tr.stop()
        self.assertEqual(called, [])

    def test_duplicate_submit_runs_once(self):
        rid = "r-20260101-000000-eeee"
        store = self._store(rid, status="done")
        count = []
        started = threading.Event()

        def fake(path, mime, env):
            count.append(1)
            started.set()
            time.sleep(0.1)
            return "한 번"

        tr = stt.Transcriber(store, env={}, transcribe_fn=fake)
        tr.start()
        try:
            tr.submit(rid)
            tr.submit(rid)
            tr.submit(rid)
            self.assertTrue(wait_idle(tr))
        finally:
            tr.stop()
        self.assertEqual(len(count), 1)

    def test_resubmit_retranscribes_finished_id(self):
        rid = "r-20260101-000000-ffff"
        store = self._store(rid)
        count = []

        def fake(path, mime, env):
            count.append(1)
            return "받아 적음"

        tr = stt.Transcriber(store, env={}, transcribe_fn=fake)
        tr.start()
        try:
            self.assertTrue(wait_idle(tr))
            self.assertEqual(len(count), 1)
            self.assertFalse(tr.busy(rid))
            self.assertTrue(tr.resubmit(rid))
            self.assertTrue(wait_idle(tr))
        finally:
            tr.stop()
        self.assertEqual(len(count), 2)

    def test_resubmit_sets_pending_under_lock(self):
        rid = "r-20260101-000000-7777"
        store = self._store(rid)
        tr = stt.Transcriber(store, env={}, transcribe_fn=lambda p, m, e: "x")
        # 스레드를 시작하지 않으니 큐에 남아 pending 이 그대로 보인다
        store.set_status(rid, "failed", "e")
        self.assertTrue(tr.resubmit(rid))
        self.assertEqual(store.get(rid)["status"], "pending")
        self.assertTrue(tr.busy(rid))
        self.assertFalse(tr.resubmit(rid))

    def test_process_exception_marks_failed(self):
        rid = "r-20260101-000000-6666"
        store = self._store(rid)

        def boom(*a, **k):
            raise OSError("disk full")

        store.set_transcript = boom
        tr = stt.Transcriber(store, env={}, transcribe_fn=lambda p, m, e: "x")
        tr.start()
        try:
            self.assertTrue(wait_idle(tr))
        finally:
            tr.stop()
        self.assertEqual(store.get(rid)["status"], "failed")
        self.assertFalse(tr.busy(rid))

    def test_resubmit_returns_false_while_busy(self):
        rid = "r-20260101-000000-9999"
        store = self._store(rid)
        entered = threading.Event()
        release = threading.Event()

        def fake(path, mime, env):
            entered.set()
            release.wait(5)
            return "끝"

        tr = stt.Transcriber(store, env={}, transcribe_fn=fake)
        tr.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertTrue(tr.busy(rid))
            self.assertFalse(tr.resubmit(rid))
            release.set()
            self.assertTrue(wait_idle(tr))
        finally:
            release.set()
            tr.stop()
        self.assertFalse(tr.busy(rid))

    def test_concurrent_resubmit_queues_once(self):
        rid = "r-20260101-000000-8888"
        store = self._store(rid)
        count = []
        release = threading.Event()
        barrier = threading.Barrier(2)

        def fake(path, mime, env):
            count.append(1)
            if len(count) >= 2:
                release.wait(5)
            return "끝"

        tr = stt.Transcriber(store, env={}, transcribe_fn=fake)
        tr.start()
        try:
            self.assertTrue(wait_idle(tr))
            self.assertEqual(len(count), 1)
            results = []

            def worker():
                barrier.wait(5)
                results.append(tr.resubmit(rid))

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(sorted(results), [False, True])
            release.set()
            self.assertTrue(wait_idle(tr))
        finally:
            release.set()
            tr.stop()
        self.assertEqual(count, [1, 1])


if __name__ == "__main__":
    unittest.main()
