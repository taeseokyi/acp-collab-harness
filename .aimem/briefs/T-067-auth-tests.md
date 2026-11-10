# T-067 인증·TLS 계약 테스트 - `tests/test_aimem_monitor_auth.py` (새 파일)

## 왜

함대 모니터를 외부에 공개하기 위해 관리자가 `server.py` 에 **접근 제어와 HTTPS** 를 구현했다
(태석님 요청 19:05). 구현은 끝났고 관리자가 curl 로 훑었지만, **회귀를 잡는 테스트가 없다.**
다음 사람이 라우팅 한 줄만 고쳐도 인증이 조용히 열릴 수 있다. 그걸 막는 것이 이 태스크다.

## 쓰기 경로

`tests/test_aimem_monitor_auth.py` **새 파일 하나.** (`tests/test_aimem_monitor*.py` 는 네 소유다.)
`tools/` 아래는 **읽기만** 하라 - 구현이 정본이고, 어긋나면 테스트가 아니라 **보고에 적어라.**

## 대상 (읽고 시작할 자리)

```bash
grep -n "def load_access_token\|def ensure_access_token\|def sign_session\|def verify_session\|def build_ssl_context\|def github_enabled\|def github_allowed_logins\|class LoginGuard\|def _path\|def _auth_gate\|def _subject\|def serve" tools/aimem_monitor/server.py
sed -n '/^# ===/,/^def _reader/p' tools/aimem_monitor/server.py   # 인증 구현부 전체
grep -n "AUTH_\|SESSION_\|LOGIN_FAIL\|SECURITY_HEADERS\|HSTS\|TOKEN_FILE\|CERT_FILE" tools/aimem_monitor/__init__.py
```

세션 쿠키 꼴: `v1.<만료 epoch>.<subject>.<hex hmac>`,
mac = `HMAC-SHA256(키=접근 토큰 문자열의 ascii 바이트, 메시지="v1.<exp>.<subject>")`.
subject 는 `token` 또는 `gh:<login>`.

## 반드시 지킬 것

- **저장소의 `.aimem/tls/` 를 건드리지 마라.** 토큰·인증서는 실물이다. 테스트는
  `tempfile.TemporaryDirectory()` 를 root 로 잡고 그 안에서만 토큰을 만들어라
- 서버를 띄울 때는 **포트 0**(커널이 빈 포트를 고름)이나 18810 이상을 쓰고, 스레드로 띄운 뒤
  `shutdown()` 으로 내려라. 다른 작업자가 쓰는 18799·18801~18804 를 쓰지 마라
- `pkill` 금지. `python3 -m unittest` 로 끝나야 한다(테스트가 프로세스를 남기면 안 된다)

## 덮을 것 (최소 이만큼)

### 순수 함수

1. `ensure_access_token` - 없으면 만든다(64자 hex), **파일 권한이 0600**, 두 번 불러도 같은 값,
   `create=False` 면 None
2. `load_access_token` - 빈 파일 / 63자 / 65자 / 대문자 hex / 공백·개행 섞임 → **None**
   (정상 토큰만 통과)
3. `sign_session` / `verify_session` 왕복 - 정상 통과, 그리고 **전부 None 이어야 하는 것들**:
   mac 1글자 변조, exp 를 키운 쿠키, **같은 mac 을 다른 exp 에 붙이기**, 과거 exp(만료),
   `v2.` 버전, 점 개수가 다른 값, subject 에 `.`·개행·`;`, 빈 문자열, None,
   **다른 토큰으로 서명한 쿠키**(토큰 교체 = 세션 전원 무효)
4. `github_enabled` - 환경변수 둘 중 하나만 있으면 False (`unittest.mock.patch.dict(os.environ)`)
5. `github_allowed_logins` - 파일 없으면 **빈 집합**, `#` 주석·빈 줄 무시, 대문자는 소문자로
6. `LoginGuard` - 상한 안에서는 `check()==0.0`, 넘으면 양수, `reset()` 하면 다시 0.0,
   창(`window`)이 지나면 기록이 사라진다(`now=` 인자를 넣어 **시간을 흉내내라**. `sleep` 금지)

### HTTP (서버를 실제로 띄워서)

`http.server.ThreadingHTTPServer` 를 `server.serve(...)` 대신 직접 조립해도 되고
(`type("H", (server.Handler,), {...})` 로 `root`/`require_auth`/`access_token`/`guard` 를 묶는다),
`threading.Thread(target=server.serve, kwargs={...})` 로 띄워도 된다. **둘 중 쉬운 쪽.**

7. 인증 켠 상태에서 무인증: `/api/state`·`/api/health`·`/static/app.js`·`/api/runs/<id>` → **401**
8. `/` 와 `/index.html` → **302** + `Location: /login`
9. `/login`·`/api/authinfo` → **200** (면제)
10. `Authorization: Bearer <맞는 토큰>` → 200 / **틀린 토큰 → 401** / `Bearer` 뒤 빈 값 → 401
11. `POST /api/login` 맞는 토큰 → 200 `{"ok":true,"redirect":"/"}` + `Set-Cookie` 에
    `HttpOnly`·`SameSite=Strict`·`Path=/` 가 있고 **TLS 가 아니면 `Secure` 가 없다**
12. 그 쿠키로 `/api/state` → 200. **변조한 쿠키로는 401**
13. `POST /api/logout` → `Max-Age=0` 쿠키
14. **우회 시도 전부 401**: `/login/../api/state`, `//api/state`, `/./api/state`, `/api/state/`,
    `/LOGIN`, `/login%2f..%2fapi/state`, `/favicon.ico/../api/state`, `/login%00`
15. `POST /api/requests` - `Content-Type: text/plain` → **415**, `Origin` 이 `Host` 와 다르면 **403**,
    `Content-Length` 없음 → **411**, 음수 → **400**, `MAX_BODY` 초과 → **413**
16. 모든 응답에 `X-Content-Type-Options`·`Referrer-Policy`·`Content-Security-Policy` 가 붙는다
    (401 과 302 에도). `Server` 헤더에 **파이썬 버전이 없다**
17. **인증을 끄면(`require_auth=False`) 예전 그대로** - `/api/state` 200, `/` 200.
    이 테스트 하나가 "공개 작업이 로컬 동작을 깨지 않았다" 를 못박는다

### TLS

18. `build_ssl_context` - 인증서가 없는 임시 root → `SystemExit`.
    키 권한이 0644 면 `SystemExit`(권한 문구). **정상 인증서로 컨텍스트가 만들어지는 것까지만** -
    실제 핸드셰이크 테스트는 선택이다(만들려면 `openssl` 대신
    `ssl.SSLContext` + 임시 자체서명 인증서를 `tests/` 안에서 만들지 말고 **건너뛰고 보고에 적어라**)

## 검증

```bash
python3 -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|^FAILED"
python3 -m unittest discover -s tests -p "test_aimem_monitor_auth.py" -v 2>&1 | tail -40
ls -l .aimem/tls/   # 테스트가 실물 토큰을 건드리지 않았는지 확인 (수정 시각이 그대로여야 한다)
```

지금 전체는 **106건 OK** 다. 네 파일을 더한 뒤에도 **106 + 네 테스트 수**가 OK 여야 한다.

## 보고

첫 줄 상태. ① 새 파일 줄 수와 테스트 수 ② 위 세 명령의 **실제 출력 그대로**
③ 구현과 브리프가 어긋난 곳(있으면 어느 쪽이 맞다고 보는지) ④ 못 덮은 것.
