# 관리자 세션 6라운드 브리프 (태석님 지시, 클로드 코드가 전달 · 2026-11-10 09:20)

당신은 `/home/tsyi/work/opencode` AIMEM 함대의 **관리자**(Claude Opus ACP 세션, `8.0`)입니다. 새 세션이라 기억이 없습니다. 정본은 AIMEM.md(규약, REV 114)와 **`.aimem/aimem.db`(운영 상태, R5 부터 쓰기 정본)**. 위임은 `~/.claude/CLAUDE.md`.

## 0. 턴 규칙
기다릴 때는 `fleet.py wait` / `fleet_graph.py run` 을 **포그라운드로 블로킹**. 백그라운드 감시 + "알림 오면 잇겠다" 로 턴을 끝내지 않는다. 보고를 본문에 다 쓰기 전에는 턴이 끝나지 않는다. `pkill -f` 에 자기 명령줄이 걸리지 않게 pid 로 죽인다(R5 관리자가 자기 셸을 죽인 사례).

## 1. 먼저 읽을 것
`python3 tools/fleet.py status`, `python3 tools/fleet.py children`, `python3 tools/aimem_db.py state | head -80`, `python3 tools/aimem_db.py queue list`, `python3 tools/aimem_db.py request list`, `python3 tools/aimem_db.py ownership list`, AIMEM.md 서문·`4절`(REV 114 의 R5 기록)·`8.0`·`8.0-5`, `AIMEM-state.md`, `python3 tools/fleet.py runs --last 15`.

## 2. 환경 변화
- **S2(codex, kistillm) 복귀.** KISTI 서버가 2026-11-10 아침에 정상화됐고(health ok, chat 1.1초) S2 스모크 통과(28초). **테스트 경로 소유권은 S4 → S2 로 환원**(DB ownership 반영, 큐 16번은 지우십시오). 이제 네 슬롯 전부 가용: S1 opus / S2 codex·kistillm / S3 opencode·EXAONE / S4 sonnet.
- **동시성:** EXAONE(S3)은 초당 1·분당 60 제한이라 S3 는 한 번에 1개. kistillm(S2)은 동시 처리가 되지만 큰 프롬프트에 느릴 수 있으니 이번 라운드에 `runs` 경과로 측정해 `4절` 에 적으십시오. 그래프 `concurrency` 는 4.
- 오픈클로 에이전트(클로 등)는 EXAONE 입니다. 관리자 세션은 Opus 그대로.

## 3. R5 가 남긴 교훈 → 이번 라운드 규칙
- **6절 소유권은 관리자 자신에게도 적용됩니다.** 작업자가 쓰는 중인 파일(예: `tools/aimem_monitor/__init__.py`)을 관리자가 동시에 고치지 마십시오. R5 에서 그 때문에 S1 검증이 깨졌습니다. 관리자 직접분은 작업자 쓰기 범위와 겹치지 않는 파일로 한정하거나, 작업자가 끝난 뒤에 하십시오.
- **그래프 노드의 `verify` 는 그 노드 산출물 범위로 좁히십시오**(예: `python3 -m unittest tests.test_x -q`). 전체 스위트를 verify 로 두면 빨간 테스트 1건이 멀쩡한 노드들을 연쇄 `failed` 로 만듭니다(R5 T-071·T-073). 전체 스위트는 라운드 끝 관리자 검증에서만.
- 이 두 규칙을 `8.0` 에 한 줄씩 적으십시오(REV 증가 때).

## 4. 과제 (R5 보고의 다음 라운드 계획 = 큐 순서)
1. **큐 15·23번 + 9절 2번**: `tests/test_fleet*.py` 소유권을 S2 에 등재하고(태석님 승인: 이 브리프가 승인) `fleet.py` DB 경로(roster/owned_paths/read_rev 의 DB 우선·폴백) 회귀 테스트를 S2 에. 함대 생명선인데 테스트가 없습니다.
2. **상세 패널 마무리**(큐 18~22): 보드 행·요청 서브태스크 클릭 진입점(S1 검수 T-054 의 7건). 데이터 계약(`board[]` 에 run id 를 실을지)을 관리자가 먼저 정하고 S3(EXAONE, 1개씩)에.
3. **큐 13번** `requests[].detail` 절단 + **큐 3번** 토큰 파일 `O_NOFOLLOW`(관리자 또는 S1).
4. **큐 7~9번 `fleet_graph.py`**: 단일 실행자 flock 잠금, 노드 타임아웃, 보고 첫 줄 `BLOCKED/NEEDS-*` 파싱(rc 0 이어도 done 금지). S4 검수가 두 라운드째 지적한 항목입니다. S1 에 주고 S4 가 검수.
5. 웹 요청 NEW/IN-PROGRESS 분담 포함. 매 라운드와 같이 REV 증가(`aimem_db.py event --bump` + 서문 동기), 린터·테스트 통과, **커밋·푸시 금지**, 대기 시간 `4절` 한 줄, 끝에 `aimem_db.py migrate && render`.

## 5. 보고 형식
첫 줄 `상태: DONE|PARTIAL|BLOCKED`, (1) 태스크 표(태스크·슬롯·모델·상태·경과·시도), (2) 재현한 검증과 출력, (3) 대기 시간(슬롯별, kistillm 측정 포함), (4) 큐 진행도, (5) 다음 라운드 계획.
