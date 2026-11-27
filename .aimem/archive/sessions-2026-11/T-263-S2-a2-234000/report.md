DONE

`run_limit_signal` 의 결함 넷(N3·N4·N5·N7)을 `tools/fleet_graph.py` 에서 고쳤습니다. 다른 파일은 건드리지 않았고 `step()` 도 그대로입니다.

**고친 것**
- **N3:** `is_error` 가 참인데 표지가 없으면 `False` 대신 `None` 을 돌려줍니다. `False` 는 `is_error` 가 거짓일 때만 나옵니다. 까닭은 주석 한 줄과 docstring 에 적었습니다.
- **N4:** `terminal_reason == "api_error"` 갈래에서 `or "limit" in value.lower()` 를 지우고 `report_limit_hit(value)` 만 씁니다.
- **N5:** `_LIMIT_PATTERNS` 에서 `"limit reached"` 와 `"too many requests"` 만 지웠습니다. `"hit your weekly limit"`·`"hit your usage limit"` 와 나머지 항목은 그대로입니다.
- **N7:** `run_limit_signal` 맨 앞에 run_id 검사를 두었습니다. 문자열이 아니거나 128자를 넘거나 `_RUN_ID_RE` 에 안 맞으면 `None` 입니다.

**정규식을 브리프와 다르게 썼습니다.** 브리프의 `[A-Za-z0-9._-]+` 는 `..` 를 통과시킵니다. 그러면 `fleet._session_dir("..")` 가 세션 루트 밖으로 나갈 수 있어서, 첫 글자를 영숫자로 요구하는 `\A[A-Za-z0-9][A-Za-z0-9._-]*\Z` 로 했습니다.

실제 `reader.RUN_ID_RE`(`aimem_monitor/__init__.py:125`)는 이보다 더 엄격합니다. `T-053-S3-a3-181328`, `20261109-172618-S3`, `M-R21-193012` 꼴만 받습니다. 그 꼴을 그대로 쓰면 임의 이름의 검증용 가짜 기록이 전부 `None` 이 될 수 있어 쓰지 않았습니다. 같은 엄격함이 필요하면 알려 주십시오.

**돌린 검증**
- `python3 -m unittest tests.test_fleet_graph tests.test_fleet_ctl tests.test_fleet` 결과는 `Ran 109 tests ... OK` 입니다.
- 임시 폴더의 가짜 기록 여섯(429 / 5시간 문구만 있음 / 오류 아님 / 컨텍스트 창 한도 / codex 하네스 / 깨진 JSON)에 `run_limit_signal` 을 돌린 결과는 `[True, None, False, None, None, None]` 입니다.
- `run_limit_signal("../outside/evil")`, `".."`, `None` 은 모두 `None` 입니다.
- `report_limit_hit` 의 오인 둘(`"...time limit reached..."`, `"...429 Too Many Requests"`)은 `False` 가 되었고, `"You've hit your weekly limit"` 는 `True` 로 남았습니다.
- 검증용 스크립트 `/tmp/s2_check.py` 는 저장소 밖에 둡니다.

**다음 담당자가 알 것**
- 현재 코드에는 브리프에 없던 세션 분기가 있습니다(`fleet._session_dir` → `rt_harness...limit_signal(sd)`). 이 분기는 그대로 두었습니다. 거기서 오는 `False` 가 글자 판정을 가리는지는 `fleet_rt/harness.py` 에서 따로 봐야 하며, 이번 범위 밖이라 읽지 않았습니다.
- 5시간 한도 문구만 있는 `is_error` 기록은 이제 `None` 이 되어 `step()` 이 글자 판정으로 넘깁니다.
- 처음에 CLAUDE.md 예시의 `--rev 114` 를 그대로 써서 불일치가 났습니다. 지시문의 REV 164 로 다시 돌려 일치했고, 그 전에는 파일을 쓰지 않았습니다.
- 커밋·푸시는 하지 않았습니다.