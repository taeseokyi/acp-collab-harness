"""트렌드 정답 저장소 (표준 라이브러리만).

`data/trend.txt` 가 정본입니다 - `YYYY-MM-DD 낱말` 줄, `#` 주석. 마지막으로 정한 시각은 `data/trend_meta.json`
(`{"last_run": "2026-11-15T01:47:40+09:00"}`). `serve.py` 의 `/api/trend/pick` 과 `tools/pick_answers.py` 가 같은
`pick_and_store` 를 씁니다. 이미 있는 날짜는 절대 덮어쓰지 않으므로 하루 정답은 한 번 정해지면 바뀌지 않습니다.
쓰기는 모듈 잠금과 같은 폴더의 `.trend.lock` (`fcntl.flock`) 안에서(프로세스 사이도 막음) 임시 파일 → `os.replace` 로 하므로 반쯤 쓴 파일이 남지 않습니다.
"""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import json
import os
import re
import threading
from pathlib import Path

import trend_news

HERE = Path(__file__).resolve().parent
TREND_PATH = HERE / "data" / "trend.txt"
META_PATH = HERE / "data" / "trend_meta.json"
HEADER = "# 트렌드 정답 - tools/pick_answers.py 와 앱 서버가 날짜와 낱말을 덧붙입니다\n"

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LOCK = threading.Lock()


def _is_date(text) -> bool:
    if not (isinstance(text, str) and _DATE_RE.fullmatch(text)):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _is_word(text) -> bool:
    return isinstance(text, str) and bool(text) and not any(c.isspace() for c in text)


@contextlib.contextmanager
def _file_lock(path: Path):
    """`path` 옆 `.trend.lock` 에 배타 잠금(프로세스 사이). 호출자가 `_LOCK` 을 먼저 잡습니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.parent / ".trend.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # 닫으면 잠금도 풀림


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _read_unlocked(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return found
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[0].startswith("#") and _is_date(parts[0]):
            found.setdefault(parts[0], parts[1])
    return found


def read_trend(path=TREND_PATH) -> dict[str, str]:
    """{날짜: 낱말}. 파일이 없으면 {}; 주석·빈 줄·깨진 줄은 건너뜁니다."""
    return _read_unlocked(Path(path))


def append_picks(picks, path=TREND_PATH) -> list[dict]:
    """picks = [{"date","word"}...] 중 빈 날짜·바른 꼴만 덧붙이고, 덧붙인 것만 돌려줍니다."""
    path = Path(path)
    with _LOCK, _file_lock(path):
        have = _read_unlocked(path)
        added: list[dict] = []
        for item in picks or []:
            if not isinstance(item, dict):
                continue
            day, word = item.get("date"), item.get("word")
            if not _is_date(day) or not _is_word(word) or day in have:
                continue
            have[day] = word
            added.append({"date": day, "word": word})
        if not added:
            return []
        try:
            old = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            old = HEADER
        if old and not old.endswith("\n"):
            old += "\n"
        _atomic_write(path, old + "".join(f"{a['date']} {a['word']}\n" for a in added))
        return added


def last_run(meta_path=META_PATH):
    """마지막으로 정한 시각(ISO, 시간대 포함) 또는 None."""
    try:
        value = json.loads(Path(meta_path).read_text(encoding="utf-8")).get("last_run")
    except (OSError, ValueError, UnicodeDecodeError, AttributeError):
        return None
    return value if isinstance(value, str) and value else None


def record_run(when=None, meta_path=META_PATH) -> str:
    """지금(또는 when, aware datetime)을 ISO 로 저장하고 돌려줍니다."""
    when = when or datetime.datetime.now().astimezone()
    if when.tzinfo is None:
        when = when.astimezone()
    stamp = when.isoformat(timespec="seconds")
    meta_path = Path(meta_path)
    with _LOCK, _file_lock(meta_path):
        _atomic_write(meta_path, json.dumps({"last_run": stamp}, ensure_ascii=False) + "\n")
    return stamp


def pick_and_store(days, source="wiktionary", start=None, *, skip_dates=(), pick=None,
                   path=TREND_PATH, meta_path=META_PATH) -> dict:
    """뉴스에서 고르고(이미 있는 날짜 건너뜀) 빈 날짜에 덧붙인 뒤 결과에 added·trend·last_run 을 보탭니다."""
    skip = sorted(set(read_trend(path)) | set(skip_dates or ()))
    result = (pick or trend_news.pick)(days, source, start, skip_dates=skip)
    if not isinstance(result, dict) or not result.get("ok"):
        out = dict(result) if isinstance(result, dict) else {"ok": False, "error": "정답 고르기에 실패했습니다"}
        out["last_run"] = last_run(meta_path)
        return out
    out = dict(result)
    out["added"] = append_picks(result.get("picks") or [], path)
    out["last_run"] = record_run(meta_path=meta_path)
    out["trend"] = read_trend(path)
    return out
