# REVIEW PACK FIXR1-03 — Bundle / render / CLI (`02_source/src/benchreceipt/`)

- **Anchor:** `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`)
- **Pack:** 03 of 06. Files read in full at the anchor commit.
- **Verdict:** no P0/P1 in this pack. Two P2 cross-refs: P2-25
  (`bundle.py` comment), P2-26 (`render/html.py` text).

## Files

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/bundle.py` | `ce557f6f4ca79497be3b66ce4196ce9c7bae5b7036dc68327cabe118d0af0168` | 788 | bundle build/verify |
| `02_source/src/benchreceipt/render/html.py` | `66704da5fad44da9d15d4edef7a5580446926e1d9f92f0e50b5259ec2c9fcf63` | 693 | HTML report renderer |
| `02_source/src/benchreceipt/cli.py` | `51fb6c3189ad8bc8776ce8fe4014984df5eb7e4425e01042d115f2f5ce1752a7` | 381 | CLI entry |
| `02_source/src/benchreceipt/__main__.py` | `30819d5b2ec5058171bac68f863dfb03f1d6b8858116dcca4d2eb15ea08bb278` | 13 | module entry |
| `02_source/src/benchreceipt/__init__.py` | `1b7920a55ec70c3c210a5b3e760054d810774d0b8d452ff59873545aba7cae44` | 10 | package init |
| `02_source/src/benchreceipt/render/__init__.py` | `ddec99272b71a4193baecf2c0422118733cc3dc63e27cefa6a2895aad603489d` | 5 | render package init |
| `02_source/src/benchreceipt/reports/__init__.py` | `73c8c07bffb35e8d59420d00de6911bdaf94bff086c337bf299d630daba03527` | 10 | reports package init |

## What I checked

- **`bundle.py` (788, unchanged).** Bundle build / manifest /
  `verify_bundle` unchanged since T013. Manifest entries are re-hashed
  after copy; `verify` recomputes from disk and never trusts stored
  digests; path containment (`_validate_rel_posix`,
  `_is_within_root` resolving) and symlink refusal at build and at
  verify are intact; manifest parsing treats CR / duplicates /
  self-listing / unsafe paths as problems, never silent. **P2-25:**
  the comment at line 103 still says "48-job S0 bundles" — the set
  is 52. Comment only. Carried: P2-12 (`build_bundle` cleanup only
  on `BundleError`).
- **`render/html.py` (693, unchanged).** Every interpolated value
  passes through `html.escape(…, quote=True)` (verified by reading
  all render functions); no external resource references; no argv /
  secret / absolute-path leakage into reports. **P2-26:**
  `REASON_MEANINGS["MISSING_FIELD"]` (line 102) mentions only the
  JUnit-summary example, not the after-identity case that the
  P0-R1-01 fix made the more common trigger. Display text only.
- **`cli.py` (381, +1 line).** `capture` / `verify` / `bundle` /
  `render` subcommands; exit-code contract intact (verify: 0
  `BOUND_PASS`, 1 `BOUND_FAIL`, 2 `UNBOUND`, 3 `INVALID`, 4
  `INTERNAL_ERROR`) — confirmed by my re-runs (legacy repro exit 2;
  offline roundtrip exit 0). Argument names verified against
  `--help`: `capture --job … --matrix K=V,… --junit …` (note: `--job`,
  not `--job-id` — my first roundtrip attempt used the wrong flag and
  the CLI rejected it with a clear usage error).
- **`__main__.py` (13), `render/__init__.py` (5),
  `reports/__init__.py` (10), `__init__.py` (10).** Thin entry
  points / re-exports. **P2-17 (carried):** `__init__.py` docstring
  still says "Skeleton placeholder… NOT_VERIFIED until S0 passes"
  although S0 passes (10/10, re-run in this review).

## Re-runs touching this pack

- `ui_smoke.py`: PASS — 3 reports rendered, 0 external refs
  (screenshots NOT_TESTED, no browser on this VM).
- `verify_release.py` on a scratch worktree at `b221401`: PASS —
  "source.zip matches the frozen tree file-by-file, manifest +
  SHA256SUMS verified, LICENSE MIT in both zips, deps == 0, S0 52/52
  + repeat-100 1 hash, bundle clones, offline install checked".

## Findings in this pack

- P2-25 (`bundle.py:103`), P2-26 (`render/html.py:102`) — see
  `REVIEW_FINDINGS_FIXR1.md`.
- Carried: P2-12, P2-17.
