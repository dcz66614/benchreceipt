# P027 BenchReceipt — FIX-R1 Validator Redirect + Second Re-freeze Summary (v1.2.0, release r1)

> **✅ FREEZE VALID.** Validator redirect done in the scripts
> themselves (P2-28 fixed); second re-freeze on branch `fix-r1`.
> `scripts/verify_release.py` **PASS, exit 0** (3 runs, all
> byte-identical, offline-install check included every time).
> No STOP condition was hit; the only `02_source` change vs
> `66502f6` is the two validator scripts.

## 1. Commits (branch `fix-r1`)

| Role | Commit | Subject |
|---|---|---|
| FIX-R1 | `737e0b17a975f14f080bd4c27077e6bab215b273` | FIX-R1: fail-closed legacy after-identity (P0-R1-01), Scheme A |
| Previous frozen commit | `66502f6255976b44b3efebb7da778ea8807b1ba1` | Control: FIX-R1 re-verification evidence (frozen-tree candidate) |
| Previous release commit | `b221401ba5a8ddc713249f8d04f2804caf4b0e53` | Release: re-freeze r1 on FIX-R1 (frozen commit 66502f6) — FREEZE VALID |
| Frozen commit (this work) | `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09` | Control: validator redirect + re-verification evidence (frozen-tree candidate) |
| Release commit | `213677f0df7cfda427a3ef6d5558ffecadd91d26` | Release: second re-freeze r1, validator redirect (frozen commit 2b1ba19) — FREEZE VALID |
| Control commit (this file) | on top of the release commit — see `git log` | Control: FIX-R1 validator-redirect re-freeze summary (this file) |

- HEAD at release-commit time: `213677f0df7cfda427a3ef6d5558ffecadd91d26`.
- The frozen commit's `02_source` tree differs from `66502f6`
  ONLY in the two validator scripts (§2, §8); the 34 FIX-R1 key
  production files are byte-identical (§8).
- The release commit's `02_source` tree is identical to the frozen
  commit's tree: `git diff 2b1ba19 <release> -- 02_source` is
  **empty** (0 lines).
- Working tree after both commits: **clean** (`git status
  --porcelain` empty).
- Spec version: **1.2.0**. Release ID: **r1** (fifth freeze of r1).
- No merge, no R2 submission, no GitHub upload (not authorized).

## 2. Task 1 — validator redirect (what changed)

### `02_source/scripts/verify_review_pack.py` (253 → 289 lines)

- `--index` (default `04_review/REVIEW_INDEX.md`) and
  `--pack-glob` (default `REVIEW_PACK_*.md`, matched inside
  `04_review/`); docstring documents the new parameters.
- `_is_key_production`: the `02_source/schemas/*.json` rule is
  extended to the post-T014-F1 location
  `02_source/src/benchreceipt/schemas/*.json` (old location kept,
  so packs anchored before the move still validate). Key files at
  `66502f6` by validator definition: 31 → **34**, matching the
  FIXR1 index's 34 `Key = yes` rows.
- New SHA-256: `eae974023d4d7b673b561f79fd04d7463604b6aec9076b89d7ab82830b29cff0`
  (old `f1c6b2d7defb6092df07e3f2d9ec8a2c2290cdf9cbcc4b7f9d3e244ec05ace03`).

### `02_source/scripts/check_review_coverage.py` (125 → 194 lines)

- `--index` (default `04_review/REVIEW_INDEX.md`) and
  `--pack-glob` (accepted for a uniform validator CLI; ignored —
  coverage is per-index, not per-pack; documented in the docstring).
- Default coverage CSV is derived from the index name:
  `REVIEW_INDEX*.md` → `REVIEW_COVERAGE*.csv`
  (`REVIEW_INDEX_FIXR1.md` pairs with
  `REVIEW_COVERAGE_FIXR1.csv`); an explicit positional CSV still
  overrides. (First version derived a `.md` name and failed on the
  missing file; fixed to `.csv` before any freeze step.)
- Accepts the FIXR1 CSV format (`path_at_66502f6` / `key`
  columns) in addition to the standard (`file` / `reviewed`)
  format; a FIXR1 row counts as reviewed when `key` is `yes`
  (every row of that table is a file the reviewer covered, in the
  pack named by its `pack` column).
- New SHA-256: `7775da3902ddafed06129dc6f9970b896f457ccf294557efa607bef7cee2d168`
  (old `70cbffe17efc8f5c311730b041cbb5d99a20eed5be1a49d9f12a5ce230d67515`).

### Tests

- No test covers either script: `grep -rln
  "verify_review_pack|REVIEW_INDEX" 02_source/tests/` returns
  nothing. Per the task ("若 tests/ 里有这两个脚本的测试，一并
  更新") no test was added — adding one would have put a new file
  into the frozen production tree, breaking the §8 diff discipline.

### Why review inventory rows were re-recorded (not a scope creep)

The validator reads the two scripts from the **working tree**,
and both indexes + both pack-06 files record their SHA-256 +
line counts. Editing the scripts therefore broke those rows —
proven live, not assumed: the first post-edit run showed exactly
8 script-row mismatches on the new FIXR1 call and would have
added 6 to the old default call (34 → 40 problems). The fix is
mechanical re-recording, no content change:

| File | Rows re-recorded |
|---|---|
| `04_review/REVIEW_INDEX.md` | 2 script rows + 1 `REVIEW_PACK_06.md` row (its bytes changed with the script rows) |
| `04_review/REVIEW_PACK_06.md` | 2 script rows (new pack SHA `66531adf07d65a1bb9bc242fc933be16fba83fd2c1c8bcb884faa39f7b68f9d3`, 114 lines) |
| `04_review/REVIEW_INDEX_FIXR1.md` | 2 script rows + 1 `REVIEW_PACK_FIXR1_06.md` row |
| `04_review/REVIEW_PACK_FIXR1_06.md` | 2 script rows (new pack SHA `7ddaacde28c8809cdfb2ffbacb9f7d6a4a2e9dda17d79a3c5fb085c543bb99df`, 103 lines) |

The `REVIEW_COVERAGE_FIXR1.csv` `sha256_at_66502f6` column was
NOT touched: it records the hashes AT commit `66502f6`, which
are unchanged. Prose line citations in the review docs (e.g.
`check_review_coverage.py:71`, "(253)") now refer to the
pre-redirect versions; only the machine-checkable inventory
rows were updated. Intermediate logs
(`verify-review-pack-*-prererecord.log`) preserve the
pre-rerecord failures as evidence.

## 3. Task 1 — old vs new calls (all run by this worker)

| Call | Exit | Result | Log |
|---|---|---|---|
| `verify_review_pack.py` (default, **pre-change baseline**) | 1 | FAIL 34 problems (old `cfede271` anchor) | `verify-review-pack-OLD-default-baseline.log` — byte-identical to the reviewer's `03_evidence/fix-r1-review/verify-review-pack-post-reformat.log` (`diff` empty) |
| `verify_review_pack.py` (default, **post-change**) | 1 | FAIL 34 problems, **output byte-identical to the baseline** (`diff` empty) | `verify-review-pack-NEW-default.log` |
| `verify_review_pack.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'` | 0 | **PASS** — commit `66502f6255976b44b3efebb7da778ea8807b1ba1`, 43 index rows, 37 pack rows, 34 key production files all listed in 6 packs, all SHA-256 + line counts match | `verify-review-pack-NEW-fixr1.log` |
| `check_review_coverage.py` (default, **pre-change baseline**) | 0 | PASS — all 34 key files reviewed | `check-review-coverage-OLD-default-baseline.log` |
| `check_review_coverage.py` (default, **post-change**) | 0 | PASS — **output byte-identical to the baseline** (`diff` empty) | `check-review-coverage-NEW-default.log` |
| `check_review_coverage.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'` | 0 | **PASS** — all 34 key production files reviewed in `04_review/REVIEW_COVERAGE_FIXR1.csv` | `check-review-coverage-NEW-fixr1.log` |

## 4. Old → new hash对照表 (no old hash reused)

| File | Old (FIX-R1 re-freeze, frozen `66502f6`) | New (this re-freeze, frozen `2b1ba19`) |
|---|---|---|
| `source.zip` | `873b4dc43252202b17432c619397254a480e2dcfe10b43b7404d14b0efcd420b` (431,740 B, 355 files, 1,156,533 source bytes) | `15d1dd0bcfd217cc060ba1501c9205c9aa2fde9300c5734077867b664cac54af` (433,074 B, 355 files, 1,160,832 source bytes) |
| `dist.zip` | `da900faf679551ab6599c2ed333923bc151032957ceba2542ff065a51fc1bacd` (152,883 B) | `eb73174ab6e51069d2565ebd793d91369b772c33115cf2ba91926bd21b2b48b1` (152,880 B) |
| bundle | `86c4c82ed019803d349997c5708d62805b918c7b89675e181a20b5f4d00d0dc8` (`benchreceipt-66502f625597.bundle`, 3,844,063 B) | `79faf42ab7b5d9487cea9bdec8b24f69b56c4dc3ef0c74dd9a5b7d016f5474b1` (`benchreceipt-2b1ba19f7f46.bundle`, 4,622,659 B) |

- Old bundle file `benchreceipt-66502f625597.bundle` was **deleted**
  from `05_release/` (it would otherwise fail the validator's
  no-unlisted-files check). `05_release/` now holds exactly 7
  files: `.gitkeep`, `FREEZE_REPORT.md`, `RELEASE_MANIFEST.json`,
  `SHA256SUMS.txt`, `benchreceipt-2b1ba19f7f46.bundle`, `dist.zip`, `source.zip`.
- `dist.zip` contents (4 entries): `INSTALL.txt` (721 B), `LICENSE`
  (1,082 B), `benchreceipt-0.1.0-py3-none-any.whl` (80,150 B, 27
  entries incl. `benchreceipt/schemas/{run,policy,result}.v1.json`),
  `benchreceipt-0.1.0.tar.gz` (73,334 B). Wheel METADATA:
  `License-Expression: MIT`, `Requires-Python: >=3.12`, zero
  runtime dependencies.

## 5. Manifest gates (`05_release/RELEASE_MANIFEST.json`)

- `spec_version`: `1.2.0`; `frozen_commit`:
  `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`.
- `pytest_passed`: **848** (failed 0); `oracle_tests_passed/total`:
  **26/26**.
- `s0_verdict`: **S0 PASS**; controls **16/16**; faults **36/36**;
  parity **52/52**; false PASS **0**; false block **0**;
  repeat distinct hashes **1**; repeat hash
  `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530`;
  golden SHA-256
  `fb8e70a136aef710fb59d46addda99df71bafb18320afb23d75b61bf21560497`;
  reason-codes SHA-256
  `16feb3b809021e410a94c0ccb0a64dfd012cbc8ad72c869c6741747090f4a8e5`;
  P95 `0.0924846160000925` s; privacy violations **0**; offline
  network refs **0**; `s0_generated_at` `2026-11-18T04:33:36.163958Z`.
- `files` list (6 entries + the manifest itself): `.gitkeep`,
  `FREEZE_REPORT.md`, `benchreceipt-2b1ba19f7f46.bundle`,
  `dist.zip`, `source.zip`, `SHA256SUMS.txt`.
- **P2-R1-01:** `05_release/.gitkeep` exists (0 bytes, sha
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`),
  listed in `SHA256SUMS.txt` and in the manifest `files` list.

## 6. Gates re-run fresh by this worker (all exit 0 unless noted)

All from `02_source` with `../.venv/bin/python` (Python 3.12.3,
Node v24.22.1), `TMPDIR=~/workspace/p027-benchreceipt/.tmp/validator-refreeze-tmp`.
Logs in `03_evidence/fix-r1-validator-refreeze/`.

| Gate | Result | Log |
|---|---|---|
| Full pytest | **848 passed** in 39.93 s (re-run after the duplicate-import cleanup, same count) | `pytest.log` |
| Oracle `node --test oracle/verify.test.mjs` | **26/26 pass** | `oracle.log` |
| S0 gate | **S0 PASS 10/10** (16/16, 36/36, 52/52, repeat-100 1 hash `a19054f1…`, P95 0.0925 s) | `s0-gate.log` |
| Repeat-100 | **1 distinct hash** `a19054f1…d530` (fixture `n02-two-job-pr-head`) | `repeat-hash.log` |
| e7/e8 + n01 spot check (S0 per-fixture) | **e7 `e7-legacy-clean-checkout` UNBOUND, e8 `e8-legacy-empty-commit` UNBOUND** (Python + Oracle, parity, pass; threshold 2 requires the correct reason code, so both are MISSING_FIELD); **n01 `n01-single-pr-head` BOUND_PASS** | `03_evidence/s0/S0_GATE.json` |
| Review pack + coverage (old + new) | §3 (default verify FAIL 34 expected; both new calls PASS) | `verify-review-pack-*.log`, `check-review-coverage-*.log` |
| Offline check | PASS — static CLEAN, 0 socket events, verify BOUND_PASS | `offline-check.log`, `offline_check.json` |
| Workflow example | PASS — 4 matrix jobs | `validate-workflow.log` |
| Privacy scan | **193 files, 0 findings** | `privacy-scan.log` |
| UI smoke | PASS — 3 reports (n01 BOUND_PASS 7742 B, g1 BOUND_FAIL 9002 B, d1 UNBOUND 8093 B), 0 external refs; screenshots NOT_TESTED | `ui-smoke.log`, `ui/report-*.html` |

## 7. `verify_release.py` — PASS (3 runs)

```
PASS: verify_release: frozen commit 2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09, source.zip matches the frozen tree file-by-file, manifest + SHA256SUMS verified, LICENSE MIT in both zips, deps == 0, S0 52/52 + repeat-100 1 hash, bundle clones, offline install checked
```

- Run 1: `verify-release.log`, exit 0. Run 2 (after the manifest
  second pass): `verify-release-2.log`, exit 0, byte-identical log.
  Run 3 (final on-disk state, after the second full build):
  `verify-release-3.log`, exit 0, byte-identical to run 1.
- `sha256sum -c SHA256SUMS.txt` (in `05_release/`): all 5 entries
  **OK** (`.gitkeep`, `FREEZE_REPORT.md`, bundle, `dist.zip`,
  `source.zip`).
- Independent ZIP↔tree check (this worker, not the validator):
  `source.zip` 355 entries == `git ls-tree -r 2b1ba19 --
  02_source` 355 files, **0 missing, 0 extra**, names + bytes
  identical; `dist.zip` exactly the 4 expected entries.
  Log: `zip-tree-check.log`.

## 8. `66502f6` → `2b1ba19` diff summary (the STOP gate)

- `git diff 66502f6 2b1ba19 --stat -- 02_source`: **exactly 2
  files** — `02_source/scripts/check_review_coverage.py`
  (+101/−~24) and `02_source/scripts/verify_review_pack.py`
  (+52/−~24). No other production file changed.
- 34 FIX-R1 key files byte-identical: `git diff 66502f6 2b1ba19
  -- <all 34 key files>` is **empty** (0 bytes, 0 lines).
  Log: `key-files-identical-check.log`.
- Outside `02_source`, the frozen commit also carries the 4
  review-row re-records (§2), the regenerated S0 evidence
  (timestamp + P95 only; golden/reason unchanged), and the fresh
  gate logs in `03_evidence/fix-r1-validator-refreeze/`.

## 9. S0-release — re-run from the frozen bundle (not just the tree)

- Cloned the frozen bundle
  (`git clone --branch fix-r1 05_release/benchreceipt-2b1ba19f7f46.bundle`,
  HEAD `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`) into scratch and
  ran its own `scripts/s0_gate.py` there: **S0 PASS 10/10** —
  16/16 controls, 36/36 faults, parity 52/52, repeat-100 1 hash
  `a19054f1…d530`, per-fixture rows **byte-identical** to the
  baseline run; only P95 differed (0.0745 s vs 0.0925 s — timing).
  Log: `s0-release-clone.log`.
- (Note: one earlier attempt at this step failed on a wrong
  relative venv path — `../../../../.venv` instead of the absolute
  path — and was re-run correctly; the failed line stays in the
  log above the successful run, same as the previous round's note.)

## 10. Offline install — independent manual run from the final `dist.zip`

Separate from the validator's internal offline check, this worker
did a fresh-venv install from the released `dist.zip` (log:
`offline-manual.log`):

- `python -m venv` (fresh) → `pip install --no-index --no-deps
  benchreceipt-0.1.0-py3-none-any.whl`: **exit 0**,
  "Successfully installed benchreceipt-0.1.0".
- Bare `benchreceipt --help`: **exit 0**.
- `capture` (scratch git repo, 1 green JUnit test, explicit_sha,
  same procedure as `verify_release.py`'s internal check):
  **exit 0**, `source_mutated=false`.
- `verify`: **exit 0**, `status=BOUND_PASS jobs_verified=1
  reason_codes=-`.
- (Note: my first manual attempt guessed the CLI wrong — bare
  `capture`/`verify` without `--job`/`--policy`/`--evidence` and
  a pytest that isn't in the fresh venv. Those lines were removed
  from the log; the kept round trip follows the validator's exact
  procedure. No stale result was used.)

## 11. Determinism — second full build byte-identical

- The freeze script builds twice internally and accepts only
  identical hashes: first build `OK: deterministic build from
  2b1ba19` (log: `freeze-build.log`, stdout:
  `freeze-build-stdout.log`).
- This worker then ran the **whole build a second time** into a
  separate work dir (`freeze-work-2`, logs `freeze-build-2.log` /
  `freeze-build-2-stdout.log`): same three hashes —
  source.zip `15d1dd0b…`, dist.zip `eb73174a…`, bundle
  `79faf42a…`. That is **4 builds, 1 hash each**.
- The second build overwrote `05_release/` with byte-identical
  files; `verify_release.py` was re-run afterwards (run 3, §7) and
  still passes.

## 12. Cleanliness — no forbidden content in the frozen tree

- `source.zip` scan: **0** entries matching `__pycache__`,
  `*.pyc`, `.venv`, `*.pdf`; **0** JWT-like tokens (`eyJ…`);
  **0** `/home/hatch` strings. Log: `zip-tree-check.log`.
- Scratch dirs (bundle clone, offline venvs, build work dirs)
  live under `.tmp/validator-refreeze-tmp/` and are **not**
  committed.

## 13. Commands (every step, in order)

```bash
cd ~/workspace/p027-benchreceipt
mkdir -p 03_evidence/fix-r1-validator-refreeze .tmp/validator-refreeze-tmp
export TMPDIR=$PWD/.tmp/validator-refreeze-tmp
# pre-change baselines (from 02_source)
../.venv/bin/python scripts/verify_review_pack.py                   # > 03_evidence/fix-r1-validator-refreeze/verify-review-pack-OLD-default-baseline.log  (exit 1, 34 problems)
../.venv/bin/python scripts/check_review_coverage.py               # > check-review-coverage-OLD-default-baseline.log  (exit 0)
# task 1: edit the two scripts (argparse --index/--pack-glob, schemas path, FIXR1 CSV format)
# re-record 6 inventory rows in 04_review (2 script rows x 4 files + 2 pack-06 rows in the indexes)
../.venv/bin/python scripts/verify_review_pack.py                   # > verify-review-pack-NEW-default.log  (exit 1; diff vs baseline empty)
../.venv/bin/python scripts/verify_review_pack.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'   # > verify-review-pack-NEW-fixr1.log  (exit 0)
../.venv/bin/python scripts/check_review_coverage.py               # > check-review-coverage-NEW-default.log  (exit 0; diff vs baseline empty)
../.venv/bin/python scripts/check_review_coverage.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'   # > check-review-coverage-NEW-fixr1.log  (exit 0)
# gates (from 02_source)
../.venv/bin/python -m pytest -q                                   # > 03_evidence/fix-r1-validator-refreeze/pytest.log  (848 passed; re-run after the import cleanup)
node --test oracle/verify.test.mjs                                  # > oracle.log  (26/26)
../.venv/bin/python scripts/s0_gate.py                              # > s0-gate.log  (S0 PASS 10/10)
../.venv/bin/python scripts/repeat_hash.py --runs 100               # > repeat-hash.log  (1 hash)
../.venv/bin/python scripts/offline_check.py --out ../03_evidence/fix-r1-validator-refreeze/offline_check.json   # > offline-check.log
../.venv/bin/python scripts/privacy_scan.py                         # > privacy-scan.log
../.venv/bin/python scripts/validate_workflow_example.py            # > validate-workflow.log
../.venv/bin/python scripts/ui_smoke.py --out-dir ../03_evidence/fix-r1-validator-refreeze/ui   # > ui-smoke.log
# frozen commit (control)
git add 02_source/scripts/verify_review_pack.py 02_source/scripts/check_review_coverage.py \
        04_review/REVIEW_INDEX.md 04_review/REVIEW_INDEX_FIXR1.md 04_review/REVIEW_PACK_06.md 04_review/REVIEW_PACK_FIXR1_06.md \
        03_evidence/s0/S0_GATE.json 03_evidence/s0/S0_REPORT.md 03_evidence/s0/performance.json \
        03_evidence/fix-r1-validator-refreeze
git commit -m "Control: validator redirect + re-verification evidence (frozen-tree candidate)"   # 2b1ba19
# diff gate: git diff 66502f6 2b1ba19 -- 02_source  (only the 2 scripts) + 34-key-files check  # > key-files-identical-check.log
# freeze
cd 02_source
../.venv/bin/python scripts/freeze_release.py --commit 2b1ba19 build \
    --work-dir ../.tmp/validator-refreeze-tmp/freeze-work \
    --build-log ../03_evidence/fix-r1-validator-refreeze/freeze-build.log   # > freeze-build-stdout.log
rm ../05_release/benchreceipt-66502f625597.bundle   # stale bundle from the previous freeze
# (write 05_release/FREEZE_REPORT.md — draft, §3 filled with the verbatim validator line)
../.venv/bin/python scripts/freeze_release.py --commit 2b1ba19 manifest \
    --pytest-passed 848 --oracle-passed 26 --oracle-total 26   # > freeze-manifest-stdout.log
../.venv/bin/python scripts/verify_release.py --tmp-dir ../.tmp/validator-refreeze-tmp/verify-release   # > verify-release.log (run 1)
# manifest + validator re-run (second pass, §3 final)
../.venv/bin/python scripts/freeze_release.py --commit 2b1ba19 manifest \
    --pytest-passed 848 --oracle-passed 26 --oracle-total 26   # > freeze-manifest-2-stdout.log
../.venv/bin/python scripts/verify_release.py --tmp-dir ../.tmp/validator-refreeze-tmp/verify-release   # > verify-release-2.log (run 2)
# independent checks: ZIP↔tree diff + secret/path scan (# > zip-tree-check.log), bundle-clone S0 (# > s0-release-clone.log),
# manual offline install (# > offline-manual.log), second full build (freeze-work-2, # > freeze-build-2.log / freeze-build-2-stdout.log),
# final verify (run 3, # > verify-release-3.log)
# release commit + control commit
git add 05_release 03_evidence/fix-r1-validator-refreeze
git commit -m "Release: second re-freeze r1, validator redirect (frozen commit 2b1ba19) — FREEZE VALID"  # release commit
git add 03_evidence/fix-r1-validator-refreeze/SUMMARY.md
git commit -m "Control: FIX-R1 validator-redirect re-freeze summary"   # this file
```

## 14. Log index (`03_evidence/fix-r1-validator-refreeze/`)

`verify-review-pack-OLD-default-baseline.log`,
`verify-review-pack-NEW-default.log`,
`verify-review-pack-NEW-default-prererecord.log`,
`verify-review-pack-NEW-fixr1.log`,
`verify-review-pack-NEW-fixr1-prererecord.log`,
`check-review-coverage-OLD-default-baseline.log`,
`check-review-coverage-NEW-default.log`,
`check-review-coverage-NEW-fixr1.log`,
`pytest.log`, `oracle.log`, `s0-gate.log`, `repeat-hash.log`,
`offline-check.log`, `offline_check.json`, `privacy-scan.log`,
`validate-workflow.log`, `ui-smoke.log`, `ui/report-{n01,g1,d1}.html`,
`key-files-identical-check.log`, `freeze-build.log`,
`freeze-build-stdout.log`, `freeze-manifest-stdout.log`,
`freeze-manifest-2-stdout.log`, `freeze-build-2.log`,
`freeze-build-2-stdout.log`, `verify-release.log`,
`verify-release-2.log`, `verify-release-3.log`,
`zip-tree-check.log`, `s0-release-clone.log`, `offline-manual.log`,
`SUMMARY.md` (this file). Scratch (not committed):
`.tmp/validator-refreeze-tmp/` (build work dirs, bundle clone,
verify-release tmp, offline venvs).

## 15. Open items / notes for the coordinator

- **P2-28 is fixed in the scripts, not just simulated:** the new
  FIXR1 calls PASS exit 0 in the shipped scripts (not only in the
  reviewer's in-memory simulation).
- **Design decisions the coordinator should confirm or overturn:**
  (a) `check_review_coverage.py --pack-glob` is accepted and
  ignored (uniform CLI); (b) the default coverage CSV is derived
  from the index name; (c) the FIXR1 CSV format
  (`path_at_66502f6`/`key`) is accepted as a second format;
  (d) the 6 review inventory rows were re-recorded (mechanical
  hash updates, §2) — required for both the byte-identical
  default output and the new PASS.
- **No R2 submitted, no GitHub upload, no merge** — per task.
  Next step is the coordinator's independent verification, then
  R2 dispatch in the same conversation (round 2 of 5) and Drive
  archive of `05_release/` (including `.gitkeep`).
- **Stale prose:** review-doc line citations such as
  `check_review_coverage.py:71` and "(253)" now point at the
  pre-redirect script versions (§2); only inventory rows were
  updated. Worth a P2 note if R2 re-reads those docs literally.
