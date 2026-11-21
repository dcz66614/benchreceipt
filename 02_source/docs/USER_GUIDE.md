# BenchReceipt User Guide (P027-T012, spec v1.2.0)

Local-first CI test-evidence binding: capture per-job receipts, verify
them against a policy, render the verdict, and bundle the evidence for
transport. Everything here runs offline on the machine that holds the
evidence — BenchReceipt makes no network requests, calls no API, and
needs no token (proven for capture/verify/report in T012; see
`03_evidence/t012/offline_check.json`).

Companion references: `BUNDLE_FORMAT.md` (bundle + manifest format),
`REASON_CODES.md` (every reason code), `LIMITATIONS.md` (what a
`BOUND_PASS` does **not** mean — read it before gating on a verdict),
`../README.md` (verified quickstart), `../examples/github-actions/`
(the CI workflow example).

## 1. Install

Requirements: Python ≥ 3.12, `git` on `PATH`. No runtime dependencies
(standard library only). The test suite needs `pytest` (dev only).

```bash
# From 02_source/:
python -m pip install -e .

# Check it:
benchreceipt --help
```

The install provides the `benchreceipt` console script
(`[project.scripts]` in `pyproject.toml`, spec §6.4). It is the
documented invocation everywhere in this guide and in the CI example.
(The earlier T012 finding P1-01 — no console script existed, so the
module form was the only invocation — was closed by the FIX-P1-01
task: `pyproject.toml` now declares the entry point and 7 regression
tests pin the installed script; see
`03_evidence/t012/FINDING-P1-01-missing-console-script.md` for the
finding and its closure.)

In CI, install from a vendored copy of this source tree (never
download it at runtime); see §6.

## 2. Concepts

- **Receipt** (`benchreceipt.run/v1`, `receipt.json`): one per matrix
  job. Binds the job id, matrix cell, Git HEAD/tree *before and after*
  the run, source mode, workflow run/attempt, command digest, and the
  SHA-256 + size of each declared report (JUnit/LCOV).
- **Policy** (`.benchreceipt.toml`): declares the expected source mode,
  workflow, required job ids, `min_tests`, and which reports are
  required/optional. See `../examples/benchreceipt.toml`.
- **Evidence tree** (`.benchreceipt/evidence/<job-id>/`): one directory
  per job, containing `receipt.json` plus `artifacts/` (the report
  bytes, copied verbatim).
- **Verdict** (`benchreceipt.result/v1`, `verification.json`): the
  outcome of verifying the whole evidence tree against the policy:
  `BOUND_PASS` / `BOUND_FAIL` / `UNBOUND` / `INVALID` /
  `INTERNAL_ERROR`, with `reason_codes` explaining every non-pass.
  Exit codes: 0 / 1 / 2 / 3 / 4 respectively (PROJECT_BOOK §5.6).
- **Bundle**: a portable copy of an evidence tree plus a
  `SHA256SUMS.txt` manifest (`<sha256> <size> <relative-posix-path>`,
  LF endings), verifiable offline with `bundle --verify`.

## 3. Capture — wrap a test command

```bash
benchreceipt capture --job <job-id> \
  --matrix os=<os>,python=<version> [--matrix <k=v,...>] \
  [--junit <path>] [--lcov <path>] \
  -- <command> [args...]
```

- `--job` is a stable id (max 128 chars; e.g. `unit-linux-py312`).
  It is also the evidence subdirectory name, so it must be a safe
  relative path segment (no `/`, `\`, `..`, leading `.`, or spaces
  at the edges).
- `--matrix` is repeatable; each is a comma-separated `k=v` list
  (max 32 entries, keys ≤ 64 chars).
- `--junit` / `--lcov` name the report files the wrapped command
  produces. They are hashed, copied verbatim into `artifacts/`, and
  (for JUnit) parsed for the `tests`/`failures`/`errors`/`skipped`
  summary stored in the receipt. A malformed report omits the summary
  and verify reports `MISSING_FIELD` / `UNBOUND` — fail-closed, never
  a silent pass.
- The wrapped command runs **without a shell** (`shell=False`); shell
  metacharacters in argv are literal arguments, never executed.
- The exit code of `capture` is the wrapped command's exit code, and
  a failure receipt is still written when the command fails — the
  evidence of a red run is itself evidence.
- **Clean tree required.** Capture records `git status` before and
  after. If the tree is dirty at start, or tracked source changes
  during the run (outside the declared evidence output directory),
  the receipt records `source_mutated_during_run` and verify reports
  `SOURCE_MUTATED_DURING_RUN` / `UNBOUND`. Commit the policy file and
  add `.benchreceipt/` to `.gitignore` before capturing (the README
  quickstart shows the exact setup). Report outputs themselves must
  live under `.benchreceipt/` (or another ignored directory) so their
  creation does not count as a source mutation.
- Secrets in argv (`--token …`, `--api-key=…`, `password=…`) are
  redacted to `[REDACTED]` in `command.display` and never reach the
  receipt. **But** a secret printed by the test itself into its JUnit
  failure text (or an LCOV `SF:` path) still exists in the verbatim
  artifact copy — see `LIMITATIONS.md`. Do not print secrets into
  test output.

Example (local, single job — the full run is in the README quickstart):

```bash
benchreceipt capture --job demo-linux-py312 \
  --matrix os=ubuntu-latest,python=3.12 \
  --junit .benchreceipt/out/junit.xml \
  -- python -m pytest -q --junitxml=.benchreceipt/out/junit.xml test_demo.py
```

## 4. Verify — check a bundle of receipts

```bash
benchreceipt verify --policy <policy.toml> \
  --evidence <evidence-dir> \
  --expected-source-sha <40-hex> \
  [--expected-run-id <id>] [--expected-attempt <n>] \
  --out <verification.json>
```

- `--expected-source-sha` is the SHA every job's `git.head_sha` must
  equal. It is required; a missing or malformed value exits 3
  (`INVALID`), never a pass.
- `--expected-run-id` / `--expected-attempt` additionally pin the
  workflow run id / attempt every job must share (attempt 1–100000).
- `--out` is always written (even for non-pass verdicts) and is itself
  validated against `benchreceipt.result/v1`; if the verifier ever
  produced a malformed result it would exit 4 instead of writing it.
- What verify checks, in order: every receipt parses and matches the
  frozen `benchreceipt.run/v1` schema; the source mode matches the
  policy; every job's HEAD/tree equal the expected source; the
  before/after identity is unchanged (`SOURCE_MUTATED_DURING_RUN`
  otherwise); the required job matrix is complete with no duplicates
  or unexpected jobs; all jobs share the same run id / attempt / tree;
  every declared report exists in `artifacts/` with matching size and
  SHA-256 and parses (JUnit: `tests > 0`, `failures = errors = 0`,
  testcase count consistent with the header).
- A missing file, a parse failure, or an unknown field never degrades
  to PASS — the result is `UNBOUND` or `INVALID`. See
  `REASON_CODES.md` for the full list of reason codes.

## 5. Report — render the verdict as HTML

```bash
benchreceipt report --input <verification.json> \
  --html <report.html>
```

Renders a single self-contained HTML evidence-chain page (inline
CSS/JS only, no external resources, no network). It reads only the
verification JSON — it never re-runs verification and never touches
the evidence. Exit 0 on valid input, 3 on invalid input or a rendering
failure.

## 6. Bundle — transport the evidence

```bash
# Build:
benchreceipt bundle --evidence <evidence-dir> --out <bundle-dir>
# Verify a bundle you received (offline):
benchreceipt bundle --verify <bundle-dir>
```

Build copies the evidence tree verbatim and writes `SHA256SUMS.txt`
(one line per file, sorted by POSIX relative path, LF endings).
Verify re-hashes every listed file, checks sizes, and rejects:
missing/extra files, hash/size mismatches, CRLF or duplicate manifest
lines, escaping or backslash paths, and symlinks. A bundle that fails
integrity verification exits 3. See `BUNDLE_FORMAT.md` for the exact
format. Note the documented P2-03 gap: reordered manifest lines alone
still verify (order carries no security information; tampering in a
reordered manifest is still caught) — see `LIMITATIONS.md`.

## 7. CI example — GitHub Actions

The full working example is `../examples/github-actions/ci.yml`
(validated by `../scripts/validate_workflow_example.py` and the
integration tests; it has **not** been run on real GitHub Actions —
there is no real repo for this project yet). Its shape, condensed:

```yaml
# jobs.test (one per matrix cell):
#   - uses: actions/checkout@v4
#     with:
#       ref: ${{ github.event.pull_request.head.sha || github.sha }}
#       # Check out the PR HEAD, not the merge commit (PROJECT_BOOK §1.2 A).
#   - uses: actions/setup-python@v5
#   - run: python -m pip install --no-build-isolation ./vendor/benchreceipt
#       # Installed from a path inside the repo, never downloaded.
#   - run: benchreceipt capture --job ${{ matrix.job_id }}
#       --matrix os=${{ matrix.os }},python=${{ matrix.python }}
#       --junit .benchreceipt/out/junit.xml
#       -- python -m pytest -q --junitxml=.benchreceipt/out/junit.xml
#   - uses: actions/upload-artifact@v4
#     with:
#       name: benchreceipt-evidence-${{ matrix.job_id }}
#       path: .benchreceipt/evidence/${{ matrix.job_id }}
#
# jobs.verify (needs: test):
#   - download every per-job artifact into .benchreceipt/evidence/<job-id>
#   - run: benchreceipt verify --policy .benchreceipt.toml
#       --evidence .benchreceipt/evidence
#       --expected-source-sha ${{ github.event.pull_request.head.sha || github.sha }}
#       --out .benchreceipt/verification.json
#     # Fails (non-zero exit) on anything other than BOUND_PASS.
```

Rules the example enforces (PROJECT_BOOK §1.2 A, §2.2, §7.1):

- **Source identity:** for `pull_request` events GitHub defines two
  SHAs — `github.event.pull_request.head.sha` (what the author wrote)
  and `github.sha` (the merge commit `actions/checkout` checks out by
  default). The workflow explicitly checks out the PR head **and**
  verifies against that same SHA. Change both together or neither:
  checking out the merge commit while the policy says
  `source_mode = "pr_head"` correctly yields
  `SOURCE_SHA_MISMATCH` / `UNBOUND`.
- **Push events:** the example policy is `pr_head`, so a `push` run
  captures with `source_mode = "event_sha"` and verifies `UNBOUND`
  (`SOURCE_MODE_MISMATCH`). That is by design — this policy is a PR
  gate. Use a second policy file with `source_mode = "event_sha"` for
  a push gate.
- **No token, no API:** nothing uses `github.token`, `secrets.*`, the
  `gh` CLI, or any GitHub API call. Identity comes only from the
  checkout, the event payload on the runner, and the standard
  `GITHUB_*` environment variables. The validator script fails the
  build if a token or API call is ever added to the workflow file.
- **Matrix:** the example covers `ubuntu-latest` / `windows-latest` ×
  Python 3.12 / 3.13. The Windows cells are in the workflow text, but
  **Windows has never been run** — see `LIMITATIONS.md`.

## 8. Policy file reference

```toml
schema_version = 1
source_mode = "pr_head"        # or "merge_commit" | "event_sha" | "explicit_sha"
                               # "explicit_sha" pins the source to one SHA:
                               # capture with --source-mode explicit_sha
                               # --expected-sha <40-hex-sha> (ADR-006)
expected_workflow = "CI"       # workflow name every job must share
required_jobs = [ "unit-linux-py312", "unit-linux-py313" ]
min_tests = 1
require_clean_source_after = true
same_tree_across_jobs = true
same_run_id = true
same_run_attempt = true

[reports]
junit = "required"             # "required" | "optional"
lcov = "optional"

[security]
store_stdout = false
store_stderr = false
store_full_environment = false
```

Unknown policy fields are `INVALID_POLICY` — the policy schema is
closed, so a typo'd key fails loudly instead of being silently
ignored. See `../src/benchreceipt/schemas/policy.v1.json` and `../examples/benchreceipt.toml`.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `SOURCE_MUTATED_DURING_RUN` / `UNBOUND`, exit 2 | tree dirty at capture start, or a file changed during the run (uncommitted policy, unignored report output) | commit everything except ignored output; add `.benchreceipt/` to `.gitignore` |
| `SOURCE_SHA_MISMATCH` / `UNBOUND` | verified SHA ≠ receipt HEAD (e.g. merge commit vs PR head) | pass the same SHA you checked out; see §7 |
| `MISSING_FIELD` / `UNBOUND` | policy requires junit but the receipt has no JUnit summary (report missing or malformed) | check the JUnit file exists and parses; a malformed report is a fail-closed `UNBOUND`, not a pass |
| `MATRIX_MISSING_JOB` / `MATRIX_UNEXPECTED_JOB` | evidence tree ≠ `required_jobs` (typo, case variant, extra job) | job ids are case-sensitive and exact |
| `REPORT_HASH_MISMATCH` / `INVALID` | artifact bytes changed after capture, or the receipt's digest was edited | re-capture; never hand-edit a receipt |
| `BUNDLE_MANIFEST_MALFORMED` | CRLF endings, duplicate lines, backslash/escaping paths in `SHA256SUMS.txt` | rebuild the bundle from the evidence tree |
| `INTERNAL_ERROR`, exit 4 | unexpected BenchReceipt failure | file a bug with the stderr line; the run is not a pass |

## 10. Performance and offline notes

- Verification is fast: on the T012-resume host (Ubuntu 24.04.5, 4 vCPU,
  Python 3.12.3) a 100-job bundle verifies with P95 **0.1041 s**
  (limit 1 s) over 100 repetitions — `03_evidence/performance/performance-t012-resume.json`.
  (The first T012 run measured 0.1481 s; same limit, same host.)
- Capture/verify/report/bundle make zero network requests (T012
  offline check: static scan of `src/` clean + audit-hook trace of a
  full end-to-end run showing 0 socket events).
- Receipts are small by design, but see `LIMITATIONS.md` P2-02: there
  is no byte cap on `receipt.json` itself.
