## 운영 방식: 무료 중심 (R37)

이 라운드는 **비용을 아끼는 쪽**입니다. 늦어도 괜찮습니다.

- **만들기·고치기는 무료 슬롯**에만 줍니다(새 코드·결함 수정·테스트·문서). 검수가 찾은 결함도 무료 슬롯이 고칩니다.
- **유료 슬롯은 판단과 적대적 검수에만** 씁니다. "빨라서" 는 이유가 아닙니다.
- **무료 슬롯이 막혀도 유료로 옮기지 않습니다.** 공급자 장애면 그 노드는 엔진이 `막힘(공급자 장애)` 로 두니, 보고에 적고 넘어갑니다.
- 검수는 그래프 끝에 한 번, 수정이 있으면 재검수 한 번.

### 지금 슬롯 (엔진이 적음)
- S1 · claude · opus · 유료 · 공급자 anthropic(동시 3) · R36 적대적 검수(마지막)
- S2 · codex · kisti/kistillm · 무료 · 공급자 kisti(동시 1) · R36 대기 (막힌 노드 받기)
- S3 · opencode · opencode/deepseek-v4.1-flash-free · 무료 · 공급자 opencode(동시 1) · R36 빠른 구현: VoxLog INTERFACE.md (무료)
- S4 · claude · sonnet · 유료 · 공급자 anthropic(동시 3) · R36 빠른 구현: VoxLog serve.py 진척 마감·mkdir 오류
- S5 · claude · sonnet · 유료 · 공급자 anthropic(동시 3) · R36 빠른 구현: VoxLog 408 재시도·브라우저 24번 · 관리자 추가
- S6 · freebuff · freebuff/pane · 무료 · 공급자 freebuff(동시 1) · tmux 팬의 freebuff (무료) - 사람이 모니터에서 지시문을 읽고 '보내기' 를 눌러야 시작. 문서·초벌 검토처럼 막히지 않는 일만 · **사람이 '보내기' 를 눌러야 시작 - 막히지 않는 일만**

### 슬롯을 더하고 역할을 정하는 것은 관리자의 판단입니다
- 역할: `python3 tools/aimem_db.py slot set --slot S<n> --role "<이번 라운드의 역할>"` (어느 슬롯이든).
- 더하기: 일이 슬롯보다 넓으면 지금 **1개**까지 더할 수 있습니다(무료 공급자). `python3 tools/aimem_db.py slot add --harness <하네스> --model <공급자/모델> --role "<역할>"` → 새 슬롯에 `ownership set` → 그래프에 배정. 엔진이 상한·모델·공급자 자리를 확인하고, 안 되면 까닭을 말합니다. 더한 슬롯은 다음 라운드에도 남으니 필요 없으면 `slot remove` 합니다. 보고 (6)에 더한 슬롯과 까닭을 적습니다.
