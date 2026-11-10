# T-064 `reader.py` 3건 - 슬롯별 모델 / 비밀 가림 / 심볼릭 링크 차단

## 쓰기 경로

`tools/aimem_monitor/reader.py` **하나뿐이다.** 테스트(`tests/test_aimem_monitor*.py`)는 S2 소유라
건드리지 마라 - **기존 테스트를 깨지 않는 것이 이 태스크의 제약**이다
(`python3 -m unittest discover -s tests` 가 지금 통과하는 것은 계속 통과해야 한다).

## (1) 슬롯별 모델 표시 - 태석님 요청 `b125`

**지금 틀렸다.** `/api/state` 의 슬롯 명부가 `S1 anthropic/claude-sonnet-5-5` 로 나온다.
S1 은 `opus` 다. `harness_model("claude")` 가 하네스 하나당 모델 하나를 돌려주는데,
claude 하네스에 슬롯이 둘(S1 opus / S4 sonnet) 붙어 있어서 생긴 결함이다.

- **정본은 `tools/fleet_slots.json`** 이다. 지금 내용: `{"S1": {"model": "opus", "harness": "claude"},
  "S4": {"model": "sonnet", "harness": "claude"}}`. `fleet.py` 의 `SLOT_DEFAULT_MODEL` 이 이 파일을
  읽어 `spawn --model` 의 기본값으로 쓴다 (`grep -n "fleet_slots\|SLOT_DEFAULT_MODEL" tools/fleet.py`)
- **고칠 것:** 슬롯 행을 만들 때 (`reader.py:401` 근처, `collect` 의 명부 조립부)
  1. `tools/fleet_slots.json` 에 그 슬롯 항목이 있으면 그 `model` 을 쓰고
     `model_source` 를 `"tools/fleet_slots.json (슬롯별 기본 모델)"` 로 적는다
  2. 없으면 지금처럼 `harness_model(harness)` 로 떨어진다 (S2·S3 는 여기로 간다)
- **기대 결과:** S1 `opus` / S4 `sonnet` / S2·S3 는 `kisti/kistillm` (하네스 설정 출처 표기 유지)
- `harness_model()` 의 claude 분기가 `--model sonnet` 을 **하드코딩**하고 있다(`4.5` 큐 10번).
  슬롯별 값이 정본이 되면 그 하드코딩은 "슬롯 정보가 없을 때의 마지막 기본값" 으로만 남는다 -
  주석을 그렇게 고쳐라. **`openclaw.json` 의 관리자용 opus 를 작업자 모델로 읽지 마라**
- **키 이름(`model`/`model_source`)과 `SLOT_KEYS` 집합은 바꾸지 마라.** S2 테스트가 못박았다

## (2) 비밀 가림 - S4 적대적 검수 1번 (공개 전 필수)

웹 UI 가 **외부에 공개된다**(태석님 19:05). `run_detail()` 의 `brief` / `report` / `stderr_tail` 은
작업자 기록 원문을 그대로 싣는다. 작업자가 `env` 나 `cat .aimem/tls/access-token` 을 한 번이라도
찍으면 그 값이 `.aimem/runs/<id>.{out,err}` 에 남고, 인증을 통과한 사람에게 그대로 보인다.
접근 토큰이 새면 세션을 다시 발급할 수 있어 **인증 전체가 무너진다.**

- `run_detail()` 이 `brief`·`report`·`stderr_tail` 을 돌려주기 **직전에** 다음 패턴을 `***` 로 바꿔라.
  한 군데(작은 함수 하나)에서 하고 세 필드에 같이 적용해라:

  | 무엇 | 정규식(대소문자 무시) |
  | --- | --- |
  | 64자 hex (접근 토큰 꼴) | `\b[0-9a-f]{64}\b` |
  | Bearer 토큰 | `Bearer\s+[A-Za-z0-9._\-]{8,}` |
  | GitHub 토큰 | `gh[pousr]_[A-Za-z0-9]{20,}` |
  | OpenAI/Anthropic 꼴 키 | `sk-[A-Za-z0-9_\-]{12,}` |
  | 환경변수 대입 | `(KISTI_API_KEY|GITHUB_CLIENT_SECRET|ANTHROPIC_API_KEY|OPENAI_API_KEY)\s*[=:]\s*\S+` |
  | 브리프의 확인토큰 줄 | `확인토큰:\s*[0-9a-f]{6}` → `확인토큰: ***` |

  치환은 **값만** 가리고 이름은 남겨라(`KISTI_API_KEY=***`). 무엇이 가려졌는지 보여야 한다.
  40자 hex 는 git SHA 라 **건드리지 마라**(S4 확인). 64자만 가린다
- `brief` 는 본문이 길다 - 치환을 전체에 한 번만 돌려라(필드당 한 번, 루프 안에서 반복 금지)

## (3) 심볼릭 링크 차단 - S4 검수 7번

`run_detail()` 이 `.aimem/runs/<id>.{brief.md,out,err}` 를 `read_text()` 로 읽는다.
그 경로가 심볼릭 링크이면 링크가 가리키는 **임의 파일**이 응답에 실린다(작업자는 그 디렉터리에
쓰기 권한이 있다). 읽기 전에 막아라:

- `p.is_symlink()` 이거나 `p.resolve()` 가 `.aimem/runs` 디렉터리 밖이면 **읽지 말고 건너뛰고**
  `errors` 에 한 줄 남겨라 (`f"{p.name} 은 심볼릭 링크라 읽지 않았습니다"`)
- `paths` 딕셔너리에 경로 문자열을 담는 것 자체는 그대로 둔다(이번에 바꾸지 않는다)

## 하지 말 것

- `/api/state` 의 **키를 더하거나 빼지 마라.** `root`·`paths`·`slots[].token`·`kisti.url` 이
  공개면에 나가는 문제(S4 검수 5·6번)는 **다음 라운드 과제**로 큐에 올려 뒀다 - 프런트·테스트와
  같이 움직여야 해서 이번에 건드리면 화면이 깨진다
- `collect()` / `run_detail()` 의 시그니처와 키 목록(`DETAIL_KEYS`) 변경 금지

## 검증 (이대로 돌리고 출력을 보고에 붙여라)

```bash
python3 -m unittest discover -s tests 2>&1 | tail -5
PYTHONPATH=tools python3 -c "
from aimem_monitor import reader
s=reader.collect()
print([(x['slot'],x['model'],x['model_source'][:40]) for x in s['slots']])
print('errors:', s['errors'])
"
PYTHONPATH=tools python3 -c "
from aimem_monitor import reader
import re
d=reader.run_detail('T-060-S1-a1-192258')
blob=(d['brief'] or '')+(d['report'] or '')+(d['stderr_tail'] or '')
print('64hex 남음:', re.findall(r'\b[0-9a-f]{64}\b', blob)[:2])
print('확인토큰 줄:', [l for l in (d['brief'] or '').splitlines() if '확인토큰' in l])
print('키 16개:', len(d)==16)
"
```

세 번째 명령의 `확인토큰 줄` 은 `확인토큰: ***` 이어야 한다.

## 보고

첫 줄 상태. ① 고친 함수와 줄 범위 ② 위 세 명령의 **실제 출력 그대로** ③ 테스트 건수
(before/after) ④ 다음 담당자가 알아야 할 것.
