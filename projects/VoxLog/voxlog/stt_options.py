"""VoxLog 받아쓰기 옵션 거르기.

웹에서 고른 옵션을 받아쓰기 서버 필드로 바꾸고, 서버 결과에서 실제 쓰인 값을
읽는다. 표준 라이브러리만 쓴다. 허용 값·범위는 받아쓰기 서버의 작업 API 와
맞춘다. 틀린 값은 사람이 읽을 한국어 한 줄 ValueError 로 알린다.
"""

import unicodedata

PREPROCESS = ("none", "basic", "level", "dereverb", "denoise")
SPEAKERS_MIN, SPEAKERS_MAX = 1, 20
CONTEXT_MAX = 4000

_OPTION_KEYS = ("preprocess", "num_speakers", "context", "auto", "review")

_PREPROCESS_ERROR = "preprocess 는 none, basic, level, dereverb, denoise 중 하나여야 합니다"
_SPEAKERS_ERROR = "num_speakers 는 1~20 사이의 정수여야 합니다"
_CONTEXT_TYPE_ERROR = "context 는 글이어야 합니다"
_CONTEXT_LENGTH_ERROR = "context 는 4000자까지입니다"
_NOT_DICT_ERROR = "받아쓰기 옵션은 객체여야 합니다"


def normalize(obj) -> dict:
    """고른 옵션만 담은 새 dict 를 돌려준다.

    None 은 {} 로 본다. dict 가 아니거나 모르는 키·틀린 값이면 ValueError.
    값이 None 인 키는 고르지 않은 것과 같아 결과에서 빠진다.
    """
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(_NOT_DICT_ERROR)

    out = {}
    for key, value in obj.items():
        if key not in _OPTION_KEYS:
            raise ValueError(f"모르는 받아쓰기 옵션 키입니다: {key}")
        if value is None:
            continue

        if key == "preprocess":
            if not isinstance(value, str) or value not in PREPROCESS:
                raise ValueError(_PREPROCESS_ERROR)
            out[key] = value
        elif key == "num_speakers":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(_SPEAKERS_ERROR)
            if not SPEAKERS_MIN <= value <= SPEAKERS_MAX:
                raise ValueError(_SPEAKERS_ERROR)
            out[key] = value
        elif key == "context":
            if not isinstance(value, str):
                raise ValueError(_CONTEXT_TYPE_ERROR)
            text = value.replace("\r\n", "\n").replace("\r", "\n")
            text = text.replace("\u2028", "\n").replace("\u2029", "\n")
            text = "".join(
                ch
                for ch in text
                if ch in "\n\t"
                or ch == "\u200d"
                or 0xE0020 <= ord(ch) <= 0xE007F
                or unicodedata.category(ch) not in ("Cf", "Cc")
            ).strip()
            if not text:
                continue
            if len(text) > CONTEXT_MAX:
                raise ValueError(_CONTEXT_LENGTH_ERROR)
            out[key] = text
        else:  # auto, review
            if not isinstance(value, bool):
                raise ValueError(f"{key} 는 true 또는 false 여야 합니다")
            out[key] = value

    return out


def form_fields(opts) -> dict:
    """정규화된 옵션을 받아쓰기 서버의 multipart 필드로 바꾼다. 고른 것만 담는다."""
    norm = normalize(opts)
    fields = {}
    if "preprocess" in norm:
        fields["preprocess"] = norm["preprocess"]
    if "num_speakers" in norm:
        fields["num_speakers"] = str(norm["num_speakers"])
    if "context" in norm:
        fields["context"] = norm["context"]
    if "auto" in norm:
        fields["auto"] = "1" if norm["auto"] else "0"
    if "review" in norm:
        fields["review"] = "1" if norm["review"] else "0"
    return fields


def _short_text(value):
    if not isinstance(value, str):
        return None
    return value[:40]


def _auto_flag(value):
    if value is None:
        return False
    if isinstance(value, dict):
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "none")
    return bool(value)


def used_from_result(result) -> dict:
    """서버 결과에서 실제 쓰인 값을 읽는다. 결과가 dict 가 아니면 {}."""
    if not isinstance(result, dict):
        return {}

    speakers = result.get("speakers")
    if isinstance(speakers, list):
        speakers_value = len(speakers)
    elif isinstance(speakers, int) and not isinstance(speakers, bool):
        speakers_value = speakers
    else:
        speakers_value = None

    return {
        "preprocess": _short_text(result.get("preprocess")),
        "mode": _short_text(result.get("mode")),
        "speakers": speakers_value,
        "auto": _auto_flag(result.get("auto")),
        "review": result.get("review") is not None,
    }
