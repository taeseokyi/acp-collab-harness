# R44 공통 인터페이스 - 녹음 초안의 주인 판정을 웹 잠금으로 (요청 Q-261124-b4ad)

관리자가 정한 약속. 노드마다 이 파일을 읽고 자기 파일만 고친다. 근거 문서: `projects/VoxLog/docs/RESEARCH-draft-owner.md`
(§4.1·§4.2(A)·§5). **이 파일과 조사 문서가 다르면 이 파일이 맞다** (요청이 옛 장치를 남기지 말라고 했고, 전환기 규칙을 더 단순하게 정했다).

## 원칙
- 손으로 만든 장치를 걷어낸다: `tabId`, `draftBc`(BroadcastChannel `voxlog-drafts`), `draftPings`, `liveDraftIds`,
  `DRAFT_LEASE_MS` 로 하는 '살아 있나' 판정, `draftTouch`(5초 갱신)와 그 export, app.js 의 `rc.touchTimer`, init 의 22초 재시도.
  두 방식을 함께 남기지 않는다.
- 웹 잠금(`navigator.locks`)이 없는 브라우저(또는 보안 연결이 아닌 곳)에서는 **초안 자체를 만들지 않는다** - 녹음·올리기는
  그대로(녹음은 끝날 때 메모리의 조각으로 `enqueue`), '끊긴 녹음 되살리기' 만 꺼진다.

## queue.js (window.VoxQueue)
- `locksOk()` (안쪽 함수): `!!(navigator.locks && typeof navigator.locks.request === 'function')` - 예외는 false.
- `supported()` 의 돌려주는 값에 `draftLocks: <locksOk()>` 를 더한다.
- 잠금 이름: `'voxlog-draft-' + draftId`.
- `draftStart({draftId, mime, recordedAt, location}) -> Promise<boolean>`
  - `locksOk()` 가 아니면 아무것도 쓰지 않고 `false`.
  - 맞으면 `navigator.locks.request(name, {ifAvailable: true}, cb)`: cb 가 lock 을 받으면(null 이 아니면) **그 안에서**
    초안 줄을 넣고(`{draftId, mime, recordedAt, location, started: now, aliveAt: Infinity, lock: true}`), 바깥 Promise 를
    `true` 로 풀고, cb 는 '놓기 전까지 끝나지 않는 Promise' 를 돌려줘 잠금을 쥔다. 놓는 함수는 `held[draftId]` 에 둔다.
    lock 이 null 이거나 넣기가 실패하면 쥔 것을 놓고 `false`(실패면 reject 해도 된다 - app.js 는 둘 다 draftOk=false 로 본다).
  - `activeDraft = draftId` 는 true 일 때만.
  - `aliveAt: Infinity` 는 **이미 열려 있는 구버전 탭 막이**다: 구버전 탭의 회수 필터(`now - aliveAt < 20000` 이면 건너뜀)가
    새 초안을 영영 건너뛰게 한다(R43-N6 의 '구탭이 새 녹음을 빼앗음' 쪽). 새 코드는 aliveAt 을 다시 고치지 않는다
    (`draftSetLocation`·`draftAppend` 의 `aliveAt = Date.now()` 를 지운다).
  - `lock: true` 는 세대 표식이다(새 코드가 만든 초안).
- `draftRelease(draftId)` (안쪽 함수): `held[draftId]` 가 있으면 불러 잠금을 놓고 지운다. `activeDraft === draftId` 면 null.
- `draftFinish(draftId, durationMs, location) -> Promise<boolean>`: 초안이 없으면 `false`, **조각이 0개면 초안을 지우고 `false`**
  (R41-N16 - 지금은 true), 있으면 enqueue → 지움 → `true`. 성공·실패 모두 끝에 `draftRelease(draftId)`.
- `draftDiscard(draftId)`: 초안·조각을 지우고 `draftRelease(draftId)`.
- `draftRecover(exceptDraftId?) -> Promise<number>`: `locksOk()` 가 아니면 `0`. 아니면 drafts 를 읽어, `exceptDraftId`·
  `activeDraft`·`held` 에 있는 것은 빼고, 각각:
  - **구세대 초안**(`d.lock !== true`): `typeof d.aliveAt === 'number' && Date.now() - d.aliveAt < 20000` 이면 건너뛴다
    (구버전 탭이 녹음 중일 수 있음 - 상수 이름 `OLD_DRAFT_FRESH_MS`, 주석에 '잠금 이전 초안 전용' 이라고). 아니면 아래 즉시 판정으로.
    구세대에는 기다리는 요청을 걸지 않는다(다음 방문 때 다시 본다).
  - 즉시 판정: `navigator.locks.request(name, {ifAvailable: true}, async lock => lock ? draftFinish(id, null) : null)`.
    `true` 면 센다. `null`(주인이 쥐고 있음)이고 새 세대면 기다리는 요청을 건다.
  - 기다리는 요청(R41-N13): `waits[id]` 가 없을 때만 `AbortController` 를 만들어
    `navigator.locks.request(name, {signal}, async () => { delete waits[id]; const ok = await draftFinish(id, null); if (ok) recovered(1); })`.
    abort 로 끝난 거절(AbortError)은 조용히 삼킨다. 기다리는 동안 draftRecover 의 Promise 는 이것을 기다리지 않는다.
  - `recovered(n)`: `onrecover` 로 등록된 콜백들을 `n` 으로 부르고 `notify()`.
- `onrecover(cb)` (새 export): 기다리던 회수가 나중에 끝났을 때 불린다(살린 수).
- 페이지 수명(한 번만 등록): `freeze`·`pagehide` 에서 모든 `waits` 를 abort 하고 비운다. `resume`·`pageshow`(persisted 든 아니든)
  에서 `draftRecover()` 를 다시 불러(살린 수가 있으면 `recovered(n)`) 기다리는 요청을 다시 건다.
  **쥔 잠금(held)은 freeze/pagehide 에서 놓지 않는다** - 조사 문서 §3 의 예외.
- export 에서 `draftTouch` 를 빼고 `onrecover` 를 더한다.

## app.js
- `startRec`: `rc.chain = Promise.resolve(dq.draftStart({...})).then(ok => { rc.draftOk = ok === true; }, () => { rc.draftOk = false; })`.
  `rc.touchTimer` 와 5초 `setInterval`·`draftTouch` 호출을 지운다.
- `finishRec`: `clearInterval(rc.touchTimer)` 를 지운다. 메모리 조각으로 `enqueue(item)` 하는 두 길(`rc.draftOk` 가 false 일 때,
  `draftFinish` 가 false 이거나 실패했을 때) 모두 enqueue 가 끝난 뒤 `q.draftDiscard(draftId)` 를 불러 DB 초안·조각을 지우고 잠금을
  놓는다(R41-N18). draftDiscard 의 실패는 삼킨다(녹음은 이미 대기열에 있음).
- `init`: 22초 `setTimeout` 재시도를 지운다. `queueApi().onrecover` 가 있으면 `n => { toast('끝나지 않은 녹음 ' + n + '건을 살렸습니다'); updateQueue(); }`
  를 등록한다(첫 `draftRecover()` 의 토스트는 그대로).

## 바꾸지 않는 것
- `sw.js`(초안 코드가 없다 - 업로드 엄격 판정은 그대로), DB 이름·판(`voxlog` 2)·저장소 구조, `draftAppend`·`draftSetLocation` 의 동작
  (aliveAt 줄만 빠짐), `enqueue`·`flush`.
