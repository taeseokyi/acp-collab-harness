SLOT=S2 T-272 실행 기록 읽기: FIFO 에서 막힘·메타 크기 상한 없음 (R20-N6·R20-N8 = R22-P4) (G-055)
확인토큰: d27e93
AIMEM REV: 164
너는 S2 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: tools/fleet.py, tools/fleet_graph.py
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

# T-272 실행 기록을 안전하게 읽기 (R20-N6·R20-N8, R22 재검수 P4)

쓸 파일은 **둘**입니다: `tools/fleet.py`, `tools/fleet_graph.py`. 다른 파일(`tests/**` 포함)은 **읽기만** 하십시오. 바로 파일을 고치십시오.
근거: `rounds/R20/REVIEW-r20.md` 의 N6·N8 행 (그 보고서의 나머지는 읽지 않아도 됩니다).

## 결함

- N6: `tools/fleet_graph.py` `run_limit_signal` 이 `.aimem/runs/<id>.out` 을 `open("rb").read(1MiB)` 로 엽니다. 그 자리가 FIFO(이름 있는 파이프)면 **쓰는 쪽이 올 때까지 영영 막힙니다** - 그래프 실행기 전체가 멈춥니다. 세션 갈래의 `meta.json` 읽기도 같습니다.
- N8: `tools/fleet.py` `_run_meta` (369행 근처)와 `_session_meta` (352행 근처)가 `read_text()` 로 **크기 상한 없이** 읽습니다.

## 할 일

1. `tools/fleet.py` 에 작은 도우미 하나: `read_regular_bytes(path, limit) -> Optional[bytes]`. `os.open(path, os.O_RDONLY | os.O_NONBLOCK)` 로 연 뒤 `os.fstat` 으로 `stat.S_ISREG` 가 아니면 `None`, 크기가 `limit` 를 넘으면 `None`, 아니면 `limit` 바이트까지 읽어 돌려줍니다. `OSError` 는 `None`. 열었으면 반드시 닫습니다(`try/finally`).
2. `_run_meta`·`_session_meta` 가 그 도우미로 읽게 합니다 (상한 256 KiB). 지금의 반환 꼴(dict 또는 None)은 그대로.
3. `tools/fleet_graph.py` `run_limit_signal`: `.out` 읽기는 `fleet.read_regular_bytes(..., 1024*1024)` 로 (넘으면 지금처럼 `None` 이 되면 됩니다 - 지금은 1MiB 까지 잘라 읽어 JSON 이 깨져 `None` 이었습니다). 세션 갈래의 `meta.json` 읽기도 도우미로(256 KiB).
4. 다른 동작은 바꾸지 마십시오.

## 하지 말 것

`tests/**` 고치기(다음 노드 S3 가 시험을 씁니다), `git commit`/`push`, 파일 삭제, 운영 모니터 부르기.

## 검증 (엔진이 돌립니다)

`tests.test_fleet_graph`·`tests.test_fleet_ctl`·`tests.test_fleet` 와 `test_rt_*.py` 전부가 통과하고, 임시 `RUNS` 에 FIFO `X.out` + claude 메타를 두면 `run_limit_signal("X")` 가 3초 안에 `None`, 2 MiB 짜리 `Y.json` 이면 `fleet._run_meta("Y")` 가 `None`, 정상 메타는 dict, `fleet.read_regular_bytes` 가 있어야 합니다.
