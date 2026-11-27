SLOT=S2 T-263 fleet_graph.py: 한도 판정 회귀 N3 + 너무 넓은 걸림말 N4·N5 + run_id 검사 N7 (G-052)
확인토큰: d27e93
AIMEM REV: 164
너는 S2 슬롯이다. 작업 폴더는 /home/tsyi/work/ai-fleet 다.
쓰기는 다음 경로에만 한다: tools/fleet_graph.py
금지: git commit / push / 삭제 / 의존성 설치. 보고는 응답 본문에 직접 쓴다.
보고 첫 줄은 상태(DONE / PARTIAL / BLOCKED / NEEDS-LOCK / NEEDS-APPROVAL), 이어서 한 일·고친 파일·실제로 돌린 검증 명령과 출력·다음 담당자가 알아야 할 것.
검증 명령은 승인 없이 실행되는 형태로 쓴다: `python3 ...`, `PYTHONPATH=tools python3 ...`, `pytest ...`, `ls/cat/grep/sed -n/wc/diff/git status/git diff/curl ...`. 셸 변수 대입이나 다른 접두사를 앞에 붙이면 승인 요구로 막힌다. py_compile 이 만드는 __pycache__ 는 쓰기로 치지 않는다.

# T-263 `run_limit_signal` 의 결함 넷 (적대적 검수 N3·N4·N5·N7)

쓸 파일은 **하나**입니다: `tools/fleet_graph.py`. `tests/**` 와 다른 `tools/**` 는 읽기만 하고
**절대 고치지 마십시오**(특히 `tools/fleet.py`). 계획을 세우지 말고 바로 고치십시오.

고칠 곳은 `run_limit_signal` (`:440` 근처) 과 `_LIMIT_PATTERNS` (`:418` 근처) 뿐입니다.
`step()` 은 **건드리지 마십시오.**

## N3 (중간) - **회귀**: 구조 신호 `False` 가 글자 판정을 덮어씁니다

`step()` 은 `sig is None` 일 때만 보고 글자를 봅니다. 그런데 지금 `run_limit_signal` 은
`is_error: true` 인데 `api_error_status`·`api_error`·`terminal_reason` 이 **하나도 없으면**
`False` 를 돌려줍니다. 그러면 글자 판정이 **아예 안 돌아** 진짜 한도가 보통 실패로 재시도됩니다.
R20 **이전에는 글자로 잡히던** 경우입니다.

실측(검수): `{"is_error": true, "result": "You've hit your 5-hour limit · resets 11:20am"}`
(메타 harness claude) → `run_limit_signal` = `False` 인데 `report_limit_hit(result)` = `True`.

**고칠 것:** 마지막 `return False` 를 **`return None`** 으로 바꾸십시오.
`False` 는 **`is_error` 가 거짓일 때만** (`if not data.get("is_error"): return False`) 돌려줍니다.
즉 "JSON 은 읽혔고 오류가 아니다" 만 `False`, "오류인데 표지가 없다" 는 `None`(글자 판정으로).
주석 한 줄로 까닭을 적고 docstring 도 그에 맞게 고치십시오.

## N4 (중간) - `terminal_reason == "api_error"` 갈래의 `"limit"` 부분 일치가 너무 넓다

지금:

```python
if report_limit_hit(value) or "limit" in value.lower():
```

`"Prompt exceeds the context window limit"` 처럼 **재시도로 풀리는** API 오류까지 사용 한도로
보고 blocked 시킵니다.

**고칠 것:** `or "limit" in value.lower()` 를 **지우고** `report_limit_hit(value)` 만 쓰십시오.

## N5 (낮음) - 글자 판정에 넣은 일반 낱말 둘

`_LIMIT_PATTERNS` 에서 **`"limit reached"` 와 `"too many requests"` 를 지우십시오.**
실측: `report_limit_hit("NEEDS-FIX: verify step time limit reached, test failed")` → `True`,
`report_limit_hit("DONE - added handler for HTTP 429 Too Many Requests")` → `True`. 둘 다 오인입니다.
**`"hit your weekly limit"` 와 `"hit your usage limit"` 는 하네스가 실제로 찍는 문구이니 남기십시오.**
그 밖의 기존 항목도 건드리지 마십시오.

## N7 (낮음) - `run_id` 검사가 없어 `runs/` 밖을 읽습니다

`run_limit_signal("../outside/evil")` 이 `runs/` 바깥의 `.json`·`.out` 을 읽습니다.
`tools/aimem_monitor/reader.py` 의 `RUN_ID_RE` 가 같은 문제를 이미 막고 있습니다 - **읽어서**
같은 꼴의 정규식을 `run_limit_signal` **맨 앞**에 두십시오(모듈 상수로). 꼴이 아니면 **`None`**.

```python
_RUN_ID_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")   # reader.RUN_ID_RE 와 같은 뜻
...
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        return None
```

`reader.py` 의 진짜 꼴을 먼저 보고 그와 **같은 엄격함**으로 쓰십시오(점·슬래시로 폴더를 벗어날 수
없어야 합니다). 이 검사는 `try` **바깥**에 두어도 되고 안에 두어도 됩니다.

## 하지 말 것

- `step()` 의 `rc != 0` 조건과 `sig is None` 갈래를 **바꾸지 마십시오**
- 1 MiB 읽기 상한, `harness != "claude"` → `None`, `try/except Exception: return None` 은 그대로
- `tools/fleet.py` 는 읽기만

## 검증

검증 명령이 봅니다: `tests.test_fleet_graph`·`tests.test_fleet_ctl`·`tests.test_fleet` 가 초록이고,
임시 폴더의 가짜 실행 기록 여섯에 대해 `run_limit_signal` 이
`True / None / False / None / None / None` 이며 `report_limit_hit` 의 오인 둘이 사라진 것.

[재시도 2/2] 직전 시도(run T-263-S2-a1-193012) 는 rc=124 / 검증 rc=None 로 실패했다. 산출물이 남아 있을 수 있으니 먼저 확인하고 이어서 하라. 직전 검증 출력 꼬리:


직전 작업자의 보고(참고만 하라 - 틀렸을 수 있으니 그대로 믿지 말고 직접 확인하라):
` 와 `"hit your usage limit"` 는 하네스가 실제로 찍는 문구이니 남기십시오.**
그 밖의 기존 항목도 건드리지 마십시오.
## N7 (낮음) - `run_id` 검사가 없어 `runs/` 밖을 읽습니다
`run_limit_signal("../outside/evil")` 이 `runs/` 바깥의 `.json`·`.out` 을 읽습니다.
`tools/aimem_monitor/reader.py` 의 `RUN_ID_RE` 가 같은 문제를 이미 막고 있습니다 - **읽어서**
같은 꼴의 정규식을 `run_limit_signal` **맨 앞**에 두십시오(모듈 상수로). 꼴이 아니면 **`None`**.
```python
_RUN_ID_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")   # reader.RUN_ID_RE 와 같은 뜻
...
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        return None
```
`reader.py` 의 진짜 꼴을 먼저 보고 그와 **같은 엄격함**으로 쓰십시오(점·슬래시로 폴더를 벗어날 수
없어야 합니다). 이 검사는 `try` **바깥**에 두어도 되고 안에 두어도 됩니다.
## 하지 말 것
## 검증
검증 명령이 봅니다: `tests.test_fleet_graph`·`tests.test_fleet_ctl`·`tests.test_fleet` 가 초록이고,
임시 폴더의 가짜 실행 기록 여섯에 대해 `run_limit_signal` 이
`True / None / False / None / None / None` 이며 `report_limit_hit` 의 오인 둘이 사라진 것.
ERROR: Reconnecting... 1/5
