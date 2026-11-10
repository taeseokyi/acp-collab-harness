# 웹워들 테스트

명령은 모두 **저장소 루트**(`projects/` 가 보이는 곳)에서 돌립니다.

## 다섯 벌과 돌리는 명령

| 무엇 | 파일 | 명령 | 초록이면 |
|---|---|---|---|
| 로직 | `test_game.mjs` · `smoke_integration.mjs` | `node --test projects/웹워들/tests/*.mjs` | `ℹ fail 0` |
| 단어 목록 | `test_words.py` | `python3 -m unittest discover -s projects/웹워들/tests` | `OK` |
| 브라우저 - 핵심 한 판 | `browser_core.py` | `python3 projects/웹워들/tests/browser_core.py` | rc 0, `통과 67 / 전체 67` |
| 브라우저 - 레이아웃 | `browser_layout.py` | `python3 projects/웹워들/tests/browser_layout.py` | rc 0, `통과 18 / 전체 18` |
| 브라우저 - 통계·공유·설정·접근성·도움말 | `browser_ui.py` | `python3 projects/웹워들/tests/browser_ui.py` | rc 0, `통과 155 / 전체 155` |

2026-11-11 (T-125) 에 다섯 벌 모두 초록이었습니다: core 67/67 (두 번 돌려 두 번 다), layout 18/18, ui 155/155,
모두 rc 0. 로직 `ℹ pass 25`·`fail 0`, 단어 목록 `Ran 6 tests`·`OK`.

검사 수는 시나리오가 중간에 죽으면 줄어듭니다(남은 검사가 기록되지 않음). **수가 위와 다르면 rc 0 이어도
의심하십시오.** `browser_ui.py` 의 155 가운데 52 는 대비 측정이고, 서로 다른 글자색·배경색 쌍은 13 개뿐입니다
(아래 '알고 쓸 약점').

- `node --test` 에는 **파일**을 주십시오. `node --test projects/웹워들/tests/` 처럼 폴더를 주면
  폴더 자체를 테스트 파일로 읽으려다 실패합니다
- 브라우저 스크립트는 맨 끝에 `통과 n / 전체 m` 을 찍고, **rc 는 실패한 검사 수**입니다.
  `browser_core.py` · `browser_ui.py` 는 브라우저를 못 띄우면 rc 2 를 냅니다.
  `browser_layout.py` 는 그런 처리가 없어 예외가 나면 traceback 과 rc 1 로 끝나고 요약 줄이 없습니다

## 브라우저 검증에 필요한 것

- Python 용 `playwright` 와 그 chromium (`python3 -m playwright install chromium` 으로 받는 것).
  이 둘이 없으면 브라우저 스크립트 셋은 돌지 않습니다
- **서버는 띄우지 마십시오.** `browser_harness.server()` 가 `serve.py` 의 `Handler` 로
  `127.0.0.1` 의 빈 포트(포트 0)를 잡아 `web/` 을 내보내고, 끝나면 닫습니다. 포트가 겹칠 일이 없습니다
- 시나리오마다 새 브라우저 context 를 쓰므로 localStorage 는 늘 비어서 시작합니다 (첫 방문 상태)
- 오늘의 정답은 숫자로 박혀 있지 않고, 페이지 안에서 `game.js` 의 `answerForDate(new Date(), ANSWERS)` 로
  그때그때 구합니다. 자정 무렵에 돌리면 `ui.js` 의 날짜 바뀜 처리(30초마다·창 포커스 때)가
  판을 갈아 끼워 실패할 수 있습니다 - 자정 근처는 피하십시오

## 스크린샷

- `projects/웹워들/tests/screenshots/<묶음>/<이름>.png` 에 쌓입니다. 묶음은 `core` · `layout` · `ui`
- `browser_harness.shot(page, name)` 은 **뷰포트(창에 보이는 만큼)** 만 찍습니다. 사람이 첫 화면에서 보는
  그대로입니다. 쪽 전체(스크롤해야 보이는 아래까지)가 필요하면 `shot(page, name, full_page=True)` 로 부르십시오.
  지금은 어느 스크립트도 `full_page=True` 를 쓰지 않으므로, 모든 그림이 뷰포트 그림입니다
- 루트 `.gitignore` 가 `projects/웹워들/tests/screenshots/` 를 빼므로 **커밋되지 않습니다**
- 스크립트는 같은 이름을 **덮어쓸 뿐 폴더를 비우지 않습니다.** 시나리오가 `shot()` 전에 죽으면
  지난번 그림이 그대로 남아 새것처럼 보입니다. 파일 시각(`ls -l`)을 보고 판단하십시오.
  `core/` 에 있는 `narrow*.png` · `short*.png` 는 지금 어느 스크립트도 그 폴더에 쓰지 않는 옛 그림입니다

| 묶음 | 파일 |
|---|---|
| core | `invalid-word` `win` `win-stats` `lose` |
| layout | `narrow` `narrow-modal` `short` `short-modal` |
| ui | `help-first` `stats-after-win` `restored` `stats-mixed` `stats-nth-line` `stats-after-loss` `stats-reload-finished` `share` `theme-dark` `theme-colorblind` `theme-light` `theme-colorblind-present` |

`browser_core.py` 의 화면 키·키 색 유지 시나리오와 `browser_ui.py` 의 접근성 두 시나리오는 그림을 남기지 않습니다.

## 목표 → 그것을 증명하는 검사

`부분` 은 목표 문장 일부에 그것을 가르는 검사가 없다는 뜻이고, 셀 때는 미증명으로 칩니다.

| 목표 | 증명하는 파일:함수 | 증명됨/미증명 |
|---|---|---|
| 보드 - 6×5, 입력 중 글자 보임, 제출 시 뒤집기 | `browser_core.py:scenario_board` (줄·칸 수, filled+대문자, 지우기, 판정 색을 파이썬 독립 구현과 대조, `MutationObserver` 로 `.flip` 이 붙는 순간의 시각을 기록해 다섯 칸·왼쪽부터·끝나면 떨어짐 확인, **Enter 전에 건** `animationstart` 리스너의 기록을 `name == 'flip'` 으로 거른 뒤, 칸마다 가장 이른 것 하나를 골라 정확히 다섯 칸(0~4)이고 그 순간 `getAnimations()` 에 `flip` 이 running 인지 확인). 입력 중 글자가 실제로 보이는지는 `browser_ui.py:scenario_accessibility_contrast` 의 "입력 중 칸" 대비가 받침 | 증명됨 (T-125) - `pop` 을 이름으로 버렸지만 다섯 칸·running 조건은 그대로이고, 세 검사 모두 `len(flip_starts) == 5` 를 요구하므로 기록 0개로 통과하는 길은 없습니다. 쪽 안에서 `@keyframes flip` 을 `deleteRule` 로 지우자(1개 지워짐) `animationstart` 세 검사가 `flip 기록=[]` 로 빨개짐을 다시 확인(보드만 13/16, rc 3). 단 다른 다섯 칸 검사들(class 붙음, 선언, 순서, 떨어짐)은 그때도 초록이므로 **뒤집기 애니메이션이 실제로 돈다는 증명은 `animationstart` 세 검사가 혼자 집니다.** 왼쪽부터 차례인지는 `animationstart` 시각이 아니라 `MutationObserver` 의 class 시각으로만 봅니다 |
| 키보드 - 화면 키 + 물리 Enter/Backspace, 색 누적 | `browser_core.py:scenario_keyboard` (화면 `q` 클릭, 물리 입력·Backspace·Enter, 키 색 = 타일 판정, present → correct) · `scenario_screen_keys` (화면 ENTER·⌫ 가 보이고 크기가 있음, 화면 키만으로 다섯 칸 → ⌫ → ENTER 클릭 제출, 다섯 글자 미만 ENTER 는 안내만) · `scenario_keyboard_correct_kept` (correct 키가 다음 줄 present/absent 뒤에도 correct) | 증명됨 |
| 없는 단어 거절 - 흔들림 + 안내 | `browser_core.py:scenario_invalid` (`.shake`, 토스트 `사전에 없는 단어입니다`, 글자 유지) | 증명됨 - 두 번째(5글자 미만) 흔들림 검사는 첫 흔들림의 남은 class 로도 통과할 수 있음 |
| 판 끝 - 승리/패배 표시, 정답 공개 | `browser_core.py:scenario_win` · `scenario_lose` (모두 correct+bounce+칭찬, 여섯 줄 판정+`정답: XXXXX` 토스트, 통계 창 지연 열림, 끝난 뒤 입력 무시) | 증명됨 - 지연 시간 검사는 하한만 느슨하게 봄. 칭찬 토스트는 여섯 문구 중 아무것이나 통과 (몇 번째 줄에 맞혔는지에 맞는 문구인지는 안 봄) |
| 통계 - 판수·승률·연승·최대 연승·분포, 새로 고쳐도 판 유지 | `browser_ui.py:scenario_stats` (빈 값 0, 첫 판 `1 100 1 1`) · `scenario_restore` (진행 중 판 새로 고침 뒤 보드·키 색 같음) · `scenario_stats_mixed` (localStorage 에 `7/5/2/4` 를 심어 네 값이 서로 다른 `7 71 2 4`, 이름표 순서 `판수`·`승률`·`연승`·`최대` → 이긴 뒤 `8 75 3 4`, 분포 첫 칸 증가) · `scenario_stats_nth_line` (`3/2/1/2` 와 빈 분포를 심고 틀린 단어 셋 뒤 4번째 줄에서 이김 → 분포 `0 0 0 1 0 0`, `4 75 2 2`, `hl` 이 정확히 한 줄이고 그것이 4번째) · `scenario_stats_after_loss` (진 뒤 `8 63 0 4`, 분포 그대로) · `scenario_stats_reload_finished` (끝난 판 새로 고침 뒤 `8 75 3 4` 그대로, 보드·키 색·공유 단추 그대로) | 증명됨 - 4번째 줄 승리는 줄마다 `wait_submit_settled` 로 그 줄이 판정될 때까지 기다리므로 `busy` 로 글자가 버려지면 시간 초과로 시나리오가 죽어 수가 줄어듭니다(조용히 다른 줄에서 이기는 길 없음). 기대값은 셈과 맞습니다(3+1=4, 3/4=75%, 연승 1+1=2, 최대 max(2,2)=2). 이름표는 부분 문자열 비교라 `연승`↔`최대 연승` 이 바뀌면 4번째 칸에서만 잡힙니다(그래도 잡힘) |
| 결과 공유 - 이모지 격자 복사 | `browser_ui.py:scenario_share` (클립보드 실제 읽기, 첫 줄 `웹워들 <번호> 1/6`, 🟩 다섯) | 증명됨 - 브라우저에서는 1/6 전부 초록만. 🟨⬛·`X/6` 은 `test_game.mjs` 의 `shareText` 가 봄 |
| 보기 설정 - 어두운 테마, 색약(초록/노랑 → 주황/파랑), 저장 | `browser_ui.py:scenario_settings` (`data-theme`, body 계산 배경이 실제로 더 어두움, 색약 correct 계산 배경이 일반과 다르고 `r>g>b` 이며 hue 0~40도, 새로 고친 뒤 속성·체크박스 유지와 **칠해진 body 배경색이 새로 고침 전(어두움)과 같음**) · `scenario_settings_colorblind_present` (색약 present 계산 배경이 `b>g>r` 이고 hue 190~250도, correct 가 `r>g>b` 이고 hue 0~40도, 새로 고친 뒤 칠해진 배경색이 같음) | 증명됨 - hue 범위는 실제 색(`#f5793a` 20.2도, `#85c0f9` 209.5도)을 통과시키고 노랑(`#c9b458` 48.8도, `#b59f3b` 49.2도)과 초록(`#6aaa64` 114.9도)을 떨어뜨립니다 (`rgb_hue` 를 불러 계산). 새로 고침 비교의 "전" 값은 어두운 테마에서 잰 것(`rgb(18, 18, 19)`)이고 바로 앞 검사가 밝음보다 어둡다고 확인하므로, 저장이 깨져 흰색으로 돌아오면 빨개집니다. 색약 present 의 파랑 판정은 밝은 테마에서만 합니다(어두움+색약은 대비 검사가 같은 `rgb(133, 192, 249)` 을 찍을 뿐 단언하지 않음) |
| 접근성 - 키보드만으로 완주, `aria-live`, 대비 4.5:1 | `browser_ui.py:scenario_accessibility` (Tab 포커스, 포커스된 키에서 Enter 가 글자 입력, Tab+Enter 로 화면 글자 키·화면 ENTER 만으로 한 줄 제출, 물리 키보드로 이김, 판정 타일 aria-label, `#toasts` aria-live 에 칭찬이 들어감, 판정 타일 대비 네 모드) · `scenario_stats_after_loss` (진 판 `정답: XXXXX` 가 `#toasts[aria-live=polite]` 안에 들어감 - `#toasts` 는 `#app` 밖이라 통계 창의 `inert` 에 안 걸림) · `scenario_accessibility_contrast` (밝음·어두움·색약·어두움+색약 네 모드에서 머리글 제목, 판정 없는 키, correct/present/absent 키, ENTER·⌫, 입력 중 칸, 토스트, 통계 설명 글 - 배경은 불투명한 조상까지 올라가 구함) | 증명됨 - 단 도움말·설정 창 본문, 공유 단추(`.primary`, 어두움에서 4.71:1 로 문턱 근처), 창 닫기 ✕, 분포 막대 대비는 검사가 없음 (지금 값은 모두 4.5 이상인 것을 손으로 쟀음). 화면 키만으로 친 줄은 판정이 끝났는지만 보고 글자가 친 단어와 같은지는 안 봄 |
| 도움말 - 처음 열면 안내, 다시 볼 수 있음 | `browser_ui.py:scenario_help` (첫 방문에 열림, 열린 동안 입력 막힘, 새로 고치면 안 열림, `#btn-help` 로 다시 열림) | 증명됨 - "설명 글" 검사는 글이 한 글자라도 있으면 통과 |

`browser_layout.py` 는 아홉 목표 어느 것에도 직접 걸리지 않는 보조 검사입니다 (좁은 폭 360×640,
낮은 창 900×420 에서 가로 넘침·보드/키보드 가로 범위·키 높이·통계 창 아래 끝). 모든 줄이 같은 이름
`접근성/레이아웃` 으로 찍히므로 무엇이 깨졌는지는 `[narrow]`/`[short]` 뒤의 내용으로 구분합니다.

## 알고 쓸 약점

- **시간:** `sleep` 을 쓰는 곳은 없습니다. 기다림은 모두 `wait_for_function`·`wait_for_selector` (대개 3~5초,
  진 판 정답 토스트는 15초). `scenario_stats_nth_line` 은 줄 사이마다 `wait_input_ready` 로 `busy` 가 풀린 것을
  실제로 글자 하나 쳐 보고 확인합니다. 뒤집기 순서는 `MutationObserver` 가 남긴 시각으로 판정하므로, 정해진 시간 창
  안에 읽어야 통과하는 검사는 없습니다
- **뒤집기 `animationstart` 검사의 남은 헐거움:** 기록을 `flip` 으로 거른 뒤 칸마다 가장 이른 것 하나만
  남기므로, 한 칸에서 `flip` 이 두 번 시작해도(되풀이 재생) 잡지 못합니다 - 이름대로 "다섯 **칸** 분" 입니다.
  "animationstart가 … flip로 시작됨" 의 `all(item["name"] == "flip" ...)` 부분은 이미 걸렀으니 늘 참이고,
  "정확히 다섯 칸 분" 검사는 앞 두 검사의 칸 조건을 되풀이합니다 - `flip` 이 안 돌면 같은 원인으로 셋이
  한꺼번에 빨개집니다(실제 결함은 하나)
- **옛 이름만 보던 검사는 이름이 바뀌었습니다:** 지금 이름은 "`.flip` 에 animation 선언이 걸려 있음(이름·시간)"
  이고, 계산된 `animationName`·`animationDuration` 만 본다는 것을 이름이 그대로 말합니다. `@keyframes flip`
  을 지워도 초록인 것은 여전합니다(T-125 에서 다시 확인). 애니메이션이 돈다는 증명으로 읽지 마십시오
- **`flip` 이 `pop` 을 끊으면 `pop` 이 다시 돕니다 (제품 쪽, 사람 손에선 거의 안 남):** `ui.js` 는
  `animationend` 때만 `pop` 을 떼는데, `flip` 이 덮으면 `pop` 은 끝나지 않고 취소되어 class 가 남습니다.
  `flip` 이 떨어지는 순간 그 칸이 한 번 더 커졌다 돌아옵니다. 마지막 글자를 친 뒤 100ms 안에 Enter 를 눌러야
  생기므로 테스트에서만 보입니다. 이 폴더의 쓰기 범위가 아니라 고치지 않았습니다
- **중간 `return`:** `browser_core.py` 2곳·`browser_ui.py` 9곳의 이른 `return` 은 모두 바로 앞에 `False`
  검사를 남기고 나갑니다(조용한 통과 없음). 다만 그 뒤 검사가 기록되지 않아 수가 줄어듭니다 - 수를 보십시오.
  `try/except` 는 시나리오 전체를 감싸 "시나리오 실행" FAIL 로 남기는 것과 context 닫기뿐입니다
- **대비 검사 수는 부풀어 있습니다:** 대비 측정 52 개가 재는 글자색·배경색 쌍은 13 개입니다.
  `scenario_accessibility` 의 판정 타일 12 개는 `scenario_accessibility_contrast` 의 판정 키 12 개와 같은
  CSS 변수라 숫자가 똑같고, 판정 없는 키·ENTER·⌫ 는 한 쌍, 머리글 제목·입력 중 칸은 한 쌍, 토스트는 그
  쌍을 뒤집은 것입니다. 색약은 correct·present 만 바꾸므로 색약 모드의 나머지 여덟 줄은 밝음·어두움의 되풀이입니다
- **대비 배경 구하기:** `effective_colors` 는 알파가 0 보다 큰 첫 조상의 배경을 쓰는데, 그 배경이 반투명이면
  (`.modal` 의 `rgba(0, 0, 0, .5)` 같은) 알파를 버리고 불투명한 것으로 계산합니다. 요소의 `opacity` 도 보지
  않습니다. 지금 재는 곳은 모두 불투명한 배경에 닿아 숫자가 맞지만, 새 요소를 더할 때 조심하십시오
- **색 계열 판정:** 노랑이 주황으로 통과하던 구멍은 hue 검사로 막혔습니다. 남은 것: 주황 범위 0~40도는
  빨강(`#ff0000` = 0도)도 받습니다. `rgb_hue` 는 회색(최대=최소)에 0도를 돌려주므로 hue 검사만으로는 회색도
  "주황" 입니다. 같이 붙은 `r>g>b` 검사가 둘 다 막고 있으니 그 검사를 지우지 마십시오
- **이름표 비교는 부분 문자열입니다:** `scenario_stats_mixed` 는 `연승` 이 `최대 연승` 안에도 들어 있어,
  3번째 칸 하나만 보면 둘이 바뀐 것을 못 가립니다. 4번째 칸의 `최대` 가 잡아 줍니다
- **날짜:** `browser_ui.py` 의 통계 심기(`SEED_JS`)는 브라우저 시각으로 어제 날짜를 `lastDay` 로 넣어 연승이
  이어지게 합니다. 자정을 넘기며 돌면 연승이 끊겨 `8 75 3 4` 등이 깨집니다
- **흔들림 두 번째 검사:** `scenario_invalid` 의 5글자 미만 거절은 `.shake` 를 기다리는데, 첫 거절의
  `shake` 는 `ui.js` 가 600ms 뒤에야 뗍니다. 그 안에 지나가면 첫 흔들림으로도 통과합니다
- **느슨한 하한:** 통계 창 자동 열림 지연은 `>= 2.0초`(이김, 입력 전부터 잼) · `>= 1.5초`(짐) 만 봅니다.
  재는 구간에 뒤집기(~1초)가 들어 있어 실제 지연이 1초·0.5초로 줄어도 통과합니다
- **레이아웃:** 보드와 키보드가 세로로 겹치는지, 보드가 세로로 잘리는지, 통계 창 위 끝은 보지 않습니다.
  타일 너비 하한이 8px 이라 900×420 에서 실제로 나온 약 20px 타일(보드 너비 117px)도 그냥 통과합니다.
  콘솔 오류도 모으지 않습니다
- **스크립트끼리 복사된 상수:** 칭찬 문구 여섯 개, 토스트 문구, 화면 키 28개, 이름표(`판수`·`승률`·`연승`·`최대`),
  색약 hue 범위(주황 0~40도·파랑 190~250도), 판정말(`맞음`·`자리 틀림`·`없음`)이 `ui.js`·`style.css` 와 따로 적혀 있어 바꾸면 테스트도 같이 바꿔야 합니다.
  `browser_core.py` 와 `browser_ui.py` 는 `wrong_words`·`row_snapshot` 같은 도우미를 각자 복사해 갖고 있습니다
  (`wrong_words` 의 `count` 인자는 무시되고 늘 여섯 개를 돌려줍니다)
