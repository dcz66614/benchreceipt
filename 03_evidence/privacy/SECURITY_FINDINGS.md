# P027-T011 Security Findings — Adversarial / Privacy / Security Regression

- **Task:** P027-T011 (IMPLEMENTATION_PLAN §5 T011, 5h)
- **Spec:** v1.0.0; **input commit:** `702910f` (main)
- **Status: STOPPED — P0 found. T011 did NOT complete and does NOT pass.**
  Per the task's FAILURE_AND_ROLLBACK rule, on finding a P0 the remaining
  T011 work stops immediately: the full adversarial battery (probes (a)–(d),
  (f)–(j)), `scripts/privacy_scan.py`, its tests, and `privacy_scan.log`
  were **NOT** produced. They are listed below as NOT RUN, not as passed.
- **Branch:** `t011`; **no production code was modified** (tests + evidence only).
- **Severity scale:** IMPLEMENTATION_PLAN §6.3 — P0 = false PASS, cross
  commit/run/attempt mix undetected, report hash wrong yet passing, command
  injection, path escape, secret leak.

## Counts

| Severity | Count |
|---|---:|
| P0 | **1** (P0-01, two variants, one root cause) |
| P1 | 0 |
| P2 | 1 observation (P2-01, residual limitation, not a defect in the §5.5 design) |
| Not run (blocked by the P0 stop) | probes (a)–(d), (f)–(j), privacy scanner |

## P0-01 — Mid-run HEAD/tree change is invisible to the verifier: false BOUND_PASS

**Severity: P0 (false PASS; undetected cross-commit mix).**

### Claim

A wrapped command that changes `HEAD` mid-run — `git checkout <other-commit>`
(clean tree, different HEAD *and* tree) or `git commit --allow-empty`
(HEAD changes, tree identical) — produces a receipt that claims the tests ran
against the *before* commit, while the tests actually ran against the *after*
commit. `verify.evaluate` returns **`BOUND_PASS`, `jobs_verified: 1`, zero
reason codes**. The gate that is supposed to catch this
(`SOURCE_MUTATED_DURING_RUN`, PROJECT_BOOK §5.5) never fires.

### Exact reproduction (executable)

`02_source/tests/adversarial/test_source_mutation_evasion.py` — run with:

```bash
cd /home/hatch/workspace/p027-benchreceipt
TMPDIR=/home/hatch/workspace/p027-benchreceipt/.tmp \
  .venv/bin/python -m pytest -q 02_source/tests/adversarial
```

Result at input commit `702910f`: **2 failed, 1 passed** — the two failures
*are* the finding (fail-first reproduction); the passing test is the control.

- `test_head_change_mid_run_is_detected` — FAIL: verify returns
  `BOUND_PASS` (expected `SOURCE_MUTATED_DURING_RUN`, `jobs_verified == 0`).
- `test_empty_commit_mid_run_is_detected` — FAIL: same `BOUND_PASS`.
- `test_dirty_to_clean_flip_is_detected` — PASS (control: dirty→clean flip
  *is* caught, proving the harness works and the defect is specific to
  clean-tree HEAD/tree changes).

Manual probe (same steps, scratch script in ignored `.tmp/`, not committed):

1. Synthetic repo, commit 1 (`code.py`: `VALUE = 1`, sha
   `e74d0451d3c72ec3ffcc494143035c982c6ac66a`), commit 2 (`VALUE = 2`, sha
   `8ec9228ae24bccea44574daf504a50c92b7ed28c`), checkout commit 1.
2. `capture(job_id="unit-linux-py312", matrix={"os": "ubuntu-latest",
   "python": "3.12"}, argv=[sys.executable, "-c",
   "import subprocess; subprocess.run(['git','checkout','-q','<sha2>'],
   check=True); open('junit.xml','w').write(<2-test green JUnit>)]",
   repo_path=<repo>, junit_path="junit.xml", cwd=<repo>)`.
3. `capture` returns `source_mutated_during_run=True` with
   `mutation_details=('head_sha changed: e74d… -> 8ec9…',
   'tree_sha changed: 90f1… -> ee07…')` — **capture itself detects it**.
4. The written receipt nevertheless contains:
   `git.head_sha = e74d…` (commit 1), `git.tree_sha = 90f1…` (commit 1's
   tree), `dirty_before = false`, `dirty_after = false`,
   `source_state_before.tracked_diff_sha256 ==
   source_state_after.tracked_diff_sha256 ==
   e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
   (the SHA-256 of the empty string — empty porcelain output before and
   after), and `HEAD` at verify time is `8ec9…` (commit 2).
5. `evaluate(policy, <sha1>, <evidence>)` with a policy matching the local
   capture (`source_mode="event_sha"`, `expected_workflow="local"`,
   `required_jobs=["unit-linux-py312"]`, junit required) returns:

```json
{"status": "BOUND_PASS", "jobs_verified": 1, "reason_codes": [],
 "identity_mismatches": [], "report_errors": [], "missing_jobs": [],
 "unexpected_jobs": [], "duplicate_jobs": []}
```

### Root cause

- `verify.py` (`_evaluate_inner`, §5.5 mutation check) detects mutation
  **only** from (i) `source_state_before/after.tracked_diff_sha256`
  inequality, (ii) `git.dirty_before != git.dirty_after`, or (iii)
  `require_clean_source_after and dirty_after`. All three are blind to a
  clean-tree HEAD change: `summarize_source_state`
  (`git_identity.py`) digests *only* `git status --porcelain=v1` lines,
  which are empty before and after a clean checkout, so the digests are
  identical and both dirty flags are `False`.
- The receipt has nowhere to carry the after-identity: the frozen
  `benchreceipt.run/v1` schema (`02_source/schemas/run.v1.json`,
  `additionalProperties: false`) has no `head_sha_after` /
  `tree_sha_after` / mutation-flag field, and `capture.py` does not
  persist `CaptureResult.source_mutated_during_run` / `mutation_details`
  into the receipt — they exist only in memory and in a capture-time
  stderr warning. The verifier only ever reads the receipt, so it cannot
  see what capture saw.
- `capture.py`'s module docstring (step 4) claims mutation "is recorded
  *as data*: `git.dirty_before/dirty_after` plus
  `source_state_before/after` differ" — that claim is **false** for this
  case: none of those fields differ. The docstring's fail-closed story
  holds only for mutations that leave the worktree dirty or change the
  porcelain output.
- Why S0 missed it: fixtures e1–e4 cover clean→dirty, one-job mutated,
  started-dirty, and digest-changed-flags-clean. No S0 fixture plants a
  HEAD/tree change with a clean tree on both sides.

### Impact

- A job whose tests ran against commit B is certified as evidence for
  commit A. Any consumer of `BOUND_PASS` (merge gate, release freeze)
  is misled about which code was tested. This is exactly the failure
  mode BenchReceipt exists to prevent (PROJECT_BOOK §0.1/§1.2, scenario D).
- The capture-time warning (`source_mutated=true` on stdout, warning on
  stderr) is visible only to whoever watches that capture run; the
  receipt — the portable artefact that `verify`/`report` consume,
  possibly on another machine/job — carries no trace. The trust boundary
  (verify) is blind.
- Note the failure is *silent*: no error, no warning in the verification
  result; exit code 0.

### FIX recommendation (for a separate FIX task — NOT done here)

This needs a spec decision, because the receipt schema is frozen:

1. Preferred: add `git.head_sha_after` / `git.tree_sha_after` (or a
   `source_mutated_during_run` boolean) to `benchreceipt.run/v1` via ADR
   + SPEC_VERSION bump + schema change (same route as ADR-004's LCOV-gap
   note); `capture` populates them from `git_after`; `verify` flags
   `SOURCE_MUTATED_DURING_RUN` when after != before. The regression
   tests in this task then become the pass criteria.
2. Alternative without a schema change: `capture` refuses to write a
   receipt when `source_mutated_during_run` is true (fail-closed at
   capture time). This changes the CLI contract (currently a non-zero
   exit / mutated run still writes a failure receipt) and loses the
   evidence of *what* ran — weaker, and it does not help hand-written
   or third-party receipts. Only adopt if the spec owners reject (1).
3. In either case: add S0-style fixtures for clean-tree HEAD change and
   empty-commit mid-run (e5/e6), re-run the S0 gate + full suite, and
   re-check the Oracle parity for the new reason-code path.

### What was verified NOT broken by this finding

- Full suite at this commit: **496 passed, 2 failed** — the only failures
  are the two P0-01 reproduction tests (`03_evidence/tests/pytest-t011.log`).
- S0 gate re-run: **PASS (10/10 thresholds)**,
  `03_evidence/tests/s0-gate-t011.log` (repeat hash
  `a19054f1…` unchanged). S0 passing while P0-01 exists is itself
  evidence that S0's mutation fixtures do not cover this case.
- Oracle: **8/8 passed** (`03_evidence/tests/oracle-t011.log`).

## P2-01 — Transient mutate-and-revert inside one run is undetectable by design (observation)

A command that modifies a tracked file and reverts it *within* the run
(dirty in the middle, clean before and after) leaves identical
before/after snapshots, so no before/after scheme — including the §5.5
design — can detect it. This is a residual limitation of snapshot-based
mutation detection, not a defect in the implemented code, and no test
was written asserting it (it cannot be fixed without continuous
monitoring, which is out of scope). Recorded here so the FIX task and
T013 do not mistake it for P0-01. **Severity: P2** (non-blocking
limitation; document in LIMITATIONS in T012).

## Probes NOT RUN (stopped per FAILURE_AND_ROLLBACK on P0-01)

The following T011 probes were **not executed and are not claimed
either way**. Code was read for orientation only; no pass/fail verdict
is recorded for them. They belong to the FIX-task regression round
(after P0-01 is fixed) or to a resumed T011.

| Probe (task list) | Status |
|---|---|
| (a) Path traversal / absolute / Windows paths / symlink escape (bundle verify + verify.evaluate) | NOT RUN |
| (b) Oversized receipt JSON, reports array > 32, job_id > 128 chars, matrix > 32, receipt-level oversize | NOT RUN |
| (c) DTD/XXE variants (parameter entities, external DTD, billion-laughs) with sentinel file | NOT RUN |
| (d) Secret redaction (argv `--token`/`--api-key`/`password=`, CI event JSON env values, JUnit failure text, LCOV paths) | NOT RUN |
| (f) Hash forgery variants (size matches/hash differs; hash matches/size differs) | NOT RUN |
| (g) Schema confusion (extra top-level receipt field, unknown policy field, wrong status enum) | NOT RUN |
| (h) Command injection via capture (`;`, `$(...)`, backticks, `&&`, sentinel file) | NOT RUN |
| (i) Duplicate/confused job identity (same job_id different content; case variants) | NOT RUN |
| (j) Tampered bundle manifest (sort order, CRLF, duplicate lines) | NOT RUN |
| `02_source/scripts/privacy_scan.py` + `02_source/tests/privacy/` + `03_evidence/privacy/privacy_scan.log` | NOT BUILT / NOT RUN |

## Evidence files (this commit)

- `02_source/tests/adversarial/test_source_mutation_evasion.py` — executable
  P0-01 reproduction (2 fail-first tests + 1 passing control).
- `03_evidence/tests/pytest-t011.log` — full suite: 496 passed, 2 failed
  (only the P0-01 reproductions).
- `03_evidence/tests/s0-gate-t011.log` — S0 gate re-run: PASS 10/10.
- `03_evidence/tests/oracle-t011.log` — Oracle: 8/8 passed.
- This file: `03_evidence/privacy/SECURITY_FINDINGS.md`.

---

# T011 RESUMED — remaining probes (a)–(d), (f)–(j) + privacy scanner

- **Task:** P027-T011 resumed (FIX-P0-01 merged; this round is a NEW session
  from the FIX builder).
- **Spec:** v1.1.0 (ADR-005); **input commit:** `63f04cc` (main, FIX-P0-01
  merged); **branch:** `t011-resume`; **no production code was modified**
  (adversarial/privacy tests + `scripts/privacy_scan.py` + evidence only).
- **Status: T011 COMPLETE — PASS.** All probes (a)–(d), (f)–(j) were run;
  none was skipped. **No new P0 or P1 was found.** The 3 P0-01 regression
  tests still pass unchanged. Two new P2 observations (robustness /
  format-strictness notes, not defects in the §5 design) are recorded
  below as P2-02 and P2-03; P2-01 (transient mutate-and-revert) is
  carried over unchanged.
- **Severity scale:** IMPLEMENTATION_PLAN §6.3 — P0 = false PASS, cross
  commit/run/attempt mix undetected, report hash wrong yet passing,
  command injection, path escape, secret leak.

## Counts (this round)

| Severity | Count |
|---|---:|
| P0 (new) | **0** |
| P1 (new) | **0** |
| P2 (new observations) | **2** (P2-02, P2-03; non-blocking) |
| P0-01 regression tests | 3/3 still passing |
| New tests added | **165** (168 in `tests/adversarial` + `tests/privacy`
  including the 3 pre-existing P0-01 tests) |
| Full suite | **670 passed, 0 failed** (baseline 505 + 165 new) |
| S0 gate | **PASS 10/10** (50 fixtures; repeat hash `a19054f1…` unchanged) |
| Oracle | **8/8 passed** |

## Acceptance commands (all run, all exit 0)

```bash
cd 02_source
TMPDIR=/home/hatch/workspace/p027-benchreceipt/.tmp ../.venv/bin/python -m pytest -q tests/adversarial tests/privacy
# 168 passed
TMPDIR=/home/hatch/workspace/p027-benchreceipt/.tmp ../.venv/bin/python scripts/privacy_scan.py
# privacy_scan: 184 file(s) scanned, 0 finding(s), 0 skipped
TMPDIR=/home/hatch/workspace/p027-benchreceipt/.tmp ../.venv/bin/python -m pytest -q
# 670 passed
TMPDIR=/home/hatch/workspace/p027-benchreceipt/.tmp ../.venv/bin/python scripts/s0_gate.py
# S0 gate: PASS (10/10 thresholds)
node --test oracle/verify.test.mjs
# 8 pass, 0 fail
```

## Per-probe verdicts

| Probe | Verdict | Tests | Evidence / notes |
|---|---|---|---|
| (a) Path traversal / absolute / Windows paths / symlink escape (bundle verify + verify.evaluate) | **PASS** | 27 in `tests/adversarial/test_path_traversal.py` | Hostile `reports[].path` values (`../`, absolute, backslash, `C:` drive, `//`, trailing `/`) are `INVALID_RECEIPT` at schema load; a symlink to an outside file is `REPORT_HASH_MISMATCH` on containment even when the outside file's bytes — and even the receipt's recorded digest — match exactly; `build_bundle` refuses symlinks (`BundleError`); `verify_bundle` reports `BUNDLE_UNSUPPORTED_SYMLINK` / `BUNDLE_PATH_ESCAPE` for planted symlinks and escaping manifest entries. |
| (b) Oversized inputs | **PASS** (+ P2-02 observation) | 13 in `tests/adversarial/test_oversized_inputs.py` | reports array 33, job_id 129 chars, matrix 33 entries, matrix key 65 chars, report `size_bytes` 1 GiB+1, `command.display` 513 chars are all `INVALID_RECEIPT`; capture rejects oversized job_id/matrix with `CaptureError` before any repo access; sparse 1 GiB+1 JUnit/LCOV files are rejected by `stat` without being read; a ~1 MB / 30,000-testcase JUnit still verifies `BOUND_PASS`; 64 extra job dirs yield `MATRIX_UNEXPECTED_JOB` (required job still verifies). |
| (c) DTD/XXE variants | **PASS** | 10 in `tests/adversarial/test_xxe.py` | External DTD, parameter entities, billion-laughs, external general entity, internal DTD, and lowercase `<!doctype` are all rejected by `parse_junit` (`JUnitError`); end-to-end capture omits the JUnit summary and verify returns `INVALID` (`JUNIT_MALFORMED` + `MISSING_FIELD`), never `BOUND_PASS`. The sentinel file stayed byte-identical and its content appeared in no error, receipt, or verdict. |
| (d) Secret redaction | **PASS** | 23 in `tests/adversarial/test_secret_redaction.py` | argv `--token` / `--api-key` (both `=` and following-value forms), `password=…`, `--TOKEN`, `--api_key`, `--apikey`, bare secret-bearing tokens are all `[REDACTED]` in `command.display` and absent from `receipt.json`; secrets in the CI event JSON payload never reach the receipt (only allowlisted fields are persisted); a secret in JUnit failure text is counted, never stored (verify still `BOUND_FAIL` on `JUNIT_FAILED`); a secret-looking LCOV SF path is never stored (no LCOV summary field exists); absolute LCOV SF paths are `LCOV_MALFORMED` → `INVALID`. See the artifact-verbatim observation below. |
| (f) Hash forgery variants | **PASS** | 7 in `tests/adversarial/test_hash_forgery.py` | Size-matches/hash-differs, hash-matches/size-differs, digest-of-other-content (same size), empty-file digest claimed for a real report, and swapped digests between two jobs are all `REPORT_HASH_MISMATCH` (`INVALID`); a flipped byte after bundling is `BUNDLE_HASH_MISMATCH` (+ receipt cross-check `REPORT_HASH_MISMATCH`). |
| (g) Schema confusion | **PASS** | 19 in `tests/adversarial/test_schema_confusion.py` | Extra top-level receipt field, a forged `status: BOUND_PASS` field, wrong `schema` const, wrong `source_mode` enum, uppercase SHA, string-typed `junit.tests`, wrong report `kind` enum, missing `ci`, non-object / non-JSON receipt, and a job dir without a receipt are all `INVALID_RECEIPT`; unknown policy fields (top-level and inside `reports`), wrong policy `source_mode` enum, `schema_version: 2`, empty `required_jobs`, a run-identity field in the policy, a non-dict policy, and a malformed expected-SHA argument are all `INVALID_POLICY`. |
| (h) Command injection via capture | **PASS** | 9 in `tests/adversarial/test_command_injection.py` | `;`, `$(touch …)`, backticks, `&&`, `|` as argv elements are literal arguments (`shell=False`); a metacharacter in argv[0] raises `OSError` (no shell, no receipt). The sentinel file was never created in any variant. |
| (i) Duplicate/confused job identity | **PASS** | 8 in `tests/adversarial/test_job_identity_confusion.py` | Same job_id in two dirs (different or byte-identical content, or a different run id) is `MATRIX_DUPLICATE_JOB` and never verifies twice; a case variant (`Unit-Linux-Py312`) is `MATRIX_MISSING_JOB` + `MATRIX_UNEXPECTED_JOB`, never an alias; two dirs differing only by case are distinct jobs; trailing-space / leading-dot job_ids are `INVALID_RECEIPT`. |
| (j) Tampered bundle manifest | **PASS** (+ P2-03 observation) | 14 in `tests/adversarial/test_manifest_tampering.py` | CRLF endings, duplicate lines, extra blank line, non-hex hash, and a manifest entry naming itself are `BUNDLE_MANIFEST_MALFORMED`; wrong hash / wrong size are `BUNDLE_HASH_MISMATCH` / `BUNDLE_SIZE_MISMATCH`; missing file is `BUNDLE_MISSING_FILE`; extra unlisted file is `BUNDLE_EXTRA_FILE`; swapped hashes and a renamed path are detected. Reordered lines alone still verify (P2-03). |
| Privacy scanner | **PASS** | 35 in `tests/privacy/test_privacy_scan.py` + `02_source/scripts/privacy_scan.py` | Scanner flags secret-named JSON keys, credential-shaped values (`ghp_`/`gho_`/`github_pat_`/`sk-`/`sk-proj-`/`AKIA…`/`xox…`/private-key headers/`Bearer`), TOML secret assignments, unparsable JSON, and absolute home paths (`/home/`, `/Users/`, `C:\Users`, `/root/`); it does NOT flag 40/64-hex SHAs, `[REDACTED]` displays, relative paths, or schema prose mentioning secrets. `privacy_scan.py` over `02_source`: 184 files, 0 findings; over the whole work tree: 188 files, 0 findings. |

## P2-02 — No byte cap on `receipt.json` itself (observation)

A 2 MB whitespace-padded (otherwise valid) receipt parses and yields
the correct `BOUND_PASS` verdict — schema-valid receipt *content* is
bounded (every field has a max length / max items), but the file has
no byte cap, so a hostile multi-MB receipt is parsed in full before
any verdict. **Severity: P2** (robustness / DoS note, not a false
PASS: the verdict is still correct). No test asserts a rejection
here; the probe test pins the current correct-verdict behaviour.
Consider a byte cap in T012/T014 if the threat model grows to
untrusted receipt files at scale.

## P2-03 — Manifest sort order is not enforced by `verify_bundle` (observation)

`BUNDLE_FORMAT.md` documents the manifest as sorted by POSIX path,
but `verify_bundle` treats the manifest as a set of entries: a
reordered manifest still verifies `ok=True`. Tampering is still
detected (a flipped byte in a reordered manifest is
`BUNDLE_HASH_MISMATCH`), so order carries no security information.
**Severity: P2** (format-strictness gap, not a security defect). The
probe test pins both behaviours: reorder-alone verifies, and
reorder-plus-tamper is still caught. Enforcing sort order is a
one-line strictness change for T014 if the format doc is to be
treated as normative.

## Observation (not a numbered finding) — secrets in report artifacts

A declared report artifact is copied verbatim into `artifacts/` by
design: a secret printed by the test itself into its JUnit failure
text (or an LCOV `SF:` path) therefore still exists in the artifact
file, even though the receipt (`receipt.json`) is clean — the tests
assert receipt-cleanliness only. That is the test output's own
content, not something BenchReceipt adds, and the receipt never
carries it. Flag for T012 `LIMITATIONS`: do not print secrets into
test output; the privacy scanner scans `*.json`/`*.toml`/
`SHA256SUMS.txt`, not report artifacts.

## Evidence files (this round)

- `02_source/tests/adversarial/_evidence.py` — shared fixture/repo helpers.
- `02_source/tests/adversarial/test_path_traversal.py` (27),
  `test_oversized_inputs.py` (13), `test_xxe.py` (10),
  `test_secret_redaction.py` (23), `test_hash_forgery.py` (7),
  `test_schema_confusion.py` (19), `test_command_injection.py` (9),
  `test_job_identity_confusion.py` (8), `test_manifest_tampering.py` (14).
- `02_source/scripts/privacy_scan.py` + `02_source/tests/privacy/test_privacy_scan.py` (35).
- `03_evidence/tests/pytest-t011-resume-adversarial-privacy.log` — 168 passed.
- `03_evidence/tests/pytest-t011-resume.log` — full suite: 670 passed.
- `03_evidence/tests/s0-gate-t011-resume.log` — S0 gate: PASS 10/10.
- `03_evidence/tests/oracle-t011-resume.log` — Oracle: 8/8 passed.
- `03_evidence/privacy/privacy_scan.log` — scanner: 184 files / 0 findings
  (`02_source`), 188 files / 0 findings (whole work tree).
- This file: `03_evidence/privacy/SECURITY_FINDINGS.md` (appended).
