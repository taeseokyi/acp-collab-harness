# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)

- 정본은 `.aimem/aimem.db` 입니다. 이 파일을 손으로 고치지 마십시오. 생성 2026-11-10T21:47:54 / REV 146

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

- `2026-11-10 21:47` 클로드 코드 [handoff] REV 146: **REV 146. 웹에서 프로젝트 결과물을 보고, 요청 수정 화면에서 프로젝트를 바꾼다.** (1) `GET /api/projects/<이름>/files` · `/file?path=` - `projects/<이름>/` 의 파일 목록(최대 500, README·PROGRESS 먼저, 숨김·링크·의존성 폴더 제외)과 본문(텍스트만, 200KB 까지, 상세 응답과 같은 가림). 경로는 폴더 안 상대 경로만 - 절대 경로·`..`·숨김 조각·심볼릭 링크 거절. (2) 함대 탭 프로젝트 카드에 '결과물 보기' → 상세 패널에서 목록, 행을
- `2026-11-10 21:40` 클로드 코드 [handoff] REV 145: **REV 145. 프로젝트 구조 종합 검토 - 라운드 흐름 결함 5건과 화면 가독성 정비.** (1) 웹 요청 폼은 파일만 만들고 `request list` 는 DB 만 읽어 표준 브리프 라운드의 관리자가 NEW 를 못 봤다 → `aimem_db.load_request_files` 를 `request list/set`·`task set` 앞에서 부른다. (2) `request set --project` 추가(파일 없으면 만든다). (3) 관리자가 안 뜬 라운드는 `round.json` 에 `state: failed` → 프로젝트 
- `2026-11-10 21:02` Claude Code [handoff] REV 144: **REV 144. 작업자 실행 상태에 프로젝트 구분.** 태석님 지시. 식별자는 그대로 두고, 작업자를 띄울 때 실행 기록(`.aimem/runs/<id>.json`)에 `project`·`round` 를 따로 적는다 - 프로젝트는 그래프 노드의 `"project"` 또는 태스크→요청(`task set --request`)에서, 라운드는 가장 최근에 띄운 라운드(`fleet.current_round()`). 그래프 파일에도 `round`. 웹 '작업자 실행 상태' 표에 **프로젝트 칸**(`이름 · R<n>`, 없으면 '함대'),
- `2026-11-10 21:00` Claude Code [handoff] REV 143: **REV 143. 프로젝트별 진행 상황을 함대 화면에.** 태석님 지시(식별자에는 붙이지 않는다 - 알아볼 수만 있으면 된다 / 대신 각 프로젝트가 얼마나 진행됐는지, 몇 라운드를 거쳤는지). 식별자 체계(`8.0-3-1`)는 그대로. (1) 함대 탭 '프로젝트' 카드: 프로젝트마다 진행률 막대(그 프로젝트 요청들의 평균 - 완료 100, 진행 중은 요청 진행율, 거절 제외, 아카이브된 완료 포함), 요청 완료/진행/대기 건수, 거친 라운드 수와 목록, 마지막 라운드 시각, `PROGRESS.md` 최근 항목(펼침). `/api/
- `2026-11-10 20:10` Claude Code [handoff] REV 142: **REV 142. 프로젝트 - 여러 라운드를 묶는 단위, 결과물은 프로젝트 폴더 한 곳에.** 태석님 정정(라운드는 과정이라 라운드별 결과물 폴더는 맞지 않다 / 요청마다 프로젝트 선택 / 저장소 안). (1) 요청에 `project` 필드: 웹 작업 요청 폼의 '프로젝트' 칸(목록에서 고르거나 새 이름, 한글·영문·숫자·`-`·`_` 40자, 빈 값 = 함대 자체의 일). `aimem_db.py request list` 가 `[이름]` 으로 보인다. (2) 결과물은 `projects/<프로젝트>/` 에 여러 라운드에 걸쳐 쌓인다
- `2026-11-10T20:08:35` Claude Code [ownership] REV 141: rounds/** -> 관리자
- `2026-11-10T20:08:35` Claude Code [ownership] REV 141: projects/** -> 관리자
- `2026-11-10 20:01` Claude Code [handoff] REV 141: **REV 141. 준비 점검 펼침이 새로고침에 닫히던 것.** 태석님 지시. 함대 탭 '준비 점검' 목록은 5초마다 다시 그려지며 펼친 상태를 잃었다 - 펼침을 `state.expanded` 에 기억하고, '준비' 를 방금 눌렀을 때만 한 번 자동으로 펼친다(그 뒤 사람이 접으면 접힌 채). 서비스 워커 캐시 v3. 바뀐 파일: `tools/aimem_monitor/static/{app.js,sw.js}`. 브라우저로 자동 새로고침 두 번 넘게 열려 있음을 확인.
- `2026-11-10 19:49` Claude Code [handoff] REV 140: **REV 140. 웹에서 라운드 할 일을 넣는 길이 보이게.** 태석님 지시(작업 요청 폼이 안 보인다). 함대 탭 '라운드 실행' 아래에 지금 쌓인 NEW 요청 건수와 **'할 일 쓰기'** 버튼(작업 요청 폼으로 이동·제목 칸 포커스), 요청 0건으로 라운드를 누르면 확인 창이 '점검만 하고 끝난다' 고 알림, 폼 제목에 '다음 라운드가 할 일' 설명. 앞선 안내 문구의 '요청 탭' 은 틀린 말이었다(요청 트리 탭엔 입력 칸이 없다). 서비스 워커 캐시 v2. 바뀐 파일: `tools/aimem_monitor/static/{a
- `2026-11-10 18:51` Claude Code [handoff] REV 139: **REV 139. 라운드 내용은 웹 요청으로, 결과물은 라운드 작업 공간으로.** 태석님 지시. (1) 표준 브리프 `.aimem/briefs/manager-round-standard.md`: 그 라운드만의 확정 브리프가 없으면 '라운드 실행' 이 이 파일로 다음 번호 라운드를 띄운다 - 할 일은 NEW 요청 전부, 요청도 큐도 비었으면 보고만 하고 끝. 브리프를 매번 쓰지 않는다. (2) 라운드 작업 공간 `rounds/R<N>/`(git 포함): 띄울 때 만들고 보낸 브리프를 `brief.md` 로 남긴다. 종료 보고는 `RE
- `2026-11-10T18:50:59` Claude Code [ownership] REV 138: rounds/** -> 관리자
- `2026-11-10 18:39` Claude Code [handoff] REV 138: **REV 138. 남은 큐 3건을 끝내 대기 큐가 비었다.** 태석님 지시(필요하면 여기서 실행). (1) `fleet_graph.py unblock <그래프> <노드>`: 사람이 확인한 blocked/failed 노드를 다시 굴린다 - 작업자가 살아 있으면 거절, 죽이지 못해 막혔던 실행이 그 뒤 끝났으면 새로 띄우지 않고 거두게 하고, 그 밖엔 todo(한도를 다 썼으면 한 번 더), 의존 때문에 막힌 뒤쪽 노드도 푼다. `8.0-5` 명령 목록에 한 줄. (2) 깨진 run 메타: `fleet._run_state` 가 정수 
- `2026-11-10T18:38:08` Claude Code [queue] REV 137: queue -1 `fleet_graph` 결함 11 - `refused` 로 `blocked` 가 된 노드를 아무도 거두지 않는다 (`unblock`/`reset` 명령 없음)
- `2026-11-10T18:38:08` Claude Code [queue] REV 137: queue -2 `fleet_graph.harness_durations()` - 깨진 run 메타(`pid` 가 문자열) 하나로 `progress`/`status`/`list` 가 TypeError
- `2026-11-10T18:38:08` Claude Code [queue] REV 137: queue -3 `tests/test_fleet_graph.py` 커버리지 구멍 - 결함 1·2·7·8·10 을 막는 테스트가 없다
- `2026-11-10 18:32` Claude Code [handoff] REV 137: **REV 137. 대기 큐 12건 → 3건.** 태석님 지시(꼭 필요한 것만 남길 것). 현재 코드와 대조해 9건을 내렸다 - 원문과 건별 이유는 `retired-sections-2026-11.md` `[REV 137 내림] 4.5 대기 큐`. 남은 큐: (1) `fleet_graph` unblock/reset 명령 (2) `harness_durations` TypeError (3) `test_fleet_graph.py` 커버리지 구멍. 보드·요청·그래프는 이미 비어 있었다. R7 브리프 4-1 을 여기에 맞춤: 과제 4건(위 셋
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -1 `.aimem/runs/<id>.json`·`.rc` 에도 심볼릭 링크 검사
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -2 요청 -> 서브태스크 분담을 관리자 CLI 로 (`fleet.py request` 또는 `fleet_graph` 와 요청 파일 연결)
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -3 그래프 노드 <-> 요청 서브태스크 자동 동기화
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -4 `serve()` 가 `Handler.rate` 를 묶는지 보는 테스트
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -5 `aimem_board.py` 의 `--file` 마크다운 경로 폐기 여부 결정
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -6 `state_dict()` 이벤트 합집합 질의와 `migrate` 의 REV 씨앗 규칙 테스트
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -7 `fleet.roster()` 마크다운 폴백의 셋째 칸이 세션키가 아니라 **역할** 이다 (docstring 불일치)
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -8 `aimem_monitor` HTTP 테스트가 샌드박스(codex/S2)에서 소켓 금지로 22건 error - TCP 불가 시 폴백 `PipeConnection` 에 `settimeout` 없음
- `2026-11-10T18:31:47` Claude Code [queue] REV 136: queue -11 `report_block_reason` 소문자 평문 거짓 양성 (`blocked: none`·`reject: no`·`needs-review: none`)
- `2026-11-10 18:29` Claude Code [handoff] REV 136: **REV 136. 모니터 GitHub 로그인 - 기기 흐름.** 태석님 지시(reefwiz-esp32 가 쓰는 OAuth App 재사용). `monitor.env` 에 `GITHUB_CLIENT_ID` 만 있으면 기기 흐름(RFC 8628): `POST /api/github/device/start` 가 확인 코드를 받아 화면에 보이고, 사람이 github.com/login/device 에서 승인하면 `/api/github/device/poll` 이 계정을 허용 목록과 대조해 세션을 준다. 콜백 주소·시크릿 없음 - 접속 주소(내부
- `2026-11-10 18:17` Claude Code [handoff] REV 135: **REV 135. 9절 1번 승인·처리 - 위임 파일 문구.** 태석님 승인(2026-11-10). 사용자 전역 위임 파일 셋(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md`)의 "디스코드 #sss-fleet 의 클로 관리자 세션" 을 "AIMEM.md 서문에 적힌 관리자 세션" 으로 고침. 예외 목록은 그대로. 9절 표는 비었고(원문은 `retired-sections-2026-11.md` `[REV 135 내림] 9절 1번`), `8.0` 의
- `2026-11-10 18:14` Claude Code [handoff] REV 134: **REV 134. --expect-rev 기본화·로그 정렬 테스트·저장소 지침 영문화.** (1) `8.0-8` 종료 1번: `handoff add --bump` 에 `--expect-rev N` 을 항상 붙인다 - 거절되면 다시 읽고 판단, 숫자만 바꿔 재시도 금지. R7 브리프 4-2 도 같은 문구(브리프의 REV 표기 126→134, 핸드오프 정본 설명 갱신). (2) `tests/test_aimem_monitor_state.py` `test_6a_log_rev_first_then_when`: 모니터 로그가 REV 우선·같은
- `2026-11-10 18:03` Claude Code [handoff] REV 133: **REV 133. Post-REV-132 audit: five leftovers fixed, no functional defect found.** Verified on a copy of the live DB: `migrate` twice keeps 42 handoff rows, `render` twice is byte-stable, 16 concurrent processes get REVs with no overlap and the generated file equals the DB. Fixed: (1) ownership note
- `2026-11-10T18:02:30` Claude Code [ownership] REV 132: .aimem/handoff.md -> 관리자
- `2026-11-10 17:58` Claude Code [handoff] REV 132: **REV 132. Handoff log has one source of truth: the DB.** (Taeseok: "is there a simpler, equally effective way?") `events(kind=handoff)` is the only store; `.aimem/handoff.md` is a generated view of the latest 12, rebuilt inside the same write transaction as the insert and by `render`. Removed from 
- `2026-11-10 17:48` Claude Code [handoff] REV 131: **REV 131. Concurrent handoff writes are blocked at the source.** `handoff add`, `rollover` and `archive` now hold one file lock (`.aimem/handoff.lock`, flock, 30 s timeout, re-entrant per thread) for the whole read-modify-write; the REV is read and raised inside `BEGIN IMMEDIATE`; `handoff.md` is w
- `2026-11-10 17:08` Claude Code [handoff] REV 130: **REV 130. AIMEM.md compressed to rules and pointers (765→475 lines); five tool/doc mismatches fixed.** (1) Compression: Section 0 to 60 lines, hard limits stated once in `0.2`, histories replaced by archive pointers, dated provenance dropped from headings, 8.0 84→41 lines; full REV 129 text kept at
- `2026-11-10T16:47:15` Claude Code [archive] REV 129: 핸드오프 로그 9건 → .aimem/archive/handoff-<YYYY-MM>.md (최신 4건 유지)
- `2026-11-10 16:47` Claude Code [handoff] REV 129: **REV 129. Handoff log moved out of AIMEM.md (Taeseok: "manage the handoff log differently, keep the document light").** Entries now live in `.aimem/handoff.md`; Section 4 states only the method. New `aimem_db.py handoff add|list|rollover`: `add` prepends to the file, records `events(kind=handoff)`,
- `2026-11-10T16:45:07` Claude Code [ownership] REV 128: .aimem/handoff.md -> 관리자
- `2026-11-10 16:34` Claude Code (Taeseok: "write AIMEM.md in English, clear and declarative, usable by any LLM") [handoff] REV 128: **REV 128. AIMEM.md rewritten in English.** Every section, rule and log entry translated into declarative English; section numbers (`0.1`, `4.5`, `8.0-8`, …) kept so briefs, `CLAUDE.md`/`AGENTS.md` and tools still resolve their references. Literal strings that tools print or match stay in Korean and
- `2026-11-10 16:21` Claude Code (Taeseok: "fix the same-second comparison defect") [handoff] REV 127: **REV 127. Fixed the same-second comparison defect in `archive`.** Noted but left open at REV 119 - `archive_plan` compared the cutoff with `<`, so `--days 0` skipped rows finished in the same second and had to be run twice. All three comparisons (task SQL, request files, graphs) are now **inclusive
- `2026-11-10 17:55` Claude Code (Taeseok: "make the briefs and AIMEM.md consistent and systematic") [handoff] REV 126: **REV 126. One set of round routines.** New `8.0-8 Manager Round Routine and Control` - start (read state; assign unassigned slot roles; **classify NEW requests: in scope → split, otherwise PLANNED + "next round"; notification requests → confirm → DONE**), graph checkpoints (a)~(e), close (tests, RE
- `2026-11-10 17:40` Claude Code (Taeseok: "monitor from the phone too, install as a Chrome app") [handoff] REV 125: **REV 125. Installable PWA.** `static/manifest.webmanifest` (standalone, icons 192/512/maskable) + `sw.js` (app shell only, stale-while-revalidate; **`/api/*` and login are never cached**) + head tags (theme-color, apple-touch-icon). Manifest, icons and `sw.js` are exempt from auth (data-free shell,
- `2026-11-10 17:10` Claude Code (Taeseok: "roles and remarks follow the Manager's intent" / "the Manager must know what I add" / "slot management is the Manager's responsibility") [handoff] REV 124: **REV 124. Slot control sorted out.** (1) The web changes **harness and model only** - sending role or remark returns 400; a slot added from the web gets the role marker `(미배정 - 관리자가 다음 라운드에 정함)` ("unassigned - the Manager decides next round"). (2) Every web slot add/change/remove makes the server *
- `2026-11-10 16:40` Claude Code (Taeseok: "how does archiving work" → instruction to do 1+2) [handoff] REV 123: **REV 123. Archiving: one tool, two trigger points.** (1) `aimem_db.py archive` split into `archive_plan/apply`, and it now also moves **request files and graphs (with side files and inputs)** - today's manual procedure turned into code. NEW requests, graphs with running nodes and anything newer tha
- `2026-11-10 16:10` Claude Code (Taeseok: "add/remove slot harnesses, choose models - from the openclaw-configured models") [handoff] REV 122: **REV 122. Slot management via web and CLI.** (1) New `aimem_db.py slot add|set|remove|list` - DB `slots` is the source of truth, `fleet_slots.json` mirrored, `events` recorded, guard on unfinished tasks (`--force`), ownership rows removed along with the slot. `fleet.py slot` delegates here (the old
- `2026-11-10 15:30` Claude Code (Taeseok: "details in markdown") [handoff] REV 121: **REV 121. Markdown rendering in detail views.** A renderer inside `app.js` with no external library (Section 1 bans CDNs) - headings, paragraphs (line breaks preserved as `<br>`), lists (indented nesting, `-` vs `1.` separated), code fences, quotes, tables (alignment), rules, inline code / bold / i
- `2026-11-10 15:00` Claude Code (Taeseok: "details with line breaks, in full") [handoff] REV 120: **REV 120. Removed truncation in detail views; guaranteed line breaks.** Four truncations removed - (1) handoff log 400 chars (`reader` LOG_MAX in two paths + `aimem_db.state_dict` `substr(body,1,400)`) → full text (measured max 2,459 chars; lists use CSS ellipsis), (2) Manager session step bodies 1
- `2026-11-10 14:30` Claude Code (Taeseok: "remove all finished work") [handoff] REV 119: **REV 119. First clean-up of board, queue and request tree.** (1) All 31 lingering REVIEW tasks belonged to DONE requests or finished graphs (G-004~007 100%; G-003 and G-005 resolved in later rounds), so they were closed as DONE, and all 59 DONE rows were moved with `archive --days 0` to `.aimem/arc
- `2026-11-10 14:20` Claude Code (Taeseok's instruction) [handoff] REV 118: **REV 118. Detail views reachable from all three monitor tabs.** Places that had no detail: idle slot rows, board rows without a run (Manager's own work), the queue, graph nodes (tasks), request subtasks without a run, past Manager sessions, and **the handoff log was not on screen at all** (the "log
- `2026-11-10 13:50` Claude Code (Taeseok's instruction) [handoff] REV 117: **REV 117. Five monitor design-vs-function checks + shared CA and Windows proxy.** (1) For closed requests (DONE/REJECTED) the request status decides progress and ETA (`reader._estimate`, front end shows "closed") - 10 DONE requests had shown 0~90% progress and remaining ETA. The `REVIEW` closing ru
- `2026-11-10 11:40` Claude Code (Taeseok's instruction, fleet stopped) [handoff] REV 116: **REV 116. Direct monitor UI work + clearing handled items.** (1) UI: numbered titles → bullets, type scale 15/14/13/12, width 1680 + fixed request sidebar, underline tabs with counts, Manager session line (`/api/state.managers`, 30-second background cache), per-slot "now", 20 runs + more + report b
- `2026-11-10 10:40` Manager (R6) [handoff] REV 115: **REV 115. Four slots back + `fleet_graph` cut down three times + tab UI.** (1) **S2 (codex, kistillm) returned.** KISTI recovered in the morning (smoke 28 s), test-path ownership reverted S4→**S2**, and `tests/test_fleet*.py` was **registered** as S2-owned (Taeseok approved in the R6 brief → `Secti

## 4.5 대기 큐

| 순서 | 태스크 | 후보 슬롯 | 비고 |
| --- | --- | --- | --- |

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
| `.aimem/handoff.md` | 관리자 | 핸드오프 로그의 생성물(최신 12건). 정본은 DB events - 손으로 고치지 않는다, handoff add/render 가 덮는다 (REV 132) |
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
| `projects/**` | 관리자 | 프로젝트 결과물 projects/<이름>/ - 여러 라운드에 걸쳐 쌓임 (REV 142). 관리자가 하위 경로를 슬롯에 배정 |
| `rounds/**` | 관리자 | 라운드 기록 폴더 rounds/R<N>/ - brief.md·REPORT.md 만 (결과물은 projects/) |
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
