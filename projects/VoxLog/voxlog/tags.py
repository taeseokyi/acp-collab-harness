"""VoxLog 녹취 이름·태그 정규화와 모델 출력에서 태그 뽑기.

표준 라이브러리만 쓴다. 다른 voxlog 모듈을 가져오지 않는다.
"""

import re

LABEL_MAX = 40
TAG_MAX = 20
TAGS_MAX = 10
AUTO_TAGS_MAX = 5

_SPLIT_RE = re.compile(r"[\n,\u3001]+")
_PREFIX_RE = re.compile(r"^\s*(?:[-*•·#]+|\d+[.)]|[①-⑳]\)?)\s*")
_TAG_HEADER_RE = re.compile(r"^\s*(?:tags|tag|태그)\s*[:：]\s*", re.IGNORECASE)
_INNER_PUNCT_RE = re.compile(r"\.\s|。|[?？!！]")
_QUOTE_CHARS = "\"'`“”‘’"
_END_PUNCT = ".\u3002"


def clean(s: str) -> str:
    """앞뒤를 자르고 안쪽 공백(줄바꿈 포함)을 한 칸으로 접는다."""
    return " ".join(s.split())


def normalize_label(v) -> str:
    if not isinstance(v, str):
        raise ValueError("label 은 문자열이어야 합니다")
    label = clean(v)
    if len(label) > LABEL_MAX:
        raise ValueError("이름은 40자 이하여야 합니다")
    return label


def tag_key(t: str) -> str:
    return t.casefold()


def normalize_tags(v) -> list[str]:
    if not isinstance(v, list) or any(not isinstance(t, str) for t in v):
        raise ValueError("tags 는 문자열 목록이어야 합니다")

    out = []
    seen = set()
    for item in v:
        tag = clean(item)
        if not tag:
            continue
        if len(tag) > TAG_MAX:
            raise ValueError("태그는 하나당 20자 이하여야 합니다")
        key = tag_key(tag)
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)

    if len(out) > TAGS_MAX:
        raise ValueError("태그는 최대 10개입니다")
    return out


def merge_tags(human, auto) -> list[str]:
    merged = list(human)
    seen = {tag_key(t) for t in merged}
    for tag in auto:
        if len(merged) >= TAGS_MAX:
            break
        key = tag_key(tag)
        if key not in seen:
            merged.append(tag)
            seen.add(key)
    return merged[:TAGS_MAX]


def _strip_decoration(s: str) -> str:
    while True:
        before = s
        s = s.strip()
        s = _PREFIX_RE.sub("", s)
        s = s.strip().strip(_QUOTE_CHARS)
        s = s.rstrip(_END_PUNCT).strip()
        if s == before:
            return s


def parse_tag_output(text: str, limit=AUTO_TAGS_MAX) -> list[str]:
    if not isinstance(text, str):
        return []

    out = []
    seen = set()
    for part in _SPLIT_RE.split(text):
        if len(out) >= limit:
            break
        tag = _strip_decoration(part)
        tag = _TAG_HEADER_RE.sub("", tag)
        tag = clean(_strip_decoration(tag))
        if not tag or len(tag) > TAG_MAX:
            continue
        if ":" in tag or "：" in tag:
            continue
        if _INNER_PUNCT_RE.search(tag):
            continue
        if "<" in tag or ">" in tag:
            continue
        key = tag_key(tag)
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out
