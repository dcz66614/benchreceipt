"""Probe (j) — tampered bundle manifest.

``SHA256SUMS.txt`` is the bundle's trust anchor: one line per file,
``<sha256> <size> <relative-posix-path>``, LF endings, no duplicates,
no self-reference, no escaping paths. Any tamper — CRLF endings,
duplicate lines, an extra blank line, a bad hash, a missing or extra
file, an escaping entry — must yield ``ok=False`` with a specific
problem code.

Sort order is the one documented property ``verify_bundle`` does NOT
enforce: reordering lines alone still verifies (the hashes are still
checked), and a tampered file in a reordered manifest is still
caught. That is recorded as an observation in SECURITY_FINDINGS.md,
not a security defect — order is canonicalisation, not a check.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from _evidence import make_evidence
from benchreceipt.bundle import build_bundle, verify_bundle

MANIFEST = "SHA256SUMS.txt"


def _build(tmp_path: Path) -> Path:
    evidence = make_evidence(tmp_path)
    bundle = tmp_path / "bundle"
    build_bundle(evidence, bundle)
    return bundle


def _lines(bundle: Path) -> list[str]:
    return (bundle / MANIFEST).read_text(encoding="utf-8").splitlines()


def _rewrite(bundle: Path, lines: list[str]) -> None:
    (bundle / MANIFEST).write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8"
    )


def _codes(result) -> list[str]:
    return [p["code"] for p in result.problems]


def test_untouched_bundle_passes(tmp_path: Path):
    """Control: a freshly built bundle verifies ok."""
    result = verify_bundle(_build(tmp_path))
    assert result.ok is True, result.problems
    assert result.problems == []
    assert result.files_checked == result.manifest_files > 0


def test_manifest_crlf_endings_rejected(tmp_path: Path):
    """CRLF line endings are BUNDLE_MANIFEST_MALFORMED."""
    bundle = _build(tmp_path)
    raw = (bundle / MANIFEST).read_bytes().replace(b"\n", b"\r\n")
    (bundle / MANIFEST).write_bytes(raw)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_MANIFEST_MALFORMED" in _codes(result)


def test_manifest_duplicate_line_rejected(tmp_path: Path):
    """A duplicated manifest entry is BUNDLE_MANIFEST_MALFORMED."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    lines.append(lines[0])
    _rewrite(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_MANIFEST_MALFORMED" in _codes(result)


def test_manifest_extra_blank_line_rejected(tmp_path: Path):
    """An extra blank line at the end is BUNDLE_MANIFEST_MALFORMED."""
    bundle = _build(tmp_path)
    raw = (bundle / MANIFEST).read_bytes() + b"\n"
    (bundle / MANIFEST).write_bytes(raw)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_MANIFEST_MALFORMED" in _codes(result)


def test_manifest_bad_hash_rejected(tmp_path: Path):
    """A non-hex / wrong-length hash field is BUNDLE_MANIFEST_MALFORMED."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    _digest, size, rel = lines[0].split(" ", 2)
    lines[0] = f"{'z' * 64} {size} {rel}"
    _rewrite(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_MANIFEST_MALFORMED" in _codes(result)


def test_manifest_wrong_hash_rejected(tmp_path: Path):
    """A well-formed but wrong hash is BUNDLE_HASH_MISMATCH."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    _digest, size, rel = lines[0].split(" ", 2)
    lines[0] = f"{'0' * 64} {size} {rel}"
    _rewrite(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_HASH_MISMATCH" in _codes(result)


def test_manifest_wrong_size_rejected(tmp_path: Path):
    """A well-formed but wrong size is BUNDLE_SIZE_MISMATCH."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    digest, size, rel = lines[0].split(" ", 2)
    lines[0] = f"{digest} {int(size) + 1} {rel}"
    _rewrite(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_SIZE_MISMATCH" in _codes(result)


def test_manifest_listing_itself_rejected(tmp_path: Path):
    """A manifest entry naming SHA256SUMS.txt is MALFORMED."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    digest, size, _rel = lines[0].split(" ", 2)
    lines.append(f"{digest} {size} {MANIFEST}")
    _rewrite(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_MANIFEST_MALFORMED" in _codes(result)


def test_manifest_missing_file_rejected(tmp_path: Path):
    """Deleting a listed file is BUNDLE_MISSING_FILE."""
    bundle = _build(tmp_path)
    (bundle / "unit-linux-py312" / "artifacts" / "junit.xml").unlink()
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_MISSING_FILE" in _codes(result)


def test_manifest_extra_unlisted_file_rejected(tmp_path: Path):
    """A file on disk but not in the manifest is BUNDLE_EXTRA_FILE."""
    bundle = _build(tmp_path)
    (bundle / "unit-linux-py312" / "artifacts" / "planted.txt").write_text(
        "planted", encoding="utf-8"
    )
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_EXTRA_FILE" in _codes(result)


def test_manifest_reordered_lines_still_verify(tmp_path: Path):
    """Reordering manifest lines alone still verifies (observation).

    ``verify_bundle`` does not enforce the documented sort order; the
    manifest is treated as a set of entries. Order carries no security
    information — the hashes are still checked entry by entry — so
    this is a format-strictness observation, not a defect.
    """
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    _rewrite(bundle, list(reversed(lines)))
    result = verify_bundle(bundle)
    assert result.ok is True, result.problems


def test_reordered_manifest_still_detects_tampering(tmp_path: Path):
    """A reordered manifest still catches a flipped artifact byte."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    _rewrite(bundle, list(reversed(lines)))
    artifact = bundle / "unit-linux-py312" / "artifacts" / "junit.xml"
    data = bytearray(artifact.read_bytes())
    data[50] ^= 0xFF
    artifact.write_bytes(bytes(data))
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_HASH_MISMATCH" in _codes(result)


def test_manifest_entry_swapped_between_files_rejected(tmp_path: Path):
    """Swapping two entries' hashes is a hash mismatch for both."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    assert len(lines) >= 2
    d0, s0, r0 = lines[0].split(" ", 2)
    d1, s1, r1 = lines[1].split(" ", 2)
    lines[0] = f"{d1} {s0} {r0}"
    lines[1] = f"{d0} {s1} {r1}"
    _rewrite(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_HASH_MISMATCH" in _codes(result)


def test_manifest_with_wrong_path_but_right_hash_rejected(tmp_path: Path):
    """Renaming a manifest path (hash kept) is missing + extra file."""
    bundle = _build(tmp_path)
    lines = _lines(bundle)
    digest, size, rel = lines[0].split(" ", 2)
    lines[0] = f"{digest} {size} {rel}.renamed"
    _rewrite(bundle, lines)
    result = verify_bundle(bundle)
    assert result.ok is False, result
    assert "BUNDLE_MISSING_FILE" in _codes(result)
    assert "BUNDLE_EXTRA_FILE" in _codes(result)
