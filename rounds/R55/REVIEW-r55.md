# R55 적대적 검수 (S4, 부작용 중심)

대상: `git diff -- projects/VoxLog` (stt_options.py Cs 거르기, app.js `readSttDefaults`·`state.sttReads`·`saveSttDefaults`·`retryWithOptions` N4 가드, api.js signal, 문서, 새·바뀐 검사). 코드는 고치지 않았다.

## 직접 돌린 검사

- `python3 -m unittest discover -s projects/VoxLog/tests` → `Ran 318 tests in 121.552s` / `OK`
- `python3 projects/VoxLog/tests/browser_voxlog.py` → `77/77 통과`, 실패 0
- 정상 이모지: ZWJ 가족·깃발 태그열·국기·한글·결합 악센트가 든 문장이 `normalize` 뒤 그대로(`True`). JSON `"a😀b \ud83d c"` 는 짝은 😀 한 글자로 합쳐지고 외톨이만 빠짐(`'a😀b  c'`). 정상 이모지 영향 없음.

## 되돌려 보기 (사본 `/tmp/s4_mut_*`, 끝나고 지움)

| 되돌림 | 결과 |
| -- | -- |
| Cs 거르기 되돌림 | 단위 22·23 실패 → 잡힘 |
| api.js signal 줄 삭제 | 67·77·78 실패 → 잡힘 |
| 저장이 읽기를 안 끊음 | 77 실패 → 잡힘 |
| 저장 중 열기 읽기 가드(`sttSaving`) 삭제 | 77 실패 → 잡힘 |
| N4 가드(`seq` 비교) 삭제 | 75 실패 → 잡힘 (76 은 통과 - 성공 뒤 닫힘은 그대로) |
| 오류 쪽 `current()` 삭제 | 77·78 실패 → 잡힘 |
| 상세 닫기 칸의 abort 삭제 | 78 실패 → 잡힘 |
| 성공 쪽 `current()` 삭제 | 67·74·77·78 모두 통과 → **안 잡힘** (N3) |
| openDetail 의 abort 삭제 / 상세 `hasSttOptions` 분기 abort 삭제 | 각각 통과 → **안 잡힘** (서로 겹침, N3) |
| closeDetail 의 abort 삭제 | 통과 → **안 잡힘** (N3) |
| 저장 실패 때 `sttSaving=false`·잠금 풀기 삭제 | 49·52·67·77·78 통과 → **안 잡힘** (N3) |

## 눈여겨본 질문에 대한 답

- 끊긴 읽기가 상태 글·잠금·칸을 건드리는 길: 코드로 남은 길을 찾지 못했다. `abortSttRead` 가 `state.sttReads[bundle]=null` 을 동기로 하므로, abort 와 응답 도착이 겹쳐도(응답은 왔으나 `.then` 이 아직 안 돈 경우 포함) 두 처리기 모두 `current()` 가 거짓이라 아무것도 하지 않는다. 타임아웃으로 끊긴 읽기만 `current()` 가 참이라 `onFail('시간이 지났습니다')` 로 간다.
- 저장이 읽기를 끊은 뒤: 저장 성공이면 잠금 풀림·응답 값으로 채움, 실패면 `sttSaving=false`·잠금 풀림(코드로 확인, 검사는 N3).
- 설정과 상세는 `sttReads` 가 묶음별 칸이라 서로 끊지 않는다(코드로 확인, 둘을 함께 여는 검사는 없음 - N3).
- N4 가드: `seq` 는 `openSttPanel`·`openDetail`·`closeDetail` 에서만 오르고 폴링·`loadDetail` 은 올리지 않아, 같은 녹음 성공 뒤 칸 닫기와 실패 때 상태 글 지우기·토스트를 막지 않는다(76·75 로 확인).

## 지적

### R55-N1 (하) 저장 요청이 응답 없이 걸리면 설정 칸이 다시 읽히지도 풀리지도 않는다

`saveSttDefaults` 는 `sttSaving=true` 로 칸을 잠그고 PUT 의 응답·거절에서만 푼다. PUT 에는 읽기와 달리 시간 제한이 없고 `loadSttSettings` 는 `sttSaving` 이면 일찍 돌아간다. 연결이 걸린 채 응답도 거절도 없으면(모바일 PWA) 브라우저가 소켓을 포기할 때까지 칸이 잠기고 설정을 다시 열어도 읽지 않는다. 바뀌기 전에는 저장에 잠금이 없었다. 브라우저의 소켓 한도에서 결국 풀리므로 하. 고치려면 PUT 에도 같은 시간 제한을 두면 된다.

### R55-N2 (하) 읽기의 15초 제한이 fetch 가 시작된 뒤에만 듣는다

옛 코드는 손 타이머가 약속을 직접 거절했다. 새 코드의 타이머는 `ac.abort()` 만 부르고 `onFail` 은 fetch 의 거절을 거쳐야 호출된다. `api().json` 의 `getConfig()`(IndexedDB) 가 끝나지 않으면 fetch 가 시작되지 않아 abort 가 아무 데도 닿지 않고 칸이 잠긴 채 남는다. 옛 코드는 이 경우도 15초에 풀렸다. getConfig 는 실패도 `mem` 으로 받아 넘기므로 걸리는 일 자체가 드물어 하.

### R55-N3 (하) 새 검사가 안 잡는 곳

위 표의 "안 잡힘" 줄. 고침을 되돌려도 77/77 로 남는 것: ① 저장 실패 때 `sttSaving=false`·잠금 풀기(PUT 400 을 거는 52 는 이 칸을 확인하지 않음) ② `closeDetail` 의 abort(응답이 늦게 와도 `seq` 가 막아 동작은 같고 요청만 남음) ③ 성공 쪽 `current()`(`seq` 와 겹침 - 저장이 끊은 읽기는 mock 이 바로 거절해 성공 처리기에 오지 않음) ④ openDetail 과 상세 `hasSttOptions` 분기의 abort(서로 겹쳐 하나만 지우면 통과). 또 설정 읽기를 쥔 채 상세를 열어 서로 안 끊는지 보는 검사가 없다. ①이 가장 쓸모 있다: PUT 을 500 으로 막고 저장 뒤 칸·저장 단추가 풀리고 다시 열면 읽기가 나가는지 보면 된다.

### R55-N4 (하) 저장 쪽 abort 는 사람이 닿을 수 없는 길

읽는 동안 칸과 저장 단추가 잠겨(`setSttFieldsBusy`) 사람은 저장을 누를 수 없다. 77 은 `dispatchEvent(new MouseEvent('click'))` 로 잠긴 단추에 합성 클릭을 보내 이 길을 시험한다. 방어 코드로는 해롭지 않으나 실제로 닿는 경로의 검사가 아니다. 동작에는 문제 없음, 기록만.

## 문서·기타

- INTERFACE.md·README.md 의 Cs 설명과 설정 칸 서술은 코드와 맞다. sw.js VERSION 20→21 은 app.js·api.js 변경에 맞게 올랐다.
- R53-N10(15초 넘은 응답 버림)은 일부러 남긴 맞바꿈이라 지적하지 않았다.

판정: 통과
