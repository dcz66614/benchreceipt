# P027 BenchReceipt — FIX-R1 Independent Review Findings

- **Anchor commit:** `66502f6255976b44b3efebb7da778ea8807b1ba1` (branch `fix-r1-review`)
- **Frozen tree:** `02_source` = 355 files; release commit `b221401`
- **Spec version:** 1.2.0 (ADR-007)
- **Reviewer role:** independent, review-only; did not write the fix code.
- **Coverage:** 34/34 key files read in full at `66502f6` (+ 3 Key=no files read; 37/37 inventory rows).
- **Counts: P0 = 0, P1 = 0, P2 = 9 new** (P2-22–P2-30) plus carried P2-01–P2-21 (see §Carried).
- **Verdict: PASS** — 0 P0 / 0 P1. R1's P0-R1-01 and P1-R1-01 are both CLOSED (evidence below).

---

# R1 blockers — closure

## P0-R1-01 — CLOSED: legacy receipts without both after fields now fail closed

R1: receipts with both optional after fields (`git.head_sha_after` /
`git.tree_sha_after`) deleted still verified `BOUND_PASS` (ADR-005
decision 4 compat fallback to dirty/digest checks). FIX-R1 (ADR-007)
overturns that fallback: both-after-absent is `UNBOUND` + `MISSING_FIELD`.

Independent re-runs by this reviewer, all on frozen source `66502f6`:

1. **Fixture repro (my own script,
   `03_evidence/fix-r1-review/p0_fixture_repro.py`):** e5
   (`e5-clean-tree-head-change`) and e6 (`e6-empty-commit-mid-run`),
   orig + legacy × Python CLI + Node Oracle = 8/8 cells as expected.
   Orig: `UNBOUND` + `SOURCE_MUTATED_DURING_RUN`, jobs 0, exit 2.
   Legacy (both after fields deleted, nothing else touched, still
   `run.v1`-schema-valid): `UNBOUND` + `MISSING_FIELD`, jobs 0, exit 2,
   report error exactly `missing git.head_sha_after and
   git.tree_sha_after`. Log:
   `03_evidence/fix-r1-review/p0-fixture-repro.run.log`.
2. **Reviewer wheel repro (original R1 script,
   `03_evidence/r1-repro/independent_p0_wheel_repro.py`)** run against a
   fresh venv installed from the NEW `dist.zip` wheel: case 1
   (`clean_checkout`) printed legacy `UNBOUND` + `MISSING_FIELD`,
   jobs 0, schema-valid — then the script's final assertion failed by
   design (it asserts the OLD `BOUND_PASS` expectation). Log:
   `03_evidence/fix-r1-review/wheel_repro_original_script.log`.
3. **Post-fix wheel repro (`03_evidence/fix-r1/post_fix_wheel_repro.py`,
   same probe, flipped assertions):** 2/2 cases `UNBOUND` +
   `MISSING_FIELD`, jobs 0; originals still `UNBOUND` +
   `SOURCE_MUTATED_DURING_RUN`. Exit 0. Log:
   `03_evidence/fix-r1-review/wheel_repro_postfix.log`.
4. **Code identity:** `verify.py` §5.5 (lines ~536–586) and
   `oracle/verify.mjs` (lines ~1444–1475) implement the same rule:
   both-after-absent → `MISSING_FIELD` + report error, `job_ok=False`
   (UNBOUND via `REASON_STATUS`: `verify.py:106`,
   `verify.mjs:55`); one-field-present with a differing value, or
   `dirty_after != dirty_before`, or `require_clean_source_after` with
   `dirty_after=True`, is a mutation (`SOURCE_MUTATED_DURING_RUN`).
   Message template is byte-identical in both implementations
   (`verify.py:560`, `verify.mjs:1463`):
   `missing git.head_sha_after and git.tree_sha_after`, and matches
   `docs/REASON_CODES.md:70` and the e7/e8 Golden entries.
   Spot check (this reviewer): deleting only `tree_sha_after` from e5
   still yields `UNBOUND` + `SOURCE_MUTATED_DURING_RUN` in both
   implementations — the one-field rule is unchanged.
5. **Fixtures + Golden:** 52 fixtures inventoried; e7
   (`e7-legacy-clean-checkout`) and e8 (`e8-legacy-empty-commit`)
   receipts contain neither after field; Golden gives both `UNBOUND` +
   `MISSING_FIELD`, jobs 0. e5/e6 Golden stay `UNBOUND` +
   `SOURCE_MUTATED_DURING_RUN`. 16 controls `BOUND_PASS`, 36 faults
   detected (S0 16/16 + 36/36 re-run, see below).
6. **Spec coherence:** `run.v1.json` keeps the after fields optional;
   only the descriptions changed to the ADR-007 fail-closed wording.
   `PROJECT_BOOK.md` §5.5 states the fail-closed rule and that ADR-005
   decision 4 is overturned; ADR-007
   (`00_control/ADR/ADR-007-fix-r1-legacy-after-fail-closed.md`)
   carries the n01/e7 indistinguishability proof and the rejected
   alternatives. `capture.py` always emits both after fields, so
   Scheme A (after = before by default) is the only production path
   that creates them; `build_fixtures.py` `omit_after=True` is the
   only no-after-field path and is used only by e7/e8.

## P1-R1-01 — CLOSED: review pack re-anchored to the freeze

R1: the T013 pack anchored `cfede271`, while the freeze was `a07dc79`
(19/34 identical, 12 changed, 3 schema files migrated). This pack
anchors `66502f6` at its head (see `REVIEW_INDEX_FIXR1.md`): all 37
inventory rows were compared against `66502f6` by SHA-256
(`03_evidence/fix-r1-review/inventory_table.md`): 21 UNCHANGED, 14
CHANGED, 2 MOVED+CHANGED (schema files; `policy.v1.json` and
`result.v1.json` byte-identical after the move, only `run.v1.json`
changed). All 3 schema files verified at their new paths under
`02_source/src/benchreceipt/schemas/`.

## T013 P1 findings F-01–F-10 — all fixed in the code read

- **F-01** every JUnit report judged (not only the last) — `verify.py`
  FIX-R13a block judges each parsed report in receipt order.
- **F-02** Oracle parses LCOV — `oracle/verify.mjs` now contains a
  full LCOV parser (the file grew 702 → 1823 lines in FIX-R13b).
- **F-03** Oracle checks JUnit count attributes.
- **F-04** hand-written XML parser (no dependency on a lenient parser).
- **F-05** symlink-resolving containment (`_is_within_root`).
- **F-06** schema validation on load (`run.v1` / `result.v1` /
  `policy.v1`).
- **F-07** TOML duplicate-key rejection.
- **F-08** run pins (`--expected-run-id` / `--expected-attempt`)
  enforced; Oracle F-08 test passes.
- **F-09** widened `SECRET_HINTS` + path shortening in `command.py`
  (see P2-27 for a docstring over-claim that remains).
- **F-10** `explicit_sha` capture (`--source-mode explicit_sha` /
  `--expected-sha`, ADR-006).

No P0 or P1 remains. The two R1 blockers are closed and every T013 P1
is fixed; the review proceeds to P2 only.

---

# P2 findings (non-blocking observations)

## P2-22 — `schemas/README.md` duplicates its opening paragraph

`02_source/src/benchreceipt/schemas/README.md:3–8` and `:10–11` both
start "Three JSON Schemas (draft 2020-12), frozen by T002. They are the
contract T003+ builds on…". The second copy drops the v1.1.0 amendment
sentence, so a reader stopping at the second paragraph misses that
ADR-005 added the two optional after fields. Docs only; the schemas
themselves are correct.

## P2-23 — `policy.v1.json` `schema_version` description is stale

`02_source/src/benchreceipt/schemas/policy.v1.json` (single-line file):
`"schema_version": {"const": 1, "description": "Policy format
version. Only 1 is valid for spec v1.0.0."}` — the spec is now v1.2.0.
The `const: 1` itself is correct; only the description's version is
stale. Same class as P2-24/P2-25/P2-29 (stale version pointers left by
the v1.2.0 bump).

## P2-24 — `verify.py:874` comment still says "48 S0 fixtures"

`02_source/src/benchreceipt/verify.py:874`: `# unreachable for the 48
S0 fixtures (covered by tests).` The S0 set is 52 fixtures since FIX-R1
(e7/e8 added). Comment only; the code path is unchanged.

## P2-25 — `bundle.py:103` comment still says "48-job S0 bundles"

`02_source/src/benchreceipt/bundle.py:103`: `# hits them (48-job S0
bundles are ~tens of files), tight enough to…`. Same stale count as
P2-24 (52 now). Comment only.

## P2-26 — HTML `REASON_MEANINGS` for `MISSING_FIELD` mentions only the JUnit case

`02_source/src/benchreceipt/render/html.py:102`:
`"MISSING_FIELD": ("UNBOUND", "A field the policy requires is absent,
although the schema allows it to be optional (e.g. the JUnit
summary).")` — the after-identity case (the P0-R1-01 fix, now the
more common trigger) is not mentioned, while `docs/REASON_CODES.md:39`
covers both. A user reading only the HTML report sees the JUnit
example and may misread an after-identity `MISSING_FIELD`. Display
text only.

## P2-27 — `command.py` docstring over-claims the SECRET_HINTS / privacy-scanner match

`02_source/src/benchreceipt/command.py:63–67` (FIX-R13a F-09 comment):
"The widened list matches the names the project's own privacy scanner
treats as secret (scripts/privacy_scan.py SECRET_KEY_RE) plus
passphrase/credential." In fact `SECRET_HINTS` (`command.py:69–75`) is
a superset: bare `"key"`, `"passphrase"`, `"credential"`, `"auth"`,
`"pwd"` are hints, but `SECRET_KEY_RE`
(`02_source/scripts/privacy_scan.py:61–66`) only matches those tokens
as parts of longer suffixed keys (`…token`, `…secret`, `…key$`) and
does not match bare `"key"` / `"passphrase"` / `"credential"` at all.
The direction is safe (capture redacts more than the scanner flags),
but the comment's "matches … plus passphrase/credential" understates
the gap: the scanner would NOT flag a JSON key literally named `key`
or `passphrase` holding a secret. Docs/comment only; no leak observed
(privacy scan: 193 files, 0 findings).

## P2-28 — Review-pack validators are anchored to the old index and old schema path

`02_source/scripts/verify_review_pack.py:109–118` `_is_key_production`
matches only `02_source/schemas/*.json`, so it does not cover the 3
schema JSONs at their new location
`02_source/src/benchreceipt/schemas/*.json`; and both
`verify_review_pack.py` (glob `REVIEW_PACK_*.md`, index read at
`04_review/REVIEW_INDEX.md`) and `check_review_coverage.py:71`
validate against the T013 index, which lists the old anchor
`cfede271` and the old schema paths. This pack's own files already
use the validator's parseable format — `| Path | SHA-256 | Lines |
… |` tables in this index and in all six packs, and the `Frozen
candidate commit:` line above — so a re-anchored run can parse them.
Three validator-side gaps remain for the coordinator: (a) the
validator reads `REVIEW_INDEX.md`, not `REVIEW_INDEX_FIXR1.md`;
(b) `_is_key_production` needs the
`02_source/src/benchreceipt/schemas/` prefix so the 3 schemas count
as key files; (c) its pack glob covers the old T013 packs too, whose
rows are anchored to `cfede271` and would mismatch `66502f6` blobs —
a re-anchored run must scope the glob (or the old packs) to FIXR1.
Evidence: pre-delivery runs against the old pack PASS, exit 0
(`verify-review-pack-old-anchor.log`,
`check-review-coverage-old.log`); the post-delivery run against the
old index fails as expected — 12 problems (6 "PACK NOT LISTED IN
INDEX" for the new packs; 6 "EMPTY PACK" because the pre-reformat
tables did not use the `| Path | SHA-256 | Lines |` column order —
fixed by the reformat above, so a re-anchored run will parse them)
(`verify-review-pack-post-delivery.log`). A second run after the
reformat (`verify-review-pack-post-reformat.log`) fails with 34
problems — every one of them is the old anchor itself (SHA/line
mismatches = the FIX-R1 delta vs `cfede271`, the moved schemas
"MISSING" at `cfede271`). Decisively, a simulation of the validator
re-anchored to this index and `66502f6` with the pack glob scoped to
FIXR1 files — reusing the validator's own functions — **PASSES**
(43 index rows, 37 pack rows, 31 key files per the validator's
definition, all SHA-256 + line counts match)
(`validator_reanchored_simulation.log`; parse check in
`validator_parse_check.log`). `check_review_coverage.py`
still passes post-delivery only because it reads the old
`REVIEW_COVERAGE.csv`, not `REVIEW_COVERAGE_FIXR1.csv`
(`check-review-coverage-post-delivery.log`). This is the same
anchor-staleness class as R1's P1-R1-01, now in the validator
tooling rather than the pack itself — P2 because the pack itself is
correctly anchored and the validators are review tooling, not
production code.

## P2-29 — `ci.yml:82` comment points at T013 as if still open

`02_source/examples/github-actions/ci.yml:82`: `# summary field is a
spec decision for T013, not a capture change.` T013 is complete and
its review is superseded by this FIX-R1 pack. Stale pointer; the
workflow itself validates PASS (`validate_workflow_example.py`).

## P2-30 — Release zips are gitignored and uncommitted; only their hashes are tracked

`05_release/source.zip` (431,740 B) and `05_release/dist.zip`
(152,883 B) match the release manifest's SHA-256 values (verified
independently by this reviewer — see `REVIEW_INDEX_FIXR1.md` §Freeze
identity), but `.gitignore:13` (`*.zip`) excludes them, so neither is
in commit `b221401` (`git ls-tree b221401 -- 05_release/` lists only
`.gitkeep`, `FREEZE_REPORT.md`, `RELEASE_MANIFEST.json`,
`SHA256SUMS.txt`, and the bundle). The tracked manifest + SHA256SUMS
record the hashes, and the on-disk copies on this VM are the only
git-side source of the zips until the coordinator archives them to
Drive. Process observation, non-blocking: the hashes are verified and
the zips are byte-identical to the frozen tree (source.zip 355/355),
but a fresh clone of `b221401` alone cannot reproduce the release
without Drive. (Also noted: at the frozen commit `66502f6` itself,
the on-disk tracked `05_release/` files are still the old a07dc79
release — expected, since the re-freeze lives in `b221401`.)

---

# Carried P2 (from T013 / R1, status re-checked)

## Known P2-01–P2-04 — verified as documented (NOT re-reported)

As in T013 (`04_review/REVIEW_FINDINGS.md:562–580`), each as stated
in `02_source/docs/LIMITATIONS.md`; `PROJECT_BOOK.md` §5.5 also
carries P2-01 as a residual:

- **P2-01** transient mutate-and-revert undetectable — by construction
  of any before/after snapshot scheme. Agree, carries.
- **P2-02** no byte cap on `receipt.json` itself. Agree, carries.
- **P2-03** manifest sort order unenforced. Agree, carries.
- **P2-04** bare CR inside an LCOV `SF:` path preserved verbatim.
  Agree, carries.

## P2-05–P2-21 — still present as written, except P2-15 (partially fixed)

Spot-verified by grep/read at `66502f6`; none is a P0/P1:

- **P2-05** schema validator pattern anchoring (`re.search` + `$`
  accepts a trailing newline) — still present.
- **P2-06** giant-integer `int()` conversions leak `ValueError` —
  still present.
- **P2-07** `evaluate()` can return a `result.v1`-schema-invalid
  result when the bundle is very large — still present.
- **P2-08** invalid `--expected-source-sha` reported as
  `INVALID_POLICY` — still present.
- **P2-09** dirty tree at capture start not independently enforced —
  still present (note: `require_clean_source_after` + `dirty_after`
  is enforced at verify; the gap is at capture start).
- **P2-10** nested `<testsuite>` count attributes never checked —
  still present.
- **P2-11** report-path `.` segments: schema allows, `verify`
  passes, `bundle` rejects — still present.
- **P2-12** `build_bundle` cleanup runs only on `BundleError` —
  still present.
- **P2-13** workflow validator accepts a remote `.whl` URL as a
  "local install" — still present.
- **P2-14** S0 gate threshold 8 partly vacuous (`network_requests`
  hardcoded 0; gate never runs the socket audit) — still present.
- **P2-15 — PARTIALLY FIXED:** the Oracle now has an
  `INTERNAL_ERROR` vocabulary and `internalErrorResult()`, so unknown
  codes no longer map to `INVALID` inside `evaluate()`. But its CLI
  `main()` catch still prints to stderr and exits 4 with no result
  JSON on internal error — the second half of the finding remains.
- **P2-16** policy `schema_version = true` passes `const: 1` (Python
  `True == 1`) — still present on the Python side; the Oracle rejects
  `schema_version=true`.
- **P2-17 — re-confirmed:** dead code — `_flag_name` defined once
  (`command.py:102`, never called); `junit_file_ok` assigned
  (`verify.py:610/650`), never read; `__init__.py` docstring still
  says "Skeleton placeholder… NOT_VERIFIED until S0 passes" although
  S0 passes.
- **P2-18** `verify` reads symlinked `receipt.json` / job dirs
  straight through — still present.
- **P2-19** privacy scanner coverage gaps — still present (see also
  P2-27).
- **P2-20** `build_fixtures.py` rebuilds the frozen fixture set with
  no guard flag — still present.
- **P2-21** whitespace-only `--expected-run-id` accepted as a pin —
  still present.

---

# Points checked and found sound (no finding)

- **Freeze identity:** source.zip 431,740 B /
  `873b4dc43252202b17432c619397254a480e2dcfe10b43b7404d14b0efcd420b`,
  355/355 files byte-identical to the frozen tree at `66502f6`;
  dist.zip 152,883 B /
  `da900faf679551ab6599c2ed333923bc151032957ceba2542ff065a51fc1bacd`,
  wheel 27 entries incl. the 3 schemas, MIT, `Requires-Python:
  >=3.12`, zero runtime deps; bundle 3,844,063 B /
  `86c4c82ed019803d349997c5708d62805b918c7b89675e181a20b5f4d00d0dc8`;
  manifest `frozen_commit` = `66502f6…`, `spec_version` 1.2.0,
  `.gitkeep` present (0 B) and listed in the new SHA256SUMS — P2-R1-01
  is closed.
- **Independent re-runs (all exit 0, logs in
  `03_evidence/fix-r1-review/`):** pytest 848 passed (57.07 s);
  Oracle 26/26 (incl. 2 FIX-R1 tests); S0 gate PASS 10/10 (16/16
  controls, 36/36 faults, 52/52 parity, false PASS/block 0, repeat-100
  1 hash `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530`,
  P95 0.150 s in my run vs 0.0789 s in the manifest — both ≤ 1 s,
  golden `fb8e70a1…`, reason-codes `16feb3b8…` — all match the
  manifest); repeat-100 1 hash; offline_check PASS; privacy_scan 193
  files 0 findings; validate_workflow PASS; ui_smoke PASS
  (screenshots NOT_TESTED — no browser on this VM, same as the
  coordinator's run); `verify_release.py` PASS on a scratch worktree
  at `b221401`; offline install from the new `dist.zip` wheel in a
  fresh venv + clean-tree capture/verify roundtrip `BOUND_PASS`.
- **Spec sync:** `01_spec/` vs `~/workspace/p027-specs/` mirror 4/4
  byte-identical (BOOK.md 40,942 B `de795a33…37b692`; BOOK.docx 62,022
  B `2a9394d3…998ab6b`; PLAN.md 33,788 B `41be8c66…2723ca81afc`;
  PLAN.docx 56,117 B `482badde…2b816d`); `SPEC_MANIFEST.json`
  spec_version 1.2.0, all 4 artifact entries OK; mirror
  `SHA256SUMS.txt` 4/4 OK; SECRET_HINTS present once in each BOOK.md
  (prior divergence eliminated). MD↔DOCX: PROJECT_BOOK 65 MD headings
  vs 64 DOCX (difference is only the H1 title style plus backtick
  stripping in §6.2/§6.3 titles — 64/64 content headings match);
  IMPLEMENTATION_PLAN 44 vs 43 (H1 title only — 43/43). Keyword
  counts match exactly after including DOCX tables (BOOK v1.2.0 5/5,
  MISSING_FIELD 3/3, ADR-007 3/3; PLAN 4/4, 1/1, 2/2); §5.5/§8.6/§11.2
  key sentences verified present in DOCX. PLAN "§11.5 rule 5" is list
  item 5 under `## 11`, not a heading — no discrepancy.
- **Fail-closed (general):** `evaluate` never raises for bad input
  (unexpected exceptions → `INTERNAL_ERROR`); empty reason set is the
  only path to `BOUND_PASS`; aggregation precedence is total
  (`INTERNAL_ERROR > INVALID > UNBOUND > BOUND_FAIL > BOUND_PASS`).
- **Determinism / offline:** repeat-100 1 hash; offline install uses
  `--no-index` and the wheel has zero runtime dependencies; the
  `dist.zip` sdist note (needs a PEP 517 builder) is documented in
  `INSTALL.txt`.
