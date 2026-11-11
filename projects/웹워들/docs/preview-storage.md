> 설계 문서입니다. 구현은 다음 라운드입니다 (R12 T-152, T-158 에서 검토 반영).

# 미리보기(격리 칸)에서 기록이 남게 하는 postMessage 길

한 줄 요약: 결과물은 격리된 채로 두고, **모니터 쪽 페이지가 자기가 만든 iframe 하나에만**
"그 프로젝트 몫의 작은 문자열 보관함"을 빌려 준다. 프로젝트 이름은 **메시지에서 읽지 않고**
모니터가 iframe 을 만들 때 쥔 변수에서 온다.

## 1. 지금 무엇이 막혀 있나

모니터는 결과물을 두 겹으로 격리합니다.

- `tools/aimem_monitor/static/app.js:2864`
  `fr.setAttribute('sandbox', 'allow-scripts allow-popups allow-modals');` - `allow-same-origin` 없음
- `tools/aimem_monitor/server.py:2118` (`app_csp`)
  `"sandbox allow-scripts allow-popups allow-modals; " ...` - "새 탭에서 열기"로 iframe 밖에서 열어도 같은 격리

`allow-same-origin` 이 없으니 문서의 출처는 **불투명(opaque)** 이고 `self.origin === "null"` 입니다.
불투명 출처에서 `window.localStorage` 를 **읽는 순간** 브라우저가 `DOMException` `SecurityError` 를
던집니다(크로미움: "The document is sandboxed and lacks the 'allow-same-origin' flag").
`document.cookie` 도 같은 예외입니다.

`storage.js` 는 이것을 첫 접근에서 한 번 잡고 메모리로 넘어갑니다.

```js
// projects/웹워들/web/js/storage.js:8-16
  try {
    const ls = globalThis.localStorage;   // ← 여기서 SecurityError
    ...
    backend = ls;
  } catch {
    backend = null;                        // ← 이후 모든 read/write 는 Map 만 씀
  }
```

`write()`(36-44행)는 언제나 `memory.set(k, text)` 를 먼저 하므로 판 안에서는 값이 살아 있지만,
새로 고치면 `memory` (3행 `new Map()`)가 비어 **통계·설정·진행 중인 판·`seenHelp`** 가 사라집니다.

지금 쓰는 키(접두 `webwordle.` 는 2행):

| 키 | 값(JSON) | 크기 감 |
|---|---|---|
| `stats` | `{played,wins,streak,maxStreak,dist[6],lastDay}` | ~120 B |
| `settings` | `{hardMode,dark,colorblind}` | ~50 B |
| `seenHelp` | `true` | 4 B |
| `daily.YYYY-MM-DD` | 그날 판 상태 객체 | 수백 B, **하루 하나씩 쌓임** |

## 2. 주고받을 것

**결과물 → 모니터 두 종류, 모니터 → 결과물 한 종류**면 충분합니다. 읽기는 시작할 때 한 번에
받고(스냅숏), 그 뒤로는 결과물의 `memory` 가 원본이며 쓰기만 흘려보냅니다. 키 하나씩 묻는
`get` 은 두지 않습니다 - `read()` 가 동기 함수라 비동기 왕복을 끼울 자리가 없습니다.

```jsonc
// ① 결과물 → 모니터: 시작 신호 (페이지마다 1번)
{"aimem": "store.v1", "op": "ready"}

// ② 모니터 → 결과물: 그 프로젝트 칸 전체
{"aimem": "store.v1", "op": "snapshot",
 "items": {"stats": "{\"played\":7,\"wins\":5,...}", "settings": "{\"hardMode\":false,...}"}}

// ③ 결과물 → 모니터: 쓰기 하나 (value 가 null 이면 지우기)
{"aimem": "store.v1", "op": "put", "key": "daily.2026-11-11", "value": "{\"guesses\":[...]}"}
```

못박는 것:

| 필드 | 자료형 | 상한 / 꼴 |
|---|---|---|
| `aimem` | 문자열 | 정확히 `"store.v1"` (다르면 조용히 버림 - 다른 postMessage 와 섞여도 안전) |
| `op` | 문자열 | `ready` · `put` 만 (모니터가 받는 쪽). `snapshot` 은 모니터만 보냄 |
| `key` | 문자열 | `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` (1~64자, 첫 글자 영숫자) |
| `value` | 문자열 또는 `null` | 문자열이면 **8,192자 이하**. 모니터는 **파싱하지 않음** |
| 메시지 전체 | 평범한 객체 | 위 필드 밖의 키가 있으면 버림 |
| 프로젝트 칸 | - | 키 **64개 이하**, **저장될 형태** `JSON.stringify(칸)` 의 길이 **65,536자 이하** |
| 빈도 | - | `ready` **패널 수명당 2번까지**(두 번째는 첫 번째로부터 1초 뒤부터) · `put` **1초 창에 20개까지**. 넘치면 조용히 버림 |

크기는 **직렬화한 결과**로 잽니다. 값이 이미 JSON 문자열이라 다시 직렬화하면 `"` 가 `\"` 로 늘어
(최대 약 2배) 원본 합으로는 실제 저장을 못 막기 때문입니다. `put` 마다 반영한 칸을 `JSON.stringify` 해
길이(UTF-16 단위 = JS `length`, `localStorage` 가 세는 단위)를 보고 넘으면 버립니다(3.3).

값을 JSON 문자열 그대로 나르는 것은 일부러입니다. `storage.js` 는 이미 `JSON.stringify` 한 문자열을
`setItem` 하고 있었으니 바꿀 것이 적고, 모니터는 내용을 해석할 일이 없어 공격면이 문자열 길이뿐입니다.
`structuredClone` 으로 넘어오는 객체·`Blob`·`MessagePort` 같은 것은 자료형 검사에서 걸러집니다.

## 3. 모니터가 받을 때 보는 것

`openProjectApp` 안, **iframe 을 붙이기 전에** 리스너를 겁니다(① 이 리스너보다 먼저 오면 잃습니다).

```js
const part = 'aimem.app.v1.' + encodeURIComponent(name);  // name 은 pr.name - 메시지에서 오지 않음
const dict = loadPart(part);   // Map - 패널을 열 때 한 번만 읽고 이후엔 이 사본이 원본 (3.2)
function onMsg(ev) {
  const src = ev.source;                        // 1. 이 패널이 만든, 지금 붙어 있는 그 칸에서 온 것만
  if (!src || src !== fr.contentWindow || !fr.isConnected) return;
  if (ev.origin !== 'null') return;             // 2. 격리가 풀려 있으면 받지 않음
  const m = ev.data;                            // 3. 꼴·자료형·크기 (2절 표)
  if (!m || typeof m !== 'object' || Array.isArray(m) || m.aimem !== 'store.v1') return;
  if (m.op === 'ready' && rate.ready()) src.postMessage({aimem:'store.v1', op:'snapshot', items: Object.fromEntries(dict)}, '*');
  else if (m.op === 'put' && rate.put() && okKey(m.key) && okVal(m.value)) putIfFits(dict, m.key, m.value);
}
window.addEventListener('message', onMsg);
state.panelCleanups.push(() => {               // 3.1 - 닫을 때·다른 패널을 열 때 불림
  window.removeEventListener('message', onMsg);
  flushPut(part, dict);                         // try/catch 안 (3.3)
  fr.remove();                                  // 숨긴 채 남지 않게 - isConnected 가 거짓이 됨
});
```

### 3.1 패널 닫힘 훅 (`openPanel` 변경)

지금 `openPanel`(`app.js:383`)은 `build(body)` 를 부르고 끝나며, `closeDetail`(`app.js:352`)은
오버레이를 **숨기기만** 해서 iframe 이 DOM 에 붙은 채 계속 돕니다. 닫힘을 알 길이 없으므로 다음을 더합니다.

- `state.panelCleanups = []` (정리 함수 목록). `runPanelCleanups()` 는 목록을 **먼저 비운 뒤**
  하나씩 `try { f() } catch {}` 로 부릅니다 - 하나가 던져도 나머지는 돌고, 다시 불려도 두 번 돌지 않음
- `openPanel` **첫 줄**과 `closeDetail` **첫 줄**에서 `runPanelCleanups()`. 그 밖의 닫힘 경로
  (Esc·바깥 클릭)는 모두 `closeDetail` 을 지나므로 따로 걸지 않습니다. 정리할 것이 없는 패널은 그대로

**검사 1 의 세 조건은 각각 따로 필요합니다.** 정리 훅이 리스너를 떼는 것이 1차 방어이고, 첫 줄
검사는 훅이 빠지거나 예외로 끊겨도 남는 **마지막 방어선**입니다.

- `!src` - 보낸 창이 배달 전에 버려지면(결과물이 중첩 iframe 에서 `top.postMessage` 하고 같은 태스크에서
  그 iframe 을 지움) `ev.source` 는 `null` 입니다. 닫힌 패널의 `fr.contentWindow` 도 `null` 이므로
  이 조건이 없으면 **`null === null` 이 참이 되어 남은 리스너가 그 메시지를 자기 칸에 씁니다**
- `src !== fr.contentWindow` - 객체 동일성(중첩 iframe·팝업·다른 패널의 창). `!fr.isConnected` - 떼어 낸
  iframe 의 리스너가 남아도 그 패널은 죽은 것으로 봄. `ready` 응답은 `src` 로 보내니 `null` 에서 `TypeError` 없음

### 3.2 빈도 상한

`rate` 는 패널마다 새로 만드는 작은 계수기입니다(2절 표의 숫자).

- `ready`: 정상 결과물은 로드마다 1번. 패널 수명 동안 **2번까지**(새로 고침 1번, 첫 번째로부터 1초 뒤부터).
  더 새로 고치면 스냅숏 없이 500ms 뒤 메모리 모드로 시작(7절 `init`), 패널을 다시 열면 계수기 초기화
- `put`: 최근 1초 창에 **20개까지**. 웹워들은 한 번 입력에 `put` 2~3개라 여유가 큽니다. 넘치면 버림
- 스냅숏은 `getItem`+`JSON.parse` 를 매번 하지 않고 메모리 사본 `dict` 를 보냅니다. 넘친 메시지도
  리스너는 불리지만 버리는 비용이 계수기 비교 하나라 화면이 굳지 않습니다. 큐를 끊으려면 패널을 닫습니다

### 3.3 읽기·쓰기 규칙

- **읽기 (`loadPart`)**: `getItem` → `JSON.parse` 를 `try/catch` 로 감싸고, 결과가 평범한 객체가
  아니면 빈 칸. 그다음 `Object.keys(parsed)` 중 `okKey`·`okVal` 을 지나는 것만 **`Map`** 에 옮깁니다.
  이후 존재·개수는 `dict.has`·`dict.size` 로만 봅니다. `in`·`dict[key]`·`dict.hasOwnProperty` 를 쓰지
  않으므로 `constructor`·`hasOwnProperty`·`toString` 같은 키가 와도 그냥 문자열 키입니다
- **쓰기 (`putIfFits`)**: `Map` 에 반영해 본 칸을 `JSON.stringify(Object.fromEntries(dict))` 로 재고
  (2절), 키 수나 길이가 넘으면 되돌리고 버립니다. 반영되면 250ms 묶음 타이머를 겁니다
- **내보내기 (`flushPut`)**: `localStorage.setItem` 을 `try/catch` 로 감쌉니다. `QuotaExceededError`
  등으로 실패하면 **그 쓰기만 버리고**(메모리 `dict` 는 남아 같은 패널 안에서는 계속됨) 콘솔에 한 줄
  경고 후 정리를 계속합니다. 정리 코드가 중간에 끊기지 않게 하는 것이 목적입니다
- 모니터는 값을 **파싱하지도, 화면에 그리지도 않습니다.** 나중에 기록을 보여 주는 기능을 더하면
  "저장값이 닿는 DOM 경로 없음"(T-153 점검 7) 판단이 무효가 되므로 그때 새로 검토합니다

- **`event.source` 가 주된 검사입니다.** 불투명 출처는 `origin` 이 언제나 문자열 `"null"` 이라
  `origin` 만으로는 "어느 격리 칸인지"를 전혀 가리지 못합니다 - 세상의 모든 sandbox iframe,
  `data:` 문서가 다 `"null"` 입니다. 그래서 `origin === "null"` 은 **신원 확인이 아니라 격리가
  유지되는지의 확인**으로만 씁니다(누가 실수로 `allow-same-origin` 을 붙이면 길이 닫힘).
  신원은 `ev.source === fr.contentWindow` 로 봅니다. 이것은 이 패널의 지역 변수 `fr` 과의
  **객체 동일성 비교**라 메시지 내용으로 위조할 수 없습니다. 결과물 안의 중첩 iframe·팝업이
  `top.postMessage` 를 불러도 `source` 가 그 창이라 걸립니다
- 보내는 쪽 `targetOrigin` 이 `'*'` 인 이유: 불투명 출처는 지정할 이름이 없습니다(`"null"` 은
  `targetOrigin` 으로 쓸 수 없음). 대신 **받는 창을 `ev.source` 로 못박고**, 보내는 것은 그 칸 몫의
  스냅숏뿐이라 받는 이가 누구든 이미 그 칸 안의 코드입니다(6절 (d))
- 결과물 쪽은 `parent.postMessage(m, new URL(location.href).origin)` 으로 보냅니다. 문서 출처는
  `"null"` 이지만 URL 의 출처는 모니터 호스트라, 부모가 모니터가 아니면 배달되지 않습니다
- 키 허용은 **꼴 허용 목록**(정규식)입니다. 웹워들 키 이름을 모니터에 박지 않습니다 - 모니터는
  여러 프로젝트를 띄우고, 막아야 할 것은 "다른 칸·모니터 자기 키에 닿기"이지 키 이름 자체가
  아니기 때문입니다. `__proto__` 같은 이름은 첫 글자 규칙에서 걸리고, 칸은 쓸 때도 읽을 때도
  `Map` 으로 다룹니다(3.3)
- 쓰기는 250ms 묶어서 `localStorage.setItem` 한 번. 상한을 넘는 `put` 은 **조용히 버립니다**
  (결과물의 `memory` 에는 남아 판은 계속됨). 패널을 닫을 때 리스너를 떼고 밀린 쓰기를 내보내는
  것은 3.1 의 정리 훅이 합니다

**왜 이것으로 충분한가** - 핸들러가 하는 일은 "고정된 접두 + 모니터가 쥔 이름" 아래의 문자열
사전 하나를 읽고 고치는 것뿐입니다. 메시지 내용은 **어떤 URL·DOM·`fetch`·`eval` 에도 닿지 않고**,
`localStorage` 의 키 이름도 되지 않습니다(사전 안의 필드일 뿐). 그러니 검사할 것은 "어느 칸인가
(`source`)"와 "얼마나 큰가(길이·개수)" 둘로 닫힙니다.

## 4. 프로젝트끼리 섞이지 않게

- 모니터 `localStorage` 에 **프로젝트마다 키 하나**: `aimem.app.v1.<encodeURIComponent(이름)>`,
  값은 `{키: 문자열}` JSON. 웹워들은 `aimem.app.v1.%EC%9B%B9%EC%9B%8C%EB%93%A4`
- 이름은 `pr.name` - 서버 `/api/projects` 가 준 목록의 그 항목이고, 서버는 `_PROJECT_RE`
  (`server.py:1732`)를 지난 폴더만 내줍니다. **메시지에는 프로젝트 이름 필드가 아예 없습니다**
- `../` 가 무의미한 이유: `localStorage` 키는 경로가 아니라 평평한 문자열이고, 비교는 완전 일치입니다.
  `encodeURIComponent` 는 단사(서로 다른 이름 → 서로 다른 결과)이고 `/` 를 `%2F` 로 바꾸므로
  어떤 이름도 다른 이름의 접두+구분자를 흉내 낼 수 없습니다. 메시지의 `key` 는 사전 안에만
  들어가니 `../stats` 가 와도 정규식에서 걸리고, 지났다 해도 같은 칸 안의 필드 이름일 뿐입니다
- 모니터 자기 설정 키(접두가 `aimem.app.` 이 아닌 것)는 결과물이 이름을 고를 수 없으니 닿지 않습니다

## 5. 어디에 남기나

**모니터 페이지의 `localStorage`(브라우저별)** 로 합니다. 서버는 고르지 않습니다.

- 장점: 새 API·인증·디스크 쓰기가 없습니다. `create_request` 가 "서버가 쓰는 유일한 파일"이라는
  지금의 성질도 그대로입니다
- 대가: 브라우저·기기마다 기록이 따로입니다. 모니터 쿠키/사이트 데이터를 지우면 함께 지워집니다.
  `serve.py` 로 띄운 웹워들(자기 출처의 `localStorage`)과도 **공유되지 않습니다** - 둘은 다른 칸입니다
- 용량: 프로젝트당 **직렬화 기준** 64 KiB 상한(2절)이라 모니터 출처의 약 5 MiB 몫을 결과물들이
  다 먹지 못합니다. 프로젝트가 수십 개여도 모니터 자기 키 자리가 남습니다. 그래도 몫이 차서
  `setItem` 이 실패하면 그 쓰기만 버립니다(3.3) - 모니터 자기 키(`aimem-theme`) 쓰기는 이 길과 무관합니다

## 6. 새 길이 생기지 않는다는 근거

설계 뒤에도 결과물 JS 의 출처는 그대로 `"null"` 이고, 새로 얻는 것은 "자기 칸 문자열 사전에 대한
읽기·쓰기" 하나뿐입니다.

- **(a) 모니터 API 를 부를 수 없다** - 막는 것: ① CSP `connect-src 'self'` 의 `'self'` 는 불투명 출처라
  사실상 모니터 호스트만, ② 세션 쿠키가 `SameSite=Strict` (`server.py:2420`)라 불투명 출처발 요청에
  실리지 않음 → `/api/` 는 401, ③ `/api/` 응답엔 `Access-Control-Allow-Origin` 이 없어 읽지도 못함
  (`ACAO: null` 은 `/app/` 파일에만, 2645행). 이 설계는 셋 중 무엇도 건드리지 않고, 메시지 핸들러는
  `fetch` 를 대신 불러 주지 않습니다(**대리 호출 금지**가 구현 규칙입니다)
- **(b) 세션 쿠키를 읽을 수 없다** - 쿠키는 `HttpOnly`(2420행)라 같은 출처여도 JS 로 못 읽고,
  불투명 출처는 `document.cookie` 자체가 `SecurityError`. 스냅숏에는 그 칸 사전만 담고 모니터의
  다른 `localStorage` 키·쿠키·토큰을 담지 않습니다
- **(c) 실행 티켓을 얻을 수 없다** - 자기 티켓은 이미 자기 URL(`/app/~<티켓>/<이름>/`)에 있으니
  새 것이 아닙니다. 다른 프로젝트 티켓은 `/app/<이름>/` 의 서명(2622-2634행)이 세션을 요구하는데
  (b)·(a)의 이유로 세션이 실리지 않습니다. 모니터는 메시지에 URL·티켓을 **보내지 않습니다**
- **(d) 다른 프로젝트 기록을 읽거나 쓸 수 없다** - 칸은 `ev.source === fr.contentWindow` 로 고르고,
  그 `fr` 은 모니터가 `pr.name` 으로 만든 것입니다. A 의 코드가 B 칸에 닿으려면 **B 패널의 iframe
  안에서 돌아야** 하는데, sandbox 의 "navigation 금지" 플래그 때문에 A 는 자기와 자기 자손 말고는
  (부모·형제·`top` 모두) 이동시킬 수 없습니다(`allow-top-navigation` 없음)

**가장 아슬아슬한 것 - (d) 의 "칸은 창에 묶이지, 문서에 묶이지 않는다".** `fr.contentWindow` 는
iframe 이 **스스로 다른 곳으로 이동해도 같은 객체**입니다. 그래서 A 의 칸 안에서 A 가 고른 문서
(외부 사이트든 `/app/~<B티켓>/B/` 든)가 돌면 그 문서가 **A 칸**을 읽고 씁니다. 이것이 새 구멍이
아닌 이유는 그 문서를 들인 것이 A 자신이고, A 는 지금도 `location = 'https://x/?' + 자기기록` 으로
자기 기록을 내보낼 수 있기 때문입니다(CSP 는 이동을 막지 않음). 즉 A 칸이 새는 것은 A 의 선택
범위 안입니다. **이동해 온 문서는 A 칸을 읽을 뿐 아니라 `put` 으로 A 칸을 지우거나 덮어쓸 수도
있습니다.** A 가 `ready` 를 보낸 직후 이동하면 `snapshot` 도 이동한 문서가 받습니다. 이것은
의도된 동작입니다 - 칸의 주인은 "A 패널 창" 이고, 그 창에 무엇을 들일지는 A 가 정하며, 이동한 문서가
얻는 것은 A 가 이미 가진 것(A 칸)뿐입니다. 시험으로 고정합니다(7절). **B 칸**은 B 패널 iframe 에만
묶여 있어 A 가 닿지 못합니다. 단 이 논증은
"A 가 B 의 새 티켓을 얻지 못한다"((c))에 기대므로, 구현 때 **티켓 발급에 `Sec-Fetch-Site` 가
`same-origin`·`none` 일 때만**이라는 검사를 더해 쿠키 동작에만 기대지 않게 하기를 권합니다(9절).

## 7. 무엇이 바뀌나

| 파일 | 줄 수 감 | 내용 |
|---|---|---|
| `tools/aimem_monitor/static/app.js` `openPanel`·`closeDetail` | +12 | 3.1: `state.panelCleanups` 와 `runPanelCleanups()`, 두 함수 첫 줄에서 호출. 다른 패널의 동작은 바뀌지 않음 |
| `tools/aimem_monitor/static/app.js` `openProjectApp` | +75 | 리스너(3절, `!src`·`isConnected` 검사), `rate` 계수기(3.2), `Map` 칸 읽기·직렬화 길이 검사·`try/catch` 쓰기(3.3), 정리 함수 등록(`removeEventListener`·`flushPut`·`fr.remove()`), 안내 문구(2849행) "기록은 이 브라우저에 남습니다" 로 |
| `projects/웹워들/web/js/storage.js` | +35 | `export async function init()`: `localStorage` 가 되면 그대로, 안 되고 `parent !== self` 면 `ready` 보내고 스냅숏을 최대 500ms 기다려 `memory` 를 채움. `write`/`remove` 는 부모 모드일 때 `put` 도 보냄. `daily.*` 중 오늘이 아닌 것은 `init` 때 지움(키 64개 상한 대비) |
| 웹워들 진입 모듈 (이번에 읽지 않음) | +3 | 첫 `loadSettings()` 전에 `await init()` |
| `tools/aimem_monitor/server.py` | 0 (권하는 +6) | 길 자체엔 필요 없음. 권하는 것: 티켓 발급 전 `Sec-Fetch-Site` 검사(6절 끝) |
| 웹워들 `PROGRESS.md` · `README.md` | 문구 | R10 "알아 둘 것" 갱신 |

필요한 검사(목록만):

- 브라우저: 미리보기에서 한 판 이기고 새로 고침 → 통계 1판 남음, 도움말 다시 안 뜸, 설정 유지
- 브라우저: 프로젝트 둘을 번갈아 열어 칸이 섞이지 않음(가짜 두 번째 프로젝트로)
- 브라우저: iframe 안 중첩 iframe·팝업에서 보낸 `put` 이 무시됨(`source` 검사)
- 브라우저(결함 1): B 를 열었다 닫고 A 를 엶 → A 의 **일시 중첩 iframe**(보내고 같은 태스크에서 제거)이 보낸
  `put` 이 B 칸 불변, `ready` 에 `TypeError` 없음, 닫은 뒤 iframe 이 DOM 에 없음. 버려진 창의 `ev.source === null` 도 실측
- 브라우저(결함 2·3·4): `ready`·`put` 루프에도 화면 응답, 반영 `put` ≤20/초·스냅숏 ≤2번 / `"` 로만 된 8,192자 값
  8개가 직렬화 상한에서 끊김, `setItem` 이 던져도 닫기 정리 완료 / 키 `hasOwnProperty`·`constructor` 뒤에도 `put` 정상
- 브라우저(결함 5): A 가 `ready` 후 자기 칸을 다른 문서로 이동 → 그 문서의 `put` 이 **A 칸**에 쓰임(의도), B 칸 불변
- 브라우저: `aimem` 다름 / `op` 모름 / 키 꼴 위반 / 8,193자 / 65번째 키 / 객체 값 → 전부 무시, 모니터 오류 없음
- 브라우저: 결과물이 `__proto__`·`../x` 키로 `put` 해도 모니터의 다른 `localStorage` 키 불변
- 브라우저: 부모 없음("새 탭에서 열기")·스냅숏 무응답에서도 500ms 뒤 게임 시작(지금 동작 유지)
- 회귀: `browser_monitor_app.py` · `browser_monitor_auth.py` 기존 통과, 결과물에서 `/api/` 401 유지
- `node --test`: `storage.js` 부모 모드 단위 시험(가짜 `parent`)

## 8. 고르지 않은 길과 그 이유

1. **같은 출처로 띄우기(`allow-same-origin`)** - `localStorage` 가 바로 되지만 결과물 JS 가 모니터 출처가
   되어 세션 쿠키가 실린 `fetch('/api/...')` 를 부르고 응답을 읽습니다. R10 적대적 검수 결함 2 그대로
   입니다. `allow-scripts` + `allow-same-origin` 조합은 결과물이 자기 sandbox 속성을 떼어 낼 수도 있어
   격리가 통째로 무의미해집니다
2. **서버에 저장(`/api/app-store/<이름>`)** - 기기 사이에 기록이 이어지는 장점은 있지만, 결과물이
   부를 수 있는 모니터 API 가 처음으로 생깁니다. 불투명 출처는 쿠키를 못 싣으니 티켓으로 인가해야
   하고, 그러면 **12시간짜리 티켓이 쓰기 권한**이 됩니다(로그에서 가리는 것 이상의 관리 필요).
   디스크 용량·동시 쓰기·누가 지우나도 새로 정해야 합니다. 얻는 것에 비해 공격면이 큽니다
3. **`MessageChannel` 포트 넘겨주기** - 첫 포트를 넘길 때도 결국 `fr.contentWindow.postMessage(…, '*')`
   이고 신뢰의 뿌리는 같습니다. 포트가 iframe 이동 뒤에도 살아남아 6절의 "창에 묶임" 문제가
   오히려 흐려집니다. 단순한 `source` 비교가 검토하기 쉽습니다
4. **결과물별 서브도메인(`웹워들.apps.host`)** - 진짜 출처 분리라 가장 깨끗하지만 DNS·TLS 인증서·
   `_app_host_allowed` 를 손봐야 하고 `localhost` 개발 흐름이 깨집니다. 이 저장소 규모엔 과합니다

## 9. 남은 물음

- **불투명 출처가 시작한 하위 프레임 이동에 `SameSite=Strict` 쿠키가 정말 안 실리는가** -
  `server.py:2489` 주석은 그렇다고 하지만 브라우저별 실측이 없습니다(크로미움은 이동 개시자를 보고,
  다른 엔진은 조상만 볼 수 있음). 실리면 A 가 자기 칸을 `/app/B/` 로 옮겨 B 티켓을 받을 수 있습니다
  (그래도 B 의 코드가 A 칸에서 돌 뿐 B 칸은 안전 - 6절). `Sec-Fetch-Site` 검사를 넣을지 함께 정할 것
- **opt-in 을 둘까** - `app.json` 에 `"storage": "parent"` 를 적은 프로젝트에만 리스너를 걸면 표면이
  더 작아집니다. 그러면 `server.py` `project_app` 이 그 필드를 통과시켜야 합니다(+5줄)
- **스냅숏 대기 500ms** 가 체감상 괜찮은지, 진입 모듈이 `await` 를 받아들이는 구조인지 (진입 모듈은 이번에 읽지 않음)
- 미리보기 칸과 `serve.py` 칸이 따로인 것을 사용자에게 어떻게 알릴지(안내 문구로 충분한가)
- 같은 프로젝트 패널을 두 탭에서 열었을 때 나중 쓰기가 이깁니다. `storage` 이벤트로 맞출지는 미정
- 칸 상한(64키·64 KiB)을 넘을 때 결과물에 알릴지(지금 설계는 조용히 버림)

## 검토 반영 (R12 T-153 -> T-158)

- **결함 1 (높음)** - 3절 코드 첫 줄을 `if (!src || src !== fr.contentWindow || !fr.isConnected) return;` 로 바꾸고 `ready` 응답도 `src` 로 보냄. 3.1 을 새로 써서 `openPanel`·`closeDetail` 첫 줄의 `runPanelCleanups()` 로 리스너 떼기·쓰기 내보내기·`fr.remove()` 를 하게 함(`closeDetail` 이 iframe 을 숨기기만 한다는 점도 짚음). 7절 표에 `openPanel`·`closeDetail` 행을 올리고, 시험에 "B 열고 닫음 → A 의 일시 중첩 iframe `put` 이 B 칸 불변" 을 넣음
- **결함 2 (중간)** - 2절 표에 빈도 행(`ready` 패널 수명당 2번·1초 간격, `put` 1초에 20개)을 넣고, 3.2 에서 계수기와 "스냅숏은 `load` 대신 메모리 사본 `dict`" 를 규정함. 시험 한 줄을 더함
- **결함 3 (낮음)** - 2절 표와 그 아래 문단에서 상한을 `JSON.stringify(칸)` 길이(UTF-16 단위)로 재도록 바꿈. 3.3 `flushPut` 에서 `setItem` 을 `try/catch` 로 감싸 실패하면 그 쓰기만 버리고 정리를 계속하게 함. 5절 용량 문단과 시험을 맞춤
- **결함 4 (낮음)** - 3.3 `loadPart` 에서 읽은 객체를 `okKey`·`okVal` 를 지난 키만 `Map` 으로 옮기고 `has`/`size` 만 쓰게 함. 3절 본문의 "`Object.create(null)`" 서술을 `Map` 으로 고침. 검토가 낸 `Object.assign(Object.create(null), parsed)` 대신 `Map` 을 고른 이유: `Map` 은 키 이름과 메서드가 섞이지 않아 `dict.hasOwnProperty` 같은 실수가 구조상 생기지 않음
- **결함 5 (낮음)** - 6절 "가장 아슬아슬한 것" 에 "이동한 문서가 `put` 으로 A 칸을 지우거나 덮어쓰고, `ready` 직후 이동하면 `snapshot` 도 그 문서가 받는다. 의도된 동작이다" 를 더하고, 7절 시험으로 고정함. 코드 변경은 없음
- 검토 점검 7 의 "모니터가 값을 그리지 말 것" 권고는 3.3 마지막 줄에 규칙으로 넣음. 점검 8 의 `Sec-Fetch-Site` 를 "권장" 에서 "규칙" 으로 올리라는 권고는 **이번에 반영하지 않음** - 지시 범위(결함 1~5)를 벗어나고 `server.py` 변경 여부는 9절 남은 물음으로 관리자가 정할 일이라 그대로 둠
