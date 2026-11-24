#!/home/tsyi/miniconda3/envs/openclaw/bin/python3
"""흑석동성당(bstsd.or.kr) 주보 신규 게시 확인.

핵심 원칙: "새 주보인지"의 판단은 이 스크립트가 한다. 호출하는 에이전트는
마지막 줄의 판정(NOTIFY / NO_NOTIFY / FETCH_FAILED)만 보고 행동한다.

판정 기준: 사이트 최신 주보 날짜 > 직전에 알림을 보낸 주보 날짜
(미래 날짜 여부는 보지 않는다. 주보는 항상 과거~당일 날짜로 올라온다.)

표준 라이브러리만 사용한다 (requests/bs4 의존성 없음).

사용법:
    check_bulletin.py                      # 확인 후 판정 출력
    check_bulletin.py --mark-notified DATE # 알림 전송 성공 후 기준선 갱신
    check_bulletin.py --state-only         # 네트워크 없이 현재 상태만 출력
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime

URL = os.environ.get("BULLETIN_URL", "https://bstsd.or.kr/a/weekly")
DEFAULT_STATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "memory", "church-bulletin-last.json",
)
STATE_PATH = os.path.abspath(os.environ.get("BULLETIN_STATE", DEFAULT_STATE))
TIMEOUT = int(os.environ.get("BULLETIN_TIMEOUT", "15"))
UA = "Mozilla/5.0 (compatible; openclaw-church-bulletin-monitor/2.0)"

# 게시글 URL에 날짜가 박혀 있다 (.../a/weekly/2026-08-09-연중-제19주일).
# 제목 텍스트보다 안정적이라 이쪽을 1순위로 본다.
HREF_DATE = re.compile(r"/a/weekly/(20\d{2})-(\d{2})-(\d{2})")
TEXT_DATE = re.compile(r"(20\d{2})[.\-/](\d{2})[.\-/](\d{2})")


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, STATE_PATH)


def now_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def baseline(state):
    """직전에 알림을 보낸 주보 날짜. 없으면 None."""
    d = state.get("lastNotifiedBulletinDate")
    if d:
        return d
    # 구 스키마 호환: 알림을 보낸 적이 있으면 그때의 최신 주보를 기준선으로 본다.
    if state.get("notifiedDiscord") and state.get("latestBulletinDate"):
        return state["latestBulletinDate"]
    return None


def fetch_dates():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    found = set()
    for y, m, d in HREF_DATE.findall(html):
        found.add("%s-%s-%s" % (y, m, d))
    if not found:
        for y, m, d in TEXT_DATE.findall(html):
            found.add("%s-%s-%s" % (y, m, d))

    valid = []
    for s in found:
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            continue
        valid.append(s)
    return sorted(valid, reverse=True)


def cmd_mark_notified(target):
    state = load_state()
    state["lastNotifiedBulletinDate"] = target
    state["notifiedDiscord"] = True
    state["notifiedAt"] = now_iso()
    state["pendingNotify"] = False
    state["notificationError"] = None
    state["retryNeeded"] = False
    save_state(state)
    print("기준선 갱신: lastNotifiedBulletinDate = %s" % target)
    print("MARKED: %s" % target)
    return 0


def cmd_state_only():
    state = load_state()
    print("=== 흑석동성당 주보 상태 (네트워크 조회 안 함) ===")
    print("상태 파일: %s" % STATE_PATH)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_check():
    state = load_state()
    prev = baseline(state)

    try:
        dates = fetch_dates()
    except (urllib.error.URLError, OSError, ValueError) as e:
        state["lastCheck"] = now_iso()
        state["lastError"] = str(e)
        save_state(state)
        print("조회 실패: %s" % e, file=sys.stderr)
        print("FETCH_FAILED")
        return 2

    if not dates:
        state["lastCheck"] = now_iso()
        state["lastError"] = "no bulletin dates parsed"
        save_state(state)
        print("주보 목록을 찾을 수 없습니다 (사이트 구조 변경 가능).", file=sys.stderr)
        print("FETCH_FAILED")
        return 2

    latest = dates[0]

    print("=== 흑석동성당 주보 확인 ===")
    print("조회 시각: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("오늘 날짜: %s" % date.today())
    print("최신 주보: %s" % latest)
    print("직전 알림: %s" % (prev or "(없음)"))
    print()
    print("최근 주보 목록:")
    for d in dates[:5]:
        print("  - %s" % d)
    print()

    is_new = prev is None or latest > prev

    state["lastCheck"] = now_iso()
    state["latestBulletinDate"] = latest
    state["newBulletinFound"] = bool(is_new)
    state["lastError"] = None
    if prev is None:
        # 최초 실행: 지금 있는 최신 주보를 기준선으로 잡고 알리지 않는다.
        state["lastNotifiedBulletinDate"] = latest
        state["pendingNotify"] = False
        state["notifiedDiscord"] = False
        save_state(state)
        print("기준선 최초 설정 (%s) — 알림 없음" % latest)
        print("NO_NOTIFY")
        return 0

    if is_new:
        state["pendingNotify"] = True
        state["notifiedDiscord"] = False
        save_state(state)
        print("새 주보 감지: %s (직전 %s)" % (latest, prev))
        print("NOTIFY: %s" % latest)
        return 0

    state["pendingNotify"] = False
    save_state(state)
    print("새 주보 없음 (최신 %s 은 이미 알림 완료)" % latest)
    print("NO_NOTIFY")
    return 0


def main():
    p = argparse.ArgumentParser(description="흑석동성당 주보 확인")
    p.add_argument("--mark-notified", metavar="YYYY-MM-DD",
                   help="알림 전송에 성공한 뒤 호출. 해당 날짜를 기준선으로 저장한다.")
    p.add_argument("--state-only", action="store_true",
                   help="네트워크 조회 없이 현재 상태 파일만 출력")
    args = p.parse_args()

    if args.mark_notified:
        try:
            datetime.strptime(args.mark_notified, "%Y-%m-%d")
        except ValueError:
            print("날짜 형식이 잘못됨 (YYYY-MM-DD): %s" % args.mark_notified, file=sys.stderr)
            return 2
        return cmd_mark_notified(args.mark_notified)

    if args.state_only:
        return cmd_state_only()

    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
