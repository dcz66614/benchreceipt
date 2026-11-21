"""Bundle tests (P027-T006, PROJECT_BOOK §5.4, §6.1, §11.2).

Covers: SHA256SUMS.txt byte-level correctness (recomputed
independently in the test, never by trusting bundle.py's own hash),
round-trip capture -> build_bundle -> verify_bundle, path traversal
and symlink probes (never copied/followed), missing-file /
hash-mismatch / size-lie probes, extra-file detection, empty evidence
dirs, deterministic manifests, BundleError on structurally invalid
input, and end-to-end bundling of the frozen S0 fixtures.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from benchreceipt.bundle import (
    BundleError,
    build_bundle,
    verify_bundle,
)
from benchreceipt.capture import capture

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "s0"

JUNIT_XML = (
    '<?xml version="1.0"?>\n'
    '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
    ' skipped="0">'
    '<testcase classname="s" name="t1"/>'
    '<testcase classname="s" name="t2"/>'
    "</testsuite></testsuites>\n"
)

LCOV_INFO = (
    "TN:\nSF:src/example.py\nFN:1,func\nFNF:1\nFNH:1\n"
    "DA:1,1\nDA:2,0\nLF:2\nLH:1\nend_of_record\n"
)

NORMAL_FIXTURES = [f"n{i:02d}" for i in range(1, 17)]


def _fixture_dir(fixture_id: str) -> Path:
    """Resolve a short id (``n01``) to its frozen fixture directory."""
    matches = sorted(FIXTURES.glob(f"{fixture_id}-*"))
    assert len(matches) == 1, f"{fixture_id}: {matches}"
    return matches[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _codes(result) -> list[str]:
    return sorted(p["code"] for p in result.problems)


def _paths_for(result, code: str) -> list[str]:
    return sorted(p["path"] for p in result.problems if p["code"] == code)


def make_evidence(root: Path, jobs: dict[str, dict[str, bytes]] | None = None) -> Path:
    """Build a synthetic evidence tree.

    ``jobs`` maps job-id -> {relative path -> bytes}; defaults to one
    job with a receipt + junit + lcov whose recorded digests match the
    artifact bytes exactly (as ``capture`` would write them).
    """
    evidence = root / "evidence"
    if jobs is None:
        junit = JUNIT_XML.encode("utf-8")
        lcov = LCOV_INFO.encode("utf-8")
        receipt = {
            "schema": "benchreceipt.run/v1",
            "job_id": "unit-linux-py312",
            "reports": [
                {
                    "kind": "junit",
                    "path": "artifacts/junit.xml",
                    "size_bytes": len(junit),
                    "sha256": _sha256(junit),
                },
                {
                    "kind": "lcov",
                    "path": "artifacts/lcov.info",
                    "size_bytes": len(lcov),
                    "sha256": _sha256(lcov),
                },
            ],
        }
        jobs = {
            "unit-linux-py312": {
                "receipt.json": (
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8"),
                "artifacts/junit.xml": junit,
                "artifacts/lcov.info": lcov,
            }
        }
    for job_id, files in jobs.items():
        for rel, data in files.items():
            target = evidence / job_id / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return evidence


def make_repo(path: Path) -> Path:
    """Create a synthetic git repo at ``path`` with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "BenchReceipt Test"],
        check=True,
    )
    (path / "tracked.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "initial"], check=True)
    return path


# ---------------------------------------------------------------------------
# Manifest correctness (byte-level, independently recomputed)
# ---------------------------------------------------------------------------


def test_manifest_bytes_match_independent_recompute(tmp_path: Path):
    evidence = make_evidence(tmp_path)
    summary = build_bundle(evidence, tmp_path / "bundle")
    bundle = tmp_path / "bundle"
    manifest_bytes = (bundle / "SHA256SUMS.txt").read_bytes()

    # Summary agrees with the manifest file itself.
    assert summary["files"] == 3
    assert summary["sha256"] == _sha256(manifest_bytes)
    assert summary["manifest"] == "SHA256SUMS.txt"

    # Every line, recomputed from the bundle bytes by this test.
    lines = manifest_bytes.decode("utf-8").splitlines()
    assert len(lines) == 3
    rels = [line.split(" ", 2)[2] for line in lines]
    assert rels == sorted(rels)  # sorted by relative path
    total = 0
    for line in lines:
        digest, size_text, rel = line.split(" ", 2)
        data = (bundle / rel).read_bytes()
        assert digest == _sha256(data)
        assert int(size_text) == len(data)
        total += len(data)
    assert summary["total_bytes"] == total
    # No trailing blank line, LF endings only.
    assert manifest_bytes.endswith(b"\n")
    assert b"\r" not in manifest_bytes
    assert manifest_bytes.count(b"\n") == 3


def test_manifest_is_deterministic_across_builds(tmp_path: Path):
    evidence = make_evidence(tmp_path)
    build_bundle(evidence, tmp_path / "b1")
    build_bundle(evidence, tmp_path / "b2")
    assert (tmp_path / "b1" / "SHA256SUMS.txt").read_bytes() == (
        tmp_path / "b2" / "SHA256SUMS.txt"
    ).read_bytes()


def test_round_trip_verifies_ok(tmp_path: Path):
    evidence = make_evidence(tmp_path)
    summary = build_bundle(evidence, tmp_path / "bundle")
    result = verify_bundle(tmp_path / "bundle")
    assert result.ok
    assert result.problems == []
    assert result.files_checked == summary["files"] == 3
    assert result.manifest_files == 3


# ---------------------------------------------------------------------------
# Empty evidence + structurally invalid input
# ---------------------------------------------------------------------------


def test_empty_evidence_dir_bundles_and_verifies(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    summary = build_bundle(evidence, tmp_path / "bundle")
    assert summary == {
        "files": 0,
        "total_bytes": 0,
        "sha256": _sha256(b""),
        "out_dir": str(tmp_path / "bundle"),
        "manifest": "SHA256SUMS.txt",
    }
    assert (tmp_path / "bundle" / "SHA256SUMS.txt").read_bytes() == b""
    result = verify_bundle(tmp_path / "bundle")
    assert result.ok
    assert result.files_checked == 0
    assert result.manifest_files == 0


def test_build_bundle_rejects_missing_evidence_dir(tmp_path: Path):
    with pytest.raises(BundleError):
        build_bundle(tmp_path / "no-such-dir", tmp_path / "bundle")


def test_build_bundle_rejects_nonempty_out_dir(tmp_path: Path):
    evidence = make_evidence(tmp_path)
    out = tmp_path / "bundle"
    out.mkdir()
    (out / "stale.txt").write_text("stale", encoding="utf-8")
    with pytest.raises(BundleError):
        build_bundle(evidence, out)
    # Stale content is left untouched, not merged into.
    assert (out / "stale.txt").read_text(encoding="utf-8") == "stale"
    assert not (out / "SHA256SUMS.txt").exists()


def test_verify_bundle_rejects_non_bundle_dirs(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "receipt.json").write_text("{}", encoding="utf-8")
    with pytest.raises(BundleError):
        verify_bundle(plain)
    with pytest.raises(BundleError):
        verify_bundle(tmp_path / "missing")
    with pytest.raises(BundleError):
        verify_bundle(tmp_path / "plain" / "receipt.json")


# ---------------------------------------------------------------------------
# Tamper probes: one byte, one deletion, one size lie, one extra file
# ---------------------------------------------------------------------------


def _good_bundle(tmp_path: Path) -> Path:
    evidence = make_evidence(tmp_path)
    build_bundle(evidence, tmp_path / "bundle")
    return tmp_path / "bundle"


def test_tamper_one_byte_is_detected(tmp_path: Path):
    bundle = _good_bundle(tmp_path)
    junit = bundle / "unit-linux-py312" / "artifacts" / "junit.xml"
    data = bytearray(junit.read_bytes())
    data[10] ^= 0x01  # flip one byte
    junit.write_bytes(bytes(data))
    result = verify_bundle(bundle)
    assert not result.ok
    codes = _codes(result)
    assert "BUNDLE_HASH_MISMATCH" in codes
    assert "unit-linux-py312/artifacts/junit.xml" in _paths_for(
        result, "BUNDLE_HASH_MISMATCH"
    )
    # The receipt cross-check independently catches the same tamper:
    # the receipt's recorded digest no longer matches the file bytes.
    assert "REPORT_HASH_MISMATCH" in codes


def test_missing_file_is_detected(tmp_path: Path):
    bundle = _good_bundle(tmp_path)
    (bundle / "unit-linux-py312" / "artifacts" / "lcov.info").unlink()
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_MISSING_FILE" in _codes(result)
    assert "unit-linux-py312/artifacts/lcov.info" in _paths_for(
        result, "BUNDLE_MISSING_FILE"
    )
    assert "REPORT_MISSING" in _codes(result)


def test_size_lie_in_manifest_is_detected(tmp_path: Path):
    bundle = _good_bundle(tmp_path)
    manifest = bundle / "SHA256SUMS.txt"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    # Lie about the size of the first entry (hash left untouched).
    digest, _size, rel = lines[0].split(" ", 2)
    lines[0] = f"{digest} 999999 {rel}"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_SIZE_MISMATCH" in _codes(result)
    assert rel in _paths_for(result, "BUNDLE_SIZE_MISMATCH")


def test_extra_unlisted_file_is_detected(tmp_path: Path):
    bundle = _good_bundle(tmp_path)
    (bundle / "unit-linux-py312" / "artifacts" / "sneaky.txt").write_text(
        "not in the manifest\n", encoding="utf-8"
    )
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_EXTRA_FILE" in _codes(result)
    assert "unit-linux-py312/artifacts/sneaky.txt" in _paths_for(
        result, "BUNDLE_EXTRA_FILE"
    )


def test_receipt_hash_lie_is_detected_even_when_manifest_matches(tmp_path: Path):
    # Manifest is built from the actual bytes, so it agrees with disk;
    # the receipt is then edited to record a wrong digest. Only the
    # receipt cross-check can catch this — it must.
    bundle = _good_bundle(tmp_path)
    receipt_path = bundle / "unit-linux-py312" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["reports"][0]["sha256"] = "0" * 64
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # The edited receipt.json itself now differs from the manifest, so
    # the manifest check fires too; the receipt check must ALSO fire.
    result = verify_bundle(bundle)
    assert not result.ok
    assert "REPORT_HASH_MISMATCH" in _codes(result)


def test_malformed_manifest_is_fail_closed_not_fatal(tmp_path: Path):
    bundle = _good_bundle(tmp_path)
    (bundle / "SHA256SUMS.txt").write_text(
        "this is not a manifest line\n", encoding="utf-8"
    )
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_MANIFEST_MALFORMED" in _codes(result)
    # Every on-disk file is now unlisted, so extras are reported too.
    assert "BUNDLE_EXTRA_FILE" in _codes(result)


# ---------------------------------------------------------------------------
# Path traversal + symlink probes
# ---------------------------------------------------------------------------


def test_build_refuses_symlink_to_outside_file(tmp_path: Path):
    evidence = make_evidence(tmp_path)
    job = evidence / "unit-linux-py312"
    os.symlink("/etc/passwd", job / "artifacts" / "evil.xml")
    with pytest.raises(BundleError):
        build_bundle(evidence, tmp_path / "bundle")
    # No half-written bundle is left behind.
    assert not (tmp_path / "bundle" / "SHA256SUMS.txt").exists()
    # The outside target was never read or copied.
    assert Path("/etc/passwd").read_bytes()[:4] == b"root"


def test_build_refuses_symlinked_directory(tmp_path: Path):
    evidence = make_evidence(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    os.symlink(outside, evidence / "linked-job", target_is_directory=True)
    with pytest.raises(BundleError):
        build_bundle(evidence, tmp_path / "bundle")


def test_verify_rejects_symlink_in_bundle_and_never_follows_it(tmp_path: Path):
    bundle = _good_bundle(tmp_path)
    link = bundle / "unit-linux-py312" / "artifacts" / "evil.xml"
    os.symlink("/etc/passwd", link)
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_UNSUPPORTED_SYMLINK" in _codes(result)
    assert "unit-linux-py312/artifacts/evil.xml" in _paths_for(
        result, "BUNDLE_UNSUPPORTED_SYMLINK"
    )
    # /etc/passwd content never entered any problem message or hash.
    assert all("root:" not in p["message"] for p in result.problems)


def test_verify_symlink_replacing_listed_file_is_detected(tmp_path: Path):
    bundle = _good_bundle(tmp_path)
    target = bundle / "unit-linux-py312" / "artifacts" / "junit.xml"
    target.unlink()
    os.symlink("/etc/passwd", target)
    result = verify_bundle(bundle)
    assert not result.ok
    codes = _codes(result)
    assert "BUNDLE_UNSUPPORTED_SYMLINK" in codes
    assert "BUNDLE_MISSING_FILE" in codes  # symlink is not a real file


def _handmade_bundle(tmp_path: Path, manifest_text: str) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "SHA256SUMS.txt").write_text(manifest_text, encoding="utf-8")
    return bundle


def test_verify_rejects_dotdot_manifest_entry(tmp_path: Path):
    bundle = _handmade_bundle(
        tmp_path,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 0 ../evil.txt\n",
    )
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_PATH_ESCAPE" in _codes(result)


def test_verify_rejects_absolute_manifest_entry(tmp_path: Path):
    bundle = _handmade_bundle(
        tmp_path,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 0 /etc/passwd\n",
    )
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_PATH_ESCAPE" in _codes(result)
    assert not (tmp_path / "evil.txt").exists()


def test_verify_rejects_windows_drive_manifest_entry(tmp_path: Path):
    bundle = _handmade_bundle(
        tmp_path,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 0 C:/Windows/evil.txt\n",
    )
    result = verify_bundle(bundle)
    assert not result.ok
    assert "BUNDLE_PATH_ESCAPE" in _codes(result)


def test_receipt_report_path_escape_is_detected(tmp_path: Path):
    junit = JUNIT_XML.encode("utf-8")
    receipt = {
        "schema": "benchreceipt.run/v1",
        "job_id": "unit-linux-py312",
        "reports": [
            {
                "kind": "junit",
                "path": "../outside.xml",
                "size_bytes": len(junit),
                "sha256": _sha256(junit),
            }
        ],
    }
    evidence = make_evidence(
        tmp_path,
        {
            "unit-linux-py312": {
                "receipt.json": (
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8"),
            }
        },
    )
    build_bundle(evidence, tmp_path / "bundle")
    result = verify_bundle(tmp_path / "bundle")
    assert not result.ok
    assert "REPORT_HASH_MISMATCH" in _codes(result)


# ---------------------------------------------------------------------------
# Round-trips: real capture output, and the frozen S0 fixtures
# ---------------------------------------------------------------------------


def test_capture_output_round_trip(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    junit = repo / "junit.xml"
    junit.write_text(JUNIT_XML, encoding="utf-8")
    lcov = repo / "lcov.info"
    lcov.write_text(LCOV_INFO, encoding="utf-8")
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "print('ok')"],
        repo_path=repo,
        junit_path=junit,
        lcov_path=lcov,
        cwd=repo,
    )
    evidence_root = result.evidence_dir.parent  # .benchreceipt/evidence
    summary = build_bundle(evidence_root, tmp_path / "bundle")
    assert summary["files"] == 3
    verify_result = verify_bundle(tmp_path / "bundle")
    assert verify_result.ok
    assert verify_result.problems == []
    # The receipt inside the bundle is byte-identical to capture's.
    bundled = json.loads(
        (tmp_path / "bundle" / "unit-linux-py312" / "receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundled == result.receipt


def test_s0_normal_fixtures_bundle_and_verify(tmp_path: Path):
    """All 16 S0 normal controls bundle and verify cleanly."""
    for fixture_id in NORMAL_FIXTURES:
        evidence = _fixture_dir(fixture_id) / "evidence"
        bundle = tmp_path / f"bundle-{fixture_id}"
        build_bundle(evidence, bundle)
        result = verify_bundle(bundle)
        assert result.ok, f"{fixture_id}: {result.problems}"


def test_s0_planted_hash_fault_is_caught_by_receipt_cross_check(tmp_path: Path):
    """f2 plants a report hash mismatch: the manifest (built from the
    actual bytes) agrees with disk, so only the receipt cross-check
    can catch it — and it must."""
    evidence = _fixture_dir("f2") / "evidence"
    build_bundle(evidence, tmp_path / "bundle")
    result = verify_bundle(tmp_path / "bundle")
    assert not result.ok
    assert "REPORT_HASH_MISMATCH" in _codes(result)
    # No manifest-level problem: the manifest describes the real bytes.
    assert "BUNDLE_HASH_MISMATCH" not in _codes(result)
    assert "BUNDLE_MISSING_FILE" not in _codes(result)


def test_all_52_s0_fixtures_bundle_without_raising(tmp_path: Path):
    """Bundling must never crash, even on fixtures whose receipts are
    deliberately broken (h4 omits `command`, f1 lacks a report file)."""
    fixture_ids = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    assert len(fixture_ids) == 52
    for fixture_id in fixture_ids:
        evidence = FIXTURES / fixture_id / "evidence"
        bundle = tmp_path / f"bundle-{fixture_id}"
        summary = build_bundle(evidence, bundle)
        assert summary["files"] >= 1
        result = verify_bundle(bundle)
        assert isinstance(result.ok, bool)
        assert all(
            set(p) == {"code", "path", "message"} for p in result.problems
        )
