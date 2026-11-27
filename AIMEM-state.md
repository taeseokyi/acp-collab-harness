# AIMEM-state.md - 운영 상태 스냅샷 (읽기 전용, `python3 tools/aimem_db.py render` 가 생성)

- 정본은 `.aimem/aimem.db` 입니다. 이 파일을 손으로 고치지 마십시오. 생성 2026-11-28T00:13:20 / REV 209

## 2. 세션 명부

| 슬롯 | 확인토큰 | 하네스 | 모델 | 역할 | 비고 |
| --- | --- | --- | --- | --- | --- |
| S1 | `a41f0c` | claude | opus | R52 쉼 (무료 중심) | 11-09 CLI 작업자. `claude -p --model opus`(=opus-5.5, 태석님 17:45) |
| S2 | `d27e93` | codex | kisti/kistillm | R52 VoxLog 지난 글 여러 벌: 브라우저 검사·serve 응답 검사 | 무료 |
| S3 | `5b8c1e` | opencode | kisti/kistillm | R52 VoxLog 지난 글 여러 벌: store.py·단위 검사·문서 | 무료 |
| S4 | `6cd650` | claude | sonnet | R52 VoxLog 적대적 검수(부작용 중심) | 유료, 검수만 |
| S5 | `61dfcc` | claude | sonnet | R52 쉼 (무료 중심) |  |
| S6 | `47764b` | freebuff | (하네스 기본) | R52 VoxLog 지난 글 여러 벌: 화면(web/) | 무료 |

## 3. 작업 보드

| ID | 요청 | 태스크 | 담당 | 상태 | 산출물 |
| --- | --- | --- | --- | --- | --- |
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
| T-338 | Q-261116-fa85 | VoxLog 저장소 store.py + 단위 검사 | S3 | DONE |  |
| T-339 | Q-261116-fa85 | VoxLog 음성인식 stt.py + 가짜 받아쓰기 + 단위 검사 | S6 | DONE |  |
| T-340 | Q-261116-fa85 | VoxLog 클로드 묻기 ask.py + 가짜 LLM + 단위 검사 | S7 | DONE |  |
| T-341 | Q-261116-fa85 | VoxLog 화면: 녹음·현황·목록·상세·묻기·설정 | S4 | DONE |  |
| T-342 | Q-261116-fa85 | VoxLog serve.py: 정적 + API + 토큰·TLS + 단위 검사 | S5 | DONE |  |
| T-343 | Q-261116-fa85 | VoxLog 서비스 워커·업로드 대기열·매니페스트·아이콘 | S5 | DONE |  |
| T-344 | Q-261116-fa85 | VoxLog 끝에서 끝 브라우저 검사 | S4 | DONE |  |
| T-345 | Q-261116-fa85 | R33 적대적 검수: VoxLog + 앱 서버 정리 | S1 | DONE |  |
| T-346 | Q-261116-fa85 | [함대] 큐 R32-N3·N5 앱 서버 정리 | S8 | DONE |  |
| T-347 | Q-261116-fa85 | 검수 후속 N1·N4·N5·N9 + 위치: 대기열·serve.py | S5 | DONE |  |
| T-348 | Q-261116-fa85 | 검수 후속 N3·N6 + 위치: ask.py | S7 | DONE |  |
| T-349 | Q-261116-fa85 | 검수 후속 N7·N17: 앱 서버 pid 시작 시각 | S5 | DONE |  |
| T-350 | Q-261116-fa85 | 검수 후속 N1·N2·N4·N8·N10~N12 + 위치: 화면·브라우저 검사 | S4 | DONE |  |
| T-351 | Q-261116-fa85 | R33 재검수 | S1 | DONE |  |
| T-352 | Q-261116-fa85 | 요청 수정 반영: store.py 위치정보 | S3 | DONE |  |
| T-353 | Q-261116-fa85 | 재검수 후속 N18·N19·N20·N12: 살린 녹음 위치·이어 녹음·검사 틈 | S4 | DONE |  |
| T-354 | Q-261116-r34q | stt.py: resubmit/busy(N13)·ffmpeg 형식 강제(N15) | S3 | DONE |  |
| T-355 | Q-261116-r34q | store.py: 업로드 파일 받기·메타 잠금·목록 캐시(N14) | S4 | DONE |  |
| T-356 | Q-261116-r34q | 화면: 서버 주소 설정 빼기(N16)·503/507 재시도 | S5 | DONE |  |
| T-357 | Q-261116-r34q | serve.py: retry 409(N13)·업로드 흘려 쓰기·503·507(N14) | S5 | DONE |  |
| T-358 | Q-261116-r34q | R34 적대적 검수 | S1 | DONE |  |
| T-359 | Q-261116-r34q | 검수 후속 R34-N1·N2: retry 판정·전사 실패 처리 | S5 | DONE |  |
| T-360 | Q-261116-r34q | 검수 후속 R34-N3·N5·N7: 검사 21번·Retry-After·문서 | S4 | DONE |  |
| T-361 | Q-261117-r35q | [VoxLog] R34-N6 업로드 전체 마감(408)·저장 OSError 500/507 | S4 | DONE |  |
| T-362 | Q-261117-r35q | [VoxLog] R34-N4 실제 서버 503 브라우저 검사(22번) | S5 | DONE |  |
| T-363 | Q-261117-r35q | [VoxLog] INTERFACE.md 업로드 408·500/507·연결 오류 | S3 | DONE |  |
| T-364 | Q-261117-r35q | [VoxLog] R35 적대적 검수 | S1 | DONE |  |
| T-365 | Q-261117-r36q | [VoxLog] R35-N1 진척 기준 업로드 마감·R35-N3 incoming mkdir OSError | S4 | DONE | projects/VoxLog/serve.py,projects/VoxLog/tests/test_serve.py |
| T-366 | Q-261117-r36q | [VoxLog] R35-N2 408 도 Retry-After 뒤 재시도 + 브라우저 검사 24번 | S5 | DONE | projects/VoxLog/web/queue.js,projects/VoxLog/web/sw.js,projects/VoxLog/tests/browser_voxlog.py |
| T-367 | Q-261117-r36q | [VoxLog] INTERFACE.md 진척 마감·408 재시도·mkdir 오류 | S3 | DONE | projects/VoxLog/docs/INTERFACE.md |
| T-368 | Q-261117-r36q | [VoxLog] R36 적대적 검수 | S1 | DONE | rounds/R36/REVIEW-r36.md |
| T-369 | Q-261123-f11a | [자모맞히기] 코드 검수: 서버 쪽 파이썬 (S6 freebuff 시험) | S6 | DONE |  |
| T-370 | Q-261123-f11a | [자모맞히기] 코드 검수: 화면 쪽 web (S6 freebuff 시험) | S6 | DONE |  |
| T-371 | Q-261123-018e | [VoxLog] 코드 검수: 서버 쪽 파이썬 (S6 freebuff 이어 가기 시험) | S6 | DONE | rounds/R38/REVIEW-r38-s6.md |
| T-372 | Q-261123-6bf6 | [VoxLog] R38-N1(상) HEAD 요청이 녹음을 지움 | S6 | DONE |  |
| T-373 | Q-261123-6bf6 | [VoxLog] R38-N2·N3·N6 오류를 연결 끊김 대신 JSON 으로 | S6 | DONE |  |
| T-374 | Q-261123-6bf6 | [VoxLog] R38-N4·N5 녹음 시각·날짜 검사, 프롬프트 시각 정렬 | S6 | DONE |  |
| T-375 | Q-261123-6bf6 | [자모맞히기] R37-N1 words.js 를 trend.txt 에 맞춰 다시 만들기 | S6 | DONE |  |
| T-376 | Q-261123-6bf6 | [자모맞히기] R37-N2 6칸 아닌 트렌드 정답 거르기 + 시작 실패 안내 | S6 | DONE |  |
| T-377 | Q-261123-6bf6 | [자모맞히기] R37-N3·N4 serve.py 예외를 JSON 500 으로, 0줄 덧붙임 안내 | S6 | DONE |  |
| T-378 | Q-261123-6bf6 | [자모맞히기] R37-N5~N9 Origin 없는 GET·verify opener·출처 안내·'네'·화면 복잡도 | S6 | DONE |  |
| T-379 | Q-261123-6bf6 | [VoxLog·자모맞히기] R39 적대적 검수 (S6 수정 7건) | S1 | DONE |  |
| T-380 | Q-261123-7d3e | [VoxLog] 화면 쪽 검수: web/ 6파일 (S6 세션 이어 가기 시험 1/2) | S6 | DONE |  |
| T-381 | Q-261123-7d3e | [VoxLog] 검사·문서 대조 검수: INTERFACE.md ↔ serve.py·voxlog/·tests/ (S6 세션 이어 가기 시험 2/2) | S6 | DONE | 실행 안 됨 - 일은 R41 T-382 로 다시 냄(큐 6) |
| T-382 | Q-261124-9281 | [VoxLog] 문서 대조 검수: INTERFACE.md ↔ serve.py·voxlog/·tests/ (S6 1/3, 큐 6) | S6 | DONE |  |
| T-383 | Q-261124-9281 | [VoxLog] R39-N1·N2·N4 고치기 (S6 2/3, 큐 2) | S6 | DONE |  |
| T-384 | Q-261124-9281 | [VoxLog] R40-N1·N2·N3 고치기 (S6 3/3, 큐 4·5) | S6 | DONE |  |
| T-385 | Q-261124-9281 | [VoxLog] R41 적대적 검수 (S3 빈손 - /tmp 권한 거절) | S3 | DONE |  |
| T-386 | Q-261124-9281 | [VoxLog] R41 적대적 검수 재시도 (불합격) | S2 | DONE |  |
| T-387 | Q-261124-9281 | [VoxLog] R41 검수 수정: 초안 lease·업로드 엄격 판정·검사 | S2 | DONE |  |
| T-388 | Q-261124-9281 | [VoxLog] R41 재검수 (조건부 통과) | S3 | DONE |  |
| T-389 | Q-261124-7f0b |  | - | DONE |  |
| T-390 | Q-261124-e24b |  | - | DONE |  |
| T-391 | Q-261124-e24b | [VoxLog] R41-N13~N18 초안 회수 고치기 - 되돌림, 웹 잠금 전환(R44)으로 대체됨 | - | DONE |  |
| T-392 | Q-261124-e24b |  | - | DONE |  |
| T-393 | Q-261124-e24b |  | - | DONE |  |
| T-394 | Q-261124-e24b |  | - | DONE |  |
| T-395 | Q-261124-e24b |  | - | DONE |  |
| T-396 | Q-261124-e24b |  | - | DONE |  |
| T-397 | Q-261124-795c | [VoxLog] 조사 문서: 초안 주인 판정의 표준 방식 (docs/RESEARCH-draft-owner.md) | S2 | DONE | projects/VoxLog/docs/RESEARCH-draft-owner.md |
| T-398 | Q-261124-795c | [VoxLog] R42-N2 store.set_job 64자 자름 제거 | S3 | DONE | projects/VoxLog/voxlog/store.py |
| T-399 | Q-261124-795c | [VoxLog] R42-N3 ask 본문 검사: 까닭 문구·유효한 ids·절대 마감 변이 | S3 | DONE | projects/VoxLog/tests/test_serve_ask_body.py |
| T-400 | Q-261124-795c | [VoxLog] R43 적대적 검수 (조건부 통과) | S4 | DONE |  |
| T-401 | Q-261124-795c | [VoxLog] R43-N1~N4 조사 문서 수정 | S2 | DONE | projects/VoxLog/docs/RESEARCH-draft-owner.md |
| T-402 | Q-261124-795c | [VoxLog] R43 재검수 (조건부 통과, R43-N6~N8 큐) | S4 | DONE |  |
| T-403 | Q-261124-b4ad | [VoxLog] queue.js 웹 잠금 전환·lease 걷어냄·기다리는 회수·R41-N16 | S2 | DONE |  |
| T-404 | Q-261124-b4ad | [VoxLog] app.js lease 타이머·22초 재시도 제거·R41-N18·늦은 회수 알림 | S2 | DONE |  |
| T-405 | Q-261124-b4ad | [VoxLog] 브라우저 검사: 웹 잠금 회수·열화·전환기 | S2 | DONE |  |
| T-406 | Q-261124-b4ad | [VoxLog] README·INTERFACE.md 웹 잠금·열화 | S2 | DONE |  |
| T-407 | Q-261124-b4ad | [VoxLog] 조사 문서 R43-N6~N8 정리 | S6 | DONE |  |
| T-408 | Q-261124-b4ad | [VoxLog] R44 적대적 검수(부작용 중심) | S4 | DONE |  |
| T-409 | Q-261124-ba96 | [주보알림] bulletin.py: 확인·미리 보기·전송·기록 논리 (ref 스크립트를 그대로 부름) | S2 | DONE | projects/주보알림/bulletin.py |
| T-410 | Q-261124-ba96 | [주보알림] serve.py·화면(web/)·app.json - 화면 하나, 확인·미리 보기·카톡 보내기·보낸 기록 | S3 | DONE | projects/주보알림/serve.py,projects/주보알림/web/,projects/주보알림/app.json |
| T-411 | Q-261124-ba96 | [주보알림] bulletin.preview(): 실제 전송과 같은 쪽·순서(maria 1~7쪽, bstsd 내림차순)와 seq | S2 | DONE | projects/주보알림/bulletin.py |
| T-412 | Q-261124-ba96 | [주보알림] 화면: 미리 보기를 카톡 대화방에 그림이 온 것처럼 (seq 순서, 묶음 말풍선) | S3 | DONE | projects/주보알림/web/ |
| T-413 | Q-261124-ba96 | [주보알림] 실물 시험: 앱으로 확인·미리 보기·카톡 보내기 한 번 (실제 전송) | S2 | DONE | projects/주보알림/data/history.json |
| T-416 | Q-261124-f310 | [VoxLog] R43-N5 _read_body 두 분기 검사 보강 + R44-N2 조사 문서 옛 문장 | S2 | DONE | projects/VoxLog/tests/test_serve_ask_body.py, projects/VoxLog/docs/RESEARCH-draft-owner.md |
| T-417 | Q-261124-f310 | [VoxLog] R44-N1 녹음 시작 실패 때 초안 잠금 정리 + R44-N3 pageshow 는 bfcache 복원 때만 회수 | S3 | DONE | projects/VoxLog/web/app.js, projects/VoxLog/web/queue.js, projects/VoxLog/tests/browser_voxlog.py |
| T-418 | Q-261124-f310 | [VoxLog] R46 적대적 검수 (부작용 중심) - T-416·T-417 | S4 | DONE | .aimem/sessions/T-418-S4-a1-233913/report.md |
| T-419 | Q-261125-f9f0 | [VoxLog] R46-N1 문서의 'resume·pageshow 에서 회수' 서술을 지금 코드(pageshow 는 persisted 일 때만)에 맞추기 | S2 | DONE | projects/VoxLog/docs/INTERFACE.md, projects/VoxLog/docs/RESEARCH-draft-owner.md |
| T-420 | Q-261125-f9f0 | [VoxLog] R47 적대적 검수 - T-419 문서 + R46-N2 추정 독립 확인 | S4 | DONE | .aimem/sessions/T-420-S4-a1-001546/report.md |
| T-421 | Q-261125-5fa4 | [VoxLog] S2 가 VoxLog 를 써 보고 추가 기능 아이디어 둘 (구현 안 함) | S2 | DONE | rounds/R48/ideas.md |
| T-422 | Q-261125-5fa4 | [VoxLog] S3 가 VoxLog 를 써 보고 추가 기능 아이디어 둘 (구현 안 함) | S3 | DONE | rounds/R48/ideas.md |
| T-423 | Q-261125-5fa4 | [VoxLog] S6 가 VoxLog 를 써 보고 추가 기능 아이디어 둘 (구현 안 함) | S6 | DONE | rounds/R48/ideas.md |
| T-424 | Q-261125-5fa4 | [VoxLog] S2 가 남의 아이디어 넷(I3~I6)에 의견 (구현 안 함) | S2 | DONE | rounds/R48/decision.md |
| T-425 | Q-261125-5fa4 | [VoxLog] S3 가 남의 아이디어 넷(I1·I2·I5·I6)에 의견 (구현 안 함) | S3 | DONE | rounds/R48/decision.md |
| T-426 | Q-261125-5fa4 | [VoxLog] S6 가 남의 아이디어 넷(I1~I4)에 의견 (구현 안 함) | S6 | DONE | rounds/R48/decision.md |
| T-427 | Q-261125-5fa4 | [VoxLog] 다음 기능 설계 문서 docs/DESIGN-next-features.md (F1 출처·F2 이름과 태그·F3 이어 묻기 + 아이디어 전체와 의견) | S2 | DONE | projects/VoxLog/docs/DESIGN-next-features.md |
| T-428 | Q-261125-5fa4 | [VoxLog] R48 적대적 검수 - 설계 문서가 코드·결정과 맞는지, 기존 기능을 해치는 설계가 없는지 | S4 | DONE | .aimem/sessions/T-428-S4-a1-012943/report.md |
| T-429 | Q-261125-5fa4 | [VoxLog] 설계 문서에 R48 검수 지적 중 8건(R48-N1~N8) 반영 | S2 | DONE | projects/VoxLog/docs/DESIGN-next-features.md |
| T-430 | Q-261125-5fa4 | [VoxLog] R48 재검수 - R48-N1~N8 반영이 맞는지와 고치며 생긴 새 문제 | S4 | DONE | .aimem/sessions/T-430-S4-a1-014911/report.md |
| T-431 | Q-261125-5fa4 | [VoxLog] 설계 문서에 재검수 지적 중 3건(R48-N15~N17) 반영 | S2 | DONE | projects/VoxLog/docs/DESIGN-next-features.md |
| T-432 | Q-261125-5fa4 | [VoxLog] R48 재검수 2 - R48-N15~N17 반영과 새 문제 | S4 | DONE | .aimem/sessions/T-432-S4-a1-015855/report.md |
| T-433 | Q-261125-76c8 | [VoxLog] F2 voxlog/tags.py - 이름·태그 정규화와 모델 출력에서 태그 뽑기 + tests/test_tags.py | S2 | DONE |  |
| T-434 | Q-261125-76c8 | [VoxLog] F2 store.py - label·tags·tags_auto·tags_human·autotag 저장, set_label_tags·set_auto_tags·set_autotag, list(tag, q 확장, match) + test_store.py | S3 | DONE |  |
| T-435 | Q-261125-76c8 | [VoxLog] F2 자동 태그 일꾼 - ask.py build_tag_prompt·llm_status·Asker 우선순위 큐·submit_tag, stt.py on_done + 검사 | S2 | DONE |  |
| T-436 | Q-261125-76c8 | [VoxLog] F2 serve.py - PATCH /api/recordings/<id>, POST …/autotag, ?tag=, 받아쓰기 뒤 자동 태그 연결 + test_serve.py·fake_llm.py | S3 | DONE |  |
| T-437 | Q-261125-76c8 | [VoxLog] F2 화면 뼈대 - index.html 요소·style.css 칩과 편집 블록(폰 320px·어두운 모드)·sw.js VERSION | S6 | DONE |  |
| T-438 | Q-261125-76c8 | [VoxLog] F2 app.js - 목록 이름·칩·태그 거르기, 상세 이름·태그 편집·저장·태그 다시 달기·자동 태그 상태 | S2 | DONE |  |
| T-439 | Q-261125-76c8 | [VoxLog] F2 브라우저 검사 t42(손 편집·칩·거르기·검색·넘침) t43(자동 태그·사람 손댐 보호·다시 달기) t44(LLM 없음) | S6 | DONE |  |
| T-440 | Q-261125-76c8 | [VoxLog] F2 문서 - 설계 문서 F2 절·'보류한 것' I3 를 결정대로, INTERFACE.md·README 맞추기 | S6 | DONE |  |
| T-441 | Q-261125-76c8 | [VoxLog] R49 적대적 검수 (부작용 중심) - F2 이름·태그·자동 태그 T-433~T-440 | S4 | DONE | .aimem/sessions/T-441-S4-a1-135833/report.md |
| T-442 | Q-261125-76c8 | [VoxLog] R49-N2·N3·N4 고치기 - 태그 뽑기가 사과·머리말을 거름, 태그 호출 60초 상한, 도는 중 다시 받아쓰기면 한 번 더 | S2 | DONE |  |
| T-443 | Q-261125-76c8 | [VoxLog] R49-N1 서버 쪽 - set_label_tags 가 태그가 그대로면 tags_human 을 켜지 않음 + 느린 가짜 LLM | S3 | DONE |  |
| T-444 | Q-261125-76c8 | [VoxLog] R49-N1 화면 쪽 - saveLabels 가 태그 입력이 바뀌었을 때만 tags 를 보냄 | S2 | DONE |  |
| T-445 | Q-261125-76c8 | [VoxLog] R49-N1 브라우저 검사 - 이름만 저장해도 자동 태그가 이어짐, 자동 태그 기다리는 중 저장해도 AI 태그가 붙음 | S6 | DONE |  |
| T-446 | Q-261125-76c8 | [VoxLog] R49 재검수 - R49-N1~N4 고침이 맞는지, 고치며 생긴 새 문제, 변이 검사 | S4 | DONE | .aimem/sessions/T-446-S4-a1-163102/report.md |
| T-447 | Q-261126-902f | [VoxLog] 화면 큐 고치기 - R49-N5 받아쓰기 끝 순간 자동 태그 폴링, R49-N6 폴링 오류 뒤 굳음, R48-N24 webm 길이 Infinity, R49-N9 검사 항등식 | S2 | DONE | projects/VoxLog/web/app.js, projects/VoxLog/tests/test_ask.py |
| T-448 | Q-261126-902f | [VoxLog] R49-N11 store.set_label_tags - 대소문자만 바뀐 태그는 표기만 갱신 | S3 | DONE | projects/VoxLog/voxlog/store.py, projects/VoxLog/tests/test_store.py |
| T-449 | Q-261126-902f | [VoxLog] 문서 큐 정리 - 설계 문서 R48-N9~N22 반영, R48-N23 결론, R47-N1 persisted 단서, R49-N7·N8 INTERFACE | S3 | DONE | projects/VoxLog/docs/DESIGN-next-features.md, projects/VoxLog/docs/RESEARCH-draft-owner.md, projects/VoxLog/docs/INTERFACE.md |
| T-450 | Q-261126-902f | [VoxLog] 브라우저 검사 t46~t48 - webm 길이, 받아쓰기 끝 순간 AI 태그, 폴링 오류 뒤 이어짐 + 셸 캐시 VERSION | S6 | DONE | projects/VoxLog/tests/browser_voxlog.py, projects/VoxLog/web/sw.js |
| T-451 | Q-261127-8d1e | [VoxLog] 받아쓰기 옵션 거르기 모듈 voxlog/stt_options.py + 단위 검사 | S3 | DONE |  |
| T-452 | Q-261127-8d1e | [VoxLog] store.py - 녹음별·전체 기본 옵션, stt_used, 이전 글 한 벌 | S3 | DONE |  |
| T-453 | Q-261127-8d1e | [VoxLog] stt.py - 옵션 필드 보내기, 400 글 읽기, 쓰인 옵션 받기, Transcriber options_fn | S2 | DONE |  |
| T-454 | Q-261127-8d1e | [VoxLog] serve.py - GET/PUT /api/stt-options, retry 에 옵션 본문 | S2 | DONE |  |
| T-455 | Q-261127-8d1e | [VoxLog] 화면 - 설정 칸 받아쓰기 기본 옵션, 상세 '옵션 바꿔 다시 받아쓰기', 쓰인 옵션·이전 글 | S6 | DONE |  |
| T-456 | Q-261127-8d1e | [VoxLog] 브라우저 검사 t49~t52 - 옵션 화면이 실제 요청으로 나가는지, 이전 글, 320px | S2 | DONE |  |
| T-457 | Q-261127-8d1e | [VoxLog] 문서 - INTERFACE.md·README 에 받아쓰기 옵션 | S3 | DONE |  |
| T-458 | Q-261127-8d1e | [VoxLog] R51 적대적 검수 - 받아쓰기 옵션(부작용 중심) | S4 | DONE | rounds/R51/REVIEW-r51.md |
| T-459 | Q-261127-8d1e | [VoxLog] R51-N1 이전 글은 밀려난 글 중 가장 긴 것을 지킴 + 실패해도 글이 남는 검사 | S3 | DONE |  |
| T-460 | Q-261127-8d1e | [VoxLog] R51-N2 다시 받아쓰기는 남은 작업 id 를 지우고 새로 맡김, R51-N3 빈 옵션은 전체 기본값을 따름 | S2 | DONE |  |
| T-461 | Q-261127-8d1e | [VoxLog] R51-N3 화면 - 옵션 묶음을 실제로 쓰일 값으로 채움, 이전 글 안내문 맞춤 | S6 | DONE |  |
| T-462 | Q-261127-8d1e | [VoxLog] 브라우저 검사 t53~t55 - 폴링이 열어 둔 옵션 입력을 안 지움, 상세 옵션이 전체 기본값으로 채워짐, 재시도 400 의 서버 글 | S2 | DONE |  |
| T-463 | Q-261127-8d1e | [VoxLog] R51 재검수 - N1~N3 고침이 맞는지, 고치며 생긴 새 문제, 변이 | S4 | DONE | rounds/R51/REVIEW-r51-2.md |
| T-464 | Q-261127-8d1e | [VoxLog] 실물 확인 - 안내방송 녹음을 따로 띄운 서버의 웹에서 denoise 로 다시 받아쓰기 | S6 | DONE | rounds/R51/REAL-CHECK.md |
| T-465 | Q-261127-8d1e | [VoxLog] R51-N9 화면 - '기본' 이름을 묶음마다 뜻대로, 녹음 옵션은 합치지 않음 안내, 이전 글 요약 이름 | S6 | DONE |  |
| T-466 | Q-261127-8d1e | [VoxLog] R51-N9·N12·N10 - effective_stt_options 가 빈 옵션을 없음으로, 문서를 고친 동작에 맞춤 | S3 | DONE |  |
| T-467 | Q-261127-8d1e | [VoxLog] R51 재검수 2 - N9 문구·빈 옵션 규칙·문서 | S4 | DONE | rounds/R51/REVIEW-r51-3.md |
| T-468 | Q-261127-8f71 | [VoxLog] store.py 지난 글 여러 벌(.prev.json·상한 5·같은 글 안 늘림·옛 .prev.txt 이어받기) + 단위 검사 | S3 | DONE | projects/VoxLog/voxlog/store.py, projects/VoxLog/tests/test_store.py |
| T-469 | Q-261127-8f71 | [VoxLog] 화면 - 상세 '지난 글 N벌' 목록(받아쓴 때·옵션), 안내 문구, 셸 캐시 VERSION | S6 | DONE | projects/VoxLog/web/app.js, index.html, style.css, sw.js |
| T-470 | Q-261127-8f71 | [VoxLog] 문서 - INTERFACE.md·README.md 의 이전 글 규칙을 판 기록으로 (R51-N14 포함) | S3 | DONE | projects/VoxLog/docs/INTERFACE.md, projects/VoxLog/README.md |
| T-471 | Q-261127-8f71 | [VoxLog] 검사 - test_serve 응답 키, 브라우저 t51 고침 + t56(A→B→C 둘 다 보임·옵션)·t57(옛 .prev.txt 가 지난 글로) | S2 | DONE | projects/VoxLog/tests/test_serve.py, projects/VoxLog/tests/browser_voxlog.py |
| T-472 | Q-261127-8f71 | [VoxLog] R52 적대적 검수 - 지난 글 여러 벌(부작용 중심) | S4 | DONE | rounds/R52/REVIEW-r52.md |
| T-473 | Q-261127-8f71 | [VoxLog] R52-N1 받아쓰기 결과가 빈 글이면 실패로 - 지금 글·지난 글 그대로 | S2 | DONE | projects/VoxLog/voxlog/stt.py, projects/VoxLog/tests/test_stt.py |
| T-474 | Q-261127-8f71 | [VoxLog] R52 재검수 - N1 고침과 고치며 생긴 새 문제 | S4 | DONE | rounds/R52/REVIEW-r52-2.md |

## 4.5 대기 큐

| 순서 | 태스크 | 후보 슬롯 | 비고 |
| --- | --- | --- | --- |
| 1 | [VoxLog] R51 검수 하 등급 묶음: R51-N4 깊은 중첩 JSON 이 400 대신 연결 끊김(RecursionError, PUT stt-options·retry·PATCH 세 곳), R51-N5 context 의 제로폭·제어 문자 거르기, R51-N6 설정 기본값 캐시가 낡음·설정 칸 다시 열면 입력 덮임, R51-N7 재시도 실패 시 옵션 되돌림의 좁은 틈·다른 녹취로 옮긴 뒤 묶음 숨김. 검사 구멍 넷(검수 변이 표의 폴링이 이전 글 펼침 접음·격리 출처 숨김·토스트 innerHTML·옵션 복구). 원문 rounds/R51/REVIEW-r51.md | S2/S3 무료 |  |
| 2 | [VoxLog] R51 재검수 하 등급 묶음: R51-N11 겹친 두 재시도가 진행 중 작업 id 를 지울 수 있는 좁은 틈(set_job(None) 을 resubmit 잠금 안으로), R51-N12 resubmit 실패 시 옵션 복구 검사 없음. 원문 rounds/R51/REVIEW-r51-2.md | S2 무료 |  |
| 3 | [VoxLog] R51 재검수 2 하 등급 묶음: R51-N13 녹음에 다른 옵션이 있을 때 상세 칸의 '기본(앱 설정 따름)' 이름이 틀림, R51-N15 새 문구를 잡는 검사 없음 (R51-N14 는 R52 T-470 에서 닫힘). 원문 rounds/R51/REVIEW-r51-3.md | S3·S6 무료 |  |
| 4 | [VoxLog] R52 검수 하 등급 묶음: R52-N2 같은 글 중복 제거 (2) 가 정상 경로로 안 닿고 검사도 없음(지울지·검사할지), R52-N3 깨진 .prev.json 이 옛 .prev.txt 를 가려 다음 쓰기에 옛 글이 사라짐, R52-N4 옛 .prev.txt 가 지금 글과 같으면 지난 글에 또 보임, R52-N5 큰 글 5벌이면 상세 응답이 커지고 받아쓰는 동안 5초마다 되풀이(지난 글을 따로 받는 API 는 후속 거리), R52-N6 검사 구멍(지난 글 본문 XSS·공백만 다른 글·'5벌까지' 문구가 PREV_KEEP 와 따로 놂). 원문 rounds/R52/REVIEW-r52.md | S2·S3 무료 |  |
| 5 | [VoxLog] R52 재검수 하 등급 묶음: R52-N7 문서(INTERFACE·README)가 '빈 받아쓰기 결과는 실패' 를 말하지 않음, R52-N8 재시도가 빈 결과로 실패하면 '실패' 줄 옆에 옛 글의 N자가 보이고 무음 파일 안내가 없음, R52-N9 옛 done+빈 글 자료와 '(빈 글)' 문구, R52-N10 빈 결과 실패의 화면 검사 없음·문구가 두 곳에 박힘·on_done 앞 strip 군더더기. 원문 rounds/R52/REVIEW-r52-2.md | S3·S6 무료 |  |

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
| `projects/VoxLog/README.md` | S3 | R52 |
| `projects/VoxLog/docs/**` | S6 | R39 |
| `projects/VoxLog/docs/DESIGN-next-features.md` | S3 | R50 |
| `projects/VoxLog/docs/INTERFACE.md` | S3 | R52 |
| `projects/VoxLog/docs/RESEARCH-draft-owner.md` | S3 | R50 |
| `projects/VoxLog/serve.py` | S2 | R52 |
| `projects/VoxLog/settings.example.json` | S2 | R44 |
| `projects/VoxLog/tests/**` | S6 | R39 |
| `projects/VoxLog/tests/browser_voxlog.py` | S2 | R52 |
| `projects/VoxLog/tests/fake_llm.py` | S3 | R49 |
| `projects/VoxLog/tests/fake_tag_llm.py` | S2 | R49 |
| `projects/VoxLog/tests/test_ask.py` | S2 | R49 |
| `projects/VoxLog/tests/test_serve.py` | S2 | R52 |
| `projects/VoxLog/tests/test_serve_ask_body.py` | S2 | R46 |
| `projects/VoxLog/tests/test_store.py` | S3 | R52 |
| `projects/VoxLog/tests/test_stt.py` | S2 | R52 |
| `projects/VoxLog/tests/test_stt_options.py` | S3 | R51 |
| `projects/VoxLog/tests/test_tags.py` | S2 | R49 |
| `projects/VoxLog/voxlog/**` | S6 | R39 |
| `projects/VoxLog/voxlog/__init__.py` | S3 | R33 |
| `projects/VoxLog/voxlog/ask.py` | S2 | R49 |
| `projects/VoxLog/voxlog/store.py` | S3 | R52 |
| `projects/VoxLog/voxlog/stt.py` | S2 | R52 |
| `projects/VoxLog/voxlog/stt_options.py` | S3 | R51 |
| `projects/VoxLog/voxlog/tags.py` | S2 | R49 |
| `projects/VoxLog/web/**` | S4 | R34 |
| `projects/VoxLog/web/api.js` | S6 | R41 |
| `projects/VoxLog/web/app.js` | S6 | R52 |
| `projects/VoxLog/web/icons/**` | S5 | R33 |
| `projects/VoxLog/web/index.html` | S6 | R52 |
| `projects/VoxLog/web/manifest.webmanifest` | S5 | R33 |
| `projects/VoxLog/web/queue.js` | S3 | R46 |
| `projects/VoxLog/web/style.css` | S6 | R52 |
| `projects/VoxLog/web/sw.js` | S6 | R52 |
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
| `projects/자모맞히기/dict_server.py` | S6 | R39 |
| `projects/자모맞히기/serve.py` | S6 | R39 |
| `projects/자모맞히기/tests/**` | S6 | R39 |
| `projects/자모맞히기/tests/README.md` | S6 | R42 |
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
| `projects/자모맞히기/tools/**` | S6 | R39 |
| `projects/자모맞히기/tools/pick_answers.py` | S5 | R32 |
| `projects/자모맞히기/trend_news.py` | S6 | R39 |
| `projects/자모맞히기/trend_store.py` | S6 | R39 |
| `projects/자모맞히기/web/css/**` | S3 | R24 T-280 |
| `projects/자모맞히기/web/css/style.css` | S5 | R32 |
| `projects/자모맞히기/web/index.html` | S5 | R32 |
| `projects/자모맞히기/web/js/**` | S6 | R39 |
| `projects/자모맞히기/web/js/app.js` | S2 | R23 |
| `projects/자모맞히기/web/js/dict.js` | S4 | R31 |
| `projects/자모맞히기/web/js/game.js` | S4 | R31 |
| `projects/자모맞히기/web/js/jamo.js` | S2 | R24 T-276 |
| `projects/자모맞히기/web/js/storage.js` | S5 | R32 |
| `projects/자모맞히기/web/js/trend.js` | S5 | R32 |
| `projects/자모맞히기/web/js/ui.js` | S5 | R32 |
| `projects/자모맞히기/web/js/words.js` | S5 | R31 |
| `projects/주보알림/app.json` | S3 | R45 |
| `projects/주보알림/bulletin.py` | S2 | R45 |
| `projects/주보알림/data/**` | S2 | R45 |
| `projects/주보알림/serve.py` | S3 | R45 |
| `projects/주보알림/web/**` | S3 | R45 |
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
| `rounds/R33/REVIEW-r33.md` | S1 | R33 |
| `rounds/R34/REVIEW-r34.md` | S1 | R34 |
| `rounds/R35/REVIEW-r35.md` | S1 | R35 |
| `rounds/R36/REVIEW-r36.md` | S1 | R36 |
| `rounds/R39/REVIEW-r39.md` | S1 | R39 |
| `rounds/R51/REAL-CHECK.md` | S6 | R51 실물 확인 |
| `rounds/R51/REVIEW-r51*.md` | S4 | R51 적대적 검수 |
| `rounds/R51/REVIEW-r51-3.md` | S4 | R51 재검수 2 |
| `rounds/R52/REVIEW-r52*.md` | S4 | R52 적대적 검수 |
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
| `tests/test_aimem_monitor_app_server.py` | S5 | G-072 T-349 S8→S5 |
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
| `tools/aimem_monitor/app_server.py` | S5 | G-072 T-349 S8→S5 |
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
| Q-261116-fa85 | 녹취 기록 및 조회 크롬 앱 제작 | 태석 | DONE | 2026-11-16T13:58:37 |
| Q-261116-r34q | [VoxLog] 대기 큐 1건 처리: R33-N13·N14·N15·N16 (하) | 관리자 M-R34 (대기 큐) | DONE | 2026-11-16T15:13:18 |
| Q-261117-r35q | [VoxLog] 대기 큐 1건 처리: R34-N4·N6 (하) + OSError 응답 | 관리자 M-R35 (대기 큐) | DONE | 2026-11-17T08:28:01 |
| Q-261117-r36q | [VoxLog] 대기 큐 1건 처리: R35-N1·N2·N3 (하) | 관리자 M-R36 (대기 큐) | DONE | 2026-11-17T11:12:21 |
| Q-261123-f11a | [자모맞히기] 시험 라운드: freebuff 슬롯(S6)으로 코드 검수 | 태석 (클로드 코드 전달) | DONE | 2026-11-23T14:11:00 |
| Q-261123-018e | [VoxLog] 시험 라운드: freebuff 세션이 도중에 끝날 때 이어 가기(S6) | 태석 (클로드 코드 전달) | DONE | 2026-11-23T16:50:49 |
| Q-261123-6bf6 | 대기 큐 7건 처리 - S6(freebuff)에 맡기는 시험 라운드 (세션 도중 끊김 보기) | 태석 (클로드 코드 전달) | DONE | 2026-11-23T17:42:01 |
| Q-261123-7d3e | [VoxLog] 시험 라운드: freebuff 세션이 일하는 도중 풀릴 때 이어 가기 (S6 노드 둘) | 태석 (클로드 코드 전달) | DONE | 2026-11-23T22:33:35 |
| Q-261124-9281 | [VoxLog] 시험 라운드: 새 보내기 방식(1차 지시를 줄 앞에 붙여 한 번에)으로 freebuff 세션 풀림 이어 가기 - 대기 큐 VoxLog 4건 (S6 노드 셋) | 태석 (클로드 코드 전달) | DONE | 2026-11-24T09:56:42 |
| Q-261124-e24b | [VoxLog] 대기 큐 VoxLog 4건 처리 - S6(freebuff)에 맡김, 종류별 기본 1차 지시의 첫 실물 시험 | 태석 (클로드 코드 전달) | DONE | 2026-11-24T13:23:08 |
| Q-261124-7f0b | [자모맞히기] 대기 큐 R39-N3 - tests/README.md 의 기대 검사 수 맞추기 (S6, 문서 노드) | 태석 (클로드 코드 전달) | DONE | 2026-11-24T13:23:08 |
| Q-261124-795c | [VoxLog] 조사: 녹음 초안이 살아 있는지 판정하는 표준 방식 (웹 잠금 등) - 구현하지 않음 | 태석 (클로드 코드 전달) | DONE | 2026-11-24T15:08:47 |
| Q-261124-b4ad | [VoxLog] 녹음 초안의 주인 판정을 웹 잠금(navigator.locks)으로 바꾸기 | 태석 (클로드 코드 전달) | DONE | 2026-11-24T16:17:54 |
| Q-261124-ba96 | [주보알림] 새 주보 확인하고 카톡으로 보내는 웹 앱 (시제품) | 태석 (클로드 코드 전달) | DONE | 2026-11-24T18:31:06 |
| Q-261124-f310 | [VoxLog] 대기 큐의 VoxLog 항목 둘 처리 (R43-N5, R44-N1~N3) | 태석 (클로드 코드 전달) | DONE | 2026-11-24T23:08:57 |
| Q-261125-f9f0 | [VoxLog] 대기 큐의 VoxLog 항목 처리 (R46-N1, R46-N2) | 태석 (클로드 코드 전달) | DONE | 2026-11-25T00:08:19 |
| Q-261125-5fa4 | [VoxLog] 작업자마다 써 보고 추가 기능 아이디어 둘씩 → 관리자가 검토·확정 → 설계 문서 (구현하지 않음) | 태석 (클로드 코드 전달) | DONE | 2026-11-25T00:31:34 |
| Q-261125-76c8 | [VoxLog] F2 녹취 이름·태그 구현 - AI 가 자동으로 태그를 달고 사람이 고치거나 더함 | 태석 (클로드 코드 전달) | DONE | 2026-11-25T11:21:26 |
| Q-261126-902f | [VoxLog] 대기 큐의 VoxLog 항목 다섯 모두 정리 | 태석 (클로드 코드 전달) | DONE | 2026-11-26T10:21:43 |
| Q-261127-8d1e | [VoxLog] 웹에서 받아쓰기 설정 옵션 바꾸기 (전처리 denoise 등) | 태석 (클로드 코드 전달) | DONE | 2026-11-27T16:17:01 |
| Q-261127-8f71 | [VoxLog] 다시 받아쓰기의 지난 글을 여러 벌 남기기 (판 기록, R51-N8 결정) | 태석 (클로드 코드 전달) | DONE | 2026-11-27T21:56:58 |
