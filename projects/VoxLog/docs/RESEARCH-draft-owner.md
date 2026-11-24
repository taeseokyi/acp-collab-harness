# VoxLog 초안 주인 탭 생존 판정 조사 (G-092)

조사 범위: 문서만. `projects/VoxLog/web/queue.js`, `web/app.js`, `web/sw.js`, `tests/browser_voxlog.py`는 읽기만 했고 코드는 고치지 않았다.

## 요약과 권고

바꿀 만하다. 표준 방식은 **Web Locks API의 같은 출처 배타 잠금**이다. 녹음 탭은 초안을 만들기 전부터 `voxlog-draft-<draftId>` 잠금을 쥐고, 저장·정리·폐기가 끝날 때 놓는다. 다른 탭은 `navigator.locks.request(name, {ifAvailable:true}, ...)`로 즉시 판정하고, 주인이 나중에 죽는 경우를 위해 같은 이름의 대기 요청을 건다. 이 대기 요청에는 `AbortSignal`을 달아 자기 탭이 `freeze`/`pagehide`에 들어갈 때 abort하고, `resume`/`pageshow`에서 다시 건다. 그러면 얼어붙은 대기 탭이 FIFO 대기 줄 전체를 막는 경로를 거의 없앤다.

배포 전환기(R43-N6)는 세대로 가른다. 새 코드가 만든 초안에는 `lock: true`(새 세대 표식)와 `aliveAt: Infinity`를 함께 저장한다. 구버전 탭의 회수 필터는 `now - aliveAt < 20000`이면 그 초안을 녹음 중으로 보고 건너뛰는데, `Infinity`는 이 식을 항상 참으로 만들어 새 초안을 구탭의 회수 대상에서 영영 빼놓는다. 20초 신선도 규칙은 표식이 없는 구세대 초안에만 적용하고, 새 세대 초안은 잠금만으로 판정한다. 그래서 새 코드끼리는 잠금을 얻는 즉시 회수되고, 새 코드는 5초 heartbeat와 BroadcastChannel을 두지 않는다. Web Locks가 없는 브라우저에서는 지금의 `aliveAt` lease를 열화 경로로 남기지 않는다. 초안 자체를 만들지 않고 '끊긴 녹음 되살리기'만 꺼 두며, 녹음과 올리기는 그대로 된다(녹음은 끝날 때 메모리의 조각으로 `enqueue`).

단, Web Locks는 “탭이 살아 있음”과 “탭이 얼었음(frozen)”을 구분하지 않는다. 얼어 있는 녹음 탭의 잠금은 계속 잡혀 있으므로 다른 탭이 초안을 가져가지 않는다. 대신 그 탭이 다시 살아나거나 브라우저가 실제로 버리기 전까지 회수가 늦어질 수 있다. 이 맞바꿈은 받아들여야 한다. 전환기에는 잠금(새 세대)과 `aliveAt` lease(구세대)가 세대 표식으로 갈려, 각자 맡은 초안만 판정한다. `AbortSignal` 대기 요청과 전환기 규칙은 규격·Page Lifecycle 문서와 배포 현실을 합친 추론이며, 실제 기기 검증 항목으로 남긴다.

## 1. 표준·권장 방식

| 방식 | 주인 생존 판정이 되는가 | 죽은 탭을 누가 언제 아는가 | 복잡도 | 근거 |
| --- | --- | --- | --- | --- |
| **Web Locks, 배타 잠금** | 된다. 잠금은 같은 출처의 탭·워커 사이에서 하나만 잡히며, `ifAvailable:true`는 즉시 잡히지 않으면 콜백에 `null`을 준다. | 브라우저 잠금 관리자가 문서 unloading/agent 종료 때 잠금을 풀고, 대기 중인 요청이 그때 잠금을 얻는다. 탭이 닫히거나 죽으면 heartbeat 만료를 기다리지 않는다. | 중간. 녹음 전체를 감싸는 long-lived request와 회수용 대기 request가 필요하다. | MDN Web Locks API, MDN LockManager.request, W3C Web Locks §2.4·§2.6·§4.2 |
| **BroadcastChannel만 쓰기** | 단독으로는 안 된다. “살아 있나?” 질문에 답이 없으면 죽은 것인지, 얼었는지, 탭이 백그라운드에서 지연됐는지 구분하지 못한다. | 닫힘/종료 이벤트가 없다. 상대 탭이 응답하지 않는 시점을 lease나 시간초과로 추정해야 한다. | 낮음~중간. 질문·응답·lease·재시도가 함께 필요하다. | MDN BroadcastChannel: 같은 출처 browsing context 사이 메시지, `close()`는 자기 채널만 닫음; close 알림 이벤트 없음 |
| **SharedWorker** | 중앙 조정자를 둘 수는 있지만, 페이지별 연결 종료를 신뢰할 수 있는 이벤트로 받는 방식은 아니다. `MessagePort`에는 close 이벤트가 없고, SharedWorker 수명은 열린 페이지의 참조에 묶인다. | 조정자가 연결 목록을 유지해도 페이지가 닫힌 시점을 즉시 통보받는 표준 이벤트가 없다. | 높음. 별도 worker·프로토콜·수명 관리가 필요하다. | MDN SharedWorker: 여러 browsing context가 같은 worker에 접근, 열린 페이지가 참조를 잡는 동안 유지; MDN MessagePort에는 close()만 있고 close 이벤트 없음 |
| **서비스 워커 `clients.matchAll`** | 초안별 주인 판정에는 부족하다. 현재 window client 목록을 볼 수 있지만, 어떤 초안을 누가 녹음 중인지는 별도 상태가 필요하다. | 서비스 워커가 이벤트 때만 깨어나고, client가 닫힌 순간을 초안별로 통보하지 않는다. 얼어 있는 client도 목록에 남을 수 있다. | 중간~높음. 서비스 워커 수명·client 상태·초안 상태를 함께 설계해야 한다. | MDN Clients.matchAll: 서비스 워커에서만, 현재 client 목록 반환; MDN Service Worker API: event-driven worker |
| **IndexedDB lease 그대로** | 추정만 된다. `aliveAt`이 최근이면 살아 있다고 보고, 오래되면 죽었다고 본다. 실제 탭 존재와 다를 수 있다. | lease 만료(현재 20초)나 BroadcastChannel 무응답(300ms) 뒤에 추정한다. 탭이 실제로 죽은 시점이 아니다. | 낮음. 다만 정지·프리즈·빠른 새로고침에서 오판한다. | 현재 `queue.js`의 `DRAFT_LEASE_MS`, `aliveAt`, `liveDraftIds(300)`; MDN IndexedDB는 저장 API일 뿐 탭 수명 API가 아님 |

`navigator.locks.query()`는 held/pending 잠금의 스냅샷과 `clientId`를 보여 주는 진단용이다. 스냅샷을 본 뒤 “잡혀 있지 않다”고 판정하고 곧바로 다른 탭이 잡는 사이에 상태가 바뀔 수 있으므로, 판정·회수는 `query()`가 아니라 `request(..., {ifAvailable:true})`로 원자적으로 해야 한다. MDN query와 W3C snapshot 절도 “어떤 시점의 스냅샷”이라고 말한다.

## 2. 지원 범위

MDN·BCD 기준이다. BCD가 “mirror”로 표시한 항목은 같은 계열의 숫자를 풀어 적었다. Edge만 크로미엄 엣지 첫 버전인 79로 추정했다.

| 브라우저 | Web Locks 지원 | 비고 |
| --- | --- | --- |
| Chrome | 69+ | BCD `api.LockManager` 기준 |
| Chrome Android | 69+ (Chrome 69 mirror) | BCD `chrome_android`는 mirror |
| Edge | 79+ (mirror에서 추정) | Chromium 기반 Edge 첫 버전이 79이므로 79+로 추정한다. BCD `edge`는 mirror |
| Firefox | 96+ | BCD 기준 |
| Firefox Android | 96+ (Firefox 96 mirror) | BCD `firefox_android`는 mirror |
| Safari | 15.4+ | BCD 기준 |
| Safari iOS | 15.4+ (Safari 15.4 mirror) | BCD `safari_ios`는 mirror. iPadOS도 별도 항목이 없어 같은 WebKit 기준으로 15.4+로 적었다 |
| Android WebView | 69+ (Chrome 69 mirror) | BCD `webview_android`는 mirror |
| iOS WebView | 15.4+ (Safari 15.4 mirror) | BCD `webview_ios`는 mirror |

MDN은 Web Locks를 **Secure context** 기능이라고 표시한다. 따라서 HTTPS가 원칙이고, `http://localhost`, `http://127.0.0.1` 같은 loopback은 secure context로 취급된다. MDN Secure contexts 문서는 문서가 HTTPS 또는 loopback에서 왔을 때 secure context라고 설명한다. VoxLog를 폰에서 실제로 쓰려면 HTTPS 또는 secure context가 보장되는 배포가 필요하다.

Web Locks는 `LockManager` IDL이 `[SecureContext, Exposed=(Window, Worker)]`이고 `WorkerNavigator`에도 `locks`가 있다. MDN Web Locks API는 “available in Web Workers”라고 표시한다. Dedicated worker, shared worker, service worker는 모두 worker context이므로 규격상 Web Locks를 쓸 수 있다. 다만 서비스 워커에서의 실제 사용은 이 조사에서 직접 실행해 보지 않았으므로 기기·브라우저 검증 항목으로 남긴다.

## 3. 폰에서의 동작

아래는 문서에서 확인된 것과, 문서와 규격에서 추론한 것을 구분한다.

| 상태 | 잠금이 어떻게 되는가(확인/추론) | 다른 탭이 초안을 가져갈 수 있는가 |
| --- | --- | --- |
| Active / Passive / Hidden | 페이지 JS가 돌거나 hidden에서 throttling될 수 있다. 녹음 탭이 잠금을 쥐고 있으면 잠금은 유지된다. | `ifAvailable:true`는 `null`을 받으므로 가져가지 않는다. |
| Frozen | Page Lifecycle API는 freezable task와 타이머·fetch 콜백이 멈춘다고 설명한다. Web Locks의 잠금은 콜백이 반환하는 promise가 settle될 때 풀리므로, promise가 멈춘 동안 잠금은 잡혀 있다고 추론된다. | 가져가지 않는다. 얼어 있는 탭은 “죽은 탭”으로 취급되지 않는다. 대신 그 탭이 resume하지 않고 브라우저가 계속 보존하면 회수도 멈춘다. |
| Discarded | Chrome Page Lifecycle API는 discarded 상태에서 task·event callback·JS가 모두 돌 수 없고 페이지가 unloaded/cleared된다고 설명한다. W3C Web Locks §2.6은 unloading document cleanup에서 남은 잠금과 요청을 terminate한다고 규정한다. 따라서 잠금이 풀린다고 추론된다. 정확한 시점은 문서만으로 단정하지 않는다. | 잠금이 풀린 뒤 새 탭이나 대기 요청이 잡고 회수할 수 있다. |
| Terminated | 페이지가 unload되고 메모리에서 cleared된다. W3C의 unloading cleanup과 agent termination 조항이 적용된다고 추론된다. | 잠금이 풀리면 회수 가능하다. |
| 화면 꺼짐(폰) | 문서가 “화면 꺼짐”을 하나의 표준 상태로 정의하지 않는다. 보통 hidden·background suspension·OS의 탭 종료 중 하나가 된다. 프로세스가 살아 있으면 잠금은 유지되고, 탭이 종료되면 풀린다. 실제 iOS/Android 동작은 기기 검증이 필요하다. | 살아 있으면 가져가지 않고, 실제 종료 뒤 회수된다. |
| bfcache | web.dev는 bfcache가 페이지를 파괴하는 대신 JS 실행을 멈춘다고 설명한다. pending timer·promise도 멈춘다. web.dev는 Web Locks를 다른 탭에 영향을 줄 수 있는 API의 예로 들고, open IndexedDB 연결이 있는 페이지는 일부 브라우저가 bfcache에 넣지 않는다고 적는다. “frozen에서 held Web Locks를 놓으라”는 권고는 Chrome Page Lifecycle 문서의 frozen 절(“Release any held Web Locks”)에 있으며, 같은 절은 IndexedDB·BroadcastChannel·WebSocket 연결도 닫으라고 한다. VoxLog는 `queue.js`에서 DB를 열어 두므로 bfcache 대상이 아닐 가능성이 높다. bfcache에 들어간 경우에는 잠금이 잡힌 채 멈추고, 다시 restore되면 그대로 이어질 것으로 추론된다. | bfcache에 있는 동안에는 가져가지 않는다. 페이지가 bfcache에서 evict/unload되면 잠금이 풀린다. |

중요한 설계상의 예외: Chrome Page Lifecycle 문서의 “frozen에서 held Web Locks를 놓으라”는 조언은 페이지가 다른 탭을 막지 않게 하려는 일반 권고다. VoxLog의 녹음 탭은 녹음이 끝날 때까지 일부러 그 권고를 따르지 않고 잠금을 쥔다. 녹음 중 `pagehide`나 `freeze`에서 잠금을 놓으면, 다른 탭이 살아 있는 녹음의 초안을 가져갈 수 있다. 그래서 녹음 탭은 정상 종료·폐기 때만 잠금을 놓고, 브라우저가 페이지를 실제로 버릴 때는 브라우저가 잠금을 풀게 두는 설계가 맞다.

## 4. VoxLog 적용 설계안

### 4.1 녹음 탭이 쥐는 것

- 잠금 이름은 초안마다 하나: `voxlog-draft-<draftId>`. `draftId`는 현재 `app.js`의 `uuid()`로 만든 고유값이므로 충돌하지 않는다.
- `startRec`에서 `draftStart`를 부르기 **전에** `navigator.locks.request('voxlog-draft-' + draftId, ...)`를 시작한다. 콜백이 잠금을 받은 뒤에만 `draftStart`를 하고, 잠금을 받지 못하면 초안을 만들지 않는다. 이 순서가 중요하다. 잠금 없이 초안을 먼저 만들면 다른 탭이 그 짧은 틈에 회수할 수 있다.
- 콜백은 녹음이 끝날 때 settle되는 promise를 반환한다. 녹음 탭은 그 promise를 `finishRec`의 `draftFinish`/`draftDiscard`와 `enqueue`가 끝난 뒤 resolve한다. 그러면 잠금은 저장·정리까지 끝난 뒤 풀린다.
- 녹음 중 `visibilitychange`, `freeze`, `pagehide`에서 잠금을 놓지 않는다. 사용자가 멈추거나 소리가 없어 폐기할 때만 정상적으로 놓는다. 탭이 죽으면 브라우저가 unloading cleanup에서 놓는다.

### 4.2 회수하는 쪽의 판정

- 새 탭은 `draftRecover()`에서 IndexedDB의 `drafts`를 읽고, 자기 `draftId`는 제외한다.
- 각 초안에 대해 `navigator.locks.request(name, {ifAvailable:true}, async lock => { if (!lock) return false; return draftFinish(...); })`를 호출한다. `lock`이 `null`이면 주인 탭이 잠금을 쥐고 있으므로 건드리지 않는다. 잠금을 얻으면 그 안에서 `draftFinish`를 실행해, 회수 경쟁 중 다른 탭이 같은 초안을 가져가지 못하게 한다.
- `ifAvailable`만으로 끝내면 R41-N13(다른 탭이 이미 열린 뒤 녹음 탭이 늦게 죽는 경우)은 남는다. 그래서 새 탭은 잠금이 잡혀 있는 초안에 대해 **대기 요청**도 하나 건다. 다만 timeout 없는 요청을 그대로 두면 얼어붙은 탭이 FIFO 대기 줄의 머리를 잡고 콜백을 못 돌려 뒤의 탭과 새 탭의 `ifAvailable`을 막을 수 있다. 다음 두 보완을 비교한다.
  - (A) `AbortSignal`을 단 대기 요청. `const ac = new AbortController(); navigator.locks.request(name, {signal: ac.signal}, async lock => { ... draftFinish ... })`를 건다. `freeze`·`pagehide`에서 `ac.abort()`로 대기 요청을 줄에서 빼고, `resume`·`pageshow`에서 새 `AbortController`로 다시 건다. 주인이 살아 있으면 여전히 pending이고, 주인이 죽으면 잠금을 받아 회수한다. 이 abort는 줄 막힘을 거의 없애지만, 완전히 없애지는 않는다. 대기 요청이 이미 잠금을 받았는데 콜백을 돌리는 태스크가 아직 돌지 않았을 때 `freeze`가 오면, abort해도 잠금은 해동 뒤에야 풀려 그동안 뒤의 요청이 막힌다. `freeze`도 `pagehide`도 없이 정지되는 브라우저(iOS Safari 백그라운드 등)에서는 abort가 아예 걸리지 않는다. 이 두 경우를 §6의 기기 검증 항목에 이름으로 적어 두었다(R43-N7).
  - (B) 대기 요청을 쓰지 않고 사건 때 다시 묻기. `visibilitychange`와 `pageshow`에서 `ifAvailable`을 다시 호출한다. 구현이 더 단순하고 얼어붙은 대기자 문제가 원천적으로 없다. 대신 회수 탭이 계속 visible인 채 주인 탭이 죽으면 다음 `visibilitychange`/`pageshow`까지 회수가 늦어지고, R41-N13의 즉시 회수는 보장되지 않는다.
- 권고: (A)를 쓴다. R41-N13의 “주인이 나중에 죽는 경우”를 실제로 회수하면서, 대기 줄 막힘은 abort/re-arm으로 거의 없앨 수 있다(남는 두 틈은 위와 §6). (B)는 더 단순하지만 회수 지연을 감수해야 하므로 주 경로로 권하지 않는다. `freeze` 이벤트를 못 받는 브라우저에서는 `pagehide`와 `pageshow`를 최소한의 경계로 쓰고, 그래도 대기 요청을 건다. 이 보완은 Web Locks 규격의 signal·pending request 의미와 Page Lifecycle 문서의 frozen 정의(콜백·타이머가 멈춘다)를 합친 추론이며, 직접 실행해 보지 않았다.
- 대기 요청은 페이지가 살아 있는 동안 pending promise로 남을 수 있다. 페이지가 navigation/close로 사라지면 그 요청도 context와 함께 사라진다. 앱의 다른 작업을 막지는 않는다.
- `query()`는 디버깅이나 “현재 held/pending 목록” 확인에만 쓰고, 회수 판정의 근거로 쓰지 않는다. `ifAvailable`이 원자적 판정이다.
- 회수 시도 시점: 앱 `init`에서 `draftRecover()`를 한 번 부르고, 그 안에서 `ifAvailable` 즉시 시도 + 대기 요청을 건다. 현재 `app.js`의 22초 `setTimeout` 재시도는 없앤다. 탭이 visible이 될 때 추가 `ifAvailable` 시도를 넣을 수 있지만, 대기 요청이 있으면 필수는 아니다.

### 4.3 지원하지 않는 브라우저의 가장 단순한 열화

`navigator.locks`가 없으면(secure context가 아니라서 없는 경우 포함) 새 코드는 **초안 자체를 만들지 않는다**. `DRAFT_LEASE_MS=20000`·5초 `draftTouch`·`liveDraftIds(300)` BroadcastChannel 질문·22초 재시도 같은 옛 lease 장치를 열화 경로로 남기지 않는다. 잃는 것은 '끊긴 녹음 되살리기' 하나다. 녹음과 올리기는 그대로 되고, 녹음은 끝날 때 메모리의 조각으로 `enqueue`된다. 지원 검출은 `navigator.locks && typeof navigator.locks.request === 'function'`(예외는 false)로 하고, 그 값을 `supported()`의 `draftLocks`로 함께 돌려주어 UI가 같은 판단을 쓴다. 이 열화는 README와 `docs/INTERFACE.md`에 적는다.

### 4.4 배포 전환기 규칙

새 코드가 배포되어도 이미 열린 구버전 탭은 잠금을 모른 채 `aliveAt` lease와 BroadcastChannel만 쓴다. 두 방향의 사고를 세대 표식 하나로 가른다. 새 코드가 만든 초안에는 `lock: true`(새 세대 표식)와 `aliveAt: Infinity`를 함께 저장한다.

- **구탭이 새 녹음을 빼앗는 쪽**(R43-N6). 구버전 탭의 회수 필터는 `Date.now() - aliveAt < 20000`이면 그 초안을 녹음 중으로 보고 건너뛴다. `aliveAt: Infinity`는 이 식을 `-Infinity < 20000`, 곧 항상 참으로 만들어 새 초안을 구탭의 회수 대상에서 영영 빼놓는다. 새 코드가 `draftSetLocation`·`draftAppend`에서 `aliveAt`을 다시 고치면 `Infinity`가 유한값으로 덮여 이 보호가 풀리므로, 그 갱신을 지운다. 새 코드는 BroadcastChannel 표식을 두지 않는다(`aliveAt: Infinity`가 그 역할을 대신한다).
- **새 코드가 구탭 녹음을 빼앗는 쪽.** 잠금이 비어 있어도 구탭이 녹음 중일 수 있다. 그래서 20초 신선도 규칙을 **구세대 초안**(`d.lock !== true`)에만 남긴다. 상수 이름은 `OLD_DRAFT_FRESH_MS`이고, 주석에 '잠금 이전 초안 전용'이라고 적는다. 새 세대 초안은 잠금만 보므로 새 코드끼리는 잠금을 얻는 즉시 회수된다. 22초 재시도와 5초 heartbeat를 지워도 새 코드끼리의 회수가 늦어지지 않는 이유가 이것이다(R43-N6의 모순을 이렇게 푼다).
- 서비스 워커 `VERSION`을 올리는 것은 새 로드에 새 코드를 주는 데 도움이 되지만, 이미 열린 구탭을 닫거나 다시 로드하게 만들지는 않는다. 그래서 그것을 전환기의 안전 근거로 삼지 않는다. 전환기 종료는 '구버전 탭이 남지 않았다'는 배포·관측 기준으로 정하고, 그 뒤에는 `OLD_DRAFT_FRESH_MS` 필터도 지운다.

이 전환기 규칙은 규격이 아니라 배포 현실에서 온 추론이다. 남는 위험은 구세대 초안 쪽이다. 구버전 탭이 20초 넘게 얼면 lease가 만료되어 새 코드가 그 초안을 회수할 수 있다(§5.5 R41-N14 행). 이는 구버전 lease 설계의 기존 위험이며 전환이 끝나면 함께 사라진다. 새 세대 초안은 프리즈 동안 잠금이 유지되고 `aliveAt: Infinity`라 이 위험이 없다.

## 5. 걷어낼 범위

### 5.1 `projects/VoxLog/web/queue.js`

없어지거나 바뀔 것:

- `tabId`, `draftBc`, `draftPings`, `liveDraftIds(waitMs)`, `DRAFT_LEASE_MS` — 모두 없앤다. 새 코드의 생존 판정은 잠금 하나이고, heartbeat·BroadcastChannel은 두지 않는다.
- `draftTouch(draftId)`와 그 export — 5초 heartbeat. 잠금이 생존 표시를 대신하므로 없앤다.
- `aliveAt` 갱신 — `draftStart`는 `aliveAt: Infinity`를 한 번만 쓰고, `draftSetLocation`·`draftAppend`의 `aliveAt = Date.now()`는 지운다. `Infinity`가 유한값으로 덮이면 구버전 탭 보호가 풀린다. 필드는 구세대 초안 호환과 구탭 보호를 위해 DB에 남긴다.
- `draftRecover(exceptDraftId)`의 `now - aliveAt < DRAFT_LEASE_MS` 필터와 `!live[d.draftId]` 필터 — `ifAvailable`과 `AbortSignal` 대기 요청으로 대체한다. 신선도 필터는 구세대 초안(`d.lock !== true`) 전용 `OLD_DRAFT_FRESH_MS`(20초)로 이름과 적용 범위를 좁혀 남긴다.

전환기(§4.4)에 남는 것은 `aliveAt` 필드와 `OLD_DRAFT_FRESH_MS` 필터뿐이다. heartbeat·BroadcastChannel 표식은 되살리지 않는다. 구버전 탭이 실제로 남지 않았다고 확인한 뒤에는 이 필터도 지운다. 서비스 워커 `VERSION` 변경만으로는 그 시점을 보장하지 않는다.

남을 것:

- DB `drafts`, `chunks` 저장 구조와 `draftStart`, `draftAppend`, `draftSetLocation`, `draftFinish`, `draftDiscard`, `draftClear`. 이들은 녹음 조각 보존과 최종 `enqueue`에 계속 필요하다.
- `activeDraft` 또는 같은 역할의 자기 초안 표식. 다른 탭의 회수 대상에서 자기 초안을 제외하는 데 필요하다.
- 새로 넣을 것: `draftRelease(draftId)`(쥔 잠금을 놓는 안쪽 함수)와 `onrecover(cb)`(나중에 끝난 회수의 살린 수를 알리는 새 export). `draftStart`는 잠금 이름 `'voxlog-draft-' + draftId`를 얻은 뒤에 초안을 넣고, `draftFinish`·`draftDiscard`는 끝에 `draftRelease`를 부른다.

### 5.2 `projects/VoxLog/web/app.js`

없어지거나 바뀔 것:

- `startRec`의 `rc.touchTimer` 생성과 5초 `setInterval` 안의 `dq.draftTouch(rc.draftId)` 호출. 잠금이 생존 표시라 heartbeat는 없다.
- `finishRec`의 `clearInterval(rc.touchTimer)`. heartbeat를 걷었으므로 함께 없앤다.
- `init`의 22초 `setTimeout`과 그 안의 두 번째 `rq.draftRecover()` 호출. 잠금 대기 요청이 이 지연을 대신한다.
- `startRec`은 `dq.draftStart(...)`가 돌려주는 Promise를 `rc.chain`에 걸어 `rc.draftOk`를 정한다. 실패와 거절 모두 `false`로 본다.
- `init`에서 `queueApi().onrecover`가 있으면 콜백을 등록해, 나중에 끝난 회수의 살린 수를 토스트와 `updateQueue()`로 알린다.
- `finishRec`의 두 메모리 조각 경로(`draftOk`가 false일 때, `draftFinish`가 false이거나 실패했을 때)는 `enqueue`가 끝난 뒤 `q.draftDiscard(draftId)`로 DB 초안·조각을 지우고 잠금을 놓는다. 실패는 삼킨다(녹음은 이미 대기열에 있다).

전환기에도 heartbeat를 되살리지 않는다. 새 초안은 `aliveAt: Infinity` 하나로 구탭의 회수 필터를 피한다(§4.4).

남을 것:

- `finishRec`의 `draftFinish`/`draftDiscard`와 `enqueue` 흐름. 잠금 해제는 이 저장·정리 뒤에 한다.
- `init`의 첫 `draftRecover()` 호출. 구현은 Web Locks 기반으로 바뀌지만 호출 위치는 남는다.
- `visibilitychange`의 화면 잠금(`wakeLock`) 처리와 녹음 UI. 초안 소유권과 무관하다.

### 5.3 `projects/VoxLog/web/sw.js`

초안 소유권·lease 코드는 현재 `sw.js`에 없다. `doUpload()`의 업로드 엄격 판정(성공은 `res.ok` + JSON `id` 문자열일 때만)은 이 조사와 별개로 남는다. Web Locks 때문에 `sw.js`를 바꿀 필요는 없다. 서비스 워커에서 회수를 설계하려면 별도 검증이 필요하지만, 권고안은 window 쪽 회수를 유지한다.

### 5.4 `projects/VoxLog/tests/browser_voxlog.py`

남길 것:

- `db_drafts(pg)`, `draft_recover_done(pg)` helper.
- `t27`(녹음 중 새 탭이 초안을 가져가지 않음)은 Web Locks 판정으로 다시 작성해 남긴다.
- `t31`(200 text/html·id 없는 JSON 엄격 판정)은 초안 방식과 무관하므로 남긴다.

바꿀 것:

- `t30`은 현재 “BroadcastChannel이 없는 탭” 열화 검사다. Web Locks가 primary가 되면 `t30`은 **fallback 검사**로 이름/전제를 바꾸거나, Web Locks가 없는 환경을 강제하는 새 검사로 대체한다.
- 새 검사가 필요하다: (a) 녹음 탭이 잠금을 쥐는 동안 두 번째 탭의 `ifAvailable`이 `null`이고 초안을 가져가지 않음, (b) 녹음 탭 `page.close()` 뒤 대기 요청이 잠금을 얻어 초안을 회수함, (c) 빠른 새로고침 뒤 회수가 22초 지연 없이 됨, (d) 조각 0개 초안은 회수 수에 세지 않음, (e) `draftOk=false` 뒤 DB 초안이 정리됨, (f) 대기 탭이 `freeze`/`pagehide`에서 요청을 abort하고 `resume`/`pageshow`에서 다시 걸어 뒤의 `ifAvailable`을 막지 않음, (g) 전환기에 잠금이 비어 있지만 `aliveAt`이 신선한 구세대 초안(`lock !== true`)은 새 코드가 회수하지 않음, (h) 새 세대 초안(`lock: true`)은 `aliveAt`과 무관하게 잠금만으로 즉시 회수됨.

### 5.5 R41-N13~N18 판정

| 번호 | 새 방식에서 | 이유 |
| --- | --- | --- |
| R41-N13 | **설계 조건부로 저절로 사라짐** | 다른 탭이 이미 열린 뒤 녹음 탭이 죽는 경우는 `ifAvailable` 한 번만으로는 남는다. 4.2의 timeout 없는 대기 `request`를 넣으면, 주인 탭이 죽을 때 잠금이 넘어가 회수된다. 대기 요청을 넣지 않으면 여전히 고쳐야 함. |
| R41-N14 | **저절로 사라짐** (전환기 예외) | 20초 넘는 프리즈에서 lease가 만료되어 살아 있는 초안을 회수하는 문제는, 새 세대 초안이면 잠금이 프리즈 동안 유지되고 `aliveAt: Infinity`라 사라진다. 대신 얼어 있는 탭이 영원히 resume하지 않으면 회수가 늦어진다. 전환기에는 구세대 초안(`lock !== true`)에 20초 규칙이 남아 있어, 구버전 탭이 20초 넘게 얼면 그 초안을 새 코드가 회수할 수 있다 — 구버전 lease 설계의 기존 위험이며 전환이 끝나면 함께 사라진다. |
| R41-N15 | **대부분 사라짐** | 녹음 중 새로고침하면 기존 context가 unloading cleanup으로 잠금을 풀고 새 페이지가 잠금을 얻는다. 22초 재시도가 필요 없다. 정확한 release 타이밍은 기기 검증 항목이다. |
| R41-N16 | **여전히 고쳐야 함** | `draftFinish`는 조각이 0개여도 `draftClear` 뒤 `true`를 돌려준다(`queue.js:465`). Web Locks는 이 반환값을 바꾸지 않는다. 0개 초안은 `false`로 돌려 회수 수에 세지 않아야 한다. |
| R41-N17 | **일부 사라짐 / 일부 남음** | lease 만료 회수 경로 검사는 새 방식에서 의미가 없어져 사라진다. 그러나 `sw.js` 업로드 엄격 판정과 `t31`의 id 없는 JSON `lastError` 검사는 그대로 필요하다. 새 Web Locks 검사도 추가해야 한다. |
| R41-N18 | **여전히 고쳐야 함** | `draftAppend` 실패로 `rc.draftOk=false`가 되면 `activeDraft`와 DB 초안이 남는 문제(`queue.js:373,475`, `app.js:448-454`)는 잠금 방식과 별개다. `finishRec`의 fallback/폐기 경로에서 DB 초안을 정리하고 자기 표식을 해제해야 한다. |

## 6. 걸리는 점과 모르는 점

문서로 확인되지 않아 실제 기기·브라우저에서 봐야 하는 것:

- **Discarded/terminated에서 잠금이 풀리는 정확한 시점.** W3C는 unloading cleanup/agent termination에서 terminate한다고 하지만, Chrome이 discard할 때 unloading cleanup을 언제 실행하는지 이 문서들만으로 단정할 수 없다.
- **frozen 탭이 오래 남는 경우.** 잠금이 계속 잡혀 있어 다른 탭이 회수하지 못한다. 브라우저가 bfcache를 언제 evict하는지, 사용자가 탭을 다시 열 때까지 얼마나 보존하는지는 기기·브라우저마다 다르다.
- **iOS/iPadOS의 화면 꺼짐·백그라운드·탭 종료.** Safari가 백그라운드 탭의 JS와 잠금을 어떻게 처리하는지, OS가 탭을 죽일 때 Web Locks가 즉시 풀리는지는 실제 iPhone/iPad에서 확인해야 한다.
- **MediaRecorder가 frozen/background에서 계속 녹음하는지.** Page Lifecycle 문서는 task가 멈춘다고 하지만, 오디오 녹음·미디어 장치의 실제 동작은 별도 검증이 필요하다.
- **bfcache와 Web Locks의 상호작용.** web.dev는 open IndexedDB가 bfcache를 막을 수 있다고 하고 Web Locks를 다른 탭에 영향을 줄 수 있는 API의 예로 든다. held Web Locks를 frozen에서 놓으라는 권고는 Chrome Page Lifecycle 문서의 것이다. VoxLog는 녹음 중 그 권고를 일부러 따르지 않으므로, bfcache에 들어가는지와 잠금이 restore까지 유지되는지는 실제 Chrome/Safari에서 확인해야 한다.
- **서비스 워커에서 `navigator.locks` 사용.** 규격상 WorkerNavigator에 `locks`가 있지만, 이 앱의 서비스 워커에서 실제로 쓸 수 있는지와 서비스 워커 종료 뒤 상태가 어떤지는 실행 검증이 필요하다.
- **background/hidden 탭의 대기 요청이 언제 실행되는지.** 잠금이 풀려도 회수 탭이 백그라운드에서 throttling되면 회수가 늦을 수 있다. 대기 요청이 즉시 콜백을 받는지는 브라우저별 검증이 필요하다.
- **얼어붙은 대기 탭과 abort/re-arm.** `freeze`/`pagehide`에서 대기 요청을 abort하고 `resume`/`pageshow`에서 다시 거는 설계가 실제 Chrome·Safari·iOS에서 이벤트 순서와 잠금 승계대로 동작하는지는 기기 검증이 필요하다. 규격의 FIFO 큐와 Page Lifecycle의 frozen 정의를 합친 추론이다.
- **대기 요청이 잠금을 받은 직후 `freeze`(R43-N7 첫 경우).** 대기 요청이 잠금을 받았지만 콜백을 돌리는 태스크가 아직 돌지 않았을 때 `freeze`가 오면, abort해도 잠금은 해동 뒤에야 풀린다. 그동안 뒤의 `ifAvailable`과 대기 요청이 막히는지, 막히는 시간이 실제로 얼마나 되는지 확인이 필요하다. 틈은 좁을 것으로 추론한다.
- **`freeze`·`pagehide` 없이 정지하는 브라우저(R43-N7 둘째 경우).** iOS Safari가 백그라운드로 갈 때 `freeze`도 `pagehide`도 주지 않으면 abort가 걸리지 않아, 얼어붙은 탭의 대기 요청이 줄을 잡고 남을 수 있다. 실제 iPhone/iPad에서 이벤트가 오는지, 오지 않을 때 줄이 얼마나 막히는지 확인해야 한다.
- **iPadOS와 Edge의 정확한 최소 버전.** iPadOS는 별도 BCD 항목이 없어 iOS Safari 15.4를 따르는 것으로 적었다. Edge는 BCD가 mirror라 Chromium 기반 Edge 첫 버전 79로 추정했다. 실제 배포 대상의 최소 버전은 별도 확인이 필요하다.
- **구버전 탭이 남은 전환기.** 세대 표식(`lock: true`)과 `aliveAt: Infinity`, 그리고 구세대 초안 전용 20초 규칙이 실제 배포에서 충분한지, 구탭이 얼마나 오래 남는지는 배포·관측으로 확인해야 한다.
- **SharedWorker/서비스 워커를 대안으로 쓸 때의 연결 종료 감지.** `MessagePort`에는 close 이벤트가 없고 SharedWorker 수명은 페이지 참조에 묶인다. 중앙 조정자 방식은 이 조사에서 표준 권고로 채택하지 않았다.

## 출처

읽은 URL(모두 `curl -sL`로 받았고 HTTP 200 확인):

- https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API
- https://developer.mozilla.org/en-US/docs/Web/API/LockManager/request
- https://developer.mozilla.org/en-US/docs/Web/API/LockManager/query
- https://developer.mozilla.org/en-US/docs/Web/API/Navigator/locks
- https://developer.mozilla.org/en-US/docs/Web/API/WorkerNavigator/locks
- https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel
- https://developer.mozilla.org/en-US/docs/Web/API/SharedWorker
- https://developer.mozilla.org/en-US/docs/Web/API/MessagePort
- https://developer.mozilla.org/en-US/docs/Web/API/Clients/matchAll
- https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
- https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API
- https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts
- https://w3c.github.io/web-locks/
- https://developer.chrome.com/docs/web-platform/page-lifecycle-api
- https://web.dev/articles/bfcache
- https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/LockManager.json
- https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/Lock.json
- https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/BroadcastChannel.json
- https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/SharedWorker.json
- https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/Clients.json

읽지 못한 URL:

- https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/IndexedDB.json — HTTP 404. IndexedDB 지원 범위는 이 조사에서 BCD로 확인하지 않았고, MDN IndexedDB_API 문서만 읽었다.

## 고친 이력

- R43 검수 반영: R43-N1 — §4.2에 `AbortSignal` 대기 요청과 사건 기반 대안을 비교하고 `AbortSignal` 쪽을 권고했다. §6에 얼어붙은 대기 탭의 실제 기기 검증 항목을 추가했다.
- R43 검수 반영: R43-N2 — §4.4에 배포 전환기 규칙을 추가하고, §5.1·§5.2에 `aliveAt`·`draftTouch`·BroadcastChannel 표식을 전환기 동안 유지하는 조건을 적었다.
- R43 검수 반영: R43-N3 — §2 표의 mirror를 Chrome Android 69, Firefox Android 96, Safari iOS 15.4, WebView Android 69, WebView iOS 15.4로 풀고, Edge는 79+로 추정 표시했다.
- R43 검수 반영: R43-N4 — §3 bfcache 행과 §6의 출처를 Chrome Page Lifecycle 문서로 고치고, 녹음 중에는 그 권고를 일부러 따르지 않는다는 예외를 명시했다.
- R44 구현 결정 반영: R43-N6 — §4.4를 세대 표식(`lock: true`)과 `aliveAt: Infinity` 규칙으로 다시 썼다. 20초 신선도 규칙은 표식 없는 구세대 초안(`OLD_DRAFT_FRESH_MS`)에만 적용하고, 새 코드는 heartbeat·BroadcastChannel 없이 잠금만으로 판정한다. §5.1·§5.2에서 전환기 유지 항목을 걷어냈다.
- R44 구현 결정 반영: R43-N7 — §4.2의 '얼어도 줄을 막지 않는다' 단정을 좁히고, §6에 두 경우(잠금을 받은 직후 freeze, freeze/pagehide 없이 정지하는 iOS Safari)를 이름으로 넣었다.
- R44 구현 결정 반영: R43-N8 — §5.5 R41-N14 행에 전환기 단서(구세대 초안의 20초 규칙)를 붙였다.
- R44 구현 결정 반영: §4.3·요약 — 웹 잠금이 없으면 초안을 만들지 않고 되살리기만 끈다. 옛 lease 열화 경로를 남기지 않는다.



