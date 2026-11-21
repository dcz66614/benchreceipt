# REVIEW_PACK_04 — Schema + policy

Frozen candidate: `cfede2711bc54567b918b1f85654c2dd42c30943` (see `REVIEW_INDEX.md`).

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/schema.py` | `7aa6bfcb709e87ed5ba53522d44461ca52cc4eb80bbaaf431b87f0e426327ffc` | 265 | hand-rolled JSON Schema validator (no dependency) |
| `02_source/src/benchreceipt/policy.py` | `683ef274cb87b8777ea04b8bb5ecf3f1dc85c81a6c9902f4dc059a8f6bf4b5e1` | 124 | policy load + validate (benchreceipt.policy/v1) |
| `02_source/schemas/run.v1.json` | `a8c95b12cf237680ed8273fe4cab986f81f061e70da7c97fe31ba59360ca1e2a` | 1 | schema benchreceipt.run/v1 (per-job receipt) |
| `02_source/schemas/policy.v1.json` | `2e555dc3c954b08ac70d2baeb22e449886c88e9ad5dfdc8c7f604daa5312f37a` | 1 | schema benchreceipt.policy/v1 |
| `02_source/schemas/result.v1.json` | `2f16a1024bb589063fa89eeac9ae643b5bea52db1bee0dd73bdf1ff61f30aa11` | 1 | schema benchreceipt.result/v1 |
| `02_source/schemas/README.md` | `401edf54f6dc306cbb512b01ec660f5e4fa4a6a9d3bc21aa138f28d4ab97cb0a` | 87 | schema directory notes (supporting, not a key file) |

## What this pack covers

`schema.py` is a hand-rolled JSON Schema validator (the product
has zero runtime dependencies, so no `jsonschema` package): it is
the only thing standing between an attacker-crafted receipt/policy
and `verify`. `policy.py` loads a TOML policy and validates it
against `benchreceipt.policy/v1`. The three JSON files are the
frozen schemas themselves (`run/v1` = receipt, `policy/v1` =
policy, `result/v1` = verification result).

## Review questions

1. **Validator completeness.** `schema.py` implements a subset
   of JSON Schema (draft 2020-12). List exactly which keywords
   it supports (`type`, `properties`, `required`,
   `additionalProperties`, `pattern`, `enum`, `const`, `min/max`,
   `min/maxLength`, `min/maxItems`, `min/maxProperties`,
   `$ref`, …) and which it ignores. For every keyword a frozen
   schema *uses*, confirm the validator enforces it; for every
   keyword it ignores, confirm no frozen schema relies on it.
   A silently-ignored constraint is a hole.
2. **`$ref` resolution.** `_resolve_ref` resolves local `#/...`
   refs (e.g. `#/$defs/source_state`). Confirm it cannot be
   tricked into resolving an external ref, recursing infinitely
   on a cyclic ref, or resolving to a wrong node via a crafted
   pointer (`~0`/`~1` escapes, array indices).
3. **Pattern strictness.** The schemas pin SHAs with
   `^[0-9a-f]{40}$` / `^[0-9a-f]{64}$`, timestamps with a
   strict UTC pattern, report paths with a no-`..`/no-backslash
   pattern. Confirm the validator anchors patterns as written
   (full-string match, not substring) and that a receipt with an
   uppercase SHA, a `..` report path, or a 1 GiB+1 `size_bytes`
   is rejected. Check the `size_bytes` maximum (1 GiB, ADR-001)
   and the `reports` `maxItems: 32`.
4. **No new required fields without a spec change.** `run.v1`
   was amended by ADR-005 (spec v1.1.0) adding *optional*
   `git.head_sha_after` / `git.tree_sha_after`. Confirm the
   schema still validates pre-v1.1.0 receipts (both after-fields
   absent) and that no required field was added silently.
   Confirm `result.v1` admits no `null` where `verify` might
   emit one (e.g. `expected_source_mode` is omitted, not null,
   on INTERNAL_ERROR).
5. **Policy validation.** `validate_policy` must reject: unknown
   `source_mode`, empty `required_jobs`, duplicate job ids,
   unknown report kinds, `min_tests < 0`, missing
   `expected_workflow`, wrong types (e.g. `same_tree_across_jobs`
   as a string, `run_attempt` as a bool — note Python `bool` is
   an `int` subclass; check the validator rejects bools where
   an integer is required). Confirm an invalid policy can never
   yield a permissive default (no default policy, no pass).
6. **TOML parsing.** `load_policy` uses `tomllib` (stdlib).
   Confirm a missing file, unreadable file, invalid TOML, or a
   TOML document that parses to a non-object all yield
   `PolicyInvalid` (→ INVALID/INVALID_POLICY), never a crash
   and never a partial policy.
7. **Schema / code drift.** The schemas say one thing; `verify`
   and `capture` must do the same. Spot-check: does `capture`
   emit exactly the fields `run.v1` requires (and no extra
   fields, since `additionalProperties: false`)? Does `verify`
   emit exactly what `result.v1` requires? Any drift is a
   finding.
8. **Docs cross-check.** `02_source/schemas/README.md` and
   `02_source/docs/REASON_CODES.md` describe the same contracts
   in prose. Confirm the prose matches the schemas and the code
   (e.g. the reason-code table, the size limits).

## Inlined source

No single function is inlined here: the three schema files are
each a single JSON document (1 line each — see the inventory in
`REVIEW_INDEX.md` for their SHA-256 values) and the reviewer
reads them in full from the checkout. The security-critical
surface is the validator in `schema.py` (`_validate`,
`validate_against_schema`, `_resolve_ref`) and the policy
normaliser in `policy.py` (`validate_policy`, `load_policy`) —
review those functions in full.
