"""CLI tests (P027-T008, PROJECT_BOOK §5.6, §6.4).

Drives the real CLI in a subprocess (``sys.executable -m benchreceipt``
with the venv python) wherever an exit code is asserted, so the numbers
are process exit codes, not in-process return values. The one exception
is INTERNAL_ERROR (exit 4): no honest input can force a verifier bug
from the outside, so that path is exercised in-process with a
monkeypatched ``evaluate_with_policy_path`` raising — exactly the
forced-internal-error case.

Covers: --help for the program and every subcommand; the verify
four-state exit codes 0/1/2/3 on S0 fixtures; missing
--expected-source-sha -> 3 (never a pass); invalid policy / missing
evidence -> 3 with a machine-readable INVALID result; expected run
id / attempt pins; missing evidence never passes; the report stub
(exit 0 on valid input, 3 on invalid input); the bundle subcommand
(build + verify + tamper -> 3); capture delegation (exit code is the
wrapped command's, receipt still written on failure).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchreceipt.schema import validate_against_schema

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "s0"


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "benchreceipt", *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(cwd) if cwd is not None else None,
    )


def _fixture_sha(fid: str) -> str:
    return json.loads((FIXTURES / fid / "expected.json").read_text())["expected_source_sha"]


def _verify_args(fid: str, out: Path, extra: list[str] | None = None) -> list[str]:
    args = [
        "verify",
        "--policy", str(FIXTURES / fid / "policy.toml"),
        "--evidence", str(FIXTURES / fid / "evidence"),
        "--expected-source-sha", _fixture_sha(fid),
        "--out", str(out),
    ]
    if extra:
        args.extend(extra)
    return args


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_top_level_help():
    proc = _run_cli("--help")
    assert proc.returncode == 0
    for word in ("capture", "verify", "report", "bundle"):
        assert word in proc.stdout


@pytest.mark.parametrize("sub", ["capture", "verify", "report", "bundle"])
def test_subcommand_help(sub: str):
    proc = _run_cli(sub, "--help")
    assert proc.returncode == 0, proc.stderr


def test_no_args_is_usage_error():
    proc = _run_cli()
    assert proc.returncode == 2


def test_unknown_subcommand_is_usage_error():
    proc = _run_cli("frobnicate")
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# verify exit codes 0/1/2/3 (subprocess, S0 fixtures)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fid,status,exit_code",
    [
        ("n01-single-pr-head", "BOUND_PASS", 0),
        ("g1-junit-failed", "BOUND_FAIL", 1),
        ("d1-matrix-missing", "UNBOUND", 2),
        ("f2-report-hash-mismatch", "INVALID", 3),
    ],
)
def test_verify_exit_codes(fid: str, status: str, exit_code: int, tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_cli(*_verify_args(fid, out))
    assert proc.returncode == exit_code, proc.stdout + proc.stderr
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == status
    validate_against_schema(result, "result")


def test_verify_missing_expected_source_sha_is_invalid(tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_cli(
        "verify",
        "--policy", str(FIXTURES / "n01-single-pr-head" / "policy.toml"),
        "--evidence", str(FIXTURES / "n01-single-pr-head" / "evidence"),
        "--out", str(out),
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "expected-source-sha" in proc.stderr
    assert not out.exists(), "no verification was performed, so no result is written"


def test_verify_invalid_sha_format_is_invalid(tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_cli(
        "verify",
        "--policy", str(FIXTURES / "n01-single-pr-head" / "policy.toml"),
        "--evidence", str(FIXTURES / "n01-single-pr-head" / "evidence"),
        "--expected-source-sha", "not-a-sha",
        "--out", str(out),
    )
    assert proc.returncode == 3


def test_verify_invalid_policy_file_is_invalid(tmp_path: Path):
    bad_policy = tmp_path / "bad.toml"
    bad_policy.write_text("source_mode = 42\n", encoding="utf-8")
    out = tmp_path / "verification.json"
    proc = _run_cli(
        "verify",
        "--policy", str(bad_policy),
        "--evidence", str(FIXTURES / "n01-single-pr-head" / "evidence"),
        "--expected-source-sha", _fixture_sha("n01-single-pr-head"),
        "--out", str(out),
    )
    assert proc.returncode == 3
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "INVALID"
    assert result["reason_codes"] == ["INVALID_POLICY"]
    validate_against_schema(result, "result")


def test_verify_missing_evidence_dir_is_invalid(tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_cli(
        "verify",
        "--policy", str(FIXTURES / "n01-single-pr-head" / "policy.toml"),
        "--evidence", str(tmp_path / "no-such-evidence"),
        "--expected-source-sha", _fixture_sha("n01-single-pr-head"),
        "--out", str(out),
    )
    assert proc.returncode == 3
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "INVALID"
    assert result["reason_codes"] == ["INVALID_EVIDENCE"]


def test_verify_empty_evidence_dir_is_unbound_never_pass(tmp_path: Path):
    empty = tmp_path / "evidence"
    empty.mkdir()
    out = tmp_path / "verification.json"
    proc = _run_cli(
        "verify",
        "--policy", str(FIXTURES / "n01-single-pr-head" / "policy.toml"),
        "--evidence", str(empty),
        "--expected-source-sha", _fixture_sha("n01-single-pr-head"),
        "--out", str(out),
    )
    assert proc.returncode == 2
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "UNBOUND"
    assert result["reason_codes"] == ["MATRIX_MISSING_JOB"]
    assert result["jobs_verified"] == 0


# ---------------------------------------------------------------------------
# Expected run id / attempt pins
# ---------------------------------------------------------------------------


def test_verify_expected_run_id_pin(tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_cli(*_verify_args(
        "n01-single-pr-head", out, ["--expected-run-id", "9001"]))
    assert proc.returncode == 0
    proc = _run_cli(*_verify_args(
        "n01-single-pr-head", out, ["--expected-run-id", "9002"]))
    assert proc.returncode == 2
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["reason_codes"] == ["RUN_ID_MISMATCH"]


def test_verify_expected_attempt_pin(tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_cli(*_verify_args(
        "n01-single-pr-head", out, ["--expected-attempt", "2"]))
    assert proc.returncode == 0
    proc = _run_cli(*_verify_args(
        "n01-single-pr-head", out, ["--expected-attempt", "1"]))
    assert proc.returncode == 2
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["reason_codes"] == ["RUN_ATTEMPT_MISMATCH"]


def test_verify_attempt_out_of_range_is_invalid(tmp_path: Path):
    out = tmp_path / "verification.json"
    proc = _run_cli(*_verify_args(
        "n01-single-pr-head", out, ["--expected-attempt", "0"]))
    assert proc.returncode == 3


# ---------------------------------------------------------------------------
# INTERNAL_ERROR (exit 4) — forced internal error, in-process
# ---------------------------------------------------------------------------


def test_verify_internal_error_exit_4(monkeypatch, tmp_path: Path, capsys):
    """A forced internal error (monkeypatched evaluate raising) exits 4
    with one short stderr line and no traceback-as-pass."""
    import benchreceipt.cli as cli

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated verifier bug")

    monkeypatch.setattr(cli, "evaluate_with_policy_path", _boom)
    out = tmp_path / "verification.json"
    code = cli.main(_verify_args("n01-single-pr-head", out))
    assert code == 4
    err = capsys.readouterr().err
    assert "internal error" in err
    assert "Traceback" not in err
    assert not out.exists()


# ---------------------------------------------------------------------------
# report stub
# ---------------------------------------------------------------------------


def _make_verification_json(tmp_path: Path) -> Path:
    out = tmp_path / "verification.json"
    proc = _run_cli(*_verify_args("n01-single-pr-head", out))
    assert proc.returncode == 0
    return out


def test_report_stub_valid_input(tmp_path: Path):
    result_path = _make_verification_json(tmp_path)
    html_path = tmp_path / "report.html"
    proc = _run_cli("report", "--input", str(result_path), "--html", str(html_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = html_path.read_text(encoding="utf-8")
    assert "BOUND_PASS" in html
    assert "P027-T010" in html  # stub names the owner of the real renderer


def test_report_stub_invalid_input(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    proc = _run_cli("report", "--input", str(bad), "--html", str(tmp_path / "r.html"))
    assert proc.returncode == 3


def test_report_stub_wrong_schema(tmp_path: Path):
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"schema": "benchreceipt.run/v1"}), encoding="utf-8")
    proc = _run_cli("report", "--input", str(wrong), "--html", str(tmp_path / "r.html"))
    assert proc.returncode == 3


def test_report_stub_missing_input(tmp_path: Path):
    proc = _run_cli(
        "report", "--input", str(tmp_path / "absent.json"),
        "--html", str(tmp_path / "r.html"),
    )
    assert proc.returncode == 3


# ---------------------------------------------------------------------------
# bundle subcommand
# ---------------------------------------------------------------------------


def test_bundle_build_and_verify_smoke(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    proc = _run_cli(
        "bundle",
        "--evidence", str(FIXTURES / "n02-two-job-pr-head" / "evidence"),
        "--out", str(bundle_dir),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (bundle_dir / "SHA256SUMS.txt").is_file()
    proc = _run_cli("bundle", "--verify", str(bundle_dir))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_bundle_verify_tampered_is_invalid(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    proc = _run_cli(
        "bundle",
        "--evidence", str(FIXTURES / "n01-single-pr-head" / "evidence"),
        "--out", str(bundle_dir),
    )
    assert proc.returncode == 0
    junit = bundle_dir / "unit-linux-py312" / "artifacts" / "junit.xml"
    junit.write_bytes(junit.read_bytes() + b" ")
    proc = _run_cli("bundle", "--verify", str(bundle_dir))
    assert proc.returncode == 3
    assert "HASH_MISMATCH" in proc.stderr


def test_bundle_verify_not_a_bundle_is_invalid(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = _run_cli("bundle", "--verify", str(empty))
    assert proc.returncode == 3


def test_bundle_needs_a_mode(tmp_path: Path):
    proc = _run_cli("bundle")
    assert proc.returncode == 2
    proc = _run_cli("bundle", "--verify", str(tmp_path), "--evidence", str(tmp_path))
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# capture delegation
# ---------------------------------------------------------------------------


def _init_git_repo(repo: Path) -> None:
    def _git(*args: str) -> None:
        proc = subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=60
        )
        assert proc.returncode == 0, proc.stderr

    _git("init", "-q")
    _git("config", "user.email", "t008@example.invalid")
    _git("config", "user.name", "T008")
    (repo / "README.md").write_text("# t008 capture smoke\n", encoding="utf-8")
    _git("add", "-A")
    _git("commit", "-q", "-m", "init")


_JUNIT = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<testsuite name="suite" tests="1" failures="0" errors="0" skipped="0">'
    '<testcase classname="t" name="test_0"></testcase></testsuite>'
)


def test_capture_delegates_and_returns_command_exit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    write_cmd = (
        f"import pathlib; pathlib.Path('junit.xml').write_text({_JUNIT!r})"
    )
    proc = _run_cli(
        "capture",
        "--job", "unit-linux-py312",
        "--matrix", "os=ubuntu-latest,python=3.12",
        "--junit", "junit.xml",
        "--", sys.executable, "-c", write_cmd,
        cwd=repo,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    receipt = json.loads(
        (repo / ".benchreceipt" / "evidence" / "unit-linux-py312" / "receipt.json")
        .read_text(encoding="utf-8")
    )
    assert receipt["job_id"] == "unit-linux-py312"
    assert receipt["command"]["exit_code"] == 0


def test_capture_failing_command_still_writes_receipt(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    proc = _run_cli(
        "capture",
        "--job", "unit-linux-py312",
        "--matrix", "os=ubuntu-latest,python=3.12",
        "--", sys.executable, "-c", "import sys; sys.exit(3)",
        cwd=repo,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    receipt = json.loads(
        (repo / ".benchreceipt" / "evidence" / "unit-linux-py312" / "receipt.json")
        .read_text(encoding="utf-8")
    )
    assert receipt["command"]["exit_code"] == 3


def test_capture_explicit_sha_flag(tmp_path: Path):
    """FIX-R13a (F-10, ADR-006): the real CLI accepts
    --source-mode explicit_sha --expected-sha <HEAD> and the receipt
    carries source_mode="explicit_sha" with the pinned SHA."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    write_cmd = (
        f"import pathlib; pathlib.Path('junit.xml').write_text({_JUNIT!r})"
    )
    proc = _run_cli(
        "capture",
        "--job", "unit-linux-py312",
        "--matrix", "os=ubuntu-latest,python=3.12",
        "--junit", "junit.xml",
        "--source-mode", "explicit_sha",
        "--expected-sha", head,
        "--", sys.executable, "-c", write_cmd,
        cwd=repo,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    receipt = json.loads(
        (repo / ".benchreceipt" / "evidence" / "unit-linux-py312" / "receipt.json")
        .read_text(encoding="utf-8")
    )
    validate_against_schema(receipt, "run")
    assert receipt["git"]["source_mode"] == "explicit_sha"
    assert receipt["git"]["expected_source_sha"] == head
    assert receipt["git"]["head_sha"] == head


@pytest.mark.parametrize(
    "extra",
    [
        ["--source-mode", "explicit_sha"],
        ["--source-mode", "explicit_sha", "--expected-sha", "NOT-A-SHA"],
        ["--expected-sha", "b" * 40],
    ],
)
def test_capture_explicit_sha_flag_rejects_bad_pins(tmp_path: Path, extra):
    """Incomplete / malformed / mode-less pins are capture failures
    (exit 4, INTERNAL_ERROR) and write no receipt."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    proc = _run_cli(
        "capture",
        "--job", "unit-linux-py312",
        "--matrix", "os=ubuntu-latest,python=3.12",
        *extra,
        "--", sys.executable, "-c", "pass",
        cwd=repo,
    )
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert not (repo / ".benchreceipt").exists()
