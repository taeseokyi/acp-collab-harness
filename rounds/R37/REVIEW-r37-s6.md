# R37 검수 기록 - 자모맞히기 코드 검수 (S6 freebuff, 읽기 전용)

요청 `Q-261123-f11a`, 그래프 G-078. 검수자는 S6(freebuff, 사람 승인 슬롯 - 이번에는 '미리 고른 문구 자동 전송'). S6 는 파일을
쓰지 않고 답만 냈고, 관리자가 그 답을 추려 여기에 옮겼다. 관리자가 코드에서 다시 확인한 것은 `[확인]` 으로 적었다.
이 라운드에서는 코드를 고치지 않았다 - 아래 항목은 모두 대기 큐로 갔다.

| 노드 | 범위 | 결과 | 원문 |
| ---- | ---- | ---- | ---- |
| T-369 | 서버 쪽 파이썬 6파일 | 시도 1 DONE, 발견 7건 | `.aimem/sessions/T-369-S6-a1-141250/report.md` |
| T-370 | 화면 쪽 web | 시도 1 은 30분 한도에 잘림(답 거의 다 씀, 엔진이 거둔 보고는 한 줄), 시도 2 는 **빈 보고로 done** | 시도 1 의 잘린 답: freebuff 대화 파일 `~/.config/manicode/projects/ai-fleet/chats/2026-11-23T05-41-36.726Z/chat-messages.json` 마지막 메시지 (태석님이 INBOX 로 알려 줌) |

## 발견 (프로젝트 - 대기 큐 `[자모맞히기]`)

- **R37-N1 [중] 생성물 `web/js/words.js` 가 `data/trend.txt` 보다 낡음** (T-369 #1, T-370 #1 이 같은 것을 따로 찾음).
  trend.txt 는 2026-12-05 까지 21줄, words.js 의 TREND 는 11-21 까지 7개, ALLOWED 에 6낱말(위반·감찰·강화·복귀·아시아·확대) 빠짐.
  `test_words.WordsTest.test_rebuild_is_byte_identical` 이 빨강. 서버 없이 `web/` 만 열면 11-22~12-05 정답이 서버 모드와 갈린다.
  `trend_meta.json` 의 last_run 은 11-15 라 11-22~ 줄이 어느 경로로 들어갔는지도 확인할 것.
  `[확인]` 관리자가 `python3 -m unittest discover -s tests` 로 133 중 1 실패 재현
- **R37-N2 [중] 6칸이 아닌 트렌드 정답을 서버·화면 모두 거르지 않아 오늘 판이 빈 채로 죽음** (T-369 #2 + T-370 #2).
  `trend_store.py:41` `_is_word` 는 공백만 보고, `web/js/trend.js:3` `WORD_RE = /^[가-힣]{1,10}$/` 는 음절 수만 본다 →
  `ui.js:811` `toUnits(answerForDate(...))` → `game.js:144-147` `checkAnswer` 가 예외 → `ui.js:896` `startDaily()` 가 try 밖이라 화면이 빈 채.
  재현: `data/trend.txt` 에 `2026-11-23 사과` 를 넣고 serve.py 로 연다(README 의 '어색한 낱말 빼기' 처럼 사람이 줄을 고치는 흐름이 있다).
  `build_words.py:123` 은 6칸을 걸러 버리는데 서버 경로만 빠졌다. `[확인]`
- **R37-N3 [하] `serve.py` `_api` 에서 난 예외가 응답 없이 연결을 끊음** (T-369 #3·#7). `POST /api/trend/pick` 의 저장 실패(권한·디스크)
  는 `RemoteDisconnected` + 서버 traceback 만(재현함: trend_path=`/proc/1/trend.txt`), 화면은 '서버 없음' 으로 보여 까닭을 모른다.
  같은 길로 `dict_server.py:304-305` 캐시 축출(`_CACHE.pop(next(iter(_CACHE)))`)이 동시 조회에서 `KeyError` 를 낼 수 있음(추정). `[확인]`
- **R37-N4 [하] 덧붙인 줄이 0개여도 `last_run` 을 새로 적고, 명령줄은 저장 안 된 줄을 저장한 것처럼 찍음** (T-369 #4).
  `trend_store.py:143-146`, `tools/pick_answers.py:61-73`. 설정 창이 '방금 정함' 으로 바뀌지만 정답표는 그대로. 의도일 수 있음 - 고칠지 정할 것. `[확인]`
- **R37-N5 [하] Origin 머리 없는 GET 이 출처 검사를 통과** (T-369 #5). `serve.py:95-101`. 남의 페이지의
  `<img src="http://127.0.0.1:<port>/api/lookup?word=…&source=stdict">` 가 서버가 가진 키로 실제 조회를 일으켜 한도를 태운다(응답은 못 읽음).
  로컬 전용이라 피해는 작다. `[확인]`
- **R37-N6 [하] `trend_news.verify(..., opener=)` 가 위키가 아닌 출처에서 무시됨** (T-369 #6). `trend_news.py:232-241`.
  시험이 전역 monkeypatch 로 우회하고 있다.
- **R37-N7 [하] 외부 사전 출처 안내 글이 사실과 다름** (T-370 #3). `ui.js:560-568` `sourceNote`: 서버가 없으면 gemini·openrouter-free 에
  `(serve.py 필요)` 를 붙이지만 사용자 키가 있으면 브라우저가 직접 부른다. 서버가 있고 `.env` 키가 없으면 `(키 없음)` 이지만 사용자 키로 된다. 표시만 틀림.
- **R37-N8 [하] LLM 답 `네` 를 못 읽음** (T-370 #4). `dict.js:66-73` `parseLlmAnswer` 는 `예`/`yes`/`아니`/`no` 만 본다. `[확인]`
- **R37-N9 [하] 쓸데없이 복잡한 곳** (T-370 #5): API 키 한 글자마다 `renderDictSelect()` 로 `<select>` 재생성(`ui.js:633-637`),
  `renderAll` 이 칸마다 `game.rows` 복사(36번, `ui.js:134`), 날짜 키 포맷 세 벌(`game.js dayKey`·`storage.js todayKey`·`ui.js dayKeyOf`),
  `hasStoredSettings()` 중복(`ui.js:78, 886-891`).

## 확인했고 문제 없다고 본 곳 (S6 답 요약)

서버: trend_store 잠금(스레드 락+flock+임시 파일→replace, 있는 날짜 안 덮음), Host/Origin 검사(DNS 되돌림·교차 출처 POST),
`/api/trend/pick` 의 Content-Type·4KB·인자 검증, 사전 키 비노출, 429·deadline, build_words 의 분해·씨앗·정렬.
화면(T-370 시도 1 의 생각 글에서): `innerHTML` 0건(XSS 없음, textContent 만), 키는 평문 localStorage(문서화됨), 저장소 읽기 실패는
try/catch 로 메모리 폴백, `scoreGuess` 무작위 2만 번 대조 불일치 없음.

## 발견 (함대 - 대기 큐 `[함대]`)

- **R37-N10 [중] freebuff 하네스가 '답 글 없이 끝난 턴' 을 빈 보고 rc 0 으로 내고, 엔진이 쓰기 경로 없는 노드를 그대로 done 으로 받음.**
  T-370 시도 2: 대화의 마지막 ai 메시지가 `isComplete` 인데 마지막 조각이 도구 호출이고 글이 없었다 → `final_text` 가 `""` →
  `end ok:true result:""` → G-078 이 `done T-370`. `report.md` 0바이트. 엔진의 `report_ended_in_tool_call`·`wrote_nothing` 은
  빈 보고 + 빈 write 를 거르지 못한다. 고칠 곳: `tools/fleet_rt/harness/freebuff.py` `_work`(글 없는 완료는 실패나 '더 기다림'),
  `tools/fleet_graph.py`(rc 0 이라도 보고가 비면 done 아님). freebuff 가 왜 글 없이 턴을 끝냈는지(단계 상한 등)는 팬을 못 봐서 모름.
