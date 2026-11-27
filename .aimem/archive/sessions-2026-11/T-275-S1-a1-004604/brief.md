SLOT=S1 T-275 검수: R22-P4·S1·S2·Q3·Q4 수정이 닫혔는가 (FIFO·메타 상한·시험 구멍) (G-055)
확인토큰: a41f0c
AIMEM REV: 164
너는 S1 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: rounds/R22/REVIEW-r22-4.md
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

# T-275 **검수** - 큐 두 건(R22-P4, R22-S1·S2·Q3·Q4)의 수정이 정말 닫혔는가

쓸 파일은 **하나**입니다: `rounds/R22/REVIEW-r22-4.md` (새 파일). 저장소의 다른 파일은 고치지 마십시오. 변이는 저장소 사본에만.

## 고친 것

| 번호 | 무엇 | 고친 곳 |
| - | --- | --- |
| R20-N6 (= R22-P4) | `.out`·`meta.json` 이 FIFO 면 막힘 → `fleet.read_regular_bytes` (`O_NONBLOCK` + `S_ISREG`) | `tools/fleet.py`, `tools/fleet_graph.py` |
| R20-N8 | 메타를 크기 상한 없이 읽음 → 256 KiB 상한 | `tools/fleet.py` |
| R22-S1·S2 | context-window 시험 `assertIsNone`, 어댑터 except 갈래 시험 | `tests/test_fleet_graph.py`, `tests/test_rt_claude.py` |
| R22-Q3·Q4 | 브라우저 검사의 '이번 라운드' 값 고정 자료화, 넓은 폭 잘린 제목 펼침 갈래 | `tests/browser_monitor_ui.py` |

근거 보고서: `rounds/R20/REVIEW-r20.md`(N6·N8), `rounds/R22/REVIEW-r22.md`(Q3·Q4), `rounds/R22/REVIEW-r22-3.md`(S1·S2).

## 방법

1. 저장소를 `/tmp` 로 복사(`.aimem/tls/` 제외, `.git`·`.aimem/runs`·`__pycache__` 도 빼도 됨). 끝나면 그 `/tmp` 폴더를 `rm -rf`
2. 사본에서 **전체** `python3 -m unittest discover -s tests` 와, `projects/`·`.aimem` 을 치운 사본에서 `python3 tests/browser_monitor_ui.py`
3. 수정마다 옛 모습으로 되돌리는 변이를 넣어 시험이 빨개지는지 (FIFO 검사 지우기, 크기 상한 지우기, fd 닫기 지우기, `fleet.RUNS` 갈아끼우기 지우기 등)
4. 새 결함: `read_regular_bytes` 가 심볼릭 링크·권한 없는 파일·딱 상한 크기에서 어떻게 되는지, fd 가 새지 않는지, 이 변경이 모니터(`tools/aimem_monitor/reader.py` 등 `fleet._run_meta` 를 부르는 곳)의 동작을 바꾸지 않는지

## 보고서

1. 닫힘표 `| 번호 | 닫혔나 | 근거 |` 2. 새 결함표 `| 번호 | 심각도 | 무엇이 | 어디 | 재현 | 고칠 방향 |` (없으면 "없음") 3. 변이표, 마지막 줄 `합계 <n>개: 잡힘 <a>, 생존 <b>` 4. 한 문단 총평

## 하지 말 것

제품·시험 고치기, `git commit`/`push`, 저장소 파일 삭제, 운영 모니터 부르기.
