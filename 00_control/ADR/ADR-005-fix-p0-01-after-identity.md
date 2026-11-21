# ADR-005 — FIX-P0-01: run.v1 gains `git.head_sha_after` / `git.tree_sha_after`; S0 grows 48 → 50

- **Date:** 2026-11-18
- **Task:** P027-FIX-P0-01 (P0 — false BOUND_PASS on mid-run HEAD change)
- **Status:** Accepted (Sam approved Option 1, ~00:03 GMT 2026-11-18)
- **Spec change:** yes — the ONE approved spec change for this fix.
  SPEC_VERSION 1.0.0 → 1.1.0 (PROJECT_BOOK.md + IMPLEMENTATION_PLAN.md,
  both in `01_spec/` and mirrored in `~/workspace/p027-specs/`, MD + DOCX
  + SPEC_MANIFEST.json). No other spec change is made here.

## Context

T011 found P0-01 (full detail in
`03_evidence/privacy/SECURITY_FINDINGS.md`, branch `t011`): a wrapped
command that changes HEAD mid-run — `git checkout <other-commit>`
(clean tree, different HEAD *and* tree) or `git commit --allow-empty`
(HEAD changes, tree identical) — produces a receipt claiming the tests
ran against commit A while they ran against commit B, and
`verify.evaluate` returns `BOUND_PASS`, exit 0, zero reason codes.
Capture itself detects the change (`CaptureResult.
source_mutated_during_run == True` + stderr warning), but the receipt
carries no trace of it: the frozen `benchreceipt.run/v1` schema
(`additionalProperties: false`) has no after-identity or
mutation-flag field, and capture never persists its in-memory
`source_mutated_during_run` into the receipt. Verify detects mutation
only from the porcelain-diff digest inequality, the dirty-flag change,
or `require_clean_source_after` — all three blind to a clean checkout
(empty porcelain before and after, both dirty flags False).

S0 missed it because fixtures e1–e4 cover clean→dirty, one-job
mutated, started-dirty, and digest-changed-flags-clean — no fixture
plants a clean-tree HEAD change.

`capture.py`'s module docstring (step 4) claimed mutation "is recorded
*as data*" via `git.dirty_before/dirty_after` plus
`source_state_before/after` — that claim was **false** for this case
and is corrected by this fix (see decision 3).

## Decisions

1. **Schema: two OPTIONAL after fields, not a bare boolean.**
   `benchreceipt.run/v1` gains optional `git.head_sha_after` and
   `git.tree_sha_after` (40-hex, same pattern as `head_sha` /
   `tree_sha`). The two after SHAs were preferred over a bare
   `source_mutated_during_run` boolean because they preserve the
   evidence of *what* the run ended on (the flag is derivable from
   them: after != before), and a boolean alone would not let a later
   reader tell which commit the tests actually ran against. No
   boolean field is added. No required field, enum, or limit changes;
   `additionalProperties: false` is kept everywhere, so receipts
   written before v1.1.0 (neither after field) still validate.
2. **Capture populates both after fields, always.** `capture.py`
   writes `git.head_sha_after` / `git.tree_sha_after` from the same
   `git_after` snapshot its mutation check already uses — including
   when they equal the before values (an equal after value is itself
   evidence that no clean-tree HEAD change happened). The
   `CaptureResult.source_mutated_during_run` / `mutation_details`
   in-memory reporting is unchanged.
3. **Docstring corrected.** Step 4 of the `capture.py` module
   docstring now says exactly what is recorded (after fields +
   dirty flags + source-state digests) and records that the old
   "recorded as data via dirty/digest" claim was false for clean-tree
   HEAD changes (P0-01).
4. **Verify flags after != before, fail closed on inconsistency**
   (`verify.py`, `_evaluate_inner` §5.5 mutation check; same logic
   independently in the Node Oracle `oracle/verify.mjs`). The
   existing porcelain/dirty checks stay as-is. New rules, in
   addition to them:
   - `head_sha_after` present and != `head_sha` → mutated;
     `tree_sha_after` present and != `tree_sha` → mutated.
   - Only one of the two after fields present → mutated (the pair
     must appear together; a half-present pair is inconsistent
     evidence, never a pass).
   - An after field present while its before value is missing or
     not a string → mutated (defensive; the schema requires the
     before values, so this cannot arise from a schema-valid
     receipt, but the verifier must not trust a dangling after).
   - Receipts with neither after field are judged by the
     dirty/digest checks alone, exactly as before (all pre-v1.1.0
     S0 fixtures keep passing).
   A mutated job gets reason code `SOURCE_MUTATED_DURING_RUN`
   (already in the frozen vocabulary, UNBOUND class) and
   `jobs_verified == 0` for that job; status aggregation and the
   exit-code mapping are unchanged (UNBOUND → exit 2, per
   `02_source/docs/REASON_CODES.md`). No new reason code is added.
5. **S0 fixtures e5/e6 (frozen set 48 → 50).** Mirroring e1's
   layout (single job, `evidence/<job>/`, `expected.json`,
   `policy.toml`):
   - `e5-clean-tree-head-change`: clean tree both sides, HEAD
     `aaaa…a` → `bbbb…b`, tree `dddd…d` → `eeee…e`, identical empty
     porcelain digests, both dirty flags False. Expected: UNBOUND,
     `SOURCE_MUTATED_DURING_RUN`, `jobs_verified` 0.
   - `e6-empty-commit-mid-run`: HEAD `aaaa…a` → `cccc…c`, tree
     unchanged (`dddd…d`), identical digests, both dirty flags
     False. Expected: same as e5 — only `head_sha_after` can catch
     this variant.
   Both fixtures are generated by `02_source/scripts/build_fixtures.py`
   (new `head_after` / `tree_after` parameters on `make_receipt`);
   re-running the builder reproduces the other 48 fixtures
   byte-identically (verified by diff during this fix). Golden gains
   the two hand-written entries (same shape as e1); no existing
   Golden value is changed. S0 thresholds move 32 → 34 faults and
   48/48 → 50/50 parity; controls stay 16/16.
6. **Oracle parity.** The Node Oracle applies the same after-field
   logic independently (own code, no Python imports) and its
   structural receipt check now rejects a present-but-malformed
   after field (non-40-hex) as a bad receipt. Oracle tests re-run
   (8/8); S0 pytest parametrisation checks Oracle vs Golden for
   e5/e6 as for every fixture.
7. **Residual limitation (not fixed here).** P2-01 from the T011
   findings: a transient mutate-and-revert *within* one run (dirty
   in the middle, clean before and after) is undetectable by any
   before/after scheme, including this one. It is a documented
   limitation for T012 LIMITATIONS, not a defect in this fix.

## Alternatives considered

- **Capture refuses to write a receipt when mutated** (the T011
  alternative): rejected — it changes the CLI contract (a non-zero
  exit / mutated run still writes a failure receipt), loses the
  evidence of what ran, and does not help hand-written or
  third-party receipts. The after-field route keeps the evidence
  and lets the verifier (the trust boundary) decide.
- **A bare `source_mutated_during_run` boolean instead of the two
  SHAs**: rejected per decision 1 — it discards which commit the
  run ended on.

## Verification (branch `fix-p0-01`)

- The two t011 fail-first tests
  (`02_source/tests/adversarial/test_source_mutation_evasion.py`)
  now PASS (both variants detected, control still passes).
- New tests `02_source/tests/capture/test_capture_after_identity.py`
  (3 tests): clean capture emits after == before and verifies
  `BOUND_PASS`; a receipt with only one after field fails closed
  with `SOURCE_MUTATED_DURING_RUN`; a non-hex after value is
  schema-invalid.
- Full suite: 505 passed (495 at main input + 3 t011 regression tests
  now passing + 3 new after-identity tests + 4 from the S0
  parametrisation growing 48 → 50 fixtures × 2 tests). S0 gate: PASS
  10/10 (16/16 controls, 34/34 faults, parity 50/50, repeat-hash 100
  runs 1 hash). Oracle: 8/8 passed.
