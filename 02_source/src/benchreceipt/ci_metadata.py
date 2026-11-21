"""GitHub Actions CI metadata for BenchReceipt capture (P027-T003).

Reads ONLY a fixed allowlist of environment variables (PROJECT_BOOK
§11.1: never store the full environment) plus the JSON event payload
referenced by ``GITHUB_EVENT_PATH``. Missing metadata is NEVER inferred:
absent fields come back as ``None`` / ``"unknown"`` and the caller
decides the fail-closed consequence.

GitHub semantics used (docs.github.com, pull_request events):

- ``GITHUB_SHA`` is the *merge* commit SHA for ``pull_request`` events,
  not the PR head SHA.
- The PR head SHA lives in the event payload at
  ``pull_request.head.sha``; ``pull_request.merge_commit_sha`` (when
  present) is the merge commit.
- ``GITHUB_RUN_ID`` / ``GITHUB_RUN_ATTEMPT`` identify the workflow run
  and attempt; ``GITHUB_WORKFLOW`` is the workflow name.

The allowlist deliberately has no ``GITHUB_WORKFLOW_REF`` /
``GITHUB_WORKFLOW_SHA`` entry, so ``workflow_ref`` / ``workflow_sha``
are NOT populated by this module (ADR-001: emit optional fields only
when available — they are not available from the allowlist).

Standard library only. All functions take an explicit ``env`` mapping
(default ``os.environ``) so tests and T004 fixtures can inject
synthetic CI environments without touching process state.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

__all__ = ["CI_ALLOWLIST", "CIMetadata", "collect_ci_metadata"]

# Fixed allowlist — the ONLY environment variables this module reads.
# PROJECT_BOOK §11.1: no full environment, no secrets.
CI_ALLOWLIST = (
    "GITHUB_SHA",
    "GITHUB_REF",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_WORKFLOW",
    "GITHUB_JOB",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_WORKSPACE",
    "GITHUB_REPOSITORY",
    "RUNNER_OS",
    "RUNNER_ARCH",
)

_MAX_EVENT_BYTES = 10 * 1024 * 1024  # 10 MiB cap on the event payload file.


@dataclass(frozen=True)
class CIMetadata:
    """Parsed GitHub Actions metadata. Absent values are ``None``."""

    is_github: bool = False
    provider: str = "generic"
    run_id: str | None = None
    run_attempt: int | None = None
    workflow: str | None = None
    job: str | None = None
    event_name: str | None = None
    github_sha: str | None = None
    github_ref: str | None = None
    repository: str | None = None
    workspace: str | None = None
    runner_os: str | None = None
    runner_arch: str | None = None
    # PR head SHA from the event payload (pull_request.head.sha).
    head_sha: str | None = None
    # Merge commit SHA from the event payload, if present.
    event_merge_sha: str | None = None
    event: dict[str, Any] | None = None
    # Set when GITHUB_EVENT_PATH was given but the payload could not be
    # read/parsed; the metadata is still returned, minus event data.
    event_error: str | None = None


def _clean(value: str | None) -> str | None:
    """Strip whitespace; empty strings become None (missing, not empty)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_run_attempt(raw: str | None) -> int | None:
    """Parse GITHUB_RUN_ATTEMPT; raises ValueError on malformed values.

    A malformed attempt must never be silently coerced to 1 — that
    would manufacture run identity. The caller converts this to a
    capture failure.
    """
    raw = _clean(raw)
    if raw is None:
        return None
    try:
        attempt = int(raw, 10)
    except ValueError as exc:
        raise ValueError(f"malformed GITHUB_RUN_ATTEMPT: {raw!r}") from exc
    if not 1 <= attempt <= 100000:
        raise ValueError(f"GITHUB_RUN_ATTEMPT out of range 1..100000: {attempt}")
    return attempt


def _load_event(path_value: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """Load the GITHUB_EVENT_PATH JSON payload, bounded and fail-safe.

    Returns ``(event_dict_or_None, error_or_None)``. A missing file,
    oversize file, non-object JSON, or parse failure yields
    ``(None, <reason>)`` — never an exception, never a fabricated event.
    """
    path_value = _clean(path_value)
    if path_value is None:
        return None, None
    path = Path(path_value)
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, f"cannot read GITHUB_EVENT_PATH {path_value}: {exc}"
    if size > _MAX_EVENT_BYTES:
        return None, f"GITHUB_EVENT_PATH too large ({size} bytes)"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"cannot parse GITHUB_EVENT_PATH {path_value}: {exc}"
    if not isinstance(data, dict):
        return None, f"GITHUB_EVENT_PATH is not a JSON object: {path_value}"
    return data, None


def _pr_sha(event: dict[str, Any] | None, *keys: str) -> str | None:
    """Walk ``event["pull_request"]`` for a nested SHA field."""
    if not isinstance(event, dict):
        return None
    node: Any = event.get("pull_request")
    if not isinstance(node, dict):
        return None
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) and node.strip() else None


def collect_ci_metadata(env: Mapping[str, str] | None = None) -> CIMetadata:
    """Collect GitHub Actions metadata from ``env`` (default: os.environ).

    Only ``CI_ALLOWLIST`` keys are read. Missing values stay ``None``;
    a malformed ``GITHUB_RUN_ATTEMPT`` raises :class:`ValueError`.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    values = {key: _clean(source.get(key)) for key in CI_ALLOWLIST}

    event, event_error = _load_event(values["GITHUB_EVENT_PATH"])

    head_sha = _pr_sha(event, "head", "sha")
    event_merge_sha = _pr_sha(event, "merge_commit_sha")

    is_github = any(
        values[key] is not None
        for key in (
            "GITHUB_RUN_ID",
            "GITHUB_SHA",
            "GITHUB_WORKFLOW",
            "GITHUB_JOB",
            "GITHUB_EVENT_NAME",
            "GITHUB_REPOSITORY",
        )
    )
    return CIMetadata(
        is_github=is_github,
        provider="github-actions" if is_github else "generic",
        run_id=values["GITHUB_RUN_ID"],
        run_attempt=_parse_run_attempt(values["GITHUB_RUN_ATTEMPT"]),
        workflow=values["GITHUB_WORKFLOW"],
        job=values["GITHUB_JOB"],
        event_name=values["GITHUB_EVENT_NAME"],
        github_sha=values["GITHUB_SHA"],
        github_ref=values["GITHUB_REF"],
        repository=values["GITHUB_REPOSITORY"],
        workspace=values["GITHUB_WORKSPACE"],
        runner_os=values["RUNNER_OS"],
        runner_arch=values["RUNNER_ARCH"],
        head_sha=head_sha,
        event_merge_sha=event_merge_sha,
        event=event,
        event_error=event_error,
    )
