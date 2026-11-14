"""연합뉴스 RSS 제목에서 6칸 낱말을 뽑고, 사전으로 확인해 날짜별 정답을 고릅니다 (표준 라이브러리만).

`serve.py` 의 `POST /api/trend/pick` 과 `tools/pick_answers.py` 가 같이 씁니다. 파일은 쓰지 않습니다.
RSS 는 CORS 머리가 없어 브라우저가 직접 읽지 못하므로 서버 쪽에서만 부릅니다.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
for _path in (HERE, HERE / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import build_words  # noqa: E402
import dict_server  # noqa: E402

STOP_PATH = HERE / "data" / "trend_stop.txt"
ANSWERS_PATH = HERE / "data" / "answers.txt"
TREND_PATH = HERE / "data" / "trend.txt"

FEEDS = [f"https://www.yna.co.kr/rss/{name}.xml"
         for name in ("news", "politics", "economy", "society", "culture", "sports", "international")]

HANGUL_RUN = re.compile(r"[가-힣]+")
# 긴 것부터 뗍니다 (에서 가 에 보다 먼저)
JOSA = sorted("에서 으로 에게 까지 부터 처럼 이라 와 과 은 는 이 가 을 를 의 에 로 도 만".split(),
              key=len, reverse=True)
BATCH = 50
UA = "jamo-matchigi/1.0 (word game; local)"
MAX_BODY = 2_000_001  # 2MB + 1 - 이만큼 읽히면 응답이 너무 큽니다
SINGLE_JOSA = {suffix for suffix in JOSA if len(suffix) == 1}


def load_stop(path=STOP_PATH) -> set[str]:
    """한 줄 한 낱말, `#` 로 시작하는 줄·빈 줄은 무시. 파일이 없으면 빈 집합."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}


def _read(opener, url, timeout, *, data=None):
    request = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    response = opener(request, timeout=timeout)
    try:
        body = response.read(2_000_001)
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
    if len(body) >= MAX_BODY:
        raise ValueError("응답이 2MB 를 넘습니다")
    return body


def fetch_titles(*, opener=urlopen, feeds=FEEDS, timeout=10) -> list[str]:
    """각 피드의 `<item><title>` 만, 겹침 뺌(처음 나온 순). 한 피드가 실패하면 건너뜁니다."""
    seen: set[str] = set()
    titles: list[str] = []
    for url in feeds:
        try:
            root = ET.fromstring(_read(opener, url, timeout))
        except Exception:  # noqa: BLE001 - 네트워크·XML 오류 모두 그 피드만 건너뜀
            continue
        for item in root.iter("item"):
            node = item.find("title")
            title = (node.text or "").strip() if node is not None else ""
            if title and title not in seen:
                seen.add(title)
                titles.append(title)
    return titles


def strip_josa(token: str) -> str:
    """끝의 조사 하나를 뗍니다. 뗀 뒤 두 글자 미만이면 그대로 둡니다."""
    for suffix in JOSA:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)]
    return token


def josa_variants(token: str) -> list[str]:
    """조사를 뗀 것과 원형 후보. 3음절 이상 낱말 끝의 1글자 조사는 둘 다 남깁니다.

    `전문가`·`어린이`·`경기도` 처럼 조사로 잘려도 6칸이 되는 낱말을 살리기 위해서입니다
    (어느 쪽이 낱말인지는 사전이 고릅니다).
    """
    for suffix in JOSA:
        if not token.endswith(suffix) or len(token) - len(suffix) < 2:
            continue
        stripped = token[: -len(suffix)]
        if suffix in SINGLE_JOSA and len(token) >= 3:
            return [token, stripped]
        return [stripped]
    return [token]


def candidates(titles, *, existing=(), stop=None) -> list[tuple[str, int]]:
    """제목의 한글 토막 → 조사 떼기/원형(3음절 이상 1글자 조사) → 6칸 → stop·existing 뺌.

    (낱말, 나온 기사 수) 를 기사 수 내림차순, 같으면 처음 나온 순으로 돌려줍니다.
    """
    blocked = set(existing or ()) | set(stop or ())
    counts: dict[str, int] = {}
    for title in titles:
        words = set()
        for run in HANGUL_RUN.findall(title):
            for word in josa_variants(run):
                if word in blocked:
                    continue
                spelled = build_words.units(word)
                if spelled is not None and len(spelled) == build_words.WORD_UNITS:
                    words.add(word)
        for word in words:
            counts[word] = counts.get(word, 0) + 1
    order = {word: index for index, word in enumerate(counts)}
    return sorted(counts.items(), key=lambda pair: (-pair[1], order[pair[0]]))


def _mediawiki_batch(batch, url, wiktionary, opener, timeout):
    """한 묶음을 한 번에 물어 확인된 낱말 집합을 돌려줍니다. 429 는 urllib 오류로 올라갑니다."""
    query = urllib.parse.urlencode({
        "action": "query", "titles": "|".join(batch), "prop": "categories", "cllimit": "max",
        "redirects": "1", "format": "json", "formatversion": "2",
    })
    data = json.loads(_read(opener, f"{url}?{query}", timeout).decode("utf-8"))
    body = data.get("query") or {}
    to_final = {}
    for key in ("normalized", "redirects"):
        for entry in body.get(key) or []:
            to_final[entry.get("from")] = entry.get("to")
    good = set()
    for page in body.get("pages") or []:
        if page.get("missing"):
            continue
        if wiktionary and not any("명사" in (c.get("title") or "") for c in page.get("categories") or []):
            continue
        good.add(page.get("title"))
    found = set()
    for word in batch:
        title = word
        for _ in range(3):  # normalized → redirects 되짚기
            title = to_final.get(title, title)
        if title in good:
            found.add(word)
    return found


def _mark(state, *, checked=None, stopped=None):
    if state is None:
        return
    if checked is not None:
        state["checked"] = checked
    if stopped is not None:
        state["stopped"] = stopped


def _verify_wiki(words, source, opener, sleep, limit, *, until=None, clock=time.monotonic, state=None):
    url = dict_server.SOURCES[source]["url"]
    wiktionary = source == "wiktionary"
    words = list(words)[:limit]
    found: set[str] = set()
    asked = 0
    for index in range(0, len(words), BATCH):
        if until is not None and clock() >= until:
            _mark(state, checked=asked, stopped="deadline")
            return [w for w in words if w in found]
        if index:
            sleep(3)
        batch = words[index:index + BATCH]
        asked += len(batch)
        for attempt in (0, 1):
            try:
                found |= _mediawiki_batch(batch, url, wiktionary, opener, 10)
                break
            except urllib.error.HTTPError as error:
                if error.code != 429:
                    break  # 이 묶음만 건너뜀
                if attempt == 0:
                    sleep(10)
                    continue
                _mark(state, checked=asked)
                return [w for w in words if w in found]  # 또 429 - 거기까지
            except Exception:  # noqa: BLE001
                break
    _mark(state, checked=asked)
    return [w for w in words if w in found]


def _is_429(result) -> bool:
    return isinstance(result, dict) and result.get("ok") is False and "429" in str(result.get("error", ""))


def _verify_lookup(words, source, sleep, env, *, until=None, clock=time.monotonic, state=None):
    found: set[str] = set()
    checked = list(words)[:40]
    asked = 0
    for index, word in enumerate(checked):
        if until is not None and clock() >= until:
            _mark(state, checked=asked, stopped="deadline")
            return [w for w in checked if w in found]
        if index:
            sleep(1)
        asked += 1
        result = dict_server.lookup(word, source, env=env)
        if _is_429(result):
            sleep(10)
            if until is not None and clock() >= until:
                _mark(state, checked=asked, stopped="deadline")
                return [w for w in checked if w in found]
            result = dict_server.lookup(word, source, env=env)
            if _is_429(result):
                break
        if isinstance(result, dict) and result.get("ok") and result.get("found"):
            found.add(word)
    _mark(state, checked=asked)
    return [w for w in checked if w in found]


def verify(words, source="wiktionary", *, opener=urlopen, sleep=time.sleep, env=None, limit=600,
           until=None, clock=time.monotonic, state=None) -> list[str]:
    """사전에 있는 낱말만, 들어온 순서대로. 위키낱말사전은 '명사' 분류인 것만.

    `until`(monotonic 시각)이 지나면 그때까지 확인한 것으로 끝내고 `state["stopped"]` 에
    `"deadline"` 을, `state["checked"]` 에 실제로 물은 낱말 수를 적습니다.
    """
    if source in ("wiktionary", "wikipedia"):
        return _verify_wiki(words, source, opener, sleep, limit, until=until, clock=clock, state=state)
    return _verify_lookup(words, source, sleep, env, until=until, clock=clock, state=state)


def _read_words(path, column) -> set[str]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    out = set()
    for line in lines:
        parts = line.split()
        if parts and not parts[0].startswith("#") and len(parts) > column:
            out.add(parts[column])
    return out


def default_existing(answers_path=ANSWERS_PATH, trend_path=TREND_PATH) -> set[str]:
    return _read_words(answers_path, 0) | _read_words(trend_path, 1)


def _dates(days, start, skip) -> list[str]:
    out: list[str] = []
    day = start
    skipped = {str(d) for d in skip}
    while len(out) < days:
        if day.isoformat() not in skipped:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def pick(days, source="wiktionary", start=None, *, skip_dates=(), existing_words=None,
         opener=urlopen, sleep=time.sleep, env=None, deadline=120, clock=time.monotonic) -> dict:
    """start 부터(skip_dates 건너뜀) days 개 날짜에 기사 수 많은 순으로 확인된 낱말을 하나씩.

    시작부터 `deadline` 초가 지나면 그때까지 확인된 것으로 끝내고 `"stopped": "deadline"` 을
    결과에 보탭니다(`deadline=None` 이면 제한 없음). throw 하지 않음.
    """
    try:
        started = clock()
        until = None if deadline is None else started + float(deadline)
        if source not in dict_server.SOURCES:
            return {"ok": False, "error": f"알 수 없는 사전: {source}"}
        first = date.fromisoformat(str(start)) if start else date.today()
        titles = fetch_titles(opener=opener)
        if not titles:
            return {"ok": False, "error": "연합뉴스 제목을 받지 못했습니다"}
        existing = default_existing() if existing_words is None else set(existing_words)
        found = candidates(titles, existing=existing, stop=load_stop())
        state: dict = {}
        words = verify([w for w, _ in found], source, opener=opener, sleep=sleep, env=env,
                       until=until, clock=clock, state=state)
        checked = state.get("checked", min(len(found), 600 if source in ("wiktionary", "wikipedia") else 40))
        stopped = {"stopped": state["stopped"]} if state.get("stopped") else {}
        if not words:
            return {"ok": False, "error": "사전으로 확인된 낱말이 없습니다", "checked": checked, **stopped}
        picks = [{"date": d, "word": w} for d, w in zip(_dates(int(days), first, skip_dates), words)]
        return {"ok": True, "picks": picks, "titles": len(titles), "candidates": len(found),
                "checked": checked, "source": source, **stopped}
    except Exception as error:  # noqa: BLE001 - 호출자는 JSON 만 기대
        return {"ok": False, "error": f"정답 고르기 실패: {type(error).__name__}"}
