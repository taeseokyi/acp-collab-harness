DONE. 시험 둘을 고쳤고, 전체 discover 가 통과합니다.

**고친 파일:** `tests/test_fleet_graph.py` 만.

**R1 (전체 discover 에서 빨갛던 것)**
- `_session()` 도우미가 `fleet_rt.harness.get` 을 `Mock` 으로 패치합니다. 이 Mock 은 어떤 이름을 청해도 `claude.ADAPTER` 를 돌려줍니다.
- `fleet_graph.run_limit_signal` 이 호출 시점에 `rt_harness.get` 을 속성으로 찾으므로 이 자리에서 패치가 먹습니다.
- `AIFLEET_HARNESS=fake` 환경변수는 건드리지 않았습니다.
- `_session()` 은 `test_q2_*` 셋과 Q1 시험이 씁니다.
- `test_q2_session_branch_429_is_true` 에 `self.harness_get.assert_called_once_with("claude")` 를 더했습니다.

**R2 (Q1 시험이 `/` 허용을 못 잡던 것)**
- `test_q1_run_id_with_path_segments_is_none` 이 디딤 폴더를 실제로 만듭니다.
  - 세션 `T-1-S1-a1-000000` 에는 `meta.json` 과 429 사건이 든 `events.jsonl` 이 있습니다.
  - 바깥 `outside/evil` 에는 `meta.json`(`harness_effective: claude`)과 429 result 한 줄짜리 `events.jsonl` 이 있습니다.
- 반례 id 는 `T-1-S1-a1-000000/../../outside/evil` 입니다.
- 이 경로가 실제로 풀리는지 `(root / bad / "meta.json").exists()` 로 단언했습니다.
- `fleet._session_dir(bad) is not None` 도 단언했습니다.
- 정상 id 가 `True` 를 내는지도 대조로 단언했습니다.
- 이 사전 조건이 있어서, 정규식이 `/` 를 허용하면 `run_limit_signal(bad)` 가 `True` 가 되어 시험이 실패합니다.
- 정규식을 직접 바꿔서 이 실패를 재현해 보지는 않았습니다. 제품 수정 금지 때문입니다.

**실제로 돌린 검증**
- `python3 -m unittest tests.test_fleet_graph` → `Ran 77 tests ... OK`
- `python3 -m unittest discover -s tests` → `Ran 940 tests in 135.044s ... OK (skipped=1)`

제품 결함은 찾지 못했습니다. `tools/**` 와 `tests/_fleet_env.py` 는 읽기만 했습니다. commit, push, 삭제도 하지 않았습니다.