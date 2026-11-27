# R22 재검수 (T-266, S1, G-052) - R20 결함 N1~N7·M3~M8·M11 이 정말 닫혔는가

- 대상: 작업 트리의 미커밋 수정 3파일 (`tools/fleet_graph.py`, `tests/test_fleet_graph.py`, `tests/browser_monitor_ui.py`) - REV 164 위
- 방법: `/tmp/r22-review` 사본 (`python3 shutil.copytree`, `.git`·`__pycache__`·`.aimem/tls`·`.aimem/runs`·`.aimem/sessions` 제외).
  재현은 `/tmp/r22-tools/repro.py` (사본의 `fleet_graph`·`fleet_rt.harness.claude` 를 임시 runs/sessions 로 직접 호출),
  변이는 `/tmp/r22-tools/mut.py` (사본 파일 한 조각을 바꾸고 시험 실행 → 원문 복원, 치운 파일도 복원).
  전수 재검은 `/tmp/r22-tools/survey.py` - **진짜 저장소의 `.aimem/runs`(277)·`.aimem/sessions`(10) 를 읽기만** 하고
  옛 판정(`git show HEAD:tools/fleet_graph.py`)과 새 판정을 나란히 셈.
  저장소 원본은 이 파일 말고 고치지 않았습니다.
- 기준선 (변이 없음, 사본): `test_fleet_graph` 73 OK 0.68s / `test_rt_claude` 24 OK / `test_fleet` 10 OK / `test_fleet_ctl` 40 OK /
  `test_rt_integration` 18 OK 17.9s / `browser_monitor_ui.py` 27/27 (rc 0)

## 1. 닫힘표

| 번호 | 닫혔나 | 근거(명령과 결과) |
| --- | --- | --- |
| N3 (옛 경로 `.aimem/runs`) | 닫힘 | `python3 /tmp/r22-tools/repro.py` → `{"is_error": true, "result": "You've hit your 5-hour limit · resets 11:20am"}` = `None`, `report_limit_hit` = `True` (1차: `False`). `"Claude AI usage limit reached\|1731400000"` 도 `None`/`True`. `step()` 시험 `test_n3_step_falls_through_to_text_judgement_and_blocks` 가 blocked·limit 단언 |
| N3 (새 엔진 경로 `.aimem/sessions`) | **안 닫힘 → P1** | 같은 기록을 세션 `events.jsonl` 의 result 사건으로 두면 `fleet_rt.harness.claude.ADAPTER.limit_signal` = `False`, `fleet_graph.run_limit_signal("T-1-S1-a1-000000")` = `False` → `step()` 이 글자 판정을 건너뜀. `tools/fleet_rt/harness/claude.py:237` 이 아직 `return False` |
| N4 (옛 경로) | 닫힘 | `{"is_error": true, "terminal_reason": "api_error", "result": "Prompt exceeds the context window limit"}` → `None` (1차 `True`), 글자 판정도 `False` → 재시도. `"max_tokens limit: output token limit exceeded"` 도 `None` |
| N4 (새 엔진 경로) | **안 닫힘 → P2** | 같은 기록 세션 경로 → `True`. `fleet_graph.run_limit_signal(<세션 id>)` 도 `True`. `claude.py:92-94` `_limit_text` = `"limit" in v or ...` (1차 N4 와 같은 부분 일치) |
| N5 | 닫힘 | `report_limit_hit("NEEDS-FIX: verify step time limit reached, test failed")` = `False`, `report_limit_hit("DONE - added handler for HTTP 429 Too Many Requests")` = `False` (1차 둘 다 `True`). 진짜 기록 287건 전수에서 최종 한도 판정 수 변화 없음 (1→1) |
| N7 | 닫힘 | `run_limit_signal("../outside/evil")` = `None` (1차 `True`), 절대 경로 `/tmp/.../outside/evil` = `None`, `"R-1\n"` = `None`(`\Z`), 비문자열 5종 `None`. 진짜 id 287건 모두 새 정규식 통과(옛·새 sig 분포 동일) |
| M3 | 닫힘 | 변이 V11 (`is_error` 검사 지우기) → `test_fleet_graph` FAILED (failures=4) |
| M4 | 닫힘 | V12 (`terminal_reason` 갈래 끄기) → `test_m4_terminal_reason_api_error_branch_alone_is_true` FAIL. V02 (`"limit"` 부분 일치 되살리기) → `test_n4_context_window_limit_is_not_a_usage_limit` FAIL |
| M5 | 닫힘 (옛 경로만) | V01 (N3 되돌림) → FAILED (failures=4, `test_n3_*` 포함). 새 엔진 경로는 시험 없음 → Q2 |
| M6 | 닫힘 | V13 (`harness == "claude"` 검사 지우기) → FAILED (failures=4) - codex/opencode 시험의 `.out` 을 claude 꼴 JSON 으로 바꾼 효과 |
| M7 | 닫힘 | V14 (`f.read()` 로 상한 지우기) → `test_m7_read_is_capped_at_one_mib` FAIL |
| M8 | 닫힘 | V15 (출처 표시 뒤집기) → `test_m8_log_marks_structural_source`·`..._report_text_source` FAIL (failures=2) |
| N1 | 닫힘 | 사본 `projects/` 를 통째로 치우고 `python3 tests/browser_monitor_ui.py` → rc 0, `통과 27 / 전체 27` (1차: FileNotFoundError, 3/4). `write_fixed_project` 가 `app.json`·`web/index.html`(타일 30)·`PROGRESS.md` 를 직접 씀 |
| N2 | 닫힘 (단, 잔여 의존 Q3) | 사본 `.aimem/aimem.db`(+wal/shm) 를 치우고 돌림 → rc 0, 27/27 (1차: 26/27 '생략된 제목' FAIL). `changed_ui_scenario` 가 `temporary_aimem_root` 안 `monitor_server(root=temp_root)` 로 감. 다만 '이번 라운드' 값은 아직 사본의 `rounds/`·`.aimem/fleet-*.json` 에서 옴 (`R22 · 2026-11-12 23:38 관리자 끊김(감독 사라짐)`) - 그것까지 치우면 `띄운 라운드 없음 실행` 으로 바뀌고 통과 |
| M11 | 닫힘 | `show_all_projects` 가 무조건 `click(timeout=5000)`. 변이 B2 (app.js 프로젝트 필터에서 '전체' 칩 지우기) → `[FAIL] 검사 실행 - TimeoutError: Locator.click: Timeout 5000ms exceeded.` 3/4. B1 (칩 안 누르기) → '앱 열기' FAIL 3/5 - 고정 자료에 진행 중 프로젝트(`진행앱`)가 있어 칩이 꼭 필요함 |
| N1·N2 되돌림 감시 | 환경으로만 지켜짐 (정보) | B4 (N1 되돌림, 정상 사본) → 27/27 생존, B5 (되돌림 + `projects/` 치움) → FAIL. B6 (N2 되돌림 + db 치움) → '생략된 제목' FAIL 26/27. 되돌림은 저장소 상태가 비었을 때만 빨개짐 - 1차 R-* 변이와 같은 성질이라 막을 수 없는 것은 아님(정보) |

## 2. 새 결함표

| 번호 | 심각도 | 무엇이 | 어디 | 재현 | 고칠 방향 |
| --- | --- | --- | --- | --- | --- |
| P1 | 중간 (N3 과 같은 피해, 그러나 **지금 실제로 도는 경로**) | N3 수정이 옛 `.aimem/runs` 경로에만 들어갔습니다. REV 163 부터 작업자는 `fleet_rt` 세션(`.aimem/sessions/<id>`)이고, `run_limit_signal` 은 세션 폴더가 있으면 `rt_harness...limit_signal(sd)` 로 넘깁니다. 그 claude 어댑터는 `is_error: true` + 구조 표지 없음에서 여전히 `False` → `step()` 이 글자 판정을 건너뛰어 진짜 한도가 **보통 실패로 재시도** | `tools/fleet_rt/harness/claude.py:210-239` (마지막 `return False`), 경로는 `tools/fleet_graph.py:467-470` | `repro.py`: 세션 `events.jsonl` 에 `{"type":"result","is_error":true,"result":"You've hit your 5-hour limit · resets 11:20am"}` → 어댑터 `False`, `fleet_graph.run_limit_signal("T-1-S1-a1-000000")` `False`. 수정자 T-264 의 보고도 "이번 시험은 구 방식 경로만 다룹니다" 라고 적음 | 어댑터 끝(거절 사건도 없을 때)을 `return None` 으로. `tests/test_rt_claude.py:196` `test_other_error_false` 가 지금 **옛 동작을 못박고** 있으므로 함께 바꾸기(V19) |
| P2 | 중간 | N4 와 같은 결함이 새 엔진 어댑터에 그대로: `terminal_reason == "api_error"` 갈래의 `_limit_text` 가 `"limit" in v` 부분 일치라 컨텍스트 창·출력 토큰 한도 오류를 사용 한도로 보고 blocked (재시도 안 함) | `tools/fleet_rt/harness/claude.py:92-94`, `:225-230` | `repro.py`: 세션 경로 `"Prompt exceeds the context window limit"` → `True`, `"max_tokens limit: output token limit exceeded"` → `True`, `"API Error: 400 input length and max_tokens exceed context limit"` → `True` | `_limit_text` 를 `fleet_graph.report_limit_hit` (좁힌 문구 목록)로 바꾸기 - 판정 함수를 한 곳에 두기 |
| P3 | 낮음 | 한도 판정이 **두 벌**(`fleet_graph.run_limit_signal` 과 `fleet_rt/harness/claude.py limit_signal`)이고 "옮긴 것"이라 적혀 있지만 이미 어긋났습니다 (N3·N4 수정, 거절 사건 갈래는 어댑터에만). 다음 수정도 한쪽에만 들어갈 구조 | 두 파일 | `diff` 로 비교: 끝 `return None` vs `return False`, `report_limit_hit` vs `_limit_text`, `rate_limit_event` 갈래는 어댑터에만 | result 사건 dict 하나를 받는 판정 함수 하나로 모으고 두 경로가 그것을 부르기 |
| P4 | 정보 | N6 (FIFO 에서 영영 막힘)·N8 (메타 상한 없음) 은 이번 수정 대상이 아니라 그대로 열려 있습니다 | `tools/fleet_graph.py:474-475`, `tools/fleet.py:373-374` | 코드 읽어 확인 (`open("rb").read(1MiB)`·`read_text()` 그대로, `S_ISREG` 검사 없음) | 1차 N6·N8 의 방향 그대로 |
| P5 | 정보 | `run_limit_signal` 이 `None` 을 더 자주 돌려주게 됐지만, 진짜 기록 287건(runs 277 + sessions 10) 전수에서 오인이 늘지 않았습니다: sig 분포 옛·새 모두 `None 209 / False 77 / True 1`, rc≠0 에서 글자 판정으로 가는 건 옛·새 4건, 최종 한도 판정 옛·새 1건(`T-215-S1-a1-101031`, 진짜 5-hour 한도). 글자 적중은 13→12 (빠진 1건 `T-264-S3-a1-234216` 은 rc 0 이라 원래 판정 밖). 지금 기록에는 `is_error` 참·표지 없음 꼴이 없어 N3 수정의 실효는 아직 0건 | - | `python3 /tmp/r22-tools/survey.py` | 없음 (기록) |
| Q1 | 낮음 | `_RUN_ID_RE` 에 `/` 를 허용해도(머리는 영숫자 그대로) 시험이 통과. 시험의 탈출 예는 `../` 로 **시작**해서 머리 글자 검사에 먼저 걸림. `M-R21-230339/../../outside/evil` 처럼 **있는 세션 폴더**를 딛고 나가는 꼴은 `_session_dir` 를 거쳐 저장소 밖 `meta.json`·`events.jsonl` 을 읽게 됨 | `tests/test_fleet_graph.py` `test_n7_*` | 변이 V08 → 73 OK | `"R-1/../../outside/evil"`·`"T-1-S1-a1-000000/../x"` 반례 추가 |
| Q2 | 중간 | `test_fleet_graph` 전체가 새 엔진(세션) 갈래를 한 번도 타지 않습니다 - 세션 갈래를 통째로 꺼도(V21) 73 OK. P1·P2 가 시험 없이 남은 까닭 | `tests/test_fleet_graph.py` | V21 → OK | 세션 폴더(`meta.json`+`events.jsonl`)로 N3·N4 를 같은 단언으로 한 번 더 |
| Q3 | 낮음 | 임시 저장소로 옮긴 뒤에도 '이번 라운드' 값은 `fleet.RUNS` 기반(`fleet_ctl._aimem_dir()`·`rounds/`)이라 **저장소 상태**를 읽습니다 - `temporary_aimem_root` 가 `fleet.RUNS` 를 갈아끼우지 않음. 검사는 '내용이 있다' 만 봐서 어느 값이든 통과 | `tests/browser_monitor_ui.py:475-500` | 사본 `rounds/`·`fleet-*.json`·db·projects·requests·graph 를 다 치우고 돌림 → 27/27, value=`띄운 라운드 없음\n실행` (치우기 전엔 진짜 R22 관리자 상태) | `temporary_aimem_root` 에서 `fleet.RUNS` 도 `root/.aimem/runs` 로, 고정 자료에 `rounds/R1/round.json` 하나 두고 값까지 단언 |
| Q4 | 낮음 | '생략된 제목' 검사는 여전히 **대체 갈래**(카드 배치)로만 통과합니다 - '옆으로 잘린 제목 펼침' 원래 갈래는 한 번도 안 돎(1차 M12 그대로). 고정 보드 자료는 효과가 있어(B7: 끄면 FAIL) 후보가 생기고, 펼침 깨짐(B8)도 잡지만, 잘린 칸의 `scrollWidth` 비교 갈래는 시험 밖 | `tests/browser_monitor_ui.py:283-299` | 기준선 출력 `[OK] 생략된 제목을 ... - 옆으로 잘린 제목 없음(카드 배치) - ...` | 1차 M12 방향: 넓은 폭(표 배치)에서 잘린 제목 갈래를 따로 재기 |
| Q5 | 낮음 | `test_run_limit_signal_is_none_for_text_only_harnesses` 를 claude 꼴 JSON 으로 바꾸면서, 이 시험과 새 `test_m6_non_claude_harness_ignores_claude_shaped_json` 이 같은 것을 두 번 잽니다 (글자 `.out` 꼴은 이제 안 잼) | `tests/test_fleet_graph.py:400-405`, 새 `test_m6_*` | 읽어서 확인 | 하나는 옛 글자 `.out` 으로 되돌리기 |

## 3. 변이표

"잡혔나": ○ = 시험이 빨개짐, × = 생존. 모든 변이는 `/tmp/r22-review` 사본에서 넣고 돌린 뒤 되돌렸습니다.
단위 변이 명령: `python3 -m unittest discover -s tests -p test_fleet_graph.py` (V19·V20 은 `test_rt_claude.py`), cwd = 사본.

| 변이 | 잡혔나 |
| --- | --- |
| V01 N3 되돌림: 마지막 `return None` → `return False` | ○ failures=4 |
| V02 N4 되돌림: `or "limit" in value.lower()` 되살리기 | ○ `test_n4_context_window_limit_is_not_a_usage_limit` |
| V03 N5 되돌림: `"limit reached"`·`"too many requests"` 다시 넣기 | ○ `test_n5_report_limit_hit_rejects_non_limit_reports` |
| V04 N5 반만: `"limit reached"` 만 | ○ 같은 시험 |
| V05 N5 반만: `"too many requests"` 만 | ○ 같은 시험 |
| V06 N7 되돌림: run_id 검사 줄 통째로 지우기 | ○ `test_n7_run_id_escaping_runs_dir_is_none` |
| V07 N7 느슨: 머리에 `.`, 몸에 `/` 허용 | ○ 같은 시험 |
| V08 N7 느슨: 몸에 `/` 만 허용 (머리 영숫자) | × 73 OK (Q1) |
| V09 N7: `isinstance(run_id, str)` 지우기 | ○ errors=5 (`test_n7_non_string_run_id_is_none`) |
| V10 N7: 길이 상한 `> 128` 지우기 | — 동치 (긴 이름은 `OSError` → `except` → `None`, 결과 같음), 합계 제외 |
| V11 M3: `is_error` 검사 지우기 | ○ failures=4 |
| V12 M4: `terminal_reason == "api_error"` 갈래 끄기 | ○ `test_m4_...` |
| V13 M6: `harness == "claude"` 검사 지우기 | ○ failures=4 |
| V14 M7: 1 MiB 읽기 상한 지우기 | ○ `test_m7_...` |
| V15 M8: 로그 출처 표시 뒤집기 | ○ failures=2 |
| V16 `step()`: 글자 대체 지우기 (`limit = sig is True`) | ○ failures=5, errors=1 |
| V17 `429` 검사 지우기 | ○ failures=3 |
| V18 `api_error` 의 `usage_limit`/`rate_limit` 검사 지우기 | ○ failures=1 |
| V19 새 엔진 어댑터에 N3 수정을 넣기 (`return False` → `None`) | ○ 그러나 **거꾸로** - `test_rt_claude.test_other_error_false` 가 옛(결함) 동작을 단언해 빨개짐 (P1) |
| V20 새 엔진 어댑터 `_limit_text` 를 좁히기 (N4 수정을 넣기) | × 24 OK - 어댑터엔 N4 반례 시험이 없음 (P2) |
| V21 `run_limit_signal` 의 세션 갈래 끄기 (`if sd is not None` → `if False`) | × 73 OK (Q2) |
| B1 M11: `show_all_projects` 가 칩을 누르지 않게 | ○ '앱 열기' FAIL, 3/5 |
| B2 M11: app.js `PROJECT_FILTERS` 에서 '전체' 칩 지우기 | ○ `TimeoutError: Locator.click`, 3/4 |
| B3 M11 옛 꼴(있으면 누르기)로 되돌림만 (app.js 정상) | × 27/27 - 되돌림 자체는 정상 환경에서 드러나지 않음 (칩 사라짐은 B2 로 잡힘) |
| B4 N1 되돌림: `write_fixed_project` 가 진짜 `projects/웹워들` 복사 (정상 사본) | × 27/27 (환경으로만 지켜짐) |
| B5 N1 되돌림 + 사본 `projects/` 치움 | ○ `FileNotFoundError ... projects/웹워들`, 0/1 |
| B6 N2 되돌림 (`changed_ui_scenario` 를 진짜 저장소 서버로) + 사본 `aimem.db` 치움 | ○ '생략된 제목' FAIL, 26/27 |
| B7 `write_fixed_board(temp_root)` 지우기 | ○ '생략된 제목' FAIL (보이는 제목=False), 26/27 |
| B8 app.js `makeElidable`: `classList.toggle('elide-open')` → `false` | ○ '생략된 제목'·그래프 제목 펼침 2건 FAIL, 24/27 |

합계 28개 (동치 V10 제외): 잡힘 23, 생존 5

- 단위 20개: 잡힘 17 (V01~V07·V09·V11~V19), 생존 3 (V08·V20·V21). V19 는 **거꾸로 잡힘** - 결함을 고치는 변이를 시험이 막음
- 브라우저 8개 (`python3 tests/browser_monitor_ui.py`, 1벌에 1~2분): 잡힘 6 (B1·B2·B5·B6·B7·B8), 생존 2 (B3·B4 - 둘 다 '시험을 옛 꼴로 되돌리기'라 정상 환경에선 원래 드러나지 않는 종류)

## 4. 총평

R20 1차 검수가 고치라고 한 번호는 **보고된 자리에서는 모두 닫혔습니다.** 옛 `.aimem/runs` 경로의 `run_limit_signal` 은 N3 기록에 `None` 을 돌려 글자 판정으로 넘기고, 컨텍스트 한도 문구(N4)·일반 낱말(N5)·`../outside/evil`(N7)은 모두 막혔으며, 고친 줄을 옛 모습으로 돌리는 변이 V01~V07·V09·V11~V18 이 하나도 살아남지 못했습니다. 브라우저 쪽도 `projects/` 나 `aimem.db` 를 치운 사본에서 27/27 이 그대로이고, '전체' 칩이 사라지면 바로 빨개집니다(N1·N2·M11 닫힘). 진짜 기록 287건 전수에서도 `None` 이 늘어 생긴 오인은 없었습니다(최종 한도 1→1). **그러나 수정이 지금 실제로 도는 경로에 닿지 않았습니다.** REV 163 부터 작업자는 `fleet_rt` 세션이고 `run_limit_signal` 은 세션 폴더가 있으면 `tools/fleet_rt/harness/claude.py` 의 어댑터로 넘기는데, 그 어댑터는 N3 기록에 여전히 `False`(P1), 컨텍스트 한도 오류에 여전히 `True`(P2)를 돌려줍니다. `test_fleet_graph` 는 세션 갈래를 한 번도 타지 않고(V21 생존), `test_rt_claude.test_other_error_false` 는 오히려 결함 동작을 못박고 있습니다(V19). 다음 수정 슬롯은 판정을 한 함수로 모으고(P3) 어댑터에 N3·N4 수정을 옮긴 뒤, 세션 폴더로 같은 반례를 시험하십시오(Q2). 그 다음 Q1(`/` 반례)·Q3(`fleet.RUNS` 갈아끼우기)·Q4(잘린 제목 갈래)를 닫으면 됩니다.
