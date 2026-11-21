# REVIEW_PACK_05 — Oracle independence

Frozen candidate: `cfede2711bc54567b918b1f85654c2dd42c30943` (see `REVIEW_INDEX.md`).

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/oracle/verify.mjs` | `a693893d6a9210d831c17585c94164a896b4a11ee88cd0e2f5cbf4c7b0c72cc0` | 702 | independent Node re-implementation of verify |
| `02_source/oracle/verify.test.mjs` | `a3589e170b1e89d7bffb99dd01bcc3927ea3f8edd664d65e3eeb7171d1426abc` | 111 | Oracle tests (node --test), 8 tests |
| `02_source/oracle/README.md` | `fb4c97d019e2aacd424b7ac3e7871972b30034cdb7c8b62b8ad6df9461d69df5` | 32 | Oracle notes: independence rules |

## What this pack covers

The Oracle is an *independent* re-implementation of the verifier
in Node.js (no Python, no shared code with `src/benchreceipt/`).
It exists so that a bug in the production verifier cannot bless
itself: the S0 gate requires production/Oracle parity on all 50
fixtures (50/50 at the frozen commit). `verify.test.mjs` is its
own test suite (`node --test`, 8 tests).

## Review questions

1. **True independence.** Confirm the Oracle imports nothing
   from `02_source/src/` and shares no code with the production
   verifier (no copied helper, no shared schema file at runtime
   — it reads the same frozen JSON schemas, which is intended:
   the *schemas* are shared, the *decision logic* is not).
   Confirm it has zero npm dependencies and makes zero network
   requests (S0 threshold 8 requires 0 network tokens in both
   implementations).
2. **Same verdicts, independently derived.** Compare
   `oracle/verify.mjs: evaluate()` against
   `src/benchreceipt/verify.py: _evaluate_inner()` line by line:
   matrix comparison, identity checks, mutation checks, report
   checks, JUnit summary checks, exit-code contradiction,
   five-state aggregation with the same precedence. List every
   behavioural difference, however small (e.g. reference-value
   selection, duplicate handling, sort orders, error-message
   wording). A difference that changes a verdict on any input
   is a finding; a difference that changes only message text
   must be recorded as such.
3. **Same reason vocabulary.** Confirm the Oracle's
   `REASON_STATUS` (inlined below) is exactly the frozen 24
   codes with the same status classes as `verify.REASON_STATUS`,
   and that an unknown code is handled fail-closed (not shipped
   as a pass).
4. **Same fail-closed behaviour.** Missing evidence dir, invalid
   policy, malformed receipt, malformed JUnit, missing report:
   confirm each yields INVALID/UNBOUND in the Oracle exactly as
   in production, and that the Oracle never throws for bad input
   (its CLI exit codes must match §5.6: 0/1/2/3/4).
5. **TOML parsing.** The Oracle parses policy TOML by hand
   (`parseToml`, `parsePolicyToml`) — Node has no stdlib TOML
   parser. This is the highest-risk Oracle surface: confirm it
   handles quoting, escapes, comments, duplicate keys, and
   malformed input the same way `tomllib` does for every policy
   the S0 fixtures use, and that a policy that parses
   differently in the two parsers cannot change a verdict.
   (If the hand parser is weaker than `tomllib`, say exactly
   where — and whether it matters for verdicts.)
6. **JUnit minimal parser.** `parseJUnitMinimal` is a regex /
   string parser, not a full XML parser. Confirm it counts the
   same elements as production's `parse_junit` on every JUnit
   file in the S0 fixtures, and probe adversarial inputs:
   nested `<testsuites>`, namespaced tags, `<failure>` inside
   CDATA, entities, a count attribute disagreeing with counted
   elements, malformed XML. Any divergence that changes a
   verdict is a finding.
7. **Hashing.** `sha256File` must hash exact bytes (streamed,
   no newline normalisation). Confirm report digests computed by
   the Oracle equal production's on every S0 fixture file.
8. **Test independence.** `verify.test.mjs` (8 tests) must not
   import production code and must exercise the Oracle alone.
   Confirm the 8 tests cover the spec §12.3 samples (mixed
   attempt → UNBOUND/RUN_ATTEMPT_MISMATCH; wrong source SHA →
   UNBOUND/SOURCE_SHA_MISMATCH) and the control fixture.

## Inlined source (verbatim — do not paraphrase)

### `oracle/verify.mjs` — status order, reason vocabulary, exit codes

```javascript
const STATUS_ORDER = ["INVALID", "UNBOUND", "BOUND_FAIL", "BOUND_PASS"];

const REASON_STATUS = {
  SOURCE_SHA_MISMATCH: "UNBOUND",
  SOURCE_MODE_MISMATCH: "UNBOUND",
  TREE_SHA_MISMATCH: "UNBOUND",
  RUN_ID_MISMATCH: "UNBOUND",
  RUN_ATTEMPT_MISMATCH: "UNBOUND",
  WORKFLOW_MISMATCH: "UNBOUND",
  MATRIX_MISSING_JOB: "UNBOUND",
  MATRIX_DUPLICATE_JOB: "UNBOUND",
  MATRIX_UNEXPECTED_JOB: "UNBOUND",
  SOURCE_MUTATED_DURING_RUN: "UNBOUND",
  REPORT_MISSING: "UNBOUND",
  MISSING_FIELD: "UNBOUND",
  REPORT_HASH_MISMATCH: "INVALID",
  JUNIT_MALFORMED: "INVALID",
  JUNIT_SUMMARY_MISMATCH: "INVALID",
  INVALID_RECEIPT: "INVALID",
  INVALID_POLICY: "INVALID",
  INVALID_EVIDENCE: "INVALID",
  JUNIT_FAILED: "BOUND_FAIL",
  JUNIT_EMPTY: "BOUND_FAIL",
  EXIT_CODE_MISMATCH: "BOUND_FAIL",
  POLICY_MISMATCH: "BOUND_FAIL",
};

const EXIT_BY_STATUS = {
  BOUND_PASS: 0,
  BOUND_FAIL: 1,
  UNBOUND: 2,
  INVALID: 3,
  INTERNAL_ERROR: 4,
};

// ---------------------------------------------------------------------------
// Minimal TOML parser: only the subset .benchreceipt.toml uses.
// Supports top-level key = value (string / integer / boolean / array of
// strings), [section] headers, and [reports] / [security] tables.
// Anything else is a parse error (policy INVALID, fail-closed).
// ---------------------------------------------------------------------------
```
