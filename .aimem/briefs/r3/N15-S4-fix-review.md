# 관리자 수정분 적대적 재검수 (**읽기 전용. 저장소 파일을 고치지 마라.**)

네가 run `20261109-173336-S4` 에서 찾은 `server.py` 결함 5건을 **관리자가 고쳤다고 주장한다.**
`8.0-1` 대로 **만든 사람이 자기 채점을 하지 않는다.** 주장을 깨 보라. 고친 곳은 이렇다.

| 네가 찾은 것 | 관리자 주장 |
| --- | --- |
| 1. 노드 모양이 틀린 그래프가 `/api/state`+`/api/health` 를 죽임 | `collect_graphs()` 의 노드 루프를 파일 단위 try 로 감쌈 |
| 2. 302 리다이렉트가 `Bearer` 키를 타 호스트로 | `_no_redirect_opener()` - `redirect_request` 가 `None` |
| 3. `timeout=3.0` 은 소켓 하나 제한 (트리클에 55초 블로킹) | 갱신을 **배경 스레드**로, 요청 경로는 캐시만 읽음 |
| 4. 캐시 stampede (동시 5 = 외부 5) | `refreshing_since` 플래그 + stale 반환 |
| 5. 실패 분기 키 9개 누락 / `KISTI_FIELDS` 타입 무검사 | `_empty_state()` 단일화 + `KISTI_FIELD_TYPES` |

추가로 새로 생긴 것도 봐라: `GET /api/runs/<id>` 라우팅, `RUN_ID_RE`, `create_request` 의
**빈 요청자 400 거절**, `tools/fleet_graph.py` 의 `_busy_slots()`·원자적 `_save()`·`_ready()` dep 검사.

## 깨 볼 것 (각 항목: 재현 + 실제 출력 + 판정)
1. **1번이 정말 닫혔나.** 노드가 문자열·정수·`None`, `deps` 가 문자열, `attempts` 가 dict,
   `nodes` 가 dict, 상태가 `None`, 파일이 빈 바이트·BOM·거대(10MB) 인 경우를 **임시 root 로** 만들어
   `collect_state()`/`collect_graphs()` 가 **예외 없이** `errors` 로 낮추는지 보라. `/api/health` 도 같이.
2. **2번.** 로컬 소켓으로 302·307·https→http 강등을 만들어 **`Authorization` 헤더가 두 번째 호스트에
   도달하는지** 확인하라. **가짜 키로만 시험하라.** 301/303 과 `Location` 이 상대경로인 경우도.
3. **3번.** 헤더·바디를 1바이트/초로 흘리는 서버를 만들고 `/api/state` 를 **동시에 10번** 쳐라.
   요청 경로가 **막히지 않는지**(각 응답 시간) 와 스레드가 쌓이는지(`threading.active_count()`) 를 재라.
   배경 스레드가 영영 안 끝나면 `KISTI_REFRESH_STUCK_SEC`(120) 뒤에 새 갱신이 뜨는지도 보라.
4. **4번.** 콜드 동시 10 / 만료 직후 동시 10 / 순차 10 각각 **외부 호출 횟수**를 세라.
   `_fetch_kisti` 를 가짜로 바꿔 세면 된다. 캐시가 **영원히 stale 로 굳는** 경로가 있는지 보라.
5. **5번.** `reader.collect` 를 (a) 예외 (b) 비-dict (c) 키가 모자란 dict 로 바꿔
   세 경우의 최상위 키가 정상과 **정확히** 같은지 보라. `KISTI_FIELD_TYPES` 에 `busy=1`(int),
   `queued=True`(bool), `phase=None`, 아주 큰 int, NaN 을 넣어 무엇이 통과하고 무엇이 `dropped` 인지 표로.
6. **`/api/runs/<id>`.** 경로 탈출(`%2e%2e%2f`, 이중 인코딩, 널바이트, 유니코드 정규화),
   아주 긴 id, 형식은 맞지만 없는 id, `HEAD` 요청, `?a=b` 쿼리. **500 이 한 번이라도 나오면 결함이다.**
   응답에 저장소 **절대경로가 새는지**도 보라(`paths` 필드).
7. **빈 요청자 400.** 공백만, 탭, 제로폭 공백, 60자 초과, `null`, 숫자, 리스트를 보내 보라.
   기존 테스트(`tests/test_aimem_monitor.py`)가 이 변경으로 깨지지 않는지도 확인하라.
8. **`_busy_slots()`.** `.aimem/runs` 에 깨진 메타·`slot` 없는 메타·죽은 pid 가 있을 때 예외가 나는가?
   **지금 실제로 S1·S2·S3 작업자가 돌고 있다** - 읽기만 하고 아무것도 죽이지 마라.
9. **원자적 `_save()`.** tmp 파일이 남는 경로, 디스크 꽉 참 흉내, `GRAPHS` 가 없는 경우.
   `.json.tmp` 가 `glob("*.json")` 에 안 걸리는지 확인하라(서버가 그래프를 그걸로 읽으면 안 된다).

## 금지·주의
- **실제 `.aimem/graph/R-002.json` 과 `.aimem/runs/` 를 고치지 마라.** 임시 root 로 복제해 쓰라
- 바깥 네트워크로 나가지 마라. 전부 `127.0.0.1` 로컬 소켓과 monkeypatch 로
- `pkill`·`kill` 류 금지. 지금 작업자 셋이 돌고 있다
- 보고는 **표 하나(항목/판정/근거 한 줄)** + **결함 심각도 순(파일·행)**. 고치지는 마라.
  **"OK" 를 쓸 때는 무엇을 쳐서 OK 였는지 반드시 적어라.**
