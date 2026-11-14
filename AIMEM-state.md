# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)

- 정본은 `.aimem/aimem.db` 입니다. 이 파일을 손으로 고치지 마십시오. 생성 2026-11-15T02:34:34 / REV 183

## 2. 세션 명부

| 슬롯 | 확인토큰 | 하네스 | 모델 | 역할 | 비고 |
| --- | --- | --- | --- | --- | --- |
| S1 | `a41f0c` | claude | opus | R32 적대적 검수(T-335): 모니터 앱 서버 이어 주기 | 11-09 CLI 작업자. `claude -p --model opus`(=opus-5.5, 태석님 17:45) |
| S2 | `d27e93` | codex | kisti/kistillm | R30 대기 (일이 둘뿐 - 막힌 노드 받기) | 11-13 태석님 배정. 무료 작업자(공급자 kisti) |
| S3 | `5b8c1e` | opencode | opencode/deepseek-v4.1-flash-free | R32 만들기: 뉴스 정답 품질 결함·문서 (무료) | 11-13 태석님 배정. 무료 작업자(오픈코드 자체 공급, 키 없음) |
| S4 | `6cd650` | claude | sonnet | R32 빠른 구현: 모니터 app_server.py → server.py 잇기 | 11-09 17:30 태석님 배정. `claude -p --model sonnet`(=sonnet-5.5). 소유 경로는 태스크마다 6절에 등재 |
| S5 | `61dfcc` | claude | sonnet | R32 빠른 구현: 서버 정답 저장 → 화면 → 끝에서 끝 검사 |  |

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
| T-276 | Q-261113-bd56 | jamo.js: 칸 풀기·조합·두벌식 자판 표 | S2 | DONE |  |
| T-277 | Q-261113-bd56 | 낱말 목록: 원본 + build_words.py → words.js + test_words.py | S3 | DONE |  |
| T-278 | Q-261113-bd56 | game.js: 웹워들 로직을 6칸 자모로 | S2 | DONE |  |
| T-279 | Q-261113-bd56 | ui.js: 자모 자판·e.code 입력·미리보기·날마다/연습 | S2 | DONE |  |
| T-280 | Q-261113-bd56 | index.html·style.css·storage.js: 제목·도움말·모드·미리보기·6칸 | S3 | DONE |  |
| T-281 | Q-261113-bd56 | 단위 검사: test_jamo.mjs + test_game.mjs | S3 | DONE |  |
| T-282 | Q-261113-bd56 | 브라우저 검사 browser_game.py | S3 | DONE |  |
| T-283 | Q-261113-bd56 | 적대적 검수: 자모맞히기 1차 | S1 | DONE |  |
| T-284 | Q-261113-bd56 | 낱말 목록 손질 (R24-N1·N2·N3·N11) | S2 | DONE |  |
| T-285 | Q-261113-bd56 | ui.js 모드 오가기 정리 (R24-N4·N5·N6·N7·N8·N13) | S3 | DONE |  |
| T-286 | Q-261113-bd56 | storage.js 시스템 어두운 모드 + 접두어 시험 (R24-N9·N12) | S3 | DONE |  |
| T-287 | Q-261113-bd56 | 브라우저 회귀 검사 browser_modes.py (R24-N4~N9·N12·N13) | S3 | DONE |  |
| T-288 | Q-261113-bd56 | 재검수: R24-N1~N13 닫힘 + 목표 판정 | S1 | DONE |  |
| T-289 | Q-261113-bd56 | ui.js: 끝난 연습 판 유지 (T-287 NEEDS-FIX) | S3 | DONE |  |
| T-290 | Q-261113-bd56 | 추측 목록 보강 1000 + 오기·어근 빼기 (R24 재검수 N1·N2·N3) | S2 | DONE |  |
| T-291 | Q-261113-bd56 | 새 날 연습 정답 토스트 + 시험 빈틈 셋 (R24 재검수 N4·N6) | S3 | DONE |  |
| T-292 | Q-261113-bd56 | 3차 확인(가벼움) | S1 | DONE |  |
| T-293 | Q-261113-bd56 | 하드 모드 설정이 빈 판에 바로 닿게 (R24-N5 하) + 시험 | S3 | DONE |  |
| T-294 | Q-261113-bd56 | 추측 목록 갈래 1: 생활(음식·집·옷·몸·건강) 300개+ (R24-N1) | S2 | DONE |  |
| T-295 | Q-261113-bd56 | 추측 목록 갈래 2: 사회(학교·일·돈·교통·장소) 300개+ (R24-N1) | S3 | DONE |  |
| T-296 | Q-261113-bd56 | 추측 목록 갈래 3: 자연·마음(날씨·동식물·시간·감정·놀이) 300개+ (R24-N1) | S3 | DONE |  |
| T-297 | Q-261113-bd56 | 추측 목록 갈래 4: 풀이씨(동사·형용사 기본형) 250개+ (R24-N1) | S2 | DONE |  |
| T-298 | Q-261113-bd56 | build_words 가 data/words/*.txt 읽기 + test_words 2000·까닭·경계 6개 빼기 (R24-N1·N2·N3) | S2 | DONE |  |
| T-299 | Q-261113-bd56 | 적대적 검수: 새 표본으로 덮는 범위·지어낸 말 + N5 변이 + 목표 판정 | S1 | DONE |  |
| T-300 | Q-261113-292d | 낱말: 갈래 파일 어근 걷기·BANNED·까닭 MUST·ANSWERS 약속 시험 + 빠진 흔한 말 32개 (R27-N1·N2) | S4 | DONE |  |
| T-301 | Q-261113-292d | 브라우저: 연습 쪽 하드 맞춤·입력 중 글자 유지 시험 - V3·V6 (R27-N2) | S5 | DONE |  |
| T-302 | Q-261113-292d | tests/README.md 검사 수 갱신 (R27-N3) | S2 | DONE |  |
| T-303 | Q-261113-292d | 가벼운 적대적 재검수 + '검사' 목표 판정 | S1 | DONE |  |
| T-304 | Q-261114-23ef | 브라우저: 줄 낸 판 하드 잠금·빈 판 맞춤 판 번호 시험 - V16·V14 (R28-N1·N2) | S4 | DONE |  |
| T-305 | Q-261114-23ef | 낱말: 남은 어근 걷기·파일 훑기 + 빠진 흔한 말 30개 (R28-N3·N4) | S2 | DONE |  |
| T-306 | Q-261114-23ef | 가벼운 적대적 재검수: R28-N1~N4 | S1 | DONE |  |
| T-307 | Q-261114-a3cf | 브라우저: 하드 잠금 뒤 저장 설정 시험 - V19 (R29-N1) | S4 | DONE |  |
| T-308 | Q-261114-a3cf | 낱말: 배우다 보태기·words.js 재생성 (R29-N2) | S4 | DONE |  |
| T-309 | Q-261114-a3cf | 가벼운 적대적 재검수: R29-N1·N2 | S1 | DONE |  |
| T-310 | Q-261114-e40c | 브라우저 사전 모듈 web/js/dict.js + test_dict.mjs | S4 | DONE |  |
| T-311 | Q-261114-e40c | 사전 서버 dict_server.py + serve.py /api/lookup·/api/sources + 시험 | S5 | DONE |  |
| T-312 | Q-261114-e40c | 트렌드 정답 빌드: trend.txt → words.js TREND, game.js answerForDate(trend) | S6 | DONE |  |
| T-313 | Q-261114-e40c | 설정 화면 '외부 사전'·추측 흐름·저장 (ui·index·style·storage) | S4 | DONE |  |
| T-314 | Q-261114-e40c | 트렌드 정답 고르는 도구 tools/pick_answers.py (Gemini+검색, 사전 확인) + 시험 | S3 | DONE |  |
| T-315 | Q-261114-e40c | 모니터 /app/ CSP connect-src 에 app.json connect 목록 + 시험 | S5 | DONE |  |
| T-316 | Q-261114-e40c | 브라우저 사전 검사 browser_dict.py + tests/README | S5 | DONE |  |
| T-317 | Q-261114-e40c | 마지막 적대적 검수 (R31 외부 사전 전체) | S1 | DONE |  |
| T-318 | Q-261114-e40c | 고침: 사전에서 찾은 낱말이 진행 중인 판에 반영 안 됨(무한 재조회) | S4 | DONE |  |
| T-319 | Q-261114-e40c | 검수 후속 R31-N1·N3·N6: serve.py 교차 출처 막기·낱말 꼴·시험 독립 | S5 | DONE |  |
| T-320 | Q-261114-e40c | 검수 후속 R31-N2·N7: 키 저장 위험 안내·custom https 재확인 | S4 | DONE |  |
| T-321 | Q-261114-e40c | 검수 후속 R31-N4·N5: README 외부 사전 절·tests README | S6 | DONE |  |
| T-322 | Q-261114-e40c | 실물 결함: 추론 LLM(EXAONE) max_tokens 8 빈 답 - 서버 | S5 | DONE |  |
| T-323 | Q-261114-e40c | 실물 결함: 추론 LLM 빈 답 - 브라우저 dict.js | S4 | DONE |  |
| T-324 | Q-261114-e40c | 연합뉴스 RSS 정답 고르기: trend_news.py + /api/trend/pick + pick_answers.py 다시 씀 | S5 | DONE |  |
| T-325 | Q-261114-e40c | 설정 창 '지금 뉴스에서 정답 고르기' 단추·저장·날마다 정답 반영 + browser_trend.py | S4 | DONE |  |
| T-326 | Q-261114-e40c | 실물 한 번: 연합뉴스로 오늘부터 7일치 정답 + 브라우저 검사 TREND + README | S5 | DONE |  |
| T-327 | Q-261114-e40c | 가벼운 적대적 검수: 연합뉴스 정답 고르기 | S1 | DONE |  |
| T-328 | Q-261115-4aff | 서버가 정답 저장: trend_store.py + serve.py GET /api/trend·pick 저장 + pick_answers.py 같은 함수 | S5 | DONE |  |
| T-329 | Q-261115-4aff | 모니터: 앱 서버 관리 모듈 app_server.py (띄우기·다시 씀·이어 주기·내리기) | S4 | DONE |  |
| T-330 | Q-261115-4aff | 뉴스 정답 품질 결함 R31-N11~N14: RSS 2MB 상한·전체 마감·기업명/시군·조사 원형·checked 실제 수 | S3 | DONE |  |
| T-331 | Q-261115-4aff | 화면: 서버 정답 받아 쓰기·지난 시간 표시·jamo.trend 걷기·오늘 판 정답 고정(R31-N8)·서버 없음 글(R31-N10) | S5 | DONE |  |
| T-332 | Q-261115-4aff | 모니터: app.json server 선언 + /app/…/api/* 이어 주기·사전 요청·감사 로그·정리 잇기 | S4 | DONE |  |
| T-333 | Q-261115-4aff | 끝에서 끝: 자모맞히기 app.json server 선언 + 모니터 '앱 열기' 에서 정답 정하기·지난 시간 브라우저 검사 | S5 | DONE |  |
| T-334 | Q-261115-4aff | 문서: 프로젝트 README(서버 저장·모니터에서 서버)·tests/README 수 맞춤·EXAONE 429 안내 | S3 | DONE |  |
| T-335 | Q-261115-4aff | 적대적 검수: 모니터가 앱 serve.py 를 띄워 이어 주는 길 + 서버 정답 저장·화면 | S1 | DONE |  |
| T-336 | Q-261115-4aff | 검수 후속 R32-N1: trend_store 프로세스 사이 잠금(fcntl.flock) + 두 프로세스 검사 | S5 | DONE |  |
| T-337 | Q-261115-4aff | 검수 후속 R32-N2·N4·N6: cleanup_stale pid 확인 좁힘, server 바뀌면 다시 띄움, OPTIONS 티켓 먼저 | S4 | DONE |  |

## 4.5 대기 큐

| 순서 | 태스크 | 후보 슬롯 | 비고 |
| --- | --- | --- | --- |
| 1 | [함대] R32-N3·R32-N5 (하, rounds/R32/REVIEW-r32.md 5절): 같은 저장소를 모니터 둘이 보면 둘째의 cleanup_stale 이 첫째의 살아 있는 앱 서버를 내림 - 기록에 모니터 pid(owner)를 넣고 살아 있으면 건너뜀(R32-N3). 앱이 setsid 로 띄운 손자는 stop 뒤에도 남음 - /proc/<pid>/task/*/children 으로 거둠(R32-N5). 덧붙여 R32 마감 때 /tmp 임시 저장소의 가짜 앱 서버(projects/알파/serve.py) 하나가 고아로 남아 있었음 - 어느 검사·실험이 남겼는지 찾아 검사 tearDown 을 단단히 |  |  |

## 6. 파일 소유권

| 경로 패턴 | 쓰기 소유 | 비고 |
| --- | --- | --- |
| `(그 외 모든 경로)` | 미배정 | 배정 전 쓰기 금지. 아래 절차로 요청 |
| `.aimem.lock` | 미배정 | flock 대상. 내용을 쓰지 않고 unlink 금지 |
| `.aimem/aimem.db` | 관리자 | **운영 상태의 정본(전환 중)**. `.gitignore` 대상 - 커밋되는 것은 `AIMEM-state.md` 스냅샷 |
| `.aimem/archive/**` | 관리자 | 아카이브는 관리자만 씁니다 |
| `.aimem/briefs/**` | 관리자 | 관리자 세션 브리프와 참조 자료(예: `strata-tokens.css`). 작업자는 읽기만 |
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
| `projects/자모맞히기/README.md` | S3 | R32 |
| `projects/자모맞히기/app.json` | S5 | R32 |
| `projects/자모맞히기/data/**` | S2 | R24 T-284 |
| `projects/자모맞히기/data/README.md` | S4 | G-060 T-298 S2→S4 |
| `projects/자모맞히기/data/allowed.txt` | S4 | G-060 T-298 S2→S4 |
| `projects/자모맞히기/data/answers.txt` | S4 | G-060 T-298 S2→S4 |
| `projects/자모맞히기/data/trend.txt` | S5 | R31 |
| `projects/자모맞히기/data/trend_stop.txt` | S3 | R32 |
| `projects/자모맞히기/data/words/**` | S4 | R28 |
| `projects/자모맞히기/data/words/사회.txt` | S4 | G-060 T-295 S3→S4 |
| `projects/자모맞히기/data/words/자연마음.txt` | S4 | G-060 T-296 S3→S4 |
| `projects/자모맞히기/data/words/풀이씨.txt` | S4 | R30 T-308 S3→S4 |
| `projects/자모맞히기/dict_server.py` | S5 | R31 |
| `projects/자모맞히기/serve.py` | S5 | R32 |
| `projects/자모맞히기/tests/README.md` | S3 | R32 |
| `projects/자모맞히기/tests/browser_dict.py` | S5 | R31 |
| `projects/자모맞히기/tests/browser_game.py` | S5 | R31 |
| `projects/자모맞히기/tests/browser_harness.py` | S4 | R31 |
| `projects/자모맞히기/tests/browser_modes.py` | S5 | R31 |
| `projects/자모맞히기/tests/browser_trend.py` | S5 | R32 |
| `projects/자모맞히기/tests/test_dict.mjs` | S4 | R31 |
| `projects/자모맞히기/tests/test_dict_server.py` | S5 | R32 |
| `projects/자모맞히기/tests/test_game.mjs` | S4 | R31 |
| `projects/자모맞히기/tests/test_jamo.mjs` | S3 | R24 T-281 |
| `projects/자모맞히기/tests/test_logic.mjs` | S3 | R23 |
| `projects/자모맞히기/tests/test_pick_answers.py` | S5 | R32 |
| `projects/자모맞히기/tests/test_storage.mjs` | S5 | R32 |
| `projects/자모맞히기/tests/test_trend.mjs` | S5 | R32 |
| `projects/자모맞히기/tests/test_trend_news.py` | S3 | R32 |
| `projects/자모맞히기/tests/test_trend_store.py` | S5 | R32 후속 |
| `projects/자모맞히기/tools/**` | S2 | R24 T-284 |
| `projects/자모맞히기/tools/pick_answers.py` | S5 | R32 |
| `projects/자모맞히기/trend_news.py` | S3 | R32 |
| `projects/자모맞히기/trend_store.py` | S5 | R32 후속 |
| `projects/자모맞히기/web/css/**` | S3 | R24 T-280 |
| `projects/자모맞히기/web/css/style.css` | S5 | R32 |
| `projects/자모맞히기/web/index.html` | S5 | R32 |
| `projects/자모맞히기/web/js/app.js` | S2 | R23 |
| `projects/자모맞히기/web/js/dict.js` | S4 | R31 |
| `projects/자모맞히기/web/js/game.js` | S4 | R31 |
| `projects/자모맞히기/web/js/jamo.js` | S2 | R24 T-276 |
| `projects/자모맞히기/web/js/storage.js` | S5 | R32 |
| `projects/자모맞히기/web/js/trend.js` | S5 | R32 |
| `projects/자모맞히기/web/js/ui.js` | S5 | R32 |
| `projects/자모맞히기/web/js/words.js` | S5 | R31 |
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
| `rounds/R23/REVIEW-r23*.md` | S1 | R23 |
| `rounds/R24/REVIEW-r24-2.md` | S1 | R24 T-288 |
| `rounds/R24/REVIEW-r24-3.md` | S1 | R24 T-292 |
| `rounds/R24/REVIEW-r24.md` | S1 | R24 T-283 |
| `rounds/R25/REVIEW-r25.md` | S1 | R25 T-299 |
| `rounds/R26/REVIEW-r26.md` | S1 | R26 T-299 적대적 검수 |
| `rounds/R27/REVIEW-r27.md` | S1 | R27 T-299 |
| `rounds/R28/REVIEW-r28.md` | S1 | R28 |
| `rounds/R29/REVIEW-r29.md` | S1 | R29 |
| `rounds/R30/REVIEW-r30.md` | S1 | R30 |
| `rounds/R31/REVIEW-r31.md` | S1 | R31 |
| `rounds/R31/REVIEW-r31b.md` | S1 | R31 |
| `rounds/R32/REVIEW-r32.md` | S1 | R32 |
| `skills/**` | 관리자 | **현재 비어 있음** (REV 101 에서 `acp-slot-lifecycle` 제거). 되살아나면 이 행이 그대로 적용된다 |
| `tests/browser_monitor_app.py` | S3 | R10 T-131 |
| `tests/browser_monitor_app_server.py` | S5 | R32 |
| `tests/browser_monitor_auth.py` | S3 | R10 T-135 |
| `tests/browser_monitor_preview.py` | S2 | R14 T-185 웹워들 미리보기 보관함 브라우저 실측 (새 파일, app.js 보관함을 쓴 R13 S2 와 같은 슬롯이나 검사 대상은 R13 산출물) |
| `tests/browser_monitor_preview_guard.py` | S3 | R14 T-185 미리보기 보관함 방어 실측 (새 파일) |
| `tests/browser_monitor_tabs.py` | S3 | R17 T-223 프로젝트 탭·전역 정리 단추 실측 (새 파일, static 을 고친 S2 와 다른 슬롯) |
| `tests/browser_monitor_ui.py` | S3 | R13 T-170 화면 실측 (app.js 를 고친 S2 와 다른 슬롯) |
| `tests/browser_monitor_usage.py` | S3 | R18 T-233 사용 한도 카드 브라우저 실측 (새 파일, static 을 고친 S2 와 다른 슬롯) |
| `tests/test_aimem_db_cli.py` | S3 | R14 T-180 (aimem_db.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_aimem_lint.py` | S2 | T-005B. R5 에 S4 로 잠시 이관(KISTI 장애) → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_aimem_monitor*.py` | S2 | 웹 UI 계약 테스트. R5 에 S4 로 잠시 이관 → 2026-11-10 09:15 S2 복구로 환원(태석님 지시) |
| `tests/test_aimem_monitor_app.py` | S4 | R32 |
| `tests/test_aimem_monitor_app_proxy.py` | S4 | R32 후속 |
| `tests/test_aimem_monitor_app_server.py` | S4 | R32 후속 |
| `tests/test_archive_api.py` | S3 | R14 T-183 /api/archive 계약 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_fleet*.py` | S2 | `fleet.py` 회귀 테스트. 태석님 승인 2026-11-10 R6 브리프 (9절 2번 해소 - 승인 당시 S4 였으나 S2 복귀로 S2) |
| `tests/test_fleet_graph.py` | S3 | R19 T-243 한도 오인 회귀 시험 (fleet_graph.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_monitor_claude_usage.py` | S3 | R18 T-231 claude_usage 정리 단위 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_monitor_shutdown.py` | S3 | R20 T-252 SIGTERM 종료 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_monitor_ticket_regress.py` | S3 | R16 T-210 티켓 회귀 시험 (새 파일, server.py 를 고친 S2 와 다른 슬롯) |
| `tests/test_rt_claude.py` | S3 | R22 T-268 (claude.py 를 고친 S2 와 다른 슬롯) |
| `tools/aimem_db.py` | S2 | R14 T-177·T-178 끝난 것 정리와 연동한 기록 아카이브 (관리자→S2, 만들기·고치기는 무료 슬롯) |
| `tools/aimem_lint.py` | S1 | T-005A |
| `tools/aimem_monitor/__init__.py` | S2 | R10 |
| `tools/aimem_monitor/__main__.py` | 관리자 | 라운드 3 웹 UI. `python3 -m aimem_monitor` 진입점 |
| `tools/aimem_monitor/app_server.py` | S4 | R32 후속 |
| `tools/aimem_monitor/reader.py` | S2 | R13 T-166·T-168 goal 제거·ETA 수정 (S1 유료→S2 무료) |
| `tools/aimem_monitor/server.py` | S4 | R32 후속 |
| `tools/aimem_monitor/static/**` | S3 | 라운드 3 웹 UI. 정적 프런트엔드 (HTML/JS/CSS) |
| `tools/aimem_monitor/static/app.js` | S2 | R10 |
| `tools/aimem_monitor/static/index.html` | S2 | R13 T-167 KISTI 카드 제거 (app.js 와 같은 슬롯) |
| `tools/aimem_monitor/static/style.css` | S2 | R10 |
| `tools/aimem_monitor/static/sw.js` | S2 | R10 |
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
| Q-261113-bd56 | 한글 자모 낱말 맞히기 웹 게임 (새 프로젝트) | 태석 | DONE | 2026-11-13T14:24:03 |
| Q-261113-292d | 자모맞히기: 남은 목표 1개 이어 가기 (R27 뒤 자동) | 함대 이어 달리기 | DONE | 2026-11-13T23:20:46 |
| Q-261114-23ef | 자모맞히기: 대기 큐 1건 처리 (R28 뒤 자동) | 함대 이어 달리기 | DONE | 2026-11-14T00:18:27 |
| Q-261114-a3cf | 자모맞히기: 대기 큐 1건 처리 (R29 뒤 자동) | 함대 이어 달리기 | DONE | 2026-11-14T00:52:27 |
| Q-261114-e40c | 낱말 사전 외부 조회 | 태석 | DONE | 2026-11-14T23:34:06 |
| Q-261115-4aff | 모니터 '앱 열기' 에서 앱의 serve.py 를 띄워 서버 쪽 기능이 그대로 되게 (일반 장치, 큐 R31-P2 를 대신함) | 태석(클로드 코드) | DONE | 2026-11-15T01:47:14 |
