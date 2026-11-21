"""S0 gate tests (P027-T004, PROJECT_BOOK §8).

These pytest tests drive the gate pieces: fixture inventory (52),
Golden self-consistency, receipt/policy validity, artifact hash
consistency, and production/Oracle parity (full 52-fixture comparison
against the hand-written Golden). The authoritative gate run is
``scripts/s0_gate.py``; these tests give the same verdicts a fast
pytest form.

Golden expected is hand-written (fixtures/s0/GOLDEN.json) from the
frozen rules — it is never generated from production output.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.schema import validate_against_schema  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "02_source" / "fixtures" / "s0"
ORACLE = ROOT / "02_source" / "oracle" / "verify.mjs"
REASON_CODES_MD = ROOT / "02_source" / "docs" / "REASON_CODES.md"

COMPARE_KEYS = ["status", "jobs_verified", "missing_jobs", "unexpected_jobs",
                "duplicate_jobs", "reason_codes", "identity_mismatches",
                "report_errors", "expected_source_mode"]

# Fixtures whose receipts/artifacts intentionally break the "valid +
# consistent" invariant, and why (see scripts/build_fixtures.py).
INTENTIONALLY_INVALID_RECEIPT = {"h4-missing-command"}
INTENTIONALLY_MISSING_FILE = {"f1-report-file-missing", "f3-lcov-required-missing"}
INTENTIONALLY_HASH_MISMATCH = {"f2-report-hash-mismatch", "f4-report-size-lie"}


def fixture_ids() -> list[str]:
    golden = json.loads((FIXTURES / "GOLDEN.json").read_text())
    return sorted(golden["fixtures"])


def load_fixture(fid: str):
    fdir = FIXTURES / fid
    policy = load_policy(fdir / "policy.toml")
    expected_sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]
    return fdir, policy, expected_sha


def run_oracle(fdir: Path, expected_sha: str) -> dict:
    proc = subprocess.run(
        ["node", str(ORACLE), "--policy", str(fdir / "policy.toml"),
         "--expected-source-sha", expected_sha,
         "--evidence", str(fdir / "evidence")],
        capture_output=True, text=True, timeout=120)
    assert proc.stdout.strip(), f"oracle no output for {fdir}: {proc.stderr}"
    return json.loads(proc.stdout)


def test_inventory_is_52():
    ids = fixture_ids()
    assert len(ids) == 52
    controls = [i for i in ids if i.startswith("n")]
    faults = [i for i in ids if not i.startswith("n")]
    assert len(controls) == 16
    assert len(faults) == 36
    on_disk = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    assert on_disk == ids
    for fid in ids:
        fdir = FIXTURES / fid
        assert (fdir / "policy.toml").is_file()
        assert (fdir / "expected.json").is_file()
        assert (fdir / "evidence").is_dir()
        assert list((fdir / "evidence").iterdir()), f"{fid}: empty evidence/"


def test_golden_self_consistency():
    golden = json.loads((FIXTURES / "GOLDEN.json").read_text())["fixtures"]
    reason_text = REASON_CODES_MD.read_text()
    for fid, g in golden.items():
        assert g["status"] in ("BOUND_PASS", "BOUND_FAIL", "UNBOUND", "INVALID")
        for code in g["reason_codes"]:
            assert f"`{code}`" in reason_text, f"{fid}: code {code} not frozen in REASON_CODES.md"
        if fid.startswith("n"):
            assert g["status"] == "BOUND_PASS", f"control {fid} must be BOUND_PASS"
            assert g["reason_codes"] == []
            assert g["missing_jobs"] == [] and g["unexpected_jobs"] == [] and g["duplicate_jobs"] == []
        else:
            assert g["status"] != "BOUND_PASS", f"fault {fid} must not PASS"
            assert g["reason_codes"], f"fault {fid} needs a reason code"
    assert len([f for f in golden if f.startswith("n")]) == 16


def test_policies_and_expected_sha_valid():
    for fid in fixture_ids():
        fdir, policy, expected_sha = load_fixture(fid)
        assert len(expected_sha) == 40
        assert all(c in "0123456789abcdef" for c in expected_sha)
        assert policy["source_mode"] in ("pr_head", "merge_commit", "event_sha", "explicit_sha")


def test_receipts_validate_against_run_schema():
    for fid in fixture_ids():
        fdir = FIXTURES / fid
        for receipt_path in sorted((fdir / "evidence").rglob("receipt.json")):
            data = json.loads(receipt_path.read_text())
            if fid in INTENTIONALLY_INVALID_RECEIPT:
                with pytest.raises(Exception):
                    validate_against_schema(data, "run")
            else:
                validate_against_schema(data, "run")


def test_artifact_hashes_match_receipts_except_planted():
    for fid in fixture_ids():
        fdir = FIXTURES / fid
        for receipt_path in sorted((fdir / "evidence").rglob("receipt.json")):
            data = json.loads(receipt_path.read_text())
            job_dir = receipt_path.parent
            for rep in data.get("reports", []):
                target = job_dir / rep["path"]
                if fid in INTENTIONALLY_MISSING_FILE and not target.exists():
                    continue
                assert target.is_file(), f"{fid}: {rep['path']} missing"
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                size = target.stat().st_size
                if fid in INTENTIONALLY_HASH_MISMATCH:
                    assert digest != rep["sha256"] or size != rep["size_bytes"], (
                        f"{fid}: planted hash/size mismatch did not materialise")
                else:
                    assert digest == rep["sha256"], f"{fid}: hash mismatch for {rep['path']}"
                    assert size == rep["size_bytes"], f"{fid}: size mismatch for {rep['path']}"


def test_no_absolute_paths_or_forbidden_keys_in_receipts():
    for receipt_path in FIXTURES.rglob("receipt.json"):
        text = receipt_path.read_text()
        data = json.loads(text)
        assert "stdout" not in data and "stderr" not in data and "environment" not in data
        for pattern in ("/home/", "/Users/", "C:\\", "C:/", "/tmp/"):
            assert pattern not in text, f"{receipt_path}: absolute path pattern {pattern!r}"


@pytest.mark.parametrize("fid", fixture_ids())
def test_python_matches_golden(fid):
    golden = json.loads((FIXTURES / "GOLDEN.json").read_text())["fixtures"][fid]
    fdir, policy, expected_sha = load_fixture(fid)
    result = evaluate(policy, expected_sha, fdir / "evidence")
    slim = {k: result.get(k) for k in COMPARE_KEYS}
    assert slim == golden, f"{fid}: python != golden: {slim} vs {golden}"


@pytest.mark.parametrize("fid", fixture_ids())
def test_oracle_matches_golden_and_python(fid):
    golden = json.loads((FIXTURES / "GOLDEN.json").read_text())["fixtures"][fid]
    fdir, policy, expected_sha = load_fixture(fid)
    oracle_result = run_oracle(fdir, expected_sha)
    slim_ora = {k: oracle_result.get(k) for k in COMPARE_KEYS}
    assert slim_ora == golden, f"{fid}: oracle != golden: {slim_ora} vs {golden}"
    py_result = evaluate(policy, expected_sha, fdir / "evidence")
    slim_py = {k: py_result.get(k) for k in COMPARE_KEYS}
    assert slim_ora == slim_py, f"{fid}: oracle != python"
