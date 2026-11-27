DONE

**고친 파일:** `tests/browser_monitor_ui.py` 하나만 고쳤습니다. 제품(`tools/**`)은 읽기만 했습니다.

**R22-Q3 ('이번 라운드' 값을 고정 자료로)**
- `temporary_aimem_root` 가 `fleet.RUNS` 를 `root/.aimem/runs` 로 바꾸고, 끝나면 되돌립니다.
- `fleet.ROOT` 도 `root` 로 바꿉니다. 브리프에는 없던 변경입니다. 라운드 기록은 `fleet.ROOT/rounds/` 에서 읽으므로(`fleet_ctl._record_rounds`, `_round_record`, `round_workspace`), `fleet.RUNS` 만 바꾸면 진짜 저장소의 `rounds/R22` 가 그대로 새어 들어옵니다.
- `write_fixed_round(root)` 가 `rounds/R1/round.json` 을 씁니다. 내용은 `{"round":1,"at":"2026-11-05T09:30:00","brief":...,"requests":[],"projects":[]}` 입니다. `session` 칸이 없어서 `manager_status` 는 None 이고, `_last_round` 가 이 기록에서 값을 만듭니다.
- 새 검사는 화면 값이 정확히 `R1 · 2026-11-05 09:30` 인지 봅니다. 진짜 저장소 값(R22 등)이면 실패합니다.

**R22-Q4 (넓은 폭에서 옆으로 잘린 제목)**
- 새 시나리오 `wide_truncated_title_scenario` 는 1280px(표 배치)에서 돕니다.
- 잘린 칸은 `scrollWidth > clientWidth + 1` 을 `page.evaluate` 로 찾습니다. 고정 자료의 보드 제목과 그래프 제목을 각각 따로 잽니다. 잘린 칸이 없으면 실패로 칩니다. 이것이 예전 대체 갈래로 몰래 통과하던 구멍을 막습니다.
- 잘린 칸을 누르면 `elide-open` 이 붙고, `is_visible()` 이 참이며, `bounding_box()` 가 화면 안(x, y 와 폭 안쪽, 높이 > 0)입니다. 높이가 늘고 `scrollWidth <= clientWidth` 입니다.
- 새 고정 자료는 필요 없었습니다. 기존 `write_fixed_board` 와 `write_fixed_graph` 의 긴 제목이 1280px 에서도 실제로 잘립니다.
  - 보드: `scrollWidth` 1873 > `clientWidth` 544.
  - 그래프: `scrollWidth` 3256 > `clientWidth` 863.

**실제로 돌린 검증:** `python3 tests/browser_monitor_ui.py` 를 두 번 돌렸고, 마지막 줄은 둘 다 `통과 30 / 전체 30` 입니다. 28 이상 조건을 만족합니다.
- Q3 줄: `[OK] '이번 라운드' 값이 임시 저장소 고정 자료(rounds/R1/round.json)에서 나온다 - 화면='R1 · 2026-11-05 09:30'`
- Q4 보드 줄: `[OK] 넓은 폭(1280px)에서 옆으로 잘린 보드 제목을 누르면 전문이 보인다 - 전: scrollWidth=1873>clientWidth=544, 높이=40.6; 후: ... box={'x': 117, 'y': 340.5, 'width': 544, 'height': 126.9}`
- Q4 그래프 줄: `[OK] 넓은 폭(1280px)에서 옆으로 잘린 그래프 제목을 누르면 전문이 보인다 - 전: scrollWidth=3256>clientWidth=863, ...후: box={'x': 58, 'y': 314.2, 'width': 1164, 'height': 93}`

**다음 담당자에게**
- 제품 결함은 못 찾았습니다.
- 변이로 직접 확인한 것은 없습니다. 예를 들어 `fleet.ROOT` 패치를 빼도 Q3 검사가 실제로 빨개지는지는 돌려 보지 않았습니다.
- `fleet.ROOT` 패치는 이 파일의 임시 저장소 구간에서만 걸리고 끝나면 풀립니다.
- 작업 트리에는 이 작업 전부터 있던 다른 변경이 있습니다(`tools/fleet.py` 등). 이 슬롯은 건드리지 않았습니다.