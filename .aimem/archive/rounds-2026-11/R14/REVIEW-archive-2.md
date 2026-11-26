# R14 T-191 재검수 - 결함 13건이 닫혔는가 (G-033)

검수자 S1 (claude/opus), REV 157, 2026-11-12. 대상: 작업 트리의 `tools/aimem_db.py` `archive_plan`(820~1069) ·
`archive_apply`(1072~1345) · `cmd_archive`(1348~1383), `tests/test_aimem_db_cli.py` `ArchiveAttachedRecordsTest`(454~),
`tests/test_archive_api.py`. **제품·검사는 고치지 않았다.** 운영 DB 에는 `archive_plan` (읽기) 만 불렀다.

## 방법

- 변이: 지난 부록 A 를 **글자 그대로** `REVIEW-archive.md` 에서 뽑아 다시 돌렸다 (`python3 -c` 로 블록을 꺼내 `exec`).
  제품이 바뀌어 치환 문자열이 안 맞는 6개(M03·M04·M06·M13·M16·M17)와, 문자열은 맞지만 고친 뒤 **중복 줄**이 되어
  뜻이 달라진 M11 은 같은 뜻의 치환으로 다시 썼다 (부록 A2, `'` 표시). 고친 곳 자체를 되돌리는 변이 X1~X11 을 더했다
- 시나리오: 지난 부록 B 를 그대로 돌리면 S5 에서 멈춘다 (이벤트 아카이브가 `events-*.md` → `events-*.jsonl` 로 바뀜).
  같은 상자(`TemporaryDirectory` + `mock.patch`) 로 S1~S12 를 지금 제품에 맞춰 다시 쓰고, 경쟁·render 실패를 보는 S7 경쟁·S13 을 더했다 (부록 B2)
- 기준선: 변이 없이 **124개 모두 통과** (지난번 115 → 새 시험 9개)

## 변이 표 - 22개 중 10개 잡힘 (지난번 8)

| # | 바꾼 것 | 지난번 | 이번 | 잡은 검사 / 메모 |
| -- | -- | -- | -- | -- |
| M01 | 이벤트 열린 id 보호 제거 | O | O | test_events_move_only_when_no_open_id_is_mentioned |
| M02 | 이벤트 시각 `<=` → `<` | X | X | 경계 시험 없음 |
| M03' | 이벤트를 jsonl 에 안 씀 (치환 고침) | O | O | 5개 |
| M04' | 이벤트 `missing` 확인 제거 (치환 고침) | X | X | 쓰기 실패 주입 시험 없음 |
| M05 | 핸드오프 12 → 11 | O | O | test_newest_12_handoffs… |
| M06' | 핸드오프 확인 없이 지움 (치환 고침) | X | X | 같음 |
| M07 | `.rc` 없는 실행 보호 제거 | O | O | test_running_run_stays… |
| M08 | 열린 태스크 실행 보호 제거 | X | X | 끝난 그래프에 열린 태스크 노드의 실행이 있는 경우만 다르다 - 시험 없음 |
| M09 | `_mentions` 뒤 경계 제거 | X | **O** | test_no_partial_id_match (방향 고쳐짐) |
| M10 | `_mentions` 앞 경계 제거 | X | X | `XT-15` 꼴 시험 없음 |
| M11' | 열린 그래프 보호 블록 제거 (치환 고침) | X | **O** | test_running_graph_protects_* 3개. 원래 문자열 `open_ids.update(open_graph_ids)` 은 이제 중복이라 X |
| M12 | 열린 요청(파일) 보호 제거 | X | X | 파일에만 있는 열린 요청 시험 없음. DB 쪽 M12' 도 X (아래 결함 13) |
| M13' | 남은 그래프 라운드 보호 제거 (치환 고침) | X | X | "한 라운드에 끝난 그래프와 도는 그래프가 함께, 최신 라운드는 아님" 시험 없음 |
| M14 | 로그 apply `<=` → `<` | X | X | 경계 시험 없음 |
| M15 | 로그 대상에 access.log | O | O | test_logs_move_only_old_timestamped_lines |
| M16' | 로그 줄 수 확인 제거 (치환 고침) | X | X | 쓰기 실패 주입 시험 없음 |
| M17' | DB `runs` 행 안 지움 (치환 고침) | O | O | test_finished_task_runs_move_with_it |
| M18 | 끝난 그래프 노드 실행 연결 제거 | X | X | `days>0` + 최근 실행 시험 없음 |
| M19 | `meta.rev` +1 | O | O | test_rev_unchanged… |
| M20 | 태스크 계획이 ASSIGNED/TODO 도 담음 | X | X | DELETE 재확인 덕에 행은 남지만 board 아카이브에 열린 태스크가 DONE 줄로 적힌다 - 시험 없음 |
| M21 | `kind=rev` 언제나 내림 | X | X | 시험 없음 |
| M22 | `--dry-run` 무시 | O | O | 9개 |

### 고친 곳을 되돌리는 변이 (이번에 더함) - 13개 중 4개 잡힘

| # | 되돌린 것 | 잡힘 | 메모 |
| -- | -- | -- | -- |
| M11'' | 열린 그래프 노드 id 보호만 | O | …finished_node_task_row |
| M11''' | 열린 그래프 run_id 보호만 | X | 노드 id=태스크 id 일 때 태스크 보호와 겹침. S1 의 "id≠태스크" 모양은 시험 없음 |
| M12'' | 큐 id 보호 | O | test_queue_referenced_event_stays |
| M13'' | 그래프 없는 라운드 보호 | O | test_open_round_and_graphless_relay_stay |
| M13''' | 최신 라운드 보호 | X | 시험의 r22 가 그래프 없는 라운드라 다른 규칙이 지킨다 |
| X1 | 결함 4: 실행 파일 `.json` 먼저 옮김 | X | 시험 없음 |
| X2 | 결함 4: 고아 `.rc/.out` 줍기 제거 | X | 시험 없음 |
| X3 | 결함 3: 태스크 멱등 제거 | O | test_apply_is_idempotent |
| X4 | 결함 3: 이벤트 멱등 제거 | O | test_apply_is_idempotent |
| X5 | 결함 3: 로그 멱등 제거 | X | 시험 없음 |
| X6/6b/6c | 결함 8: 핸드오프 확인·쓰기·둘 다 부분 문자열로 | X X X | **test_handoff_archive_line_exact_match 가 빈 검사** (새 결함 N4) |
| X7 | 결함 9: 태스크 DELETE 재확인 제거 | X | 시험 없음 |
| X8 | 결함 2: 같은 inode 다시 쓰기 → `os.replace` 로 되돌림 | X | **결함 2 를 통째로 되살려도 초록** |
| X9 | 결함 2: apply 의 monitor.log 쥠 확인 제거 | X | 시험 없음 |
| X10 | 결함 12: `render()` 호출 제거 | X | 시험 없음 |
| X11 | 결함 7: `rev` 칸 버림 | O | test_event_archive_keeps_rev_and_newlines |

## 결함 13건의 상태 - 닫힘 6 · 부분 6 · 안 닫힘 1

| 번호 | 상태 | 무엇으로 확인했나 |
| -- | -- | -- |
| 1 도는 그래프의 기록 | **닫힘** | S1: 태스크 내림 `[]`, 실행 내림 `[]`, T-1·T-3·G-1 이벤트 모두 남음. 노드 id≠태스크인 열린 그래프의 run `r-x` 도 남음. M11' 이 3개 시험에 잡힘 |
| 2 monitor.log 교체 | **부분** | S7: 같은 inode 로 자르고 다시 씀(inode 같음), 서버 fd 가 뒤에 쓴 줄 남음, pid 가 살았거나 pid 파일이 없으면 건너뜀. 운영 미리보기도 `monitor.log … 서버가 쥐고 있어 건너뜀`. **남은 것**: 읽기~자르기 사이에 덧붙은 줄이 원본·아카이브 둘 다에서 사라짐 (S7 경쟁, 새 결함 N2). X8·X9 가 초록 - 지키는 시험 없음 |
| 3 다시 돌리면 두 번 | **닫힘** | S5: tasks DELETE 직전 죽음 → board 에 T-1 **1번**, events → jsonl 에 seq 1 **1번**, 로그 다시 쓰기 직전 죽음 → 아카이브에 옛 줄 **1번**. 로그 멱등은 시험 없음 (X5) |
| 4 실행 파일 고아 | **부분** | S5: 1·2·3번째 replace 에서 죽으면 다음 계획이 줍고 재실행 뒤 `runs/` 비고 DB 행도 없음. 고아 `.out/.rc` 도 계획이 주움. **4번째(마지막 `.json`) 에서 죽으면** `.json` 만 남아 `.rc` 가 없으니 "도는 실행" 으로 보이고 다음 계획 `[]`, DB 행 남음 - 영구 고아 (새 결함 N1). X1·X2 초록 |
| 5 열린 요청·큐 | **부분** | S4: DB 에만 있는 열린 요청 + 끝난 T-1 이벤트 남음, 파일에만 있는 열린 요청도 남음. S3: id 있는 큐 항목 이벤트 남음. **id 없는 큐 항목** ("브라우저 검사를…") 의 `queue +1` 이벤트는 **여전히 내려감**. 운영에서 지금 큐 1·5번의 `queue +3`(#467)·`queue +5`(#597) 가 `--days 0` 계획에 들어 있다 |
| 6 전달 기록 | **닫힘** | S12: 그래프 없는 r20·문자열 round 의 r21 → 옮김 `[]`; 끝난 5·6·7 → `[5, 6]` (최신 7 남음); round 키 없는 끝난 그래프가 섞여도 정상. 운영: r7~r13 옮기고 r14 (G-033 도는 중·최신) 남음. M13'·M13''' 은 시험 없음 |
| 7 이벤트 rev·줄바꿈 | **닫힘** | S6: `{"seq":1,…,"rev":150,"body":"T-1 첫줄\n둘째줄"}`. X11 이 잡힘 |
| 8 핸드오프 부분 문자열 | **닫힘** (제품) | S10: 내린 seq `[2, 1]`, `'작업 1'` 줄 있음 `True`. 다만 그것을 지키는 시험이 빈 검사 (N4) |
| 9 계획~실행 사이 재확인 | **부분** | S11: 다시 열린 T-1 의 **행은 남음**. 그러나 board 아카이브에 `T-1 … DONE` 줄이 적히고, T-1 의 **이벤트·실행은 그대로 내려감**. 나중에 T-1 이 진짜 끝나면 멱등 표식(`| T-1 |`) 때문에 새 줄이 안 적혀 옛 줄이 남는다. X7 초록 |
| 10 migrate 뒤 핸드오프 순서 | **안 닫힘** | S9: `migrate 뒤 handoff.md 와 DB 렌더 같음: False` (그 밖은 정상: 12건, STALE 없음, `--bump --expect-rev 157 → (158,1)`, migrate 뒤 `→ (159,1)`) |
| 11 `[#seq]` 가 DB 세대를 모름 | **닫힘** (코드 읽기) | 표식이 `(seq, at)` 쌍이 되었다 (1201·1223). 새 DB 의 seq 1 과 옛 `[#1]` 은 `at` 이 달라 섞이지 않는다. 재현기·시험 없음 |
| 12 정리 뒤 render | **부분** | S13 정상 경로: `AIMEM-state.md` 가 다시 만들어지고 보드 표에 T-1 없음. 그러나 render 가 실패하면 `out["render_error"]` 에만 담기고 **CLI 는 안 찍고 웹 화면도 안 보인다** (새 결함 N3). X10 초록 |
| 13 검사의 구멍 | **부분** | 22개 중 10개 (8 → 10). 새 시험 9개 중 2개가 빈 검사 (N4), 고친 곳 변이 13개 중 4개만 잡힘 - 결함 2·4·8·9·12 의 수정은 되돌려도 초록 |

## 새로 찾은 결함

| 번호 | 위치 | 무엇이 잘못되나 · 재현 | 심각도 |
| -- | -- | -- | -- |
| N1 | `tools/aimem_db.py:1148-1149` + `926-927` | 실행 파일을 `.json` 을 **맨 마지막**에 옮기도록 고쳤는데, 계획은 `.rc` 없는 실행을 "도는 것" 으로 건너뛴다. 마지막 `.json` 이동에서 죽으면 `runs/` 에 `.json` 혼자 남아 **영원히 도는 실행**으로 보이고 다시 줍지 못한다. DB `runs` 행도 남는다 (DELETE 는 파일 뒤). S5 k=4: `남은 ['T-1-S1-a1.json'] | 다음 계획 [] | 재실행 뒤 그대로 | DB 행 [('T-1-S1-a1',)]`. 고치기: `.rc` 를 맨 마지막에 옮기면 (그 전 단계 고아는 `.rc` 고아 줍기가 받는다) 어디서 죽어도 다음 계획이 줍는다 | 중간~낮음 (같은 폴더 rename 실패라 드묾. 결함 4 의 범위를 줄였을 뿐 남아 있다) |
| N2 | `tools/aimem_db.py:1271-1311` | 로그를 같은 핸들에서 `read()` → 아카이브 쓰기·확인 → `seek(0)/write(kept)/truncate()`. 그 사이에 다른 프로세스가 `O_APPEND` 로 덧붙인 줄은 `kept` 에 없으므로 잘려 **원본·아카이브 둘 다에서 사라진다**. 잠금(flock)도, 자르기 직전 크기 재확인도 없다. S7 경쟁: `fleet-mode.log` · `monitor.log`(죽은 pid) 모두 `끼어든 줄이 원본에 False / 아카이브에 False` | 낮음 - 창은 ms 단위. `fleet-mode.log` 는 `fleet_ctl.set_mode` 때만 쓰이고 `monitor.log` 는 서버가 죽었을 때만 손댄다. 하지만 되돌릴 수 없는 손실이다. 고치기: 자르기 직전 `f.seek(0,2)` 크기가 처음 읽은 길이와 다르면 덧붙은 꼬리를 `kept` 에 더하거나 포기 |
| N3 | `tools/aimem_db.py:1341-1344`, `cmd_archive` 1382, `static/app.js:2311-2316` | `render()` 예외는 모두 삼켜 `out["render_error"]` 에만 담는다. `cmd_archive` 는 그것을 찍지 않고, 웹은 `moved_counts` 에 문자열로 실려 오지만 화면은 runs/events/… 만 읽는다. S13: `render_error = OSError: state 쓰기 실패` / `cmd_archive 출력에 보이나: False`. 그러면 `AIMEM-state.md`·`handoff.md` 가 낡은 채로 "성공" 이 뜨고 린터 STATE_SNAPSHOT 이 나중에 걸린다. 덧붙여 `render()` 는 `sync_rev_in_aimem()` 로 **`AIMEM.md` 를 쓸 수 있다** (DB REV ≠ 서문 REV 일 때) - 웹 단추가 관리자 전용 파일을 건드리는 길이다 | 낮음 |
| N4 | `tests/test_aimem_db_cli.py:722` `test_handoff_archive_line_exact_match`, `:680` `test_db_only_open_request_event_stays` | 둘 다 **빈 검사**. 앞의 것은 미리 적어 둔 줄이 `관리자:` 인데 시험 행의 actor 가 `"t"` 라 만들어지는 줄은 `- \`… \` t: … 작업 1` - 접두가 겹치지 않는다. 그래서 X6c (쓰기·확인 둘 다 부분 문자열) 도 초록. 뒤의 것은 이벤트가 `Q-OPEN` 만 가리키므로 보호가 없어도 "알려진 id, 정리 대상 아님" 으로 남는다 (M12' 초록). S4 처럼 끝난 `T-1` 을 함께 넣어야 잰다 | 중간 (결함 8·5 의 회귀를 아무도 못 본다) |

참고 (결함으로 올리지 않음): 운영 `--days 0` 계획에 **G-032** (노드 10개 모두 done) 가 들어간다. 그 그래프의 요청
`Q-261111-7859`·`731b` 는 DB 에서 아직 `IN-PROGRESS` 다. 그래프의 `request` 칸이 자유 글이라 요청 id 로 묶이지 않는다.
요청이 끝나기 전에 그 그래프 파일이 `archive/` 로 가도 되는지는 관리자가 정할 일이다.

## 보호 집합이 너무 넓어지지 않았나 - 운영 DB 읽기

`PYTHONPATH=tools python3 -c "import aimem_db as A; A.archive_plan(14); A.archive_plan(0)"` (읽기만):

| | 태스크 | 요청 | 그래프 | 실행 | 이벤트 | 핸드오프 | 전달 | 로그 |
| -- | -- | -- | -- | -- | -- | -- | -- | -- |
| 지난번 `--days 0` | 80 | 14 | 24 | 166 | 514 | 57 | 7 (r7~r13) | fleet-mode 38 / monitor 0 |
| 이번 `--days 0` | 80 | 14 | 25 | 166 | 511 | 57 | 7 (r7~r13) | fleet-mode 38 / monitor 건너뜀 (서버 살아 있음) |
| 이번 `--days 14` | 0 | 0 | 0 | 0 | 0 | 4 | 0 | fleet-mode 0 / monitor 건너뜀 |

**지나치게 넓지 않다.** 이벤트가 3건 줄었고 (새 보호 - 큐 id·DB 열린 요청 - 때문으로 보이나 건별 대조는 안 했다; 그 사이 이벤트도 새로 쌓였다), 그래프는 G-032 가 끝나 1개 늘었다.
열린 태스크 15개 (T-164 BLOCKED, T-177~185 REVIEW, T-187~191 ASSIGNED)·열린 요청 5개·G-033·r14 는 계획에 없다.

## 운영에서 "지금 끝난 것 전부" 를 눌러도 되는가

**예, 조건부로.** 지난번 막았던 두 이유는 풀렸다: 도는 그래프(G-033)의 실행·태스크·이벤트는 계획에 없고(결함 1 닫힘),
`monitor.log` 는 서버 pid 가 살아 있어 아예 건드리지 않으며 교체 대신 같은 inode 에서 자른다(결함 2 의 손실 경로 닫힘).
중복·`rev` 손실·핸드오프 부분 문자열 손실도 닫혔다. 남은 위험은 작고 모두 "지워지지 않고 `archive/` 로 옮겨진다":
id 없는 큐 항목 1·5번의 `queue +N` 이벤트 2건(#467·#597)이 내려가고(결함 5 부분), `fleet-mode.log` 38줄을 자르는
몇 ms 동안 모드 전환이 겹치면 그 한 줄을 잃을 수 있다(N2). 그러니 **누르기 전에 큐 1·5번 이벤트를 남길지 정하고,
누르는 동안 `fleet.py mode` 를 바꾸지 않으면** 눌러도 된다. 다만 웹 단추는 `plan.total`(태스크·요청·그래프) 이 0 이면
비활성이라 `--days 14` 의 핸드오프 4건만 있을 때는 웹에서 못 누른다 - 이것은 결함이 아니라 참고다.

## 다음 라운드로 넘길 것

1. **결함 10** (안 닫힘): `_import_handoff_entries` 가 rev 를 못 읽으면 파일 순서로 이어받기 - S9 의 마지막 `False` 를 시험으로
2. **결함 5 잔여**: 큐 항목이 id 없이 글만 있을 때도 그 `queue +N` 이벤트를 지키기 (큐 `task` 글과 이벤트 본문 비교) - 운영 #467·#597
3. **결함 9 잔여**: 계획~실행 사이 다시 열린 태스크의 실행·이벤트도 내리지 않기, board 아카이브에 DONE 줄 안 적기 (DELETE 결과를 먼저 보고 쓰기)
4. **N1**: 실행 파일 이동 순서를 `.rc` 맨 마지막으로 (또는 `.json` 단독 + DB 행 `done` 인 것을 고아로 줍기)
5. **N2**: 로그 자르기 직전 길이 재확인 또는 flock
6. **N3**: `render_error` 를 CLI·웹에 보이기. 아카이브 안의 render 가 `AIMEM.md` 를 쓰지 않게 (`render_text`+`handoff_sync` 만)
7. **N4**: 빈 검사 두 개 고치기 (actor 를 `관리자` 로, 이벤트에 끝난 `T-1` 함께)
8. **결함 13 잔여 - 시험이 없는 수정**: X1·X2(실행 순서·고아), X5(로그 멱등), X7(DELETE 재확인), X8·X9(같은 inode·서버 쥠),
   X10(render) 을 각각 시험으로. 그리고 M02·M14 (기준 시각 경계), M10 (앞 경계 `XT-15`), M13' (한 라운드에 끝난·도는 그래프),
   M13''' (최신 라운드), M16'/M04'/M06' (쓰기 실패 주입), M20 (board 에 열린 태스크 줄), M21 (`kind=rev`)
9. 참고: 열린 요청의 그래프(G-032) 를 정리할지 관리자 결정

## 부록 A2. 치환을 고친 변이 + 고친 곳 변이

```python
# === RUNNER mut2 ===
import sys, types, unittest, io, importlib, pathlib, contextlib
ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
SRC = (ROOT / "tools" / "aimem_db.py").read_text(encoding="utf-8")
M = [
 ("M03' 이벤트: jsonl 에 안 씀", 'fh.write(json.dumps(row, ensure_ascii=False) + "\\n")', 'pass'),
 ("M04' 이벤트: missing 확인 제거", 'missing = [e["seq"] for e in events if (e.get("seq"), e.get("at")) not in seen]', 'missing = []'),
 ("M06' 핸드오프: 확인 없이 지움", '            if line in text.splitlines():\n                confirmed.append(h["seq"])', '            confirmed.append(h["seq"])'),
 ("M11' 열린 그래프 보호 블록 전체 제거", '            if not archived:\n                protected_ids.add(gid)', '            if False:\n                protected_ids.add(gid)'),
 ("M11'' 열린 그래프 노드 id 보호만 제거", '                    for key in (n.get("id"), n.get("task")):\n                        if isinstance(key, str) and key:\n                            protected_ids.add(key)', '                    pass'),
 ("M11''' 열린 그래프 run_id 보호만 제거", '                        if isinstance(attempt, dict) and attempt.get("run_id"):\n                            protected_ids.add(str(attempt["run_id"]))', '                        pass'),
 ("M12' DB 열린 요청 보호 제거", "\"SELECT id FROM requests WHERE upper(COALESCE(status,'')) NOT IN ('DONE','REJECTED')\")}", "\"SELECT id FROM requests WHERE 0\")}"),
 ("M12'' 큐 보호 제거", 'protected_ids.update(re.findall(', '(re.findall('),
 ("M13' 전달: 남은 그래프 라운드 보호 제거", 'if str(n) in remaining_graph_rounds:\n                continue', 'pass'),
 ("M13'' 전달: 그래프 없는 라운드 보호 제거", 'if str(n) not in archived_graph_rounds:', 'if False:'),
 ("M13''' 전달: 최신 라운드 보호 제거", 'if n == max_round:\n                continue', 'pass'),
 ("M16' 로그: 줄 수 확인 제거", 'if after <= before and not old_text.endswith(chunk):', 'if False:'),
 ("M17' 실행: DB runs 행을 안 지움", 'con.execute("DELETE FROM runs WHERE id=?", (r["id"],))', '0 and con.execute("DELETE FROM runs WHERE id=?", (r["id"],))'),
 ("X1 결함4: .json 을 먼저 옮김", '        ordered = [name for name in names if not name.endswith(".json")]\n        ordered += [name for name in names if name.endswith(".json")]', '        ordered = sorted(names)'),
 ("X2 결함4: 고아 줍기 제거", '            orphans.setdefault(rid, []).append(f)', '            pass'),
 ("X3 결함3: 태스크 멱등 제거", '                    if any(line.startswith(marker) for line in old_lines):\n                        continue', '                    pass'),
 ("X4 결함3: 이벤트 멱등 제거", '                if marker in existing:\n                    continue', '                pass'),
 ("X5 결함3: 로그 멱등 제거", '                    if not old_text.endswith(chunk):\n                        with', '                    if True:\n                        with'),
 ("X6 결함8: 핸드오프 부분문자열로 되돌림", '            if line in text.splitlines():\n                confirmed', '            if line in text:\n                confirmed'),
 ("X6b 결함8: 핸드오프 쓰기 쪽을 부분문자열로", '                if line not in old.splitlines():', '                if line not in old:'),
 ("X6c 결함8: 쓰기·확인 둘 다 부분문자열로", '                if line not in old.splitlines():', '                if line not in old:', '            if line in text.splitlines():\n                confirmed', '            if line in text:\n                confirmed'),
 ("X7 결함9: 태스크 DELETE 재확인 제거", "con.execute(f\"DELETE FROM tasks WHERE id IN ({','.join('?' * len(ids))}) AND status='DONE'\", ids)", "con.execute(f\"DELETE FROM tasks WHERE id IN ({','.join('?' * len(ids))})\", ids)"),
 ("X8 결함2: 같은 inode 대신 os.replace", '                f.seek(0)\n                f.write("".join(kept))\n                f.truncate()', '                tmp = log_path.with_suffix(".tmp"); tmp.write_text("".join(kept), encoding="utf-8"); os.replace(tmp, log_path)'),
 ("X9 결함2: monitor.log 쥠 확인 제거(apply)", '            held, reason = _monitor_log_held()\n            if held:\n                continue', '            pass'),
 ("X10 결함12: render 호출 제거", '        try:\n            render()', '        try:\n            pass'),
 ("X11 결함7: rev 칸 버림", '"rev": e.get("rev"), "kind"', '"kind"'),
]
def run(src):
    mod = types.ModuleType("aimem_db"); mod.__file__ = str(ROOT / "tools" / "aimem_db.py")
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    sys.modules["aimem_db"] = mod
    suite = unittest.TestSuite()
    for n in ("test_aimem_db_cli", "test_archive_api"):
        sys.modules.pop(n, None)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(n)))
    buf = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()):
        r = unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
    return r.testsRun, [t.id().split(".", 1)[1] for t, _ in r.failures + r.errors]
n, f = run(SRC); print("BASELINE ran", n, "fail", f)
ONLY = sys.argv[1:]   # 이름 앞부분을 주면 그것만
for k, *pr in M:
    if ONLY and not any(k.startswith(o) for o in ONLY): continue
    src, cs = SRC, []
    for a, b in zip(pr[::2], pr[1::2]):
        cs.append(src.count(a)); src = src.replace(a, b)
    if min(cs) < 1:
        print(k, "| PATTERN-NOT-FOUND"); continue
    n, f = run(src)
    print(k, "| 자리", cs, "|", "O" if f else "X", "|", ", ".join(sorted(set(x.split(".")[-1] for x in f)))[:200])
# === END ===
```

## 부록 B2. 시나리오 재현기 (부록 B 를 지금 제품에 맞춘 것)

```python
# === RUNNER scen2 ===
import sys, json, pathlib, tempfile, contextlib, io, os, sqlite3, types
from unittest import mock
ROOT = pathlib.Path.cwd(); sys.path.insert(0, str(ROOT / "tools"))
import aimem_db as A
OLD = "2026-01-01T00:00:00"

@contextlib.contextmanager
def box():
    tmp = tempfile.TemporaryDirectory(); root = pathlib.Path(tmp.name).resolve()
    for d in ("requests", "runs", "graph/inputs", "relay"):
        (root / ".aimem" / d).mkdir(parents=True)
    ps = [mock.patch.object(A, "ROOT", root), mock.patch.object(A, "DB", root / ".aimem" / "aimem.db"),
          mock.patch.object(A, "AIMEM", root / "AIMEM.md"), mock.patch.object(A, "HANDOFF", root / ".aimem" / "handoff.md")]
    for p in ps: p.start()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            A.cmd_init()
        with A.connect() as c:
            c.execute("INSERT INTO meta(key,value) VALUES('rev','157')"); c.commit()
        yield root
    finally:
        for p in ps: p.stop()
        tmp.cleanup()

def sql(q, *a):
    with A.connect() as c:
        r = c.execute(q, a).fetchall(); c.commit(); return r
def task(t, st, upd=OLD): sql("INSERT INTO tasks(id,title,slot,status,created,updated) VALUES(?,?,?,?,?,?)", t, "t", "S1", st, upd, upd)
def ev(body, kind="note", at=OLD, rev=None):
    with A.connect() as c:
        s = c.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)", (at, "t", rev, kind, body)).lastrowid; c.commit(); return s
def run(root, rid, t, rc=True):
    d = root / ".aimem" / "runs"
    (d / (rid + ".json")).write_text(json.dumps({"id": rid, "task": t, "started": OLD}), encoding="utf-8")
    (d / (rid + ".out")).write_text("x", encoding="utf-8"); (d / (rid + ".brief.md")).write_text("x", encoding="utf-8")
    if rc: (d / (rid + ".rc")).write_text("0", encoding="utf-8")
    sql("INSERT INTO runs(id,task_id,started,state) VALUES(?,?,?,?)", rid, t, OLD, "done" if rc else "running")
def graph(root, gid, nodes, rnd=None, side=()):
    g = {"id": gid, "request": "Q", "created": OLD, "updated": OLD, "nodes": nodes}
    if rnd is not None: g["round"] = rnd
    gd = root / ".aimem" / "graph"; (gd / (gid + ".json")).write_text(json.dumps(g), encoding="utf-8")
    for s in side: (gd / s).write_text("x", encoding="utf-8")
def apply0():
    p = A.archive_plan(0)
    with contextlib.redirect_stdout(io.StringIO()):
        o = A.archive_apply(p, "t")
    return p, o
def alive(seq): return bool(sql("SELECT 1 FROM events WHERE seq=?", seq))
def jl(root, name="events-2026-01.jsonl"):
    f = root / ".aimem/archive" / name
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []
def pidfile(root, pid): (root / ".aimem/monitor.pid").write_text(str(pid), encoding="utf-8")
DEAD = 2**22 + 12345   # pid_max 를 넘는 수 - 살아 있을 수 없다

print("== S1 도는 그래프의 끝난 노드: 태스크·실행·이벤트 (결함 1)")
with box() as root:
    task("T-1", "DONE"); task("T-2", "ASSIGNED")
    graph(root, "G-1", [{"id": "T-1", "status": "done", "attempts": [{"run_id": "T-1-S1-a1"}]},
                        {"id": "T-3", "status": "done", "attempts": [{"run_id": "T-3-S1-a1"}]},
                        {"id": "T-2", "status": "running", "attempts": [{"run_id": "T-2-S1-a1"}]}], rnd=14)
    run(root, "T-1-S1-a1", "T-1"); run(root, "T-3-S1-a1", "T-3"); run(root, "T-2-S1-a1", "T-2", rc=False)
    e1 = ev("T-1 DONE 보고"); e3 = ev("T-3 노드 끝남"); eg = ev("G-1 진행 중 T-1 done")
    p, o = apply0()
    print(" 태스크 내림", o["tasks"], "| 실행 내림", sorted(o["runs"]), "| 이벤트 T-1 남음", alive(e1), "T-3 남음", alive(e3), "G-1 남음", alive(eg))
    print(" 그래프 노드가 run_id 만 있고 id 가 태스크와 다를 때:")
with box() as root:
    graph(root, "G-1", [{"id": "n1", "task": "inputs-n1", "status": "done", "attempts": [{"run_id": "r-x"}]},
                        {"id": "n2", "status": "running"}])
    run(root, "r-x", "T-77")
    p, o = apply0(); print("  열린 그래프 노드의 실행 r-x 내림:", o["runs"])

print("== S2 경계 (회귀)")
with box() as root:
    task("T-15", "DONE"); task("T-150", "TODO")
    run(root, "T-15-S1-a1", "T-15"); run(root, "T-150-S1-a1", "T-150")
    a = ev("T-150 진행"); b = ev("T-15 끝"); g = ev("T-15 와 T-150 비교"); h = ev("XT-15 끝")
    p, o = apply0()
    print(" T-150 남음", alive(a), "| T-15 내려감", not alive(b), "| 함께 남음", alive(g), "| 'XT-15' 내려감", not alive(h), "| 실행", o["runs"])

print("== S3 대기 큐 (결함 5)")
with box() as root:
    sql("INSERT INTO queue(pos,task) VALUES(1,'T-300 다음 할 일')")
    s = ev("queue +1 T-300 다음 할 일", kind="queue")
    apply0(); print(" id 있는 큐 항목의 이벤트 남음:", alive(s))
with box() as root:
    sql("INSERT INTO queue(pos,task) VALUES(1,'브라우저 검사를 파이어폭스로도 한 번')")
    s = ev("queue +1 브라우저 검사를 파이어폭스로도 한 번", kind="queue")
    apply0(); print(" id 없는 큐 항목의 이벤트 남음:", alive(s), "| 큐 행", [tuple(r) for r in sql("SELECT pos,task FROM queue")])

print("== S4 DB 에만 있는 열린 요청 (결함 5)")
with box() as root:
    task("T-1", "DONE"); sql("INSERT INTO requests(id,status,created) VALUES('Q-OPEN','IN-PROGRESS',?)", OLD)
    s = ev("T-1 은 Q-OPEN 의 첫 단계")
    apply0(); print(" 끝난 T-1 과 열린 Q-OPEN 을 함께 가리키는 이벤트 남음:", alive(s))
with box() as root:
    task("T-1", "DONE")
    (root / ".aimem/requests/Q-F.json").write_text(json.dumps({"id": "Q-F", "status": "NEW", "created": OLD}), encoding="utf-8")
    s = ev("T-1 은 Q-F 의 첫 단계")
    apply0(); print(" 파일에만 있는 열린 요청 Q-F 와 T-1 을 함께 가리키는 이벤트 남음:", alive(s))

print("== S5 중간에 죽고 다시 (결함 3·4)")
class Boom(Exception): pass
def dying(prefix):
    orig = A.connect
    def bad():
        con = orig()
        class W:
            def execute(s, q, *a):
                if q.startswith(prefix): raise Boom(prefix)
                return con.execute(q, *a)
            def __getattr__(s, n): return getattr(con, n)
            def __enter__(s): con.__enter__(); return s
            def __exit__(s, *a): return con.__exit__(*a)
        return W()
    return mock.patch.object(A, "connect", bad)
with box() as root:
    task("T-1", "DONE")
    try:
        with dying("DELETE FROM tasks"): apply0()
    except Boom: pass
    apply0()
    print("  DELETE FROM tasks 직전 죽음 → board 에 T-1", (root / ".aimem/archive/board-2026-01.md").read_text(encoding="utf-8").count("| T-1 |"), "번")
with box() as root:
    ev("T-1 끝")
    try:
        with dying("DELETE FROM events"): apply0()
    except Boom: pass
    apply0()
    print("  DELETE FROM events 직전 죽음 → jsonl 에 seq 1", sum(1 for r in jl(root) if r["seq"] == 1), "번")
with box() as root:
    log = root / ".aimem" / "fleet-mode.log"; log.write_text("2026-01-01T00:00:00 옛 줄\n2099-01-01T00:00:00 새 줄\n", encoding="utf-8")
    orig_open = pathlib.Path.open
    def bad_open(self, mode="r", *a, **k):
        f = orig_open(self, mode, *a, **k)
        if self.name == "fleet-mode.log" and mode == "r+":
            class F:
                def __getattr__(s, n): return getattr(f, n)
                def __enter__(s): return s
                def __exit__(s, *x): f.close()
                def read(s, *x): return f.read(*x)
                def seek(s, *x): raise Boom("seek")
            return F()
        return f
    try:
        with mock.patch.object(pathlib.Path, "open", bad_open): apply0()
    except Boom: pass
    apply0()
    print("  로그 원본 다시 쓰기 직전 죽음 → 아카이브에 '옛 줄'", (root / ".aimem/archive/logs-2026-01/fleet-mode.log").read_text(encoding="utf-8").count("옛 줄"), "번 | 원본:", log.read_text(encoding="utf-8").splitlines())
for k in (1, 2, 3, 4):
    with box() as root:
        task("T-1", "DONE"); run(root, "T-1-S1-a1", "T-1")
        origr = pathlib.Path.replace; n = [0]
        def badr(self, t, k=k):
            if self.parent.name == "runs":
                n[0] += 1
                if n[0] == k: raise OSError("disk")
            return origr(self, t)
        try:
            with mock.patch.object(pathlib.Path, "replace", badr): apply0()
        except OSError: pass
        left = sorted(x.name for x in (root / ".aimem/runs").iterdir())
        p2 = A.archive_plan(0)
        apply0()
        left2 = sorted(x.name for x in (root / ".aimem/runs").iterdir())
        print(f"  실행 파일 {k}번째 replace 에서 죽음 → 남은 {left} | 다음 계획 실행 {[r['id'] for r in p2['runs']]} | 재실행 뒤 runs/ {left2} | DB 행 {[tuple(r) for r in sql('SELECT id FROM runs')]}")
with box() as root:
    d = root / ".aimem/runs"; (d / "r-orph.out").write_text("x"); (d / "r-orph.rc").write_text("0")
    p = A.archive_plan(0); print("  .json 없는 고아 .out/.rc 를 계획이 줍나:", [r["id"] for r in p["runs"]])

print("== S6 이벤트 rev / 줄바꿈 (결함 7)")
with box() as root:
    task("T-1", "DONE"); ev("T-1 첫줄\n둘째줄", kind="task", rev=150)
    apply0(); r = jl(root)[0]; print(" ", r, "| rev 남음", r["rev"] == 150, "| 줄바꿈 남음", "\n" in r["body"])

print("== S7 monitor.log (결함 2)")
for label, pid in (("pid 파일 없음", None), ("살아 있는 pid", os.getpid()), ("죽은 pid", DEAD)):
    with box() as root:
        ml = root / ".aimem" / "monitor.log"; fh = open(ml, "a", encoding="utf-8")
        fh.write("2026-01-01T00:00:00 옛 줄\n"); fh.flush()
        if pid is not None: pidfile(root, pid)
        ino = ml.stat().st_ino
        p, o = apply0(); fh.write("2099-01-01T00:00:00 아카이브 뒤 401 줄\n"); fh.flush(); fh.close()
        txt = ml.read_text(encoding="utf-8")
        print(f"  [{label}] 계획 {p['logs'][0]} | 옮긴 줄 {o['log_lines']} | 같은 inode {ml.stat().st_ino == ino} | 뒤에 쓴 줄 남음 {'401' in txt} | 옛 줄 원본에 남음 {'옛 줄' in txt} | 앞에 NUL {chr(0) in txt}")
print("  경쟁: 읽은 뒤·다시 쓰기 전에 다른 프로세스가 덧붙인 줄")
for name in ("fleet-mode.log", "monitor.log"):
    with box() as root:
        log = root / ".aimem" / name; log.write_text("2026-01-01T00:00:00 옛 줄\n", encoding="utf-8")
        if name == "monitor.log": pidfile(root, DEAD)
        orig_open = pathlib.Path.open
        def racing(self, mode="r", *a, **k):
            if self.name == name and self.parent.name.startswith("logs-") and mode == "a":
                with orig_open(log, "a", encoding="utf-8") as w: w.write("2099-01-01T00:00:00 끼어든 줄\n")
            return orig_open(self, mode, *a, **k)
        with mock.patch.object(pathlib.Path, "open", racing): apply0()
        arch = (root / ".aimem/archive/logs-2026-01" / name).read_text(encoding="utf-8")
        print(f"  [{name}] 끼어든 줄이 원본에 {'끼어든' in log.read_text(encoding='utf-8')} / 아카이브에 {'끼어든' in arch}")

print("== S8 access.log (회귀)")
with box() as root:
    acc = root / ".aimem" / "access.log"; acc.write_bytes(b"2026-01-01T00:00:00\tlogin-ok\t1.2.3.4\n"); before = acc.read_bytes()
    pidfile(root, DEAD)
    (root / ".aimem/monitor.log").write_text("2026-01-01T00:00:00 m\n"); (root / ".aimem/fleet-mode.log").write_text("2026-01-01T00:00:00 f\n")
    task("T-1", "DONE"); ev("T-1"); apply0()
    print("  바이트 같음:", acc.read_bytes() == before)

print("== S9 핸드오프 12건·REV·DB 잃은 뒤 migrate (결함 10)")
with box() as root:
    for i in range(1, 16):
        ev("- `2026-01-%02d 00:00` 관리자: **REV %d** 항목 %02d" % (i, 140 + i, i), kind="handoff", at="2026-01-%02d 00:00" % i, rev=140 + i)
    ev("REV 155: 뭔가", kind="rev", rev=155); task("T-1", "DONE"); ev("T-1 끝")
    with contextlib.redirect_stdout(io.StringIO()): A.handoff_sync()
    p, o = apply0()
    hm = A.HANDOFF.read_text(encoding="utf-8")
    with A.connect() as c: stale = hm != A.render_handoff_text(c)
    print("  핸드오프 DB", sql("SELECT count(*) FROM events WHERE kind='handoff'")[0][0], "| handoff.md 항목", hm.count("\n- `"), "| STALE?", stale,
          "| meta.rev", sql("SELECT value FROM meta WHERE key='rev'")[0][0])
    print("  handoff add --bump --expect-rev 157 →", A.handoff_add("다음", bump=True, expect_rev=157))
    (root / "AIMEM.md").write_text("- **REV: 158**\n", encoding="utf-8")
    for x in (".aimem/aimem.db", ".aimem/aimem.db-wal", ".aimem/aimem.db-shm"):
        if (root / x).exists(): (root / x).unlink()
    with contextlib.redirect_stdout(io.StringIO()): A.migrate(verbose=False)
    print("  migrate 뒤: rev", sql("SELECT value FROM meta WHERE key='rev'")[0][0], "| 핸드오프", sql("SELECT count(*) FROM events WHERE kind='handoff'")[0][0])
    with A.connect() as c: print("  migrate 뒤 handoff.md 와 DB 렌더 같음:", A.HANDOFF.read_text(encoding="utf-8") == A.render_handoff_text(c))
    print("  migrate 뒤 handoff add --bump --expect-rev 158 →", A.handoff_add("또", bump=True, expect_rev=158))

print("== S10 핸드오프 줄이 다른 줄의 앞부분 (결함 8)")
with box() as root:
    ev("- `2026-01-01 00:00` 관리자: 작업 1", kind="handoff", at="2026-01-01 00:00", rev=1)
    ev("- `2026-01-01 00:00` 관리자: 작업 12", kind="handoff", at="2026-01-01 00:00", rev=2)
    for i in range(12): ev("- `2026-02-01 00:00` 관리자: 새 %d" % i, kind="handoff", at="2026-02-01 00:00", rev=10 + i)
    p, o = apply0()
    arch = (root / ".aimem/archive/handoff-2026-01.md").read_text(encoding="utf-8").splitlines()
    print("  내린 seq", o["handoff"], "| '작업 1' 줄 있나:", "- `2026-01-01 00:00` 관리자: 작업 1" in arch)

print("== S11 계획과 실행 사이 다시 열린 태스크 (결함 9)")
with box() as root:
    task("T-1", "DONE"); ev("T-1 끝"); run(root, "T-1-S1-a1", "T-1"); p = A.archive_plan(0); sql("UPDATE tasks SET status='ASSIGNED' WHERE id='T-1'")
    with contextlib.redirect_stdout(io.StringIO()): o = A.archive_apply(p, "t")
    print("  T-1 행 남음:", bool(sql("SELECT 1 FROM tasks WHERE id='T-1'")), "| board 아카이브에 T-1 DONE 줄:", "| T-1 |" in (root / ".aimem/archive/board-2026-01.md").read_text(encoding="utf-8"),
          "| T-1 이벤트 남음:", alive(1), "| T-1 실행 남음:", (root / ".aimem/runs/T-1-S1-a1.json").exists())

print("== S12 전달 기록 (결함 6)")
with box() as root:
    (root / ".aimem/relay/r20.json").write_text(json.dumps({"round": 20, "at": OLD})); (root / ".aimem/relay/r20.log").write_text("x")
    graph(root, "G-9", [{"id": "T-9", "status": "running"}], rnd="21")
    (root / ".aimem/relay/r21.json").write_text(json.dumps({"round": 21, "at": OLD}))
    p, o = apply0(); print("  옮긴 라운드:", o["relay"])
with box() as root:
    for n in (5, 6, 7): (root / (".aimem/relay/r%d.json" % n)).write_text(json.dumps({"round": n, "at": OLD}))
    graph(root, "G-5", [{"id": "T-5", "status": "done"}], rnd=5); graph(root, "G-6", [{"id": "T-6", "status": "done"}], rnd=6)
    graph(root, "G-7", [{"id": "T-7", "status": "done"}], rnd=7)
    p, o = apply0(); print("  끝난 라운드 5·6·7 (7 최신) → 옮김:", o["relay"])
with box() as root:
    for n in (5, 6): (root / (".aimem/relay/r%d.json" % n)).write_text(json.dumps({"round": n, "at": OLD}))
    graph(root, "G-5", [{"id": "T-5", "status": "done"}], rnd=5); graph(root, "G-X", [{"id": "T-X", "status": "done"}])
    p, o = apply0(); print("  round 키 없는 끝난 그래프 G-X 가 같이 있을 때 → 옮김:", o["relay"], "(G-X 도 정리됨:", "G-X" in o["graphs"], ")")

print("== S13 render 가 정리 안에서 실패하면 (결함 12)")
with box() as root:
    task("T-1", "DONE")
    def boom(): raise OSError("state 쓰기 실패")
    with mock.patch.object(A, "render", boom):
        p, o = apply0()
    print("  out.render_error =", o.get("render_error"), "| T-1 DB 에서 내려감", not sql("SELECT 1 FROM tasks WHERE id='T-1'"))
    buf = io.StringIO()
    with mock.patch.object(A, "render", boom), contextlib.redirect_stdout(buf):
        task("T-2", "DONE"); A.cmd_archive(types.SimpleNamespace(days=0, dry_run=False, actor="t"))
    print("  cmd_archive 출력에 render 실패가 보이나:", "render" in buf.getvalue() or "state" in buf.getvalue())
with box() as root:
    task("T-1", "DONE"); apply0()
    st = (root / "AIMEM-state.md")
    print("  정상 경로: AIMEM-state.md 만들어짐", st.exists(), "| 보드 표에 T-1 행 없음", st.exists() and "| T-1 |" not in st.read_text(encoding="utf-8"))
# === END ===
```
