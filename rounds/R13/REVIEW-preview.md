결함 6건 (보관함 길에 새 권한 상승 경로는 없음 - 결함은 기능·검증 쪽)

# R13 T-165 적대적 검수 - 미리보기 보관함 (postMessage 길, G-029)

검수자: S1 (REV 156). 코드는 고치지 않았다.

방법:
- `app.js` 2865-2960행(보관함 코드)을 **손으로 옮기지 않고 원문을 잘라 내어** Node 에서 가짜
  `document`·`localStorage`·`window`·`Date` 로 돌리는 공격 하네스를 `/tmp` 에 만들어 19개 시나리오를 돌렸다
  (16 통과, 3 실패 - 아래 결함 3·4·5).
- `storage.js` 를 가짜 `parent` 로 돌려 스냅숏이 안 올 때의 동작을 실측했다(결함 2).
- 저장소를 `/tmp` 에 복사(`.aimem/tls` 제외)해 변이 12개를 넣고 기존 검사(브라우저 8개 + `test_storage.mjs` 6개)와
  하네스를 각각 돌렸다. 끝난 뒤 `/tmp` 폴더는 지웠다.
- **실제 브라우저에서 이 길을 잰 증거는 이번에도 없다.** 하네스는 `ev.source`·`contentWindow` 의 브라우저 의미
  (버려진 창의 `source === null`, 중첩 iframe/팝업의 `source`)를 흉내 낼 뿐 실측하지 않는다.

## 결함 표

| 번호 | 심각도 | 파일:줄 | 무엇이 잘못됐는가 | 어떻게 재현했는가 | 고치는 방향 |
|---|---|---|---|---|---|
| 1 | 높음 | `tests/browser_monitor_app.py:62` | 브라우저 검사가 `/app/웹워들/` 을 **최상위로** 연다. 모니터 페이지도 `openProjectApp` 도 거치지 않으니 `parent === self` 이고 `init()` 은 바로 끝난다. 보관함 길은 한 줄도 실행되지 않는다. G-029 목표를 뒷받침할 증거가 0이다 | 변이 시험: `app.js` 변이 10개(M1-M10) 가운데 기존 브라우저 8개 검사가 잡은 것 **0개**. `test_storage.mjs` 는 `app.js` 를 로드하지 않아 역시 0개 | 설계 7절 "필요한 검사" 를 브라우저로 구현한다. 모니터 `/` 를 열고 `openProjectApp` 으로 미리보기를 띄운 뒤, 한 판 이기기 → 패널 다시 열기 → 통계 남음, 가짜 두 번째 프로젝트로 칸 분리, 중첩 iframe `put` 무시, 닫은 뒤 `fr` DOM 에 없음 |
| 2 | 중간 | `projects/웹워들/web/js/storage.js:114` | 스냅숏이 안 와도(500ms 시간 초과) `parentMode = true` 가 무조건 켜진다. 그 뒤 첫 `write` 가 **빈 메모리에서 계산한 값**을 `put` 으로 보내 모니터 칸의 기존 통계·설정을 덮는다. 설계 3.2 는 이 경우를 "메모리 모드" 라고 적었는데 구현은 부모 모드다. 스냅숏이 안 오는 경우: 패널 하나에서 iframe 을 세 번째 다시 불러오기, 첫 `ready` 뒤 1초 안에 다시 불러오기(`rate.ready` 거절), 모니터가 느릴 때 | 가짜 부모가 응답하지 않게 하고 `init()` 뒤 `recordResult(true,3,…)`: 실제로 `put stats {"played":1,"wins":1,…}` 가 나갔다. 모니터 하네스에서 같은 `put` 은 상한·빈도를 지나 칸에 반영된다 → 저장된 `played:50` 이 `1` 로 바뀐다 | 스냅숏을 받았을 때만 `parentMode = true`. 시간 초과면 메모리 모드로 두고 `put` 을 보내지 않는다. 단위 시험 "스냅숏 없으면 put 안 보냄" 을 더한다 |
| 3 | 중간 | `projects/웹워들/web/js/storage.js:71` ↔ `tools/aimem_monitor/static/app.js:2950` | 지우기 규약이 서로 다르다. `storage.js` 는 `op:'remove'` 를 보내고 모니터는 `op:'put'`+`value:null` 만 지우기로 받는다(설계 2절도 `put`+`null`). 그래서 `clearDaily`·`init` 의 지난 `daily.*` 정리가 **모니터 칸에 한 번도 반영되지 않는다.** 하루에 키 하나씩 쌓여 61일째(stats·settings·seenHelp + daily 61 = 64)부터는 **새 날의 `daily.*` put 이 키 상한에 걸려 조용히 버려진다** - 진행 중인 판이 남지 않는다. 단위 시험 `test_storage.mjs:94` 는 **지금 빨갛다**(5/6). "통과" 보고가 있었다면 사실과 다르다 | `node --test tests/test_storage.mjs` → `✖ 지우기는 value 가 null 이다`, 실제 `op:'remove'`. 하네스 S10(`op:'remove'` 를 모니터가 무시함), S13(daily 61개 칸에서 `remove` 뒤 새 daily `put` → 반영 안 됨, size 64) | `storage.js` 71행을 `sendToParent('put', key, null)` 로 바꾸고 17행 검사가 `null` 을 통과시키게 한다. 모니터 쪽은 고치지 않는다(설계가 정본) |
| 4 | 낮음 | `tools/aimem_monitor/static/app.js:2947` | 설계 2절 표 "위 필드 밖의 키가 있으면 버림" 이 구현되지 않았다. `{aimem,op,key,value,part,name}` 이 받아들여진다. 남는 필드를 아무도 읽지 않아 지금은 보안 영향이 없다. 다만 설계와 구현이 어긋나 있고, 나중에 필드를 더할 때 쓸 방어선이 없다 | 하네스 S11: 남는 필드 `part:'aimem-theme'` 을 붙인 `put` 이 반영됨(다른 칸·키에는 영향 없음 확인) | `Object.keys(m)` 가 `{aimem,op}`(ready) / `{aimem,op,key,value}`(put) 의 부분집합이 아니면 버린다 |
| 5 | 낮음 | `tools/aimem_monitor/static/app.js:2883-2885` | `loadPart` 가 저장된 칸의 키 수·직렬화 길이를 재지 않는다. 이미 상한을 넘은 칸(옛 버전이 썼거나 같은 출처의 다른 코드가 썼을 때)을 읽으면, 이후 `put` 은 **지우기까지** "넘침" 으로 되돌려져 칸이 굳는다 | 하네스 S12: 키 70개 칸에서 `put('k0', null)` → `k0` 남음, size 70 | 읽을 때도 64키·65,536자로 자르거나, 지우기(`null`)는 상한 검사를 건너뛴다 |
| 6 | 낮음 | `tools/aimem_monitor/static/app.js:815`, `:973`, `:1551` (+ `:2907`) | 정리 훅을 건너뛰는 길이 둘 있다. (i) `openRequestDetail`·`openDetail`·`openManagerDetail` 은 `openPanel` 을 거치지 않고 `detail-body` 를 비운다. 앱 패널이 열린 채 이 셋이 불리면 리스너가 다음 `closeDetail` 까지 남는다. 다만 `fr` 이 떨어져 나가 `isConnected` 검사로 모든 메시지가 버려지므로, 닫힌 쪽으로 실패한다. 오버레이가 모달이라 도달하기도 어렵다. (ii) 모니터 탭을 닫거나 새로 고치면 `pagehide` 처리가 없어 250ms 묶음에 남은 쓰기가 사라진다(예: 이긴 직후 탭을 닫으면 그 판 통계가 빠짐) | (i) 코드 읽기(세 함수 모두 `runPanelCleanups` 호출 없음), (ii) 코드 읽기. 둘 다 브라우저 실측은 없음 | (i) 세 함수 첫 줄에 `runPanelCleanups()`. (ii) `pagehide` 에서 `runPanelCleanups()` 또는 `flushPut` |

깨려 했으나 버틴 것(하네스 실측): 스냅숏에 다른 `localStorage` 키(`aimem-theme`, 다른 프로젝트 칸, 토큰 흉내 키) 섞임 없음(S1).
`__proto__`·`../x`·`''`·65자·`.x`·`%2e%2e` 키는 거절된다. `constructor`·`hasOwnProperty`·`toString` 은 평범한 키로 저장되고,
그 칸을 다시 읽어도 정상이다(S2, S2b, S2c). `"` 로만 된 8,192자 값 10번: 3개째에서 멈추고 저장은 49,177자다.
기존 키를 키우는 `put` 도 되돌려진다(S3, S3b). 키 64개 상한(S4). `put` 은 1초 창에 20개까지다. 잘못된 `put` 도 몫을
먹으므로 보수적이다(S5, S5b). `ready` 는 2회이고 두 번째는 1초 뒤부터다(S6). 남의 창·`origin != "null"`·`source null` 은
거절된다(S7). 닫은 뒤 핸들러를 직접 불러도(`null`, 떼어 낸 창) 쓰기가 없다(S7b). 닫으면 iframe 이 제거된다(S7c).
`setItem` 이 던져도 리스너 떼기와 iframe 제거가 끝까지 간다(S8). 밀린 쓰기는 닫을 때 나간다(S9).

## 변이 시험 표

기존 검사 = `tests/browser_monitor_app.py`(8) + `projects/웹워들/tests/test_storage.mjs`(6). 기준선에서 `test_storage.mjs` 는 이미 1개가 빨갛다(결함 3).
아래 "잡았나" 는 **기준선보다 새로 빨개진 검사**가 있는지다. 참고로 이번 검수 하네스의 결과도 함께 적는다.

| 변이 | 무엇을 망가뜨렸나 | 기존 검사가 잡았나 | 잡은 검사 이름 | (참고) 검수 하네스 |
|---|---|---|---|---|
| M1 | `app.js` `src !== fr.contentWindow` 삭제 | 아니오 | - | 잡음 (S7) |
| M2 | `app.js` `!src`·`!fr.isConnected` 삭제 | 아니오 | - | 잡음 (S7b) |
| M3 | `app.js` 직렬화 상한 65536 → 655360 | 아니오 | - | 잡음 (S3, S3b) |
| M4 | `app.js` `put` 20/초 → 2000/초 | 아니오 | - | 잡음 (S5) |
| M5 | `app.js` `ready` 2회 → 99회 | 아니오 | - | 잡음 (S6) |
| M6 | `app.js` 키 정규식 삭제(문자열이면 통과) | 아니오 | - | 잡음 (S2) |
| M7 | `app.js` `ev.origin !== 'null'` 검사 삭제 | 아니오 | - | 잡음 (S7) |
| M8 | `app.js` 스냅숏 `items` 를 모니터 `localStorage` 전체로 | 아니오 | - | 잡음 (S1) |
| M9 | `app.js` 정리에서 `removeEventListener` 삭제 | 아니오 | - | 잡음 (S7b, S8) |
| M10 | `app.js` 상한 초과 시 되돌리기 삭제 | 아니오 | - | 잡음 (S3, S4) |
| M11 | `storage.js` 스냅숏 `ev.source !== parent` 검사 삭제 | 예 | `test_storage.mjs` "딴 데서 온 메시지는 무시한다" | 해당 없음 |
| M12 | `storage.js` `put` 8,192자 상한 삭제 | 아니오 | - | 해당 없음 |

**기존 검사: 12개 중 1개(M11)만 잡았다. 모니터 쪽 변이(M1-M10)는 0/10이다.** 브라우저 8개는 12개 모두 그대로 8/8 통과였다.
모니터 쪽 보관함 코드는 지금 어떤 검사도 지키지 않는다. 결함 1이 이것이다.

## 설계 6절 - 지금 구현에서 지켜지는가

- **(a) 모니터 API 를 대신 불러 주지 않는다** - **지켜진다.** 핸들러(`app.js:2942-2953`)와 보조 함수가 닿는 것은
  `Map`, `JSON`, 고정 키의 `localStorage.getItem/setItem`, `src.postMessage` 뿐이다. `fetch`·XHR·`location`·`import()`·`eval`·`new Function` 으로 가는 길은 없다(코드 읽기).
  막아 주는 검사는 없다.
- **(b) 쿠키·다른 키가 스냅숏에 실리지 않는다** - **지켜진다**(하네스 S1). 다만 M8 처럼 퇴행해도 잡을 검사가 없다.
- **(c) 티켓·URL 을 보내지 않는다** - **지켜진다.** 메시지는 `{aimem,op,items}` 뿐이다. "다른 티켓을 못 얻는다" 는 전제는
  9절 첫 물음(불투명 출처가 시작한 이동에 `SameSite=Strict` 쿠키가 실리는가)에 기대는데, 이것은 여전히 실측되지 않았다. 이 길이 새로 연 것은 아니다.
- **(d) 칸 가르기** - **로직으로는 지켜진다**(S7, S7b, S2b). `ev.source === fr.contentWindow` 는 지역 변수 `fr` 과의
  객체 동일성 비교로 진짜 신원 검사이고, `!src`·`isConnected` 도 각각 따로 효과가 있다(M1, M2 를 하네스가 따로 잡음).
  **브라우저에서 실제 `source` 의미(버려진 창 → `null`, 중첩 iframe·팝업의 `source`)를 잰 증거는 없다.**

## 목표 G-029 "모니터 안에서 실행해도 통계·설정이 남는다" 를 체크해도 되는가

**아니오.** (1) 보관함 길을 브라우저에서 잰 증거가 없다(결함 1, T-164 두 번 실패). (2) 스냅숏을 놓치면 저장된 통계를 덮어쓴다(결함 2).
(3) 지우기가 반영되지 않아 약 두 달 뒤 판 저장이 멈춘다. 단위 시험도 지금 빨갛다(결함 3).
