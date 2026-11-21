# P027 BenchReceipt — FIX-R1 Independent Review: evidence summary

- **Anchor commit:** `66502f6255976b44b3efebb7da778ea8807b1ba1`
  (branch `fix-r1-review`; release commit `b221401`)
- **Spec version:** 1.2.0 (ADR-007)
- **Reviewer:** independent, review-only; did not write the fix code.
- **Verdict: PASS — 0 P0 / 0 P1** (9 new P2: P2-22–P2-30; see
  `04_review/REVIEW_FINDINGS_FIXR1.md`).
- **Coverage:** 34/34 key files read in full at `66502f6` (+ 3 Key=no
  files; 37/37 inventory rows). Inventory with per-file SHA-256:
  `inventory_table.md`, `REVIEW_COVERAGE_FIXR1.csv`.
- **Method:** read-only review. No production code, test, fixture,
  Golden, spec, or release file was modified. All runs used
  `TMPDIR=$PWD/.tmp/review-tmp` (persistent disk, never `/tmp`).
  S0 output went to `03_evidence/fix-r1-review/s0/` via `--out-dir`
  (the committed `03_evidence/s0/` was never touched).

## R1 blockers — closure evidence

### P0-R1-01 (legacy after-less receipts fail closed) — CLOSED

| Check | Result | Log |
|---|---|---|
| Fixture repro, my own script (`p0_fixture_repro.py`): e5/e6 × orig/legacy × Python CLI + Oracle | 8/8 cells: orig `UNBOUND`+`SOURCE_MUTATED_DURING_RUN`; legacy `UNBOUND`+`MISSING_FIELD`, jobs 0, exit 2, message `missing git.head_sha_after and git.tree_sha_after` | `p0-fixture-repro.run.log`, `p0-fixture-repro/` |
| Reviewer wheel repro, original R1 script, fresh venv from NEW `dist.zip` wheel | case 1 legacy `UNBOUND`+`MISSING_FIELD`, jobs 0; script's final assert fails **by design** (asserts old `BOUND_PASS`) | `wheel_repro_original_script.log` |
| Post-fix wheel repro (same probe, flipped asserts) | 2/2 cases fail-closed, exit 0 | `wheel_repro_postfix.log` |
| One-field spot check (only `tree_sha_after` deleted from e5) | both impls `UNBOUND`+`SOURCE_MUTATED_DURING_RUN` | (in-session; see findings) |
| Code identity | `verify.py:536–586` ≡ `oracle/verify.mjs:1444–1475`; message template byte-identical (`verify.py:560`, `verify.mjs:1463`, `REASON_CODES.md:70`) | packs 02/05 |
| Fixtures + Golden | e7 `e7-legacy-clean-checkout`, e8 `e8-legacy-empty-commit`: no after fields in receipts; Golden `UNBOUND`+`MISSING_FIELD`, jobs 0; 52 fixtures = 16 controls + 36 faults | (in-session) |

### P1-R1-01 (pack re-anchored) — CLOSED

This pack anchors `66502f6`. Inventory vs T013 anchor `cfede271`:
21 UNCHANGED, 14 CHANGED, 2 MOVED+CHANGED; all 3 schema files
verified at `02_source/src/benchreceipt/schemas/` (`policy.v1.json`
and `result.v1.json` byte-identical after the move).

## Freeze identity (independently computed)

| Artifact | Bytes | SHA-256 | Result |
|---|---|---|---|
| `05_release/source.zip` | 431,740 | `873b4dc43252202b17432c619397254a480e2dcfe10b43b7404d14b0efcd420b` | ✓ 355/355 files byte-identical to frozen tree |
| `05_release/dist.zip` | 152,883 | `da900faf679551ab6599c2ed333923bc151032957ceba2542ff065a51fc1bacd` | ✓ wheel 27 entries incl. 3 schemas, MIT, ≥3.12 |
| bundle (from `b221401`) | 3,844,063 | `86c4c82ed019803d349997c5708d62805b918c7b89675e181a20b5f4d00d0dc8` | ✓ |
| `SHA256SUMS.txt` (from `b221401`) | 409 | `d7568b5f1dc475ab79a488f83a672e58275a9058bf40771f3d4c41245f8de29a` | ✓ 5/5 entries |
| manifest (from `b221401`) | 3,177 | — | ✓ frozen_commit `66502f6…`, spec 1.2.0, gates match my re-runs |
| `.gitkeep` | 0 | `e3b0c44298fc…` | ✓ present (P2-R1-01 closed) |

Caveats recorded (P2-30): `source.zip`/`dist.zip` are gitignored and
not in `b221401` (only hashes tracked); on-disk tracked `05_release/`
files at `66502f6` are the old a07dc79 release — `verify_release.py`
was run on a scratch worktree at `b221401`. Full detail:
`freeze_identity.log`.

## Independent re-runs

| Check | Result | Log |
|---|---|---|
| Full pytest | 848 passed, 57.07 s | `pytest-full.log` |
| Oracle self-tests | 26/26 | `oracle.log` |
| S0 gate | PASS 10/10: 16/16, 36/36, 52/52, false 0/0, repeat-100 1 hash `a19054f1…d530`, P95 0.150 s (manifest 0.0789 s — both ≤1 s), golden `fb8e70a1…`, reason-codes `16feb3b8…` | `s0_gate.log`, `s0/` |
| Repeat-100 hash | 1 hash `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530` | `repeat-100.log` |
| Offline install (fresh venv, new wheel) + clean-tree capture/verify | `BOUND_PASS`, jobs 1 | `offline_install.log` |
| `offline_check.py` | PASS | `offline_check.log` |
| `privacy_scan.py` | 193 files, 0 findings | `privacy_scan.log` |
| `validate_workflow_example.py` | PASS | `validate_workflow.log` |
| `ui_smoke.py` | PASS (screenshots NOT_TESTED — no browser on this VM) | `ui_smoke.log` |
| `verify_release.py` (worktree `b221401`) | PASS | `verify_release_b221401.log` |
| Old-anchor validators (pre-delivery) | PASS, exit 0 | `verify-review-pack-old-anchor.log`, `check-review-coverage-old.log` |
| Post-delivery validator (old index) | FAIL as expected (12 pre-reformat / 34 post-reformat — all the old anchor itself) | `verify-review-pack-post-delivery.log`, `verify-review-pack-post-reformat.log` |
| Re-anchored validator simulation | **PASS** (43 index rows, 37 pack rows, 31 key files) | `validator_reanchored_simulation.log`, `validator_parse_check.log` |
| Spec sync | CONVERGED 4/4; manifest + SHA256SUMS 4/4 OK; SECRET_HINTS 1× each BOOK.md | `spec_sync.log`, `spec_docx_check.log` |

## Corrections to the handoff record (found while re-checking)

- e7/e8 fixture directory names are `e7-legacy-clean-checkout` and
  `e8-legacy-empty-commit` (not `e7-legacy-no-after-clean` /
  `e8-legacy-no-after-dirty`); n01 is `n01-single-pr-head` (not
  `n01-normal-2job-pr-head`). GOLDEN.json is `{"fixtures": {...},
  "note", "version"}` with 52 entries — not a flat dict.
- My first offline-roundtrip attempts failed on MY setup, not the
  product: (a) `pip install dist.zip` directly is not supported —
  the wheel inside must be installed (`INSTALL.txt` documents this);
  (b) my hand-written `policy.toml` used a `[policy]` table — the
  real format is top-level keys; (c) `capture` takes `--job`, not
  `--job-id`; (d) a dirty scratch repo correctly yields
  `SOURCE_MUTATED_DURING_RUN` under `require_clean_source_after`.
  The corrected roundtrip (clean tree, committed policy/junit,
  `.benchreceipt/` gitignored) passes `BOUND_PASS`. All four
  missteps are recorded here so they are not mistaken for findings.
- `03_evidence/fix-r1-review/` previously held an empty 0-byte
  `release-b221401/dist.zip` + `source.zip` from a failed
  `git show` (those files are not in `b221401` — gitignored); the
  files were removed and the verified on-disk `05_release/*.zip`
  used instead.

## Evidence files in this directory

`SUMMARY.md` (this file), `inventory_check.py`,
`inventory_check.log`, `inventory_table.md`, `spec_docx_check.log`,
`spec_sync.log`, `verify-review-pack-old-anchor.log`,
`check-review-coverage-old.log`, `freeze_identity.log`,
`p0_fixture_repro.py`, `p0-fixture-repro.run.log`,
`p0-fixture-repro/` (13 files), `wheel_repro_original_script.log`,
`wheel_repro_postfix.log`, `pytest-full.log`, `oracle.log`,
`repeat-100.log`, `s0_gate.log`, `s0/` (`S0_GATE.json`,
`S0_REPORT.md`, `performance.json`), `offline_check.log`,
`privacy_scan.log`, `validate_workflow.log`, `ui_smoke.log`,
`offline_install.log`, `verify_release_b221401.log`,
`verify-review-pack-post-delivery.log`,
`verify-review-pack-post-reformat.log`,
`check-review-coverage-post-delivery.log`,
`validator_parse_check.log`, `validator_reanchored_simulation.log`.
Scratch (not evidence): `.tmp/review-tmp/` (wheel venvs, worktree
removed after use, fixture copies).

## Deliverables

- `04_review/REVIEW_INDEX_FIXR1.md`
- `04_review/REVIEW_PACK_FIXR1_01.md` … `REVIEW_PACK_FIXR1_06.md`
- `04_review/REVIEW_FINDINGS_FIXR1.md`
- `04_review/REVIEW_COVERAGE_FIXR1.csv`
- This evidence directory.

T013 pack files were not touched. No production code, test, fixture,
Golden, spec, or release file was modified at any point.
