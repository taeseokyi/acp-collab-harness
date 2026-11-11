# R11 적대적 검수 A (T-136, S1)

대상: `tools/aimem_monitor/server.py` 의 `/app/` 경로 티켓(`app_ticket`/`app_ticket_ok`/`_auth_gate`/`do_GET` 의 `_APP_RE` 갈래)과
결과물 격리(미리보기 iframe·새 탭·팝업). 모든 시험은 `/tmp/T-136/` 아래 임시 루트와 임시 포트로 띄운 서버에서 했고,
운영 모니터(18799)와 운영 `.aimem/` 은 건드리지 않았습니다. 작업 트리는 이 파일 말고 고치지 않았습니다.

## 판정

**결함 2건: 높음 1, 낮음 1.** 높음 1건은 **인증 우회**입니다. 인증 없는 소켓이 `GET /app/<이름>/../~x/` 한 번으로
그 프로젝트의 **유효한 12시간 티켓을 발급받고**, 그 티켓으로 결과물 파일을 200 으로 읽습니다. `_auth_gate` 는
**정규화된** 경로가 `/app/~` 로 시작하는지만 보고, 라우팅은 **원본** 경로를 `_APP_RE` 에 맞춰 "티켓 없음 → 발급"
갈래로 보내기 때문입니다. 브리프가 의심한 바로 그 어긋남입니다. `/api/*`·`/static/*`·POST 로는 닿지 못했고(전부 401/302),
닿는 범위는 `app.json` 이 선언한 프로젝트 앱 폴더입니다. 그래도 공개 서버의 인증 문이 뚫린 것이므로
**고치기 전에는 운영에 올리면 안 됩니다**(이미 올라가 있으면 바로 고칠 대상). 낮음 1건은 티켓이 표준오류 로그
(`monitorctl` 이 `.aimem/monitor.log` 로 보냄)에 그대로 남는 것입니다. 티켓 서명(위조·만료·다른 프로젝트·키 교체)과
브라우저 격리(iframe·새 탭·팝업, Referer)는 시도한 모든 길에서 버텼습니다.

## 실제로 돌려 본 것

스크립트: `/tmp/T-136/harness.py`(임시 루트·서버·원시 소켓 요청), `t1_bypass.py`, `t2_ticket.py`, `t3_fallback.py`,
`t4_leak.py`, `t5_browser.py`, `t6_variants_fix.py`. 임시 루트에는 `웹워들`·`다른앱`(같은 앱 + `secret-B.txt`)·
`공격앱`(t5, 공격 스크립트) 세 프로젝트를 두었습니다. 접근 토큰 `"a"*64`, 인증 켬, TLS 끔.
"무인증" = 쿠키·Authorization 없는 원시 소켓.

| 번호 | 시도한 것 | 명령 | 결과 |
|---|---|---|---|
| 0 | 기준선: 무인증 `/app/웹워들/`, `/api/state` | `python3 /tmp/T-136/t1_bypass.py` | 302 → `/login`, 401 |
| 1-1 | 만료 티켓(exp=now-1, exp=0, 올바른 서명) | `python3 /tmp/T-136/t2_ticket.py` | 403, 403 |
| 1-2a | 서명 끝/처음 1글자 변경, 31자, 33자, 64자(전체 hmac) | t2 | 전부 403 |
| 1-2b | exp 만 +1 / 10^11 로(서명 그대로) | t2 | 403, 403 |
| 1-2c | 대문자 16진수, `٣` 섞인 exp, `+exp`, `%20exp`, `0x…` exp, 점 3개, `%2e` 로 점 인코딩 | t2 | 전부 403 |
| 1-2d | 빈 티켓 `/app/~/웹워들/…` | t2 | 404 (티켓 없음 갈래 → 이름 `~` 가 `_PROJECT_RE` 불통) |
| 1-2e | 다른 키(`b"b"*64`)·빈 키로 서명 | t2 | 403, 403 |
| 1-2f | exp 앞에 `0` 붙이기(서명 그대로) `01794383358.<mac>` | t2 | **200** (결함 아님 - 아래) |
| 1-2g | exp 10^12(13자리, 올바른 서명) / 999999999999(12자리, 올바른 서명) | t2 | 403 / 200 (서버가 그런 exp 로 서명하지 않으므로 키 없이는 못 만듦) |
| 1-3a | 웹워들 티켓으로 `다른앱/secret-B.txt`, 다른앱 티켓으로 웹워들 | t2 | 403, 403 |
| 1-3b | 웹워들 티켓 + 이름 소문자 퍼센트 인코딩 | t2 | 200 (같은 이름이라 정상) |
| 1-3c | 웹워들 티켓 + 이름 이중 인코딩 / NFD / `%20` 꼬리 / `.` 꼬리 | t2 | 403 / 403 / 403 / 403 |
| 1-3d | NFD 이름으로 서명한 티켓 + NFD 이름 경로 | t2 | 404 (NFD 자모는 `_PROJECT_RE`·프로젝트 폴더에 안 맞음) |
| 1-3e | 웹워들 티켓 + 이름을 인코딩 없이 UTF-8 원문으로 | t1 | 403 (`http.server` 가 요청줄을 latin-1 로 읽어 이름이 깨짐 → 서명 불일치. 닫힌 쪽으로 실패) |
| 1-4 | 토큰 `a*64` 로 받은 티켓 → 토큰 `c*64` 로 새로 띄운 서버 | t2 | 403. 새 토큰 티켓은 200 |
| 1-5a | 인증 끈 서버에서 티켓 없이 `/app/웹워들/` | t2 | 302 → `/app/~<티켓>/…`, 따라가면 200 (인증 끔이면 공개가 맞음) |
| 1-5b | 인증 끈 서버: 프로세스 1 이 발급한 티켓을 프로세스 2(새로 띄움)에 | `python3 /tmp/T-136/t3_fallback.py` | 프로세스 1 에서 200, 프로세스 2 에서 **403** (난수 fallback 키가 바뀜) |
| 1-5c | 인증 끈 서버에 접근 토큰 키로 만든 티켓 | t2 | 403 (fallback 키와 다름) |
| 1-6 | 비교 함수 확인 | `grep -n compare_digest tools/aimem_monitor/server.py` | `app_ticket_ok` 236행 `hmac.compare_digest(bytes, bytes)`. 비교 전 `[0-9a-f]{32}` fullmatch 로 ASCII 보장. 타이밍에 새는 `==` 비교 없음 |
| **2-0** | **무인증 `/app/웹워들/../~x/`** | t1 | **302 `Location: /app/~1794422924.97fa…/웹워들/../~x/`. `app_ticket_ok` 로 확인한 결과 유효한 티켓** → 결함 1 |
| **2-0b** | 그 티켓으로 무인증 `/app/~T/웹워들/`, `/index.html` | t1 | **200, 결과물 HTML** |
| **2-0c** | 같은 길로 `다른앱` 티켓 발급 → 무인증 `secret-B.txt` | t1 | **200 `B-ONLY`** |
| 2-0d | 변형: `…/x/../../~x`, `…/../~x`(꼬리 `/` 없음), `…/./../~/`, `…/../~`, `abc/../~x/`, HEAD, 절대 URI 요청줄 | `python3 /tmp/T-136/t6_variants_fix.py` | 전부 302 + 유효 티켓 (`abc` 같은 없는 이름도 발급됨) |
| 2-0e | 같은 경로 POST | t6 | 404 `없는 경로입니다: /app/~x` (POST 에는 `/app` 갈래 없음) |
| 2-1 | 유효 티켓 + `웹워들/../../api/state` | t1 | 302 `/login` (정규화 → `/api/state`, 게이트에 걸림) |
| 2-2 | `%2e%2e%2f…api/state`, `..%252f…`, `....//`, `..;/`, 백슬래시, `%0a/../../api/state` | t1 | 404 (`_app_parts` 가 조각 거절) |
| 2-3 | `%00/../api/state` | t1 | 400 널바이트 |
| 2-4 | `/app/~T/../api/state`, `/./app/~T/../api/state`, `/app/~T/웹워들;/../../api/state` | t1 | 302 `/login` |
| 2-5 | `/app/~T//api/state` | t1 | 404 (`_APP_RE` 가 티켓 없음으로 해석, 이름 `~T` 불통) |
| 2-6 | `/api/state/../app/~T/x` | t1 | 401 |
| 2-7 | `//app/~T/웹워들/` | t1 | 200 - 파이썬 `http.server` 가 앞 `//` 를 `/` 로 접음. 같은 앱 파일이라 결함 아님 |
| 2-8 | 티켓 경로로 `/static/app.js`(두 꼴), `/login` | t1 | 302/401/302 |
| 2-9 | 티켓 경로로 다른 프로젝트: `웹워들/../다른앱/secret-B.txt`, `%2e%2e/…`, `..%2f…` | t1 | 404 |
| 2-10 | 티켓 경로로 `../app.json`, `%2e%2e%2fapp.json`, `.%2e/app.json`, `js/../../app.json`, `..%2F..%2F..%2F.aimem%2Faimem.db` | t1 | 전부 404 |
| 2-11 | `index.html?x=/../../api/state`, `index.html%3F/../../app.json` | t1 | 200 index.html (쿼리 버림) |
| 2-12 | 절대 URI 요청줄: `GET http://127.0.0.1:P/api/state`, `…/app/~T/../api/state`, `http://evil/app/~T/웹워들/../../api/state` | t1 | 401, 302 `/login`, 302 `/login` |
| 2-13 | `/app/~T/웹워들/../~T/../../api/state` | t1 | 302 `/login` |
| 2-14 | POST `/api/requests` 를 `/app/~T/../api/requests`, `/app/~T/웹워들/../../api/requests`, `/app/웹워들/../~x/../../api/requests` 로 | t1 | 전부 401, 요청 파일 0건 |
| 3-1 | `.aimem/access.log` 에 티켓 | `python3 /tmp/T-136/t4_leak.py` | 파일 자체가 안 생김(`/app` 은 `audit()` 안 부름) |
| 3-2 | 표준 `log_message` 켜고 stderr | t4 | **6줄 중 5줄에 티켓 원문** → 결함 2 |
| 3-3 | 오류 응답 본문에 티켓(200/404 없는 파일/404 조각/403 다른 이름/302) | t4 | 어느 본문에도 티켓 바이트 없음. 404 는 `rel` 만, 403 은 고정 문구 |
| 3-4 | Referer: iframe 안 `target=_blank` 링크, 새 탭 안 링크 클릭(같은 탭 이동), iframe 안 `window.open(기록 서버)` | `timeout 200 python3 /tmp/T-136/t5_browser.py` | 기록 서버가 받은 `Referer` 전부 `null`(헤더 없음), `Cookie` 없음. `/app/` 응답에 `Referrer-Policy: no-referrer` 가 붙음(`SECURITY_HEADERS`, 새 탭 링크에 속성이 없어도 응답 헤더가 막음) |
| 3-5 | 결과물 안 `fetch(기록 서버)`, `<img src=기록 서버>` | t5 | fetch `Failed to fetch`, img 는 요청 자체가 안 옴(CSP `connect-src`/`img-src`) |
| 4-1 | 로그인 확인 | t5 | `/api/login` 200, 쿠키 `aimem_session` SameSite=Strict, HttpOnly. 메인 화면에서 `fetch('/api/state')` 200 |
| 4-2 | 미리보기 iframe(app.js 와 같은 `sandbox="allow-scripts allow-popups allow-modals"` `referrerpolicy=no-referrer`) | t5 | `window.origin` `"null"`, `document.cookie`/`localStorage`/`parent.document`/`top.location.href` 전부 `SecurityError`, `fetch('/api/state')`·`POST /api/requests` `Failed to fetch`, 요청 파일 0건 |
| 4-3 | 새 탭(로그인한 브라우저로 `/app/공격앱/` 최상위 이동) | t5 | 티켓 경로로 302 후 `window.origin` `"null"`(CSP `sandbox` 적용됨), cookie/localStorage `SecurityError`, `fetch('/api/state')`·POST 실패 |
| 4-4 | 모니터와 같은 `<a target=_blank rel="noopener noreferrer">` 클릭 | t5 | 새 창 `window.origin` `"null"`, `window.opener === null` |
| 4-5 | iframe·새 탭 양쪽에서 `window.open('/app/웹워들/')` | t5 | 팝업 `window.origin` `"null"`, `/login` 에 떨어짐(불투명 출처 이동이라 Strict 쿠키 안 실림) |
| 4-6 | 양쪽에서 `window.open('/api/state')` | t5 | 팝업 본문 401 `인증이 필요합니다`, 팝업 안 `fetch('/api/state',{credentials:'include'})` 실패 |
| 4-7 | 양쪽에서 `window.open('about:blank')` + opener 가 그 창 `fetch` 접근 | t5 | 팝업 `window.origin` `"null"`, 팝업 안 fetch 실패, opener 에서 접근 `SecurityError` |
| 4-8 | `allow-popups-to-escape-sandbox`·`allow-same-origin` 검색 | `grep -rn "allow-popups-to-escape-sandbox\|allow-same-origin" tools/aimem_monitor/` | 0건 (`app_csp` 는 `sandbox allow-scripts allow-popups allow-modals`) |
| 5 | 결함 1 고침안을 하위 클래스로 시험(작업 트리 수정 없음) | t6 | `/app/웹워들/../~x/`, `…/x/../../~x` → 404. 정상 티켓 경로 200, 무인증 `/app/웹워들/` → 302 `/login` 유지 |
| 6 | 기존 테스트 | `python3 -m unittest tests.test_aimem_monitor_app` | `Ran 24 tests … OK` (결함 1 을 잡는 시험은 없음) |

## 결함

### 결함 1 - 무인증 소켓이 `/app/<이름>/../~x/` 로 유효한 티켓을 발급받는다 (높음, 인증 우회)

**어디:** `tools/aimem_monitor/server.py`
- 2400행 `_auth_gate`: `if path.startswith(PROJECT_APP_URL_PREFIX + PROJECT_APP_TICKET_PREFIX): return False` - `path` 는
  `_path()` 가 `posixpath.normpath` 로 **접은** 경로
- 2518~2531행 `do_GET`: `am = _APP_RE.match(raw_path)` - **원본** 경로. `ticket is None` 이면 세션 확인 없이
  `app_ticket(app_name, now+TTL, key)` 로 서명해 302 로 내준다

원본 `/app/웹워들/../~x/` 는 `_APP_RE` 로 보면 티켓 없음·이름 `웹워들`·rel `../~x/` 이고, 정규화하면 `/app/~x` 라
게이트가 "티켓 경로" 로 보고 세션 검사를 건너뜁니다. 발급 갈래는 "게이트가 이미 세션을 봤다" 고 가정하므로 그대로 서명합니다.

**재현 (무인증 원시 소켓, `python3 /tmp/T-136/t1_bypass.py` 실제 출력):**
```
A0 /app/<name>/ (no auth)   '/app/%EC%9B%B9%EC%9B%8C%EB%93%A4/'        -> HTTP/1.1 302 Found loc=/login
A1 /app/<name>/../~x/       '/app/%EC%9B%B9%EC%9B%8C%EB%93%A4/../~x/'  -> HTTP/1.1 302 Found loc=/app/~1794422924.97fa92835ac417492797dc21825a7fbb/%EC%9B%B9%EC%9B%8C%EB%93%A4/../~x/
minted ticket: 1794422924.97fa92835ac417492797dc21825a7fbb valid: True
A5 /app/~T/<name>/ (index) w/o auth  -> HTTP/1.1 200 OK body=b'<!DOCTYPE html>\n<html lang="ko" ...
A7 mint for 다른앱  '/app/%EB%8B%A4%EB%A5%B8%EC%95%B1/../~x/'  -> HTTP/1.1 302 Found loc=/app/~1794422924.e0360c2d.../%EB%8B%A4%EB%A5%B8%EC%95%B1/../~x/
A8 다른앱 secret w/o auth  '/app/~1794422924.e0360c2d.../%EB%8B%A4%EB%A5%B8%EC%95%B1/secret-B.txt' -> HTTP/1.1 200 OK body=b'B-ONLY'
```
curl 로는: `curl -si --path-as-is 'http://127.0.0.1:<임시 포트>/app/%EC%9B%B9%EC%9B%8C%EB%93%A4/../~x/'` → `Location` 의 `~<티켓>` 을 떼어
`curl -s 'http://127.0.0.1:<임시 포트>/app/~<티켓>/%EC%9B%B9%EC%9B%8C%EB%93%A4/'` (curl 은 `--path-as-is` 없이 `..` 를 접어 버리므로 꼭 붙여야 함).
변형 `…/x/../../~x`, `…/../~`, `…/./../~/`, HEAD, 절대 URI 요청줄, 없는 이름 `abc/../~x/` 도 전부 발급됩니다(t6).

**닿는 범위:** `app.json` 이 runnable 로 선언한 **모든** 프로젝트의 앱 폴더 파일(이름만 알면 됨 - 이름은 `/api/state` 를 못 봐도
추측 가능). `/api/*`·`/static/*`·POST·다른 프로젝트 폴더·`app.json`·`.aimem` 으로는 표의 2-1~2-14 처럼 넘어가지 못했습니다.

**고칠 방법 (둘 다 하십시오):**
1. 게이트가 라우팅과 **같은 입력·같은 정규식**으로 판단하게 합니다. 정규화된 경로의 접두가 아니라
   `am = _APP_RE.match(raw_path)` 에서 `am.group("ticket") is not None` 이고 **원본 경로에 `.`/`..`/빈 조각이 없을 때만**
   (= `posixpath.normpath(raw_path)` 가 원본과 같을 때, 꼬리 `/` 만 예외) 세션 검사를 건너뜁니다. 그렇지 않은데 정규화 경로가
   `/app/~` 로 시작하면 404 로 끊습니다. t6 의 하위 클래스(`Fixed._auth_gate`)로 이 방식을 실제로 돌려 `/app/웹워들/../~x/`·
   `…/x/../../~x` → 404, 정상 티켓 → 200, 무인증 `/app/웹워들/` → 302 `/login` 을 확인했습니다.
2. 심층 방어로 **발급 갈래(2522행 `if ticket is None:`) 안에서 직접** `if self.require_auth and not self._subject():` 이면
   `/login` 302 를 돌려줍니다. 서명은 "이 요청이 인증됐다" 는 사실을 그 자리에서 확인한 뒤에만 합니다.
3. 회귀 시험을 `tests/test_aimem_monitor_app.py` 에 더합니다: 무인증 `GET /app/<이름>/../~x/`, `…/x/../../~x`, `…/../~` 가
   302 `Location: /app/~…` 를 **돌려주지 않는다**(원시 소켓 또는 `http.client` 로 - `urllib` 는 `..` 를 접지 않지만 curl 은 접음).

### 결함 2 - 티켓이 표준오류 로그(`.aimem/monitor.log`)에 원문으로 남는다 (낮음)

**어디:** `tools/aimem_monitor/server.py` 2237행 `Handler.log_message` - 요청줄을 그대로 적습니다.
`tools/aimem_monitor/monitorctl.sh` 62행이 표준오류를 `$ROOT/.aimem/monitor.log`(600) 로 보냅니다.

**재현 (`python3 /tmp/T-136/t4_leak.py` 실제 출력):**
```
stderr 로그 줄 수: 6  티켓 포함 줄 수: 5
   11/Nov/2026 15:49:37 "GET /app/~1794383377.69e2deb6d8ac63d039f3836a65543f28/%EC%9B%B9%EC%9B%8C%EB%93%A4/index.html HTTP/1.1" 200 -
```
로그를 읽을 수 있는 사람은 12시간 동안 인증 없이 그 결과물을 읽습니다. 다만 같은 `.aimem/` 아래에 접근 토큰 파일이 있으므로
이 로그를 읽을 수 있는 쪽은 대개 토큰도 읽을 수 있어 **실질 위험은 낮습니다.** 결함 1 이 고쳐진 뒤에는 이 로그가 티켓의 주된 유출처입니다.

**고칠 방법:** `log_message` 에서 줄을 쓰기 전에 `re.sub(r"/app/~[^/\s]+/", "/app/~***/", line)` 로 가립니다(`_LOG_SAFE` 치환과 같은 자리).
시험: `/app/~<티켓>/…` 요청 뒤 stderr 에 티켓 문자열이 없음을 확인.

## 결함 아님 (적어 둠)

- **exp 앞 `0` 허용(1-2f):** `01794383358.<mac>` 이 원래 티켓과 같이 통과합니다. `int()` 로 읽은 뒤 서명 대상을 다시 만들기 때문입니다.
  만료를 늘리거나 다른 프로젝트로 옮기지 못하므로 권한 상승은 없습니다. 한 티켓의 문자열 꼴이 여러 개라는 것뿐입니다
  (티켓 문자열로 블록리스트를 만들 일이 생기면 `exp_s == str(int(exp_s))` 를 요구하십시오).
- **exp 상한 없음(1-2g):** 12자리 exp(서기 3만 년대)도 올바른 서명이면 통과합니다. 서버는 `now+TTL` 로만 서명하므로 키 없이는 못 만듭니다.
  `exp <= now + TTL + 여유` 상한을 두면 키가 샌 경우의 피해를 줄일 수 있습니다(권고).
- **유니코드 숫자:** `\d{1,12}` 는 파이썬에서 `٣` 같은 유니코드 숫자도 맞추지만, 서명 대상은 `int()` 값이라 서명이 맞지 않아 403 입니다.
  `re.ASCII` 를 붙이면 더 깔끔합니다(권고).
- **인증 끈 서버의 무티켓 접근(1-5a):** 인증 끔이면 모든 것이 공개라 302 → 200 이 맞습니다. 재시작하면 옛 티켓은 죽습니다(1-5b).
- **`//app/~T/…` (2-7):** `http.server` 가 앞 `//` 를 접어 같은 앱 파일을 줍니다. 범위 밖으로 안 나갑니다.
- **sandbox 팝업에서 `/app/<다른 이름>/` 을 열면 `/login` 으로 감(4-5):** 불투명 출처에서 시작한 이동이라 Strict 쿠키가 안 실리는 것.
  보안상 옳고, 결과물이 다른 결과물을 여는 기능이 필요해지면 그때의 문제입니다.
- **새 탭 링크에 `referrerpolicy` 속성 없음:** `rel=noreferrer` 가 있고, 결과물 응답에 `Referrer-Policy: no-referrer` 헤더가 붙어
  결과물 안에서 나가는 이동의 Referer 가 실제로 비어 있었습니다(3-4).
- **새 탭 공격 스크립트의 `parent.document` 가 `"atk"`:** 최상위 창이라 `parent === window` 인 것. 모니터 문서가 아닙니다.
- **CSP 가 인라인 `onclick` 을 막음:** 결과물이 인라인 처리기를 쓰면 동작하지 않습니다(`script-src` 에 `'unsafe-inline'` 없음). 의도된 것으로 보입니다.

## 못 본 것

- TLS 모드·좁은 화면·변이 시험: 브리프대로 T-137 몫이라 하지 않았습니다.
- 브라우저는 playwright chromium(헤드리스) 하나만 봤습니다. Firefox/Safari 의 CSP `sandbox` 처리, 실제 사용자 클릭 팝업 차단기는 보지 않았습니다.
- GitHub OAuth 로 로그인한 세션(`gh:` subject)으로는 돌리지 않았습니다(토큰 로그인만). 티켓 발급 갈래는 세션 종류를 보지 않으므로 결과가 다를 이유는 없어 보입니다.
- 프록시(nginx 등) 뒤에서 경로가 한 번 더 정규화·디코딩되는 배치는 재현하지 않았습니다. 앞단이 `..` 를 접는 프록시라면 결함 1 의
  원시 요청이 서버까지 안 올 수도 있지만, 운영 배치가 그런지는 확인하지 못했습니다 - 고침은 그것과 무관하게 필요합니다.
