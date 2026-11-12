# R22 3차 재검수 (T-271, S1, G-054) - R22-R1·R2 가 닫혔는가

- 대상: 작업 트리의 미커밋 수정, REV 164 위. T-270 이 고친 곳은 `tests/test_fleet_graph.py` 의 `_session` 도우미(`fleet_rt.harness.get` 을 claude 어댑터로 패치)와 `test_q1_run_id_with_path_segments_is_none`(디딤 폴더를 만듦)
- 방법: `/tmp/r22c-review` 사본을 만들었습니다(`python3 shutil.copytree`, `.git`·`__pycache__` 와 `.aimem/{tls,runs,sessions}` 제외). 고친 세 파일은 md5 로 저장소와 같음을 확인했습니다.
  변이는 `/tmp/r22c-tools/mut.py` 로 했습니다(조각 하나 교체 → 시험 → 복원). `full` 은 사본에서 `python3 -m unittest discover -s tests` 전체를, `quick` 은 `import _fleet_env` 뒤 `test_fleet_graph`·`test_rt_claude` 를 돌립니다.
  끝난 뒤 두 `/tmp` 폴더는 지웠습니다. 저장소에서 쓴 파일은 이 보고서 하나입니다.
- 기준선: 사본 전체 `python3 -m unittest discover -s tests` → **`Ran 940 tests in 134.608s` / `OK (skipped=3)`**. 2차에는 `FAILED (failures=1)` 였습니다.
  건너뛴 3건: `test_good_cert_builds_context` 는 원래부터 건너뜁니다. `test_read_only_before_after`·`test_real_record_reads_rc_and_report` 는 `실제 기록 없음: 20261109-172618-S3` 때문인데, 사본에서 `.aimem/runs` 를 뺐기 때문입니다. 2차의 `skipped=1` 과 다른 까닭이 이것이고, 이번 수정과는 무관합니다.

## 1. 닫힘표

| 번호 | 닫혔나 | 근거 |
| --- | --- | --- |
| R1 (Q2 세션 시험이 전체 discover 에서 fake 로 감) | 닫힘 | 전체 discover 가 초록입니다(940 OK). `test_q2_session_branch_429_is_true` 는 `self.harness_get.assert_called_once_with("claude")` 로 패치가 실제로 탔음을 단언합니다. 전체 discover 에서 V21 은 `test_q2_session_branch_429_is_true` 로, W01 은 `test_q2_session_branch_n3_record_is_none` 으로 빨개집니다. 그러니 n3 시험은 이제 claude 어댑터를 탑니다. fake 는 `None` 을 돌려주므로 이 시험이 fake 로 갔다면 W01 에서도 통과했을 것입니다. 남은 약점 1건은 아래 S1 |
| R2 (Q1 반례에 디딤 폴더 없음) | 닫힘 | 이제 시험이 `sessions/T-1-S1-a1-000000/` 와 `outside/evil/{meta.json,events.jsonl(429)}` 를 만듭니다. 그리고 "경로가 실제로 풀린다"(`(root/bad/"meta.json").exists()`, `fleet._session_dir(bad) is not None`)와 "같은 장치로 `True` 가 날 수 있다"(정상 id → `True`)를 먼저 단언합니다. 전체 discover 에서 V08 은 `test_q1_... (run_id='T-1-S1-a1-000000/../../outside/evil')` FAIL 로 잡힙니다 |
| 패치 범위 (fake 안전 장치) | 문제 없음 | `AIFLEET_HARNESS` 는 건드리지 않습니다(grep: 환경 패치 0건). `get` 패치는 `mock.patch(...).start()` + `addCleanup(stop)` 이라 시험 하나 안에서만 삽니다. 실측: 사본에서 `_fleet_env` 를 들이고 Q1·Q2 시험 4건을 돌린 뒤 확인했습니다. `H.get is orig` → `True`, `AIFLEET_HARNESS` → `fake`, `get("claude"/"codex"/"opencode")` → 모두 `fleet_rt.harness.fake`. 시험 안에서 claude 어댑터로 부르는 것은 `limit_signal`(파일 읽기)뿐이고, 이 시험들은 spawn·probe 를 부르지 않습니다. 따라서 진짜 하네스가 뜰 길은 없습니다 |

## 2. 새 결함표

| 번호 | 심각도 | 무엇이 | 어디 | 재현 | 고칠 방향 |
| --- | --- | --- | --- | --- | --- |
| S1 | 낮음 | `test_q2_session_branch_context_window_text_is_not_true` 가 여전히 `assertIsNot(..., True)` 입니다. claude 어댑터는 이 기록에 `None` 을 돌려주므로 `None`→`False` 로 바뀌어도 이 시험은 통과합니다(W01 에서 이 시험은 빨개지지 않았습니다). 2차 R1 의 "고칠 방향"이 제안한 `assertIsNone` 은 반영되지 않았습니다. 다만 같은 되돌림을 n3 시험이 잡으므로, 지금 살아남는 변이는 없습니다 | `tests/test_fleet_graph.py` `test_q2_session_branch_context_window_text_is_not_true` | W01 full: 이 시험은 FAIL 목록에 없음 | `assertIsNone` 으로 좁히기 (선택) |
| S2 | 정보 | 어댑터 `limit_signal` 의 `except Exception: return None` 을 `False` 로 바꾼 변이(W01b)는 살아남습니다. 그 갈래(사건 읽기 예외)를 타는 시험이 없기 때문입니다. `_events` 가 자체적으로 예외를 삼킨다면 사실상 죽은 갈래입니다. R1·R2 범위 밖이라 합계에서 뺐습니다 | `tools/fleet_rt/harness/claude.py` `limit_signal` | `mut.py W01b quick` → 105 OK | 필요하면 `_events` 를 예외로 패치하는 시험 하나 |

R1·R2 범위 안의 새 결함은 없습니다.

## 3. 변이표

모두 **전체 discover**(사본, `python3 -m unittest discover -s tests`) 기준입니다. 단, 범위 밖 참고용인 W01c 는 `quick`(`_fleet_env` 를 먼저 들인 뒤 두 모듈)으로 돌렸습니다.

| 변이 | 잡혔나 |
| --- | --- |
| V08 `_RUN_ID_RE` 몸에 `/` 허용 (`[A-Za-z0-9._/-]*`) | ○ `test_q1_run_id_with_path_segments_is_none (run_id='T-1-S1-a1-000000/../../outside/evil')` - 940 중 FAIL 1 |
| V21 `run_limit_signal` 세션 갈래 끄기 (`if sd is not None:` → `if False:`) | ○ `test_q2_session_branch_429_is_true`, `test_q1_...` - FAIL 2 |
| W01 어댑터 끝 `return result_limit_signal(res, evs)` → `... or False` | ○ `test_q2_session_branch_n3_record_is_none`, rt_claude `test_other_error_none`·`test_error_without_marker_even_with_limit_text_is_none` - FAIL 3 |
| (참고) W01c 어댑터 `res is None` → `return False` | ○ rt_claude `test_none_without_result` (quick) |

합계 3개: 잡힘 3, 생존 0

(범위 밖 W01b 는 생존했습니다. 위 S2 를 보십시오. 합계에 넣지 않았습니다.)

## 4. 총평

R22-R1·R2 는 **닫혔습니다.** 프로젝트의 정식 명령 `python3 -m unittest discover -s tests` 로 사본에서 940개가 초록입니다(건너뜀 3은 사본에 `.aimem/runs` 를 뺀 탓). 2차 때 전체 discover 에서 빨갛거나 아무것도 재지 않던 Q2 세션 시험은 이제 `fleet_rt.harness.get` 패치로 claude 어댑터를 탑니다. 그 증거로 `assert_called_once_with("claude")` 가 통과하고, 전체 discover 아래에서 V21·W01 이 각각 Q2 시험으로 잡힙니다. Q1 시험은 디딤 폴더와 바깥 `outside/evil` 을 실제로 만듭니다. 그리고 경로가 풀린다는 것을 먼저 단언하므로, V08 이 전체 discover 에서 잡힙니다. 패치는 `get` 하나만, 시험 하나 동안만 바꿉니다. `AIFLEET_HARNESS=fake` 는 그대로이고, 시험이 끝나면 `get` 은 원래 함수로 돌아와 모든 이름에 fake 를 줍니다(실측). 그러니 진짜 하네스가 뜰 길은 생기지 않았습니다. 남은 것은 낮음 1건(S1: context-window 시험이 `assertIsNot True` 라 단독으로는 `None`→`False` 를 못 잡음, 다른 시험이 대신 잡음)과 범위 밖 정보 1건(S2)뿐입니다. 커밋을 막을 결함은 아닙니다.
