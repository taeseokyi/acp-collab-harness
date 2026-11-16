# R34 적대적 검수 - VoxLog R33-N13~N16 수정 (T-358, S1)

대상: `projects/VoxLog/` (커밋 전, untracked) - `voxlog/stt.py`, `voxlog/store.py`, `serve.py`, `web/api.js`·`queue.js`·`sw.js`, 검사 4종.
실험은 모두 `/tmp/s1r34/` 복사본에서 함(제품 코드 안 고침).

## 1. 판정

**조건부 통과** - 상 0 · 중 0 · 하 7.

네 결함(N13~N16)은 모두 재현으로 닫힘을 확인했다. 조건은 둘이다:
R34-N1(재시도가 영구 409 에 갇히는 새 회귀)과 R34-N3(브라우저 검사 21번이 1/3 확률로 거짓 실패 - 관문 신뢰도)을 고칠 것.
나머지 하 5건은 후속 큐로 충분하다.

## 2. 돌린 검사와 결과

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s projects/VoxLog/tests` | `Ran 101 tests in 19.575s` / `OK` |
| `python3 projects/VoxLog/tests/browser_voxlog.py` (1회째) | `실패  21 업로드 503 → 대기열에 남고 다음 시도에 올라감 - 503 이 돌려지지 않음` / **`20/21 통과`** |
| 같은 명령 (2회째·3회째) | `21/21 통과`, `21/21 통과` |
| `python3 /tmp/s1r34/ff.py` (ffmpeg 위장 파일, 실제 ffmpeg `/usr/bin/ffmpeg`) | 아래 4절 N15 |
| `python3 /tmp/s1r34/srv.py` (서버 경쟁 실험 6가지, 가짜 STT) | 아래 4절·3절 |

`srv.py` 출력 요약:

```
== 1. N13: 받아쓰는 중 retry 두 번
retry1 409 retry2 409
받아쓰기 호출 수 1 status done
끝난 뒤 동시 retry 10개 응답 [200, 409, 409, 409, 409, 409, 409, 409, 409, 409] 받아쓰기 호출 1 status done
== 2. set_transcript 실패 뒤 'transcribing' 에 갇힘
status transcribing busy False
디스크 회복 뒤 retry (409, {'error': '받아쓰는 중입니다'})
== 3. 같은 client_id 동시 업로드 5개
응답 [200, 200, 200, 200, 201] id 수 1 meta 파일 2 audio 1 incoming []
   (meta 2 는 전사기 set_status 의 .tmp- 파일이 찍힌 순간값 - 끝난 뒤 다시 보면 meta 1·audio 1)
== 4. 느린 업로드 중 목록 응답 시간 + 동시 3번째 503 + 507
업로드 2개 도는 중 목록 200 0.002s
3번째 업로드 503
incoming 진행 중 파일 2
끊긴 뒤 incoming [] 자리 회복 업로드 201
디스크 부족 507
503 + 5MB 본문 -> 클라이언트 예외 BrokenPipeError [Errno 32] Broken pipe
== 5. 메타 쓰기 실패 뒤 고아 오디오
메타 실패 업로드 -> 클라이언트 예외 RemoteDisconnected
audio [] incoming [] 자리 회복 201 201 201
== 6. 목록 캐시: 다시 받아쓰기·지우기 뒤
목록1 버전1 내용
목록2 버전2 내용
지우기 200 목록 후 0 캐시 항목 0
```

확인한 것(결함 없음): 세마포어는 400/507/메타 실패/끊김 모든 경로에서 풀림(실험 4·5 뒤 업로드 201 이어짐) ·
끊긴 업로드와 메타 쓰기 실패 뒤 `incoming/`·`audio/` 에 찌꺼기·고아 없음 · 같은 client_id 동시 5개는 녹음 1개(201 1·200 4) ·
목록 캐시는 다시 받아쓰기 뒤 새 글, 지우기 뒤 항목·캐시 모두 0 · 503/507 은 `queue.js:240`·`sw.js` 에서 영구 실패(`failed`)로 빠지지 않음.

## 3. 결함 표

| 번호 | 심각도 | 설명 | 위치 | 재현 | 고칠 방법 |
|---|---|---|---|---|---|
| R34-N1 | 하 | **새 회귀.** retry 가 메타 `status == "transcribing"` 만 보고도 409 를 준다. 전사기가 `set_status("transcribing")` 뒤 `set_transcript`/`set_status` 에서 예외(디스크 가득 등)를 내면 `_run` 이 삼키고 `_active` 에서 뺀다 → 메타는 `transcribing` 으로 남고 아무도 처리하지 않는데, 재시도는 영원히 `409 받아쓰는 중입니다`. 서버를 다시 켜야(`pending_ids`) 풀림. 이번 라운드가 507 로 다루려는 바로 그 디스크 부족 상황에서 생긴다 | `serve.py:411`, `voxlog/stt.py:258-261`·`287` | `srv.py` 2번: `set_transcript` 가 `OSError(28)` → `status transcribing busy False` → 회복 뒤 retry `409` | 판정은 `tr.busy(rid)` 하나로(메타 status 비교 삭제). 덧붙여 `_run` 의 `except` 에서 `set_status(rid, "failed", ...)` 를 한 번 시도 |
| R34-N2 | 하 | retry 의 "busy 확인 → `set_status("pending")` → `resubmit`" 이 한 덩어리가 아니다. 겹친 두 retry 중 늦은 쪽이 확인을 통과한 뒤, 앞선 쪽 작업이 이미 `transcribing` 으로 바꾼 메타를 `pending` 으로 덮고 409 를 받는다(받아쓰기 끝나면 `done` 으로 돌아오므로 잠깐의 표시 오류) | `serve.py:411-415` | 코드 경로(실험 1 의 동시 10개는 받아쓰기 1회로 정상) | `Transcriber.resubmit` 안에서 잠금을 쥔 채 `store.set_status(rid,"pending")` 후 `put` 하고, serve 는 `resubmit` 결과만 봄 |
| R34-N3 | 하 | 브라우저 검사 21번이 **3번 중 1번 거짓 실패**. `wait_for(lambda: hits["n"] == 1, 15)` 가 파이썬 dict 만 들여다보며 `time.sleep` 으로 돈다 - 동기 Playwright 는 Playwright 호출 중에만 route 처리기를 돌리므로, 업로드 요청이 `rec_cycle` 마지막 호출 뒤에 오면 15초 동안 처리기가 안 돌아 `hits` 가 0 | `tests/browser_voxlog.py:604` | 위 2절: 1회째 `20/21`, 2·3회째 `21/21` | 폴링 안에서 Playwright 를 부르게: `wait_for(lambda: (pg.wait_for_timeout(100), hits["n"] == 1)[1], 15)` 또는 `pg.wait_for_request(...)` |
| R34-N4 | 하 | 503/507 을 본문을 읽기 전에 보내고 연결을 닫는다(64KB 넘는 본문은 버리지 않음). 큰 녹음을 보내던 쪽은 상태 코드 대신 연결 오류를 받을 수 있다 - 파이썬 클라이언트는 `BrokenPipeError`. 브라우저면 `queue.js` 의 네트워크 오류 경로('연결 안 됨', 대기열 유지)로 가므로 영구 실패는 아니지만 503 문구·`Retry-After` 는 잃는다. 검사 21번은 `route.fulfill` 가짜 503 이라 실제 서버 경로를 안 거침 | `serve.py:292-294`·`306-307`, `serve.py:138` | `srv.py` 4번: `503 + 5MB 본문 -> BrokenPipeError` | 동작은 그대로 두고 INTERFACE 에 "503/507 은 연결 오류로 보일 수 있음" 명시, 또는 실제 서버로 503 을 받는 브라우저 검사 하나 |
| R34-N5 | 하 | 페이지 대기열은 503/507 뒤 `return` 으로 멈추기만 하고 `Retry-After` 를 안 본다. Background Sync 가 없는 브라우저(사파리·파이어폭스)는 다음 `online`/화면 보임/새 녹음까지 대기 | `web/queue.js:248` | 코드 경로 | 5xx 면 `setTimeout(flush, Retry-After 초 또는 5초)` 한 번 |
| R34-N6 | 하 | 업로드 자리 2개를 느린(멈춘) 연결이 오래 쥘 수 있다. `timeout = 60` 은 recv 한 번 기준이라 59초마다 1바이트씩 보내면 자리를 무한정 쥠 → 인증된 클라이언트 둘이면 모든 업로드 503. 토큰이 필요하므로 하 | `serve.py:98`, `serve.py:324-329` | 코드 경로(실험 4 에서 2개가 멈춘 동안 3번째 503) | 업로드 전체 마감(예: `length / 최소 속도 + 여유`)을 넘으면 400 으로 끊음 |
| R34-N7 | 하 | 인터페이스 문서가 이번 수정을 반영하지 않음: 아직 `getConfig` 의 `apiBase`, `POST {apiBase}/api/recordings`, `VoxApi` 가 apiBase 를 붙인다고 적혀 있고 retry 409·업로드 503/507·`incoming/`·`busy/resubmit` 이 없음 | `docs/INTERFACE.md:146`·`156`·`198` | `grep -n "503\|507\|409\|resubmit" docs/INTERFACE.md` → 없음 | 해당 절 갱신 |

참고(결함으로 세지 않음): 메타 쓰기·`os.replace` 의 `OSError` 는 `ValueError` 가 아니라 처리기 밖으로 나가 응답 없이 끊긴다(`serve.py:340-345`, 실험 5 `RemoteDisconnected`). 정리는 올바르고 클라이언트는 대기열에 남기므로 해는 없으나 500/507 로 답하는 편이 낫다. 끊긴 업로드에 400 을 쓰려다 `BrokenPipeError` 트레이스백이 로그에 남는 것도 같은 부류의 소음.

## 4. 네 결함별 판정

| 결함 | 판정 | 근거 |
|---|---|---|
| R33-N13 받아쓰는 중 retry → 한 번 더 받아씀 | **닫힘** | 실험 1: 받아쓰는 중 retry 두 번 모두 409, 받아쓰기 1회. 끝난 뒤 동시 retry 10개 → 200 1·409 9, 받아쓰기 1회. serve 가 `_seen`·`_lock` 을 직접 만지지 않고 `busy()`/`resubmit()` 공개 메서드 사용(`serve.py:411-415`). 다만 새 회귀 R34-N1·표시 경쟁 R34-N2 |
| R33-N14 업로드 메모리·잠금·스레드·목록 | **닫힘** | 64KB 단위로 `incoming/` 에 흘려 쓰고(`serve.py:319-331`), 잠금은 rid 예약·메타 쓰기에만(`store.py:300-353`), 동시 2개 넘으면 503·디스크 여유 부족이면 507, 목록은 `(mtime_ns,size)` 캐시. 실험 4: 업로드 2개가 멈춰 있는 동안 목록 0.002초. 남은 것 R34-N4~N6 |
| R33-N15 ffmpeg 내용 판별 → 다른 파일 읽음 | **닫힘** | 실제 ffmpeg 로 concat·HLS 텍스트를 webm/ogg/m4a/mp3/wav 로 위장: 예전 명령(`-f` 없음)은 HLS 5종 모두 `rc 0`(다른 파일을 읽어 변환), 새 `to_audio` 는 10종 모두 `SttError`(`-f matroska` 등 강제 + `-protocol_whitelist file,pipe`). 모르는 확장자는 ffmpeg 를 부르지 않음 |
| R33-N16 쓸 수 없는 '서버 주소' 설정 | **닫힘** | `#api-base` 없음, `api.js:40`·`queue.js:184`·`sw.js:152` 모두 같은 출처로 고정. 브라우저 검사 20번(저장된 `apiBase: 'https://elsewhere.invalid'` 가 있어도 같은 출처로 올라감) 3회 모두 통과. OPTIONS 는 CORS 머리 없이 204 그대로(같은 출처만 쓰므로 맞음). 문서만 낡음(R34-N7) |
