"""benchreceipt.policy/v1 schema + TOML loader tests (P027-T002)."""

from pathlib import Path

import pytest

from benchreceipt.policy import PolicyInvalid, load_policy, validate_policy
from benchreceipt.schema import SchemaValidationError, validate_against_schema

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


def valid_policy():
    """Parsed form of examples/benchreceipt.toml (PROJECT_BOOK §6.3)."""
    return {
        "schema_version": 1,
        "source_mode": "pr_head",
        "expected_workflow": "CI",
        "required_jobs": [
            "unit-linux-py312",
            "unit-linux-py313",
            "unit-windows-py312",
            "unit-windows-py313",
        ],
        "min_tests": 1,
        "require_clean_source_after": True,
        "same_tree_across_jobs": True,
        "same_run_id": True,
        "same_run_attempt": True,
        "reports": {"junit": "required", "lcov": "optional"},
        "security": {
            "store_stdout": False,
            "store_stderr": False,
            "store_full_environment": False,
        },
    }


def test_example_toml_loads_and_validates():
    loaded = load_policy(EXAMPLES_DIR / "benchreceipt.toml")
    assert loaded["schema_version"] == 1
    assert loaded["source_mode"] == "pr_head"
    assert loaded["required_jobs"] == [
        "unit-linux-py312",
        "unit-linux-py313",
        "unit-windows-py312",
        "unit-windows-py313",
    ]
    assert loaded["reports"] == {"junit": "required", "lcov": "optional"}
    assert loaded["security"] == {
        "store_stdout": False,
        "store_stderr": False,
        "store_full_environment": False,
    }


def test_valid_policy_dict_passes_schema():
    validate_against_schema(valid_policy(), "policy")


@pytest.mark.parametrize(
    "missing",
    [
        "schema_version",
        "source_mode",
        "expected_workflow",
        "required_jobs",
        "min_tests",
        "require_clean_source_after",
        "same_tree_across_jobs",
        "same_run_id",
        "same_run_attempt",
        "reports",
    ],
)
def test_missing_required_field_is_invalid(missing):
    policy = valid_policy()
    del policy[missing]
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)
    with pytest.raises(SchemaValidationError):
        validate_against_schema(policy, "policy")


def test_missing_required_jobs_is_invalid_not_empty_pass():
    policy = valid_policy()
    del policy["required_jobs"]
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)


def test_empty_required_jobs_is_invalid():
    policy = valid_policy()
    policy["required_jobs"] = []
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)


def test_duplicate_required_jobs_is_invalid():
    policy = valid_policy()
    policy["required_jobs"] = ["unit-linux-py312", "unit-linux-py312"]
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)


def test_wrong_source_mode_enum_is_invalid():
    policy = valid_policy()
    policy["source_mode"] = "head"
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)


def test_wrong_schema_version_is_invalid():
    policy = valid_policy()
    policy["schema_version"] = 2
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)


def test_undeclared_report_requirement_is_invalid():
    policy = valid_policy()
    del policy["reports"]["lcov"]
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)


def test_missing_security_section_defaults_all_false():
    policy = valid_policy()
    del policy["security"]
    loaded = validate_policy(policy)
    assert loaded["security"] == {
        "store_stdout": False,
        "store_stderr": False,
        "store_full_environment": False,
    }


def test_partial_security_section_fills_missing_false():
    policy = valid_policy()
    policy["security"] = {"store_stdout": True}
    loaded = validate_policy(policy)
    assert loaded["security"] == {
        "store_stdout": True,
        "store_stderr": False,
        "store_full_environment": False,
    }


def test_extra_top_level_field_is_invalid():
    policy = valid_policy()
    policy["expected_source_sha"] = "a" * 40
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)


def test_malformed_toml_is_invalid(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("source_mode = [\n", encoding="utf-8")
    with pytest.raises(PolicyInvalid):
        load_policy(bad)


def test_missing_file_is_invalid():
    with pytest.raises(PolicyInvalid):
        load_policy("/nonexistent/no-such-policy.toml")


def test_non_dict_policy_is_invalid():
    with pytest.raises(PolicyInvalid):
        validate_policy(["not", "a", "table"])
