NEEDS-FIX: 연습에서 진 판을 모드 오갔다 오면 새 판으로 바뀐다 — `projects/자모맞히기/web/js/ui.js:554` (`selectMode`)

**한 일**
- `projects/자모맞히기/tests/browser_modes.py` 새 파일 작성. 지시된 13개 항목(N4~N9·N13, N12의 Process 키·연습 이어 하기·뒤집기 중 모드·미리보기 고정값·도움말↔README)을 **검사 62개**로 나눠 그려진 화면(`is_visible`·`getComputedStyle`·`bounding_box`)으로 확인.
- `projects/자모맞히기/tests/README.md`: 네 벌 명령 표에 `browser_modes.py` 행 추가, 목표→검사 표의 자모 규칙·실물 자판·날마다/연습·판 끝·어두운 모드·접근성 행 갱신, 현재 실패 상태와 원인을 명시.
- 제품 파일·`browser_game.py`는 쓰지 않음.

**고친 파일**
- `projects/자모맞히기/tests/browser_modes.py` (새 파일)
- `projects/자모맞히기/tests/README.md`

**실제로 돌린 검증과 출력**
- `python3 tools/aimem_db.py check --slot S3 --token 5b8c1e --rev 170` → `일치: S3 토큰 5b8c1e 하네스 opencode … REV 170`
- `python3 projects/자모맞히기/tests/browser_modes.py` (두 번) → 두 번 다:
  ```
  [FAIL] N5 연습으로 돌아오면 그 판이 그대로 보임 - 첫 줄 ''
  [FAIL] N5 연습으로 돌아오면 그 판의 정답 토스트만 보임 - 실제 []
  통과 60 / 전체 62
  ```
  rc 1
- `python3 -m py_compile projects/자모맞히기/tests/browser_modes.py` → `COMPILE-OK`
- `python3 projects/자모맞히기/tests/browser_game.py` → `통과 121 / 전체 121`, rc 0 (회귀 없음)

**실패 2건의 원인 (제품 결함, R24-N5)**
- 재현: 연습에서 6번 틀려 짐 → `정답: <낱말>` 토스트 확인 → `#mode-daily` 클릭(토스트는 정상적으로 사라짐, 통계 창도 안 열림) → `#mode-practice` 클릭 → **첫 줄이 빈 새 연습 판**이 뜨고 정답 토스트가 없다.
- `ui.js:554` `if (!practiceGame || practiceGame.status !== 'playing') startPractice();` 가 **진(또는 이긴) 연습 판을 버리고 새 판을 만든다.** `CONTRACT.md` 의 "모드를 바꾸면 그 모드의 판을 보여 줌 (연습 판도 마찬가지)" 와 지시 2번("연습으로 돌아오면 그 판의 정답 토스트만")에 어긋난다. `#btn-new` 로만 새 연습 판을 여는 쪽(예: `if (!practiceGame) startPractice();` + 완료된 판은 그대로 보여 주기)이 계약에 맞다.

**다음 담당자가 알아야 할 것**
- 나머지 60개는 통과한다: N4 Enter 단추 3종, N6 통계 창, N7 뒤집기 중 입력·자판 색, N8 하드 모드(모드별 체크박스·새로 고침 일관), N9 dark/light 문맥·끈 값 유지, N13 미래 시계 공유 첫 줄 `자모맞히기 1 1/6`, N12 Process 키·연습 이어 하기·뒤집기 중 모드 무시·미리보기 `닭`/`갑시`·도움말↔README 표.
- N9는 `browser_harness.new_page()` 대신 `color_scheme`·`add_init_script`를 받는 지역 `open_page()`로 문맥을 만든다(하네스는 고치지 않음). N13은 `add_init_script`로 `Date`를 2026-11-12에 고정한다.
- `browser_modes.py`는 `통과 62 / 전체 62`가 초록 기준이다. N5 결함이 고쳐지면 그대로 62/62가 되어야 하며, `tests/README.md`에도 60/62와 원인을 적어 두었다.
- `git commit`/`push`, 삭제, 의존성 설치, 운영 모니터 호출은 하지 않았다.