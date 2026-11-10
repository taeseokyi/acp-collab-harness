# 식별자 체계 패치 메모 (클로드 코드 준비, 2026-11-09 18:20)

관리자 소유 파일이라 관리자가 반영한다. 앵커가 다르면 의도만 살려 적용.

## tools/fleet_graph.py
1. `_spawn_node(g, n, attempt_no)` 의 Namespace 에 `task_id=<노드 id가 T-0xx 면 그 값, 아니면 None>`, `attempt=attempt_no` 를 추가한다. 라벨은 `f"{n.get('title','')} ({g['id']})"` 로 바꿔 라운드/그래프 접두사(`R-002/N3`)를 뺀다. fleet.py 가 실행 id 를 `T-050-S1-a2-HHMMSS` 로 만든다(이미 반영).
2. `cmd_new`: 그래프 id 가 `G-\d{3}` 가 아니면 경고, 노드 id 가 `T-\d+[A-Z]?` 가 아니면 경고(차단은 안 함 - 이력 호환).
3. `import re` 가 없으면 추가.

## tools/aimem_monitor/server.py
- `POST /api/requests` 의 id 생성: `rid = f"Q-{now.strftime('%y%m%d')}-{secrets.token_hex(2)}"` (파일명도 같은 접두사). 옛 `20261109-HHMMSS-xxxx` 파일은 그대로 읽힌다.
- 실행 표 API 에 run id 를 쪼갠 `task`, `slot`, `attempt` 필드를 함께 내보내면 UI 가 열로 보여 줄 수 있다(run 메타 json 에 이미 `task`/`attempt` 가 있음).

## AIMEM.md
- `8.0-5 용어와 식별자` 절(REV 126 부터 `8.0-3-1`)(표 5행: 요청 Q- / 태스크 T- / 그래프 G- / 실행 <T>-<S#>-a<n>-<HHMMSS> / 라운드 R<n> 기록 전용, 노드 id = 태스크 id, ADHOC 규칙, 옛 식별자는 이력) 을 `8.0-4` 앞에 넣고 REV 를 올린다. 4절은 13건 초과라 롤오버 필요.
