"""git_identity tests (P027-T003).

All git behaviour is exercised against real synthetic repositories
created in tmp dirs — never against the project repo itself, so the
tests stay hermetic and never depend on the checkout state.
"""

import hashlib
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from benchreceipt.git_identity import (
    collect_git_identity,
    repo_root,
    summarize_source_state,
)

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@contextmanager
def outside_repo_dir():
    """A temp dir guaranteed to sit outside any git worktree.

    NOTE: pytest's ``tmp_path`` lives under the project work dir (via
    TMPDIR), which IS inside the project git repo — so a "plain" dir
    under ``tmp_path`` is still inside a worktree and
    :func:`collect_git_identity` correctly finds the enclosing repo.
    Non-repo tests therefore need a dir under /tmp (separate tmpfs,
    outside the repo). Only tiny files are created there.
    """
    directory = Path(tempfile.mkdtemp(dir="/tmp"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def make_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    """Create a synthetic git repo at ``path`` with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "BenchReceipt Test"],
        check=True,
    )
    for name, content in (files or {"tracked.txt": "hello\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-qm", "initial"], check=True
    )
    return path


def git_rev(path: Path, arg: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(path), "rev-parse", arg],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def test_head_and_tree_match_real_repo(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    ident = collect_git_identity(repo)
    assert ident.available is True
    assert ident.head_sha == git_rev(repo, "HEAD")
    assert ident.tree_sha == git_rev(repo, "HEAD^{tree}")
    assert len(ident.head_sha) == 40
    assert len(ident.tree_sha) == 40
    assert ident.reason is None


def test_clean_tree_is_not_dirty(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    ident = collect_git_identity(repo)
    state = summarize_source_state(ident)
    assert state["dirty"] is False
    assert state["tracked_diff_sha256"] == EMPTY_SHA256


def test_tracked_modification_is_dirty(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "tracked.txt").write_text("hello\nchanged\n", encoding="utf-8")
    ident = collect_git_identity(repo)
    state = summarize_source_state(ident)
    assert state["dirty"] is True
    assert state["tracked_diff_sha256"] != EMPTY_SHA256


def test_untracked_unignored_file_is_dirty(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "new-file.txt").write_text("untracked\n", encoding="utf-8")
    ident = collect_git_identity(repo)
    state = summarize_source_state(ident)
    assert state["dirty"] is True


def test_ignored_file_is_not_dirty(tmp_path: Path):
    repo = make_repo(tmp_path / "repo", {"tracked.txt": "hello\n", ".gitignore": "*.log\n"})
    (repo / "debug.log").write_text("ignored\n", encoding="utf-8")
    ident = collect_git_identity(repo)
    state = summarize_source_state(ident)
    # .gitignore itself is committed; debug.log is ignored -> clean.
    assert state["dirty"] is False


def test_benchreceipt_dir_excluded_by_default(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    evidence = repo / ".benchreceipt" / "evidence" / "job-1"
    evidence.mkdir(parents=True)
    (evidence / "receipt.json").write_text("{}\n", encoding="utf-8")
    ident = collect_git_identity(repo)
    state = summarize_source_state(ident)
    assert state["dirty"] is False


def test_explicit_report_file_excluded(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "junit.xml").write_text("<testsuites/>\n", encoding="utf-8")
    ident = collect_git_identity(repo)
    excluded = summarize_source_state(ident, exclude_files=("junit.xml",))
    assert excluded["dirty"] is False
    included = summarize_source_state(ident, exclude_files=())
    assert included["dirty"] is True


def test_diff_digest_is_deterministic(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "tracked.txt").write_text("hello\nchanged\n", encoding="utf-8")
    first = summarize_source_state(collect_git_identity(repo))
    second = summarize_source_state(collect_git_identity(repo))
    assert first == second


def test_non_git_dir_reports_unknown_not_fabricated(tmp_path: Path):
    with outside_repo_dir() as plain:
        ident = collect_git_identity(plain)
        assert ident.available is False
        assert ident.head_sha is None
        assert ident.tree_sha is None
        assert ident.reason == "not-a-git-repo"
        # Unknown state is never reported clean.
        assert summarize_source_state(ident)["dirty"] is True
        assert "tracked_diff_sha256" not in summarize_source_state(ident)


def test_missing_dir_reports_unknown(tmp_path: Path):
    ident = collect_git_identity(tmp_path / "does-not-exist")
    assert ident.available is False
    assert ident.head_sha is None
    assert ident.reason == "not-a-directory"


def test_repo_root_found_from_subdirectory(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    assert repo_root(sub) == repo
    with outside_repo_dir() as plain:
        assert repo_root(plain) is None


def test_empty_repo_without_commits_is_unavailable(tmp_path: Path):
    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    ident = collect_git_identity(repo)
    assert ident.available is False
    assert ident.head_sha is None
