# VoxLog (복스로그)

폰에서 음성 녹음을 쉽게 남기고 쌓아, 크롬 앱(PWA)에서 여러 방식으로 찾아보고 클로드에게 묻는 녹취 기록 앱.
(요청 `Q-261116-fa85`, R33 에서 시작)

## 무엇을 하나

1. **녹음** - 폰의 VoxLog 앱(설치한 PWA)에서 큰 단추 하나로 녹음 시작·멈춤. 멈추면 음성 파일이 생깁니다.
2. **올리기** - 녹음을 시작할 때 **위치정보**(위도·경도·정확도, 설정에서 끌 수 있음)를 함께 얻습니다. 음성 파일과 위치는 기기 안 대기열(IndexedDB)에 먼저 들어가고 백엔드 API 로 올라갑니다.
   네트워크가 끊겼으면 **Background Sync** 로 기다렸다가 연결되면 자동으로 올립니다(지원 안 하는 브라우저는 앱을 열거나
   온라인이 될 때 올림).
3. **받아쓰기** - 서버가 받은 음성을 텍스트로 인식해 `data/transcripts/<날짜>/<id>.txt` 로 쌓습니다.
4. **조회** - 녹취 현황(날짜별 수·글자 수), 검색·날짜 거르기, 녹음 다시 듣기, 받아 적은 글 보기.
5. **묻기** - 고른 녹취(또는 오늘·이번 주·검색 결과)로 요약·핵심어·할 일 뽑기·직접 묻기를 요청하면 서버가
   **claude CLI** 로 답을 만들고 앱에 보여 줍니다. 답은 쌓여서 다시 볼 수 있습니다.

## 측면(전원) 버튼으로 녹음 시작·멈춤

웹 앱(PWA)은 전원 버튼 누름을 직접 받을 수 없습니다(안드로이드가 어떤 앱에도 주지 않음). 그래서 이렇게 잇습니다.

- 앱은 **열릴 때마다 녹음을 켜고 끄는 신호**를 받습니다: 매니페스트 `launch_handler: focus-existing` + `launchQueue`.
  이미 떠 있는 VoxLog 를 다시 열면 새 창 대신 그 창에 "열림" 이 전달되고, 설정 '앱을 열면 바로 녹음' 이 켜져 있으면
  녹음 중이 아니면 시작, 녹음 중이면 멈춥니다.
- **삼성 갤럭시:** 설정 → 유용한 기능 → 측면 버튼 → **두 번 누르기 → 앱 열기 → VoxLog**. 측면 버튼 두 번 = 녹음 시작,
  다시 두 번 = 멈춤.
- 다른 안드로이드: 아이콘 길게 누르기 → '녹음 시작/멈춤' 바로가기(매니페스트 `shortcuts`)를 홈 화면에 두거나,
  버튼을 앱 실행에 묶는 도구(제조사 설정, Key Mapper 등)로 VoxLog 를 엽니다.
- 녹음 중 화면이 꺼지면 크롬이 녹음을 멈출 수 있어, 녹음 중에는 화면 켜짐 유지(Wake Lock)를 씁니다.

## 실행

```bash
cd projects/VoxLog
python3 serve.py                                   # http://127.0.0.1:8790 (이 컴퓨터에서만)
python3 serve.py --host 0.0.0.0 --token <비밀> --tls-cert cert.pem --tls-key key.pem   # 폰에서 쓸 때
```

- 폰의 크롬에서 마이크·서비스 워커를 쓰려면 **HTTPS**(또는 localhost)여야 합니다. 밖에 열 때는 토큰이 필수입니다
  (루프백이 아닌 주소에 토큰 없이는 시작을 거절).
- 음성인식 백엔드 (`VOXLOG_STT`):
  - `command` - `VOXLOG_STT_CMD="whisper-cli -m model.bin -f {wav} -nt -l ko"` 처럼 받아쓰기 명령(16kHz 모노 wav 를 받음)
  - `api` - `VOXLOG_STT_URL` 의 OpenAI 꼴 받아쓰기 엔드포인트(`…/v1/audio/transcriptions`). 모델 `VOXLOG_STT_MODEL`,
    언어 `VOXLOG_STT_LANG`(기본 `ko`), 키가 필요한 서버면 `VOXLOG_STT_API_KEY`. 화자 구분 없이 받아쓸 때는 긴 녹음을 10분씩 잘라 보냅니다(서버 권장: 한 요청 10분·25MB 이하).
    지금 설정(`settings.json`)은 KISTI 의 `Qwen3-ASR-1.7B`
  - 화자 구분: `VOXLOG_STT_DIARIZE=1` 이면 녹음을 자르지 않고 통째로 `response_format=diarized_json` 과 함께 보내고,
    서버가 돌려준 `segments`(`speaker`·`text`)를 `화자 1: …` 줄로 적습니다(지금 설정은 켜 둠). 서버가 녹음 전체에서
    화자를 나누므로 긴 녹음도 화자 번호가 끝까지 같습니다
  - 없으면 녹음은 쌓이고 상태가 '음성인식 없음' - 나중에 백엔드를 켜고 '다시 받아쓰기'
  - 음성 변환에 `ffmpeg` 가 필요합니다
- 묻기는 `claude` CLI(`claude -p`, 도구 없이)를 씁니다. 다른 명령은 `VOXLOG_LLM_CMD`.
- 데이터는 `data/`(git 제외) 또는 `VOXLOG_DATA`.
- 서버 설정은 `settings.json` 의 `VOXLOG_*` 값 위에 환경 변수를 덮은 것입니다(환경 변수가 이김). 모니터의 '앱 열기'·배포는
  환경을 좁혀 띄우므로 음성인식 주소·모델은 이 파일에 둡니다. 비밀 값은 넣지 않습니다.

### 모니터 '앱 열기'

`app.json` 의 `"server": "serve.py"` 로 모니터가 서버를 띄워 이어 주므로 **녹취 목록·검색·묻기는 모니터에서도 됩니다.**
다만 모니터의 앱 화면은 격리된 출처(sandbox)라 서비스 워커·IndexedDB·마이크가 없고, 모니터의 앱 API 본문 상한이
64KB 라 **녹음과 올리기는 VoxLog 자체 주소에서** 합니다. 화면이 이를 알아보고 안내합니다. 모니터에서는 지우기
단추가 숨고(모니터가 DELETE 를 이어 주지 않음), 2MB 가 넘는 음성(32kbps 로 약 8분)은 응답 상한 때문에 자체 주소에서 듣습니다.

## 폴더

```
serve.py            HTTP 서버 (정적 web/ + /api/*)
voxlog/             store.py(저장소) · stt.py(음성인식) · ask.py(클로드 묻기)
web/                화면(index.html·app.js·api.js·style.css) · 서비스 워커(sw.js)·대기열(queue.js) · 매니페스트·아이콘
tests/              단위 검사(python3 -m unittest discover -s tests) · 끝에서 끝 브라우저 검사(browser_voxlog.py)
docs/INTERFACE.md   모듈·API·전역 객체의 약속
data/               실행 데이터 (git 제외)
```
