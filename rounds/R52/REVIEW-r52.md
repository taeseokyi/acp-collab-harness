# R52 적대적 검수 - 지난 글 여러 벌 (S4, 부작용 중심)

대상: `voxlog/store.py`(`.prev.json`·`PREV_KEEP`·옛 `.prev.txt` 이어받기·delete), `web/app.js`·`index.html`·`style.css`·`sw.js`,
`docs/INTERFACE.md`·`README.md`, 시험(`test_store.py`·`test_serve.py`·`browser_voxlog.py`). 코드는 고치지 않았다.
검사는 /tmp 가짜 자료·/tmp 사본에서만 했다(운영 `data/`·`settings.json` 은 읽지 않음, 받아쓰기 서버 요청 없음).

## 끝난 기준 네 가지

| 기준 | 결과 |
| -- | -- |
| A→B→C 뒤 A·B 와 옵션이 보임 | 충족. `get` 이 `prev_transcripts` = [B, A] (최근이 앞), 벌마다 `stt_used`·`at`. 브라우저 검사 56 이 요약 `지난 글 2벌`·옵션 요약 문구를 확인 |
| 상한 넘으면 가장 오래된 것 빠짐 | 충족. 7번 받아쓰면 [F, E, D, C, B] 만 남고 `.prev.json` 도 5벌(`test_prev_transcripts_capped_at_five_oldest_dropped`) |
| 옛 `.prev.txt` 녹음이 지난 글로 보임 | 충족(읽을 때 첫 벌로 봄, 다음 쓰기에 옮김). 단 R52-N3·N4 의 가장자리 있음 |
| R51-N14 문장 | 충족. INTERFACE·README 에 `가장 긴`·`transcript_prev` 문장 없음(남은 곳은 `PROGRESS.md` 의 R51 때 기록 줄과 INTERFACE 의 R51 이력 줄뿐 - 이력이라 괜찮음) |

## 지적

### R52-N1 (중) 받아쓰기 서버가 빈 글을 주면 지금 글이 빈 글이 되고 done 으로 남는다 - 약속 §1 의 전제가 api 백엔드에서 거짓
- `stt.py::_transcribe_api` 끝: `return "\n".join(lines) if lines else result["text"].strip()` - 서버가 `done` 인데 `text` 가 공백이면 빈 문자열을 **raise 없이** 돌려준다. `_process` 의 `else:` 는 그대로 `store.set_transcript(rid, "", used=used)` 를 부른다(command 백엔드는 `받아 적은 글이 비었습니다` 로 raise 하지만 api 는 아님).
- 약속 §1 은 "빈 결과로 끝난 실패는 `set_transcript` 를 부르지 않으므로 글도 목록도 그대로" 라고 적었고 요청도 "실패하면 지금 글도 지난 글도 그대로"다.
- 재현(/tmp 가짜 자료): `set_transcript(rid,"좋은 글")` → `set_transcript(rid,"")` ⇒ `transcript == ""`, `status == "done"`, `title == ""`, `prev_transcripts == ["좋은 글"]`. 화면은 완료인데 빈 글, 사람은 옵션을 바꿔 봤다가 지금 글을 잃은 것처럼 본다(지난 글에는 남아 있어 복구는 눈으로만 가능, 되돌리는 단추 없음). 자동 태그 `on_done` 은 건너뛰어 AI 태그는 옛 글 기준으로 남는다.
- R51 부터 있던 구멍이지만 R52 약속·문서가 "실패면 그대로"를 명시하므로 이번 라운드 기준으로 어긋남. 고칠 곳 후보: `_process` 에서 `not (text or "").strip()` 이면 `set_status(failed, "받아 적은 글이 비었습니다")`(command 백엔드와 같은 문구), 또는 `set_transcript` 가 빈 글이면 목록을 건드리지 않고 거절.

### R52-N2 (하) 같은 글 중복 제거 (2) 가 시험에 안 잡히고 평소엔 닿지 않는 코드
- `set_transcript` 의 `seen` 중복 제거: 목록 안 벌은 쓰기 때마다 "지금 글과 같은 벌 제거" 가 먼저 돌므로 정상 경로로는 목록 안에 같은 글이 둘 생기지 않는다. 닿는 길은 R52-N4 의 옛 자료(지난 글 == 지금 글)뿐.
- 변이 M2(중복 제거 줄 삭제)에 단위 검사 전부 통과(아래 변이 표). 지워도 되는 코드이거나 닿는 시험이 없는 코드 - 어느 쪽이든 약속 (2) 문장과 시험이 어긋난다.

### R52-N3 (하) 깨진 `.prev.json` 이 옛 `.prev.txt` 를 가린다 - 다음 쓰기에 옛 글이 조용히 사라짐
- `_read_prev_list`: `.prev.json` 이 있으나 JSON 이 깨지면 `[]` 를 돌려주고 `.prev.txt` 는 보지 않는다. 다음 `set_transcript` 가 `_write_prev_list` 로 `.prev.json` 을 덮고 `.prev.txt` 를 **지운다**. 재현: A 받아쓰기 → `.prev.txt`="옛글"·`.prev.json`="{broken" → get 은 `[]`, B 로 다시 받아쓰면 목록 [A] 뿐, `.prev.txt` 사라짐(옛글 소실).
- 약속 §2 는 깨진 파일을 빈 목록으로 본다고만 했고 이 조합은 정하지 않음. `.prev.json` 이 `os.replace` 로 원자적으로 쓰여 실제 깨질 일은 드물어 하. 옛 `.prev.txt` 는 쓰기 직전까지 "손대지 않는다"는 §2 의 뜻과는 어긋남.

### R52-N4 (하) 옛 `.prev.txt` 글이 지금 글과 같으면 지난 글에 지금 글이 또 보인다
- `.prev.json` 이 없으면 `_read_prev_list` 가 `.prev.txt` 를 무조건 첫 벌로 낸다. R51 은 `old != text` 일 때만 `.prev.txt` 를 쓰므로 보통 지금 글과 다르지만, 이후 사람이 R51 판에서 같은 글로 되돌아온 경우(R51 은 같은 글로는 prev 를 지우지 않음)에는 지금 글 == 지난 글 한 벌로 화면에 중복. 재현: 지금 글 "같은" + `.prev.txt`="같은" ⇒ `prev_transcripts == ["같은"]`. 다음 쓰기에는 §1 (1) 이 빼므로 일시적.

### R52-N5 (하) 큰 글 5벌이면 상세 응답이 약 6배, 받아쓰는 동안 5초마다 되풀이
- 가짜 30만 자 글 ×(지금 1 + 지난 5) ⇒ `Store.get` JSON 5,400,770 바이트(`get` 한 번 12ms). `GET /api/recordings/<id>` 는 압축 없이 그대로 내보낸다. 상세가 열린 채 받아쓰는 중이면 `loadDetail` 이 5초마다 다시 읽는다(`app.js` 1057 줄 근처 `busy` 폴링). 받아쓰기 서버가 허용하는 길이(50MB 오디오)에서 30만 자는 극단이지만 한 시간 분량(수만 자)도 폴링당 수백 KB.
- 같은 이유로 `Transcriber._process` 의 `self.store.get(rid)`(메타만 필요)도 지난 글 5벌 파일을 읽는다. 지금 규모에선 실해 없음 - 지난 글을 상세 열 때 한 번만 받는 길(별 API)은 후속 거리.

### R52-N6 (하) 시험이 못 잡는 곳
- 브라우저 검사에 **지난 글 본문의 XSS** 시험이 없다(13 번은 태그만). 코드는 `textContent` 만 써서 안전하나(`app.js` renderPrev 의 summary·pre 모두 `textContent`) 되돌리는 변이를 막을 시험이 없다 - 아래 변이 W3 참고.
- 단위: 공백만 다른 글(`"A"`→`"A\n"`)이 지난 글에 안 남는다는 규칙(§1 `strip()`)의 시험이 없다(변이 M10 통과).
- 문구 `5벌까지` 가 `index.html`·`app.js` 에 글자로 박혀 `PREV_KEEP` 와 따로 논다(상한을 바꾸면 화면 문구가 거짓). 하.
- (정정) 브라우저 검사 번호는 41 이 비어 57 까지 56개이고 머리말 "56개"와 맞음 - 어긋남 아님.
- `PROGRESS.md` 의 R51 줄(`transcript_prev`·`이전 글 중 가장 긴 것`, 남은 일 R51-N8)은 이번 라운드가 닫은 항목을 아직 "남은 일"로 적고 있음 - 정리는 관리자 몫이라 소유 경로 밖이어서 손대지 않음.

## 부작용 점검 결과 (문제 없음 포함)

- **옮기다 실패·동시 쓰기**: `set_transcript` 는 `self._lock` 안에서 `.prev.json` → `.prev.txt` 삭제 → `.txt` → 메타 순. `.prev.json` 쓰기 뒤 `.txt` 쓰기가 실패하면 목록에 지금 글과 같은 벌이 생기지만 다음 쓰기의 (1)·(2) 가 정리(하 - 일시적). `.prev.json` 이 있으면 메타의 `prev_stt_used` 는 안 읽히므로 메타 쓰기 전 중단돼도 옛 글은 안 사라짐. 동시 `get` 도 같은 잠금.
- **날짜 폴더 다름**: `recorded_at` 을 바꾸는 길이 없어 `.prev.*` 는 `.txt` 와 같은 폴더. 다른 날짜 폴더에 있는 `.prev.txt` 는 읽지 않지만(재현: 7) `delete` 의 glob(`*/<rid>.prev.txt`·`.prev.json`)이 지워 파일이 남지 않는다(`root` 아래 파일 0개 확인).
- **delete**: A·B·C 3번 받아쓴 뒤 delete ⇒ 자료 폴더 파일 0개(재현: 6). 직접 경로와 glob 이 겹쳐 둘 중 하나만 빠져도 지워지므로 변이 M5/M5b 는 동치(잡힐 수 없음), 둘 다 빼면 `test_delete_removes_previous_text` 가 잡는다.
- **동시 재시도·재시작 이어받기**: 이미 받아쓰는 중이면 `resubmit` 이 409(옵션도 되돌림). 이어받기로 같은 결과가 두 번 들어와도 둘째는 `old.strip() == text.strip()` 이라 목록을 건드리지 않음. 서로 다른 글이 연달아 들어오면 정상 순서로 붙음.
- **없앤 키를 읽는 곳**: `transcript_prev`·`prev_stt_used` 를 읽는 코드는 `store.py`(옛 메타 이어받기 한 곳)뿐. `web/` 전체·`serve.py`·`stt.py`·`ask.py`·`tags.py` 에는 없음. 응답 쪽은 `get`·`list` 가 둘 다 뺌.
- **폴링이 펼친 벌을 접나**: `renderPrev` 는 `JSON.stringify(items)` 가 같으면 다시 안 그림. 상세를 다시 열 때 `state.detailPrevText = null` 로 되돌려 빈 목록이 남는 길 없음. 브라우저 검사 56 이 폴링 2번 뒤 펼친 상태 `[true, true]` 유지를 확인.
- **XSS**: 글·`stt_used` 값 모두 `textContent`(`innerHTML` 없음). 서버가 내는 `preprocess` 값은 40자 제한.
- **옵션 정리**: `used_from_result` 외 모든 `stt_used` 키는 화면 낱말 4개만 씀.

## 실제로 돌린 검사

- `python3 -m unittest discover -s tests` (projects/VoxLog): `Ran 300 tests in 84.560s` / `OK`
- `python3 projects/VoxLog/tests/browser_voxlog.py`: 마지막 줄 `56/56 통과`, 종료 코드 0 (51·56·57 이 지난 글 관련).
- 가장자리 재현 스크립트(`/tmp/s4_probe/probe.py`, 지움 가능): N1·N3·N4·N5 재현, 6·7·9 확인. 9 번: `.prev.json` 에 dict 아닌 항목·`text` 가 문자열 아닌 항목이 섞여도 건너뛰고, 잘못된 `stt_used`·`at` 은 `None` 으로 읽는다.

## 변이 검사 (/tmp 사본에서 핵심 줄을 되돌림, `test_store.py` 만)

| 변이 | 결과 |
| -- | -- |
| M1 상한 자르기 삭제 | 잡힘 |
| M2 같은 글 중복 제거 (2) 삭제 | **못 잡음 (R52-N2)** |
| M3 지금 글과 같은 벌 빼기 (1) 삭제 | 잡힘 |
| M4 옛 `.prev.txt` 이어받기 삭제 | 잡힘 |
| M5·M5b delete 의 두 경로 중 하나만 삭제 | 동치(하나가 다른 하나를 덮음) - 못 잡는 게 맞음 |
| M6 응답 순서를 오래된 것이 앞으로 | 잡힘(6건) |
| M7 `at` 안 남김 | 잡힘 |
| M8 `stt_used` 안 남김 | 잡힘 |
| M9 `.prev.txt` 안 지움·`prev_stt_used` 안 지움 | 잡힘 |
| M10 공백만 다른 글도 밀어냄 | **못 잡음 (R52-N6)** |
| M11 응답에 `transcript_prev` 되살림 | 잡힘 |
| M12 목록 응답에 `prev_stt_used` 되살림 | 잡힘 |
| M13 `PREV_KEEP=3` | 잡힘 |
| M14 새 벌을 앞에 끼움 | 잡힘 |

화면 변이(W1 키 비교 삭제=항상 다시 그림, W2 `textContent`→`innerHTML`, W3 `sw.js` VERSION 되돌림)는 브라우저 검사가 한 번에 수 분이라 돌리지 않고 시험 코드를 읽어 판정했다:
W1 은 56 번(폴링 2번 뒤 `open_states == [True, True]`)이 잡는다. W2 는 지난 글 본문을 위한 XSS 시험이 없어 **못 잡을 가능성이 크다**(R52-N6). W3 은 `VERSION` 을 보는 시험을 찾지 못함 - 못 잡는다(하, 캐시 갱신은 사람이 확인).

## 판정

끝난 기준 네 가지는 모두 충족, 단위 300 OK·브라우저 56/56 통과. 상 등급 없음, 중 1(R52-N1 빈 결과가 지금 글을 비움), 하 5(N2~N6).

판정: 조건부(상 0·중 1)
