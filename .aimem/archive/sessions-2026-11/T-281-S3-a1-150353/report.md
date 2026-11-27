DONE

# tests 49 · # pass 49 · # fail 0

한 일
- `projects/자모맞히기/tests/test_jamo.mjs` 새로 씀 (19 tests): UNITS 33글자, SHIFTED 일곱 쌍, KEYMAP 26키/UNITS 안/Shift 꼴 일치, KEY_ROWS↔KEYMAP 보통 글자 집합 일치, toUnits(쌍자음·ㅐㅔㅒㅖ·겹모음 7·겹받침 11·null 입력), composeUnits(왕복·입력 중·받침 넘어가기·낱자·빈 문자열·겹 합치기), words.js ALLOWED/ANSWERS 6칸·왕복(import 실패 시 건너뛰지 않고 그대로 실패).
- `projects/자모맞히기/tests/test_game.mjs` 웹워들 복사본을 자모 판으로 고쳐 씀 (30 tests): 상수 6/6, scoreGuess(겹침은 남은 개수만큼만 present·초록 우선·길이 예외), keyboardState, hardModeViolation 일곱 갈래, addLetter 거절(`a`/`ㅘ`/`ㄳ`/`가`)·7칸 거절, submit 문구 두 가지, 진행/이김/끝난 판, 지는 판, shareText(날마다·연습·진 판 X/6·하드 `*`), 저장·복원(왕복, scores 재판정, 손상값 거절 9종, current 자모 아닌 글자 제거), dailyIndex 2026-11-13→0/다음 날→1, answerForDate.

고친 파일
- `projects/자모맞히기/tests/test_jamo.mjs` (신규)
- `projects/자모맞히기/tests/test_game.mjs` (전면 교체)
- 제품 파일은 읽기만 함. 삭제·commit·push·의존성 설치 없음.

실제로 돌린 검증
- `node --test projects/자모맞히기/tests/test_jamo.mjs projects/자모맞히기/tests/test_game.mjs`
- 출력: `tests 49 / pass 49 / fail 0 / skipped 0`
- 파일별: test_jamo 19 pass, test_game 30 pass.

다음 담당자가 알아야 할 것
- 제품 결함은 발견하지 못함(`web/js/jamo.js`, `web/js/game.js`, `web/js/words.js` 모두 시험 통과). `NEEDS-FIX` 없음.
- `test_jamo.mjs` 는 `words.js` 를 정적 import 하므로 생성물이 없거나 깨지면 곧바로 실패한다(의도된 동작).
- 브라우저/화면 시험은 이 작업 범위 밖이며 돌리지 않았다.