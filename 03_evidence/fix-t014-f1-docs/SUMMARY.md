# FIX-T014-F1-docs — summary (branch `fix-t014-f1-docs`)

Fixes the stale references to the old `02_source/schemas/` path left by
FIX-T014-F1, then re-freezes release r1. Docstring/comment/link text
only — no behaviour change anywhere.

## Branch / commits

- Branch `fix-t014-f1-docs`, from `fix-t014-f1` at `2e28245`.
- Frozen (source) commit: `a07dc797c02b005356af2ee95212ed847c2fc656`
  ("FIX-T014-F1-docs: fix stale 02_source/schemas/ references left by
  the schema move") — 6 files, +14/−9.
- Release commit: adds `05_release/*` + this evidence dir + regenerated
  `03_evidence/s0/*`; `02_source` tree identical to the frozen commit
  (`git diff a07dc797 -- 02_source` empty).

## Per-file fixes (old → new)

1. `02_source/docs/USER_GUIDE.md:263` — `` `../schemas/policy.v1.json` ``
   → `` `../src/benchreceipt/schemas/policy.v1.json` ``; resolved path
   verified to exist.
2. `02_source/README.md:187` — tree listing `schemas/` →
   `src/benchreceipt/schemas/`; no other tree line references the old
   location.
3. `02_source/src/benchreceipt/schema.py` (`_schemas_dir` docstring) —
   Layout 1 recorded as the pre-move repo layout (removed by FIX-T014-F1;
   candidate kept only so an older checkout still resolves); Layout 2
   (package data next to the module) now fires in both editable and
   installed layouts. Code unchanged.
4. `02_source/src/benchreceipt/reports/junit.py` (lines 32, 53) and
   `lcov.py` (lines 41, 63) — `` `schemas/README.md` `` →
   `` `src/benchreceipt/schemas/README.md` ``. Comments only.
5. `02_source/src/benchreceipt/__init__.py:4` — `(schemas/canonical)` →
   `(src/benchreceipt/schemas/ — canonical schemas)`.

## Grep sweep (`grep-sweep.log`)

`git grep` for `02_source/schemas` / `../schemas/` over all tracked
files + a scoped `grep -rn` outside git. No remaining **live**
old-path references. Deliberately left (all documented in the log):
- `02_source/scripts/verify_review_pack.py:118` — anchored to the T013
  frozen candidate `cfede27`, where the old path is correct (untouched
  per task; the pack still PASSES).
- `04_review/`, `00_control/ADR/` — frozen historical records (untouched).
- `03_evidence/` logs — historical records of the FIX-T014-F1 investigation.
- `02_source/pyproject.toml:50,55` and
  `02_source/tests/packaging/test_wheel_contents.py:15-17` — comments
  describing the old location as history (both files forbidden to touch).
- The new `schema.py` docstring itself, which intentionally names the
  pre-move layout.

## Acceptance (all from `02_source`, `.venv` Python 3.12.3, `TMPDIR=~/workspace/p027-benchreceipt/.tmp`)

| Gate | Exit | Result |
|---|---|---|
| `../.venv/bin/python -m pytest -q` | 0 | **830 passed** in 34.44 s (`pytest.log`) |
| `../.venv/bin/python scripts/s0_gate.py` | 0 | **S0 PASS 10/10** — 16/16, 34/34, parity 50/50, repeat-100 1 hash, P95 0.0736 s, 77 receipts 0 violations (`s0-gate.log`) |
| `node --test oracle/verify.test.mjs` | 0 | **24/24 pass** (`oracle.log`) |
| `../.venv/bin/python scripts/privacy_scan.py` | 0 | 187 files, **0 findings** (`privacy-scan.log`) |
| `../.venv/bin/python scripts/verify_review_pack.py` | 0 | PASS, commit `cfede27…` (`verify-review-pack.log`) |
| `../.venv/bin/python scripts/verify_release.py` | 0 | **PASS fully, incl. offline-install check** — run twice, identical output (`verify-release.log`, `verify-release-2.log`) |
| extras: repeat-100 / parity / offline_check / validate_workflow_example / ui_smoke | 0 | 1 hash `a19054f1…d530`; 69 passed; PASS (0 socket events, BOUND_PASS); PASS; PASS, 3 reports, 0 external refs |

**P0 = 0, P1 = 0.** No new findings. No gate failed; freeze proceeded.

## Re-freeze (`05_release/`)

- `freeze_release.py --commit a07dc79 build --bundle-ref refs/heads/fix-t014-f1-docs`
  exit 0 — deterministic (two internal builds byte-identical).
  Note: the script docstring's `build --commit <sha>` order fails
  (exit 2, "unrecognized arguments: --commit"); `--commit` must
  precede the subcommand. Recorded in FREEZE_REPORT.md §4.
- Manifest run twice (`manifest-1.log`, `manifest-2.log` — identical);
  `sha256sum -c SHA256SUMS.txt` all OK.

| File | Bytes | SHA-256 |
|---|---|---|
| `source.zip` | 419233 | `2b06fcd38e6207f3c3bfa2058b68443e693b7c1b719e04b69dbdccd34f09caac` (345 files, 1,116,100 source bytes) |
| `dist.zip` | 152203 | `77b08aacfd2c93a14bce670608e03f6b3ca77116e9f344c72521ac327539f1df` (wheel 79,760 B / 27 entries incl. all 3 schemas; sdist 73,039 B) |
| `benchreceipt-a07dc797c02b.bundle` | 2934895 | `d9e7119be3eacdc195fe10d37b44f56e80da4621f4bc54c3fdaf1c8a48a67898` (ref `fix-t014-f1-docs`) |

Replaces the FIX-T014-F1 re-freeze (source.zip `6418c204…`, dist.zip
`a5e4fae1…`, bundle `50d16edc…` for frozen commit `52bad183…`); the old
bundle file was removed from `05_release/` (still in git history on
`fix-t014-f1` at `2e28245`).

## Notes for the coordinator

- No merge, no GitHub upload (not authorized).
- Pre-existing uncommitted S0 regen on `fix-t014-f1` (timestamps/p95
  only, 2026-11-18 02:48) was stashed, not lost:
  `git stash list` → "fix-t014-f1-docs: pre-existing uncommitted S0
  regen 2026-11-18 02:48 …". My own S0 re-run (02:52Z) regenerated
  `03_evidence/s0/*` fresh and is committed in the release commit.
- `05_release/FREEZE_REPORT.md` §3 quotes the verbatim validator PASS
  line; manifest was re-run after finalisation and is byte-identical.
