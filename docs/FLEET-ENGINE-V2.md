# 함대 엔진 개선 설계서 (ai-fleet)

- 작성: 2026-11-12, 클로드 코드 (태석님 지시)
- 대상 저장소: `~/work/ai-fleet` (2026-11-12 20:36 에 `~/work/opencode` 에서 이름을 바꿨다 - 5.11 의 '한 것 / 남은 것' 참고)
- 기준: AIMEM REV 162, 커밋 `50176c2`, 실행 기록 277건(2026-11-09 ~ 11-12)
- 상태: **설계 문서.** 이 문서로 코드는 한 줄도 바뀌지 않았다

## 0. 한눈에

| 요구 | 이 문서의 답 | 절 |
|---|---|---|
| openclaw ACP 세션을 없애고 의존성을 완전히 제거 | 의존 지점 14곳을 전부 적고, 지점마다 무엇으로 바꾸는지 정했다 | 2, 6 |
| ACP 세션을 대신할 멀티 하네스 운영 체제 | **하네스 어댑터 + 세션 감독기** 두 부품. 관리자도 작업자와 같은 방식으로 직접 띄운다 | 3 |
| 새 체제로 엔진을 고치고 튜닝해 비효율 제거 | 실측으로 확인한 비효율 10건과 고침 | 4, 5 |
| 수행에 필요한 기술 사항 | 하네스 CLI 사양표, 자료 구조, 설정 파일, 이행 단계, 검증 계획 | 3, 6, 7, 부록 |

핵심은 한 문장이다. **지금도 작업자는 openclaw 없이 CLI 로 직접 뜬다. openclaw 가 꼭 필요한 곳은 '관리자를 띄우고 지켜보는 길' 하나뿐이고, 그 길을 작업자와 같은 길로 합치면 의존이 사라진다.**

---

## 1. 지금 구조 (실측)

### 1.1 한 라운드가 도는 길

```
사람(모니터 '라운드 실행' / fleet_ctl.py round)
  └ fleet_ctl._relay_worker                      ← 배경 프로세스
      └ openclaw agent --agent coding            ← 클로(전달자, kistillm)에게 지시문 전달
          └ 클로: sessions_spawn(runtime:"acp", agentId:"claude")   ← 관리자(Opus) ACP 세션
              └ 관리자: fleet_graph.py new / run                    ← 그래프 실행기 (15초 간격 폴링)
                  └ fleet.py spawn → codex exec / opencode run / claude -p   ← 작업자 (직접 CLI)
```

- 작업자(S1~S4)는 `tools/fleet.py` 의 `_worker_argv()` 가 만든 명령으로 **직접** 뜬다. openclaw 를 거치지 않는다
- 관리자만 `openclaw → 클로 → ACP` 세 단계를 거친다
- 모니터는 관리자 상태를 `openclaw sessions --agent claude --json` 과 `~/.openclaw/acpx/sessions/*.json` 에서 읽는다

### 1.2 수치

| 항목 | 값 | 출처 |
|---|---|---|
| 실행 기록 | 277건 (done 262 · lost 13 · 중단 2) | `aimem.db` `runs` |
| codex(kistillm) 실행 | 93건, 평균 7.5분, 최장 40.1분, 재시도 16건 | 11-11 이후 |
| opencode(kistillm) 실행 | 71건, 평균 8.4분, 최장 45.1분, 재시도 12건 | 〃 |
| claude opus 실행(검수) | 22건, 평균 10.7분, 최장 25.9분 | 〃 |
| 관리자 기동 지연 | R17 2분 5초 · R18 2분 59초 · R19 2분 37초 · R20 3분 58초 | `.aimem/relay/r<N>.json` |
| 그래프 실행기 폴링 | 15초 (`--poll 15`), 이어 달리기 감시 45초 | `fleet_graph.py`, `fleet_ctl.py` |
| 관리자 세션 조회 캐시 | 30초, 첫 조회는 수십 초 '조회 중' | 모니터 실측 |
| R20 관리자 대화 기록 | 797KB, 125단계, 2시간 38분 | 모니터 관리자 카드 |

---

## 2. openclaw 의존 지점 전체

코드에서 `openclaw`·`acp`·`gateway`·`클로` 를 전부 찾아 기능별로 묶었다. **A 는 없으면 엔진이 안 도는 것, B 는 없어도 도는데 기능이 빠지는 것, C 는 글자만 남은 것**이다.

| # | 등급 | 어디 | 무엇을 하나 | 바꿀 것 |
|---|---|---|---|---|
| 1 | A | `fleet_ctl.py:560~583` `RELAY_TEMPLATE`·`NUDGE_TEMPLATE` | 클로에게 "관리자를 ACP 로 띄워라" 는 지시문 | 삭제. 엔진이 직접 띄운다(3.3) |
| 2 | A | `fleet_ctl.py:648~700` `_relay_worker` | `openclaw agent --agent coding --session-key …` 로 전달, 관리자가 안 뜨면 한 번 재촉 | `sessions.spawn(role="manager")` 한 번 |
| 3 | A | `fleet_ctl.py:409~427` `_manager_sessions`·`manager_running` | `openclaw sessions --agent claude --json` 에서 `:acp:` 키를 골라 관리자가 도는지 판정 | DB `sessions` 표 조회 |
| 4 | A | `fleet_ctl.py:499~550` `prepare` | 준비 점검에 `openclaw` 바이너리·게이트웨이 세션 조회가 **필수 항목** | 하네스 CLI 와 공급자 응답 점검으로 교체 |
| 5 | A | `aimem_monitor/server.py:1236~1300` | 관리자 카드·상세를 `openclaw sessions` 와 `~/.openclaw/acpx/sessions/*.json` 에서 만든다 | `.aimem/sessions/<id>/events.jsonl` 에서 |
| 6 | B | `aimem_monitor/server.py:1514~1630` `openclaw_models` | 슬롯 편집의 모델 목록 = `openclaw models list` ∪ `~/.openclaw/openclaw.json` | `fleet.toml` 의 `[providers]` |
| 7 | B | `aimem_monitor/server.py:612~690` `load_monitor_env` | `KISTI_API_KEY` 를 `~/.openclaw/.env` 에서도 읽는다 | 저장소 밖 `~/.config/ai-fleet/env` 한 곳 |
| 8 | B | `fleet.py:136~178` `cmd_close` | 종료 점검에 `openclaw gateway call sessions.list`, 남은 `:acp:` 세션 삭제 안내 | `sessions` 표의 미종료 행 점검 |
| 9 | B | `fleet.py:230~260` `cmd_children` | ACP 자식 세션 목록 | 삭제 (`fleet.py runs` 가 같은 일을 한다) |
| 10 | B | `fleet.py:320~362` `cmd_brief` | 스폰 호출문 `sessions_spawn(runtime:"acp" …)` 을 찍는다 | 삭제 |
| 11 | C | `aimem_lint.py:41` `MANAGER_SESSION_KEY = "agent:claude:acp:"` | AIMEM.md 서문의 관리자 식별자를 고정 | 새 식별자(3.4)로 교체 |
| 12 | C | `AIMEM.md` 서문·8.0 (12곳) | "관리자 = Claude ACP 세션, 클로가 `sessions_spawn` 으로 연다" | 서문·8.0 다시 쓰기 (**AIMEM.md 쓰기는 태석님 허용 필요**) |
| 13 | C | `fleet.py:201~228`, `reader.py:126`, `aimem_db.py:1664` | 모델 출처 설명에 `openclaw.json` 언급 | 글자 고침 |
| 14 | C | `.aimem/briefs/manager-round-standard.md` (2곳), 옛 브리프들 | 관리자 브리프의 ACP·클로 언급 | 표준 브리프만 고침. 옛 브리프는 기록이라 둔다 |

저장소 밖에도 흔적이 있다. 엔진을 떼어 낸 뒤 정리한다.

| 어디 | 무엇 | 처리 |
|---|---|---|
| `~/.openclaw/openclaw.json` 315~352행 | 에이전트 셋의 `workspace`·`cwd` 가 `/home/tsyi/work/opencode` | 함대용 에이전트 항목 삭제 (오픈클로 쪽 작업, `~/work/openclaw` 에서) |
| `~/.openclaw/workspace-coding/AGENTS.md` 307·323행 | 클로의 함대 전달 규칙 | 삭제 |
| `~/.openclaw/.env` 의 `CODEX_PATH` 셰임 | ACP 자식 codex 에 모델 카탈로그를 넣던 장치 | 함대와 무관해짐. 오픈클로가 codex 를 안 쓰면 삭제 |
| `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md` | 위임문의 `~/work/opencode`·"관리자 세션" 문구 | 경로와 관리자 식별 문구 교체 (5.11) |

---

## 3. 새 체제: 멀티 하네스 런타임

부품은 둘이다. **어댑터**는 하네스마다 다른 것을 감추고, **감독기**는 하네스와 무관한 것(프로세스·기록·상태)을 맡는다. 관리자·작업자·검수자는 모두 "세션" 한 가지이고 역할(`role`)만 다르다.

```
tools/fleet/                      ← 새 패키지 (지금의 fleet.py 를 쪼갠다)
  harness/base.py                 ← 어댑터 규약
  harness/claude.py  codex.py  opencode.py  fake.py
  sessions.py                     ← 감독기: spawn / poll / wait / cancel / resume / reap
  providers.py                    ← 공급자 동시성 문지기, 응답 점검
  config.py                       ← fleet.toml 읽기
```

### 3.1 하네스 어댑터

어댑터 하나가 답해야 하는 것은 여섯 가지다.

```python
class Harness(Protocol):
    name: str
    def command(self, spec: SessionSpec) -> Command          # argv · env · stdin 파일 · cwd
    def parse_event(self, line: str) -> Event | None         # 출력 한 줄 → 공통 사건
    def final_report(self, session_dir: Path) -> str         # 마지막 답(보고 본문)
    def limit_signal(self, session_dir: Path) -> bool | None # 사용 한도에 걸렸나 (모르면 None)
    def resume_command(self, spec, prior_id: str, message: str) -> Command | None   # 이어 말하기 (못 하면 None)
    def probe(self) -> ProbeResult                           # 준비 점검: 바이너리·버전·공급자 응답
```

`SessionSpec` 은 `role`(manager|worker|reviewer), `slot`, `model`, `brief_path`, `cwd`, `write_paths`, `tools`(허용 도구), `timeout`, `idle_timeout` 을 담는다.

공통 사건(`Event`)은 다섯 종류면 충분하다: `text`(모델의 말), `tool`(도구 호출과 한 줄 요약), `usage`(토큰·비용), `error`(재접속·한도·시간 초과), `end`(종료와 종료코드).

하네스별 사양 (이 기기에 깔린 판에서 `--help` 로 확인: claude 2.1.322, codex-cli 0.162.1, opencode 1.18.33):

| | claude | codex | opencode |
|---|---|---|---|
| 비대화 실행 | `claude -p` (프롬프트는 stdin) | `codex exec … -` (stdin) | `opencode run "<메시지>"` |
| 사건 흐름 | `--output-format stream-json --verbose` | `--json` | `--format json` |
| 마지막 답만 | `--output-format json` 의 `result` | `-o <파일>` | 사건 흐름의 마지막 text |
| 모델 | `--model opus\|sonnet\|<id>` | `-m <id> -c model_provider=<p>` | `-m <provider>/<model>` |
| 권한 | `--permission-mode`, `--allowedTools` | `--sandbox workspace-write -c sandbox_workspace_write.network_access=true` | 에이전트 설정 |
| 세션 id 지정 | `--session-id <uuid>` | 없음(끝난 뒤 id 를 읽음) | `--title`, id 는 사건에서 |
| 이어 말하기 | `--resume <id>` | `codex exec resume <id> "<말>"` (`--ephemeral` 이면 불가) | `-s <id>` |
| 비용 상한 | `--max-budget-usd` | 없음 | 없음 |
| 지금 쓰는 꼴 | `--output-format json` (끝에 한 번) | `--ephemeral`, 사건 흐름 없음 | 기본 포맷(사람용) |

지금 `_worker_argv()` 는 세 하네스 모두 **끝날 때까지 아무 사건도 내지 않는 꼴**로 띄운다. 그래서 작업자가 살아 있는지 알 길이 파일 수정 시각뿐이다. 어댑터는 세 하네스 모두 사건 흐름 꼴로 띄운다.

`fake.py` 는 검사용이다. 브리프의 지시(`FAKE: write a.txt; report DONE` 따위)를 읽어 파일을 쓰고 보고를 낸다. **검사에서 진짜 하네스가 뜨는 일을 구조적으로 막는 장치**이기도 하다(5.5).

### 3.2 세션 감독기

감독기는 세션 하나를 다음처럼 다룬다.

1. **띄우기** — `subprocess.Popen(…, start_new_session=True)` 로 새 프로세스 그룹을 만든다. stdout 은 `.aimem/sessions/<id>/events.jsonl`, stderr 는 `stderr.log` 로 보낸다. `meta.json` 에 pid·pgid·명령·시작 시각을 적는다
2. **지켜보기** — 프로세스 종료는 `os.waitpid`(자식일 때)나 pidfd 로 즉시 안다. 사건 파일은 이어 읽어 `last_event_at` 을 갱신한다
3. **시간 제한 두 가지** — `timeout`(전체 벽시계)과 `idle_timeout`(마지막 사건 뒤 침묵). 침묵이 길면 공급자가 멈춘 것이다(4.2)
4. **끝내기** — 그룹 전체에 SIGTERM, 5초 뒤 SIGKILL(`os.killpg`). 지금 `_kill_run` 이 하는 일을 감독기 한 곳으로 모은다
5. **거두기** — 종료코드, `final_report`, `limit_signal`, 쓴 파일 목록을 DB 에 적는다
6. **고아 청소** — 감독기가 뜰 때와 `stop`·`prepare` 때, `sessions` 표에 살아 있다고 적힌 pgid 와 실제 프로세스를 맞춰 본다. 표에는 없는데 `AIFLEET_SESSION` 환경변수를 가진 프로세스가 있으면 끝낸다(모든 세션에 이 변수를 넣어 띄운다)

DB 표 하나를 더한다. 지금의 `runs` 는 이 표의 부분집합이므로 옮긴 뒤 뷰로 남긴다.

```sql
CREATE TABLE sessions(
  id TEXT PRIMARY KEY,            -- 'M-R21-193012' (관리자) / 'T-263-S2-a1-193012' (작업자, 지금 run id 그대로)
  role TEXT NOT NULL,             -- manager | worker | reviewer
  round INTEGER, task_id TEXT, slot TEXT,
  harness TEXT NOT NULL, model TEXT, provider TEXT,
  pid INTEGER, pgid INTEGER, harness_session_id TEXT,   -- 이어 말하기에 쓰는 하네스 쪽 id
  state TEXT NOT NULL,            -- queued | running | done | failed | killed | lost | timeout | stalled
  started TEXT, ended TEXT, last_event_at TEXT,
  rc INTEGER, report_status TEXT,
  tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL,
  fail_kind TEXT                  -- work | infra | limit | timeout (4.3 재시도 정책이 본다)
);
```

`queued` 가 새 상태다. 공급자 문지기(3.5)가 자리를 줄 때까지 기다리는 세션이다.

### 3.3 관리자도 세션이다

관리자는 `role="manager"` 인 claude 세션일 뿐이다.

```
claude -p --model opus --session-id <uuid> \
  --output-format stream-json --verbose \
  --permission-mode acceptEdits --allowedTools "<관리자 도구 목록>" \
  --settings <관리자용 settings.json>   < rounds/R<N>/brief.md
```

- 지시문은 지금처럼 `rounds/R<N>/brief.md` 를 stdin 으로 준다. 클로의 전달 지시문·재촉문은 없어진다
- 작업자를 띄울 때 지우는 중첩 표식(`_CLAUDE_NESTED_ENV`)은 관리자를 띄울 때도 지운다
- 관리자 허용 도구는 작업자보다 넓다: `fleet_graph.py`·`fleet.py`·`aimem_db.py`·`aimem_board.py`·`aimem_lint.py` 실행, AIMEM.md·`.aimem/`·`rounds/` 쓰기. 지금 ACP 는 `permissionMode: approve-all` 이라 **무엇이든 허용**인데, 새 체제에서는 목록으로 좁힌다. `git commit/push`·삭제·설치는 지금 위임문대로 목록에 넣지 않는다
- 기동 지연은 프로세스 하나 뜨는 시간(몇 초)이다. 지금은 2~4분이다(1.2)
- `fleet_ctl.launch_round()` 는 `sessions.spawn(SessionSpec(role="manager", …))` 한 줄이 된다. `_relay_worker`·재촉·`.aimem/relay/` 는 없어지고 이어 달리기 감시(`_chain_wait_and_step`)만 남는다

**사람이 도중에 말 걸기.** ACP 는 디스코드 스레드로 관리자에게 말을 걸 수 있었다. 대신 모니터에 "관리자에게 전하기" 를 둔다. 관리자 세션이 끝나 있으면 `claude -p --resume <harness_session_id>` 로 한 턴을 더 돌리고, 돌고 있으면 `.aimem/inbox/M-R<N>.md` 에 적어 둔다(관리자 브리프에 "그래프 한 틱이 끝날 때마다 이 파일을 본다" 를 넣는다). 급하지 않으면 2단계로 미뤄도 된다.

### 3.4 관리자 식별과 위임

지금 관리자의 정체는 세션 키 접두 `agent:claude:acp:` 이고 린터가 이것을 고정한다. 새 식별은 이렇다.

- 관리자 세션 id: `M-R<N>-<HHMMSS>` (예 `M-R21-193012`)
- 엔진이 관리자를 띄울 때 환경변수 `AIFLEET_SESSION=M-R21-193012`, `AIFLEET_ROLE=manager` 를 넣는다
- AIMEM.md 서문: "관리자 = 엔진(`fleet_ctl.py round`)이 띄운 `role=manager` 세션. id 는 `M-R<N>-…`. `sessions` 표에 `running` 인 관리자는 하나뿐이다(엔진이 강제)"
- 린터: `MANAGER_SESSION_KEY` → `MANAGER_SESSION_RE = r"M-R\d+-\d{6}"`

위임문(`~/.claude/CLAUDE.md` 등)의 "관리자 세션이 보내는 지시" 는 작업자 지시문 머리말의 `슬롯·확인토큰·REV` 로 검증하는 지금 방식 그대로다. ACP 가 사라져도 이 검증은 바뀌지 않는다. 위임을 저장소 밖에 두는 원칙도 그대로다.

### 3.5 공급자 문지기

S2(codex)와 S3(opencode)는 둘 다 `kisti/kistillm` 을 쓰고, 그 서버는 요청을 **직렬**로 처리한다. 엔진은 이것을 모른 채 둘을 동시에 띄운다. 문지기는 공급자마다 "동시에 몇 세션까지" 를 지킨다.

```toml
# fleet.toml
[providers.kisti]
base_url = "https://aida.kisti.re.kr:10430/v1"
env_key = "KISTI_API_KEY"
max_concurrent = 1            # 직렬 서버
idle_timeout_sec = 240        # 사건이 이만큼 없으면 멈춘 것으로 본다
probe = "models"              # 준비 점검 때 GET /v1/models

[providers.anthropic]
max_concurrent = 3
idle_timeout_sec = 600
```

- 구현은 DB 한 줄이면 된다: `running` 인 세션을 공급자별로 세고, 넘치면 `queued` 로 둔다
- 그래프 실행기의 `_ready()` 는 "슬롯이 비었나" 에 더해 "공급자 자리가 있나" 를 본다
- 문지기는 **함대 밖 프로세스는 못 본다.** 그래서 고아 청소(3.2-6)가 짝이다

`max_concurrent = 1` 이 정말 옳은지는 재 봐야 한다(7.3). 서버가 2개까지는 느려지지 않는다면 2 가 맞다.

### 3.6 설정 한 곳: `fleet.toml`

지금 슬롯·모델 정보는 네 곳에 흩어져 있다: DB `slots`, `tools/fleet_slots.json`(거울), `~/.openclaw/openclaw.json`(모델 목록), 각 하네스 설정(`~/.codex/config.toml`, `~/.config/opencode/opencode.jsonc`).

- `fleet.toml` 에 `[providers.*]`(3.5)와 `[harness.*]`(바이너리 경로, 기본 인자, 받을 수 있는 공급자)를 둔다
- 슬롯 명부의 정본은 지금처럼 DB `slots`. `fleet_slots.json` 거울은 없앤다
- 모니터의 모델 목록(`/api/models`)은 `fleet.toml` 의 공급자·모델에서 만든다
- 하네스 자체 설정 파일은 하네스의 것이라 그대로 둔다. 다만 `prepare` 가 "슬롯이 가리키는 공급자·모델이 그 하네스 설정에 있는가" 를 점검한다(codex 는 `model_providers.<p>` 와 `model_catalog_json`, opencode 는 `provider.<p>.models`)
- 비밀 키는 `fleet.toml` 에 적지 않는다. 환경변수 이름(`env_key`)만 적고, 값은 `~/.config/ai-fleet/env`(권한 600)에서 읽는다

---

## 4. 지금의 비효율 (실측 근거)

| # | 무엇이 | 근거 | 낭비 |
|---|---|---|---|
| 4.1 | 관리자 기동이 세 단계를 거친다 | R17~R20 전달 2분 5초 ~ 3분 58초. 클로(kistillm)가 지시문을 읽고 스폰하는 시간. R6 에서는 클로가 읽기만 하고 끝내 재촉이 필요했다 | 라운드마다 2~4분 + 실패 경로 하나 |
| 4.2 | 공급자가 멈춰도 엔진이 모른다 | 11-12 19:30 T-263(codex)이 19:35 `Reconnecting… 1/5` 뒤 **37분 침묵**. T-265(opencode)는 `Provider response headers timed out after 300000ms` 로 31분 뒤 실패. 엔진은 노드 타임아웃(기본 30분)까지 기다릴 뿐 | 한 번에 30~45분. 최장 실행 40.1분·45.1분이 이런 경우 |
| 4.3 | 기반 장애가 '작업 실패' 로 세어진다 | 위 T-265 1차는 모델이 답을 못 받은 것인데 시도 1/2 을 썼다. 재시도 28건 중 일부가 이런 경우 | 시도 횟수 소진 → 멀쩡한 태스크가 failed |
| 4.4 | 직렬 서버에 둘을 동시에 보낸다 | S2·S3 가 같은 kistillm. 같이 뜨면 둘 다 느려지고 뒤쪽은 헤더 시간 초과 | 4.2 의 원인 중 하나 |
| 4.5 | 검사가 진짜 하네스를 띄우고 고아로 남긴다 | 11-12 19:18:45 적대적 검수 중 `codex exec … -C /tmp/r20-review` 3묶음이 떴고, 검수가 끝난 뒤에도 49분간 남아 kistillm 연결을 하나씩 잡고 있었다. 직후 4.2 가 났다 | 공급자 줄 점유. 사람이 pid 로 찾아 끝냄 |
| 4.6 | 작업자가 사는지 알 길이 없다 | 세 하네스 모두 끝에 한 번만 출력하는 꼴로 띄운다. `.out` 이 0바이트인 채 수십 분 | 4.2 를 못 잡는 직접 원인. 모니터도 "경과 37분" 만 보인다 |
| 4.7 | 폴링 | 그래프 실행기 15초, 이어 달리기 45초, 관리자 조회 30초 캐시 + 첫 조회 수십 초 | 노드 하나 끝날 때마다 평균 7.5초, 라운드 전환마다 평균 22초. 모니터 관리자 카드가 '조회 중' |
| 4.8 | 보드와 그래프가 따로 논다 | 그래프 노드가 done 이어도 보드(`tasks`)는 관리자가 라운드를 닫을 때까지 TODO. 11-12 '미완료 10' 중 6건이 이미 끝나 있었다 | 화면이 틀린 수를 보임(모니터에서 임시로 가렸다). 이어 달리기의 '남은 일' 판단도 같은 자료를 본다 |
| 4.9 | 관리자가 기다리는 데 유료 토큰을 쓴다 | R20: Opus 세션 2시간 38분, 125단계, 기록 797KB. 대부분은 `fleet_graph.py run` 이 끝나기를 기다렸다가 결과를 읽는 단계 | 라운드가 길수록 관리자 문맥이 커지고 단계마다 그 문맥을 다시 낸다 |
| 4.10 | 관리자가 끊기면 라운드가 마감 없이 남는다 | R16·R18 관리자 `failed`. R20 은 사람이 끊었다. 보고·핸드오프 없이 반쯤 고친 파일이 남는다 | 다음 세션이 사람 손으로 상태를 맞춰야 한다 |

---

## 5. 엔진 수정·튜닝 항목

항목마다 **지금 → 바꿀 것 → 확인 방법**을 적었다. 번호는 4절과 맞췄고 5.11~5.12 는 이름 바꾸기와 마무리다.

### 5.1 관리자 직접 기동 (4.1)
- 지금: `launch_round` → `_relay_worker` → `openclaw agent` → 클로 → `sessions_spawn`
- 바꿀 것: `launch_round` → `sessions.spawn(role="manager")`. `RELAY_TEMPLATE`·`NUDGE_TEMPLATE`·`_relay_worker`·`.aimem/relay/` 삭제. `public_state()` 의 `relay` 칸은 `manager` 칸(세션 id·상태·시작)으로 바꾼다
- 확인: '라운드 실행' 을 누른 뒤 관리자 첫 사건까지 10초 안. `fake` 하네스로 도는 통합 검사 하나

### 5.2 침묵 감지 (4.2, 4.6)
- 지금: 노드 타임아웃(벽시계)만. 출력은 끝에 한 번
- 바꿀 것: 어댑터가 사건 흐름으로 띄우고, 감독기가 `idle_timeout` 을 지킨다. 넘으면 세션을 `stalled` 로 끝내고 `fail_kind="infra"`
- 하네스 쪽 재시도도 줄인다. codex 는 `-c stream_max_retries=1 -c request_max_retries=1` 로 띄워 재접속 5회를 기다리지 않게 하고(키 이름은 쓰기 전에 그 판의 문서로 확인), opencode 는 공급자 `timeout` 을 설정에서 줄인다. **기다리는 것은 엔진 한 곳에서만 한다**
- 확인: `fake` 하네스에 "사건 하나 내고 멈춤" 을 시켜 `idle_timeout` 뒤에 `stalled` 가 되는지

### 5.3 실패의 종류를 가른다 (4.3)
- 지금: 실패는 한 가지. 시도 횟수를 쓴다
- 바꿀 것: `fail_kind` 넷. `work`(보고가 BLOCKED·검증 실패)만 시도를 쓴다. `infra`(침묵·헤더 시간 초과·재접속)는 **시도를 쓰지 않고** 공급자 점검이 통과할 때까지 기다렸다 다시 넣는다(최대 3회, 그 뒤 그래프를 멈추고 사람에게). `limit`(사용 한도)은 지금처럼 라운드를 멈춘다. `timeout`(벽시계)은 시도를 쓴다
- 유료 모델로의 자동 대체는 넣지 않는다(11-10 결정: 장애는 보고만)
- 확인: `fake` 로 infra 실패 2회 뒤 성공 → 시도 1/2 로 done

### 5.4 공급자 문지기 (4.4)
- 3.5 그대로. 그래프의 `concurrency` 는 "슬롯 수" 가 아니라 "공급자 자리 수" 로 정해진다
- 덧붙여 **차례 정하기**: 같은 공급자를 기다리는 노드가 여럿이면 의존이 많이 걸린 노드(다른 노드가 기다리는 것) 먼저
- 확인: kistillm 노드 둘을 가진 그래프에서 둘이 겹쳐 `running` 인 순간이 없는지(`sessions` 표의 시작·끝 구간)

### 5.5 검사에서 진짜 하네스 금지 (4.5)
- 바꿀 것 셋
  1. 검사 실행기(`tests/` 공통 설정)가 `AIFLEET_HARNESS=fake` 를 넣는다. 어댑터 선택 함수는 이 변수가 있으면 무조건 `fake` 를 준다
  2. 진짜 어댑터의 `command()` 는 `cwd` 가 저장소 루트 밖(예 `/tmp/…`)이면 거절한다. 11-12 의 고아는 `-C /tmp/r20-review` 였다
  3. 고아 청소(3.2-6)
- 검수자 브리프에도 한 줄: "변이 시험에서 `fleet.py spawn` 을 부를 때는 `AIFLEET_HARNESS=fake`"
- 확인: 검사 전체를 돌린 뒤 `pgrep -f "codex exec|opencode run|claude -p"` 가 비어 있는지 검사 끝에서 본다

### 5.6 살아 있음을 화면에 (4.6)
- 모니터의 실행 표·관리자 카드에 "마지막 사건 N초 전 · 지금 하는 일(마지막 `tool` 사건 요약)" 을 보인다. 자료는 `sessions.last_event_at` 과 `events.jsonl` 의 끝 줄
- 관리자 상세는 `~/.openclaw/acpx/sessions/` 대신 `.aimem/sessions/M-…/events.jsonl` 을 읽는다. 조회가 파일 읽기라 '조회 중' 과 30초 캐시가 없어진다

### 5.7 폴링을 사건으로 (4.7)
- 그래프 실행기: 세션 종료를 감독기가 즉시 알려 준다(`wait_any(timeout=5)`). 15초 잠자기 대신 "끝난 세션이 있거나 5초가 지나면" 한 틱
- 이어 달리기 감시: 관리자 세션의 종료를 기다린다(45초 폴링 삭제)
- 모니터: 지금처럼 5초 갱신. 서버 쪽은 `openclaw` 호출이 없어져 `/api/state` 가 DB 와 파일만 읽는다

### 5.8 보드와 그래프를 한 자료로 (4.8)
- 바꿀 것: 그래프 노드의 상태가 바뀔 때 감독기 콜백에서 `tasks.status` 를 같이 고친다(`todo→IN-PROGRESS→REVIEW/DONE`, 실패는 `BLOCKED`). 관리자는 라운드를 닫을 때 **판정만** 한다(REVIEW → DONE)
- 모니터의 `boardLive()` 임시 처리(11-12)는 그 뒤 걷어낸다
- AIMEM.md 의 "보드 쓰기는 관리자만" 규칙과 닿는다. 엔진이 관리자의 손으로서 쓰는 것으로 규칙을 고쳐야 한다(**AIMEM.md 쓰기, 태석님 허용 필요**)

### 5.9 관리자를 짧게 여러 번 (4.9)
지금은 관리자 하나가 라운드 내내 산다. 그래프를 돌리는 일은 판단이 아니라 기계 일이므로 엔진이 맡고, 관리자는 **판단이 필요한 세 곳**에서만 뜬다.

| 호출 | 입력 | 내는 것 |
|---|---|---|
| ① 계획 | 열린 요청, 대기 큐, 최근 핸드오프 2건 | 그래프 정의(JSON)와 노드별 브리프 |
| ② 판정 | 끝난 그래프의 보고·검증 결과·검수 보고서 | 닫을 것 / 다시 할 것(후속 그래프) / 큐로 보낼 것 |
| ③ 마감 | 라운드 전체 결과 | 라운드 보고, 핸드오프, 보드 판정 |

- ①과 ② 사이에서 엔진이 그래프를 돈다. 그동안 유료 세션은 없다
- 세 호출은 같은 하네스 세션을 `--resume` 으로 이어도 되고(문맥 유지), 새 세션으로 띄워도 된다(문맥 최소). **먼저 새 세션으로 해 보고**, 판단 품질이 떨어지면 이어 쓰기로 바꾼다
- 그래프가 중간에 막히면(노드 failed·infra 3회) 엔진이 ②를 앞당겨 부른다
- 이 항목이 가장 큰 변경이다. 5.1~5.8 이 자리 잡은 뒤 3단계로 한다(6절)
- 확인: 같은 요청 묶음을 지금 방식과 새 방식으로 한 번씩 돌려 관리자 토큰·벽시계·결과(검사 통과 수)를 견준다

### 5.10 끊겨도 마감이 남게 (4.10)
- 감독기는 관리자 세션이 `done` 이 아닌 상태로 끝나면(`failed`·`killed`·`timeout`) **엔진이** 최소 마감을 적는다: `rounds/R<N>/REPORT.md` 에 "관리자 없이 끝남 · 그래프 상태 · 미완 노드 · 손댄 파일(`git status`)" 과 핸드오프 한 건
- 5.9 가 들어가면 ③ 호출이 실패해도 ①②의 산출물은 DB 에 있으므로 다음 라운드가 이어받는다
- `stop` 은 지금 작업자와 그래프 실행기만 끝낸다. 관리자 세션도 같이 끝내고 위 최소 마감을 쓴다(11-12 에는 관리자와 전달자를 손으로 따로 끊어야 했다)

### 5.11 폴더 이름 바꾸기: `opencode` → `ai-fleet`
엔진 코드는 `ROOT = Path(__file__).resolve().parent.parent` 로 자기 위치를 구하므로 이름이 바뀌어도 돈다. 절대 경로가 박힌 곳만 고치면 된다.

| 어디 | 고칠 것 |
|---|---|
| `~/.claude/settings.json` `statusLine.command` | `/home/tsyi/work/ai-fleet/tools/claude_usage_statusline.py` |
| `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md` | 위임문의 `~/work/opencode` (세 파일, 각 3~4곳) |
| `AIMEM.md` 3행·526행, `tools/claude_usage_statusline.py` 10행 | 경로 글자 (**AIMEM.md 는 태석님 허용 필요**) |
| `.aimem/briefs/manager-round-standard.md` | 경로 글자 |
| `~/.openclaw/openclaw.json`, `~/.openclaw/workspace-coding/AGENTS.md` | 5.1 뒤에는 함대 항목을 통째로 지운다. 그 전에 이름만 바꾸면 클로 전달이 끊긴다 |
| 클로드 코드 프로젝트 기억 | `~/.claude/projects/-home-tsyi-work-opencode/` 는 새 경로에서 안 읽힌다. 필요한 기억은 `-home-tsyi-work-ai-fleet/` 로 옮긴다 |
| 운영 모니터 | 옛 경로에서 뜬 프로세스다. 이름을 바꾸기 전에 끄고 새 경로에서 다시 띄운다. 윈도우 프록시(18800→18799)는 포트만 보므로 그대로 |
| 깃 원격 | `acp-collab-harness` 라는 저장소 이름은 내용과 안 맞게 된다. 바꿀지는 태석님 결정 |

옛 `rounds/R*/brief.md`·`.aimem/archive/` 안의 옛 경로는 기록이므로 고치지 않는다.

**2026-11-12 20:36 에 (가)로 했다.**

- 한 것: 모니터를 내리고 `mv` → 새 경로에서 다시 띄움(https, 18799). `~/.claude/settings.json` 상태줄, 위임문 셋(`~/.claude/CLAUDE.md`·`~/.codex/AGENTS.md`·`~/.config/opencode/AGENTS.md`, 경로만), `~/.codex/config.toml` 의 신뢰 폴더, `~/.openclaw/openclaw.json` 6곳과 `~/.openclaw/workspace-coding/AGENTS.md` 2곳(옛 폴더가 다시 생기지 않게 경로만), `tools/claude_usage_statusline.py`·표준 브리프의 경로 글자. 고친 파일마다 옆에 `.bak-20261112-rename`
- 클로드 코드 기억: `~/.claude/projects/-home-tsyi-work-ai-fleet/memory/` 에 함대 관련 37건을 옮겨 두었다
- **남은 것**: `AIMEM.md` 3행·526행의 옛 경로(쓰기 허용 필요), 오픈클로 게이트웨이는 다시 띄워야 새 경로를 읽는다(지금은 옛 경로를 기억한 채 돈다 - 라운드를 돌리지 않으므로 지장 없음), 깃 원격 이름
- 지금 엔진(클로 전달)으로는 **라운드를 돌리지 말 것.** 2단계가 끝날 때까지 함대는 멈춘 채 둔다

**순서가 중요했다.** 이름을 먼저 바꾸면 지금 엔진(클로 전달)이 깨진다. 함대는 지금 멈춰 있으므로 (가) 이름을 먼저 바꾸고 1단계가 끝날 때까지 라운드를 돌리지 않거나, (나) 1단계를 끝낸 뒤 이름을 바꾼다. 권하는 것은 (가)다. 새 코드를 처음부터 새 경로에서 짠다.

### 5.12 걷어낼 것
새 체제가 들어가면 아래는 필요 없다.
- `fleet.py` 의 `cmd_children`, `cmd_brief` 의 스폰 호출문, `cmd_close` 의 게이트웨이 점검
- `fleet_ctl.py` 의 전달·재촉 일체, `_SESS_CACHE`
- `server.py` 의 `openclaw_models`, `ACPX_SESSIONS`, `OPENCLAW_ENV_FILE`
- `tools/fleet_slots.json`
- 하네스 사정을 엔진 본문에 적어 둔 분기들(`_worker_argv` 의 codex/opencode/claude 세 갈래, opencode 전용 머리말 주입)은 어댑터 안으로 들어간다

---

## 6. 이행 단계

함대는 지금 멈춰 있다(11-12 20:13 완전 중지, R20 은 마감 없이 끊김). 엔진을 고치는 동안에는 라운드를 돌리지 않는다. **엔진 수정은 함대 작업자에게 맡기지 않는다** — 고치는 대상이 자기를 띄우는 장치이기 때문이다. 클로드 코드가 태석님과 직접 한다.

| 단계 | 내용 | 끝났다고 보는 기준 | 되돌리기 |
|---|---|---|---|
| 0 | 정리: R20 미완 변경(20개 파일)을 검사 돌려 확정하거나 되돌림 → 커밋. ~~폴더 이름 바꾸기(5.11)~~ 11-12 완료 | 검사 전부 초록, 작업 트리 깨끗, 새 경로에서 모니터 뜸 | `mv` 되돌리기 |
| 1 | 런타임: `tools/fleet/` 패키지(어댑터 넷 + 감독기 + `sessions` 표). 작업자 띄우기를 감독기로 옮김. `runs` 는 뷰 | 기존 검사 초록 + `fake` 통합 검사. 진짜 작업자 한 명씩(S2·S3·S4) 손으로 띄워 사건 흐름·침묵 감지·끝내기 확인 | 커밋 하나로 묶어 되돌림 |
| 2 | openclaw 떼기: 5.1 관리자 직접 기동, 5.6 모니터, 5.12, 2절 표 1~14. `fleet.toml` | `grep -ri "openclaw\|acp" tools/` 가 비어 있음. `PATH` 에서 openclaw 를 뺀 셸에서 `prepare` 통과와 라운드 한 번 완주 | 단계 1 커밋으로 |
| 3 | 튜닝: 5.2~5.4, 5.7, 5.8, 5.10 | 4절 표의 항목마다 확인 방법 통과. 같은 요청 묶음으로 벽시계를 지금과 견줌 | 항목별 커밋 |
| 4 | 관리자 세 번 호출(5.9) | 견줌 라운드에서 관리자 토큰이 줄고 결과가 같거나 나음 | 설정 한 줄로 옛 방식(상주)으로 |
| 5 | 뒷정리: `~/.openclaw` 쪽 함대 흔적(2절 아래 표), AIMEM.md 서문·8.0, 위임문, README | 오픈클로 `doctor` 에 함대 관련 항목 없음 | — |

단계 2 의 "openclaw 를 뺀 셸에서 완주" 가 **의존성을 완전히 없앴다는 증명**이다.

---

## 7. 검증·위험·미결정

### 7.1 검증
- 단위: 어댑터마다 `command()` 가 내는 argv 를 고정 자료와 견준다. `parse_event()` 는 하네스에서 실제로 받은 출력 표본(하네스마다 정상·재접속·한도·도구 호출)을 `tests/fixtures/` 에 두고 돌린다
- 통합: `fake` 하네스로 그래프 한 벌(성공·work 실패 후 재시도·infra 실패·침묵·완전 중지·고아 청소)
- 실물: 단계마다 진짜 하네스로 손 검사. 자동 검사에 넣지 않는다(5.5)
- 화면: 11-12 에 만든 캡처 도구(읽기 전용 사본 서버 + 폭 22종)로 모니터를 다시 찍는다

### 7.2 위험
| 위험 | 대비 |
|---|---|
| 하네스 판이 바뀌어 사건 꼴이 달라진다 | `probe()` 가 버전을 적고, 모르는 사건은 버리지 않고 `raw` 로 남긴다. 어댑터가 모르는 판이면 `prepare` 가 경고 |
| 관리자 도구 목록이 좁아 관리자가 막힌다 | 단계 2 에서 한 라운드를 지켜보며 막힌 명령을 목록에 더한다. 막힘은 `events.jsonl` 의 권한 거절로 보인다 |
| codex 를 `--ephemeral` 없이 띄우면 세션 파일이 쌓인다 | 작업자는 지금처럼 `--ephemeral`. 이어 말하기가 필요한 것은 관리자(claude)뿐 |
| `idle_timeout` 이 짧아 오래 생각하는 모델을 죽인다 | 공급자마다 따로 정하고, 처음에는 넉넉히(kistillm 240초, anthropic 600초) 두고 `sessions` 의 사건 간격 분포를 보고 줄인다 |
| 관리자를 직접 띄우면 사용 한도 정보를 못 본다 | 어댑터가 `stream-json` 의 한도·오류 사건을 `limit_signal` 로 올린다. 상태줄 파일(`.aimem/claude-usage.json`)은 대화형 세션에서만 갱신되므로 보조로만 쓴다 |

### 7.3 정해야 할 것
1. ~~이름 바꾸기 시점~~ — 11-12 에 (가)로 했다 (5.11)
2. **R20 미완 변경** — 검사 돌려 살릴지, 되돌릴지. 화면 개선분(`static/` 5개 파일 + `tests/browser_monitor_ui.py`)과 R20 작업자 수정이 한 트리에 섞여 있다
3. **AIMEM.md 고쳐 쓰기 허용** — 서문·8.0(관리자 정의), 보드 쓰기 규칙(5.8), 경로(5.11)
4. **kistillm 동시 처리 수** — 1 이 맞는지. 같은 프롬프트를 1개·2개·3개 동시에 보내 응답 시간을 재면 정해진다(무료 서버라 비용 없음)
5. **사람이 관리자에게 말 걸기** — 2단계에 넣을지 미룰지(3.3)
6. **관리자 하네스** — 설계는 claude(Opus) 그대로다. 어댑터 구조상 다른 하네스도 관리자가 될 수 있지만 권하지 않는다(11-06 관찰: kistillm 은 맥락 추론·되묻기가 약하다)
7. **깃 저장소 이름** — `acp-collab-harness` 를 바꿀지

---

## 부록 A. 지금 코드에서 그대로 쓰는 것

새로 짜는 것은 어댑터·감독기·문지기·설정 읽기뿐이다. 아래는 손대지 않거나 호출만 바꾼다.

- `fleet_graph.py` 의 그래프 모델·검증(`validate_graph`)·준비 노드 고르기(`_ready`)·보고 판정(`report_block_reason`, `report_limit_hit`)·라운드 상한(`round_budget_problem`)
- `fleet_ctl.py` 의 함대 모드(준비/실행/일시 중지/완전 중지)·이어 달리기 판단(`chain_decide`)
- `aimem_db.py`, `aimem_board.py`, `aimem_lint.py` (린터는 관리자 식별자 한 줄만)
- 소유 경로 검사(`owned_paths`, `path_allowed`), 지시문 머리말(슬롯·확인토큰·REV)
- 모니터 전체(관리자 카드·모델 목록의 자료 출처만 바뀐다)

## 부록 B. 세션 폴더

```
.aimem/sessions/<id>/
  meta.json        명령·env 이름(값 없음)·pid·pgid·시작/끝·하네스 판
  brief.md         받은 지시문 (지금 .aimem/runs/<id>.brief.md)
  events.jsonl     하네스가 낸 사건 원문 한 줄씩 (감독기가 받은 시각을 앞에 붙임)
  stderr.log
  report.md        final_report() 가 뽑은 마지막 답
  rc               종료코드
```

지금 `.aimem/runs/<id>.{brief.md,out,err,rc,json}` 다섯 파일이 폴더 하나로 모인다. 아카이브(`archive/runs-<월>/`)는 폴더째 옮긴다.

## 부록 C. 이번 조사에서 본 것 (11-12)

- 19:18:45 고아 codex 3묶음 발생 → 19:30 부터 T-263·T-265 무응답 → 20:09 고아 종료 → 20:13 함대 완전 중지 → 20:16 관리자 세션 중단(`sessions.abort`) → 20:17 전달자 세션 중단
- `stop` 이 관리자를 끝내지 않아 손으로 두 번 더 끊어야 했다(5.10)
- 고아 종료 뒤 kistillm 이 풀렸는지는 확인하지 못했다(지켜보던 중 중단 지시). 4.5 와 4.2 의 인과는 시각이 맞을 뿐 확증이 아니다
