# T-062 로그인 화면 - `tools/aimem_monitor/static/login.html`

## 왜

함대 모니터 웹 UI 를 **외부에 공개**한다(태석님 요청 19:05, HTTPS 자체 인증서 + 접근 제어).
공개되면 토큰 없이는 아무것도 못 보게 막는데, 그 **토큰을 넣는 화면**이 없다. 그것을 만든다.
서버 쪽 인증(TLS·쿠키·401)은 **관리자가 같은 시각에 `server.py` 에 구현 중**이다 - 너는 화면만.

## 쓰기 경로

`tools/aimem_monitor/static/login.html` **새 파일 하나.** (필요하면 `static/style.css` 도 쓸 수
있지만 **쓰지 않는 쪽을 권한다** - 아래 "자족" 항 참조.) `server.py`·`reader.py`·`app.js` 는 건드리지 마라.

## 반드시 지킬 것 - 자족 (이게 보안 요건이다)

**`login.html` 은 외부 자원을 하나도 부르지 않는다.** CSS 와 JS 를 `<style>` / `<script>` 로
파일 안에 적어라. `style.css` 도, 폰트도, CDN 도 부르지 마라.

- 이유: 인증 전에 서버가 통과시키는 경로는 `/login` 하나뿐이다. `login.html` 이 `/static/style.css`
  를 부르면 그 요청은 **401 로 막혀 화면이 맨몸으로 뜬다.** 면제 경로를 늘리는 것은 그만큼
  공개면을 넓히는 것이라 하지 않는다
- 색은 `static/style.css` 의 `--st-*` 토큰 중 **필요한 것만 복사해** `:root` 에 적어라
  (`grep -n '^\s*--st-' tools/aimem_monitor/static/style.css` 로 값을 본다). 밝은 모드가 기본이다
  (태석님 2026-11-09 17:22). 본문 텍스트 대비 **4.5:1 이상**을 지켜라

## 서버 계약 (관리자가 못박았다. 이대로 부른다)

| 호출 | 응답 |
| --- | --- |
| `GET /api/authinfo` | `{"ok":true,"github_enabled":bool,"tls":bool,"authenticated":bool}` - 인증 없이 열린다 |
| `POST /api/login` `{"token":"<64자 hex>"}` | 성공 `200 {"ok":true,"redirect":"/"}` + 세션 쿠키 / 실패 `401 {"ok":false,"error":"..."}` |
| `GET /auth/github/start` | GitHub 로그인 시작. **`github_enabled` 이 true 일 때만 존재** (false 면 404) |

- 성공하면 `location.replace(data.redirect || '/')`
- 실패하면 화면에 `error` 문구를 띄운다. **연속 실패 시 서버가 응답을 수 초 지연시킨다** -
  버튼을 비활성화하고 "확인 중..." 을 보여라(이중 전송 방지)
- `github_enabled` 이 false 면 GitHub 버튼을 **DOM 에서 빼라**(숨기기만 하면 안 된다)

## 화면

- 가운데 카드 하나. 제목 "AIMEM 함대 모니터", 부제 한 줄로 "접근 토큰을 입력하십시오"
- `<form>` + `<input type="password" id="token" autocomplete="off" spellcheck="false">` + 제출 버튼
  - `<form>` 의 기본 제출을 막고(`e.preventDefault()`) `fetch` 로 보낸다
  - 입력값은 `trim()` 한다. 비어 있으면 서버를 부르지 말고 그 자리에서 안내
  - **토큰을 `localStorage`·`sessionStorage`·URL 쿼리·`document.cookie` 에 쓰지 마라.** 세션 쿠키는
    서버가 `Set-Cookie` 로 준다. 브라우저 저장소에 남기면 XSS 한 번에 통째로 샌다
- 오류 영역 `<p id="err" role="alert">` - **서버가 준 문자열을 `textContent` 로** 넣어라
  (`innerHTML` 금지)
- GitHub 버튼은 `<a href="/auth/github/start">` 한 줄이면 된다
- 접근성: `<label for="token">`, 포커스 링을 지우지 마라, 카드에 `aria-live="polite"` 영역 하나

## 검증 (이대로 돌리고 출력을 보고에 붙여라)

서버는 아직 `/login` 을 서빙하지 못할 수 있다(관리자가 구현 중). 그러면 **파일 자체를 검사해라.**

```bash
python3 -c "
import pathlib,html.parser,sys
p=pathlib.Path('tools/aimem_monitor/static/login.html'); t=p.read_text(encoding='utf-8')
print('bytes', len(t))
import re
ext=re.findall(r'(?:src|href)=\"([^\"]+)\"', t)
print('외부 참조:', [u for u in ext if not u.startswith('/auth') and not u.startswith('#')])
for bad in ('localStorage','sessionStorage','innerHTML','document.cookie','cdn','googleapis'):
    print(bad, bad in t)
class P(html.parser.HTMLParser):
    def error(self,m): raise SystemExit('HTML 파싱 실패: '+m)
P().feed(t); print('HTML 파싱 ok')
"
curl -s -o /dev/null -w "login 서빙 %{http_code}\n" --max-time 5 http://127.0.0.1:18799/login
```

"외부 참조" 목록은 **비어 있어야** 하고 `localStorage`/`sessionStorage`/`innerHTML`/`document.cookie`
는 **전부 False** 여야 한다.

## 보고

첫 줄 상태. ① 만든 파일과 줄 수 ② 위 검증 명령의 **실제 출력 그대로** ③ 쓴 `--st-*` 토큰과
대비비 계산(배경/글자 hex 와 비율 숫자) ④ 관리자가 `/login` 라우트를 붙일 때 알아야 할 것.

---

## 2차 시도 메모 (관리자, 19:31)

1차(`T-062-S3-a1-192301`, opencode/kistillm)는 **KISTI LLM 서버 장애**로 71초 만에
`Cannot connect to API` 로 죽었다. **산출물 없음 - `static/login.html` 은 존재하지 않는다.
처음부터 하라.** (`ls tools/aimem_monitor/static/` 에 `app.js`·`index.html`·`style.css` 셋뿐)

**서버 쪽 구현은 끝났다.** 관리자가 `server.py` 에 다음을 붙였고 지금 코드에 있다 -
`grep -n "api/authinfo\|def _login\|AUTH_EXEMPT" tools/aimem_monitor/server.py` 로 확인하라.

- `GET /login` → `static/login.html` 을 서빙한다 (인증 면제)
- `GET /api/authinfo` → `{"ok":true,"github_enabled":bool,"tls":bool,"auth_required":bool,"authenticated":bool}`
- `POST /api/login` 본문 `{"token":"<64자 hex>"}` → 성공 `200 {"ok":true,"redirect":"/"}`,
  실패 `401 {"ok":false,"error":"토큰이 맞지 않습니다"}`
  - **`Content-Type: application/json` 을 반드시 붙여라.** 안 붙이면 `/api/requests` 는 415 다
    (`/api/login` 은 아직 검사하지 않지만 같은 헤더로 보내라)
- `POST /api/logout` → 쿠키 삭제
- `GET /auth/github/start` → `github_enabled` 이 false 면 404

**직접 띄워서 확인할 수 있다** (포트 18801 을 쓰고 끝나면 PID 로 내려라 -
`pkill -f` 는 금지다. 다른 작업자를 같이 죽인 사고가 있었다):

```bash
PYTHONPATH=tools python3 -m aimem_monitor --port 18801 --auth > /tmp/t62.log 2>&1 &
echo $! > /tmp/t62.pid ; sleep 2 ; cat /tmp/t62.log
curl -s -o /dev/null -w "login %{http_code}\n" http://127.0.0.1:18801/login
curl -s http://127.0.0.1:18801/api/authinfo
curl -s -o /dev/null -w "state(무인증) %{http_code}\n" http://127.0.0.1:18801/api/state
kill $(cat /tmp/t62.pid)
```
