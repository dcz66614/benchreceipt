# FIX-T014-F1 summary — wheel ships no schemas/ (P1, fail-closed)

Branch `fix-t014-f1` from `main` at `0a73d05`. T014-F1 is CLOSED by
this fix (pending coordinator verification + merge): the re-freeze
below was validated by `scripts/verify_release.py` PASS including
the offline-install round trip.

## 1. What the task specified vs what actually works

The task (and the finding's suggested fix) said to add exactly:

```toml
[tool.setuptools.package-data]
benchreceipt = ["schemas/*.json"]
```

and told the worker to verify the stanza against the actual layout.
Verification (scratch builds with the pinned toolchain
setuptools 80.9.0, `python -m build --no-isolation`, logs in this
directory, namelist summary in `wheel-namelists.txt`) proved the
literal stanza **cannot** work while the schemas live at
`02_source/schemas/`, outside the package:

| Scratch experiment | Wheel `schemas/` members |
|---|---|
| literal `["schemas/*.json"]`, schemas at `02_source/schemas/` (`wheel-build-literal-stanza.log`) | **none** — setuptools resolves package-data globs relative to the package dir `src/benchreceipt/` and silently drops non-matching globs (no warning) |
| `["../schemas/*.json"]` (`wheel-build-dotdot-stanza.log`) | **none** — `..` from the package dir is `src/`, which has no `schemas/` |
| `["../../schemas/*.json"]` (`wheel-build-dotdotdot-stanza.log`) | **none in the wheel** — the files DO enter the sdist (`benchreceipt-0.1.0/schemas/*.json`) and ARE copied by `build_py` to `build/lib/benchreceipt/../../schemas`, i.e. `build/lib/schemas/`, outside any package dir, where `install_lib` never picks them up for the wheel |

Conclusion: no glob can place outside-package files at
`benchreceipt/schemas/` in the wheel. Setuptools only ships
package-data files that physically live inside the package
directory. The fix therefore has two parts, both required:

1. **`git mv 02_source/schemas/ 02_source/src/benchreceipt/schemas/`**
   — byte-identical move (all four SHA-256 unchanged, verified
   before/after: `run.v1.json a8c95b12…`, `policy.v1.json
   2e555dc3…`, `result.v1.json 2f16a102…`, `README.md 401edf54…` —
   the same values recorded in `04_review/REVIEW_INDEX.md`).
   Frozen schema contents unchanged; no spec change.
2. **The literal stanza** in `02_source/pyproject.toml`
   (`[tool.setuptools.package-data] benchreceipt =
   ["schemas/*.json"]`, with a comment recording why the move was
   necessary).

`schema.py` is untouched: in the repo/editable layout Layout 1
(`02_source/schemas/`) no longer exists, so `_schemas_dir()` falls
through to the already-documented Layout 2
(`src/benchreceipt/schemas/`); in the installed wheel Layout 2
(`site-packages/benchreceipt/schemas/`) is the one that fires. No
production code, no schema content, no search logic changed.

This move is the alternative the finding note itself sanctions
("(or move `schemas/` under `src/benchreceipt/` and ship it the
same way)"). The coordinator should confirm the move is acceptable
at merge; the alternative (a custom build hook / backend switch)
was rejected as a larger deviation.

### Known follow-ups left for the coordinator (not fixed here — out of scope)

- Stale path references to the old `02_source/schemas/` location
  (docs/comments only, no behaviour): `02_source/README.md:187`
  (tree listing), `02_source/docs/USER_GUIDE.md:263`
  (`../schemas/policy.v1.json` link — now broken),
  `src/benchreceipt/reports/junit.py` / `lcov.py` comments
  (`schemas/README.md`), and the `schema.py::_schemas_dir()`
  docstring (Layout 1 is now historical). One-line doc follow-up.
- The wheel ships only `*.json` (per the specified stanza);
  `schemas/README.md` is not in the wheel/sdist. It is
  documentation, not loaded by the product; the full tree (incl.
  the README) is in `source.zip`.

## 2. Regression test

`02_source/tests/packaging/test_wheel_contents.py` (3 tests, ~5 s):

- `test_wheel_contains_every_loaded_schema` — builds a real wheel
  (`python -m build --no-isolation`, pinned offline toolchain
  from `.tmp/t014-freeze/piptest/`), enumerates
  `src/benchreceipt/schemas/*.json` (never hardcoded) and asserts
  each is present at `benchreceipt/schemas/<name>` byte-identical,
  and that every file `schema.py::SCHEMA_FILES` loads is among them.
- `test_wheel_without_package_data_contains_no_schemas` —
  negative control: the same tree built with the stanza stripped
  must contain no schemas.
- `test_schemas_dir_resolves_in_packaged_layout` — unpacks the
  fixed wheel somewhere with no `schemas/` next to it (Layout 1
  cannot fire) and asserts, in a subprocess importing
  `benchreceipt` from the unpacked wheel only, that
  `_schemas_dir()` == `<unpacked>/benchreceipt/schemas` and
  `load_schema` works for run/policy/result.

**Proof the tests catch the defect** (`wheel-test-prefix-proof.log`):
with the stanza temporarily reverted (`git stash push --
02_source/pyproject.toml`, schemas still inside the package), the
positive test FAILED with `fixed wheel is missing packaged
schemas: [all three]` and the packaged-layout test FAILED with the
exact T014-F1 error (`schema directory not found`, exit 4 class),
while the negative control PASSED. Stanza restored afterwards.
(The first proof attempt errored in the fixture because the
stanza-strip helper asserted the stanza exists; fixed to tolerate
an already stanza-less tree, then the proof above was re-run.)

**Offline-install smoke** (`wheel-smoke-install.log`,
`wheel-smoke-roundtrip.log`): fresh venv, `--no-index --no-deps`
install of the fixed wheel, `_schemas_dir()` resolves to
`site-packages/benchreceipt/schemas`, `load_schema("run")` loads,
and the `verify_release.py`-style capture → verify round trip
returns **BOUND_PASS** (exit 0).

## 3. Gates (all re-run fresh on this branch; logs in this directory)

| Gate | Command (from `02_source`, project `.venv`, `TMPDIR=…/.tmp`) | Result |
|---|---|---|
| New wheel test (standalone) | `pytest tests/packaging/test_wheel_contents.py -v` | **3 passed** (`wheel-test-standalone.log`) |
| Full suite | `python -m pytest -q` | **830 passed** (827 baseline + 3 new; `pytest.log`) |
| S0 gate | `python scripts/s0_gate.py` | **S0 PASS 10/10**; repeat-100 hash `a19054f1…d530` unchanged; P95 0.0782 s (`s0-gate.log`; regenerated `03_evidence/s0/*` committed — only timestamps + perf timings changed) |
| Oracle | `node --test oracle/verify.test.mjs` | **24/24** (`oracle.log`) |
| Privacy scan | `python scripts/privacy_scan.py` | **184 files, 0 findings** (`privacy-scan.log`) |
| Workflow example | `python scripts/validate_workflow_example.py` | **PASS** (`validate-workflow.log`) |
| Review pack | `python scripts/verify_review_pack.py` | **PASS** — commit `cfede27…`, 45 index rows, 37 pack rows, 34 key files (`verify-review-pack.log`; anchored to the frozen candidate commit, unaffected by the move) |
| Release validator | `python scripts/verify_release.py` | **PASS** incl. offline-install BOUND_PASS — see §4 (`verify-release.log`) |

No new P0/P1 found. No gate failed.

## 4. Re-freeze (this branch)

Re-ran `02_source/scripts/freeze_release.py` from the fix commit
(see `05_release/FREEZE_REPORT.md` §4 for the procedure; the
manifest names the source-freeze commit, not the release commit —
a manifest naming its own commit is uncomputable). The old INVALID
T014 artifacts were replaced. New hashes / counts are in
`05_release/RELEASE_MANIFEST.json` and `FREEZE_REPORT.md`; the
validator log is `03_evidence/fix-t014-f1/verify-release.log`.
`freeze-build.log` is in `03_evidence/fix-t014-f1/`.
