# REVIEW PACK FIXR1-04 — Schema / policy (`02_source/src/benchreceipt/`, schemas)

- **Anchor:** `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`)
- **Pack:** 04 of 06. Files read in full at the anchor commit.
- **Verdict:** no P0/P1 in this pack. This pack covers the R1-noted
  schema migration: all 3 schema JSONs verified at their new paths.
  Two P2 cross-refs: P2-22 (`schemas/README.md`), P2-23
  (`policy.v1.json`).

## Files

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/schema.py` | `3b0ce03abdcdbe34fdc8c66685b3cee84ba3d074192e281792a4c13517b31103` | 270 | schema validation |
| `02_source/src/benchreceipt/policy.py` | `683ef274cb87b8777ea04b8bb5ecf3f1dc85c81a6c9902f4dc059a8f6bf4b5e1` | 124 | policy loading |
| `02_source/src/benchreceipt/schemas/run.v1.json` | `fce85f3decbdcc1043df2ea852f60c7e033b5bd148d498f28704b641c7479166` | 1 | run receipt schema |
| `02_source/src/benchreceipt/schemas/policy.v1.json` | `2e555dc3c954b08ac70d2baeb22e449886c88e9ad5dfdc8c7f604daa5312f37a` | 1 | policy schema |
| `02_source/src/benchreceipt/schemas/result.v1.json` | `2f16a1024bb589063fa89eeac9ae643b5bea52db1bee0dd73bdf1ff61f30aa11` | 1 | result schema |
| `02_source/src/benchreceipt/schemas/README.md` | `27613c955a036837bd20bb3dd2e3e9557373483a6ae49e869ab42bfb07fd4087` | 90 | schema notes |

## What I checked

- **Schema migration (R1 P1-R1-01 context).** All three JSON schemas
  moved `02_source/schemas/` → `02_source/src/benchreceipt/schemas/`
  and were read at the new paths. `policy.v1.json` and
  `result.v1.json` are byte-identical after the move (same SHA-256 as
  the T013 table). Only `run.v1.json` changed: the after fields
  (`git.head_sha_after` / `git.tree_sha_after`) stay optional — only
  their descriptions changed to the ADR-007 fail-closed wording.
  The wheel built from the new `dist.zip` ships all three schemas
  (`benchreceipt/schemas/{run,policy,result}.v1.json`, 27 wheel
  entries total). `schema.py` resolves schemas from the package
  location, so the move is load-bearing and correct — confirmed by
  the legacy-shape repro (schema validation of the after-less receipt
  passes, then verify fails it closed) and by the full pytest run.
- **`schema.py` (270, +5 lines).** Validator loads the moved schemas;
  pattern anchoring note (P2-05, carried): `re.search` + `$` accepts
  a trailing newline — still present.
- **`policy.py` (124, unchanged).** TOML policy loading; duplicate-key
  rejection (F-07) intact; no invented passing defaults (missing
  required fields → `INVALID`); `security.*` defaults to false.
- **`schemas/README.md` (90).** **P2-22:** lines 3–8 and 10–11
  duplicate the "Three JSON Schemas (draft 2020-12), frozen by
  T002…" paragraph; the second copy drops the v1.1.0 amendment
  sentence (ADR-005 adding the two optional after fields). Docs
  only. (Key=no in the T013 inventory; read anyway.)
- **`policy.v1.json`.** **P2-23:** the `schema_version` description
  still says "Only 1 is valid for spec v1.0.0" — the spec is v1.2.0.
  The `const: 1` is correct; description only.
- **`result.v1.json`.** Unchanged; `MISSING_FIELD` maps to UNBOUND
  in `REASON_STATUS` consistently with `verify.py:106` and
  `verify.mjs:55`.

## Spec coherence (this pack's cross-checks)

- `run.v1.json` optional-after-fields + `PROJECT_BOOK.md` §5.5
  fail-closed rule + ADR-007 (overturns ADR-005 decision 4, with the
  n01/e7 indistinguishability proof) are mutually consistent; no
  contradiction found.
- `docs/REASON_CODES.md:39` (table) and `:69–70` (message templates)
  cover both `MISSING_FIELD` triggers (JUnit summary, after
  identity) and match the byte-identical template used by both
  implementations.

## Findings in this pack

- P2-22 (`schemas/README.md:3–8` vs `:10–11`), P2-23
  (`policy.v1.json` `schema_version` description) — see
  `REVIEW_FINDINGS_FIXR1.md`.
- Carried: P2-05, P2-16 (Python side only; the Oracle rejects
  `schema_version=true`).
