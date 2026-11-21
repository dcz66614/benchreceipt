"""benchreceipt.run/v1 schema tests (P027-T002)."""

import copy

import pytest

from benchreceipt.schema import SchemaValidationError, validate_against_schema

SHA40_A = "a" * 40
SHA40_B = "b" * 40
SHA64_C = "c" * 64
SHA64_D = "d" * 64


def valid_receipt():
    """Minimal valid receipt per PROJECT_BOOK §6.2."""
    return {
        "schema": "benchreceipt.run/v1",
        "job_id": "unit-linux-py312",
        "matrix": {"os": "ubuntu-latest", "python": "3.12"},
        "git": {
            "head_sha": SHA40_A,
            "tree_sha": SHA40_B,
            "source_mode": "pr_head",
            "expected_source_sha": SHA40_A,
            "dirty_before": False,
            "dirty_after": False,
        },
        "ci": {
            "provider": "github-actions",
            "run_id": "9001",
            "run_attempt": 2,
            "workflow": "CI",
            "event_name": "pull_request",
        },
        "command": {
            "argv_sha256": SHA64_C,
            "display": "python -m pytest -q",
            "exit_code": 0,
        },
        "runner": {"os": "Linux", "arch": "x86_64", "python": "3.12.3"},
        "junit": {"tests": 18, "failures": 0, "errors": 0, "skipped": 1},
        "reports": [
            {
                "kind": "junit",
                "path": "artifacts/junit.xml",
                "size_bytes": 2048,
                "sha256": SHA64_D,
            }
        ],
    }


def assert_invalid(receipt):
    with pytest.raises(SchemaValidationError):
        validate_against_schema(receipt, "run")


def test_valid_receipt_passes():
    validate_against_schema(valid_receipt(), "run")


def test_valid_receipt_by_full_schema_id():
    validate_against_schema(valid_receipt(), "benchreceipt.run/v1")


def test_missing_required_field_fails():
    receipt = valid_receipt()
    del receipt["git"]
    assert_invalid(receipt)


def test_missing_nested_required_field_fails():
    receipt = valid_receipt()
    del receipt["git"]["tree_sha"]
    assert_invalid(receipt)


def test_wrong_enum_fails():
    receipt = valid_receipt()
    receipt["git"]["source_mode"] = "head"
    assert_invalid(receipt)


def test_wrong_report_kind_fails():
    receipt = valid_receipt()
    receipt["reports"][0]["kind"] = "cobertura"
    assert_invalid(receipt)


def test_absolute_report_path_fails():
    receipt = valid_receipt()
    receipt["reports"][0]["path"] = "/etc/passwd"
    assert_invalid(receipt)


def test_dotdot_report_path_fails():
    for bad in ("../secret.xml", "artifacts/../../secret.xml", "artifacts/../x.xml"):
        receipt = valid_receipt()
        receipt["reports"][0]["path"] = bad
        assert_invalid(receipt)


def test_relative_report_path_passes():
    receipt = valid_receipt()
    receipt["reports"][0]["path"] = "artifacts/sub/junit.xml"
    validate_against_schema(receipt, "run")


def test_oversized_string_fails():
    receipt = valid_receipt()
    receipt["job_id"] = "j" * 129
    assert_invalid(receipt)


def test_oversized_array_fails():
    receipt = valid_receipt()
    receipt["reports"] = [
        {"kind": "junit", "path": f"artifacts/r{i}.xml", "size_bytes": 1, "sha256": SHA64_D}
        for i in range(33)
    ]
    assert_invalid(receipt)


def test_bad_sha_patterns_fail():
    receipt = valid_receipt()
    receipt["git"]["head_sha"] = "A" * 40  # uppercase: not lowercase hex
    assert_invalid(receipt)
    receipt = valid_receipt()
    receipt["git"]["head_sha"] = "a" * 39  # abbreviated SHA
    assert_invalid(receipt)
    receipt = valid_receipt()
    receipt["command"]["argv_sha256"] = "c" * 63
    assert_invalid(receipt)


def test_additional_property_fails():
    receipt = valid_receipt()
    receipt["unexpected_field"] = "boom"
    assert_invalid(receipt)


def test_boolean_is_not_an_integer():
    receipt = valid_receipt()
    receipt["junit"]["tests"] = True
    assert_invalid(receipt)


def test_junit_optional_lcov_only_receipt_passes():
    receipt = valid_receipt()
    del receipt["junit"]
    receipt["reports"] = [
        {"kind": "lcov", "path": "artifacts/lcov.info", "size_bytes": 512, "sha256": SHA64_D}
    ]
    validate_against_schema(receipt, "run")


def test_optional_source_state_accepted():
    receipt = valid_receipt()
    receipt["source_state_before"] = {"dirty": False, "tracked_diff_sha256": "e" * 64}
    receipt["source_state_after"] = {"dirty": False, "tracked_diff_sha256": "e" * 64}
    validate_against_schema(receipt, "run")


def test_optional_timestamps_accepted_and_bad_format_rejected():
    receipt = valid_receipt()
    receipt["started_at"] = "2026-11-17T07:00:00Z"
    receipt["finished_at"] = "2026-11-17T07:00:05.123Z"
    validate_against_schema(receipt, "run")
    bad = copy.deepcopy(receipt)
    bad["started_at"] = "17 Nov 2026"
    assert_invalid(bad)


def test_empty_reports_array_is_schema_valid():
    # Empty reports is a verify-time UNBOUND (T008), not a schema INVALID.
    receipt = valid_receipt()
    receipt["reports"] = []
    validate_against_schema(receipt, "run")
