# T-050 reader.run_detail() - 실행 상세 조회 (요청 8d8d "상세 조회 UI 추가")

태석님이 웹 폼으로 넣은 요청: "작업이나 라벨을 클릭하면 상세내용이 나오면 좋겠다".
프런트가 행을 클릭하면 서버가 `/api/runs/<id>` 로 상세를 내려 주는 구조다.
너는 **데이터 계층만** 만든다. 서버 라우팅과 프런트는 다른 담당이다.

## 할 일
`tools/aimem_monitor/reader.py` 에 함수 하나를 추가한다.

```python
def run_detail(run_id: str, root: pathlib.Path | None = None) -> dict
```

반환 dict 의 **최상위 키는 아래 14개로 고정**한다. 없으면 빈 값으로라도 반드시 넣는다
(프런트가 무조건 읽는다 - 키가 빠지면 화면이 깨진다).

| 키 | 타입 | 내용 |
| --- | --- | --- |
| `id` | str | 받은 run_id 그대로 |
| `found` | bool | 실행 기록이 있으면 True |
| `slot` | str | 예 `S3` (없으면 `""`) |
| `harness` | str | claude/codex/opencode (없으면 `""`) |
| `model` | str | `harness_model()` 로 구한 실행 모델 표기 (없으면 `""`) |
| `label` | str | 라벨 (없으면 `""`) |
| `status` | str | `runs` 표와 같은 값 (`done`/`running`/`lost` 등, 없으면 `""`) |
| `rc` | int \| None | 종료 코드 |
| `elapsed_s` | int \| None | 경과 초 |
| `started` | str \| None | ISO 문자열 |
| `ended` | str \| None | ISO 문자열 |
| `brief` | str | 그 실행에 준 **지시 본문**. 없으면 `""` |
| `report` | str | **보고 본문**. 기존 `_report_body()` 를 그대로 재사용한다. 없으면 `""` |
| `stderr_tail` | str | stderr 마지막 2,000자 이내. 없으면 `""` |
| `paths` | dict | `{"dir":…, "out":…, "err":…, "rc":…, "brief":…}` 문자열 경로. 없는 파일도 경로는 넣되 존재하지 않으면 값 `""` |
| `errors` | list[str] | 읽다 실패한 것 한 줄씩 |

(표가 16행이다 - `paths`/`errors` 포함해 **16개 키**로 읽어라. 위 "14개"는 오기다.)

## 반드시 지킬 것
1. **어떤 입력에도 예외를 던지지 않는다.** 깨진 JSON, 없는 디렉터리, 권한 오류 전부
   `errors` 한 줄로 낮추고 `found: False` 로 돌아온다.
2. **경로 탈출 방어.** `run_id` 가 `^[0-9]{8}-[0-9]{6}-S[0-9]+(-[0-9]+)?$` 에 맞지 않으면
   파일을 건드리지 말고 바로 `found: False` + `errors` 에 `"잘못된 run id"` 를 넣고 돌아온다.
   `../`, 절대경로, 빈 문자열, `None`, 1만 자 문자열 모두 이 경로로 떨어져야 한다.
3. `report` 는 `_report_body(harness, out_path)` 를 쓴다. 보고가 없으면 (11-09 S3 사례)
   빈 문자열이고 `stderr_tail` 이 대신 채워진다. 기존 `fleet.py report` 의 동작과 같다.
4. `brief` 본문이 어디 있는지는 `tools/fleet.py` 의 `cmd_spawn` 이 실행 기록을 어떻게
   남기는지 읽어서 확인하라 (`.aimem/runs/<id>.json` 과 `.aimem/runs/<id>/`). 추측하지 말고 읽어라.
5. 기존 `collect()` 의 동작과 반환 스키마를 **바꾸지 마라.** 순수 추가다.
6. `.aimem/runs/` 를 **쓰지 마라.** 읽기 전용이다.

## 검증 (반드시 직접 돌리고 출력을 보고에 붙여라)
```
python3 -m unittest discover -s tests
python3 -c "
import sys; sys.path.insert(0,'tools')
from aimem_monitor import reader
for rid in ['20261109-172618-S3','20261109-173336-S4','20261109-163112-S1','없는거','../../etc/passwd','',None]:
    d=reader.run_detail(rid)
    print(repr(rid), d['found'], d['slot'], d['harness'], d['rc'], d['elapsed_s'], len(d['report']), len(d['brief']), d['errors'][:1])
    assert set(d)=={'id','found','slot','harness','model','label','status','rc','elapsed_s','started','ended','brief','report','stderr_tail','paths','errors'}, sorted(d)
print('OK')
"
```
`20261109-172618-S3` 는 done/rc=0/850초짜리 실제 실행이다. `report` 가 비어 있지 않아야 한다.

쓰기는 `tools/aimem_monitor/reader.py` 에만 한다. 테스트 파일은 S2 가 따로 쓴다.
보고에 함수 시그니처·키 목록·검증 출력·다음 담당자(서버/프런트)가 알아야 할 주의점을 적어라.
