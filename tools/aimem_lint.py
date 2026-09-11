#!/usr/bin/env python3
"""AIMEM.md 구조 불변식 린터. 표준 라이브러리만 사용."""

import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

REV_RE = re.compile(r"\*\*REV:\s*(-?\d+)\*\*")
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{6}$")
SEP_RE = re.compile(r"^\|?[\s\-:|]+\|?$")
VALID_STATUSES = {"TODO", "ASSIGNED", "IN-PROGRESS", "REVIEW", "DONE", "BLOCKED"}
ADMIN_OWNER_LITERALS = {"해당 슬롯", "미배정"}

# 크기 상한 (`5절`). 작업자가 매 턴 전문을 읽으므로 크기는 곧 턴당 비용이다. 총량만 강제한다.
# 상한(거부선)과 롤오버 목표(archive-rollover --keep 10)는 일부러 다르다 - 여유 2건을 띄워
# 롤오버 직후 로그를 한두 건 써도 바로 막히지 않게 한다.
MAX_TOTAL_LINES = 800
MAX_HANDOFF_ENTRIES = 12
# 4절 핸드오프 로그 항목 경계. aimem_board.py 의 archive-rollover 와 **같은 기준**이어야 두
# 도구가 같은 수를 센다. aimem_board 를 import 하지는 않는다(훅이 린터만 단독 실행하므로).
HANDOFF_ENTRY_RE = re.compile(r"^- `(\d{4})-(\d{2})-\d{2}")


@dataclass
class Violation:
    code: str
    line: Optional[int]
    message: str

    def __str__(self) -> str:
        loc = f"line {self.line}" if self.line is not None else "line ?"
        return f"[{self.code}] {loc}: {self.message}"


def _find_section(lines: List[str], number: int) -> Optional[Tuple[int, int]]:
    """0-indexed (start, end) 범위. start 는 '## N.' 헤딩 줄, end 는 다음 '## ' 헤딩 줄(배타)."""
    start = None
    heading_re = re.compile(rf"^##(?!#)\s*{number}\.\s")
    for i, line in enumerate(lines):
        if heading_re.match(line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    next_heading_re = re.compile(r"^##(?!#)\s")
    for i in range(start + 1, len(lines)):
        if next_heading_re.match(lines[i]):
            end = i
            break
    return start, end


def _split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _extract_table(
    lines: List[str], start: int, end: int
) -> Optional[Tuple[List[str], List[Tuple[int, List[str]]]]]:
    """구간 안에서 첫 번째 markdown 표를 찾는다.
    반환: (헤더 셀 목록, [(1-indexed 줄번호, 데이터 셀 목록), ...]). 못 찾으면 None.
    """
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
    header_cells = _split_row(lines[block[0]])
    if not SEP_RE.match(lines[block[1]].strip()):
        return None
    rows = [(i + 1, _split_row(lines[i])) for i in block[2:]]
    return header_cells, rows


def _col_index(header_cells: List[str], name: str) -> Optional[int]:
    for i, cell in enumerate(header_cells):
        if name in cell:
            return i
    return None


def lint_text(text: str) -> List[Violation]:
    """AIMEM.md 본문 문자열을 검사해 위반 목록을 반환한다. 위반이 없으면 빈 리스트."""
    violations: List[Violation] = []
    lines = text.splitlines()

    # 0. 크기 상한 (`5절`) - 총량만 검사한다. 항목당 줄수는 검사하지 않는다.
    total_lines = len(lines)
    if total_lines > MAX_TOTAL_LINES:
        violations.append(Violation(
            "SIZE_TOTAL_LINES", None,
            f"총 {total_lines}줄로 상한 {MAX_TOTAL_LINES}줄을 초과함. 오래된 '4. 핸드오프 로그'를 "
            f"`python3 tools/aimem_board.py archive-rollover --keep 10` 로 아카이브해 줄이십시오",
        ))
    handoff = _find_section(lines, 4)
    if handoff is not None:
        h_start, h_end = handoff
        entry_count = sum(1 for i in range(h_start, h_end) if HANDOFF_ENTRY_RE.match(lines[i]))
        if entry_count > MAX_HANDOFF_ENTRIES:
            violations.append(Violation(
                "SIZE_HANDOFF_LOG", h_start + 1,
                f"'4. 핸드오프 로그' 항목이 {entry_count}건으로 상한 {MAX_HANDOFF_ENTRIES}건을 초과함. "
                f"`python3 tools/aimem_board.py archive-rollover --keep 10` 로 오래된 것부터 아카이브하십시오",
            ))

    # 1. REV 선언 - 정확히 한 번, 양의 정수
    rev_matches = [(i + 1, m.group(1)) for i, line in enumerate(lines) for m in [REV_RE.search(line)] if m]
    if not rev_matches:
        violations.append(Violation("REV_MISSING", None, "최상단 REV 선언(- **REV: N**)을 찾을 수 없음"))
    elif len(rev_matches) > 1:
        line_nos = ", ".join(str(n) for n, _ in rev_matches)
        violations.append(
            Violation("REV_MULTIPLE", rev_matches[0][0], f"REV 선언이 {len(rev_matches)}번 등장함 (줄: {line_nos})")
        )
    else:
        line_no, val = rev_matches[0]
        if not re.match(r"^\d+$", val) or int(val) <= 0:
            violations.append(Violation("REV_INVALID", line_no, f"REV 값이 양의 정수가 아님: {val}"))

    # 2. 세션 명부
    roster_slots: Dict[str, int] = {}
    roster_parsed = False
    section = _find_section(lines, 2)
    if section is None:
        violations.append(Violation("ROSTER_SECTION_MISSING", None, "'2. 세션 명부' 절을 찾을 수 없음"))
    else:
        start, end = section
        table = _extract_table(lines, start, end)
        if table is None:
            violations.append(Violation("ROSTER_TABLE_MISSING", start + 1, "'2. 세션 명부' 절에 표가 없음"))
        else:
            header_cells, rows = table
            slot_idx = _col_index(header_cells, "슬롯")
            token_idx = _col_index(header_cells, "확인토큰")
            if slot_idx is None or token_idx is None:
                violations.append(
                    Violation("ROSTER_HEADER_INVALID", start + 1, f"필요한 열(슬롯/확인토큰)을 찾을 수 없음: {header_cells}")
                )
            else:
                roster_parsed = True
                seen_tokens: Dict[str, int] = {}
                for line_no, cells in rows:
                    if len(cells) <= max(slot_idx, token_idx):
                        violations.append(Violation("ROSTER_ROW_MALFORMED", line_no, f"열 개수가 헤더와 다름: {cells}"))
                        continue
                    slot = cells[slot_idx].strip("` ")
                    token = cells[token_idx].strip("` ")
                    if slot and slot != "-":
                        if slot in roster_slots:
                            violations.append(
                                Violation("ROSTER_DUPLICATE_SLOT", line_no, f"슬롯 ID 중복: {slot} (처음: 줄 {roster_slots[slot]})")
                            )
                        else:
                            roster_slots[slot] = line_no
                    if token and token != "-":
                        if not TOKEN_RE.match(token):
                            violations.append(Violation("ROSTER_TOKEN_INVALID", line_no, f"토큰이 6자리 hex 아님: {token}"))
                        if token in seen_tokens:
                            violations.append(
                                Violation("ROSTER_DUPLICATE_TOKEN", line_no, f"확인토큰 중복: {token} (처음: 줄 {seen_tokens[token]})")
                            )
                        else:
                            seen_tokens[token] = line_no

    # 3. 작업 보드
    section = _find_section(lines, 3)
    if section is None:
        violations.append(Violation("BOARD_SECTION_MISSING", None, "'3. 작업 보드' 절을 찾을 수 없음"))
    else:
        start, end = section
        table = _extract_table(lines, start, end)
        if table is None:
            violations.append(Violation("BOARD_TABLE_MISSING", start + 1, "'3. 작업 보드' 절에 표가 없음"))
        else:
            header_cells, rows = table
            id_idx = _col_index(header_cells, "ID")
            slot_idx = _col_index(header_cells, "담당 슬롯")
            status_idx = _col_index(header_cells, "상태")
            handoff_idx = _col_index(header_cells, "이어받음")
            missing = [
                n
                for n, idx in [("ID", id_idx), ("담당 슬롯", slot_idx), ("상태", status_idx), ("이어받음", handoff_idx)]
                if idx is None
            ]
            if missing:
                violations.append(Violation("BOARD_HEADER_INVALID", start + 1, f"필요한 열을 찾을 수 없음: {missing}"))
            else:
                seen_ids: Dict[str, int] = {}
                task_ids = set()
                dup_ids: set = set()
                status_by_id: Dict[str, str] = {}
                handoff_refs: List[Tuple[int, str, str, str]] = []
                needed = max(id_idx, slot_idx, status_idx, handoff_idx)
                for line_no, cells in rows:
                    if len(cells) <= needed:
                        violations.append(Violation("BOARD_ROW_MALFORMED", line_no, f"열 개수가 헤더와 다름: {cells}"))
                        continue
                    task_id = cells[id_idx].strip("` ")
                    slot = cells[slot_idx].strip("` ")
                    status = cells[status_idx].strip("` ")
                    handoff = cells[handoff_idx].strip("` ")
                    if task_id:
                        task_ids.add(task_id)
                        if task_id in seen_ids:
                            violations.append(
                                Violation("BOARD_DUPLICATE_TASK_ID", line_no, f"태스크 ID 중복: {task_id} (처음: 줄 {seen_ids[task_id]})")
                            )
                            dup_ids.add(task_id)
                        else:
                            seen_ids[task_id] = line_no
                        # 선행 태스크 상태 조회용. 중복 ID 는 위에서 이미 잡으므로 첫 등장분만 남긴다.
                        status_by_id.setdefault(task_id, status)
                    if status not in VALID_STATUSES:
                        violations.append(Violation("BOARD_INVALID_STATUS", line_no, f"상태 값이 허용 목록 밖: {status}"))
                    if slot and slot != "-" and roster_parsed and slot not in roster_slots:
                        violations.append(Violation("BOARD_UNKNOWN_SLOT", line_no, f"담당 슬롯이 명부에 없음: {slot}"))
                    if handoff and handoff != "-":
                        handoff_refs.append((line_no, task_id, status, handoff))
                for line_no, task_id, status, handoff in handoff_refs:
                    if handoff not in task_ids:
                        violations.append(
                            Violation("BOARD_HANDOFF_UNKNOWN_TASK", line_no, f"이어받음이 가리키는 태스크 ID가 보드에 없음: {handoff}")
                        )
                        continue
                    # ID 가 중복인 행은 '자기 자신'/'선행'의 정본이 모호하다. 근본 결함은
                    # BOARD_DUPLICATE_TASK_ID 가 이미 잡으므로, 그 위에 파생 위반을 얹지 않는다.
                    # 중복을 고치고 재실행하면 남은 SELF/NOT_DONE 이 드러난다.
                    if task_id in dup_ids or handoff in dup_ids:
                        continue
                    # 자기 자신을 이어받음으로 가리키면 위반. task_id 가 비어 있지 않으면
                    # task_ids 에 들어가 있으므로 UNKNOWN_TASK 에 걸리지 않고 여기로 온다.
                    if task_id and handoff == task_id:
                        violations.append(
                            Violation("BOARD_HANDOFF_SELF", line_no, f"태스크가 자기 자신을 이어받음으로 가리킴: {task_id}")
                        )
                        continue
                    # 후행이 DONE 인데 선행이 DONE 이 아니면 위반 - 끝나지 않은 일을 이어받아
                    # 끝났다고 적히는 상태를 막는다. 선행이 보드에 있을 때만 검사한다(없으면 위 UNKNOWN).
                    if status == "DONE":
                        pred_status = status_by_id.get(handoff)
                        if pred_status != "DONE":
                            violations.append(
                                Violation(
                                    "BOARD_HANDOFF_NOT_DONE",
                                    line_no,
                                    f"DONE 태스크의 이어받음이 가리키는 선행 태스크가 DONE 이 아님: {handoff} (상태: {pred_status})",
                                )
                            )

    # 6. 파일 소유권
    section = _find_section(lines, 6)
    if section is None:
        violations.append(Violation("OWNERSHIP_SECTION_MISSING", None, "'6. 파일 소유권' 절을 찾을 수 없음"))
    else:
        start, end = section
        table = _extract_table(lines, start, end)
        if table is None:
            violations.append(Violation("OWNERSHIP_TABLE_MISSING", start + 1, "'6. 파일 소유권' 절에 표가 없음"))
        else:
            header_cells, rows = table
            path_idx = _col_index(header_cells, "경로 패턴")
            owner_idx = _col_index(header_cells, "쓰기 소유")
            missing = [n for n, idx in [("경로 패턴", path_idx), ("쓰기 소유", owner_idx)] if idx is None]
            if missing:
                violations.append(Violation("OWNERSHIP_HEADER_INVALID", start + 1, f"필요한 열을 찾을 수 없음: {missing}"))
            else:
                seen_paths: Dict[str, int] = {}
                needed = max(path_idx, owner_idx)
                for line_no, cells in rows:
                    if len(cells) <= needed:
                        violations.append(Violation("OWNERSHIP_ROW_MALFORMED", line_no, f"열 개수가 헤더와 다름: {cells}"))
                        continue
                    path = cells[path_idx].strip("` ")
                    owner = cells[owner_idx].strip("` ")
                    if path:
                        if path in seen_paths:
                            violations.append(
                                Violation("OWNERSHIP_DUPLICATE_PATH", line_no, f"경로 패턴 중복: {path} (처음: 줄 {seen_paths[path]})")
                            )
                        else:
                            seen_paths[path] = line_no
                    if owner and not (
                        owner.startswith("관리자") or owner in ADMIN_OWNER_LITERALS or owner in roster_slots
                    ):
                        violations.append(
                            Violation(
                                "OWNERSHIP_INVALID_OWNER",
                                line_no,
                                f"쓰기 소유가 관리자도 아니고 명부의 슬롯도 아님: {owner}",
                            )
                        )

    return violations


def lint_file(path: str) -> List[Violation]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return lint_text(text)


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: aimem_lint.py <AIMEM.md 경로>", file=sys.stderr)
        return 2
    path = argv[0]
    try:
        violations = lint_file(path)
    except OSError as e:
        print(f"[IO_ERROR] 파일을 읽을 수 없음: {e}", file=sys.stderr)
        return 1
    if not violations:
        print(f"OK: {path} - 위반 없음")
        return 0
    for v in violations:
        print(str(v))
    print(f"위반 {len(violations)}건")
    return 1


if __name__ == "__main__":
    sys.exit(main())
