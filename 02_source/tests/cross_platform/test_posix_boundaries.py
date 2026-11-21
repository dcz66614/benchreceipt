"""Cross-platform / line-ending boundary tests (P027-T012).

BenchReceipt is developed and run on Linux, and Windows/macOS are
NOT_TESTED (no such host is available — see ``03_evidence/t012/
os_toolchain.log``). What T012 *can* pin on this host is the
format-level boundary the code already enforces, so a bundle or
report produced on one OS cannot silently change meaning on another:

- All on-disk formats are LF-only, UTF-8, POSIX relative paths
  (``BUNDLE_FORMAT.md``; ``bundle._validate_rel_posix`` rejects
  backslashes, drive letters, ``..`` segments and CRLF manifests).
- Report *parsers* tolerate CRLF input (a JUnit/LCOV file written by
  a Windows runner must still parse to the same summary), while the
  *writers* never emit CR — so a digest computed at capture time
  agrees with one computed at verify time on any host.
- A filename containing a backslash (legal on Linux, a separator on
  Windows) can never enter a bundle: ``build_bundle`` refuses it.

These tests pin the boundary; they do not claim a Windows/macOS pass.
If a real Windows/macOS run ever happens, it must be recorded as its
own evidence — these tests passing on Linux is not that evidence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from benchreceipt.bundle import BundleError, build_bundle
from benchreceipt.capture import capture
from benchreceipt.reports.junit import parse_junit
from benchreceipt.reports.lcov import parse_lcov

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


def _to_crlf(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Parsers tolerate CRLF input (Windows-written reports)
# ---------------------------------------------------------------------------


def test_crlf_junit_parses_to_same_summary_as_lf() -> None:
    lf = parse_junit(JUNIT_XML.encode("utf-8"))
    crlf = parse_junit(_to_crlf(JUNIT_XML))
    assert crlf == lf
    assert lf == {
        "tests": 2,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "suites": 1,
        "testcase_count": 2,
    }


def test_crlf_lcov_parses_to_same_summary_as_lf() -> None:
    lf = parse_lcov(LCOV_INFO.encode("utf-8"))
    crlf = parse_lcov(_to_crlf(LCOV_INFO))
    assert crlf == lf


def test_lone_cr_in_lcov_sf_path_is_preserved_not_stripped() -> None:
    # A bare CR inside an SF path (not a CRLF ending) is data, not a
    # line ending: the parser keeps it verbatim in ``source_file``
    # rather than quietly normalising it away. Pinned as observed
    # behaviour; see LIMITATIONS P2-04. The value is harmless in
    # practice: no LCOV summary field is stored in the receipt
    # (T011 probe (d)), and the SF path is never joined to the
    # filesystem — only the counts feed the verdict.
    bad = LCOV_INFO.replace("src/example.py", "src/exam\rple.py")
    summary = parse_lcov(bad.encode("utf-8"))
    assert summary["records"][0]["source_file"] == "src/exam\rple.py"
    assert summary["lines_found"] == 2
    assert summary["lines_hit"] == 1


# ---------------------------------------------------------------------------
# Writers never emit CR; bundle paths are POSIX-only
# ---------------------------------------------------------------------------


def _make_evidence(root: Path) -> Path:
    evidence = root / "evidence"
    job = evidence / "unit-linux-py312"
    (job / "artifacts").mkdir(parents=True)
    (job / "artifacts" / "junit.xml").write_bytes(JUNIT_XML.encode("utf-8"))
    (job / "receipt.json").write_text(
        '{"schema": "benchreceipt.run/v1", "job_id": "unit-linux-py312"}\n',
        encoding="utf-8",
    )
    return evidence


def test_manifest_bytes_have_no_cr_or_backslash(tmp_path: Path) -> None:
    evidence = _make_evidence(tmp_path)
    build_bundle(evidence, tmp_path / "bundle")
    manifest = (tmp_path / "bundle" / "SHA256SUMS.txt").read_bytes()
    assert b"\r" not in manifest
    assert b"\\" not in manifest
    assert manifest.endswith(b"\n")
    assert manifest.count(b"\n") == 2  # one line per file, no blank line


def test_backslash_filename_is_rejected_by_build_bundle(tmp_path: Path) -> None:
    # A backslash is a legal Linux filename character but a Windows
    # path separator: such a file must never enter a bundle, because
    # its manifest entry would mean something different on Windows.
    evidence = _make_evidence(tmp_path)
    evil = evidence / "unit-linux-py312" / "artifacts" / "we\\ird.txt"
    evil.write_bytes(b"backslash in name\n")
    with pytest.raises(BundleError, match="backslash"):
        build_bundle(evidence, tmp_path / "bundle")


def test_capture_receipt_json_is_lf_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t012@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "P027-T012"], check=True
    )
    (repo / "code.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "junit.xml").write_bytes(JUNIT_XML.encode("utf-8"))
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c1"], check=True)
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "pass"],
        junit_path="junit.xml",
        repo_path=repo,
        cwd=repo,
    )
    receipt_bytes = (
        repo / ".benchreceipt" / "evidence" / "unit-linux-py312" / "receipt.json"
    ).read_bytes()
    assert result.receipt_path == (
        repo / ".benchreceipt" / "evidence" / "unit-linux-py312" / "receipt.json"
    )
    assert b"\r" not in receipt_bytes
    assert receipt_bytes.endswith(b"\n")
