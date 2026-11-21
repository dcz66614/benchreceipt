# REVIEW PACK FIXR1-01 — Capture (`02_source/src/benchreceipt/`, capture side)

- **Anchor:** `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`)
- **Pack:** 01 of 06. Files read in full at the anchor commit.
- **Verdict:** no P0/P1 in this pack. One P2 cross-ref: P2-27 (`command.py`
  docstring over-claim).

## Files

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/capture.py` | `6ba926dc391412e5b3cea5e2ffd5f61c11e2922d0785bfbb43c4a208349c5f25` | 674 | capture runner |
| `02_source/src/benchreceipt/git_identity.py` | `61f1a53fae80422cf3f6d3b1cb38ac5e9814c948868c85301f590efa2792542a` | 213 | git identity |
| `02_source/src/benchreceipt/ci_metadata.py` | `960ab6c537d39024e45ed213d17cef85d40eedb030876cbdeedc9e2daac0f0ac` | 196 | CI metadata |
| `02_source/src/benchreceipt/command.py` | `0fedd5aa4b7176e0abcf1d846e58237a30907ccff97dffe5c8dc864e7cebf276` | 289 | argv redaction |
| `02_source/src/benchreceipt/canonical.py` | `540d16a88e29e9ccbd1c3959c24b4c16b2a43505a48d8d8830030ae6fc147c88` | 50 | canonical JSON |

## What I checked

- **`capture.py` (674 lines).** Reads the full file. Capture always
  populates both `git.head_sha_after` / `git.tree_sha_after` from the
  post-run `git_after` snapshot (Scheme A: after = before by default,
  so a clean run records both). No code path omits them — the only
  no-after-field receipts in the repo are the e7/e8 fixtures, built
  by `build_fixtures.py` with `omit_after=True` (Pack 06). Dirty
  flags, `tracked_diff_sha256` before/after, and the
  `source_mutated_during_run` flag are computed from real git state;
  nothing is fabricated when git is unavailable (unavailable snapshots
  are `dirty=True` with no digest). The receipt's `git` block keys are
  exactly the `run.v1` allowed set (Oracle enforces the same key list,
  `verify.mjs:1007`).
- **`git_identity.py` (213, unchanged).** `_rev_parse` requires exactly
  40 lowercase hex; `determine_source_mode` branches all re-derived —
  every branch's expected SHA comes from CI metadata or the real HEAD,
  and every disagreeing branch fails closed at `verify`
  (`SOURCE_SHA_MISMATCH`). No change since T013; still sound.
- **`ci_metadata.py` (196, unchanged).** CI provider detection and
  run/attempt extraction unchanged; no new provider branches.
- **`command.py` (289, +61 lines).** The F-09 fix is present: widened
  `SECRET_HINTS` (lines 69–75: `token`, `password`, `secret`,
  `api-key`/`apikey`/`api_key`, `key`, `auth`, `passwd`, `pwd`,
  `passphrase`, `credential`, `private-key`/`private_key`) plus display
  truncation at 512 chars with digest over the full argv. **P2-27:**
  the comment at lines 63–67 claims the list "matches the names the
  project's own privacy scanner treats as secret
  (`SECRET_KEY_RE`) plus passphrase/credential" — in fact it is a
  superset (bare `key`/`passphrase`/`credential` are not matched by
  `SECRET_KEY_RE`, `privacy_scan.py:61–66`). Safe direction, comment
  only. Dead code re-confirmed (P2-17, carried): `_flag_name`
  (`command.py:102`) defined once, never called.
- **`canonical.py` (50, unchanged).** Sorted keys, compact separators,
  UTF-8, `allow_nan=False` — deterministic; the repeat-100 run in this
  review (1 hash `a19054f1…d530`) confirms it end to end.

## Re-runs touching this pack

- Offline install roundtrip (fresh venv from the new `dist.zip`
  wheel): clean-tree `capture` + `verify` → `BOUND_PASS`, jobs 1
  (`03_evidence/fix-r1-review/offline_install.log`). A dirty-tree
  attempt correctly yielded `SOURCE_MUTATED_DURING_RUN` (my first
  roundtrip used a dirty scratch repo with `require_clean_source_after`
  — the verifier behaved per spec; the roundtrip was redone clean).
- Reviewer wheel repro (real `capture` + `evaluate` from the installed
  wheel): originals `UNBOUND` + `SOURCE_MUTATED_DURING_RUN`; legacy
  shapes `UNBOUND` + `MISSING_FIELD`.

## Findings in this pack

- P2-27 (docstring over-claim, `command.py:63–67`) — see
  `REVIEW_FINDINGS_FIXR1.md`.
- P2-17 (dead code, carried) — `_flag_name` still uncalled.
