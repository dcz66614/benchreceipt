"""Shared helpers for the T011-resume adversarial tests (not a test module).

Builds evidence bundles from the frozen S0 ``n06-single-event-sha``
fixture (one green job, workflow ``CI``) and synthetic git repos for
capture-based probes. Only public APIs are used; no production
internals are patched.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from benchreceipt.verify import evaluate

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "s0"
N06_EVIDENCE = FIXTURES / "n06-single-event-sha" / "evidence"

EXPECTED_SHA = "a" * 40

POLICY: dict[str, Any] = {
    "schema_version": 1,
    "source_mode": "event_sha",
    "expected_workflow": "CI",
    "required_jobs": ["unit-linux-py312"],
    "min_tests": 1,
    "require_clean_source_after": True,
    "same_tree_across_jobs": True,
    "same_run_id": True,
    "same_run_attempt": True,
    "reports": {"junit": "required", "lcov": "optional"},
}

JUNIT_XML = (
    '<?xml version="1.0"?>\n'
    '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
    ' skipped="0">'
    '<testcase classname="s" name="t1"/>'
    '<testcase classname="s" name="t2"/>'
    "</testsuite></testsuites>\n"
)


def load_n06_receipt() -> dict[str, Any]:
    """A deep copy of the frozen n06 receipt dict."""
    return json.loads(
        (N06_EVIDENCE / "unit-linux-py312" / "receipt.json").read_text(
            encoding="utf-8"
        )
    )


def junit_bytes() -> bytes:
    """The frozen n06 JUnit artifact bytes."""
    return (N06_EVIDENCE / "unit-linux-py312" / "artifacts" / "junit.xml").read_bytes()


def make_evidence(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any], Path], None] | None = None,
    job_dir: str = "unit-linux-py312",
) -> Path:
    """Copy the n06 evidence tree to ``tmp_path/evidence``.

    ``mutate`` (optional) receives the receipt dict and the evidence
    dir before the receipt is written back, so a probe can forge
    exactly one field. Returns the evidence dir.
    """
    evidence = tmp_path / "evidence"
    shutil.copytree(N06_EVIDENCE, evidence)
    if mutate is not None:
        receipt_path = evidence / job_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        mutate(receipt, evidence)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return evidence


def evaluate_evidence(evidence_dir: Path, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run :func:`benchreceipt.verify.evaluate` on an evidence dir."""
    return evaluate(policy if policy is not None else POLICY, EXPECTED_SHA, evidence_dir)


def assert_not_pass(verdict: dict[str, Any]) -> None:
    """A tampered/confused input must never verify as BOUND_PASS."""
    assert verdict["status"] != "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 0, verdict


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def make_repo(path: Path) -> Path:
    """Synthetic repo with two commits differing in tracked content."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t011@example.invalid")
    _git(path, "config", "user.name", "P027-T011")
    (path / "code.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "c1")
    (path / "code.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "c2")
    return path


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")
