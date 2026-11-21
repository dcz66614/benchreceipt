# ADR-006 — FIX-R13a / F-10: add an explicit-SHA capture path; `explicit_sha` stays in the frozen enums

- **Date:** 2026-11-18
- **Task:** P027-FIX-R13a (T013 P1 F-10 — `explicit_sha` source mode unreachable from `capture`)
- **Status:** Accepted (spec decision already made by the task: add the capture path, not enum removal)
- **Spec change:** no — SPEC_VERSION stays 1.1.0. No schema or enum changes: `explicit_sha` is already in the frozen `source_mode` enums (`run.v1.json`, `policy.v1.json`) and in S0 fixture `n07-single-explicit-sha`. This ADR records a producer-path addition only.

## Context

T013 F-10 (full detail in `04_review/REVIEW_FINDINGS.md`, repro
`03_evidence/t013-review/repro5.py` R11): `determine_source_mode`
(`02_source/src/benchreceipt/capture.py`) returned only `pr_head` /
`merge_commit` / `event_sha`, and no CLI flag could produce
`explicit_sha`. A real local capture therefore emitted
`source_mode = "event_sha"`, and verifying that receipt against a
policy with `source_mode = "explicit_sha"` returned
`UNBOUND / SOURCE_MODE_MISMATCH` (jobs 0) — a documented mode no
producer could emit, i.e. a permanent false block for any user
following the docs into an `explicit_sha` policy. Fail-closed (never
a false pass), but a broken documented interface.

The fix direction in the review offered two options: (a) add an
explicit-SHA capture path, or (b) remove/document `explicit_sha` as
receipt-only (third-party producers). The FIX-R13a task decision is
(a): the mode is a real, useful binding — a run pinned to one exact
commit outside any PR/event context (e.g. a manually checked-out
release commit, or a non-GitHub runner with no CI metadata) — and
removing it from the frozen enums would be a spec change, while
adding the producer path is not.

## Decisions

1. **Capture path added, enum kept.** New CLI surface (also the
   programmatic API):
   `benchreceipt capture --source-mode explicit_sha --expected-sha <40-hex-sha> ...`
   - `capture.determine_source_mode(ci, head_sha, expected_sha=None)`:
     with a pinned SHA it returns `("explicit_sha", <pinned>)`.
   - `capture.capture(..., source_mode=None, expected_sha=None)` and
     the provisional capture CLI pass both through; `cli.py`'s §6.4
     contract line documents the optional flags.
   - Only `explicit_sha` is accepted as a pinned mode. Any other
     `source_mode` value, an `--expected-sha` without
     `--source-mode explicit_sha`, or an `explicit_sha` pin without a
     SHA raises `CaptureError` (CLI exit 4) — fail closed, no
     receipt written.
2. **The pin is validated, fail closed.** The pinned SHA must be
   exactly 40 lowercase hex characters, checked with
   `re.fullmatch` (not `re.match` + `$`, which accepts a trailing
   newline — the T013 P2-05 anchoring trap). A malformed pin raises
   `ValueError` in `determine_source_mode` and `CaptureError` in
   `capture()`. Uppercase, short/long, empty, whitespace-padded and
   non-string pins are all rejected (regression tests).
3. **The pin never rewrites reality.** The receipt's `git.head_sha`
   stays the real checked-out HEAD and `git.expected_source_sha`
   records the pinned SHA. A pin that differs from HEAD is therefore
   recorded honestly: verifying with the pinned SHA as the expected
   SHA fails `UNBOUND / SOURCE_SHA_MISMATCH` (the tests did not run
   on the pinned commit), while verifying with the real HEAD as the
   expected SHA passes — the pin selects the mode and records the
   operator's intent; it does not bless a commit the tests did not
   run on. This matches how the CI-derived modes already behave:
   `verify` judges `git.head_sha` against the caller's expected SHA
   and never compares the receipt's `expected_source_sha` field.
4. **No SPEC_VERSION bump, no MD/DOCX change.** Checked
   `01_spec/PROJECT_BOOK.md` and `01_spec/IMPLEMENTATION_PLAN.md`:
   PROJECT_BOOK §5.1 already lists all four modes including
   `explicit_sha`, and neither document claims capture cannot emit
   it or lacks the flag — the §6.4 CLI contract shows an example
   invocation, not an exhaustive flag list. The mode, the enums and
   the schemas are unchanged, so per IMPLEMENTATION_PLAN §11.5
   (spec changes bump SPEC_VERSION and sync MD/DOCX) there is
   nothing to bump or sync. This ADR alone records the decision.
   Follow-up note (not changed here): `02_source/docs/USER_GUIDE.md:239`
   shows an example policy comment listing only three modes
   (`pr_head` | `merge_commit` | `event_sha`); it omits `explicit_sha`
   without contradicting it, and is left for a T014 doc touch-up.

## Verification

- Repro5 R11 re-run: unchanged behaviour for the unpinned path
  (real local capture still emits `event_sha`); the new pinned path
  emits `explicit_sha` and verifies `BOUND_PASS` against an
  `explicit_sha` policy (see `03_evidence/fix-r13a/`).
- Regression tests: `determine_source_mode` pin/malformed-pin unit
  cases, capture end-to-end pinned → `BOUND_PASS`, wrong pin →
  `UNBOUND / SOURCE_SHA_MISMATCH`, bad pins → `CaptureError`,
  CLI `--source-mode explicit_sha --expected-sha <HEAD>` → exit 0
  with `explicit_sha` in the receipt, bad CLI pins → exit 4, no
  receipt (`02_source/tests/capture/test_capture.py`,
  `02_source/tests/cli/test_cli.py`).
- Full suite, S0 gate, Oracle tests, privacy scan and workflow
  validator all re-run green (see `03_evidence/fix-r13a/`).
