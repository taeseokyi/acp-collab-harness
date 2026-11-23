# R39 적대적 검수 - S6(freebuff) 수정 7건 (T-379, S1)

**판정: 조건부 통과 - 상 0 · 중 0 · 하 4.** 15건(R38-N1~N6, R37-N1~N9)은 모두 닫혔습니다. R38-N1(상)은 실제 서버에서 다시 해 봐도 재현되지 않습니다.
새로 찾은 하 4건 가운데 R39-N1 은 T-374 가 만든 **회귀**입니다(날짜 검사가 느슨해짐). 나머지 세 건은 문서 두 건과 R38-N4 를 고치고도 남은 끝 한 건입니다.
제품 코드는 고치지 않았습니다. 실험은 `/tmp/r39s1-*` 에서만 했고, 데이터는 `/tmp/r39s1-vdata` 에 두었습니다.

## 돌린 검증

| 명령 | 마지막 줄 | 기대(tests/README.md) |
| ---- | -------- | --------------------- |
| `python3 -m unittest discover -s projects/VoxLog/tests` | `Ran 136 tests` / `OK` | (T-374 보고 136) 일치 |
| `python3 projects/VoxLog/tests/browser_voxlog.py` | `26/26 통과` | 26 |
| `python3 -m unittest discover -s projects/자모맞히기/tests -p test_*.py` | `Ran 144 tests` / `OK` | README 132 → **낡음**(R39-N3) |
| `node --test projects/자모맞히기/tests/*.mjs` | `ℹ pass 109` `ℹ fail 0` | README 107 → 낡음 |
| `python3 projects/자모맞히기/tests/browser_game.py` | `통과 121 / 전체 121` | 121 일치 |
| `python3 projects/자모맞히기/tests/browser_modes.py` | `통과 100 / 전체 100` | 100 일치 |
| `python3 projects/자모맞히기/tests/browser_dict.py` | `통과 75 / 전체 75` | 75 일치 |
| `python3 projects/자모맞히기/tests/browser_trend.py` | `통과 85 / 전체 85` | README 81 → 낡음(새 시나리오 4검사) |

### 실제 서버 재현 (VoxLog `serve.py --port 18961 --data /tmp/r39s1-vdata`, 토큰 없음)
- 녹음을 올린 뒤 `HEAD /api/recordings/<id>` 를 보냈습니다. Origin 이 없을 때와 `Origin: https://evil.example` 일 때 모두 **200 이고, 이어서 GET 하면 200(남아 있음)**. HEAD 목록 200, HEAD audio 200, HEAD retry·ask 405.
- 같은 id 에 메서드를 바꿔 보냈습니다. PUT·PATCH 는 Origin 이 없으면 405, evil Origin 이면 403. OPTIONS 204. PROPFIND·TRACE·CONNECT·소문자 `get` 은 501. **모든 경우에 녹음이 남았습니다.** 지우는 길은 DELETE 하나이고, evil Origin 을 단 DELETE 는 403 입니다.
- DNS 되돌림: `Host: evil.example` 이면 GET·HEAD 모두 403.
- `X-Recorded-At` 은 값마다 결과가 이렇습니다.
  - 201 + 서버 시각 기록: `9999-12-31T23:59:59+00:00`, `not-a-date`, 시간대 없는 값, `2026-11-23`
  - 201 + 보낸 값 유지: `…Z`, 앞뒤 공백이 붙은 `+09:00` 값
  - **연결 끊김**: `0001-01-01T00:00:00+14:00`, `9999-12-31T23:59:59-14:00` (R39-N2)
- `from=2026-13-40`·`to=2026-02-30`·`from=2026-1-1` 은 400 입니다. 그런데 **`from=20261123` 과 `to=2026-W48-1` 은 200** 입니다(R39-N1).
  같은 데이터로 돌려 보면 `from=2026-11-23` 은 12건, `from=20261123` 은 **0건**, `to=2026-W48-1` 은 14건(전부)이 나옵니다.
- `/api/ask` 의 kind 가 `[]`·`{}`·없음이면 400 JSON, `"nope"` 이면 400 입니다. ids 가 이상해도 400 입니다.

### 실제 서버 재현 (자모맞히기 `serve.Handler`, /tmp 의 trend.txt)
- trend.txt 에 `사과`·`닭`(6칸 아님)과 `한국`·`위반` 을 넣었습니다. `GET /api/trend` 는 `{'2026-11-24': '한국', '2026-11-26': '위반'}` 을 돌려줍니다. 서버 경로가 6칸 아닌 낱말을 거릅니다.
- `Sec-Fetch-Site` 값별 결과:
  - 머리 없음·`same-origin`·`none`·`same-site` → 200
  - `cross-site`(대소문자·공백이 달라도) → 403
  - 정적 `/` 은 `cross-site` 여도 200
  - Origin 없는 POST pick 은 `cross-site` 면 403
  - DNS 되돌림 → 403
- 모니터 '앱 열기' 경로를 확인했습니다. `tools/aimem_monitor/server.py:3261` 은 `Content-Type`·`Accept` 만 앱 서버로 넘기므로, sandbox(불투명 출처)의 `Sec-Fetch-Site: cross-site` 가 serve.py 까지 닿지 않습니다. **정상 경로가 막히지 않습니다.**
- 화면 경로(R37-N2)는 browser_trend 의 `scenario_bad_server_answer` 가 지킵니다. 아래 변이 시험에서 83/85 로 떨어지는 것을 확인했습니다.

### 변이 시험 (/tmp 사본에 하나씩 넣고 그 검사 파일만 돌림, 사본은 지움)

| 변이 | 잡힘 |
| ---- | ---- |
| VoxLog 라우팅이 `self.command == "GET"` 을 보게 함(HEAD → 지움) | `test_head_detail_does_not_delete`·`test_head_foreign_origin_does_not_delete` FAIL |
| 출처 검사를 `in ("POST","DELETE")` 로 되돌림 | `test_foreign_origin_write_403` FAIL |
| kind 문자열 검사 뺌 | `test_ask_nonstring_kind_400_json_then_ok` ERROR |
| 시간대 없는 recorded_at 허용 | `test_bad_recorded_at_uses_server_time` FAIL |
| `_valid_date` 를 늘 참으로 | `test_bad_date_filter_is_400` FAIL |
| `build_prompt` 를 문자열 정렬로 되돌림 | test_ask 2개 FAIL |
| retry 의 `except ValueError` → `KeyError` | `test_retry_resubmit_valueerror_404_json` ERROR |
| health 의 빈 명령 검사 뺌 | `TestHealthWhitespaceLlmCmd` ERROR |
| 자모 `trend_store._is_word` 에서 6칸 검사 뺌 | test_trend_store 5 FAIL |
| `trend.js isAnswer` 에서 6칸 검사 뺌 | test_trend.mjs 3 ✖, browser_trend `통과 83 / 전체 85` rc 2 |
| serve.py `_api` 가 `KeyError` 만 잡게 함 | `test_unhandled_exception_is_json_500…` ERROR |
| Sec-Fetch-Site 비교값을 바꿈 | `test_cross_site_without_origin_403` FAIL |
| dict.js `네` 뺌 | test_dict.mjs ✖ |
| trend_news 에서 opener 를 넘기지 않음 | `test_opener_is_passed_to_lookup_sources` FAIL |
| pick_answers 0줄일 때 `0줄 덧붙였습니다` | `test_zero_added_says_nothing_new_saved` FAIL |
| pick_answers `이미 있음` 줄에 뉴스 낱말을 찍음 | `test_already_there_dates_print_with_their_stored_word` FAIL |

16개 모두 잡혔습니다. 잡지 못하는 변이는 하나 있습니다. `_valid_date` 가 `20261123` 을 받아들이는 지금 동작인데, 이것은 검사가 없어서 R39-N1 이 됩니다.

## 결함

| 번호 | 심각도 | 프로젝트 | 내용 | 위치 | 재현 | 고침 제안 |
| ---- | ------ | -------- | ---- | ---- | ---- | -------- |
| R39-N1 | 하(회귀) | VoxLog | T-374 가 `DATE_RE` 를 지우고 `datetime.date.fromisoformat` 하나만 남겼습니다. 파이썬 3.11 의 이 함수는 `20261123`(기본형)과 `2026-W48-1`(ISO 주)도 받아들입니다. 그런데 store 는 이 값을 문자열로 `day < date_from` 비교하므로 **400 대신 200 + 틀린 목록**이 나옵니다. 고치기 전에는 정규식 덕분에 400 이었습니다. INTERFACE.md 의 "YYYY-MM-DD 이면서" 설명과도 어긋납니다 | `serve.py` `_valid_date`(약 92행), `_rec_list` 457행 | `GET /api/recordings?from=20261123` → 200, 0건(같은 데이터로 `from=2026-11-23` 은 12건). `to=2026-W48-1` → 200, 전부 | 정규식 `^\d{4}-\d{2}-\d{2}$` 와 `fromisoformat` 을 둘 다 검사합니다. `test_bad_date_filter_is_400` 에 `20261123`·`2026-W48-1` 을 더합니다 |
| R39-N2 | 하 | VoxLog | `_valid_recorded_at` 의 `dt.astimezone(utc)` 는 날짜 범위 끝(1년 1월 1일 +14:00, 9999-12-31 -14:00 등)에서 `OverflowError` 를 냅니다. 이 예외를 잡지 않아 업로드가 응답 없이 끊깁니다. 서버에는 traceback 이 남고, 자리(slot)는 finally 가 돌려줍니다. 대기열 쪽에서 보면 '연결 오류 → 다시 올림' 이라 같은 녹음을 끝없이 다시 보냅니다. 앱은 `localIso`/`toISOString` 만 보내므로 실제로 일어날 가능성은 낮습니다. "못 쓰는 값이면 서버 시각" 이라는 규칙의 빈틈입니다 | `serve.py` `_valid_recorded_at` (`dt.astimezone(...)` 줄) | `X-Recorded-At: 0001-01-01T00:00:00+14:00` 로 업로드 → `RemoteDisconnected` | `except (ValueError, OverflowError)` 로 넓히고 `astimezone` 도 try 안에 넣습니다. 검사 한 줄을 더합니다 |
| R39-N3 | 하(문서) | 자모맞히기 | `tests/README.md` 의 기대 수가 낡았습니다. 표(9~14행)·16~17행·89행이 로직 107·파이썬 132·트렌드 81 이고, 실제는 109·144·85 입니다. README 는 "수가 위와 다르면 rc 0 이어도…" 를 판정 기준으로 쓰라고 하므로, 지금은 다음 검수자가 정상을 이상으로 읽게 됩니다 | `projects/자모맞히기/tests/README.md` | 위 검증 표 | 109·144·85 로 고치고 날짜를 2026-11-23(R39) 으로 적습니다 |
| R39-N4 | 하(문서) | VoxLog | INTERFACE.md 의 health 행에 T-373 이 더한 `llm_error`(설정 오류일 때만 붙음)가 없습니다. ask 의 `kind` 가 문자열이 아니면 400 이라는 것도 적혀 있지 않습니다(상태 코드는 원래 4xx 라 큰 문제는 아님) | `projects/VoxLog/docs/INTERFACE.md:142` | `VOXLOG_LLM_CMD="   "` → `{"ok":true,…,"llm":false,"llm_error":"…"}` (TestHealthWhitespaceLlmCmd) | health 행에 `(+ "llm_error": str, VOXLOG_LLM_CMD 가 비었거나 따옴표가 안 맞을 때)` 를 더합니다 |

참고(결함 아님):
- R37-N5 의 `Sec-Fetch-Site` 판정은 `same-site` 를 통과시킵니다. 그래서 같은 호스트의 다른 포트 페이지(예: `http://127.0.0.1:8790` 의 다른 로컬 앱)가 `<img>` 로 조회를 일으킬 수는 있습니다.
  `cross-site` 하나만 막은 것은 지시문 범위 그대로이고, 로컬 전용이라 피해도 작습니다. 더 조이려면 `not in ("", "same-origin", "none")` 이면 403 으로 할 수 있습니다.
- `X-Recorded-At` 은 과거 하한이 없습니다. `0001-01-01T00:00:00+00:00` 를 받아 `by_date` 에 `0001-01-01` 이 생깁니다. 목록 맨 아래로 가므로 R38-N4 가 문제 삼은 '맨 위에 계속 남음' 과는 다릅니다.

## 대상별 닫힘 판정

| 번호 | 판정 | 근거 |
| ---- | ---- | ---- |
| R38-N1 (상) HEAD 가 지움 | **닫힘** | 실제 서버에서 HEAD(Origin 있음·없음)를 보낸 뒤에도 녹음이 남음. PUT·PATCH·OPTIONS·WebDAV·TRACE·소문자 메서드 어느 것으로도 못 지움. 변이로 새 검사 2개가 FAIL |
| R38-N2 kind 비문자열 | 닫힘 | 실제 서버에서 400 JSON, 변이로 확인 |
| R38-N3 LLM 명령 설정 오류 → health 끊김 | 닫힘 | 200 + `llm:false` + `llm_error`. 문서 누락은 R39-N4 |
| R38-N4 X-Recorded-At·from/to | **닫힘(끝 남음)** | 9999년·형식 오류·시간대 없음 → 201 + 서버 시각. **업로드를 거절하지 않으므로 대기열이 영구 실패로 가지 않음.** 2026-13-40 → 400. 남은 끝: R39-N2(범위 끝 Overflow), R39-N1(from/to 회귀) |
| R38-N5 프롬프트 정렬 | 닫힘 | `store._sort_key` 사용, 변이로 test_ask 2 FAIL |
| R38-N6 retry 경합 | 닫힘 | `ValueError` → 404 JSON, 변이로 확인 |
| R37-N1 words.js 낡음 | 닫힘 | `test_rebuild_is_byte_identical` 이 OK(144 안에 있음). TREND 21개, ALLOWED +6 |
| R37-N2 6칸 아닌 트렌드 정답 | 닫힘(서버·화면 둘 다) | 서버: `/api/trend` 가 `사과`·`닭` 을 뺌(실제 HTTP). 화면: `mergeTrend` 가 거르고 browser_trend 시나리오가 지킴(변이로 83/85). `safeStartDaily` 가 끝 방어막 |
| R37-N3 serve.py 예외 → 끊김 | 닫힘 | `_api` 가 500 JSON(예외 이름만). 캐시 축출은 잠금 + `pop(k, None)` |
| R37-N4 0줄 last_run·출력 | 닫힘(출력) | 출력은 사실대로 바뀜(변이 2개 잡힘). last_run 갱신은 관리자 결정으로 그대로 둠 |
| R37-N5 Origin 없는 GET | 닫힘 | `cross-site` 면 403. 정상 같은 출처(`same-origin`·`none`)·curl·모니터 프록시 경로는 통과. 위 참고 참조 |
| R37-N6 verify opener | 닫힘 | 비위키 출처도 opener 를 넘김, 변이로 확인 |
| R37-N7 sourceNote 안내 | 닫힘 | 사용자 키가 있는 브라우저 직접 출처와 위키는 안내 없음. 서버 없음 → `(키 또는 serve.py 필요)`. browser_dict 75/75 |
| R37-N8 `네` | 닫힘 | 변이로 test_dict.mjs ✖ |
| R37-N9 복잡도 정리 | 닫힘, 동작 그대로 | (a) 키 있음·없음 경계에서만 다시 그림 (b) `game.rows` 한 번만 복사 (c) `dayKey` 하나로 합침. 기본 인자 `new Date()` 라 `todayKey()` 와 결과가 같음 (d) `hasStoredSettings` 제거. `loadSettings` 가 이미 `systemPrefersDark()` 를 기본값으로 주고 있었으므로(이 줄은 diff 밖) 결과가 같음. game 121·modes 100(시스템 테마 포함) 그대로 |

회귀 확인: 업로드(503·507·408·400 경로는 test_serve 52개 OK), 토큰, 출처, DNS 되돌림, browser_voxlog 26/26, 자모맞히기 날마다 판·연습·사전 조회(browser 4벌 381/381) - 이상 없음. 회귀는 R39-N1 하나입니다.

## 다음 담당자가 알 것
- R39-N1·N2 는 `projects/VoxLog/serve.py` 한 파일에서 몇 줄이면 고칩니다(검사도 함께). N3·N4 는 문서만 고치면 됩니다.
- T-375 보고에 따르면 trend.txt 의 2026-11-29~12-05 일곱 줄은 커밋 0598dfb 에서 pick 경로를 거치지 않고(last_run 그대로) 들어왔습니다. 낱말은 모두 6칸이라 동작에는 문제가 없지만, 출처는 태석님에게 확인할 거리입니다.
- `voxlog/ask.py` 가 `store._sort_key`(비공개 이름)를 가져다 씁니다. store 의 정렬 규칙을 바꾸면 프롬프트 순서도 함께 바뀝니다.
- 이번에 쓴 파일은 이 보고서 하나입니다. 남은 /tmp 실험 데이터(`/tmp/r39s1-vdata`, `/tmp/r39s1-probe`)는 저장소 밖이고 정리는 자유입니다.
