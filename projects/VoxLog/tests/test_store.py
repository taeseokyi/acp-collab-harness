import json
import pathlib
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import voxlog.store as store_mod
from voxlog.store import ALLOWED_MIME, MAX_AUDIO_BYTES, Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name) / "data"
        self.store = Store(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, data=b"abc", mime="audio/webm", **kwargs):
        return self.store.add_recording(data, mime, **kwargs)

    # 1
    def test_add_and_get(self):
        meta = self.add(b"hello", recorded_at="2026-01-02T03:04:05", duration_ms=1000,
                        client_id="c1")
        self.assertRegex(meta["id"], r"^r-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(meta["status"], "pending")
        self.assertEqual(meta["size"], 5)
        self.assertEqual(meta["mime"], "audio/webm")
        self.assertEqual(meta["recorded_at"], "2026-01-02T03:04:05")
        self.assertEqual(meta["title"], "")
        self.assertEqual(meta["chars"], 0)
        self.assertNotIn("duplicate", meta)

        path = self.store.audio_path(meta["id"])
        self.assertIsNotNone(path)
        self.assertEqual(path.read_bytes(), b"hello")

        got = self.store.get(meta["id"])
        self.assertEqual(got["id"], meta["id"])
        self.assertEqual(got["transcript"], "")
        self.assertIsNone(self.store.get("r-20260102-030405-abcd"))

    # 2
    def test_mime_codecs_stripped(self):
        meta = self.add(mime="audio/webm;codecs=opus,opus")
        self.assertEqual(meta["mime"], "audio/webm")
        path = self.store.audio_path(meta["id"])
        self.assertEqual(path.suffix, ".webm")

    # 3
    def test_invalid_mime_empty_too_large(self):
        with self.assertRaises(ValueError):
            self.add(mime="audio/flac")
        with self.assertRaises(ValueError):
            self.add(data=b"")
        with mock.patch.object(store_mod, "MAX_AUDIO_BYTES", 10):
            with self.assertRaises(ValueError):
                self.store.add_recording(b"x" * 11, "audio/webm")
            ok = self.store.add_recording(b"x" * 10, "audio/webm")
            self.assertEqual(ok["size"], 10)

    # 4
    def test_duplicate_client_id(self):
        first = self.add(b"one", client_id="same")
        second = self.add(b"two", client_id="same")
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(len(list(self.store.audio_dir.iterdir())), 1)
        self.assertEqual(self.store.stats()["count"], 1)

    # 5
    def test_set_transcript(self):
        meta = self.add(b"sound", recorded_at="2026-07-08T12:00:00")
        text = "가나다" * 50
        self.store.set_transcript(meta["id"], text)

        txt = self.root / "transcripts" / "2026-07-08" / (meta["id"] + ".txt")
        self.assertTrue(txt.exists())
        self.assertEqual(txt.read_text(encoding="utf-8"), text)

        got = self.store.get(meta["id"])
        self.assertEqual(got["status"], "done")
        self.assertEqual(got["chars"], 150)
        self.assertEqual(got["title"], text[:40])
        self.assertIsNone(got["error"])
        self.assertEqual(got["transcript"], text)

    # 6
    def test_non_iso_recorded_at_uses_created_date(self):
        meta = self.add(recorded_at="어제 저녁")
        self.store.set_transcript(meta["id"], "메모")
        day = meta["created"][:10]
        txt = self.root / "transcripts" / day / (meta["id"] + ".txt")
        self.assertTrue(txt.exists())
        self.assertEqual(self.store.list()[0]["snippet"], "메모")

    # 7
    def test_stt_job_id_is_kept_in_meta_until_cleared(self):
        rid = self.add()["id"]
        self.store.set_job(rid, "abc123")
        self.assertEqual(self.store.get(rid)["stt_job"], "abc123")
        self.store.set_status(rid, "transcribing")
        self.assertEqual(self.store.get(rid)["stt_job"], "abc123")            # 상태가 바뀌어도 남는다
        self.store.set_job(rid, None)
        self.assertNotIn("stt_job", self.store.get(rid))
        with self.assertRaises(ValueError):
            self.store.set_job("r-20200101-000000-abcd", "x")

    def test_list_search_date_status_order(self):
        a = self.add(recorded_at="2026-01-01T10:00:00")
        b = self.add(recorded_at="2026-01-02T10:00:00")
        c = self.add(recorded_at="2026-01-03T10:00:00")
        self.store.set_transcript(a["id"], "사과 바나나")
        self.store.set_transcript(b["id"], "바나나 주스")

        items = self.store.list()
        self.assertEqual([m["id"] for m in items], [c["id"], b["id"], a["id"]])
        self.assertEqual(items[2]["snippet"], "사과 바나나")

        found = self.store.list(q="바나나")
        self.assertEqual({m["id"] for m in found}, {a["id"], b["id"]})
        b_item = [m for m in found if m["id"] == b["id"]][0]
        self.assertIn("바나나", b_item["snippet"])

        self.assertEqual([m["id"] for m in self.store.list(q="바나나", date_from="2026-01-02")],
                         [b["id"]])
        self.assertEqual([m["id"] for m in self.store.list(date_to="2026-01-01")], [a["id"]])
        self.assertEqual({m["id"] for m in self.store.list(status="done")}, {a["id"], b["id"]})
        self.assertEqual([m["id"] for m in self.store.list(limit=1)], [c["id"]])
        self.assertEqual(self.store.list(limit=0), [])

    def test_list_search_is_case_insensitive(self):
        # 찾는 말을 40자 뒤에 둬 제목(앞 40자)에는 없게 한다 - 본문 검색만 대소문자를 무시하는지 본다
        meta = self.add(recorded_at="2026-01-01T10:00:00")
        self.store.set_transcript(meta["id"], "가" * 50 + "Hello World")
        for q in ("hello", "HELLO", "HeLLo"):
            found = self.store.list(q=q)
            self.assertEqual([m["id"] for m in found], [meta["id"]], q)

    def test_list_search_matches_title(self):
        # 제목만 다른 말을 담게 바꿔 둔다 - 본문에 없는 말도 제목으로 찾아야 한다
        meta = self.add(recorded_at="2026-01-01T10:00:00")
        self.store.set_transcript(meta["id"], "본문에는 없는 말")
        mpath = self.store.meta_dir / (meta["id"] + ".json")
        stored = json.loads(mpath.read_text(encoding="utf-8"))
        stored["title"] = "특별한 제목"
        mpath.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        found = self.store.list(q="특별한")
        self.assertEqual([m["id"] for m in found], [meta["id"]])
        self.assertNotIn("특별한", found[0]["snippet"])
        self.assertEqual(self.store.list(q="없는말"), [])

    def test_list_search_snippet_window_is_forty_each_side(self):
        meta = self.add(recorded_at="2026-01-01T10:00:00")
        text = "가" * 50 + "찾는말" + "나" * 50
        self.store.set_transcript(meta["id"], text)
        found = self.store.list(q="찾는말")
        self.assertEqual(len(found), 1)
        idx = text.index("찾는말")
        self.assertEqual(found[0]["snippet"], text[idx - 40:idx + len("찾는말") + 40])
        self.assertTrue(found[0]["snippet"].startswith("가" * 40))
        self.assertTrue(found[0]["snippet"].endswith("나" * 40))

    # 8
    def test_pending_ids(self):
        a = self.add()
        b = self.add()
        c = self.add()
        self.store.set_status(b["id"], "transcribing")
        self.store.set_status(c["id"], "done")
        self.assertEqual(set(self.store.pending_ids()), {a["id"], b["id"]})

    # 9
    def test_delete_removes_three_files(self):
        meta = self.add(b"bye", recorded_at="2026-02-03T00:00:00")
        self.store.set_transcript(meta["id"], "지울 글")
        audio = self.store.audio_path(meta["id"])
        txt = self.root / "transcripts" / "2026-02-03" / (meta["id"] + ".txt")
        json_path = self.root / "meta" / (meta["id"] + ".json")
        self.assertTrue(audio.exists() and txt.exists() and json_path.exists())

        self.assertTrue(self.store.delete(meta["id"]))
        self.assertFalse(audio.exists())
        self.assertFalse(txt.exists())
        self.assertFalse(json_path.exists())
        self.assertIsNone(self.store.get(meta["id"]))
        self.assertFalse(self.store.delete(meta["id"]))

    # 10
    def test_bad_id(self):
        self.assertIsNone(self.store.get("../x"))
        self.assertIsNone(self.store.audio_path("../x"))
        with self.assertRaises(ValueError):
            self.store.set_status("../x", "done")
        with self.assertRaises(ValueError):
            self.store.set_transcript("../x", "글")
        with self.assertRaises(ValueError):
            self.store.delete("../x")

    # 11
    def test_stats_by_date(self):
        a = self.add(recorded_at="2026-05-01T01:00:00")
        b = self.add(recorded_at="2026-05-01T02:00:00")
        c = self.add(recorded_at="2026-05-02T03:00:00")
        self.store.set_transcript(a["id"], "가나다")
        self.store.set_transcript(b["id"], "라마바사")
        self.store.set_status(c["id"], "failed", "까닭")

        stats = self.store.stats()
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["done"], 2)
        self.assertEqual(stats["pending"], 0)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["chars"], 7)
        self.assertEqual(stats["by_date"], {"2026-05-01": 2, "2026-05-02": 1})

    # 12
    def test_answers_crud(self):
        rid = self.add()["id"]
        answer = self.store.add_answer("summary", "요약해 줘", [rid])
        self.assertRegex(answer["id"], r"^a-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(answer["status"], "running")
        self.assertIsNone(answer["answer"])
        self.assertEqual(answer["ids"], [rid])

        self.assertEqual(self.store.get_answer(answer["id"])["prompt"], "요약해 줘")
        self.store.set_answer(answer["id"], "done", answer="짧은 답")
        got = self.store.get_answer(answer["id"])
        self.assertEqual(got["status"], "done")
        self.assertEqual(got["answer"], "짧은 답")

        about = self.store.list_answers()[0]["about"]                             # 무엇에 대한 답인지: 첫 녹취의 때·첫마디
        self.assertEqual(about, {"recorded_at": self.store.get(rid)["recorded_at"], "title": self.store.get(rid)["title"]})
        gone = self.store.add_answer("summary", "", ["r-20200101-000000-abcd"])   # 녹취가 지워진 답
        self.assertIsNone([a for a in self.store.list_answers() if a["id"] == gone["id"]][0]["about"])
        self.assertIs(self.store.delete_answer(gone["id"]), "running")
        self.store.set_answer(gone["id"], "failed", error="x")
        self.assertIs(self.store.delete_answer(gone["id"]), True)
        other = self.store.add_answer("keywords", "", [rid])
        self.assertEqual({a["id"] for a in self.store.list_answers()},
                         {answer["id"], other["id"]})
        self.assertEqual(len(self.store.list_answers(limit=1)), 1)
        self.assertIsNone(self.store.get_answer("a-20260101-000000-0000"))
        with self.assertRaises(ValueError):
            self.store.set_answer("../x", "done")

        running = self.store.add_answer("summary", "", [rid])
        self.assertEqual(self.store.delete_answer(running["id"]), "running")      # 묻는 중인 답은 안 지운다
        self.assertIsNotNone(self.store.get_answer(running["id"]))
        self.assertIs(self.store.delete_answer(answer["id"]), True)
        self.assertIsNone(self.store.get_answer(answer["id"]))
        self.assertIs(self.store.delete_answer(answer["id"]), False)
        self.assertIs(self.store.delete_answer("../meta/x"), False)
        self.assertIsNotNone(self.store.get(rid))                                 # 녹취는 그대로

    # 13

    def test_location_saved_and_returned(self):
        meta = self.add(recorded_at="2026-03-01T10:00:00",
                        location={"lat": "37.5", "lon": 127.0, "accuracy": 12})
        want = {"lat": 37.5, "lon": 127.0, "accuracy": 12.0}
        self.assertEqual(meta["location"], want)
        self.assertEqual(self.store.get(meta["id"])["location"], want)
        self.assertEqual(self.store.list()[0]["location"], want)
        self.assertIsNone(self.add()["location"])

    # 14
    def test_invalid_location_stored_as_none(self):
        cases = [
            {"lat": 91, "lon": 0, "accuracy": 5},
            {"lat": "abc", "lon": 0, "accuracy": 5},
            {"lat": float("nan"), "lon": 0, "accuracy": 5},
            {"lat": 0, "lon": 181, "accuracy": 5},
            {"lat": 0, "lon": 0, "accuracy": -1},
            {"lat": float("inf"), "lon": 0, "accuracy": 5},
        ]
        for loc in cases:
            meta = self.add(location=loc)
            self.assertIsNone(meta["location"], loc)
            self.assertEqual(self.store.audio_path(meta["id"]).read_bytes(), b"abc")
            self.assertIsNone(self.store.get(meta["id"])["location"])

    # 15
    def test_old_meta_without_location_returns_none(self):
        meta = self.add(recorded_at="2026-04-01T10:00:00")
        path = self.root / "meta" / (meta["id"] + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["location"]
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(self.store.get(meta["id"])["location"])
        self.assertIsNone(self.store.list()[0]["location"])

    # 16
    def test_recorded_at_with_offset_uses_local_date(self):
        meta = self.add(recorded_at="2026-11-16T08:00:00.000+09:00")
        self.store.set_transcript(meta["id"], "오프셋")
        txt = self.root / "transcripts" / "2026-11-16" / (meta["id"] + ".txt")
        self.assertTrue(txt.exists())

    # 17
    def test_list_orders_by_parsed_datetime_across_offsets(self):
        a = self.add(recorded_at="2026-01-01T10:00:00+09:00")
        b = self.add(recorded_at="2026-01-01T02:00:00+00:00")
        c = self.add(recorded_at="2026-01-01T03:00:00Z")
        self.assertEqual([m["id"] for m in self.store.list()],
                         [c["id"], b["id"], a["id"]])

    # 18
    def test_two_threads_add_unique_ids(self):
        ids = []
        lock = threading.Lock()

        def worker(n):
            local = []
            for i in range(20):
                meta = self.store.add_recording(b"x", "audio/webm",
                                                client_id="t{}-{}".format(n, i))
                local.append(meta["id"])
            with lock:
                ids.extend(local)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)
        self.assertEqual(len(self.store.list(limit=100)), 40)

    # ---- R33-N14: 파일로 받기·잠금·캐시 ----

    def incoming(self, data=b"abc"):
        path = self.store.incoming_path()
        path.write_bytes(data)
        return path

    # 19
    def test_add_recording_file_moves_file(self):
        path = self.incoming(b"hello")
        self.assertEqual(path.parent, self.root / "incoming")
        meta = self.store.add_recording_file(path, "audio/webm;codecs=opus",
                                             recorded_at="2026-01-02T03:04:05",
                                             client_id="f1")
        self.assertFalse(path.exists())
        self.assertEqual(meta["size"], 5)
        self.assertEqual(meta["mime"], "audio/webm")
        self.assertEqual(meta["status"], "pending")
        self.assertNotIn("duplicate", meta)
        self.assertEqual(self.store.audio_path(meta["id"]).read_bytes(), b"hello")
        self.assertEqual(list((self.root / "incoming").iterdir()), [])
        self.assertNotEqual(self.store.incoming_path(), self.store.incoming_path())

    # 20
    def test_add_recording_file_duplicate_deletes_received(self):
        first = self.store.add_recording_file(self.incoming(b"one"), "audio/webm",
                                              client_id="dup")
        path = self.incoming(b"two")
        second = self.store.add_recording_file(path, "audio/webm", client_id="dup")
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["id"], first["id"])
        self.assertFalse(path.exists())
        self.assertEqual(len(list(self.store.audio_dir.iterdir())), 1)

    # 21
    def test_add_recording_file_invalid_deletes_received(self):
        for data, mime in ((b"x", "audio/flac"), (b"", "audio/webm")):
            path = self.incoming(data)
            with self.assertRaises(ValueError):
                self.store.add_recording_file(path, "audio/flac" if data else mime)
            self.assertFalse(path.exists())
        path = self.incoming(b"")
        with self.assertRaises(ValueError):
            self.store.add_recording_file(path, "audio/webm")
        self.assertFalse(path.exists())
        with mock.patch.object(store_mod, "MAX_AUDIO_BYTES", 10):
            big = self.incoming(b"x" * 11)
            with self.assertRaises(ValueError):
                self.store.add_recording_file(big, "audio/webm")
            self.assertFalse(big.exists())
            ok = self.store.add_recording_file(self.incoming(b"x" * 10), "audio/webm")
            self.assertEqual(ok["size"], 10)
        self.assertEqual(self.store.stats()["count"], 1)

    # 22
    def test_same_client_id_concurrent_makes_one_meta(self):
        real = store_mod.os.replace
        gate = threading.Event()

        def slow(src, dst):
            if str(dst).startswith(str(self.store.audio_dir)):
                gate.wait(0.3)
            return real(src, dst)

        results = []
        paths = [self.incoming(b"a"), self.incoming(b"b")]

        def worker(p):
            results.append(self.store.add_recording_file(p, "audio/webm", client_id="same"))

        with mock.patch.object(store_mod.os, "replace", slow):
            threads = [threading.Thread(target=worker, args=(p,)) for p in paths]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(len(results), 2)
        self.assertEqual(len({r["id"] for r in results}), 1)
        self.assertEqual(sum(1 for r in results if r.get("duplicate")), 1)
        self.assertEqual(len(list((self.root / "meta").glob("*.json"))), 1)
        self.assertEqual(len(list(self.store.audio_dir.iterdir())), 1)
        self.assertEqual(list((self.root / "incoming").iterdir()), [])

    # 23
    def test_lock_not_held_during_slow_move(self):
        real = store_mod.os.replace
        started = threading.Event()
        release = threading.Event()

        def slow(src, dst):
            if str(dst).startswith(str(self.store.audio_dir)):
                started.set()
                release.wait(5)
            return real(src, dst)

        other = self.add(b"y", recorded_at="2026-01-01T00:00:00")
        path = self.incoming(b"big")
        out = {}

        def uploader():
            out["meta"] = self.store.add_recording_file(path, "audio/webm")

        with mock.patch.object(store_mod.os, "replace", slow):
            t = threading.Thread(target=uploader)
            t.start()
            try:
                self.assertTrue(started.wait(5))
                got = {}

                def reader():
                    got["list"] = self.store.list()
                    got["get"] = self.store.get(other["id"])

                r = threading.Thread(target=reader)
                r.start()
                r.join(2)
                self.assertFalse(r.is_alive(), "업로드가 잠금을 잡고 있다")
                self.assertEqual([m["id"] for m in got["list"]], [other["id"]])
                self.assertEqual(got["get"]["id"], other["id"])
            finally:
                release.set()
                t.join(5)
        self.assertEqual(len(self.store.list()), 2)
        self.assertEqual(self.store.audio_path(out["meta"]["id"]).read_bytes(), b"big")

    # 24
    def test_init_clears_incoming_leftovers(self):
        stale = self.incoming(b"dead")
        self.assertTrue(stale.exists())
        Store(self.root)
        self.assertFalse(stale.exists())
        self.assertTrue((self.root / "incoming").is_dir())

    # 25
    def test_list_cache_refreshes_after_set_transcript_and_delete(self):
        meta = self.add(recorded_at="2026-01-01T10:00:00")
        self.store.set_transcript(meta["id"], "첫째 글")
        self.assertEqual(self.store.list()[0]["snippet"], "첫째 글")
        with mock.patch.object(Store, "_read_transcript",
                               side_effect=AssertionError("캐시를 안 씀")):
            self.assertEqual(self.store.list()[0]["snippet"], "첫째 글")
        self.store.set_transcript(meta["id"], "둘째 글")
        self.assertEqual(self.store.list()[0]["snippet"], "둘째 글")
        self.assertEqual([m["id"] for m in self.store.list(q="둘째")], [meta["id"]])
        self.assertEqual(self.store.list(q="첫째"), [])
        self.store.delete(meta["id"])
        self.assertEqual(self.store.list(), [])

    # 26
    def test_list_cache_skips_rereading_unchanged_files(self):
        meta = self.add(recorded_at="2026-01-01T10:00:00")
        self.store.set_transcript(meta["id"], "글")
        self.store.list()
        real_open = open
        opened = []

        def spy(file, *a, **k):
            opened.append(str(file))
            return real_open(file, *a, **k)

        with mock.patch("builtins.open", spy):
            self.store.list()
        self.assertFalse([p for p in opened if p.endswith(".txt")])


if __name__ == "__main__":
    unittest.main()
