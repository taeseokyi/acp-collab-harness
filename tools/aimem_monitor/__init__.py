"""AIMEM 함대 모니터 - 공통 계약 (관리자 소유, `AIMEM.md` `6절`).

표준 라이브러리만 씁니다. 이 패키지는 **읽기 전용**이 원칙입니다 - 함대 상태(보드·큐·runs·
그래프)는 절대 고치지 않습니다. 쓰는 것은 **사람이 웹에서 누른 것**에 한합니다(전부 `server.py`,
감사 로그 `.aimem/access.log` 에 남김):
  - `.aimem/requests/<id>.json` 생성(POST) 과 **NEW 요청**의 제목·본문 수정(POST, 2026-11-10 승인)
  - 함대 제어 `tools/fleet_ctl.py` 호출(준비/실행/일시 중지/중지/라운드 실행 - `.aimem/fleet-mode.json`,
    `.aimem/relay/`)
  - 로그인 세션 쿠키 발급(파일 쓰기 없음, hmac 서명)
  - **슬롯 관리**(2026-11-10 태석님 지시): `POST /api/slots`(추가) / `/api/slots/<S>/set` / `/api/slots/<S>/remove` →
    `aimem_db.slot_*` (DB `slots` 정본 + `tools/fleet_slots.json` 거울). 모델은 `GET /api/models`(OpenClaw 가 설정한
    모델 = `openclaw models list` ∪ `openclaw.json` providers)에서만 고른다. 도는 작업자가 있는 슬롯은 삭제·하네스 변경 거절

계층:
  reader.py   파일 -> 딕셔너리 (AIMEM.md 파싱 / `.aimem/runs` 스캔 / ETA 추정)   [S1]
  server.py   딕셔너리 -> HTTP (JSON API + 정적 파일). **합류점 - 관리자 소유**
  static/     브라우저 (HTML+JS+CSS, 의존성 없음)                                 [S3]

**인터페이스는 관리자가 못박습니다.** 슬롯이 협의하면 병렬이 아니라 회의가 됩니다
(REV 102 선례: `envcheck` 의 `check() -> list[Result]`).

    reader.collect(root: pathlib.Path | None = None) -> dict   # STATE 스키마 (아래)
    reader.median_durations(runs: list[dict]) -> dict          # ETA 표본

실행:
    PYTHONPATH=tools python3 -m aimem_monitor          # 127.0.0.1:18799
"""

PORT = 18799
HOST = "127.0.0.1"

#: `/api/state` 의 최상위 키와 뜻. **공개면의 정본입니다** (REV 114, 공개면 2차).
#:
#: `reader.collect()` 는 이보다 **많이** 돌려줄 수 있습니다 - 예를 들어 `root`(저장소
#: 절대경로)는 reader 내부 계산에 쓰이지만 `server.collect_state()` 가 내보내기 전에
#: 떼어냅니다. 외부에 공개되는 순간 경로 구조가 새는 값이고 프런트는 쓰지 않습니다
#: (S4 유출 검수 5번). 같은 이유로 `slots[].token`(작업자 확인토큰)과
#: `kisti.url`(상류 엔드포인트)도 여기 없습니다. **이 표에 없는 키는 공개면에
#: 나가지 않아야 합니다** - `PUBLIC_FORBIDDEN` 이 그것을 코드로 못박습니다.
STATE_KEYS = {
    "generated": "ISO8601(초) 수집 시각",
    "aimem": "{rev, lines, updated, goal:{text, status}}  - DB 의 REV + AIMEM.md 1절",
    "slots": "[{slot, harness, role, note, model, model_source}]  - 명부 + 하네스 설정 모델",
    "board": "[{id, task, slot, status, handoff, artifact}]  - 작업 보드",
    "queue": "[{order, task, slots, handoff, note}]  - 대기 큐",
    "log": "[{when, text}]  - 핸드오프 로그, 최신 먼저",
    "runs": "[{id, slot, harness, model, label, rev, write, started, state, rc, elapsed_sec, report_head, "
            "task, project, round}]  - project/round 는 식별자에 붙이지 않고 따로 (없으면 null)",
    "eta": "{by_harness:{<h>:{median_sec, samples, source}}, overall:{median_sec, samples}}",
    "requests": "[{" + ", ".join(REQUEST_ROW_KEYS := (
                    "id", "created", "updated", "requester", "project", "title", "detail", "detail_truncated", "detail_len",
                    "status", "subtasks", "graph", "progress_pct", "eta_sec", "eta_at", "eta_basis", "eta_over")) + "}]"
                "  - 행 키는 REQUEST_ROW_KEYS 가 정본, scrub_public 이 그 밖의 키를 떼어냅니다",
    "errors": "[문자열]  - 파싱 중 삼킨 문제. 비어 있어야 정상",
}

#: `reader.collect()` 가 아니라 **서버가 덧붙이는** 최상위 키. `reader` 는 파일만 읽고
#: 네트워크·외부 도구를 타지 않으므로 여기 둡니다(계층 분리, REV 111).
SERVER_KEYS = {
    "kisti": "{ok, fetched, age_sec, stale, pending, dropped, busy, queued, phase, "
             "prompt_tokens, generated, max_tokens, reasoning_recoveries, thinking_budget, error}",
    "graphs": "[{id, request, created, updated, percent, eta_seconds, eta_at, counts, nodes:[...], source}]",
    # 관리자 ACP 세션 (요청 Q-261110-549a, 2026-11-10). `openclaw sessions` 배경 갱신 30초 캐시.
    # 세션 키 원문은 싣지 않고 uuid 앞 8자(id)만 싣습니다.
    "managers": "{ok, pending, age_sec, error, sessions:[{label, status, started, updated, id, record_kb, "
                "last_activity, steps, last_step}]}",
    # 함대 제어 상태 (`tools/fleet_ctl.public_state`, 2026-11-10). can = 지금 누를 수 있는 동작
    "fleet": "{mode, label, at, by, note, default, running_runs, graphs, brief, prepare, relay, "
             "can:{prepare, run, pause, stop, round}, idle, last_round:{round, label, at, state, report_status, report}, chain:{on, project, max_rounds, rounds_done, goals_done, stopped_why, last}}",   # idle = '실행' 인데 도는 것이 없다(라운드 끝)
    # 프로젝트 목록 (2026-11-10) - `projects/` 아래 폴더 + 요청이 가리키는 이름. exists = 폴더가 이미 있나
    # percent = 목표 대비(`PROGRESS.md` 의 `## 목표` 체크리스트, basis "goals") - 목표가 없으면 요청들의 평균(basis "requests").
    # goals = {total, done} 또는 null. request_percent = 요청 평균(늘 실음). rounds = `rounds/R<N>/round.json`(띄운 기록) + `PROGRESS.md` 의 `## R<N>`.
    # summary = `projects/<이름>/PROGRESS.md` 의 가장 최근 라운드 항목
    # app = 실행 선언(`projects/<이름>/app.json`). {runnable, url, title, root, entry, reason} 또는 null
    "projects": "[{name, path, exists, percent, basis, goals:{total, done}, request_percent, requests:{total, done, new, active}, rounds, round_count, first_round, "
                "last_round, last_round_at, updated, summary, app}]",
}

#: 공개면에서 **절대 나가면 안 되는** 것 (REV 114, S4 유출 검수 5번).
#:  - 최상위: 키 이름
#:  - `slots[]` 행: 키 이름
#:  - `kisti`: 키 이름
#: `server.collect_state()` 가 내보내기 직전에 이 세 묶음을 떼어냅니다. 키를 지우는
#: 것만으로는 모자랍니다 - 값이 다른 필드(예: 오류 문자열)에 섞여 나가는 길이
#: 남으므로 그쪽도 가립니다(`_scrub_upstream`).
PUBLIC_FORBIDDEN = {"top": ("root", "paths"), "slot": ("token",), "kisti": ("url",)}

#: 요청 생성(`POST /api/requests`) 속도 제한 (S4 유출 검수 3번, REV 114).
#: 개수 상한(`MAX_REQUESTS`)은 디스크가 차는 **끝점**만 막습니다 - 그 사이에
#: 초당 수십 건이 들어오면 `/api/state` 가 매 폴링마다 그 디렉터리를 통째로 읽어
#: 화면이 먼저 멈춥니다. **IP 당** 창 안의 성공 건수로 셉니다.
REQUEST_RATE_MAX = 5
REQUEST_RATE_WINDOW_SEC = 60
#: **거절된 요청의 별도 한도.** 성공만 세면 400 은 무제한이 됩니다 - S4 실측에서
#: 60KB 본문의 무효 POST 300건이 전부 400 으로 받아들여졌습니다(429 0건). 매 건이
#: 본문을 읽고 요청 디렉터리를 세므로 CPU·IO 는 그대로 나갑니다. 성공 한도보다
#: 넉넉히 두어 **폼을 고쳐 다시 내는 사람은 걸리지 않게** 합니다.
REQUEST_FAIL_MAX = 20

#: 공개면에 싣는 `requests[].detail` 의 글자 수 상한 (`4.5` 큐 13번, REV 115).
#: 요청 본문은 웹 폼에서 들어오고 서버는 **64KB 까지** 받습니다. 그 전문을 매
#: 폴링(5초)마다 모든 요청에 대해 내보내면 `/api/state` 가 요청 하나에 수십 KB 씩
#: 불어납니다 - 목록 화면은 어차피 몇 줄만 보여 줍니다. **자르는 자리는 공개
#: 직전 한 군데**(`scrub_public`)이고, 원본은 `.aimem/requests/<id>.json` 에 그대로
#: 남습니다. 잘렸다는 사실을 숨기지 않으려고 `detail_truncated`/`detail_len` 을
#: 같이 싣습니다 - 화면이 "일부만 보고 있다"고 말할 수 있어야 합니다.
REQUEST_DETAIL_MAX = 600

#: `reader.run_detail(run_id)` 의 최상위 키 (REV 111, 요청 8d8d "상세 조회 UI").
#: **서버·프런트·테스트가 이 튜플 하나를 본다** - 세 군데서 따로 적으면 어긋납니다.
RUN_DETAIL_KEYS = ("id", "found", "slot", "harness", "model", "label", "status", "rc",
                   "elapsed_s", "started", "ended", "brief", "report", "stderr_tail",
                   "paths", "errors")

#: run id 꼴. 경로 탈출(`../`)과 절대경로를 여기서 한 번에 막습니다.
#: run id 꼴 **두 가지**를 받습니다.
#:  - 새 체계(태석님 2026-11-09 18:15, `fleet.py:405`): `<태스크>-<슬롯>-a<시도>-<HHMMSS>`
#:    예 `T-053-S3-a3-181328` / 태스크 없는 임시 실행은 `ADHOC-S3-a1-181328`
#:  - 옛 체계: `20261109-172618-S3`. **`.aimem/runs/` 에 그대로 남아 있으므로 계속 받습니다**
#: `$` 가 아니라 `\Z` 입니다 - `$` 는 끝의 줄바꿈 앞에서도 맞아서 `"<id>\n"` 이 통과합니다.
#: `reader.run_detail()` 은 `fullmatch` 로 거르므로 둘이 어긋납니다.
RUN_ID_RE = (r"(?:[0-9]{8}-[0-9]{6}-S[0-9]+"
             r"|(?:T-[0-9]+[A-Z]?|ADHOC)-S[0-9]+-a[0-9]+-[0-9]{6})(-[0-9]+)?\Z")

#: KISTI LLM 서버 상태 엔드포인트. S2·S3 작업자(kistillm)가 실제로 돌고 있는지 보는 창입니다.
#: **키는 환경변수에서만 읽고 `/api/state` 로 내보내지 않습니다** - 프런트는 결과만 봅니다.
KISTI_STATUS_URL = "https://aida.kisti.re.kr:10430/status"
KISTI_API_KEY_ENV = "KISTI_API_KEY"
KISTI_CACHE_SEC = 10        # 프런트가 5초 폴링이라 매번 외부를 때리지 않도록
KISTI_TIMEOUT_SEC = 3.0     # 막히면 화면 전체가 멈추므로 짧게 끊습니다

#: `/status` 응답에서 그대로 통과시킬 필드. 모르는 필드는 버립니다 - 외부 응답이
#: 커지거나 바뀌어도 우리 스키마가 따라 흔들리지 않게 하기 위해서입니다.
KISTI_FIELDS = ("busy", "queued", "phase", "prompt_tokens", "generated",
                "max_tokens", "reasoning_recoveries", "thinking_budget")

#: 타입까지 못박습니다. 외부가 `busy:"yes"` / `queued:{...}` 를 보내도 프런트가
#: 숫자·불리언을 가정하고 렌더링하다 깨지지 않게, 어긋나는 필드는 버리고
#: `dropped` 에 이름만 남깁니다 (S4 적대적 검수 9번, REV 111).
KISTI_FIELD_TYPES = {
    "busy": bool, "queued": int, "phase": str, "prompt_tokens": int,
    "generated": int, "max_tokens": int, "reasoning_recoveries": int,
    "thinking_budget": int,
}

#: 태스크 그래프 파일 위치 (`tools/fleet_graph.py` 가 씁니다). 서버는 읽기만 합니다.
GRAPH_DIR = ".aimem/graph"

#: 요청 파일 `.aimem/requests/<id>.json` 의 상태 값.
REQUEST_STATES = ("NEW", "PLANNED", "IN-PROGRESS", "DONE", "REJECTED")
#: 닫힌 요청 - 진행율·ETA 는 서브태스크가 아니라 **이 상태가** 정합니다 (`reader._estimate`, 2026-11-10).
REQUEST_CLOSED_STATES = ("DONE", "REJECTED")

#: 서브태스크 상태 -> 진행율 가중치. `3절` 상태 값과 같은 어휘를 씁니다.
#: 평균 x 100 이 요청 단위 진행율입니다.
PROGRESS_WEIGHTS = {
    "TODO": 0.0,
    "ASSIGNED": 0.1,
    "IN-PROGRESS": 0.5,
    "REVIEW": 0.8,
    "DONE": 1.0,
    "BLOCKED": 0.0,
}

#: 작업자 실행 상태. `fleet.py` `_run_state()` 와 같은 어휘여야 합니다.
RUN_STATES = ("running", "done", "lost", "unknown")

# ----------------------------------------------------------------------------
# 외부 공개 (요청 `Q-261109-407b`, 태석님 19:05) - HTTPS + 접근 제어 계약
#
# **관리자가 못박습니다.** `server.py`(구현) / `tests/test_aimem_monitor_auth.py`(S2) /
# `static/login.html`(S3) 세 군데가 이 이름만 봅니다. 셋이 따로 적으면 어긋납니다.
# 표준 라이브러리만 씁니다 (`ssl` / `hmac` / `hashlib` / `secrets`).
# ----------------------------------------------------------------------------

#: TLS 자료와 접근 토큰이 사는 곳. **`.gitignore` 대상이고 키는 0600 입니다.**
TLS_DIR = ".aimem/tls"
CERT_FILE = ".aimem/tls/server.crt"
KEY_FILE = ".aimem/tls/server.key"
TOKEN_FILE = ".aimem/tls/access-token"               # 32바이트 hex(64자), 0600
#: 서버 인증서를 서명한 사설 CA 의 공개 인증서 사본 (2026-11-10, 태석님 지시 - carefor-app·
#: Signposts_of_Faith 와 **같은 CA** 를 쓴다. 윈도우 신뢰 루트에 그 CA 가 이미 있어 서비스마다
#: 인증서를 설치할 필요가 없다). 자체 서명일 때는 없을 수 있다. CA **개인키**는 저장소 밖에 산다.
CA_FILE = ".aimem/tls/ca.crt"
#: `admin cert renew` 가 마지막 발급 조건(CA 디렉터리·추가 SAN)을 적어 두는 곳. 다음 `renew` 는
#: 인자가 없어도 이것을 그대로 다시 쓴다 - 갱신 때 SAN 하나를 빠뜨려 브라우저 경고가 돌아오지 않게.
CERT_PROFILE_FILE = ".aimem/tls/cert-profile.json"
#: 프로젝트 (2026-11-10 태석님 지시) - 여러 라운드를 묶는 단위. 결과물은 `projects/<이름>/` 한 곳에 쌓인다.
#: 요청마다 프로젝트를 고른다(빈 값 = 함대 자체의 일). 이름은 한 폴더 이름이라 구분자·점·공백을 받지 않는다.
PROJECTS_DIR = "projects"
PROJECT_NAME_RE = r"\A[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]{0,39}\Z"

# 결과물은 모니터와 같은 출처(origin)에서 내려가지만 화면은 그것을 `sandbox` iframe(불투명 출처)에 넣습니다.
# 그래서 결과물 코드는 `/api/*` 를 인증된 세션 쿠키로 부를 수 없습니다. 불투명 출처에서는 CSP 의
# `'self'` 가 아무것도 가리키지 못하므로, `/app/` 응답의 CSP 는 요청의 Host 로 만든 출처를 직접 적습니다.
# 프로젝트는 `app.json` 한 장으로 "내 웹앱은 여기 있다" 고 선언합니다. 선언이 없으면 실행 경로도 없습니다.

#: 프로젝트가 "내 웹앱은 여기 있다" 고 적는 선언 파일. 없으면 그 프로젝트는 실행할 수 없습니다.
PROJECT_APP_MANIFEST = "app.json"
#: 실행 경로 접두. `/app/<프로젝트>/<앱 안의 상대 경로>`
PROJECT_APP_URL_PREFIX = "/app/"
#: 실행 경로가 내려 주는 한 파일의 크기 상한.
PROJECT_APP_FILE_MAX_BYTES = 8 * 1024 * 1024
#: `/app/` 경로 티켓. 불투명 출처(sandbox) 안에서는 SameSite=Strict 쿠키가 실리지 않아
#: 세션으로는 하위 요청을 인가할 수 없습니다. 그래서 **경로 앞에 박는 짧은 HMAC 티켓**을 씁니다.
#: 티켓 하나는 프로젝트 하나의 정적 파일만, TTL 동안만 열어 줍니다.
PROJECT_APP_TICKET_PREFIX = "~"
PROJECT_APP_TICKET_TTL_SEC = 12 * 3600

GITHUB_ALLOW_FILE = ".aimem/tls/allowed-github-logins"   # 한 줄 한 계정, `#` 주석 허용

#: 세션 쿠키. `Secure` 는 TLS 일 때만 붙습니다(http 로컬 검증에서 쿠키가 죽지 않도록).
SESSION_COOKIE = "aimem_session"
SESSION_TTL_SEC = 12 * 3600
#: 쿠키 값 = `v1.<만료 epoch>.<subject>.<hex hmac>`.
#: mac = HMAC-SHA256(키=접근 토큰 바이트, 메시지=`v1.<exp>.<subject>`).
#: **접근 토큰을 갈아 끼우면 발급된 세션이 전부 무효가 됩니다** - 그것이 회수 수단입니다.
SESSION_VERSION = "v1"
#: subject 어휘: 토큰 로그인은 `token`, GitHub 로그인은 `gh:<login>`.
SESSION_SUBJECT_TOKEN = "token"
SESSION_SUBJECT_GITHUB_PREFIX = "gh:"

#: 인증 없이 통과하는 경로. **여기에 무엇을 더하든 그것은 공개입니다.**
#: 로그인 화면은 자족적이어야 합니다 - `login.html` 하나로 끝나고 외부 자원을
#: 부르지 않습니다(부르면 그 경로도 면제 목록에 들어가야 하므로).
AUTH_EXEMPT_PATHS = ("/login", "/api/login", "/api/logout", "/api/authinfo",
                     "/auth/github/start", "/auth/github/callback", "/favicon.ico",
                     "/api/github/device/start", "/api/github/device/poll",
                     # 폰 설치(PWA, 2026-11-10) - 매니페스트·아이콘·서비스 워커는 데이터가 없는 껍데기라 공개해도 되고,
                     # 공개해야 로그인 화면에서도 '앱 설치' 가 뜬다. `app.js`·`/api/*` 는 그대로 인증 뒤다.
                     "/manifest.webmanifest", "/sw.js", "/icon-192.png", "/icon-512.png",
                     "/icon-maskable-512.png", "/apple-touch-icon.png")

#: 로그인 실패 제한 - IP 당 1분에 5회를 넘으면 지연으로 갚게 합니다.
LOGIN_FAIL_WINDOW_SEC = 60
LOGIN_FAIL_MAX = 5
LOGIN_FAIL_DELAY_SEC = 2.0

#: 공개 시 항상 붙는 응답 헤더. HSTS 는 **TLS 일 때만** 붙입니다
#: (http 에 붙이면 브라우저가 그 호스트를 https 로 못박아 로컬 검증이 막힙니다).
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; "
                                "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
}
HSTS_HEADER = ("Strict-Transport-Security", "max-age=31536000")

#: GitHub OAuth 는 **환경변수가 둘 다 있을 때만** 켜집니다. 없으면 버튼을 숨깁니다.
GITHUB_CLIENT_ID_ENV = "GITHUB_CLIENT_ID"
GITHUB_CLIENT_SECRET_ENV = "GITHUB_CLIENT_SECRET"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_STATE_COOKIE = "aimem_oauth_state"
GITHUB_CALLBACK_PATH = "/auth/github/callback"
#: 기기 흐름(RFC 8628, 2026-11-10 태석님 지시 - reefwiz-esp32 가 쓰는 OAuth App 을 같이 쓴다).
#: `GITHUB_CLIENT_ID` 만 있고 시크릿이 없으면 이 흐름이다. 콜백 주소가 없어 접속 주소(내부 IP·외부 주소·포트)에
#: 묶이지 않고, 시크릿도 없다. 화면에 뜬 코드를 github.com/login/device 에 넣어 승인한다.
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_DEVICE_VERIFY_URL = "https://github.com/login/device"
GITHUB_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
GITHUB_DEVICE_COOKIE = "aimem_gh_device"
GITHUB_DEVICE_START_PATH = "/api/github/device/start"
GITHUB_DEVICE_POLL_PATH = "/api/github/device/poll"
GITHUB_DEVICE_MAX_PENDING = 8          # 동시에 열려 있는 확인 코드 수(전체). IP 하나에는 하나

#: `server.py` 가 제공하는 인증 함수 이름 - **테스트와 구현이 보는 유일한 목록**입니다.
AUTH_API = {
    "ensure_access_token(root, create=True)": "(토큰문자열, 새로만들었나) - 없으면 32바이트 hex 생성·0600",
    "load_access_token(root)": "토큰 문자열 또는 None (파일이 없거나 꼴이 아니면 None)",
    "sign_session(token, subject, exp_epoch)": "쿠키 값 문자열",
    "verify_session(token, cookie_value, now=None)": "{'subject','exp'} 또는 None (만료·변조·꼴 불일치는 None)",
    "build_ssl_context(root)": "ssl.SSLContext - 인증서/키가 없으면 SystemExit",
    "github_enabled()": "환경변수 둘 다 있으면 True",
    "github_allowed_logins(root)": "허용 로그인 집합 (소문자, 파일 없으면 빈 집합)",
    "LoginGuard().check(ip)": "지연해야 할 초(0.0 이면 즉시 허용)",
    "LoginGuard().fail(ip)": "실패 1회 기록",
    "LoginGuard().reset(ip)": "성공 시 해당 IP 기록 삭제",
    "serve(host, port, root, once=False, tls=False, auth=None)": "auth=None 이면 tls 값을 따름",
}

#: 인증이 걸렸을 때의 응답 규칙 (S2 가 이것을 테스트합니다).
#:  - `/api/*`·정적 자원·그 외 전부: 쿠키/Bearer 없으면 **401** JSON `{"ok": false, "error": …}`
#:  - `GET /` `GET /index.html` 만 예외로 **302 -> /login** (브라우저가 바로 로그인 화면을 보도록)
#:  - `Authorization: Bearer <접근 토큰>` 은 쿠키 없이도 통과 (curl 검증용)
AUTH_UNAUTH_REDIRECT_PATHS = ("/", "/index.html")
#: 인증이 없을 때 로그인 화면으로 **보내 주는** 경로 접두 (`AUTH_UNAUTH_REDIRECT_PATHS` 의 접두판).
#: 결과물을 새 탭에서 열었는데 JSON 401 이 뜨면 사람이 막힙니다.
AUTH_UNAUTH_REDIRECT_PREFIXES = ("/app/",)
