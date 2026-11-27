SLOT=S3 T-285 ui.js 모드 오가기 정리: Enter·정답 토스트·통계 타이머·뒤집기 중 입력·하드 모드·날짜 번호 (R24-N4·N5·N6·N7·N8·N13) (G-057)
확인토큰: 5b8c1e
AIMEM REV: 170
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: projects/자모맞히기/web/js/ui.js
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.

# T-285 `web/js/ui.js` 모드 오가기 결함 (R24-N4·N5·N6·N7·N8·N13)

쓸 파일은 **하나**: `projects/자모맞히기/web/js/ui.js`. 다른 파일은 읽기만. **바로 파일을 고치십시오.**

근거: `rounds/R24/REVIEW-r24.md` 2절의 N4~N8·N13 행(재현 방법·고칠 방향이 적혀 있음 - 그 여섯 행만 읽으면 됩니다). 화면 약속은 `.aimem/graph/inputs/r24/CONTRACT.md` '화면' 절.

## 고칠 것

- **N4** 모드 단추·`#btn-new` 에 포커스가 있을 때 Enter 가 추측 제출로 새어 나감 → keydown 의 Enter 갈래에서 포커스가 `button`(화면 자판 단추 포함)이면 그 단추에 맡김(`t.closest('.header, #modes')` 를 넓히거나 `activeElement` 가 `button` 이면 return).
- **N5** 진 판의 `정답: …` 토스트(시간 0)가 모드 바꿈·새 판 뒤에도 남음 → 모드를 바꾸거나 새 판을 열면 그 토스트를 지우고, 바뀐 판이 진 판이면 **그 판의** 정답만 다시 띄움.
- **N6** `endTimer` 가 모드 바꿈·새 판에서 취소되지 않아 다른 모드 위에 통계 창이 열림 → `selectMode`·`#btn-new` 에서 `clearTimeout(endTimer)`. 통계 창의 막대 강조(`hl`)는 `mode === 'daily'` 일 때만.
- **N7** 실물 자판 글자 입력이 `busy`(뒤집는 중)를 안 봄 → 화면 자판처럼 `handleKey` 를 거치게(또는 `if (busy) return`). 뒤집기가 끝나기 전에 자판 색이 먼저 칠해지지 않게.
- **N8** 하드 모드가 모드 사이에서 어긋남 → 설정 창의 하드 모드 체크박스는 **지금 판의 값**을 보여 줌(모드를 바꾸면 그 판 값으로 맞춤). 판이 시작된 뒤(줄 ≥1)에는 잠김(웹워들 그대로). 바꿀 수 있을 때 바꾸면 **지금 판만** 그 값으로 다시 만들고(친 칸 유지) 설정에 저장. 날마다 판을 새로 만들 때(빈 판)는 저장된 설정을 따름. 새로 고침 뒤 설정이 말없이 꺼지지 않게.
- **N13** 기기 시계가 2026-11-13 보다 앞이면 날마다 판 번호가 0 이하가 되어 공유 글이 `연습` 으로 나옴 → 날마다 `puzzleNumber = Math.max(1, dailyIndex(now) + 1)`.

다른 동작은 바꾸지 마십시오(웹워들 흐름 유지).

## 스스로 확인

`python3 .aimem/graph/inputs/r24/v_modes.py` 와 `python3 .aimem/graph/inputs/r24/v_smoke.py` 가 모두 `통과 N / 전체 N`, `python3 projects/자모맞히기/tests/browser_game.py` 도 전부 통과(회귀 없음). 셋 다 엔진의 검증입니다. 관리자 스크립트(`.aimem/graph/inputs/r24/*`)는 고치지 마십시오.

## 하지 말 것

다른 파일 쓰기(시험은 다음 노드가 씁니다), `git commit`/`push`, 파일 삭제, 의존성 설치, 운영 모니터 부르기.

보고 첫 줄은 `DONE` / `PARTIAL` / `BLOCKED` / `NEEDS-FIX: …`, 그다음 세 검사의 마지막 줄.
