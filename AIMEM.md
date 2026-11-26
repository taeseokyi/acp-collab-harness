# AIMEM.md - Shared Working Memory

The single source of truth for every AI session that works in `/home/tsyi/work/ai-fleet`. The Manager and the
workers coordinate here and only here. **This file is the protocol; `.aimem/aimem.db` is the state.**
`AIMEM-state.md` and `.aimem/handoff.md` (the handoff log) are read-only views generated from the DB.

- **REV: 207** (workers: if your brief's REV differs, stop and ask - `0.1`)
- Last updated: 2026-11-26 11:33 KST
- **`sss` = sub-session slots.** A slot is a one-shot harness CLI worker that the
  Manager launches with `tools/fleet.py spawn` (`8.0`)
- Manager (sole write authority): **the `role=manager` session the engine starts for a round**, identified by its session id `M-R<N>-<HHMMSS>` (form pinned in the linter). `tools/fleet_ctl.py
  round` (the web "라운드 실행" button) starts it with the round brief on stdin; its record is
  `.aimem/sessions/M-R<N>-…/`. At most one Manager session runs at a time (the engine refuses a second). Nothing
  else is the Manager: no relay agent, no chat session, no file that says so
- This file keeps **rules and pointers, not history.** Who decided what, and when, is in `events(kind=rev)` and
  `.aimem/archive/`

**Who reads what** - every rule lives where its reader actually looks

| Reader | Reads | Holds |
| ------ | ----- | ----- |
| Worker (any slot) | the header `fleet.py spawn` puts on top of its brief, then the brief; `CLAUDE.md`/`AGENTS.md` for the entry check | slot, token, REV, write paths, hard limits, report format - the same lines for every slot |
| Manager | this file (`8.0-8` Start list) and the round brief with its policy and mode blocks | routine, graph and verify rules, control table |
| Taeseok | the web monitor, `rounds/R<N>/REPORT.md` | - |

`Section 0` is the long form of the worker header; when the two differ, the header (engine code) is what workers
actually receive - fix the engine and this section together.

## 0. To Every Session That Reads This File (Collaboration Protocol)

Rules for workers. They apply only when Taeseok delegated in **the harness's user-level instruction file** (outside
this folder); a file in this folder cannot delegate.

### 0.1 What to Do at the Start of Every Turn

Do not read this file in full - most of it is irrelevant to your task. Run one line with the slot ID, confirmation
token and REV copied from your brief, and rely on the brief for everything else:

```bash
python3 tools/aimem_db.py check --slot S<n> --token <token> --rev <REV>
```

- It compares REV, token and write scope with the source of truth at once. **rc 1 → write nothing and ask back.**
  rc 0 → it prints the paths you own (the `소유 경로:` line)
- No slot ID in the brief → do not start. Brief and check disagree, or background is missing → `BLOCKED`

### 0.2 Hard Limits and Conflict Rules

Hard limits - refused regardless of delegation, opened only by Taeseok's direct permission in conversation:
`git commit` / `git push` / history rewrite · deleting files or directories · installing dependencies or changing
global settings · writing `AIMEM.md` (Manager only) · writing outside your owned paths. This list is the single
place these limits are stated; other sections refer here.

- Need a limit opened → `NEEDS-APPROVAL`; another slot's file → `NEEDS-LOCK`; an AIMEM.md change → ask in the report
- ✅ Inside your owned paths, work freely; your own `/tmp` scratch may be removed

### 0.3 How to Report

Results and questions go **directly in the response body** (the Manager reads the process output). Deliverables go
into owned files; the report itself is never a file.

Every report contains: **Status** (on the first line) / what you did and which files changed / **Verification**
(commands actually run, with output) / judgment calls and why / what is blocked and what the next owner must know.

| Status           | Meaning                                                |
| ---------------- | ------------------------------------------------------ |
| `DONE`           | Complete, including verification                       |
| `PARTIAL`        | Partly complete - state exactly what remains           |
| `BLOCKED`        | Stuck - state what is needed                           |
| `NEEDS-LOCK`     | Another slot's file is required - state the path       |
| `NEEDS-APPROVAL` | A hard limit (`0.2`) must be opened                    |
| `NEEDS-FIX`      | Your checks found a product defect - state what and where; change neither product nor checks |
| `REJECT`         | The instruction itself should not be carried out (out of scope, unsafe) - say why |

Attach verification; do not assert it - the Manager re-runs the same command. Asking back is not a failure.

## 1. Current Goal

- **Goal:** **the fleet turns web requests into finished projects.** A request names a project; rounds
  accumulate its deliverables in `projects/<project>/`; the project is done when every item of the goal checklist
  in its `PROGRESS.md` is checked with evidence. Requests without a project are work on the fleet itself
- **Definition of done (per project):** all goals checked; each check backed by a test or a measured result the
  Manager reproduced; `PROGRESS.md` says what is left ("none" when nothing is)
- **Out of scope:** dependencies (standard library only), front-end frameworks, fonts, CDNs for the fleet's own code

## 2. Session Roster

> **Source of truth: `.aimem/aimem.db`.** Read `2. 세션 명부` in the snapshot **`AIMEM-state.md`** (generated by
> `python3 tools/aimem_db.py render`; never edited by hand). Live: `aimem_db.py slot list`, `fleet.py status`.

Slot ID + confirmation token identify a slot; tokens change with the roster, and a brief with an old token is
refused by the check. A slot's model is DB `slots.model` (empty → the harness default in `fleet.toml`).

## 3. Task Board

> **Source of truth: `.aimem/aimem.db`.** Read `3. 작업 보드` in **`AIMEM-state.md`**.

```bash
python3 tools/aimem_db.py task list
python3 tools/aimem_db.py task set --id T-069 --slot S<n> --status DONE  # Manager only
```

Status values: `TODO` / `ASSIGNED` / `IN-PROGRESS` / `REVIEW` / `DONE` / `BLOCKED`. The graph runner moves a task
with its node - `IN-PROGRESS` when it starts, `REVIEW` when it finishes, `BLOCKED` when it fails - as the Manager's
hand, not a second writer. **`DONE` is the Manager's verdict; the runner never sets or overwrites it.** Finished rows
stay in the DB until archived (`Section 6`, Archive Lifecycle).

## 4. Handoff Log

> **Source of truth: `events(kind=handoff)` in `.aimem/aimem.db`.** `.aimem/handoff.md` (latest entries) and
> **`AIMEM-state.md`** are generated views. This section states only the method.

One entry per round close or commit: what was done, what changed, what remains. The next Manager reads the latest
first.

```bash
python3 tools/aimem_db.py handoff list --last 2        # read at round start (`--all` for everything)
python3 tools/aimem_db.py handoff add --bump --expect-rev N --actor "Manager (R8)" --body "**REV N+1. <title>.** <what changed>"
```

- `add` inserts one row and regenerates `.aimem/handoff.md` in one DB transaction; `--bump` raises the REV in the
  same transaction (run `render` afterwards for the other snapshots); `--expect-rev N` refuses when another session
  raised the REV meanwhile. The log says **what changed**; history goes to the archive. Length cap: `Section 5`
- `.aimem/handoff.md` is never edited - the next `add` or `render` overwrites it. Entries that leave the window are
  exported to the archive and stay in the DB. "Record it in `Section 4`" means `handoff add`; entries written into
  this file are a linter violation (`HANDOFF_IN_AIMEM`)

## 4.5 Waiting Queue

> **Source of truth: `.aimem/aimem.db`.** Read `4.5 대기 큐` in **`AIMEM-state.md`**.

```bash
python3 tools/aimem_db.py queue list | add --task "..." --slot-hint S1 | edit --pos 2 --task "..." | drop --pos 3   # Manager only
```

**What it is:** follow-up work that came out of handling requests - mostly review findings and "next time" items.
New web requests (`NEW`) come first each round; then the queue, top down. The web shows it as `대기 큐 · 후속 일`
(columns: 할 일 / 추천 슬롯 / 출처 태스크).
- **Finding IDs carry their round:** `R17-N5`, `R17-N5·N6`, `R19-P2` - never bare `N5`. Review reports number
  findings from 1 in every report,
  so a bare ID is ambiguous across rounds. `queue add/edit` refuses any bare `<1-2 capital letters><digits>` except
  a round (`R17`) or a slot (`S1`-`S9`)
- **Refer to an item by its finding ID or text, not its position:** positions are renumbered after every `drop`
- **Every item starts with its owner:** `[<project name>]` (the folder name under `projects/`, as is) for a project's
  work, `[함대]` for the fleet's own. A project's items are that project's remaining work - a chain run on the project
  does not end while they are left, and files them as that project's request. No tag, or a name with no folder,
  counts as the fleet's

The Manager takes the next task from the top (`8.0-4`). When the queue is empty it reports a summary and stops; it
never invents items.

## 5. Shared Decisions and Constraints

- **Protocol here, state in the DB.** `Section 6` or `Section 3` means that DB table. `AIMEM-state.md` is generated

**Size caps** - the cost every reader pays, and the line past which the Manager loses control. Stated here only:

| Cap | Value | Enforced by |
| --- | ----- | ----------- |
| AIMEM.md total lines | **800** | linter `SIZE_TOTAL_LINES`, pre-commit hook. The linter also notes when dates or REV citations pile up (history creeping back) |
| Handoff entries shown in `.aimem/handoff.md` | latest **12** | generated from the DB; older entries are exported to the archive automatically |
| Characters per handoff entry | **1,200** | `handoff add` refuses (`--allow-long` overrides) |

## 6. File Ownership

> **Source of truth: `.aimem/aimem.db`.** Read `6. 파일 소유권` in **`AIMEM-state.md`**.

Only the owning slot writes; everyone reads. `fleet.py spawn --write <path>` checks this table and refuses to launch
when the path is not owned. Owner values: a slot ID / `관리자` (Manager) / `미배정` (unassigned). Need a new path →
`NEEDS-LOCK`; work starts after registration.

```bash
python3 tools/aimem_db.py check --slot S<n> --token <token>            # my paths (worker)
python3 tools/aimem_db.py ownership list | set --path tests/x.py --owner S<n>   # set: Manager only, per 6.1
```

### 6.1 When Changing This Table (the Manager Binds Itself)

The delegation refers to this table for write scope, so editing it moves worker permissions without touching the
delegated wording - and the worker's check cannot see that. Therefore: **widening an existing slot's row** (adding
paths, widening a pattern, changing the owner) needs Taeseok's approval; **adding Manager-owned or unassigned rows**,
rows for a slot the Manager added, the owner change made by `fleet_graph.py move`, and formatting may be done alone.
Every change is recorded in the handoff log.

### Archive Lifecycle

**Move, never delete.** Past history is not re-read every turn, but throwing it away makes the next person step on
the same trap. Only the Manager writes the archive. Always archive first, verify the copy, then remove from the
body, and leave a pointer in the body.

- Handoff log → `.aimem/archive/handoff-YYYY-MM.md` (automatic, `Section 4`)
- Retired or compressed sections → `.aimem/archive/retired-sections-YYYY-MM.md` (or a full-text snapshot such as
  `AIMEM-rev129-full.md`), in the same REV that removes them
- Finished tasks, closed requests, finished graphs → `python3 tools/aimem_db.py archive [--days 14] [--dry-run]`
  after 14 days, inclusive cutoff (tasks → `board-<YYYY-MM>.md`, requests → `requests-<YYYY-MM>/`, graphs with their
  files → `graph-<YYYY-MM>/`; old session folders too; round records `rounds/R<N>/` → `rounds-<YYYY-MM>/`, except
  the highest round and rounds still in use). It also drops ownership rows of projects whose folder is gone. Run by
  the Manager at round close and by Taeseok from the web ("끝난 것 정리…")
- A removed project's folder → `.aimem/archive/projects-<YYYY-MM>/<name>-<time>/` (not in git; `Section 8` table)
This list is deliberately not a table - the linter would read a table in `Section 6` as a leftover state table.

## 7. Known Limits

- **Writes are not technically blocked.** Ownership and hard limits are voluntary; the engine checks `--write`
  against `Section 6` at spawn; only `verify` runs confined (`8.0-8`)
- **A worker's or the Manager's own "fixed" is unreliable** - the Manager reproduces verification, and Manager code
  is cross-reviewed like any other
- **Unexplained changes: suspect yourself first.** Code files have no write lock - the last writer wins

## 8. sss Slot Operations (Manager Only)

Taeseok delegated spawning, retrying, slot roles and extra slots within the round's operating policy to the
Manager; standing slots' harness and model stay his (control table, `8.0-8`). Anything needing his approval goes in
the round report, together.

### 8.0 Top-Level Rule - Engine-Started Manager + Harness CLI Workers

**This section wins over the rest of Section 8.**

- **Manager:** a session the engine starts per round. It is blank every round, so **this file is its memory** - it
  starts with the `8.0-8` Start list. Its tools exclude commit, push, delete, install, killing processes and
  restarting the monitor
- **Workers:** one-shot CLI processes, normally launched through a graph (`8.0-5`); by hand:

  ```
  python3 tools/fleet.py spawn --slot S<n> --label "T-041 tests" --write tests/test_x.py --task-file brief.md
  python3 tools/fleet.py runs | wait [<id>...] | report <id>
  ```

  `spawn` prepends the header and checks `--write` against `Section 6`. Records: `.aimem/sessions/<id>/`.
  One brief in, one report out; workers do not talk to each other
- **Slots and models:** `aimem_db.py slot list` is the source of truth. Taeseok sets the standing slots; **the
  Manager may set any slot's role and add slots within the round's operating policy** (`8.0-8` control table)
- **The engine already does this - never repeat it by hand:** reads the status from the first report line; moves
  board status with its node; retries a failed node (`max_attempts` 2) with the previous verify tail and report;
  re-queues infrastructure failures and blocks the node after 3 of them or 10 minutes of provider silence; ends
  silent workers; fails an attempt that did nothing (`aborted`, `no-report`, `no-op`)
- **Ownership binds the Manager too:** never edit a file a worker is writing. **A node's `verify` is scoped to its
  own deliverables** - the full suite runs only at round close

#### 8.0-1 Slots Are Narrow; Only the Manager Sees the Whole

- One local task per slot: "change this function in this file this way; verify with this command"
- **Briefs are self-contained:** path, current behavior, expected behavior, verification command, completion
  criterion - and **what not to read**. Quote the needed passage instead of "read AIMEM and decide"
- The slot that built it never verifies it

#### 8.0-2 Decision and Execution Are Separate

Design and progress are the Manager's; split judgment goes to Taeseok. A slot asked for a design decision has a
defective brief; `BLOCKED` is the right answer.

#### 8.0-3 Parallel Dispatch

Dependent tasks wait for their predecessor; never two slots on one file. One worker per slot, within each
provider's `max_concurrent` (`fleet.toml`). The biggest lever is **prompt length** - short briefs, narrow write
scope.

#### 8.0-3-1 Terminology and Identifiers

| Layer | Meaning | Format | Example | Created by |
| ----- | ------- | ------ | ------- | ---------- |
| Request | One thing Taeseok wants | `Q-<YYMMDD>-<4 chars>` | `Q-261109-8d8d` | web `POST /api/requests` |
| Task | A unit split from a request = one board row | `T-<n>` | `T-050` | Manager |
| Graph | A DAG of tasks scheduled together | `G-<nnn>` | `G-003` | Manager (`fleet_graph.py new`) |
| Run | One worker process; new per retry | `<T>-<S#>-a<attempt>-<HHMMSS>` | `T-050-S1-a2-174829` | `fleet.py spawn` |
| Round | One `라운드 실행` launch = one Manager session | `R<N>` | `R3` | `fleet_ctl.py round` / web |

Node id = task id. Round notation appears in `rounds/R<N>/`, session ids (`M-R<N>-…`) and finding ids (`R17-N5`).
Ad-hoc runs without a task are `ADHOC-<S#>-a1-<HHMMSS>`. Old identifiers in history are not corrected.

#### 8.0-4 Progress Rules - The Non-Stop Loop (Manager only)

1. On a report, **verify first**: run the deliverable, compare `git status` with reality, reproduce the claimed
   verification. Never trust the report
2. On pass, **without asking**: close `REVIEW` → `DONE` and take the next queue item. Pre-approval covers only this
   folder and `Section 6` paths
3. **Stop and ask** on anything outside this folder or behind a hard limit (`0.2`). A blocked or twice-failed node
   is handled by the operating policy (report it, or `fleet_graph.py move` it to another slot)
4. Empty queue → one summary report, then stop. Never invent tasks

#### 8.0-5 Loop and Graph Engineering (`tools/fleet_graph.py`)

Everything goes through `fleet.py spawn`, so header, token, REV and ownership checks still apply. `validate` catches
cycles, unknown slots and unowned paths before any spawn; a cleared dependency starts the next node at the next tick
(2 s); a node is done when `rc==0 && verify_rc==0`.

```
python3 tools/fleet_graph.py new --id G-<nnn> --request "<one line>" --nodes .aimem/graph/inputs/G-<nnn>-nodes.json
python3 tools/fleet_graph.py validate G-<nnn>
python3 tools/fleet_graph.py run G-<nnn> --timeout 570          # foreground; repeat while rc 1 and nodes still run
python3 tools/fleet_graph.py status G-<nnn>
python3 tools/fleet_graph.py move G-<nnn> T-<n> --slot S<n>      # within the operating policy
python3 tools/fleet_graph.py unblock G-<nnn> T-<n> [--reverify]  # after checking a blocked/failed node
```

- **`run` stays in the foreground** - the Manager's shell tool caps one command at 10 minutes, hence
  `--timeout 570` and the repeat. rc: **0** all done · **1** not finished,
  or a node failed or blocked (under `quality`/`speed` it returns as soon as a node blocks, so the Manager can move
  or unblock) · **2** validation or lock · **3** fleet stopped · **4** the human left a message in
  `rounds/R<N>/INBOX.md`
- Node inputs go in `.aimem/graph/inputs/` (the server parses `.aimem/graph/*.json` as graphs; `.aimem/graph/` is
  ignored by git). Limits: no editing while running (stop → edit → `validate` → relaunch); coarse estimates

#### 8.0-6 The Manager Finishes Within the Turn

When the turn ends the Manager never wakes. Wait in the foreground; the turn ends only after the full report is in
the response body. If a turn may be cut, write progress with `aimem_db.py event` and report `PARTIAL`.

#### 8.0-8 Manager Round Routine and Control

The standing routine every round brief points to; briefs list only what is specific to running the round. **This
subsection is canonical for graph and verify rules.**

**Talking to a running round:** `fleet_ctl.py tell "…"` appends to `rounds/R<N>/INBOX.md`. The Manager reads it at
start, before making a graph and at every checkpoint; `fleet_graph.py run` returns rc 4 when it changes. Within a
request, the human's message wins over the request text.

**Round content, projects, records.** A round is launched with `fleet_ctl.py round [--policy cost|quality|speed]` or
from the web (`라운드 실행`). Without a round-specific brief (`.aimem/briefs/manager-round<N>-<date>.md`) the standard
brief `.aimem/briefs/manager-round-standard.md` is used and **the round's tasks are the `NEW` requests**; with
nothing to do the Manager reports and ends.
- **A project spans rounds.** Each request names a project (empty = the fleet's own code, changed in place).
  Deliverables accumulate in **`projects/<project>/`** - edited in place, no per-round copies. Its `PROGRESS.md` is
  the project's memory: the goal checklist `## 목표` on top (the web progress is done/total of it), then `## R<N>`
  entries, newest first. A new project gets a `README.md`. Assign paths with `aimem_db.py ownership set` before a
  worker writes. The brief says how to keep these
- **A round folder holds records only:** `rounds/R<N>/brief.md` (as sent), `round.json` (written by the launcher;
  `task set --request` / `request set` add to it), `INBOX.md`, `REPORT.md`. No deliverables there; other rounds'
  folders are not touched. Identifiers (`8.0-3-1`) never get a project or round prefix

**Start** (a new session is blank) - the one list of what the Manager reads
1. `fleet_ctl.py status` · `fleet.py status` · `aimem_db.py queue list` · `request list` · `slot list` ·
   `fleet.py runs --last 10` · `aimem_db.py handoff list --last 2` · `rounds/R<N>/INBOX.md` · the `PROGRESS.md` of
   each open request's project, then this header and `8.0`.
2. **Roster:** slots with role `(미배정 - 관리자가 다음 라운드에 정함)` or `events(kind=slot)` → set role and remark
   with `aimem_db.py slot set --slot S<n> --role "…" --note "…"`. Adding slots: within the operating policy
3. **NEW requests:** within scope and caps → split into subtasks → `PLANNED` → graph. **Caps are enforced by
   `fleet_graph.py new`:** new work stops at 3 graphs and 10 tasks per round; a graph that fixes review findings or
   re-reviews those fixes passes with `--followup "<what it follows>"` up to 6 graphs and 18 tasks. Never skip the
   re-review to stay under the cap. Otherwise `PLANNED` + "next round", mentioned in report item (5). A notification
   request from `슬롯 관리(웹)` is confirm → assign role → `DONE`. Mid-round arrivals are judged the same way at every
   checkpoint

**Graph and verify rules**
- **Slot use follows the round's operating policy** (chosen at launch; default `fleet.toml` `[policy] default`).
  Its text (`.aimem/briefs/policy-<key>.md`), with the live slot roster and the slot allowance filled in, follows
  the brief; each project's mode block follows it. The policy divides slots; the mode decides how much is reviewed
  and tested
- **One graph per round by principle,** with every task and its `deps`; a second graph only when the first one's
  results must change the plan. Reviews are nodes inside the graph; the Manager checks once after it ends
- **Parallel graphs:** a `deps` edge only where a node reads another's output. Fix the interface (file and function
  names, input/output shapes) first and put it in each brief, so logic, UI, styles and tests (written against the
  interface, not the implementation) can sit side by side;
  spread one level over different slots; reviews go last.
  `fleet_graph.py new` prints the graph's shape and notes a single-file chain or a crowded slot
- **Small nodes:** one new file, about 200 lines, about 10 checks. Split larger work; split a file two slots
  would both write. Do not tell a worker to "plan first" - have it edit files right away. Workers can run a browser
  and local TCP servers
- **`verify` is ONE check command judged by its exit code** - e.g. `python3 -m unittest tests.test_x`,
  `python3 tests/browser_x.py`. Do not redirect or filter its output: the engine keeps the output
  tail and passes it to the retry. A node that writes checks is verified by "its checks ran" (it may add one count
  assertion), not "the product passed"; a product defect is reported `NEEDS-FIX` (`0.3`) and fixed by a later node.
  Fix and re-verify nodes require all checks to pass. Have check scripts print the failure cause in their last
  lines. Run the command on the current tree once before using it (the Manager's tools run `python3 -m unittest …`,
  `python3 tests/<file>.py` and `python3 tools/check.py`)
- **`verify` runs confined** (bubblewrap): writable only in the repo and `/tmp`, `.git` read-only, `.env` and
  `.aimem/tls/` unreadable, no API keys, tokens or session markers in the environment, its own pid namespace; the
  network stays. A `verify` that writes elsewhere, reads keys or signals processes fails even if it passed by hand.
  Without bubblewrap the graph log says `검증 명령이 울타리 없이 돕니다`
- **Work done but `verify` wrong:** fix the `verify`, then `fleet_graph.py unblock <G> <node> --reverify` - it re-runs
  only the verify, without a new worker
- **Screen checks ask what is rendered** (`is_visible`, computed style, bounding boxes), not attributes. Projects
  with a screen check overlap and overflow after input; a screen behind login gets a check with auth on.
  Screen-task briefs carry this rule
- **Work on the fleet itself** (a request with no project): read `.aimem/briefs/fleet-self.md` first

**Graph checkpoints** (after each graph, so a cut session can resume from the DB)
- (a) one `aimem_db.py event` line: "G-xxx finished: per-node results, what remains"
- (b) board: a task in `REVIEW` → `DONE` when its review is done; a request → `DONE` when all its tasks are (the
  engine does the rest)
- (c) queue update (`queue drop`/`add`)
- (d) re-read `INBOX.md`; judge newly arrived `NEW` requests by start step 3

**Close**
1. Full tests and linter; `aimem_db.py handoff add --bump --expect-rev N --body "**REV N+1. …**"`; `render`; new
   rules registered in `8.0`. **`--expect-rev` is always given** - N is the REV this session last saw. A refusal
   means another session wrote meanwhile: re-read `handoff list --last 2` and the header, then decide; never retry
   with the new number blindly
2. `python3 tools/aimem_db.py archive` once (counts in the report)
3. Update each project's `PROGRESS.md`; report: `Status: DONE|PARTIAL|BLOCKED` + (1) task table (2) reproduced
   verification (3) waiting time (4) queue progress (5) next round's plan (6) operating metrics - slot utilization,
   Manager-only intervals, retries, slots added or nodes moved (7) one improvement proposal. Also written to
   `rounds/R<N>/REPORT.md`

**Request lifecycle:** `NEW` (web/phone form) → `PLANNED` (Manager splits) → `IN-PROGRESS` (Manager) →
`DONE`/`REJECTED` (Manager). Taeseok can edit title and body only while `NEW`.

**Control table** - who changes what

| Target | Changed by | Path | How the Manager learns |
| ------ | ---------- | ---- | ---------------------- |
| Standing slots: harness and model | Taeseok | web Fleet tab / `aimem_db.py slot` | auto NEW request, `events(kind=slot)` |
| Slot role, remark, assignment | Manager | `aimem_db.py slot set`, graphs | - |
| Extra slots (add, change, remove its own) | Manager, within the operating policy | `aimem_db.py slot add\|set\|remove` | the engine refuses what the policy does not allow; report item (6) |
| Pause, resume, remove or add a slot, also mid-round | Taeseok | web Fleet tab / `fleet_ctl.py slot` (add: `aimem_db.py slot add`) | `INBOX.md` (rc 4); `run` prints `쓸 수 없는 슬롯에 걸린 노드` - re-divide with `move`; report item (6) |
| Moving a node to another slot | Manager; to a slot of the same tier always, to another tier only if the policy allows | `fleet_graph.py move <G> <node> --slot S<n>` | graph log |
| Operating policy, project mode | Taeseok | `fleet_ctl.py round --policy` / web; `fleet_ctl.py project mode <name> <key>` / web project card | the blocks at the end of the brief |
| Requests: create, edit while NEW | Taeseok | request form | start step 3 / checkpoint (d) |
| Requests: split, status | Manager | `aimem_db.py request set`, graphs | - |
| Archive run | Manager (close 2) / Taeseok (web) | `aimem_db.py archive` | `events(kind=archive)` |
| Project removal | Taeseok, while nothing runs | web project card / `fleet_ctl.py project remove <name>` | `events(kind=project)`, handoff entry |
| Fleet mode (prepare, run, stop) | Taeseok | web fleet bar | `run` prints `함대 모드:`; rc 3 when stopped → checkpoint, report `PARTIAL` |
| Message to a running round | Taeseok | `fleet_ctl.py tell` | `INBOX.md`, rc 4 |
| Chained rounds (`이어 달리기`) | Taeseok | web fleet bar / `fleet_ctl.py chain` | the next round starts when one ends, while the targets have open requests, unchecked goals or queue items and the report is DONE |
| Commit and push | Claude Code, with Taeseok's permission | git | - |
