# P027 BenchReceipt — FIX-R1 Review Pack Re-anchor to `2b1ba19` (branch `fix-r1-reanchor`)

> **Re-anchor COMPLETE, no STOP hit.** The FIX-R1 independent
> review pack (original verdict PASS, 0 P0 / 0 P1, anchored at
> `66502f6`) is re-anchored to `2b1ba19` / release `213677f`.
> The only `02_source` difference between the two anchors is the
> validator redirect itself; all 34 key files are proven
> byte-identical one by one below. Both new validator calls PASS
> exit 0 against `2b1ba19`; full suite + S0 show no regression.

- Branch: `fix-r1-reanchor`, cut from `fix-r1` HEAD `bd86c0d`
  (working tree verified clean before the cut).
- Old anchor: `66502f6255976b44b3efebb7da778ea8807b1ba1`
  (release `b221401ba5a8ddc713249f8d04f2804caf4b0e53`).
- New anchor: `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`
  (release `213677f0df7cfda427a3ef6d5558ffecadd91d26`).
- Spec version: 1.2.0. Reviewer: same independent, review-only
  reviewer as the FIX-R1 pack; no production code, test, fixture,
  Golden, spec or release file was modified in this work — only
  `04_review/REVIEW_INDEX_FIXR1.md` (header + one new section)
  and this evidence directory.
- Model routing: no model was dispatched for this task — every
  check below is a local `git` / `sha256` / `python` / `node` run
  by this reviewer, so there is no model-route claim to report.

## 1. Anchor diff gate (STOP gate — passed)

`git diff 66502f6..2b1ba19 -- 02_source` lists **exactly 2 files**
(log: `diff-66502f6-2b1ba19.log`):

| File | Change |
|---|---|
| `02_source/scripts/check_review_coverage.py` | +101/−~24 (redirect) |
| `02_source/scripts/verify_review_pack.py` | +52/−~24 (redirect) |

`git diff 66502f6..2b1ba19` restricted to the 34 key files alone
is **0 bytes**. No key file differs — the re-anchor proceeds.

## 2. Per-file byte-identity table (all 43 index rows)

Method: for each inventory row in
`04_review/REVIEW_INDEX_FIXR1.md`, SHA-256 + line count
(validator definition: `len(bytes.decode('utf-8',
errors='replace').splitlines())`) of the blob at `66502f6` vs the
blob at `2b1ba19` vs the recorded value vs the working-tree file.
Script: `.tmp/reanchor-tmp/check_byte_identity.py` (scratch, not
committed). Full raw output:
`byte-identity-check.log` (43 rows parsed).

- **35 production rows: OK-IDENTICAL** — blob@66502f6 ==
  blob@2b1ba19 == recorded value (34 key files + the one further
  production row, `schemas/README.md`, `Key = no`).
- **2 pack-tooling rows: OK-REDIRECT** — recorded value ==
  worktree == blob@2b1ba19, and blob@66502f6 is the known old
  value (`verify_review_pack.py` `f1c6b2d7…`/253,
  `check_review_coverage.py` `70cbffe1…`/125). This difference is
  the intended redirect, not a regression.
- **6 pack rows: OK** — recorded value == worktree ==
  blob@2b1ba19 (packs did not exist at `66502f6`, MISSING there
  as expected).

| Path | Recorded (SHA…/lines) | @66502f6 | @2b1ba19 | Worktree | Verdict |
|---|---|---|---|---|---|
| `02_source/examples/github-actions/ci.yml` | `9c672a4caf…`/190 | `9c672a4caf…`/190 | `9c672a4caf…`/190 | `9c672a4caf…`/190 | OK-IDENTICAL |
| `02_source/oracle/README.md` | `bd1e243e41…`/58 | `bd1e243e41…`/58 | `bd1e243e41…`/58 | `bd1e243e41…`/58 | OK-IDENTICAL |
| `02_source/oracle/verify.mjs` | `ac65f524c4…`/1823 | `ac65f524c4…`/1823 | `ac65f524c4…`/1823 | `ac65f524c4…`/1823 | OK-IDENTICAL |
| `02_source/oracle/verify.test.mjs` | `bdab569718…`/606 | `bdab569718…`/606 | `bdab569718…`/606 | `bdab569718…`/606 | OK-IDENTICAL |
| `02_source/pyproject.toml` | `60bb4f4db8…`/63 | `60bb4f4db8…`/63 | `60bb4f4db8…`/63 | `60bb4f4db8…`/63 | OK-IDENTICAL |
| `02_source/scripts/build_fixtures.py` | `f6a9ff891c…`/607 | `f6a9ff891c…`/607 | `f6a9ff891c…`/607 | `f6a9ff891c…`/607 | OK-IDENTICAL |
| `02_source/scripts/check_review_coverage.py` | `7775da3902…`/194 | `70cbffe17e…`/125 | `7775da3902…`/194 | `7775da3902…`/194 | OK-REDIRECT |
| `02_source/scripts/offline_check.py` | `3deb9b75d4…`/240 | `3deb9b75d4…`/240 | `3deb9b75d4…`/240 | `3deb9b75d4…`/240 | OK-IDENTICAL |
| `02_source/scripts/performance_smoke.py` | `9deb600338…`/165 | `9deb600338…`/165 | `9deb600338…`/165 | `9deb600338…`/165 | OK-IDENTICAL |
| `02_source/scripts/privacy_scan.py` | `cdb5566b99…`/267 | `cdb5566b99…`/267 | `cdb5566b99…`/267 | `cdb5566b99…`/267 | OK-IDENTICAL |
| `02_source/scripts/repeat_hash.py` | `64281520c0…`/64 | `64281520c0…`/64 | `64281520c0…`/64 | `64281520c0…`/64 | OK-IDENTICAL |
| `02_source/scripts/s0_gate.py` | `04dca6fa77…`/375 | `04dca6fa77…`/375 | `04dca6fa77…`/375 | `04dca6fa77…`/375 | OK-IDENTICAL |
| `02_source/scripts/ui_smoke.py` | `298de709d1…`/120 | `298de709d1…`/120 | `298de709d1…`/120 | `298de709d1…`/120 | OK-IDENTICAL |
| `02_source/scripts/validate_workflow_example.py` | `8412a94c66…`/601 | `8412a94c66…`/601 | `8412a94c66…`/601 | `8412a94c66…`/601 | OK-IDENTICAL |
| `02_source/scripts/verify_review_pack.py` | `eae974023d…`/289 | `f1c6b2d7de…`/253 | `eae974023d…`/289 | `eae974023d…`/289 | OK-REDIRECT |
| `02_source/src/benchreceipt/__init__.py` | `1b7920a55e…`/10 | `1b7920a55e…`/10 | `1b7920a55e…`/10 | `1b7920a55e…`/10 | OK-IDENTICAL |
| `02_source/src/benchreceipt/__main__.py` | `30819d5b2e…`/13 | `30819d5b2e…`/13 | `30819d5b2e…`/13 | `30819d5b2e…`/13 | OK-IDENTICAL |
| `02_source/src/benchreceipt/bundle.py` | `ce557f6f4c…`/788 | `ce557f6f4c…`/788 | `ce557f6f4c…`/788 | `ce557f6f4c…`/788 | OK-IDENTICAL |
| `02_source/src/benchreceipt/canonical.py` | `540d16a88e…`/50 | `540d16a88e…`/50 | `540d16a88e…`/50 | `540d16a88e…`/50 | OK-IDENTICAL |
| `02_source/src/benchreceipt/capture.py` | `6ba926dc39…`/674 | `6ba926dc39…`/674 | `6ba926dc39…`/674 | `6ba926dc39…`/674 | OK-IDENTICAL |
| `02_source/src/benchreceipt/ci_metadata.py` | `960ab6c537…`/196 | `960ab6c537…`/196 | `960ab6c537…`/196 | `960ab6c537…`/196 | OK-IDENTICAL |
| `02_source/src/benchreceipt/cli.py` | `51fb6c3189…`/381 | `51fb6c3189…`/381 | `51fb6c3189…`/381 | `51fb6c3189…`/381 | OK-IDENTICAL |
| `02_source/src/benchreceipt/command.py` | `0fedd5aa4b…`/289 | `0fedd5aa4b…`/289 | `0fedd5aa4b…`/289 | `0fedd5aa4b…`/289 | OK-IDENTICAL |
| `02_source/src/benchreceipt/git_identity.py` | `61f1a53fae…`/213 | `61f1a53fae…`/213 | `61f1a53fae…`/213 | `61f1a53fae…`/213 | OK-IDENTICAL |
| `02_source/src/benchreceipt/matrix.py` | `6c2cbe8bf7…`/101 | `6c2cbe8bf7…`/101 | `6c2cbe8bf7…`/101 | `6c2cbe8bf7…`/101 | OK-IDENTICAL |
| `02_source/src/benchreceipt/policy.py` | `683ef274cb…`/124 | `683ef274cb…`/124 | `683ef274cb…`/124 | `683ef274cb…`/124 | OK-IDENTICAL |
| `02_source/src/benchreceipt/render/__init__.py` | `ddec99272b…`/5 | `ddec99272b…`/5 | `ddec99272b…`/5 | `ddec99272b…`/5 | OK-IDENTICAL |
| `02_source/src/benchreceipt/render/html.py` | `66704da5fa…`/693 | `66704da5fa…`/693 | `66704da5fa…`/693 | `66704da5fa…`/693 | OK-IDENTICAL |
| `02_source/src/benchreceipt/reports/__init__.py` | `73c8c07bff…`/10 | `73c8c07bff…`/10 | `73c8c07bff…`/10 | `73c8c07bff…`/10 | OK-IDENTICAL |
| `02_source/src/benchreceipt/reports/junit.py` | `bb5af528f6…`/199 | `bb5af528f6…`/199 | `bb5af528f6…`/199 | `bb5af528f6…`/199 | OK-IDENTICAL |
| `02_source/src/benchreceipt/reports/lcov.py` | `80c3f2b53b…`/309 | `80c3f2b53b…`/309 | `80c3f2b53b…`/309 | `80c3f2b53b…`/309 | OK-IDENTICAL |
| `02_source/src/benchreceipt/schema.py` | `3b0ce03abd…`/270 | `3b0ce03abd…`/270 | `3b0ce03abd…`/270 | `3b0ce03abd…`/270 | OK-IDENTICAL |
| `02_source/src/benchreceipt/schemas/README.md` | `27613c955a…`/90 | `27613c955a…`/90 | `27613c955a…`/90 | `27613c955a…`/90 | OK-IDENTICAL |
| `02_source/src/benchreceipt/schemas/policy.v1.json` | `2e555dc3c9…`/1 | `2e555dc3c9…`/1 | `2e555dc3c9…`/1 | `2e555dc3c9…`/1 | OK-IDENTICAL |
| `02_source/src/benchreceipt/schemas/result.v1.json` | `2f16a1024b…`/1 | `2f16a1024b…`/1 | `2f16a1024b…`/1 | `2f16a1024b…`/1 | OK-IDENTICAL |
| `02_source/src/benchreceipt/schemas/run.v1.json` | `fce85f3dec…`/1 | `fce85f3dec…`/1 | `fce85f3dec…`/1 | `fce85f3dec…`/1 | OK-IDENTICAL |
| `02_source/src/benchreceipt/verify.py` | `7c70f44570…`/970 | `7c70f44570…`/970 | `7c70f44570…`/970 | `7c70f44570…`/970 | OK-IDENTICAL |
| `04_review/REVIEW_PACK_FIXR1_01.md` | `d75105baae…`/71 | MISSING | `d75105baae…`/71 | `d75105baae…`/71 | OK |
| `04_review/REVIEW_PACK_FIXR1_02.md` | `af02a9a559…`/72 | MISSING | `af02a9a559…`/72 | `af02a9a559…`/72 | OK |
| `04_review/REVIEW_PACK_FIXR1_03.md` | `03ef5d8882…`/66 | MISSING | `03ef5d8882…`/66 | `03ef5d8882…`/66 | OK |
| `04_review/REVIEW_PACK_FIXR1_04.md` | `27a4892228…`/71 | MISSING | `27a4892228…`/71 | `27a4892228…`/71 | OK |
| `04_review/REVIEW_PACK_FIXR1_05.md` | `ffa131e647…`/61 | MISSING | `ffa131e647…`/61 | `ffa131e647…`/61 | OK |
| `04_review/REVIEW_PACK_FIXR1_06.md` | `7ddaacde28…`/103 | MISSING | `7ddaacde28…`/103 | `7ddaacde28…`/103 | OK |

(Full 64-hex SHAs are in the index itself and in
`byte-identity-check.log`; prefixes above are 10 hex chars.)

## 3. The 6 re-recorded rows — verification (count discrepancy noted)

The brief said the worker re-recorded 6 inventory rows in the
pack (4 script rows + 2 pack-06 self rows). The
`30bfd0c..2b1ba19` diff over the FIXR1 files shows **5** changed
rows, not 6 — all 5 verified character-for-character (recorded ==
worktree == blob@2b1ba19; old values confirmed as the known
pre-redirect ones):

| # | File | Row | Old (at `30bfd0c`) | New (verified) |
|---|---|---|---|---|
| 1 | `04_review/REVIEW_INDEX_FIXR1.md` | `02_source/scripts/verify_review_pack.py` | `f1c6b2d7…`/253 | `eae974023d4d7b673b561f79fd04d7463604b6aec9076b89d7ab82830b29cff0`/289 |
| 2 | `04_review/REVIEW_INDEX_FIXR1.md` | `02_source/scripts/check_review_coverage.py` | `70cbffe1…`/125 | `7775da3902ddafed06129dc6f9970b896f457ccf294557efa607bef7cee2d168`/194 |
| 3 | `04_review/REVIEW_INDEX_FIXR1.md` | `04_review/REVIEW_PACK_FIXR1_06.md` | `b0361226…`/103 | `7ddaacde28c8809cdfb2ffbacb9f7d6a4a2e9dda17d79a3c5fb085c543bb99df`/103 |
| 4 | `04_review/REVIEW_PACK_FIXR1_06.md` | `02_source/scripts/verify_review_pack.py` | `f1c6b2d7…`/253 | `eae974023d4d7b673b561f79fd04d7463604b6aec9076b89d7ab82830b29cff0`/289 |
| 5 | `04_review/REVIEW_PACK_FIXR1_06.md` | `02_source/scripts/check_review_coverage.py` | `70cbffe1…`/125 | `7775da3902ddafed06129dc6f9970b896f457ccf294557efa607bef7cee2d168`/194 |

The 6th row the brief counts is the T013 pack's own
`REVIEW_PACK_06.md` self-row in `04_review/REVIEW_INDEX.md`
(`887ffc7d…` → `66531adf…`, 114 lines) — outside the FIXR1
pack, also re-recorded by the worker; the T013 files carry 5
re-recorded rows in total, same pattern. No FIXR1 inventory row
was left stale: `grep` for the old script SHAs (`f1c6b2d7`,
`70cbffe1`) and the old pack-06 SHA (`b0361226`) over the FIXR1
inventory files finds nothing.

One deliberate non-update, checked and judged correct: the
`REVIEW_COVERAGE_FIXR1.csv` rows 37–38 still carry the OLD
script SHAs in the `sha256_at_66502f6` / `lines_at_66502f6`
columns. That is the column's semantics — hashes AT `66502f6`,
where the scripts were the old versions — and the worker's
SUMMARY §2 says so explicitly. `check_review_coverage.py` does
not read those columns (only `path_at_66502f6` + `key`), so
nothing machine-checked is stale. No correction made.

The other index rows were NOT touched: of the 43 index rows, 3
changed (the 2 script rows + the pack-06 row above) and 40 are
untouched; of the 37 rows across the 6 pack files, 2 changed
(both script rows in pack-06) and 35 are untouched. (The brief's
"其余 31 行" does not match either count — 37 file rows minus
the brief's 6 would be 31, but the diff shows 5 changed rows in
the FIXR1 files, not 6; the true untouched counts are 40 in the
index and 35 across the packs. All of them are proven identical
in §2 above and by the validator PASS in §5.)

## 4. Anchor update checklist (`04_review/REVIEW_INDEX_FIXR1.md`)

| Change | Old | New |
|---|---|---|
| Anchor commit (header) | `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`) | `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09` (branch `fix-r1`) |
| Frozen candidate commit (header, the line the validators parse) | `66502f6255976b44b3efebb7da778ea8807b1ba1` | `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09` |
| Release commit (header) | `b221401` ("Release: re-freeze r1 on FIX-R1 (frozen commit 66502f6) — FREEZE VALID") | `213677f` ("Release: second re-freeze r1, validator redirect (frozen commit 2b1ba19) — FREEZE VALID") |
| New section | — | `## Re-anchor to 2b1ba19 (branch fix-r1-reanchor, this review)` — explains the original anchor, the byte-identity proof, the CSV column-name decision, and that historical `66502f6` prose below is the record of the original verification |
| `REVIEW_COVERAGE_FIXR1.csv` `path_at_66502f6` column | unchanged by design | unchanged by design (see §3 + §6) |
| All other index content (Conclusion, Freeze identity table, Coverage, inventory rows, re-run table, P2-28 section) | — | untouched |

New-release numbers cited in the added section were verified by
this reviewer from the `213677f` manifest / SHA256SUMS (read-only
`git show`): manifest `frozen_commit` =
`2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`; `source.zip`
`15d1dd0bcfd217cc060ba1501c9205c9aa2fde9300c5734077867b664cac54af`
(433,074 B, 355 files); `dist.zip`
`eb73174ab6e51069d2565ebd793d91369b772c33115cf2ba91926bd21b2b48b1`;
bundle
`79faf42ab7b5d9487cea9bdec8b24f69b56c4dc3ef0c74dd9a5b7d016f5474b1`.

## 5. Validator re-runs (new calls, anchor now `2b1ba19`)

Both run from `02_source` with
`TMPDIR=$PWD/../.tmp/reanchor-tmp`, Python 3.12.3 (`.venv`),
exit 0:

| Call | Result | Log |
|---|---|---|
| `python scripts/verify_review_pack.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'` | **PASS** — commit `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`, 43 index rows, 37 pack rows, 34 key production files all listed in 6 pack(s), all SHA-256 + line counts match | `verify-review-pack-fixr1-2b1ba19.log` |
| `python scripts/check_review_coverage.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'` | **PASS** — all 34 key production files reviewed in `04_review/REVIEW_COVERAGE_FIXR1.csv` | `check-review-coverage-fixr1-2b1ba19.log` |

## 6. Validator worker SUMMARY §15 design decisions — assessment

The coordinator confirmed (a)–(c); I reviewed each for harm to
the pack's machine-checkability and judge **none of them harms
it** — no STOP:

- (a) `check_review_coverage.py --pack-glob` accepted and
  ignored. Coverage is per-index by construction (key list from
  the index, reviewed set from the CSV); a pack glob cannot
  change the outcome. The docstring says so explicitly. The
  uniform CLI avoids caller mistakes; the ignored flag is not a
  silent weakening because there is nothing for it to weaken.
- (b) Default coverage CSV derived from the index name
  (`REVIEW_INDEX*.md` → `REVIEW_COVERAGE*.csv`). Deterministic,
  documented, and strictly better than the old default: the
  FIXR1 call now resolves the right CSV without a positional
  argument (verified live in §5 — the call above passed no CSV
  path and read `REVIEW_COVERAGE_FIXR1.csv`). An explicit
  positional CSV still overrides.
- (c) FIXR1 CSV format (`path_at_66502f6` / `key`) accepted as a
  second format. The acceptance rule is as strict as the
  standard one: a row counts only when `key` is `yes`, and all
  34 key files must be present. The column name is a historical
  label (paths as of the original review commit); the script
  never verifies SHAs from the CSV — that is
  `verify_review_pack.py`'s job, and it checks the blobs at the
  new anchor (§5 PASS). Keeping the column name avoids another
  script change + re-freeze for zero checkability gain.

## 7. Gates re-run fresh by this reviewer (no regression)

All from `02_source`, `TMPDIR=~/workspace/p027-benchreceipt/.tmp/reanchor-tmp`
(persistent disk, not `/tmp`), Python 3.12.3 (`.venv`), Node
v24.22.1. S0 wrote to `03_evidence/fix-r1-reanchor/s0/` via
`--out-dir` so the committed `03_evidence/s0/` is untouched.

| Gate | Result | Log |
|---|---|---|
| Full pytest | **848 passed** in 40.01 s | `pytest-full.log` |
| Oracle `node --test oracle/verify.test.mjs` | **26/26 pass** | `oracle.log` |
| S0 gate | **S0 PASS 10/10** — 16/16 controls, 36/36 faults, parity 52/52, false PASS 0, false block 0, repeat-100 1 hash `a19054f1…d530`, P95 0.0905 s, privacy 0, offline 0 | `s0-gate.log`, `s0/S0_GATE.json` (generated 2026-11-18T04:45:58Z) |
| Repeat-100 | **1 distinct hash** `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530` (fixture `n02-two-job-pr-head`) | `repeat-hash.log` |
| `verify_release.py` (bonus, read-only re-confirmation of the on-disk `213677f` release) | **PASS** — frozen commit `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`, source.zip matches the frozen tree file-by-file, manifest + SHA256SUMS verified, LICENSE MIT in both zips, deps == 0, S0 52/52 + repeat-100 1 hash, bundle clones, offline install checked | `verify-release.log` |

S0 golden `fb8e70a136aef710fb59d46addda99df71bafb18320afb23d75b61bf21560497`
and reason-codes `16feb3b809021e410a94c0ccb0a64dfd012cbc8ad72c869c6741747090f4a8e5`
reproduce the manifest values exactly (only P95 / timestamp
differ — run-to-run timing, as before).

## 8. Commands (every step, in order)

```bash
cd ~/workspace/p027-benchreceipt
git status --porcelain   # clean; HEAD bd86c0d on fix-r1
git checkout -b fix-r1-reanchor   # new branch at bd86c0d
mkdir -p 03_evidence/fix-r1-reanchor .tmp/reanchor-tmp
export TMPDIR=$PWD/.tmp/reanchor-tmp
# §1 diff gate
git diff 66502f6..2b1ba19 --name-only -- 02_source
git diff 66502f6..2b1ba19 --stat -- 02_source
# > 03_evidence/fix-r1-reanchor/diff-66502f6-2b1ba19.log
# §2 per-file proof (checker script, scratch in .tmp/)
python3 .tmp/reanchor-tmp/check_byte_identity.py
# > 03_evidence/fix-r1-reanchor/byte-identity-check.log  (exit 0)
# §3 re-record audit
git diff 30bfd0c..2b1ba19 -- 04_review/REVIEW_INDEX_FIXR1.md 04_review/REVIEW_PACK_FIXR1_06.md
grep -rn "f1c6b2d7|70cbffe1|b0361226" 04_review/REVIEW_INDEX_FIXR1.md 04_review/REVIEW_PACK_FIXR1_*.md 04_review/REVIEW_FINDINGS_FIXR1.md 04_review/REVIEW_COVERAGE_FIXR1.csv
# (only the 2 deliberate CSV sha256_at_66502f6 rows, §3)
# §4 index edit (header anchor/release + new re-anchor section)
# new-release numbers cross-check (read-only):
git show 213677f:05_release/RELEASE_MANIFEST.json
git show 213677f:05_release/SHA256SUMS.txt
# §5 validators (from 02_source)
../.venv/bin/python scripts/verify_review_pack.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'
# > 03_evidence/fix-r1-reanchor/verify-review-pack-fixr1-2b1ba19.log (exit 0)
../.venv/bin/python scripts/check_review_coverage.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'
# > 03_evidence/fix-r1-reanchor/check-review-coverage-fixr1-2b1ba19.log (exit 0)
# §7 gates (from 02_source)
../.venv/bin/python -m pytest -q
# > 03_evidence/fix-r1-reanchor/pytest-full.log (848 passed, 40.01 s)
node --test oracle/verify.test.mjs
# > 03_evidence/fix-r1-reanchor/oracle.log (26/26)
../.venv/bin/python scripts/repeat_hash.py --runs 100
# > 03_evidence/fix-r1-reanchor/repeat-hash.log (1 hash)
../.venv/bin/python scripts/s0_gate.py --out-dir ../03_evidence/fix-r1-reanchor/s0
# > 03_evidence/fix-r1-reanchor/s0-gate.log (S0 PASS 10/10)
../.venv/bin/python scripts/verify_release.py --tmp-dir ../.tmp/reanchor-tmp/verify-release
# > 03_evidence/fix-r1-reanchor/verify-release.log (PASS)
# commit (this file + the edited index)
git add 04_review/REVIEW_INDEX_FIXR1.md 03_evidence/fix-r1-reanchor
git commit -m "Review: FIX-R1 pack re-anchored 66502f6 -> 2b1ba19 (PASS, 0 P0/0 P1)"
```

## 9. Log index (`03_evidence/fix-r1-reanchor/`)

`byte-identity-check.log`, `diff-66502f6-2b1ba19.log`,
`verify-review-pack-fixr1-2b1ba19.log`,
`check-review-coverage-fixr1-2b1ba19.log`, `pytest-full.log`,
`oracle.log`, `repeat-hash.log`, `s0-gate.log`,
`s0/S0_GATE.json`, `s0/S0_REPORT.md`, `s0/performance.json`,
`verify-release.log`, `SUMMARY.md` (this file). Scratch (not
committed): `.tmp/reanchor-tmp/` (byte-identity checker script,
pytest tmp, verify-release tmp).

## 10. Open items / notes for the coordinator

- **Count note (§3):** the brief said 6 re-recorded rows in the
  FIXR1 pack; the diff shows 5 (4 script + 1 pack-06 self-row).
  All 5 verified; nothing is stale. If the coordinator's count
  of 6 refers to something else, the per-file table in §2 plus
  the validator PASS in §5 bound it either way — every
  machine-checked row in the pack matches at `2b1ba19`.
- **Stale prose (pre-existing, not introduced here):** pack-06
  prose still cites the pre-redirect script versions
  (`verify_review_pack.py` "(253)", `check_review_coverage.py`
  "(125)", `:71`) — already flagged in the validator-refreeze
  SUMMARY §15. Only inventory rows were updated, per the
  re-record discipline; a P2 note if R2 re-reads those docs
  literally.
- **No R2 submitted, no GitHub upload, no merge** — per task.
  The pack now validates against `2b1ba19` with the shipped
  scripts; R2 can be dispatched in the same conversation
  (round 2 of 5).
