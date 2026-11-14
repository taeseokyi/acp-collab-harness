# R32 적대적 검수 - 모니터가 앱 serve.py 를 띄워 이어 주는 길 + 서버 정답 저장·화면 (T-335, S1)

대상: `tools/aimem_monitor/app_server.py`(새), `tools/aimem_monitor/server.py`(`_app_api`·`_app_post`·`do_OPTIONS`·`do_GET` api 분기·
`project_app`/`_app_server_decl`·`serve()` 정리·프로젝트 삭제 뒤 `stop`), `projects/자모맞히기/{serve.py,trend_store.py,web/js/trend.js,web/js/ui.js}`.
정본 `.aimem/graph/inputs/r32/SPEC.md`. 저장소 파일은 고치지 않았습니다. 실험은 모두 임시 루트(`tempfile`)·`/tmp/s1r32/` 사본에서 했고,
띄운 자식은 pid 로 내렸습니다(남은 프로세스 0 확인). 변이 사본 `/tmp/s1r32/m` 은 지웠으나 `/tmp/s1r32/`(실험 스크립트·v.log·race.txt)는
`rm -rf` 가 승인 요구로 막혀 남아 있습니다 - 저장소 밖이라 무해, 지워도 됩니다. 운영 모니터는 부르지 않았습니다.

실험 도구(저장소 밖): `/tmp/s1r32/probe.py`(검사의 `tests.test_aimem_monitor_app_proxy.Base` 를 그대로 써서 인증 켠 모니터 +
가짜 앱 서버를 진짜 소켓으로 찌름), `/tmp/s1r32/mut.py`(사본에서 한 군데씩 깨고 검사 실행).

## 1. 재현

`python3 .aimem/graph/inputs/r32/v.py <노드>` 를 한 번씩:

| 노드 | 결과 | 내용 |
|---|---|---|
| store | `v_store: 모두 통과` | test_trend_store 16 · test_dict_server 56 · test_pick_answers 8 OK, `/tmp` 에서 `pick_answers.py --help` rc 0, `trend_meta.json` 안 생김 |
| ui | `v_ui: 모두 통과` | node pass 107 / fail 0 · browser_trend 81/81 · browser_game 121/121 · browser_modes 100/100 · browser_dict 75/75 |
| appsrv | `v_appsrv: 모두 통과` | test_aimem_monitor_app_server 21 OK |
| proxy | `v_proxy: 모두 통과` | app_proxy 20 · app 53 · app_gate 17 · app_server 21 OK |
| news | `v_news: 모두 통과` | test_trend_news 38 · test_pick_answers 8 OK |
| e2e | `v_e2e: 모두 통과` | browser_monitor_app_server 21/21 · browser_monitor_app 8/8 |

## 2. 보안 (요청 목록 1~8)

### (1) 티켓 없이·위조·만료·다른 앱·`..`/`%2e%2e`/이중 인코딩
| 시도 (인증 켬, `/app/~<알파 티켓>/알파/` 아래) | 결과 | 앱 서버에 닿음 |
|---|---|---|
| `GET /app/알파/api/x` (티켓·인증 없음) | 302 → `/login` | 아니오 |
| 위조·만료·다른 앱 티켓 | 403 (검사 `test_forged_*`·`test_expired_*`·`test_other_apps_*` 와 같음, 직접도 확인) | 아니오 |
| 알파 티켓으로 `/감마/api/x` (감마도 서버 선언) | 403 | 아니오 (감마 calls 0) |
| `api/%2e%2e/x`, `api/..%2fx`, `api%2f..%2f..%2fx`, `api/./x`, `api//x` | 404 | 아니오 |
| `api/x%00y` | 400 | 아니오 |
| `api/%252e%252e/%252e%252e/x` (이중 인코딩) | 200 - 앱에 `GET /api/%252e%252e/...` **문자 그대로** 감 | 예 (아래) |
| `api/x%0d%0aX-Evil:%201` | 200 - 앱에 인코딩된 채로 감, 머리 주입 없음 | 예 |

이중 인코딩은 모니터가 한 번 풀어 `..` 를 보고, 앱에는 원래 인코딩 그대로 넘깁니다 - 앱 쪽에서 한 번 풀어도 `%2e%2e` 라 경로가 되지 않고,
자모맞히기 `serve.py` 는 `/api/` 아래를 완전 일치로만 고르므로(정적 파일 길은 `/api/` 로 시작하지 않는 경로뿐, 모니터는 `/api/` 만 넘김) 새는 것이 없습니다. 결함 아님.

### (2) 선언
선언 없는 앱·`..`·절대 경로·`.py` 아님·디렉터리·심볼릭 링크(파일·중간 폴더)는 `test_bad_server_declarations_are_not_forwarded`·
`test_symlinked_directory_in_server_path_is_refused`·`test_app_without_server_declaration_keeps_old_behaviour` 가 다루고 코드(`_app_server_decl` →
`_app_parts` + `_app_inside` + `is_symlink`/`is_file`)도 그대로입니다. `server_error` 글에 경로가 없습니다. 선언이 틀려도 앱 자체는 `runnable` 그대로.

### (3) 죽은·느린·안 뜨는 서버, 동시 시작
- 듣지 않는 스크립트(`time.sleep(120)`), `start_timeout=1.5` → **503, 1.6초**, 남은 프로세스 0.
- 이미 떠 있던 자식을 내린 뒤 동시에 10건 → 200 ×9 + 429 ×1, **자식 1개**(`pgrep` 으로 셈). 하나만 뜸.
- 실제 `serve.py` 의 첫 기동 + `GET /api/trend` 0.10~0.11초 (화면의 2.5초 상한 안).
- 띄운 뒤 `app.json` 의 `server` 가 다른 파일로 바뀌어도 떠 있는 옛 자식을 계속 씀(`ensure` 가 `script` 를 비교하지 않음) → R32-N4(하).
- 앱이 `start_new_session=True` 로 손자를 따로 띄우면 `stop` 뒤에도 그 손자는 남음(같은 그룹 손자는 내려감) → R32-N5(하, 앱 코드가 일부러 하는 일이라 기록만).

### (4) 큰 본문·큰 응답
- `Transfer-Encoding: chunked`(Content-Length 없음) → 411, 앱에 안 감.
- Content-Length 를 실제보다 크게 → 모니터 `Handler.timeout = 15` 로 **15.0초** 뒤 연결 닫힘(스레드 묶임 상한 있음).
- Content-Length 를 실제보다 작게(뒤에 `GET /api/state` 를 붙임) → 응답은 앞 요청 하나뿐, 뒤 바이트로 인증 우회 없음(같은 연결·같은 클라이언트 일).
- 413(읽기 전)·411·음수 400·응답 2MB 넘음 502·느린 응답 504 는 검사가 다루고 변이 M7 로도 잡힘.

### (5) 모니터 내림·재시작·프로젝트 삭제
- `serve()` 는 시작 때 `cleanup_stale()`, 60초 `reap_idle()`, `finally` 에서 `stop_all()`; 삭제 성공 뒤 `stop(pname)` - 코드 확인, 검사 `test_monitor_shutdown_takes_the_child_down` 통과.
- `stop` 뒤 기록 파일이 지워짐(확인).
- **엉뚱한 pid:** 기록의 pid 가 재사용돼 다른 스크립트를 돌리면 살려 둠(검사 `test_cleanup_stale_spares_other_cmdline`). 다만 비교가
  "cmdline 인자 중 하나가 기록의 `script` 와 같음" 뿐이라, 기록의 `script` 가 `-c` 같은 흔한 인자면 아무 프로세스나 내립니다 -
  `{"pid": <python -c sleep>, "script": "-c"}` 기록으로 **희생 프로세스가 내려감**을 확인 → R32-N2(하: 기록은 신뢰하는 상태 파일이고 같은 사용자만 씀).
- **같은 저장소를 두 모니터가 볼 때:** 둘째 모니터의 시작 `cleanup_stale` 이 첫 모니터의 **살아 있는 자식을 내림**(확인; 첫 모니터는 다음 호출에 다시 띄워 200). 이름별 기록 파일도 서로 덮어씀 → R32-N3(하, 운영은 모니터 하나).

### (6) 다른 앱의 서버로 새기
티켓이 앱 이름에 묶여 있어 알파 티켓으로 감마 길은 403(위). 포트는 이름별 기록·`_entries` 로만 찾고, 자식이 죽어 포트를 다른 프로세스가 잡아도
`_alive` 가 `proc.poll()` 을 먼저 보므로 옛 포트로 보내지 않고 다시 띄웁니다. 결함 없음.

### (7) 비밀
- 자식 환경: 모니터에 `FOO_API_KEY`·`AIMEM_ACCESS_TOKEN`·`GH_TOKEN` 을 두고 띄운 자식의 `os.environ` 키 = `HOME LANG PATH PYTHONDONTWRITEBYTECODE PYTHONIOENCODING TZ` 뿐.
- 이어 준 요청 머리: `Cookie`·`Authorization: Bearer <접근 토큰>`·`Origin`·`Referer`·`X-Forwarded-For` 를 실어 보냈을 때 앱이 받은 머리 =
  `accept`, `accept-encoding`(http.client 가 붙이는 `identity`), `host` 뿐.
- 응답 머리: 앱이 `Set-Cookie` 를 보내도 모니터 응답에는 없음(상태·`Content-Type` 만 옮김). 모니터 응답 머리 = ACAO `null`·`Vary`·CSP·보안 머리 등 정적 응답과 같음.
- 감사 로그: `app-api` 줄 5건, 티켓 문자열 없음(쿼리도 뺌).
- 참고: 앱 응답 본문은 `_json` 의 비밀 값 지우기(`_scrub_secrets`)를 거치지 않고 그대로 나갑니다. 앱이 스스로 `.env` 를 읽는 설계라 앱이 키를
  응답에 싣지 않는 것은 앱 책임입니다(자모맞히기 `dict_server` 는 오류 글에 키가 섞일 수 있는 메시지를 싣지 않음 - 301행). 결함으로 올리지 않음.

### (8) OPTIONS
- 무인증·위조 티켓 OPTIONS: 선언 앱 403 / 선언 없는 앱 501 / 없는 앱 501. 바른 티켓 → 204 + `GET, POST`, **앱 서버에 닿지 않음**. `OPTIONS /api/state` 무인증 401.
- 우회 길은 없음. 다만 티켓 검사보다 선언 확인이 먼저라, 무인증으로 "이 이름의 프로젝트가 있고 서버를 선언했는가" 를 403/501 차이로 알 수 있음 → R32-N6(하).

## 3. 자모맞히기

- `GET /api/trend` (실제 `serve.py`, 모니터 길로): 200, `trend` 7건, `last_run: null`. 본문 검사 실패(`days:0`)는 400 그대로 이어짐.
- `sinceText` 경계(node 로 직접): null/'' → '아직 정한 적 없음', 못 읽음·30초·앞날짜 → '방금 정함', 60초 → '1분', 59분59초 → '59분', 1시간 → '1시간',
  23시간59분59초 → '23시간', 24시간 → '1일'. 명세와 같음. `mergeTrend` 는 서버가 덮고, 꼴 틀린 키·숫자 값·`__proto__` 를 버림.
- 오늘 판 정답 고정(R31-N8): `startDaily` 가 줄 있는 저장 판을 그 정답으로 되살리고, `applyServerTrend` 는 오늘 판이 빈 때만 다시 시작 - 명세대로.
- `append_picks`: 프로세스 안에서는 모듈 잠금 + 임시 파일 → `os.replace` 로 원자적이고 있는 날짜를 건너뜀(변이 M3 이 검사에 잡힘).
  **그러나 프로세스 사이에는 잠금이 없어 덮어쓰기(줄 잃음)가 납니다.** 두 프로세스가 같은 파일에 서로 다른 날짜 150건씩 `append_picks` →
  **300건이어야 할 것이 171건**(129줄 잃음). 모니터가 띄운 `serve.py` 와 명령줄 `tools/pick_answers.py`(또는 따로 띄운 `serve.py`)가 겹쳐 쓰면
  이미 정한 날짜 줄이 사라지고, 다음 고르기에서 그 날짜가 다른 낱말로 다시 정해질 수 있습니다 - "이미 있는 날짜는 절대 덮어쓰지 않는다"(R31-N8 서버 쪽 절반)가 깨짐 → R32-N1.

## 4. 변이 (`/tmp` 사본, 한 군데씩)

| 변이 | 돌린 검사 | 결과 |
|---|---|---|
| M1 GET api 길의 티켓 검사 빼기 | `tests.test_aimem_monitor_app_proxy` | FAILED (failures=7) - 잡힘 |
| M2 자식 환경 걸러내기 빼기(`dict(os.environ)`) | `tests.test_aimem_monitor_app_server` | FAILED (failures=1) - 잡힘 |
| M3 있는 날짜 덮어쓰기(`or day in have` 빼기) | `test_trend_store.py` | FAILED (failures=3) - 잡힘 |
| M4 OPTIONS 티켓 검사 빼기 | proxy | FAILED (failures=1) - 잡힘 |
| M5 `server.py` 에서 모든 요청 머리를 넘기기 | proxy | **OK - 안 잡힘** (아래) |
| M5b `app_server.forward` 의 머리 거르기 빼기 | app_server | FAILED (failures=1) - 잡힘 |
| M6 `cleanup_stale` 의 cmdline 확인 빼기 | app_server + proxy | FAILED (failures=2) - 잡힘 |
| M7 `/app/` POST 본문 413 빼기 | proxy | FAILED (errors=1) - 잡힘 |
| M8 api 경로 `..` 거르기 빼기 | proxy | FAILED (failures=3) - 잡힘 |

M5 가 안 잡히는 것은 `app_server.forward` 가 한 번 더 걸러 실제로 새지 않기 때문입니다(이중 방어의 바깥 겹). 결함 아님 - 두 겹 중 안쪽(M5b)은 검사가 지킵니다.

## 5. 결함

| 번호 | 심각도 | 무엇 | 어디 | 재현 | 고칠 방향 |
|---|---|---|---|---|---|
| R32-N1 | 중 | `append_picks`·`record_run` 이 프로세스 사이 잠금 없이 읽고-덮어써서, 두 프로세스가 겹쳐 쓰면 줄을 잃음(이미 정한 날짜가 사라져 다시 정해질 수 있음) | `projects/자모맞히기/trend_store.py` `append_picks` (`_LOCK` 은 `threading.Lock` 뿐) | 두 프로세스가 같은 임시 파일에 서로 다른 날짜 150건씩 `append_picks` → 300 대신 171건 | 같은 폴더의 잠금 파일에 `fcntl.flock`(표준 라이브러리)을 `_LOCK` 안에서 잡고 읽기·쓰기, 또는 덧붙이기만 `O_APPEND` 로 하고 읽을 때 첫 줄 우선(지금도 `setdefault`). 두 프로세스 검사 하나 |
| R32-N2 | 하 | `cleanup_stale` 의 pid 재사용 보호가 "cmdline 인자 하나가 기록 `script` 와 같음" 뿐이라, 기록의 `script` 가 흔한 값이면 엉뚱한 프로세스를 내림 | `tools/aimem_monitor/app_server.py` `cleanup_stale` | `state_dir/zz.json` = `{"pid": <python -c sleep 60>, "script": "-c"}` → `cleanup_stale()` 이 그 pid 를 내림 | `script` 가 절대 경로·`.py`·`state_dir` 의 루트 `projects/` 아래인지 보고, cmdline 의 **두 번째 인자**(=`argv[1]`)가 정확히 `script` 이며 `--host 127.0.0.1 --port <기록 port>` 가 따라올 때만 내림 |
| R32-N3 | 하 | 같은 저장소를 두 모니터가 보면 둘째의 시작 정리가 첫째의 살아 있는 자식을 내리고, 이름별 기록 파일을 서로 덮어씀 | `app_server.py` `cleanup_stale`·`_write_record` | 같은 `state_dir` 로 `AppServers` 둘 - 첫째로 띄운 뒤 둘째 `cleanup_stale()` → 첫째 자식 내려감 | 기록에 모니터 pid(`owner`)를 넣고 그 pid 가 살아 있으면 건너뜀. 운영은 하나라 낮음 |
| R32-N4 | 하 | 떠 있는 자식은 `app.json` 의 `server` 가 바뀌어도 그대로 쓰임 | `app_server.py` `ensure` | 스크립트 A 로 `forward` 뒤 같은 이름으로 스크립트 B `forward` → A 의 응답 | `ensure` 에서 `entry.script != str(script)` 면 내리고 다시 띄움 |
| R32-N5 | 하 | 앱이 `start_new_session=True` 로 띄운 손자는 `stop`·`stop_all` 뒤에도 남음 | `app_server.py` `_kill_group` | 손자를 setsid 로 띄우는 가짜 앱 → `stop` 뒤 손자 1개 남음(같은 그룹 손자는 0) | 기록만(앱이 일부러 빠져나가는 경우). 필요하면 자식 `/proc/<pid>/task/*/children` 을 거둬 함께 내림 |
| R32-N6 | 하 | 무인증 OPTIONS 가 티켓 검사 전에 선언을 봐서 403/501 차이로 프로젝트·서버 선언 유무가 드러남 | `server.py` `do_OPTIONS` | 위조 티켓 OPTIONS: 서버 선언 앱 403, 선언 없는 앱·없는 앱 501 | 티켓 경로 꼴이면 먼저 `_app_ticket_check` 를 하고 그 뒤 선언 확인(GET·POST 와 같은 순서) |

'상' 없음.

## 6. 판정

새로 여는 길의 경계(티켓 검사 한 벌·경로 검사·좁은 환경·머리 거르기·본문 상한·OPTIONS·pid 로만 내리기)는 실험과 변이 모두에서 지켜졌습니다.
남은 것은 서버 정답 파일의 프로세스 사이 덮어쓰기(중) 하나와 하 다섯입니다. 모니터 재시작 필요(관리자 검토 뒤, 클로드 코드가).

판정: 통과
