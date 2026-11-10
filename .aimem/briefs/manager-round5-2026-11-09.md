# 관리자 세션 5라운드 브리프 (태석님 지시, 클로드 코드가 전달 · 2026-11-09 20:55)

당신은 `/home/tsyi/work/opencode` AIMEM 함대의 **관리자**(Claude Opus ACP 세션, `8.0`)입니다. 새 세션이라 기억이 없습니다. 정본은 AIMEM.md(규약, REV 113)와 `.aimem/aimem.db`(운영 상태). 위임은 `~/.claude/CLAUDE.md`.

## 0. 턴 규칙
기다릴 때는 `python3 tools/fleet.py wait …` / `python3 tools/fleet_graph.py run <id>` 를 **포그라운드로 블로킹**합니다. 백그라운드 감시 + "알림 오면 잇겠다" 로 턴을 끝내지 마십시오. 보고를 본문에 다 쓰기 전에는 턴이 끝나지 않습니다.

## 1. 먼저 읽을 것
`python3 tools/fleet.py status`, `python3 tools/fleet.py children`, `python3 tools/aimem_db.py state | head -60`, `python3 tools/aimem_db.py request list`, AIMEM.md 서문·`4절` 최신(REV 113 의 R4 기록)·`4.5` 큐·`8.0`·`8.0-5`, `python3 tools/fleet.py runs --last 12`.

## 2. 이번 라운드의 환경 (중요)
- **S2(codex, kistillm) 는 이번 라운드에서 제외합니다.** KISTI 서버(`aida.kisti.re.kr:10430`, 플랫폼 8442)가 19:25 부터 연결 거부 상태입니다(태석님 확인 20:50). S2 몫(테스트)은 **S4(sonnet) 또는 S1(opus)** 에 주십시오. `--harness claude` 대체 스폰은 하지 마십시오 - 슬롯을 바꾸면 됩니다.
- **S3(opencode) 의 모델이 EXAONE(`exaone/k-exaone_v2.5`) 으로 바뀌었습니다**(opencode.jsonc 기본, 도구 호출 스모크 OK). EXAONE 은 **초당 1 요청·분당 60** 제한이라 opencode 작업자는 **동시에 1개**만 띄우고, 그래프 `concurrency` 는 3(S1·S3·S4 각 1). 429 가 나면 재시도 루프가 받습니다.
- 오픈클로 에이전트(구름·클로·옥티)도 EXAONE 으로 바뀌었습니다. codex 는 Responses API 가 없어 EXAONE 을 못 쓰므로 kistillm 유지(복구 후).
- 서버(18799)는 R4 코드로 떠 있을 수 있습니다. 코드를 바꾸면 재시작하십시오(`pkill -f "python3 -m aimem_monitor"` 후 `PYTHONPATH=tools nohup python3 -m aimem_monitor &`, 외부 공개 전엔 http 로컬).

## 3. 과제 (R4 보고의 다음 라운드 계획 그대로, 큐 순서)
A. **DB 2단계 마무리** - 한 그래프(`G-003`, 노드 id = 태스크 id)로: `reader.py` 가 `aimem_db.state_dict()` 를 읽어 `collect()` 를 채우기(S1) ∥ `fleet.py` 의 `roster()/owned_paths()/read_rev()` 를 DB 우선·마크다운 폴백으로(관리자 직접) → `aimem_board.py` 폐기 또는 `aimem_db.py task set` 위임(S1) → **AIMEM.md 2·3·4·4.5·6절 표 제거 + 아카이브 + 포인터**(관리자) → 린터 `STATE_TABLE_IN_AIMEM` 4건이 0 이 되는 것이 완료 판정. 테스트 보강은 S4.
B. **공개면 2차** - `/api/state` 에서 `slots[].token`·`root` 절대경로·`kisti.url` 제거, 요청 생성 분당 제한, 프런트·테스트 동반(S3 EXAONE 1개 + S4 테스트). S4 가 R4 에서 재현한 항목이 닫히는지 재검수.
C. **웹 요청** `request list` 의 NEW/IN-PROGRESS 를 분담에 포함(상세 패널 마무리 등). 요청 파일 상태·서브태스크 갱신.
D. 매 라운드와 같이: 검증 재현, REV 증가(`aimem_db.py event --bump` 와 서문 동기), 린터·테스트 통과, **커밋·푸시 금지**, 대기 시간 수치를 `4절` 에 한 줄. 끝난 뒤 `python3 tools/aimem_db.py migrate && python3 tools/aimem_db.py render`.

## 4. 보고 형식
첫 줄 `상태: DONE|PARTIAL|BLOCKED`, (1) 그래프/태스크 표(태스크·슬롯·모델·상태·경과·시도), (2) 재현한 검증 명령과 출력(린터 0건 여부 포함), (3) 대기 시간, (4) DB 2단계·공개면 2차 진행도와 남은 것, (5) 다음 라운드 계획. 막히면 BLOCKED 와 필요한 것.
