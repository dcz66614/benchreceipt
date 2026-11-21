# NEW P1 — T014-F1: the released wheel/sdist ships no `schemas/`, so an installed `benchreceipt` cannot capture/verify

- **Found:** 2026-11-18, T014 freeze gate (`scripts/verify_release.py`,
  offline-install check). **Status:** OPEN, freeze BLOCKED.
- **Severity:** P1 — broken documented interface (README quickstart +
  `pip install` path; IMPLEMENTATION_PLAN §12.1 "dist.zip 可离线安装和
  运行" fails). Not P0: it fails closed with an error, never a false
  `BOUND_PASS`.
- **Not previously known:** no mention in `04_review/REVIEW_FINDINGS.md`,
  `02_source/docs/LIMITATIONS.md`, `03_evidence/fix-r13b/SUMMARY.md` or
  the plan. The T013 review never smoke-tested an installed wheel
  (all acceptance ran the editable install, where Layout 1 applies).

## Symptom

Fresh venv, wheel installed from the frozen `05_release/dist.zip`
with `pip install --no-index`:

- bare `benchreceipt --help` works (exit 0, no schema load).
- `benchreceipt capture …` fails with exit 4:

```text
benchreceipt capture: error: assembled receipt fails benchreceipt.run/v1 validation:
schema validation failed: schema directory not found (looked in
['…/venv/lib/python3.12/schemas',
 '…/venv/lib/python3.12/site-packages/benchreceipt/schemas'])
```

`verify` and `report` load the same schemas (`schema.py: load_schema`)
and fail the same way. From the wheel, the CLI can only print `--help`.

## Root cause

`02_source/src/benchreceipt/schema.py::_schemas_dir()` documents two
layouts: Layout 1 (repo/editable install, `02_source/schemas/`) and
Layout 2 (packaged, `schemas/` shipped as package data next to the
module). But `02_source/pyproject.toml` has **no
`[tool.setuptools.package-data]` entry** (no `MANIFEST.in` either), so
`python -m build` produces a wheel containing only `benchreceipt/*.py`
+ dist-info — no `schemas/` anywhere. The sdist is affected the same
way (same `pyproject.toml`), so installing from the sdist builds an
identical broken wheel.

Wheel namelist (from `05_release/dist.zip`, frozen commit `818c012c`):
`benchreceipt/*.py` (17 files), `benchreceipt-0.1.0.dist-info/*`
(incl. `licenses/LICENSE`) — zero matches for `schemas`.

## Evidence

- `03_evidence/t014/verify-release.log` — `verify_release.py` FAIL,
  exit 1, single problem: offline-install capture round trip, exit 4,
  schema directory not found. Every other check passed (source.zip vs
  frozen tree, manifest + SHA256SUMS, LICENSE MIT, deps == 0, S0 block,
  bundle clone).
- `03_evidence/t014/wheel-repro.log` — standalone repro: fresh venv,
  `--no-index` wheel install OK, `--help` OK, capture exit 4 with the
  error above; wheel namelist has no `schemas`.
- `03_evidence/t014/quickstart-frozen.log` — the frozen source itself
  is FINE: fresh checkout of `818c012c`, editable install, README
  quickstart verbatim → capture 0, verify **BOUND_PASS** 0, report 0,
  bundle built (2 files) + verify ok. The defect is packaging-only.

## Suggested fix (for the coordinator / FIX task — NOT done in T014)

Add the schemas as package data, e.g. in `pyproject.toml`:

```toml
[tool.setuptools.package-data]
benchreceipt = ["schemas/*.json"]
```

(or move `schemas/` under `src/benchreceipt/` and ship it the same
way), then add a regression test: build the wheel from a scratch tree
and assert `benchreceipt/schemas/run.v1.json` is present and an
installed `benchreceipt capture` succeeds. A FIX task should also
re-run the full T014 freeze (the freeze scripts already exist and are
proven: deterministic build, `verify_release.py` catches exactly this
class of defect). Do NOT paper over it by injecting schemas into the
wheel post-build in `freeze_release.py` — the released wheel must be
reproducible from the frozen tree by a plain `python -m build`.

## Impact on T014

Per the task's STOP rule (any NEW P0/P1 → STOP, commit with a finding
note, do not proceed to freeze): the freeze is BLOCKED. The artifacts
in `05_release/` were built deterministically from the frozen commit
`818c012c…` and their hashes are correct, but the release is NOT valid
— `dist.zip` does not run — and `FREEZE_REPORT.md` is marked STOP
accordingly. No merge, no GitHub upload. All other gates passed
(pytest 827, Oracle 24/24, S0 PASS 10/10, repeat-100 1 hash,
verify_review_pack PASS, offline_check PASS, UI smoke PASS).
