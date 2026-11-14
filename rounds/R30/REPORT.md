# R30 보고 (관리자 M-R30-005228, 2026-11-14)

상태: DONE

할 일은 요청 `Q-261114-a3cf` 하나(자모맞히기 큐 R29-N1·N2, 모두 하)였고, 그래프 G-063 하나로 끝냈습니다. REV 177 → **178**. 커밋은 하지 않았습니다.

## (1) 태스크 표

| 태스크 | 슬롯 | 무엇 | 결과 |
| ---- | ---- | ---- | ---- |
| T-307 | S4 sonnet | R29-N1: `scenario_hard_locked_after_play` 에 저장된 설정 확인 검사 3개 + `tests/README.md` 수 | DONE - 모드 97 → 100, V19 잡힘 |
| T-308 | S3 → **S4** | R29-N2: `풀이씨.txt` 에 `배우다`, `words.js` 재생성 | DONE - ALLOWED 2182 (S3 이 3번 침묵해 옮김) |
| T-309 | S1 opus | 가벼운 적대적 재검수 `rounds/R30/REVIEW-r30.md` | DONE - 판정: R29-N1·N2 닫음, 새 결함 하 1 |

프로젝트별로 쌓인 곳:
- `projects/자모맞히기/tests/browser_modes.py`, `tests/README.md`, `data/words/풀이씨.txt`, `web/js/words.js`, `PROGRESS.md`(`## R30`)
- 라운드 기록: `rounds/R30/REVIEW-r30.md`, `rounds/R30/REPORT.md`. 관리자 검증 도구: `.aimem/graph/inputs/r30/`

## (2) 재현한 검증

- `python3 .aimem/graph/inputs/r30/v_modes.py` → 원본 `통과 100 / 전체 100` rc 0, V19 잡힘(97/100), V16 잡힘(94/95), `v_modes: 모두 통과`
- `python3 .aimem/graph/inputs/r30/v_words.py` → 낱말 시험 OK, ANSWERS 380 · ALLOWED 2182, `v_words: 모두 통과`
- 재검수의 네 벌: node 66 · python 13 · browser_game 121 · browser_modes 100, 모두 rc 0
- 함대 전체 `python3 tools/check.py --all` → `Ran 949 tests … OK (skipped=1)`. 린터 `aimem_lint.py AIMEM.md` → 위반 없음(render 뒤)

## (3) 기다린 시간

그래프 00:55:59 → 01:24:27, 약 **28.5분**. 이 가운데 약 19분(00:55:59 → 01:15:23)은 T-308 이 S3(opencode)에서 240초 침묵으로
세 번 다시 띄워진 시간입니다. S4 로 옮긴 뒤 T-308 은 14초 만에 끝났고, 재검수 T-309 는 약 9분.

## (4) 대기 큐

- 시작 1건(`[자모맞히기] R29-N1·N2`) → 처리하고 drop → **0건**
- 새 결함 R30-N1(하)은 INBOX 지시(클로드 코드·함대 운영, 00:52)에 따라 **큐에 넣지 않았습니다** - `PROGRESS.md` 남은 일과 아래 (7)에 적음

## (5) 다음 라운드

할 일 없음. 요청 NEW·PLANNED 0, 큐 0, 자모맞히기 목표 15/15. R30-N1 을 할지는 사람이 정합니다.

## (6) 운영 지표

- 슬롯 사용: S4 2노드(T-307 9분, T-308 14초), S1 1노드(9분), S3 1노드 배정(세 번 침묵, 결과 없음), S2 쓸 일 없음(대기)
- 관리자만 일한 구간: 시작 점검·검증 도구 작성 00:52 → 00:55:52, 마감 01:24 → 약 01:33
- 재시도: T-308 infra-requeue 2번(시도로 세지 않음) 뒤 INFRA 막힘. **노드 이동 1건: T-308 S3 → S4**(유료 sonnet) - 운영 방식(빠른 구현)이 막힌 노드를 바로 옮기라고 하고, 일이 한 줄짜리라 S2(kistillm 직렬)보다 빨랐음. 처음 move 를 시도했을 땐 노드가 아직 running 이라 거절됨(소유를 잠깐 옮겼다 되돌림)
- 슬롯 더함: 없음
- 유료 슬롯에 준 만들기: T-307(브라우저 시험, 운영 방식이 빠른 구현), T-308(위 이동)

## (7) 개선안

**opencode 무료 공급자 침묵.** S3(`opencode/deepseek-v4.1-flash-free`)이 R29 에선 쓸 일이 없었고 R30 에서 첫 배정에 240초 침묵을 세 번
냈습니다(약 19분 손실). 다음에 함대 쪽에서 S3 의 공급자 상태를 한 번 확인하고(빠른 구현 라운드에선 첫 침묵 한 번 뒤 바로 옮기는 편이 낫다 -
엔진이 INFRA 로 막기 전에도 `move` 를 받으면 좋겠습니다. 지금은 running 노드를 옮기지 못합니다).

품질 보강 거리(하, 큐에 안 넣음 - 사람이 정함): **R30-N1** 잠금 저장 검사가 한 방향만 봄. 하드 켠 판에서 줄을 낸 뒤 끄기를 시도할 때
`false` 를 저장하는 변이가 안 보임. 짝 시나리오 하나면 됨(`rounds/R30/REVIEW-r30.md` 4절).
