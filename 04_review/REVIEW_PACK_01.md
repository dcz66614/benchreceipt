# REVIEW_PACK_01 — Capture + Git identity

Frozen candidate: `cfede2711bc54567b918b1f85654c2dd42c30943` (see `REVIEW_INDEX.md`). All files below
are inventoried with SHA-256 + line counts; the reviewer reads the
full files from the checkout at that commit. Line numbers in the
questions refer to that exact version.

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/capture.py` | `15ca06363898818561a5026882cbdccb9f6089996ce7f7f6f11166e179bea850` | 609 | capture: runs the command, snapshots git before/after, writes receipt.json |
| `02_source/src/benchreceipt/git_identity.py` | `61f1a53fae80422cf3f6d3b1cb38ac5e9814c948868c85301f590efa2792542a` | 213 | git identity snapshot: HEAD/tree/porcelain, fail-closed |
| `02_source/src/benchreceipt/ci_metadata.py` | `960ab6c537d39024e45ed213d17cef85d40eedb030876cbdeedc9e2daac0f0ac` | 196 | CI metadata from env + GitHub event file |
| `02_source/src/benchreceipt/command.py` | `8c6afb5a435ab118ee178c7957a340569467ff9ff68454943c5bb78fee4ef6c2` | 228 | argv normalise / redact / digest, subprocess runner |
| `02_source/src/benchreceipt/canonical.py` | `540d16a88e29e9ccbd1c3959c24b4c16b2a43505a48d8d8830030ae6fc147c88` | 50 | canonical JSON + canonical hash |

## What this pack covers

`capture` wraps one test command, snapshots git identity before and
after the run, and writes one `benchreceipt.run/v1` receipt per job.
`git_identity` is the only place that talks to `git`; `ci_metadata`
is the only place that reads CI environment / the GitHub event file;
`command` is the only place that runs a subprocess and the only place
that handles secrets in argv; `canonical` defines the byte-exact
hashing everything else relies on.

## Review questions

1. **No fabricated SHA (fail-closed).** `collect_git_identity`
   returns `available=False` with `head_sha`/`tree_sha` `None` on
   every failure path (not-a-repo, git missing, rev-parse failure,
   status failure). Confirm no path returns a zero SHA, a truncated
   SHA, or a placeholder. Confirm `capture` refuses to emit a
   receipt when the snapshot is unavailable instead of inventing
   values.
2. **SHA validation.** `_rev_parse` accepts only exactly 40
   lowercase hex chars. Is there any caller that trusts
   `git rev-parse` output without this check? (Search all
   `subprocess` call sites: only `command.py` and
   `git_identity.py` run subprocesses, both with `shell=False`.)
3. **Source-mode decision table** (`determine_source_mode`, inlined
   below). Walk every branch: `pull_request` + HEAD==head_sha →
   `pr_head`; `pull_request` + HEAD!=head_sha + github_sha →
   `merge_commit`; `pull_request` without github_sha → `pr_head`
   with the PR head SHA; otherwise `event_sha` with github_sha or
   HEAD. Is there an input where the returned expected SHA is not
   the SHA the tests actually ran against? In particular: can
   `ci.head_sha` come from an untrusted event payload and disagree
   with the checked-out HEAD in a way that `verify` would then
   bless?
4. **Dirty-state digest.** `summarize_source_state` hashes the
   filtered porcelain lines (LF-joined, UTF-8); clean tree hashes
   the empty string. Check the exclusion logic
   (`_is_excluded`, `_porcelain_path`): can a real source mutation
   hide under an excluded path (`.benchreceipt/`, declared report
   output dirs)? Can a rename (`old -> new`) be mis-parsed so the
   digest misses a change? Is `dirty=True` returned (never clean)
   when the snapshot is unavailable?
5. **Secret redaction** (`command.redact_argv`, `_is_secret_token`).
   Tokens naming a secret (`--token=...`, `--token <value>`,
   bare secret values) must become `[REDACTED]` in the receipt's
   `display` string, while `argv_sha256` still covers the *full*
   unredacted argv. Check: does any secret-bearing token survive
   into `display` (e.g. a secret flag written `--token=abc` where
   the hint list misses the flag name, or a secret value that does
   not follow its flag)? Does the display truncation (512 chars +
   ellipsis) ever cut in a way that leaks a secret tail? Is the
   full argv ever written anywhere (receipt, log, HTML report)?
6. **Absolute paths.** `_shorten_path_token` / `display_command`
   must strip absolute user paths from receipts. Check Windows
   drive-letter paths and POSIX paths, including paths embedded
   inside a longer token.
7. **Size limits.** `_hash_file` refuses reports over 1 GiB
   (`_MAX_REPORT_BYTES`). Check the limit is enforced *during*
   streaming (not after reading the whole file into memory) and
   that the failure is a clean `CaptureError`, not a pass.
8. **Timestamps / runner fingerprint.** `utc_now_iso` and
   `_runner_fingerprint` record only os/arch/python — confirm no
   hostname, username, home directory, or full environment is
   recorded anywhere in the receipt.
9. **Canonical hash.** `canonical_json` / `canonical_hash` must be
   deterministic (sorted keys, fixed separators, UTF-8). Confirm a
   dict with the same content always hashes the same, and that no
   caller hashes a non-canonical serialisation.

## Inlined source (verbatim — do not paraphrase)

### `git_identity.py` — complete file (the whole git-trust boundary)

```python
"""Git identity collection for BenchReceipt capture (P027-T003).

Collects the commit / tree / worktree state of a repository by invoking
the ``git`` CLI with ``subprocess`` and ``shell=False`` only (PROJECT_BOOK
§5.5, §11.2). No shell string is ever built.

Fail-closed rules (PROJECT_BOOK §5.6, ADR-001):

- If the directory is not a git repository, ``git`` is missing, or any
  ``git`` call fails, the snapshot reports ``available == False`` and
  ``head_sha`` / ``tree_sha`` are ``None``. A SHA is NEVER fabricated:
  no zero-SHA, no placeholder, no truncated hash. Callers that need a
  schema-valid receipt (``capture``) refuse to emit one without a real
  HEAD/tree instead of inventing values.
- ``tracked_diff_sha256`` is the SHA-256 of the filtered
  ``git status --porcelain=v1 --untracked-files=all`` output: one line
  per entry, LF-joined, UTF-8. A clean tree hashes the empty byte
  string (``e3b0c442...``). Paths under evidence/output directories
  (e.g. ``.benchreceipt/`` and the directories holding declared report
  outputs) are excluded before the digest is computed, so generated
  report files never count as source mutation (PROJECT_BOOK §5.5).
- ``dirty`` is True when any non-excluded status line remains. That
  includes untracked, un-ignored files (``??`` lines): PROJECT_BOOK
  §5.5 speaks of "tracked source or un-ignored source files".

Standard library only.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "GitIdentity",
    "collect_git_identity",
    "repo_root",
    "summarize_source_state",
]

_UNKNOWN_REASONS = {
    "not-a-git-repo",
    "git-not-found",
    "git-error",
    "not-a-directory",
}


@dataclass(frozen=True)
class GitIdentity:
    """One point-in-time snapshot of a git worktree.

    ``head_sha`` / ``tree_sha`` are full 40-hex lowercase SHAs when
    ``available`` is True, else ``None``. ``status_lines`` holds the raw
    ``git status --porcelain=v1`` lines (unfiltered); use
    :func:`summarize_source_state` to apply evidence-path exclusions.
    """

    available: bool
    repo_path: str
    head_sha: str | None = None
    tree_sha: str | None = None
    status_lines: tuple[str, ...] = ()
    reason: str | None = None  # one of _UNKNOWN_REASONS, else None


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    """Run ``git <args>`` with ``shell=False``; return None if git cannot run."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _rev_parse(arg: str, cwd: Path) -> str | None:
    """Return a validated 40-hex SHA from ``git rev-parse <arg>`` or None."""
    proc = _run_git(["rev-parse", arg], cwd)
    if proc is None or proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        return None
    return value


def repo_root(path: str | Path) -> Path | None:
    """Return the top-level directory of the git repo containing ``path``.

    Returns ``None`` when ``path`` is not inside a git worktree or git
    cannot run. Never raises for a non-repo path.
    """
    cwd = Path(path)
    if not cwd.is_dir():
        return None
    proc = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if proc is None or proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return Path(root) if root else None


def collect_git_identity(repo_path: str | Path) -> GitIdentity:
    """Snapshot HEAD, tree and porcelain status for ``repo_path``.

    ``repo_path`` may be any directory inside the worktree; the snapshot
    is taken for the enclosing repository. On any failure the returned
    identity has ``available == False`` and ``reason`` set — never a
    fabricated SHA.
    """
    cwd = Path(repo_path)
    if not cwd.is_dir():
        return GitIdentity(
            available=False, repo_path=str(cwd), reason="not-a-directory"
        )
    root = repo_root(cwd)
    if root is None:
        # Distinguish "git binary missing" from "not a repo": if git
        # itself cannot run, every git call returns None.
        probe = _run_git(["--version"], cwd)
        reason = "git-not-found" if probe is None else "not-a-git-repo"
        return GitIdentity(available=False, repo_path=str(cwd), reason=reason)

    head_sha = _rev_parse("HEAD", root)
    tree_sha = _rev_parse("HEAD^{tree}", root)
    if head_sha is None or tree_sha is None:
        return GitIdentity(
            available=False, repo_path=str(root), reason="git-error"
        )
    proc = _run_git(
        ["status", "--porcelain=v1", "--untracked-files=all"], root
    )
    if proc is None or proc.returncode != 0:
        return GitIdentity(
            available=False, repo_path=str(root), reason="git-error"
        )
    lines = tuple(line for line in proc.stdout.splitlines() if line)
    return GitIdentity(
        available=True,
        repo_path=str(root),
        head_sha=head_sha,
        tree_sha=tree_sha,
        status_lines=lines,
    )


def _is_excluded(rel_path: str, exclude_dirs: tuple[str, ...], exclude_files: tuple[str, ...]) -> bool:
    """True when a porcelain entry path is an evidence/output path.

    ``rel_path`` is the path as reported by ``git status`` (relative to
    the repo root, POSIX separators). A path is excluded when it equals
    an excluded file or lives under an excluded directory.
    """
    if rel_path in exclude_files:
        return True
    for directory in exclude_dirs:
        if rel_path == directory or rel_path.startswith(directory + "/"):
            return True
    return False


def _porcelain_path(line: str) -> str:
    """Extract the path field from one ``--porcelain=v1`` line.

    Format is ``XY <path>``; renames are ``XY <old> -> <new>`` and the
    *new* path is the one that exists in the worktree.
    """
    rest = line[3:] if len(line) > 3 else ""
    if " -> " in rest:
        return rest.split(" -> ", 1)[1]
    return rest


def summarize_source_state(
    identity: GitIdentity,
    exclude_dirs: tuple[str, ...] = (".benchreceipt",),
    exclude_files: tuple[str, ...] = (),
) -> dict[str, object]:
    """Summarise a snapshot as a ``source_state_before/after`` dict.

    Returns ``{"dirty": bool, "tracked_diff_sha256": <64-hex>}`` for an
    available snapshot, or ``{"dirty": True}`` with no digest when the
    snapshot is unavailable (unknown state is dirty, never clean — a
    fail-closed reading: capture refuses to emit a receipt at all in
    that case, but the summary itself never claims "clean" without
    evidence).

    Exclusions are relative paths inside the repo (POSIX form):
    ``exclude_dirs`` are directory prefixes, ``exclude_files`` exact
    files. The default excludes ``.benchreceipt/`` (receipts and
    copied artifacts) so generated evidence never counts as source
    mutation.
    """
    if not identity.available:
        return {"dirty": True}
    kept: list[str] = []
    for line in identity.status_lines:
        if not _is_excluded(
            _porcelain_path(line), exclude_dirs, exclude_files
        ):
            kept.append(line)
    digest = hashlib.sha256("\n".join(kept).encode("utf-8")).hexdigest()
    return {"dirty": bool(kept), "tracked_diff_sha256": digest}
```

### `capture.py` — `determine_source_mode` (verbatim)

```python
def determine_source_mode(
    ci: CIMetadata, head_sha: str
) -> tuple[str, str]:
    """Decide ``(source_mode, expected_source_sha)`` from CI metadata.

    See the module docstring for the decision table. Never returns a
    fabricated SHA: every branch's expected SHA comes from the CI
    metadata or from the real checked-out HEAD.
    """
    if ci.event_name == "pull_request" and ci.head_sha:
        if head_sha == ci.head_sha:
            return "pr_head", ci.head_sha
        if ci.github_sha:
            return "merge_commit", ci.github_sha
        return "pr_head", ci.head_sha
    if ci.github_sha:
        return "event_sha", ci.github_sha
    return "event_sha", head_sha
```
