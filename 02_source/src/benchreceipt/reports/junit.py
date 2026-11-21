"""Safe JUnit XML parsing (P027-T005, PROJECT_BOOK §5.4 and §11).

Produces a standardised summary::

    parse_junit(path_or_bytes) -> {
        "tests": int,            # == testcase_count, always the counted value
        "failures": int,         # counted <failure> elements
        "errors": int,           # counted <error> elements
        "skipped": int,          # counted <skipped> elements
        "testcase_count": int,   # counted <testcase> elements
        "suites": int,           # number of <testsuite> elements
    }

Rules (fail-closed; uncertainty returns INVALID, never a lenient guess):

- The counted elements are the truth. A ``tests`` / ``failures`` /
  ``errors`` / ``skipped`` attribute, when present on a ``<testsuite>``
  (or on a ``<testsuites>`` wrapper), must equal the counted value for
  that element; any mismatch raises :class:`JUnitError`. The attribute
  is never silently trusted. When no attribute is present the count is
  derived from the elements.
- ``tests == 0`` (or no ``<testcase>`` at all) parses successfully and
  returns ``tests == 0``; it is the *verifier's* job to map that to
  ``JUNIT_EMPTY`` (never PASS). This parser does not decide pass/fail.
- Any ``<!DOCTYPE ...>`` or ``<!ENTITY ...>`` declaration is rejected
  before parsing, so no DTD is ever processed and no external entity is
  ever resolved. ``xml.etree.ElementTree`` does not resolve external
  entities by itself, but rejecting the declaration outright also rules
  out internal-entity expansion tricks; a real JUnit producer never
  emits a DOCTYPE.
- The file size limit is the frozen schema limit
  (``src/benchreceipt/schemas/README.md``: ``reports[].size_bytes`` <= 1 GiB). The size
  is checked with ``stat`` before the file is read, and again after
  reading, so an oversized file is rejected without being loaded.
- Anything else unparsable — malformed XML, a wrong root element, a
  non-integer count attribute, a missing/unreadable file — raises
  :class:`JUnitError` with ``.code == "JUNIT_MALFORMED"`` (the frozen
  reason code in ``docs/REASON_CODES.md``).

Standard library only (``xml.etree.ElementTree``). No network access,
no file access outside the one file given.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

__all__ = ["JUnitError", "MAX_JUNIT_BYTES", "parse_junit"]

# Frozen schema limit: reports[].size_bytes <= 1 GiB (src/benchreceipt/schemas/README.md,
# ADR-001 decision 5). Enforced here so an oversized report can never
# reach the XML parser.
MAX_JUNIT_BYTES = 1073741824

_COUNT_ATTRS = ("tests", "failures", "errors", "skipped")
_INT_RE = re.compile(r"[0-9]+\Z")
# Byte-level pre-scan: any DOCTYPE or ENTITY declaration is rejected
# before ElementTree ever sees the document.
_DOCTYPE_RE = re.compile(rb"<!doctype", re.IGNORECASE)
_ENTITY_RE = re.compile(rb"<!entity", re.IGNORECASE)


class JUnitError(ValueError):
    """A JUnit report that cannot be trusted as parsed.

    Carries ``.code`` — a frozen reason code from
    ``docs/REASON_CODES.md``. Every failure raised by this module uses
    ``"JUNIT_MALFORMED"``: the verifier maps it to ``INVALID``.
    """

    def __init__(self, message: str, code: str = "JUNIT_MALFORMED") -> None:
        self.code = code
        super().__init__(message)


def _read_input(path_or_bytes: str | Path | bytes | bytearray) -> bytes:
    """Return the report bytes, enforcing the size limit first."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
        if len(data) > MAX_JUNIT_BYTES:
            raise JUnitError(
                f"JUnit report exceeds size limit of {MAX_JUNIT_BYTES} bytes"
            )
        return data
    if isinstance(path_or_bytes, (str, Path)):
        path = Path(path_or_bytes)
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise JUnitError(f"JUnit report is unreadable: {path}: {exc}") from exc
        if size > MAX_JUNIT_BYTES:
            raise JUnitError(
                f"JUnit report exceeds size limit of {MAX_JUNIT_BYTES} bytes"
            )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise JUnitError(f"JUnit report is unreadable: {path}: {exc}") from exc
        if len(data) > MAX_JUNIT_BYTES:
            raise JUnitError(
                f"JUnit report exceeds size limit of {MAX_JUNIT_BYTES} bytes"
            )
        return data
    raise TypeError(
        "parse_junit expects a path (str/Path) or bytes, "
        f"got {type(path_or_bytes).__name__}"
    )


def _local(tag: str) -> str:
    """Local name of a possibly namespaced element tag."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _check_count_attrs(elem: Any, counted: dict[str, int], where: str) -> None:
    """A present count attribute must equal the counted value."""
    for attr in _COUNT_ATTRS:
        raw = elem.get(attr)
        if raw is None:
            continue
        if not _INT_RE.match(raw):
            raise JUnitError(
                f"JUnit {where} has a non-integer {attr} attribute: {raw!r}"
            )
        if int(raw) != counted[attr]:
            raise JUnitError(
                f"JUnit {where} {attr} attribute ({raw}) does not match "
                f"counted {attr} ({counted[attr]})"
            )


def _count_suite(suite: Any) -> dict[str, int]:
    """Count testcases/failures/errors/skipped under one <testsuite>."""
    counted = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for elem in suite.iter():
        name = _local(elem.tag)
        if name == "testcase":
            counted["tests"] += 1
        elif name == "failure":
            counted["failures"] += 1
        elif name == "error":
            counted["errors"] += 1
        elif name == "skipped":
            counted["skipped"] += 1
    return counted


def parse_junit(path_or_bytes: str | Path | bytes | bytearray) -> dict[str, int]:
    """Parse a JUnit XML report into a standardised summary dict.

    ``path_or_bytes`` is a filesystem path (``str``/``Path``) or the raw
    report bytes. Raises :class:`JUnitError` (``.code ==
    "JUNIT_MALFORMED"``) for oversized, malformed, DTD-bearing, or
    internally inconsistent reports. Never returns a guessed summary.
    """
    data = _read_input(path_or_bytes)

    if _DOCTYPE_RE.search(data) or _ENTITY_RE.search(data):
        raise JUnitError(
            "JUnit XML contains a DOCTYPE or ENTITY declaration; "
            "DTD processing is disabled"
        )

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise JUnitError(f"JUnit XML is malformed: {exc}") from exc

    root_name = _local(root.tag)
    if root_name == "testsuite":
        suites = [root]
    elif root_name == "testsuites":
        suites = [child for child in root if _local(child.tag) == "testsuite"]
        if not suites:
            raise JUnitError("JUnit <testsuites> contains no <testsuite>")
    else:
        raise JUnitError(f"JUnit root element is <{root_name}>, not <testsuite>")

    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        counted = _count_suite(suite)
        _check_count_attrs(suite, counted, "<testsuite>")
        for key in total:
            total[key] += counted[key]

    if root_name == "testsuites":
        _check_count_attrs(root, total, "<testsuites>")

    return {
        "tests": total["tests"],
        "failures": total["failures"],
        "errors": total["errors"],
        "skipped": total["skipped"],
        "testcase_count": total["tests"],
        "suites": len(suites),
    }
