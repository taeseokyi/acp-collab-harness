DONE
# tests 49 · # pass 49

**한 일**
- 재시도 산출물(`test_jamo.mjs` 19 tests, `test_game.mjs` 30 tests)이 이미 남아 있어 먼저 계약(`r24/CONTRACT.md`의 칸 규칙·jamo.js·game.js 절)과 지시 항목에 비추어 직접 검토했습니다.
- 두 파일 모두 요구 항목을 충족해 **고친 파일 없음**(제품 `web/js/*.js`도 읽기만).

**검증(실제로 돌린 명령과 출력)**
- `node --test projects/자모맞히기/tests/test_jamo.mjs projects/자모맞히기/tests/test_game.mjs`
  → `ℹ tests 49 / ℹ pass 49 / ℹ fail 0`, rc=0 (3회 반복 모두 동일)
- 파일별: `test_jamo` 19 pass/19, `test_game` 30 pass/30
- 엔진 모사: 출력 파일 + `python3 .aimem/graph/inputs/r24/count.py <out> node 35 all`
  → `node: 통과 49 / 전체 49 (최소 35, 전부 통과 요구)`, rc=0

**직전 0/0 진단**
- 현재 재현되지 않습니다. node는 **존재하지 않는 경로를 조용히 건너뛰고** `tests 0`으로 rc=0을 낼 수 있음을 실험으로 확인했습니다. 직전 검증 시점(15:07:24)에는 `web/js/words.js`(mtime 15:09)와 파일 기록이 끝나지 않아 경로가 비어 있었던 것으로 보입니다.
- 현재 `words.js`는 ANSWERS 398 / ALLOWED 1032로 존재하고, 경로는 모두 NFC로 일관됩니다.

**다음 담당자가 알아야 할 것**
- 제품 결함 발견 없음 → `NEEDS-FIX` 없음.
- `test_jamo.mjs`는 `web/js/words.js`를 정적 import하므로 생성물이 없거나 깨지면 즉시 실패합니다(의도). `words.js`를 다시 만드는 슬롯과 동시에 검증하면 경합할 수 있습니다.
- 커버리지: toUnits/composeUnits(겹모음 7·겹받침 11·받침 넘어감·낱자·빈 문자열·null), UNITS/SHIFTED/KEYMAP/KEY_ROWS, ALLOWED 6칸·왕복, 점수(잔여 개수 present)·키 상태·하드 모드 8갈래·진행/승/패·addLetter 거절·submit 문구·shareText 4종·저장/복원 및 손상값 거절·dailyIndex/answerForDate.
- 브라우저·화면 시험은 범위 밖이라 돌리지 않았습니다.