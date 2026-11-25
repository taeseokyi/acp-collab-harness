# R49 보고 (M-R49-112131, 2026-11-25 11:21 ~ 16:50)

상태: DONE

요청 `Q-261125-76c8` [VoxLog] F2 녹취 이름·태그 + AI 자동 태그 - DONE. 운영 방식 무료 중심(만들기·고치기는 무료 S2·S3·S6, 유료 S4 는 검수만), 관리 방식 VoxLog 품질 우선.
결과물은 모두 `projects/VoxLog/` 에 쌓였고(아래 (1)), 라운드 폴더에는 기록(`spec.md`·이 보고)만 있습니다.

## 관리자가 정한 것 (요청이 관리자에게 맡긴 결정, 정본 `rounds/R49/spec.md`)
- AI 태그와 사람 태그를 구분해 저장: meta `label`·`tags`·`tags_auto`·`tags_human`·`autotag`(옛 meta 는 읽을 때 기본값). 화면은 한 줄의 칩, AI 것은 점선 테두리 + `AI 가 단 태그`.
- 사람이 태그를 한 번이라도 고치면 그 녹취의 자동 태그(다시 받아쓰기 뒤)는 끝 - 지운 것을 되살리지도, 더한 것을 지우지도 않음. 이름만 고치면 자동 태그는 계속.
- 이미 있는 녹취: 상세 `태그 다시 달기`(`POST /api/recordings/<id>/autotag`) - 사람 태그는 남기고 AI 태그만 바꿈.
- `llm=false` 면 자동 태그만 빠짐(다시 달기 단추 숨김·503). Asker 를 우선순위 큐로 - 사용자 묻기가 쌓인 태그 일보다 먼저, 태그 호출 상한 60초. 실패는 조용히(상세에 한 줄, `status` 무영향), 재시작 때 pending → failed.

## (1) 태스크 표

| 태스크 | 슬롯 | 내용 | 결과 |
| --- | --- | --- | --- |
| T-433 | S2 codex | `voxlog/tags.py`(새) 정규화·태그 뽑기 + `tests/test_tags.py`(새) | DONE, verify rc 0 |
| T-434 | S3 opencode | `voxlog/store.py` 다섯 필드·set_label_tags·set_auto_tags·set_autotag·list(tag, match) + test_store | DONE |
| T-435 | S2 | `voxlog/ask.py` build_tag_prompt·llm_status·우선순위 큐·submit_tag, `voxlog/stt.py` on_done + 검사 | DONE |
| T-436 | S3 | `serve.py` PATCH·autotag·?tag=·자동 태그 연결 + test_serve·fake_llm | DONE |
| T-437 | S6 freebuff | `web/index.html`·`style.css`·`sw.js` VERSION | DONE |
| T-438 | S2 | `web/app.js` 칩·거르기·편집·저장·다시 달기·폴링 | DONE |
| T-439 | S6 | 브라우저 t42·t43·t44 | DONE, 43/43, 변이 7개 확인 |
| T-440 | S6 | 설계 문서 F2·I3, INTERFACE.md, README | DONE |
| T-441 | S4 sonnet | 적대적 검수 | NEEDS-FIX 조건부: 상 R49-N1, 중 N2·N3·N4, 하 N5~N8 |
| T-442 | S2 | R49-N2·N3·N4 고치기(tags.py·ask.py + 검사) | DONE, 되돌림 3개 실패 확인 |
| T-443 | S3 | R49-N1 서버 쪽(같은 태그면 tags_human 안 켬) + 느린 가짜 LLM | DONE |
| T-444 | S2 | R49-N1 화면 쪽(saveLabels 는 바뀐 것만) | DONE |
| T-445 | S6 | 브라우저 t45 | DONE(2차 시도), 44/44 |
| T-446 | S4 | 재검수 | 상·중 0, 하 3(R49-N9~N11), 변이 8/9 |

바뀐 파일(`projects/VoxLog/`): `voxlog/tags.py`(새)·`store.py`·`ask.py`·`stt.py`, `serve.py`, `web/app.js`·`index.html`·`style.css`·`sw.js`, `tests/test_tags.py`(새)·`test_store.py`·`test_ask.py`·`test_stt.py`·`test_serve.py`·`fake_llm.py`·`browser_voxlog.py`, `docs/DESIGN-next-features.md`·`docs/INTERFACE.md`, `README.md`, `PROGRESS.md`(목표 F2 체크·R49 항목).

## (2) 재현한 검증
- 관리자: `python3 -m unittest discover -s projects/VoxLog/tests` → 229 OK. `python3 tools/check.py` → 530 OK.
- 브라우저 `projects/VoxLog/tests/browser_voxlog.py` 는 관리자 셸에서 승인이 필요해 직접 못 돌림 - 엔진 verify(T-437·T-438·T-439·T-442~T-445 모두 rc 0)와 재검수자 실행 44/44 를 씀.
- 재검수 T-446 이 `/tmp` 사본에 변이 9개: 8개 걸림, `TAG_TIMEOUT` 300 되돌림만 안 걸림(R49-N9, 검사가 항등식).
- T-445 1차 verify 는 기존 녹음 탭 검사(t30·t32 등 `탭1 녹음이 켜지지 않음`)에서 실패, 코드 변경 없이 2차에서 두 번 통과 → 흔들리는 검사로 판단.
- 실제 `claude` 로 자동 태그가 달리는지는 배포본에서 볼 것(배포·운영 서버 재시작은 요청대로 안 함).

## (3) 기다린 시간
- kisti 공급자(동시 1)를 S2·S3 가 나눠 써 무료 노드 8개가 줄을 섬. S6(freebuff)이 따로 돌아 겹침. 가장 긴 노드 T-439(S6) 4003초 - 변이 검사를 사본에서 돌린 시간 포함.
- G-105 11:28~13:58, G-106 14:08~16:39.

## (4) 큐
- 들어감: R49-N5~N8(하, 검수), R49-N9~N11(하, 재검수).
- 줄어듦: 2번 항목에서 이름·태그 몫(R48-N10·N11·N12 일부)과 R48-N20 을 내림(요청 4). 남은 큐 5건, 모두 VoxLog 하 등급.

## (5) 다음 라운드
- 넘기는 `PLANNED` 없음. 요청 0.
- VoxLog 남은 목표: F1 답의 출처 녹취 → F3 답 이어 묻기(설계 문서 '구현 순서' 의 요청 문장). 큐 4·5번(R49 하)은 R49-N9 한 줄 고침과 함께 한 번에 치우면 작음.

## (6) 운영 수치
- 슬롯 실행 시간: S2 4278초(5노드), S3 2817초(3), S6 10080초(5, T-445 2회 포함), S4 644초(2). S1·S5 쉼(무료 중심).
- 관리자만 돈 구간: 시작~11:28(약속 정하기), 13:58~14:08(검수 읽고 후속 그래프), 16:39~(마무리).
- 재시도: T-445 1회(verify 흔들림). 노드 옮김 없음. 슬롯 더함 없음.
- INBOX: 13:45 태석님이 자동 태그를 kistillm(OpenAI 호환)으로 바꾸라고 남겼다가 13:46 철회. 노드를 더하기 전에 철회를 봐서 코드·노드 변경은 없었음. spec 9절에 적었던 안을 지우고 철회 기록만 남겼고, 잠깐 바꾼 소유 경로(serve.py·test_serve.py·fake_llm.py → S2)를 S3 로 되돌림. 그때 새로 생긴 소유 행 `tests/fake_tag_llm.py`·`settings.example.json`(S2)은 남아 있음(쓴 것 없음, 지우기는 하지 않음).
- 그래프 상한: G-105 9노드(새 일) + G-106 5노드(`--followup`, 검수 수정·재검수).

## (7) 개선안 하나
VoxLog 의 녹음 탭 브라우저 검사(t28~t32 부근 `탭1 녹음이 켜지지 않음`)가 부하가 있을 때 흔들립니다(같은 코드로 1차 실패·2차 두 번 통과). 작업자가 사본에서 브라우저 검사를 동시에 돌리면 엔진 verify 와 겹칩니다. 다음 VoxLog 요청 때 그 검사의 대기 조건(녹음 켜짐을 고정 시간이 아니라 상태로 기다리는지)을 읽기 전용으로 먼저 살펴보기를 권합니다.
