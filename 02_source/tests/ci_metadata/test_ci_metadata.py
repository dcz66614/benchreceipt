"""ci_metadata tests (P027-T003).

Synthetic GitHub Actions environments are injected as plain mappings —
no process environment is touched and no real CI is needed.
"""

import json
from pathlib import Path

import pytest

from benchreceipt.ci_metadata import CI_ALLOWLIST, collect_ci_metadata

HEAD_SHA = "a" * 40
MERGE_SHA = "b" * 40


def pr_event(tmp_path: Path, head_sha: str = HEAD_SHA, merge_sha: str = MERGE_SHA) -> Path:
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps(
            {
                "action": "opened",
                "pull_request": {
                    "head": {"sha": head_sha},
                    "merge_commit_sha": merge_sha,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_empty_env_is_generic_and_unknown(tmp_path: Path):
    meta = collect_ci_metadata({})
    assert meta.is_github is False
    assert meta.provider == "generic"
    assert meta.run_id is None
    assert meta.run_attempt is None
    assert meta.workflow is None
    assert meta.event_name is None
    assert meta.github_sha is None
    assert meta.head_sha is None
    assert meta.event is None
    assert meta.event_error is None


def test_github_env_fields(tmp_path: Path):
    meta = collect_ci_metadata(
        {
            "GITHUB_SHA": MERGE_SHA,
            "GITHUB_REF": "refs/pull/1/merge",
            "GITHUB_RUN_ID": "9001",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_WORKFLOW": "CI",
            "GITHUB_JOB": "unit-linux-py312",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_WORKSPACE": "/home/runner/work/repo",
            "RUNNER_OS": "Linux",
            "RUNNER_ARCH": "X64",
        }
    )
    assert meta.is_github is True
    assert meta.provider == "github-actions"
    assert meta.run_id == "9001"
    assert meta.run_attempt == 2
    assert meta.workflow == "CI"
    assert meta.job == "unit-linux-py312"
    assert meta.event_name == "pull_request"
    assert meta.github_sha == MERGE_SHA
    assert meta.github_ref == "refs/pull/1/merge"
    assert meta.repository == "owner/repo"
    assert meta.workspace == "/home/runner/work/repo"
    assert meta.runner_os == "Linux"
    assert meta.runner_arch == "X64"


def test_pr_event_head_and_merge_parsed(tmp_path: Path):
    event = pr_event(tmp_path)
    meta = collect_ci_metadata(
        {
            "GITHUB_SHA": MERGE_SHA,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event),
        }
    )
    assert meta.head_sha == HEAD_SHA
    assert meta.event_merge_sha == MERGE_SHA
    assert meta.event is not None
    assert meta.event["pull_request"]["head"]["sha"] == HEAD_SHA
    assert meta.event_error is None


def test_event_without_pull_request_has_no_head_sha(tmp_path: Path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"action": "created"}), encoding="utf-8")
    meta = collect_ci_metadata({"GITHUB_EVENT_PATH": str(event)})
    assert meta.head_sha is None
    assert meta.event_error is None


def test_missing_event_file_is_error_not_crash(tmp_path: Path):
    meta = collect_ci_metadata(
        {"GITHUB_EVENT_PATH": str(tmp_path / "no-such-event.json")}
    )
    assert meta.event is None
    assert meta.head_sha is None
    assert meta.event_error is not None


def test_malformed_event_json_is_error_not_crash(tmp_path: Path):
    event = tmp_path / "event.json"
    event.write_text("{not json", encoding="utf-8")
    meta = collect_ci_metadata({"GITHUB_EVENT_PATH": str(event)})
    assert meta.event is None
    assert meta.event_error is not None


def test_non_object_event_json_is_error(tmp_path: Path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps(["a", "list"]), encoding="utf-8")
    meta = collect_ci_metadata({"GITHUB_EVENT_PATH": str(event)})
    assert meta.event is None
    assert meta.event_error is not None


@pytest.mark.parametrize("bad", ["abc", "0", "-1", "100001", "2.5", ""])
def test_malformed_run_attempt_raises(bad: str):
    # An empty string counts as missing (None), not malformed.
    if bad == "":
        assert collect_ci_metadata({"GITHUB_RUN_ATTEMPT": ""}).run_attempt is None
        return
    with pytest.raises(ValueError, match="GITHUB_RUN_ATTEMPT"):
        collect_ci_metadata({"GITHUB_RUN_ATTEMPT": bad})


def test_allowlist_only_non_allowlisted_vars_have_no_effect():
    base = {"GITHUB_RUN_ID": "9001", "GITHUB_WORKFLOW": "CI"}
    with_secrets = dict(
        base,
        GITHUB_TOKEN="ghp_should-never-be-read",
        AWS_SECRET_ACCESS_KEY="also-never-read",
        MY_PASSWORD="hunter2",
        HOME="/home/someone",
    )
    assert collect_ci_metadata(base) == collect_ci_metadata(with_secrets)
    # The allowlist itself is the fixed contract.
    assert "GITHUB_TOKEN" not in CI_ALLOWLIST
    assert "GITHUB_SHA" in CI_ALLOWLIST
    assert len(CI_ALLOWLIST) == 12
