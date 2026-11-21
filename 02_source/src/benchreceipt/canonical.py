"""Canonical JSON and deterministic digests (P027-T002).

Frozen rules (PROJECT_BOOK §5, §8.3 determinism; IMPLEMENTATION_PLAN §4):

- Keys sorted (``sort_keys=True``).
- UTF-8 encoding, ``ensure_ascii=False`` (non-ASCII is emitted as UTF-8,
  not ``\\uXXXX`` escapes).
- Compact separators (``","``, ``":"``) — no whitespace.
- ``allow_nan=False``: NaN / Infinity are rejected, never serialised,
  because they have no canonical JSON form and would break the
  100-replay / one-hash determinism gate.
- Digest = SHA-256 of the canonical bytes, lowercase hex.

Standard library only (``json``, ``hashlib``). No third-party deps.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["canonical_json", "canonical_hash"]


def canonical_json(obj: Any) -> bytes:
    """Return the canonical JSON encoding of ``obj`` as UTF-8 bytes.

    Raises ``TypeError`` for non-JSON-serialisable values (and for dicts
    whose keys are not mutually sortable strings) and ``ValueError``
    for NaN / Infinity. Both are fail-closed: a receipt that cannot be
    canonicalised cannot be digested, hashed, or verified.
    """
    text = json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8")


def canonical_hash(obj: Any) -> str:
    """Return the SHA-256 hex digest of :func:`canonical_json` of ``obj``.

    Key order is irrelevant: ``{"b": 1, "a": 2}`` and ``{"a": 2, "b": 1}``
    produce identical bytes and therefore identical digests.
    """
    return hashlib.sha256(canonical_json(obj)).hexdigest()
