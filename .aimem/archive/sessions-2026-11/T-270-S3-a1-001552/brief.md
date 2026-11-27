SLOT=S3 T-270 test_fleet_graph: Q2 세션 시험이 전체 discover 에서 fake 로 가는 것 + Q1 디딤 폴더 (재검수 R22-R1·R2) (G-054)
확인토큰: 5b8c1e
AIMEM REV: 164
너는 S3 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: tests/test_fleet_graph.py
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

# T-270 `tests/test_fleet_graph.py` 의 시험 둘 고치기 (재검수 R22-R1·R2)

쓸 파일은 **하나**입니다: `tests/test_fleet_graph.py`. 다른 파일은 **읽기만** 하십시오(`tests/_fleet_env.py`·`tools/**` 고치기 금지).
바로 파일을 고치십시오. 근거는 `rounds/R22/REVIEW-r22-2.md` 의 R1·R2 행(30~31줄)입니다.

## R1 (중간) - 전체 시험이 빨갛다

`python3 -m unittest discover -s tests` (프로젝트의 정식 명령) 에서 `test_q2_session_branch_429_is_true` 가 FAIL 합니다. 까닭: `tests/_fleet_env.py` 가 `AIFLEET_HARNESS=fake` 를 깔고, `tools/fleet_rt/harness/__init__.py` 의 `get()` 이 그때 무엇을 청하든 `fake` 어댑터를 줍니다. 그래서 `_session()` 도우미(535행 근처)가 `meta.json` 에 `harness_effective: "claude"` 를 써도 `fleet_graph.run_limit_signal` 이 fake 로 갑니다. 모듈 하나만 돌리면 통과해서 놓쳤습니다. 나머지 `test_q2_*` 둘은 fake 에서도 우연히 통과해 아무것도 재지 않습니다.

**고치는 법:** fake 강제 장치(환경변수)는 **풀지 마십시오** - 진짜 하네스가 뜨는 것을 막는 안전 장치입니다. 대신 `test_q2_*` (와 아래 Q1 시험) 안에서 `unittest.mock.patch("fleet_rt.harness.get", lambda name: claude_adapter)` 처럼 **어댑터 고르기만** claude 어댑터(`from fleet_rt.harness import claude` 의 `claude.ADAPTER`)로 바꾸십시오. claude 어댑터의 `limit_signal` 은 파일만 읽으므로 안전합니다. `fleet_graph` 가 `rt_harness.get` 을 어떻게 부르는지(`tools/fleet_graph.py` 의 `run_limit_signal`)를 보고 패치 자리를 맞추십시오. 그리고 시험 하나는 `get` 이 정말 `"claude"` 로 불렸는지도 단언하십시오.

## R2 (낮음) - Q1 시험이 `/` 허용 변이를 못 잡는다

`test_q1_run_id_with_path_segments_is_none` 의 반례는 디딤 폴더가 없어 OS 가 경로를 못 풀고 실패하므로, 정규식이 `/` 를 허용해도 `None` 이 나옵니다. 시험 안에서 임시 세션 자리(`_session()` 이 쓰는 자리)에 `T-1-S1-a1-000000/meta.json` 과, 그 바깥에 `outside/evil/meta.json`(`{"harness_effective": "claude"}`)·`outside/evil/events.jsonl`(429 result 사건 한 줄) 을 실제로 만들고, `T-1-S1-a1-000000/../../outside/evil` 꼴(자리에 맞게 `..` 수를 맞추십시오)이 `None` 인지 단언하십시오. 디딤 폴더가 있으면 정규식이 `/` 를 허용하는 순간 그 경로가 풀려 `True` 가 나와야 이 시험이 의미가 있습니다 - 정규식을 직접 바꿔 보지 말고(제품 고치기 금지) 경로가 실제로 풀리는지는 `pathlib` 으로 `exists()` 를 단언해 확인하십시오.

## 제품 결함을 찾으면

제품도 시험도 고치지 말고 보고 첫 줄을 `NEEDS-FIX: <무엇이 어디서>` 로.

## 하지 말 것

`tools/**`·`tests/_fleet_env.py` 고치기, `git commit`/`push`, 파일 삭제, 운영 모니터 부르기.

## 검증 (엔진이 돌립니다)

**전체** `python3 -m unittest discover -s tests` 가 통과(약 2~3분)하고, `tests.test_fleet_graph` 단독도 통과하며 시험이 77개 이상. 끝내기 전에 당신도 전체 discover 로 확인하십시오.
