# T-063 공개 전 정보 유출 적대적 검수 (읽기 전용)

## 왜

이 웹 UI 는 지금까지 `127.0.0.1` 전용이었다. 태석님 지시(19:05)로 **외부에 공개**한다.
로컬 전용일 때는 "유출" 이 아니던 것이 공개되는 순간 유출이 된다. 관리자가 지금 인증·TLS 를
붙이는 중인데, **인증을 통과한 뒤에 보이는 것 중 무엇이 새면 안 되는지**를 먼저 알아야 한다.
너는 그걸 찾는다. 자기채점 금지 규칙(`8.0-1`)에 따라 **만들지 않은 슬롯이 검수한다.**

## 쓰기 경로

**없다. 읽기 전용이다.** 파일을 만들지도 고치지도 마라. 보고가 산출물이다.

## 볼 것

```
tools/aimem_monitor/reader.py          (557줄) - collect() / run_detail() 이 무엇을 담아 내보내는가
tools/aimem_monitor/server.py          (559줄) - /api/state, /api/runs/<id>, /api/health, POST /api/requests
tools/aimem_monitor/static/app.js      (1186줄) - 응답을 화면에 어떻게 넣는가 (innerHTML?)
tools/aimem_monitor/__init__.py        - 계약. KISTI 키 비노출 선언이 여기 있다
tools/fleet.py                         - 작업자 기록 `.aimem/runs/<id>.{json,brief.md,out,err,rc}` 의 생김새
```

읽기용 예시 데이터: `ls .aimem/runs | head`, `.aimem/runs/<id>.json` 한두 개, 그리고
`curl -s --max-time 5 http://127.0.0.1:18799/api/state` (서버가 떠 있다).

## 답할 질문 (이 순서로)

1. **비밀이 응답에 실리는가.** `/api/state` 와 `/api/runs/<id>` 의 **모든 필드**를 훑어 다음이
   흘러나올 길이 있는지 짚어라 - 환경변수(`KISTI_API_KEY`, `GITHUB_CLIENT_SECRET`, `ANTHROPIC_*`),
   접근 토큰(`.aimem/tls/access-token`), 슬롯 확인토큰(`a41f0c` 같은 6자리 - **이건 공개돼도
   되는 값인지 네 판단을 적어라**), 절대경로, 사용자명, 내부 IP, KISTI `/status` 원문.
   `run_detail` 의 `brief`/`report`/`stderr_tail`/`paths` 가 특히 넓다 - **브리프 본문과 stderr 에
   무엇이 적히는지 실제 파일로 확인해라**
2. **경로 탈출.** `/api/runs/<id>` 의 `RUN_ID_RE` 와 `reader.run_detail()` 의 `fullmatch` 가
   어긋나는 입력이 있는가. `/static/` 서빙의 `resolve()` + `relative_to()` 가 심볼릭 링크·
   대소문자·퍼센트 인코딩(`%2e%2e%2f`)·널바이트로 뚫리는가. **실제로 curl 로 때려 보고
   상태코드를 적어라**
3. **인증 우회면.** 관리자가 붙이는 면제 경로는 `/login`, `/api/login`, `/api/logout`,
   `/api/authinfo`, `/auth/github/start`, `/auth/github/callback`, `/favicon.ico` 뿐이다
   (`tools/aimem_monitor/__init__.py` 의 `AUTH_EXEMPT_PATHS`). 이 목록에 **경로 정규화 문제**가
   있는가 - `/login/../api/state`, `/LOGIN`, `/login%00`, 뒤에 `?`·`#`·슬래시가 붙은 꼴,
   `//api/state`, `/./api/state`. `urllib.parse.urlparse(self.path).path` 가 이것들을 어떻게
   돌려주는지 **파이썬으로 직접 찍어서** 확인해라
4. **쓰기면.** `POST /api/requests` 가 만드는 파일 이름(`_slug`)과 경로가 공격자 입력으로
   어디까지 움직이는가. 같은 이름 충돌, 디스크 채우기(본문 상한 `MAX_BODY`/`MAX_DETAIL`),
   `.aimem/requests/` 밖으로 나갈 길
5. **XSS.** `app.js` 가 서버 응답(요청 제목·본문·보고 본문·stderr)을 `innerHTML` 로 넣는 곳이
   있는가. 있으면 **어느 줄에서 어떤 값으로** 스크립트가 실행되는지 구체적으로

## 어떻게 보고하나

결함마다 다음 네 줄로. **재현되지 않은 추측은 "미재현" 이라고 명시해라** - 추측과 실측을
섞으면 관리자가 전부 다시 확인해야 한다.

```
[번호] 한 줄 요약
  파일:줄   (tools/aimem_monitor/server.py:505 처럼)
  재현      실제로 친 명령과 받은 출력 (또는 "미재현 - 코드 판독")
  영향·고침  공개 시 무엇이 새거나 뚫리는가 / 어떻게 막으면 되는가 (한두 줄)
```

심각도 순으로 정렬하고, **"문제 없음" 으로 확인한 항목도 한 줄씩 남겨라**(관리자가 같은 자리를
두 번 보지 않게). 마지막에 **"공개 전에 반드시 막아야 할 것" 3건 이하**로 추려라.

첫 줄은 상태(DONE / PARTIAL / BLOCKED).
