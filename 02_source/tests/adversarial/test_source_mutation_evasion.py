"""Adversarial regression: source-mutation evasion (P027-T011, P0-01).

FAIL-FIRST reproduction tests for SECURITY_FINDINGS.md P0-01. These tests
currently FAIL (the defect is real, production code untouched): a wrapped
command that changes HEAD mid-run — to a different commit with a clean
tree, or via an empty commit — leaves NO trace the verifier can see, so
``verify.evaluate`` returns ``BOUND_PASS`` for a receipt whose tests
actually ran against a different commit than the one the receipt claims.

Root cause (see 03_evidence/privacy/SECURITY_FINDINGS.md): the receipt
carries only the BEFORE ``git.head_sha`` / ``git.tree_sha`` plus
``source_state_before/after`` digests of ``git status --porcelain`` lines.
A clean-tree HEAD change leaves the porcelain output empty before AND
after, so the diff digests are identical and the dirty flags are both
False. ``capture`` itself detects the change (``CaptureResult.
source_mutated_during_run == True``) but that flag is NOT persisted in
the receipt — the frozen ``benchreceipt.run/v1`` schema has no
``head_sha_after`` / ``tree_sha_after`` / mutation-flag field — so the
verifier, which only ever reads the receipt, cannot detect it.

Only public APIs are used: :func:`benchreceipt.capture.capture` and
:func:`benchreceipt.verify.evaluate`. No production internals are patched.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchreceipt.capture import capture
from benchreceipt.verify import evaluate

JUNIT_XML = (
    '<?xml version="1.0"?>\n'
    '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
    ' skipped="0">'
    '<testcase classname="s" name="t1"/>'
    '<testcase classname="s" name="t2"/>'
    "</testsuite></testsuites>\n"
)

# Policy matching a local (non-CI) capture: source_mode "event_sha",
# workflow "local". The policy dict is validated by evaluate() itself.
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


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def _verify_evidence(repo: Path, expected_sha: str) -> dict:
    return evaluate(POLICY, expected_sha, repo / ".benchreceipt" / "evidence")


def test_head_change_mid_run_is_detected(tmp_path: Path):
    """P0-01 variant 1: `git checkout <other-commit>` mid-run.

    The wrapped command checks out the second commit (clean tree, different
    HEAD and tree) and then writes a green JUnit report. The tests therefore
    ran against commit 2, but the receipt claims commit 1. Verification
    must NOT return BOUND_PASS: it must flag SOURCE_MUTATED_DURING_RUN.
    """
    repo = _make_repo(tmp_path / "repo")
    sha1 = _git(repo, "rev-parse", "HEAD~1")
    sha2 = _head(repo)
    assert sha1 != sha2
    _git(repo, "checkout", "-q", sha1)
    assert _head(repo) == sha1

    script = (
        "import subprocess; "
        f"subprocess.run(['git', 'checkout', '-q', '{sha2}'], check=True); "
        f"open('junit.xml', 'w').write({JUNIT_XML!r})"
    )
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", script],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    # Capture itself sees the mutation; the defect is that the receipt
    # does not carry it to the verifier.
    assert result.source_mutated_during_run is True
    assert _head(repo) == sha2  # the tests ran against commit 2
    receipt = json.loads(
        (repo / ".benchreceipt" / "evidence" / "unit-linux-py312"
         / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["git"]["head_sha"] == sha1  # receipt claims commit 1
    assert receipt["source_state_before"] == receipt["source_state_after"]

    verdict = _verify_evidence(repo, sha1)
    assert verdict["status"] != "BOUND_PASS", verdict
    assert "SOURCE_MUTATED_DURING_RUN" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 0, verdict


def test_empty_commit_mid_run_is_detected(tmp_path: Path):
    """P0-01 variant 2: `git commit --allow-empty` mid-run.

    HEAD changes but the tree is byte-identical, so even a tree comparison
    would not catch this — only an after-HEAD (or a persisted mutation
    flag) can. Same expectation as variant 1.
    """
    repo = _make_repo(tmp_path / "repo")
    sha1 = _head(repo)
    script = (
        "import subprocess; "
        "subprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', 'mid-run'], check=True); "
        f"open('junit.xml', 'w').write({JUNIT_XML!r})"
    )
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", script],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    assert result.source_mutated_during_run is True
    sha2 = _head(repo)
    assert sha2 != sha1  # HEAD moved; tree is identical
    receipt = json.loads(
        (repo / ".benchreceipt" / "evidence" / "unit-linux-py312"
         / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["git"]["head_sha"] == sha1
    assert receipt["source_state_before"] == receipt["source_state_after"]

    verdict = _verify_evidence(repo, sha1)
    assert verdict["status"] != "BOUND_PASS", verdict
    assert "SOURCE_MUTATED_DURING_RUN" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 0, verdict


def test_dirty_to_clean_flip_is_detected(tmp_path: Path):
    """Control: a dirty -> clean flip IS caught by the existing checks.

    Proves the harness and the verifier's dirty-flag comparison work, and
    that the defect is specific to mutations that leave the worktree
    clean (HEAD/tree changes with an empty porcelain status).
    """
    repo = _make_repo(tmp_path / "repo")
    sha1 = _head(repo)
    (repo / "code.py").write_text("VALUE = 99  # uncommitted\n", encoding="utf-8")
    script = (
        "import subprocess; "
        "subprocess.run(['git', 'checkout', '-q', '--', '.'], check=True); "
        f"open('junit.xml', 'w').write({JUNIT_XML!r})"
    )
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", script],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    assert result.source_mutated_during_run is True
    verdict = _verify_evidence(repo, sha1)
    assert verdict["status"] != "BOUND_PASS", verdict
    assert "SOURCE_MUTATED_DURING_RUN" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 0, verdict
