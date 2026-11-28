# R56 재검수 (T-507, S4) - R56-N1 고침 확인

대상: `projects/VoxLog/tests/test_browser_select.py`(25개), `tests/browser_voxlog.py`(`exit_code`·`apply_selection` 등 뺀 함수).
방법: diff 정독, `/tmp` 아래 `shutil.copytree` 사본에 되돌림을 하나씩 걸어 `python3 -m unittest test_browser_select`, `--only 7`·`--only 999`·`--match "기본값 읽기"` 실행. 코드는 고치지 않았고 사본은 지웠다.

## (1) 되돌림 표 (사본 하나씩, 원본은 25 tests OK)

| 되돌림 | 새 검사 | 실패한 검사 |
|---|---|---|
| A: `check()` 의 `if SELECTION … SKIPPED += 1; return` 3줄 삭제 | **실패** (1) | `CheckSelectionTest.test_check_skips_unselected_without_running_it` |
| B1: `apply_selection` 안 `SELECTION = resolve_selection(only, match)` → `SELECTION = None` | **실패** (1) | `ApplySelectionTest.test_sets_and_returns_selection` |
| B2: `main()` 에서 `apply_selection(sys.argv[1:])` 호출 줄 삭제 (`--only` 가 다시 전체를 돎) | **통과 못 막음** (25 OK) | 없음 → R56-N5 |
| C: `exit_code` 본문 `ran > 0 and failed == 0` → `failed == 0` | **실패** (1) | `ExitCodeTest.test_requires_ran_at_least_one_and_no_failure` |
| C2: `main()` 의 `return exit_code(ran, len(bad))` → `return 0 if not bad else 1` | **실패** (1) | `ExitCodeTest.test_main_uses_exit_code` (소스에 `exit_code(` 문자열이 있는지만 봄) |
| D: `NEEDS` 의 `3: (2,)` → `3: ()` | **실패** (3) | `test_only_is_expanded_with_real_needs`·`test_expand_uses_module_needs`·`test_sets_and_returns_selection` |

앞 검수의 A~D 는 모두 이제 잡힌다(A·C·D 는 직접, B 는 `apply_selection` 안쪽 줄로 옮겨져 B1 이 잡음). 앞서 못 잡던 `_known_names()`(검사 22: 77개·41 없음)·`resolve_selection`(18~20)·`NEEDS` 값(19·21)도 지켜진다.

## (2) 함수로 빼면서 바뀐 것

diff 를 읽은 결과 **인자 없는 실행의 동작은 그대로**다.
- `main()` 맨 앞 `apply_selection(sys.argv[1:])` → `parse_selection([])` = `(None, [])` → `resolve_selection(None, [])` = `None` → `SELECTION is None` 이라 `check()` 는 예전과 같고 `SKIPPED` 는 0.
- 끝줄: `summary_line(ran, total, ok, 0)` = `"%d/%d 통과"` 로 예전 `print("%d/%d 통과" % (ok, len(RESULTS)))` 와 같다(`total = ran + 0`). 고른 게 0개일 때만 나오는 `고른 검사가 없습니다` 는 전체 실행에선 `ran == 0` 이 될 수 없어 안 나온다.
- rc: `0 if not bad else 1` → `exit_code(ran, len(bad))`. 전체 실행에선 `ran > 0` 이므로 같은 값. **바뀐 것은 rc 를 함수로 뺀 것뿐**이다(고른 게 0개일 때 1 은 앞 라운드부터).
- 유일한 새 차이: 모르는 인자(오타 `--onyl`)는 예전엔 무시되어 전체를 돌았고 이제 argparse 오류 rc 2 다. 엔진·도구는 인자 없이 부르므로 영향 없음(앞 검수에서 확인한 사항).

직접 돌린 것(인자 없는 전체 브라우저는 안 돌림, 하나씩 겹침 없이):

| 명령 | rc | 끝줄 |
|---|---|---|
| `python3 projects/VoxLog/tests/browser_voxlog.py --only 7` | 0 (6초) | 통과 2·3·7 → `부분 실행: 3/77 돌림 · 74 건너뜀 · 3/3 통과 (전체 통과 아님)` |
| `… --only 999` | **1** | `고른 검사가 없습니다` / `부분 실행: 0/77 돌림 · 77 건너뜀 · 0/0 통과 (전체 통과 아님)` |
| `… --match "기본값 읽기"` | 0 | `통과  68 기본값 읽기 실패: …` / `부분 실행: 1/77 돌림 · 76 건너뜀 · 1/1 통과 (전체 통과 아님)` |

`python3 -m unittest discover -s projects/VoxLog/tests -p test_browser_select.py` → `Ran 25 tests … OK` (0.09초, 브라우저 안 씀, 검사 1 은 playwright 없이 임포트됨을 확인).

## (3) 모듈 전역이 다른 검사로 새는가 - 새지 않는다

- 전역을 건드리는 단위 검사는 둘뿐이다. 검사 17(`CheckSelectionTest`)은 `SELECTION`·`SKIPPED`·`RESULTS` 를 저장했다가 `finally` 에서 `SELECTION`·`SKIPPED` 는 대입으로, `RESULTS` 는 `RESULTS[:] = saved` 로 **같은 리스트 객체를 되살린다**(`del RESULTS[:]` 로 비운 뒤라 객체를 바꿔치기하면 다른 참조가 어긋나는데 그렇게 하지 않음). 검사 25(`ApplySelectionTest`)는 `apply_selection` 이 `SELECTION` 을 바꾸므로 `SELECTION` 을 저장·복구한다(`SKIPPED`·`RESULTS` 는 `apply_selection` 이 건드리지 않음).
- 예외가 나도 `finally` 라 복구된다. 검사 17 은 `contextlib.redirect_stdout` 으로 `check()` 의 출력을 막는다.
- 나머지 검사는 순수 함수나 `NEEDS`(읽기만)만 쓴다. `expand_needs(..., needs=NEEDS)` 는 `out = set(selected)` 로 복사해 `NEEDS` 도 인자도 안 바꾼다.
- 실행 순서를 바꿔도(`unittest` 는 알파벳 순) 서로 의존하지 않는다: 사본 되돌림 표에서 어떤 한 검사만 실패했고 다른 검사가 연쇄로 실패한 적이 없다.
- 한계: 이 검사들은 `browser_voxlog` 모듈 전역을 건드리므로 병렬 실행(스레드)엔 안전하지 않다. `unittest discover` 는 순차라 문제 없다.

## 지적

### R56-N5 (하) `main()` 이 `apply_selection` 을 부르는지 지키는 검사가 없다
검사 24 는 `main` 소스에 `exit_code(` 가 있는지만 본다. `main()` 에서 `apply_selection(sys.argv[1:])` 줄을 지워도(표의 B2) 25개가 모두 통과한다. 그러면 `--only`·`--match` 가 조용히 무시되고 인자 없는 전체 실행이 된다.
실패 시나리오: 누군가 `main()` 을 고치다 그 줄을 빼면 `--only 7` 이 6초가 아니라 전체(수 분·메모리 약 1GB)를 돈다. **거짓 통과는 아니다** - 전체가 통과하면 끝줄이 `77/77 통과` 라 구분되고 rc 도 맞다 - 그래서 하. 고른 게 도로 전체가 되는 낭비·오해만 생긴다.
손볼 방향(고치지 않음): 검사 24 와 같은 방식으로 `inspect.getsource(browser_voxlog.main)` 에 `apply_selection(` 이 있는지 한 줄 더 보거나, `main` 의 앞 단계를 `playwright` 임포트 앞에서 `--only 999` 가 rc 1 로 끝나도록 나눠 부르게 한다(선택). 큐로 보낼 만한 크기.

앞 검수의 R56-N2~N4(하)는 큐로 갔으므로 다시 지적하지 않는다. 새로 본 상·중은 없다.

## 요약
- R56-N1(중) 은 고쳐졌다: 되돌림 A·C·D 는 새 검사가 잡고, B 는 `apply_selection` 안쪽 줄을 잡는다. `main()` 이 `apply_selection` 을 부르는 줄만 안 지켜진다(하 1).
- 인자 없는 실행의 끝줄·rc·고르기 동작은 그대로, 바뀐 것은 rc 를 `exit_code` 로 뺀 것뿐이다.
- 단위 검사의 전역 복구는 `finally` 로 되어 있어 다른 검사에 새지 않는다.
- 커밋·삭제(자기 /tmp 사본 제외)·설치 없음. 운영 자료 안 읽음.

판정: 통과
