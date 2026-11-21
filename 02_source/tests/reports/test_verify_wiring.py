"""Verify-wiring tests (P027-T005).

The full parsers in ``benchreceipt.reports`` are wired into
``benchreceipt.verify.evaluate``: a JUnit file whose ``tests``
attribute disagrees with its counted testcases must surface as
``JUNIT_MALFORMED`` / ``INVALID`` (not as a silently trusted summary),
and a malformed LCOV file must surface as ``LCOV_MALFORMED`` /
``INVALID``. Each case starts from a frozen S0 fixture copied into a
scratch directory, so the harness (policy, expected SHA, receipt
shape) is the real one and only the report bytes change.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from benchreceipt.policy import load_policy
from benchreceipt.verify import evaluate

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "s0"


def _load_fixture(fid: str):
    fdir = FIXTURES / fid
    policy = load_policy(fdir / "policy.toml")
    expected_sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]
    return fdir, policy, expected_sha


def _refresh_report_entry(receipt_path: Path, kind: str, data: bytes) -> None:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for entry in receipt["reports"]:
        if entry["kind"] == kind:
            entry["size_bytes"] = len(data)
            entry["sha256"] = hashlib.sha256(data).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


def test_unmodified_fixture_copy_still_passes(tmp_path: Path):
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    evidence = tmp_path / "evidence"
    shutil.copytree(fdir / "evidence", evidence)
    result = evaluate(policy, expected_sha, evidence)
    assert result["status"] == "BOUND_PASS"
    assert result["reason_codes"] == []


def test_junit_attribute_mismatch_is_invalid_via_verify(tmp_path: Path):
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    evidence = tmp_path / "evidence"
    shutil.copytree(fdir / "evidence", evidence)
    junit_path = evidence / "unit-linux-py312" / "artifacts" / "junit.xml"
    # tests="5" but only 3 <testcase> elements: the full parser must
    # reject this instead of trusting the attribute (or the receipt).
    doctored = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<testsuite name="suite" tests="5" failures="0" errors="0" skipped="0">'
        b'<testcase classname="t" name="a"></testcase>'
        b'<testcase classname="t" name="b"></testcase>'
        b'<testcase classname="t" name="c"></testcase></testsuite>'
    )
    junit_path.write_bytes(doctored)
    _refresh_report_entry(
        evidence / "unit-linux-py312" / "receipt.json", "junit", doctored
    )
    result = evaluate(policy, expected_sha, evidence)
    assert result["status"] == "INVALID"
    assert "JUNIT_MALFORMED" in result["reason_codes"]
    assert result["jobs_verified"] == 0


def test_malformed_lcov_is_invalid_via_verify(tmp_path: Path):
    fdir, policy, expected_sha = _load_fixture("n13-junit-plus-lcov")
    evidence = tmp_path / "evidence"
    shutil.copytree(fdir / "evidence", evidence)
    lcov_path = evidence / "unit-linux-py312" / "artifacts" / "lcov.info"
    # Absolute SF path: the LCOV parser must reject it, and the
    # verifier must surface that as INVALID, not PASS.
    doctored = b"SF:/etc/passwd\nDA:1,1\nend_of_record\n"
    lcov_path.write_bytes(doctored)
    _refresh_report_entry(
        evidence / "unit-linux-py312" / "receipt.json", "lcov", doctored
    )
    result = evaluate(policy, expected_sha, evidence)
    assert result["status"] == "INVALID"
    assert "LCOV_MALFORMED" in result["reason_codes"]
    # The untouched Windows job still verifies.
    assert result["jobs_verified"] == 1
