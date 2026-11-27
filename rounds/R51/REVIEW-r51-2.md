# R51 재검수 (G-109: N1~N3 고침) - 부작용 중심 - S4

대상: `git diff -- projects/VoxLog` 중 `store.py` set_transcript, `serve.py` `_rec_retry`, `web/app.js`(옵션 채우기·`hasSttOptions`), `index.html`, 문서 `docs/INTERFACE.md`·`README.md`. 코드는 고치지 않았다.
한계(중요): 이 세션에서 `/tmp` 에 폴더를 만드는 명령(`mkdir`·`cp`)이 승인 대기로 막혔다(비대화 세션이라 승인 못 함). 그래서 **/tmp 사본 변이 실행과 가짜 서버 재현은 하지 못했고**, 변이 여부는 시험 코드를 읽어 판정했다(아래 '변이'에 "읽어서 판정" 으로 표시). 단위·브라우저 검사는 정상 실행했다. 운영 자료·진짜 서버는 건드리지 않았다.

## 돌린 검사
- `python3 -m unittest discover -s projects/VoxLog/tests -t projects/VoxLog/tests`: `Ran 292 tests in 81.880s` `OK`
- `python3 projects/VoxLog/tests/browser_voxlog.py`: `54/54 통과` (50~55 가 옵션·이전 글·폴링·재시도 400 토스트)

## 첫 검수 N1~N3 고침 판정

### N1 이전 글 규칙(`store.py:526-533`) - 계기 시나리오는 지킨다, 규칙 자체에 새 문제(N8)
- 규칙: 밀려나는 글이 `.prev.txt` 의 글보다 짧으면(공백 뺀 길이) prev 를 덮지 않는다.
- 소음 녹음: 좋은 글 A → `"아"` → `"아."` 에서 prev=A 유지, `prev_stt_used` 도 A 것 그대로(코드 읽기 + 시험 `test_set_transcript_keeps_longest_displaced_text` 통과). 빈 글 `""` 은 A 를 prev 로 보내고 그다음 `"아"` 는 old 가 비어 prev 유지. 계기는 지켜진다.
- 맞게 되는 것: `prev_stt_used` 는 prev 가 바뀔 때만 같이 바뀌어 글과 옵션이 어긋나지 않는다.

### N2 `stt_job` 지움(`serve.py` `_rec_retry`) - 고쳐졌고 재시작 이어받기를 깨지 않는다
- 사람이 누른 재시도(본문 있든 없든)만 `set_job(rid, None)` 뒤 `resubmit`. 앱 재시작 이어받기는 `pending_ids`→`Transcriber` 큐로 가고 `_rec_retry` 를 지나지 않으므로 `stt_job` 을 그대로 읽는다(코드 읽기: `stt.py` 276행 `job.get()` 경로 불변, 단위 검사 중 이어받기 시험 모두 통과).
- 지우는 순서가 `resubmit` 앞이라 그 사이 앱이 죽어도 상태는 옛 것(done/failed)이고 맡긴 작업이 없을 뿐 - 잃는 것 없음.
- 시험이 고침을 잡는다: `TestRetryStaleJobApi`(본문 있음·없음 둘). 가짜 서버가 어떤 작업 id 든 done 으로 답해서, 지움이 없으면 맡기기 POST 가 안 나가 `posts == before+1` 이 깨진다(읽어서 판정).
- 부수 효과(정보): 시간 초과로 끝난 옛 작업은 서버에서 계속 돌 수 있고(고아) 새 작업이 하나 더 생긴다. 서버가 24시간 뒤 지우므로 영향은 부하뿐.

### N3 빈 옵션 `{}` = null(`serve.py` `new_opts = norm or None`) - 동작은 일관, **화면 문구·문서가 어긋남(N9·N10)**
- 화면이 보내는 `{"options": {}}` → 서버가 `null` 로 저장(메타 키 삭제) → 이후 일반 '다시 받아쓰기' 가 전체 기본값을 쓴다. 단위 `test_retry_empty_options_follows_defaults`·브라우저 54 가 이를 잡는다.
- 열 때 채우기: `hasSttOptions` 가 `{}`·없음을 전체 기본값으로 처리해 화면과 서버가 같은 뜻(통과).

## 새 지적 (R51-N8 부터)

### R51-N8 (중) '가장 긴 글을 남김' 은 '좋은 글' 이 아니다 - 방금까지 보던 좋은 글이 사라질 수 있다
- `store.py:526-533`: 밀려나는 글이 prev 보다 짧으면 prev 를 갱신하지 않는다.
- 재현(코드 논리, 시험 없음): A 2000자(반복 환각이 섞인 긴 글, level) → 재시도 B 500자(denoise 로 깨끗해진 좋은 글, prev=A) → 재시도 C(다른 옵션, 더 나쁜 글). C 로 바뀔 때 old=B(500) < prev=A(2000) 이라 prev=A 그대로, **B 는 어디에도 남지 않는다.** 화면 '이전 글' 은 방금 전 글이 아니라 더 길고 나쁜 A 다.
- 사람이 보기에도 헷갈린다: 접힌 요약은 `이전 글 (전처리 level)` 뿐이라 '직전 글' 로 읽히는데 실제로는 '이전 글 중 가장 긴 것' 이다. 이 문구가 정확히 보이는 곳은 재시도 토스트와 묶음 안 한 줄(`index.html`)뿐이다.
- 고칠 방향(택1): prev 를 2벌(직전·가장 긴 것)로 두기 / 아주 짧은 글(예: 옛 글의 10% 미만이거나 N자 미만)만 거르기 / 요약을 `이전 글 중 가장 긴 것` 으로 맞추기. 어느 쪽이든 아래 N10 문서도 맞출 것.
- 시험 빈틈: `test_set_transcript_previous_tracks_longest_of_displaced` 는 a<b 로 길이가 늘어나는 경우만 본다. 길이가 줄어드는 좋은 글(B<A)이 밀려나는 경우 시험이 없다.

### R51-N9 (중) '기본' 이라는 말이 화면마다 뜻이 다르고, 옵션 `{}` 가 이제 전체 기본값을 따르므로 문구가 틀리다
- `app.js` `buildSttFields`: 전처리 `''` 의 이름은 두 묶음 모두 `기본(서버: level)`(`STT_PREPROCESS_LABEL['']`). 자동 추정·LLM 검토의 `''` 는 상세 묶음에서 `앱 기본값`, 설정 묶음에서 `서버 기본`.
- 재현 1(전처리): 전체 기본값 `denoise` → 녹음 상세 열기(denoise 로 채워짐) → 전처리를 `기본(서버: level)` 로 바꾸고 나머지도 기본 → 서버로 `{}` → null → **실제로는 전체 기본값 denoise 로 돎**. 화면은 level 이라 적었다.
- 재현 2(부분 옵션): 전체 기본값 `{auto:false}`, 녹음 옵션 `{num_speakers:2}` 저장 → `effective_stt_options` 는 녹음 옵션만 쓰고 전체 기본값과 합치지 않는다. 그런데 이 녹음 상세 묶음은 자동 추정을 `앱 기본값` 으로 보이는데 실제는 서버 기본(auto 미전송)이다. 즉 '앱 기본값' 이라는 이름이 녹음에 옵션이 하나라도 있으면 틀리다.
- 고칠 방향: 상세 묶음의 `''` 이름을 `기본(앱 설정 따름)` 하나로 통일하고, 녹음 옵션이 있을 땐 "이 녹음 옵션이 앱 기본값을 대신합니다(합치지 않음)" 한 줄을 달거나, `effective_stt_options` 를 키 단위로 합치도록 규칙을 정해 문서에 적을 것(관리자 결정거리 - 스펙 3번 `effective` 는 '그것, 아니면 전체' 라서 합침은 스펙 변경).

### R51-N10 (하) 문서가 고침과 어긋남
- `docs/INTERFACE.md:288·299-302`(retry): `"options": null` 만 말하고 **`{}` 도 키를 지운다(전체 기본값을 따름)** 는 말이 없다. 화면이 항상 보내는 형태가 `{}` 라서 가장 중요한 줄이 빠졌다.
- `INTERFACE.md:121-122`(`set_stt_options`): `{}` 는 '전체 기본값을 쓰지 않음' 이라 적었다. 저장소 수준에선 사실이나 retry API 와 화면은 `{}` 를 이 값으로 만들지 않는다 - '저장소만의 값, 화면·retry 는 `{}` 를 null 로 바꿔 보냄' 으로 한 줄 보충.
- `INTERFACE.md:114-118`(`set_transcript`)·`INTERFACE.md:439`·`README.md` 다시 받아쓰기 항목·스펙 5번은 모두 '이전 글 한 벌/밀려난 글' 이라 쓰고, 지금 규칙(밀려나는 글이 더 짧으면 prev 유지)과 `index.html` 의 '바뀌기 전 글 중 가장 긴 것 한 벌' 과 다르다. 문서만 보면 직전 글이 남는 것으로 읽힌다.
- `INTERFACE.md:32` `.prev.txt` '이전 글 한 벌' 도 같음.

### R51-N11 (하) 재시도에서 `set_job(None)` 이 busy 검사 밖(락 없음)이라 겹친 두 재시도가 진행 중 작업 id 를 지울 수 있다
- `_rec_retry`: `tr.busy` 검사 → (본문 읽기) → `set_job(None)` → `resubmit`. 두 재시도가 동시에 오면 둘 다 busy 검사를 통과하고, 먼저 온 쪽이 `resubmit` 로 받아쓰기를 시작해 `stt_job` 을 적은 뒤 뒤 온 쪽의 `set_job(None)` 이 그것을 지운다(뒤 온 쪽은 `resubmit` 이 False → 409). 그 상태에서 앱이 죽으면 이어받기가 작업 id 없이 새로 맡겨 서버에 같은 작업이 두 번 돈다. 좁은 틈(코드 논리, 재현은 못 함 - 위 한계).
- 고칠 방향: `set_job(None)` 을 `resubmit` 이 성공한 쪽에서만(예: `Transcriber.resubmit` 안, 잠금 안에서) 하거나, busy 를 `set_job` 직전에 한 번 더 본다.

### R51-N12 (하) 시험 빈틈 둘
- resubmit 이 False 일 때 옵션 복구(`store.set_stt_options(rid, prev_opts)`)를 보는 시험이 없다. `test_retry_resubmit_false_409` 는 본문 없이 호출해 복구 경로를 타지 않는다(첫 검수 M10 이 아직 안 잡힌다. 읽어서 판정).
- 고치기 전에 이미 `{}` 로 저장된 녹음(운영 자료에 있다면)은 화면 묶음이 전체 기본값을 보이지만(`hasSttOptions({})` false), 일반 '다시 받아쓰기' 는 여전히 옵션 없이 돈다. R51 이 미커밋이라 영향은 개발 중 자료뿐이다. 필요하면 `effective_stt_options` 가 빈 dict 를 '없음' 으로 보게 하면 한 줄로 맞는다(권고).

## 변이 (첫 검수에서 못 잡던 것이 이제 걸리는가) - 읽어서 판정, /tmp 실행은 못 함
| 번호 | 내용 | 지금 | 근거 |
| -- | -- | -- | -- |
| M9 | busy 검사를 옵션 저장 뒤로 | 잡힘 | `test_retry_options_while_transcribing_409_and_options_unchanged`(serve:870) 가 denoise→basic 요청 뒤 옵션 불변을 확인 |
| M16 | `set_status`(실패)가 글 파일을 비움 | 잡힘 | `test_set_status_failed_keeps_transcript_and_previous`(store:931)가 글 파일 내용·prev 를 확인 |
| F3 | 폴링이 옵션 입력을 지움 | 잡힘 | 브라우저 53 |
| F5 | 재시도 400 에 서버 글 대신 고정 글 | 잡힘 | 브라우저 55 (재시도 경로 400 을 route 로 주입) |
| N2 | `set_job(None)` 제거 | 잡힘 | `TestRetryStaleJobApi` 둘 - 가짜 서버가 어떤 id 든 done 이라 맡기기 POST 수 `before+1` 이 깨짐 |
| M10 | resubmit 실패 시 옵션 복구 제거 | **못 잡음** | N12 |
| (새) N1 변이: `>=` 비교를 없애 매번 덮기 | 잡힘 | `test_set_transcript_keeps_longest_displaced_text` 의 `"아."` 단계 |
| (새) N8 변이: 길이 줄어드는 좋은 글 | **못 잡음** | N8 시험 빈틈 |

## 확인했고 문제 없던 것
- 옵션 안 건드린 녹음·옛 메타: 일반 재시도는 필드가 예전과 같다(첫 검수 확인 사항, 이번 diff 로 바뀐 곳 없음).
- 409 때 옵션 불변·400 때 옵션·상태 불변·32KiB 413 시험 모두 통과.
- 폴링이 이전 글 펼침·옵션 입력을 접거나 지우지 않음(브라우저 53·51).
- `{}`→null 이 재시도 응답 메타에도 `stt_options: null` 로 실린다(단위 통과).

## 다음 담당자
- 우선순위: N8(좋은 글 소실)·N9(화면의 '기본' 뜻) 먼저. N9 는 합침 규칙이 관리자 결정거리일 수 있다. N10 문서는 N8·N9 결정 뒤 한 번에 맞추면 된다.
- N4~N7(첫 검수) 은 하라 큐로 갔으므로 다시 적지 않았다.
- 변이를 /tmp 사본으로 직접 돌리는 확인은 못 했으니, 다음 담당자가 /tmp 가 열린 세션에서 N8·N11·M10 세 개만 한 번 돌려 보면 좋다.

판정: 조건부(상 0·중 2)
