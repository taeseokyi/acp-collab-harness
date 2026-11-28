# VoxLog 진행

## 목표

이 프로젝트가 "다 됐다" 고 하려면 있어야 할 것. 검증까지 끝난 것만 체크합니다.
(R33 에서 요청 `Q-261116-fa85` 와 README 를 보고 끝까지 가는 데 필요한 것을 예측해 적었습니다.)

- [x] 프로젝트 뼈대 - README, 인터페이스 문서, `serve.py` 로 열림, `app.json` 으로 모니터에서 목록·묻기
- [x] 녹음 - 큰 단추로 시작·멈춤, 시간 표시, 64kbps(통화용 울림 제거·잡음 억제·자동 음량 조절은 끔), 녹음 중 조각을 기기에 저장해 페이지가 죽어도 살림 - 초안 주인 판정은 웹 잠금(`navigator.locks`, R44), 없으면 되살리기만 꺼짐 (크롬 webm/opus·브라우저 검사로 확인, 폰 실기기 확인 목록은 R44 항목)
- [x] 측면 버튼 - 앱 열기 신호(`launchQueue`·`focus-existing`·`?action=toggle`)로 녹음 켜고 끄기 + 바로가기, 기기별 설정 안내 (흉내 검사로 확인, 실물은 아래)
- [x] 올리기 대기열 - IndexedDB 에 먼저 넣고 올림, 같은 녹음 두 번 올라가지 않음(client_id), 영구 실패는 '올리지 못한 녹음' 칸(내려받기·다시·지우기)
- [x] 위치정보 - 녹음 때 위치를 얻어 음성과 함께 서버로 보내 쌓고(`X-Location`), 상세에 지도 링크, 살린 녹음도 위치 유지 (요청 수정 14:03)
- [x] 백그라운드 동기화 - 오프라인 녹음이 연결되면 저절로 올라감(Background Sync, 없으면 online·앱 열기)
- [x] PWA 설치 - 매니페스트·아이콘·서비스 워커, 서버를 내려도 캐시로 앱이 열리고 녹음이 대기열에 남음(브라우저 검사 23, 2026-11-17). 폰에서 연결이 불안정해도 이어질 때 올라가는 것은 태석님 확인
- [x] 받아쓰기 - 서버가 음성을 글로 바꿔 날짜별(기기 지역 날짜) 텍스트 파일로 쌓음, 백엔드 고르기(명령·OpenRouter·없음), 다시 받아쓰기 (가짜 받아쓰기로 확인)
- [x] 조회 - 현황(수·글자·날짜별), 검색·날짜 거르기, 다시 듣기, 글 보기, 지우기
- [x] 묻기 - 요약·핵심어·할 일·직접 묻기를 claude CLI 로(도구·MCP·설정 끔, 빈 임시 폴더), 답을 앱에 보이고 쌓음 (가짜 LLM 으로 확인)
- [x] 보안 - 토큰·HTTPS·경로 탈출·남의 출처·DNS 리바인딩·프롬프트 감쌈, ffmpeg 입력 형식 강제·protocol_whitelist, 업로드 흘려 쓰기·동시 2개·디스크 여유·업로드 마감(받은 만큼으로 재서 넘기면 408)·저장 OSError 500/507 (R36 에서 R35-N1·N2·N3 닫힘, 하 R36-N1·N2·N3 는 큐)
- [x] 폰(320~430px)·데스크톱에서 겹침·넘침 없음, 어두운 모드
- [x] 검사 - 단위 318·끝에서 끝 브라우저 77/77, 적대적 검수 27회(R33 2회·R34·R35·R36·R39 1회씩·R41 2회·R42 2회·R43 2회·R44·R46·R47 1회씩·R49 2회·R51 3회·R52 2회·R53 3회·R54·R55 1회씩)
- [x] 실제 폰에서 동작 확인 - 태석님이 폰에서 써 보고 "모두 잘됩니다" 라고 확인(2026-11-17). 항목별(측면 버튼·오프라인 올리기·위치 권한·사파리 mp4) 결과는 따로 받지 않음
- [x] 실제 음성인식 백엔드 연결 - KISTI Qwen3-ASR(`VOXLOG_STT_URL`, 화자 구분 `diarized_json`)로 받아쓰기, 태석님이 폰 녹음으로 확인(2026-11-17). 실제 `claude` 묻기는 배포본에서 답 2건 완료(2026-11-16)
- [x] 다음 기능 설계 - 작업자 셋이 써 보고 낸 아이디어 6개·서로의 의견·관리자 확정을 `docs/DESIGN-next-features.md` 에 (R48, 검수 2회 재검수 통과)
- [ ] F1 답의 출처 녹취 - 설계 `docs/DESIGN-next-features.md` F1 절
- [x] F2 녹취 이름·태그(손으로 붙이기, 태그 거르기) + AI 자동 태그(받아쓰기 뒤 바로, 사람이 고친 것은 덮지 않음) - 같은 문서 F2 절 (R49, 가짜 LLM 으로 확인)
- [ ] F3 답 이어 묻기 - 같은 문서 F3 절
- [x] 받아쓰기 옵션 - 전처리·화자 수·문맥 글·자동 추정·LLM 검토를 앱 전체 기본값(설정 칸)과 녹음마다(상세 '옵션 바꿔 다시 받아쓰기')로 고름, 안 고르면 예전과 같은 요청, 쓰인 옵션·이전 글 표시 (R51, 가짜 서버 시험 + 실제 서버에서 안내방송 녹음을 denoise 로 다시 받아써 글이 달라짐을 확인)
- [x] 지난 글 판 기록 - 다시 받아쓰기로 밀려난 글을 받아쓴 순서대로 5벌까지(받아쓴 때·옵션과 함께), 같은 글은 늘리지 않음, R51 의 `.prev.txt` 는 첫 벌로 이어받음, 상세 '지난 글 N벌' (R52, 단위·브라우저 검사)

## R55 (2026-11-28)

요청 `Q-261128-8001`(대기 큐 1번 정리 - R54-N1~N5, R53-N7·N9·N10, R53-N5). 운영 방식 무료 중심·관리 방식 품질 우선. 그래프 G-119 하나(만들기 4·전체 검사 1·검수 1). 도중 태석님이 S6·S2 를 멈춰(opencode go 를 쓰려고) T-497 을 S3 로, T-498 을 새 슬롯 S8(opencode-go deepseek)로 옮김. 목표 체크는 바뀐 것 없음(검사 줄 숫자만).

- **관리자가 정한 것**: R53-N7·N9 는 조사 권고안(`rounds/R54/RESEARCH-stt-defaults.md` 4.1)대로 구현 - 할 일이 분명하고 같은 자리를 네 번째 고치는 일이라 부분 수정 대신 표준 방식으로. R53-N10(15초 넘은 정상 응답 버림)은 알려진 맞바꿈으로 문서에 적고 닫음(닫으려면 지운 캐시를 되살려야 함). R53-N5 는 기록만이라 닫음. R54-N1·N2 는 R54 의 끊긴 T-494 가 이미 파일에 고쳐 둔 것을 T-496 이 되돌림 실패로 확인
- **고침**
  - `voxlog/stt_options.py`(T-496): context 거르기가 외톨이 서로게이트(`Cs`)도 뺌(R54-N3). 태그 글자 범위 `0xE0020 <= ord(ch) <= 0xE007F`(R54-N1)와 8자리 깃발 시험 값(R54-N2)은 되돌리면 시험이 실패함을 확인
  - `web/app.js`(T-497): `state.sttDefaults`·`state.sttDefaultsReq`·`sttDefaults()` 를 없애고 묶음별 `state.sttReads` + `readSttDefaults()`·`abortSttRead()` - 칸을 열 때마다 앞 읽기를 끊고 새로 읽음, 15초 손 타이머·`state.sttSeq` 가드 유지. `saveSttDefaults` 는 저장 중 잠금·걸린 읽기 끊기·저장 중 열기 읽기 안 함(`state.sttSaving`)(R53-N7·N9). `retryWithOptions` 성공 때 칸 닫기는 칸 번호가 같을 때만(R54-N4). app.js 1723→1743줄(조사 추정 −17 과 달리 +20 - `api.js` 가 `AbortError` 를 연결 실패 글로 바꿔 버려 끊김을 `ac` 소유권으로 판별하는 줄이 늘었음). `web/api.js` `json()` 이 `opts.signal` 을 넘김. `sw.js` VERSION 20→21
  - 문서(T-499): `docs/INTERFACE.md`·`README.md` 에 Cs 거르기, AbortController 읽기, 15초 맞바꿈(R53-N10)
  - 검사(T-498): 단위 316→318, 브라우저 73→77 - 쥐는 장치가 끊김을 실제 fetch 처럼 거절·기록, 저장 PUT 쥐기 `STT_SAVE_HOLD_JS`, 67·72 를 abort 방식으로, 새 75(N4)·76(N5 같은 녹음 성공·400 실패)·77(N7 저장 잠금·저장이 읽기를 끊음)·78(N9 다시 열면 새 GET)
- **바뀐 파일**: `voxlog/stt_options.py`, `web/app.js`·`api.js`·`sw.js`, `tests/test_stt_options.py`·`browser_voxlog.py`, `docs/INTERFACE.md`, `README.md`
- **검증**: 노드 verify 모두 1차 rc 0. 작업자가 고친 것마다 되돌려 실패 확인(T-496·T-498 보고). 전체 검사 노드 T-500 단위 318 OK·브라우저 77/77(`rounds/R55/TESTS.md`). 검수 T-501 **통과**(상·중 0, 하 4) - 검수자가 /tmp 사본에서 되돌림 11가지를 돌려 7가지가 검사에 걸림. 관리자 재현: VoxLog 단위 318 OK, 함대 `tools/check.py --all` 1140 OK. 브라우저 77/77 은 엔진 verify·검수자 실행 결과(관리자 셸은 브라우저 검사에 승인 필요)
- **남은 일**: 큐 하 묶음 하나(R55-N1 저장 PUT 에 시간 제한 없음·N2 15초 제한이 fetch 시작 뒤에만·N3 검사가 못 잡는 되돌림·N4 합성 클릭 시험 - `rounds/R55/REVIEW-r55.md`). F1·F3 구현. 운영 VoxLog 서버 재시작(새 코드 반영)은 태석님 쪽

## R53 (2026-11-28)

요청 `Q-261128-22db`(대기 큐의 VoxLog 하 등급 다섯 묶음 정리 - R51·R52 검수). 운영 방식 무료 중심·관리 방식 품질 우선. 관리자가 공통 약속 `rounds/R53/spec.md` 를 정함. 그래프 셋: G-114 만들기 6(무료 S3·S2·S6)·검수 T-481 조건부(중 1 R53-N1) → G-115 N1 고치기·검사·재검수 T-484 조건부(중 1 R53-N6, N1 고침이 만든 것) → G-116 N6 고치기·검사·재검수 2 T-487 **통과**. 목표 체크는 바뀐 것 없음(검사 줄 숫자만).

- **관리자가 정한 것**: R52-N2 중복 제거 (2) 는 지우지 않고 검사로 받침(옛 `.prev.txt` == 지금 글인 녹음을 다시 받아쓸 때 닿음) / R52-N5 지난 글을 따로 받는 API 는 안 만들고, 받아쓰는 중 폴링만 `GET /api/recordings/<id>?prev=0` 로 덜어 냄(`Transcriber._process` 의 `store.get` 은 그대로 - 후속 거리) / R52-N9 옛 done+빈 글과 `(빈 글)` 문구는 그대로(다시 받아쓰기가 복구 길) / R51-N7 둘째 줄(오디오 없는 녹음의 재시도 실패 뒤 옵션이 남음)은 안 고침 - 옵션은 사람이 고른 값 / R53-N1 은 같은 자리 재고침이라 표준 방식(불러오는 동안 칸을 disabled)으로 고침
- **고침**
  - `voxlog/store.py`(T-475): 깨진 `.prev.json` 이면 옛 `.prev.txt` 이어받기 길(R52-N3), `get(rid, with_prev=True)` - False 면 지난 글 안 읽음, True 면 지금 글과 같은 벌 뺌(R52-N4)
  - `serve.py`(T-476): JSON 본문 도우미 `_read_json_body`(RecursionError 포함 400, PUT stt-options·PATCH·retry·ask, R51-N4), `VoxServer.retry_lock` 안에서 busy 검사~옵션 되돌림(R51-N7·N11), `?prev=0`
  - `voxlog/stt.py`(T-476): `EMPTY_TEXT_ERROR` 상수(`받아 적은 글이 비었습니다 - 소리가 없거나 …`)를 두 백엔드가 씀, on_done 앞 군더더기 뺌(R52-N8·N10)
  - `voxlog/stt_options.py`(T-477): context 에서 Cf·Cc(\n·\t 제외) 글자를 뺀 뒤 strip(R51-N5)
  - `web/app.js`(T-478·T-482·T-485): 설정·옵션 칸을 열 때 기본값을 새로 읽음(R51-N6) + 읽는 동안 칸·실행 단추 잠금(R53-N1) + 열 때마다 번호·녹음 이동/닫기 때 풀기·읽기 15초 제한(R53-N6), 재시도 뒤 칸 닫기는 같은 녹음일 때만(R51-N7), 상세 빈 값 이름 `기본(앱 설정 따름)`/`기본(서버 기본)`(R51-N13), 실패 줄 `이전 글 그대로 N자`(R52-N8), 받아쓰는 중 폴링 `?prev=0`·끝나면 전체 한 번 더(R52-N5). `sw.js` VERSION 16→19
  - 문서(T-480): `docs/INTERFACE.md`·`README.md` 에 빈 결과 실패·`?prev=0`·`with_prev`·깨진 `.prev.json`·빈 값 이름·context 거르기·깊은 JSON 400(R52-N7)
  - 검사: 단위 302→314(test_store·test_serve·test_stt·test_stt_options), 브라우저 56→68(t58~t69: 격리 출처·토스트/지난 글 XSS·새 문구·설정 다시 읽기·실패 줄·`?prev=0` 폴링·재시도 중 이동·응답 지연 잠금·이동/실패/시간 제한 풀림), 흔들리던 검사 50 을 응답 지연 주입으로 결정적으로(R51-N12·N15, R52-N6·N10 검사 구멍)
- **바뀐 파일**: `voxlog/store.py`·`stt.py`·`stt_options.py`, `serve.py`, `web/app.js`·`sw.js`, `tests/test_store.py`·`test_serve.py`·`test_stt.py`·`test_stt_options.py`·`browser_voxlog.py`, `docs/INTERFACE.md`, `README.md`
- **검증**: 엔진 verify 노드마다 rc 0(T-475·T-482 은 2차에서). 고친 것마다 작업자가 되돌림 실패를 확인해 보고. 검수 T-481 조건부(중 1) → 재검수 T-484 조건부(중 1) → 재검수 2 T-487 통과(브라우저 68/68·단위 314). 관리자 재현: VoxLog 단위 314 OK, 함대 `tools/check.py --all` 1135 OK. 브라우저 68/68 은 엔진 verify·검수자 실행 결과(관리자 셸은 브라우저 검사에 승인 필요). 변이 사본 실행은 검수 세션에서 /tmp 복사가 막혀 시험 코드를 읽어 판정
- **남은 일**: 큐 하 묶음 하나(R53-N2~N5·N7~N12 - 이모지 ZWJ, 저장 중 잠금, 15초 넘은 응답 버림, 검사 갈래 등). F1·F3 구현. 운영 VoxLog 서버 재시작(새 코드 반영)은 태석님 쪽

## R52 (2026-11-27~28)

요청 `Q-261127-8f71`(다시 받아쓰기의 지난 글을 여러 벌 남기기, 태석님 결정 R51-N8 (가)). 운영 방식 무료 중심·관리 방식 품질 우선. 관리자가 공통 약속 `rounds/R52/spec.md` 를 정함. 그래프 둘: G-112 만들기 4(무료 S3·S6·S3·S2)·검수 T-472(S4) 조건부(중 1) → G-113(followup) N1 고치기(S2)·재검수 T-474(S4) **통과**. 새 목표 '지난 글 판 기록' 을 더하고 체크.

- **관리자가 정한 것**(요청의 '관리자가 정할 것'): 저장은 녹음마다 한 파일 `transcripts/<날짜>/<id>.prev.json`(오래된 것이 앞, 벌 = `{text, stt_used, at}`) / 상한 `PREV_KEEP = 5`, 넘으면 오래된 것부터 버림 / 같은 글(`strip()` 비교)은 새 지금 글과 같은 벌을 빼고 겹치면 최근 것 하나 / 옛 `.prev.txt`+메타 `prev_stt_used` 는 읽을 때 첫 벌로 보이고 다음 쓰기에 `.prev.json` 으로 옮긴 뒤 지움 / API 는 `prev_transcripts`(최근 것이 앞), `transcript_prev`·`prev_stt_used` 는 없앰 / **되돌리기 단추는 두지 않음**(요청이 선택으로 둠, 태그·묻기 답 규칙이 얽힘)
- **한 일**: `voxlog/store.py`(T-468, S3) 판 기록·이어받기·delete 가 둘 다 지움 / `web/`(T-469, S6) 상세 `#detail-prev` 를 `지난 글 N벌` + `#detail-prev-list` 의 `.prev-item`(받아쓴 때·옵션 요약·글, textContent)로, 폴링이 내용이 같으면 다시 안 그림, 안내 문구 두 곳, 셸 캐시 VERSION +1 / 문서(T-470, S3) INTERFACE·README 를 판 기록으로(R51-N14 닫음) / 검사(T-471, S2) test_serve 응답 키, 브라우저 t51 고침·t56(A→B→C 뒤 B·A 와 서로 다른 옵션이 보임, 폴링 뒤 펼침 유지, 320px)·t57(옛 `.prev.txt` 가 지난 글 1벌로) / R52-N1(T-473, S2): api 받아쓰기가 빈 글을 주면 지금 글이 빈 글이 되던 구멍(R51 부터) - `Transcriber._process` 가 공백뿐이면 `failed`('받아 적은 글이 비었습니다')로, 글·지난 글 그대로
- **바뀐 파일**: `voxlog/store.py`·`stt.py`, `web/app.js`·`index.html`·`style.css`·`sw.js`, `tests/test_store.py`·`test_stt.py`·`test_serve.py`·`browser_voxlog.py`, `docs/INTERFACE.md`, `README.md`
- **검증**: 엔진 verify 노드마다 rc 0(T-473 은 1차 verify 의 브라우저 단계 실패 → 2차 통과). 검수 T-472 조건부(중 1 = N1, 변이 표에서 핵심 줄 되돌림은 대부분 잡힘, 중복 제거 (2)·공백만 다른 글은 못 잡음 → 큐) → 재검수 T-474 통과(N1 되돌림 변이가 이제 검사 3개에 걸림). 관리자 재현: VoxLog 단위 302 OK, 함대 `tools/check.py --all` 1135 OK. 브라우저 56/56 은 엔진 verify·검수자 실행 결과(관리자 셸은 브라우저 검사에 승인 필요)
- **남은 일**: 큐 하 묶음 둘(R52-N2~N6: 깨진 `.prev.json` 이 옛 `.prev.txt` 를 가림·큰 글 5벌 응답 크기·검사 구멍 등 / R52-N7~N10: 문서에 '빈 결과는 실패'·실패 줄 옆 옛 글자 수·화면 검사). R51 하 묶음 셋은 그대로(R51-N14 만 닫힘). F1·F3 구현. 운영 VoxLog 서버 재시작(새 코드 반영)은 태석님 쪽 - 재시작 뒤 R51 때 남은 `.prev.txt` 는 다음 다시 받아쓰기에서 `.prev.json` 으로 옮겨짐

## R51 (2026-11-27)

요청 `Q-261127-8d1e`(웹에서 받아쓰기 설정 옵션 바꾸기). 운영 방식 무료 중심·관리 방식 품질 우선. 그래프 넷: G-108 만들기 7(무료 S2·S3·S6)·검수 T-458(S4) → G-109(followup) 중 3 고치기·재검수 T-463 → G-111(followup) 중 2 중 하나 고치기·재검수 2 T-467 **통과**, G-110 실물 확인(S6). 관리자가 공통 약속 `rounds/R51/spec.md` 를 정함. 새 목표 '받아쓰기 옵션' 을 더하고 체크.

- **관리자가 정한 것**(요청의 '관리자가 정할 것'): 옵션 다섯(`preprocess`·`num_speakers`·`context`·`auto`·`review`, min/max·diarize_mode·language 는 안 내놓음) / 단위는 둘 다(전체 기본값 + 녹음마다) / 전체 기본값은 자료 폴더 `stt_options.json`(settings.json 은 손대지 않아 키가 웹으로 나갈 길 없음), 녹음마다는 메타 `stt_options` / 아무것도 안 고르면 필드를 안 보냄 = 예전 요청 / 녹음 옵션이 있으면 그것만 쓰고 앱 설정과 합치지 않음, 빈 옵션 `{}` 는 앱 설정을 따름 / 다시 받아쓰기 뒤처리: 성공하면 새 글, 밀려난 글 중 가장 긴 것 한 벌(`transcript_prev`·`prev_stt_used`), 실패면 글 그대로, 이름·사람 태그·묻기 답 그대로, AI 태그는 지금처럼 새 글로 다시
- **한 일**
  - `voxlog/stt_options.py`(새): normalize(허용 값·1~20 정수·bool 아님·4000자·모르는 키 거절)·form_fields·used_from_result
  - `voxlog/store.py`: `stt_options`·`stt_used`·`prev_stt_used` 필드, `<id>.prev.txt`, set/effective/default 옵션, `set_transcript(used=)`, delete 가 prev 도 지움
  - `voxlog/stt.py`: api 백엔드가 옵션 필드를 보냄, 서버 400 의 `error.message` 를 실패 까닭으로, 결과의 실제 쓰인 값(`stt_used`), `Transcriber(options_fn=)`
  - `serve.py`: `GET/PUT /api/stt-options`(32 KiB), `POST …/retry` 의 선택 본문 `{"options":…}`(받아쓰는 중 409·틀린 값 400 이면 아무것도 안 바뀜), 사람이 누른 재시도는 남은 작업 id(`stt_job`)를 지우고 새로 맡김(R51-N2)
  - `web/`: 설정 칸 `#stt-defaults`, 상세 `옵션 바꿔 다시 받아쓰기`(`#detail-stt`, 실제로 쓰일 값으로 채움, 폴링이 입력을 안 지움), `받아쓴 옵션` 줄, `이전 글 중 가장 긴 것` 묶음, 문맥 글·denoise 주의 문구, 셸 캐시 VERSION +3
  - 문서: `docs/INTERFACE.md`·`README.md`
- **바뀐 파일**: `voxlog/stt_options.py`(새)·`store.py`·`stt.py`, `serve.py`, `web/app.js`·`index.html`·`style.css`·`sw.js`, `tests/test_stt_options.py`(새)·`test_store.py`·`test_stt.py`·`test_serve.py`·`browser_voxlog.py`(t49~t55), `docs/INTERFACE.md`, `README.md`
- **검증**: 엔진 verify 노드마다 rc 0. 검수 T-458 조건부(중 3: 이전 글 한 벌이 연속 재시도에 덮임·남은 작업 id 로 옵션이 무시됨·빈 옵션이 전체 기본값을 덮음) → G-109 → 재검수 T-463 조건부(중 2: N8 '가장 긴 글' 이 좋은 글이 아님·N9 '기본' 의 뜻) → N9 만 G-111 에서 고침 → 재검수 2 T-467 **통과**(상·중 0, 하 3). 첫 검수 변이 22개 중 못 잡던 M9·M16·F3·F5·N2 는 고친 뒤 검사에 걸림(재검수가 시험 코드를 읽어 판정 - /tmp 변이 실행은 재검수 세션에서 막힘). **실물**(T-464, `rounds/R51/REAL-CHECK.md`): 사본 자료 + 포트 18951 서버, 크롬으로 상세 → denoise → 받아쓰기 서버에 1회 → `화자 ?: 아.` 가 `화자 1: 지출한 지출. 응. 이렇게 해요. 네.` 로 바뀜, `받아쓴 옵션: 전처리 denoise · 화자 1 · 자동 추정 켬 · 검토 끔`, 이전 글 묶음 보임. 운영 자료 mtime 그대로. 관리자 재현: VoxLog 단위 293 OK, 함대 `tools/check.py` 644 OK. 브라우저 54/54 는 엔진 verify·검수자 실행 결과(관리자 셸은 승인 필요)
- **남은 일**: 큐 결정거리 **R51-N8**(이전 글을 여러 벌 판 기록으로 둘지 - 같은 자리를 두 번 지적받아 이번엔 갈아엎지 않음, 태석님 결정). 큐 하 묶음 셋(R51-N4~N7, R51-N11·N12, R51-N13~N15). F1·F3 구현. 운영 VoxLog 서버 재시작(새 코드 반영)은 태석님 쪽. 안내방송 녹음은 denoise 로도 내용이 맞지 않음 - 옵션은 수단이지 보장이 아님

## R50 (2026-11-26)

요청 `Q-261126-902f`(대기 큐의 VoxLog 항목 다섯 모두 정리). 운영 방식 무료 중심·관리 방식 속도 우선(검수 노드 없음). 요청이 "고친 것은 검사로 받친다" 고 해서 고친 것에만 검사를 더함(새 검사 t46~t48·단위 1). 그래프 G-107 하나, 무료 슬롯만(S2·S3·S6). 목표 체크는 바뀐 것 없음(검사 줄 숫자만).

- **고침**
  - R49-N5(T-447, S2): `web/app.js` `loadDetail` - 받아쓰기가 막 끝났는데(앞 상태 pending/transcribing → done) `autotag` 가 아직 null 이고 LLM 이 있으면 2초 뒤 한 번 더 읽음
  - R49-N6(T-447): 상세 폴링 오류 뒤 autotag pending 이면 5초 뒤 다시, `loadList` 도 바쁜 상태였으면 오류 뒤 5초 다시(401 은 안 함)
  - R48-N24(T-447): **재현됨 - 결함.** 가짜 마이크 3초 webm 이 고치기 전 상세 `duration` Infinity·올리기 `duration_ms` 없음 → `audioDuration`(Infinity 면 `currentTime` 을 크게 두고 `durationchange` 에서 읽는 널리 쓰는 우회, 5초 상한)을 올리기와 상세 플레이어가 같이 씀 → 2.94초
  - R49-N9(T-447): `tests/test_ask.py` 태그 상한 검사를 `[60]` 으로 박음
  - R49-N11(T-448, S3): `voxlog/store.py` `set_label_tags` - 대소문자만 바뀐 같은 태그면 `tags`·`tags_auto` 표기만 새 것으로, `tags_human` 그대로 + 단위 검사 하나
  - 문서(T-449, S3): `docs/DESIGN-next-features.md` 에 R48-N9~N14·N18·N19·N21·N22 반영(F1·F3 는 구현하지 않고 설계만 - 뒤 구현 요청이 이 문서만 보고 가게, N10 시그니처는 문서 안 INTERFACE 초안에만), R48-N23·N24 결론 줄. `docs/RESEARCH-draft-owner.md` 148행 persisted 단서(R47-N1). `docs/INTERFACE.md` 에 20000자 한도(R49-N7)·casefold/toLowerCase 차이(R49-N8) 한 줄씩
  - 브라우저 검사(T-450, S6): t46(webm 길이 - 상세·올리기·목록), t47(받아쓰기 끝 순간 autotag null 을 `page.route` 로 흉내 → 새로고침 없이 AI 칩), t48(pending 폴링 GET 한 번 abort → 그래도 칩이 뜸). `web/sw.js` 셸 캐시 VERSION 11→12
- **고치지 않고 닫음**
  - R47-N2: 지금 코드에선 안 일어남 - `getConfig` 는 언제나 객체로 풀리고(`web/api.js:8-26`), `fillSettings`·`applyRecSupport` 가 만지는 id 는 모두 `index.html` 에 있으며, `updateQueue`·`checkHealth` 는 안에서 예외를 잡아 Promise 로 돌려줌. 관리자가 코드로 판정
  - R48-N23: 뜻한 동작 - 현황은 거르기와 무관한 전체 요약('총 건수'·'오늘', `Store.stats()` 에 거르기 인자 없음). 거른 결과 수는 목록이 보임
  - R49-N8·N10: 기록만(요청·검수가 '기록만' 으로 둠). N8 은 INTERFACE 에 적음, N10(문장부호 없는 안내 문장이 태그가 되는 것)은 여기 메모로
- **바뀐 파일**: `web/app.js`·`sw.js`, `voxlog/store.py`, `tests/test_ask.py`·`test_store.py`·`browser_voxlog.py`, `docs/DESIGN-next-features.md`·`INTERFACE.md`·`RESEARCH-draft-owner.md`
- **검증**: 엔진 verify 넷 rc 0(코드 노드는 단위+브라우저 전체, 문서 노드는 번호 대조). 관리자 재현: 단위 230 OK. 브라우저 47/47 은 T-450 엔진 verify 결과(관리자 셸에서는 승인이 필요해 돌리지 않음)
- **남은 일**: 큐 0. F1·F3 구현(설계 문서대로 - T-449 보고: 구현 때 실제 `INTERFACE.md` 의 `Asker.submit`·`build_prompt` 시그니처를 맞추고 F1 검사 절의 '이름 바꾼 뒤 옛 답 출처 칩 이름' 검사를 더할 것). 실제 `claude` 로 자동 태그가 달리는지와 webm 길이 고침은 배포본에서 볼 것(배포·운영 서버 재시작은 하지 않음 - 요청대로)

## R49 (2026-11-25)

요청 `Q-261125-76c8`(F2 녹취 이름·태그 구현 + 태석님이 보류를 뒤집은 AI 자동 태그). 운영 방식 무료 중심·관리 방식 품질 우선. 그래프 둘: G-105 만들기(무료 S2·S3·S6)·검수(S4) → G-106 검수 지적 상·중 고치기(무료)·재검수(S4). 관리자가 먼저 공통 약속 `rounds/R49/spec.md` 를 정함(설계 문서와 다르면 이것이 정본). 목표 F2 를 체크(F1·F3 는 남음).

- **관리자가 정한 것**(요청이 맡긴 결정): AI 태그와 사람 태그를 구분해 저장(`tags`·`tags_auto`·`tags_human`·`autotag`), 화면은 한 줄의 칩이고 AI 것은 점선 테두리 + `AI 가 단 태그`. 사람이 태그를 한 번이라도 고치면 그 녹취의 자동 태그(다시 받아쓰기 뒤)는 끝 - 지운 것을 되살리지도 더한 것을 지우지도 않음. 이름만 고치면 자동 태그는 계속. 이미 있는 녹취에는 상세의 `태그 다시 달기`(`POST /api/recordings/<id>/autotag`, 사람 태그는 남기고 AI 태그만 바꿈). 실패는 조용히(상세에 한 줄), 재시작 때 pending → failed
- **한 일**
  - `voxlog/tags.py`(새): 이름·태그 정규화(40자·20자·10개·공백 접기·대소문자 무시 중복), 모델 출력에서 태그 뽑기(글머리·번호·따옴표·쉼표, 사과·머리말 문장 거름, 5개까지)
  - `voxlog/store.py`: meta 다섯 필드(옛 meta 는 읽을 때 기본값), `set_label_tags`(태그가 그대로면 `tags_human` 안 켬)·`set_auto_tags`·`set_autotag`·`autotag_pending_ids`, `list(tag=…)`·`q` 가 이름·태그도 찾고 `match`
  - `voxlog/ask.py`: `build_tag_prompt`(가드·`</녹취>` 이스케이프·20000자), `llm_status`, Asker 를 우선순위 큐로(사용자 묻기 0·태그 1) - 태그 일이 쌓여도 묻기가 먼저, 태그 호출 상한 60초(묻기는 300), 도는 중에 다시 받아쓰기면 끝난 뒤 한 번 더. `voxlog/stt.py`: 글 저장 성공 때만 `on_done`
  - `serve.py`: `PATCH /api/recordings/<id>`(6 KiB·토큰·출처), `POST …/autotag`(LLM 없으면 503·글 없으면 409), `?tag=`, 받아쓰기 → 자동 태그 연결(LLM 이 있을 때만)
  - `web/`: 목록 이름·칩 2개+`+N`·칩 누르면 태그 거르기, 검색칸 `글·이름·태그에서 찾기`, `이름에서 맞음`/`태그에서 맞음`, 상세 이름·태그 편집(쉼표)·저장(바뀐 것만 보냄)·`태그 다시 달기`·자동 태그 상태, 폴링이 쓰던 입력을 지우지 않음, 격리 출처에서 편집 숨김, 셸 캐시 VERSION +1
  - 문서: 설계 문서 F2 절·I3 을 'R49 채택' 으로(보류 까닭과 푼 방법), INTERFACE.md(API·Store·Asker·Transcriber), README 기능 5. 이름·태그. 큐 R48-N10·N11·N12·N20 의 이름·태그 몫 반영
- **바뀐 파일**: `voxlog/tags.py`(새), `voxlog/store.py`·`ask.py`·`stt.py`, `serve.py`, `web/app.js`·`index.html`·`style.css`·`sw.js`, `tests/test_tags.py`(새)·`test_store.py`·`test_ask.py`·`test_stt.py`·`test_serve.py`·`fake_llm.py`·`browser_voxlog.py`(t42~t45), `docs/DESIGN-next-features.md`·`docs/INTERFACE.md`, `README.md`
- **검증**: 엔진 verify(단위·브라우저) 노드마다 rc 0. 검수 T-441(S4) 조건부 - 상 R49-N1(이름만 저장해도 태그를 같이 보내 자동 태그가 끊김)·중 N2(사과 문장이 태그가 됨)·N3(태그 일이 묻기를 300초까지 막음)·N4(도는 중 다시 받아쓰기 무시) → G-106 에서 고치고 되돌리면 실패하는 검사를 작업자가 직접 확인 → 재검수 T-446 **상·중 0**, 하 3, /tmp 사본 변이 9개 중 8개가 검사에 걸림(안 걸린 하나가 R49-N9), 브라우저 44/44. 관리자 재현: VoxLog 단위 229 OK, 함대 `tools/check.py` 530 OK(브라우저 검사는 관리자 셸에서 승인이 필요해 엔진 verify·검수자 실행 결과를 씀). T-445 의 1차 verify 는 기존 녹음 탭 검사(t30·t32 '탭1 녹음이 켜지지 않음')에서 떨어졌다가 코드 변경 없이 2차에서 두 번 통과 - 흔들리는 검사로 봄
- **남은 일**: 큐 R49-N5~N8(하 - 받아쓰기 끝 순간 폴링 멈춤·폴링 오류 뒤 굳음·20000자 한계 문서·casefold 차이), R49-N9~N11(하 - 60초 상한 검사가 항등식, 문장부호 없는 안내 문장, 대소문자만 바꾼 태그 표기). F1·F3 구현. 실제 `claude` 로 자동 태그가 달리는지는 배포본에서 볼 것(배포·운영 서버 재시작은 하지 않음 - 요청대로). 13:45 INBOX 의 kistillm 전환 지시는 13:46 철회되어 반영하지 않음

## R48 (2026-11-25)

요청 `Q-261125-5fa4`(작업자마다 써 보고 아이디어 둘씩 → 관리자 검토·확정 → 설계 문서, 구현 안 함) + 태석님 INBOX 보탬(낸 사람이 아닌 작업자들의 의견 단계, 문서에 아이디어별 의견). 운영 방식 무료 중심·관리 방식 품질 우선. 그래프 넷: G-100 아이디어(S2·S3·S6) → G-101 의견(같은 셋, 자기 것 빼고) → 관리자 확정 → G-102 설계 문서(S2)·검수(S4) → G-103·G-104 지적 반영(S2)·재검수(S4). 새 목표 넷을 덧붙임(설계 하나 체크, 구현 셋 남음).

- **한 일**
  - 써 보기: 슬롯마다 `/tmp/voxlog-r48-S<n>` 사본 서버(가짜 받아쓰기·가짜 LLM)로 녹음·올리기·조회·묻기를 돌림. 운영 서버·`data/` 안 건드림(각 보고에서 `git status` 로 확인)
  - 아이디어 6개(I1~I6, 원문 `rounds/R48/ideas.md`) → 의견 둘씩 → 확정(`rounds/R48/decision.md`): **F1 답의 출처 녹취(I2)·F2 녹취 이름·태그(I1+I3 거르기)·F3 답 이어 묻기(I5 바탕+I4 실 화면)** 채택, **I6 할 일 수집함·I3 자동 태그 제안 보류**
  - 설계 문서 `docs/DESIGN-next-features.md`(391줄): 기능마다 동작·화면·서버와 저장·인터페이스(INTERFACE.md 초안)·검사·구현 노드 나누기, 구현 순서와 다음 라운드 요청 문장 셋, 보류 까닭, 아이디어 전체와 의견(누가 어떤 판정)·슬롯별 순위, 써 보다 본 다른 것, 고친 이력
- **바뀐 파일**: `docs/DESIGN-next-features.md`(새), `PROGRESS.md`. 코드·검사 변경 없음
- **검증**: S4(Sonnet) 적대적 검수 T-428 중 8(PATCH 가 삭제로 가는 라우트 함정, 모니터에 do_PATCH 없음, 출처 계산의 잠금 비용 등) → 반영 T-429 → 재검수 T-430 중 3(무효 id·limit 뜻·고아 자식 판정) → 반영 T-431 → 재검수 2 T-432 **통과**(상·중 0). 관리자가 문서의 의견 절을 의견 원문과 대조. 단위 155 OK
- **남은 일**: 구현은 F1 → F2 → F3 차례로 다음 라운드부터(문서 '구현 순서와 까닭' 의 요청 문장을 그대로 쓰면 됨). 큐 R48-N9~N14·N18~N22(하, 설계 세부 - 구현 요청 때 함께), R48-N23·N24(하, 써 보다 본 것 확인). S3 의 I6 의견은 출력 상한으로 잘려 순위가 없음. 배포는 하지 않음(요청대로)

## R47 (2026-11-25)

요청 `Q-261125-f9f0`(대기 큐 R46-N1·N2). 운영 방식 무료 중심·관리 방식 품질 우선. 그래프 G-099 하나(문서 고치기는 무료 S2, 검수만 유료 S4). 목표 체크는 바뀐 것 없음(코드 변경 없음).

- **한 일**
  - R46-N1(T-419, S2 codex): `docs/INTERFACE.md` draftRecover 절 - 'resume 과 bfcache 복원(pageshow 의 persisted 가 참일 때)에서만 다시 건다, 첫 로드 회수는 app.js init' 으로. `docs/RESEARCH-draft-owner.md` 요약(7)·§4.2(A)(74)·§6(172)에 같은 단서, 고친 이력 한 줄
  - R46-N2: **추정이 틀려 고치지 않음.** `api().getConfig()` 는 거절되지 않는다 - `web/api.js:8-26` 이 동기 예외를 try/catch, 비동기 거절을 `then(ok, fail)` 로 삼키고, `web/queue.js:99-109` 도 `catch` 로 memConfig 를 돌려줌. 관리자가 코드로 판정하고 S4 검수가 따로 같은 결론
- **바뀐 파일**: `docs/INTERFACE.md`(+2/−1), `docs/RESEARCH-draft-owner.md`(+4/−3). 코드·검사 변경 없음
- **검증**: T-419 엔진 verify rc 0(옛 문장 없음·persisted 단서·이력). S4(Sonnet) 적대적 검수 T-420 - 상·중 0, 하 2. 관리자 재현: 단위 155 OK(문서만 바뀌어 브라우저 검사는 돌리지 않음), 함대 전체 1128 OK·린터 OK
- **남은 일**: 큐 R47-N1·N2(하) - `docs/RESEARCH-draft-owner.md:148` (f) 검사 항목에 persisted 단서가 빠짐, init 의 첫 로드 회수·initOpen 이 getConfig.then 안의 앞선 동기 호출(fillSettings 등)이 던지지 않아야만 돎(추정, 지금 코드에선 안 일어남). 배포는 하지 않음(요청대로)

## R46 (2026-11-24)

요청 `Q-261124-f310`(대기 큐 VoxLog 둘: R43-N5, R44-N1~N3). 운영 방식 무료 중심·관리 방식 품질 우선. 그래프 G-098 하나(만들기는 무료 S2·S3, 검수만 유료 S4). 목표 체크는 바뀐 것 없음(검사 줄만 갱신).

- **한 일**
  - R43-N5(T-416, S2 codex): `tests/test_serve_ask_body.py` 에 `_read_body` 분기별 검사 둘 - `test_zero_grace_whole_body_gets_400`(`body_grace=0` → `left <= 0` 분기), `test_short_body_write_closed_gets_400_before_grace`(짧은 본문+쓰기 닫음 → `got != length` 분기, GRACE/2 안에 답)
  - R44-N2(T-416): `docs/RESEARCH-draft-owner.md:147` 옛 계획 문장을 R44 실제 결정(t30 = 웹 잠금 없는 탭 검사)으로
  - R44-N1(T-417, S3 opencode): `web/app.js` startRec 에서 `mr.start(5000)` 를 try/catch - 실패면 rc.finished·state.rc/rec 비움·마이크 끔·`rc.chain` 뒤에 draftOk 일 때만 `draftDiscard`(잠금 놓음)·토스트 '녹음을 시작하지 못했습니다.'
  - R44-N3(T-417): `web/queue.js` 의 pageshow 회수는 `ev.persisted`(bfcache 복원)일 때만 - 첫 로드 회수는 app.js init 한 곳. `resume` 은 그대로
  - 새 브라우저 검사 t39(녹음 시작 실패 때 초안·잠금 정리·다시 녹음 가능), t40(pageshow 는 persisted 일 때만 회수)
- **바뀐 파일**: `tests/test_serve_ask_body.py`(+41), `docs/RESEARCH-draft-owner.md`(1줄), `web/app.js`(+14/−1), `web/queue.js`(2줄), `tests/browser_voxlog.py`(+77/−1)
- **검증**: 엔진 verify 셋 rc 0. S4(Sonnet) 적대적 검수 T-418 **통과**(상·중 0, 하 2) - /tmp 사본 변이 4/4 가 의도한 검사 하나씩에만 걸림(serve.py 362·382행 400→500, app.js catch 의 draftDiscard 삭제, queue.js persisted 조건 삭제). 관리자 재현: 단위 155 OK·브라우저 40/40
- **남은 일**: 큐 R46-N1·N2(하) - `docs/INTERFACE.md:240` 등의 'resume·pageshow 에서 회수' 서술이 낡음, init 의 첫 로드 회수가 getConfig 성공 뒤에만 돌아 getConfig 거절 때 그 방문엔 회수 없음(추정, 소실 없음). 배포는 하지 않음(요청대로)

## R44 (2026-11-24)

요청 `Q-261124-b4ad`(녹음 초안의 주인 판정을 웹 잠금으로 바꾸기, 태석님 승인). 운영 방식 무료 중심. 그래프 G-094 하나. 목표 체크는 바뀐 것 없음(녹음·검사 줄만 갱신).

- **한 일**
  - 공통 약속 `rounds/R44/spec.md` 를 관리자가 먼저 정하고 파일별로 나눔
  - `web/queue.js`(T-403): 옛 장치(tabId·BroadcastChannel `voxlog-drafts`·draftPings·liveDraftIds·DRAFT_LEASE_MS 판정·draftTouch, 조각마다 aliveAt 갱신) 삭제. 초안마다 `voxlog-draft-<id>` 배타 잠금 - `draftStart` 가 잠금을 얻은 **뒤에** 초안 줄을 넣고 `Promise<boolean>`, `draftFinish`·`draftDiscard` 가 끝에 놓음. `draftRecover`: `ifAvailable` 즉시 판정 + 주인이 쥔 새 세대 초안엔 AbortController 기다리는 요청(R41-N13), freeze/pagehide 에 abort·resume/pageshow 에 다시 걸기, `onrecover` 알림. 조각 0개 초안은 `false`(R41-N16). `supported().draftLocks`. 웹 잠금이 없으면 초안을 만들지 않음(녹음·올리기는 그대로)
  - 전환기(R43-N6, 더 단순한 쪽): 새 초안은 `lock: true` 세대 표식 + `aliveAt: Infinity`(이미 열린 구버전 탭의 20초 필터가 영영 건너뜀). 20초 신선도 규칙(`OLD_DRAFT_FRESH_MS`)은 표식 없는 구세대 초안에만, 구세대엔 기다리는 요청 없음. heartbeat 를 남기지 않음
  - `web/app.js`(T-404): `rc.touchTimer`·5초 draftTouch·init 22초 재시도 삭제(R41-N15), draftOk 는 draftStart 의 true 일 때만, 메모리 조각으로 올리는 두 길 모두 enqueue 뒤 `draftDiscard`(R41-N18), `onrecover` 토스트
  - `tests/browser_voxlog.py`(T-405): t30 을 '웹 잠금 없는 탭' 으로 교체, 새 t32~t38(닫힌 녹음 탭의 초안을 기다리던 탭이 회수·새로고침 회수 22초 없이·0개 초안·draftAppend 실패 뒤 정리·구세대 20초 규칙·lock/Infinity 표식과 held 잠금·freeze/resume 로 대기 요청 abort/재등록)
  - 문서: README(기능 6 '끊긴 녹음 되살리기'·열화 절)·`docs/INTERFACE.md` 초안 절(T-406), `docs/RESEARCH-draft-owner.md` 에 구현 결정·R43-N6~N8 반영(T-407, S6). R43 항목의 '없는 브라우저는 lease+BroadcastChannel 로 열화' 권고는 이 결정으로 대체됨
- **걷어낸 양**: `git diff --numstat` - queue.js −89/+165, app.js −20/+23 (web/ 합계 −109/+188). 옛 장치는 남지 않음(검수 (5) 확인). 줄 수가 늘어난 것은 기다리는 요청·페이지 수명 처리·주석 때문
- **바뀐 파일**: `web/queue.js`, `web/app.js`, `tests/browser_voxlog.py`, `README.md`, `docs/INTERFACE.md`, `docs/RESEARCH-draft-owner.md`. `sw.js` 는 변경 없음
- **검증**: 엔진 verify(T-405 `python3 projects/VoxLog/tests/browser_voxlog.py` rc 0), 검수자 재실행 브라우저 38/38·단위 153 OK, 관리자 단위 153 OK. S4(Sonnet) 적대적 검수 T-408 **통과**(상·중 0, 하 3) - /tmp 사본 변이 6/6 잡힘(0개→true·draftDiscard 삭제·기다리는 요청 삭제·freeze abort 삭제·구세대 20초 규칙 삭제·Infinity→Date.now())
- **실제 기기에서 볼 것**(함대는 못 함, 조사 문서 §6): 녹음 탭을 닫거나 앱을 스와이프로 죽였을 때 다른 탭/다음 방문이 바로 살리는가, 녹음 중 새로고침 뒤 바로 살아나는가, 화면을 끄거나 다른 앱으로 오래 갔다 돌아왔을 때 녹음이 빼앗기지 않는가, iOS 사파리에서 백그라운드·탭 종료 때 잠금이 풀리는가, bfcache·freeze 뒤 잠금 유지와 pageshow 동작, 넘겨받은 직후 얼어붙은 대기 탭, MediaRecorder 가 백그라운드에서 계속 녹음하는가
- **남은 일**: 큐 R44-N1~N3(하 - mr.start 예외 때 잠금 누수(추정), 조사 문서 147행 옛 문장, 첫 로드 토스트 순서(추정)), 큐 R43-N5(하, 검사 강도)

## R43 (2026-11-24)

요청 `Q-261124-795c`(조사만, 구현 안 함) + 대기 큐 R42-N2·R42-N3. 운영 방식 무료 중심. 목표 체크는 바뀐 것 없음(검사 수만 갱신).

- **한 일**
  - 조사 문서 `docs/RESEARCH-draft-owner.md`(S2 codex 가 MDN·규격·BCD·Page Lifecycle·bfcache 를 직접 받아 읽고 씀, T-397 → 검수 반영 T-401). 권고: **Web Locks API(`navigator.locks`) 배타 잠금으로 바꿀 만함** - 녹음 탭이 `voxlog-draft-<id>` 를 쥐고, 다른 탭은 `ifAvailable` 로 즉시 판정 + AbortSignal 단 대기 요청(freeze/pagehide 에서 abort), 없는 브라우저는 지금의 aliveAt lease+BroadcastChannel 로 열화. 지원: Chrome/Android 69·Firefox 96·Safari(iOS 포함) 15.4·Edge 79(추정), HTTPS 필요, 워커에서도 됨. 맞바꿈: 얼어 있는 녹음 탭의 초안은 그 탭이 풀리거나 버려질 때까지 회수 안 됨
  - R42-N2: `voxlog/store.py` `set_job` 이 작업 id 를 64자로 자르던 것을 없앰(유일한 호출 전에 `stt._job_id_ok` 가 1~128자로 검증) + `tests/test_store.py` 128자 검사 (T-398)
  - R42-N3: `tests/test_serve_ask_body.py` - setUp 에서 실제 녹음을 만들어 유효한 ids, 400 은 까닭 문구('본문이 중간에 끊겼습니다')까지 확인, 마감 안 느린 본문은 202 → `/api/answers/{id}` done·'가짜 답', 시작부터 합계가 마감을 넘는 느린 본문 → 400 (유휴 기준 변이를 직접 잡음) (T-399)
- **바뀐 파일**: `docs/RESEARCH-draft-owner.md`(새), `voxlog/store.py`, `tests/test_store.py`, `tests/test_serve_ask_body.py`
- **검증**: 단위 153 OK. S4(Sonnet) 적대적 검수 T-400 - 문서는 공식 문서와 대조해 조건부 통과(R43-N1~N4), 큐 수정 합격(/tmp 사본 변이: 옛 `[:64]`·유휴 기준 마감 모두 잡힘, CPU 부하 6회 흔들림 없음). 재검수 T-402 조건부 통과(N1·N3·N4 통과)
- **남은 일**
  - 큐 R43-N6(중)·N7·N8(하): 문서 §4.4 전환기 규칙(aliveAt 이 신선하면 잠금을 얻어도 안 건드림)이 새 코드끼리의 즉시 회수·22초 재시도 제거와 모순 - 초안에 세대 표식을 두는 쪽이 유력. **구현 요청 때 함께 정할 것**
  - 큐 R41-N13~N18(초안 회수): 조사 문서 §5.5 표에 새 방식에서 각각 어떻게 되는지 있음. 태석님이 문서를 보고 승인하면 구현 요청을 따로
  - 큐 R43-N5(하): ask 본문 검사가 `_read_body` 의 경쟁 분기 두 곳 변이를 못 잡음(실제 결함 아님)

## R42 (2026-11-24)

**한 일.** 요청 `Q-261124-e24b`(대기 큐 VoxLog 4건을 S6 에 - 종류별 기본 1차 지시 첫 실물 시험). 그래프 G-088(S6 노드) → G-089(S3 검수) → G-090(S2 수정) → G-091(S3 재검수).
- T-390(S6) R41-N1: `voxlog/stt.py` 작업 id 규칙을 `isalnum` → 1~128자 `[A-Za-z0-9._-]`(`.`·`..` 거절)로 완화. R41-N5: `serve.py` `_read_body` 가 POST /api/ask 본문을 마감(`BODY_GRACE_S` 30초, `make_server(body_grace=…)`) 안에 다 받지 못하면 400 `본문이 중간에 끊겼습니다`
- T-391(S6) R41-N13~N18 초안 회수 - **되돌림.** 태석님이 초안 판정 방식(시각 갱신·만료·BroadcastChannel)을 웹 잠금(`navigator.locks`)으로 바꾸기로 해, 클로드 코드가 web/ 네 파일을 R41 끝(d094881) 상태로 돌림(31/31). 큐 2번에 비고
- T-392(S6) 검사 13개: 검색 계약(R41-N2)·recordings status·limit(N3)·running 답 DELETE 409(N6)·health llm 참(N7)·ask ids 1~200(N11). 변이 9/9 잡힘
- T-393(S6) `docs/INTERFACE.md` 를 코드에 맞춤(R41-N4·N8~N12, limit 규칙, stt id, ask 본문 400). 초안 회수(R41-N15)는 방식이 바뀌어 일부러 안 적음
- T-394(S3) 적대적 검수 조건부 통과(/tmp 사본 변이 10/10): 중 1(ask 본문 마감 설명이 '조용하면' 인데 코드는 절대 마감) → T-395(S2) 설명 네 곳과 INTERFACE.md 를 절대 마감으로, 느린 본문 검사 추가 → T-396(S3) 재검수 **통과**(남은 하 1 = R42-N3 큐)

**바뀐 파일.** `serve.py`, `voxlog/stt.py`, `docs/INTERFACE.md`, `tests/test_stt.py`, `tests/test_store.py`, `tests/test_serve.py`, `tests/test_ask.py`, 새 `tests/test_serve_ask_body.py`. web/ 는 변경 없음(되돌림).

**검증.** 관리자 `python3 -m unittest discover -s projects/VoxLog/tests` → 151 OK. 검수자 /tmp 사본 변이 10/10·재검수 유휴 기반 변이 잡힘, 느린 본문 검사 15회 반복 OK.

**남은 일.** 큐 `[VoxLog]`: R41-N13~N18(초안 회수 - 웹 잠금으로 바꾸기, 조사 먼저·구현은 태석님 승인 뒤), R42-N2(store.py:450 id 64자 자름 vs 규칙 128자, 선행), R42-N3(느린 본문 검사가 400 까닭을 안 봄).

## R41 (2026-11-24)

**한 일.** 요청 `Q-261124-9281`(새 보내기 방식으로 S6 세션 풀림 이어 가기 시험, 대기 큐 VoxLog 4건). 그래프 G-083(S6 셋) → G-084·G-085(검수) → G-086(수정) → G-087(재검수).
- T-382(S6) INTERFACE.md ↔ serve.py·voxlog/·tests/ 대조 검수: 중 3·하 9(R41-N1~N12, 코드는 고치지 않음, 큐로)
- T-383(S6) R39-N1(날짜 정규식+fromisoformat 둘 다)·R39-N2(astimezone OverflowError → 서버 시각)·R39-N4(health `llm_error`, ask 400 조건 문서)
- T-384(S6) R40-N1(녹음 중인 초안을 다른 탭이 안 가져감)·R40-N2(flush 진행 중 넣은 녹음도 올림, `flushAgain`)·R40-N3(api.js: 본문이 JSON 아니면 오류)
- T-386(S2) 적대적 검수 **불합격**: R40-N1 이 BroadcastChannel 없음/300ms 무응답 탭에서 남음, 업로드가 200 비-JSON 을 성공으로 받아 녹음을 지움
- T-387(S2) 수정: 초안 lease(`aliveAt`, 20초, 녹음 중 5초마다 갱신, 시작 22초 뒤 한 번 더 회수), 업로드 성공은 JSON + 문자열 `id` 일 때만(queue.js·sw.js), sw VERSION 10
- T-388(S3) 재검수 **조건부 통과**: 두 결함 닫힘, 남은 중 1·하 5(R41-N13~N18) 큐로

**바뀐 파일.** `serve.py`, `docs/INTERFACE.md`, `tests/test_serve.py`, `web/app.js`, `web/queue.js`, `web/api.js`, `web/sw.js`, `tests/browser_voxlog.py`. 검수 기록 `rounds/R41/REVIEW-r41-s6.md`.

**검증.** 관리자 `python3 -m unittest discover -s projects/VoxLog/tests` → 137 OK. 엔진 verify 로 `browser_voxlog.py` 29/29(T-384)·31/31(T-387), 재검수가 31/31 다시 돌림. 검수자 변이 시험(되돌리면 새 검사가 실패).

**남은 일.** 큐 `[VoxLog]` 넷: R41-N13~N18(초안 회수 남은 경쟁, 중1), R41-N1·N5(stt id 규칙·ask 본문 timeout, 중1), R41-N2·N3·N6·N7(검사 빈틈, 중2), R41-N4·N8~N12(INTERFACE 문서 맞추기).
목표 체크는 그대로(새 발견은 이미 검증된 목표의 빈틈 - 되돌리지 않음).

## R40 (2026-11-23)

**한 일.** 요청 `Q-261123-7d3e`(freebuff 슬롯 S6 세션 풀림 이어 가기 시험, 읽기 전용 검수 2건). 그래프 G-082. 코드는 고치지 않음.
- T-380 화면 쪽 검수(web/ 6파일) - S6 done, 26분. **중 1·하 2**: R40-N1(중) 녹음 중에 같은 주소로 새 탭을 열면
  `draftRecover` 가 그 초안을 가져가 마감하고, 원래 탭은 멈출 때 녹음을 잃으면서 '저장됨' 을 띄움(app.js:1060, queue.js:376-405).
  R40-N2(하) 올리는 중 끝난 녹음이 sync 없는 브라우저에서 다시 안 올라감(queue.js:180·278). R40-N3(하) 200 인데 JSON 이
  아닌 응답을 빈 성공으로 받아 '연결됨 0건'(api.js:67). md.js 삽입 위험은 없음을 확인
- T-381 검사·문서 대조 검수 - 엔진 결함으로 blocked(작업 지시가 나가기 전에 끊김), 일은 큐로

**바뀐 파일.** 없음(기록은 `rounds/R40/REVIEW-r40-s6.md`).

**검증.** S6 가 /tmp 복사본 서버+크롬으로 세 발견을 직접 재현. 관리자 `python3 -m unittest discover -s tests` → 136 OK, 프로젝트 트리 변경 없음.

**남은 일.** 큐 `[VoxLog]`: R39-N1·N2·N4(하), R40-N1(중), R40-N2·N3(하), R40 노드 2(INTERFACE ↔ 코드·검사 대조 검수).
목표 체크는 그대로(새 발견은 '올리기 대기열'·'조회' 의 빈틈이지만 이미 검증된 목표를 되돌리지는 않음 - R40-N1 을 고치면 브라우저 검사에 시나리오 추가).

## R39 (2026-11-23)

**한 일.** 요청 `Q-261123-6bf6`(대기 큐 7건을 모두 freebuff 슬롯 S6 에 맡기는 시험 라운드) 중 VoxLog 3건. 그래프 G-080, 셋 다 시도 1.
- T-372 **R38-N1(상)**: `_api` 가 HEAD→GET 바꿈을 처리 함수 고르기보다 먼저 함. HEAD 는 아무것도 지우거나 만들지 않음.
  출처 검사는 바꾸지 않는 메서드(GET·HEAD·OPTIONS) 말고 모두(PUT·PATCH 포함)에 걸림
- T-373 R38-N2·N3·N6: `/api/ask` 의 kind 가 문자열이 아니면 400 JSON. LLM 명령 설정이 깨져도 `/api/health` 는 200(`llm_error` 칸). retry 도중 삭제는 404 JSON
- T-374 R38-N4·N5: `X-Recorded-At` 은 시간대가 붙은 실제 시각이고 하루 넘게 미래가 아닐 때만 씀, 아니면 서버 시각으로 받음(업로드는 201 그대로).
  `?from=`·`?to=` 가 실제 날짜가 아니면 400. 프롬프트는 실제 시각 순으로 정렬
- S1 적대적 검수(T-379): **조건부 통과, 상 0·중 0·하 4**. R38-N1~N6 모두 닫힘. 기록은 `rounds/R39/REVIEW-r39.md`

**바뀐 파일.** `serve.py`, `voxlog/ask.py`, `docs/INTERFACE.md`, `tests/test_serve.py`, `tests/test_ask.py`.

**검증.** 관리자 `python3 -m unittest discover -s tests` → 136 OK. S1 검수가 `browser_voxlog.py` 26/26, 변이 시험 16개, 실제 서버에 HEAD(Origin 있음·없음)를 보내 녹음이 남는 것을 확인함.

**남은 일.** 큐 `[VoxLog] R39-N1·N2·N4`(모두 하):
- R39-N1: T-374 가 날짜 정규식을 지워 `from=20261123`·`2026-W48-1` 이 400 대신 200(회귀). 정규식과 `fromisoformat` 을 둘 다 검사
- R39-N2: `X-Recorded-At: 0001-01-01T00:00:00+14:00` 이면 OverflowError 로 업로드가 끊김
- R39-N4: INTERFACE.md 의 health 행에 `llm_error` 빠짐

## R38 (2026-11-23)

**한 일.** 시험 라운드(요청 `Q-261123-018e`, freebuff 슬롯 S6 가 세션이 도중에 끝나도 이어 가는지 보기). 일감은 서버 쪽 파이썬
(`serve.py`·`voxlog/store.py`·`stt.py`·`ask.py`) 읽기 전용 검수 하나(T-371, 그래프 G-079). **코드는 고치지 않음**(요청대로).
S6 는 37분 동안 한 번에 끝냄. 세션은 도중에 끝나지 않아 이어 보내기는 일어나지 않음.

**바뀐 파일.** 프로젝트 코드 없음. 검수 기록 `rounds/R38/REVIEW-r38-s6.md`(답 전문은 `.aimem/sessions/T-371-S6-a1-165155/report.md`).

**검증.** S6 와 관리자 모두 `python3 -m unittest discover -s tests` → 123 OK. 관리자는 R38-N1·N2 를 코드에서 행 단위로 확인함.

**남은 일.** 큐 `[VoxLog]` 3건:
- **R38-N1(상)**: `HEAD /api/recordings/<id>` 가 녹음을 지움(`serve.py:238·252`). 토큰이 없는 서버면 남의 사이트도 지울 수 있음. **먼저 고칠 것.**
- R38-N2(중)·N3·N6(하): `/api/ask` 의 kind 타입, `/api/health` 의 LLM 명령 해석, retry 도중 삭제. 셋 다 JSON 오류 대신 연결이 끊김.
- R38-N4·N5(하): `X-Recorded-At`·날짜 범위 검사 없음, 프롬프트 정렬이 문자열 순서.
- 참고: R36-N1·N2·N3 은 REV 190(2026-11-17)에서 이미 닫혔고 큐에 없음. 그런데 이번 S6 지시문은 이 셋을 아직 큐에 있는 것으로 적었음(관리자 실수, 검수에는 영향 없음).

목표 '보안'·'검사' 는 체크된 채로 둠. 다만 R38-N1 이 닫히기 전에는 사실상 열린 상태임.

## R36 (2026-11-17)

**한 일.** 대기 큐 1건(R35 검수의 하 결함 R35-N1·N2·N3, 요청 `Q-261117-r36q`). 그래프는 G-077(4노드)로, 구현 3개를 동시에 돌리고 검수 1개를 마지막에 둠. 모든 노드가 시도 1번에 끝남.
- R35-N1(S4): 업로드 마감을 매 바퀴 `시작 + UPLOAD_GRACE_S + 받은 바이트 / UPLOAD_MIN_RATE` 로 다시 셈(선언 길이는 쓰지 않음). 50MB 를 선언하고 1B/s 로 보내면 31초에 408. 상수(30초, 16KB/s)는 그대로임(R35-N4 는 태석님 결정으로 닫힘).
- R35-N3(S4): `store.incoming_path()` 를 try 안으로 옮김. mkdir 이 ENOSPC/EDQUOT 이면 507, 그 밖이면 500 으로 답함. `_unlink(None)` 은 아무것도 하지 않음.
- R35-N2(S5): 코드를 문서에 맞춤. `queue.js`·`sw.js` 가 408 도 5xx 처럼 waiting 으로 두고 Retry-After 뒤 다시 시도함(sw 는 throw). sw `VERSION` 은 6→7. 브라우저 검사 24번을 더함(route 로 첫 업로드에만 408 → 저절로 다시 올라감).
- `docs/INTERFACE.md`(S3): 새 마감 공식, 408 재시도, mkdir 오류를 적음.

**바뀐 파일.** `serve.py`, `tests/test_serve.py`(단위 4개 추가), `web/queue.js`, `web/sw.js`, `tests/browser_voxlog.py`(24번), `docs/INTERFACE.md`. 검수 보고는 `rounds/R36/REVIEW-r36.md`.

**검증.** 관리자: `python3 -m unittest discover -s projects/VoxLog/tests` → 119 OK. 엔진 verify·검수: `browser_voxlog.py` → 24/24.
검수(S1)는 /tmp 복사본에서 실제 상수로 실험함. 경계값(12KB/s → 120초, 8KB/s → 60초)이 공식과 1초 안으로 맞았고, 진짜 EACCES → 500, ENOSPC/EDQUOT → 507 이 나왔으며 트레이스백은 없었음.
변이 M1~M4 는 새 검사가 모두 잡음. 판정은 **통과(상0 중0 하3)**.

**남은 일.** 큐 `[VoxLog] R36-N1·N2·N3`(모두 하):
- sw.js 의 408·5xx 재시도 조건을 지키는 검사가 없음. queue.js 와 같은지 비교하는 단위 검사를 더해야 함(N1).
- INTERFACE.md 155행 제목과 164~165행 요약이 옛 내용임(N2).
- 60초 넘게 멈춘 업로드가 408 이 아니라 400(영구 실패)으로 답함. 전부터 있던 문제임(N3).

참고로 새 공식에서는 16KB/s 보다 느린 회선이 크기와 상관없이 `30·16/(16−r)` 초 뒤에 끊김(12KB/s 면 약 1.4MB 까지 올라감).

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
