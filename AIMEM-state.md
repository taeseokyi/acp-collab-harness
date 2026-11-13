# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)

- 정본은 `.aimem/aimem.db` 입니다. 이 파일을 손으로 고치지 마십시오. 생성 2026-11-13T13:54:52 / REV 169

## 2. 세션 명부

| 슬롯 | 확인토큰 | 하네스 | 모델 | 역할 | 비고 |
| --- | --- | --- | --- | --- | --- |
| S1 | `a41f0c` | claude | opus | 린터 / 보드 CLI / 판단형 | 11-09 CLI 작업자. `claude -p --model opus`(=opus-5.5, 태석님 17:45) |
| S2 | `d27e93` | claude | sonnet | 만들기·고치기 (무료) | R21: 하네스 claude(sonnet) - 23:03 시동 쪽 변경, 관리자 변경 아님 |
| S3 | `5b8c1e` | claude | sonnet | 만들기·검사 (무료) | R21: 하네스 claude(sonnet) - 23:03 시동 쪽 변경, 관리자 변경 아님 |
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
| T-128 | Q-261111-5593 | 브라우저 검증 스크립트 tests/browser_monitor_app.py | S2 | DONE | R10 에서 실패 - T-131·T-132 로 나눠 대체됨(결과물 있음). 보드 정리 2026-11-11 R11 |
| T-129 | Q-261111-5593 | 웹워들: app.json 선언 + README 실행 안내 | S3 | DONE |  |
| T-130 | Q-261111-5593 | 적대적 검수: 경로 탈출·인증·CSP/sandbox·증거의 진위 | S1 | DONE | R10 에서 T-128 실패로 막힘 - T-133 으로 대체됨(rounds/R10/REVIEW.md). 보드 정리 2026-11-11 R11 |
| T-131 | Q-261111-5593 | 브라우저 실측 A: /app/웹워들/ 이 그려지는가 (8개) | S3 | DONE |  |
| T-132 | Q-261111-5593 | 브라우저 실측 B: 모니터 '실행' → 격리 iframe 안에 결과물 (6개) | S2 | DONE |  |
| T-133 | Q-261111-5593 | 적대적 검수: 경로 탈출·인증·CSP/sandbox·변이 시험 | S1 | DONE |  |
| T-134 | Q-261111-5593 | 검수 결함 1~4 수정: /app/ 경로 티켓 + ACAO null + CSP sandbox + 패널 높이 | S2 | DONE |  |
| T-135 | Q-261111-5593 | 브라우저 실측 C: 인증을 켠 채로 미리보기가 뜨는가 (6개) | S3 | DONE |  |
| T-136 | Q-261111-8481 | 적대적 검수 A: /app/ 경로 티켓 인가·유출·격리(새 탭·팝업) | S1 | DONE |  |
| T-137 | Q-261111-8481 | 적대적 검수 B: TLS·프록시 Host·좁은 화면(720px)·검사의 진위(변이 시험) | S4 | DONE |  |
| T-138 | Q-261111-8481 | browser_monitor_auth.py 를 임시 루트에서 돌리기 (운영 .aimem/access.log 오염 제거) | S3 | DONE |  |
| T-139 | Q-261111-8481 | 검수 결함 수정: 티켓 로그 가리기 + Host 허용 목록 + 미리보기 최소 높이 | S2 | DONE | tools/aimem_monitor/server.py, tools/aimem_monitor/static/style.css |
| T-140 | Q-261111-8481 | 단위 검사 6개 추가: TLS 쿠키·TLS/Host CSP 출처·티켓 수명·sw.js | S2 | DONE |  |
| T-141 | Q-261111-8481 | browser_monitor_ui: 폰 폭 미리보기 높이·잘림·가로 스크롤 검사 3개 | S3 | DONE |  |
| T-142 | Q-261111-8481 | browser_monitor_auth: 새 탭(최상위) 격리 검사 3개 | S3 | DONE |  |
| T-143 | Q-261111-8481 | 재검수: 고친 넷 + 새 검사의 변이 시험 | S1 | DONE |  |
| T-144 | Q-261111-8481 | 남은 결함 둘: Host 꼴 엄격 검사 + 미리보기 최소 높이 428px | S2 | DONE |  |
| T-145 | Q-261111-8481 | 검사 구멍 셋: 티켓 로그 가리기·발급 갈래 단독·짧은 화면 키 크기 | S2 | DONE |  |
| T-146 | Q-261111-4e63 | style.css: 화면 키 32px 하한 + 가로로 넓고 낮은 창의 좌우 배치 | S2 | DONE |  |
| T-147 | Q-261111-4e63 | ui.js: 뒤집기가 pop 을 끊어 class 가 남는 결함 수정 | S3 | DONE |  |
| T-148 | Q-261111-4e63 | game.js: 하드 모드를 엄하게 (노랑 개수·같은 자리 되놓기) | S2 | DONE |  |
| T-149 | Q-261111-4e63 | 낱말 거르기: 고유명사·굴절형·고어 꼴을 정답 후보에서 빼기 | S2 | DONE |  |
| T-150 | Q-261111-4e63 | browser_layout.py: 키 높이·좌우 배치·뒤집기 뒤 칸 크기 실측 검사 | S3 | DONE |  |
| T-151 | Q-261111-4e63 | test_game.mjs: 엄해진 하드 모드 검사 | S3 | DONE |  |
| T-152 | Q-261111-4e63 | 설계: 미리보기에서도 기록이 남는 postMessage 길 | S1 | DONE |  |
| T-153 | Q-261111-4e63 | 적대적 검토: T-152 설계가 보안 경계를 새로 뚫지 않는가 | S4 | DONE |  |
| T-154 | Q-261111-e1f1 | 모니터 티켓 심층 방어: exp 상한 + %7E 로그 가리기 | S2 | DONE |  |
| T-155 | Q-261111-e1f1 | GitHub 로그인 세션으로의 실행 티켓 발급 단위 시험 | S2 | DONE |  |
| T-156 | Q-261111-e1f1 | 허용 목록에서 빠진 GitHub 계정의 옛 세션을 끊기 (_subject 재확인) | S2 | DONE |  |
| T-157 | Q-261111-e1f1 | 재검수: 허용 목록 재확인 수정 적대적 재검수 (변이 시험) | S1 | DONE |  |
| T-158 | Q-261111-4e63 | 설계 문서를 T-153 검토 지적대로 고치기 | S1 | DONE |  |
| T-159 | Q-261111-e1f1 | test_aimem_monitor_auth 픽스처: 임시 루트에 GitHub 허용 목록 만들기 | S2 | DONE |  |
| T-160 | Q-261111-e1f1 | 대소문자 검사를 실제 쓰임대로 (쿠키 gh:TaeSeok, 목록 taeseok) | S2 | DONE |  |
| T-161 | Q-261111-663d | 웹워들 storage.js·ui.js: 미리보기(격리 칸) 부모 모드 저장 | S2 | DONE |  |
| T-162 | Q-261111-663d | test_storage.mjs: 부모 모드 단위 시험 (가짜 parent) | S3 | DONE |  |
| T-163 | Q-261111-663d | app.js: panelCleanups + openProjectApp 보관함 리스너 | S2 | DONE |  |
| T-164 | Q-261111-663d | browser_monitor_app.py: 미리보기 기록 유지·칸 격리 실측 | S3 | DONE | tests/browser_monitor_preview.py, tests/browser_monitor_preview_guard.py |
| T-165 | Q-261111-663d | 적대적 검수: 미리보기 보관함이 새 길을 뚫지 않는가 | S1 | DONE |  |
| T-166 | Q-261111-2665 | server.py·reader.py: KISTI 상태 폴링·준비 점검·aimem.goal 제거 | S2 | DONE |  |
| T-167 | Q-261111-2665 | app.js·index.html·style.css: KISTI 카드 제거 + 현재 목표 -> 이번 라운드 | S2 | DONE |  |
| T-168 | Q-261111-0afe | reader.py·app.js: 분담 전 요청의 ETA 0초 버그와 상태별 표시 | S2 | DONE |  |
| T-169 | Q-261111-d64b | app.js·style.css: 프로젝트 칸 볼드 기준 + 생략 제목 전문 보기 | S2 | DONE |  |
| T-170 | Q-261111-2e0f | browser_monitor_ui.py: 바뀐 화면 다섯 가지 실측 | S3 | DONE |  |
| T-171 | Q-261111-663d | storage.js 결함 2·3: 스냅숏 없으면 메모리 모드, 지우기는 put+null | S2 | DONE |  |
| T-172 | Q-261111-663d | app.js 결함 4·5·6: 남는 필드 거름, 굳은 칸 풀기, 정리 훅 구멍 | S2 | DONE |  |
| T-173 | Q-261111-2665 | browser_monitor_ui.py: KISTI 검사가 작업 기록 글자에 걸리던 것 | S3 | DONE |  |
| T-174 | Q-261111-663d | 재검수: 고친 결함 넷의 변이 시험 | S1 | DONE |  |
| T-175 | Q-261111-663d | storage.js: init 의 지난 daily 정리가 접두를 빠뜨려 한 번도 안 지워지던 결함 | S2 | DONE |  |
| T-176 | Q-261111-663d | test_storage.mjs: 지난 daily 정리와 '스냅숏 없으면 put 안 보냄' 검사 | S3 | DONE |  |
| T-177 | Q-261111-7859 | aimem_db.py: 끝난 것 정리가 딸린 실행 기록·이벤트를 함께 옮긴다 | S2 | DONE |  |
| T-178 | Q-261111-7859 | aimem_db.py: 핸드오프·전달 기록·로그 줄까지 + VACUUM·종류별 건수 | S2 | DONE |  |
| T-179 | Q-261111-7859 | server.py: /api/archive 가 종류별 건수를 돌려주고 audit 에 남긴다 | S2 | DONE |  |
| T-180 | Q-261111-7859 | test_aimem_db_cli.py: 연동 아카이브 단위 시험 (열린 작업의 기록은 남는다) | S3 | DONE |  |
| T-181 | Q-261111-731b | app.js·index.html·style.css: 요청 트리에서 끝난 것 치우기 + 진행 표시 현실화 | S2 | DONE |  |
| T-182 | Q-261111-7859 | test_archive_api.py(새): /api/archive 가 종류별 건수를 돌려준다 | S3 | DONE |  |
| T-183 | Q-261111-fa37 | browser_monitor_ui.py: 바뀐 요청 트리 실측 + ETA 검사를 임시 저장소로 | S3 | DONE |  |
| T-184 | Q-261111-b56e | browser_monitor_preview.py(새): 미리보기 기록이 남고 칸이 섞이지 않는다 | S2 | DONE |  |
| T-185 | Q-261111-b56e | browser_monitor_preview_guard.py(새): 중첩 iframe·팝업·자기 put 이 무시된다 | S3 | DONE |  |
| T-186 | Q-261111-7859 | 적대적 검수: 연동 아카이브가 열린 작업·감사 기록·REV 길을 깨뜨리지 않는가 | S1 | DONE | rounds/R14/REVIEW-archive.md |
| T-187 | Q-261111-7859 | 아카이브 결함 1·5·6·9: 열려 있는 것의 기록을 지키는 집합을 넓힌다 | S2 | DONE |  |
| T-188 | Q-261111-7859 | 아카이브 결함 2·4: 서버가 쥔 로그를 안 갈아 끼우고 실행 파일 고아를 안 만든다 | S2 | DONE |  |
| T-189 | Q-261111-7859 | 아카이브 결함 3·7·8·12: 멱등·칸 보존·줄 단위 확인·끝에 render | S2 | DONE |  |
| T-190 | Q-261111-7859 | test_aimem_db_cli.py: 검수가 살려 둔 변이 14개를 잡는 검사로 메우기 | S3 | DONE |  |
| T-191 | Q-261111-7859 | 재검수: 결함 13건의 수정이 실제로 닫혔는가 (변이 22개 재실행) | S1 | DONE | rounds/R14/REVIEW-archive-2.md |
| T-192 | Q-261111-7859 | N3: 웹 '끝난 것 정리' 가 AIMEM.md 를 고쳐 쓰는 길을 막는다 | S2 | DONE |  |
| T-193 | Q-261111-7859 | 빈 검사 둘(N4)을 메우고 시험이 없던 수정(결함 2·4·8·9·12)을 검사로 지킨다 | S3 | DONE |  |
| T-194 | Q-261112-7417 | server.py: 실행 티켓 서명에 주체를 넣고 /app/ 에서 대조 (큐 2) | S2 | DONE |  |
| T-195 | Q-261112-7417 | server.py: 허용 목록에 걸린 요청을 audit 에 남긴다 (큐 3) | S2 | DONE |  |
| T-196 | Q-261112-7417 | server.py: monitor.log 의 모든 줄에 ISO 시각 (큐 8) | S2 | DONE |  |
| T-197 | Q-261112-7417 | aimem_db.py: 복구 적재가 REV 없는 핸드오프를 가라앉히던 것 (큐 6) | S2 | DONE |  |
| T-198 | Q-261112-7417 | aimem_db.py: 아카이브 N1(마지막 .json 고아)·N2(로그 자르기 경쟁) (큐 7) | S2 | DONE |  |
| T-199 | Q-261112-7417 | test_storage.mjs: 키 꼴·8,192자 상한을 지키는 단위 시험 (큐 4) | S3 | DONE |  |
| T-200 | Q-261112-7417 | browser_ui.py: 접근성 대비 검사를 오늘의 낱말에서 떼기 (큐 5) | S3 | DONE |  |
| T-201 | Q-261112-7417 | test_aimem_db_cli.py: 결함 10·N1·N2 회귀 시험 | S3 | DONE |  |
| T-202 | Q-261112-7417 | 적대적 검수: 티켓 주체 묶기와 거절 감사 | S1 | DONE |  |
| T-203 | Q-261112-7417 | server.py: 티켓이 주체를 자기 안에 담아 쿠키 없이도 앱이 열리게 (검수 D1) | S2 | DONE |  |
| T-204 | Q-261112-7417 | browser_monitor_auth.py: 인증 켠 브라우저로 앱 자원 200 + 회수 403 실측 | S3 | DONE |  |
| T-205 | Q-261112-7417 | 재검수: D1 수정이 회수를 깨지 않고 앱을 되살렸는가 | S1 | DONE |  |
| T-206 | Q-261112-6ec6 | 감사 로그: 모든 티켓·쿠키 거절을 남기고 억제 키에서 ip 를 뺀다 (큐 2 D5 · 큐 3 D3·D4) | S2 | DONE |  |
| T-207 | Q-261112-6ec6 | 티켓 URL 에서 로그인 감추기: 주체를 되돌릴 수 없는 태그로 (큐 4) + 회수 뒤 재등록 TTL 문서화 (큐 9 N5) | S2 | DONE |  |
| T-208 | Q-261112-6ec6 | browser_monitor_auth.py: 회수를 iframe 안에서 옛 티켓 하위 자원으로 재기 (큐 7 N3) | S3 | DONE |  |
| T-209 | Q-261112-6ec6 | 웹워들 tests/README.md 의 browser_ui.py 기대 검사 수 155→156 (큐 5) | S3 | DONE |  |
| T-210 | Q-261112-6ec6 | 티켓 회귀 시험 새 파일: 주체 바꿔치기·상한 160·회수 감사·꼴 검사 (큐 6 N1 · 큐 8 N2·N6·D6) | S3 | DONE |  |
| T-211 | Q-261112-6ec6 | 적대적 검수: 이번 라운드의 감사·티켓 변경이 회수와 실제 브라우저 앱을 깨뜨리지 않았는가 | S1 | DONE |  |
| T-212 | Q-261112-6ec6 | _APP_RE: 상한 넘는 티켓 칸이 프로젝트 이름으로 넘어가지 않게 (T-210 NEEDS-FIX 후속) | S2 | DONE |  |
| T-213 | Q-261112-6ec6 | 검수 D1·D2: 무인증 거절이 감사 로그를 불리지 못하게, session-bad 는 세션 쿠키가 있을 때만 | S2 | DONE |  |
| T-214 | Q-261112-6ec6 | 시험 구멍 다섯(M10·M12·M13·M15·M17)과 D1 회귀 시험 메우기 | S3 | DONE |  |
| T-215 | Q-261112-6ec6 | 재검수: D1·D2 수정이 D5 감사 범위를 잃지 않았는가 | S1 | DONE | rounds/R16/REVIEW-ticket-url-2.md |
| T-216 | Q-261112-bd33 | server.py: 감사 N1 - URL 이 주장한 티켓 주체를 인증된 주체로 치지 않는다 (+N2 생략 수 귀속, N3 경로 고정) | S2 | DONE |  |
| T-217 | Q-261112-bd33 | test_monitor_ticket_regress.py: 감사 상한·창·생략 수·무인증 키 회귀 시험 (검수 N4 구멍 M21~M27) | S3 | DONE |  |
| T-218 | Q-261112-bd33 | aimem_db.py: archive_plan 이 브리프 본문을 식별자로 삼아 미리보기가 15초 걸리는 것 | S2 | DONE |  |
| T-219 | Q-261112-bd33 | test_aimem_db_cli.py: 긴 node.task 가 protected_ids 에 들어가지 않는다는 회귀 시험 | S3 | DONE |  |
| T-220 | Q-261112-7a8e | 프로젝트를 별도 탭으로 분리 (index.html·app.js·style.css·sw.js) | S2 | DONE |  |
| T-221 | Q-261112-a8be | 작업 요청 폼의 프로젝트: 있는 것은 고르고 없으면 새로 입력 (index.html·app.js·style.css·sw.js) | S2 | DONE |  |
| T-222 | Q-261112-bd33 | browser_monitor_ui.py: 390px 그래프 제목 펼치기 실측 + 옮긴 정리 단추에 맞춰 갱신 | S3 | DONE |  |
| T-223 | Q-261112-7a8e | browser_monitor_tabs.py(새): 프로젝트 탭·전역 정리 단추·프로젝트 고르기 실측 | S3 | DONE |  |
| T-224 | Q-261112-bd33 | 적대적 검수: 감사 N1 수정 + 모니터 UI 변경 + archive 식별자 수정 | S1 | DONE | rounds/R17/REVIEW-r17.md |
| T-225 | Q-261112-edfe | 끝난 것 정리 단추를 상단 전역 바로 옮김 (보드·요청 트리에서 제거) | S2 | DONE |  |
| T-226 | Q-261112-bd33 | 검수 N9·M10 시험 구멍: 진짜 티켓으로 N1 수정을 지키는 회귀 시험 | S3 | DONE |  |
| T-227 | Q-261112-bd33 | browser_monitor_ui.py: 그래프 제목 펼치기 검사를 임시 저장소 고정 그래프로 (끝난 그래프가 접혀 깨짐) | S3 | DONE | tests/browser_monitor_ui.py |
| T-228 | Q-261112-7a8e | 프로젝트 탭 분리로 깨진 브라우저 검사: auth·preview_guard | S3 | DONE |  |
| T-229 | Q-261112-7a8e | 프로젝트 탭 분리로 깨진 브라우저 검사: preview (S2 소유 파일) | S2 | DONE |  |
| T-230 | Q-261112-bd33 | browser_monitor_ui.py: '프로젝트 칸의 볼드 기준' 도 임시 저장소 고정 실행 기록으로 | S3 | DONE |  |
| T-231 | Q-261112-b1d2 | tests/test_monitor_claude_usage.py(새): server.claude_usage 계약 단위 시험 | S3 | DONE |  |
| T-232 | Q-261112-b1d2 | server.py: .aimem/claude-usage.json 을 읽어 /api/state 에 claude_usage 로 | S2 | DONE |  |
| T-233 | Q-261112-b1d2 | tests/browser_monitor_usage.py(새): 함대 탭 사용 한도 카드 브라우저 실측 | S3 | DONE |  |
| T-234 | Q-261112-b1d2 | 함대 탭 맨 위 'Claude 사용 한도' 카드 (index.html·app.js·style.css·sw.js) | S2 | DONE |  |
| T-235 | Q-261112-c3a1 | 감사 상한: 창마다 처음 보는 (event,subject) 1줄 보장 + 생략 수 보존·N7·N10 (큐 1·2) | S2 | DONE |  |
| T-236 | Q-261112-c3a1 | test_monitor_ticket_regress.py: 창별 첫 줄 보장·생략 수 보존·상한 상수 못박기 (큐 1~3) | S3 | DONE |  |
| T-237 | Q-261112-b1d2 | 엔진: 사용 한도로 끊긴 시도를 limit 으로 구분하고 재시도하지 않기 (+이어 달리기 까닭) | S2 | DONE |  |
| T-238 | Q-261112-b1d2 | 적대적 검수: 사용 한도 표시·감사 상한 몫·한도 실패 구분 | S1 | DONE |  |
| T-239 | Q-261112-b1d2 | browser_monitor_usage.py: 입력 자료를 진짜 claude-usage.json 꼴(dict)로 (T-234 NEEDS-FIX 후속) | S3 | DONE |  |
| T-240 | Q-261112-c3a1 | test_monitor_ticket_regress.py: 상한 시험 4건을 첫 주체 보장에 맞추기 (T-235 NEEDS-FIX 후속) | S3 | DONE |  |
| T-241 | Q-261112-b1d2 | SERVER_KEYS 에 claude_usage 계약 올리기 (/api/state 계약 시험 1건 빨강) | S2 | DONE |  |
| T-242 | Q-261112-b1d2 | 엔진: 멀쩡한 보고를 '사용 한도'로 오인하는 거짓 양성 (R18 T-237 결함, 실측 run T-241) | S2 | DONE |  |
| T-243 | Q-261112-b1d2 | test_fleet_graph.py: 한도 오인 회귀 시험 + 검증 통과 갈래 | S3 | DONE |  |
| T-244 | Q-261112-b1d2 | server.py: 악성 사용 한도 파일이 /api/state 를 죽이는 것(N1·N2) + SIGTERM 감사 비우기(N4) | S2 | DONE |  |
| T-245 | Q-261112-b1d2 | test_monitor_claude_usage.py: 악성 파일·64KiB·두 갈래 키 회귀 시험 (검수 M8·구멍 S3·S4·S5) | S3 | DONE |  |
| T-246 | Q-261112-b1d2 | 엔진: 한도 판정을 rc != 0 일 때만 (검수 N3) | S2 | DONE |  |
| T-247 | Q-261112-b1d2 | test_fleet_graph.py: rc 조건 회귀 시험 + 2000자 구멍(G3) | S3 | DONE |  |
| T-248 | Q-261112-b1d2 | 재검수: N1·N2·N3·N4 수정이 정말 닫혔는가 | S1 | DONE |  |
| T-249 | Q-261112-b1d2 | server.py: 서러게이트 한 글자가 /api/state 를 죽이는 것 (재검수 P1, 높음) | S2 | DONE |  |
| T-250 | Q-261112-b1d2 | test_monitor_claude_usage.py: 서러게이트·곁다리 카드·갈래별 키 회귀 시험 (P1·P5·M2) | S3 | DONE |  |
| T-251 | Q-261112-7d68 | server.py: SIGTERM 처리기 설치를 try 바로 앞으로 (재검수 R19-P6) | S2 | DONE |  |
| T-252 | Q-261112-7d68 | tests/test_monitor_shutdown.py(새): 진짜 SIGTERM 으로 감사 비우기 실측 (큐 R19-P2) | S3 | DONE | T-261 이 이어받아 닫음 (R21 정리) |
| T-253 | Q-261112-7d68 | fleet_graph.py: 한도 판정을 보고 글자보다 .out 의 구조 신호로 먼저 (큐 R19-P3) | S2 | DONE |  |
| T-254 | Q-261112-7d68 | test_fleet_graph.py: 구조 신호 한도 판정 + rc!=0 verify 면제 분기 회귀 시험 (R18-G7) | S3 | DONE |  |
| T-255 | Q-261112-7d68 | browser_monitor_ui.py: 저장소 현재 상태에 기대는 시나리오 넷을 고정 자료로 (큐 1) | S3 | DONE |  |
| T-256 | Q-261112-7d68 | browser_monitor_tabs.py: 탭·프로젝트 고르개 검사를 고정 자료 저장소로 (큐 1) | S3 | DONE |  |
| T-257 | Q-261112-7d68 | 시험 구멍 둘: 창 전환 때 seen 비우기(R18-A7)·미래 at 의 age(R18-S8) | S3 | DONE |  |
| T-258 | Q-261112-7d68 | browser_monitor_usage.py: 퍼센트 반올림(R18-B10)·'N시간 전 기준' 경계(R18-B12) | S3 | DONE |  |
| T-259 | Q-261112-7d68 | test_fleet_ctl.py: 연쇄 한도 로그 정규식의 앵커 부정 사례 (R18-C2) | S2 | DONE |  |
| T-260 | Q-261112-7d68 | 적대적 검수: R20 의 SIGTERM 종료·한도 구조 신호·고정 자료 브라우저 검사·시험 구멍 넷 | S1 | DONE | T-262 가 같은 검수를 다시 해 rounds/R20/REVIEW-r20.md 로 닫음 (R21 정리) |
| T-261 | Q-261112-7d68 | test_monitor_shutdown.py: 빨간 시험 둘 고치기 (T-252 이어받기) | S3 | DONE |  |
| T-262 | Q-261112-7d68 | 적대적 검수: R20 의 SIGTERM 종료·한도 구조 신호·고정 자료 브라우저 검사·시험 구멍 넷 | S1 | DONE |  |
| T-263 | Q-261112-7d68 | fleet_graph.py: 한도 판정 회귀 N3 + 너무 넓은 걸림말 N4·N5 + run_id 검사 N7 | S2 | DONE |  |
| T-264 | Q-261112-7d68 | test_fleet_graph.py: N3·N4·N5·N7 회귀 + 변이 구멍 여섯 (M3~M8) | S3 | DONE |  |
| T-265 | Q-261112-7d68 | browser_monitor_ui.py: 고정 자료가 아직 진짜 저장소를 읽는다 (N1·N2·M11) | S3 | DONE |  |
| T-266 | Q-261112-7d68 | 재검수: N3·N4·N5·N7·N1·N2 수정이 정말 닫혔는가 | S1 | DONE |  |
| T-267 | Q-261112-7d68 | claude 어댑터 한도 판정: N3·N4 수정 옮기기 + 판정 한 곳으로 (R22-P1·P2·P3) | S2 | DONE |  |
| T-268 | Q-261112-7d68 | 시험: 어댑터 한도 판정 세션 갈래·옛 동작 못박기 걷기 (R22-Q1·Q2·Q5, V19) | S3 | DONE |  |
| T-269 | Q-261112-7d68 | 재검수: R22-P1·P2·P3·Q1·Q2·Q5 가 정말 닫혔는가 | S1 | DONE |  |
| T-270 | Q-261112-7d68 | test_fleet_graph: Q2 세션 시험 fake 우회 + Q1 디딤 폴더 (R22-R1·R2) | S3 | DONE |  |
| T-271 | Q-261112-7d68 | 재검수: R22-R1·R2 가 닫혔는가 | S1 | DONE |  |
| T-272 | Q-261113-a22b | 실행 기록 읽기: FIFO 막힘·메타 상한 (R20-N6·R20-N8 = R22-P4) | S2 | DONE |  |
| T-273 | Q-261113-a22b | 시험: FIFO·큰 메타 회귀 + 한도 판정 시험 구멍 (R22-P4·R22-S1·R22-S2) | S3 | DONE |  |
| T-274 | Q-261113-a22b | browser_monitor_ui.py: 이번 라운드 값 고정 자료 + 잘린 제목 펼침 (R22-Q3·R22-Q4) | S3 | DONE |  |
| T-275 | Q-261113-a22b | 검수: R22-P4·S1·S2·Q3·Q4 수정 | S1 | DONE |  |

## 4. 이벤트 로그 (최신 50)

- `2026-11-13 13:54` 클로드 코드 [handoff] REV 169: **REV 169. 공급자 동시 실행은 규칙이 아니라 설정 (태석님 지시).** kistillm 이 돌아와 동시 처리 수를 쟀다(요청마다 다른 1.6만 토큰 입력·256 토큰 출력, 2회): 동시 1 약 20초, 동시 2 둘 다 약 39초, 동시 3 셋 다 약 57초 - 서버는 함께 받지만 처리량이 고정이라 나눠 먹는다. 그래서 지금 `fleet.toml` `[providers.kisti] max_concurrent = 1`. 태석님 방침: 자원이 늘면 동시 실행이 득일 수 있으니 열어 둔다 - 엔진은 이 숫자만 보고, 올릴 때는 
- `2026-11-13T08:58:12` 클로드 코드 [queue] REV 168: 대기 큐 2건 처리(태석님 지시): R22-N1 - fleet.py wait 의 stderr 읽기도 FIFO 안전하게, step() 단위 FIFO 회귀 검사. R22-N2·N3·N4 - 세션 meta 상한·read_regular_bytes 의 장치 거절과 fd 닫기·'이번 라운드' 둘째 줄 검사. 변이 시험으로 옛 동작을 잡는 것 확인.
- `2026-11-13T08:58:12` 관리자 [queue] REV 168: queue -1 FIFO 에서 step() 이 아직 막힘(R22-N1, 낮음): fleet_graph.step() 이 run_limit_signal 보다 먼저 fleet.run_report 로 같은 .out 을 read_text 하고(tools/fleet.py run_report), .rc 가 FIFO 면 _run_state 의 rc.read_text 도 막힘. .out·.rc·.err 읽기를 fleet.read_regular_bytes 로 옮기고 FIFO 시험을 step() 단위로. 근거 rounds/R22/REVIEW-r22-4
- `2026-11-13T08:58:12` 관리자 [queue] REV 168: queue -2 시험 구멍 셋(R22-N2·R22-N3·R22-N4, 낮음~정보): 세션 meta.json 256 KiB 상한 시험(_session_meta·run_limit_signal 세션 갈래), read_regular_bytes 의 S_ISREG 검사·fd 닫기를 지키는 시험(/dev/zero 링크 등), browser_monitor_ui.py '이번 라운드' 둘째 줄(관리자 상태)까지 단언. 근거 rounds/R22/REVIEW-r22-4.md (R22-N5 심볼릭 링크 따라감은 회귀 아님, 정보)
- `2026-11-13 07:02` 클로드 코드 [handoff] REV 168: **REV 168. 엔진 v2 남은 위험 셋 (태석님 지시, 클로드 코드 커밋).** (1) **`verify` 는 울타리 안에서 돈다**(bubblewrap, `tools/fleet_rt/sandbox.py`): 쓰기는 저장소와 `/tmp` 만, `.git` 읽기 전용, `.env`·`.aimem/tls/` 안 보임, 환경에 API 키·토큰·세션 표식 없음, 자기 pid 네임스페이스, 네트워크는 됨. 시간 초과면 프로세스 그룹째 끊는다. `$HOME` 에 쓰거나 키를 읽는 검사는 엔진에서 실패한다(8.0-8 규칙·브리프에 적음).
- `2026-11-13 02:38` 클로드 코드 [handoff] REV 167: **REV 167. 엔진 v2 4단계 - 관리자 호출 방식 (태석님 지시, 클로드 코드 커밋). 기본값은 그대로 상주 방식이다.** `fleet.toml` `[manager] mode = "resident" | "calls"`. `calls` 면 관리자를 ① 계획 ② 판정(되풀이) ③ 마감, 짧은 새 세션으로만 띄우고 그 사이 `fleet_graph run` 은 엔진(라운드 진행기 `fleet_ctl.py _rounddrive`)이 돈다. 호출은 보고 마지막 줄 `NEXT: RUN G-… | CLOSE | STOP <까닭>` 로 다
- `2026-11-13 02:01` 클로드 코드 [handoff] REV 166: **REV 166. 엔진 v2 3단계 - 그래프 실행기 튜닝 (태석님 지시, 클로드 코드 커밋).** (1) 실패의 종류: 시도마다 `fail_kind`(work·infra·limit·timeout). 공급자·전송 장애(infra: 침묵으로 끊김·감독 소멸·응답 없이 오류)는 **시도 횟수를 쓰지 않고** `infra_attempts` 로 옮겨 다시 넣는다. 다시 넣기 전에 공급자가 응답하는지 본다. 3번 이어지면 노드는 `blocked` + `infra`(태스크 잘못이 아님) - 공급자가 돌아오면 `fleet_graph.py un
- `2026-11-13 01:23` M-R22 [handoff] REV 165: **REV 165. R22 (관리자 M-R22-233844) - DONE.** R21 의 엔진 결함 수정(관리자 세션이 슬롯을 바쁨으로 만들던 것)이 실전에서 통과: 작업자 13회 띄움, 막힘 0. 요청 둘 DONE: Q-261112-7d68(R20 이어받기 - G-052 재개 후 재검수가 새 엔진 claude 어댑터에 N3·N4 미반영(P1·P2) 발견 → G-053·G-054 후속으로 판정을 fleet_rt/harness/claude.py 한 벌(result_limit_signal·limit_text_hit)로 모으고 시험이 전
- `2026-11-13T01:21:22` M-R22 [graph] REV 164: G-055 finished: T-272(S2 read_regular_bytes·메타 256KiB)·T-273(S3 시험)·T-274(S3 브라우저 Q3·Q4)·T-275(S1 검수 rounds/R22/REVIEW-r22-4.md) DONE. R20-N6·N8·R22-S1·S2·Q3·Q4 닫힘, 변이 20 중 15. 남은 것 큐 2건(R22-N1 step() FIFO, R22-N2·N3·N4 시험 구멍). Q-261113-a22b DONE
- `2026-11-13T01:21:18` 관리자 [ownership] REV 164: tools/fleet.py -> 관리자
- `2026-11-13T01:21:18` M-R22 [queue] REV 164: queue +2 시험 구멍 셋(R22-N2·R22-N3·R22-N4, 낮음~정보): 세션 meta.json 256 KiB 상한 시험(_session_meta·run_limit_signal 세션 갈래), read_regular_bytes 의 S_ISREG 검사·fd 닫기를 지키는 시험(/dev/zero 링크 등), browser_monitor_ui.py '이번 라운드' 둘째 줄(관리자 상태)까지 단언. 근거 rounds/R22/REVIEW-r22-4.md (R22-N5 심볼릭 링크 따라감은 회귀 아님, 정보)
- `2026-11-13T01:21:18` M-R22 [queue] REV 164: queue +1 FIFO 에서 step() 이 아직 막힘(R22-N1, 낮음): fleet_graph.step() 이 run_limit_signal 보다 먼저 fleet.run_report 로 같은 .out 을 read_text 하고(tools/fleet.py run_report), .rc 가 FIFO 면 _run_state 의 rc.read_text 도 막힘. .out·.rc·.err 읽기를 fleet.read_regular_bytes 로 옮기고 FIFO 시험을 step() 단위로. 근거 rounds/R22/REVIEW-r22-4
- `2026-11-13T01:21:18` M-R22 [queue] REV 164: queue -1 시험 구멍 넷(R22-S1·R22-S2·R22-Q3·R22-Q4, 낮음~정보): (가) test_fleet_graph 의 test_q2_session_branch_context_window_text_is_not_true 를 assertIsNone 으로 (나) claude 어댑터 limit_signal 의 except 갈래를 타는 시험 (다) browser_monitor_ui.py temporary_aimem_root 가 fleet.RUNS 도 갈아끼우고 '이번 라운드' 값까지 단언 (라) 넓은 폭 표 배치에서 잘린 
- `2026-11-13T01:21:18` M-R22 [queue] REV 164: queue -2 한도 판정 남은 결함(R20-N6·R20-N8 = R22-P4, 정보~낮음): fleet_graph.run_limit_signal 이 .out 을 S_ISREG 검사 없이 열어 FIFO 면 영영 막힘(tools/fleet_graph.py 의 1MiB 읽기), fleet._run_meta 가 meta 를 크기 상한 없이 read_text (tools/fleet.py). 방향은 rounds/R20/REVIEW-r20.md
- `2026-11-13T01:21:17` M-R22 [request] REV 164: Q-261113-a22b DONE
- `2026-11-13T01:21:17` 관리자 [task] REV 164: T-275 DONE
- `2026-11-13T01:21:17` 관리자 [task] REV 164: T-274 DONE
- `2026-11-13T01:21:17` 관리자 [task] REV 164: T-273 DONE
- `2026-11-13T01:21:17` 관리자 [task] REV 164: T-272 DONE
- `2026-11-13T00:36:37` M-R22 [request] REV 164: Q-261113-a22b IN-PROGRESS
- `2026-11-13T00:36:37` 관리자 [task] REV 164: T-275 TODO S1 검수: R22-P4·S1·S2·Q3·Q4 수정
- `2026-11-13T00:36:37` 관리자 [task] REV 164: T-274 TODO S3 browser_monitor_ui.py: 이번 라운드 값 고정 자료 + 잘린 제목 펼침 (R22-Q3·R22-Q4)
- `2026-11-13T00:36:37` 관리자 [task] REV 164: T-273 TODO S3 시험: FIFO·큰 메타 회귀 + 한도 판정 시험 구멍 (R22-P4·R22-S1·R22-S2)
- `2026-11-13T00:36:37` 관리자 [task] REV 164: T-272 TODO S2 실행 기록 읽기: FIFO 막힘·메타 상한 (R20-N6·R20-N8 = R22-P4)
- `2026-11-13T00:36:32` 관리자 [ownership] REV 164: rounds/R22/REVIEW-r22-4.md -> S1
- `2026-11-13T00:36:31` 관리자 [ownership] REV 164: tools/fleet.py -> S2
- `2026-11-13T00:36:31` M-R22 [request] REV 164: Q-261113-a22b PLANNED 대기 큐 2건 처리: 실행 기록 FIFO·메타 상한(R22-P4) + 시험 구멍 넷(R22-S1·S2·Q3·Q4)
- `2026-11-13T00:35:09` M-R22 [graph] REV 164: G-054 finished: T-270(S3 Q2 시험 claude 어댑터 패치·Q1 디딤 폴더)·T-271(S1 재검수 rounds/R22/REVIEW-r22-3.md) DONE, R22-R1·R2 닫힘, 전체 discover 940 OK, 변이 3/3. 큐 5건(Q-261112-7d68 의 대상) 모두 처리돼 drop, 새 큐 2건(R22-P4, R22-S1·S2·Q3·Q4). Q-261112-7d68 DONE
- `2026-11-13T00:35:09` M-R22 [request] REV 164: Q-261112-7d68 DONE
- `2026-11-13T00:35:09` M-R22 [queue] REV 164: queue +2 한도 판정 남은 결함(R20-N6·R20-N8 = R22-P4, 정보~낮음): fleet_graph.run_limit_signal 이 .out 을 S_ISREG 검사 없이 열어 FIFO 면 영영 막힘(tools/fleet_graph.py 의 1MiB 읽기), fleet._run_meta 가 meta 를 크기 상한 없이 read_text (tools/fleet.py). 방향은 rounds/R20/REVIEW-r20.md
- `2026-11-13T00:35:04` M-R22 [queue] REV 164: queue +1 시험 구멍 넷(R22-S1·R22-S2·R22-Q3·R22-Q4, 낮음~정보): (가) test_fleet_graph 의 test_q2_session_branch_context_window_text_is_not_true 를 assertIsNone 으로 (나) claude 어댑터 limit_signal 의 except 갈래를 타는 시험 (다) browser_monitor_ui.py temporary_aimem_root 가 fleet.RUNS 도 갈아끼우고 '이번 라운드' 값까지 단언 (라) 넓은 폭 표 배치에서 잘린 
- `2026-11-13T00:34:57` 관리자 [task] REV 164: T-271 DONE
- `2026-11-13T00:34:57` 관리자 [task] REV 164: T-270 DONE
- `2026-11-13T00:34:50` M-R22 [queue] REV 164: queue -1 브라우저 검사가 '진짜 저장소의 그때그때 상태' 에 기대는 자리를 한 번 쓸어내십시오. R17 에 두 건이 이 까닭으로 깨졌습니다(그래프 제목 펼치기 - 끝난 그래프가 접힘 / 프로젝트 칸 볼드 - 최근 실행 20건이 전부 함대 일). 둘 다 임시 저장소 고정 자료로 옮겨 고쳤습니다. tests/browser_monitor_*.py 에서 ROOT 를 그대로 보는 시나리오를 찾아 같은 꼴로 옮기십시오
- `2026-11-13T00:34:50` M-R22 [queue] REV 164: queue -2 SIGTERM 시험 구멍(재검수 R19-P2, 중간): 재검수가 넣은 변이 셋 - serve() 의 SIGTERM 처리기 지우기 / 처리기 되돌리기 지우기 / finally 의 flush_denied_audit 지우기 - 이 모두 모니터 시험 117건을 초록으로 통과합니다. 자식 프로세스로 서버를 띄워 실제 SIGTERM 을 보내고 access.log 에 'audit-dropped' 가 남는지 보는 시험을 새 파일(tests/test_monitor_shutdown.py)에 두십시오 (rounds/R19/REVIEW-
- `2026-11-13T00:34:50` M-R22 [queue] REV 164: queue -3 한도 판정의 구조 신호(재검수 R19-P3, 낮음): 지금은 rc != 0 + 보고 글자로 봅니다. 글자 쪽은 'You've hit your weekly limit' 같은 형제 문구를 놓칩니다. claude 하네스는 .aimem/runs/<id>.out JSON 에 is_error·api_error_status=429·api_error=usage_limit_reached·terminal_reason=api_error 를 남기므로 글자보다 그것을 먼저 보십시오. codex/opencode 는 그런 칸이 없어 글자 판정
- `2026-11-13T00:34:49` M-R22 [queue] REV 164: queue -4 R18 적대적 검수가 남긴 시험 구멍 일곱(R18-A7·R18-A12·R18-S8·R18-G7·R18-C2·R18-B10·R18-B12, 낮음~정보): 변이를 넣어도 시험이 초록인 자리들입니다. rounds/R18/REVIEW-r18.md 의 변이표를 보고 하나씩 메우십시오
- `2026-11-13T00:34:49` M-R22 [queue] REV 164: queue -5 재검수 R19-P6(낮음): serve() 에서 SIGTERM 처리기를 건 뒤 try: 로 들어가기까지 log_line 여러 줄이 있어, 그 틈에 SIGTERM 이 오면 shutdown 이 아직 안 뜬 httpd 를 건드립니다. 처리기 설치를 try 바로 앞으로 옮기거나 처리기가 플래그만 세우게 하십시오 (rounds/R19/REVIEW-r19.md)
- `2026-11-13T00:15:52` 관리자 [task] REV 164: T-271 TODO S1 재검수: R22-R1·R2 가 닫혔는가
- `2026-11-13T00:15:51` 관리자 [task] REV 164: T-270 TODO S3 test_fleet_graph: Q2 세션 시험 fake 우회 + Q1 디딤 폴더 (R22-R1·R2)
- `2026-11-13T00:15:48` 관리자 [ownership] REV 164: rounds/R22/REVIEW-r22-3.md -> S1
- `2026-11-13T00:15:48` M-R22 [graph] REV 164: G-053 finished: T-267(S2 어댑터 판정 한 벌)·T-268(S3 시험)·T-269(S1 재검수 rounds/R22/REVIEW-r22-2.md) DONE. P1·P2·P3·Q5·V19 닫힘(변이 16 중 15 잡힘). 남은 것: R1(중간, 전체 discover 에서 test_q2 429 FAIL - fake 강제)·R2(낮음, Q1 디딤 폴더) → G-054 후속
- `2026-11-13T00:15:48` 관리자 [task] REV 164: T-269 DONE
- `2026-11-13T00:15:48` 관리자 [task] REV 164: T-268 DONE
- `2026-11-13T00:15:48` 관리자 [task] REV 164: T-267 DONE
- `2026-11-12T23:57:29` 관리자 [task] REV 164: T-269 TODO S1 재검수: R22-P1·P2·P3·Q1·Q2·Q5 가 정말 닫혔는가
- `2026-11-12T23:57:29` 관리자 [task] REV 164: T-268 TODO S3 시험: 어댑터 한도 판정 세션 갈래·옛 동작 못박기 걷기 (R22-Q1·Q2·Q5, V19)
- `2026-11-12T23:57:29` 관리자 [task] REV 164: T-267 TODO S2 claude 어댑터 한도 판정: N3·N4 수정 옮기기 + 판정 한 곳으로 (R22-P1·P2·P3)
- `2026-11-12T23:57:17` 관리자 [ownership] REV 164: rounds/R22/REVIEW-r22-2.md -> S1
- `2026-11-12T23:57:17` 관리자 [ownership] REV 164: tests/test_rt_claude.py -> S3
- `2026-11-12 23:28` M-R21 [handoff] REV 164: **REV 164. R21 (관리자 M-R21-230339) - BLOCKED, 엔진 v2 결함으로 작업자 0명.** NEW 요청 없음. 이어받은 Q-261112-7d68 의 G-052(R20 후속 4노드)를 재개하려 했으나 fleet_graph._busy_slots 가 관리자 세션(.aimem/sessions/M-R21-*, role manager·slot null)을 '슬롯 모를 running 실행' 으로 세어 모든 슬롯을 바쁨으로 본다 → 관리자가 살아 있는 한 어떤 노드도 못 띄운다(로그: skip T-263/T-265 - 
- `2026-11-12 23:00` 클로드 코드 [handoff] REV 163: **REV 163. 함대 엔진 v2 (태석님 지시, 클로드 코드 커밋).** R20 은 11-12 20:13 마감 없이 끊겼다(G-052 4건 todo, 요청 Q-261112-7d68 진행 중, 큐 5건 - 다음 라운드가 이어받는다). 그 뒤 엔진을 바꿨다: (1) 작업자와 관리자를 엔진이 직접 세션으로 띄운다 - `tools/fleet_rt`(하네스 어댑터 claude·codex·opencode·fake + 세션마다 감독 프로세스), 기록은 `.aimem/sessions/<id>/`(사건 흐름 events.jsonl·report.
- `2026-11-12 17:42` 클로드 코드 [handoff] REV 162: **REV 162 (덧붙임, 클로드 코드 커밋 - R20 도중).** 태석님 지시. 모니터 화면 정리: (1) 상단 바 - 어두운 모드·로그인·로그아웃을 ⚙ 설정 메뉴 하나로(폰·데스크톱 같은 꼴), 720px 이하는 짧은 글자로 2행, 930px 이상 1행(320~1450px 10px 간격 실측, 3행 없음). (2) 데스크톱 - 핸드오프 로그 시각 칸이 잘리던 것, ASSIGNED·NEEDS-FIX 배지 잘림, '자동 새로고침' 간격, 서브태스크 없는 진행 중 요청의 같은 문장 두 번. 함께: R19 종료분(REPORT·REV 
- `2026-11-12 17:32` 관리자 R19 [handoff] REV 162: **REV 162. R19 - 끊긴 R18 을 닫고, 사용 한도 카드와 감사 상한을 끝까지 몰아 적대적 검수·재검수까지.** R18 은 WSL 재시작으로 끊겼었고 G-045 를 이어 돌려 닫았습니다(T-234·T-235 는 작업자가 일을 다 했는데 다른 파일의 검사 자료가 틀려 verify 가 빨갰던 것 - 고친 뒤 관리자가 같은 명령을 직접 돌려 rc 0 확인하고 닫음). **엔진 결함 둘을 실측으로 잡았습니다**: R18 이 넣은 한도 판정이 보고에 '사용 한도' 글자만 있어도 멀쩡한 DONE 을 막았습니다(실제로 T-241·T
- `2026-11-12 17:16` 클로드 코드 [handoff] REV 161: **REV 161 (클로드 코드, R19 도중 커밋).** 태석님 지시. (1) **대기 큐 결함 번호에 라운드**: 검수 번호(N=결함·M=변이 시험·D=넘어온 결함)는 보고서마다 1부터 다시 세어 라운드끼리 섞였다 → 큐에는 `R17-N5`·`R17-N5·N6` 꼴만, `queue add/edit` 가 맨 `N5` 를 거절. `queue edit --pos`(제자리 고침) 신설. 큐 1~3 을 이 꼴로 고치고 출처 T-224 를 적음. 표준 브리프·AIMEM 4.5 에 규칙(순서 번호 대신 발견 번호로 가리킴). (2) **화면
- `2026-11-12 15:30` 클로드 코드 [handoff] REV 160: **R18 끊김 (REV 그대로).** 2026-11-12 14:57 WSL 이 업데이트로 재시작되어(15:22 재기동, 커널 6.18.58.1) 관리자 R18·작업자·이어 달리기 감시자가 모두 사라졌다. G-045: T-231·T-232·T-233·T-237 done, T-234(S2)·T-236(S3) 는 실행 1분 안에 lost(거둠), T-235·T-238 todo. 파일·git·DB 손상 없음, 린터 통과. 전체 테스트 641 중 1건 실패 - `test_collect_state_failure_branch_keys_matc
- `2026-11-12 14:15` 관리자 R17 [handoff] REV 160: **REV 160. R17 - R16 을 닫고(끊긴 라운드), 웹 요청 넷을 끝냈습니다. 큰 것은 감사 N1.** 티켓 URL 하나로 분당 60줄 상한을 채워 **회수된 계정의 시도가 0줄**이던 것을 닫았습니다 - URL 이 주장한 티켓 주체는 인증된 주체로 치지 않아 키에서 경로를 뺍니다(`authenticated` 인자). 재검수 실측: 가상 30분 park 0줄 → **30줄**. N2(생략 수 귀속)·N3(경로 고정)도 닫힘. 검수 T-224 가 찾은 **N9(중간, 시험 구멍)** - 그 수정을 되돌려도 시험이 전부 초록

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
| `projects/웹워들/docs/**` | S1 | R12 T-152 미리보기 기록 저장 설계 문서 (새 경로) |
| `projects/웹워들/tests/README.md` | S3 | R16 T-209 검사 수 고치기 (S1 유료→S3 무료, 만들기·고치기는 무료 슬롯) |
| `projects/웹워들/tests/browser_core.py` | S2 | R9 T-118 S3 장애(세 번 빈손 종료)로 S2 이관 |
| `projects/웹워들/tests/browser_harness.py` | S3 | R9 T-115 shot() 뷰포트 선택지 (S2→S3, 브라우저를 띄울 수 있는 슬롯) |
| `projects/웹워들/tests/browser_layout.py` | S3 | R8 T-114 (style.css 와 같은 슬롯) |
| `projects/웹워들/tests/browser_ui.py` | S3 | R15 T-200 접근성 대비 검사 (game.js·ui.js 를 고친 S2 와 다른 슬롯) |
| `projects/웹워들/tests/screenshots/core/**` | S2 | R9 T-118 (browser_core.py 와 같은 슬롯) |
| `projects/웹워들/tests/screenshots/layout/**` | S3 | R8 증거 스크린샷 |
| `projects/웹워들/tests/screenshots/ui/**` | S2 | R8 증거 스크린샷 |
| `projects/웹워들/tests/smoke_integration.mjs` | S3 | R8 T-113 dvh 대비 불변식 재작성 (S1→S3 이관) |
| `projects/웹워들/tests/test_game.mjs` | S3 | R7 로직 테스트 (만든 슬롯과 다른 슬롯) |
| `projects/웹워들/tests/test_storage.mjs` | S3 | R13 T-162 부모 모드 단위 시험 (만든 슬롯과 다른 슬롯) |
| `projects/웹워들/tests/test_words.py` | S2 | R7 단어 목록 테스트 |
| `projects/웹워들/tools/**` | S2 | R7 단어 목록 생성기 |
| `projects/웹워들/web/css/**` | S4 | R7 테마·타일·키보드 |
| `projects/웹워들/web/css/style.css` | S2 | R12 T-146 키 높이 하한·좌우 배치 (S3→S2, 검사는 S3 가 써 교차 검증) |
| `projects/웹워들/web/index.html` | S4 | R7 화면 |
| `projects/웹워들/web/js/game.js` | S2 | R12 T-148 하드 모드 (S1 유료→S2 무료, 만들기·고치기는 무료 슬롯) |
| `projects/웹워들/web/js/storage.js` | S2 | R13 T-161 부모 모드 저장 (S4 유료→S2 무료, 만들기·고치기는 무료 슬롯) |
| `projects/웹워들/web/js/ui.js` | S2 | R13 T-161 await init() 호출 자리 (storage.js 와 같은 슬롯) |
| `projects/웹워들/web/js/words.js` | S2 | R7 단어 목록 생성물 |
| `rounds/**` | 관리자 | 라운드 기록 폴더 rounds/R<N>/ - brief.md·REPORT.md 만 (결과물은 projects/) |
| `rounds/R10/REVIEW.md` | S1 | R10 |
| `rounds/R11/REVIEW-A.md` | S1 | R11 T-136 적대적 검수 A |
| `rounds/R11/REVIEW-B.md` | S4 | R11 T-137 적대적 검수 B |
| `rounds/R11/REVIEW-C.md` | S1 | R11 T-143 재검수 |
| `rounds/R12/REVIEW-auth.md` | S1 | R12 T-157 재검수 (새 경로) |
| `rounds/R12/REVIEW-design.md` | S4 | R12 T-153 설계 적대적 검토 (새 경로) |
| `rounds/R13/REVIEW-preview-2.md` | S1 | R13 T-174 재검수 |
| `rounds/R13/REVIEW-preview.md` | S1 | R13 T-165 적대적 검수 |
| `rounds/R14/REVIEW-archive-2.md` | S1 | R14 T-191 재검수 |
| `rounds/R14/REVIEW-archive.md` | S1 | R14 T-186 적대적 검수 |
| `rounds/R15/REVIEW-ticket-2.md` | S1 | R15 T-205 재검수 |
| `rounds/R15/REVIEW-ticket.md` | S1 | R15 T-202 적대적 검수 |
| `rounds/R16/REVIEW-ticket-url-2.md` | S1 | R16 T-215 재검수 |
| `rounds/R16/REVIEW-ticket-url.md` | S1 | R16 T-211 적대적 검수 |
| `rounds/R17/REVIEW-r17.md` | S1 | R17 T-224 적대적 검수 |
| `rounds/R18/REVIEW-r18.md` | S1 | R18 T-238 적대적 검수 |
| `rounds/R19/REVIEW-r19.md` | S1 | R19 T-248 재검수 보고서 (새 파일) |
| `rounds/R20/REVIEW-r20-2.md` | S1 | R20 재검수 |
| `rounds/R20/REVIEW-r20.md` | S1 | R20 적대적 검수 |
| `rounds/R21/REVIEW-r21.md` | S1 | R21 T-266 재검수 |
| `rounds/R22/REVIEW-r22-2.md` | S1 | R22 T-269 재검수 |
| `rounds/R22/REVIEW-r22-3.md` | S1 | R22 T-271 재검수 |
| `rounds/R22/REVIEW-r22-4.md` | S1 | R22 T-275 검수 |
| `rounds/R22/REVIEW-r22.md` | S1 | R22 T-266 재검수 (R21 이 못 띄워 R22 폴더로 옮김) |
| `skills/**` | 관리자 | **현재 비어 있음** (REV 101 에서 `acp-slot-lifecycle` 제거). 되살아나면 이 행이 그대로 적용된다 |
| `tests/browser_monitor_app.py` | S3 | R10 T-131 |
| `tests/browser_monitor_auth.py` | S3 | R10 T-135 |
| `tests/browser_monitor_preview.py` | S2 | R14 T-185 웹워들 미리보기 보관함 브라우저 실측 (새 파일, app.js 보관함을 쓴 R13 S2 와 같은 슬롯이나 검사 대상은 R13 산출물) |
| `tests/browser_monitor_preview_guard.py` | S3 | R14 T-185 미리보기 보관함 방어 실측 (새 파일) |
| `tests/browser_monitor_tabs.py` | S3 | R17 T-223 프로젝트 탭·전역 정리 단추 실측 (새 파일, static 을 고친 S2 와 다른 슬롯) |
| `tests/browser_monitor_ui.py` | S3 | R13 T-170 화면 실측 (app.js 를 고친 S2 와 다른 슬롯) |
| `tests/browser_monitor_usage.py` | S3 | R18 T-233 사용 한도 카드 브라우저 실측 (새 파일, static 을 고친 S2 와 다른 슬롯) |
| `tests/test_aimem_db_cli.py` | S3 | R14 T-180 (aimem_db.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_aimem_lint.py` | S2 | T-005B. R5 에 S4 로 잠시 이관(KISTI 장애) → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_aimem_monitor*.py` | S2 | 웹 UI 계약 테스트. R5 에 S4 로 잠시 이관 → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_aimem_monitor_app.py` | S2 | R10 |
| `tests/test_archive_api.py` | S3 | R14 T-183 /api/archive 계약 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_fleet*.py` | S2 | `fleet.py` 회귀 테스트. 태석님 승인 2026-11-10 R6 브리프 (9절 2번 해소 - 승인 당시 S4 였으나 S2 복귀로 S2) |
| `tests/test_fleet_graph.py` | S3 | R19 T-243 한도 오인 회귀 시험 (fleet_graph.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_monitor_claude_usage.py` | S3 | R18 T-231 claude_usage 정리 단위 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_monitor_shutdown.py` | S3 | R20 T-252 SIGTERM 종료 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_monitor_ticket_regress.py` | S3 | R16 T-210 티켓 회귀 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_rt_claude.py` | S3 | R22 T-268 (claude.py 를 고친 S2 와 다른 슬롯) |
| `tools/aimem_board.py` | S1 | T-006 / T-009 |
| `tools/aimem_db.py` | S2 | R14 T-177·T-178 끝난 것 정리와 연동한 기록 아카이브 (관리자→S2, 만들기·고치기는 무료 슬롯) |
| `tools/aimem_lint.py` | S1 | T-005A |
| `tools/aimem_monitor/__init__.py` | S2 | R10 |
| `tools/aimem_monitor/__main__.py` | 관리자 | 라운드 3 웹 UI. `python3 -m aimem_monitor` 진입점 |
| `tools/aimem_monitor/reader.py` | S2 | R13 T-166·T-168 goal 제거·ETA 수정 (S1 유료→S2 무료) |
| `tools/aimem_monitor/server.py` | S2 | R10 |
| `tools/aimem_monitor/static/**` | S3 | 라운드 3 웹 UI. 정적 프런트엔드 (HTML/JS/CSS) |
| `tools/aimem_monitor/static/app.js` | S2 | R10 |
| `tools/aimem_monitor/static/index.html` | S2 | R13 T-167 KISTI 카드 제거 (app.js 와 같은 슬롯) |
| `tools/aimem_monitor/static/style.css` | S2 | R10 |
| `tools/aimem_monitor/static/sw.js` | S2 | R10 |
| `tools/envcheck/__init__.py` | 관리자 | 공통 계약(`check()` / `Result`) 정의 |
| `tools/envcheck/__main__.py` | 관리자 | 통합 러너. **합류점을 하나로 두는 장치** |
| `tools/envcheck/runtime.py` | S2 | 라운드 2. 실행 환경 계층 검사 |
| `tools/envcheck/sessions.py` | S1 | 라운드 2. 세션·에이전트 계층 검사 |
| `tools/envcheck/terminal.py` | S3 | 라운드 2. 터미널 규약 계층 검사 |
| `tools/fleet.py` | 관리자 | R22 종료로 환원 (T-272 동안 S2) |
| `tools/fleet_ctl.py` | 관리자 | R19 종료로 환원 (R18 T-237 동안 S2) |
| `tools/fleet_graph.py` | S2 | R20 T-253 한도 판정 구조 신호 (큐 R19-P3) |
| `tools/fleet_rt/harness/claude.py` | S2 | R22 T-267 한도 판정 한 곳으로 (재검수 R22-P1·P2·P3) |
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
| Q-261111-8481 | 모니터 결과물 실행(/app, 경로 티켓)의 적대적 검수와 수정·재검수 | 클로드 코드 (태석님 위임, R10 남은 일) | DONE | 2026-11-11T15:37:59 |
| Q-261111-4e63 | 웹워들 후속: 키 높이·애니메이션 결함·좌우 배치·낱말 거르기·하드 모드·미리보기 기록 저장(설계) | 클로드 코드 (태석님 위임) | DONE | 2026-11-11T17:55:31 |
| Q-261111-e1f1 | 모니터: 티켓 심층 방어·파이어폭스 검사·GitHub 세션 티켓 발급 시험 | 클로드 코드 (태석님 위임) | DONE | 2026-11-11T17:55:31 |
| Q-261111-fbd1 | 보드 큐, 끝난 작업 정리 기능 점검 | 태석 | DONE | 2026-11-11T18:12:27 |
| Q-261111-2665 | 함대, kistillm 모니터링 제거 | 태석 | DONE | 2026-11-11T18:22:39 |
| Q-261111-d64b | 함대, 작업자 실행 상태, 프로젝트 컬럼 볼드처리 점검 개선 | 태석 | DONE | 2026-11-11T18:26:59 |
| Q-261111-0afe | 요청트리, 요청별 분담트리 ETA 상태 점검 개선 | 태석 | DONE | 2026-11-11T18:34:57 |
| Q-261111-2e0f | 작업 트리, 태스크 그래프의 제목의 생략 내용 조회 | 태석 | DONE | 2026-11-11T18:44:15 |
| Q-261111-e099 | 함대, 현재 목표 기능 삭제, 개선 검토 | 태석 | DONE | 2026-11-11T18:48:55 |
| Q-261111-663d | 웹워들: 남은 목표 1개 이어 가기 (R12 뒤 자동) | 함대 이어 달리기 | DONE | 2026-11-11T18:57:21 |
| Q-261111-731b | 요청 트리: 끝난 요청·그래프를 화면에서 치우기 (있는 '끝난 것 정리' 를 쓰기 쉽게, 자동 정리 기준 손보기) | 태석 | DONE | 2026-11-11T18:58:35 |
| Q-261111-7859 | 끝난 것 정리와 연동: 정리되는 작업의 실행 기록·이벤트·핸드오프·로그도 함께 아카이브 (자동은 14일, Q-261111-731b 에 덧붙임) | 태석 (클로드 코드가 옮겨 적음) | DONE | 2026-11-11T19:15:43 |
| Q-261111-fa37 | 요청별 분담 트리 진행상황 표시 현실화 | 태석 | DONE | 2026-11-11T20:31:53 |
| Q-261111-7958 | 알림: S3(opencode)의 모델이 EXAONE 에서 kistillm 으로 바뀌었습니다 (태석님 지시) | 슬롯 관리(클로드 코드, 태석님 지시) | DONE | 2026-11-11T21:02:42 |
| Q-261111-b56e | 웹워들: 미리보기 기록 저장을 실제 브라우저로 재서 마지막 목표 닫기 | 클로드 코드 (태석님 위임) | DONE | 2026-11-11T22:01:50 |
| Q-261112-7417 | 대기 큐 8건 처리 (R14 뒤 자동) | 함대 이어 달리기 | DONE | 2026-11-12T06:28:30 |
| Q-261112-6ec6 | 대기 큐 9건 처리 (R15 뒤 자동) | 함대 이어 달리기 | DONE | 2026-11-12T08:04:11 |
| Q-261112-7a8e | 프로젝트 탭 분리 | 태석 | DONE | 2026-11-12T09:02:19 |
| Q-261112-edfe | 끝난것 정리 위치 이동 | 태석 | DONE | 2026-11-12T09:04:36 |
| Q-261112-a8be | 작업요청에 프로젝트 목록 나오지않음 | 태석 | DONE | 2026-11-12T09:08:39 |
| Q-261112-bd33 | R16 마무리 (사용 한도로 끊김) + 재검수 N1 + 그래프 제목 펼치기 검사 | 클로드 코드(태석님 위임) | DONE | 2026-11-12T11:45:55 |
| Q-261112-b1d2 | 함대 탭에 Claude 사용 한도(5시간·주간) 표시 | 태석 | DONE | 2026-11-12T11:49:37 |
| Q-261112-c3a1 | 대기 큐 1~3 처리 (R18) | 관리자 (R17 검수가 남긴 큐) | DONE | 2026-11-12T14:25:16 |
| Q-261112-7d68 | 대기 큐 5건 처리 (R19 뒤 자동) | 함대 이어 달리기 | DONE | 2026-11-12T17:35:20 |
| Q-261113-a22b | 대기 큐 2건 처리: 실행 기록 FIFO·메타 상한(R22-P4) + 시험 구멍 넷(R22-S1·S2·Q3·Q4) | 관리자 M-R22 (대기 큐) | DONE | 2026-11-13T00:36:31 |

## 실행 (최근 30)

| run id | 태스크 | 슬롯 | 하네스 | 모델 | 시도 | 상태 | rc | 시작 | 끝 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-259-S2-a1-181328 | T-259 | S2 | codex |  | 1 | done | 0 | 18:13:28 | 18:15:21 |
| T-252-S3-a1-185202 | T-252 | S3 | opencode |  | 1 | done | 0 | 18:52:02 | 18:55:19 |
| T-252-S3-a2-185555 | T-252 | S3 | opencode |  | 2 | done | 0 | 18:55:55 | 18:58:04 |
| T-254-S3-a1-185833 | T-254 | S3 | opencode |  | 1 | done | 0 | 18:58:33 | 19:01:31 |
| T-256-S3-a1-190137 | T-256 | S3 | opencode |  | 1 | done | 0 | 19:01:37 | 19:05:05 |
| T-257-S3-a1-190512 | T-257 | S3 | opencode |  | 1 | done | 0 | 19:05:12 | 19:09:53 |
| T-258-S3-a1-191029 | T-258 | S3 | opencode |  | 1 | done | 0 | 19:10:29 | 19:12:49 |
| T-261-S3-a1-191342 | T-261 | S3 | opencode |  | 1 | done | 0 | 19:13:42 | 19:15:23 |
| T-262-S1-a1-191529 | T-262 | S1 | claude | opus | 1 | done | 0 | 19:15:29 | 19:27:09 |
| T-263-S2-a1-193012 | T-263 | S2 | codex |  | 1 | lost |  | 19:30:12 | 20:10:17 |
| T-265-S3-a1-193012 | T-265 | S3 | opencode |  | 1 | done | 1 | 19:30:12 | 20:01:25 |
| T-265-S3-a2-200131 | T-265 | S3 | opencode |  | 2 | lost |  | 20:01:31 | 20:13:52 |
| T-263-S2-a2-201017 | T-263 | S2 | codex |  | 2 | lost |  | 20:10:17 | 20:13:52 |
| ADHOC-S4-a1-213402 | ADHOC | S4 | claude | sonnet | 1 | done | 0 | 21:34:02 | 21:34:14 |
| ADHOC-S2-a1-220212 | ADHOC | S2 | codex | openrouter/deepseek/deepseek-v4.1-flash | 1 | done | 0 | 22:02:12 | 22:02:20 |
| ADHOC-S3-a1-220213 | ADHOC | S3 | opencode | openrouter/deepseek/deepseek-v4.1-flash | 1 | done | 0 | 22:02:13 | 22:02:26 |
| ADHOC-S3-a1-220242 | ADHOC | S3 | opencode | openrouter/deepseek/deepseek-v4.1-flash | 1 | killed | -15 | 22:02:42 | 22:03:07 |
| T-263-S2-a2-234000 | T-263 | S2 | claude | sonnet | 2 | done | 0 | 23:40:00 | 23:40:45 |
| T-265-S3-a2-234000 | T-265 | S3 | claude | sonnet | 2 | done | 0 | 23:40:00 | 23:41:53 |
| T-264-S3-a1-234216 | T-264 | S3 | claude | sonnet | 1 | done | 0 | 23:42:16 | 23:42:59 |
| T-266-S1-a1-234309 | T-266 | S1 | claude | opus | 1 | done | 0 | 23:43:09 | 23:52:32 |
| T-267-S2-a1-235730 | T-267 | S2 | claude | sonnet | 1 | done | 0 | 23:57:30 | 23:59:42 |
| T-268-S3-a1-000043 | T-268 | S3 | claude | sonnet | 1 | done | 0 | 00:00:43 | 00:01:28 |
| T-269-S1-a1-000136 | T-269 | S1 | claude | opus | 1 | done | 0 | 00:01:36 | 00:12:40 |
| T-270-S3-a1-001552 | T-270 | S3 | claude | sonnet | 1 | done | 0 | 00:15:52 | 00:18:37 |
| T-271-S1-a1-002059 | T-271 | S1 | claude | opus | 1 | done | 0 | 00:20:59 | 00:34:19 |
| T-272-S2-a1-003638 | T-272 | S2 | claude | sonnet | 1 | done | 0 | 00:36:38 | 00:37:57 |
| T-273-S3-a1-003851 | T-273 | S3 | claude | sonnet | 1 | done | 0 | 00:38:51 | 00:41:36 |
| T-274-S3-a1-004400 | T-274 | S3 | claude | sonnet | 1 | done | 0 | 00:44:00 | 00:45:31 |
| T-275-S1-a1-004604 | T-275 | S1 | claude | opus | 1 | done | 0 | 00:46:04 | 01:20:51 |
