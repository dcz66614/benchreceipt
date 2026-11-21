# Frozen schemas — P027 BenchReceipt v1.2.0 (P027-T002; amended by ADR-005, ADR-007)

Three JSON Schemas (draft 2020-12), frozen by T002. They are the contract
T003+ builds on; changing a required field, an enum, or a limit needs a
spec change (ADR + SPEC_VERSION bump), not a quiet edit here. The v1.1.0
amendment (ADR-005, P0-01 fix) adds two OPTIONAL fields to
`benchreceipt.run/v1` only — `git.head_sha_after` /
`git.tree_sha_after` — and changes no required field, enum, or limit.

Three JSON Schemas (draft 2020-12), frozen by T002. They are the contract
T003+ builds on; changing a required field, an enum, or a limit needs a
spec change (ADR + SPEC_VERSION bump), not a quiet edit here.

| File | Schema id | Source |
|---|---|---|
| `run.v1.json` | `benchreceipt.run/v1` | PROJECT_BOOK §5.1, §6.2 |
| `policy.v1.json` | `benchreceipt.policy/v1` | PROJECT_BOOK §6.3 (parsed TOML form) |
| `result.v1.json` | `benchreceipt.result/v1` | PROJECT_BOOK §5.6, §12.2/§12.3 |

Validation is stdlib-only: `src/benchreceipt/schema.py` implements the
small JSON Schema subset these files use (`type`, `const`, `enum`,
`required`, `properties`, `additionalProperties`, `propertyNames`,
`items`, length/count bounds, `pattern`, `minimum`/`maximum`, local
`$ref`). There is deliberately **no `jsonschema` dependency** — runtime
dependencies must stay empty.

## Frozen decisions

- **After-identity fields (v1.1.0, ADR-005; fail-closed since v1.2.0, ADR-007).** `git.head_sha_after` /
  `git.tree_sha_after` are OPTIONAL 40-hex SHAs recording HEAD/tree at
  capture end. Capture always emits them; verify flags
  `SOURCE_MUTATED_DURING_RUN` when either differs from its before
  value, or when only one of the two is present (fail closed), and
  flags `MISSING_FIELD` (UNBOUND) when BOTH are absent — a receipt
  with no after identity cannot prove the run's HEAD/tree did not
  change, so it must not `BOUND_PASS` on the dirty/digest checks
  alone (ADR-007 overturns the ADR-005 decision 4 compat rule).
  No `source_mutated_during_run` boolean was added: the two after
  SHAs preserve the evidence of *what* the run ended on, and the
  flag is derivable from them.
- **No new required fields.** `benchreceipt.run/v1` requires exactly
  `schema`, `job_id`, `matrix`, `git`, `ci`, `command`, `runner`,
  `reports`. Everything else in §5.1 (`started_at`, `finished_at`,
  `junit`, `source_state_before/after`, `ci.event_name`,
  `ci.workflow_ref`, `ci.workflow_sha`) is optional at schema level so
  hand-written fixtures and LCOV-only jobs validate; `capture` (T003)
  SHOULD still always emit them when available.
- **SHAs are full lowercase hex**: git SHAs 40 hex, digests 64 hex.
  Abbreviated SHAs are rejected.
- **Enums frozen**: `source_mode` = `pr_head` / `merge_commit` /
  `event_sha` / `explicit_sha`; report `kind` = `junit` / `lcov`;
  `ci.provider` = `github-actions` / `generic`; result `status` =
  `BOUND_PASS` / `BOUND_FAIL` / `UNBOUND` / `INVALID` /
  `INTERNAL_ERROR` (§5.6 table; the task text listed four, the spec
  lists five — see ADR-001).
- **Paths are relative only**: `reports[].path` rejects a leading `/`,
  any `..` segment, backslashes, `//`, and a trailing `/`.
- **Policy fail-closed**: every field in §6.3 except `[security]` is
  required; `required_jobs` must be non-empty; both `reports.junit`
  and `reports.lcov` must be declared explicitly. The only default is
  `security.* = false` (store less, never more). A missing/invalid
  policy is `INVALID`, never a passing default.
- **Reason codes are not frozen as an enum** in `result.v1.json` — only
  their shape (uppercase snake-case tokens). The vocabulary is owned
  by the verifier (T008).
- **Expected SHA / run id are NOT policy fields**: they are passed to
  `verify` on the command line (`--expected-source-sha`, PROJECT_BOOK
  §6.4), so they do not appear in `policy.v1.json`.

## Frozen size limits (no numbers in the spec — see ADR-001)

| Limit | Value |
|---|---|
| `job_id`, required-job id | 1–128 chars |
| `matrix` | 1–32 entries; keys ≤ 64 chars; values JSON scalars only |
| `command.display` | ≤ 512 chars |
| `reports` | ≤ 32 entries; `path` ≤ 512 chars; `size_bytes` ≤ 1 GiB |
| `reports[].size_bytes` | 0 – 1,073,741,824 |
| `required_jobs` | 1–128 entries, unique |
| `reason_codes` | ≤ 64 entries |
| `missing/unexpected/duplicate_jobs`, `identity_mismatches`, `report_errors` | ≤ 128 entries each |
| `ci.run_attempt` | 1 – 100,000 |
| `junit` counts | 0 – 100,000,000 |

## Canonical JSON (see `src/benchreceipt/canonical.py`)

Sort keys, UTF-8, `ensure_ascii=False`, separators `(",", ":")`, no
whitespace, `allow_nan=False`. Digest = SHA-256 of the canonical bytes.
Test vectors live in `tests/canonical/vectors.json`; their SHA-256 values
were computed independently of the implementation.
