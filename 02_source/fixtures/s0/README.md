# S0 fixtures — 52 frozen synthetic cases (P027-T004, PROJECT_BOOK §8.1; e5/e6 added by ADR-005, spec v1.1.0; e7/e8 added by ADR-007, spec v1.2.0)

16 normal controls (all `BOUND_PASS`) + 36 planted faults (all detected
with the correct reason code). Frozen by the S0 gate: never delete a
failing fixture, never rewrite Golden to force a pass.

## Layout

```text
fixtures/s0/
  GOLDEN.json            # HAND-WRITTEN expected results, keyed by fixture id
  <fixture-id>/
    policy.toml          # the .benchreceipt.toml for this fixture
    expected.json        # {"expected_source_sha": "<40-hex>"}
    evidence/
      <job-dir>/         # one dir per receipt; the receipt's job_id is
        receipt.json     #   the identity (dir name may differ, see d2)
        artifacts/
          junit.xml      # real bytes; SHA-256 matches the receipt,
          lcov.info      #   except where the fixture plants a mismatch
```

Rebuild deterministically with `python 02_source/scripts/build_fixtures.py`
(fixed SHAs, timestamps, digests; no wall-clock or randomness).

## Synthetic identities

- PR head SHA `aaaa…a`, merge commit SHA `bbbb…b`, other SHA `cccc…c`
- Tree SHAs `dddd…d` / `eeee…e`; workflow run `9001` / `9002`
- All receipts validate against `benchreceipt.run/v1` **except**
  `h4-missing-command`, whose receipt intentionally omits the required
  `command` object — the verifier must answer `INVALID`, not crash.
  Receipts for e5/e6 carry the optional `git.head_sha_after` /
  `git.tree_sha_after` fields (spec v1.1.0, ADR-005) with after values
  that differ from their before values; every other builder-generated
  receipt carries after fields EQUAL to its before values (spec
  v1.2.0, ADR-007, scheme A — the builder simulates current capture
  output). Only e7/e8 carry neither after field, deliberately: they
  are the legacy shape (R1 P0-R1-01) and must fail closed with
  `MISSING_FIELD` (UNBOUND). Their two receipts are byte-identical
  by design — without after fields the clean-checkout scenario (e7)
  and the empty-commit scenario (e8) are indistinguishable.

## Fixture inventory

| IDs | Category | Expected |
|---|---|---|
| `n01`–`n16` | Normal controls: single / multi-matrix / PR head / merge commit / event SHA / explicit SHA / LCOV-only / skipped / policy-relaxed trees & attempts / min_tests boundary / optional fields | 16/16 `BOUND_PASS` |
| `a1`–`a4` | Wrong source SHA / head-merge confusion | `SOURCE_SHA_MISMATCH` (×3), `SOURCE_MODE_MISMATCH` |
| `b1`–`b4` | Tree SHA mixing | `TREE_SHA_MISMATCH` |
| `c1`–`c4` | Run ID / attempt mixing | `RUN_ATTEMPT_MISMATCH`, `RUN_ID_MISMATCH`, both |
| `d1`–`d4` | Matrix missing / duplicate / unexpected | `MATRIX_MISSING_JOB`, `MATRIX_DUPLICATE_JOB`, `MATRIX_UNEXPECTED_JOB` |
| `e1`–`e8` | Source dirty before→after (flag change, digest change, started-dirty, digest-only change) + clean-tree HEAD change (e5) and empty-commit mid-run (e6, ADR-005) + legacy shape with no after fields (e7/e8, ADR-007) | `SOURCE_MUTATED_DURING_RUN`, `MISSING_FIELD` (e7/e8) |
| `f1`–`f4` | Report missing / hash mismatch / required LCOV missing / size lie | `REPORT_MISSING`, `REPORT_HASH_MISMATCH` |
| `g1`–`g4` | JUnit failed / empty / malformed / exit-code contradiction | `JUNIT_FAILED`, `JUNIT_EMPTY`, `JUNIT_MALFORMED`, `EXIT_CODE_MISMATCH` |
| `h1`–`h4` | Workflow mismatch / junit summary missing / below min_tests / receipt missing `command` | `WORKFLOW_MISMATCH`, `MISSING_FIELD`, `POLICY_MISMATCH`, `INVALID_RECEIPT` |

Reason codes, status classes, message templates and the
`jobs_verified` counting rule are frozen in `02_source/docs/REASON_CODES.md`.
