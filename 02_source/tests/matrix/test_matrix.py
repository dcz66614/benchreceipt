"""Matrix aggregator tests (P027-T007, PROJECT_BOOK §5.2).

Tests the pure function ``benchreceipt.matrix.aggregate_matrix``:
expected vs actual set diffs, duplicate counting, deterministic sorted
output, and the fail-closed empty-expected rule (an empty expected
set is PolicyInvalid, never an empty-set pass).

Reason-code mapping (frozen in ``02_source/docs/REASON_CODES.md``;
matrix.py returns the sets, verify.py maps them): missing ->
MATRIX_MISSING_JOB, unexpected -> MATRIX_UNEXPECTED_JOB, duplicate ->
MATRIX_DUPLICATE_JOB. No new reason codes are introduced here.
"""

import pytest

from benchreceipt.matrix import aggregate_matrix
from benchreceipt.policy import PolicyInvalid


def test_exact_match_returns_empty_lists():
    assert aggregate_matrix(
        ["unit-linux-py312", "unit-windows-py312"],
        ["unit-windows-py312", "unit-linux-py312"],
    ) == {"missing": [], "unexpected": [], "duplicate": []}


def test_missing_only():
    assert aggregate_matrix(
        ["a", "b", "c"],
        ["a"],
    ) == {"missing": ["b", "c"], "unexpected": [], "duplicate": []}


def test_unexpected_only():
    assert aggregate_matrix(
        ["a", "b"],
        ["a", "b", "extra-1", "extra-2"],
    ) == {"missing": [], "unexpected": ["extra-1", "extra-2"], "duplicate": []}


def test_duplicate_only():
    assert aggregate_matrix(
        ["a", "b"],
        ["a", "b", "b"],
    ) == {"missing": [], "unexpected": [], "duplicate": ["b"]}


def test_duplicate_counted_three_times():
    assert aggregate_matrix(["a"], ["a", "a", "a"]) == {
        "missing": [],
        "unexpected": [],
        "duplicate": ["a"],
    }


def test_all_three_at_once():
    assert aggregate_matrix(
        ["a", "b", "c"],
        ["a", "b", "b", "surprise"],
    ) == {"missing": ["c"], "unexpected": ["surprise"], "duplicate": ["b"]}


def test_empty_actual_is_all_missing():
    assert aggregate_matrix(["a", "b"], []) == {
        "missing": ["a", "b"],
        "unexpected": [],
        "duplicate": [],
    }


def test_empty_expected_is_invalid_not_empty_set_pass():
    with pytest.raises(PolicyInvalid, match="non-empty"):
        aggregate_matrix([], [])
    with pytest.raises(PolicyInvalid, match="non-empty"):
        aggregate_matrix([], ["a"])


def test_output_is_sorted_regardless_of_input_order():
    assert aggregate_matrix(
        ["z-job", "a-job", "m-job"],
        ["x-job", "m-job", "m-job", "b-job"],
    ) == {
        "missing": ["a-job", "z-job"],
        "unexpected": ["b-job", "x-job"],
        "duplicate": ["m-job"],
    }


def test_duplicate_unexpected_job_is_both_unexpected_and_duplicate():
    # Duplicate detection counts actual occurrences regardless of
    # whether the job was expected (same rule verify.py used inline).
    assert aggregate_matrix(["a"], ["a", "ghost", "ghost"]) == {
        "missing": [],
        "unexpected": ["ghost"],
        "duplicate": ["ghost"],
    }


def test_job_identity_is_job_id_string_only():
    # The same job_id twice is a duplicate no matter what else might
    # differ about the two receipts (matrix values, run, tree): this
    # function sees job ids only, per PROJECT_BOOK §5.1.
    assert aggregate_matrix(["a"], ["a", "a"])["duplicate"] == ["a"]
    # And distinct ids are distinct jobs even if they look similar.
    assert aggregate_matrix(["a-1", "a-2"], ["a-1", "a-2"]) == {
        "missing": [],
        "unexpected": [],
        "duplicate": [],
    }


def test_duplicate_expected_jobs_is_invalid():
    with pytest.raises(PolicyInvalid, match="duplicate"):
        aggregate_matrix(["a", "a"], ["a"])


def test_non_list_expected_is_invalid():
    with pytest.raises(PolicyInvalid):
        aggregate_matrix("a", ["a"])  # a bare string is not a job list
    with pytest.raises(PolicyInvalid):
        aggregate_matrix(None, ["a"])


def test_non_string_job_ids_are_invalid():
    with pytest.raises(PolicyInvalid):
        aggregate_matrix(["a", 1], ["a"])
    with pytest.raises(PolicyInvalid):
        aggregate_matrix(["a"], ["a", None])
    with pytest.raises(PolicyInvalid):
        aggregate_matrix([""], ["a"])
    with pytest.raises(PolicyInvalid):
        aggregate_matrix(["a"], [""])


def test_non_list_actual_is_invalid():
    with pytest.raises(PolicyInvalid):
        aggregate_matrix(["a"], "a")


def test_single_job_exact_match():
    assert aggregate_matrix(["only-job"], ["only-job"]) == {
        "missing": [],
        "unexpected": [],
        "duplicate": [],
    }
