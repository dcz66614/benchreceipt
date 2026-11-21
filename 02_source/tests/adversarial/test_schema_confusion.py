"""Probe (g) — schema confusion.

The frozen schemas (run.v1 / policy.v1 / result.v1) all set
``additionalProperties: false`` and pin enums / consts. A receipt
that smuggles an extra field (including a forged ``status``), a
policy with an unknown field, or a wrong enum value must be
INVALID — never interpreted, never passed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from _evidence import (
    EXPECTED_SHA,
    POLICY,
    assert_not_pass,
    evaluate_evidence,
    make_evidence,
)
from benchreceipt.verify import evaluate


def _verdict_with_receipt_mutation(tmp_path: Path, mutate) -> dict:
    return evaluate_evidence(make_evidence(tmp_path, mutate))


def test_receipt_extra_top_level_field_is_invalid(tmp_path: Path):
    """An unknown top-level receipt field is INVALID_RECEIPT."""
    def mutate(receipt, _evidence):
        receipt["forged_note"] = "trust me"

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_cannot_carry_a_status_field(tmp_path: Path):
    """A forged ``status: BOUND_PASS`` inside a receipt must not pass.

    Receipts carry no status field at all; smuggling one in is a
    schema violation, and the verifier never reads it as a verdict.
    """
    def mutate(receipt, _evidence):
        receipt["status"] = "BOUND_PASS"

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_wrong_schema_const_is_invalid(tmp_path: Path):
    """A receipt claiming another schema id is INVALID_RECEIPT."""
    def mutate(receipt, _evidence):
        receipt["schema"] = "benchreceipt.run/v2"

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_wrong_source_mode_enum_is_invalid(tmp_path: Path):
    """``git.source_mode`` outside its enum is INVALID_RECEIPT."""
    def mutate(receipt, _evidence):
        receipt["git"]["source_mode"] = "whatever"

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_uppercase_sha_is_invalid(tmp_path: Path):
    """Uppercase hex in ``git.head_sha`` fails the schema pattern."""
    def mutate(receipt, _evidence):
        receipt["git"]["head_sha"] = "A" * 40

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_junit_counts_wrong_type_is_invalid(tmp_path: Path):
    """``junit.tests`` as a string is INVALID_RECEIPT."""
    def mutate(receipt, _evidence):
        receipt["junit"]["tests"] = "10"

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_report_kind_wrong_enum_is_invalid(tmp_path: Path):
    """``reports[].kind`` outside {junit, lcov} is INVALID_RECEIPT."""
    def mutate(receipt, _evidence):
        receipt["reports"][0]["kind"] = "coverage"

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_missing_required_field_is_invalid(tmp_path: Path):
    """A receipt without ``ci`` is INVALID_RECEIPT, not a pass."""
    def mutate(receipt, _evidence):
        del receipt["ci"]

    verdict = _verdict_with_receipt_mutation(tmp_path, mutate)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_not_an_object_is_invalid(tmp_path: Path):
    """A receipt file holding a JSON array is INVALID_RECEIPT."""
    evidence = make_evidence(tmp_path)
    (evidence / "unit-linux-py312" / "receipt.json").write_text(
        json.dumps([1, 2, 3]), encoding="utf-8"
    )
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_receipt_invalid_json_is_invalid(tmp_path: Path):
    """A receipt file that is not JSON at all is INVALID_RECEIPT."""
    evidence = make_evidence(tmp_path)
    (evidence / "unit-linux-py312" / "receipt.json").write_text(
        "{not json", encoding="utf-8"
    )
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_job_dir_without_receipt_is_invalid_not_missing(tmp_path: Path):
    """A job dir with no receipt.json counts as invalid, never silent."""
    evidence = make_evidence(tmp_path)
    (evidence / "unit-linux-py312" / "receipt.json").unlink()
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    # The job is present-but-invalid, not "missing": it must not be
    # silently dropped from the matrix comparison.
    assert verdict["missing_jobs"] == [], verdict
    assert_not_pass(verdict)


# --- policy confusion -------------------------------------------------------


def test_policy_unknown_top_level_field_is_invalid(tmp_path: Path):
    """A policy with an unknown field is INVALID_POLICY."""
    policy = copy.deepcopy(POLICY)
    policy["unexpected_field"] = "BOUND_PASS"
    verdict = evaluate(policy, EXPECTED_SHA, make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict
    assert verdict["jobs_verified"] == 0, verdict


def test_policy_unknown_field_inside_reports_is_invalid(tmp_path: Path):
    """An unknown field inside policy ``reports`` is INVALID_POLICY."""
    policy = copy.deepcopy(POLICY)
    policy["reports"] = {"junit": "required", "lcov": "optional", "xml": "required"}
    verdict = evaluate(policy, EXPECTED_SHA, make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict


def test_policy_wrong_source_mode_enum_is_invalid(tmp_path: Path):
    """A policy source_mode outside its enum is INVALID_POLICY."""
    policy = copy.deepcopy(POLICY)
    policy["source_mode"] = "whatever"
    verdict = evaluate(policy, EXPECTED_SHA, make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict


def test_policy_wrong_schema_version_is_invalid(tmp_path: Path):
    """``schema_version: 2`` is INVALID_POLICY (only 1 is valid)."""
    policy = copy.deepcopy(POLICY)
    policy["schema_version"] = 2
    verdict = evaluate(policy, EXPECTED_SHA, make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict


def test_policy_empty_required_jobs_is_invalid(tmp_path: Path):
    """An empty required_jobs list would make the matrix check vacuous."""
    policy = copy.deepcopy(POLICY)
    policy["required_jobs"] = []
    verdict = evaluate(policy, EXPECTED_SHA, make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict


def test_policy_run_identity_field_is_invalid(tmp_path: Path):
    """Run identity (expected_source_sha) must not live in the policy."""
    policy = copy.deepcopy(POLICY)
    policy["expected_source_sha"] = EXPECTED_SHA
    verdict = evaluate(policy, EXPECTED_SHA, make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict


def test_policy_not_a_dict_is_invalid(tmp_path: Path):
    """A non-dict policy is INVALID_POLICY, never a default policy."""
    verdict = evaluate(["not", "a", "dict"], EXPECTED_SHA, make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict


def test_expected_sha_wrong_format_is_invalid(tmp_path: Path):
    """A malformed expected_source_sha argument is INVALID_POLICY."""
    verdict = evaluate(POLICY, "XYZ", make_evidence(tmp_path))
    assert verdict["status"] == "INVALID", verdict
    assert verdict["reason_codes"] == ["INVALID_POLICY"], verdict
