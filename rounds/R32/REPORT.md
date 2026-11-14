# R32 보고 (관리자 M-R32-014740, 2026-11-15 01:47~02:34)

상태: DONE

할 일: 요청 `Q-261115-4aff` [자모맞히기]: 모니터 '앱 열기' 에서 앱의 serve.py 를 띄워 서버 쪽 기능이 그대로 되게 하기. 함께 큐 R31-P1, R31-N8, R31-N10~N14 도 했습니다. 큐 R31-P2(옛 방법)는 이 요청이 대신하므로 내렸습니다(INBOX 01:47).

## 결과물이 쌓인 곳
- `projects/자모맞히기/`: 새 파일 `trend_store.py`·`web/js/trend.js`·`tests/test_trend_store.py`·`tests/test_trend.mjs`. 고친 파일 `serve.py`·`tools/pick_answers.py`·`trend_news.py`·`data/trend_stop.txt`·`web/js/ui.js`·`storage.js`·`index.html`·`style.css`·`app.json`(`"server": "serve.py"`)·`README.md`·`tests/README.md`·`tests/test_dict_server.py`·`test_pick_answers.py`·`test_trend_news.py`·`test_storage.mjs`·`browser_trend.py`·`PROGRESS.md`
- 함대: 새 파일 `tools/aimem_monitor/app_server.py`·`tests/test_aimem_monitor_app_server.py`·`tests/test_aimem_monitor_app_proxy.py`·`tests/browser_monitor_app_server.py`. 고친 파일 `tools/aimem_monitor/server.py`·`tests/test_aimem_monitor_app.py`
- 기록: `rounds/R32/REVIEW-r32.md`(적대적 검수). 관리자 도구는 `.aimem/graph/inputs/r32/`(SPEC.md·v.py·노드 생성기)

**모니터 재시작 필요.** `server.py` 를 바꿨습니다. 클로드 코드가 코드를 검토한 뒤 재시작하십시오. 그 전까지는 운영 모니터의 '앱 열기' 에서 단추를 누르면 '서버 없음' 글이 나옵니다.

## (1) 태스크

| 태스크 | 슬롯 | 내용 | 결과 |
|---|---|---|---|
| T-328 | S5 sonnet | `trend_store.py`를 새로 만들고, `serve.py` 에 `GET /api/trend` 를 냄. pick 결과 저장·`timeout 30`, `pick_answers.py` 도 같은 함수를 씀 | DONE 129s |
| T-329 | S4 sonnet | `app_server.py`(띄우기·다시 씀·이어 주기·내리기) + 검사 23개 | DONE 114s |
| T-330 | S3 무료 | R31-N11~N14: RSS 2MB 상한, 마감 120초, 기업명·시군 거름, 조사 원형, `checked` 를 실제 수로 | DONE 409s |
| T-331 | S5 sonnet | 화면: 서버 정답 받아 씀, `#trend-since` 표시, `jamo.trend` 걷음, R31-N8·N10 | DONE 373s |
| T-332 | S4 sonnet | `server.py`: `server` 선언, api 이어 주기, OPTIONS, 감사 로그, 정리 + 검사 21개 | DONE 223s |
| T-333 | S5 sonnet | `app.json` server 선언 + 끝에서 끝 브라우저 검사 `browser_monitor_app_server.py` 21개 | DONE 169s |
| T-334 | S3 무료 | 문서: 프로젝트 README, tests/README 수 | DONE 532s |
| T-335 | S1 opus | 적대적 검수 → 판정 통과 | DONE 491s |
| T-336 | S5 sonnet | 후속 R32-N1(중): `fcntl.flock` 프로세스 잠금 + 두 프로세스 검사 | DONE 66s |
| T-337 | S4 sonnet | 후속 R32-N2·N4·N6: pid 확인 좁힘, script 가 바뀌면 다시 띄움, OPTIONS 는 티켓 먼저 | DONE 54s |

## (2) 재현한 검증
관리자가 `v.py` 의 store·news·proxy·ui·e2e·docs 를 다시 돌렸고 모두 통과했습니다.
- 프로젝트: node 107, python 133, 브라우저 game 121/121, modes 100/100, dict 75/75, trend 81/81
- 함대: `browser_monitor_app_server` 21/21, `browser_monitor_app` 8/8, unittest 전체 1025 OK(건너뜀 1). R31 때는 981 이었습니다
- 린터: 위반 없음(render 뒤)
- 실제 `data/trend_meta.json` 은 생기지 않았습니다. 검사는 임시 경로만 씁니다

검수 `REVIEW-r32.md` 는 상 0건, 중 1건(N1), 하 5건(N2~N6)으로 판정 통과입니다. N1·N2·N4·N6 은 G-070 에서 고쳤고 엔진 verify 를 통과했습니다. 규칙상 재검수는 '높음' 결함을 고쳤을 때만 하므로 생략했습니다.

## (3) 기다린 시간
- 라운드 전체 약 47분(01:47~02:34)
- 가장 긴 구간은 T-331 → T-333 → T-334(무료, 532s) → T-335(검수) 로 이어지는 사슬이었습니다
- 노드가 끝난 뒤 브라우저 verify 를 기다린 시간은 노드마다 2~3분이었습니다

## (4) 큐 진행
- 내림: R31-P2(이 요청이 대신함), R31-P1(T-328·T-331·T-333), R31-N11~N14(T-330·T-334)
- 더함: `[함대]` R32-N3·N5(하). 같은 저장소를 모니터 둘이 볼 때의 cleanup_stale 문제와, 앱이 setsid 로 띄운 손자가 남는 문제입니다. 아래 고아 프로세스의 출처를 찾는 일도 함께 적었습니다
- 남은 큐: 1건

## (5) 다음 라운드
- 자모맞히기는 목표 21/21 입니다. 남은 것은 사람 몫입니다: 운영 모니터 재시작, 국립국어원 키를 `.env` 에 넣기
- 큐의 `[함대]` R32-N3·N5 는 하(낮음)라서 급하지 않습니다
- 다음 라운드로 넘긴 PLANNED 요청은 없습니다

## (6) 운영 지표
- 슬롯 사용률(47분 기준): S5 737s(26%), S3 941s(33%), S1 491s(17%), S4 391s(14%)
- 관리자 혼자 일한 구간: 시작·설계 01:47~01:54(7분), 재현·마감 02:26~02:34(8분)
- 재시도 0, 노드 이동 0, 더한 슬롯 0. S2 는 일시 사용 중지(장애)라 쓰지 않았습니다
- 유료 슬롯에 맡긴 만들기와 그 까닭(운영 방식 '빠른 구현'):
  - S4·S5 sonnet: 모니터 보안 경계 코드와 화면·브라우저 검사를 빨리 끝내기 위해
  - S1 opus: 마지막 검수
- 슬롯 역할: S1 검수, S3 품질 결함·문서, S4 모니터, S5 자모맞히기 서버·화면·끝에서 끝
- 정리 못 한 것: `/tmp` 임시 저장소의 가짜 앱 서버 `projects/알파/serve.py`(pid 147068) 하나가 고아로 남아 있습니다
  - 관련 검사 모듈을 다시 돌려 봤지만 새로 남지는 않았습니다. 작업자나 검수자가 실험하다 끊긴 것으로 보입니다
  - `kill 147068` 은 권한 승인이 필요해 하지 못했습니다. 루프백 포트에만 떠 있습니다. 클로드 코드가 pid 로 내려 주십시오

## (7) 개선안 한 가지
문서 노드가 검수 노드를 막지 않게 하자는 제안입니다. 이번 라운드에서는 무료 슬롯의 문서 노드(T-334, 532s)가 검수(T-335)의 선행이라, 사슬이 약 9분 길어졌습니다. 검수는 코드만 보면 되니, 문서 노드를 검수와 같은 단계(둘 다 끝에서 끝 검사 뒤)에 나란히 두면 라운드가 그만큼 짧아집니다. 다음 그래프부터 관리자가 이렇게 짜겠습니다. 운영 규칙으로 두려면 `8.0-8` Graph rules 에 "문서 노드는 검수의 deps 에 넣지 않음" 한 줄을 넣으면 됩니다.

## 판단해서 진행한 것 (태석님이 자리에 없어서)
- 정적 파일은 지금처럼 모니터가 내주고, `api/` 만 앱 서버로 이어 줍니다. 그래서 sandbox·CSP·티켓 격리는 그대로입니다
- `pick` 결과를 저장할 때 이미 있는 날짜는 덮어쓰지 않습니다. 명령줄과 같은 규칙입니다. 그래서 오늘 정답은 한 번 정해지면 바뀌지 않습니다
