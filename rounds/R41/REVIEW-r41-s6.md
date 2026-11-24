# R41 S6 검수 기록 (관리자가 옮겨 적음)

## T-382 문서 대조 검수: INTERFACE.md ↔ serve.py·voxlog/·tests/ - DONE, 시도 1

- run `T-382-S6-a1-095926`. 09:59:26 띄움 → 10:16:29 팬에 지시 한 줄(미리 고른 문구 자동 전송) → 10:44:28 끝 (약 28분)
- 슬롯 검사 통과, 프로젝트 파일 변경 없음, /tmp 사본에서 단위 136 OK, 변이 18개(잡힘 9 · 빈틈 9), 임시 서버로 불일치 6건 재현
- 원본 보고 전문: `.aimem/sessions/T-382-S6-a1-095926/events.jsonl` 마지막 `end` 줄

### 발견 (중 3 · 하 9) - 번호는 큐에서 R41-N<k>

| 번호 | 심각도 | 무엇 | 자리 | 재현/변이 |
| ---- | ------ | ---- | ---- | --------- |
| R41-N1 (V1) | 중 | STT 작업 id 를 `isalnum()` 만 받음 - 문서는 아무 `{"id"}`. UUID·`job_1` 꼴이면 받아쓰기 실패 (실제 KISTI id 형식은 추정) | `voxlog/stt.py:229`, INTERFACE.md:90-92 | POST 응답 `{"id":"3f2a…-…"}` → SttError |
| R41-N2 (V2) | 중 | 검색 계약(대소문자 무시·title 일치·snippet 앞뒤 40자)이 검사로 고정 안 됨 | `voxlog/store.py:383,400,404-410`, `tests/test_store.py:115-135` | 대소문자 구분·title 검사 삭제·창 축소 변이 모두 통과 |
| R41-N3 (V3) | 중 | `GET /api/recordings` 의 status·limit 이 HTTP 검사에 없음, limit 규칙(0→1, abc→400, 상한 1000)이 문서 밖 | `serve.py:449-469`, INTERFACE.md:144 | `?limit=0` → 1건, `?limit=abc` → 400 |
| R41-N4 (V4) | 하·문서 | llm 기본 명령에 `--strict-mcp-config --setting-sources ""` 가 문서에 없음(검사는 코드를 지킴) | `voxlog/ask.py:84-86`, INTERFACE.md:120 | - |
| R41-N5 (V5) | 하·결함 | `POST /api/ask` 본문이 선언보다 짧고 연결이 살아 있으면 읽기 timeout 을 안 잡아 응답 없이 끊김(문서: 400) | `serve.py:333` | `Content-Length: 100`, 7바이트, 연결 유지 → RemoteDisconnected |
| R41-N6 (V6) | 하·검사 | `DELETE /api/answers/<id>` 묻는 중 409 의 HTTP 검사 없음 | `serve.py:545-549` | 409→404 변이 통과 |
| R41-N7 (V7) | 하·검사 | health `llm` 참 경로 검사 없음 | `serve.py:292-311`, `tests/test_serve.py:95-102` | `llm=False` 고정 변이 통과 |
| R41-N8 (V8) | 하·문서 | `Origin: null` 은 403 인데 문서는 null 은 남의 출처 아님이라 함(검사는 403 고정 - 문서가 낡음). 루프백 아닌 Host 403(리바인딩 방어)이 문서에 없음 | `serve.py:247,185-187`, INTERFACE.md:171 | - |
| R41-N9 (V9) | 하·문서 | title 은 공백을 접은 40자(문서: 글 앞 40자), 어느 쪽도 검사 없음 | `voxlog/store.py:462`, INTERFACE.md:40 | - |
| R41-N10 (V10) | 하·문서 | `Store.delete_answer` 가 store API 목록에 없음, 잘못된 id 에 False(문서: ValueError) | `voxlog/store.py:578-581`, INTERFACE.md:45-77 | - |
| R41-N11 (V11) | 하·문서 | ask 의 문서 밖 규칙 셋: user_prompt 2000자 자름, start 가 running 답을 failed 로, ids 1~200(상한 검사 없음) | `voxlog/ask.py:14,41,45,127-140,158` | ids 상한 200→2 변이 통과 |
| R41-N12 (V12) | 하·문서 | `backend_name` 이 문서의 세 값 밖(`VOXLOG_STT` 값 그대로)을 돌려줌 | `voxlog/stt.py:49-50`, INTERFACE.md:84 | `VOXLOG_STT=garbage` → "garbage" |

참고(영향 작음): 503/507 을 "본문을 읽지 않고" 답한다는 문서(:156·:167)와 달리 `_err` 는 64KB 이하 본문을 버리려고 읽음.

S6 의견: 바로 고칠 것 R41-N5·N1(실제 id 형식 확인 뒤), 검사 먼저 R41-N2·N3·N6·N7, 나머지는 INTERFACE.md 를 코드에 맞추면 닫힘.

## T-385 적대적 검수 (S3) - 빈손

opencode 가 `/tmp` 사본을 만들려다 `permission requested: external_directory (/tmp/*) ; auto-rejecting` 으로 끝남(11:11:34). 보고는 첫 줄 한 줄. 엔진은 done 으로 받음 → 큐 `[함대] R41-P1`.

## T-386 적대적 검수 재시도 (S2) - 불합격

전문 `.aimem/sessions/T-386-S2-a1-111210/report.md`. R39-N1·N2·N4·R40-N2·N3 닫힘(변이로 확인). R40-N1 은 BroadcastChannel 없음/300ms 무응답 탭에서 남음(직접 재현, 중). 업로드(queue.js:267·sw.js:168)가 200 text/html 을 성공으로 받아 녹음을 지움(직접 재현, 중). 검사 빈틈 하 3. → T-387 이 모두 고침.

## T-388 재검수 (S3, /tmp 없이) - 조건부 통과

전문 `.aimem/sessions/T-388-S3-a1-120644/report.md`. 초안 lease·업로드 엄격 판정·검사 보강 닫힘, 회귀 없음(137 OK·31/31).

| 번호 | 심각도 | 무엇 | 자리 |
| ---- | ------ | ---- | ---- |
| R41-N13 | 중(추정) | 다른 탭이 열린 채 녹음 탭이 그 탭의 22초 재시도 뒤 죽으면 앱을 다시 열 때까지 초안 회수 안 됨(데이터는 IndexedDB 에 남음) | `web/app.js:1073`, `queue.js:484` |
| R41-N14 | 하(추정) | 20초 넘는 메인 스레드 정지·탭 프리즈면 살아 있는 초안이 여전히 회수될 수 있음 | `queue.js:24,498` |
| R41-N15 | 하 | 녹음 중 새로고침하면 회수가 최대 약 22초 늦음(문서화 필요) | `app.js:1069-1080` |
| R41-N16 | 하(추정) | 조각 0개 초안도 '살렸습니다' 로 셈 | `queue.js:465,504` |
| R41-N17 | 하·검사 | lease 만료 회수 경로·sw.js 엄격 판정·t31 의 id 없는 JSON lastError 가 검사로 고정 안 됨 | `tests/browser_voxlog.py:896-1060` |
| R41-N18 | 하(추정) | draftAppend 실패(draftOk=false) 때 activeDraft 가 남아 DB 초안이 정리 안 됨(손실 없음) | `queue.js:373,475`, `app.js:448-454` |
