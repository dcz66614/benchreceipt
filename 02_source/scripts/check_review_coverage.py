"""Validate a T013 review-coverage table (P027-T013-PREP).

The reviewer produces ``04_review/REVIEW_COVERAGE.csv`` after
reviewing the frozen candidate. This script checks that every key
production file recorded in ``04_review/REVIEW_INDEX.md`` (the
inventory rows flagged ``Key = yes``) appears in the coverage table
with a positive ``reviewed`` flag.

Expected CSV format (header row required)::

    file,reviewed,pack,notes
    02_source/src/benchreceipt/verify.py,yes,02,...

``file`` and ``reviewed`` columns are required; ``pack`` / ``notes``
are optional and ignored. ``reviewed`` counts as reviewed when it
is (case-insensitive) one of ``yes``, ``true``, ``1``, ``y``, ``x``.

Exit 0 only when every key file is covered and reviewed; otherwise
exit 1, listing each missing or unreviewed file. Read-only: never
modifies the tree or the CSV.

Usage::

    python scripts/check_review_coverage.py [coverage.csv]
        [--index 04_review/REVIEW_INDEX.md]
        [--pack-glob 'REVIEW_PACK_*.md']

With no argument the default is ``04_review/REVIEW_COVERAGE.csv``
(the file the reviewer produces; it is NOT committed by the pack
builder). A path in ``/tmp`` (e.g. a synthetic test CSV) works the
same way.

``--index`` selects which review index supplies the key-file list
(default ``04_review/REVIEW_INDEX.md``); when no coverage CSV is
given, its default is derived from the index name by replacing
``INDEX`` with ``COVERAGE`` (``REVIEW_INDEX_FIXR1.md`` pairs with
``REVIEW_COVERAGE_FIXR1.csv``). ``--pack-glob`` is accepted for a
uniform validator CLI with ``verify_review_pack.py``; coverage is
per-index, not per-pack, so the value is ignored.

Two coverage CSV formats are accepted. The standard format has
``file`` / ``reviewed`` columns (above). The FIXR1 format has
``path_at_66502f6`` / ``key`` columns instead; a row counts as
reviewed when ``key`` is ``yes`` (every row of that table is a file
the reviewer covered, in the pack named by its ``pack`` column).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REVIEWED_VALUES = {"yes", "true", "1", "y", "x"}

# Inventory table rows in REVIEW_INDEX.md:
#   | <path> | <sha256> | <lines> | <pack(s)> | <key yes/no> | ...
_INDEX_ROW_RE = re.compile(
    r"^\|\s*`?(\S+?)`?\s*\|\s*`?[0-9a-f]{64}`?\s*\|\s*\d+\s*\|[^|]*\|\s*(yes|no)\s*\|"
)


def repo_root() -> Path:
    """Repository root (parent of the ``02_source`` directory)."""
    return Path(__file__).resolve().parents[2]


def _key_files_from_index(index_text: str) -> list[str]:
    key_files: list[str] = []
    for line in index_text.splitlines():
        match = _INDEX_ROW_RE.match(line.strip())
        if match and match.group(2) == "yes":
            key_files.append(match.group(1))
    return sorted(set(key_files))


def _reviewed_from_rows(rows: list[dict[str, str | None]]) -> set[str] | None:
    """Reviewed file names from coverage CSV rows, or None if the
    columns are not a format this script understands.

    Standard format: ``file`` + ``reviewed`` columns. FIXR1 format:
    ``path_at_66502f6`` + ``key`` columns, where ``key == yes``
    counts as reviewed (see module docstring).
    """
    fieldnames = rows[0].keys() if rows else []
    if "file" in (fieldnames or []) and "reviewed" in (fieldnames or []):
        reviewed: set[str] = set()
        for row in rows:
            name = (row.get("file") or "").strip()
            flag = (row.get("reviewed") or "").strip().lower()
            if name and flag in REVIEWED_VALUES:
                reviewed.add(name)
        return reviewed
    if "path_at_66502f6" in (fieldnames or []) and "key" in (fieldnames or []):
        return {
            (row.get("path_at_66502f6") or "").strip()
            for row in rows
            if (row.get("path_at_66502f6") or "").strip()
            and (row.get("key") or "").strip().lower() in REVIEWED_VALUES
        }
    return None


def _default_coverage_path(index_path: Path) -> Path:
    """Coverage CSV paired with an index: REVIEW_INDEX*.md ->
    REVIEW_COVERAGE*.csv in the same directory."""
    return index_path.with_name(
        index_path.stem.replace("INDEX", "COVERAGE") + ".csv"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a T013 review-coverage table."
    )
    parser.add_argument(
        "coverage",
        nargs="?",
        default=None,
        help="coverage CSV (default: derived from --index, "
        "REVIEW_INDEX*.md -> REVIEW_COVERAGE*.csv)",
    )
    parser.add_argument(
        "--index",
        default="04_review/REVIEW_INDEX.md",
        help="review index supplying the key-file list, relative to "
        "the repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--pack-glob",
        default="REVIEW_PACK_*.md",
        help="accepted for a uniform CLI with verify_review_pack.py; "
        "ignored (coverage is per-index, not per-pack)",
    )
    args = parser.parse_args(argv)
    root = repo_root()
    index_path = root / args.index
    csv_path = (
        Path(args.coverage)
        if args.coverage
        else _default_coverage_path(index_path)
    )
    if not index_path.is_file():
        print(f"FAIL: {args.index} is missing")
        return 1
    key_files = _key_files_from_index(
        index_path.read_text(encoding="utf-8")
    )
    if not key_files:
        print(f"FAIL: {index_path.name} lists no key (Key = yes) files")
        return 1
    if not csv_path.is_file():
        print(f"FAIL: coverage file is missing: {csv_path}")
        print(f"  ({len(key_files)} key files would be uncovered)")
        return 1
    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        print(f"FAIL: cannot read coverage CSV {csv_path}: {exc}")
        return 1
    if not rows:
        print(f"FAIL: coverage CSV {csv_path} has no data rows")
        return 1
    fieldnames = rows[0].keys() if rows else []
    reviewed = _reviewed_from_rows(rows)
    if reviewed is None:
        print(
            "FAIL: coverage CSV needs 'file' and 'reviewed' columns "
            "(or 'path_at_66502f6' and 'key' columns); "
            f"found: {sorted(fieldnames or [])}"
        )
        return 1
    missing = [p for p in key_files if p not in reviewed]
    if missing:
        print(
            f"FAIL: check_review_coverage: {len(missing)} of "
            f"{len(key_files)} key file(s) missing or unreviewed in "
            f"{csv_path}"
        )
        for path in missing:
            print(f"  - {path}")
        return 1
    print(
        f"PASS: check_review_coverage: all {len(key_files)} key "
        f"production files reviewed in {csv_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
