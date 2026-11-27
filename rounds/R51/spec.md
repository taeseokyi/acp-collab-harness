# R51 공통 약속 - VoxLog 받아쓰기 옵션 (요청 Q-261127-8d1e)

관리자가 정한 것. 노드는 이 문서를 정본으로 짓는다(요청 원문 `.aimem/requests/Q-261127-8d1e.json`).

## 관리자가 정한 것 (요청의 '관리자가 정할 것' 1~5)
1. **범위**: `preprocess`·`num_speakers`·`context`·`auto`·`review` 다섯. `min/max_speakers`·`diarize_mode`·`language` 는 내놓지 않음.
2. **단위**: (다) 둘 다. 앱 전체 기본값(설정 칸) + 녹음마다(상세의 `옵션 바꿔 다시 받아쓰기`).
3. **저장**: 전체 기본값은 자료 폴더의 `stt_options.json`(settings.json 은 손대지 않음 - 키가 웹으로 나가거나 덮일 길이 없다). 녹음마다는 녹음 메타 `stt_options`.
4. **기본값**: 아무것도 고르지 않으면 필드를 보내지 않는다 = 지금과 같은 요청(`language`·`model` 만).
5. **다시 받아쓰기의 뒤처리**: 성공하면 글은 새 글로 바뀌고 **이전 글 한 벌**이 남는다(`transcript_prev`, 그때 쓰인 옵션 `prev_stt_used`). 실패하면 글은 그대로(상태 failed·까닭). 이름·사람이 고친 태그·묻기 답은 그대로. AI 태그는 지금처럼 새 글로 다시 단다(사람이 태그를 고친 녹취는 안 함). 화면에 이 내용을 한 줄로 알린다.

## 옵션 객체 (JSON, 모든 키는 고를 때만 있음)
| 키 | 값 | 서버로 가는 필드 |
| -- | -- | -- |
| `preprocess` | `none`·`basic`·`level`·`dereverb`·`denoise` 중 하나 | `preprocess` |
| `num_speakers` | 정수 1~20 (bool 은 안 됨) | `num_speakers` (`str(n)`) |
| `context` | 글. 앞뒤 공백 자른 뒤 비면 없는 것, 4000자 넘으면 거절 | `context` |
| `auto` | true/false | `auto` = `"1"`/`"0"` |
| `review` | true/false | `review` = `"1"`/`"0"` |

값이 `null` 인 키는 없는 것과 같다. 모르는 키, 틀린 값은 `ValueError`(사람이 읽을 한국어 한 줄 - 서버가 400 으로 그대로 보임).

## `voxlog/stt_options.py` (새, 표준 라이브러리만)
```python
PREPROCESS = ("none", "basic", "level", "dereverb", "denoise")
SPEAKERS_MIN, SPEAKERS_MAX = 1, 20
CONTEXT_MAX = 4000
def normalize(obj) -> dict          # None → {}. dict 아니면·모르는 키·틀린 값 → ValueError. 고른 키만 담은 새 dict
def form_fields(opts) -> dict       # normalize 된 dict → {필드: 글} (위 표). {} → {}
def used_from_result(result) -> dict
    # 서버 결과(result dict)에서 실제 쓰인 값: {"preprocess": str|None, "mode": str|None,
    #   "speakers": int|None (list 면 len, int 면 그대로), "auto": bool (result["auto"] 가 dict 면 True),
    #   "review": bool (result["review"] 가 None/없음이 아니면 True)}. 글 값은 40자까지. result 가 dict 가 아니면 {}
```

## `voxlog/store.py` 에 더할 것
- 메타 기본값(`_fill_meta_defaults`): `stt_options` None, `stt_used` None, `prev_stt_used` None.
- `get(rid)` 이 `transcript_prev`(글, 없으면 "") 를 같이 돌려준다. 파일은 글과 같은 날짜 폴더의 `<id>.prev.txt`.
- `set_stt_options(rid, opts)` - opts 는 normalize 된 dict 또는 None(전체 기본값을 따름 = 메타에서 키를 지움). 없는 녹음은 ValueError(다른 set_* 와 같게).
- `effective_stt_options(meta) -> dict` - meta 의 `stt_options` 가 dict 면 그것, 아니면 `default_stt_options()`.
- `default_stt_options() -> dict` - `<자료 폴더>/stt_options.json` 을 읽어 normalize. 없거나 깨졌으면 {}.
- `set_default_stt_options(opts)` - normalize 해서 원자적으로 씀(`_atomic_write`).
- `set_transcript(rid, text, used=None)` - 있던 글이 비어 있지 않고 새 글과 다르면 먼저 그 글을 `<id>.prev.txt` 로, 메타 `prev_stt_used` = 있던 `stt_used`. 그다음 새 글을 쓰고 `stt_used` = `dict(used, at=<지금 ISO>)`(used 가 None 이면 None). 나머지는 지금 그대로.
- `delete(rid)` 가 `.prev.txt` 도 지운다. 목록·검색·현황은 `.prev.txt` 를 보지 않는다.

## `voxlog/stt.py` 에 더할 것
- `transcribe(path, mime, env=None, opener=None, job=None, options=None, used=None)` → api 백엔드만 옵션을 씀(command 는 무시).
- `_transcribe_api(..., options=None, used=None)`: `fields.update(stt_options.form_fields(options or {}))` (language·model 은 그대로 먼저). 결과가 done 이면 `used` 가 dict 일 때 `used.update(stt_options.used_from_result(result))`.
- 맡기기가 **400** 이면 서버 응답 `{"error":{"message":…}}` 의 message 를 읽어 `SttError("음성인식 서버가 요청을 거절했습니다 - " + message[:160])`. 읽지 못하면 지금처럼 `음성인식 서버 400`. (`_call` 이 HTTPError 의 본문을 읽어 객체로 돌려주게 - 다른 호출의 뜻은 그대로.)
- `Transcriber(store, env=None, transcribe_fn=transcribe, on_done=None, options_fn=None)`: `_process` 에서 `opts = options_fn(meta)` (없거나 예외면 {}), 진짜 `transcribe` 일 때 `options=opts, used=<새 dict>` 를 넘기고, 성공하면 `store.set_transcript(rid, text, used=used)`(진짜 transcribe 가 아니면 `used=None`). 남이 준 transcribe_fn 은 지금처럼 `(path, mime, env)` 로 부른다.

## `serve.py` API
- `GET /api/stt-options` → 200 `{"options": <전체 기본값>, "choices": {"preprocess": [...], "speakers_max": 20, "context_max": 4000}, "stt": <backend_name>}`
- `PUT /api/stt-options` 본문 `{"options": {...}}` (32 KiB 까지) → normalize → 저장 → 200 `{"options": …}`. 틀리면 400 + ValueError 글. 토큰·출처 검사는 다른 쓰기와 같음.
- `POST /api/recordings/<id>/retry` 본문은 **없어도 됨**(지금처럼). 있으면 `{"options": {...} | null}` (32 KiB): 받아쓰는 중이면 409(옵션도 안 바꿈) → normalize(틀리면 400, 아무것도 안 바꿈) → `set_stt_options` → resubmit. 본문이 없거나 `options` 키가 없으면 메타 옵션은 그대로.
- Transcriber 를 만들 때 `options_fn=store.effective_stt_options`.
- 녹음 GET 응답에는 store.get 이 주는 `stt_options`·`stt_used`·`prev_stt_used`·`transcript_prev` 가 그대로 실린다.

## 화면 (`web/`)
- **설정 칸**(`#settings`)에 `받아쓰기 옵션 (새 녹음과 '다시 받아쓰기' 의 기본값)` 묶음 `#stt-defaults` - 열 때 `GET api/stt-options` 로 채우고 `#stt-defaults-save` 로 `PUT`. 격리 출처(`isolated()`)이거나 불러오기 실패면 숨기거나 까닭 한 줄.
- **상세**: 있는 `#detail-retry`(지금 옵션 그대로 다시)는 그대로 둔다. 옆에 `#detail-retry-opts` `옵션 바꿔 다시 받아쓰기` → 그 아래 `#detail-stt` 묶음이 열린다(녹음의 `stt_options` 가 있으면 그것, 없으면 전체 기본값으로 채움) → `#detail-stt-run` 이 `POST …/retry` 에 `{"options": …}` 를 보냄. 묶음 안에 뒤처리 한 줄: `다시 받아쓰면 글이 새 글로 바뀝니다(이전 글은 한 벌 남음). 이름·직접 고친 태그·묻기 답은 그대로이고, AI 태그는 새 글로 다시 답니다.`
- 두 묶음은 같은 입력 모양(함수 하나로 만듦): 전처리 select(`기본(서버: level)`, none·basic·level·dereverb·denoise 와 짧은 뜻), 화자 수 number(빈칸 = 자동, 1~20), 문맥 글 textarea(maxlength 4000, 기본 비움, 밑에 `문맥 글은 조용한 구간에 새어 나오거나 낱말이 끌려갈 수 있어 기본은 비워 둡니다.`), 자동 추정·LLM 검토 select(`기본`·`켬`·`끔`). `기본` 은 키를 빼고 보낸다. 전처리 설명에 `잡음이 많은 녹음은 denoise 가 나을 수 있습니다(보장은 아님). 깨끗한 녹음에서는 오히려 나빠질 수 있습니다.`
- 상세 메타에 `stt_used` 가 있으면 `받아쓴 옵션: 전처리 denoise · 화자 1 · 자동 추정 켬 · 검토 끔` 한 줄 `#detail-stt-used`.
- `transcript_prev` 가 있으면 `<details id="detail-prev">` `이전 글` (요약에 `prev_stt_used` 의 전처리), 펼치면 글.
- 400 이면 서버 message 를 토스트로. 폰 320px 에서 겹침·넘침 없음.
