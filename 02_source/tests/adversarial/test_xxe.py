"""Probe (c) — DTD / XXE variants.

``benchreceipt.reports.junit`` rejects any ``<!DOCTYPE`` or
``<!ENTITY`` declaration by byte pre-scan before ElementTree ever
sees the document, so no DTD is processed and no external entity is
resolved. Each payload below references a sentinel file that must
stay byte-identical and whose content must never appear in any parse
result, receipt, or verdict.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from _evidence import (
    JUNIT_XML,
    assert_not_pass,
    head,
    make_repo,
)
from benchreceipt.capture import capture
from benchreceipt.reports.junit import JUnitError, parse_junit
from benchreceipt.verify import evaluate

# Local-capture policy (workflow "local"), mirroring the mutation tests.
LOCAL_POLICY = {
    "schema_version": 1,
    "source_mode": "event_sha",
    "expected_workflow": "local",
    "required_jobs": ["unit-linux-py312"],
    "min_tests": 1,
    "require_clean_source_after": True,
    "same_tree_across_jobs": True,
    "same_run_id": True,
    "same_run_attempt": True,
    "reports": {"junit": "required", "lcov": "optional"},
}

SENTINEL_VALUE = "T011_XXE_SENTINEL_7f3a9c21_DO_NOT_LEAK"


def _sentinel(tmp_path: Path) -> Path:
    target = tmp_path / "sentinel.txt"
    target.write_text(SENTINEL_VALUE + "\n", encoding="utf-8")
    return target


def _check_sentinel_intact(target: Path) -> None:
    assert target.read_text(encoding="utf-8") == SENTINEL_VALUE + "\n"


def _external_dtd(sentinel: Path) -> bytes:
    return (
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE testsuite SYSTEM "file://{sentinel}">\n'
        '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
        ' skipped="0">'
        '<testcase classname="s" name="t1"/>'
        '<testcase classname="s" name="t2"/>'
        "</testsuite></testsuites>\n"
    ).encode("utf-8")


def _parameter_entity(sentinel: Path) -> bytes:
    return (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE testsuite ['
        f'<!ENTITY % pe SYSTEM "file://{sentinel}"> %pe;'
        ']>\n'
        '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
        ' skipped="0">'
        '<testcase classname="s" name="t1"/>'
        '<testcase classname="s" name="t2"/>'
        "</testsuite></testsuites>\n"
    ).encode("utf-8")


def _billion_laughs() -> bytes:
    # Three expansion levels; if any parser expanded entities, the
    # result would blow up. Nothing here is ever expanded: the
    # declaration itself is rejected first.
    return (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE lolz ['
        '<!ENTITY lol "lollollollollollollollollollol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        ']>\n'
        '<testsuites><testsuite name="s" tests="1" failures="0" errors="0"'
        ' skipped="0">'
        '<testcase classname="s" name="t1"><failure message="&lol3;"/>'
        "</testcase>"
        "</testsuite></testsuites>\n"
    ).encode("utf-8")


def _external_general_entity(sentinel: Path) -> bytes:
    return (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE testsuite ['
        f'<!ENTITY xxe SYSTEM "file://{sentinel}">'
        ']>\n'
        '<testsuites><testsuite name="s" tests="1" failures="1" errors="0"'
        ' skipped="0">'
        '<testcase classname="s" name="t1">'
        '<failure message="leak: &xxe;"/>'
        "</testcase>"
        "</testsuite></testsuites>\n"
    ).encode("utf-8")


def _internal_dtd_no_external_ref() -> bytes:
    return (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE testsuite [<!ENTITY innocuous "plain text">]>\n'
        '<testsuites><testsuite name="s" tests="2" failures="0" errors="0"'
        ' skipped="0">'
        '<testcase classname="s" name="t1"/>'
        '<testcase classname="s" name="t2"/>'
        "</testsuite></testsuites>\n"
    ).encode("utf-8")


@pytest.mark.parametrize(
    "payload",
    ["external_dtd", "parameter_entity", "billion_laughs",
     "external_general_entity", "internal_dtd"],
)
def test_junit_parser_rejects_dtd_variants(tmp_path: Path, payload: str):
    """Every DTD-bearing JUnit is rejected; the sentinel stays intact."""
    sentinel = _sentinel(tmp_path)
    builders = {
        "external_dtd": lambda: _external_dtd(sentinel),
        "parameter_entity": lambda: _parameter_entity(sentinel),
        "billion_laughs": _billion_laughs,
        "external_general_entity": lambda: _external_general_entity(sentinel),
        "internal_dtd": _internal_dtd_no_external_ref,
    }
    data = builders[payload]()
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(data)
    # The sentinel's content must not leak into the error either.
    assert SENTINEL_VALUE not in str(excinfo.value)
    _check_sentinel_intact(sentinel)


def test_junit_parser_rejects_lowercase_doctype(tmp_path: Path):
    """Case variation (``<!doctype``) is rejected too."""
    sentinel = _sentinel(tmp_path)
    data = _external_dtd(sentinel).replace(b"<!DOCTYPE", b"<!doctype")
    with pytest.raises(JUnitError):
        parse_junit(data)
    _check_sentinel_intact(sentinel)


def test_junit_parser_accepts_plain_report_without_dtd():
    """Control: a DOCTYPE-free report parses normally."""
    summary = parse_junit(JUNIT_XML.encode("utf-8"))
    assert summary["tests"] == 2
    assert summary["failures"] == 0


def test_junit_parser_accepts_failure_text_mentioning_system(tmp_path: Path):
    """Control: the word SYSTEM in failure text (no declaration) is fine."""
    xml = (
        '<?xml version="1.0"?>\n'
        '<testsuites><testsuite name="s" tests="1" failures="1" errors="0"'
        ' skipped="0">'
        '<testcase classname="s" name="t1">'
        '<failure message="system under test failed"/>'
        "</testcase>"
        "</testsuite></testsuites>\n"
    ).encode("utf-8")
    summary = parse_junit(xml)
    assert summary["tests"] == 1
    assert summary["failures"] == 1


def test_xxe_junit_end_to_end_never_passes(tmp_path: Path):
    """Capture + verify of an XXE JUnit: INVALID, never BOUND_PASS.

    Capture omits the JUnit summary (malformed report, fail-closed)
    and verify re-parses the artifact itself, yielding
    JUNIT_MALFORMED. The sentinel file is untouched and its content
    appears nowhere in the receipt or the verdict.
    """
    sentinel = _sentinel(tmp_path)
    repo = make_repo(tmp_path / "repo")
    sha = head(repo)
    (repo / "junit.xml").write_bytes(_external_general_entity(sentinel))
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "pass"],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    assert "junit" not in result.receipt  # no guessed summary
    receipt_text = (
        repo / ".benchreceipt" / "evidence" / "unit-linux-py312"
        / "receipt.json"
    ).read_text(encoding="utf-8")
    assert SENTINEL_VALUE not in receipt_text
    verdict = evaluate(LOCAL_POLICY, sha, repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "INVALID", verdict
    assert "JUNIT_MALFORMED" in verdict["reason_codes"], verdict
    assert "MISSING_FIELD" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)
    assert SENTINEL_VALUE not in json.dumps(verdict)
    _check_sentinel_intact(sentinel)


def test_billion_laughs_end_to_end_never_passes(tmp_path: Path):
    """Billion-laughs payload end to end: INVALID, no expansion."""
    repo = make_repo(tmp_path / "repo")
    sha = head(repo)
    (repo / "junit.xml").write_bytes(_billion_laughs())
    result = capture(
        job_id="unit-linux-py312",
        matrix={"os": "ubuntu-latest", "python": "3.12"},
        argv=[sys.executable, "-c", "pass"],
        repo_path=repo, junit_path="junit.xml", cwd=repo,
    )
    assert "junit" not in result.receipt
    verdict = evaluate(LOCAL_POLICY, sha, repo / ".benchreceipt" / "evidence")
    assert verdict["status"] == "INVALID", verdict
    assert "JUNIT_MALFORMED" in verdict["reason_codes"], verdict
    assert_not_pass(verdict)
