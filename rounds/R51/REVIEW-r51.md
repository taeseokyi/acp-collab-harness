# R51 적대적 검수 - 받아쓰기 옵션 (부작용 중심) - S4

대상: `git diff -- projects/VoxLog` 와 새 파일 `voxlog/stt_options.py`·`tests/test_stt_options.py`. 코드는 고치지 않았다.
방법: 코드 읽기 + /tmp 에 가짜 settings.json(가짜 키)·가짜 받아쓰기 서버(필드 기록)·임시 자료 폴더로 실제 서버(`serve.make_server`)를 띄워 재현 + /tmp 사본 변이 22개.
운영 자료 `data/`·`settings.json` 은 읽지 않았고 진짜 받아쓰기 서버에는 요청하지 않았다.

## 돌린 검사
- `python3 -m unittest discover -s tests` (projects/VoxLog): `Ran 286 tests ... OK` (82초)
- `python3 tests/browser_voxlog.py`: `51/51 통과`

## 지적

### R51-N1 (중) 이전 글은 한 벌뿐이라 연속 재시도 두 번이면 좋은 글이 사라진다
- `voxlog/store.py:526-529` `if old and old != text:` 가 매번 `.prev.txt` 를 덮는다.
- 재현(가짜 서버): 글 A → 재시도가 `""` 반환(글 `""`, prev=A) → 다시 재시도가 `"아"`: `old` 가 비어 prev 유지. 그러나 A → 재시도 `"아"`(prev=A) → 재시도 `"아."`: old=`"아"` 가 비지 않고 다르므로 prev=`"아"`, A 소실. 이번 계기(소음 녹음이 "아"/"아." 를 내는 경우)가 정확히 이 경로다. 실측 A→B→C 에서도 `transcript_prev=B`, A 없음.
- 고칠 방향: 새 글이 비었거나 짧은(예: 옛 글 길이의 몇 %) 때는 prev 를 덮지 않거나, prev 를 2벌(직전·그 전) 두거나, "비지 않은 글 중 가장 긴 것" 을 보존. 화면 안내문 `이전 글은 한 벌 남음` 이 이 한계를 말하지 않으므로 어느 쪽이든 안내를 맞출 것.

### R51-N2 (중) 멈춘 작업 id(`stt_job`)가 남아 있으면 옵션을 바꿔 다시 받아써도 옛 작업을 이어받는다
- `voxlog/stt.py` `_transcribe_api` 의 `jid = job.get()` (약 273행) 와 `serve.py:629-675` `_rec_retry`/`stt.py:405` `resubmit` 이 `stt_job` 을 지우지 않는다. `job.set(None)` 은 정상 종료·401/403/404 에서만 불리고, "너무 오래 걸립니다"(JOB_TIMEOUT)·폴링 오류 연속(POLL_MAX_ERRORS) 로 끝난 뒤에는 남는다.
- 재현(가짜 서버): 메타에 `stt_job: "job1"` 을 둔 채 `POST …/retry {"options":{"preprocess":"denoise"}}` → 서버 호출은 `GET` 하나뿐(맡기기 POST 없음), 글은 옛 작업 결과, 메타 `stt_options` 는 새 옵션 `denoise` 로 기록 → 화면에는 요청한 옵션이 적혔는데 실제 글은 옛 옵션 결과. 사용자는 옵션을 바꿔도 그대로인 것처럼 본다.
- 고칠 방향: 재시도 API(옵션이 오든 안 오든 사용자가 누른 재시도)에서 `resubmit` 전에 `store.set_job(rid, None)`. 앱 재시작 때 이어받기(`pending_ids`)는 그대로 두어 옛 작업을 잇는다. 시험은 `stt_job` 이 남은 메타로 재시도 시 맡기기 POST 가 나가는지.

### R51-N3 (중) 녹음별 옵션 `{}`(전부 "기본")이 전체 기본값을 영구히 덮고, 화면에서 되돌릴 길이 없다
- `voxlog/store.py:549-554` `effective_stt_options` 는 메타 `stt_options` 가 dict 면(빈 dict 포함) 그것을 쓴다. 화면 `retryWithOptions`(`web/app.js`) 는 항상 `{"options": {...}}` 를 보내므로 모두 "기본" 으로 둔 채 눌러도 `{}` 가 저장된다(null 은 보내지 않음).
- 재현: 전체 기본값 `denoise` 저장 → 어떤 녹음에서 `옵션 바꿔 다시` 를 전부 기본으로 눌러 실행 → 이후 그 녹음의 일반 `다시 받아쓰기` 필드는 `language`·`model` 뿐(전체 기본값 `preprocess` 누락). 반대로 같은 녹음에서 `{"options": null}` 은 전체 기본값을 되살리지만 화면에서 보낼 수 없다. 또 패널을 열면 `{}` 로 채워 전체 기본값이 보이지 않아 "기본" 이 무엇을 뜻하는지 어긋난다.
- 고칠 방향: 화면에서 모두 기본이면 `options: null` 을 보내거나(전체 기본값을 따름), `{}` 와 null 을 구분해 안내. 열 때 채울 값은 `{}` 면 전체 기본값.

### R51-N4 (하) 깊게 중첩한 JSON 본문이 400 대신 연결 끊김(RecursionError, 스레드 트레이스백)
- `serve.py:546`(PUT stt-options), `serve.py:645`(retry 새 본문 경로): `except (ValueError, UnicodeDecodeError)` 만 있어 `RecursionError` 가 새 나간다. `{"options":` + `[`×16000 + `]`×16000 + `}`(≈32 KB 이내) 로 재현: PUT 이 응답 없이 `RemoteDisconnected`, 서버 로그에 트레이스백, 서버는 계속 산다(health 200). 토큰이 있어야 닿는다. 같은 패턴이 `serve.py:565`(PATCH)에도 이미 있다(이전부터).
- 고칠 방향: `except (ValueError, UnicodeDecodeError, RecursionError)`. 세 곳 공통 도우미로 묶으면 좋다.

### R51-N5 (하) `context` 거르기 틈: 제로폭 글자·제어 문자
- `voxlog/stt_options.py:52` `value.strip()` 은 U+200B(제로폭 공백)를 못 자른다. `{"context":"​"}` 가 200 으로 저장되고 서버에는 비지 않은 `context` 가 나가 서버의 `auto` 용어 추정을 건너뛰게 한다(명세: 문맥을 주면 건너뜀). NBSP·U+3000 은 잘림(통과 확인). `"a\x00b"` 같은 NUL·제어 문자도 그대로 저장·전송.
- 고칠 방향: 포맷 문자(Cf)·제어 문자(개행·탭 제외)를 빼거나 거절한 뒤 strip.

### R51-N6 (하) 설정 기본값 캐시가 낡을 수 있고, 설정 칸을 다시 열면 쓰던 입력이 덮인다
- `web/app.js` `sttDefaults()` 는 한 번 불러오면 `state.sttDefaults` 를 계속 쓴다. 다른 기기·탭에서 바꾼 값이 안 보이고, 그 낡은 값을 보고 저장하면 덮어쓴다. 설정 칸을 닫았다 열면 `loadSttSettings()` 가 저장 안 한 입력을 캐시로 되돌린다.
- 고칠 방향: 열 때마다 GET(작은 요청)으로 다시 채우되 열려 있는 동안엔 건드리지 않음.

### R51-N7 (하) 실패·재시도 중간 상태의 작은 빈틈
- `serve.py:659-673`: `set_stt_options` 를 `resubmit` 보다 먼저 저장하고, 실패 시 `prev_opts`(읽은 시점 값)로 되돌린다. 읽은 뒤~되돌림 사이 다른 요청이 옵션을 바꾸면 그것을 덮는다(좁은 틈). 오디오가 없는 녹음은 재시도가 failed 가 돼도 새 옵션이 남는다. 둘 다 영향은 작다.
- `retryWithOptions` 성공 콜백이 `$('detail-stt').hidden = true` 를 그 사이 다른 녹취로 이동했어도 건드린다(작음).

## 확인했고 문제 없던 것 (요청 점검 항목)
1. 옵션 안 건드린 녹음·옛 메타(필드 3키 삭제): 서버로 가는 필드는 `['language','model','file']` 뿐 - 예전과 같음(재현 `legacy meta retry fields`).
2. 키 누출: 가짜 키로 `GET/PUT stt-options`, 녹음 GET 응답에 키 없음, 자료 폴더 전체 grep 에서 키는 가짜 `settings.json` 에만 있음. PUT 뒤 `settings.json` mtime 불변. 서버 400 글(HTML 섞임)이 메타 `error` 에 저장되나 키는 아님. `Authorization` 은 서버로만 감.
3. 이름·사람 태그·`tags_human`: 재시도 뒤 그대로. 서버 400 거절 때 글: 이전에 있던 글 유지(상태 failed + 까닭 `음성인식 서버가 요청을 거절했습니다 - …` 160자 컷). 빈 글 결과(`""`)는 done 으로 글을 비우나 prev 에 옛 글이 남음(N1 과 연결).
4. 거르기: bool·float·문자열·10^30 의 `num_speakers` 400, `auto` 문자열·정수 400, 대소문자·공백 붙은 `preprocess` 400, NaN 400, 모르는 키 400, 4001자 400/4000자 200, null 키 무시, NBSP·U+3000 만의 context 는 빈 값. 32 KiB 넘는 본문 413. 토큰 없음·틀림 401.
5. HTML 주입: 화면은 `textContent` 만 쓴다(`app.js` 에 `innerHTML` 없음 - grep). 서버 글은 토스트·메타에 텍스트로만 간다.
6. 폴링·재렌더: `loadDetail` 은 `fillSttFields` 를 부르지 않고 `renderPrev` 도 같은 글이면 건드리지 않아 열어 둔 입력·펼침이 유지된다(코드 읽기, 브라우저 51/51). 격리 출처에서는 설정 묶음·옵션 버튼을 숨기는 코드가 있음.
7. 앱 재시작 이어받기: `options_fn(meta)` 가 처리 시점의 메타를 읽으므로 대기 중이던 녹음은 새 옵션으로 간다. 이미 맡겨 둔 작업은 옛 옵션 그대로 이어받음(정상). 다만 N2.

## 검사가 고침을 잡는가 (변이)
/tmp 사본에서 한 줄씩 바꿔 단위 16개·브라우저 6개:
- 잡힘(단위 13): 필드 안 보내기, Transcriber 가 options 안 넘김, prev 안 씀, prev_stt_used 안 옮김, bool 허용, delete 가 prev 안 지움, 400 글 안 읽음, effective 가 메타 무시, PUT 거르기 없음, retry 가 옵션 저장 안 함, context strip 없음, used 안 채움, set_transcript 가 이름 지움.
- **못 잡음(단위 3)**:
  - M9 busy 검사를 옵션 저장 뒤로 옮김(= 409 인데 옵션이 바뀜): 시험이 409 때 옵션 불변을 확인하지 않는다.
  - M10 resubmit 실패 시 옵션 복구 제거: 복구 시험 없음.
  - M16 `set_status`(실패)가 글 파일을 비움: 실패해도 글이 남는 시험이 없다(명세 5번의 핵심 약속).
- 브라우저: 잡힘 1(F1: 기본을 빈 키로 보냄 → 50번 실패). **못 잡음 5**: F2 폴링이 이전글 펼침을 접음, F3 폴링이 옵션 입력을 지움, F4 격리 출처에서 설정 묶음 안 숨김, F5 재시도 400 의 서버 글 대신 고정 글, F6 토스트 innerHTML. 52번이 보는 400 토스트는 PUT 경로뿐이라 재시도 경로의 400 은 시험이 없다.
- 권고: 위 8개 각각 시험 한 개씩(특히 M16·F3·N2 재현).

## 다음 담당자
- 우선순위: N2(옵션이 조용히 무시됨)·N1(좋은 글 소실)·N3(기본값 덮임)부터. N4~N7 은 하.
- 재현 스크립트는 /tmp/s4probe(probe.py, probe2.py, mut.py)에 있으나 /tmp 라 휘발성.

판정: 조건부(상 0·중 3)
