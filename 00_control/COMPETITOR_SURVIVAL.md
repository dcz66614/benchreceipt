# P027 BenchReceipt — Competitor Survival Gate (T001)

**Checked:** 2026-11-17, by live web search in this session (searches run
~07:10–07:20 GMT). Scope: tools that do exactly **multi-job same
run/attempt + commit/tree + artifact digest binding for CI test evidence** —
i.e. all of the following at once:

1. **Multi-job binding** — aggregate several CI jobs and check they belong
   to the same workflow run *and* the same attempt.
2. **Source identity** — commit SHA *and* tree SHA, with an explicit
   PR-head vs merge-commit distinction.
3. **Artifact digest binding** — JUnit/LCOV (or equivalent) report bytes
   re-hashed and matched to the receipt.
4. **Required-matrix policy** — a declared expected job set, with
   missing / duplicate / unexpected jobs detected.
5. **Local + offline** — no signing service, no GitHub API token, no
   hosted dashboard required to verify.
6. **Actively maintained** — a live project, not an abandoned prototype.

A tool is a *fully equivalent competitor* only if it meets **all six**.
Meeting one or two is adjacency, not equivalence. If any tool had met all
six, the verdict below would be STOP.

## Comparison table

| Tool | What it covers | Meets | Why NOT fully equivalent |
|---|---|---|---|
| GitHub Artifact Attestations (`actions/attest`) | Signed in-toto provenance binding an artifact digest to the workflow identity that produced it (Sigstore keyless signing) | (3) partial, (6) | Per-artifact provenance, not per-test-run evidence: no JUnit/LCOV parsing, no required-matrix completeness check, no run/attempt cross-job aggregation, no PR head/merge distinction, no tree SHA. Needs GitHub + Sigstore; private repos need Enterprise Cloud. It is a *stronger* primitive for authenticity and a *weaker* one for multi-job test-evidence aggregation — BenchReceipt explicitly does not replace it. |
| in-toto Test Result Predicate | Standard schema for test results: subject, configuration, result, test names | (3) schema only | A **format**, not a tool: defines what a test-result attestation looks like, but implements no capture, no matrix policy, no verifier, no run/attempt binding. BenchReceipt plans to *export* an unsigned Statement aligned with it (PROJECT_BOOK §0.3), not compete with it. |
| `attested` by Praxso (v0.1, early) | **Closest neighbour found.** Wraps a Playwright (or any CTRF-report) run into an in-toto Statement receipt: result, failing tests, commit, sha256 of every trace/video/screenshot; signed via `actions/attest`; a required check fails closed unless a signed receipt exists for the PR head | (2) partial (commit, not tree; PR head only), (3) partial (CTRF, not JUnit/LCOV), (6) new | Single-run / single-report receipt, not multi-job: no required-matrix policy, no missing/duplicate/unexpected job detection, no run-ID/attempt cross-job check, no tree SHA, no JUnit/LCOV parsing, no offline local verify (verification is `gh attestation verify` against GitHub + Sigstore). Playwright/CTRF-centric; status "0.1, early" (launched 2026-11-02). |
| `Uncle` (unclehq/uncle) | Binds AI-agent workflow evidence (test results, human approvals) to an exact Git tree hash; in-toto Statement v1; Bash/Python driver that tracks real exit codes per stage | (2) (tree hash), (6)? new | Per-stage driver with human approval gates, not a CI multi-job aggregator: no run/attempt binding, no matrix completeness policy, no JUnit/LCOV report-digest binding, no offline multi-job `verify` CLI. Its problem is "was this tree reviewed/approved", not "do these N green reports belong to one run". |
| `proofcheck` | Checks whether a PR does what it claims: runs the PR's tests before/after the change, replays the linked issue reproducer, matches PR-description claims to measured evidence (fail→pass) | (2) partial (base/head commits), (6) | PR **claim-vs-diff** verification, not evidence binding: it proves a claim was tested, not that N reports from N jobs belong to one run/attempt/matrix. No receipt aggregation, no attempt check, no report-digest binding, no required-matrix policy. Already ruled out for C02 in PROJECT_BOOK §3.1. |
| `trustbut` (v0.7.0) | Reruns tests in a clean git worktree; every new/changed test also runs against pre-change code (fail-before/pass-after); flags skips/focus/deleted tests; PASS/WARN/FAIL receipt; local, deterministic, 11 languages | (5), (6) | Test-**meaning** verification (does the test prove the change?), not test-**evidence** binding. Single local run, no CI jobs at all: no run/attempt, no matrix policy, no artifact-digest aggregation across jobs. Complementary, not equivalent. |
| `Proof` (EricFinland/proof) | Verifies agent completion claims against tests and diff (per PROJECT_BOOK §14 reference) | (2) partial | Agent completion-claim verification / Stop-hook style tooling: checks what an agent claims it did, not whether multi-job CI reports share one run/attempt/commit/tree. No matrix policy, no report-digest binding. (Repo page not re-fetched this session; assessed from the spec reference and its described scope.) |
| `Vigil` (name ambiguous) | Several unrelated projects share the name: `vigil-ai-cli` (PyPI) is a static scanner for AI-generated code (hallucinated deps, placeholder secrets, empty test theatre); `VIGIL` papers are LLM-agent verify-before-commit / self-healing runtimes | — | No single canonical "Vigil" does CI test-evidence binding. The scanner checks code patterns, not run identity; the papers are research runtimes, not a maintained CI verifier. None meets (1)–(5). |
| BuildPulse | Cloud flaky-test detection/history/ranking/quarantine from ingested JUnit XML; CI & test-health dashboard | (3) partial (ingests JUnit) | A hosted **flaky analytics** service, not a binding verifier: no commit/tree/run/attempt identity checks, no matrix completeness gate, no offline local verify, requires uploading results to its cloud. Already ruled out for C04 in PROJECT_BOOK §3.1. |
| Currents | Cloud Playwright/Cypress dashboard: collects results from distributed shards, traces, flakiness analytics | (1) partial (collects shards) | A hosted **test-reporting dashboard**: aggregates runs for display and flake analysis, but does not verify that shards share one commit/tree/run/attempt against a required-matrix policy, does not bind report digests to receipts, and is not local/offline. |
| TestifySec `cilock` (git attestor) | Captures git state (HEAD, tree hash, dirtiness) as an in-toto-style attestation; part of a supply-chain attestation platform | (2) partial | One attestor inside a **hosted platform** (defaults to the TestifySec platform): records git state for a single run, but does not aggregate multi-job test evidence, check run/attempt, parse JUnit/LCOV, or enforce a required-matrix policy locally. |

### Also examined, not equivalent (single-line)

- **BootProof** (`bootproof/bootproof`) — signed receipts that an app
  actually booted and answered HTTP; boot evidence, not CI test matrices.
- **aetherproof** — signed receipts for AI model outputs (model-weight /
  output hashes); no CI, no jobs, no reports.
- **attest-receipts** — signed purchase receipts (offline verifiable);
  unrelated domain.
- **TookEffect** — verifies an agent's claimed *external* effect
  (GitHub/Vercel/Cloudflare state) after the fact; no CI test-evidence
  binding.

## The closest call, examined honestly

**`attested` (Praxso)** is the nearest thing to BenchReceipt in the
world as of 2026-11-17: same one-sentence pitch ("a receipt proves the
commit's own tests reported the result"), same in-toto Statement shape,
same fail-closed required check. It is also **two weeks old** (Product
Hunt launch 2026-11-02, status 0.1 early) and differs on every point
that defines BenchReceipt's scope:

- one run / one CTRF report per receipt — no multi-job matrix, no
  required-jobs policy, no missing/duplicate/unexpected detection;
- binds the PR head commit, not the tree, and does not distinguish
  run attempts across jobs;
- verification depends on GitHub Attestations + Sigstore (`gh attestation
  verify`), i.e. exactly the hosted signing infrastructure BenchReceipt
  deliberately avoids (unsigned, local, offline);
- Playwright/CTRF only — no JUnit/LCOV, no generic command wrapping.

If `attested` later adds multi-job matrix aggregation with run/attempt
checks and an offline verifier, that would be a re-establishment trigger
and must be re-checked at T013. As of today it does not, so it does not
block this project. The same re-check applies to `Uncle` if it grows a
multi-job CI aggregator.

## Verdict

# **PASS — no direct equivalent found. Proceed to T002.**

No actively-maintained tool found in this session meets all six
equivalence criteria (multi-job same run/attempt + commit/tree +
artifact-digest binding + required-matrix policy + local/offline).
The nearest neighbours (`attested`, `Uncle`, GitHub Artifact
Attestations, in-toto Test Result Predicate) each cover a *different
slice* — signed single-run receipts, tree-hash approval gates, signed
provenance, or a standard format — and none aggregates multi-matrix CI
test evidence locally and offline. BenchReceipt's stated non-goals
(no signatures, no SLSA replacement) are consistent with this gap:
it occupies the lightweight unsigned-consistency-check niche, not the
signed-provenance niche.

**Caveats recorded for T013 re-check:** (1) `attested` is new
(2026-11-02) and fast-moving — re-search before final review;
(2) `Proof`'s repo page was not re-fetched this session (assessed from
the PROJECT_BOOK §14 reference); (3) web search is not an exhaustive
market survey — absence of evidence here is a gate result, not a
market-size claim (cf. PROJECT_BOOK §1.3, `USER_VALUE_NOT_MEASURED`).

## Sources (URLs as returned by search / cited in the frozen spec)

- GitHub Artifact Attestations (docs):
  https://docs.github.com/en/actions/concepts/security/artifact-attestations
- in-toto Test Result Predicate:
  https://github.com/in-toto/attestation/blob/main/spec/predicates/test-result.md
- `attested` by Praxso — repo: https://github.com/Praxso/attested ;
  Product Hunt: https://www.producthunt.com/products/attested ;
  overview: http://glama.ai/mcp/servers/Praxso/attested
- `Uncle` — write-up:
  https://blogs.techbytes.app/posts/an-ai-agent-said-the-code-was-verified-the-evidence/
  (repo named in the article: github.com/unclehq/uncle)
- `proofcheck` — Marketplace:
  https://github.com/marketplace/actions/proofcheck-pr-evidence ;
  PyPI: https://pypi.org/project/proofcheck-ai/
- `trustbut` — repo (PROJECT_BOOK §14):
  https://github.com/isAlmogK/trustbut ;
  write-up: https://almog.io/writing/ai-agents-faking-tests-201-merged-prs
- `Proof` — repo (PROJECT_BOOK §14): https://github.com/EricFinland/proof
- `Vigil` scanner — PyPI: https://pypi.org/project/vigil-ai-cli/0.7.0/
- BuildPulse — flaky tests: https://buildpulse.io/products/flaky-tests ;
  docs: https://docs.buildpulse.io/flaky-tests/overview
- Currents — Playwright dashboard: https://currents.dev/playwright
- TestifySec `cilock` git attestor:
  https://www.testifysec.com/docs/cilock/attestors/git/
- BootProof: https://github.com/bootproof/bootproof
- in-toto attestation framework overview:
  https://softwsp.com/guides/in-toto-attestation-framework/
