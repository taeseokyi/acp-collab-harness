# T-060 린터를 2단계(DB 정본)로 바꾼다 - `tools/aimem_lint.py`

## 왜

`AIMEM.md` 의 운영 상태 표(2절 명부 / 3절 보드 / 4절 핸드오프 로그 / 4.5 대기 큐 / 6절 소유권)는
**이번 라운드에 `.aimem/aimem.db` 로 옮기고 본문에는 포인터 한 줄만 남긴다**(관리자가 같은 라운드에
직접 한다). 그러면 지금 린터가 하는 "표가 있어야 하고 형식이 맞아야 한다" 검사는 전부 거꾸로 된다 -
**표가 남아 있으면 위반**이다. 그 반전을 린터에 반영하는 것이 이 태스크다.

**지금 이 순간의 `AIMEM.md` 에는 아직 표가 그대로 있다.** 그러니 `python3 tools/aimem_lint.py AIMEM.md`
는 네 작업이 끝난 직후 새 위반(`STATE_TABLE_IN_AIMEM` 등)을 쏟아내는 것이 **정상**이다. 그것을 "내가
깨뜨렸다"고 보지 마라. 관리자가 표를 들어낸 뒤 rc0 이 된다. **너의 검증은 아래 픽스처 2종으로 한다.**

## 쓰기 경로

`tools/aimem_lint.py` **하나뿐이다.** 테스트(`tests/test_aimem_lint.py`)는 **S2 가 같은 시각에 같은
계약으로 고치고 있다** - 건드리지 마라. `tools/aimem_board.py` 도 건드리지 마라(다음 태스크다).

## 지금 코드 (읽고 시작할 자리)

- `lint_text(text, notes=None) -> List[Violation]` (526행) 이 본체. **이 시그니처와 반환 계약은 그대로 둔다** -
  `tools/aimem_board.py` 와 `.githooks/pre-commit` 과 S2 테스트가 의존한다
- `_check_roster`(277) / `_check_board`(349) / `_check_ownership`(447) 세 함수가 표 검사 전부
- `find_section`(164) / `extract_table`(175) 은 **`tools/aimem_board.py` 가 `lint.find_section` /
  `lint.extract_table` 로 import 한다. 지우지 마라.** (T-021 때 이걸 지워 board 전체가 죽은 회귀가 있다)

## 바꿀 것 - 규칙 집합 (관리자가 못박았다. 이름·동작을 바꾸지 마라)

### 그대로 두는 코드

`SIZE_TOTAL_LINES` / `REV_MISSING` / `REV_MULTIPLE` / `REV_INVALID` / `DUPLICATE_SECTION` /
`MANAGER_KEY_MISMATCH` (관리자 선언 + 세션키 접두사 `agent:claude:acp:` 핀. **이 검사가 2단계의
핵심 보증이다**).

### 없애는 코드 (규칙과 그 전용 헬퍼까지)

- `ROSTER_*` 9종 (`_check_roster` 통째로)
- `BOARD_*` 9종 (`_check_board` 통째로)
- `OWNERSHIP_*` 7종 (`_check_ownership` 통째로)
- `SIZE_HANDOFF_LOG` / `SIZE_LOG_ENTRY_CHARS` / `REV_LOG_MISSING` / `HANDOFF_SECTION_MISSING`
  - 넷 다 4절 본문을 전제한다. 4절 로그는 DB `events` 테이블로 간다
- 위 규칙만 쓰던 상수·헬퍼도 같이 지운다 (`VALID_STATUSES`, `ADMIN_OWNER_LITERALS`,
  `BOARD_NON_SLOT_OWNERS`, `PROTECTED_PATHS`, `MAX_HANDOFF_ENTRIES`, `MAX_LOG_ENTRY_CHARS`,
  `HANDOFF_ENTRY_RE`, `LOG_REV_RE`, `_glob_regex`, `_covers`, `_more_specific`, `_seg_overlap`,
  `_intersects`, `_governed_tables`, `_extract_tables`, `_col_index`, `_split_row`, `TOKEN_RE`, `SEP_RE`
  - **쓰이는 곳이 정말 없는지 `grep -n` 으로 확인한 것만** 지운다. `find_section`/`extract_table`/
  `_section_spans`/`_fenced_mask`/`_first_heading_index` 는 남는다)

### 새로 넣는 코드 4종

모두 **관리자 선언(`관리자\(단독 쓰기 권한\)` = 기존 `MANAGER_DECL_RE`)이 서문에 있을 때만** 검사한다.
선언 없는 최소 픽스처(테스트의 `good.md` 류)가 깨지면 안 된다 - 기존 `MANAGER_KEY_MISMATCH` 와 같은 게이팅이다.

1. **`STATE_TABLE_IN_AIMEM`** - 2·3·4·4.5·6절 **안에 마크다운 표가 남아 있으면** 위반.
   - 판정: 해당 절 구간에서 펜스(```) 밖이면서 `|` 로 시작하는 줄이 **2줄 이상** 있으면 표로 본다
     (한 줄짜리 포인터에 `|` 가 섞여도 오탐이 안 나게)
   - line 은 첫 표 줄, 메시지는 "운영 상태의 정본은 `.aimem/aimem.db` 다. 이 표를 `AIMEM-state.md`
     포인터 한 줄로 바꾸십시오" 류
   - **4.5 절 구간 찾기:** `_section_spans(lines, fenced, n)` 은 정수만 받는다. `## 4.5` 는
     `^##(?!#)\s+4\.5(\D|$)` 로 따로 찾아라. 그리고 `_section_spans(..., 4)` 가 `## 4.5` 를
     4절로 집어삼키지 않는지 **직접 확인**하고(현재 구현이 `4.` 로 끊는지 `4` 로 끊는지), 삼키면
     4절 구간은 `## 4.5` 직전에서 끝나게 하라
2. **`STATE_POINTER_MISSING`** - 그 다섯 절이 **존재하는데** 구간 안 어디에도 `AIMEM-state.md`
   문자열이 없으면 위반. 절 자체가 없으면 위반이 아니다(다른 문서일 수 있다)
3. **`REV_DB_MISMATCH`** - `AIMEM.md` 서문 REV 와 DB `meta.rev` 가 다르면 위반.
   render 가 서문 REV 를 맞추므로(`aimem_db.render` → `sync_rev_in_aimem`), 어긋남 = render 를 안 돌림
4. **`STATE_SNAPSHOT_STALE`** / **`STATE_SNAPSHOT_MISSING`** - `AIMEM-state.md` 가
   `aimem_db.render_text()` 산출물과 **다르면** / **없으면** 위반

### 3·4 를 넣는 자리 - `lint_repo()` 신설

`lint_text` 는 **순수 함수로 남긴다**(문자열만 본다. DB·파일을 읽지 않는다).
DB 를 보는 검사는 새 함수에 넣어라:

```python
def lint_repo(path, root=None, notes=None) -> List[Violation]:
    """lint_file(path) + DB 대조(REV_DB_MISMATCH / STATE_SNAPSHOT_*). main() 이 이것을 부른다."""
```

- `root` 생략 시 `path` 의 부모 디렉터리
- DB 는 `sys.path` 에 `tools` 를 넣고 `import aimem_db` 로 쓴다. `aimem_db.DB`(= `<root>/.aimem/aimem.db`)
  가 **없으면 위반이 아니라 `notes` 한 줄로 건너뛴다**(픽스처·임시 디렉터리). import 실패도 같다.
  `aimem_db` 는 모듈 상수로 경로를 잡으므로 `root` 가 저장소 루트가 아닐 때는 건너뛰어라
  (`pathlib.Path(root).resolve() != aimem_db.ROOT` 이면 note)
- **스냅샷 비교에서 `aimem_db.STAMP_PREFIX`(`- 정본은 ...`) 로 시작하는 줄 하나는 양쪽에서 빼고 비교한다.**
  그 줄만 생성 시각을 담아 매번 달라진다. 나머지가 한 줄이라도 다르면 `STATE_SNAPSHOT_STALE`,
  메시지에 **처음 다른 줄 번호와 양쪽 값 80자**를 넣어라(없으면 고칠 수가 없다)
- `main()` 은 `lint_repo` 를 부르고 나머지(노트 출력·종료 코드)는 지금 그대로 둔다.
  `lint_file` / `lint_text` 는 남긴다 (board·테스트가 쓴다)

## 검증 (이대로 돌리고 출력을 보고에 붙여라)

```bash
python3 -c "import sys; sys.path.insert(0,'tools'); import aimem_lint; print('import ok')"
python3 tools/aimem_lint.py AIMEM.md ; echo "현물 rc=$? (표가 아직 있으므로 STATE_TABLE_IN_AIMEM 이 나오는 것이 정상)"
python3 tools/aimem_lint.py AIMEM-state.md ; echo "스냅샷 rc=$?"
python3 -m unittest discover -s tests 2>&1 | tail -5   # S2 가 테스트를 고치는 중이라 실패가 섞일 수 있다. 그 사실만 보고에 적어라
```

그리고 **픽스처 2종을 네가 만들어 돌려라**(`/tmp` 아래. 저장소에 파일을 남기지 마라):

- (A) 관리자 선언 + 다섯 절이 **포인터 한 줄**인 문서 → 위반 0 이어야 한다
- (B) (A) 에서 3절에 표를 도로 붙인 문서 → `STATE_TABLE_IN_AIMEM` 1건만 나와야 한다

```bash
python3 - <<'PY'
import sys; sys.path.insert(0,'tools')
import aimem_lint as L
# (A)/(B) 문자열을 여기서 만들고 L.lint_text(...) 로 코드 목록을 찍어라
PY
```

## 보고

첫 줄 상태. 이어서 ① 없앤 코드/함수 목록 ② 새 코드 4종의 판정 조건 한 줄씩 ③ 위 검증 명령의
**실제 출력** ④ 픽스처 (A)(B) 결과 ⑤ 남은 것/다음 담당자가 알아야 할 것.
