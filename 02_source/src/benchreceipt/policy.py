"""Policy types and TOML loading (P027-T002; completed in P027-T007).

A policy is the parsed form of ``.benchreceipt.toml`` (PROJECT_BOOK §6.3),
validated against ``benchreceipt.policy/v1``. The fail-closed rule
(PROJECT_BOOK §5.6) applies at load time:

- A policy missing any required field, with a wrong enum, or with
  malformed TOML raises :class:`PolicyInvalid`. It is NEVER silently
  replaced by a default that could pass verification.
- The one safe default: a missing ``[security]`` section (or missing
  fields inside it) normalises to ``store_stdout = store_stderr =
  store_full_environment = false`` — the direction that stores *less*,
  never more. Storing is opt-in and explicit.
- ``PolicyInvalid`` messages name EVERY missing/invalid field, not just
  the first: the schema validator collects all violations and they are
  joined into one message, so a caller can fix the whole policy at once.
- Unknown top-level or section keys are rejected (the frozen schema
  sets ``additionalProperties: false`` everywhere), including
  ``expected_source_sha`` and run-identity fields, which are supplied
  to ``verify`` on the command line, not stored in the policy
  (ADR-001 decision 12).

Standard library only (``tomllib`` + :mod:`benchreceipt.schema`).
No third-party validator; runtime dependencies stay empty.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from benchreceipt.schema import SchemaValidationError, validate_against_schema

__all__ = ["PolicyInvalid", "load_policy", "validate_policy"]

# Security fields and their safe default. Frozen by benchreceipt.policy/v1.
SECURITY_FIELDS = ("store_stdout", "store_stderr", "store_full_environment")

# Run-identity fields that must NEVER appear in a policy (ADR-001
# decision 12): the expected source SHA and the run/attempt identity are
# supplied to `verify` on the command line, not stored in the policy.
# The frozen schema already rejects any unknown top-level key
# (`additionalProperties: false`); this set names the forbidden ones
# explicitly so the error message says *why* they are rejected.
FORBIDDEN_RUN_IDENTITY_FIELDS = (
    "expected_source_sha",
    "expected_run_id",
    "run_id",
    "workflow_run_id",
    "expected_attempt",
    "run_attempt",
)


class PolicyInvalid(ValueError):
    """Raised when a policy file cannot be loaded or fails validation.

    A policy in this state is INVALID (exit 3 at the CLI, T008) — it must
    never be treated as an empty/accepting policy.
    """


def validate_policy(data: Any) -> dict[str, Any]:
    """Validate a parsed (TOML-decoded) policy dict and return a
    normalised copy.

    Normalisation only fills the safe security defaults (all ``False``).
    Every other field must be present and valid as written; missing or
    wrong values raise :class:`PolicyInvalid`, with a message naming
    every missing/invalid field (not just the first).
    """
    if not isinstance(data, dict):
        raise PolicyInvalid(f"policy must be a TOML table, got {type(data).__name__}")
    # Defence in depth, before schema validation so the message is
    # explicit: run-identity fields are never policy fields (ADR-001
    # decision 12), and an empty required_jobs list would make the
    # matrix check vacuous. The schema would reject both as well
    # (additionalProperties false / minItems 1); this names the cause.
    forbidden = [f for f in FORBIDDEN_RUN_IDENTITY_FIELDS if f in data]
    if forbidden:
        raise PolicyInvalid(
            "policy must not contain run-identity field(s) "
            + ", ".join(sorted(forbidden))
            + ": expected_source_sha / run identity are supplied to verify "
            "on the command line, not stored in the policy"
        )
    if isinstance(data.get("required_jobs"), list) and len(data["required_jobs"]) == 0:
        raise PolicyInvalid(
            "policy required_jobs must be non-empty: an empty expected "
            "job set would pass the matrix check vacuously"
        )
    try:
        validate_against_schema(data, "policy")
    except SchemaValidationError as exc:
        raise PolicyInvalid("; ".join(exc.errors)) from exc

    normalised = dict(data)
    security = data.get("security")
    if security is None:
        security = {}
    elif not isinstance(security, dict):
        raise PolicyInvalid("policy [security] must be a table")
    merged = {field: security.get(field, False) for field in SECURITY_FIELDS}
    normalised["security"] = merged
    return normalised


def load_policy(path: str | Path) -> dict[str, Any]:
    """Load and validate the policy at ``path``.

    Raises :class:`PolicyInvalid` when the file is missing, unreadable,
    not valid TOML, or fails ``benchreceipt.policy/v1`` — never returns a
    default policy.
    """
    path = Path(path)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise PolicyInvalid(f"cannot read policy file {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise PolicyInvalid(f"policy file {path} is not valid TOML: {exc}") from exc
    return validate_policy(data)
