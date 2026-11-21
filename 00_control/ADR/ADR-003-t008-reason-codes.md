# ADR-003 — T008 reason-code ratification (LCOV_MALFORMED, INTERNAL_ERROR)

- **Date:** 2026-11-17
- **Task:** P027-T008 (verification engine + exit codes + CLI)
- **Status:** Accepted (frozen for spec v1.0.0; changing any of these needs a
  spec change, not a quiet vocabulary edit)
- **Blocking?** No — both codes already exist in the shipped code; this ADR
  freezes their meanings instead of letting them drift.

## Context

`02_source/docs/REASON_CODES.md` (frozen by T004, ADR-002 decision 4)
lists 22 reason codes. Two codes have since appeared in the verifier
without a frozen definition:

1. `LCOV_MALFORMED` — introduced by T005 with the full LCOV parser
   (`reports/lcov.py`). The frozen vocabulary had no LCOV code, and no
   existing code describes a malformed coverage file. The T005 handoff
   (HANDOFF.md) flagged it as "T008 must ratify it in REASON_CODES.md
   via ADR".
2. `INTERNAL_ERROR` — needed by T008 to complete PROJECT_BOOK §5.6.
   The five-state table lists `INTERNAL_ERROR` as a *status* (exit 4),
   but the frozen vocabulary has no *reason code* that explains it: a
   result whose status is `INTERNAL_ERROR` would otherwise carry either
   no code or a borrowed code (`INVALID_RECEIPT`), both misleading.
   The result schema already admits it (`tests/schema/test_result_schema.py`
   validates a result with status `INTERNAL_ERROR` and reason code
   `INTERNAL_ERROR`).

## Decisions

### 1. Ratify `LCOV_MALFORMED` (status class INVALID)

- **Meaning:** a LCOV report file listed in a receipt cannot be parsed
  as valid LCOV. Concretely, `benchreceipt.reports.lcov.parse_lcov`
  raises `LcovError` when the file is not UTF-8, contains a NUL byte,
  exceeds the frozen size limit, carries an unknown tag, has a malformed
  `FN` / `FNDA` / `BRDA` / `DA` line, has a record without `SF`, has an
  unsafe `SF` path (absolute, backslash, `..` escape), has a
  non-integer count, or has summary counts that disagree with the
  records (with the T005 FNH rule: `FNH` is checked against `FNDA` hits
  only when `FNDA` lines exist — S0 LCOV fixtures carry `FN`/`FNH`
  with no `FNDA`, and the stated `FNH` is recorded as-is).
- **Status class:** `INVALID` — a malformed report is hash/format damage
  (§5.6: parse failure must be `UNBOUND` or `INVALID`, never PASS), and
  it matches its sibling `JUNIT_MALFORMED` (INVALID), not the
  bound-but-failing `JUNIT_EMPTY` (BOUND_FAIL).
- **Fixed message template:** `LCOV report is malformed` (same shape as
  `JUNIT_MALFORMED`'s `JUnit XML is malformed`; no parser detail is
  embedded, so the Python verifier and the Node Oracle agree byte for
  byte).
- **Trigger:** any receipt whose LCOV report bytes fail parsing, after
  the receipt's recorded size + SHA-256 have already matched (a digest
  mismatch is `REPORT_HASH_MISMATCH` instead, and takes precedence
  because the digest check runs first).
- **No S0 fixture triggers it** (same as `JUNIT_SUMMARY_MISMATCH`):
  coverage comes from the T005 parser tests and the T008 synthetic
  cases in `tests/verify/test_verify.py`.

### 2. Ratify `INTERNAL_ERROR` as a reason code (status class INTERNAL_ERROR)

- **Meaning:** the verifier itself hit an unexpected internal exception
  while verifying — a verifier bug, not bad input. Bad input already has
  its own codes (`INVALID_POLICY`, `INVALID_EVIDENCE`,
  `INVALID_RECEIPT`); `INTERNAL_ERROR` is reserved for the case where
  no input-side code applies because the verifier could not finish.
- **Status class:** `INTERNAL_ERROR`, which dominates the §5.6
  precedence (`INTERNAL_ERROR` > `INVALID` > `UNBOUND` > `BOUND_FAIL` >
  `BOUND_PASS`): when the verifier fails, no other finding can be
  trusted, so the whole result is `INTERNAL_ERROR`.
- **Result shape:** fixed content only — `jobs_verified` 0, empty
  `missing_jobs` / `unexpected_jobs` / `duplicate_jobs` /
  `identity_mismatches`, `reason_codes` exactly `["INTERNAL_ERROR"]`,
  one `report_errors` entry `{code: "INTERNAL_ERROR", message:
  "internal error during verification"}`, and `expected_source_mode`
  omitted (the mode the verifier would have echoed cannot be trusted
  either). The underlying exception text is never embedded (it is
  non-deterministic across runtimes and could leak paths); the CLI
  prints one short line to stderr instead.
- **Trigger:** `evaluate()` / `evaluate_with_policy_path()` catching an
  unexpected exception, or the verifier emitting a code outside the
  frozen vocabulary (vocabulary enforcement — see decision 3). The CLI
  maps the status to exit 4.
- **No existing code's meaning changes:** no other code is re-mapped,
  and `INTERNAL_ERROR` never replaces an input-side code for bad input.

### 3. Vocabulary enforcement (T008)

- The frozen vocabulary is now **24 codes**: the 22 from T004 plus
  `LCOV_MALFORMED` and `INTERNAL_ERROR`. `verify.py` exposes them as
  `REASON_CODES` / `REASON_STATUS` and enforces them: a result that
  would carry any other code is replaced by an `INTERNAL_ERROR` result
  before it can ship. An unknown code is a verifier bug, never a
  finding.
- The result schema (`result.v1.json`) still constrains only the *shape*
  of reason codes (ADR-001 decision 4); the vocabulary lives here and
  in `docs/REASON_CODES.md`.

### 4. No changes to the existing 22 codes

Every existing code keeps exactly the meaning, status class, and fixed
message template frozen by T004. In particular, `JUNIT_SUMMARY_MISMATCH`
stays INVALID and is still triggered only when parsed JUnit counts
disagree with the receipt summary (no S0 fixture plants it; T008 adds
a synthetic case), and `INVALID_RECEIPT` still covers only receipts
that are not JSON or fail `benchreceipt.run/v1` validation.

## Consequences

- `docs/REASON_CODES.md` gains exactly two rows (`LCOV_MALFORMED`,
  `INTERNAL_ERROR`) plus their message templates; no existing row is
  edited.
- `tests/verify/test_verify.py` carries a triggering sample for every
  one of the 24 codes (S0 fixtures where they exist, synthetic cases
  where they do not: `JUNIT_SUMMARY_MISMATCH`, `INVALID_POLICY`,
  `INVALID_EVIDENCE`, `LCOV_MALFORMED`, `INTERNAL_ERROR`).
- The S0 Golden expected is untouched: no S0 fixture triggers either
  new code, so all 48 results stay identical.
- Any future code needs its own ADR; the verifier refuses to emit an
  unfrozen code.

## Note (not a vocabulary decision): `evaluate()` gains optional kwargs

T008 extends `evaluate(policy, expected_sha, evidence_dir)` with two
*optional keyword-only* parameters, `expected_run_id` and
`expected_attempt`, so the CLI `--expected-run-id` /
`--expected-attempt` flags have real semantics (each job must match
the pinned run identity, in addition to the cross-job consistency the
policy requires). All existing calls — including the S0 gate — pass
neither, so behaviour is unchanged when they are omitted. The
extension is recorded here only because it is an interface decision
made in this task; it changes no reason code and no S0 result.
