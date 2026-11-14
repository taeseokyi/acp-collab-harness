# R31 마지막 적대적 검수 - 자모맞히기 외부 사전 (T-317, S1)

기준: 요청 `Q-261114-e40c`, 명세 `.aimem/graph/inputs/r31/SPEC.md`. 대상 노드 T-310~T-316. 2026-11-15, 저장소 파일은 읽기만 했고
변이·실험은 `/tmp/s1r31/` 사본에서 함(끝에 지움). 자동 검사는 진짜 외부망을 부르지 않았고, 위키낱말사전만 손으로 두 번 불렀다.

## 1 재현

| 벌 | 명령 | 결과 | `tests/README.md` 의 수 |
|---|---|---|---|
| 로직 | `node --test projects/자모맞히기/tests/*.mjs` | `ℹ pass 89`, `ℹ fail 0` | **88** (어긋남, R31-N5) |
| 파이썬 | `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_*.py'` | `Ran 71 tests`, `OK` | 71 맞음 |
| 화면 | `python3 projects/자모맞히기/tests/browser_game.py` | rc 0, `통과 121 / 전체 121` | 맞음 |
| 모드 | `python3 projects/자모맞히기/tests/browser_modes.py` | rc 0, `통과 100 / 전체 100` | 맞음 |
| 사전 | `python3 projects/자모맞히기/tests/browser_dict.py` | rc 0, `통과 75 / 전체 75` | 수는 맞으나 README 는 "아직 초록이 아님(알려진 결함)" 이라 적음 (R31-N5) |
| 모니터 | `python3 -m unittest tests.test_aimem_monitor_app` | `Ran 53 tests`, `OK` | - |

README 의 '알려진 결함'(`toAllowedSet` 복사로 무한 재조회)은 이미 고쳐져 있다: `game.js:190` `allowWord(units)` 가 생기고
`ui.js:301` 이 `g.allowWord(guess)` 를 부른다. 그래서 사전 벌이 75/75 다. 문서만 낡았다.

## 2 보안

**키가 새는 길 (T-311 `dict_server.py`·`serve.py`)** - `/tmp` 사본에 가짜 opener 를 넣어 찔렀다(`srv_probe.py`).
- HTTPError(상류가 URL=키를 메시지에 넣음) → `"HTTP 오류 500"`, URLError → `"연결 실패"`, 알 수 없는 예외(메시지에 URL·헤더) →
  `"조회 중 알 수 없는 오류"`. 셋 다 키 없음. `_fetch` 가 종류만 말하고 `from None` 으로 원인을 끊는다. 좋음.
- `available_sources(env)` 에 키 값 없음(bool 만). `serve.py` 의 `log_message` 는 2xx 아닌 것만, 경로에는 word·source 뿐.
  POST 의 사용자 키는 본문이라 로그에 안 남음.
- 상류가 응답 본문에 키를 되돌려 주면 `evidence`(80자)에 실릴 수 있다(가짜 상류로 재현). 진짜 국립국어원·LLM 이 키를
  되돌려 줄 까닭이 없어 결함으로 치지 않음 - 참고만.
- 브라우저 `dict.js:errText` 는 fetch 오류 메시지에서 키를 `***` 로 가린다(재현: `failed Bearer ***`).

**열린 LLM 중계인가** - 아니다. 낱말 꼴 `^[가-힣]{1,10}$` 를 조회 전에 보고(공백·영문·자모·11자·빈 값 모두 거절, opener 안 불림),
system 프롬프트는 고정, `max_tokens 8`. custom 은 `https://` 로 시작해야 함(`http://`·`HTTPS://`·`https://` 만 → 거절, opener 안 불림).
- 단, 파이썬 `WORD_RE.match` 의 `$` 는 끝 줄바꿈 앞에서도 맞아 `"한국\n"` 이 통과해 바깥 호출이 나간다(R31-N3, 하).
- **교차 출처**: `serve.py` 는 Host·Origin·Content-Type 을 보지 않는다. 사용자가 `serve.py` 를 띄워 둔 채 아무 웹 페이지를
  열면 그 페이지가 `GET http://127.0.0.1:18811/api/lookup?word=…&source=kistillm` 을 단순 요청으로 보내 사용자의 KISTI·EXAONE·
  Gemini·국립국어원 키 한도를 쓰게 할 수 있고, `POST`(Content-Type `text/plain`)의 `custom.base_url` 로 임의 `https://` 호스트
  (`https://127.0.0.1:<포트>` 포함)에 고정 본문 POST 를 보내게 할 수 있다(맹목 SSRF). 응답은 CORS 머리가 없어 못 읽지만
  DNS 리바인딩이면 읽힌다(키는 여전히 안 나옴). 게다가 브라우저 `lookupWord` 는 custom 을 늘 직접 부르므로 **`POST /api/lookup`
  은 화면이 쓰지 않는 길**이다(R31-N1, 중).

**모니터 CSP `connect` 거름 (T-315)** - `app_connect_origins` 에 적대 입력 24개를 넣었다(`csp.py`):
`; script-src *`, `'unsafe-eval'`, 따옴표·쉼표·탭·줄바꿈 꼬리, 대문자(`HTTPS://`, `A.com`), 유니코드 호스트(`한국.kr`, 켈빈 기호 `K`),
`*`·`*.a.com`, `http://`·`wss://`·`data:`, 포트 0·99999·두 개, 끝 `/`, 앞 공백, 점 없는 `localhost` → **모두 버림**.
`fullmatch` + ASCII 소문자 클래스라 우회 못 찾음. 퓨니코드(`xn--…`)는 통과 - 정상. 11개 이상은 앞 10개만. 목록이 아니면 빈 목록.
`app_csp` 는 한 번 더 거르고 `connect-src` 에만 보탠다. 통과.

**사용자 키를 localStorage 에 두는 위험의 안내** - 부족(R31-N2, 중). Gemini/OpenRouter 키 입력에는 placeholder
`이 기기에만 저장됩니다` 뿐이고, 사용자 LLM 키 입력에는 아무 안내가 없다. 키는 `jamo.dict` 에 평문으로 들고, 모니터 iframe 안에서는
`storage.js:sendToParent` 가 같은 값을 **모니터 출처의 저장소**로도 보낸다(`app.js:3806` `putIfFits`). 화면이 "평문으로 이 브라우저에
남고, 같은 출처의 스크립트가 읽을 수 있다 · 무료/한도 있는 키만 넣으라" 를 말하지 않는다.

## 3 동작

- **조회 중 입력 막기·두 번 제출**: `handleKey` 가 `looking` 이면 무시(`ui.js:246`), `submit` 은 `!looking` 일 때만 조회,
  조회 뒤 재제출은 `afterLookup=true` 로 한 번만. `browser_dict.py` 의 '느린 조회 중 Enter 여러 번 → 요청 하나' 가 지킴.
  변이 M7(가드에서 `looking` 뺌)을 넣으니 73/75 로 잡힘.
- **찾은 낱말 저장·하드 모드**: 있음 → `ALLOWED_SET.add` + `g.allowWord` + `WORD_OF` + `addExtraWord`, 시작 때
  `loadExtraWords()` 를 보탬(`ui.js:765`), 최대 500. 재제출은 `game.submit()` 을 다시 타므로 하드 모드 검사도 그대로 걸린다.
- **판이 바뀐 경우**: 조회 중 모드를 바꾸면 `g !== game` 이라 결과를 버림(`ui.js:297`). 좋음.
- **키 없는 사전**: 서버 `{"ok":false,"error":"키가 없습니다: STDICT_API_KEY"}`, 화면 목록엔 ` (키 없음)`, 토스트 `사전 조회 실패: …`.
- **모니터(서버 없음)**: 가짜 fetch 로 `api/` 404 · HTML 200(JSON 아님) · 500 세 경우 모두 위키는 `via:"direct"` + `origin=*` 로 떨어짐,
  `stdict` 는 `이 사전은 serve.py 로 열었을 때만 됩니다`. 모니터의 `/app/<이름>/api/lookup` 은 `project_app_file` 이 404 JSON 을 낸다.
- **TREND 날짜 경계** (TZ Asia/Seoul): `2026-11-19 23:59:59.999` → 기존 정답, `11-20 00:00:00.000`·`23:59:59.999` → `첫눈`,
  `11-21 00:00` → 기존. 셋째 인자 없음 → 기존. 프로토타입 키는 안 탐(`hasOwnProperty`). `build_words.py` 는 꼴 틀린 줄·날짜·6칸 아님·
  같은 날짜 두 번을 경고하고 버림. 변이 M4(UTC 날짜 키)가 잡힘.
- **pick_answers 거름**: `HANGUL.fullmatch` → `units` 6칸 → 기존(trend.txt·answers.txt) 제외 → 중복 제외 → `lookup` 이
  `ok is True and found is True` 인 것만 → 비어 있는 다음 날짜. 키 없으면 rc 2 + 받는 곳. 키는 `x-goog-api-key` 헤더라 오류 글에 안 섞임.
- **LLM 답 읽기**: `예.`/`"예"`/`Yes` → 있음, `아니오`/`No.` → 없음, `네` → 알 수 없음. `Not sure`·`normal`·`nothing` 도 `no` 로
  시작해 '없음' 이 된다 - 명세 글자 그대로라 결함으로 치지 않음(없음 쪽으로 틀리면 기존 거절과 같아 해가 작음).
- 브라우저 `lookupWord` 는 custom 주소의 `https://` 를 다시 보지 않는다(화면 더하기에서만 거름). 저장소가 조작·옛 값이면
  `serve.py` 로 연 페이지(CSP 없음)에서 `http://` 로 키를 보낸다(R31-N7, 하).

## 4 실물 (위키낱말사전, 키 없음, 손으로 한 번)

```
curl 'https://ko.wiktionary.org/w/api.php?action=query&titles=한국&format=json&formatversion=2&redirects=1&origin=*'
{"batchcomplete":true,"query":{"pages":[{"pageid":1232,"ns":0,"title":"한국"}]}}
… titles=한국어사전없는말 …
{"batchcomplete":true,"query":{"pages":[{"ns":0,"title":"한국어사전없는말","missing":true}]}}
access-control-allow-origin: *
```
이 두 응답을 그대로 `parseMediawiki` 에 넣으면 `true` / `false`. 파이썬 `_do_lookup` 의 판정(`missing`·`invalid` 없음)도 같은 꼴.
`origin=*` 에 `access-control-allow-origin: *` 가 와서, 모니터의 sandbox iframe(Origin `null`)에서도 직접 조회가 된다.

## 5 변이 (`/tmp` 사본)

| 번호 | 넣은 변이 | 돌린 검사 | 잡힘 |
|---|---|---|---|
| M1 | `parseMediawiki` 가 `missing` 무시 | node | 잡힘 (fail 2) |
| M2 | 서버 `lookup` 의 낱말 꼴 검사 제거 | 파이썬 | 잡힘 (`test_bad_word_shapes_never_call_opener`) |
| M3 | HTTP 오류 글에 `e.url`(키 든 URL) 싣기 | 파이썬 | 잡힘 (`test_http_error_hides_key`) |
| M4 | TREND 날짜 키를 UTC(`toISOString`)로 | node | 잡힘 (fail 1) |
| M5 | 서버 custom 이 `http://` 허용 | 파이썬 | 잡힘 (`test_http_rejected`) |
| M6 | 서버 404 뒤 위키 직접으로 안 떨어짐 | node | 잡힘 (fail 2) |
| M7 | `handleKey` 에서 `looking` 가드 제거 | `browser_dict.py` | 잡힘 (73/75) |

사본(`/tmp`)에서는 변이와 무관하게 `test_kisti_base_url_from_fleet_toml` 이 ERROR 다 - 검사가 저장소의 진짜 `fleet.toml`
(사본 위치에서 두 단계 위)에 기대기 때문(R31-N6, 하). 저장소 안에서는 통과.

## 6 결함

| 번호 | 심각도 | 무엇 | 어디 | 재현 | 고칠 방향 |
|---|---|---|---|---|---|
| R31-N1 | 중 | `/api/*` 가 Host·Origin·Content-Type 을 안 봐서 아무 웹 페이지가 로컬 서버로 사용자 키 한도를 쓰고(GET), 임의 https 호스트로 맹목 POST(custom) 를 보낼 수 있음. DNS 리바인딩이면 결과도 읽힘. `POST /api/lookup` 은 화면이 안 씀 | `serve.py:_api` | `Origin: https://evil.example`·`Host: evil.example` 로 `GET /api/lookup?source=kistillm` → 200·lookup 불림; `text/plain` POST custom `https://attacker.example/v1` → lookup 불림 (`srv_probe.py`) | Host 가 `127.0.0.1`/`localhost`(+포트)가 아니면 403, `Origin` 이 있고 자기 출처가 아니면 403, POST 는 `application/json` 만. 화면이 안 쓰는 POST custom 은 빼는 것도 방법 |
| R31-N2 | 중 | 사용자 키를 평문 localStorage(모니터에선 모니터 출처 저장소에도) 두는 위험이 화면에 안내되지 않음. 사용자 LLM 키 칸엔 안내 없음 | `index.html:84,95`, `storage.js:sendToParent` | 설정 창 열기 - placeholder `이 기기에만 저장됩니다` 만 보임 | 키 칸 아래 한 줄: "이 브라우저에 평문으로 저장됩니다. 한도 있는 무료 키만 넣고, 공용 기기에선 지우십시오" |
| R31-N3 | 하 | 서버 낱말 꼴 검사가 끝 줄바꿈을 통과시킴(`re.match` + `$`) | `dict_server.py:257` | `lookup("한국\n","wiktionary")` → opener 불림; GET `word=%ED%95%9C%EA%B5%AD%0A` 도 같음 | `WORD_RE.fullmatch` 또는 `\Z`, 검사에 `"한국\n"` 한 줄 |
| R31-N4 | 하 | 명세 1절의 "나무위키·구글은 공식 무료 API 가 없어 안 넣음" 한 줄과 외부 사전 쓰는 법(serve.py·키·pick_answers)이 프로젝트 README 에 없음 | `projects/자모맞히기/README.md` | `grep 나무위키 README.md` → 없음 | README 에 외부 사전 절(출처 표·키는 `.env`·모니터에선 위키·사용자 키만·나무위키/구글 까닭 한 줄·`pick_answers.py` 쓰는 법) |
| R31-N5 | 하 | 테스트 README 가 낡음: 로직 88(실제 89), 사전 벌 '아직 초록 아님'·'알려진 결함'·목표 표 '부분'(실제 75/75, `allowWord` 로 고쳐짐) | `tests/README.md:9,15-16,33-37,84` | 1절 표 | 수를 89 로, '알려진 결함' 절을 '고쳐짐(Game.allowWord)' 으로, 목표 표를 '증명됨' 으로 |
| R31-N6 | 하 | `test_kisti_base_url_from_fleet_toml` 이 저장소의 진짜 `fleet.toml` 에 기대 사본·다른 위치에서 ERROR | `tests/test_dict_server.py` | `/tmp` 사본에서 unittest → ERROR 1 | 임시 `fleet.toml` 을 만들어 `dict_server.FLEET_TOML` 을 갈아 끼움 |
| R31-N7 | 하 | 브라우저 `lookupWord` 가 custom 주소의 `https://` 를 다시 보지 않음 | `dict.js:lookupWord` custom 갈래 | `customs:[{baseUrl:'http://evil.example/v1'}]` → `http://…/chat/completions` 로 키 실어 보냄 (`real.mjs`) | `directLookup` 전에 `/^https:\/\//` 확인, 아니면 오류 |

## 7 판정

노드별 평:
- **T-310 `dict.js`**: 명세 함수·꼴 그대로, 던지지 않음, 키 가림, 404·HTML·500 모두 위키 직접으로 떨어짐. custom 의 https 재확인만 빠짐(N7).
- **T-311 `dict_server.py`·`serve.py`**: 키 누출 길 없음(오류·로그·sources), 고정 프롬프트·꼴 검사로 열린 중계 아님, 4KB 상한·404 JSON 정상. 교차 출처 막이 없음(N1), 정규식 `$`(N3).
- **T-312 TREND 빌드·`answerForDate`**: 로컬 날짜 경계 정확, 셋째 인자 없는 호출 그대로, 잘못된 줄 경고 후 버림. 결함 없음.
- **T-313 화면**: 명세 id 모두 있음, 조회 중 입력 막기·한 번만 재조회·판 바뀜 처리 좋음, 기존 거절 문구로 시작. 키 저장 위험 안내 부족(N2).
- **T-314 `pick_answers.py`**: 거름 순서·rc 2·dry-run 명세대로, 키가 헤더라 오류 글에 안 섞임. 결함 없음.
- **T-315 모니터 CSP**: 적대 입력 24개 모두 막음. 결함 없음.
- **T-316 검사·README**: 다섯 벌 모두 초록이고 변이 7개를 다 잡음. README 의 수·'알려진 결함'이 낡음(N5), fleet.toml 의존(N6).

'상' 결함 없음. 중 2건(N1 로컬 서버 교차 출처, N2 키 저장 안내)은 후속 일로 넘기면 됨.

판정: 통과 - '상' 결함 없음, 키는 어떤 응답·오류·로그로도 새지 않고 검사 다섯 벌 초록·변이 7/7 잡힘; 중 2건(R31-N1·N2)과 하 5건은 후속으로
