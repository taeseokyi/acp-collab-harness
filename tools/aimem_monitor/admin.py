"""모니터 접근 제어 관리 명령 (2026-11-10, 태석님 "접근 제어 기능 넣어줘").

    PYTHONPATH=tools python3 -m aimem_monitor admin status          # 인증 설정 점검 (비밀값은 안 찍음)
    PYTHONPATH=tools python3 -m aimem_monitor admin token show      # 로그인할 접근 토큰 보기
    PYTHONPATH=tools python3 -m aimem_monitor admin token rotate    # 새 토큰 - **모든 세션이 즉시 끊김**
    PYTHONPATH=tools python3 -m aimem_monitor admin github list|allow <계정>|deny <계정>
    PYTHONPATH=tools python3 -m aimem_monitor admin cert info
    PYTHONPATH=tools python3 -m aimem_monitor admin cert renew [--ip 1.2.3.4 ...] [--dns host ...] [--days 825]
    PYTHONPATH=tools python3 -m aimem_monitor admin audit [-n 30]

세션 쿠키는 접근 토큰으로 서명합니다(`sign_session`). 그래서 **토큰을 바꾸면 발급된 모든 세션이
무효**가 됩니다 - 기기를 잃어버렸을 때의 "전부 로그아웃" 이 `token rotate` 입니다. 돌고 있는
서버는 토큰을 시작할 때 읽으므로 교체 뒤에는 서버를 다시 띄워야 합니다(`monitorctl.sh restart`).
"""
import argparse
import datetime
import ipaddress
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys

from . import CA_FILE, CERT_FILE, CERT_PROFILE_FILE, GITHUB_ALLOW_FILE, KEY_FILE, TOKEN_FILE
from . import server

_LOGIN_RE = re.compile(r"\A[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z")   # GitHub 로그인 꼴


def _p(root, rel):
    return pathlib.Path(root) / rel


def _write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


# ---------------------------------------------------------------- token
def token_show(root):
    tok = server.load_access_token(root)
    if not tok:
        print("접근 토큰이 없습니다. `admin token rotate` 로 만들거나 `--tls` 로 서버를 한 번 띄우십시오", file=sys.stderr)
        return 1
    print(tok)
    return 0


def token_rotate(root):
    tok = secrets.token_hex(32)
    _write_private(_p(root, TOKEN_FILE), tok + "\n")
    server.audit(root, "token-rotate", "cli", None, "모든 세션 무효")
    print(tok)
    print("새 토큰을 썼습니다. 발급된 세션은 모두 무효가 됩니다. 서버를 다시 띄우십시오 "
          "(tools/aimem_monitor/monitorctl.sh restart).", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- github
def _read_allow(root):
    p = _p(root, GITHUB_ALLOW_FILE)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def github_list(root):
    allowed = sorted(server.github_allowed_logins(root))
    server.load_monitor_env(root)
    print("GitHub 로그인: " + ("켜짐 (웹 흐름)" if server.github_enabled() else
                              "켜짐 (기기 흐름 - 화면의 코드를 github.com/login/device 에)" if server.github_device_enabled() else
                              "꺼짐 (GITHUB_CLIENT_ID 를 .aimem/tls/monitor.env 에. 시크릿까지 넣으면 웹 흐름)"))
    print("허용 계정: " + (", ".join(allowed) if allowed else "(없음 - 아무도 GitHub 로 들어올 수 없음)"))
    return 0


def github_allow(root, login):
    if not _LOGIN_RE.match(login or ""):
        print(f"GitHub 로그인 꼴이 아닙니다: {login!r}", file=sys.stderr)
        return 2
    lines = _read_allow(root)
    if login.lower() in {l.strip().lower() for l in lines if l.strip() and not l.strip().startswith("#")}:
        print(f"이미 허용돼 있습니다: {login}")
        return 0
    if not lines:
        lines = ["# GitHub 로그인 허용 목록 - 한 줄에 한 계정 (대소문자 무시). admin github allow/deny 로 고칩니다"]
    lines.append(login)
    _write_private(_p(root, GITHUB_ALLOW_FILE), "\n".join(lines) + "\n")
    server.audit(root, "github-allow", "cli", None, login)
    print(f"허용했습니다: {login}")
    return 0


def github_deny(root, login):
    lines = _read_allow(root)
    keep = [l for l in lines if l.strip().lower() != (login or "").lower()]
    if len(keep) == len(lines):
        print(f"목록에 없습니다: {login}")
        return 1
    _write_private(_p(root, GITHUB_ALLOW_FILE), "\n".join(keep) + "\n")
    server.audit(root, "github-deny", "cli", None, login)
    print(f"뺐습니다: {login} (이미 받은 세션은 만료(12시간)까지 유효 - 즉시 끊으려면 token rotate)")
    return 0


# ---------------------------------------------------------------- cert
def _openssl():
    o = shutil.which("openssl")
    if not o:
        raise SystemExit("openssl 이 없습니다")
    return o


def cert_info(root):
    crt = _p(root, CERT_FILE)
    if not crt.exists():
        print("인증서 없음 - `admin cert renew` 로 만드십시오")
        return 1
    out = subprocess.run([_openssl(), "x509", "-in", str(crt), "-noout", "-subject", "-issuer", "-enddate",
                          "-fingerprint", "-sha256", "-ext", "subjectAltName"], capture_output=True, text=True)
    print(out.stdout.strip() or out.stderr.strip())
    prof = _load_profile(root)
    if prof:
        print(f"발급 조건({CERT_PROFILE_FILE}): CA 디렉터리 {prof.get('ca_dir') or '없음(자체 서명)'} / "
              f"추가 DNS {prof.get('dns') or []} / 추가 IP {prof.get('ips') or []}")
    return 0 if out.returncode == 0 else 1


def _default_sans():
    dns, ips = {"localhost", "aimem-fleet"}, {"127.0.0.1"}
    try:
        host = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5).stdout.split()
        for h in host:
            try:
                if ipaddress.ip_address(h).version == 4:
                    ips.add(h)
            except ValueError:
                pass
    except (OSError, subprocess.TimeoutExpired):
        pass
    return dns, ips


def _load_profile(root):
    f = _p(root, CERT_PROFILE_FILE)
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_profile(root, ca_dir, dns, ips):
    f = _p(root, CERT_PROFILE_FILE)
    f.write_text(json.dumps({"ca_dir": str(ca_dir) if ca_dir else None, "dns": sorted(dns), "ips": sorted(ips),
                             "saved": datetime.datetime.now().isoformat(timespec="seconds")},
                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def cert_renew(root, extra_ips=(), extra_dns=(), days=825, ca_dir=None, self_signed=False):
    """서버 인증서를 새로 만듭니다 (EC P-256). 옛 것은 `.bak` 으로 남깁니다.

    두 가지 길:
      - **CA 서명** (`--ca-dir <ca.crt·ca.key 가 있는 디렉터리>`): 그 사설 CA 로 서명합니다. 태석님 PC 의
        다른 서비스(carefor-app·Signposts_of_Faith)와 같은 CA 를 쓰면 윈도우 신뢰 루트에 이미 있는
        CA 하나로 전부 통하므로 **브라우저에 아무것도 설치하지 않아도** 됩니다. CA 공개 인증서는
        `CA_FILE` 로 복사해 두고(검증용), CA 개인키는 읽기만 하고 복사하지 않습니다.
      - **자체 서명** (`--self-signed`, 또는 CA 를 한 번도 지정한 적이 없을 때): 예전 방식. 브라우저에
        `server.crt` 를 신뢰 루트로 설치해야 경고가 사라집니다.

    마지막 발급 조건은 `CERT_PROFILE_FILE` 에 적고, 다음 `renew` 는 인자 없이 쳐도 그것을 다시 씁니다
    (추가 SAN 은 **누적**됩니다 - 빼려면 파일을 고치십시오). 외부 주소(공유기 공인 IP·도메인)로
    접속하려면 `--ip`/`--dns` 로 그 주소를 넣어야 이름 불일치 경고가 나지 않습니다.
    825일은 브라우저가 받아 주는 최대 유효기간입니다.
    """
    for ip in extra_ips:
        ipaddress.ip_address(ip)   # 꼴 검사 - 틀리면 ValueError
    for d in extra_dns:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", d):
            raise SystemExit(f"DNS 이름 꼴이 아닙니다: {d!r}")
    prof = _load_profile(root)
    saved_dns, saved_ips = set(prof.get("dns") or []), set(prof.get("ips") or [])
    if self_signed:
        ca_dir = None
    elif ca_dir is None and prof.get("ca_dir"):
        ca_dir = prof["ca_dir"]
    ca_crt = ca_key = None
    if ca_dir:
        ca_dir = pathlib.Path(ca_dir).expanduser()
        ca_crt, ca_key = ca_dir / "ca.crt", ca_dir / "ca.key"
        for f in (ca_crt, ca_key):
            if not f.is_file():
                raise SystemExit(f"CA 파일이 없습니다: {f} (--ca-dir 에는 ca.crt 와 ca.key 가 있어야 합니다)")
    dns, ips = _default_sans()
    dns |= saved_dns | set(extra_dns)
    ips |= saved_ips | set(extra_ips)
    san = ",".join([f"DNS:{d}" for d in sorted(dns)] + [f"IP:{i}" for i in sorted(ips)])
    crt, key = _p(root, CERT_FILE), _p(root, KEY_FILE)
    crt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    for f in (crt, key):
        if f.exists():
            f.replace(f.with_name(f"{f.name}.{stamp}.bak"))
    tmpkey = key.with_name(key.name + ".new")
    if ca_dir:
        _issue_with_ca(crt, tmpkey, san, days, ca_crt, ca_key)
        shutil.copyfile(ca_crt, _p(root, CA_FILE))
        os.chmod(_p(root, CA_FILE), 0o644)
        how = f"CA 서명 ({ca_dir})"
        tail = "브라우저에 이 CA 가 이미 신뢰돼 있으면 더 설치할 것이 없습니다."
    else:
        r = subprocess.run([_openssl(), "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                            "-nodes", "-keyout", str(tmpkey), "-out", str(crt), "-days", str(int(days)),
                            "-subj", "/CN=aimem-fleet", "-addext", f"subjectAltName={san}",
                            "-addext", "extendedKeyUsage=serverAuth"], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("openssl 실패: " + r.stderr.strip()[-300:])
        how = "자체 서명"
        tail = "브라우저(Windows)에 이 인증서를 '신뢰할 수 있는 루트 인증 기관' 으로 설치하면 경고가 사라집니다."
    os.chmod(tmpkey, 0o600)
    os.replace(tmpkey, key)
    os.chmod(crt, 0o644)
    _save_profile(root, ca_dir, saved_dns | set(extra_dns), saved_ips | set(extra_ips))
    server.audit(root, "cert-renew", "cli", None, f"{how} {san}")
    print(f"새 인증서: {crt}  [{how}]\n  SAN: {san}\n  {days}일. 서버를 다시 띄우십시오(`monitorctl.sh restart`). {tail}")
    return 0


def _issue_with_ca(crt, key, san, days, ca_crt, ca_key):
    """키 생성 -> CSR -> CA 서명. 임시 파일은 인증서 디렉터리 안에 두고 끝나면 지웁니다."""
    o = _openssl()
    csr, ext = crt.with_name("server.csr.tmp"), crt.with_name("server.ext.tmp")
    try:
        for cmd in ([o, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(key)],
                    [o, "req", "-new", "-key", str(key), "-subj", "/CN=aimem-fleet", "-out", str(csr)]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit("openssl 실패: " + r.stderr.strip()[-300:])
        ext.write_text("basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                       f"extendedKeyUsage=serverAuth\nsubjectAltName={san}\n", encoding="utf-8")
        r = subprocess.run([o, "x509", "-req", "-in", str(csr), "-CA", str(ca_crt), "-CAkey", str(ca_key),
                            "-CAcreateserial", "-CAserial", str(crt.with_name("ca.srl")), "-days", str(int(days)),
                            "-sha256", "-extfile", str(ext), "-out", str(crt)], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("openssl(CA 서명) 실패: " + r.stderr.strip()[-300:])
    finally:
        for f in (csr, ext):
            if f.exists():
                f.unlink()


# ---------------------------------------------------------------- status / audit
def status(root):
    rows = []
    tok = _p(root, TOKEN_FILE)
    rows.append(("접근 토큰", tok.exists() and server.load_access_token(root) is not None,
                 f"{tok} ({oct(tok.stat().st_mode & 0o777)})" if tok.exists() else "없음"))
    env = _p(root, server.MONITOR_ENV_FILE)
    env_ok = env.exists() and not (env.stat().st_mode & 0o077)
    keys = sorted(server._parse_env(env.read_text(encoding="utf-8")).keys()) if env_ok else []
    rows.append(("설정 파일 monitor.env", env_ok,
                 (f"키 {', '.join(keys) or '없음'}" if env_ok else
                  ("권한이 600 이 아님" if env.exists() else "없음 (선택 - KISTI 키는 ~/.openclaw/.env 에서도 읽음)"))))
    server.load_monitor_env(root)
    rows.append(("KISTI_API_KEY", bool(os.environ.get(server.KISTI_API_KEY_ENV)), "있음" if os.environ.get(server.KISTI_API_KEY_ENV) else "없음"))
    allowed = server.github_allowed_logins(root)
    gh_on = server.github_enabled() or server.github_device_enabled()
    rows.append(("GitHub 로그인", gh_on,
                 f"{'웹' if server.github_enabled() else '기기'} 흐름, 허용 {len(allowed)}명" if gh_on else "꺼짐 (선택)"))
    crt = _p(root, CERT_FILE)
    if crt.exists():
        r = subprocess.run([_openssl(), "x509", "-in", str(crt), "-noout", "-enddate"], capture_output=True, text=True)
        end = r.stdout.strip().split("=", 1)[-1]
        try:
            left = (datetime.datetime.strptime(end, "%b %d %H:%M:%S %Y %Z") - datetime.datetime.utcnow()).days
        except ValueError:
            left = None
        rows.append(("TLS 인증서", left is not None and left > 30, f"만료 {end} (남은 {left}일)"))
    else:
        rows.append(("TLS 인증서", False, "없음"))
    key = _p(root, KEY_FILE)
    rows.append(("TLS 개인키 권한", key.exists() and not (key.stat().st_mode & 0o077),
                 oct(key.stat().st_mode & 0o777) if key.exists() else "없음"))
    optional = ("GitHub 로그인", "설정 파일 monitor.env")
    for name, ok, detail in rows:
        mark = "✓" if ok else ("-" if name in optional else "✗")
        print(f"  {mark} {name:<22} {detail}")
    return 0 if all(ok for name, ok, _ in rows if name not in optional) else 1


def audit_tail(root, n=30):
    p = _p(root, server.AUDIT_LOG)
    if not p.exists():
        print("감사 로그가 아직 없습니다")
        return 0
    for line in p.read_text(encoding="utf-8").splitlines()[-n:]:
        print(line)
    return 0


def main(argv, root):
    p = argparse.ArgumentParser(prog="aimem_monitor admin", description="모니터 접근 제어 관리")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    t = sub.add_parser("token")
    t.add_argument("action", choices=["show", "rotate"])
    g = sub.add_parser("github")
    g.add_argument("action", choices=["list", "allow", "deny"])
    g.add_argument("login", nargs="?")
    c = sub.add_parser("cert")
    c.add_argument("action", choices=["info", "renew"])
    c.add_argument("--ip", action="append", default=[])
    c.add_argument("--dns", action="append", default=[])
    c.add_argument("--days", type=int, default=825)
    c.add_argument("--ca-dir", help="ca.crt·ca.key 가 있는 사설 CA 디렉터리 (한 번 주면 다음부터 기억)")
    c.add_argument("--self-signed", action="store_true", help="CA 를 쓰지 않고 자체 서명으로")
    a_ = sub.add_parser("audit")
    a_.add_argument("-n", type=int, default=30)
    a = p.parse_args(argv)
    if a.cmd == "status":
        return status(root)
    if a.cmd == "token":
        return token_show(root) if a.action == "show" else token_rotate(root)
    if a.cmd == "github":
        if a.action == "list":
            return github_list(root)
        if not a.login:
            p.error("계정 이름이 필요합니다")
        return github_allow(root, a.login) if a.action == "allow" else github_deny(root, a.login)
    if a.cmd == "cert":
        return cert_info(root) if a.action == "info" else cert_renew(root, a.ip, a.dns, a.days, a.ca_dir, a.self_signed)
    if a.cmd == "audit":
        return audit_tail(root, a.n)
    return 2
