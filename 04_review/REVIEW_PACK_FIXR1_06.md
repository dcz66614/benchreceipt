# REVIEW PACK FIXR1-06 — Scripts / CI / packaging (`02_source/`, scripts & config)

- **Anchor:** `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`)
- **Pack:** 06 of 06. Files read in full at the anchor commit.
- **Verdict:** no P0/P1 in this pack. Three P2 cross-refs: P2-28
  (review-pack validators), P2-29 (`ci.yml` comment), P2-30 (release
  zips uncommitted — recorded here as it concerns the release
  scripts' `.gitignore` treatment).

## Files

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/pyproject.toml` | `60bb4f4db82513c4103e48ed823e5d05a3014f700f7a015d795bcde651efc255` | 63 | packaging |
| `02_source/examples/github-actions/ci.yml` | `9c672a4cafe9be66aac0d6b8a6849f6b90e237d0d29cf73c59c2aee37ffec7cf` | 190 | CI example |
| `02_source/scripts/s0_gate.py` | `04dca6fa77e6bd684e650602ae3c6f83eb248664ae721b9c9eaadb93b878be25` | 375 | S0 gate |
| `02_source/scripts/repeat_hash.py` | `64281520c01f739a8e138804c9b9cf3aa218f7ae9b5ae31f06277aa858f94829` | 64 | repeat-hash check |
| `02_source/scripts/validate_workflow_example.py` | `8412a94c666e2edaa5fac597f3d8ff232d27a34967d7a3db73efa193fe9239bb` | 601 | workflow validator |
| `02_source/scripts/offline_check.py` | `3deb9b75d40088c45192c5150c98c725a6a98e27010deb7c1450c030ca45dfba` | 240 | offline check |
| `02_source/scripts/performance_smoke.py` | `9deb600338dfbc38edf1487c932e86ac4b078b0006a4c9a315801a1ce9b49b7c` | 165 | perf smoke |
| `02_source/scripts/privacy_scan.py` | `cdb5566b99a8cb95d7532b6bac8dde58cdffe0f3ab0b2b4a2d49eb42814d5363` | 267 | privacy scanner |
| `02_source/scripts/build_fixtures.py` | `f6a9ff891ce2730ec41e3b86aa41cd7e12794083f89957d56f725ede05195003` | 607 | fixture builder |
| `02_source/scripts/ui_smoke.py` | `298de709d1593b1e5c802bc4b7cdae2afe30efc35cd551284b6c3797ddef907d` | 120 | UI smoke |
| `02_source/scripts/verify_review_pack.py` | `eae974023d4d7b673b561f79fd04d7463604b6aec9076b89d7ab82830b29cff0` | 289 | pack validator |
| `02_source/scripts/check_review_coverage.py` | `7775da3902ddafed06129dc6f9970b896f457ccf294557efa607bef7cee2d168` | 194 | coverage checker |

## What I checked

- **`pyproject.toml` (63).** Packaging metadata: MIT license,
  `Requires-Python >= 3.12`, zero runtime dependencies, package data
  includes the moved `schemas/` (the wheel ships all three schema
  JSONs — verified by inspecting the built wheel). Version 0.1.0.
- **`examples/github-actions/ci.yml` (190, unchanged).**
  `validate_workflow_example.py` PASS (4 matrix jobs, policy
  agreement + token-free + local-install checks OK). **P2-29:** the
  comment at line 82 ("summary field is a spec decision for T013,
  not a capture change") points at T013 as if still open. Stale
  pointer; the workflow itself is sound. Carried: P2-13 (remote
  `.whl` URL accepted as "local install").
- **`s0_gate.py` (375).** 10 thresholds; `--out-dir` honored (my run
  wrote to `03_evidence/fix-r1-review/s0/` without touching the
  committed `03_evidence/s0/`). Carried: P2-14 (threshold 8 partly
  vacuous — `network_requests` hardcoded 0, gate never runs the
  socket audit).
- **`repeat_hash.py` (64), `performance_smoke.py` (165).**
  Determinism + P95 measurement. My repeat-100 run: 1 hash
  `a19054f1…d530`; my S0 P95 was 0.150 s vs the manifest's 0.0789 s
  — both ≤ 1 s, run-to-run variance, not a discrepancy.
- **`offline_check.py` (240), `privacy_scan.py` (267).** Static
  network-token scan + socket audit (PASS, 0 events); privacy scan
  193 files, 0 findings. Carried: P2-19 (scanner coverage gaps);
  see also P2-27 in Pack 01.
- **`build_fixtures.py` (607, +40 lines).** `make_receipt` defaults
  after = before (Scheme A); `omit_after=True` is the only
  no-after-field path and is used only by e7/e8. Fixture set rebuilt
  deterministically: 52 dirs, Golden 52 entries (16 controls, 36
  faults). Carried: P2-20 (no guard flag against rebuilding the
  frozen fixture set).
- **`ui_smoke.py` (120).** Renders 3 reports, 0 external refs; PASS
  (screenshots NOT_TESTED — no browser on this VM).
- **`verify_review_pack.py` (253) / `check_review_coverage.py`
  (125) — P2-28.** Both UNCHANGED since T013 and both still anchored
  to the old index: `_is_key_production` (lines 109–118) matches only
  `02_source/schemas/*.json`, missing the 3 schemas at
  `02_source/src/benchreceipt/schemas/`; the `REVIEW_PACK_*.md`
  glob (lines 197–199) and `check_review_coverage.py:71` validate
  against `04_review/REVIEW_INDEX.md` (anchor `cfede271`, old schema
  paths). Pre-delivery runs against the old pack: both PASS, exit 0
  (`verify-review-pack-old-anchor.log`,
  `check-review-coverage-old.log`). The post-delivery run against the
  old index fails as expected (12 problems: 6 "PACK NOT LISTED IN
  INDEX" + 6 "EMPTY PACK" — the latter because the first version of
  this pack's tables did not use the validator's `| Path | SHA-256 |
  Lines |` column order; all six packs and this index's inventory
  table have since been reformatted to that convention, and the index
  carries a `Frozen candidate commit:` line, so a re-anchored run can
  parse them — verified: a simulation of the validator re-anchored to
  `REVIEW_INDEX_FIXR1.md` / `66502f6` with the pack glob scoped to
  FIXR1 files, reusing the validator's own functions, **PASSES**: 43
  index rows, 37 pack rows, 31 key files, all SHA-256 + line counts
  match, all packs listed
  (`validator_reanchored_simulation.log`; the parse check is in
  `validator_parse_check.log`). A second post-delivery run after the
  reformat fails with 34 problems, every one of them the old anchor
  itself (SHA/line mismatches = the FIX-R1 delta, moved schemas
  "MISSING" at `cfede271`).

## Re-runs touching this pack

- Full pytest 848 passed; Oracle 26/26; S0 PASS 10/10; repeat-100 1
  hash; offline_check PASS; privacy_scan 0 findings;
  validate_workflow PASS; ui_smoke PASS; `verify_release.py` PASS on
  a scratch worktree at `b221401` (its offline-install step included);
  offline install from the new `dist.zip` wheel in a fresh venv +
  clean-tree capture/verify roundtrip `BOUND_PASS`.

## Findings in this pack

- P2-28 (`verify_review_pack.py:109–118`, `:197–199`;
  `check_review_coverage.py:71`), P2-29 (`ci.yml:82`), P2-30
  (release zips gitignored/uncommitted) — see
  `REVIEW_FINDINGS_FIXR1.md`.
- Carried: P2-13, P2-14, P2-19, P2-20.
