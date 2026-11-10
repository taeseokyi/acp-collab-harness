#!/usr/bin/env python3
"""AIMEM.md 구조 불변식 린터 - 2단계(DB 정본). 표준 라이브러리만 사용.

2단계(T-060)부터 운영 상태(2절 명부 / 3절 보드 / 4절 로그 / 4.5 대기 큐 / 6절 소유권)의 정본은
`.aimem/aimem.db` 이고, AIMEM.md 의 그 절들은 `AIMEM-state.md` 를 가리키는 포인터 한 줄만 둔다.
그래서 예전의 "표가 있어야 하고 형식이 맞아야 한다" 검사(ROSTER_* / BOARD_* / OWNERSHIP_* /
SIZE_HANDOFF_LOG / SIZE_LOG_ENTRY_CHARS / REV_LOG_MISSING / HANDOFF_SECTION_MISSING)는 없앴고,
거꾸로 **표가 남아 있으면 위반**이다.

위반 코드:
- `lint_text`(순수 함수, 문자열만 본다): SIZE_TOTAL_LINES / REV_MISSING / REV_MULTIPLE / REV_INVALID /
  DUPLICATE_SECTION / MANAGER_KEY_MISMATCH / STATE_TABLE_IN_AIMEM / STATE_POINTER_MISSING
- `lint_repo`(DB·파일 대조): 위 전부 + REV_DB_MISMATCH / STATE_SNAPSHOT_STALE / STATE_SNAPSHOT_MISSING
새 코드 5종(STATE_* / REV_DB_MISMATCH)은 MANAGER_KEY_MISMATCH 처럼 **서문에 관리자 선언이 있을 때만** 본다.

T-021(REV 71)의 파서 계층(펜스 인식·중복 절 검출)은 그대로 쓴다.
"""

import pathlib
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

REV_RE = re.compile(r"\*\*REV:\s*(-?\d+)\*\*")
# 아래 넷(SEP_RE / VALID_STATUSES / MAX_HANDOFF_ENTRIES / HANDOFF_ENTRY_RE)과 `_col_index` 는 린터
# 규칙에서는 더 쓰지 않지만 **`tools/aimem_board.py` 가 `lint.X` 로 import 한다.** board 가 2단계로
# 바뀔 때(다음 태스크) 함께 정리한다. 지금 지우면 board 가 죽는다(T-021 회귀와 같은 모양).
SEP_RE = re.compile(r"^\|?[\s\-:|]+\|?$")
VALID_STATUSES = {"TODO", "ASSIGNED", "IN-PROGRESS", "REVIEW", "DONE", "BLOCKED"}

# 의미 계층 (T-021). 린터는 "누가 진짜 관리자인가"를 알 수 없다. 아래는 그 권위를
# **검사 가능한 형태로 번역**한 것이다 - 근거와 한계는 outbox [T-021] 에 적었다.
#
# 관리자 세션키를 린터 소스(보호 아티팩트, S1 소유)에 못박는다. 공격자가 쓰기 가능한
# AIMEM.md 안의 관리자 선언을 다른 세션키로 바꿔치기하면(F1) 여기 값과 어긋나 잡힌다.
# 신뢰의 뿌리를 쓰기 가능한 파일에서 코드로 옮기는 것이 요점. 관리자 키가 정당하게
# 바뀌면 이 상수도 함께 고쳐야 한다(6.1 자기구속과 같은 성격).
# REV 109: 관리자는 Claude ACP 세션(하네스 claude). 세션키는 `agent:claude:acp:<uuid>` 로 나므로
# 못박는 것은 그 접두사다. 서문 관리자 선언에 이 접두사가 없으면 뿌리가 바뀐 것으로 본다.
MANAGER_SESSION_KEY = "agent:claude:acp:"
# AIMEM.md 가 영어로 바뀌어도(REV 128) 같은 선언을 알아보도록 두 표기를 받는다.
MANAGER_DECL_RE = re.compile(r"관리자\(단독 쓰기 권한\)|Manager \(sole write authority\)")

# 크기 상한 (`5절`). 작업자가 매 턴 전문을 읽으므로 크기는 곧 턴당 비용이다. 총량만 강제한다.
MAX_TOTAL_LINES = 800
# board 호환용(위 주석 참조). 린터 규칙은 더 쓰지 않는다 - 4절 로그는 DB `events` 로 갔다.
MAX_HANDOFF_ENTRIES = 12
HANDOFF_ENTRY_RE = re.compile(r"^- `(\d{4})-(\d{2})-\d{2}")

# 절 헤딩. `## N.` (세 번째 # 이 아님). 절 종료 판정에도 쓴다.
SECTION_HEAD_RE = re.compile(r"^##(?!#)\s")
# `## 4.5` 는 정수 절 번호가 아니라 `_section_spans` 가 못 찾는다. 따로 찾는다.
# (`_section_spans(.., 4)` 는 `4\.\s` 로 시작을 판정하므로 `## 4.5` 를 4절 시작으로 보지 않고,
#  4절 구간은 다음 `## ` 헤딩인 `## 4.5` 직전에서 끝난다 - 집어삼키지 않는다.)
SECTION_45_RE = re.compile(r"^##(?!#)\s+4\.5(\D|$)")

# 2단계: AIMEM.md 에서 표를 들어내고 포인터만 남기는 절. (라벨, 절 번호 - 4.5 는 문자열)
STATE_SECTIONS = (("2절 세션 명부", 2), ("3절 작업 보드", 3), ("4절 핸드오프 로그", 4),
                  ("4.5 대기 큐", "4.5"), ("6절 파일 소유권", 6))
STATE_POINTER = "AIMEM-state.md"


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


def _first_heading_index(lines: List[str], fenced: List[bool]) -> int:
    for i, line in enumerate(lines):
        if not fenced[i] and SECTION_HEAD_RE.match(line):
            return i
    return len(lines)


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
            f"총 {total_lines}줄로 상한 {MAX_TOTAL_LINES}줄을 초과함. "
            f"줄이십시오 (운영 상태는 `.aimem/aimem.db` 로, 지난 서술은 `.aimem/archive/` 로)",
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

    # 의미: 관리자 선언. VALID_DOC(관리자 선언 없는 최소 픽스처)를 깨지 않으려면
    # **관리자 선언이 있을 때만** 검사한다. 선언이 곧 "통치되는 AIMEM"이라는 표식이다.
    # (선언 자체를 지우는 공격은 이 조건 때문에 못 잡는다 - 알려진 한계)
    first_head = _first_heading_index(lines, fenced)
    manager_decl_line = _manager_decl_line(lines, fenced)
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
        _check_state_sections(lines, fenced, violations)
        _check_handoff_entries(lines, fenced, violations)
        if notes is not None:
            _note_weight(lines, fenced, notes)

    return violations


#: 가벼움 지표 (REV 130). 위반이 아니라 노트다 - 본문에 날짜·REV 인용이 쌓이면 역사 서술이 규약 자리로 돌아오고 있다는 신호.
WEIGHT_DATES_MAX = 20
WEIGHT_REV_MENTIONS_MAX = 30


def _note_weight(lines: List[str], fenced: List[bool], notes: List[str]) -> None:
    body = [l for i, l in enumerate(lines) if not fenced[i]]
    dates = sum(len(re.findall(r"\b20\d\d-\d\d-\d\d\b", l)) for l in body)
    revs = sum(len(re.findall(r"\bREV \d+", l)) for l in body)
    if dates > WEIGHT_DATES_MAX or revs > WEIGHT_REV_MENTIONS_MAX:
        notes.append(f"가벼움: 본문에 날짜 {dates}개 / REV 인용 {revs}개 (권고 {WEIGHT_DATES_MAX}/{WEIGHT_REV_MENTIONS_MAX} 이하) - "
                     f"경위는 .aimem/archive/ 로, 본문에는 규칙과 포인터만 (위반 아님, 정보)")


def _check_handoff_entries(lines: List[str], fenced: List[bool], violations: List[Violation]) -> None:
    """REV 129: 4절은 관리 방법만 적는다. 로그 항목(`- \`YYYY-MM-DD\``)이 남아 있으면 문서가 다시 무거워지는 길이다 -
    항목은 `.aimem/handoff.md` (`aimem_db.py handoff add`) 에 쌓이고 오래된 것은 `handoff rollover` 가 아카이브로 보낸다."""
    for s, e in _section_spans(lines, fenced, 4):
        hits = [i for i in range(s, e) if not fenced[i] and HANDOFF_ENTRY_RE.match(lines[i])]
        if hits:
            violations.append(Violation(
                "HANDOFF_IN_AIMEM", hits[0] + 1,
                f"4절에 핸드오프 로그 항목 {len(hits)}건이 남아 있음. 항목은 `.aimem/handoff.md` 에 둔다 - "
                f"`python3 tools/aimem_db.py handoff add --body '…'`; 이 줄들은 거기로 옮기십시오",
            ))


def _manager_decl_line(lines: List[str], fenced: List[bool]) -> Optional[int]:
    """서문(첫 `## ` 헤딩 전, 펜스 밖)의 관리자 선언 줄 번호(1-indexed). 없으면 None."""
    first_head = _first_heading_index(lines, fenced)
    for i in range(first_head):
        if not fenced[i] and MANAGER_DECL_RE.search(lines[i]):
            return i + 1
    return None


def _state_section_spans(lines: List[str], fenced: List[bool], number) -> List[Tuple[int, int]]:
    """STATE_SECTIONS 의 절 구간. 정수는 `_section_spans`, "4.5" 는 SECTION_45_RE 로 찾는다."""
    if number != "4.5":
        return _section_spans(lines, fenced, number)
    spans = []
    for s, line in enumerate(lines):
        if fenced[s] or not SECTION_45_RE.match(line):
            continue
        end = len(lines)
        for j in range(s + 1, len(lines)):
            if not fenced[j] and SECTION_HEAD_RE.match(lines[j]):
                end = j
                break
        spans.append((s, end))
    return spans


def _check_state_sections(lines: List[str], fenced: List[bool], violations: List[Violation]) -> None:
    """2단계(T-060): 2·3·4·4.5·6절은 표 없이 `AIMEM-state.md` 포인터만 둔다.

    - STATE_TABLE_IN_AIMEM: 절 구간에서 펜스 밖 `|` 로 시작하는 줄이 **2줄 이상**이면 표가 남은 것.
      (한 줄짜리 포인터에 `|` 가 섞여도 오탐이 안 나게 1줄은 봐준다. 구분선 유무는 따지지 않는다 -
      구분선을 빼서 표 판정을 피하는 우회를 막는다.)
    - STATE_POINTER_MISSING: 절이 **있는데** 구간 어디에도 `AIMEM-state.md` 가 없으면. 절이 없으면 통과.
    """
    for label, number in STATE_SECTIONS:
        spans = _state_section_spans(lines, fenced, number)
        if not spans:
            continue
        pipe_lines = [
            i for s, e in spans for i in range(s, e)
            if not fenced[i] and lines[i].lstrip().startswith("|")
        ]
        if len(pipe_lines) >= 2:
            violations.append(Violation(
                "STATE_TABLE_IN_AIMEM", pipe_lines[0] + 1,
                f"'{label}' 에 표가 남아 있음({len(pipe_lines)}줄). 운영 상태의 정본은 `.aimem/aimem.db` 다. "
                f"이 표를 `{STATE_POINTER}` 포인터 한 줄로 바꾸십시오 (`python3 tools/aimem_db.py render`)",
            ))
        if not any(not fenced[i] and STATE_POINTER in lines[i] for s, e in spans for i in range(s, e)):
            violations.append(Violation(
                "STATE_POINTER_MISSING", spans[0][0] + 1,
                f"'{label}' 에 `{STATE_POINTER}` 포인터가 없음 - 이 절의 운영 상태를 어디서 읽는지 알 수 없음",
            ))


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


def _first_diff(a: List[str], b: List[str]) -> Optional[Tuple[int, str, str]]:
    """두 줄 목록에서 처음 다른 자리 (1-indexed 번호, a 값, b 값). 같으면 None. 길이 차이도 차이다."""
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "<없음>"
        y = b[i] if i < len(b) else "<없음>"
        if x != y:
            return i + 1, x, y
    return None


def lint_repo(path, root=None, notes: Optional[List[str]] = None) -> List[Violation]:
    """lint_file(path) + DB 대조(REV_DB_MISMATCH / STATE_SNAPSHOT_*). main() 이 이것을 부른다.

    `lint_text` 는 순수 함수로 두고, DB·파일을 읽는 검사는 여기에만 둔다. DB 검사도 관리자 선언이
    있는 문서에서만 한다(나머지 2단계 규칙과 같은 게이팅). DB 가 없거나, `aimem_db` import 가
    실패하거나, `root` 가 `aimem_db.ROOT` 가 아니면 위반이 아니라 노트 한 줄로 건너뛴다.
    """
    if notes is None:
        notes = []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    violations = lint_text(text, notes)

    lines = text.splitlines()
    fenced = _fenced_mask(lines)
    if _manager_decl_line(lines, fenced) is None:
        return violations

    root_path = pathlib.Path(root) if root is not None else pathlib.Path(path).resolve().parent
    tools_dir = str(pathlib.Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import aimem_db  # noqa: E402 - 린터 단독 실행(훅)에서도 DB 검사가 돌게 지연 import
    except Exception as e:  # ImportError 외에 모듈 최상위 오류도 같은 취급
        notes.append(f"DB 대조 스킵: aimem_db import 실패({e.__class__.__name__}: {e}) - 위반 아님, 정보")
        return violations
    if root_path.resolve() != aimem_db.ROOT:
        notes.append(f"DB 대조 스킵: root {root_path.resolve()} 가 aimem_db.ROOT({aimem_db.ROOT}) 가 아님 - 위반 아님, 정보")
        return violations
    if not aimem_db.DB.exists():
        # aimem_db.connect() 는 DB 를 새로 만들어 버리므로 반드시 먼저 존재를 본다.
        notes.append(f"DB 대조 스킵: {aimem_db.DB} 없음 - 위반 아님, 정보")
        return violations

    # REV_DB_MISMATCH - 서문 REV 가 하나이고 유효할 때만(REV_* 와 중복 발화 방지).
    rev_matches = [
        (i + 1, m.group(1)) for i, line in enumerate(lines)
        if not fenced[i] for m in [REV_RE.search(line)] if m
    ]
    try:
        with aimem_db.connect() as con:
            db_rev = aimem_db.rev(con)
        snapshot = aimem_db.render_text()
    except Exception as e:
        notes.append(f"DB 대조 스킵: DB 읽기 실패({e.__class__.__name__}: {e}) - 위반 아님, 정보")
        return violations
    if len(rev_matches) == 1 and re.match(r"^\d+$", rev_matches[0][1]):
        line_no, val = rev_matches[0]
        if db_rev is None:
            notes.append("REV_DB 대조 스킵: DB meta.rev 없음 - 위반 아님, 정보")
        elif int(val) != db_rev:
            violations.append(Violation(
                "REV_DB_MISMATCH", line_no,
                f"서문 REV {val} 와 DB meta.rev {db_rev} 가 다름 - REV 의 정본은 DB 다. "
                f"`python3 tools/aimem_db.py render` 가 서문 REV 를 맞춘다(render 를 안 돌린 상태)",
            ))

    # STATE_SNAPSHOT_* - 생성 시각 줄(STAMP_PREFIX) 하나만 양쪽에서 빼고 비교한다.
    state_path = root_path / STATE_POINTER
    if not state_path.exists():
        violations.append(Violation(
            "STATE_SNAPSHOT_MISSING", None,
            f"`{STATE_POINTER}` 이 없음 - `python3 tools/aimem_db.py render` 로 만드십시오",
        ))
        return violations

    def _strip_stamp(body: str) -> List[str]:
        out, dropped = [], False
        for ln in body.splitlines():
            if not dropped and ln.startswith(aimem_db.STAMP_PREFIX):
                dropped = True
                continue
            out.append(ln)
        return out

    current = state_path.read_text(encoding="utf-8")
    diff = _first_diff(_strip_stamp(current), _strip_stamp(snapshot))
    if diff is None and current.endswith("\n") != snapshot.endswith("\n"):
        diff = (len(current.splitlines()), "(끝 개행 차이)", "(끝 개행 차이)")
    if diff is not None:
        n, have, want = diff
        violations.append(Violation(
            "STATE_SNAPSHOT_STALE", None,
            f"`{STATE_POINTER}` 이 DB 렌더 결과와 다름(생성 시각 줄 제외 {n}번째 줄부터). "
            f"현물: {have[:80]!r} / DB: {want[:80]!r} - `python3 tools/aimem_db.py render` 를 돌리십시오",
        ))
    return violations


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: aimem_lint.py <AIMEM.md 경로>", file=sys.stderr)
        return 2
    path = argv[0]
    notes: List[str] = []
    try:
        violations = lint_repo(path, notes=notes)
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
