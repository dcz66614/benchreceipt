"""Probe (a) — path traversal / absolute / Windows paths / symlink escape.

Targets: ``verify.evaluate`` (receipt ``reports[].path``) and
``bundle.build_bundle`` / ``bundle.verify_bundle`` (manifest entries
and on-disk files). Every hostile path must fail closed — never
``BOUND_PASS`` / never ``ok=True`` — and a symlink must never be
followed out of the evidence/bundle root, even when the file it points
at has exactly the digest the receipt claims.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from _evidence import (
    EXPECTED_SHA,
    POLICY,
    assert_not_pass,
    evaluate_evidence,
    junit_bytes,
    load_n06_receipt,
    make_evidence,
)
from benchreceipt.bundle import (
    BundleError,
    build_bundle,
    verify_bundle,
)

# --- verify.evaluate: hostile reports[].path values -----------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "../escape.xml",                    # parent traversal
        "artifacts/../../escape.xml",       # traversal hidden mid-path
        "/etc/passwd",                      # absolute POSIX
        "/tmp/evil/junit.xml",              # absolute POSIX (tmp)
        "artifacts\\junit.xml",             # backslash separator
        "..\\escape.xml",                   # Windows-style traversal
        "C:/evil/junit.xml",                # Windows drive path
        "C:\\evil\\junit.xml",              # Windows drive + backslashes
        "artifacts//junit.xml",             # empty segment
        "artifacts/junit.xml/",             # trailing slash
    ],
)
def test_verify_rejects_hostile_report_path(tmp_path: Path, hostile: str):
    """A receipt whose report path escapes the job dir never verifies.

    The frozen run.v1 schema rejects all of these at load
    (``INVALID_RECEIPT``); the verifier never opens the path.
    """
    def mutate(receipt, _evidence):
        receipt["reports"][0]["path"] = hostile

    verdict = evaluate_evidence(make_evidence(tmp_path, mutate))
    assert verdict["status"] == "INVALID", verdict
    assert "INVALID_RECEIPT" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_verify_symlink_to_identical_outside_file_is_rejected(tmp_path: Path):
    """A symlink is rejected on containment, not just on hash.

    The outside file holds byte-identical content (so its digest
    matches the receipt exactly); the only reason to reject it is that
    the resolved path escapes the job dir. If the verifier merely
    re-hashed the target, this would pass — it must not.
    """
    outside = tmp_path / "outside.xml"
    outside.write_bytes(junit_bytes())
    evidence = make_evidence(tmp_path)
    artifact = evidence / "unit-linux-py312" / "artifacts" / "junit.xml"
    artifact.unlink()
    artifact.symlink_to(outside)
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "INVALID", verdict
    assert "REPORT_HASH_MISMATCH" in verdict["reason_codes"], verdict
    assert any(
        e.get("code") == "REPORT_HASH_MISMATCH"
        and "digest mismatch" in e.get("message", "")
        for e in verdict["report_errors"]
    ), verdict
    assert_not_pass(verdict)


def test_verify_symlink_to_attacker_file_with_matching_receipt_hash(tmp_path: Path):
    """Stronger variant: the attacker also controls the receipt digest.

    The receipt's recorded sha/size are rewritten to the attacker's
    outside file, so a hash-only check would pass. Containment must
    still reject it.
    """
    attacker = tmp_path / "attacker.xml"
    attacker.write_bytes(b"<forged/>")
    digest = hashlib.sha256(b"<forged/>").hexdigest()

    def mutate(receipt, _evidence):
        receipt["reports"][0]["sha256"] = digest
        receipt["reports"][0]["size_bytes"] = len(b"<forged/>")

    evidence = make_evidence(tmp_path, mutate)
    artifact = evidence / "unit-linux-py312" / "artifacts" / "junit.xml"
    artifact.unlink()
    artifact.symlink_to(attacker)
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "INVALID", verdict
    assert "REPORT_HASH_MISMATCH" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_verify_missing_report_file_is_not_a_pass(tmp_path: Path):
    """Control-adjacent: a deleted artifact fails closed (REPORT_MISSING)."""
    evidence = make_evidence(tmp_path)
    (evidence / "unit-linux-py312" / "artifacts" / "junit.xml").unlink()
    verdict = evaluate_evidence(evidence)
    assert verdict["status"] == "UNBOUND", verdict
    assert "REPORT_MISSING" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)


def test_verify_untouched_fixture_passes(tmp_path: Path):
    """Control: the unmodified n06 evidence verifies BOUND_PASS."""
    verdict = evaluate_evidence(make_evidence(tmp_path))
    assert verdict["status"] == "BOUND_PASS", verdict
    assert verdict["jobs_verified"] == 1, verdict


# --- bundle: symlinks and manifest path escapes ---------------------------


def _build_bundle(tmp_path: Path) -> Path:
    evidence = make_evidence(tmp_path)
    out = tmp_path / "bundle"
    build_bundle(evidence, out)
    return out


def test_bundle_build_refuses_symlink_in_source_tree(tmp_path: Path):
    """build_bundle refuses a symlinked artifact (never follows it)."""
    evidence = make_evidence(tmp_path)
    artifact = evidence / "unit-linux-py312" / "artifacts" / "junit.xml"
    target = tmp_path / "real.xml"
    target.write_bytes(junit_bytes())
    artifact.unlink()
    artifact.symlink_to(target)
    with pytest.raises(BundleError, match="symlink"):
        build_bundle(evidence, tmp_path / "bundle")


def test_bundle_build_refuses_symlinked_directory(tmp_path: Path):
    """build_bundle refuses a symlinked job directory too."""
    evidence = make_evidence(tmp_path)
    job_dir = evidence / "unit-linux-py312"
    real = tmp_path / "real-job"
    shutil.copytree(job_dir, real)
    shutil.rmtree(job_dir)
    job_dir.symlink_to(real, target_is_directory=True)
    with pytest.raises(BundleError, match="symlink"):
        build_bundle(evidence, tmp_path / "bundle")


def test_bundle_verify_rejects_symlink_planted_after_build(tmp_path: Path):
    """A symlink planted in a bundle after build is never followed."""
    bundle = _build_bundle(tmp_path)
    artifact = bundle / "unit-linux-py312" / "artifacts" / "junit.xml"
    outside = tmp_path / "outside.xml"
    outside.write_bytes(junit_bytes())
    artifact.unlink()
    artifact.symlink_to(outside)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert any(
        p["code"] == "BUNDLE_UNSUPPORTED_SYMLINK" for p in result.problems
    ), result.problems


def test_bundle_verify_rejects_symlinked_directory_planted_after_build(tmp_path: Path):
    """A symlinked directory planted in a bundle is rejected."""
    bundle = _build_bundle(tmp_path)
    job_dir = bundle / "unit-linux-py312"
    real = tmp_path / "real-job"
    shutil.copytree(job_dir, real)
    shutil.rmtree(job_dir)
    job_dir.symlink_to(real, target_is_directory=True)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert any(
        p["code"] == "BUNDLE_UNSUPPORTED_SYMLINK" for p in result.problems
    ), result.problems


def _rewrite_manifest(bundle: Path, lines: list[str]) -> None:
    (bundle / "SHA256SUMS.txt").write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8"
    )


def _manifest_lines(bundle: Path) -> list[str]:
    return (bundle / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()


def _manifest_line_for(bundle: Path, rel: str) -> str:
    for line in _manifest_lines(bundle):
        if line.endswith(" " + rel):
            return line
    raise AssertionError(f"no manifest line for {rel!r}")


@pytest.mark.parametrize(
    "hostile",
    [
        "../escape.txt",
        "../../etc/passwd",
        "/etc/passwd",
        "/tmp/evil.txt",
        "C:/evil.txt",
        "C:\\evil.txt",
        "unit-linux-py312\\artifacts\\junit.xml",
    ],
)
def test_bundle_manifest_path_escape_rejected(tmp_path: Path, hostile: str):
    """A manifest entry naming a path outside the bundle fails closed."""
    bundle = _build_bundle(tmp_path)
    lines = _manifest_lines(bundle)
    digest, size, _rel = lines[0].split(" ", 2)
    lines[0] = f"{digest} {size} {hostile}"
    _rewrite_manifest(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert any(
        p["code"] == "BUNDLE_PATH_ESCAPE" for p in result.problems
    ), result.problems


def test_bundle_receipt_report_path_escape_rejected(tmp_path: Path):
    """A receipt inside the bundle pointing at ``../`` fails closed.

    The receipt is edited AND the manifest is re-hashed for it, so the
    only finding is the receipt's own escaping report path (the bundle
    manifest itself stays consistent).
    """
    bundle = _build_bundle(tmp_path)
    receipt_path = bundle / "unit-linux-py312" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["reports"][0]["path"] = "../outside.xml"
    raw = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    receipt_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    lines = [
        f"{digest} {len(raw)} unit-linux-py312/receipt.json"
        if line.endswith(" unit-linux-py312/receipt.json") else line
        for line in _manifest_lines(bundle)
    ]
    _rewrite_manifest(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert any(
        p["code"] == "REPORT_HASH_MISMATCH" for p in result.problems
    ), result.problems


def test_bundle_verify_untouched_bundle_passes(tmp_path: Path):
    """Control: an unmodified bundle verifies ok."""
    result = verify_bundle(_build_bundle(tmp_path))
    assert result.ok is True, result.problems
    assert result.problems == []
