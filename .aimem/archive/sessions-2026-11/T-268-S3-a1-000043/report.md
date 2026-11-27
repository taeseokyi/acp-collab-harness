DONE

둘 다 전부 통과했고 시험 수는 `tests/test_rt_claude.py` 24→28, `tests/test_fleet_graph.py` 73→77 로 늘었습니다. 제품 결함은 없었고 `tools/**` 는 읽기만 했습니다.

**고친 파일**
- `tests/test_rt_claude.py`
  - `test_other_error_false` 를 `test_other_error_none` 으로 바꾸고 `assertIsNone` 으로 고쳤습니다(V19).
  - 새 시험 4개를 더했습니다.
    - `test_error_without_marker_even_with_limit_text_is_none`: `"You've hit your 5-hour limit"` 에 표지가 없으면 `None` 인지 봅니다.
    - `test_api_error_branch_ignores_non_usage_limit_phrases`: `terminal_reason=api_error` 와 요청하신 세 문구에서 각각 `True` 가 아님을 `subTest` 로 봅니다.
    - `test_result_limit_signal_direct_events_rejected_is_true`: 시험 수 28을 채우려고 제가 더한 시험입니다. `result_limit_signal` 을 직접 불러 거절 사건이 있으면 `True`, 없으면 `None` 인지 봅니다.
    - `test_result_limit_signal_direct_non_dict_is_none`: `result_limit_signal` 을 직접 불러, dict 가 아닌 입력(`None`, 문자열, 목록, 숫자)에서 `None` 인지 봅니다.
- `tests/test_fleet_graph.py`
  - Q2 세션 갈래 시험 3개를 더했습니다. 이름은 `test_q2_session_branch_n3_record_is_none`, `test_q2_session_branch_context_window_text_is_not_true`, `test_q2_session_branch_429_is_true` 입니다. 임시 폴더를 세션 폴더로 쓰게 하려고 `fleet._sessions_root` 를 `mock.patch` 했습니다(`fleet._session_dir` 를 직접 패치하지 않고, 그것이 부르는 `_sessions_root` 를 패치). 도우미 `_session` 은 `meta.json` 과 `events.jsonl`(`<시각>\t<json>`)을 만듭니다.
  - Q1 `test_q1_run_id_with_path_segments_is_none` 은 `"R-1/../../outside/evil"` 과 `"T-1-S1-a1-000000/../x"` 가 `None` 인지 봅니다. 앞의 것은 실제로 `evil.json`·`evil.out` 을 만들어 두어, 경로 검사를 걷어내면 `True` 가 나오는 꼴입니다.
  - Q5 `test_run_limit_signal_is_none_for_text_only_harnesses` 의 `.out` 을 글자 `"DONE: something"` 으로 되돌렸습니다. claude 꼴 JSON 은 `test_m6_non_claude_harness_ignores_claude_shaped_json` 이 맡습니다.

**돌린 검증**
`python3 -m unittest tests.test_rt_claude tests.test_fleet_graph` 는 `_fleet_env` 를 못 찾아 import 에 실패했습니다. `tests/` 가 경로에 있어야 하니 `discover -s tests` 로 돌리십시오.
- `python3 -m unittest discover -s tests -p "test_rt_claude.py"` → `Ran 28 tests ... OK`
- `python3 -m unittest discover -s tests -p "test_fleet_graph.py"` → `Ran 77 tests ... OK`

**다음 담당자에게**
- 위 명령 중 `test_rt_claude.py` 28개 통과는 마지막 시험을 더한 뒤에 다시 확인했습니다. 중간에는 27개였습니다.
- 쓴 경로는 슬롯 소유 경로 안의 두 파일뿐입니다.