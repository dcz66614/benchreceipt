"""Safe LCOV parsing (P027-T005, PROJECT_BOOK §5.4 and §11).

Produces a standardised summary::

    parse_lcov(path_or_bytes) -> {
        "files": int,        # number of records (one per SF entry)
        "lines_found": int,  # total DA entries across all records
        "lines_hit": int,    # total DA entries with hits > 0
        "records": [
            {"source_file": str, "lines_found": int, "lines_hit": int,
             "functions_found": int, "functions_hit": int,
             "branches_found": int, "branches_hit": int},
            ...
        ],
    }

Rules (fail-closed; uncertainty returns INVALID, never a lenient guess):

- Format: one record per source file, made of ``TN`` / ``SF`` / ``FN`` /
  ``FNDA`` / ``FNF`` / ``FNH`` / ``BRDA`` / ``BRF`` / ``BRH`` / ``DA`` /
  ``LF`` / ``LH`` lines, closed by ``end_of_record``. Any unknown line
  tag, any malformed value, a record without ``SF``, a record without
  its closing ``end_of_record``, a duplicate ``DA`` line number inside
  one record, or an empty file raises :class:`LcovError`.
- ``SF`` paths are relative only: an absolute path, a Windows drive
  path, a backslash, a ``//``, or any ``..`` segment is rejected
  (PROJECT_BOOK §11.2 path containment; the same rule the frozen
  schema applies to ``reports[].path``).
- Summary lines are checked, not trusted: a present ``LF`` / ``LH``
  must equal the ``DA`` counts derived from that record, ``FNF`` must
  equal the ``FN`` count, ``BRF`` / ``BRH`` the ``BRDA`` count / hit
  count, and ``FNH`` the hit ``FNDA`` count when ``FNDA`` lines are
  present. (When a record carries ``FN``/``FNH`` but no ``FNDA`` lines
  — as the frozen S0 fixtures do — there is no ``FNDA`` data to check
  against, so the stated ``FNH`` is recorded as-is.) When a summary
  line is absent the value is derived from the data lines.
- No coverage-quality score is computed and no behaviour correctness
  is inferred from the numbers (PROJECT_BOOK §5.4, §2.2): the parser
  records source files and line hits only.
- The file size limit is the frozen schema limit
  (``src/benchreceipt/schemas/README.md``: ``reports[].size_bytes`` <= 1 GiB), checked
  before the file is read and again after reading.
- :class:`LcovError` carries ``.code == "LCOV_MALFORMED"``. That code
  is new: the frozen vocabulary in ``docs/REASON_CODES.md`` has no
  LCOV code at all, and none of its existing codes describes a
  malformed LCOV report, so inventing a misleading reuse (for example
  ``JUNIT_MALFORMED`` for a coverage file) would be worse. The code
  follows the frozen code shape (``^[A-Z][A-Z0-9_]{0,63}$``) and the
  verifier maps it to ``INVALID``; T008 must ratify it in
  ``REASON_CODES.md`` via ADR (flagged in the T005 handoff).

Standard library only. No network access, no file access outside the
one file given.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["LcovError", "MAX_LCOV_BYTES", "parse_lcov"]

# Frozen schema limit: reports[].size_bytes <= 1 GiB (src/benchreceipt/schemas/README.md,
# ADR-001 decision 5). Enforced here so an oversized report can never
# be loaded into memory.
MAX_LCOV_BYTES = 1073741824

_INT_RE = re.compile(r"[0-9]+\Z")
_DRIVE_RE = re.compile(r"[A-Za-z]:")

_KNOWN_TAGS = frozenset(
    {"TN", "SF", "FN", "FNDA", "FNF", "FNH", "BRDA", "BRF", "BRH", "DA", "LF", "LH"}
)


class LcovError(ValueError):
    """An LCOV report that cannot be trusted as parsed.

    Carries ``.code == "LCOV_MALFORMED"`` (see the module docstring:
    a new code in the frozen shape, pending T008/ADR ratification).
    The verifier maps it to ``INVALID``.
    """

    def __init__(self, message: str, code: str = "LCOV_MALFORMED") -> None:
        self.code = code
        super().__init__(message)


def _read_input(path_or_bytes: str | Path | bytes | bytearray) -> bytes:
    """Return the report bytes, enforcing the size limit first."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
        if len(data) > MAX_LCOV_BYTES:
            raise LcovError(
                f"LCOV report exceeds size limit of {MAX_LCOV_BYTES} bytes"
            )
        return data
    if isinstance(path_or_bytes, (str, Path)):
        path = Path(path_or_bytes)
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise LcovError(f"LCOV report is unreadable: {path}: {exc}") from exc
        if size > MAX_LCOV_BYTES:
            raise LcovError(
                f"LCOV report exceeds size limit of {MAX_LCOV_BYTES} bytes"
            )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise LcovError(f"LCOV report is unreadable: {path}: {exc}") from exc
        if len(data) > MAX_LCOV_BYTES:
            raise LcovError(
                f"LCOV report exceeds size limit of {MAX_LCOV_BYTES} bytes"
            )
        return data
    raise TypeError(
        "parse_lcov expects a path (str/Path) or bytes, "
        f"got {type(path_or_bytes).__name__}"
    )


def _validate_sf_path(sf: str) -> None:
    """An SF path must be a plain relative path (no escape possible)."""
    if not sf:
        raise LcovError("LCOV SF path is empty")
    if sf.startswith("/") or sf.startswith("\\"):
        raise LcovError(f"LCOV SF path is absolute: {sf!r}")
    if _DRIVE_RE.match(sf):
        raise LcovError(f"LCOV SF path is absolute: {sf!r}")
    if "\\" in sf:
        raise LcovError(f"LCOV SF path contains a backslash: {sf!r}")
    if "//" in sf:
        raise LcovError(f"LCOV SF path contains '//': {sf!r}")
    if sf.endswith("/"):
        raise LcovError(f"LCOV SF path ends with '/': {sf!r}")
    if ".." in sf.split("/"):
        raise LcovError(f"LCOV SF path escapes its directory: {sf!r}")


def _parse_int(value: str, what: str) -> int:
    if not _INT_RE.match(value):
        raise LcovError(f"LCOV {what} is not a non-negative integer: {value!r}")
    return int(value)


def _parse_record(lines: list[str], record_no: int) -> dict:
    """Parse and validate one record (lines excluding end_of_record)."""
    tn_seen = False
    sf: str | None = None
    fn_count = 0
    fnda_hits = 0
    fnda_seen = False
    brda_count = 0
    brda_hits = 0
    da: dict[int, int] = {}
    summaries: dict[str, int] = {}

    def fail(message: str) -> None:
        raise LcovError(f"LCOV record {record_no}: {message}")

    for raw in lines:
        if ":" not in raw:
            fail(f"line has no tag: {raw!r}")
        tag, value = raw.split(":", 1)
        if tag not in _KNOWN_TAGS:
            fail(f"unknown line tag: {tag!r}")
        if tag == "TN":
            if tn_seen or sf is not None:
                fail("TN appears more than once or after SF")
            tn_seen = True
        elif tag == "SF":
            if sf is not None:
                fail("duplicate SF in one record")
            _validate_sf_path(value)
            sf = value
        elif tag == "FN":
            if sf is None:
                fail("FN before SF")
            line_no, sep, name = value.partition(",")
            if not sep or not name or not _INT_RE.match(line_no) or int(line_no) < 1:
                fail(f"malformed FN line: {raw!r}")
            fn_count += 1
        elif tag == "FNDA":
            if sf is None:
                fail("FNDA before SF")
            hits, sep, name = value.partition(",")
            if not sep or not name or not _INT_RE.match(hits):
                fail(f"malformed FNDA line: {raw!r}")
            fnda_seen = True
            if int(hits) > 0:
                fnda_hits += 1
        elif tag == "BRDA":
            if sf is None:
                fail("BRDA before SF")
            parts = value.split(",")
            if len(parts) != 4:
                fail(f"malformed BRDA line: {raw!r}")
            line_no, _block, _branch, taken = parts
            if not _INT_RE.match(line_no) or int(line_no) < 1:
                fail(f"malformed BRDA line: {raw!r}")
            if taken != "-" and not _INT_RE.match(taken):
                fail(f"malformed BRDA line: {raw!r}")
            brda_count += 1
            if taken != "-" and int(taken) > 0:
                brda_hits += 1
        elif tag == "DA":
            if sf is None:
                fail("DA before SF")
            parts = value.split(",")
            if len(parts) != 2:
                fail(f"malformed DA line: {raw!r}")
            line_no, hits = parts
            if not _INT_RE.match(line_no) or int(line_no) < 1:
                fail(f"malformed DA line: {raw!r}")
            if not _INT_RE.match(hits):
                fail(f"malformed DA line: {raw!r}")
            if int(line_no) in da:
                fail(f"duplicate DA line number: {line_no}")
            da[int(line_no)] = int(hits)
        else:  # FNF, FNH, BRF, BRH, LF, LH — summary lines.
            if sf is None:
                fail(f"{tag} before SF")
            if tag in summaries:
                fail(f"duplicate {tag} in one record")
            summaries[tag] = _parse_int(value, f"{tag} value")

    if sf is None:
        fail("record has no SF line")

    lines_found = len(da)
    lines_hit = sum(1 for hits in da.values() if hits > 0)
    checks = (
        ("LF", lines_found),
        ("LH", lines_hit),
        ("FNF", fn_count),
        ("BRF", brda_count),
        ("BRH", brda_hits),
    )
    for tag, derived in checks:
        if tag in summaries and summaries[tag] != derived:
            fail(f"{tag} summary ({summaries[tag]}) does not match "
                 f"derived value ({derived})")
    # FNH is checked against the FNDA hit count only when FNDA lines
    # are present. The frozen S0 fixtures carry FN/FNH with no FNDA
    # lines at all (e.g. n08-lcov-only: FN:1,foo + FNH:1, no FNDA), so
    # with no FNDA data there is nothing to check against and the
    # stated FNH is recorded as-is; it is never invented from DA data.
    if fnda_seen and "FNH" in summaries and summaries["FNH"] != fnda_hits:
        fail(f"FNH summary ({summaries['FNH']}) does not match "
             f"derived value ({fnda_hits})")

    return {
        "source_file": sf,
        "lines_found": lines_found,
        "lines_hit": lines_hit,
        "functions_found": summaries.get("FNF", fn_count),
        "functions_hit": summaries.get("FNH", fnda_hits if fnda_seen else 0),
        "branches_found": summaries.get("BRF", brda_count),
        "branches_hit": summaries.get("BRH", brda_hits),
    }


def parse_lcov(path_or_bytes: str | Path | bytes | bytearray) -> dict:
    """Parse an LCOV report into a standardised summary dict.

    ``path_or_bytes`` is a filesystem path (``str``/``Path``) or the raw
    report bytes. Raises :class:`LcovError` (``.code ==
    "LCOV_MALFORMED"``) for oversized, malformed, or path-escaping
    reports. Never returns a guessed summary, and never computes a
    coverage-quality score.
    """
    data = _read_input(path_or_bytes)

    if b"\x00" in data:
        raise LcovError("LCOV report contains a NUL byte")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LcovError(f"LCOV report is not valid UTF-8: {exc}") from exc

    records: list[dict] = []
    current: list[str] = []
    open_record = False
    for raw_line in text.split("\n"):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if line == "":
            continue
        if line == "end_of_record":
            if not open_record:
                raise LcovError("LCOV end_of_record with no open record")
            records.append(_parse_record(current, len(records) + 1))
            current = []
            open_record = False
            continue
        open_record = True
        current.append(line)

    if open_record:
        raise LcovError("LCOV record is not closed by end_of_record")
    if not records:
        raise LcovError("LCOV report contains no records")

    return {
        "files": len(records),
        "lines_found": sum(r["lines_found"] for r in records),
        "lines_hit": sum(r["lines_hit"] for r in records),
        "records": records,
    }
