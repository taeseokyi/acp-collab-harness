SLOT=S3 T-289 ui.js: 끝난 연습 판을 모드 오가기에서 버리지 않음 (T-287 NEEDS-FIX, R24-N5 잔여) (G-058)
확인토큰: 5b8c1e
AIMEM REV: 170
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: projects/자모맞히기/web/js/ui.js
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.

# T-289 끝난 연습 판을 모드 오가기에서 버리지 않기 (T-287 이 찾은 결함)

쓸 파일은 **하나**: `projects/자모맞히기/web/js/ui.js`. 다른 파일은 읽기만. **바로 파일을 고치십시오.**

## 결함

연습에서 진(또는 이긴) 판 → `#mode-daily` → `#mode-practice` 로 돌아오면 **빈 새 연습 판**이 뜨고 정답 토스트도 없습니다. 원인: `selectMode` (551행 근처) 의 `if (!practiceGame || practiceGame.status !== 'playing') startPractice();`. 약속(`.aimem/graph/inputs/r24/CONTRACT.md` '화면' 절)은 "모드를 바꾸면 그 모드의 판을 보여 줌 - 연습 판도 마찬가지" 입니다. (관리자의 앞 브리프가 '끝났으면 새로' 라고 잘못 적었습니다 - 약속이 맞습니다.)

## 고칠 것

- 연습 판은 **없을 때만** 새로 만듭니다(`if (!practiceGame) startPractice();`). 끝난 연습 판은 그대로 보여 주고, 진 판이면 그 판의 정답 토스트를 다시 띄웁니다(이미 있는 `showAnswerToast()` 흐름). 새 연습 판은 `#btn-new` 로만.
- 다른 동작은 바꾸지 마십시오.

## 스스로 확인 (엔진의 검증도 이것)

`python3 projects/자모맞히기/tests/browser_modes.py` 전부 통과(지금 60/62 - 실패 둘이 이 결함), `python3 projects/자모맞히기/tests/browser_game.py` 전부 통과, `python3 .aimem/graph/inputs/r24/v_modes.py` 전부 통과. 시험 파일·관리자 스크립트는 고치지 마십시오.

## 하지 말 것

다른 파일 쓰기, `git commit`/`push`, 파일 삭제, 의존성 설치, 운영 모니터 부르기.

보고 첫 줄은 `DONE` / `PARTIAL` / `BLOCKED`, 그다음 세 검사의 마지막 줄.
