import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SOURCES, DEFAULT_SOURCE, isLookupWord, mediawikiUrl, parseMediawiki,
  llmRequest, parseLlmAnswer, fetchServerSources, lookupWord
} from "../web/js/dict.js";

// 가짜 fetch: handler(url, init) -> {status, body} | throw. 진짜 외부망은 부르지 않는다.
function fake(handler) {
  const calls = [];
  const f = async (url, init) => {
    calls.push({ url: String(url), init });
    const r = await handler(String(url), init);
    return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => r.body };
  };
  f.calls = calls;
  return f;
}
const notFound = () => ({ status: 404, body: { ok: false } });
const wikiBody = (missing) => ({ query: { pages: [missing ? { title: "x", missing: true } : { pageid: 1, title: "한국" }] } });
const llmBody = (text) => ({ choices: [{ message: { content: text } }] });

test("SOURCES: 기본값과 표의 id", () => {
  assert.equal(DEFAULT_SOURCE, "wiktionary");
  const ids = SOURCES.map((s) => s.id);
  for (const id of ["wiktionary", "wikipedia", "stdict", "opendict", "krdict", "kistillm", "exaone", "gemini", "openrouter-free"]) {
    assert.ok(ids.includes(id), id);
  }
  assert.equal(SOURCES.find((s) => s.id === "wiktionary").browserDirect, true);
  assert.equal(SOURCES.find((s) => s.id === "stdict").browserDirect, false);
});

test("isLookupWord: 한글만, 1~10자", () => {
  assert.equal(isLookupWord("한국"), true);
  assert.equal(isLookupWord("가"), true);
  assert.equal(isLookupWord("가나다라마바사아자차"), true);
  assert.equal(isLookupWord("가나다라마바사아자차카"), false);
  assert.equal(isLookupWord(""), false);
  assert.equal(isLookupWord("abc"), false);
  assert.equal(isLookupWord("한 국"), false);
  assert.equal(isLookupWord("ㅎㅏㄴ"), false);
  assert.equal(isLookupWord(null), false);
});

test("mediawikiUrl: 직접일 때만 origin=*, 낱말 인코딩", () => {
  const api = "https://ko.wiktionary.org/w/api.php";
  const d = mediawikiUrl(api, "한국", true);
  const s = mediawikiUrl(api, "한국", false);
  assert.ok(d.endsWith("&origin=*"));
  assert.ok(!s.includes("origin="));
  assert.ok(d.includes(`titles=${encodeURIComponent("한국")}`));
  assert.ok(d.includes("formatversion=2") && d.includes("redirects=1") && d.includes("action=query"));
});

test("parseMediawiki: missing·있음·빈 꼴", () => {
  assert.equal(parseMediawiki(wikiBody(false)), true);
  assert.equal(parseMediawiki(wikiBody(true)), false);
  assert.equal(parseMediawiki({}), false);
  assert.equal(parseMediawiki(null), false);
  assert.equal(parseMediawiki({ query: { pages: [] } }), false);
});

test("parseLlmAnswer: 예/아니오/엉뚱한 답", () => {
  for (const t of ["예", "예.", " Yes", "YES!", "'예'"]) assert.equal(parseLlmAnswer(t), true, t);
  for (const t of ["아니오", "아니요.", "no", "No."]) assert.equal(parseLlmAnswer(t), false, t);
  for (const t of ["글쎄요", "", "...", null, undefined]) assert.equal(parseLlmAnswer(t), null, String(t));
});

test("llmRequest: Authorization 머리·모델·max_tokens·낱말", () => {
  const { url, init } = llmRequest("https://x.test/v1/", "m-1", "SECRETKEY", "한국");
  assert.equal(url, "https://x.test/v1/chat/completions");
  assert.equal(init.method, "POST");
  assert.equal(init.headers.Authorization, "Bearer SECRETKEY");
  const body = JSON.parse(init.body);
  assert.equal(body.model, "m-1");
  assert.equal(body.max_tokens, 1024);
  assert.equal(body.temperature, 0);
  assert.equal(body.messages[0].role, "system");
  assert.equal(body.messages[1].content, "낱말: 한국");
});

test("fetchServerSources: 성공은 배열, 404·throw 는 null", async () => {
  const ok = fake(() => ({ status: 200, body: { sources: [{ id: "wiktionary" }] } }));
  assert.deepEqual(await fetchServerSources({ fetch: ok }), [{ id: "wiktionary" }]);
  assert.equal(ok.calls[0].url, "api/sources");
  assert.equal(await fetchServerSources({ fetch: fake(notFound) }), null);
  assert.equal(await fetchServerSources({ fetch: async () => { throw new Error("net"); } }), null);
});

test("lookupWord: 서버 성공 → via server", async () => {
  const f = fake(() => ({ status: 200, body: { ok: true, found: true, source: "stdict", evidence: "총 1건" } }));
  const r = await lookupWord("한국", { source: "stdict" }, { fetch: f });
  assert.equal(r.ok, true);
  assert.equal(r.found, true);
  assert.equal(r.via, "server");
  assert.ok(f.calls[0].url.startsWith("api/lookup?word="));
  assert.ok(f.calls[0].url.includes("source=stdict"));
});

test("lookupWord: 서버가 ok:false 를 주면 그대로(via server)", async () => {
  const f = fake(() => ({ status: 200, body: { ok: false, source: "stdict", error: "키가 없습니다: STDICT_API_KEY" } }));
  const r = await lookupWord("한국", { source: "stdict" }, { fetch: f });
  assert.equal(r.ok, false);
  assert.equal(r.via, "server");
  assert.match(r.error, /STDICT_API_KEY/);
});

test("lookupWord: 서버 404 + 위키 → 직접 다시 (origin=*)", async () => {
  const f = fake((url) => (url.startsWith("api/") ? notFound() : { status: 200, body: wikiBody(false) }));
  const r = await lookupWord("한국", { source: "wiktionary" }, { fetch: f });
  assert.equal(r.ok, true);
  assert.equal(r.found, true);
  assert.equal(r.via, "direct");
  assert.equal(f.calls.length, 2);
  assert.ok(f.calls[1].url.startsWith("https://ko.wiktionary.org/"));
  assert.ok(f.calls[1].url.includes("origin=*"));
});

test("lookupWord: 서버가 네트워크 오류여도 위키는 직접, 없는 낱말은 found false", async () => {
  const f = fake((url) => { if (url.startsWith("api/")) throw new Error("down"); return { status: 200, body: wikiBody(true) }; });
  const r = await lookupWord("가나다", { source: "wikipedia" }, { fetch: f });
  assert.equal(r.ok, true);
  assert.equal(r.found, false);
  assert.equal(r.via, "direct");
  assert.ok(f.calls[1].url.startsWith("https://ko.wikipedia.org/"));
});

test("lookupWord: 서버 404 + stdict → 'serve.py 로 열었을 때만' 오류", async () => {
  const f = fake(notFound);
  const r = await lookupWord("한국", { source: "stdict" }, { fetch: f });
  assert.equal(r.ok, false);
  assert.match(r.error, /serve\.py 로 열었을 때만/);
  assert.equal(f.calls.length, 1);
});

test("lookupWord: gemini 키 있음 → 직접, 없음 → 서버", async () => {
  const f1 = fake(() => ({ status: 200, body: llmBody("예") }));
  const r1 = await lookupWord("한국", { source: "gemini", keys: { gemini: "GKEY" } }, { fetch: f1 });
  assert.equal(r1.ok, true);
  assert.equal(r1.found, true);
  assert.equal(r1.via, "direct");
  assert.ok(f1.calls[0].url.startsWith("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"));
  assert.equal(f1.calls[0].init.headers.Authorization, "Bearer GKEY");

  const f2 = fake(() => ({ status: 200, body: { ok: true, found: false, source: "gemini", evidence: "아니오" } }));
  const r2 = await lookupWord("한국", { source: "gemini", keys: {} }, { fetch: f2 });
  assert.equal(r2.via, "server");
  assert.ok(f2.calls[0].url.startsWith("api/lookup"));
});

test("lookupWord: custom → 직접, 아니오 → found false", async () => {
  const f = fake(() => ({ status: 200, body: llmBody("아니오") }));
  const cfg = { source: "custom:1", customs: [{ id: "custom:1", label: "내 모델", baseUrl: "https://my.test/v1", model: "mm", key: "CKEY" }] };
  const r = await lookupWord("한국", cfg, { fetch: f });
  assert.equal(r.ok, true);
  assert.equal(r.found, false);
  assert.equal(r.via, "direct");
  assert.equal(f.calls[0].url, "https://my.test/v1/chat/completions");
  assert.equal(JSON.parse(f.calls[0].init.body).model, "mm");
});

test("lookupWord: LLM 의 엉뚱한 답 → 오류", async () => {
  const f = fake(() => ({ status: 200, body: llmBody("글쎄요") }));
  const r = await lookupWord("한국", { source: "gemini", keys: { gemini: "K" } }, { fetch: f });
  assert.equal(r.ok, false);
  assert.match(r.error, /알 수 없는 답/);
});

test("lookupWord: fetch 가 throw 해도 throw 하지 않음", async () => {
  const boom = async () => { throw new Error("network down"); };
  for (const cfg of [{ source: "wiktionary" }, { source: "stdict" }, { source: "gemini", keys: { gemini: "K" } }]) {
    const r = await lookupWord("한국", cfg, { fetch: boom });
    assert.equal(r.ok, false, cfg.source);
    assert.equal(typeof r.error, "string");
  }
});

test("lookupWord: 꼴 아닌 낱말은 fetch 를 부르지 않음", async () => {
  const f = fake(notFound);
  for (const w of ["abc", "", "한 국", "ㅎㅏㄴ", "가나다라마바사아자차카"]) {
    const r = await lookupWord(w, { source: "wiktionary" }, { fetch: f });
    assert.equal(r.ok, false, w);
  }
  assert.equal(f.calls.length, 0);
});

test("lookupWord: 키 값이 결과에 나오지 않음 (오류 문구에 섞여도 가림)", async () => {
  const KEY = "SUPER-SECRET-123";
  const leak = async () => { throw new Error(`failed with key ${KEY}`); };
  const r = await lookupWord("한국", { source: "gemini", keys: { gemini: KEY } }, { fetch: leak });
  assert.equal(r.ok, false);
  assert.ok(!JSON.stringify(r).includes(KEY));
  const f = fake(() => ({ status: 200, body: llmBody("예") }));
  const r2 = await lookupWord("한국", { source: "gemini", keys: { gemini: KEY } }, { fetch: f });
  assert.ok(!JSON.stringify(r2).includes(KEY));
});

test("lookupWord: 모르는 출처·등록 안 된 custom 은 오류(fetch 없음)", async () => {
  const f = fake(notFound);
  assert.equal((await lookupWord("한국", { source: "nope" }, { fetch: f })).ok, false);
  assert.equal((await lookupWord("한국", { source: "custom:9", customs: [] }, { fetch: f })).ok, false);
  assert.equal(f.calls.length, 0);
});

const llmCfg = { source: "gemini", keys: { gemini: "K" } };

test("llmRequest: max_tokens 1024 (추론 모델이 생각할 몫)", () => {
  assert.equal(JSON.parse(llmRequest("https://x.test/v1", "m", "K", "한국").init.body).max_tokens, 1024);
});

test("lookupWord: <think>·<thought> 는 걷고 답을 읽음", async () => {
  for (const t of ["<think>음... 아니오일까</think>예", "<thought>생각\n중</thought>\n아니오"]) {
    const f = fake(() => ({ status: 200, body: llmBody(t) }));
    const r = await lookupWord("한국", llmCfg, { fetch: f });
    assert.equal(r.ok, true, t);
    assert.equal(r.found, t.endsWith("예"), t);
  }
});

test("lookupWord: 빈 답 + finish_reason length → 잘림 오류, 그 밖의 빈 답 → 빈 답", async () => {
  const f1 = fake(() => ({ status: 200, body: { choices: [{ message: { content: "", reasoning_content: "생각…" }, finish_reason: "length" }] } }));
  const r1 = await lookupWord("한국", llmCfg, { fetch: f1 });
  assert.equal(r1.ok, false);
  assert.equal(r1.error, "답이 잘렸습니다(모델이 생각하다 멈춤)");
  const f2 = fake(() => ({ status: 200, body: { choices: [{ message: { content: "" }, finish_reason: "stop" }] } }));
  const r2 = await lookupWord("한국", llmCfg, { fetch: f2 });
  assert.equal(r2.ok, false);
  assert.equal(r2.error, "빈 답");
});

test("lookupWord: HTTP 429 → 한도 오류", async () => {
  const f = fake(() => ({ status: 429, body: { error: "rate" } }));
  const r = await lookupWord("한국", llmCfg, { fetch: f });
  assert.equal(r.ok, false);
  assert.equal(r.error, "요청 한도 초과(429) - 잠시 뒤 다시");
});

test("lookupWord: custom 주소가 https 가 아니면 fetch 없이 오류", async () => {
  const f = fake(() => ({ status: 200, body: llmBody("예") }));
  for (const u of ["http://my.test/v1", "ftp://x/v1", "", undefined]) {
    const cfg = { source: "custom:1", customs: [{ id: "custom:1", label: "m", baseUrl: u, model: "mm", key: "CKEY" }] };
    const r = await lookupWord("한국", cfg, { fetch: f });
    assert.equal(r.ok, false);
  }
  assert.equal(f.calls.length, 0);
});
