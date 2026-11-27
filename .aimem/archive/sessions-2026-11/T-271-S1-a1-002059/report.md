DONE

R22-R1 and R22-R2 are both closed. In a copy of the repo, the full `python3 -m unittest discover -s tests` passes, and all three mutations fail it.

**What I did**
- Confirmed the slot: `python3 tools/aimem_db.py check --slot S1 --token a41f0c --rev 164` → `일치: S1 토큰 a41f0c 하네스 claude 모델 opus REV 164`. The allowed write paths include `rounds/R22/REVIEW-r22-3.md`.
- Copied the repo to `/tmp/r22c-review`, leaving out `.git`, `__pycache__` and `.aimem/{tls,runs,sessions}`. The three changed files have the same md5 in the copy and the repo.
- Ran the mutations with a script at `/tmp/r22c-tools/mut.py`. It swaps in one code change, runs the tests, then puts the original back.
- Removed both `/tmp` folders when done (checked: both gone).

**Changed files:** `rounds/R22/REVIEW-r22-3.md` only (new). No product or test code was touched.

**Verification run (all in the copy)**

| Run | Result |
|---|---|
| Baseline, full discover | `Ran 940 tests in 134.608s`, `OK (skipped=3)` (in the 2nd review it was `FAILED (failures=1)`) |
| V08 (`/` allowed inside `_RUN_ID_RE`), full | FAIL 1: `test_q1_run_id_with_path_segments_is_none (run_id='T-1-S1-a1-000000/../../outside/evil')` |
| V21 (session branch turned off), full | FAIL 2: `test_q2_session_branch_429_is_true`, `test_q1_...` |
| W01 (adapter end `... or False`), full | FAIL 3: `test_q2_session_branch_n3_record_is_none`, `test_other_error_none`, `test_error_without_marker_even_with_limit_text_is_none` |

- **Mutation total:** 3 run, 3 caught, 0 survived.
- **Patch scope:** I ran the four Q1/Q2 tests in one process with `_fleet_env` loaded first. Afterwards `fleet_rt.harness.get` was the original function again. `AIFLEET_HARNESS` was still `fake`, and `get("claude"/"codex"/"opencode")` all returned the `fake` adapter. No test changes the environment (checked with grep). Inside these tests the real claude adapter is only used for `limit_signal`, which just reads files, so no real harness can start.
- **Skipped 3 instead of 1:** two of the skips say `실제 기록 없음: 20261109-172618-S3`. They happen because I left `.aimem/runs` out of the copy, not because of this fix.

**For the next owner**
- **S1 (low):** `test_q2_session_branch_context_window_text_is_not_true` still uses `assertIsNot(..., True)`. On its own it would not notice a change from `None` to `False`. The n3 test catches that change instead, so nothing survives today. Switching it to `assertIsNone` is optional.
- **S2 (info, outside this task):** one extra mutation survives — changing the adapter `limit_signal`'s `except Exception: return None` to `return False`. No test reaches that branch. I left it out of the total.
- Nothing found should block the commit. Committing is for whoever is told to do it.