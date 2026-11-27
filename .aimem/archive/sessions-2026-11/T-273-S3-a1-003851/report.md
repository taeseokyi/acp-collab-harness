DONE

전체 `python3 -m unittest discover -s tests` 통과: 944개 실행, OK (skipped=1), 136초. `tools/**` 는 읽기만 했고 제품 결함은 없었습니다.

**고친 파일**
- `tests/test_fleet_graph.py`, `FleetGraphContractTests` 클래스. 이 클래스의 `setUp` 이 `fleet.RUNS` 를 임시 폴더로 갈아끼웁니다.
  - `test_fifo_out_does_not_block_and_is_none`: claude 메타 `X.json` 과 `os.mkfifo` 로 만든 `X.out` 을 두고 `run_limit_signal("X")` 를 스레드로 돌립니다.
    - `join(3)` 뒤에도 살아 있으면 실패 처리합니다.
    - 그 전에 FIFO 를 `O_WRONLY|O_NONBLOCK` 으로 열어 막힌 스레드를 풀어 줍니다.
    - 결과는 `[None]` 이어야 합니다.
  - `test_oversized_meta_is_none`: 2 MiB 짜리 `Y.json` 에서 `fleet._run_meta("Y")` 가 `None` 이어야 합니다.
  - `test_read_regular_bytes_cases`: 일반 파일은 바이트(limit 10 과 limit 5 둘 다)를 돌려주고, limit 4 초과·디렉터리·없는 경로는 `None` 입니다.
  - R22-S1: `test_q2_session_branch_context_window_text_is_not_true` 의 단언을 `assertIsNone` 으로 바꿨습니다.
- `tests/test_rt_claude.py`
  - R22-S2: `LimitTest.test_events_raising_is_none` 을 추가했습니다.
    - `ClaudeHarness._events` 에 `mock.patch.object(side_effect=RuntimeError)` 를 걸면 `limit_signal` 이 `None` 입니다.
    - 같은 세션을 패치 없이 읽으면 `True` 임을 확인해, `None` 이 `except` 갈래 덕임을 보였습니다.

**검증 명령과 출력**
- `python3 -m unittest discover -s tests`: 위의 전체 결과입니다. 출력 중 `ResourceWarning: subprocess ... is still running` 한 건은 이번에 만든 시험이 아니라 기존 시험에서 나온 것으로 보입니다.
- `python3 -m unittest discover -s tests -p test_fleet_graph.py -v 2>&1 | grep -c "ok$"` → 80
- `python3 -m unittest discover -s tests -p test_rt_claude.py -v 2>&1 | grep -c "ok$"` → 29

**참고**
- 쓰기 경로는 지시받은 두 시험 파일뿐입니다. git commit·push 는 하지 않았습니다.