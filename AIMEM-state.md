# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)

- 정본은 `.aimem/aimem.db` 입니다. 이 파일을 손으로 고치지 마십시오. 생성 2026-11-10T11:32:22 / REV 116

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
| T-036 | 20261109-170155-582a | 웹 UI 데이터 계층 - AIMEM/runs 파싱 + ETA 추정 | S1 | REVIEW | `tools/aimem_monitor/reader.py` |
| T-037 | 20261109-170155-582a | 웹 UI 계약 테스트 (`collect()` 스키마·진행율·ETA) | S2 | REVIEW | `tests/test_aimem_monitor.py` |
| T-038 | 20261109-170155-582a | 웹 UI 정적 프런트엔드 (대시보드·요청 폼·분담 트리) | S3 | DONE | `tools/aimem_monitor/static/**` |
| T-040 | 20261109-170155-582a | 통합·교차검수 (만든 슬롯이 아닌 슬롯이 검수) | S1 | REVIEW | 그래프 노드 `R-002/N5`. T-045 로 실행 |
| T-041 | 20261109-171508-ce9f | 웹 UI 밝은 모드 기본 + 색 토큰 `:root` 이관 + 어두운 모드 토글 | S3 | DONE | `static/style.css`·`index.html`·`app.js` (`R-002/N3`) |
| T-042 | 20261109-171508-ce9f | 웹 UI 가독성·정렬 (열 정렬·고정폭·말줄임+툴팁·카드 위계) | S3 | DONE | 요청 `ce9f`. 같은 화면이라 T-041 과 한 노드 |
| T-043 | 20261109-170155-582a | ETA 초과 처리 (`_estimate` 가 0 으로 바닥치던 것) | S1 | REVIEW | `reader.py` `eta_over` (`R-002/N1`) |
| T-044 | - | 린터 보드 담당 `관리자`/`미배정` 허용 | S1 | REVIEW | `tools/aimem_lint.py` (`R-002/N2`) |
| T-045 | 20261109-171508-ce9f | 계약 테스트 보강 (ETA 초과 · `kisti`/`graphs` · 보드 슬롯) | S2 | REVIEW | `tests/test_aimem_monitor.py`·`test_aimem_lint.py` (`R-002/N4`) |
| T-046 | 20261109-170155-582a | KISTI LLM 서버 상태를 `/api/state` 에 (10초 캐시, 키 비노출) | 관리자 | DONE | `server.py` `kisti_status()` / `collect_graphs()` |
| T-047 | 20261109-172326-c5c1 | 모니터 UI 를 Strata 토큰(`--st-*`)으로 재스킨 | S3 | DONE | 요청 `c5c1`. 그래프 노드 `R-002/N6` |
| T-048 | 20261109-172326-c5c1 | Strata 교차검수 - 대비비 재측정 + 하드코딩 hex + DOM id 보존 (S4 가 T-047 검수로 이미 수행) | S4 | DONE | 결과는 4.5 큐 10·11번(라이트 accent 2.54:1 / 진행막대 2.37:1 / 원본 토큰 4.136:1). 중복 검수를 띄우지 않고 그 보고로 갈음 (REV 114) |
| T-049 | - | **관리자 코드 적대적 검수** (`server.py` kisti/graphs). 읽기 전용 | S4 | DONE | 관리자 자기채점을 깨는 첫 사례. `8.0-1` 을 관리자에게도 적용 |
| T-050 | 20261109-173900-8d8d | 상세 조회 데이터 계층 (`reader.run_detail()` 16키 계약) | S1 | REVIEW | 요청 8d8d. `reader.py`, run `…174829-S1` |
| T-051 | 20261109-173900-8d8d | `GET /api/runs/<id>` 라우팅 + 빈 요청자 400 거절 | 관리자 | DONE | 요청 8d8d. `server.py`. 404/400 재현 확인 |
| T-052 | 20261109-173900-8d8d | 상세 조회 계약 테스트 (16키·경로탈출·404/400·결함 회귀) | S2 | REVIEW | `tests/test_aimem_monitor_detail.py` |
| T-053 | 20261109-173900-8d8d | 상세 패널 + id 열 + lost 배지 + 요청자 기본값 | S3 | DONE | 요청 8d8d·cf63·c87c. 1차 유실 후 2차 `…175955-S3` |
| T-054 | 20261109-173900-8d8d | 상세 조회 UI 교차검수 (읽기 전용). S4 가 바빠 S1 에 배정 | S1 | DONE | S1 교차검수. 결함 7건 - F2(상세 paths 절대경로)는 관리자가 R5 에서 고침, 나머지 5건은 4.5 큐 18~22번 |
| T-055 | - | ETA 표본 결함 2건 (중복 `eta_over` · 스모크가 중앙값 끌어내림) | S1 | REVIEW | `4.5` 큐 4·5번. opencode 중앙값 458→841s |
| T-056 | 20261109-175025-cf63 | 관리자 `server.py` 결함 5건 수정 (그래프 파싱·리다이렉트·블로킹·stampede·실패분기 키) | 관리자 | DONE | 동시10=외부1, 요청경로 0.010s |
| T-057 | 20261109-175208-c87c | `fleet_graph` 결함 3건 수정 (슬롯 바쁨·고아 스폰·원자적 저장) | 관리자 | DONE | S4 적대적 검수 근거. 남은 3건은 `4.5` 큐 |
| T-058 | 20261109-175208-c87c | lost 실행 경과 고정 (`.lost` 마커 / 마지막 mtime) | S1 | REVIEW | 요청 c87c. `reader.py`, run `…180013-S1` |
| T-059 | - | 관리자 수정분 적대적 재검수 (읽기 전용) | S4 | DONE | 자기채점 금지 `8.0-1` |
| T-060 | - | 린터를 2단계(DB 정본)로 - 상태 표 검사 제거 + `STATE_*` 5종 신설 | S1 | REVIEW | `tools/aimem_lint.py` 709->454줄. `lint_repo()` 신설 |
| T-061 | - | 린터 2단계 테스트 갈아끼우기 (71건 폐기, 새 계약 덮기) | S2 | REVIEW | `tests/test_aimem_lint.py` 98->73건. 전체 106건 OK |
| T-062 | 20261109-190205-407b | 로그인 화면 (자족 HTML, 외부자원 0, 토큰 저장 금지) | S3 | DONE | 요청 `407b`. `static/login.html` 138줄, 대비 4.95~16.5:1 |
| T-063 | 20261109-190205-407b | 공개 전 정보유출 적대적 검수 (읽기 전용) | S4 | DONE | 요청 `407b`. 결함 7건 - 2·5·6번은 관리자가 수정, 나머지 큐 |
| T-064 | 20261109-180055-b125 | `reader` 슬롯별 모델 + 비밀 가림 + 심볼릭 링크 차단 | S1 | REVIEW | 요청 `b125` 완료(S1 opus/S4 sonnet 실측). `reader.py` |
| T-065 | 20261109-190205-407b | 인증·TLS 구현 적대적 검수 (읽기 전용) | S4 | DONE | 요청 `407b`. 관리자 자기채점 금지 `8.0-1` - 결함 9건(TLS DoS 포함) 재현 - 관리자가 7건 수정 |
| T-066 | 20261109-190205-407b | **서버 TLS + 접근 제어** (ssl / 토큰 / 세션쿠키 / 면제경로 / 보안헤더 / CSRF) | 관리자 | REVIEW | 요청 `407b`. `server.py` +400줄. curl 검증 전항 통과 |
| T-067 | 20261109-190205-407b | 인증·TLS 계약 테스트 (`test_aimem_monitor_auth.py`) | S2 | REVIEW | 요청 `407b`. 18개 항목 브리프 - 55+3건. **관리자 CSRF 들여쓰기 결함을 테스트가 잡았다** |
| T-068 | 20261109-190205-407b | 인증서 생성·크롬 설치·`netsh portproxy` 절차 | 관리자 | DONE | 요청 `407b`. `README.md` + `.gitignore` `.aimem/tls/` |
| T-069 | - | reader.collect() 를 DB 정본으로 (운영 상태 마크다운 파싱 폐기) | S1 | REVIEW | tools/aimem_monitor/reader.py (collect 가 aimem_db.state_dict() 를 읽음, 마크다운 폴백 유지). a1 성공분을 a2 가 재확인 |
| T-070 | - | fleet.py roster/owned_paths/read_rev/board_rows 를 DB 우선·마크다운 폴백으로 | 관리자 | REVIEW | tools/fleet.py db_state(5초 TTL·실패 비캐시·sys.path 보정)/roster/owned_paths/read_rev/board_rows/path_allowed/_roster_miss |
| T-071 | - | aimem_board.py 를 aimem_db.py 위임으로 (마크다운 쓰기 폐기) | S1 | REVIEW | tools/aimem_board.py 644->795줄. board-* 는 DB 위임, 나머지 6개는 rc 2 폐기 |
| T-072 | - | AIMEM.md 2·3·4·4.5·6절 표 제거 + 아카이브 + 포인터 (린터 STATE_TABLE_IN_AIMEM 0건) | 관리자 | REVIEW | AIMEM.md 772->705줄. 표 4개 제거, 원문은 retired-sections-2026-11.md. 린터 STATE_TABLE_IN_AIMEM 4->0 |
| T-073 | - | 2단계 계약 테스트 (reader 가 DB 를 읽는다 / 표 없는 AIMEM.md 에서도 돈다) | S4 | REVIEW | tests/test_aimem_monitor_state.py 11건 |
| T-074 | 20261109-190205-407b | 공개면 2차 프런트 (토큰 열 제거·root/kisti.url 비의존) | S3 | DONE | static/app.js 확인토큰 열 제거 + DEMO token 제거 (S3 EXAONE 1차 성공) |
| T-075 | 20261109-190205-407b | /api/state 에서 slots[].token·root·kisti.url 제거 + 요청 생성 분당 제한 | 관리자 | REVIEW | server.py scrub_public()+mask_deep()+RequestRateLimiter(+실패 버킷). 상세 엔드포인트까지 가림. __init__.py PUBLIC_FORBIDDEN/REQUEST_RATE_*/REQUEST_FAIL_MAX |
| T-076 | 20261109-190205-407b | 공개면 2차 계약 테스트 (token/root/kisti.url 부재 · 분당 제한 · S4 검수 5·6번 재검수) | S4 | REVIEW | tests/test_aimem_monitor.py 18->32건 |
| T-077 | - | reader 의 log 를 when 내림차순으로 (events.seq 순서가 시간순이 아닐 수 있다) | S1 | REVIEW | reader 의 log 를 when 내림차순으로 (S4 테스트가 잡은 브리프 모순) |
| T-078 | - | R5 관리자 수정분 적대적 검수 (scrub_public·속도제한·queue CLI·fleet DB) 읽기전용 | S4 | DONE | S4 적대적 검수. 결함 9건 - 관리자가 7건 수정·재현, 2건(폴백 사문화 주석·path_allowed)도 수정. 남은 테스트는 큐 23번 |
| T-079 | - | 속도 제한 계약 변경(allow 가 센다 · refund · 실패 버킷) 테스트 정합 | S4 | REVIEW | tests/test_aimem_monitor.py 32->38건. 동시 20스레드에 allow 통과 정확히 5건 |
| T-080 | - | `fleet.py` DB 우선·마크다운 폴백 회귀 테스트 (큐 15·23) | S2 | REVIEW | tests/test_fleet.py |
| T-081 | - | `fleet_graph` 단일 실행자 잠금 · 노드 타임아웃 · 보고 BLOCKED 파싱 (큐 7·8·9) | S1 | REVIEW | tools/fleet_graph.py |
| T-082 | - | 상세 패널 진입점 - 보드 행·요청 서브태스크 클릭 + 404/400 이유 표시 + DEMO_STATE 정리 (큐 18·19·21) | S3 | DONE | tools/aimem_monitor/static/app.js |
| T-083 | - | KISTI 카드 pending/stale 구분 + 상세 다이얼로그 포커스 가둠·복귀 (큐 20·22) | S3 | DONE | tools/aimem_monitor/static/app.js |
| T-084 | - | T-081 적대적 검수 (읽기 전용) - 잠금·타임아웃·BLOCKED 판정 | S4 | DONE | 보고 본문 |
| T-085 | - | `requests[].detail` 절단 + 토큰 파일 O_NOFOLLOW 읽기 계약 테스트 | S2 | REVIEW | tests/test_aimem_monitor*.py |
| T-086 | - | `/api/state` requests[].detail 절단 + 접근 토큰 읽기 O_NOFOLLOW (큐 13·3) | 관리자 | DONE | server.py `_truncate_request_details`/`load_access_token`, `__init__.py` `REQUEST_DETAIL_MAX` |
| T-087 | Q-261110-7201 | fleet_graph S4 검수 결함 5건 수정 (killpg·pid 신원·단어경계·timeout 범위·validate 범위) | S1 | REVIEW | tools/fleet_graph.py |
| T-088 | - | `fleet_graph` 계약 테스트 (잠금·BLOCKED 판정·타임아웃·시작 전 검증) | S2 | REVIEW | tests/test_fleet_graph.py (21건). 1차는 계약 오류로 BLOCKED - T-093 이 해소 |
| T-089 | Q-261110-549a | 모니터 UI 탭 구조 (함대 / 보드·큐 / 요청 트리, 요청 폼은 상시) | S3 | DONE | EXAONE 2회 실패(app.js 42KB 완독). T-094 로 좁혀 재배정해 해소 |
| T-090 | - | T-087 재검수 + 새 구멍 탐색 (읽기 전용) | S4 | DONE | 보고 본문 |
| T-091 | Q-261110-549a | 요청 본문 줄바꿈 유지 + 잘린 본문 전체 보기 | S3 | DONE | static/app.js·style.css |
| T-092 | - | fleet_graph 재검수 결함 7·8 수정 (refused 시 blocked · tz astimezone) | S1 | REVIEW | tools/fleet_graph.py |
| T-093 | - | test_fleet_graph 계약 표 1행 정정 + 경계 2행 추가 | S2 | REVIEW | tests/test_fleet_graph.py |
| T-094 | Q-261110-549a | 모니터 UI 탭 구조 (3차 - 읽을 것을 못박은 좁힌 브리프) | S3 | DONE | static/index.html·app.js·style.css |
| T-095 | - | T-092 3차 검수 + 테스트 커버리지 표 (읽기 전용) | S4 | DONE | 보고 본문 |

## 4. 이벤트 로그 (최신 50)

- `2026-11-10T11:22:56` 웹(웹) [fleet-mode] REV 116: running -> paused (일시 중지) 새 작업자 투입 보류, 돌고 있는 작업자는 끝까지
- `2026-11-10T11:22:48` 웹(웹) [fleet-mode] REV 116: paused -> running (실행) 진행 중 라운드 재개
- `2026-11-10T11:21:31` 클로드 코드(태석 10:35 일시 중지 지시) [fleet-mode] REV 116: running -> paused (일시 중지) 새 작업자 투입 보류, 돌고 있는 작업자는 끝까지
- `2026-11-10 11:40` 관리자 [handoff] REV 116: - `2026-11-10 11:40` 클로드 코드(태석님 지시, 함대 정지 중): **REV 116. 모니터 UI 직접 정비 + 처리한 항목 정리.** (1) UI: 제목 번호→불릿, 글자 체계 15/14/13/12, 폭 1680 + 작업 요청 고정 사이드바, 밑줄 탭·건수, 관리자 세션 줄(`/api/state.managers`, 30초 배경 캐시), 슬롯별 '지금', 실행 20건+더 보기+보고 배지, 보드 '최근 실행' 열·필터, 끝난·멈춘 그래프와 DONE 요청 접기, 요청 본문 4줄 접기·전문 조회(`GET /api/requ
- `2026-11-10T11:02:48` 클로드 코드(태석 지시) [cleanup] REV 116: REV 116: 모니터 UI 직접 정비 + 큐 6건·요청 3건·화면 태스크 11건·그래프 R-002 정리, aimem_db archive 구현
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-094 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-091 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-083 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-082 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-074 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-062 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-053 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-047 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-042 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-041 DONE
- `2026-11-10T11:02:22` 클로드 코드(태석 지시 2026-11-10, 브라우저 실측 검수) [task] REV 115: T-038 DONE
- `2026-11-10T11:02:09` 클로드 코드(태석 지시 2026-11-10) [request] REV 115: Q-261110-549a DONE
- `2026-11-10T11:02:09` 클로드 코드(태석 지시 2026-11-10) [request] REV 115: Q-261110-7201 DONE
- `2026-11-10T11:02:09` 클로드 코드(태석 지시 2026-11-10) [request] REV 115: 20261109-173900-8d8d DONE
- `2026-11-10T11:01:53` 클로드 코드(태석 지시) [queue] REV 115: queue -2 쿠키 로그인 흐름 브라우저 확인 (Playwright)
- `2026-11-10T11:01:53` 클로드 코드(태석 지시) [queue] REV 115: queue -5 밝은 모드 스크린샷 검증 (Playwright)
- `2026-11-10T11:01:53` 클로드 코드(태석 지시) [queue] REV 115: queue -6 라이트 모드 `--st-accent-ink`(#fff) on `--st-accent` = **2.54:1**
- `2026-11-10T11:01:53` 클로드 코드(태석 지시) [queue] REV 115: queue -7 참조 토큰 원본 `.aimem/briefs/strata-tokens.css` 의 `--st-accent-text` 가 틀렸다
- `2026-11-10T11:01:52` 클로드 코드(태석 지시) [queue] REV 115: queue -12 DONE 태스크 14일 아카이브 도구 (`aimem_db.py archive` - 보드 → `.aimem/archive/board-<YYYY-MM>.md`)
- `2026-11-10T11:01:52` 클로드 코드(태석 지시) [queue] REV 115: queue -13 요청 분담 트리에서 `DONE` 요청·태스크를 기본 접힘으로
- `2026-11-10T10:41:53` 관리자(R6) [ownership] REV 115: tools/fleet_graph.py -> 관리자
- `2026-11-10 10:40` 관리자 [handoff] REV 115: - `2026-11-10 10:40` 관리자(R6): **REV 115. 네 슬롯 복귀 + `fleet_graph` 를 세 번 깎아 냄 + 탭 UI.** (1) **S2(codex·kistillm) 복귀.** KISTI 가 아침에 정상화돼(스모크 28초) 테스트 경로 소유권을 S4→**S2** 로 환원했고, `tests/test_fleet*.py` 를 S2 소유로 **등재**했다(태석님 R6 브리프 승인 → `9절` 2번 해소). **함대 생명선에 테스트가 생겼다** - `fleet.py` 의 DB 우선·마크다운 폴백 10건(T-0
- `2026-11-10T10:41:23` 관리자(R6) [handoff] REV 115: `2026-11-10 10:40` 관리자(R6): **REV 115.** 네 슬롯 복귀(S2 codex 환원) + `fleet_graph` 잠금·타임아웃·BLOCKED 판정을 넣고 S4 가 3회 적대 검수(결함 10건 → 7건 수정) + 상세 패널 마무리 + 탭 UI(Q-549a) + 유료 모델 대체 금지 정책(Q-7201) + `requests[].detail` 절단·토큰 `O_NOFOLLOW`. 작업자 16건 5,219초. 테스트 195→238. 커밋하지 않음.
- `2026-11-10T10:41:23` 관리자(R6) [request] REV 114: Q-261110-7201 DONE
- `2026-11-10T10:41:23` 관리자(R6) [task] REV 114: T-088 REVIEW
- `2026-11-10T10:41:23` 관리자(R6) [task] REV 114: T-089 DONE
- `2026-11-10T10:41:23` 관리자(R6) [task] REV 114: T-095 DONE
- `2026-11-10T10:41:23` 관리자(R6) [task] REV 114: T-090 DONE
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-086 DONE
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-084 DONE
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-094 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-093 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-092 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-091 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-087 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-085 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-083 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-082 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-081 REVIEW
- `2026-11-10T10:41:22` 관리자(R6) [task] REV 114: T-080 REVIEW
- `2026-11-10T10:40:39` 관리자(R6) [queue] REV 114: queue +20 `tests/test_fleet_graph.py` 커버리지 구멍 - 결함 1·2·7·8·10 을 막는 테스트가 없다
- `2026-11-10T10:40:39` 관리자(R6) [queue] REV 114: queue +19 `report_block_reason` 소문자 평문 거짓 양성 (`blocked: none`·`reject: no`·`needs-review: none`)
- `2026-11-10T10:40:39` 관리자(R6) [queue] REV 114: queue +18 `fleet_graph.harness_durations()` - 깨진 run 메타(`pid` 가 문자열) 하나로 `progress`/`status`/`list` 가 TypeError
- `2026-11-10T10:40:39` 관리자(R6) [queue] REV 114: queue +17 `fleet_graph` 결함 11 - `refused` 로 `blocked` 가 된 노드를 아무도 거두지 않는다 (`unblock`/`reset` 명령 없음)
- `2026-11-10T10:22:35` 관리자(R6) [queue] REV 114: queue +16 `aimem_monitor` HTTP 테스트가 샌드박스(codex/S2)에서 소켓 금지로 22건 error - TCP 불가 시 폴백 `PipeConnection` 에 `settimeout` 없음
- `2026-11-09 21:50` 관리자 [handoff] REV 114: - `2026-11-09 21:50` 관리자(R5): **REV 114. DB 2단계 완료 + 공개면 2차.** (1) **운영 상태 표 4개를 내렸다**(2·3·4.5·6절, 772→705줄). 순서를 지켰다 - `reader`(T-069,S1)·`fleet.py`(T-070,관리자)·`aimem_board`(T-071,S1)가 DB 를 읽게 된 **뒤에** 내렸고 원문은 `retired-sections-2026-11.md` 로 먼저 옮겼다. **린터 `STATE_TABLE_IN_AIMEM` 4→0, rc 0**(완료 판정). 큐
- `2026-11-09T21:48:23` 관리자(R5) [handoff] REV 114: REV 114: DB 2단계 완료(AIMEM.md 상태 표 4개 제거, 린터 STATE_TABLE_IN_AIMEM 4->0) + 공개면 2차(root/token/kisti.url 키·값 제거, 요청 분당 제한). 자세한 것은 AIMEM.md 4절.
- `2026-11-09T19:42:03` 관리자(R4) [handoff] REV 113: REV 113: 외부 공개(HTTPS+접근제어) + 린터 2단계. 자세한 것은 AIMEM.md 4절.
- `2026-11-09 19:45` 관리자 [handoff] REV 113: - `2026-11-09 19:45` 관리자(R4): **REV 113. 외부 공개(HTTPS+접근제어) 구현 + 린터 2단계 전환.** (1) **요청 `407b` 공개:** `server.py` 에 TLS(`--tls`, 자체 인증서 `.aimem/tls/`)와 접근 제어(32바이트 토큰 → hmac 서명 세션 쿠키 `HttpOnly;Secure;SameSite=Strict`, Bearer 병행, 면제 7경로, 실패 지연, HSTS·CSP·nosniff, CSRF(Content-Type+Origin), 본문 64KB, 요청파일 
- `2026-11-09 19:01` 관리자 [handoff] REV 112: - `2026-11-09 19:01` 관리자: 클로드 코드(태석님 승인 2026-11-09 18:20, 관리자·작업자 정지 중 적용): **REV 112. 식별자 체계 통일 (`8.0-5` 신설).** 요청 `Q-<YYMMDD>-<4자>` / 태스크 `T-0xx` / 그래프 `G-00x` / 실행 `<T>-<S#>-a<n>-<HHMMSS>` / 라운드 `R<n>` 은 기록 전용. `fleet.py spawn --task-id/--attempt` 가 실행 id·라벨을 만들고, `fleet_graph.py` 가 노드 id(=태스크 id
- `2026-11-09 18:05` 관리자 [handoff] REV 111: - `2026-11-09 18:05` 관리자(R3): **REV 111 (2/2). R2 가 턴을 끝내 끊긴 라운드를 이어받고 웹 요청 `8d8d` 를 분담.** **왜 끊겼나:** R2 는 백그라운드 감시를 걸고 "알림이 오면 잇겠다"며 턴을 끝냈다 - **일회성 ACP 세션은 다시 깨어나지 않는다.** 규칙을 `8.0-6` 에 박았다. (1) **S4 적대적 검수가 관리자 코드에서 결함 5건**(그래프 노드 한 줄이 `/api/state`+`/api/health` 를 무응답으로 끊음 / 302 리다이렉트에 `Bearer` 키가 
- `2026-11-09 17:35` 관리자 [handoff] REV 111: - `2026-11-09 17:35` 관리자(R2): **REV 111 (1/2). 태스크 DAG 로 라운드를 돌린 첫 사례 + 웹 요청 2건 분담.** 그래프 `R-002` 6노드(N1 ETA초과 / N2 린터 보드슬롯 / N3 밝은모드+가독성 / N4 테스트보강 / N5 교차검수 / N6 Strata 재스킨). **의존이 풀리면 관리자 턴 없이 다음이 뜬다** - N1 이 17:24:46 에 끝나자 같은 초에 N2 가 떴다. **유실을 루프가 거둔다** - N3 1차가 `lost` 되자 같은 초에 2차를 띄웠고 직전 run id
- `2026-11-09 17:10` 관리자 [handoff] REV 110: - `2026-11-09 17:10` 관리자: **REV 110. 함대 모니터링 웹 UI 1차 (태석님 주문 2026-11-09).** Claude ACP 관리자 체제의 첫 실전 라운드. `6절` 에 `tools/aimem_monitor/**`·`tests/test_aimem_monitor*.py`·`.aimem/requests/**` 7행 등재(태석님 승인, `6.1`). **계약을 관리자가 못박고**(`__init__.py` 의 `STATE_KEYS`/`PROGRESS_WEIGHTS`) 의존 없는 3건을 **한 턴에 병렬 spa
- `2026-11-09 16:40` 관리자 [handoff] REV 109: - `2026-11-09 16:40` 관리자: 클로드 코드(태석님 지시 2026-11-09, 관리자 세션 아님): **REV 109. 관리자를 Opus 5.5 Claude ACP 세션으로, 작업자를 하네스 CLI 일회성 프로세스로.** (1) 서문·`0.5`·`2절`·`5절`·`7절`·`8.0` 개정 - 관리자 식별은 세션키 접두사 `agent:claude:acp:`(린터 핀 교체, `tools/aimem_lint.py`·테스트 픽스처 갱신), 구 관리자 클로는 읽기만. (2) `tools/fleet.py` 에 `spawn / ru

## 4.5 대기 큐

| 순서 | 태스크 | 후보 슬롯 | 비고 |
| --- | --- | --- | --- |
| 1 | `.aimem/runs/<id>.json`·`.rc` 에도 심볼릭 링크 검사 | S1 | T-064 가 `brief`/`out`/`err` 만 막았다. 메타 파일이 링크면 `slot`/`label`/`model` 문자열이 응답에 실린다 (S1 보고 ④) |
| 2 | 요청 -> 서브태스크 분담을 관리자 CLI 로 (`fleet.py request` 또는 `fleet_graph` 와 요청 파일 연결) | 관리자 | 지금은 요청 파일을 손으로 고쳐야 분담이 보인다. REV 111 에서 `graph`/`graph_node` 필드를 손으로 넣었다 |
| 3 | 그래프 노드 <-> 요청 서브태스크 자동 동기화 | 관리자 | `8.0-5` 채택 결과. `fleet_graph` 가 노드 상태를 바꿀 때 `.aimem/requests/*.json` 의 같은 `graph_node` 행도 갱신하면 손 갱신이 사라진다 |
| 4 | 작업자 허용목록 - 브리프가 `PYTHONPATH=... python3` 로 시작하면 아직 막힌다 | 관리자 | 16:51 수정은 `Bash(python3:*)` 접두사 매칭이라 **명령 첫 낱말이 `python3` 여야** 한다. 11-09 17:33 제3 세션 브리프가 그걸 몰라 작업자가 검증을 한 줄도 못 돌렸다. `fleet.py spawn` 이 브리프의 검증 명령을 점검해 경고하거나, 허용목록에 `Bash(PYTHONPATH=*)` 를 더할 것 |
| 5 | `serve()` 가 `Handler.rate` 를 묶는지 보는 테스트 | S4 | S4 보고. 지금 테스트는 제한기를 직접 묶은 핸들러를 쓰므로 `serve()` 에서 `rate` 배선을 빼도 안 잡힌다. `serve(once=True)` 를 띄워 6번째 POST 가 429 인지 보면 된다 |
| 6 | `aimem_board.py` 의 `--file` 마크다운 경로 폐기 여부 결정 | 관리자 | T-071 이 `AIMEM.md` 쓰기를 끊었으나 `--file <사본>` 으로 임의 마크다운을 옛 방식으로 편집하는 길은 남겼다(`tests/test_aimem_lint.py` 스모크가 그 길을 쓴다). 795줄 중 상당수가 그 경로다 - 테스트를 DB 쪽으로 옮기고 지울지 정할 것 |
| 7 | `state_dict()` 이벤트 합집합 질의와 `migrate` 의 REV 씨앗 규칙 테스트 | S4 | R5 에서 둘 다 실측 결함으로 고쳤다: (a) `LIMIT 50` 이 핸드오프를 밀어내 웹 4절 로그가 2건으로 줄었다 -> 합집합(+핸드오프 12건), (b) `migrate` 가 AIMEM.md 서문에서 REV 를 매번 덮어써 114->113 으로 되돌렸다 -> DB 에 REV 가 없을 때만 씨앗. 회귀 테스트가 없다 |
| 8 | `fleet_graph.step()` - `running` 인데 `attempts` 가 빈 노드에서 `IndexError` | S1 | S4 2차 검수. 손으로 고친 그래프에서 닿는다. 기존 결함 |
| 9 | `fleet.roster()` 마크다운 폴백의 셋째 칸이 세션키가 아니라 **역할** 이다 (docstring 불일치) | S1 | T-080 이 테스트로 현재 동작을 고정하며 발견. 폴백은 표가 없어 사실상 죽은 길이라 영향 없음 - 주석만 고치면 된다 |
| 10 | `aimem_monitor` HTTP 테스트가 샌드박스(codex/S2)에서 소켓 금지로 22건 error - TCP 불가 시 폴백 `PipeConnection` 에 `settimeout` 없음 | S2 | T-085·T-088 보고. 관리자 환경에서는 전부 통과하므로 기준선 판정이 슬롯마다 달라진다 - 작업자가 자기 환경을 기준선으로 오인한다 |
| 11 | `fleet_graph` 결함 11 - `refused` 로 `blocked` 가 된 노드를 아무도 거두지 않는다 (`unblock`/`reset` 명령 없음) | S1 | S4 3차 검수 [중간]. 작업자가 살아 있는 동안 슬롯이 계속 바쁨 → 같은 슬롯 노드가 영영 못 뜬다. 나중에 `.rc` 가 써져도 노드는 blocked 로 남는다 |
| 12 | `fleet_graph.harness_durations()` - 깨진 run 메타(`pid` 가 문자열) 하나로 `progress`/`status`/`list` 가 TypeError | S1 | S4 3차 검수 [낮음]. `_busy_slots` 는 삼키는데 여기는 안 삼킨다 - 같은 호출을 두 곳이 다르게 방어한다 |
| 13 | `report_block_reason` 소문자 평문 거짓 양성 (`blocked: none`·`reject: no`·`needs-review: none`) | S1 | S4 3차 검수 [낮음]. 결함 9 를 고치며 다시 열린 길. `rejected: none` 은 None 인데 `reject: none` 은 상태 - 어미 -ed 유무로 갈린다. 안전한 쪽(사람에게 넘김)이라 낮음 |
| 14 | `tests/test_fleet_graph.py` 커버리지 구멍 - 결함 1·2·7·8·10 을 막는 테스트가 없다 | S2 | S4 3차 검수의 커버리지 표. 특히 `+09:00` 케이스는 `node_timeout_sec=10**9` 라 **옛 구현(tz 그냥 뗌)도 통과한다** - 겉으로는 tz 를 검사하는데 아무것도 검사하지 않는다. `_kill_run` 을 mock 하지 않는 테스트가 하나도 없다 |

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
