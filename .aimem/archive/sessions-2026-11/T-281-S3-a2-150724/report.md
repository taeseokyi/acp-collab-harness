DONE
# tests 49 / # pass 49

확인 사항
- 직전 시도 산출물이 이미 남아 있었고, 두 파일 모두 계약(r24 CONTRACT.md)과 지시 항목을 충족하는 상태였습니다. 새로 고칠 필요 없이 그대로 검증했습니다.
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