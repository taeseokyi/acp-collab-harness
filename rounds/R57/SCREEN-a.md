# SCREEN-a — VoxLog 화면 검수 A (S7, R57)

브리프 T-509-S7-a1-190029. 임시 서버: `VOXLOG_STT=command VOXLOG_STT_CMD="python3 tests/fake_stt.py {wav}" VOXLOG_LLM_CMD="python3 tests/fake_llm.py" python3 serve.py --host 127.0.0.1 --port 18977 --data /tmp/r57-S7-data`(뒤에서 절대경로·다른 가짜 STT 로 재기동한 사유는 D1 과 장면 4 참고). 운영 서버·`projects/VoxLog/data/`·`settings.json` 은 읽지도 쓰지도 않았다. 갈무리는 모두 `/tmp/r57-shots/S7/` 아래.

## 본 장면

1. 첫 화면 → 녹음 → 멈춤 → 올리기·받아쓰기 (1280, 320, 430)
2. 녹음 상세 → 묻기 → 답 보기·복사·공유·지우기 (1280)
3. 파일 올리기 (1280)
4. 지난 글 목록·검색·상세 열고 닫기, 다시 받아쓰기 뒤 '지난 글 N벌' 펼침 (1280)
5. 서버 오류·오프라인 대기열 (430)
6. 320·430px 훑기 (가림·넘침·가로 스크롤·누르기 어려운 단추)

### 장면 1 — 첫 화면 → 녹음 → 멈춤 → 올리기·받아쓰기

- 밟은 걸음: `open http://127.0.0.1:18977/` → `resize 1280 800` → `snapshot` → 녹음 단추 `click` → 3초 뒤 `snapshot`·`screenshot` → 다시 `click`(멈춤) → `snapshot` → 4~6초 뒤 `snapshot`·`eval`(queue-count·rec-result 읽기) → `curl /api/recordings`(서버 상태 대조)
- 본 것:
  - 첫 화면: 녹음 큰 단추·00:00·'아직 녹음이 없습니다.'·'녹음 파일 올리기'. 연결됨 표시 초록. 깔끔.
  - 녹음 중: 단추가 '멈춤' 으로, 상태 '녹음 중…', 시간 00:04 로 갱신 — 정상.
  - 멈춤 직후: 상태 '마지막 녹음 00:08 · 저장됨, 서버로 올리는 중입니다.' — 정상.
  - 그런데 서버 업로드(POST 201)와 받아쓰기(title '가짜 받아쓰기 253518바이트', status done)가 끝나도 이 상태 글이 **그대로 남아 있다**(10초 이상 관찰). 배지('올릴 녹음 N건')는 사라지고 기록 탭 목록은 갱신되지만, 녹음 탭의 상태 글은 새로 고침 전까지 '올리는 중' 인 채로 있다 → **D2**.
  - 콘솔에 favicon.ico 404 오류 하나 → **D5**.
- 갈무리: `/tmp/r57-shots/S7/01-first-1280.png`, `02-recording-1280.png`, `03-uploading-1280.png`, `04-transcribed-1280.png`

### 장면 2 — 녹음 상세 → 묻기 → 답 보기·복사·공유·지우기

- 밟은 걸음: 기록 탭 `click` → 목록 항목 `click`(상세 열기) → 체크박스 `check`(묻기에 쓸 녹취 고르기) → 묻기 탭 `click` → '묻기' `click` → 3~4초 뒤 `snapshot`·`screenshot` → 답의 `복사` `click`(toast 확인) → `eval` 로 `navigator.share` 를 흉내 내어 지난 답 다시 열기 → `공유` `click` → `eval` 로 전달된 title·text 확인 → 지난 답의 `이 답 지우기` `click` → `dialog-accept`(확인창) → `snapshot`
- 본 것:
  - 상세: 받아쓰기 글·복사·다시 받아쓰기·옵션 바꿔 다시 받아쓰기·지우기·이름·태그 편집 모두 보임. 자동 태그 실패 시 '자동 태그를 달지 못했습니다' 표시는 제대로 나옴(D1 의 결과를 정직히 알려 줌).
  - 묻기: 무엇을(요약·핵심어·할 일·직접 묻기)·범위·묻기 단추. 첫 시도는 **실패** — 브리프가 준 상대경로 `VOXLOG_LLM_CMD="python3 tests/fake_llm.py"` 로 서버를 띄우면 날 오류문이 그대로 답 자리에 남는다 → **D1**.
  - 절대경로로 다시 띄운 뒤 같은 걸음: 답 완료. 마크다운(목록·표·인용·코드)이 그려지고 `<img src=x onerror=...>` 은 글자로만 남는 것(XSS 곱빼기) 확인.
  - 복사: '복사했습니다.' 배너. 공유: `navigator.share` 가 없으면 '공유' 단추가 아예 숨는 것 확인(설계대로), 흉내를 넣자 단추가 나오고 누르면 title 'VoxLog 요약 · …' 과 마크다운 원문이 그대로 전달됨.
  - 지우기: 확인창 '이 답을 지울까요? 되돌릴 수 없습니다. (녹취는 그대로 남습니다)' → '지웠습니다.' 배너, 지난 답 목록에서 사라짐.
- 갈무리: `/tmp/r57-shots/S7/05-list-1280.png`, `06-detail-1280.png`, `07-ask-1280.png`, `08-ask-result-1280.png`(실패 화면), `10-ask-success-1280.png`, `11-answer-share-copy-1280.png`, `12-answer-deleted-1280.png`

### 장면 3 — 파일 올리기

- 밟은 걸음: 파이썬 `wave` 로 0.5초짜리 작은 wav 를 `/tmp/r57-upload-a.wav` 에 만듦 → 녹음 탭 → '녹음 파일 올리기' `click` → `upload /tmp/r57-upload-a.wav` → 3~4초 뒤 기록 탭 `snapshot`·`screenshot` + `curl /api/recordings`
- 본 것: 상태 '파일 r57-upload-a.wav · 저장됨, 서버로 올리는 중입니다.' → 목록에 '11/28 19:09 00:01 완료 가짜 받아쓰기 16078바이트' 로 올라옴. 받아쓰기·자동 태그(회의·가짜 태그·세번째, 'AI 가 단 태그' 칩)까지 끝남. 이때도 상태 글은 '올리는 중' 에 머물러 D2 의 소견과 같다.
- 갈무리: `/tmp/r57-shots/S7/13-uploaded-list-1280.png`

### 장면 4 — 지난 글 목록·검색·상세 열고 닫기, 다시 받아쓰기 뒤 '지난 글 N벌'

- 밟은 걸음: 목록에서 항목 `click` → 상세에서 '다시 받아쓰기' `click` → 몇 초 뒤 `find "지난 글"` → 상세가 닫겨 있어 다시 열고 `find` → '지난 글 1벌' 요약 `click` → 안쪽 '받아쓴 때 …' `click` → `screenshot` → '닫기' `click` → 검색창에 '버전' `fill` → `snapshot` → 검색 지우고 첫 녹음 상세 '지우기' `click` → `dialog-accept` → `snapshot`
- 본 것:
  - 검색: '버전' 에 목록이 1건으로 걸러짐. 상태 거르기·날짜 칸도 1280·320 에서 흐트러짐 없음.
  - 상세 열고 닫기 잘 됨. 녹음 지우기: 확인창 '이 녹취(음성과 글)를 지울까요? 되돌릴 수 없습니다.' → '지웠습니다.' 배너, 목록에서 사라지고 상세 닫힘.
  - '지난 글': 처음 '다시 받아쓰기' 를 눌렀을 때 '지난 글' 이 생기지 않았다 — 가짜 STT 가 매번 같은 글을 내놓아(`old != text` 일 때만 지난 글로 남김, store.py:578) 서버에 남을 옛 글이 없었기 때문. `tests/fake_stt.py` 대신 번호를 매겨 다른 글을 내는 가짜 STT(`/tmp/r57-fake-stt-alt.py`)로 임시 서버만 다시 띄워 시험하니 '지난 글 1벌' 이 생겼고, 펼치면 '받아쓴 때 2026-11-28 19:09 · 옵션 기록 없음' 아래 옛 글이 보였다. 제품 동작은 정상.
  - 한 가지 걸음이 어색하다: '다시 받아쓰기' 를 누르면 목록이 다시 읽히면서 상세가 **닫힌다**. 답이 나왔는지 보려면 목록에서 같은 항목을 다시 열어야 한다. 다시 받아쓰기가 '요청됨' 상태(받아쓰는 중)인 동안 상세가 그 항목을 계속 보여 주면 더 자연스러울 일이다(주 걸음은 아니므로 결함으로는 적지 않는다 — 관찰만).
- 갈무리: `/tmp/r57-shots/S7/14-retranscribed-1280.png`, `15-detail-past-1280.png`, `16-past-1-1280.png`, `17-past-open-1280.png`, `18-past-detail-1280.png`, `19-search-1280.png`, `20-after-delete-1280.png`

### 장면 5 — 서버 오류·오프라인 대기열 (430px 에서)

- 밟은 걸음: `eval` 로 `window.fetch` 를 가로채 `/api/recordings` 만 거절로 흉내 → 기록 탭 `click` → `snapshot`·`screenshot` → 녹음 탭에서 3초 녹음 후 멈춤 → `snapshot` → 서버를 `kill`(pid 로)한 뒤 다시 녹음·멈춤 → `snapshot`(대기열 상자) → 서버 재기동 → 대기 상자의 '다시 올리기' `click` → `snapshot` + `curl /api/recordings` + 서버 로그
- 본 것:
  - 서버 오류 흉내: 머리글 표시가 빨간 '연결 안 됨' 으로 바뀌고 '서버에 연결할 수 없습니다' 배너. 목록·상세는 이미 가진 자료를 그대로 보여 준다.
  - 서버를 내린 채 녹음·멈춤: '올리지 못한 녹음' 상자가 생기고 '11/28 19:15 · 29KB / 아직 올리지 못했습니다: 연결 안 됨' 과 내려받기·다시 올리기·지우기 단추가 나옴. 머리글 배지 '올릴 녹음 1건'.
  - 서버 복구 뒤 '다시 올리기': POST 201 로 올라가고 배지·상자가 사라지며 목록에 '가짜 받아쓰기 126798바이트 (버전 3)' 로 받아쓰기까지 끝남. (참고: 자동 재올림은 실패 응답의 Retry-After·브라우저 online/visibilitychange 에 매여 있어, 서버만 내렸다 올린 이 흉내에서는 자동으로 다시 올라가지 않았다 — 실제 오프라인 복귀는 online 이벤트로 걸린다. 페이지가 열려 있는 채 서버만 잠깐 죽은 경우엔 사람이 '다시 올리기' 를 눌러야 한다. 관찰만 적어 둔다.)
  - 서버 로그에 `Request timed out: TimeoutError('timed out')` 이 잠깐씩 찍히는데, CPython `http.server` 가 쉬는 keep-alive 연결에 찍는 기록이라 제품 결함은 아니다(브라우저가 연결을 놓고 있으니 나는 것).
- 갈무리: `/tmp/r57-shots/S7/32-server-error-430.png`, `34-offline-queued-430.png`, `36-retry-upload-430.png`, `37-list-after-flush-430.png`

### 장면 6 — 320·430px 훑기

- 밟은 걸음: `resize 320 700` → 녹음 탭 첫 화면 `screenshot` → 녹음·멈춤 `screenshot` → 기록 목록 `screenshot` → 상세 열고 아래로 `screenshot` → 묻기 탭·답 표(표 147px 로 넘침 없음) `screenshot` → 단추 크기 일괄 실측(`eval` 로 모든 보이는 단추·입력의 getBoundingClientRect) → `resize 430 900` 으로 같은 걸음 반복
- 본 것:
  - 두 폭 모두 가로 스크롤 없음(scrollWidth == clientWidth, 320·430 모두). 머리글·탭·목록·상세·묻기 폼·마크다운 표·오디오 조각까지 겹침·가림 없이 떨어진다. 상세의 '옵션 바꿔 다시 받아쓰기' 폼(전처리·화자 수·문맥 글·자동 중정·LLM 견도)도 좁은 폭에서 잘 줄바뀐다.
  - 누르기 크기: 탭·단추 대부분 44px 높이. 아래 두 가지만 작다 → D3·D4.
- 갈무리: `/tmp/r57-shots/S7/21-first-320.png`, `22-recording-320.png`, `23-list-320.png`, `24-detail-320.png`, `25-detail-bottom-320.png`, `26-ask-320.png`, `27-ask-table-320.png`, `28-first-430.png`, `29-list-430.png`, `30-detail-430.png`, `31-ask-430.png`, `38-stt-options-430.png`, `39-stt-options-form-430.png`

## 결함

### D1 (중) 상대경로 VOXLOG_LLM_CMD 로 서버를 띄우면 묻기·자동태그가 다 실패한다

- 재현 걸음: 브리프와 같은 방식으로 서버 기동(`VOXLOG_LLM_CMD="python3 tests/fake_llm.py"`, 기동 폴더 projects/VoxLog) → 기록에서 녹취 고르기 → 묻기 → '묻기' 단추. 자동 태그도 같은 이유로 '자동 태그를 달지 못했습니다'.
- 기대: 가짜 STT 처럼 상대경로로도 붙는다(stt.py 는 기동 폴더에서 명령을 돌려 잘 된다), 또는 안내가 절대경로를 요구한다.
- 실제: 답 자리에 `python3: can't open file '/tmp/tmpXXXX/tests/fake_llm.py': [Errno 2] No such file or directory` 가 그대로 남고 자동 태그는 '실패'. run_llm 이 명령을 임시 폴더를 작업 폴더로 돌리므로 상대경로가 풀린다. STT 쪽과 LLM 쪽이 작업 폴더를 다루는 방식이 달라 생기는 어긋남. 절대경로(`python3 $PWD/tests/fake_llm.py`)로 띄우면 둘 다 잘 된다.
- 의심 위치: projects/VoxLog/voxlog/ask.py:129(`cwd=workdir`) — 비교: projects/VoxLog/voxlog/stt.py:138~145(작업 폴더를 바꾸지 않음)
- 갈무리: /tmp/r57-shots/S7/08-ask-result-1280.png

### D2 (중) 올리기·받아쓰기가 끝나도 녹음 탭 상태 글이 '올리는 중' 인 채로 남는다

- 재현 걸음: 녹음 → 멈춤 → 서버 업로드·받아쓰기가 다 끝날 때까지 기다림(서버 로그에 POST 201·status done 확인) → 녹음 탭 상태 글 관찰.
- 기대: 끝나면 '저장됨' 이니까 '서버로 올리는 중입니다' 는 치워진다(예: '마지막 녹음 00:08 · 올렸습니다').
- 실제: '마지막 녹음 00:08 · 저장됨, 서버로 올리는 중입니다.' 가 새로 고침 전까지 계속 남아 있다. 파일 올리기(장면 3)도 같다. 기다리는 사람은 받아쓰기가 끝났는지 알 수 없어 다시 누르거나 기록 탭을 열어 확인하게 된다.
- 의심 위치: projects/VoxLog/web/app.js:924(글을 세우는 곳, 끝낸 뒤 바꾸는 곳이 없음 — app.js:577 updateQueue 는 배지·목록만 갱신)
- 갈무리: /tmp/r57-shots/S7/04-transcribed-1280.png(20초가 지나도 같은 문구), /tmp/r57-shots/S7/13-uploaded-list-1280.png

### D3 (하) '묻기에 쓸 녹취 고르기' 체크박스가 작아 좁은 폭에서 누르기 어렵다

- 재현 걸음: 320px(430 에서도 같음)로 기록 탭 → 목록 항목의 체크박스 실측.
- 기대: 누르는 크기 44px 안팎.
- 실제: 22×22px(핵 체크박스 자체). 항목 줄과 겹치지 않은 왼쪽 자리라 오누르기 쉽다.
- 의심 위치: projects/VoxLog/web/index.html(목록 체크박스)·projects/VoxLog/web/style.css(크기)
- 갈무리: /tmp/r57-shots/S7/23-list-320.png

### D4 (하) '+1' 태그 칩이 44px 보다 좁다

- 재현 걸음: 목록·상세에서 숨은 태그가 있는 항목의 '+1' 칩 실측(320·430).
- 기대: 누르는 크기 44px 안팎.
- 실제: 38×44px(폭이 모자라다). 높이는 충분하나 폭이 좁아 옆 칩과 오누를 수 있다.
- 의심 위치: projects/VoxLog/web/style.css(태그 칩 최소 폭)
- 갈무리: /tmp/r57-shots/S7/23-list-320.png, /tmp/r57-shots/S7/30-detail-430.png

### D5 (하) favicon.ico 가 없어 콘솔에 404 오류가 하나 찍힌다

- 재현 걸음: 페이지를 열면 콘솔에 `Failed to load resource: 404 @ /favicon.ico`.
- 기대: 404 가 없거나 아이콘이 응답한다.
- 실제: 404. 아이콘 파일은 `/icons/` 아래에 있는데 favicon.ico 만 없다.
- 의심 위치: projects/VoxLog/serve.py(기본 favicon 응답) 또는 web/ 아래 favicon.ico 추가
- 갈무리: (콘솔 로그 — /tmp/playwright-cli/console-2026-11-28T10-03-30-964Z.log)

## playwright-cli 를 쓰다 막힌 것

- 첫 서버 기동을 `( ... & )` 로 했다가 하네스가 백그라운드 프로세스를 기다려 명령이 끝나지 않았다. `setsid env ... &` 로 띄우는 것이 안전했다(첫 서버는 하네스가 정리하며 죽어 한 번 다시 띄웠다).
- `eval` 에 문장을 여러 개 나열하면 `SyntaxError: Unexpected token ';'` 로 거절된다 — `() => { ...; return ...; }` 꼴의 식으로 감싸야 한다.
- 페이지 fetch 가로채기는 서비스 근로자(sw.js)가 올리는 건 막지 못했다(업로드는 계속 성공). 오프라인 대기열 시험은 서버를 pid 로 끄는 쪽으로 했다.
- 복사한 글 확인은 이 화면에서 클립보드 읽기 권한이 막혀(`NotAllowedError`) 배너('복사했습니다.')로만 확인했다.
