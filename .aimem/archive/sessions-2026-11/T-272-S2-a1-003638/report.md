DONE

**한 일**
- `tools/fleet.py`
  - `read_regular_bytes(path, limit)` 를 추가했습니다. `O_RDONLY|O_NONBLOCK` 으로 연 뒤 `fstat` 으로 검사합니다. 일반 파일이 아니거나 `limit` 를 넘거나 `OSError` 면 `None` 이고, 열었으면 `finally` 에서 닫습니다.
  - 안쪽 도우미 `_read_json_capped(path, limit=256KiB)` (상수 `META_LIMIT`)와 `import os, stat` 도 추가했습니다.
  - `_session_meta` 와 `_run_meta` 가 이 도우미로 읽습니다. 반환 꼴은 dict 또는 None 그대로입니다.
- `tools/fleet_graph.py` `run_limit_signal`
  - `.out` 은 `fleet.read_regular_bytes(..., 1 MiB)` 로 읽고, `None` 이면 `None` 을 돌려줍니다.
  - 세션 갈래의 `meta.json` 도 `fleet._read_json_capped` (256 KiB)로 읽고, dict 가 아니면 `None` 입니다.

**검증**
- `python3 -m unittest tests.test_fleet_graph tests.test_fleet_ctl tests.test_fleet` → `Ran 127 tests ... OK`
- `python3 -m unittest discover -s tests -p "test_rt_*.py"` → `Ran 179 tests ... OK`
- 임시 `RUNS` 를 쓰는 스크립트(`/tmp/s2chk.py`)의 출력:
  - FIFO `X.out` + claude 메타: `run_limit_signal('X')` → `None`, 0.0초
  - 2 MiB 짜리 `Y.json`: `_run_meta('Y')` → `None`
  - 정상 메타 `Z.json`: `_run_meta('Z')` → `{'harness': 'claude'}`
  - FIFO 에 `read_regular_bytes(X.out, 10)` → `None`

**다음 담당자가 알아야 할 것**
- 동작이 하나 바뀝니다. `_run_meta` 가 깨진 JSON 에서 예전에는 `ValueError` 를 던졌는데 이제는 `None` 을 돌려줍니다. 호출부가 모두 `or {}` 로 받거나 `run_limit_signal` 처럼 예외를 삼키는 자리여서 테스트는 모두 통과했습니다.
- 세션 갈래는 `meta.json` 이 FIFO 면 `_session_dir` 의 `is_file()` 검사에서 이미 걸러지고, 나머지 읽기는 도우미를 지납니다.
- `tests/**` 는 건드리지 않았습니다. S3 가 FIFO·상한 시험을 쓰면 됩니다. 스크립트 `/tmp/s2chk.py` 의 시나리오를 그대로 옮기면 됩니다.