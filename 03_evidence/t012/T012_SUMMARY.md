# P027-T012 Summary — cross-platform / offline / performance / docs (RESUME)

- **Task:** P027-T012 (IMPLEMENTATION_PLAN §T012), resumed after the
  P1-01 stop. **Branch:** `t012-resume` (from main `061027c`).
- **Spec:** v1.1.0 (ADR-005). **Date:** 2026-11-18.
- **Status: T012 COMPLETE.** All §T012 work is done; no P0/P1 found
  in this round. P2-02/P2-03/P2-04 and the artifact-verbatim-secret
  observation are carried forward as documented limitations (see §4).

## 1. What was done

### 1.1 Merge of branch `t012` (first step)

`git merge t012` into `t012-resume`. Clean except the expected
conflict in the regenerated S0 evidence
(`03_evidence/s0/{S0_GATE.json,S0_REPORT.md,performance.json}` —
both branches had regenerated them with different timestamps/P95).
Resolved exactly as instructed: re-ran `python scripts/s0_gate.py`
fresh (PASS 10/10, P95 0.088s at merge time) and committed the
regenerated files. No S0 output was hand-edited. Merge commit
`27f6f23`. Everything from `t012` (README rewrite, USER_GUIDE,
`offline_check.py`, cross-platform tests 6/6, performance/offline
evidence, FINDING-P1-01 note) is now on this branch.

### 1.2 Docs switched from `python -m benchreceipt` to bare `benchreceipt` (P1-01 closure)

- `02_source/README.md`: install section now documents the
  `benchreceipt` console script (`[project.scripts]`, spec §6.4);
  all quickstart commands (capture / verify / report / bundle)
  use the bare form. The old "There is no `benchreceipt` console
  script; invoke it as a module" paragraph is gone.
- `02_source/docs/USER_GUIDE.md`: §1 install/check rewritten
  (bare `benchreceipt --help`, P1-01 recorded as CLOSED by
  FIX-P1-01 with its 7 regression tests, pointing at the finding
  note); §§3–6 commands in bare form; the §7 comment
  ("use `python -m benchreceipt ...` until the FIX task adds one",
  old line ~188) removed. No `python -m benchreceipt` invocation
  remains in either file (verified by grep; the only remaining
  P1-01 mentions are closure notes).
- Verified end-to-end: the README quickstart was re-run verbatim
  in **bare form** in a scratch repo (capture → verify
  `BOUND_PASS` → report → bundle build/verify OK). Log:
  `03_evidence/t012/quickstart-bare.log` (HEAD
  `578c820f7a74c98b9d808c5269030730a0ccb600`, `BOUND_PASS`,
  `jobs_verified=1`). The README quickstart intro now cites this
  log.
- Incident during the first bare-quickstart attempt (recorded
  honestly): the runner script used a relative `mkdir
  quickstart-demo` and ran its `git init`/`git add .`/`git commit`
  inside the **project repo root**, overwriting the repo
  `.gitignore` and landing one stray commit (`c2b3bd5`, "demo: add
  benchreceipt policy", `.benchreceipt.toml` only — the "demo: one
  green test" commit had already failed on `git add .`). Recovery:
  `git reset --mixed 27f6f23`, restored `.gitignore`, deleted the
  stray files (`.benchreceipt/`, `.benchreceipt.toml`,
  `test_demo.py`, `quickstart-demo/`), unset the local git identity
  the script had set. Verified afterwards: HEAD back at `27f6f23`,
  only the intended T012 changes in the tree. The corrected
  quickstart then ran in an absolute scratch path under `.tmp/`
  and passed; the first (bad) log was overwritten by the good run.
  Note the gate itself behaved correctly in the bad run: capture
  in the dirty parent repo produced a receipt whose verify was
  `UNBOUND / SOURCE_MUTATED_DURING_RUN` — fail-closed, as designed.

### 1.3 `02_source/docs/LIMITATIONS.md` written

Records, honestly and completely:

- P2-01 transient mutate-and-revert undetectable by any
  before/after scheme (PROJECT_BOOK §5.5 v1.1.0 substance).
- P2-02 no byte cap on `receipt.json` (2 MB whitespace-padded
  receipt parses, correct `BOUND_PASS`; hostile multi-MB receipt
  parsed in full).
- P2-03 `verify_bundle` does not enforce the documented manifest
  sort order (reordered lines alone still verify; tampering still
  detected).
- P2-04 bare CR inside an LCOV `SF:` path preserved verbatim
  (harmless: no LCOV summary field in the receipt, SF path never
  joined to the filesystem; pinned by
  `test_lone_cr_in_lcov_sf_path_is_preserved_not_stripped`).
- Artifact-verbatim-secret observation: a secret printed by a
  test into its own JUnit failure text / LCOV `SF:` path still
  exists in the artifact file; the receipt itself is clean.
- Honest boundaries: proves test-evidence binding to source
  identity, NOT test-logic correctness / assertion strength /
  absence of bugs; receipts are unsigned SHA-256 (not an
  authenticity claim against a malicious runner); does not replace
  SLSA / in-toto / Sigstore / GitHub Artifact Attestations.
- Windows/macOS: NOT_TESTED (no such host available) — never
  claimed as a pass; format-level boundary pinned by the
  cross-platform tests (POSIX paths, LF-only writers,
  CRLF-tolerant parsers).
- Also: no LCOV summary field (ADR-004, T013 spec decision), no
  real GitHub Actions run, closed policy schema, local-only
  (no network / token / server).

### 1.4 `02_source/docs/README.md` index updated

Lists USER_GUIDE, LIMITATIONS, BUNDLE_FORMAT, REASON_CODES with
one-line descriptions; status VERIFIED (T012 resume), pointing at
this summary. The old "placeholder / NOT_VERIFIED / arrives with
T012" text is gone.

### 1.5 Stale T009 "KNOWN LIMITATION" in `examples/github-actions/ci.yml` fixed

The header comment claimed `capture` writes no JUnit summary and
`verify` reports `MISSING_FIELD` / `UNBOUND` on real captures.
That gap was closed by ADR-004 (`fix-capture-junit`). The header
now states the closure (with the pinning tests) and records the
one remaining by-design gap (no LCOV summary field — a T013 spec
decision), matching `examples/github-actions/README.md` §5.
`validate_workflow_example.py` re-run after the edit: PASS.

### 1.6 Numbers refreshed to the resume run

- Full suite **683 passed** (670 T011 + 6 cross-platform +
  7 console-script) — README Status + Layout updated.
- Performance P95 **0.1041 s** / 100 manifests (limit 1 s) —
  README Status + USER_GUIDE §10 updated (first T012 run was
  0.1481 s; same limit, same host).

## 2. Acceptance results (all exit 0, exact commands)

Run from `02_source/` with `TMPDIR=$REPO/.tmp` and the project
`.venv` (except the Oracle, which uses `node --test`):

| Command | Result | Log |
|---|---|---|
| `../.venv/bin/python -m pytest -q` | **683 passed** in 21.84 s | `03_evidence/tests/pytest-t012-resume.log` |
| `../.venv/bin/python scripts/performance_smoke.py --jobs 100` | **PASS**, P95 **0.1041 s** (limit 1.0 s), 100 jobs × 100 reps, network_requests=0 | `03_evidence/performance/performance-t012-resume.log` + `.json` |
| `../.venv/bin/python scripts/offline_check.py` | **PASS** — static=CLEAN, socket_events=0, verify=BOUND_PASS | `03_evidence/t012/offline_check-resume.log` |
| `../.venv/bin/python scripts/s0_gate.py` (repo root) | **PASS 10/10** — 16/16 controls, 34/34 faults, false PASS 0, false block 0, parity 50/50, 1 hash over 100 replays (`a19054f1…`), P95 0.0743 s, 0 network requests, 77 receipts 0 violations | `03_evidence/tests/s0-gate-t012-resume.log`; `03_evidence/s0/{S0_GATE.json,S0_REPORT.md,performance.json}` regenerated |
| `node --test oracle/verify.test.mjs` | **8 pass, 0 fail** | `03_evidence/tests/oracle-t012-resume.log` |
| `../.venv/bin/python scripts/privacy_scan.py` | **184 files, 0 findings, 0 skipped** (re-run after the new docs were added) | `03_evidence/privacy/privacy_scan-t012-resume.log` |
| `../.venv/bin/python scripts/validate_workflow_example.py` | **PASS** — 4 matrix jobs, policy agreement + token-free + local-install checks OK | `03_evidence/t012/validate_workflow_example-resume.log` |
| Bare-form README quickstart round trip | **BOUND_PASS** end-to-end (capture → verify → report → bundle build/verify) | `03_evidence/t012/quickstart-bare.log` |

No P0/P1 found in this round. Full suite stayed green at the
merged total (683; the 677 main baseline + 6 cross-platform tests
from `t012`).

## 3. NOT_TESTED (deliberately left, not claimed)

- **Windows / macOS:** no such host available. The CI example
  still lists `windows-latest` cells in text only; they have not
  executed anywhere. Format-level boundaries (POSIX paths,
  LF-only writers, CRLF-tolerant parsers) are pinned by
  `tests/cross_platform/test_posix_boundaries.py` (6/6) for a
  future real run.
- **Real GitHub Actions:** the example workflow has not run on
  real GitHub Actions (no real repository exists for this
  project); validated only by synthetic/local checks.
- **Independent review (T013) and release freeze (T014):** not
  part of T012.

## 4. Open observations carried forward (P2, non-blocking)

- **P2-02** — no byte cap on `receipt.json` (hostile multi-MB
  receipt parsed in full; verdict still correct). Consider a byte
  cap if the threat model grows to untrusted receipts at scale.
- **P2-03** — `verify_bundle` does not enforce the documented
  manifest sort order. One-line strictness change if the format
  doc is to be treated as normative (T014 candidate).
- **P2-04** — bare CR in an LCOV `SF:` path preserved verbatim
  (harmless; see LIMITATIONS §5).
- **Artifact-verbatim-secret observation** — secrets in test
  output stay in the verbatim artifact copy; receipt stays clean.
  Mitigation is user behaviour (do not print secrets into test
  output), now documented in LIMITATIONS §6 and USER_GUIDE §3.

## 5. Files changed on `t012-resume` (this round, beyond the `t012` merge)

- `02_source/README.md` — bare `benchreceipt` throughout,
  console-script install note, 683 tests, P95 0.1041 s,
  quickstart-bare log reference.
- `02_source/docs/USER_GUIDE.md` — bare form throughout, P1-01
  caveats in §1/§7 closed, P95 0.1041 s.
- `02_source/docs/LIMITATIONS.md` — new (see §1.3).
- `02_source/docs/README.md` — index rewritten (was a
  placeholder).
- `02_source/examples/github-actions/ci.yml` — header comment
  corrected (ADR-004 closure; no code change).
- `03_evidence/s0/{S0_GATE.json,S0_REPORT.md,performance.json}`
  — regenerated by the S0 gate (merge resolution + final run).
- `03_evidence/t012/{T012_SUMMARY.md,quickstart-bare.log,offline_check-resume.log,validate_workflow_example-resume.log}`
  — new evidence for this round.
- `03_evidence/tests/{pytest-t012-resume.log,s0-gate-t012-resume.log,oracle-t012-resume.log}`
  — new acceptance logs.
- `03_evidence/performance/performance-t012-resume.{log,json}`
  — new performance evidence.
- `03_evidence/privacy/privacy_scan-t012-resume.log` — new
  privacy-scan evidence.

No production code, schema, S0 fixture/Golden, release file, or
`pyproject.toml` was touched.
