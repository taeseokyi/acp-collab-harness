# T-061 린터 2단계 테스트로 갈아끼우기 - `tests/test_aimem_lint.py`

## 왜

운영 상태 표(`AIMEM.md` 2절 명부 / 3절 보드 / 4절 로그 / 4.5 큐 / 6절 소유권)가 이번 라운드에
`.aimem/aimem.db` 로 옮겨간다. 그래서 린터 규칙이 **반전**된다 - "표가 있어야 한다" 에서
"표가 **없어야** 한다" 로. **S1 이 지금 같은 시각에 `tools/aimem_lint.py` 를 그 계약으로 고치고 있다.**
너는 테스트를 같은 계약에 맞춘다.

## 쓰기 경로

`tests/test_aimem_lint.py` **하나뿐이다.** `tools/aimem_lint.py` 는 S1 이 고치는 중이다 - **읽기만 하고
절대 쓰지 마라.** `tools/aimem_board.py` 도 쓰지 마라.

## 못박힌 계약 (S1 에게 준 것과 같은 문서다)

### 남는 위반 코드

`SIZE_TOTAL_LINES` / `REV_MISSING` / `REV_MULTIPLE` / `REV_INVALID` / `DUPLICATE_SECTION` /
`MANAGER_KEY_MISMATCH`

### 사라지는 위반 코드 (이 코드를 단언하는 테스트는 전부 지운다)

`ROSTER_*` 9종 / `BOARD_*` 9종 / `OWNERSHIP_*` 7종 /
`SIZE_HANDOFF_LOG` / `SIZE_LOG_ENTRY_CHARS` / `REV_LOG_MISSING` / `HANDOFF_SECTION_MISSING`

사라지는 상수·헬퍼도 같이 import 에서 뺀다: `VALID_STATUSES`, `ADMIN_OWNER_LITERALS`,
`BOARD_NON_SLOT_OWNERS`, `PROTECTED_PATHS`, `MAX_HANDOFF_ENTRIES`, `MAX_LOG_ENTRY_CHARS`.
**남는 것:** `find_section`, `extract_table`, `lint_text`, `lint_file`, `MAX_TOTAL_LINES`,
`MANAGER_SESSION_KEY`.

### 새 위반 코드 4종 (테스트를 새로 써야 하는 자리)

모두 **관리자 선언(서문에 `관리자(단독 쓰기 권한)`)이 있을 때만** 발화한다. 선언 없는 최소
픽스처는 위반 0 이어야 한다 - 이 게이팅 자체도 테스트 한 건으로 못박아라.

1. `STATE_TABLE_IN_AIMEM` - 2·3·4·4.5·6절 구간 안에 펜스 밖 `|` 로 시작하는 줄이 **2줄 이상**이면 위반
2. `STATE_POINTER_MISSING` - 그 절이 있는데 구간 안에 `AIMEM-state.md` 문자열이 없으면 위반
   (절 자체가 없으면 위반 아님)
3. `REV_DB_MISMATCH` - 서문 REV 와 DB `meta.rev` 불일치
4. `STATE_SNAPSHOT_STALE` / `STATE_SNAPSHOT_MISSING` - `AIMEM-state.md` 가
   `aimem_db.render_text()` 와 다름 / 없음

3·4 는 `lint_text` 가 아니라 **새 함수 `lint_repo(path, root=None, notes=None)`** 이 한다.
`lint_text` 는 순수 함수로 남는다(문자열만 본다). DB 가 없거나 `root` 가 저장소 루트가 아니면
**위반이 아니라 `notes` 한 줄**이다 - 임시 디렉터리 픽스처는 그래서 조용히 통과한다.
**스냅샷 비교는 `aimem_db.STAMP_PREFIX` 로 시작하는 줄 하나를 양쪽에서 빼고 한다**(생성 시각 줄).

## 어떻게

1. 지금 파일(1000줄 남짓)에서 `ROSTER`/`BOARD`/`OWNERSHIP`/핸드오프 크기 관련 **테스트 클래스와
   헬퍼를 통째로 지운다.** 부분 수정하지 마라 - 전제가 사라진 테스트다
2. `aimem_board.py` 스모크/행동 테스트(파일 뒤쪽 `_BOARD3`/`_ROSTER2`/`_OWNER6`/`_QUEUE` 를 쓰는
   클래스들)는 **이번 라운드에 board 를 고치지 않으므로 그대로 둔다.** 다만 그 테스트들이 쓰는
   픽스처 문서에는 표가 들어 있어야 board 가 동작한다 - 그 픽스처는 `lint_text` 위반 단언과
   엮지 마라. **board 테스트가 깨지면 보고에 적되 고치려 들지 마라**(S1 이 쓰는 파일이다)
3. 새 코드 4종 테스트를 더한다. 각 코드마다 **발화 1건 + 비발화(정상 문서) 1건**
4. `lint_repo` 테스트: (a) DB 없는 임시 디렉터리 → 위반 0 + note 1줄 이상
   (b) 저장소 현물(`AIMEM.md`, root=저장소 루트) → 터지지 않고 리스트를 돌려준다(내용은 단언하지 마라.
   관리자가 같은 라운드에 본문을 고치는 중이라 건수가 움직인다)

## 검증 (이대로 돌리고 출력을 보고에 붙여라)

```bash
python3 -m unittest discover -s tests -v 2>&1 | tail -30
python3 -m unittest discover -s tests 2>&1 | tail -5
python3 -c "import sys; sys.path.insert(0,'tools'); import aimem_lint; print(sorted(n for n in dir(aimem_lint) if not n.startswith('_')))"
```

S1 이 아직 린터를 못 고쳤으면 새 코드 테스트가 실패한다. **그 실패는 네 결함이 아니다** -
실패 개수와 이름을 보고에 그대로 적어라. 테스트 파일이 import 에러로 통째로 죽는 것만은 피해라
(사라질 상수를 import 하지 마라).

## 보고

첫 줄 상태. ① 지운 테스트 클래스 목록과 건수 ② 새로 쓴 테스트 목록 ③ 위 명령의 **실제 출력**
(요약하지 말고 마지막 5줄 그대로) ④ S1 쪽 미구현으로 실패한 것과 네 쪽 결함을 구분해서.

---

## 2차 시도 메모 (관리자, 19:30)

1차(`T-061-S2-a1-192300`, codex/kistillm)는 **KISTI LLM 서버가 내려가 있어** 아무 일도 못 하고
`ERROR: Reconnecting... waiting for network` 만 반복하다 관리자가 PID 로 내렸다.
**산출물 없음 - `tests/test_aimem_lint.py` 는 1차 이전 그대로다. 처음부터 하라.**

**S1 의 린터 작업은 이미 끝났다**(`tools/aimem_lint.py`, 709줄 → 454줄). 즉 **구현이 먼저 있고
테스트가 따라가는 상황**이다. 다음 두 가지가 1차 브리프와 달라졌으니 그대로 반영하라.

- **지워진 줄 알았으나 남은 상수·헬퍼:** `SEP_RE`, `VALID_STATUSES`, `MAX_HANDOFF_ENTRIES`,
  `HANDOFF_ENTRY_RE`, `_col_index`, `_split_row`, `_extract_tables` 는 **남아 있다**
  (`tools/aimem_board.py` 가 쓰기 때문이다). import 해도 된다
- **정말 사라진 것:** `ADMIN_OWNER_LITERALS`, `BOARD_NON_SLOT_OWNERS`, `PROTECTED_PATHS`,
  `MAX_LOG_ENTRY_CHARS`, `LOG_REV_RE`, `TOKEN_RE`, `_glob_regex`, `_covers`, `_more_specific`,
  `_seg_overlap`, `_intersects`, `_governed_tables`, `_check_roster`, `_check_board`, `_check_ownership`
- **지금 테스트 모듈은 `ADMIN_OWNER_LITERALS` 를 import 해서 로드 단계에서 통째로 죽는다**
  (`python3 -m unittest discover -s tests` → `ImportError`). **이걸 먼저 고쳐라** - 그래야
  나머지 테스트가 돌아간다
- 새 코드는 **5종**이다: `STATE_TABLE_IN_AIMEM`, `STATE_POINTER_MISSING`, `REV_DB_MISMATCH`,
  `STATE_SNAPSHOT_MISSING`, `STATE_SNAPSHOT_STALE`. 뒤 셋은 `lint_repo(path, root=None, notes=None)`
  에서만 발화한다. 실제 구현을 **읽고**(`grep -n "STATE_\|REV_DB\|def lint_repo" tools/aimem_lint.py`)
  그 동작에 맞춰라 - 브리프와 구현이 어긋나면 **구현이 정본이고, 어긋난 점을 보고에 적어라**
