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

## 함대 모니터를 외부에 공개하기 (HTTPS + 접근 제어)

기본은 **로컬 전용**입니다 - `PYTHONPATH=tools python3 -m aimem_monitor` 는 `127.0.0.1:18799`
에 인증 없이 뜹니다. 외부 공개는 `--tls` 로만 합니다.

### 1. 자체 인증서 만들기 (WSL 쪽, 한 번)

```bash
mkdir -p .aimem/tls && chmod 700 .aimem/tls
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -days 825 -nodes \
  -keyout .aimem/tls/server.key -out .aimem/tls/server.crt -subj /CN=aimem-fleet \
  -addext "subjectAltName=DNS:aimem-fleet,DNS:localhost,IP:127.0.0.1,IP:$(hostname -I | awk '{print $1}')" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" -addext "extendedKeyUsage=serverAuth"
chmod 600 .aimem/tls/server.key
```

**`.aimem/tls/` 는 `.gitignore` 대상입니다.** 개인키와 접근 토큰이 들어 있으니 커밋하지 마십시오.
WSL IP 는 재부팅마다 바뀝니다 - 바뀌면 인증서를 다시 만들어야 SAN 이 맞습니다.

### 2. 크롬에 인증서 설치 (윈도우 쪽)

1. `\\wsl$\<배포판>\home\<사용자>\work\opencode\.aimem\tls\server.crt` 를 윈도우로 복사
2. 더블클릭 → **인증서 설치** → **로컬 컴퓨터** → **모든 인증서를 다음 저장소에 저장** →
   **신뢰할 수 있는 루트 인증 기관**
3. 크롬을 완전히 닫았다 다시 엽니다. `https://aimem-fleet:18799/` 또는 `https://<WSL IP>:18799/`

설치하지 않으면 크롬이 `NET::ERR_CERT_AUTHORITY_INVALID` 를 띄웁니다(`curl -k` 는 그래도 됩니다).

### 3. 띄우기

```bash
PYTHONPATH=tools python3 -m aimem_monitor --tls --host 0.0.0.0
```

- `--tls` 는 **인증을 함께 켭니다.** `.aimem/tls/access-token` 이 없으면 32바이트 hex 를
  0600 으로 만들고 **그때 한 번만** stderr 에 찍습니다
- 브라우저는 `/login` 에서 토큰을 넣습니다 → `HttpOnly; Secure; SameSite=Strict` 세션 쿠키(12시간)
- 도구는 `Authorization: Bearer <토큰>` 으로도 됩니다
- `/login`·`/api/login`·`/api/logout`·`/api/authinfo`·`/auth/github/*`·`/favicon.ico` 를 뺀
  **모든 경로**가 401 입니다
- 토큰을 회수하려면 **토큰 파일을 새 값으로 갈아 끼우고 서버를 다시 띄우십시오** -
  발급된 세션 쿠키가 전부 무효가 됩니다(쿠키 서명 키가 그 토큰입니다)

### 4. 윈도우에서 들어오게 하기 (WSL2, 태석님이 직접 실행)

WSL2 는 NAT 뒤에 있어 윈도우 쪽 포워딩이 필요합니다. **관리자 권한 PowerShell**에서:

```powershell
netsh interface portproxy add v4tov4 listenport=18799 listenaddress=0.0.0.0 `
    connectport=18799 connectaddress=<WSL IP>
New-NetFirewallRule -DisplayName "AIMEM fleet monitor" -Direction Inbound `
    -LocalPort 18799 -Protocol TCP -Action Allow
```

되돌리기: `netsh interface portproxy delete v4tov4 listenport=18799 listenaddress=0.0.0.0`.
**이 두 명령은 저장소 밖(호스트 설정)이라 작업자도 관리자도 실행하지 않습니다.**

### 5. GitHub 로그인 (선택)

`GITHUB_CLIENT_ID` 와 `GITHUB_CLIENT_SECRET` 이 **둘 다** 있을 때만 켜집니다.
OAuth 앱의 콜백 URL 은 `https://<호스트>:18799/auth/github/callback`,
허용 계정은 `.aimem/tls/allowed-github-logins` 에 한 줄 하나씩 적습니다
(**파일이 없으면 전원 거부**입니다).

## 알려진 한계

`7절` 에 적어 두었습니다. 요약하면 - 소유권 표와 하드리밋은 **자발적 준수**입니다.
파일 권한으로 강제되지 않습니다. 이 구조는 정직한 작업자의 실수를 막는 장치이지,
악의를 막는 장치가 아닙니다.
