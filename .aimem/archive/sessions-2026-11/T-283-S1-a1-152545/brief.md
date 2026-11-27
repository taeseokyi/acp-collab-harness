SLOT=S1 T-283 적대적 검수: 자모맞히기 1차 (규칙·판정·조합·자판·모드·저장·화면·낱말 목록·출처) (G-056)
확인토큰: a41f0c
AIMEM REV: 170
너는 S1 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: rounds/R24/REVIEW-r24.md
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

# T-283 **적대적 검수** - 자모맞히기 1차

쓸 파일은 **하나**: `rounds/R24/REVIEW-r24.md` (새 파일). 저장소의 다른 파일은 고치지 마십시오. 변이·실험은 `/tmp` 사본에서.

## 무엇을 만들었나

`projects/자모맞히기/` - 한글 낱말을 자모 여섯 칸으로 풀어 여섯 번 안에 맞히는 정적 웹 게임(요청 `Q-261113-bd56`: `.aimem/requests/Q-261113-bd56.json`). **`projects/웹워들/` 을 복사해 자모에 맞게 바꾼 것**입니다. 약속은 `.aimem/graph/inputs/r24/CONTRACT.md`, 규칙 정본은 `projects/자모맞히기/README.md` '규칙' 절. 바뀐 파일: `web/js/jamo.js`(새), `web/js/game.js`, `web/js/ui.js`, `web/index.html`, `web/css/style.css`, `web/js/storage.js`, `web/js/words.js`(생성물), `tools/build_words.py`, `data/*`, `tests/*`.

## 방법

1. 저장소를 `/tmp/r24-review/` 로 복사(`.aimem/tls/`·`.git`·`.aimem/runs` 제외). 끝나면 그 폴더를 `rm -rf`.
2. 사본에서 `node --test projects/자모맞히기/tests/*.mjs`, `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_*.py'`, `python3 projects/자모맞히기/tests/browser_game.py` 를 돌려 수를 적음.
3. 변이: `jamo.js` 의 겹받침·겹모음 표 한 줄 지우기, `composeUnits` 받침 넘김 끄기, `scoreGuess` 남은 개수 무시, KEYMAP 한 키 바꾸기, Shift 한 번 뒤 끄기 빼기, 연습 판이 통계에 기록되게, `#preview` 갱신 빼기, 320px 넘침(키 최소 너비 키우기) 등 **10개 이상** - 시험이 빨개지는지.
4. 새 결함 찾기: 규칙과 도움말·README 가 일치하는가(겹받침 11·겹모음 7 표), 판정의 겹친 자모, 한/영 입력기 상태(`e.key === 'Process'`)에서도 실물 자판이 되는가, 저장값 손상, 날짜 경계, 연습/날마다 오가기·뒤집기 중 모드 바꿈, 접근성(aria-label·aria-live), 폰 폭·어두운 모드에서 대비, 낱말 목록의 질(**정답 후보에 어색한 말·비표준어·고유명사·비속어가 섞였는지 표본 50개를 직접 보고 비율을 적기**, 흔한 6칸 낱말이 ALLOWED 에서 빠져 추측이 거절되는 예), 외부 게임(꼬들)의 이름·문구·색·목록이 들어오지 않았는가, `app.json` 이 모니터 결과물 실행 규칙(`projects/웹워들/app.json` 과 같은 꼴)에 맞는가.

## 보고서

1. 요약(검사 수, 변이 잡힘 수) 2. 새 결함표 `| 번호 | 심각도 | 무엇이 | 어디 | 재현 | 고칠 방향 |` - 번호는 `N1`, `N2` … (없으면 "없음") 3. 변이표, 마지막 줄 `합계 <n>개: 잡힘 <a>, 생존 <b>` 4. 낱말 목록 표본 판정 5. `PROGRESS.md` 의 `## 목표` 15개 각각에 대해 `| 목표 | 닫아도 되나(예/아니오) | 근거 |` 6. 한 문단 총평.

## 하지 말 것

제품·시험 고치기, `git commit`/`push`, 저장소 파일 삭제, 의존성 설치, 운영 모니터 부르기.
