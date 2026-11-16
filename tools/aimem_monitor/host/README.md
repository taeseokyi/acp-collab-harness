# 윈도우 쪽 통과 프록시 (호스트에 두는 파일)

`aimem_proxy.py` 는 **윈도우**에서 돕니다: `C:\\Temp\\aimem-proxy\\aimem_proxy.py`, 작업 스케줄러 `\\tsyi\\AIMEM fleet proxy`
(`0.0.0.0:18800` → `127.0.0.1:18799`). 저장소의 이 사본이 정본이고, 바꿨으면 사람이 호스트에 옮깁니다 - 함대도
클로드 코드도 호스트 파일은 고치지 않습니다(권한 밖). 예외는 둘: 태석님이 그 대화에서 직접 시킨 교체, 그리고 배포가 쓰는
`ports.json`(모니터가 켜고 끌 때마다 고쳐 씁니다).

## 2026-11-16 판: 배포한 앱의 포트도 같이 중계

모니터 프로젝트 탭의 **배포**(`tools/aimem_monitor/deploy.py`)가 앱의 자체 서버를 WSL `127.0.0.1:<공개 포트 + 100>` 에
띄우고, 이 폴더의 `ports.json`(`{"ports": [18810, ...]}`)에 켜 둔 공개 포트를 적습니다. 프록시는 3초마다 그 파일을 읽어
포트를 열고 닫습니다 - **프로세스도 작업 스케줄러 항목(`\\tsyi\\AIMEM fleet proxy`)도 하나 그대로**이고, 인자도 그대로입니다.

- 공개 포트는 18810 부터 차례로 하나씩(18810~18899), 잇는 곳은 늘 `127.0.0.1:포트 + 100`. 파일에는 **어느 포트를 여느냐만**
  적히므로, 파일을 고칠 수 있어도 다른 포트를 열거나 다른 곳으로 잇게 할 수는 없습니다. 꺼 둔 포트는 듣지 않습니다.
- 배포 포트에는 PROXY 줄을 보내지 않습니다(앱 서버는 그 줄을 모릅니다) - 앱에는 접속자가 127.0.0.1 로 보입니다.
- 인증서는 모니터 것을 같이 씁니다(같은 PC 이름·주소, 포트만 다름). 토큰은 배포마다 따로이고 `.aimem/deploy/deploys.json`(0600)에 있습니다.
- **2026-11-16 15:07 에 호스트에 옮겨 재시작했습니다**(태석님 지시 "배포 기능 작업해", 원본은 `aimem_proxy.py.bak-20261116`).
  되돌리려면 그 `.bak` 을 다시 복사하고 작업을 재시작합니다.
- 다른 기기에서 닿으려면 윈도우 방화벽이 그 포트를 받아야 합니다(관리자 PowerShell, 한 번):
  `New-NetFirewallRule -DisplayName "AIMEM fleet apps" -Direction Inbound -Protocol TCP -LocalPort 18810-18899 -Action Allow`
  집 밖에서 쓰려면 공유기에서 같은 구간을 이 PC 로 넘깁니다. 토큰 없이 켠 배포는 그 주소에 닿는 누구나 쓰게 됩니다.

## 2026-11-11 판: 접속자 주소 넘기기

프록시가 연결마다 `PROXY TCP4 <접속자> 127.0.0.1 <포트> 18799` 한 줄을 먼저 보내고, 서버(`read_proxy_header`)가
loopback 에서 온 그 줄만 믿어 접속 기록·주소별 제한에 진짜 주소를 씁니다. **2026-11-11 18:06 에 호스트에 옮겨 재시작했습니다**(태석님 승인, 원본은 `aimem_proxy.py.bak-20261111`). 다음에 바꿀 때는 PowerShell 에서:

```powershell
Copy-Item C:\Temp\aimem-proxy\aimem_proxy.py C:\Temp\aimem-proxy\aimem_proxy.py.bak
Copy-Item \\wsl$\Ubuntu\home\tsyi\work\opencode\tools\aimem_monitor\host\aimem_proxy.py C:\Temp\aimem-proxy\aimem_proxy.py
schtasks /End /TN "\tsyi\AIMEM fleet proxy"; schtasks /Run /TN "\tsyi\AIMEM fleet proxy"
```

확인: 폰이나 다른 PC 에서 접속한 뒤 `.aimem/access.log` 의 주소 칸이 `127.0.0.1` 이 아니라 그 기기의 주소인지 봅니다.
되돌리려면 `.bak` 을 다시 복사하고 작업을 재시작합니다.
