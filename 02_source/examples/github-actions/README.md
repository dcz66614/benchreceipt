# GitHub Actions integration — BenchReceipt example (P027-T009)

A complete example workflow (`ci.yml`) plus the policy it verifies
against (`../benchreceipt.toml`). It shows how to wire BenchReceipt
into GitHub Actions **without a GitHub API token, without any paid API,
and without BenchReceipt ever touching the network**.

Status: example files only. This workflow has **not** been run on real
GitHub Actions — no real repository exists for this project yet. It is
validated only by the synthetic/local checks in
`02_source/tests/integration/test_github_actions.py` and
`02_source/scripts/validate_workflow_example.py`.

## 1. What the workflow does

```
pull_request / push
  └─ job `test` (matrix: 2 OS × 2 Python = 4 jobs)
  │    checkout PR head → setup-python → pip install BenchReceipt
  │    (from a local path) → `benchreceipt capture` wraps pytest
  │    → upload `.benchreceipt/evidence/<job-id>/` as artifact
  │      `benchreceipt-evidence-<job-id>`
  └─ job `verify` (needs: test)
       checkout PR head → install BenchReceipt → download ALL FOUR
       job artifacts into `.benchreceipt/evidence/<job-id>/`
       → confirm every `receipt.json` is present
       → `benchreceipt verify` → fails the job unless BOUND_PASS
```

The matrix is explicit (`strategy.matrix.include`), so each job id is
stable and matches the policy exactly:

| job id | os | python |
|---|---|---|
| `unit-linux-py312` | ubuntu-latest | 3.12 |
| `unit-linux-py313` | ubuntu-latest | 3.13 |
| `unit-windows-py312` | windows-latest | 3.12 |
| `unit-windows-py313` | windows-latest | 3.13 |

These four ids are exactly the `required_jobs` in
`../benchreceipt.toml`. The validator script enforces that equality:
if you add or remove a matrix cell, update `required_jobs` to match,
or verification will report `MATRIX_MISSING_JOB` /
`MATRIX_UNEXPECTED_JOB` (UNBOUND).

## 2. Copying it into your repository

1. Copy `ci.yml` to `.github/workflows/ci.yml` in your repo.
2. Copy `../benchreceipt.toml` to `.benchreceipt.toml` at your repo
   root (that is the `--policy` path the `verify` job uses).
3. Vendor BenchReceipt itself: copy this project's `02_source/`
   directory to `vendor/benchreceipt/` in your repo, **or** build a
   wheel once (`python -m build`, in `02_source/`) and commit it under
   `dist/`, changing the install step to
   `python -m pip install ./dist/benchreceipt-0.1.0-py3-none-any.whl`.
   Either way BenchReceipt is installed from a path inside your repo —
   the workflow never downloads BenchReceipt from the internet. The
   only network use is the standard `actions/checkout` and
   `actions/setup-python` actions.
4. Make sure your test run leaves no untracked files behind: the
   example runs pytest with `-p no:cacheprovider` and sets
   `PYTHONDONTWRITEBYTECODE=1`, and writes the JUnit report under
   `.benchreceipt/out/`. Capture treats any other new file in the
   worktree (`.pytest_cache/`, `__pycache__/`, a stray `.coverage`)
   as source mutation during the run (`SOURCE_MUTATED_DURING_RUN`,
   UNBOUND). Add those paths to your `.gitignore` if your suite
   produces them.
5. Run `python 02_source/scripts/validate_workflow_example.py` after
   any edit to the workflow; it fails on structural mistakes, on a
   policy/matrix mismatch, and on any token or API call creeping in.

## 3. The pr_head vs merge_commit decision (PROJECT_BOOK §1.2, scenario A)

For a `pull_request` event GitHub defines two different SHAs:

- `github.event.pull_request.head.sha` — the tip of the PR branch,
  i.e. what the author actually wrote;
- `github.sha` / `GITHUB_SHA` — the *merge* commit GitHub synthesises
  to test the PR merged into its base, which is also what
  `actions/checkout` checks out **by default**.

This example **explicitly chooses the PR head**, in both jobs:

```yaml
ref: ${{ github.event.pull_request.head.sha || github.sha }}
```

and verifies against that same SHA:

```yaml
--expected-source-sha ${{ github.event.pull_request.head.sha || github.sha }}
```

The `|| github.sha` fallback applies only to `push` events, where
there is no `pull_request` payload and the pushed commit is the only
sensible identity.

How capture reacts, per the frozen source-mode rules (T003):

- checkout is the PR head → receipt `source_mode = "pr_head"`,
  `expected_source_sha` = head SHA → matches the policy.
- checkout is the merge commit (e.g. you drop the explicit `ref:`)
  → receipt `source_mode = "merge_commit"`,
  `expected_source_sha` = merge SHA → verify reports
  `SOURCE_SHA_MISMATCH` (UNBOUND) against the `pr_head` policy and
  the expected head SHA. The report would describe the merge commit,
  not the PR head you asked to verify — the gate failing is correct
  behaviour, not a false alarm.

To verify the merge commit instead, change **both** the checkout
`ref:` and the policy `source_mode` to `"merge_commit"`. Changing
only one side silently re-introduces the confusion this tool exists
to catch.

**Push events.** The shipped policy is `source_mode = "pr_head"`, so
it is a PR gate. On a `push` run capture records
`source_mode = "event_sha"` and the aggregate job reports
`SOURCE_MODE_MISMATCH` / UNBOUND. That is by design. For a push gate,
use a second policy file with `source_mode = "event_sha"`.

## 4. How the aggregate job works — and why it downloads first

`actions/download-artifact` does **not** verify anything; it only
transports files. If the aggregate job verified after downloading
whatever happened to be there, a missing or stale artifact could pass
unnoticed. So the `verify` job is deliberately boring and explicit:

1. It `needs: test`, so it only runs after the matrix jobs finish.
2. It downloads each of the four job artifacts **by name, one step
   per job**, into `.benchreceipt/evidence/<job-id>/`. (A single
   `pattern:` + `merge-multiple: true` download is *not* used: it
   would merge four `receipt.json` files into one directory and
   destroy the per-job layout `verify` expects.)
3. A guard step asserts all four `receipt.json` files exist before
   any verification runs. A missing download fails the job here,
   before `verify` is even invoked.
4. Only then it runs:

   ```bash
   benchreceipt verify \
     --policy .benchreceipt.toml \
     --evidence .benchreceipt/evidence \
     --expected-source-sha ${{ github.event.pull_request.head.sha || github.sha }} \
     --out .benchreceipt/verification.json
   ```

   `verify` exits non-zero for anything other than `BOUND_PASS`, and
   a non-zero step fails the job in GitHub Actions. The result JSON is
   printed to the log and uploaded as the `benchreceipt-verification`
   artifact (`if: always()`, so it is kept even when the gate fails).

`verify` checks, for the whole bundle at once (PROJECT_BOOK §5.2–§5.4):

- every `required_jobs` entry is present exactly once (missing /
  unexpected / duplicate jobs → UNBOUND);
- every job's `git.head_sha` equals the expected source SHA, every
  job shares one tree SHA, one run id and one run attempt — a Linux
  artifact from attempt 1 mixed with a Windows artifact from attempt
  2 is rejected with `RUN_ATTEMPT_MISMATCH` (scenario B), even when
  both JUnit files are green;
- every report listed in a receipt is present, byte-identical
  (SHA-256 recomputed) and parses, with `tests > 0`, `failures = 0`,
  `errors = 0`.

### Exit codes (PROJECT_BOOK §5.6)

| `verify` exit | Status | Meaning |
|---:|---|---|
| 0 | `BOUND_PASS` | Evidence complete, identities consistent, tests green. |
| 1 | `BOUND_FAIL` | Evidence belongs to the expected run, but tests failed (or a policy condition such as `min_tests` failed). |
| 2 | `UNBOUND` | Cannot prove the binding: missing/duplicate/unexpected job, source/run/attempt mismatch, missing report or missing field. **This is the fail-closed outcome — never a pass.** |
| 3 | `INVALID` | Input malformed: bad policy, unreadable receipt, report hash mismatch, malformed JUnit/LCOV. |
| 4 | `INTERNAL_ERROR` | The verifier itself failed unexpectedly. |

## 5. Known limitation — closed by FIX-capture-junit (2026-11-17)

**The T003/T008 seam documented here is now fixed.** `capture`
emits the parsed `junit` summary counts (counted testcases via the
T005 parser) into the receipt, so an all-green, same-head, same-run,
same-attempt, matrix-complete bundle now verifies as

```json
{"status": "BOUND_PASS", "reason_codes": [], "jobs_verified": 4}
```

Previously (T003 capture, verified 2026-11-17 in a synthetic git
repo with the real CLI and a real PR event JSON) the same bundle was
`{"status": "UNBOUND", "reason_codes": ["MISSING_FIELD"],
"jobs_verified": 0}`: `capture` wrote the JUnit report bytes and
their SHA-256 but no parsed `junit` summary, while `verify` (T008)
requires the summary when the policy marks junit `"required"`. The
gate failed closed then — it never produced a false green — it just
could not produce a green at all. The fix (branch
`fix-capture-junit`, ADR-004) also pins the new behaviour in
`02_source/tests/integration/test_github_actions.py`
(`test_all_green_bundle_verifies_bound_pass`) and in
`02_source/tests/capture/test_capture_junit_summary.py`. A malformed
JUnit report still fails closed: no summary is guessed, the receipt
is written with a stderr warning, and verify reports
`JUNIT_MALFORMED` → INVALID.

One gap remains, by design: the frozen `benchreceipt.run/v1` schema
has no field for an LCOV summary, so `capture` does not emit one —
only the JUnit summary is recorded (see ADR-004). Adding an LCOV
summary field is a spec decision for T013, not a capture change.

## 6. Honest limits — what this does not give you

- **No signing, no SLSA replacement.** Receipts are unsigned SHA-256
  bindings. They detect accidental mixing, stale artifacts, byte
  changes and configuration mistakes. A compromised runner or a
  malicious workflow can forge a whole bundle. Do not present a
  `BOUND_PASS` as a security attestation; for that, use GitHub
  Artifact Attestations, Sigstore, or SLSA tooling. (PROJECT_BOOK
  §0.3, §2.2.)
- **No judgement about the tests themselves.** A green suite with
  weak assertions still passes; BenchReceipt only proves the green
  report belongs to the expected commit, run, attempt, matrix cell
  and report bytes.
- **No token, no API, no network at runtime.** That is a deliberate
  property, not a missing feature: identity comes from the checkout,
  the event payload and the `GITHUB_*` environment. If a future
  integration needs a GitHub API token, this example must be removed
  and the change recorded in an ADR (IMPLEMENTATION_PLAN §5 T009
  failure fallback) — never quietly add a token here.
- **Windows is exercised only as a matrix cell in this file.**
  The Windows job has not been run on a real Windows runner in this
  project (no Windows host available; see `00_control/ENVIRONMENT.md`:
  Windows NOT_TESTED). The workflow syntax is the same on both OSes,
  but a real Windows run is still an untested claim.
- **The example policy is the shipped one.** It requires junit and
  treats lcov as optional, requires a clean source tree after the
  run, and requires one tree / run id / run attempt across jobs.
  Change it only by editing `.benchreceipt.toml` and re-running the
  validator so the matrix and the policy cannot silently diverge.

## 7. Files

| File | Purpose |
|---|---|
| `ci.yml` | The example workflow (this document's subject). |
| `README.md` | This file. |
| `../benchreceipt.toml` | The example policy the workflow verifies against. Its `required_jobs` must equal the workflow matrix job ids. |
| `../../scripts/validate_workflow_example.py` | Stdlib-only structural validator for `ci.yml` (no PyYAML needed). Run it after any edit. |
| `../../tests/integration/test_github_actions.py` | Synthetic `GITHUB_EVENT_PATH` end-to-end tests: PR head capture, merge-commit confusion, attempt mixing, artifact naming, validator negatives. |

### Change record (T009)

- 2026-11-17: workflow created (2 OS × Python 3.12/3.13 = 4 jobs).
  `../benchreceipt.toml` `required_jobs` expanded from the §6.3
  two-job set (`unit-linux-py312`, `unit-windows-py312`) to the four
  workflow job ids (added `unit-linux-py313`, `unit-windows-py313`);
  nothing else in the policy changed. The two existing tests that
  asserted the old two-job list
  (`tests/schema/test_policy_schema.py`,
  `tests/policy/test_policy.py`) were updated mechanically to the
  new four-job list — they still assert exactly what the file
  contains; no assertion was weakened.
