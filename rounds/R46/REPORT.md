# R46 보고 (관리자 M-R46-230904, 2026-11-24)

상태: DONE

할 일: 요청 `Q-261124-f310` [VoxLog] 대기 큐 VoxLog 항목 둘(R43-N5, R44-N1~N3). 운영 방식 무료 중심, VoxLog 관리 방식 품질 우선. 그래프 G-098 하나(노드 3). INBOX 에 태석님 답 1건(자모맞히기 큐 물음) - 반영함.

결과물 위치
- VoxLog: `projects/VoxLog/` - `web/app.js`, `web/queue.js`, `tests/browser_voxlog.py`, `tests/test_serve_ask_body.py`, `docs/RESEARCH-draft-owner.md`, `PROGRESS.md`(## R46)
- 자모맞히기: `projects/자모맞히기/PROGRESS.md`(## R46 - trend.txt 출처 한 줄, 코드 변경 없음)

## (1) 태스크 표

| 태스크 | 슬롯 | 일 | 결과 |
| --- | --- | --- | --- |
| T-416 | S2 codex·kistillm(무료) | R43-N5 `_read_body` 의 `left <= 0`·`got != length` 분기를 따로 잡는 검사 2개 + R44-N2 조사 문서 147행 | DONE, 시도 1, verify rc 0 |
| T-417 | S3 opencode·kistillm(무료) | R44-N1 `startRec` 의 `mr.start` try/catch(초안·잠금·상태·마이크 정리) + R44-N3 pageshow 는 `persisted` 일 때만 회수 + 브라우저 t39·t40 | DONE, 시도 1, verify rc 0 |
| T-418 | S4 claude·sonnet(유료, 검수만) | 적대적 검수(부작용 중심) | 통과 - 상·중 0, 하 2 |

요청 `Q-261124-f310` → DONE. 배포는 하지 않음(요청대로).

## (2) 재현한 검증
- 관리자: `python3 -m unittest discover -s projects/VoxLog/tests` → `Ran 155 tests ... OK`; `python3 tests/browser_voxlog.py`(VoxLog 폴더) → `40/40 통과`
- 검수자 변이(/tmp 사본, 지움): serve.py 362행 400→500 → `test_zero_grace_whole_body_gets_400` 만 실패; 382행 400→500 → `test_short_body_write_closed_gets_400_before_grace` 만 실패; app.js catch 의 `draftDiscard` 삭제 → t39 만 실패; queue.js `persisted` 조건 삭제 → t40 만 실패. 작업자도 각자 되돌림 확인을 보고함
- 함대 전체: `python3 tools/check.py --all` → `Ran 1128 tests ... OK`; `aimem_lint.py AIMEM.md` → 위반 없음(render 뒤)

## (3) 기다린 시간
- 라운드 시작 23:09, 그래프 시작 23:15, T-416 23:15~23:18, T-417 23:19~23:39(kisti 동시 1 이라 S2·S3 가 차례로), T-418 23:39~약 23:47. 관리자 마무리 ~23:55
- 공급자 장애·막힘 없음

## (4) 큐 진행
- 내림: [VoxLog] R43-N5, [VoxLog] R44-N1·N2·N3(이번 요청), [자모맞히기] trend.txt 출처 물음(INBOX 의 태석님 답 - 연합뉴스 제목 RSS 에서 사전에 있는 낱말만 고른 것, PROGRESS 에 기록)
- 올림: [VoxLog] R46-N1·R46-N2(하) - `docs/INTERFACE.md:240`(와 RESEARCH 문서 일반 서술)의 'resume·pageshow 에서 회수' 가 낡음; init 의 첫 로드 회수가 `getConfig` 성공 뒤에만 돌아 getConfig 거절 때 그 방문엔 회수 없음(추정, 다음 방문·resume 에 다시 시도라 소실 없음)
- 지금 큐: 1건(위 R46-N1·N2)

## (5) 다음 라운드
- 열린 요청 없음. 넘기는 PLANNED 없음
- 큐 1건(VoxLog 하 2)은 요청이 오면 처리. R46-N1 은 문서 한 줄, R46-N2 는 고칠지 태석님 판단(그대로 두고 알려 둘 수도 있음)

## (6) 운영 지표
- 슬롯 가동: S2 약 3분, S3 약 20분, S4 약 8분. S1·S5·S6 대기
- 관리자 혼자 구간: 시작 점검·그래프 작성 약 6분(23:09~23:15), 마무리(재현·전체 검사 178초·기록) 약 8분
- 재시도 0, 노드 옮김 0, 슬롯 더함 0
- 무료 두 슬롯이 같은 kisti 공급자(동시 1)라 병렬 그래프여도 차례로 돌았음

## (7) 개선안 하나
- 무료 슬롯 둘(S2·S3)이 같은 공급자(kisti, 동시 1)를 쓰니, 무료 중심 라운드에서 한 단계에 무료 노드 둘을 나란히 두어도 실제로는 줄을 섭니다. `fleet_graph.py new` 가 '같은 공급자 동시 1 에 한 단계 노드 둘' 을 모양 알림에 한 줄로 알려 주면 관리자가 ETA 를 바로 잡고, 필요하면 무료 공급자가 다른 슬롯(freebuff 등)에 문서 같은 작은 노드를 나눌 수 있습니다.

## 참고
- 작업 트리에 이번 라운드 것이 아닌 변경이 있음(`AIMEM.md` 352행 한 줄·`.aimem/briefs/policy-speed.md`·`projects/주보알림/` 의 PROGRESS·web/app.js·`rounds/R42/setup.sh`·`rounds/R45/probe_env.py` 삭제) - 건드리지 않았음. AIMEM.md 서문 REV 는 handoff 로 203
- 미커밋(커밋은 태석님 허락 뒤)
