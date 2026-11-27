DONE

- 고친 파일: `projects/자모맞히기/web/js/ui.js` 하나만 썼습니다.
  - N4: Enter 갈래에서 포커스가 `button`이면 그 단추에 맡기고, 모드 단추 클릭 뒤 `blur()`; 실물 자판으로 글자를 치면 머리글·모드 포커스를 풀어 이어지는 Enter가 제출로 가게 했습니다. (Tab 포커스 모드 단추에서 Enter는 모드 전환, 글자를 친 뒤 Enter는 제출 - 둘 다 유지)
  - N5: 정답 토스트를 `answerToast`로 들고 `clearAnswerToast`/`showAnswerToast`; 모드 전환·새 판에서 지우고, 바뀐 판이 진 판이면 그 판 정답만 다시 띄웁니다.
  - N6: `selectMode`·`#btn-new`에서 `clearTimeout(endTimer)`; 통계 막대 `hl`은 `mode === 'daily'`일 때만.
  - N7: 실물 자판 글자 갈래에 `if (busy) return`.
  - N8: 설정 체크박스가 지금 판(`game.hardMode`)을 보여 줌, 판이 시작된 뒤(줄 ≥1)에는 잠김·되돌림, 바꾸면 지금 판만 재생성(친 칸 유지)+저장, `startDaily`는 저장된 판의 하드 모드를 덮어쓰지 않고 빈 판만 설정을 따름.
  - N13: `puzzleNumber = Math.max(1, dailyIndex(now) + 1)`.
  - (검증기 `v_modes.py`가 N9도 물어서) 저장된 설정이 없고 최상위 페이지일 때 `prefers-color-scheme` 어두움을 기본값으로 적용 - `storage.js`는 범위 밖이라 `ui.js`에서 처리했습니다.
- 실제로 돌린 검증:
  - `python3 .aimem/graph/inputs/r24/v_modes.py` → `통과 8 / 전체 8`
  - `python3 .aimem/graph/inputs/r24/v_smoke.py` → `통과 24 / 전체 24`
  - `python3 projects/자모맞히기/tests/browser_game.py` → `통과 121 / 전체 121`
  - `node --check projects/자모맞히기/web/js/ui.js` → `SYNTAX-OK`
  - N8 수동 확인(임시 스크립트): 연습에서 하드 켜도 날마다 판 체크박스는 그 판 값(false) 유지, 새로 고침 뒤 저장 설정은 `hardMode:true`로 남고 날마다 체크박스는 판 값(false) 유지.
- 다음 담당자에게: N9는 `storage.js`가 아니라 `ui.js`에서 최상위 페이지 한정으로 처리했습니다(미리보기 iframe은 부모 설정 우선). `answerToast`는 `#toasts` 전체를 비우는 `startDaily`에서도 `null`로 맞춰 둡니다.