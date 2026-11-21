"""capture tests (P027-T003): end-to-end receipt assembly.

Every test builds a real synthetic git repo in a tmp dir, runs
:func:`benchreceipt.capture.capture` (or the provisional CLI) inside
it, and checks the receipt that lands in
``.benchreceipt/evidence/<job-id>/receipt.json``.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from benchreceipt.capture import CaptureError, capture, determine_source_mode
from benchreceipt.ci_metadata import collect_ci_metadata
from benchreceipt.schema import validate_against_schema
from benchreceipt.verify import evaluate


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

JUNIT_XML = (
    '<?xml version="1.0"?>\n'
    '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
    ' skipped="0">'
    '<testcase classname="s" name="t1"/>'
    '<testcase classname="s" name="t2"/>'
    "</testsuite></testsuites>\n"
)


def write_junit(repo: Path, name: str = "junit.xml") -> Path:
    path = repo / name
    path.write_text(JUNIT_XML, encoding="utf-8")
    return path


def read_receipt(evidence_dir: Path) -> dict:
    return json.loads((evidence_dir / "receipt.json").read_text(encoding="utf-8"))


def test_happy_path_receipt_validates_and_records_real_head(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    junit = write_junit(repo)
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "print('ok')"],
        repo_path=repo,
        junit_path=junit,
        cwd=repo,
        env={},
    )
    receipt = result.receipt
    assert result.exit_code == 0
    assert result.source_mutated_during_run is False
    # Schema-valid, and the receipt file on disk matches the result.
    validate_against_schema(receipt, "run")
    assert read_receipt(result.evidence_dir) == receipt
    assert receipt["schema"] == "benchreceipt.run/v1"
    assert receipt["job_id"] == "unit-linux-py312"
    assert receipt["matrix"] == {"os": "ubuntu-latest", "python": "3.12"}
    # Real git identity, not fabricated.
    assert receipt["git"]["head_sha"] == git_rev(repo, "HEAD")
    assert receipt["git"]["tree_sha"] == git_rev(repo, "HEAD^{tree}")
    assert receipt["git"]["dirty_before"] is False
    assert receipt["git"]["dirty_after"] is False
    assert receipt["git"]["source_mode"] == "event_sha"
    assert receipt["git"]["expected_source_sha"] == git_rev(repo, "HEAD")
    # Local run: generic provider with local fallbacks.
    assert receipt["ci"]["provider"] == "generic"
    assert receipt["ci"]["run_id"] == "local"
    assert receipt["ci"]["run_attempt"] == 1
    assert receipt["ci"]["workflow"] == "local"
    # Runner fingerprint + timings present.
    assert receipt["runner"]["python"] == sys.version.split()[0]
    assert receipt["started_at"] < receipt["finished_at"] or receipt["started_at"] == receipt["finished_at"]
    # JUnit summary (FIX-capture-junit): capture emits the parsed
    # summary for a valid report — the counted testcases, not the
    # raw attributes.
    assert receipt["junit"] == {
        "tests": 2,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    # Report hashed at byte level and copied beside the receipt.
    report = receipt["reports"][0]
    assert report["kind"] == "junit"
    assert report["path"] == "artifacts/junit.xml"
    assert report["size_bytes"] == len(JUNIT_XML.encode("utf-8"))
    assert report["sha256"] == hashlib.sha256(JUNIT_XML.encode("utf-8")).hexdigest()
    copied = result.evidence_dir / "artifacts" / "junit.xml"
    assert copied.read_bytes() == JUNIT_XML.encode("utf-8")
    # Privacy: no absolute paths, no stdout/stderr, no full argv.
    dumped = json.dumps(receipt)
    assert str(repo) not in dumped
    assert str(tmp_path) not in dumped
    assert "/home/" not in dumped
    assert receipt["command"]["display"].split()[0] == "python"
    assert "stdout" not in dumped and "stderr" not in dumped
    assert "print('ok')" not in dumped
    # source_state digests agree before/after on a clean run.
    assert receipt["source_state_before"] == receipt["source_state_after"]


def test_command_failure_still_writes_failure_receipt(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    result = capture(
        job_id="failing-job",
        matrix={"os": "ubuntu-latest"},
        argv=[sys.executable, "-c", "import sys; sys.exit(3)"],
        repo_path=repo,
        cwd=repo,
        env={},
    )
    assert result.exit_code == 3
    receipt = result.receipt
    assert receipt["command"]["exit_code"] == 3
    validate_against_schema(receipt, "run")
    assert (result.evidence_dir / "receipt.json").is_file()
    assert receipt["reports"] == []


def test_tracked_source_change_during_run_is_detected(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    code = "open('tracked.txt', 'a').write('mutated\\n')"
    result = capture(
        job_id="mutating-job",
        matrix={"os": "ubuntu-latest"},
        argv=[sys.executable, "-c", code],
        repo_path=repo,
        cwd=repo,
        env={},
    )
    assert result.exit_code == 0
    assert result.source_mutated_during_run is True
    assert result.mutation_details
    receipt = result.receipt
    assert receipt["git"]["dirty_before"] is False
    assert receipt["git"]["dirty_after"] is True
    assert (
        receipt["source_state_before"]["tracked_diff_sha256"]
        != receipt["source_state_after"]["tracked_diff_sha256"]
    )
    validate_against_schema(receipt, "run")


def test_report_created_under_benchreceipt_is_not_mutation(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    out = repo / ".benchreceipt" / "out"
    out.mkdir(parents=True)
    code = (
        "from pathlib import Path; "
        "Path('.benchreceipt/out/junit.xml').write_text("
        f"{JUNIT_XML!r})"
    )
    result = capture(
        job_id="report-job",
        matrix={"os": "ubuntu-latest"},
        argv=[sys.executable, "-c", code],
        repo_path=repo,
        junit_path=".benchreceipt/out/junit.xml",
        cwd=repo,
        env={},
    )
    assert result.source_mutated_during_run is False
    assert result.receipt["reports"][0]["kind"] == "junit"
    validate_against_schema(result.receipt, "run")


def test_declared_report_missing_raises_and_writes_nothing(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    with pytest.raises(CaptureError, match="not found"):
        capture(
            job_id="missing-report",
            matrix={"os": "ubuntu-latest"},
            argv=[sys.executable, "-c", "pass"],
            repo_path=repo,
            junit_path="never-created.xml",
            cwd=repo,
            env={},
        )
    assert not (repo / ".benchreceipt" / "evidence" / "missing-report" / "receipt.json").exists()


def test_non_git_dir_raises_capture_error(tmp_path: Path):
    plain = Path(tempfile.mkdtemp(dir="/tmp"))
    try:
        with pytest.raises(CaptureError, match="cannot determine git repository"):
            capture(
                job_id="no-git",
                matrix={"os": "ubuntu-latest"},
                argv=[sys.executable, "-c", "pass"],
                repo_path=plain,
                cwd=plain,
                env={},
            )
    finally:
        shutil.rmtree(plain, ignore_errors=True)


def test_invalid_job_id_and_matrix_raise(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    with pytest.raises(CaptureError, match="job_id"):
        capture("bad job!", {"os": "x"}, [sys.executable, "-c", "pass"],
                repo_path=repo, cwd=repo, env={})
    with pytest.raises(CaptureError, match="matrix"):
        capture("ok-job", {}, [sys.executable, "-c", "pass"],
                repo_path=repo, cwd=repo, env={})


def test_pr_head_mode_when_head_matches_event(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    head = git_rev(repo, "HEAD")
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {"pull_request": {"head": {"sha": head}, "merge_commit_sha": "c" * 40}}
        ),
        encoding="utf-8",
    )
    env = {
        "GITHUB_SHA": "c" * 40,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_RUN_ID": "9001",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_WORKFLOW": "CI",
        "GITHUB_EVENT_PATH": str(event),
    }
    result = capture(
        job_id="pr-job",
        matrix={"os": "ubuntu-latest"},
        argv=[sys.executable, "-c", "pass"],
        repo_path=repo,
        cwd=repo,
        env=env,
    )
    receipt = result.receipt
    assert receipt["git"]["source_mode"] == "pr_head"
    assert receipt["git"]["expected_source_sha"] == head
    assert receipt["ci"]["provider"] == "github-actions"
    assert receipt["ci"]["run_id"] == "9001"
    assert receipt["ci"]["run_attempt"] == 2
    assert receipt["ci"]["workflow"] == "CI"
    assert receipt["ci"]["event_name"] == "pull_request"
    validate_against_schema(receipt, "run")


def test_merge_commit_mode_when_head_is_github_sha(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    head = git_rev(repo, "HEAD")
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {"pull_request": {"head": {"sha": "a" * 40}, "merge_commit_sha": head}}
        ),
        encoding="utf-8",
    )
    env = {
        "GITHUB_SHA": head,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_RUN_ID": "9001",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW": "CI",
        "GITHUB_EVENT_PATH": str(event),
    }
    result = capture(
        job_id="merge-job",
        matrix={"os": "ubuntu-latest"},
        argv=[sys.executable, "-c", "pass"],
        repo_path=repo,
        cwd=repo,
        env=env,
    )
    assert result.receipt["git"]["source_mode"] == "merge_commit"
    assert result.receipt["git"]["expected_source_sha"] == head


def test_determine_source_mode_unit_cases():
    head = "a" * 40
    merge = "b" * 40
    ci_pr_head = collect_ci_metadata(
        {"GITHUB_SHA": merge, "GITHUB_EVENT_NAME": "pull_request",
         "GITHUB_EVENT_PATH": ""})
    # Event path empty -> no event payload; head_sha None -> falls to event_sha.
    assert determine_source_mode(ci_pr_head, head) == ("event_sha", merge)


# ---------------------------------------------------------------------------
# FIX-R13a (F-10): explicit_sha capture path (ADR-006)
# ---------------------------------------------------------------------------

EXPLICIT_SHA_POLICY = {
    "schema_version": 1,
    "source_mode": "explicit_sha",
    "expected_workflow": "local",
    "required_jobs": ["unit-linux-py312"],
    "min_tests": 1,
    "require_clean_source_after": True,
    "same_tree_across_jobs": True,
    "same_run_id": True,
    "same_run_attempt": True,
    "reports": {"junit": "required", "lcov": "optional"},
}


def test_determine_source_mode_explicit_sha_pin():
    """A pinned SHA selects explicit_sha; the pin is the expected SHA."""
    head = "a" * 40
    pinned = "b" * 40
    ci = collect_ci_metadata({})
    assert determine_source_mode(ci, head, pinned) == ("explicit_sha", pinned)
    # The pin wins over CI metadata, not just over the local default.
    ci_pr = collect_ci_metadata(
        {"GITHUB_SHA": "c" * 40, "GITHUB_EVENT_NAME": "push"})
    assert determine_source_mode(ci_pr, head, pinned) == ("explicit_sha", pinned)


@pytest.mark.parametrize(
    "bad_sha",
    ["NOT-A-SHA", "A" * 40, "b" * 39, "b" * 41, "b" * 40 + "\n",
     "b" * 40 + " ", "", 123],
)
def test_determine_source_mode_rejects_malformed_pin(bad_sha):
    """A malformed pinned SHA fails closed (ValueError), never a mode
    with a fabricated expected SHA. The trailing-newline case is the
    re.match/$ anchoring trap (cf. T013 P2-05)."""
    ci = collect_ci_metadata({})
    with pytest.raises(ValueError):
        determine_source_mode(ci, "a" * 40, bad_sha)


def test_capture_explicit_sha_end_to_end_verifies_bound_pass(tmp_path: Path):
    """FIX-R13a (F-10, repro5 R11): a real capture with
    --source-mode explicit_sha --expected-sha <HEAD> emits
    source_mode="explicit_sha" and verifies BOUND_PASS against an
    explicit_sha policy — the mode is no longer unreachable."""
    repo = make_repo(tmp_path / "repo")
    head = git_rev(repo, "HEAD")
    junit = write_junit(repo)
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "print('ok')"],
        repo_path=repo,
        junit_path=junit,
        cwd=repo,
        env={},
        source_mode="explicit_sha",
        expected_sha=head,
    )
    receipt = result.receipt
    validate_against_schema(receipt, "run")
    assert receipt["git"]["source_mode"] == "explicit_sha"
    assert receipt["git"]["expected_source_sha"] == head
    # The pin never rewrites reality: head_sha stays the real HEAD.
    assert receipt["git"]["head_sha"] == head
    verdict = evaluate(
        EXPLICIT_SHA_POLICY, head, repo / ".benchreceipt" / "evidence"
    )
    assert verdict["status"] == "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 1


def test_capture_explicit_sha_wrong_pin_fails_verification(tmp_path: Path):
    """A pin that differs from the checked-out HEAD is recorded
    honestly (head_sha stays the real HEAD) and verify fails it with
    SOURCE_SHA_MISMATCH when the pinned SHA is expected — the pin
    cannot bless a commit the tests did not run on."""
    repo = make_repo(tmp_path / "repo")
    head = git_rev(repo, "HEAD")
    junit = write_junit(repo)
    pinned = "c" * 40
    assert pinned != head
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "print('ok')"],
        repo_path=repo,
        junit_path=junit,
        cwd=repo,
        env={},
        source_mode="explicit_sha",
        expected_sha=pinned,
    )
    receipt = result.receipt
    assert receipt["git"]["source_mode"] == "explicit_sha"
    assert receipt["git"]["expected_source_sha"] == pinned
    assert receipt["git"]["head_sha"] == head
    verdict = evaluate(
        EXPLICIT_SHA_POLICY, pinned, repo / ".benchreceipt" / "evidence"
    )
    assert verdict["status"] == "UNBOUND", verdict
    assert verdict["reason_codes"] == ["SOURCE_SHA_MISMATCH"]
    assert verdict["jobs_verified"] == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_mode": "explicit_sha"},
        {"source_mode": "explicit_sha", "expected_sha": "NOT-A-SHA"},
        {"source_mode": "explicit_sha", "expected_sha": "A" * 40},
        {"source_mode": "explicit_sha", "expected_sha": "b" * 40 + "\n"},
        {"expected_sha": "b" * 40},
        {"source_mode": "pr_head", "expected_sha": "b" * 40},
        {"source_mode": "bogus"},
    ],
)
def test_capture_explicit_sha_bad_pins_raise(tmp_path: Path, kwargs):
    """Incomplete, malformed or unsupported pins are CaptureErrors —
    no receipt is written."""
    repo = make_repo(tmp_path / "repo")
    with pytest.raises(CaptureError):
        capture(
            job_id="unit-linux-py312",
            matrix={"os": "ubuntu-latest"},
            argv=[sys.executable, "-c", "pass"],
            repo_path=repo,
            cwd=repo,
            env={},
            **kwargs,
        )
    assert not (repo / ".benchreceipt").exists()


# ---------------------------------------------------------------------------
# Provisional CLI
# ---------------------------------------------------------------------------


def _run_cli(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "benchreceipt", "capture", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )


def test_cli_help_exits_zero(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    proc = _run_cli(repo, "--help")
    assert proc.returncode == 0
    assert "capture" in proc.stdout
    assert "--job" in proc.stdout


def test_cli_end_to_end_and_exit_passthrough(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    junit = write_junit(repo)
    proc = _run_cli(
        repo,
        "--job", "cli-job",
        "--matrix", "os=ubuntu-latest,python=3.12",
        "--junit", "junit.xml",
        "--", sys.executable, "-c", "print('cli-ok')",
    )
    assert proc.returncode == 0, proc.stderr
    receipt = read_receipt(repo / ".benchreceipt" / "evidence" / "cli-job")
    validate_against_schema(receipt, "run")
    assert receipt["git"]["head_sha"] == git_rev(repo, "HEAD")
    assert receipt["command"]["exit_code"] == 0
    assert "cli-ok" in proc.stdout  # stdio inherited, visible to the user


def test_cli_nonzero_exit_passthrough_with_receipt(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    proc = _run_cli(
        repo,
        "--job", "cli-fail",
        "--matrix", "os=ubuntu-latest",
        "--", sys.executable, "-c", "import sys; sys.exit(5)",
    )
    assert proc.returncode == 5, proc.stderr
    receipt = read_receipt(repo / ".benchreceipt" / "evidence" / "cli-fail")
    assert receipt["command"]["exit_code"] == 5
    validate_against_schema(receipt, "run")


def test_cli_secret_argv_is_redacted_in_receipt(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    proc = _run_cli(
        repo,
        "--job", "cli-secret",
        "--matrix", "os=ubuntu-latest",
        "--", sys.executable, "-c", "pass", "--token=do-not-store-me",
    )
    assert proc.returncode == 0, proc.stderr
    receipt = read_receipt(repo / ".benchreceipt" / "evidence" / "cli-secret")
    assert "do-not-store-me" not in json.dumps(receipt)
    assert "[REDACTED]" in receipt["command"]["display"]
