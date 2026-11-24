#!/usr/bin/env python3
"""주보알림 논리: 확인, 미리 보기, 카톡 전송, 기록."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("JUBO_DATA", ROOT / "data"))
REF = ROOT / "ref"
CHECK_URL = "https://bstsd.or.kr/a/weekly"
OPENCLAW_STATE = Path.home() / ".openclaw/workspace/memory/church-bulletin-last.json"


def _choose_python() -> str:
    env = os.environ.get("BULLETIN_PY")
    if env:
        return env
    conda = Path("/home/tsyi/miniconda3/envs/openclaw/bin/python3")
    if conda.exists():
        return str(conda)
    return sys.executable


PY = _choose_python()
UA = "Mozilla/5.0 (compatible; openclaw-church-bulletin-monitor/2.0)"
STATE_PATH = DATA / "state.json"
HISTORY_PATH = DATA / "history.json"

POST_RE = re.compile(r"/a/weekly/(20\d{2})-(\d{2})-(\d{2})(?:-([^?#]*))?")
SITE_ORDER = ["maria", "bstsd"]
# pipeline.py 의 maria 1~7쪽 규칙과 같아야 한다 (ref/ 는 고치지 않는다)
MARIA_MAX_PAGES = 7

_LOCK = threading.Lock()
_BUSY: str | None = None


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _load_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _read_state() -> dict:
    data = _load_json(STATE_PATH, {})
    return data if isinstance(data, dict) else {}


def _save_state_key(key: str, value) -> None:
    data = _read_state()
    data[key] = value
    _save_json(STATE_PATH, data)


def _seed_from_openclaw(data: dict) -> dict:
    if data.get("sent"):
        return data
    openclaw = _load_json(OPENCLAW_STATE, None)
    if not isinstance(openclaw, dict):
        return data
    date = openclaw.get("lastNotifiedBulletinDate")
    if not date:
        return data
    data["sent"] = {
        "date": date,
        "title": "",
        "at": openclaw.get("notifiedAt"),
        "source": "openclaw",
    }
    try:
        _save_json(STATE_PATH, data)
    except OSError:
        pass
    return data


def _enter(name: str) -> bool:
    global _BUSY
    if not _LOCK.acquire(blocking=False):
        return False
    _BUSY = name
    return True


def _leave() -> None:
    global _BUSY
    _BUSY = None
    _LOCK.release()


def _busy_result() -> dict:
    return {"ok": False, "error": f"다른 작업({_BUSY or '?'}) 이 도는 중"}


def _run(cmd: list[str], timeout: int):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout or "", proc.stderr or "", None
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return None, out, err, f"{timeout}초 안에 끝나지 않았습니다"
    except Exception as exc:
        return None, "", "", f"실행하지 못했습니다: {exc}"


def _clear_files(path: Path, pattern: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for item in path.glob(pattern):
        try:
            item.unlink()
        except OSError:
            pass


def _page_key(path: Path) -> int:
    match = re.search(r"-(\d+)\.jpg$", path.name)
    return int(match.group(1)) if match else 0


def check() -> dict:
    if not _enter("check"):
        return _busy_result()
    at = _now()
    latest = None
    recent = []
    error = None
    try:
        req = urllib.request.Request(CHECK_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        posts = {}
        for href in re.findall(r'href="([^"]+)"', html):
            match = POST_RE.search(href)
            if not match:
                continue
            date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                continue
            if date in posts:
                continue
            slug = match.group(4) or ""
            title = urllib.parse.unquote(slug).replace("-", " ").strip()
            posts[date] = {
                "date": date,
                "title": title,
                "url": urllib.parse.urljoin(CHECK_URL, href),
            }

        if not posts:
            error = "주보 날짜를 찾지 못했습니다 (사이트 구조가 바뀌었을 수 있습니다)"
        else:
            recent = [posts[d] for d in sorted(posts, reverse=True)[:5]]
            latest = recent[0]
    except Exception as exc:
        error = f"사이트를 읽지 못했습니다: {exc}"

    result = {
        "ok": error is None,
        "at": at,
        "latest": latest,
        "recent": recent,
        "error": error,
    }
    try:
        _save_state_key("last_check", result)
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"확인 결과를 저장하지 못했습니다: {exc}"
    finally:
        _leave()
    return result


def history(limit: int = 20) -> list:
    data = _load_json(HISTORY_PATH, [])
    if not isinstance(data, list):
        return []
    return data[:limit]


def state() -> dict:
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        data = _seed_from_openclaw(_read_state())
    except OSError:
        data = _read_state()

    sent = data.get("sent")
    if not isinstance(sent, dict):
        sent = None
    last_check = data.get("last_check")
    if not isinstance(last_check, dict):
        last_check = None
    preview = data.get("preview")
    if not isinstance(preview, dict):
        preview = None

    if last_check is None or not last_check.get("ok"):
        is_new = None
    elif sent is None:
        is_new = True
    else:
        latest = last_check.get("latest")
        latest_date = latest.get("date") if isinstance(latest, dict) else None
        sent_date = sent.get("date")
        is_new = (
            bool(latest_date and isinstance(sent_date, str) and latest_date > sent_date)
            if sent_date
            else None
        )

    return {
        "sent": sent,
        "last_check": last_check,
        "is_new": is_new,
        "busy": _BUSY,
        "history": history(20),
        "preview": preview,
    }


def preview() -> dict:
    if not _enter("preview"):
        return _busy_result()
    at = _now()
    bulletins = []
    images = []
    collected: dict[str, list[Path]] = {}
    error = None
    try:
        pdf_dir = DATA / "pdf"
        preview_dir = DATA / "preview"
        _clear_files(pdf_dir, "*.pdf")
        _clear_files(preview_dir, "*.jpg")

        cmd = [
            PY,
            str(REF / "bulletin-pdf-downloader/scripts/download.py"),
            "--all",
            "--download-dir",
            str(pdf_dir),
            "--format",
            "json",
        ]
        rc, out, err, timed_out = _run(cmd, 180)
        results = None
        if timed_out:
            error = timed_out
        else:
            try:
                results = json.loads(out)
                if not isinstance(results, list):
                    raise ValueError("JSON 배열이 아닙니다")
            except Exception as exc:
                detail = (err or out).strip()[-300:]
                error = f"다운로드 스크립트 실패(rc={rc}): {detail or exc}"

        if isinstance(results, list):
            ordered = sorted(
                results,
                key=lambda r: SITE_ORDER.index(r.get("site"))
                if r.get("site") in SITE_ORDER
                else len(SITE_ORDER),
            )
            for result in ordered:
                site = str(result.get("site") or "?")
                item = {
                    "site": site,
                    "site_name": result.get("site_name") or site,
                    "date": result.get("date"),
                    "title": result.get("title") or "",
                    "ok": bool(result.get("success")),
                    "error": result.get("error"),
                }
                if item["ok"]:
                    pdf_path = result.get("filepath")
                    if not pdf_path or not Path(pdf_path).exists():
                        item["ok"] = False
                        item["error"] = "받은 PDF 파일이 없습니다"
                    else:
                        prefix = preview_dir / site
                        conv_rc, conv_out, conv_err, conv_timed = _run(
                            ["pdftoppm", "-jpeg", "-r", "60", str(pdf_path), str(prefix)],
                            120,
                        )
                        if conv_timed or conv_rc != 0:
                            item["ok"] = False
                            item["error"] = conv_timed or (
                                f"PDF 그림 변환 실패: {(conv_err or conv_out).strip()[:300]}"
                            )
                        else:
                            files = sorted(
                                preview_dir.glob(f"{site}-*.jpg"), key=_page_key
                            )
                            if not files:
                                item["ok"] = False
                                item["error"] = "그림이 만들어지지 않았습니다"
                            else:
                                if site == "maria":
                                    kept = [f for f in files if _page_key(f) <= MARIA_MAX_PAGES]
                                else:
                                    kept = list(files)
                                for image in files:
                                    if image not in kept:
                                        try:
                                            image.unlink()
                                        except OSError:
                                            pass
                                collected[site] = kept
                bulletins.append(item)
    except Exception as exc:
        error = f"미리 보기를 만들지 못했습니다: {exc}"

    failed = [b for b in bulletins if not b["ok"]]
    seq = 1
    for site in SITE_ORDER:
        files = collected.get(site, [])
        if site == "bstsd":
            files = sorted(files, key=_page_key, reverse=True)
        for image in files:
            images.append({"site": site, "name": image.name, "seq": seq})
            seq += 1
    ok = bool(bulletins) and not failed and bool(images)
    if not ok and error is None:
        if not bulletins:
            error = "주보를 받지 못했습니다"
        else:
            error = "; ".join(f"{b['site']}: {b['error']}" for b in failed)

    result = {
        "ok": ok,
        "at": at,
        "bulletins": bulletins,
        "images": images,
        "error": error,
    }
    try:
        _save_state_key("preview", result)
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"미리 보기 결과를 저장하지 못했습니다: {exc}"
    finally:
        _leave()
    return result


def send() -> dict:
    if not _enter("send"):
        return _busy_result()
    try:
        at = _now()
        rc = None
        log = ""
        timed_out = None
        try:
            rc, out, err, timed_out = _run(
                [PY, str(REF / "bulletin-pdf-downloader/scripts/pipeline.py")], 600
            )
            log = out + ("\n" + err if err else "")
        except Exception as exc:
            timed_out = f"전송 절차를 실행하지 못했습니다: {exc}"

        ok = rc == 0 and timed_out is None
        date = None
        title = ""
        for line in log.splitlines():
            match = re.search(
                r"✅\s*bstsd:\s*(\d{4}-\d{2}-\d{2})\s*-\s*(.*?)\s*$", line
            )
            if match:
                date = match.group(1)
                title = match.group(2)

        if date is None:
            last_check = _read_state().get("last_check")
            latest = last_check.get("latest") if isinstance(last_check, dict) else None
            if isinstance(latest, dict):
                date = latest.get("date")
                title = latest.get("title") or ""

        reason = None
        if ok:
            try:
                _save_state_key(
                    "sent",
                    {"date": date, "title": title, "at": at, "source": "app"},
                )
            except Exception as exc:
                ok = False
                reason = f"보낸 주보를 저장하지 못했습니다: {exc}"
        elif timed_out:
            reason = timed_out
        else:
            lines = [line.strip() for line in log.splitlines() if line.strip()]
            error_lines = [line for line in lines if "ERROR" in line]
            if error_lines:
                reason = error_lines[-1]
            elif lines:
                reason = "\n".join(lines[-3:])
            else:
                reason = "까닭을 로그에서 찾지 못했습니다"

        entry = {
            "at": at,
            "date": date,
            "title": title,
            "ok": ok,
            "reason": reason,
            "rc": rc,
        }
        try:
            records = history(200)
            records.insert(0, entry)
            _save_json(HISTORY_PATH, records[:200])
        except Exception:
            pass

        return {"ok": ok, "entry": entry, "log_tail": log.splitlines()[-40:]}
    finally:
        _leave()
