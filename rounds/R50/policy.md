## 운영 방식: 무료 중심 (R50)

이 라운드는 **비용을 아끼는 쪽**입니다. 늦어도 괜찮습니다.

- **만들기·고치기는 무료 슬롯**에만 줍니다(새 코드·결함 수정·테스트·문서). 검수가 찾은 결함도 무료 슬롯이 고칩니다.
- **유료 슬롯은 판단과 적대적 검수에만** 씁니다. "빨라서" 는 이유가 아닙니다.
- **무료 슬롯이 막혀도 유료로 옮기지 않습니다.** 공급자 장애면 그 노드는 엔진이 `막힘(공급자 장애)` 로 두니, 보고에 적고 넘어갑니다.

### 지금 슬롯 (엔진이 적음)
- S1 · claude · opus · 유료 · 공급자 anthropic(동시 3) · R49 쉼 (무료 중심)
- S2 · codex · kisti/kistillm · 무료 · 공급자 kisti(동시 1) · R49 VoxLog F2 만들기: tags.py·ask/stt 자동 태그·app.js
- S3 · opencode · kisti/kistillm · 무료 · 공급자 kisti(동시 1) · R49 VoxLog F2 만들기: store.py·serve.py PATCH/autotag
- S4 · claude · sonnet · 유료 · 공급자 anthropic(동시 3) · R49 VoxLog F2 적대적 검수(부작용 중심)
- S5 · claude · sonnet · 유료 · 공급자 anthropic(동시 3) · R49 쉼 (무료 중심) · 관리자 추가
- S6 · freebuff · freebuff/pane · 무료 · 공급자 freebuff(동시 1) · R49 VoxLog F2 만들기: index.html·style.css·브라우저 검사·문서

### 슬롯을 더하고 역할을 정하는 것은 관리자의 판단입니다
- 역할: `python3 tools/aimem_db.py slot set --slot S<n> --role "<이번 라운드의 역할>"` (어느 슬롯이든).
- 더하기: 일이 슬롯보다 넓으면 지금 **1개**까지 더할 수 있습니다(무료 공급자). `python3 tools/aimem_db.py slot add --harness <하네스> --model <공급자/모델> --role "<역할>"` → 새 슬롯에 `ownership set` → 그래프에 배정. 엔진이 상한·모델·공급자 자리를 확인하고, 안 되면 까닭을 말합니다. 더한 슬롯은 다음 라운드에도 남으니 필요 없으면 `slot remove` 합니다. 보고 (6)에 더한 슬롯과 까닭을 적습니다.

## 관리 방식
프로젝트마다 사람이 찍어 둔 취향입니다(안 찍은 프로젝트는 균형). 검수와 검사를 얼마나 할지는 이 절이 정하고, 운영 방식은 슬롯을 어떻게 나눌지만 정합니다. 라운드 도중 들어온 요청은 그 프로젝트의 방식을, 여기 없으면 균형을 따릅니다.

### VoxLog · 속도 우선
- 검수·재검수 노드를 두지 않는다
- 검사는 새로 쓰지 않는다. verify 는 "뜬다" 와 있던 검사 통과
- 지적·남은 일은 큐에 올리지 않고 PROGRESS.md 메모로 남긴다
- 새로 만드는 것은 자유. 있던 파일은 요청에 필요한 만큼만 고친다
