"""Policy loader completion tests (P027-T007).

Covers what the T002 schema tests did not pin down at the loader
level: PolicyInvalid messages naming EVERY missing/invalid field,
unknown-key rejection (top-level and inside sections), the
run-identity-field ban (ADR-001 decision 12), security defaulting,
TOML parse errors, and non-dict / wrong-type values.

The frozen schema (``benchreceipt.policy/v1``) is the authority; these
tests assert the loader's observable behaviour (``load_policy`` /
``validate_policy`` raising :class:`PolicyInvalid`), not the schema
file itself. The example TOML is the PROJECT_BOOK §6.3 policy.
"""

from pathlib import Path

import pytest

from benchreceipt.policy import PolicyInvalid, load_policy, validate_policy

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"

REQUIRED_FIELDS = [
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
]

RUN_IDENTITY_FIELDS = [
    "expected_source_sha",
    "expected_run_id",
    "run_id",
    "workflow_run_id",
    "expected_attempt",
    "run_attempt",
]


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


def _toml_text(policy: dict) -> str:
    """Render a policy dict as TOML for load_policy file tests.

    Only the shapes used in this file are supported: scalars, a list
    of strings, and one-level ``[reports]`` / ``[security]`` tables.
    """
    lines = []
    for key, value in policy.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for sub_key, sub_value in value.items():
                lines.append(f"{sub_key} = {_toml_scalar(sub_value)}")
        elif isinstance(value, list):
            items = ", ".join(f'"{item}"' for item in value)
            lines.append(f"{key} = [{items}]")
        else:
            lines.append(f"{key} = {_toml_scalar(value)}")
    return "\n".join(lines) + "\n"


def _toml_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


# --- valid policies ------------------------------------------------------


def test_example_toml_loads():
    loaded = load_policy(EXAMPLES_DIR / "benchreceipt.toml")
    assert loaded["schema_version"] == 1
    assert loaded["source_mode"] == "pr_head"
    assert loaded["required_jobs"] == [
        "unit-linux-py312",
        "unit-linux-py313",
        "unit-windows-py312",
        "unit-windows-py313",
    ]
    assert loaded["security"] == {
        "store_stdout": False,
        "store_stderr": False,
        "store_full_environment": False,
    }


def test_valid_policy_dict_passes_and_is_not_mutated():
    policy = valid_policy()
    snapshot = valid_policy()
    loaded = validate_policy(policy)
    assert loaded["required_jobs"] == [
        "unit-linux-py312",
        "unit-linux-py313",
        "unit-windows-py312",
        "unit-windows-py313",
    ]
    assert policy == snapshot  # validate_policy returns a copy, no mutation


# --- missing fields: every one named --------------------------------------


@pytest.mark.parametrize("missing", REQUIRED_FIELDS)
def test_each_missing_required_field_is_invalid_and_named(missing):
    policy = valid_policy()
    del policy[missing]
    with pytest.raises(PolicyInvalid) as excinfo:
        validate_policy(policy)
    assert missing in str(excinfo.value), (
        f"PolicyInvalid for missing {missing!r} must name the field: {excinfo.value}"
    )


def test_multiple_missing_fields_all_named_not_just_first():
    policy = valid_policy()
    for field in ("schema_version", "source_mode", "required_jobs", "min_tests"):
        del policy[field]
    with pytest.raises(PolicyInvalid) as excinfo:
        validate_policy(policy)
    message = str(excinfo.value)
    for field in ("schema_version", "source_mode", "required_jobs", "min_tests"):
        assert field in message, f"message must name {field!r}: {message}"


def test_empty_toml_file_names_all_missing_fields(tmp_path):
    empty = tmp_path / "empty.toml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(PolicyInvalid) as excinfo:
        load_policy(empty)
    message = str(excinfo.value)
    for field in REQUIRED_FIELDS:
        assert field in message, f"message must name {field!r}: {message}"


def test_empty_required_jobs_is_invalid_not_empty_set_pass(tmp_path):
    policy = valid_policy()
    policy["required_jobs"] = []
    with pytest.raises(PolicyInvalid, match="required_jobs"):
        validate_policy(policy)
    bad = tmp_path / "bad.toml"
    bad.write_text(_toml_text(policy), encoding="utf-8")
    with pytest.raises(PolicyInvalid, match="required_jobs"):
        load_policy(bad)


# --- unknown keys ----------------------------------------------------------


def test_unknown_top_level_key_is_invalid():
    policy = valid_policy()
    policy["surprise_field"] = True
    with pytest.raises(PolicyInvalid, match="surprise_field"):
        validate_policy(policy)


@pytest.mark.parametrize("field", RUN_IDENTITY_FIELDS)
def test_run_identity_field_in_policy_is_invalid_and_named(field):
    policy = valid_policy()
    policy[field] = "a" * 40 if "sha" in field else 9001
    with pytest.raises(PolicyInvalid) as excinfo:
        validate_policy(policy)
    assert field in str(excinfo.value)


def test_expected_source_sha_in_toml_file_is_invalid(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        _toml_text(valid_policy()) + 'expected_source_sha = "' + "a" * 40 + '"\n',
        encoding="utf-8",
    )
    with pytest.raises(PolicyInvalid, match="expected_source_sha"):
        load_policy(bad)


def test_unknown_key_inside_reports_section_is_invalid():
    policy = valid_policy()
    policy["reports"]["cobertura"] = "required"
    with pytest.raises(PolicyInvalid, match="cobertura"):
        validate_policy(policy)


def test_unknown_key_inside_security_section_is_invalid():
    policy = valid_policy()
    policy["security"]["store_everything"] = True
    with pytest.raises(PolicyInvalid, match="store_everything"):
        validate_policy(policy)


def test_missing_report_declaration_is_invalid():
    policy = valid_policy()
    del policy["reports"]["lcov"]
    with pytest.raises(PolicyInvalid, match="lcov"):
        validate_policy(policy)


# --- security defaulting ---------------------------------------------------


def test_absent_security_section_defaults_all_false(tmp_path):
    policy = valid_policy()
    del policy["security"]
    assert validate_policy(policy)["security"] == {
        "store_stdout": False,
        "store_stderr": False,
        "store_full_environment": False,
    }
    no_sec = tmp_path / "no-sec.toml"
    no_sec.write_text(_toml_text(policy), encoding="utf-8")
    assert load_policy(no_sec)["security"] == {
        "store_stdout": False,
        "store_stderr": False,
        "store_full_environment": False,
    }


def test_partial_security_section_fills_missing_false_and_honours_present():
    policy = valid_policy()
    policy["security"] = {"store_stdout": True}
    assert validate_policy(policy)["security"] == {
        "store_stdout": True,
        "store_stderr": False,
        "store_full_environment": False,
    }
    policy["security"] = {"store_stderr": True, "store_full_environment": False}
    assert validate_policy(policy)["security"] == {
        "store_stdout": False,
        "store_stderr": True,
        "store_full_environment": False,
    }


def test_security_wrong_type_is_invalid():
    for bad_security in ("yes", ["store_stdout"], 1, True):
        policy = valid_policy()
        policy["security"] = bad_security
        with pytest.raises(PolicyInvalid):
            validate_policy(policy)
    policy = valid_policy()
    policy["security"] = {"store_stdout": "yes"}
    with pytest.raises(PolicyInvalid, match="store_stdout"):
        validate_policy(policy)


# --- TOML parse errors / missing file --------------------------------------


def test_malformed_toml_is_invalid(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("source_mode = [\n", encoding="utf-8")
    with pytest.raises(PolicyInvalid):
        load_policy(bad)


def test_duplicate_toml_key_is_invalid(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('source_mode = "pr_head"\nsource_mode = "pr_head"\n', encoding="utf-8")
    with pytest.raises(PolicyInvalid):
        load_policy(bad)


def test_missing_file_is_invalid():
    with pytest.raises(PolicyInvalid):
        load_policy("/nonexistent/no-such-policy.toml")


def test_directory_as_policy_path_is_invalid(tmp_path):
    with pytest.raises(PolicyInvalid):
        load_policy(tmp_path)


# --- non-dict / wrong-type values ------------------------------------------


@pytest.mark.parametrize("bad", [None, "not a table", 42, ["not", "a", "table"], True])
def test_non_dict_policy_is_invalid(bad):
    with pytest.raises(PolicyInvalid):
        validate_policy(bad)


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("schema_version", "1"),
        ("schema_version", 2),
        ("source_mode", "head"),
        ("source_mode", 1),
        ("expected_workflow", ""),
        ("expected_workflow", 42),
        ("required_jobs", "unit-linux-py312"),
        ("required_jobs", ["unit-linux-py312", "unit-linux-py312"]),
        ("required_jobs", [""]),
        ("min_tests", "1"),
        ("min_tests", -1),
        ("min_tests", True),
        ("require_clean_source_after", "true"),
        ("same_tree_across_jobs", 1),
        ("same_run_id", "yes"),
        ("same_run_attempt", None),
        ("reports", []),
        ("reports", {"junit": "always"}),
        ("reports", {"junit": "required"}),
    ],
)
def test_wrong_type_or_value_is_invalid(field, bad_value):
    policy = valid_policy()
    policy[field] = bad_value
    with pytest.raises(PolicyInvalid):
        validate_policy(policy)
