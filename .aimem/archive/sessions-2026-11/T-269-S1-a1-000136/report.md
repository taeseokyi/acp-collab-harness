PARTIAL

The product-code fixes P1, P2 and P3 are closed, and so are tests Q5 and V19. Q2 is only half closed, and the full test suite (`python3 -m unittest discover -s tests`) now fails 1 of 940 tests. Q1 is not closed.

**What I did:** `python3 tools/aimem_db.py check --slot S1 --token a41f0c --rev 164` printed `일치` (match), and `rounds/R22/REVIEW-r22-2.md` is on my owned-path list. I copied the repo to `/tmp/r22b-review`, leaving out `.git`, `__pycache__`, `tls`, `runs` and `sessions`; `.aimem/tls` was confirmed absent. In that copy I ran the reproduction, 17 mutations, and a read-only survey of the real run records. I deleted both `/tmp` folders afterwards. Only the review file below was written in the repo; the other changes in `git status` were already there.

**Changed file:** `rounds/R22/REVIEW-r22-2.md` (new; contains the closure, new-defect and mutation tables and the summary)

**Verification commands and output:**
- `python3 -m unittest discover -s tests -p test_fleet_graph.py` → `Ran 77 tests OK`
- `python3 -m unittest discover -s tests -p test_rt_claude.py` → `Ran 28 tests OK`
- `python3 -m unittest discover -s tests` → `Ran 940 tests in 135.9s FAILED (failures=1, skipped=1)`, failing test `test_q2_session_branch_429_is_true: None is not True`
- Reproduction: I gave the same 10 records to both the old `.aimem/runs` path and the session path. All four checks (old path, session path, the claude adapter, and the shared function) gave the same answer every time:
  - the N3 cases → `None`
  - context-window / `max_tokens` errors → `None`
  - `429`, or `api_error` with "hit your limit" → `True`
  - `fleet_graph._result_limit_signal is claude.result_limit_signal` → `True`
- Mutations: 16 counted, 15 caught, 1 survived (V08). W12 is equivalent to the original and is left out of the count.
- Survey of all 290 real records: the final limit verdict count went 1→1, so adding `"hit your limit"` caused no new misreads. The only report that matches it is `T-267`, where the fix worker quotes the phrase; it ended with rc 0, so the verdict is unaffected.
- `import fleet_graph` works on its own, and there is no import cycle.

**What the next owner needs to know:**
1. **R1 (medium, fix before committing):** `tests/_fleet_env.py:10` sets `AIFLEET_HARNESS=fake`. In a full `discover` run, other test modules load it first, so the `_session` helper's session tests get the fake adapter instead of the claude one. Run that way, the 429 test fails, and the `n3` and `context window` tests pass without testing anything. The fix author apparently ran each module on its own. Fix: clear the forced fake harness inside `_session` (`mock.patch.dict(os.environ, {"AIFLEET_HARNESS": ""})`), then confirm with a full `discover` run.
2. **R2 (low):** the Q1 test's counterexamples don't create the session folder the path would climb out from. So when `/` is allowed in run IDs (V08), all 77 tests still pass. With that change and a real session folder in place, `T-1-S1-a1-000000/../../outside/evil` reads files outside the repo and returns `True`. The product currently blocks this; the gap is that no test would notice if that protection were removed.
3. Minor: `LIMIT_PATTERNS as _LIMIT_PATTERNS` in `tools/fleet_graph.py:52` is imported but never used.
4. The work tree is still uncommitted.