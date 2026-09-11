---
name: "acp-slot-lifecycle"
description: "work/opencode 슬롯 작업 시작/종료 절차 - 시작은 태석님이 /acp spawn, 그 뒤는 클로가 전담. 종료도 클로가 전담"
---

# 슬롯 작업 시작/종료

`/home/tsyi/work/opencode` 의 작업자 슬롯 절차입니다. **태석님 확정 2026-09-11 16:48.**

역할 분담이 핵심입니다. **슬롯을 여는 것만 태석님, 나머지는 전부 클로.**

## 시작

### 1. 명령을 보여드린다

슬롯 개수만큼 줄을 만들어 드립니다. 한 번에 한 줄씩 치시라고 안내합니다.

```
/acp spawn claude --mode persistent --thread auto --cwd /home/tsyi/work/opencode --label aimem-S1
/acp spawn claude --mode persistent --thread auto --cwd /home/tsyi/work/opencode --label aimem-S2
/acp spawn claude --mode persistent --thread auto --cwd /home/tsyi/work/opencode --label aimem-S3
```

- `--mode persistent` 가 기본입니다. 한 번 쓰고 버릴 일이면 `oneshot`
- `--thread auto` 는 자식 스레드를 만들어 묶습니다. `--bind` 와 같이 쓰면 거부됩니다
- `--label` 은 사람이 알아보는 이름일 뿐입니다. **세션키가 유일한 안정 식별자입니다**
- `acp.maxConcurrentSessions` 를 넘지 않는지 먼저 확인합니다 (현재 5)

**왜 태석님이 치셔야 하는가** — 클로의 `sessions_spawn` 은 스레드 바인딩이 안 됩니다
(`thread_binding_invalid`: 클로 세션에서는 디스코드 대화가 해석되지 않음). 그리고 클로가 만든
슬롯은 워커가 내려가면 되살릴 수 없습니다 - 게이트웨이가 세션키의 `claude` 를 `agents.list` 에서
찾는데 없고, 그 등록은 보호된 설정 경로라 클로가 고칠 수 없습니다.

태석님의 `/acp spawn` 은 다릅니다. 게이트웨이 클라이언트 컨텍스트가 없어 스코프 검사를 건너뛰고
(`if (!Array.isArray(scopes)) return null`), `ownerAllowFrom` 의 owner 판정만 받아 통과합니다.

### 2. 태석님이 실행하신다

기다립니다. 재촉하지 않습니다.

### 3. 그다음은 클로가 이어받는다

**세션키를 직접 조회합니다.** 태석님께 여쭙지 않습니다.

```bash
openclaw gateway call sessions.list --json | python3 -c "
import sys,json
d=json.load(sys.stdin)
for s in d.get('sessions',[]):
    if ':acp:' in s.get('key',''): print(s['key'],'|',s.get('label'))
"
```

그다음 순서대로:

1. **`AIMEM.md` 2절 명부**에 세션키를 박습니다. 확인토큰은 폐쇄할 때 미리 발급해 둔 값을 그대로
   씁니다. REV 를 올리고 4절에 로그 한 줄. 린터를 돌립니다
2. **각 슬롯에 개시 브리프**를 보냅니다. 반드시 넣을 것:
   - **슬롯 ID** (`당신의 슬롯 ID 는 S1 입니다`) - 작업자는 자기 세션키를 모릅니다
   - REV 번호와 그 슬롯의 확인토큰 - 작업자가 `AIMEM.md` 실측과 대조합니다
   - 작업 폴더, 할 일, 쓰기 범위
3. 작업자가 REV/토큰 불일치로 되물으면 **거절이 정상 동작**입니다. 밀어붙이지 않습니다

슬롯에 메시지가 닿지 않으면(`Agent "claude" no longer exists in configuration`) 워커가 내려간
것입니다. 클로는 되살릴 수 없으니 태석님께 보고하고 다시 열어 주십사 요청합니다.

## 종료

**전부 클로가 합니다.** 태석님이 "작업 종료" 라고만 하시면 됩니다.

```bash
# 1. 세션 삭제 - 파라미터는 key 다 (sessionKey 아님)
openclaw gateway call sessions.delete --params '{"key":"agent:claude:acp:<uuid>"}' --json

# 2. 남은 것 확인 - 둘 다 비어야 한다
openclaw gateway call sessions.list --json | python3 -c "
import sys,json;d=json.load(sys.stdin)
print([s['key'] for s in d.get('sessions',[]) if ':acp:' in s.get('key','')])"
ps -eo pid,args | grep -E "claude-agent-acp|acpx" | grep -v grep | wc -l

# 3. 아카이브 정리 - 태석님은 이게 쌓이는 걸 원치 않으신다
find /home/tsyi/.openclaw -name "*.jsonl.deleted.*" -delete
```

`sessions.delete` 는 하네스 프로세스까지 함께 죽입니다. 따로 kill 하지 마십시오.
백업은 만들지 않습니다 - 남길 산출물은 작업자가 `.aimem/outbox/<슬롯>.md` 에 써 둔 쪽을 씁니다.

### 명부 갱신

`AIMEM.md` 2절에서 세션키를 `-` 로 비우고 비고에 폐쇄 날짜를 적습니다.

**확인토큰 칸은 비우지 마십시오.** 린터가 6자리 hex 를 요구해서 `(없음)` 은 `ROSTER_TOKEN_INVALID` +
`ROSTER_DUPLICATE_TOKEN` 을 냅니다. 재개설용 토큰을 미리 발급해 넣으면 다음에 열 때 그대로 씁니다.

```python
import re, secrets
used = set(re.findall(r'`([0-9a-f]{6})`', open('AIMEM.md').read()))
t = secrets.token_hex(3)   # used 에 없을 때까지 반복
```

REV 를 올리고 4절에 로그를 남긴 뒤 린터를 돌립니다.

```bash
cd /home/tsyi/work/opencode && python3 tools/aimem_lint.py AIMEM.md
```

`OK: AIMEM.md - 위반 없음` 이어야 끝입니다. **인자를 빼면 usage 만 찍고 종료코드 0 이라
통과한 것처럼 보입니다** - 출력을 눈으로 확인하십시오.
핸드오프 로그 상한(12건)에 걸리면 `python3 tools/aimem_board.py archive-rollover --keep 10`.

## 위임

`~/.claude/CLAUDE.md` 에 상시 위임이 있고 하네스가 `claudeMd` 로 자동 주입합니다.
**태석님이 세션마다 위임하지 않으십니다.** 슬롯을 열기 전에 그 파일이 있는지만 확인합니다.

```bash
test -f ~/.claude/CLAUDE.md && head -5 ~/.claude/CLAUDE.md
```

그 파일을 클로가 고치지 않습니다. 위임의 출처가 지시받는 쪽이 되면 위임이 아닙니다.

## 하지 않는 것

- **커밋하지 않습니다.** `git commit`/`push` 는 하드리밋입니다. 미커밋으로 두고 보고합니다
- 작업자에게 하드리밋을 넘는 지시를 전달하지 않습니다 - 삭제, 의존성 설치, `AIMEM.md` 쓰기,
  슬롯 소유 경로 밖 쓰기. 클로가 위임받은 범위 밖입니다
- `/acp spawn` 을 클로가 우회해서 치려 하지 않습니다. `chat.send` 로 슬래시 명령을 넣는 경로가
  있지만 `operator.admin` 스코프에서 막히고, 발신자 신원을 흉내내는 것은 위조입니다
