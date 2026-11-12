# R22 4차 검수 (T-275, S1, G-055) - R22-P4·S1·S2·Q3·Q4 가 닫혔는가

대상: 작업 트리의 미커밋 변경 (`tools/fleet.py`·`tools/fleet_graph.py`·`tools/fleet_rt/harness/claude.py`·`tests/test_fleet_graph.py`·`tests/test_rt_claude.py`·`tests/browser_monitor_ui.py`), REV 164.
사본: `/tmp/t275/base` (`.git`·`.aimem/{tls,runs,sessions}`·`__pycache__` 제외). 변이마다 `/tmp/t275/m_<번호>` 로 따로 복사해 쓰고 지웠습니다. 저장소 파일은 이 보고서 말고 건드리지 않았습니다. 운영 모니터는 부르지 않았습니다.

## 기준선

- `python3 -m unittest discover -s tests` (사본) → `Ran 944 tests in 133.464s` / `OK (skipped=3)`. 건너뛴 3건은 사본에서 `.aimem/runs` 를 뺐기 때문입니다
- `python3 tests/browser_monitor_ui.py` (`projects/`·`.aimem` 을 치운 사본 `/tmp/t275/bare`) → rc 0, `통과 30 / 전체 30`. 새 검사 세 줄이 모두 OK입니다
  - `'이번 라운드' 값이 임시 저장소 고정 자료(rounds/R1/round.json)에서 나온다 - 화면='R1 · 2026-11-05 09:30'`
  - `넓은 폭(1280px)에서 옆으로 잘린 보드 제목을 누르면 전문이 보인다 - 전: scrollWidth=1873>clientWidth=544 … 후: … elide-open, scrollWidth=544`
  - `넓은 폭(1280px)에서 옆으로 잘린 그래프 제목을 누르면 전문이 보인다 - 전: scrollWidth=3256>clientWidth=863 … 후: scrollWidth=1164, clientWidth=1164`

## 1. 닫힘표

| 번호 | 닫혔나 | 근거 |
| - | --- | --- |
| R20-N6 (= R22-P4) FIFO 에서 막힘 | **보고된 자리에서는 닫힘. 다만 `step()` 은 여전히 막힘 (새 결함 N1)** | `read_regular_bytes` 는 `O_NONBLOCK` 로 열고 `fstat`+`S_ISREG` 로 거릅니다. 직접 재 보니 FIFO `.out`·FIFO `<id>.json` → `None` 으로 바로 돌아오고, 세션 `meta.json` 이 FIFO 면 `_session_dir` 가 이미 `None` 을 줍니다. `test_fifo_out_does_not_block_and_is_none` 가 V02·V09 를 잡습니다. 그러나 `step()` 은 `run_limit_signal` 보다 **먼저** `fleet.run_report()` (`tools/fleet_graph.py:873`) 를 부르고, `run_report` 는 같은 `.out` 을 `read_text` 로 읽습니다 (`tools/fleet.py:508`). 실측 결과는 `run_report with FIFO .out: HANG` 입니다. N6 이 적은 증상("`step()` 전체가 멈춤")은 그대로 남았습니다 |
| R20-N8 메타 크기 상한 | 닫힘 (옛 실행 갈래), 세션 갈래는 시험 없음 | `META_LIMIT = 256 KiB`. 실측: 262144 B → dict, 262145 B → `None`. `test_oversized_meta_is_none` 가 V05·V06 을 잡습니다. 세션 `meta.json` 을 읽는 두 곳(`fleet._session_meta`, `fleet_graph.run_limit_signal` 세션 갈래)을 옛 무제한 읽기로 되돌린 V07·V08 은 **생존**했습니다 (변이표·N2). 실제 메타 최대 크기는 3184 B (296개 중)라서 상한이 정상 기록을 자르지 않습니다 |
| R22-S1 context-window 시험 `assertIsNone` | 닫힘 | `test_q2_session_branch_context_window_text_is_not_true` 가 이제 `assertIsNone` 입니다. V12 (어댑터 끝 `return None`→`False`)로 이 시험을 **단독으로** 돌리면 FAIL 입니다 (`/tmp/t275/v12s1.py`: 3개 중 FAIL 3) |
| R22-S2 어댑터 except 갈래 시험 | 닫힘 | `test_events_raising_is_none` 은 `_events` 를 예외로 패치하고, 같은 세션이 패치 없이는 `True` 임도 단언합니다. V13 (`except` → `return False`) → 이 시험 FAIL. 3차 W01b 생존이 해소됐습니다 |
| R22-Q3 '이번 라운드' 값 고정 | 닫힘 (조건부, N3 참고) | `rounds/R1/round.json` 고정 자료가 생겼고, `temporary_aimem_root` 가 `fleet.RUNS`·`fleet.ROOT` 를 갈아끼웁니다. 값도 단언합니다. B2 (ROOT 갈아끼우기 지움)·B3 (둘 다 지움)·B4 (고정 라운드 안 씀) → FAIL. B1 (RUNS 만 지움)은 사본에 세션 기록이 없으면 **생존**하고, 진짜 `.aimem/sessions` 를 넣으면 잡힙니다 (`화면='R22 · 2026-11-12 23:38'`) |
| R22-Q4 넓은 폭 잘린 제목 갈래 | 닫힘 | `wide_truncated_title_scenario` 가 1280px 표 배치에서 `scrollWidth>clientWidth` 인 칸을 찾아 누릅니다. 후보가 없으면 FAIL 입니다. B5 (`.elide.elide-open` 의 `white-space:normal; overflow:visible` 제거) → 3건 FAIL. B6 (`app.js` 의 `scrollWidth <= clientWidth` 비교 갈래 제거) → 넓은 폭 보드 FAIL. 카드 배치 대체 갈래만으로는 통과하지 못합니다 |

## 2. 새 결함표

| 번호 | 심각도 | 무엇이 | 어디 | 재현 | 고칠 방향 |
| - | --- | --- | --- | --- | --- |
| N1 | 낮음 (N6 과 같은 위협 모형) | FIFO `.out` 이면 `step()` 이 여전히 영영 막힙니다. 끝난 시도마다 `run_report()` 가 `run_limit_signal()` 보다 먼저 같은 `.out` 을 `read_text()` 로 엽니다. `.rc` 가 FIFO 여도 `_run_state` 가 막힙니다 | `tools/fleet.py:508` (`run_report`), `tools/fleet.py:484` (`_run_state` 의 `rc.read_text()`), 부르는 곳 `tools/fleet_graph.py:860·873` | `fleet.RUNS` 를 임시로, `F.json`={"harness":"claude"} + `os.mkfifo(F.out)` → `fleet.run_report("F")` 3초 HANG. `os.mkfifo(G.rc)` → `fleet._run_state("G")` 3초 HANG (`/tmp/t275/probe.py`) | `.out`·`.rc`·`.err` 읽기도 `read_regular_bytes` 로 바꿉니다 (`.out` 상한은 기존 무제한이니 적당한 값으로). FIFO 시험은 `run_limit_signal` 대신 `step()` 단위로 겁니다 |
| N2 | 낮음 (시험 구멍) | 세션 `meta.json` 의 256 KiB 상한을 지키는 시험이 없습니다. 두 곳 모두 옛 무제한 `read_text` 로 되돌려도 944개가 초록입니다 | `tools/fleet.py` `_session_meta`, `tools/fleet_graph.py:460` | V07·V08 생존 (`Ran 944 … OK`) | 세션 폴더에 256 KiB+1 B `meta.json` 을 두고 `_run_meta`·`run_limit_signal` 이 `None` 인지 보는 시험 |
| N3 | 정보 (시험 구멍) | `S_ISREG` 검사와 fd 닫기를 지키는 시험이 없습니다. FIFO 는 `O_NONBLOCK` 덕에 빈 바이트 → JSON 실패 → `None` 이 되어 `S_ISREG` 없이도 통과합니다. 디렉터리는 `os.read` 의 `IsADirectoryError` 로 걸러집니다. `S_ISREG` 를 지우면 `/dev/zero` 같은 장치(크기 0)에서 `limit` 바이트를 읽어 돌려줍니다 | `tools/fleet.py` `read_regular_bytes` | V01·V04 생존. 실측: 원래 코드에서 3500번 불러도 fd 수 4→4 로 새지 않음 | `read_regular_bytes(fifo, 10) is None` 를 직접 단언합니다 (FIFO 는 `b""` 와 구분됨). `/dev/null` 이나 `/dev/zero` 심볼릭 링크 → `None`. fd 는 `/proc/self/fd` 수를 앞뒤로 비교 |
| N4 | 정보 | Q3 시험은 '이번 라운드' 첫 `span` (라운드 번호·시각)만 단언합니다. `fleet.RUNS` 갈아끼우기를 빼도, 진짜 세션 기록이 없는 저장소에서는 통과합니다 (B1 생존). 둘째 줄(관리자 상태 `실행`/`관리자 끊김`)은 단언하지 않습니다 | `tests/browser_monitor_ui.py` `changed_ui_scenario` | 세션 없는 사본 B1 → 30/30. 진짜 `.aimem/sessions` 를 넣은 사본 B1x → FAIL (`R22 · …\n관리자 끊김(감독 사라짐)`) | 고정 자료가 만드는 상태 글(`실행`)까지 단언하거나, 임시 `.aimem` 에 '더 새 관리자 세션이 없다' 를 보장하는 반례 하나 |
| N5 | 정보 | `read_regular_bytes` 는 심볼릭 링크를 따라갑니다 (트리 밖 `/etc/hostname` 링크도 읽힘). `O_NOCTTY` 가 없어 tty 장치 링크를 열면 제어 터미널이 될 수 있습니다. 옛 `read_text` 도 링크를 따라갔으므로 **회귀는 아닙니다** | `tools/fleet.py` `read_regular_bytes` | `/tmp/t275/probe.py`: 일반 파일 링크 → 100 B, `/dev/zero` 링크 → None, 자기 순환·끊긴 링크 → None, 권한 0 파일 → None (예외 없음) | 필요하면 `O_NOCTTY` 추가. 링크 거부는 모니터 `reader.py` 처럼 정책을 정한 뒤에 |

그 밖의 실측 (결함 아님):
- 딱 상한 크기(100 B / limit 100)는 읽히고, 99 이면 `None` 입니다. 빈 파일은 `b""` 입니다. `limit=0` 이면 빈 파일은 `b""`, 아니면 `None` 입니다. `limit=-1` 이면 `None` 입니다. `str`·`bytes` 경로 모두 받습니다. `None`·`float` 경로는 `TypeError` 를 냅니다 (호출부는 늘 `Path` 라 문제 없음)
- **동작 변화**: 옛 실행 갈래 `_run_meta` 는 깨진 JSON에서 `JSONDecodeError` 를 냈는데, 이제 `None` 입니다. BOM·깨진 UTF-8 도 `None` 입니다. JSON 목록은 예전처럼 목록을 그대로 돌려줍니다. 호출부 8곳은 모두 `… or {}` 꼴이라 더 너그러워질 뿐입니다. 모니터는 `fleet._run_meta` 를 직접 부르지 않고 `fleet_ctl.public_state`→`running_runs` 를 거칩니다. 올바른 메타에서 결과는 같습니다. `reader.py` 는 이 함수를 쓰지 않습니다
- `fleet_rt` 세션 `report()` (`run_report` 세션 갈래)가 FIFO 에서 어떤지는 재지 않았습니다

## 3. 변이표

단위 변이는 사본마다 **전체** `python3 -m unittest discover -s tests` 로, 브라우저 변이는 `.aimem`·`projects`·`rounds` 가 있는 사본(세션·runs 제외)에서 `python3 tests/browser_monitor_ui.py` 로 돌렸습니다.

| 변이 | 결과 |
| - | - |
| V01 `S_ISREG` 검사 지움 (`if st.st_size > limit:`) | ✗ 생존 - 944 OK |
| V02 `O_NONBLOCK` 지움 | ○ `test_fifo_out_does_not_block_and_is_none` FAIL |
| V03 크기 상한 지움 (`S_ISREG` 만) | ○ `test_read_regular_bytes_cases` FAIL |
| V04 `finally: os.close(fd)` → `pass` (fd 샘) | ✗ 생존 - 944 OK |
| V05 `META_LIMIT = 1 << 40` | ○ `test_oversized_meta_is_none` FAIL |
| V06 `_run_meta` 옛 `read_text` 로 되돌림 | ○ `test_oversized_meta_is_none` FAIL |
| V07 `_session_meta` 옛 `read_text` 로 되돌림 | ✗ 생존 - 944 OK |
| V08 `run_limit_signal` 세션 메타를 옛 `read_text` 로 | ✗ 생존 - 944 OK |
| V09 `.out` 을 옛 `open("rb").read(1MiB)` 로 | ○ `test_fifo_out_does_not_block_and_is_none` FAIL |
| V10 `.out` 상한 1 MiB → 1 GiB | ○ `test_m7_read_is_capped_at_one_mib` FAIL |
| V11 읽기 고리가 4바이트에서 끊김 | ○ `test_broken_run_meta_…`·`test_kill_run_…` 등 다수 FAIL/ERROR |
| V12 (S1) 어댑터 끝 `return None` → `False` | ○ 전체: n3·m8·n4 등 FAIL. 단독: `test_q2_session_branch_context_window_text_is_not_true` FAIL |
| V13 (S2) 어댑터 `except` → `return False` | ○ `test_events_raising_is_none` FAIL |
| B1 (Q3) `temporary_aimem_root` 에서 `fleet.RUNS` 갈아끼우기 지움 - 세션 기록 없는 사본 | ✗ 생존 - 30/30 |
| B1x (Q3) 같은 변이 - 진짜 `.aimem/sessions` 를 넣은 사본 | ○ `'이번 라운드' 값이 … 고정 자료…` FAIL (`화면='R22 · 2026-11-12 23:38'`), 대조군 B0x 30/30 |
| B2 (Q3) `fleet.ROOT` 갈아끼우기 지움 | ○ 같은 검사 FAIL (`R22 · …`) |
| B3 (Q3) `RUNS`·`ROOT` 둘 다 지움 | ○ 같은 검사 FAIL |
| B4 (Q3) `write_fixed_round` 부르기 지움 | ○ 같은 검사 FAIL (`화면='띄운 라운드 없음'`) |
| B5 (Q4) CSS `.elide.elide-open` 를 `nowrap; overflow:hidden` 으로 | ○ 넓은 폭 보드·그래프, 폰 폭 그래프 펼침 FAIL (29→27) |
| B6 (Q4) `app.js` 의 `scrollWidth <= clientWidth` 비교 갈래 지움 | ○ `넓은 폭(1280px)에서 옆으로 잘린 보드 제목…` FAIL (28/30) |

합계 20개: 잡힘 15, 생존 5

## 4. 총평

큐 두 건은 **보고된 자리에서 닫혔습니다.** `read_regular_bytes` 는 FIFO·디렉터리·장치·권한 없음·끊긴 링크·순환 링크에서 예외 없이 `None` 을 줍니다. 딱 상한 크기는 읽고, 한 바이트 넘으면 거절합니다. fd 도 새지 않았습니다 (3500번 호출에 fd 4→4). 메타 256 KiB 상한은 실제 메타(최대 3 KiB)를 건드리지 않습니다. 깨진 메타가 예외 대신 `None` 이 된 것은 호출부가 모두 `or {}` 라 더 안전해진 변화이고, 모니터 동작은 바뀌지 않았습니다. 시험 쪽도 S1 (`assertIsNone` 이 단독으로 V12 를 잡음)·S2 (V13 잡음)·Q3 (ROOT·고정 라운드 변이 잡음)·Q4 (넓은 폭 원래 갈래를 CSS·JS 변이 둘 다 잡음)가 모두 실제로 무는 것을 확인했습니다. 다만 N6 이 적은 증상 자체는 남았습니다. **`step()` 은 `run_limit_signal` 보다 먼저 `run_report` 로 같은 `.out` 을 `read_text` 하므로 FIFO `.out` 에서 여전히 멈춥니다 (N1, 낮음).** `.rc` FIFO 도 `_run_state` 를 멈춥니다. 다음 수정은 `.out`·`.rc`·`.err` 읽기를 같은 함수로 옮기고, FIFO 시험을 `step()` 단위로 거는 것입니다. 생존 변이 다섯(V01·V04·V07·V08·B1)은 모두 시험 구멍(N2~N4)입니다. 지금 코드가 틀렸다는 뜻은 아니므로 커밋을 막을 결함은 없다고 봅니다.
