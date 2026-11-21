# P027 BenchReceipt — Completion Notice

**Date:** 2026-11-18
**Status:** ACCEPTED — GPT final review R2 FINAL_VERDICT: PASS

## Project summary

BenchReceipt (P027, 测证收据) is a CI test/benchmark-run evidence receipt
system: it proves which code version, which CI run, which matrix job, and
which actual test report a test result belongs to. Receipt states are
BOUND_PASS / BOUND_FAIL / UNBOUND / INVALID / INTERNAL_ERROR (exit 0/1/2/3/4);
machine-readable JSON + standalone HTML evidence chain. It proves
test-evidence binding to source identity, NOT test-logic correctness,
assertion strength, or absence of bugs. Receipts are unsigned SHA-256 (not
an authenticity claim against a malicious runner); it does not replace
SLSA / in-toto / Sigstore / GitHub Artifact Attestations.

- Spec: v1.2.0 (VERIFIED)
- Licence: MIT
- Human participants: zero
- Budget: 88h
- Work directory: `~/workspace/p027-benchreceipt/` (git HEAD b71c42b at time
  of writing; freeze 2b1ba19)

## Freeze identity

- Final freeze commit: **2b1ba19** (full:
  2b1ba19f7f461e2fc9acbf3c7c392d2d21edbd09)
- Release commit: 213677f0df7cfda427a3ef6d5558ffecadd91d26
- source.zip: **355 files, 433,074 B, 1,160,832 source bytes**
  - SHA-256: `15d1dd0bcfd217cc060ba1501c9205c9aa2fde9300c5734077867b664cac54af`
- dist.zip: **152,880 B** (wheel benchreceipt-0.1.0-py3-none-any.whl)
  - SHA-256: `eb73174ab6e51069d2565ebd793d91369b772c33115cf2ba91926bd21b2b48b1`
- bundle: `benchreceipt-2b1ba19f7f46.bundle`, **4,622,659 B**
  - SHA-256: `79faf42ab7b5d9487cea9bdec8b24f69b56c4dc3ef0c74dd9a5b7d016f5474b1`
- SHA256SUMS.txt: 5/5 OK; 4 builds, same hash

## Gate results

- Full pytest suite: **848/848**
- S0 acceptance: **52/52** (16 normal controls + 36 planted faults incl.
  e5/e6 clean-tree HEAD change and empty-commit mid-run, e7/e8 legacy-shape
  regressions), production/Oracle parity 52/52, False PASS 0, False block 0
- S0 `--repeat 100`: PASS, 100 replays, 1 hash
  `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530`
- Oracle self-test: 26/26; parity corpus 69 passed; P95 0.091s
- verify_release: PASS; verify_review_pack (anchor 2b1ba19): PASS
  (43 index rows, 37 pack rows, 34 key files, SHA + line counts match)

## Final review R2 verdict

- **FINAL_VERDICT: PASS** — received 2026-11-18 ~05:24 GMT
- Reviewer: GPT-6 + Extra High (thinking 极高), 16m02s
- Findings: P0 = 0, P1 = 0, BLOCKERS: NONE
- R1 (2026-11-18 ~03:25 GMT) was FAIL (P0 1 / P1 1 / P2 22). All three R1
  blockers CLOSED in FIX-R1:
  - P0-R1-01 legacy receipts without after-fields returned BOUND_PASS →
    fail-closed (both after-fields missing → UNBOUND + MISSING_FIELD,
    jobs_verified 0, exit 2; production verifier + Node Oracle synced;
    spec v1.2.0, ADR-007 overturns ADR-005 decision 4); e7/e8 regressions
    added; reviewer's own repro script 2/2 on source + 2/2 on offline
    wheel install; single-field deletion still UNBOUND +
    SOURCE_MUTATED_DURING_RUN (not a brittle special case).
  - P1-R1-01 T013 review pack anchored to the wrong commit → fresh
    independent review pack anchored to 2b1ba19, FINAL_VERDICT: PASS
    (0 P0 / 0 P1), verify_review_pack PASS, coverage 34/34.
  - P2-R1-01 Drive 05_release missing zero-byte .gitkeep → present
    (0 bytes, MD5 d41d8cd9…).
- GPT conversation:
  https://chatgpt.com/g/g-p-6ade5013e8ec8191b55dca46c27772e1-agent-project-automatic/c/6afbec98-1048-83eb-a0af-113cf330b077
- Full R2 reply archived in this folder as `GPT_FINAL_REVIEW_R2.md`
  (local source: `~/workspace/P027_FINAL_REVIEW_R2.md`).

## PASS scope (strict)

This PASS covers engineering fixes + offline acceptance on 52 frozen
synthetic fixtures + delivery integrity ONLY. It does NOT establish:

- test-logic correctness, assertion strength, or absence of bugs;
- authenticity of a receipt against a malicious runner (receipts are
  unsigned SHA-256);
- replacement for SLSA / in-toto / Sigstore / GitHub Artifact Attestations;
- Windows/macOS compatibility beyond the frozen Linux/Node test runs.

## Carried items (all non-blocking)

- **Active P2 = 29**: carried P2-01–P2-21 + new P2-22–P2-27, P2-29, P2-30.
  New P2s: P2-22 schemas README duplicate paragraph; P2-23 policy schema
  v1.0.0 description residue; P2-24 verify.py comment still says 48
  fixtures; P2-25 bundle.py comment still says 48-job; P2-26 HTML
  explanation of MISSING_FIELD does not cover after-identity; P2-27
  SECRET_HINTS docstring slightly overstates; P2-29 GitHub Actions comment
  still references T013; P2-30 ZIP excluded by .gitignore, Git tracks only
  its hash (release-process observation).
- **P2-28 CLOSED in R2**: verify_review_pack.py now includes the new schema
  path and supports it.
- **Document residue (non-blocking)**: REVIEW_FINDINGS_FIXR1.md still
  carries historical 66502f6 anchor text in its opening and conclusion
  ("this pack is anchored to 66502f6"); the machine-checkable index
  REVIEW_INDEX_FIXR1.md is anchored to 2b1ba19 and the validator passes.
  Cleanup is optional follow-up, not rework.
- **Evidence note**: GPT did not re-run the full 848 pytest itself in R2
  (environment/time window); the frozen-VM pytest log was accepted as
  evidence alongside GPT's own re-runs (S0 52/52, Oracle 26/26, parity 69,
  P0专项, wheel verification, verify_release PASS).

## Drive evidence

- Project folder `P027-benchreceipt`:
  `1qUj7ViaJm8YGU0nvmqYKk6zQyscUlQBY`
- 05_release (7 files, incl. zero-byte .gitkeep):
  `1a5miS35a7Y5OPfaVVQaeB5wIxWvaFmex`
- 04_review (incl. FIXR1 pack, 9 files):
  `1L7O1oq-LlVsNA2puGOJJPLeFOeQSXZSj`
- 03_evidence (incl. r1-repro, the reviewer's R1 repro pack):
  `1099gZaLBw2UQX8_PcNFes5gOELaQmRFL`
- Closure subfolder `CLOSURE_2026-11-18_R2_PASS` (this notice + R2 verdict):
  `1XbXaaWTVTcGutdlCCh945Kbl1ug6-zmw`

## GitHub upload

GitHub upload (private, MIT) — in progress at time of writing; repository
name `benchreceipt`. URL and head commit to be filled in once the upload
completes.
