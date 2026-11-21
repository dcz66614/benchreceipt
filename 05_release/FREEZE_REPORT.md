# P027 BenchReceipt — Release Freeze Report (FIX-R1 validator redirect, release r1 re-freeze)

> **✅ FREEZE VALID.** This re-freeze is for FIX-R1 (commit
> `737e0b1`, "fail-closed legacy after-identity (P0-R1-01), Scheme
> A") plus the validator redirect (P2-28 fix): the two pack-check
> scripts now take `--index` / `--pack-glob`, and the schemas
> key-file rule covers the post-T014-F1 location
> `02_source/src/benchreceipt/schemas/*.json`. Frozen from control
> commit `2b1ba19`, whose `02_source` tree differs from `737e0b1`
> ONLY in the two validator scripts (`git diff 66502f6 2b1ba19 --
> 02_source` = those two files; the 34 FIX-R1 key production files
> are byte-identical). It replaces the FIX-R1 re-freeze artifacts
> (source.zip `873b4dc4…`, dist.zip `da900faf…`, bundle `86c4c82e…`
> for frozen commit `66502f6`).
> `scripts/verify_release.py` PASSES fully, including the
> offline-install capture → verify round trip to `BOUND_PASS`.

- **Freeze date (UTC):** 2026-11-18
- **Branch:** `fix-r1`
- **Frozen commit (source freeze):**
  `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09` ("Control: validator
  redirect + re-verification evidence (frozen-tree candidate)")
- **FIX-R1 commit:** `737e0b17a975f14f080bd4c27077e6bab215b273`
  (`02_source` differs only in the two validator scripts; see above)
- **Previous frozen commit:** `66502f6255976b44b3efebb7da778ea8807b1ba1`
  (FIX-R1 re-freeze; identical `02_source` except the two scripts)
- **Spec version:** 1.2.0 (SPEC_VERSION bumped 1.1.0 → 1.2.0 by
  FIX-R1; ADR-007 overturns ADR-005 decision 4)
- **Release ID:** r1 (fifth freeze of r1; replaces the FIX-R1
  re-freeze of the same release id)

## 1. Gate results (all re-run fresh on 2026-11-18, branch `fix-r1`)

All commands run from `02_source` with the project `.venv` (Python
3.12.3), `TMPDIR=~/workspace/p027-benchreceipt/.tmp/validator-refreeze-tmp`
(`/tmp` is a 512 MB tmpfs). Logs under
`03_evidence/fix-r1-validator-refreeze/`.

| Gate | Command | Exit | Result | Log |
|---|---|---|---|---|
| Full suite | `../.venv/bin/python -m pytest -q` | 0 | **848 passed** in 39.93 s (same count as the FIX-R1 re-freeze) | `pytest.log` |
| Oracle tests | `node --test oracle/verify.test.mjs` | 0 | **26/26 pass** | `oracle.log` |
| S0 gate | `../.venv/bin/python scripts/s0_gate.py` | 0 | **S0 PASS 10/10** — 16/16 controls, 36/36 faults, false PASS 0, false block 0, parity 52/52, repeat-100 1 hash, P95 0.0925 s, 0 network refs, 79 receipts 0 violations | `s0-gate.log`, `03_evidence/s0/S0_GATE.json` (regenerated 2026-11-18T04:33Z) |
| Repeat-100 | `../.venv/bin/python scripts/repeat_hash.py --runs 100` | 0 | **1 distinct hash**: `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530` (fixture `n02-two-job-pr-head`) | `repeat-hash.log` |
| e7/e8 legacy spot check | S0 per-fixture (threshold 2, correct reason code) | 0 | **e7 + e8 both UNBOUND + MISSING_FIELD** (Python and Oracle, parity, pass); n01 still **BOUND_PASS** | `03_evidence/s0/S0_GATE.json` per-fixture rows `e7-legacy-clean-checkout`, `e8-legacy-empty-commit`, `n01-single-pr-head` |
| Review pack (old, default) | `../.venv/bin/python scripts/verify_review_pack.py` | 1 (expected) | FAIL — **34 problems, byte-identical output** to the pre-change baseline and to the reviewer's post-reformat log; every problem is the old `cfede271` anchor itself (P2-28, unchanged) | `verify-review-pack-OLD-default-baseline.log`, `verify-review-pack-NEW-default.log` (diff empty) |
| Review pack (new, FIXR1) | `../.venv/bin/python scripts/verify_review_pack.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'` | 0 | **PASS** — commit `66502f62…`, 43 index rows, 37 pack rows, 34 key files all listed in 6 packs, all SHA-256 + line counts match | `verify-review-pack-NEW-fixr1.log` |
| Coverage (old, default) | `../.venv/bin/python scripts/check_review_coverage.py` | 0 | **PASS** — all 34 key files reviewed; output byte-identical to the pre-change baseline | `check-review-coverage-OLD-default-baseline.log`, `check-review-coverage-NEW-default.log` (diff empty) |
| Coverage (new, FIXR1) | `../.venv/bin/python scripts/check_review_coverage.py --index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob 'REVIEW_PACK_FIXR1_*.md'` | 0 | **PASS** — all 34 key production files reviewed in `04_review/REVIEW_COVERAGE_FIXR1.csv` | `check-review-coverage-NEW-fixr1.log` |
| Release validator | `../.venv/bin/python scripts/verify_release.py` | 0 | **PASS — including the offline-install check** (fresh venv + `--no-index` wheel install + capture → verify `BOUND_PASS`); see §3 | `verify-release.log` |
| Offline check | `../.venv/bin/python scripts/offline_check.py --out ../03_evidence/fix-r1-validator-refreeze/offline_check.json` | 0 | PASS — static CLEAN, 0 socket events, verify BOUND_PASS | `offline-check.log`, `offline_check.json` |
| Workflow example | `../.venv/bin/python scripts/validate_workflow_example.py` | 0 | PASS — 4 matrix jobs, policy agreement + token-free + local-install checks OK | `validate-workflow.log` |
| Privacy scan | `../.venv/bin/python scripts/privacy_scan.py` | 0 | 193 files scanned, 0 findings | `privacy-scan.log` |
| UI smoke | `../.venv/bin/python scripts/ui_smoke.py --out-dir ../03_evidence/fix-r1-validator-refreeze/ui` | 0 | PASS — 3 reports rendered (n01 BOUND_PASS 7742 B, g1 BOUND_FAIL 9002 B, d1 UNBOUND 8093 B), 0 external refs; screenshots NOT_TESTED (no browser on this VM) | `ui-smoke.log`, `ui/report-*.html` |

**P0 = 0, P1 = 0.** No new P0/P1 was found in this re-freeze. The
T013 P2s (P2-01–P2-04 + P2-05–P2-21) are recorded non-blocking
observations and were NOT fixed here (§5). The R1 findings
(P0-R1-01 FIXED by FIX-R1; P1-R1-01 review-pack anchor lag and
P2-R1-01 `.gitkeep` in SHA256SUMS) are addressed in §7. P2-28
(validator hard-coded to the old pack) is FIXED by the redirect
in this freeze (§7); the old pack's 34 problems are now proven to
be the anchor itself, not the validator.

## 2. Frozen artifacts (`05_release/`)

| File | Bytes | SHA-256 |
|---|---|---|
| `source.zip` | 433074 | `15d1dd0bcfd217cc060ba1501c9205c9aa2fde9300c5734077867b664cac54af` |
| `dist.zip` | 152880 | `eb73174ab6e51069d2565ebd793d91369b772c33115cf2ba91926bd21b2b48b1` |
| `benchreceipt-2b1ba19f7f46.bundle` | 4622659 | `79faf42ab7b5d9487cea9bdec8b24f69b56c4dc3ef0c74dd9a5b7d016f5474b1` |
| `SHA256SUMS.txt` | — | (see `RELEASE_MANIFEST.json`; verified with `sha256sum -c`) |
| `RELEASE_MANIFEST.json` | — | (values in §3; the manifest lists SHA256SUMS.txt) |
| `FREEZE_REPORT.md` | — | (this file) |

- **source.zip:** 355 files, 1,160,832 source bytes — the `02_source/`
  tree at the frozen commit (`src`, `oracle`, `schemas` under
  `src/benchreceipt/schemas/`, `scripts`, `tests`, `fixtures`,
  `examples`, `docs`, `README.md`, `LICENSE` (MIT),
  `pyproject.toml`, `requirements-dev.lock`), verified file-by-file
  against `git ls-tree` blobs by `verify_release.py`. (355 files
  in the FIX-R1 re-freeze as well; +4,299 source bytes here — the
  two redirected scripts only.)
- **dist.zip:** 4 entries — `benchreceipt-0.1.0-py3-none-any.whl`
  (80,150 B, 27 entries incl. `benchreceipt/schemas/run.v1.json`,
  `policy.v1.json`, `result.v1.json`),
  `benchreceipt-0.1.0.tar.gz` (73,334 B, repacked sdist, see §4;
  contains `src/benchreceipt/schemas/*.json`), `LICENSE` (MIT),
  `INSTALL.txt`. Wheel METADATA: `License-Expression: MIT`,
  `Requires-Python: >=3.12`, zero runtime dependencies.
  **Offline install PROVEN:** fresh venv + `pip install --no-index`
  succeeds, bare `benchreceipt --help` exits 0, and the capture →
  verify round trip returns `BOUND_PASS` (§3, §6).
- **Bundle:** `git bundle` of ref `fix-r1` at the frozen commit
  (a bare SHA is refused by `git bundle create` — "Refusing to
  create empty bundle" — so the freeze script bundles the ref
  pointing at the commit). The bundle advertises
  `refs/heads/fix-r1` but no HEAD, so a bare `git clone`
  fetches nothing: clone it with
  `git clone --branch fix-r1 <bundle> <dir>` (the procedure
  `verify_release.py` uses). `git bundle verify` passes; cloning
  from it checks out the frozen commit and reproduces the
  `02_source` tree file-by-file (checked by `verify_release.py`).

## 3. `verify_release.py` result — PASS

> (Full log: `03_evidence/fix-r1-validator-refreeze/verify-release.log`. The
> validator was run after the manifest step; §3 was then edited
> only to quote its verbatim output, and the manifest + validator
> were re-run so `SHA256SUMS.txt` / `RELEASE_MANIFEST.json`
> match this exact report text.)

```
PASS: verify_release: frozen commit 2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09, source.zip matches the frozen tree file-by-file, manifest + SHA256SUMS verified, LICENSE MIT in both zips, deps == 0, S0 52/52 + repeat-100 1 hash, bundle clones, offline install checked
```

Every check passed: source.zip matches the frozen tree
file-by-file, manifest + SHA256SUMS verified, LICENSE MIT in both
zips, deps == 0, S0 52/52 + repeat-100 1 hash, bundle clones and
reproduces the tree, and the offline-install check — the check
that caught T014-F1 — passes: fresh venv, `--no-index` wheel
install OK, `--help` OK, capture exit 0, verify `BOUND_PASS`.
The three manifest lags from the previous freeze are gone: the
manifest now records S0 faults **36/36**, parity **52/52**, golden
`fb8e70a136aef710fb59d46addda99df71bafb18320afb23d75b61bf21560497`
(verified against the regenerated `03_evidence/s0/S0_GATE.json`).

Checks performed by the validator (cheap first, offline install last):
manifest values vs files on disk (commit, counts, bytes, SHA-256,
per-file list, no unlisted files); `SHA256SUMS.txt` recomputed;
source.zip vs frozen tree names + bytes; LICENSE MIT in source.zip, in
dist.zip, in the wheel dist-info, and `License-Expression: MIT` in
wheel METADATA; `pyproject.toml` runtime dependencies `== []`;
manifest gate block vs `03_evidence/s0/S0_GATE.json` (S0 PASS, 16/16,
36/36, 52/52, false PASS/block 0, repeat hash `a19054f1…d530`); bundle
verify + clone + tree reproduction; fresh-venv `--no-index` wheel
install + `--help` + capture → verify `BOUND_PASS`.

**Negative control (from T014, still valid):** the validator was run
in `/tmp` against a copy of the T014 release with one corrupted
manifest value (see `03_evidence/t014/verify-release-negative.log`):
it FAILed with exit 1 naming the mismatch (`MANIFEST:
source_zip.sha256 mismatch`). It is not a rubber stamp — and it is
the check that caught T014-F1.

## 4. Freeze procedure (determinism)

`02_source/scripts/freeze_release.py` (proven in T014) builds from
the frozen commit in two passes and compares SHA-256 across both:

1. `freeze_release.py --commit <sha> build` — exports the commit's
   `02_source` tree (`git archive`), normalises all mtimes to the
   commit timestamp, builds `source.zip` from git blobs (fixed zip
   timestamps, sorted names), builds wheel + sdist with a pinned
   toolchain (`python -m build --no-isolation`; setuptools 80.9.0,
   wheel 0.45.1, build 1.2.2, pyproject_hooks 1.2.0, packaging 25.0),
   and creates the bundle. The whole build runs **twice** and is
   accepted only when source.zip, dist.zip and the bundle are
   byte-identical across runs. Two nondeterminism sources were found
   and fixed in T014 (both are handled by the script): the sdist
   PAX mtimes (repacked with fixed mtimes/owners, cleared
   `pax_headers`, sorted members, fixed gzip header) and the bundle
   (`pack.threads=1`). Build commands are recorded in
   `03_evidence/fix-r1-validator-refreeze/freeze-build.log`.
2. `freeze_release.py --commit <sha> manifest --pytest-passed 848
   --oracle-passed 26 --oracle-total 26` — writes `SHA256SUMS.txt`
   (source.zip, dist.zip, bundle, FREEZE_REPORT.md, `.gitkeep`) and
   `RELEASE_MANIFEST.json` (frozen commit, file/byte counts, SHA-256
   of every released file, S0 final hash, suite/Oracle counts, build
   toolchain versions). The manifest was run twice: once for the
   draft report, then again after §3 was finalised with the
   validator result, so the manifest matches the report text on
   disk exactly.

**Why the manifest names the source-freeze commit, not the release
commit.** `RELEASE_MANIFEST.json` is itself committed in the release
commit (the commit that adds `05_release/*` on branch
`fix-r1`), so its `frozen_commit` field can never equal that
commit's own hash: the hash is a fixed point of its own content
(the manifest's bytes determine the tree, which determines the
commit hash, which the manifest would have to contain). The manifest
therefore names the commit whose tree was frozen and verified
(`2b1ba19f…`), and `verify_release.py` enforces that the release
commit's `02_source` tree is identical to that commit's tree
(`git diff 2b1ba19f <release> -- 02_source` is empty at release
time). The release commit hash is recorded in the git log on branch
`fix-r1` (see §9) and in the coordinator's merge record. This
is the "second pass" the task anticipates: build from the tree,
commit, verify the manifest's commit field against the tree the
artifacts were built from — the manifest describes exactly that
tree, and nothing in the release commit changes `02_source`.

**Note:** the script's docstring shows `freeze_release.py build
--commit <sha>`, but `--commit` is a top-level parser argument and
must precede the subcommand (`freeze_release.py --commit <sha>
build …`); the docstring order fails with exit 2 ("unrecognized
arguments: --commit"). This re-freeze used the working order.

## 5. Known limitations carried forward (not fixed in this re-freeze)

### 5.1 T013 P2-01–P2-04 (verified as documented, `LIMITATIONS.md`)

- **P2-01** transient mutate-and-revert undetectable — by construction
  of any before/after snapshot scheme.
- **P2-02** no byte cap on `receipt.json` itself — a 2 MB
  whitespace-padded otherwise-valid receipt still verifies
  `BOUND_PASS` (verdict correct).
- **P2-03** manifest sort order unenforced — a reordered-alone bundle
  manifest still verifies; a flipped byte is still caught.
- **P2-04** bare CR inside an LCOV `SF:` path preserved verbatim
  (`source_file='src/foo\\rbar.py'`); the value never reaches a receipt.

### 5.2 T013 P2-05–P2-21 (non-blocking observations)

- **P2-05** schema pattern anchoring: `re.search` + `$` accepts a
  trailing newline; patterns are not full-string matches. (Matched,
  not fixed, by FIX-R13b's Oracle schema port.)
- **P2-06** giant integers (>4300 digits): production `int()` leaks
  `ValueError` → `INTERNAL_ERROR`; the Oracle treats an over-long
  integer as malformed (`INVALID`). Fail-closed both sides.
- **P2-07** `evaluate()` can return a `result.v1`-schema-invalid result
  when the bundle is very large.
- **P2-08** an invalid `--expected-source-sha` is reported as
  `INVALID_POLICY` with a policy message.
- **P2-09** a dirty tree at capture start is not independently enforced.
- **P2-10** nested `<testsuite>` count attributes are never checked
  (production and Oracle agree).
- **P2-11** report-path `.` segments: schema allows, `verify` passes,
  `bundle` rejects.
- **P2-12** `build_bundle` cleanup runs only on `BundleError`: an I/O
  failure mid-copy leaves a half-written output dir.
- **P2-13** workflow validator accepts a remote `.whl` URL as a "local
  install".
- **P2-14** S0 gate threshold 8 is partly vacuous (`network_requests`
  is a hardcoded 0 in the gate; the gate never runs the socket audit).
  The dynamic audit is covered separately by
  `scripts/offline_check.py`, re-run PASS in this freeze (0 socket events).
- **P2-15** Oracle `INTERNAL_ERROR`: unknown codes map to `INVALID`,
  and the CLI prints no result JSON on internal error. Partly
  addressed by FIX-R13b (`INTERNAL_ERROR` added to the Oracle
  vocabulary/exit map; invalid pins return an `INTERNAL_ERROR`
  result); the CLI-JSON part carries.
- **P2-16** policy `schema_version = true` passes the `const: 1` check
  (Python `True == 1`); the Oracle rejects it.
- **P2-17** dead code and a stale docstring.
- **P2-18** `verify` reads symlinked `receipt.json` / job dirs straight
  through; the Oracle rejects a receipt/job dir whose real path
  escapes its root (`INVALID_RECEIPT`) — deliberate fail-closed
  strictness on the Oracle side.
- **P2-19** privacy scanner coverage gaps.
- **P2-20** `build_fixtures.py` rebuilds the frozen fixture set with no
  guard flag.
- **P2-21** whitespace-only `--expected-run-id` is accepted as a pin.

### 5.3 FIX-R13b known divergences (Oracle vs production, all fail-closed)

Recorded in `03_evidence/fix-r13b/SUMMARY.md` and qualified in
`02_source/oracle/README.md` (T014): Oracle stricter on symlinked
receipt/job dirs than Python (P2-18); giant ints >4300 digits (P2-06);
float-form JSON ints (e.g. `run_attempt: 2.0` — Python rejects,
`JSON.parse` yields `2`, Oracle accepts); `schema_version=true`
(P2-16); UTF-16 / non-UTF-8 JUnit (production decodes per declaration,
Oracle strictly UTF-8); `--expected-attempt abc` exit-code difference
(Python argparse exits 2, Oracle exits 3); Oracle missing
`--policy`/`--evidence` exit 4 (Python argparse exits 2) — pre-existing
behaviour, untouched.

### 5.4 Platforms

**Windows and macOS are NOT_TESTED.** All gates above ran on Linux
(Ubuntu VM, Python 3.12.3, Node v24.22.1). The GitHub Actions example
contains Windows matrix cells that have never run
(`02_source/docs/LIMITATIONS.md`). No cross-platform claim is made.

## 6. README quickstart reproduction (from the frozen DIST)

The dist-based quickstart is now PROVEN by the release validator's
offline-install check (§3): fresh venv, `--no-index` wheel install
from the frozen `dist.zip`, bare `benchreceipt --help` exit 0,
capture exit 0, verify `BOUND_PASS`. The same round trip was
independently smoke-tested before the freeze against a scratch-built
fixed wheel (`03_evidence/fix-t014-f1/wheel-smoke-roundtrip.log`:
capture exit 0, verify `BOUND_PASS`, `jobs_verified=1`). The
editable-install path is covered by the full suite (848 passed)
and the S0 gate, both run from the editable install of the frozen
tree. The T014 frozen-source quickstart (fresh checkout of
`818c012c`, editable install, README quickstart verbatim →
BOUND_PASS) is recorded in the T014 freeze report, superseded by
this dist-proven result.

## 7. The FIX-R1 fix and the validator redirect (what changed vs the FIX-R1 re-freeze)

- **Background:** GPT final review R1 of P027 returned
  FINAL_VERDICT: FAIL with P0-R1-01: legacy receipts WITHOUT
  after-fields still returned `BOUND_PASS` (GPT reproduced 2/2 by
  stripping after-fields from e5/e6 goldens). P1-R1-01: the T013
  review pack anchored `cfede271` ≠ the freeze `a07dc79`.
  P2-R1-01: Drive `05_release` missing zero-byte `.gitkeep`.
- **Fix (commit `737e0b1`, branch `fix-r1`)** — fail-closed legacy
  after-identity, Scheme A: both `git.head_sha_after` /
  `git.tree_sha_after` missing → UNBOUND + MISSING_FIELD
  (jobs_verified 0, CLI exit 2) in Python verify and Node Oracle;
  half-present still SOURCE_MUTATED_DURING_RUN. Schema keeps both
  fields optional. Builder now emits after fields for all fixtures
  (75 receipts gained only the two after fields, values == before;
  e5/e6 byte-identical); new fixtures e7/e8 (legacy shape, no after
  fields), S0 50 → 52, faults 34 → 36, parity 52/52. Golden: only
  e7/e8 appended, no existing value changed. SPEC_VERSION 1.1.0 →
  1.2.0 (MD + DOCX + mirror + SPEC_MANIFEST.json); ADR-007
  overturns ADR-005 decision 4. Full suite 848 passed; S0 10/10;
  Oracle 26/26; repeat-100 1 hash a19054f1... (unchanged).
  Coordinator independently verified the fix (full suite 848,
  S0 PASS 10/10, e7/e8 UNBOUND + MISSING_FIELD, n01 BOUND_PASS;
  logs in `03_evidence/r1-repro/`).
- **P1-R1-01:** the review pack still anchors `cfede271` (T013
  frozen candidate) — the pack is a historical record of T013 and
  is deliberately NOT re-anchored. The default
  `verify_review_pack.py` call therefore FAILs with exactly the
  34 old-anchor problems (byte-identical output before and after
  the redirect, §1); that FAIL is the anchor lag itself, not a
  defect in the frozen tree. The FIXR1 pack anchored at `66502f6`
  is now machine-checkable with the new `--index` / `--pack-glob`
  call (PASS, §1). A fresh review pack for the new freeze is the
  R2 review's job, not this freeze's. No freeze gate depends on
  the pack anchor.
- **P2-R1-01:** `05_release/.gitkeep` (0 bytes, sha
  `e3b0c442…2b855`) exists in `05_release/` and is listed in
  `SHA256SUMS.txt` and in the manifest `files` list — verified
  present in this re-freeze; do not delete it, it ships with the
  Drive archive.
- **P2-28 (FIXED in this freeze — the validator redirect):**
  the two pack-check scripts hard-coded the T013 pack
  (`04_review/REVIEW_INDEX.md`, `REVIEW_PACK_*.md`, and the
  `02_source/schemas/*.json` key-file rule for the pre-T014-F1
  schemas location), so on the new freeze they defaulted to FAIL
  (34 problems, all the old `cfede271` anchor itself) even though
  the reviewer had re-anchored with the scripts' own functions and
  the new pack passed. `verify_review_pack.py` now takes
  `--index` (default `04_review/REVIEW_INDEX.md`) and
  `--pack-glob` (default `REVIEW_PACK_*.md`), and its schemas
  key rule covers both `02_source/schemas/*.json` and
  `02_source/src/benchreceipt/schemas/*.json`.
  `check_review_coverage.py` now takes `--index` (same default)
  and `--pack-glob` (accepted for a uniform CLI; ignored —
  coverage is per-index, not per-pack); its default coverage CSV
  is derived from the index name (`REVIEW_INDEX*.md` →
  `REVIEW_COVERAGE*.csv`), and it accepts the FIXR1 CSV format
  (`path_at_66502f6` / `key`, `key=yes` = reviewed). New calls
  `--index 04_review/REVIEW_INDEX_FIXR1.md --pack-glob
  'REVIEW_PACK_FIXR1_*.md'` PASS exit 0 for both scripts
  (verify: 43 index rows, 37 pack rows, 34 key files; coverage:
  34 key files). Default calls are byte-identical to before the
  change (verify still the same 34 old-anchor problems; coverage
  still PASS). No test covers these two scripts (none exists in
  `02_source/tests/`), so no test was added — adding one would
  have put a new file into the frozen production tree. The
  scripts are pack tooling, read from the working tree by the
  validator, so their inventory rows in `REVIEW_INDEX.md`,
  `REVIEW_INDEX_FIXR1.md`, `REVIEW_PACK_06.md`,
  `REVIEW_PACK_FIXR1_06.md` (plus the two pack-06 rows in the
  indexes, whose bytes changed with them) were re-recorded with
  the new SHA-256 + line counts
  (`verify_review_pack.py eae97402…`, 289 lines;
  `check_review_coverage.py 7775da39…`, 194 lines). The
  `REVIEW_COVERAGE_FIXR1.csv` `sha256_at_66502f6` column was NOT
  touched: it records the hashes AT commit `66502f6`, which are
  unchanged. The 34 FIX-R1 key production files are byte-identical
  between `66502f6` and the new frozen commit (`2b1ba19`); the only
  `02_source` change is the two scripts.
- **T014-F1 history:** the T014 freeze (frozen commit `818c012c`,
  branch `t014`) completed all gates except the offline-install
  check, STOPPED on T014-F1, and was merged to `main` as a STOP
  record (`70538cd`); its artifacts were INVALID and are replaced
  by the FIX-T014-F1 re-freeze, itself replaced by the
  FIX-T014-F1-docs re-freeze, itself replaced by the FIX-R1
  re-freeze, itself now replaced by this re-freeze. The T014 doc
  follow-ups (USER_GUIDE four modes, PROJECT_BOOK §11.1 widening +
  DOCX sync, oracle README parity qualification) remain in the
  tree unchanged.

## 8. Release checklist (§12.1, IMPLEMENTATION_PLAN)

- [x] Four spec files exist, non-empty, version consistent (v1.2.0).
- [x] `LICENSE` MIT and in source/dist.
- [x] Python runtime dependencies = 0.
- [x] `pytest` full suite passes (848).
- [x] Oracle independent tests pass (26/26).
- [x] S0 52/52, parity 52/52, false PASS 0, false block 0.
- [x] Repeat-100 single canonical hash (`a19054f1…d530`).
- [x] Offline check PASS (0 socket events).
- [x] GitHub Actions example runs in synthetic env (validator PASS).
- [x] UI smoke archived (3 reports; screenshots NOT_TESTED — no browser).
- [x] P0 = 0, P1 = 0 (P0-R1-01 FIXED by FIX-R1, verified by coordinator + this freeze; P2-28 FIXED by the validator redirect; no new P0/P1 in this re-freeze).
- [x] REVIEW_INDEX + REVIEW_PACK coverage complete (new FIXR1 calls PASS; old default still the same 34 old-anchor problems).
- [x] source.zip matches the frozen Git tree file-by-file.
- [x] **dist.zip installs and runs offline** — fresh venv +
      `--no-index` install, `--help` OK, capture → verify
      `BOUND_PASS` (§3/§6).
- [x] SHA256SUMS all OK.
- [x] RELEASE_MANIFEST commit, counts, bytes and SHAs match.
- [x] Git bundle clones and reproduces the source tree.
- [x] Untested platforms and unimplemented features marked as such
      (Windows/macOS NOT_TESTED; §5).
- [x] README quickstart reproducible from the dist (§6).

## 9. Git state

- Branch: `fix-r1`. Frozen (source) commit:
  `2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09`.
- FIX-R1 commit: `737e0b17a975f14f080bd4c27077e6bab215b273`
  (`02_source` differs from the frozen commit only in the two
  validator scripts).
- Previous frozen commit: `66502f6255976b44b3efebb7da778ea8807b1ba1`
  (FIX-R1 re-freeze; `02_source` differs from the new frozen commit
  only in the two validator scripts).
- Release commit (adds `05_release/*` + `03_evidence/fix-r1-validator-refreeze/`
  freeze logs): recorded in the branch log; the release commit's
  `02_source` tree is identical to the frozen commit's tree
  (`git diff 2b1ba19f <release> -- 02_source` empty).
- `git status --short` at release time: clean apart from the intended
  new files (listed in the release commit).
- **No merge, no GitHub upload.** The coordinator independently
  verifies and merges; GitHub upload is not authorized in this task.
  After merge, the remaining step is the Drive archive of the
  passed final-review report + completion notice (factory rule:
  Drive `agent project auto` first).
