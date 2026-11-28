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

from .tags import tag_key, merge_tags
from .stt_options import normalize

MAX_AUDIO_BYTES = 50 * 1024 * 1024
PREV_KEEP = 5
ALLOWED_MIME = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}

_RID_RE = re.compile(r"^r-\d{8}-\d{6}-[0-9a-f]{4}$")
_AID_RE = re.compile(r"^a-\d{8}-\d{6}-[0-9a-f]{4}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_RECORD_STATUS = {"pending", "transcribing", "done", "failed", "no-stt"}
_ANSWER_STATUS = {"done", "failed"}
_AUTOTAG_STATES = {None, "pending", "done", "failed"}


def _fill_meta_defaults(meta):
    if "label" not in meta:
        meta["label"] = ""
    if "tags" not in meta:
        meta["tags"] = []
    if "tags_auto" not in meta:
        meta["tags_auto"] = []
    if "tags_human" not in meta:
        meta["tags_human"] = False
    if "autotag" not in meta:
        meta["autotag"] = None
    if "stt_options" not in meta:
        meta["stt_options"] = None
    if "stt_used" not in meta:
        meta["stt_used"] = None
    return meta


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

    def _prev_transcript_path(self, meta):
        return self.transcripts_dir / self._record_date(meta) / (meta["id"] + ".prev.txt")

    def _prev_json_path(self, meta):
        return self.transcripts_dir / self._record_date(meta) / (meta["id"] + ".prev.json")

    def _read_transcript(self, meta):
        try:
            with open(self._transcript_path(meta), "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def _read_prev_transcript(self, meta):
        try:
            with open(self._prev_transcript_path(meta), "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def _read_prev_list(self, meta):
        """지난 글 벌 목록 - 오래된 것이 앞. 옛 .prev.txt 한 벌도 여기서 이어받는다."""
        path = self._prev_json_path(meta)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = None
        if not isinstance(raw, list):
            prev = self._read_prev_transcript(meta)
            if not prev.strip():
                return []
            used = meta.get("prev_stt_used")
            if not isinstance(used, dict):
                used = None
            at = used.get("at") if isinstance(used, dict) else None
            return [{"text": prev, "stt_used": dict(used) if used is not None else None,
                     "at": at if isinstance(at, str) else None}]
        items = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            used = entry.get("stt_used")
            if not isinstance(used, dict):
                used = None
            at = entry.get("at")
            if not isinstance(at, str):
                at = None
            items.append({"text": text, "stt_used": used, "at": at})
        return items

    def _write_prev_list(self, meta, items):
        self._write_json(self._prev_json_path(meta), items)
        _unlink_quiet(self._prev_transcript_path(meta))
        meta.pop("prev_stt_used", None)

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
                "label": "",
                "tags": [],
                "tags_auto": [],
                "tags_human": False,
                "autotag": None,
                "stt_options": None,
                "stt_used": None,
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

    def get(self, rid, with_prev=True):
        if not _valid_rid(rid):
            return None
        with self._lock:
            meta = self._read_json(self._meta_path(rid))
            if not isinstance(meta, dict):
                return None
            out = dict(meta)
            _fill_meta_defaults(out)
            if "location" not in out:
                out["location"] = None
            out.pop("transcript_prev", None)
            out.pop("prev_stt_used", None)
            out["transcript"] = self._read_transcript(meta)
            if with_prev:
                current = out["transcript"].strip()
                out["prev_transcripts"] = [item for item in reversed(self._read_prev_list(meta))
                                           if item["text"].strip() != current]
            return out

    def list(self, q=None, date_from=None, date_to=None, status=None, limit=200, tag=None):
        ql = q.lower() if q else None
        wanted_tag = tag_key(tag) if tag else None
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
            tags = meta.get("tags") or []
            if wanted_tag is not None and not any(tag_key(t) == wanted_tag for t in tags):
                continue
            text = self._cached_transcript(meta)
            label = meta.get("label") or ""
            title = meta.get("title") or ""
            match = None
            if ql is not None:
                lowered = text.lower()
                if ql in lowered or ql in title.lower():
                    match = "text"
                    idx = lowered.find(ql)
                    if idx >= 0:
                        start = max(0, idx - 40)
                        end = min(len(text), idx + len(q) + 40)
                        snippet = text[start:end]
                    else:
                        snippet = text[:80]
                elif ql in label.lower():
                    match = "label"
                    snippet = text[:80]
                elif any(ql in t.lower() for t in tags):
                    match = "tag"
                    snippet = text[:80]
                else:
                    continue
            else:
                snippet = text[:80]
            item = dict(meta)
            _fill_meta_defaults(item)
            if "location" not in item:
                item["location"] = None
            item.pop("transcript_prev", None)
            item.pop("prev_stt_used", None)
            item["snippet"] = snippet
            if match is not None:
                item["match"] = match
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

    def set_job(self, rid, jid):
        """받아쓰기 서버에 맡긴 작업 id 를 적는다(None 이면 지움). 앱 서버가 다시 떠도 이어 기다리는 데 쓴다.

        길이 상한은 여기서 걸지 않는다 - 맡길 때 stt.py 가 1~128자로 이미 확인하고, 여기서 자르면
        65~128자 id 가 잘린 채 저장돼 다시 뜬 뒤 이어받기가 404 → 중복 맡기기가 된다(G-092).
        """
        with self._lock:
            meta = self._load_meta(rid)
            if jid:
                meta["stt_job"] = str(jid)
            else:
                meta.pop("stt_job", None)
            self._write_json(self._meta_path(rid), meta)

    def set_transcript(self, rid, text, used=None):
        text = text or ""
        with self._lock:
            meta = self._load_meta(rid)
            path = self._transcript_path(meta)
            old = self._read_transcript(meta)
            prev_items = self._read_prev_list(meta)
            if old.strip() and old.strip() != text.strip():
                stt_used = meta.get("stt_used")
                entry_used = dict(stt_used) if isinstance(stt_used, dict) else None
                at = entry_used.get("at") if isinstance(entry_used, dict) else None
                prev_items.append({"text": old, "stt_used": entry_used,
                                   "at": at if isinstance(at, str) else None})
                current = text.strip()
                kept = [item for item in prev_items
                        if item["text"].strip() != current]
                seen = set()
                deduped = []
                for item in reversed(kept):
                    key = item["text"].strip()
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(item)
                prev_items = list(reversed(deduped))
                if len(prev_items) > PREV_KEEP:
                    prev_items = prev_items[-PREV_KEEP:]
                self._write_prev_list(meta, prev_items)
            self._atomic_write(path, text.encode("utf-8"))
            self._drop_cache(path)
            meta["title"] = " ".join(text.split())[:40]     # 화자 구분 글은 여러 줄 - 제목은 한 줄로
            meta["chars"] = len(text)
            meta["status"] = "done"
            meta["error"] = None
            meta["stt_used"] = dict(used, at=_now_iso()) if used is not None else None
            self._write_json(self._meta_path(rid), meta)

    def set_stt_options(self, rid, opts):
        norm = normalize(opts)
        with self._lock:
            meta = self._load_meta(rid)
            if opts is None:
                meta.pop("stt_options", None)
            else:
                meta["stt_options"] = norm
            self._write_json(self._meta_path(rid), meta)

    def effective_stt_options(self, meta):
        if isinstance(meta, dict):
            opts = meta.get("stt_options")
            if isinstance(opts, dict) and opts:
                return opts
        return self.default_stt_options()

    def default_stt_options(self):
        raw = self._read_json(self.root / "stt_options.json")
        if not isinstance(raw, dict):
            return {}
        try:
            return normalize(raw)
        except ValueError:
            return {}

    def set_default_stt_options(self, opts):
        norm = normalize(opts)
        with self._lock:
            self._write_json(self.root / "stt_options.json", norm)
        return norm

    def set_label_tags(self, rid, patch):
        with self._lock:
            meta = self._load_meta(rid)
            if "label" in patch:
                meta["label"] = patch["label"]
            if "tags" in patch:
                new_tags = patch["tags"]
                current = meta.get("tags") or []
                same_keys = [tag_key(t) for t in new_tags] == [tag_key(t) for t in current]
                old_auto_keys = {tag_key(t) for t in (meta.get("tags_auto") or [])}
                meta["tags"] = new_tags
                meta["tags_auto"] = [t for t in new_tags if tag_key(t) in old_auto_keys]
                if not same_keys:
                    meta["tags_human"] = True
            self._write_json(self._meta_path(rid), meta)

    def set_auto_tags(self, rid, tags, manual=False):
        with self._lock:
            meta = self._load_meta(rid)
            current = meta.get("tags") or []
            old_auto = meta.get("tags_auto") or []
            if not manual and meta.get("tags_human"):
                meta["autotag"] = "done"
                self._write_json(self._meta_path(rid), meta)
                return False
            if not manual:
                tags = tags[:10]
                meta["tags"] = tags
                meta["tags_auto"] = tags
            else:
                old_auto_keys = {tag_key(t) for t in old_auto}
                human = [t for t in current if tag_key(t) not in old_auto_keys]
                human_keys = {tag_key(t) for t in human}
                new_ai_keys = {tag_key(t) for t in tags}
                merged = merge_tags(human, tags)
                meta["tags"] = merged
                meta["tags_auto"] = [t for t in merged
                                     if tag_key(t) in new_ai_keys and tag_key(t) not in human_keys]
            meta["autotag"] = "done"
            self._write_json(self._meta_path(rid), meta)
            return True

    def set_autotag(self, rid, state):
        if state not in _AUTOTAG_STATES:
            raise ValueError("알 수 없는 자동 태그 상태입니다: " + str(state))
        with self._lock:
            meta = self._load_meta(rid)
            meta["autotag"] = state
            self._write_json(self._meta_path(rid), meta)

    def autotag_pending_ids(self):
        with self._lock:
            return [m["id"] for m in self._iter_meta() if m.get("autotag") == "pending"]

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
                ppath = self._prev_transcript_path(meta)
                if ppath.exists():
                    try:
                        os.unlink(ppath)
                        removed = True
                    except OSError:
                        pass
                pjpath = self._prev_json_path(meta)
                if pjpath.exists():
                    try:
                        os.unlink(pjpath)
                        removed = True
                    except OSError:
                        pass
            for candidate in self.audio_dir.glob(rid + ".*"):
                try:
                    os.unlink(candidate)
                    removed = True
                except OSError:
                    pass
            for suffix in (".txt", ".prev.txt", ".prev.json"):
                for candidate in self.transcripts_dir.glob("*/" + rid + suffix):
                    if suffix == ".txt":
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

    def delete_answer(self, aid):
        """답을 지운다. 지웠으면 True, 없으면 False, 아직 묻는 중이면 "running"(지우지 않음)."""
        if not _valid_aid(aid):
            return False
        with self._lock:
            path = self.answers_dir / (aid + ".json")
            data = self._read_json(path)
            if not isinstance(data, dict):
                return False
            if data.get("status") == "running":
                return "running"
            try:
                os.unlink(path)
            except FileNotFoundError:
                return False
            return True

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
            for item in items:       # 목록에서 무엇에 대한 답인지 알아보게 - 첫 녹취의 때와 첫마디(지워졌으면 None)
                item["about"] = None
                for rid in item.get("ids") or []:
                    meta = self._read_json(self._meta_path(rid)) if _valid_rid(rid) else None
                    if isinstance(meta, dict):
                        item["about"] = {"recorded_at": meta.get("recorded_at") or meta.get("created"),
                                         "title": meta.get("title")}
                        break
        return items
