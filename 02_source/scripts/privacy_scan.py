#!/usr/bin/env python3
"""Privacy scanner (P027-T011 resume, PROJECT_BOOK §11.1).

Scans receipt / evidence / policy files for values that must never
appear in a BenchReceipt artefact: secret values and absolute user
(home-directory) paths.

What is scanned: ``*.json``, ``*.toml`` and ``SHA256SUMS.txt`` files
under the given roots (default: the current directory). Directories
that never hold evidence — ``.git``, ``.venv``, ``__pycache__``,
``.pytest_cache``, ``node_modules``, ``.tmp`` — are skipped.

What counts as a finding (each is a concrete leak, not a keyword hit):

- A JSON object key naming a secret (``token``, ``password``,
  ``secret``, ``api-key`` / ``api_key`` / ``apikey``, ``private_key``,
  ``access_token``, ``client_secret`` …) whose value is a non-empty
  string other than the redaction marker ``[REDACTED]``. Prose that
  merely *mentions* secrets (e.g. a schema ``description`` saying
  "must not contain secrets") is not a finding: only the key is
  judged, never the prose.
- A well-known credential *value* format anywhere in the scanned
  text: GitHub tokens (``ghp_`` / ``gho_`` / ``github_pat_``),
  ``sk-`` / ``sk-proj-`` API keys, AWS access keys (``AKIA…``),
  ``-----BEGIN … PRIVATE KEY-----`` blocks, ``Bearer <token>``.
  A 40/64-hex SHA (git SHAs, argv/report digests) is NOT a finding.
- An absolute user path: ``/home/<user>/``, ``/Users/<user>/``,
  ``C:\\Users\\<user>`` / ``C:/Users/<user>``, ``/root/``.
  Relative paths (``artifacts/junit.xml``) are fine.

Exit codes: 0 = no findings, 1 = one or more findings, 2 = usage
error (a root does not exist / is not a directory). Output is
deterministic (sorted paths, one line per finding plus a summary).
Oversize files (> 10 MiB) and unreadable files are reported as
skipped, not as findings — a receipt is schema-bounded far below
that size, so an over-limit file is itself suspicious, but the
scanner never loads it to decide.

Standard library only. No network access.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

__all__ = ["Finding", "scan_file", "scan_root", "scan_text"]

MAX_SCAN_BYTES = 10 * 1024 * 1024  # 10 MiB; receipts are schema-bounded << this.

SKIP_DIRS = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".tmp"}
)
SCAN_SUFFIXES = frozenset({".json", ".toml"})
SCAN_NAMES = frozenset({"SHA256SUMS.txt"})

# A JSON key that names a secret. Judged on the key, not on prose.
SECRET_KEY_RE = re.compile(
    r"(token|password|passwd|pwd|secret|api[-_]?key|apikey"
    r"|private[-_]?key|access[-_]?token|auth[-_]?token"
    r"|client[-_]?secret|session[-_]?key)$",
    re.IGNORECASE,
)

# Values that are explicitly NOT leaks (redaction markers / placeholders).
CLEAN_VALUES = frozenset({"", "[REDACTED]", "redacted", "null", "none"})

# Well-known credential value formats (specific shapes, not bare words).
SECRET_VALUE_RES = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{10,}"),
)

# Absolute user (home-directory) paths. Relative paths are fine.
ABS_PATH_RES = (
    re.compile(r"/home/[^/\s\"'\\]+/"),
    re.compile(r"/Users/[^/\s\"'\\]+/"),
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\"'\s]+"),
    re.compile(r"/root/"),
)

# A secret assignment in a TOML policy (JSON is covered structurally
# by the key walk above; TOML is line-oriented here).
TOML_SECRET_ASSIGN_RE = re.compile(
    r"(?im)^\s*(token|password|passwd|secret|api[-_]?key|apikey)\s*=",
)


class Finding:
    """One leak: ``(path, kind, detail)``."""

    def __init__(self, path: str, kind: str, detail: str) -> None:
        self.path = path
        self.kind = kind
        self.detail = detail

    def as_line(self) -> str:
        return f"LEAK {self.kind}: {self.path}: {self.detail}"


def _check_secret_key(key: str, value: object, path: str, findings: list[Finding]) -> None:
    """Flag a secret-named JSON key with a real (non-redacted) value."""
    if not SECRET_KEY_RE.search(key):
        return
    if not isinstance(value, str):
        return
    if value.strip().lower() in CLEAN_VALUES:
        return
    findings.append(
        Finding(path, "secret-key", f"key {key!r} carries a non-redacted value")
    )


def _walk_json(node: object, path: str, findings: list[Finding]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                _check_secret_key(key, value, path, findings)
            _walk_json(value, path, findings)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, path, findings)


def scan_text(text: str, path: str) -> list[Finding]:
    """Scan one file's text; returns its findings (possibly empty)."""
    findings: list[Finding] = []
    if path.endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError:
            findings.append(
                Finding(path, "unparsable-json", "file is not valid JSON")
            )
        else:
            _walk_json(data, path, findings)
    for pattern in SECRET_VALUE_RES:
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(
                    path, "secret-value",
                    f"credential-shaped value {match.group(0)[:24]!r}…",
                )
            )
            break
    if path.endswith(".toml") and TOML_SECRET_ASSIGN_RE.search(text):
        findings.append(
            Finding(path, "secret-key", "secret assignment in TOML policy")
        )
    for pattern in ABS_PATH_RES:
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(
                    path, "absolute-path",
                    f"absolute user path {match.group(0)!r}",
                )
            )
            break
    return findings


def _is_scannable(path: Path) -> bool:
    return path.name in SCAN_NAMES or path.suffix.lower() in SCAN_SUFFIXES


def scan_file(path: Path) -> tuple[list[Finding], str | None]:
    """Scan one file. Returns ``(findings, skip_reason_or_None)``."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        return [], f"unreadable ({exc})"
    if size > MAX_SCAN_BYTES:
        return [], f"oversize ({size} bytes > {MAX_SCAN_BYTES})"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [], f"unreadable ({exc})"
    text = raw.decode("utf-8", errors="replace")
    return scan_text(text, str(path)), None


def scan_root(root: Path) -> tuple[list[Finding], list[str], int]:
    """Scan a root recursively.

    Returns ``(findings, skipped_lines, files_scanned)``.
    """
    findings: list[Finding] = []
    skipped: list[str] = []
    scanned = 0
    for dirpath, dirnames, filenames in _walk(root):
        for filename in sorted(filenames):
            fpath = Path(dirpath) / filename
            if not _is_scannable(fpath):
                continue
            scanned += 1
            file_findings, skip_reason = scan_file(fpath)
            if skip_reason is not None:
                skipped.append(f"SKIP {fpath}: {skip_reason}")
            findings.extend(file_findings)
    findings.sort(key=lambda f: (f.path, f.kind, f.detail))
    return findings, skipped, scanned


def _walk(root: Path):
    """``os.walk`` that never descends into skipped directories."""
    import os

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        yield dirpath, dirnames, filenames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="privacy_scan.py",
        description=(
            "Scan receipt/evidence/policy files for secret values and "
            "absolute user paths that must never appear in a "
            "BenchReceipt artefact."
        ),
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=["."],
        help="directories to scan (default: current directory)",
    )
    args = parser.parse_args(argv)

    all_findings: list[Finding] = []
    all_skipped: list[str] = []
    total_scanned = 0
    for raw_root in args.roots:
        root = Path(raw_root)
        if not root.is_dir():
            print(f"privacy_scan: error: not a directory: {raw_root}", file=sys.stderr)
            return 2
        findings, skipped, scanned = scan_root(root)
        all_findings.extend(findings)
        all_skipped.extend(skipped)
        total_scanned += scanned

    for line in sorted(all_skipped):
        print(line)
    for finding in sorted(all_findings, key=lambda f: (f.path, f.kind)):
        print(finding.as_line())
    print(
        f"privacy_scan: {total_scanned} file(s) scanned, "
        f"{len(all_findings)} finding(s), {len(all_skipped)} skipped"
    )
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
