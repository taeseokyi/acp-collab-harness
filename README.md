# ACP 협업 하네스

여러 AI 코딩 에이전트(ACP 슬롯)가 **같은 폴더에서 동시에 일할 때** 서로의 작업을
덮어쓰지 않게 하는 규약과 도구 모음입니다. 프로젝트마다 이 저장소를 복제해
`AIMEM.md` 의 목표·보드만 바꿔 쓰는 것을 전제로 만들었습니다.

## 문제

에이전트를 여러 개 띄우면 셋 다 같은 파일을 고칩니다. 서로의 변경을 모르고,
누가 무엇을 했는지 남지 않고, 한 세션이 죽으면 맥락이 사라집니다.
사람이 매번 중재하면 파이프라인이 사람 응답 속도로 떨어집니다.

## 해결 구조

- **`AIMEM.md`** - 공유 작업 메모리 하나. 규약(0절), 세션 명부(2절), 작업 보드(3절),
  핸드오프 로그(4절), 파일 소유권 표(6절)가 여기 다 있습니다. 쓰기는 관리자만
- **파일 소유권 표** - 경로 패턴마다 쓰기 소유 슬롯을 하나로 못박습니다.
  동시 쓰기 충돌을 구조적으로 없앱니다
- **REV + 확인토큰** - 작업자는 착수 전에 지시의 REV·토큰을 `AIMEM.md` 실측으로
  대조합니다. 어긋나면 멈춥니다. 재생된 옛 메시지를 걸러내는 장치입니다
- **핸드오프 / 핸드온** - 일을 넘기는 슬롯은 아웃박스에
  `다음 담당자가 알아야 할 것` 을 채웁니다. 이어받는 슬롯은 그것만 읽고 시작합니다
- **하드리밋** - 커밋/푸시, 삭제, 의존성 설치, `AIMEM.md` 쓰기, 소유 경로 밖 쓰기는
  관리자도 전달할 수 없습니다. 사람의 직접 허용만 엽니다

## 도구

| 파일 | 역할 |
| ---- | ---- |
| `tools/aimem_lint.py` | `AIMEM.md` 구조 불변식 검사기. 표준 라이브러리만 |
| `tools/aimem_board.py` | 보드·명부·큐·소유권 표 갱신 CLI. 락 + lint 롤백 안전망 |
| `tools/fleet.py` | 슬롯 브리핑·상태·거두기 도우미 (관리자 전용) |
| `tools/envcheck/` | 실행 환경 계층 점검 러너. 누적 판정은 `.aimem/envcheck-state.json` |
| `.githooks/pre-commit` | 커밋 전 린터 + 단위 테스트 자동 실행 |

내린 도구는 `.aimem/archive/retired-tools/` 에 있습니다.
`aimem_pipeline.py` (무인 배정 드라이버) 는 REV 105 에서 내렸습니다 - 게이트 판정이
사문화된 `0.6-3` 에 걸려 있었습니다.

```bash
python3 tools/aimem_lint.py AIMEM.md     # 통과 시 exit 0
python3 -m unittest discover -s tests    # 98건
PYTHONPATH=tools python3 -m envcheck     # 환경 점검
git config core.hooksPath .githooks      # 훅 활성화
```

의존성이 없습니다. 파이썬 표준 라이브러리만 씁니다.

## 쓰는 법

1. 이 저장소를 프로젝트 폴더로 복제합니다
2. `AIMEM.md` 의 `1. 현재 목표`, `3. 작업 보드`, `6. 파일 소유권` 을 프로젝트에 맞게 다시 씁니다
3. 위임을 사용자 지침 파일(`~/.claude/CLAUDE.md` 등 에이전트가 쓸 수 없는 위치)에 한 번 적습니다
4. 슬롯을 열고, 관리자가 브리프(슬롯 ID·REV·토큰·소유 경로·검증 방법)를 보냅니다

## 함대 모니터 (HTTPS + 접근 제어)

**평소에도 HTTPS 로 띄웁니다** (2026-11-10 전환). 같은 포트로 들어온 `http://` 는 https 로 301 됩니다.

```bash
tools/aimem_monitor/monitorctl.sh start          # https://<주소>:18799/  (--tls --host 0.0.0.0, 인증 켬)
tools/aimem_monitor/monitorctl.sh restart | stop | status
tools/aimem_monitor/monitorctl.sh start local    # 개발 확인용 http 127.0.0.1, 인증 없음 - 공개 경로에 두지 말 것
```

pid 는 `.aimem/monitor.pid`, 로그는 `.aimem/monitor.log`. 내릴 때는 pid 로만 죽입니다(`pkill -f` 금지).

### 접근 제어

- `/login` 에서 **접근 토큰**을 넣으면 `HttpOnly; Secure; SameSite=Strict` 세션 쿠키(12시간). 도구는
  `Authorization: Bearer <토큰>`. `/login`·`/api/login`·`/api/logout`·`/api/authinfo`·`/auth/github/*`·
  `/favicon.ico` 를 뺀 **모든 경로**가 401 입니다. 화면 오른쪽 위에 로그인한 주체와 **로그아웃**이 있습니다
- 관리 명령 (`PYTHONPATH=tools python3 -m aimem_monitor admin ...`):

| 명령 | 하는 일 |
| ---- | ------- |
| `status` | 토큰·설정 파일·KISTI 키·GitHub·인증서 만료·개인키 권한 점검 (비밀값은 찍지 않음) |
| `token show` | 로그인할 토큰 보기 |
| `token rotate` | 새 토큰. **발급된 세션이 전부 무효**(쿠키 서명 키가 토큰) - 기기 분실 시. 뒤에 `restart` |
| `github list` / `allow <계정>` / `deny <계정>` | GitHub 로그인 허용 목록 (`.aimem/tls/allowed-github-logins`, 없으면 전원 거부) |
| `cert info` / `cert renew [--ca-dir DIR] [--ip IP] [--dns 이름] [--self-signed]` | 서버 인증서 보기·재발급 (EC P-256, 825일, 옛 것은 `.bak`). `--ca-dir` 의 `ca.crt`·`ca.key` 로 서명하고 그 조건을 `.aimem/tls/cert-profile.json` 에 기억해 다음부터는 인자 없이 `cert renew` 만 치면 됨(SAN 누적). `--self-signed` 는 예전 방식 |
| `audit [-n 30]` | 감사 로그 `.aimem/access.log` - 로그인 성공·실패, 로그아웃, 요청 생성·수정, 함대 제어, 토큰 교체 |

- **비밀은 셸이 아니라 파일에서 읽습니다** - `.aimem/tls/monitor.env`(0600; `KISTI_API_KEY`,
  `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`). KISTI 키가 없으면 `~/.openclaw/.env` 에서 읽습니다.
  그룹·기타가 읽을 수 있는 파일은 읽지 않습니다. **`.aimem/tls/` 는 git 제외**입니다
- HSTS 는 **도메인 이름으로 들어온 요청에만** 보냅니다. `localhost`·IP 로 들어오면 보내지 않습니다 -
  HSTS 는 포트가 아니라 호스트 전체에 걸려, 같은 PC 의 다른 `http://localhost:*` 서비스를 깨뜨릴 수 있습니다

### 인증서 - PC 의 다른 서비스와 같은 사설 CA 를 씁니다 (2026-11-10)

서버 인증서는 태석님 PC 의 사설 CA(`C:\Temp\carefor-app\server\certs\ca.{crt,key}`, carefor-app·
Signposts_of_Faith 와 공용)로 서명합니다. 그 CA 가 윈도우 신뢰 루트에 **이미 들어 있으므로 브라우저에
따로 설치할 것이 없습니다.** CA 공개 인증서 사본은 `.aimem/tls/ca.crt`(검증용 `curl --cacert`), CA 개인키는
저장소 밖에 그대로 둡니다.

```bash
# 처음 한 번 (이후엔 `cert renew` 만 - 조건은 .aimem/tls/cert-profile.json 에 기억됨)
PYTHONPATH=tools python3 -m aimem_monitor admin cert renew \
    --ca-dir /mnt/c/Temp/carefor-app/server/certs --dns DESKTOP-4QI608A --ip 192.168.0.5 --ip 192.168.200.102
tools/aimem_monitor/monitorctl.sh restart
curl -s --cacert .aimem/tls/ca.crt https://192.168.0.5:18800/api/health   # 401 이면 체인·주소 모두 정상
```

새 주소(공인 IP·도메인)로도 들어올 거면 `--ip`/`--dns` 를 더해 `renew` 후 `restart`. WSL IP 는
자동으로 들어가지만 아래 프록시 경로에서는 필요 없습니다. CA 없이 쓰려면 `--self-signed` - 그때는
`server.crt` 를 윈도우 **신뢰할 수 있는 루트 인증 기관**에 설치해야 경고가 사라집니다.

### 외부에서 들어오게 하기 - 윈도우 쪽 TCP 프록시 (WSL2, 2026-11-10)

`netsh portproxy` 는 WSL IP 를 직접 적어야 해서 재부팅마다 끊겼습니다(Windows 10 이라 `networkingMode=mirrored`
도 못 씁니다). 대신 **윈도우에서 도는 작은 통과 프록시**가 `0.0.0.0:18800` 을 듣고 **`127.0.0.1:18799`** 로
넘깁니다 - 윈도우의 localhost 는 WSL2 가 알아서 WSL 서버로 이어 주므로 WSL IP 가 바뀌어도 아무것도 고칠 게
없습니다. TLS 는 건드리지 않고 바이트만 통과시킵니다(인증서·인증은 WSL 서버 몫).

- 스크립트·로그: `C:\Temp\aimem-proxy\aimem_proxy.py`, `aimem_proxy.log` (표준 라이브러리만, 윈도우 Python 3.13)
- 작업 스케줄러 `\tsyi\AIMEM fleet proxy`: 로그온 시 `pythonw.exe` 로 시작, 시간제한 없음, 실패 시 1분 간격 재시작.
  등록 XML 은 `C:\Temp\aimem-proxy\task.xml` (`schtasks /create /tn "\tsyi\AIMEM fleet proxy" /xml ... /f`)
- 접속 주소: **`https://192.168.0.5:18800/`** (PC IP + 프록시 포트). 공유기는 외부 포트 → `192.168.0.5:18800`
- 다른 기기에서 들어오려면 방화벽 1줄 (관리자 PowerShell, 태석님이 직접):

```powershell
New-NetFirewallRule -DisplayName "AIMEM fleet proxy" -Direction Inbound -LocalPort 18800 -Protocol TCP -Action Allow
```

**저장소 밖(호스트·공유기 설정)이라 작업자도 관리자도 실행하지 않습니다.** 옛 `portproxy` 규칙은 없습니다
(2026-11-10 확인) - 있었다면 `netsh interface portproxy delete v4tov4 listenport=18799 listenaddress=0.0.0.0`.

### GitHub 로그인 (선택)

GitHub > Settings > Developer settings > OAuth Apps > New OAuth App - 콜백 URL
`https://<외부 주소>:18799/auth/github/callback`. 받은 두 값을 `.aimem/tls/monitor.env` 에 적고
`admin github allow <내 계정>` → `restart`. 로그인 화면에 **GitHub 로 로그인** 버튼이 생깁니다.

## 알려진 한계

`7절` 에 적어 두었습니다. 요약하면 - 소유권 표와 하드리밋은 **자발적 준수**입니다.
파일 권한으로 강제되지 않습니다. 이 구조는 정직한 작업자의 실수를 막는 장치이지,
악의를 막는 장치가 아닙니다.
