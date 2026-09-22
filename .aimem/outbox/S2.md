## [T-029] 2026-09-11 / STATUS REVIEW — board 쓰기 명령의 행위 단언
- 개시 대조(실측): AIMEM.md 6행 **REV 82** ✓ / 239행 S2 토큰 `3e21f2` ✓ / 세션키 `c90aeae0` ✓. 쓰기 범위 준수: **이번 변경은 `tests/test_aimem_lint.py` + 이 아웃박스 두 곳뿐.** `tools/aimem_lint.py`·`aimem_board.py`(S1 소유)는 **읽기만**. 커밋 안 함.
- 오귀속 철회·4절 로그 반영 접수. 1단계 기각 및 내 근거(주입점 부재→S1→S2 순서 / board 가 lint 공개 API 에 얹혀 T-024 동반파손) 채택 확인.

### 무엇을 채웠나
현행 `TestBoardSmoke` 는 9개 쓰기 하위명령에 **exit0 + 산출물 린트통과**만 봤다 — 즉 board-set 이 엉뚱한 행/칸에 써도 린트만 통과하면 초록(S3 [T-027] (b) 가 지목, 내가 T-024 에서 겪은 파손이 빠져나간 경로). 새 클래스 **`TestBoardBehavior`** 9건을 추가해 두 가지를 못박음:
1. **의도한 행·의도한 칸이 의도한 값으로** 바뀐다 (`lint.extract_table`+`_col_index` 로 그 칸을 읽어 비교).
2. **그 외 모든 줄이 바이트 불변** — 멀티셋 줄 차분(`_line_diff`)으로 `removed`/`added` 가 의도한 줄만 담는지 단언. 옆줄을 망가뜨리면 여기서 잡힌다.

### 하위명령별 단언 (요청 6 + 판단으로 3 추가)
- **board-set**(요청): T-1 상태=REVIEW, 그 행 다른 칸·T-2 행 불변, **정확히 1줄만 변경**.
- **board-add**(요청): 신규 T-9 가 올바른 헤더 아래(담당 슬롯=S1·상태=TODO…), `removed==[]`·added 1줄, ID 순서 `[T-1,T-2,T-9]`. (위치기반 append 라 헤더 순서 어긋나면 깨짐)
- **roster-set**(요청): S1 세션키만 갱신, S1 타칸(역할/하네스/토큰)·S2 행 전부 불변, 1줄 변경.
- **queue-add**(요청): §4.5 맨아래 순서=max+1=2, 후보 슬롯·비고 올바른 열, 기존 순서1 행 불변.
- **queue-pop**(요청): **2행 큐**로 태워 top(대기 X)만 반환·제거 증명, 잔여(대기 Y) 순서 2→**1 재번호** 단언, 변경 줄은 전부 큐 내부(§2/§3/§6 불변).
- **owner-add**(요청): §6 신규행 경로/소유 열 정위치, 기존 3행 그대로.
- **rev-bump**(추가): `--now` 로 결정화 — REV 5→6, `최종 갱신: 2026-08-26 12:00`, **딱 2줄**(REV·최종갱신)만 변경.
- **handoff-add**(추가): §4 **맨 위** 삽입(3→4건, 기존 top 이 둘째로 밀림), 시각은 도구가 박음을 정규식으로 확인. 시각 무관 구조 단언이라 비결정성 없음.
- **archive-rollover**(추가): --keep 1 → 최신(맨 위) 1건 유지·나머지 절단, 아카이브는 tmpdir 안으로만(저장소 `.aimem/archive` 무접촉).

3개를 다룬 이유: 전부 결정적으로 만들 수 있었고(시각은 `--now`/구조단언, 아카이브는 tmpdir 격리) (b) 의 구멍을 가장 넓게 닫는다. 다루지 않은 것 없음.

### 검증
- `python3 tests/test_aimem_lint.py` → **Ran 73, OK** (64→+9). `python3 -m unittest discover -s tests` 도 73 OK.
- `python3 tools/aimem_lint.py AIMEM.md` → 위반 0.
- **비공허 증명(뮤테이션 2건, 저장소 무접촉 몽키패치):** ① board-set 을 엉뚱한 열에 쓰게 → 테스트 실패. ② **린트는 통과하나 엉뚱한 행**(값 유효)에 쓰게 → 셀 단언이 실패 검출. 즉 S3 가 지목한 "옆줄 망가져도 린트 통과" 구멍을 실제로 잡는다.

### board 버그 발견 여부
**없음.** 현행 `aimem_board.py` 9개 명령은 전부 의도한 칸만 바꾸고 나머지 바이트 불변 — 새 단언을 다 통과. (버그를 찾았으면 고치지 않고 여기 적으라는 지시대로, 찾은 게 없음을 명시.) 단, **행위 계약이 이제 회귀로 고정**됐으니 이후 리팩터가 칸/행/순서를 어긋내면 커밋 전에 걸린다.

### T-028(S1) 충돌 여부
S1 이 같은 라운드에 `aimem_lint.py` 에 검사 2종(아웃박스 크기 가드 / 헤더REV↔4절로그 동기)을 추가 중. 내 파일과 다른 파일이라 직접 충돌은 없으나, **린터에 검사가 늘면 `BOARD_FIXTURE`/`VALID_DOC` 가 새로 걸릴 수 있다** — 특히 '헤더REV↔4절로그 동기' 검사가 `BOARD_FIXTURE`(REV 5, §4 3건)에 발동하면 `TestBoardBehavior`·`TestBoardSmoke` 시드가 깨진다. S1 병합 후 재실행 필요. 깨지면 이 아웃박스로 알린다.

STATUS: **REVIEW** (S3 검수 요청).

---

## [1단계 구체화] 2026-09-11 / 템플릿화 - 검증가능성 입장 (구현 안 함, 테스트 읽기만)
- 개시 대조(파일 실측): AIMEM.md 6행 **REV 81** = 브리프 ✓ / 239행 S2 토큰 `3e21f2` ✓ / 세션키 `c90aeae0` ✓ / 쓰기 범위 `tests/test_aimem_lint.py`·`tools/aimem_pipeline.py`·`.aimem/pipeline.log`·이 아웃박스. **이 턴 쓰기는 이 아웃박스 한 곳뿐.** 테스트 실측: `python3 -m unittest discover -s tests` → **Ran 64, OK**.

### Q1. 하드코딩에 의존하는 테스트 — 몇 건·어느 것 (파일: `tests/test_aimem_lint.py` 단일)
결론: **64건 사실상 전부**가 최소 한 축에 묶여 있다. 세 픽스처(`VALID_DOC` L25, `ROSTER_KEYS_DOC` L457, `BOARD_FIXTURE` L607)가 관리자키·한국어 선언구·한국어 헤더·절번호·6-hex 토큰·상태어휘를 **본문 리터럴로 함께** 박고 있어서, 한 축을 설정화하면 픽스처가 통째로 깨진다. 축별로 **터지는(=값을 직접 단언하거나 리터럴을 박은) 테스트**:
- **관리자 세션키**(`MANAGER_SESSION_KEY` L30 / `VALID_DOC` L29 리터럴): 상수 import(L17) 후 — `TestManagerDeclChecks` 5건 전부(L357 `DECL_LINE`, L362 `test_manager_key_mismatch_when_key_swapped`, L377 `test_missing_key_and_s4_cooccur` 은 스왑 대상 `...:9999999999` 를 **하드코딩**), `ROSTER_KEYS_DOC`(L492)·`BOARD_FIXTURE`(L656)를 쓰는 `TestSessionKeyUniqueness` 3건·`TestBoardSmoke` 3건. **VALID_DOC L29 는 상수가 아니라 리터럴 문자열이라, 상수만 바꾸면 `test_valid_fixture_has_no_violations`(L71) 포함 VALID_DOC 기반 전 테스트가 `MANAGER_KEY_MISMATCH` 로 무너진다** — 가장 촘촘한 결합.
- **한국어 관리자 선언구**(`MANAGER_DECL_RE` = `관리자(단독 쓰기 권한)` L31): 이 정확한 구가 의미검사(F1/F8)의 트리거. `TestManagerDeclChecks` 5건이 선언 유무로 발동/비발동을 단언(L365 `test_no_manager_key_check_without_declaration`, L380 `test_no_handoff_check_without_declaration`).
- **토큰 형식 6-hex**(`TOKEN_RE` L18): `test_roster_token_invalid`(L107, `zzzzzz`→INVALID 단언)가 직접 의존. 픽스처 토큰 `abc123`/`def456`(13곳)이 전부 6-hex 라 형식을 넓히면 baseline 재검증 필요.
- **상태 어휘**(`VALID_STATUSES` L20): `test_board_invalid_status`(L126, `FINISHED`=무효 단언)·`test_decoy_column_does_not_shadow_real_status`(L581, `FINISHED` 무효). 픽스처가 `DONE`/`TODO`, 보드 스모크 `board-set ... REVIEW`(L667)에 의존.
- **한국어 열 헤더**(`슬롯/확인토큰/세션키/ID/담당 슬롯/상태/이어받음/경로 패턴/쓰기 소유`, 41곳): `_governed_tables` 가 정확일치로 표를 식별. `test_decoy_column_does_not_shadow_real_status`(L581, `상태` vs `상태요약` 정확일치)·`TestMultipleTable` 6건(governed=필요열 보유 판정)이 헤더 문자열에 직접 걸림.
- **절 번호/제목**(`2.세션명부/3.작업보드/4.핸드오프로그/6.파일소유권`): `test_subsection_4_5_not_counted_as_section_4`(L403)·`TestDuplicateSection` 3건이 번호에 의존, 다수 테스트가 `.replace("## 2.", …)` 로 절을 조작.
- **소유자 리터럴**(`ADMIN_OWNER_LITERALS`={해당 슬롯,미배정} L21 + `관리자` startswith): `test_admin_owner_literals_accepted`(L155, 상수 import)·`test_protected_owner_manager_prefix_passes`(L534, `관리자(클로)`).
- **보호경로**(`AIMEM.md/CLAUDE.md/AGENTS.md`): `TestProtectedAndGlobOwnership` 의 PROTECTED 3건(L528/536).

### Q2. "템플릿화 됐다" 의 실행가능한 완료조건 (말 안 받음 — 픽스처로 못박음)
현재 `lint_text(text)` 는 **인자가 text 하나뿐**(L513), 모든 설정이 모듈 상수/함수 내부 한국어 리터럴. 따라서 완료조건 = **"설정 주입 경로가 실제로 존재하고, 다른 설정의 문서가 통과한다"** 를 코드로 증명하는 것:
1. **다른-설정 통과 픽스처**: 영어 헤더(`Slot|Token|…`)·영어 절 제목·다른 관리자 세션키(예 `agent:x:y:z`)·다른 토큰 형식(예 8-hex)·다른 상태어휘(예 `OPEN/CLOSED`)로 짠 `ALT_CONFIG_DOC` 를 만들고, 그 설정을 주입한 린터가 `lint_text(ALT_CONFIG_DOC, config=alt) == []` 를 단언. **지금 구조에선 불가**(config 인자 없음) → 이것이 곧 미충족 증거.
2. **한국어 baseline 회귀**: 같은 API 로 기존 `VALID_DOC` 를 **기본 설정(config=None)** 으로 돌려 여전히 `[]`. 즉 설정화가 현행 문서를 깨지 않음을 못박음.
3. **교차 거부**: 한국어 문서를 영어 설정으로, 영어 문서를 한국어 설정으로 린트하면 헤더/절을 못 찾아 `*_TABLE_MISSING`·`*_SECTION_MISSING` 이 뜬다 — 설정이 실제로 파싱을 가른다는 양성대조.
4. **상수→설정 이관 완결성**: `test_no_module_level_hardcoded_manager_key` 류로, 관리자키·상태어휘·헤더·토큰정규식이 **모듈 최상위 상수로 남아있지 않고** config 로부터 온다는 것을 단언(회귀로 재하드코딩 차단).
→ 이 4종이 다 초록이면 "템플릿화 됐다". 하나라도 XFAIL/불가면 미완.

### Q3. 지금 테스트 구조에서 그 판정을 세울 수 있나 — **부분만. 격리 인프라는 있으나 주입점이 없다**
- **있는 것**: `tempfile.mkdtemp` 기반 임시 디렉터리 격리가 이미 둘(`TestMainExitCodes.setUp` L162, `TestBoardSmoke.setUp` L676) — 파일 단위 실험은 바로 가능. `lint_text` 는 순수함수라 픽스처 문자열만 있으면 in-memory 로 충분.
- **없는 것(막힘)**: `lint_text`/`lint_file`/체크함수들이 **config 인자를 받지 않는다.** 관리자키·헤더·절번호·토큰형식·상태어휘가 `_check_roster`/`_check_board`/`_check_ownership` 내부에 한국어 리터럴로 박혀 있어(L276·288·347·360·445·457 등), 테스트가 설정을 **주입할 지점이 없다.** Q2 의 1·3·4 는 이 주입점(예: `LintConfig` 데이터클래스 + `lint_text(text, config=...)`)이 S1 쪽 린터에 먼저 생겨야 작성 가능하다. **그래서 이 라운드 순서는 S1(린터 설정화) → S2(설정화 테스트)가 맞다** — 테스트가 먼저 갈 수 없다. 지금 S2 가 할 수 있는 건 Q2 의 픽스처·기대값을 **XFAIL 스켈레톤**으로 먼저 박아 두는 것(주입점 생기면 초록 전환).

### Q4. 회귀 위험이 큰 지점 (미리)
- **VALID_DOC L29 의 리터럴 관리자키**: 상수만 config 로 옮기고 픽스처 L29 를 안 고치면 VALID_DOC 기반 ~40+ 테스트가 일제히 `MANAGER_KEY_MISMATCH` — 가장 광범위한 회귀. 픽스처 생성을 config 에서 파생시켜야(하드리터럴 금지).
- **`_col_index` 정확일치(L88)**: 헤더를 설정화하며 부분일치로 되돌리면 `test_decoy_column_does_not_shadow_real_status`(F7 방어)가 뚫린다 — 디코이 열 은닉 재발.
- **`_find_section` 번호 매칭(L100 `{number}\.\s`)**: 절 제목을 설정화할 때 `4.` vs `4.5` 경계(L403)와 `## 4.` 정확+공백 규칙을 유지 못하면 `SIZE_HANDOFF_LOG`·`DUPLICATE_SECTION` 경계가 어긋난다.
- **`_governed_tables` 필요열 판정(L247)**: 헤더를 설정화하면 FP2/FP3(정당한 둘째 표 통과)와 디코이 검출이 같은 헤더집합에 의존 — 설정별로 governed 헤더가 갈리면 둘 다 재검증 필요.
- **토큰 정규식 확장**: 6-hex→가변형식 시 `ROSTER_DUPLICATE_TOKEN`(유일성)은 형식과 무관하게 유지돼야 하는데, 정규식 교체가 유일성 검사까지 건드리면 조용히 약화될 수 있다.
- **`aimem_board.py` 동반 파손(T-024 재발)**: board 가 `find_section/extract_table` 공개 API 로 절·표를 찾으므로(L601 주석), 헤더/절 설정화가 board 의 갱신 CLI 를 깬다. `TestBoardSmoke` 9개 하위명령이 안전망이나, board 도 같은 config 를 받게 해야 산출물이 린트를 통과한다.

---

<!-- 이전 보고는 .aimem/archive/outbox-S2-2026-09.md 로 이관됨 (2026-09-11 관리자). 새 보고는 파일 맨 위에 prepend -->
