#!/usr/bin/env python3
"""자모맞히기 외부 사전 조회 (서버 쪽, 표준 라이브러리만).

낱말이 저장 목록에 없을 때 외부 사전·AI 모델에 "이 낱말이 있나" 를 묻습니다.
`serve.py` 가 `GET /api/sources`, `GET /api/lookup` 으로 이 모듈을 부릅니다.

키 넣는 법 - 저장소 루트 `.env` 의 `KEY=값` 줄, 또는 같은 이름의 환경변수(환경변수가 우선):

    출처 id          환경변수             받는 곳
    wiktionary       (키 없음)
    wikipedia        (키 없음)
    stdict           STDICT_API_KEY       https://stdict.korean.go.kr/openapi/openApiInfo.do
    opendict         OPENDICT_API_KEY     https://opendict.korean.go.kr/service/openApiInfo
    krdict           KRDICT_API_KEY       https://krdict.korean.go.kr/openApi/openApiInfo
    kistillm         KISTI_API_KEY        (fleet.toml [providers.kisti] 의 주소·모델)
    exaone           EXAONE_API_KEY       (fleet.toml [providers.exaone] 의 주소·모델)
    gemini           GEMINI_API_KEY       https://aistudio.google.com/apikey
    openrouter-free  OPENROUTER_API_KEY   https://openrouter.ai/keys  (모델: OPENROUTER_FREE_MODEL)

키 값은 요청 주소(쿼리)나 `Authorization: Bearer` 로만 나가고, 응답·오류·로그에는 나오지 않습니다.
`lookup(custom=)` 은 파이썬 호출용이며 HTTP 로는 닿지 않습니다.
바깥 호출은 모두 `opener(Request, timeout=)` 하나로 합니다(검사는 가짜 opener 를 넣음).
"""
import json
import os
import re
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # 저장소 루트 (.env, fleet.toml)
FLEET_TOML = ROOT / "fleet.toml"

WORD_RE = re.compile(r"[가-힣]{1,10}")
CACHE_MAX = 2000
_CACHE: dict = {}

SYSTEM_PROMPT = (
    "너는 한국어 사전 편찬자다. 낱말이 표준 한국어 사전에 표제어로 실린 낱말(명사, 또는 동사·형용사의 기본형)이면 "
    "'예', 아니면 '아니오' 한 단어로만 답하라."
)

SOURCES: dict = {
    "wiktionary": {"label": "위키낱말사전", "kind": "mediawiki", "env_key": None,
                   "url": "https://ko.wiktionary.org/w/api.php", "model": None, "signup": "", "browser_direct": True},
    "wikipedia": {"label": "한국어 위키백과", "kind": "mediawiki", "env_key": None,
                  "url": "https://ko.wikipedia.org/w/api.php", "model": None, "signup": "", "browser_direct": True},
    "stdict": {"label": "표준국어대사전(국립국어원)", "kind": "stdict", "env_key": "STDICT_API_KEY",
               "url": "https://stdict.korean.go.kr/api/search.do", "model": None,
               "signup": "https://stdict.korean.go.kr/openapi/openApiInfo.do", "browser_direct": False},
    "opendict": {"label": "우리말샘(국립국어원)", "kind": "opendict", "env_key": "OPENDICT_API_KEY",
                 "url": "https://opendict.korean.go.kr/api/search", "model": None,
                 "signup": "https://opendict.korean.go.kr/service/openApiInfo", "browser_direct": False},
    "krdict": {"label": "한국어기초사전(국립국어원)", "kind": "krdict", "env_key": "KRDICT_API_KEY",
               "url": "https://krdict.korean.go.kr/api/search", "model": None,
               "signup": "https://krdict.korean.go.kr/openApi/openApiInfo", "browser_direct": False},
    "kistillm": {"label": "KISTI LLM (함대 설정)", "kind": "llm", "env_key": "KISTI_API_KEY",
                 "url": "https://aida.kisti.re.kr:10430/v1", "model": "kistillm", "signup": "",
                 "browser_direct": False, "fleet": "kisti"},
    "exaone": {"label": "EXAONE (함대 설정)", "kind": "llm", "env_key": "EXAONE_API_KEY",
               "url": "https://api.exaone.ai/v1", "model": "k-exaone_v2.5", "signup": "",
               "browser_direct": False, "fleet": "exaone"},
    "gemini": {"label": "Google Gemini (무료 키)", "kind": "llm", "env_key": "GEMINI_API_KEY",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash",
               "signup": "https://aistudio.google.com/apikey", "browser_direct": True},
    "openrouter-free": {"label": "OpenRouter 무료 모델", "kind": "llm", "env_key": "OPENROUTER_API_KEY",
                        "url": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-chat-v3.1:free",
                        "signup": "https://openrouter.ai/keys", "browser_direct": True,
                        "model_env": "OPENROUTER_FREE_MODEL"},
}


def load_env(env=None) -> dict:
    """env 가 주어지면 그것만. 아니면 os.environ 위에 저장소 .env 를 (덮지 않고) 보탭니다."""
    if env is not None:
        return dict(env)
    merged = dict(os.environ)
    try:
        text = (ROOT / ".env").read_text(encoding="utf-8")
    except OSError:
        return merged
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and k not in merged:
            merged[k] = v
    return merged


def _llm_target(src: dict, env: dict):
    """(base_url, model). 함대 설정이 있으면 fleet.toml, 없으면 표의 값."""
    base, model = src["url"], src["model"]
    if src.get("fleet"):
        try:
            with open(FLEET_TOML, "rb") as f:
                p = tomllib.load(f)["providers"][src["fleet"]]
            base = p.get("base_url") or base
            models = p.get("models") or []
            model = models[0] if models else model
        except (OSError, KeyError, tomllib.TOMLDecodeError):
            pass
    if src.get("model_env") and env.get(src["model_env"]):
        model = env[src["model_env"]]
    return base, model


def available_sources(env=None) -> list:
    env = load_env(env)
    out = []
    for sid, s in SOURCES.items():
        needs = bool(s["env_key"])
        out.append({"id": sid, "label": s["label"], "kind": s["kind"],
                    "available": (not needs) or bool(env.get(s["env_key"])),
                    "needs_key": needs, "browser_direct": s["browser_direct"], "signup": s["signup"]})
    return out


def _err(source, via, msg):
    return {"ok": False, "source": source, "via": via, "error": msg}


def _ok(source, via, found, evidence):
    return {"ok": True, "found": bool(found), "source": source, "via": via, "evidence": str(evidence)[:80]}


class _Fail(Exception):
    pass


def _fetch(opener, req, timeout) -> bytes:
    """바깥 호출 한 번. 오류 글에 URL(=키)이 들어가지 않게 종류만 말합니다."""
    try:
        r = opener(req, timeout=timeout)
        try:
            return r.read()
        finally:
            close = getattr(r, "close", None)
            if close:
                close()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise _Fail("요청 한도 초과(429) - 잠시 뒤 다시") from None
        raise _Fail(f"HTTP 오류 {e.code}") from None
    except TimeoutError:
        raise _Fail("시간 초과") from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError) or "timed out" in str(e.reason):
            raise _Fail("시간 초과") from None
        raise _Fail("연결 실패") from None
    except OSError:
        raise _Fail("연결 실패") from None


def _json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _Fail("응답 JSON 이 깨졌습니다") from None


def _total(data) -> int:
    if isinstance(data, dict) and "error" in data and "channel" not in data:
        raise _Fail("사전이 오류를 돌려주었습니다 (키·한도 확인)")
    try:
        return int(str((data.get("channel") or {}).get("total", 0)).strip() or 0)
    except (ValueError, AttributeError):
        raise _Fail("응답 꼴이 다릅니다") from None


def _first_word(data) -> str:
    try:
        item = data["channel"]["item"]
        item = item[0] if isinstance(item, list) else item
        return re.sub(r"<[^>]*>|\^", "", str(item.get("word", "")))
    except (KeyError, TypeError, IndexError, AttributeError):
        return ""


LLM_MAX_TOKENS = 1024   # 추론 모델은 생각 토큰까지 담아야 답이 나옵니다
TIMEOUT_DEFAULT = 8     # 위키·국립국어원
TIMEOUT_LLM = 30        # 추론이 길어 넉넉히
_THINK_RE = re.compile(r"<(think|thought)>.*?</\1>", re.S | re.I)


def _parse_llm(text):
    t = re.sub(r"^[\s\W_]+|[\s\W_]+$", "", str(text or "")).lower()
    if t.startswith("예") or t.startswith("yes"):
        return True
    if t.startswith("아니") or t.startswith("no"):
        return False
    return None


def _do_lookup(word, sid, src, env, opener, timeout, custom):
    kind = src["kind"]
    if timeout is None and kind != "llm":
        timeout = TIMEOUT_DEFAULT
    key = ""
    if src.get("env_key"):
        key = env.get(src["env_key"]) or ""
        if not key:
            return _err(sid, "server", f"키가 없습니다: {src['env_key']}")
    ua = {"User-Agent": "jamo-dict/1"}
    if kind == "mediawiki":
        q = urllib.parse.urlencode({"action": "query", "titles": word, "format": "json",
                                    "formatversion": "2", "redirects": "1"})
        data = _json(_fetch(opener, urllib.request.Request(f"{src['url']}?{q}", headers=ua), timeout))
        pages = (data.get("query") or {}).get("pages") or []
        if not pages:
            raise _Fail("응답 꼴이 다릅니다")
        found = not pages[0].get("missing") and not pages[0].get("invalid")
        return _ok(sid, "server", found, "문서 있음" if found else "문서 없음")
    if kind in ("stdict", "opendict"):
        q = urllib.parse.urlencode({"key": key, "q": word, "req_type": "json"})
        raw = _fetch(opener, urllib.request.Request(f"{src['url']}?{q}", headers=ua), timeout)
        if not raw.strip():
            return _ok(sid, "server", False, "결과 0건")
        data = _json(raw)
        n = _total(data)
        return _ok(sid, "server", n > 0, (_first_word(data) or f"{n}건") if n else "결과 0건")
    if kind == "krdict":
        q = urllib.parse.urlencode({"key": key, "q": word})
        raw = _fetch(opener, urllib.request.Request(f"{src['url']}?{q}", headers=ua), timeout)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            raise _Fail("응답 XML 이 깨졌습니다") from None
        node = root.find(".//total")
        if node is None or not (node.text or "").strip().isdigit():
            raise _Fail("사전이 오류를 돌려주었습니다 (키·한도 확인)" if root.find(".//error_code") is not None
                        else "응답 꼴이 다릅니다")
        n = int(node.text)
        return _ok(sid, "server", n > 0, f"{n}건" if n else "결과 0건")
    # llm
    if sid == "custom":
        base, model, key = custom["base_url"], custom["model"], custom.get("key") or ""
    else:
        base, model = _llm_target(src, env)
    body = json.dumps({"model": model, "max_tokens": LLM_MAX_TOKENS, "temperature": 0, "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"낱말: {word}"}]}).encode("utf-8")
    headers = {"Content-Type": "application/json", **ua}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
    data = _json(_fetch(opener, req, TIMEOUT_LLM if timeout is None else timeout))
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise _Fail("응답 꼴이 다릅니다") from None
    text = _THINK_RE.sub("", str(text or "")).strip()
    if not text:
        if isinstance(choice, dict) and choice.get("finish_reason") == "length":
            raise _Fail("답이 잘렸습니다(모델이 생각하다 멈춤)")
        raise _Fail("빈 답")
    ans = _parse_llm(text)
    if ans is None:
        raise _Fail("알 수 없는 답")
    return _ok(sid, "server", ans, f"모델 답: {str(text).strip()}")


def lookup(word, source_id, *, env=None, opener=None, timeout=None, custom=None) -> dict:
    sid = source_id
    if not isinstance(word, str) or not WORD_RE.fullmatch(word):
        return _err(sid, "server", "한글 1~10자 낱말만 조회합니다")
    opener = opener or urllib.request.urlopen
    if sid == "custom":
        c = custom if isinstance(custom, dict) else {}
        base, model = str(c.get("base_url") or ""), str(c.get("model") or "")
        if not base.startswith("https://") or len(base) <= 8:
            return _err(sid, "server", "사용자 LLM 주소는 https:// 로 시작해야 합니다")
        if not model:
            return _err(sid, "server", "사용자 LLM 모델 이름이 없습니다")
        src = {"kind": "llm", "env_key": None}
        cache_key = (sid, base, model, word)
        c = {"base_url": base, "model": model, "key": str(c.get("key") or "")}
        env = {}
    elif sid in SOURCES:
        src = SOURCES[sid]
        env = load_env(env)
        cache_key = (sid, word)
        c = None
    else:
        return _err(sid, "server", "모르는 출처입니다")
    if cache_key in _CACHE:
        return dict(_CACHE[cache_key])
    try:
        res = _do_lookup(word, sid, src, env, opener, timeout, c)
    except _Fail as e:
        return _err(sid, "server", str(e))
    except Exception:  # 어떤 경우도 던지지 않고 꼴로 (메시지는 키가 섞일 수 있어 싣지 않음)
        return _err(sid, "server", "조회 중 알 수 없는 오류")
    if res.get("ok"):
        if len(_CACHE) >= CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[cache_key] = dict(res)
    return res
