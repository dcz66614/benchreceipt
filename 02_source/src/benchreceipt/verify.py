"""Production verifier (P027-T008; first version shipped by T004).

Implements PROJECT_BOOK §5 as a pure function::

    evaluate(policy_dict, expected_source_sha, evidence_dir) -> result dict

The result dict follows ``benchreceipt.result/v1`` (frozen by T002).
Reason codes and their status classes are frozen in
``02_source/docs/REASON_CODES.md``; the fixed ``report_errors`` message
templates live there too, so this module and the independent Node Oracle
(``oracle/verify.mjs``) produce byte-identical results. The vocabulary
is enforced here: :data:`REASON_CODES` is the complete frozen set
(22 codes from T004 plus ``LCOV_MALFORMED``, ratified by T008 in
``00_control/ADR/ADR-003-t008-reason-codes.md``, plus
``INTERNAL_ERROR``); a result that would carry any other code is
replaced by an ``INTERNAL_ERROR`` result, never shipped.

What this module implements:

- Matrix set comparison (§5.2): missing / unexpected / duplicate jobs.
- Per-job identity (§5.3): source SHA vs the expected SHA argument,
  source mode vs policy, workflow vs policy, cross-job tree / run id /
  run attempt consistency when the policy requires sameness. When the
  caller additionally supplies an expected run id / attempt (the CLI
  ``--expected-run-id`` / ``--expected-attempt`` flags), each job is
  also checked against those values; without them only cross-job
  consistency is checked (the S0 behaviour).
- Report integrity (§5.4): report file presence, size + SHA-256
  recomputation, full JUnit XML parsing via
  ``benchreceipt.reports.junit`` (T005; counted elements are the
  truth, count attributes must match them), LCOV format + path
  validation via ``benchreceipt.reports.lcov`` (T005), ``tests > 0``,
  ``failures == 0``, ``errors == 0``, ``min_tests``. Every ``junit``
  report in a job is judged against the receipt summary (FIX-R13a /
  F-01): a failing report is never hidden by another report listed
  after it.
- Source-mutation detection (§5.5) via the T003 fields
  (``git.dirty_before/after`` + ``source_state_before/after``
  ``tracked_diff_sha256``) plus, since spec v1.1.0 (ADR-005),
  ``git.head_sha_after`` / ``git.tree_sha_after``: a clean-tree HEAD
  change is invisible to the dirty/digest checks, so an after value
  differing from its before value — or the two after fields appearing
  inconsistently — flags ``SOURCE_MUTATED_DURING_RUN`` (fail closed).
  Since spec v1.2.0 (ADR-007, P0-R1-01) a receipt with BOTH after
  fields absent is ``UNBOUND`` with ``MISSING_FIELD``: it cannot prove
  the run's HEAD/tree did not change, so it must not ``BOUND_PASS``
  on the dirty/digest checks alone.
- Five-state aggregation (§5.6) with strict precedence
  INTERNAL_ERROR > INVALID > UNBOUND > BOUND_FAIL > BOUND_PASS.
  Missing evidence, parse failure, unreadable input, or an unknown
  field never degrades to PASS.
- ``INTERNAL_ERROR`` path: :func:`evaluate` never raises for bad
  *input* (invalid policy / evidence / receipts produce an ``INVALID``
  result, fail-closed). An unexpected *internal* exception (a verifier
  bug, not bad input) is caught and returned as a result with status
  ``INTERNAL_ERROR`` and reason code ``INTERNAL_ERROR`` — never a
  traceback-as-pass and never exit 0. :func:`evaluate_with_policy_path`
  is the same contract starting from a policy file path (the CLI entry
  point): an unloadable policy yields an ``INVALID`` / ``INVALID_POLICY``
  result instead of raising.

Standard library only. No network access, no GitHub API, no credentials.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchreceipt.matrix import aggregate_matrix
from benchreceipt.policy import PolicyInvalid, load_policy, validate_policy
from benchreceipt.reports.junit import JUnitError, parse_junit
from benchreceipt.reports.lcov import LcovError, parse_lcov
from benchreceipt.schema import SchemaValidationError, validate_against_schema

__all__ = [
    "EXIT_CODES",
    "REASON_CODES",
    "REASON_STATUS",
    "evaluate",
    "evaluate_with_policy_path",
    "status_to_exit_code",
]

# Status precedence: the strictest (lowest index) wins. §5.6.
# INTERNAL_ERROR dominates: when the verifier itself fails, no other
# finding can be trusted, so it outranks even INVALID.
_STATUS_ORDER = ("INTERNAL_ERROR", "INVALID", "UNBOUND", "BOUND_FAIL", "BOUND_PASS")

# Reason code -> status class (frozen in docs/REASON_CODES.md; ratified
# additions in 00_control/ADR/ADR-003-t008-reason-codes.md).
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


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _is_within_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# --- JUnit parsing (T005 full parser) ----------------------------------
# Delegates to benchreceipt.reports.junit: counted <testcase> /
# <failure> / <error> / <skipped> elements are the truth, and a count
# attribute that disagrees with the counted value is malformed, never
# silently trusted. No DTD or external entity is ever resolved.

def _parse_junit(data: bytes) -> tuple[int, int, int, int] | None:
    """Return (tests, failures, errors, skipped) or None if unparsable."""
    try:
        summary = parse_junit(data)
    except JUnitError:
        return None
    return (
        summary["tests"],
        summary["failures"],
        summary["errors"],
        summary["skipped"],
    )


def _load_receipts(evidence_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Load every ``<job-dir>/receipt.json`` under ``evidence_dir``.

    Returns ``(receipts, invalid_entries, invalid_job_ids)`` where each
    receipt is ``{"job_dir": str, "data": dict}``, each invalid entry is
    a ``report_errors``-shaped dict with code ``INVALID_RECEIPT``, and
    ``invalid_job_ids`` holds the job id of each invalid receipt (from
    the file when parseable, else the directory name). An invalid
    receipt still counts as *present* for the matrix set comparison
    (§5.2: it has no usable evidence, but the job is not "missing" —
    it is invalid); it never counts as verified and never supplies
    reference values. A subdirectory without a readable/valid receipt
    still counts as an invalid entry (fail-closed); it never silently
    disappears.
    """
    receipts: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    invalid_job_ids: list[str] = []
    for child in sorted(evidence_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        receipt_path = child / "receipt.json"
        job_label = child.name
        if not receipt_path.is_file():
            invalid.append(
                {
                    "code": "INVALID_RECEIPT",
                    "message": "receipt is not valid benchreceipt.run/v1",
                    "job_id": job_label,
                }
            )
            invalid_job_ids.append(job_label)
            continue
        try:
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            invalid.append(
                {
                    "code": "INVALID_RECEIPT",
                    "message": "receipt is not valid benchreceipt.run/v1",
                    "job_id": job_label,
                }
            )
            invalid_job_ids.append(job_label)
            continue
        if not isinstance(data, dict):
            invalid.append(
                {
                    "code": "INVALID_RECEIPT",
                    "message": "receipt is not valid benchreceipt.run/v1",
                    "job_id": job_label,
                }
            )
            invalid_job_ids.append(job_label)
            continue
        try:
            validate_against_schema(data, "run")
        except SchemaValidationError:
            invalid.append(
                {
                    "code": "INVALID_RECEIPT",
                    "message": "receipt is not valid benchreceipt.run/v1",
                    "job_id": data.get("job_id") if isinstance(data.get("job_id"), str) else job_label,
                }
            )
            invalid_job_ids.append(
                data.get("job_id") if isinstance(data.get("job_id"), str) else job_label
            )
            continue
        receipts.append({"job_dir": child, "data": data})
    return receipts, invalid, invalid_job_ids


def _evaluate_inner(
    policy_dict: dict[str, Any],
    expected_source_sha: str,
    evidence_dir: str | Path,
    expected_run_id: str | None = None,
    expected_attempt: int | None = None,
) -> dict[str, Any]:
    """Inner verification; see :func:`evaluate`.

    ``expected_run_id`` / ``expected_attempt`` (both optional) are the
    CLI ``--expected-run-id`` / ``--expected-attempt`` values: when
    given, every job's ``ci.run_id`` / ``ci.run_attempt`` must equal
    them, in addition to the cross-job consistency checks the policy
    requires. When omitted, only cross-job consistency is checked.

    Never raises for bad *input*: invalid policy / evidence / receipts
    produce an ``INVALID`` result (fail-closed). Caller-API misuse
    (a non-string run id, an out-of-range attempt) raises
    ``ValueError``; :func:`evaluate` converts that to an
    ``INTERNAL_ERROR`` result. Unexpected internal errors propagate to
    :func:`evaluate` the same way.
    """
    if expected_run_id is not None and (
        not isinstance(expected_run_id, str) or not expected_run_id
    ):
        raise ValueError("expected_run_id must be a non-empty string")
    if expected_attempt is not None and (
        isinstance(expected_attempt, bool)
        or not isinstance(expected_attempt, int)
        or not 1 <= expected_attempt <= 100000
    ):
        raise ValueError("expected_attempt must be an integer in 1..100000")

    evidence_path = Path(evidence_dir)

    try:
        policy = validate_policy(policy_dict)
    except PolicyInvalid:
        return _invalid_result(
            ["INVALID_POLICY"],
            [{"code": "INVALID_POLICY", "message": "policy is not valid benchreceipt.policy/v1"}],
        )

    expected_mode = policy["source_mode"]

    if (
        not isinstance(expected_source_sha, str)
        or len(expected_source_sha) != 40
        or any(c not in "0123456789abcdef" for c in expected_source_sha)
    ):
        return _invalid_result(
            ["INVALID_POLICY"],
            [{"code": "INVALID_POLICY", "message": "policy is not valid benchreceipt.policy/v1"}],
            expected_source_mode=expected_mode,
        )

    if not evidence_path.is_dir():
        return _invalid_result(
            ["INVALID_EVIDENCE"],
            [{"code": "INVALID_EVIDENCE", "message": "evidence directory is missing or unreadable"}],
            expected_source_mode=expected_mode,
        )

    required_jobs: list[str] = list(policy["required_jobs"])
    required_set = set(required_jobs)

    receipts, invalid_entries, invalid_job_ids = _load_receipts(evidence_path)

    reason_codes: set[str] = set()
    identity_mismatches: list[dict[str, Any]] = []
    report_errors: list[dict[str, Any]] = list(invalid_entries)
    if invalid_entries:
        reason_codes.add("INVALID_RECEIPT")

    # --- matrix set comparison (§5.2) ------------------------------------
    # Delegated to benchreceipt.matrix.aggregate_matrix (P027-T007).
    # aggregate_matrix counts occurrences in actual_job_ids, so the
    # list passed here must encode the ADR-002 decision 3 rule exactly:
    # invalid receipts count as present (not missing) but never toward
    # duplicates. Each invalid job id is therefore appended once, and
    # only when no valid receipt already carries that id; two invalid
    # receipts for the same job id likewise contribute one presence,
    # never a duplicate. Valid receipt job ids keep their multiplicity.
    valid_job_ids = [entry["data"]["job_id"] for entry in receipts]
    valid_set = set(valid_job_ids)
    actual_job_ids = list(valid_job_ids)
    for job_id in dict.fromkeys(invalid_job_ids):
        if job_id not in valid_set:
            actual_job_ids.append(job_id)
    matrix = aggregate_matrix(required_jobs, actual_job_ids)
    missing_jobs = matrix["missing"]
    unexpected_jobs = matrix["unexpected"]
    duplicate_jobs = matrix["duplicate"]
    if missing_jobs:
        reason_codes.add("MATRIX_MISSING_JOB")
    if unexpected_jobs:
        reason_codes.add("MATRIX_UNEXPECTED_JOB")
    if duplicate_jobs:
        reason_codes.add("MATRIX_DUPLICATE_JOB")

    # Reference values for cross-job consistency: first receipt when
    # receipts are ordered by job_id (first occurrence per job id).
    first_by_job: dict[str, dict[str, Any]] = {}
    for entry in sorted(receipts, key=lambda e: e["data"]["job_id"]):
        first_by_job.setdefault(entry["data"]["job_id"], entry["data"])
    ordered_job_ids = sorted(first_by_job)
    ref_tree = ref_run = ref_attempt = None
    if ordered_job_ids:
        ref = first_by_job[ordered_job_ids[0]]
        ref_tree = ref["git"]["tree_sha"]
        ref_run = ref["ci"]["run_id"]
        ref_attempt = ref["ci"]["run_attempt"]

    jobs_verified = 0
    seen_once: set[str] = set()

    for entry in receipts:
        receipt = entry["data"]
        job_id = receipt["job_id"]
        job_ok = True

        # A duplicate's second and later copies never count as verified.
        is_duplicate_copy = job_id in seen_once
        seen_once.add(job_id)
        if is_duplicate_copy:
            job_ok = False

        git = receipt["git"]
        ci = receipt["ci"]

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
        # After-identity check (spec v1.1.0, ADR-005, P0-01 fix; made
        # fail-closed in spec v1.2.0, ADR-007, P0-R1-01): a clean-tree
        # HEAD change leaves the porcelain digests identical and both
        # dirty flags False, so the dirty/digest checks below cannot
        # see it. The receipt's git.head_sha_after /
        # git.tree_sha_after (populated by capture from git_after) are
        # the only record of it. Fail closed on inconsistency: the two
        # after fields must appear together, each must be a 40-hex SHA
        # (schema-validated on load), and a present after value that
        # differs from its before value — or whose before value is
        # missing/not a string — is a mutation. When BOTH after fields
        # are absent the receipt cannot prove the run's HEAD/tree did
        # not change mid-run, so it is UNBOUND with MISSING_FIELD
        # (ADR-007 overturns the ADR-005 decision 4 compat rule that
        # judged such receipts by the dirty/digest checks alone).
        mutated = False
        after_head = git.get("head_sha_after")
        after_tree = git.get("tree_sha_after")
        if after_head is None and after_tree is None:
            # No after-identity evidence at all: fail closed, do not
            # fall back to the dirty/digest checks (P0-R1-01).
            reason_codes.add("MISSING_FIELD")
            report_errors.append(
                {"code": "MISSING_FIELD",
                 "message": "missing git.head_sha_after and git.tree_sha_after",
                 "job_id": job_id}
            )
            job_ok = False
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

        # --- reports (§5.4) ----------------------------------------------
        job_dir: Path = entry["job_dir"]
        reports = receipt.get("reports") or []
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for rep in reports:
            by_kind.setdefault(rep["kind"], []).append(rep)

        for kind in ("junit", "lcov"):
            if policy["reports"].get(kind) != "required":
                continue
            if kind not in by_kind:
                reason_codes.add("REPORT_MISSING")
                report_errors.append(
                    {"code": "REPORT_MISSING",
                     "message": f"required {kind} report missing",
                     "job_id": job_id}
                )
                job_ok = False

        junit_path: str | None = None
        junit_file_ok = False
        # FIX-R13a (F-01): EVERY parsed junit report in this job, in
        # receipt order — (report path, parsed counts or None when the
        # file was malformed). The old code kept only the LAST parsed
        # report (the parsed value was overwritten on every junit
        # entry), so a failing bound report was silently ignored when
        # it was not last. The summary checks below judge each entry.
        junit_reports: list[tuple[str, tuple[int, int, int, int] | None]] = []
        for rep in reports:
            rel = rep["path"]
            target = (job_dir / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
            if not _is_within_root(job_dir, target):
                reason_codes.add("REPORT_HASH_MISMATCH")
                report_errors.append(
                    {"code": "REPORT_HASH_MISMATCH",
                     "message": f"report digest mismatch: {rel}",
                     "job_id": job_id, "path": rel}
                )
                job_ok = False
                continue
            if not target.is_file():
                reason_codes.add("REPORT_MISSING")
                report_errors.append(
                    {"code": "REPORT_MISSING",
                     "message": f"report file missing: {rel}",
                     "job_id": job_id, "path": rel}
                )
                job_ok = False
                continue
            size, digest = _sha256_file(target)
            if size != rep["size_bytes"] or digest != rep["sha256"]:
                reason_codes.add("REPORT_HASH_MISMATCH")
                report_errors.append(
                    {"code": "REPORT_HASH_MISMATCH",
                     "message": f"report digest mismatch: {rel}",
                     "job_id": job_id, "path": rel}
                )
                job_ok = False
                continue
            if rep["kind"] == "junit":
                junit_file_ok = True
                junit_path = rel
                parsed = _parse_junit(target.read_bytes())
                junit_reports.append((rel, parsed))
                if parsed is None:
                    reason_codes.add("JUNIT_MALFORMED")
                    report_errors.append(
                        {"code": "JUNIT_MALFORMED",
                         "message": "JUnit XML is malformed",
                         "job_id": job_id, "path": rel}
                    )
                    job_ok = False
            elif rep["kind"] == "lcov":
                # T005: LCOV format + path validation (§5.4). A
                # malformed coverage file is INVALID, never passed
                # on presence + digest alone.
                try:
                    parse_lcov(target.read_bytes())
                except LcovError:
                    reason_codes.add("LCOV_MALFORMED")
                    report_errors.append(
                        {"code": "LCOV_MALFORMED",
                         "message": "LCOV report is malformed",
                         "job_id": job_id, "path": rel}
                    )
                    job_ok = False

        # --- JUnit summary checks (§5.4) ----------------------------------
        summary = receipt.get("junit")
        if policy["reports"].get("junit") == "required" and summary is None:
            # A JUnit report file exists but the receipt carries no
            # summary (or no report at all and no summary): the summary
            # is a critical field the policy requires.
            reason_codes.add("MISSING_FIELD")
            report_errors.append(
                {"code": "MISSING_FIELD", "message": "missing junit summary",
                 "job_id": job_id}
            )
            job_ok = False

        junit_failed = False
        junit_tests: int | None = None
        if summary is not None:
            junit_tests = summary["tests"]
            if junit_tests == 0:
                reason_codes.add("JUNIT_EMPTY")
                entry_err = {"code": "JUNIT_EMPTY",
                             "message": "JUnit report has 0 tests",
                             "job_id": job_id}
                if junit_path:
                    entry_err["path"] = junit_path
                report_errors.append(entry_err)
                job_ok = False
            elif summary["failures"] > 0 or summary["errors"] > 0:
                junit_failed = True
                reason_codes.add("JUNIT_FAILED")
                entry_err = {"code": "JUNIT_FAILED",
                             "message": (
                                 f"JUnit failed: {summary['failures']} failures, "
                                 f"{summary['errors']} errors (tests={summary['tests']})"
                             ),
                             "job_id": job_id}
                if junit_path:
                    entry_err["path"] = junit_path
                report_errors.append(entry_err)
                job_ok = False
            if junit_tests is not None and junit_tests > 0 and junit_tests < policy["min_tests"]:
                reason_codes.add("POLICY_MISMATCH")
                entry_err = {"code": "POLICY_MISMATCH",
                             "message": (
                                 f"JUnit tests {junit_tests} below policy "
                                 f"min_tests {policy['min_tests']}"
                             ),
                             "job_id": job_id}
                if junit_path:
                    entry_err["path"] = junit_path
                report_errors.append(entry_err)
                job_ok = False
        # FIX-R13a (F-01): judge EVERY parsed junit report, not just
        # the last one. A report counts as failing when its own parsed
        # counts show failures/errors > 0, and every parsed report's
        # counts must match the receipt summary (when one exists) —
        # order-independent, so a failing report can no longer hide
        # behind a passing report listed after it.
        parsed_reports = [
            (path, parsed) for path, parsed in junit_reports if parsed is not None
        ]
        summary_failed = (
            summary is not None
            and (summary["failures"] > 0 or summary["errors"] > 0)
        )
        summary_empty = summary is not None and summary["tests"] == 0
        for rep_path, parsed in parsed_reports:
            p_tests, p_failures, p_errors, _p_skipped = parsed
            if summary is not None:
                if (
                    p_tests != summary["tests"]
                    or p_failures != summary["failures"]
                    or p_errors != summary["errors"]
                ):
                    reason_codes.add("JUNIT_SUMMARY_MISMATCH")
                    report_errors.append(
                        {"code": "JUNIT_SUMMARY_MISMATCH",
                         "message": "JUnit summary does not match parsed report",
                         "job_id": job_id, "path": rep_path}
                    )
                    job_ok = False
                # Judge the parsed report on its own merits too. The
                # summary already emitted JUNIT_FAILED / JUNIT_EMPTY
                # for its own counts; a per-report entry is added only
                # when the summary did not already flag the same
                # failure, so one report never yields the same finding
                # twice — but junit_failed is set from ANY failing
                # parsed report, so the exit-code check sees it too.
                if p_failures > 0 or p_errors > 0:
                    junit_failed = True
                    if not summary_failed:
                        reason_codes.add("JUNIT_FAILED")
                        report_errors.append(
                            {"code": "JUNIT_FAILED",
                             "message": (
                                 f"JUnit failed: {p_failures} failures, "
                                 f"{p_errors} errors (tests={p_tests})"
                             ),
                             "job_id": job_id, "path": rep_path}
                        )
                        job_ok = False
                elif p_tests == 0 and not summary_empty:
                    reason_codes.add("JUNIT_EMPTY")
                    report_errors.append(
                        {"code": "JUNIT_EMPTY",
                         "message": "JUnit report has 0 tests",
                         "job_id": job_id, "path": rep_path}
                    )
                    job_ok = False
            else:
                # No summary: judge the parsed report directly.
                if p_tests == 0:
                    reason_codes.add("JUNIT_EMPTY")
                    report_errors.append(
                        {"code": "JUNIT_EMPTY",
                         "message": "JUnit report has 0 tests",
                         "job_id": job_id, "path": rep_path}
                    )
                    job_ok = False
                elif p_failures > 0 or p_errors > 0:
                    junit_failed = True
                    reason_codes.add("JUNIT_FAILED")
                    report_errors.append(
                        {"code": "JUNIT_FAILED",
                         "message": (
                             f"JUnit failed: {p_failures} failures, "
                             f"{p_errors} errors (tests={p_tests})"
                         ),
                         "job_id": job_id, "path": rep_path}
                    )
                    job_ok = False
            if junit_tests is None:
                junit_tests = p_tests

        # --- exit code vs JUnit contradiction (§5.4) ----------------------
        exit_code = receipt["command"]["exit_code"]
        if parsed_reports and junit_tests is not None and junit_tests > 0:
            exit_failed = exit_code != 0
            if exit_failed != junit_failed:
                reason_codes.add("EXIT_CODE_MISMATCH")
                if exit_failed:
                    message = (
                        f"command exit code {exit_code} contradicts "
                        "passing JUnit result"
                    )
                else:
                    message = "command exit code 0 contradicts failing JUnit result"
                report_errors.append(
                    {"code": "EXIT_CODE_MISMATCH", "message": message,
                     "job_id": job_id}
                )
                job_ok = False

        if job_ok and job_id in required_set:
            jobs_verified += 1

    identity_mismatches.sort(key=lambda e: (e["job_id"], e["field"]))
    # FIX-R13a (F-01): judging every report can otherwise report the
    # same finding twice when two receipt entries point at the same
    # report file. Identical (job, code, path, message) findings are
    # one finding; distinct paths still report separately.
    _seen_errors: set[tuple[str, str, str, str]] = set()
    _deduped_errors: list[dict[str, Any]] = []
    for _err in report_errors:
        _key = (
            str(_err.get("job_id", "")),
            str(_err.get("code", "")),
            str(_err.get("path", "")),
            str(_err.get("message", "")),
        )
        if _key not in _seen_errors:
            _seen_errors.add(_key)
            _deduped_errors.append(_err)
    report_errors = _deduped_errors
    report_errors.sort(key=lambda e: (e.get("job_id", ""), e.get("code", ""), e.get("path", "")))

    # Vocabulary enforcement: no unfrozen code may ship as a finding.
    vocab_error = _enforce_vocabulary(reason_codes)
    if vocab_error is not None:
        return vocab_error

    result = {
        "schema": "benchreceipt.result/v1",
        "status": _aggregate_status(sorted(reason_codes)),
        "jobs_verified": jobs_verified,
        "missing_jobs": missing_jobs,
        "unexpected_jobs": unexpected_jobs,
        "duplicate_jobs": duplicate_jobs,
        "reason_codes": sorted(reason_codes),
        "identity_mismatches": identity_mismatches,
        "report_errors": report_errors,
        "expected_source_mode": expected_mode,
    }
    try:
        validate_against_schema(result, "result")
    except SchemaValidationError:
        # A verifier bug must never ship a schema-invalid result as a
        # pass; degrade to INTERNAL_ERROR-shaped INVALID. This branch is
        # unreachable for the 48 S0 fixtures (covered by tests).
        return {
            "schema": "benchreceipt.result/v1",
            "status": "INVALID",
            "jobs_verified": 0,
            "missing_jobs": missing_jobs,
            "unexpected_jobs": unexpected_jobs,
            "duplicate_jobs": duplicate_jobs,
            "reason_codes": ["INVALID_RECEIPT"],
            "identity_mismatches": [],
            "report_errors": [
                {"code": "INVALID_RECEIPT",
                 "message": "receipt is not valid benchreceipt.run/v1"}
            ],
            "expected_source_mode": expected_mode,
        }
    return result


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
