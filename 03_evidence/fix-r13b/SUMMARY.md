# FIX-R13b evidence summary — Oracle-side T013 P1s F-02–F-08 + F-01 mirror

- Branch: `fix-r13b` (from `main` at `89bea64`).
- Scope: `02_source/oracle/verify.mjs`, `02_source/oracle/verify.test.mjs`,
  `02_source/tests/test_oracle_parity_r13b.py` (new). No Python production
  code, schemas, S0 fixtures/Golden, `04_review/`, `00_control/`, release
  files or `pyproject.toml` touched (`git status` clean except these).
- Oracle stays dependency-free: Node built-ins only, zero npm deps, no network.

## Per-finding fix (all in `02_source/oracle/verify.mjs`)

- **F-02 LCOV**: new `parseLcov()` porting `reports/lcov.py` exactly
  (known tags, `end_of_record` structure, SF path rules, DA/FN/BRDA
  value checks, LF/LH/FNF/FNH/BRF/BRH summary cross-checks, duplicate-DA
  rejection, NUL/non-UTF-8 rejection). Malformed LCOV now yields
  `INVALID / LCOV_MALFORMED` (`REASON_STATUS` gained the code).
- **F-03 count attributes**: the JUnit parser reads `tests/failures/
  errors/skipped` on each top-level `<testsuite>` and on a `<testsuites>`
  wrapper and rejects mismatches as `JUNIT_MALFORMED`, as production does.
- **F-04 real XML parser**: `parseJUnitMinimal` is now a dependency-free
  well-formedness + element-counting parser (replacing regex counting):
  DOCTYPE/ENTITY pre-scan rejection, CDATA-as-text, comment exclusion,
  processing-instruction skipping, namespaced local-name counting,
  self-closing elements counted, duplicate-attribute / mismatched-close /
  unbound-prefix / junk-after-root rejection, entity decoding with
  attribute-value normalisation. Nested `<testsuite>` attributes are not
  checked, matching production (P2-10).
- **F-05 symlinks**: new `resolveRealPath()` (component-wise symlink
  resolution, incl. dangling targets, `.`/`..` against the resolved
  prefix, loop detection). Report real paths must stay inside the job
  dir's real path or the report is `REPORT_HASH_MISMATCH`; symlinked
  job dirs / `receipt.json` escaping the evidence tree / job dir are
  `INVALID_RECEIPT` (see "deliberate strictness" below).
- **F-06 schema**: `receiptStructuralError()` now mirrors
  `benchreceipt.run/v1` in full (additionalProperties, required fields,
  string lengths/patterns, integer ranges incl. `run_attempt` ≤ 100000,
  `size_bytes` ≤ 1 GiB, `junit` counts ≤ 100000000, enums, `maxItems`,
  `matrix` propertyNames/values, `source_state`, timestamps) and
  `policyError()` mirrors `benchreceipt.policy/v1` (incl. additional
  properties, `required_jobs` item pattern, `min_tests` range, bool
  strictness). Pattern checks follow Python `re.search` `$` semantics
  (trailing newlines accepted, P2-05 behaviour, matched not "fixed").
- **F-07 TOML**: `parseToml()` rewritten as a character-level parser:
  duplicate keys/sections rejected, trailing comments stripped outside
  strings, basic-string escapes processed as tomllib does (`\" \\ \b
  \t \n \f \r \uXXXX \UXXXXXXXX`, multi-line line-ending backslash),
  literal strings, TOML integers (underscores, 0x/0o/0b), multi-line
  arrays with comments, inline tables, dotted keys. `parsePolicyToml`
  is now an alias (no pre-joining hack).
- **F-08 pins**: CLI gains `--expected-run-id` / `--expected-attempt`
  (both `--flag value` and `--flag=value` forms); `evaluate()` takes a
  4th `options` argument and enforces the pins exactly like production
  (same codes, same UNBOUND outcome, pinned value in
  `identity_mismatches`). CLI usage errors mirror the Python CLI:
  missing/malformed `--expected-source-sha` → stderr + exit 3; empty
  run id or out-of-range/non-integer attempt → stderr + exit 3.
  Invalid pin values passed to `evaluate()` directly return an
  `INTERNAL_ERROR` result, as production's `evaluate()` does
  (`INTERNAL_ERROR` added to the Oracle vocabulary/exit map).
- **F-01 mirror**: every parsed JUnit report in a job is now judged
  against the summary (per-report `JUNIT_FAILED` when the summary did
  not already flag it, per-report `JUNIT_SUMMARY_MISMATCH`, per-report
  `JUNIT_EMPTY`), `junit_failed` is set from ANY failing parsed report
  for the exit-code check, and report errors are deduplicated on
  (job, code, path, message) exactly as production does. Both report
  orders return the identical triple
  `[EXIT_CODE_MISMATCH, JUNIT_FAILED, JUNIT_SUMMARY_MISMATCH]`, jobs 0;
  the all-passing control stays `BOUND_PASS`.

## Reviewer repro before → after (Oracle vs Python, identical status + codes)

| Case | Before (Oracle) | After (Oracle) | Python |
|---|---|---|---|
| R2 malformed LCOV | BOUND_PASS | INVALID [LCOV_MALFORMED] | INVALID [LCOV_MALFORMED] |
| R3 attr tests=999 | BOUND_PASS | INVALID [JUNIT_MALFORMED] | INVALID [JUNIT_MALFORMED] |
| R4a CDATA (11 vs 10 attr) | INVALID [JUNIT_SUMMARY_MISMATCH] | INVALID [JUNIT_MALFORMED] | INVALID [JUNIT_MALFORMED] |
| R4b comment | INVALID [JUNIT_SUMMARY_MISMATCH] | BOUND_PASS | BOUND_PASS |
| R4c bare `<testcase/>` | INVALID [JUNIT_SUMMARY_MISMATCH] | BOUND_PASS | BOUND_PASS |
| R4d unclosed testcase | BOUND_PASS | INVALID [JUNIT_MALFORMED] | INVALID [JUNIT_MALFORMED] |
| R4e DOCTYPE | BOUND_PASS | INVALID [JUNIT_MALFORMED] | INVALID [JUNIT_MALFORMED] |
| R4f namespaced | INVALID [JUNIT_SUMMARY_MISMATCH] | BOUND_PASS | BOUND_PASS |
| R4a2 CDATA | BOUND_PASS | BOUND_PASS | BOUND_PASS |
| R4b2 comment | INVALID [JUNIT_SUMMARY_MISMATCH] | BOUND_PASS | BOUND_PASS |
| R4a3 CDATA space form | INVALID [JUNIT_SUMMARY_MISMATCH] | BOUND_PASS | BOUND_PASS |
| R4g self-closing `<failure/>` | INVALID [EXIT_CODE_MISMATCH, JUNIT_FAILED, JUNIT_SUMMARY_MISMATCH] | BOUND_FAIL [EXIT_CODE_MISMATCH, JUNIT_FAILED] | BOUND_FAIL [EXIT_CODE_MISMATCH, JUNIT_FAILED] |
| R24 multi-JUnit, fail first | BOUND_PASS | INVALID [EXIT_CODE_MISMATCH, JUNIT_FAILED, JUNIT_SUMMARY_MISMATCH] | same triple |
| R24b order swapped | INVALID [JUNIT_SUMMARY_MISMATCH] | INVALID, same triple | same triple |
| R5 symlink escape | BOUND_PASS | INVALID [REPORT_HASH_MISMATCH] | INVALID [REPORT_HASH_MISMATCH] |
| R6a dup min_tests | UNBOUND [MATRIX_MISSING_JOB] (dup silently last-wins) | INVALID [INVALID_POLICY] exit 3 | PolicyInvalid |
| R6b trailing comment | INVALID [INVALID_POLICY] (false block) | policy accepted (UNBOUND [MATRIX_MISSING_JOB] on the 1-job/2-job-policy evidence) | accepts |
| R6c escaped quote | workflow kept raw backslash | workflow `CI"X` | `CI"X` |
| R7a run_attempt 200000 + extra field | BOUND_PASS | INVALID [INVALID_RECEIPT] | INVALID [INVALID_RECEIPT] |
| R7b required_jobs=[123] | INVALID [INVALID_POLICY] | INVALID [INVALID_POLICY] | PolicyInvalid |
| R16 pinned wrong run | BOUND_PASS (flags ignored) | UNBOUND [RUN_ATTEMPT_MISMATCH, RUN_ID_MISMATCH] exit 2 | UNBOUND, same codes |

Full logs: `before-repro2/3/4.log`, `after-repro2/3/4.log` in this dir.
Note: `repro4.py` still exits 1 at its R28 step, exactly as before the
fix — a pre-existing bug in the repro script itself (it calls
`verify_bundle` on a bundle dir that was never built because of an
`if False` guard); unrelated to the Oracle. R9/R10 (P2-06 giant ints)
are unchanged and out of scope: production returns INTERNAL_ERROR
there, the Oracle returns INVALID/JUNIT_MALFORMED (fail-closed).

## Parity corpus (new, pinned by tests)

- `02_source/tests/test_oracle_parity_r13b.py`: **69 passed**. Every case
  runs production `evaluate()` and the Oracle CLI on the same evidence
  and asserts identical status, reason codes, jobs_verified, full
  report_errors (code/job/path/message), identity mismatches and exit
  code. Covers all reviewer repro cases above plus new variants: 10
  LCOV malformed forms, 11 JUnit attr/structure variants, multi-JUnit
  all-passing + failing-second-with-exit-1, symlink inside/dangling,
  18 receipt-schema violations, 5 TOML/policy-text cases, 4 pin cases.
- `02_source/oracle/verify.test.mjs`: **24/24 passed** (8 baseline + 16
  new: TOML dup/comment/escapes, LCOV parse + evaluate, JUnit parser
  table, symlink in/out, schema receipt/policy tables, F-01 both
  orders, F-08 CLI pins + usage errors, symlinked receipt).

## Acceptance commands (from `02_source`, `.venv` Python 3.12.3, `TMPDIR=…/.tmp`)

| Command | Exit | Result | Log |
|---|---|---|---|
| `../.venv/bin/python ../03_evidence/t013-review/repro2.py` | 0 | all F-02–F-04 cases parity (see table) | `after-repro2.log` |
| `../.venv/bin/python ../03_evidence/t013-review/repro3.py` | 0 | R24/R24b/R5/R6/R7a/R16 parity | `after-repro3.log` |
| `../.venv/bin/python ../03_evidence/t013-review/repro4.py` | 1 | R4a3/R4g/R6a parity; aborts at pre-existing R28 script bug (unchanged) | `after-repro4.log` |
| `../.venv/bin/python -m pytest tests/test_oracle_parity_r13b.py -q` | 0 | **69 passed** | (stdout) |
| `../.venv/bin/python -m pytest -q` | 0 | **827 passed** (758 baseline + 69 new) | `pytest.log` |
| `../.venv/bin/python scripts/s0_gate.py --out-dir ../03_evidence/fix-r13b/s0` | 0 | **S0 PASS 10/10, parity 50/50** | `s0-gate.log`, `s0/` |
| `node --test oracle/verify.test.mjs` | 0 | **24/24 passed** | `oracle-tests.log` |
| `../.venv/bin/python scripts/privacy_scan.py` | 0 | 184 files, 0 findings | `privacy-scan.log` |
| `../.venv/bin/python scripts/validate_workflow_example.py` | 0 | PASS | `validate-workflow.log` |

No S0 failure, no new P0/P1 found.

## Deliberate divergences / left for T014 (not hidden)

1. **Symlinked `receipt.json` / job dirs**: the Oracle now rejects a
   receipt/job dir whose real path escapes its root (`INVALID_RECEIPT`),
   per the task direction. Production's raw `verify` reads symlinked
   receipts straight through (review P2-18: `BOUND_PASS`). This is a
   fail-closed strictness the Oracle adds; T014 should ratify it or
   ask for alignment with production.
2. **Giant integers (>4300 digits, P2-06)**: production's `int()` leaks
   `ValueError` → `INTERNAL_ERROR`; the Oracle treats an over-long
   count/summary integer as malformed (`INVALID`). Fail-closed, and
   P2-06 itself is Python-side; not changed here.
3. **Float-form integers in JSON** (e.g. `run_attempt: 2.0`): Python
   rejects (not an int); `JSON.parse` in JS yields `2`, which the
   Oracle accepts. Not in any repro input; needs a raw-JSON scan to
   close exactly.
4. **`schema_version = true` (P2-16)**: Python accepts (`True == 1`
   const check); the Oracle still rejects (`!== 1`). Schema-text-faithful
   on the Oracle side; Python-side quirk, out of scope.
5. **UTF-16 / non-UTF-8 JUnit**: production's ElementTree decodes per
   declaration; the Oracle strictly decodes UTF-8 and calls anything
   else malformed. No real JUnit producer emits UTF-16 here.
6. **CLI `--expected-attempt abc`**: Python argparse exits 2; the Oracle
   exits 3 (treated as an invalid pin, same as the range check).
   Missing `--policy`/`--evidence` still exit 4 in the Oracle (Python
   argparse exits 2) — pre-existing behaviour, untouched.
7. **`oracle/README.md` parity claim**: the review said it should be
   qualified until the Oracle gaps close. README was outside this
   task's allowed files; the qualification wording is left for the
   coordinator/T014 now that the gaps are closed.
8. No new S0 fixtures were added (frozen set untouched, per task);
   parity beyond the 50 fixtures is pinned by the 69-case pytest file
   and the 16 new node tests instead.
