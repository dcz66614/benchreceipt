"""Legacy-shape fixtures e7/e8 (spec v1.2.0, ADR-007 / P0-R1-01).

R1 proved the old verifier returned BOUND_PASS for a clean receipt
with BOTH after fields deleted (e5/e6 minus
``git.head_sha_after`` / ``git.tree_sha_after``). Scheme A keeps the
two fields optional in the schema (old receipts still parse) but
fails closed at verify time: no after identity means no proof the
run's HEAD/tree did not change, so the verdict is UNBOUND with
``MISSING_FIELD`` (reused frozen code, UNBOUND class), ``jobs_verified``
0, CLI exit 2 — in BOTH implementations, with the byte-identical
message template frozen in ``docs/REASON_CODES.md``.

e7 (legacy clean checkout) and e8 (legacy empty commit) are the two
R1 scenarios as fixtures. Their receipts are byte-identical by
design — without after fields the two scenarios cannot be told
apart — and Golden holds the hand-written expected result for each.

Coverage per fixture: source API (:func:`benchreceipt.verify.evaluate`),
schema validation (fields stay optional), Node Oracle parity
(``oracle/verify.mjs`` CLI, same result + exit code), and the
production CLI exit code (2, never 0).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchreceipt.policy import load_policy
from benchreceipt.schema import validate_against_schema
from benchreceipt.verify import evaluate, status_to_exit_code

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "s0"
ORACLE = ROOT / "oracle" / "verify.mjs"

LEGACY = ["e7-legacy-clean-checkout", "e8-legacy-empty-commit"]
EXPECTED_MESSAGE = "missing git.head_sha_after and git.tree_sha_after"
EXPECTED_REASON_CODES = ["MISSING_FIELD"]
COMPARE_KEYS = ["status", "jobs_verified", "missing_jobs", "unexpected_jobs",
                "duplicate_jobs", "reason_codes", "identity_mismatches",
                "report_errors", "expected_source_mode"]


def _load(fid: str):
    fdir = FIXTURES / fid
    policy = load_policy(fdir / "policy.toml")
    expected_sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]
    return fdir, policy, expected_sha


def _golden(fid: str) -> dict:
    return json.loads((FIXTURES / "GOLDEN.json").read_text())["fixtures"][fid]


def _receipt(fid: str) -> dict:
    return json.loads(
        (FIXTURES / fid / "evidence" / "unit-linux-py312" / "receipt.json")
        .read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("fid", LEGACY)
def test_legacy_fixture_has_no_after_fields(fid: str):
    """The fixture really is the legacy shape: neither after field."""
    receipt = _receipt(fid)
    assert "head_sha_after" not in receipt["git"]
    assert "tree_sha_after" not in receipt["git"]
    assert receipt["git"]["head_sha"] == "a" * 40
    assert receipt["git"]["tree_sha"] == "d" * 40
    assert receipt["git"]["dirty_before"] is False
    assert receipt["git"]["dirty_after"] is False


@pytest.mark.parametrize("fid", LEGACY)
def test_legacy_fixture_schema_still_valid(fid: str):
    """Both after fields stay OPTIONAL: the legacy receipt parses."""
    validate_against_schema(_receipt(fid), "run")


@pytest.mark.parametrize("fid", LEGACY)
def test_legacy_fixture_fails_closed_via_api(fid: str):
    """Source API: UNBOUND + MISSING_FIELD, jobs_verified 0."""
    fdir, policy, expected_sha = _load(fid)
    result = evaluate(policy, expected_sha, fdir / "evidence")
    assert result["status"] == "UNBOUND", result
    assert result["reason_codes"] == EXPECTED_REASON_CODES, result
    assert result["report_errors"] == [
        {"code": "MISSING_FIELD", "message": EXPECTED_MESSAGE,
         "job_id": "unit-linux-py312"}
    ], result
    assert result["jobs_verified"] == 0, result
    assert status_to_exit_code(result["status"]) == 2
    slim = {k: result.get(k) for k in COMPARE_KEYS}
    assert slim == _golden(fid), f"{fid}: python != golden"


@pytest.mark.parametrize("fid", LEGACY)
def test_legacy_fixture_oracle_parity(fid: str):
    """Node Oracle: identical verdict, identical message, exit 2."""
    fdir, policy, expected_sha = _load(fid)
    proc = subprocess.run(
        ["node", str(ORACLE), "--policy", str(fdir / "policy.toml"),
         "--expected-source-sha", expected_sha,
         "--evidence", str(fdir / "evidence")],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    oracle_result = json.loads(proc.stdout)
    slim = {k: oracle_result.get(k) for k in COMPARE_KEYS}
    assert slim == _golden(fid), f"{fid}: oracle != golden"
    py_result = evaluate(policy, expected_sha, fdir / "evidence")
    py_slim = {k: py_result.get(k) for k in COMPARE_KEYS}
    assert slim == py_slim, f"{fid}: oracle != python"


@pytest.mark.parametrize("fid", LEGACY)
def test_legacy_fixture_cli_exit_code_is_2(fid: str, tmp_path: Path):
    """Production CLI: exit 2 with UNBOUND + MISSING_FIELD in --out."""
    fdir, policy, expected_sha = _load(fid)
    out = tmp_path / "result.json"
    proc = subprocess.run(
        [sys.executable, "-m", "benchreceipt", "verify",
         "--policy", str(fdir / "policy.toml"),
         "--evidence", str(fdir / "evidence"),
         "--expected-source-sha", expected_sha,
         "--out", str(out)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "UNBOUND", result
    assert result["reason_codes"] == EXPECTED_REASON_CODES, result
    assert result["jobs_verified"] == 0, result


def test_e7_and_e8_receipts_are_byte_identical_by_design():
    """Without after fields the two legacy scenarios are
    indistinguishable — that indistinguishability is the point:
    neither receipt can prove what happened mid-run, so both fail
    closed with the same verdict."""
    assert _receipt("e7-legacy-clean-checkout") == _receipt("e8-legacy-empty-commit")
