# R53 약속 - VoxLog 대기 큐 하 등급 다섯 묶음 (관리자 M-R53)

요청 `Q-261128-22db`. 모든 노드의 공통 약속. 검수 원문: `rounds/R51/REVIEW-r51.md`·`REVIEW-r51-2.md`·`REVIEW-r51-3.md`,
`rounds/R52/REVIEW-r52.md`·`REVIEW-r52-2.md`. 배포(운영 서버 재시작) 없음. 운영 자료 `data/`·`settings.json` 은 읽지도 쓰지도 않는다.

## 인터페이스 (노드끼리 맞추는 것)

1. `Store.get(rid, with_prev=True)` - `with_prev=False` 면 응답에 `prev_transcripts` 키 자체가 없고 `.prev.json`·`.prev.txt` 를 읽지 않는다.
   그 밖은 지금과 같다. `with_prev=True`(기본)면 지금 글과 `strip()` 이 같은 벌은 `prev_transcripts` 에서 뺀다(R52-N4).
2. `GET /api/recordings/<id>?prev=0` - `store.get(rid, with_prev=False)`. `prev` 가 없거나 `0` 이 아니면 지금과 같다.
3. 화면: 상세가 받아쓰는 중(pending/transcribing)이라 되풀이해 읽을 때만 `?prev=0` 으로 읽는다. `?prev=0` 응답의 상태가
   더는 바쁘지 않으면 곧바로 한 번 `?prev=0` 없이 다시 읽어 지난 글을 그린다. `prev_transcripts` 키가 없는 응답으로는
   지난 글 묶음을 건드리지 않는다(R52-N5).
4. `voxlog/stt.py` 상수 `EMPTY_TEXT_ERROR = "받아 적은 글이 비었습니다 - 소리가 없거나 말소리가 잡히지 않았을 수 있습니다(옵션을 바꿔 다시 받아써 볼 수 있음)"`.
   command 백엔드의 raise 와 `_process` 의 실패 둘 다 이 상수를 쓴다(R52-N8·N10). `_process` 의 `on_done` 앞 군더더기
   `(text or "").strip() and` 는 뺀다.
5. `serve.py` JSON 본문 읽기 도우미 하나: 본문 JSON 을 풀다 `ValueError`·`UnicodeDecodeError`·`RecursionError` 가 나면
   400 `본문은 JSON 객체여야 합니다`. `PUT /api/stt-options`·`POST …/retry`·`PATCH /api/recordings/<id>`·`POST /api/ask` 가 함께 쓴다(R51-N4).
6. `serve.py` 재시도 잠금: 서버에 잠금 하나(`threading.Lock`)를 두고 `_rec_retry` 의 busy 검사 → 옛 옵션 읽기 → 새 옵션 저장 →
   `set_job(None)` → `resubmit` → 실패면 옛 옵션 되돌림 을 그 잠금 안에서 한다. 본문 읽기는 잠금 밖(R51-N7 첫째 줄·R51-N11).

## 관리자가 정한 것

- **R52-N2** 같은 글 중복 제거 (2) 는 **지우지 않고 검사로 받친다** - 닿는 길이 있다(옛 `.prev.txt` 가 지금 글과 같은 녹음을
  다시 받아쓰면 목록에 같은 글이 둘 들어오려 함). 그 길을 단위 검사로 만든다.
- **R52-N3** `.prev.json` 이 깨졌으면(JSON 이 아니거나 목록이 아님) 없는 것처럼 보고 옛 `.prev.txt` 이어받기 길로 간다.
  다음 쓰기는 지금처럼 `.prev.json` 을 새로 쓰고 `.prev.txt` 를 지운다(옛 글은 첫 벌로 이미 들어가 있음).
- **R52-N5** 지난 글을 따로 받는 API 는 만들지 않는다. 받아쓰는 동안의 되풀이 읽기만 `?prev=0` 으로 덜어 낸다(위 2·3).
  `Transcriber._process` 의 `store.get` 은 그대로(시험용 가짜 저장소와 얽히고, 받아쓰기 한 번에 한 번이라 작음) - 후속 거리.
- **R52-N6** `5벌` 문구는 그대로 두고, `index.html`·`app.js` 에 `f"{PREV_KEEP}벌"` 이 있는지 보는 단위 검사로 묶는다.
- **R52-N8** 상세 상태 줄: 상태가 `failed` 이고 글자 수가 있으면 `N자` 대신 `이전 글 그대로 N자`. 까닭 문구는 위 상수.
- **R52-N9** 옛 `done`+빈 글 자료와 `(빈 글)` 문구는 그대로 둔다(다시 받아쓰기가 복구 길). 고치지 않음.
- **R51-N5** `context` 는 strip 전에 형식 문자(유니코드 범주 `Cf`)와 제어 문자(`Cc`, 단 `\n`·`\t` 은 남김)를 뺀다(거절 아님).
- **R51-N6** 설정 칸을 열 때마다 `GET api/stt-options` 로 다시 채운다(캐시를 비우고 읽음). 열려 있는 동안엔 덮지 않는다.
  상세의 `옵션 바꿔 다시 받아쓰기` 칸을 열 때도 전체 기본값을 새로 읽는다.
- **R51-N7** 둘째 줄(오디오 없는 녹음의 재시도가 실패해도 새 옵션이 남음)은 고치지 않는다 - 옵션은 사람이 그 녹음에 고른
  값이고 실패 까닭과 무관하다. 셋째 줄: `retryWithOptions` 성공 뒤 옵션 칸 숨기기는 아직 같은 녹음을 보고 있을 때만.
- **R51-N13** 상세 옵션 칸의 빈 값 이름: 이 녹음에 옵션이 있으면(`hasSttOptions`) 전처리·자동 추정·LLM 검토 셋 모두
  `기본(서버 기본)`, 없으면 `기본(앱 설정 따름)`. 칸을 채울 때마다 맞춘다. 설정 칸은 지금대로 `서버 기본`.
- **R51-N10** 은 R51 에서 닫혔다(큐 1 의 '검사 구멍 넷' 은 F2·F4·F6·M10 - F2 는 R52 브라우저 56 이 지난 글 펼침 유지를 봐서 닫힘).
- `web/sw.js` 셸 캐시 `VERSION` 16 → 17.
