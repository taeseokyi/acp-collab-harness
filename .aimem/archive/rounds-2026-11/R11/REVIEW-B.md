# R11 적대적 검수 B (T-137, S4)

검수 대상: R10 이 넣은 `/app/<이름>/` 실행(경로 티켓·sandbox)의 TLS·프록시 Host·좁은 화면·서비스 워커, 그리고 검사의 진위(변이 시험).
기준: AIMEM REV 154, 작업 트리 읽기 전용. 서버는 전부 `/tmp/t137/` 의 임시 루트·임시 포트, 운영 18799 는 건드리지 않았습니다.
하니스: `/tmp/t137/lib.py`(TLSThreadingHTTPServer + ssl 컨텍스트 + 20줄 TCP 통과 프록시), `raw.py`, `br.py`, `br2.py`, `sw.py`, `mutate.py`.

## 판정

**결함 2건(둘 다 낮음) + 검사 구멍 6개.** 제품 쪽은 단단합니다. 티켓 302 는 경로만 돌려줘 프록시 포트가 바뀌어도 그대로 맞고, CSP 출처는 TLS 에서 `https://<Host 그대로>` 로 들어가며, 쿠키는 TLS 에서 `Secure; HttpOnly; SameSite=Strict`, 프록시(18800→서버 포트 모사)를 거친 브라우저에서 세 폭(390/720/1280) 모두 미리보기·새 탭이 실제로 그려졌고 잘림·겹침·가로 스크롤이 없었습니다. 서비스 워커도 `/app/` 을 캐시하지 않고 지나칩니다(브라우저 실측). 반면 **검사가 못 지키는 곳이 많습니다**: 지정한 7개 변이는 어느 한 검사에서는 빨개졌지만(M1~M7), TLS 쿠키 `Secure`, TLS 출처 `https`, sw.js 의 `/app/` 지나치기, 좁은 화면 높이 규칙, 티켓 수명 변이는 **전 검사가 초록으로 통과**했고, `app_csp` 의 `sandbox` 제거(M6)는 브라우저 검사가 전부 초록입니다(단위 문자열 검사만 잡음).

## 실제로 돌려 본 것

| # | 시도한 것 | 명령 | 결과 |
|---|---|---|---|
| 1 | TLS 서버(자체 서명) + TCP 통과 프록시 + 포트 다른 Host 로 티켓 302 | `python3 /tmp/t137/raw.py` (A) | `Host: 192.168.0.5:18800` 로 보냄 → `302`, `Location: /app/~1794422894.d9a1…/%EC%9B%B9…/` **경로만**(스킴·호스트 없음). 브라우저는 현재 스킴·호스트·포트로 해석하므로 https·프록시 포트에서 그대로 맞음 |
| 2 | 티켓 경로 200 의 CSP 출처 | 같은 스크립트 (B) | `Content-Security-Policy: sandbox allow-scripts allow-popups allow-modals; default-src 'self' https://192.168.0.5:18800; … script-src 'self' https://192.168.0.5:18800; connect-src …`, `Access-Control-Allow-Origin: null`, `Vary: Origin`. 티켓 경로는 쿠키 없이 200 |
| 3 | 로그인 Set-Cookie (TLS) | 같은 스크립트 (C) | `Set-Cookie: aimem_session=v1…; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200; Secure`. 브라우저 컨텍스트의 `cookies()` 도 `secure=True, httpOnly=True, sameSite=Strict` |
| 4 | Host 변형 | 같은 스크립트 (D) | `192.168.0.5:18800`→`https://192.168.0.5:18800`, `[::1]:18800`→`https://[::1]:18800`, `a b`·`evil.com"; x`·101자→출처 없이 `'self'` 만, **`Host: evil.com`→`https://evil.com` 이 script-src 에 들어감**(결함 1) |
| 5 | 평문 http → TLS 서버 | 같은 스크립트 (E) | 직접·프록시 모두 `301 Location: https://192.168.0.5:18800/app/x/?a=1`(Host 포트 유지). Host 없는 HTTP/1.0 → `400 이 포트는 HTTPS 전용입니다.` |
| 6 | 프록시 경유 브라우저, 세 폭에서 '실행' | `python3 /tmp/t137/br.py` | 아래 표 |
| 7 | 짧은 화면(가로 폰 등) | `python3 /tmp/t137/br2.py` | 아래 표 |
| 8 | '새 탭에서 열기' 실제 클릭(인증 켠 TLS 프록시) | `br.py` 의 NEWTAB | 세 폭 모두 새 탭 URL 이 `https://127.0.0.1:<프록시 포트>/app/~…/…/`, 타일 30개, 첫 칸 가시, 보드 350×421, `window.origin == "null"`, 가로 스크롤 0 |
| 9 | 서비스 워커(브라우저) | `python3 -u /tmp/t137/sw.py` | 등록(scope `/`, `sw.js`), 새로고침 뒤 제어됨. `caches.keys()`=`["aimem-shell-v12"]`, 항목 7개 모두 껍데기(`/ /index.html /manifest… /icon-… /style.css /app.js`), **`/app/` 항목 0개**. 미리보기 열 때마다 `/app/…`(티켓 발급 + 5개 파일) 7건이 서버에 실제로 도착, 닫고 다시 열어도 7건 재도착(캐시 응답 없음). `/app/…/` 내비게이션 `transferSize=4315`. sw.js `VERSION='aimem-shell-v12'`, `Cache-Control: no-store` |
| 10 | 변이 시험 | `python3 -u /tmp/t137/mutate.py base` 그리고 `… M1 … X6` | 아래 `## 검사 구멍` 표. 기준선은 전부 초록: unit 228 OK(skipped 1), browser_app 8/8, browser_auth 6/6, browser_ui 6/6 |

**표 6 (프록시+TLS, 로그인 뒤, `bounding_box()` 실측, 단위 px)**

| 폭×높이 | iframe (x,y,w,h) | 패널 body (y,h) | iframe 아래끝 − body 아래끝 | 탭링크 (y,h) / 메타 (y,h) | 겹침 | 가로 스크롤 | 맨 아랫줄 키 |
|---|---|---|---|---|---|---|---|
| 390×844 | 21,165.3,348,**590.8** | 63.8,704.3 | −12.0 | 142.1,23.2 / 88.8,40.3 | 없음 | 0 (페이지·body 모두) | y=691.3 h=50, 안에 있고 `is_visible()` True |
| 720×900 | 21,145.2,678,**630** | 63.8,723.4 | −12.0 | 121.9,23.2 / 88.8,20.1 | 없음 | 0 | y=704.2 h=54, 보임 |
| 1280×900 | 207,157.2,866,**651.8** | 71.8,753.2 | −16.0 | 133.9,23.2 / 100.8,20.1 | 없음 | 0 | y=738.2 h=54, 보임 |

- 390 에서 iframe 높이 590.8 = 844×0.70, 기본 규칙(`min(78vh,900px)`=658)이 아니라 **미디어 쿼리 규칙(`min(70vh,640px)`)이 이기고 있음**을 높이로 확인. 720 에서 630 = 900×0.70(경계 폭 720 에서도 미디어 쿼리 적용). 1280 에서 651.8 은 78vh=702 가 패널 `max-height:90vh` 에 눌린 값.
- 세 폭 모두 iframe 안 `innerHeight == scrollHeight`(589/628/650): 안쪽 스크롤 필요 없음.
- 콘솔 오류 1건: `An SSL certificate error occurred when fetching the script.` — 자체 서명 인증서에서 sw.js 등록이 거절된 것(하니스 한계, 표 9 는 `--ignore-certificate-errors` 로 등록시킴).

**표 7 (짧은 화면)**

| 폭×높이 | iframe h | 패널 body scrollH/clientH | 가로 스크롤 | 끝까지 스크롤한 뒤 맨 아랫줄 키 | 키 높이 |
|---|---|---|---|---|---|
| 844×390 | 320(min-height) | 421/294 | 0 | iframe·뷰포트 안 | **20** |
| 390×500 | 320 | 434/418 | 0 | 안 | **20** |
| 320×568 | 349.1 | 483/483 | 0 | 안 | 20 |

## 결함

### 결함 1 - `Host` 헤더 값이 그대로 CSP `script-src` 허용 출처가 된다 (낮음)
- 어디: `tools/aimem_monitor/server.py:2387-2392` `_app_origin()` → `:2541` `csp=app_csp(self._app_origin())`
- 무엇이: Host 꼴 검사는 문자 집합·길이뿐이라 **아무 이름**이나 통과합니다.
  재현: `python3 /tmp/t137/raw.py` (D) — `Host: evil.com` 으로 유효 티켓 경로를 부르면 응답 CSP 가 `script-src 'self' https://evil.com; connect-src 'self' https://evil.com; default-src 'self' https://evil.com …`.
  브라우저는 Host 를 URL 에서 스스로 정하므로 **다른 사이트가 피해자 요청의 Host 를 바꿀 수는 없습니다.** 다만 (a) 모니터 앞에 Host 를 그대로 전달하는 프록시/가상 호스트가 하나라도 생기거나 (b) DNS 리바인딩으로 `evil.com:18800` 이 이 서버로 풀리면, 결과물(작업자가 쓴 코드)이 evil.com 의 스크립트를 로드·접속할 수 있는 CSP 를 서버가 스스로 발급합니다. 티켓 경로는 쿠키 없이 열리므로(설계) 티켓 URL 을 아는 쪽이 Host 를 고르는 것과 같습니다.
- 고치는 법: 출처를 요청 Host 에서 만들지 말고 (1) 서버가 아는 이름 집합(바인드 주소·`--tls` 인증서 SAN·설정한 외부 주소)과 대조해 맞을 때만 넣고, 아니면 `'self'` 만 쓰거나 (2) `_app_origin()` 을 `Origin`/`Referer` 가 아닌 서버 설정값으로 바꿉니다. 테스트: `Host: evil.com` 으로 불렀을 때 CSP 에 `evil.com` 이 없어야 함.

### 결함 2 - iframe 이 낮으면 화면 키보드 키가 20px 로 쪼그라든다 (낮음, 접근성)
- 어디: `projects/웹워들/web/css/*.css:161-162`(`.key { height: clamp(20px, calc((100dvh - 330px) / 3), 54px) }`), 모바일 `:291-292`
- 무엇이: 키 높이가 **iframe 안쪽** 뷰포트 높이로 계산되는데, 모니터가 iframe 에 주는 최소 높이는 `min-height: 320px`(style.css:1327)입니다. `(320-330)/3 < 0` → 하한 20px. 실측(표 7): 844×390, 390×500 에서 맨 아랫줄 키 높이 **20px**(보임·안 겹침, 그러나 터치 목표 44px 의 절반 미만). 390×844(세로 폰)에서는 50px 로 정상.
- 고치는 법: 모니터 쪽 `.proj-app-frame` `min-height` 를 `380px` 이상으로 올리거나(패널은 이미 스크롤됨), 결과물 쪽 하한을 `clamp(32px, …)` 로. 둘 다 이 태스크 범위 밖이라 고치지 않았습니다.

## 검사 구멍

지정 변이는 **저장소 사본**(`/tmp/t137/mut`)에서 하나씩 넣고(넣기→4개 검사 병렬 실행→원본 바이트로 되돌리고 `assert` 로 바이트 동일 확인) 돌렸습니다. 검사 명령: unit=`python3 -m unittest discover -s tests -p 'test_aimem_monitor*'`, app/auth/ui=`python3 tests/browser_monitor_{app,auth,ui}.py`. 빨개진 것은 `빨강:`, 아무도 안 빨개지면 **구멍**.

| 변이 | unit | browser_app | browser_auth | browser_ui | 판정 |
|---|---|---|---|---|---|
| M1 `app_ticket_ok` 항상 True | **빨강 11건** (`test_expired_ticket_is_rejected`, `test_malformed_tickets_never_raise`×…) | 초록 8/8 | 초록 6/6 | 초록 6/6 | 지켜짐(단위만) |
| M2 만료 검사 제거 | **빨강 2** (`test_expired_ticket_is_rejected`, `test_ticket_path_passes_auth_gate_without_session`) | 초록 | 초록 | 초록 | 지켜짐(단위만) |
| M3 이름을 서명에서 제외(발급·검증 양쪽) | **빨강 1** (`test_tampered_or_other_project_ticket_is_rejected`) | 초록 | 초록 | 초록 | 지켜짐(단위 1건뿐) |
| M4 게이트 `/app/~` 면제를 `/app/` 전체로 | **빨강 1** (`test_app_route_unauthenticated_redirects_to_login`) | 초록 | **빨강 1** (`로그인 전에는 막힌다 - 상태=200, 게임HTML(id=board)=True`) | 초록 | 지켜짐(둘이 잡음) |
| M5 ACAO `null` 제거 | **빨강 1** (`test_app_route_serves_and_uses_one_origin_aware_csp`) | **빨강**(`TimeoutError`, 0/1) | **빨강 2** (그려짐·CSS) | **빨강 1** (보드 안 그려짐) | 지켜짐(모두) |
| M6 `app_csp` 에서 `sandbox` 제거 | **빨강 3** (`…one_origin_aware_csp`, `…keeps_iframe_framing…`, `…sandbox_makes_origin_opaque`) | 초록 8/8 | 초록 6/6 | 초록 6/6 | **단위(문자열)만 — 브라우저 검사 구멍**(구멍 6) |
| M7 `fr.setAttribute('sandbox', …)` 삭제 | 초록(228 OK) | 초록 | 초록 | **빨강 1** (`sandbox=None`) | 지켜짐(ui 하나뿐; CSP sandbox 가 있어 격리 자체는 유지) |
| X1 TLS 쿠키 `Secure` 제거 | 초록 | 초록 | 초록 | 초록 | **구멍 1** |
| X2 `_app_origin` 이 TLS 에서도 `http` | 초록 | 초록 | 초록 | 초록 | **구멍 2** |
| X3 sw.js 의 `/app/` 지나치기 줄 제거 | 초록 | 초록 | 초록 | 초록 | **구멍 3** |
| X4 좁은 화면 iframe 높이 규칙(`@media (max-width:720px)`) 제거 | 초록 | 초록 | 초록 | 초록 | **구멍 4** |
| X5 티켓 수명 10년으로(`PROJECT_APP_TICKET_TTL_SEC` 대신) | 초록 | 초록 | 초록 | 초록 | **구멍 5** |
| X6 `script-src` 에 `'unsafe-inline'` 추가 | **빨강 1** (`test_csp_keeps_iframe_framing_and_stays_well_formed`) | 초록 | 초록 | 초록 | 지켜짐(문자열만) |

(M·X 접두: M=브리프가 지정한 변이, X=제가 더한 변이.)

- **검사 구멍 1: TLS 에서 쿠키 `Secure` 를 빼도 초록** — 모든 검사가 `tls=False` 핸들러로만 돕니다. `tests/test_aimem_monitor_auth.py` 에 `tls=True` 핸들러로 `/api/login` 을 부르고 `Set-Cookie` 에 `Secure; HttpOnly; SameSite=Strict` 가 모두 있는지 보는 검사를 더하면 메워집니다.
- **검사 구멍 2: TLS 에서 CSP 출처가 `http://` 가 되어도 초록** — `app_csp(origin)` 단위 검사는 출처를 **인자로 받아** 문자열만 보고, `_app_origin()` 은 아무도 안 부릅니다. `tests/test_aimem_monitor_app.py` 에 `tls=True`·`Host: 192.168.0.5:18800` 핸들러로 티켓 경로를 불러 CSP 에 `https://192.168.0.5:18800` 이 있고 `http://` 가 없는지 보는 검사를 더하십시오(결함 1 의 `evil.com` 거절 검사도 같은 파일).
- **검사 구멍 3: sw.js 가 `/app/` 을 캐시하기 시작해도 초록** — sw.js 를 실행하는 검사가 하나도 없습니다. `tests/browser_monitor_auth.py` 계열(TLS+`--ignore-certificate-errors` 로 SW 등록)에 미리보기를 한 번 띄운 뒤 `caches.open(...).keys()` 에 `/app/` 경로가 0개인지 보는 검사를 더하거나, 최소한 `tests/test_aimem_monitor_app.py` 에 sw.js 텍스트에서 `/app/` 지나침 줄과 `VERSION` 상승을 확인하는 검사를 더하십시오.
- **검사 구멍 4: 좁은 화면 규칙이 죽어도 초록 (R10 결함 4 가 다시 와도 모름)** — 세 검사 모두 뷰포트 420/1280 하나로만 돌고 **높이를 재는 곳이 없습니다**(`browser_monitor_ui.py` 는 iframe 가시성·sandbox 만 봄). `tests/browser_monitor_ui.py` 에 390×844 와 1280×900 에서 `iframe.proj-app-frame` 의 `bounding_box()['height']` 를 재어 390 쪽이 `min(0.70×844, 640)=590.8±1` 이고 1280 쪽과 달라야 한다는 검사를 더하십시오(기본 규칙이면 658).
- **검사 구멍 5: 티켓 수명이 10년이 되어도 초록** — 만료 검사는 `exp` 를 직접 과거로 만든 티켓만 봅니다. 발급 경로(302 `Location` 의 티켓)를 파싱해 `exp - now <= PROJECT_APP_TICKET_TTL_SEC + 2` 를 보는 검사를 `tests/test_aimem_monitor_app.py` 에 더하십시오.
- **검사 구멍 6: 새 탭 격리(CSP `sandbox`)를 브라우저가 지키지 않음** — `browser_monitor_auth.py` 의 `check_sandbox_isolation` 은 **iframe 안**의 `window.origin == "null"` 을 보는데, 그건 iframe 의 `sandbox` 속성만으로도 `null` 이라 CSP `sandbox` 를 빼도 초록입니다(M6). 단위 검사는 문자열만 봅니다. `tests/browser_monitor_auth.py` 에 티켓 URL 을 **최상위로** `page.goto` 해서 `evaluate("window.origin") == "null"` 과 `document.cookie` 가 비어 있고 `fetch('/api/state')` 가 실패하는지 보는 검사를 더하십시오(제가 수작업으로는 새 탭 `origin=null` 을 확인했습니다).

(M3 은 단위 1건, M7 은 ui 1건뿐이라 얇습니다 — 구멍은 아니지만 같은 검사가 사라지면 곧 구멍입니다.)

## 결함 아님 (적어 둠)

- **티켓 302 `Location` 은 경로만 돌려줍니다**(스킴·호스트·포트 없음). 지적받은 대로 확인했고, 이것이 **옳은 동작**입니다: 프록시 포트(18800)·https·Host 가 어떻게 바뀌어도 브라우저가 현재 접속 주소 기준으로 풀어 줍니다(표 1, 표 8 에서 프록시 포트로 새 탭·iframe 이 모두 열림). 절대 주소로 바꾸면 Host 신뢰 문제만 생깁니다.
- 평문 http → TLS 서버: 직접·프록시 모두 `301 https://<같은 Host>/<경로>`; Host 가 없으면 400 한글 안내. 경로는 안전 문자만 남기고 자르며 본문·쿠키는 읽지 않음. `Host: evil.com` 이면 `https://evil.com/…` 로 보내지만 평문 요청자 본인에게만 가는 값이고 브라우저는 Host 를 못 속이므로 결함 아님(결함 1 과 같은 뿌리지만 데이터가 실리지 않음).
- 서비스 워커: `/app/` 은 `respondWith` 없이 지나침, 껍데기 캐시에는 `/app/` 항목 0개, 열 때마다 서버에 도착. `sw.js` 는 `no-store` 라 갱신도 즉시. **버전 `aimem-shell-v12` 로 올라 있음**(코드와 서버 응답 둘 다 확인).
- 좁은 화면 규칙 순서 수정(R10 결함 4): 브라우저로 잰 결과 **실제로 적용됨**(390/720 에서 70vh, 1280 에서 달라짐).
- iframe 아래끝이 패널 스크롤 영역 아래끝보다 12~16px **위**에 있음(패딩). 잘리지 않음, 패널 `scrollHeight == clientHeight`.
- `Access-Control-Allow-Origin: null` + `Vary: Origin` 이 200 응답에만 붙음. 불투명 출처 iframe 의 모듈/폰트 로드에 필요하고, M5 에서 세 브라우저 검사가 실제로 빨개지는 것으로 필요함을 확인.
- 301/302/400 평문 응답은 `Set-Cookie` 를 싣지 않음.
- 두 변이(M1·M2)는 브라우저 검사 3종이 모두 초록이지만, 단위 검사가 더 정확히 잡으므로 구멍으로 세지 않음.

## 못 본 것

- **윈도우 `portproxy` 자체**(0.0.0.0:18800→127.0.0.1:18799)는 흉내만 냈습니다. TCP 통과라 TLS 바이트 중계는 같고 Host 헤더가 보존되는 것은 같지만, 실제 윈도우의 방화벽·IPv6·keep-alive 동작은 못 봤습니다.
- **신뢰된 인증서**: 자체 서명이라 sw.js 등록은 `--ignore-certificate-errors` 로만 됩니다. 운영 인증서를 신뢰 저장소에 넣은 브라우저에서의 SW 업그레이드(v11→v12 때 옛 캐시 삭제 `activate` 경로)는 **실행해 보지 않았습니다**(옛 SW 를 설치한 채로 새 버전을 받아 보는 시험을 안 함).
- Chromium 외 브라우저(Safari/Firefox, 모바일 실기기). 실제 터치(`tap`)·소프트 키보드가 올라온 상태·화면 회전 중의 높이 변화.
- 티켓 인가·격리 쪽(T-136 몫), 서버 재시작·토큰 교체 뒤 티켓 회수는 안 봤습니다.
- 변이 시험은 지정 7개 + 제 추가 6개뿐입니다. `frame-ancestors`, `form-action`, `X-Content-Type-Options` 같은 다른 지시어·헤더를 빼는 변이는 시험하지 않았습니다.
- 사본 `/tmp/t137/mut` 은 **지우지 않았습니다**: 삭제는 사용자 직접 허가가 있을 때만 하라는 지침과 샌드박스 권한 때문에 `rm -rf` 를 실행하지 않았습니다(`.git` 은 `rm` 대신 복사 때 제외했습니다). `/tmp/t137/` 전체(사본·임시 루트·인증서)를 다음 담당자가 `rm -rf /tmp/t137` 로 치워 주십시오. 사본에는 운영 `.aimem/` 의 복사본이 들어 있습니다.
