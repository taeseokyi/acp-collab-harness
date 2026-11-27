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

    def test_stt_job_id_up_to_128_chars_is_kept_whole(self):
        rid = self.add()["id"]
        jid = "a" * 128                                      # stt.py 의 id 상한(128자) 끝 - 잘리면 이어받기가 404 난다
        self.store.set_job(rid, jid)
        self.assertEqual(self.store.get(rid)["stt_job"], jid)
        self.assertEqual(Store(self.root).get(rid)["stt_job"], jid)   # 다시 읽어도 그대로

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


    # ---- R49: 이름·태그·자동 태그 ----

    def test_new_meta_has_label_tag_fields(self):
        meta = self.add()
        self.assertEqual(meta["label"], "")
        self.assertEqual(meta["tags"], [])
        self.assertEqual(meta["tags_auto"], [])
        self.assertIs(meta["tags_human"], False)
        self.assertIsNone(meta["autotag"])
        got = self.store.get(meta["id"])
        self.assertEqual(got["label"], "")
        self.assertEqual(got["tags"], [])
        self.assertEqual(got["tags_auto"], [])
        self.assertIs(got["tags_human"], False)
        self.assertIsNone(got["autotag"])
        item = self.store.list()[0]
        self.assertEqual(item["label"], "")
        self.assertEqual(item["tags"], [])
        self.assertEqual(item["tags_auto"], [])
        self.assertIs(item["tags_human"], False)
        self.assertIsNone(item["autotag"])

    def test_old_meta_without_tag_fields_gets_defaults(self):
        meta = self.add(recorded_at="2026-01-01T10:00:00")
        path = self.root / "meta" / (meta["id"] + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("label", "tags", "tags_auto", "tags_human", "autotag"):
            data.pop(key, None)
        path.write_text(json.dumps(data), encoding="utf-8")
        got = self.store.get(meta["id"])
        self.assertEqual(got["label"], "")
        self.assertEqual(got["tags"], [])
        self.assertEqual(got["tags_auto"], [])
        self.assertIs(got["tags_human"], False)
        self.assertIsNone(got["autotag"])
        item = self.store.list()[0]
        self.assertEqual(item["label"], "")
        self.assertEqual(item["tags"], [])
        self.assertEqual(item["tags_auto"], [])
        self.assertIs(item["tags_human"], False)
        self.assertIsNone(item["autotag"])

    def test_set_transcript_keeps_tag_fields(self):
        rid = self.add()["id"]
        self.store.set_label_tags(rid, {"label": "이름", "tags": ["사람", "AI"]})
        self.store.set_autotag(rid, "done")
        self.store.set_transcript(rid, "받아 적은 글")
        got = self.store.get(rid)
        self.assertEqual(got["label"], "이름")
        self.assertEqual(got["tags"], ["사람", "AI"])
        self.assertEqual(got["tags_auto"], [])
        self.assertIs(got["tags_human"], True)
        self.assertEqual(got["autotag"], "done")
        self.assertEqual(got["transcript"], "받아 적은 글")

    def test_set_label_tags_label_only_keeps_tags_and_human(self):
        rid = self.add()["id"]
        self.store.set_auto_tags(rid, ["회의", "업무"])
        self.store.set_label_tags(rid, {"label": "새 이름"})
        got = self.store.get(rid)
        self.assertEqual(got["label"], "새 이름")
        self.assertEqual(got["tags"], ["회의", "업무"])
        self.assertEqual(got["tags_auto"], ["회의", "업무"])
        self.assertIs(got["tags_human"], False)
        self.assertEqual(got["autotag"], "done")

    def test_set_label_tags_tags_keeps_only_surviving_auto(self):
        rid = self.add()["id"]
        self.store.set_auto_tags(rid, ["회의", "업무", "AI3"])
        self.store.set_label_tags(rid, {"tags": ["회의", "사람", "ai3"]})
        got = self.store.get(rid)
        self.assertEqual(got["tags"], ["회의", "사람", "ai3"])
        self.assertEqual(got["tags_auto"], ["회의", "ai3"])   # 남은 AI 태그는 새 표기로
        self.assertIs(got["tags_human"], True)
        self.assertEqual(got["label"], "")

    def test_set_label_tags_empty_tags(self):
        rid = self.add()["id"]
        self.store.set_auto_tags(rid, ["회의", "업무"])
        self.store.set_label_tags(rid, {"tags": []})
        got = self.store.get(rid)
        self.assertEqual(got["tags"], [])
        self.assertEqual(got["tags_auto"], [])
        self.assertIs(got["tags_human"], True)

    def test_set_label_tags_same_tags_keeps_auto_and_human(self):
        rid = self.add()["id"]
        self.store.set_auto_tags(rid, ["회의", "업무"])
        before = self.store.get(rid)
        self.store.set_label_tags(rid, {"label": "이름", "tags": ["회의", "업무"]})
        got = self.store.get(rid)
        self.assertEqual(got["label"], "이름")
        self.assertEqual(got["tags"], before["tags"])
        self.assertEqual(got["tags_auto"], before["tags_auto"])
        self.assertIs(got["tags_human"], False)
        self.assertEqual(got["autotag"], "done")
        self.assertTrue(self.store.set_auto_tags(rid, ["새AI"]))
        got = self.store.get(rid)
        self.assertEqual(got["tags"], ["새AI"])
        self.assertEqual(got["tags_auto"], ["새AI"])
        self.assertIs(got["tags_human"], False)

    def test_set_label_tags_case_only_change_updates_spelling(self):
        rid = self.add()["id"]
        self.store.set_auto_tags(rid, ["python"])
        self.store.set_label_tags(rid, {"tags": ["Python"]})
        got = self.store.get(rid)
        self.assertEqual(got["tags"], ["Python"])
        self.assertEqual(got["tags_auto"], ["Python"])
        self.assertIs(got["tags_human"], False)

    def test_set_label_tags_different_tags_marks_human(self):
        rid = self.add()["id"]
        self.store.set_auto_tags(rid, ["회의", "업무"])
        self.store.set_label_tags(rid, {"label": "이름", "tags": ["업무", "회의"]})
        got = self.store.get(rid)
        self.assertEqual(got["tags"], ["업무", "회의"])
        self.assertEqual(got["tags_auto"], ["업무", "회의"])
        self.assertIs(got["tags_human"], True)

    def test_set_auto_tags_does_not_change_human_tags(self):
        rid = self.add()["id"]
        self.store.set_label_tags(rid, {"tags": ["사람", "AI"]})
        before = self.store.get(rid)
        self.assertFalse(self.store.set_auto_tags(rid, ["새AI"]))
        got = self.store.get(rid)
        self.assertEqual(got["tags"], before["tags"])
        self.assertEqual(got["tags_auto"], before["tags_auto"])
        self.assertIs(got["tags_human"], True)
        self.assertEqual(got["autotag"], "done")

    def test_set_auto_tags_auto_false_writes_tags(self):
        rid = self.add()["id"]
        tags = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"]
        self.assertTrue(self.store.set_auto_tags(rid, tags))
        got = self.store.get(rid)
        self.assertEqual(got["tags"], tags[:10])
        self.assertEqual(got["tags_auto"], tags[:10])
        self.assertIs(got["tags_human"], False)
        self.assertEqual(got["autotag"], "done")

    def test_set_auto_tags_manual_keeps_human_replaces_old_auto(self):
        rid = self.add()["id"]
        self.store.set_auto_tags(rid, ["AI1", "AI2", "공통"])
        self.store.set_label_tags(rid, {"tags": ["사람1", "ai2"]})
        self.assertIs(self.store.get(rid)["tags_human"], True)
        self.assertTrue(self.store.set_auto_tags(rid, ["새AI", "공통"], manual=True))
        got = self.store.get(rid)
        self.assertEqual(got["tags"], ["사람1", "새AI", "공통"])
        self.assertEqual(got["tags_auto"], ["새AI", "공통"])
        self.assertIs(got["tags_human"], True)
        self.assertEqual(got["autotag"], "done")

    def test_set_autotag_states_and_errors(self):
        rid = self.add()["id"]
        for state in (None, "pending", "done", "failed"):
            self.store.set_autotag(rid, state)
            self.assertEqual(self.store.get(rid)["autotag"], state)
        with self.assertRaises(ValueError):
            self.store.set_autotag(rid, "unknown")
        with self.assertRaises(ValueError):
            self.store.set_autotag("r-20200101-000000-abcd", "pending")

    def test_autotag_pending_ids(self):
        a = self.add()["id"]
        b = self.add()["id"]
        c = self.add()["id"]
        self.store.set_autotag(a, "pending")
        self.store.set_autotag(b, "done")
        self.store.set_autotag(c, "failed")
        self.assertEqual(self.store.autotag_pending_ids(), [a])

    def test_list_tag_filter_case_insensitive_and_and(self):
        a = self.add(recorded_at="2026-01-01T10:00:00")
        b = self.add(recorded_at="2026-01-02T10:00:00")
        c = self.add(recorded_at="2026-01-03T10:00:00")
        self.store.set_auto_tags(a["id"], ["회의"])
        self.store.set_auto_tags(b["id"], ["회의", "업무"])
        self.store.set_auto_tags(c["id"], ["업무"])
        self.store.set_transcript(a["id"], "사과")
        self.store.set_transcript(b["id"], "바나나")
        self.store.set_transcript(c["id"], "사과")
        self.store.set_status(b["id"], "failed")
        self.assertEqual({m["id"] for m in self.store.list(tag="회의")}, {a["id"], b["id"]})
        self.assertEqual({m["id"] for m in self.store.list(tag="회의", q="바나나")}, {b["id"]})
        self.assertEqual({m["id"] for m in self.store.list(tag="회의", status="done")}, {a["id"]})
        self.assertEqual({m["id"] for m in self.store.list(tag="업무", date_to="2026-01-02")},
                         {b["id"]})
        self.assertEqual(self.store.list(tag="없는태그"), [])

    def test_list_match_text_label_tag_and_no_q(self):
        a = self.add(recorded_at="2026-01-01T10:00:00")
        b = self.add(recorded_at="2026-01-02T10:00:00")
        c = self.add(recorded_at="2026-01-03T10:00:00")
        self.store.set_transcript(a["id"], "apple pie")
        self.store.set_transcript(b["id"], "다른 글")
        self.store.set_transcript(c["id"], "다른 글")
        self.store.set_label_tags(b["id"], {"label": "Apple 이름"})
        self.store.set_label_tags(c["id"], {"tags": ["Apple"]})
        found = {m["id"]: m for m in self.store.list(q="apple")}
        self.assertEqual(set(found), {a["id"], b["id"], c["id"]})
        self.assertEqual(found[a["id"]]["match"], "text")
        self.assertEqual(found[b["id"]]["match"], "label")
        self.assertEqual(found[c["id"]]["match"], "tag")
        self.assertEqual(found[b["id"]]["snippet"], "다른 글"[:80])
        self.assertEqual(found[c["id"]]["snippet"], "다른 글"[:80])
        for item in self.store.list():
            self.assertNotIn("match", item)


    # ---- R51: 받아쓰기 옵션·이전 글 ----

    def test_new_meta_has_stt_fields(self):
        meta = self.add()
        self.assertIsNone(meta["stt_options"])
        self.assertIsNone(meta["stt_used"])
        self.assertIsNone(meta["prev_stt_used"])
        got = self.store.get(meta["id"])
        self.assertIsNone(got["stt_options"])
        self.assertIsNone(got["stt_used"])
        self.assertIsNone(got["prev_stt_used"])
        self.assertEqual(got["transcript_prev"], "")

    def test_set_transcript_used_and_previous_text(self):
        rid = self.add(recorded_at="2026-01-01T10:00:00")["id"]
        first_used = {"preprocess": "denoise", "speakers": 1}
        self.store.set_transcript(rid, "첫 글", used=first_used)

        got = self.store.get(rid)
        self.assertEqual(got["transcript"], "첫 글")
        self.assertEqual(got["transcript_prev"], "")
        self.assertIsNone(got["prev_stt_used"])
        self.assertEqual(got["stt_used"]["preprocess"], "denoise")
        self.assertEqual(got["stt_used"]["speakers"], 1)
        self.assertIn("at", got["stt_used"])
        self.assertIsNotNone(store_mod._parse_iso(got["stt_used"]["at"]))

        second_used = {"preprocess": "none"}
        self.store.set_transcript(rid, "둘째 글", used=second_used)

        got = self.store.get(rid)
        self.assertEqual(got["transcript"], "둘째 글")
        self.assertEqual(got["transcript_prev"], "첫 글")
        prev_used = dict(got["prev_stt_used"])
        prev_used.pop("at")
        self.assertEqual(prev_used, first_used)
        self.assertEqual(got["stt_used"]["preprocess"], "none")
        prev_path = self.store.transcripts_dir / "2026-01-01" / (rid + ".prev.txt")
        self.assertEqual(prev_path.read_text(encoding="utf-8"), "첫 글")

    def test_set_transcript_same_text_keeps_previous(self):
        rid = self.add(recorded_at="2026-01-01T10:00:00")["id"]
        self.store.set_transcript(rid, "첫 글", used={"preprocess": "denoise"})
        before = self.store.get(rid)
        self.store.set_transcript(rid, "둘째 글", used={"preprocess": "none"})
        after_second = self.store.get(rid)
        self.store.set_transcript(rid, "둘째 글", used={"preprocess": "basic"})
        got = self.store.get(rid)

        self.assertEqual(got["transcript_prev"], after_second["transcript_prev"])
        self.assertEqual(got["prev_stt_used"], after_second["prev_stt_used"])
        self.assertEqual(got["stt_used"]["preprocess"], "basic")
        self.assertNotEqual(before["stt_used"]["preprocess"], "basic")

    def test_set_transcript_empty_previous_creates_no_prev(self):
        rid = self.add(recorded_at="2026-01-01T10:00:00")["id"]
        self.store.set_transcript(rid, "")
        self.store.set_transcript(rid, "새 글", used={"preprocess": "level"})
        got = self.store.get(rid)
        self.assertEqual(got["transcript_prev"], "")
        self.assertIsNone(got["prev_stt_used"])
        prev_path = self.store.transcripts_dir / "2026-01-01" / (rid + ".prev.txt")
        self.assertFalse(prev_path.exists())

    def test_set_transcript_used_none_clears_stt_used(self):
        rid = self.add()["id"]
        self.store.set_transcript(rid, "글", used={"preprocess": "denoise"})
        self.assertIsNotNone(self.store.get(rid)["stt_used"])
        self.store.set_transcript(rid, "다른 글", used=None)
        got = self.store.get(rid)
        self.assertIsNone(got["stt_used"])
        self.assertEqual(got["transcript_prev"], "글")

    def test_retranscript_keeps_label_and_tags(self):
        rid = self.add()["id"]
        self.store.set_label_tags(rid, {"label": "이름", "tags": ["사람"]})
        self.store.set_autotag(rid, "done")
        self.store.set_transcript(rid, "첫 글", used={"preprocess": "denoise"})
        self.store.set_transcript(rid, "둘째 글", used={"preprocess": "none"})
        got = self.store.get(rid)
        self.assertEqual(got["label"], "이름")
        self.assertEqual(got["tags"], ["사람"])
        self.assertIs(got["tags_human"], True)
        self.assertEqual(got["autotag"], "done")

    def test_old_meta_without_stt_fields_gets_defaults(self):
        meta = self.add(recorded_at="2026-01-01T10:00:00")
        prefix = meta["id"]
        mpath = self.store.meta_dir / (prefix + ".json")
        data = json.loads(mpath.read_text(encoding="utf-8"))
        for key in ("stt_options", "stt_used", "prev_stt_used"):
            data.pop(key, None)
        mpath.write_text(json.dumps(data), encoding="utf-8")

        got = self.store.get(prefix)
        self.assertIsNone(got["stt_options"])
        self.assertIsNone(got["stt_used"])
        self.assertIsNone(got["prev_stt_used"])
        self.assertEqual(got["transcript_prev"], "")
        item = self.store.list()[0]
        self.assertIsNone(item["stt_options"])
        self.assertIsNone(item["stt_used"])
        self.assertIsNone(item["prev_stt_used"])

    def test_default_and_effective_stt_options(self):
        self.assertEqual(self.store.default_stt_options(), {})
        self.store.set_default_stt_options({"preprocess": "level", "num_speakers": 2})
        self.assertEqual(self.store.default_stt_options(),
                         {"preprocess": "level", "num_speakers": 2})

        rid = self.add()["id"]
        meta = self.store.get(rid)
        self.assertIsNone(meta["stt_options"])
        self.assertEqual(self.store.effective_stt_options(meta),
                         {"preprocess": "level", "num_speakers": 2})

        self.store.set_stt_options(rid, {"preprocess": "denoise"})
        meta = self.store.get(rid)
        self.assertEqual(meta["stt_options"], {"preprocess": "denoise"})
        self.assertEqual(self.store.effective_stt_options(meta),
                         {"preprocess": "denoise"})
        self.assertEqual(self.store.effective_stt_options({"stt_options": None}),
                         {"preprocess": "level", "num_speakers": 2})

        self.store.set_stt_options(rid, None)
        meta = self.store.get(rid)
        self.assertIsNone(meta["stt_options"])
        self.assertEqual(self.store.effective_stt_options(meta),
                         {"preprocess": "level", "num_speakers": 2})

    def test_effective_stt_options_empty_dict_follows_defaults(self):
        self.store.set_default_stt_options({"preprocess": "denoise", "num_speakers": 2})
        rid = self.add()["id"]
        self.store.set_stt_options(rid, {})
        meta = self.store.get(rid)
        self.assertEqual(meta["stt_options"], {})
        self.assertEqual(self.store.effective_stt_options(meta),
                         {"preprocess": "denoise", "num_speakers": 2})
        self.assertEqual(self.store.effective_stt_options({"stt_options": {}}),
                         {"preprocess": "denoise", "num_speakers": 2})

        self.store.set_stt_options(rid, {"num_speakers": 3})
        self.assertEqual(self.store.effective_stt_options(self.store.get(rid)),
                         {"num_speakers": 3})

    def test_set_stt_options_errors(self):
        rid = self.add()["id"]
        with self.assertRaises(ValueError):
            self.store.set_stt_options(rid, {"preprocess": "wrong"})
        self.assertIsNone(self.store.get(rid)["stt_options"])
        with self.assertRaises(ValueError):
            self.store.set_stt_options("r-20200101-000000-abcd", {"preprocess": "none"})
        with self.assertRaises(ValueError):
            self.store.set_default_stt_options({"num_speakers": True})

    def test_broken_default_stt_options_file_is_empty(self):
        path = self.root / "stt_options.json"
        path.write_text("{oops", encoding="utf-8")
        self.assertEqual(self.store.default_stt_options(), {})
        path.write_text("[]", encoding="utf-8")
        self.assertEqual(self.store.default_stt_options(), {})
        path.write_text(json.dumps({"preprocess": "wrong"}), encoding="utf-8")
        self.assertEqual(self.store.default_stt_options(), {})

    def test_delete_removes_previous_text(self):
        rid = self.add(recorded_at="2026-02-03T00:00:00")["id"]
        self.store.set_transcript(rid, "첫 글", used={"preprocess": "denoise"})
        self.store.set_transcript(rid, "둘째 글", used={"preprocess": "none"})
        txt = self.root / "transcripts" / "2026-02-03" / (rid + ".txt")
        prev = self.root / "transcripts" / "2026-02-03" / (rid + ".prev.txt")
        self.assertTrue(txt.exists() and prev.exists())
        self.assertTrue(self.store.delete(rid))
        self.assertFalse(txt.exists())
        self.assertFalse(prev.exists())
        self.assertIsNone(self.store.get(rid))

    def test_list_and_search_ignore_previous_text(self):
        rid = self.add(recorded_at="2026-01-01T10:00:00")["id"]
        self.store.set_transcript(rid, "옛말", used={"preprocess": "denoise"})
        self.store.set_transcript(rid, "새글", used={"preprocess": "none"})

        self.assertEqual(self.store.list(q="옛말"), [])
        found = self.store.list(q="새글")
        self.assertEqual([m["id"] for m in found], [rid])
        self.assertEqual(found[0]["snippet"], "새글")
        self.assertEqual(self.store.list()[0]["snippet"], "새글")

    def test_set_transcript_keeps_longest_displaced_text(self):
        rid = self.add(recorded_at="2026-01-01T10:00:00")["id"]
        long_text = "긴" * 50
        first_used = {"preprocess": "denoise"}
        self.store.set_transcript(rid, long_text, used=first_used)
        self.store.set_transcript(rid, "아", used={"preprocess": "none"})
        got = self.store.get(rid)
        self.assertEqual(got["transcript"], "아")
        self.assertEqual(got["transcript_prev"], long_text)
        prev_used = dict(got["prev_stt_used"])
        prev_used.pop("at")
        self.assertEqual(prev_used, first_used)

        self.store.set_transcript(rid, "아.", used={"preprocess": "basic"})
        got = self.store.get(rid)
        self.assertEqual(got["transcript"], "아.")
        self.assertEqual(got["transcript_prev"], long_text)
        prev_used = dict(got["prev_stt_used"])
        prev_used.pop("at")
        self.assertEqual(prev_used, first_used)

    def test_set_transcript_previous_tracks_longest_of_displaced(self):
        rid = self.add(recorded_at="2026-01-01T10:00:00")["id"]
        a = "짧은 글"
        b = "훨씬 더 긴 두 번째 글"
        c = "세 번째 글"
        self.store.set_transcript(rid, a, used={"preprocess": "level"})
        self.store.set_transcript(rid, b, used={"preprocess": "denoise"})
        got = self.store.get(rid)
        self.assertEqual(got["transcript_prev"], a)

        self.store.set_transcript(rid, c, used={"preprocess": "basic"})
        got = self.store.get(rid)
        self.assertEqual(got["transcript"], c)
        self.assertEqual(got["transcript_prev"], b)
        prev_used = dict(got["prev_stt_used"])
        prev_used.pop("at")
        self.assertEqual(prev_used, {"preprocess": "denoise"})

    def test_set_status_failed_keeps_transcript_and_previous(self):
        rid = self.add(recorded_at="2026-01-01T10:00:00")["id"]
        self.store.set_transcript(rid, "첫 글", used={"preprocess": "level"})
        self.store.set_transcript(rid, "둘째 글", used={"preprocess": "denoise"})
        self.store.set_status(rid, "failed", "받아쓰기 실패")

        got = self.store.get(rid)
        self.assertEqual(got["status"], "failed")
        self.assertEqual(got["error"], "받아쓰기 실패")
        self.assertEqual(got["transcript"], "둘째 글")
        self.assertEqual(got["transcript_prev"], "첫 글")
        path = self.store.transcripts_dir / "2026-01-01" / (rid + ".txt")
        self.assertEqual(path.read_text(encoding="utf-8"), "둘째 글")


if __name__ == "__main__":
    unittest.main()
