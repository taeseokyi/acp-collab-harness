DONE

**한 일**
- 기존 산출물 `projects/자모맞히기/tests/browser_modes.py`(직전 시도)를 확인하고, 현재 제품 `ui.js` 상태를 직접 대조했습니다. 직전 보고의 R24-N5 결함(`selectMode` 가 진 연습 판을 새로 만듦)은 **현재 제품에 이미 고쳐져 있습니다**(`selectMode`: `if (!practiceGame) startPractice();` + `clearAnswerToast()/showAnswerToast()`, `startDaily`: 토스트·`endTimer` 정리). 따라서 해당 검사는 이제 정상 통과합니다.
- `open_page()` 가 특수 문맥(`color_scheme`, `add_init_script`)이 아닐 때는 하네스의 `new_page()` 를 쓰도록 정리했습니다(N9 dark/light, N13 Date 고정만 지역 문맥).
- `tests/README.md` 의 낡은 서술을 바로잡았습니다: `통과 60 / 62`·N5 실패·"검사 초록 아님" → `통과 62 / 62`, R24-N5 회귀 방지 검사로 표기.

**고친 파일**
- `projects/자모맞히기/tests/browser_modes.py`
- `projects/자모맞히기/tests/README.md`
- 제품 파일·`browser_game.py` 는 건드리지 않았습니다.

**실제로 돌린 검증**
```bash
python3 projects/자모맞히기/tests/browser_modes.py
```
출력 마지막 줄: `통과 62 / 전체 62`, `RC=0`.
추가로 `python3 -m py_compile projects/자모맞히기/tests/browser_modes.py` → OK.
검사 범위: N4(모드·`#btn-new` Enter), N5/N6(연습 정답 토스트·통계 타이머), N7(뒤집기 중 입력/자판 색), N8(하드 모드 모드별 값·새로 고침), N9(dark/light 시스템 문맥·끈 값 유지), N13(2026-11-12 고정 시계 공유 첫 줄), N12(Process 키·연습 이어 하기·뒤집기 중 모드 무시·미리보기 `닭`/`갑시`·도움말↔README 표), 시나리오별 페이지 오류 없음.

**다음 담당자에게**
- 현재 `browser_modes.py` 는 `통과 62 / 전체 62` 가 기준입니다. 수가 줄면 시나리오 중간 예외를 의심하십시오.
- 직전 보고의 `NEEDS-FIX` 는 제품이 이미 고쳐진 뒤의 낡은 판단입니다. 제품 `ui.js` 는 수정하지 않았습니다.
- `git commit`/`push`, 삭제, 의존성 설치, 운영 모니터 호출은 하지 않았습니다.