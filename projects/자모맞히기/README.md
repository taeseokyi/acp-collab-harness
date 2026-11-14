# 자모맞히기

한글 낱말을 **자모 여섯 개**로 풀어 여섯 번 안에 맞히는 게임입니다(요청 `Q-261113-bd56`).
기본은 **정적 웹 게임**(`web/`, 서버 없음)이고, 저장 목록에 없는 낱말을 **외부 사전·AI 모델**에
물어보는 기능과 **뉴스로 날짜별 정답을 고르고 지난 시간을 보여 주는 일**은 로컬 `serve.py`
(국립국어원·KISTI·EXAONE)가 맡습니다. 브라우저가 직접 부르는 조회(위키, 사용자가 키를 넣은 LLM)도
씁니다. 낱말 맞히기 장르의 규칙과 손맛만 참고했고, 이름·화면·색·문구·
낱말 목록·코드는 모두 이 프로젝트에서 새로 지었습니다.

## 규칙 (R23 에서 관리자가 정함)

- **한 칸 = 두벌식 자판 한 번 누름.** 그래서
  - 쌍자음 `ㄲ ㄸ ㅃ ㅆ ㅉ` 과 `ㅐ ㅔ ㅒ ㅖ` 는 한 칸입니다 (`ㅃ ㅉ ㄸ ㄲ ㅆ ㅒ ㅖ` 는 Shift)
  - 겹모음은 두 칸으로 풉니다: `ㅘ=ㅗㅏ ㅙ=ㅗㅐ ㅚ=ㅗㅣ ㅝ=ㅜㅓ ㅞ=ㅜㅔ ㅟ=ㅜㅣ ㅢ=ㅡㅣ`
  - 겹받침도 두 칸입니다: `ㄳ=ㄱㅅ ㄵ=ㄴㅈ ㄶ=ㄴㅎ ㄺ=ㄹㄱ ㄻ=ㄹㅁ ㄼ=ㄹㅂ ㄽ=ㄹㅅ ㄾ=ㄹㅌ ㄿ=ㄹㅍ ㅀ=ㄹㅎ ㅄ=ㅂㅅ`
- 정답은 이렇게 풀었을 때 **꼭 여섯 칸**인 낱말입니다 (예: `한국` = ㅎㅏㄴㄱㅜㄱ, `까닭` = ㄲㅏㄷㅏㄹㄱ)
- 추측도 낱말 목록에 있는 여섯 칸 낱말이어야 합니다
- 색: **자리 맞음 / 들어 있음 / 없음.** 같은 자모가 여러 번 나오면 자리 맞음을 먼저 세고, 정답에 남은
  개수만큼만 '들어 있음' 을 줍니다
- **날마다 하나**(2026-11-13 이 1번, 누구에게나 같음)와 **연습**(무제한, 무작위) 두 모드

## 폴더

화면·흐름(판·뒤집기·화면 자판·도움말/통계/설정 창·어두운 모드·공유)은 **`projects/웹워들/` 을 가져와**
자모에 맞게 바꿨습니다(R24, 요청의 14:50 덧붙임).

| 경로 | 무엇 |
| ---- | ---- |
| `web/` | 정적 게임 (서버 없이도 열림). `index.html`, `css/style.css`, `js/` |
| `web/js/jamo.js` | 칸 풀기(`toUnits`)·조합(`composeUnits`)·두벌식 자판 표(`KEYMAP`·`SHIFTED`·`KEY_ROWS`) - 순수 함수 |
| `web/js/game.js` | 판정·날짜·판 상태·하드 모드·공유 글 - 웹워들 game.js 를 칸 문자열 6칸으로 바꾼 것 (순수) |
| `web/js/storage.js` | `localStorage`(접두어 `jamo.`) - 통계·설정·오늘 판(판의 정답 포함). 모니터 미리보기 칸에서는 부모에 맡김 |
| `web/js/words.js` | 낱말 목록 - `tools/build_words.py` 가 `data/*.txt` 에서 생성 (손으로 고치지 않음) |
| `web/js/dict.js` | 외부 사전 조회(브라우저) - 출처 목록(`SOURCES`)·조회(`lookupWord`)·LLM 답 읽기. 위키는 직접, 나머지는 서버 |
| `web/js/trend.js` | 뉴스 정답의 지난 시간 글(`sinceText`)·정적+서버 정답 합치기(`mergeTrend`) - 순수 함수(DOM 없음) |
| `web/js/ui.js` | 화면·입력(`e.code`)·날마다/연습 모드·외부 사전·뉴스 정답 흐름. 진입점 |
| `data/` | 손으로 고른 낱말 원본과 고른 기준(`data/README.md`) |
| `data/trend.txt` | 날짜별 트렌드 정답 **정본** - `trend_store.py`·`tools/pick_answers.py`·앱 서버가 덧붙임(이미 있는 날짜는 안 덮음). 마지막으로 정한 시각은 `data/trend_meta.json`. `build_words.py` 가 `TREND` 로 |
| `tools/build_words.py` | 원본을 걸러 `words.js` 생성 |
| `tools/pick_answers.py` | 연합뉴스 RSS 제목에서 6칸 낱말을 골라 사전에 있는 것만 `data/trend.txt` 에 덧붙이고 `words.js` 재생성 - 앱 서버와 같은 `trend_store.pick_and_store` |
| `trend_store.py` | 트렌드 정답 저장소(표준 라이브러리만) - 읽기·덧붙이기·마지막 시각·`pick_and_store`. 쓰기는 잠금 안에서 임시 파일 → `os.replace` |
| `trend_news.py` · `data/trend_stop.txt` | 뉴스 제목 읽기·후보 뽑기·사전 확인 · 정답에서 뺄 낱말(사람이 고침) |
| `tests/` | 단위 검사(`node --test`, `unittest`)와 브라우저 검사(Playwright) - 돌리는 법은 `tests/README.md` |
| `serve.py` | 로컬 서버 - 정적 파일 + 외부 사전 조회 `/api/sources`·`/api/lookup`, 뉴스 정답 `GET /api/trend`·`POST /api/trend/pick` (키는 서버만) |
| `dict_server.py` | 서버 쪽 외부 사전 조회 - 국립국어원·KISTI·EXAONE 등. 키는 저장소 `.env`/환경변수 |
| `app.json` | 함대 모니터 '결과물 실행' 선언 - `"server": "serve.py"` 면 모니터가 그 서버를 자식 프로세스로 띄워 `/api/*` 를 이어 줌 (`connect` 는 브라우저 직접 조회 출처) |

## 실행

서버 없이 정적 파일만 열어도 게임은 됩니다(그때 외부 사전은 위키 직접 조회와 사용자가 키를 넣은 LLM 만).

```bash
python3 -m http.server -d projects/자모맞히기/web 8000   # 정적만: 그리고 http://127.0.0.1:8000/
python3 projects/자모맞히기/serve.py [--host 127.0.0.1] [--port 18811]   # 서버 사전·정답 고르기까지 쓰려면 이쪽
```

함대 모니터에서는 '앱 열기' 로 `/app/자모맞히기/` 가 열립니다. `app.json` 의 `"server": "serve.py"` 선언을 보고
모니터가 그 파일을 `--host 127.0.0.1 --port <빈 포트>` 로 **자식 프로세스**로 띄운 뒤, 앱 화면의
`/app/자모맞히기/api/*` 호출을 그 프로세스로 이어 줍니다(정적 파일은 모니터가 냅니다). 그래서 모니터에서 열어도
서버 사전과 '지금 뉴스에서 정답 고르기' 가 따로 띄운 것과 똑같이 됩니다. 앱이 할 일은 `--host`·`--port` 를 받는
것뿐입니다. 모니터는 자기 접근 토큰·세션·쿠키와 `*_API_KEY` 를 자식 환경이나 이어 주는 요청에 싣지 않습니다.

## 외부 사전

저장 낱말 목록에 없는 추측은 설정 창의 **외부 사전으로 확인**(기본 켬)이 켜져 있으면 외부 사전·AI 모델에
물어보고, 있으면 받아 줍니다. 출처는 아래 표와 같고 화면에서 고릅니다(브라우저는 `web/js/dict.js` 의
`SOURCES`, 서버는 `dict_server.py` 의 `SOURCES`).

| id | 이름(화면) | 키 env | 브라우저 직접 | 키 받는 곳 |
| --- | --- | --- | --- | --- |
| `wiktionary` | 위키낱말사전 (**기본**) | - | 됨 | - |
| `wikipedia` | 한국어 위키백과 | - | 됨 | - |
| `stdict` | 표준국어대사전(국립국어원) | `STDICT_API_KEY` | 안 됨(서버) | https://stdict.korean.go.kr/openapi/openApiInfo.do |
| `opendict` | 우리말샘(국립국어원) | `OPENDICT_API_KEY` | 안 됨 | https://opendict.korean.go.kr/service/openApiInfo |
| `krdict` | 한국어기초사전(국립국어원) | `KRDICT_API_KEY` | 안 됨 | https://krdict.korean.go.kr/openApi/openApiInfo |
| `kistillm` | KISTI LLM (함대 설정) | `KISTI_API_KEY` | 안 됨 | `fleet.toml` `[providers.kisti]` |
| `exaone` | EXAONE (함대 설정) | `EXAONE_API_KEY` | 안 됨 | `fleet.toml` `[providers.exaone]` |
| `gemini` | Google Gemini (무료 키) | `GEMINI_API_KEY` | 됨(사용자 키) | https://aistudio.google.com/apikey |
| `openrouter-free` | OpenRouter 무료 모델 | `OPENROUTER_API_KEY` | 됨(사용자 키) | https://openrouter.ai/keys |
| `custom:<n>` | 사용자가 더한 LLM | 사용자 입력 | 됨 | OpenAI 호환 `{base_url}/chat/completions` |

- **키 넣는 법.** 국립국어원·KISTI·EXAONE 같은 서버 사전 키는 저장소 루트 `.env` 에 `KEY=값` 줄로 두거나
  같은 이름의 환경변수로 줍니다(환경변수가 우선). 키는 서버만 알고 브라우저로 나가지 않습니다.
- **`/api/*` 가 있는 곳에서만.** 서버 사전(국립국어원·KISTI·EXAONE)은 `serve.py` 가 떠 있을 때만 됩니다 -
  `python3 projects/자모맞히기/serve.py` 로 직접 열거나, 함대 모니터의 '앱 열기' 가 `app.json` 의
  `"server": "serve.py"` 를 보고 띄울 때입니다. `/api/*` 가 없는 정적 서버에서만 그 출처가
  `이 사전은 serve.py 로 열었을 때만 됩니다` 로 실패합니다.
- **EXAONE 한도.** EXAONE 은 연달아 부르면 429 가 곧 걸림 - 추측마다 조회에 쓰기엔 한도가 빡빡함.
- **모니터에서는.** 함대 모니터에서도 위키를 브라우저가 직접 조회하고 사용자 키 LLM
  (`gemini`·`openrouter-free`·사용자 LLM)을 쓸 수 있으며, 서버 사전(국립국어원·KISTI·EXAONE)도 모니터가
  띄운 `serve.py` 를 거쳐 됩니다. 브라우저 직접 조회의 허용 출처는 `app.json` 의 `connect` 목록이 정합니다
  (`https://ko.wiktionary.org`·`https://ko.wikipedia.org`·`https://generativelanguage.googleapis.com`·`https://openrouter.ai`).
- **사용자 키 주의.** 사용자가 화면에서 넣는 키는 이 브라우저에 **평문으로 저장**됩니다(같은 출처 스크립트가
  읽을 수 있음). 한도 있는 무료 키만 넣고, 공용 기기에서는 지우십시오.
- **넣지 않은 곳.** 나무위키·구글 검색은 공식 무료 조회 API 가 없어(나무위키는 API 없음, 구글 Custom Search 는
  키+검색엔진 id 필요) 출처로 넣지 않았습니다.

## 트렌드 정답

날짜별 정답의 **정본은 서버의 `data/trend.txt`** 입니다(`YYYY-MM-DD 낱말` 줄, `#` 주석). 마지막으로 정한
시각은 `data/trend_meta.json` 의 `{"last_run": "..."}` 에 둡니다. 연합뉴스 RSS(`yna.co.kr/rss/*.xml`, 키 없음)의
기사 제목에서 한글 토막을 뽑아 조사를 떼고 → 자모 6칸·기존 낱말·`data/trend_stop.txt` 제외 → 기사 수 많은 순으로
위키낱말사전(기본)에 있는 명사만 골라, 날짜마다 하나씩 정답으로 삼습니다. 뉴스 RSS 는 브라우저가 직접 못 읽어
(CORS) 서버나 명령줄에서만 됩니다.

- **서버가 저장.** `trend_store.py` 가 `data/trend.txt` 를 읽고(`read_trend`) 덧붙이며(`append_picks`), 마지막으로
  정한 시각을 `data/trend_meta.json` 에 적습니다(`record_run`). 이미 있는 날짜는 **절대 덮어쓰지 않습니다** -
  그래서 오늘 정답은 한 번 정해지면 안 바뀝니다.
- **앱 서버.** `GET /api/trend` 는 `{"ok": true, "trend": {날짜: 낱말}, "last_run": ISO|null}` 을 돌려줍니다
  (오늘보다 앞선 날짜도 그대로 - 고르는 것은 화면). `POST /api/trend/pick` 은 뉴스에서 골라 빈 날짜에만 덧붙이고
  `added`·`trend`·`last_run` 을 돌려줍니다. `Handler.timeout = 30`.
- **화면은 받아 씀.** 열 때 `GET /api/trend` 로 받아 `mergeTrend(TREND, 서버)` 로 하루 정답에 쓰고(다시 빌드
  없이), 단추 성공 뒤에도 응답의 `trend`·`last_run` 으로 같은 일을 합니다. 설정 창 단추 옆
  `<span id="trend-since">` 에 `sinceText(last_run)` 로 '방금 정함'·'N분 전에 정함'·'N시간 전에 정함'·
  'N일 전에 정함' 을 적고, 창을 열 때마다 지금 기준으로 다시 씁니다. 서버가 없으면(GET 실패)
  '서버 없이 열어 정한 때를 모릅니다' 이고 정적 `TREND` 만 씁니다. 낱말은 화면에 보이지 않습니다.
- **브라우저 저장은 없어짐.** 예전 `localStorage` `jamo.trend` 는 걷어냈습니다(남은 키는 한 번 지움). 정본은 서버입니다.
- **판 정답 고정.** 오늘 판에 줄이 있으면 그 판의 정답은 새로 고친 뒤에도 바뀌지 않습니다 - 오늘 판을 저장할 때
  그 판의 정답도 같이 저장하고, 줄이 있는 저장 판은 그 정답으로 되살립니다. 오늘 판이 비어 있을 때만 새 오늘
  정답으로 다시 시작합니다.
- **명령줄.** `tools/pick_answers.py` 도 같은 `trend_store.pick_and_store` 를 써서 `data/trend.txt` 에 덧붙이고
  `words.js` 의 `TREND` 를 다시 만듭니다. 모든 사람 공통입니다.
- **모니터 '앱 열기' 에서도 됨.** `app.json` 의 `"server": "serve.py"` 선언을 보고 모니터가 그 파일을
  `--host`·`--port` 로 자식 프로세스로 띄워 `/app/자모맞히기/api/*` 를 이어 줍니다. 앱이 할 일은 `--host`·`--port`
  를 받는 것뿐이라, 따로 띄운 `serve.py` 와 똑같이 정답 고르기·서버 사전이 됩니다.

```bash
python3 projects/자모맞히기/tools/pick_answers.py --days 7 --dry-run   # 확인만 (오늘부터 7일, 이미 있는 날짜는 건너뜀)
python3 projects/자모맞히기/tools/pick_answers.py --days 7             # trend.txt 덧붙임 + words.js 재생성
```

옵션: `--source wiktionary`(기본) · `--start YYYY-MM-DD`. 연합뉴스·위키에 닿지 않으면 rc 1 과 까닭을 냅니다.

- **날마다 다시 채우는 법.** 일주일에 한 번 사람이 `pick_answers.py --days 7` 을 돌리고 `trend.txt`·`words.js` 를
  커밋합니다(다 떨어진 날은 원래 정답 목록으로 돌아갑니다). 급하면 게임 전에 설정 창 단추를 눌러도 됩니다.
- **어색한 낱말 빼기.** 정답으로 어색한 낱말(지명·잘린 토막·기사 꼬리표·너무 전문어)은 `data/trend_stop.txt` 에
  한 줄에 하나씩 적고(`#` 는 주석) 다시 `--dry-run` 으로 확인합니다. 이미 `trend.txt` 에 든 날짜는 건너뛰므로
  바꾸려면 그 줄을 고친 뒤 `python3 projects/자모맞히기/tools/build_words.py` 로 `words.js` 를 다시 만듭니다.

## 낱말 목록의 출처와 이용 조건

함대 작업자가 일상어에서 **직접 고른** 낱말입니다(외부 게임·사전의 목록을 복사하지 않음). 낱말 자체는
저작물이 아니며, 이 목록 파일은 저장소와 같은 조건을 따릅니다. 자세한 고른 기준은 `data/README.md`.
