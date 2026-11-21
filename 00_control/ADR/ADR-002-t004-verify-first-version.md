# ADR-002 — T004 ships a minimal first version of verify.py

- **Date:** 2026-11-17
- **Task:** P027-T004 (48 fixtures, independent Oracle, S0 gate)
- **Status:** Accepted (frozen for spec v1.0.0)
- **Blocking?** No — this sequences work, it does not change any rule.

## Context

IMPLEMENTATION_PLAN §4 assigns `src/benchreceipt/verify.py` to T008
(Verification Engine + Exit Codes), but the S0 gate (T004) cannot run
without a working verifier to compare against the independent Oracle:
48 fixtures + Golden + parity need a Python `evaluate()` today, while
the CLI, exit codes, and full hardening are T008's job. T004 must not
build `cli.py` (T008 owns it) and must not redesign the frozen
interfaces from T002/T003.

## Decisions

### 1. T004 ships a minimal first version of verify.py; T008 completes it

`verify.py` as shipped by T004 exposes exactly one public function,
`evaluate(policy_dict, expected_source_sha, evidence_dir) -> result dict`,
implementing PROJECT_BOOK §5 (matrix set comparison, per-job
source/run/attempt/tree checks, report digest recomputation + minimal
JUnit summary checks, source-mutation detection via the T003
dirty/digest fields, four-state aggregation with precedence
INVALID > UNBOUND > BOUND_FAIL > BOUND_PASS). The file header records
this sequencing. T008's job becomes completing it (CLI, exit codes,
full reason vocabulary, matrix aggregation hardening) WITHOUT breaking
S0 parity: every T008 change must keep all 48 fixtures' results
identical to `fixtures/s0/GOLDEN.json`.

### 2. JUnit parsing in the minimal verifier is deliberately minimal

T005 owns the full JUnit/LCOV parser. The T004 verifier parses JUnit
only far enough for S0: count `<testcase>` / `<failure>` / `<error>`
elements with `xml.etree.ElementTree` (no DTD / external entities),
compare the counts with the receipt summary, and enforce §5.4
(`tests > 0`, `failures = 0`, `errors = 0`, `min_tests`). LCOV is
checked for presence + digest only. This is marked in the code as
minimal; T005 replaces the parsing, not the verdict rules.

### 3. Invalid receipts count as present, not missing

A receipt file that exists but fails `benchreceipt.run/v1` validation
is `INVALID_RECEIPT` and the job is UNBOUND/INVALID — but the job is
not `MATRIX_MISSING_JOB`: §5.2 defines missing as "no receipt", and
the file exists. Both implementations (Python + Oracle) therefore
count an invalid receipt's job id toward the present set (from the
file when parseable, else the directory name), while it never counts
as verified and never supplies cross-job reference values. This is
also recorded in `docs/REASON_CODES.md` via the `jobs_verified`
counting rule and in the `verify.py` docstring.

### 4. The reason-code vocabulary is frozen by T004, adopted verbatim by T008

`02_source/docs/REASON_CODES.md` freezes the codes, their status
classes, the fixed `report_errors` message templates, and the
`jobs_verified` counting rule. The Oracle and the Python verifier
produce byte-identical results on all 48 fixtures because both follow
that file. T008 adopts it verbatim; adding a code needs an ADR.

## Consequences

- T005–T008 build on `evaluate()`'s signature and result shape; the
  CLI (`cli.py`) wraps it in T008 and must not change its semantics.
- Any T008 change that alters any of the 48 Golden results is a
  regression, not an improvement, until an ADR re-freezes the rule.
