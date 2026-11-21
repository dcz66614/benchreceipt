"""Tests for scripts/privacy_scan.py (P027-T011 resume).

The scanner is the T011 privacy gate: it must flag real leaks
(secret values, secret-named keys, absolute home paths) and must NOT
flag the things BenchReceipt legitimately stores (40/64-hex SHAs,
``[REDACTED]`` displays, schema prose that merely mentions secrets).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "s0"


def _load_scanner():
    spec = importlib.util.spec_from_file_location(
        "privacy_scan", SCRIPTS / "privacy_scan.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


def _clean_receipt_text() -> str:
    return (
        FIXTURES / "n06-single-event-sha" / "evidence" / "unit-linux-py312"
        / "receipt.json"
    ).read_text(encoding="utf-8")


# --- unit: clean inputs stay clean ------------------------------------------


def test_clean_receipt_has_no_findings():
    """A frozen S0 receipt (SHAs, [REDACTED]-free, relative paths) is clean."""
    assert scanner.scan_text(_clean_receipt_text(), "receipt.json") == []


def test_schema_prose_mentioning_secrets_is_not_a_finding():
    """Prose that *mentions* secrets (schema descriptions) is not a leak."""
    text = json.dumps({
        "description": "must not contain secrets or tokens or passwords",
        "properties": {"command": {"description": "redacted display string"}},
    })
    assert scanner.scan_text(text, "schema.json") == []


def test_hex_shas_are_not_findings():
    """40/64-hex digests (git SHAs, argv/report digests) are not secrets."""
    text = json.dumps({
        "git": {"head_sha": "a" * 40, "tree_sha": "d" * 40},
        "command": {"argv_sha256": "c" * 64},
    })
    assert scanner.scan_text(text, "receipt.json") == []


def test_redacted_display_is_not_a_finding():
    """A ``[REDACTED]`` display string is clean."""
    text = json.dumps({"command": {"display": "pytest --token [REDACTED]"}})
    assert scanner.scan_text(text, "receipt.json") == []


def test_relative_paths_are_not_findings():
    """Relative artifact paths are fine."""
    text = json.dumps({"reports": [{"path": "artifacts/junit.xml"}]})
    assert scanner.scan_text(text, "receipt.json") == []


# --- unit: real leaks are flagged --------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"token": "abc123def456"}),
        json.dumps({"api_key": "abc123def456"}),
        json.dumps({"command": {"password": "hunter2"}}),
        json.dumps({"nested": {"client_secret": "shh"}}),
        json.dumps({"access_token": "ya29.abcdef"}),
    ],
)
def test_secret_named_json_key_is_flagged(text):
    findings = scanner.scan_text(text, "receipt.json")
    assert any(f.kind == "secret-key" for f in findings), findings


@pytest.mark.parametrize(
    "value",
    [
        "ghp_" + "A" * 36,
        "gho_" + "B" * 36,
        "github_pat_11ABCDEFG0" + "x" * 20,
        "sk-" + "c" * 48,
        "sk-proj-" + "d" * 20,
        "AKIA" + "E" * 16,
        "xoxb-123456789012-abcdefghij",
        "-----BEGIN RSA PRIVATE KEY-----",
        "Bearer abcdefghij.klmnopqr.stuvwx",
    ],
)
def test_credential_shaped_value_is_flagged(value):
    text = json.dumps({"note": f"leaked {value} here"})
    findings = scanner.scan_text(text, "receipt.json")
    assert any(f.kind == "secret-value" for f in findings), findings


@pytest.mark.parametrize(
    "path_text",
    [
        "/home/alice/.ssh/id_ed25519",
        "/Users/bob/Documents/report.txt",
        "C:\\Users\\carol\\secret.txt",
        "C:/Users/dave/notes.txt",
        "/root/.aws/credentials",
    ],
)
def test_absolute_user_path_is_flagged(path_text):
    text = json.dumps({"note": f"stored at {path_text}"})
    findings = scanner.scan_text(text, "receipt.json")
    assert any(f.kind == "absolute-path" for f in findings), findings


def test_toml_secret_assignment_is_flagged():
    text = "[ci]\ntoken = \"abc123\"\n"
    findings = scanner.scan_text(text, "policy.toml")
    assert any(f.kind == "secret-key" for f in findings), findings


def test_unparsable_json_is_flagged():
    findings = scanner.scan_text("{not json", "receipt.json")
    assert any(f.kind == "unparsable-json" for f in findings), findings


# --- file / directory level --------------------------------------------------


def test_scan_root_clean_tree(tmp_path: Path):
    """A tree of clean receipts scans with zero findings."""
    dest = tmp_path / "evidence" / "unit-linux-py312"
    dest.mkdir(parents=True)
    (dest / "receipt.json").write_text(_clean_receipt_text(), encoding="utf-8")
    findings, skipped, scanned = scanner.scan_root(tmp_path)
    assert findings == []
    assert skipped == []
    assert scanned == 1


def test_scan_root_flags_planted_secret(tmp_path: Path):
    """A planted secret in a receipt is found with its path."""
    dest = tmp_path / "evidence" / "unit-linux-py312"
    dest.mkdir(parents=True)
    (dest / "receipt.json").write_text(
        json.dumps({"token": "T011_PLANTED_SECRET"}), encoding="utf-8"
    )
    findings, _skipped, scanned = scanner.scan_root(tmp_path)
    assert scanned == 1
    assert len(findings) == 1
    assert findings[0].kind == "secret-key"
    assert "receipt.json" in findings[0].path


def test_scan_root_skips_excluded_dirs(tmp_path: Path):
    """Secrets inside .venv / __pycache__ are out of scope (not scanned)."""
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "leak.json").write_text(
        json.dumps({"token": "T011_PLANTED_SECRET"}), encoding="utf-8"
    )
    findings, _skipped, scanned = scanner.scan_root(tmp_path)
    assert findings == []
    assert scanned == 0


def test_scan_root_skips_non_scannable_files(tmp_path: Path):
    """A .py file holding a fake secret literal is not in scope."""
    (tmp_path / "notes.py").write_text('TOKEN = "ghp_" + "A" * 36\n', encoding="utf-8")
    findings, _skipped, scanned = scanner.scan_root(tmp_path)
    assert findings == []
    assert scanned == 0


def test_scan_root_oversize_file_is_skipped_not_flagged(tmp_path: Path):
    """A > 10 MiB file is skipped (never loaded), not flagged."""
    big = tmp_path / "big.json"
    with big.open("wb") as handle:
        handle.write(b'{"note": "')
        handle.write(b"x" * (10 * 1024 * 1024))
        handle.write(b'"}')
    findings, skipped, scanned = scanner.scan_root(tmp_path)
    assert findings == []
    assert scanned == 1
    assert len(skipped) == 1 and "oversize" in skipped[0]


def test_scan_fixtures_tree_is_clean():
    """End to end: the whole frozen S0 fixture tree scans clean."""
    findings, skipped, scanned = scanner.scan_root(FIXTURES)
    assert findings == [], findings
    assert skipped == []
    assert scanned > 50  # 52 fixtures' receipts + policies + GOLDEN


# --- CLI ---------------------------------------------------------------------


def test_cli_clean_tree_exits_zero(tmp_path: Path):
    (tmp_path / "receipt.json").write_text(_clean_receipt_text(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "privacy_scan.py"), str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 finding(s)" in proc.stdout


def test_cli_dirty_tree_exits_one(tmp_path: Path):
    (tmp_path / "receipt.json").write_text(
        json.dumps({"token": "T011_PLANTED_SECRET"}), encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "privacy_scan.py"), str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "LEAK secret-key" in proc.stdout
    assert "1 finding(s)" in proc.stdout


def test_cli_missing_root_exits_two():
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "privacy_scan.py"), "/nonexistent-dir-xyz"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
