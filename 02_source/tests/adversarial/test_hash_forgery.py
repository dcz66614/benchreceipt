"""Probe (f) — hash forgery variants.

The verifier recomputes size + SHA-256 from the artifact bytes at
verify time and compares BOTH against the receipt. Forging either
side — a matching size with a different hash, or a matching hash
with a different size — must yield REPORT_HASH_MISMATCH (INVALID),
never a pass.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from _evidence import (
    assert_not_pass,
    evaluate_evidence,
    junit_bytes,
    make_evidence,
)
from benchreceipt.bundle import build_bundle, verify_bundle


def test_size_matches_hash_differs_is_rejected(tmp_path: Path):
    """Same byte count, different content: digest mismatch."""
    forged = junit_bytes().replace(b'test_0', b'test_X', 1)
    assert len(forged) == len(junit_bytes())  # size identical, hash differs

    def mutate(receipt, evidence):
        (evidence / "unit-linux-py312" / "artifacts" / "junit.xml").write_bytes(forged)

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "REPORT_HASH_MISMATCH" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_hash_matches_size_differs_is_rejected(tmp_path: Path):
    """Recorded hash is right, recorded size is wrong: still mismatch."""
    def mutate(receipt, _evidence):
        receipt["reports"][0]["size_bytes"] += 1  # hash untouched

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "REPORT_HASH_MISMATCH" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_hash_of_other_content_is_rejected(tmp_path: Path):
    """Receipt carries the digest of a different file (same size)."""
    other = b"X" * len(junit_bytes())
    assert hashlib.sha256(other).hexdigest() != hashlib.sha256(junit_bytes()).hexdigest()

    def mutate(receipt, _evidence):
        receipt["reports"][0]["sha256"] = hashlib.sha256(other).hexdigest()

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "REPORT_HASH_MISMATCH" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_empty_file_digest_claimed_for_real_report(tmp_path: Path):
    """The empty-string SHA-256 claimed for a real report is rejected."""
    def mutate(receipt, _evidence):
        receipt["reports"][0]["sha256"] = hashlib.sha256(b"").hexdigest()
        receipt["reports"][0]["size_bytes"] = 0

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "REPORT_HASH_MISMATCH" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_swapped_report_hashes_are_rejected(tmp_path: Path):
    """Two-job bundle: each receipt claims the other's report digest."""
    evidence = make_evidence(tmp_path)
    job2 = evidence / "unit-windows-py312"
    shutil.copytree(evidence / "unit-linux-py312", job2)
    import json

    receipt2_path = job2 / "receipt.json"
    receipt2 = json.loads(receipt2_path.read_text(encoding="utf-8"))
    receipt2["job_id"] = "unit-windows-py312"
    receipt2["matrix"] = {"os": "windows-latest", "python": "3.12"}
    # Tamper job2's artifact, then give job2 job1's (now stale) digest
    # and job1 job2's digest: both digests are "real" digests of some
    # file, just bound to the wrong job.
    artifact2 = job2 / "artifacts" / "junit.xml"
    forged = junit_bytes().replace(b'test_9', b'test_Y', 1)
    artifact2.write_bytes(forged)
    receipt1_path = evidence / "unit-linux-py312" / "receipt.json"
    receipt1 = json.loads(receipt1_path.read_text(encoding="utf-8"))
    receipt1["reports"][0]["sha256"] = hashlib.sha256(forged).hexdigest()
    receipt2["reports"][0]["sha256"] = hashlib.sha256(junit_bytes()).hexdigest()
    receipt1_path.write_text(json.dumps(receipt1, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt2_path.write_text(json.dumps(receipt2, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    policy = {
        "schema_version": 1,
        "source_mode": "event_sha",
        "expected_workflow": "CI",
        "required_jobs": ["unit-linux-py312", "unit-windows-py312"],
        "min_tests": 1,
        "require_clean_source_after": True,
        "same_tree_across_jobs": True,
        "same_run_id": True,
        "same_run_attempt": True,
        "reports": {"junit": "required", "lcov": "optional"},
    }
    from benchreceipt.verify import evaluate
    from _evidence import EXPECTED_SHA

    verdict = evaluate(policy, EXPECTED_SHA, evidence)
    assert verdict["status"] == "INVALID", verdict
    assert "REPORT_HASH_MISMATCH" in verdict["reason_codes"], verdict
    assert verdict["jobs_verified"] == 0, verdict


def test_bundle_tampered_artifact_is_rejected(tmp_path: Path):
    """Bundle level: one flipped byte after bundling is detected."""
    evidence = make_evidence(tmp_path)
    bundle = tmp_path / "bundle"
    build_bundle(evidence, bundle)
    artifact = bundle / "unit-linux-py312" / "artifacts" / "junit.xml"
    data = bytearray(artifact.read_bytes())
    data[100] ^= 0xFF
    artifact.write_bytes(bytes(data))
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert any(
        p["code"] == "BUNDLE_HASH_MISMATCH" for p in result.problems
    ), result.problems
    assert any(
        p["code"] == "REPORT_HASH_MISMATCH" for p in result.problems
    ), result.problems


def test_untouched_evidence_passes(tmp_path: Path):
    """Control: the unmodified fixture verifies BOUND_PASS."""
    verdict = evaluate_evidence(make_evidence(tmp_path))
    assert verdict["status"] == "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 1, verdict
