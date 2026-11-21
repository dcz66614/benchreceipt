"""Console-script regression tests (P027 FIX-P1-01).

PROJECT_BOOK §6.4 documents the CLI as bare ``benchreceipt``
commands, and ``examples/github-actions/ci.yml`` runs bare
``benchreceipt capture`` / ``benchreceipt verify`` steps — but
``pyproject.toml`` declared no ``[project.scripts]`` entry point, so an
editable install produced no ``benchreceipt`` executable at all and the
documented CI steps would fail with "command not found" on a real
runner. Only ``python -m benchreceipt`` worked.

These tests exercise the *installed* entry point as a real process —
``<venv>/bin/benchreceipt`` under the running interpreter's
``sys.prefix`` — never ``cli.main`` in-process and never ``python -m``. That is the
whole point: the pre-fix suite only ever drove the module form, which
is why the missing executable shipped. If the entry point is ever
dropped from ``pyproject.toml`` again, ``_console_script`` fails
instead of skipping, so the regression is loud.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "s0"
GIT = "git"
FAKE_MERGE_SHA = "1" * 40


def _console_script() -> Path:
    """Path of the installed ``benchreceipt`` console script.

    It lives in the ``bin/`` (``Scripts/`` on Windows) directory of the
    environment running this test suite (``sys.prefix`` — the project
    .venv after ``pip install -e 02_source``). ``sys.executable`` must
    NOT be used to locate it: the venv python is a symlink to the
    system interpreter, so resolving it points at ``/usr/bin`` instead
    of the venv. A missing script is a test FAILURE, not a skip:
    """
    script = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin") / "benchreceipt"
    assert script.is_file(), (
        "no installed `benchreceipt` console script under "
        f"{sys.prefix} — is [project.scripts] missing from "
        "02_source/pyproject.toml, or was the package not installed "
        "editable into this venv? (P1-01)"
    )
    return script


def _run_bare(*args: str, cwd: Path | None = None,
              env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(_console_script()), *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
    )


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_console_script_exists_and_help():
    proc = _run_bare("--help")
    assert proc.returncode == 0, proc.stderr
    for word in ("capture", "verify", "report", "bundle"):
        assert word in proc.stdout


@pytest.mark.parametrize("sub", ["capture", "verify", "report", "bundle"])
def test_console_script_subcommand_help(sub: str):
    proc = _run_bare(sub, "--help")
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# Bare verify of a known BOUND_PASS fixture
# ---------------------------------------------------------------------------


def test_console_script_verify_fixture_is_bound_pass(tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_bare(
        "verify",
        "--policy", str(FIXTURES / "n01-single-pr-head" / "policy.toml"),
        "--evidence", str(FIXTURES / "n01-single-pr-head" / "evidence"),
        "--expected-source-sha",
        json.loads(
            (FIXTURES / "n01-single-pr-head" / "expected.json").read_text()
        )["expected_source_sha"],
        "--out", str(out),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "BOUND_PASS"


# ---------------------------------------------------------------------------
# Bare capture -> verify -> report round trip in a throwaway git repo
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one passing test, committed clean."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run([GIT, "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        [GIT, "config", "user.email", "fix-p1-01@example.invalid"],
        cwd=repo, check=True,
    )
    subprocess.run(
        [GIT, "config", "user.name", "FIX-P1-01"], cwd=repo, check=True
    )
    (repo / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n.benchreceipt/\n", encoding="utf-8"
    )
    (repo / "test_ok.py").write_text(
        "def test_ok():\n    assert 1 == 1\n", encoding="utf-8"
    )
    subprocess.run([GIT, "add", "-A"], cwd=repo, check=True)
    subprocess.run([GIT, "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


def _single_job_policy(repo: Path) -> Path:
    """Single-job pr_head policy mirroring the n01 S0 fixture."""
    policy = repo / "benchreceipt.toml"
    policy.write_text(
        'schema_version = 1\n'
        'source_mode = "pr_head"\n'
        'expected_workflow = "CI"\n'
        'required_jobs = ["demo-linux-py312"]\n'
        'min_tests = 1\n'
        'require_clean_source_after = true\n'
        'same_tree_across_jobs = true\n'
        'same_run_id = true\n'
        'same_run_attempt = true\n'
        '\n'
        '[reports]\n'
        'junit = "required"\n'
        'lcov = "optional"\n'
        '\n'
        '[security]\n'
        'store_stdout = false\n'
        'store_stderr = false\n'
        'store_full_environment = false\n',
        encoding="utf-8",
    )
    return policy


def test_console_script_capture_verify_report_round_trip(
    temp_repo: Path, tmp_path: Path
):
    """Bare `benchreceipt capture` -> `verify` -> `report`, end to end.

    This is the exact shape the GitHub Actions example workflow runs
    (one matrix job, PR-head checkout, same run id / attempt): capture
    wraps a green pytest run, verify binds it BOUND_PASS, report
    renders the verification JSON as HTML. Every step goes through the
    installed console script, not `python -m`.
    """
    repo = temp_repo
    head = subprocess.run(
        [GIT, "rev-parse", "HEAD"], cwd=repo, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "action": "opened",
                "number": 1,
                "pull_request": {
                    "head": {"sha": head},
                    "merge_commit_sha": FAKE_MERGE_SHA,
                    "number": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "GITHUB_SHA": FAKE_MERGE_SHA,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_RUN_ID": "9001",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW": "CI",
        }
    )
    capture = _run_bare(
        "capture",
        "--job", "demo-linux-py312",
        "--matrix", "os=ubuntu-latest,python=3.12",
        "--junit", ".benchreceipt/out/junit.xml",
        "--", sys.executable, "-m", "pytest", "-q",
        "-p", "no:cacheprovider",
        "--junitxml=.benchreceipt/out/junit.xml",
        cwd=repo, env=env,
    )
    assert capture.returncode == 0, capture.stderr
    receipt = json.loads(
        (repo / ".benchreceipt" / "evidence" / "demo-linux-py312"
         / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["git"]["source_mode"] == "pr_head"
    assert receipt["git"]["head_sha"] == head

    out = repo / ".benchreceipt" / "verification.json"
    verify = _run_bare(
        "verify",
        "--policy", str(_single_job_policy(repo)),
        "--evidence", str(repo / ".benchreceipt" / "evidence"),
        "--expected-source-sha", head,
        "--out", str(out),
        cwd=repo,
    )
    assert verify.returncode == 0, verify.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "BOUND_PASS"

    html = repo / ".benchreceipt" / "report.html"
    report = _run_bare(
        "report", "--input", str(out), "--html", str(html), cwd=repo
    )
    assert report.returncode == 0, report.stderr
    assert html.is_file()
    assert "BOUND_PASS" in html.read_text(encoding="utf-8")
