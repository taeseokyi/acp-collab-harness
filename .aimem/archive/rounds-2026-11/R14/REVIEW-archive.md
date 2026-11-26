# R14 T-186 적대적 검수 - 연동 아카이브 (G-032, 요청 Q-261111-7859·731b)

검수자 S1 (claude/opus), REV 157, 2026-11-11. 대상: 작업 트리의 `tools/aimem_db.py` `archive_plan`(785~965) ·
`archive_apply`(968~1165) · `cmd_archive`(1168~1203) · 핸드오프 묶음(26~205), `tools/aimem_monitor/server.py`
`archive_action`(1179~1217), `tests/test_aimem_db_cli.py` `ArchiveAttachedRecordsTest`, `tests/test_archive_api.py`.
**제품·검사는 고치지 않았다.**

## 방법 (지시와 다른 점 하나)

지시는 "저장소를 `/tmp` 로 복사하고 끝나면 `rm -rf`" 였으나, 그것은 이 슬롯 소유 경로 밖 쓰기이자 삭제이고
사용자 전역 지침이 둘 다 사용자의 직접 허락을 요구한다. 그래서 **저장소를 복사하지 않고** 같은 효과를 이렇게 냈다:

- 변이: `tools/aimem_db.py` 원문을 메모리에서 문자열 치환해 `aimem_db` 모듈로 올리고, 그 모듈로
  `test_aimem_db_cli` + `test_archive_api` (115개) 를 돌렸다. 디스크의 제품 파일은 그대로다 (부록 A)
- 시나리오: 기존 단위 시험과 똑같이 `tempfile.TemporaryDirectory` + `mock.patch(ROOT/DB/AIMEM/HANDOFF)` 상자 안에서
  돌렸다. 상자는 끝나면 스스로 지워진다. 운영 DB·운영 파일에는 `archive_plan` (읽기만) 외에는 손대지 않았다 (부록 B)
- 운영 저장소 미리보기 (`archive_plan(0)`, 읽기만): 태스크 80 · 요청 14 · 그래프 24 · 실행 166 · 이벤트 514
  (task 282, ownership 75, queue 70, request 35, graph 18, **rev 12**, slot 12 …) · 핸드오프 57 · 전달 7 (r7~r13) ·
  로그 fleet-mode 38줄 / monitor 0줄. 지금 도는 G-032 의 실행은 0건 걸린다 - **G-032 의 노드 태스크가 보드에 ASSIGNED 로
  있어서일 뿐**이고 그래프가 지켜 주는 것이 아니다 (결함 1)

## 변이 시험 - 22개 중 8개 잡힘

| # | 바꾼 것 | 잡힘 | 잡은 검사 |
| -- | -- | -- | -- |
| M01 | 이벤트: 열린 id 보호 조건(907) 제거 | O | test_events_move_only_when_no_open_id_is_mentioned |
| M02 | 이벤트: 시각 비교 `<=` → `<` (913) | X | - (고정 OLD + `days=0` 이라 경계를 안 밟음) |
| M03 | 이벤트: 파일에 안 쓰고 DB 만 지움 | O | test_events_move_only…, test_rev_unchanged…, test_apply_returns_counts |
| M04 | 이벤트: `missing` 확인 제거 (1077) | X | - |
| M05 | 핸드오프: 12건 상한 → 11 (801) | O | test_newest_12_handoffs_stay_in_db_and_file |
| M06 | 핸드오프: 파일 확인 없이 지움 (1056) | X | - |
| M07 | 실행: `.rc` 없는(도는) 실행 보호 제거 | O | test_running_run_stays_even_for_finished_task |
| M08 | 실행: 열린 태스크 실행 보호(879) 제거 | X | - (그 조건 없이도 열린 태스크 실행은 연결되지 않아 같은 결과 - 보호가 중복이거나 시험이 그 길을 안 밟음) |
| M09 | `_mentions` 뒤 경계 제거 (`T-15` 가 `T-150` 에 걸림) | X | - (`test_no_partial_id_match` 는 본문 `T-90` 에서 `T-900` 을 찾는다 - 경계가 없어도 절대 안 걸리는 방향이라 **빈 검사**) |
| M10 | `_mentions` 앞 경계 제거 | X | - |
| M11 | 열린 그래프 id 보호 제거 | X | - (그래프 시험 없음) |
| M12 | 열린 요청 id 보호 제거 | X | - (요청 시험 없음) |
| M13 | 전달: 남은 그래프 라운드 보호 제거 | X | - (전달 기록 시험 없음) |
| M14 | 로그: apply 시각 `<=` → `<` | X | - |
| M15 | 로그 대상에 `access.log` 추가 | O | test_logs_move_only_old_timestamped_lines |
| M16 | 로그: 줄 수 확인 제거 | X | - |
| M17 | 실행: DB `runs` 행을 안 지움 | O | test_finished_task_runs_move_with_it |
| M18 | 실행: 끝난 그래프 노드 실행 연결 제거 | X | - |
| M19 | 아카이브가 `meta.rev` 를 +1 | O | test_rev_unchanged_and_archive_event_written |
| M20 | 태스크: `status IN (DONE, ASSIGNED, TODO)` 도 내림 | X | - (**열린 태스크 행이 보드에서 지워져도 초록**) |
| M21 | 이벤트: `kind=rev` 를 시각 무관하게 언제나 내림 | X | - |
| M22 | `cmd_archive`: `--dry-run` 무시 | O | test_archive_dry_run_changes_nothing 외 2 |

기준선: 변이 없이 115개 모두 통과. 잡히지 않은 14개는 아래 "검사의 구멍" 결함(13)으로 묶었다.
M04·M06·M16 은 정상 경로에서 결과가 같은 "안전장치" 변이라, 쓰기 실패를 주입하는 시험이 있어야 잡힌다.

## 결함 목록 (13건)

| 번호 | 위치 | 무엇이 잘못되나 | 재현 | 심각도 |
| -- | -- | -- | -- | -- |
| 1 | `tools/aimem_db.py:876-889`, 796 | **도는 그래프의 실행·태스크·이벤트가 내려간다.** `graph_run_ids` 는 *정리되는* 그래프에서만 모으고, 열린 그래프의 `attempts[].run_id` 를 지키는 집합이 없다. 노드 태스크가 보드에 없으면 (`task not in task_status`) 시각 규칙으로, 보드에서 DONE 이면 태스크 연결로 실행이 옮겨진다. 그 태스크 행과 그 태스크만 가리키는 이벤트도 함께 간다 | 부록 B S1: 열린 G-1 (노드 T-2 running) 의 끝난 노드 T-1 (보드 DONE) · T-3 (보드에 없음) → `실행 내림 ['T-1-S1-a1','T-3-S1-a1']`, `태스크 내림 ['T-1']`, "T-1 DONE 보고"·"T-3 노드 끝남" 이벤트 내려감 | **높음** - 요청이 명시한 "도는 그래프와 그것이 가리키는 기록" 위반. 운영에서는 관리자가 보드 태스크를 DONE 으로 바꾸는 순간 `--days 0` 정리로 G-032 같은 그래프의 기록이 빠진다 |
| 2 | `tools/aimem_db.py:1138-1140` + `tools/aimem_monitor/monitorctl.sh:62` | **`monitor.log` 를 `os.replace` 로 갈아 끼운다.** 서버는 `>>"$LOG"` 로 연 fd 를 쥐고 있어서, 교체 뒤 서버가 쓰는 줄은 모두 지워진 옛 inode 로 가고 재시작 전까지 **영영 사라진다**. 읽기(1112)와 교체(1140) 사이에 덧붙은 줄도 잃는다 (`fleet-mode.log` 도 같다) | S7: fd 를 연 채로 정리 → 그 뒤 쓴 "401 줄" 이 `monitor.log` 에 없음 (`False`) | **높음, 잠복** - 지금 `monitor.log` 줄에 시각이 없어 0줄이라 교체가 안 일어난다. 시각을 찍는 요청이 들어가는 날부터 터진다. 큐 3번이 말하듯 401 은 monitor.log 에만 남는다 |
| 3 | `tools/aimem_db.py:988-994` (태스크), 1072-1079 (이벤트), 1129-1140 (로그) | **중간에 죽은 뒤 다시 돌리면 두 번 적힌다.** 셋 다 "덧붙이고 → 들어갔나 확인 → 원본 지우기" 이고 "이미 들어 있나" 를 보지 않는다. 이벤트는 태스크 표의 `missing` 확인과 **같은 수준** (둘 다 약하다); 핸드오프만 `line not in old` 로 거른다 | S5: DELETE 직전 예외 → 재실행 → `board-2026-01.md` 에 `T-1` 2번, `events-2026-01.md` 에 `[#1]` 2번, 로그 아카이브에 옛 줄 2번 | 중간 - 손실은 아니고 중복. 반대 방향 (DB 만 지워지고 파일에 없음) 은 이벤트·태스크·로그에서는 못 만들었다 |
| 4 | `tools/aimem_db.py:1027-1037` | **실행 파일을 옮기다 죽으면 고아가 남는다.** 이름순이라 `.json` 이 `.out`·`.rc` 보다 먼저 가고, 다음 계획은 `runs/*.json` 에서 시작하므로 그 실행을 다시 못 찾는다. DB `runs` 행도 남는다 (DELETE 는 모두 옮긴 뒤 한 번) | S5 끝: 3번째 `replace` 에서 OSError → `runs/` 에 `T-1-S1-a1.out`, `.rc` 고아, 다음 계획 실행 `[]`, DB 행 `('T-1-S1-a1','done')` | 중간 - 함대 탭에 파일 없는 실행이 영구히 보이고, 아카이브 쪽 실행은 반쪽 |
| 5 | `tools/aimem_db.py:805-817`, 898-900 | **"열린 것" 집합이 모자란다.** 열린 요청은 *요청 파일*로만 정한다 (`request set` 을 `--project` 없이 쓰면 파일이 없다). **대기 큐** 항목은 아예 안 본다 | S4: DB 에만 있는 IN-PROGRESS `Q-OPEN` 과 끝난 T-1 을 함께 가리키는 이벤트 → 내려감. S3: 큐에 남은 "T-300 다음 할 일" 의 `queue +1` 이벤트 → 내려감. 운영 미리보기에서도 큐 2·3번의 `queue +2`/`+3` 이벤트 (#534, #535) 와 큐 2·3번이 가리키는 T-157 이벤트가 걸린다 | 중간 - 옮겨질 뿐 지워지지는 않지만, 열린 일의 기록이 DB·보드·state 에서 사라진다 |
| 6 | `tools/aimem_db.py:916-946` | **전달 기록 보호가 그래프 `round` 키의 정수 일치에만 기댄다.** 그래프가 아직 안 생긴 라운드, `round` 가 문자열인 그래프, `round` 키가 없는 그래프의 라운드는 열려 있어도 `r<N>.*` 가 옮겨진다 | S12: 그래프 없는 r20, 도는 G-9 (`round:"21"`) 의 r21 → `옮긴 라운드: [20, 21]` | 중간 - 라운드 시작 직후 "지금 끝난 것 전부" 를 누르면 그 라운드의 지시·로그가 빠진다 |
| 7 | `tools/aimem_db.py:1074-1075` | **이벤트 아카이브가 `rev` 칸을 버리고 줄바꿈을 공백으로 편다.** 아카이브 줄로 원래 행을 되만들 수 없고, `migrate` 도 이것을 다시 읽지 않는다 | S6: `rev=150`, 본문 두 줄 → `- \`2026-01-01T00:00:00\` [#1] t · task · T-1 첫줄 둘째줄`, `150` 없음 | 낮음~중간 - "지우지 않고 옮긴다" 의 원칙이 한 칸만큼 깨진다 |
| 8 | `tools/aimem_db.py:1049`, 1056 (같은 꼴 122) | **핸드오프 확인이 부분 문자열이다** (`line in text`). 이미 적힌 다른 줄의 앞부분인 줄은 "들어 있다" 로 판정되어 **쓰지 않고 DB 에서 지운다.** 계획은 최신 먼저라 긴 줄이 먼저 적힌다 | S10: "…작업 12" 가 먼저 적히고 "…작업 1" 은 안 적힌 채 seq 1 도 내려감 → `'작업 1' 줄 그대로 있나: False` | 중간 - **실제 손실 경로** (드물다) |
| 9 | `tools/aimem_db.py:997`, 1083 | **계획과 실행 사이를 다시 확인하지 않는다.** DELETE 에 `AND status='DONE'` 같은 재확인이 없어, 그 사이 다시 열린 태스크도 지운다 | S11: 계획 뒤 T-1 을 ASSIGNED 로 → 적용 → `DB 에 남았나: False` | 낮음 - 창은 짧지만 실행 수백 개를 옮기는 동안 열려 있다 |
| 10 | `tools/aimem_db.py:142-157` (`_import_handoff_entries`) | **DB 를 잃고 `migrate` 하면 본문에 `**REV N` 이 없는 핸드오프의 rev 가 None 이 되어 맨 아래로 가라앉는다.** 그러면 `handoff.md` ≠ DB 렌더가 되어 `HANDOFF_SNAPSHOT_STALE` 이 바로 뜨고, 다음 `handoff add` 에서 **잃기 전 가장 새 항목이 창 밖으로 밀려나** 아카이브가 DB 에서 내린다. 원인은 예전부터 있었고, 아카이브가 "내보내기" 를 "DB 에서 내리기" 로 키웠다 | S9: `migrate 뒤 handoff.md 와 DB 렌더 같음: False` | 낮음~중간 |
| 11 | `tools/aimem_db.py:1077` | **`[#seq]` 확인은 DB 세대를 모른다.** DB 를 잃고 새로 만들면 seq 가 1부터 다시 나와, 옛 세대가 남긴 `[#12]` 가 이번 쓰기가 실패해도 "들어갔다" 로 통과시킨다 | 코드 읽기 (재현기 없음) | 낮음 |
| 12 | `archive_apply` 끝 (1144-1165) | **정리 뒤 `render` 를 안 부른다.** `AIMEM-state.md` 는 최근 이벤트 50개 (`state_dict` 488) 를 담으므로 이벤트를 내리면 바로 낡고, 린터의 STATE_SNAPSHOT 검사가 걸린다. 태스크만 내리던 때부터 있던 것이 이벤트로 넓어졌다 | 코드 읽기 | 낮음 |
| 13 | `tests/test_aimem_db_cli.py` `ArchiveAttachedRecordsTest`, `tests/test_archive_api.py` | **검사의 구멍: 변이 22개 중 14개가 살아남는다.** 그래프·요청·큐·전달 보호, 경계 일치, 시각 경계, 쓰기 실패 주입, 열린 태스크 행 보호 (M20) 를 보는 시험이 없다. `test_no_partial_id_match` 는 방향이 거꾸로라 아무것도 재지 않는다 | 위 변이 표 | 중간 - 결함 1·5·6 이 초록 아래 숨어 있었다 |

### 확인했고 문제없던 것

- **열린 태스크 vs 끝난 태스크를 함께 가리키는 이벤트**: 열린 쪽이 이긴다 (907 이 909 보다 먼저). S2 "T-15 와 T-150 비교" 는 남는다
- **경계**: `T-15`/`T-150`, `Q-261111-663d`/`Q-261111-663d-1`, `G-3`/`G-30` 모두 맞게 갈렸다 (이벤트·실행 파일·그래프 부속 파일·inputs). 실행 파일은 `"<id>."` 접두로 고르고 run id 는 `T-15-S1-a1` 꼴이라 `T-150-…` 을 끌고 가지 않는다 (S2 남은 파일 목록)
- **도는 실행** (`.rc` 없음) 은 어떤 길로도 안 내려간다 (M07 이 잡힘, S1 의 T-2 실행 남음)
- **최신 핸드오프 12건**: `--days 0` 에서도 12건이 남고 `handoff.md` 도 12건, `HANDOFF_SNAPSHOT_STALE` 안 뜸, `handoff add --bump --expect-rev 157` → `(158, 1)` (S9)
- **REV**: `meta.rev` 는 그대로다. `events(kind=rev)` 12건은 `--days 0` 에서 내려가지만 (운영 미리보기) `rev()` 는 `meta` 만 읽고 REV 를 올리는 두 길 (`event --bump`, `handoff add --bump`) 도 `meta` 만 쓴다. 요청이 "어느 작업에도 딸리지 않은 이벤트는 시각 규칙" 이라 했으므로 의도대로다
- **`access.log`**: 아카이브는 한 글자도 바꾸지 않는다 (S8, 바이트 같음). 웹 경로는 `_audit` 로 한 줄 **덧붙일** 뿐이다
- **DB 를 잃은 뒤 `migrate`**: REV (AIMEM.md 서문 씨앗) · 최신 12 핸드오프 (`handoff.md`) · 남은 요청·그래프·실행 파일이 돌아오고, `handoff add --bump --expect-rev` 도 돈다 (S9: `(159, 1)`). **영영 DB 로 안 돌아오는 것**: 아카이브된 이벤트 (`events-*.md` 를 다시 읽는 길이 없다), 태스크 (`board-*.md`), `archive/runs-*` 의 실행, 13번째부터의 핸드오프. 이벤트·12건 밖 핸드오프는 이 기능 전에도 DB 를 잃으면 돌아오지 않았으므로 "그 길은 그대로" 라는 요구는 **지켜진다**. 단 결함 10 이 그 길의 순서를 비튼다

## 결론 - 새 권한·새 손실 경로

**새 권한은 없다.** `/api/archive` 는 그대로 운영 저장소 전용·인증·CSRF 뒤에 있고 `days` 는 0~3650 정수로 묶인다.
다만 같은 단추 한 번이 이제 태스크·요청·그래프뿐 아니라 실행 166건, 이벤트 514건, 로그 줄까지 옮기며,
웹에서 `days=0` ("지금 끝난 것 전부") 을 고를 수 있다. **새 손실 경로는 셋이다.**
(1) 서버가 열어 둔 `monitor.log` 의 교체 (결함 2, 잠복이지만 되돌릴 수 없음).
(2) 부분 문자열 확인 때문에 쓰지 않고 지우는 핸드오프 (결함 8).
(3) 이벤트 아카이브에서 떨어지는 `rev` 칸 (결함 7).
**보호 범위의 구멍도 셋이다.** 도는 그래프의 실행·이벤트 (결함 1), DB 에만 있는 열린 요청과 대기 큐 (결함 5),
그래프 없는 라운드의 전달 기록 (결함 6). 이것들은 지워지지 않고 `archive/` 로 옮겨지므로 손으로 되돌릴 수는 있다.
하지만 "열린 것에 딸린 기록은 남는다" 는 약속을 어기고, 검사 22개 변이 중 14개가 초록이라 그 어김이 보이지 않았다.
**결함 1·2 를 고치기 전에는 운영에서 `--days 0` 정리를 누르지 않기를 권한다.**

## 고치는 방법 (한 줄씩)

1. 열린 그래프의 모든 `attempts[].run_id` 와 노드 id 를 `open_ids`·보호 실행 집합에 넣고, 열린 그래프의 노드 태스크는 보드에서도 내리지 않는다
2. 로그는 `os.replace` 대신 "아카이브에 쓰고 → 원본을 같은 inode 에서 잘라 남은 줄만 다시 쓰기" 또는 로그 회전 신호로 하고, `monitor.log` 는 서버가 쥔 동안 건너뛴다
3. 태스크·이벤트·로그도 덧붙이기 전에 "이미 그 줄이 있나" 를 보아 멱등으로 만든다 (핸드오프와 같은 수준)
4. 실행 파일은 `.json` 을 **맨 마지막**에 옮기고, 다음 계획이 `.rc`/`.out` 고아도 줍게 한다
5. `open_ids` 에 DB `requests` 의 열린 상태와 `queue.task` 에서 뽑은 id 를 더한다
6. 전달 보호를 `str(round)` 비교로 바꾸고, 열린 라운드 (`relay r<N>.json` 의 상태나 최신 라운드) 는 언제나 남긴다
7. 이벤트 아카이브를 `.jsonl` (모든 칸 그대로) 로 쓴다
8. 핸드오프 확인을 부분 문자열이 아닌 "줄 단위 일치" 로 바꾼다 (122 행도)
9. DELETE 에 계획 때의 조건 (`status='DONE'` 등) 을 다시 건다
10. `_import_handoff_entries` 가 rev 를 못 읽으면 앞뒤 항목에서 이어받거나 파일 순서로 seq 를 매긴다
11. 이벤트 확인 표식에 seq 와 함께 `at` 을 넣는다
12. 정리 끝에 `render` (state 스냅샷) 를 부른다
13. 위 S1·S3·S4·S6·S10·S12 와 M02/M09/M14/M20 을 그대로 단위 시험으로 옮긴다 (`test_no_partial_id_match` 는 본문 `T-9000` + 정리 대상 `T-900` 꼴로 바꾼다)

## 부록 A. 변이 실행기

```python
# === RUNNER mut ===
import sys, types, unittest, io, importlib, pathlib, contextlib
ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
SRC = (ROOT / "tools" / "aimem_db.py").read_text(encoding="utf-8")
M = [
 ("M01 이벤트: 열린 것 보호 조건 제거", 'if any(_mentions(body, ident) for ident in open_ids):', 'if False:'),
 ("M02 이벤트: 시각 비교 <= -> <", 'if str(e["at"] or "") <= cutoff:', 'if str(e["at"] or "") < cutoff:'),
 ("M03 이벤트: 파일에 안 쓰고 DB 만 지움", "fh.write(f\"- `{e.get('at')}` [#{e.get('seq')}]", "(lambda *_: 0)(f\"- `{e.get('at')}` [#{e.get('seq')}]"),
 ("M04 이벤트: missing 확인 제거", "missing = [e[\"seq\"] for e in events if f\"[#{e['seq']}]\" not in text]", "missing = []"),
 ("M05 핸드오프: 12건 상한 -> 11", 'for row in _handoff_rows(con)[HANDOFF_MAX:]:', 'for row in _handoff_rows(con)[HANDOFF_MAX - 1:]:'),
 ("M06 핸드오프: 확인 없이 지움", '            if line in text:\n                confirmed.append(h["seq"])', '            confirmed.append(h["seq"])'),
 ("M07 실행: .rc 없는(도는) 실행 보호 제거", 'if not (run_dir / f"{rid}.rc").exists():\n                continue', 'pass'),
 ("M08 실행: 열린 태스크 실행 보호 제거", 'task_status[task] != "DONE":\n                continue', 'task_status[task] != "DONE":\n                pass'),
 ("M09 _mentions: 뒤 경계 제거 (T-15 가 T-150 에 걸림)", 're.escape(ident) + r"(?![0-9A-Za-z-])"', 're.escape(ident) + r""'),
 ("M10 _mentions: 앞 경계 제거", 'r"(?<![0-9A-Za-z-])" + re.escape(ident)', 're.escape(ident)'),
 ("M11 열린 그래프 id 보호 제거", 'open_ids.update(open_graph_ids)', 'pass'),
 ("M12 열린 요청 id 보호 제거", 'open_ids.update(open_request_ids)', 'pass'),
 ("M13 전달: 남은 그래프 라운드 보호 제거", 'if n in remaining_graph_rounds:\n                continue', 'pass'),
 ("M14 로그: apply 시각 비교 <= -> <", 'if m and _iso(line[:19]) <= plan["cutoff"]:', 'if m and _iso(line[:19]) < plan["cutoff"]:'),
 ("M15 로그: access.log 를 대상에 추가", '(ROOT / ".aimem" / "monitor.log", ROOT / ".aimem" / "fleet-mode.log")', '(ROOT / ".aimem" / "monitor.log", ROOT / ".aimem" / "fleet-mode.log", ROOT / ".aimem" / "access.log")'),
 ("M16 로그: 줄 수 확인 제거", 'if after <= before:', 'if False:'),
 ("M17 실행: DB runs 행을 안 지움", 'con.execute(f"DELETE FROM runs WHERE id IN', '0 and con.execute(f"DELETE FROM runs WHERE id IN'),
 ("M18 실행: 그래프 노드 실행 연결 제거", 'if rid in graph_run_ids:\n                attached = True', 'pass'),
 ("M19 아카이브가 meta.rev 를 +1", '(_now(), actor, rev(con), "archive", body))', '(_now(), actor, rev(con), "archive", body)); con.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key=\'rev\'")'),
 ("M20 태스크: DONE 아닌 것도 내림", "\"WHERE status='DONE' AND COALESCE", "\"WHERE status IN ('DONE','ASSIGNED','TODO') AND COALESCE"),
 ("M21 이벤트: kind=rev 를 언제나 내림", 'if e["kind"] == "handoff":\n                continue', 'if e["kind"] == "handoff":\n                continue\n            if e["kind"] == "rev":\n                plan["events"].append(dict(e)); continue'),
 ("M22 cmd_archive: --dry-run 무시", '    if a.dry_run:\n        return 0\n    try:\n        out = archive_apply', '    try:\n        out = archive_apply'),
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
for k, a, b in M:
    c = SRC.count(a)
    if c < 1:
        print(k, "| PATTERN-NOT-FOUND"); continue
    n, f = run(SRC.replace(a, b))
    print(k, "| 자리", c, "|", "O" if f else "X", "|", ", ".join(x.split(".")[-1] for x in f))
# === END ===
```

## 부록 B. 시나리오 재현기

```python
# === RUNNER scen ===
import sys, json, pathlib, tempfile, contextlib, io, os, sqlite3
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
def req(root, rid, st): (root / ".aimem" / "requests" / (rid + ".json")).write_text(json.dumps({"id": rid, "status": st, "created": OLD, "updated": OLD}), encoding="utf-8")
def apply0():
    p = A.archive_plan(0)
    with contextlib.redirect_stdout(io.StringIO()):
        o = A.archive_apply(p, "t")
    return p, o
def alive(seq): return bool(sql("SELECT 1 FROM events WHERE seq=?", seq))

print("== S1 도는 그래프의 끝난 노드: 태스크·실행·이벤트")
with box() as root:
    task("T-1", "DONE"); task("T-2", "ASSIGNED")
    graph(root, "G-1", [{"id": "T-1", "status": "done", "attempts": [{"run_id": "T-1-S1-a1"}]},
                        {"id": "T-3", "status": "done", "attempts": [{"run_id": "T-3-S1-a1"}]},
                        {"id": "T-2", "status": "running", "attempts": [{"run_id": "T-2-S1-a1"}]}], rnd=14)
    run(root, "T-1-S1-a1", "T-1"); run(root, "T-3-S1-a1", "T-3"); run(root, "T-2-S1-a1", "T-2", rc=False)
    e1 = ev("T-1 DONE 보고"); e3 = ev("T-3 노드 끝남"); eg = ev("G-1 진행 중 T-1 done")
    p, o = apply0()
    print(" 태스크 내림", o["tasks"], "| 실행 내림", sorted(o["runs"]), "| 이벤트 T-1만 내려감", not alive(e1), "T-3만 내려감", not alive(e3), "G-1 언급 남음", alive(eg))

print("== S2 경계 T-15/T-150, Q-..663d/Q-..663d-1, G-3/G-30")
with box() as root:
    task("T-15", "DONE"); task("T-150", "TODO")
    run(root, "T-15-S1-a1", "T-15"); run(root, "T-150-S1-a1", "T-150")
    req(root, "Q-261111-663d", "DONE"); req(root, "Q-261111-663d-1", "NEW")
    graph(root, "G-3", [{"id": "T-15", "status": "done"}], rnd=3, side=("G-3.log", "G-3-T-15-a1.task.md"))
    graph(root, "G-30", [{"id": "T-150", "status": "running"}], rnd=30, side=("G-30.log", "G-30-T-150-a1.task.md"))
    (root / ".aimem" / "graph" / "inputs" / "G-3-a.md").write_text("x"); (root / ".aimem" / "graph" / "inputs" / "G-30-a.md").write_text("x")
    a = ev("T-150 진행"); b = ev("T-15 끝"); c = ev("Q-261111-663d-1 진행"); d = ev("Q-261111-663d 끝"); e = ev("G-30 진행"); f = ev("G-3 끝"); g = ev("T-15 와 T-150 비교")
    p, o = apply0()
    left = sorted(x.name for x in (root / ".aimem").rglob("*") if x.is_file() and "archive" not in x.parts and x.suffix != ".db" and not x.name.endswith(("-wal", "-shm")))
    print(" 남은 이벤트(열린 쪽):", [alive(x) for x in (a, c, e, g)], "내려간(끝난 쪽):", [not alive(x) for x in (b, d, f)])
    print(" 남은 파일:", left)

print("== S3 대기 큐에 있는 일의 이벤트")
with box() as root:
    sql("INSERT INTO queue(pos,task) VALUES(1,'T-300 다음 할 일')")
    s = ev("queue +1 T-300 다음 할 일", kind="queue")
    apply0(); print(" 큐에 남은 일의 이벤트가 내려감:", not alive(s), "| 큐 행:", [tuple(r) for r in sql("SELECT pos,task FROM queue")])

print("== S4 DB 에만 있는 열린 요청 (요청 파일 없음, CLI request set)")
with box() as root:
    task("T-1", "DONE"); sql("INSERT INTO requests(id,status,created) VALUES('Q-OPEN','IN-PROGRESS',?)", OLD)
    s = ev("T-1 은 Q-OPEN 의 첫 단계")
    apply0(); print(" 열린 요청을 가리키는 이벤트가 내려감:", not alive(s))

print("== S5 중간에 죽으면 (DELETE 직전 예외) 다시 돌릴 때 두 번 적히는가")
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
for prefix, setup, fname, needle in (
        ("DELETE FROM tasks", lambda root: task("T-1", "DONE"), "board-2026-01.md", "| T-1 |"),
        ("DELETE FROM events", lambda root: ev("T-1 끝"), "events-2026-01.md", "[#1]")):
    with box() as root:
        setup(root)
        try:
            with dying(prefix): apply0()
        except Boom: pass
        apply0()
        txt = (root / ".aimem" / "archive" / fname).read_text(encoding="utf-8")
        print(" ", prefix, "뒤 재실행 →", fname, "에", txt.count(needle), "번")
with box() as root:
    log = root / ".aimem" / "fleet-mode.log"; log.write_text("2026-01-01T00:00:00 옛 줄\n", encoding="utf-8")
    orig = os.replace
    def bad(s, d):
        if str(d).endswith("fleet-mode.log"): raise Boom("replace")
        return orig(s, d)
    try:
        with mock.patch.object(A.os, "replace", bad): apply0()
    except Boom: pass
    apply0()
    print("  로그 원본 교체 직전 죽음 뒤 재실행 → 아카이브에", (root / ".aimem/archive/logs-2026-01/fleet-mode.log").read_text(encoding="utf-8").count("옛 줄"), "번")
with box() as root:
    task("T-1", "DONE"); run(root, "T-1-S1-a1", "T-1")
    origr = pathlib.Path.replace; n = [0]
    def badr(self, t):
        n[0] += 1
        if n[0] == 3: raise OSError("disk")
        return origr(self, t)
    try:
        with mock.patch.object(pathlib.Path, "replace", badr): apply0()
    except OSError: pass
    p2 = A.archive_plan(0)
    print("  실행 파일 옮기다 죽음 → runs/ 에 남은 고아:", sorted(x.name for x in (root / ".aimem/runs").iterdir()),
          "| 다음 계획의 실행:", [r["id"] for r in p2["runs"]], "| DB 행:", [tuple(r) for r in sql("SELECT id,state FROM runs")])

print("== S6 이벤트의 rev 칸 / 여러 줄 본문")
with box() as root:
    task("T-1", "DONE"); ev("T-1 첫줄\n둘째줄", kind="task", rev=150)
    apply0(); line = [l for l in (root / ".aimem/archive/events-2026-01.md").read_text(encoding="utf-8").splitlines() if "[#" in l][0]
    print(" ", line, "| '150' 이 남았나:", "150" in line)

print("== S7 monitor.log 를 붙든 서버(>> 로 연 fd)")
with box() as root:
    ml = root / ".aimem" / "monitor.log"; fh = open(ml, "a", encoding="utf-8")
    fh.write("2026-01-01T00:00:00 옛 줄\n"); fh.flush()
    apply0(); fh.write("2099-01-01T00:00:00 아카이브 뒤 401 줄\n"); fh.flush(); fh.close()
    print("  아카이브 뒤 서버가 쓴 줄이 monitor.log 에 있나:", "401" in ml.read_text(encoding="utf-8"))

print("== S8 access.log")
with box() as root:
    acc = root / ".aimem" / "access.log"; acc.write_bytes(b"2026-01-01T00:00:00\tlogin-ok\t1.2.3.4\n"); before = acc.read_bytes()
    (root / ".aimem/monitor.log").write_text("2026-01-01T00:00:00 m\n"); (root / ".aimem/fleet-mode.log").write_text("2026-01-01T00:00:00 f\n")
    task("T-1", "DONE"); ev("T-1"); apply0()
    print("  바이트 같음:", acc.read_bytes() == before)

print("== S9 핸드오프 12건·REV·DB 잃은 뒤 migrate")
with box() as root:
    for i in range(1, 16):
        ev("- `2026-01-%02d 00:00` 관리자: **REV %d** 항목 %02d" % (i, 140 + i, i), kind="handoff", at="2026-01-%02d 00:00" % i, rev=140 + i)
    ev("REV 155: 뭔가", kind="rev", rev=155); task("T-1", "DONE"); ev("T-1 끝")
    with contextlib.redirect_stdout(io.StringIO()): A.handoff_sync()
    p, o = apply0()
    hm = A.HANDOFF.read_text(encoding="utf-8")
    with A.connect() as c: stale = hm != A.render_handoff_text(c)
    print("  핸드오프 DB", sql("SELECT count(*) FROM events WHERE kind='handoff'")[0][0], "| handoff.md 항목", hm.count("\n- `"), "| HANDOFF_SNAPSHOT_STALE?", stale,
          "| meta.rev", sql("SELECT value FROM meta WHERE key='rev'")[0][0], "| kind=rev 이벤트 남음", bool(sql("SELECT 1 FROM events WHERE kind='rev'")))
    print("  handoff add --bump --expect-rev 157 →", A.handoff_add("다음", bump=True, expect_rev=157))
    (root / "AIMEM.md").write_text("- **REV: 158**\n", encoding="utf-8")
    for x in (".aimem/aimem.db", ".aimem/aimem.db-wal", ".aimem/aimem.db-shm"):
        if (root / x).exists(): (root / x).unlink()
    with contextlib.redirect_stdout(io.StringIO()): A.migrate(verbose=False)
    print("  migrate 뒤: rev", sql("SELECT value FROM meta WHERE key='rev'")[0][0], "| 핸드오프", sql("SELECT count(*) FROM events WHERE kind='handoff'")[0][0],
          "| 그 밖 이벤트", sql("SELECT count(*) FROM events WHERE kind!='handoff'")[0][0], "| 태스크", sql("SELECT count(*) FROM tasks")[0][0], "| 실행", sql("SELECT count(*) FROM runs")[0][0])
    with A.connect() as c: print("  migrate 뒤 handoff.md 와 DB 렌더 같음:", A.HANDOFF.read_text(encoding="utf-8") == A.render_handoff_text(c))
    print("  migrate 뒤 handoff add --bump --expect-rev 158 →", A.handoff_add("또", bump=True, expect_rev=158))

print("== S10 핸드오프 줄이 다른 줄의 앞부분일 때")
with box() as root:
    ev("- `2026-01-01 00:00` 관리자: 작업 1", kind="handoff", at="2026-01-01 00:00", rev=1)
    ev("- `2026-01-01 00:00` 관리자: 작업 12", kind="handoff", at="2026-01-01 00:00", rev=2)
    for i in range(12): ev("- `2026-02-01 00:00` 관리자: 새 %d" % i, kind="handoff", at="2026-02-01 00:00", rev=10 + i)
    p, o = apply0()
    arch = (root / ".aimem/archive/handoff-2026-01.md").read_text(encoding="utf-8").splitlines()
    print("  내린 seq", o["handoff"], "| 아카이브 줄:", [l for l in arch if l.startswith("- ")], "| '작업 1' 줄 그대로 있나:", "- `2026-01-01 00:00` 관리자: 작업 1" in arch)

print("== S11 계획과 실행 사이에 다시 열린 태스크")
with box() as root:
    task("T-1", "DONE"); p = A.archive_plan(0); sql("UPDATE tasks SET status='ASSIGNED' WHERE id='T-1'")
    with contextlib.redirect_stdout(io.StringIO()): A.archive_apply(p, "t")
    print("  다시 열린 T-1 이 DB 에 남았나:", bool(sql("SELECT 1 FROM tasks WHERE id='T-1'")))

print("== S12 전달 기록: 그래프 아직 없는 라운드 / round 가 문자열")
with box() as root:
    (root / ".aimem/relay/r20.json").write_text(json.dumps({"round": 20, "at": OLD})); (root / ".aimem/relay/r20.log").write_text("x")
    graph(root, "G-9", [{"id": "T-9", "status": "running"}], rnd="21")
    (root / ".aimem/relay/r21.json").write_text(json.dumps({"round": 21, "at": OLD}))
    p, o = apply0(); print("  옮긴 라운드:", o["relay"], "(r21 은 도는 그래프 G-9 의 라운드)")
# === END ===
```
