DONE
- 고친 파일: `projects/자모맞히기/web/js/ui.js` — `selectMode`의 554행 조건을 `if (!practiceGame || practiceGame.status !== 'playing') startPractice();` → `if (!practiceGame) startPractice();`로 변경. 끝난 연습 판은 그대로 보이고, `game=practiceGame` 후 기존 `clearAnswerToast()`/`showAnswerToast()` 흐름이 진 판의 정답 토스트를 다시 띄움. 새 판은 `#btn-new`로만.
- 검증 (실제 실행):
  - `python3 projects/자모맞히기/tests/browser_modes.py` → `통과 62 / 전체 62` (직전 60/62)
  - `python3 projects/자모맞히기/tests/browser_game.py` → `통과 121 / 전체 121`
  - `python3 .aimem/graph/inputs/r24/v_modes.py` → `통과 8 / 전체 8`
- 다음 담당자: 쓰기 범위(소유 경로) 내 이 파일 한 곳만 변경함. git commit/push 안 함. 시험 파일·관리자 스크립트 무수정.