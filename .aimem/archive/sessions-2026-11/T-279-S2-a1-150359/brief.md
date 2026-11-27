SLOT=S2 T-279 ui.js: 자모 자판(Shift)·e.code 입력·조합 미리보기·날마다/연습 모드 (G-056)
확인토큰: d27e93
AIMEM REV: 170
너는 S2 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: projects/자모맞히기/web/js/ui.js
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.

# T-279 `web/js/ui.js` 를 자모맞히기로

쓸 파일은 **하나**: `projects/자모맞히기/web/js/ui.js`. 지금은 **웹워들 ui.js 를 그대로 복사한 것**입니다. `index.html`·`style.css`·`storage.js`·`game.js`·`jamo.js`·`words.js` 는 앞 노드들이 이미 바꿔 두었습니다 - 읽기만. **바로 파일을 고치십시오.** 웹워들의 흐름(뒤집기·흔들기·토스트·창·통계·공유·설정·새 날 감지·이어 하기)은 그대로 둡니다.

먼저 `.aimem/graph/inputs/r24/CONTRACT.md` 의 '화면' 절을 읽으십시오. 그 절이 할 일 목록입니다. 요약:

1. `import { KEY_ROWS, KEYMAP, SHIFTED, toUnits, composeUnits } from './jamo.js'`. 웹워들의 `KEY_ROWS` 상수는 지웁니다. `ALLOWED`·`ANSWERS` 는 한글 낱말이므로 게임에는 칸 문자열을 줍니다: `ALLOWED_SET = new Set(ALLOWED.map(toUnits))`, `WORD_OF = new Map(ALLOWED.map(w => [toUnits(w), w]))`, 정답은 `toUnits(answerForDate(now, ANSWERS))`.
2. `buildKeyboard`: 1줄 `KEY_ROWS[0]` / 2줄 `shift` 키(`⇧`, `aria-label="쌍자음"`, `aria-pressed`) + `KEY_ROWS[1]` (spacer 없음) / 3줄 `enter`(글자 `입력`) + `KEY_ROWS[2]` + `back`. 자모 키 `data-key` 는 보통 글자.
3. Shift 한 번: `shiftOn` 상태. shift 키를 누르면 뒤집고, `#keyboard` 의 `data-shift` 를 `on`/없음, SHIFTED 일곱 키의 글자·aria-label 을 쌍 꼴로. 자모 키가 눌리면 shiftOn 이면 `SHIFTED[id] ?? id` 를 넣고 Shift 를 끔. `renderKeyboard` 는 키에 **지금 보이는 글자**의 상태를 `data-state` 로.
4. 실물 자판: 웹워들의 `/^[a-zA-Z]$/.test(e.key)` 갈래를 `KEYMAP[e.code]` 로 바꿈 → `e.shiftKey ? 쌍 : 보통` 을 그대로 넣음(화면 Shift 상태와 무관, 넣은 뒤 화면 Shift 도 끔). Enter/Backspace/Escape·Ctrl/Alt/Meta 무시·포커스 처리는 웹워들 그대로. 자모를 넣었으면 `e.preventDefault()`.
5. `#preview`: 지금 줄을 바꿀 때마다(`renderCurrentRow`·`renderAll`·제출 뒤) `composeUnits(game.current)`. 끝난 판이면 빈 글.
6. 정답을 보일 때(`정답: …` 토스트 두 곳) `WORD_OF.get(game.answer) ?? composeUnits(game.answer)`. `toUpperCase` 는 모두 뺌. 타일 aria-label 은 그 자모 그대로.
7. 모드: `mode = 'daily'|'practice'`, `dailyGame`·`practiceGame` 을 따로 들고 `game` 은 지금 모드의 것. `#mode-daily`/`#mode-practice` 클릭(뒤집기 중이면 무시) → 그 모드로, `aria-pressed` 갱신, `#btn-new.hidden = mode !== 'practice'`, `renderAll()`. 연습 판이 없거나 끝났으면 새로: `puzzleNumber 0`, 정답 `toUnits(ANSWERS[Math.floor(Math.random()*ANSWERS.length)])`. `#btn-new` → 새 연습 판. **연습 판은 `saveDaily`·`recordResult` 를 부르지 않음**(submit 안에서 `mode === 'daily'` 일 때만). 날마다는 `puzzleNumber = dailyIndex(now) + 1`. 통계 창의 공유 단추는 지금 판의 `shareText()`. `checkNewDay` 는 날마다 판만 새로 시작.
8. 문구: `새로운 날, 새로운 단어!` → `새로운 날, 새로운 낱말!`. 그 밖의 '단어' → '낱말'.

## 스스로 확인

`python3 .aimem/graph/inputs/r24/v_smoke.py` 가 마지막 줄 `통과 N / 전체 N` (엔진의 검증도 이것; 관리자 스크립트 - 고치지 마십시오). 실패 줄이 무엇을 기대하는지 읽고 ui.js 를 고치십시오. **index.html·style.css 쪽 결함이라 ui.js 로는 못 고치면** 첫 줄 `NEEDS-FIX: <무엇이 어디서>` 로 보고하십시오.

## 하지 말 것

다른 파일 쓰기, `git commit`/`push`, 파일 삭제, 의존성 설치, 운영 모니터 부르기.

보고 첫 줄은 `DONE` / `PARTIAL` / `BLOCKED` / `NEEDS-FIX: …`, 그다음 v_smoke 마지막 줄.
