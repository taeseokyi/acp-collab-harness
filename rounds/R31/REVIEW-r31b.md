# R31 검수 2 - 연합뉴스 정답 고르기 (T-324~T-326, SPEC2) · S1 · T-327

기준: `.aimem/graph/inputs/r31/SPEC2.md`. 프로젝트 파일은 고치지 않았고, 실험은 `/tmp/s1r31b` 사본(끝나고 지움)에서 했다.
`P = projects/자모맞히기`.

## 1 재현

사본 루트(`/tmp/s1r31b`, `fleet.toml` 같이 복사)에서 돌림.

| 벌 | 명령 | 실제 | `tests/README.md` 표 |
|---|---|---|---|
| 로직·저장 | `node --test projects/자모맞히기/tests/*.mjs` | rc 0, `ℹ pass 94`, `ℹ fail 0` | 94 - 맞음 |
| 파이썬 | `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_*.py'` | rc 0, `Ran 97 tests`, `OK` | 97 - 맞음 |
| 화면 | `python3 projects/자모맞히기/tests/browser_game.py` | rc 0, `통과 121 / 전체 121` | 맞음 |
| 모드 | `python3 projects/자모맞히기/tests/browser_modes.py` | rc 0, `통과 100 / 전체 100` | 맞음 |
| 사전 | `python3 projects/자모맞히기/tests/browser_dict.py` | rc 0, `통과 75 / 전체 75` | 맞음 |
| 트렌드 | `python3 projects/자모맞히기/tests/browser_trend.py` | rc 0, `통과 45 / 전체 45` | 맞음 |

README 의 표(9~14행)는 실제와 같다. 다만 16행 문단은 아직 `로직 pass 90` 이라 적혀 표(94)와 어긋나고, 제목은 "다섯 벌" 인데
표는 여섯 줄이다(R31-N14, 하).

## 2 보안

`serve.Handler` 를 사본에서 띄우고 `trend_pick` 을 2초 걸리는 가짜로 바꿔 `http.client` 로 찔러 봄(`probe.py`).

- **출처** - `Host: evil.example`(포트 있든 없든) 403, `Origin: https://evil.example` 403, `Origin: null` 403,
  같은 출처 `Origin` 200. DNS 되돌림도 Host 검사에서 끊긴다.
- **Content-Type** - `text/plain`·`application/x-www-form-urlencoded`·없음 모두 400. 남의 페이지에서 단순 요청(폼·`no-cors`)으로는
  부를 수 없고, `application/json` 이면 사전 요청(OPTIONS)이 생기는데 `serve.py` 에는 OPTIONS 가 없어(501) 실제 POST 는 나가지 않는다.
- **본문** - 5KB 400, 빈 본문 400, JSON 배열 400, `days` 가 `true`·`1.5`·`"7"`·0·15 이면 400, `start` 가 `2026-02-30`·전각 숫자이면 400,
  `source` 가 `custom`·`__proto__` 이면 400, `skip` 61개·꼴이 틀리면 400. 다른 POST `/api/lookup` 405, GET `/api/trend/pick` 404.
- **잠금** - 첫 요청이 도는 동안 둘째 요청은 0.00s 만에 429 `이미 고르는 중입니다`. 그동안 `GET /api/sources`·`GET /` 는 0.00s 에 200
  (ThreadedServer 라 막히지 않음). 갈아 끼운 pick 이 예외를 던지면 연결은 끊기지만 `_PICK_LOCK` 은 풀린다(`locked() False`).
  진짜 `trend_news.pick` 은 모두 잡아 `{"ok": false}` 로 돌려준다.
- **느린 요청** - `Content-Length: 100` 에 1바이트만 보내고 붙들어도 다른 GET·pick 은 바로 됨(잠금 잡기 전에 본문을 읽으므로).
  다만 핸들러에 소켓 시간 제한이 없어 그 스레드는 상대가 끊을 때까지 묶인다. 잠금은 화면이 150초에 끊어도 서버가 끝날 때까지
  잡혀 있고, 최악의 실행 시간(피드 7×10초 + 묶음 12×(10초+3초+429 재시도 10초…))은 150초를 넘을 수 있다(R31-N12, 하).
- **RSS XML** - expat 2.7.3: 엔터티 폭탄은 `limit on input amplification factor … breached` 로 거절, 외부 엔터티(`SYSTEM "file:///etc/passwd"`)는
  `undefined entity` 로 거절 - 둘 다 그 피드만 건너뜀. **크기 상한은 없다** - `_read` 가 `response.read()` 를 통째로 읽어 36MB 피드를
  받아 길이 1200만 자 제목 하나를 만들었다(R31-N11, 하). `urlopen` 은 리다이렉트를 어느 호스트로든 따른다(주소는 고정 7개라 낮음).
- 서버는 파일을 쓰지 않는다(`trend_news`·`_trend_pick` 에 쓰기 없음) - 명세대로.

## 3 화면

- 낱말 숨김 - `browser_trend.py` 의 `낱말 글자가 화면 어디에도 없음`(innerText+textContent) 통과. 코드도 `#trend-status` 에 날짜·일수·제목 수만,
  토스트·aria 글에 낱말을 넣는 곳이 없다. `applyTrendPicks` 는 꼴(6칸·날짜)을 다시 보고 저장.
- 줄 낸 오늘 판 - 누를 때 이미 줄이 있으면 `start` 가 내일이고 오늘 판·낸 줄이 그대로임(`scenario_played_today` 통과).
  **그러나 응답을 기다리는 동안 줄을 내면 오늘 판이 바뀐다** - `/tmp` 재현(`race.py`, 같은 하네스): 빈 판에서 누름(`start: 2026-11-15`) →
  설정을 닫고 줄 하나 냄 → 오늘 날짜가 든 응답 → `jamo.trend` 에 `2026-11-15` 저장(판은 그대로 보임) → 새로 고치면 첫 줄이
  `['empty' ×6]` - 낸 줄이 사라지고 오늘 정답이 바뀐다. 상태 글이 "1분쯤" 이라 기다리며 판을 하는 것은 흔한 흐름이다(R31-N8, 중).
- 서버 없음 - 404 와 네트워크 오류면 `뉴스 정답 고르기는 serve.py 로 열었을 때만 됩니다 …`. 모니터 `/app/~<티켓>/<앱>/api/trend/pick` 은
  라우팅에서 404(인가된 티켓 경로)이고, sandbox(불투명 출처) iframe 의 JSON POST 는 사전 요청에서 실패(→ 네트워크 오류)라 둘 다 이 글이 나온다.
  **README 가 안내하는 `python3 -m http.server` 로 열면** POST 가 `501 Unsupported method` 라 `정답 고르기 실패: 서버 응답 501` 이 나와
  까닭이 안 보인다(실측, R31-N10, 하). 모니터의 티켓 없는·무인증 경로면 401 도 같은 꼴.

## 4 실물

- `data/trend.txt` 7개: 지원·혐의·진출·중단·논란·국회·전국. 위키낱말사전 분류 실측 - 모두 '…명사'. 지명·꼬리표·잘린 토막 없음, 정답으로 무난.
  (`혐의` 가 어두운 낱말이긴 하나 결함 아님.)
- `python3 /tmp/s1r31b/projects/자모맞히기/tools/pick_answers.py --days 2 --dry-run` (사본 = 저장소와 같은 파일, 진짜 네트워크) →
  `2026-11-22 서비스` / `2026-11-23 삼성` / `(뉴스 제목 668건, 후보 494개)` / `(dry-run: data/trend.txt 에 쓰지 않았습니다)`, 쓰기 없음.
  `ModuleNotFoundError` 는 고쳐졌고 trend.txt 의 날짜(11-15~21)를 건너뛰었다.
- 그러나 둘째 낱말 `삼성` 은 회사 이름으로 읽힌다(위키낱말사전엔 '한국어 명사' 로 있어 확인을 지남). 같은 까닭으로 `울산`·`광주` 도
  '명사' 분류라 stop 목록만이 지명을 막는다 - 목록에 없는 시·군(거제·안동 등)과 기업 이름은 지나간다. 조사 떼기도 3음절 이상
  낱말 끝의 `가/이/도/의` 를 떼어 `전문가→전문`·`어린이→어린`·`경기도→경기`·`고속도로→고속도` 를 만든다(R31-N13, 하).
- 실행 직후 같은 API 를 한 번 더 부르면 HTTP 429 - 실제 rate limit 이 있고, 코드의 3초 간격·한 번 재시도가 필요한 것이 맞다.

## 5 변이

사본에서 한 줄씩 바꾸고 해당 벌을 돌림(`mut.py`, 끝나면 원복).

| 변이 | 벌 | 결과 |
|---|---|---|
| 줄 낸 판도 오늘부터 (`todayPlayed = false`) | browser_trend | 잡힘 - `통과 44 / 전체 45`, `[FAIL] 줄을 낸 날은 요청 start 가 내일` |
| stop 거름 끔 (`blocked` 에서 stop 뺌) | unittest | 잡힘 - `FAIL: test_stop_and_existing_removed` |
| 기본 existing 에서 trend.txt 낱말 빠짐 | unittest | **못 잡음** - `OK` (R31-N14) |
| 잠금 없앰 | unittest | 잡힘 - `ERROR: test_trend_pick_busy_is_429` 외 1 |

## 6 결함

| 번호 | 심각도 | 무엇 | 어디 | 재현 | 고칠 방향 |
|---|---|---|---|---|---|
| R31-N8 | 중 | 고르는 중에 오늘 판에 줄을 내면, 늦게 온 응답의 오늘 낱말이 저장돼 새로 고친 뒤 낸 줄이 사라지고 오늘 정답이 바뀜 | `web/js/ui.js:applyTrendPicks` (`saveTrend(map)` 이 오늘을 무조건 저장) | 3절 `race.py`: 누름 → 설정 닫고 줄 하나 → 오늘이 든 응답 → 새로 고침 → 첫 줄 빈칸 | 응답 때 `dailyGame.rows.length > 0` 이면 `map` 에서 오늘을 빼고 저장(그리고 상태 글의 일수도 뺀 수로). browser_trend 에 이 흐름 한 시나리오 |
| R31-N9 | 중 | SPEC2(01:15:52) 뒤의 INBOX 지시가 명세·구현에 없음: 01:15 '마지막으로 고른 뒤 얼마나 지났는지' 표시, 01:22 서버가 정하고 저장·서버가 마지막 시각 저장, 01:26 모니터 '앱 열기' 에서 앱 파이썬을 한 번 불러 되게 | `rounds/R31/INBOX.md` 01:15~01:26 ↔ `SPEC2.md`·`ui.js`·`serve.py` | `grep -rn "전에 고름\|고른 적\|정한 적" P/web P/*.py` → 없음 | 관리자가 명세 3을 써서 잇거나 큐에 남김(01:22 는 '1~3 먼저, 4 는 큐' 허용) |
| R31-N10 | 하 | README 가 안내하는 정적 서버(`python3 -m http.server`)에서 누르면 `정답 고르기 실패: 서버 응답 501` - 까닭이 안 보임 | `ui.js:pickTrend` (404 만 서버 없음으로 봄) | 사본 `http.server` 에 JSON POST → `HTTP Error 501: Unsupported method ('POST')` | 404·405·501 또는 JSON 이 아닌 응답이면 `TREND_NO_SERVER` |
| R31-N11 | 하 | RSS 응답 크기 상한 없음 | `trend_news.py:_read` | 가짜 opener 로 36MB 피드 → 1200만 자 제목 하나, 거절 없음 | `response.read(2_000_001)` 후 넘으면 그 피드 건너뜀. (엔터티 폭탄·외부 엔터티는 expat 이 이미 막음) |
| R31-N12 | 하 | 최악 실행 시간이 화면 150초를 넘을 수 있고, 화면이 끊어도 잠금은 서버가 끝날 때까지 남아 다시 누르면 429. 핸들러 소켓 시간 제한 없음 | `trend_news.pick`·`serve.py` | 계산: 피드 7×10초 + 묶음 최대 12×(10+3+10…)초 | 전체 마감(예: 120초) 넘으면 거기까지로 끝냄, `Handler.timeout = 30` |
| R31-N13 | 하 | 정답 품질: 기업명(`삼성`, 실물 dry-run 11-23)·목록 밖 지명이 지나감, 조사 떼기가 `전문가→전문` 등 잘린 토막을 만듦 | `data/trend_stop.txt`, `trend_news.strip_josa` | 4절 dry-run 출력, `strip_josa('어린이')` → `어린` | stop 에 주요 기업·시군 보탬. 3음절 이상에서 1글자 조사(`가 이 도 의 로`)는 사전 확인에 원형도 같이 넣거나 떼지 않음 |
| R31-N14 | 하 | 검사·문서 빈틈: 기본 existing 에 trend.txt 낱말이 빠져도 검사가 못 잡음(같은 낱말이 다른 날짜에 겹칠 수 있음), 결과의 `checked` 는 429 로 일찍 끝나도 `min(후보, 600)` 이라 실제와 다름, tests/README 16행 `로직 pass 90`(표는 94)·"다섯 벌"(표는 여섯 줄) | `tests/test_trend_news.py`, `trend_news.pick`, `tests/README.md:5,16` | 5절 변이 3 → `OK` | `default_existing()` 을 임시 파일로 묻는 검사 한 줄, `checked` 는 실제 확인 수, README 문단을 표와 맞춤 |

## 7 판정

SPEC2 의 서버·명령줄·화면 요구는 대체로 맞고 보안 경계(출처·Content-Type·본문·잠금·XML 엔터티)는 실측으로 단단하다. 검사 여섯 줄 수가 README 표와 같고,
변이 4개 가운데 3개를 잡았다. 남은 것은 중 2건(R31-N8 고르는 중 경합, R31-N9 SPEC2 뒤의 INBOX 지시 미반영)과 하 5건이며 '상' 은 없다.

판정: 통과
