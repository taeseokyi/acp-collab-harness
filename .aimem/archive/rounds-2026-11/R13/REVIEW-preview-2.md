결함 2·4·5·6 은 고쳐졌다. 결함 3 은 절반만 고쳐졌다(init 정리가 키 이름을 틀림, 새 결함 A). 결함 1 은 계획대로 손대지 않았다. 기존 검사는 여전히 `app.js` 변이를 하나도 잡지 못한다(0/10, 이번에 더한 6개도 0/6).

# R13 T-174 재검수 - 미리보기 보관함 결함 수정 확인 (G-030)

검수자: S1 (REV 156). 코드는 고치지 않았다.

방법:
- `/tmp` 에 Node 하네스를 다시 만들었다. `app.js` 는 손으로 옮기지 않았다. `const ALLOWED_MSG_KEYS` 부터 `function renderProjects` 앞까지,
  그리고 `function runPanelCleanups` 를 **원문 그대로 잘라** 가짜 `document`·`localStorage`·`window`·`Date`·`setTimeout` 위에서 돌렸다.
  `storage.js` 는 가짜 `parent` 를 둔 채 그대로 `import` 했다. 둘을 이어 붙여 자식 → 모니터 → 칸까지 끝에서 끝까지 쟀다.
  시나리오는 24개다. 수정본 기준선에서 22개가 통과했고 2개가 실패했다(D3b·D3c, 아래 새 결함 A).
- 저장소를 `/tmp` 에 복사했다(`.aimem/tls`·`.git` 은 처음부터 복사하지 않음). 변이 19개를 하나씩 넣고
  `node --test projects/웹워들/tests/*.mjs`(38개)와 하네스를 돌렸다. 끝난 뒤 `/tmp` 폴더 둘을 지웠다.
- 실제 저장소에서 `node --test projects/웹워들/tests/*.mjs` → 38/38 통과다(앞 검수 때 빨갛던 `지우기는 value 가 null 이다` 포함).
- **브라우저 실측은 이번에도 없다.**

## 결함별 표

| 번호 | 앞 검수의 결함 | 고쳐졌나 | 어떻게 확인했나 |
|---|---|---|---|
| 1 | 브라우저 검사가 `/app/웹워들/` 을 최상위로 열어 보관함 길을 한 줄도 실행하지 않는다 | 아니오 (계획대로 다음 라운드로 넘김) | `tests/browser_monitor_app.py:61` 은 여전히 `page.goto(base + "/app/웹워들/")` 이다. 파일 안에 `openProjectApp`·`store.v1` 은 없다. 다시 파헤치지 않았다 |
| 2 | 스냅숏이 안 와도 부모 모드가 켜져, 빈 메모리 값의 `put` 이 칸을 덮는다 | 예 | `storage.js:116` `if (!receivedSnapshot) return;`. 하네스 D2a: 응답 없는 부모로 `init()` → `recordResult`·`saveSettings` 를 해도 나간 메시지는 `["ready"]` 뿐이고 `put` 은 0개다. 메모리 모드로 계속 돈다. **(c) 스냅숏이 온 경우** D2c: `played:50` 스냅숏 뒤 `recordResult` → `put stats {"played":51,…}` 가 나간다 |
| 3 | 지우기 규약 불일치(`op:'remove'` ↔ `put`+`null`). 지난 `daily.*` 가 칸에 쌓여 61일째부터 새 판 저장이 막힌다 | **부분** | 규약은 고쳐졌다. `storage.js:71` `sendToParent('put', key, null)` 이고 단위 시험도 초록이다. 하네스 D3a 에서 `clearDaily` 가 칸에서 실제로 지워진다. **그러나 init 의 지난 `daily.*` 정리가 여전히 칸에 반영되지 않는다.** 하네스 D3b·D3c 가 실패하고, 앞 검수가 적은 결과(64키 칸에서 오늘 `daily` put 이 버려짐, size 64)가 그대로 재현된다. 원인은 새 결함 A 다 |
| 4 | 허용 필드 밖의 키가 붙은 메시지를 버리지 않는다 | 예 | `app.js:2851-2854` `ALLOWED_MSG_KEYS`, `:2961-2962`. 하네스 D4: `part` 를 덧붙인 `put` 과 `x` 를 덧붙인 `ready` 는 버려진다. **(b) 정상 메시지:** `{aimem,op,key,value}` put, `value:null` 지우기, `{aimem,op}` ready 는 모두 받는다(스냅숏 1번). `op:'__proto__'`·`'constructor'`·`'snapshot'` 은 배열이 아니어서 버려진다. 끝에서 끝까지 이은 D2c·D3a 에서 `storage.js` 의 실제 메시지가 걸러지지 않음도 확인했다 |
| 5 | 이미 상한을 넘은 칸이 지우기까지 막혀 굳는다 | 예 | `app.js:2915` 는 넘쳤더라도 키 수나 길이가 줄어드는 쪽이면 허용한다. 하네스 D5: 70키 칸에서 `put(k0,null)` 이 반영된다(size 69). 값 줄이기도 허용된다. **(a) 상한이 물러졌나 → 아니다.** 넘친 칸에서 새 키 추가·값 늘리기는 막힌다. 빈 칸에서는 65번째 키가 막히고, 64키에서 기존 키 갱신은 된다. `"`×8,192 를 10번 보내면 3개째에서 멈춘다(49,177자). 그 뒤 넘기는 새 키도 막힌다. 길이로 넘친 칸(9×8,192)에서 값을 줄였다가 다시 키우는 것도 막힌다(65,610자에서 멈춤). 한 번의 put 은 키 수를 늘리면서 길이를 줄일 수 없으므로, 두 차원을 엇갈려 빠져나갈 길은 없다(코드 읽기). 덤으로 `loadPart` 가 잘못된 키·값(숫자 값, `__bad`, 70자 키)을 거른다 |
| 6 | 정리 훅을 건너뛰는 길: (i) 상세 셋이 `runPanelCleanups` 를 안 부름 (ii) `pagehide` 없음 | 예 (코드 읽기 + 하네스 일부) | (i) `openRequestDetail`(`app.js:817`), `openDetail`(`:976`), `openManagerDetail`(`:1555`) 모두 첫 줄이 `runPanelCleanups()` 다. (ii) `:364` `window.addEventListener('pagehide', runPanelCleanups)`. 하네스 D6: 정리 전에는 칸에 아무것도 쓰이지 않았고(250ms 묶음), `runPanelCleanups` 가 밀린 쓰기를 내보낸 뒤 리스너는 0개다. **브라우저에서 `pagehide` 가 실제로 쓰기를 살리는지는 재지 않았다** |

## 새로 생긴 결함

| 번호 | 심각도 | 파일:줄 | 무엇이 잘못됐는가 | 어떻게 재현했는가 | 고치는 방향 |
|---|---|---|---|---|---|
| A | 중간 | `projects/웹워들/web/js/storage.js:123` | init 의 지난 날 정리가 `remove(day)` 를 부른다. `day` 는 `daily.` 를 떼어 낸 `2025-01-01` 이라, 지우는 대상은 `webwordle.2025-01-01`(없는 키)이고 부모에는 `put key:"2025-01-01" value:null` 이 나간다. 진짜 `daily.2025-01-01` 은 자식 메모리와 모니터 칸에 그대로 남는다. `ui.js` 는 `clearDaily` 를 부르지 않으므로 **이 루프가 유일한 정리 길**이다. 결국 결함 3 의 결과(플레이한 날마다 키 하나씩 쌓이고, 61일째부터 새 날의 `daily.*` put 이 64키 상한에 걸려 조용히 버려짐)가 그대로 남는다 | 자식만 따로: 스냅숏 `{"daily.2025-01-01":…}` → 나간 메시지 `[{"op":"put","key":"2025-01-01","value":null}]`, `loadDaily('2025-01-01')` 은 여전히 `{"g":1}`. 끝에서 끝까지: D3b 는 5일치 칸이 정리 뒤에도 5개 그대로이고, D3c 는 64키 칸에서 오늘 `daily` 가 반영되지 않는다(size 64) | `remove('daily.' + day)` 로 바꾼다. 단위 시험 "init 은 지난 daily 를 `put key:'daily.<날짜>' value:null` 로 보낸다" 를 더한다. 지금은 이 줄을 고쳐도(변이 N3) 어떤 단위 시험도 반응하지 않는다. 틀린 동작도 맞는 동작도 고정되어 있지 않다 |
| B | 낮음 (코드 읽기만) | `tools/aimem_monitor/static/app.js:364` | `pagehide` 는 bfcache 로 들어갈 때도 불린다. 그때 `runPanelCleanups` 가 iframe 을 지우고 리스너를 뗀다. 뒤로 가기로 페이지가 되살아나면(`pageshow` persisted) 앱 패널 오버레이는 열린 채 iframe 없이 빈 칸으로 보인다. 데이터 손실은 없다(정리 때 저장함) | 코드 읽기. 브라우저 실측 없음 | `pageshow` 에서 `ev.persisted` 이고 앱 패널이 열려 있으면 `closeDetail()`. 또는 쓰기만 `flushPut` 하고 iframe 은 두는 별도 훅을 쓴다 |

참고(결함 아님): A 를 고친 뒤에도 이미 60개 남짓 쌓인 칸을 한 번에 정리하면, `put` 20개/초 제한 때문에 첫 1초에는 20개만 지워진다(변이 N3 에서 D3c 가 여전히 실패한 이유).
정상이면 세션마다 지난 키가 몇 개뿐이라 문제가 되지 않는다. 이 기능은 아직 배포되지 않아 이미 쌓인 칸도 없을 것이다.

## 변이 시험 표

기존 검사 = `node --test projects/웹워들/tests/*.mjs` (38개: `test_game.mjs`·`test_storage.mjs`·`smoke_integration.mjs`). 수정본 기준선은 38/38 초록이다.
Python `tests/` 에서 `store.v1`·`ALLOWED_MSG_KEYS`·`putIfFits`·`pagehide`·`runPanelCleanups` 를 언급하는 검사는 없다(grep). 브라우저 검사는 돌리지 않았다(결함 1 때문에 이 길을 실행하지 않음).

| 변이 | 무엇을 망가뜨렸나 | 잡혔나 | 잡은 검사 |
|---|---|---|---|
| M1 | `app.js` `src !== fr.contentWindow` 삭제 | 아니오 | - (이번 하네스에도 출처 시나리오는 넣지 않았다) |
| M2 | `app.js` `!src`·`!fr.isConnected` 삭제 | 아니오 | - (상동) |
| M3 | `app.js` 길이 상한 65536 → 655360 | 아니오 | - (하네스 D5 셋이 잡음) |
| M4 | `app.js` `put` 20/초 → 2000/초 | 아니오 | - |
| M5 | `app.js` `ready` 빈도 제한 삭제 | 아니오 | - |
| M6 | `app.js` 키 정규식 삭제 | 아니오 | - (하네스 loadPart 시나리오가 잡음) |
| M7 | `app.js` `ev.origin !== 'null'` 삭제 | 아니오 | - |
| M8 | `app.js` 스냅숏에 모니터 `localStorage` 전체 섞기 | 아니오 | - (하네스 loadPart 시나리오가 우연히 잡음) |
| M9 | `app.js` 정리에서 `removeEventListener` 삭제 | 아니오 | - (하네스 D6 이 잡음) |
| M10 | `app.js` 상한 초과 시 되돌리기 삭제 | 아니오 | - (하네스 D5 여섯이 잡음) |
| N1 | `storage.js` `if (!receivedSnapshot) return;` 삭제 (결함 2 되돌림) | **아니오** | - (하네스 D2a 가 잡음). 앞 검수가 권한 단위 시험 "스냅숏 없으면 put 안 보냄" 이 더해지지 않았다. "500ms 안에 포기" 시험은 `put` 을 보지 않는다 |
| N2 | `storage.js` 지우기를 `op:'remove'` 로 되돌림 (결함 3 되돌림) | **예** | `test_storage.mjs` "지우기는 value 가 null 이다" (하네스 D3a 도) |
| N3 | `storage.js:123` 을 `remove('daily.' + day)` 로 (새 결함 A 를 고치는 쪽) | 해당 없음 | 기존 검사 38개가 그대로 초록이다. 이 줄은 어떤 단위 시험도 고정하지 않는다. 하네스 D3b 는 초록으로 바뀐다 |
| N4 | `app.js` 허용 키 검사 줄 삭제 (결함 4 되돌림) | 아니오 | - (하네스 D4 둘이 잡음) |
| N5 | `app.js` 줄어드는 쪽 허용 조건 삭제 (결함 5 되돌림) | 아니오 | - (하네스 D5 셋이 잡음) |
| N6 | `app.js` 키 상한 64 → 6400 (상한 무르게) | 아니오 | - (하네스 D5 셋이 잡음) |
| N7 | `app.js` `loadPart` 의 키·값 거르기 삭제 | 아니오 | - (하네스가 잡음) |
| N8 | `app.js` `pagehide` 등록 삭제 (결함 6-ii 되돌림) | 아니오 | - (이번 하네스도 이 줄을 실행하지 않는다. 표에 보이는 "변화"는 잘라 내는 경계가 밀린 탓이다) |
| N9 | `app.js` `openRequestDetail` 첫 줄 `runPanelCleanups()` 삭제 (결함 6-i 되돌림) | 아니오 | - |

**기존 검사: 망가뜨리는 변이 18개(N3 제외) 가운데 1개(N2)만 잡았다. 앞 검수와 같은 `app.js` 변이 M1-M10 은 이번에도 0/10 이다. 숫자는 달라지지 않았다.**
이번 수정을 되돌리는 `app.js` 변이 N4-N9 도 0/6 이다. `storage.js` 쪽은 결함 3 의 규약만 단위 시험이 지키고, 결함 2 수정(N1)과 init 정리(A/N3)는 지키지 않는다.
모니터 쪽 보관함 코드를 지키는 자동 검사는 여전히 없다. 결함 1 이 남아 있는 한 그렇다.

## 목표 "모니터 안에서 실행해도 통계·설정이 남는다" 를 지금 체크해도 되는가

**아니오.** (1) 보관함 길을 브라우저에서 잰 증거가 아직 없다(결함 1). (2) init 정리가 키 이름을 틀려(새 결함 A) 지난 판이 칸에 쌓인다.
그래서 플레이한 날이 61일쯤 되면 진행 중인 판 저장이 다시 조용히 멈춘다.
