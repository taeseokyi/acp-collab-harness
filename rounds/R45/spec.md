# R45 주보알림 공통 인터페이스 (관리자가 정함 - 두 노드가 이대로 맞춘다)

요청: `.aimem/requests/Q-261124-ba96.json`. 관리 방식 **속도 우선**: 검수 노드 없음, 새 검사 파일 없음, verify 는 "뜬다".
원본 스킬 사본: `projects/주보알림/ref/` (먼저 `ref/README.md`). **ref/ 는 고치지 않는다** - 앱이 그대로 불러 쓴다.
의존성 설치 금지. 표준 라이브러리 + `pdftoppm` + ref 스크립트가 쓰는 오픈클로 conda 파이썬만.

## 폴더

```
projects/주보알림/
  app.json        모니터 '앱 열기'용 (T-410)
  serve.py        HTTP 서버 (T-410)
  bulletin.py     논리 (T-409)
  web/index.html, web/app.js, web/style.css   화면 (T-410)
  data/           실행 중 생기는 것 - state.json, history.json, pdf/, preview/  (git 제외, .gitignore 있음)
  ref/            원본 사본 (읽기만)
```

## bulletin.py (T-409, S2) - 표준 라이브러리만, 모듈 수준에서 네트워크·프로세스 안 띄움

상수
- `ROOT = Path(__file__).resolve().parent`, `DATA = Path(os.environ.get("JUBO_DATA", ROOT / "data"))`
- `REF = ROOT / "ref"`, `CHECK_URL = "https://bstsd.or.kr/a/weekly"`
- `PY`: 환경 `BULLETIN_PY` → 없으면 `/home/tsyi/miniconda3/envs/openclaw/bin/python3` 이 있으면 그것 → 없으면 `sys.executable`
  (ref 의 download.py·pipeline.py 는 requests·bs4·lxml 이 필요해 오픈클로 conda 파이썬으로 돌린다)
- `OPENCLAW_STATE = Path.home() / ".openclaw/workspace/memory/church-bulletin-last.json"` - **읽기만**, 쓰지 않는다

함수 (모두 dict/list 를 돌려주고 예외를 밖으로 던지지 않는다 - 실패는 `ok: False, error: "<까닭 한국어>"`)
- `state() -> dict` - 화면이 한 번에 그리는 것:
  `{"sent": {"date","title","at","source"} | None, "last_check": <check() 결과> | None, "is_new": bool | None,
    "busy": None | "check" | "preview" | "send", "history": [최근 20건, 최신이 앞], "preview": <preview() 결과> | None}`
  - `sent` 가 없으면(첫 실행) `OPENCLAW_STATE` 의 `lastNotifiedBulletinDate` 를 읽어 `{"date": 그 값, "title": "", "at": notifiedAt, "source": "openclaw"}`
    로 씨앗을 심고 `data/state.json` 에 저장한다(파일이 없거나 못 읽으면 None 그대로)
  - `is_new`: `last_check` 가 ok 이고 `sent` 가 있으면 `latest.date > sent.date`, `sent` 가 없으면 True, `last_check` 가 없거나 실패면 None(모름)
- `check() -> dict` - bstsd 목록을 다시 읽는다(urllib, 타임아웃 15초, check_bulletin.py 와 같은 정규식·UA 꼴).
  게시글 주소 `/a/weekly/2026-11-22-연중-제34주일-그리스도왕-대축일` 에서 날짜와 **제목**(날짜 뒤 슬러그를 URL 디코드, `-` → 공백)을 뽑는다.
  돌려주는 값 `{"ok", "at", "latest": {"date","title","url"} | None, "recent": [최근 5개 같은 꼴], "error"}`.
  못 읽거나 날짜가 0개면 `ok: False` 와 까닭 - **새것이라고 꾸미지 않는다.** 결과는 `data/state.json` 의 `last_check` 에 저장
- `preview() -> dict` - 미리 보기 그림을 만든다(전송·Pictures 건드리지 않음):
  `data/pdf/*.pdf`·`data/preview/*.jpg` 를 비우고 → `PY ref/bulletin-pdf-downloader/scripts/download.py --all --download-dir data/pdf --format json`
  (타임아웃 180초) → 받은 PDF 마다 `pdftoppm -jpeg -r 60 <pdf> data/preview/<site>` → 
  `{"ok", "at", "bulletins": [{"site","site_name","date","title","ok","error"}], "images": [{"site","name"}], "error"}`
  (`name` 은 `data/preview/` 안의 파일 이름, 사이트 순서는 pipeline 과 같게 maria 먼저·bstsd 다음, 쪽 번호 순).
  한 사이트라도 실패하면 그 사이트의 `ok: False, error` 를 그대로 싣고, 받은 것은 보여 준다. 결과를 `state.json` 의 `preview` 에 저장
- `send() -> dict` - **지금 쓰는 전송 절차를 그대로**: `PY ref/bulletin-pdf-downloader/scripts/pipeline.py` (인자 없음, 타임아웃 600초,
  stdout+stderr 를 모은다). `ok = (rc == 0)`. 로그에서 `✅ bstsd: (YYYY-MM-DD) - (제목)` 줄로 보낸 주보 날짜·제목을 얻는다
  (없으면 `last_check.latest`). ok 이면 `sent = {"date","title","at": 지금,"source":"app"}` 갱신. 실패면 `reason` 에 로그의 마지막
  `ERROR` 줄(없으면 끝 3줄). 기록 한 건 `{"at","date","title","ok","reason","rc"}` 를 `data/history.json` 앞에 넣고(최대 200건),
  `{"ok","entry","log_tail": 끝 40줄}` 을 돌려준다
- `history(limit=20) -> list`
- 동시에 둘이 돌지 않게 모듈 수준 `threading.Lock` 하나 - 잡혀 있으면 곧장 `{"ok": False, "error": "다른 작업(<busy>) 이 도는 중"}`. `busy` 는 state() 에 보인다
- 파일 쓰기는 `.tmp` 에 쓰고 `os.replace`. `DATA` 는 없으면 만든다

## serve.py (T-410, S3) - 표준 라이브러리 `http.server.ThreadingHTTPServer`

- `python3 serve.py --host 127.0.0.1 --port 18831` (`--host` 기본 127.0.0.1, `--port` 기본 18831). 모니터가 `--host --port` 로 띄운다
- `GET /` → `web/index.html`, `GET /<파일>` → `web/` 안 정적 파일(경로 밖으로 못 나가게)
- `GET /api/state` → `bulletin.state()`
- `POST /api/check` → `bulletin.check()` 뒤 `bulletin.state()` 를 돌려줌 (`{"result": …, "state": …}`)
- `POST /api/preview` → 같은 꼴 (`preview()`), `POST /api/send` → 같은 꼴 (`send()`)
- `GET /api/preview/<name>` → `data/preview/<name>` jpg (이름은 `[A-Za-z0-9_.-]+\.jpg` 만)
- JSON 은 `ensure_ascii=False`, `Cache-Control: no-store`. 오류도 JSON
- 화면은 **상대 경로**로 부른다(`api/state`, `/api/state` 아님) - 모니터가 `/app/주보알림/` 아래로 이어 준다

## 화면 web/ (T-410, S3) - 화면 하나, 한국어, 폰 폭(360px)에서도 한 줄로 안 넘침

- 위: **최신 주보**(날짜·제목, 확인 시각) / **보낸 주보**(날짜·제목·언제, 출처가 openclaw 면 "오픈클로 기록") / 새것 표시
  (`is_new` true → "새 주보 있음" 강조, false → "새 주보 없음", null → "아직 확인 못 함" 과 마지막 오류)
- 단추: **지금 확인**, **미리 보기**, **카톡 보내기**. 도는 동안 단추를 막고 "확인 중…" 처럼 보인다. 확인 실패는 빨갛게 까닭 그대로
- 카톡 보내기는 `confirm()` 한 번("흑석동성당·서울대교구 주보를 카톡으로 보냅니다") 뒤 POST. 결과(성공/실패와 까닭)를 위에 띄우고, 실패 로그 끝을 접어 보이기(`<details>`)
- 미리 보기: 그림을 사이트별로 묶어 가로 스크롤 또는 격자(작게), 누르면 새 창으로 원본 크기
- 보낸 기록 표: 언제 · 어느 주보(날짜·제목) · 성공/실패 · 까닭
- 열 때 `api/state` 한 번. 자동 새로 고침 없음

## 덧붙임 (INBOX 2026-11-24 20:46, 태석님 지시) - 미리 보기 = 실제로 보내는 그림 (G-096)

- `preview()` 의 `images` 는 **pipeline.py 가 실제로 보내는 그림과 같은 쪽·같은 순서**다. 쪽 고르기·순서는 ref `pipeline.py` 의
  `convert_pdfs_to_images()` 를 따른다: maria 는 1~7쪽만 쪽 번호 오름차순, 그다음 bstsd 는 전 쪽을 **쪽 번호 내림차순**.
  전송에 안 가는 쪽(maria 8쪽 이후)의 그림은 `data/preview/` 에서 지운다. 각 항목에 전송 순번 `seq`(1부터, pipeline 의 `01.jpg`… 와 같은 번호)를
  더한다: `{"site","name","seq"}`. 바꾸는 것은 고르기·순서뿐 - pipeline 의 상수(7쪽)는 `ref/` 를 고치지 않고 bulletin.py 에 같은 값으로 두고
  "pipeline.py 의 maria 1~7쪽 규칙과 같아야 한다" 는 주석을 단다
- 화면의 미리 보기는 **카톡 대화방에 그림이 온 것처럼**: 대화방 바탕(옅은 푸른 회색 `#b2c7d9` 꼴), 내가 보낸 쪽(오른쪽)에 그림 묶음 말풍선
  (카톡 사진 묶음처럼 2~3열 격자, 모서리 둥글게), 말풍선 옆에 작은 시각과 장 수. 그림은 `seq` 순서대로. 누르면 새 창 원본.
  위에 "보낼 그림 미리 보기 - 실제 전송과 같은 N장" 한 줄
