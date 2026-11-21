"""benchreceipt.result/v1 schema tests (P027-T002).

Examples A/B/C are PROJECT_BOOK §12.2/§12.3 verbatim shapes.
"""

import pytest

from benchreceipt.schema import SchemaValidationError, validate_against_schema


def assert_invalid(result):
    with pytest.raises(SchemaValidationError):
        validate_against_schema(result, "result")


def test_sample_a_bound_pass():
    # PROJECT_BOOK §12.2
    validate_against_schema(
        {
            "schema": "benchreceipt.result/v1",
            "status": "BOUND_PASS",
            "missing_jobs": [],
            "unexpected_jobs": [],
            "identity_mismatches": [],
            "report_errors": [],
            "jobs_verified": 2,
        },
        "result",
    )


def test_sample_b_mixed_attempt_unbound():
    # PROJECT_BOOK §12.3 sample B
    validate_against_schema(
        {
            "schema": "benchreceipt.result/v1",
            "status": "UNBOUND",
            "reason_codes": ["RUN_ATTEMPT_MISMATCH"],
            "jobs_verified": 1,
        },
        "result",
    )


def test_sample_c_source_mode_mismatch():
    # PROJECT_BOOK §12.3 sample C
    validate_against_schema(
        {
            "schema": "benchreceipt.result/v1",
            "status": "UNBOUND",
            "reason_codes": ["SOURCE_SHA_MISMATCH"],
            "expected_source_mode": "pr_head",
            "jobs_verified": 0,
        },
        "result",
    )


def test_internal_error_status_is_valid():
    validate_against_schema(
        {
            "schema": "benchreceipt.result/v1",
            "status": "INTERNAL_ERROR",
            "reason_codes": ["INTERNAL_ERROR"],
            "jobs_verified": 0,
        },
        "result",
    )


def test_missing_jobs_verified_fails():
    assert_invalid({"schema": "benchreceipt.result/v1", "status": "BOUND_PASS"})


def test_bad_status_fails():
    assert_invalid(
        {
            "schema": "benchreceipt.result/v1",
            "status": "PASS",
            "jobs_verified": 1,
        }
    )


def test_bad_reason_code_shape_fails():
    assert_invalid(
        {
            "schema": "benchreceipt.result/v1",
            "status": "UNBOUND",
            "reason_codes": ["source sha mismatch"],
            "jobs_verified": 0,
        }
    )


def test_identity_mismatch_item_shape():
    validate_against_schema(
        {
            "schema": "benchreceipt.result/v1",
            "status": "UNBOUND",
            "reason_codes": ["SOURCE_SHA_MISMATCH"],
            "identity_mismatches": [
                {
                    "job_id": "unit-linux-py312",
                    "field": "git.head_sha",
                    "expected": "a" * 40,
                    "actual": "b" * 40,
                },
                {
                    "job_id": "unit-windows-py312",
                    "field": "ci.run_attempt",
                    "expected": 2,
                    "actual": 1,
                },
            ],
            "jobs_verified": 0,
        },
        "result",
    )
    assert_invalid(
        {
            "schema": "benchreceipt.result/v1",
            "status": "UNBOUND",
            "identity_mismatches": [{"job_id": "unit-linux-py312"}],
            "jobs_verified": 0,
        }
    )


def test_report_error_item_shape():
    validate_against_schema(
        {
            "schema": "benchreceipt.result/v1",
            "status": "UNBOUND",
            "report_errors": [
                {
                    "code": "REPORT_HASH_MISMATCH",
                    "message": "sha256 mismatch for artifacts/junit.xml",
                    "job_id": "unit-linux-py312",
                    "path": "artifacts/junit.xml",
                }
            ],
            "jobs_verified": 0,
        },
        "result",
    )
