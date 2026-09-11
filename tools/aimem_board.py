#!/usr/bin/env python3
"""AIMEM.md 표 갱신 CLI. 표준 라이브러리만 사용.

인라인 문자열 치환 대신, 표 구조를 파싱해 셀 단위로 고친다. 쓰기 전에
aimem_lint.lint_text() (순수 함수) 로 검증하고, 위반이 있으면 아무것도 쓰지 않고
exit 1 한다 - 규약을 깨는 갱신을 애초에 저장하지 않는 것이 이 도구의 핵심 가치다.
동시 갱신은 .aimem.lock 에 대한 fcntl.flock 으로 read/modify/write 전체를 직렬화하고,
저장은 os.replace 로 원자적 교체한다(반쪽 파일 노출 방지).
"""

import argparse
import datetime
import difflib
import errno
import fcntl
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import aimem_lint as lint

NEXT_HEADING_RE = re.compile(r"^##(?!#)\s")
# 4절 핸드오프 로그 항목 경계: "- `YYYY-MM-DD ...`" 로 시작하는 줄. 다음 경계 전까지(들여쓴
# 연속 줄 포함)가 한 항목이다. 캡처그룹으로 연/월을 뽑아 아카이브 파일명에 쓴다.
# 단일 출처: aimem_lint 의 상수를 그대로 참조한다. 롤오버(여기)와 린터가 같은 정규식으로
# 세야 "롤오버가 남긴 건수 != 린터가 세는 건수" divergence 가 생기지 않는다. 방향은 board->lint
# 뿐이다(훅이 린터를 단독 실행하므로 lint 는 board 에 의존하면 안 된다).
ENTRY_RE = lint.HANDOFF_ENTRY_RE

# 동시 갱신 상호배제: 셸 flock(1) 과 파이썬 fcntl.flock 은 같은 flock(2) 라
# 같은 .aimem.lock 에 대해 상호 호환된다. 저장소는 ext4 로컬(/dev/sdd)이라 flock 이 동작한다.
LOCK_NAME = ".aimem.lock"
LOCK_TIMEOUT_SEC = 10
# --now 미래값 가드의 시계 오차 허용치
MAX_CLOCK_SKEW = datetime.timedelta(minutes=2)


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
    # 린터 공개 API 를 통해 절을 찾는다(T-024). lint 의 내부 헬퍼를 직접 부르지 않는다 -
    # 파서 재작성(T-021)에서 _find_section 이 사라져 이 도구 전체가 죽었던 회귀의 교훈.
    return lint.find_section(lines, number)


def find_queue_section(lines):
    """'## 4.5 대기 큐' 절. lint.find_section 은 정수 번호만 받으므로 여기서 직접 찾는다."""
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
    """(header_idx, sep_idx, data_idxs) - lint.extract_table 의 블록 탐지 규칙과 동일하게 맞춘다.
    펜스 안 줄은 제외하고, 둘째 줄이 구분선인 블록만 표로 인정한다(T-021 린터 규칙과 일치)."""
    fenced = lint._fenced_mask(lines)
    pipe_lines = [i for i in range(start, end) if not fenced[i] and lines[i].strip().startswith("|")]
    if not pipe_lines:
        return None
    block = [pipe_lines[0]]
    for i in pipe_lines[1:]:
        if i == block[-1] + 1:
            block.append(i)
        else:
            break
    if len(block) < 2 or not lint.SEP_RE.match(lines[block[1]].strip()):
        return None
    return block[0], block[1], block[2:]


def replace_row_cells(lines, start, end, key_col, key_val, updates):
    table = lint.extract_table(lines, start, end)
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
    table = lint.extract_table(lines, start, end)
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
    now_str = _resolve_now(args.now)
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
    table = lint.extract_table(lines, start, end)
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
    table = lint.extract_table(lines, start, end)
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


def cmd_archive_rollover(args, lines):
    if args.keep < 0:
        die("--keep 는 0 이상이어야 함")
    section = find_section(lines, 4)
    if section is None:
        die("'4. 핸드오프 로그' 절을 찾을 수 없음")
    start, end = section
    starts = [i for i in range(start, end) if ENTRY_RE.match(lines[i])]
    total = len(starts)
    if total <= args.keep:
        args._archive_plan = []
        return f"archive-rollover: 항목 {total}건 (상한 keep={args.keep} 이하) - 롤오버 없음"

    # 최신 keep 건은 맨 위(시간 역순)이므로 그 아래 전부를 잘라낸다. 항목 끝의 구분선/빈 줄
    # (--- 등)은 절 구조 유지를 위해 파일에 남긴다.
    cut_start = starts[args.keep]
    cut_end = end
    while cut_end > cut_start and lines[cut_end - 1].strip() in ("", "---"):
        cut_end -= 1
    archived = lines[cut_start:cut_end]
    del lines[cut_start:cut_end]

    plan = _plan_archive(archived, Path(args.file))
    args._archive_plan = plan
    moved = total - args.keep
    dest = ", ".join(f"handoff-{m}.md({cnt}건)" for m, _p, _t, cnt in plan)
    return f"archive-rollover: {moved}건 아카이브({dest}), 최신 {args.keep}건 유지"


def cmd_handoff_add(args, lines):
    body = args.text if args.text is not None else sys.stdin.read()
    body = body.rstrip("\n")
    if not body.strip():
        die("본문이 비어 있음 - --text 또는 표준입력으로 본문을 주십시오")

    section = find_section(lines, 4)
    if section is None:
        die("'4. 핸드오프 로그' 절을 찾을 수 없음")
    start, end = section
    entry_starts = [i for i in range(start, end) if ENTRY_RE.match(lines[i])]

    # 삽입 전에 상한 초과를 선제 거부한다. 린터(T-011)가 12건 초과를 위반으로 막으므로 그냥
    # 삽입하면 finalize 의 린트에서 쓰기가 거부된다. 여기서 먼저 멈추고 archive-rollover 를
    # 안내하는 편이 더 명확하다. 자동 롤오버는 하지 않는다(파괴적 동작 결합 금지).
    if len(entry_starts) + 1 > lint.MAX_HANDOFF_ENTRIES:
        die(
            f"현재 {len(entry_starts)}건으로 한 건 더하면 {len(entry_starts) + 1}건 - 상한 "
            f"{lint.MAX_HANDOFF_ENTRIES}건 초과라 린터가 거부합니다. 먼저 "
            f"`python3 tools/aimem_board.py archive-rollover --keep 10` 로 롤오버한 뒤 다시 추가하십시오"
        )

    # 시각은 도구가 직접 읽어 박는다. 사람이 넘길 수 없다 - 옮겨 적는 실수를 원천 차단.
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    body_lines = body.split("\n")
    entry = [f"- `{ts}` 관리자: {body_lines[0]}"]
    for bl in body_lines[1:]:
        entry.append(f"  {bl}" if bl.strip() else "")

    if entry_starts:
        insert_at = entry_starts[0]
    else:
        # 항목이 없으면 헤더/안내문 다음에 넣는다(안내문 뒤 빈 줄들을 건너뜀).
        insert_at = start + 1
        while insert_at < end and lines[insert_at].strip() != "":
            insert_at += 1
        while insert_at < end and lines[insert_at].strip() == "":
            insert_at += 1
    lines[insert_at:insert_at] = entry

    new_count = len(entry_starts) + 1
    note = " (상한 도달 - 다음 추가 전 롤오버 권장)" if new_count == lint.MAX_HANDOFF_ENTRIES else ""
    return f"handoff-add: `{ts}` 관리자 항목 1건 추가 (총 {new_count}건){note}"


CMD_FUNCS = {
    "rev-bump": cmd_rev_bump,
    "handoff-add": cmd_handoff_add,
    "archive-rollover": cmd_archive_rollover,
    "board-set": cmd_board_set,
    "board-add": cmd_board_add,
    "queue-pop": cmd_queue_pop,
    "queue-add": cmd_queue_add,
    "roster-set": cmd_roster_set,
    "owner-add": cmd_owner_add,
}


def _resolve_now(raw_now):
    """--now 문자열을 파싱해 "YYYY-MM-DD HH:MM KST" 로 정규화. 미래 시각·형식 오류는 거부.

    기존 구현은 endswith("KST") 만 봐서 아무 문자열이나 통과했고, 미래 시각도 막지 못했다.
    """
    if not raw_now:
        return f"{datetime.datetime.now():%Y-%m-%d %H:%M} KST"
    raw = re.sub(r"\s*KST$", "", raw_now.strip()).strip()
    try:
        given = datetime.datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        die(f'--now 형식이 잘못됨: {raw_now!r} ("YYYY-MM-DD HH:MM" 여야 함)')
    now = datetime.datetime.now()
    if given > now + MAX_CLOCK_SKEW:
        die(f"--now 가 미래 시각임: {given:%Y-%m-%d %H:%M} > 현재 {now:%Y-%m-%d %H:%M}")
    return f"{given:%Y-%m-%d %H:%M} KST"


def _acquire(lock_path: Path) -> int:
    """LOCK_EX 를 비블로킹으로 시도하다 타임아웃 시 실패. 락파일은 절대 unlink 하지 않는다.

    O_EXCL(프로세스 사망 시 영구 교착)도 mtime 재확인(TOCTOU)도 아닌 fcntl.flock 을 쓴다 -
    커널이 fd 수명으로 관리해 프로세스가 죽으면 자동 해제된다. CLI 는 짧게 살고 호출자가
    재시도할 수 있으므로 무한 대기보다 "빨리 실패"가 낫다.
    """
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o664)
    deadline = time.monotonic() + LOCK_TIMEOUT_SEC
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError as e:
            if e.errno not in (errno.EACCES, errno.EAGAIN):
                os.close(fd)
                raise
            if time.monotonic() >= deadline:
                os.close(fd)
                die(f"{LOCK_TIMEOUT_SEC}초 안에 락을 얻지 못함: {lock_path} (다른 갱신이 진행 중)")
            time.sleep(0.1)


def _atomic_write(path: Path, text: str) -> None:
    """같은 디렉터리에 임시 파일을 쓰고 os.replace 로 원자적 교체. 반쪽 파일 노출을 막는다.

    mkstemp 는 0600 이므로 원본 권한을 보존한다(빠뜨리면 조용히 권한이 좁아진다).
    """
    parent = path.parent if str(path.parent) else Path(".")
    fd, tmp = tempfile.mkstemp(dir=str(parent), prefix=".aimem.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            orig_mode = os.stat(path).st_mode & 0o777
        except OSError:
            orig_mode = 0o664
        os.chmod(tmp, orig_mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _archive_dir_for(path: Path) -> Path:
    parent = path.parent if str(path.parent) else Path(".")
    return parent / ".aimem" / "archive"


def _plan_archive(archived_lines, path: Path):
    """잘린 줄들을 항목의 연-월 기준으로 묶어 [(월, 아카이브경로, 본문, 항목수)] 로 만든다.

    잘린 순서(4절의 원래 순서)를 그대로 보존한다. 여러 달이 섞이면 달마다 나눠 넣는다.
    """
    groups = []          # [(월, [줄], 항목수)]
    pos_of = {}          # 월 -> groups 내 위치
    cur = None
    for line in archived_lines:
        m = ENTRY_RE.match(line)
        if m:
            cur = f"{m.group(1)}-{m.group(2)}"
            if cur not in pos_of:
                pos_of[cur] = len(groups)
                groups.append((cur, [], 0))
        if cur is None:
            die("아카이브 대상의 첫 줄이 항목 시작이 아님 - 경계 파싱 오류")
        month, buf, cnt = groups[pos_of[cur]]
        buf.append(line)
        groups[pos_of[cur]] = (month, buf, cnt + (1 if m else 0))

    adir = _archive_dir_for(path)
    return [(month, adir / f"handoff-{month}.md", "\n".join(buf), cnt) for month, buf, cnt in groups]


def _append_archive(apath: Path, text: str) -> None:
    """아카이브 파일에 덧붙인다. 기존 내용은 덮어쓰지 않고, 없으면 만든다. 권한 0664."""
    apath.parent.mkdir(parents=True, exist_ok=True)
    block = text if text.endswith("\n") else text + "\n"
    if apath.exists() and apath.stat().st_size > 0:
        existing = apath.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            block = "\n" + block
    with open(apath, "a", encoding="utf-8") as f:
        f.write(block)
    os.chmod(apath, 0o664)


def finalize(path: Path, original_text: str, lines, dry_run: bool, success_msg: str, archive_plan=None) -> int:
    new_text = "\n".join(lines)
    if original_text.endswith("\n"):
        new_text += "\n"

    # 쓰기 전에 검증한다. lint_text 는 순수 함수이므로 통과하면 한 번만 쓰면 되고,
    # 위반이면 아무것도 쓰지 않는다 - "위반 시 롤백이 남의 편집을 날린다" 결함이 원인째 사라진다.
    violations = lint.lint_text(new_text)
    if violations:
        print("린트 위반 - 저장하지 않음:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    if dry_run:
        diff = difflib.unified_diff(
            original_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (dry-run, 미저장)",
        )
        sys.stdout.writelines(diff)
        for _month, apath, _text, cnt in (archive_plan or []):
            print(f"[dry-run] 아카이브 append -> {apath} ({cnt}건)")
        print(f"[dry-run] {success_msg}")
        return 0

    # 아카이브를 먼저 덧붙이고(실패 시 AIMEM.md 무변경 -> 깨끗한 재시도), 그 다음 AIMEM.md 를
    # 원자적으로 교체한다. 린트는 이미 통과한 상태다. 아카이브 append 와 AIMEM.md 쓰기 모두
    # main() 의 flock 안에서 일어난다.
    for _month, apath, text, _cnt in (archive_plan or []):
        _append_archive(apath, text)
    _atomic_write(path, new_text)
    print(success_msg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--file", default="AIMEM.md", help="대상 AIMEM.md 경로 (기본: AIMEM.md)")
    common.add_argument("--dry-run", action="store_true", help="diff만 출력하고 저장하지 않음")
    common.add_argument(
        "--expect-rev",
        type=int,
        default=None,
        help="락 안에서 읽은 현재 REV 가 이 값이 아니면 거부 (낙관적 동시성 - sed 우회 경로 안전망)",
    )

    parser = argparse.ArgumentParser(prog="aimem_board.py", description="AIMEM.md 표 갱신 CLI (표준 라이브러리만)")
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("rev-bump", parents=[common], help="REV 증가 및 최종 갱신 시각 갱신")
    sp.add_argument("--to", type=int, default=None, help="증가(+1) 대신 이 값으로 설정")
    sp.add_argument("--now", default=None, help='시각 문자열 (예: "2026-08-25 15:30"). 생략 시 시스템 시각 사용')

    sp = sub.add_parser(
        "handoff-add",
        parents=[common],
        help="4절 핸드오프 로그 맨 위에 항목 추가. 시각은 도구가 직접 박음(사람이 못 넘김)",
    )
    sp.add_argument("--text", default=None, help="항목 본문. 생략 시 표준입력에서 읽음. 여러 줄이면 이어지는 줄은 2칸 들여씀")

    sp = sub.add_parser(
        "archive-rollover",
        parents=[common],
        help="4절 핸드오프 로그가 상한을 넘으면 오래된 것부터 월별 아카이브(.aimem/archive/handoff-YYYY-MM.md)로 롤오버",
    )
    sp.add_argument("--keep", type=int, default=10, help="4절에 남길 최신 항목 수 (기본 10)")

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

    # read/modify/write 전체를 한 락 안에서 직렬화한다. finalize() 안에만 걸면
    # read -> (남이 쓴다) -> write 구간이 열려 lost update 가 남는다. --dry-run 도 락 안에서
    # 돌려야 낡은 내용을 진단하지 않는다.
    lock_dir = path.parent if str(path.parent) else Path(".")
    lock_fd = _acquire(lock_dir / LOCK_NAME)
    try:
        try:
            original_text = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"오류: 파일을 읽을 수 없음: {e}", file=sys.stderr)
            return 1

        lines = original_text.splitlines()

        if args.expect_rev is not None:
            m = lint.REV_RE.search(original_text)
            if m is None:
                print("오류: REV 선언을 찾을 수 없어 --expect-rev 를 대조할 수 없음", file=sys.stderr)
                return 1
            cur_rev = int(m.group(1))
            if cur_rev != args.expect_rev:
                print(
                    f"오류: REV 불일치 - 예상 {args.expect_rev}, 실제 {cur_rev} (다시 읽고 재시도할 것)",
                    file=sys.stderr,
                )
                return 1

        func = CMD_FUNCS[args.command]
        try:
            msg = func(args, lines)
        except SystemExit as e:
            return int(e.code) if e.code is not None else 1

        return finalize(path, original_text, lines, args.dry_run, msg, getattr(args, "_archive_plan", None))
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
