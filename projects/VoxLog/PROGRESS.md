# VoxLog 진행

## 목표

이 프로젝트가 "다 됐다" 고 하려면 있어야 할 것. 검증까지 끝난 것만 체크합니다.
(R33 에서 요청 `Q-261116-fa85` 와 README 를 보고 끝까지 가는 데 필요한 것을 예측해 적었습니다.)

- [x] 프로젝트 뼈대 - README, 인터페이스 문서, `serve.py` 로 열림, `app.json` 으로 모니터에서 목록·묻기
- [x] 녹음 - 큰 단추로 시작·멈춤, 시간 표시, 32kbps, 녹음 중 조각을 기기에 저장해 페이지가 죽어도 살림 (크롬 webm/opus 로 확인)
- [x] 측면 버튼 - 앱 열기 신호(`launchQueue`·`focus-existing`·`?action=toggle`)로 녹음 켜고 끄기 + 바로가기, 기기별 설정 안내 (흉내 검사로 확인, 실물은 아래)
- [x] 올리기 대기열 - IndexedDB 에 먼저 넣고 올림, 같은 녹음 두 번 올라가지 않음(client_id), 영구 실패는 '올리지 못한 녹음' 칸(내려받기·다시·지우기)
- [x] 위치정보 - 녹음 때 위치를 얻어 음성과 함께 서버로 보내 쌓고(`X-Location`), 상세에 지도 링크, 살린 녹음도 위치 유지 (요청 수정 14:03)
- [x] 백그라운드 동기화 - 오프라인 녹음이 연결되면 저절로 올라감(Background Sync, 없으면 online·앱 열기)
- [x] PWA 설치 - 매니페스트·아이콘·서비스 워커, 서버를 내려도 캐시로 앱이 열리고 녹음이 대기열에 남음(브라우저 검사 23, 2026-11-17). 폰에서 연결이 불안정해도 이어질 때 올라가는 것은 태석님 확인
- [x] 받아쓰기 - 서버가 음성을 글로 바꿔 날짜별(기기 지역 날짜) 텍스트 파일로 쌓음, 백엔드 고르기(명령·OpenRouter·없음), 다시 받아쓰기 (가짜 받아쓰기로 확인)
- [x] 조회 - 현황(수·글자·날짜별), 검색·날짜 거르기, 다시 듣기, 글 보기, 지우기
- [x] 묻기 - 요약·핵심어·할 일·직접 묻기를 claude CLI 로(도구·MCP·설정 끔, 빈 임시 폴더), 답을 앱에 보이고 쌓음 (가짜 LLM 으로 확인)
- [x] 보안 - 토큰·HTTPS·경로 탈출·남의 출처·DNS 리바인딩·프롬프트 감쌈, ffmpeg 입력 형식 강제·protocol_whitelist, 업로드 흘려 쓰기·동시 2개·디스크 여유·업로드 전체 마감(408)·저장 OSError 500/507 (R35 에서 R34-N4·N6 닫힘, 하 R35-N1·N2·N3·N4 는 큐)
- [x] 폰(320~430px)·데스크톱에서 겹침·넘침 없음, 어두운 모드
- [x] 검사 - 단위 115·끝에서 끝 브라우저 23/23, 적대적 검수 4회(R33 2회·R34 1회·R35 1회)
- [x] 실제 폰에서 동작 확인 - 태석님이 폰에서 써 보고 "모두 잘됩니다" 라고 확인(2026-11-17). 항목별(측면 버튼·오프라인 올리기·위치 권한·사파리 mp4) 결과는 따로 받지 않음
- [x] 실제 음성인식 백엔드 연결 - KISTI Qwen3-ASR(`VOXLOG_STT_URL`, 화자 구분 `diarized_json`)로 받아쓰기, 태석님이 폰 녹음으로 확인(2026-11-17). 실제 `claude` 묻기는 배포본에서 답 2건 완료(2026-11-16)

## R35 (2026-11-17)

**한 일.** 대기 큐 1건(R34 검수 하 결함 R34-N4·N6 + 저장 OSError, 요청 `Q-261117-r35q`). 그래프 G-076(4노드, 3개 동시 + 검수).
- R34-N6(S4): 업로드 전체 마감 = `UPLOAD_GRACE_S`(30초) + 길이 / `UPLOAD_MIN_RATE`(16KB/s). 넘으면 incoming 을 지우고 **408**을 보냄(400 은 대기열이 영구 실패로 보내므로 쓰지 않음). 조각마다 소켓 timeout 을 남은 시간으로 줄임. `make_server(upload_grace=, upload_min_rate=)` 로 검사가 줄일 수 있음.
- 저장 OSError(S4): incoming 쓰기·`add_recording_file` 의 OSError 가 ENOSPC/EDQUOT 이면 507, 그 밖은 500. 끊긴 쪽에 답할 때 BrokenPipe 트레이스백이 남지 않음.
- R34-N4(S5): 브라우저 검사 22번. 파이썬 소켓 둘로 업로드 자리를 채우고 페이지가 **실제 서버의 503**(Retry-After 5)을 받는 것을 확인함. 줄은 waiting 으로 남고, 자리가 풀리면 저절로 올라감.
- `docs/INTERFACE.md`(S3): 408·500/507 을 적고, 503/507 이 큰 본문에는 연결 오류로 보일 수 있다는 점을 덧붙임.

**바뀐 파일.** `serve.py`, `tests/test_serve.py`, `tests/browser_voxlog.py`, `docs/INTERFACE.md`. 검수 보고는 `rounds/R35/REVIEW-r35.md`.

**검증.** 관리자: `python3 -m unittest discover -s projects/VoxLog/tests` → 115 OK. 엔진 verify·검수: `browser_voxlog.py` → 22/22.
검수(S1)는 /tmp 복사본에서 실제 상수로 느린 연결 실험을 했고(491KB 선언에 1바이트씩 → 60초에 408), 변이 2개(503→400, 대기열이 503 을 영구 실패로)를 22번이 모두 잡음.
판정은 조건부 통과(상0 중0 하4). 하뿐이라 재검수는 하지 않음.

**남은 일.** 큐 `[VoxLog] R35-N1·N2·N3·N4`:
- 마감을 선언 길이로 재므로 50MB 를 선언하면 자리를 최대 54분 쥘 수 있음 → 실제 진척으로도 끊어야 함(N1).
- INTERFACE 의 408 재시도 설명이 코드와 다르고 408 검사가 없음(N2).
- `incoming_path()` 의 mkdir OSError 가 try 밖에 있음(N3).
- 16KB/s 는 느린 폰 회선에서 너무 높을 수 있음. 태석님 판단 거리(N4).

목표에서 체크하지 않은 셋(PWA 오프라인 열림 검사, 실물 폰 확인, 실제 STT·claude 연결)은 그대로.

## R34 (2026-11-16)

**한 일.** 대기 큐 1건(R33 검수 하 결함 N13~N16, 요청 `Q-261116-r34q`). 그래프 G-074(5노드) + 검수 후속 G-075(2노드).
- N13: `Transcriber.busy(rid)`·`resubmit(rid)` 공개 메서드(resubmit 이 잠금 안에서 pending 으로 두고 넣음), serve 의 retry 는 busy 면 409(비공개 `_seen` 안 만짐).
  검수가 찾은 회귀 R34-N1(전사 중 예외 → 메타가 transcribing 에 갇혀 영원히 409)도 고침: 판정은 busy 하나, 전사 예외면 `failed`.
- N14: 업로드를 `incoming/` 에 64KB 씩 흘려 쓰고 `Store.add_recording_file` 이 `os.replace` 로 옮김, 전역 잠금은 rid·메타에만, 동시 업로드 2개 넘으면 503(+Retry-After)·디스크 여유 부족 507,
  시작 때 incoming 찌꺼기 지움, 목록은 (mtime_ns,size) 글 캐시.
- N15: ffmpeg 에 `-protocol_whitelist file,pipe -f <확장자별 형식>` (모르는 확장자는 부르지 않음) - 검수가 실제 ffmpeg 로 concat/HLS 위장 10종 모두 막힘 확인.
- N16: '서버 주소'(apiBase) 설정 삭제, api.js·queue.js·sw.js 는 늘 같은 출처. 대기열은 503/507 을 영구 실패로 보내지 않고 Retry-After(없으면 5초, 최대 60초) 뒤 한 번 다시.
- `docs/INTERFACE.md` 를 이번 수정에 맞춤(R34-N7). 브라우저 검사 21번 거짓 실패(R34-N3) 고침.

**바뀐 파일.** `voxlog/stt.py`, `voxlog/store.py`, `serve.py`, `web/{index.html,app.js,api.js,queue.js,sw.js}`, `docs/INTERFACE.md`,
`tests/{test_stt,test_store,test_serve}.py`, `tests/browser_voxlog.py`(20·21번 추가). 검수 보고 `rounds/R34/REVIEW-r34.md`.

**검증.** `python3 -m unittest discover -s projects/VoxLog/tests` → 104 OK(관리자). `python3 projects/VoxLog/tests/browser_voxlog.py` → 21/21 세 번 연속(T-360 작업자·엔진 verify).
검수(S1)가 /tmp 복사본에서 경쟁 실험 6가지·실제 ffmpeg 위장 파일로 네 결함이 모두 닫혔음을 확인. 판정은 조건부(상0 중0 하7) → 조건 N1·N3 와 N2·N5·N7 고침. 하 결함뿐이라 재검수는 하지 않음.

**남은 일.** 큐 `[VoxLog] R34-N4·N6`(503/507 이 큰 본문엔 연결 오류로 보임·느린 연결이 업로드 자리를 오래 쥠·OSError 를 500/507 로 답하기). 목표에서 체크하지 않은 셋(PWA 오프라인 열림 검사, 실물 폰 확인, 실제 STT·claude 연결)은 그대로.

## R33 (2026-11-16)

**한 일.** 새 프로젝트. 관리자가 README·`docs/INTERFACE.md`(모듈·API·전역 객체 약속)·`app.json` 을 쓰고, 그래프 3개로 만들었습니다.
- G-071(9노드): `voxlog/store.py`(S3) · `voxlog/stt.py`(S6) · `voxlog/ask.py`(S7) · 화면 `web/index.html·style.css·app.js·api.js`(S4) ·
  `web/sw.js·queue.js·manifest.webmanifest·icons/`(S5) → `serve.py`(S5) → 끝에서 끝 브라우저 검사 `tests/browser_voxlog.py`(S4) → 적대적 검수(S1).
- 요청이 14:03 에 고쳐져 **위치정보**가 더해짐(INBOX 로 전달, 관리자가 G-071 을 짤 때 놓침) → G-072 에서 store·대기열·serve·화면·묻기에 반영.
- G-072(6노드): 검수 상1·중7 수정(N1 영구 실패 칸·32kbps, N2 지역 날짜, N3 재시작 뒤 묻기, N4 초안 조각 저장, N5 DNS 리바인딩, N6 claude 맥락 끄기,
  N8 검사 보강) + 위치 + 재검수. G-073(1노드): 재검수의 N18(살린 녹음의 위치)·N19·N20·N12.

**바뀐 파일.** `projects/VoxLog/` 전부 새로: `README.md`, `PROGRESS.md`, `app.json`, `docs/INTERFACE.md`, `serve.py`, `voxlog/{__init__,store,stt,ask}.py`,
`web/{index.html,style.css,app.js,api.js,queue.js,sw.js,manifest.webmanifest}`, `web/icons/*`, `tests/{test_store,test_stt,test_ask,test_serve}.py`,
`tests/{fake_stt,fake_llm}.py`, `tests/browser_voxlog.py`. 검수 보고는 `rounds/R33/REVIEW-r33.md`.

**검증.** `python3 -m unittest discover -s projects/VoxLog/tests` → 77 OK. `python3 projects/VoxLog/tests/browser_voxlog.py` → 19/19
(가짜 마이크·가짜 받아쓰기·가짜 LLM·오프라인→복구·413·새로고침 살리기·Honolulu 시간대·위치·XSS·launchQueue 흉내·폭 320/390/1280·어두운 모드·토큰).
검수자가 복사본에 결함을 넣어 검사가 잡는지 확인(변이 9개 모두 잡음).

**남은 일.**
- 실물: 폰 설치·측면 버튼·위치 권한·사파리, 실제 STT 백엔드(2026-11-16 `settings.json` 으로 KISTI Qwen3-ASR 연결·표본 확인, 폰 녹음은 미확인), 실제 `claude` 묻기 한 번
  (관리자 셸에서는 승인이 필요해 못 돌림 - `--setting-sources ""` 등 플래그가 실제로 받아들여지는지 확인할 것).
- 큐 `[VoxLog] R33-N13·N14·N15·N16`(하). 오프라인에서 앱이 열리는지 검사 추가.
- 폰에서 쓰려면 `serve.py --host 0.0.0.0 --token … --tls-cert … --tls-key …` 와 공유기/프록시 연결(태석님).
