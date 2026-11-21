# P027 BenchReceipt — FIX-R1 Independent Review Index

- **Anchor commit:** `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`
  (branch `fix-r1`, frozen tree `02_source` = 355 files)
- Frozen candidate commit: `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`
- **Release commit:** `213677f` ("Release: second re-freeze r1,
  validator redirect (frozen commit 2b1ba19) — FREEZE VALID")
- **Control / summary commit at assignment:** `56a0b4e`
- **Spec version:** 1.2.0 (ADR-007)
- **Reviewer:** independent, review-only; did not write the fix code.
- **R1 verdict this pack answers:** FINAL_VERDICT: FAIL (1 new P0
  P0-R1-01, 1 new P1 P1-R1-01, 22 P2 cumulative) — full text in
  `~/workspace/P027_FINAL_REVIEW_R1.md`.

## Re-anchor to `2b1ba19` (branch `fix-r1-reanchor`, this review)

This pack was originally written and verified against anchor
`66502f6` / release `b221401`. It is re-anchored here to `2b1ba19`
/ release `213677f` without re-reading any production file,
because the only `02_source` difference between the two anchors
is the validator redirect itself:

- `git diff 66502f6..2b1ba19 -- 02_source` lists exactly two
  files: `02_source/scripts/verify_review_pack.py` and
  `02_source/scripts/check_review_coverage.py` (the `--index` /
  `--pack-glob` redirect; P2-28 fix). The same diff restricted to
  the 34 key files alone is 0 bytes.
- All 34 key files — and the one further production inventory row
  (`02_source/src/benchreceipt/schemas/README.md`, `Key = no`) —
  were re-verified one by one by this reviewer: SHA-256 + line
  count of the blob at `66502f6` == blob at `2b1ba19` == the
  recorded inventory value. Per-file table:
  `03_evidence/fix-r1-reanchor/byte-identity-check.log` (35/35
  OK-IDENTICAL).
- The two validator scripts are the intended exception: their
  recorded rows now hold the new values (`verify_review_pack.py`
  `eae97402…`, 289 lines; `check_review_coverage.py` `7775da39…`,
  194 lines), verified against the working tree and the `2b1ba19`
  blob; their `66502f6` values (`f1c6b2d7…`, 253 lines;
  `70cbffe1…`, 125 lines) were confirmed as the known old ones.
  The 6 pack rows likewise match the working tree and `2b1ba19`.
- Of the worker's re-recorded inventory rows, the FIXR1 files
  carry 5 changed rows (4 script rows: 2 in this index + 2 in
  `REVIEW_PACK_FIXR1_06.md`; 1 pack-06 self row in this index) —
  all 5 verified character-for-character above. (The task brief
  said 6; the `30bfd0c..2b1ba19` diff over the FIXR1 files shows
  5. The T013 files carry 5 further re-recorded rows of the same
  pattern. No FIXR1 inventory row was left stale: no old script
  SHA remains in any FIXR1 inventory table.)
- `REVIEW_COVERAGE_FIXR1.csv` keeps its `path_at_66502f6` column
  name (renaming it would force another coverage-script change
  and re-freeze). The column records the paths as of the original
  review commit; the 34 key files at those paths are the ones
  proven byte-identical at `2b1ba19` above. Its
  `sha256_at_66502f6` values for the two validator scripts are
  likewise the hashes AT `66502f6` (old versions) by design —
  that column is not read by `check_review_coverage.py`, which
  only uses `path_at_66502f6` + `key`.
- Historical prose below still says `66502f6` where it describes
  the original verification (Conclusion, "Freeze identity",
  "Coverage", the "Re-anchored validator simulation" row): those
  sentences describe what was done at the original anchor and are
  left as the record. The machine-checkable anchor is the header
  above (`2b1ba19`), which is what the validators parse. The
  "Freeze identity" table preserves the original `b221401`
  numbers; the new release's numbers are in
  `03_evidence/fix-r1-validator-refreeze/SUMMARY.md` §4–§5
  (`source.zip` `15d1dd0b…`, 433,074 B, 355 files; `dist.zip`
  `eb73174a…`; bundle `79faf42a…`; manifest `frozen_commit` =
  `2b1ba19…`, verified by this reviewer from the `213677f`
  manifest).
- After this re-anchor, the new validator calls PASS exit 0
  against `2b1ba19` (see `03_evidence/fix-r1-reanchor/` logs).

## Conclusion

**FINAL_VERDICT: PASS — 0 P0 / 0 P1.**

- **P0-R1-01 CLOSED:** legacy receipts with both after fields deleted
  now fail closed (`UNBOUND` + `MISSING_FIELD`, jobs 0, CLI exit 2)
  in both the Python CLI and the Node Oracle, and in a fresh venv
  installed from the new `dist.zip` wheel (2/2 cases). Originals
  still `UNBOUND` + `SOURCE_MUTATED_DURING_RUN`.
- **P1-R1-01 CLOSED:** this pack is anchored to the frozen commit
  `66502f6` (not `cfede271`); every inventory row was compared
  against `66502f6` by SHA-256, and all 3 schema files were verified
  at their new paths under `02_source/src/benchreceipt/schemas/`.
- **T013 P1s F-01–F-10:** all fixed in the code read.
- **New findings:** 9 × P2 (P2-22–P2-30), all non-blocking; carried
  P2-01–P2-21 as documented in `REVIEW_FINDINGS_FIXR1.md`
  (P2-15 now partially fixed).

## Freeze identity (independently computed by this reviewer)

| Artifact | Bytes | SHA-256 | Verdict |
|---|---|---|---|
| `05_release/source.zip` | 431,740 | `873b4dc43252202b17432c619397254a480e2dcfe10b43b7404d14b0efcd420b` | ✓ matches manifest; 355/355 files byte-identical to the frozen tree at `66502f6` (prefix-stripped) |
| `05_release/dist.zip` | 152,883 | `da900faf679551ab6599c2ed333923bc151032957ceba2542ff065a51fc1bacd` | ✓ matches manifest; wheel 27 entries incl. 3 schemas, MIT, `Requires-Python >=3.12`, zero runtime deps |
| `benchreceipt-66502f625597.bundle` (from `b221401`) | 3,844,063 | `86c4c82ed019803d349997c5708d62805b918c7b89675e181a20b5f4d00d0dc8` | ✓ matches manifest |
| `05_release/SHA256SUMS.txt` (from `b221401`) | 409 | `d7568b5f1dc475ab79a488f83a672e58275a9058bf40771f3d4c41245f8de29a` | ✓ 5 entries, all matching (`.gitkeep` `e3b0c442…`, FREEZE_REPORT `40e1ace2…`, bundle, dist.zip, source.zip) |
| `05_release/RELEASE_MANIFEST.json` (from `b221401`) | 3,177 | `64476e34487a…` | ✓ `frozen_commit` = `66502f6…`, `spec_version` 1.2.0; gates 848/0, 26/26, S0 16/16 + 36/36 + 52/52, repeat hash `a19054f1…`, golden `fb8e70a1…`, reason-codes `16feb3b8…` — all reproduced by this reviewer's re-runs |
| `05_release/.gitkeep` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | ✓ present — P2-R1-01 closed |

Notes:

- The frozen commit `66502f6` is a pure evidence commit on top of
  FIX-R1 commit `737e0b1` (`git diff 737e0b1 66502f6 -- 02_source`
  is empty).
- At `66502f6` itself, the on-disk tracked `05_release/` files are
  still the old a07dc79 release (FREEZE_REPORT 21,582 B, old
  SHA256SUMS, old bundle) — expected: the re-freeze lives in
  `b221401`. `verify_release.py` was therefore run on a scratch
  worktree at `b221401` (PASS), not on this branch.
- `source.zip` / `dist.zip` are gitignored (`*.zip`, `.gitignore:13`)
  and not committed in `b221401` — only their hashes are tracked
  (see P2-30). The copies verified here are the on-disk ones on this
  VM; a fresh clone of `b221401` alone cannot reproduce the release
  without the Drive archive.

## Coverage: 34/34 key files read in full

34 key files (`Key = yes`) + 3 `Key = no` files = **37/37 inventory
rows read in full at `66502f6`**. Per-file SHA-256, line counts and
vs-T013 status are in `03_evidence/fix-r1-review/inventory_table.md`
(and `REVIEW_COVERAGE_FIXR1.csv`). Summary vs T013 anchor
`cfede271`: 21 UNCHANGED, 14 CHANGED, 2 MOVED+CHANGED (schema files;
`policy.v1.json` and `result.v1.json` byte-identical after the move,
only `run.v1.json` changed). Note: `verify_review_pack.py` and
`check_review_coverage.py` show as UNCHANGED — they do not exist as
blobs at `cfede271` on main (added in T013-PREP `0946203`); their
SHA-256 matches the T013 table.

## File inventory

| Path | SHA-256 | Lines | Pack | Key | Status vs T013 |
|---|---|---|---|---|---|
| `02_source/src/benchreceipt/capture.py` | `6ba926dc391412e5b3cea5e2ffd5f61c11e2922d0785bfbb43c4a208349c5f25` | 674 | 1 | yes | CHANGED |
| `02_source/src/benchreceipt/git_identity.py` | `61f1a53fae80422cf3f6d3b1cb38ac5e9814c948868c85301f590efa2792542a` | 213 | 1 | yes | UNCHANGED |
| `02_source/src/benchreceipt/ci_metadata.py` | `960ab6c537d39024e45ed213d17cef85d40eedb030876cbdeedc9e2daac0f0ac` | 196 | 1 | yes | UNCHANGED |
| `02_source/src/benchreceipt/command.py` | `0fedd5aa4b7176e0abcf1d846e58237a30907ccff97dffe5c8dc864e7cebf276` | 289 | 1 | yes | CHANGED |
| `02_source/src/benchreceipt/canonical.py` | `540d16a88e29e9ccbd1c3959c24b4c16b2a43505a48d8d8830030ae6fc147c88` | 50 | 1 | yes | UNCHANGED |
| `02_source/src/benchreceipt/verify.py` | `7c70f44570baf6070a1e39e8e165457e5b040f87fd3abcf31faaed3acd47cfe1` | 970 | 2 | yes | CHANGED |
| `02_source/src/benchreceipt/matrix.py` | `6c2cbe8bf70c24a3e48bad10b9df84e9b19df1309a48e3caaa2a692176fe04f3` | 101 | 2 | yes | UNCHANGED |
| `02_source/src/benchreceipt/reports/junit.py` | `bb5af528f6d98a6e9a49f164d86c6413c67234f5a5b11ba8e17fa6e8b6dd7242` | 199 | 2 | yes | CHANGED |
| `02_source/src/benchreceipt/reports/lcov.py` | `80c3f2b53b55ea98ddcd8efdcbb276754d62f6eb7273e92735dd5fb6f4612f41` | 309 | 2 | yes | CHANGED |
| `02_source/src/benchreceipt/bundle.py` | `ce557f6f4ca79497be3b66ce4196ce9c7bae5b7036dc68327cabe118d0af0168` | 788 | 3 | yes | UNCHANGED |
| `02_source/src/benchreceipt/render/html.py` | `66704da5fad44da9d15d4edef7a5580446926e1d9f92f0e50b5259ec2c9fcf63` | 693 | 3 | yes | UNCHANGED |
| `02_source/src/benchreceipt/cli.py` | `51fb6c3189ad8bc8776ce8fe4014984df5eb7e4425e01042d115f2f5ce1752a7` | 381 | 3 | yes | CHANGED |
| `02_source/src/benchreceipt/__main__.py` | `30819d5b2ec5058171bac68f863dfb03f1d6b8858116dcca4d2eb15ea08bb278` | 13 | 3 | yes | UNCHANGED |
| `02_source/src/benchreceipt/__init__.py` | `1b7920a55ec70c3c210a5b3e760054d810774d0b8d452ff59873545aba7cae44` | 10 | 3 | yes | CHANGED |
| `02_source/src/benchreceipt/render/__init__.py` | `ddec99272b71a4193baecf2c0422118733cc3dc63e27cefa6a2895aad603489d` | 5 | 3 | yes | UNCHANGED |
| `02_source/src/benchreceipt/reports/__init__.py` | `73c8c07bffb35e8d59420d00de6911bdaf94bff086c337bf299d630daba03527` | 10 | 3 | yes | UNCHANGED |
| `02_source/src/benchreceipt/schema.py` | `3b0ce03abdcdbe34fdc8c66685b3cee84ba3d074192e281792a4c13517b31103` | 270 | 4 | yes | CHANGED |
| `02_source/src/benchreceipt/policy.py` | `683ef274cb87b8777ea04b8bb5ecf3f1dc85c81a6c9902f4dc059a8f6bf4b5e1` | 124 | 4 | yes | UNCHANGED |
| `02_source/src/benchreceipt/schemas/run.v1.json` | `fce85f3decbdcc1043df2ea852f60c7e033b5bd148d498f28704b641c7479166` | 1 | 4 | yes | MOVED+CHANGED |
| `02_source/src/benchreceipt/schemas/policy.v1.json` | `2e555dc3c954b08ac70d2baeb22e449886c88e9ad5dfdc8c7f604daa5312f37a` | 1 | 4 | yes | UNCHANGED |
| `02_source/src/benchreceipt/schemas/result.v1.json` | `2f16a1024bb589063fa89eeac9ae643b5bea52db1bee0dd73bdf1ff61f30aa11` | 1 | 4 | yes | UNCHANGED |
| `02_source/src/benchreceipt/schemas/README.md` | `27613c955a036837bd20bb3dd2e3e9557373483a6ae49e869ab42bfb07fd4087` | 90 | 4 | no | MOVED+CHANGED |
| `02_source/oracle/verify.mjs` | `ac65f524c4fa99d601c0dad80e44e27b75d18a5d81cc4933155755219babf800` | 1823 | 5 | yes | CHANGED |
| `02_source/oracle/verify.test.mjs` | `bdab56971828380b2d35f460496072756b60cdfe8784bd4a5daff6365b7c0754` | 606 | 5 | yes | CHANGED |
| `02_source/oracle/README.md` | `bd1e243e41e9e80e6701b2e717e25a3f2503f847fa9cd50c40ea7e232d72b4c1` | 58 | 5 | yes | CHANGED |
| `02_source/pyproject.toml` | `60bb4f4db82513c4103e48ed823e5d05a3014f700f7a015d795bcde651efc255` | 63 | 6 | yes | CHANGED |
| `02_source/examples/github-actions/ci.yml` | `9c672a4cafe9be66aac0d6b8a6849f6b90e237d0d29cf73c59c2aee37ffec7cf` | 190 | 6 | yes | UNCHANGED |
| `02_source/scripts/s0_gate.py` | `04dca6fa77e6bd684e650602ae3c6f83eb248664ae721b9c9eaadb93b878be25` | 375 | 6 | yes | CHANGED |
| `02_source/scripts/repeat_hash.py` | `64281520c01f739a8e138804c9b9cf3aa218f7ae9b5ae31f06277aa858f94829` | 64 | 6 | yes | UNCHANGED |
| `02_source/scripts/validate_workflow_example.py` | `8412a94c666e2edaa5fac597f3d8ff232d27a34967d7a3db73efa193fe9239bb` | 601 | 6 | yes | UNCHANGED |
| `02_source/scripts/offline_check.py` | `3deb9b75d40088c45192c5150c98c725a6a98e27010deb7c1450c030ca45dfba` | 240 | 6 | yes | UNCHANGED |
| `02_source/scripts/performance_smoke.py` | `9deb600338dfbc38edf1487c932e86ac4b078b0006a4c9a315801a1ce9b49b7c` | 165 | 6 | yes | UNCHANGED |
| `02_source/scripts/privacy_scan.py` | `cdb5566b99a8cb95d7532b6bac8dde58cdffe0f3ab0b2b4a2d49eb42814d5363` | 267 | 6 | yes | UNCHANGED |
| `02_source/scripts/build_fixtures.py` | `f6a9ff891ce2730ec41e3b86aa41cd7e12794083f89957d56f725ede05195003` | 607 | 6 | yes | CHANGED |
| `02_source/scripts/ui_smoke.py` | `298de709d1593b1e5c802bc4b7cdae2afe30efc35cd551284b6c3797ddef907d` | 120 | 6 | yes | UNCHANGED |
| `02_source/scripts/verify_review_pack.py` | `eae974023d4d7b673b561f79fd04d7463604b6aec9076b89d7ab82830b29cff0` | 289 | 6 | no | UNCHANGED |
| `02_source/scripts/check_review_coverage.py` | `7775da3902ddafed06129dc6f9970b896f457ccf294557efa607bef7cee2d168` | 194 | 6 | no | UNCHANGED |
| `04_review/REVIEW_PACK_FIXR1_01.md` | `d75105baae629fcb06b75839f3b572b8cba534761623e974b8557a06b8bf0787` | 71 | 01 | no | pack |
| `04_review/REVIEW_PACK_FIXR1_02.md` | `af02a9a5598085ef37fde3c97b34bc455ce427be21ce736a354f0f218c709a56` | 72 | 02 | no | pack |
| `04_review/REVIEW_PACK_FIXR1_03.md` | `03ef5d888279332e43c80e0e8ebafc03a66adc9eee398bec8e52738c3ec47893` | 66 | 03 | no | pack |
| `04_review/REVIEW_PACK_FIXR1_04.md` | `27a4892228f444497e5c005d04da97e636f4d31341c86569c07e1d89d51405df` | 71 | 04 | no | pack |
| `04_review/REVIEW_PACK_FIXR1_05.md` | `ffa131e6470e244fcb66901ca87d15c421979b1de24fc77dcc0e32cd65905dba` | 61 | 05 | no | pack |
| `04_review/REVIEW_PACK_FIXR1_06.md` | `7ddaacde28c8809cdfb2ffbacb9f7d6a4a2e9dda17d79a3c5fb085c543bb99df` | 103 | 06 | no | pack |

## Independent re-runs (all by this reviewer, TMPDIR on persistent disk)

| Check | Result | Log |
|---|---|---|
| Full pytest | **848 passed** in 57.07 s | `03_evidence/fix-r1-review/pytest-full.log` |
| Oracle self-tests | **26/26** (incl. 2 FIX-R1 tests) | `oracle.log` |
| S0 gate | **PASS 10/10** — 16/16 controls, 36/36 faults, 52/52 parity, false PASS/block 0, repeat-100 1 hash `a19054f1…d530`, P95 0.150 s, privacy 0, offline 0 | `s0/S0_GATE.json`, `s0_gate.log` |
| Repeat-100 hash | **1 hash** `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530` | `repeat-100.log` |
| P0 fixture repro (e5/e6 × orig/legacy × Python+Oracle) | **8/8 cells** as expected (legacy `UNBOUND`+`MISSING_FIELD`, jobs 0, exit 2) | `p0-fixture-repro.run.log`, `p0-fixture-repro/` |
| Reviewer wheel repro (original R1 script, new wheel) | case 1 legacy `UNBOUND`+`MISSING_FIELD`; final assert fails **by design** (asserts old `BOUND_PASS`) | `wheel_repro_original_script.log` |
| Post-fix wheel repro (2/2 cases) | **PASS** — 2/2 legacy fail-closed | `wheel_repro_postfix.log` |
| Offline install (fresh venv, new `dist.zip` wheel) + capture/verify | **BOUND_PASS**, jobs 1 | `offline_install.log` |
| `offline_check.py` | **PASS** (static CLEAN, socket 0, verify BOUND_PASS) | `offline_check.log` |
| `privacy_scan.py` | 193 files, **0 findings** | `privacy_scan.log` |
| `validate_workflow_example.py` | **PASS** | `validate_workflow.log` |
| `ui_smoke.py` | **PASS** (3 reports, 0 external refs; screenshots NOT_TESTED) | `ui_smoke.log` |
| `verify_release.py` (scratch worktree at `b221401`) | **PASS** | `verify_release_b221401.log` |
| Old-anchor `verify_review_pack.py` / `check_review_coverage.py` (pre-delivery) | **PASS**, exit 0 (against the old T013 pack) | `verify-review-pack-old-anchor.log`, `check-review-coverage-old.log` |
| Post-delivery `verify_review_pack.py` (old index) | FAIL as expected — 12 problems pre-reformat, 34 post-reformat; every problem is the old `cfede271` anchor itself (P2-28) | `verify-review-pack-post-delivery.log`, `verify-review-pack-post-reformat.log` |
| Re-anchored validator simulation (FIXR1 index + `66502f6`, FIXR1 packs only, validator's own functions) | **PASS** — 43 index rows, 37 pack rows, 31 key files, all SHA-256 + line counts match | `validator_reanchored_simulation.log`, `validator_parse_check.log` |
| Spec sync (mirror + manifest + SHA256SUMS) | **CONVERGED 4/4**; SECRET_HINTS 1× in each BOOK.md | `spec_sync.log`, `spec_docx_check.log` |

## Review-pack validators — known limitation (P2-28)

`verify_review_pack.py` / `check_review_coverage.py` are anchored to
the T013 index (`cfede271`, old schema paths). They PASS against the
old pack (pre-delivery runs above). This pack's files already use the
validators' parseable format (`| Path | SHA-256 | Lines | … |` tables
here and in all six packs, plus the `Frozen candidate commit:` line
at the top of this index), so a re-anchored run can parse them; the
remaining gaps are validator-side: it reads `REVIEW_INDEX.md` (not
`REVIEW_INDEX_FIXR1.md`), `_is_key_production` misses the new schema
path, and its pack glob also covers the old T013 packs (anchored to
`cfede271`, would mismatch `66502f6` blobs). The post-delivery run
against the old index fails as expected (12 problems pre-reformat;
34 after the reformat — every one of them is the old anchor itself:
SHA/line mismatches = the FIX-R1 delta, moved schemas "MISSING" at
`cfede271`). A simulation of the validator re-anchored to this index
and `66502f6`, pack glob scoped to FIXR1 files, **PASSES** (43 index
rows, 37 pack rows, 31 key files, all SHA-256 + line counts match).
Full detail in `REVIEW_FINDINGS_FIXR1.md` P2-28. `check_review_coverage.py` still
passes post-delivery only because it reads the old
`REVIEW_COVERAGE.csv`.

## Deliverables (new files; T013 pack untouched)

- `04_review/REVIEW_INDEX_FIXR1.md` (this file)
- `04_review/REVIEW_PACK_FIXR1_01.md` … `REVIEW_PACK_FIXR1_06.md`
- `04_review/REVIEW_FINDINGS_FIXR1.md`
- `04_review/REVIEW_COVERAGE_FIXR1.csv`
- `03_evidence/fix-r1-review/SUMMARY.md` + all raw logs in
  `03_evidence/fix-r1-review/`
