# R54 조사 - 옵션 칸 '기본값 읽기' 장치와 그 표준 방식 (R53-N7·N9·N10, 구현하지 않음)

대상: `projects/VoxLog/web/app.js` 의 `sttDefaults`·`state.sttDefaults`·`state.sttDefaultsReq`·`state.sttSeq`·
손으로 만든 15초 `setTimeout`·`setSttFieldsBusy`·`loadSttSettings`·`openSttPanel`·`saveSttDefaults`,
그리고 `web/api.js` 의 `json()`. 원문 지적은 `rounds/R53/REVIEW-r53-2.md`(N7·N9), `rounds/R53/REVIEW-r53-3.md`(N10).
코드는 고치지 않았다. 이 문서는 조사와 권고만 담는다.

- 끝난 기준: `## 권고` 절이 있다.
- 한 줄 결론: **바꾸는 쪽이 소스가 단순해진다.** 손으로 만든 "한 벌 캐시 + 단일 비행 약속 + 수동 settle +
  늦은 응답 신원 검사"를 묶음별 `AbortController` 하나로 줄이면 N7·N9 가 사라지고 약 −17줄이 된다.
  N10 은 이 방식으로 닫히지 않는다(닫으려면 캐시를 되살려야 함) - 하 등급이므로 남긴다.

---

## 1. 지금 장치

### 1.1 조각과 줄 번호

| 조각 | 위치 | 하는 일 |
|---|---|---|
| `state.sttDefaults` | `app.js:30` | 한 벌 캐시. 서버에서 받은 마지막 기본값(dict 또는 `{}`). **화면을 그리는 데는 아무도 쓰지 않는다** - 오직 "이미 읽었나" 판정용 |
| `state.sttDefaultsReq` | `app.js:31` | 지금 걸려 있는 읽기 약속(단일 비행). 두 묶음이 같은 약속을 공유한다 |
| `state.sttSeq` | `app.js:33~34` | 묶음별 열기 번호. 응답 처리기가 "내 번호"일 때만 채우고 푼다(R53-N6) |
| `setSttFieldsBusy` | `app.js:231~242` | 다섯 칸과 단추의 `disabled` 를 켜고 끈다. 잠금 장치 |
| `sttDefaults()` | `app.js:268~298` | 캐시 있으면 즉시 반환 → 걸린 약속 있으면 그것 반환 → 없으면 새 `Promise` 를 만들고 15초 타이머를 건다. `settle()` 이 타이머를 지우고 `sttDefaultsReq` 를 비운다 |
| `loadSttSettings` | `app.js:300~329` | 설정 칸을 열 때. 캐시를 비우고(`:311`), 번호를 올리고(`:312`), 잠그고(`:313`), 읽어서 채운다 |
| `saveSttDefaults` | `app.js:331~347` | `PUT api/stt-options`. **잠그지 않는다**. 응답의 옵션을 캐시에 넣고 칸을 되돌려 쓴다(`:339~340`) |
| `openSttPanel` | `app.js:349~391` | 상세 칸 열기/닫기. 열 때 캐시를 비우고(`:366`) 녹음 옵션이 있으면 읽지 않고 바로 채운다(`:367~373`) |
| `retryWithOptions` | `app.js:393~425` | 재시도 POST. `state.sttSeq.detail` 을 응답 가드로 쓴다(`:400·404·414`) |
| `api().json` | `api.js:58~83` | `fetch(url, {method, headers, cache:'no-store'})`. **`signal` 을 받지 않는다** |
| 호출부 | `app.js:1287~1288`(`openDetail`), `app.js:1309~1310`(`closeDetail`), `app.js:1640~1643`(설정 단추·저장 단추·옵션 단추 배선) | 이동/닫기 때 번호를 올리고 잠금을 푼다 |

### 1.2 흐름 (한 번 열 때)

1. 캐시를 `null` 로 버린다 → 2. 번호를 올린다 → 3. 다섯 칸·단추를 잠그고 `불러오는 중…` 을 쓴다 →
4. `sttDefaults()` - 캐시가 없고 걸린 요청이 없으므로 새 `Promise` + 15초 타이머 →
5. 응답: 번호가 같으면 잠금을 풀고, 칸이 아직 열려 있으면 채운다. 실패: 잠금을 풀고 까닭 한 줄.
6. 15초가 먼저 지나면 `settle()` 후 거절. 그 뒤 도착한 응답은 `state.sttDefaultsReq !== req` 라 버려진다(`:286`).

이 장치가 하는 일은 결국 하나다 - **"지금 열린 칸을 채울 자격이 있는 응답은 어느 것인가"**. 그것을 캐시·약속 신원·
번호·타이머 네 가지로 나눠 표현한 것이 지금 모양이고, R51-N6·R53-N1·R53-N6 세 번의 수정이 모두 이 자리였다.

---

## 2. 표준 방식 후보와 출처

### 2.1 요청 취소 - `AbortController` / `AbortSignal`

`fetch` 에 `signal` 을 넘기면 `controller.abort()` 로 요청을 중단할 수 있고, 중단된 `fetch` 는 `AbortError` 로
거절된다. "새로 열면 앞 요청을 취소한다"는 이 장치의 표준 해법이다.

- MDN AbortController - <https://developer.mozilla.org/en-US/docs/Web/API/AbortController>
  ("`abort()` ... able to abort fetch requests, consumption of any response bodies, and streams")
- WHATWG DOM 규격 - <https://dom.spec.whatwg.org/#interface-abortsignal>

취소하는 쪽이 **누가 새 주인인지**를 정한다: 앞 요청을 `abort()` 한 뒤 새 요청을 걸면, 낡은 응답은 애초에 도착하지
않으므로 "늦은 응답이 사람이 고른 값을 덮는" 경로가 네트워크 층에서 끊긴다.

**시간 제한**은 두 가지 표준이 있다. 둘 다 이 앱의 지원 기준 밖이다(2.4 표).

- `AbortSignal.timeout(ms)` - <https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static>
- `AbortSignal.any([a, b])` - <https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/any_static>
  (사용자 취소 신호와 시간 초과 신호를 합치는 표준 조합. MDN 예제가 정확히 그 모양이다)

그래서 지금 지원 기준 안에서 같은 일을 하려면 **손 타이머 + `ac.abort()`** 가 표준에 가장 가까운 형태다.
`setTimeout(function () { timedOut = true; ac.abort(); }, 15000)` 정도이며, `timedOut` 깃발이 필요한 까닭은
Chrome 124 미만의 `AbortSignal.timeout` 이 `TimeoutError` 가 아니라 `AbortError` 로 끊는 것과 같은 이유다
(BCD `timeout_static` 의 `partial_implementation` 주석). 즉 어차피 "취소인지 시간 초과인지"는 직접 구분해야 한다.

**이 저장소에 이미 있는 관례**와 같다 - `web/queue.js:504` 가 `try { ac = new AbortController(); } catch (e) { return; }`
로 만들고, `queue.js:516` 이 `if (e && e.name === 'AbortError') return;` 로 조용히 넘긴다. 새 개념이 아니다.

### 2.2 잠금 - `<fieldset disabled>`

- MDN `<fieldset>` - <https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/fieldset>
  ("all form controls that are descendants of the `<fieldset>` are disabled ... They won't receive any browsing
  events, like mouse clicks or focus-related events")

지금의 `setSttFieldsBusy`(다섯 칸 배열 순회 + 단추 하나)를 `fieldset.disabled = true` 한 줄로 바꾸는 것이 표준이다.
다만 **이 화면 구조에서는 이득이 작다**: 두 묶음의 칸은 `<div id="stt-defaults-fields">`·`<div id="detail-stt-fields">`
안에 있고(`index.html:36`·`:154`), 단추·상태 글은 그 div **밖**의 `.row` 에 있다(`index.html:37~40`·`:157~160`).
fieldset 으로 묶으려면 `index.html` 두 곳의 구조를 바꾸고, fieldset 기본 테두리·여백을 CSS 로 지워야 한다
(320px 폭에서 겹치지 않는다는 조건이 `docs/INTERFACE.md:472` 에 있다). 게다가 시험 두 개가 깨진다(4.2).

### 2.3 캐시 갱신 - stale-while-revalidate / 쿼리 캐시

표준 라이브러리들이 쓰는 모양은 이렇다.

- 값은 **키 하나**의 캐시에 두고, 열 때는 캐시를 즉시 보여 준 뒤(잠금 없음) 뒤에서 새로 읽는다(stale-while-revalidate).
- 새로 읽기는 **앞 읽기를 취소하고** 시작한다. 걸린 요청에 "합류"하지 않는다.
- 저장(PUT)은 관련 읽기를 **취소하고**, 성공 응답을 캐시에 바로 쓴다(query invalidation / mutation response).
- 관찰자가 사라진 뒤 도착한 응답은 **버리지 않고 캐시에 넣는다** - 다음 열기가 그 값을 쓴다.
  TanStack Query 문서가 기본 동작으로 이렇게 적는다: "queries that unmount or become unused before their
  promises are resolved are not cancelled ... the resulting data will be available in the cache"
  - <https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation>

VoxLog 자신도 이미 이 패턴을 안다: `web/sw.js:33~46` 의 앱 껍데기 처리가 network-first + 캐시 갱신(SWR)이다.

### 2.4 지원 판 (이 앱의 기준과 견주어)

이 앱의 문서화된 기준은 "웹 잠금 Chrome 69+ / Firefox 96+ / Safari·iOS 15.4+, 없으면 열화"
(`README.md:53`, `docs/RESEARCH-draft-owner.md:31~39` 의 BCD 표)이다.

| API | Chrome / Android | Safari / iOS | 이 앱 기준 안인가 |
|---|---|---|---|
| `AbortController`·`AbortSignal` | 66 / 66 | 11.1 / 11.1 | **안** (여유 있음) |
| `AbortSignal.timeout()` | 103 (124 전은 `AbortError` 로 끊음) | 16 / 16 | **밖** (iOS 15.4 미달) |
| `AbortSignal.any()` | 116 | 17.4 / 17.4 | **밖** (한참 밖) |
| `<fieldset disabled>` | 아주 오래됨(Baseline 2015-07) | 같음 | 안 |

출처: BCD 원본 <https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/AbortSignal.json>
(`any_static`·`timeout_static` 항목의 `version_added`), MDN 두 문서의 Baseline 표시.

---

## 3. 표준 방식으로 바꾸면 N7·N9·N10 이 사라지는가

### 3.1 요약

| 지적 | abort 방식(권고안) | SWR 방식(캐시 유지 + 잠금 제거) |
|---|---|---|
| N7 (저장 잠금 없음·글 덮음·GET 이 PUT 앞지름) | **사라짐** (+4줄) | 사라짐 |
| N9 (안 읽는 길에서 캐시 비움·걸린 읽기 재사용) | **사라짐** (캐시를 지우므로) | 사라짐 (캐시를 안 비우므로) |
| N10 (15초 넘은 정상 응답 버림·백그라운드 복귀) | **남음** | 사라짐 |

### 3.2 N7 - 사라진다

세 갈래 모두 표준 패턴이 직접 덮는다.

- (a) 저장 중 사람이 값을 바꾸면 응답이 되돌려 씀 → `saveSttDefaults` 도 `setSttFieldsBusy(…, true)` 로 잠근다(2줄).
- (b) `저장 중…` 과 `불러오는 중…` 이 서로 덮음 → **저장이 걸린 읽기를 abort 한다**. 끊긴 읽기의 처리기는
  `AbortError` 를 보고 아무 글도 쓰지 않고 돌아가므로(`queue.js:516` 과 같은 관례) `저장 중…` 이 살아남는다.
- (c) GET 이 PUT 을 앞지름 → 저장 중에는 열기 읽기를 시작하지 않는다(저장 중 깃발 2줄). 저장 응답이 이미 칸을
  서버 값으로 되돌려 쓰므로(`app.js:339~340`) 저장 뒤 다시 읽을 필요도 없다.

핵심은 "잠금 + 글 한 벌"이 아니라 **취소가 소유권을 정한다**는 것이다. 지금은 GET 과 PUT 이 서로의 상태 글을
모르는 채 같은 `#stt-defaults-state` 를 쓴다.

### 3.3 N9 - 사라진다(구조적으로)

- "안 읽는 길에서도 캐시를 비우는 줄"(`app.js:311`·`:366`)은 **캐시 자체를 지우면 없어진다.**
  `state.sttDefaults` 는 화면을 그리는 데 쓰이지 않으므로(1.1 표) 지워도 잃는 것이 없다.
- "걸린 읽기 재사용"은 **재사용 대신 취소 후 새로 읽기**로 바뀐다. 두 묶음이 각자 자기 요청을 갖는다.
  대가: 설정 칸과 상세 칸을 동시에 열면 GET 이 두 번 나간다(작은 JSON 한 번 더). 대신 두 응답이 서로의 칸을
  건드릴 길이 없어져 "공유 캐시" 개념이 통째로 빠진다.

### 3.4 N10 - 남는다(그래도 권한다)

- abort 방식에서도 15초를 넘긴 응답은 **끊겨서 버려진다**. "계속 느린 회선에서는 영영 못 읽는다"는 그대로다.
- 닫는 방법은 하나뿐이다 - 늦은 응답을 **캐시에 넣고 다음 열기가 쓰게** 하는 것(2.3 의 TanStack 기본 동작).
  그런데 그것은 3.3 에서 지운 캐시를 다시 들이는 일이고, "화면은 안 건드리고 캐시만 채운다"는 규칙을 또 하나 더한다.
- 백그라운드 복귀에서 타이머가 먼저 도는 문제는 표준 API 로도 안 없어진다. `AbortSignal.timeout` 도 내부는 타이머이고,
  브라우저는 숨은 탭의 타이머를 늦춘다. 즉 "타이머가 응답보다 먼저 돈다"는 성질은 어느 방식이든 같다.
- 판단: N10 은 **하 등급이고 사용자 영향이 작다**(칸은 풀려 있고 빈 칸으로 실행 가능). 리뷰도 "기록만 해도 됨"이라고
  적었다(`REVIEW-r53-3.md:36`). 이번 변경에서 억지로 닫지 말고, 알려진 맞바꿈으로 문서에 남긴다.

---

## 4. 걷어낼 범위와 줄 수

### 4.1 권고안(abort 방식)의 모양

```js
// 묶음마다 지금 도는 기본값 읽기 하나. 열 때마다 앞 읽기를 끊고 새로 읽는다(R53-N7·N9).
sttReads: { defaults: null, detail: null },   // { ac, timer }  -  state.sttDefaults·sttDefaultsReq 를 대신한다
```

```js
// 받아쓰기 기본값 읽기. 앞 읽기는 끊는다 - 끊긴 쪽은 AbortError 로 조용히 돌아간다.
function readSttDefaults(bundle, seq, onFill, onFail) {
  var old = state.sttReads[bundle];
  if (old) { clearTimeout(old.timer); old.ac.abort(); }
  var ac;
  try { ac = new AbortController(); } catch (e) { onFail(new Error('불러오지 못했습니다')); return; }
  var timedOut = false;
  var timer = setTimeout(function () { timedOut = true; ac.abort(); }, STT_DEFAULTS_TIMEOUT_MS);
  state.sttReads[bundle] = { ac: ac, timer: timer };
  api().json('api/stt-options', { signal: ac.signal }).then(function (d) {
    clearTimeout(timer);
    if (seq !== state.sttSeq[bundle]) return;          // 번호 가드는 그대로 - 그래도 필요하다(4.3)
    onFill(optsOf(d));
  }, function (e) {
    clearTimeout(timer);
    if (e && e.name === 'AbortError' && !timedOut) return;   // 내가 끊었다 - 새 읽기가 이 칸의 주인이다
    if (seq !== state.sttSeq[bundle]) return;
    onFail(timedOut ? new Error('시간이 지났습니다') : e);
  });
}
```

`state.sttSeq`(번호)는 **지운다기보다 남긴다**. 이미 끝난 약속의 처리기가 다음 틱에 도는 경우(응답이 도착해 resolve 된
직후 `abort()` 를 부르면 취소가 먹지 않는다)를 번호가 막아 준다. `retryWithOptions`(`app.js:400·404·414`)도 같은 번호를
쓰므로 손대지 않는다. 반대로 **캐시·단일 비행·수동 settle·`sttDefaultsReq` 신원 검사**는 없어진다.

### 4.2 지울 것·남길 것·바뀔 것 (줄 수는 추정)

| 항목 | 지금 | 바꾼 뒤 | 증감 |
|---|---|---|---|
| `state.sttDefaults` (`:30`) | 1 | 없음(캐시 삭제) | −1 |
| `state.sttDefaultsReq` (`:31`) | 1 | `state.sttReads` 2키 | ±0 |
| `state.sttSeq` (`:33~34`) | 2 | 그대로 | 0 |
| `sttDefaults()` (`:268~298`) | 31 | `readSttDefaults()` 약 18 | −13 |
| `setSttFieldsBusy` (`:231~242`) | 12 | 그대로(fieldset 안 씀) | 0 |
| `loadSttSettings` (`:300~329`) | 30 | 약 25 (캐시 비우기·결과 공유 문구 삭제) | −5 |
| `saveSttDefaults` (`:331~347`) | 17 | 약 21 (저장 잠금 2 + 저장 중 열기 막기 2) | +4 |
| `openSttPanel` (`:349~391`) | 43 | 약 38 | −5 |
| `openDetail`·`closeDetail` (`:1287~1288`·`:1309~1310`) | 6 | 8 (abort 2줄 추가) | +2 |
| `api.js` `json()` (`:58~83`) | — | `if (opts.signal) init.signal = opts.signal;` | +1 |

합계 **약 −17줄**(app.js −18, api.js +1). 줄 수보다 큰 변화는 개념 수다: 네 가지(캐시·단일 비행·수동 settle·
늦은 응답 신원 검사)가 하나(묶음별 진행 중 요청)가 된다.

### 4.3 검사 50·62·66~69 중 바뀔 것

| 검사 | 보는 것 | abort 방식에서 | 할 일 |
|---|---|---|---|
| 50 (`tests/browser_voxlog.py:2118`) | 클릭 직후 다섯 칸·실행 단추의 `.disabled` 와 `불러오는 중…` | **그대로 통과** - 여전히 `.disabled` 를 켠다 | 없음 |
| 62 (`:2815`) | 닫았다 열면 다른 기기의 PUT 값이 반영 | 통과 - 열 때마다 새 GET 이 나간다 | 없음 |
| 66 (`:3002`) | 설정 칸 잠금 + 풀린 뒤 고른 값이 PUT 본문에 실림 | 통과 | 없음 |
| 67 (`:3049`) | A 의 기본값 GET 응답을 쥔 채 B 로 옮겨도 B 칸이 유지 | **깨진다** | 아래 설명 |
| 68 (`:3105`) | 500 이면 칸이 풀리고 실패 글 | 통과 (`AbortError` 가 아니다) | 없음 |
| 69 (`:3155`) | `page.clock` 으로 15초를 넘기면 풀림 + `시간이 지났습니다` | 손 타이머면 통과 | 손 타이머를 유지할 것 |

**67 이 깨지는 까닭**: 쥐는 장치(`STT_OPTIONS_HOLD_JS`, `:192`)는 `window.fetch` 를 감싸 실제 요청을 미뤄 두었다가
`__releaseSttOptions()` 때 `orig(h.input, h.init)` 로 보낸다(`:203~205`). 이동하면서 그 요청의 `AbortController` 를
끊으면, 놓는 순간의 `fetch` 가 이미 abort 된 신호로 즉시 거절되어 `__releasedFetchDone`(`:204`)이 서지 않는다.
67 은 그 깃발을 5초 기다리므로(`:3095`) 실패한다. 고치는 법은 둘 중 하나다.

- 쥐는 장치에 "끊겼음"을 남기게 한다(`h.init.signal && h.init.signal.aborted` 를 `__releasedFetchAborted` 로 기록).
- 67 의 마지막 절반을 "놓아도 B 칸이 그대로다"로 바꾸고, 이동이 A 의 읽기를 **끊었다**는 단언을 새로 넣는다.

**69 는 손 타이머를 유지해야 한다.** `page.clock.install()` 은 페이지의 `setTimeout` 을 갈아 끼우지만
`AbortSignal.timeout()` 은 브라우저 내부 타이머라 밀리지 않는다. `AbortSignal.timeout` 을 쓰면 69 는 실제 15초를
기다려야 하고, 어차피 2.1·2.4 때문에 지원 기준 밖이다.

### 4.4 검사 50·62·66~69 밖에서 같이 고칠 문서

- `docs/INTERFACE.md:457` 의 "저장 뒤 `state.sttDefaults` 를 갱신한다" - 캐시가 없어지므로 문장을 바꾼다.
- `docs/INTERFACE.md:456~457` 의 "열 때 `GET` 으로 채우고" 는 그대로 맞다. 잠금·`불러오는 중…` 서술도 그대로다
  (권고안은 잠금을 없애지 않는다).
- `web/sw.js` 의 `VERSION` 을 올린다(현재 20). 이 저장소는 껍데기 파일을 고칠 때마다 올려 왔다
  (`git log --oneline -- web/sw.js`: 15→16 이 R52 커밋에 함께 들어 있다).

---

## 5. 걸리는 점

1. **`api.js` 의 `fetch` 에 signal 을 넘기는 길** - `json(path, opts)` 는 `init` 을 직접 만든다(`api.js:60~65`).
   `if (opts.signal) init.signal = opts.signal;` 한 줄이면 된다. `audioUrl`(`:85`)은 이 장치와 무관하므로 두지 않는다.
   `json` 은 먼저 `getConfig()` 를 거치므로(`:59`), 그 사이에 끊기면 `fetch` 가 이미 abort 된 신호로 즉시 거절된다 - 문제없다.
2. **크롬 안드로이드·사파리 iOS 지원 판** - `AbortController` 는 Chrome 66 / Safari 11.1 이라 이 앱 기준(Chrome 69,
   iOS 15.4) 안이다. `AbortSignal.timeout`(Chrome 103·Safari 16)과 `AbortSignal.any`(Chrome 116·Safari 17.4)는
   **밖이라 쓰지 않는다.** `new AbortController()` 자체를 `try/catch` 로 감싸는 관례도 `queue.js:504` 에 이미 있다.
3. **서비스 워커** - `sw.js:38~39` 가 `/api/` 요청을 그대로 통과시키므로 abort 는 네트워크에 바로 닿는다(캐시가 끼어들지 않음).
   껍데기(`app.js`)는 network-first + 캐시 갱신이라(`sw.js:33~46`) 다음 온라인 방문에 새 파일이 실린다. 그래도 관례대로
   `VERSION` 을 올린다.
4. **`<fieldset disabled>` 를 쓰면 시험이 깨진다** - 직접 확인했다. `fieldset disabled` 안의 `input` 은
   `element.disabled` **IDL 속성이 `false` 로 남고** `:disabled` 선택자만 참이 된다. 50·66 은
   `document.querySelector('#detail-stt-' + k).disabled` 처럼 IDL 속성을 직접 읽으므로(`:2143~2149`·`:3020~3026`)
   fieldset 으로 바꾸면 그 단언이 실패한다. 반면 Playwright 의 `is_enabled` 는 fieldset 안쪽을 `False` 로 본다
   (`stt_fields_ready` 는 그대로 유효). 확인 방법과 출력은 7절에 적었다.
5. **두 GET 이 동시에 나갈 수 있다** - 설정 칸과 상세 칸을 함께 열면 요청이 두 번이다. 지금은 하나를 공유한다.
   작은 JSON 이고 각자 자기 칸만 채우므로 맞바꿀 만하다(3.3).
6. **N10 은 남는다** - 3.4. 백그라운드 복귀 시 타이머가 먼저 도는 성질도 어느 방식이든 같다.
7. **변경 범위** - `app.js`(함수 4개·상태 2개·호출부 3곳), `api.js` 1줄, `sw.js` VERSION, `tests/browser_voxlog.py` 67 하나,
   `docs/INTERFACE.md` 한 줄. `retryWithOptions`·`buildSttFields`·`fillSttFields`·`readSttFields` 는 손대지 않는다.

---

## 6. 왜 지금 모양이 세 번 고쳐졌는가 (권고의 근거)

R51-N6("열 때마다 새로 읽기") → R53-N1(잠금 추가) → R53-N6(번호·이동/닫기 풀기·15초 제한) → R53-N7·N9·N10.
매번 증상은 달랐지만 원인은 하나였다 - **"어느 응답이 이 칸의 주인인가"를 캐시·약속·번호·타이머로 나눠 표현한 것**.
네 장치가 서로의 상태를 모르니, 한 곳을 고칠 때마다 다른 곳에 틈이 생겼다(예: 캐시를 비우는 줄이 읽지 않는 길에서도
돌고, 걸린 약속은 새 열기에 재사용되고, 타이머는 정상 응답을 버린다).

표준 방식은 그 질문에 답을 하나로 준다: **요청을 끊는 쪽이 주인이다.** `AbortController` 는 "새 열기가 앞 요청을
끊는다"를, `AbortError` 무시는 "끊긴 쪽은 아무것도 하지 않는다"를, 저장 시 끊기는 "저장이 읽기를 이긴다"를 각각
한 줄로 만든다. 그래서 캐시·단일 비행·수동 settle 이 필요 없어지고, N7·N9 가 구조적으로 사라진다.

---

## 권고

**바꾼다 - 다음에 `app.js` 를 손댈 때, 4.1 모양의 `AbortController` 방식으로 한 번에.**

- **무엇을**: `state.sttDefaults`·`state.sttDefaultsReq`·`sttDefaults()`(268~298)를 지우고 묶음별
  `readSttDefaults()` 로 바꾼다. `loadSttSettings`·`openSttPanel` 은 그 함수를 부르게 하고, `saveSttDefaults` 는
  저장 중 잠금과 "저장 중에는 열기 읽기를 시작하지 않음"을 더한다. `api.js` 에 `signal` 한 줄.
- **까닭**: 기준은 "소스가 단순해지는 쪽"이다. 약 −17줄에 개념이 넷에서 하나로 줄고, N7·N9 가 사라진다.
  새 라이브러리·새 개념이 아니라 이 저장소가 `queue.js:504~516` 에서 이미 쓰는 관례다.
- **닫지 못하는 것**: N10(15초 넘은 정상 응답 버림·백그라운드 복귀). 닫으려면 캐시를 되살려야 하고, 그 캐시가
  바로 이번에 지우는 것이다. 하 등급이고 칸은 풀려 있으므로 **알려진 맞바꿈으로 남긴다.** 필요해지면 그때
  "늦은 응답은 캐시에만 넣는다"(2.3)를 따로 더한다.
- **하지 않는다**: `<fieldset disabled>`(마크업·CSS 비용 > 이득, 시험 50·66 수정 필요 - 5.4),
  `AbortSignal.timeout`/`any`(지원 판 밖 - 2.4), 잠금을 없애는 완전한 stale-while-revalidate(검사 50·66·69 와
  `INTERFACE.md:456~457` 의 계약을 다시 써야 하고, 이득은 N7 의 (b)(c) 뿐이다).
- **언제**: 급하지 않다. N7·N9·N10 은 모두 하 등급이고 사용자 영향이 작다(리뷰도 "큐에 둬도 된다").
  다만 **다음에 이 네 함수 중 하나를 또 고칠 일이 생기면 부분 수정을 하지 말고 이 변경을 먼저 한다** -
  세 번의 부분 수정이 모두 같은 자리로 돌아왔다.

---

## 7. 이 세션이 확인한 것 / 하지 못한 것

확인(읽기만):

- `projects/VoxLog/web/app.js` 전문 중 해당 구간(1~80, 144~201, 200~439, 1270~1324, 1620~1659), `web/api.js` 전문,
  `web/sw.js` 1~45, `web/queue.js` 495~516, `web/index.html` 30~43·148~163, `docs/INTERFACE.md` 425~479,
  `README.md` 40~84, `tests/browser_voxlog.py` 150~193·2118~2202·2815~2864·3002~3193,
  `rounds/R53/REVIEW-r53-2.md`·`REVIEW-r53-3.md`.
- 웹: MDN `AbortController`·`AbortSignal.any()`·`<fieldset>`, BCD `api/AbortSignal.json`(버전 값),
  TanStack Query "Query Cancellation"(늦은 응답을 캐시에 남기는 기본 동작).
- `<fieldset disabled>` 의 `disabled` IDL 속성과 Playwright `is_enabled` 의 차이 - `/tmp` 에 HTML 한 장을 만들고
  Playwright 로 직접 읽었다(프로젝트 트리 밖, /tmp 파일은 지웠다). 출력:

  ```
  is_enabled(a): False
  is_enabled(b): False
  a.disabled: False
  a:disabled matches: True
  ```

하지 못한 것(이 세션의 일이 아님):

- 코드 수정·시험 실행 없음. 4.1 의 줄 수는 읽고 센 **추정**이고, 4.3 의 "깨진다/통과한다"는 시험 코드를 읽어
  판정한 것이지 돌려서 본 것이 아니다. 구현할 때 브라우저 검사 전체를 한 번 돌려 확인할 것.
- 실제 폰(크롬 안드로이드·사파리 iOS)에서의 백그라운드 타이머 동작은 확인하지 않았다.
- 운영 자료는 읽지 않았다. `AIMEM.md`, R51~R54 밖 라운드 폴더도 읽지 않았다.
