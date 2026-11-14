"""dict_server.py · serve.py /api/* 시험. 진짜 외부망은 부르지 않습니다(가짜 opener).

    python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_dict_server.py'
"""
import functools
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

P = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(P))

import dict_server as ds  # noqa: E402
import serve  # noqa: E402
import trend_store  # noqa: E402

KEY = "SECRETKEY123"


class FakeResp:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")

    def read(self):
        return self.body

    def close(self):
        pass


class Opener:
    def __init__(self, body=b"", exc=None):
        self.body, self.exc, self.calls = body, exc, []

    def __call__(self, req, timeout=None):
        self.calls.append((req, timeout))
        if self.exc:
            raise self.exc
        return FakeResp(self.body)

    @property
    def url(self):
        return self.calls[-1][0].full_url


def llm(text):
    return json.dumps({"choices": [{"message": {"content": text}}]})


class Base(unittest.TestCase):
    def setUp(self):
        ds._CACHE.clear()


class TestSources(Base):
    def test_wiki_found(self):
        o = Opener(json.dumps({"query": {"pages": [{"title": "한국", "pageid": 1}]}}))
        r = ds.lookup("한국", "wiktionary", env={}, opener=o)
        self.assertTrue(r["ok"] and r["found"])
        self.assertEqual((r["source"], r["via"]), ("wiktionary", "server"))
        self.assertIn("ko.wiktionary.org", o.url)
        self.assertIn("redirects=1", o.url)

    def test_wiki_missing(self):
        o = Opener(json.dumps({"query": {"pages": [{"title": "가나다라", "missing": True}]}}))
        r = ds.lookup("가나다라", "wikipedia", env={}, opener=o)
        self.assertTrue(r["ok"])
        self.assertFalse(r["found"])
        self.assertIn("ko.wikipedia.org", o.url)

    def test_stdict_found_and_key_in_query(self):
        o = Opener(json.dumps({"channel": {"total": 2, "item": [{"word": "한^국"}]}}))
        r = ds.lookup("한국", "stdict", env={"STDICT_API_KEY": KEY}, opener=o)
        self.assertTrue(r["found"])
        self.assertIn("key=" + KEY, o.url)
        self.assertNotIn(KEY, json.dumps(r))

    def test_stdict_empty_body_is_not_found(self):
        r = ds.lookup("한국", "stdict", env={"STDICT_API_KEY": KEY}, opener=Opener(b""))
        self.assertTrue(r["ok"])
        self.assertFalse(r["found"])

    def test_opendict_total(self):
        env = {"OPENDICT_API_KEY": KEY}
        r1 = ds.lookup("한국", "opendict", env=env, opener=Opener(json.dumps({"channel": {"total": "3"}})))
        r0 = ds.lookup("가가가", "opendict", env=env, opener=Opener(json.dumps({"channel": {"total": 0}})))
        self.assertTrue(r1["found"])
        self.assertFalse(r0["found"])

    def test_krdict_xml(self):
        env = {"KRDICT_API_KEY": KEY}
        xml1 = "<?xml version='1.0'?><channel><total>1</total><item/></channel>"
        xml0 = "<?xml version='1.0'?><channel><total>0</total></channel>"
        self.assertTrue(ds.lookup("한국", "krdict", env=env, opener=Opener(xml1))["found"])
        self.assertFalse(ds.lookup("가가가", "krdict", env=env, opener=Opener(xml0))["found"])
        bad = ds.lookup("나라", "krdict", env=env, opener=Opener("<a><b></a>"))
        self.assertFalse(bad["ok"])

    def test_llm_answers(self):
        env = {"GEMINI_API_KEY": KEY}
        for text, expect in (("예", True), ("  예.", True), ("Yes!", True), ("아니오", False), ("No", False)):
            ds._CACHE.clear()
            r = ds.lookup("한국", "gemini", env=env, opener=Opener(llm(text)))
            self.assertTrue(r["ok"], text)
            self.assertEqual(r["found"], expect, text)

    def test_llm_nonsense_is_error(self):
        r = ds.lookup("한국", "gemini", env={"GEMINI_API_KEY": KEY}, opener=Opener(llm("글쎄요")))
        self.assertFalse(r["ok"])
        self.assertIn("알 수 없는 답", r["error"])

    def test_llm_request_shape_bearer(self):
        o = Opener(llm("예"))
        ds.lookup("한국", "gemini", env={"GEMINI_API_KEY": KEY}, opener=o)
        req = o.calls[-1][0]
        self.assertTrue(req.full_url.endswith("/chat/completions"))
        self.assertEqual(req.get_header("Authorization"), "Bearer " + KEY)
        body = json.loads(req.data)
        self.assertEqual((body["max_tokens"], body["temperature"]), (1024, 0))
        self.assertEqual(body["model"], "gemini-2.5-flash")
        self.assertEqual(body["messages"][1]["content"], "낱말: 한국")
        self.assertNotIn(KEY, req.full_url)

    def test_kisti_base_url_from_fleet_toml(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "fleet.toml"
            fake.write_text('[providers.kisti]\nbase_url = "https://kisti.example/v9/"\nmodels = ["m-one", "m-two"]\n',
                            encoding="utf-8")
            old = ds.FLEET_TOML
            ds.FLEET_TOML = fake
            try:
                o = Opener(llm("예"))
                ds.lookup("한국", "kistillm", env={"KISTI_API_KEY": KEY}, opener=o)
            finally:
                ds.FLEET_TOML = old
        self.assertEqual(o.url, "https://kisti.example/v9/chat/completions")
        self.assertEqual(json.loads(o.calls[-1][0].data)["model"], "m-one")

    def test_fleet_toml_missing_falls_back(self):
        old = ds.FLEET_TOML
        ds.FLEET_TOML = Path(tempfile.gettempdir()) / "없는-fleet.toml"
        try:
            o = Opener(llm("예"))
            ds.lookup("한국", "exaone", env={"EXAONE_API_KEY": KEY}, opener=o)
            self.assertTrue(o.url.startswith("https://api.exaone.ai/v1/"))
        finally:
            ds.FLEET_TOML = old

    def test_openrouter_model_env(self):
        o = Opener(llm("예"))
        ds.lookup("한국", "openrouter-free", env={"OPENROUTER_API_KEY": KEY, "OPENROUTER_FREE_MODEL": "x/y:free"}, opener=o)
        self.assertEqual(json.loads(o.calls[-1][0].data)["model"], "x/y:free")


class TestReasoningLLM(Base):
    ENV = {"GEMINI_API_KEY": KEY}

    def _resp(self, content, finish="stop"):
        return json.dumps({"choices": [{"finish_reason": finish, "message": {"content": content}}]})

    def test_think_block_stripped(self):
        for t in ("<think>음 생각 중 아니오?</think>\n예", "<thought>x</thought>예"):
            ds._CACHE.clear()
            r = ds.lookup("한국", "gemini", env=self.ENV, opener=Opener(self._resp(t)))
            self.assertTrue(r["ok"] and r["found"], t)

    def test_empty_with_length_is_truncated_error(self):
        r = ds.lookup("한국", "gemini", env=self.ENV, opener=Opener(self._resp("", "length")))
        self.assertFalse(r["ok"])
        self.assertIn("답이 잘렸습니다", r["error"])

    def test_empty_without_length_is_empty_answer(self):
        r = ds.lookup("한국", "gemini", env=self.ENV, opener=Opener(self._resp("<think>a</think>", "stop")))
        self.assertEqual(r["error"], "빈 답")

    def test_429_message_hides_key(self):
        exc = urllib.error.HTTPError(f"https://x/?key={KEY}", 429, f"Too many {KEY}", {}, None)
        r = ds.lookup("한국", "gemini", env=self.ENV, opener=Opener(exc=exc))
        self.assertEqual(r["error"], "요청 한도 초과(429) - 잠시 뒤 다시")
        self.assertNotIn(KEY, json.dumps(r, ensure_ascii=False))

    def test_default_timeouts_by_kind(self):
        o = Opener(self._resp("예"))
        ds.lookup("한국", "gemini", env=self.ENV, opener=o)
        self.assertEqual(o.calls[-1][1], 30)
        o = Opener(json.dumps({"query": {"pages": [{"title": "x"}]}}))
        ds.lookup("한국", "wiktionary", env={}, opener=o)
        self.assertEqual(o.calls[-1][1], 8)


class TestErrors(Base):
    def test_missing_key(self):
        o = Opener()
        r = ds.lookup("한국", "stdict", env={}, opener=o)
        self.assertEqual(r["ok"], False)
        self.assertEqual(r["error"], "키가 없습니다: STDICT_API_KEY")
        self.assertEqual(o.calls, [])

    def test_http_error_hides_key(self):
        url = f"https://stdict.korean.go.kr/api/search.do?key={KEY}&q=x"
        exc = urllib.error.HTTPError(url, 403, f"Forbidden {KEY}", {}, None)
        r = ds.lookup("한국", "stdict", env={"STDICT_API_KEY": KEY}, opener=Opener(exc=exc))
        self.assertFalse(r["ok"])
        self.assertIn("403", r["error"])
        self.assertNotIn(KEY, json.dumps(r, ensure_ascii=False))

    def test_timeout_and_urlerror(self):
        r = ds.lookup("한국", "wiktionary", env={}, opener=Opener(exc=TimeoutError(f"t {KEY}")))
        self.assertIn("시간 초과", r["error"])
        r = ds.lookup("나라", "wiktionary", env={}, opener=Opener(exc=urllib.error.URLError(f"dns {KEY}")))
        self.assertFalse(r["ok"])
        self.assertNotIn(KEY, r["error"])

    def test_broken_json(self):
        r = ds.lookup("한국", "wiktionary", env={}, opener=Opener(b"{not json"))
        self.assertFalse(r["ok"])
        self.assertIn("JSON", r["error"])

    def test_unexpected_exception_is_contained(self):
        r = ds.lookup("한국", "gemini", env={"GEMINI_API_KEY": KEY}, opener=Opener(exc=RuntimeError(KEY)))
        self.assertFalse(r["ok"])
        self.assertNotIn(KEY, json.dumps(r))

    def test_bad_word_shapes_never_call_opener(self):
        o = Opener()
        for w in ("", "abc", "한 국", "가나다라마바사아자차카", "한국1", "ㄱㄴ", "한국\n", None):
            r = ds.lookup(w, "wiktionary", env={}, opener=o)
            self.assertFalse(r["ok"], repr(w))
        self.assertEqual(o.calls, [])

    def test_unknown_source(self):
        self.assertFalse(ds.lookup("한국", "nope", env={}, opener=Opener())["ok"])


class TestCustom(Base):
    def test_http_rejected(self):
        o = Opener(llm("예"))
        r = ds.lookup("한국", "custom", env={}, opener=o, custom={"base_url": "http://x.example/v1", "model": "m", "key": KEY})
        self.assertFalse(r["ok"])
        self.assertIn("https://", r["error"])
        self.assertEqual(o.calls, [])
        self.assertNotIn(KEY, json.dumps(r))

    def test_custom_ok(self):
        o = Opener(llm("아니오"))
        c = {"base_url": "https://llm.example/v1/", "model": "m1", "key": KEY}
        r = ds.lookup("한국", "custom", env={}, opener=o, custom=c)
        self.assertTrue(r["ok"])
        self.assertFalse(r["found"])
        self.assertEqual(o.url, "https://llm.example/v1/chat/completions")
        self.assertEqual(o.calls[-1][0].get_header("Authorization"), "Bearer " + KEY)

    def test_custom_missing_model(self):
        r = ds.lookup("한국", "custom", env={}, opener=Opener(), custom={"base_url": "https://a.example", "model": ""})
        self.assertFalse(r["ok"])

    def test_custom_cache_separate_by_endpoint(self):
        o1, o2 = Opener(llm("예")), Opener(llm("아니오"))
        ds.lookup("한국", "custom", env={}, opener=o1, custom={"base_url": "https://a.example/v1", "model": "m"})
        r = ds.lookup("한국", "custom", env={}, opener=o2, custom={"base_url": "https://b.example/v1", "model": "m"})
        self.assertEqual(len(o2.calls), 1)
        self.assertFalse(r["found"])


class TestCacheEnv(Base):
    def test_cache_second_call_skips_opener(self):
        o = Opener(json.dumps({"query": {"pages": [{"title": "한국"}]}}))
        a = ds.lookup("한국", "wiktionary", env={}, opener=o)
        b = ds.lookup("한국", "wiktionary", env={}, opener=o)
        self.assertEqual(len(o.calls), 1)
        self.assertEqual(a, b)

    def test_errors_not_cached(self):
        o = Opener(b"{bad")
        ds.lookup("한국", "wiktionary", env={}, opener=o)
        ds.lookup("한국", "wiktionary", env={}, opener=o)
        self.assertEqual(len(o.calls), 2)

    def test_cache_limit(self):
        o = Opener(json.dumps({"query": {"pages": [{"title": "한국"}]}}))
        old = ds.CACHE_MAX
        ds.CACHE_MAX = 2
        try:
            for w in ("가나", "다라", "마바"):
                ds.lookup(w, "wiktionary", env={}, opener=o)
            self.assertEqual(len(ds._CACHE), 2)
        finally:
            ds.CACHE_MAX = old

    def test_available_sources_no_key_values(self):
        env = {"STDICT_API_KEY": KEY, "GEMINI_API_KEY": KEY}
        lst = ds.available_sources(env)
        self.assertNotIn(KEY, json.dumps(lst, ensure_ascii=False))
        by = {s["id"]: s for s in lst}
        self.assertEqual(set(by), set(ds.SOURCES))
        self.assertTrue(by["stdict"]["available"] and by["stdict"]["needs_key"])
        self.assertFalse(by["krdict"]["available"])
        self.assertTrue(by["wiktionary"]["available"] and not by["wiktionary"]["needs_key"])
        self.assertTrue(by["gemini"]["browser_direct"] and not by["stdict"]["browser_direct"])

    def test_load_env_given_dict_only(self):
        self.assertEqual(ds.load_env({"A": "1"}), {"A": "1"})

    def test_load_env_reads_dotenv_without_overriding(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".env").write_text('# c\nNEW_ONE="값1"\nPATH=zzz\nQ=\'x\'\n깨진줄\n', encoding="utf-8")
            old = ds.ROOT
            ds.ROOT = Path(d)
            try:
                e = ds.load_env()
            finally:
                ds.ROOT = old
        self.assertEqual(e["NEW_ONE"], "값1")
        self.assertEqual(e["Q"], "x")
        self.assertNotEqual(e["PATH"], "zzz")

    def test_load_env_unreadable_is_silent(self):
        old = ds.ROOT
        ds.ROOT = Path(tempfile.gettempdir()) / "없는-폴더-s5"
        try:
            self.assertIsInstance(ds.load_env(), dict)
        finally:
            ds.ROOT = old


class TestServe(Base):
    def setUp(self):
        super().setUp()
        self.calls = []
        outer = self
        self.tmp = tempfile.TemporaryDirectory()
        self.trend_file = Path(self.tmp.name) / "trend.txt"
        self.meta_file = Path(self.tmp.name) / "trend_meta.json"

        class H(serve.Handler):
            trend_path = outer.trend_file
            meta_path = outer.meta_file

            @staticmethod
            def lookup(word, source, **kw):
                outer.calls.append((word, source, kw))
                return {"ok": True, "found": True, "source": source, "via": "server", "evidence": "가짜"}

        self.httpd = serve.ThreadedServer(("127.0.0.1", 0), functools.partial(H, directory=str(P / "web")))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get(self, path):
        try:
            return urllib.request.urlopen(self.base + path, timeout=5)
        except urllib.error.HTTPError as e:
            return e

    def test_sources(self):
        r = self.get("/api/sources")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        ids = {s["id"] for s in json.load(r)["sources"]}
        self.assertIn("wiktionary", ids)

    def test_lookup_get(self):
        r = self.get("/api/lookup?word=%ED%95%9C%EA%B5%AD&source=stdict")
        self.assertEqual(r.status, 200)
        self.assertEqual(json.load(r)["evidence"], "가짜")
        self.assertEqual(self.calls[-1][:2], ("한국", "stdict"))

    def req(self, path, headers=None, method="GET", data=None):
        r = urllib.request.Request(self.base + path, headers=headers or {}, method=method, data=data)
        try:
            return urllib.request.urlopen(r, timeout=5)
        except urllib.error.HTTPError as e:
            return e

    def test_post_is_405_json(self):
        body = json.dumps({"word": "한국", "source": "custom",
                           "custom": {"base_url": "https://a.example/v1", "model": "m"}}).encode()
        r = self.req("/api/lookup", method="POST", data=body)
        self.assertEqual(r.code, 405)
        self.assertFalse(json.load(r)["ok"])
        self.assertEqual(self.calls, [])

    def test_foreign_host_403(self):
        for h in ("evil.example", "evil.example:80", "127.0.0.1.evil.example"):
            r = self.req("/api/sources", {"Host": h})
            self.assertEqual(r.code, 403, h)
        r = self.req("/api/lookup?word=%ED%95%9C%EA%B5%AD", {"Host": "evil.example"})
        self.assertEqual(r.code, 403)
        self.assertEqual(self.calls, [])

    def test_foreign_origin_403_and_no_lookup(self):
        r = self.req("/api/lookup?word=%ED%95%9C%EA%B5%AD&source=stdict", {"Origin": "http://evil.example"})
        self.assertEqual(r.code, 403)
        self.assertFalse(json.load(r)["ok"])
        self.assertEqual(self.calls, [])

    def test_same_origin_and_localhost_ok(self):
        r = self.req("/api/lookup?word=%ED%95%9C%EA%B5%AD&source=stdict", {"Origin": self.base})
        self.assertEqual(r.status, 200)
        self.assertEqual(len(self.calls), 1)
        port = self.httpd.server_address[1]
        r = self.req("/api/sources", {"Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"})
        self.assertEqual(r.status, 200)

    def test_unknown_api_404_json(self):
        r = self.get("/api/%EC%97%86%EB%8A%94%EA%B2%83")
        self.assertEqual(r.code, 404)
        self.assertFalse(json.load(r)["ok"])

    # --- POST /api/trend/pick (가짜 pick) ---
    def pick_post(self, body, headers=None, raw=False):
        h = {"Content-Type": "application/json", **(headers or {})}
        data = body if raw else json.dumps(body).encode()
        return self.req("/api/trend/pick", h, method="POST", data=data)

    def fake_pick(self, fn):
        self.httpd.RequestHandlerClass.func.trend_pick = staticmethod(fn)

    def test_trend_pick_ok(self):
        seen = []

        def fake(days, source, start, **kw):
            seen.append((days, source, start, kw))
            return {"ok": True, "picks": [{"date": "2026-11-15", "word": "지원"}], "titles": 3,
                    "candidates": 1, "checked": 1, "source": source}
        self.fake_pick(fake)
        r = self.pick_post({"source": "wikipedia", "days": 5, "start": "2026-11-15", "skip": ["2026-11-16"]})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.headers["Content-Type"], "application/json; charset=utf-8")
        self.assertTrue(json.load(r)["ok"])
        self.assertEqual(seen, [(5, "wikipedia", "2026-11-15", {"skip_dates": ["2026-11-16"]})])

    def test_trend_pick_bad_input_400(self):
        calls = []
        self.fake_pick(lambda *a, **k: calls.append(1) or {"ok": True})
        for body in ({"days": 0}, {"days": 15}, {"days": "7"}, {"days": True},
                     {"days": 3, "start": "내일"}, {"days": 3, "start": "2026-13-40"},
                     {"days": 3, "source": "custom"}, {"days": 3, "source": "nope"},
                     {"days": 3, "skip": "2026-11-16"}, {"days": 3, "skip": ["x"]}, [1, 2]):
            r = self.pick_post(body)
            self.assertEqual(r.code, 400, body)
            self.assertFalse(json.load(r)["ok"])
        r = self.pick_post(b"{not json", raw=True)
        self.assertEqual(r.code, 400)
        r = self.pick_post(json.dumps({"days": 3, "pad": "x" * 5000}).encode(), raw=True)
        self.assertEqual(r.code, 400)  # 4KB 상한
        self.assertEqual(calls, [])

    def test_trend_pick_content_type_must_be_json(self):
        calls = []
        self.fake_pick(lambda *a, **k: calls.append(1) or {"ok": True})
        r = self.pick_post({"days": 3}, {"Content-Type": "text/plain"})
        self.assertIn(r.code, (400, 415))
        self.assertEqual(calls, [])

    def test_trend_pick_foreign_origin_403(self):
        calls = []
        self.fake_pick(lambda *a, **k: calls.append(1) or {"ok": True})
        r = self.pick_post({"days": 3}, {"Origin": "http://evil.example"})
        self.assertEqual(r.code, 403)
        r = self.pick_post({"days": 3}, {"Host": "evil.example"})
        self.assertEqual(r.code, 403)
        self.assertEqual(calls, [])

    def test_trend_pick_busy_is_429(self):
        started, release = threading.Event(), threading.Event()

        def slow(days, source, start, **kw):
            started.set()
            release.wait(5)
            return {"ok": True, "picks": [], "titles": 0, "candidates": 0, "checked": 0, "source": source}
        self.fake_pick(slow)
        first = []
        t = threading.Thread(target=lambda: first.append(self.pick_post({"days": 3}).code))
        t.start()
        try:
            self.assertTrue(started.wait(5))
            r = self.pick_post({"days": 3})
            self.assertEqual(r.code, 429)
            self.assertEqual(json.load(r), {"ok": False, "error": "이미 고르는 중입니다"})
        finally:
            release.set()
            t.join(5)
        self.assertEqual(first, [200])
        self.assertEqual(self.pick_post({"days": 3}).code, 200)  # 끝났으니 다시 됨

    def test_get_trend_shape(self):
        self.trend_file.write_text("# 머리\n2026-11-15 지원\n2026-11-16 혐의\n", encoding="utf-8")
        r = self.get("/api/trend")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(json.load(r), {"ok": True, "trend": {"2026-11-15": "지원", "2026-11-16": "혐의"},
                                        "last_run": None})

    def test_get_trend_empty_without_files(self):
        self.assertEqual(json.load(self.get("/api/trend")), {"ok": True, "trend": {}, "last_run": None})
        self.assertFalse(self.meta_file.exists())

    def test_get_trend_foreign_origin_403(self):
        self.assertEqual(self.req("/api/trend", {"Origin": "http://evil.example"}).code, 403)
        self.assertEqual(self.req("/api/trend", {"Host": "evil.example"}).code, 403)

    def test_trend_pick_stores_and_get_sees_it(self):
        self.fake_pick(lambda days, source, start, **kw: {
            "ok": True, "picks": [{"date": "2026-11-15", "word": "지원"}], "titles": 3,
            "candidates": 1, "checked": 1, "source": source})
        body = json.load(self.pick_post({"days": 1, "start": "2026-11-15"}))
        self.assertEqual(body["added"], [{"date": "2026-11-15", "word": "지원"}])
        self.assertEqual(body["trend"], {"2026-11-15": "지원"})
        self.assertIsNotNone(body["last_run"])
        self.assertIn("2026-11-15 지원", self.trend_file.read_text(encoding="utf-8"))
        self.assertTrue(self.meta_file.exists())
        got = json.load(self.get("/api/trend"))
        self.assertEqual((got["trend"], got["last_run"]), ({"2026-11-15": "지원"}, body["last_run"]))

    def test_trend_pick_second_time_same_date_not_overwritten(self):
        for word in ("지원", "바뀜"):
            self.fake_pick(lambda days, source, start, w=word, **kw: {
                "ok": True, "picks": [{"date": "2026-11-15", "word": w}], "titles": 1,
                "candidates": 1, "checked": 1, "source": source})
            body = json.load(self.pick_post({"days": 1}))
        self.assertEqual(body["added"], [])
        self.assertEqual(trend_store.read_trend(self.trend_file), {"2026-11-15": "지원"})

    def test_trend_pick_failure_writes_no_files(self):
        self.fake_pick(lambda *a, **k: {"ok": False, "error": "제목 없음"})
        body = json.load(self.pick_post({"days": 1}))
        self.assertFalse(body["ok"])
        self.assertFalse(self.trend_file.exists())
        self.assertFalse(self.meta_file.exists())

    def test_handler_timeout_is_30(self):
        self.assertEqual(serve.Handler.timeout, 30)

    def test_other_post_still_405(self):
        r = self.req("/api/trend/other", method="POST", data=b"{}")
        self.assertEqual(r.code, 405)

    def test_static_still_served(self):
        r = self.get("/index.html")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
