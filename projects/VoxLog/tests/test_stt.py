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
        env = {"VOXLOG_STT": "command", "VOXLOG_STT_CMD": "x", "OPENROUTER_API_KEY": "k"}
        self.assertEqual(stt.backend_name(env), "command")

    def test_command_when_cmd_set(self):
        self.assertEqual(stt.backend_name({"VOXLOG_STT_CMD": "x"}), "command")

    def test_openrouter_when_key_set(self):
        self.assertEqual(stt.backend_name({"OPENROUTER_API_KEY": "k"}), "openrouter")

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
class OpenRouterBackendTest(unittest.TestCase):
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

    def test_openrouter_posts_audio_and_returns_text(self):
        payload = {"choices": [{"message": {"content": "  안녕하세요  "}}]}
        opener = FakeOpener(response=json.dumps(payload).encode("utf-8"))
        env = {"OPENROUTER_API_KEY": "test-key-abc", "VOXLOG_STT_MODEL": "my/model"}
        text = stt.transcribe(self.src, "audio/webm", env=env, opener=opener)
        self.assertEqual(text, "안녕하세요")
        req = opener.last_req
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], "my/model")
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "input_audio")
        self.assertEqual(content[1]["input_audio"]["format"], "mp3")
        self.assertTrue(content[1]["input_audio"]["data"])
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key-abc")
        self.assertEqual(opener.calls, [180])

    def test_openrouter_http_error_hides_key(self):
        secret = "SUPER-SECRET-KEY-9999"
        opener = FakeOpener(fail_code=401)
        env = {"OPENROUTER_API_KEY": secret}
        try:
            stt.transcribe(self.src, "audio/webm", env=env, opener=opener)
        except stt.SttError as exc:
            self.assertIn("401", str(exc))
            self.assertNotIn(secret, str(exc))
            self.assertNotIn(secret, repr(exc))
        else:
            self.fail("SttError 가 나야 합니다")


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
