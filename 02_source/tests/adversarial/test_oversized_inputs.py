"""Probe (b) — oversized inputs.

Frozen schema caps (run.v1.json, ADR-001 decision 5): reports array
<= 32 items, job_id <= 128 chars, matrix <= 32 entries / keys <= 64
chars, report size_bytes <= 1 GiB, command.display <= 512 chars.
Anything past a cap must be INVALID_RECEIPT at load, never verified.
Report parsers enforce the 1 GiB cap by ``stat`` before reading, so
an over-limit file is rejected without being loaded into memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from _evidence import (
    JUNIT_XML,
    POLICY,
    assert_not_pass,
    evaluate_evidence,
    load_n06_receipt,
    make_evidence,
)
from benchreceipt.capture import CaptureError, _validate_job_id, _validate_matrix
from benchreceipt.reports.junit import JUnitError, parse_junit
from benchreceipt.reports.lcov import LcovError, parse_lcov

MAX_REPORT_BYTES = 1073741824  # 1 GiB, frozen schema limit.


def _report_entry(**overrides):
    entry = {
        "kind": "junit",
        "path": "artifacts/junit.xml",
        "size_bytes": 613,
        "sha256": "c85ce097db9bfc8195ca39a082b0bec31d859bc9bfc40a900433f29bccd5628c",
    }
    entry.update(overrides)
    return entry


def test_reports_array_over_32_is_invalid(tmp_path: Path):
    """33 report entries exceed the schema maxItems (32)."""
    def mutate(receipt, _evidence):
        receipt["reports"] = [_report_entry() for _ in range(33)]

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_reports_array_at_32_boundary(tmp_path: Path):
    """32 entries are schema-valid (the cap itself is not the defect).

    The 32 copies all name the same artifact, so verification still
    fails — but on the report check (duplicate kind handling), not on
    the schema. The point is the boundary is accepted, not crashed on.
    """
    def mutate(receipt, _evidence):
        receipt["reports"] = [_report_entry() for _ in range(32)]

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    # No INVALID_RECEIPT: the receipt is schema-valid at the boundary.
    assert "INVALID_RECEIPT" not in verdict["reason_codes"], verdict


def test_job_id_over_128_chars_is_invalid(tmp_path: Path):
    """A 129-char job_id exceeds the schema maxLength (128)."""
    def mutate(receipt, _evidence):
        receipt["job_id"] = "u" * 129

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_matrix_over_32_entries_is_invalid(tmp_path: Path):
    """33 matrix entries exceed the schema maxProperties (32)."""
    def mutate(receipt, _evidence):
        receipt["matrix"] = {f"k{i:02d}": "v" for i in range(33)}

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_matrix_key_over_64_chars_is_invalid(tmp_path: Path):
    """A 65-char matrix key exceeds the schema key maxLength (64)."""
    def mutate(receipt, _evidence):
        receipt["matrix"] = {"k" * 65: "v"}

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_report_size_bytes_over_1gib_is_invalid(tmp_path: Path):
    """size_bytes 1 GiB + 1 exceeds the schema maximum."""
    def mutate(receipt, _evidence):
        receipt["reports"][0]["size_bytes"] = MAX_REPORT_BYTES + 1

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_command_display_over_512_chars_is_invalid(tmp_path: Path):
    """A 513-char display string exceeds the schema maxLength (512)."""
    def mutate(receipt, _evidence):
        receipt["command"]["display"] = "x" * 513

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_capture_rejects_oversized_job_id_and_matrix():
    """Capture fails closed before any repo access on oversized ids."""
    with pytest.raises(CaptureError):
        _validate_job_id("u" * 129)
    with pytest.raises(CaptureError):
        _validate_matrix({f"k{i:02d}": "v" for i in range(33)})


def test_junit_over_1gib_rejected_without_reading(tmp_path: Path):
    """A sparse 1 GiB + 1 file is rejected by stat, never loaded.

    ``os.truncate`` makes the file sparse (no disk use); the parser's
    size check fires before any byte is read.
    """
    target = tmp_path / "huge.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    os.truncate(target, MAX_REPORT_BYTES + 1)
    assert target.stat().st_size == MAX_REPORT_BYTES + 1
    with pytest.raises(JUnitError, match="exceeds size limit"):
        parse_junit(target)


def test_lcov_over_1gib_rejected_without_reading(tmp_path: Path):
    """Same stat-first rejection for LCOV."""
    target = tmp_path / "huge.info"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    os.truncate(target, MAX_REPORT_BYTES + 1)
    with pytest.raises(LcovError, match="exceeds size limit"):
        parse_lcov(target)


def test_large_but_valid_junit_still_verifies(tmp_path: Path):
    """A ~1 MB JUnit with 30,000 testcases verifies normally.

    Guards against an accidental small limit: large-but-legal reports
    must still reach BOUND_PASS.
    """
    cases = "".join(
        f'<testcase classname="s" name="t{i}"/>' for i in range(30000)
    )
    xml = (
        '<?xml version="1.0"?>\n'
        '<testsuites><testsuite name="s" tests="30000" failures="0"'
        f' errors="0" skipped="0">{cases}</testsuite></testsuites>\n'
    ).encode("utf-8")
    assert len(xml) > 1024 * 1024  # genuinely large

    def mutate(receipt, evidence):
        artifact = evidence / "unit-linux-py312" / "artifacts" / "junit.xml"
        artifact.write_bytes(xml)
        receipt["reports"][0]["size_bytes"] = len(xml)
        receipt["reports"][0]["sha256"] = hashlib.sha256(xml).hexdigest()
        receipt["junit"] = {"tests": 30000, "failures": 0, "errors": 0, "skipped": 0}

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 1, verdict


def test_bulk_unexpected_job_dirs_do_not_crash(tmp_path: Path):
    """64 extra job dirs are handled as unexpected jobs, not a crash."""
    evidence = make_evidence(tmp_path)
    src = evidence / "unit-linux-py312"
    for i in range(64):
        dest = evidence / f"extra-job-{i:03d}"
        shutil.copytree(src, dest)
        receipt_path = dest / "receipt.json"
        receipt = load_n06_receipt()
        receipt["job_id"] = f"extra-job-{i:03d}"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "MATRIX_UNEXPECTED_JOB" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 1, verdict  # required job still verifies
    assert len(verdict["unexpected_jobs"]) == 64, verdict


def test_whitespace_padded_receipt_verdict_is_unchanged(tmp_path: Path):
    """A 2 MB whitespace-padded receipt yields the same verdict.

    Schema-valid receipt content is bounded by the schema (every field
    has a max length / max items), but ``receipt.json`` itself has no
    byte cap: leading/trailing JSON whitespace is accepted and the
    verdict is still the correct BOUND_PASS. Recorded as P2-02 in
    SECURITY_FINDINGS.md (robustness observation, not a false PASS):
    a hostile multi-MB receipt is parsed in full before any verdict.
    """
    evidence = make_evidence(tmp_path)
    receipt_path = evidence / "unit-linux-py312" / "receipt.json"
    raw = receipt_path.read_bytes()
    padded = b" " * (2 * 1024 * 1024) + raw + b"\n" * 1024
    receipt_path.write_bytes(padded)
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 1, verdict
