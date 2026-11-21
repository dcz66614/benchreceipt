"""Probe (i) — duplicate / confused job identity.

Two job directories can carry the same ``job_id`` (same id, different
content), or ids that differ only by case or trailing whitespace.
Matrix comparison is exact-string based: a duplicate is
MATRIX_DUPLICATE_JOB, a case variant is a missing job plus an
unexpected job — never a silent alias for the required job, and never
a second verified count for one required job.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from _evidence import (
    EXPECTED_SHA,
    POLICY,
    assert_not_pass,
    evaluate_evidence,
    junit_bytes,
    load_n06_receipt,
    make_evidence,
)
from benchreceipt.verify import evaluate


def _add_job_copy(evidence: Path, dir_name: str, job_id: str, **receipt_overrides) -> Path:
    """Copy the n06 job dir under a new name with a rewritten job_id."""
    dest = evidence / dir_name
    shutil.copytree(evidence / "unit-linux-py312", dest)
    receipt_path = dest / "receipt.json"
    receipt = load_n06_receipt()
    receipt["job_id"] = job_id
    for key, value in receipt_overrides.items():
        receipt[key] = value
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return dest


def test_same_job_id_different_content_is_a_duplicate(tmp_path: Path):
    """Two dirs, one job_id, different reports: MATRIX_DUPLICATE_JOB.

    The second copy carries a different tree SHA and a tampered
    report, so it must not be mistaken for a second verified job —
    and the first copy must not be double-counted either.
    """
    evidence = make_evidence(tmp_path)
    other = junit_bytes().replace(b'name="t1"', b'name="tX"', 1)
    dest = _add_job_copy(
        evidence, "unit-linux-py312-copy", "unit-linux-py312",
    )
    (dest / "artifacts" / "junit.xml").write_bytes(other)
    receipt_path = dest / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["git"]["tree_sha"] = "e" * 40
    receipt["reports"][0]["sha256"] = hashlib.sha256(other).hexdigest()
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "MATRIX_DUPLICATE_JOB" in verdict["reason_codes"], verdict
    assert verdict["duplicate_jobs"] == ["unit-linux-py312"], verdict
    # The duplicate never counts as a second verified job.
    assert verdict["jobs_verified"] == 1, verdict


def test_same_job_id_identical_content_is_still_a_duplicate(tmp_path: Path):
    """Even a byte-identical second copy is a duplicate, not a pass."""
    evidence = make_evidence(tmp_path)
    _add_job_copy(evidence, "unit-linux-py312-copy", "unit-linux-py312")
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "MATRIX_DUPLICATE_JOB" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 1, verdict


def test_same_job_id_different_run_id_is_duplicate_and_mismatch(tmp_path: Path):
    """A duplicate copy with a different run id adds RUN_ID_MISMATCH."""
    evidence = make_evidence(tmp_path)
    dest = _add_job_copy(evidence, "unit-linux-py312-copy", "unit-linux-py312")
    receipt_path = dest / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["ci"]["run_id"] = "9999"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "MATRIX_DUPLICATE_JOB" in verdict["reason_codes"], verdict
    assert "RUN_ID_MISMATCH" in verdict["reason_codes"], verdict


def test_job_id_case_variant_is_missing_plus_unexpected(tmp_path: Path):
    """``Unit-Linux-Py312`` is NOT the required ``unit-linux-py312``."""
    def mutate(receipt, _evidence):
        receipt["job_id"] = "Unit-Linux-Py312"

    evidence = make_evidence(tmp_path, mutate)
    # The directory name no longer matters: identity is the receipt field.
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "MATRIX_MISSING_JOB" in verdict["reason_codes"], verdict
    assert "MATRIX_UNEXPECTED_JOB" in verdict["reason_codes"], verdict
    assert verdict["missing_jobs"] == ["unit-linux-py312"], verdict
    assert verdict["unexpected_jobs"] == ["Unit-Linux-Py312"], verdict
    assert verdict["jobs_verified"] == 0, verdict


def test_two_dirs_differing_only_by_case_are_not_the_same_job(tmp_path: Path):
    """Lowercase + UPPERCASE dirs: one required job, one unexpected."""
    evidence = make_evidence(tmp_path)
    _add_job_copy(evidence, "UNIT-LINUX-PY312", "UNIT-LINUX-PY312")
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "MATRIX_UNEXPECTED_JOB" in verdict["reason_codes"], verdict
    assert verdict["unexpected_jobs"] == ["UNIT-LINUX-PY312"], verdict
    assert verdict["missing_jobs"] == [], verdict
    assert verdict["jobs_verified"] == 1, verdict


def test_job_id_with_trailing_space_is_invalid(tmp_path: Path):
    """``unit-linux-py312 `` (trailing space) fails the id pattern."""
    def mutate(receipt, _evidence):
        receipt["job_id"] = "unit-linux-py312 "

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_job_id_with_leading_dot_is_invalid(tmp_path: Path):
    """``.unit-linux-py312`` fails the id pattern (must start alnum)."""
    def mutate(receipt, _evidence):
        receipt["job_id"] = ".unit-linux-py312"

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_duplicate_job_id_never_verifies_twice_for_two_required(tmp_path: Path):
    """Two required jobs, but both dirs claim the same id: one verifies."""
    evidence = make_evidence(tmp_path)
    _add_job_copy(evidence, "unit-windows-py312", "unit-linux-py312")
    policy = dict(POLICY)
    policy["required_jobs"] = ["unit-linux-py312", "unit-windows-py312"]
    verdict = evaluate(policy, EXPECTED_SHA, evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "MATRIX_DUPLICATE_JOB" in verdict["reason_codes"], verdict
    assert "MATRIX_MISSING_JOB" in verdict["reason_codes"], verdict
    assert verdict["missing_jobs"] == ["unit-windows-py312"], verdict
    assert verdict["jobs_verified"] == 1, verdict
