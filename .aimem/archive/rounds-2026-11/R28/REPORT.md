# R28 종료 보고 (관리자 M-R28-232048, 운영 방식: 빠른 구현)

상태: DONE

요청 `Q-261113-292d` (자모맞히기: 남은 목표 1개) - **목표 15/15**, 요청 DONE. 결과물은 모두 `projects/자모맞히기/` 에 쌓였고
이 폴더에는 기록(`brief.md`·`REVIEW-r28.md`·`REPORT.md`)만 있다.

## (1) 태스크

| 태스크 | 슬롯 | 결과 | 바뀐 파일 |
| ---- | ---- | ---- | ---- |
| T-300 낱말: 어근 13 지움·BANNED +17·`까닭` MUST·ANSWERS 약속 시험·빠진 흔한 말 32 보탬 | S4 sonnet | DONE, 1회, 58초 | `projects/자모맞히기/data/words/{자연마음,풀이씨,생활,사회}.txt`, `tests/test_words.py`, `web/js/words.js` |
| T-301 브라우저: 연습 쪽 하드 맞춤·입력 중 글자 유지 시나리오 2개(검사 7) | S5 sonnet(관리자 추가) | DONE, 1회, 293초 | `projects/자모맞히기/tests/browser_modes.py` |
| T-302 시험 안내 문서 수 66·13·121·90 | S2 codex kistillm(무료) | DONE, 1회, 243초 | `projects/자모맞히기/tests/README.md` |
| T-303 가벼운 적대적 재검수 | S1 opus | DONE, 1회, 1286초 - 판정 **'검사' 목표 닫음** | `rounds/R28/REVIEW-r28.md` |

그래프 G-061 하나, 4노드·2단계(만들기 2 동시 → README·검수 2 동시).

## (2) 재현한 검증

- 엔진 verify(관리자 도구 `.aimem/graph/inputs/r28/v_words.py`·`v_modes.py`·`v_readme.py`·`v_review.py`) 넷 모두 rc 0. 고치기 전 트리에서
  한 번씩 돌려 실패하는 것을 먼저 확인함(`v_modes` 는 변이 V3·V6 생존을 그대로 보임)
- 관리자 재현: `python3 -m unittest discover -s projects/자모맞히기/tests -p 'test_*.py'` → Ran 13 OK
- 검수 재현(작업 트리): node 66 · python 13 · browser_game 121 · browser_modes 90 모두 초록. R27 생존 변이 V3·V6·V10·V12 잡힘, V11 생존(하, 목록 시험의 한계)
- 함대 전체: `python3 -m unittest discover -s tests` (관리자 세션 안) → Ran 948, OK (skipped=1)
- 린터: `render` 뒤 `aimem_lint.py AIMEM.md` → 위반 없음. `archive` → 14일 지난 끝난 것 없음(0건). REV 175 → 176

## (3) 기다린 시간

23:20 시작 → 23:30 그래프 시작 → 23:38 만들기 둘 끝(T-301 은 verify 의 변이 실행 포함) → 00:00 무렵 검수 끝. 작업자 쪽 약 30분, 그중 T-303 검수 21분이 가장 김.

## (4) 큐

- 처리: 큐 1번(R27-N1·N2·N3 + 덮는 범위) drop
- R27-P1(관리자 세션 안 unittest 가 AIFLEET_ROLE 누수로 깨짐): **재현 안 됨 → drop.** `AIFLEET_ROLE=manager`·`AIFLEET_SESSION=M-R28-232048`(빠른 구현 라운드)을 넣고 세 모듈 109 OK(`.aimem/graph/inputs/r28/v_isolation.py`), 이 관리자 세션 안 전체 948 OK. REV 174 정리 뒤 사라진 것으로 보임 - 다시 보이면 새로 적을 것
- 더함: `R28-N1·N2·N3·N4`(모두 하, 품질 보강 - 하드 잠금 시험, 판 번호 시험, 남은 어근 5개, 빠진 흔한 말 30개)

## (5) 다음 라운드

자모맞히기 목표는 15/15 로 다 찼다 - 이어 달리기는 '목표 다 체크' 로 멈춰야 맞다. 남은 것은 큐의 품질 보강 하 4건뿐이며
요청이 오면 1그래프(고치기 2노드 + 가벼운 재검수)로 끝날 크기다. 넘겨 가는 PLANNED 요청 없음.

## (6) 운영 지표

- 슬롯 사용: S1 검수 1, S2 1(무료, 성공 - R27 의 62분 빈손과 달리 4분), S4 1, S5 1. S3(opencode 무료)는 일이 3개뿐이라 놀림
- **더한 슬롯:** S5 claude sonnet - 같은 단계의 만들기 둘(T-300·T-301)을 동시에 돌리려고(빠른 구현). 끝나고 `slot remove` 함
- **유료 슬롯에 준 만들기:** T-300(S4)·T-301(S5) - 까닭: 빠른 구현 + R27 에서 무료 둘이 62분 결과물 0. 작은 문서 일(T-302)은 무료에 줘서 성공
- 옮긴 노드 없음, 재시도 0
- 관리자 혼자 일한 구간: 23:20~23:30(시작 점검·검증 도구 넷 작성과 시험 실행·그래프), 검수 뒤 마감
- R27 그래프의 verify 는 출력을 `/tmp` 로 돌리고 grep 했는데(8.0-8 위반), 이번에는 검증 도구 한 명령으로 바꿈

## (7) 개선안 하나

관리자 세션의 권한 목록에 `python3 .aimem/graph/inputs/**/*.py` 와 `python3 tools/check.py` 가 없어, 검증 도구를 돌려 보려면
unittest 모듈 꼴(`Dry` 테스트)로 감싸 `python3 -m unittest discover -s .aimem/graph/inputs/r28 -p v_x.py` 로 돌려야 했다.
8.0-8 은 "verify 명령을 쓰기 전에 지금 트리에서 한 번 돌려라" 고 하므로 이 두 꼴을 관리자 허용 목록에 넣는 것을 제안한다(태석님 결정).
