# R18 적대적 검수 (T-238, S1) - 사용 한도 카드 · 감사 상한 몫 · 엔진 한도 판정

**한 줄 요약:** 3 KB짜리 `claude-usage.json` 하나(중첩 깊이 1500, 또는 `at` 이 `0001-01-01T00:00:00+05:00`)로 `/api/state` 가 **응답 없이 연결을 끊습니다**(실패 분기 `_empty_state` 도 같은 함수를 불러 대체 화면도 없음). 엔진의 한도 판정은 **실제 보고 250건 중 DONE 보고 3건을 한도로 오인**하며 그중 T-242 는 실제로 `verify_rc=-4` blocked 됐습니다. `flush_denied_audit` 은 운영 정지 방식(SIGTERM)에서 **한 번도 돌지 않습니다**. 변이 45개 중 30개 잡힘, 15개 생존(그중 동치 4개).

검수 대상 트리: 작업 트리 그대로(커밋 87ad847 + 미커밋 R18·R19 변경). `_LIMIT_PATTERNS` 는 이미 R19(T-242)가 좁힌 판입니다 - 아래 N3 수치는 **좁힌 뒤의** 패턴으로 잰 것입니다.

| # | 심각도 | 무엇 | 어디(파일:행) | 재현 | 닫는 법 |
|---|---|---|---|---|---|
| N1 | 높음 | 깊은 중첩 JSON 이 `RecursionError` 를 던져 `/api/state` 가 죽음. docstring 의 "예외도 없습니다" 위반. 실패 분기도 같은 함수를 불러 대체 상태도 못 냄 | `tools/aimem_monitor/server.py:954` (호출 `:1135`, `:895`) | 유효 객체 + `"pad": "["*1500 + "]"*1500` (3,106 B, 상한 64 KiB 안) → `claude_usage` `RecursionError`; 임시 포트 서버 `/api/state` → `RemoteDisconnected` (2.2 s), 파일 복구 즉시 200 | `except (OSError, ValueError, UnicodeDecodeError, RecursionError)` 로 넓히고, `collect_state`/`_empty_state` 의 호출을 `try: ... except Exception: None` 로 한 번 더 감쌀 것(부가 카드가 전체 상태를 죽이지 않게) |
| N2 | 높음 | `at` 의 시간대 변환이 `OverflowError` 를 던짐 - `except (TypeError, ValueError)` 가 못 잡음 | `server.py:988-990` | `at="0001-01-01T00:00:00+05:00"` 또는 `"9999-12-31T23:59:59-05:00"` → `OverflowError: date value out of range` → `/api/state` `RemoteDisconnected`. (`resets_at` 쪽 `_usage_resets_at` 은 `OverflowError` 를 잡아서 무사 - 같은 파일 안 불일치) | `except (TypeError, ValueError, OverflowError)`. N1 의 바깥 `try` 가 있으면 함께 닫힘 |
| N3 | 중간 | 엔진이 **멀쩡한 DONE 보고를 한도로 오인** → 재시도 없이 blocked. 보고 꼬리 2000자에 패턴이 **인용**만 돼도 걸림 | `tools/fleet_graph.py:413-429`, `:821-844` | 실제 `.aimem/runs` 250건 전수: 걸린 4건 = 진짜 한도 1건(T-215, rc=1) + **DONE 보고 3건**(T-237, T-242, T-243, 모두 rc=0). T-242 는 `G-047.json` 에 `limit: true, verify_rc: -4` 로 실제 막힘(로그 `16:16:45 limit T-242`). 문장 시험: `"DONE\n- 감사 상한 작업: 분당 60줄 한도를 초과한 거절은…"` → True, `"DONE\n- 429 응답(rate limit exceeded)을 받으면 재시도…"` → True, `"검증은 디스크 한도에 걸려…"` → True. 반대로 `"Session limit reached ∙ resets 3pm"`, `"You've reached your usage limit"` → False(놓침). verify 가 없는 노드는 rc=0 DONE 이어도 즉시 blocked | (a) 판정을 **rc != 0 일 때만** 하라 - 실데이터에서 오인 3건이 전부 사라지고 진짜 1건은 남음. (b) claude 하네스는 글자 대신 `.out` JSON 의 구조 신호를 보라: T-215 는 `is_error=True`, `api_error_status=429`, `api_error="usage_limit_reached"`, `terminal_reason="api_error"`. (c) 글자 판정이 남는다면 마지막 줄(또는 300자)만 |
| N4 | 중간 | `flush_denied_audit` 이 운영에서 안 돎: `monitorctl.sh` 는 `kill "$pid"`(SIGTERM)로 끄는데 서버에 SIGTERM 처리기가 없어 `finally` 가 실행되지 않음. 범람이 끝난 뒤 조용해지면 남은 수는 다음 거절까지 무기한 대기 | `server.py:3211`, `tools/aimem_monitor/monitorctl.sh:43` | `grep -n "signal\.\|SIGTERM" server.py __init__.py` → 0건. 모의: 상한 60 위로 80건 → `_denied_cap_skipped=20`, 이후 요청 없음 → 줄 0 | `signal.signal(SIGTERM, ...)` 에서 `KeyboardInterrupt` 를 일으키거나 `httpd.shutdown()` 을 부르고, 창 전환을 요청에 기대지 말고 타이머(또는 `/api/state` 처리 때)로도 내보낼 것 |
| N5 | 낮음 | 한도 표시가 영구적: T-242 는 지금 `status=done` 인데 `limit=True` 그대로, 그래프 로그의 `limit` 줄도 남아 `_round_hit_limit(19)` 이 계속 True → R19 가 DONE 아닌 보고로 멈추면 까닭에 "사용 한도로 끊긴 시도가 있습니다" 가 **틀리게** 붙음 | `tools/fleet_ctl.py:919-946`, `fleet_graph.py` `cmd_unblock` | `fleet_ctl._round_hit_limit(19)` → True, `_round_hit_limit(18)` → False | 로그 대신 그래프 JSON 에서 `status=="blocked" and limit` 인 노드만 셀 것. `unblock` 때 `n["limit"]` 를 지울 것 |
| N6 | 낮음 | 처음 보는 주체 보장(256)이 분당 상한(60)을 사실상 256으로 올림. 다만 주체는 서명 쿠키/HMAC 해석에서만 오므로 무인증으로는 못 엶 | `server.py:757` | `audit` 를 계수기로 바꿔 모의: (a) 무인증, event·method·reason·path·ip 를 모두 바꾼 10만 건/50 s → **12줄**. (b) 허용 사용자 경로 바꾸기 10만 건 → **60줄**(cap_skipped 99,940). (c) 분마다 새 주체 2000개 × 3분 → **770줄** = 창당 256 + 생략줄. 즉 GitHub 계정 256개가 있으면 분당 257줄(≈ 37만 줄/일), 그리고 그 256개가 보장을 다 써 진짜 회수 계정이 굶을 수 있음 | `_DENIED_AUDIT_FIRST_MAX` 를 32 정도로, 또는 보장분에 별도 분당 예산. 무인증 경로는 지금도 충분히 닫혀 있음 |
| N7 | 낮음 | 억제 중인 중복 수(`_revoked_last` 의 `rec[1]`)는 `flush` 가 내보내지 않아 종료 때 사라짐 (이중 계상은 없음 - 아래) | `server.py:781-789` | 같은 키 5건 → 줄 1, `flush` → 0줄, 대기 수 `[4]` 가 버려짐 | `flush` 가 `_revoked_last` 의 `rec[1]` 합도 더할 것 |
| N8 | 낮음 | 64 KiB 상한은 `stat().st_size` 만 봄 - `/dev/zero` 같은 문자 장치·FIFO 는 `st_size=0` 이라 통과하고 `read_text` 가 끝없이 읽거나 막힘(5초마다 스레드 하나씩) | `server.py:952-954` | `os.stat("/dev/zero").st_size` → 0 (실측). `.aimem/` 은 작업자도 쓸 수 있는 곳. 링크·FIFO 를 실제로 만들어 재지는 않음(쓰기 범위 밖) | `os.open(..., O_RDONLY|O_NONBLOCK|O_NOFOLLOW)` → `fstat` 로 `S_ISREG` 확인 → `read(MAX+1)` 로 읽고 넘치면 None |
| N9 | 정보 | `at` 문자열이 그대로(최대 ~64 KiB, 제어문자 포함) `/api/state` 로 나감. 화면은 안 쓰지만 5초마다 실림. 미래 `at` 은 age 0 → "N분 전 기준" 이 영영 안 뜸 | `server.py:993` | `at="A"*60000` → 그대로 실림. `at="…\u0000\u001b[31m‮"` → 그대로. `at="2099-01-01T00:00:00"` → `age_seconds=0` | `at` 은 내보내지 말고 `age_seconds` 만, 미래 시각은 `None`(모름) |
| N10 | 정보 | DOM 은 전부 `textContent` - 안전. `resets_at_iso` 는 서버가 다시 만든 ISO 라 `"<img src=x onerror=…>"` → `null`. `label` 은 서버 표. NaN/±Inf → 0/100/0, 5000자리 정수 → 파일 전체 None, `rate_limits` 리스트 → None, `at` 숫자 → None | `app.js:1571-1621`, `server.py:922-944` | P6-P18 탐침, 모두 예외 없음 | - |
| N11 | 정보 | 비용: 실제 저장소로 `/api/state` 한 번이 1.9-2.0 s, 349 KB. 그 안에서 `claude_usage` 는 정상 파일 0.02 ms, 64 KiB 거대 배열 1.7 ms - 무시할 만함 | - | `perf_counter` 측정 | - |
| M1 | 중간 | 64 KiB 상한을 지워도 초록 - 시험 파일에 `rate_limits` 가 없어 상한과 무관하게 None | `tests/test_monitor_claude_usage.py:47` | 변이 S3 생존 | 패딩 파일에 **유효한** `rate_limits` 를 넣고 None 을 요구 |
| M2 | 중간 | `_empty_state`·`collect_state` 에서 `claude_usage` 줄을 지워도 단위 시험 초록 - `_blank_keys` 가 이미 `None` 키를 주고, 시험 root 에 파일이 없음 | `tests/test_monitor_claude_usage.py:158` | S4(`_empty_state`) 생존 - **아무 시험도 못 잡음**. S5(`collect_state`) 는 단위 생존, 브라우저만 잡음(S5b) | 유효 파일을 쓰고 두 분기 모두 `rows` 가 있는지 볼 것 |
| M3 | 중간 | "꼬리 2000자만" 시험이 빈 시험: 앞쪽 글 `"사용 한도"` 는 패턴이 아니어서 전문을 봐도 False | `tests/test_fleet_graph.py:267` | 변이 G3(`text[-2000:]` → `text`) 생존 | 앞쪽에 **실제 패턴** `"사용 한도로 끊겼습니다\n" + "x"*2500 + "\nDONE"` 을 두고 False 요구 |
| M4 | 낮음 | 창 전환 때 `_denied_window_seen` 을 안 비워도 초록 - 시험이 2창에서 **처음 보는** 주체(gh:park)만 씀 | `tests/test_monitor_ticket_regress.py:453` | 변이 A7 생존 | 1창에서 쓴 주체가 2창의 상한 뒤에도 한 줄 남는지 볼 것 |
| M5 | 낮음 | `serve()` 의 `flush_denied_audit` 호출을 지워도 초록 (N4 와 같이 닫을 것) | `server.py:3211` | 변이 A12 생존 | SIGTERM 으로 서버를 내리고 감사 파일에 `audit-dropped` 가 남는지 |
| M6 | 낮음 | 연쇄의 로그 정규식 앵커를 풀어도(`.*limit`) 초록 - 줄 가운데 `limit` 이 든 부정 사례가 없음 | `tests/test_fleet_ctl.py:361` | 변이 C2 생존 | `"…retry-queued T-1 - rate limit 문구"` 줄에 False 요구 |
| M7 | 낮음 | rc != 0 + verify 있음 + 한도 글 분기 미검사, 미래 `at` 의 age 음수 미검사, JS 의 "N시간 전 기준" 미검사, 퍼센트 반올림(정수만 씀) 미검사 | 각 시험 | 변이 G7, S8, B12, B10 생존 | 각 분기에 한 사례씩 |
| M8 | 낮음 | N1·N2 의 악성 입력(깊은 중첩, 범위 밖 날짜) 시험이 없음 | `tests/test_monitor_claude_usage.py` | 탐침 P3, P9, P10 | 두 사례 + `/api/state` 200 을 요구하는 시험 |

## 무엇을 어떻게 했나

**/tmp 사본 대신 메모리 변이.** `rsync … /tmp/…` 는 승인 요구로 막혔고, 소유 경로 밖 쓰기는 위임의 예외이기도 해서 우회하지 않았습니다. 대신 디스크를 건드리지 않는 방식으로 같은 시험을 했습니다:
- 파이썬 변이: `os.fork()` 한 자식에서 모듈 원문에 문자열 치환 하나를 하고 `exec(compile(...), mod.__dict__)` 로 그 모듈을 덮어쓴 뒤 해당 unittest 모듈을 돌림. 치환 대상이 정확히 1회 나오는지 확인(B2 는 처음에 2회라 문맥을 넓혀 다시 돌림).
- 정적 파일 변이: 자식에서 `server.Handler._static` 을 감싸 해당 파일만 바꾼 바이트로 내보내고 `tests/browser_monitor_usage.py` 의 `main()` 을 그대로 돌림(바뀐 파일이 실제로 7번 서빙됨을 셈).
- **대조군:** 아무것도 안 바꾼 재-exec/대체 서빙 4종 → 단위 56/48/38 건 실패 0, 브라우저 13/13 통과. 하네스 자체가 빨강을 만들지 않음을 확인.
- 기준선(원본): `python3 -m unittest tests.test_monitor_claude_usage tests.test_monitor_ticket_regress tests.test_fleet_graph tests.test_fleet_ctl` → `Ran 141 tests … OK`, `python3 tests/browser_monitor_usage.py` → `통과 13 / 전체 13`.
- 악성 파일 탐침과 `/api/state` 실측은 `pathlib.Path.stat/read_text` 를 그 파일 이름에 대해서만 가로채 내용물을 메모리로 공급했고, 서버는 `browser_monitor_usage.monitor_server` 로 127.0.0.1 임시 포트에 띄움. 운영 모니터는 부르지 않음.
- 감사 범람은 `server.audit` 를 계수기로, `time.time` 을 가짜 시계로 바꿔 모의.

## 적대적 질문에 대한 답

- **악성 파일에 `/api/state` 가 죽는가?** 예 - N1(깊이 ≥ 약 1000, 3 KB 로 충분), N2(`at` 범위 밖). 연결이 응답 없이 끊기고 프런트는 상태 전체를 잃음. 거대 배열 64 KiB 는 1.7 ms 로 무해. 리스트·숫자·제어문자는 무해(N9, N10).
- **DOM 에 글자 그대로 들어가는가?** 전부 `textContent`/`style.width` 숫자. `innerHTML` 로 바꾼 변이(B4, B5)는 생존하지만 서버가 `label` 을 고정하고 `resets_at_iso` 를 정규화하므로 지금은 동치 - XSS 경로 없음.
- **새 범람 구멍?** 무인증은 닫힘(10만 건 → 12줄). 보장 256 은 서로 다른 인증 주체가 있어야 열리며 그때 분당 257줄(N6). **같은 수를 두 번 내보내지 않음**: (e) 80건 → 창 전환 → flush 2회 = `상한 생략 20건` 한 줄. 파일 쓰기(`audit`)는 `_revoked_lock` 밖에서 함 - 락 안 파일 I/O 없음. 남은 문제는 오히려 **못 내보내는 수**(N4, N7).
- **멀쩡한 실패를 한도로 오인?** 예, 실측 - N3. 감사 상한 작업 보고 같은 문장이 그대로 True.
- **브라우저 검사는 그려진 것을 묻는가?** 대체로 그렇습니다: 막대 너비는 `bounding_box` 비율, 색은 `getComputedStyle`, 글은 `inner_text`, 배치는 박스 겹침·`scrollWidth`. CSS `!important` 로 너비를 100% 로 만든 변이(B3)와 crit=warn 색 변이(B1)를 잡음. 빈 곳: "N시간 전 기준"(B12), 소수 퍼센트 반올림(B10).

## 변이 시험 표

| 변이 | 빨간 시험 |
|---|---|
| S1 `percent` 0~100 자르기 제거 | `test_percent_is_clamped` |
| S2 epoch 를 UTC 로 (이 기계 KST) | `test_epoch_resets_at_becomes_local_iso` - TZ=UTC 기계에서는 생존할 것 |
| S3 64 KiB 상한 제거 | **없음 (M1)** |
| S4 `_empty_state` 에서만 `claude_usage` 빼기 | **없음 (M2)** |
| S5 `collect_state` 에서 `claude_usage` 빼기 | 단위 **없음** / 브라우저 10항목 빨강 (S5b) |
| S6 `bool` 을 숫자로 받기 | `test_non_numeric_rows_are_dropped` |
| S7 행 차례 바꾸기 | `test_rows_order_and_labels` |
| S8 미래 `at` 에 age 음수 허용 | **없음 (M7)** |
| A1 `_denied_window_seen` 보장 제거 | 4건 (`test_first_seen_subject_is_written_after_the_cap` 외) |
| A2 `reason` 을 키에서 빼기 | `test_app_ticket_bad_reasons_have_separate_keys`, `test_capped_denial_is_not_marked_as_written` |
| A3 `flush_denied_audit` 두 번째 호출에도 씀 | `test_flush_denied_audit_writes_once` |
| A4 창 전환의 `audit-dropped` 줄 제거 | 3건 |
| A5 밀려난 억제 수 버림 | `test_evicted_suppression_count_is_reported_next_window` |
| A6 창 전환 때 cap 수 안 비움(이중 계상) | `test_cap_skipped_count_is_reported_only_once` |
| A7 창 전환 때 seen 안 비움 | **없음 (M4)** |
| A8 인증 주체 키에서 path 빼기 | 7건 |
| A9 창 길이 60 s → 6000 s | 4건 |
| A10 URL 주체 키에 path 넣기 | `test_real_ticket_subject_cannot_grow_the_audit_keys` |
| A11 상한 걸린 건도 written 증가 | 없음 - **동치**(이미 상한 이상) |
| A12 `serve()` 의 flush 제거 | **없음 (M5)** |
| G1 `report_limit_hit` 늘 False | 다수 (계약표 4행, 2000자, step 계열) |
| G2 한도(verify 없음)인데 재시도 경로로 흘림 | `test_step_limit_hit_blocks_without_retry`, `…keeps_attempt_count_at_two` |
| G3 꼬리 2000자 대신 전문 | **없음 (M3)** |
| G4 verify 통과 면제 제거 | `…with_passing_verify_is_done`, `…with_failing_verify_blocks` |
| G5 verify 실패+한도 → 평범한 실패로 | `test_step_limit_like_report_with_failing_verify_blocks` |
| G6 verify 를 두 번 돌림 | `test_step_limit_like_report_with_passing_verify_is_done` |
| G7 rc != 0 에도 verify 면제 적용 | **없음 (M7)** |
| G8 `status` 의 limit 표시 제거 | `test_cmd_status_marks_limit_nodes` |
| G9 한국어 패턴 전부 제거 | 4건 |
| C1 `_round_hit_limit` 늘 False | 2건 |
| C2 로그 정규식 앵커 풀기 | **없음 (M6)** |
| C3 라운드 거르기 제거 | `test_round_hit_limit_only_when_graph_log_has_limit_line` |
| B1 `usage-crit` 색 = `usage-warn` 색 | 브라우저 "세 상태의 막대 색이 서로 다르다" |
| B2 JS `.usage-fill` 너비 늘 100% | 브라우저 "그려진 막대 너비가 퍼센트를 따른다" |
| B3 CSS `.usage-fill{width:100% !important}` | 브라우저 "그려진 막대 너비가 퍼센트를 따른다" |
| B4 `label` 을 `innerHTML` 로 | 없음 - 지금은 동치(서버 고정 라벨) |
| B5 `reset` 을 `innerHTML` 로 | 없음 - 지금은 동치(정규화된 ISO) |
| B6 stale 문턱 600 → 6000 | 브라우저 "오래된 자료는 'N분 전 기준'…" |
| B7 경고 문턱 80 → 90 | 브라우저 클래스·색 2항목 |
| B8 `isToday` 늘 false | 브라우저 "five_hour 초기화 글이 오늘 꼴이다" |
| B9 JS 행 차례 뒤집기 | 브라우저 8항목 |
| B10 퍼센트 반올림 → 내림 | **없음 (M7)** |
| B11 JS 0~100 자르기 제거 | 없음 - 서버가 먼저 자르므로 동치 |
| B12 "N시간 전 기준" 경계 | **없음 (M7)** |

합계 45개: 잡힘 30, 생존 15 (동치 A11·B4·B5·B11 의 4개를 빼면 **진짜 구멍 11개**: S3, S4, S5(단위), S8, A7, A12, G3, G7, C2, B10, B12).

## 다음 담당자에게

- 우선순위: N1+N2 (한 줄씩, 바깥 `try` 하나로 함께 닫힘) → N3 (rc != 0 조건만으로 실데이터 오인 0) → N4.
- T-242 의 `limit: true` 는 지금도 `G-047.json` 에 남아 있습니다. N5 를 닫기 전까지 R19 연쇄의 멈춤 까닭이 틀릴 수 있습니다.
- 이 검수는 제품·검사 파일을 하나도 바꾸지 않았고 `/tmp` 사본도 만들지 않았습니다(만들려던 시도가 승인 요구로 막혀 메모리 변이로 대신함).
