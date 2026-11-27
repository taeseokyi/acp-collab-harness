DONE
통과 24 / 전체 24

**고친 파일**
- `projects/자모맞히기/web/js/ui.js`만 수정했습니다.

**한 일**
- `jamo.js`의 `KEY_ROWS`·`KEYMAP`·`SHIFTED`·`toUnits`·`composeUnits`를 사용하도록 바꿨습니다.
- 자판을 3줄 구조로 다시 만들었습니다: `KEY_ROWS[0]` / `⇧` + `KEY_ROWS[1]` / `입력` + `KEY_ROWS[2]` + `⌫`.
- 화면 Shift는 한 번만 유지되고, 자모 입력 뒤 꺼지며 `#keyboard[data-shift="on"]`, `aria-pressed`, 일곱 키의 표시 글자를 갱신합니다.
- 실물 자판은 `e.code`와 `KEYMAP`을 사용하고 `e.shiftKey`로 쌍자음을 넣습니다.
- `#preview`에 현재 줄의 `composeUnits(game.current)`를 표시하고, 끝난 판은 빈 글입니다.
- 정답 안내는 `WORD_OF.get(...) ?? composeUnits(...)`로 낱말 형태이며, 타일은 자모 그대로 표시합니다.
- 날마다/연습 모드를 분리했습니다. 연습 판은 저장·통계를 남기지 않고 `새 판`으로 다시 시작합니다.
- `새로운 날, 새로운 낱말!` 문구로 바꿨고, 남은 `단어`·`toUpperCase` 흔적을 제거했습니다.

**검증**
- `python3 .aimem/graph/inputs/r24/v_smoke.py` → `통과 24 / 전체 24`, 실패 없음.
- `python3 -m unittest discover -s projects/자모맞히기/tests` → `Ran 8 tests`, `OK`.
- `node projects/자모맞히기/tests/test_jamo.mjs` → 19/19 통과.
- `node projects/자모맞히기/tests/test_game.mjs` → 30/30 통과.
- `node projects/자모맞히기/tests/test_storage.mjs` → 12/12 통과.
- 추가 브라우저 확인: 진 판의 토스트가 `정답: 학력`으로 나왔고, 연습 제출 뒤 localStorage에는 `jamo.seenHelp`만 남았습니다.

**다음 담당자에게**
- `ui.js`는 현재 git에서 untracked(`??`) 상태이며, 금지 규칙에 따라 commit/push는 하지 않았습니다.
- `index.html`·`style.css` 쪽 결함은 발견되지 않았고, v_smoke 기준 화면 배치도 두 뷰포트에서 통과했습니다.