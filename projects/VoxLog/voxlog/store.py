"""VoxLog 저장소 - 녹음 메타·오디오·받아 적은 글·답을 파일로 쌓는다.

표준 라이브러리만 쓴다. 쓰기는 임시 파일 + os.replace 로 하고 메서드 전체를
threading.Lock 으로 감싼다. id 는 경로를 만들기 전에 정규식으로 검사해 경로
탈출을 막는다.
"""

import datetime
import json
import math
import os
import pathlib
import re
import secrets
import tempfile
import threading

MAX_AUDIO_BYTES = 50 * 1024 * 1024
ALLOWED_MIME = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}

_RID_RE = re.compile(r"^r-\d{8}-\d{6}-[0-9a-f]{4}$")
_AID_RE = re.compile(r"^a-\d{8}-\d{6}-[0-9a-f]{4}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_RECORD_STATUS = {"pending", "transcribing", "done", "failed", "no-stt"}
_ANSWER_STATUS = {"done", "failed"}


def _now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _sort_key(meta):
    dt = _parse_iso(meta.get("recorded_at"))
    if dt is None:
        dt = _parse_iso(meta.get("created"))
    if dt is None:
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(datetime.timezone.utc)


def _clean_location(location):
    if not isinstance(location, dict):
        return None
    try:
        lat = float(location["lat"])
        lon = float(location["lon"])
        accuracy = float(location["accuracy"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(accuracy)):
        return None
    if abs(lat) > 90 or abs(lon) > 180 or accuracy < 0:
        return None
    return {"lat": lat, "lon": lon, "accuracy": accuracy}


def _unlink_quiet(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _valid_rid(rid):
    return isinstance(rid, str) and _RID_RE.match(rid) is not None


def _valid_aid(aid):
    return isinstance(aid, str) and _AID_RE.match(aid) is not None


class Store:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.audio_dir = self.root / "audio"
        self.meta_dir = self.root / "meta"
        self.transcripts_dir = self.root / "transcripts"
        self.answers_dir = self.root / "answers"
        self.incoming_dir = self.root / "incoming"
        for d in (self.audio_dir, self.meta_dir, self.transcripts_dir, self.answers_dir,
                  self.incoming_dir):
            d.mkdir(parents=True, exist_ok=True)
        # 죽은 업로드 찌꺼기를 치운다
        for leftover in self.incoming_dir.iterdir():
            try:
                if leftover.is_dir():
                    continue
                os.unlink(leftover)
            except OSError:
                pass
        self._lock = threading.Lock()
        # 진행 중인 업로드: client_id -> Event, 예약된 rid
        self._inflight = {}
        self._reserved_rids = set()
        # 글 캐시: 경로 -> (mtime_ns, size, 글)
        self._text_cache = {}
        self._cache_lock = threading.Lock()

    # ---- 내부 도우미 (락 안에서만 부른다) ----

    def _atomic_write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _write_json(self, path, obj):
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self._atomic_write(path, data)

    def _read_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _meta_path(self, rid):
        return self.meta_dir / (rid + ".json")

    def _audio_path(self, meta):
        ext = ALLOWED_MIME.get(meta.get("mime"))
        if not ext:
            return None
        return self.audio_dir / (meta["id"] + "." + ext)

    def _record_date(self, meta):
        recorded = meta.get("recorded_at") or ""
        day = recorded[:10]
        if _DATE_RE.match(day):
            return day
        created = (meta.get("created") or "")[:10]
        if _DATE_RE.match(created):
            return created
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def _transcript_path(self, meta):
        return self.transcripts_dir / self._record_date(meta) / (meta["id"] + ".txt")

    def _read_transcript(self, meta):
        try:
            with open(self._transcript_path(meta), "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def _cached_transcript(self, meta):
        """(경로, mtime_ns, size) 가 같으면 캐시된 글을 돌려준다."""
        path = self._transcript_path(meta)
        try:
            st = os.stat(path)
        except OSError:
            with self._cache_lock:
                self._text_cache.pop(path, None)
            return ""
        key = (st.st_mtime_ns, st.st_size)
        with self._cache_lock:
            hit = self._text_cache.get(path)
        if hit is not None and hit[0] == key[0] and hit[1] == key[1]:
            return hit[2]
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return ""
        with self._cache_lock:
            self._text_cache[path] = (key[0], key[1], text)
        return text

    def _drop_cache(self, path):
        with self._cache_lock:
            self._text_cache.pop(path, None)

    def _iter_meta(self):
        try:
            names = os.listdir(self.meta_dir)
        except OSError:
            return
        for name in names:
            if not name.endswith(".json"):
                continue
            rid = name[:-5]
            if not _valid_rid(rid):
                continue
            meta = self._read_json(self.meta_dir / name)
            if isinstance(meta, dict):
                yield meta

    def _find_by_client_id(self, client_id):
        for meta in self._iter_meta():
            if meta.get("client_id") == client_id:
                return meta
        return None

    def _new_rid(self):
        now = datetime.datetime.now()
        for _ in range(1000):
            rid = "r-{}-{}".format(now.strftime("%Y%m%d-%H%M%S"), secrets.token_hex(2))
            if rid not in self._reserved_rids and not self._meta_path(rid).exists():
                return rid
        raise RuntimeError("녹음 id 를 만들 수 없습니다")

    def _new_aid(self):
        now = datetime.datetime.now()
        for _ in range(1000):
            aid = "a-{}-{}".format(now.strftime("%Y%m%d-%H%M%S"), secrets.token_hex(2))
            if not (self.answers_dir / (aid + ".json")).exists():
                return aid
        raise RuntimeError("답 id 를 만들 수 없습니다")

    def _load_meta(self, rid):
        if not _valid_rid(rid):
            raise ValueError("잘못된 녹음 id 입니다")
        meta = self._read_json(self._meta_path(rid))
        if not isinstance(meta, dict):
            raise ValueError("없는 녹음입니다: " + rid)
        return meta

    # ---- 녹음 ----

    def incoming_path(self):
        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        while True:
            path = self.incoming_dir / ("up-" + secrets.token_hex(8))
            if not path.exists():
                return path

    @staticmethod
    def _check_upload(mime, size):
        base_mime = (mime or "").split(";", 1)[0].strip().lower()
        if base_mime not in ALLOWED_MIME:
            raise ValueError("지원하지 않는 오디오 형식입니다: " + str(mime))
        if not size:
            raise ValueError("오디오 데이터가 비어 있습니다")
        if size > MAX_AUDIO_BYTES:
            raise ValueError("오디오가 너무 큽니다 (최대 {} 바이트)".format(MAX_AUDIO_BYTES))
        return base_mime

    def add_recording(self, data, mime, recorded_at=None, duration_ms=None,
                      client_id=None, location=None):
        self._check_upload(mime, len(data) if data else 0)
        path = self.incoming_path()
        try:
            with open(path, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            _unlink_quiet(path)
            raise
        return self.add_recording_file(path, mime, recorded_at=recorded_at,
                                       duration_ms=duration_ms, client_id=client_id,
                                       location=location)

    def add_recording_file(self, path, mime, recorded_at=None, duration_ms=None,
                           client_id=None, location=None):
        path = pathlib.Path(path)
        try:
            try:
                size = os.stat(path).st_size
            except OSError:
                raise ValueError("받은 파일이 없습니다")
            base_mime = self._check_upload(mime, size)
        except BaseException:
            _unlink_quiet(path)
            raise

        # 1) 잠금 안: client_id 중복 확인 + rid 정하기(예약). 오래 걸리는 일 없음.
        while True:
            with self._lock:
                if client_id:
                    old = self._find_by_client_id(client_id)
                    if old is not None:
                        old = dict(old)
                        old["duplicate"] = True
                        _unlink_quiet(path)
                        return old
                    waiting = self._inflight.get(client_id)
                    if waiting is None:
                        done = threading.Event()
                        self._inflight[client_id] = done
                else:
                    waiting = None
                if waiting is None:
                    try:
                        rid = self._new_rid()
                    except BaseException:
                        if client_id:
                            self._inflight.pop(client_id, None).set()
                        _unlink_quiet(path)
                        raise
                    self._reserved_rids.add(rid)
                    break
            # 같은 client_id 가 올라가는 중 - 끝나길 기다렸다 다시 확인한다
            waiting.wait()

        audio = self.audio_dir / (rid + "." + ALLOWED_MIME[base_mime])
        moved = False
        try:
            # 2) 잠금 밖: 파일 옮기기 (복사 아님)
            os.replace(path, audio)
            moved = True
            created = _now_iso()
            meta = {
                "id": rid,
                "client_id": client_id,
                "created": created,
                "recorded_at": recorded_at if recorded_at else created,
                "duration_ms": duration_ms,
                "mime": base_mime,
                "size": size,
                "status": "pending",
                "error": None,
                "title": "",
                "chars": 0,
                "location": _clean_location(location),
            }
            # 3) 잠금 안: 메타 쓰기만
            with self._lock:
                self._write_json(self._meta_path(rid), meta)
            return dict(meta)
        except BaseException:
            _unlink_quiet(path)
            if moved:
                _unlink_quiet(audio)
            raise
        finally:
            with self._lock:
                self._reserved_rids.discard(rid)
                if client_id:
                    ev = self._inflight.pop(client_id, None)
                    if ev is not None:
                        ev.set()

    def get(self, rid):
        if not _valid_rid(rid):
            return None
        with self._lock:
            meta = self._read_json(self._meta_path(rid))
            if not isinstance(meta, dict):
                return None
            out = dict(meta)
            if "location" not in out:
                out["location"] = None
            out["transcript"] = self._read_transcript(meta)
            return out

    def list(self, q=None, date_from=None, date_to=None, status=None, limit=200):
        ql = q.lower() if q else None
        with self._lock:
            metas = list(self._iter_meta())
        # 글 읽기는 잠금 밖에서 (캐시가 (경로, mtime_ns, size) 로 새로 읽을지 정한다)
        items = []
        for meta in metas:
            day = self._record_date(meta)
            if date_from and day < date_from:
                continue
            if date_to and day > date_to:
                continue
            if status and meta.get("status") != status:
                continue
            text = self._cached_transcript(meta)
            if ql is not None:
                title = meta.get("title") or ""
                lowered = text.lower()
                if ql not in lowered and ql not in title.lower():
                    continue
                idx = lowered.find(ql)
                if idx >= 0:
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(q) + 40)
                    snippet = text[start:end]
                else:
                    snippet = text[:80]
            else:
                snippet = text[:80]
            item = dict(meta)
            if "location" not in item:
                item["location"] = None
            item["snippet"] = snippet
            items.append(item)
        items.sort(key=_sort_key, reverse=True)
        if limit is not None:
            items = items[:max(0, limit)]
        return items

    def audio_path(self, rid):
        if not _valid_rid(rid):
            return None
        with self._lock:
            meta = self._read_json(self._meta_path(rid))
            if not isinstance(meta, dict):
                return None
            path = self._audio_path(meta)
            if path is not None and path.exists():
                return path
            for candidate in self.audio_dir.glob(rid + ".*"):
                if candidate.is_file():
                    return candidate
            return None

    def set_status(self, rid, status, error=None):
        if status not in _RECORD_STATUS:
            raise ValueError("알 수 없는 상태입니다: " + str(status))
        with self._lock:
            meta = self._load_meta(rid)
            meta["status"] = status
            meta["error"] = error
            self._write_json(self._meta_path(rid), meta)

    def set_transcript(self, rid, text):
        text = text or ""
        with self._lock:
            meta = self._load_meta(rid)
            path = self._transcript_path(meta)
            self._atomic_write(path, text.encode("utf-8"))
            self._drop_cache(path)
            meta["title"] = " ".join(text.split())[:40]     # 화자 구분 글은 여러 줄 - 제목은 한 줄로
            meta["chars"] = len(text)
            meta["status"] = "done"
            meta["error"] = None
            self._write_json(self._meta_path(rid), meta)

    def pending_ids(self):
        with self._lock:
            found = [m for m in self._iter_meta()
                     if m.get("status") in ("pending", "transcribing")]
        found.sort(key=lambda m: (m.get("recorded_at") or m.get("created") or ""))
        return [m["id"] for m in found]

    def delete(self, rid):
        if not _valid_rid(rid):
            raise ValueError("잘못된 녹음 id 입니다")
        with self._lock:
            meta = self._read_json(self._meta_path(rid))
            removed = False
            if isinstance(meta, dict):
                path = self._audio_path(meta)
                if path is not None and path.exists():
                    try:
                        os.unlink(path)
                        removed = True
                    except OSError:
                        pass
                tpath = self._transcript_path(meta)
                self._drop_cache(tpath)
                if tpath.exists():
                    try:
                        os.unlink(tpath)
                        removed = True
                    except OSError:
                        pass
            for candidate in self.audio_dir.glob(rid + ".*"):
                try:
                    os.unlink(candidate)
                    removed = True
                except OSError:
                    pass
            for candidate in self.transcripts_dir.glob("*/" + rid + ".txt"):
                self._drop_cache(candidate)
                try:
                    os.unlink(candidate)
                    removed = True
                except OSError:
                    pass
            mpath = self._meta_path(rid)
            if mpath.exists():
                try:
                    os.unlink(mpath)
                    removed = True
                except OSError:
                    pass
            return removed

    def stats(self):
        with self._lock:
            metas = list(self._iter_meta())
        out = {"count": 0, "done": 0, "pending": 0, "failed": 0, "chars": 0,
               "by_date": {}}
        for meta in metas:
            out["count"] += 1
            status = meta.get("status")
            if status == "done":
                out["done"] += 1
            elif status in ("pending", "transcribing"):
                out["pending"] += 1
            elif status == "failed":
                out["failed"] += 1
            out["chars"] += int(meta.get("chars") or 0)
            day = self._record_date(meta)
            out["by_date"][day] = out["by_date"].get(day, 0) + 1
        return out

    # ---- 답 ----

    def add_answer(self, kind, prompt, ids):
        with self._lock:
            aid = self._new_aid()
            answer = {
                "id": aid,
                "kind": kind,
                "prompt": prompt,
                "ids": list(ids or []),
                "created": _now_iso(),
                "status": "running",
                "answer": None,
                "error": None,
            }
            self._write_json(self.answers_dir / (aid + ".json"), answer)
            return dict(answer)

    def set_answer(self, aid, status, answer=None, error=None):
        if not _valid_aid(aid):
            raise ValueError("잘못된 답 id 입니다")
        if status not in _ANSWER_STATUS:
            raise ValueError("알 수 없는 답 상태입니다: " + str(status))
        with self._lock:
            path = self.answers_dir / (aid + ".json")
            data = self._read_json(path)
            if not isinstance(data, dict):
                raise ValueError("없는 답입니다: " + aid)
            data["status"] = status
            data["answer"] = answer
            data["error"] = error
            self._write_json(path, data)

    def get_answer(self, aid):
        if not _valid_aid(aid):
            return None
        with self._lock:
            data = self._read_json(self.answers_dir / (aid + ".json"))
            return dict(data) if isinstance(data, dict) else None

    def list_answers(self, limit=50):
        with self._lock:
            items = []
            try:
                names = os.listdir(self.answers_dir)
            except OSError:
                names = []
            for name in names:
                if not name.endswith(".json"):
                    continue
                aid = name[:-5]
                if not _valid_aid(aid):
                    continue
                data = self._read_json(self.answers_dir / name)
                if isinstance(data, dict):
                    items.append(data)
        items.sort(key=lambda a: a.get("created") or "", reverse=True)
        if limit is not None:
            items = items[:max(0, limit)]
        return items
