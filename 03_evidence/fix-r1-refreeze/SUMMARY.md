# P027 BenchReceipt — FIX-R1 Re-freeze Summary (v1.2.0, release r1)

> **✅ FREEZE VALID.** Re-freeze of v1.2.0 on branch `fix-r1`.
> `scripts/verify_release.py` **PASS, exit 0** (3 runs, all
> identical, offline-install check included every time).
> No STOP condition was hit; no production code / spec / fixture /
> test was changed by this worker.

## 1. Commits (branch `fix-r1`)

| Role | Commit | Subject |
|---|---|---|
| FIX-R1 | `737e0b17a975f14f080bd4c27077e6bab215b273` | FIX-R1: fail-closed legacy after-identity (P0-R1-01), Scheme A |
| Frozen commit (control) | `66502f6255976b44b3efebb7da778ea8807b1ba1` | Control: FIX-R1 re-verification evidence (frozen-tree candidate) |
| Release commit | `b221401ba5a8ddc713249f8d04f2804caf4b0e53` | Release: re-freeze r1 on FIX-R1 (frozen commit 66502f6) — FREEZE VALID |
| Control commit (this file) | on top of `b221401` — see `git log` | Control: FIX-R1 re-freeze summary (this file) |

- HEAD at release-commit time: `b221401ba5a8ddc713249f8d04f2804caf4b0e53`.
- The frozen commit is a pure evidence commit on top of FIX-R1:
  `git diff 737e0b1 66502f6 -- 02_source` is **empty** (0 lines) —
  it only adds regenerated `03_evidence/s0/*`, the coordinator's
  `03_evidence/r1-repro/` logs, and the fresh gate logs in
  `03_evidence/fix-r1-refreeze/`.
- The release commit's `02_source` tree is identical to the frozen
  commit's tree: `git diff 66502f6 b221401 -- 02_source` is **empty**
  (0 lines).
- Working tree after both commits: **clean** (`git status
  --porcelain` empty).
- Spec version: **1.2.0**. Release ID: **r1** (fourth freeze of r1).
- No merge, no R2 submission, no GitHub upload (not authorized).

### Why the working tree was not clean at start

On arrival the tree had uncommitted S0 regenerations (coordinator's
04:00 re-run) plus untracked `03_evidence/r1-repro/`. The S0 diff
was timestamps + P95 + `reason_codes_sha256` `a60613b3…` →
`16feb3b8…`: the committed S0 in `737e0b1` was generated at 03:41,
*before* FIX-R1 changed `02_source/docs/REASON_CODES.md` (03:57),
so the old hash belonged to the pre-fix doc; `16feb3b8…` is the
correct hash of the current doc (verified: `sha256sum
02_source/docs/REASON_CODES.md` = `16feb3b8…`). Golden SHA
unchanged (`fb8e70a1…`). These files were committed as the frozen
commit `66502f6` before any freeze step, per the "commit first,
freeze from a commit" discipline.

## 2. Old → new hash对照表 (no old hash reused)

| File | Old (FIX-T014-F1-docs re-freeze, frozen `a07dc79`) | New (this re-freeze, frozen `66502f6`) |
|---|---|---|
| `source.zip` | `2b06fcd38e6207f3c3bfa2058b68443e693b7c1b719e04b69dbdccd34f09caac` (419,233 B, 345 files) | `873b4dc43252202b17432c619397254a480e2dcfe10b43b7404d14b0efcd420b` (431,740 B, 355 files, 1,156,533 source bytes) |
| `dist.zip` | `77b08aacfd2c93a14bce670608e03f6b3ca77116e9f344c72521ac327539f1df` (152,203 B) | `da900faf679551ab6599c2ed333923bc151032957ceba2542ff065a51fc1bacd` (152,883 B) |
| bundle | `d9e7119be3eacdc195fe10d37b44f56e80da4621f4bc54c3fdaf1c8a48a67898` (`benchreceipt-a07dc797c02b.bundle`, 2,934,895 B) | `86c4c82ed019803d349997c5708d62805b918c7b89675e181a20b5f4d00d0dc8` (`benchreceipt-66502f625597.bundle`, 3,844,063 B) |

- Old bundle file `benchreceipt-a07dc797c02b.bundle` was **deleted**
  from `05_release/` (it would otherwise fail the validator's
  no-unlisted-files check). `05_release/` now holds exactly 7
  files: `.gitkeep`, `FREEZE_REPORT.md`, `RELEASE_MANIFEST.json`,
  `SHA256SUMS.txt`, `benchreceipt-66502f625597.bundle`, `dist.zip`,
  `source.zip`.
- `dist.zip` contents (4 entries): `INSTALL.txt` (721 B), `LICENSE`
  (1,082 B), `benchreceipt-0.1.0-py3-none-any.whl` (80,150 B, 27
  entries incl. `benchreceipt/schemas/{run,policy,result}.v1.json`),
  `benchreceipt-0.1.0.tar.gz` (73,336 B). Wheel METADATA:
  `License-Expression: MIT`, `Requires-Python: >=3.12`, zero
  runtime dependencies.

## 3. Manifest gates (`05_release/RELEASE_MANIFEST.json`)

- `spec_version`: `1.2.0`; `frozen_commit`:
  `66502f6255976b44b3efebb7da778ea8807b1ba1`.
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
  P95 `0.07886755099997345` s; privacy violations **0**; offline
  network refs **0**; `s0_generated_at` `2026-11-18T04:03:18.970409Z`.
- The previous freeze's 3 manifest lags are **eliminated**: faults
  34/34 → **36/36**, parity 50/50 → **52/52**, golden
  `65ccd954…` → **`fb8e70a1…`**.
- `files` list (6 entries + the manifest itself): `.gitkeep`,
  `FREEZE_REPORT.md`, `benchreceipt-66502f625597.bundle`,
  `dist.zip`, `source.zip`, `SHA256SUMS.txt`.
- **P2-R1-01:** `05_release/.gitkeep` exists (0 bytes, sha
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`),
  listed in `SHA256SUMS.txt` and in the manifest `files` list.
  It was not deleted and ships with the Drive archive.

## 4. Gates re-run fresh by this worker (all exit 0)

All from `02_source` with `../.venv/bin/python` (Python 3.12.3,
Node v24.22.1), `TMPDIR=~/workspace/p027-benchreceipt/.tmp/refreeze-tmp`.
Logs in `03_evidence/fix-r1-refreeze/`.

| Gate | Result | Log |
|---|---|---|
| Full pytest | **848 passed** in 40.70 s | `pytest.log` |
| Oracle `node --test oracle/verify.test.mjs` | **26/26 pass** | `oracle.log` |
| S0 gate | **S0 PASS 10/10** (16/16, 36/36, 52/52, repeat-100 1 hash `a19054f1…`, P95 0.0789 s) | `s0-gate.log` |
| Repeat-100 | **1 distinct hash** `a19054f1…d530` (fixture `n02-two-job-pr-head`) | `repeat-hash.log` |
| e7/e8 + n01 spot check (S0 per-fixture) | **e7 `e7-legacy-clean-checkout` UNBOUND, e8 `e8-legacy-empty-commit` UNBOUND** (Python + Oracle, parity, pass; threshold 2 requires the correct reason code, so both are MISSING_FIELD); **n01 `n01-single-pr-head` BOUND_PASS** | `03_evidence/s0/S0_GATE.json` |
| Review pack | PASS — commit `cfede27…`, 45 index rows, 37 pack rows, 34 key files | `verify-review-pack.log` |
| Offline check | PASS — static CLEAN, 0 socket events, verify BOUND_PASS | `offline-check.log`, `offline_check.json` |
| Workflow example | PASS — 4 matrix jobs | `validate-workflow.log` |
| Privacy scan | **193 files, 0 findings** | `privacy-scan.log` |
| UI smoke | PASS — 3 reports (n01 BOUND_PASS 7742 B, g1 BOUND_FAIL 9002 B, d1 UNBOUND 8093 B), 0 external refs; screenshots NOT_TESTED | `ui-smoke.log`, `ui/report-*.html` |

## 5. `verify_release.py` — PASS (3 runs)

```
PASS: verify_release: frozen commit 66502f6255976b44b3efebb7da778ea8807b1ba1, source.zip matches the frozen tree file-by-file, manifest + SHA256SUMS verified, LICENSE MIT in both zips, deps == 0, S0 52/52 + repeat-100 1 hash, bundle clones, offline install checked
```

- Run 1: `verify-release.log`, exit 0. Run 2 (after the manifest
  second pass): `verify-release-2.log`, exit 0, byte-identical log.
  Run 3 (final on-disk state, after the second full build):
  `verify-release-3.log`, exit 0.
- `sha256sum -c SHA256SUMS.txt` (in `05_release/`): all 5 entries
  **OK** (`.gitkeep`, `FREEZE_REPORT.md`, bundle, `dist.zip`,
  `source.zip`).
- Independent ZIP↔tree check (this worker, not the validator):
  `source.zip` 355 entries == `git ls-tree -r 66502f6 --
  02_source` 355 files, **0 missing, 0 extra**, names + bytes
  identical; `dist.zip` exactly the 4 expected entries.

## 6. S0-release — re-run from the frozen bundle (not just the tree)

- Cloned the frozen bundle
  (`git clone --branch fix-r1 05_release/benchreceipt-66502f625597.bundle`,
  HEAD `66502f6255976b44b3efebb7da778ea8807b1ba1`) into scratch and
  ran its own `scripts/s0_gate.py` there: **S0 PASS 10/10** —
  16/16 controls, 36/36 faults, parity 52/52, repeat-100 1 hash
  `a19054f1…d530`, per-fixture rows **byte-identical** to the
  baseline run; only P95 differed (0.0823 s vs 0.0789 s — timing).
  Log: `s0-release-clone.log`.
- (Note: one earlier attempt at this step failed on a wrong
  relative log path — the `../../../` redirect — and was re-run
  correctly with absolute paths; the first attempt never executed
  the gate, so no stale result was used.)

## 7. Offline install — independent manual run from the final `dist.zip`

Separate from the validator's internal offline check, this worker
did a fresh-venv install from the released `dist.zip` (log:
`offline-manual.log`):

- `python -m venv` (fresh) → `pip install --no-index --no-deps
  benchreceipt-0.1.0-py3-none-any.whl`: **exit 0**,
  "Successfully installed benchreceipt-0.1.0".
- Bare `benchreceipt --help`: **exit 0**.
- `capture` (scratch git repo, 1 green JUnit test, explicit_sha):
  **exit 0**, `source_mutated=false`.
- `verify`: **exit 0**, `status=BOUND_PASS jobs_verified=1
  reason_codes=-`.

## 8. Determinism — second full build byte-identical

- The freeze script builds twice internally and accepts only
  identical hashes: first build `OK: deterministic build from
  66502f6` (log: `freeze-build.log`, stdout:
  `freeze-build-stdout.log`).
- This worker then ran the **whole build a second time** into a
  separate work dir (`freeze-work-2`, logs `freeze-build-2.log` /
  `freeze-build-2-stdout.log`): same three hashes —
  source.zip `873b4dc4…`, dist.zip `da900faf…`, bundle
  `86c4c82e…`. That is **4 builds, 1 hash each**.
- The second build overwrote `05_release/` with byte-identical
  files; `verify_release.py` was re-run afterwards (run 3, §5) and
  still passes.

## 9. Cleanliness — no forbidden content in the frozen tree

- `source.zip` scan: **0** entries matching `__pycache__`,
  `*.pyc`, `.venv`, `*.pdf`; **0** JWT-like tokens (`eyJ…`).
- One `/home/…` string hit investigated:
  `tests/ci_metadata/test_ci_metadata.py` contains only synthetic
  CI fixture strings (`/home/runner/work/repo`,
  `/home/someone`, from T003) — **no real user path**
  (`/home/hatch` appears nowhere in `source.zip`).
- No `venv/`, `__pycache__/`, `*.pyc`, user PDF, secret, or
  absolute user path ships in the release. Scratch dirs
  (bundle clone, offline venvs, build work dirs) live under
  `.tmp/refreeze-tmp/` and are **not** committed.

## 10. Commands (every step, in order)

```bash
cd ~/workspace/p027-benchreceipt
# gates (TMPDIR=~/workspace/p027-benchreceipt/.tmp/refreeze-tmp, from 02_source)
../.venv/bin/python -m pytest -q                                   # > 03_evidence/fix-r1-refreeze/pytest.log
node --test oracle/verify.test.mjs                                  # > oracle.log
../.venv/bin/python scripts/s0_gate.py                              # > s0-gate.log
../.venv/bin/python scripts/repeat_hash.py --runs 100               # > repeat-hash.log
../.venv/bin/python scripts/verify_review_pack.py                   # > verify-review-pack.log
../.venv/bin/python scripts/offline_check.py --out ../03_evidence/fix-r1-refreeze/offline_check.json
../.venv/bin/python scripts/privacy_scan.py                         # > privacy-scan.log
../.venv/bin/python scripts/validate_workflow_example.py            # > validate-workflow.log
../.venv/bin/python scripts/ui_smoke.py --out-dir ../03_evidence/fix-r1-refreeze/ui
# frozen commit (control)
git add 03_evidence/s0/S0_GATE.json 03_evidence/s0/S0_REPORT.md 03_evidence/s0/performance.json \
        03_evidence/r1-repro 03_evidence/fix-r1-refreeze
git commit -m "Control: FIX-R1 re-verification evidence (frozen-tree candidate)"   # 66502f6
# freeze
cd 02_source
../.venv/bin/python scripts/freeze_release.py --commit 66502f6 build \
    --work-dir ../.tmp/refreeze-tmp/freeze-work \
    --build-log ../03_evidence/fix-r1-refreeze/freeze-build.log
rm ../05_release/benchreceipt-a07dc797c02b.bundle   # stale bundle from the previous freeze
# (write 05_release/FREEZE_REPORT.md — draft, §3 filled with the verbatim validator line)
../.venv/bin/python scripts/freeze_release.py --commit 66502f6 manifest \
    --pytest-passed 848 --oracle-passed 26 --oracle-total 26
../.venv/bin/python scripts/verify_release.py --tmp-dir ../.tmp/refreeze-tmp/verify-release
# manifest + validator re-run (second pass, §3 final)
../.venv/bin/python scripts/freeze_release.py --commit 66502f6 manifest \
    --pytest-passed 848 --oracle-passed 26 --oracle-total 26
../.venv/bin/python scripts/verify_release.py --tmp-dir ../.tmp/refreeze-tmp/verify-release
# independent checks: ZIP↔tree diff, secret/path scan, bundle-clone S0,
# manual offline install, second full build (freeze-work-2), final verify (run 3)
# release commit + control commit
git add 05_release 03_evidence/fix-r1-refreeze
git commit -m "Release: re-freeze r1 on FIX-R1 (frozen commit 66502f6) — FREEZE VALID"  # b221401
git add 03_evidence/fix-r1-refreeze/SUMMARY.md
git commit -m "Control: FIX-R1 re-freeze summary"   # this file
```

## 11. Log index (`03_evidence/fix-r1-refreeze/`)

`pytest.log`, `oracle.log`, `s0-gate.log`, `repeat-hash.log`,
`verify-review-pack.log`, `offline-check.log`,
`offline_check.json`, `privacy-scan.log`, `validate-workflow.log`,
`ui-smoke.log`, `ui/report-{n01,g1,d1}.html`, `freeze-build.log`,
`freeze-build-stdout.log`, `freeze-manifest-stdout.log`,
`freeze-manifest-2-stdout.log`, `freeze-build-2.log`,
`freeze-build-2-stdout.log`, `verify-release.log`,
`verify-release-2.log`, `verify-release-3.log`,
`s0-release-clone.log`, `offline-manual.log`, `SUMMARY.md`
(this file). Scratch (not committed):
`.tmp/refreeze-tmp/` (build work dirs, bundle clone,
verify-release tmp, offline venvs).

## 12. Open items / notes for the coordinator

- **P1-R1-01 (review-pack anchor):** the pack still anchors
  `cfede271` (T013 candidate) and `verify_review_pack.py` passes
  against it. Deliberately not re-anchored — a fresh pack for the
  new freeze belongs to the R2 review, not this freeze.
- **No R2 submitted, no GitHub upload, no merge** — per task.
  Next step is the coordinator's independent verification, then
  R2 dispatch in the same conversation (round 2 of 5) and Drive
  archive of `05_release/` (including `.gitkeep`).
