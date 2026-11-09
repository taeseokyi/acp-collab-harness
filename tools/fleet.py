#!/usr/bin/env python3
"""작업자 운영 도우미 (관리자 전용).

`AIMEM.md` `8.0` 의 **ACP 일회성 자식** 체제(2026-11-09, claude/codex/opencode)를
전제합니다. 판단은 사람이 하고, 이 도구는 옮겨 적는 일과 대조만 합니다.

  python3 tools/fleet.py status              # REV / 슬롯 / 열린 태스크 / 미커밋
  python3 tools/fleet.py brief --slot S1 ... # 브리프 머리말 + 쓰기 경로 6절 대조
  python3 tools/fleet.py close               # 거두기 전 점검

2026-09-22 (REV 91) 에 `open` / `prepare` 를 폐기했습니다. 둘 다 상주 슬롯을
여는 절차(`8.5`)의 도우미였고, 지금은 관리자가 일회성 자식을 직접 띄웁니다.
2026-11-09 (REV 107) 부터 자식은 ACP 하네스이고 `brief` 가 스폰 호출문을 같이 찍습니다.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AIMEM = ROOT / "AIMEM.md"


def sh(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def read_rev():
    for line in AIMEM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \*\*REV: (\d+)\*\*", line)
        if m:
            return int(m.group(1))
    sys.exit("AIMEM.md 에서 REV 를 찾지 못했습니다")


def roster():
    """2절 명부에서 슬롯 -> (확인토큰, 하네스, 세션키) 를 읽습니다."""
    out = {}
    for line in AIMEM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(S\d)\s*\|\s*`([0-9a-f]+)`\s*\|\s*([^|]*?)\s*\|[^|]*\|\s*([^|]*?)\s*\|", line)
        if m:
            out[m.group(1)] = (m.group(2), m.group(3).strip(), m.group(4).strip())
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
    for slot, (token, harness, key) in sorted(roster().items()):
        print(f"  {slot}  {token}  {harness:<9} {key or '(비어 있음)'}")
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
    # 거두지 않은 ACP 일회성 자식이 남아 있는지 (`8.0`. 정상이면 턴 끝에 사라집니다).
    # 조회에 실패하면 조용히 넘어갑니다 -
    # 게이트웨이가 안 떠 있어도 나머지 점검은 쓸모가 있습니다.
    try:
        res = sh("openclaw", "gateway", "call", "sessions.list", "--json")
    except OSError:
        res = None  # openclaw 바이너리가 PATH 에 없는 환경(cron 등)
    if res is not None and res.returncode == 0:
        try:
            payload = json.loads(res.stdout)
        except ValueError:
            payload = None
        sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
        if not isinstance(sessions, list):
            sessions = []
        left = [s.get("key", "") for s in sessions
                if isinstance(s, dict) and ":acp:" in s.get("key", "")]
        for key in left:
            problems.append(f"ACP 세션이 남아 있습니다: {key}\n    "
                            f"openclaw gateway call sessions.delete "
                            f"--params '{{\"key\":\"{key}\"}}' --timeout 60000 --json")
    if not problems:
        print("종료 준비 완료. 걸리는 것 없습니다.")
        return 0
    print("종료 전에 정리할 것:")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    return 1


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
    token, harness, _key = r[slot]
    # 세션키는 요구하지 않습니다. 일회성 자식은 매번 새 세션이고 명부의 세션키 칸은
    # 비어 있는 것이 정상입니다 (`8.0`). 대조에 쓰는 것은 슬롯 ID / 확인토큰 / REV 입니다.
    if harness not in ("claude", "codex", "opencode"):
        sys.exit(f"{slot} 의 하네스 칸이 ACP 하네스가 아닙니다: {harness!r} (2절을 고치십시오)")
    rev = read_rev()
    pats = owned_paths(slot)

    bad = [w for w in args.write if not path_allowed(w, pats)]
    if bad:
        print(f"지시를 만들지 않았습니다. {slot} 소유가 아닌 경로입니다:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        print(f"  {slot} 소유: {', '.join(pats) or '(없음)'}", file=sys.stderr)
        return 2

    print(f"# 스폰: sessions_spawn(runtime:\"acp\", agentId:\"{harness}\", mode:\"run\", "
          f"context:\"isolated\", label:\"{slot} ...\", task:<아래 본문>)")
    print(f"슬롯 {slot} / 확인토큰 {token} / 하네스 {harness} / AIMEM REV {rev}")
    if args.task:
        print(f"쓰기는 {', '.join(args.write)} 에만 하십시오." if args.write else "")
        print()
        print(args.task)
    print()
    print("보고는 이 응답 본문에 직접 쓰십시오. 아웃박스에 쓰지 마십시오.")
    print()
    print(f"# 쓰기 경로 {len(args.write)}건 전부 6절상 {slot} 소유")
    return 0


def main():
    p = argparse.ArgumentParser(description="작업자 운영 도우미 (관리자 전용)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="AIMEM REV / 슬롯 / 열린 태스크 / 미커밋 한눈에")
    c = sub.add_parser("close", help="거두기 전 점검 - 정리할 것을 짚어 줍니다")
    c.add_argument("--slot", help="특정 슬롯만 점검")
    b = sub.add_parser("brief", help="브리프 머리말 - 슬롯/토큰/REV 자동, 쓰기 경로를 6절과 대조")
    b.add_argument("--slot", required=True)
    b.add_argument("--write", nargs="*", default=[], help="이 지시에서 쓸 경로")
    b.add_argument("--task", help="지시 본문")
    a = p.parse_args()
    return {"status": cmd_status, "close": cmd_close, "brief": cmd_brief}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
