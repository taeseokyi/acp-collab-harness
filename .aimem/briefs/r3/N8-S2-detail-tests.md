# T-051 상세 조회 계약 테스트 (요청 8d8d) - 새 파일 하나만 쓴다

쓰기는 **`tests/test_aimem_monitor_detail.py` 한 파일에만** 한다. 새로 만든다.
`tests/test_aimem_monitor.py` 는 **같은 시각 다른 작업자가 고치고 있다. 절대 건드리지 마라.**
네 파일 밖에서 나는 실패는 고치지 말고 보고에 그대로 적어라.

## 배경
웹 UI 에 "행을 클릭하면 상세가 열린다" 를 넣는다. 데이터는 아래 둘이다.
- `aimem_monitor.reader.run_detail(run_id, root=None) -> dict` (다른 작업자가 지금 만드는 중)
- `GET /api/runs/<run_id>` (관리자가 지금 만드는 중)

**둘 다 아직 없을 수 있다.** 그래서 테스트는 **계약 기준으로 먼저 쓴다.**
`run_detail` 이 아직 없으면 `self.skipTest("run_detail 미구현")` 으로 건너뛰게 하되,
**스킵 조건은 `hasattr(reader,'run_detail')` 하나뿐**이다. 다른 실패를 스킵으로 덮지 마라.

## 계약 (이 표가 정본이다)
`run_detail()` 반환 dict 의 최상위 키는 정확히 이 16개다:
`id, found, slot, harness, model, label, status, rc, elapsed_s, started, ended, brief, report, stderr_tail, paths, errors`

- `found` bool / `rc`,`elapsed_s` int|None / `started`,`ended` str|None /
  `slot`,`harness`,`model`,`label`,`status`,`brief`,`report`,`stderr_tail` str /
  `paths` dict (`dir,out,err,rc,brief` 키) / `errors` list[str]
- **예외를 던지면 실패다.** 잘못된 id (`"../../etc/passwd"`, `""`, `None`, `"x"*10000`,
  `"20261109-172618-S3/../.."`) 는 전부 `found=False` + `errors` 비어있지 않음 + 예외 없음.
- 정상 id 형식은 `^[0-9]{8}-[0-9]{6}-S[0-9]+(-[0-9]+)?$`.
- 없는 id 는 `found=False`, 키 16개는 그대로 있어야 한다.
- 실제 기록이 있는 id (`20261109-172618-S3`) 는 `found=True`, `rc==0`, `elapsed_s>0`,
  `report` 가 빈 문자열이 아니어야 한다. 저장소 실제 `.aimem/runs/` 를 읽는 이 테스트는
  기록이 없으면 스킵해도 된다 (`os.path.exists` 로 판단).
- **읽기 전용이어야 한다**: `run_detail` 호출 전후로 `.aimem/runs/` 의 파일 목록과
  mtime 이 바뀌지 않음을 확인하라.

`GET /api/runs/<id>` 서버 계약:
- 정상 id → 200, `Content-Type: application/json`, 본문은 위 16키 dict
- 없는 id → **404**, 본문 `{"error": "..."}`  (500 이면 실패)
- 잘못된 id (경로 탈출 등) → **400 또는 404**, 500 이면 실패
- 서버 테스트는 `aimem_monitor.server` 의 핸들러를 임시 포트(0번)로 띄워서 한다.
  `server` 에 `/api/runs/` 라우트가 없으면 그 테스트만 스킵한다.

## 추가로 덮을 것 (적대적 검수 S4 가 찾은 결함의 회귀 테스트)
`tools/aimem_monitor/server.py` 를 임시 root 로 호출해 확인한다. 아직 안 고쳐졌으면 **실패로 남겨라**
(스킵하지 마라 - 관리자가 고치는 중이고 이 테스트가 확인 수단이다).
1. `collect_graphs(root)` 에 모양이 틀린 그래프 JSON (`{"nodes": ["x"]}`, `{"nodes":[{"attempts":[None]}]}`)
   이 있어도 **예외를 던지지 않고** `errors` 한 줄로 낮춘다.
2. `collect_state(root)` 가 1번 상황에서도 정상 dict 를 돌려준다 (`/api/health` 가 죽지 않아야 한다).
3. `collect_state` 의 **실패 분기에서도 최상위 키가 정상 분기와 같다.**
   `reader.collect` 를 monkeypatch 로 (a) 예외 던지기 (b) dict 가 아닌 값 돌려주기 로 바꿔
   두 경우 모두 키 집합이 정상과 일치하는지 본다 (`kisti`, `graphs` 포함).
4. `KISTI_FIELDS` 타입 방어: `busy="yes"`, `queued={"a":1}`, `generated="9"` 같은 응답이 와도
   서버가 500 을 내지 않는다.

## 금지
- 네트워크를 치지 마라. KISTI 는 전부 monkeypatch 로 가짜 응답을 준다.
- `pytest` 는 이 환경에 없다. `unittest` 만 쓴다.
- 커밋·설치·삭제 금지.

## 검증 (출력을 보고에 붙여라)
```
python3 -m unittest tests.test_aimem_monitor_detail -v
python3 -m unittest discover -s tests 2>&1 | tail -20
```
실패가 남으면 **어느 것이 "아직 구현 안 됨" 이고 어느 것이 "진짜 결함" 인지 보고에 나눠 적어라.**
