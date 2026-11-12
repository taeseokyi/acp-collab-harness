## 역할 - 적대적 검수 (읽기 전용)

너는 **검수자**다. **파일을 하나도 고치지 마라.** 고칠 것은 보고에 적는다.

**왜 너인가.** 아래 코드는 **관리자가 직접 썼고 관리자가 혼자 검증했다.** `AIMEM.md` `8.0-1`
("만든 슬롯이 아닌 슬롯이 검수한다. 자기 채점은 자기 사각지대를 영원히 못 본다")이 관리자에게도
적용되는데 지금까지 적용된 적이 없다. 네가 그 자리다. **봐주지 마라.**

## 검수 대상

1. `/home/tsyi/work/ai-fleet/tools/aimem_monitor/server.py` - 이번 라운드에 추가된
   `_fetch_kisti()` / `kisti_status()` / `collect_graphs()` 와 `collect_state()` 의 변경
2. `/home/tsyi/work/ai-fleet/tools/aimem_monitor/__init__.py` - `SERVER_KEYS`, `KISTI_*`,
   `GRAPH_DIR` 상수
3. 참고(고치지 말고 읽기만): `tools/fleet_graph.py` 의 `progress()` - `collect_graphs()` 가 부른다

서버는 `127.0.0.1:18799` 에 떠 있다.

## 설계 의도 (이것과 어긋나면 결함이다)

- `server.py` 는 **합류점**이고 데이터를 가공하지 않는다. `reader.collect()` 결과를 그대로
  내보내고 거기에 `kisti` / `graphs` 두 키만 **덧붙인다**
- **쓰기는 `.aimem/requests/<id>.json` 생성 하나뿐이다.** 그 외 모든 경로는 읽기 전용이어야 한다
- **KISTI API 키(`KISTI_API_KEY` 환경변수)는 `/api/state` 응답에 절대 나오면 안 된다**
- 외부 서버가 느리거나 죽어도 **화면 전체가 멈추면 안 된다**
- 표준 라이브러리만 쓴다

## 반드시 따져 볼 것 (각각 판정과 근거를 적어라)

1. **키 유출 경로가 정말 없나.** `_fetch_kisti()` 가 예외 문자열을 `error` 에 싣는다.
   `urllib` 예외 메시지에 요청 헤더나 URL 이 섞여 나올 수 있는 경우가 있나?
   리다이렉트를 따라갈 때 `Authorization` 헤더가 다른 호스트로 전달되나? **실험으로 확인해라.**
2. **캐시가 스레드 안전한가.** 서버는 `ThreadingHTTPServer` 다. `kisti_status()` 는 락 밖에서
   `_fetch_kisti()` 를 부른다. 동시에 5개 요청이 오면 외부를 몇 번 때리나? 그게 의도대로인가?
   (의도: 10초에 한 번 근처. 매 요청마다면 결함이다.) **동시 호출을 실제로 돌려서 세어라.**
3. **타임아웃이 실제로 먹히나.** `KISTI_TIMEOUT_SEC = 3.0` 이다. 외부가 **연결은 되는데 응답을
   안 주는** 경우(블랙홀)에도 3초에 끊기나? `urlopen(timeout=)` 이 커버하는 범위는 어디까지인가?
   `python3 -c` 로 로컬에 느린 소켓 서버를 띄워 재현해라.
4. **`collect_graphs()` 가 읽기 전용인가.** `fleet_graph.progress()` 를 부르는데,
   그 함수가 파일을 쓰거나 프로세스를 띄우지 않는다고 확신할 수 있나? **소스를 읽어 확인해라.**
   (`fleet_graph.step()`/`_spawn_node()` 는 쓰지만 `progress()` 는? `harness_durations()` 는?)
5. **`sys.path` 오염.** `collect_graphs()` 가 `tools` 디렉터리를 `sys.path` 에 넣는다.
   `/api/state` 는 5초마다 불린다. 무한히 늘어나나? 늘어나지 않게 막혀 있나? **세어서 확인해라.**
6. **`errors` 가 매 요청 커지나.** `collect_graphs(root, errors)` 가 `errors` 에 append 한다.
   깨진 그래프 파일이 하나 있으면 `/api/state` 를 100번 부를 때 `errors` 가 100줄이 되나,
   매번 1줄이 되나? **실제로 여러 번 불러서 확인해라.**
7. **실패 경로의 스키마가 안정적인가.** `collect_state()` 의 `reader` 실패 분기와 정상 분기가
   **같은 최상위 키 집합**을 내나? 프런트가 `state.kisti` / `state.graphs` 를 무조건 읽어도
   안전한가? 둘을 비교해 키 차이를 목록으로 적어라.
8. **`_fetch_kisti` 가 거대한 응답을 받으면.** `r.read(64*1024)` 로 끊는데, 그보다 큰 JSON 이
   오면 잘린 바이트를 파싱해 `ValueError` 가 난다. 그게 `error` 로 떨어지나, 500 이 되나?
9. **`KISTI_FIELDS` 통과 목록.** 외부가 응답에 새 필드를 넣거나 기존 필드 타입을 바꾸면
   어떻게 되나? 프런트가 깨지나?

## 검증 명령 (맨 앞이 `cd` 또는 `python3` 여야 허용된다)

```
cd /home/tsyi/work/ai-fleet && curl -s http://127.0.0.1:18799/api/state | python3 -c "import json,sys;s=json.load(sys.stdin);print(sorted(s.keys()));print(s['errors'])"
cd /home/tsyi/work/ai-fleet/tools && python3 -c "import aimem_monitor.server as sv; print(sv.KISTI_CACHE_SEC, sv.KISTI_TIMEOUT_SEC)"
```

**키 유출 검사는 값을 출력하지 말고** `있음/없음` 만 보고해라.

## 보고 형식

첫 줄 `DONE` 또는 `PARTIAL`. 이어서 **결함을 심각한 순서로** 번호 매겨:
`파일:줄 / 무엇이 잘못됐나 / 어떤 입력·상황에서 드러나나 / 제안`.
그 다음 위 9개 항목에 대한 `항목 / 판정(OK·결함·판정불가) / 근거(돌린 명령 또는 읽은 줄)` 표.
**결함이 없으면 "없음" 이라고 분명히 적어라.** 추측을 사실처럼 쓰지 마라 - 돌려 보지 않았으면
`판정불가` 라고 적어라.

**파일을 고치지 마라. 커밋하지 마라. 아무것도 설치하지 마라.**
