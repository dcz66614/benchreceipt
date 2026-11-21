"""Capture runner for BenchReceipt (P027-T003).

Orchestrates one wrapped test command into a ``benchreceipt.run/v1``
receipt (PROJECT_BOOK §5.1, §5.5, §6.2, §6.4):

1. Snapshot Git identity BEFORE the run (HEAD, tree, porcelain status).
2. Run the explicit user argv with ``shell=False`` (see
   :mod:`benchreceipt.command`).
3. Snapshot Git identity AFTER the run.
4. Detect source mutation during the run (HEAD/tree change, or a
   before/after difference in the filtered tracked-diff digest). The
   mutation is recorded *as data* in the receipt: ``git.head_sha_after``
   / ``git.tree_sha_after`` (the after-run HEAD/tree, added in spec
   v1.1.0 / ADR-005 — the fields that make a clean-tree HEAD change
   visible to the verifier), plus ``git.dirty_before/dirty_after``
   plus ``source_state_before/after``. The programmatic
   :class:`CaptureResult` also carries ``source_mutated_during_run``
   and ``mutation_details`` for T008 / CLI reporting. The verifier
   (T008) turns any of those differences into
   ``SOURCE_MUTATED_DURING_RUN``. NOTE (P0-01, fixed by ADR-005):
   before v1.1.0 the schema had no after-identity field, so this step's
   claim that mutation "is recorded as data" via dirty flags +
   source-state digests was FALSE for a clean-tree HEAD change
   (empty porcelain before and after, both dirty flags False) — the
   receipt claimed the before commit while the tests ran against the
   after commit, and verify returned BOUND_PASS. The after fields are
   the fix; dirty/digest checks alone are not sufficient evidence.
5. Hash declared JUnit/LCOV reports (byte-level SHA-256), copy them
   into ``artifacts/`` beside the receipt, assemble the receipt,
   validate it against ``benchreceipt.run/v1``, and write it to
   ``.benchreceipt/evidence/<job-id>/receipt.json``. When a JUnit
   report was declared, the receipt also carries its parsed summary
   (``receipt["junit"]``: ``tests`` / ``failures`` / ``errors`` /
   ``skipped``, counted testcases from :mod:`benchreceipt.reports.junit`
   — never the raw XML attributes); without it no green real capture
   could ever verify ``BOUND_PASS`` (the verifier requires the summary
   when the policy marks JUnit ``"required"``, PROJECT_BOOK §5.4/§6.2).

Fail-closed rules:

- No git identity (non-repo, missing git, unparseable HEAD) → no
  receipt is written at all; :class:`CaptureError` is raised. A SHA
  is never fabricated (see :mod:`benchreceipt.git_identity`).
- A declared report path that does not exist / cannot be read →
  :class:`CaptureError`; a missing report is never silently dropped
  from ``reports[]``.
- A declared JUnit report that cannot be parsed (malformed XML,
  DOCTYPE, attribute/count mismatch) is NEVER summarised by guessing:
  the ``junit`` field is omitted, a ``JUNIT_MALFORMED`` warning is
  written to stderr, and the receipt is still written with the
  command's exit code passed through. The verifier then flags
  ``MISSING_FIELD`` (UNBOUND) for the absent summary AND re-parses
  the artifact itself, yielding ``JUNIT_MALFORMED`` (INVALID) — so a
  malformed JUnit can never produce ``BOUND_PASS``. No LCOV summary
  is emitted: the frozen ``benchreceipt.run/v1`` schema has no field
  for one (see ADR-004); that gap is a spec decision, not a capture
  decision, and capture must not invent a schema field.
- A non-zero command exit code STILL writes a failure receipt (the
  exit code is recorded); only capture-internal failures abort
  without a receipt.
- No full environment, stdout, or stderr is ever stored (PROJECT_BOOK
  §11.1). Receipt paths are relative only (``artifacts/<name>``).
- Generated evidence never counts as source mutation: the
  ``.benchreceipt/`` tree and the exact declared report files are
  excluded from the before/after diff. Anything else the command
  creates in the worktree (e.g. a ``.coverage`` file at the repo root
  when it is not git-ignored) WILL show up as a before/after
  difference — that is deliberate fail-closed behaviour; point report
  outputs under ``.benchreceipt/`` (as in the PROJECT_BOOK §6.4
  example) to keep the tree clean.

Source-mode determination (no policy is passed to ``capture``; the
mode describes what the CI environment intended vs. what was checked
out, from the allowlisted metadata only):

- ``pull_request`` event with a head SHA, and the checked-out HEAD
  equals it → ``pr_head``, expected = head SHA.
- ``pull_request`` event, HEAD equals ``GITHUB_SHA`` (the merge
  commit) → ``merge_commit``, expected = ``GITHUB_SHA``.
- ``pull_request`` event, HEAD equals neither → ``merge_commit``,
  expected = ``GITHUB_SHA`` (what CI intended to test; the verifier
  flags the mismatch — the receipt never pretends they agree).
- No PR event but ``GITHUB_SHA`` present → ``event_sha``,
  expected = ``GITHUB_SHA``.
- No CI metadata at all (local run) → ``event_sha``,
  expected = the checked-out HEAD itself.
- Explicit pin (FIX-R13a / F-10, ADR-006):
  ``capture --source-mode explicit_sha --expected-sha <40-hex>`` →
  ``explicit_sha``, expected = the pinned SHA. The receipt's
  ``git.head_sha`` stays the real checked-out HEAD: a pinned SHA that
  differs from HEAD is recorded honestly and verify fails it with
  ``SOURCE_SHA_MISMATCH`` — the receipt never rewrites HEAD to agree
  with the pin. Before this fix no capture path could emit
  ``explicit_sha`` at all, so an ``explicit_sha`` policy could never
  verify (permanent false block).

Provisional CLI: the full ``cli.py`` is owned by T008. This module
therefore exposes a minimal ``capture`` subcommand only
(``python -m benchreceipt capture ...``), clearly marked provisional;
T008 replaces it with the complete CLI.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from benchreceipt.canonical import canonical_hash  # noqa: F401  (re-exported for T004/T008 reuse)
from benchreceipt.ci_metadata import CIMetadata, collect_ci_metadata
from benchreceipt.command import CommandResult, run_command
from benchreceipt.git_identity import (
    GitIdentity,
    collect_git_identity,
    repo_root,
    summarize_source_state,
)
from benchreceipt.reports.junit import JUnitError, parse_junit
from benchreceipt.schema import SchemaValidationError, validate_against_schema

__all__ = [
    "CaptureError",
    "CaptureResult",
    "build_capture_parser",
    "capture",
    "determine_source_mode",
    "main",
    "parse_matrix_args",
]

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_MATRIX_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_MAX_REPORT_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB, frozen schema limit.

# Exit code for capture-internal failures (INTERNAL_ERROR, §5.6).
EXIT_INTERNAL_ERROR = 4


class CaptureError(RuntimeError):
    """Capture failed before a receipt could be written.

    Raised for missing git identity, missing/unreadable declared
    reports, invalid job/matrix/argv, malformed CI metadata, or a
    receipt that fails schema validation. A non-zero *command* exit
    code is NOT a CaptureError — it produces a failure receipt.
    """


@dataclass(frozen=True)
class CaptureResult:
    """Outcome of :func:`capture` (programmatic result, not the receipt).

    ``receipt`` is the exact dict written to ``receipt_path``.
    ``source_mutated_during_run`` is True when HEAD/tree changed or
    the filtered tracked-diff digest changed between the before/after
    snapshots (generated evidence excluded); see module docstring.
    """

    receipt: dict
    evidence_dir: Path
    receipt_path: Path
    exit_code: int
    source_mutated_during_run: bool
    mutation_details: tuple[str, ...] = ()
    command: CommandResult | None = None


def _validate_job_id(job_id: str) -> None:
    if not isinstance(job_id, str) or not _JOB_ID_RE.match(job_id):
        raise CaptureError(
            f"invalid job_id {job_id!r}: must match "
            "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
        )


def _validate_matrix(matrix: Mapping) -> dict:
    if not isinstance(matrix, dict) or not matrix:
        raise CaptureError("matrix must be a non-empty mapping")
    if len(matrix) > 32:
        raise CaptureError("matrix must have at most 32 entries")
    cleaned: dict = {}
    for key, value in matrix.items():
        if not isinstance(key, str) or not _MATRIX_KEY_RE.match(key) or len(key) > 64:
            raise CaptureError(f"invalid matrix key {key!r}")
        if isinstance(value, bool) or isinstance(value, (str, int, float)):
            cleaned[key] = value
        else:
            raise CaptureError(
                f"invalid matrix value for {key!r}: JSON scalars only, "
                f"got {type(value).__name__}"
            )
    return cleaned


def parse_matrix_args(values: Sequence[str]) -> dict[str, str]:
    """Parse ``--matrix k=v,k=v`` arguments (repeatable) into a dict.

    Raises ``ValueError`` on a missing ``=``, an empty key/value, or a
    duplicate key. Values stay strings (schema also allows numbers /
    booleans, but the CLI contract passes strings, e.g. ``python=3.12``).
    """
    matrix: dict[str, str] = {}
    for raw in values:
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            if "=" not in item:
                raise ValueError(f"invalid --matrix entry {item!r}: expected k=v")
            key, value = item.split("=", 1)
            key, value = key.strip(), value.strip()
            if not key or not value:
                raise ValueError(f"invalid --matrix entry {item!r}: empty key or value")
            if key in matrix:
                raise ValueError(f"duplicate --matrix key {key!r}")
            matrix[key] = value
    if not matrix:
        raise ValueError("--matrix must name at least one k=v pair")
    return matrix


def determine_source_mode(
    ci: CIMetadata, head_sha: str, expected_sha: str | None = None
) -> tuple[str, str]:
    """Decide ``(source_mode, expected_source_sha)`` from CI metadata.

    See the module docstring for the decision table. Never returns a
    fabricated SHA: every branch's expected SHA comes from the CI
    metadata or from the real checked-out HEAD — except the explicit
    pin (FIX-R13a / F-10, ADR-006): when ``expected_sha`` is given it
    must be a 40-character lowercase hex SHA and the mode is
    ``explicit_sha`` with the pinned SHA as the expected value. A
    malformed pinned SHA raises ``ValueError`` (fail closed; the
    caller converts it to :class:`CaptureError`). ``head_sha`` is
    never rewritten to match the pin.
    """
    if expected_sha is not None:
        if not isinstance(expected_sha, str) or not _SHA40_RE.fullmatch(expected_sha):
            raise ValueError(
                "expected_sha must be a 40-character lowercase hex SHA"
            )
        return "explicit_sha", expected_sha
    if ci.event_name == "pull_request" and ci.head_sha:
        if head_sha == ci.head_sha:
            return "pr_head", ci.head_sha
        if ci.github_sha:
            return "merge_commit", ci.github_sha
        return "pr_head", ci.head_sha
    if ci.github_sha:
        return "event_sha", ci.github_sha
    return "event_sha", head_sha


def _hash_file(path: Path) -> tuple[int, str]:
    """Streamed ``(size_bytes, sha256_hex)`` of a file's exact bytes."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_REPORT_BYTES:
                raise CaptureError(
                    f"report {path} exceeds the 1 GiB size limit"
                )
            digest.update(chunk)
    return size, digest.hexdigest()


def _rel_to_repo(path: Path, repo: Path) -> str | None:
    """POSIX relative path of ``path`` inside ``repo``, or None if outside."""
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None


def _runner_fingerprint() -> dict[str, str]:
    return {
        "os": platform.system(),
        "arch": platform.machine(),
        "python": platform.python_version(),
    }


def capture(
    job_id: str,
    matrix: Mapping,
    argv: Sequence[str],
    repo_path: str | Path | None = None,
    junit_path: str | Path | None = None,
    lcov_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    evidence_root: str | Path | None = None,
    cwd: str | Path | None = None,
    source_mode: str | None = None,
    expected_sha: str | None = None,
) -> CaptureResult:
    """Wrap ``argv`` and write a ``benchreceipt.run/v1`` receipt.

    ``repo_path`` defaults to the current working directory (any
    directory inside the repo works). ``junit_path`` / ``lcov_path``
    are report files produced by the wrapped command, resolved
    relative to ``cwd`` (default: the process cwd); a declared report
    that is missing after the command finishes raises
    :class:`CaptureError`. ``evidence_root`` defaults to
    ``<repo>/.benchreceipt/evidence``. ``env`` is an explicit
    environment mapping for CI metadata (default: ``os.environ``).
    ``source_mode`` / ``expected_sha`` pin the source mode explicitly
    (FIX-R13a / F-10, ADR-006): the only supported pin is
    ``source_mode="explicit_sha"`` with a 40-character lowercase hex
    ``expected_sha``; anything else raises :class:`CaptureError`
    (fail closed). When both are omitted the mode is derived from CI
    metadata as before.

    Returns a :class:`CaptureResult`; the receipt dict is also written
    to ``.benchreceipt/evidence/<job-id>/receipt.json``. A non-zero
    command exit code still writes a failure receipt. When a JUnit
    report was declared and parses, the receipt carries its counted
    summary under ``"junit"``; when it is malformed the key is omitted
    (with a stderr warning) and no summary is guessed.
    """
    _validate_job_id(job_id)
    matrix = _validate_matrix(matrix)
    if not argv:
        raise CaptureError("argv must not be empty")
    if source_mode is not None and source_mode != "explicit_sha":
        raise CaptureError(
            f"unsupported source_mode {source_mode!r}: capture supports "
            "only 'explicit_sha' (or none, for the CI-derived mode)"
        )
    if expected_sha is not None and source_mode != "explicit_sha":
        raise CaptureError(
            "--expected-sha requires --source-mode explicit_sha"
        )
    if source_mode == "explicit_sha" and expected_sha is None:
        raise CaptureError(
            "--source-mode explicit_sha requires --expected-sha <40-hex-sha>"
        )

    command_cwd = Path(cwd) if cwd is not None else Path.cwd()
    search_root = Path(repo_path) if repo_path is not None else command_cwd
    root = repo_root(search_root)
    if root is None:
        raise CaptureError(
            f"cannot determine git repository for {search_root}: "
            "not a git worktree or git is unavailable; refusing to "
            "emit a receipt without real git identity"
        )

    git_before = collect_git_identity(root)
    if not git_before.available:
        raise CaptureError(
            f"git identity unavailable ({git_before.reason}); refusing "
            "to emit a receipt without a real HEAD/tree SHA"
        )
    assert git_before.head_sha is not None and git_before.tree_sha is not None

    try:
        ci = collect_ci_metadata(env)
    except ValueError as exc:
        raise CaptureError(f"malformed CI metadata: {exc}") from exc

    try:
        resolved_mode, resolved_expected = determine_source_mode(
            ci, git_before.head_sha, expected_sha
        )
    except ValueError as exc:
        raise CaptureError(f"invalid --expected-sha: {exc}") from exc

    # Declared reports, resolved against the command cwd. Their exact
    # paths are evidence exclusions for the diff (see module docstring).
    declared: list[tuple[str, Path]] = []
    for kind, given in (("junit", junit_path), ("lcov", lcov_path)):
        if given is None:
            continue
        resolved = (command_cwd / str(given)).resolve()
        declared.append((kind, resolved))
    exclude_files = tuple(
        rel
        for _, path in declared
        for rel in [_rel_to_repo(path, root)]
        if rel is not None
    )

    def _state(identity: GitIdentity) -> dict[str, object]:
        return summarize_source_state(
            identity,
            exclude_dirs=(".benchreceipt",),
            exclude_files=exclude_files,
        )

    state_before = _state(git_before)

    command = run_command(argv, cwd=command_cwd)

    git_after = collect_git_identity(root)
    if not git_after.available:
        raise CaptureError(
            f"git identity became unavailable after the run "
            f"({git_after.reason}); refusing to emit a receipt"
        )
    state_after = _state(git_after)

    # --- source-mutation detection (before vs after) -------------------
    mutation_details: list[str] = []
    if git_after.head_sha != git_before.head_sha:
        mutation_details.append(
            f"head_sha changed: {git_before.head_sha} -> {git_after.head_sha}"
        )
    if git_after.tree_sha != git_before.tree_sha:
        mutation_details.append(
            f"tree_sha changed: {git_before.tree_sha} -> {git_after.tree_sha}"
        )
    if state_before.get("tracked_diff_sha256") != state_after.get(
        "tracked_diff_sha256"
    ):
        mutation_details.append("tracked diff changed during run")
    elif state_before.get("dirty") != state_after.get("dirty"):
        mutation_details.append("dirty flag changed during run")
    source_mutated = bool(mutation_details)

    # --- reports: hash + copy into artifacts/ --------------------------
    evidence_base = (
        Path(evidence_root)
        if evidence_root is not None
        else root / ".benchreceipt" / "evidence"
    )
    evidence_dir = evidence_base / job_id
    artifacts_dir = evidence_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    reports: list[dict[str, object]] = []
    junit_summary: dict[str, int] | None = None
    seen_basenames: set[str] = set()
    for kind, source in declared:
        if not source.is_file():
            raise CaptureError(
                f"declared {kind} report not found after run: {source}"
            )
        basename = source.name
        if basename in seen_basenames:
            raise CaptureError(
                f"report basename collision: both reports are named {basename!r}"
            )
        seen_basenames.add(basename)
        size, digest = _hash_file(source)
        dest = artifacts_dir / basename
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
        reports.append(
            {
                "kind": kind,
                "path": f"artifacts/{basename}",
                "size_bytes": size,
                "sha256": digest,
            }
        )
        if kind == "junit":
            # Parse the declared JUnit file with the T005 parser and
            # emit the counted summary into receipt["junit"] (§5.4/§6.2).
            # Only the four schema-allowed keys are emitted
            # (run.v1.json: junit has additionalProperties false, so
            # the parser's extra testcase_count/suites keys must NOT
            # be copied). A malformed report fails closed: no guessed
            # summary, stderr warning, receipt still written (see
            # module docstring); verify re-parses the artifact and
            # yields JUNIT_MALFORMED -> INVALID.
            try:
                parsed = parse_junit(source)
            except JUnitError as exc:
                print(
                    "benchreceipt capture: warning: JUNIT_MALFORMED: "
                    f"{exc}; omitting junit summary from the receipt "
                    "(verify will flag MISSING_FIELD and re-parse the "
                    "artifact as JUNIT_MALFORMED -> INVALID)",
                    file=sys.stderr,
                )
            else:
                junit_summary = {
                    "tests": parsed["tests"],
                    "failures": parsed["failures"],
                    "errors": parsed["errors"],
                    "skipped": parsed["skipped"],
                }

    # --- assemble + validate + write receipt ---------------------------
    ci_block: dict[str, object] = {
        "provider": ci.provider,
        "run_id": ci.run_id if ci.run_id is not None else "local",
        "run_attempt": ci.run_attempt if ci.run_attempt is not None else 1,
        "workflow": ci.workflow if ci.workflow is not None else "local",
    }
    if ci.event_name is not None:
        ci_block["event_name"] = ci.event_name

    receipt: dict[str, object] = {
        "schema": "benchreceipt.run/v1",
        "job_id": job_id,
        "matrix": matrix,
        "git": {
            "head_sha": git_before.head_sha,
            "tree_sha": git_before.tree_sha,
            # After-identity (spec v1.1.0, ADR-005): the HEAD/tree at
            # capture end, taken from the same git_after snapshot the
            # mutation check already uses. Always emitted, even when
            # unchanged — an after value equal to the before value is
            # itself evidence that no clean-tree HEAD change happened.
            # Without these fields a clean-tree `git checkout` /
            # empty-commit mid-run was invisible to the verifier
            # (P0-01): dirty flags and porcelain digests do not move.
            "head_sha_after": git_after.head_sha,
            "tree_sha_after": git_after.tree_sha,
            "source_mode": resolved_mode,
            "expected_source_sha": resolved_expected,
            "dirty_before": bool(state_before.get("dirty", True)),
            "dirty_after": bool(state_after.get("dirty", True)),
        },
        "ci": ci_block,
        "command": {
            "argv_sha256": command.argv_sha256,
            "display": command.display,
            "exit_code": command.exit_code,
        },
        "runner": _runner_fingerprint(),
        "reports": reports,
        "started_at": command.started_at,
        "finished_at": command.finished_at,
        "source_state_before": state_before,
        "source_state_after": state_after,
    }
    # No LCOV summary field exists in the frozen run.v1 schema, so only
    # the JUnit summary is emitted (see ADR-004 for the LCOV gap).
    if junit_summary is not None:
        receipt["junit"] = junit_summary
    try:
        validate_against_schema(receipt, "run")
    except SchemaValidationError as exc:
        raise CaptureError(
            f"assembled receipt fails benchreceipt.run/v1 validation: {exc}"
        ) from exc

    receipt_path = evidence_dir / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return CaptureResult(
        receipt=receipt,
        evidence_dir=evidence_dir,
        receipt_path=receipt_path,
        exit_code=command.exit_code,
        source_mutated_during_run=source_mutated,
        mutation_details=tuple(mutation_details),
        command=command,
    )


# ---------------------------------------------------------------------------
# Provisional CLI (T008 owns the full cli.py; this is the minimal
# `capture` subcommand only — see module docstring).
# ---------------------------------------------------------------------------


def build_capture_parser() -> argparse.ArgumentParser:
    """Argument parser for the provisional ``capture`` subcommand."""
    parser = argparse.ArgumentParser(
        prog="benchreceipt capture",
        description=(
            "Wrap an explicit test command and write a "
            "benchreceipt.run/v1 receipt (provisional CLI; the full CLI "
            "is owned by P027-T008)."
        ),
    )
    parser.add_argument("--job", required=True, help="stable job id, e.g. unit-linux-py312")
    parser.add_argument(
        "--matrix",
        required=True,
        action="append",
        metavar="K=V,...",
        help="matrix cell, e.g. os=ubuntu-latest,python=3.12 (repeatable)",
    )
    parser.add_argument("--junit", default=None, help="JUnit XML report produced by the command")
    parser.add_argument("--lcov", default=None, help="LCOV report produced by the command")
    parser.add_argument(
        "--source-mode",
        default=None,
        choices=["explicit_sha"],
        metavar="MODE",
        help="pin the source mode instead of deriving it from CI "
        "metadata: explicit_sha (requires --expected-sha; ADR-006)",
    )
    parser.add_argument(
        "--expected-sha",
        default=None,
        metavar="SHA",
        help="40-character lowercase hex SHA the run is bound to "
        "(requires --source-mode explicit_sha)",
    )
    parser.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="command to run, after '--' (e.g. -- python -m pytest -q)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Provisional ``capture`` CLI entry point. Returns a process exit code.

    The exit code is the wrapped command's exit code (signal deaths map
    to ``128 + signum``); capture-internal failures return 4
    (INTERNAL_ERROR, PROJECT_BOOK §5.6). ``argparse`` errors return 2.
    """
    parser = build_capture_parser()
    args = parser.parse_args(argv)
    # argparse.REMAINDER keeps a leading '--' as the first element.
    command_argv = list(args.argv)
    if command_argv and command_argv[0] == "--":
        command_argv = command_argv[1:]
    if not command_argv:
        parser.error("no command given after '--'")
    try:
        matrix = parse_matrix_args(args.matrix)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        result = capture(
            job_id=args.job,
            matrix=matrix,
            argv=command_argv,
            junit_path=args.junit,
            lcov_path=args.lcov,
            source_mode=args.source_mode,
            expected_sha=args.expected_sha,
        )
    except CaptureError as exc:
        print(f"benchreceipt capture: error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR
    try:
        rel_receipt = result.receipt_path.relative_to(Path.cwd())
    except ValueError:
        rel_receipt = result.receipt_path
    print(
        f"benchreceipt capture: job={result.receipt['job_id']} "
        f"exit={result.exit_code} receipt={rel_receipt} "
        f"source_mutated={str(result.source_mutated_during_run).lower()}"
    )
    if result.source_mutated_during_run:
        print(
            "benchreceipt capture: warning: SOURCE_MUTATED_DURING_RUN: "
            + "; ".join(result.mutation_details),
            file=sys.stderr,
        )
    exit_code = result.exit_code
    if exit_code < 0:
        exit_code = 128 + (-exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
