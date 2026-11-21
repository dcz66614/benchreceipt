# ADR-004 — FIX-capture-junit: capture emits the parsed JUnit summary; LCOV summary gap recorded

- **Date:** 2026-11-17
- **Task:** P027-FIX-capture-junit (P1 — blocks any real capture from ever verifying BOUND_PASS)
- **Status:** Accepted (fix only; no schema change, no spec change)
- **Blocking?** No — the fix is inside `capture.py`'s existing flow and needs no new field.

## Context

The T003/T008 seam, reproduced by the coordinator 2026-11-17 ~08:20 GMT
with the real CLI in a synthetic git repo: `capture` with a valid 2-test
JUnit file wrote a receipt with NO `junit` key (only `reports[]` with
the hashed artifact), so `verify` with `junit = "required"` returned
UNBOUND `[MISSING_FIELD, SOURCE_MODE_MISMATCH]`, jobs_verified 0, exit 2.
(The SOURCE_MODE_MISMATCH was expected in that local synthetic setup —
local capture infers `event_sha` while the policy said `pr_head`; the
MISSING_FIELD was the defect.) Consequence: NO real capture could ever
verify BOUND_PASS. The S0 gate still passed because its 48 fixtures are
hand-written receipts that already contain junit summaries.

The frozen schema (`02_source/schemas/run.v1.json`) already allows the
fix: top-level `junit` is optional, with exactly four required integer
properties (`tests`, `failures`, `errors`, `skipped`) and
`additionalProperties: false`. PROJECT_BOOK §6.2 shows the same shape,
§5.4 requires the summary counts to match the parsed testcase count,
and §5.6 forbids degrading missing evidence to PASS.

## Decisions

1. **Capture emits the parsed JUnit summary.** After the declared
   `--junit` report is hashed and copied into `artifacts/`, capture
   parses it with the T005 parser (`reports/junit.parse_junit`) and
   writes exactly `{tests, failures, errors, skipped}` — the counted
   testcases, never the raw XML attributes — into `receipt["junit"]`.
   The parser's extra keys (`testcase_count`, `suites`) are NOT copied:
   the schema forbids additional properties.
2. **Malformed JUnit fails closed, never guessed.** On `JUnitError`
   (malformed XML, DOCTYPE/ENTITY, attribute/count mismatch, oversize)
   capture omits the `junit` field, prints a `JUNIT_MALFORMED` warning
   to stderr, still writes the receipt, and still passes the command's
   exit code through. Verify then flags `MISSING_FIELD` (UNBOUND) for
   the absent summary AND re-parses the artifact itself, yielding
   `JUNIT_MALFORMED` (INVALID) — INVALID dominates, so a malformed
   JUnit can never produce BOUND_PASS. No summary is ever fabricated.
   No new receipt field records the parse failure: the schema has no
   field for it, and inventing one would be a schema change.
3. **No LCOV summary is emitted — gap recorded, not silently fixed.**
   The frozen `benchreceipt.run/v1` schema has NO top-level `lcov`
   summary field (properties are `ci, command, finished_at, git,
   job_id, junit, matrix, reports, runner, schema, source_state_*,
   started_at` only), and `reports[]` carries only kind/path/size/sha.
   PROJECT_BOOK §5.4 asks LCOV to record `SF`/`DA` counts, but there
   is nowhere schema-legal to put them in the receipt. Capture therefore
   emits ONLY the junit summary. Adding an `lcov` summary field needs a
   spec decision (T013: ADR + SPEC_VERSION bump + schema change) — it
   is NOT done here, and must not be improvised by a later worker.
   The LCOV artifact itself is still hashed/copied and verify still
   re-parses it (`LCOV_MALFORMED` → INVALID), so malformed coverage
   still fails closed; only the summary counts are absent.
4. **No CLI, schema, verifier, fixture, Golden, or Oracle change.**
   The fix is inside `capture.py`'s existing flow; `verify.py`,
   schemas, S0 fixtures, Golden, and the Oracle are untouched. The
   only other files changed are tests and docs that pinned the seam:
   `test_capture.py` / `test_bundle.py` (their shared `JUNIT_XML`
   fixture claimed `tests="2"` with zero `<testcase>` elements — the
   T005 parser rightly rejects that as malformed; the fixture now
   contains 2 real testcases), `test_github_actions.py` (the all-green
   test now expects BOUND_PASS, per its own docstring instruction;
   the mixed-attempt test now expects jobs_verified 3 — only the
   stale-attempt job fails — instead of 0), the GitHub Actions
   example README §5 (seam documented as closed), and this ADR.

## Verification (branch `fix-capture-junit`)

- New regression tests `02_source/tests/capture/test_capture_junit_summary.py`
  (6 tests): valid summary == parsed counts; failing JUnit → BOUND_FAIL
  via `verify.evaluate`; malformed JUnit → no summary + stderr warning +
  verify INVALID (`JUNIT_MALFORMED`); no `--junit` → no key; green
  capture + matching policy → BOUND_PASS; lying attributes → malformed,
  never trusted. 4 of 6 failed pre-fix (the defect tests); all 6 pass
  post-fix.
- Full suite: 495 passed (was 489 + 6 new). S0 gate: PASS 10/10,
  repeat hash `a19054f1…` unchanged (no fixture moved). Oracle:
  8/8 passed.
- E2E demo (real CLI, synthetic repo, log in `.tmp/e2e-demo.log`):
  green capture → receipt `junit {tests: 2, failures: 0, errors: 0,
  skipped: 0}` → verify BOUND_PASS, exit 0; malformed capture →
  stderr `JUNIT_MALFORMED` warning, receipt written, exit 0 passthrough,
  no `junit` key → verify INVALID `[JUNIT_MALFORMED, MISSING_FIELD]`,
  exit 3, jobs_verified 0.
