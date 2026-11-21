# P027 BenchReceipt — T013 Review Index (REVIEW_INDEX.md)

Master index for the independent read-only code review (T013,
IMPLEMENTATION_PLAN §T013 / §12). The reviewer is a fresh session
that did not build the code. This file states exactly which commit
and which file versions are under review; the reviewer reads the
full files from the checkout at that commit.

## Frozen candidate

- Frozen candidate commit: `cfede2711bc54567b918b1f85654c2dd42c30943`
- Branch built from: `main` at `cfede2711bc54567b918b1f85654c2dd42c30943` (`Control: T012 PASS
  (merge 3b1733d), T013-PREP running; frozen candidate 3b1733d`).
  The production tree at `cfede2711bc54567b918b1f85654c2dd42c30943` is byte-identical to the
  merged T012 content at `3b1733d8e1a4410b68c93e5d67e858cf6cc3060c`
  — the only difference between the two commits is
  `00_control/PROJECT_STATE.json` (control state, not production
  code). T001–T012 all PASS and merged.
- Spec version: **v1.1.0** (`PROJECT_BOOK.md` v1.1.0,
  `IMPLEMENTATION_PLAN.md` v1.1.0, ADR-005).
- Review-pack branch: `t013-prep` (this pack; never merged by the
  builder — a coordinator verifies and merges).
- Repo tree state at pack build: `git status --short` on `main`
  at `cfede2711bc54567b918b1f85654c2dd42c30943` was clean (nothing to commit, working tree
  clean) before `git checkout -b t013-prep`. On `t013-prep` the
  tree adds ONLY the files listed in §File inventory and the
  evidence logs in `03_evidence/t013-prep/` — no production
  file, test, fixture, Golden value, spec, or release file was
  modified (verify with `git status --short` and
  `git diff main --stat`).

## Review scope (IMPLEMENTATION_PLAN §T013 — all six must be reviewed)

1. **Oracle independence** — the Node Oracle re-implements the
   verifier with no shared decision logic (pack 05).
2. **Source mode** — `determine_source_mode` decision table and
   the `expected_source_sha` it yields (pack 01).
3. **Matrix / run attempt** — matrix set comparison and cross-job
   run-id / run-attempt consistency (pack 02).
4. **Hash** — SHA-256 handling everywhere: argv digest, report
   digests, bundle manifest, canonical hash, repeat-100
   (packs 01–03, 06).
5. **Fail-closed behaviour** — every unjudgeable input fails
   (INVALID/UNBOUND/INTERNAL_ERROR), never passes (all packs).
6. **Privacy boundaries** — no secrets, no full argv, no
   environment, no absolute user paths in any receipt, report,
   or log (packs 01, 03, 06).

Completion: 100% coverage of key production files (see
`REVIEW_COVERAGE.csv`), each with a reviewed flag; findings in
`REVIEW_FINDINGS.md` with path / line / reproduction command /
severity. A P0/P1 finding blocks T014 (return to a FIX task).

## How to use this pack

1. Check out the frozen commit: `git checkout cfede2711bc54567b918b1f85654c2dd42c30943` (or
   work on branch `t013-prep` and confirm
   `git diff cfede2711bc54567b918b1f85654c2dd42c30943 -- 02_source/src 02_source/schemas
   02_source/oracle 02_source/pyproject.toml
   02_source/examples` is empty).
2. Read packs 01–06 in order; each pack lists its files with
   SHA-256 + line counts and the review questions for that area,
   and inlines the most security-critical functions verbatim.
3. Run the acceptance commands from `02_source`:
   `python scripts/verify_review_pack.py` (must PASS, exit 0)
   and `python scripts/check_review_coverage.py
   ../../../04_review/REVIEW_COVERAGE.csv` (must PASS once the
   coverage table is complete).
4. Write `04_review/REVIEW_FINDINGS.md` (one finding per
   path/line/repro/severity) and `04_review/REVIEW_COVERAGE.csv`
   (`file,reviewed,pack,notes` — see §Coverage table format).
   Do NOT modify any production file, test, fixture, Golden
   value, spec, or release file. Do NOT commit coverage for a
   file you did not actually read.

## File inventory

Line counts are physical lines (`splitlines()` count; a file with
no trailing newline still counts its last line). `Key = yes`
means the file is a key production file: it must appear in at
least one pack AND in `REVIEW_COVERAGE.csv` with `reviewed=yes`.
`Key = no` means supporting/tooling (listed for completeness;
the coverage checker does not require it).

| Path | SHA-256 | Lines | Pack(s) | Key |
|---|---|---|---|---|
| `02_source/src/benchreceipt/capture.py` | `15ca06363898818561a5026882cbdccb9f6089996ce7f7f6f11166e179bea850` | 609 | 01 | yes |
| `02_source/src/benchreceipt/git_identity.py` | `61f1a53fae80422cf3f6d3b1cb38ac5e9814c948868c85301f590efa2792542a` | 213 | 01 | yes |
| `02_source/src/benchreceipt/ci_metadata.py` | `960ab6c537d39024e45ed213d17cef85d40eedb030876cbdeedc9e2daac0f0ac` | 196 | 01 | yes |
| `02_source/src/benchreceipt/command.py` | `8c6afb5a435ab118ee178c7957a340569467ff9ff68454943c5bb78fee4ef6c2` | 228 | 01 | yes |
| `02_source/src/benchreceipt/canonical.py` | `540d16a88e29e9ccbd1c3959c24b4c16b2a43505a48d8d8830030ae6fc147c88` | 50 | 01 | yes |
| `02_source/src/benchreceipt/verify.py` | `14637b8e1647f218a36ab92866e64b699ee675165e6b0e03e41c34874d125915` | 886 | 02 | yes |
| `02_source/src/benchreceipt/matrix.py` | `6c2cbe8bf70c24a3e48bad10b9df84e9b19df1309a48e3caaa2a692176fe04f3` | 101 | 02 | yes |
| `02_source/src/benchreceipt/reports/junit.py` | `714735dd956b97e9a5e44dd1564605ae8e58b684d51f84fc50df135ab3335fe0` | 199 | 02 | yes |
| `02_source/src/benchreceipt/reports/lcov.py` | `9354b4c1942c4fe2cd0f4c3d413f0a3f6dc1c10acbfe8b3f81c0e91726c95e7c` | 309 | 02 | yes |
| `02_source/src/benchreceipt/bundle.py` | `ce557f6f4ca79497be3b66ce4196ce9c7bae5b7036dc68327cabe118d0af0168` | 788 | 03 | yes |
| `02_source/src/benchreceipt/render/html.py` | `66704da5fad44da9d15d4edef7a5580446926e1d9f92f0e50b5259ec2c9fcf63` | 693 | 03 | yes |
| `02_source/src/benchreceipt/cli.py` | `5bea320be24286a240dd3072e893dcb24311c9f5e973618099d10e13aa510328` | 380 | 03 | yes |
| `02_source/src/benchreceipt/__main__.py` | `30819d5b2ec5058171bac68f863dfb03f1d6b8858116dcca4d2eb15ea08bb278` | 13 | 03 | yes |
| `02_source/src/benchreceipt/__init__.py` | `9d8176dea0c1b4985de66baf505b201ae43f766f2d58fcb6c6484ef7ee1f158c` | 10 | 03 | yes |
| `02_source/src/benchreceipt/render/__init__.py` | `ddec99272b71a4193baecf2c0422118733cc3dc63e27cefa6a2895aad603489d` | 5 | 03 | yes |
| `02_source/src/benchreceipt/reports/__init__.py` | `73c8c07bffb35e8d59420d00de6911bdaf94bff086c337bf299d630daba03527` | 10 | 03 | yes |
| `02_source/src/benchreceipt/schema.py` | `7aa6bfcb709e87ed5ba53522d44461ca52cc4eb80bbaaf431b87f0e426327ffc` | 265 | 04 | yes |
| `02_source/src/benchreceipt/policy.py` | `683ef274cb87b8777ea04b8bb5ecf3f1dc85c81a6c9902f4dc059a8f6bf4b5e1` | 124 | 04 | yes |
| `02_source/schemas/run.v1.json` | `a8c95b12cf237680ed8273fe4cab986f81f061e70da7c97fe31ba59360ca1e2a` | 1 | 04 | yes |
| `02_source/schemas/policy.v1.json` | `2e555dc3c954b08ac70d2baeb22e449886c88e9ad5dfdc8c7f604daa5312f37a` | 1 | 04 | yes |
| `02_source/schemas/result.v1.json` | `2f16a1024bb589063fa89eeac9ae643b5bea52db1bee0dd73bdf1ff61f30aa11` | 1 | 04 | yes |
| `02_source/schemas/README.md` | `401edf54f6dc306cbb512b01ec660f5e4fa4a6a9d3bc21aa138f28d4ab97cb0a` | 87 | 04 | no |
| `02_source/oracle/verify.mjs` | `a693893d6a9210d831c17585c94164a896b4a11ee88cd0e2f5cbf4c7b0c72cc0` | 702 | 05 | yes |
| `02_source/oracle/verify.test.mjs` | `a3589e170b1e89d7bffb99dd01bcc3927ea3f8edd664d65e3eeb7171d1426abc` | 111 | 05 | yes |
| `02_source/oracle/README.md` | `fb4c97d019e2aacd424b7ac3e7871972b30034cdb7c8b62b8ad6df9461d69df5` | 32 | 05 | yes |
| `02_source/pyproject.toml` | `7c52dbd620a09ee1d5ef6eaa81faf1cf18cbe0dc3e65d9f068336daa1f257502` | 47 | 06 | yes |
| `02_source/examples/github-actions/ci.yml` | `9c672a4cafe9be66aac0d6b8a6849f6b90e237d0d29cf73c59c2aee37ffec7cf` | 190 | 06 | yes |
| `02_source/scripts/s0_gate.py` | `da59fe90a851271654f587648809daec51d2fc8b4577aa0e049f70f85ecdd060` | 375 | 06 | yes |
| `02_source/scripts/repeat_hash.py` | `64281520c01f739a8e138804c9b9cf3aa218f7ae9b5ae31f06277aa858f94829` | 64 | 06 | yes |
| `02_source/scripts/validate_workflow_example.py` | `8412a94c666e2edaa5fac597f3d8ff232d27a34967d7a3db73efa193fe9239bb` | 601 | 06 | yes |
| `02_source/scripts/offline_check.py` | `3deb9b75d40088c45192c5150c98c725a6a98e27010deb7c1450c030ca45dfba` | 240 | 06 | yes |
| `02_source/scripts/performance_smoke.py` | `9deb600338dfbc38edf1487c932e86ac4b078b0006a4c9a315801a1ce9b49b7c` | 165 | 06 | yes |
| `02_source/scripts/privacy_scan.py` | `cdb5566b99a8cb95d7532b6bac8dde58cdffe0f3ab0b2b4a2d49eb42814d5363` | 267 | 06 | yes |
| `02_source/scripts/build_fixtures.py` | `8c98f02844fb68ff7f95d535c07c88e23f9a1489750159a3b93318318be883e4` | 567 | 06 | yes |
| `02_source/scripts/ui_smoke.py` | `298de709d1593b1e5c802bc4b7cdae2afe30efc35cd551284b6c3797ddef907d` | 120 | 06 | yes |
| `02_source/scripts/verify_review_pack.py` | `eae974023d4d7b673b561f79fd04d7463604b6aec9076b89d7ab82830b29cff0` | 289 | 06 | no |
| `02_source/scripts/check_review_coverage.py` | `7775da3902ddafed06129dc6f9970b896f457ccf294557efa607bef7cee2d168` | 194 | 06 | no |
| `04_review/REVIEW_PACK_01.md` | `6ebe64ff2feb6b2515f320e09949f3b0cc76862dc404f4681e55214ad5018535` | 326 | pack 01 | no |
| `04_review/REVIEW_PACK_02.md` | `700ed46b29cde3e6e56ec8c743a305546f5b49c8b99ef19209d3f69c9d618734` | 423 | pack 02 | no |
| `04_review/REVIEW_PACK_03.md` | `b209296e670c6e60fcc99458efd683ecfbe665733f6f16d0794ea63cca72f92c` | 218 | pack 03 | no |
| `04_review/REVIEW_PACK_04.md` | `fa329182f264847a6d08b65617fd09a622a722461fa9b4d23de24871132ff552` | 89 | pack 04 | no |
| `04_review/REVIEW_PACK_05.md` | `f2c9d8e34a3d49c256377eebeca2c958e3fca79eb2302e64e11e03cb0ce528f3` | 123 | pack 05 | no |
| `04_review/REVIEW_PACK_06.md` | `66531adf07d65a1bb9bc242fc933be16fba83fd2c1c8bcb884faa39f7b68f9d3` | 114 | pack 06 | no |

Totals: 37 inventoried production/supporting files
(34 key production files) across 6 packs, plus the 6 pack
files above. (`REVIEW_INDEX.md` itself is not listed — a file
cannot inventory its own hash. `REVIEW_COVERAGE.csv` and
`REVIEW_FINDINGS.md` do not exist yet; the reviewer produces them.)

## Specs (pointers, not under review as code)

| File | SHA-256 | Lines | Notes |
|---|---|---|---|
| `01_spec/PROJECT_BOOK.md` | `f9f4ee534f9e7df7aa5ff5346efdf56fbdfef5f5c8f853d33c34aeb323628cca` | 777 | authoritative requirements, v1.1.0 |
| `01_spec/IMPLEMENTATION_PLAN.md` | `023af87b052d7ddd8d4d3ec66f2471b34b081ab876898d219551d8d3bb809847` | 727 | tasks T001–T014, §T013 review scope, §12 release checklist |
| `02_source/docs/REASON_CODES.md` | (see pack 02) | — | frozen 24 reason codes + message templates |
| `02_source/docs/BUNDLE_FORMAT.md` | (see pack 03) | — | bundle manifest format + BUNDLE_* codes |
| `02_source/docs/LIMITATIONS.md` | (see pack 03) | — | known limitations, NOT_TESTED platforms |
| `00_control/ADR/ADR-005-fix-p0-01-after-identity.md` | — | — | spec v1.1.0: `head_sha_after` / `tree_sha_after` (P0-01 fix) |

## S0 fixtures / Golden inventory

- Fixtures: **50** under `02_source/fixtures/s0/` — 16 controls
  (`n01`–`n16`, expected BOUND_PASS) + 34 planted faults
  (`a1`–`a4`, `b1`–`b4`, `c1`–`c4`, `d1`–`d4`, `e1`–`e6`,
  `f1`–`f4`, `g1`–`g4`, `h1`–`h4`, expected UNBOUND / INVALID /
  BOUND_FAIL with frozen reason codes).
- `02_source/fixtures/s0/GOLDEN.json`: SHA-256 `65ccd954142d10cca5885277088924e7fec686047da77592a6eb8140d0ef7870`,
  1 lines. Golden expected values are hand-written;
  never generated from production output.
- Golden SHA-256 (S0 report): `65ccd954142d10cca5885277088924e7fec686047da77592a6eb8140d0ef7870`
  (see `03_evidence/s0/S0_REPORT.md`).

## Evidence logs (latest at pack build, T012)

| Evidence | Log | Result |
|---|---|---|
| Full pytest | `03_evidence/tests/pytest-t012-resume.log` | 676 passed (T012; re-run fresh under `03_evidence/t013-prep/`) |
| S0 gate | `03_evidence/s0/S0_GATE.json`, `03_evidence/s0/S0_REPORT.md` (2026-11-18 00:56 UTC) | PASS 10/10, 50 fixtures, parity 50/50, repeat-100 1 hash, P95 0.0743 s |
| Oracle | `03_evidence/tests/oracle-t012-resume.log` | 8/8 tests pass (`node --test oracle/*.test.mjs`) |
| Privacy scan | `03_evidence/privacy/privacy_scan-t012-resume.log` | 184 files scanned, 0 findings |
| Performance | `03_evidence/performance/performance-t012-resume.json` | P95 0.1481 s (limit 1.0 s), 100 jobs × 100 reps, 0 network requests |
| Offline check | `03_evidence/t012/offline_check-resume.log` | PASS, static CLEAN, 0 socket events |
| Repeat hash | `03_evidence/s0/repeat-hash.log` | 1 distinct hash over 100 replays |
| T012 summary | `03_evidence/t012/T012_SUMMARY.md` | T012 PASS; P1-01 (missing console script) CLOSED |

Fresh T013-prep acceptance logs (pytest, S0 gate, Oracle,
verify-review-pack, coverage synthetic tests) are under
`03_evidence/t013-prep/` — see `T013_PREP_SUMMARY.md` there.
Fresh re-run 2026-11-18 ~01:06–01:08 UTC, all on branch
`t013-prep`: pytest **683 passed** (exit 0); S0 gate **PASS 10/10**
(50 fixtures, parity 50/50, repeat-100 1 hash, P95 0.0989 s);
Oracle **8/8** (`node --test`); `verify_review_pack.py` PASS
(exit 0); `check_review_coverage.py` PASS on synthetic complete
CSV, FAIL naming the missing file on synthetic incomplete CSVs.
The fresh S0 re-run also regenerated `03_evidence/s0/S0_GATE.json`,
`S0_REPORT.md`, `performance.json` (timestamps + P95 timing only:
0.0743 s → 0.0989 s, still ≤ 1 s; verdicts and Golden SHA
unchanged).

## Coverage table format (for the reviewer)

`04_review/REVIEW_COVERAGE.csv`, header row required:

```csv
file,reviewed,pack,notes
02_source/src/benchreceipt/verify.py,yes,02,read in full; findings in REVIEW_FINDINGS.md
```

- `file`: repo-relative path exactly as in §File inventory.
- `reviewed`: `yes` only if the file was actually read in full
  at the frozen commit. Anything else (`no`, blank) fails the
  coverage check.
- `pack`: the pack number(s) that list the file.
- `notes`: optional free text.
- Validate with `python scripts/check_review_coverage.py`
  (from `02_source`); exit 0 only when all 34 key files
  are `reviewed=yes`.

## Pack-check scripts (tooling, not production code)

- `02_source/scripts/verify_review_pack.py` — validates this
  pack (every listed file exists at the frozen commit with the
  recorded SHA-256 + line count; every key production file is
  listed in at least one pack). Run from `02_source`.
- `02_source/scripts/check_review_coverage.py` — validates
  `REVIEW_COVERAGE.csv` against this index. Run from
  `02_source`, optionally with an explicit CSV path.
