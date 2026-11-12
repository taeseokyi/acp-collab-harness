# R22 2차 재검수 (T-269, S1, G-053) - P1·P2·P3·Q1·Q2·Q5 가 정말 닫혔는가

- 대상: 작업 트리의 미커밋 수정 (`tools/fleet_rt/harness/claude.py`, `tools/fleet_graph.py`, `tests/test_fleet_graph.py`, `tests/test_rt_claude.py`) - REV 164 위
- 방법: `/tmp/r22b-review` 사본 (`python3 shutil.copytree`, `.git`·`__pycache__`·`tls`·`runs`·`sessions` 제외 - `.aimem/tls` 없음 확인).
  재현 `/tmp/r22b-tools/repro.py` (같은 기록을 옛 `.aimem/runs/<id>.out` 과 세션 `events.jsonl` 에 나란히 두고 `run_limit_signal`·어댑터·공용 함수를 함께 부름),
  변이 `/tmp/r22b-tools/mut.py` (조각 교체 → 시험 → 복원), 전수 `/tmp/r22b-tools/survey.py` (진짜 `.aimem/runs`·`.aimem/sessions` 읽기만).
  끝난 뒤 두 `/tmp` 폴더는 지웠습니다. 저장소에서 고친 파일은 이 보고서 하나입니다.
- 기준선:
  - `python3 -m unittest discover -s tests -p test_fleet_graph.py` → `Ran 77 tests ... OK`
  - `python3 -m unittest discover -s tests -p test_rt_claude.py` → `Ran 28 tests ... OK`
  - **`python3 -m unittest discover -s tests` (CLAUDE.md 가 정한 명령) → `Ran 940 tests in 135.9s FAILED (failures=1, skipped=1)`,
    실패는 `test_q2_session_branch_429_is_true` 하나 (`AssertionError: None is not True`)** → 새 결함 R1

## 1. 닫힘표

| 번호 | 닫혔나 | 근거 |
| --- | --- | --- |
| P1 (오류 + 표지 없음 → `None`, 세션 경로) | 닫힘 | `repro.py`: `{"is_error":true,"result":"You've hit your 5-hour limit · resets 11:20am"}` → 옛 경로 `None` / 세션 경로 `run_limit_signal("T-0-S1-a1-000000")` `None` / 어댑터 `None` / 공용 `result_limit_signal` `None`. `"Claude AI usage limit reached\|..."`·`api_error_status 500` 도 넷 다 `None`. 1차 때 세션 쪽은 `False` 였음 |
| P2 (`_limit_text` 삭제, 좁은 목록) | 닫힘 | `_limit_text` 가 없어지고 api_error 갈래가 `limit_text_hit` 를 씀. `"Prompt exceeds the context window limit"`·`"max_tokens limit: output token limit exceeded"`·`"API Error: 400 ... exceed context limit"` → 옛·세션·어댑터·공용 넷 다 `None` (1차 때 세션 쪽은 `True`). `api_error` + `"You've hit your limit"`·`429` 는 넷 다 `True` |
| P3 (판정 한 벌) | 닫힘 | `fleet_graph._limit_text_hit is claude.limit_text_hit` = `True`, `fleet_graph._result_limit_signal is claude.result_limit_signal` = `True`. `report_limit_hit` 는 `limit_text_hit` 에 위임만 함. 옛 경로 판정을 옛 사본으로 되돌리는 W04, 넓은 목록을 따로 두는 W05 모두 잡힘. (군더더기: `fleet_graph.py:52` 의 `LIMIT_PATTERNS as _LIMIT_PATTERNS` 는 import 만 되고 쓰는 곳 없음 - 정보) |
| Q1 (`/` 반례) | **안 닫힘 → R2** | 제품은 `/` 를 막습니다 (`T-1-S1-a1-000000/../../outside/evil` → `None`). 그러나 새 시험 `test_q1_run_id_with_path_segments_is_none` 은 **있는 폴더를 딛고 나가는 꼴을 만들지 않아서** 변이 V08 (몸에 `/` 허용) 이 그대로 삽니다. 같은 V08 에서 세션 폴더 `T-1-S1-a1-000000` 을 만들어 두면 `run_limit_signal("T-1-S1-a1-000000/../../outside/evil")` = **`True`** (저장소 밖 `meta.json`·`events.jsonl` 을 읽음) |
| Q2 (세션 갈래 시험) | **반만 닫힘 → R1** | 모듈 하나만 돌리면 세 시험이 세션 갈래를 타고 V21·W01 을 잡습니다. 그러나 전체 `discover` 에서는 다른 시험 모듈이 먼저 불러온 `tests/_fleet_env.py:10` 이 `AIFLEET_HARNESS=fake` 를 깔아, `fleet_rt.harness.get("claude")` 가 **fake 어댑터**를 줍니다. 그래서 `429` 시험은 빨갛고, `n3`·`context window` 시험 둘은 fake 가 `None` 을 돌려줘서 **공짜로 통과**합니다 (claude 어댑터를 안 탐) |
| Q5 (글자 `.out` 시험 복원) | 닫힘 | `test_run_limit_signal_is_none_for_text_only_harnesses` 가 글자 `.out`(`"DONE: something"`)으로 돌아왔고, JSON 꼴은 `test_m6_*` 가 맡습니다. W13 (`harness == "claude"` 검사 지우기) → `test_m6_*` 2건 FAIL. 원래 글자에 있던 한도 문구(`5-hour limit reached`)는 빠졌지만 어느 쪽이든 JSON 파싱 실패로 `None` 이라 차이는 없음 |
| V19 (`test_other_error_false` → `none`) | 닫힘 | `test_other_error_none` 이 `assertIsNone`. V19 (공용 함수 끝 `return False`) → `test_rt_claude` 3건·`test_fleet_graph` 5건 FAIL (1차 때는 거꾸로 잡혔음) |

## 2. 새 결함표

| 번호 | 심각도 | 무엇이 | 어디 | 재현 | 고칠 방향 |
| --- | --- | --- | --- | --- | --- |
| R1 | 중간 (전체 시험이 빨감, Q2 시험 둘은 아무것도 안 잼) | `_session()` 도우미가 `meta.json` 에 `harness_effective: "claude"` 라고 쓰지만, 전체 `discover` 에서는 `AIFLEET_HARNESS=fake` 때문에 fake 어댑터로 갑니다. 결과는 실행 순서에 따라 갈립니다. 모듈 하나만 돌리면 통과하고, 프로젝트의 정식 명령으로 돌리면 빨갛습니다. 수정자는 모듈 단위로만 돌린 것으로 보입니다 | `tests/test_fleet_graph.py` `_session` (`test_q2_*` 3건), `tests/_fleet_env.py:10`, `tools/fleet_rt/harness/__init__.py:15-17` | `python3 -m unittest discover -s tests` → `FAILED (failures=1)` `test_q2_session_branch_429_is_true: None is not True`. 사본에서 `import _fleet_env` 뒤 `test_fleet_graph` 만 돌려도 같은 실패 | `_session` 에서 `mock.patch.dict(os.environ, {"AIFLEET_HARNESS": ""})` 를 걸거나, `fleet_rt.harness.get` 을 claude 어댑터로 고정하세요. 그 뒤 `n3`·`context window` 시험이 claude 어댑터를 탔는지 단언합니다 (예: `assertIsNot(sig, True)` 대신 `assertIsNone` 을 쓰고, `429` 시험과 짝지어 같은 도우미가 `True` 도 낼 수 있음을 보이기) |
| R2 | 낮음 | Q1 시험의 반례(`R-1/../../outside/evil`, `T-1-S1-a1-000000/../x`)는 디딤 폴더(`runs/R-1/`·`sessions/T-1-S1-a1-000000/`)가 없어서 OS 가 경로를 못 풀고 실패합니다. 그래서 정규식이 `/` 를 허용해도 결과는 `None` 입니다 | `tests/test_fleet_graph.py` `test_q1_run_id_with_path_segments_is_none` | 변이 V08 → 77 OK. 같은 변이에서 디딤 폴더를 만들면 탈출해 `True` (위 닫힘표 Q1) | 시험 안에서 `sessions/T-1-S1-a1-000000/meta.json` 과 `outside/evil/{meta.json,events.jsonl(429)}` 를 만들고 `T-1-S1-a1-000000/../../outside/evil` 이 `None` 인지 단언하세요 (R1 고침과 같이 해야 claude 어댑터까지 닿음) |
| R3 | 정보 | `"hit your limit"` 추가는 판정을 늘리지 않았습니다. 진짜 기록 290건(runs + sessions) 전수: 구조 신호 `None 209 / False 80 / True 1`, rc≠0 이라 글자 판정으로 가는 건 4건, 최종 한도는 1건(`T-215-S1-a1-101031`, 진짜 5-hour 한도)이고 옛 목록으로 셈해도 1건. 보고 글자에 `"hit your limit"` 이 들어간 것은 `T-267-S2-a1-235730` 하나인데, **수정 보고가 그 문구를 인용한 것**입니다 (rc 0·구조 `False` 라 판정에는 영향 없음). 날 기록에서 이 문구가 나오는 파일 5개도 모두 R22 검수·수정 세션이 문구를 언급한 것입니다. 글자 판정은 인용과 진짜를 구별하지 못하므로, rc≠0 인 보고가 이 문구를 인용하면 오인합니다 (지금 0건) | `tools/fleet_rt/harness/claude.py:92-99` | `python3 /tmp/r22b-tools/survey.py <사본> <저장소>` | 없음 (기록). 걱정되면 판정 범위를 보고 마지막 몇 줄로 좁히세요 |
| R4 | 정보 | import 는 문제없습니다: 사본 `tools` 만 경로에 두고 `import fleet_graph` 단독 → 성공. `fleet_rt.harness.claude` → `fleet_graph` 순서로 불러도 성공. `fleet_graph.py --help` 정상. `fleet` 은 `fleet_graph`·`claude` 를 부르지 않고, `fleet_rt` 쪽에서 `fleet_graph` 를 부르는 곳도 없습니다 (`fleet_ctl`·`server` 만 지연 import). 다만 이제 `fleet_graph` 가 import 시점에 `fleet_rt` 패키지에 묶입니다 (예전에는 세션 갈래에서만 지연 import) | `tools/fleet_graph.py:51-52` | 위 명령 | 없음 |

## 3. 변이표

"잡혔나" 는 모듈 단위(`test_fleet_graph`, `test_rt_claude` 를 따로 실행) 기준입니다. 전체 `discover` 순서(fake 아래)에서는 기준선부터 `test_q2_session_branch_429_is_true` 가 빨갛습니다. 그래서 V21·W01 은 그 모드에서 `test_fleet_graph` 로는 기준선과 구별되지 않습니다. W01 은 `test_rt_claude` 가 따로 잡습니다.

| 변이 | 잡혔나 |
| --- | --- |
| V08 `_RUN_ID_RE` 몸에 `/` 허용 | × 생존 (R2) |
| V19 공용 `result_limit_signal` 끝 `return None` → `False` (P1 되돌림) | ○ fleet_graph 5건·rt_claude 3건 |
| V20 api_error 갈래에 `'limit' in v` 부분 일치 되살리기 (P2 되돌림) | ○ `test_n4_*`·`test_q2_..._context_window_*`·`test_api_error_branch_ignores_*` ×3 |
| V21 `run_limit_signal` 세션 갈래 끄기 | ○ `test_q2_session_branch_429_is_true` (모듈 단위에서만 의미 있음, R1) |
| W01 어댑터만 `or False` (P1 을 세션 경로에서만 되돌림) | ○ `test_q2_..._n3_*`, rt_claude `test_other_error_none`·`test_error_without_marker_*` |
| W02 fleet_graph 옛 경로만 `or False` (N3 되돌림) | ○ 5건 |
| W03 공용 `limit_text_hit` 에 `'limit'` 부분 일치 | ○ fleet_graph 4건·rt_claude 3건 |
| W04 옛 경로에 옛 판정 사본 되살리기 (P3 되돌림) | ○ 5건 |
| W05 `report_limit_hit` 를 따로 둔 옛 넓은 목록으로 (P3 되돌림) | ○ `test_n5_*` |
| W06 `"hit your limit"` 빼기 | ○ rt_claude `test_api_error_text` |
| W07 `"limit reached"` 다시 넣기 | ○ `test_n5_*` |
| W08 `"too many requests"` 다시 넣기 | ○ `test_n5_*` |
| W09 `rate_limit_event` 거절 갈래 끄기 | ○ rt_claude 2건 |
| W10 `result_limit_signal` 비 dict 검사 지우기 | ○ rt_claude ERROR ×4 |
| W11 `limit_text_hit` 끝 2000자 제한 지우기 | ○ fleet_graph 2건 |
| W12 사건 `isinstance(d, dict)` 검사 지우기 | — 동치 (`_events` 가 `_parse_json` 으로 dict 만 넘기고 fleet_graph 는 `events=()`), 합계 제외 |
| W13 `harness == "claude"` 검사 지우기 (M6·Q5) | ○ `test_m6_*` ×2 |

합계 16개: 잡힘 15, 생존 1

## 4. 총평

제품 코드 쪽은 **닫혔습니다.** 한도 판정은 이제 `fleet_rt/harness/claude.py` 의 `result_limit_signal`·`limit_text_hit` 한 벌이고, `fleet_graph` 는 그 같은 함수 객체를 부릅니다. 그래서 1차에서 갈라졌던 두 경로가 같은 기록 10종에 대해 옛 경로·세션 경로·어댑터·공용 함수 넷 다 같은 답을 냅니다. N3 꼴은 `None` 이 되어 글자 판정으로 넘어가고, 컨텍스트·출력 한도 문구는 `True` 가 아니며, `429`·api_error 와 한도 문구 조합은 `True` 입니다(P1·P2·P3). 이번 수정을 옛 모습으로 되돌리는 변이 W01~W11·W13 과 1차 V19·V20·V21 이 모두 잡혔습니다. 진짜 기록 290건 전수에서 `"hit your limit"` 추가로 늘어난 오인은 없고(최종 한도 1→1), import 순환도 없습니다. **그러나 시험 쪽 둘이 덜 닫혔습니다.** 첫째(R1, 중간), Q2 의 세션 시험은 모듈 하나만 돌릴 때만 claude 어댑터를 탑니다. 프로젝트의 정식 명령 `python3 -m unittest discover -s tests` 에서는 `AIFLEET_HARNESS=fake` 때문에 fake 어댑터로 가서 **940개 중 1개가 빨갛고**, 다른 둘은 아무것도 재지 않고 통과합니다. 커밋 전에 꼭 고쳐야 합니다. 둘째(R2, 낮음), Q1 시험은 디딤 폴더를 만들지 않아 `/` 허용 변이(V08)를 못 잡습니다. 지금 제품은 막고 있으니 되돌림을 감시하는 문제입니다. 다음 수정 슬롯은 `_session` 도우미에서 fake 강제를 풀고, Q1 반례를 있는 세션 폴더 위에서 다시 세운 뒤, **전체 discover** 로 확인하십시오.
