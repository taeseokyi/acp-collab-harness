# 자모맞히기 테스트

명령은 모두 **저장소 루트**(`projects/` 가 보이는 곳)에서 돌립니다.

## 여섯 벌과 돌리는 명령

| 무엇 | 파일 | 명령 | 초록이면 |
|---|---|---|---|
| 로직·저장 | `test_game.mjs` · `test_jamo.mjs` · `test_storage.mjs` · `test_dict.mjs` · `test_trend.mjs` | `node --test projects/자모맞히기/tests/*.mjs` | `ℹ pass 107`, `ℹ fail 0` |
| 낱말 목록·사전 서버·정답 고르기 | `test_words.py` · `test_dict_server.py` · `test_pick_answers.py` · `test_trend_news.py` · `test_trend_store.py` | `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_*.py'` | `Ran 132 tests`, `OK` |
| 브라우저 - 그려진 화면 | `browser_game.py` | `python3 projects/자모맞히기/tests/browser_game.py` | rc 0, `통과 121 / 전체 121` |
| 브라우저 - 모드 오가기·시스템 테마 | `browser_modes.py` | `python3 projects/자모맞히기/tests/browser_modes.py` | rc 0, `통과 100 / 전체 100` |
| 브라우저 - 외부 사전 조회(R31) | `browser_dict.py` | `python3 projects/자모맞히기/tests/browser_dict.py` | rc 0, `통과 75 / 전체 75` |
| 브라우저 - 뉴스 정답 고르기(R31·R32) | `browser_trend.py` | `python3 projects/자모맞히기/tests/browser_trend.py` | rc 0, `통과 81 / 전체 81` |

2026-11-15 (R32 T-334) 단위 검사 수: 로직 `pass 107`·`fail 0`, 파이썬 `Ran 132 tests`·`OK`, 화면 `통과 121 / 전체 121` rc 0,
모드 `통과 100 / 전체 100` rc 0, 사전 `통과 75 / 전체 75` rc 0, 트렌드 `통과 81 / 전체 81` rc 0 - 여섯 벌 모두 초록.
(R31 T-318 때는 로직 90·파이썬 97·트렌드 45, 그 앞 R28 T-302 때는 로직 66·낱말 13.)
`test_trend_store.py`(R32)는 서버 정답 저장소 `trend_store.py` 를 임시 파일로만 검사하고(진짜 `data/` 는 안 건드림),
`test_trend.mjs`(R32)는 `web/js/trend.js` 의 `sinceText`·`mergeTrend` 를 검사합니다. 함대 쪽
`tests/browser_monitor_app_server.py` 는 모니터의 '앱 열기' 가 이 프로젝트의 `serve.py` 를 띄워 `/api/*` 를 이어 주는지
보는 검사입니다(이 프로젝트가 첫 사용자, 임시 루트에 진짜 모니터를 띄우고 임시 복사본만 씀).

`browser_modes.py` 는 R24 의 N4~N9·N12·N13 을 그려진 화면으로 묻고, 연습 정답 토스트가 모드를 따라
새지 않는지(R24-N5), 연습 쪽 하드 맞춤이 빈 연습 판에 닿는지(T-301 `scenario_hard_reaches_empty_practice`),
입력 중 글자가 정렬 뒤에도 남는지(T-301 `scenario_typed_letters_survive_align`), 낸 줄이 있는 판의 하드 잠금
(T-304 `scenario_hard_locked_after_play`), 빈 판 맞춤이 판 번호를 지키는지(T-304 `scenario_align_keeps_puzzle_number`)도 지킵니다.

검사 수는 시나리오가 중간에 죽으면 줄어듭니다(남은 검사가 기록되지 않음). **수가 위와 다르면 rc 0 이어도
의심하십시오.** 브라우저 스크립트는 맨 끝에 `통과 n / 전체 m` 을 찍고, rc 는 실패한 검사 수입니다.
브라우저를 못 띄우면 rc 2 입니다.

`browser_dict.py` (T-316) 는 외부 사전(R31)을 그려진 설정 창과 추측 흐름으로 묻습니다: 설정 절·기본 켬·출처 목록,
gemini 일 때만 보이는 키 입력, 있음(줄·색·`jamo.extraWords`·새로 고친 뒤 조회 없이 받아들임)·없음·오류 토스트, 끄면 요청 0,
느린 조회 중 Enter 를 여러 번 눌러도 요청 하나, 사용자 LLM 더하기(`http://` 거절·`https://` 저장·`.dict-del`),
320px 가로 넘침, `#dict-test` 결과. **외부망은 모두 `page.route` 가짜**(서버 `/api/*`·위키·LLM 모두)이며
진짜 외부망을 부르지 않습니다. 목록에 없는 6칸 낱말은 페이지에서 `ALLOWED` 를 보고 그때그때 고릅니다.

**고쳐짐 (T-318, `Game.allowWord`):** 사전이 '있음' 이면 `ui.js` 가 `g.allowWord(guess)` 로 이미 만들어진 `Game` 의
허용 목록에 낱말을 바로 더합니다. 전에는 `ui.js` 의 `ALLOWED_SET.add()` 가 생성 때 복사된 사본만 고쳐(`game.js:toAllowedSet`)
`submit()` 이 다시 `unknown` 이 되고 같은 낱말을 무한히 되묻는(`…에서 찾았습니다` 토스트가 쌓임) 결함이 있었습니다.
`browser_dict.py` 가 그 흐름(줄이 하나 들어감·칸 색·조회 요청 한 번)을 지킵니다 - 지금은 `통과 75 / 전체 75`.

## 브라우저 검사에 필요한 것

- Python 용 `playwright` 와 그 chromium (`python3 -m playwright install chromium`).
- **이 폴더의 브라우저 검사는 서버를 따로 띄우지 마십시오.** `browser_harness.server()` 가 `serve.py` 의 `Handler` 로 `127.0.0.1` 의
  빈 포트(포트 0)를 잡아 `web/` 을 내보내고 끝나면 닫습니다.
- 시나리오마다 새 브라우저 context 를 써서 localStorage 는 늘 비어 있는 첫 방문에서 시작합니다.
- 오늘의 정답은 숫자로 박지 않고 페이지 안에서
  `answerForDate(new Date(), ANSWERS, TREND)` 로 그때그때 구합니다(`words.js` 의 `TREND` 에 오늘이 들어 있으면 그 낱말이 정답이라 `TREND` 를 꼭 넘깁니다). 자정 무렵에 돌리면 `ui.js` 의 날짜 바꿈
  처리(30초마다·창 포커스 때)가 판을 갈아 끼워 실패할 수 있습니다 - 자정 근처는 피하십시오.

## 스크린숏

`projects/자모맞히기/tests/screenshots/game/<이름>.png` 에 쌓입니다. `browser_harness.shot()` 은 뷰포트만
찍습니다. 스크립트는 같은 이름을 덮어쓸 뿐 폴더를 비우지 않으므로, 시나리오가 `shot()` 전에 죽으면 지난
그림이 남습니다.

| 그림 | 시나리오 |
|---|---|
| `help-first` | 첫 방문 도움말 |
| `win-stats` | 오늘 정답으로 이긴 뒤 통계 창 |
| `share` | 공유 글을 복사한 뒤 |
| `lose` | 여섯 번 틀려 진 뒤 정답 안내 |
| `theme-dark` | 어두운 테마를 켠 화면 |
| `layout-320` | 폭 320 에서 여섯 칸을 친 화면 |

## 목표 → 그것을 증명하는 검사

`PROGRESS.md` 의 목표별. `부분` 은 목표 문장 일부에 그것을 가르는 검사가 없다는 뜻입니다.

| 목표 | 증명하는 파일:함수 | 증명됨/미증명 |
|---|---|---|
| 프로젝트 뼈대 - 정적 서버로 열림 | `browser_game.py` 의 모든 시나리오가 `server()` 로 `index.html` 을 열고 `#board .tile` 이 뜰 때까지 기다림, `scenario_layout` | 증명됨 - 함대 모니터의 '앱 열기' 는 `tests/browser_monitor_app_server.py`(함대 검사)가 임시 루트의 진짜 모니터로 봄 |
| 자모 규칙 - 풀기·조합·겹자음/겹모음/겹받침 | `test_jamo.mjs` (`UNITS`·`SHIFTED`·`KEYMAP`·`toUnits`·`composeUnits`), `browser_game.py:scenario_physical_keys`·`scenario_screen_shift`·`scenario_preview`·`scenario_help`, `browser_modes.py:scenario_preview_fixed`·`scenario_help_table` (미리보기 고정값 `닭`·`갑시`, 도움말 표를 README 규칙 절과 대조) | 증명됨 |
| 판정 로직 - 겹치는 자모 | `test_game.mjs` (`scoreGuess`·`keyboardState`), `browser_game.py:scenario_score` (파이썬 독립 구현과 칸·키 색 대조) | 증명됨 |
| 낱말 목록 - 생성물, 여섯 칸, 출처 | `test_words.py` (모든 낱말 6칸·중복 없음·ANSWERS⊆ALLOWED·다시 만들어도 같음), `data/README.md` | 증명됨 |
| 보드 - 6×6, 입력 중 자모, 조합 미리보기, 제출 색 | `browser_game.py:scenario_preview`·`scenario_score`·`scenario_layout` (모든 시나리오가 6줄×6칸을 전제) | 증명됨 |
| 화면 자판 + 실물 자판(`e.code`) | `browser_game.py:scenario_screen_shift`·`scenario_physical_keys` (`KeyG KeyK KeyS`→ㅎㅏㄴ, `Shift+KeyR`→ㄲ, `Control+KeyA` 무시, 화면 ⇧ 표시·한 번 뒤 꺼짐), `browser_modes.py:scenario_process_key` (한글 입력기 `key:'Process'` + `code:'KeyR'`→ㄱ, Shift→ㄲ) | 증명됨 |
| 없는 낱말·모자란 입력 거절과 안내 | `browser_game.py:scenario_reject` (토스트가 보임, 줄·글자 그대로) | 증명됨 |
| 날마다·연습 모드, 새로 고쳐도 오늘 판 유지 | `browser_game.py:scenario_win` (새로 고침 뒤 끝난 판·줄 그대로) · `scenario_practice` (연습 판 분리, `#btn-new`, 날마다로 돌아오면 치던 칸까지 그대로), `browser_modes.py:scenario_practice_resume` (연습에서 세 칸 치고 날마다를 거쳐 돌아와도 그대로) · `scenario_flip_mode_lock` (뒤집기 중 모드 바꿈 무시) · `scenario_answer_toast` (진 연습 판은 날마다를 거쳐 돌아와도 그 판과 정답 토스트만 남고, `#btn-new` 뒤 사라짐) | 증명됨 |
| 판 끝 - 이김/짐, 정답 공개, 공유 | `browser_game.py:scenario_win`·`scenario_lose` (`정답: <한글 낱말>` 토스트) · `scenario_share` (클립보드 실제 읽기), `browser_modes.py:scenario_future_clock` (시계를 2026-11-12 로 고정해도 날마다 판 공유 첫 줄이 `자모맞히기 1 1/6`, 연습 아님) | 증명됨 |
| 도움말 - 처음 열림, 다시 보기 | `browser_game.py:scenario_help` (겹모음·겹받침 글자와 예시 타일 18개가 보임, 닫힘, `#btn-help` 로 다시) | 증명됨 |
| 폰(320~430px)·데스크톱 - 겹침·넘침 없음 | `browser_game.py:scenario_layout` 320·375·430·1280 (보드·자판·`#modes` 화면 안, 서로 안 겹침, 자판 3줄 키 안 잘림, 여섯 칸 뒤에도 안 넘침) | 증명됨 - 세로로 아주 낮은 창(예: 900×420)은 보지 않음 |
| 어두운 모드 - 시스템 설정 따름 + 단추로 바꿈, 저장됨 | `browser_game.py:scenario_dark` (계산된 body 배경 밝기, 새로 고침 뒤 같은 색·체크박스), `browser_modes.py:scenario_system_dark`·`scenario_system_light` (`color_scheme='dark'`/`'light'` 첫 방문 body 배경 밝기, 어두운 문맥에서 설정을 끄면 새로 고침 뒤에도 밝음) | 증명됨 |
| 접근성 - 키보드만으로 완주, `aria-live` | `browser_game.py:scenario_keyboard_only` (Escape 로 첫 도움말, Tab+Enter 로 다시 열기, Tab 으로 모드 단추, 물리 자판으로 이김, `#toasts[aria-live=polite]` 에 결과 글), `browser_modes.py:scenario_enter_buttons` (모드 단추·`#btn-new` 에 포커스 + Enter 가 그 단추를 누르고 제출로 새지 않음) | 증명됨 |
| 통계 - 판수·승률·연승·최대 연승·분포 | `browser_game.py:scenario_win` (첫 판 `1 100 1 1`, 분포 `1 0 0 0 0 0`, 이긴 줄만 `hl`, 새로 고침 뒤 그대로) | 증명됨(날마다 모드만) - 연습은 통계를 안 남긴다는 것도 `scenario_practice` 가 봄 |
| 검사 - 로직·브라우저 모두 초록 | 이 표의 여섯 명령 | 증명됨 - 로직 107·파이썬 132·화면 121·모드 100·사전 75·트렌드 81 모두 초록 |

## 이 검사가 일부러 보지 않는 것 / 약점

- **시스템 어두운 모드:** 첫 방문에 저장된 설정이 없고 최상위 페이지일 때만 시스템 설정을 따릅니다
  (`browser_modes.py:scenario_system_dark`·`scenario_system_light` 가 봅니다). 모니터 미리보기처럼
  iframe 안에서는 부모의 보관함 설정이 우선입니다.
- **연습 판 보존:** `browser_modes.py:scenario_answer_toast` 가 연습에서 진 판을 날마다로 갔다가
  돌아왔을 때 그 판과 정답 토스트만 남는지, `#btn-new` 뒤에는 사라지는지 봅니다(R24-N5 회귀 방지).
- **시계 고정:** `browser_modes.py:scenario_future_clock` 은 `add_init_script` 로 `Date` 를
  2026-11-12 에 묶어, 기기 시계가 앞서도 공유 첫 줄이 `자모맞히기 연습` 으로 새지 않는지 봅니다.
- **쌍자음 키 색:** 계약상 `button.key[data-key]` 는 **보통 글자**이고 `data-state` 는 그 키에
  **지금 보이는 글자**의 상태입니다. Shift 가 꺼져 있으면 ㄲ·ㅃ 같은 쌍자음은 어느 키에도 보이지
  않으므로, `scenario_score` 의 키 색 대조는 보통 글자 26키만 봅니다. 쌍자음만 든 추측의 키 색은
  화면에 존재하지 않는 것이 정상입니다.
- **작은 대기:** `wait_settled` 는 마지막 `.flip` 이 떨어진 뒤 140ms 만 기다립니다. `ui.js` 의
  `busy` 는 마지막 뒤집기보다 50ms 늦게 풀리므로 그 사이를 메우려는 것이고, 고정 `sleep` 으로
  판정하지는 않습니다.
- **연습 정답 고정:** `scenario_practice` 는 `Math.random = () => 0` 으로 `ANSWERS[0]` 을 정답으로
  만듭니다. 목록의 첫 낱말이 바뀌면 이 시나리오가 보는 정답도 바뀝니다.
- **레이아웃 높이:** 폭 320·375·430 은 폰 높이(640·667·740), 1280 은 900 으로 봅니다. 가로 넘침과
  요소끼리 겹침은 보지만, 아주 낮은 가로 창에서 세로로 잘리는지는 보지 않습니다.
- **죽은 시나리오:** `run_scenario` 는 예외를 `"<이름> - 시나리오 실행"` FAIL 로 남기고 페이지 오류
  검사도 그대로 합니다. 다만 그 뒤 검사는 기록되지 않아 전체 수가 줄어듭니다 - 수를 보십시오.
- **공유:** 첫 줄의 `k/6` 은 2로 고정하려고 틀린 줄 하나 뒤 정답을 넣습니다. 이모지 세 종류가
  모두 나오는 것은 `mixed_wrong` 이 고른 낱말에 달려 있습니다(색이 겹치면 줄 수만 확인).
