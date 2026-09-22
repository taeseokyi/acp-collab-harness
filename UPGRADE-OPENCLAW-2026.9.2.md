# OpenClaw 업그레이드 지시서 — 2026.7.1-2 -> 2026.9.2

작성: 클로(coding) / 2026-09-22 22:1x / 태석님 승인 완료
수행: **이 폴더에서 `claude` 로 기동한 별도 에이전트** (OpenClaw 세션이 아니다)

---

## 0. 이 문서를 읽는 에이전트에게

**이 작업은 AIMEM 규약(`AIMEM.md`) 밖이다.** 슬롯, 아웃박스, REV, 확인토큰, board CLI —
전부 이 폴더의 *다른* 작업용 규약이고 이 업그레이드와 무관하다. 여기서는 그 절차를
따르지 마라. `AIMEM.md` 를 수정하지도 마라. 이 문서와 아래 RUNBOOK 만 따른다.

**그런데 이 폴더의 `CLAUDE.md` 가 걸린다.** 거기 적힌 예외 조항이 이 작업의 본체다:

- 의존성 설치 (`pnpm add -g openclaw@2026.9.2`)
- 자기 슬롯 소유 경로 밖 쓰기 (`~/.openclaw/`, `~/.config/systemd/`, `~/.local/share/pnpm/`)
- 삭제 (롤백 시 DB 사이드카 정리)

그 조항은 **"내가 그 대화에서 직접 허용할 때만 한다"** 이다. 문서에 적혀 있다고 허용된 게 아니다.
**태석님이 이 세션에서 직접 "승인한다"고 말씀하시기 전에는 2단계(코어 설치) 이후로 넘어가지 마라.**
읽기와 사전 점검(1단계까지)은 승인 없이 해도 된다.

### 왜 이 폴더의 별도 에이전트가 하는가

게이트웨이를 재시작하면 OpenClaw 에이전트(구름/클로/옥티) 세션이 끊긴다. tmux `agents` 세션도
같이 죽은 전례가 있다(2026-08-25). 즉 **OpenClaw 안에서 실행하면 실행자가 자기 손을 자른다.**
너는 OpenClaw 밖의 순수 CLI라 재시작에 영향받지 않는다. 그래서 이 일을 맡는다.

따라서:
- **`pan-run` 을 쓰지 마라.** 그건 OpenClaw 에이전트용 tmux 래퍼다. 명령을 직접 실행해라
- tmux `agents` 세션이 죽으면 **네가** `agents-session-start` 로 되살린다 (아래 7-(4))
- 완료/실패 보고는 태석님께 이 대화로 직접 한다

---

## 1. 무엇을, 왜

**대상:** OpenClaw 코어 `2026.7.1-2` -> `2026.9.2` + 외부 플러그인 6개

**목적:** 업스트림 이슈 [#120006](https://github.com/openclaw/openclaw/issues/120006) 수정분 수령.
증상은 **한 세션키에 CLI 계보 둘이 동시에 살면서 서로 모르는 채 같은 파일을 고치는 것**이다.
2026-09-22 하루에 15회 `invalidated:message-policy` 가 났고 그중 2회가 실제로 중복 실행이 됐다.
피해 실례: `AIMEM.md`/`fleet.py`/백업 아티팩트가 "누가 썼는지 모르는 채" 바뀌었다.

수정 PR 3건(#120108, #121509, #132185)은 **`v2026.8.1` 시점에 이미 포함**돼 있다.
현재 라인(`extended-stable` 2026.7.x)에는 백포트되지 않았다 — 커밋 조상 관계로 실측 확인했다.

**왜 최신(9.5)이 아니라 9.2 인가 — Node 때문이다.**

```
openclaw@2026.9.2  engines.node: ">=22.22.3 <23 || >=24.15.0 <25 || >=25.9.0"   <- 현재 Node v22.23.2 통과
openclaw@2026.9.5  engines.node: ">=24.16.0 <25 || >=26.1.0"                    <- 통과 못 함
```
9.3 릴리스 노트: *"Upgrade Node before OpenClaw to prevent SQLite text truncation."*
**9.2 가 Node 22 를 지원하는 마지막 버전이다.** 필요한 수정은 8.1 에 이미 있으므로 Node 를
건드리지 않고 목적을 달성할 수 있다.

**9.2 는 종착지가 아니라 정거장이다.** 9.5 노트에 *"Users updating from 2026.9.2 must follow
the manual schema-upgrade instructions"* 가 있다. 트랜잭션 펜싱은 9.3부터라 **9.2 가 마지막
"펜스 없는 업데이터"** 다. 그리고 *"Package rollback cannot undo migrated state"* —
**9.2 로 올린 뒤 7.1 로 되돌리는 것은 패키지만으로 보장되지 않는다. 백업이 유일한 롤백 수단이다.**

---

## 2. 명령집은 이 문서가 아니라 RUNBOOK 이다

복붙할 명령 전문은 백업 안에 있다. **먼저 이 파일을 읽어라. 이게 정본이다.**

```
~/backups/openclaw-pre-upgrade-20260922-2108/RUNBOOK.md      <- 업그레이드 A + 롤백 B 전체
~/backups/openclaw-pre-upgrade-20260922-2108/MANIFEST.md     <- 백업에 무엇이 들었나
```

**복구 원본 우선순위 (RUNBOOK 머리에도 같은 내용이 있다):**

1. `~/backups/openclaw-pre-upgrade-20260922-2108/` **디렉터리** — 이미 풀려 있다. 절차는 전부 이걸 쓴다
2. 디렉터리가 상했으면 `~/backups/openclaw-pre-upgrade-20260922-2108-full.tar.gz` 를 푼다
3. **`*.INCOMPLETE-DO-NOT-USE` 로 끝나는 41MB 파일은 쓰지 마라.** 21:08 최초본이고
   `local-bin` / `dist-patched` / `claude-memory` / `config/pnpm-workspace.yaml.bak` 이 빠져 있다

**2순위(tar)로 후퇴할 때는 RUNBOOK 의 "무결성 검증" 절(19행)을 먼저 돌려라.** 판별은 파일 시각이
아니라 해시로 한다 — 문서를 고칠 때마다 다시 말아서 시각 라벨이 세 번 어긋난 전례가 있다.

백업에 든 것(요약): 상태 DB 4개(온라인 백업 API로 뜬 일관 스냅샷, `integrity_check ok` 확인),
세션 트랜스크립트 5개 에이전트분, 설정 일체(`openclaw.json`/`.env`/`credentials`/`identity`/
`devices`/`cron`/`exec-approvals.json`), systemd 유닛 본체 + 드롭인 2개, `~/.local/bin/` 스크립트,
**패치 적용된 dist 사본**, 롤백용 tgz(7.1 코어 + discord 플러그인), 클로/구름/옥티 메모리.

---

## 3. 먼저 알아야 할 함정 셋 (이것 때문에 문서가 길다)

### (가) pnpm 전역 override — 설치가 "성공"하고도 구버전이 계속 돈다

`~/.local/share/pnpm/global/5/pnpm-workspace.yaml` 끝에 이게 살아 있다:

```yaml
overrides:
  openclaw: link:../../../../../work/openclaw
```

그리고 `/home/tsyi/work/openclaw` 에 **2026.7.1 소스 체크아웃이 실재한다**(커밋 `0790d9f`, 지금 도는 버전과 동일).
`pnpm add -g` 는 이 파일을 다시 읽는다. 발동하면 레지스트리 대신 로컬 체크아웃을 링크하고,
**설치는 성공 메시지로 끝나며 게이트웨이는 7.1 을 계속 돌린다.**
게다가 그 체크아웃 dist 는 카탈로그 패치가 안 된 원본이다(실측: `opus-5` 문자열 체크아웃 0개 파일 / 설치본 3개 파일).
결과는 **opus-5 가 opus-4-8 로 고착되고 `/new` 로도 안 풀리는 상태**다.

-> RUNBOOK `A.-1` 에서 **`overrides:` 블록 두 줄만** 제거한다(백업 `.pre-92` 를 남긴다).
`~/work/openclaw` 디렉터리 **자체는 지우지 마라.** 태석님 소유이고 이슈 조사에 쓴 자산이다.

### (나) 카탈로그 패치가 엉뚱한 곳에 먹으면서 `--check` 는 전부 초록

`openclaw-opus5-catalog-patch` 의 `find_dist()` 는 **1순위 후보가 `which openclaw` 를
`resolve()` 로 끝까지 따라간 경로**다. override 가 발동해 `node_modules/openclaw` 가 체크아웃
링크가 되면, 패치 스크립트는 **설치본이 아니라 체크아웃을 패치하고 `--check` 는 FAIL 0 을 띄운다.**
자기모순이 없어서 버전 문자열 확인보다 한 겹 더 안 잡힌다.

-> **스크립트 첫 줄이 찍는 dist 경로를 반드시 눈으로 읽어라.**

```
dist: /home/tsyi/.local/share/pnpm/global/5/node_modules/openclaw/dist   <- 정상
dist: /home/tsyi/work/openclaw/dist                                      <- 나오면 즉시 중단
```

검증은 셋을 교차한다 (RUNBOOK `A.-0.5`): `readlink -f node_modules/openclaw` /
`package.json` 버전 / `grep -c 'opus-5' dist/cli-constants-*.js` (패치 후 **3**).
**`dist/*.bak` 개수는 지표가 아니다** — 실측 0건이고 이 스크립트는 `.bak` 을 남기지 않는다.

### (다) 롤백 시 WAL 사이드카 — 순서를 틀리면 복구가 아니라 DB 파괴다

DB 4개가 전부 WAL 모드이고 지금도 사이드카가 살아 있다(`state` WAL 4.2MB, `coding` WAL 14.7MB).
백업 tar 에는 `.sqlite` **본체만** 들어 있다(정상이다 — 온라인 백업 API로 떴다).
`.sqlite` 만 덮으면 **9.2 스키마로 쓰인 WAL 이 복원된 7.1 DB 위에 재생된다.**
SQLite 는 WAL 이 그 DB 의 것인지 검증하지 않는다.

-> **사이드카 제거가 본체 복원보다 반드시 먼저다.** RUNBOOK `B.5` 에 순서대로 적혀 있다.
`ls`/`find` 로 잔존 0건을 확인한 뒤에 복원한다.

---

## 4. 태석님 승인 완료 항목 (이 세션에서 재확인 후 수행)

아래 넷은 2026-09-22 태석님이 승인하셨다. 다만 3절 조항대로 **이 대화에서 한 번 더 구두 확인**을 받아라.

1. **`overrides:` 블록 제거** (RUNBOOK `A.-1`)
2. **`agents.list` 의 `main` 보정** — 아래 5절
3. **9.2 새 기본값 차단 — self-learning / swarm** — 아래 7-(6)
4. **업그레이드 실행 + 재시작**

---

## 5. 설정 편집 (게이트웨이 정지 후, 코어 설치 전에)

**`agents.list` 에서 `main` 만 `name`/`workspace`/`agentDir` 이 전부 없다.** coding/review 는 셋 다 명시돼 있다.
8.1 릴리스 노트에 *"migrate legacy main-session history to its clear owner, and reuse `main`
as an ordinary agent ID after required doctor repairs"* 가 있다 — **우리가 정확히 그 대상이다.**
defaults 상속으로 같은 경로에 떨어지므로 파국 확률은 낮지만, 마이그레이션이 추론할 여지를 없앤다.

현재:
```json
{"id": "main", "subagents": {"allowAgents": ["coding", "review"]}}
```
목표:
```json
{"id": "main",
 "name": "main",
 "workspace": "/home/tsyi/.openclaw/workspace",
 "agentDir": "/home/tsyi/.openclaw/agents/main/agent",
 "subagents": {"allowAgents": ["coding", "review"]}}
```
(두 경로 모두 실재를 확인했다. defaults 로 지금 해석되는 값과 동일하다 — 값을 바꾸는 게 아니라
암묵을 명시로 바꾸는 것뿐이다.)

**편집 방법: 게이트웨이가 정지된 상태에서 `~/.openclaw/openclaw.json` 을 직접 고친다.**
핫리로드 경합을 피하려는 것이다. 순서:

```bash
systemctl --user stop openclaw-gateway     # RUNBOOK A.0
cp -a ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.pre-92
python3 - <<'PY'
import json, os
p = os.path.expanduser('~/.openclaw/openclaw.json')
c = json.load(open(p))
for a in c['agents']['list']:
    if a.get('id') == 'main':
        a.setdefault('name', 'main')
        a.setdefault('workspace', '/home/tsyi/.openclaw/workspace')
        a.setdefault('agentDir', '/home/tsyi/.openclaw/agents/main/agent')
json.dump(c, open(p, 'w'), ensure_ascii=False, indent=2)
PY
python3 -c "import json,os;json.load(open(os.path.expanduser('~/.openclaw/openclaw.json')));print('JSON OK')"
```

`.pre-92` 사본은 롤백 때 `openclaw.json` 을 되돌리는 용도로도 쓴다
(백업 `$B/config/openclaw.json` 이 정본이고, 이건 편집 직전 스냅샷이다).

---

## 6. 실행 순서

RUNBOOK `A` 절을 그대로 따른다. 단계 번호는 RUNBOOK 기준이다.

| 단계 | 내용 | 비고 |
|---|---|---|
| A.-1 | pnpm `overrides:` 제거 | **가장 먼저.** 3-(가) |
| A.0 | `systemctl --user stop openclaw-gateway` | 멈추고 시작한다 |
| **5절** | `openclaw.json` 의 `main` 보정 | 이 문서 5절 |
| A.1 | `doctor` / `cron list` / systemd PATH 사전 기록 | 사후 `diff` 원본 |
| A.2 | `pnpm add -g --allow-build=openclaw openclaw@2026.9.2` | `--allow-build` 필수 |
| A.-0.5 | **설치 검증 3줄** | 하나라도 어긋나면 4단계로 가지 마라 |
| A.3 | discord 플러그인만 먼저 | 연락 경로 확보 |
| A.4 | 카탈로그 패치 재적용 | **첫 줄 dist 경로 확인** (3-(나)) |
| A.5 | 기동 + **디스코드 3계정 실사격** | 실패하면 즉시 롤백 B |
| A.6 | 나머지 플러그인 5개 + 재시작 | acpx/brave/firecrawl/perplexity/tavily |
| A.7 | 사후 검증 5종 + 아래 7절 | |

**플러그인을 나눠 설치하는 이유는 버전 정합이 아니라 원인 격리다.**
지금도 코어 `7.1-2` / 플러그인 `7.1` 로 패치 레벨이 어긋난 채 6개 다 정상 로드되고 doctor 오류 0이다.
한 번에 갈면 실패했을 때 원인이 7갈래이고, **그중 discord 가 죽으면 연락 경로가 끊긴 채로
원인을 찾아야 한다.** 그래서 코어 -> discord -> 실사격 -> 나머지 순이다.

**A.5 의 디스코드 실사격은 태석님 손이 필요하다.** 네가 대신 못 한다.
"디스코드에서 아무 채널에 한 줄 보내 보시고 답이 오는지 봐 주십시오" 라고 요청해라.
3계정 = 구름(main) / 클로(coding) / 옥티(review).

---

## 7. 사후 검증 — RUNBOOK A.7 에 더해서

RUNBOOK 의 (1)~(5)를 먼저 다 돌린다. 요지만 옮기면:
`doctor` 앞뒤 diff / `cron list` 2건 온전 / **systemd PATH 드롭인** / tmux 복구 / `/status` 로 설정이
"남았는지"가 아니라 "먹었는지".

**드롭인 주의:** `~/.config/systemd/user/openclaw-gateway.service.d/` 의 `10-conda.conf` 와
`override.conf` 는 패키지 밖이라 **생존한다.** 하지만 `Environment=PATH` 는 prepend 가 아니라
**치환**이다. 9.2 본체가 새 경로를 추가했는데 드롭인에 없으면 그 경로가 조용히 사라진다.
`diff` 로 반드시 대조해라. 고칠 때는 사본(`10-conda.conf.pre-92`)을 먼저 남긴다 — 롤백에서 되돌려야 한다.
드롭인 맨 앞의 `~/miniconda3/envs/openclaw/bin` 은 절대 빼지 마라(conda 파이썬 고정이다).

### (6) 9.2 새 기본값 차단 — self-learning / swarm

현재 `openclaw.json` 에 관련 키가 **없다**(`swarm`/`selfLearning`/`learning` 전부 null).
즉 **9.2 의 새 기본값을 그대로 받는다.** 우리 운영과 충돌하는 게 둘이다.

- **Automatic self-learning (8.1 도입, 기본 on)** — 스킬 자동 적용.
  우리 규칙은 **"스킬 제안은 태석님 승인 시에만 적용"** 이다. 정면 충돌
- **Swarm 기본 활성 (9.2)** — 병렬 팬아웃.
  우리는 에이전트당 tmux 팬 1개 + `flock` 직렬화다. 팬아웃이 같은 팬에 몰리면
  락 대기만 쌓여 `pan-run` 이 `exit 67`(락 대기 초과)을 낸다

**정확한 설정 키 이름을 나는 모른다. 7.1 스키마에 없는 키라 확인할 방법이 없었다.**
추측해서 쓰지 마라. 9.2 를 깐 뒤 실물에서 찾아라:

```bash
D=~/.local/share/pnpm/global/5/node_modules/openclaw
grep -roh 'selfLearning[A-Za-z.]*\|self_learning\|autoApplySkill[A-Za-z]*\|swarm[A-Za-z.]*' $D/dist | sort | uniq -c | sort -rn | head -30
openclaw doctor 2>&1 | grep -i -e swarm -e learning
```

찾으면 `openclaw.json` 에 **명시적으로 off** 를 박고 게이트웨이를 재시작한다.
**10분 안에 못 찾으면 추측하지 말고 그대로 두고 태석님께 보고해라.**
이건 파괴적 항목이 아니라 행동 기본값이다 — 나중에 관찰해서 끌 수 있다.
반대로 잘못된 키를 박으면 스키마 검증에 걸려 게이트웨이가 안 뜬다. 그게 더 나쁘다.

### (7) 고아 에이전트 디렉터리 (확신 없음, 관찰만)

`~/.openclaw/agents/` 에 `claude` 와 `opencode` 가 실재하는데 `agents.list` 에는 없다
(`main`/`coding`/`review` 뿐). 8.1 명부 마이그레이션이 *"required doctor repairs"* 를 말하는
맥락이라 doctor 가 이 고아들을 건드릴 가능성이 있는데 **근거를 찾지 못했다.**
백업에 5개 전부 들어 있어 잃을 건 없다. **A.7-(1) doctor diff 에 이 둘이 언급되는지만 봐 두고 보고해라.**

### (8) ACP 래퍼 — 덤으로 고쳐질 수 있는 것

`~/.openclaw/acpx/claude-agent-acp-wrapper.mjs` 에 **`session/load` 처리가 없다**(현재 7.1 기준, 실측).
그래서 `sessions_spawn` 의 `resumeSessionId` 가 **조용히 무시되고 새 세션이 열린다** — 에러도 안 난다.
래퍼는 런타임이 스폰할 때 재생성되므로 9.2 템플릿으로 바뀐다.
**고쳐졌는지 확인만 해 주면 고맙다** (기능 요구는 아니다):

```bash
grep -c 'session/load' ~/.openclaw/acpx/claude-agent-acp-wrapper.mjs
```

---

## 8. 롤백

**시한: 재시작 후 30분.** 그 안에 A.7 검증이 통과하지 않으면 붙잡고 고치지 말고 RUNBOOK `B` 로 간다.
**롤백은 원상복구가 아니라 21:08 시점으로 시간이 되감기는 것이다.** 늦을수록 잃는 게 크다.
30분을 넘겼으면 롤백보다 전진 수리가 낫다 — 그 판단은 태석님 몫이다.

RUNBOOK `B` 요약: 정지 -> 코어 tgz 되돌리기(네트워크 없이 가능) -> discord 먼저 ->
나머지 5개 -> 카탈로그 패치(실패 시 백업 dist 통째 덮기) -> **설정/DB 복원(WAL 사이드카 먼저!)** ->
systemd 복원(드롭인 포함) -> 확인 -> 스크립트 복원.

**롤백에서 빠뜨리기 쉬운 것 둘:**
- A.7-(3)에서 `10-conda.conf` 의 PATH 를 9.2 본체에 맞춰 손댔다면 **반드시 되돌려라.**
  7.1 본체 + 9.2용 PATH 조합이 남으면 조용히 어긋난다
- pnpm `overrides:` 는 **되살릴 필요가 대개 없다.** 롤백은 레지스트리 `2026.7.1-2` 로 가는 것이고
  override 는 로컬 체크아웃을 물리는 개발용이다. 태석님이 `~/work/openclaw` 로 개발하실 때만 되돌린다

---

## 9. 배경 문서 (읽을 필요는 없다. 근거를 확인하고 싶을 때만)

```
~/.openclaw/shared/handoff/claw-upgrade-readiness-2026-09-22.md   준비 상태 (클로)
~/.openclaw/shared/handoff/octy-upgrade-review-2026-09-22.md      검수 5차 (옥티, 800행+)
~/.openclaw/shared/handoff/octy-upgrade-precheck-2026-09-22.md    사전 점검 (옥티)
```

**주의: 이 셋은 OpenClaw 에이전트들이 쓴 작업 문서라 사람 이름과 진행 중 서술이 섞여 있다.**
명령의 정본은 RUNBOOK 이다. 두 문서가 어긋나면 RUNBOOK 을 따르고 어긋났다는 사실을 보고해라.

---

## 10. 끝나면

태석님께 이 대화로 직접 보고한다. 담을 것:

- `openclaw --version` / 플러그인 6개 버전
- A.-0.5 검증 3줄의 실제 출력 (특히 패치 스크립트 `dist:` 첫 줄)
- `doctor` 앞뒤 diff 요약, `cron list` 2건 생존 여부
- systemd PATH 변화 유무 + 드롭인을 손댔는지
- 7-(6) self-learning / swarm — 키를 찾았는지, 껐는지, 못 찾았는지
- 7-(7) 고아 디렉터리 언급 유무 / 7-(8) `session/load` 유무
- tmux `agents` 복구 여부
- **중단하거나 건너뛴 단계가 있으면 반드시 그것부터**

성공하면 OpenClaw 에이전트들(구름/클로/옥티)이 다시 뜨므로 그쪽으로도 소식이 간다.
실패해서 게이트웨이가 정지 상태로 남으면 **9.2 는 사후 검증 실패 시 자동 복구를 하지 않는다.**
그때 다음 수를 둘 수 있는 건 터미널 앞의 사람과 너뿐이다.
