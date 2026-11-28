# R53 적대적 검수 - VoxLog 큐 하 등급 정리 (S4, 부작용 중심)

대상: `git diff -- projects/VoxLog` 전체(REV 209 위 미커밋). 약속 `rounds/R53/spec.md`. 코드는 고치지 않았다.

## 돌린 검사

- 단위 `python3 -m unittest discover -s tests` (projects/VoxLog): `Ran 314 tests in 87.133s` · `OK`
- 브라우저 `python3 tests/browser_voxlog.py` **두 번**:
  - 1차 `실패한 항목: 50 ... 본문이 다름: '{"options":{}}'` · `63/64 통과`
  - 2차 `64/64 통과`
  → 같은 코드에서 한 번 실패·한 번 통과 = 타이밍에 달린 실패 (R53-N1).
- 직접 확인(/tmp 가짜 입력, `normalize({"context": ...})`): 한글·`❤️`(VS16)·탭·줄바꿈은 그대로.
  `👨‍👩‍👧` → `👨👩👧`(ZWJ 빠짐), 🏴󠁧󠁢󠁥󠁮󠁧󠁿(영국 깃발, 태그 문자 Cf) → `🏴`, `\r` 도 빠짐, `U+2028` 은 남음.
- 변이(7): 사본 복사(`cp -r`)가 이 세션에서 승인이 필요해 **돌리지 못했다.** 시험 코드를 읽어 판정했다(아래 7절).

## 지적

### R53-N1 (중) 설정·상세 옵션 칸을 열 때의 새로 읽기가 사람이 방금 고른 값을 덮는다 (브라우저 50 이 흔들림)

`web/app.js` `openSttPanel`(약 315행)이 `state.sttDefaults = null` 로 캐시를 비운 뒤, 옵션 없는 녹음이면
`fillSttFields(detail, {})` → `sttDefaults().then(fill)` 한다. 예전엔 캐시가 있어 곧바로 풀렸지만 이제는 매번 네트워크
왕복이라, 응답이 오기 전에 사람이 전처리를 `denoise` 로 고르면 응답이 와서 전체 기본값(빈 값)으로 **덮어쓴다.**
`.then` 안 가드는 "같은 녹음·칸이 열려 있나"만 보고 "사람이 손댔나"는 안 본다.
설정 칸(`openSettings` 279~281행)도 같은 꼴(열린 직후 입력이 응답에 덮임). 약속의 "열려 있는 동안엔 덮지 않는다"와도 어긋난다.

재현: 브라우저 50 - 2회 중 1회 실패(첫 재시도 본문이 `{"options":{}}`). 느린 폰 회선이면 사람이 직접 겪는다.
고치는 방향(구현은 안 함): 응답 때 칸이 아직 처음 채운 그대로일 때만 채우거나(손댄 표시), 새로 읽은 값을 캐시에만
넣고 이미 열린 칸은 덮지 않는다. 시험 50 은 이 경합을 일부러 만들도록(응답 지연 주입) 고칠 것.

### R53-N2 (하) context 의 Cf 거르기는 이모지 ZWJ·태그 순서를 깬다 (영향은 작음)

위 직접 확인대로 ZWJ(U+200D) 이모지는 낱개 이모지가 되고 태그 순서 깃발은 기본 깃발이 된다. `context` 는 받아쓰기 힌트
(회의 이름·참석자 이름)라 음성 인식에 이모지가 쓰일 일이 거의 없어 **판단: 감수 가능, 한글에는 영향 없음**
(한글 자모·완성형은 Lo, `U+FE0F` 는 Mn 이라 남음, ZWNJ 는 한글에 안 쓰임). 다만 (a) 시험이 한글·이모지를 안 본다
(`test_stt_options` 는 ZWSP·소프트 하이픈·BOM·NUL 만) - 한글 한 줄과 `❤️` 가 그대로 남는다는 단언 하나가 있으면 좋다.
(b) `U+2028/2029`(Zl/Zp) 는 안 걸러지고, 맨 `\r` 은 빠져 줄이 붙는다(CRLF 는 `\n` 만 남아 무해). INTERFACE.md 문구
"형식 문자(Cf)와 제어 문자(Cc)" 는 실제와 맞다.

### R53-N3 (하) 시험 64 의 가짜 응답이 `?prev=0` 응답에도 `prev_transcripts` 를 실어 보내, "키 없는 응답은 지난 글 묶음을 안 건드림"을 못 본다

`browser_voxlog.py` t64 의 `inject` 는 `prev=0` 이 URL 에 있으면 `prev_transcripts` 를 넣는다(실제 서버는 키를 뺀다). 그래서 이
시험은 폴링 URL 에 `?prev=0` 이 붙는 것과 끝난 뒤 전체 읽기가 한 번 더 나가는 것만 본다. 지난 글 펼침 유지(R52-N5 셋째 줄)는
t56(주입 옵션·폴링 뒤 펼침 유지)이 맡고 통과했다. 코드(`Object.prototype.hasOwnProperty.call(r,'prev_transcripts')`)는
읽어서 맞다. 가짜 응답을 실제 모양(키 없음)으로 바꾸면 더 확실하다.

### R53-N4 (하) `_rec_retry` 첫 404 확인이 지난 글 파일까지 읽는다

`serve.py` `_rec_retry` 첫 줄 `store.get(rid)` 는 `with_prev=True` 라 `.prev.json`·`.prev.txt` 를 읽고 버린다. 잠금 밖이라 느려짐·교착은
아니고 작은 낭비. `with_prev=False` 로 충분(잠금 안 두 번째 `get` 은 `stt_options` 만 쓰므로 거기도 같음).

### R53-N5 (하) 깨진 `.prev.json` 은 다음 쓰기에서 조용히 덮인다 (결정대로, 기록만)

R52-N3 결정(없는 것처럼 보고 `.prev.txt` 이어받기)대로 동작하고 단위 검사(`test_broken_prev_json_falls_back...`)가 받친다.
`.prev.txt` 가 없으면 `[]` 이고 다음 `set_transcript` 가 새 `.prev.json` 을 쓰며 깨진 원본은 남지 않는다. 쓰기는 원자적이라
깨질 일이 드물고 복구할 내용도 이미 못 읽는 상태라 등급 하. 조치 불필요.

## (1) 큐 항목 닫힘 표

| 항목 | 내용 | 닫힘 | 근거 |
|---|---|---|---|
| R51-N4 | 깊은 JSON → 400 | 닫힘 | `_read_json_body` 가 `RecursionError` 포함, 네 경로 공용. `test_ask_deep_json_body_400`·`test_deep_json_put_and_retry_400`·`test_patch_deep_json_body_400` |
| R51-N5 | context Cf·Cc 거르기 | 닫힘(N2 하) | `stt_options.normalize`, 단위 5줄 |
| R51-N6 | 설정·상세 열 때 기본값 새로 읽기 | **조건부** | 새로 읽기는 되나 R53-N1 경합. t62 통과 |
| R51-N7 | 둘째 줄 안 고침(결정) / 셋째 줄 | 닫힘 | 셋째 줄은 `state.detailId === id` 가드, t65 통과. 둘째 줄은 결정대로 |
| 검사 구멍 F2·F4·F6 | 펼침 유지·격리 출처·토스트 innerHTML | 닫힘 | t56·t58·t59/t60 통과 |
| 검사 구멍 M10 | resubmit 실패 시 옵션 되돌림 | 닫힘 | `test_retry_resubmit_false_restores_old_options` |
| R51-N11 | 재시도 잠금 | 닫힘 | `retry_lock`, `test_retry_lock_keeps_first_job_when_two_retries_overlap`(결과 `[200,409]`·`stt_job`=job-first) |
| R51-N12 | 시험 빈틈 | 닫힘 | 위 M10 시험·잠금 시험 |
| R51-N13 | 빈 값 이름 | 닫힘 | `detailEmptyLabel`·`defaultOpts`, t61 |
| R51-N15 | 새 문구 시험 | 닫힘 | t61·t63·`test_screen_text_matches_prev_keep_count` |
| R52-N2 | 같은 글 중복 제거 (지우지 않고 검사로) | 닫힘 | `test_legacy_prev_txt_same_as_current_is_deduped_on_retranscript`·`test_whitespace_only_difference...` |
| R52-N3 | 깨진 `.prev.json` | 닫힘 | `test_broken_prev_json_falls_back_to_prev_txt_and_absorbs`, 문서 갱신 |
| R52-N4 | `get` 의 같은 글 빼기 | 닫힘 | `test_get_hides_prev_entry_equal_to_current_text` |
| R52-N5 | `?prev=0` | 닫힘(N3 하) | `test_get_without_prev_does_not_read_prev_files`, t64·t56 |
| R52-N6 | `5벌` 문구 묶기 | 닫힘 | `test_screen_text_matches_prev_keep_count` |
| R52-N7 | 문서에 빈 결과=실패 | 닫힘 | README 해당 문장 추가 |
| R52-N8 | 상세 `이전 글 그대로 N자`·상수 | 닫힘 | `EMPTY_TEXT_ERROR`·t63 |
| R52-N9 | 옛 빈 글 그대로(결정) | 닫힘 | 코드 무변경, 근거 spec |
| R52-N10 | `_process` 군더더기·상수 통일 | 닫힘 | `stt.py` diff, `test_command_blank_result_failure_uses_empty_text_error` |

## (2) 재시도 잠금

- 잠금 안: busy 검사 → 옛 옵션 읽기 → 새 옵션 저장 → `set_job(None)` → `resubmit` → 실패 시 되돌림. 본문 읽기(`_read_json_body`)는
  잠금 **밖**(느린 클라이언트가 잠금을 쥐지 않음). 응답용 `store.get` 도 잠금 밖.
- 교착: 잠금 순서는 `retry_lock → store._lock / Transcriber._lock` 한 방향뿐이고 거꾸로 `retry_lock` 을 잡는 곳이 없다. 안쪽 호출은
  디스크 쓰기 몇 번이라 짧다. 업로드·조회·PATCH 등 다른 요청은 이 잠금을 안 쓰므로 막히지 않는다. 서버 전역 잠금 하나라서 서로 다른
  녹음의 재시도끼리는 직렬이지만 그 구간이 밀리초 단위라 감수 가능.
- 업로드 쪽 `submit` 은 잠금 밖이지만 `resubmit` 이 `_active` 를 다시 검사하므로 이중 투입은 막힌다(전부터 같음).

## (3) `?prev=0` 폴링·펼침 유지

- 되풀이 읽기만 `?prev=0`(`omitPrev` 는 호출 시점의 `detailStatus` 가 바쁠 때 + poll 일 때). 응답 상태가 더는 바쁘지 않으면 곧바로
  전체 읽기를 `afterBusy` 로 한 번 더 한다 → 끝나는 순간 지난 글을 놓치지 않는다(전체 읽기가 실패하면 다음 목록 폴링·사람 동작 때까지
  지난 글이 옛 모양이나, 그때는 상태가 바쁘지 않아 폴링도 안 돌므로 **전체 읽기 실패 시 새로고침 전까지 옛 지난 글이 남을 수 있음** - 드문 경로, 하에 못 미쳐 기록만).
- `renderPrev` 는 내용 키(JSON)가 같으면 다시 안 그려 펼침이 유지되고, 키 없는 응답은 건드리지 않는다. t56 이 확인.

## (5) 깨진 `.prev.json`·같은 글 빼기

`_read_prev_list` 는 읽기 실패·목록 아님이면 `.prev.txt` 길로 간다. 지난 글을 **잃는 길은 못 찾았다**: 같은 글 빼기는 표시에서만
빼고 파일은 그대로이며, 쓰기(`set_transcript`)는 새 글과 같은 벌을 거르고 최신 쪽을 남기므로 정보가 줄지 않는다. 표시의 `지난 글 N벌` 은
저장 벌 수보다 적을 수 있으나(같은 글은 옛 자료에서만 생김) 의도된 동작.

## (6) 새 문구·빈 값 이름

- `이전 글 그대로 N자`: `status=failed` 이고 `chars` 가 있을 때만. 받아쓰기 실패는 `set_status` 만 바꿔 글·`chars` 가 그대로이므로 사실과 맞다. 첫 받아쓰기가 비어 실패한 녹음은 `chars` 가 없어 이 말이 안 붙는다(맞음).
- `EMPTY_TEXT_ERROR` 의 "옵션을 바꿔 다시 받아써 볼 수 있음" 은 격리 출처(`isolated()`)에선 옵션 칸이 숨겨져 안 맞지만 그 출처는 편집 자체를 막는 곳이라 문제 아님.
- 빈 값 이름은 칸을 채울 때마다 맞춘다. 칸이 열린 채 다른 기기가 옵션을 바꾸면 이름이 낡을 수 있으나 칸 값도 안 덮는 설계라 일관.

## (7) 변이 판정 (실제로 돌리지는 못함 - 시험 코드를 읽어 판정)

| 변이 | 걸림 | 근거 |
|---|---|---|
| 재시도 잠금 제거 | 걸릴 것 | `test_retry_lock...` 가 `set_stt_options` 를 지연시켜 두 요청을 겹침. 잠금이 없으면 둘째가 옵션을 `level` 로 쓰고 `stt_job`/옵션 단언이 어긋남 |
| 본문 읽기를 잠금 안으로 이동 | **못 걸림** | 동작은 같고 지연만 늘어 시험이 이를 보지 않음(교착·느려짐은 시험 밖). 하 |
| `get` 의 같은 글 빼기 제거 | 걸릴 것 | `test_get_hides_prev_entry_equal_to_current_text` |
| 깨진 `.prev.json` 이어받기 되돌림 | 걸릴 것 | `test_broken_prev_json_falls_back...` |
| `with_prev=False` 가 파일을 읽음 | 걸릴 것 | `test_get_without_prev_does_not_read_prev_files` |
| JS `omitPrev` 제거(항상 전체 읽기) | 걸릴 것 | t64 가 URL 에 `prev=0` 이 나가는지 봄 |
| JS 끝난 뒤 전체 읽기 제거 | 걸릴 것 | t64 가 끝난 뒤 지난 글 묶음 표시를 봄 |
| JS `hasOwnProperty` 가드 제거 | **못 걸릴 수 있음** | t64 의 가짜 `?prev=0` 응답이 키를 싣고 옴(R53-N3) |
| context Cf 거르기 제거 | 걸릴 것 | `test_stt_options` 의 ZWSP·BOM 단언 |
| `이전 글 그대로` 문구 제거 | 걸릴 것 | t63 |
| `retryWithOptions` 의 `detailId === id` 가드 제거 | 걸릴 것 | t65 |
| 설정·상세 열 때 캐시 비우기 제거 | 걸릴 것 | t62 |

## 다음 담당자에게

1. R53-N1 은 R53 이 새로 만든 회귀다. 시험 50 이 흔들리는 것 자체가 단서이므로, 고친 뒤에는 응답 지연을 주입해 결정적으로 재현하는 시험으로 바꾸고 50 을 여러 번 돌릴 것.
2. N2~N5 는 하. 닫아도 되고 큐에 둬도 된다.
3. 변이는 /tmp 사본이 열린 세션에서 위 표의 "못 걸림" 두 줄만 실제로 돌려 확인하면 된다.

판정: 조건부(상 0·중 1)
