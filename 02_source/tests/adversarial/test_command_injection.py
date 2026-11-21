"""Probe (h) — command injection via capture.

``benchreceipt.command.run_command`` runs the argv with
``subprocess.run(..., shell=False)``: no shell string is ever built,
so shell metacharacters (``;``, ``$(...)``, backticks, ``&&``, ``|``)
in argv elements are literal arguments, never commands. Each test
plants a sentinel file that must stay untouched: if any metacharacter
were interpreted by a shell, the sentinel would appear.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from _evidence import JUNIT_XML, head, make_repo
from benchreceipt.capture import capture
from benchreceipt.command import run_command
from benchreceipt.verify import evaluate

SENTINEL_NAME = "pwned.txt"

LOCAL_POLICY = {
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


def test_shell_metacharacters_as_arguments_are_literal(tmp_path: Path):
    """Metacharacters passed as argv elements never execute anything."""
    repo = make_repo(tmp_path / "repo")
    sentinel = repo / SENTINEL_NAME
    script = (
        "import sys; "
        f"open('junit.xml', 'w').write({JUNIT_XML!r}); "
        "print('argv:', sys.argv)"
    )
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[
            sys.executable, "-c", script,
            ";", f"$(touch {SENTINEL_NAME})", f"`touch {SENTINEL_NAME}`",
            "&&", f"touch {SENTINEL_NAME}", "|", f"touch {SENTINEL_NAME}",
            f"a;touch {SENTINEL_NAME}",
        ],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    assert result.exit_code == 0
    assert not sentinel.exists()
    # The receipt still records the command (display is just text).
    assert ";" in result.receipt["command"]["display"]
    verdict = evaluate(LOCAL_POLICY, head(repo), repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "BOUND_PASS", verdict


def test_shell_metacharacter_as_executable_is_never_run(tmp_path: Path):
    """An argv[0] containing shell syntax is not executed at all.

    With shell=False there is no shell to interpret it, so the exec
    fails with FileNotFoundError and no receipt is written.
    """
    repo = make_repo(tmp_path / "repo")
    sentinel = repo / SENTINEL_NAME
    with pytest.raises(OSError):
        capture(
            job_id="unit-linux-py312",
            matrix={"os": "ubuntu-latest", "python": "3.12"},
            argv=[f"echo hi; touch {SENTINEL_NAME}"],
            repo_path=repo, junit_path="junit.xml", cwd=repo,
        )
    assert not sentinel.exists()
    assert not (repo / ".benchreceipt" / "evidence" / "unit-linux-py312"
                / "receipt.json").exists()


@pytest.mark.parametrize(
    "metachar",
    [";", "$(touch pwned.txt)", "`touch pwned.txt`", "&& touch pwned.txt",
     "| touch pwned.txt", "foo;touch pwned.txt"],
)
def test_run_command_never_builds_a_shell_string(tmp_path: Path, metachar: str):
    """run_command with a hostile argv[0] raises instead of executing."""
    sentinel = tmp_path / "pwned.txt"
    with pytest.raises(OSError):
        run_command([f"nonexistent-cmd {metachar}"], cwd=tmp_path)
    assert not sentinel.exists()


def test_metacharacters_inside_a_quoted_argument_are_literal(tmp_path: Path):
    """A ``;`` inside a real argument value is data, not a separator."""
    repo = make_repo(tmp_path / "repo")
    sentinel = repo / SENTINEL_NAME
    script = (
        "import sys; "
        f"open('junit.xml', 'w').write({JUNIT_XML!r}); "
        "open('seen.txt', 'w').write(sys.argv[1])"
    )
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", script, f"a;b;touch {SENTINEL_NAME}"],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    assert result.exit_code == 0
    assert not sentinel.exists()
    assert (repo / "seen.txt").read_text(encoding="utf-8") == (
        f"a;b;touch {SENTINEL_NAME}"
    )
