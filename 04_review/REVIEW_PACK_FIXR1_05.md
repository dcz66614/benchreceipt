# REVIEW PACK FIXR1-05 — Oracle (`02_source/oracle/`)

- **Anchor:** `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`)
- **Pack:** 05 of 06. Files read in full at the anchor commit.
- **Verdict:** no P0/P1 in this pack. The Oracle is now a genuine
  second implementation, not a mirror of the Python verifier's
  blind spots. One carried P2 is now partial: P2-15.

## Files

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/oracle/verify.mjs` | `ac65f524c4fa99d601c0dad80e44e27b75d18a5d81cc4933155755219babf800` | 1823 | Oracle verifier |
| `02_source/oracle/verify.test.mjs` | `bdab56971828380b2d35f460496072756b60cdfe8784bd4a5daff6365b7c0754` | 606 | Oracle tests |
| `02_source/oracle/README.md` | `bd1e243e41e9e80e6701b2e717e25a3f2503f847fa9cd50c40ea7e232d72b4c1` | 58 | Oracle notes |

## What I checked

- **`oracle/verify.mjs` (1823 lines — rewritten in FIX-R13b, was 702
  at T013).** Read in full. It is now a full second implementation:
  hand-written XML parser (F-04), LCOV parser (F-02), JUnit count
  attribute checks (F-03), schema validation on load (F-06,
  `git` key allowlist at line 1007, 40-hex checks at lines
  1016–1017), run pins (F-08), symlink-resolving containment
  (F-05). The §5.5 after-identity block (lines ~1444–1475) mirrors
  `verify.py` §5.5 exactly: both-after-absent → `MISSING_FIELD` +
  `reportErrors.push({ code: "MISSING_FIELD", message: "missing
  git.head_sha_after and git.tree_sha_after", job_id: jobId })`
  (line 1463) + UNBOUND via `REASON_STATUS` (line 55); the JUnit
  summary branch is at lines 1568–1569 with the same message
  (`missing junit summary`) as Python. The message template is
  byte-identical between the two implementations and with
  `docs/REASON_CODES.md:70`.
- **`oracle/verify.test.mjs` (606 lines).** 26 tests, including two
  FIX-R1 tests ("both after fields absent fails closed with
  `MISSING_FIELD`"; "e7 legacy fixture is UNBOUND + `MISSING_FIELD`
  via `evaluate()` and CLI") and F-05/F-08 regression tests.
- **`oracle/README.md` (58).** Documents the Oracle as the
  independent second implementation and its test invocation
  (`node --test oracle/verify.test.mjs`).

## Re-runs touching this pack

- **Oracle self-tests:** 26/26 pass
  (`03_evidence/fix-r1-review/oracle.log`).
- **P0 fixture repro:** e5/e6 orig + legacy via the Node Oracle CLI
  agree cell-for-cell with the Python CLI (8/8 cells; legacy
  `UNBOUND` + `MISSING_FIELD`, jobs 0, exit 2).
- **S0 parity:** 52/52 fixtures agree between Python and Oracle.
- **Offline check:** 0 external network references in the Oracle;
  `offline_check.py` PASS.

## Findings in this pack

- **P2-15 — PARTIALLY FIXED (carried):** the Oracle now has an
  `INTERNAL_ERROR` vocabulary and `internalErrorResult()`, so unknown
  codes no longer map to `INVALID` inside `evaluate()`. But its CLI
  `main()` catch still prints to stderr and exits 4 with no result
  JSON on internal error — the second half of the finding remains.
- No new P2 in this pack. The T013 Oracle P1s (F-02, F-03, F-04,
  F-05, F-08) are all fixed in the rewritten file.
