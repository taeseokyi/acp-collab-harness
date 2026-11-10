# 관리자 세션 4라운드 브리프 (태석님 지시, 클로드 코드가 전달 · 2026-11-09)

당신은 `/home/tsyi/work/opencode` AIMEM 함대의 **관리자**(Claude Opus ACP 세션, `8.0`)입니다. 새 세션이라 기억이 없습니다. 정본은 AIMEM.md(규약) 와 **`.aimem/aimem.db`(운영 상태, 이번 라운드부터)** 입니다. 위임은 `~/.claude/CLAUDE.md`.

## 0. 턴 규칙 (R2 사고의 재발 방지)
기다릴 때는 `python3 tools/fleet.py wait …` / `python3 tools/fleet_graph.py run <id>` 를 **포그라운드로 블로킹**합니다. 백그라운드 감시 + "알림 오면 잇겠다" 로 턴을 끝내지 마십시오. 보고를 이 응답 본문에 다 쓰기 전에는 턴이 끝나지 않습니다.

## 1. 먼저 읽을 것
`python3 tools/fleet.py status`, `python3 tools/aimem_db.py state | head -80`, AIMEM.md 서문·`1절`·`8.0`·`8.0-5`, `AIMEM-state.md`(DB 스냅샷), `python3 tools/aimem_db.py task list`, `request list`(status NEW 가 이번 라운드 분담 대상), `python3 tools/fleet.py runs --last 15`, `python3 tools/fleet_graph.py list`.

## 2. 이번 라운드부터 바뀐 것 (태석님 결정 18:25, 클로드 코드가 정지 중 적용)
- **운영 상태의 정본이 SQLite 로 옮겨 가는 중입니다.** `.aimem/aimem.db` 에 slots / ownership / requests / tasks / queue / graphs / nodes / runs / events 가 있고, `python3 tools/aimem_db.py render` 가 `AIMEM-state.md` 스냅샷을 만듭니다. `fleet.py spawn/wait/reap/slot` 은 파일과 DB 에 **이중 기록**합니다.
- **전환 1단계(지금):** 마크다운(AIMEM.md 2·3·4·4.5·6절) → DB 방향 동기화(`aimem_db.py migrate`). 아직 AIMEM.md 가 쓰기 정본이므로 보드·로그는 지금처럼 AIMEM.md 에 쓰되, **라운드 끝에 `python3 tools/aimem_db.py migrate && python3 tools/aimem_db.py render`** 를 돌려 DB 와 스냅샷을 맞추십시오.
- **전환 2단계(이번 라운드의 과제):** 방향을 뒤집어 DB 가 쓰기 정본이 되게 합니다. 태스크로 쪼개 배정하십시오:
  (a) `tools/aimem_lint.py`(S1): 2·3·4·4.5·6절 존재·형식 검사를 AIMEM.md 에서 떼고, "AIMEM.md 에 운영 상태 표가 **없어야** 한다 + AIMEM-state.md 는 render 산출물과 바이트 일치해야 한다 + 관리자 선언 접두사" 로 바꾼다. 테스트 픽스처도.
  (b) `tools/aimem_board.py`(S1): `board-set`/`archive-rollover` 를 `aimem_db.py task set` / events 로 위임하거나 폐기.
  (c) 웹 서버(관리자 또는 S4): `/api/state` 를 `aimem_db.state_dict()` 기반으로 바꾸고 `POST /api/requests` 가 파일 대신 `requests` 행을 쓴다(파일도 한 라운드 더 병행). reader.py 의 마크다운 파싱은 폐기 후보.
  (d) 계약 테스트(S2): DB 스키마·state 키·check 명령 케이스.
  (e) AIMEM.md 에서 2·3·4·4.5·6절 본문을 "→ AIMEM-state.md / aimem.db" 포인터 한 줄로 바꾸고 원문은 아카이브로(관리자). REV 는 `aimem_db.py event --bump` 가 올리고 서문 REV 는 render 가 맞춘다.
- **작업자 0.1 세 줄 검사**는 `python3 tools/aimem_db.py check --slot S2 --token <t> --rev <N>` 한 줄로도 됩니다. spawn 머리말에 이 명령을 넣는 것은 fleet.py(클로드 코드) 가 2단계 뒤에 합니다.

## 3. 식별자 체계 (`8.0-5`, REV 112) - 전부 반영됨 (클로드 코드, 정지 중 19:01)
요청 `Q-<YYMMDD>-<4자>` / 태스크 `T-0xx` / 그래프 `G-00x` / 실행 `<T>-<S#>-a<n>-<HHMMSS>` / 라운드 `R<n>`(기록 전용). `fleet.py spawn --task-id --attempt`, `fleet_graph.py`(노드 id = 태스크 id, Namespace 에 task_id/attempt, G-/T- 경고), `server.py`(요청 id `Q-`, **서버 재시작 뒤 적용**) 모두 반영. AIMEM `8.0-5` 신설, 4절 롤오버 완료. 새 그래프는 `G-003` 부터, 노드 id 는 보드 `T-0xx`. 옛 id 는 이력. 131 테스트 OK.

## 4. 이어받을 상태와 열린 요청
`python3 tools/aimem_db.py request list` 의 NEW / IN-PROGRESS 를 전부 분담하십시오. 특히 **S4 모델 표시(b125)**: reader.py 가 `tools/fleet_slots.json` 을 읽어 슬롯별 모델을 채우고 서버 재시작 → `/api/state` 에 S1 opus / S4 sonnet. **lost 표시(c87c)**, **상세 패널(8d8d, S3 3차 시도 중이었음)**, **Strata 재스킨 검수 결과 반영**. 슬롯은 S1 opus(판단형) / S4 sonnet(속도) / S2·S3 kistillm(비용). kistillm 동시성은 측정으로 정하되 그래프 `concurrency` 는 4.

## 4.5 새 요청 - 외부 공개 (태석님 19:05, 요청 파일 `…-407b-ui-https-github.json`, 이번 라운드 최우선 중 하나)
함대 웹 UI 를 외부에서 접속하도록 공개한다. HTTPS 자체 인증서(크롬에 설치)+접근 제어. 상세는 요청 파일 `detail` 에 있다(ssl.SSLContext 로 ThreadingHTTPServer 감싸기, `openssl req -x509` 로 `.aimem/tls/server.{crt,key}` SAN 포함, `--tls` 플래그, 토큰 로그인 → HttpOnly/Secure/SameSite 쿠키(hmac 서명), 모든 `/api/*`·정적 자원 401 보호, 실패 지연, 선택적 GitHub OAuth(환경변수 있을 때만, 허용 로그인 목록 대조), HSTS, 본문 64KB, WSL2 portproxy 는 README 에만). 분담 제안: 서버 인증·TLS(S1 opus), 로그인 화면(S3), 테스트(S2), **적대적 보안 검수(S4: 키·토큰 유출, 우회, 탈출)**. 완료 판정은 요청 파일의 검증 항목. 외부 공개 전엔 기존 http 동작을 깨지 말 것(`--tls` 없으면 지금처럼).

## 5. 보고 형식
첫 줄 `상태: DONE|PARTIAL|BLOCKED`, (1) 태스크 분할표(태스크·슬롯·하네스·상태·경과·시도), (2) 재현한 검증 명령과 출력(린터·테스트·`/api/state`·`aimem_db.py state`), (3) 대기 시간 수치, (4) 2단계 전환 진행도와 남은 것, (5) 다음 라운드 계획. 커밋·푸시 금지.
