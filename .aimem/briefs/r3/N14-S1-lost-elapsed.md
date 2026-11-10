# 요청 `c87c` 1항 - lost 실행의 경과 시간이 영원히 늘어난다 (`reader.py` 만 쓴다)

**태석님 지적 2026-11-09 17:55.** 실행 표의 `20261109-172329-S3`(lost)이 **27분 넘게 경과가 계속
늘어나고 있다.** 작업자는 이미 없는데 화면은 아직 일하는 것처럼 보인다.

**원인:** `.rc` 파일이 없어 `_collect_runs()` 가 끝 시각을 `now` 로 계산한다.

## 할 일
`state == "lost"` 인 실행의 경과를 **멈춰라.** 끝 시각은 이 순서로 구한다:
1. `.aimem/runs/<id>.lost` 마커의 JSON `ended` 필드 (`fleet.py reap` 이 쓴다 - **이미 있는 명령이다**)
2. 마커가 없거나 깨졌으면 그 실행의 기록 파일들(`<id>.json`/`.out`/`.err`/`.brief.md`)의 **마지막 mtime**

`fleet.py` 에 `_run_last_mtime()` 이 이미 이 일을 한다. **다시 짜지 말고 읽고 쓰라** -
같은 규칙이 두 군데 있으면 CLI 표와 웹 화면이 다른 숫자를 말하게 된다.

`running` 실행의 경과는 지금처럼 `now` 기준으로 계속 늘어나야 한다. **lost 만 멈춘다.**

## 반드시
- `collect()` 의 **반환 스키마를 바꾸지 마라.** 키를 더하지도 빼지도 마라
- `run_detail()` 과 `median_durations()` 는 건드리지 마라 (방금 다른 작업에서 고쳤다)
- `.aimem/runs/` 는 **읽기 전용**이다. `.lost` 마커를 쓰는 것은 `fleet.py reap` 이지 reader 가 아니다

## 검증 (출력을 보고에 붙여라) - 태석님이 요구한 수용 기준이다
```
python3 -c "
import sys,time; sys.path.insert(0,'tools')
from aimem_monitor import reader
a={r['id']:(r['status'],r['elapsed_s']) for r in reader.collect()['runs']}
time.sleep(3)
b={r['id']:(r['status'],r['elapsed_s']) for r in reader.collect()['runs']}
for k in sorted(a):
    if a[k][0]=='lost': print(k, a[k], '->', b[k], 'OK' if a[k]==b[k] else '아직 늘어남!')
for k in sorted(a):
    if a[k][0]=='running': print(k, a[k], '->', b[k], '(running 은 늘어나야 정상)')
"
python3 -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|^FAILED"
```
`20261109-172329-S3` 의 경과가 **두 호출 사이에 변하지 않아야** 통과다. 그 값이 실제 작업자가
살아 있던 시간(약 1,377초)과 얼마나 맞는지도 한 줄로 적어라.
