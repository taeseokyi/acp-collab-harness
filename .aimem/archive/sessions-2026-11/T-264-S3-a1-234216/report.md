DONE

**한 일**
- `tests/test_fleet_graph.py` 에 시험 14건을 보태 59건에서 **73건**이 됐습니다. 다른 파일은 건드리지 않았습니다.
- 제품 코드 수정 없이 모두 통과했습니다. `NEEDS-FIX` 대상은 없습니다.
- N3, M3~M8, N4, N5, N7 은 각각 아래 시험이 맡습니다.

| 항목 | 시험 |
|---|---|
| N3 | `is_error` 참 + 표지 없음 → `None`, `is_error` 거짓 → `False`, `step()` 이 글자 판정으로 `blocked` + `limit` |
| M3 | `is_error: false` 에 429 · `api_error` 를 섞어도 `False` |
| M4 | `terminal_reason: "api_error"` + 한도 문구만 있는 기록 → `True` |
| N4 | `api_error` + "context window limit" → `None` |
| M5 | `step()` 단 N3 시험이 겸함. N3 기록으로 rc 1 실행을 꾸며 `blocked`, `limit` 참, `verify_rc` -4 를 확인 |
| M6 | codex·opencode 의 `.out` 을 claude 꼴 JSON 으로 바꿔도 `None` |
| M7 | 1 MiB + 4 KiB 파일, 끝까지 읽으면 올바른 JSON(`True`), 1 MiB 에서 자르면 깨짐(`None`) |
| M8 | 로그에 `(구조 신호)` / `(보고 글자)` 가 각각 들어 있고 서로 상대를 포함하지 않음 |
| N5 | `report_limit_hit` 에서 "time limit reached"·"HTTP 429" 보고는 `False`, "weekly limit" 은 `True` |
| N7 | `../outside/evil` 은 `runs/` 밖에 `evil.json`·`evil.out` 을 실제로 두고도 `None`. `run_id` 가 `str` 이 아닌 값(`None`, 123, list, bytes, dict)도 `None` |

- M7 은 앞머리만 맞추지 않고 끝까지 읽으면 `True` 가 되도록 올바른 JSON 으로 만들었습니다. 그래서 상한이 없어지면 시험이 실패합니다.
- 기존 `test_run_limit_signal_is_none_for_text_only_harnesses` 의 `.out` 자료만 `{"is_error": true, "api_error_status": 429}` 로 바꿨습니다(M6 지시).
- `fleet.RUNS` 와 `GRAPHS` 는 기존 `setUp` 의 임시 폴더 패치를 그대로 썼고, 실제 작업자는 띄우지 않았습니다.

**검증**
- 첫 줄: `python3 tools/aimem_db.py check --slot S3 --token 5b8c1e --rev 164` → `일치: S3 ... REV 164`.
- `python3 -m unittest tests.test_fleet_graph` → `Ran 73 tests in 0.604s`, `OK` (rc 0).
- 변이를 직접 넣어 시험이 실패하는지는 돌려 보지 않았습니다. 검수가 알려 준 구멍을 시험 설계로 메웠을 뿐입니다.

**다음 담당자에게**
- 시험 안의 `_step_rc1` 은 `verify` 가 불리지 않았는지도 함께 단정합니다. `step()` 이 한도 갈래에서 `verify` 를 건너뛰는 동작이 바뀌면 여러 시험이 한꺼번에 깨집니다.
- 이번 시험은 구 방식(`.aimem/runs/<id>.json`) 경로만 다룹니다. `fleet._session_dir` 가 새 세션 폴더를 돌려주는 경로는 이 시험 밖입니다.