# R51 실물 확인 - 웹 상세에서 전처리 denoise 로 다시 받아쓰기

- 확인 날짜: 2026-11-27 19:40~19:43 (KST)
- 대상: `projects/VoxLog` 의 지금 작업 트리(코드 수정 없음, 실행만)
- 녹음: `r-20261127-145927-c6bb` (35.0초, 소음 속 안내방송, webm)
- 서버: 사본 자료 `/tmp/voxlog-r51-real` + `python3 serve.py --port 18951` (루프백, 토큰 없음, 900초 timeout)
- 조작: 크롬(headless, playwright) → `기록` 탭 → 그 녹음 상세 → `옵션 바꿔 다시 받아쓰기` → 전처리만 `denoise` → `이 옵션으로 다시 받아쓰기`
- 받아쓰기 요청: **1회만** 보냄(시험 서버 로그에 `POST /api/recordings/r-20261127-145927-c6bb/retry 200` 한 줄)
- 운영 서버·운영 자료: 건드리지 않음. 원본 `data/meta`·`data/transcripts` 는 읽기만 했고 mtime 이 15:52 그대로다.
- `settings.json` 은 열어 보지 않았고 받아쓰기 주소·키는 어디에도 적지 않는다(서버가 스스로 읽게 두었다).

## 사본 구성 (지시와 다른 점 하나)

지시는 `audio/`·`meta/` 의 두 파일만 복사하라고 했는데, **글 파일(`transcripts/2026-11-27/r-20261127-145927-c6bb.txt`)도 함께 복사**했다.
글은 meta 가 아니라 별도 파일에 있어서, 두 파일만 복사하면 상세가 "앞 글 없음"으로 뜨고 `이전 글` 묶음을 확인할 수 없기 때문이다.
복사한 것은 이 녹음의 파일 셋뿐이고(다른 녹음·답·대기열 없음), 원본은 읽기만 했다.

```
/tmp/voxlog-r51-real/audio/r-20261127-145927-c6bb.webm              282311 바이트
/tmp/voxlog-r51-real/meta/r-20261127-145927-c6bb.json                  630 바이트
/tmp/voxlog-r51-real/transcripts/2026-11-27/r-20261127-145927-c6bb.txt  14 바이트
```

## 결과

| 항목 | 값 |
| --- | --- |
| 앞 글(다시 받아쓰기 전, 상세의 `#transcript`) | `화자 ?: 아.` (8자) |
| 새 글(완료 뒤, 상세의 `#transcript`) | `화자 1: 지출한 지출. 응. 이렇게 해요. 네.` (27자) |
| `받아쓴 옵션` 줄(상세의 `#detail-stt-used`) | `받아쓴 옵션: 전처리 denoise · 화자 1 · 자동 추정 켬 · 검토 끔` |
| `이전 글` 묶음(`#detail-prev`) | **보임.** 요약은 `이전 글`(앞 글에 쓰인 옵션이 없어 전처리 표기는 없음), 펼치면 `화자 ?: 아.` |
| 녹음에 저장된 옵션(`meta.stt_options`) | `{"preprocess": "denoise"}` — 화면에서 고른 값 하나만 들어감 |
| 실제로 쓰인 옵션(`meta.stt_used`) | `preprocess=denoise, mode=context, speakers=1, auto=true, review=false` |
| 상태 | `done`, `error` 없음, 27자 |
| 걸린 시간 | 약 25초 (재시도 요청 시각은 브라우저 대기 조건이 어긋나 정확히 재지 못함. 글 파일 저장 시각 19:41:22, 요청은 그 20~25초 전) |

## 화면에서 본 것 (한 줄씩)

1. 상세를 열면 글이 `화자 ?: 아.`, `받아쓴 옵션` 줄은 없음(이 녹음은 옛 방식으로 받아써 `stt_used` 가 비어 있었다).
2. `옵션 바꿔 다시 받아쓰기` 를 누르면 옵션 묶음이 열리고, 전처리 칸이 `기본(서버: level)` 로 채워져 있다(녹음에 저장된 옵션이 없어 서버 기본값을 채움).
3. 전처리만 `denoise · 기본 + 잡음 제거` 로 바꾸고 실행 → 묶음이 닫히고 안내 토스트가 뜬다.
4. 끝난 뒤 새로 열면 글이 `화자 1: 지출한 지출. 응. 이렇게 해요. 네.` 로 바뀌고 `받아쓴 옵션: 전처리 denoise …` 줄과 `이전 글` 묶음이 함께 보인다.

## 실제로 돌린 명령과 출력 (요약)

```
python3 tools/aimem_db.py check --slot S6 --token 47764b --rev 207
  -> 일치: S6 토큰 47764b ... REV 207 / 소유 경로에 rounds/R51/REAL-CHECK.md 포함

mkdir -p /tmp/voxlog-r51-real/{audio,meta,transcripts/2026-11-27}
cp data/audio/r-20261127-145927-c6bb.webm data/meta/r-20261127-145927-c6bb.json \
   data/transcripts/2026-11-27/r-20261127-145927-c6bb.txt /tmp/voxlog-r51-real/... (원본은 읽기만)

cd projects/VoxLog && timeout 900 python3 serve.py --port 18951 --data /tmp/voxlog-r51-real
  -> VoxLog http://127.0.0.1:18951  (인증 꺼짐, 데이터 /tmp/voxlog-r51-real)
curl -s http://127.0.0.1:18951/api/health
  -> {"ok": true, "auth": false, "stt": "api", "llm": true, "version": "0.1"}

python3 /tmp/voxlog-r51-webcheck.py   # 크롬으로 상세 → 옵션 → denoise → 실행 (요청 1회)
  -> POST /api/recordings/r-20261127-145927-c6bb/retry 200  (시험 서버 로그, 1회)
python3 /tmp/voxlog-r51-ui.py         # 새 요청 없이 결과 화면만 읽음
  -> sttUsed: "받아쓴 옵션: 전처리 denoise · 화자 1 · 자동 추정 켬 · 검토 끔"
  -> prevHidden: false, prevSummary: "이전 글", prevText: "화자 ?: 아."

ls -l projects/VoxLog/data/meta/r-20261127-145927-c6bb.json
  -> 2026-11-27 15:52 (원본 그대로, 사본만 바뀜)
```

## 다음 담당자가 알아야 할 것

- 이 녹음은 소음이 커서 denoise 로도 내용이 맞지는 않는다(위 새 글은 실제 안내방송 문장이 아니다). 확인한 것은 "옵션을 바꿔 다시 받아쓰는 흐름과 화면 표시"이지 받아쓰기 품질이 아니다.
- 앞 글(`화자 ?: 아.`)에는 `stt_used` 가 없었으므로 `이전 글` 요약에 `(전처리 …)` 가 붙지 않았다. 그 표기는 `prev_stt_used` 가 있을 때만 나오는 것이 정상 동작이다.
- 브라우저 확인 스크립트(`/tmp/voxlog-r51-webcheck.py`, `/tmp/voxlog-r51-ui.py`)는 작업용 임시 파일이다. 저장소에는 넣지 않았다.
- 시험 서버(포트 18951)는 `timeout 900` 으로 스스로 내려간다.

결과: 달라짐
