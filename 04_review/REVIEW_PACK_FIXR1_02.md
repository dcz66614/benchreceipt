# REVIEW PACK FIXR1-02 — Verify (`02_source/src/benchreceipt/`, verify side)

- **Anchor:** `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`)
- **Pack:** 02 of 06. Files read in full at the anchor commit.
- **Verdict:** no P0/P1 in this pack. This pack contains the P0-R1-01
  fix; it is verified closed by re-runs, not just by reading.

## Files

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/verify.py` | `7c70f44570baf6070a1e39e8e165457e5b040f87fd3abcf31faaed3acd47cfe1` | 970 | verifier |
| `02_source/src/benchreceipt/matrix.py` | `6c2cbe8bf70c24a3e48bad10b9df84e9b19df1309a48e3caaa2a692176fe04f3` | 101 | matrix checks |
| `02_source/src/benchreceipt/reports/junit.py` | `bb5af528f6d98a6e9a49f164d86c6413c67234f5a5b11ba8e17fa6e8b6dd7242` | 199 | JUnit parser |
| `02_source/src/benchreceipt/reports/lcov.py` | `80c3f2b53b55ea98ddcd8efdcbb276754d62f6eb7273e92735dd5fb6f4612f41` | 309 | LCOV parser |

## What I checked

- **`verify.py` (970 lines) — the P0-R1-01 fix, §5.5 (lines ~536–586),
  read in full.** Both-after-absent is now fail-closed:
  `reason_codes.add("MISSING_FIELD")` (line 557) + report error
  `{"code": "MISSING_FIELD", "message": "missing
  git.head_sha_after and git.tree_sha_after", "job_id": job_id}`
  (lines 559–563) + `job_ok = False` (UNBOUND via `REASON_STATUS`,
  line 106). The comment block (lines 536–551) states the rule and
  names ADR-007 overturning the ADR-005 decision 4 compat fallback.
  One-field-present with a differing value, a missing/not-string
  before value, a `tracked_diff_sha256` change, a `dirty_before !=
  dirty_after` change, or `require_clean_source_after` with
  `dirty_after=True` all set `mutated = True` →
  `SOURCE_MUTATED_DURING_RUN`. The JUnit-summary `MISSING_FIELD`
  (lines 683–685, message `missing junit summary`) is a separate,
  unchanged branch. Aggregation precedence is total
  (`INTERNAL_ERROR > INVALID > UNBOUND > BOUND_FAIL > BOUND_PASS`);
  `evaluate` never raises for bad input; empty reason set is the only
  path to `BOUND_PASS`. The Oracle mirrors this block verbatim
  (`verify.mjs:1444–1475`, message at `:1463`) — see Pack 05.
- **`matrix.py` (101, unchanged).** Required-job / matrix-cell checks
  unchanged; duplicates never count twice; invalid receipts count as
  present, never verified.
- **`reports/junit.py` (199) / `reports/lcov.py` (309).** Content
  changed since T013 at the same line counts (F-01: every JUnit report
  judged, not only the last — the per-report loop in `verify.py`
  FIX-R13a; F-02/F-03: LCOV parsing and JUnit count-attribute checks
  now present in both implementations). Parsers are hand-written,
  reject malformed input instead of guessing, and never trust stored
  digests (sizes + digests recomputed from disk).
- **Stale comment (P2-24):** `verify.py:874` still says "unreachable
  for the 48 S0 fixtures" — the set is 52 since e7/e8. Comment only.

## Re-runs touching this pack (all on frozen source)

- **P0 fixture repro** (my own script): e5/e6 orig + legacy × Python
  CLI + Oracle = 8/8 cells as expected (orig `UNBOUND` +
  `SOURCE_MUTATED_DURING_RUN`; legacy `UNBOUND` + `MISSING_FIELD`;
  jobs 0; exit 2). Log:
  `03_evidence/fix-r1-review/p0-fixture-repro.run.log`.
- **One-field spot check:** deleting only `tree_sha_after` from e5
  still yields `UNBOUND` + `SOURCE_MUTATED_DURING_RUN` in both
  implementations.
- **Full pytest:** 848 passed in 57.07 s
  (`03_evidence/fix-r1-review/pytest-full.log`).
- **S0 gate:** PASS 10/10 — 16/16 controls, 36/36 faults, 52/52
  parity, false PASS/block 0 (`03_evidence/fix-r1-review/s0/`).

## Findings in this pack

- P2-24 (stale "48 S0 fixtures" comment, `verify.py:874`) — see
  `REVIEW_FINDINGS_FIXR1.md`.
- Carried: P2-05, P2-06, P2-07, P2-08, P2-09, P2-10, P2-11, P2-16,
  P2-17 (`junit_file_ok` assigned at `verify.py:610/650`, never read),
  P2-18 — all still present as written in T013; none is a P0/P1.
