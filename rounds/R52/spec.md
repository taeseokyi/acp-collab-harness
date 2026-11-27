# R52 공통 약속 - 다시 받아쓰기의 지난 글 여러 벌 (판 기록)

요청 `Q-261127-8f71`(태석님 결정: 큐 R51-N8 의 (가)). 관리자 M-R52 가 정함. 모든 노드는 이 약속에 맞춰 쓴다.
R51 의 약속(`rounds/R51/spec.md`) 가운데 '밀려난 글 중 가장 긴 것 한 벌' 만 이것으로 바뀌고 나머지(실패하면 글 그대로,
이름·사람 태그·묻기 답 그대로, AI 태그는 새 글로 다시)는 그대로다.

## 1. 규칙 (store)
- 다시 받아쓰기로 지금 글이 바뀌면, **밀려난 글을 받아쓴 순서대로 목록 끝에 붙인다.** 길이로 고르지 않는다.
- 목록 한 벌 = `{"text": str, "stt_used": dict|None, "at": str|None}`
  - `stt_used` = 그 글이 지금 글이었을 때의 메타 `stt_used` 그대로(옵션 + `at`). 없으면 `None`
  - `at` = 그 글을 받아쓴 때 = `stt_used["at"]`(있으면), 없으면 `None`
- 붙이는 조건은 R51 과 같다: 있던 글(old)이 비어 있지 않고 새 글과 다를 때(`old.strip() != text.strip()` 면 다름).
  같으면 목록을 건드리지 않는다
- **같은 글은 늘리지 않는다**: 붙인 뒤 목록에서 (1) 새 지금 글과 `strip()` 이 같은 벌을 빼고, (2) `strip()` 이 같은
  벌이 여럿이면 가장 뒤(최근) 것 하나만 남긴다
- **상한 `PREV_KEEP = 5`** (`voxlog/store.py` 모듈 상수). 넘으면 앞(가장 오래된 것)부터 버린다
- 받아쓰기 실패(`set_status(... 'failed')`)·빈 결과로 끝난 실패는 `set_transcript` 를 부르지 않으므로 글도 목록도 그대로
- A → B → C 로 받아쓰면 지금 글 C, 목록 [A, B]. 이어서 B 가 다시 나오면 지금 글 B, 목록 [A, C]

## 2. 저장 모양
- 녹음마다 파일 하나: `transcripts/<YYYY-MM-DD>/<id>.prev.json` - 위 벌의 JSON 배열, **오래된 것이 앞**.
  `_atomic_write` 로 쓴다. 날짜 폴더는 지금 글(`<id>.txt`)과 같은 규칙(`_record_date`)
- **옛 자료(R51)**: `.prev.json` 이 없고 `<id>.prev.txt` 가 있어 글이 비어 있지 않으면, 읽을 때 그것을 첫 벌
  `{"text": <그 글>, "stt_used": meta["prev_stt_used"], "at": (prev_stt_used 의 "at") 또는 None}` 로 본다.
  다음에 목록을 쓸 때(`set_transcript` 가 붙일 때) 이 벌을 포함해 `.prev.json` 을 쓰고, `.prev.txt` 를 지우고,
  메타의 `prev_stt_used` 키를 없앤다. 쓰기 전까지 옛 파일은 손대지 않는다
- 깨진 `.prev.json`(JSON 아님·배열 아님)은 빈 목록으로 보고 다음 쓰기에 덮는다. 벌 가운데 `text` 가 문자열이 아닌
  것은 건너뛴다
- `delete(rid)` 는 `.prev.json` 과 `.prev.txt` 를 모두 지운다(날짜 폴더를 모를 때 쓰는 glob 쪽도)

## 3. API
- `Store.get(rid)` 와 `GET /api/recordings/<id>` 는 **`prev_transcripts`**: 위 벌의 배열, **최근 것이 앞**(화면 순서).
  없으면 `[]`
- `transcript_prev`(문자열)와 `prev_stt_used` 는 **없앤다**(get·list 응답에서 모두 뺌, 새 메타에도 안 씀).
  옛 메타에 `prev_stt_used` 가 남아 있어도 응답에는 내지 않는다
- 목록(`list`)·검색(`q`)·현황(`stats`)은 지난 글을 보지 않는다(지금과 같음)
- `serve.py` 는 `store.get` 결과를 그대로 내므로 코드 변경은 없을 수 있다 - 응답 키 검사만 맞춘다

## 4. 화면 (`web/`)
- 상세의 `<details id="detail-prev">` 를 그대로 쓰고, 요약 `#detail-prev-summary` = `지난 글 N벌` (N = 배열 길이).
  배열이 비면 묶음을 숨긴다
- 안에 `<ol id="detail-prev-list">`, 벌마다 `<li class="prev-item">` 안에 `<details>`:
  - `<summary>` = `받아쓴 때 <YYYY-MM-DD HH:MM>` (at 이 없으면 `받아쓴 때 모름`) + ` · ` + 옵션 요약
    (`sttUsedText` 와 같은 낱말: `전처리 denoise · 화자 2 · 자동 추정 켬 · 검토 끔`, 옵션 기록이 없으면 `옵션 기록 없음`)
  - `<pre class="transcript">` = 그 글(`textContent` 로 넣음 - innerHTML 금지)
- 순서는 API 순서(최근 것이 위). 폴링이 다시 그릴 때 **배열 내용이 바뀌지 않았으면 다시 그리지 않는다**(펼쳐 둔 것 유지)
- `#detail-prev-text` 는 없앤다
- 문구 바꿈: 다시 받아쓰기 안내(`index.html` `.stt-why`, `app.js` 토스트)의 `바뀌기 전 글 중 가장 긴 것 한 벌이 남음`
  → `바뀌기 전 글은 '지난 글' 에 5벌까지 남음`
- 지난 글을 지금 글로 되돌리는 단추는 **두지 않는다**(요청이 선택으로 둠, 태그·묻기 답 규칙이 얽혀 범위 밖)
- 폰 320~430px 에서 넘침 없음. `sw.js` 셸 캐시 VERSION +1

## 5. 문서
- `docs/INTERFACE.md`: `.prev.txt` 한 벌·'가장 긴 것' 문장을 모두 이 약속으로(R51-N14 포함), `prev_transcripts`,
  `PREV_KEEP`, 옛 자료 처리. `README.md` 의 같은 문장도

## 6. 지킬 것
- 운영 자료 `projects/VoxLog/data/`·`settings.json` 은 읽지도 쓰지도 않는다. 받아쓰기 서버(운영)에 요청하지 않는다 -
  가짜 받아쓰기(명령 백엔드·`tests/fake_stt.py`)로 검사한다. 배포돼 도는 VoxLog 서버를 건드리지 않는다
- 표준 라이브러리만. 커밋·배포·삭제·설치 없음
