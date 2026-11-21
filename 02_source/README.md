# BenchReceipt（测证收据）

**CI 显示绿色，不代表所有绿色测试报告都属于同一个代码版本。**

BenchReceipt is a local-first CI test-evidence binding tool. For every CI
test matrix job it generates a `benchreceipt.run/v1` receipt binding the
Git commit/tree, source mode, workflow run/attempt, job/matrix, command
digest, runner environment and JUnit/LCOV report hashes — then an
aggregator verifies, against a `.benchreceipt.toml` policy, that all jobs
belong to the same expected source and the same workflow run/attempt, that
the required matrix is complete, and that no report was swapped, lost or
mixed in from another run.

## Status

- **Spec:** v1.2.0 (ADR-007; P0-R1-01 legacy-shape fail-closed fix).
- **Build:** T001–T012 complete. Full suite **683 passed** (670 at T011
  + 6 cross-platform boundary tests, T012, + 7 console-script
  regression tests, FIX-P1-01), S0 gate **PASS 10/10**
  (52 fixtures; repeat hash `a19054f1…`), independent Node.js Oracle
  **8/8**, privacy scan **184 files, 0 findings**.
- **Performance (T012 resume, this VM):** P95 **0.1041 s** per 100-manifest
  verification (limit 1 s) — see `03_evidence/performance/performance-t012-resume.json`.
- **Offline (T012, this VM):** capture/verify/report make **0 network
  requests** (static scan clean + audit-hook trace) — see
  `03_evidence/t012/offline_check.json`.
- **Not yet done:** independent review (T013) and release freeze
  (T014). No GitHub upload exists for this project.
- **Platforms:** verified on Ubuntu 24.04.5 / Python 3.12.3 / Node
  v24.22.1 only. **Windows and macOS are NOT_TESTED** — see
  `docs/LIMITATIONS.md`.

## Honest boundary — what BenchReceipt proves and what it does not

**It proves:** whether the Git commit/tree, run/attempt, job/matrix and
report bytes collected in the current workspace satisfy the declared
binding rules — and it detects PR head/merge SHA confusion,
cross-run/attempt mixing, missing/duplicate matrix jobs, dirty source
during a run, and missing or hash-mismatched reports.

**It does NOT prove:**

- that the tests themselves are correct, or that their assertions are
  strong enough — a passing suite can still miss bugs;
- that the code under test is correct or vulnerability-free;
- authenticity against a malicious runner: receipts are **unsigned
  SHA-256** bindings. A compromised runner or workflow can forge a whole
  bundle. SHA-256 here detects accidental mixing, stale artifacts and
  byte changes — it is not a signature;
- anything about PR prose vs. diff (no claim matching), flaky-test
  ranking, or coverage quality.

BenchReceipt does **not** replace SLSA, in-toto/Sigstore, or GitHub
Artifact Attestations. It can export an unsigned in-toto Statement aligned
with the in-toto Test Result Predicate, but an unsigned file must never be
presented as a security attestation.

The full list of known limitations (including P2-01 transient
mutate-and-revert, P2-02 no receipt byte cap, P2-03 unenforced manifest
sort order, and the verbatim-artifact secret observation) is in
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md). Read it before relying on
a `BOUND_PASS`.

## Install

Python ≥ 3.12, standard library only — no runtime dependencies, no
network access at runtime.

```bash
# From this directory (02_source):
python -m pip install -e .
```

The install provides the `benchreceipt` console script
(`[project.scripts]`, spec §6.4):

```bash
benchreceipt --help
```

## Quickstart

Every command below was run verbatim in bare form on this VM during
the T012 resume (`03_evidence/t012/quickstart-bare.log`, 2026-11-18)
and produced `BOUND_PASS`. It uses a scratch repo with one green test.

```bash
# 1. A scratch repo with one green test.
mkdir quickstart-demo && cd quickstart-demo
git init -q -b main
printf 'def test_add():\n    assert 1 + 1 == 2\n' > test_demo.py
printf '.benchreceipt/\n__pycache__/\n.pytest_cache/\n' > .gitignore
git add . && git commit -qm "demo: one green test"

# 2. A policy for a local single-job run. Commit it: capture requires
#    a clean tree at start, and an uncommitted policy file would make
#    the run dirty (see "Why did I get UNBOUND?" below).
cat > .benchreceipt.toml <<'TOML'
schema_version = 1
source_mode = "event_sha"
expected_workflow = "local"
required_jobs = [ "demo-linux-py312" ]
min_tests = 1
require_clean_source_after = true
same_tree_across_jobs = true
same_run_id = false
same_run_attempt = false

[reports]
junit = "required"
lcov = "optional"

[security]
store_stdout = false
store_stderr = false
store_full_environment = false
TOML
git add .benchreceipt.toml && git commit -qm "demo: add benchreceipt policy"

# 3. Capture: wrap the test command, write the receipt.
benchreceipt capture --job demo-linux-py312 \
  --matrix os=ubuntu-latest,python=3.12 \
  --junit .benchreceipt/out/junit.xml \
  -- python -m pytest -q -p no:cacheprovider \
     --junitxml=.benchreceipt/out/junit.xml test_demo.py
# -> benchreceipt capture: job=demo-linux-py312 exit=0
#    receipt=.benchreceipt/evidence/demo-linux-py312/receipt.json
#    source_mutated=false

# 4. Verify the evidence against the policy and the HEAD SHA.
SHA=$(git rev-parse HEAD)
benchreceipt verify --policy .benchreceipt.toml \
  --evidence .benchreceipt/evidence --expected-source-sha "$SHA" \
  --out .benchreceipt/verification.json
# -> benchreceipt verify: status=BOUND_PASS jobs_verified=1
#    reason_codes=- out=.benchreceipt/verification.json
#    (exit 0)

# 5. Render the evidence-chain page.
benchreceipt report --input .benchreceipt/verification.json \
  --html .benchreceipt/report.html
# -> benchreceipt report: status=BOUND_PASS html=.benchreceipt/report.html

# 6. Bundle the evidence for transport, and verify the bundle.
benchreceipt bundle --evidence .benchreceipt/evidence \
  --out .benchreceipt/bundle
benchreceipt bundle --verify .benchreceipt/bundle
# -> benchreceipt bundle: ok: 2 files checked, 2 manifest entries
```

### Why did I get UNBOUND?

The most common cause in a local run is a dirty tree. `capture`
requires the tree clean at start and unchanged (except the declared
evidence output directory) at end; anything else is recorded as
`SOURCE_MUTATED_DURING_RUN` and verify fails closed with `UNBOUND`
(exit 2). In the T012 quickstart run, the first attempt failed exactly
this way — the policy file was uncommitted and the JUnit output was not
ignored — and committing the policy plus ignoring `.benchreceipt/` fixed
it. That is the gate working, not a bug: a receipt must never certify
tests that ran against a tree nobody can reproduce.

### Exit codes (PROJECT_BOOK §5.6)

| Status | Meaning | Exit |
|---|---|---:|
| `BOUND_PASS` | evidence complete, identity consistent, tests green | 0 |
| `BOUND_FAIL` | binding holds, but tests failed or a policy condition failed | 1 |
| `UNBOUND` | missing identity, matrix, or report; binding unprovable | 2 |
| `INVALID` | malformed input, damaged hash, or schema violation | 3 |
| `INTERNAL_ERROR` | unexpected BenchReceipt failure (never a pass) | 4 |

## Layout

```text
02_source/
  pyproject.toml            # Python >= 3.12, stdlib-only runtime deps
  src/benchreceipt/         # production CLI
  tests/                    # pytest suite (683 tests)
  oracle/                   # independent Node.js 24 Oracle (T004)
  fixtures/s0/              # 52 frozen S0 fixtures (T004; e5/e6 added by ADR-005; e7/e8 added by ADR-007)
  scripts/                  # s0_gate.py, performance_smoke.py, offline_check.py,
                            # privacy_scan.py, validate_workflow_example.py
  examples/github-actions/  # CI workflow example (T009)
  docs/                     # USER_GUIDE.md, LIMITATIONS.md, BUNDLE_FORMAT.md,
                            # REASON_CODES.md (T012)
  src/benchreceipt/schemas/  # benchreceipt.run/v1, result/v1, policy/v1
  LICENSE                   # MIT
  README.md                 # this file
```

Full user guide: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).

## License

MIT — see [LICENSE](LICENSE).
