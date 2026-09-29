#!/usr/bin/env python3
"""AIMEM.md 구조 불변식 린터. 표준 라이브러리만 사용.

검사하는 불변식은 위반 코드 기준 37건이다
(크기 2 + REV 3 + 구조 3 + 2절 명부 9 + 3절 보드 11 + 6절 소유권 9).

T-021(REV 71)에서 S3 의 적대적 감사(T-020) 발견을 막기 위해 파서 계층과 의미 계층을
강화했다. 자세한 설계 판단·못 막는 것은 `.aimem/outbox/S1.md` [T-021] 참조.
"""

import functools
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

REV_RE = re.compile(r"\*\*REV:\s*(-?\d+)\*\*")
# 4절 로그 항목이 선언하는 REV. 헤더 `**REV: N**`(콜론)과 달리 로그는 `**REV N.`(공백)로 적는
# 관례다. 이 관례가 실제로 쓰인 문서에서만 헤더-로그 동기(REV_LOG_MISSING)를 강제한다 - 관례가
# 없는 문서(REV 표기 없는 로그)에서는 어떤 항목이 헤더 REV 에 대응하는지 식별할 수 없어 오탐이 된다.
LOG_REV_RE = re.compile(r"\*\*REV\s+(\d+)")
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{6}$")
SEP_RE = re.compile(r"^\|?[\s\-:|]+\|?$")
VALID_STATUSES = {"TODO", "ASSIGNED", "IN-PROGRESS", "REVIEW", "DONE", "BLOCKED"}
ADMIN_OWNER_LITERALS = {"해당 슬롯", "미배정"}

# 의미 계층 (T-021). 린터는 "누가 진짜 관리자인가"를 알 수 없다. 아래는 그 권위를
# **검사 가능한 형태로 번역**한 것이다 - 근거와 한계는 outbox [T-021] 에 적었다.
#
# 관리자 세션키를 린터 소스(보호 아티팩트, S1 소유)에 못박는다. 공격자가 쓰기 가능한
# AIMEM.md 안의 관리자 선언을 다른 세션키로 바꿔치기하면(F1) 여기 값과 어긋나 잡힌다.
# 신뢰의 뿌리를 쓰기 가능한 파일에서 코드로 옮기는 것이 요점. 관리자 키가 정당하게
# 바뀌면 이 상수도 함께 고쳐야 한다(6.1 자기구속과 같은 성격).
MANAGER_SESSION_KEY = "agent:coding:discord:channel:1541705515908988989"
MANAGER_DECL_RE = re.compile(r"관리자\(단독 쓰기 권한\)")

# 권위를 주는 파일. 소유가 슬롯으로 넘어가면 "한 번 쓸 수 있는 자가 권한을 영구히
# 넓히는"(F2) 공격이다. 이들의 소유는 반드시 관리자여야 한다.
PROTECTED_PATHS = {"AIMEM.md", "CLAUDE.md", "AGENTS.md"}

# 크기 상한 (`5절`). 작업자가 매 턴 전문을 읽으므로 크기는 곧 턴당 비용이다. 총량만 강제한다.
# 상한(거부선)과 롤오버 목표(archive-rollover --keep 10)는 일부러 다르다 - 여유 2건을 띄워
# 롤오버 직후 로그를 한두 건 써도 바로 막히지 않게 한다.
MAX_TOTAL_LINES = 800
MAX_HANDOFF_ENTRIES = 12
# 4절 항목 **하나**의 문자 수 상한. 항목 수(MAX_HANDOFF_ENTRIES)와 총줄수(MAX_TOTAL_LINES)를
# 둘 다 지켜도 한 항목이 통째로 부풀면 문서가 커진다 - REV 103 항목이 1줄 3,277자로 둘 다
# 통과했다. 규약의 "6줄 이내 권고"는 줄 수라서 이걸 못 막는다. 그래서 문자로 잰다.
MAX_LOG_ENTRY_CHARS = 1200
# 4절 핸드오프 로그 항목 경계. aimem_board.py 의 archive-rollover 와 **같은 기준**이어야 두
# 도구가 같은 수를 센다. aimem_board 를 import 하지는 않는다(훅이 린터만 단독 실행하므로).
HANDOFF_ENTRY_RE = re.compile(r"^- `(\d{4})-(\d{2})-\d{2}")

# 절 헤딩. `## N.` (세 번째 # 이 아님). 절 종료 판정에도 쓴다.
SECTION_HEAD_RE = re.compile(r"^##(?!#)\s")


@dataclass
class Violation:
    code: str
    line: Optional[int]
    message: str

    def __str__(self) -> str:
        loc = f"line {self.line}" if self.line is not None else "line ?"
        return f"[{self.code}] {loc}: {self.message}"


def _fenced_mask(lines: List[str]) -> List[bool]:
    """코드펜스(``` 또는 ~~~) 안/경계 줄을 True 로 표시한다.

    파서 은닉 공격(F5/F5b)의 뿌리: 펜스 안의 `## 3.` 이나 표를 린터가 실제 절/표로
    오인했다. 펜스 줄은 절 헤딩·표 어느 판정에서도 제외한다. 델리미터 줄 자체도 True.
    """
    mask = [False] * len(lines)
    in_fence = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            mask[i] = True
            in_fence = not in_fence
            continue
        mask[i] = in_fence
    return mask


def _split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _col_index(header_cells: List[str], name: str) -> Optional[int]:
    """헤더에서 열 위치를 찾는다. **정확 일치**만 인정한다.

    이전에는 부분일치(`name in cell`)라, `상태` 앞에 `상태요약` 열을 끼우면 status 검사가
    가짜 열을 가리켰다(F7). 정확 일치로 이 바꿔치기를 막는다.
    """
    for i, cell in enumerate(header_cells):
        if cell == name:
            return i
    return None


def _section_spans(lines: List[str], fenced: List[bool], number: int) -> List[Tuple[int, int]]:
    """절 번호 `number` 의 **모든** (start, end) 구간을 0-indexed 로 반환한다.

    - 펜스 안 헤딩은 무시한다(F5b).
    - 여러 번 등장하면 전부 반환한다 - 호출부가 중복을 위반으로 잡고, 모든 구간을
      검사해 뒤 절 은닉(F6)을 막는다.
    end 는 다음 (펜스 밖) `## ` 헤딩 줄(배타) 또는 파일 끝.
    """
    head_re = re.compile(rf"^##(?!#)\s*{number}\.\s")
    starts = [i for i, line in enumerate(lines) if not fenced[i] and head_re.match(line)]
    spans = []
    for s in starts:
        end = len(lines)
        for j in range(s + 1, len(lines)):
            if not fenced[j] and SECTION_HEAD_RE.match(lines[j]):
                end = j
                break
        spans.append((s, end))
    return spans


def _extract_tables(
    lines: List[str], start: int, end: int, fenced: List[bool]
) -> List[Tuple[List[str], List[Tuple[int, List[str]]]]]:
    """구간 [start, end) 안의 **모든** markdown 표를 반환한다.

    각 표: (헤더 셀, [(1-indexed 줄번호, 데이터 셀), ...]).
    - 펜스 줄은 건너뛴다.
    - '표'는 파이프로 시작하는 연속 줄 블록 중 **둘째 줄이 구분선**인 것만 인정한다.
      구분선이 없는 고립 파이프 산문(F10)은 표가 아니므로 건너뛰되 오류로 삼지 않는다.
    - 여러 표를 전부 반환하므로, 빈 디코이 표를 위에 얹어 진짜 표를 숨기는 F4 가 막힌다.
    """
    tables: List[Tuple[List[str], List[Tuple[int, List[str]]]]] = []
    i = start
    while i < end:
        if fenced[i] or not lines[i].strip().startswith("|"):
            i += 1
            continue
        block = []
        j = i
        while j < end and not fenced[j] and lines[j].strip().startswith("|"):
            block.append(j)
            j += 1
        if len(block) >= 2 and SEP_RE.match(lines[block[1]].strip()):
            header_cells = _split_row(lines[block[0]])
            rows = [(k + 1, _split_row(lines[k])) for k in block[2:]]
            tables.append((header_cells, rows))
        i = j if j > i else i + 1
    return tables


def find_section(lines: List[str], number: int) -> Optional[Tuple[int, int]]:
    """호환 공개 API: 절 `number` 의 **첫** 구간 (start, end) 0-indexed, 없으면 None.

    aimem_board.py 등 외부 도구가 절을 찾을 때 쓴다. 내부 `_section_spans`(펜스 인식)
    위에 얹으므로 **린터와 board 가 같은 기준으로 절을 찾는다**(T-024). 절이 여러 번
    등장하면 첫 구간을 준다 - 정본은 첫 절이고, 린터가 중복 자체는 DUPLICATE_SECTION 으로 잡는다.
    """
    spans = _section_spans(lines, _fenced_mask(lines), number)
    return spans[0] if spans else None


def extract_table(lines: List[str], start: int, end: int) -> Optional[Tuple[List[str], List[Tuple[int, List[str]]]]]:
    """호환 공개 API: 구간 [start, end) 의 **첫** 표 (header_cells, rows) 또는 None.

    `_extract_tables`(펜스 인식, 구분선 필수) 위에 얹는다. 린터와 board 가 같은 표를 본다(T-024).
    """
    tables = _extract_tables(lines, start, end, _fenced_mask(lines))
    return tables[0] if tables else None


def _glob_regex(pat: str) -> "re.Pattern":
    """소유권 경로 패턴을 정규식으로. `**`→ 임의(슬래시 포함), `*`→ 한 세그먼트."""
    out = ["^"]
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if i + 1 < n and pat[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        out.append(re.escape(c))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def _covers(pattern: str, path: str) -> bool:
    """pattern 이 path 를 포함하는가(글롭 매칭)."""
    return bool(_glob_regex(pattern).match(path))


def _more_specific(sub: str, sup: str) -> bool:
    """sub 이 sup 보다 **엄격히 더 구체적**인가 (sup 이 sub 을 덮지만 그 역은 아님).

    계층 소유(T-025 FP1): `tools/**`(관리자) 위에 `tools/aimem_lint.py`(S1) 예외를 두는 것은
    소유권 표의 자연스러운 방식이다. 더 구체적인 경로가 캐치올을 이긴다(most-specific-wins)
    - 이 경우는 충돌이 아니다. 충돌은 '같은 구체성에서 소유자가 갈릴 때'만이다.
    """
    return _covers(sup, sub) and not _covers(sub, sup)


def _seg_overlap(x: str, y: str) -> bool:
    """단일 경로 세그먼트 글롭 두 개가 공통 문자열을 갖는가. `*` 는 세그먼트 내 `[^/]*`."""
    @functools.lru_cache(maxsize=None)
    def go(i: int, j: int) -> bool:
        if i == len(x) and j == len(y):
            return True
        if i < len(x) and x[i] == "*":
            return go(i + 1, j) or (j < len(y) and go(i, j + 1))
        if j < len(y) and y[j] == "*":
            return go(i, j + 1) or (i < len(x) and go(i + 1, j))
        if i < len(x) and j < len(y) and x[i] == y[j]:
            return go(i + 1, j + 1)
        return False

    return go(0, 0)


def _intersects(a: str, b: str) -> bool:
    """두 경로 글롭이 공통 경로를 가질 수 있는가. `**` 는 0개 이상의 세그먼트, `*` 는 한 세그먼트.

    포함관계가 없는데도 겹치는 경우(예: `tools/*.py` 와 `tools/aimem_*` 가 `tools/aimem_x.py` 에서
    겹침)를 잡는다 - 이것이 '같은 구체성 충돌'이다(T-025).
    """
    A = a.split("/")
    B = b.split("/")

    @functools.lru_cache(maxsize=None)
    def go(i: int, j: int) -> bool:
        if i == len(A) and j == len(B):
            return True
        if i < len(A) and A[i] == "**":
            return go(i + 1, j) or (j < len(B) and go(i, j + 1))
        if j < len(B) and B[j] == "**":
            return go(i, j + 1) or (i < len(A) and go(i + 1, j))
        if i < len(A) and j < len(B) and _seg_overlap(A[i], B[j]):
            return go(i + 1, j + 1)
        return False

    return go(0, 0)


def _governed_tables(tables, required):
    """절 안의 표 중 **필요한 열을 모두 가진** 표만 고른다(T-025 FP2/FP3).

    범례·이력 같은 설명용 둘째 표는 필요한 열이 없어 자연히 제외된다 - 검사 대상은
    그 절의 '진짜 표'(필요 열을 가진 표)뿐이다. 디코이 은닉(F4)은 진짜 표와 **같은 헤더**를
    써야 검사 대상이 되므로, 같은 헤더 표가 2개 이상이면 여전히 MULTIPLE_TABLE 로 잡는다.
    """
    return [t for t in tables if all(_col_index(t[0], c) is not None for c in required)]


def _first_heading_index(lines: List[str], fenced: List[bool]) -> int:
    for i, line in enumerate(lines):
        if not fenced[i] and SECTION_HEAD_RE.match(line):
            return i
    return len(lines)


def _check_roster(
    lines: List[str], fenced: List[bool], violations: List[Violation]
) -> Tuple[Dict[str, int], bool]:
    """2절 세션 명부. 반환: (roster_slots, parsed 여부)."""
    roster_slots: Dict[str, int] = {}
    spans = _section_spans(lines, fenced, 2)
    if not spans:
        violations.append(Violation("ROSTER_SECTION_MISSING", None, "'2. 세션 명부' 절을 찾을 수 없음"))
        return roster_slots, False
    tables: List[Tuple[List[str], List[Tuple[int, List[str]]]]] = []
    for s, e in spans:
        tables.extend(_extract_tables(lines, s, e, fenced))
    governed = _governed_tables(tables, ("슬롯", "확인토큰"))
    if not governed:
        violations.append(Violation("ROSTER_TABLE_MISSING", spans[0][0] + 1, "'2. 세션 명부' 절에 (슬롯·확인토큰 열을 가진) 표가 없음"))
        return roster_slots, False
    if len(governed) > 1:
        violations.append(
            Violation("ROSTER_MULTIPLE_TABLE", spans[0][0] + 1, f"'2. 세션 명부' 절에 명부 표가 {len(governed)}개 - 디코이 표로 진짜 명부를 가릴 수 있음")
        )
    parsed = False
    seen_tokens: Dict[str, int] = {}
    seen_keys: Dict[str, int] = {}
    for header_cells, rows in governed:
        slot_idx = _col_index(header_cells, "슬롯")
        token_idx = _col_index(header_cells, "확인토큰")
        key_idx = _col_index(header_cells, "세션키")
        if slot_idx is None or token_idx is None:
            violations.append(
                Violation("ROSTER_HEADER_INVALID", None, f"필요한 열(슬롯/확인토큰)을 찾을 수 없음: {header_cells}")
            )
            continue
        parsed = True
        need = max(slot_idx, token_idx, key_idx if key_idx is not None else 0)
        for line_no, cells in rows:
            if len(cells) <= need:
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
            if key_idx is not None:
                key = cells[key_idx].strip("` ")
                if key and key != "-":
                    if key in seen_keys:
                        violations.append(
                            Violation(
                                "ROSTER_DUPLICATE_SESSION_KEY",
                                line_no,
                                f"세션키가 여러 슬롯에 중복: {key} (처음: 줄 {seen_keys[key]}) - '세션키가 유일한 안정 식별자'(2절) 전제 붕괴",
                            )
                        )
                    else:
                        seen_keys[key] = line_no
    return roster_slots, parsed


def _check_board(
    lines: List[str], fenced: List[bool], roster_slots: Dict[str, int], roster_parsed: bool, violations: List[Violation]
) -> None:
    """3절 작업 보드."""
    spans = _section_spans(lines, fenced, 3)
    if not spans:
        violations.append(Violation("BOARD_SECTION_MISSING", None, "'3. 작업 보드' 절을 찾을 수 없음"))
        return
    tables: List[Tuple[List[str], List[Tuple[int, List[str]]]]] = []
    for s, e in spans:
        tables.extend(_extract_tables(lines, s, e, fenced))
    governed = _governed_tables(tables, ("ID", "담당 슬롯", "상태", "이어받음"))
    if not governed:
        violations.append(Violation("BOARD_TABLE_MISSING", spans[0][0] + 1, "'3. 작업 보드' 절에 (ID·담당 슬롯·상태·이어받음 열을 가진) 표가 없음"))
        return
    if len(governed) > 1:
        violations.append(
            Violation("BOARD_MULTIPLE_TABLE", spans[0][0] + 1, f"'3. 작업 보드' 절에 보드 표가 {len(governed)}개 - 디코이 표로 진짜 보드를 가릴 수 있음")
        )

    # 모든 보드 표의 행을 하나로 모아, 기존 교차행 로직(중복/자기참조/미완료 선행)을 한 번 돈다.
    normalized: List[Tuple[int, str, str, str, str]] = []
    for header_cells, rows in governed:
        id_idx = _col_index(header_cells, "ID")
        slot_idx = _col_index(header_cells, "담당 슬롯")
        status_idx = _col_index(header_cells, "상태")
        handoff_idx = _col_index(header_cells, "이어받음")
        missing = [
            n for n, idx in [("ID", id_idx), ("담당 슬롯", slot_idx), ("상태", status_idx), ("이어받음", handoff_idx)] if idx is None
        ]
        if missing:
            violations.append(Violation("BOARD_HEADER_INVALID", None, f"필요한 열을 찾을 수 없음: {missing}"))
            continue
        need = max(id_idx, slot_idx, status_idx, handoff_idx)
        for line_no, cells in rows:
            if len(cells) <= need:
                violations.append(Violation("BOARD_ROW_MALFORMED", line_no, f"열 개수가 헤더와 다름: {cells}"))
                continue
            normalized.append(
                (
                    line_no,
                    cells[id_idx].strip("` "),
                    cells[slot_idx].strip("` "),
                    cells[status_idx].strip("` "),
                    cells[handoff_idx].strip("` "),
                )
            )

    seen_ids: Dict[str, int] = {}
    task_ids: set = set()
    dup_ids: set = set()
    status_by_id: Dict[str, str] = {}
    handoff_refs: List[Tuple[int, str, str, str]] = []
    for line_no, task_id, slot, status, handoff in normalized:
        if task_id:
            task_ids.add(task_id)
            if task_id in seen_ids:
                violations.append(
                    Violation("BOARD_DUPLICATE_TASK_ID", line_no, f"태스크 ID 중복: {task_id} (처음: 줄 {seen_ids[task_id]})")
                )
                dup_ids.add(task_id)
            else:
                seen_ids[task_id] = line_no
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
        # 중복 ID 행은 '자기 자신'/'선행'의 정본이 모호하다. 근본 결함(DUPLICATE)만 남기고
        # 파생 위반을 얹지 않는다. 중복을 고쳐 재실행하면 남은 SELF/NOT_DONE 이 드러난다.
        if task_id in dup_ids or handoff in dup_ids:
            continue
        if task_id and handoff == task_id:
            violations.append(
                Violation("BOARD_HANDOFF_SELF", line_no, f"태스크가 자기 자신을 이어받음으로 가리킴: {task_id}")
            )
            continue
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


def _check_ownership(
    lines: List[str], fenced: List[bool], roster_slots: Dict[str, int], violations: List[Violation]
) -> None:
    """6절 파일 소유권."""
    spans = _section_spans(lines, fenced, 6)
    if not spans:
        violations.append(Violation("OWNERSHIP_SECTION_MISSING", None, "'6. 파일 소유권' 절을 찾을 수 없음"))
        return
    tables: List[Tuple[List[str], List[Tuple[int, List[str]]]]] = []
    for s, e in spans:
        tables.extend(_extract_tables(lines, s, e, fenced))
    governed = _governed_tables(tables, ("경로 패턴", "쓰기 소유"))
    if not governed:
        violations.append(Violation("OWNERSHIP_TABLE_MISSING", spans[0][0] + 1, "'6. 파일 소유권' 절에 (경로 패턴·쓰기 소유 열을 가진) 표가 없음"))
        return
    if len(governed) > 1:
        violations.append(
            Violation("OWNERSHIP_MULTIPLE_TABLE", spans[0][0] + 1, f"'6. 파일 소유권' 절에 소유권 표가 {len(governed)}개 - 디코이 표로 진짜 소유권을 가릴 수 있음")
        )

    seen_paths: Dict[str, int] = {}
    own_rows: List[Tuple[str, str, int]] = []  # (path, owner, line_no)
    for header_cells, rows in governed:
        path_idx = _col_index(header_cells, "경로 패턴")
        owner_idx = _col_index(header_cells, "쓰기 소유")
        missing = [n for n, idx in [("경로 패턴", path_idx), ("쓰기 소유", owner_idx)] if idx is None]
        if missing:
            violations.append(Violation("OWNERSHIP_HEADER_INVALID", None, f"필요한 열을 찾을 수 없음: {missing}"))
            continue
        need = max(path_idx, owner_idx)
        for line_no, cells in rows:
            if len(cells) <= need:
                violations.append(Violation("OWNERSHIP_ROW_MALFORMED", line_no, f"열 개수가 헤더와 다름: {cells}"))
                continue
            path = cells[path_idx].strip("` ")
            owner = cells[owner_idx].strip("` ")
            own_rows.append((path, owner, line_no))
            if path:
                if path in seen_paths:
                    violations.append(
                        Violation("OWNERSHIP_DUPLICATE_PATH", line_no, f"경로 패턴 중복: {path} (처음: 줄 {seen_paths[path]})")
                    )
                else:
                    seen_paths[path] = line_no
            if owner and not (owner.startswith("관리자") or owner in ADMIN_OWNER_LITERALS or owner in roster_slots):
                violations.append(
                    Violation("OWNERSHIP_INVALID_OWNER", line_no, f"쓰기 소유가 관리자도 아니고 명부의 슬롯도 아님: {owner}")
                )
            # F2: 권위를 주는 보호 파일의 소유는 반드시 관리자여야 한다.
            if path in PROTECTED_PATHS and owner and not owner.startswith("관리자"):
                violations.append(
                    Violation(
                        "OWNERSHIP_PROTECTED_OWNER",
                        line_no,
                        f"보호 경로 '{path}' 의 소유가 관리자가 아님: {owner} - 쓰기 권한의 뿌리를 넘기는 권한 확대",
                    )
                )

    # F3 + T-025 FP1: 글롭 겹침. **most-specific-wins** - 한쪽이 다른쪽을 엄격히 포함하면
    # 더 구체적인 경로가 캐치올을 이기는 정당한 계층 소유이므로 넘어간다. 진짜 충돌은
    # 두 경로가 겹치는데 **어느 쪽도 더 구체적이지 않을**(같은 구체성) 때뿐이다.
    for a in range(len(own_rows)):
        pa, oa, la = own_rows[a]
        for b in range(a + 1, len(own_rows)):
            pb, ob, lb = own_rows[b]
            if not pa or not pb or pa == pb or oa == ob:
                continue
            if _more_specific(pa, pb) or _more_specific(pb, pa):
                continue  # 계층 소유: 더 구체적인 쪽이 이긴다 - 충돌 아님
            if _intersects(pa, pb):
                violations.append(
                    Violation(
                        "OWNERSHIP_GLOB_OVERLAP",
                        max(la, lb),
                        f"경로 패턴이 다른 슬롯 소유 경로와 같은 구체성으로 겹침: '{pa}'({oa}) vs '{pb}'({ob}) - 한 파일을 두 슬롯이 소유",
                    )
                )


def lint_text(text: str, notes: Optional[List[str]] = None) -> List[Violation]:
    """AIMEM.md 본문 문자열을 검사해 위반 목록을 반환한다. 위반이 없으면 빈 리스트.

    `notes` 가 주어지면, **위반이 아닌 정보/경고**(예: 게이팅으로 건너뛴 검사)를 그 리스트에
    덧붙인다. 노트는 반환값(위반 목록)에 들어가지 않으므로 exit 코드에 영향이 없고, 노트를
    넘기지 않는 호출자(테스트, board self-lint)의 반환값 계약도 그대로 유지된다.
    """
    violations: List[Violation] = []
    lines = text.splitlines()
    fenced = _fenced_mask(lines)

    # 0. 크기 상한 (`5절`) - 총량만 검사한다.
    total_lines = len(lines)
    if total_lines > MAX_TOTAL_LINES:
        violations.append(Violation(
            "SIZE_TOTAL_LINES", None,
            f"총 {total_lines}줄로 상한 {MAX_TOTAL_LINES}줄을 초과함. 오래된 '4. 핸드오프 로그'를 "
            f"`python3 tools/aimem_board.py archive-rollover --keep 10` 로 아카이브해 줄이십시오",
        ))
    handoff_spans = _section_spans(lines, fenced, 4)
    if handoff_spans:
        h_start, h_end = handoff_spans[0]
        entry_count = sum(1 for i in range(h_start, h_end) if not fenced[i] and HANDOFF_ENTRY_RE.match(lines[i]))
        if entry_count > MAX_HANDOFF_ENTRIES:
            violations.append(Violation(
                "SIZE_HANDOFF_LOG", h_start + 1,
                f"'4. 핸드오프 로그' 항목이 {entry_count}건으로 상한 {MAX_HANDOFF_ENTRIES}건을 초과함. "
                f"`python3 tools/aimem_board.py archive-rollover --keep 10` 로 오래된 것부터 아카이브하십시오",
            ))
        # 항목당 문자 수. 경계 판정은 **HANDOFF_ENTRY_RE 하나로만** 한다(T-013 단일화 유지) -
        # 항목은 시작줄부터 다음 항목 시작줄 직전(없으면 절 끝)까지이고, 이어지는 들여쓰기
        # 줄도 그 항목에 포함해 합산한다. 개행은 세지 않는다(줄을 접는 것으로 우회 못 하게).
        entry_starts = [
            i for i in range(h_start, h_end)
            if not fenced[i] and HANDOFF_ENTRY_RE.match(lines[i])
        ]
        for idx, start in enumerate(entry_starts):
            stop = entry_starts[idx + 1] if idx + 1 < len(entry_starts) else h_end
            chars = sum(len(lines[i]) for i in range(start, stop) if not fenced[i])
            if chars > MAX_LOG_ENTRY_CHARS:
                violations.append(Violation(
                    "SIZE_LOG_ENTRY_CHARS", start + 1,
                    f"핸드오프 로그 항목 하나가 {chars}자 > {MAX_LOG_ENTRY_CHARS}자. "
                    f"{chars - MAX_LOG_ENTRY_CHARS}자를 줄이거나 본문을 절로 옮기십시오 "
                    f"(로그는 '무엇이 바뀌었나' 한 줄, 근거·경위는 해당 절에)",
                ))

    # 1. REV 선언 - 정확히 한 번, 양의 정수 (펜스 안 예시는 세지 않는다)
    rev_matches = [
        (i + 1, m.group(1))
        for i, line in enumerate(lines)
        if not fenced[i]
        for m in [REV_RE.search(line)]
        if m
    ]
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

    # 구조: 필수 절이 여러 번 등장하면 첫 절만 검사되어 뒤 절 은닉(F6). 넷 다 중복 금지.
    for n, label in [(2, "2절 세션 명부"), (3, "3절 작업 보드"), (4, "4절 핸드오프 로그"), (6, "6절 파일 소유권")]:
        sp = _section_spans(lines, fenced, n)
        if len(sp) > 1:
            violations.append(
                Violation("DUPLICATE_SECTION", sp[1][0] + 1, f"'{label}' 헤딩이 {len(sp)}번 등장함 - 뒤 절이 은닉될 수 있음")
            )

    # REV 헤더-로그 동기 (T-028). 헤더 REV 는 4절 로그에 근거 항목을 가져야 한다. 오늘 21:12
    # 사건(헤더만 80->81 오르고 로그 누락 -> 관리자 자신이 슬롯 무단 쓰기로 오인)이 실측 구멍이다.
    # 단, **로그가 REV 를 본문에 표기하는 관례(`**REV N`)를 실제로 쓰는 문서에서만** 강제한다.
    # 관례가 전혀 없으면(표기 없는 로그) 대응 항목을 식별할 수 없어 오탐이 되므로 건너뛴다.
    # REV 선언이 하나이고 유효할 때만 검사한다(REV_MISSING/MULTIPLE/INVALID 와 중복 발화 방지).
    if len(rev_matches) == 1:
        h_line, h_val = rev_matches[0]
        if re.match(r"^\d+$", h_val) and int(h_val) > 0:
            logged_revs = set()
            for s, e in _section_spans(lines, fenced, 4):
                for i in range(s, e):
                    if not fenced[i]:
                        for m in LOG_REV_RE.finditer(lines[i]):
                            logged_revs.add(int(m.group(1)))
            if not logged_revs:
                # 게이팅 유지: 4절에 `**REV N` 표기가 하나도 없으면 대응 항목을 식별할 수 없어
                # 검사를 건너뛴다(픽스처·표기 관례 미사용 문서의 오탐 방지). 다만 조용히 죽으면
                # 초록불이 "REV 동기 확인됨"을 거짓 보증하므로, 스킵 사실을 노트로 남긴다.
                # 노트는 위반이 아니라 정보 한 줄이라 exit 코드를 올리지 않는다(T-031).
                if notes is not None:
                    notes.append(
                        f"REV_LOG_SYNC 스킵: 4절에 **REV 표기 없음 - 헤더 REV {h_val} 의 "
                        f"로그 동기 검사를 건너뜀(위반 아님, 정보)"
                    )
            elif int(h_val) not in logged_revs:
                violations.append(Violation(
                    "REV_LOG_MISSING", h_line,
                    f"헤더 REV {h_val} 에 대응하는 로그 항목이 4절에 없음 "
                    f"(로그가 선언한 REV: {sorted(logged_revs, reverse=True)}) - "
                    f"REV 헤더 증가와 4절 로그 기재는 한 번에 끝내야 함",
                ))

    # 의미: 관리자 선언과 감사 로그. VALID_DOC(관리자 선언 없는 최소 픽스처)를 깨지 않으려면
    # **관리자 선언이 있을 때만** 검사한다. 선언이 곧 "통치되는 AIMEM"이라는 표식이다.
    # (선언 자체를 지우는 공격은 이 조건 때문에 못 잡는다 - 한계로 outbox 에 명시)
    first_head = _first_heading_index(lines, fenced)
    manager_decl_line = None
    for i in range(first_head):
        if not fenced[i] and MANAGER_DECL_RE.search(lines[i]):
            manager_decl_line = i + 1
            break
    if manager_decl_line is not None:
        preamble = "\n".join(lines[i] for i in range(first_head) if not fenced[i])
        # F1: 관리자 선언이 있는데 못박은 세션키가 서문에 없으면 뿌리가 바꿔치기된 것.
        if MANAGER_SESSION_KEY not in preamble:
            violations.append(
                Violation(
                    "MANAGER_KEY_MISMATCH",
                    manager_decl_line,
                    "관리자 선언은 있으나 린터에 못박은 관리자 세션키가 서문에 없음 - 관리자 세션키 바꿔치기 가능성",
                )
            )
        # F8: 통치되는 AIMEM(관리자 선언 존재)은 감사 로그(4절)를 반드시 지녀야 한다.
        if not _section_spans(lines, fenced, 4):
            violations.append(
                Violation(
                    "HANDOFF_SECTION_MISSING",
                    manager_decl_line,
                    "관리자 선언이 있는 문서에 '4. 핸드오프 로그'(감사 추적)가 없음 - 소유권 변경 이력의 유일한 기록",
                )
            )

    roster_slots, roster_parsed = _check_roster(lines, fenced, violations)
    _check_board(lines, fenced, roster_slots, roster_parsed, violations)
    _check_ownership(lines, fenced, roster_slots, violations)

    return violations


def lint_file(path: str, notes: Optional[List[str]] = None) -> List[Violation]:
    """파일을 읽어 lint_text 에 넘긴다. 시그니처·반환 계약은 호출자(aimem_board.py,
    .githooks/pre-commit)가 의존하므로 바꾸지 않는다.

    아웃박스 크기 검사(OUTBOX_TOO_LARGE, T-028)는 REV 103 에서 제거했다 - `.aimem/outbox/` 는
    `8.0`(2026-09-22)부터 과거 기록이고 쓰는 주체가 없다. 쓰는 사람이 없는 대상의 페일세이프는
    코드만 무겁게 한다. 아웃박스 운용이 되살아나면 이 자리에 다시 붙인다.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return lint_text(text, notes)


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: aimem_lint.py <AIMEM.md 경로>", file=sys.stderr)
        return 2
    path = argv[0]
    notes: List[str] = []
    try:
        violations = lint_file(path, notes)
    except OSError as e:
        print(f"[IO_ERROR] 파일을 읽을 수 없음: {e}", file=sys.stderr)
        return 1
    # 노트(스킵 알림 등)는 위반과 별개로, 클린 통과든 위반이든 항상 출력한다.
    # 초록불과 "검사가 조용히 꺼진 초록불"을 구분하기 위한 정보 줄이다(T-031).
    for n in notes:
        print(f"[INFO] {n}")
    if not violations:
        print(f"OK: {path} - 위반 없음")
        return 0
    for v in violations:
        print(str(v))
    print(f"위반 {len(violations)}건")
    return 1


if __name__ == "__main__":
    sys.exit(main())
