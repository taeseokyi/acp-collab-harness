SLOT=S3 T-291 새 날에 연습 정답 토스트 유지 + 시험 빈틈 셋(#btn-new 타이머·통계 강조·빈 날마다 판 하드) (R24 재검수 N4·N6) (G-059)
확인토큰: 5b8c1e
AIMEM REV: 170
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: projects/자모맞히기/web/js/ui.js, projects/자모맞히기/tests/browser_modes.py
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.

# T-291 새 날 정답 토스트 + 시험 빈틈 (재검수 `rounds/R24/REVIEW-r24-2.md` 2절 N4·N6, 3절 V13·V14·V17)

쓸 파일: `projects/자모맞히기/web/js/ui.js`, `tests/browser_modes.py`. 다른 파일은 읽기만. **바로 파일을 고치십시오.**

## 고칠 것 (ui.js)

- **N4** 연습 판에서 진 채로 날이 바뀌면 `checkNewDay` → `startDaily` 가 `#toasts` 를 통째로 비워(`$('toasts').textContent = ''`, 528행 근처) 연습 판의 정답 토스트가 사라집니다. 화면은 여전히 연습 판입니다. → 새 날 처리 뒤 **지금 보이는 판**이 진 판이면 그 판의 정답 토스트가 남게(이미 있는 `clearAnswerToast()`/`showAnswerToast()` 흐름을 쓰십시오). 지금 모드가 날마다면 지금처럼 새 판.
- 다른 동작은 바꾸지 마십시오.

## 더할 시험 (browser_modes.py, 4개 이상)

1. N4: 연습에서 짐 → `Date` 를 하루 미는 방식(이 파일이 N13 에서 쓰는 `add_init_script` 방식, 또는 `page.evaluate` 로 `Date` 갈아끼운 뒤 `window.dispatchEvent(new Event('focus'))`)으로 새 날 → `정답:` 토스트가 **보임**, 연습 단추 눌림 그대로
2. V13: 연습에서 진 직후(1.5초 안) `#btn-new` → 2.5초 뒤 통계 창이 **안 보임**
3. V14: 연습에서 이긴 뒤 통계 창을 열면 `.bar.hl`(또는 이 화면이 강조에 쓰는 class)이 **없음**, 날마다에서 이긴 뒤엔 있음
4. V17: 저장 설정 하드=켬 + 빈 날마다 판으로 새로 고침 → 첫 제출 전 설정 창 하드 체크박스가 켜져 있고 공유 글 첫 줄 끝에 `*`(이긴 뒤)

화면 검사 규칙: 그려진 것을 묻습니다(`is_visible()`, `getComputedStyle`, `bounding_box()`). 기존 62개 검사는 그대로 두십시오.

## 스스로 확인 (엔진의 검증도 이것)

`python3 projects/자모맞히기/tests/browser_modes.py` 가 `통과 N / 전체 N` 이고 N ≥ 66, `python3 projects/자모맞히기/tests/browser_game.py` 전부 통과, `python3 .aimem/graph/inputs/r24/v_modes.py` 전부 통과.

## 하지 말 것

다른 파일 쓰기, `git commit`/`push`, 파일 삭제, 의존성 설치, 운영 모니터 부르기.

보고 첫 줄은 `DONE` / `PARTIAL` / `BLOCKED` / `NEEDS-FIX: …`, 그다음 세 검사의 마지막 줄.
