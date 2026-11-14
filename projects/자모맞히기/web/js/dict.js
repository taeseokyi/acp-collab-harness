// 외부 사전 조회 (브라우저). DOM 없음. 명세: .aimem/graph/inputs/r31/SPEC.md 4절.
// 결과 꼴: {ok:true, found, source, via, evidence} | {ok:false, source, via, error}

const WIKI_HOST = "https://ko.wiktionary.org/w/api.php";

export const SOURCES = [
  { id: "wiktionary", label: "위키낱말사전", kind: "mediawiki", keyName: null, browserDirect: true,
    url: WIKI_HOST, model: null, signup: "" },
  { id: "wikipedia", label: "한국어 위키백과", kind: "mediawiki", keyName: null, browserDirect: true,
    url: "https://ko.wikipedia.org/w/api.php", model: null, signup: "" },
  { id: "stdict", label: "표준국어대사전(국립국어원)", kind: "stdict", keyName: "STDICT_API_KEY", browserDirect: false,
    url: "https://stdict.korean.go.kr/api/search.do", model: null, signup: "https://stdict.korean.go.kr/openapi/openApiInfo.do" },
  { id: "opendict", label: "우리말샘(국립국어원)", kind: "opendict", keyName: "OPENDICT_API_KEY", browserDirect: false,
    url: "https://opendict.korean.go.kr/api/search", model: null, signup: "https://opendict.korean.go.kr/service/openApiInfo" },
  { id: "krdict", label: "한국어기초사전(국립국어원)", kind: "krdict", keyName: "KRDICT_API_KEY", browserDirect: false,
    url: "https://krdict.korean.go.kr/api/search", model: null, signup: "https://krdict.korean.go.kr/openApi/openApiInfo" },
  { id: "kistillm", label: "KISTI LLM (함대 설정)", kind: "llm", keyName: "KISTI_API_KEY", browserDirect: false,
    url: null, model: null, signup: "" },
  { id: "exaone", label: "EXAONE (함대 설정)", kind: "llm", keyName: "EXAONE_API_KEY", browserDirect: false,
    url: null, model: null, signup: "" },
  { id: "gemini", label: "Google Gemini (무료 키)", kind: "llm", keyName: "GEMINI_API_KEY", browserDirect: true,
    url: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.5-flash",
    signup: "https://aistudio.google.com/apikey" },
  { id: "openrouter-free", label: "OpenRouter 무료 모델", kind: "llm", keyName: "OPENROUTER_API_KEY", browserDirect: true,
    url: "https://openrouter.ai/api/v1", model: "deepseek/deepseek-chat-v3.1:free",
    signup: "https://openrouter.ai/keys" },
];

export const DEFAULT_SOURCE = "wiktionary";

const SYSTEM_PROMPT = "너는 한국어 사전 편찬자다. 낱말이 표준 한국어 사전에 표제어로 실린 낱말(명사, 또는 동사·형용사의 기본형)이면 '예', 아니면 '아니오' 한 단어로만 답하라.";
const TIMEOUT_MS = 8000;
const LLM_TIMEOUT_MS = 30000;
const SERVER_LLM_TIMEOUT_MS = 35000;
const RATE_LIMIT = "요청 한도 초과(429) - 잠시 뒤 다시";
const SERVER_ONLY = "이 사전은 serve.py 로 열었을 때만 됩니다";

export function isLookupWord(word) {
  return typeof word === "string" && /^[가-힣]{1,10}$/.test(word);
}

export function mediawikiUrl(apiUrl, word, direct) {
  const q = `action=query&titles=${encodeURIComponent(word)}&format=json&formatversion=2&redirects=1`;
  return `${apiUrl}?${q}${direct ? "&origin=*" : ""}`;
}

export function parseMediawiki(json) {
  const page = json && json.query && Array.isArray(json.query.pages) ? json.query.pages[0] : null;
  return !!page && !page.missing && !page.invalid;
}

export function llmRequest(baseUrl, model, key, word) {
  return {
    url: `${String(baseUrl).replace(/\/+$/, "")}/chat/completions`,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
      body: JSON.stringify({
        model,
        messages: [{ role: "system", content: SYSTEM_PROMPT }, { role: "user", content: `낱말: ${word}` }],
        max_tokens: 1024,
        temperature: 0,
      }),
    },
  };
}

export function parseLlmAnswer(text) {
  if (typeof text !== "string") return null;
  const t = text.trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "").toLowerCase();
  if (t.startsWith("예") || t.startsWith("yes")) return true;
  if (t.startsWith("아니") || t.startsWith("no")) return false;
  return null;
}

// <think>…</think>·<thought>…</thought> 를 걷어 낸다 (닫히지 않은 것은 끝까지).
export function stripThinking(text) {
  if (typeof text !== "string") return text;
  return text
    .replace(/<(think|thought)>[\s\S]*?<\/\1>/gi, "")
    .replace(/<(think|thought)>[\s\S]*$/i, "")
    .trim();
}

// 시간 제한(기본 8초)을 걸어 fetch. 응답 본문 JSON 까지 읽어 {status, ok, json} 로.
async function getJson(fetchFn, url, init, timeoutMs = TIMEOUT_MS) {
  const ctl = typeof AbortController === "function" ? new AbortController() : null;
  const timer = ctl ? setTimeout(() => ctl.abort(), timeoutMs) : null;
  try {
    const res = await fetchFn(url, ctl ? { ...(init || {}), signal: ctl.signal } : init);
    let json = null;
    try { json = await res.json(); } catch { json = null; }
    return { status: res.status, ok: !!res.ok, json };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function fetchServerSources({ fetch: fetchFn, base = "api/" } = {}) {
  try {
    const r = await getJson(fetchFn, `${base}sources`);
    if (!r.ok || !r.json || !Array.isArray(r.json.sources)) return null;
    return r.json.sources;
  } catch {
    return null;
  }
}

function errText(e, secrets, timeoutMs = TIMEOUT_MS) {
  let msg = e && e.name === "AbortError" ? `시간 초과(${timeoutMs / 1000}초)` : String((e && e.message) || e || "알 수 없는 오류");
  for (const s of secrets) if (s) msg = msg.split(s).join("***");
  return msg.slice(0, 120);
}

async function directLookup(word, src, label, cfgKey, fetchFn, secrets) {
  const base = { source: src.id, via: "direct" };
  try {
    if (src.kind === "mediawiki") {
      const r = await getJson(fetchFn, mediawikiUrl(src.url, word, true));
      if (!r.ok) return { ok: false, ...base, error: `${label} 응답 오류 (${r.status})` };
      const found = parseMediawiki(r.json);
      return { ok: true, found, ...base, evidence: found ? `${label}에 표제어 있음` : `${label}에 없음` };
    }
    const q = llmRequest(src.url, src.model, cfgKey, word);
    const r = await getJson(fetchFn, q.url, q.init, LLM_TIMEOUT_MS);
    if (r.status === 429) return { ok: false, ...base, error: RATE_LIMIT };
    if (!r.ok) return { ok: false, ...base, error: `${label} 응답 오류 (${r.status})` };
    const choice = r.json && r.json.choices && r.json.choices[0] ? r.json.choices[0] : null;
    const raw = stripThinking(choice && choice.message ? choice.message.content : null);
    if (typeof raw !== "string" || raw === "") {
      return { ok: false, ...base, error: choice && choice.finish_reason === "length"
        ? "답이 잘렸습니다(모델이 생각하다 멈춤)" : "빈 답" };
    }
    const found = parseLlmAnswer(raw);
    if (found === null) return { ok: false, ...base, error: "알 수 없는 답" };
    return { ok: true, found, ...base, evidence: `${label} 답: ${found ? "예" : "아니오"}` };
  } catch (e) {
    return { ok: false, ...base, error: errText(e, secrets, src.kind === "llm" ? LLM_TIMEOUT_MS : TIMEOUT_MS) };
  }
}

async function serverLookup(word, id, base, fetchFn, timeoutMs = TIMEOUT_MS) {
  const r = await getJson(fetchFn, `${base}lookup?word=${encodeURIComponent(word)}&source=${encodeURIComponent(id)}`, undefined, timeoutMs);
  if (r.status === 404 || !r.json || typeof r.json !== "object" || typeof r.json.ok !== "boolean") return null;
  return { ...r.json, source: r.json.source || id, via: "server" };
}

export async function lookupWord(word, cfg, { fetch: fetchFn, base = "api/" } = {}) {
  const c = cfg || {};
  const id = c.source || DEFAULT_SOURCE;
  if (!isLookupWord(word)) return { ok: false, source: id, via: "direct", error: "조회할 수 없는 낱말 꼴입니다" };
  const keys = c.keys || {};
  try {
    if (id.startsWith("custom:")) {
      const cu = (c.customs || []).find((x) => x.id === id);
      if (!cu) return { ok: false, source: id, via: "direct", error: "등록되지 않은 사용자 사전입니다" };
      if (!/^https:\/\//i.test(String(cu.baseUrl || ""))) {
        return { ok: false, source: id, via: "direct", error: "사용자 사전 주소는 https:// 로 시작해야 합니다" };
      }
      const src = { id, kind: "llm", url: cu.baseUrl, model: cu.model };
      return await directLookup(word, src, cu.label || id, cu.key, fetchFn, [cu.key]);
    }
    const src = SOURCES.find((s) => s.id === id);
    if (!src) return { ok: false, source: id, via: "server", error: "알 수 없는 사전입니다" };
    if (src.kind === "llm" && src.browserDirect && keys[id]) {
      return await directLookup(word, src, src.label, keys[id], fetchFn, [keys[id]]);
    }
    let res = null;
    try { res = await serverLookup(word, id, base, fetchFn, src.kind === "llm" ? SERVER_LLM_TIMEOUT_MS : TIMEOUT_MS); } catch { res = null; }
    if (res) return res;
    if (src.browserDirect && src.kind === "mediawiki") return await directLookup(word, src, src.label, null, fetchFn, []);
    return { ok: false, source: id, via: "server", error: SERVER_ONLY };
  } catch (e) {
    return { ok: false, source: id, via: "direct", error: errText(e, Object.values(keys)) };
  }
}
