DONE

Both queue items are closed where the reviews reported them. One leftover: the step loop still hangs when a run's output file is a FIFO, because another function reads that file first (N1, low). Nothing I found should block the commit.

**What I did**
- Ran the slot check: `python3 tools/aimem_db.py check --slot S1 --token a41f0c --rev 164` printed `일치: S1 토큰 a41f0c 하네스 claude 모델 opus REV 164`, and `rounds/R22/REVIEW-r22-4.md` is on its owned-path list.
- Copied the repo to `/tmp/t275`, leaving out `.git`, `.aimem/{tls,runs,sessions}` and `__pycache__`. Ran the full test suite and the browser check there, then 13 unit mutations, 7 browser mutations and an edge-case probe of `read_regular_bytes`. Deleted all the `/tmp` copies afterwards: `glob('/tmp/t275*')` returns `[]`.
- **Files changed:** only `rounds/R22/REVIEW-r22-4.md` (new). `git status` shows the same 7 modified files as before plus `rounds/R22/`.

**Checks run**
- **Full unit tests** (`python3 -m unittest discover -s tests` in the copy): `Ran 944 tests in 133.464s`, `OK (skipped=3)`. The 3 skips are because the copy has no `.aimem/runs`.
- **Browser check** (`python3 tests/browser_monitor_ui.py` in a copy without `projects/` and `.aimem`): rc 0, `통과 30 / 전체 30`. The three new checks (the current-round value, and clicking a cut-off title on the board and the graph list at 1280px) all pass.
- **Mutations:** 20 in total, 15 caught and 5 survived (V01, V04, V07, V08, B1).
  - **S1:** the narrowed context-window test now fails on its own when the adapter's final `return None` becomes `False` (V12).
  - **S2:** the new test catches the exception branch being changed to return False (V13).
  - **Q3:** removing the `fleet.ROOT` swap or the fixed round file is caught (B2–B4).
  - **Q4:** breaking the expand CSS or removing the `scrollWidth` comparison in `app.js` is caught (B5, B6).
- **Edge cases for `read_regular_bytes`:**
  - A FIFO, a directory, a symlink to `/dev/zero`, a symlink loop, a dangling link and a permission-0 file all return `None` without raising.
  - A file exactly at the limit is read; one byte over returns `None`.
  - 3500 calls left the open-fd count at 4 → 4, so no leak.

**What the next owner needs to know**
1. **N1 (low):** In the step loop, `run_report` reads the same output file with `read_text` (`tools/fleet.py:508`, called at `tools/fleet_graph.py:873`) before `run_limit_signal` runs. A FIFO output file still hangs it, and a FIFO `.rc` hangs `_run_state` (`tools/fleet.py:484`). Both reproduced (3-second hang each). Fix: move the `.out`, `.rc` and `.err` reads onto `read_regular_bytes`, and write the FIFO test against the step loop rather than `run_limit_signal`.
2. **The surviving mutations are test gaps, not wrong code:**
   - **N2:** nothing tests the 256 KiB cap on a session's `meta.json` (V07, V08).
   - **N3:** nothing tests the regular-file check or the fd close. A FIFO already reads back empty because of the non-blocking open (V01, V04).
   - **N4:** removing only the `fleet.RUNS` swap survives when the repo has no session records (B1). With the real `.aimem/sessions` copied in, the check catches it (B1x).
3. **Behaviour change (not a defect):** `_run_meta` used to raise on broken JSON and now returns `None`. All 8 callers use `… or {}`. The monitor doesn't call it directly (it goes through `fleet_ctl.public_state`), and `reader.py` doesn't use it. The largest real meta file is 3184 bytes, so the 256 KiB cap doesn't cut any existing record.
4. I did not measure how a session's `report()` behaves on a FIFO.