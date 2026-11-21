"""Wheel regression for P0-R1-01 (spec v1.2.0, ADR-007).

The R1 false PASS was reproduced by the reviewer against the
*published wheel* (``03_evidence/r1-repro/independent_p0_wheel_repro.py``:
real capture + ``benchreceipt.verify.evaluate`` from the installed
wheel, both after fields deleted). This test is the same probe with
the FIXED expectations, run against a wheel built from the current
source tree with the pinned offline toolchain — so a wheel that
regresses to the old compat rule fails here, not just in source.

Build helpers are reused from ``test_wheel_contents.py`` (same
offline toolchain cache, same ``python -m build --no-isolation``
command); only the fixed wheel is built (no stanza-less control —
that file already pins the stanza).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_WHEEL_CONTENTS = _HERE / "test_wheel_contents.py"
_spec = importlib.util.spec_from_file_location(
    "_wheel_contents", _WHEEL_CONTENTS)
_wc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wc)

REPO_ROOT = _HERE.parents[2]

JUNIT_XML = (
    '<testsuites><testsuite name="s" tests="1" failures="0" errors="0"'
    ' skipped="0"><testcase name="ok" classname="s"/></testsuite></testsuites>'
)

POLICY = {
    "schema_version": 1, "source_mode": "event_sha",
    "expected_workflow": "local",
    "required_jobs": ["unit-linux-py312"], "min_tests": 1,
    "require_clean_source_after": True, "same_tree_across_jobs": True,
    "same_run_id": True, "same_run_attempt": True,
    "reports": {"junit": "required", "lcov": "optional"},
}


@pytest.fixture(scope="module")
def installed_wheel(tmp_path_factory):
    """Build the fixed wheel once, install it into a fresh venv."""
    work = tmp_path_factory.mktemp("wheel-legacy-after")
    buildenv = _wc._unpack_toolchain(work / "buildenv")
    src = _wc._copy_source_tree(work / "fixed-src")
    wheel = _wc._build_wheel(src, buildenv, work / "fixed-out")
    venv = work / "venv"
    proc = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    venv_py = venv / "bin" / "python"
    env = dict(os.environ)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    proc = subprocess.run(
        [str(venv_py), "-m", "pip", "install", "--no-index", "--no-deps",
         str(wheel)],
        capture_output=True, text=True, env=env, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return {"work": work, "wheel": wheel, "venv_py": venv_py}


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def _write_policy(path: Path) -> Path:
    path.write_text(
        "schema_version = 1\n"
        "source_mode = \"event_sha\"\n"
        "expected_workflow = \"local\"\n"
        "required_jobs = [\"unit-linux-py312\"]\n"
        "min_tests = 1\n"
        "require_clean_source_after = true\n"
        "same_tree_across_jobs = true\n"
        "same_run_id = true\n"
        "same_run_attempt = true\n"
        "\n[reports]\n"
        "junit = \"required\"\n"
        "lcov = \"optional\"\n"
        "\n[security]\n"
        "store_stdout = false\n"
        "store_stderr = false\n"
        "store_full_environment = false\n",
        encoding="utf-8")
    return path


def _probe_script() -> str:
    """Run inside the installed venv: green capture, then the legacy
    variant (both after fields deleted), verified via the installed
    CLI. Mirrors the reviewer script, with the fixed expectations."""
    script = (
        "import json, subprocess, sys\n"
        "from pathlib import Path\n"
        "from benchreceipt.capture import capture\n"
        "from benchreceipt.schema import validate_against_schema\n"
        "repo = Path(sys.argv[1])\n"
        "policy = json.loads(sys.argv[2])\n"
        "first = sys.argv[3]\n"
        "cmd = \"import shutil; shutil.copy('junit-template.xml', 'junit.xml')\"\n"
        "result = capture(job_id='unit-linux-py312',\n"
        "    matrix={'os': 'ubuntu-latest', 'python': '3.12'},\n"
        "    argv=[sys.executable, '-c', cmd], repo_path=repo, cwd=repo,\n"
        "    junit_path='junit.xml', env={})\n"
        "assert result.source_mutated_during_run is False\n"
        "ev = repo / '.benchreceipt' / 'evidence'\n"
        "receipt_path = ev / 'unit-linux-py312' / 'receipt.json'\n"
        "data = json.loads(receipt_path.read_text())\n"
        "assert data['git']['head_sha_after'] == first\n"
        "assert data['git']['tree_sha_after'] == data['git']['tree_sha']\n"
        "for k in ('head_sha_after', 'tree_sha_after'):\n"
        "    data['git'].pop(k)\n"
        "validate_against_schema(data, 'run')\n"
        "receipt_path.write_text(json.dumps(data, sort_keys=True) + '\\n')\n"
        "print('LEGACY_SHAPE_SCHEMA_VALID')\n"
    )
    return script


def test_installed_wheel_fails_closed_on_legacy_shape(
    installed_wheel, tmp_path
):
    """Installed wheel: green capture, both after fields deleted ->
    CLI verify exits 2, UNBOUND + MISSING_FIELD, jobs_verified 0.
    The old wheel returned exit 0 / BOUND_PASS here (R1 repro)."""
    venv_py = installed_wheel["venv_py"]
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fix-r1@example.invalid")
    _git(repo, "config", "user.name", "P027-FIX-R1")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    # The wrapped command copies this committed template to junit.xml,
    # so no quoting of the XML is needed inside the -c command and the
    # tree stays clean (the declared junit.xml itself is excluded
    # from capture's dirty check).
    (repo / "junit-template.xml").write_text(JUNIT_XML, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    first = _git(repo, "rev-parse", "HEAD")

    proc = subprocess.run(
        [str(venv_py), "-c", _probe_script(), str(repo),
         json.dumps(POLICY), first],
        capture_output=True, text=True, cwd=repo, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "LEGACY_SHAPE_SCHEMA_VALID" in proc.stdout, proc.stdout

    out = tmp_path / "result.json"
    policy_path = _write_policy(tmp_path / "policy.toml")
    proc = subprocess.run(
        [str(venv_py), "-m", "benchreceipt", "verify",
         "--policy", str(policy_path),
         "--evidence", str(repo / ".benchreceipt" / "evidence"),
         "--expected-source-sha", first, "--out", str(out)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "UNBOUND", result
    assert result["reason_codes"] == ["MISSING_FIELD"], result
    assert result["report_errors"] == [
        {"code": "MISSING_FIELD",
         "message": "missing git.head_sha_after and git.tree_sha_after",
         "job_id": "unit-linux-py312"}
    ], result
    assert result["jobs_verified"] == 0, result


def test_installed_wheel_still_passes_clean_capture(
    installed_wheel, tmp_path
):
    """Control: the same installed wheel still verifies an untouched
    clean capture as BOUND_PASS (exit 0) — the fail-closed rule must
    not block receipts that DO carry after identity."""
    venv_py = installed_wheel["venv_py"]
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fix-r1@example.invalid")
    _git(repo, "config", "user.name", "P027-FIX-R1")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    # The wrapped command copies this committed template to junit.xml,
    # so no quoting of the XML is needed inside the -c command and the
    # tree stays clean (the declared junit.xml itself is excluded
    # from capture's dirty check).
    (repo / "junit-template.xml").write_text(JUNIT_XML, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    first = _git(repo, "rev-parse", "HEAD")
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from benchreceipt.capture import capture\n"
        "repo = Path(sys.argv[1])\n"
        "cmd = \"import shutil; shutil.copy('junit-template.xml', 'junit.xml')\"\n"
        "capture(job_id='unit-linux-py312',\n"
        "    matrix={'os': 'ubuntu-latest', 'python': '3.12'},\n"
        "    argv=[sys.executable, '-c', cmd], repo_path=repo, cwd=repo,\n"
        "    junit_path='junit.xml', env={})\n"
    )
    proc = subprocess.run([str(venv_py), "-c", script, str(repo)],
                          capture_output=True, text=True, cwd=repo,
                          timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    policy_path = _write_policy(tmp_path / "policy.toml")
    out = tmp_path / "result.json"
    proc = subprocess.run(
        [str(venv_py), "-m", "benchreceipt", "verify",
         "--policy", str(policy_path),
         "--evidence", str(repo / ".benchreceipt" / "evidence"),
         "--expected-source-sha", first, "--out", str(out)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "BOUND_PASS", result
    assert result["jobs_verified"] == 1, result
