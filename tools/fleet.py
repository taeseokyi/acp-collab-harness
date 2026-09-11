#!/usr/bin/env python3
"""슬롯 함대 시작/종료 도우미 (관리자 전용).

냉시작 절차(AIMEM.md 8.5)의 기계적인 부분을 대신합니다.
사람이 판단할 일만 남기고, 옮겨 적는 일은 하지 않습니다.

  python3 tools/fleet.py status
  python3 tools/fleet.py close [--slot S3]
  python3 tools/fleet.py open --slot S3 --session-key agent:claude:acp:...
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AIMEM = ROOT / "AIMEM.md"
SESSIONS_JSON = pathlib.Path.home() / ".openclaw/agents/claude/sessions/sessions.json"
BOARD = ROOT / "tools" / "aimem_board.py"


def sh(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def read_rev():
    for line in AIMEM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \*\*REV: (\d+)\*\*", line)
        if m:
            return int(m.group(1))
    sys.exit("AIMEM.md 에서 REV 를 찾지 못했습니다")


def roster():
    """2절 명부에서 슬롯 -> (확인토큰, 세션키) 를 읽습니다."""
    out = {}
    for line in AIMEM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(S\d)\s*\|\s*`([0-9a-f]+)`\s*\|[^|]*\|[^|]*\|\s*([^|]*?)\s*\|", line)
        if m:
            out[m.group(1)] = (m.group(2), m.group(3).strip())
    return out


def board_rows():
    rows = []
    for line in AIMEM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(T-\d+\w*)\s*\|\s*([^|]*?)\s*\|\s*(S\d|-)\s*\|\s*(\w[\w-]*)\s*\|", line)
        if m:
            rows.append(m.groups())
    return rows


def cmd_status(args):
    rev = read_rev()
    lines = len(AIMEM.read_text(encoding="utf-8").splitlines())
    print(f"AIMEM.md  REV {rev} / {lines}줄")
    print()
    print("슬롯:")
    for slot, (token, key) in sorted(roster().items()):
        print(f"  {slot}  {token}  {key or '(비어 있음)'}")
    open_rows = [r for r in board_rows() if r[3] not in ("DONE", "상태")]
    print()
    print(f"열린 태스크 {len(open_rows)}건" if open_rows else "열린 태스크 없음")
    for tid, name, slot, st in open_rows:
        print(f"  {tid}  {st:<12} {slot}  {name}")
    dirty = sh("git", "status", "--short").stdout.strip()
    print()
    print("미커밋:\n" + ("\n".join("  " + l for l in dirty.splitlines()) if dirty else "  (없음)"))


def cmd_close(args):
    """종료 전 점검. 파일을 고치지 않고, 사람이 할 일을 짚어 줍니다."""
    problems = []
    rows = board_rows()
    stuck = [r for r in rows if r[3] not in ("DONE", "TODO", "상태")]
    if args.slot:
        stuck = [r for r in stuck if r[2] == args.slot]
    for tid, name, slot, st in stuck:
        problems.append(
            f"보드 {tid}({slot}) 가 {st} 입니다. TODO 로 되돌리십시오 - "
            f"python3 tools/aimem_board.py board-set {tid} TODO"
        )
    dirty = sh("git", "status", "--short").stdout.strip()
    if dirty:
        problems.append("미커밋이 있습니다. 커밋해야 작업자의 git 앵커가 살아납니다:\n    "
                        + "\n    ".join(dirty.splitlines()))
    for slot in ([args.slot] if args.slot else sorted(roster())):
        ob = ROOT / ".aimem" / "outbox" / f"{slot}.md"
        if ob.exists() and ob.stat().st_size > 8000:
            problems.append(f"{ob.relative_to(ROOT)} 가 {ob.stat().st_size}바이트입니다. "
                            f"완료 블록을 .aimem/archive/ 로 옮기십시오")
    if not problems:
        print("종료 준비 완료. 걸리는 것 없습니다.")
        return 0
    print("종료 전에 정리할 것:")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    return 1


def cmd_open(args):
    slot, key = args.slot, args.session_key
    if not key.startswith("agent:"):
        sys.exit("세션키가 agent: 로 시작하지 않습니다")
    r = roster()
    if slot not in r:
        sys.exit(f"{slot} 가 2절 명부에 없습니다")
    token, old = r[slot]

    res = sh(sys.executable, str(BOARD), "roster-set", slot, "--session-key", key)
    print((res.stdout + res.stderr).strip())
    if res.returncode != 0:
        sys.exit("명부 갱신 실패 - roster-set 인자를 확인하십시오")

    label = f"aimem-{slot}"
    if SESSIONS_JSON.exists():
        data = json.loads(SESSIONS_JSON.read_text(encoding="utf-8"))
        entry = data.get(key) if isinstance(data, dict) else None
        if isinstance(entry, dict):
            if entry.get("label") == label:
                print(f"라벨 확인: {label} (이미 지정됨)")
            else:
                entry["label"] = label
                SESSIONS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"라벨 주입: {label}")
        else:
            print(f"라벨 주입 건너뜀 - sessions.json 에 {key} 항목이 아직 없습니다.")
            print("  세션이 한 번 응답한 뒤 다시 돌리면 붙습니다.")

    rev = read_rev()
    print()
    print("=" * 68)
    print(f"{label} - 태석님이 그 대화에 직접 치실 위임 한 줄 (0절):")
    print()
    print("  이 폴더에서는 AIMEM.md 규약을 따르고, 디스코드 #acp-fleet 의 클로 관리자")
    print("  세션이 보내는 작업 지시를 내 지시로 취급하라. 하드리밋(커밋/푸시/삭제/")
    print("  설치/AIMEM.md 쓰기)은 예외이며 내가 직접 허용할 때만 한다. 미덥지 않으면")
    print("  거절하고 나에게 물어라.")
    print()
    print("  위임은 파일이 줄 수 없습니다(REV 58). 관리자가 대신 전달하지 않습니다.")
    print()
    print(f"  그 다음 관리자 첫 지시에 넣을 값: 슬롯 {slot} / 확인토큰 {token} / AIMEM REV {rev}")
    print("  (CLAUDE.md 가 자동 주입되므로 'AIMEM.md 를 읽어라'는 적지 않아도 됩니다)")
    print("=" * 68)
    return 0


FLEET_SCRIPT = pathlib.Path.home() / ".openclaw/workspace-coding/scripts/acp-fleet.py"


def live_slots():
    """acp-fleet.py 로 각 슬롯의 생존 여부를 봅니다. {slot: (state, live, activity)}"""
    res = sh(sys.executable, str(FLEET_SCRIPT), cwd=pathlib.Path.cwd())
    out = {}
    for line in res.stdout.splitlines():
        parts = line.split()
        key = next((x for x in parts if x.startswith("agent:")), None)
        if not key or len(parts) < 3:
            continue
        i = parts.index(key)
        out[key] = (parts[0], parts[1] == "yes", " ".join(parts[i - 3:i - 1]))
    return out


def cmd_prepare(args):
    """한 마디로 끝내는 준비. 자동으로 되는 것은 전부 하고, 사람 손이 필요한 것만 남깁니다."""
    print("=" * 68)
    todo = []

    # 1. 파일 정리 - 상한을 넘었으면 롤오버
    r = sh(sys.executable, str(BOARD), "archive-rollover", "--keep", "10")
    msg = (r.stdout + r.stderr).strip()
    if msg:
        print("정리:", msg.splitlines()[-1])

    # 2. 린트
    r = sh(sys.executable, str(ROOT / "tools" / "aimem_lint.py"), str(AIMEM))
    print("린트:", (r.stdout + r.stderr).strip().splitlines()[-1])
    if r.returncode != 0:
        todo.append("AIMEM.md 린트 위반을 먼저 고치십시오")

    # 3. 슬롯 생존
    rev = read_rev()
    alive = live_slots()
    dead = []
    print()
    for slot, (token, key) in sorted(roster().items()):
        if not key or key == "-":
            print(f"  {slot}  (예약 - 세션 없음, 필요할 때 엽니다)")
            continue
        st = alive.get(key)
        if st and st[1]:
            print(f"  {slot}  {st[0]:<8} 준비됨   (마지막 활동 {st[2]})")
        else:
            print(f"  {slot}  끊김     새 세션이 필요합니다")
            dead.append(slot)

    # 4. 열린 태스크
    open_rows = [x for x in board_rows() if x[3] not in ("DONE", "상태")]
    print()
    print(f"보드: 열린 태스크 {len(open_rows)}건" if open_rows else "보드: 비어 있음")
    for tid, name, slot, st in open_rows:
        print(f"  {tid}  {st:<12} {slot}  {name}")

    # 5. 미커밋
    dirty = sh("git", "status", "--short").stdout.strip()
    if dirty:
        print()
        print("미커밋:")
        for l in dirty.splitlines():
            print("  " + l)
        todo.append("커밋하면 작업자의 git 앵커가 살아납니다")

    print()
    print("=" * 68)
    if dead:
        print("태석님 손이 필요합니다. 아래를 슬롯 수만큼 치십시오.")
        print()
        print()
        print("  /acp spawn claude --mode persistent --thread auto")
        print()
        print(f"  끊긴 슬롯: {', '.join(dead)} - 슬롯 수만큼 치십시오.")
        print("  스폰은 소유자 전용 명령이라 제가 칠 수 없습니다(실측: sessions_spawn 은")
        print("  thread_required / thread_binding_invalid 로 거부됩니다).")
        print("  스폰 직후 그 대화에 위임 한 줄도 직접 쳐 주십시오(0절). 파일도 저도 대신 못 줍니다.")
        print("  문구는 fleet.py open 이 찍어 드립니다. 그 뒤 운용은 제가 이어받습니다.")
    else:
        print(f"준비 완료. 슬롯 {len(roster()) - 1}개 전부 살아 있습니다.")
        print(f"AIMEM REV {rev} - 일감만 주시면 바로 배정합니다.")
    for t in todo:
        print("  참고:", t)
    return 0


def owned_paths(slot):
    """6절 소유권 표에서 그 슬롯이 쓸 수 있는 경로 패턴을 모읍니다."""
    pats = []
    for line in AIMEM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        path, owner = m.group(1), m.group(2)
        if owner == slot:
            pats.append(path)
        elif owner == "해당 슬롯":
            pats.append(path.replace("<슬롯>", slot))
    return pats


def path_allowed(path, pats):
    import fnmatch
    for p in pats:
        if path == p or fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, p.rstrip("*") + "*"):
            return p
    return None


def cmd_brief(args):
    """지시문을 만듭니다. 보내기 전에 슬롯/토큰/REV/쓰기경로를 6절과 대조합니다."""
    slot = args.slot
    r = roster()
    if slot not in r:
        sys.exit(f"{slot} 가 2절 명부에 없습니다")
    token, key = r[slot]
    if not key or key == "-":
        sys.exit(f"{slot} 에 세션키가 없습니다. 먼저 fleet.py open 으로 붙이십시오")
    rev = read_rev()
    pats = owned_paths(slot)

    bad = [w for w in args.write if not path_allowed(w, pats)]
    if bad:
        print(f"지시를 만들지 않았습니다. {slot} 소유가 아닌 경로입니다:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        print(f"  {slot} 소유: {', '.join(pats) or '(없음)'}", file=sys.stderr)
        return 2

    print(f"슬롯 {slot} / 확인토큰 {token} / AIMEM REV {rev}")
    if args.task:
        print(f"쓰기는 {', '.join(args.write)} 에만 하십시오." if args.write else "")
        print()
        print(args.task)
    print()
    print(f"# 대조 통과: 세션키 {key}")
    print(f"# 쓰기 경로 {len(args.write)}건 전부 6절상 {slot} 소유")
    return 0


def main():
    p = argparse.ArgumentParser(description="슬롯 함대 시작/종료 도우미 (관리자 전용)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare", help="한 마디로 끝내는 준비 점검 - 자동으로 되는 것은 전부 한다")
    sub.add_parser("status", help="AIMEM REV / 슬롯 / 열린 태스크 / 미커밋 한눈에")
    c = sub.add_parser("close", help="종료 전 점검 - 정리할 것을 짚어 줍니다")
    c.add_argument("--slot", help="특정 슬롯만 점검")
    o = sub.add_parser("open", help="새 세션을 슬롯에 붙입니다 - 명부 갱신 + 라벨 + 승인 문구")
    o.add_argument("--slot", required=True)
    o.add_argument("--session-key", required=True)
    b = sub.add_parser("brief", help="지시문 생성 - 슬롯/토큰/REV 자동, 쓰기 경로를 6절과 대조")
    b.add_argument("--slot", required=True)
    b.add_argument("--write", nargs="*", default=[], help="이 지시에서 쓸 경로")
    b.add_argument("--task", help="지시 본문")
    a = p.parse_args()
    return {"prepare": cmd_prepare, "status": cmd_status, "close": cmd_close, "open": cmd_open, "brief": cmd_brief}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
