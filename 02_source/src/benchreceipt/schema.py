"""Minimal stdlib-only JSON Schema validation (P027-T002).

The product runtime must have ZERO third-party dependencies (PROJECT_BOOK
§10), so this module implements the small subset of JSON Schema
(draft 2020-12) that the frozen ``benchreceipt.*`` schemas use, instead of
depending on ``jsonschema``:

- ``type`` (single type or list of types; ``"integer"`` excludes bool)
- ``const``, ``enum``
- ``required``, ``properties``, ``additionalProperties`` (bool or schema)
- ``propertyNames``, ``minProperties``, ``maxProperties``
- ``items``, ``minItems``, ``maxItems``, ``uniqueItems``
- ``minLength``, ``maxLength``, ``pattern`` (ECMA-style anchors as written)
- ``minimum``, ``maximum``
- ``$ref`` to a local ``#/...`` JSON pointer inside the same schema file

Keywords the schemas do not use (``format``, ``allOf``, ``anyOf``,
``oneOf``, ``not``, ``if``/``then``, ``dependentRequired`` …) are NOT
supported and are ignored if present. If a later task needs one of them,
extend this module deliberately — do not silently add a dependency.

Usage::

    from benchreceipt.schema import validate_against_schema
    validate_against_schema(receipt, "run")   # raises SchemaValidationError
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = [
    "SchemaValidationError",
    "load_schema",
    "validate",
    "validate_against_schema",
]

# Short name -> (schema file, canonical schema id).
SCHEMA_FILES = {
    "run": "run.v1.json",
    "policy": "policy.v1.json",
    "result": "result.v1.json",
    "benchreceipt.run/v1": "run.v1.json",
    "benchreceipt.policy/v1": "policy.v1.json",
    "benchreceipt.result/v1": "result.v1.json",
}


class SchemaValidationError(ValueError):
    """Raised by :func:`validate_against_schema` when data is invalid.

    Carries ``errors``: a list of human-readable ``"<path>: <message>"``
    strings, one per violated keyword.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("schema validation failed: " + "; ".join(self.errors))


def _schemas_dir() -> Path:
    """Locate the frozen schema files.

    Layout 1 (pre-move repo layout): ``02_source/schemas/`` — two
    directories above this module (``src/benchreceipt/schema.py``).
    That directory was removed by FIX-T014-F1 (schemas moved into the
    package); the candidate is kept only so an older checkout still
    resolves.
    Layout 2 (packaged): ``schemas/`` shipped as package data next to
    this module (``src/benchreceipt/schemas/``). Since FIX-T014-F1 this
    fires in both editable and installed layouts. Layout 1 wins when
    both exist.
    """
    candidates = [
        Path(__file__).resolve().parents[2] / "schemas",
        Path(__file__).resolve().parent / "schemas",
    ]
    for candidate in candidates:
        if (candidate / "run.v1.json").is_file():
            return candidate
    raise SchemaValidationError(
        [f"schema directory not found (looked in {[str(c) for c in candidates]})"]
    )


def load_schema(schema_name: str) -> dict[str, Any]:
    """Load a frozen schema by short name (``run``) or id
    (``benchreceipt.run/v1``). Raises ``KeyError`` for unknown names and
    ``SchemaValidationError`` if the file cannot be read or parsed.
    """
    filename = SCHEMA_FILES.get(schema_name)
    if filename is None:
        raise KeyError(f"unknown schema: {schema_name!r}")
    path = _schemas_dir() / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaValidationError([f"cannot load schema {filename}: {exc}"]) from exc


def _type_matches(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    if type_name == "integer":
        # bool is a subclass of int in Python; JSON Schema says it is not
        # an integer.
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    return False


def _resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local ``#/...`` JSON pointer against the schema root."""
    if not ref.startswith("#/"):
        raise SchemaValidationError([f"unsupported $ref (only local pointers): {ref!r}"])
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaValidationError([f"unresolvable $ref: {ref!r}"])
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaValidationError([f"$ref does not point at a schema object: {ref!r}"])
    return node


def _validate(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    if "$ref" in schema:
        _validate(value, _resolve_ref(schema["$ref"], root), root, path, errors)
        return

    type_names = schema.get("type")
    if type_names is not None:
        names = [type_names] if isinstance(type_names, str) else type_names
        if not any(_type_matches(value, name) for name in names):
            errors.append(
                f"{path}: expected type {'/'.join(names)}, got {type(value).__name__}"
            )
            return  # Further keywords are type-specific; stop here.

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']!r}")

    if isinstance(value, dict):
        for field in schema.get("required", []):
            if field not in value:
                errors.append(f"{path}: missing required field {field!r}")
        properties = schema.get("properties", {})
        for field, sub_schema in properties.items():
            if field in value:
                _validate(value[field], sub_schema, root, f"{path}.{field}", errors)
        additional = schema.get("additionalProperties", True)
        if additional is False:
            for field in value:
                if field not in properties:
                    errors.append(f"{path}: additional property {field!r} not allowed")
        elif isinstance(additional, dict):
            for field in value:
                if field not in properties:
                    _validate(value[field], additional, root, f"{path}.{field}", errors)
        if "propertyNames" in schema:
            for field in value:
                _validate(
                    field, schema["propertyNames"], root, f"{path} (property name)", errors
                )
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            errors.append(
                f"{path}: {len(value)} properties, fewer than minProperties "
                f"{schema['minProperties']}"
            )
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            errors.append(
                f"{path}: {len(value)} properties, more than maxProperties "
                f"{schema['maxProperties']}"
            )

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(
                f"{path}: {len(value)} items, fewer than minItems {schema['minItems']}"
            )
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(
                f"{path}: {len(value)} items, more than maxItems {schema['maxItems']}"
            )
        if schema.get("uniqueItems"):
            seen: list[str] = []
            for item in value:
                key = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    errors.append(f"{path}: duplicate item {item!r} (uniqueItems)")
                    break
                seen.append(key)
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(item, schema["items"], root, f"{path}[{index}]", errors)

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(
                f"{path}: string length {len(value)}, shorter than minLength "
                f"{schema['minLength']}"
            )
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(
                f"{path}: string length {len(value)}, longer than maxLength "
                f"{schema['maxLength']}"
            )
        if "pattern" in schema:
            try:
                match = re.search(schema["pattern"], value)
            except re.error as exc:
                errors.append(f"{path}: invalid pattern {schema['pattern']!r}: {exc}")
                return
            if not match:
                errors.append(
                    f"{path}: string {value!r} does not match pattern "
                    f"{schema['pattern']!r}"
                )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} is above maximum {schema['maximum']}")


def validate(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate ``data`` against a loaded schema dict.

    Returns the list of error strings (empty when valid). Does not raise.
    """
    errors: list[str] = []
    _validate(data, schema, schema, "$", errors)
    return errors


def validate_against_schema(data: Any, schema_name: str) -> None:
    """Validate ``data`` against a frozen schema (``run`` / ``policy`` /
    ``result``, or the full ``benchreceipt.<name>/v1`` id).

    Returns ``None`` on success; raises :class:`SchemaValidationError`
    with ``.errors`` on any violation.
    """
    schema = load_schema(schema_name)
    errors = validate(data, schema)
    if errors:
        raise SchemaValidationError(errors)
