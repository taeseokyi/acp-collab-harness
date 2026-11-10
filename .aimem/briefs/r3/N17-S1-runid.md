# 긴급 - run id 체계가 바뀌었다. `reader.run_detail()` 이 새 id 를 전부 거절한다

**태석님이 2026-11-09 18:15 에 식별자 체계를 바꿨다**(`tools/fleet.py:405`).
네가 아까 넣은 `RUN_ID_RE` 는 옛 꼴만 받으므로 **지금 뜨는 실행을 전부 "잘못된 run id" 로 떨군다.**

새 꼴: `<태스크>-<슬롯>-a<시도>-<HHMMSS>` — 예 `T-053-S3-a3-181328`
       태스크가 없는 임시 실행은 `ADHOC-S3-a1-181328`
옛 꼴: `20261109-172618-S3` — **`.aimem/runs/` 에 그대로 남아 있으므로 계속 받아야 한다**

관리자 쪽(`tools/aimem_monitor/__init__.py` 의 `RUN_ID_RE`)은 이미 둘 다 받게 고쳤다.
그 정규식과 **같은 것**을 쓰면 된다:
```
(?:[0-9]{8}-[0-9]{6}-S[0-9]+|(?:T-[0-9]+[A-Z]?|ADHOC)-S[0-9]+-a[0-9]+-[0-9]{6})(-[0-9]+)?
```
가능하면 `from . import RUN_ID_RE` 로 **한 군데서 가져다 써라** - 같은 규칙을 두 군데 적으면
다음에 체계가 또 바뀔 때 한쪽만 고쳐진다. 순환 import 가 나면 그때만 복사하고 주석으로 출처를 적어라.

## 반드시
- `fullmatch` + `re.ASCII` 로 거르는 지금 동작(끝의 `\n`, 전각 숫자, 경로 탈출 차단)을 **유지하라**
- `collect()` 스키마·`median_durations()`·lost 경과 고정은 건드리지 마라 (방금 네가 고친 것들이다)
- `tools/aimem_monitor/reader.py` 만 쓴다

## 검증 (출력을 보고에 붙여라)
```
python3 -c "
import sys; sys.path.insert(0,'tools')
from aimem_monitor import reader
ok  = ['20261109-172618-S3','ADHOC-S3-a1-181328','T-053-S3-a3-181328','T-5A-S12-a10-000000']
bad = ['../../etc/passwd','','x'*300,'T-053-S3-a3-181328\n','ADHOC-S3-a1-18132','20261109-172618-S3/../x']
for r in ok:  print('받아야 함 ', r, '->', reader.run_detail(r)['errors'][:1] or 'OK(형식 통과)')
for r in bad: print('막아야 함 ', repr(r)[:40], '->', reader.run_detail(r)['errors'][:1])
"
python3 -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|^FAILED"
```
`ok` 목록은 **형식에서 떨어지면 안 된다**(기록이 없어 `found=False` 인 것은 정상 - `errors` 가
"잘못된 run id" 가 아니면 통과다). `bad` 목록은 전부 "잘못된 run id" 여야 한다.
