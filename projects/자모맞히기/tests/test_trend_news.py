"""trend_news.py 검사 - 가짜 opener·가짜 sleep, 진짜 망은 부르지 않습니다.

    python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_trend_news.py'
"""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

P = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(P))

import trend_news as tn  # noqa: E402


def rss(*titles):
    items = "".join(f"<item><title>{t}</title><link>http://x/{i}</link></item>" for i, t in enumerate(titles))
    return f'<?xml version="1.0"?><rss><channel><title>채널 제목</title>{items}</channel></rss>'.encode("utf-8")


class Resp:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")

    def read(self, size=-1):
        if size is None or size < 0:
            return self.body
        return self.body[:size]

    def close(self):
        pass


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b""))


class FeedOpener:
    """URL 별 본문(또는 예외)을 돌려줍니다."""

    def __init__(self, table):
        self.table, self.urls = table, []

    def __call__(self, req, timeout=None):
        self.urls.append(req.full_url)
        item = self.table[req.full_url]
        if isinstance(item, Exception):
            raise item
        return Resp(item)


class Sleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


class Clock:
    """정해 둔 값을 차례로 돌려주고, 다 쓰면 마지막 값을 되풀이합니다."""

    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


def wiki_page(title, categories=None, missing=False):
    page = {"title": title}
    if missing:
        page["missing"] = True
    else:
        page["categories"] = [{"title": f"분류:{c}"} for c in (categories or [])]
    return page


class WikiOpener:
    """MediaWiki 요청마다 respond(titles 목록) 의 결과 JSON(또는 예외)을 돌려줍니다."""

    def __init__(self, respond):
        self.respond, self.requests = respond, []

    def __call__(self, req, timeout=None):
        q = parse_qs(urlsplit(req.full_url).query)
        titles = q["titles"][0].split("|")
        self.requests.append((req.full_url, q, titles))
        out = self.respond(titles, len(self.requests))
        if isinstance(out, Exception):
            raise out
        return Resp(json.dumps({"query": out}, ensure_ascii=False))


class TestFetchTitles(unittest.TestCase):
    def test_only_item_titles_and_dedupe(self):
        o = FeedOpener({"http://a.test/1": rss("첫째 기사", "둘째 기사"), "http://a.test/2": rss("둘째 기사", "셋째 기사")})
        titles = tn.fetch_titles(opener=o, feeds=["http://a.test/1", "http://a.test/2"])
        self.assertEqual(titles, ["첫째 기사", "둘째 기사", "셋째 기사"])  # 채널 제목 없음·겹침 뺌

    def test_failing_feed_is_skipped(self):
        o = FeedOpener({"http://a.test/1": urllib.error.URLError("x"), "http://a.test/2": b"<rss><not xml",
                        "http://a.test/3": rss("살아남은 기사")})
        feeds = ["http://a.test/1", "http://a.test/2", "http://a.test/3"]
        self.assertEqual(tn.fetch_titles(opener=o, feeds=feeds), ["살아남은 기사"])

    def test_feeds_are_seven_yna(self):
        self.assertEqual(len(tn.FEEDS), 7)
        self.assertTrue(all(u.startswith("https://www.yna.co.kr/rss/") for u in tn.FEEDS))

    def test_cdata_title(self):
        body = "<rss><channel><item><title><![CDATA[ 국회 협력 ]]></title></item></channel></rss>".encode()
        o = FeedOpener({"http://a.test/1": body})
        self.assertEqual(tn.fetch_titles(opener=o, feeds=["http://a.test/1"]), ["국회 협력"])

    def test_read_rejects_response_over_two_megabytes(self):
        body = b"a" * tn.MAX_BODY
        o = FeedOpener({"http://a.test/big": body})
        with self.assertRaises(ValueError):
            tn._read(o, "http://a.test/big", 10)

    def test_oversize_feed_is_skipped_and_next_feed_kept(self):
        o = FeedOpener({"http://a.test/big": b"a" * tn.MAX_BODY, "http://a.test/ok": rss("살아남은 기사")})
        titles = tn.fetch_titles(opener=o, feeds=["http://a.test/big", "http://a.test/ok"])
        self.assertEqual(titles, ["살아남은 기사"])


class TestCandidates(unittest.TestCase):
    def words(self, titles, **kw):
        return [w for w, _ in tn.candidates(titles, **kw)]

    def test_josa_stripped(self):
        got = self.words(["국회에서 협력을 논의", "정책의 방향"])
        self.assertIn("국회", got)
        self.assertIn("협력", got)
        self.assertNotIn("국회에서", got)

    def test_strip_josa_keeps_short(self):
        self.assertEqual(tn.strip_josa("국회에서"), "국회")
        self.assertEqual(tn.strip_josa("협력을"), "협력")
        self.assertEqual(tn.strip_josa("나라"), "나라")
        self.assertEqual(tn.strip_josa("지도"), "지도")  # 한 글자만 남으니 안 뗌

    def test_josa_variants_keep_original_for_long_words(self):
        self.assertEqual(tn.josa_variants("전문가"), ["전문가", "전문"])
        self.assertEqual(tn.josa_variants("어린이"), ["어린이", "어린"])
        self.assertEqual(tn.josa_variants("경기도"), ["경기도", "경기"])
        self.assertEqual(tn.josa_variants("한국의"), ["한국의", "한국"])
        self.assertEqual(tn.josa_variants("국회에서"), ["국회"])  # 2글자 조사는 떼기만
        self.assertEqual(tn.josa_variants("나라"), ["나라"])

    def test_six_unit_word_ending_in_josa_is_not_cut(self):
        # 예전에는 '나라가' → '나라'(4칸)로 잘려 후보에서 사라졌습니다.
        self.assertIn("나라가", self.words(["나라가"]))
        self.assertIn("아이도", self.words(["아이도"]))

    def test_only_six_units(self):
        got = self.words(["국회 협력 대통령 한국 가나"])
        self.assertEqual(sorted(got), ["국회", "한국", "협력"])  # 대통령(7칸)·가나(4칸) 빠짐

    def test_stop_and_existing_removed(self):
        got = self.words(["국회 협력 지원"], existing={"국회"}, stop={"협력"})
        self.assertEqual(got, ["지원"])

    def test_sorted_by_article_count_then_first_seen(self):
        titles = ["협력 지원", "국회 지원", "지원 국회 점검", "점검 협력"]
        self.assertEqual(tn.candidates(titles), [("지원", 3), ("협력", 2), ("국회", 2), ("점검", 2)])

    def test_count_once_per_title(self):
        self.assertEqual(tn.candidates(["지원 지원 지원"]), [("지원", 1)])

    def test_load_stop(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "stop.txt"
            f.write_text("# 주석\n\n종합\n  단독 \n", encoding="utf-8")
            self.assertEqual(tn.load_stop(f), {"종합", "단독"})
            self.assertEqual(tn.load_stop(Path(d) / "없음.txt"), set())

    def test_real_stop_file_has_enough_entries(self):
        stop = tn.load_stop()
        self.assertGreaterEqual(len(stop), 40)
        self.assertIn("종합", stop)

    def test_real_stop_file_has_companies_and_counties(self):
        stop = tn.load_stop()
        for word in ("삼성전자", "에스케이", "카카오", "네이버", "포스코", "한화", "롯데",
                     "파주시", "구리시", "여주시", "가평군", "완도군"):
            self.assertIn(word, stop)


class TestVerifyWiki(unittest.TestCase):
    def test_batches_of_50_joined_with_pipe_and_sleep_3(self):
        words = [f"낱말{i}" for i in range(120)]
        o = WikiOpener(lambda titles, n: {"pages": [wiki_page(t, ["한국어 명사"]) for t in titles]})
        s = Sleeper()
        got = tn.verify(words, "wiktionary", opener=o, sleep=s)
        self.assertEqual(got, words)
        self.assertEqual([len(t) for _, _, t in o.requests], [50, 50, 20])
        self.assertEqual(s.calls, [3, 3])  # 요청 사이에만
        url, q, _ = o.requests[0]
        self.assertIn("ko.wiktionary.org", url)
        self.assertEqual(q["prop"], ["categories"])
        self.assertEqual(q["cllimit"], ["max"])
        self.assertEqual(q["redirects"], ["1"])
        self.assertEqual(q["formatversion"], ["2"])

    def test_noun_category_only_and_order_kept(self):
        pages = {"가나": wiki_page("가나", ["한국어 명사"]), "다라": wiki_page("다라", ["한국어 동사"]),
                 "마바": wiki_page("마바", missing=True), "사아": wiki_page("사아", ["한국어 명사", "기타"])}
        o = WikiOpener(lambda titles, n: {"pages": [pages[t] for t in titles]})
        got = tn.verify(["사아", "마바", "다라", "가나"], "wiktionary", opener=o, sleep=Sleeper())
        self.assertEqual(got, ["사아", "가나"])

    def test_wikipedia_needs_no_category(self):
        o = WikiOpener(lambda titles, n: {"pages": [wiki_page("가나"), wiki_page("다라", missing=True)]})
        got = tn.verify(["가나", "다라"], "wikipedia", opener=o, sleep=Sleeper())
        self.assertEqual(got, ["가나"])
        self.assertIn("ko.wikipedia.org", o.requests[0][0])

    def test_normalized_and_redirects_mapped_back(self):
        def respond(titles, n):
            return {"normalized": [{"from": "가나", "to": "가나다"}],
                    "redirects": [{"from": "가나다", "to": "최종"}, {"from": "옛말", "to": "최종"}],
                    "pages": [wiki_page("최종", ["한국어 명사"])]}
        got = tn.verify(["가나", "옛말", "없음"], "wiktionary", opener=WikiOpener(respond), sleep=Sleeper())
        self.assertEqual(got, ["가나", "옛말"])

    def test_limit(self):
        o = WikiOpener(lambda titles, n: {"pages": [wiki_page(t, ["명사"]) for t in titles]})
        got = tn.verify([f"낱{i}" for i in range(80)], "wiktionary", opener=o, sleep=Sleeper(), limit=60)
        self.assertEqual(len(got), 60)

    def test_checked_counts_words_actually_asked(self):
        words = [f"낱{i}" for i in range(120)]
        o = WikiOpener(lambda titles, n: {"pages": [wiki_page(t, ["명사"]) for t in titles]})
        state = {}
        got = tn.verify(words, "wiktionary", opener=o, sleep=Sleeper(), state=state)
        self.assertEqual(got, words)
        self.assertEqual(state.get("checked"), 120)
        self.assertNotIn("stopped", state)

    def test_deadline_stops_early_and_reports_actual_checked(self):
        words = [f"낱{i}" for i in range(120)]
        o = WikiOpener(lambda titles, n: {"pages": [wiki_page(t, ["명사"]) for t in titles]})
        state = {}
        got = tn.verify(words, "wiktionary", opener=o, sleep=Sleeper(),
                        until=120, clock=Clock(0, 500), state=state)
        self.assertEqual(got, words[:50])
        self.assertEqual(state, {"checked": 50, "stopped": "deadline"})
        self.assertEqual(len(o.requests), 1)

    def test_429_once_then_retry(self):
        def respond(titles, n):
            if n == 1:
                return http_error(429)
            return {"pages": [wiki_page(t, ["명사"]) for t in titles]}
        s = Sleeper()
        o = WikiOpener(respond)
        got = tn.verify(["가나", "다라"], "wiktionary", opener=o, sleep=s)
        self.assertEqual(got, ["가나", "다라"])
        self.assertEqual(s.calls, [10])
        self.assertEqual(len(o.requests), 2)

    def test_429_twice_ends_with_what_was_checked(self):
        words = [f"낱{i}" for i in range(120)]

        def respond(titles, n):
            if n == 1:
                return {"pages": [wiki_page(t, ["명사"]) for t in titles]}
            return http_error(429)
        s = Sleeper()
        o = WikiOpener(respond)
        got = tn.verify(words, "wiktionary", opener=o, sleep=s)
        self.assertEqual(got, words[:50])
        self.assertEqual(len(o.requests), 3)  # 첫 묶음 + 둘째 묶음 429 두 번 → 끝
        self.assertEqual(s.calls, [3, 10])


class TestVerifyLookup(unittest.TestCase):
    def setUp(self):
        self.real = tn.dict_server.lookup
        self.seen = []

    def tearDown(self):
        tn.dict_server.lookup = self.real

    def test_one_by_one_with_sleep_1_and_cap_40(self):
        def fake(word, source, **kw):
            self.seen.append((word, source))
            return {"ok": True, "found": word != "낱3", "source": source}
        tn.dict_server.lookup = fake
        s = Sleeper()
        words = [f"낱{i}" for i in range(60)]
        got = tn.verify(words, "stdict", sleep=s, env={})
        self.assertEqual(len(self.seen), 40)
        self.assertEqual(len(got), 39)
        self.assertNotIn("낱3", got)
        self.assertEqual(set(s.calls), {1})
        self.assertEqual(len(s.calls), 39)

    def test_not_ok_is_not_found(self):
        tn.dict_server.lookup = lambda w, s, **kw: {"ok": False, "error": "키 없음"}
        self.assertEqual(tn.verify(["가나"], "stdict", sleep=Sleeper(), env={}), [])

    def test_429_retry_then_stop(self):
        calls = []

        def fake(word, source, **kw):
            calls.append(word)
            if word == "다라":
                return {"ok": False, "error": "요청 한도 초과(429)"}
            return {"ok": True, "found": True}
        tn.dict_server.lookup = fake
        s = Sleeper()
        got = tn.verify(["가나", "다라", "마바"], "stdict", sleep=s, env={})
        self.assertEqual(got, ["가나"])
        self.assertEqual(calls, ["가나", "다라", "다라"])
        self.assertIn(10, s.calls)


class TestPick(unittest.TestCase):
    def setUp(self):
        self.real = (tn.fetch_titles, tn.verify, tn.load_stop)
        tn.load_stop = lambda *a, **k: set()

    def tearDown(self):
        tn.fetch_titles, tn.verify, tn.load_stop = self.real

    def test_shape_and_skip_dates(self):
        tn.fetch_titles = lambda **kw: ["지원 국회 협력", "지원 국회", "지원"]
        got = {}

        def fake_verify(words, source, **kw):
            got["words"], got["source"] = list(words), source
            return list(words)
        tn.verify = fake_verify
        r = tn.pick(3, "wiktionary", "2026-11-15", skip_dates=["2026-11-16"], existing_words=set())
        self.assertTrue(r["ok"])
        self.assertEqual(r["picks"], [{"date": "2026-11-15", "word": "지원"},
                                      {"date": "2026-11-17", "word": "국회"},
                                      {"date": "2026-11-18", "word": "협력"}])
        self.assertEqual((r["titles"], r["candidates"], r["source"]), (3, 3, "wiktionary"))
        self.assertIn("checked", r)
        self.assertEqual(got["words"], ["지원", "국회", "협력"])

    def test_default_start_is_today_and_existing_removed(self):
        tn.fetch_titles = lambda **kw: ["지원 국회"]
        tn.verify = lambda words, source, **kw: list(words)
        r = tn.pick(1, existing_words={"지원"})
        self.assertEqual(r["picks"], [{"date": date.today().isoformat(), "word": "국회"}])

    def test_no_titles_is_error_not_exception(self):
        tn.fetch_titles = lambda **kw: []
        r = tn.pick(2)
        self.assertFalse(r["ok"])
        self.assertTrue(r["error"])

    def test_nothing_verified_is_error(self):
        tn.fetch_titles = lambda **kw: ["지원"]
        tn.verify = lambda words, source, **kw: []
        self.assertFalse(tn.pick(2, existing_words=set())["ok"])

    def test_unknown_source_and_exception_contained(self):
        self.assertFalse(tn.pick(1, "custom")["ok"])

        def boom(**kw):
            raise RuntimeError("터짐")
        tn.fetch_titles = boom
        self.assertFalse(tn.pick(1)["ok"])


class TestPickDeadline(unittest.TestCase):
    def setUp(self):
        self.real = (tn.fetch_titles, tn.candidates, tn.load_stop)
        tn.fetch_titles = lambda **kw: ["제목"]
        tn.candidates = lambda titles, **kw: [(f"낱{i}", 1) for i in range(120)]
        tn.load_stop = lambda *a, **k: set()

    def tearDown(self):
        tn.fetch_titles, tn.candidates, tn.load_stop = self.real

    def test_deadline_returns_what_was_confirmed_and_marked(self):
        o = WikiOpener(lambda titles, n: {"pages": [wiki_page(t, ["명사"]) for t in titles]})
        r = tn.pick(5, "wiktionary", "2026-11-15", existing_words=set(), opener=o,
                    sleep=Sleeper(), deadline=120, clock=Clock(0, 0, 500))
        self.assertTrue(r["ok"])
        self.assertEqual(r["stopped"], "deadline")
        self.assertEqual(r["checked"], 50)
        self.assertEqual([p["word"] for p in r["picks"]], ["낱0", "낱1", "낱2", "낱3", "낱4"])

    def test_no_deadline_is_not_marked(self):
        o = WikiOpener(lambda titles, n: {"pages": [wiki_page(t, ["명사"]) for t in titles]})
        r = tn.pick(2, "wiktionary", "2026-11-15", existing_words=set(), opener=o,
                    sleep=Sleeper(), deadline=None)
        self.assertTrue(r["ok"])
        self.assertNotIn("stopped", r)
        self.assertEqual(r["checked"], 120)


class TestDefaultExisting(unittest.TestCase):
    def test_trend_word_included_from_temp_files(self):
        with tempfile.TemporaryDirectory() as d:
            answers = Path(d) / "answers.txt"
            trend = Path(d) / "trend.txt"
            answers.write_text("가나다\n", encoding="utf-8")
            trend.write_text("# 주석\n2026-11-15 라마바\n", encoding="utf-8")
            self.assertEqual(tn.default_existing(answers_path=answers, trend_path=trend),
                             {"가나다", "라마바"})

    def test_missing_files_are_empty(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "없음.txt"
            self.assertEqual(tn.default_existing(answers_path=missing, trend_path=missing), set())


if __name__ == "__main__":
    unittest.main()
