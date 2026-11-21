"""Command wrapping for BenchReceipt capture (P027-T003).

Wraps one explicit user-supplied argv and runs it with
``subprocess.run(..., shell=False)`` — a shell string is NEVER built
(PROJECT_BOOK §11.2). The full argv is never stored: only the
canonical argv digest and a redacted display string go into the
receipt (PROJECT_BOOK §11.1).

Privacy rules:

- ``argv_sha256`` is the SHA-256 of the canonical JSON of the argv
  list (see :mod:`benchreceipt.canonical`).
- The display string redacts secrets: any argv token containing a
  secret hint (``token`` / ``password`` / ``secret`` / ``api-key`` /
  ``apikey`` / ``api_key`` / ``key`` / ``auth`` / ``passwd`` / ``pwd`` /
  ``passphrase`` / ``credential`` / ``private-key`` — FIX-R13a / F-09,
  matching the privacy scanner's secret names), case-insensitive, is
  replaced wholesale with ``[REDACTED]`` — including ``--key=value``
  forms — and so is the value token that immediately follows a
  secret-named flag (``--token abc123`` redacts ``abc123`` too). A
  token that merely *follows* a secret flag but starts with ``-`` is
  a new flag, not a value, and is judged on its own text. Absolute-path
  tokens are shortened to their basename so the display never leaks a
  home directory layout (the full argv is still bound by the digest);
  UNC paths, ``file://`` URLs, colon-embedded absolute paths and the
  userinfo of credential-bearing URLs are shortened/redacted the same
  way.
- stdout/stderr are INHERITED (not captured, not stored, not hashed):
  the wrapped command's output streams live to the terminal / CI log
  exactly as if run directly, and no log bytes ever enter a receipt.
  That is why ``CommandResult.stdout_sha256`` / ``stderr_sha256`` are
  always ``None`` in v1 — the digest fields exist for a future
  streaming-hash implementation, not as stored content.
- Signal-killed processes keep Python's negative ``returncode`` in the
  receipt (ADR-001 decision 9); the CLI maps it to ``128 + signum``
  for the process exit code, which cannot be negative.

Standard library only.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from benchreceipt.canonical import canonical_hash

__all__ = [
    "CommandResult",
    "argv_sha256",
    "normalize_argv",
    "redact_argv",
    "run_command",
    "utc_now_iso",
]

REDACTED = "[REDACTED]"

# Case-insensitive substrings that mark a token (or a flag name) as secret.
# FIX-R13a (F-09): the old list (token/password/secret/api-key only)
# missed common secret flag names, so e.g. `--key hunter2` leaked
# verbatim into command.display. The widened list matches the names
# the project's own privacy scanner treats as secret
# (scripts/privacy_scan.py SECRET_KEY_RE) plus passphrase/credential.
SECRET_HINTS = (
    "token", "password", "secret", "api-key", "apikey", "api_key",
    "key", "auth", "passwd", "pwd", "passphrase", "credential",
    "private-key", "private_key",
)

# Display strings longer than the run.v1 schema limit (512) are cut to
# this length with an ellipsis; the digest still covers the full argv.
_MAX_DISPLAY_LEN = 512


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with a ``Z`` suffix (millis)."""
    now = datetime.now(timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """Validate and normalise an argv list.

    Returns a plain ``list[str]``. Raises ``ValueError`` for an empty
    argv or any non-string element — capture never runs an empty or
    ill-typed command.
    """
    items = list(argv)
    if not items:
        raise ValueError("argv must not be empty")
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"argv elements must be strings, got {type(item).__name__}")
    return items


def _flag_name(token: str) -> str:
    """Flag name of a token (``--token=x`` -> ``token``), else ``""``."""
    stripped = token.lstrip("-")
    if not stripped or stripped == token:
        return ""
    return stripped.split("=", 1)[0]


def _is_secret_token(token: str) -> bool:
    """True when the token itself names (or carries) a secret."""
    lowered = token.lower()
    return any(hint in lowered for hint in SECRET_HINTS)


def redact_argv(argv: Sequence[str]) -> list[str]:
    """Return the argv with secret-bearing tokens replaced by ``[REDACTED]``.

    A token is redacted when it contains a secret hint (covers
    ``--token=abc``, ``--api-key`` and bare values such as
    ``my-secret-value``), or when it is the value immediately following
    a secret-named flag (``--token abc123``). Non-secret tokens pass
    through unchanged.
    """
    items = normalize_argv(argv)
    redacted: list[str] = []
    expect_value = False
    for token in items:
        if expect_value and not token.startswith("-"):
            redacted.append(REDACTED)
            expect_value = False
            continue
        expect_value = False
        if _is_secret_token(token):
            redacted.append(REDACTED)
            # A bare secret flag (no '=') takes its value next.
            if "=" not in token:
                expect_value = True
            continue
        redacted.append(token)
    return redacted


def argv_sha256(argv: Sequence[str]) -> str:
    """SHA-256 of the canonical JSON of the argv list."""
    return canonical_hash(normalize_argv(argv))


def _shorten_path_token(token: str) -> str:
    """Shorten a path-like token so the display never leaks layouts.

    Receipts must never contain absolute user paths (PROJECT_BOOK
    §11.1): a display token that is an absolute POSIX (``/...``) or
    Windows (``C:\\...`` / ``C:/...``) path is replaced by its
    basename, and so is the value part of a ``--key=/abs/path`` token.
    FIX-R13a (F-09) also shortens UNC paths (``\\\\server\\share\\…``),
    ``file://`` URLs, colon-embedded absolute paths
    (``prefix:/abs/path`` → ``prefix:base``), and redacts the userinfo
    of credential-bearing URLs (``https://user:pass@host/…`` →
    ``https://[REDACTED]@host/…``). Relative paths pass through
    unchanged. The full argv is still bound by ``argv_sha256`` — the
    display is only human-readable, so shortening it loses no evidence.
    """
    if "=" in token:
        head, value = token.split("=", 1)
        short = _shorten_value(value)
        return f"{head}={short}" if short is not None else token
    short = _shorten_value(token)
    return short if short is not None else token


def _shorten_value(value: str) -> str | None:
    """Shortened display form of one argv value, or None to leave it.

    Checked in order: credential-bearing URLs (userinfo redacted),
    ``file://`` URLs (basename), UNC paths (basename), absolute
    POSIX/Windows paths (basename), colon-embedded absolute paths
    (``prefix:/abs/path`` → ``prefix:base``). A plain URL without
    credentials is not a local path and is left alone.
    """
    if "://" in value:
        scheme, rest = value.split("://", 1)
        authority = rest.split("/", 1)[0]
        if "@" in authority:
            after = rest[len(authority):]
            host = authority.rsplit("@", 1)[-1]
            return f"{scheme}://{REDACTED}@{host}{after}"
        if scheme.lower() == "file":
            base = rest.replace("\\", "/").rsplit("/", 1)[-1]
            base = base.split("?", 1)[0].split("#", 1)[0]
            return base or None
        return None
    # UNC path: \\server\share\file.txt -> file.txt
    if value.startswith("\\\\"):
        parts = [part for part in value.split("\\") if part]
        return parts[-1] if parts else None
    short = _basename_of_absolute(value)
    if short is not None:
        return short
    # Colon-embedded absolute path: prefix:/abs/path -> prefix:base
    # (and the backslash spelling prefix:C:\abs\path). The "://"
    # case is handled above, so a scheme is never mangled here.
    for sep in (":/", ":\\"):
        idx = value.find(sep)
        if idx > 0:
            base = value[idx + 2:].replace("\\", "/").rsplit("/", 1)[-1]
            if base:
                return value[: idx + 1] + base
    return None


def _basename_of_absolute(value: str) -> str | None:
    """Basename of ``value`` when it is an absolute path, else None."""
    stripped = value.rstrip("/\\")
    if not stripped:
        return None
    if stripped.startswith("/"):
        base = stripped.rsplit("/", 1)[-1]
    elif len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in ("\\", "/"):
        base = stripped.replace("\\", "/").rsplit("/", 1)[-1]
    else:
        return None
    return base or None


def display_command(argv: Sequence[str]) -> str:
    """Redacted, shell-quoted display string for the receipt.

    Secret tokens are redacted (see :func:`redact_argv`) and absolute
    paths are shortened to basenames, so the display never leaks
    secrets or home-directory layouts. Truncated to the 512-char
    schema limit with an ellipsis when the (redacted) command is
    longer; the digest still covers the full argv.
    """
    display = shlex.join(_shorten_path_token(t) for t in redact_argv(argv))
    if len(display) > _MAX_DISPLAY_LEN:
        display = display[: _MAX_DISPLAY_LEN - 3] + "..."
    return display


@dataclass(frozen=True)
class CommandResult:
    """Outcome of one wrapped command run.

    ``exit_code`` is the raw ``subprocess`` returncode: 0–255 normally,
    negative when the process was killed by a signal. ``stdout_sha256``
    / ``stderr_sha256`` are always ``None`` in v1 — stdio is inherited
    and never stored (see module docstring).
    """

    argv: tuple[str, ...]
    argv_sha256: str
    display: str
    exit_code: int
    started_at: str
    finished_at: str
    stdout_sha256: str | None = None
    stderr_sha256: str | None = None


def run_command(
    argv: Sequence[str],
    cwd: str | Path | None = None,
    timeout: float | None = None,
) -> CommandResult:
    """Run ``argv`` with ``shell=False`` and record exit code + timings.

    Stdout/stderr are inherited from the calling process. Raises
    ``ValueError`` for an empty/non-string argv; ``FileNotFoundError``
    when the executable does not exist; ``subprocess.TimeoutExpired``
    when ``timeout`` elapses. The command is never run through a shell.
    """
    items = normalize_argv(argv)
    started_at = utc_now_iso()
    proc = subprocess.run(
        items,
        shell=False,
        cwd=str(cwd) if cwd is not None else None,
        timeout=timeout,
    )
    finished_at = utc_now_iso()
    return CommandResult(
        argv=tuple(items),
        argv_sha256=argv_sha256(items),
        display=display_command(items),
        exit_code=proc.returncode,
        started_at=started_at,
        finished_at=finished_at,
    )
