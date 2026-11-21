# S0 Gate Report — P027 BenchReceipt

- Generated: 2026-11-18T02:04:29.578630Z
- Verdict: **S0 PASS**
- Fixtures: 50 (16 controls + 34 planted faults)
- Golden SHA-256: `65ccd954142d10cca5885277088924e7fec686047da77592a6eb8140d0ef7870`
- Reason codes SHA-256: `a60613b31be216ed9a18e7c64a0fd505ff87f3812df93d65b03687923e1b46b8`

## Thresholds (PROJECT_BOOK §8.3 — all 10 must pass)

| # | Threshold | Result | Detail |
|---|---|---|---|
| 1 | normal controls 16/16 BOUND_PASS | PASS | 16/16 controls BOUND_PASS (python+oracle) |
| 2 | planted faults 34/34 detected with correct reason code | PASS | 34/34 faults match Golden (status + reason codes, both impls) |
| 3 | False PASS = 0 | PASS | false PASS count = 0 |
| 4 | False block = 0 | PASS | false block count = 0 |
| 5 | production / Oracle parity 50/50 | PASS | parity 50/50 fixtures |
| 6 | 100 replays 1 hash | PASS | 1 distinct canonical SHA-256 over 100 replays (hash a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530) |
| 7 | 100 manifests P95 <= 1s | PASS | P95 = 0.07187618499995096s (perf script exit 0) |
| 8 | offline run, external network requests = 0 | PASS | no network tokens in Python verifier / Node Oracle; perf network_requests=0 |
| 9 | no full env/stdout/stderr/absolute user paths in receipts | PASS | 77 receipts scanned, 0 violations |
| 10 | reproducible logs + hashes | PASS | 50 fixtures inventoried; per-file SHA-256 recorded in this report |

## Summary

- Controls BOUND_PASS: 16/16
- Faults detected with correct reason code: 34/34
- False PASS: 0; false block: 0
- Production / Oracle parity: 50/50
- Repeat-100 distinct hashes: 1
- P95 (100 manifests): 0.07187618499995096s
- Offline network refs in code: 0
- Privacy violations in receipts: 0

## Per-fixture results

| Fixture | Control | Python | Oracle | Golden | Parity | Pass |
|---|---|---|---|---|---|---|
| a1-wrong-source-sha | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| a2-one-job-wrong-sha | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| a3-merge-expected-head-found | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| a4-mode-mismatch-only | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| b1-tree-mismatch | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| b2-three-job-one-tree-differs | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| b3-tree-mismatch-reversed | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| b4-two-trees-differ | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| c1-attempt-mismatch | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| c2-run-id-mismatch | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| c3-run-and-attempt-mismatch | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| c4-three-job-one-attempt-differs | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| d1-matrix-missing | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| d2-matrix-duplicate | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| d3-matrix-unexpected | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| d4-missing-plus-unexpected | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| e1-clean-to-dirty | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| e2-one-job-mutated | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| e3-started-dirty-stayed-dirty | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| e4-digest-changed-flags-clean | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| e5-clean-tree-head-change | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| e6-empty-commit-mid-run | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| f1-report-file-missing | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| f2-report-hash-mismatch | no | INVALID | INVALID | INVALID | yes | yes |
| f3-lcov-required-missing | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| f4-report-size-lie | no | INVALID | INVALID | INVALID | yes | yes |
| g1-junit-failed | no | BOUND_FAIL | BOUND_FAIL | BOUND_FAIL | yes | yes |
| g2-junit-empty | no | BOUND_FAIL | BOUND_FAIL | BOUND_FAIL | yes | yes |
| g3-junit-malformed | no | INVALID | INVALID | INVALID | yes | yes |
| g4-exit-code-contradiction | no | BOUND_FAIL | BOUND_FAIL | BOUND_FAIL | yes | yes |
| h1-workflow-mismatch | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| h2-junit-summary-missing | no | UNBOUND | UNBOUND | UNBOUND | yes | yes |
| h3-below-min-tests | no | BOUND_FAIL | BOUND_FAIL | BOUND_FAIL | yes | yes |
| h4-missing-command | no | INVALID | INVALID | INVALID | yes | yes |
| n01-single-pr-head | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n02-two-job-pr-head | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n03-three-job-pr-head | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n04-single-merge-commit | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n05-two-job-merge-commit | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n06-single-event-sha | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n07-single-explicit-sha | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n08-lcov-only | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n09-skipped-still-pass | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n10-different-trees-allowed | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n11-different-attempts-allowed | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n12-min-tests-boundary | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n13-junit-plus-lcov | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n14-optional-fields-present | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n15-three-job-merge-commit | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |
| n16-py313-single | yes | BOUND_PASS | BOUND_PASS | BOUND_PASS | yes | yes |

## Failing fixtures

None — all 50 fixtures match Golden in both implementations.

## Notes

- Golden expected is hand-written (fixtures/s0/GOLDEN.json); it is never generated from production output.
- S0 FAIL = STOP: do not enter T005, do not lower thresholds, do not delete failing fixtures, do not rewrite Golden.
