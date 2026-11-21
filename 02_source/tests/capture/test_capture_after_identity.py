"""After-identity fields (spec v1.1.0, ADR-005 / P0-01 fix).

``capture`` must always emit ``git.head_sha_after`` /
``git.tree_sha_after`` from the after-run snapshot, and ``verify``
must flag a run whose after identity differs from its before
identity — or whose after fields are inconsistently present — as
``SOURCE_MUTATED_DURING_RUN``. The two t011 fail-first tests cover
the real checkout / empty-commit variants; these tests pin the
field-level contract: clean runs emit equal after values and still
verify BOUND_PASS, a half-present after pair fails closed, and a
malformed after value is schema-invalid.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchreceipt.capture import capture
from benchreceipt.schema import SchemaValidationError, validate_against_schema
from benchreceipt.verify import evaluate

JUNIT_XML = (
    '<?xml version="1.0"?>\n'
    '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
    ' skipped="0">'
    '<testcase classname="s" name="t1"/>'
    '<testcase classname="s" name="t2"/>'
    "</testsuite></testsuites>\n"
)

POLICY = {
    "schema_version": 1,
    "source_mode": "event_sha",
    "expected_workflow": "local",
    "required_jobs": ["unit-linux-py312"],
    "min_tests": 1,
    "require_clean_source_after": True,
    "same_tree_across_jobs": True,
    "same_run_id": True,
    "same_run_attempt": True,
    "reports": {"junit": "required", "lcov": "optional"},
}


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "fix-p0-01@example.invalid")
    _git(path, "config", "user.name", "P027-FIX-P0-01")
    (path / "code.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "c1")
    return path


def _capture_green(repo: Path) -> dict:
    script = f"open('junit.xml', 'w').write({JUNIT_XML!r})"
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", script],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    assert result.source_mutated_during_run is False
    receipt_path = repo / ".benchreceipt" / "evidence" / "unit-linux-py312" / "receipt.json"
    return json.loads(receipt_path.read_text(encoding="utf-8"))


def _write_receipt(repo: Path, receipt: dict) -> None:
    path = repo / ".benchreceipt" / "evidence" / "unit-linux-py312" / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_clean_capture_emits_after_identity_and_passes(tmp_path: Path):
    """A clean run emits after == before and still verifies BOUND_PASS."""
    repo = _make_repo(tmp_path / "repo")
    sha = _git(repo, "rev-parse", "HEAD")
    receipt = _capture_green(repo)
    assert receipt["git"]["head_sha"] == sha
    assert receipt["git"]["head_sha_after"] == sha
    assert receipt["git"]["tree_sha_after"] == receipt["git"]["tree_sha"]
    validate_against_schema(receipt, "run")
    verdict = evaluate(POLICY, sha, repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 1, verdict


def test_half_present_after_pair_fails_closed(tmp_path: Path):
    """Only one after field present is inconsistent evidence: UNBOUND."""
    repo = _make_repo(tmp_path / "repo")
    sha = _git(repo, "rev-parse", "HEAD")
    receipt = _capture_green(repo)
    del receipt["git"]["tree_sha_after"]  # head_sha_after stays
    validate_against_schema(receipt, "run")  # still schema-valid: optional
    _write_receipt(repo, receipt)
    verdict = evaluate(POLICY, sha, repo / ".benchreceipt" / "evidence")
    assert verdict["status"] != "BOUND_PASS", verdict
    assert "SOURCE_MUTATED_DURING_RUN" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 0, verdict


def test_both_after_fields_missing_fails_closed_with_missing_field(tmp_path: Path):
    """P0-R1-01 (spec v1.2.0, ADR-007): BOTH after fields absent is
    UNBOUND with MISSING_FIELD, never BOUND_PASS — the receipt cannot
    prove the run's HEAD/tree did not change mid-run, so the
    dirty/digest checks alone must not pass it. The schema still
    accepts the receipt (both fields stay optional); only the
    verdict changes. This is the exact R1 false-PASS shape: the
    reviewer deleted both after fields from a clean e5/e6-style
    receipt and got BOUND_PASS from the old verifier."""
    repo = _make_repo(tmp_path / "repo")
    sha = _git(repo, "rev-parse", "HEAD")
    receipt = _capture_green(repo)
    assert receipt["git"]["head_sha_after"] == sha
    del receipt["git"]["head_sha_after"]
    del receipt["git"]["tree_sha_after"]
    validate_against_schema(receipt, "run")  # still schema-valid: optional
    _write_receipt(repo, receipt)
    verdict = evaluate(POLICY, sha, repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "UNBOUND", verdict
    assert verdict["reason_codes"] == ["MISSING_FIELD"], verdict
    assert verdict["report_errors"] == [
        {"code": "MISSING_FIELD",
         "message": "missing git.head_sha_after and git.tree_sha_after",
         "job_id": "unit-linux-py312"}
    ], verdict
    assert verdict["jobs_verified"] == 0, verdict


def test_malformed_after_value_is_schema_invalid(tmp_path: Path):
    """A non-40-hex after value fails schema validation (never trusted)."""
    repo = _make_repo(tmp_path / "repo")
    sha = _git(repo, "rev-parse", "HEAD")
    receipt = _capture_green(repo)
    receipt["git"]["head_sha_after"] = "NOT-A-SHA"
    with pytest.raises(SchemaValidationError):
        validate_against_schema(receipt, "run")
    _write_receipt(repo, receipt)
    verdict = evaluate(POLICY, sha, repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 0, verdict
