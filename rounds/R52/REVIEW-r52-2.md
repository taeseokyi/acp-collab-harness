# R52 재검수 - N1 고침(빈 받아쓰기 결과 = 실패)과 부작용 (S4)

대상: `voxlog/stt.py::Transcriber._process` 의 새 가지(`not (text or "").strip()` → `set_status(failed, "받아 적은 글이 비었습니다")` 뒤 return),
이에 맞춘 `tests/test_stt.py`(고친 1개·새 2개). 코드는 고치지 않았다. 검사는 /tmp 사본·가짜 자료만(운영 `data/`·`settings.json` 안 읽음, 받아쓰기 서버 요청 없음).
첫 검수: `REVIEW-r52.md`(N2~N6 은 하라 큐 - 다시 안 적음).

## N1 고침이 맞는가 - 맞다

- **두 백엔드가 같다.** command: `_transcribe_command` 가 이미 `SttError("받아 적은 글이 비었습니다")` 를 올려 `except SttError` → failed. api: `_transcribe_api` 는 빈 `text`(공백뿐)를 그대로 돌려주고, 이제 `_process` 의 `else:` 가지가 같은 문구로 failed 로 돌림. 문구가 글자까지 같아 화면·시험이 한 가지로 본다. 커스텀 `transcribe_fn`(시험용) 이 `""`·`None` 을 돌려줘도 같은 길.
- **`segments` 가 있으면 빈 글이 아니다.** `_speaker_lines` 는 글이 공백인 segment 를 건너뛰고, 줄이 하나도 없으면 `None` → `result["text"].strip()` 으로 떨어짐. 즉 text 가 비고 segments 도 모두 비어야 실패. 화자 줄이 하나라도 있으면 정상 완료(경계 맞음).
- **글·지난 글이 그대로.** 빈 결과는 `set_transcript` 를 부르지 않는다 → 지금 글, `prev_transcripts`, `stt_used`, 이름·태그 모두 안 건드림. 새 시험 `test_blank_api_result_keeps_current_and_prev_transcripts` 가 [옛 글]·지금 글 "좋은 글" 이 실패 뒤에도 같음을 확인.
- **작업 id 가 남지 않는다.** `_transcribe_api` 는 서버가 `done` 으로 끝나면 `job.set(None)` 을 **결과 판정 전에** 부른다(stt.py 304~305). 빈 결과로 실패해도 메타 `stt_job` 은 지워진 뒤라, 다시 받아쓰기·재시작 때 죽은 작업 id 를 이어 기다리는 일이 없다.
- **재시작·이어받기.** `pending_ids` 는 `pending`·`transcribing` 만 다시 큐에 넣고 failed 는 안 넣음 → 빈 결과 실패가 재시작 때마다 되풀이되지 않는다. 이어받은 작업의 결과가 빈 글이면 같은 길로 failed. 남은 작업 id 와 겹치는 길 없음(위 `job.set(None)`).
- **동시성.** `finally` 가 `_active`·`_pending` 을 정리하므로 return 으로 일찍 나와도 `idle()`·`busy()` 가 맞다(`wait_idle` 시험 통과). 실패 뒤 `resubmit` 은 failed → pending 으로 돌아가 정상. `set_status(pending)` 이 `error` 를 비움.
- **자동 태그.** 빈 글이면 `on_done` 안 불림(예전과 같음). 지금 글이 남아 있는 재시도 실패에서도 AI 태그는 옛 글 기준 그대로 - 실패면 글도 태그도 그대로라는 약속과 맞다.

## 실패 뒤 화면

- 상세(`loadDetail`): 줄 = `<날짜> · <길이> · 실패 · <N>자 · 받아 적은 글이 비었습니다`, 본문은 처음이면 `(글이 없습니다)`, 재시도 실패면 **남은 옛 글**. `다시 받아쓰기`·`옵션` 단추는 isolated 가 아니면 항상 보임(failed 라서 숨는 일 없음) → 다시 누를 수 있다. 목록 뱃지 `실패`. 지난 글 묶음은 그대로.
- 별도 토스트 없음(받아쓰기 도중 상세 폴링이 상태 줄만 갱신). 다른 실패(서버 오류 등)와 같은 모양이라 새 불일치는 아님.

## 지적 (새 번호 R52-N7 부터)

### R52-N7 (하) 문서가 '빈 결과는 실패' 를 말하지 않는다
- `docs/INTERFACE.md` 195 줄(`SttError → failed`)·219 줄(`on_done ... no-stt·failed·빈 글에는 없음`)·230 줄(`→ set_transcript / no-stt / failed`)과 `README.md` 어디에도 "api·command 모두 빈 글이면 failed(`받아 적은 글이 비었습니다`)" 가 없다. 219 줄의 `빈 글에는 없음` 은 이제 '빈 글로 done 이 되는 일이 없다' 는 뜻이 아니라 낡은 표현으로 읽힌다. 소리 없는 녹음이 `완료 · (빈 글)` 이 아니라 `실패` 로 보인다는 것도 문서에 없다.
- 약속 `rounds/R52/spec.md` §1 은 이미 '빈 결과로 끝난 실패' 라고 쓰므로 코드는 약속과 맞고, **문서 쪽이 뒤처짐**. 고칠 곳: INTERFACE 의 `_process` 흐름 한 줄과 README 받아쓰기 절에 한 문장.

### R52-N8 (하) 재시도가 빈 결과로 실패하면 '실패' 줄 옆에 옛 글의 `N자` 가 그대로 보인다
- 줄 `... · 실패 · 1234자 · 받아 적은 글이 비었습니다`, 본문은 옛 글. 사람이 보면 "실패인데 글은 있다" 이고, 소리 없는 파일이라면 같은 단추를 눌러도 계속 실패한다는 안내가 없다. 까닭 문구도 `소리가 없거나 말소리가 잡히지 않았을 수 있습니다` 처럼 원인 후보를 말하지 않는다(README 34 줄은 denoise 로 말소리가 잡히는 사례를 적어 둠 - 옵션을 바꿔 보라는 힌트로 연결 가능). 다른 실패(서버 오류)와 모양이 같아 헷갈림이 크진 않다.
- 오디오가 비어 있을 때 클라이언트는 이미 `녹음된 소리가 없어 저장하지 않았습니다`(app.js 776)로 막지만, **파일 올리기**로 올린 무음 파일은 그 길을 안 지나 서버가 빈 결과 → 실패로 보인다.

### R52-N9 (하) 이미 `done` + 빈 글로 남은 옛 자료는 그대로
- N1 고침은 앞으로의 결과만 바꾼다. 옛 `done`·빈 글 녹음은 `완료 · (빈 글)`(app.js 998)로 계속 보이고 `stats.done` 에 센다. `(빈 글)` 문구는 이제 옛 자료에만 닿는 코드. 지우거나 두는 것은 관리자 결정(두면 `다시 받아쓰기` 가 복구 길).

### R52-N10 (하) 시험·코드 가장자리
- 빈 결과 실패의 **화면**(상세 줄·단추·본문)을 보는 브라우저 시험이 없다 - 단위만 있음.
- `_process` 의 문구 `받아 적은 글이 비었습니다` 가 `_transcribe_command`(146 줄)와 글자로 두 번 박혀 있다. 한 곳만 바뀌면 백엔드별 문구가 갈림(상수로 묶을 거리).
- 479 줄 `if (text or "").strip() and self.on_done is not None:` 의 `.strip()` 검사는 이제 항상 참(앞에서 return) → 군더더기. 해는 없음.

## 첫 검수 변이 표에서 N1 되돌림

- /tmp 사본(`/tmp/s4_r52b`)에서 `_process` 의 새 가지 세 줄을 지우고 `python3 /tmp/s4_r52b/tests/test_stt.py`:
  `FAIL: test_blank_api_result_keeps_current_and_prev_transcripts`, `FAIL: test_blank_api_result_on_first_transcription_marks_failed`, `FAIL: test_on_done_not_called_for_empty_text` → `Ran 49 tests` / `FAILED (failures=3)`. **이제 검사에 걸린다**(고치기 전 첫 검수에서는 전부 통과했음).
- 고침 줄은 `not (text or "").strip()` 이라 공백만 있는 결과(`"   "`)도 잡는다(시험이 `"   "`·`"  "` 로 확인). 되돌리는 다른 변이(`.strip()` 만 빼기 = 공백뿐 글이 통과)는 시험 두 개의 입력이 공백이라 같이 잡힌다.

## 실제로 돌린 검사

- `python3 -m unittest discover -s tests` (projects/VoxLog): `Ran 302 tests in 84.901s` / `OK` (첫 검수 300 → 새 시험 2개).
- `python3 projects/VoxLog/tests/browser_voxlog.py`: 마지막 줄 `56/56 통과`.
- 변이: 위 절. 사본은 /tmp 안(지워도 됨).

## 판정

N1 고침은 두 백엔드에서 같고, 지금 글·지난 글·작업 id·재시작 이어받기에 새 부작용이 없다. 단위 302 OK·브라우저 56/56, N1 되돌림은 시험 3개가 잡는다. 상·중 없음, 하 4(N7~N10; 가장 먼저 N7 문서).

판정: 통과
