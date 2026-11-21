# ADR-007 — FIX-R1: both after fields absent fails closed (UNBOUND + MISSING_FIELD); S0 grows 50 → 52

- **Date:** 2026-11-18
- **Task:** P027-FIX-R1 (P0-R1-01 — legacy-shape false BOUND_PASS)
- **Status:** Accepted (coordinator ruling: scheme A, 2026-11-18)
- **Spec change:** yes — the ONE approved spec change for this fix.
  SPEC_VERSION 1.1.0 → 1.2.0 (PROJECT_BOOK.md + IMPLEMENTATION_PLAN.md,
  both in `01_spec/` and mirrored in `~/workspace/p027-specs/`, MD + DOCX
  + SPEC_MANIFEST.json). No other spec change is made here.

## Context

Final review R1 (frozen commit a07dc79) returned FINAL_VERDICT: FAIL
on one new P0, P0-R1-01: a receipt with BOTH optional after fields
(`git.head_sha_after` / `git.tree_sha_after`) deleted still verifies
BOUND_PASS. The reviewer reproduced it twice, independently:

1. The reviewer's own wheel script
   (`03_evidence/r1-repro/independent_p0_wheel_repro.py`, re-run by
   the FIX-R1 repro worker on the frozen wheel): a real capture whose
   wrapped command switches HEAD mid-run (clean checkout) or creates
   an empty commit verifies UNBOUND + `SOURCE_MUTATED_DURING_RUN` as
   captured — but after deleting the two after fields from the same
   receipt, `evaluate` returns BOUND_PASS, `jobs_verified` 1.
2. The fixture-deletion variant (`03_evidence/fix-r1-repro/`): the
   frozen S0 fixtures e5/e6 with both after fields deleted verify
   BOUND_PASS under BOTH the Python CLI and the Node Oracle
   (4/4 legacy cells BOUND_PASS; the 4 orig controls stay UNBOUND).

Root cause: ADR-005 decision 4 kept a compatibility rule — receipts
with neither after field "are judged by the dirty/digest checks
alone, exactly as before" (PROJECT_BOOK §5.5 v1.1.0). A clean-tree
HEAD change is invisible to the dirty/digest checks (empty porcelain
before and after, both dirty flags False), so the fallback cannot
see the very mutation the after fields exist to catch. The schema
still had to keep the fields optional (old receipts must parse), so
the fallback was the only thing standing between a legacy receipt
and BOUND_PASS — and it stands for nothing.

## The indistinguishability proof (why the old rule cannot be kept)

The first FIX-R1 worker (correctly) STOPPED without changing any
production code, after the coordinator verified the proof:

- e7, as originally designed (e5 with its two after fields deleted),
  and the existing control fixture n01 have byte-identical inputs:
  receipt JSON, `policy.toml`, and `expected.json` are all the same
  (HEAD `aaaa…a`, tree `dddd…d`, clean tree both sides, identical
  empty porcelain digests, both dirty flags False).
- Golden requires n01 → BOUND_PASS and e7 → UNBOUND.
- `verify` is a deterministic function of its inputs. Two identical
  inputs cannot produce two different outputs.

So no verifier-side rule can satisfy both Golden entries while the
old "judge legacy receipts by dirty/digest alone" rule stands: any
rule that passes n01 passes e7, and any rule that fails e7 fails
n01. The old constraint ("the other 50 fixtures stay
byte-identical") is therefore incompatible with closing P0-R1-01.
One of the two has to go — and the Golden values are hand-written
from the frozen rules and must never be rewritten to fit code, so
the constraint goes.

## Decisions

1. **Verify fails closed on missing after identity (both
   implementations).** When BOTH `git.head_sha_after` and
   `git.tree_sha_after` are absent, the job is UNBOUND with reason
   code `MISSING_FIELD` (reused frozen code, UNBOUND class — no new
   reason code), `jobs_verified` 0 for that job, CLI exit 2. The
   message template is frozen in `docs/REASON_CODES.md` and is
   byte-identical in Python and Oracle:
   `missing git.head_sha_after and git.tree_sha_after`. Only one
   after field present is still judged by the existing rule
   (`SOURCE_MUTATED_DURING_RUN` — the pair must appear together).
   Status aggregation and the exit-code mapping are unchanged
   (UNBOUND → exit 2).
2. **Schema: the two after fields stay OPTIONAL, description only.**
   `benchreceipt.run/v1` keeps `git.head_sha_after` /
   `git.tree_sha_after` optional, so receipts written before v1.1.0
   still validate — they now get UNBOUND instead of INVALID. Only
   the `description` text of the two fields (and the schema's
   top-level description) changes, to state the fail-closed rule.
   No required field, enum, or limit changes.
3. **This ADR overturns ADR-005 decision 4.** The decision-4 bullet
   ("Receipts with neither after field are judged by the
   dirty/digest checks alone, exactly as before") is revoked in
   full. PROJECT_BOOK §5.5's compatibility sentence is deleted and
   replaced by the fail-closed rule; the schema README, the fixture
   README, and `verify.py` / `oracle/verify.mjs` comments are
   updated to match. Nothing else in ADR-005 is changed: capture
   still always records both after fields (decision 2), the fields
   are still two SHAs rather than a boolean (decision 1), and the
   P2-01 residual limitation still stands (decision 7).
4. **Scheme A: the builder gives every existing fixture after
   fields.** `make_receipt` / `std_job` now default
   `head_after` / `tree_after` to the before values (the builder
   simulates current capture output, which always records after
   identity). Re-running the builder over the 50 existing fixtures
   changes ONLY the two added fields (verified field-by-field by
   diff during this fix: 75 receipts gained an after pair equal to
   their before values; e5/e6 are byte-identical; no other file
   differs). The 48 fixtures that lacked after fields were not a
   semantic choice — v1.1.0 fixed capture but never updated the
   builder's default, so they still carried the pre-v1.1.0 shape.
   A new `omit_after=True` parameter is the ONLY way to generate a
   receipt without after fields, and it exists only for the two
   legacy fixtures below.
5. **S0 fixtures e7/e8 (frozen set 50 → 52).** Mirroring e5/e6's
   layout (single job, `evidence/<job>/`, `expected.json`,
   `policy.toml`), generated by `02_source/scripts/build_fixtures.py`
   with `omit_after=True`:
   - `e7-legacy-clean-checkout`: no after fields, clean tree both
     sides, HEAD `aaaa…a` → `bbbb…b`, tree `dddd…d` → `eeee…e`,
     identical empty porcelain digests, both dirty flags False.
     Expected: UNBOUND, `MISSING_FIELD`, `jobs_verified` 0.
   - `e8-legacy-empty-commit`: no after fields, HEAD `aaaa…a` →
     `cccc…c`, tree unchanged (`dddd…d`), otherwise identical to
     e7. Expected: same as e7.
   Both fixtures' receipts are byte-identical by design — without
   after fields the two legacy scenarios are indistinguishable,
   which is exactly why both must fail closed. Golden gains the
   two hand-written entries (same shape as e1); no existing Golden
   value is changed. S0 thresholds move 34 → 36 faults and
   50/50 → 52/52 parity; controls stay 16/16. The S0 gate script
   now derives its counts from the fixture inventory instead of
   hard-coding 50/34.
6. **Oracle parity.** The Node Oracle applies the same fail-closed
   rule independently (own code, no Python imports) with the
   byte-identical MISSING_FIELD message. S0 pytest parametrisation
   checks Oracle vs Golden for e7/e8 as for every fixture; the
   69-case parity corpus still asserts identical status, reason
   codes, report errors, identity mismatches and exit code.
7. **Tests.** New coverage: `test_both_after_fields_missing_fails_closed_with_missing_field`
   (real capture, both fields deleted → UNBOUND/MISSING_FIELD),
   `tests/verify/test_legacy_after_missing.py` (e7/e8: source API,
   schema-still-valid, Oracle parity, CLI exit 2), and
   `tests/packaging/test_wheel_legacy_after_missing.py` (the
   reviewer probe rebuilt against a wheel from the fixed tree,
   with the fixed expectations, plus a clean-capture control).
   Existing tests that asserted a no-after-field receipt could
   BOUND_PASS would be testing the revoked rule — none did: every
   pre-existing BOUND_PASS test is fixture- or capture-based, and
   all of them now carry after fields (see FIX-R1 SUMMARY).

## Alternatives considered

- **Keep the compat rule and distinguish e7 from n01 another way:**
  rejected — impossible. The proof above shows the two inputs are
  identical; no verifier-side rule can separate them. Any "fix"
  that kept the rule would have to change Golden (forbidden) or
  make verify non-deterministic (absurd).
- **Make the after fields REQUIRED in the schema:** rejected — it
  would turn every pre-v1.1.0 receipt INVALID instead of UNBOUND,
  breaking the R1 repair bar ("keep old-format parsing, but fail
  closed") and the frozen-schema discipline that required fields
  change only with a spec change. The fail-closed UNBOUND keeps
  old receipts readable and their verdict honest.
- **Fail closed only when the dirty/digest checks are also silent
  (i.e. keep the fallback for receipts whose dirty/digest checks
  DO fire):** rejected — that is just the old rule restated for
  the passing case. The false PASS happens exactly when
  dirty/digest are silent; a fallback that only fires when other
  checks already fire adds nothing.
- **Scheme B (keep the 50 fixtures byte-identical, special-case
  e7/e8 in the gate):** rejected by the coordinator — it would
  leave 48 fixtures in a shape current capture never emits, and
  the gate would then be testing a verifier rule (fail-closed on
  missing after fields) against fixtures that contradict it
  (n01–n16 would fail closed too). Scheme A keeps the fixtures
  honest about what capture emits.

## Verification (branch `fix-r1`)

- Pre-fix repro on the branch (before any production change):
  fixture repro 4/4 legacy cells BOUND_PASS (Python + Oracle);
  reviewer wheel script 2/2 legacy-shape false PASS proven.
- Post-fix: the same two repros flip to 4/4 UNBOUND +
  MISSING_FIELD (fixture) and 2/2 UNBOUND + MISSING_FIELD
  (wheel), with the original 6 tests and the original e5/e6
  UNBOUND verdicts unchanged.
- Full suite: 848 passed (830 at the v1.1.0 freeze + 18 new: 4 from
  the S0 parametrisation growing 50 → 52 fixtures × 2 tests, 11 new
  e7/e8 tests, 1 new both-fields-missing test, 2 new wheel tests).
  S0 gate PASS 10/10 (16/16 controls, 36/36 faults, parity 52/52,
  repeat-hash 100 runs 1 hash — the repeat hash is unchanged from
  the v1.1.0 freeze), Oracle 26/26, offline install check.
  Counts are in `03_evidence/fix-r1/SUMMARY.md`.
