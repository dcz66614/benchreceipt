"""Matrix aggregator (P027-T007, PROJECT_BOOK §5.2).

Pure functions over job-id sets. Job identity is the ``job_id`` string
only — matrix values do not change job identity (``job_id`` is the
stable identity per PROJECT_BOOK §5.1); this module therefore takes
plain ``job_id`` strings and nothing else.

Given the expected job set ``E`` (``policy.required_jobs``) and the
actual job ids ``A`` (one entry per receipt instance, duplicates kept):

- ``missing = E - A``
- ``unexpected = A - E``
- ``duplicate = {x | count_A(x) > 1}``

All three lists are returned sorted, so output is deterministic for
any input order. An empty expected list is :class:`PolicyInvalid`,
never an empty-set pass: a policy with no required jobs would make
the matrix check vacuous (ADR-001 decision 6 / T002 rule that missing
fields never default to pass; ``required_jobs`` is already required
non-empty by ``policy.v1.json`` — this is defence in depth here too).

Reason-code mapping (frozen in ``02_source/docs/REASON_CODES.md``;
this module returns the sets, the verifier maps them to codes):

- non-empty ``missing``    -> ``MATRIX_MISSING_JOB`` (UNBOUND)
- non-empty ``unexpected`` -> ``MATRIX_UNEXPECTED_JOB`` (UNBOUND)
- non-empty ``duplicate``  -> ``MATRIX_DUPLICATE_JOB`` (UNBOUND)

Standard library only. No network access, no I/O.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

from benchreceipt.policy import PolicyInvalid

__all__ = ["aggregate_matrix"]


def aggregate_matrix(
    expected_jobs: Sequence[str],
    actual_job_ids: Sequence[str],
) -> dict[str, list[str]]:
    """Compute the §5.2 matrix diff between expected and actual jobs.

    ``expected_jobs`` is the required set (``policy.required_jobs``);
    ``actual_job_ids`` is one ``job_id`` per receipt instance, with
    duplicates kept so they can be counted. Returns
    ``{"missing": [...], "unexpected": [...], "duplicate": [...]}``
    with every list sorted.

    Raises :class:`PolicyInvalid` (fail-closed) when the inputs cannot
    describe a real matrix check: an empty or non-list ``expected_jobs``,
    a duplicated or non-string/empty entry in ``expected_jobs``, or a
    non-list / non-string entry in ``actual_job_ids``. An empty
    ``actual_job_ids`` is *valid* input (everything is missing); an
    empty ``expected_jobs`` is not.
    """
    if not isinstance(expected_jobs, (list, tuple)):
        raise PolicyInvalid(
            "policy required_jobs must be a list of job ids, "
            f"got {type(expected_jobs).__name__}"
        )
    if len(expected_jobs) == 0:
        raise PolicyInvalid(
            "policy required_jobs must be non-empty: an empty expected "
            "job set would pass the matrix check vacuously"
        )
    for job_id in expected_jobs:
        if not isinstance(job_id, str) or not job_id:
            raise PolicyInvalid(
                "policy required_jobs must contain non-empty string job ids, "
                f"got {job_id!r}"
            )
    if len(set(expected_jobs)) != len(expected_jobs):
        raise PolicyInvalid(
            "policy required_jobs must not contain duplicate job ids: "
            f"{sorted(set(j for j in expected_jobs if expected_jobs.count(j) > 1))}"
        )
    if not isinstance(actual_job_ids, (list, tuple)):
        raise PolicyInvalid(
            "actual job ids must be a list of job id strings, "
            f"got {type(actual_job_ids).__name__}"
        )
    for job_id in actual_job_ids:
        if not isinstance(job_id, str) or not job_id:
            raise PolicyInvalid(
                "actual job ids must be non-empty string job ids, "
                f"got {job_id!r}"
            )

    expected_set = set(expected_jobs)
    counts: Counter[str] = Counter(actual_job_ids)
    actual_set = set(counts)
    return {
        "missing": sorted(expected_set - actual_set),
        "unexpected": sorted(actual_set - expected_set),
        "duplicate": sorted(job_id for job_id, count in counts.items() if count > 1),
    }
