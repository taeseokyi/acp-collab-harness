---
name: "acp-slot-lifecycle"
description: "work/opencode 작업자 절차 - 일회성 ACP 자식을 클로가 직접 띄우고 출력을 목적 고정 tmux 팬에 남긴다"
---

# 작업자 띄우기와 거두기

`/home/tsyi/work/opencode` 의 작업자 절차입니다. **태석님 확정 2026-09-22 17:29.**
정본은 `AIMEM.md` 의 `8.0` 절이고 이 문서는 실행 절차입니다. 어긋나면 `8.0` 을 따릅니다.

**전부 클로가 합니다.** 태석님이 `/acp spawn` 을 치실 일이 없습니다.

## 왜 바뀌었나

상주 슬롯(`/acp spawn --mode persistent`)은 **완료 통보 경로가 없습니다.** 관리자와 동급인
동료 세션이라 런타임이 끝났다고 알려주지 않습니다. 2026-09-22 에 검수 완료를 세 번 모두
태석님이 직접 알려주셔야 했고, **대기 시간을 특정할 수 없다**는 것이 폐지 사유입니다.

일회성 자식은 부모-자식 관계라 **런타임이 완료를 통보합니다.** 작업자의 자발적 보고에
기대지 않습니다. 실측 4건(22초 / 2분19초 / 2분42초 / 5분2초) 전부 통보가 도달했습니다.

대신 **세션 기록이 이어지지 않습니다.** `resumeSessionId` 는 게이트를 통과하지만 하네스가
이전 대화를 로드하지 않습니다(실측). 그래서 기록은 세션이 아니라 tmux 팬에 쌓습니다.

## 1. 팬 창 확인

```bash
slots-window-start   # 이미 있으면 그대로 유지
```

tmux `agents` 세션의 `slots` 창에 목적 고정 팬 3개가 있습니다.

| 팬 | 목적 | 파일 로그 |
| --- | --- | --- |
| `[S1] 구현` | 코드 수정 | `~/.openclaw/shared/slot-logs/S1.log` |
| `[S2] 테스트` | 테스트 작성/검증 | `~/.openclaw/shared/slot-logs/S2.log` |
| `[S3] 검수` | 검수 | `~/.openclaw/shared/slot-logs/S3.log` |

**창 0(구름/클로/옥티)은 건드리지 않습니다.** 팬을 더하면 `pan-run` 의 팬 인덱스·제목
검증이 깨집니다.

## 2. 자식을 띄운다

`sessions_spawn(runtime="acp", agentId="claude", mode="run", cwd="/home/tsyi/work/opencode",
streamTo="parent", label=...)`.

- **`streamTo: "parent"` 를 반드시 줍니다.** 응답의 `streamLogPath` 가 다음 단계의 입력입니다
- 자식은 맥락을 물려받지 못합니다. 브리프에 **배경 / 할 일 / 쓰기 범위 / 검증 방법**을
  매번 전부 싣습니다. 슬롯 ID·확인토큰·REV 대조는 그대로 유지합니다
- **보고는 응답 본문에 직접 쓰게 합니다.** 자식은 슬롯이 아니므로 아웃박스에 쓰지 않습니다
- 하드리밋을 브리프에 명시합니다: 커밋 금지, 소유 경로 밖 쓰기 금지, `AIMEM.md` 쓰기 금지
- 브리프 머리말은 `tools/fleet.py brief` 로 만들면 쓰기 경로가 `6절` 과 자동 대조됩니다

## 3. 팬에 연결한다

```bash
slot-pane <1|2|3> <streamLogPath> "[S1] T-033 린터 가드"
```

즉시 반환합니다(자식을 기다리지 않습니다). 렌더러는 lifecycle end 를 보면 스스로 끝나고
팬이 프롬프트로 돌아옵니다.

- `exit 66` 팬 제목 불일치 - 팬이 재배치됐습니다. 보내지 않았습니다
- `exit 69` 팬 사용 중 - 이전 자식이 아직 출력 중입니다. 두 자식을 한 팬에 겹치지 마십시오
- 렌더러: `~/.openclaw/workspace-coding/scripts/acp-stream-render.py`

## 4. 완료를 받는다

런타임이 부모 세션을 깨웁니다. 그 턴에서 **자식 보고를 그대로 받지 말고 직접 재현합니다** -
린터·테스트·diff 를 관리자가 다시 돌려 확인한 뒤 보드와 REV 를 갱신합니다.

팬 스트림이 길면 전문은 파일 로그에서 읽습니다: `~/.openclaw/shared/slot-logs/S3.log`

## 5. 거둔다

```bash
openclaw gateway call sessions.delete --params '{"key":"agent:claude:acp:<uuid>"}' --timeout 60000 --json
find /home/tsyi/.openclaw -name "*.jsonl.deleted.*" -delete
python3 tools/fleet.py close
```

`--params` 입니다(위치 인자가 아닙니다). 키 이름은 `key` 입니다(`sessionKey` 아님).
`sessions.delete` 는 하네스 프로세스까지 죽입니다. 따로 kill 하지 마십시오.

팬과 파일 로그는 지우지 않습니다 - **그게 기록 본체입니다.**

## AIMEM 갱신 순서

린터가 순서를 강제합니다. **`handoff-add` 를 먼저, `rev-bump` 를 나중에** 하십시오.
거꾸로 하면 `[REV_LOG_MISSING]` 으로 저장이 거부됩니다.

```bash
python3 tools/aimem_board.py archive-rollover --keep 10   # 로그 12건 상한에 닿았을 때
python3 tools/aimem_board.py handoff-add --expect-rev <현재> --text "**REV <다음>.** ..."
python3 tools/aimem_board.py rev-bump --expect-rev <현재>
python3 tools/aimem_lint.py AIMEM.md    # OK 문구를 눈으로 확인
```

`aimem_lint.py` 는 **인자를 빼면 usage 만 찍고 종료코드 0** 이라 통과한 것처럼 보입니다.

## 위임

`~/.claude/CLAUDE.md` 에 상시 위임이 있고 하네스가 `claudeMd` 로 자동 주입합니다.
**태석님이 세션마다 위임하지 않으십니다.** 그 파일을 클로가 고치지 않습니다 -
위임의 출처가 지시받는 쪽이 되면 위임이 아닙니다.

## 하지 않는 것

- **먼저 커밋하지 않습니다.** `git commit`/`push` 는 하드리밋입니다. 미커밋으로 두고 보고합니다
- 태석님이 커밋을 허락하셔도 **거두기 절차를 먼저 끝내고** 커밋합니다. 세션 정리·명부
  갱신·REV·린터까지 마친 상태가 한 커밋에 담겨야 저장소가 일관됩니다
- 상주 슬롯을 다시 열지 않습니다. 필요해지면 `8.0` 을 먼저 고치고 태석님 확인을 받습니다

## 참고 - 상주 슬롯이 왜 클로 손으로는 안 열렸나

문턱이 둘이었습니다. ① `sessions_spawn(mode="session", thread=true)` 이
`thread_binding_invalid` 로 거부 - 클로 세션에서는 디스코드 대화가 해석되지 않습니다.
② 게이트웨이가 세션키의 `claude` 를 `agents.list` 에서 찾는데 등록이 없습니다.
태석님의 `/acp spawn` 은 게이트웨이 클라이언트 컨텍스트가 없어 스코프 검사를 건너뛰고
(`if (!Array.isArray(scopes)) return null`) owner 판정만 받아 통과했습니다.
일회성은 스레드를 묶지 않고 부모-자식으로 뜨므로 두 문턱 다 걸리지 않습니다.
