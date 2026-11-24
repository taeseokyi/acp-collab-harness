# R47 보고 (관리자 M-R47-000825, 2026-11-25)

상태: DONE

요청 `Q-261125-f9f0` [VoxLog] 대기 큐 R46-N1·N2 처리 → DONE. 운영 방식 무료 중심, VoxLog 관리 방식 품질 우선. REV 203 → 204.

결과물: `projects/VoxLog/docs/INTERFACE.md`, `projects/VoxLog/docs/RESEARCH-draft-owner.md`, 기록 `projects/VoxLog/PROGRESS.md` `## R47`.

## (1) 태스크

| 태스크 | 슬롯 | 내용 | 결과 |
| --- | --- | --- | --- |
| T-419 | S2 codex·kistillm (무료) | R46-N1: INTERFACE.md:240 과 RESEARCH-draft-owner.md 요약·§4.2(A)·§6 에 'pageshow 는 bfcache 복원(persisted)일 때만, 첫 로드는 app.js init' 단서, 고친 이력 한 줄 | DONE, 1회 시도, 343초 |
| T-420 | S4 claude·sonnet (유료·검수만) | 적대적 검수 + R46-N2 추정 독립 판정 | DONE. 상·중 0, 하 2 |

R46-N2 는 **추정이 틀려 고치지 않았습니다.** `api().getConfig()` 가 거절되는 경로가 없습니다.
- `web/api.js:8-26`: 동기 예외는 try/catch 로, 비동기 거절은 `then(ok, fail)` 로 받아 메모리 설정을 돌려줍니다
- `web/queue.js:99-109`: `.catch` 로 memConfig 를 돌려줍니다

관리자가 코드를 읽고 먼저 판정했고, 검수자가 따로 같은 결론을 냈습니다.

## (2) 재현한 검증
- T-419 엔진 verify rc 0. 옛 문장이 없고, persisted 단서가 INTERFACE 와 RESEARCH 3곳에 있으며, 고친 이력에 R46-N1 이 있습니다
- `git diff --stat projects/VoxLog/`: 문서 두 개만 바뀌었습니다(+6/−4). hunk 를 직접 읽어 코드(`web/queue.js:628-634`)와 맞는지 확인했습니다
- VoxLog 단위 155 OK. 문서만 바뀌어 브라우저 검사는 돌리지 않았습니다
- `tools/check.py --all`: 1128 OK
- `aimem_lint.py AIMEM.md`: 위반 없음

## (3) 기다린 시간
- 라운드 00:08 → 00:21, 약 13분
- T-419 343초 (kisti)
- T-420 41초 + 38초. 두 번째 실행 38초는 관리자 실수입니다. NEEDS-FIX 로 막힌 검수 노드를 `--reverify` 없이 `unblock` 해 검수가 한 번 더 돌았습니다. 결과는 DONE 으로 같았습니다

## (4) 큐
- 내림: R46-N1·N2
- 올림: R47-N1·N2(하), 한 항목
  - R47-N1: `docs/RESEARCH-draft-owner.md:148` 의 (f) 검사 항목에 persisted 단서가 빠졌습니다
  - R47-N2: init 의 첫 로드 회수와 initOpen 은 getConfig.then 안의 앞선 동기 호출이 던지지 않을 때만 돕니다. 추정이며 지금 코드에서는 일어나지 않습니다
- 큐는 1건(VoxLog)입니다

## (5) 다음 라운드
- 넘긴 요청은 없습니다
- 큐 R47-N1·N2 는 하 등급입니다. 사람이 요청할 때 처리합니다
- 배포(운영 서버 재시작)는 요청대로 하지 않았습니다. 이번 변경은 문서뿐이라 배포할 것도 없습니다

## (6) 운영 지표
- 쓴 슬롯: S2(무료, 만들기)·S4(유료, 검수). S1·S3·S5·S6 은 쉬었습니다. 일이 문서 한 건이라 한 갈래면 충분했습니다
- 관리자 혼자 일한 구간: 시작 점검과 R46-N2 코드 판정 약 7분, 종료 절차 약 4분(전체 검사 176초 포함)
- 재시도: T-420 1회. 위 (3)의 관리자 실수입니다
- 더한 슬롯·옮긴 노드: 없음

## (7) 개선안 하나
검수 노드가 NEEDS-FIX 를 내면 그래프가 막힙니다. 하 등급만 있어 큐로 넘길 때 `unblock` 은 검수를 다시 띄웁니다(유료 1회 낭비).

- 지금 쓸 수 있는 길: `unblock --reverify` 로 확정합니다. 이것은 `8.0-5` 와 '`verify` wrong' 항목에 이미 있습니다
- 제안: 표준 브리프의 검수 노드 지시에 '하 등급만이면 첫 줄 DONE' 을 한 줄 넣습니다. 그러면 막힘 자체가 줄어듭니다
