# Oracle — independent Node.js verifier (P027-T004)

`oracle/verify.mjs` is an independent implementation of the PROJECT_BOOK
§5 rules (matrix, identity, report integrity, source mutation,
four-state aggregation) in Node.js 24 ESM. It does **not** import, call,
or copy any production Python module — the TOML parser, receipt checks,
JUnit counting, SHA-256 recomputation, and status aggregation were
written from the spec alone, sharing only the fixture files and the
frozen reason-code list (`02_source/docs/REASON_CODES.md`).

## CLI contract (frozen for T005–T008)

```bash
node oracle/verify.mjs --policy <toml> --expected-source-sha <sha> --evidence <dir>
```

Prints the `benchreceipt.result/v1` JSON to stdout. Exit code follows
§5.6: `BOUND_PASS` 0, `BOUND_FAIL` 1, `UNBOUND` 2, `INVALID` 3,
`INTERNAL_ERROR` 4.

## Tests

```bash
node --test 02_source/oracle/*.test.mjs
```

Node built-ins only (`node:test`, `node:fs`, `node:crypto`). No npm deps.

## Status

S0 gate (PROJECT_BOOK §8.3): production / Oracle parity 52/52 — see
`03_evidence/s0/S0_GATE.json`. That claim covers the 52 frozen S0
fixtures only. Parity beyond the fixtures is pinned by the 69-case
parity corpus (`02_source/tests/test_oracle_parity_r13b.py`, which runs
production `evaluate()` and the Oracle CLI on the same evidence and
asserts identical status, reason codes, report errors, identity
mismatches and exit code), the 26 Node tests in `verify.test.mjs`,
and the T013 reviewer repro corpus (`03_evidence/t013-review/repro*.py`,
re-run green after FIX-R13b). It is **not** a claim that the Oracle
agrees with production on every possible input. Known remaining
divergences (all fail-closed, recorded in `03_evidence/fix-r13b/SUMMARY.md`
and `05_release/FREEZE_REPORT.md`):

- Symlinked `receipt.json` / job dirs: the Oracle rejects a receipt or
  job dir whose real path escapes its root (`INVALID_RECEIPT`); production
  `verify` reads symlinked receipts straight through (T013 P2-18).
- Giant integers (>4300 digits, P2-06): production leaks `ValueError` to
  `INTERNAL_ERROR`; the Oracle treats an over-long integer as malformed
  (`INVALID`).
- Float-form integers in JSON (e.g. `run_attempt: 2.0`): Python rejects
  them; `JSON.parse` yields `2`, which the Oracle accepts.
- Policy `schema_version = true` (P2-16): Python accepts (`True == 1`);
  the Oracle rejects it.
- UTF-16 / non-UTF-8 JUnit: production decodes per the XML declaration;
  the Oracle strictly decodes UTF-8 and calls anything else malformed.
- CLI `--expected-attempt abc`: Python argparse exits 2, the Oracle exits 3.
- Missing `--policy` / `--evidence`: the Oracle exits 4 (Python argparse
  exits 2) — pre-existing behaviour, untouched by FIX-R13b.
