PARTIAL — the re-review is finished and `rounds/R22/REVIEW-r22.md` is written, but I couldn't delete the temporary copies in `/tmp` (see the end).

**Result:** every fix is closed where it was made. But the limit-detection fixes for N3 and N4 don't reach the path workers actually use now, so those two defects are still live in production.

## What I did
- `python3 tools/aimem_db.py check --slot S1 --token a41f0c --rev 164` → `일치: S1 … REV 164`. The only file I wrote in the repo is `rounds/R22/REVIEW-r22.md` (11,712 characters, 61 table rows, `합계` line present).
- Made a copy at `/tmp/r22-review`, leaving out `.git`, `__pycache__`, `.aimem/tls`, `.aimem/runs` and `.aimem/sessions`. Baseline in the copy: `test_fleet_graph` 73 OK, `test_rt_claude` 24 OK, `test_fleet` 10 OK, `test_fleet_ctl` 40 OK, `test_rt_integration` 18 OK, `python3 tests/browser_monitor_ui.py` 27/27.
- Re-ran my R20 reproductions and put 28 mutations (code changes the tests should catch) into the copy, each reverted after its run. I also re-scored all 287 real run records (277 in `.aimem/runs`, 10 in `.aimem/sessions`), reading them only, under both the old (HEAD) and new rules.

## What is closed
- **N3, N4, N5, N7 (old `.aimem/runs` path):** the N3 record now returns `None` and falls through to the text check, which finds the limit. The context-window message returns `None` instead of a usage limit. The two common phrases no longer trigger. `../outside/evil` returns `None`.
- **M3–M8:** reverting each fixed line turns the tests red.
- **N1:** with `projects/` removed from the copy, the browser test still passes 27/27.
- **N2:** with `.aimem/aimem.db` removed from the copy, it still passes 27/27.
- **M11:** removing the '전체' chip now fails the test (`TimeoutError: Locator.click`).
- **Real records:** the number of runs judged as hitting the limit is unchanged, 1 → 1 (T-215, a real 5-hour limit). Returning `None` more often caused no new misjudgments.

## New defects
- **P1 (medium, live path):** since REV 163 workers run as sessions, and `run_limit_signal` hands those to `tools/fleet_rt/harness/claude.py`. That adapter still returns `False` for the N3 record (line 237), so a real limit gets retried as an ordinary failure. `tests/test_rt_claude.py:196` (`test_other_error_false`) asserts this old wrong behaviour, so it goes red when the fix is applied there.
- **P2 (medium):** the same adapter's `_limit_text` (lines 92–94) still matches any `"limit"`, so context-window errors are treated as usage limits and not retried.
- **P3 (low):** limit detection exists in two copies (`fleet_graph` and the adapter) that have already drifted apart.
- **Q2 (medium):** no `test_fleet_graph` test goes through the session path. Switching that branch off entirely still gives 73 OK.
- **Q1 (low):** allowing `/` inside a run id is not caught by any test.
- **Q3 (low):** in the browser test, the '이번 라운드' value still comes from the repo's own `rounds/` and fleet state, because the temporary repo setup doesn't redirect `fleet.RUNS`. The check only asks that the value is non-empty, so it passes either way.
- **Q4 (low):** the '생략된 제목' check still only takes its fallback branch (unchanged from R20's M12).
- N6 (FIFO hang) and N8 (no size cap on the meta file) were not in this round's scope and are still open.

## Mutation totals
28 mutations: 23 caught, 5 survived. The survivors:
- **V08:** `/` allowed in run ids.
- **V20:** narrowing the adapter's limit text check.
- **V21:** switching off the session branch.
- **B3:** test reverted to "click the chip only if present".
- **B4:** N1 reverted. It only goes red once `projects/` is removed (B5).

V10 was left out of the count because its result is identical (no-op). V19 goes red, but because the test protects the defect.

## For the next owner
Fix P1–P3 first: move the N3/N4 fixes into the claude adapter, ideally by sharing one detection function, and update `test_other_error_false`. Then add session-path tests for the same records (Q2). After that, Q1, Q3, Q4.

## Not done
`rm -rf /tmp/r22-review /tmp/r22-aside /tmp/r22-tools` was blocked by an approval prompt because the paths are outside the working folder, so I left them. `/tmp/r22-review` holds a full copy of the repo (including `.aimem/aimem.db`), without `.aimem/tls`, `.aimem/runs` or `.aimem/sessions`. Someone with permission should run that command. `git status` shows the same three modified files as when I started, plus `rounds/R22/`, which was already untracked.