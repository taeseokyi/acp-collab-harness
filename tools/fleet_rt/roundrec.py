"""`rounds/R<N>/round.json` 의 유일한 쓰는 곳 - 엔진·DB 도구가 같은 잠금으로 읽고 고쳐 쓴다. 표준 라이브러리만."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pathlib
import tempfile

FILE = "round.json"
LOCK = ".round.lock"


def _check(round_dir):
    # 작업자도 `rounds/` 에 쓸 수 있어 링크를 심으면 기록이 저장소 밖에 쓰이므로 거절한다.
    d = pathlib.Path(round_dir)
    for p in (d.parent, d, d / FILE):
        if p.is_symlink():
            raise ValueError(f"{p} 가 심볼릭 링크라 쓰지 않습니다")
    return d


def read(round_dir):
    """기록 dict - 없거나 깨졌거나 링크면 {}."""
    try:
        d = _check(round_dir)
        rec = json.loads((d / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return rec if isinstance(rec, dict) else {}


@contextlib.contextmanager
def _locked(d):
    fd = os.open(d / LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def update(round_dir, fn):
    """잠금 안에서 읽고(없으면 {}) `fn(rec)` 가 돌려준 dict 를 고유 임시 파일 + os.replace 로 쓴다. 쓴 dict.

    `fn` 이 None 을 돌려주면 쓰지 않고 None. 폴더가 없으면 만든다. 링크면 ValueError, dict 도 None 도 아니면 TypeError."""
    d = _check(round_dir)
    d.mkdir(parents=True, exist_ok=True)
    _check(d)
    with _locked(d):
        rec = fn(read(d))
        if rec is None:
            return None
        if not isinstance(rec, dict):
            raise TypeError("roundrec.update: fn 은 dict 를 돌려줘야 합니다")
        fd, tmp = tempfile.mkstemp(prefix=f".{FILE}.", suffix=".tmp", dir=str(d))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
            os.replace(tmp, d / FILE)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    return rec
