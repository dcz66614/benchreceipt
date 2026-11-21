"""FIX-R13a F-09 after-check: credential URLs + case variants + controls.

Supplements repro2 R1b, whose list has no credential-bearing URL case.
Run from the repo root with the project venv; exit 0 only if every
secret/path form is redacted or shortened and every control is intact.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_source" / "src"))
from benchreceipt.command import display_command, redact_argv

FAILURES = []

def check(argv, forbidden, must_contain=None):
    display = display_command(argv)
    for secret in forbidden:
        if secret in display:
            FAILURES.append(f"LEAK {argv!r} -> {display!r} contains {secret!r}")
    if must_contain is not None and must_contain not in display:
        FAILURES.append(f"MISSING {argv!r} -> {display!r} lacks {must_contain!r}")
    print(f"{argv!r} -> {display!r}")

# Credential-bearing URLs (not in repro2 R1b).
check(["curl", "https://user:s3cret@example.com/x"], ["s3cret", "user:"],
      "https://[REDACTED]@example.com/x")
check(["curl", "https://user@example.com/x"], ["user@example"],
      "https://[REDACTED]@example.com/x")
check(["curl", "http://admin:p4ss@internal.example:8080/a/b"], ["p4ss", "admin"],
      "http://[REDACTED]@internal.example:8080/a/b")
# Case variants of the widened flags.
for flag in ["--KEY", "--Auth", "--PASSWD", "--Private-Key", "--CREDENTIAL=hunter2"]:
    argv = ["pytest", flag] if "=" not in flag else ["pytest", flag]
    if "=" not in flag:
        argv = ["pytest", flag, "hunter2"]
    check(argv, ["hunter2"], "[REDACTED]")
# Controls: already-covered forms unchanged; benign tokens untouched.
assert redact_argv(["cmd", "--token=abc123"]) == ["cmd", "[REDACTED]"]
assert redact_argv(["cmd", "--api-key", "sk-xyz"]) == ["cmd", "[REDACTED]", "[REDACTED]"]
assert display_command(["python", "-m", "pytest", "-q", "--os=ubuntu-latest"]) == \
    "python -m pytest -q --os=ubuntu-latest"
assert display_command(["git", "clone", "git@github.com:org/repo.git"]) == \
    "git clone git@github.com:org/repo.git"
assert display_command(["curl", "https://example.com/path/file.txt"]) == \
    "curl https://example.com/path/file.txt"
print("controls OK")

if FAILURES:
    print("FAILURES:")
    for f in FAILURES:
        print(" ", f)
    sys.exit(1)
print("F-09 after-check: all forms redacted/shortened, controls intact")
