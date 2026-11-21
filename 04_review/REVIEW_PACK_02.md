# REVIEW_PACK_02 — Verify decision table + reason codes

Frozen candidate: `cfede2711bc54567b918b1f85654c2dd42c30943` (see `REVIEW_INDEX.md`).

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/verify.py` | `14637b8e1647f218a36ab92866e64b699ee675165e6b0e03e41c34874d125915` | 886 | verifier: decision table, aggregation, exit codes |
| `02_source/src/benchreceipt/matrix.py` | `6c2cbe8bf70c24a3e48bad10b9df84e9b19df1309a48e3caaa2a692176fe04f3` | 101 | matrix set comparison (missing/unexpected/duplicate) |
| `02_source/src/benchreceipt/reports/junit.py` | `714735dd956b97e9a5e44dd1564605ae8e58b684d51f84fc50df135ab3335fe0` | 199 | JUnit XML parser: counted elements are truth |
| `02_source/src/benchreceipt/reports/lcov.py` | `9354b4c1942c4fe2cd0f4c3d413f0a3f6dc1c10acbfe8b3f81c0e91726c95e7c` | 309 | LCOV parser + SF path validation |

## What this pack covers

`verify.evaluate(policy, expected_source_sha, evidence_dir)` is the
verdict function: it decides BOUND_PASS / BOUND_FAIL / UNBOUND /
INVALID / INTERNAL_ERROR for a whole evidence bundle. `matrix`
does the set comparison; `reports/junit.py` and `reports/lcov.py`
parse the report files whose digests the receipt binds. The frozen
reason-code vocabulary (24 codes) lives in `verify.REASON_STATUS`
and in `02_source/docs/REASON_CODES.md` (supporting doc, not a key
file — see `REVIEW_INDEX.md`).

## Review questions

1. **Precedence (PROJECT_BOOK §5.6).** `_aggregate_status` picks
   the strictest status: INTERNAL_ERROR > INVALID > UNBOUND >
   BOUND_FAIL > BOUND_PASS. Confirm the ordering is total and
   that an empty reason-code set is the *only* path to
   BOUND_PASS. Is there any path that returns BOUND_PASS while a
   check was skipped, errored, or produced no evidence?
2. **Fail-closed on bad input.** `evaluate` must never raise for
   bad input: invalid policy → INVALID/INVALID_POLICY; missing
   evidence dir → INVALID/INVALID_EVIDENCE; malformed receipt →
   INVALID_RECEIPT (job counts as present for the matrix, never
   verified, never a reference value). Confirm every input-parsing
   failure lands in INVALID/UNBOUND and never in BOUND_PASS, and
   that an unexpected internal exception becomes
   INTERNAL_ERROR (exit 4), never exit 0 and never a traceback
   rendered as a pass.
3. **Identity checks (§5.3).** Per job: `head_sha` vs expected
   SHA, `source_mode` vs policy, `workflow` vs policy,
   cross-job `tree_sha` / `run_id` / `run_attempt` consistency
   when the policy requires sameness, plus the CLI-pinned
   `--expected-run-id` / `--expected-attempt`. Check the
   reference values (`ref_tree`/`ref_run`/`ref_attempt`) are taken
   from the first receipt by job_id — can a *first* receipt that
   is itself wrong set the reference and make a wrong bundle
   pass? Can a duplicate job's second copy count as verified?
   (It must not: `seen_once`.)
4. **Source-mutation detection (§5.5, ADR-005 / P0-01 fix).**
   The `head_sha_after` / `tree_sha_after` check must flag a
   clean-tree HEAD change that the dirty/digest checks cannot see.
   Confirm: the two after-fields must appear together; a present
   after value differing from its before value flags
   SOURCE_MUTATED_DURING_RUN; a missing-before with present-after
   also flags. Is there a combination (e.g. only one after-field
   present *and* digests equal *and* dirty flags equal) that
   escapes? Check the dirty_before/dirty_after comparison and the
   `require_clean_source_after` branch for the same gap.
5. **Report integrity (§5.4).** For each declared report:
   path containment (`_is_within_root` — resolved paths must stay
   inside the job dir; absolute paths, `..`, symlinks must not
   escape), file presence, size + SHA-256 recomputation from disk
   (never trusting the stored digest). Confirm a size lie, a hash
   lie, a missing file, and a path-escape all fail the job. Note
   the escape case is reported as REPORT_HASH_MISMATCH — is that
   the right code, and is it INVALID (not UNBOUND)?
6. **JUnit truth.** `parse_junit` counts `<testcase>` /
   `<failure>` / `<error>` / `<skipped>` elements; a count
   attribute disagreeing with the counted value is malformed.
   Confirm: `tests == 0` → JUNIT_EMPTY (BOUND_FAIL); failures /
   errors > 0 → JUNIT_FAILED; summary-vs-parsed mismatch →
   JUNIT_SUMMARY_MISMATCH (INVALID); `tests < min_tests` →
   POLICY_MISMATCH; exit-code-vs-JUnit contradiction →
   EXIT_CODE_MISMATCH. Check the DTD / external-entity stance
   (no external entities resolved) and the size cap
   (`MAX_JUNIT_BYTES`).
7. **LCOV.** `parse_lcov` validates format and `SF:` paths.
   Confirm a malformed LCOV file is LCOV_MALFORMED (INVALID),
   never passed on presence + digest alone, and that an `SF:`
   path cannot escape the repo (absolute / `..` / drive letter).
8. **Vocabulary enforcement.** `_enforce_vocabulary` turns any
   reason code outside the frozen 24 into INTERNAL_ERROR. Confirm
   the frozen set in code matches `docs/REASON_CODES.md` exactly
   (24 codes incl. `LCOV_MALFORMED` and `INTERNAL_ERROR`) and
   that no code path can emit a code not in the set.
9. **Determinism / leakage.** Results are sorted
   (`identity_mismatches`, `report_errors`) and the final result
   is schema-validated before return; an invalid result degrades
   to INVALID, never ships. Confirm no exception text, absolute
   path, or environment value leaks into a result, and that
   `_internal_error_result` is byte-identical for the same inputs.

## Inlined source (verbatim — do not paraphrase)

### `verify.py` — reason vocabulary, aggregation, exit codes

```python
REASON_STATUS: dict[str, str] = {
    "SOURCE_SHA_MISMATCH": "UNBOUND",
    "SOURCE_MODE_MISMATCH": "UNBOUND",
    "TREE_SHA_MISMATCH": "UNBOUND",
    "RUN_ID_MISMATCH": "UNBOUND",
    "RUN_ATTEMPT_MISMATCH": "UNBOUND",
    "WORKFLOW_MISMATCH": "UNBOUND",
    "MATRIX_MISSING_JOB": "UNBOUND",
    "MATRIX_DUPLICATE_JOB": "UNBOUND",
    "MATRIX_UNEXPECTED_JOB": "UNBOUND",
    "SOURCE_MUTATED_DURING_RUN": "UNBOUND",
    "REPORT_MISSING": "UNBOUND",
    "MISSING_FIELD": "UNBOUND",
    "REPORT_HASH_MISMATCH": "INVALID",
    "JUNIT_MALFORMED": "INVALID",
    "JUNIT_SUMMARY_MISMATCH": "INVALID",
    # LCOV_MALFORMED arrived with the T005 full parser (the frozen
    # vocabulary had no LCOV code; no existing code describes a
    # malformed coverage file). Ratified by T008 in ADR-003; it follows
    # the frozen code shape. No S0 fixture triggers it.
    "LCOV_MALFORMED": "INVALID",
    "INVALID_RECEIPT": "INVALID",
    "INVALID_POLICY": "INVALID",
    "INVALID_EVIDENCE": "INVALID",
    "JUNIT_FAILED": "BOUND_FAIL",
    "JUNIT_EMPTY": "BOUND_FAIL",
    "EXIT_CODE_MISMATCH": "BOUND_FAIL",
    "POLICY_MISMATCH": "BOUND_FAIL",
    # INTERNAL_ERROR is both a status (§5.6) and the reason code that
    # explains it: the verifier itself hit an unexpected exception, so
    # the result carries no other finding. Ratified by T008 in ADR-003.
    "INTERNAL_ERROR": "INTERNAL_ERROR",
}

# The complete frozen reason-code vocabulary. Any code outside this set
# is a verifier bug, never a finding: see _enforce_vocabulary().
REASON_CODES: frozenset[str] = frozenset(REASON_STATUS)

# CLI exit codes, PROJECT_BOOK §5.6. status_to_exit_code() is the one
# place that maps a result status to a process exit code.
EXIT_CODES: dict[str, int] = {
    "BOUND_PASS": 0,
    "BOUND_FAIL": 1,
    "UNBOUND": 2,
    "INVALID": 3,
    "INTERNAL_ERROR": 4,
}


def status_to_exit_code(status: str) -> int:
    """Map a result status to its §5.6 CLI exit code.

    An unknown status is a verifier bug: fail closed to 4
    (INTERNAL_ERROR), never to 0.
    """
    return EXIT_CODES.get(status, 4)


def _internal_error_result() -> dict[str, Any]:
    """The result returned when verification itself fails unexpectedly.

    Fixed content only: the underlying exception text is never embedded
    (it is non-deterministic across runtimes and could leak paths), so
    every INTERNAL_ERROR result is byte-identical for the same inputs.
    ``expected_source_mode`` is omitted: when the verifier fails, the
    mode it would have echoed cannot be trusted either.
    """
    return {
        "schema": "benchreceipt.result/v1",
        "status": "INTERNAL_ERROR",
        "jobs_verified": 0,
        "missing_jobs": [],
        "unexpected_jobs": [],
        "duplicate_jobs": [],
        "reason_codes": ["INTERNAL_ERROR"],
        "identity_mismatches": [],
        "report_errors": [
            {"code": "INTERNAL_ERROR",
             "message": "internal error during verification"}
        ],
    }


def _invalid_result(
    codes: list[str],
    errors: list[dict[str, Any]],
    expected_source_mode: str | None = None,
) -> dict[str, Any]:
    """Build an ``INVALID`` result for a known-bad input.

    ``expected_source_mode`` is included only when the policy was
    successfully validated (it is unknown — and the result schema does
    not admit null — when the policy itself is invalid).
    """
    result: dict[str, Any] = {
        "schema": "benchreceipt.result/v1",
        "status": "INVALID",
        "jobs_verified": 0,
        "missing_jobs": [],
        "unexpected_jobs": [],
        "duplicate_jobs": [],
        "reason_codes": sorted(set(codes)),
        "identity_mismatches": [],
        "report_errors": sorted(errors, key=lambda e: (e.get("job_id", ""), e.get("code", ""))),
    }
    if expected_source_mode is not None:
        result["expected_source_mode"] = expected_source_mode
    return result


def _enforce_vocabulary(reason_codes: set[str]) -> dict[str, Any] | None:
    """Return an INTERNAL_ERROR result if any code is outside the frozen
    vocabulary, else None. A verifier emitting an unfrozen code is a
    verifier bug; the finding must never ship as if it were a real
    verdict.
    """
    if reason_codes - REASON_CODES:
        return _internal_error_result()
    return None


def _aggregate_status(reason_codes: list[str]) -> str:
    """Strictest status among the emitted reason codes (§5.6 precedence)."""
    if not reason_codes:
        return "BOUND_PASS"
    worst = "BOUND_PASS"
    for code in reason_codes:
        status = REASON_STATUS.get(code, "INVALID")
        if _STATUS_ORDER.index(status) < _STATUS_ORDER.index(worst):
            worst = status
    return worst
```

### `verify.py` — per-job identity + source-mutation checks (§5.3/§5.5)

```python
        # --- identity (§5.3) --------------------------------------------
        if git["head_sha"] != expected_source_sha:
            reason_codes.add("SOURCE_SHA_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "git.head_sha",
                 "expected": expected_source_sha, "actual": git["head_sha"]}
            )
            job_ok = False
        if git["source_mode"] != policy["source_mode"]:
            reason_codes.add("SOURCE_MODE_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "git.source_mode",
                 "expected": policy["source_mode"], "actual": git["source_mode"]}
            )
            job_ok = False
        if ci["workflow"] != policy["expected_workflow"]:
            reason_codes.add("WORKFLOW_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "ci.workflow",
                 "expected": policy["expected_workflow"], "actual": ci["workflow"]}
            )
            job_ok = False
        if policy["same_tree_across_jobs"] and git["tree_sha"] != ref_tree:
            reason_codes.add("TREE_SHA_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "git.tree_sha",
                 "expected": ref_tree, "actual": git["tree_sha"]}
            )
            job_ok = False
        if policy["same_run_id"] and ci["run_id"] != ref_run:
            reason_codes.add("RUN_ID_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "ci.run_id",
                 "expected": ref_run, "actual": ci["run_id"]}
            )
            job_ok = False
        if policy["same_run_attempt"] and ci["run_attempt"] != ref_attempt:
            reason_codes.add("RUN_ATTEMPT_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "ci.run_attempt",
                 "expected": ref_attempt, "actual": ci["run_attempt"]}
            )
            job_ok = False
        # --- expected run identity from the CLI (§6.4) ------------------
        # Independent of the cross-job checks above: when the caller
        # pins an expected run id / attempt, each job must match it.
        # The code is the same RUN_ID_MISMATCH / RUN_ATTEMPT_MISMATCH
        # (UNBOUND); only the `expected` value differs (the pinned
        # value instead of the first job's value).
        if expected_run_id is not None and ci["run_id"] != expected_run_id:
            reason_codes.add("RUN_ID_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "ci.run_id",
                 "expected": expected_run_id, "actual": ci["run_id"]}
            )
            job_ok = False
        if expected_attempt is not None and ci["run_attempt"] != expected_attempt:
            reason_codes.add("RUN_ATTEMPT_MISMATCH")
            identity_mismatches.append(
                {"job_id": job_id, "field": "ci.run_attempt",
                 "expected": expected_attempt, "actual": ci["run_attempt"]}
            )
            job_ok = False

        # --- source mutation (§5.5) --------------------------------------
        # After-identity check (spec v1.1.0, ADR-005, P0-01 fix): a
        # clean-tree HEAD change leaves the porcelain digests identical
        # and both dirty flags False, so the dirty/digest checks below
        # cannot see it. The receipt's git.head_sha_after /
        # git.tree_sha_after (populated by capture from git_after) are
        # the only record of it. Fail closed on inconsistency: the two
        # after fields must appear together, each must be a 40-hex SHA
        # (schema-validated on load), and a present after value that
        # differs from its before value — or whose before value is
        # missing/not a string — is a mutation. Receipts written before
        # v1.1.0 carry neither after field and are judged by the
        # dirty/digest checks alone, as before.
        mutated = False
        after_head = git.get("head_sha_after")
        after_tree = git.get("tree_sha_after")
        if (after_head is not None) != (after_tree is not None):
            mutated = True
        if after_head is not None:
            if not isinstance(git.get("head_sha"), str) or after_head != git["head_sha"]:
                mutated = True
        if after_tree is not None:
            if not isinstance(git.get("tree_sha"), str) or after_tree != git["tree_sha"]:
                mutated = True
        before = receipt.get("source_state_before")
        after = receipt.get("source_state_after")
        if (
            isinstance(before, dict)
            and isinstance(after, dict)
            and isinstance(before.get("tracked_diff_sha256"), str)
            and isinstance(after.get("tracked_diff_sha256"), str)
            and before["tracked_diff_sha256"] != after["tracked_diff_sha256"]
        ):
            mutated = True
        if git.get("dirty_before") != git.get("dirty_after"):
            mutated = True
        if policy["require_clean_source_after"] and git.get("dirty_after") is True:
            mutated = True
        if mutated:
            reason_codes.add("SOURCE_MUTATED_DURING_RUN")
            job_ok = False
```

### `verify.py` — `evaluate` / `evaluate_with_policy_path` (verbatim)

```python
def evaluate(
    policy_dict: dict[str, Any],
    expected_source_sha: str,
    evidence_dir: str | Path,
    *,
    expected_run_id: str | None = None,
    expected_attempt: int | None = None,
) -> dict[str, Any]:
    """Verify one evidence bundle against a policy and an expected SHA.

    ``policy_dict`` is the tomllib-parsed policy (validated + normalised
    via :func:`benchreceipt.policy.validate_policy`).
    ``expected_source_sha`` is the 40-hex SHA every job's
    ``git.head_sha`` must equal. ``evidence_dir`` holds one subdirectory
    per job, each with ``receipt.json`` and ``artifacts/``.
    ``expected_run_id`` / ``expected_attempt`` are optional pinned run
    identities (the CLI ``--expected-run-id`` / ``--expected-attempt``
    flags); when given, every job must match them as well as the
    cross-job consistency the policy requires. All three positional
    parameters keep their T004 meaning, so existing callers (including
    the S0 gate) are unaffected.

    Returns a ``benchreceipt.result/v1`` dict. Never raises for bad
    input: invalid policy / evidence / receipts produce an ``INVALID``
    result (fail-closed). An unexpected internal exception — a verifier
    bug, not bad input — is caught here and returned as an
    ``INTERNAL_ERROR`` result instead of propagating: a traceback must
    never become a pass, and the CLI maps it to exit 4.
    """
    try:
        return _evaluate_inner(
            policy_dict,
            expected_source_sha,
            evidence_dir,
            expected_run_id=expected_run_id,
            expected_attempt=expected_attempt,
        )
    except Exception:
        return _internal_error_result()


def evaluate_with_policy_path(
    policy_path: str | Path,
    expected_source_sha: str,
    evidence_dir: str | Path,
    *,
    expected_run_id: str | None = None,
    expected_attempt: int | None = None,
) -> dict[str, Any]:
    """Verify an evidence bundle, loading the policy from ``policy_path``.

    Convenience wrapper used by the CLI: the policy file is loaded via
    :func:`benchreceipt.policy.load_policy`, then :func:`evaluate` runs.
    A policy file that is missing, unreadable, not valid TOML, or fails
    ``benchreceipt.policy/v1`` yields an ``INVALID`` result with reason
    code ``INVALID_POLICY`` — never a default policy, never a pass.
    An unexpected internal exception yields an ``INTERNAL_ERROR``
    result. This function never raises for bad input.
    """
    try:
        policy = load_policy(policy_path)
    except PolicyInvalid:
        return _invalid_result(
            ["INVALID_POLICY"],
            [{"code": "INVALID_POLICY", "message": "policy is not valid benchreceipt.policy/v1"}],
        )
    except Exception:
        return _internal_error_result()
    try:
        return evaluate(
            policy,
            expected_source_sha,
            evidence_dir,
            expected_run_id=expected_run_id,
            expected_attempt=expected_attempt,
        )
    except Exception:
        return _internal_error_result()
```
