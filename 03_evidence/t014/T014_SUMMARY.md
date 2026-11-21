# P027 BenchReceipt — T014 worker summary (STOP: new P1 T014-F1)

- **Branch:** `t014` (from `main` at `9a2f928`).
- **Frozen (source) commit:** `818c012c60b668ecb5d0389015b75c092ea65b4f`
  (doc follow-ups + release tooling; production code, tests, fixtures,
  schemas, S0 thresholds byte-identical to `main` at `9a2f928` plus the
  three allowed doc edits — verified by `git diff`).
- **Outcome: STOP — freeze BLOCKED by new P1 T014-F1** (see
  `FINDING-T014-F1.md`). Per the task's STOP rule: committed with a
  finding note, no merge, no freeze.

## What passed

- pytest **827 passed** (final re-run against the frozen commit).
- Oracle `node --test` **24/24**; parity corpus **69 passed**.
- S0 gate **PASS 10/10** (16/16, 34/34, parity 50/50, false PASS/block
  0, repeat-100 1 hash `a19054f1…d530`, P95 0.0822 s).
- `verify_review_pack.py` PASS; `offline_check.py` PASS (0 socket
  events); workflow validator PASS; privacy scan 0 findings; UI smoke
  PASS (3 reports; screenshots NOT_TESTED, no browser).
- `verify_release.py` negative control in `/tmp`: corrupted manifest
  → FAIL exit 1 naming the mismatch.
- README quickstart from the **frozen source** (fresh checkout,
  editable install): **BOUND_PASS**.
- Deterministic freeze build proven (built twice, byte-identical
  source.zip/dist.zip/bundle; two nondeterminism bugs found and fixed
  in the script: sdist PAX mtimes, bundle `pack.threads=1`).

## What failed — T014-F1 (new P1)

The released wheel/sdist ships no `schemas/`: `pyproject.toml` has no
`[tool.setuptools.package-data]`, although `schema.py` documents a
packaged Layout 2. An offline-installed `benchreceipt` installs fine
and `--help` works, but `capture`/`verify`/`report` fail with exit 4
(`schema directory not found`). The frozen source is fine; only the
packaging is broken. Full analysis + suggested fix in
`FINDING-T014-F1.md`; repro in `wheel-repro.log`.

## Doc follow-ups (done)

- USER_GUIDE.md:239 — all four source modes + `--expected-sha`.
- PROJECT_BOOK.md §11.1 + DOCX — widened F-09 redaction list (one
  DOCX paragraph changed, verified by diff; `sync_docx_11_1.py`).
  No SPEC_VERSION bump. **Flag:** no SPEC_MANIFEST.json / spec
  SHA256SUMS.txt exists in the repo, so there was nothing to update
  there — coordinator follow-up if such a manifest is supposed to exist.
- oracle/README.md — parity claim qualified (50 S0 + 69-case corpus +
  reviewer repro corpus; known divergences listed).

## Release artifacts (`05_release/`)

Deterministically built from `818c012c…` but **NOT a valid release**
(dist broken): source.zip (344 files, 1,103,262 B,
`b77afa50…`), dist.zip (`4d76e784…`), bundle
`benchreceipt-818c012c60b6.bundle` (`236bf12c…`), SHA256SUMS.txt,
RELEASE_MANIFEST.json, FREEZE_REPORT.md (marked STOP). The manifest's
`frozen_commit` names the source-freeze commit (a manifest naming its
own commit is uncomputable — hash fixed point; explained in
FREEZE_REPORT.md §4); `verify_release.py` enforces the release
commit's `02_source` tree equals it.

## For the coordinator

1. Dispatch a FIX task for T014-F1 (suggested fix: package-data for
   `schemas/*.json` + a wheel-content regression test; do NOT inject
   schemas into the wheel post-build).
2. After the fix, re-run the T014 freeze with the existing scripts
   (`freeze_release.py build` + `manifest`, `verify_release.py`) —
   they are proven and they catch exactly this defect class.
3. Spec-manifest question (above) if a spec-file manifest is expected.
