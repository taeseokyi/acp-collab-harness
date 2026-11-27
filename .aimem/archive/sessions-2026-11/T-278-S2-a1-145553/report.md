DONE
game: 모두 통과

**한 일**
`projects/자모맞히기/web/js/game.js`만 수정했습니다. API·export·Game 메서드/getter·판정 규칙·저장 복원 방어는 그대로 두고 다음을 바꿨습니다.

- `WORD_LENGTH` 5 → 6
- 파일 안에 33글자 `UNITS` 상수를 두고 `LETTER`/`WORD`/`CURRENT` 정규식을 자모 기준으로 변경 (`import` 없음)
- `EPOCH_UTC = Date.UTC(2026, 10, 13)` — 2026-11-13이 0, 11-14가 1
- 실패 문구: `자모 6개를 채워 주세요`, `낱말 목록에 없는 낱말입니다`
- 하드 모드 문구에서 `toUpperCase()` 제거, `1번째 칸은 ㄴ 이어야 합니다` 형태로 변경
- 오류 메시지의 `a-z` → `자모`
- `shareText`: `puzzleNumber > 0`이면 `자모맞히기 N n/6`, 0이면 `자모맞히기 연습 n/6`
- `fromJSON`의 정답·추측·`current` 검사를 UNITS 기준으로 변경

**검증**
```bash
python3 tools/aimem_db.py check --slot S2 --token d27e93 --rev 170
# 일치 ... 소유 경로에 projects/자모맞히기/web/js/game.js 포함

node .aimem/graph/inputs/r24/v_game.mjs
# game: 모두 통과
# rc=0
```

**다음 담당자에게**
- `tests/test_game.mjs`는 아직 웹워들 시험이라 깨지는 것이 정상이며, 지시대로 고치지 않았습니다.
- `git status`의 `.aimem/requests/Q-261113-bd56.json`, `AIMEM-state.md`, `rounds/R24/` 변경은 제 작업 전부터 있던 상태이며 건드리지 않았습니다. 커밋·삭제·설치도 하지 않았습니다.