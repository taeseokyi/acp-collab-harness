# R20 적대적 검수 (T-262, S1, G-051)

- 대상: R20 이 고친 여섯 묶음 (SIGTERM 종료 순서, 진짜 SIGTERM 시험, `run_limit_signal`, 그 회귀 시험, 브라우저 검사 고정 자료화, 시험 구멍 넷)
- 방법: `/tmp/r20-review` 사본 (`.git`·`.aimem/tls`·`.aimem/runs`·`__pycache__` 제외, `python3 shutil.copytree`)에 변이를 하나씩 넣고 해당 시험을 돌렸습니다. 변이는 매번 원문으로 되돌렸습니다. 저장소 원본은 이 파일 말고 고치지 않았습니다.
- 기준선 (변이 없음, 사본): `unittest` 5개 모듈 (shutdown·fleet_graph·claude_usage·ticket_regress·fleet_ctl) 173건 OK 24.2s / `browser_monitor_usage.py` 17/17 / `browser_monitor_ui.py` 27/27 / `browser_monitor_tabs.py` 10/10

## 1. 결함표

| 번호 | 심각도 | 무엇이 | 어디(파일:줄) | 재현 | 고칠 방향 |
| --- | --- | --- | --- | --- | --- |
| N1 | 높음 | **고정 자료로 옮긴 `browser_monitor_ui.py` 가 아직 저장소 상태에 기댑니다** (이번 라운드 큐 1 의 핵심). `write_fixed_project` 가 고정 자료를 만들지 않고 **진짜 저장소의 `projects/웹워들` 을 복사**합니다 | `tests/browser_monitor_ui.py:415-420` | 사본의 `projects/` 를 비우고 `python3 tests/browser_monitor_ui.py` → `[FAIL] 검사 실행 - FileNotFoundError: ... projects/웹워들`, `통과 3 / 전체 4` (rc 1). `.aimem/requests` 만 비우면 27/27 통과 | 최소한의 웹워들 꼴 프로젝트(`index.html` + 보드 30칸)를 시험 안에 글자로 써 넣거나 `tests/fixtures/` 에 두고 거기서 복사. 진짜 `projects/` 를 읽지 않기 |
| N2 | 높음 | `changed_ui_scenario` 는 **아직 진짜 저장소(`monitor_server()` 기본 root, 진짜 `aimem.db`)** 로 돕니다. 옮기지 않았습니다 | `tests/browser_monitor_ui.py:814-815` | 사본의 `.aimem/aimem.db` 를 치우고 돌리면 `[FAIL] 생략된 제목을 눌러 펼칠 수 있다 (폰 폭 390px) - ... 보이는 제목=False` (26/27). '이번 라운드' 검사의 값도 진짜 DB 의 `R20 · 2026-11-12 17:35` 입니다 | 이 시나리오도 `temporary_aimem_root(temp_root)` 안으로 옮기고, 보드·큐에 긴 제목 행을 고정 자료로 넣기 |
| N3 | 중간 | **구조 신호 `False` 가 글자 판정의 `True` 를 덮어씁니다.** `is_error: true` 인데 `api_error_status`·`api_error`·`terminal_reason` 이 없으면 `False` 를 돌려주고, `step()` 은 `sig is None` 일 때만 글자를 보므로 진짜 한도가 **보통 실패로 재시도**됩니다 (R20 이전엔 글자로 잡히던 것 - 회귀) | `tools/fleet_graph.py:455-472`, `:869` | 사본에서 `{"is_error": true, "result": "You've hit your 5-hour limit · resets 11:20am"}` (+ meta harness claude) → `run_limit_signal` = `False`, `report_limit_hit(result)` = `True`. `"Claude AI usage limit reached\|1731400000"` 도 같음 | `is_error` 가 참인데 구조 표지가 하나도 없으면 `False` 가 아니라 `None` 을 돌려 글자 판정으로 넘기기. `False` 는 `is_error` 가 거짓일 때만 |
| N4 | 중간 | `terminal_reason == "api_error"` 갈래의 `"limit" in value.lower()` 가 너무 넓습니다. 컨텍스트 길이·출력 토큰 한도 같은 **재시도로 풀리는 API 오류도 사용 한도로** 봅니다 → blocked, 재시도 안 함 | `tools/fleet_graph.py:469` | `{"is_error": true, "terminal_reason": "api_error", "result": "Prompt exceeds the context window limit"}` → `True` | `"limit"` 부분 일치를 빼고 `report_limit_hit` (한도 문구 목록)만 쓰기. 또는 `usage`/`rate`/`5-hour`/`weekly` 와 함께일 때만 |
| N5 | 낮음 | 글자 판정에 새로 넣은 `"limit reached"`·`"too many requests"` 가 일반 낱말이라 rc≠0 인 codex·opencode 보고에서 오인합니다 | `tools/fleet_graph.py:422` | `report_limit_hit("NEEDS-FIX: verify step time limit reached, test failed")` → `True`. `report_limit_hit("DONE - added handler for HTTP 429 Too Many Requests")` → `True` | 하네스가 실제로 찍는 문구 그대로만 (`"hit your ... limit"`, `"usage limit reached"`). 일반 낱말은 빼기 |
| N6 | 낮음 | `.out`/`.json` 이 **FIFO** 면 `run_limit_signal` 이 **영영 막힙니다** (예외는 안 나가지만 `step()` 전체가 멈춤). `_run_meta` 의 `read_text()` 도 같음 | `tools/fleet_graph.py:447-451`, `tools/fleet.py:440-441` | `os.mkfifo(runs/'F.out')` 후 `run_limit_signal('F')` → 15초 시간 초과(hang). `F.json` 이 FIFO 여도 같음 | 열기 전에 `stat.S_ISREG` 확인, 또는 `os.open(..., O_RDONLY\|O_NONBLOCK\|O_NOFOLLOW)` 뒤 fstat 으로 일반 파일만 |
| N7 | 낮음 | `run_id` 검사가 없어 `../` 로 **`runs/` 밖 `.json`·`.out` 을 읽습니다.** 모니터 `reader.py:639` 는 `RUN_ID_RE` 로 막지만 `fleet_graph` 는 막지 않습니다. `run_id` 는 그래프 JSON 에서 오므로 그 파일을 쓸 수 있는 사람만 가능 - 결과는 1비트지만 한도 판정을 조작할 수 있음 | `tools/fleet_graph.py:447,450` | `run_limit_signal("../outside/evil")` (runs 밖에 `evil.json`/`evil.out` 둠) → `True` | `reader.RUN_ID_RE` 와 같은 `fullmatch` 를 `run_limit_signal` 머리에. 아니면 `None` |
| N8 | 낮음 | `_run_meta` 가 메타 `.json` 을 상한 없이 통째로 읽습니다 (`.out` 은 1 MiB 로 막았는데 메타는 안 막음) | `tools/fleet.py:440-441` | 300 MiB 메타 → `True` 를 돌려주지만 maxrss 614 MiB | 메타도 크기 상한(예: 64 KiB) 뒤 읽기 |
| N9 | 정보 | `.out` 이 1 MiB 를 넘으면 JSON 이 잘려 `None`(글자 판정)으로 갑니다. 지금 가장 큰 `.out` 이 28 KB 라 실해는 없음 | `tools/fleet_graph.py:451` | 앞머리에 `is_error/429` 가 있는 300 MiB 성긴 파일 → `None` | 정보로만. 커지면 끝 쪽 `{"type":"result"...}` 만 읽기 |
| N10 | 정보 | SIGTERM 처리기를 `try:` 바로 앞에 붙였지만 **설치 `try` 블록 안**(`signal.signal` 돌아온 직후 ~ `sigterm_installed = True` 앞)에 SIGTERM 이 오면 `KeyboardInterrupt` 가 `(ValueError, OSError)` 에 안 걸려 `serve()` 밖으로 나가고 `finally`(되돌리기·flush·`server_close`)가 돌지 않습니다. 이 시점엔 감사 생략이 있을 수 없어 실해는 없음 | `tools/aimem_monitor/server.py:3240-3245` | 경합 창이 바이트코드 몇 개라 재현 안 함 (읽어서 확인) | 설치를 바깥 `try:` 안으로 넣기 (`try: old = signal.signal(...); ...; serve_forever() finally: ...`) |
| N11 | 정보 | `log_line ("\n내립니다.")` - 괄호 앞 공백. 동작엔 영향 없으나 순서 시험(`"log_line(" in line`)이 이 꼴을 못 셉니다 (M1 참고) | `tools/aimem_monitor/server.py:3248` | `grep -n "log_line (" tools/aimem_monitor/server.py` | 공백 지우기 |
| M1 | 중간 | 순서 시험은 설치와 `try:` 사이에 **`log_line(` 글자만** 찾습니다. 다른 문장(`print`, `log_line (`, 느린 호출)을 끼워 R19-P6 의 틈을 되살려도 통과 | `tests/test_monitor_shutdown.py:204-213` | 변이 M05 (설치와 `try:` 사이에 `print('serving', flush=True)`) → 3/3 통과 | 설치 줄 다음의 **문장**이 `except`/`pass` 뒤 곧바로 `try:` 인지 `ast` 로 보기 (설치 `try` 문과 serve `try` 문이 `serve` 본문에서 이웃인지) |
| M2 | 중간 | flush 시험의 `any("5" in line ...)` 가 약합니다 - 줄에 **시각**이 들어 있어 `5` 는 거의 늘 있습니다. 생략 수를 틀리게 써도 통과 | `tests/test_monitor_shutdown.py:92` | 변이 M28 (`skipped + 50` → `55건`) 생존. M29 (`1건`) 은 시각에 `5` 가 없던 순간이라 이번엔 잡혔을 뿐 | `"상한 생략 5건" == line.split("\t")[4]` 처럼 칸을 정확히 |
| M3 | 중간 | `is_error` 검사를 지워도 생존 - `is_error: false` 이면서 429·`usage_limit`·`terminal_reason: api_error` 를 함께 가진 기록이 시험에 없습니다 | `tests/test_fleet_graph.py` (C2 묶음) | 변이 M09 → 59/59 통과 | `{"is_error": false, "api_error_status": 429, "terminal_reason": "api_error", "result": "limit"}` → `False` 단언 추가 |
| M4 | 중간 | `terminal_reason == "api_error"` 갈래 전체, 그리고 그 안의 `"limit"` 부분 일치가 시험되지 않습니다 (N4 가 시험 없이 들어옴) | `tests/test_fleet_graph.py` | 변이 M12·M13 → 통과 | 이 갈래만 타는 기록(429·api_error 없음, result 에 한도 문구) 하나 + 컨텍스트 한도 오류는 `False` 인 반례 하나 |
| M5 | 중간 | N3 을 막는 시험이 없습니다 - `is_error: true` + 구조 표지 없음 + 한도 문구 result | `tests/test_fleet_graph.py` | 위 N3 재현 그대로 | `step()` 단에서 이 기록이 `limit` 으로 blocked 되는지 단언 |
| M6 | 낮음 | `harness == "claude"` 검사를 지워도 생존 - codex 시험의 `.out` 이 JSON 이 아니라서 어차피 `None` | `tests/test_fleet_graph.py` `test_run_limit_signal_is_none_for_text_only_harnesses` | 변이 M14 → 통과 | codex 시험의 `.out` 을 **claude 꼴 JSON**(`is_error/429`)으로 써서 그래도 `None` 인지 |
| M7 | 낮음 | 1 MiB 읽기 상한이 시험되지 않습니다 | `tests/test_fleet_graph.py` | 변이 M15 → 통과 | 1 MiB + 1 바이트 `.out` → `None` |
| M8 | 낮음 | 로그의 출처 표시(`구조 신호`/`보고 글자`)가 뒤집혀도 통과 - 시험은 `"limit"`·run_id 만 봅니다 | `tests/test_fleet_graph.py` `test_step_nonzero_rc_with_structural_limit_blocks_and_logs_limit` | 변이 M17 → 통과 | `assertIn("(구조 신호)", log)` 및 글자 경로 시험에 `"(보고 글자)"` |
| M9 | 낮음 | 첫 창(`_revoked_last` 가 빌 때)의 `_denied_window_seen.clear()` 를 지워도 생존 | `tests/test_monitor_ticket_regress.py` | 변이 M20 → 39/39 통과 | `_revoked_last` 를 비운 뒤 같은 주체가 다시 보장 기록되는지 |
| M10 | 낮음 | `_LIMIT_LOG_LINE` 의 `limit` 뒤 공백을 지워도 생존 (`limited ...` 같은 줄을 한도로 볼 수 있음) | `tests/test_fleet_ctl.py` `test_round_hit_limit_ignores_limit_in_the_middle_of_a_line` | 변이 M26 → 통과 | `"2026-...T.. limiter T-1 ..."` 반례 한 줄 |
| M11 | 낮음 | 브라우저 `scenario()` 의 '전체' 칩 누르기가 **있으면 누르기**로 느슨해졌습니다. 칩이 버그로 사라져도 조용히 통과 | `tests/browser_monitor_ui.py:83` | 읽어서 확인 (고정 저장소엔 진행 중 프로젝트가 없어 칩이 꼭 필요하지 않음) | 고정 자료에 진행 중 프로젝트 하나를 넣어 칩이 **반드시** 있게 하고 무조건 누르기 |
| M12 | 낮음 | '생략된 제목을 눌러 펼칠 수 있다' 검사가 **늘 대체 갈래**(잘린 제목 없음 → 아무 제목 눌러 상세가 열리면 OK)로만 통과합니다. 원래 단언(잘린 제목 펼침)은 지금 한 번도 돌지 않습니다. 전엔 이 경우 `False` 로 실패했습니다 | `tests/browser_monitor_ui.py:279-299` | 기준선 출력: `[OK] 생략된 제목을 ... - 옆으로 잘린 제목 없음(카드 배치) - 제목 누름: ...` | 검사 이름을 실제로 재는 것으로 바꾸고, 잘린 제목 갈래는 넓은 폭 고정 자료로 따로 재기 |
| M13 | 정보 | `usageStaleText` 의 600초 문턱(`<=`)이 시험되지 않습니다 (R20 대상 밖) | `tests/browser_monitor_usage.py` | 변이 M23 → 17/17 통과 | 600초·601초 두 점 |

## 2. 변이표

모든 변이는 `/tmp/r20-review` 사본에서 넣고 돌린 뒤 되돌렸습니다. "잡혔나": ○ = 시험이 빨개짐, × = 생존(구멍).
R-* 줄은 저장소 상태를 비운 변이이며, **시험이 계속 통과해야 ○** 입니다 (통과하지 않으면 저장소에 기대는 것 = ×).

| 변이 | 잡혔나 |
| --- | --- |
| M01 `serve`: `signal.signal(SIGTERM, _sigterm_interrupt)` 설치 지우기 (`getsignal` 로 대체) | ○ test_monitor_shutdown |
| M02 `serve`: `finally` 의 처리기 되돌리기 지우기 | ○ test_monitor_shutdown |
| M03 `serve`: `finally` 의 `flush_denied_audit(root)` 지우기 | ○ test_monitor_shutdown |
| M04 `serve`: 처리기 설치를 다시 `log_line` 들 앞으로 | ○ test_monitor_shutdown (소스 순서 시험) |
| M05 `serve`: 설치와 `try:` 사이에 `print(...)` 끼우기 (틈 재도입) | × 3/3 통과 (M1) |
| M06 `run_limit_signal` 늘 `None` | ○ test_fleet_graph |
| M07 `run_limit_signal` 늘 `True` | ○ test_fleet_graph |
| M08 `step()`: `rc != 0` 조건 풀기 (rc 0 도 판정) | ○ test_fleet_graph |
| M09 `run_limit_signal`: `is_error` 검사 지우기 | × 59/59 통과 (M3) |
| M10 `run_limit_signal`: `429` 검사 지우기 | ○ test_fleet_graph |
| M11 `run_limit_signal`: `api_error` 의 `usage_limit`/`rate_limit` 검사 지우기 | ○ test_fleet_graph |
| M12 `run_limit_signal`: `terminal_reason == "api_error"` 갈래 지우기 | × 통과 (M4) |
| M13 `run_limit_signal`: 그 갈래의 `"limit" in value.lower()` 지우기 | × 통과 (M4) |
| M14 `run_limit_signal`: `harness == "claude"` 검사 지우기 | × 통과 (M6) |
| M15 `run_limit_signal`: 1 MiB 읽기 상한 지우기 | × 통과 (M7) |
| M16 `step()`: `sig is None` 일 때 글자 판정 대체 지우기 (`limit = sig is True`) | ○ test_fleet_graph |
| M17 `step()`: 로그 출처 표시 뒤집기 | × 통과 (M8) |
| M18 `claude_usage`: `age_seconds = max(0, ...)` 의 `max(0, ...)` 지우기 | ○ test_monitor_claude_usage |
| M19 `_audit_denied`: 창이 바뀔 때 `_denied_window_seen` 안 비우기 | ○ test_monitor_ticket_regress |
| M20 `_audit_denied`: 첫 창(빈 `_revoked_last`) 때 `_denied_window_seen` 안 비우기 | × 39/39 통과 (M9) |
| M21 `app.js`: 사용량 행 `Math.round(pct)` → `Math.floor(pct)` | ○ browser_monitor_usage (`pct='79%'`) |
| M22 `app.js`: `usageStaleText` `minutes > 60` → `>= 60` | ○ browser_monitor_usage (`60분='1시간 전 기준'`) |
| M23 `app.js`: `usageStaleText` 600초 문턱 `n <= 600` → `n < 600` | × 17/17 통과 (M13) |
| M24 `fleet_ctl`: `_LIMIT_LOG_LINE` 의 `^` 만 지우기 (`.match` 그대로) | — 동치 변이 (`.match` 가 이미 앞에 묶음), 합계 제외 |
| M25 `fleet_ctl`: `.match` → `.search` 만 (`^` 그대로) | — 동치 변이 (`^` 가 남아 여전히 앞에 묶임), 합계 제외 |
| M26 `fleet_ctl`: `_LIMIT_LOG_LINE` 의 `limit` 뒤 공백 지우기 | × 통과 (M10) |
| M27 `fleet_ctl`: 앵커 완전히 풀기 (`^` 지우기 + `.search`) | ○ test_fleet_ctl (세 subTest 모두 FAIL) |
| M28 `flush_denied_audit`: 생략 수를 `skipped + 50` 으로 쓰기 | × 통과 (M2) |
| M29 `flush_denied_audit`: 생략 수를 `1` 로 쓰기 | × 이번엔 FAIL 했지만 `"5" in line` 이 시각에 걸리면 생존하는 불안정 검출 - 생존으로 셈 (M2) |
| R-A 사본 `projects/` 비움 → `browser_monitor_ui.py` | × FileNotFoundError `projects/웹워들`, 3/4 (N1) |
| R-A 사본 `projects/` 비움 → `browser_monitor_tabs.py` | ○ 10/10 |
| R-B 사본 `.aimem/requests/` 비움 → `browser_monitor_ui.py` | ○ 27/27 |
| R-B 사본 `.aimem/requests/` 비움 → `browser_monitor_tabs.py` | ○ 10/10 |
| R-C `projects/` + `.aimem/requests/` 비움 → `browser_monitor_ui.py` | × FileNotFoundError, 3/4 (N1) |
| R-C `projects/` + `.aimem/requests/` 비움 → `browser_monitor_tabs.py` | ○ 10/10 |
| R-D `projects/` + `requests/` + `.aimem/graph/` 비움 → `browser_monitor_ui.py` | × FileNotFoundError, 3/4 (N1) |
| R-D `projects/` + `requests/` + `.aimem/graph/` 비움 → `browser_monitor_tabs.py` | ○ 10/10 |
| R-E 사본 `.aimem/aimem.db` 치움 → `browser_monitor_ui.py` | × 26/27, '생략된 제목' FAIL (N2) |
| R-E 사본 `.aimem/aimem.db` 치움 → `browser_monitor_tabs.py` | ○ 10/10 |
| 합계 37개 (동치 M24·M25 제외): 잡힘 21, 생존 16 | 코드 변이 27 (잡힘 15 = M01·02·03·04·06·07·08·10·11·16·18·19·21·22·27, 생존 12 = M05·09·12·13·14·15·17·20·23·26·28·29) + 저장소 비움 10 (○ 6, × 4 = R-A·R-C·R-D·R-E 의 ui) |

합계 37개: 잡힘 21, 생존 16

## 변이 말고 본 것

- **`run_limit_signal` 이 예외를 내보내는 길**: 사본 `tools` 를 불러 `fleet.RUNS` 를 임시 폴더로 바꾸고 직접 때렸습니다. 아주 깊은 중첩 (`[`×200000, `{"a":`×100000) → `None`, 300 MiB 성긴 파일 → `None`, 짝 없는 서러게이트 (`\ud800` 이스케이프) → 예외 없음(`True`), 깨진 UTF-8 → `None`, `/etc/passwd`·`/tmp`·자기 자신 심볼릭 링크 → `None`, 디렉터리 `.out` → `None`, `/dev/zero` 링크 → `None`(1 MiB 에서 끊김), `1e999`·`NaN`·엉뚱한 형 → `False`, 메타가 목록·깨짐·디렉터리 → `None`, `run_id` 가 `''`·`None`·`/nonexistent` → `None`. **예외는 하나도 밖으로 안 나갔습니다.** 막히는 길은 FIFO 둘 (N6), 그릇된 값은 N3·N4·N7.
- **종료 시험 속도·흔들림**: 이어서 세 번 0.63s / 0.43s / 0.50s 모두 3/3 ok, 동시에 다섯 벌 1.13s 모두 rc 0. 끝난 뒤 `ps -eo pid,args` 에 `server.serve(` 자식 없음 - 프로세스·포트를 흘리지 않습니다. `_free_port()` 는 묶었다 풀고 자식이 다시 묶는 TOCTOU 가 있으나 다섯 벌 병렬에서 안 걸렸습니다(정보).
- **검사 수 유지**: `checks.ok(` 호출 수 HEAD→지금 - ui 30→30, tabs 11→11, usage 14→18 (+4 새 검사). 실행 검사 수 ui 27, tabs 10, usage 17. `is_visible()` 을 `count()>0` 으로 바꾼 곳은 없습니다. 느슨해진 단언은 M11 (칩 있으면 누르기), M12 (생략 제목 대체 갈래), 그리고 `badge.get_attribute("data-status") or inner_text()` 는 단언이 아니라 읽는 방법 변경이라 문제 아님.
- **`.aimem/runs/` 임의 경로**: N7 - `run_limit_signal("../outside/evil")` 이 runs 밖을 읽어 `True`. 모니터의 `reader.RUN_ID_RE` 같은 검사가 `fleet_graph` 쪽엔 없습니다.

## 3. 총평

SIGTERM 쪽은 닫혔습니다. 처리기 설치 지우기, 되돌리기 지우기, flush 지우기, log_line 앞으로 되돌리기 네 변이를 진짜 자식 프로세스 시험이 모두 잡았고, 시험은 빠르며(0.5s 안팎) 세 번·병렬 다섯 벌에서도 흔들리거나 프로세스를 흘리지 않았습니다. 다만 순서 시험이 `log_line(` 글자만 봐서 다른 문장으로 틈을 되살리면 못 잡고(M1), flush 단언은 시각 속 `5` 에 기대는 약한 단언입니다(M2). 한도 구조 신호는 예외를 내보내는 길이 없음을 확인했고 핵심 변이(늘 None/True, 429, api_error, rc 조건, 글자 대체)는 잡혔습니다. 하지만 `is_error: true` 인데 구조 표지가 없으면 `False` 가 글자 판정을 덮어 R20 전에 잡히던 한도를 놓치는 회귀(N3)가 생겼고, `terminal_reason` 갈래의 `"limit"` 부분 일치(N4)와 일반 낱말 문구(N5)는 시험 없이 들어왔습니다. **이번 라운드의 핵심인 큐 1 (브라우저 검사의 저장소 의존 끊기)은 닫히지 않았습니다.** `browser_monitor_tabs.py` 는 진짜로 독립이 되었지만(모든 비움 변이에서 10/10), `browser_monitor_ui.py` 는 `projects/` 를 비우면 웹워들 복사에서 바로 죽고(N1), `changed_ui_scenario` 는 아예 옮기지 않아 진짜 DB 에 기댑니다(N2). 다음 수정 슬롯은 N1·N2·N3 을 먼저, 이어서 M1~M5 를 닫으십시오.
