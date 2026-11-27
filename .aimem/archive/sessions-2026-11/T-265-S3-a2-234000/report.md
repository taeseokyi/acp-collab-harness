DONE — `tests/browser_monitor_ui.py` 한 파일만 고쳤고, `python3 tests/browser_monitor_ui.py` 가 **통과 27 / 전체 27** 입니다. 다만 `projects/`·`.aimem` 을 치운 사본에서 돌리는 검증은 이 환경에서 승인이 막혀 직접 못 돌렸습니다.

**한 일**
- **N1**: `write_fixed_project` 가 진짜 `projects/` 를 더는 읽지 않습니다. 이 함수에서 `ROOT` 와 `shutil` 이 사라졌습니다.
  - 시험이 직접 프로젝트 둘을 만듭니다.
  - `웹워들`: 끝남. 목표가 모두 `[x]` 이고, 손으로 쓴 `app.json` 과 `web/index.html` 이 있습니다. 이 html 은 `#board` 안에 `.tile` 30칸과 `.key` 단추 둘을 글자 그대로 담았습니다.
  - `진행앱`: 진행 중. 목표 하나가 `[ ]` 입니다.
- **N2**: `changed_ui_scenario` 를 `temporary_aimem_root` + `monitor_server(root=temp_root)` 블록 안으로 옮겼습니다. `main()` 에 `root` 없는 `monitor_server()` 호출은 없습니다. 소스를 정규식으로 확인했습니다.
- **N2 자료**: 임시 DB 에 제목이 아주 긴 보드 태스크와 큐 항목을 하나씩 넣는 `write_fixed_board` 를 새로 만들었습니다. 이걸 빼면 `'생략된 제목을 눌러 펼칠 수 있다'` 가 빨개집니다. 단언은 느슨하게 바꾸지 않았습니다.
- **M11**: `show_all_projects(page)` 가 `'전체'` 칩을 무조건 누릅니다. 칩이 없으면 타임아웃 예외가 나서 검사가 빨개집니다. `narrow_scenario` 와 `short_scenario` 에도 같은 클릭을 넣었습니다. 진행 중 프로젝트가 있으면 기본 필터가 `'진행 중'` 이라 `웹워들` 이 숨기 때문입니다.

**돌린 명령**
- `python3 tests/browser_monitor_ui.py | grep -v "^\[OK\]"` 의 출력은 `통과 27 / 전체 27` 한 줄뿐입니다.
- 위 출력은 `write_fixed_board` 를 넣은 뒤 것이고, 그 전 실행은 26/27 이었습니다. 빨간 검사는 `'생략된 제목을 눌러 펼칠 수 있다'` 였습니다.
- 정규식 확인 결과는 `root 없는 호출: []`, `ROOT in write_fixed_project: False` 입니다.

**다음 담당자가 알아야 할 것**
- **미검증**: `projects/`·`.aimem` 을 치운 사본 안에서 27/27 이 나오는지는 확인하지 못했습니다. `/tmp` 로 `cp`·`mkdir`·`rm` 하는 명령이 승인 대기에 걸렸습니다. 이 시험은 `projects/` 와 `.aimem` 을 읽을 길이 없다고 코드로 확인했을 뿐입니다. 사본 검증은 `tests` 와 `tools` 만 복사한 폴더에서 돌리면 됩니다.
- 작업 트리에는 내가 건드리지 않은 `tools/fleet_graph.py` 변경이 있습니다. 다른 슬롯의 것으로 보입니다.
- 제품 결함은 없었습니다.