"""capture JUnit summary tests (P027-FIX-capture-junit).

Regression tests for the T003/T008 seam: capture must emit the parsed
JUnit summary (``receipt["junit"]``) so a green real capture can verify
BOUND_PASS. Before the fix, tests (a), (b) and (e) FAIL — the receipt
carries no ``junit`` key and verify returns UNBOUND/MISSING_FIELD.

Every test builds a real synthetic git repo in a tmp dir (same helpers
as ``test_capture.py``) and drives the real :func:`benchreceipt.capture.capture`
plus :func:`benchreceipt.verify.evaluate`.
"""

import subprocess
import sys
from pathlib import Path

from benchreceipt.capture import capture
from benchreceipt.schema import validate_against_schema
from benchreceipt.verify import evaluate

JOB_ID = "unit-linux-py312"


def make_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    """Create a synthetic git repo at ``path`` with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "BenchReceipt Test"],
        check=True,
    )
    for name, content in (files or {"tracked.txt": "hello\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "initial"], check=True)
    return path


def git_rev(path: Path, arg: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(path), "rev-parse", arg],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()

# A green 2-test JUnit file: counted testcases == attributes, so the
# T005 parser accepts it and the summary is {2, 0, 0, 0}.
GREEN_JUNIT = (
    '<?xml version="1.0"?>\n'
    '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
    ' skipped="0">'
    '<testcase classname="s" name="t1"/>'
    '<testcase classname="s" name="t2"/>'
    "</testsuite></testsuites>\n"
)

# A mixed 4-test file: 1 pass, 1 failure, 1 error, 1 skipped.
# Attributes match the counted elements exactly.
MIXED_JUNIT = (
    '<?xml version="1.0"?>\n'
    '<testsuites><testsuite name="s" tests="4" failures="1" errors="1"'
    ' skipped="1">'
    '<testcase classname="s" name="pass"/>'
    '<testcase classname="s" name="fail"><failure message="boom"/></testcase>'
    '<testcase classname="s" name="err"><error message="kaboom"/></testcase>'
    '<testcase classname="s" name="skip"><skipped/></testcase>'
    "</testsuite></testsuites>\n"
)

MALFORMED_JUNIT = "this is not xml at all <oops\n"


def _policy(*, min_tests: int = 1) -> dict:
    """A policy matching a local capture: event_sha + workflow local."""
    return {
        "schema_version": 1,
        "source_mode": "event_sha",
        "expected_workflow": "local",
        "required_jobs": [JOB_ID],
        "min_tests": min_tests,
        "require_clean_source_after": False,
        "same_tree_across_jobs": False,
        "same_run_id": False,
        "same_run_attempt": False,
        "reports": {"junit": "required", "lcov": "optional"},
    }


def _run_capture(repo: Path, *, junit_text: str | None, argv=None):
    """Run capture with ``junit_text`` pre-written (or none) at repo root."""
    junit_path = None
    if junit_text is not None:
        junit_path = repo / "junit.xml"
        junit_path.write_text(junit_text, encoding="utf-8")
    if argv is None:
        argv = [sys.executable, "-c", "print('ok')"]
    return capture(
        job_id=JOB_ID,
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=argv,
        repo_path=repo,
        junit_path=junit_path,
        cwd=repo,
        env={},
    )


def test_valid_junit_summary_matches_parsed_file(tmp_path: Path):
    """(a) Valid JUnit -> receipt junit == the parsed counts."""
    repo = make_repo(tmp_path / "repo")
    result = _run_capture(repo, junit_text=MIXED_JUNIT)
    receipt = result.receipt
    assert result.exit_code == 0
    validate_against_schema(receipt, "run")
    assert receipt["junit"] == {
        "tests": 4,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
    }


def test_failing_junit_summary_present_and_verify_bound_fail(tmp_path: Path):
    """(b) Failing JUnit -> summary present (failures>0); verify BOUND_FAIL."""
    repo = make_repo(tmp_path / "repo")
    result = _run_capture(
        repo,
        junit_text=MIXED_JUNIT,
        argv=[sys.executable, "-c", "import sys; sys.exit(1)"],
    )
    assert result.exit_code == 1  # command exit passes through
    assert result.receipt["junit"]["failures"] == 1
    assert result.receipt["junit"]["errors"] == 1
    verdict = evaluate(
        _policy(),
        git_rev(repo, "HEAD"),
        result.evidence_dir.parent,
    )
    assert verdict["status"] == "BOUND_FAIL", verdict
    assert "JUNIT_FAILED" in verdict["reason_codes"]
    assert verdict["jobs_verified"] == 0


def test_malformed_junit_omits_summary_and_never_bound_pass(
    tmp_path: Path, capsys
):
    """(c) Malformed JUnit -> NO fabricated summary; verify never BOUND_PASS.

    Fail-closed path: capture still writes the receipt and passes the
    command's exit code through, warns on stderr, and verify's own
    artifact re-parse yields JUNIT_MALFORMED -> INVALID (which
    outranks the MISSING_FIELD/UNBOUND from the absent summary).
    """
    repo = make_repo(tmp_path / "repo")
    result = _run_capture(repo, junit_text=MALFORMED_JUNIT)
    assert result.exit_code == 0
    assert "junit" not in result.receipt
    validate_against_schema(result.receipt, "run")
    assert (result.evidence_dir / "receipt.json").is_file()
    captured = capsys.readouterr()
    assert "JUNIT_MALFORMED" in captured.err
    verdict = evaluate(
        _policy(),
        git_rev(repo, "HEAD"),
        result.evidence_dir.parent,
    )
    assert verdict["status"] != "BOUND_PASS", verdict
    assert verdict["status"] == "INVALID", verdict
    assert "JUNIT_MALFORMED" in verdict["reason_codes"]
    assert verdict["jobs_verified"] == 0


def test_no_junit_flag_means_no_junit_key(tmp_path: Path):
    """(d) No --junit -> no junit key (unchanged behaviour)."""
    repo = make_repo(tmp_path / "repo")
    result = _run_capture(repo, junit_text=None)
    assert result.exit_code == 0
    assert "junit" not in result.receipt
    validate_against_schema(result.receipt, "run")


def test_green_capture_verifies_bound_pass_end_to_end(tmp_path: Path):
    """(e) Green capture + matching policy -> verify BOUND_PASS, exit 0.

    Direct regression test for the defect: before the fix this returns
    UNBOUND with MISSING_FIELD and jobs_verified 0.
    """
    repo = make_repo(tmp_path / "repo")
    result = _run_capture(repo, junit_text=GREEN_JUNIT)
    assert result.exit_code == 0
    assert result.receipt["junit"] == {
        "tests": 2,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    verdict = evaluate(
        _policy(),
        git_rev(repo, "HEAD"),
        result.evidence_dir.parent,
    )
    assert verdict["status"] == "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 1
    assert verdict["reason_codes"] == []


def test_lie_attributes_are_malformed_not_trusted(tmp_path: Path):
    """Attributes that disagree with counted testcases are malformed.

    Guards the 'summary must reflect the PARSED file' rule: a file
    claiming tests="2" with zero testcases must never yield a
    fabricated {tests: 2} summary.
    """
    repo = make_repo(tmp_path / "repo")
    lying = (
        '<?xml version="1.0"?>\n'
        '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
        ' skipped="0"></testsuite></testsuites>\n'
    )
    result = _run_capture(repo, junit_text=lying)
    assert "junit" not in result.receipt
    verdict = evaluate(
        _policy(),
        git_rev(repo, "HEAD"),
        result.evidence_dir.parent,
    )
    assert verdict["status"] != "BOUND_PASS", verdict
