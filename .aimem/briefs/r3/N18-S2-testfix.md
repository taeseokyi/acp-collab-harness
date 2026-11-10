# 테스트 한 건의 기대값을 고친다 (`tests/test_aimem_monitor_detail.py` 만)

네 보고가 정확했다. 다만 **"진짜 결함" 분류는 틀렸고, 틀린 쪽은 코드가 아니라 내가 준 계약이다.**

`test_collect_graphs_bad_attempts` 는 `{"nodes":[{"attempts":[None]}]}` 에서 `errors` 1건을 기대한다.
그런데 **서버가 그 노드를 버리지 않고 `last_run=None` 으로 살려 쓰는 쪽이 옳다** -
그래프 파일 하나를 통째로 버리면 멀쩡한 나머지 노드까지 화면에서 사라진다.
`attempts` 원소가 dict 가 아닌 것은 "읽을 수 없는 파일" 이 아니라 "마지막 run id 를 모르는 노드" 다.

## 할 일 (이 한 가지만)
`test_collect_graphs_bad_attempts` 의 기대를 아래로 바꾼다.
- **예외를 던지지 않는다** (이건 그대로 유지 - 이게 이 테스트의 핵심이다)
- 결과가 리스트다
- **그 그래프가 결과에 남아 있고**, 그 노드의 `last_run` 이 `None` 이며 `attempts` 가 정수다
- `errors` 건수는 **단언하지 않는다** (0 이어도 1 이어도 통과)

`{"nodes": ["x"]}`(노드가 객체가 아님) 쪽 테스트는 **지금 그대로 둬라** - 그건 파일을 읽을 수
없는 경우가 맞고 `errors` 1건이 옳다.

다른 테스트는 **한 줄도 건드리지 마라.** `tests/test_aimem_monitor.py` 도 건드리지 마라.

## 검증
```
python3 -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|^FAILED"
```
`OK` 가 나와야 끝이다. 바꾼 단언을 보고에 그대로 붙여라.
