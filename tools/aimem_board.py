#!/usr/bin/env python3
"""AIMEM.md 표 갱신 CLI. 표준 라이브러리만 사용.

인라인 문자열 치환 대신, 표 구조를 파싱해 셀 단위로 고치고 매 쓰기 뒤
aimem_lint.lint_text() 로 검증한다. 위반이 나면 파일을 원래대로 되돌리고
exit 1 한다 - 규약을 깨는 갱신을 애초에 저장하지 않는 것이 이 도구의 핵심 가치다.
"""

import argparse
import datetime
import difflib
import re
import sys
from pathlib import Path

import aimem_lint as lint

NEXT_HEADING_RE = re.compile(r"^##(?!#)\s")


def die(msg: str) -> None:
    print(f"오류: {msg}", file=sys.stderr)
    sys.exit(1)


def sanitize(value: str) -> str:
    if "\n" in value:
        die("셀 값에 줄바꿈을 포함할 수 없음")
    return value.strip().replace("|", "\\|")


def row_line(cells):
    return "| " + " | ".join(cells) + " |"


def find_section(lines, number):
    return lint._find_section(lines, number)


def find_queue_section(lines):
    """'## 4.5 대기 큐' 절. lint._find_section 은 정수 번호만 받으므로 여기서 직접 찾는다."""
    heading_re = re.compile(r"^##(?!#)\s*4\.5\s")
    start = None
    for i, line in enumerate(lines):
        if heading_re.match(line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if NEXT_HEADING_RE.match(lines[i]):
            end = i
            break
    return start, end


def table_block(lines, start, end):
    """(header_idx, sep_idx, data_idxs) - lint._extract_table 의 블록 탐지 규칙과 동일하게 맞춘다."""
    pipe_lines = [i for i in range(start, end) if lines[i].strip().startswith("|")]
    if not pipe_lines:
        return None
    block = [pipe_lines[0]]
    for i in pipe_lines[1:]:
        if i == block[-1] + 1:
            block.append(i)
        else:
            break
    if len(block) < 2:
        return None
    return block[0], block[1], block[2:]


def replace_row_cells(lines, start, end, key_col, key_val, updates):
    table = lint._extract_table(lines, start, end)
    if table is None:
        return False, "표를 찾을 수 없음"
    header_cells, rows = table
    key_idx = lint._col_index(header_cells, key_col)
    if key_idx is None:
        return False, f"열을 찾을 수 없음: {key_col}"
    col_idxs = {}
    for col_name in updates:
        idx = lint._col_index(header_cells, col_name)
        if idx is None:
            return False, f"열을 찾을 수 없음: {col_name}"
        col_idxs[col_name] = idx
    for line_no, cells in rows:
        if cells[key_idx].strip("` ") == key_val:
            new_cells = list(cells)
            for col_name, val in updates.items():
                new_cells[col_idxs[col_name]] = val
            lines[line_no - 1] = row_line(new_cells)
            return True, None
    return False, f"'{key_val}' 에 해당하는 행을 찾을 수 없음"


def append_row(lines, start, end, cells):
    block = table_block(lines, start, end)
    if block is None:
        return False, "표를 찾을 수 없음"
    _, sep_idx, data_idxs = block
    insert_at = (data_idxs[-1] + 1) if data_idxs else (sep_idx + 1)
    lines.insert(insert_at, row_line(cells))
    return True, None


def pop_first_row(lines, start, end, order_col):
    table = lint._extract_table(lines, start, end)
    if table is None:
        return None, None, "표를 찾을 수 없음"
    header_cells, rows = table
    if not rows:
        return None, None, "큐가 비어 있음"
    order_idx = lint._col_index(header_cells, order_col)
    popped_line_no, popped_cells = rows[0]
    del lines[popped_line_no - 1]
    for new_order, (line_no, cells) in enumerate(rows[1:], start=1):
        idx0 = line_no - 2  # 삭제로 한 줄 당겨짐 (1-indexed -> 0-indexed, -1 더)
        new_cells = list(cells)
        if order_idx is not None:
            new_cells[order_idx] = str(new_order)
        lines[idx0] = row_line(new_cells)
    return popped_cells, header_cells, None


# ---- 하위 명령 ----

def cmd_rev_bump(args, lines):
    rev_matches = [(i, m) for i, line in enumerate(lines) for m in [lint.REV_RE.search(line)] if m]
    if not rev_matches:
        die("REV 선언을 찾을 수 없음")
    if len(rev_matches) > 1:
        die(f"REV 선언이 {len(rev_matches)}번 등장함 - 수동 확인 필요")
    idx, m = rev_matches[0]
    cur = int(m.group(1))
    new_rev = args.to if args.to is not None else cur + 1
    if new_rev <= 0:
        die(f"REV 값은 양의 정수여야 함: {new_rev}")
    line = lines[idx]
    lines[idx] = line[: m.start(1)] + str(new_rev) + line[m.end(1):]

    updated_idx = next((i for i, l in enumerate(lines) if "최종 갱신:" in l), None)
    if updated_idx is None:
        die("'최종 갱신:' 줄을 찾을 수 없음")
    now_str = args.now.strip() if args.now else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not now_str.endswith("KST"):
        now_str = f"{now_str} KST"
    prefix_m = re.match(r"^(.*최종 갱신:\s*).*$", lines[updated_idx])
    lines[updated_idx] = prefix_m.group(1) + now_str
    return f"REV {cur} -> {new_rev}, 최종 갱신: {now_str}"


def cmd_board_set(args, lines):
    if args.status not in lint.VALID_STATUSES:
        die(f"허용되지 않는 상태값: {args.status} (허용: {', '.join(sorted(lint.VALID_STATUSES))})")
    section = find_section(lines, 3)
    if section is None:
        die("'3. 작업 보드' 절을 찾을 수 없음")
    start, end = section
    ok, err = replace_row_cells(lines, start, end, "ID", args.task_id, {"상태": args.status})
    if not ok:
        die(err)
    return f"board-set {args.task_id} -> {args.status}"


def cmd_board_add(args, lines):
    if args.status not in lint.VALID_STATUSES:
        die(f"허용되지 않는 상태값: {args.status} (허용: {', '.join(sorted(lint.VALID_STATUSES))})")
    section = find_section(lines, 3)
    if section is None:
        die("'3. 작업 보드' 절을 찾을 수 없음")
    start, end = section
    table = lint._extract_table(lines, start, end)
    if table is None:
        die("'3. 작업 보드' 표를 찾을 수 없음")
    header_cells, rows = table
    id_idx = lint._col_index(header_cells, "ID")
    if id_idx is not None:
        for _, cells in rows:
            if cells[id_idx].strip("` ") == args.task_id:
                die(f"이미 존재하는 태스크 ID: {args.task_id}")
    cells = [
        sanitize(args.task_id),
        sanitize(args.name),
        sanitize(args.slot),
        sanitize(args.status),
        sanitize(args.handoff),
        sanitize(args.artifact),
    ]
    ok, err = append_row(lines, start, end, cells)
    if not ok:
        die(err)
    return f"board-add {args.task_id} ({args.slot}, {args.status})"


def cmd_queue_pop(args, lines):
    section = find_queue_section(lines)
    if section is None:
        die("'4.5 대기 큐' 절을 찾을 수 없음")
    start, end = section
    popped, header_cells, err = pop_first_row(lines, start, end, "순서")
    if popped is None:
        die(err)
    pairs = "; ".join(f"{h}={v}" for h, v in zip(header_cells, popped))
    return f"queue-pop -> {pairs}"


def cmd_queue_add(args, lines):
    section = find_queue_section(lines)
    if section is None:
        die("'4.5 대기 큐' 절을 찾을 수 없음")
    start, end = section
    table = lint._extract_table(lines, start, end)
    if table is None:
        die("'4.5 대기 큐' 표를 찾을 수 없음")
    header_cells, rows = table
    order_idx = lint._col_index(header_cells, "순서")
    max_order = 0
    if order_idx is not None:
        for _, cells in rows:
            try:
                max_order = max(max_order, int(cells[order_idx].strip("` ")))
            except ValueError:
                pass
    new_order = max_order + 1
    cells = [
        str(new_order),
        sanitize(args.task),
        sanitize(args.candidate_slot),
        sanitize(args.handoff),
        sanitize(args.note),
    ]
    ok, err = append_row(lines, start, end, cells)
    if not ok:
        die(err)
    return f"queue-add #{new_order} {args.task}"


def cmd_roster_set(args, lines):
    section = find_section(lines, 2)
    if section is None:
        die("'2. 세션 명부' 절을 찾을 수 없음")
    start, end = section
    updates = {"세션키": sanitize(args.session_key)}
    if args.role is not None:
        updates["역할"] = sanitize(args.role)
    if args.note is not None:
        updates["비고"] = sanitize(args.note)
    if args.harness is not None:
        updates["하네스"] = sanitize(args.harness)
    ok, err = replace_row_cells(lines, start, end, "슬롯", args.slot, updates)
    if not ok:
        die(err)
    return f"roster-set {args.slot}: {', '.join(f'{k}={v}' for k, v in updates.items())}"


def cmd_owner_add(args, lines):
    section = find_section(lines, 6)
    if section is None:
        die("'6. 파일 소유권' 절을 찾을 수 없음")
    start, end = section
    cells = [sanitize(args.path_pattern), sanitize(args.owner_slot), sanitize(args.note)]
    ok, err = append_row(lines, start, end, cells)
    if not ok:
        die(err)
    return f"owner-add {args.path_pattern} -> {args.owner_slot}"


CMD_FUNCS = {
    "rev-bump": cmd_rev_bump,
    "board-set": cmd_board_set,
    "board-add": cmd_board_add,
    "queue-pop": cmd_queue_pop,
    "queue-add": cmd_queue_add,
    "roster-set": cmd_roster_set,
    "owner-add": cmd_owner_add,
}


def finalize(path: Path, original_text: str, lines, dry_run: bool, success_msg: str) -> int:
    new_text = "\n".join(lines)
    if original_text.endswith("\n"):
        new_text += "\n"

    if dry_run:
        diff = difflib.unified_diff(
            original_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (dry-run, 미저장)",
        )
        sys.stdout.writelines(diff)
        print(f"[dry-run] {success_msg}")
        return 0

    path.write_text(new_text, encoding="utf-8")
    violations = lint.lint_text(new_text)
    if violations:
        path.write_text(original_text, encoding="utf-8")
        print("린트 위반 - 파일을 원래대로 되돌림:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(success_msg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--file", default="AIMEM.md", help="대상 AIMEM.md 경로 (기본: AIMEM.md)")
    common.add_argument("--dry-run", action="store_true", help="diff만 출력하고 저장하지 않음")

    parser = argparse.ArgumentParser(prog="aimem_board.py", description="AIMEM.md 표 갱신 CLI (표준 라이브러리만)")
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("rev-bump", parents=[common], help="REV 증가 및 최종 갱신 시각 갱신")
    sp.add_argument("--to", type=int, default=None, help="증가(+1) 대신 이 값으로 설정")
    sp.add_argument("--now", default=None, help='시각 문자열 (예: "2026-08-25 15:30"). 생략 시 시스템 시각 사용')

    sp = sub.add_parser("board-set", parents=[common], help="작업 보드의 상태 칸 갱신")
    sp.add_argument("task_id")
    sp.add_argument("status")

    sp = sub.add_parser("board-add", parents=[common], help="작업 보드에 행 추가")
    sp.add_argument("task_id")
    sp.add_argument("name")
    sp.add_argument("slot")
    sp.add_argument("status")
    sp.add_argument("handoff")
    sp.add_argument("artifact")

    sub.add_parser("queue-pop", parents=[common], help="대기 큐 맨 위 항목을 꺼내 출력하고 제거")

    sp = sub.add_parser("queue-add", parents=[common], help="대기 큐 맨 아래에 항목 추가")
    sp.add_argument("task")
    sp.add_argument("candidate_slot")
    sp.add_argument("handoff")
    sp.add_argument("note")

    sp = sub.add_parser("roster-set", parents=[common], help="세션 명부 행 갱신")
    sp.add_argument("slot")
    sp.add_argument("--session-key", required=True)
    sp.add_argument("--role", default=None)
    sp.add_argument("--note", default=None)
    sp.add_argument("--harness", default=None)

    sp = sub.add_parser("owner-add", parents=[common], help="파일 소유권 표에 행 추가")
    sp.add_argument("path_pattern")
    sp.add_argument("owner_slot")
    sp.add_argument("note")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    path = Path(args.file)
    try:
        original_text = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"오류: 파일을 읽을 수 없음: {e}", file=sys.stderr)
        return 1

    lines = original_text.splitlines()
    func = CMD_FUNCS[args.command]
    try:
        msg = func(args, lines)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 1

    return finalize(path, original_text, lines, args.dry_run, msg)


if __name__ == "__main__":
    sys.exit(main())
