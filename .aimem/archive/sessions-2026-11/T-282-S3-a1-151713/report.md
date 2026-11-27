DONE

## 한 일
- `projects/자모맞히기/tests/browser_game.py` 새로 작성: 임시 포트 서버 + 파이썬 Playwright(크로미움)로 계약서 `화면` 절의 14개 항목을 검사. 속성이 아니라 `is_visible()`·`getComputedStyle`·`bounding_box()` 로 그려진 것을 확인.
- `projects/자모맞히기/tests/README.md` 새로 작성: 세 벌 명령, `PROGRESS.md` 목표→검사 표, 스크린숏 목록, 이 검사가 일부러 보지 않는 것.
- 제품 파일은 읽기만 했고, `git commit`/`push`/삭제/의존성 설치 없음.

## 고친 파일
- `projects/자모맞히기/tests/browser_game.py` (새 파일)
- `projects/자모맞히기/tests/README.md` (새 파일)
- 실행 산출물: `projects/자모맞히기/tests/screenshots/game/{help-first,win-stats,share,lose,theme-dark,layout-320}.png`

## 실제로 돌린 검증
- `python3 -m py_compile projects/자모맞히기/tests/browser_game.py` → 통과
- `node --test projects/자모맞히기/tests/*.mjs` → `ℹ pass 61`, `ℹ fail 0`
- `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_*.py'` → `Ran 8 tests`, `OK`
- `python3 projects/자모맞히기/tests/browser_game.py` → rc 0, `통과 121 / 전체 121` (두 번 연속 같은 수)

## 다음 담당자가 알아야 할 것
- 제품 결함은 찾지 못했습니다. 실패 검사 없음.
- **시스템 어두운 모드(`prefers-color-scheme`)는 제품이 구현하지 않아** 그 검사는 뺐고 README 에 적었습니다(웹워들도 안 따름). 설정 단추로 켜는 어두운 테마·저장·새로고침 유지는 검사합니다.
- 쌍자음 키 색은 계약상 `data-key` 가 보통 글자라 Shift 가 꺼진 상태에서 화면에 존재하지 않습니다. 그래서 키 색 대조는 보통 글자 26키만 봅니다.
- `wait_settled` 는 마지막 `.flip` 뒤 140ms 만 기다립니다(`busy` 가 50ms 늦게 풀리는 것을 메우기 위함). 고정 sleep 으로 판정하지 않습니다.
- 스크린숏은 브리프 50줄에 따라 `projects/자모맞히기/tests/screenshots/` 아래에 썼지만, `check` 가 찍은 소유 경로 목록에는 이 경로가 없었습니다. 필요하면 관리자가 정리·gitignore 여부를 정하십시오.
- 자정 무렵 실행은 날짜 바꿈 처리 때문에 흔들릴 수 있습니다.

통과 121 / 전체 121 · 실패 없음