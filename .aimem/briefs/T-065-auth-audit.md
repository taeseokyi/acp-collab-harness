# T-065 관리자가 새로 쓴 인증·TLS 코드 적대적 검수 (읽기 전용)

## 왜

관리자가 방금 `tools/aimem_monitor/server.py` 에 **접근 제어와 HTTPS** 를 직접 구현했다
(태석님 요청 `Q-261109-407b`, 외부 공개). 관리자 코드를 관리자가 채점하면 사각지대가 영원히
남는다(`8.0-1`). 지난 라운드에 네가 같은 파일에서 결함 5건을 재현해 낸 선례가 있다.
**이번에는 인증이 대상이다 - 뚫리면 공개면 전체가 열린다.**

## 쓰기 경로

**없다. 읽기 전용이다.** 서버를 띄워 때려 보는 것은 **된다**(읽기다). 포트는 **18802** 를 써라.
끝나면 **PID 로** 내려라 - `pkill -f` 는 다른 작업자를 같이 죽인 사고가 있어 금지다.
저장소 파일을 만들거나 고치지 마라. **`.aimem/tls/` 아래 토큰 파일은 서버가 만든다** -
그 파일을 지우지 말고, 값을 보고에 적지도 마라(길이와 권한만 적어라).

## 읽을 것

```
tools/aimem_monitor/server.py      - 새 코드: 92~340행 근처(토큰/세션/TLS/LoginGuard) + Handler 의
                                     _send / _subject / _cookie_header / _issue_session / _path /
                                     _auth_gate / do_GET / do_POST / _login / _github_* / serve
tools/aimem_monitor/__init__.py    - 계약(AUTH_API, AUTH_EXEMPT_PATHS, SECURITY_HEADERS, 세션 쿠키 꼴)
```

세션 쿠키 꼴: `v1.<만료 epoch>.<subject>.<hex hmac>`,
mac = `HMAC-SHA256(키=접근 토큰 바이트, 메시지="v1.<exp>.<subject>")`.

## 직접 때려 보기

```bash
PYTHONPATH=tools python3 -m aimem_monitor --port 18802 --auth > /tmp/t65.log 2>&1 &
echo $! > /tmp/t65.pid ; sleep 2 ; cat /tmp/t65.log
TOK=$(cat .aimem/tls/access-token)
curl -s -o /dev/null -w "state 무인증 %{http_code}\n" http://127.0.0.1:18802/api/state
curl -s -o /dev/null -w "state Bearer %{http_code}\n" -H "Authorization: Bearer $TOK" http://127.0.0.1:18802/api/state
# ... 네가 생각한 공격을 여기에 ...
kill $(cat /tmp/t65.pid)
```

## 답할 질문 (이 순서로. 각 항목은 **재현 시도**가 원칙이다)

1. **인증 우회.** 토큰·쿠키 없이 보호 경로에 닿는 길이 있는가.
   - 경로 꼴: `/login/../api/state`, `//api/state`, `/./api/state`, `/api/state/`, `/api//state`,
     `/API/STATE`, `/login;/api/state`, `/api/state?x=/login`, `/login%2f..%2fapi%2fstate`,
     `/favicon.ico/../api/state`, 뒤에 점·공백·`%20` 붙이기
   - `_path()` 는 `posixpath.normpath` 로 접고 **퍼센트 디코딩은 하지 않는다**. 이 선택이
     면제 비교(`in AUTH_EXEMPT_PATHS`, 완전 일치)와 라우팅(`==`, `startswith("/api/runs/")`,
     `startswith("/static/")`) 사이에 **틈을 만드는지** 보라. 특히 `/static/` 과
     `"/" not in path[1:]` 평평한 자원 분기
   - `do_HEAD = do_GET` 이다. HEAD 로 인증이 달라지는가
2. **세션 위조.** `sign_session` / `verify_session` 을 깨 보라.
   - 서명 없는 쿠키, 잘린 mac, 대문자 mac, `exp` 를 키운 쿠키, `subject` 에 `.` ·`;` ·개행 ·
     `gh:` 접두사 위조, 같은 mac 재사용(**다른 exp 에 붙여 보라**), 토큰을 바꾼 뒤 옛 쿠키,
     `v2.` 버전, 쿠키 두 개 보내기, `Cookie:` 헤더를 여러 줄로 보내기
   - `hmac.compare_digest` 를 쓰는지, 비교 전에 **길이가 같은지** - 타이밍 차이가 실제로 측정되는가
     (측정이 안 되면 "미재현" 으로 적어라)
   - **만료가 실제로 막히는가.** `exp` 를 과거로 서명해 넣어 보라 (토큰 파일을 읽을 수 있으니
     직접 서명할 수 있다 - 그것이 이 검수의 권한이다)
3. **토큰 취급.** 접근 토큰이 로그·응답·`/api/state`·`/api/runs/<id>`·오류 메시지·
   `Server` 헤더·예외 추적에 실릴 길이 있는가. `.aimem/tls/` 디렉터리와 파일 **권한**을 확인하라
   (`stat -c '%a %n'`). 로그인 실패 로그에 토큰이 찍히는가. `--auth` 로 띄웠을 때 stderr 에
   토큰이 한 번만 찍히는가(새로 만들 때만이어야 한다)
4. **실패 제한(`LoginGuard`).** 1분에 5회 넘으면 지연이다. 우회 가능한가 -
   `X-Forwarded-For` 를 믿는가, IPv6, 동시 연결 다발, 지연이 스레드를 묶어 **정상 사용자의
   요청까지 막는지**(서비스 거부의 자해), 메모리 증가(IP 4096 초과 시 `clear()` 의 부작용 -
   **그 순간 모두의 실패 기록이 사라지는 것이 맞는가**)
5. **응답 헤더.** `SECURITY_HEADERS` 와 HSTS 가 **모든 응답**(401·403·302·정적 파일·오류 포함)에
   붙는가. `_redirect` 와 `_send` 가 어긋나지 않는가. CSP 가 `login.html` 의 인라인 스크립트를
   막지 않는가(`script-src 'unsafe-inline'` 이 들어 있는지)
6. **GitHub 분기** (환경변수가 없어 꺼져 있다 - **코드 판독으로**).
   `state` 쿠키 검증, `redirect_uri` 를 `Host` 헤더로 만드는 것의 위험(호스트 헤더 주입),
   허용 목록 파일이 없을 때 **빈 집합 = 전원 거부**가 맞는지, 로그인 문자열 정규화
   (`re.sub` 로 걸러 `subject` 를 만드는데 **다른 계정으로 충돌**할 수 있는가),
   토큰 교환에서 리다이렉트 미추종이 지켜지는가
7. **깨뜨리지 말아야 할 것.** `--tls`/`--auth` **없이** 띄우면 예전과 똑같이 동작하는가
   (`python3 -m unittest discover -s tests` 와 무인증 `GET /api/state` 200). 인증을 켰을 때
   `--once` 모드·HEAD·`Content-Length: 0` 이 깨지지 않는가

## 보고 형식

결함마다 네 줄: `[번호] 한 줄 요약` / `파일:줄` / `재현`(친 명령과 받은 출력, 또는 "미재현 - 코드 판독") /
`영향·고침`. 심각도 순. **"문제 없음" 으로 확인한 항목도 한 줄씩** 남겨라.
마지막에 **"공개 전에 반드시 막아야 할 것" 3건 이하.** 첫 줄은 상태.
