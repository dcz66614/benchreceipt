"""LCOV parser tests (P027-T005, PROJECT_BOOK §5.4, §11).

Covers: valid single- and multi-record reports, summary-line checks,
malformed lines, missing SF / missing end_of_record, absolute and
traversal SF paths, oversized reports, and path-vs-bytes input. No
coverage-quality score is ever asserted: the parser records source
files and line hits only.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchreceipt.reports.lcov import LcovError, MAX_LCOV_BYTES, parse_lcov

VALID_SINGLE = b"""TN:
SF:src/foo.py
FN:1,foo
FNF:1
FNH:1
FNDA:1,foo
DA:1,1
DA:2,0
LF:2
LH:1
end_of_record
"""

VALID_MULTI = b"""TN:test_a
SF:src/a.py
DA:1,3
DA:2,0
LF:2
LH:1
end_of_record
TN:test_b
SF:src/b.py
FN:5,bar
FNF:1
FNH:0
FNDA:0,bar
BRDA:5,0,0,1
BRDA:5,0,1,-
BRF:2
BRH:1
DA:5,2
DA:6,2
LF:2
LH:2
end_of_record
"""

NO_SUMMARIES = b"""SF:src/c.py
DA:1,1
DA:2,1
DA:3,0
end_of_record
"""


def test_valid_single_record_totals():
    result = parse_lcov(VALID_SINGLE)
    assert result["files"] == 1
    assert result["lines_found"] == 2
    assert result["lines_hit"] == 1
    assert result["records"] == [
        {
            "source_file": "src/foo.py",
            "lines_found": 2,
            "lines_hit": 1,
            "functions_found": 1,
            "functions_hit": 1,
            "branches_found": 0,
            "branches_hit": 0,
        }
    ]


def test_valid_multi_record_totals():
    result = parse_lcov(VALID_MULTI)
    assert result["files"] == 2
    assert result["lines_found"] == 4
    assert result["lines_hit"] == 3
    assert result["records"][0]["source_file"] == "src/a.py"
    assert result["records"][1]["source_file"] == "src/b.py"
    assert result["records"][1]["functions_found"] == 1
    assert result["records"][1]["functions_hit"] == 0
    assert result["records"][1]["branches_found"] == 2
    assert result["records"][1]["branches_hit"] == 1


def test_summaries_derived_when_absent():
    result = parse_lcov(NO_SUMMARIES)
    assert result["files"] == 1
    assert result["lines_found"] == 3
    assert result["lines_hit"] == 2
    assert result["records"][0]["functions_found"] == 0


def test_s0_fixture_shape_fn_fnh_without_fnda():
    # Verbatim content of the frozen S0 fixture LCOV files
    # (n08-lcov-only, n13-junit-plus-lcov): FN + FNH but no FNDA
    # lines. The stated FNH is recorded as-is; there is no FNDA data
    # to check it against, and rejecting this shape would break S0.
    data = b"""TN:
SF:src/foo.py
FN:1,foo
FNF:1
FNH:1
DA:1,1
DA:2,0
LF:2
LH:1
end_of_record
"""
    result = parse_lcov(data)
    assert result["files"] == 1
    assert result["lines_found"] == 2
    assert result["lines_hit"] == 1
    assert result["records"][0]["functions_found"] == 1
    assert result["records"][0]["functions_hit"] == 1


def test_fnh_checked_against_fnda_when_present():
    # With FNDA lines present, a disagreeing FNH is malformed.
    data = b"""SF:src/a.py
FN:1,foo
FNF:1
FNH:1
FNDA:0,foo
DA:1,0
LF:1
LH:0
end_of_record
"""
    with pytest.raises(LcovError) as excinfo:
        parse_lcov(data)
    assert excinfo.value.code == "LCOV_MALFORMED"


def test_path_input_and_bytes_input_agree(tmp_path: Path):
    path = tmp_path / "lcov.info"
    path.write_bytes(VALID_SINGLE)
    assert parse_lcov(path) == parse_lcov(VALID_SINGLE)
    assert parse_lcov(str(path)) == parse_lcov(VALID_SINGLE)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\n",
        b"TN:\n",
        # Unknown line tag.
        b"SF:src/a.py\nXX:1\nend_of_record\n",
        # Line with no tag separator.
        b"SF:src/a.py\nDA1,1\nend_of_record\n",
        # Malformed DA (non-integer hits / line).
        b"SF:src/a.py\nDA:1,many\nend_of_record\n",
        b"SF:src/a.py\nDA:x,1\nend_of_record\n",
        b"SF:src/a.py\nDA:1\nend_of_record\n",
        # DA line number 0.
        b"SF:src/a.py\nDA:0,1\nend_of_record\n",
        # Duplicate DA line number in one record.
        b"SF:src/a.py\nDA:1,1\nDA:1,0\nend_of_record\n",
        # Record without SF.
        b"DA:1,1\nend_of_record\n",
        # Record not closed by end_of_record.
        b"SF:src/a.py\nDA:1,1\n",
        # end_of_record with no open record.
        b"end_of_record\n",
        # Duplicate SF in one record.
        b"SF:src/a.py\nSF:src/b.py\nend_of_record\n",
        # Data line before SF.
        b"DA:1,1\nSF:src/a.py\nend_of_record\n",
        # LF summary disagrees with the DA lines.
        b"SF:src/a.py\nDA:1,1\nDA:2,0\nLF:5\nLH:1\nend_of_record\n",
        # LH summary disagrees with the DA lines.
        b"SF:src/a.py\nDA:1,1\nDA:2,0\nLF:2\nLH:2\nend_of_record\n",
        # FNF summary disagrees with the FN lines.
        b"SF:src/a.py\nFN:1,foo\nFNF:2\nend_of_record\n",
        # BRDA with wrong field count / bad taken value.
        b"SF:src/a.py\nBRDA:1,0,0\nend_of_record\n",
        b"SF:src/a.py\nBRDA:1,0,0,maybe\nend_of_record\n",
        # Non-UTF-8 bytes.
        b"SF:src/a.py\nDA:1,1\n\xff\xfe\nend_of_record\n",
        # NUL byte.
        b"SF:src/a.py\nDA:1,1\n\x00\nend_of_record\n",
    ],
)
def test_malformed_lcov_raises(data: bytes):
    with pytest.raises(LcovError) as excinfo:
        parse_lcov(data)
    assert excinfo.value.code == "LCOV_MALFORMED"


@pytest.mark.parametrize(
    "sf",
    [
        "/etc/passwd",
        "/home/sam/project/src/a.py",
        "../secret.py",
        "src/../../etc/passwd",
        "..\\secret.py",
        "src\\a.py",
        "C:/Users/sam/a.py",
        "C:a.py",
        "\\\\server\\share\\a.py",
        "src//a.py",
        "src/a.py/",
    ],
)
def test_absolute_or_escaping_sf_path_rejected(sf: str):
    data = f"SF:{sf}\nDA:1,1\nend_of_record\n".encode("utf-8")
    with pytest.raises(LcovError) as excinfo:
        parse_lcov(data)
    assert excinfo.value.code == "LCOV_MALFORMED"


def test_oversized_bytes_rejected_via_patched_limit(monkeypatch):
    import benchreceipt.reports.lcov as lcov_mod

    monkeypatch.setattr(lcov_mod, "MAX_LCOV_BYTES", 32)
    with pytest.raises(LcovError) as excinfo:
        parse_lcov(VALID_SINGLE)
    assert excinfo.value.code == "LCOV_MALFORMED"
    monkeypatch.setattr(lcov_mod, "MAX_LCOV_BYTES", len(NO_SUMMARIES))
    assert parse_lcov(NO_SUMMARIES)["files"] == 1


def test_oversized_file_rejected_without_reading(tmp_path: Path):
    # Sparse file: one byte past the frozen 1 GiB limit, created with
    # truncate so it costs no disk. The stat check must reject it
    # before any content is read.
    assert MAX_LCOV_BYTES == 1073741824
    path = tmp_path / "huge.info"
    with path.open("wb") as handle:
        handle.truncate(MAX_LCOV_BYTES + 1)
    assert os.path.getsize(path) == MAX_LCOV_BYTES + 1
    with pytest.raises(LcovError) as excinfo:
        parse_lcov(path)
    assert excinfo.value.code == "LCOV_MALFORMED"


def test_missing_file_raises_typed_error(tmp_path: Path):
    with pytest.raises(LcovError) as excinfo:
        parse_lcov(tmp_path / "does-not-exist.info")
    assert excinfo.value.code == "LCOV_MALFORMED"


def test_wrong_input_type_raises_type_error():
    with pytest.raises(TypeError):
        parse_lcov(12345)  # type: ignore[arg-type]
