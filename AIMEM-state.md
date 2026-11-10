# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)

- 정본은 `.aimem/aimem.db` 입니다. 이 파일을 손으로 고치지 마십시오. 생성 2026-11-10T17:08:05 / REV 130

## 2. 세션 명부

| 슬롯 | 확인토큰 | 하네스 | 모델 | 역할 | 비고 |
| --- | --- | --- | --- | --- | --- |
| S1 | `a41f0c` | claude | opus | 린터 / 보드 CLI / 판단형 | 11-09 CLI 작업자. `claude -p --model opus`(=opus-5.5, 태석님 17:45) |
| S2 | `d27e93` | codex | (하네스 기본) | 테스트 / 파이프라인 | 11-09 16시 CLI 작업자. `codex exec`, kistillm |
| S3 | `5b8c1e` | opencode | (하네스 기본) | 커밋 훅 / 검수 | 11-09 16시 CLI 작업자. `opencode run`, kistillm |
| S4 | `6cd650` | claude | sonnet | 병렬 작업자 (속도) | 11-09 17:30 태석님 배정. `claude -p --model sonnet`(=sonnet-5.5). 소유 경로는 태스크마다 6절에 등재 |

## 3. 작업 보드

| ID | 요청 | 태스크 | 담당 | 상태 | 산출물 |
| --- | --- | --- | --- | --- | --- |

## 4. 이벤트 로그 (최신 50)

- `2026-11-10 17:08` Claude Code [handoff] REV 130: **REV 130. AIMEM.md compressed to rules and pointers (765→475 lines); five tool/doc mismatches fixed.** (1) Compression: Section 0 to 60 lines, hard limits stated once in `0.2`, histories replaced by archive pointers, dated provenance dropped from headings, 8.0 84→41 lines; full REV 129 text kept at
- `2026-11-10T16:47:15` Claude Code [archive] REV 129: 핸드오프 로그 9건 → .aimem/archive/handoff-<YYYY-MM>.md (최신 4건 유지)
- `2026-11-10 16:47` Claude Code [handoff] REV 129: - `2026-11-10 16:47` Claude Code: **REV 129. Handoff log moved out of AIMEM.md (Taeseok: "manage the handoff log differently, keep the document light").** Entries now live in `.aimem/handoff.md`; Section 4 states only the method. New `aimem_db.py handoff add|list|rollover`: `add` prepends to the fil
- `2026-11-10T16:45:07` Claude Code [ownership] REV 128: .aimem/handoff.md -> 관리자
- `2026-11-10 16:34` 관리자 [handoff] REV 128: - `2026-11-10 16:34` Claude Code (Taeseok: "write AIMEM.md in English, clear and declarative, usable by any LLM"): **REV 128. AIMEM.md rewritten in English.** Every section, rule and log entry translated into declarative English; section numbers (`0.1`, `4.5`, `8.0-8`, …) kept so briefs, `CLAUDE.md`
- `2026-11-10 16:21` 관리자 [handoff] REV 127: - `2026-11-10 16:21` Claude Code (Taeseok: "fix the same-second comparison defect"): **REV 127. Fixed the same-second comparison defect in `archive`.** Noted but left open at REV 119 - `archive_plan` compared the cutoff with `<`, so `--days 0` skipped rows finished in the same second and had to be r
- `2026-11-10 17:55` 관리자 [handoff] REV 126: - `2026-11-10 17:55` Claude Code (Taeseok: "make the briefs and AIMEM.md consistent and systematic"): **REV 126. One set of round routines.** New `8.0-8 Manager Round Routine and Control` - start (read state; assign unassigned slot roles; **classify NEW requests: in scope → split, otherwise PLANNED 
- `2026-11-10 17:40` 관리자 [handoff] REV 125: - `2026-11-10 17:40` Claude Code (Taeseok: "monitor from the phone too, install as a Chrome app"): **REV 125. Installable PWA.** `static/manifest.webmanifest` (standalone, icons 192/512/maskable) + `sw.js` (app shell only, stale-while-revalidate; **`/api/*` and login are never cached**) + head tags 
- `2026-11-10 17:10` 관리자 [handoff] REV 124: - `2026-11-10 17:10` Claude Code (Taeseok: "roles and remarks follow the Manager's intent" / "the Manager must know what I add" / "slot management is the Manager's responsibility"): **REV 124. Slot control sorted out.** (1) The web changes **harness and model only** - sending role or remark returns 
- `2026-11-10 16:40` 관리자 [handoff] REV 123: - `2026-11-10 16:40` Claude Code (Taeseok: "how does archiving work" → instruction to do 1+2): **REV 123. Archiving: one tool, two trigger points.** (1) `aimem_db.py archive` split into `archive_plan/apply`, and it now also moves **request files and graphs (with side files and inputs)** - today's ma
- `2026-11-10 16:10` 관리자 [handoff] REV 122: - `2026-11-10 16:10` Claude Code (Taeseok: "add/remove slot harnesses, choose models - from the openclaw-configured models"): **REV 122. Slot management via web and CLI.** (1) New `aimem_db.py slot add|set|remove|list` - DB `slots` is the source of truth, `fleet_slots.json` mirrored, `events` record
- `2026-11-10 15:30` 관리자 [handoff] REV 121: - `2026-11-10 15:30` Claude Code (Taeseok: "details in markdown"): **REV 121. Markdown rendering in detail views.** A renderer inside `app.js` with no external library (Section 1 bans CDNs) - headings, paragraphs (line breaks preserved as `<br>`), lists (indented nesting, `-` vs `1.` separated), cod
- `2026-11-10 15:00` 관리자 [handoff] REV 120: - `2026-11-10 15:00` Claude Code (Taeseok: "details with line breaks, in full"): **REV 120. Removed truncation in detail views; guaranteed line breaks.** Four truncations removed - (1) handoff log 400 chars (`reader` LOG_MAX in two paths + `aimem_db.state_dict` `substr(body,1,400)`) → full text (mea
- `2026-11-10 14:30` 관리자 [handoff] REV 119: - `2026-11-10 14:30` Claude Code (Taeseok: "remove all finished work"): **REV 119. First clean-up of board, queue and request tree.** (1) All 31 lingering REVIEW tasks belonged to DONE requests or finished graphs (G-004~007 100%; G-003 and G-005 resolved in later rounds), so they were closed as DONE
- `2026-11-10 14:20` 관리자 [handoff] REV 118: - `2026-11-10 14:20` Claude Code (Taeseok's instruction): **REV 118. Detail views reachable from all three monitor tabs.** Places that had no detail: idle slot rows, board rows without a run (Manager's own work), the queue, graph nodes (tasks), request subtasks without a run, past Manager sessions, 
- `2026-11-10 13:50` 관리자 [handoff] REV 117: - `2026-11-10 13:50` Claude Code (Taeseok's instruction): **REV 117. Five monitor design-vs-function checks + shared CA and Windows proxy.** (1) For closed requests (DONE/REJECTED) the request status decides progress and ETA (`reader._estimate`, front end shows "closed") - 10 DONE requests had shown
- `2026-11-10 11:40` 관리자 [handoff] REV 116: - `2026-11-10 11:40` Claude Code (Taeseok's instruction, fleet stopped): **REV 116. Direct monitor UI work + clearing handled items.** (1) UI: numbered titles → bullets, type scale 15/14/13/12, width 1680 + fixed request sidebar, underline tabs with counts, Manager session line (`/api/state.managers
- `2026-11-10 10:40` 관리자 [handoff] REV 115: - `2026-11-10 10:40` Manager (R6): **REV 115. Four slots back + `fleet_graph` cut down three times + tab UI.** (1) **S2 (codex, kistillm) returned.** KISTI recovered in the morning (smoke 28 s), test-path ownership reverted S4→**S2**, and `tests/test_fleet*.py` was **registered** as S2-owned (Taeseo
- `2026-11-09 21:50` 관리자 [handoff] REV 114: - `2026-11-09 21:50` Manager (R5): **REV 114. DB phase 2 complete + second public-surface pass.** (1) **Four operating-state tables removed** (Sections 2, 3, 4.5, 6; 772→705 lines). Order respected - removed **after** `reader` (T-069, S1), `fleet.py` (T-070, Manager) and `aimem_board` (T-071, S1) re
- `2026-11-09 19:45` 관리자 [handoff] REV 113: - `2026-11-09 19:45` Manager (R4): **REV 113. External exposure (HTTPS + access control) + linter phase 2.** (1) **Request `407b` (exposure):** the Manager added TLS (`--tls`, self-signed cert in `.aimem/tls/`) and access control (32-byte token → hmac-signed session cookie `HttpOnly;Secure;SameSite=
- `2026-11-09 19:01` 관리자 [handoff] REV 112: - `2026-11-09 19:01` Manager: Claude Code (approved by Taeseok 2026-11-09 18:20, applied while Manager and workers were stopped): **REV 112. Unified identifier scheme (`8.0-5` created).** Request `Q-<YYMMDD>-<4 chars>` / task `T-0xx` / graph `G-00x` / run `<T>-<S#>-a<n>-<HHMMSS>` / round `R<n>` (rec
- `2026-11-09 18:05` 관리자 [handoff] REV 111: - `2026-11-09 18:05` Manager (R3): **REV 111 (2/2). Took over the round R2 cut short by ending its turn, and split web request `8d8d`.** **Why it broke:** R2 set up a background watcher and ended its turn saying "I will continue when notified" - **a one-shot ACP session never wakes again.** Rule pin
- `2026-11-09 17:35` 관리자 [handoff] REV 111: - `2026-11-09 17:35` Manager (R2): **REV 111 (1/2). First round run as a task DAG + two web requests split.** Graph `R-002`, 6 nodes (N1 ETA overrun / N2 linter board slots / N3 light mode + readability / N4 test reinforcement / N5 cross-review / N6 Strata reskin). **When a dependency clears, the ne
- `2026-11-09 17:10` 관리자 [handoff] REV 110: - `2026-11-09 17:10` Manager: **REV 110. Fleet monitoring web UI, first pass (Taeseok's order 2026-11-09).** First live round under the Claude ACP Manager regime. 7 rows registered in `Section 6` (`tools/aimem_monitor/**`, `tests/test_aimem_monitor*.py`, `.aimem/requests/**`; approved by Taeseok, `6
- `2026-11-09 16:40` 관리자 [handoff] REV 109: - `2026-11-09 16:40` Manager: Claude Code (Taeseok's instruction 2026-11-09, not a Manager session): **REV 109. Manager becomes an Opus 5.5 Claude ACP session; workers become one-shot harness CLI processes.** (1) Header, `0.5`, `Section 2`, `Section 5`, `Section 7`, `8.0` revised - the Manager is id
- `2026-11-09 15:00` 관리자 [handoff] REV 108: - `2026-11-09 15:00` Manager: Claude Code (Taeseok's instruction 2026-11-09, not a Manager session): **REV 108. Cleared up the ACP child model-label confusion.** In the high-five check `sessions_list.model` showed `kistillm` for all three (S1 actually ran on sonnet-5), so Clo and Gureum asked back. 
- `2026-11-10T16:34:02` Claude Code [rev] REV 128: REV 128: AIMEM.md rewritten in English (declarative protocol text, same section numbers); Korean-only regexes in linter/reader/migrate widened to accept the English labels
- `2026-11-10T16:21:30` 클로드 코드 [rev] REV 127: REV 127: archive 같은 초 비교 결함 수정 - archive_plan 기준 시각을 포함 비교(<=)로, 회귀 테스트 추가
- `2026-11-10T16:11:46` 클로드 코드 [rev] REV 126: REV 126: 8.0-8 관리자 라운드 루틴과 통제권 신설, 브리프 정비, 8.0-5 중복 번호 해소
- `2026-11-10T15:43:45` 클로드 코드 [rev] REV 125: REV 125: PWA 설치형(매니페스트·서비스 워커·아이콘), API 캐시 금지
- `2026-11-10T15:38:25` 클로드 코드 [rev] REV 124: REV 124: 슬롯 통제권 - 웹은 하네스·모델만, 역할·비고는 관리자, 웹 변경은 NEW 요청으로 관리자 통지
- `2026-11-10T15:37:47` 웹(접근 토큰) [slot] REV 123: slot remove S5 (codex, 모델 -, 소유권 0행 내림)
- `2026-11-10T15:37:41` 웹(접근 토큰) [slot] REV 123: slot add S5 codex 모델 (하네스 기본) - (미배정 - 관리자가 다음 라운드에 정함)
- `2026-11-10T15:35:36` 웹(접근 토큰) [slot] REV 123: slot remove S5 (codex, 모델 -, 소유권 0행 내림)
- `2026-11-10T15:35:36` 관리자(R7) [slot] REV 123: slot set S5: 역할, 비고
- `2026-11-10T15:35:36` 웹(접근 토큰) [slot] REV 123: slot add S5 codex 모델 (하네스 기본) - (미배정 - 관리자가 다음 라운드에 정함)
- `2026-11-10T15:19:32` 웹(접근 토큰) [archive] REV 123: 0일 경과 - 태스크 0건, 요청 1건, 그래프 1개 아카이브
- `2026-11-10T15:19:10` 클로드 코드 [rev] REV 123: REV 123: archive 가 요청·그래프까지, 실행 지점 관리자 체크포인트 + 웹 '끝난 것 정리'
- `2026-11-10T15:06:16` 클로드 코드 [rev] REV 122: REV 122: 슬롯 관리(추가·삭제·하네스·모델) 웹+CLI, 모델은 OpenClaw 설정 목록
- `2026-11-10T15:05:22` 웹(접근 토큰) [slot] REV 121: slot remove S5 (codex, 모델 kisti/kistillm, 소유권 0행 내림)
- `2026-11-10T15:05:18` 웹(접근 토큰) [slot] REV 121: slot add S5 codex 모델 kisti/kistillm - UI 시험 슬롯
- `2026-11-10T15:04:48` 웹(접근 토큰) [slot] REV 121: slot remove S5 (codex, 모델 kisti/kistillm, 소유권 0행 내림)
- `2026-11-10T15:04:47` 웹(접근 토큰) [slot] REV 121: slot set S5: 하네스 opencode→codex, 모델 exaone/k-exaone_v2.5→kisti/kistillm
- `2026-11-10T15:04:47` 웹(접근 토큰) [slot] REV 121: slot add S5 opencode 모델 exaone/k-exaone_v2.5 - 시험 슬롯
- `2026-11-10T14:48:41` 클로드 코드 [rev] REV 121: REV 121: 상세보기 마크다운 렌더링(의존성 없음, HTML 비해석, 원문 토글)
- `2026-11-10T14:31:11` 클로드 코드 [rev] REV 120: REV 120: 상세보기 잘림 제거(로그·관리자 단계/이벤트·stderr 전문, ?all=1) + 줄바꿈 보장
- `2026-11-10T14:25:09` 클로드 코드 [rev] REV 119: REV 119: 보드·큐·요청 트리 1차 정리 - DONE 59건 아카이브, 요청 10건·그래프 6개 아카이브, 큐 2건 내림
- `2026-11-10T14:25:09` 클로드 코드(태석 지시 2026-11-10 정리) [archive] REV 118: DONE 0일 경과 5건 -> board-*.md: T-085, T-087, T-088, T-092, T-093
- `2026-11-10T14:24:21` 클로드 코드(태석 지시 2026-11-10 정리) [queue] REV 118: queue -4 작업자 허용목록 - 브리프가 `PYTHONPATH=... python3` 로 시작하면 아직 막힌다
- `2026-11-10T14:24:20` 클로드 코드(태석 지시 2026-11-10 정리) [queue] REV 118: queue -8 `fleet_graph.step()` - `running` 인데 `attempts` 가 빈 노드에서 `IndexError`

## 4.5 대기 큐

| 순서 | 태스크 | 후보 슬롯 | 비고 |
| --- | --- | --- | --- |
| 1 | `.aimem/runs/<id>.json`·`.rc` 에도 심볼릭 링크 검사 | S1 | T-064 가 `brief`/`out`/`err` 만 막았다. 메타 파일이 링크면 `slot`/`label`/`model` 문자열이 응답에 실린다 (S1 보고 ④) |
| 2 | 요청 -> 서브태스크 분담을 관리자 CLI 로 (`fleet.py request` 또는 `fleet_graph` 와 요청 파일 연결) | 관리자 | 지금은 요청 파일을 손으로 고쳐야 분담이 보인다. REV 111 에서 `graph`/`graph_node` 필드를 손으로 넣었다 |
| 3 | 그래프 노드 <-> 요청 서브태스크 자동 동기화 | 관리자 | `8.0-5` 채택 결과. `fleet_graph` 가 노드 상태를 바꿀 때 `.aimem/requests/*.json` 의 같은 `graph_node` 행도 갱신하면 손 갱신이 사라진다 |
| 4 | `serve()` 가 `Handler.rate` 를 묶는지 보는 테스트 | S4 | S4 보고. 지금 테스트는 제한기를 직접 묶은 핸들러를 쓰므로 `serve()` 에서 `rate` 배선을 빼도 안 잡힌다. `serve(once=True)` 를 띄워 6번째 POST 가 429 인지 보면 된다 |
| 5 | `aimem_board.py` 의 `--file` 마크다운 경로 폐기 여부 결정 | 관리자 | T-071 이 `AIMEM.md` 쓰기를 끊었으나 `--file <사본>` 으로 임의 마크다운을 옛 방식으로 편집하는 길은 남겼다(`tests/test_aimem_lint.py` 스모크가 그 길을 쓴다). 795줄 중 상당수가 그 경로다 - 테스트를 DB 쪽으로 옮기고 지울지 정할 것 |
| 6 | `state_dict()` 이벤트 합집합 질의와 `migrate` 의 REV 씨앗 규칙 테스트 | S4 | R5 에서 둘 다 실측 결함으로 고쳤다: (a) `LIMIT 50` 이 핸드오프를 밀어내 웹 4절 로그가 2건으로 줄었다 -> 합집합(+핸드오프 12건), (b) `migrate` 가 AIMEM.md 서문에서 REV 를 매번 덮어써 114->113 으로 되돌렸다 -> DB 에 REV 가 없을 때만 씨앗. 회귀 테스트가 없다 |
| 7 | `fleet.roster()` 마크다운 폴백의 셋째 칸이 세션키가 아니라 **역할** 이다 (docstring 불일치) | S1 | T-080 이 테스트로 현재 동작을 고정하며 발견. 폴백은 표가 없어 사실상 죽은 길이라 영향 없음 - 주석만 고치면 된다 |
| 8 | `aimem_monitor` HTTP 테스트가 샌드박스(codex/S2)에서 소켓 금지로 22건 error - TCP 불가 시 폴백 `PipeConnection` 에 `settimeout` 없음 | S2 | T-085·T-088 보고. 관리자 환경에서는 전부 통과하므로 기준선 판정이 슬롯마다 달라진다 - 작업자가 자기 환경을 기준선으로 오인한다 |
| 9 | `fleet_graph` 결함 11 - `refused` 로 `blocked` 가 된 노드를 아무도 거두지 않는다 (`unblock`/`reset` 명령 없음) | S1 | S4 3차 검수 [중간]. 작업자가 살아 있는 동안 슬롯이 계속 바쁨 → 같은 슬롯 노드가 영영 못 뜬다. 나중에 `.rc` 가 써져도 노드는 blocked 로 남는다 |
| 10 | `fleet_graph.harness_durations()` - 깨진 run 메타(`pid` 가 문자열) 하나로 `progress`/`status`/`list` 가 TypeError | S1 | S4 3차 검수 [낮음]. `_busy_slots` 는 삼키는데 여기는 안 삼킨다 - 같은 호출을 두 곳이 다르게 방어한다 |
| 11 | `report_block_reason` 소문자 평문 거짓 양성 (`blocked: none`·`reject: no`·`needs-review: none`) | S1 | S4 3차 검수 [낮음]. 결함 9 를 고치며 다시 열린 길. `rejected: none` 은 None 인데 `reject: none` 은 상태 - 어미 -ed 유무로 갈린다. 안전한 쪽(사람에게 넘김)이라 낮음 |
| 12 | `tests/test_fleet_graph.py` 커버리지 구멍 - 결함 1·2·7·8·10 을 막는 테스트가 없다 | S2 | S4 3차 검수의 커버리지 표. 특히 `+09:00` 케이스는 `node_timeout_sec=10**9` 라 **옛 구현(tz 그냥 뗌)도 통과한다** - 겉으로는 tz 를 검사하는데 아무것도 검사하지 않는다. `_kill_run` 을 mock 하지 않는 테스트가 하나도 없다 |

## 6. 파일 소유권

| 경로 패턴 | 쓰기 소유 | 비고 |
| --- | --- | --- |
| `(그 외 모든 경로)` | 미배정 | 배정 전 쓰기 금지. 아래 절차로 요청 |
| `.aimem.lock` | 미배정 | flock 대상. 내용을 쓰지 않고 unlink 금지 |
| `.aimem/aimem.db` | 관리자 | **운영 상태의 정본(전환 중)**. `.gitignore` 대상 - 커밋되는 것은 `AIMEM-state.md` 스냅샷 |
| `.aimem/archive/**` | 관리자 | 아카이브는 관리자만 씁니다 |
| `.aimem/briefs/**` | 관리자 | 관리자 세션 브리프와 참조 자료(예: `strata-tokens.css`). 작업자는 읽기만 |
| `.aimem/envcheck-state.json` | 관리자 | 러너의 누적 판정 상태. **러너만 씁니다. `.gitignore` 대상 - 이력 자산이 아니라 상태 파일(REV 106)** |
| `.aimem/graph/**` | 관리자 | 그래프 파일·로그·노드 브리프. `fleet_graph` 와 관리자만 씁니다. **`.gitignore` 대상**입니다(`.aimem/runs/` 와 같은 성격 - 실행 기록). 노드 입력은 `inputs/` 아래 |
| `.aimem/handoff.md` | 관리자 | 핸드오프 로그 정본 파일 (REV 129). handoff add/rollover 로만 쓴다; AIMEM.md 4절은 방법만 |
| `.aimem/outbox/README.md` | 관리자 | 아웃박스 사용법 |
| `.aimem/requests/**` | 관리자 | 웹에서 들어온 작업 요청. 생성은 **서버만** 하고, 분담(`status`/`subtasks`/`graph`)은 관리자가 채웁니다 |
| `.aimem/tls/**` | 관리자 | 외부 공개용 자체 인증서·개인키(0600)·접근 토큰. **`.gitignore` 대상, 절대 커밋 금지** (REV 113) |
| `.githooks/**` | S3 | T-008 |
| `.gitignore` | 관리자 |  |
| `AGENTS.md` | 관리자 | `CLAUDE.md` 심볼릭 링크 (타 하네스용) |
| `AIMEM-state.md` | 관리자 | `aimem_db.py render` **산출물**. 손으로 고치지 않는다 (린터가 바이트 대조) |
| `AIMEM.md` | 관리자(클로) | 작업자 쓰기 금지 |
| `CLAUDE.md` | 관리자 | 부트스트랩. 자동 주입되는 유일한 파일 |
| `README.md` | 관리자 | 저장소 소개 |
| `skills/**` | 관리자 | **현재 비어 있음** (REV 101 에서 `acp-slot-lifecycle` 제거). 되살아나면 이 행이 그대로 적용된다 |
| `tests/test_aimem_lint.py` | S2 | T-005B. R5 에 S4 로 잠시 이관(KISTI 장애) → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_aimem_monitor*.py` | S2 | 웹 UI 계약 테스트. R5 에 S4 로 잠시 이관 → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_fleet*.py` | S2 | `fleet.py` 회귀 테스트. 태석님 승인 2026-11-10 R6 브리프 (9절 2번 해소 - 승인 당시 S4 였으나 S2 복귀로 S2) |
| `tools/aimem_board.py` | S1 | T-006 / T-009 |
| `tools/aimem_db.py` | 관리자 | 운영 상태 SQLite (REV 112~). `migrate`/`render`/`check`/`event`. 출처는 클로드 코드 |
| `tools/aimem_lint.py` | S1 | T-005A |
| `tools/aimem_monitor/__init__.py` | 관리자 | 라운드 3 웹 UI. 공통 계약(`collect()` 스키마·가중치) |
| `tools/aimem_monitor/__main__.py` | 관리자 | 라운드 3 웹 UI. `python3 -m aimem_monitor` 진입점 |
| `tools/aimem_monitor/reader.py` | S1 | 라운드 3 웹 UI. 파일 -> 딕셔너리 (파싱·ETA) |
| `tools/aimem_monitor/server.py` | 관리자 | 라운드 3 웹 UI. HTTP 라우팅 + 요청 파일 쓰기. **합류점을 하나로 두는 장치** |
| `tools/aimem_monitor/static/**` | S3 | 라운드 3 웹 UI. 정적 프런트엔드 (HTML/JS/CSS) |
| `tools/envcheck/__init__.py` | 관리자 | 공통 계약(`check()` / `Result`) 정의 |
| `tools/envcheck/__main__.py` | 관리자 | 통합 러너. **합류점을 하나로 두는 장치** |
| `tools/envcheck/runtime.py` | S2 | 라운드 2. 실행 환경 계층 검사 |
| `tools/envcheck/sessions.py` | S1 | 라운드 2. 세션·에이전트 계층 검사 |
| `tools/envcheck/terminal.py` | S3 | 라운드 2. 터미널 규약 계층 검사 |
| `tools/fleet.py` | 관리자 | 슬롯 시작/종료 도우미 |
| `tools/fleet_graph.py` | 관리자 | 라운드 R6 동안만 S1 이었다(T-081/087/092, 태석님 R6 브리프 승인). 라운드 종료로 관리자 환원 - 큐 14·17·18·19 를 꺼낼 때 다시 S1 로 등재한다 |
| `tools/fleet_slots.json` | 관리자 | 슬롯별 하네스·모델 정본. `fleet.py slot` 이 쓰고 `reader` 가 읽는다 (`8.0` 모델 항) |

## 요청

| id | 제목 | 요청자 | 상태 | 생성 |
| --- | --- | --- | --- | --- |
| 20261109-170155-582a | AIMEM 함대 모니터링 웹 UI | 태석 | DONE | 2026-11-09T17:01:55 |
| 20261109-171508-ce9f | 함대 모니터 UI 가독성·정렬 개선 | 태석 (클로드 코드 전달) | DONE | 2026-11-09T17:15:08 |
| 20261109-172326-c5c1 | 모니터 UI 스타일을 KISTI Strata 모니터(aida.kisti.re.kr:10430/#monitor)와 비슷하게 | 태석 (클로드 코드 전달) | DONE | 2026-11-09T17:23:26 |
| 20261109-173900-8d8d | 상세 조회 UI 추가 | 태석 (폼의 요청자 칸이 비어 "(익명)" 으로 저장됐다 - REV 111 에서 서버가 빈 값을 거부하도록 고쳤다) | DONE | 2026-11-09T17:39:00 |
| 20261109-175025-cf63 | "작업자 실행 상태" 등 id 중심 표시 | 태석 (폼의 요청자 칸이 비어 "(익명)" 으로 저장됐다 - 서버가 이제 빈 값을 400 으로 거절한다) | DONE | 2026-11-09T17:50:25 |
| 20261109-175208-c87c | lost 실행의 경과 시간 고정 및 표시 | 태석 (클로드 코드 전달) | DONE | 2026-11-09T17:52:08 |
| 20261109-180055-b125 | 함대 현황의 슬롯 모델을 슬롯별로 표시 (S1 opus / S4 sonnet) | 태석 (클로드 코드 전달) | DONE | 2026-11-09T18:00:55 |
| 20261109-190205-407b | 함대 웹 UI 외부 공개: HTTPS(자체 인증서) + 접근 제어(토큰, 선택적 GitHub 로그인) | 태석 (클로드 코드 전달) | DONE | 2026-11-09T19:02:05 |
| Q-261110-7201 | 정책: 유료 모델 대체 금지 - kistillm 장애 시 보고만 | 태석 (클로드 코드 전달) | DONE | 2026-11-10T09:33:10 |
| Q-261110-549a | AIMEM 함대 모니터 페이지가 너무 길어졌어. UI 구조 탭방식으로 변경해 | 태석 | DONE | 2026-11-10T09:41:01 |

## 실행 (최근 30)

| run id | 태스크 | 슬롯 | 하네스 | 모델 | 시도 | 상태 | rc | 시작 | 끝 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-074-S3-a1-212016 | T-074 | S3 | opencode |  | 1 | done | 0 | 21:20:16 | 21:22:54 |
| T-069-S1-a2-212247 | T-069 | S1 | claude | opus | 2 | done | 0 | 21:22:47 | 21:23:48 |
| T-073-S4-a1-212402 | T-073 | S4 | claude | sonnet | 1 | done | 0 | 21:24:02 | 21:25:20 |
| T-071-S1-a1-212402 | T-071 | S1 | claude | opus | 1 | done | 0 | 21:24:02 | 21:27:01 |
| T-073-S4-a2-212535 | T-073 | S4 | claude | sonnet | 2 | done | 0 | 21:25:35 | 21:26:14 |
| T-071-S1-a2-212719 | T-071 | S1 | claude | opus | 2 | done | 0 | 21:27:19 | 21:28:58 |
| T-077-S1-a1-212927 | T-077 | S1 | claude | opus | 1 | done | 0 | 21:29:27 | 21:30:20 |
| T-076-S4-a1-213229 | T-076 | S4 | claude | sonnet | 1 | done | 0 | 21:32:30 | 21:34:10 |
| T-078-S4-a1-213751 | T-078 | S4 | claude | sonnet | 1 | done | 0 | 21:37:51 | 21:41:06 |
| T-054-S1-a1-213752 | T-054 | S1 | claude | opus | 1 | done | 0 | 21:37:52 | 21:39:49 |
| T-079-S4-a1-214626 | T-079 | S4 | claude | sonnet | 1 | done | 0 | 21:46:26 | 21:47:21 |
| ADHOC-S2-a1-091223 | ADHOC | S2 | codex |  | 1 | done | 0 | 09:12:23 | 09:12:50 |
| T-080-S2-a1-093320 | T-080 | S2 | codex |  | 1 | done | 0 | 09:33:20 | 09:41:30 |
| T-081-S1-a1-093320 | T-081 | S1 | claude | opus | 1 | done | 0 | 09:33:20 | 09:36:26 |
| T-082-S3-a1-093320 | T-082 | S3 | opencode |  | 1 | done | 0 | 09:33:20 | 09:44:05 |
| T-084-S4-a1-093638 | T-084 | S4 | claude | sonnet | 1 | done | 0 | 09:36:38 | 09:40:12 |
| T-085-S2-a1-094140 | T-085 | S2 | codex |  | 1 | done | 0 | 09:41:40 | 09:50:25 |
| T-083-S3-a1-094420 | T-083 | S3 | opencode |  | 1 | done | 0 | 09:44:20 | 09:44:55 |
| T-083-S3-a2-094507 | T-083 | S3 | opencode |  | 2 | done | 0 | 09:45:07 | 09:52:32 |
| T-087-S1-a1-095756 | T-087 | S1 | claude | opus | 1 | done | 0 | 09:57:56 | 10:01:19 |
| T-089-S3-a1-095756 | T-089 | S3 | opencode |  | 1 | done | 0 | 09:57:56 | 10:03:48 |
| T-088-S2-a1-100129 | T-088 | S2 | codex |  | 1 | done | 0 | 10:01:29 | 10:11:36 |
| T-090-S4-a1-100129 | T-090 | S4 | claude | sonnet | 1 | done | 0 | 10:01:29 | 10:04:53 |
| T-089-S3-a2-100401 | T-089 | S3 | opencode |  | 2 | done | 0 | 10:04:01 | 10:11:23 |
| T-092-S1-a1-101439 | T-092 | S1 | claude | opus | 1 | done | 0 | 10:14:39 | 10:17:49 |
| T-094-S3-a1-101439 | T-094 | S3 | opencode |  | 1 | done | 0 | 10:14:39 | 10:19:45 |
| T-093-S2-a1-101757 | T-093 | S2 | codex |  | 1 | done | 0 | 10:17:57 | 10:19:58 |
| T-091-S3-a1-102121 | T-091 | S3 | opencode |  | 1 | done | 0 | 10:21:21 | 10:26:18 |
| T-095-S4-a1-102121 | T-095 | S4 | claude | sonnet | 1 | done | 0 | 10:21:21 | 10:24:59 |
| T-091-S3-a2-102624 | T-091 | S3 | opencode |  | 2 | done | 0 | 10:26:24 | 10:39:50 |
