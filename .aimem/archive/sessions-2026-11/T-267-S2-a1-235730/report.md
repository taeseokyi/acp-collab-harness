DONE

**한 일**
- `tools/fleet_rt/harness/claude.py`: 판정을 이 파일 한 벌로 모았습니다.
  - `LIMIT_PATTERNS`(`fleet_graph` 에 있던 목록과 같고 `"hit your limit"` 을 더했습니다), `limit_text_hit(text)`, `result_limit_signal(res, events=())` 를 추가했습니다.
  - `result_limit_signal` 은 지시한 순서대로 판정하고, 표지가 없는 오류는 `None` 을 돌려줍니다.
  - `_limit_text` 는 지웠습니다. `limit_signal(session_dir)` 은 마지막 result 를 찾아 `result_limit_signal` 을 부를 뿐이며, result 가 없거나 예외가 나면 `None` 입니다.
- `tools/fleet_graph.py`
  - `_LIMIT_PATTERNS` 는 `from fleet_rt.harness.claude import ...` 로 옮겨 온 것을 가리킵니다. import 는 파일 위쪽 `import fleet` 바로 아래에 두었고 순환 문제는 없었습니다.
  - `report_limit_hit` 은 `limit_text_hit` 를 부르게 했습니다. 이름과 docstring 은 그대로입니다.
  - 옛 `.out` 경로는 `json.loads` 뒤에 `_result_limit_signal(data)` 만 부릅니다. run_id 꼴 검사, `fleet._session_dir`, 1MiB 읽기는 그대로입니다.
- `tests/**` 와 다른 파일은 건드리지 않았습니다.

**검증**

| 명령 | 결과 |
|---|---|
| `python3 -m unittest tests.test_fleet_graph tests.test_fleet_ctl tests.test_fleet` | 123개 OK |
| `python3 -m unittest discover -s tests -p "test_rt_*.py"` | 175개 중 실패 1개 |
| 위 명령에서 실패한 시험 | `test_rt_claude.LimitTest.test_other_error_false` 하나뿐 |
| `python3 -m unittest discover -s tests -p "test_rt_claude.py"` | 24개 중 같은 시험 1개 실패 |

그 시험이 실패하는 것은 지시하신 대로입니다. 옛 `False` 를 못박고 있어서, 다음 노드가 `None` 으로 고쳐야 합니다.

`PYTHONPATH=tools python3 -c ...` 로 세션 폴더 `events.jsonl` 에 직접 써서 확인한 결과:
- `_LIMIT_PATTERNS is claude.LIMIT_PATTERNS` → `True`
- `report_limit_hit("You've hit your limit · resets 11am")` → `True`
- 오류 + `"You've hit your 5-hour limit"` 만 있을 때 → `None`
- `terminal_reason=api_error` + `"Prompt exceeds the context window limit"` → `None`
- `api_error_status=429` → `True`
- 성공 → `False`

**다음 담당자에게**
- 처음에 `xargs` 로 파일 경로를 넘긴 시도는 `_fleet_env` import 오류로 실패했습니다. 시험은 `discover -s tests -p ...` 로 돌려야 합니다.
- 작업 트리에 있던 `_LIMIT_PATTERNS` 는 HEAD 보다 짧아서 `"limit reached"` 와 `"too many requests"` 가 이미 빠져 있었습니다. 지시대로 작업 트리 쪽 목록을 옮겼고 이번에 더한 것은 `"hit your limit"` 뿐입니다.
- `report_limit_hit` 의 `"limit reached"` 부분 일치가 필요한 시험이 있다면 다음 노드가 확인해야 합니다. 다만 `test_fleet_graph` 는 통과했습니다.