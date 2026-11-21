"""GitHub Actions example integration tests (P027-T009).

Everything here is synthetic and local — no real GitHub repository
exists for this project, no network, no token. The tests exercise the
real ``benchreceipt`` CLI in throwaway git repos with a hand-crafted
``GITHUB_EVENT_PATH`` pull_request payload, exactly the way the
example workflow (``02_source/examples/github-actions/ci.yml``) would
see it on a runner:

- a PR-head capture records the head SHA with ``source_mode pr_head``;
- a merge-commit checkout records ``merge_commit`` and verify flags
  ``SOURCE_SHA_MISMATCH`` against the ``pr_head`` policy
  (PROJECT_BOOK §1.2 scenario A);
- two jobs from different run attempts verify as UNBOUND with
  ``RUN_ATTEMPT_MISMATCH`` (scenario B), even though both JUnit
  reports are green;
- an all-green, same-head, same-run, same-attempt, matrix-complete
  bundle is UNBOUND with reason_codes == ["MISSING_FIELD"] — the
  known pre-existing T003/T008 seam: ``capture`` never writes the
  ``junit`` summary ``verify`` requires when the policy says
  ``junit = "required"`` (see examples/github-actions/README.md §5).
  That test pins the current behaviour so a future FIX task's change
  is visible, rather than asserting a BOUND_PASS this build cannot
  honestly produce;
- the workflow file itself passes the structural validator, its
  upload/download artifact names match the job ids, and the
  validator rejects token use / a missing download / a default
  (merge-commit) checkout.

The wrapped test command is the same shape the workflow uses
(``python -m pytest -q -p no:cacheprovider --junitxml=...`` under
``.benchreceipt/out/``) with ``PYTHONDONTWRITEBYTECODE=1`` and a
committed ``.gitignore`` for caches, so capture's dirty-source check
stays clean — the same hygiene the workflow README asks adopters
for.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # 02_source/
WORKFLOW = ROOT / "examples" / "github-actions" / "ci.yml"
POLICY = ROOT / "examples" / "benchreceipt.toml"
VALIDATOR = ROOT / "scripts" / "validate_workflow_example.py"

GIT = "git"
FAKE_MERGE_SHA = "1" * 40


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_workflow_example", VALIDATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def temp_repo(tmp_path):
    """A throwaway git repo with one passing test, committed clean."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run([GIT, "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        [GIT, "config", "user.email", "t009@example.invalid"], cwd=repo, check=True
    )
    subprocess.run([GIT, "config", "user.name", "T009"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n.benchreceipt/\n", encoding="utf-8"
    )
    (repo / "test_ok.py").write_text(
        "def test_ok():\n    assert 1 == 1\n", encoding="utf-8"
    )
    subprocess.run([GIT, "add", "-A"], cwd=repo, check=True)
    subprocess.run([GIT, "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


def _head_sha(repo: Path) -> str:
    return subprocess.run(
        [GIT, "rev-parse", "HEAD"], cwd=repo, capture_output=True,
        text=True, check=True,
    ).stdout.strip()


def _write_event(tmp_path: Path, head_sha: str, merge_sha: str) -> Path:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "action": "opened",
                "number": 1,
                "pull_request": {
                    "head": {"sha": head_sha},
                    "merge_commit_sha": merge_sha,
                    "number": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return event


def _capture(
    repo: Path,
    *,
    job_id: str,
    matrix: str,
    event_path: Path,
    github_sha: str,
    run_id: str = "9001",
    attempt: int = 1,
) -> subprocess.CompletedProcess:
    """Run the real capture CLI the way the workflow's test job does."""
    env = dict(os.environ)
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "GITHUB_SHA": github_sha,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_RUN_ID": run_id,
            "GITHUB_RUN_ATTEMPT": str(attempt),
            "GITHUB_WORKFLOW": "CI",
        }
    )
    return subprocess.run(
        [
            sys.executable, "-m", "benchreceipt", "capture",
            "--job", job_id,
            "--matrix", matrix,
            "--junit", ".benchreceipt/out/junit.xml",
            "--", sys.executable, "-m", "pytest", "-q",
            "-p", "no:cacheprovider",
            "--junitxml=.benchreceipt/out/junit.xml",
        ],
        cwd=repo, env=env, capture_output=True, text=True,
    )


def _verify(repo: Path, expected_sha: str) -> tuple[int, dict]:
    out = repo / ".benchreceipt" / "verification.json"
    proc = subprocess.run(
        [
            sys.executable, "-m", "benchreceipt", "verify",
            "--policy", str(POLICY),
            "--evidence", str(repo / ".benchreceipt" / "evidence"),
            "--expected-source-sha", expected_sha,
            "--out", str(out),
        ],
        cwd=repo, capture_output=True, text=True,
    )
    return proc.returncode, json.loads(out.read_text(encoding="utf-8"))


def _receipt(repo: Path, job_id: str) -> dict:
    return json.loads(
        (repo / ".benchreceipt" / "evidence" / job_id / "receipt.json")
        .read_text(encoding="utf-8")
    )


def test_pr_head_capture_records_head_and_mode(temp_repo, tmp_path):
    """Scenario A (good path): checkout == PR head -> pr_head receipt."""
    repo = temp_repo
    head = _head_sha(repo)
    event = _write_event(tmp_path, head, FAKE_MERGE_SHA)
    proc = _capture(
        repo, job_id="unit-linux-py312",
        matrix="os=ubuntu-latest,python=3.12",
        event_path=event, github_sha=FAKE_MERGE_SHA,
    )
    assert proc.returncode == 0, proc.stderr
    receipt = _receipt(repo, "unit-linux-py312")
    assert receipt["git"]["head_sha"] == head
    assert receipt["git"]["source_mode"] == "pr_head"
    assert receipt["git"]["expected_source_sha"] == head
    assert receipt["ci"]["provider"] == "github-actions"
    assert receipt["ci"]["run_id"] == "9001"
    assert receipt["ci"]["run_attempt"] == 1
    assert receipt["ci"]["event_name"] == "pull_request"
    assert receipt["matrix"] == {"os": "ubuntu-latest", "python": "3.12"}
    assert receipt["command"]["exit_code"] == 0
    assert receipt["reports"][0]["kind"] == "junit"
    assert receipt["reports"][0]["path"] == "artifacts/junit.xml"


def test_merge_checkout_records_merge_mode_and_verify_flags_it(
    temp_repo, tmp_path
):
    """Scenario A (bad path): checkout == merge commit -> UNBOUND.

    A second commit plays the merge commit: the event still names the
    first commit as the PR head, ``GITHUB_SHA`` is the merge commit,
    and the worktree is checked out at the merge commit. Capture must
    record ``merge_commit``; verify against the pr_head policy and the
    head SHA must report SOURCE_SHA_MISMATCH (UNBOUND, exit 2).
    """
    repo = temp_repo
    head = _head_sha(repo)
    (repo / "test_ok.py").write_text(
        "def test_ok():\n    assert 1 == 1\n\n\n# merge-commit simulation\n",
        encoding="utf-8",
    )
    subprocess.run([GIT, "add", "-A"], cwd=repo, check=True)
    subprocess.run([GIT, "commit", "-qm", "merge"], cwd=repo, check=True)
    merge = _head_sha(repo)
    assert merge != head
    event = _write_event(tmp_path, head, merge)
    proc = _capture(
        repo, job_id="unit-linux-py312",
        matrix="os=ubuntu-latest,python=3.12",
        event_path=event, github_sha=merge,
    )
    assert proc.returncode == 0, proc.stderr
    receipt = _receipt(repo, "unit-linux-py312")
    assert receipt["git"]["head_sha"] == merge
    assert receipt["git"]["source_mode"] == "merge_commit"
    assert receipt["git"]["expected_source_sha"] == merge
    exit_code, result = _verify(repo, head)
    assert exit_code == 2  # UNBOUND
    assert result["status"] == "UNBOUND"
    assert "SOURCE_SHA_MISMATCH" in result["reason_codes"]


def test_mixed_attempt_bundle_is_unbound(temp_repo, tmp_path):
    """Scenario B: attempt 1 + attempt 2, both green -> RUN_ATTEMPT_MISMATCH.

    Two captures of the same commit and run id, differing only in
    GITHUB_RUN_ATTEMPT, verified together. Both JUnit reports pass,
    but the bundle must still be UNBOUND — a green report from a
    stale attempt must never be aggregated with a fresh one.
    """
    repo = temp_repo
    head = _head_sha(repo)
    event = _write_event(tmp_path, head, FAKE_MERGE_SHA)
    for job_id, matrix, attempt in (
        ("unit-linux-py312", "os=ubuntu-latest,python=3.12", 1),
        ("unit-linux-py313", "os=ubuntu-latest,python=3.13", 1),
        ("unit-windows-py312", "os=windows-latest,python=3.12", 1),
        ("unit-windows-py313", "os=windows-latest,python=3.13", 2),
    ):
        proc = _capture(
            repo, job_id=job_id, matrix=matrix,
            event_path=event, github_sha=FAKE_MERGE_SHA, attempt=attempt,
        )
        assert proc.returncode == 0, proc.stderr
    exit_code, result = _verify(repo, head)
    assert exit_code == 2  # UNBOUND
    assert result["status"] == "UNBOUND"
    assert "RUN_ATTEMPT_MISMATCH" in result["reason_codes"]
    # Only the stale-attempt job fails: the three attempt-1 jobs now
    # verify (their JUnit summaries are present since FIX-capture-junit,
    # so MISSING_FIELD no longer fails every job). The bundle is still
    # UNBOUND overall — a green report from a stale attempt is never
    # aggregated with a fresh one.
    assert result["jobs_verified"] == 3
    assert result["identity_mismatches"] == [
        {"job_id": "unit-windows-py313", "field": "ci.run_attempt",
         "expected": 1, "actual": 2}
    ]


def test_all_green_bundle_verifies_bound_pass(
    temp_repo, tmp_path
):
    """T003/T008 seam CLOSED by FIX-capture-junit: all-green -> BOUND_PASS.

    Same head, same run id, same attempt, matrix complete (all four
    policy jobs), every JUnit report green — verify is now BOUND_PASS
    with jobs_verified 4, because capture emits the parsed ``junit``
    summary verify requires when the policy says junit is required.

    Previously (T009) this test pinned the seam: the same bundle was
    UNBOUND with reason_codes == ["MISSING_FIELD"] and nothing else,
    because capture never wrote the summary. The gate failed closed
    (never a false green); it can now go green. See
    examples/github-actions/README.md §5 and ADR-004.
    """
    repo = temp_repo
    head = _head_sha(repo)
    event = _write_event(tmp_path, head, FAKE_MERGE_SHA)
    for job_id, matrix in (
        ("unit-linux-py312", "os=ubuntu-latest,python=3.12"),
        ("unit-linux-py313", "os=ubuntu-latest,python=3.13"),
        ("unit-windows-py312", "os=windows-latest,python=3.12"),
        ("unit-windows-py313", "os=windows-latest,python=3.13"),
    ):
        proc = _capture(
            repo, job_id=job_id, matrix=matrix,
            event_path=event, github_sha=FAKE_MERGE_SHA, attempt=1,
        )
        assert proc.returncode == 0, proc.stderr
    exit_code, result = _verify(repo, head)
    assert exit_code == 0  # BOUND_PASS
    assert result["status"] == "BOUND_PASS"
    assert result["missing_jobs"] == []
    assert result["reason_codes"] == []
    assert result["jobs_verified"] == 4


# --- workflow file checks -------------------------------------------------


def test_workflow_passes_validator():
    validator = _load_validator()
    required = validator.load_required_jobs(POLICY)
    errors = validator.validate_workflow_text(
        WORKFLOW.read_text(encoding="utf-8"), required
    )
    assert errors == []


def test_workflow_artifact_names_match_job_ids():
    """Upload dir names match job ids; every job has a download step."""
    validator = _load_validator()
    doc = validator.parse_yaml_subset(WORKFLOW.read_text(encoding="utf-8"))
    include = doc["jobs"]["test"]["strategy"]["matrix"]["include"]
    job_ids = [cell["job_id"] for cell in include]
    assert job_ids == [
        "unit-linux-py312",
        "unit-linux-py313",
        "unit-windows-py312",
        "unit-windows-py313",
    ]
    # The example policy's required_jobs must be exactly the matrix.
    assert validator.load_required_jobs(POLICY) == job_ids
    test_steps = doc["jobs"]["test"]["steps"]
    upload = next(
        s for s in test_steps
        if str(s.get("uses", "")).startswith("actions/upload-artifact@")
    )
    assert upload["with"]["name"] == "benchreceipt-evidence-${{ matrix.job_id }}"
    assert upload["with"]["path"] == ".benchreceipt/evidence/${{ matrix.job_id }}"
    verify_steps = doc["jobs"]["verify"]["steps"]
    downloads = {
        s["with"]["name"]: s["with"]["path"]
        for s in verify_steps
        if str(s.get("uses", "")).startswith("actions/download-artifact@")
    }
    assert downloads == {
        f"benchreceipt-evidence-{job_id}": f".benchreceipt/evidence/{job_id}"
        for job_id in job_ids
    }
    # The verify step comes after every download step.
    verify_idx = next(
        i for i, s in enumerate(verify_steps)
        if isinstance(s.get("run"), str) and "benchreceipt verify" in s["run"]
    )
    last_download_idx = max(
        i for i, s in enumerate(verify_steps)
        if str(s.get("uses", "")).startswith("actions/download-artifact@")
    )
    assert verify_idx > last_download_idx


def test_validator_rejects_token_use():
    validator = _load_validator()
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated = text.replace(
        "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
        "ref: ${{ github.event.pull_request.head.sha }}\n"
        "          token: ${{ github.token }}",
        1,
    )
    assert mutated != text
    errors = validator.validate_workflow_text(
        mutated, validator.load_required_jobs(POLICY)
    )
    assert any("github.token" in e for e in errors)


def test_validator_rejects_missing_download():
    validator = _load_validator()
    text = WORKFLOW.read_text(encoding="utf-8")
    # Drop the whole download step for unit-windows-py313.
    start = text.index("Download evidence for unit-windows-py313")
    block_start = text.rfind("      - name:", 0, start)
    block_end = text.index("      - name:", start)
    mutated = text[:block_start] + text[block_end:]
    errors = validator.validate_workflow_text(
        mutated, validator.load_required_jobs(POLICY)
    )
    assert any(
        "benchreceipt-evidence-unit-windows-py313" in e for e in errors
    )


def test_validator_rejects_default_merge_checkout():
    validator = _load_validator()
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated = text.replace(
        "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
        "ref: ${{ github.sha }}",
    )
    assert mutated != text
    errors = validator.validate_workflow_text(
        mutated, validator.load_required_jobs(POLICY)
    )
    assert any("PR head SHA" in e for e in errors)


def test_validator_rejects_network_pip_install():
    validator = _load_validator()
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated = text.replace(
        "python -m pip install --no-build-isolation ./vendor/benchreceipt",
        "python -m pip install benchreceipt",
    )
    assert mutated != text
    errors = validator.validate_workflow_text(
        mutated, validator.load_required_jobs(POLICY)
    )
    assert any("local path" in e for e in errors)
