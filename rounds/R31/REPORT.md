# R31 종료 보고 (관리자 M-R31, 2026-11-15 00:19 ~ 01:46)

상태: DONE

요청 `Q-261114-e40c` [자모맞히기] '낱말 사전 외부 조회' → DONE. 라운드 도중 INBOX 로 온 태석님 지시(01:11~01:26) 가운데 연합뉴스 RSS 와 설정 단추는 이번에 했습니다. 나머지(서버가 저장·지난 시간 표시·모니터에서 앱 파이썬 실행)는 후속 상한(그래프 6·태스크 18)에 닿아 **대기 큐 R31-P1·R31-P2** 로 넘겼습니다.

## (1) 태스크

| 태스크 | 슬롯 | 그래프 | 무엇 | 결과 |
|---|---|---|---|---|
| T-310 | S4 sonnet | G-064 | `web/js/dict.js` + `test_dict.mjs` | DONE |
| T-311 | S5 sonnet | G-064 | `dict_server.py` + `serve.py` `/api/sources`·`/api/lookup` + 시험 | DONE (막힘 1회 - T-312 와 같은 시각에 `test_words.py` 를 고치다 충돌, 재검증으로 풂) |
| T-312 | S6 deepseek | G-064 | `trend.txt` → `words.js` `TREND`, `answerForDate(…, trend)` | DONE |
| T-314 | S3 무료 | G-064 | `pick_answers.py`(Gemini판) + 시험 | DONE → T-324 에서 다시 씀 |
| T-313 | S4 | G-064 | 설정 `#set-dict`·추측 흐름·저장·하네스 기본 라우트 | DONE |
| T-315 | S5 | G-064 | 모니터 `/app/` CSP `connect-src` ← `app.json` `connect` | DONE |
| T-316 | S5 | G-064 | `browser_dict.py` 75 검사 | NEEDS-FIX(제품 결함 찾음) → T-318 뒤 재검증 DONE |
| T-317 | S1 opus | G-064 | 적대적 검수 1 `REVIEW-r31.md` | 판정 통과 (상 0·중 2·하 5) |
| T-318 | S4 | G-065 | 찾은 낱말이 진행 중인 판에 반영 안 됨(무한 재조회) 고침 - `Game.allowWord` | DONE |
| T-319 | S5 | G-066 | R31-N1(중) 교차 출처 막기·N3·N6 | DONE |
| T-320 | S4 | G-066 | R31-N2(중) 키 평문 저장 안내·N7 | DONE |
| T-321 | S6 | G-066 | R31-N4·N5 README | DONE |
| T-322 | S5 | G-067 | 추론 LLM 빈 답(서버) | DONE |
| T-323 | S4 | G-067 | 추론 LLM 빈 답(브라우저) | DONE |
| T-324 | S5 | G-068 | `trend_news.py`(연합뉴스 RSS)·`POST /api/trend/pick`·`pick_answers.py` 다시 씀 | DONE |
| T-325 | S4 | G-068 | 설정 `#set-trend` 단추 + `browser_trend.py` | DONE |
| T-326 | S5 | G-068 | 실물: `trend.txt` 11-15~21 + 브라우저 검사 오늘 정답에 TREND + README | DONE |
| T-327 | S1 | G-068 | 적대적 검수 2 `REVIEW-r31b.md` | 판정 통과 (상 0·중 2·하 5 → 큐) |

**프로젝트별로 쌓인 곳**
- `projects/자모맞히기/`: `web/js/dict.js`(새), `dict_server.py`(새), `trend_news.py`(새), `serve.py`, `tools/pick_answers.py`(새), `tools/build_words.py`, `data/trend.txt`(새), `data/trend_stop.txt`(새),
  `web/js/{ui,game,storage,words}.js`, `web/index.html`, `web/css/style.css`, `app.json`(`connect`), `README.md`(외부 사전·트렌드 정답 절), `PROGRESS.md`(목표 21개 중 19 체크, R31 항목),
  `tests/`(`test_dict.mjs`·`test_dict_server.py`·`test_trend_news.py`·`test_pick_answers.py`·`browser_dict.py`·`browser_trend.py` 새, `browser_harness.py`·`browser_game.py`·`browser_modes.py`·`test_game.mjs`·`test_words.py`·`README.md` 고침)
- 함대: `tools/aimem_monitor/server.py`(`app_connect_origins`·`app_csp(connect=)`), `tests/test_aimem_monitor_app.py` - **모니터 재시작 필요**(클로드 코드가 검토한 뒤)
- 기록: `rounds/R31/REVIEW-r31.md`, `REVIEW-r31b.md`, 이 파일. 관리자 명세·검증 도구 `.aimem/graph/inputs/r31/`(`SPEC.md`·`SPEC2.md`·`v.py`)

## (2) 재현한 검증

- `python3 .aimem/graph/inputs/r31/v.py real`(관리자가 마지막에 다시 돌림): node `pass 94`·`fail 0`, unittest `Ran 97`·OK, `browser_game` 121/121, `browser_modes` 100/100, `browser_dict` 75/75, `browser_trend` 45/45, `words.js` = `build_words.py` 출력, 오늘(11-15)이 TREND 에 있음 → `v_real: 모두 통과`
- 함대 `python3 -m unittest discover -s tests`: `Ran 981`, OK (skipped 1). `aimem_lint.py AIMEM.md`: 위반 없음(render 뒤)
- 관리자 실물 조회(진짜 키, `.aimem/graph/inputs/r31/real_lookup.py`): 위키낱말사전·위키백과 - 한국·바다 있음, 뷁쉙 없음(정확). EXAONE - 고치기 전 '알 수 없는 답'(`max_tokens 8` 에 `finish_reason: length`·`content` 빔 - 명세 결함, T-322·T-323 으로 고침), 고친 뒤 '한국 → 예', 연달아 부르면 429. kistillm - 시간 초과(S2 장애와 같은 원인). 국립국어원·Gemini - 키 없음 안내.
- 실물 정답(T-326): 연합뉴스 제목 668건 → 후보 501 → 지원·혐의·진출·중단·논란·국회·전국 (11-15~21)
- 검수 변이: 검수 1 의 변이 7개 모두 잡힘, 검수 2 의 변이도 기록(`REVIEW-r31b.md` 5절)

## (3) 기다린 시간

| 그래프 | 시작 | 끝 | 걸림 |
|---|---|---|---|
| G-064 | 00:26 | 00:59 | 33분 (T-311 막힘 4분, T-316 NEEDS-FIX 6분 포함) |
| G-065 | 00:48 | 00:53 | 5분 |
| G-066 | 01:00 | 01:11 | 11분 |
| G-067 | 01:13 | 01:14 | 1.5분 |
| G-068 | 01:17 | 01:40 | 23분 |

작업자 자체는 대개 1~2분에 끝났고, 시간 대부분은 엔진 verify(브라우저 검사 네 벌)입니다.

## (4) 대기 큐

시작 0건 → 끝 3건 (모두 이번 라운드가 넣음)
1. `[자모맞히기]` R31-P1 정답 정하기를 서버가 저장(`trend.txt`·마지막 시각)하고 게임이 `GET api/trend` 로 받아 씀(브라우저 `jamo.trend` 걷어냄) + 단추 옆 '3시간 전에 정함' (INBOX 01:15·01:22 1~3). R31-N8(중)·R31-N10 함께
2. `[함대]` R31-P2 모니터 '앱 열기' 에서 앱 `api/*` 가 돌게 - `app.json` `"api": {"<동작>": "<.py>"}` 선언 파일을 그 자리에서 한 번 실행(상주 서버 없음), `serve.py` 도 같은 약속 (INBOX 01:26). 적대적 검수 필수
3. `[자모맞히기]` R31-N11~N14 (하): RSS 2MB 상한, 전체 마감 120초, 정답 품질(기업명·잘린 토막), 검사 빈틈 + EXAONE 429 안내

## (5) 다음 라운드 계획

- 큐 1(R31-P1) → 큐 2(R31-P2) 순. 1 은 자모맞히기 안에서 끝나고(로컬 `serve.py` 로 완성), 2 는 함대 모니터의 새 길이라 적대적 검수 노드를 꼭 넣습니다. 2 가 들어오면 `serve.py` 의 `/api/trend/*`·`/api/lookup` 도 같은 `api` 선언 약속으로 맞춥니다.
- INBOX 01:15·01:22·01:26 의 지시는 **상한(후속 6그래프·18태스크)에 닿은 뒤**에 와서 이번에 못 했습니다. 지금 단추는 `serve.py` 로 열었을 때만 되고, 결과는 그 브라우저(`jamo.trend`)에만 저장됩니다(명령줄 `pick_answers.py` 는 `trend.txt`·`words.js` 에 써서 모두에게 공통).
- 사람이 할 일: 모니터 재시작(T-315 CSP 변경, 검토 뒤), 국립국어원 키를 `.env` 에 넣으면 그 사전들이 켜짐, 커밋.

## (6) 운영 지표

- 슬롯: S1 opus(검수 2회, 약 15분), S4 sonnet(7노드), S5 sonnet(8노드, **관리자 추가** - 사전 서버·CSP·뉴스 정답을 S4 와 나란히 돌리려고), S6 opencode·openrouter deepseek(2노드, **관리자 추가**·유료 - anthropic 동시 3 자리가 S1·S4·S5 로 차서 다른 공급자가 필요했음, 끝나고 `slot remove`), S3 무료(1노드), S2 일시 사용 중지(장애, 쓰지 않음)
- 유료 슬롯에 준 만들기·고치기: 운영 방식 '빠른 구현' 이 유료 사용을 허용, 요청 본문이 'claude 유료 슬롯 추가 허용'. S5 는 다음 라운드(큐 1·2)를 위해 남겨 둠
- 재시도 0, 노드 옮기기 0. 막힘 2회 모두 재검증(`unblock --reverify`)으로 풂 - T-311(동시 편집 충돌, 작업 자체는 맞음), T-316(검사가 제품 결함을 정확히 잡음 → G-065)
- 관리자만 돈 구간: 시작·설계 00:19~00:26(7분), T-316 결함 판단 00:48(1분), 검수 1 판단 00:59~01:00, 실물 조회·EXAONE 원인 01:02~01:13(11분, G-066 과 겹침), INBOX 판단 01:14~01:17·01:19~01:28(G-068 과 겹침), 마무리 01:40~01:46
- 상한: 그래프 5/6(후속), 태스크 18/18. G-068 은 INBOX 지시(같은 요청)와 실물 결함(`pick_answers.py` 실행 불가·Gemini 키 차단)을 고치는 일로 `--followup` 에 넣었습니다 - 엄밀히는 새 일이 섞였다는 점을 밝혀 둡니다

## (7) 개선안 하나

**명세에 든 숫자·가정은 관리자가 그래프 전에 실물로 한 번 찔러 본다.** 이번 라운드의 큰 결함 셋(EXAONE `max_tokens 8` 빈 답, Gemini 키 차단, `pick_answers.py` 의 `ModuleNotFoundError`)은 모두 검사가 가짜를 넣어 통과하고 검수도 놓친 것으로, 진짜 키·진짜 실행 한 번이면 그래프 전에 드러났습니다. 외부 API 를 쓰는 요청이면 표준 브리프의 '시작' 에 "관리자가 진짜 엔드포인트를 한 번 불러 응답 꼴을 명세에 붙인다", verify 에 "다른 cwd 에서 진입점 `--help` 한 번" 을 넣자는 제안입니다(규약 변경이라 태석님 판단).
