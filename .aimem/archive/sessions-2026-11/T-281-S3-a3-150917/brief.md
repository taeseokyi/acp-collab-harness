SLOT=S3 T-281 단위 검사: test_jamo.mjs 새로 + test_game.mjs 를 자모로 (G-056)
확인토큰: 5b8c1e
AIMEM REV: 170
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: projects/자모맞히기/tests/test_jamo.mjs, projects/자모맞히기/tests/test_game.mjs
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.

# T-281 로직 단위 검사

쓸 파일: `projects/자모맞히기/tests/test_jamo.mjs` (새 파일), `tests/test_game.mjs` (지금은 **웹워들 시험을 복사한 것** - 자모로 고쳐 씀). 제품(`web/js/*.js`)은 **읽기만**. **바로 파일을 쓰십시오.**

먼저 `.aimem/graph/inputs/r24/CONTRACT.md` 의 '칸(unit) 규칙'·'jamo.js'·'game.js' 절을 읽으십시오. 시험은 **그 약속**을 봅니다(구현을 베끼지 말 것). `node:test` + `node:assert/strict`, 의존성 없음.

## test_jamo.mjs (15개 이상)

- `toUnits`: 쌍자음 한 칸(`까닭`), ㅐㅔㅒㅖ 한 칸(`얘기`), 겹모음 일곱 각각 두 칸(`과 괘 괴 궈 궤 귀 의`), 겹받침 열하나 각각 두 칸(`넋 앉 않 닭 삶 넓 곬 핥 읊 앓 값`), 음절 아닌 입력 null(`''`, `'abc'`, `'ㄱ'`, `'한 국'`).
- `composeUnits`: 모든 위 낱말의 되돌림(`composeUnits(toUnits(w)) === w`), 입력 중 꼴(`'ㅎㅏㄴㄱ'`→`'한ㄱ'`), 받침 넘어가기(`'ㄷㅏㄹㄱㅏ'`→`'달가'`, `'ㄱㅏㅂㅅㅣ'`→`'갑시'`), 낱자(`'ㄱㄱ'`, `'ㅏ'`), 빈 문자열.
- `KEYMAP` 26키·`SHIFTED` 일곱·`KEY_ROWS` 의 모든 글자가 `UNITS` 안이고 KEYMAP 의 보통 글자 집합과 같음.
- `words.js` 가 있으면(`import` 실패 시 건너뜀은 **하지 말 것** - T-277 이 이미 만듦) ALLOWED 모든 낱말이 6칸이고 되돌림이 같음.

## test_game.mjs (웹워들 시험 꼴 그대로, 20개 이상)

- 영어 낱말을 6칸 칸 문자열로 바꿔 씁니다(예 `crane` → `'ㅎㅏㄴㄱㅜㄱ'`, `slate` → `'ㄲㅏㄷㅏㄹㄱ'` 처럼 - 낱말은 당신이 고름). 겹치는 자모 판정(정답에 남은 개수만큼만 present), 키 상태, 하드 모드(웹워들 시험의 갈래 모두), 판 진행, 지는 판, 공유 글(날마다 `자모맞히기 N k/6`, 연습 `자모맞히기 연습 k/6`, 진 판 `X/6`, 하드 `*`), 저장과 복원(손상된 저장값 거절 포함), 날짜(`dailyIndex` 2026-11-13 → 0, 다음 날 1), 자모 아닌 입력 거절(`a`, `ㅘ`, `ㄳ`, `가`), 실패 문구(`자모 6개를 채워 주세요`, `낱말 목록에 없는 낱말입니다`).

## 제품 결함을 찾으면

제품도 시험도 고치지 말고 보고 첫 줄을 `NEEDS-FIX: <무엇이 어디서>` 로. 실패하는 시험은 그대로 두십시오.

## 스스로 확인

`node --test projects/자모맞히기/tests/test_jamo.mjs projects/자모맞히기/tests/test_game.mjs` (엔진은 '돌았고 시험이 35개 이상인가' 를 봅니다).

## 하지 말 것

제품 파일 쓰기, `git commit`/`push`, 파일 삭제, 의존성 설치, 운영 모니터 부르기.

보고 첫 줄은 `DONE` / `PARTIAL` / `BLOCKED` / `NEEDS-FIX: …`, 그다음 `# tests`·`# pass` 수.

[재시도 3/3] 직전 시도(run T-281-S3-a2-150724) 는 rc=0 / 검증 rc=1 로 실패했다. 산출물이 남아 있을 수 있으니 먼저 확인하고 이어서 하라. 직전 검증 출력 꼬리:
node: 통과 0 / 전체 0 (최소 35)


직전 작업자의 보고(참고만 하라 - 틀렸을 수 있으니 그대로 믿지 말고 직접 확인하라):
시도 산출물이 이미 남아 있었고, 두 파일 모두 계약(r24 CONTRACT.md)과 지시 항목을 충족하는 상태였습니다. 새로 고칠 필요 없이 그대로 검증했습니다.
- 이전 검증의 `통과 0 / 전체 0` 은 재현되지 않았습니다. 파일 작성이 끝나기 전에 검증이 돌았던 것으로 보입니다.

고친 파일
- `projects/자모맞히기/tests/test_jamo.mjs` (신규, 19 tests)
- `projects/자모맞히기/tests/test_game.mjs` (웹워들 복사본을 자모 판으로 교체, 30 tests)
- 제품 파일(`web/js/*.js`)은 읽기만 함. commit/push/삭제/의존성 설치 없음.

실제로 돌린 검증
- `node --test projects/자모맞히기/tests/test_jamo.mjs projects/자모맞히기/tests/test_game.mjs`
- 출력: `tests 49 / pass 49 / fail 0 / cancelled 0 / skipped 0`

다음 담당자가 알아야 할 것
- 제품 결함 발견 없음. `NEEDS-FIX` 없음.
- `test_jamo.mjs` 는 `web/js/words.js` 를 정적 import 하므로 생성물이 없거나 깨지면 즉시 실패합니다(의도된 동작).
- 커버리지: `toUnits`/`composeUnits`(겹모음 7·겹받침 11·받침 넘어감·낱자), `UNITS`/`SHIFTED`/`KEYMAP`/`KEY_ROWS`, ALLOWED·ANSWERS 6칸/왕복, 점수·키 상태·하드 모드 7갈래, addLetter 거절, submit 문구, 진행/승/패, shareText 4종, 저장·복원 및 손상값 거절, dailyIndex/answerForDate.
- 브라우저·화면 시험은 범위 밖이라 돌리지 않았습니다.
