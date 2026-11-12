DONE

- **N1·N2·N4 는 닫혔습니다**(깊이 1500/5000/30000, `rate_limits` 깊음, `_empty_state` 갈래, 범위 밖 `at` 전부 `/api/state` 200, 실제 SIGTERM 에 `audit-dropped 상한 생략 23건` 남음). 그러나 **같은 카드에서 새 길(P1)이 열려 있습니다**: `at` 에 짝 없는 서러게이트(`"\ud800"`, 71 B 파일) 하나면 `/api/state` 가 정상·실패 두 갈래 모두 응답 없이 **`RemoteDisconnected`** 로 끊깁니다. 바깥 `try` 는 직렬화 단계(`_send` 의 `encode`)를 감싸지 못합니다.
- **N3 은 실데이터에서 닫혔습니다**: 저장된 실행 257건 전수(끝난 것 244건)를 새 규칙으로 걸면 **T-215 한 건(진짜 한도)만** 걸립니다. 옛 글자 규칙은 이제 rc 0 DONE 보고 **5건**(T-237·T-242·T-243·T-246·T-247)을 오인했을 것입니다. 다만 rc != 0 표본이 4건뿐이고, 패턴에 `hit your weekly limit` 같은 형제 문구가 빠져 있습니다(P3).
- **시험 구멍**: 변이 19개 중 **6개가 살아남습니다** - SIGTERM 처리기 설치 지우기·되돌리기 지우기·`serve()` 의 flush 지우기(**SIGTERM 시험이 하나도 없음**, 모니터 시험 117건 전부 초록), `_empty_state` 만 / `collect_state` 만 `claude_usage` 줄 빼기(R18 M2 그대로), 바깥 `try` 지우기.

# R19 재검수 (T-248, S1) - N1·N2·N3·N4 수정이 정말 닫혔는가

검수 대상: 작업 트리 그대로(커밋 87ad847 + 미커밋 R18·R19 변경). 제품·시험 파일은 하나도 바꾸지 않았고 저장소를 `/tmp` 로 복사하지 않았습니다. 임시 디렉터리는 `tempfile` 의 임시 저장소(가짜 root)로만 썼고, 서버는 전부 127.0.0.1 임시 포트(`port=0`)입니다. 운영 10443 은 건드리지 않았습니다.

## 1. 발견 표

| # | 심각도 | 무엇이 | 어디(파일:행) | 어떻게 재현 | 고칠 법 |
|---|---|---|---|---|---|
| P1 | **높음** | `at` 에 짝 없는 서러게이트가 있으면 `claude_usage()` 는 정상 반환하지만, 그 글자가 `/api/state` 로 그대로 실려 `_send` 의 `body.encode("utf-8")` 가 `UnicodeEncodeError` → 연결이 응답 없이 끊김. 실패 갈래(`_empty_state`)도 같은 카드를 실으므로 대체 화면도 없음. N1 과 같은 부류(곁다리 카드가 상태 전체를 죽임)이며, R18 N9(“`at` 은 내보내지 말 것”)를 따랐으면 막혔을 길 | `tools/aimem_monitor/server.py:1006` (나가는 곳), `:2489` (죽는 곳), 부르는 곳 `:896`·`:1148` | 파일 `{"at": "\ud800", "rate_limits": {"five_hour": {"used_percentage": 40}}}` (JSON 이스케이프 그대로, 71 B) → `server.claude_usage(root)` 는 `rows=1 at='\ud800'` 반환 → 임시 포트 `/api/state` 정상 갈래·`reader.collect` 예외 갈래 둘 다 `RemoteDisconnected`, 서버 로그에 `UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' … surrogates not allowed` | (a) `at` 은 내보내지 말고 `age_seconds` 만 (가장 간단, N9 도 함께 닫힘). 또는 (b) `at.encode("utf-8")` 이 실패하면 `at=None`. 더 넓게는 (c) `_send` 가 `encode("utf-8", "replace")` 하거나 `json.dumps(ensure_ascii=True)` - 다른 상태 글자(파일 이름 등)로 같은 일이 나는 것까지 막음. 시험: 이 파일로 `/api/state` 200 |
| P2 | 중간 | **SIGTERM 경로를 묻는 시험이 없음.** 처리기 설치를 지워도, 원복을 지워도, `serve()` 의 `flush_denied_audit` 을 지워도 시험 117건(`test_monitor_claude_usage`·`test_monitor_ticket_regress`·`test_aimem_monitor`) 전부 초록. R18 M5 가 그대로 남음 | `server.py:3218`, `:3242`, `:3245` | 변이 S7·S8·S9 (아래 표) | 자식 프로세스로 `serve(port=0, root=임시)` 를 띄우고 `_denied_cap_skipped` 를 0 보다 크게 해 둔 뒤 SIGTERM → rc 0 과 `access.log` 의 `audit-dropped` 줄을 요구. 같은 프로세스에서 `serve(once=True)` 뒤 `signal.getsignal(SIGTERM)` 이 원래 값인지 요구. 아래 §3 N4 의 재현이 그대로 시험이 됨 |
| P3 | 중간 | 한도 패턴이 진짜 문구의 형제들을 놓침. 실데이터의 진짜 한도는 `You've hit your 5-hour limit · resets …` 인데, 패턴은 `hit your 5-hour limit` 만 있어 같은 꼴의 `hit your weekly limit`·`hit your Opus limit`·`hit your limit` 이 False. rc != 0 조건이 생겨 오인 위험이 크게 줄었으므로 이제는 넓혀도 됨 | `tools/fleet_graph.py:418` | `report_limit_hit("You've hit your weekly limit · resets Mon 9am")` → False. 같은 꼴로 `"You've hit your Opus limit · resets 3pm"`, `"You've hit your usage limit. Upgrade to Pro…"`, `"exceeded retry limit, last status: 429 Too Many Requests"`, `"Rate limit reached for requests"` → 모두 False. (주의: 5-hour 외 문구는 **실데이터에 없는 가정 문구**입니다) | rc != 0 일 때만 보므로 `re.search(r"hit your .{0,20}limit|limit reached|429 too many requests|rate limit", tail)` 정도로 넓힐 것. claude 하네스는 글자보다 `.out` 의 `api_error == "usage_limit_reached"` / `api_error_status == 429` 를 먼저 볼 것(T-215 에 그대로 있음) |
| P4 | 중간 | `_empty_state` 의 `claude_usage` 줄만 빼도, `collect_state` 의 줄만 빼도 시험 초록 - `_blank_keys` 가 이미 `None` 키를 주고 시험 root 에는 파일이 없음. R18 M2 가 **안 닫힘**. 새 시험 `test_both_state_branches_have_claude_usage` 는 키 **존재**만 물음 | `tests/test_monitor_claude_usage.py:265`, 제품 `server.py:896`·`:1148`·`:906` | 변이 S5·S6 생존. `_blank_keys` 의 키까지 함께 빼야(S5b) 빨개짐 | 시험에서 **유효한** 사용량 파일을 쓰고 두 갈래 모두 `state["claude_usage"]["rows"]` 가 비어 있지 않음을 요구 |
| P5 | 낮음 | 바깥 `try`(`_safe_claude_usage`)를 지워도 초록 - 안쪽 `except` 가 이미 `RecursionError` 를 잡아 지금은 동치. 그러나 P1 처럼 **새 예외가 생기면** 바깥 `try` 만이 막아 줄 자리이므로, 이를 고정하는 시험이 있어야 함 | `server.py:945` | 변이 S2 생존, S1+S2(둘 다 지우기)는 2건 빨강 | `mock.patch.object(server, "claude_usage", side_effect=RuntimeError)` 상태로 `/api/state` 200 과 `claude_usage is None` 요구 |
| P6 | 낮음 | 처리기 설치(`:3218`)와 `try:`(`:3234`) 사이에 `log_line` 여러 줄이 있음. 그 틈에 SIGTERM 이 오면 `KeyboardInterrupt` 가 `try` 밖에서 터져 원복도 flush 도 안 됨. 같은 틈에서 `log_line` 이 예외를 내도 처리기가 원복되지 않은 채 남음 | `server.py:3214-3234` | 정적 확인(틈이 짧아 실측으로 맞히지는 않음) | 설치를 `try:` 바로 앞으로 옮기거나, 설치부터 `try/finally` 안에 넣을 것 |
| P7 | 정보 | N3 의 rc != 0 표본이 작음: 끝난 실행 244건 중 rc != 0 은 **4건**(claude 2, opencode 2), 그중 한도 1건. 새 규칙의 정밀도는 맞지만 근거가 얇음. codex 는 rc != 0 실행이 0건이라 **codex 가 한도에서 몇으로 끝나는지 자료가 없음** | `.aimem/runs` | 아래 §3 N3 | codex 한도 실행이 처음 생기면 `.rc`·`.err` 를 보관해 패턴을 맞출 것 |
| P8 | 정보 | 운영 10443 프로세스는 R19 코드를 아직 읽지 않았음 - 재기동 전까지 N4 처리기는 운영에 없음. `serve()` 가 찍는 시작 줄은 `port=0` 일 때 실제 포트가 아니라 `:0` 을 찍음(시험용 띄움에서만 보이는 겉모습) | `server.py:3223` | 임시 포트 띄움 로그 `http://127.0.0.1:0/` | `httpd.server_address[1]` 을 찍을 것(선택) |

## 2. 변이 시험 표

방법: R18 과 같음. `os.fork()` 한 자식에서 모듈 원문에 문자열 치환을 하고(대상이 **정확히 1회** 나오는지 assert) `exec(compile(...), mod.__dict__)` 로 덮어쓴 뒤 해당 unittest 모듈을 돌림. 디스크 쓰기 없음. 대조군(치환 없음): `test_monitor_claude_usage` 23/23, `test_fleet_graph` 51/51, 모니터 3묶음 117/117 초록. 하네스가 빨강을 만들지 않음을 확인.

| 변이 | 빨개진 시험 | 판정 |
|---|---|---|
| S1 `RecursionError` 를 `except` 에서 빼기 | `test_deeply_nested_json_is_none_without_exception` | 잡힘 |
| S2 바깥 `try`(`_safe_claude_usage`) 지우기 | 없음 | **생존 (P5, 지금은 동치)** |
| S1+S2 둘 다 | `…deeply_nested…`, `test_api_state_200_with_deeply_nested_usage` | 잡힘 |
| S3 `at` 의 `OverflowError` 빼기 | `test_out_of_range_at_is_not_fatal` 두 subTest (`0001…+05:00`, `9999…-05:00`) | 잡힘 |
| S4 64 KiB 상한 지우기 | `test_over_64_kib_with_normal_rate_limits_is_none` | 잡힘 (R18 M1 닫힘) |
| S5 `_empty_state` 에서만 `claude_usage` 줄 빼기 | 없음 | **생존 (P4)** |
| S5b S5 + `_blank_keys` 의 키까지 빼기 | `test_both_state_branches_have_claude_usage`, `test_state_keys` | 잡힘 |
| S6 `collect_state` 에서만 줄 빼기 (모니터 117건 기준) | 없음 | **생존 (P4)** |
| S7 SIGTERM 처리기 설치 지우기 (117건 기준) | 없음 | **생존 (P2)** |
| S8 처리기 되돌리기 지우기 (117건 기준) | 없음 | **생존 (P2)** |
| S9 `serve()` 의 `flush_denied_audit` 지우기 (117건 기준) | 없음 | **생존 (P2, R18 M5 그대로)** |
| G1 `rc != 0` 조건 지우기 | `…rc_zero_is_not_a_limit`, `…passing_verify_is_done`, `…failing_verify_is_retried_without_limit` | 잡힘 |
| G2 새 걸림말 둘 지우기 | 계약표 subTest 2건 | 잡힘 |
| G2a `session limit reached` 만 | 계약표 1건 | 잡힘 |
| G2b `reached your usage limit` 만 | 계약표 1건 | 잡힘 |
| G3 꼬리 2000자 → 전문 | `…only_reads_last_2000_chars`, `…before_last_2000_chars_with_nonzero_rc_is_not_limit` | 잡힘 (R18 M3 닫힘) |
| G4 rc != 0 한도 갈래를 `if False` 로 | 4건 (`…blocks_without_retry`, `…keeps_attempt_count_at_two`, `…rc_nonzero_blocks_with_limit`, `…flag_remains_in_saved_graph_json`) | 잡힘 |
| G5 `cmd_status` 의 `(사용 한도)` 표시 빼기 | `test_cmd_status_marks_limit_nodes` | 잡힘 |

합계 19개(대조군 제외): 잡힘 13, **생존 6** (S2 는 지금 동치이나 방어선 고정용으로 구멍으로 셈). 브리프가 든 여덟 가지(RecursionError·바깥 try·OverflowError·처리기·원복·rc != 0·걸림말 둘·64 KiB·`_empty_state` 만)는 모두 넣었습니다.

## 3. R18 의 N1·N2·N3·N4 판정

### N1 - **닫힘** (같은 부류의 새 길 P1 은 열림)

임시 저장소 + 임시 포트 `/api/state`, 정상 갈래와 `reader.collect` 를 `RuntimeError` 로 바꾼 `_empty_state` 갈래를 각각 측정:

| 파일 | 크기 | `claude_usage()` | 정상 갈래 | `_empty_state` 갈래 |
|---|---|---|---|---|
| 정상 `rate_limits` + 깊이 1500 리스트 | 3,093 B | None | 200 | 200 |
| 깊이 5000 | 10,093 B | None | 200 | 200 |
| 깊이 30000 (64 KiB 바로 아래) | 60,093 B | None | 200 | 200 |
| 깊이 3000 dict 중첩 | 18,065 B | None | 200 | 200 |
| `rate_limits.five_hour` 안이 깊이 3000 | 6,062 B | None | 200 | 200 |

안쪽 `except` 에 `RecursionError` 가 들어가 깊이 문제는 함수 안에서 끝납니다. 다만 깊은 파일은 **카드 전체가 None** 이 됩니다(정상 `rate_limits` 가 있어도). 이것은 의도된 실패 방식으로 봅니다.

### N2 - **닫힘**

`at` 이 `0001-01-01T00:00:00+05:00`, `9999-12-31T23:59:59-05:00`, `0001-01-01T00:00:00+14:00`, `9999-12-31T23:59:59.999999-14:00`, `"+99999-01-01"`, 숫자 `1731390000`, `null` 일 때 모두 예외 없이 `rows=1, age_seconds=None`, 두 갈래 모두 200. `resets_at` 이 `1e300`·서러게이트일 때도 행은 남고 `resets_at_iso=None`. **단 서러게이트 `at` 은 P1** (`age_seconds` 계산은 무사하지만 글자가 그대로 나가서 직렬화에서 죽음).

### N3 - **닫힘** (패턴 폭은 P3, 표본은 P7)

`fleet._run_state` / `fleet.run_report` 로 `.aimem/runs/*.json` 257건을 전수 재측정(끝난 것 244건: claude rc0 68 / rc≠0 2, codex rc0 94, opencode rc0 78 / rc≠0 2, 미완료 13):

- **새 규칙(rc != 0 + 글자)에 걸리는 것: `T-215-S1-a1-101031` 한 건.** `.out` 이 `is_error=True, api_error_status=429, api_error=usage_limit_reached, terminal_reason=api_error` 인 진짜 한도. 정밀도 1/1.
- **옛 글자 규칙만 걸리는 것: 5건, 전부 rc 0 정상 DONE** - T-237(codex), T-242(codex), T-243(opencode), T-246(codex), T-247(opencode). R18 때 3건에서 2건 늘었음(한도 작업 보고가 패턴을 인용하기 때문). 새 규칙에서 모두 사라짐.
- **진짜 한도인데 rc 0 인 하네스?** claude rc 0 실행 68건의 `.out` 에서 `is_error`·`api_error_status`·비정상 `terminal_reason` 이 있는 것 **0건**. codex·opencode 의 `.err` 꼬리 4,000자에서 `429|rate limit|usage limit|quota|한도` 를 찾으면 10건이 걸리지만 전부 작업자가 **소스를 읽은 흔적**(`rate_limit` 변수, `한도` 문서)이며 보고는 정상 완료. 따라서 **실데이터에는 놓친 한도가 없음**.
- 나머지 rc != 0 3건: claude `20261109-163112-S1`(빈 `.out`), opencode 2건(`Cannot connect to API`) - 한도 아님, 새 규칙도 안 걸림. 맞음.
- **놓치는 비용(가정):** 어떤 하네스가 한도에서 rc 0 으로 끝난다면 (a) verify 가 있는 노드: verify 실패 → 보통 재시도로 시도 1회를 헛씀 → `max_attempts` 에서 blocked, 까닭은 "한도" 가 아니라 평범한 실패. (b) **verify 가 없는 노드: rc 0 이면 바로 done** - 한도로 끊긴 빈 일이 완료로 표시됨. 이것이 가장 비싼 경우이나, 한도 갈래가 생기기 전에도 같았으므로 R19 가 만든 퇴행은 아닙니다. 막으려면 claude 는 `.out` 구조 신호를 rc 와 상관없이 볼 것.

### N4 - **닫힘** (시험 없음 P2, 틈 P6)

- **실제 SIGTERM:** 자식 프로세스에서 `server._denied_cap_skipped=20, _denied_evicted_skipped=3` 로 두고 `serve(host="127.0.0.1", port=0, root=임시, auth=False)` → 1초 뒤 SIGTERM → **rc 0, 0.02 s**, 임시 `.aimem/access.log` = `…\taudit-dropped\t-\t-\t상한 생략 23건`. `once=True` 로도 같음(rc 0, 같은 줄).
- **대조:** 처리기 설치를 지운 변이로 같은 일을 하면 **rc -15, `access.log` 없음** - 처리기가 실제로 일을 함.
- **주 스레드가 아닐 때:** 스레드에서 `serve(once=True)` → 요청 1건 → 반환 `0`, `ValueError` 없음, 프로세스 SIGTERM 처리기 그대로.
- **원복:** 주 스레드에서 `serve(once=True)` 뒤 `signal.getsignal(SIGTERM)` 이 원래 값(`SIG_DFL`=0)으로 돌아옴. 자식 프로세스의 `serve()` 반환 뒤에도 `SIG_DFL`.
- `monitorctl.sh:43-45` 는 `kill` 뒤 6초(0.2 s × 30)를 기다리고 `kill -9` - 0.02 s 안에 내려가므로 넉넉함.

## 4. 기준선과 실제로 돌린 명령

- `python3 tools/aimem_db.py check --slot S1 --token a41f0c --rev 160` → `일치: S1 토큰 a41f0c …`
- `python3 -m unittest tests.test_monitor_claude_usage tests.test_fleet_graph` → `Ran 74 tests … OK` (23 + 51, 브리프의 23+·51+ 충족)
- 변이: 위 fork+exec 하네스(파이썬 표준 입력으로 실행, 파일 없음). 탐침·SIGTERM·전수 재측정도 같은 방식.

## 5. 우선순위

1. **P1** (높음) - `at` 을 내보내지 않기 한 줄 + `/api/state` 200 시험. 할 김에 `_send` 의 `encode` 를 `errors="replace"` 로 하면 같은 부류 전체가 닫힘.
2. **P2** - SIGTERM 시험 두 개(자식 프로세스 + `audit-dropped`, 원복). §3 N4 재현을 그대로 옮기면 됨.
3. **P4** - 유효 파일로 두 갈래의 `rows` 를 요구(R18 M2 를 이번에야 닫기).
4. **P3** - rc != 0 조건 아래서 패턴 넓히기 + claude `.out` 구조 신호.
5. P5·P6 - 바깥 `try` 고정 시험, 처리기 설치 위치를 `try` 바로 앞으로.
6. P7·P8 - 정보. 운영 반영은 모니터 재기동 뒤.
