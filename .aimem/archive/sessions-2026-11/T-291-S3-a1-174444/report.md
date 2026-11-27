DONE

## 한 일
- **N4 수정 (`ui.js`)**: `startDaily()`가 `#toasts`를 비운 뒤, 화면에 남아 있는 판이 진 연습 판이면 기존 `showAnswerToast()`로 그 판의 정답 토스트를 다시 띄웁니다. 날마다 모드일 때는 이전과 똑같이 새 판을 보여 줍니다(`ui.js:528-531`). 다른 동작은 건드리지 않았습니다.
- **시험 추가 (`browser_modes.py`)**: 4개 시나리오, 검사 14개(시나리오 10 + 페이지 오류 4) 추가. 기존 62개는 그대로.
  - N4: 연습 패배 → `Date`를 하루 밀고 `focus` 이벤트 → `정답:` 토스트 보임, 연습 단추 눌림 유지, 진 판 유지
  - V13: 연습 패배 직후 `#btn-new` → 2.5초 뒤 통계 창 안 보임
  - V14: 연습 승리 뒤 통계 `.bar.hl` 없음 / 날마다 승리 뒤 `.bar.hl` 1개 보임
  - V17: 저장 설정 하드=켬 + 저장된 빈 날마다 판(하드 아님)으로 새로 고침 → 첫 제출 전 `#set-hard` 체크됨, 승리 후 공유 첫 줄 `*` 끝

## 고친 파일
- `projects/자모맞히기/web/js/ui.js`
- `projects/자모맞히기/tests/browser_modes.py`

## 실제로 돌린 검증
```
$ python3 projects/자모맞히기/tests/browser_modes.py
통과 76 / 전체 76

$ python3 projects/자모맞히기/tests/browser_game.py
통과 121 / 전체 121

$ python3 .aimem/graph/inputs/r24/v_modes.py
통과 8 / 전체 8
```
변이 확인(저장소 밖 `/tmp/opencode/zamo_mut` 사본): N4 수정 제거 75/76(`N4 새 날 - 연습에서 진 판의 정답 토스트가 보임` FAIL), V13 제거 75/76, V14 제거 75/76, V17 제거 74/76 — 새 시험이 모두 잡습니다.

## 다음 담당자가 알아야 할 것
- 변이 확인용 사본이 `/tmp/opencode/zamo_mut/{n4,v13,v14,v17}`에 남아 있습니다(저장소 밖, 삭제 금지 규칙 때문에 두었음).
- `git status`상 `projects/자모맞히기/`가 untracked라 `git diff`로는 변경이 보이지 않습니다.
- 지시 범위 밖 파일은 쓰지 않았고, commit/push/삭제/설치도 하지 않았습니다.