# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)

- 정본은 `.aimem/aimem.db` 입니다. 이 파일을 손으로 고치지 마십시오. 생성 2026-11-11T15:32:03 / REV 154

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
| T-096 | Q-261110-0437 | 웹워들 핵심 판정 로직 (game.js) | S1 | DONE |  |
| T-097 | Q-261110-0437 | 웹워들 단어 목록 생성기와 생성물 | S2 | DONE |  |
| T-098 | Q-261110-0437 | 웹워들 화면 (보드·키보드·통계) | S4 | DONE |  |
| T-099 | Q-261110-0437 | 웹워들 로직 테스트 (다른 슬롯이 검증) | S3 | DONE |  |
| T-100 | Q-261110-0437 | 웹워들 통합 연기 테스트 + 적대적 검수 | S1 | DONE |  |
| T-101 | Q-261110-0437 | 웹워들 화면 결함 7건 수정 (검수) | S4 | DONE |  |
| T-102 | Q-261110-0437 | 웹워들 fromJSON 손상 저장값 방어 (검수) | S1 | DONE |  |
| T-103 | Q-261110-0437 | 웹워들 수정 재검수 + 회귀 테스트 | S1 | DONE |  |
| T-104 | Q-261110-0437 | 웹워들 남은 결함 3건 (키보드 접근성·연승·모달 높이) | S4 | DONE |  |
| T-105 | Q-261110-c450 | 웹워들 브라우저 검증 1: 공용 하네스 + 보드·키보드·없는 단어·판 끝 | S2 | DONE | projects/웹워들/tests/browser_harness.py, projects/웹워들/tests/browser_core.py |
| T-106 | Q-261110-c450 | 웹워들 브라우저 검증 2: 좁은 폭(360px)·낮은 창 레이아웃 | S3 | DONE | projects/웹워들/tests/browser_layout.py |
| T-107 | Q-261110-c450 | 웹워들 브라우저 검증 3: 통계·공유·테마·접근성·도움말 | S2 | DONE | projects/웹워들/tests/browser_ui.py |
| T-108 | Q-261110-c450 | 웹워들 브라우저 검증 적대적 검수 + tests/README.md | S1 | DONE | projects/웹워들/tests/README.md |
| T-109 | Q-261110-c450 | browser_core.py find_present_pair 수정 (present+correct 겹침) | S3 | DONE | projects/웹워들/tests/browser_core.py |
| T-110 | Q-261110-c450 | 웹워들 화면 결함 3건: hidden 무력화·짧은 창 키보드 넘침·토스트가 타일 가림 | S2 | DONE |  |
| T-111 | Q-261110-c450 | browser_ui.py: 보이는지로 검사 + 테마는 body 배경으로 | S2 | DONE |  |
| T-112 | Q-261110-c450 | browser_core.py: 토스트가 타일을 가리지 않는지 검사 추가 | S3 | DONE |  |
| T-113 | Q-261110-c450 | T-110 이 떨어뜨린 dvh 의 vh 대비 복구 + 불변식 테스트로 재작성 | S3 | DONE | projects/웹워들/web/css/style.css, projects/웹워들/tests/smoke_integration.mjs |
| T-114 | Q-261110-c450 | 글자를 치면 보드가 커져 낮은 창에서 키보드가 밀려남 + 검사 순서 구멍 | S3 | DONE | projects/웹워들/web/css/style.css, projects/웹워들/tests/browser_layout.py |
| T-115 | Q-261111-f77f | browser_harness: shot() 뷰포트 스크린샷 선택지 | S2 | DONE |  |
| T-116 | Q-261111-f77f | browser_ui: 통계 목표 구멍 메우기 (서로 다른 네 값·진 판·끝난 판 새로 고침) | S2 | DONE |  |
| T-117 | Q-261111-f77f | browser_ui: 보기 설정(색약 present 파랑·저장)과 접근성(대비 전면·어두움+색약·키보드 완주·aria-live) | S2 | DONE |  |
| T-118 | Q-261111-f77f | browser_core: 뒤집기 애니메이션 실측·화면 ENTER/⌫ 누르기·키 색 안 내려감 | S2 | DONE |  |
| T-119 | Q-261111-f77f | 웹워들 목표 넷 적대적 검수 + tests/README.md 갱신 | S1 | DONE |  |
| T-120 | Q-261111-f77f | browser_ui 새 검사 둘의 결함 수정 (공유 단추는 창 안·busy 빈틈) | S2 | DONE |  |
| T-121 | Q-261111-f77f | browser_core: 뒤집기를 animationstart 로 진짜 증명 + 빈 all()·0.5s 박기 제거 | S2 | DONE |  |
| T-122 | Q-261111-f77f | browser_ui: n번째 줄 승리 분포·통계 이름표·색약 hue·새로 고침 뒤 칠해진 색 | S2 | DONE |  |
| T-123 | Q-261111-f77f | 보드·통계·보기 설정 재검수 + tests/README.md 갱신 | S1 | DONE |  |
| T-124 | Q-261111-f77f | browser_core: animationstart 기록에서 pop 거르기 + 옛 검사 이름 정직하게 | S2 | DONE |  |
| T-125 | Q-261111-f77f | 보드 목표 최종 확인 + tests/README.md 마무리 | S1 | DONE |  |
| T-126 | Q-261111-5593 | 모니터: /app/<프로젝트>/ 정적 실행 경로 + app.json 선언 + 단위 시험 | S2 | DONE |  |
| T-127 | Q-261111-5593 | 모니터 화면: 프로젝트 칸의 '실행' 단추 + 격리 iframe 패널 (sw v12) | S2 | DONE |  |
| T-128 | Q-261111-5593 | 브라우저 검증 스크립트 tests/browser_monitor_app.py | S2 | BLOCKED |  |
| T-129 | Q-261111-5593 | 웹워들: app.json 선언 + README 실행 안내 | S3 | DONE |  |
| T-130 | Q-261111-5593 | 적대적 검수: 경로 탈출·인증·CSP/sandbox·증거의 진위 | S1 | BLOCKED |  |
| T-131 | Q-261111-5593 | 브라우저 실측 A: /app/웹워들/ 이 그려지는가 (8개) | S3 | DONE |  |
| T-132 | Q-261111-5593 | 브라우저 실측 B: 모니터 '실행' → 격리 iframe 안에 결과물 (6개) | S2 | DONE |  |
| T-133 | Q-261111-5593 | 적대적 검수: 경로 탈출·인증·CSP/sandbox·변이 시험 | S1 | DONE |  |
| T-134 | Q-261111-5593 | 검수 결함 1~4 수정: /app/ 경로 티켓 + ACAO null + CSP sandbox + 패널 높이 | S2 | DONE |  |
| T-135 | Q-261111-5593 | 브라우저 실측 C: 인증을 켠 채로 미리보기가 뜨는가 (6개) | S3 | DONE |  |

## 4. 이벤트 로그 (최신 50)

- `2026-11-11 15:32` 클로드 코드 [handoff] REV 154: **REV 154. 무료 작업자가 빈손으로 끝나던 원인 셋을 찾아 고쳤다 (R10 결과물과 함께 커밋).** (1) S2 codex+kistillm 이 도구 호출을 글자로 찍고 끝나던 것: codex 가 내주는 도구에 `update_plan`·`apply_patch` 가 없는데 `~/.codex/models-kisti.json` 기본 지시문이 그것을 쓰라고 했다(실패 7건 전부 이 둘). 지시문에서 계획 도구 절을 빼고 편집은 `exec_command` 로 `apply_patch` heredoc 을 돌리라고 고쳤다 - 같은 과제 실
- `2026-11-11 08:13` 관리자 R10 [handoff] REV 153: **REV 153. 함대 모니터 웹에서 프로젝트 결과물을 바로 돌릴 수 있게 됐다** (요청 `Q-261111-5593`, 태석). 프로젝트가 `projects/<이름>/app.json`(`root`·`entry`·`title`) 한 장을 두면 모니터가 그 폴더를 `/app/<이름>/` 로 내려 주고, 프로젝트 칸의 **실행** 단추가 격리된 칸에서 띄운다. 웹워들이 첫 손님(16/16). 그래프 셋·태스크 열(T-126~T-135, 상한 꽉 참). **핵심 교훈 둘.** (1) **S1 적대적 검수가 '이번 라운드의 핵심 기능이 
- `2026-11-11T08:13:23` 관리자 R10 [graph] REV 152: G-021 끝(2/2 done). T-134(S2): /app/ 인가를 세션 쿠키에서 경로 티켓(/app/~<만료>.<hmac32>/<이름>/)으로 바꾸고 ACAO:null + CSP sandbox 지시어를 더해 검수 결함 1·2 를 닫음. 패널 높이(3)·미디어 쿼리 순서(4)도 수정. T-135(S3): 인증 켠 브라우저 검사 6개 신규. 관리자 재현: 단위 456 OK, browser app 8/8 ui 6/6 auth 6/6, 무인증 302, 위조 티켓 403, CSP 헤더 1개.
- `2026-11-11T08:13:23` 관리자 R10 [request] REV 152: Q-261111-5593 DONE
- `2026-11-11T08:13:23` 관리자 R10 [task] REV 152: T-135 DONE
- `2026-11-11T08:13:23` 관리자 R10 [task] REV 152: T-134 DONE
- `2026-11-11T07:40:09` 관리자 R10 [task] REV 152: T-135 ASSIGNED S3 브라우저 실측 C: 인증을 켠 채로 미리보기가 뜨는가 (6개)
- `2026-11-11T07:40:09` 관리자 R10 [task] REV 152: T-134 ASSIGNED S2 검수 결함 1~4 수정: /app/ 경로 티켓 + ACAO null + CSP sandbox + 패널 높이
- `2026-11-11T07:40:09` 관리자 R10 [ownership] REV 152: tests/browser_monitor_auth.py -> S3
- `2026-11-11T07:38:08` 관리자 R10 [graph] REV 152: G-020 끝(3/3 done). S1 적대적 검수(T-133)가 중대 결함 넷을 찾음: (1) sandbox iframe 은 불투명 출처라 type=module 스크립트가 CORS 로 막히고, 인증을 켜면 SameSite=Strict 쿠키가 안 실려 CSS 까지 302 - 미리보기가 실제로는 안 뜬다(관리자 재확인: browser_monitor_ui 4/6). (2) '새 탭'은 같은 출처라 결과물 JS 가 사람의 세션으로 /api/* 를 호출할 수 있다. (3) iframe 이 패널 밖으로 34px 잘린다. (4) 좁은 화면 높
- `2026-11-11T07:38:08` 관리자 R10 [task] REV 152: T-133 DONE
- `2026-11-11T07:38:08` 관리자 R10 [task] REV 152: T-132 DONE
- `2026-11-11T07:38:08` 관리자 R10 [task] REV 152: T-131 DONE
- `2026-11-11T07:06:27` 관리자 R10 [graph] REV 152: G-019 끝: T-126(뒷단 /app/ 경로+단위시험 16개) T-127(화면 실행 단추+sandbox iframe, sw v12) T-129(웹워들 app.json+README) done. T-128(브라우저 실측 스크립트)은 S2(codex)가 두 시도 모두 패치를 글자로만 찍고 파일을 만들지 않아 failed → T-130(S1 검수)이 blocked. 남은 일은 G-020 으로 다시 짬: T-131(S3 결과물 직접 열기 8검사) T-132(S2 모니터 실행 iframe 6검사) T-133(S1 검수).
- `2026-11-11T07:06:27` 관리자 R10 [task] REV 152: T-129 DONE
- `2026-11-11T07:06:27` 관리자 R10 [task] REV 152: T-127 DONE
- `2026-11-11T07:06:27` 관리자 R10 [task] REV 152: T-126 DONE
- `2026-11-11T07:06:27` 관리자 R10 [task] REV 152: T-130 BLOCKED
- `2026-11-11T07:06:27` 관리자 R10 [task] REV 152: T-128 BLOCKED
- `2026-11-11T07:06:19` 관리자 R10 [task] REV 152: T-133 ASSIGNED S1 적대적 검수: 경로 탈출·인증·CSP/sandbox·변이 시험
- `2026-11-11T07:06:19` 관리자 R10 [task] REV 152: T-132 ASSIGNED S2 브라우저 실측 B: 모니터 '실행' → 격리 iframe 안에 결과물 (6개)
- `2026-11-11T07:06:19` 관리자 R10 [task] REV 152: T-131 ASSIGNED S3 브라우저 실측 A: /app/웹워들/ 이 그려지는가 (8개)
- `2026-11-11T07:06:19` 관리자 R10 [ownership] REV 152: tests/browser_monitor_ui.py -> S2
- `2026-11-11T07:06:19` 관리자 R10 [ownership] REV 152: tests/browser_monitor_app.py -> S3
- `2026-11-11T06:24:21` 관리자 R10 [request] REV 152: Q-261111-5593 IN-PROGRESS
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: rounds/R10/REVIEW.md -> S1
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: projects/웹워들/README.md -> S3
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: projects/웹워들/app.json -> S3
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: tests/browser_monitor_app.py -> S2
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: tools/aimem_monitor/static/sw.js -> S2
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: tools/aimem_monitor/static/style.css -> S2
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: tools/aimem_monitor/static/app.js -> S2
- `2026-11-11T06:19:05` 관리자 R10 [ownership] REV 152: tests/test_aimem_monitor_app.py -> S2
- `2026-11-11T06:19:04` 관리자 R10 [ownership] REV 152: tools/aimem_monitor/__init__.py -> S2
- `2026-11-11T06:19:04` 관리자 R10 [ownership] REV 152: tools/aimem_monitor/server.py -> S2
- `2026-11-11T06:18:59` 관리자 R10 [task] REV 152: T-130 ASSIGNED S1 적대적 검수: 경로 탈출·인증·CSP/sandbox·증거의 진위
- `2026-11-11T06:18:59` 관리자 R10 [task] REV 152: T-129 ASSIGNED S3 웹워들: app.json 선언 + README 실행 안내
- `2026-11-11T06:18:59` 관리자 R10 [task] REV 152: T-128 ASSIGNED S2 브라우저 검증 스크립트 tests/browser_monitor_app.py
- `2026-11-11T06:18:59` 관리자 R10 [task] REV 152: T-127 ASSIGNED S2 모니터 화면: 프로젝트 칸의 '실행' 단추 + 격리 iframe 패널 (sw v12)
- `2026-11-11T06:18:59` 관리자 R10 [task] REV 152: T-126 ASSIGNED S2 모니터: /app/<프로젝트>/ 정적 실행 경로 + app.json 선언 + 단위 시험
- `2026-11-11T06:18:54` 관리자 R10 [request] REV 152: Q-261111-5593 PLANNED
- `2026-11-11 05:58` 클로드 코드 [handoff] REV 152: **REV 152. R7~R9 를 지켜보며 찾은 함대 결함을 고쳤다 (웹워들 15/15 완성분과 함께 커밋).** (1) 엔진 `fleet_graph.py`: 보고가 도구 호출 글자로 끝난 시도(`report_ended_in_tool_call`, 로그 `aborted`)와 `write` 경로를 하나도 안 고친 첫 시도(`wrote_nothing`, 로그 `no-op`)는 rc 0·verify 통과여도 실패로 보고 다시 굴린다 - R9 G-014 에서 네 노드 중 셋이 빈손으로 done 이 됐다. (2) 표준 브리프: 만들기·고치기는
- `2026-11-11 04:43` 관리자 [handoff] REV 151: **REV 151. 웹워들을 15/15 로 닫았다** (요청 Q-261111-f77f). 그래프 다섯(G-014~018)·태스크 열하나(T-115~125). 결과물은 `projects/웹워들/tests/` - 브라우저 검사 **125 → 240개**(core 67 · layout 18 · ui 155, 전부 초록). **`web/` 은 한 줄도 안 바꿨다** - 통째로 '검사가 참·거짓을 가리게 만드는' 일이었다. 뒤집기는 `animationstart`+`getAnimations()` 로, 통계는 네 값이 서로 다른 판·진 판·4번
- `2026-11-11T04:43:30` 관리자 [request] REV 150: Q-261111-f77f DONE
- `2026-11-11T04:43:30` 관리자 [task] REV 150: T-125 DONE
- `2026-11-11T04:43:30` 관리자 [task] REV 150: T-124 DONE
- `2026-11-11T04:27:00` 관리자 [graph] REV 150: G-017 끝: T-121(core 뒤집기 animationstart)·T-122(ui 155/155)·T-123(S1 재검수). 통계·보기 설정·접근성 닫힘, 목표 14/15. 보드만 남음 - animationstart 기록이 pop 까지 세어 core 64/67. G-018 로 거르기만 고치면 끝.
- `2026-11-11T04:27:00` 관리자 [task] REV 150: T-125 ASSIGNED S1 보드 목표 최종 확인 + tests/README.md 마무리
- `2026-11-11T04:27:00` 관리자 [task] REV 150: T-124 ASSIGNED S2 browser_core: animationstart 기록에서 pop 거르기 + 옛 검사 이름 정직하게
- `2026-11-11T04:27:00` 관리자 [task] REV 150: T-123 DONE
- `2026-11-11 01:59` 관리자 [handoff] REV 150: **REV 150. 웹워들을 처음으로 브라우저에서 눈으로 봤다** (요청 Q-261110-c450). 그래프 셋(G-011~013)·태스크 열(T-105~114). 결과물은 `projects/웹워들/tests/` - 크로미움으로 도는 검증 세 벌 **125검사**(core 48 · layout 18 · ui 59)와 공용 하네스·README. 오늘의 정답·포트는 하드코딩이 없어 날이 바뀌어도 돈다. **테스트가 31개 전부 초록인 채로 화면 결함 다섯이 숨어 있었다**: 토스트가 보드 첫 줄을 가림(진 판은 영영), 공유 단추가 판
- `2026-11-10 23:04` 관리자 [handoff] REV 149: **REV 149. 웹워들 프로젝트를 새로 열고 돌아가는 워들 한 벌을 만들었다** (요청 Q-261110-0437). 그래프 셋·태스크 아홉(T-096~T-104). 결과물은 `projects/웹워들/` - 순수 로직 `web/js/game.js`(S1), 시스템 사전에서 뽑은 단어 목록(정답 2,488·허용 5,641, S2), 화면 넷(S4), 테스트 셋(S3·S1·S2). 의존성도 네트워크도 없다. 적대적 검수가 찾은 결함 11건을 같은 라운드에 모두 고쳤다 - 손상된 localStorage 값으로 일곱 번째 제출이 들어와 
- `2026-11-10 22:08` 클로드 코드 [handoff] REV 148: **REV 148. 프로젝트 진행률을 목표 대비로, 라운드 도중 요청도 라운드 기록에.** (1) 관리자가 `projects/<이름>/PROGRESS.md` 맨 위 `## 목표` 체크리스트에 프로젝트를 끝내는 데 필요한 목표를 예측해 적고 라운드마다 체크를 맞춘다(표준 브리프 1-1, 8.0-8). 웹 프로젝트 카드의 진행률은 그 목록의 끝난 수/전체(`basis: goals`, '목표 2/5 · 40%'), 목표가 없으면 예전처럼 요청 평균('요청 기준 N%', `request_percent` 는 늘 실음). (2) `task s
- `2026-11-10 21:53` 클로드 코드 [handoff] REV 147: **REV 147. `monitorctl.sh restart` 가 내리기만 하고 올리지 못하던 것.** 원인: 출력을 `| head -1` 처럼 중간에 닫히는 파이프로 받으면 stop 의 다음 줄을 찍다 SIGPIPE 로 스크립트가 죽어 start 까지 가지 못했다. `trap '' PIPE` + 출력 함수 `say`(실패 무시)로 출력이 끊겨도 동작은 끝까지 한다. 내리는 순간의 `tr: 읽기 오류` 소음도 버림. `restart | head -1` 3회 연속 재기동 확인. 준비 점검의 '2건 미통과' 는 15:37(REV 123
- `2026-11-10 21:47` 클로드 코드 [handoff] REV 146: **REV 146. 웹에서 프로젝트 결과물을 보고, 요청 수정 화면에서 프로젝트를 바꾼다.** (1) `GET /api/projects/<이름>/files` · `/file?path=` - `projects/<이름>/` 의 파일 목록(최대 500, README·PROGRESS 먼저, 숨김·링크·의존성 폴더 제외)과 본문(텍스트만, 200KB 까지, 상세 응답과 같은 가림). 경로는 폴더 안 상대 경로만 - 절대 경로·`..`·숨김 조각·심볼릭 링크 거절. (2) 함대 탭 프로젝트 카드에 '결과물 보기' → 상세 패널에서 목록, 행을
- `2026-11-10 21:40` 클로드 코드 [handoff] REV 145: **REV 145. 프로젝트 구조 종합 검토 - 라운드 흐름 결함 5건과 화면 가독성 정비.** (1) 웹 요청 폼은 파일만 만들고 `request list` 는 DB 만 읽어 표준 브리프 라운드의 관리자가 NEW 를 못 봤다 → `aimem_db.load_request_files` 를 `request list/set`·`task set` 앞에서 부른다. (2) `request set --project` 추가(파일 없으면 만든다). (3) 관리자가 안 뜬 라운드는 `round.json` 에 `state: failed` → 프로젝트 
- `2026-11-10 21:02` Claude Code [handoff] REV 144: **REV 144. 작업자 실행 상태에 프로젝트 구분.** 태석님 지시. 식별자는 그대로 두고, 작업자를 띄울 때 실행 기록(`.aimem/runs/<id>.json`)에 `project`·`round` 를 따로 적는다 - 프로젝트는 그래프 노드의 `"project"` 또는 태스크→요청(`task set --request`)에서, 라운드는 가장 최근에 띄운 라운드(`fleet.current_round()`). 그래프 파일에도 `round`. 웹 '작업자 실행 상태' 표에 **프로젝트 칸**(`이름 · R<n>`, 없으면 '함대'),
- `2026-11-10 21:00` Claude Code [handoff] REV 143: **REV 143. 프로젝트별 진행 상황을 함대 화면에.** 태석님 지시(식별자에는 붙이지 않는다 - 알아볼 수만 있으면 된다 / 대신 각 프로젝트가 얼마나 진행됐는지, 몇 라운드를 거쳤는지). 식별자 체계(`8.0-3-1`)는 그대로. (1) 함대 탭 '프로젝트' 카드: 프로젝트마다 진행률 막대(그 프로젝트 요청들의 평균 - 완료 100, 진행 중은 요청 진행율, 거절 제외, 아카이브된 완료 포함), 요청 완료/진행/대기 건수, 거친 라운드 수와 목록, 마지막 라운드 시각, `PROGRESS.md` 최근 항목(펼침). `/api/

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
| `projects/웹워들/README.md` | S3 | R10 |
| `projects/웹워들/app.json` | S3 | R10 |
| `projects/웹워들/tests/README.md` | S1 | R8 검증 모음 사용법 |
| `projects/웹워들/tests/browser_core.py` | S2 | R9 T-118 S3 장애(세 번 빈손 종료)로 S2 이관 |
| `projects/웹워들/tests/browser_harness.py` | S3 | R9 T-115 shot() 뷰포트 선택지 (S2→S3, 브라우저를 띄울 수 있는 슬롯) |
| `projects/웹워들/tests/browser_layout.py` | S3 | R8 T-114 (style.css 와 같은 슬롯) |
| `projects/웹워들/tests/browser_ui.py` | S2 | R8 |
| `projects/웹워들/tests/screenshots/core/**` | S2 | R9 T-118 (browser_core.py 와 같은 슬롯) |
| `projects/웹워들/tests/screenshots/layout/**` | S3 | R8 증거 스크린샷 |
| `projects/웹워들/tests/screenshots/ui/**` | S2 | R8 증거 스크린샷 |
| `projects/웹워들/tests/smoke_integration.mjs` | S3 | R8 T-113 dvh 대비 불변식 재작성 (S1→S3 이관) |
| `projects/웹워들/tests/test_game.mjs` | S3 | R7 로직 테스트 (만든 슬롯과 다른 슬롯) |
| `projects/웹워들/tests/test_words.py` | S2 | R7 단어 목록 테스트 |
| `projects/웹워들/tools/**` | S2 | R7 단어 목록 생성기 |
| `projects/웹워들/web/css/**` | S4 | R7 테마·타일·키보드 |
| `projects/웹워들/web/css/style.css` | S3 | R8 T-113 dvh 대비 복구 (S2→S3) |
| `projects/웹워들/web/index.html` | S4 | R7 화면 |
| `projects/웹워들/web/js/game.js` | S1 | R7 순수 판정 로직 |
| `projects/웹워들/web/js/storage.js` | S4 | R7 통계·진행 저장 |
| `projects/웹워들/web/js/ui.js` | S4 | R7 DOM·입력·애니메이션 |
| `projects/웹워들/web/js/words.js` | S2 | R7 단어 목록 생성물 |
| `rounds/**` | 관리자 | 라운드 기록 폴더 rounds/R<N>/ - brief.md·REPORT.md 만 (결과물은 projects/) |
| `rounds/R10/REVIEW.md` | S1 | R10 |
| `skills/**` | 관리자 | **현재 비어 있음** (REV 101 에서 `acp-slot-lifecycle` 제거). 되살아나면 이 행이 그대로 적용된다 |
| `tests/browser_monitor_app.py` | S3 | R10 T-131 |
| `tests/browser_monitor_auth.py` | S3 | R10 T-135 |
| `tests/browser_monitor_ui.py` | S2 | R10 T-132 |
| `tests/test_aimem_lint.py` | S2 | T-005B. R5 에 S4 로 잠시 이관(KISTI 장애) → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_aimem_monitor*.py` | S2 | 웹 UI 계약 테스트. R5 에 S4 로 잠시 이관 → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_aimem_monitor_app.py` | S2 | R10 |
| `tests/test_fleet*.py` | S2 | `fleet.py` 회귀 테스트. 태석님 승인 2026-11-10 R6 브리프 (9절 2번 해소 - 승인 당시 S4 였으나 S2 복귀로 S2) |
| `tools/aimem_board.py` | S1 | T-006 / T-009 |
| `tools/aimem_db.py` | 관리자 | 운영 상태 SQLite (REV 112~). `migrate`/`render`/`check`/`event`. 출처는 클로드 코드 |
| `tools/aimem_lint.py` | S1 | T-005A |
| `tools/aimem_monitor/__init__.py` | S2 | R10 |
| `tools/aimem_monitor/__main__.py` | 관리자 | 라운드 3 웹 UI. `python3 -m aimem_monitor` 진입점 |
| `tools/aimem_monitor/reader.py` | S1 | 라운드 3 웹 UI. 파일 -> 딕셔너리 (파싱·ETA) |
| `tools/aimem_monitor/server.py` | S2 | R10 |
| `tools/aimem_monitor/static/**` | S3 | 라운드 3 웹 UI. 정적 프런트엔드 (HTML/JS/CSS) |
| `tools/aimem_monitor/static/app.js` | S2 | R10 |
| `tools/aimem_monitor/static/style.css` | S2 | R10 |
| `tools/aimem_monitor/static/sw.js` | S2 | R10 |
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
| Q-261110-0437 | 웹 용 워들 게임 만들어 | 태석 | DONE | 2026-11-10T22:17:14 |
| Q-261110-c450 | 웹워들 화면을 브라우저로 검증하고 남은 목표 아홉 개를 닫기 | 클로드 코드 (태석님 위임, R7 남은 일) | DONE | 2026-11-10T23:07:15 |
| Q-261111-f77f | 웹워들 남은 목표 넷(보드·통계·보기 설정·접근성)의 검사 구멍을 메워 15/15 로 | 클로드 코드 (태석님 위임, R8 남은 일) | DONE | 2026-11-11T02:00:19 |
| Q-261111-5593 | 워들을 함대 모니터 웹에서 실행하기 | 태석 | DONE | 2026-11-11T05:43:39 |

## 실행 (최근 30)

| run id | 태스크 | 슬롯 | 하네스 | 모델 | 시도 | 상태 | rc | 시작 | 끝 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-116-S2-a1-021559 | T-116 | S2 | codex |  | 1 | done | 0 | 02:15:59 | 02:16:21 |
| T-118-S3-a1-021559 | T-118 | S3 | opencode |  | 1 | done | 0 | 02:15:59 | 02:18:24 |
| T-117-S2-a1-021653 | T-117 | S2 | codex |  | 1 | done | 0 | 02:16:53 | 02:28:45 |
| T-116-S2-a1-023655 | T-116 | S2 | codex |  | 1 | done | 0 | 02:36:55 | 02:49:27 |
| T-118-S3-a1-023655 | T-118 | S3 | opencode |  | 1 | done | 0 | 02:36:55 | 02:41:32 |
| T-118-S3-a2-024200 | T-118 | S3 | opencode |  | 2 | done | 0 | 02:42:00 | 02:47:42 |
| T-117-S2-a1-025012 | T-117 | S2 | codex |  | 1 | done | 0 | 02:50:12 | 03:05:43 |
| T-117-S2-a2-030558 | T-117 | S2 | codex |  | 2 | done | 0 | 03:05:58 | 03:24:36 |
| T-120-S2-a1-033010 | T-120 | S2 | codex |  | 1 | done | 0 | 03:30:10 | 03:40:15 |
| T-118-S2-a1-034111 | T-118 | S2 | codex |  | 1 | done | 0 | 03:41:11 | 03:52:05 |
| T-119-S1-a1-035235 | T-119 | S1 | claude | opus | 1 | done | 0 | 03:52:35 | 03:58:37 |
| T-121-S2-a1-040236 | T-121 | S2 | codex |  | 1 | done | 0 | 04:02:36 | 04:04:56 |
| T-121-S2-a2-040506 | T-121 | S2 | codex |  | 2 | done | 0 | 04:05:06 | 04:11:13 |
| T-122-S2-a1-041145 | T-122 | S2 | codex |  | 1 | done | 0 | 04:11:45 | 04:16:34 |
| T-123-S1-a1-041737 | T-123 | S1 | claude | opus | 1 | done | 0 | 04:17:37 | 04:24:21 |
| T-124-S2-a1-042703 | T-124 | S2 | codex |  | 1 | done | 0 | 04:27:03 | 04:32:41 |
| T-125-S1-a1-043311 | T-125 | S1 | claude | opus | 1 | done | 0 | 04:33:11 | 04:37:31 |
| T-126-S2-a1-062424 | T-126 | S2 | codex |  | 1 | done | 0 | 06:24:24 | 06:41:23 |
| T-127-S2-a1-064202 | T-127 | S2 | codex |  | 1 | done | 0 | 06:42:02 | 06:44:14 |
| T-129-S3-a1-064202 | T-129 | S3 | opencode |  | 1 | done | 0 | 06:42:02 | 06:42:52 |
| T-129-S3-a2-064302 | T-129 | S3 | opencode |  | 2 | done | 0 | 06:43:02 | 06:47:39 |
| T-127-S2-a2-064422 | T-127 | S2 | codex |  | 2 | done | 0 | 06:44:22 | 06:48:55 |
| T-128-S2-a1-064941 | T-128 | S2 | codex |  | 1 | done | 0 | 06:49:41 | 06:55:00 |
| T-128-S2-a2-065502 | T-128 | S2 | codex |  | 2 | done | 0 | 06:55:02 | 07:00:12 |
| T-131-S3-a1-070633 | T-131 | S3 | opencode |  | 1 | done | 0 | 07:06:33 | 07:07:12 |
| T-132-S2-a1-070633 | T-132 | S2 | codex |  | 1 | done | 0 | 07:06:33 | 07:09:57 |
| T-131-S3-a2-070713 | T-131 | S3 | opencode |  | 2 | done | 0 | 07:07:13 | 07:16:55 |
| T-133-S1-a1-071705 | T-133 | S1 | claude | opus | 1 | done | 0 | 07:17:05 | 07:26:47 |
| T-134-S2-a1-074014 | T-134 | S2 | codex |  | 1 | done | 0 | 07:40:14 | 07:52:51 |
| T-135-S3-a1-075339 | T-135 | S3 | opencode |  | 1 | done | 0 | 07:53:39 | 08:00:26 |
