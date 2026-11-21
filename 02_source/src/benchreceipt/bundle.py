"""Artifact bundle + SHA-256 (P027-T006).

Safely packages per-job receipts + reports (a ``.benchreceipt/evidence``
tree, PROJECT_BOOK §6.1) into a portable evidence directory whose
contents are verifiable by hash, and verifies such a bundle.

Manifest format decision (frozen by this task; see also
``02_source/docs/BUNDLE_FORMAT.md``)
---------------------------------------------------------------
ONE manifest file, ``SHA256SUMS.txt`` at the bundle root, one line per
bundled file (excluding the manifest itself), sorted by POSIX relative
path, LF line endings, one trailing newline per line::

    <sha256-hex> <size-bytes-decimal> <relative-posix-path>

e.g. ``e3b0c442...  0  unit-linux-py312/receipt.json`` — fields are
separated by exactly one ASCII space; the path is the remainder of the
line after the second space (paths therefore may contain spaces, but
never a newline). This is a *single-file* manifest: sizes live in the
size column, so there is no companion ``MANIFEST.json`` to drift out
of sync with ``SHA256SUMS.txt``. Note the format is deliberately NOT
byte-compatible with stock ``sha256sum -c`` output (which has no size
column); verify bundles with :func:`verify_bundle`, not ``sha256sum``.

Layout
------
``build_bundle(evidence_dir, out_dir)`` copies the evidence tree
verbatim (job-id subdirs, ``receipt.json`` + ``artifacts/``) into
``out_dir`` and writes ``SHA256SUMS.txt`` there. ``verify_bundle``
re-reads every file, recomputes SHA-256 + size, compares against the
manifest, AND cross-checks each job receipt's recorded report hashes
against freshly recomputed digests (PROJECT_BOOK §5.4: re-read +
recompute at verify time, never trust a stored digest).

Fail-closed rules (PROJECT_BOOK §11.2)
----------------------------------------
- Any symlink anywhere in the source tree → :class:`BundleError` at
  build time (refused, never followed); any symlink found in a bundle
  at verify time → ``BUNDLE_UNSUPPORTED_SYMLINK`` problem, never
  followed.
- Manifest entries (or receipt report paths) that are absolute, contain
  a ``..`` segment, a backslash, or escape the bundle root → rejected
  (``BUNDLE_PATH_ESCAPE`` in the manifest case; the verifier's
  ``REPORT_HASH_MISMATCH`` for receipt report paths, matching
  :mod:`benchreceipt.verify`).
- Missing file / hash mismatch / size mismatch / extra unlisted file /
  malformed manifest / receipt digest disagreement → ``ok=False``,
  never a pass. Tampering with one byte after bundling is detected.
- Size limits (consistent with the frozen schema, ADR-001 decision 5
  and ``capture``/``reports``): one file at most 1 GiB
  (``MAX_FILE_BYTES``), a bundle at most 10,000 files
  (``MAX_BUNDLE_FILES``) and 10 GiB total (``MAX_BUNDLE_BYTES``).
  Exceeding a limit at build time raises :class:`BundleError`; at
  verify time it is a ``BUNDLE_LIMIT_EXCEEDED`` problem and the
  over-limit file is not hashed (its bytes are not trusted anyway).
- ``build_bundle`` refuses a non-empty ``out_dir`` (stale content must
  never silently merge into a fresh bundle) and refuses an
  ``evidence_dir`` that already contains a root-level ``SHA256SUMS.txt``
  (the manifest would be ambiguous).
- A directory that is not a bundle at all (missing, not a directory, or
  no ``SHA256SUMS.txt``) raises :class:`BundleError` from both entry
  points — it is a structural error, not a verifiable mismatch.

Reason codes: manifest/file-level problems use ``BUNDLE_*`` codes
documented in ``BUNDLE_FORMAT.md``; receipt report cross-checks reuse
the frozen verifier vocabulary (``REPORT_MISSING``,
``REPORT_HASH_MISMATCH``, ``INVALID_RECEIPT``) from
``02_source/docs/REASON_CODES.md`` so the two checkers agree on what a
report problem is called. No new verify reason code is invented here.

Library only: T008 owns ``cli.py`` and wires the ``bundle``
subcommand. No CLI, no network, standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "BundleError",
    "BundleProblem",
    "BundleResult",
    "MAX_BUNDLE_BYTES",
    "MAX_BUNDLE_FILES",
    "MAX_FILE_BYTES",
    "build_bundle",
    "verify_bundle",
]

MANIFEST_NAME = "SHA256SUMS.txt"
RECEIPT_NAME = "receipt.json"

# Frozen schema limit (ADR-001 decision 5; run.v1.json size_bytes max;
# capture._MAX_REPORT_BYTES; reports MAX_JUNIT_BYTES / MAX_LCOV_BYTES).
MAX_FILE_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB per file.
# Bundle-level caps: generous enough that no realistic evidence bundle
# hits them (48-job S0 bundles are ~tens of files), tight enough to
# bound untrusted input (PROJECT_BOOK §11.2).
MAX_BUNDLE_FILES = 10_000
MAX_BUNDLE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GiB total.

_CHUNK = 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Manifest line: "<sha256> <size> <rel-posix-path>" — exactly one space
# between the first two fields; the path is the rest of the line.
_MANIFEST_LINE_RE = re.compile(r"^([0-9a-f]{64}) ([0-9]+) (.+)$")

# Problem codes (see BUNDLE_FORMAT.md for the full table).
CODE_MISSING_FILE = "BUNDLE_MISSING_FILE"
CODE_HASH_MISMATCH = "BUNDLE_HASH_MISMATCH"
CODE_SIZE_MISMATCH = "BUNDLE_SIZE_MISMATCH"
CODE_EXTRA_FILE = "BUNDLE_EXTRA_FILE"
CODE_PATH_ESCAPE = "BUNDLE_PATH_ESCAPE"
CODE_UNSUPPORTED_SYMLINK = "BUNDLE_UNSUPPORTED_SYMLINK"
CODE_MANIFEST_MALFORMED = "BUNDLE_MANIFEST_MALFORMED"
CODE_LIMIT_EXCEEDED = "BUNDLE_LIMIT_EXCEEDED"


class BundleError(RuntimeError):
    """Structurally invalid bundle input or an unsafe build request.

    Raised (not returned as a problem) when the input is not a bundle
    dir at all, when a build request is unsafe (symlink, path escape,
    size/count limit, non-empty output dir), or when the manifest
    cannot be read. A *tampered* bundle, by contrast, is reported via
    :class:`BundleResult` problems with ``ok=False``.
    """


@dataclass(frozen=True)
class BundleProblem:
    """One verification finding: ``{code, path, message}``."""

    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class BundleResult:
    """Outcome of :func:`verify_bundle`.

    ``ok`` is True only when ``problems`` is empty. ``problems`` is a
    list of ``{code, path, message}`` dicts, sorted deterministically
    by ``(path, code)``. ``files_checked`` counts real files hashed on
    disk (excluding the manifest itself); ``manifest_files`` counts
    entries listed in the manifest.
    """

    ok: bool
    problems: list[dict[str, str]] = field(default_factory=list)
    files_checked: int = 0
    manifest_files: int = 0


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------


def _is_within_root(root: Path, path: Path) -> bool:
    """True iff ``path`` (resolved) stays inside ``root`` (resolved)."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _validate_rel_posix(rel: str) -> str | None:
    """Return an error reason if ``rel`` is not a safe relative POSIX path.

    Rejects: empty, absolute (leading ``/`` or a Windows drive ``C:``),
    ``.`` / ``..`` segments, empty segments (``//``), trailing slash,
    backslashes, NUL. Returns None when the path is safe.
    """
    if not rel:
        return "empty relative path"
    if rel.startswith("/") or rel.startswith("\\"):
        return f"absolute path {rel!r}"
    if len(rel) >= 2 and rel[1] == ":" and rel[0].isalpha():
        return f"absolute (drive-letter) path {rel!r}"
    if "\\" in rel:
        return f"backslash in path {rel!r}"
    if "\x00" in rel:
        return f"NUL byte in path {rel!r}"
    if rel in (".", ".."):
        return f"unsafe path {rel!r}"
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return f"unsafe path {rel!r}"
    return None


def _safe_join(root: Path, rel: str) -> Path:
    """Join ``rel`` onto ``root`` after validation; raise BundleError."""
    reason = _validate_rel_posix(rel)
    if reason is not None:
        raise BundleError(f"unsafe bundle path: {reason}")
    target = root / rel
    if not _is_within_root(root, target):
        raise BundleError(f"path escapes bundle root: {rel!r}")
    return target


def _hash_file(path: Path) -> tuple[int, str]:
    """Streamed ``(size_bytes, sha256_hex)`` of a file's exact bytes.

    Same semantics as ``capture._hash_file`` (single streamed pass,
    1 MiB chunks); the helpers are intentionally identical so a digest
    computed at capture time, at bundle time, and at verify time agree
    byte for byte.
    """
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


# ---------------------------------------------------------------------------
# build_bundle
# ---------------------------------------------------------------------------


def build_bundle(evidence_dir: str | Path, out_dir: str | Path) -> dict[str, object]:
    """Copy an evidence tree into a portable bundle dir + manifest.

    ``evidence_dir`` is a ``.benchreceipt/evidence`` tree (one subdir
    per job, each with ``receipt.json`` + ``artifacts/``). ``out_dir``
    is created; it must not exist non-empty, must not be inside
    ``evidence_dir``, and ``evidence_dir`` must not be inside it.

    Returns a manifest summary dict::

        {"files": <int>, "total_bytes": <int>,
         "sha256": <sha256 of SHA256SUMS.txt bytes>,
         "out_dir": <str path>, "manifest": "SHA256SUMS.txt"}

    Raises :class:`BundleError` on any structural or safety problem:
    missing/non-directory evidence dir, symlink anywhere in the tree,
    a file over 1 GiB, over 10,000 files / 10 GiB total, an unsafe
    relative path, a root-level ``SHA256SUMS.txt`` already present in
    the evidence tree, or a non-empty / overlapping ``out_dir``.
    """
    src_root = Path(evidence_dir)
    dst_root = Path(out_dir)
    if not src_root.is_dir():
        raise BundleError(
            f"evidence directory is missing or not a directory: {src_root}"
        )
    try:
        src_resolved = src_root.resolve()
        dst_resolved = dst_root.resolve()
    except OSError as exc:
        raise BundleError(f"cannot resolve bundle paths: {exc}") from exc
    if src_resolved == dst_resolved:
        raise BundleError("evidence_dir and out_dir are the same directory")
    if dst_resolved.is_relative_to(src_resolved) or src_resolved.is_relative_to(
        dst_resolved
    ):
        raise BundleError("evidence_dir and out_dir must not contain each other")
    if dst_root.exists():
        if not dst_root.is_dir():
            raise BundleError(f"out_dir exists and is not a directory: {dst_root}")
        if any(dst_root.iterdir()):
            raise BundleError(
                f"out_dir is not empty, refusing to merge into stale content: {dst_root}"
            )
    if (src_root / MANIFEST_NAME).exists():
        raise BundleError(
            f"evidence tree already contains a root-level {MANIFEST_NAME}; "
            "refusing to bundle an ambiguous manifest"
        )

    # Collect real files first (fail before copying anything).
    entries: list[tuple[str, Path]] = []  # (posix rel path, source path)
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(src_root, followlinks=False):
        dirpath_p = Path(dirpath)
        # Symlinked directories are never followed; refuse outright.
        for dirname in sorted(dirnames):
            if (dirpath_p / dirname).is_symlink():
                raise BundleError(
                    "unsupported symlink in evidence tree: "
                    f"{(dirpath_p / dirname).relative_to(src_root).as_posix()!r} "
                    "(symlinks are never followed)"
                )
        for filename in sorted(filenames):
            fpath = dirpath_p / filename
            if fpath.is_symlink():
                raise BundleError(
                    "unsupported symlink in evidence tree: "
                    f"{fpath.relative_to(src_root).as_posix()!r} "
                    "(symlinks are never followed)"
                )
            rel = fpath.relative_to(src_root).as_posix()
            reason = _validate_rel_posix(rel)
            if reason is not None:
                raise BundleError(f"unsafe path in evidence tree: {reason}")
            if not _is_within_root(src_root, fpath):
                raise BundleError(f"path escapes evidence root: {rel!r}")
            entries.append((rel, fpath))

    entries.sort(key=lambda item: item[0])
    if len(entries) > MAX_BUNDLE_FILES:
        raise BundleError(
            f"bundle file count {len(entries)} exceeds the limit of "
            f"{MAX_BUNDLE_FILES}"
        )

    dst_root.mkdir(parents=True, exist_ok=True)
    manifest_lines: list[str] = []
    try:
        for rel, fpath in entries:
            size, digest = _hash_file(fpath)
            if size > MAX_FILE_BYTES:
                raise BundleError(
                    f"file {rel!r} is {size} bytes, exceeding the 1 GiB "
                    "per-file limit"
                )
            total_bytes += size
            if total_bytes > MAX_BUNDLE_BYTES:
                raise BundleError(
                    f"bundle total size exceeds the limit of "
                    f"{MAX_BUNDLE_BYTES} bytes"
                )
            dest = dst_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fpath, dest)
            # Re-hash the copied bytes: the manifest describes the
            # bundle on disk, not the source tree.
            copied_size, copied_digest = _hash_file(dest)
            if copied_size != size or copied_digest != digest:
                raise BundleError(
                    f"copy verification failed for {rel!r}: copied bytes "
                    "differ from source"
                )
            manifest_lines.append(f"{digest} {size} {rel}")
    except BundleError:
        # A failed build must not leave a half-written bundle behind
        # that a later verify could mistake for a real one.
        shutil.rmtree(dst_root, ignore_errors=True)
        raise

    manifest_bytes = "".join(line + "\n" for line in manifest_lines).encode("utf-8")
    manifest_path = dst_root / MANIFEST_NAME
    manifest_path.write_bytes(manifest_bytes)
    return {
        "files": len(entries),
        "total_bytes": total_bytes,
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "out_dir": str(dst_root),
        "manifest": MANIFEST_NAME,
    }


# ---------------------------------------------------------------------------
# verify_bundle
# ---------------------------------------------------------------------------


def _parse_manifest(
    manifest_bytes: bytes,
) -> tuple[dict[str, tuple[str, int]], list[BundleProblem]]:
    """Parse ``SHA256SUMS.txt`` bytes.

    Returns ``(entries, problems)`` where ``entries`` maps a safe
    relative POSIX path to ``(sha256, size_bytes)``. Malformed lines,
    duplicate entries, unsafe paths, and an entry naming the manifest
    itself are reported as problems (never raised, never silently
    skipped) so a tampered manifest is fail-closed, not fatal.
    """
    entries: dict[str, tuple[str, int]] = {}
    problems: list[BundleProblem] = []
    try:
        text = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(
            BundleProblem(
                CODE_MANIFEST_MALFORMED,
                MANIFEST_NAME,
                "manifest is not valid UTF-8",
            )
        )
        return entries, problems
    if "\r" in text:
        problems.append(
            BundleProblem(
                CODE_MANIFEST_MALFORMED,
                MANIFEST_NAME,
                "manifest contains CR characters (expected LF line endings)",
            )
        )
    for lineno, line in enumerate(text.split("\n"), start=1):
        if lineno == len(text.split("\n")) and line == "":
            continue  # trailing newline after the last entry
        if line == "":
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    f"manifest line {lineno} is empty",
                )
            )
            continue
        match = _MANIFEST_LINE_RE.match(line)
        if not match:
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    f"manifest line {lineno} does not match "
                    "'<sha256> <size> <relative-path>'",
                )
            )
            continue
        digest, size_text, rel = match.groups()
        if rel == MANIFEST_NAME:
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    "manifest lists itself; the manifest is never a listed file",
                )
            )
            continue
        reason = _validate_rel_posix(rel)
        if reason is not None:
            problems.append(
                BundleProblem(
                    CODE_PATH_ESCAPE,
                    rel,
                    f"manifest entry has an unsafe path: {reason}",
                )
            )
            continue
        if rel in entries:
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    f"manifest lists {rel!r} more than once",
                )
            )
            continue
        entries[rel] = (digest, int(size_text))
    return entries, problems


def _check_receipt_reports(
    bundle_root: Path,
    job_dir: Path,
    receipt_rel: str,
    problems: list[BundleProblem],
) -> None:
    """Cross-check one job receipt's recorded report digests (§5.4).

    Re-reads each listed report file and recomputes size + SHA-256 from
    its actual bytes; compares against the receipt's recorded values.
    Appends frozen verifier codes (``REPORT_MISSING`` /
    ``REPORT_HASH_MISMATCH`` / ``INVALID_RECEIPT``) to ``problems``.
    A receipt that is not JSON, not an object, or has a malformed
    ``reports`` list is ``INVALID_RECEIPT``; the check never raises.
    """
    receipt_path = bundle_root / receipt_rel
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        problems.append(
            BundleProblem(
                "INVALID_RECEIPT",
                receipt_rel,
                "receipt is not valid benchreceipt.run/v1",
            )
        )
        return
    if not isinstance(data, dict):
        problems.append(
            BundleProblem(
                "INVALID_RECEIPT",
                receipt_rel,
                "receipt is not valid benchreceipt.run/v1",
            )
        )
        return
    reports = data.get("reports")
    if reports is None:
        # A receipt with no reports list at all cannot bind any report;
        # the schema makes reports required, so this is invalid.
        problems.append(
            BundleProblem(
                "INVALID_RECEIPT",
                receipt_rel,
                "receipt is not valid benchreceipt.run/v1",
            )
        )
        return
    if not isinstance(reports, list):
        problems.append(
            BundleProblem(
                "INVALID_RECEIPT",
                receipt_rel,
                "receipt is not valid benchreceipt.run/v1",
            )
        )
        return
    for rep in reports:
        if not isinstance(rep, dict):
            problems.append(
                BundleProblem(
                    "INVALID_RECEIPT",
                    receipt_rel,
                    "receipt is not valid benchreceipt.run/v1",
                )
            )
            continue
        rel = rep.get("path")
        size = rep.get("size_bytes")
        digest = rep.get("sha256")
        if (
            not isinstance(rel, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not isinstance(digest, str)
            or not _SHA256_RE.match(digest)
        ):
            problems.append(
                BundleProblem(
                    "INVALID_RECEIPT",
                    receipt_rel,
                    "receipt is not valid benchreceipt.run/v1",
                )
            )
            continue
        reason = _validate_rel_posix(rel)
        if reason is not None:
            problems.append(
                BundleProblem(
                    "REPORT_HASH_MISMATCH",
                    rel,
                    f"report digest mismatch: {rel}",
                )
            )
            continue
        target = job_dir / rel
        if not _is_within_root(job_dir, target):
            problems.append(
                BundleProblem(
                    "REPORT_HASH_MISMATCH",
                    rel,
                    f"report digest mismatch: {rel}",
                )
            )
            continue
        if target.is_symlink() or not target.is_file():
            problems.append(
                BundleProblem(
                    "REPORT_MISSING",
                    rel,
                    f"report file missing: {rel}",
                )
            )
            continue
        try:
            actual_size, actual_digest = _hash_file(target)
        except OSError:
            problems.append(
                BundleProblem(
                    "REPORT_MISSING",
                    rel,
                    f"report file missing: {rel}",
                )
            )
            continue
        if actual_size != size or actual_digest != digest:
            problems.append(
                BundleProblem(
                    "REPORT_HASH_MISMATCH",
                    rel,
                    f"report digest mismatch: {rel}",
                )
            )


def verify_bundle(bundle_dir: str | Path) -> BundleResult:
    """Verify a portable evidence bundle.

    Re-reads every file, recomputes SHA-256 + size, compares against
    ``SHA256SUMS.txt`` and against each job receipt's recorded report
    hashes. Returns a :class:`BundleResult` (``ok`` is True only when
    no problem is found). Problems cover: missing file, hash mismatch,
    size mismatch, extra unlisted file, path escape, unsupported
    symlink, malformed manifest, over-limit file, and receipt report
    mismatches.

    Raises :class:`BundleError` only when the input is not a bundle
    dir at all (missing / not a directory / no ``SHA256SUMS.txt``).
    A tampered bundle is a result with problems, never an exception.
    """
    root = Path(bundle_dir)
    if not root.is_dir():
        raise BundleError(
            f"bundle directory is missing or not a directory: {root}"
        )
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise BundleError(
            f"not a bundle directory (no {MANIFEST_NAME}): {root}"
        )

    problems: list[BundleProblem] = []
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise BundleError(f"cannot read manifest {manifest_path}: {exc}") from exc
    entries, manifest_problems = _parse_manifest(manifest_bytes)
    problems.extend(manifest_problems)

    # Walk the bundle (never following symlinks) and check every file.
    found: dict[str, Path] = {}
    files_checked = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirpath_p = Path(dirpath)
        for dirname in sorted(dirnames):
            child = dirpath_p / dirname
            rel = child.relative_to(root).as_posix()
            if child.is_symlink():
                problems.append(
                    BundleProblem(
                        CODE_UNSUPPORTED_SYMLINK,
                        rel,
                        f"unsupported symlink in bundle: {rel!r} (never followed)",
                    )
                )
                dirnames.remove(dirname)
        for filename in sorted(filenames):
            fpath = dirpath_p / filename
            rel = fpath.relative_to(root).as_posix()
            if rel == MANIFEST_NAME:
                continue
            if fpath.is_symlink():
                problems.append(
                    BundleProblem(
                        CODE_UNSUPPORTED_SYMLINK,
                        rel,
                        f"unsupported symlink in bundle: {rel!r} (never followed)",
                    )
                )
                continue
            if not _is_within_root(root, fpath):
                problems.append(
                    BundleProblem(
                        CODE_PATH_ESCAPE,
                        rel,
                        f"file escapes bundle root: {rel!r}",
                    )
                )
                continue
            found[rel] = fpath
            files_checked += 1

    # Manifest-listed files: present? size + hash match?
    for rel in sorted(entries):
        digest, size = entries[rel]
        fpath = found.get(rel)
        if fpath is None:
            problems.append(
                BundleProblem(
                    CODE_MISSING_FILE,
                    rel,
                    f"file listed in manifest is missing: {rel}",
                )
            )
            continue
        try:
            actual_size = fpath.stat().st_size
        except OSError:
            problems.append(
                BundleProblem(
                    CODE_MISSING_FILE,
                    rel,
                    f"file listed in manifest is missing: {rel}",
                )
            )
            continue
        if actual_size != size:
            problems.append(
                BundleProblem(
                    CODE_SIZE_MISMATCH,
                    rel,
                    f"size mismatch for {rel}: manifest says {size} bytes, "
                    f"file is {actual_size} bytes",
                )
            )
            # A size mismatch already proves tampering; still hash so a
            # hash mismatch is also reported (both facts are useful).
        if actual_size > MAX_FILE_BYTES:
            problems.append(
                BundleProblem(
                    CODE_LIMIT_EXCEEDED,
                    rel,
                    f"file {rel} is {actual_size} bytes, exceeding the "
                    "1 GiB per-file limit",
                )
            )
            continue
        total_bytes += actual_size
        try:
            _actual_size, actual_digest = _hash_file(fpath)
        except OSError:
            problems.append(
                BundleProblem(
                    CODE_MISSING_FILE,
                    rel,
                    f"file listed in manifest is missing: {rel}",
                )
            )
            continue
        if actual_digest != digest:
            problems.append(
                BundleProblem(
                    CODE_HASH_MISMATCH,
                    rel,
                    f"hash mismatch for {rel}: manifest says {digest}, "
                    f"recomputed {actual_digest}",
                )
            )

    # Extra files: on disk but not listed in the manifest.
    for rel in sorted(found):
        if rel not in entries:
            problems.append(
                BundleProblem(
                    CODE_EXTRA_FILE,
                    rel,
                    f"file present in bundle but not listed in manifest: {rel}",
                )
            )

    if len(found) > MAX_BUNDLE_FILES:
        problems.append(
            BundleProblem(
                CODE_LIMIT_EXCEEDED,
                ".",
                f"bundle file count {len(found)} exceeds the limit of "
                f"{MAX_BUNDLE_FILES}",
            )
        )
    if total_bytes > MAX_BUNDLE_BYTES:
        problems.append(
            BundleProblem(
                CODE_LIMIT_EXCEEDED,
                ".",
                f"bundle total size {total_bytes} bytes exceeds the limit "
                f"of {MAX_BUNDLE_BYTES} bytes",
            )
        )

    # Receipt cross-check: each first-level job dir's receipt.json.
    for job_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        receipt = job_dir / RECEIPT_NAME
        if receipt.is_file() and not receipt.is_symlink():
            receipt_rel = receipt.relative_to(root).as_posix()
            _check_receipt_reports(root, job_dir, receipt_rel, problems)

    problems.sort(key=lambda p: (p.path, p.code))
    return BundleResult(
        ok=not problems,
        problems=[p.as_dict() for p in problems],
        files_checked=files_checked,
        manifest_files=len(entries),
    )
