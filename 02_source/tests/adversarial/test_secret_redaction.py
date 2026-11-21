"""Probe (d) — secret redaction.

Secrets can reach a receipt through four channels: the wrapped
command's argv (``command.display``), CI event JSON values (the
``GITHUB_EVENT_PATH`` payload), JUnit failure text (only the counted
summary is stored), and LCOV source paths (no LCOV summary is stored
at all). No secret value may appear in any ``receipt.json``.

NOTE (observation, not a receipt leak): a declared report artifact is
copied verbatim into ``artifacts/`` by design — a secret printed by
the test itself into its JUnit failure text therefore still exists in
the artifact file, even though the receipt is clean. That is the test
output's own content, not something BenchReceipt adds; see
SECURITY_FINDINGS.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from _evidence import JUNIT_XML, head, make_repo
from benchreceipt.capture import capture
from benchreceipt.command import display_command, redact_argv
from benchreceipt.verify import evaluate

TOKEN = "T011_SECRET_TOKEN_9f3a7c21"
API_KEY = "T011_SECRET_APIKEY_4b8d2e65"
PASSWORD = "T011_SECRET_PASSWORD_1c5f8a93"
EVENT_SECRET = "T011_SECRET_EVENT_6e2b49ad"
JUNIT_SECRET = "T011_SECRET_JUNIT_8d4c17f2"
LCOV_SECRET = "T011_SECRET_LCOV_3a9e65b8"

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


def _receipt_text(repo: Path) -> str:
    return (
        repo / ".benchreceipt" / "evidence" / "unit-linux-py312"
        / "receipt.json"
    ).read_text(encoding="utf-8")


def _run_capture(repo: Path, argv, **kwargs):
    return capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=argv, repo_path=repo, cwd=repo, **kwargs,
    )


# --- argv redaction (unit level) ------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["pytest", "--token", TOKEN],
        ["pytest", f"--token={TOKEN}"],
        ["pytest", "--api-key", API_KEY],
        ["pytest", f"--api-key={API_KEY}"],
        ["pytest", f"password={PASSWORD}"],
        ["pytest", "--password", PASSWORD],
        ["pytest", "--TOKEN", TOKEN],          # case-insensitive flag
        ["pytest", "--api_key", API_KEY],      # underscore variant
        ["pytest", "--apikey", API_KEY],
        ["pytest", "my-secret-value"],         # bare secret-bearing token
    ],
)
def test_argv_secret_tokens_are_redacted(argv):
    """Any secret-bearing token (or its following value) is redacted."""
    redacted = redact_argv(argv)
    joined = " ".join(redacted)
    for secret in (TOKEN, API_KEY, PASSWORD):
        assert secret not in joined, redacted
    assert "[REDACTED]" in redacted
    display = display_command(argv)
    for secret in (TOKEN, API_KEY, PASSWORD):
        assert secret not in display, display


def test_argv_non_secret_tokens_pass_through():
    """Redaction does not mangle ordinary arguments."""
    argv = ["python", "-m", "pytest", "-q", "--os=ubuntu-latest"]
    assert redact_argv(argv) == argv
    assert display_command(argv) == "python -m pytest -q --os=ubuntu-latest"


def test_argv_secret_flag_followed_by_flag_does_not_swallow_flag():
    """A flag after a secret flag is judged on its own text."""
    redacted = redact_argv(["pytest", "--token", "--verbose"])
    assert redacted == ["pytest", "[REDACTED]", "--verbose"]


# --- argv redaction (capture end to end) ----------------------------------


def test_capture_argv_secrets_never_enter_receipt(tmp_path: Path):
    """Secrets passed as argv values never appear in the receipt."""
    repo = make_repo(tmp_path / "repo")
    script = f"open('junit.xml', 'w').write({JUNIT_XML!r})"
    result = _run_capture(
        repo,
        [sys.executable, "-c", script,
         "--token", TOKEN, f"--api-key={API_KEY}", f"password={PASSWORD}"],
        junit_path="junit.xml",
    )
    assert result.exit_code == 0
    text = _receipt_text(repo)
    for secret in (TOKEN, API_KEY, PASSWORD):
        assert secret not in text, text
    assert "[REDACTED]" in result.receipt["command"]["display"]
    verdict = evaluate(LOCAL_POLICY, head(repo), repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "BOUND_PASS", verdict


# --- FIX-R13a (F-09): widened secret flags + path forms ----------------
# T013 found the old SECRET_HINTS (token/password/secret/api-key only)
# let common secret flag names and several path/URL forms leak verbatim
# into command.display. Every form below must redact/shorten; the
# spec-named forms (--token/--api-key) keep their old behaviour.

NEW_SECRET_FLAGS = [
    "--key", "--auth", "--passwd", "--pwd",
    "--passphrase", "--credential", "--private-key", "--private_key",
]
NEW_SECRET_VALUE = "F09_SECRET_VALUE_7d2e9a41"


@pytest.mark.parametrize("flag", NEW_SECRET_FLAGS)
@pytest.mark.parametrize("spelling", ["space", "equals"])
def test_argv_new_secret_flags_are_redacted(flag, spelling):
    """Every widened secret flag redacts its value, in both spellings."""
    if spelling == "space":
        argv = ["pytest", flag, NEW_SECRET_VALUE]
    else:
        argv = ["pytest", f"{flag}={NEW_SECRET_VALUE}"]
    redacted = redact_argv(argv)
    assert NEW_SECRET_VALUE not in " ".join(redacted), redacted
    assert "[REDACTED]" in redacted
    display = display_command(argv)
    assert NEW_SECRET_VALUE not in display, display
    assert "[REDACTED]" in display


@pytest.mark.parametrize(
    "flag",
    ["--KEY", "--Key", "--AUTH", "--Auth", "--PASSWD", "--Passwd",
     "--PWD", "--Pwd", "--PASSPHRASE", "--Passphrase",
     "--CREDENTIAL", "--Credential", "--PRIVATE-KEY", "--Private-Key"],
)
def test_argv_new_secret_flags_are_case_insensitive(flag):
    """Secret-flag matching is case-insensitive (as for --TOKEN)."""
    argv = ["pytest", flag, NEW_SECRET_VALUE]
    assert NEW_SECRET_VALUE not in display_command(argv)
    assert "[REDACTED]" in display_command(argv)


@pytest.mark.parametrize(
    "token,expected_display",
    [
        # UNC paths shorten to the basename.
        ("\\\\server\\share\\file.txt", "file.txt"),
        ("\\\\server\\share\\deep\\file.txt", "file.txt"),
        # file:// URLs shorten to the basename.
        ("file:///home/sam/file.txt", "file.txt"),
        ("file://server/share/file.txt", "file.txt"),
        # Colon-embedded absolute paths keep the prefix, drop the path.
        ("prefix:/home/sam/file.txt", "prefix:file.txt"),
        ("prefix:C:/Users/sam/file.txt", "prefix:C:file.txt"),
        ("prefix:C:\\Users\\sam\\file.txt", "prefix:C:file.txt"),
        # Credential-bearing URLs lose the userinfo, keep host/path.
        ("https://user:s3cret@example.com/x",
         "'https://[REDACTED]@example.com/x'"),
        ("https://user@example.com/x",
         "'https://[REDACTED]@example.com/x'"),
        ("http://admin:p4ss@internal.example:8080/a/b",
         "'http://[REDACTED]@internal.example:8080/a/b'"),
        # Plain URLs and scp-like remotes are not local paths: untouched.
        ("https://example.com/path/file.txt",
         "https://example.com/path/file.txt"),
        ("git@github.com:org/repo.git", "git@github.com:org/repo.git"),
        # Already-covered forms, unchanged (controls).
        ("/home/sam/file.txt", "file.txt"),
        ("rel/path/file.txt", "rel/path/file.txt"),
    ],
)
def test_display_shortens_new_path_and_url_forms(token, expected_display):
    """UNC / file:// / embedded-path / credential-URL tokens never leak
    a username, home layout or password into the display string."""
    assert display_command(["cmd", token]) == f"cmd {expected_display}"
    for secret in ("sam", "s3cret", "p4ss", "admin"):
        assert secret not in display_command(["cmd", token])


@pytest.mark.parametrize(
    "argv",
    [
        ["pytest", "--key=/home/sam/secret.txt"],
        ["curl", "https://user:s3cret@example.com/x"],
        ["pytest", "--auth", "abc123", "--key", "hunter2"],
    ],
)
def test_display_new_forms_after_equals_and_as_values(argv):
    """The new forms also redact when they appear as a --flag=value or
    as the value of a non-secret flag (curl URL)."""
    display = display_command(argv)
    for leaked in ("hunter2", "abc123", "s3cret", "user", "/home/sam"):
        assert leaked not in display, display


def test_capture_new_secret_flags_and_paths_never_enter_receipt(tmp_path: Path):
    """End to end: secrets under the widened flags and a UNC path in
    argv never appear in the receipt; the run still verifies."""
    repo = make_repo(tmp_path / "repo")
    script = f"open('junit.xml', 'w').write({JUNIT_XML!r})"
    unc = "\\\\server\\share\\secret-file.txt"
    result = _run_capture(
        repo,
        [sys.executable, "-c", script,
         "--key", NEW_SECRET_VALUE, f"--auth={NEW_SECRET_VALUE}",
         "--passwd", NEW_SECRET_VALUE, unc],
        junit_path="junit.xml",
    )
    assert result.exit_code == 0
    text = _receipt_text(repo)
    for leaked in (NEW_SECRET_VALUE, "server", "share", "secret-file"):
        assert leaked not in text, text
    assert "[REDACTED]" in result.receipt["command"]["display"]
    verdict = evaluate(LOCAL_POLICY, head(repo), repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "BOUND_PASS", verdict


def test_capture_ci_event_secrets_never_enter_receipt(tmp_path: Path):
    """Secrets inside the GITHUB_EVENT_PATH payload stay out of receipts.

    ``collect_ci_metadata`` reads the event JSON (allowlisted fields
    only) but ``capture`` persists none of the payload: only run id,
    attempt, workflow, event name and SHAs reach the receipt.
    """
    repo = make_repo(tmp_path / "repo")
    sha = head(repo)
    event = {
        "pull_request": {
            "head": {"sha": sha},
            "title": f"leak {EVENT_SECRET} in title",
            "body": f"token={EVENT_SECRET}",
            "number": 7,
        },
        "repository": {"full_name": "example/repo"},
        "secret_note": EVENT_SECRET,
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    (repo / "junit.xml").write_text(JUNIT_XML, encoding="utf-8")
    env = {
        "GITHUB_SHA": sha,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW": "CI",
    }
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "pass"],
        repo_path=repo, junit_path="junit.xml", cwd=repo, env=env,
    )
    text = _receipt_text(repo)
    assert EVENT_SECRET not in text, text
    assert result.receipt["git"]["source_mode"] == "pr_head"
    policy = dict(LOCAL_POLICY)
    policy["source_mode"] = "pr_head"
    policy["expected_workflow"] = "CI"
    verdict = evaluate(policy, sha, repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "BOUND_PASS", verdict
    assert EVENT_SECRET not in json.dumps(verdict)


# --- JUnit failure text -----------------------------------------------------


def test_capture_junit_failure_text_secret_stays_out_of_receipt(tmp_path: Path):
    """A secret in a JUnit failure message is counted, never stored."""
    repo = make_repo(tmp_path / "repo")
    failing = (
        '<?xml version="1.0"?>\n'
        '<testsuites><testsuite name="s" tests="1" failures="1" errors="0"'
        ' skipped="0">'
        '<testcase classname="s" name="t1">'
        f'<failure message="auth failed, token was {JUNIT_SECRET}"/>'
        "</testcase>"
        "</testsuite></testsuites>\n"
    )
    (repo / "junit.xml").write_text(failing, encoding="utf-8")
    result = _run_capture(repo, [sys.executable, "-c", "pass"], junit_path="junit.xml")
    assert result.receipt["junit"] == {
        "tests": 1, "failures": 1, "errors": 0, "skipped": 0,
    }
    text = _receipt_text(repo)
    assert JUNIT_SECRET not in text, text
    verdict = evaluate(LOCAL_POLICY, head(repo), repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "BOUND_FAIL", verdict
    assert "JUNIT_FAILED" in verdict["reason_codes"], verdict
    assert JUNIT_SECRET not in json.dumps(verdict)


# --- LCOV paths -------------------------------------------------------------


def _lcov_with_sf(sf: str) -> str:
    return f"TN:\nSF:{sf}\nDA:1,1\nLF:1\nLH:1\nend_of_record\n"


def test_capture_lcov_source_path_secret_stays_out_of_receipt(tmp_path: Path):
    """A secret-looking LCOV SF path is never stored in the receipt.

    Capture stores no LCOV summary (frozen schema has no field for
    one); the SF path lives only in the artifact file itself.
    """
    repo = make_repo(tmp_path / "repo")
    (repo / "lcov.info").write_text(
        _lcov_with_sf(f"src/token-{LCOV_SECRET}.py"), encoding="utf-8"
    )
    (repo / "junit.xml").write_text(JUNIT_XML, encoding="utf-8")
    policy = dict(LOCAL_POLICY)
    policy["reports"] = {"junit": "optional", "lcov": "required"}
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "pass"],
        repo_path=repo, junit_path="junit.xml", lcov_path="lcov.info", cwd=repo,
    )
    text = _receipt_text(repo)
    assert LCOV_SECRET not in text, text
    assert "lcov" not in result.receipt  # no LCOV summary field exists
    verdict = evaluate(policy, head(repo), repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "BOUND_PASS", verdict


def test_capture_lcov_absolute_sf_path_fails_verification(tmp_path: Path):
    """An absolute SF path is LCOV_MALFORMED at verify time (INVALID)."""
    repo = make_repo(tmp_path / "repo")
    (repo / "lcov.info").write_text(
        _lcov_with_sf("/home/user/secret-project/src/code.py"), encoding="utf-8"
    )
    (repo / "junit.xml").write_text(JUNIT_XML, encoding="utf-8")
    policy = dict(LOCAL_POLICY)
    policy["reports"] = {"junit": "optional", "lcov": "required"}
    _run_capture(
        repo, [sys.executable, "-c", "pass"],
        junit_path="junit.xml", lcov_path="lcov.info",
    )
    verdict = evaluate(policy, head(repo), repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "INVALID", verdict
    assert "LCOV_MALFORMED" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 0, verdict


@pytest.mark.parametrize(
    "sf",
    [
        "/etc/passwd",
        "C:\\Users\\victim\\code.py",
        "C:/Users/victim/code.py",
        "..\\..\\secret.py",
        "../secret.py",
        "src\\..\\secret.py",
    ],
)
def test_lcov_sf_path_escape_rejected(tmp_path: Path, sf: str):
    """LCOV SF paths that are absolute or escaping are malformed."""
    from benchreceipt.reports.lcov import LcovError, parse_lcov

    with pytest.raises(LcovError):
        parse_lcov(_lcov_with_sf(sf).encode("utf-8"))
