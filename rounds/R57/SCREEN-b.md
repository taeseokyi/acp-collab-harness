# R57 VoxLog 화면 검수 B (S8)

대상: `projects/VoxLog` 임시 서버. 운영 서버·운영 `data/`·`settings.json` 은 건드리지 않았다.
가짜 마이크와 `tests/fake_stt.py`·`tests/fake_llm.py` 로 녹음·받아쓰기·묻기를 돌렸다.

공통 준비(모든 장면):

```bash
cd projects/VoxLog
VOXLOG_STT=command \
VOXLOG_STT_CMD="python3 /home/tsyi/work/ai-fleet/projects/VoxLog/tests/fake_stt.py {wav}" \
VOXLOG_LLM_CMD="python3 /home/tsyi/work/ai-fleet/projects/VoxLog/tests/fake_llm.py" \
python3 serve.py --host 127.0.0.1 --port 18978 --data /tmp/r57-S8-data
```

- 화면: `playwright-cli open http://127.0.0.1:18978/`
- 서버 확인: `curl -s http://127.0.0.1:18978/api/health` → `{"ok": true, "auth": false, "stt": "command", "llm": true, "version": "0.1"}`
- 갈무리: 모두 `/tmp/r57-shots/S8/`
- `VOXLOG_LLM_CMD` 는 절대 경로여야 한다. 묻기는 임시 cwd 에서 명령을 돌려 상대 경로 `python3 tests/fake_llm.py` 가 `No such file or directory` 로 실패했다(서버 첫 기동 때). 절대 경로로 다시 띄운 뒤 정상이었다.
- 15초 제한을 빨리 보려고 `page.addInitScript(() => { window.__VOX_STT_TIMEOUT_MS__ = 1000; })` 를 넣었다. 운영 기본값은 15초 그대로다.

## 본 장면 목록

1. 설정(⚙) 열기·기본값 채움·값 바꿔 저장·닫고 다시 열기 (1280×800)
2. 설정 읽기/저장 응답 없음 - 1000ms 제한과 칸 풀림 (1280×800)
3. 설정 503 - 읽기 실패와 저장 실패, 다시 시도 (1280×800)
4. 목록 503 - 빈 목록과 이미 있던 목록, 연결 표시와 재시도 (1280×800)
5. 올리기 503 - 대기열·'올리지 못한 녹음'·다시 올리기 (1280×800)
6. 다시 받아쓰기 503 - 토스트와 재시도 성공 (1280×800, 430×900)
7. 묻기 503 - 토스트와 재시도 성공 (1280×800)
8. 목록 응답 없음 - 1초/9초에 무엇이 도는지 (1280×800)
9. 묻기 응답 없음 - 1초/11초에 무엇이 도는지 (1280×800)
10. 오프라인 녹음 - 대기열 표시와 재연결 뒤 업로드 (1280×800)
11. 320×700 - 설정·긴 503 토스트·오프라인 대기열
12. 430×900 - 설정·긴 503 토스트·상세와 재시도

### 장면 1 설정 열기·기본값·저장·다시 열기 (1280)

(1) 밟은 걸음

```text
playwright-cli open http://127.0.0.1:18978/
playwright-cli resize 1280 800
playwright-cli click "#settings-btn"
sleep 1 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/01-settings-open-1280.png
playwright-cli eval "JSON.stringify({hidden:..., vals:{...}, disabled:[...]})"
playwright-cli select "#stt-defaults-preprocess" denoise
playwright-cli fill "#stt-defaults-speakers" 2
playwright-cli fill "#stt-defaults-context" "회의 참석자: 김, 이"
playwright-cli select "#stt-defaults-auto" 1
playwright-cli select "#stt-defaults-review" 0
playwright-cli screenshot --filename=/tmp/r57-shots/S8/02-settings-changed-1280.png
playwright-cli click "#stt-defaults-save"
sleep 0.6 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/03-settings-saved-1280.png
# 설정을 닫았다 다시 열기
playwright-cli click "#settings-btn" && sleep 0.3 && playwright-cli click "#settings-btn"
sleep 0.8 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/04-settings-reopen-1280.png
curl -s http://127.0.0.1:18978/api/stt-options
```

(2) 본 것

- 처음 열면 전처리·화자 수·문맥 글·자동 추정·LLM 검토가 모두 빈 값(서버 기본)이고, `불러오는 중…` 이 잠깐 보인 뒤 채워졌다. 잠금은 정상으로 풀렸다.
- 값을 바꾸고 저장하면 토스트 `받아쓰기 기본값을 저장했습니다.` 가 뜨고, 칸과 저장 단추의 `disabled` 가 모두 `false` 로 돌아왔다.
- 닫았다 다시 열어도 `denoise`, `2`, `회의 참석자: 김, 이`, 자동 추정 `1`, LLM 검토 `0` 이 그대로였다. 서버도 같은 `options` 를 돌려줬다.
- 1280 에서 칸·단추가 겹치거나 넘치지 않았다.

(3) 갈무리

- `/tmp/r57-shots/S8/01-settings-open-1280.png` (처음 열기, 빈 값)
- `/tmp/r57-shots/S8/02-settings-changed-1280.png` (값 바꾼 뒤)
- `/tmp/r57-shots/S8/03-settings-saved-1280.png` (저장 토스트)
- `/tmp/r57-shots/S8/04-settings-reopen-1280.png` (다시 열어 값 유지)

### 장면 2 설정 읽기/저장 응답 없음 - 1000ms 제한 (1280)

(1) 밟은 걸음

```text
playwright-cli run-code "async page => { await page.addInitScript(() => { window.__VOX_STT_TIMEOUT_MS__ = 1000; }); }"
playwright-cli reload
# GET /api/stt-options 만 영원히 안 끝나는 Promise 로 바꿈
playwright-cli eval "(() => { window.__origFetch = window.fetch; window.fetch = function(u,o){ ... if (/\\/api\\/stt-options$/.test(url) && m === 'GET') return new Promise(function(){}); ... }; return 'patched'; })()"
playwright-cli click "#settings-btn"
sleep 1.5 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/05-settings-get-hang-1000ms-1280.png
playwright-cli eval "JSON.stringify({note:..., fieldsHidden:..., saveHidden:..., disabled:[...]})"
# PUT /api/stt-options 만 영원히 안 끝나는 Promise 로 바꿈
playwright-cli fill "#stt-defaults-context" "저장 응답 없음 시험"
playwright-cli run-code "async page => { await page.click('#stt-defaults-save'); await page.waitForTimeout(300); ... screenshot ... }"
sleep 1.2 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/08-settings-reopen-after-put-timeout-1280.png
```

(2) 본 것

- 읽기 응답 없음: 1.0초가 지나자 `받아쓰기 옵션을 불러오지 못했습니다: 시간이 지났습니다` 가 남고, 칸 영역과 저장 단추가 숨겨졌다. 칸은 잠긴 채 남지 않았다.
- 저장 중(응답 없음) 300ms 시점: 상태 글이 `저장 중…`, 칸·저장 단추 모두 `disabled=true`.
- 같은 저장 1.2초 뒤: 상태 글이 비고 칸·저장 단추가 모두 `disabled=false`, 토스트 `받아쓰기 기본값을 저장하지 못했습니다: 시간이 지났습니다`.
- 저장이 시간 초과로 끝난 뒤 설정을 닫았다 다시 열면 새 GET 이 나가고, 서버에 남아 있던 이전 값(`denoise`, `2`, `회의 참석자: 김, 이`)이 다시 채워졌다. 응답 없는 PUT 이 값을 반쯤 덮지 않았다.

(3) 갈무리

- `/tmp/r57-shots/S8/05-settings-get-hang-1000ms-1280.png`
- `/tmp/r57-shots/S8/06-settings-put-hang-during-1280.png` (저장 중 잠금)
- `/tmp/r57-shots/S8/08-settings-reopen-after-put-timeout-1280.png` (시간 초과 뒤 다시 열기)

### 장면 3 설정 503 - 읽기 실패·저장 실패 (1280)

(1) 밟은 걸음

```text
playwright-cli route "**/api/stt-options" --status=503 --body='{"error":"받아쓰기 옵션을 저장할 수 없습니다 (503)"}' --content-type=application/json
playwright-cli click "#settings-btn"
sleep 1 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/11-settings-get-503-1280.png
playwright-cli unroute "**/api/stt-options"
# 다시 열어 정상으로 채운 뒤, PUT 만 503 으로 바꿈
playwright-cli eval "(() => { window.fetch = ...; if (/\\/api\\/stt-options$/.test(url) && m === 'PUT') return Promise.resolve(new Response(...503...)); ...; })()"
playwright-cli fill "#stt-defaults-context" "503 저장 시험"
playwright-cli click "#stt-defaults-save"
sleep 0.4 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/10-settings-save-503-1280.png
```

(2) 본 것

- 읽기 503: `받아쓰기 옵션을 불러오지 못했습니다: 받아쓰기 옵션을 저장할 수 없습니다 (503)`(응답 본문의 error) 가 남고 칸·저장 단추가 숨겨졌다. 다시 시도 단추는 없고, 설정을 닫았다 열면 새 GET 으로 다시 시도된다.
- 저장 503: 토스트 `받아쓰기 기본값을 저장하지 못했습니다 (503)`, 칸·저장 단추는 모두 풀려 있고 입력한 값도 남아 있었다. 저장 단추를 다시 누를 수 있었고, 503 을 풀고 다시 누르면 정상 저장됐다(장면 11 의 320 저장 성공 토스트).
- 두 경우 모두 헤더는 초록 `연결됨` 그대로였다.

(3) 갈무리

- `/tmp/r57-shots/S8/11-settings-get-503-1280.png`
- `/tmp/r57-shots/S8/10-settings-save-503-1280.png`

### 장면 4 목록 503 - 빈 목록과 기존 목록 (1280)

(1) 밟은 걸음

```text
playwright-cli click "#tabbtn-list" && sleep 0.8
playwright-cli screenshot --filename=/tmp/r57-shots/S8/13-list-normal-1280.png
playwright-cli route "**/api/recordings?*" --status=503 --body='{"error":"목록을 불러오지 못했습니다 (503)"}' --content-type=application/json
playwright-cli click "#tabbtn-list" && sleep 0.6
playwright-cli screenshot --filename=/tmp/r57-shots/S8/14-list-503-with-existing-1280.png
playwright-cli eval "JSON.stringify({conn:..., toast:..., items:..., listText:...})"
playwright-cli unroute "**/api/recordings?*"
playwright-cli click "#tabbtn-list"
```

(2) 본 것

- 이미 목록이 있던 상태에서 503 이 나자 토스트 `목록을 불러오지 못했습니다 (503)` 만 떴다. 목록·통계는 이전 내용 그대로였고, 헤더는 초록 `연결됨` 이었다. 다시 시도 단추는 없었다.
- 토스트는 4.5초 뒤 사라졌고, 그 뒤에는 화면 어디에도 실패 흔적이 없었다. 기록 탭을 다시 누르면 새 요청으로 복구된다.
- 빈 목록 상태의 503 도 같은 토스트만 남고 목록은 빈 채였다(`09-list-503-1280.png`).

(3) 갈무리

- `/tmp/r57-shots/S8/13-list-normal-1280.png` (정상 목록)
- `/tmp/r57-shots/S8/14-list-503-with-existing-1280.png` (503, 옛 목록 유지·연결됨)
- `/tmp/r57-shots/S8/09-list-503-1280.png` (빈 목록 503)

### 장면 5 올리기 503 - 대기열·다시 올리기 (1280)

(1) 밟은 걸음

```text
# 짧은 무음 wav 를 /tmp/r57-S8-sample.wav 로 만든 뒤
playwright-cli route "**/api/recordings" --status=503 --body='{"error":"지금은 올릴 수 없습니다 (503)"}' --content-type=application/json
playwright-cli click "#tabbtn-rec"
playwright-cli run-code "async page => { await page.setInputFiles('#file-input', '/tmp/r57-S8-sample.wav'); await page.waitForTimeout(1000); ... }"
playwright-cli screenshot --filename=/tmp/r57-shots/S8/15-upload-503-1280.png
# 503 을 풀고 '다시 올리기'
playwright-cli unroute "**/api/recordings"
playwright-cli click "#failed-box button.f-retry"
sleep 1.5 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/16-upload-retry-success-1280.png
curl -s http://127.0.0.1:18978/api/recordings
```

(2) 본 것

- 503 이면 헤더에 `올릴 녹음 1건` 배지, 아래 `올리지 못한 녹음` 상자에 `아직 올리지 못했습니다: 지금은 올릴 수 없습니다 (503)` 와 `내려받기`·`다시 올리기`·`지우기` 가 보였다.
- 503 을 풀고 `다시 올리기` 를 누르자 배지와 상자가 사라지고 서버 녹음 수가 1→2 로 늘었다. 다시 시도 길이 실제로 동작한다.
- 1280 에서 상자·단추가 겹치지 않았다.

(3) 갈무리

- `/tmp/r57-shots/S8/15-upload-503-1280.png`
- `/tmp/r57-shots/S8/16-upload-retry-success-1280.png`

### 장면 6 다시 받아쓰기 503 - 재시도 성공 (1280·430)

(1) 밟은 걸음

```text
playwright-cli click "#tabbtn-list" && sleep 0.8
playwright-cli click <녹취 항목 단추>
playwright-cli route "**/api/recordings/*/retry" --status=503 --body='{"error":"다시 받아쓰기를 시작하지 못했습니다 (503)"}' --content-type=application/json
playwright-cli click "getByRole('button', { name: '다시 받아쓰기', exact: true })"
playwright-cli eval "document.getElementById('toast').textContent"
playwright-cli unroute "**/api/recordings/*/retry"
playwright-cli click "getByRole('button', { name: '다시 받아쓰기', exact: true })"
sleep 2 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/39-detail-retry-success-430.png
```

(2) 본 것

- 503 이면 토스트 `다시 받아쓰기를 시작하지 못했습니다 (503)` 만 뜨고, 상세 화면의 단추는 그대로라 다시 누를 수 있었다.
- 503 을 풀고 다시 누르면 토스트 `다시 받아쓰기를 요청했습니다.` 가 뜨고 상세 상태가 `받아쓰는 중` 으로 바뀌었다. 430 에서도 같았다.

(3) 갈무리

- `/tmp/r57-shots/S8/17-detail-retry-503-1280.png`
- `/tmp/r57-shots/S8/38-detail-open-430.png`
- `/tmp/r57-shots/S8/39-detail-retry-success-430.png`

### 장면 7 묻기 503 - 재시도 성공 (1280)

(1) 밟은 걸음

```text
playwright-cli click "#tabbtn-ask" && sleep 0.8
playwright-cli select "#ask-scope" today
playwright-cli route "**/api/ask" --status=503 --body='{"error":"묻기를 시작하지 못했습니다 (503)"}' --content-type=application/json
playwright-cli click "#ask-go" && sleep 0.8
playwright-cli screenshot --filename=/tmp/r57-shots/S8/18-ask-503-1280.png
playwright-cli unroute "**/api/ask"
playwright-cli click "#ask-go" && sleep 2
playwright-cli screenshot --filename=/tmp/r57-shots/S8/19-ask-retry-success-1280.png
```

(2) 본 것

- 범위가 `고른 것` 인 채로 누르면 `기록 탭에서 녹취를 먼저 골라 주세요.` 토스트가 뜨고 요청은 나가지 않았다(정상 안내). `오늘` 로 바꾸자 요청이 나갔다.
- 503 이면 토스트 `묻기를 시작하지 못했습니다 (503)`, 상태 글은 비고, `묻기` 단추는 다시 눌 수 있었다.
- 503 을 풀고 다시 누르면 가짜 LLM 답이 정상으로 보였다.

(3) 갈무리

- `/tmp/r57-shots/S8/18-ask-503-1280.png`
- `/tmp/r57-shots/S8/19-ask-retry-success-1280.png`

### 장면 8 목록 응답 없음 - 1초/9초 (1280)

(1) 밟은 걸음

```text
playwright-cli eval "(() => { window.__origFetch4 = window.fetch; window.fetch = function(u,o){ ... if (/\\/api\\/recordings\\?/.test(url) && m === 'GET') return new Promise(function(){}); ... }; return 'patched'; })()"
playwright-cli click "#tabbtn-list" && sleep 1.2
playwright-cli screenshot --filename=/tmp/r57-shots/S8/20-list-hang-1s-1280.png
sleep 8 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/21-list-hang-9s-1280.png
playwright-cli eval "JSON.stringify({conn:..., anyBusy:[...document.querySelectorAll('[aria-busy=true]')].length, text:...})"
```

(2) 본 것

- 응답을 붙잡은 채 기록 탭을 누르면 1.2초에도 9초에도 스피너·`aria-busy`·상태 글·토스트가 없었다.
- 화면에는 이전 목록이 그대로 남고 헤더는 초록 `연결됨` 이었다. 요청이 걸려 있다는 것을 알 길이 없었고, 시간 제한도 없어 그대로 기다리게 된다.

(3) 갈무리

- `/tmp/r57-shots/S8/20-list-hang-1s-1280.png`
- `/tmp/r57-shots/S8/21-list-hang-9s-1280.png`

### 장면 9 묻기 응답 없음 - 1초/11초 (1280)

(1) 밟은 걸음

```text
playwright-cli click "#tabbtn-ask"
playwright-cli eval "(() => { window.__origFetch5 = window.fetch; window.fetch = function(u,o){ ... if (/\\/api\\/ask$/.test(url) && m === 'POST') return new Promise(function(){}); ... }; return 'patched'; })()"
playwright-cli click "#ask-go" && sleep 1.2
playwright-cli screenshot --filename=/tmp/r57-shots/S8/22-ask-hang-1s-1280.png
sleep 10 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/23-ask-hang-11s-1280.png
```

(2) 본 것

- 1.2초에도 11초에도 상태 글 `요청 중…`, `묻기` 단추 `disabled=true`, 답 영역은 빈 채였다. 시간 제한·취소·다시 시도 길이 없어 새로 고침 전에는 묻기를 다시 할 수 없었다.
- 헤더는 여전히 초록 `연결됨` 이었다.

(3) 갈무리

- `/tmp/r57-shots/S8/22-ask-hang-1s-1280.png`
- `/tmp/r57-shots/S8/23-ask-hang-11s-1280.png`

### 장면 10 오프라인 녹음 - 대기열과 재연결 (1280)

(1) 밟은 걸음

```text
playwright-cli reload && sleep 1
playwright-cli run-code "async page => { await page.context().setOffline(true); return 'offline on'; }"
playwright-cli click "#tabbtn-rec"
playwright-cli click "#rec" && sleep 1.5 && playwright-cli click "#rec" && sleep 1.5
playwright-cli screenshot --filename=/tmp/r57-shots/S8/24-offline-recording-queued-1280.png
playwright-cli eval "JSON.stringify({online:navigator.onLine, conn:..., queue:..., failed:...})"
playwright-cli run-code "async page => { await page.context().setOffline(false); return 'offline off'; }"
sleep 2.5 && playwright-cli screenshot --filename=/tmp/r57-shots/S8/25-offline-reconnect-uploaded-1280.png
curl -s http://127.0.0.1:18978/api/recordings
```

(2) 본 것

- 오프라인 녹음은 `마지막 녹음 00:02 · 저장됨, 서버로 올리는 중입니다.` 로 저장되고 대기열에 남았다. 헤더 배지 `올릴 녹음 1건`, 상자 `아직 올리지 못했습니다: 연결 안 됨`, `다시 올리기` 가 보였다.
- 헤더 연결 표시는 초록 `연결됨` 그대로였다(오프라인인데도). 대기열 쪽 문구는 `연결 안 됨` 이라 서로 달랐다.
- 다시 연결하자 2.5초 안에 배지와 상자가 사라지고 서버 녹음 수가 2→3 으로 늘었다. 자동 업로드가 동작했다.

(3) 갈무리

- `/tmp/r57-shots/S8/24-offline-recording-queued-1280.png`
- `/tmp/r57-shots/S8/25-offline-reconnect-uploaded-1280.png`

### 장면 11 320×700 - 설정·긴 503 토스트·오프라인 대기열

(1) 밟은 걸음

```text
playwright-cli resize 320 700
playwright-cli click "#settings-btn" && sleep 1.2
playwright-cli screenshot --filename=/tmp/r57-shots/S8/26-settings-open-320.png
playwright-cli screenshot --full-page --filename=/tmp/r57-shots/S8/27-settings-full-320.png
# PUT 503, 긴 서버 오류 문구
playwright-cli run-code "async page => { await page.locator('#stt-defaults-save').scrollIntoViewIfNeeded(); ... page.click('#stt-defaults-save'); await page.waitForTimeout(350); ... screenshot ... }"
# 오프라인 녹음
playwright-cli reload && sleep 1
playwright-cli run-code "async page => { await page.context().setOffline(true); return 'offline'; }"
playwright-cli click "#tabbtn-rec" && playwright-cli click "#rec" && sleep 1.2 && playwright-cli click "#rec" && sleep 1.5
playwright-cli screenshot --filename=/tmp/r57-shots/S8/32-offline-queued-320.png
playwright-cli screenshot --full-page --filename=/tmp/r57-shots/S8/33-offline-queued-full-320.png
```

(2) 본 것

- 설정: 가로 넘침 없음(`document.documentElement.scrollWidth == 320`), 설정 카드 304px, 칸 256px, 전처리·저장·탭 높이 모두 44px. 체크박스 줄과 도움말은 줄바꿈되지만 넘치지 않았다.
- 긴 503 토스트: `받아쓰기 기본값을 저장하지 못했습니다 (503) - 서버가 잠시 점검 중입니다. 잠시 뒤 다시 시도해 주세요.` 가 폭 160px, 높이 188px 로 좁게 줄바꿈됐다. 토스트 사각형 `x=80,y=496,w=160,h=188` 이 탭 줄(`y=520~564`)과 녹음 단추를 덮었다. 짧은 성공 토스트는 160×68 로 탭을 덮지 않았다.
- 오프라인 대기열: 배지·`올리지 못한 녹음` 상자·세 단추가 320 안에 들어왔고 단추 높이는 44px. 상자 단추는 두 줄로 접혔다. 헤더에는 `VoxLog`·`올릴 녹음 1건`·`연결됨`·`설정` 이 모두 보였다(설정 단추 58×44, x=254).
- 320 에서도 헤더 연결 표시는 초록 `연결됨` 이었다.

(3) 갈무리

- `/tmp/r57-shots/S8/26-settings-open-320.png`
- `/tmp/r57-shots/S8/27-settings-full-320.png`
- `/tmp/r57-shots/S8/28-settings-save-503-toast-320.png` (긴 토스트가 탭·녹음 단추를 덮음)
- `/tmp/r57-shots/S8/29-settings-save-ok-toast-320.png` (짧은 성공 토스트)
- `/tmp/r57-shots/S8/32-offline-queued-320.png`
- `/tmp/r57-shots/S8/33-offline-queued-full-320.png`
- `/tmp/r57-shots/S8/34-settings-btn-320-offline.png`
- `/tmp/r57-shots/S8/35-header-320-offline.png`

### 장면 12 430×900 - 설정·긴 503 토스트·상세

(1) 밟은 걸음

```text
playwright-cli resize 430 900
playwright-cli reload && sleep 1
playwright-cli eval "(() => { window.scrollTo(0,0); return 'top'; })()"
playwright-cli click "#settings-btn" && sleep 1.2
playwright-cli screenshot --filename=/tmp/r57-shots/S8/36-settings-open-430.png
playwright-cli screenshot --full-page --filename=/tmp/r57-shots/S8/37-settings-full-430-clean.png
# 긴 PUT 503 토스트
playwright-cli run-code "async page => { ... scrollIntoViewIfNeeded ... click ... waitForTimeout(350) ... screenshot ... }"
# 상세 열고 다시 받아쓰기
playwright-cli click "#tabbtn-list" && sleep 0.8
playwright-cli click <녹취 항목 단추>
playwright-cli screenshot --filename=/tmp/r57-shots/S8/38-detail-open-430.png
```

(2) 본 것

- 가로 넘침 없음(`scrollWidth == 430`), 설정 카드 406px, 저장·탭 높이 44px. 430 에서는 320 보다 여유가 있었다.
- 긴 503 토스트는 폭 215px, 높이 140px 로 여전히 좁은 기둥 모양이었지만, 이 스크롤 위치에서는 탭·저장 단추를 덮지 않았다(토스트 y=744~884, 탭 y=520~564). 녹음 시간·아래 안내 글 일부를 덮었다.
- 상세 화면과 다시 받아쓰기 단추는 430 에서 겹침 없이 보였고, 503 뒤 재시도도 성공했다.

(3) 갈무리

- `/tmp/r57-shots/S8/36-settings-open-430.png`
- `/tmp/r57-shots/S8/37-settings-full-430-clean.png`
- `/tmp/r57-shots/S8/31-settings-save-503-toast-430.png`
- `/tmp/r57-shots/S8/38-detail-open-430.png`
- `/tmp/r57-shots/S8/39-detail-retry-success-430.png`

## 결함

### D1 (중) 320px 에서 긴 토스트가 화면 절반 폭으로 좁아져 탭·녹음 단추를 덮는다

- 재현 걸음: 320×700 → 설정 열기 → `PUT /api/stt-options` 를 503 으로 가로채고 긴 오류 문구를 주기 → `기본값 저장` 클릭 → 350ms 뒤 화면과 `getBoundingClientRect` 측정.
- 기대: 토스트가 화면 폭(최대 `92vw`)에 맞게 퍼지고, 탭·단추 같은 조작 요소를 덮지 않는다.
- 실제: 토스트가 `x=80,y=496,w=160,h=188` 로 폭이 정확히 화면의 절반(160px)이고, 탭 줄(`y=520~564`)과 녹음 단추를 덮었다. 430 에서도 `w=215,h=140` 으로 절반 폭(215px)이었다. `pointer-events:none` 이라 탭은 아래로 통과하지만, 가려진 단추를 누르게 되어 오작동할 수 있다. 짧은 토스트도 160px 폭으로 줄바꿈된다.
- 의심 위치: `projects/VoxLog/web/style.css:187` 의 `.toast` 가 `left:50%` + `transform` 으로 가운데 정렬하면서 `width`/`right` 를 주지 않아, 고정 요소의 shrink-to-fit 폭이 남은 절반(50vw)으로 계산된다. `width: max-content`(와 `max-width`) 또는 `left:8px; right:8px; margin-inline:auto; transform:none` 꼴이 표준에 가깝다.
- 갈무리: `/tmp/r57-shots/S8/28-settings-save-503-toast-320.png`, `/tmp/r57-shots/S8/31-settings-save-503-toast-430.png`, 비교용 `/tmp/r57-shots/S8/29-settings-save-ok-toast-320.png`

### D2 (중) 목록을 못 불러올 때(503·무응답) 상태·재시도가 없고 '연결됨' 이 남는다

- 재현 걸음 A(503): 정상 목록을 연 뒤 `route "**/api/recordings?*" --status=503` → `기록` 탭 클릭. 토스트가 사라진 뒤 다시 확인.
- 재현 걸음 B(무응답): `eval` 로 `GET /api/recordings?` 를 영원히 안 끝나는 Promise 로 바꾼 뒤 `기록` 탭 클릭. 1.2초·9초에 확인.
- 기대: 실패가 화면에 계속 남고(또는 연결 표시가 `연결 안 됨` 으로 바뀌고), 다시 시도할 단추나 길이 보인다. 무응답이면 로딩 표시나 시간 제한이 있다.
- 실제: 503 이면 토스트 `목록을 불러오지 못했습니다 (503)` 만 4.5초 떴다가 사라지고, 옛 목록·통계가 그대로 남으며 헤더는 초록 `연결됨` 이다. 다시 시도 단추는 없다. 무응답이면 1.2초에도 9초에도 스피너·`aria-busy`·상태 글이 없고, 옛 목록과 `연결됨` 이 그대로다.
- 의심 위치: `projects/VoxLog/web/app.js:1174` `loadList` 의 요청에 `AbortController`/시간 제한이 없고, `:1193` 실패 갈래는 `onApiError` 만 부른다. `:105` `onApiError` 는 401·status 0 만 `연결 안 됨` 으로 바꾸고 503 은 그대로 둔다.
- 갈무리: `/tmp/r57-shots/S8/14-list-503-with-existing-1280.png`, `/tmp/r57-shots/S8/20-list-hang-1s-1280.png`, `/tmp/r57-shots/S8/21-list-hang-9s-1280.png`, 빈 목록 `/tmp/r57-shots/S8/09-list-503-1280.png`

### D3 (중) 묻기 응답이 없으면 '요청 중…' 과 잠긴 단추가 끝없이 남는다

- 재현 걸음: `묻기` 탭, 범위 `오늘` → `eval` 로 `POST /api/ask` 를 영원히 안 끝나는 Promise 로 바꿈 → `묻기` 클릭 → 1.2초·11초 확인.
- 기대: 시간 제한 뒤 `요청 중…` 을 풀고 단추를 다시 누를 수 있게 하거나, 실패·다시 시도를 안내한다.
- 실제: 11초 뒤에도 상태 글 `요청 중…`, `묻기` 단추 `disabled=true`, 답 영역 빈 채. 취소·재시도 길이 없어 새로 고침 전에는 다시 묻지 못한다. 헤더는 `연결됨` 그대로다.
- 의심 위치: `projects/VoxLog/web/app.js:1591` `ask` 가 `:1606` 의 POST 에 시간 제한을 두지 않고, 성공·거절 처리기에서만 `ask-go` 를 푼다.
- 갈무리: `/tmp/r57-shots/S8/22-ask-hang-1s-1280.png`, `/tmp/r57-shots/S8/23-ask-hang-11s-1280.png`

### D4 (하) 오프라인인데 헤더는 초록 '연결됨' 이다

- 재현 걸음: `run-code` 로 `context.setOffline(true)` → `녹음` 탭에서 1.5초 녹음.
- 기대: 오프라인 동안 헤더 연결 표시가 `연결 안 됨`(또는 오프라인)으로 바뀐다.
- 실제: `navigator.onLine == false` 인데 헤더는 초록 `연결됨`. 대기열 배지와 `올리지 못한 녹음` 상자의 `연결 안 됨` 만 사실을 말한다. 재연결하면 자동 업로드는 정상.
- 의심 위치: `projects/VoxLog/web/app.js:105` `onApiError` 는 API 실패 때만 연결 표시를 바꾸고, 오프라인 녹음 경로는 API 를 부르지 않는다. `online` 만 듣고 `offline` 은 듣지 않는다(`projects/VoxLog/web/queue.js:622` 는 `online` 만 등록).
- 갈무리: `/tmp/r57-shots/S8/24-offline-recording-queued-1280.png`, `/tmp/r57-shots/S8/32-offline-queued-320.png`

### D5 (하) 설정 불러오기 실패에 '다시 시도' 단추가 없고, 닫았다 열어야 한다는 안내도 없다

- 재현 걸음: `route "**/api/stt-options" --status=503` 로 설정을 열거나, `GET /api/stt-options` 를 응답 없이 붙잡고 1000ms 제한을 기다린다.
- 기대: 안내 옆에 다시 시도할 수 있는 단추가 있거나, "설정을 닫았다 다시 열어 주세요" 같은 길을 알려 준다.
- 실제: `받아쓰기 옵션을 불러오지 못했습니다: …`(또는 `시간이 지났습니다`) 만 남고, 칸·저장 단추가 숨는다. 다시 시도 단추는 없다. 실제로 설정을 닫았다 다시 열면 새 GET 이 나가 정상으로 채워지지만, 그 사실은 화면에 없다.
- 의심 위치: `projects/VoxLog/web/app.js:318` `loadSttSettings` 의 실패 처리(주석 318~345)와 `projects/VoxLog/web/index.html:33` 의 `#stt-defaults` 안에 다시 시도 단추가 없음.
- 갈무리: `/tmp/r57-shots/S8/05-settings-get-hang-1000ms-1280.png`, `/tmp/r57-shots/S8/11-settings-get-503-1280.png`

## playwright-cli 를 쓰다 막힌 것

- `eval` 은 식(expression)만 받는다. `window.fetch = ...; return ...` 처럼 문장을 이어 쓰면 `SyntaxError: Unexpected token ';'` 가 난다. 모든 다문장 평가는 `(() => { ...; return ...; })()` 로 감싸서 썼다.
- `route` 에는 지연·무응답 옵션이 없다. 응답 없음·붙잡기는 `eval`/`run-code` 로 `window.fetch` 를 바꿔 영원히 안 끝나는 Promise 를 돌려주는 식으로 흉내 냈다. `window.__VOX_STT_TIMEOUT_MS__` 는 `run-code` 의 `page.addInitScript` 로 페이지 로드 전에 넣었다.
- `upload` 명령은 보이지 않는 `#file-input` 에 바로 쓰기 어려워, `run-code` 안에서 `page.setInputFiles('#file-input', '/tmp/r57-S8-sample.wav')` 를 썼다(change 이벤트는 정상 발생).
- `screenshot --full-page` 는 스크롤이 0 이 아닐 때 `position: sticky` 헤더를 현재 스크롤 위치에 한 번 더 그린다(430 설정 전체 갈무리에서 헤더가 카드 중간에 보임). 제품 결함이 아니라 갈무리 도구의 합성 현상이라, 레이아웃 판정에는 스크롤 0 의 전체 갈무리(`37-...`)와 뷰포트 갈무리를 썼다.
- 브라우저는 한 번에 하나만 띄웠고, 장면 사이에 `close` 하지 않고 같은 세션을 이어 썼다(램 4GB). 마지막에 `playwright-cli close` 로 닫았다.
