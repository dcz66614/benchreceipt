# P027-T012 FINDING P1-01 — No `benchreceipt` console script: spec §6.4 CLI contract unmet

- **Task:** P027-T012 (IMPLEMENTATION_PLAN §T012)
- **Status: STOPPED — P1 found. T012 did NOT complete and does NOT pass.**
  Per the task's stop-on-P0/P1 rule, work stops immediately on finding
  a P1. The remaining T012 items (LIMITATIONS.md, docs/README.md
  index, the stale T009 comment in `examples/github-actions/ci.yml`,
  the T012 summary report) were **NOT** produced. They are listed
  below as NOT DONE, not as passed. No production code was modified
  (docs + performance/offline scripts + cross-platform tests only).
- **Branch:** `t012`; **input commit:** `2dcddb5` (main).
- **Severity:** P1 — the documented primary CLI interface does not
  exist after install. Fail-closed (a real run goes red, never a
  false `BOUND_PASS`), so NOT P0.

## Claim

PROJECT_BOOK §6.4 documents the CLI contract as bare `benchreceipt`
commands (`benchreceipt capture …`, `benchreceipt verify …`,
`benchreceipt report …`). The installed package provides **no**
`benchreceipt` executable: `pyproject.toml` declares no
`[project.scripts]` entry point, there is no `entry_points.txt` in
the installed dist-info, and `.venv/bin/` contains no `benchreceipt`.
Only `python -m benchreceipt` works (via `src/benchreceipt/__main__.py`).

## Exact reproduction (executable)

```bash
cd /home/hatch/workspace/p027-benchreceipt
.venv/bin/python -m pip install -e 02_source   # exit 0
.venv/bin/benchreceipt --help
# /bin/bash: line 1: .venv/bin/benchreceipt: No such file or directory
ls .venv/bin/ | grep -i bench                   # (no output)
cat .venv/lib/python3.12/site-packages/benchreceipt-0.1.0.dist-info/entry_points.txt
# NO entry_points.txt
.venv/bin/python -m benchreceipt --help         # works (exit 0)
```

## Impact

Everything downstream of the §6.4 contract assumes the bare command
exists:

- `02_source/examples/github-actions/ci.yml` (T009) runs bare
  `benchreceipt capture` and `benchreceipt verify` steps. On a real
  GitHub Actions runner those steps fail with `command not found` —
  the flagship CI integration does not run as documented. (It has
  never been run on real Actions; the header says so.)
- `02_source/scripts/validate_workflow_example.py` *requires* the
  literal strings `benchreceipt capture` / `benchreceipt verify` in
  the workflow file, so the validator actively enforces the broken
  form.
- `02_source/examples/github-actions/README.md` shows bare commands
  throughout (e.g. §4 `benchreceipt verify …`).
- The T012 README quickstart and USER_GUIDE were written to use
  `python -m benchreceipt` (verified live), so the *docs* are
  correct — but they now contradict the spec contract and the CI
  example, and a user following §6.4 verbatim gets a broken install.

Why P1 and not P0: a missing executable fails loudly (exit 127 /
step failure). No receipt is written, no verdict is produced, and no
consumer can mistake it for a pass. It is a broken documented
interface, not a false PASS, not a leak, not an escape.

Why P1 and not P2: the primary interface in the frozen spec, the CI
example, and the validator all depend on it. Every new user following
the documented path hits it first.

## What was verified NOT broken by this finding

- `python -m benchreceipt` works end-to-end: the T012 quickstart
  (capture → verify `BOUND_PASS` → report → bundle build/verify) ran
  green with the module form (`03_evidence/t012/quickstart.log`).
- Full suite **676 passed** (670 baseline + 6 new cross-platform
  tests), S0 gate **PASS 10/10**, Oracle **8/8**, privacy scan
  **184 files / 0 findings** — all recorded before the stop.
- Performance P95 **0.1481 s** / 100 manifests (limit 1 s); offline
  check **PASS** (static scan clean, 0 socket events, `BOUND_PASS`).

## FIX recommendation (for a separate FIX task — NOT done here)

1. Add the entry point to `02_source/pyproject.toml`:
   `[project.scripts] benchreceipt = "benchreceipt.cli:main"`.
   (`cli.main` already returns an `int` exit code, which console
   scripts use as the process exit code; `__main__.py` keeps working
   unchanged.)
2. Regression test: after an editable install, assert a `benchreceipt`
   executable exists on `PATH` and `benchreceipt --help` exits 0
   (and/or invoke the installed script for one capture→verify round
   trip). The existing suite never exercises the installed script —
   that is why this shipped.
3. Re-run `scripts/validate_workflow_example.py` and the T009
   integration tests unchanged (they already require the bare form).
4. Re-run the T012 quickstart with the bare form once the entry point
   lands, and update the T012 README/USER_GUIDE to use it.

## T012 work completed before the stop (committed on `t012`)

- `02_source/README.md` — rewritten, quickstart verified live
  (`BOUND_PASS`, `03_evidence/t012/quickstart.log`).
- `02_source/docs/USER_GUIDE.md` — install / capture / verify /
  report / bundle / CI example / policy reference / troubleshooting
  (with a P1-01 caveat in §1 and §7).
- `02_source/scripts/offline_check.py` — static scan + audit-hook
  dynamic trace; **PASS** (0 socket events, `BOUND_PASS`).
- `02_source/tests/cross_platform/test_posix_boundaries.py` — 6 tests
  (CRLF JUnit/LCOV parsing, LF-only writers, backslash-filename
  rejection); **6/6 pass**.
- Evidence: `03_evidence/t012/` (quickstart, offline, OS/toolchain
  logs), `03_evidence/performance/performance-t012.*`,
  `03_evidence/tests/pytest-t012.log` (676 passed),
  `s0-gate-t012.log` (PASS 10/10), `oracle-t012.log` (8/8),
  `03_evidence/privacy/privacy_scan-t012.log` (184 files, 0 findings).

## Observations recorded alongside (P2, not stop causes)

- **P2-04 (new, T012):** a bare CR inside an LCOV `SF:` path is
  preserved verbatim in the parsed summary (`source_file`) rather
  than rejected (`_validate_sf_path` rejects backslash / absolute /
  `..` but not control characters). Harmless in practice: no LCOV
  summary field is stored in the receipt (T011 probe (d)), and the
  SF path is never joined to the filesystem — only counts feed the
  verdict. Pinned by
  `test_lone_cr_in_lcov_sf_path_is_preserved_not_stripped`. Belongs
  in LIMITATIONS when T012 resumes.
- P2-01 / P2-02 / P2-03 and the artifact-verbatim-secret observation
  (SECURITY_FINDINGS.md) are still unrecorded in LIMITATIONS.md —
  that file was not written before the stop.

## NOT DONE (blocked by the stop)

- `02_source/docs/LIMITATIONS.md` (P2-01, P2-02, P2-03, P2-04,
  artifact-secret observation, honest boundaries, NOT_TESTED
  platforms).
- `02_source/docs/README.md` index update.
- Stale T009 "KNOWN LIMITATION" comment in
  `examples/github-actions/ci.yml` header (the capture-junit gap was
  closed by ADR-004; `examples/github-actions/README.md` §5 already
  says so, the `.yml` header still says otherwise).
- T012 summary report.
