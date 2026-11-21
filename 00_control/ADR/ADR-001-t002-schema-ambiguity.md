# ADR-001 — T002 schema ambiguities and frozen interpretations

- **Date:** 2026-11-17
- **Task:** P027-T002 (freeze schemas, policy, canonical JSON)
- **Status:** Accepted (frozen for spec v1.0.0; changing any of these needs a
  spec change, not a quiet schema edit)
- **Blocking?** No — none of these blocks T003. Each point below was
  decided in the fail-closed direction and recorded here instead of being
  silently improvised.

## Context

PROJECT_BOOK v1.0.0 defines the receipt/policy/result shapes in §5.1,
§5.6, §6.2, §6.3 and §12.2/§12.3, but leaves several points open: which
fields are required vs optional, the exact size limits (§11.2 only says
"size limits" exist), the reason-code vocabulary, and a few enum
memberships. The task instruction also differs from the spec in one
place (result status list). All decisions below follow one rule: when in
doubt, choose the stricter / less-assuming option, and never let a
missing value silently become a pass.

## Decisions

### 1. Result status includes INTERNAL_ERROR (spec wins over task text)

- The task text lists the result status enum as
  `BOUND_PASS / BOUND_FAIL / UNBOUND / INVALID`.
- PROJECT_BOOK §5.6 lists five states, adding `INTERNAL_ERROR` (exit 4).
- **Decision:** `result.v1.json` accepts all five. The spec table is
  authoritative; omitting `INTERNAL_ERROR` would make a legitimate
  verifier output schema-invalid.

### 2. §5.1 fields absent from the §6.2 example are OPTIONAL in run.v1

- §5.1 lists `started_at`, `finished_at`, `workflow_ref`,
  `workflow_sha`, and `source_state_before/after`; the §6.2 example
  omits them. `junit` is likewise absent for LCOV-only jobs.
- **Decision:** all of these are optional at schema level. `capture`
  (T003) SHOULD always emit them when available, and the S0 fixtures
  (T004) SHOULD include them, but a receipt missing one is not
  schema-INVALID — whether it is UNBOUND is the verifier's call (T008).
  Making them required would have turned hand-written fixtures and
  LCOV-only jobs into schema failures for no binding benefit.

### 3. `ci.provider` enum is `github-actions` / `generic`

- The spec names GitHub Actions as the first integration and allows
  other CI "through explicit parameters" (§2.2).
- **Decision:** `generic` is the explicit-parameter provider value.
  No other provider strings are valid in v1; a new provider needs a
  schema change.

### 4. Reason codes are shape-frozen, not vocabulary-frozen

- §12.2/§12.3 show `SOURCE_SHA_MISMATCH` and `RUN_ATTEMPT_MISMATCH`
  but never enumerate the full vocabulary; the verifier (T008) owns it.
- **Decision:** `result.v1.json` constrains `reason_codes[]` and
  `report_errors[].code` to uppercase snake-case tokens
  (`^[A-Z][A-Z0-9_]{0,63}$`) but does not enumerate values. T008 must
  freeze the vocabulary (and T004's Golden expected must use it).

### 5. Size limits (spec gives no numbers)

- §11.2 requires "file size, array length and string length" limits
  but sets no values.
- **Decision (frozen values, see `schemas/README.md` for the full
  table):** `job_id` ≤ 128 chars; `matrix` ≤ 32 entries; `reports`
  ≤ 32 entries, `path` ≤ 512 chars, `size_bytes` ≤ 1 GiB; `required_jobs`
  1–128 entries, unique; `reason_codes` ≤ 64; matrix/job-list arrays
  ≤ 128; `run_attempt` 1–100,000; JUnit counts 0–100,000,000. These are
  generous enough that no realistic receipt hits them, tight enough to
  bound untrusted input.

### 6. `security` is the only defaulting section, and it defaults to false

- The task text says `security{...}` fields are "all false by default";
  the §5.6 ban rule says missing required fields must never default to
  a pass.
- **Decision:** both hold. `[security]` is optional and any missing
  field inside it normalises to `false` — that default stores *less*
  data, i.e. it is fail-closed in the privacy direction and can never
  manufacture a pass. Every other policy field is required and a
  missing one raises `PolicyInvalid`.

### 7. `reports` may be empty at schema level

- An empty `reports[]` cannot be `BOUND_PASS`, but that is a
  verification judgement, not a schema property.
- **Decision:** `minItems: 0`. T008 must return `UNBOUND` (or worse)
  for a receipt with no reports; the schema does not do that job.

### 8. `min_tests` schema minimum is 0

- §5.4 requires `tests > 0` for a passing JUnit report.
- **Decision:** the schema allows `min_tests = 0` (structurally valid);
  the `tests > 0` rule is enforced by the verifier (T008), which also
  applies when a policy sets `min_tests = 0`. The schema must not
  duplicate verifier semantics.

### 9. `exit_code` range is -255..255

- Shell exit codes are 0–255, but Python `subprocess` reports
  signal-killed processes with negative returncodes.
- **Decision:** allow -255..255 so `capture` can record a
  signal-terminated command faithfully instead of coercing it.

### 10. `identity_mismatches[]` / `report_errors[]` object shapes

- The spec names these arrays (§12.2) but gives no item shape.
- **Decision (frozen):**
  `identity_mismatches[]` = `{job_id, field, expected?, actual?}`
  where `expected`/`actual` are string/integer/boolean/null;
  `report_errors[]` = `{code, message, job_id?, path?}`.
  T008 must emit exactly these shapes.

### 11. Matrix values are JSON scalars only

- §6.2 shows string values; GitHub matrix values can also be numbers
  or booleans. Nested objects/arrays have no meaning as a job identity.
- **Decision:** `matrix` values are `string | number | boolean`;
  nested values are schema-INVALID.

### 12. `expected_source_sha` / run identity are NOT policy fields

- They are supplied to `verify` on the command line
  (`--expected-source-sha`, §6.4), not stored in the policy.
- **Decision:** `policy.v1.json` has no such fields. A policy that
  contains them is rejected (`additionalProperties: false`).

## Consequences

- T003 must emit the optional §5.1 fields whenever it can, and must
  treat a missing optional field in an *incoming* receipt as "unknown",
  never as a matching value.
- T008 must freeze the reason-code vocabulary and enforce §5.4
  (`tests > 0`), empty-`reports` → not `BOUND_PASS`, and the
  `identity_mismatches` / `report_errors` item shapes above.
- Any change to these decisions requires a spec version bump and a new
  ADR; the schema files alone must not drift.
