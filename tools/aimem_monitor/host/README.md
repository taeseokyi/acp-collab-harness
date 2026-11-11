# 윈도우 쪽 통과 프록시 (호스트에 두는 파일)

`aimem_proxy.py` 는 **윈도우**에서 돕니다: `C:\\Temp\\aimem-proxy\\aimem_proxy.py`, 작업 스케줄러 `\\tsyi\\AIMEM fleet proxy`
(`0.0.0.0:18800` → `127.0.0.1:18799`). 저장소의 이 사본이 정본이고, 바꿨으면 사람이 호스트에 옮깁니다 - 함대도
클로드 코드도 호스트 파일은 고치지 않습니다(권한 밖).

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
