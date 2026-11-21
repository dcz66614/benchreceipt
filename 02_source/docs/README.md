# BenchReceipt docs (P027-T012, spec v1.2.0)

- [`USER_GUIDE.md`](USER_GUIDE.md) — install, capture, verify,
  report, bundle, the CI example, policy reference,
  troubleshooting, performance and offline notes.
- [`LIMITATIONS.md`](LIMITATIONS.md) — what a `BOUND_PASS` does
  **not** mean, the recorded P2 observations (P2-01 transient
  mutate-and-revert, P2-02 no receipt byte cap, P2-03 unenforced
  manifest sort order, P2-04 bare CR in an LCOV `SF:` path), the
  verbatim-artifact secret observation, and the NOT_TESTED
  platforms. Read it before gating on a verdict.
- [`BUNDLE_FORMAT.md`](BUNDLE_FORMAT.md) — bundle + manifest
  format (`SHA256SUMS.txt`).
- [`REASON_CODES.md`](REASON_CODES.md) — every reason code.

Authoritative requirements are the frozen specs in
`../../01_spec/` (PROJECT_BOOK.md v1.2.0,
IMPLEMENTATION_PLAN.md v1.2.0). The verified quickstart is in
[`../README.md`](../README.md).

Status: VERIFIED (T012 resume) — full suite green, S0 gate PASS
10/10, Oracle 8/8, privacy scan 0 findings; see
`../../03_evidence/t012/T012_SUMMARY.md`.
