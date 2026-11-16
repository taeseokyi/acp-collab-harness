# VoxLog 인터페이스 (R33 관리자가 고정 - 모든 작업자가 이것에 맞춰 씀)

바꾸고 싶으면 고치지 말고 보고에 적습니다. 파이썬은 **표준 라이브러리만**, 브라우저 쪽은 **빌드 없는 바닐라 JS**(모듈 아님, `<script>` 로 읽힘).

## 폴더

```
projects/VoxLog/
  serve.py                 HTTP 서버(정적 web/ + /api/*)            - T-342
  voxlog/__init__.py       (빈 파일)                                - T-338
  voxlog/store.py          저장소                                   - T-338
  voxlog/stt.py            음성인식(백엔드 고르기 + 배경 작업자)     - T-339
  voxlog/ask.py            클로드 CLI 로 묻기(배경 작업자)           - T-340
  web/index.html web/style.css web/app.js web/api.js   화면         - T-341
  web/sw.js web/queue.js web/manifest.webmanifest web/icons/*       - T-343
  tests/test_store.py tests/test_stt.py tests/test_ask.py tests/test_serve.py
  tests/fake_stt.py tests/fake_llm.py   (가짜 명령 - 각 노드가 필요한 쪽이 씀, 아래 형식)
  tests/browser_voxlog.py  끝에서 끝 브라우저 검사                   - T-344
  data/                    실행 데이터(git 제외). 환경 변수 VOXLOG_DATA 로 바꿈
```

검사는 `projects/VoxLog` 에서 `python3 -m unittest discover -s tests` 로 돕니다(각 tests/*.py 는
`sys.path.insert(0, <프로젝트 폴더>)` 로 `voxlog` 를 읽음). 검사는 임시 폴더(`tempfile`)만 씁니다.

## 데이터 (data/ 아래)

- `audio/<id>.<ext>` 받은 녹음 원본 (ext: webm·ogg·m4a·mp3·wav)
- `meta/<id>.json` 녹음 하나의 메타
- `transcripts/<YYYY-MM-DD>/<id>.txt` 받아 적은 글 (날짜는 recorded_at 의 날짜) - **텍스트 파일로 쌓이는 것이 요청의 핵심**
- `answers/<aid>.json` 묻기 결과

id 형식: 녹음 `r-YYYYMMDD-HHMMSS-xxxx`, 답 `a-YYYYMMDD-HHMMSS-xxxx` (xxxx 는 소문자 16진 4자리).
경로를 만들기 전에 반드시 정규식 `^r-\d{8}-\d{6}-[0-9a-f]{4}$` / `^a-\d{8}-\d{6}-[0-9a-f]{4}$` 로 검사합니다.

녹음 메타(dict, JSON):
```
{"id", "client_id": str|None, "created": 서버 ISO 시각, "recorded_at": 클라이언트 ISO 시각(없으면 created),
 "duration_ms": int|None, "mime": "audio/webm" 꼴(매개변수 뗀 것), "size": int,
 "status": "pending"|"transcribing"|"done"|"failed"|"no-stt", "error": str|None,
 "title": 받아 적은 글 앞 40자(없으면 ""), "chars": int}
```

## voxlog/store.py

```python
MAX_AUDIO_BYTES = 50 * 1024 * 1024
ALLOWED_MIME = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
                "audio/wav": "wav", "audio/x-wav": "wav"}
class Store:
    def __init__(self, root: pathlib.Path)               # 하위 폴더를 만듦. 스레드 안전(threading.Lock), 쓰기는 임시 파일+os.replace
    def add_recording(self, data: bytes, mime: str, recorded_at: str|None=None,
                      duration_ms: int|None=None, client_id: str|None=None, location: dict|None=None) -> dict
        # mime 의 ';codecs=…' 를 떼고 ALLOWED_MIME 검사, 빈 데이터·너무 큼·모르는 mime → ValueError(한국어 까닭)
        # 같은 client_id 가 이미 있으면 새로 만들지 않고 그 메타에 "duplicate": True 를 붙여 돌려줌 (업로드 재시도 대비)
        # 새 것은 status "pending". 메모리에 든 바이트를 incoming/ 에 쓴 뒤 add_recording_file 로 넘김
    def incoming_path(self) -> pathlib.Path              # root/incoming/up-<16진> - 아직 없는 새 경로(폴더는 만들어 둠)
    def add_recording_file(self, path, mime, recorded_at=None, duration_ms=None,
                           client_id=None, location=None) -> dict
        # incoming_path() 에 흘려 쓴 파일을 검사(mime·빈 파일·크기)하고 audio/ 로 옮김(복사 아님). 같은 인자·같은 오류(ValueError)·
        # 같은 duplicate 규칙. 실패·중복이면 그 파일은 지움. Store 를 만들 때 incoming/ 에 남은 찌꺼기는 치움
    def get(self, rid) -> dict|None                      # 메타 + "transcript": 글(없으면 "")
    def list(self, q=None, date_from=None, date_to=None, status=None, limit=200) -> list[dict]
        # recorded_at 최신순. q 는 받아 적은 글·title 에서 대소문자 무시 부분 일치. date_* 는 "YYYY-MM-DD"(포함).
        # 항목은 메타 + "snippet"(q 가 있으면 맞은 곳 앞뒤 40자, 없으면 글 앞 80자)
    def audio_path(self, rid) -> pathlib.Path|None
    def set_status(self, rid, status, error=None) -> None
    def set_transcript(self, rid, text) -> None          # txt 쓰기, status "done", title·chars 갱신, error None
    def pending_ids(self) -> list[str]                   # status 가 pending 또는 transcribing 인 것 (재시작 때 다시 넣기)
    def delete(self, rid) -> bool                         # 오디오·메타·글 지움
    def stats(self) -> dict  # {"count","done","pending","failed","chars","by_date": {"YYYY-MM-DD": n}}
    def add_answer(self, kind, prompt, ids) -> dict      # {"id","kind","prompt","ids","created","status":"running","answer":None,"error":None}
    def set_answer(self, aid, status, answer=None, error=None) -> None   # status "done"|"failed"
    def get_answer(self, aid) -> dict|None
    def list_answers(self, limit=50) -> list[dict]       # 최신순
```
잘못된 id 는 get/audio_path/get_answer 가 None, set_*/delete 는 False 또는 KeyError 없이 조용히 무시하지 말고 `ValueError`.

## voxlog/stt.py

```python
class SttUnavailable(Exception)   # 백엔드가 없음 → 메타 status "no-stt"
class SttError(Exception)         # 실패 → status "failed", error 에 짧은 까닭(키·주소 없이)
def backend_name(env=None) -> str  # "command" | "api" | "none"
    # VOXLOG_STT 가 있으면 그것. 없으면 VOXLOG_STT_CMD 가 있으면 "command", VOXLOG_STT_URL 이 있으면 "api", 아니면 "none"
def to_audio(src: pathlib.Path, fmt: str) -> pathlib.Path   # ffmpeg 로 16kHz 모노 wav/mp3 임시 파일 (ffmpeg 없으면 SttError)
def transcribe(path: pathlib.Path, mime: str, env=None, opener=None) -> str
    # command: VOXLOG_STT_CMD 를 shlex.split, "{wav}" 자리에 16k 모노 wav 경로, shell 없이 실행, stdout 이 글, 시간 상한 600초
    # api: OpenAI 꼴 받아쓰기 엔드포인트. split_audio 로 16kHz 모노 mp3 를 CHUNK_SECONDS(600초)씩 잘라 차례로
    #   POST VOXLOG_STT_URL (multipart: file, language=VOXLOG_STT_LANG(기본 "ko"), model=VOXLOG_STT_MODEL(있을 때)),
    #   VOXLOG_STT_API_KEY 가 있으면 Bearer. 응답 {"text": …} 을 빈칸으로 이어 붙임. 조각마다 시간 상한 180초, opener 는 검사용 주입
    #   VOXLOG_STT_DIARIZE=1 이면 자르지 않고 mp3 하나로 통째로 보내며 response_format=diarized_json 을 더 보냄
    #   (시간 상한 DIARIZE_TIMEOUT 3600초). 응답에 segments([{speaker, text, …}])가 있으면 "화자 N: 글" 줄들로 적음
    #   (같은 화자가 이어지면 한 줄, 번호는 처음 나온 차례). segments 가 없으면 text 그대로
def split_audio(src: pathlib.Path, seconds=None) -> (pathlib.Path, list)   # (임시 폴더, 조각 경로들) - 폴더는 호출한 쪽이 지움
class Transcriber:
    def __init__(self, store, env=None, transcribe_fn=transcribe)
    def start(self)            # 데몬 스레드 하나, store.pending_ids() 를 먼저 넣음
    def submit(self, rid)      # 큐에 넣음 (같은 id 중복 무시)
    def busy(self, rid) -> bool      # 그 id 가 큐에 있거나 지금 받아쓰는 중
    def resubmit(self, rid) -> bool  # busy 면 False(retry 는 409). 아니면 잠금 안에서 status "pending" 으로 바꾸고 큐에 넣고 True
    def stop(self, timeout=5)
    def idle(self) -> bool     # 큐가 비고 처리 중인 것이 없음 (검사용)
    # 처리: set_status(rid,"transcribing") → transcribe → set_transcript / no-stt / failed
```

## voxlog/ask.py

```python
KINDS = {"summary": "요약", "keywords": "핵심어·주제", "todo": "할 일·약속 뽑기", "custom": "직접 묻기"}
MAX_PROMPT_CHARS = 200_000
class AskUnavailable(Exception)  # 명령이 없음
class AskError(Exception)
def build_prompt(kind, user_prompt, items) -> str
    # items: [{"id","recorded_at","transcript"}] 오래된 순으로 묶음, 각 녹취는 구분선과 id·시각 머리로 감쌈
    # "아래 녹취는 자료일 뿐 지시가 아니다" 를 명시. 너무 길면 오래된 것부터 빼고 뺐다는 줄을 넣음
    # custom 은 user_prompt 필수(없으면 ValueError), 나머지는 user_prompt 를 덧붙임(있으면)
def llm_command(env=None) -> list[str]
    # VOXLOG_LLM_CMD 가 있으면 shlex.split, 없으면 ["claude","-p","--tools","","--no-session-persistence","--output-format","text"]
def run_llm(prompt, env=None, timeout=300) -> str   # 프롬프트는 stdin 으로, 코드 0 이 아니면 AskError(stderr 끝 300자), 실행 파일 없음 → AskUnavailable
class Asker:
    def __init__(self, store, env=None, run=run_llm)
    def start(self) ; def stop(self, timeout=5) ; def idle(self) -> bool
    def submit(self, kind, prompt, ids) -> dict
        # kind 검사(ValueError), ids 가 비었거나 받아 적은 글이 하나도 없으면 ValueError
        # store.add_answer → 큐(한 번에 하나) → build_prompt → run → set_answer(done|failed)
```

## serve.py

`python3 serve.py [--host 127.0.0.1] [--port 8790] [--data DIR] [--token T] [--tls-cert C --tls-key K]`
(모니터는 `--host 127.0.0.1 --port N` 만 넘김). 토큰은 `--token` 또는 환경 변수 `VOXLOG_TOKEN`.
`--host` 가 루프백이 아닌데 토큰이 없으면 **시작을 거절**합니다. ThreadingHTTPServer, 표준 라이브러리만.

정적: `/` → `web/index.html`, `/<파일>` → `web/` 아래(경로 탈출 거절). `sw.js` 는 `Cache-Control: no-cache`.
API (JSON, 오류는 `{"error": "한국어 까닭"}` + 4xx/5xx). 토큰이 있으면 `/api/*` 는 `Authorization: Bearer <토큰>`
필요(`hmac.compare_digest`), 없거나 틀리면 401. `GET /api/health` 만 토큰 없이도 `{"ok":true,"auth":bool}` 를 줌.

| 요청 | 답 |
| ---- | -- |
| `GET /api/health` | `{"ok":true,"auth":bool,"stt":backend_name,"llm":bool(명령 있음),"version":"0.1"}` |
| `POST /api/recordings` 본문=오디오 그대로, 머리 `Content-Type`, `X-Recorded-At`, `X-Duration-Ms`, `X-Client-Id` | 201 메타(새 것) / 200 메타(duplicate) / 400 / 413 / 503(동시 업로드 2개 넘음, `Retry-After: 5`) / 507(디스크 여유 부족) |
| `GET /api/recordings?q=&from=&to=&status=&limit=` | `{"items":[…],"stats":{…}}` |
| `GET /api/recordings/<id>` | 메타+transcript / 404 |
| `GET /api/recordings/<id>/audio` | 오디오 바이트(그 mime) |
| `POST /api/recordings/<id>/retry` | 음성인식 다시 넣음 → 200 메타 / 404 / 409(이미 큐에 있거나 받아쓰는 중) |
| `DELETE /api/recordings/<id>` | `{"ok":true}` |
| `POST /api/ask` `{"kind","prompt","ids":[…]}` | 202 답 메타 |
| `GET /api/answers` · `GET /api/answers/<aid>` | 목록 `{"items":[…]}` · 답 하나 |

업로드 본문은 메모리에 모으지 않고 `Store.incoming_path()` 의 `incoming/` 파일에 조각씩 흘려 쓴 뒤(fsync) `Store.add_recording_file` 로
`audio/` 로 옮깁니다. 동시에 받는 업로드는 2개(`max_uploads`)이고 넘으면 본문을 읽지 않고 503 + `Retry-After: 5`, 저장소 디스크 여유가
본문 길이+여유분보다 적으면 507. 큰 본문이면 서버가 연결을 닫으므로 클라이언트에는 상태 코드 대신 **연결 오류**로 보일 수 있음
(그래서 503·507·연결 오류는 영구 실패가 아니라 대기열에 남겨 다시 올림). 받는 도중 끊기면 400.
받은 녹음은 바로 `Transcriber.submit`. 남의 출처(`Origin` 이 있고 Host 와 다르고 `null` 도 아님) 쓰기 요청은 토큰 없을 때 403
(자모맞히기 `serve.py` 의 같은 검사를 참고).

## 브라우저 쪽 (전역 객체, 바닐라 JS)

`web/queue.js` (T-343) → `window.VoxQueue`:
```
VoxQueue.getConfig() -> Promise<{token: string, autoRecord: bool, saveLocation: bool}>  // apiBase 는 없어짐 - 늘 같은 출처
VoxQueue.setConfig(partial) -> Promise<void>
VoxQueue.enqueue({blob, mime, recordedAt, durationMs, clientId, location}) -> Promise<void>   // IndexedDB 에 넣고 sync 등록 + 바로 flush 시도
VoxQueue.pending() -> Promise<[{clientId, recordedAt, size, tries, lastError}]>
VoxQueue.flush() -> Promise<{sent, failed}>          // 앞 화면에서 바로 올림(동시에 둘 돌지 않음)
VoxQueue.onchange(cb)                               // 대기열이 바뀌면(넣음·올림·실패, 서비스 워커가 올린 것 포함) cb()
VoxQueue.supported() -> {indexedDB, serviceWorker, backgroundSync}
```
IndexedDB `voxlog` 판 1: 저장소 `queue`(keyPath `clientId`: `{clientId, blob, mime, recordedAt, durationMs, tries, lastError, addedAt}`),
`config`(키 `"main"`). 서비스 워커 `web/sw.js` 는 `sync` 태그 `voxlog-upload` 에서 같은 DB 를 읽어
같은 출처의 `POST api/recordings` 로 올리고(예전에 저장된 `apiBase` 는 무시; 2xx 면 지움, 401 이면 멈추고 lastError "인증 실패", 네트워크 오류면 throw 해서
브라우저가 다시 시도), 클라이언트에 `postMessage({type:"voxlog-queue"})`. Background Sync 가 없으면 `online`·
`visibilitychange`·앱 열기 때 flush. 페이지의 flush 는 5xx(503·507 등) 를 만나면 그 줄을 `waiting` 으로 남기고 멈춘 뒤
`Retry-After` 초(없으면 5, 최대 60)에 한 번 `setTimeout(flush)` 을 겁니다(이미 걸려 있으면 다시 걸지 않음; R34-N5). 서비스 워커는 앱 껍데기(html·css·js·아이콘)를 캐시해 오프라인에서도 열림(`/api/*` 는 캐시 안 함).

**R33 후속(검수 R33-N1·N4)으로 더한 것** - IndexedDB `voxlog` 판 **2**(판 1 에서 올림, 기존 줄은 `state:"waiting"`):
```
대기열 줄에 state: "waiting" | "failed" 와 mime 이 붙음. 영구 실패(HTTP 400·413·415)는 "failed" 로 옮기고
  flush·sync 가 다시 올리지 않음. 401 은 "waiting" 그대로 lastError "인증 실패" 로 멈춤(지금처럼).
VoxQueue.pending()        -> 위 항목에 state·mime 포함 (failed 도 돌려줌)
VoxQueue.remove(clientId) -> Promise<void>          // 지움 + onchange
VoxQueue.blob(clientId)   -> Promise<Blob|null>     // 내려받기용
VoxQueue.retry(clientId)  -> Promise<void>          // failed → waiting, tries 0, 그리고 flush
// 녹음 중 조각을 기기에 바로 저장(페이지가 죽어도 녹음이 남게). 저장소 `drafts`(keyPath draftId: {draftId, mime, recordedAt, started})
// 와 `chunks`(autoIncrement, 색인 draftId: {draftId, seq, blob})
VoxQueue.draftStart({draftId, mime, recordedAt}) -> Promise<void>
VoxQueue.draftAppend(draftId, blob)              -> Promise<void>   // MediaRecorder.start(5000) 의 조각마다
VoxQueue.draftFinish(draftId, durationMs)        -> Promise<void>   // 조각을 seq 순으로 이어 한 Blob → enqueue(clientId = draftId) → 초안 지움
VoxQueue.draftDiscard(draftId)                   -> Promise<void>
VoxQueue.draftRecover(exceptDraftId?)            -> Promise<number> // 끝나지 않은 초안을 durationMs null 로 draftFinish, 살린 수
VoxQueue.draftSetLocation(draftId, location)     -> Promise<void>   // 녹음 중 위치를 얻으면 초안에 적음(R33-N18) - 살린 녹음도 위치를 가짐
```
**위치정보(요청 수정 2026-11-16 14:03 - '음성파일과 위치정보를 서버로 전송')**:
```
enqueue({..., location}) / draftStart({..., location}) / draftFinish(draftId, durationMs, location?)
  location = {lat: number, lon: number, accuracy: number(m)} | null   (대기열 줄에 그대로 저장, draftFinish 의 인자가 있으면 그것)
올릴 때 머리 X-Location: "<lat>,<lon>,<accuracy>"  (location 이 null 이면 머리 없음; 숫자는 toFixed(6)/정수)
서버: serve.py 가 X-Location 을 읽어 store.add_recording(..., location={"lat","lon","accuracy"}) - 형식이 틀리거나 범위 밖
  (|lat|>90, |lon|>180, accuracy<0) 이면 location None 으로 받고 녹음은 그대로 저장
store 메타에 "location": {"lat","lon","accuracy"} | None (옛 메타엔 없음 → get/list 가 None 으로 채움)
화면: 녹음 시작 때 navigator.geolocation.getCurrentPosition(enableHighAccuracy, timeout 10000, maximumAge 60000),
  설정 '위치 함께 저장'(VoxQueue config saveLocation, 기본 true). 거절·실패·미지원이면 null 로 녹음은 계속.
  상세에 위치(위도·경도·정확도)와 지도 링크 https://www.openstreetmap.org/?mlat=<lat>&mlon=<lon>#map=17/<lat>/<lon>
ask.build_prompt: 녹취 머리에 위치가 있으면 `위치=<lat>,<lon>` 를 덧붙임
```

격리된 출처에서는 draft*/remove/blob/retry 가 reject 또는 0/null. `recordedAt` 은 **지역 시각 + 오프셋 ISO**
(`2026-11-16T08:00:00.000+09:00`) - 서버는 앞 10자를 날짜로 쓰므로 이것이 기기의 날짜가 됨(R33-N2).

`web/manifest.webmanifest`: name "VoxLog", short_name "VoxLog", `start_url: "./?source=launch"`, `display: standalone`,
`launch_handler: {"client_mode": "focus-existing"}`, `shortcuts` 에 "녹음 시작/멈춤" (`./?action=toggle`),
아이콘 192·512(png, maskable 하나 포함) + svg.

`web/api.js` (T-341) → `window.VoxApi`: `VoxApi.json(path, {method, body})` (getConfig 의 token 을 붙임 - 늘 같은 출처, 오류면
Error(서버의 error 글)), `VoxApi.audioUrl(id) -> Promise<blobURL>`.

`web/app.js` (T-341): 화면 전부. 녹음 단추 `#rec`(`aria-pressed`), 대기 수 `#queue-count`, 목록 `#list` 의 항목
`.rec-item[data-id]`, 상태 뱃지 `.status`, 상세 `#detail` 의 글 `#transcript`, 묻기 `#ask-kind`·`#ask-prompt`·`#ask-go`,
답 `#answer`, 설정 `#settings`(토큰·`#auto-record`; 서버 주소 칸은 없음). 끝에서 끝 검사(T-344)가 이 선택자를 씁니다.
