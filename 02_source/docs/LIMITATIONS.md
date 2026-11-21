# BenchReceipt Limitations (P027-T012, spec v1.2.0)

Read this before gating on a `BOUND_PASS`. BenchReceipt proves
**test-evidence binding to source identity** — that the reports
collected in a workspace belong to one declared source, one workflow
run/attempt, and the required matrix, with no report swapped, lost,
or mixed in from another run. It does **not** prove anything beyond
that. Every item below is a known, recorded boundary, not a hidden
gap. Severity scale: IMPLEMENTATION_PLAN §6.3 (P0 = false PASS;
P1 = blocking defect; P2 = non-blocking observation).

## 1. What a BOUND_PASS does NOT mean (honest boundaries)

- **Test-logic correctness.** A `BOUND_PASS` says the tests ran
  against the declared source and their reports are green and
  untampered. It says nothing about whether the tests themselves are
  correct, whether their assertions are strong enough, or whether the
  code under test is correct or vulnerability-free. A passing suite
  can still miss bugs.
- **Authenticity against a malicious runner.** Receipts are
  **unsigned SHA-256** bindings. SHA-256 detects accidental mixing,
  stale artifacts, and byte changes — it is not a signature. A
  compromised runner or a malicious workflow can forge a whole
  bundle, receipts and all. A `BOUND_PASS` must never be presented
  as a security attestation.
- **No SLSA / in-toto / Sigstore replacement.** BenchReceipt does
  not replace SLSA, in-toto/Sigstore, or GitHub Artifact
  Attestations. It can export an unsigned in-toto Statement aligned
  with the in-toto Test Result Predicate, but an unsigned file must
  never be presented as a security attestation. (PROJECT_BOOK §0.3,
  §2.2.)
- **No claim matching, flaky-test ranking, or coverage quality.**
  BenchReceipt does not compare PR prose to diffs, rank flaky
  tests, or judge coverage quality — only that the declared reports
  exist, parse, and hash-match.

## 2. P2-01 — Transient mutate-and-revert within one run is undetectable (observation)

Capture snapshots the source before and after the wrapped command
(`git rev-parse HEAD`, `HEAD^{tree}`, `git status --porcelain`,
tracked-diff digest; v1.1.0 / ADR-005 also records
`head_sha_after` / `tree_sha_after` so a clean-tree HEAD change
mid-run is caught). A command that modifies a tracked file and
**reverts it within the run** — dirty in the middle, clean before
and after — leaves identical before/after snapshots, so **no
before/after scheme can detect it**. This is a residual limitation
of snapshot-based mutation detection, not a defect in the
implementation, and it cannot be fixed without continuous
monitoring, which is out of scope. (PROJECT_BOOK §5.5 v1.2.0;
`03_evidence/privacy/SECURITY_FINDINGS.md` §P2-01.)

## 3. P2-02 — No byte cap on `receipt.json` itself (observation)

Schema-valid receipt *content* is bounded — every field has a max
length / max items, and oversized fields are `INVALID_RECEIPT`
(T011 probe (b): reports array > 32, job_id > 128 chars, matrix
> 32 entries, matrix key > 64 chars, report `size_bytes` > 1 GiB,
`command.display` > 512 chars are all rejected; sparse 1 GiB+1
JUnit/LCOV files are rejected by `stat` without being read).
But the receipt **file** has no byte cap: a 2 MB whitespace-padded
(otherwise valid) receipt parses and yields the correct
`BOUND_PASS`. A hostile multi-MB receipt is therefore parsed in
full before any verdict. The verdict is still correct — this is a
robustness / DoS note, not a false PASS. No test asserts a
rejection here; the probe test pins the current correct-verdict
behaviour. Consider a byte cap if the threat model grows to
untrusted receipt files at scale.
(`03_evidence/privacy/SECURITY_FINDINGS.md` §P2-02.)

## 4. P2-03 — `verify_bundle` does not enforce the documented manifest sort order (observation)

`BUNDLE_FORMAT.md` documents the bundle manifest
(`SHA256SUMS.txt`) as sorted by POSIX relative path, but
`verify_bundle` treats the manifest as a set of entries: a
manifest whose lines are **reordered alone still verifies**
(`ok=True`). Tampering is still detected — a flipped byte in a
reordered manifest is `BUNDLE_HASH_MISMATCH`, and CRLF endings,
duplicate lines, an extra blank line, a non-hex hash, a manifest
entry naming itself, a wrong hash / wrong size, a missing file, an
extra unlisted file, swapped hashes, and a renamed path are all
rejected. Order carries no security information, so this is a
format-strictness gap, not a security defect. The probe tests pin
both behaviours (reorder-alone verifies; reorder-plus-tamper is
still caught). Enforcing sort order is a one-line strictness
change if the format doc is to be treated as normative.
(`03_evidence/privacy/SECURITY_FINDINGS.md` §P2-03.)

## 5. P2-04 — A bare CR inside an LCOV `SF:` path is preserved verbatim (observation)

A bare carriage return inside an LCOV `SF:` path (not a CRLF line
ending — a CR *inside* the path text) is kept verbatim in the
parsed summary's `source_file` field rather than rejected:
`_validate_sf_path` rejects backslash / absolute / `..` paths but
not control characters. Harmless in practice:

- no LCOV summary field is stored in the receipt (the frozen
  `benchreceipt.run/v1` schema has no LCOV summary field — only
  the JUnit summary is recorded; see ADR-004), so the CR value
  never reaches a receipt;
- the SF path is never joined to the filesystem — only the parsed
  counts feed the verdict.

Pinned by
`test_lone_cr_in_lcov_sf_path_is_preserved_not_stripped` in
`02_source/tests/cross_platform/test_posix_boundaries.py`.

## 6. Observation — report artifacts are verbatim copies: a secret in test output stays in the artifact

A declared report artifact is copied **verbatim** into
`artifacts/` by design. A secret printed by the test itself into
its JUnit failure text (or an LCOV `SF:` path) therefore still
exists in the artifact file, even though the receipt
(`receipt.json`) is clean: secrets in argv are redacted to
`[REDACTED]` in `command.display`, secrets in the CI event JSON
never reach the receipt (only allowlisted fields are persisted),
a secret in JUnit failure text is counted but never stored, and a
secret-looking LCOV SF path is never stored (no LCOV summary
field exists). That is the test output's own content, not
something BenchReceipt adds, and the receipt never carries it.
**Do not print secrets into test output.** Treat artifacts with
the same care as the test logs they came from.
(T011 probe (d); `03_evidence/privacy/SECURITY_FINDINGS.md`.)

## 7. Platforms — Windows and macOS are NOT_TESTED

BenchReceipt is verified on **Ubuntu 24.04.5 / Python 3.12.3 /
Node v24.22.1 only**. Windows and macOS have **never been run**
— no such host was available — and no pass is claimed for them.
The CI example workflow includes `windows-latest` matrix cells
in its text, but they have not executed on real GitHub Actions
either.

What *is* pinned at the format level (so a future Windows/macOS
run has a defined boundary to test against) is in
`02_source/tests/cross_platform/test_posix_boundaries.py` (6/6
pass):

- JUnit/LCOV parsers accept CRLF input and produce the same
  summary as LF input;
- all writers emit LF only (receipt JSON, verification JSON,
  bundle manifest);
- bundle paths are POSIX-only; a backslash in a filename is
  rejected rather than silently accepted;
- a bare CR inside an LCOV `SF:` path is preserved verbatim
  (P2-04 above).

## 8. Other honest limits

- **LCOV summary.** The frozen `benchreceipt.run/v1` schema has
  no field for an LCOV summary, so `capture` does not emit one —
  only the JUnit summary is recorded (ADR-004). Adding an LCOV
  summary field is a spec decision for T013, not a capture change.
- **No real GitHub Actions run.** The example workflow
  (`examples/github-actions/ci.yml`) has not been run on real
  GitHub Actions — no real repository exists for this project yet.
  It is validated only by the synthetic/local checks in
  `02_source/tests/integration/test_github_actions.py` and
  `02_source/scripts/validate_workflow_example.py`.
- **Policy schema is closed.** Unknown policy fields are
  `INVALID_POLICY` — a typo'd key fails loudly instead of being
  silently ignored. This is deliberate fail-closed behaviour, but
  it means policy files must match the frozen schema exactly.
- **Receipts are local evidence, not a service.** BenchReceipt
  makes no network requests, calls no API, and needs no token.
  There is no server, no dashboard, and no remote verification —
  verification happens on the machine that holds the evidence.
