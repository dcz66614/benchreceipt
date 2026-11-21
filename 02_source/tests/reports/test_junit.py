"""JUnit parser tests (P027-T005, PROJECT_BOOK §5.4, §11).

Covers: valid single-suite and multi-suite reports, empty reports,
malformed XML, testcase-count vs ``tests``-attribute mismatch, DTD /
external-entity probes (which must trigger no outside read), oversized
reports, skipped-only reports, and path-vs-bytes input.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchreceipt.reports.junit import JUnitError, MAX_JUNIT_BYTES, parse_junit

VALID_SINGLE = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite" tests="4" failures="1" errors="1" skipped="1">\
<testcase classname="t" name="test_pass"></testcase>\
<testcase classname="t" name="test_fail"><failure message="assert">trace</failure></testcase>\
<testcase classname="t" name="test_err"><error message="boom">trace</error></testcase>\
<testcase classname="t" name="test_skip"><skipped/></testcase>\
</testsuite>
"""

VALID_MULTI = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites tests="3" failures="1" errors="0" skipped="0">\
<testsuite name="a" tests="2" failures="1" errors="0" skipped="0">\
<testcase classname="t" name="one"></testcase>\
<testcase classname="t" name="two"><failure message="x">y</failure></testcase>\
</testsuite>\
<testsuite name="b" tests="1" failures="0" errors="0" skipped="0">\
<testcase classname="t" name="three"></testcase>\
</testsuite>\
</testsuites>
"""

EMPTY = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite" tests="0" failures="0" errors="0" skipped="0"></testsuite>
"""

SKIPPED_ONLY = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite" tests="3" failures="0" errors="0" skipped="3">\
<testcase classname="t" name="a"><skipped/></testcase>\
<testcase classname="t" name="b"><skipped/></testcase>\
<testcase classname="t" name="c"><skipped/></testcase>\
</testsuite>
"""

NO_ATTRS = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite">\
<testcase classname="t" name="a"></testcase>\
<testcase classname="t" name="b"></testcase>\
</testsuite>
"""

NAMESPACED = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite xmlns="urn:junit" name="suite" tests="1" failures="0" errors="0" skipped="0">\
<testcase classname="t" name="a"></testcase>\
</testsuite>
"""


def test_valid_single_suite_counts():
    result = parse_junit(VALID_SINGLE)
    assert result == {
        "tests": 4,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
        "testcase_count": 4,
        "suites": 1,
    }


def test_valid_multi_suite_wrapper_sums_suites():
    result = parse_junit(VALID_MULTI)
    assert result["tests"] == 3
    assert result["failures"] == 1
    assert result["errors"] == 0
    assert result["skipped"] == 0
    assert result["testcase_count"] == 3
    assert result["suites"] == 2


def test_empty_report_parses_to_zero_tests():
    # Empty parses fine here; the verifier (not this parser) maps
    # tests == 0 to JUNIT_EMPTY, never to PASS.
    result = parse_junit(EMPTY)
    assert result["tests"] == 0
    assert result["testcase_count"] == 0
    assert result["failures"] == 0
    assert result["errors"] == 0


def test_skipped_only_report_reports_skipped_separately():
    result = parse_junit(SKIPPED_ONLY)
    assert result["tests"] == 3
    assert result["skipped"] == 3
    assert result["failures"] == 0
    assert result["errors"] == 0


def test_missing_count_attributes_are_derived_from_elements():
    result = parse_junit(NO_ATTRS)
    assert result["tests"] == 2
    assert result["failures"] == 0


def test_namespaced_junit_parses():
    result = parse_junit(NAMESPACED)
    assert result["tests"] == 1
    assert result["suites"] == 1


def test_path_input_and_bytes_input_agree(tmp_path: Path):
    path = tmp_path / "junit.xml"
    path.write_bytes(VALID_SINGLE)
    assert parse_junit(path) == parse_junit(VALID_SINGLE)
    assert parse_junit(str(path)) == parse_junit(VALID_SINGLE)


@pytest.mark.parametrize(
    "data",
    [
        b"this is not xml at all\njust some plain text\n",
        b"",
        b"   \n",
        b'<?xml version="1.0"?><testsuite tests="2"><testcase name="a">',
        b'<?xml version="1.0"?><testsuite tests="1"><testcase name="a"></testsuite>',
        b'<?xml version="1.0"?><foo tests="1"></foo>',
        b'<?xml version="1.0"?><testsuites></testsuites>',
    ],
)
def test_malformed_xml_raises(data: bytes):
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(data)
    assert excinfo.value.code == "JUNIT_MALFORMED"


@pytest.mark.parametrize(
    "data",
    [
        # tests attribute disagrees with the counted testcases.
        b'<testsuite tests="5" failures="0" errors="0" skipped="0">'
        b'<testcase name="a"/><testcase name="b"/><testcase name="c"/></testsuite>',
        b'<testsuite tests="2" failures="0" errors="0" skipped="0">'
        b'<testcase name="a"/><testcase name="b"/><testcase name="c"/></testsuite>',
        # failures attribute disagrees with counted <failure> elements.
        b'<testsuite tests="2" failures="0" errors="0" skipped="0">'
        b'<testcase name="a"><failure message="x">y</failure></testcase>'
        b'<testcase name="b"/></testsuite>',
        # skipped attribute disagrees with counted <skipped> elements.
        b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase name="a"><skipped/></testcase></testsuite>',
        # Non-integer attribute.
        b'<testsuite tests="ten" failures="0" errors="0" skipped="0">'
        b'<testcase name="a"/></testsuite>',
        # Negative attribute.
        b'<testsuite tests="-1" failures="0" errors="0" skipped="0"></testsuite>',
        # Wrapper attribute disagrees with the summed suites.
        b'<testsuites tests="9"><testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase name="a"/></testsuite></testsuites>',
    ],
)
def test_count_attribute_mismatch_raises(data: bytes):
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(data)
    assert excinfo.value.code == "JUNIT_MALFORMED"


def test_dtd_external_entity_is_rejected_without_reading_the_target(
    tmp_path: Path,
):
    # Sentinel file: if any entity were resolved, its unique marker
    # would have to be read. The parser rejects the DOCTYPE before
    # parsing, so the marker must never surface anywhere.
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("XXE_SENTINEL_MARKER_7f3a9", encoding="utf-8")
    payload = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE testsuite [<!ENTITY xxe SYSTEM "file://'
        + str(sentinel).encode("utf-8")
        + b'">]>\n'
        b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase name="a">&xxe;</testcase></testsuite>'
    )
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(payload)
    assert excinfo.value.code == "JUNIT_MALFORMED"
    assert "XXE_SENTINEL_MARKER_7f3a9" not in str(excinfo.value)
    assert sentinel.read_text(encoding="utf-8") == "XXE_SENTINEL_MARKER_7f3a9"


def test_external_dtd_is_rejected(tmp_path: Path):
    payload = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE testsuite SYSTEM "file://'
        + str(tmp_path / "no-such.dtd").encode("utf-8")
        + b'">\n'
        b'<testsuite tests="0" failures="0" errors="0" skipped="0"></testsuite>'
    )
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(payload)
    assert excinfo.value.code == "JUNIT_MALFORMED"


def test_internal_entity_billion_laughs_shape_is_rejected():
    payload = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE testsuite [<!ENTITY a "xxxxxxxxxx">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>\n'
        b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase name="a">&b;</testcase></testsuite>'
    )
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(payload)
    assert excinfo.value.code == "JUNIT_MALFORMED"


def test_oversized_bytes_rejected_via_patched_limit(monkeypatch):
    import benchreceipt.reports.junit as junit_mod

    monkeypatch.setattr(junit_mod, "MAX_JUNIT_BYTES", 64)
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(VALID_SINGLE)
    assert excinfo.value.code == "JUNIT_MALFORMED"
    # At exactly the (patched) limit a small report still parses.
    monkeypatch.setattr(junit_mod, "MAX_JUNIT_BYTES", len(EMPTY))
    assert parse_junit(EMPTY)["tests"] == 0


def test_oversized_file_rejected_without_reading(tmp_path: Path):
    # Sparse file: one byte past the frozen 1 GiB limit, created with
    # truncate so it costs no disk. The stat check must reject it
    # before any content is read.
    assert MAX_JUNIT_BYTES == 1073741824
    path = tmp_path / "huge.xml"
    with path.open("wb") as handle:
        handle.truncate(MAX_JUNIT_BYTES + 1)
    assert os.path.getsize(path) == MAX_JUNIT_BYTES + 1
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(path)
    assert excinfo.value.code == "JUNIT_MALFORMED"


def test_missing_file_raises_typed_error(tmp_path: Path):
    with pytest.raises(JUnitError) as excinfo:
        parse_junit(tmp_path / "does-not-exist.xml")
    assert excinfo.value.code == "JUNIT_MALFORMED"


def test_wrong_input_type_raises_type_error():
    with pytest.raises(TypeError):
        parse_junit(12345)  # type: ignore[arg-type]
