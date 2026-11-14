# 자모맞히기 진행

## 목표

이 프로젝트가 "다 됐다" 고 하려면 있어야 할 것. 검증까지 끝난 것만 체크합니다.
(R23 에서 요청 `Q-261113-bd56` 과 README 를 보고 끝까지 가는 데 필요한 것을 예측해 적었습니다.
R24 에서 체크한 것은 적대적 검수 3번(`rounds/R24/REVIEW-r24*.md`)이 "닫아도 됨" 으로 판정한 것뿐입니다.)

- [x] 프로젝트 뼈대 - README, 폴더 구조, 정적 서버로 열림, `app.json` 으로 모니터에서 실행
- [x] 자모 규칙 - 풀기·조합·겹자음/겹모음/겹받침 규칙이 README·화면 도움말과 같음
- [x] 판정 로직 - 같은 자모가 겹칠 때까지 자리 맞음/들어 있음/없음이 맞음 (단위 검사)
- [x] 낱말 목록 - 직접 고른 원본에서 생성, 정답·허용 모두 여섯 칸, 출처·이용 조건 적힘
- [x] 보드 - 6×6 칸, 입력 중 자모와 조합 미리보기, 제출 시 색
- [x] 화면 자판(두벌식, Shift 로 쌍자음·ㅒㅖ) + 실물 자판(한/영 상태와 무관하게 `e.code`)
- [x] 없는 낱말·모자란 입력 거절과 안내
- [x] 날마다 하나(누구에게나 같음) + 연습(무제한) 모드, 새로 고쳐도 오늘 판 유지
- [x] 판 끝 - 이김/짐 표시와 정답 공개, 결과 공유 글 복사
- [x] 도움말 - 처음 열면 규칙, 다시 볼 수 있음
- [x] 폰(320~430px)·데스크톱에서 겹침·넘침 없음
- [x] 어두운 모드 - 시스템 설정 따름 + 단추로 바꿈, 저장됨
- [x] 접근성 - 키보드만으로 완주, 결과가 `aria-live` 로 읽힘
- [x] 통계 - 판수·승률·연승·추측 분포
- [x] 검사 - 로직 단위 검사·브라우저 검사(그려진 것)가 모두 초록, 적대적 검수 통과
- [x] 외부 사전 조회 - 목록에 없는 6칸 추측을 고른 사전·AI 로 확인해 있으면 받아 줌, 찾은 낱말은 저장 (R31, 요청 `Q-261114-e40c`)
- [x] 출처 미리 등록·고르기 - 위키낱말사전·위키백과·국립국어원 3종·KISTI·EXAONE(함대 설정)·Gemini·OpenRouter, 사용자 LLM 더하기·지우기 (R31)
- [x] 키 보호 - 서버 키는 응답·오류·로그에 안 나옴, 로컬 서버는 남의 출처 요청 거절, 화면에 평문 저장 주의 (R31)
- [x] 뉴스로 정답 정하기(파이썬) - 연합뉴스 RSS → 6칸·꼬리표/지명 빼기·기사 수 순 → 사전 확인 → 날짜별 정답, 명령줄과 설정 단추가 같은 함수 (R31)
- [x] 정한 정답을 서버가 저장하고 게임이 다시 빌드 없이 받아 씀 + 단추 옆 '마지막으로 정한 뒤 지난 시간' (R32, 큐 R31-P1)
- [x] 모니터 '앱 열기' 에서도 사전 서버·정답 정하기가 됨 - app.json `"server": "serve.py"` 를 모니터가 따로 떨어진 자식 프로세스로 띄워 `api/*` 를 이어 줌 (R32, 요청 `Q-261115-4aff`; 옛 'api 선언 파일 한 번 실행' 안은 태석님이 거둠)

## R32 (2026-11-15)

**한 일** - 요청 `Q-261115-4aff`(모니터가 앱의 serve.py 를 띄워 이어 줌) + 큐 R31-P1·R31-N8·R31-N10~N14 를 그래프 G-069(8노드) + 후속 G-070(2노드)로,
운영 방식 '빠른 구현', 약 47분, 재시도·이동 0. 슬롯: S5·S4 sonnet(만들기), S3 무료(품질 결함·문서), S1 opus(검수). 목표 21 → 21 (21 체크, 줄 하나를 새 방법으로 고쳐 씀).

- 서버 정답 저장: 새 `trend_store.py`(`read_trend`·`append_picks`(있는 날짜 안 덮음, 임시 파일→`os.replace`, 스레드 잠금 + `fcntl.flock` 프로세스 잠금)·`last_run`·`record_run`·`pick_and_store`),
  `serve.py` `GET /api/trend` → `{trend, last_run}`, `POST /api/trend/pick` 이 `data/trend.txt` 에 덧붙이고 `data/trend_meta.json` 에 마지막 시각, `Handler.timeout = 30`.
  명령줄 `tools/pick_answers.py` 도 같은 `pick_and_store`
- 화면: 새 `web/js/trend.js`(`sinceText`·`mergeTrend`), 시작·단추 뒤 `GET api/trend` → 하루 정답에 `{...TREND, ...서버}`(다시 빌드 없이), 단추 옆 `#trend-since`('3시간 전에 정함'·'아직 정한 적 없음', 창 열 때마다 다시),
  브라우저 `jamo.trend` 걷어냄, 줄 있는 오늘 판은 새로 고쳐도 정답 고정(R31-N8), 404·405·501·JSON 아님 → 서버 없음 글(R31-N10)
- 뉴스 품질(R31-N11~N14): RSS 2MB 상한, `pick(deadline=120)`, `trend_stop.txt` 기업명·시군, 3음절 이상 1글자 조사는 원형도 후보, `checked` 실제 수
- 함대(모니터): 새 `tools/aimem_monitor/app_server.py`(앱당 하나·좁은 환경·이어 줄 머리 화이트리스트·크기·시간·동시 상한·유휴 내림·죽으면 다시·pid 로 내림·cleanup_stale),
  `server.py` `project_app` 의 `server` 선언 검사, `/app/~<티켓>/<앱>/api/*` GET·POST 이어 주기·`OPTIONS` 사전 요청·감사 `app-api`·시작 정리·유휴 스레드·종료 정리·프로젝트 삭제 뒤 내림. **모니터 재시작 필요**
- `app.json` 에 `"server": "serve.py"`. 문서: `README.md` 트렌드 정답 절·모니터에서 서버·EXAONE 429 안내, `tests/README.md` 수

**검증** - 관리자 검증 도구 `.aimem/graph/inputs/r32/v.py`(노드마다 엔진 verify), 관리자가 다시 돌려 재현: node 107 · python 133 · 브라우저 game 121 · modes 100 · dict 75 · trend 81 모두 초록,
함대 `tests/browser_monitor_app_server.py` 21/21(인증 켠 모니터 → 앱 열기 → 정답 정하기 → '방금 정함' → 새로 고쳐도 유지, 끝나고 자식 없음), 함대 검사 1025 OK.
적대적 검수 `rounds/R32/REVIEW-r32.md`(S1 opus, 판정 통과): 중 R32-N1(trend_store 프로세스 사이 잠금 없음) → G-070 에서 고침, 하 N2·N4·N6 고침, N3·N5 큐.

**남은 일**
1. 큐 `[함대]` R32-N3·N5(하): 모니터 둘이 같은 저장소일 때 cleanup_stale, 앱이 setsid 로 띄운 손자 - 프로젝트 일 아님
2. 사람: 운영 모니터 재시작(클로드 코드가 코드 검토 뒤) - 그 전에는 운영 '앱 열기' 에서 정답 정하기가 '서버 없음' 글
3. 사람: 국립국어원 키를 `.env` 에 넣으면 그 출처가 켜짐(README 외부 사전 절)

## R31 (2026-11-15)

**한 일** - 요청 `Q-261114-e40c`(낱말 사전 외부 조회 + 뉴스로 정답)를 그래프 다섯(G-064 8노드, 후속 G-065·G-066·G-067·G-068)으로,
운영 방식 '빠른 구현', 약 1시간 20분. 슬롯: S4 sonnet·S5 sonnet(관리자 추가)·S6 오픈라우터 deepseek(관리자 추가, 끝나고 지움)·S3 무료·S1 opus 검수. 목표 15 → 21 (19 체크).

- 외부 사전: `web/js/dict.js`(출처 표·조회 경로·LLM 요청과 답 읽기), `dict_server.py`(서버 조회·키는 `.env`/환경변수·fleet.toml 의 KISTI/EXAONE),
  `serve.py` `GET /api/sources`·`GET /api/lookup`(Host·Origin 같은 출처만), 설정 창 `#set-dict`(켜기·출처·키·사용자 LLM·확인해 보기), 추측 흐름(조회 중 입력 막기, 한 추측 한 조회,
  찾으면 `Game.allowWord` 로 그 판에 반영·`jamo.extraWords` 저장)
- 모니터: `tools/aimem_monitor/server.py` `/app/` CSP 의 `connect-src` 에 `app.json` `connect` 출처(https 만, 10개)를 보탬 → 모니터에서도 위키 직접 조회·사용자 키 LLM 이 됨. **모니터 재시작 필요**
- 추론 LLM: EXAONE 이 `max_tokens 8` 에 생각하다 잘려 빈 답(관리자 실물) → 1024·`<think>` 걷기·429 안내·LLM 30초
- 뉴스 정답: `trend_news.py`(연합뉴스 RSS 7개 피드 → 조사 떼기·6칸·`data/trend_stop.txt` 빼기·기사 수 순 → 위키낱말사전 50개씩 묶음·명사 분류 확인 → 날짜),
  명령줄 `tools/pick_answers.py`(Gemini 경로 뺌 - 구글이 키를 막음), `serve.py` `POST /api/trend/pick`, 설정 창 `#set-trend` 단추(지금은 결과를 그 브라우저 `jamo.trend` 에 저장),
  `tools/build_words.py` 가 `data/trend.txt` → `words.js` `TREND`, `game.js` `answerForDate(…, trend)`
- 실물 한 번: `data/trend.txt` 에 2026-11-15~21 일곱 날(제목 668건·후보 501개), `words.js` 재생성
- 검사: 새 `test_dict.mjs`·`test_dict_server.py`·`test_trend_news.py`·`test_pick_answers.py`·`browser_dict.py`·`browser_trend.py`, 브라우저 검사 오늘 정답에 `TREND`

**검증** - 관리자 검증 도구 `.aimem/graph/inputs/r31/v.py`(노드마다 엔진 verify), 관리자가 `v.py real` 로 재현: node 94 · python 97 · 브라우저 121 · 100 · 75 · 45 모두 초록,
함대 검사 981 OK. 관리자 실물 조회: 위키 두 곳 정확(한국·바다 있음, 뷁쉙 없음), EXAONE 고친 뒤 '한국 → 예'(연달아 부르면 429), kistillm 시간 초과(장애), 국립국어원·Gemini 키 없음.
적대적 검수 두 번 `rounds/R31/REVIEW-r31.md`(판정 통과, 중 2·하 5 → G-066 에서 모두 고침), `rounds/R31/REVIEW-r31b.md`(판정 통과, 중 2·하 5 → 큐).

**남은 일** (대기 큐, 태석님 INBOX 01:15·01:22·01:26 지시가 이번 라운드 상한 뒤에 와서 넘김)
1. 큐 R31-P1 `[자모맞히기]`: 정한 정답을 **서버가** `data/trend.txt` 와 마지막 시각에 저장, `GET api/trend` 로 게임이 받아 씀(브라우저 `jamo.trend` 걷어냄), 단추 옆 '3시간 전에 정함'.
   R31-N8(고르는 중 오늘 판에 줄을 내면 늦은 응답이 오늘 정답을 바꿈)·R31-N10 함께
2. 큐 R31-P2 `[함대]`: 모니터 '앱 열기' 에서 `app.json` `api` 선언 파이썬 파일을 한 번 실행해 응답(상주 서버 없음), `serve.py` 도 같은 약속. 적대적 검수 필수
3. 큐 R31-N11~N14 (하): RSS 크기 상한, 전체 마감, 정답 품질(기업명·잘린 토막), 검사 빈틈
4. 사람: 국립국어원(표준국어대사전·우리말샘·기초사전) 키를 `.env` 에 넣으면 그 출처가 켜짐(받는 곳은 README 외부 사전 절)

## R30 (2026-11-14)

**한 일** - 요청 `Q-261114-a3cf`(큐 R29-N1·N2, 모두 하)를 그래프 G-063 하나(3노드, 운영 방식: 빠른 구현, 약 29분)로 끝냄.
목표는 15/15 그대로(품질 보강).

- `tests/browser_modes.py`(T-307, S4 sonnet): `scenario_hard_locked_after_play` 에 잠금 시도 뒤 저장된 설정(`jamo.settings` 의
  `hardMode`)이 참이 아님 - 바로·새로 고친 뒤 - 과 빈 연습 판의 하드 체크박스가 꺼짐, 검사 3개. 모드 시험 97 → **100**
- `tests/README.md`: 모드 수 100
- `data/words/풀이씨.txt`(T-308, S3 에서 막혀 S4 로 옮김): `배우다` 보탬, `web/js/words.js` 재생성 - ANSWERS 380, ALLOWED 2181 → **2182**

**검증** - 관리자 검증 도구 `.aimem/graph/inputs/r30/v_*.py`(엔진 verify 통과, 관리자가 다시 돌려 재현: 모드 100/100, `/tmp` 사본의
V19·V16 잡힘, ALLOWED 2182). 적대적 재검수 `rounds/R30/REVIEW-r30.md`(S1 opus): 네 벌 66 · 13 · 121 · 100 모두 초록, V19·새 변이
V20·V21 잡힘. 판정: **R29-N1·N2 닫음**.

**남은 일** - 목표 기준 없음. 사람이 정할 품질 보강(하) 한 건 - 대기 큐에는 넣지 않았습니다(R30 INBOX 지시: '하' 는 큐 대신 여기와 보고에):
1. R30-N1: 잠금 저장 검사가 한 방향(하드 꺼진 판에서 켜기 시도)만 봄 - 하드 켠 판에서 줄을 낸 뒤 끄기를 시도할 때
   `false` 를 저장하는 변이는 안 보임. 하고 싶으면 짝 시나리오 하나(`REVIEW-r30.md` 4절)

## R29 (2026-11-14)

**한 일** - 요청 `Q-261114-23ef`(큐 R28-N1~N4, 모두 하)를 그래프 G-062 하나(3노드, 운영 방식: 빠른 구현, 재시도·이동 0, 약 30분)로
끝냄. 목표는 15/15 그대로(품질 보강).

- `tests/browser_modes.py`(T-304, S4 sonnet): `scenario_hard_locked_after_play`(같은 모드에서 줄을 낸 뒤 하드 켜기 → 체크 그대로·잠금
  토스트·줄 그대로·새로 고쳐도 그대로, 변이 V16)·`scenario_align_keeps_puzzle_number`(시계 고정, 연습에서 하드 바꾸고 날마다로 와서
  이긴 공유 첫 줄이 `자모맞히기 1`, 변이 V14) - 모드 시험 90 → **97**
- `tests/README.md`: 모드 수 97 과 새 시나리오
- `data/words/자연마음.txt`·`풀이씨.txt`(T-305, S2 kistillm 무료): 어근·비표준 `선선 눅눅 촉촉 용감 채이다` 지움, 빠진 흔한 말 30개
  (`일출 … 앞쪽` 자연마음, `함성 … 벌점` 생활 "보탬 4", `따지다 … 비싸다` 풀이씨) 보탬. 파일 전체 훑기에서 더 지운 것 없음(경계 `곰팡 알람`)
- `tests/test_words.py`: `BANNED` 에 다섯 낱말(시험 수 13 그대로), `web/js/words.js` 재생성: ANSWERS 380, ALLOWED 2156 → **2181**

**검증** - 관리자 검증 도구 `.aimem/graph/inputs/r29/v_*.py`(엔진 verify 모두 통과, `v_modes` 는 /tmp 사본에 V16·V14 를 넣어 실패를 확인).
적대적 재검수 `rounds/R29/REVIEW-r29.md`(S1 opus): 네 벌 node 66 · python 13 · browser_game 121 · browser_modes 97 모두 초록,
V14·V16 잡힘, 새 변이 3개 중 2개 잡힘, 새 표본 60개 빠짐 **1.7%**(배우다 하나). 판정: **R28-N1~N4 닫음**. 관리자가 `v_words` 재현.

**남은 일** - 없음 (목표 기준). 품질 보강은 대기 큐 `R29-N1·N2`(모두 하):
1. R29-N1: 잠금 시나리오가 잠금 시도 뒤 저장된 설정(localStorage `settings.hardMode`)이 그대로인지 안 봄(변이 V19 생존)
2. R29-N2: 아주 흔한 동사 `배우다` 가 ALLOWED 에 없음 - 풀이씨 묶음에 보태고 `words.js` 재생성

## R28 (2026-11-13~14)

**한 일** - 큐 1번(R27-N1·N2·N3 + 덮는 범위)을 그래프 G-061 하나(4노드, 운영 방식: 빠른 구현)로 끝내고 가벼운 적대적
재검수로 `검사` 목표를 닫음. 목표 **15/15**.

- `data/words/자연마음.txt`·`풀이씨.txt`: 어근·비표준 13개(`억울 솔직 명랑 온순 당당 씩씩 튼튼 든든 단단 쌀쌀 침울 패이다 개이다`) 지움.
  `자연마음.txt`·`생활.txt`·`사회.txt` 에 검수가 찾은 빠진 흔한 말 32개(`강둑 늦잠 … 불평 잘못`) 보탬
- `tests/test_words.py`: `BANNED` 에 그 13개 + `착실 똑똑 꼼꼼 넉넉`, `MUST` 에 `까닭`, 새 시험
  `test_answers_match_answers_file`(ANSWERS = `answers.txt`, 380) - 낱말 시험 12 → 13
- `web/js/words.js` 재생성: ANSWERS 380 그대로, ALLOWED 2137 → 2156
- `tests/browser_modes.py`: `scenario_hard_reaches_empty_practice`(연습 쪽 하드 맞춤)·`scenario_typed_letters_survive_align`
  (빈 판 다시 만들 때 입력 중 글자 유지) - 모드 시험 83 → 90
- `tests/README.md`: 수를 66 · 13 · 121 · 90 으로

**검증** - 관리자 검증 도구 `.aimem/graph/inputs/r28/v_*.py`(엔진 verify, 모두 통과). 적대적 재검수 `rounds/R28/REVIEW-r28.md`(S1 opus):
네 벌 node 66 · python 13 · browser_game 121 · browser_modes 90 모두 초록, R27 생존 변이 5개 중 4개(V3·V6·V10·V12) 이제 잡힘,
V11(BANNED 에 없는 새 어근)은 목록 시험의 본래 한계로 하. 새 변이 4개 중 2개 생존(시험 빈틈, 하). 새 표본 덮는 범위 21.7% 빠짐(기준 안).
판정: **'검사' 목표 닫음**. 관리자가 python 13 OK 재현.

**남은 일** - 없음 (목표 기준). 품질 보강은 대기 큐 `R28-N1·N2·N3·N4`(모두 하):
1. R28-N1: 같은 모드에서 줄을 낸 판의 하드 잠금(`hardModeLocked`) 브라우저 시험 - 잠금이 풀리면 하드 바꾸기가 낸 줄을 지움
2. R28-N2: `alignEmptyHard` 가 판 번호를 지키는지(`puzzleNumber` 가 0 이 아님) 시험
3. R28-N3: 갈래 파일 어근 `선선 눅눅 촉촉`(확실)·`용감`·`채이다`(경계) 지우고 `BANNED` 에, 파일 전체를 "`-하다` 없이 홀로 쓰이나" 로 훑기
4. R28-N4: 검수 4절의 빠진 흔한 말 30개. 다음 검수는 R27·R28 표본이 아닌 새 표본으로 잴 것

## R27 (2026-11-13)

**한 일** - R26 에서 함대 완전 중지로 멈춘 G-060(7노드)을 이어 끝냄(운영 방식: 빠른 구현). 추측 목록을 갈래 파일 넷으로
넓히고, 빌드가 그것을 읽게 하고, 하드 모드 빈 판 결함(R24-N5)을 고침. 목표 **14/15**(`낱말 목록` 체크).

- `data/words/생활.txt`(503)·`사회.txt`(439)·`자연마음.txt`(495)·`풀이씨.txt`(279) 새 파일 - 갈래별 6칸 추측 낱말
- `tools/build_words.py`: `data/words/*.txt` 를 이름 순으로 읽어 ALLOWED = answers ∪ allowed ∪ 갈래. **ANSWERS 는
  `answers.txt` 만**(380). ALLOWED 1033 → **2137**
- `tests/test_words.py`: ALLOWED ≥ 2000, 첫 음절 상한 `max(40, 4%)`, 갈래 파일별 첫 음절 ≤15, `BANNED` 에
  `희한 민망 괴악 희식 화성 국전`(R24-N2·N3; 이 여섯은 `allowed.txt`·`answers.txt` 에서 뺌). `까닭` 은 `allowed.txt` 에 있음
- `data/README.md` 새 구조, `web/js/words.js` 재생성
- `web/js/ui.js`·`tests/browser_modes.py`: 하드 모드 설정이 다른 모드의 빈 판에 바로 닿음(R24-N5 닫힘, 브라우저 83)

**검증** - 적대적 검수 `rounds/R27/REVIEW-r27.md`(S1 opus): 시험에 없는 새 표본 80개 중 빠짐 0(쉬운 표본), 더 어려운
표본 36개 2.8%·80개 21.2%, R24-3 옛 표본 60 중 15 빠짐(이전 57). 새 낱말 300개 표본 문제 1.0%(경계 포함 2.0%, 기준 3%).
node 66 · python 12 · browser_game 121 · browser_modes 83 모두 통과(검수 사본). 관리자가 python 12 OK 재현. 변이 12 중 7 잡힘.

**남은 일** (대기 큐 1번, 모두 하) - 이것만 하면 `검사` 목표를 닫을 수 있음(가벼운 재검수 필요)
1. R27-N1: 갈래 파일의 어근·비표준 약 12개(`억울 솔직 명랑 온순 당당 씩씩 튼튼 든든 단단 쌀쌀 침울 패이다 개이다` -
   `자연마음.txt` 231~243 성격 묶음, `풀이씨.txt` 140·258) 지우고 `BANNED` 에. `불안 침착 순진 겸손 성실` 은 명사라 둠
2. R27-N2: 시험 빈틈 - 연습 쪽 하드 맞춤·입력 중 칸 유지 브라우저 검사(검수 탐침 C·D), `까닭` 을 `MUST` 에,
   `set(ANSWERS) == answers.txt 의 6칸` 확인(지금은 갈래 낱말이 정답에 섞여도 시험이 초록)
3. R27-N3: `tests/README.md` 의 수(61·8·62 → 66·12·83)
4. 덮는 범위는 아직 완전하지 않음: `잘못 불평 친정 늦잠 믿음 운명 행운` 같은 흔한 말이 빠져 있음 - 다음 보강 때 새 표본으로 잴 것

## R24 (2026-11-13)

**한 일** - 요청 `Q-261113-bd56` 의 첫 구현. 태석님 덧붙임(14:50 "화면·게임 방식은 웹워들과 비슷하게")대로
**`projects/웹워들/` 의 `web/`·`serve.py`·`tests/browser_harness.py`·`test_game.mjs`·`test_storage.mjs` 를 관리자가 복사해
출발점으로 두고** 자모에 맞게 바꿨습니다. R23 관리자의 설계(`app.js` 등 따로 짓기)는 버렸습니다. 그래프 4개·태스크 17개:
G-056 만들기(8) → 검수 1차(새 결함 13) → G-057·G-058 수정(6) → 재검수 2차(13 중 12 닫힘, 새 결함 6 모두 하)
→ G-059 보강(2) → 3차 확인. 목표 **13/15**.

- 규칙 정본·약속: `README.md` '규칙' 절, `.aimem/graph/inputs/r24/CONTRACT.md`(칸 = 두벌식 한 번 누름 = 호환 자모 한 글자,
  33글자; 겹모음 7·겹받침 11 은 두 칸; 정답·추측 6칸; 날마다 2026-11-13 이 1번)
- `web/js/jamo.js`(새) `toUnits`·`composeUnits`·`KEYMAP`·`SHIFTED`·`KEY_ROWS` / `game.js` 웹워들 API 그대로 칸 문자열 6칸,
  공유 `자모맞히기 N k/6`·연습 `자모맞히기 연습 k/6` / `ui.js` 화면 자판(⇧ 한 번)·`e.code` 입력(한글 입력기 `Process` 에서도)·
  `#preview` 조합 미리보기·`#modes` 날마다/연습(판 객체 따로, 연습은 저장·통계 없음)·정답 토스트를 판에 묶음 /
  `storage.js` 접두어 `jamo.`(모니터에서 웹워들과 통계 안 섞임)·저장값 없으면 시스템 어두운 모드 / `index.html` 도움말에 칸 규칙 표
- 낱말: `data/answers.txt`·`allowed.txt`(함대 작업자가 직접 고름) → `tools/build_words.py [--out]` → `web/js/words.js`.
  ANSWERS 380·ALLOWED 1033. 1차의 기계 조합(`정*`·`염*`·`역*`)·비속어·고유명사·민감어는 걷어 냈고 `test_words.py` 의
  `BANNED`·`MUST`·첫 음절 쏠림(≤40) 시험이 지킵니다

**바뀐 파일** - 이 폴더 거의 전부(새 프로젝트). 기록: `rounds/R24/REVIEW-r24.md`·`-2.md`·`-3.md`, 검증 스크립트 `.aimem/graph/inputs/r24/`.

**검증** - node 66(`test_jamo`·`test_game`·`test_storage`) · python 11(`test_words`) · 브라우저 121(`browser_game.py`) +
76(`browser_modes.py`) 모두 통과(3차 확인이 사본에서 재현). 변이: 1차 23 중 18, 2차 28 중 22, 3차 9 중 8 잡힘.

**남은 일** (대기 큐에도 있음)
1. **추측 목록이 얇다(중)** - 흔한 6칸 낱말 새 표본 60개 중 57개가 "없는 낱말". 지금 목록은 시험(`MUST`)에 적힌 낱말 주변만
   덮습니다. LLM 이 손으로 1000개를 더 쓰는 방식은 한계가 보였으니(첫 시도는 지어낸 말로 채움), **이용 조건이 분명한 공개
   사전 자료에서 6칸을 뽑는 길**을 태석님께 여쭤 정하십시오(내려받기·이용 조건). 그 전까지 '낱말 목록'·'검사' 목표는 열어 둡니다
2. 같은 묶음의 하: `data/README.md` 의 겹받침 예 `까닭` 이 ALLOWED 에 없음, 어근·경계 `희한 민망 괴악 희식 화성 국전`
3. 하: 하드 모드 설정이 다른 모드의 빈 판에는 새로 고칠 때까지 안 닿음(`REVIEW-r24-2.md` N5)
4. 다음 검수는 낱말 표본을 **시험에 없는 새 낱말**로 잴 것(3차가 그렇게 해서 찾았습니다)
