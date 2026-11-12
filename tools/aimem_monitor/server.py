#!/usr/bin/env python3
"""AIMEM 함대 모니터 - HTTP 계층 (관리자 소유, `AIMEM.md` `6절`).

**합류점입니다.** `reader.py`(S1) 의 딕셔너리를 그대로 JSON 으로 내보내고
`static/`(S3) 을 그대로 서빙합니다. 여기서 데이터를 가공하지 않습니다 -
가공을 두 군데서 하면 프런트와 테스트가 어느 쪽을 믿을지 알 수 없게 됩니다.

    PYTHONPATH=tools python3 -m aimem_monitor              # 127.0.0.1:18799
    PYTHONPATH=tools python3 -m aimem_monitor --port 18800 --once

라우트:
    GET  /                 -> static/index.html
    GET  /static/<파일>    -> static/ 아래 파일 (경로 탈출 차단)
    GET  /api/state        -> reader.collect() + 서버가 붙이는 graphs / managers
    GET  /api/health       -> {"ok": true, "rev": N}  (reader 가 없어도 응답한다)
    GET  /api/runs/<id>    -> reader.run_detail(). 상세 패널용 (브리프·보고·rc·경과)
    POST /api/requests     -> .aimem/requests/<id>.json 생성
    GET  /api/requests/<id> -> 요청 하나의 전문 (목록은 600자로 잘림)
    GET  /api/projects/<이름>/files, /file?path= -> 프로젝트 결과물 목록·본문 (텍스트, 가림 적용)
    GET  /app/<이름>/<경로> -> `app.json` 이 선언한 앱 폴더의 정적 파일 (인증 뒤, /app/ CSP)
    GET  /api/managers/<id8> -> 관리자 세션 상세 (최근 단계·라운드 전달·이벤트·그래프, 도구 출력 제외)
    POST /api/requests/<id>/edit -> NEW·미분담 요청의 제목·본문 수정 (Q-261110-549a)
    POST /api/fleet/<동작> -> 함대 제어 prepare|run|pause|stop|round (tools/fleet_ctl.py)
    GET  /login            -> static/login.html (인증 면제)
    GET  /api/authinfo     -> {github_enabled, tls, auth_required, authenticated} (면제)
    POST /api/login        -> 토큰 -> 세션 쿠키 / POST /api/logout -> 쿠키 삭제
    GET  /auth/github/*    -> 선택적 GitHub 로그인 (환경변수가 있을 때만)

**쓰기는 셋뿐입니다:** 요청 파일 생성, NEW·미분담 요청의 제목·본문 수정(태석님 승인
2026-11-10), 함대 제어(`/api/fleet/<동작>` → `tools/fleet_ctl.py`, `.aimem/fleet-mode.json`).
그 외 모든 경로는 읽기 전용입니다 (원래 제약: 태석님 2026-11-09 "요청 파일 생성 하나뿐"). 요청 파일은 관리자가 분담하며 손으로 채웁니다 -
서버는 `status: "NEW"` / `subtasks: []` 로만 만듭니다.

**기본은 로컬 전용입니다** - `127.0.0.1` 바인드, 인증 없음. 옛 동작 그대로입니다.
외부 공개는 `--tls` 로만 합니다 (태석님 요청 `Q-261109-407b`, 2026-11-09 19:05):

    PYTHONPATH=tools python3 -m aimem_monitor --tls --host 0.0.0.0

`--tls` 는 자체 인증서(`.aimem/tls/server.{crt,key}`)로 HTTPS 를 걸고 **인증을 함께
켭니다**(`--no-auth` 로 끌 수 있으나 권하지 않습니다). 인증이 켜지면 `/login` 과
`/api/login`·`/api/authinfo`·`/auth/github/*` 를 뺀 **모든 경로**가 세션 쿠키 또는
`Authorization: Bearer <접근 토큰>` 을 요구합니다. 계약은 `__init__.py` 의 `AUTH_API`.
"""
import collections
import datetime
import hashlib
import hmac
import http.cookies
import ipaddress
import http.server
import json
import os
import pathlib
import posixpath
import re
import subprocess
import shutil
import secrets
import socket
import signal
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import (AUTH_EXEMPT_PATHS, AUTH_UNAUTH_REDIRECT_PATHS, AUTH_UNAUTH_REDIRECT_PREFIXES, CERT_FILE,
               GITHUB_ALLOW_FILE, GITHUB_AUTHORIZE_URL, GITHUB_CALLBACK_PATH,
               GITHUB_CLIENT_ID_ENV, GITHUB_CLIENT_SECRET_ENV, GITHUB_DEVICE_CODE_URL,
               GITHUB_DEVICE_COOKIE, GITHUB_DEVICE_GRANT, GITHUB_DEVICE_MAX_PENDING,
               GITHUB_DEVICE_POLL_PATH, GITHUB_DEVICE_START_PATH, GITHUB_DEVICE_VERIFY_URL,
               GITHUB_STATE_COOKIE,
               GITHUB_TOKEN_URL, GITHUB_USER_URL, GRAPH_DIR, HOST, HSTS_HEADER,
               KEY_FILE, KISTI_API_KEY_ENV,
               LOGIN_FAIL_DELAY_SEC, LOGIN_FAIL_MAX, LOGIN_FAIL_WINDOW_SEC, PORT,
               PUBLIC_FORBIDDEN, REQUEST_DETAIL_MAX, REQUEST_FAIL_MAX,
               REQUEST_RATE_MAX, REQUEST_RATE_WINDOW_SEC,
               PROJECT_APP_FILE_MAX_BYTES, PROJECT_APP_MANIFEST, PROJECT_APP_URL_PREFIX,
               PROJECT_APP_TICKET_PREFIX, PROJECT_APP_TICKET_TTL_SEC,
               REQUEST_STATES, RUN_DETAIL_KEYS, RUN_ID_RE, SECURITY_HEADERS,
               SESSION_COOKIE, SESSION_SUBJECT_GITHUB_PREFIX, SESSION_SUBJECT_TOKEN,
               SESSION_TTL_SEC, SESSION_VERSION, TLS_DIR, TOKEN_FILE, REQUEST_ROW_KEYS,
               PROJECTS_DIR, PROJECT_NAME_RE)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATIC = pathlib.Path(__file__).resolve().parent / "static"
REQUESTS = ROOT / ".aimem" / "requests"

#: 요청 본문 상한 **64KB** (태석님 공개 요건 2026-11-09 19:05).
#: 로컬 전용일 때는 실수로 거대한 붙여넣기를 막는 선이었지만, 공개되는 순간
#: 디스크를 채우는 가장 싼 길이 됩니다. 본문 상한은 `MAX_DETAIL` 과 **둘 다** 겁니다 -
#: 이쪽은 바이트, 저쪽은 글자라 한글에서 서로 다른 선이 됩니다.
MAX_BODY = 64 * 1024
MAX_TITLE = 200
#: 요청 파일 개수 상한 (S4 검수 3번). 넘으면 관리자가 아카이브해야 합니다.
MAX_REQUESTS = 500
MAX_DETAIL = 20_000

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
    ".wasm": "application/wasm",
    ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
}


# ===========================================================================
# 접근 제어 + TLS  (요청 `Q-261109-407b`, 태석님 19:05)
#
# 계약은 `__init__.py` 의 `AUTH_API` 가 못박습니다. 여기는 구현입니다.
# **`--tls` 또는 `--auth` 없이는 아무것도 달라지지 않습니다** - 기존 http 로컬
# 동작을 깨지 않는 것이 공개 작업의 전제 조건입니다(태석님).
# ===========================================================================

#: 로그에 그대로 찍히면 안 되는 제어문자 치환표 (S4 검수 7번).
_LOG_SAFE = {c: f"\\x{c:02x}" for c in list(range(0x20)) + [0x7f]}

#: 로그에 남는 `/app/~<티켓>/` 의 티켓을 가립니다. 티켓은 12시간짜리 인가 수단이라
#: 로그를 읽을 수 있는 쪽이 그대로 다시 쓸 수 있습니다 (R11 검수 A 결함 2).
_TICKET_LOG_RE = re.compile(r"/app/(?:~|%7[Ee])[^/\s]+")


def log_line(text):
    """서버가 직접 찍는 글의 **모든 줄** 앞에 ISO 초 단위 시각을 붙입니다.

    아카이브(`aimem_db.py`)는 ISO 시각으로 시작하는 줄만 옮깁니다. 여러 줄짜리
    글도 줄마다 머리가 있어야 줄 단위로 가져갈 수 있습니다.
    """
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    for line in str(text).splitlines():
        line = _TICKET_LOG_RE.sub("/app/~***", line).translate(_LOG_SAFE)
        sys.stderr.write(f"{stamp} {line}\n")


_TOKEN_RE = re.compile(r"\A[0-9a-f]{64}\Z")
#: subject 에 `.` 이 들어가면 쿠키 파싱이 어긋납니다. 들어올 수 있는 값은
#: `token` 과 `gh:<login>` 뿐이고 GitHub 로그인에는 점이 없습니다 - 그래도 못박습니다.
_SUBJECT_RE = re.compile(r"\A[A-Za-z0-9_:-]{1,80}\Z")


def _tls_dir(root):
    return pathlib.Path(root) / TLS_DIR


def load_access_token(root=ROOT):
    """접근 토큰 문자열 또는 None. **꼴이 아니면 None 입니다** - 빈 파일이나
    편집 중 잘린 파일을 토큰으로 받아들이면 그 값으로 서명한 세션이 통과합니다.

    **읽기도 `O_NOFOLLOW` 입니다** (`4.5` 큐 3번, REV 115). `ensure_access_token()`
    은 쓸 때 심볼릭 링크를 거부했는데 읽기는 `read_text` 라 **따라갔습니다** - 토큰
    파일 자리를 링크로 바꿔치기하면, 쓰기는 막히지만 서버가 뜰 때 그 링크가 가리키는
    아무 파일이나 접근 토큰으로 읽혔습니다. 한쪽만 막으면 막은 것이 아닙니다.
    `_TOKEN_RE` 가 64자 hex 만 받으므로 아무 파일이나 통과하지는 않지만, 그 꼴을
    가진 파일(다른 서비스의 키 등)을 겨냥하면 그대로 성립합니다.
    """
    path = pathlib.Path(root) / TOKEN_FILE
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        # ELOOP(심볼릭 링크) · ENOENT · EACCES 를 구분하지 않습니다 - 어느 쪽이든
        # "쓸 수 있는 토큰이 없다" 이고, 구분해 말하면 파일 존재 여부가 샙니다.
        return None
    try:
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            raw = f.read(4096).strip()
    except (OSError, UnicodeDecodeError):
        return None
    return raw if _TOKEN_RE.match(raw) else None


def ensure_access_token(root=ROOT, create=True):
    """(토큰, 새로 만들었나). 없으면 32바이트 hex 를 **0600 으로** 만듭니다."""
    tok = load_access_token(root)
    if tok:
        return tok, False
    if not create:
        return None, False
    d = _tls_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    tok = secrets.token_hex(32)
    path = pathlib.Path(root) / TOKEN_FILE
    # **꼴이 깨진 기존 파일을 말없이 덮지 않습니다** (S4 검수 9번). 덮으면 사람이 손으로 적어 둔
    # 토큰이 조용히 바뀌고, 새 값이 stderr 로 나갑니다. 지우는 것은 사람의 일입니다.
    if path.exists():
        sys.exit(f"접근 토큰 파일이 있는데 꼴이 아닙니다(64자 hex 여야 함): {path}\n"
                 "  내용을 확인하고 직접 지우거나 고친 뒤 다시 띄우십시오.")
    # `O_EXCL`: 경쟁하는 프로세스가 먼저 만들었으면 실패합니다.
    # `O_NOFOLLOW`: 심볼릭 링크로 바꿔치기한 자리에 쓰지 않습니다.
    # **권한을 먼저 0600 으로** 잡습니다 - 열어 놓고 나중에 chmod 하면 그 사이에 읽힙니다.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (tok + "\n").encode("ascii"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return tok, True


def sign_session(token, subject, exp_epoch):
    """세션 쿠키 값 `v1.<exp>.<subject>.<hex mac>`."""
    if not _SUBJECT_RE.match(subject or ""):
        raise ValueError(f"subject 꼴이 아닙니다: {subject!r}")
    payload = f"{SESSION_VERSION}.{int(exp_epoch)}.{subject}"
    mac = hmac.new(token.encode("ascii"), payload.encode("utf-8"), "sha256").hexdigest()
    return f"{payload}.{mac}"


_APP_TICKET_FALLBACK_KEY = secrets.token_bytes(32)
APP_TICKET_NO_SUBJECT = "-"
APP_TICKET_INVALID_ERROR = "실행 티켓이 만료됐습니다. 모니터에서 '실행' 을 다시 누르십시오."


def _app_ticket_canon(subject):
    """`gh:` 주체는 **로그인을 소문자로** 내린 꼴이 표준. 그 밖은 그대로. None/빈값은 `-`."""
    if not isinstance(subject, str) or not subject:
        return APP_TICKET_NO_SUBJECT
    if subject.startswith(SESSION_SUBJECT_GITHUB_PREFIX):
        return SESSION_SUBJECT_GITHUB_PREFIX + subject[len(SESSION_SUBJECT_GITHUB_PREFIX):].lower()
    return subject


def app_ticket_tag(subject, key):
    """URL 에 실을 되돌릴 수 없는 태그. `hmac(key, "app.sub.v1." + 표준꼴).hexdigest()[:12]`."""
    if not isinstance(key, bytes):
        raise TypeError("key 는 bytes 입니다")
    payload = "app.sub.v1." + _app_ticket_canon(subject)
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:12]


def app_ticket(name, exp, key, subject):
    """`<만료 epoch>.<태그 12자리>.<hmac 32자>`. `key` 는 bytes."""
    exp = int(exp)
    subject = _app_ticket_canon(subject)
    if not _SUBJECT_RE.match(subject):
        raise ValueError(f"subject 꼴이 아닙니다: {subject!r}")
    payload = f"app.v1.{exp}.{subject}.{name}"
    mac = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{app_ticket_tag(subject, key)}.{mac}"


def _app_ticket_parts(ticket):
    """`(exp, tag, mac)` 또는 None. 가운데 칸은 12자리 16진 태그입니다."""
    if not isinstance(ticket, str) or not ticket or len(ticket) > 160:
        return None
    parts = ticket.split(".", 2)
    if len(parts) != 3:
        return None
    exp_s, tag, mac = parts
    if not re.fullmatch(r"\d{1,12}", exp_s):
        return None
    if not re.fullmatch(r"[0-9a-f]{12}", tag):
        return None
    if not re.fullmatch(r"[0-9a-f]{32}", mac):
        return None
    return int(exp_s), tag, mac


def app_ticket_ok(ticket, name, key, subject, now=None):
    """티켓이 그 프로젝트에 대해 아직 유효한가. 참/거짓만 돌려주고 예외를 던지지 않습니다."""
    if not isinstance(ticket, str) or not isinstance(name, str) or not isinstance(key, bytes):
        return False
    if not _PROJECT_RE.match(name):
        return False
    parts = _app_ticket_parts(ticket)
    if not parts:
        return False
    exp, tag, mac = parts
    want_tag = app_ticket_tag(subject, key)
    if not hmac.compare_digest(want_tag.encode("ascii"), tag.encode("ascii")):
        return False
    if exp < int(time.time() if now is None else now):
        return False
    # 발급은 TTL 안쪽에서만 합니다. 서명이 맞아도 그보다 먼 `exp` 는
    # 이 서버가 발급한 것일 수 없습니다 (키가 샜을 때 영구 티켓을 막는 심층 방어).
    if exp > int(time.time() if now is None else now) + PROJECT_APP_TICKET_TTL_SEC + 60:
        return False
    subject = _app_ticket_canon(subject)
    payload = f"app.v1.{exp}.{subject}.{name}"
    want = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(want.encode("ascii"), mac.encode("ascii"))


def app_ticket_resolve(ticket, key, candidates):
    """티켓의 태그와 맞는 주체를 후보 가운데서 찾는다. 없으면 None.

    허용 목록에 계정을 다시 넣으면 TTL(12시간) 안의 옛 티켓이 다시 듭니다.
    이것은 **의도한 동작**입니다 - 다시 넣는 행위 자체가 명시적 재허가이고, TTL 이 12시간으로 짧으며,
    즉시 끊으려면 접근 토큰을 갈면 모든 티켓이 한 번에 죽습니다(`_app_ticket_key`).
    """
    if not isinstance(ticket, str) or not isinstance(key, bytes):
        return None
    parts = _app_ticket_parts(ticket)
    if not parts:
        return None
    tag = parts[1]
    for candidate in candidates or ():
        if not isinstance(candidate, str):
            continue
        if hmac.compare_digest(app_ticket_tag(candidate, key).encode("ascii"), tag.encode("ascii")):
            return candidate
    return None


def _app_ticket_key(request):
    """티켓 서명 키. 접근 토큰을 갈아 끼우면 티켓도 전부 무효가 됩니다 - 그것이 회수 수단입니다."""
    if request.access_token:
        return request.access_token.encode("ascii")
    return _APP_TICKET_FALLBACK_KEY


def verify_session(token, cookie_value, now=None):
    """`{'subject','exp'}` 또는 None. 변조·만료·꼴 불일치는 전부 None 입니다."""
    if not token or not cookie_value or not isinstance(cookie_value, str):
        return None
    parts = cookie_value.split(".")
    if len(parts) != 4 or parts[0] != SESSION_VERSION:
        return None
    _, exp_s, subject, mac = parts
    if not re.fullmatch(r"\d{1,12}", exp_s) or not _SUBJECT_RE.match(subject):
        return None
    payload = f"{SESSION_VERSION}.{exp_s}.{subject}"
    want = hmac.new(token.encode("ascii"), payload.encode("utf-8"), "sha256").hexdigest()
    # **바이트로 비교합니다.** 문자열 비교는 비ASCII 가 섞이면 `TypeError` 를 냅니다 -
    # 예외가 인증 경로에서 터지면 연결이 끊기고 실패 집계에서도 빠집니다 (S4 검수 4번).
    if not hmac.compare_digest(want.encode("ascii"), mac.encode("utf-8", "replace")):
        return None
    exp = int(exp_s)
    if exp <= (time.time() if now is None else now):
        return None
    return {"subject": subject, "exp": exp}


def build_ssl_context(root=ROOT):
    """자체 인증서로 TLS 컨텍스트를 만듭니다. 없으면 **만드는 법을 적고 멈춥니다.**"""
    crt, key = pathlib.Path(root) / CERT_FILE, pathlib.Path(root) / KEY_FILE
    if not crt.is_file() or not key.is_file():
        sys.exit(
            f"인증서가 없습니다: {crt} / {key}\n"
            "  다음으로 만드십시오 (WSL IP 와 윈도우 호스트 IP 를 SAN 에 넣습니다):\n"
            "  mkdir -p .aimem/tls && openssl req -x509 -newkey ec "
            "-pkeyopt ec_paramgen_curve:prime256v1 -days 825 -nodes \\\n"
            "      -keyout .aimem/tls/server.key -out .aimem/tls/server.crt \\\n"
            "      -subj /CN=aimem-fleet -addext "
            "'subjectAltName=DNS:aimem-fleet,DNS:localhost,IP:127.0.0.1,IP:<WSL IP>'\n"
            "  chmod 600 .aimem/tls/server.key")
    mode = key.stat().st_mode & 0o777
    if mode & 0o077:
        sys.exit(f"개인키 권한이 {oct(mode)} 입니다. `chmod 600 {key}` 로 좁히고 다시 띄우십시오.")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(crt), keyfile=str(key))
    return ctx


_PROXY_LINE_MAX = 107      # PROXY protocol v1 한 줄의 최대 길이 (CRLF 포함)


def read_proxy_header(request, client_address):
    """윈도우 쪽 통과 프록시(18800)가 맨 앞에 붙이는 `PROXY TCP4 <접속자> <목적지> <포트> <포트>\r\n` 한 줄을
    읽어 **진짜 접속자 주소**를 돌려줍니다 (2026-11-11). 없으면 받은 주소 그대로.

    프록시를 거치면 모든 접속이 `127.0.0.1` 로 보여 접속 기록으로는 누가 왔는지 알 수 없었고, 주소별 제한도
    모두 한 바구니였습니다(R11 인증 우회 때 악용 여부를 프록시 로그로만 가릴 수 있었습니다).
    **이 줄은 상대가 이 기계 자신(loopback)일 때만 믿습니다** - 바깥에서 직접 온 연결이 이 줄을 보내면 주소를
    속이는 것이므로 읽지 않습니다(그 연결은 TLS 핸드셰이크에서 떨어집니다). `X-Forwarded-For` 는 여전히 안 믿습니다.
    """
    try:
        if not ipaddress.ip_address(client_address[0]).is_loopback:
            return client_address
        head = request.recv(_PROXY_LINE_MAX, socket.MSG_PEEK)
        if not head.startswith(b"PROXY "):
            return client_address
        end = head.find(b"\r\n")
        if end < 0:
            return client_address
        line = request.recv(end + 2)[:end].decode("ascii", "replace").split(" ")     # 그 줄만 정확히 꺼낸다
        if len(line) == 6 and line[1] in ("TCP4", "TCP6"):
            src = ipaddress.ip_address(line[2])
            port = int(line[4])
            if 0 < port < 65536:
                return (str(src), port) + tuple(client_address[2:])
    except (OSError, ValueError, IndexError, TypeError):
        pass
    return client_address


class TLSThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """TLS 핸드셰이크를 **워커 스레드에서** 합니다 (S4 검수 1번, 높음).

    `ctx.wrap_socket(httpd.socket)` 로 리스닝 소켓을 통째로 감싸면 핸드셰이크가
    **accept 루프 안에서** 일어납니다. TLS 를 시작하지 않는 TCP 연결 하나가
    `accept()` 를 붙잡아 **서버 전체가 멈춥니다**(실측: 유휴 연결 1개로 8초 타임아웃,
    연결을 닫을 때까지 무한). `Handler.timeout` 은 그 단계에 닿지 않습니다.

    그래서 리스닝 소켓은 평문으로 두고, 연결마다 **워커 스레드에서 타임아웃을 걸고**
    감쌉니다. 핸드셰이크가 늦거나 깨지면 그 연결만 끊깁니다.
    """

    ssl_context = None
    handshake_timeout = 10

    def _redirect_plain_http(self, request):
        """첫 바이트가 TLS 핸드셰이크(0x16)가 아니면 평문 HTTP 로 보고 https 로 301 을 줍니다. 처리했으면 True.

        HTTPS 로 바꾼 뒤 예전 `http://...:18799` 즐겨찾기로 들어오면 브라우저에 알 수 없는 오류만
        보였습니다. 요청줄의 Host 만 읽어 같은 주소의 https 로 보냅니다 - 본문·쿠키는 읽지 않고,
        이 평문 응답에는 아무 데이터도 싣지 않습니다.
        """
        try:
            first = request.recv(1, socket.MSG_PEEK)
        except OSError:
            return False
        if not first or first == b"\x16":
            return False
        try:
            head = request.recv(4096).decode("latin-1", "replace")
        except OSError:
            return True
        m = re.search(r"(?im)^host:\s*([A-Za-z0-9.\-\[\]:]{1,255})\s*$", head)
        line0 = head.split("\r\n", 1)[0].split(" ")
        path = line0[1] if len(line0) >= 3 and line0[1].startswith("/") else "/"
        path = re.sub(r"[^A-Za-z0-9/._~%?&=#:+,-]", "", path)[:512] or "/"
        if m:
            body = b""
            resp = (f"HTTP/1.1 301 Moved Permanently\r\nLocation: https://{m.group(1)}{path}\r\n"
                    "Content-Length: 0\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n")
        else:
            body = "이 포트는 HTTPS 전용입니다.\n".encode("utf-8")
            resp = (f"HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain; charset=utf-8\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n")
        try:
            request.sendall(resp.encode("latin-1") + body)
        except OSError:
            pass
        return True

    def finish_request(self, request, client_address):
        try:
            request.settimeout(self.handshake_timeout)
            client_address = read_proxy_header(request, client_address)
            if self._redirect_plain_http(request):
                return
            tls = self.ssl_context.wrap_socket(request, server_side=True)
        except (OSError, ssl.SSLError, ValueError) as e:
            # 인증서를 믿지 않는 클라이언트, 평문 요청, 끊긴 연결 - 전부 여기로 옵니다.
            sys.stderr.write(f"TLS 핸드셰이크 실패 {client_address[0]}: {type(e).__name__}\n")
            return
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            try:
                tls.close()
            except OSError:
                pass


def github_enabled():
    return bool(os.environ.get(GITHUB_CLIENT_ID_ENV) and os.environ.get(GITHUB_CLIENT_SECRET_ENV))


def github_device_enabled():
    """기기 흐름: client id 만 있고 시크릿이 없을 때. (둘 다 있으면 웹 흐름 `github_enabled()`.)"""
    return bool(os.environ.get(GITHUB_CLIENT_ID_ENV)) and not os.environ.get(GITHUB_CLIENT_SECRET_ENV)


class DevicePending:
    """열려 있는 확인 코드. `aid`(쿠키로만 오가는 난수) -> device_code. 메모리에만 있고 서버가 내려가면 사라진다.

    로그인 전 누구나 부를 수 있는 길이라 크기를 묶는다: IP 하나에 하나(새로 시작하면 앞의 것은 버림), 전체 상한.
    """

    def __init__(self, limit=GITHUB_DEVICE_MAX_PENDING):
        self.limit = limit
        self._items = {}
        self._lock = threading.Lock()

    def add(self, ip, device_code, interval, expires_in, now=None):
        """aid 를 돌려준다. 자리가 없으면 None."""
        now = time.time() if now is None else now
        with self._lock:
            for k in [k for k, v in self._items.items() if v["exp"] <= now or v["ip"] == ip]:
                del self._items[k]
            if len(self._items) >= self.limit:
                return None
            aid = secrets.token_urlsafe(24)
            self._items[aid] = {"ip": ip, "device_code": device_code, "interval": max(1, int(interval)),
                                "next": now + max(1, int(interval)), "exp": now + int(expires_in)}
            return aid

    def due(self, aid, now=None):
        """(항목 사본 | None, 지금 GitHub 에 물어도 되나). 물어도 되면 다음 시각을 미룬다."""
        now = time.time() if now is None else now
        with self._lock:
            it = self._items.get(aid or "")
            if it is None:
                return None, False
            if it["exp"] <= now:
                del self._items[aid]
                return None, False
            if now < it["next"]:
                return dict(it), False
            it["next"] = now + it["interval"]
            return dict(it), True

    def slow_down(self, aid, now=None):
        now = time.time() if now is None else now
        with self._lock:
            it = self._items.get(aid)
            if it:
                it["interval"] += 5
                it["next"] = now + it["interval"]

    def drop(self, aid):
        with self._lock:
            self._items.pop(aid, None)


def github_post_form(url, fields):
    """GitHub 에 폼을 보내고 JSON 을 받는다. 리다이렉트는 따르지 않는다. (시험에서 갈아 끼우는 자리)"""
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode("ascii"),
                                 headers={"Accept": "application/json", "User-Agent": "aimem-monitor"})
    with _no_redirect_opener().open(req, timeout=8.0) as r:
        out = json.loads(r.read(64 * 1024).decode("utf-8"))
    if not isinstance(out, dict):
        raise ValueError("GitHub 응답이 객체가 아님")
    return out


def github_user_login(access_token):
    """access token -> `GET /user` 의 login. 토큰은 여기서만 쓰고 어디에도 적지 않는다."""
    req = urllib.request.Request(GITHUB_USER_URL, headers={
        "Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json",
        "User-Agent": "aimem-monitor"})
    with _no_redirect_opener().open(req, timeout=8.0) as r:
        return json.loads(r.read(64 * 1024).decode("utf-8")).get("login")


def github_allowed_logins(root=ROOT):
    """허용 GitHub 로그인 집합(소문자). 파일이 없으면 **빈 집합** - 아무도 못 들어옵니다."""
    out = set()
    try:
        text = (pathlib.Path(root) / GITHUB_ALLOW_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            out.add(line)
    return out


class LoginGuard:
    """IP 당 실패 횟수. 창(`LOGIN_FAIL_WINDOW_SEC`) 안에서 상한을 넘으면 지연으로 갚습니다.

    차단이 아니라 지연인 이유: 차단은 같은 NAT 뒤의 정당한 사용자까지 막고,
    자체 인증서 + 토큰 공개면에서 우리가 막고 싶은 것은 **초당 수천 번의 대입**뿐입니다.
    """

    def __init__(self, window=LOGIN_FAIL_WINDOW_SEC, limit=LOGIN_FAIL_MAX, delay=LOGIN_FAIL_DELAY_SEC):
        self.window, self.limit, self.delay = window, limit, delay
        self._fails = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def _prune(self, ip, now):
        dq = self._fails[ip]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        return dq

    def check(self, ip, now=None):
        """지연해야 할 초. 0.0 이면 즉시 허용."""
        now = time.time() if now is None else now
        with self._lock:
            n = len(self._prune(ip, now))
        return 0.0 if n < self.limit else self.delay * (n - self.limit + 1)

    def fail(self, ip, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._prune(ip, now).append(now)
            # 한 IP 가 메모리를 채우지 못하게 창 길이와 무관하게 상한을 둡니다.
            if len(self._fails) > 4096:
                self._fails.clear()

    def reset(self, ip):
        with self._lock:
            self._fails.pop(ip, None)


# -- 설정 파일 / 감사 로그 (접근 제어 보강, 2026-11-10) -------------------------

MONITOR_ENV_FILE = ".aimem/tls/monitor.env"      # 0600. KISTI_API_KEY / GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET(없으면 기기 흐름)
OPENCLAW_ENV_FILE = pathlib.Path.home() / ".openclaw" / ".env"
AUDIT_LOG = ".aimem/access.log"                   # git 제외. 로그인·쓰기 동작만 (폴링은 적지 않음)
#: CSP 출처에 넣어도 되는 **추가** 호스트 이름 (쉼표로 나눔). 바깥 주소가 이름(도메인)이면
#: `.aimem/monitor.env` 에 `AIMEM_MONITOR_PUBLIC_HOSTS=aimem.example.org` 처럼 적습니다.
MONITOR_PUBLIC_HOSTS_ENV = "AIMEM_MONITOR_PUBLIC_HOSTS"


def _app_host_allowed(name):
    """그 호스트 이름을 `/app/` CSP 의 허용 출처로 써도 되는가 (R11 검수 B 결함 1).

    IP 리터럴·`localhost`·환경변수에 적은 이름만 참입니다. 아무 이름이나 받으면
    `Host: evil.com` 요청 하나로 서버가 evil.com 을 `script-src` 에 넣은 CSP 를 발급합니다.
    """
    n = (name or "").strip().lower().rstrip(".")
    if not n:
        return False
    if n == "localhost" or n.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(n)
        return True
    except ValueError:
        pass
    extra = (os.environ.get(MONITOR_PUBLIC_HOSTS_ENV) or "").split(",")
    return n in {h.strip().lower().rstrip(".") for h in extra if h.strip()}


_ENV_KEYS = (KISTI_API_KEY_ENV, GITHUB_CLIENT_ID_ENV, GITHUB_CLIENT_SECRET_ENV, MONITOR_PUBLIC_HOSTS_ENV)
_audit_lock = threading.Lock()

_REVOKED_AUDIT_MIN_SEC = 60
_REVOKED_AUDIT_MAX = 256
_DENIED_AUDIT_MAX_PER_MIN = 60
_DENIED_AUDIT_FIRST_MAX = 256
_revoked_last = collections.OrderedDict()
_revoked_lock = threading.Lock()
_denied_window_start = 0.0
_denied_window_written = 0
_denied_cap_skipped = 0
_denied_evicted_skipped = 0
_denied_window_seen = set()


def _parse_env(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


def load_monitor_env(root=ROOT, openclaw_env=OPENCLAW_ENV_FILE):
    """비밀값을 **셸 환경이 아니라 파일에서** 읽습니다. 이미 환경에 있으면 덮지 않습니다.

    서버를 다시 띄울 때마다 `KISTI_API_KEY` 가 빠져 KISTI 카드가 오류를 내던 것(2026-11-10 실측)과,
    GitHub 비밀을 셸 히스토리에 남기지 않으려는 것이 이유입니다. 그룹·기타가 읽을 수 있는 파일은
    **읽지 않습니다**(비밀 파일 권한 검사). 돌려주는 값: [(키, 출처)] - 값은 돌려주지 않습니다.
    """
    loaded = []
    sources = [(pathlib.Path(root) / MONITOR_ENV_FILE, _ENV_KEYS)]
    if openclaw_env is not None:
        sources.append((pathlib.Path(openclaw_env), (KISTI_API_KEY_ENV,)))   # 오픈클로 쪽은 KISTI 키만
    for path, keys in sources:
        try:
            st = path.stat()
        except OSError:
            continue
        if st.st_mode & 0o077:
            log_line(f"  경고: {path} 권한이 {oct(st.st_mode & 0o777)} 라 읽지 않습니다 (chmod 600)")
            continue
        try:
            env = _parse_env(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        for k in keys:
            if env.get(k) and not os.environ.get(k):
                os.environ[k] = env[k]
                loaded.append((k, str(path)))
    return loaded


def audit(root, event, ip="-", subject=None, detail=""):
    """감사 로그 한 줄. 토큰·비밀은 절대 넣지 않습니다(호출자가 detail 에 넣지 않음)."""
    fields = [datetime.datetime.now().isoformat(timespec="seconds"), event, ip, subject or "-", str(detail)[:300]]
    line = "\t".join(str(f).translate(_LOG_SAFE) for f in fields)   # 칸 안의 제어문자만 가린다
    try:
        p = pathlib.Path(root) / AUDIT_LOG
        p.parent.mkdir(parents=True, exist_ok=True)
        with _audit_lock:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError:
        pass


def _audit_denied(root, event, ip, subject, path, method="GET", reason="", authenticated=False):
    """거절 한 건을 감사에 남긴다.

    인증된 주체만 `(event, subject, path, method)`, URL 이 주장한 주체는 `(event, subject, method)`,
    주체가 없으면 `(event, "-", method)`. **ip 는 넣지 않는다.**
    상한에 걸린 건은 기록 표시를 하지 않는다.
    """
    global _denied_window_start, _denied_window_written, _denied_cap_skipped
    global _denied_evicted_skipped
    now = time.time()
    safe_path = _TICKET_LOG_RE.sub("/app/~***", str(path))
    safe_method = str(method or "GET")
    safe_reason = str(reason)[:24]
    authenticated = authenticated or event == "github-revoked"
    has_subject = bool(subject) and subject != "-"
    if has_subject and authenticated:
        key = (event, subject, safe_path, safe_method, safe_reason)
    elif has_subject:
        key = (event, subject, safe_method, safe_reason)
    else:
        key = (event, "-", safe_method, safe_reason)
    bucket = (event, subject or "-")
    with _revoked_lock:
        if not _revoked_last:
            _denied_window_start = now
            _denied_window_written = 0
            _denied_cap_skipped = 0
            _denied_window_seen.clear()
        rec = _revoked_last.get(key)
        if rec is not None and now - rec[0] < _REVOKED_AUDIT_MIN_SEC:
            _revoked_last[key] = (rec[0], rec[1] + 1)
            _revoked_last.move_to_end(key)
            return

        dropped = 0
        if now - _denied_window_start >= 60:
            _denied_window_start = now
            _denied_window_written = 0
            dropped = _denied_cap_skipped + _denied_evicted_skipped
            _denied_cap_skipped = 0
            _denied_evicted_skipped = 0
            _denied_window_seen.clear()
        first_seen = bucket not in _denied_window_seen
        guaranteed = first_seen and len(_denied_window_seen) < _DENIED_AUDIT_FIRST_MAX
        if not guaranteed and _denied_window_written >= _DENIED_AUDIT_MAX_PER_MIN:
            _denied_cap_skipped += 1
            return
        _denied_window_written += 1
        if guaranteed:
            _denied_window_seen.add(bucket)
        skipped = rec[1] if rec is not None else 0
        _revoked_last[key] = (now, 0)
        _revoked_last.move_to_end(key)
        while len(_revoked_last) > _REVOKED_AUDIT_MAX:
            _, evicted = _revoked_last.popitem(last=False)
            if evicted[1] > 0:
                _denied_evicted_skipped += evicted[1]
    detail = f"{safe_method} {safe_path}"
    if skipped:
        detail += f" 생략 {skipped}건"
    if reason:
        detail += f" {reason}"
    if dropped:
        audit(root, "audit-dropped", "-", None, f"상한 생략 {dropped}건")
    audit(root, event, ip, subject, detail)


def flush_denied_audit(root):
    """남은 상한 생략 수를 한 줄로 내보내고 비웁니다. 0 이면 아무것도 쓰지 않습니다."""
    global _denied_cap_skipped, _denied_evicted_skipped
    with _revoked_lock:
        skipped = _denied_cap_skipped + _denied_evicted_skipped
        _denied_cap_skipped = 0
        _denied_evicted_skipped = 0
    if skipped > 0:
        audit(root, "audit-dropped", "-", None, f"상한 생략 {skipped}건")


def _audit_revoked(root, ip, subject, path="-", method="GET"):
    """허용 목록 밖 GitHub 주체를 일정 간격으로 한 번만 기록한다."""
    _audit_denied(root, "github-revoked", ip, subject, path, method, "허용 목록 밖", authenticated=True)


def subject_label(subject):
    """화면에 보일 이름. `token` -> '접근 토큰', `gh:login` -> 'GitHub login'."""
    if not subject:
        return None
    if subject == SESSION_SUBJECT_TOKEN:
        return "접근 토큰"
    if subject.startswith(SESSION_SUBJECT_GITHUB_PREFIX):
        return "GitHub " + subject[len(SESSION_SUBJECT_GITHUB_PREFIX):]
    return subject


def _reader():
    """`reader.py` 를 늦게 import 합니다.

    S1 이 아직 만들지 않았거나 깨져 있어도 서버는 떠야 합니다 - 안 그러면
    프런트엔드 검수까지 같이 멈춥니다. 실패는 `/api/state` 의 `errors` 로 보입니다.
    """
    from . import reader  # noqa: PLC0415 - 의도적인 지연 import
    return reader


class RequestRateLimiter:
    """IP 당 요청 생성 속도 제한 (`REQUEST_RATE_MAX` / `REQUEST_RATE_WINDOW_SEC`).

    `LoginGuard` 와 달리 **지연이 아니라 거절(429)** 입니다. 로그인은 정당한
    사용자가 오타를 낼 수 있어 지연으로 갚지만, 요청 생성은 창 안에 다섯 건을
    넘길 이유가 없고 지연으로 갚으면 그 스레드가 그만큼 잡힙니다.

    **성공한 생성만 셉니다** - 400 으로 거절된 것까지 세면 폼을 고쳐 다시 내는
    사람이 자기 할당량을 깎아먹습니다.
    """

    def __init__(self, limit=REQUEST_RATE_MAX, window=REQUEST_RATE_WINDOW_SEC):
        self.limit, self.window = limit, window
        self._hits = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def _prune(self, ip, now):
        dq = self._hits[ip]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        return dq

    def allow(self, ip, now=None):
        """(허용하나, 남은 초). **통과하면 그 자리에서 자리를 잡습니다**(예약).

        검사와 증가가 한 락 안에서 일어나야 합니다 - 나눠 두었더니 동시 10건이
        전부 201 로 통과했습니다(S4 검수 2번 실측, 한도 5건에 `429` 0건).
        요청이 400 으로 거절되면 `refund()` 로 되돌립니다.
        """
        now = time.time() if now is None else now
        with self._lock:
            dq = self._prune(ip, now)
            if len(dq) < self.limit:
                self._add(ip, dq, now)
                return True, 0
            return False, max(1, int(self.window - (now - dq[0])) + 1)

    def _add(self, ip, dq, now):
        """락을 쥔 채로 한 건 센다. `allow()` 와 `record()` 가 공유한다."""
        dq.append(now)
        if len(self._hits) > 4096:   # 한 IP 가 메모리를 채우지 못하게 (LoginGuard 와 같은 이유)
            self._hits.clear()

    def record(self, ip, now=None):
        """한도와 무관하게 한 건 셉니다. 버킷을 미리 채울 때 씁니다.

        **`allow()` 가 이미 세므로 요청 경로에서는 부르지 않습니다** - 두 번 세면
        한도가 절반이 됩니다. 검사와 증가가 떨어져 있던 것이 동시 요청에서
        뚫린 원인이었습니다(S4 검수 2번).
        """
        now = time.time() if now is None else now
        with self._lock:
            self._add(ip, self._prune(ip, now), now)

    def refund(self, ip, now=None):
        """형식 오류로 거절된 요청의 자리를 돌려줍니다.

        **성공만 세는 이유:** 폼을 고쳐 다시 내는 사람이 자기 할당량을 깎아먹으면
        안 됩니다. 다만 거절도 공짜는 아니라 `fail_guard` 가 따로 셉니다.
        """
        with self._lock:
            dq = self._hits.get(ip)
            if dq:
                dq.pop()


def _empty_state(root, errors):
    """실패 분기의 상태. **정상 분기와 최상위 키가 같아야 합니다.**

    프런트는 `state.graphs` 를 무조건 읽습니다. 실패 분기에서 키가
    빠지면 화면이 통째로 깨집니다 - 두 분기가 따로 적혀 있다 실제로 9개가
    어긋나 있었습니다 (S4 적대적 검수 7번, REV 111). 그래서 한 군데서만 만듭니다.
    """
    state = _blank_keys(root)
    state.update({"graphs": collect_graphs(root, errors),
                  "managers": manager_status(root), "errors": errors, "projects": list_projects(root)})
    state["fleet"] = fleet_state(root, state["managers"])
    state["claude_usage"] = _safe_claude_usage(root)
    return scrub_public(state, root)


def _blank_keys(root):
    """`graphs` 를 **빼고** 나머지 최상위 키의 기본값. 비싸서 따로 붙입니다."""
    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "aimem": {}, "slots": [], "board": [], "queue": [],
        "log": [], "runs": [], "eta": {}, "requests": [],
        "claude_usage": None,
    }


CLAUDE_USAGE_MAX_BYTES = 64 * 1024

#: 상태줄 파일의 칸 이름과 화면 라벨. 차례도 이 표가 정합니다.
CLAUDE_USAGE_ROWS = (
    ("five_hour", "5시간"),
    ("seven_day", "주간"),
    ("seven_day_opus", "주간·Opus"),
    ("seven_day_sonnet", "주간·Sonnet"),
)


def _usage_percent(row):
    """`used_percentage` → `utilization` → `percent` 중 첫 숫자. `bool` 은 숫자가 아닙니다."""
    for name in ("used_percentage", "utilization", "percent"):
        value = row.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return min(100.0, max(0.0, float(value)))
    return None


def _usage_resets_at(value):
    """초기 시각·ISO 문자열을 현지 시각 문자열로. 읽을 수 없으면 `None`."""
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.datetime.fromtimestamp(value).isoformat(timespec="seconds")
        if isinstance(value, str):
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed.isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None
    return None


def _safe_claude_usage(root):
    """곁다리 카드 하나가 상태 전체를 죽이지 않게 감싼 `claude_usage()`.

    깊은 중첩 JSON 은 `json.loads` 에서 `RecursionError` 를 던질 수 있고,
    그 예외는 카드 실패일 뿐 `/api/state` 실패가 아니어야 합니다.
    """
    try:
        return claude_usage(root)
    except Exception:  # noqa: BLE001 - 곁다리 카드가 상태 전체를 죽이지 않게
        return None


def claude_usage(root=ROOT):
    """`.aimem/claude-usage.json` 을 읽어 함대 탭 행을 만듭니다.

    파일 하나만 봅니다 - 자격 증명·환경 변수는 읽지 않습니다. 파일이 없거나
    깨졌으면 `None` 이고 **로그도 예외도 없습니다** (`/api/state` 는 5초마다 돕니다).
    """
    path = pathlib.Path(root) / ".aimem" / "claude-usage.json"
    try:
        if path.stat().st_size > CLAUDE_USAGE_MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    limits = data.get("rate_limits")
    if not isinstance(limits, dict) or not limits:
        return None

    rows = []
    for key, label in CLAUDE_USAGE_ROWS:
        row = limits.get(key)
        if not isinstance(row, dict):
            continue
        percent = _usage_percent(row)
        if percent is None:
            continue
        rows.append({
            "key": key,
            "label": label,
            "percent": round(percent, 1),
            "resets_at_iso": _usage_resets_at(row.get("resets_at")),
        })
    if not rows:
        return None

    at = data.get("at")
    if not isinstance(at, str):
        at = None
    age_seconds = None
    if at is not None:
        try:
            parsed_at = datetime.datetime.fromisoformat(at.replace("Z", "+00:00"))
            if parsed_at.tzinfo is not None:
                parsed_at = parsed_at.astimezone().replace(tzinfo=None)
            age_seconds = max(0, int((datetime.datetime.now() - parsed_at).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            age_seconds = None

    return {"at": at, "age_seconds": age_seconds, "rows": rows}


#: 확인토큰 꼴. **이 꼴일 때만 비밀로 취급합니다** - 길이 하한만 두면 토큰이
#: `main` 같은 흔한 낱말일 때 본문을 엉뚱하게 치환합니다
#: (S4 실측: `'domain maintain main.py'` -> `'do*** ***tain ***.py'`).
_TOKEN_SHAPE = re.compile(r"\A[0-9a-fA-F]{6,}\Z")


def _masker(root, state=None, tokens=None):
    """저장소 절대경로와 슬롯 확인토큰을 가리는 함수를 만듭니다.

    **문자열 하나를 받아 문자열을 돌려주는 순수 함수**입니다 - `/api/state` 와
    `/api/runs/<id>` 두 공개면이 같은 것을 써야 해서 클로저 밖으로 뺐습니다
    (S4 검수 1번: 상세 엔드포인트가 scrub 을 안 거쳐 실행 기록 51건이 전부
    절대경로를, 일부는 확인토큰을 그대로 싣고 있었습니다).
    """
    if tokens is None:
        tokens = []
        for s in (state or {}).get("slots") or []:
            if isinstance(s, dict):
                v = s.get("token")
                if isinstance(v, str) and _TOKEN_SHAPE.match(v):
                    tokens.append(v)
    # 끝 슬래시 유무로 결과가 갈리지 않게 벗겨 둡니다 (S4 검수 8번).
    root_str = str(root or "").rstrip("/")
    # 저장소 밖의 홈 경로도 가립니다. 작업자 보고문에 `ls` / `npx` 출력이 섞여
    # `/home/<사용자>/.npm/...` 이 실려 나갔습니다 (REV 114 재검증에서 3건 남음).
    # 저장소 경로를 **먼저** 바꾸므로 `<저장소>` 가 `<홈>/work/...` 로 뭉개지지 않습니다.
    home_str = str(pathlib.Path.home()).rstrip("/")

    def mask(s):
        if not isinstance(s, str):
            return s
        if len(root_str) > 8:   # `/home` 처럼 짧은 접두를 통째로 가리지 않도록
            s = s.replace(root_str, "<저장소>")
        if len(home_str) > 8:
            s = s.replace(home_str, "<홈>")
        for sec in tokens:
            s = s.replace(sec, "***").replace(sec.upper(), "***").replace(sec.lower(), "***")
        return s
    return mask


def mask_deep(obj, mask):
    """모든 문자열 잎에 `mask` 를 먹입니다. 숫자·불리언·None 은 건드리지 않습니다.

    **필드 목록 대신 전체를 훑는 이유** (S4 검수 8번): 필드를 열거하면 새 키가
    생길 때마다 빠집니다 - 실측에서 `slots[].note`/`board[].handoff`/
    `requests[].detail`/`graphs[].nodes[].title` 등 16군데가 목록 밖이었습니다.
    비용은 폴링 5초에 수 ms 라 정확도를 택합니다.
    """
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: mask_deep(v, mask) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_deep(v, mask) for v in obj]
    return obj


def _truncate_request_details(requests):
    """`requests[].detail` 을 `REQUEST_DETAIL_MAX` 자로 자릅니다 (`4.5` 큐 13번).

    **자른 사실을 숨기지 않습니다** - `detail_truncated`(불리언)와 `detail_len`(원본
    글자 수)을 항상 같이 싣습니다. 잘린 값만 내보내면 화면이 전문을 보고 있다고
    착각하고, 요청 본문이 길수록 조용히 잘린 끝이 판단을 바꿉니다.

    자르는 자리를 **공개 직전 한 군데**로 둔 이유는 `scrub_public` 과 같습니다 -
    원본(`.aimem/requests/<id>.json`)은 관리자가 분담할 때 읽어야 하고, reader 가
    미리 자르면 그 값이 내부에서도 사라집니다.
    """
    if not isinstance(requests, list):
        return
    for req in requests:
        if not isinstance(req, dict):
            continue
        detail = req.get("detail")
        if not isinstance(detail, str):
            # 문자열이 아니면 길이도 자르기도 뜻이 없습니다. 키는 채워 둡니다 -
            # 프런트가 `detail_truncated` 를 무조건 읽습니다.
            req["detail_truncated"] = False
            req["detail_len"] = 0
            continue
        req["detail_len"] = len(detail)
        if len(detail) > REQUEST_DETAIL_MAX:
            req["detail"] = detail[:REQUEST_DETAIL_MAX] + "…"
            req["detail_truncated"] = True
        else:
            req["detail_truncated"] = False


def scrub_public(state, root=None):
    """공개면에서 나가면 안 되는 **키와 값**을 떼어냅니다 (`PUBLIC_FORBIDDEN`, S4 검수 5번).

    **`reader.collect()` 가 아니라 여기서 떼는 이유:** `root` 는 reader 가 `.aimem/runs`
    를 훑을 때 실제로 쓰는 값이고 `token` 은 `fleet.py` 대조의 근거입니다. 둘 다
    내부에서는 필요하고 **밖으로 나가면 안 되는** 값이라, 계층의 경계인 공개 직전
    한 군데에서만 떼는 쪽이 어긋날 자리가 적습니다.

    사용자가 쓴 `title`/`detail` 은 설정 유출이 아니므로 가리지 않습니다.
    """
    mask = _masker(root if root is not None else state.get("root"), state)
    for k in PUBLIC_FORBIDDEN["top"]:
        state.pop(k, None)
    _truncate_request_details(state.get("requests"))
    reqs = state.get("requests")
    if isinstance(reqs, list):
        # 행 키 계약(`REQUEST_ROW_KEYS`) - 표에 없는 키는 공개면에 나가지 않는다는 규칙을
        # 최상위뿐 아니라 요청 행에도 적용합니다 (2026-11-10 점검 3번).
        for i, r in enumerate(reqs):
            if isinstance(r, dict):
                reqs[i] = {k: v for k, v in r.items() if k in REQUEST_ROW_KEYS}
    slots = state.get("slots")
    if isinstance(slots, list):
        for s in slots:
            if isinstance(s, dict):
                for k in PUBLIC_FORBIDDEN["slot"]:
                    s.pop(k, None)
    return mask_deep(state, mask)


def collect_state(root=ROOT):
    """`reader.collect()` 를 부르고, 실패하면 **빈 상태 + errors** 로 낮춥니다."""
    try:
        state = _reader().collect(root)
    except Exception as e:  # noqa: BLE001 - 어떤 실패든 화면은 떠야 한다
        return _empty_state(root, [f"reader.collect() 실패: {type(e).__name__}: {e}"])
    if not isinstance(state, dict):
        return _empty_state(root, [f"reader.collect() 가 dict 가 아닙니다: {type(state).__name__}"])
    # `errors` 가 리스트가 아닐 수 있습니다 - `setdefault` 는 값이 `None` 이면 덮지 않습니다.
    if not isinstance(state.get("errors"), list):
        state["errors"] = []
    # **키가 모자란 dict 를 그대로 통과시키던 것**을 막습니다. `{}` 나 `{"runs": []}` 를
    # 돌려받으면 최상위 키 10개가 빠진 채 나갔고, 프런트는 `state.graphs` 를
    # 무조건 읽습니다 (S4 재검수 2번, REV 111). 실패 분기와 **같은 기본값**으로 메웁니다.
    for k, v in _blank_keys(root).items():
        state.setdefault(k, v)
    state["graphs"] = collect_graphs(root, state["errors"])
    state["projects"] = list_projects(root, state.get("requests") if isinstance(state.get("requests"), list) else None)
    state["managers"] = manager_status(root)
    state["fleet"] = fleet_state(root, state["managers"])
    state["claude_usage"] = _safe_claude_usage(root)
    return scrub_public(state, root)


def _detail_masker(root):
    """상세 응답용 가림 함수. 토큰은 **DB 명부에서** 읽습니다.

    `/api/state` 는 자기 응답 안의 `slots[].token` 에서 토큰을 얻지만 상세 응답에는
    명부가 없습니다. 작업자 브리프 머리말이 확인토큰을 싣고 보고문이 그것을 그대로
    인용하므로(S4 검수 1번 실측: 51건 중 토큰 유출 다수), 여기서는 정본을 직접 봅니다.
    """
    tokens = []
    try:
        tools_dir = str(pathlib.Path(root) / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import aimem_db  # noqa: PLC0415 - 지연 import. 없어도 경로 가림은 돌아야 한다
        with aimem_db.connect() as con:
            tokens = [r[0] for r in con.execute("SELECT token FROM slots") if r[0]]
    except Exception:  # noqa: BLE001 - 토큰 목록을 못 얻어도 경로는 가린다
        tokens = []
    return _masker(root, tokens=tokens)


def run_detail(run_id, root=ROOT):
    """`reader.run_detail()` 로 넘기고, 없거나 깨져도 **키 16개**는 채워 돌려줍니다.

    `reader` 는 S1 소유라 서버가 먼저 떠 있을 수 있습니다(`_reader` 와 같은 이유).

    **돌려주기 전에 가립니다** - `brief`/`report`/`stderr_tail`/`paths`/`errors` 에
    저장소 절대경로와 확인토큰이 그대로 실립니다 (S4 검수 1번, 높음). 404 분기도
    같은 객체를 `{"detail": d}` 로 한 번 더 내보내므로 **여기 한 군데에서** 막습니다.
    """
    mask = _detail_masker(root)
    blank = {k: "" for k in RUN_DETAIL_KEYS}
    blank.update({"id": str(run_id)[:120], "found": False, "rc": None, "elapsed_s": None,
                  "started": None, "ended": None, "paths": {}, "errors": []})
    if not re.match(RUN_ID_RE, str(run_id)):
        blank["errors"] = ["잘못된 run id 입니다"]
        return mask_deep(blank, mask)
    try:
        d = _reader().run_detail(run_id, root)
    except AttributeError:
        blank["errors"] = ["reader.run_detail() 이 아직 없습니다"]
        return mask_deep(blank, mask)
    except Exception as e:  # noqa: BLE001
        blank["errors"] = [f"run_detail() 실패: {type(e).__name__}: {e}"]
        return mask_deep(blank, mask)
    if not isinstance(d, dict):
        blank["errors"] = [f"run_detail() 이 dict 가 아닙니다: {type(d).__name__}"]
        return mask_deep(blank, mask)
    out = dict(blank)
    out.update({k: v for k, v in d.items() if k in RUN_DETAIL_KEYS})
    return mask_deep(out, mask)


# -- 외부 HTTP (깃허브 OAuth) -----------------------------------------------

def _no_redirect_opener():
    """리다이렉트를 따르지 않는 opener.

    `urlopen` 은 302 를 따라가면서 `Authorization: Bearer <키>` 를 **다른 호스트로
    그대로 들고 갑니다.** S4 가 재현했습니다(가짜 키로 시험, 적대적 검수 2번).
    외부 서버·프록시·DNS 가 오염되면 키가 제3자에게 나가고, https -> http 강등도
    막지 못합니다. 그래서 따라가지 않습니다.
    """
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    return urllib.request.build_opener(_NoRedirect)


# -- 관리자 세션 (`fleet.py children` 의 관리자 행) -----------------------------
#
# 관리자는 S1~S4 와 별개인 Opus ACP 세션이라 `runs` 에 나오지 않습니다. 관리자가
# 계획·검증 중이면 작업자가 0개라 화면이 멈춘 것처럼 보였습니다 (요청 Q-261110-549a).
# `openclaw sessions` 는 한 번에 4초 걸리므로 **배경 갱신 + 캐시** 입니다.

MANAGER_CACHE_SEC = 30
MANAGER_TIMEOUT_SEC = 25
MANAGER_MAX = 6
ACPX_SESSIONS = pathlib.Path.home() / ".openclaw" / "acpx" / "sessions"
_mgr_lock = threading.Lock()
_mgr_cache = {"at": None, "value": None, "refreshing": False}


def _ms_iso(ms):
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _fetch_managers():
    """`openclaw sessions --agent claude` 에서 ACP 관리자 세션만 골라 요약합니다. 키 원문은 내보내지 않습니다."""
    import subprocess
    res = subprocess.run(["openclaw", "sessions", "--agent", "claude", "--json"],
                         capture_output=True, text=True, timeout=MANAGER_TIMEOUT_SEC)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or "").strip()[:160] or f"rc {res.returncode}")
    payload = json.loads(res.stdout)
    sessions = payload.get("sessions", []) if isinstance(payload, dict) else payload
    out = []
    for s in sessions:
        if not isinstance(s, dict) or ":acp:" not in str(s.get("key", "")):
            continue
        sid = str(s.get("key", "")).rsplit(":", 1)[-1]
        status = str(s.get("status") or "unknown")[:20]
        rec = _manager_record(sid[:8])
        info = {"record_kb": None, "last_activity": None, "steps": None, "last_step": None}
        if rec is not None:
            try:
                st = rec.stat()
                info["record_kb"] = st.st_size // 1024
                info["last_activity"] = datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
            except OSError:
                pass
            if status == "running":            # 끝난 세션의 1MB 기록을 30초마다 다시 읽지 않는다
                steps = _manager_steps(rec)
                if steps is not None:
                    info["steps"] = len(steps)
                    info["last_step"] = _step_line(steps[-1]) if steps else None
        out.append({
            "label": str(s.get("label") or "(라벨 없음)")[:80],
            "status": status,
            "started": _ms_iso(s.get("sessionStartedAt")),
            "updated": _ms_iso(s.get("updatedAt")),
            "id": sid[:8],
            **info,
        })
    out.sort(key=lambda m: m.get("started") or "", reverse=True)
    return out[:MANAGER_MAX]


_MGR_ID_RE = re.compile(r"\A[0-9a-f]{8}\Z")
_REQ_MGR_RE = re.compile(r"\A/api/managers/([0-9a-f]{8})\Z")
MANAGER_STEPS_MAX = 40


def _manager_record(id8):
    """관리자 세션 기록 파일(`~/.openclaw/acpx/sessions/*<uuid>*.json`). id8 은 uuid 앞 8자(16진)."""
    if not _MGR_ID_RE.match(id8 or ""):
        return None
    try:
        hits = [f for f in ACPX_SESSIONS.glob(f"*%3A{id8}*.json") if f.is_file() and not f.is_symlink()]
    except OSError:
        return None
    return max(hits, key=lambda f: f.stat().st_mtime) if hits else None


def _manager_steps(path):
    """기록의 마지막 에이전트 턴에서 단계 목록 [{kind, text}] - **도구 결과(출력)는 싣지 않습니다.**"""
    try:
        if path.stat().st_size > 64 * 1024 * 1024:
            return None
        d = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    steps = []
    for m in (d.get("messages") or []):
        agent = m.get("Agent") if isinstance(m, dict) else None
        if not isinstance(agent, dict):
            continue
        for item in agent.get("content") or []:
            if not isinstance(item, dict):
                continue
            if "Text" in item and isinstance(item["Text"], str) and item["Text"].strip():
                steps.append({"kind": "text", "text": item["Text"].strip()})
            elif isinstance(item.get("ToolUse"), dict):
                tu = item["ToolUse"]
                inp = tu.get("input") if isinstance(tu.get("input"), dict) else {}
                cmd = inp.get("command") or inp.get("file_path") or inp.get("path") or tu.get("name") or ""
                steps.append({"kind": "tool", "text": str(cmd), "desc": str(inp.get("description") or "")})
    return steps


def _step_line(step):
    s = step.get("desc") or step.get("text") or ""
    s = " ".join(str(s).split())
    return ("▸ " if step.get("kind") == "tool" else "") + s[:160]


def manager_detail(id8, root=ROOT, all_steps=False):
    """관리자 세션 하나의 상세: 요약 + 최근 단계 + 라운드 전달 기록 + 라운드 중 이벤트·그래프. (코드, 본문)"""
    if not _MGR_ID_RE.match(id8 or ""):
        return 400, {"ok": False, "error": "잘못된 관리자 id 입니다"}
    with _mgr_lock:
        cached = dict(_mgr_cache["value"] or {})
    sess = next((s for s in cached.get("sessions") or [] if s.get("id") == id8), None)
    rec = _manager_record(id8)
    if sess is None and rec is None:
        return 404, {"ok": False, "error": f"그런 관리자 세션이 없습니다: {id8}"}
    out = {"ok": True, "id": id8, "session": sess, "steps": [], "steps_total": 0, "relay": None,
           "events": [], "graphs": []}
    if rec is not None:
        steps = _manager_steps(rec) or []
        out["steps_total"] = len(steps)
        # 단계 본문은 자르지 않는다(상세는 전문, 2026-11-10). 기본은 최근 MANAGER_STEPS_MAX 개, `?all=1` 이면 전부.
        shown = steps if all_steps else steps[-MANAGER_STEPS_MAX:]
        out["steps"] = [{"kind": s["kind"], "text": s["text"], "desc": s.get("desc", "")} for s in shown]
        try:
            st = rec.stat()
            out["record_kb"] = st.st_size // 1024
            out["last_activity"] = datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        except OSError:
            pass
        if sess is None:
            # 세션 목록 캐시에 없으면(서버 막 시작·지운 세션) 기록 파일의 시작 시각으로 대신합니다
            try:
                d = json.loads(rec.read_text(encoding="utf-8", errors="replace"))
                raw = str(d.get("agent_started_at") or d.get("created_at") or "")
                started_utc = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
                sess = {"label": d.get("title") or d.get("name"), "status": "closed" if d.get("closed") else "?",
                        "started": started_utc.astimezone().replace(tzinfo=None).isoformat(timespec="seconds"),
                        "id": id8}
                out["session"] = sess
            except (OSError, ValueError, TypeError):
                pass
    label = (sess or {}).get("label") or ""
    m = re.search(r"\bR(\d+)\b", label)
    relay_f = pathlib.Path(root) / ".aimem" / "relay" / f"r{m.group(1)}.json" if m else None
    if relay_f is not None and relay_f.is_file():
        try:
            out["relay"] = json.loads(relay_f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    started = (sess or {}).get("started")
    if started:
        try:
            tools_dir = str(pathlib.Path(root) / "tools")
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            import aimem_db  # noqa: PLC0415
            until = "9999"
            if (sess or {}).get("status") != "running" and out.get("last_activity"):
                until = out["last_activity"]          # 끝난 세션은 그 세션이 끝난 시각까지만
            with aimem_db.connect() as con:
                rows = con.execute("SELECT at, actor, rev, kind, body FROM events WHERE at >= ? AND at <= ? "
                                   "ORDER BY seq DESC" + ("" if all_steps else " LIMIT 30"), (started, until)).fetchall()
            out["events"] = [{"at": r["at"], "actor": r["actor"], "rev": r["rev"], "kind": r["kind"],
                              "body": r["body"] or ""} for r in rows]
        except Exception:  # noqa: BLE001
            pass
        try:
            for g in collect_graphs(root, []):
                if started[:19] <= str(g.get("created") or "") <= (out.get("last_activity") if (sess or {}).get("status") != "running" and out.get("last_activity") else "9999"):
                    out["graphs"].append({"id": g.get("id"), "request": g.get("request"), "percent": g.get("percent"),
                                          "counts": g.get("counts")})
        except Exception:  # noqa: BLE001
            pass
    return 200, mask_deep(out, _detail_masker(root))


def _refresh_managers():
    try:
        value = {"ok": True, "sessions": _fetch_managers(), "error": None}
    except Exception as e:  # noqa: BLE001 - 배경 스레드
        value = {"ok": False, "sessions": [], "error": f"{type(e).__name__}: {str(e)[:120]}"}
    with _mgr_lock:
        old = _mgr_cache["value"]
        if not value["ok"] and old and old.get("sessions"):
            value["sessions"] = old["sessions"]   # 실패해도 지난 목록은 남긴다 (stale 로 표시)
        _mgr_cache.update({"at": datetime.datetime.now(), "value": value, "refreshing": False})


def manager_status(root=ROOT):
    """캐시를 즉시 돌려주고, 낡았으면 배경 갱신 하나를 띄웁니다. 실제 저장소가 아니면(테스트) 부르지 않습니다."""
    if pathlib.Path(root).resolve() != ROOT:
        return {"ok": True, "sessions": [], "pending": False, "age_sec": None, "error": None}
    now = datetime.datetime.now()
    with _mgr_lock:
        at, val = _mgr_cache["at"], _mgr_cache["value"]
        fresh = val is not None and at is not None and (now - at).total_seconds() < MANAGER_CACHE_SEC
        start = not fresh and not _mgr_cache["refreshing"]
        if start:
            _mgr_cache["refreshing"] = True
    if start:
        threading.Thread(target=_refresh_managers, daemon=True, name="manager-refresh").start()
    if val is None:
        return {"ok": True, "sessions": [], "pending": True, "age_sec": None, "error": None}
    age = int((now - at).total_seconds()) if at else None
    if age is not None and age > MANAGER_CACHE_SEC * 4:
        # 아무도 화면을 안 보는 동안은 갱신이 돌지 않는다 - 몇 시간 묵은 목록을 "지금" 처럼 내주면 끝난 관리자가
        # '실행 중' 으로 보인다(R8 이 끝난 뒤 R9 도중에 그렇게 보였다). 너무 낡았으면 비우고 '조회 중' 으로 답한다.
        return {"ok": True, "sessions": [], "pending": True, "age_sec": age, "error": None}
    out = dict(val)
    # `at` 은 함대 제어 직후 강제 갱신을 위해 None 으로 비워질 수 있습니다 (값은 남김) - 그때는 갱신 중
    out.update({"pending": at is None, "age_sec": age})
    return out


# -- 함대 제어 (`tools/fleet_ctl.py`) -----------------------------------------
#
# 준비 / 실행 / 일시 중지 / 완전 중지 / 라운드 실행 (태석님 지시 2026-11-10). 상태 판정과 동작은
# 전부 `fleet_ctl` 이 합니다 - 서버는 부르기만 합니다 (CLI 와 화면이 같은 규칙을 쓰게).

FLEET_ACTIONS = ("prepare", "run", "pause", "stop", "round")
_REQ_FLEET_RE = re.compile(r"\A/api/fleet/(prepare|run|pause|stop|round|chain)\Z")

# -- 슬롯 관리 (2026-11-10, 태석님 지시 "슬롯 하네스 추가·삭제, 모델 지정") ----------------------------
# 정본은 `.aimem/aimem.db` slots - `tools/aimem_db.py slot *` 과 같은 함수를 부른다. 모델은 **OpenClaw 가 설정한
# 모델 목록**(`openclaw models list --json`)에서 고른다. 쓰기는 인증 뒤에서만, 감사 로그에 남긴다.
_REQ_SLOT_RE = re.compile(r"\A/api/slots/(S\d{1,3})/(set|remove)\Z")


def archive_action(payload, by, root=ROOT):
    """`POST /api/archive` {days, dry_run} → `aimem_db.archive_plan/apply`. 끝난 태스크·요청·그래프를 아카이브로 (8.0).
    dry_run 은 계획만 돌려준다(쓰기 없음). 운영 저장소에서만."""
    if pathlib.Path(root).resolve() != ROOT:
        return 403, {"ok": False, "error": "운영 저장소가 아닙니다"}
    if not isinstance(payload, dict):
        return 400, {"ok": False, "error": "JSON 객체가 아닙니다"}
    days = payload.get("days", 14)
    if not isinstance(days, int) or isinstance(days, bool) or days < 0 or days > 3650:
        return 400, {"ok": False, "error": "days 는 0~3650 정수"}
    dry = bool(payload.get("dry_run", False))
    db = _aimem_db(root)
    try:
        plan = db.archive_plan(days)
    except Exception as e:  # noqa: BLE001 - 계획을 못 세워도 화면에는 이유가 보여야 한다 (전에는 연결이 그냥 끊겼다)
        return 500, {"ok": False, "error": f"정리 계획을 세우지 못했습니다: {type(e).__name__}: {str(e)[:160]}"}
    summary = {"days": days, "cutoff": plan["cutoff"], "total": plan["total"],
               "tasks": [{"id": t["id"], "title": t["title"], "slot": t["slot"], "updated": t["updated"]} for t in plan["tasks"]],
               "requests": [{"id": r["id"], "title": r["title"], "status": r["status"], "when": r["when"]} for r in plan["requests"]],
               "graphs": [{"id": g["id"], "request": g["request"], "when": g["when"], "counts": g["counts"],
                           "files": 1 + len(g["side_files"]) + len(g["inputs"])} for g in plan["graphs"]]}
    summary["records"] = {
        "runs":      len(plan.get("runs") or []),
        "events":    len(plan.get("events") or []),
        "handoff":   len(plan.get("handoff") or []),
        "relay":     len(plan.get("relay") or []),
        "log_lines": sum(int(l.get("lines") or 0) for l in (plan.get("logs") or [])),
    }
    summary["total_records"] = plan.get("total_records") or 0
    if dry:
        return 200, {"ok": True, "dry_run": True, "plan": summary}
    try:
        out = db.archive_apply(plan, by)
    except RuntimeError as e:
        return 500, {"ok": False, "error": str(e)}
    moved_counts = {k: (len(v) if isinstance(v, (list, tuple)) else v)
                    for k, v in out.items() if k != "files"}
    return 200, {"ok": True, "dry_run": False, "plan": summary, "moved": out,
                 "moved_counts": moved_counts}
SLOT_HARNESSES = ("claude", "codex", "opencode")
MODELS_CACHE_SEC = 60
_models_cache = {"at": None, "value": None}
_models_lock = threading.Lock()


def _aimem_db(root):
    tools_dir = str(pathlib.Path(root) / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import aimem_db  # noqa: PLC0415
    return aimem_db


def _models_for_harness(key):
    """openclaw 모델 키를 어느 하네스가 받을 수 있나. claude CLI 는 Anthropic 모델만, codex/opencode 는 그 밖(kistillm·EXAONE·…)."""
    prov = key.split("/", 1)[0].lower()
    if prov in ("anthropic", "claude-cli"):
        return ["claude"]
    return ["codex", "opencode"]


OPENCLAW_CONFIG = pathlib.Path.home() / ".openclaw" / "openclaw.json"


def _models_from_openclaw_config(path=None):
    """`~/.openclaw/openclaw.json` 의 `models.providers.<p>.models[]` → {key: {name}}. 비밀(baseUrl·apiKey)은 읽지 않는다.
    `openclaw models list` 는 인증이 안 붙은 공급자(EXAONE 등)를 '설정됨' 으로 안 보여 주는데, 그게 기본 모델이다(2026-11-10 실측)."""
    out = {}
    try:
        cfg = json.loads((path or OPENCLAW_CONFIG).read_text(encoding="utf-8"))
        for prov, v in ((cfg.get("models") or {}).get("providers") or {}).items():
            for m in (v or {}).get("models") or []:
                mid = m.get("id") if isinstance(m, dict) else m
                if mid:
                    out[f"{prov}/{mid}"] = {"name": (m.get("name") if isinstance(m, dict) else None) or str(mid)}
        prim = (((cfg.get("agents") or {}).get("defaults") or {}).get("model") or {}).get("primary")
        if isinstance(prim, str) and prim:
            out.setdefault(prim, {"name": prim})["default"] = True
    except (OSError, ValueError, AttributeError):
        pass
    return out


def openclaw_models(now=None, cache_sec=MODELS_CACHE_SEC):
    """OpenClaw 가 설정한 모델 = `openclaw models list --json` ∪ `openclaw.json` providers. 60초 캐시.
    둘 다 실패하면 빈 목록 + error 로 낮춘다(화면은 떠야 한다)."""
    now = now or datetime.datetime.now()
    with _models_lock:
        at, val = _models_cache["at"], _models_cache["value"]
        if val is not None and at is not None and (now - at).total_seconds() < cache_sec:
            return val
    exe = shutil.which("openclaw")
    out = {"ok": False, "models": [], "error": None, "source": "openclaw models list --json + ~/.openclaw/openclaw.json providers",
           "fetched": now.isoformat(timespec="seconds")}
    by_key = {}
    if not exe:
        out["error"] = "openclaw 가 PATH 에 없습니다"
    else:
        try:
            r = subprocess.run([exe, "models", "list", "--json"], capture_output=True, text=True, timeout=20)
            data = json.loads(r.stdout or "{}")
            items = data.get("models") if isinstance(data, dict) else data
            for m in items or []:
                if not isinstance(m, dict) or not m.get("key"):
                    continue
                key = str(m["key"])
                tags = [str(t) for t in (m.get("tags") or []) if isinstance(t, str)]
                by_key[key] = {"key": key, "name": str(m.get("name") or key), "provider": key.split("/", 1)[0],
                               "aliases": [t[6:] for t in tags if t.startswith("alias:")],
                               "context": m.get("contextWindow"), "harnesses": _models_for_harness(key), "from": ["list"]}
            out["ok"] = True
        except (OSError, subprocess.TimeoutExpired, ValueError) as e:
            out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    cfg = _models_from_openclaw_config()
    for key, info in cfg.items():
        if key in by_key:
            by_key[key]["from"].append("config")
        else:
            by_key[key] = {"key": key, "name": info["name"], "provider": key.split("/", 1)[0], "aliases": [], "context": None,
                           "harnesses": _models_for_harness(key), "from": ["config"]}
        if info.get("default"):
            by_key[key]["default"] = True
    if cfg:
        out["ok"] = True
    out["models"] = sorted(by_key.values(), key=lambda m: (0 if m["provider"] in ("anthropic", "claude-cli") else 1, m["key"]))
    with _models_lock:
        _models_cache["at"], _models_cache["value"] = now, out
    return out


def _slot_running(slot, root):
    """그 슬롯으로 지금 도는 작업자가 있나 (`reader` 의 runs 기준)."""
    try:
        for r in _reader().collect(root).get("runs") or []:
            if r.get("slot") == slot and r.get("state") == "running":
                return r.get("id")
    except Exception:  # noqa: BLE001 - 판단 못 하면 '없음' 으로 둔다
        return None
    return None


def _slot_payload_fields(payload):
    def pick(k, limit):
        v = payload.get(k)
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(f"{k} 은(는) 문자열이어야 합니다")
        v = v.strip()
        if len(v) > limit:
            raise ValueError(f"{k} 이(가) {limit}자를 넘습니다")
        return v
    return pick("slot", 6), pick("harness", 16), pick("model", 120), pick("role", 200), pick("note", 1000)


def _model_allowed(model, harness):
    """빈 값(하네스 기본)·claude 별칭은 통과. 그 밖은 openclaw 설정 목록에 있어야 하고 그 하네스가 받을 수 있어야 한다."""
    if not model:
        return True, ""
    if harness == "claude" and model in ("opus", "sonnet", "haiku"):
        return True, ""
    ms = openclaw_models()
    hit = next((m for m in ms["models"] if m["key"] == model), None)
    if hit is None:
        if not ms["ok"]:
            return False, f"모델 목록을 읽지 못해 확인할 수 없습니다: {ms['error']}"
        return False, f"openclaw 에 설정된 모델이 아닙니다: {model}"
    if harness not in hit["harnesses"]:
        return False, f"{model} 은(는) {harness} 하네스가 받을 수 없습니다 (가능: {', '.join(hit['harnesses'])})"
    return True, ""


SLOT_NOTICE_REQUESTER = "슬롯 관리(웹)"


def _notify_manager_slot_change(action, row, by, changes, root):
    """웹에서 바꾼 슬롯을 **라운드 관리자가 모르면 안 된다**(태석님 2026-11-10) - 요청 트리에 NEW 요청으로 남겨
    관리자가 분담하는 그 경로로 받게 한다. 실패해도 슬롯 변경 자체는 되돌리지 않는다(요청은 통지 수단)."""
    slot = row.get("slot") if isinstance(row, dict) else row
    if action == "add":
        title = f"슬롯 {slot} 추가됨({row.get('harness')}, 모델 {row.get('model') or '하네스 기본'}) - 역할·비고 배정 필요"
        detail = (f"{by} 이(가) 웹 함대 현황에서 슬롯을 추가했습니다.\n\n- 슬롯: {slot}\n- 하네스: {row.get('harness')}\n- 모델: {row.get('model') or '(하네스 기본)'}\n"
                  f"- 역할: {row.get('role')}\n\n관리자 할 일: 라운드 시작 때 이 라운드 의도에 맞춰 `python3 tools/aimem_db.py slot set --slot {slot} --role \"…\" --note \"…\"` 로 역할·비고를 정하고, "
                  f"배정 방침을 보고에 한 줄 적은 뒤 이 요청을 DONE 으로 닫으십시오. 하네스·모델은 태석님 결정이니 바꾸지 않습니다.")
    elif action == "set":
        title = f"슬롯 {slot} 변경됨({', '.join(changes) if changes else '변경 없음'}) - 확인 필요"
        detail = (f"{by} 이(가) 웹에서 슬롯 {slot} 의 하네스/모델을 바꿨습니다: {', '.join(changes) if changes else '(바뀐 것 없음)'}.\n\n"
                  f"관리자 할 일: 이 슬롯에 배정된 태스크·역할이 새 하네스/모델과 맞는지 보고, 필요하면 `slot set --role/--note` 로 역할·비고를 고친 뒤 이 요청을 DONE 으로 닫으십시오.")
    else:
        title = f"슬롯 {slot} 삭제됨 - 배정·소유권 정리 확인"
        detail = (f"{by} 이(가) 웹에서 슬롯 {slot} 을(를) 명부에서 지웠습니다. 소유권 {row.get('ownership_removed', 0)}행이 같이 내려갔습니다"
                  + (f", 미완 태스크 {', '.join(row.get('open_tasks') or [])} 는 강제로 남겨졌습니다" if row.get("open_tasks") else "") +
                  ".\n\n관리자 할 일: 이 슬롯을 전제로 한 큐·그래프·브리프가 있으면 다른 슬롯으로 돌리고, 이 요청을 DONE 으로 닫으십시오.")
    try:
        ok, res = create_request({"title": title, "detail": detail, "requester": SLOT_NOTICE_REQUESTER}, root)
        return res.get("id") if ok else None
    except Exception:  # noqa: BLE001 - 통지 실패가 슬롯 변경을 막지 않는다
        return None


def slot_action(action, slot, payload, by, root=ROOT):
    """(HTTP 코드, 응답). action: add | set | remove. 운영 저장소에서만 쓴다. 성공하면 관리자용 NEW 요청을 남긴다."""
    if pathlib.Path(root).resolve() != ROOT:
        return 403, {"ok": False, "error": "운영 저장소가 아닙니다"}
    if not isinstance(payload, dict):
        return 400, {"ok": False, "error": "JSON 객체가 아닙니다"}
    db = _aimem_db(root)
    try:
        p_slot, harness, model, role, note = _slot_payload_fields(payload)
        # 역할·비고는 **라운드 관리자의 몫**이다(8.0-1 "슬롯은 좁게, 전체 그림은 관리자만", 태석님 2026-11-10).
        # 웹(사람)은 하네스·모델 - 어떤 엔진을 몇 개 둘지 - 만 바꾼다. 역할·비고를 보내면 거절한다.
        if role is not None or note is not None:
            return 400, {"ok": False, "error": "역할·비고는 라운드 관리자가 정합니다 - 웹에서는 하네스·모델만 바꿉니다 (관리자 CLI: aimem_db.py slot set --role/--note)"}
        if action == "add":
            if not harness or harness not in SLOT_HARNESSES:
                return 400, {"ok": False, "error": f"하네스는 {'/'.join(SLOT_HARNESSES)} 중 하나"}
            ok, why = _model_allowed(model, harness)
            if not ok:
                return 400, {"ok": False, "error": why}
            stamp = datetime.datetime.now().strftime("%m-%d %H:%M")
            row = db.slot_add(p_slot or None, harness, model or None, db.SLOT_ROLE_UNASSIGNED,
                              f"{stamp} 웹에서 추가({by}). 역할·비고는 관리자가 라운드 시작 때 정한다", by)
            notice = _notify_manager_slot_change("add", row, by, [], root)
            return 201, {"ok": True, "slot": {k: v for k, v in row.items() if k != "token"}, "notice": notice}
        if action == "set":
            cur = next((r for r in db.slot_list() if r["slot"] == slot), None)
            if cur is None:
                return 404, {"ok": False, "error": f"{slot} 이 명부에 없습니다"}
            if harness and harness not in SLOT_HARNESSES:
                return 400, {"ok": False, "error": f"하네스는 {'/'.join(SLOT_HARNESSES)} 중 하나"}
            new_harness = harness or cur["harness"]
            running = _slot_running(slot, root)
            if running and harness and harness != cur["harness"]:
                return 409, {"ok": False, "error": f"{slot} 에 작업자가 돌고 있습니다 ({running}) - 하네스는 끝난 뒤 바꾸십시오"}
            clear = payload.get("model") == ""   # 빈 문자열 = 하네스 기본으로
            if not clear:
                ok, why = _model_allowed(model, new_harness)
                if not ok:
                    return 400, {"ok": False, "error": why}
            row, changes = db.slot_set(slot, harness, None if clear else model, None, None, by, clear_model=clear)
            notice = _notify_manager_slot_change("set", row, by, changes, root) if changes else None
            return 200, {"ok": True, "slot": {k: v for k, v in row.items() if k != "token"}, "changes": changes, "notice": notice}
        if action == "remove":
            running = _slot_running(slot, root)
            if running:
                return 409, {"ok": False, "error": f"{slot} 에 작업자가 돌고 있습니다 ({running}) - 끝난 뒤 삭제하십시오"}
            res = db.slot_remove(slot, by, force=bool(payload.get("force")))
            notice = _notify_manager_slot_change("remove", res, by, [], root)
            return 200, {"ok": True, **res, "notice": notice}
    except ValueError as e:
        msg = str(e)
        code = 409 if "끝나지 않은 태스크" in msg else (404 if "명부에 없습니다" in msg else 400)
        return code, {"ok": False, "error": msg}
    return 404, {"ok": False, "error": f"없는 동작입니다: {action}"}



def _fleet_ctl(root):
    tools_dir = str(pathlib.Path(root) / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import fleet_ctl  # noqa: PLC0415
    return fleet_ctl


def fleet_state(root=ROOT, managers=None):
    if pathlib.Path(root).resolve() != ROOT:
        return {"mode": "running", "label": "실행", "default": True, "can": {a: False for a in FLEET_ACTIONS}}
    try:
        sessions = (managers or {}).get("sessions") or []
        # 관리자 목록을 아직 못 읽었으면(`pending`·오류) "있다" 로 본다 - 모르는 채로 '라운드 끝' 이라 하면
        # 서버를 다시 띄운 직후 도는 라운드 위에 '라운드 실행' 이 켜진다 (REV 153)
        unknown = bool((managers or {}).get("pending")) or (managers or {}).get("ok") is False
        return _fleet_ctl(root).public_state([s.get("label") for s in sessions],
                                             unknown or any(s.get("status") == "running" for s in sessions))
    except Exception as e:  # noqa: BLE001 - 제어 상태를 못 읽어도 화면은 떠야 한다
        return {"mode": None, "error": f"{type(e).__name__}: {str(e)[:120]}", "can": {a: False for a in FLEET_ACTIONS}}


def fleet_action(action, by, root=ROOT, payload=None):
    """(HTTP 코드, 응답). 판정은 fleet_ctl 이 하고, 막힌 동작은 409 로 돌려줍니다."""
    if action == "chain":
        # 이어 달리기 켜기/끄기 (REV 155). 켜는 것은 사람이고, 라운드를 띄우는 것은 여전히 '라운드 실행' 입니다.
        if pathlib.Path(root).resolve() != ROOT:
            return 409, {"ok": False, "error": "운영 저장소가 아닙니다"}
        p = payload if isinstance(payload, dict) else {}
        if not isinstance(p.get("on"), bool):
            return 400, {"ok": False, "error": "`on` 은 true/false 여야 합니다"}
        try:
            names = p.get("projects")
            names = [x for x in names if isinstance(x, str)][:50] if isinstance(names, list) else []
            if isinstance(p.get("project"), str) and p["project"].strip():
                names.append(p["project"])
            # 대상: 함대(fleet) · 프로젝트 여러 개(projects) · 전체(all). 아무것도 안 골랐으면 거절하고 이유를 돌려준다
            out = _fleet_ctl(root).chain_set(p["on"], None, p.get("max_rounds"), by, projects=names,
                                             fleet_on=bool(p.get("fleet")), all_=bool(p.get("all")),
                                             autonomous=bool(p.get("autonomous")), renew=bool(p.get("renew")))
        except Exception as e:  # noqa: BLE001
            return 500, {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        return (200 if out.get("ok") else 400), out
    if action not in FLEET_ACTIONS:
        return 404, {"ok": False, "error": f"없는 동작입니다: {action}"}
    ctl = _fleet_ctl(root)
    extra = []
    if action == "prepare":
        try:   # 역할 미배정 슬롯 - 관리자가 라운드 시작 때 정해야 할 것이 있음을 준비 점검표에 보인다
            db = _aimem_db(root)
            pend = [s["slot"] for s in db.slot_list() if (s.get("role") or "") == db.SLOT_ROLE_UNASSIGNED]
            extra.append(ctl._check("슬롯 역할 미배정 (관리자가 라운드 시작 때 정함)", not pend,
                                    ("없음" if not pend else ", ".join(pend) + " - 관리자 브리프 (0) 대상"), required=False))
        except Exception:  # noqa: BLE001
            pass
    try:
        out = {"prepare": lambda: ctl.prepare(by, extra), "run": lambda: ctl.resume(by),
               "pause": lambda: ctl.pause(by), "stop": lambda: ctl.stop(by),
               "round": lambda: ctl.launch_round(by)}[action]()
    except Exception as e:  # noqa: BLE001
        return 500, {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    with _mgr_lock:
        _mgr_cache["at"] = None   # 관리자 목록을 다음 폴링에 새로 읽게
    if action == "prepare":
        return 200, out            # 점검 실패도 결과(checks)를 보여 줘야 하므로 200
    return (200 if out.get("ok") else 409), out


# -- 태스크 그래프 (`tools/fleet_graph.py`) ----------------------------------

def collect_graphs(root=ROOT, errors=None):
    """`.aimem/graph/*.json` 을 읽어 요청 트리 옆에 놓을 요약을 만듭니다.

    진행율·ETA 계산은 `fleet_graph.progress()` 가 정본입니다 - 여기서 다시 계산하면
    CLI 와 화면이 다른 숫자를 말하게 됩니다. 다만 `progress()` 는 **실제 저장소의**
    `.aimem/runs` 를 표본으로 쓰므로, root 가 저장소가 아닐 때는(테스트) 부르지 않고
    상태 집계만 돌려줍니다.
    """
    errors = errors if errors is not None else []
    gdir = pathlib.Path(root) / GRAPH_DIR
    if not gdir.is_dir():
        return []
    live = pathlib.Path(root).resolve() == ROOT.resolve()
    prog = None
    if live:
        try:
            # 프런트가 5초마다 부른다 - 매번 insert 하면 sys.path 가 무한히 늘어난다.
            tools_dir = str(ROOT / "tools")
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            import fleet_graph  # noqa: PLC0415 - 지연 import. 없어도 화면은 떠야 한다
            # 하네스별 소요 표본은 한 번만 구해 모든 그래프에 쓴다 (2026-11-12: 그래프마다 다시 구해 /api/state 가 7~11초)
            durations = fleet_graph.harness_durations()
            prog = lambda g, _d=durations: fleet_graph.progress(g, _d)  # noqa: E731
        except Exception as e:  # noqa: BLE001
            errors.append(f"fleet_graph 를 쓰지 못해 그래프 ETA 를 생략합니다: {type(e).__name__}: {e}")
    out = []
    for p in sorted(gdir.glob("*.json")):
        # 노드 하나가 이상해도 `/api/state` 와 `/api/health` 가 통째로 죽지 않게,
        # 파일 단위로 전부 감쌉니다. 예전에는 `n.get(...)` 이 try 밖에 있어
        # `nodes: ["x"]` 한 줄이 두 엔드포인트를 무응답으로 끊었습니다
        # (S4 적대적 검수 1번, REV 111). 읽지 못한 파일은 `errors` 로 낮춥니다.
        try:
            g = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(g, dict) or not isinstance(g.get("nodes"), list):
                raise ValueError("그래프 객체가 아님")
            counts = {}
            nodes = []
            for n in g["nodes"]:
                if not isinstance(n, dict):
                    raise ValueError(f"노드가 객체가 아님: {type(n).__name__}")
                s = n.get("status", "todo")
                counts[s] = counts.get(s, 0) + 1
                attempts = n.get("attempts") or []
                attempts = attempts if isinstance(attempts, list) else []
                last = attempts[-1] if attempts else None
                nodes.append({
                    "id": n.get("id"), "title": n.get("title"), "slot": n.get("slot"),
                    "harness": n.get("harness"), "status": s,
                    "deps": n.get("deps") if isinstance(n.get("deps"), list) else [],
                    "attempts": len(attempts), "max_attempts": n.get("max_attempts"),
                    "last_run": last.get("run_id") if isinstance(last, dict) else None,
                })
        # `Exception` 으로 넓힙니다. 튜플로 열거하면 **열거하지 않은 하나가 새어 나가**
        # 다시 두 엔드포인트를 죽입니다 - `"["` 20만 개짜리 파일의 `RecursionError` 가
        # 그랬습니다(S4 재검수 1번, REV 111). "이 파일을 못 읽었다" 는 한 줄로 충분합니다.
        except Exception as e:  # noqa: BLE001
            errors.append(f"그래프 파일 {p.name} 을(를) 읽지 못했습니다: {type(e).__name__}: {str(e)[:60]}")
            continue
        item = {"id": g.get("id") or p.stem, "request": g.get("request"),
                "created": g.get("created"), "updated": g.get("updated"),
                "percent": None, "eta_seconds": None, "eta_at": None,
                "counts": counts, "source": "counts-only", "nodes": nodes}
        if prog is not None:
            try:
                pr = prog(g)
                item.update({"percent": pr.get("percent"), "eta_seconds": pr.get("eta_seconds"),
                             "eta_at": pr.get("eta_at"), "basis": pr.get("basis"),
                             "source": "fleet_graph.progress"})
            except Exception as e:  # noqa: BLE001
                errors.append(f"그래프 {item['id']} 진행율 계산 실패: {type(e).__name__}: {e}")
        out.append(item)
    return out


#: 보이지만 않을 뿐 `strip()` 이 지우지 않는 문자들. 이것만으로 이루어진 값은 **빈 값**입니다.
#: U+200B 제로폭 공백 / U+200C·D 제로폭 접합 / U+2060 단어결합 / U+FEFF BOM /
#: U+3164 한글 채움 문자 / U+2800 점자 공백. S4 재검수 6번에서 이 전부가 통과했습니다.
_INVISIBLE = "​‌‍⁠﻿ㅤ⠀ ᠎"


def _meaningful(s):
    """보이지 않는 문자를 걷어낸 뒤에도 내용이 남으면 **원본을** 돌려줍니다(빈 값이면 `""`)."""
    if not isinstance(s, str):
        return ""
    stripped = s.strip()
    return stripped if stripped.strip(_INVISIBLE).strip() else ""


def _slug(title):
    """제목에서 run id 와 같은 꼴의 짧은 꼬리표를 만듭니다. 한글은 버립니다."""
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:24]


_PROJECT_RE = re.compile(PROJECT_NAME_RE)


def _project_of(payload):
    """(이름, 오류). 빈 값·없음은 `""`(함대 자체의 일). 이름은 폴더 하나의 이름이어야 합니다."""
    raw = payload.get("project")
    if raw is None:
        return "", None
    if not isinstance(raw, str):
        return None, "프로젝트(project)는 문자열이어야 합니다"
    name = raw.strip()
    if name and not _PROJECT_RE.match(name):
        return None, "프로젝트 이름은 한글·영문·숫자·`-`·`_` 만, 40자 이하입니다 (공백·점·`/` 불가)"
    return name, None


_PROGRESS_ROUND = re.compile(r"^##\s*R(\d+)\b(.*)$", re.MULTILINE)
# 목표 절 (REV 148): `## 목표`(또는 `## Goals`) 아래의 체크리스트. 관리자가 프로젝트 첫 라운드에 예측해 적고 라운드마다 고칩니다
_PROGRESS_GOALS = re.compile(r"^##[ \t]*(?:목표|goals)\b[^\n]*$", re.MULTILINE | re.IGNORECASE)
_PROGRESS_HEADING = re.compile(r"^##?[ \t]+\S", re.MULTILINE)
_PROGRESS_GOAL_ITEM = re.compile(r"^[ \t]{0,8}[-*][ \t]+\[([ xX])\][ \t]+\S")
PROJECT_GOALS_MAX = 200


def _progress_goals(text):
    """`PROGRESS.md` 의 `## 목표` 절 -> {"total", "done"}. 절이 없거나 항목이 없으면 None (그때는 요청 기준 진행률)."""
    m = _PROGRESS_GOALS.search(text)
    if not m:
        return None
    nxt = _PROGRESS_HEADING.search(text, m.end())
    total = done = 0
    for line in text[m.end():(nxt.start() if nxt else len(text))].splitlines()[:2000]:
        g = _PROGRESS_GOAL_ITEM.match(line)
        if g:
            total += 1
            done += g.group(1) != " "
            if total >= PROJECT_GOALS_MAX:
                break
    return {"total": total, "done": done} if total else None
PROJECT_SUMMARY_MAX = 600


def _archived_request_projects(root):
    """아카이브로 내려간 요청의 (프로젝트, 상태) - 끝난 요청이 14일 뒤 화면에서 사라져도 프로젝트 진행률에는 남게."""
    out = []
    try:
        dirs = sorted((pathlib.Path(root) / ".aimem" / "archive").glob("requests-*"))
    except OSError:
        return out
    for d in dirs:
        try:
            files = list(d.glob("*.json"))[:2000]
        except OSError:
            continue
        for f in files:
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and isinstance(rec.get("project"), str) and _PROJECT_RE.match(rec["project"]):
                out.append((rec["project"], str(rec.get("status") or "").upper()))
    return out


def _project_progress_file(root, name):
    """`projects/<이름>/PROGRESS.md` 에서 거친 라운드, 가장 최근 항목(= 남은 일이 적힌 곳), 목표 달성 수를 읽습니다."""
    f = pathlib.Path(root) / PROJECTS_DIR / name / "PROGRESS.md"
    try:
        if f.is_symlink() or not f.is_file():
            return [], "", None, None
        text = f.read_text(encoding="utf-8", errors="replace")[:200_000]
        updated = datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return [], "", None, None
    marks = list(_PROGRESS_ROUND.finditer(text))
    rounds = sorted({int(m.group(1)) for m in marks})
    summary = ""
    if marks:
        top = max(marks, key=lambda m: int(m.group(1)))      # 가장 높은 라운드의 항목
        nxt = [m.start() for m in marks if m.start() > top.start()]
        summary = text[top.start():(min(nxt) if nxt else len(text))].strip()
    else:
        summary = text.strip()
    return rounds, summary[:PROJECT_SUMMARY_MAX], updated, _progress_goals(text)


def _round_records(root):
    """`rounds/R<N>/round.json` 들 -> {프로젝트: {라운드: 띄운 시각}}. `fleet_ctl` 이 라운드를 띄울 때 씁니다."""
    out = {}
    try:
        files = sorted((pathlib.Path(root) / "rounds").glob("R*/round.json"))[:1000]
    except OSError:
        return out
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            n = int(rec["round"])
            projs = rec.get("projects") or []
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if rec.get("state") == "failed":      # 관리자가 뜨지 않은 라운드 (`fleet_ctl._mark_round_record_failed`)
            continue
        for pr in projs if isinstance(projs, list) else []:
            if isinstance(pr, str) and _PROJECT_RE.match(pr):
                out.setdefault(pr, {})[n] = rec.get("at") if isinstance(rec.get("at"), str) else None
    return out


def list_projects(root=ROOT, requests=None):
    """프로젝트별 진행 상황 (2026-11-10 태석님: "각 프로젝트가 얼마나 진행되고 있나").

    프로젝트 = `projects/` 아래 폴더 + 요청이 가리키는 이름. 진행률(`percent`)은 **목표 대비**입니다 - 관리자가
    `PROGRESS.md` 의 `## 목표` 체크리스트에 적은 것 중 끝난 비율(`basis: "goals"`, REV 148). 목표가 아직 안 적힌
    프로젝트는 예전처럼 그 프로젝트 **요청들의 평균**(`basis: "requests"`)입니다 - 끝난 요청 100, 진행 중인 요청은
    그 요청의 진행율(`progress_pct`), 거절된 요청은 셈에서 뺍니다. 요청 평균은 `request_percent` 로 늘 따로 싣습니다.
    거친 라운드와 '남은 일' 은 관리자가 쓰는 `PROGRESS.md` 에서 읽습니다.
    """
    root = pathlib.Path(root)
    names = set()
    try:
        for d in (root / PROJECTS_DIR).iterdir():
            if d.is_dir() and not d.is_symlink() and _PROJECT_RE.match(d.name):
                names.add(d.name)
    except OSError:
        pass
    have = set(names)
    if requests is None:                       # 상태를 안 받았으면 요청 파일에서 직접 (진행율 없이 상태만)
        requests = []
        try:
            for f in (root / ".aimem" / "requests").glob("*.json"):
                try:
                    rec = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(rec, dict):
                    requests.append(rec)
        except OSError:
            pass
    per = {}
    for q in requests:
        pr = q.get("project") if isinstance(q, dict) else None
        if not (isinstance(pr, str) and _PROJECT_RE.match(pr)):
            continue
        st = str(q.get("status") or "").upper()
        pct = q.get("progress_pct")
        pct = float(pct) if isinstance(pct, (int, float)) and not isinstance(pct, bool) else 0.0
        per.setdefault(pr, []).append((st, 100.0 if st == "DONE" else max(0.0, min(100.0, pct))))
    for pr, st in _archived_request_projects(root):
        per.setdefault(pr, []).append((st, 100.0 if st == "DONE" else 0.0))
    launched = _round_records(root)
    names |= set(per) | set(launched)
    out = []
    for n in sorted(names):
        rows = [r for r in per.get(n, []) if r[0] != "REJECTED"]
        counts = {"total": len(rows), "done": sum(1 for s, _ in rows if s == "DONE"),
                  "new": sum(1 for s, _ in rows if s == "NEW"),
                  "active": sum(1 for s, _ in rows if s not in ("DONE", "NEW"))}
        noted, summary, updated, goals = _project_progress_file(root, n)
        req_pct = round(sum(p for _, p in rows) / len(rows), 1) if rows else None
        mine = launched.get(n, {})
        rounds = sorted(set(noted) | set(mine))          # 띄운 기록(round.json) + 관리자가 적은 기록(PROGRESS.md)
        last = rounds[-1] if rounds else None
        out.append({"name": n, "path": f"{PROJECTS_DIR}/{n}/", "exists": n in have,
                    "percent": round(100.0 * goals["done"] / goals["total"], 1) if goals else req_pct,
                    "basis": "goals" if goals else "requests", "goals": goals, "request_percent": req_pct,
                    "requests": counts, "rounds": rounds, "round_count": len(rounds),
                    "first_round": rounds[0] if rounds else None, "last_round": last,
                    "last_round_at": mine.get(last) if last is not None else None,
                    "updated": updated, "summary": summary,
                    "app": project_app(n, root) if n in have else None})
    return out


PROJECT_FILES_MAX = 500            # 목록 상한 (넘으면 truncated)
PROJECT_FILE_MAX_BYTES = 200_000   # 한 파일 본문 상한 (넘으면 앞부분만, truncated)
_PROJECT_SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "dist", "build"}
_PROJECT_FIRST = {"README.md": 0, "PROGRESS.md": 1}


def _project_dir(name, root):
    """(폴더, 오류응답). 이름은 폴더 하나의 이름이어야 하고, 폴더는 심볼릭 링크가 아니어야 합니다."""
    if not isinstance(name, str) or not _PROJECT_RE.match(name):
        return None, (400, {"ok": False, "error": "프로젝트 이름이 올바르지 않습니다"})
    d = pathlib.Path(root) / PROJECTS_DIR / name
    if d.is_symlink() or not d.is_dir():
        return None, (404, {"ok": False, "error": f"프로젝트 폴더가 아직 없습니다: {PROJECTS_DIR}/{name}/"})
    return d, None


def project_files(name, root=ROOT):
    """`GET /api/projects/<이름>/files` - `projects/<이름>/` 의 결과물 목록 (REV 146: 웹에서 결과물을 본다).

    심볼릭 링크·숨김 항목·의존성 폴더는 건너뜁니다. README.md, PROGRESS.md 가 맨 앞, 나머지는 경로순.
    """
    d, err = _project_dir(name, root)
    if err:
        return err
    files, truncated = [], False
    for cur, dirs, names in os.walk(d, followlinks=False):
        dirs[:] = sorted(x for x in dirs if not x.startswith(".") and x not in _PROJECT_SKIP_DIRS
                         and not (pathlib.Path(cur) / x).is_symlink())
        for fn in sorted(names):
            f = pathlib.Path(cur) / fn
            if fn.startswith(".") or f.is_symlink() or not f.is_file():
                continue
            if len(files) >= PROJECT_FILES_MAX:
                truncated = True
                break
            try:
                st = f.stat()
            except OSError:
                continue
            files.append({"path": f.relative_to(d).as_posix(), "size": st.st_size,
                          "modified": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
        if truncated:
            break
    files.sort(key=lambda x: (_PROJECT_FIRST.get(x["path"], 2), x["path"]))
    return 200, {"ok": True, "name": name, "path": f"{PROJECTS_DIR}/{name}/", "files": files, "truncated": truncated}


def project_file(name, rel, root=ROOT):
    """`GET /api/projects/<이름>/file?path=<상대 경로>` - 결과물 파일 하나의 본문 (텍스트만, 상한까지).

    경로는 프로젝트 폴더 **안**이어야 합니다: 절대 경로·`..`·숨김 조각·심볼릭 링크를 거절하고, 풀어낸 실제 경로가
    폴더 밖이면 거절합니다. 본문은 상세 응답과 같은 가림(저장소 절대 경로·확인 토큰)을 거쳐 나갑니다.
    """
    d, err = _project_dir(name, root)
    if err:
        return err
    if not isinstance(rel, str) or not rel or len(rel) > 400 or "\x00" in rel or "\\" in rel:
        return 400, {"ok": False, "error": "파일 경로(path)가 올바르지 않습니다"}
    parts = rel.split("/")
    if rel.startswith("/") or any(x in ("", ".", "..") or x.startswith(".") for x in parts):
        return 400, {"ok": False, "error": "파일 경로는 프로젝트 폴더 안의 상대 경로여야 합니다"}
    f = d.joinpath(*parts)
    try:
        inside = f.resolve() == d.resolve().joinpath(*parts)     # 중간에 링크가 끼면 달라진다
    except OSError:
        inside = False
    if not inside or f.is_symlink() or not f.is_file():
        return 404, {"ok": False, "error": f"그런 파일이 없습니다: {rel[:120]}"}
    try:
        st = f.stat()
        with open(f, "rb") as fh:
            raw = fh.read(PROJECT_FILE_MAX_BYTES + 1)
    except OSError as e:
        return 500, {"ok": False, "error": f"파일을 읽지 못했습니다: {type(e).__name__}"}
    truncated = len(raw) > PROJECT_FILE_MAX_BYTES
    raw = raw[:PROJECT_FILE_MAX_BYTES]
    binary = b"\x00" in raw
    text = "" if binary else raw.decode("utf-8", errors="replace")
    out = {"ok": True, "name": name, "path": rel, "size": st.st_size,
           "modified": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
           "binary": binary, "truncated": truncated, "text": text}
    return 200, mask_deep(out, _detail_masker(root))


def _app_parts(value, label="경로"):
    """(조각들, 오류). 앱 안의 상대 경로를 프로젝트 폴더 밖으로 나가지 않게 검사합니다."""
    if not isinstance(value, str) or not value or len(value) > 400 or "\x00" in value or "\\" in value:
        return None, f"{label}가 올바르지 않습니다"
    if value.startswith("/"):
        return None, f"{label}는 상대 경로여야 합니다"
    parts = value.split("/")
    if len(parts) > 8:
        return None, f"{label}의 폴더 깊이가 너무 깁니다"
    if any(x in ("", ".", "..") or x.startswith(".") for x in parts):
        return None, f"{label}에 쓸 수 없는 조각이 있습니다"
    return parts, None


def _app_inside(base, parts):
    """`base` 아래의 실제 경로가 `base` 를 벗어나지 않는지. 중간 심볼릭 링크도 잡습니다."""
    try:
        return base.joinpath(*parts).resolve() == base.resolve().joinpath(*parts)
    except OSError:
        return False


def project_app(name, root=ROOT):
    """`projects/<이름>/app.json` 선언을 읽습니다.

    없으면 None (평범한 프로젝트), 있으면 runnable/url/title/root/entry. 잘못된 선언은
    runnable False + 사람이 읽을 수 있는 reason 입니다. 어떤 입력에도 예외를 던지지 않습니다.
    """
    d, err = _project_dir(name, root)
    if err:
        return None
    manifest = d / PROJECT_APP_MANIFEST
    try:
        if manifest.is_symlink():
            return {"runnable": False, "reason": "app.json 은 심볼릭 링크일 수 없습니다"}
        if not manifest.is_file():
            return None
        raw = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"runnable": False, "reason": f"app.json 을 읽지 못했습니다: {type(e).__name__}"}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {"runnable": False, "reason": "app.json 이 올바른 JSON 이 아닙니다"}
    if not isinstance(data, dict):
        return {"runnable": False, "reason": "app.json 은 JSON 객체여야 합니다"}

    root_value = data.get("root", "web")
    entry_value = data.get("entry", "index.html")
    title_value = data.get("title", name)

    root_parts, why = _app_parts(root_value, "root")
    if why:
        return {"runnable": False, "reason": why}
    app_root = d.joinpath(*root_parts)
    if not _app_inside(d, root_parts) or app_root.is_symlink() or not app_root.is_dir():
        return {"runnable": False, "reason": "root 가 프로젝트 안의 실제 폴더가 아닙니다"}

    entry_parts, why = _app_parts(entry_value, "entry")
    if why:
        return {"runnable": False, "reason": why}
    entry = app_root.joinpath(*entry_parts)
    if not _app_inside(app_root, entry_parts) or entry.is_symlink() or not entry.is_file():
        return {"runnable": False, "reason": "entry 가 앱 폴더 안의 실제 파일이 아닙니다"}

    if not isinstance(title_value, str):
        title_value = name
    title_value = title_value[:80]
    return {"runnable": True, "url": f"{PROJECT_APP_URL_PREFIX}{name}/", "title": title_value,
            "root": root_value, "entry": entry_value}


def project_app_file(name, rel, root=ROOT):
    """`/app/<이름>/...` 한 파일의 (code, bytes 또는 오류 dict, content-type)."""
    app = project_app(name, root)
    if app is None:
        return 404, {"ok": False, "error": f"실행 선언이 없는 프로젝트입니다: {name}"}, None
    if not app.get("runnable"):
        return 404, {"ok": False, "error": app.get("reason") or "실행할 수 없는 프로젝트입니다"}, None

    d, err = _project_dir(name, root)
    if err:
        return 404, {"ok": False, "error": "프로젝트 폴더가 없습니다"}, None

    root_parts, why = _app_parts(app.get("root"), "root")
    if why:
        return 404, {"ok": False, "error": why}, None
    app_root = d.joinpath(*root_parts)
    if not _app_inside(d, root_parts) or app_root.is_symlink() or not app_root.is_dir():
        return 404, {"ok": False, "error": "앱 폴더가 없습니다"}, None

    if rel is None:
        rel = ""
    if not isinstance(rel, str):
        return 404, {"ok": False, "error": "파일 경로가 올바르지 않습니다"}, None
    if not rel:
        rel = app.get("entry") or "index.html"

    parts, why = _app_parts(rel, "파일 경로")
    if why:
        return 404, {"ok": False, "error": why}, None
    target = app_root.joinpath(*parts)
    if not _app_inside(app_root, parts) or target.is_symlink() or not target.is_file():
        return 404, {"ok": False, "error": f"그런 파일이 없습니다: {rel[:120]}"}, None

    try:
        st = target.stat()
    except OSError as e:
        return 500, {"ok": False, "error": f"파일을 읽지 못했습니다: {type(e).__name__}"}, None
    if st.st_size > PROJECT_APP_FILE_MAX_BYTES:
        return 413, {"ok": False, "error": f"파일이 {PROJECT_APP_FILE_MAX_BYTES}바이트를 넘습니다"}, None
    try:
        with open(target, "rb") as fh:
            raw = fh.read(PROJECT_APP_FILE_MAX_BYTES + 1)
    except OSError as e:
        return 500, {"ok": False, "error": f"파일을 읽지 못했습니다: {type(e).__name__}"}, None
    if len(raw) > PROJECT_APP_FILE_MAX_BYTES:
        return 413, {"ok": False, "error": f"파일이 {PROJECT_APP_FILE_MAX_BYTES}바이트를 넘습니다"}, None

    return 200, raw, CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")


def app_csp(origin=""):
    """`/app/` 응답에 붙는 CSP. `origin` 은 `https://host:port` 또는 빈 문자열."""
    o = f" {origin}" if origin else ""

    def with_self(tail=""):
        return f"'self'{o}{tail}"

    return "sandbox allow-scripts allow-popups allow-modals; " + "; ".join((
        f"default-src {with_self()}",
        f"img-src {with_self(' data: blob:')}",
        f"style-src {with_self(' ')}'unsafe-inline'",
        f"script-src {with_self()}",
        f"connect-src {with_self()}",
        f"font-src {with_self(' data:')}",
        "frame-ancestors 'self'",
        "base-uri 'none'",
        "form-action 'none'",
    ))


_REQ_PROJECT_RE = re.compile(r"\A/api/projects/([^/]{1,400})/(files|file)\Z")
_APP_RE = re.compile(
    r"\A/app/(?:~(?P<ticket>[^/]{1,160})/)?(?P<name>[^/~][^/]{0,399})(?P<slash>/(?P<rel>.*))?\Z", re.S)


def create_request(payload, root=ROOT):
    """요청 파일을 하나 만듭니다. (성공 여부, 결과 딕셔너리) 를 돌려줍니다.

    **서버가 쓰는 유일한 파일입니다.** 상태는 항상 `NEW`, 분담(`subtasks`)은 비웁니다 -
    쪼개는 것은 관리자의 판단이고(`8.0-2`) 웹에서 들어온 값으로 정하지 않습니다.
    """
    if not isinstance(payload, dict):
        return False, {"ok": False, "error": "JSON 객체가 아닙니다"}
    title = _meaningful(payload.get("title"))
    if not title:
        return False, {"ok": False, "error": "제목(title)은 비워 둘 수 없습니다"}
    if len(title) > MAX_TITLE:
        return False, {"ok": False, "error": f"제목이 {MAX_TITLE}자를 넘습니다 ({len(title)}자)"}
    detail = str(payload.get("detail") or "").strip()
    if len(detail) > MAX_DETAIL:
        return False, {"ok": False, "error": f"본문이 {MAX_DETAIL}자를 넘습니다 ({len(detail)}자)"}
    # 빈 요청자를 조용히 "(익명)" 으로 채우지 않습니다. 11-09 17:39 에 태석님이 직접
    # 넣은 요청이 `(익명)` 으로 저장돼 누가 시킨 일인지 파일만 보고는 알 수 없었습니다.
    # 요청자는 분담·우선순위 판단의 근거라 비워 둘 값이 아닙니다 (REV 111).
    raw_requester = payload.get("requester")
    if raw_requester is not None and not isinstance(raw_requester, str):
        # `str()` 로 바꾸면 `['x']` 가 `"['x']"` 로 저장됩니다 (S4 재검수 6번).
        return False, {"ok": False, "error": "요청자(requester)는 문자열이어야 합니다"}
    requester = _meaningful(raw_requester)[:60]
    if not requester:
        return False, {"ok": False, "error": "요청자(requester)는 비워 둘 수 없습니다"}
    project, perr = _project_of(payload)
    if perr:
        return False, {"ok": False, "error": perr}

    reqs_dir = root / ".aimem" / "requests"
    # 개수 상한 (S4 검수 3번). 공개되면 요청 POST 가 디스크를 채우는 가장 싼 길이고,
    # `/api/state` 가 매 폴링마다 이 디렉터리를 통째로 읽으므로 화면까지 같이 느려집니다.
    try:
        if sum(1 for _ in reqs_dir.glob("*.json")) >= MAX_REQUESTS:
            return False, {"ok": False, "error": f"요청 파일이 {MAX_REQUESTS}건을 넘었습니다. "
                                                 "관리자가 끝난 요청을 아카이브한 뒤 다시 올리십시오"}
    except OSError:
        pass

    now = datetime.datetime.now()
    # 식별자 체계(18:15): 요청 id 는 Q-<YYMMDD>-<4자> (옛 20261109-HHMMSS-xxxx 파일은 그대로 읽힌다)
    rid = f"Q-{now.strftime('%y%m%d')}-{secrets.token_hex(2)}"
    slug = _slug(title)
    name = f"{rid}{'-' + slug if slug else ''}.json"
    try:
        reqs_dir.mkdir(parents=True, exist_ok=True)
        target = reqs_dir / name
        record = {
            "id": rid,
            "created": now.isoformat(timespec="seconds"),
            "requester": requester,
            "project": project,            # 결과물이 쌓일 곳 `projects/<이름>/`. 빈 값 = 함대 자체의 일
            "title": title,
            "detail": detail,
            "status": REQUEST_STATES[0],   # NEW. 분담은 관리자가 한다
            "subtasks": [],
        }
        # 같은 초에 두 번 들어와도 덮지 않습니다 - 토큰이 붙어 있어 사실상 안 겹치지만
        # 겹치면 쓰지 않고 실패로 돌려주는 쪽이 조용한 소실보다 낫습니다.
        with open(target, "x", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=1)
            f.write("\n")
    except OSError as e:
        return False, {"ok": False, "error": f"요청 파일을 쓰지 못했습니다: {e}"}
    return True, {"ok": True, "id": rid, "path": str(target.relative_to(root))}


#: 수정 경로의 요청 id. 새 체계(Q-YYMMDD-xxxx)와 옛 체계(YYYYMMDD-HHMMSS-xxxx)만 받습니다 -
#: 이 정규식이 경로 탈출을 막는 1차 방어입니다 (파일은 glob 으로 찾고 내용의 id 를 다시 대조).
_REQ_EDIT_RE = re.compile(r"\A/api/requests/(Q-\d{6}-[0-9a-f]{4}|\d{8}-\d{6}-[0-9a-f]{4})/edit\Z")


_REQ_GET_RE = re.compile(r"\A/api/requests/(Q-\d{6}-[0-9a-f]{4}|\d{8}-\d{6}-[0-9a-f]{4})\Z")


def _find_request(req_id, root):
    """(경로, 레코드) 또는 (None, None). 파일 이름이 아니라 **내용의 id** 로 대조합니다."""
    for f in (root / ".aimem" / "requests").glob(f"{req_id}*.json"):
        if f.is_symlink() or not f.is_file():
            continue
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("id") == req_id:
            return f, obj
    return None, None


def request_detail(req_id, root=ROOT):
    """요청 하나의 **전문**. `/api/state` 는 본문을 600자로 자르므로(REV 115) '전체 보기'와
    웹 수정이 이것을 씁니다. 상세 응답과 같은 가림(경로·확인토큰)을 겁니다."""
    try:
        f, rec = _find_request(req_id, root)
    except OSError as e:
        return 500, {"ok": False, "error": f"요청 디렉터리를 읽지 못했습니다: {e}"}
    if f is None:
        return 404, {"ok": False, "error": f"그런 요청이 없습니다: {req_id}"}
    mask = _detail_masker(root)
    out = {k: rec.get(k) for k in ("id", "created", "edited", "requester", "project", "title", "detail", "status")}
    out["subtasks"] = len(rec.get("subtasks") or [])
    out["editable"] = rec.get("status") == REQUEST_STATES[0] and not rec.get("subtasks")
    out["ok"] = True
    return 200, mask_deep(out, mask)


def update_request(req_id, payload, root=ROOT):
    """**아직 관리자가 분담하지 않은(NEW·서브태스크 없음) 요청**의 제목·본문만 고칩니다.

    태석님 요청 `Q-261110-549a` (2026-11-10): "요청분담트리에 관리자 분담 대기 중인 작업
    요청은 수정할 수 있게". 서버 쓰기는 원래 "요청 파일 생성 하나뿐"이었고, 이것이 두 번째
    쓰기입니다 - 범위를 **같은 요청 파일, NEW 상태, 제목·본문 두 필드**로 묶었습니다.
    요청자·상태·분담은 바꾸지 않습니다. 분담이 시작된 요청은 409 로 거절합니다(관리자가
    이미 읽고 쪼갠 내용이 웹에서 바뀌면 분담 근거가 사라집니다).
    """
    if not isinstance(payload, dict):
        return 400, {"ok": False, "error": "JSON 객체가 아닙니다"}
    title = _meaningful(payload.get("title"))
    if not title:
        return 400, {"ok": False, "error": "제목(title)은 비워 둘 수 없습니다"}
    if len(title) > MAX_TITLE:
        return 400, {"ok": False, "error": f"제목이 {MAX_TITLE}자를 넘습니다 ({len(title)}자)"}
    raw_detail = payload.get("detail")
    if raw_detail is not None and not isinstance(raw_detail, str):
        return 400, {"ok": False, "error": "본문(detail)은 문자열이어야 합니다"}
    detail = str(raw_detail or "").strip()
    if len(detail) > MAX_DETAIL:
        return 400, {"ok": False, "error": f"본문이 {MAX_DETAIL}자를 넘습니다 ({len(detail)}자)"}
    try:
        target, record = _find_request(req_id, root)
    except OSError as e:
        return 500, {"ok": False, "error": f"요청 디렉터리를 읽지 못했습니다: {e}"}
    if target is None:
        return 404, {"ok": False, "error": f"그런 요청이 없습니다: {req_id}"}
    if record.get("status") != REQUEST_STATES[0] or record.get("subtasks"):
        return 409, {"ok": False, "error": "관리자가 이미 분담을 시작한 요청은 웹에서 고칠 수 없습니다 "
                                           f"(상태 {record.get('status')})"}
    if "project" in payload:            # 주면 바꾸고, 안 주면 그대로 (옛 화면은 이 키를 보내지 않는다)
        project, perr = _project_of(payload)
        if perr:
            return 400, {"ok": False, "error": perr}
        record["project"] = project
    record["title"] = title
    record["detail"] = detail
    record["edited"] = datetime.datetime.now().isoformat(timespec="seconds")
    tmp = target.with_name(target.name + ".tmp")
    try:
        with open(tmp, "x", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, target)
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        return 500, {"ok": False, "error": f"요청 파일을 쓰지 못했습니다: {e}"}
    return 200, {"ok": True, "id": req_id, "edited": record["edited"]}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "aimem-monitor/1.0"
    protocol_version = "HTTP/1.1"
    root = ROOT
    #: `serve()` 가 묶어 넣습니다. 기본값은 **옛 동작 그대로**(로컬 http, 인증 없음).
    require_auth = False
    tls = False
    access_token = None
    guard = None
    device = None      # DevicePending - GitHub 기기 흐름의 열린 확인 코드 (serve() 가 채운다)
    #: 요청 생성 속도 제한. **클래스 속성 기본값으로 둡니다** - `--tls`/`--auth` 없이
    #: 로컬로 띄워도 걸립니다. 공개 여부와 무관하게 디스크·화면을 지키는 선이고,
    #: 사람이 폼으로 분당 5건을 넘길 일은 없습니다.
    rate = None
    #: 거절(400)용 별도 버킷. 성공 버킷과 나눠 두지 않으면 400 이 무제한입니다.
    fail_rate = None
    #: 소켓 타임아웃. 없으면 본문을 보내다 멈춘 연결 하나가 스레드를 영원히 잡습니다
    #: (S4 검수 2번 실측: `Content-Length: 5` + 본문 미전송 -> 무한 대기).
    timeout = 15

    # 접근 로그를 한 줄로 줄입니다. 기본 포맷은 5초 폴링에 묻혀 쓸모가 없습니다.
    def log_message(self, fmt, *args):
        # 제어문자를 `\xNN` 으로 바꿉니다 - 요청 경로의 ESC 가 그대로 찍히면 로그를 보는
        # 터미널이 조종당합니다 (S4 검수 7번. 표준 구현의 치환을 덮어쓰면서 잃었던 것입니다).
        line = "%s %s" % (datetime.datetime.now().isoformat(timespec="seconds"), fmt % args)
        line = _TICKET_LOG_RE.sub("/app/~***", line)      # 티켓은 가립니다 (R11 검수 A 결함 2)
        sys.stderr.write(line.translate(_LOG_SAFE) + "\n")

    def version_string(self):
        # 파이썬 세부 버전을 공개면에 싣지 않습니다 (S4 검수 5번).
        return "aimem-monitor"

    def send_error(self, code, message=None, explain=None):
        """기본 `send_error` 는 보안 헤더 없이 HTML 을 내보냅니다 (S4 검수 6번).

        501(미지원 메서드)·414(긴 URI)·400(깨진 요청줄)이 그 길로 나갔습니다.
        같은 헤더를 붙인 JSON 으로 통일합니다.
        """
        try:
            self.close_connection = True
            short = (message or self.responses.get(code, ("?",))[0])
            self._send(code, json.dumps({"ok": False, "error": str(short)[:200]}, ensure_ascii=False),
                       extra=[("Connection", "close")])
        except Exception:  # noqa: BLE001 - 오류 응답이 또 터지면 표준 경로로 떨어진다
            super().send_error(code, message, explain)

    # -- 응답 도우미 ---------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=(), csp=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            if k == "Content-Security-Policy" and csp is not None:
                v = csp
            self.send_header(k, v)
        if self._want_hsts():
            self.send_header(*HSTS_HEADER)
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # -- 인증 ----------------------------------------------------------------
    def _want_hsts(self):
        """HSTS 는 **이름(도메인)으로 들어온 요청에만** 보냅니다 (2026-11-10, HTTPS 전환 부작용 점검).

        HSTS 는 포트가 아니라 **호스트 전체**에 걸립니다. 인증서를 신뢰 저장소에 넣고
        `https://localhost:18799` 로 한 번 들어오면 브라우저가 1년 동안 `http://localhost:<아무 포트>`
        를 https 로 바꿔, 같은 PC 의 다른 로컬 http 서비스(오픈클로 웹 등)가 깨질 수 있습니다.
        IP 주소는 브라우저가 어차피 HSTS 를 적용하지 않으므로 같이 뺍니다.
        """
        if not self.tls:
            return False
        host = (self.headers.get("Host") or "").strip().lower() if self.headers else ""
        if host.startswith("["):
            return False                     # IPv6 리터럴
        host = host.rsplit(":", 1)[0] if ":" in host else host
        if not host or host == "localhost" or host.endswith(".localhost"):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True

    def _audit(self, event, detail=""):
        audit(self.root, event, self._client_ip(), self._subject(), detail)

    def _client_ip(self):
        # `X-Forwarded-For` 를 **믿지 않습니다.** 믿으면 헤더 한 줄로 실패 제한을 우회합니다.
        return self.client_address[0] if self.client_address else "?"

    def _cookie(self, name):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            jar = http.cookies.SimpleCookie()
            jar.load(raw)
        except http.cookies.CookieError:
            return None
        m = jar.get(name)
        return m.value if m else None

    def _subject(self):
        """인증된 주체 문자열 또는 None. Bearer 토큰 -> 쿠키 순으로 봅니다."""
        tok = self.access_token
        if not tok:
            return None
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            given = auth[len("Bearer "):].strip()
            # 바이트 비교 (S4 검수 4번. `Bearer é` 가 `TypeError` 로 연결을 끊었습니다)
            if hmac.compare_digest(given.encode("utf-8", "replace"), tok.encode("ascii")):
                return SESSION_SUBJECT_TOKEN
            _audit_denied(self.root, "token-bad", self._client_ip(), None,
                          self._path() or self.path, self.command, "토큰 불일치")
            return None
        sess = verify_session(tok, self._cookie(SESSION_COOKIE))
        if not sess:
            if self._cookie(SESSION_COOKIE) is not None:
                _audit_denied(self.root, "session-bad", self._client_ip(), None,
                              self._path() or self.path, self.command, "서명·만료")
            return None
        subject = sess["subject"]
        # **GitHub 주체는 요청마다 허용 목록을 다시 봅니다.** 목록은 로그인 때만 보던 것이라,
        # 계정을 지워도 서명된 쿠키가 TTL 동안 그대로 들었습니다 (R12 T-155 가 찾음).
        # 파일은 작고 캐시하지 않습니다 - 지운 즉시 끊기는 것이 이 검사의 값어치입니다.
        if subject.startswith(SESSION_SUBJECT_GITHUB_PREFIX):
            login = subject[len(SESSION_SUBJECT_GITHUB_PREFIX):].lower()
            if login not in github_allowed_logins(self.root):
                _audit_revoked(self.root, self._client_ip(), subject,
                               self._path() or self.path, self.command)
                return None
        return subject

    def _cookie_header(self, name, value, max_age, samesite="Strict"):
        bits = [f"{name}={value}", "Path=/", "HttpOnly", f"SameSite={samesite}"]
        if max_age is not None:
            bits.append(f"Max-Age={int(max_age)}")
        if self.tls:
            # http 로컬 검증에서 `Secure` 를 붙이면 쿠키가 아예 저장되지 않습니다.
            bits.append("Secure")
        return ("Set-Cookie", "; ".join(bits))

    def _issue_session(self, subject):
        exp = int(time.time()) + SESSION_TTL_SEC
        return self._cookie_header(SESSION_COOKIE, sign_session(self.access_token, subject, exp),
                                   SESSION_TTL_SEC)

    def _redirect(self, location, extra=()):
        body = b""
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if self._want_hsts():
            self.send_header(*HSTS_HEADER)
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _path(self):
        """경로를 **정규화해서** 돌려줍니다.

        면제 목록과 라우팅이 같은 문자열을 보아야 합니다. `urlparse().path` 는
        `//api/state`·`/./api/state`·`/login/../api/state` 를 그대로 돌려주므로,
        면제 비교를 그 문자열로 하면 `/login/..` 로 면제를 훔칠 길이 생깁니다.
        `normpath` 로 접은 뒤 **접은 결과로만** 판단합니다. 널바이트는 거부합니다.
        """
        raw = urllib.parse.urlparse(self.path).path
        if "\x00" in raw or "%00" in raw.lower():
            return None
        # **퍼센트 디코딩을 하지 않습니다.** 여기서 풀면 `/api/runs/...` 에서 한 번 더 풀려
        # 이중 디코딩이 되고, `%2e%2e%2f` 가 면제 비교를 지나는 길이 생깁니다.
        # 인코딩된 채로 남은 경로는 면제 목록(완전 일치)에 맞지 않으므로 그대로 인증에 걸립니다.
        p = posixpath.normpath(raw)
        if not p.startswith("/"):
            p = "/" + p
        return p

    def _app_origin(self):
        """요청 Host 로 만든 출처. 꼴 검사에 더해 **이름까지** 봅니다 (R11 검수 B 결함 1).

        허용하지 않는 이름이면 빈 문자열입니다 - CSP 는 `'self'` 만 남습니다. `]` 뒤에 아무거나
        붙는 `[::1].evil.com` 이 IP 리터럴로 통과하던 것을 막습니다 (R11 재검수 남은 결함 2).
        """
        host = (self.headers.get("Host") or "").strip() if self.headers else ""
        if not re.match(r"\A[A-Za-z0-9._:\[\]-]{1,100}\Z", host):
            return ""
        m = re.fullmatch(r"(?:\[(?P<v6>[0-9A-Fa-f:.]{2,45})\]|(?P<name>[A-Za-z0-9._-]{1,100}))"
                         r"(?::(?P<port>\d{1,5}))?", host)
        if not m:
            return ""
        if not _app_host_allowed(m.group("v6") or m.group("name")):
            return ""
        return ("https" if self.tls else "http") + "://" + host

    def _auth_gate(self, path):
        """인증이 필요한데 없으면 응답을 보내고 True. 통과면 False."""
        if not self.require_auth or path in AUTH_EXEMPT_PATHS:
            return False
        # 티켓 경로는 라우팅에서 티켓으로 인가합니다. 불투명 출처는 SameSite=Strict
        # 쿠키를 싣지 못하므로 세션 검사보다 먼저 통과시켜야 합니다.
        # **라우팅과 같은 입력(원본 경로)·같은 정규식으로 판단합니다** (R11 검수 A 결함 1, 인증 우회). 전에는 정규화된
        # 경로의 접두만 봐서, 무인증 `GET /app/<이름>/../~x/` 가 정규화하면 `/app/~x` 라 여기를 지났고, 라우팅은 원본을
        # "티켓 없음 → 발급" 으로 읽어 **유효한 티켓을 서명해 내줬습니다.** 원본에 `.`·`..`·빈 조각이 있으면 티켓 경로가 아닙니다.
        if path.startswith(PROJECT_APP_URL_PREFIX + PROJECT_APP_TICKET_PREFIX):
            raw = urllib.parse.urlparse(self.path).path
            am = _APP_RE.match(raw)
            clean = posixpath.normpath(raw) == (raw.rstrip("/") or "/")
            if am and am.group("ticket") is not None and clean:
                return False
            self.close_connection = True
            self._json(404, {"ok": False, "error": "없는 경로입니다"})
            return True
        if self._subject():
            return False
        wants_login = (path in AUTH_UNAUTH_REDIRECT_PATHS
                       or any(path.startswith(p) for p in AUTH_UNAUTH_REDIRECT_PREFIXES))
        if wants_login and self.command in ("GET", "HEAD"):
            self._redirect("/login")
            return True
        # **연결을 닫습니다.** POST 본문을 읽지 않고 거절하므로, 같은 연결을 이어 쓰면
        # 남은 본문이 다음 요청줄로 읽힙니다 (S4 검수 5번 실측).
        self.close_connection = True
        self._send(401, json.dumps({"ok": False, "error": "인증이 필요합니다. /login 에서 접근 토큰을 넣으십시오."},
                                   ensure_ascii=False), extra=[("Connection", "close")])
        return True

    def _secrets(self):
        """응답에서 반드시 가려야 할 **값**들. 비어 있는 것은 거릅니다."""
        vals = [self.access_token,
                os.environ.get(KISTI_API_KEY_ENV),
                os.environ.get(GITHUB_CLIENT_SECRET_ENV)]
        return [v for v in vals if isinstance(v, str) and len(v) >= 8]

    def _scrub_secrets(self, text):
        """직렬화된 응답 본문에서 비밀 **값**을 지웁니다.

        마지막 방어선입니다. `/api/runs/<id>` 는 작업자의 브리프·stderr 를 그대로
        싣는데, 작업자가 `cat .aimem/tls/access-token` 이나 `env` 를 한 번이라도
        찍으면 그 값이 기록에 남습니다 (S4 검수 1번). 원천 차단은 `reader` 쪽이고
        여기서는 **값 일치**로 한 번 더 거릅니다.
        """
        for v in self._secrets():
            text = text.replace(v, "***")
        return text

    def _json(self, code, obj):
        # `allow_nan=False`: 그래프 파일의 `max_attempts: NaN` 같은 **외부 입력**이 그대로
        # 나가면 브라우저 `JSON.parse` 가 통째로 거부합니다 - 화면이 빈 채로 멈춥니다
        # (S4 재검수 7번, REV 111). 직렬화에 실패하면 그 사실만 적어 내보냅니다.
        try:
            body = json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False)
        except ValueError as e:
            body = json.dumps({"ok": False, "error": f"JSON 직렬화 실패(NaN/Infinity?): {e}"},
                              ensure_ascii=False, indent=1)
            code = 500 if code == 200 else code
        self._send(code, self._scrub_secrets(body))

    def _static(self, rel):
        """`static/` 아래만 서빙합니다. `..` 과 심볼릭 링크 탈출을 막습니다."""
        try:
            target = (STATIC / rel).resolve()
            target.relative_to(STATIC.resolve())
        except (ValueError, OSError):
            return self._json(403, {"ok": False, "error": "static 폴더 밖입니다"})
        if not target.is_file():
            # 절대경로를 힌트에 싣지 않습니다 - `/favicon.ico` 는 인증 면제라
            # **무인증으로** 서버 경로가 샜습니다 (S4 검수 3번).
            return self._json(404, {"ok": False, "error": f"없는 파일입니다: {rel}",
                                    "hint": "static/ 아래에 그 파일이 없습니다"})
        ctype = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        return self._send(200, target.read_bytes(), ctype)

    # -- 라우팅 --------------------------------------------------------------
    def do_GET(self):
        path = self._path()
        if path is None:
            return self._json(400, {"ok": False, "error": "경로에 널바이트가 있습니다"})
        if self._auth_gate(path):
            return None
        raw_path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            return self._static("login.html")
        if path == "/api/authinfo":
            subj = self._subject()
            return self._json(200, {"ok": True, "github_enabled": github_enabled(),
                                    "github_device": github_device_enabled(),
                                    "tls": bool(self.tls), "auth_required": bool(self.require_auth),
                                    "authenticated": bool(subj), "who": subject_label(subj)})
        if path == "/auth/github/start":
            return self._github_start()
        if path == GITHUB_CALLBACK_PATH:
            return self._github_callback()
        if path == "/api/state":
            return self._json(200, collect_state(self.root))
        if path == "/api/models":
            return self._json(200, openclaw_models())
        if path == "/api/health":
            state = collect_state(self.root)
            return self._json(200, {"ok": not state.get("errors"),
                                    "rev": (state.get("aimem") or {}).get("rev"),
                                    "errors": state.get("errors", [])})
        if path.startswith("/api/runs/"):
            rid = urllib.parse.unquote(path[len("/api/runs/"):])
            if not re.match(RUN_ID_RE, rid):
                return self._json(400, {"ok": False, "error": f"잘못된 run id 입니다: {rid[:80]}"})
            d = run_detail(rid, self.root)
            if not d.get("found"):
                return self._json(404, {"ok": False, "error": f"그런 실행 기록이 없습니다: {rid}",
                                        "detail": d})
            return self._json(200, d)
        mm = _REQ_MGR_RE.match(path)
        if mm:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code, body = manager_detail(mm.group(1), self.root, all_steps=(q.get("all") or [""])[0] == "1")
            return self._json(code, body)
        m = _REQ_GET_RE.match(path)
        if m:
            code, body = request_detail(m.group(1), self.root)
            return self._json(code, body)
        pm = _REQ_PROJECT_RE.match(path)
        if pm:
            pname = urllib.parse.unquote(pm.group(1))
            if pm.group(2) == "files":
                code, body = project_files(pname, self.root)
            else:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                code, body = project_file(pname, (q.get("path") or [""])[0], self.root)
            return self._json(code, body)
        am = _APP_RE.match(raw_path)
        if am:
            app_name = urllib.parse.unquote(am.group("name"))
            ticket = am.group("ticket")
            if ticket is None:
                # 서명은 **이 요청이 인증됐음을 이 자리에서 확인한 뒤에만** 합니다 (심층 방어, R11 검수 A 결함 1).
                # 게이트가 이미 봤다고 가정하지 않습니다.
                subject = self._subject() if self.require_auth else None
                if self.require_auth and subject is None:
                    return self._redirect("/login")
                if not _PROJECT_RE.match(app_name):
                    return self._json(404, {"ok": False, "error": "프로젝트 이름이 올바르지 않습니다"})
                exp = int(time.time()) + PROJECT_APP_TICKET_TTL_SEC
                ticket = app_ticket(app_name, exp, _app_ticket_key(self), subject)
                location = (PROJECT_APP_URL_PREFIX + PROJECT_APP_TICKET_PREFIX + ticket + "/"
                            + urllib.parse.quote(app_name, safe="") + "/")
                rel = am.group("rel") or ""
                if rel:
                    location += rel
                return self._redirect(location)
            parts = _app_ticket_parts(ticket)
            if not parts:
                _audit_denied(self.root, "app-ticket-bad", self._client_ip(), None,
                              raw_path, self.command, "형식")
                return self._json(403, {"ok": False, "error": APP_TICKET_INVALID_ERROR})
            key = _app_ticket_key(self)
            candidates = [SESSION_SUBJECT_TOKEN, APP_TICKET_NO_SUBJECT]
            candidates += ["gh:" + login for login in github_allowed_logins(self.root)]
            ticket_subject = app_ticket_resolve(ticket, key, candidates)
            if ticket_subject is None:
                _audit_denied(self.root, "app-ticket-bad", self._client_ip(), None,
                              raw_path, self.command, "주체 못 찾음(회수 또는 위조)")
                return self._json(403, {"ok": False, "error": APP_TICKET_INVALID_ERROR})
            if not app_ticket_ok(ticket, app_name, key, ticket_subject):
                _audit_denied(self.root, "app-ticket-bad", self._client_ip(), ticket_subject,
                              raw_path, self.command, "서명·만료")
                return self._json(403, {"ok": False, "error": APP_TICKET_INVALID_ERROR})
            if self.require_auth and ticket_subject == APP_TICKET_NO_SUBJECT:
                _audit_denied(self.root, "app-ticket-bad", self._client_ip(), ticket_subject,
                              raw_path, self.command, "무주체")
                return self._json(403, {"ok": False, "error": APP_TICKET_INVALID_ERROR})
            credential_subject = self._subject()
            if credential_subject is not None and (
                    _app_ticket_canon(credential_subject) != _app_ticket_canon(ticket_subject)):
                _audit_denied(self.root, "app-ticket-bad", self._client_ip(), credential_subject,
                              raw_path, self.command, "주체 불일치", authenticated=True)
                return self._json(403, {"ok": False, "error": APP_TICKET_INVALID_ERROR})
            rel = urllib.parse.unquote(am.group("rel") or "").split("?", 1)[0]
            code, data, ctype = project_app_file(app_name, rel, self.root)
            if code == 200:
                return self._send(200, data, ctype,
                                  extra=[("Access-Control-Allow-Origin", "null"), ("Vary", "Origin")],
                                  csp=app_csp(self._app_origin()))
            return self._json(code, data)
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        # 프런트엔드가 `/app.js` 처럼 평평하게 부를 수도 있어 받아 줍니다.
        if "/" not in path[1:] and pathlib.Path(path).suffix in CONTENT_TYPES:
            return self._static(path[1:])
        return self._json(404, {"ok": False, "error": f"없는 경로입니다: {path}"})

    do_HEAD = do_GET

    def _read_json_body(self):
        """(payload, 오류응답을 보냈나). 본문 상한을 **읽기 전에** 겁니다.

        **`Content-Length` 가 없거나 음수면 거절합니다** (S4 검수 2번, REV 113 실측):
        `-1` 이 `length > MAX_BODY` 를 지나 `rfile.read(-1)` 로 들어가면 EOF 까지 -
        즉 상한 없이 - 읽습니다. 연결을 닫지 않으면 스레드가 그대로 묶입니다.
        """
        if self.headers.get("Content-Length") is None:
            self._json(411, {"ok": False, "error": "Content-Length 가 필요합니다"})
            return None, True
        try:
            length = int(self.headers.get("Content-Length"))
        except ValueError:
            self._json(400, {"ok": False, "error": "Content-Length 가 숫자가 아닙니다"})
            return None, True
        if length < 0:
            self._json(400, {"ok": False, "error": "Content-Length 가 음수입니다"})
            return None, True
        if length > MAX_BODY:
            self._json(413, {"ok": False, "error": f"본문이 {MAX_BODY}바이트를 넘습니다"})
            return None, True
        raw = self.rfile.read(length) if length else b""
        try:
            return (json.loads(raw.decode("utf-8")) if raw else {}), False
        except (ValueError, UnicodeDecodeError) as e:
            self._json(400, {"ok": False, "error": f"JSON 을 읽지 못했습니다: {e}"})
            return None, True

    def do_POST(self):
        path = self._path()
        if path is None:
            return self._json(400, {"ok": False, "error": "경로에 널바이트가 있습니다"})
        if self._auth_gate(path):
            return None
        if path == "/api/login":
            return self._login()
        if path == GITHUB_DEVICE_START_PATH:
            return self._github_device_start()
        if path == GITHUB_DEVICE_POLL_PATH:
            return self._github_device_poll()
        if path == "/api/logout":
            self._audit("logout")
            return self._send(200, json.dumps({"ok": True}, ensure_ascii=False),
                              extra=[self._cookie_header(SESSION_COOKIE, "", 0)])
        edit = _REQ_EDIT_RE.match(path)
        fleet_act = _REQ_FLEET_RE.match(path)
        slot_m = _REQ_SLOT_RE.match(path)
        slot_add_path = path == "/api/slots"
        archive_path = path == "/api/archive"
        if path != "/api/requests" and not edit and not fleet_act and not slot_m and not slot_add_path and not archive_path:
            return self._json(404, {"ok": False, "error": f"없는 경로입니다: {path}"})
        # CSRF (S4 검수 4번). 세션 쿠키가 `SameSite=Strict` 라 1차 방어는 되지만,
        # 쿠키 정책 하나에만 기대지 않습니다. `<form enctype="text/plain">` 으로는
        # JSON Content-Type 을 만들 수 없으므로 이 두 줄이 폼 기반 위조를 끊습니다.
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self.close_connection = True   # 본문 미소진 (S4 검수 5번)
            return self._send(415, json.dumps({"ok": False, "error": "Content-Type 은 application/json 이어야 합니다"}, ensure_ascii=False),
                              extra=[("Connection", "close")])
        origin = self.headers.get("Origin")
        if origin:
            host = (self.headers.get("Host") or "").lower()
            if urllib.parse.urlparse(origin).netloc.lower() != host:
                self.close_connection = True   # 본문 미소진 (S4 검수 5번)
                return self._send(403, json.dumps({"ok": False, "error": "Origin 이 Host 와 다릅니다"},
                                                  ensure_ascii=False),
                                  extra=[("Connection", "close")])
        if archive_path:
            payload, sent = self._read_json_body()
            if sent:
                return None
            who = self._subject()
            code, result = archive_action(payload if isinstance(payload, dict) else {}, f"웹({subject_label(who)})" if who else "웹", self.root)
            if not result.get("dry_run", True):
                self._audit("archive", f"{code} days={result.get('plan', {}).get('days')} "
                                       f"moved={json.dumps(result.get('moved_counts', {}), ensure_ascii=False)[:300]}")
            return self._json(code, result)
        if slot_m or slot_add_path:
            # 슬롯 관리 - 함대 제어와 같이 속도 제한 없이, CSRF·인증은 거친다. 감사 로그에 남긴다.
            payload, sent = self._read_json_body()
            if sent:
                return None
            who = self._subject()
            by = f"웹({subject_label(who)})" if who else "웹"
            action, slot = ("add", None) if slot_add_path else (slot_m.group(2), slot_m.group(1))
            code, result = slot_action(action, slot, payload if isinstance(payload, dict) else {}, by, self.root)
            self._audit("slot-" + action, f"{slot or (result.get('slot') or {}).get('slot') or '-'} {code}")
            return self._json(code, result)
        if fleet_act:
            # 함대 제어는 속도 제한을 걸지 않습니다 - '완전 중지' 가 한도에 막히면 안 됩니다.
            # CSRF(위 두 검사)와 인증(`_auth_gate`)은 그대로 거칩니다.
            payload, sent = self._read_json_body()
            if sent:
                return None
            who = self._subject()
            code, result = fleet_action(fleet_act.group(1), f"웹({subject_label(who)})" if who else "웹", self.root, payload)
            self._audit("fleet-" + fleet_act.group(1), f"{code} mode={result.get('mode')}"
                        + (f" chain={(result.get('chain') or {}).get('on')}" if fleet_act.group(1) == "chain" else ""))
            return self._json(code, result)
        # 속도 제한 (S4 유출 검수 3번). **본문을 읽기 전에** 겁니다 - 막을 요청의
        # 64KB 를 굳이 받아들일 이유가 없습니다. 대신 연결은 끊습니다(본문 미소진).
        # 버킷이 둘인 이유는 `REQUEST_FAIL_MAX` 주석을 보십시오.
        ip = self._client_ip()
        for bucket, limit in ((self.rate, REQUEST_RATE_MAX), (self.fail_rate, REQUEST_FAIL_MAX)):
            if bucket is None:
                continue
            allowed, retry_after = bucket.allow(ip)
            if not allowed:
                if bucket is self.fail_rate and self.rate is not None:
                    self.rate.refund(ip)   # 성공 버킷에서 잡은 자리는 돌려준다
                self.close_connection = True
                return self._send(429, json.dumps(
                    {"ok": False, "error": f"요청 생성이 너무 잦습니다 ({limit}건/"
                                           f"{REQUEST_RATE_WINDOW_SEC}초). {retry_after}초 뒤에 다시 올리십시오"},
                    ensure_ascii=False),
                    extra=[("Connection", "close"), ("Retry-After", str(retry_after))])
        payload, sent = self._read_json_body()
        if sent:
            # 본문 자체가 거절된 경우(상한 초과·깨진 JSON)도 실패입니다 - 성공
            # 할당량은 돌려주고 실패 버킷에만 남깁니다.
            if self.rate is not None:
                self.rate.refund(ip)
            return None
        if edit:
            code, result = update_request(edit.group(1), payload, self.root)
            self._audit("request-edit", f"{edit.group(1)} {code}")
            ok = code == 200
            if ok and self.fail_rate is not None:
                self.fail_rate.refund(ip)
            elif not ok and self.rate is not None:
                self.rate.refund(ip)
            return self._json(code, result)
        ok, result = create_request(payload, self.root)
        self._audit("request-create", f"{result.get('id', '-')} {'ok' if ok else 'rejected'}")
        if ok:
            if self.fail_rate is not None:
                self.fail_rate.refund(ip)    # 성공했으니 실패 버킷의 자리는 돌려준다
        elif self.rate is not None:
            self.rate.refund(ip)             # 형식 오류는 성공 할당량을 깎지 않는다
        return self._json(201 if ok else 400, result)

    # -- 로그인 --------------------------------------------------------------
    def _login(self):
        """토큰 로그인. 성공하면 세션 쿠키, 실패하면 401 + 지연."""
        if not self.access_token:
            return self._json(503, {"ok": False, "error": "서버에 접근 토큰이 없습니다 (관리자에게 알리십시오)"})
        ip = self._client_ip()
        delay = self.guard.check(ip) if self.guard else 0.0
        if delay:
            time.sleep(min(delay, 10.0))
        payload, sent = self._read_json_body()
        if sent:
            return None
        given = payload.get("token") if isinstance(payload, dict) else None
        if isinstance(given, str) and hmac.compare_digest(
                given.strip().encode("utf-8", "replace"), self.access_token.encode("ascii")):
            if self.guard:
                self.guard.reset(ip)
            self.log_message("로그인 성공 %s", ip)
            audit(self.root, "login-ok", ip, SESSION_SUBJECT_TOKEN, "토큰")
            return self._send(200, json.dumps({"ok": True, "redirect": "/"}, ensure_ascii=False),
                              extra=[self._issue_session(SESSION_SUBJECT_TOKEN)])
        if self.guard:
            self.guard.fail(ip)
        self.log_message("로그인 실패 %s", ip)   # 토큰 값은 절대 적지 않습니다
        audit(self.root, "login-fail", ip, None, "토큰 불일치")
        return self._json(401, {"ok": False, "error": "토큰이 맞지 않습니다"})

    # -- GitHub OAuth (선택. 환경변수가 둘 다 있을 때만) ----------------------
    def _github_start(self):
        if not github_enabled():
            return self._json(404, {"ok": False, "error": "GitHub 로그인이 꺼져 있습니다"})
        state = secrets.token_urlsafe(24)
        q = urllib.parse.urlencode({
            "client_id": os.environ[GITHUB_CLIENT_ID_ENV],
            "redirect_uri": self._self_url(GITHUB_CALLBACK_PATH),
            "scope": "read:user",
            "state": state,
            "allow_signup": "false",
        })
        # state 쿠키는 **Lax** 여야 합니다 - Strict 면 GitHub 에서 돌아오는 이동에 쿠키가
        # 실리지 않아 정상 로그인이 CSRF 로 오인됩니다.
        return self._redirect(f"{GITHUB_AUTHORIZE_URL}?{q}",
                              extra=[self._cookie_header(GITHUB_STATE_COOKIE, state, 600, samesite="Lax")])

    # -- GitHub 기기 흐름 (client id 만 있을 때. 콜백 주소·시크릿 없음) ---------------
    def _device_body(self):
        """로그인 전 POST 두 개의 공통 문턱: JSON Content-Type, Origin==Host, 본문 소진. 보냈으면 True."""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        origin = self.headers.get("Origin")
        bad_origin = bool(origin) and urllib.parse.urlparse(origin).netloc.lower() != (self.headers.get("Host") or "").lower()
        if ctype != "application/json" or bad_origin:
            self.close_connection = True
            self._send(403 if bad_origin else 415, json.dumps({"ok": False, "error": "요청 형식이 맞지 않습니다"}, ensure_ascii=False),
                       extra=[("Connection", "close")])
            return True
        return self._read_json_body()[1]

    def _github_device_start(self):
        if self._device_body():
            return None
        if not github_device_enabled() or not self.access_token or self.device is None:
            return self._json(404, {"ok": False, "error": "GitHub 기기 로그인이 꺼져 있습니다"})
        ip = self._client_ip()
        delay = self.guard.check(ip) if self.guard else 0.0
        if delay:
            time.sleep(min(delay, 10.0))
        try:
            r = github_post_form(GITHUB_DEVICE_CODE_URL, {"client_id": os.environ[GITHUB_CLIENT_ID_ENV], "scope": ""})
            device_code, user_code = r["device_code"], r["user_code"]
            interval, expires_in = int(r.get("interval", 5)), int(r.get("expires_in", 900))
        except (urllib.error.URLError, ValueError, KeyError, TypeError, OSError) as e:
            return self._json(502, {"ok": False, "error": f"GitHub 이 확인 코드를 주지 않았습니다: {type(e).__name__}"})
        aid = self.device.add(ip, device_code, interval, expires_in)
        if aid is None:
            return self._json(429, {"ok": False, "error": "열려 있는 GitHub 확인이 너무 많습니다. 잠시 뒤 다시 하십시오"})
        audit(self.root, "github-device-start", ip, None, "")
        body = {"ok": True, "user_code": str(user_code)[:16], "verification_uri": GITHUB_DEVICE_VERIFY_URL,
                "interval": interval, "expires_in": expires_in}
        return self._send(200, json.dumps(body, ensure_ascii=False),
                          extra=[self._cookie_header(GITHUB_DEVICE_COOKIE, aid, expires_in)])

    def _github_device_poll(self):
        if self._device_body():
            return None
        if not github_device_enabled() or not self.access_token or self.device is None:
            return self._json(404, {"ok": False, "error": "GitHub 기기 로그인이 꺼져 있습니다"})
        aid = self._cookie(GITHUB_DEVICE_COOKIE) or ""
        clear = self._cookie_header(GITHUB_DEVICE_COOKIE, "", 0)
        ip = self._client_ip()

        def done(code, state, error=None, extra=()):
            body = {"ok": state == "ok", "state": state}
            if error:
                body["error"] = error
            if state == "ok":
                body["redirect"] = "/"
            return self._send(code, json.dumps(body, ensure_ascii=False), extra=[clear, *extra])

        item, ask = self.device.due(aid)
        if item is None:
            return done(410, "expired", "확인 코드가 만료됐습니다. 다시 시작하십시오")
        if not ask:
            return self._json(200, {"ok": False, "state": "pending"})
        try:
            r = github_post_form(GITHUB_TOKEN_URL, {"client_id": os.environ[GITHUB_CLIENT_ID_ENV],
                                                    "device_code": item["device_code"], "grant_type": GITHUB_DEVICE_GRANT})
        except (urllib.error.URLError, ValueError, OSError):
            return self._json(200, {"ok": False, "state": "pending"})   # 일시 오류 - 다음 물음에 다시
        tok, err = r.get("access_token"), r.get("error")
        if not tok:
            if err == "authorization_pending":
                return self._json(200, {"ok": False, "state": "pending"})
            if err == "slow_down":
                self.device.slow_down(aid)
                return self._json(200, {"ok": False, "state": "pending"})
            self.device.drop(aid)
            if err == "access_denied":
                audit(self.root, "github-denied", ip, None, "승인 거절")
                return done(403, "denied", "GitHub 에서 승인을 거절했습니다")
            return done(410, "expired", "확인 코드가 만료됐습니다. 다시 시작하십시오")
        self.device.drop(aid)        # 한 번 승인은 한 번의 로그인에만
        try:
            login = github_user_login(tok)
        except (urllib.error.URLError, ValueError, OSError) as e:
            return done(502, "error", f"GitHub 계정 확인 실패: {type(e).__name__}")
        if not isinstance(login, str) or login.lower() not in github_allowed_logins(self.root):
            if self.guard:
                self.guard.fail(ip)
            self.log_message("GitHub 로그인 거절 %s (%s)", login or "?", ip)
            audit(self.root, "github-denied", ip, None, str(login or "?")[:60])
            return done(403, "denied", "허용 목록에 없는 계정입니다")
        subject = SESSION_SUBJECT_GITHUB_PREFIX + re.sub(r"[^A-Za-z0-9_-]", "", login)[:60]
        self.log_message("GitHub 로그인 성공 %s", subject)
        audit(self.root, "login-ok", ip, subject, "GitHub 기기 흐름")
        return done(200, "ok", extra=[self._issue_session(subject)])

    def _self_url(self, path):
        host = self.headers.get("Host") or f"127.0.0.1:{PORT}"
        return f"{'https' if self.tls else 'http'}://{host}{path}"

    def _github_callback(self):
        if not github_enabled():
            return self._json(404, {"ok": False, "error": "GitHub 로그인이 꺼져 있습니다"})
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = (q.get("code") or [""])[0]
        state = (q.get("state") or [""])[0]
        want = self._cookie(GITHUB_STATE_COOKIE) or ""
        clear = self._cookie_header(GITHUB_STATE_COOKIE, "", 0, samesite="Lax")
        if not code or not state or not want or not hmac.compare_digest(
                state.encode("utf-8", "replace"), want.encode("utf-8", "replace")):
            return self._send(400, json.dumps({"ok": False, "error": "state 가 맞지 않습니다"}, ensure_ascii=False),
                              extra=[clear])
        try:
            login = self._github_login(code)
        except (urllib.error.URLError, ValueError, OSError) as e:
            return self._send(502, json.dumps({"ok": False, "error": f"GitHub 교환 실패: {type(e).__name__}"},
                                              ensure_ascii=False), extra=[clear])
        allowed = github_allowed_logins(self.root)
        if not login or login.lower() not in allowed:
            self.log_message("GitHub 로그인 거절 %s (%s)", login or "?", self._client_ip())
            audit(self.root, "github-denied", self._client_ip(), None, login or "?")
            return self._send(403, json.dumps(
                {"ok": False, "error": f"허용 목록에 없는 계정입니다: {login or '?'}"}, ensure_ascii=False), extra=[clear])
        subject = SESSION_SUBJECT_GITHUB_PREFIX + re.sub(r"[^A-Za-z0-9_-]", "", login)[:60]
        self.log_message("GitHub 로그인 성공 %s", subject)
        audit(self.root, "login-ok", self._client_ip(), subject, "GitHub")
        # 세션 쿠키는 SameSite=Strict 라 **GitHub 에서 바로 넘어오는 이동에는 실리지 않습니다.**
        # 그래서 우리 출처의 작은 페이지를 거쳐 들어갑니다(같은 사이트 이동이라 쿠키가 실립니다).
        html = ("<!doctype html><meta charset=utf-8><title>로그인 완료</title>"
                "<meta http-equiv=refresh content='0; url=/'>"
                "<p>로그인했습니다. <a href=\"/\">함대 모니터로 이동</a></p>")
        return self._send(200, html, "text/html; charset=utf-8",
                          extra=[clear, self._issue_session(subject)])

    def _github_login(self, code):
        """code -> access token -> `GET /user` 의 login. 실패는 예외로 올립니다."""
        data = urllib.parse.urlencode({
            "client_id": os.environ[GITHUB_CLIENT_ID_ENV],
            "client_secret": os.environ[GITHUB_CLIENT_SECRET_ENV],
            "code": code,
            "redirect_uri": self._self_url(GITHUB_CALLBACK_PATH),
        }).encode("ascii")
        req = urllib.request.Request(GITHUB_TOKEN_URL, data=data,
                                     headers={"Accept": "application/json",
                                              "User-Agent": "aimem-monitor"})
        # 리다이렉트를 따라가지 않습니다 - 따라가면 `Authorization` 이 타 호스트로 샙니다
        # (REV 111 에서 KISTI 쪽에서 실제로 잡힌 결함).
        opener = _no_redirect_opener()
        with opener.open(req, timeout=5.0) as r:
            tok = json.loads(r.read(64 * 1024).decode("utf-8")).get("access_token")
        if not tok:
            raise ValueError("access_token 없음")
        ureq = urllib.request.Request(GITHUB_USER_URL, headers={
            "Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
            "User-Agent": "aimem-monitor"})
        with opener.open(ureq, timeout=5.0) as r:
            return json.loads(r.read(64 * 1024).decode("utf-8")).get("login")


def _sigterm_interrupt(signum, frame):
    """SIGTERM 을 `KeyboardInterrupt` 로 바꿔 `serve()` 의 `finally` 를 돌게 합니다."""
    raise KeyboardInterrupt


def serve(host=HOST, port=PORT, root=ROOT, once=False, tls=False, auth=None):
    """`auth=None` 이면 `tls` 값을 따릅니다 - **공개하면 인증이 자동으로 켜집니다.**

    반대로 `--tls` 없이 띄우면 옛 동작 그대로(로컬 http, 인증 없음)입니다.
    """
    require_auth = bool(tls) if auth is None else bool(auth)
    for k, src in load_monitor_env(root):
        log_line(f"  {k} 를 {src} 에서 읽었습니다")
    token, created = (None, False)
    if require_auth:
        token, created = ensure_access_token(root)
    handler = type("BoundHandler", (Handler,), {
        "root": root, "require_auth": require_auth, "tls": bool(tls),
        "access_token": token, "guard": LoginGuard(), "rate": RequestRateLimiter(),
        "device": DevicePending(),
        "fail_rate": RequestRateLimiter(limit=REQUEST_FAIL_MAX),
    })
    if tls:
        ctx = build_ssl_context(root)
        httpd = TLSThreadingHTTPServer((host, port), handler)
        httpd.ssl_context = ctx
    else:
        httpd = http.server.ThreadingHTTPServer((host, port), handler)
    # 운영은 `monitorctl.sh` 가 SIGTERM 으로 내립니다. 기본 처리기는 즉사라
    # `finally` 의 감사 비우기가 돌지 않습니다. 주 스레드가 아니면 signal.signal
    # 이 ValueError 를 던지므로 조용히 건너뜁니다 (시험은 스레드에서 띄웁니다).
    sigterm_installed = False
    try:
        old_sigterm = signal.signal(signal.SIGTERM, _sigterm_interrupt)
        sigterm_installed = True
    except (ValueError, OSError):
        pass
    scheme = "https" if tls else "http"
    log_line(f"AIMEM 모니터: {scheme}://{host}:{port}/  (저장소 {root})")
    log_line("  GET  /api/state  GET /api/health  POST /api/requests")
    if require_auth:
        log_line(f"  인증 켬 - /login 에서 토큰을 넣거나 `Authorization: Bearer <토큰>`")
        log_line(f"  토큰 파일: {pathlib.Path(root) / TOKEN_FILE} (0600)")
        if created:
            # **새로 만들었을 때만 한 번** 찍습니다. 매번 찍으면 로그가 토큰 저장소가 됩니다.
            log_line(f"  새 접근 토큰을 만들었습니다: {token}")
        if not tls:
            log_line("  주의: TLS 없이 인증만 켰습니다. 토큰이 평문으로 흐릅니다 (검증용으로만)")
    elif host not in ("127.0.0.1", "localhost", "::1"):
        log_line(f"  경고: {host} 에 바인드하는데 인증이 꺼져 있습니다. `--tls` 로 띄우십시오.")
    try:
        httpd.handle_request() if once else httpd.serve_forever()
    except KeyboardInterrupt:
        log_line("\n내립니다.")
    finally:
        if sigterm_installed:
            try:
                signal.signal(signal.SIGTERM, old_sigterm)
            except (ValueError, OSError):
                pass
        flush_denied_audit(root)
        httpd.server_close()
    return 0


def main(argv=None):
    import argparse
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["admin"]:
        # 접근 제어 관리 명령 (`admin.py`). --root 는 저장소 기본값을 씁니다.
        from . import admin   # noqa: PLC0415
        return admin.main(argv[1:], ROOT)
    p = argparse.ArgumentParser(description="AIMEM 함대 모니터 웹 서버 (읽기 + 요청 생성·수정 + 함대 제어). 관리: admin --help")
    p.add_argument("--host", default=HOST, help="기본 127.0.0.1. 외부 공개는 0.0.0.0 + --tls")
    p.add_argument("--port", type=int, default=PORT, help=f"기본 {PORT}")
    p.add_argument("--root", default=str(ROOT), help="저장소 루트")
    p.add_argument("--once", action="store_true", help="요청 하나만 처리하고 종료 (검증용)")
    p.add_argument("--tls", action="store_true",
                   help=f"HTTPS. {CERT_FILE} / {KEY_FILE} 를 쓰고 인증을 함께 켭니다")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--auth", action="store_true", help="TLS 없이 인증만 켠다 (검증용)")
    g.add_argument("--no-auth", action="store_true", help="TLS 를 켜도 인증은 끈다 (권하지 않음)")
    a = p.parse_args(argv)
    auth = True if a.auth else (False if a.no_auth else None)
    return serve(a.host, a.port, pathlib.Path(a.root).resolve(), a.once, tls=a.tls, auth=auth)


if __name__ == "__main__":
    sys.exit(main())
