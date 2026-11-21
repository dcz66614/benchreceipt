"""command tests (P027-T003): argv digest, redaction, exit codes, shell=False."""

import hashlib
import json
import os
import re
import signal
import sys
from pathlib import Path

import pytest

from benchreceipt.canonical import canonical_json
from benchreceipt.command import (
    argv_sha256,
    display_command,
    normalize_argv,
    redact_argv,
    run_command,
)

ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


def test_normalize_argv_rejects_empty_and_non_strings():
    with pytest.raises(ValueError):
        normalize_argv([])
    with pytest.raises(ValueError):
        normalize_argv(["python", 3])  # type: ignore[list-item]


def test_argv_sha256_is_canonical_digest():
    argv = ["python", "-m", "pytest", "-q"]
    expected = hashlib.sha256(canonical_json(argv)).hexdigest()
    assert argv_sha256(argv) == expected
    # Order matters: a different order is a different command.
    assert argv_sha256(["-q", "pytest", "-m", "python"]) != expected
    assert len(argv_sha256(argv)) == 64


def test_redact_key_value_secret_forms():
    assert redact_argv(["cmd", "--token=abc123"]) == ["cmd", "[REDACTED]"]
    assert redact_argv(["cmd", "--password=hunter2"]) == ["cmd", "[REDACTED]"]
    assert redact_argv(["cmd", "--api-key=sk-xyz"]) == ["cmd", "[REDACTED]"]
    assert redact_argv(["cmd", "--api_key=sk-xyz"]) == ["cmd", "[REDACTED]"]
    assert redact_argv(["cmd", "--TOKEN=abc"]) == ["cmd", "[REDACTED]"]
    assert redact_argv(["cmd", "--Secret=abc"]) == ["cmd", "[REDACTED]"]


def test_redact_flag_then_value_form():
    assert redact_argv(["cmd", "--token", "abc123", "--other", "x"]) == [
        "cmd",
        "[REDACTED]",
        "[REDACTED]",
        "--other",
        "x",
    ]
    # A flag after a secret flag is a new flag, not a redacted value.
    assert redact_argv(["cmd", "--token", "--verbose"]) == [
        "cmd",
        "[REDACTED]",
        "--verbose",
    ]


def test_redact_bare_secret_tokens():
    assert redact_argv(["cmd", "my-secret-value"]) == ["cmd", "[REDACTED]"]
    assert redact_argv(["cmd", "prefix-token-suffix"]) == ["cmd", "[REDACTED]"]


def test_redact_leaves_benign_args_alone():
    argv = ["python", "-m", "pytest", "-q", "--junitxml=out.xml"]
    assert redact_argv(argv) == argv
    assert "hunter2" not in display_command(["cmd", "--password=hunter2"])


def test_display_truncates_to_schema_limit():
    long_argv = ["cmd"] + ["x" * 100] * 10
    display = display_command(long_argv)
    assert len(display) <= 512
    assert display.endswith("...")


def test_display_shortens_absolute_paths_to_basenames():
    assert display_command(["/usr/bin/python", "-m", "pytest"]) == (
        "python -m pytest"
    )
    assert display_command(["cmd", "--junitxml=/tmp/out/junit.xml"]) == (
        "cmd --junitxml=junit.xml"
    )
    assert display_command(["cmd", r"C:\Tools\pytest.exe", "-q"]) == (
        "cmd pytest.exe -q"
    )
    # Relative paths are left alone.
    assert display_command(["cmd", "rel/path/file.txt"]) == "cmd rel/path/file.txt"
    # The digest still covers the full argv.
    assert argv_sha256(["/usr/bin/python", "-m", "pytest"]) != argv_sha256(
        ["python", "-m", "pytest"]
    )


def test_run_command_exit_zero_and_timings():
    result = run_command([sys.executable, "-c", "print('hi')"])
    assert result.exit_code == 0
    assert result.argv_sha256 == argv_sha256([sys.executable, "-c", "print('hi')"])
    assert ISO_RE.match(result.started_at)
    assert ISO_RE.match(result.finished_at)
    assert result.started_at <= result.finished_at
    # Stdio is inherited, never stored.
    assert result.stdout_sha256 is None
    assert result.stderr_sha256 is None


def test_run_command_exit_code_passthrough():
    result = run_command([sys.executable, "-c", "import sys; sys.exit(7)"])
    assert result.exit_code == 7


def test_run_command_missing_executable_raises():
    with pytest.raises(FileNotFoundError):
        run_command(["definitely-not-a-real-binary-xyz"])


def test_run_command_signal_death_keeps_negative_returncode():
    code = (
        "import os, signal; "
        "os.kill(os.getpid(), signal.SIGTERM)"
    )
    result = run_command([sys.executable, "-c", code])
    assert result.exit_code == -signal.SIGTERM


def test_no_shell_true_anywhere_in_source():
    """shell=False is a hard requirement: grep the whole package."""
    src = Path(__file__).resolve().parents[2] / "src" / "benchreceipt"
    offenders = []
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "shell=True" in text or "shell = True" in text:
            offenders.append(str(path))
        if "os.system" in text or "os.popen" in text:
            offenders.append(f"{path} (os.system/popen)")
    assert offenders == []
    # And shell=False is actually used where subprocess runs.
    assert "shell=False" in (src / "command.py").read_text(encoding="utf-8")
    assert "shell=False" in (src / "git_identity.py").read_text(encoding="utf-8")
