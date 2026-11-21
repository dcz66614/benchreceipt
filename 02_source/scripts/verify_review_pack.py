"""Validate the P027 T013 review pack (P027-T013-PREP).

Checks, against the frozen candidate commit recorded in
``04_review/REVIEW_INDEX.md``:

1. Every file listed in ``REVIEW_INDEX.md`` and in every
   ``04_review/REVIEW_PACK_*.md`` exists, and its SHA-256 and line
   count match the recorded values. Production files are read from
   the recorded commit (``git show <commit>:<path>``); review-pack
   files and the two pack-check scripts themselves are read from the
   working tree (they are new on the ``t013-prep`` branch and do not
   exist at the frozen commit).
2. Completeness: every key production file in the frozen commit's
   tree (``02_source/src/**/*.py``, ``pyproject.toml``,
   ``schemas/*.json`` (both ``02_source/schemas/`` and
   ``02_source/src/benchreceipt/schemas/``), ``oracle/*``,
   ``examples/github-actions/ci.yml``, and the eight named
   product-adjacent scripts) is listed in at least one review pack.
3. Every ``REVIEW_PACK_*.md`` file on disk is listed in the index,
   and every pack file named in the index exists.

Exit 0 only when all checks pass; otherwise exit 1, listing every
failure. Read-only: never modifies the tree.

Usage (from ``02_source``)::

    python scripts/verify_review_pack.py [--index 04_review/REVIEW_INDEX.md]
        [--pack-glob 'REVIEW_PACK_*.md']

With no options the defaults above apply, i.e. the original T013
pack (``04_review/REVIEW_INDEX.md`` + ``04_review/REVIEW_PACK_*.md``,
anchored at the T013 candidate commit). Point ``--index`` at another
index (e.g. ``04_review/REVIEW_INDEX_FIXR1.md``) and ``--pack-glob``
at its packs (e.g. ``'REVIEW_PACK_FIXR1_*.md'``) to validate a later
review pack against its own anchor commit instead; both paths are
relative to the repository root, and the glob is matched inside
``04_review/``. The schemas key-file rule covers both the original
``02_source/schemas/*.json`` location and the post-T014-F1 location
``02_source/src/benchreceipt/schemas/*.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

# Product-adjacent scripts that count as key production files. The two
# pack-check scripts themselves (this file and
# check_review_coverage.py) are pack tooling, not production code
# under review, and are NOT in this set.
KEY_SCRIPTS = frozenset(
    {
        "02_source/scripts/s0_gate.py",
        "02_source/scripts/repeat_hash.py",
        "02_source/scripts/validate_workflow_example.py",
        "02_source/scripts/offline_check.py",
        "02_source/scripts/performance_smoke.py",
        "02_source/scripts/privacy_scan.py",
        "02_source/scripts/build_fixtures.py",
        "02_source/scripts/ui_smoke.py",
    }
)

# Pack tooling: new on the t013-prep branch, verified against the
# working tree (not the frozen commit, where they do not exist).
PACK_TOOLING = frozenset(
    {
        "02_source/scripts/verify_review_pack.py",
        "02_source/scripts/check_review_coverage.py",
    }
)

# Table rows in the index / packs:
#   | <path> | <64-hex sha256> | <lines> | ...
_ROW_RE = re.compile(
    r"^\|\s*`?(\S+?)`?\s*\|\s*`?([0-9a-f]{64})`?\s*\|\s*(\d+)\s*\|"
)
_COMMIT_RE = re.compile(r"Frozen candidate commit:\s*`([0-9a-f]{40})`")


def repo_root() -> Path:
    """Repository root (parent of the ``02_source`` directory)."""
    return Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        timeout=60,
    )


def _digest_and_lines(data: bytes) -> tuple[str, int]:
    digest = hashlib.sha256(data).hexdigest()
    lines = len(data.decode("utf-8", errors="replace").splitlines())
    return digest, lines


def _parse_table_rows(text: str) -> dict[str, tuple[str, int]]:
    """Map path -> (sha256, lines) for every inventory table row."""
    rows: dict[str, tuple[str, int]] = {}
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
        if match:
            rows[match.group(1)] = (match.group(2), int(match.group(3)))
    return rows


def _is_key_production(path: str) -> bool:
    if path in KEY_SCRIPTS:
        return True
    if path == "02_source/pyproject.toml":
        return True
    if path == "02_source/examples/github-actions/ci.yml":
        return True
    if path.startswith("02_source/src/") and path.endswith(".py"):
        return "__pycache__" not in path and ".egg-info" not in path
    if path.startswith("02_source/schemas/") and path.endswith(".json"):
        return True
    # Schemas moved under src/ in T014-F1; the old location above is
    # kept so packs anchored before the move still validate.
    if path.startswith("02_source/src/benchreceipt/schemas/") and path.endswith(".json"):
        return True
    if path.startswith("02_source/oracle/"):
        return True
    return False


def _key_files_at_commit(root: Path, commit: str) -> list[str]:
    proc = _git(root, "ls-tree", "-r", "--name-only", commit)
    if proc.returncode != 0:
        raise RuntimeError(f"git ls-tree failed for {commit}: {proc.stderr}")
    return sorted(p for p in proc.stdout.splitlines() if _is_key_production(p))


def _check_listed_file(
    root: Path, commit: str, path: str, want_sha: str, want_lines: int,
    failures: list[str],
) -> None:
    """Verify one listed file's SHA-256 + line count."""
    if path.startswith("04_review/") or path in PACK_TOOLING:
        # Pack files / pack tooling: working-tree bytes.
        full = root / path
        if not full.is_file():
            failures.append(f"MISSING (working tree): {path}")
            return
        try:
            data = full.read_bytes()
        except OSError as exc:
            failures.append(f"UNREADABLE (working tree): {path}: {exc}")
            return
    else:
        # Production file: blob at the frozen commit.
        proc = _git_bytes(root, "show", f"{commit}:{path}")
        if proc.returncode != 0:
            failures.append(f"MISSING (at commit {commit[:12]}): {path}")
            return
        data = proc.stdout
    got_sha, got_lines = _digest_and_lines(data)
    if got_sha != want_sha:
        failures.append(
            f"SHA MISMATCH: {path}: recorded {want_sha[:16]}…, "
            f"actual {got_sha[:16]}…"
        )
    if got_lines != want_lines:
        failures.append(
            f"LINE COUNT MISMATCH: {path}: recorded {want_lines}, "
            f"actual {got_lines}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a P027 T013-style review pack."
    )
    parser.add_argument(
        "--index",
        default="04_review/REVIEW_INDEX.md",
        help="review index to validate, relative to the repo root "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--pack-glob",
        default="REVIEW_PACK_*.md",
        help="pack filename glob matched inside 04_review/ "
        "(default: %(default)s)",
    )
    args = parser.parse_args(argv)
    root = repo_root()
    review_dir = root / "04_review"
    failures: list[str] = []
    index_path = root / args.index
    if not index_path.is_file():
        print(f"FAIL: {args.index} is missing")
        return 1
    index_text = index_path.read_text(encoding="utf-8")
    commit_match = _COMMIT_RE.search(index_text)
    if not commit_match:
        print(f"FAIL: {index_path.name} records no frozen candidate commit")
        return 1
    commit = commit_match.group(1)
    proc = _git(root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    if proc.returncode != 0:
        print(f"FAIL: recorded commit {commit} does not exist in this repo")
        return 1

    index_rows = _parse_table_rows(index_text)
    if not index_rows:
        print("FAIL: REVIEW_INDEX.md contains no inventory table rows")
        return 1

    # 1a. Every file listed in the index.
    for path, (sha, lines) in sorted(index_rows.items()):
        _check_listed_file(root, commit, path, sha, lines, failures)

    # 1b. Every file listed in every pack; collect pack coverage.
    pack_files = sorted(review_dir.glob(args.pack_glob))
    if not pack_files:
        failures.append(
            f"MISSING: no 04_review/{args.pack_glob} files found"
        )
    pack_listed: dict[str, list[str]] = {}
    for pack_path in pack_files:
        pack_rows = _parse_table_rows(
            pack_path.read_text(encoding="utf-8")
        )
        if not pack_rows:
            failures.append(f"EMPTY PACK (no inventory rows): {pack_path.name}")
        for path, (sha, lines) in sorted(pack_rows.items()):
            pack_listed.setdefault(path, []).append(pack_path.name)
            _check_listed_file(root, commit, path, sha, lines, failures)

    # 2. Completeness: every key production file at the frozen commit
    #    is listed in at least one pack.
    try:
        key_files = _key_files_at_commit(root, commit)
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1
    unlisted = [p for p in key_files if p not in pack_listed]
    for path in unlisted:
        failures.append(f"UNLISTED KEY FILE (in no pack): {path}")

    # 3. Every pack file on disk is listed in the index.
    for pack_path in pack_files:
        rel = f"04_review/{pack_path.name}"
        if rel not in index_rows:
            failures.append(f"PACK NOT LISTED IN INDEX: {rel}")

    n_index = len(index_rows)
    n_pack_rows = sum(
        len(_parse_table_rows(p.read_text(encoding="utf-8")))
        for p in pack_files
    )
    if failures:
        print(f"FAIL: verify_review_pack: {len(failures)} problem(s)")
        for failure in failures:
            print(f"  - {failure}")
        print(
            f"  (index rows: {n_index}; pack rows: {n_pack_rows}; "
            f"key production files at {commit[:12]}: {len(key_files)}; "
            f"packs: {len(pack_files)})"
        )
        return 1
    print(
        f"PASS: verify_review_pack: commit {commit}, "
        f"{n_index} index rows, {n_pack_rows} pack rows, "
        f"{len(key_files)} key production files all listed in "
        f"{len(pack_files)} pack(s), all SHA-256 + line counts match"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
