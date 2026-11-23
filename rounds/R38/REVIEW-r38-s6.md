# R38 검수 기록 - VoxLog 서버 쪽 파이썬 (S6 freebuff, T-371)

검수자: S6(freebuff), 읽기 전용. 대상 `projects/VoxLog/serve.py`, `voxlog/store.py`, `voxlog/stt.py`, `voxlog/ask.py`.
S6 는 단위 검사 123 OK 를 확인했고, 실험은 `/tmp` 복사본에서 했다(프로젝트 트리는 깨끗).
답 전문: `.aimem/sessions/T-371-S6-a1-165155/report.md`. 관리자가 추려 큐에 올렸다. 코드는 고치지 않았다(요청대로).

관리자 확인: R38-N1·N2 는 코드에서 행 단위로 확인했다. 이 세션은 저장소 밖 스크립트를 돌릴 권한이 없어 직접 재현하지는 못했다.
나머지(N3~N6)는 S6 의 재현을 그대로 옮겼다.

| 번호 | 심각도 | 내용 | 어디 |
| ---- | ------ | ---- | ---- |
| R38-N1 | **상** | `HEAD /api/recordings/<id>` 가 녹음을 **지운다.** 처리 함수를 원래 메서드로 먼저 고르고(238행, GET 이 아니면 `_rec_delete`), 그 뒤에 HEAD 를 GET 으로 바꿔(252행) 허용 검사를 통과시킨다. 출처 검사(227행)는 POST·DELETE 만 보므로, 토큰이 없는 서버라면 아무 사이트가 `fetch(…, {method:'HEAD', mode:'no-cors'})` 로 지울 수 있다(id 는 시각+16진 4자리). `HEAD /api/recordings` 는 `_rec_upload` 로 가서 400 을 낸다. `do_HEAD = _dispatch`(162행) | `serve.py:236-238, 252-256` |
| R38-N2 | 중 | `POST /api/ask` 의 `kind` 가 리스트나 딕트면 `kind not in KINDS` 가 TypeError 를 낸다. `_ask` 는 ValueError 만 잡아서 JSON 400 대신 연결이 끊긴다 | `serve.py:474-477`, `voxlog/ask.py:152` |
| R38-N3 | 하 | `VOXLOG_LLM_CMD` 가 공백뿐이면 IndexError, 따옴표가 안 맞으면 ValueError 가 나서 `/api/health` 가 응답 없이 끊긴다. 앱이 '서버 없음' 처럼 보인다 | `serve.py:260`, `voxlog/ask.py:75-79` |
| R38-N4 | 하 | `X-Recorded-At` 의 형식을 검사하지 않는다. `9999-12-31…` 로 올리면 그 날짜 폴더가 생기고 목록 맨 위에 계속 남는다. `?from=2026-13-40` 도 200 이다(달·일 범위 검사 없음) | `serve.py:329`, `voxlog/store.py:161-168` |
| R38-N5 | 하 | `build_prompt` 가 `recorded_at` 을 문자열 순서로 정렬해서, 시간대가 섞이면 순서가 틀린다. 길이가 넘쳐 오래된 것을 뺄 때(`blocks.pop(0)`) 최신 것을 뺄 수 있다. `store._sort_key` 를 써야 한다 | `voxlog/ask.py:45` |
| R38-N6 | 하(추정) | 다시 받아쓰기 도중 같은 녹음을 지우면 `resubmit` 이 ValueError 를 내고, `_rec_retry` 에 try 가 없어 응답 없이 끊긴다. 틈이 좁아 타이밍에 달렸다 | `serve.py:450-457`, `voxlog/stt.py:358-363` |

S6 가 살펴보고 문제없다고 본 곳: 업로드 흘려 쓰기·마감·507/500, 동시 자리 503, `client_id` 중복, 정적 경로 탈출, 토큰 `compare_digest`, Host·Origin 검사(GET·POST·DELETE),
원자적 쓰기, STT 키가 오류에 남지 않음, 작업 id 이어받기, 프롬프트를 stdin 으로 넘김·빈 임시 폴더·도구 차단.
