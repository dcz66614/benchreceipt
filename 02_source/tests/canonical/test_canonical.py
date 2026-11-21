"""Canonical JSON tests (P027-T002).

Vectors in vectors.json were computed independently of the implementation
(shell hashlib over literal byte strings), so agreement here is real
evidence, not the module agreeing with itself.
"""

import json
import math
from pathlib import Path

import pytest

from benchreceipt.canonical import canonical_hash, canonical_json

VECTORS_PATH = Path(__file__).resolve().parent / "vectors.json"


def _load_vectors():
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))["vectors"]


def test_vectors_match_canonical_bytes_and_hash():
    vectors = _load_vectors()
    assert len(vectors) >= 5, "at least 5 hand-written vectors are required"
    for vector in vectors:
        expected_bytes = vector["canonical"].encode("utf-8")
        assert canonical_json(vector["input"]) == expected_bytes, vector["id"]
        assert canonical_hash(vector["input"]) == vector["sha256"], vector["id"]


def test_determinism_key_order_shuffled():
    first = {"b": 1, "a": {"d": 4, "c": 3}, "z": [1, 2, 3]}
    second = {"z": [1, 2, 3], "a": {"c": 3, "d": 4}, "b": 1}
    assert canonical_json(first) == canonical_json(second)
    assert canonical_hash(first) == canonical_hash(second)


def test_determinism_repeated_calls_identical():
    obj = {"job_id": "unit-linux-py312", "matrix": {"os": "ubuntu-latest"}}
    hashes = {canonical_hash(obj) for _ in range(100)}
    assert hashes == {canonical_hash(obj)}
    assert len(hashes) == 1


def test_compact_separators_no_whitespace():
    assert canonical_json({"a": 1, "b": [1, 2]}) == b'{"a":1,"b":[1,2]}'


def test_nan_and_infinity_rejected():
    with pytest.raises(ValueError):
        canonical_json({"x": math.nan})
    with pytest.raises(ValueError):
        canonical_json({"x": math.inf})


def test_non_serialisable_rejected():
    with pytest.raises(TypeError):
        canonical_json({"x": object()})
