# Reason codes — P027 BenchReceipt v1.0.0 (frozen by P027-T004)

Vocabulary owned by the verifier (PROJECT_BOOK §5.6, §12.2/§12.3;
ADR-001 decision 4: `result.v1.json` freezes only the *shape* of reason
codes, not the values). This file freezes the values. T008 ratifies two
additions here via ADR-003 (`LCOV_MALFORMED`, `INTERNAL_ERROR`); the
S0 Golden expected (`fixtures/s0/GOLDEN.json`) uses the original 22
codes only — no S0 fixture triggers either new code.

Rules that apply to every code:

- `reason_codes` in a result is the sorted, deduplicated union of all
  codes emitted for that verification.
- A code is emitted at most once per result, however many jobs trigger it.
- Status precedence (PROJECT_BOOK §5.6, strictest wins):
  `INVALID` > `UNBOUND` > `BOUND_FAIL` > `BOUND_PASS`.
- `identity_mismatches[]` carries `{job_id, field, expected, actual}`
  for identity codes; `report_errors[]` carries `{code, message,
  job_id, path?}` for report codes. Fixed message templates are listed
  below so the Python verifier and the Node Oracle produce byte-identical
  results (no underlying parser error text is ever embedded — parser
  messages differ between runtimes).

## Status classes

| Code | Status class | Meaning |
|---|---|---|
| `SOURCE_SHA_MISMATCH` | UNBOUND | A job's `git.head_sha` != the expected source SHA passed to verify. Covers PR head / merge commit confusion (§12.3 sample C). |
| `SOURCE_MODE_MISMATCH` | UNBOUND | A job's `git.source_mode` != policy `source_mode`. PR head and merge SHA are never treated as equivalent (§5.3). |
| `TREE_SHA_MISMATCH` | UNBOUND | Jobs disagree on `git.tree_sha` while policy `same_tree_across_jobs` is true. Reference = the tree of the first job when receipts are ordered by job_id. |
| `RUN_ID_MISMATCH` | UNBOUND | Jobs disagree on `ci.run_id` while policy `same_run_id` is true. Reference = the run id of the first job ordered by job_id. |
| `RUN_ATTEMPT_MISMATCH` | UNBOUND | Jobs disagree on `ci.run_attempt` while policy `same_run_attempt` is true (§12.3 sample B). Reference = the attempt of the first job ordered by job_id. |
| `WORKFLOW_MISMATCH` | UNBOUND | A job's `ci.workflow` != policy `expected_workflow`. |
| `MATRIX_MISSING_JOB` | UNBOUND | A `required_jobs` entry has no receipt (`missing_jobs[]`, §5.2). |
| `MATRIX_DUPLICATE_JOB` | UNBOUND | A job id appears in more than one receipt (`duplicate_jobs[]`, §5.2). Duplicates are detected by receipt `job_id`, not by evidence directory name. |
| `MATRIX_UNEXPECTED_JOB` | UNBOUND | A receipt's job id is not in `required_jobs` (`unexpected_jobs[]`, §5.2). |
| `SOURCE_MUTATED_DURING_RUN` | UNBOUND | Source changed during a job's run (§5.5): the before/after `tracked_diff_sha256` digests differ, OR the `dirty` flag changed, OR (`require_clean_source_after` and `dirty_after` is true). Recorded by T003 via `git.dirty_before/after` + `source_state_before/after` (HANDOFF.md: no dedicated run.v1 mutation field). |
| `REPORT_MISSING` | UNBOUND | A report the receipt lists is absent from the bundle, or a report kind the policy requires (`junit`/`lcov` = `required`) has no entry in `reports[]`. |
| `MISSING_FIELD` | UNBOUND | A field the policy requires is absent although the schema allows it to be optional: the `junit` summary block is missing while policy requires JUnit; or BOTH `git.head_sha_after` and `git.tree_sha_after` are absent (spec v1.2.0, ADR-007): without after identity the receipt cannot prove the run's HEAD/tree did not change mid-run, so it is UNBOUND, never BOUND_PASS. (Fields required by `run.v1.json` itself, when absent, are `INVALID_RECEIPT` instead.) |
| `REPORT_HASH_MISMATCH` | INVALID | A report file's recomputed size or SHA-256 differs from the receipt's `size_bytes` / `sha256` (§5.4). Hash damage is INVALID per §5.6. |
| `JUNIT_MALFORMED` | INVALID | A JUnit report file cannot be parsed as XML (§5.4). |
| `JUNIT_SUMMARY_MISMATCH` | INVALID | The parsed JUnit counts (testcases / failures / errors) disagree with the receipt's `junit` summary (§5.4: report test count must match parsed testcase count). No S0 fixture plants this; it is reserved for the full parser (T005). |
| `LCOV_MALFORMED` | INVALID | A LCOV report file cannot be parsed as valid LCOV (not UTF-8, NUL byte, over the size limit, unknown tag, malformed `FN`/`FNDA`/`BRDA`/`DA` line, record without `SF`, unsafe `SF` path, non-integer count, or summary counts disagreeing with the records; `FNH` is checked against `FNDA` hits only when `FNDA` lines exist — see T005). Ratified by T008 in ADR-003. No S0 fixture triggers it. |
| `INTERNAL_ERROR` | INTERNAL_ERROR | The verifier itself hit an unexpected internal exception while verifying — a verifier bug, not bad input (bad input already has `INVALID_POLICY` / `INVALID_EVIDENCE` / `INVALID_RECEIPT`). The result carries no other finding: `jobs_verified` 0, empty job lists, `reason_codes` exactly `["INTERNAL_ERROR"]`. Ratified by T008 in ADR-003. No S0 fixture triggers it. |
| `INVALID_RECEIPT` | INVALID | A receipt file is not JSON, or fails `benchreceipt.run/v1` validation. |
| `INVALID_POLICY` | INVALID | The policy dict fails `benchreceipt.policy/v1` (never silently defaulted — ADR-001 decision 6). |
| `INVALID_EVIDENCE` | INVALID | The evidence directory is missing, not a directory, or unreadable. |
| `JUNIT_FAILED` | BOUND_FAIL | Evidence is bound, but the JUnit report has `failures > 0` or `errors > 0` (§5.4). Consistent with a non-zero command exit code; when the exit code contradicts the JUnit outcome, `EXIT_CODE_MISMATCH` is also emitted. |
| `JUNIT_EMPTY` | BOUND_FAIL | Evidence is bound, but the JUnit report has `tests == 0` (§5.4: `tests > 0` required). |
| `EXIT_CODE_MISMATCH` | BOUND_FAIL | The command exit code contradicts the JUnit outcome: exit != 0 while JUnit passes, or exit == 0 while JUnit fails. Only compared when `tests > 0` and the JUnit report parsed. |
| `POLICY_MISMATCH` | BOUND_FAIL | Evidence is bound, but a policy condition on the test result fails: JUnit `tests` (with `tests > 0`) is below policy `min_tests`. |

## Fixed message templates (`report_errors[].message`)

These exact strings are used by both implementations. `{...}` slots are
filled from the receipt / parsed report; nothing else varies.

- `REPORT_MISSING` (file listed but absent): `report file missing: {path}`
- `REPORT_MISSING` (required kind has no entry): `required {kind} report missing`
- `REPORT_HASH_MISMATCH`: `report digest mismatch: {path}`
- `JUNIT_FAILED`: `JUnit failed: {failures} failures, {errors} errors (tests={tests})`
- `JUNIT_EMPTY`: `JUnit report has 0 tests`
- `JUNIT_MALFORMED`: `JUnit XML is malformed`
- `JUNIT_SUMMARY_MISMATCH`: `JUnit summary does not match parsed report`
- `LCOV_MALFORMED`: `LCOV report is malformed`
- `INTERNAL_ERROR`: `internal error during verification`
- `EXIT_CODE_MISMATCH` (exit != 0, JUnit passing): `command exit code {exit} contradicts passing JUnit result`
- `EXIT_CODE_MISMATCH` (exit == 0, JUnit failing): `command exit code 0 contradicts failing JUnit result`
- `MISSING_FIELD` (junit summary): `missing junit summary`
- `MISSING_FIELD` (after identity): `missing git.head_sha_after and git.tree_sha_after`
- `POLICY_MISMATCH`: `JUnit tests {tests} below policy min_tests {min_tests}`
- `INVALID_RECEIPT`: `receipt is not valid benchreceipt.run/v1`
- `INVALID_POLICY`: `policy is not valid benchreceipt.policy/v1`
- `INVALID_EVIDENCE`: `evidence directory is missing or unreadable`

`identity_mismatches[]` entries carry no message. Their `field` values
are: `git.head_sha`, `git.tree_sha`, `git.source_mode`, `ci.run_id`,
`ci.run_attempt`, `ci.workflow`.

## `jobs_verified` (frozen counting rule)

`jobs_verified` counts non-duplicate receipt instances whose `job_id`
is in `required_jobs` and which pass **every** per-job check (identity,
mutation, reports, JUnit, exit code). A duplicate's second and later
copies count 0; an unexpected job counts 0; a missing job counts 0.
