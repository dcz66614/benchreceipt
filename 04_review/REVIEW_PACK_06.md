# REVIEW_PACK_06 — CLI packaging, example workflow + scripts

Frozen candidate: `cfede2711bc54567b918b1f85654c2dd42c30943` (see `REVIEW_INDEX.md`).

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/pyproject.toml` | `7c52dbd620a09ee1d5ef6eaa81faf1cf18cbe0dc3e65d9f068336daa1f257502` | 47 | packaging: zero runtime deps, benchreceipt console script |
| `02_source/examples/github-actions/ci.yml` | `9c672a4cafe9be66aac0d6b8a6849f6b90e237d0d29cf73c59c2aee37ffec7cf` | 190 | example CI workflow (bare benchreceipt steps) |
| `02_source/scripts/s0_gate.py` | `da59fe90a851271654f587648809daec51d2fc8b4577aa0e049f70f85ecdd060` | 375 | S0 gate: 10 thresholds, 50 fixtures, parity check |
| `02_source/scripts/repeat_hash.py` | `64281520c01f739a8e138804c9b9cf3aa218f7ae9b5ae31f06277aa858f94829` | 64 | repeat-100 canonical-hash check |
| `02_source/scripts/validate_workflow_example.py` | `8412a94c666e2edaa5fac597f3d8ff232d27a34967d7a3db73efa193fe9239bb` | 601 | validates ci.yml against the policy |
| `02_source/scripts/offline_check.py` | `3deb9b75d40088c45192c5150c98c725a6a98e27010deb7c1450c030ca45dfba` | 240 | static network-token scan + socket-trace run |
| `02_source/scripts/performance_smoke.py` | `9deb600338dfbc38edf1487c932e86ac4b078b0006a4c9a315801a1ce9b49b7c` | 165 | P95 <= 1s over 100 manifests x 100 reps |
| `02_source/scripts/privacy_scan.py` | `cdb5566b99a8cb95d7532b6bac8dde58cdffe0f3ab0b2b4a2d49eb42814d5363` | 267 | scans receipts for secrets / absolute paths |
| `02_source/scripts/build_fixtures.py` | `8c98f02844fb68ff7f95d535c07c88e23f9a1489750159a3b93318318be883e4` | 567 | builds the 50 S0 fixtures + GOLDEN.json |
| `02_source/scripts/ui_smoke.py` | `298de709d1593b1e5c802bc4b7cdae2afe30efc35cd551284b6c3797ddef907d` | 120 | HTML report smoke check (external refs) |

## Pack tooling (reviewed as tooling, not as production code)

The two scripts below are new on the `t013-prep` branch; they
validate this pack and the reviewer's coverage table. They are
NOT production code under review, and their SHA-256 values are
verified against the working tree (they do not exist at the
frozen commit). The reviewer should still read them — a bug here
could falsely bless an incomplete pack.

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/scripts/verify_review_pack.py` | `eae974023d4d7b673b561f79fd04d7463604b6aec9076b89d7ab82830b29cff0` | 289 | pack tooling: validates this review pack (NOT production code under review) |
| `02_source/scripts/check_review_coverage.py` | `7775da3902ddafed06129dc6f9970b896f457ccf294557efa607bef7cee2d168` | 194 | pack tooling: validates REVIEW_COVERAGE.csv (NOT production code under review) |

## What this pack covers

`pyproject.toml` (packaging + the `benchreceipt` console script)
and the example GitHub Actions workflow are the two files a real
user's CI actually executes. The eight scripts are product-adjacent
tooling: the S0 gate, the repeat-hash / offline / performance /
privacy checks, the workflow validator, the fixture builder, and
the UI smoke check. They are not shipped to users, but the S0
gate and the privacy/offline scans are load-bearing for the
project's own claims — a bug in `s0_gate.py` could hide a
production failure.

## Review questions

1. **Console script (FIX-P1-01).** `pyproject.toml` declares
   `benchreceipt = "benchreceipt.cli:main"` and zero runtime
   dependencies. Confirm the `[project.scripts]` entry, the
   `requires-python >= 3.12`, and the MIT licence are all as
   specified, and that no dependency crept into `dependencies`.
   Confirm `cli.main` returns an int (not `None`) so the console
   script exit code is meaningful.
2. **Example workflow.** `examples/github-actions/ci.yml` runs
   bare `benchreceipt capture` / `benchreceipt verify` steps.
   Confirm every step the workflow runs exists in `cli.py` with
   the same flags, that the workflow captures the evidence the
   policy requires (JUnit + LCOV paths match the receipts), and
   that no step can silently swallow a non-zero exit code
   (`set -e` / step failure semantics). Confirm
   `validate_workflow_example.py` actually checks what it claims
   (its hand-rolled YAML-subset parser is the risk: list the
   YAML constructs it cannot parse and whether the example uses
   any of them).
3. **S0 gate integrity.** `s0_gate.py` runs the 10 thresholds
   against the 50 fixtures. Confirm it cannot pass spuriously:
   it compares production *and* Oracle verdicts against the
   hand-written `GOLDEN.json` (never generated from production
   output); a fixture whose verdict differs from Golden fails
   the gate; the repeat-100 check requires exactly 1 distinct
   canonical hash; the P95 check actually runs the perf script
   (exit 0 required); the privacy check scans real receipts.
   Is there a failure mode the gate would miss (e.g. a fixture
   directory silently skipped, a threshold compared with `>=`
   instead of `==`)?
4. **Fixture builder trust.** `build_fixtures.py` generates the
   50 fixtures *and* `GOLDEN.json`. Confirm Golden's expected
   values are hand-written in the builder (asserted, not copied
   from a verifier run) — if any expected value were derived by
   running production code, the S0 gate would be circular. Check
   the fixture count (50: 16 controls + 34 planted faults) and
   that the builder refuses to overwrite a frozen fixture set
   without an explicit flag.
5. **Offline check.** `offline_check.py` does a static scan for
   network tokens in `src/` + the Oracle and a dynamic
   socket-audit run. Confirm the token list covers the real
   network APIs (`socket`, `urllib`, `requests`, `http.client`,
   `fetch`, `net`, …) and that the dynamic trace actually
   exercises `capture` + `verify` (not just imports them).
6. **Privacy scan.** `privacy_scan.py` scans receipts for secret
   keys/values and absolute user paths. Confirm its secret-key
   list and its path patterns, and check for false negatives:
   a secret stored under an unusual key, a Windows absolute
   path, a base64-looking token. (Its latest run: 184 files, 0
   findings — see `03_evidence/privacy/`.)
7. **Performance smoke.** `performance_smoke.py` measures P95
   over 100 manifests × 100 reps with a 1 s limit. Confirm the
   measurement covers manifest building (not just hashing) and
   that the P95 computation is correct (sorted samples,
   95th-percentile index).
8. **Repeat hash.** `repeat_hash.py` replays 100 times and
   requires 1 distinct canonical hash. Confirm it replays the
   *same* inputs (not re-randomised ones) and hashes the
   canonical form (not wall-clock-dependent fields).
9. **UI smoke.** `ui_smoke.py` checks the HTML report has no
   external references. Confirm what it checks (no `http(s)://`
   in `src`/`href`, no external fonts/scripts) and whether a
   crafted verification result could inject one.
10. **Pack tooling (this pack's two scripts).** Confirm
    `verify_review_pack.py` really does fail on a tampered SHA,
    a wrong line count, and an unlisted key file (test with a
    scratch copy in /tmp, not by editing the pack), and that
    `check_review_coverage.py` fails on a missing/unreviewed
    file and passes on a complete table. A checker that cannot
    fail is worse than no checker.
