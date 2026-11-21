#!/usr/bin/env python3
"""Validate the GitHub Actions example workflow (P027-T009).

Checks ``02_source/examples/github-actions/ci.yml`` structurally:

1. The file parses as YAML (stdlib-only subset parser — no PyYAML
   needed; the workflow is deliberately written using only the subset
   below, and the parser rejects anything outside it rather than
   guessing).
2. Triggers include ``pull_request`` and ``push``.
3. The ``test`` job has an explicit matrix (``strategy.matrix.include``)
   whose job ids are unique, and the set of job ids EQUALS the
   ``required_jobs`` of ``02_source/examples/benchreceipt.toml``
   (workflow and policy must never silently diverge).
4. Every checkout step pins an explicit ``ref:`` containing
   ``github.event.pull_request.head.sha`` (the pr_head choice,
   PROJECT_BOOK §1.2 scenario A) — a default checkout to the merge
   commit is rejected.
5. A capture step runs ``benchreceipt capture`` with ``--job``,
   ``--matrix``, ``--junit`` and a ``-- python -m pytest`` command.
6. The per-job evidence upload uses ``actions/upload-artifact@v4``
   with a name and path containing the matrix job id.
7. The aggregate ``verify`` job ``needs:`` the matrix job, downloads
   EVERY expected job artifact by name (one step per job, each into
   ``.benchreceipt/evidence/<job-id>/``) BEFORE the verify step, and
   the verify step runs ``benchreceipt verify`` with ``--policy``,
   ``--evidence``, ``--expected-source-sha`` (containing
   ``github.event.pull_request.head.sha``) and ``--out``.
8. No GitHub API token anywhere: no ``github.token``, no ``secrets.``,
   no ``gh `` CLI invocation, no ``actions/github-script``.
9. BenchReceipt is installed from a local path only: every
   ``pip install`` line must reference a local path (``./`` or a
   ``.whl``); a bare ``pip install benchreceipt`` (PyPI fetch) is
   rejected.

Usage::

    python 02_source/scripts/validate_workflow_example.py \
        [--workflow PATH] [--policy PATH]

Exit 0 when every check passes, 1 otherwise (each failure is printed
as ``FAIL: <check>: <detail>``). The functions are importable so the
integration tests can exercise the negative cases directly:
``validate_workflow_text(text, required_jobs) -> list[str]``.

The YAML subset the parser accepts (everything ``ci.yml`` uses, and
nothing it does not need):

- ``#`` comments (a ``#`` inside a quoted scalar is data, not a comment);
- ``---`` document markers; ``key: value`` and ``key:`` nested mappings
  (2-space indentation; tabs are rejected);
- ``- item`` sequences, including ``- key: value`` mapping items;
- plain, single-quoted and double-quoted scalars;
- literal block scalars (``|`` / ``|-`` / ``|+``);
- duplicate keys at one mapping level are rejected.

Anything else — flow collections (``[a, b]`` / ``{k: v}``), anchors
(``&`` / ``*``), folded scalars (``>``), multi-line plain scalars,
keys that are not plain scalars — is rejected with a clear error
rather than silently mis-parsed. That is deliberate: a validator that
guesses at YAML it cannot parse could certify a workflow it did not
understand.

Standard library only. No network access.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

__all__ = [
    "WorkflowValidationError",
    "load_required_jobs",
    "parse_yaml_subset",
    "validate_workflow_text",
]

SOURCE = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = SOURCE / "examples" / "github-actions" / "ci.yml"
DEFAULT_POLICY = SOURCE / "examples" / "benchreceipt.toml"

# --- tokens that must never appear in a token-free workflow -------------
_FORBIDDEN_TEXT = (
    ("github.token", "uses github.token (a GitHub API token)"),
    ("secrets.", "uses secrets.* (a GitHub API token / secret)"),
    ("actions/github-script", "uses actions/github-script (GitHub API access)"),
)
_FORBIDDEN_RUN_RE = re.compile(r"(^|\s)gh\s+[a-z]", re.IGNORECASE)
_PIP_INSTALL_RE = re.compile(r"pip\s+install\b([^#\n]*)")


class WorkflowValidationError(ValueError):
    """The workflow text is not parseable YAML in the accepted subset."""


# ---------------------------------------------------------------------------
# Minimal YAML-subset parser
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment, honouring quoted scalars."""
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            if i == 0 or line[i - 1] != "\\":
                in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip()
    return line.rstrip()


def _unquote(scalar: str) -> str:
    """Interpret a YAML scalar: quoted scalars unescaped, plain as-is."""
    scalar = scalar.strip()
    if len(scalar) >= 2 and scalar[0] == scalar[-1] == '"':
        return bytes(scalar[1:-1], "utf-8").decode("unicode_escape")
    if len(scalar) >= 2 and scalar[0] == scalar[-1] == "'":
        return scalar[1:-1].replace("''", "'")
    return scalar


def _split_key_value(text: str) -> tuple[str, str] | None:
    """Split ``key: value`` / ``key:`` at the first top-level ``: ``.

    Returns ``(key, value)`` with the value possibly empty, or None when
    the text is not a mapping entry. A ``:`` inside a quoted scalar or
    inside ``${{ ... }}`` does not split.
    """
    in_single = in_double = False
    depth = 0
    for i, ch in enumerate(text):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            if i == 0 or text[i - 1] != "\\":
                in_double = not in_double
        elif not in_single and not in_double:
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
            elif ch == ":" and depth == 0:
                rest = text[i + 1 :]
                if rest == "" or rest[0] in " \t":
                    return text[:i].strip(), rest.strip()
    return None


def _parse_block(lines: list[tuple[int, str]], pos: int, indent: int) -> tuple[object, int]:
    """Parse one block (mapping or sequence) starting at ``pos``.

    ``lines`` is ``(indent, text)`` pairs with blanks/comments removed.
    Returns ``(value, next_pos)``. Raises WorkflowValidationError on
    anything outside the accepted subset.
    """
    if pos >= len(lines):
        return {}, pos
    first_indent, first_text = lines[pos]
    if first_indent < indent:
        return {}, pos
    if first_text.startswith("- ") or first_text == "-":
        return _parse_sequence(lines, pos, first_indent)
    return _parse_mapping(lines, pos, first_indent)


def _parse_mapping(lines: list[tuple[int, str]], pos: int, indent: int) -> tuple[dict, int]:
    result: dict[str, object] = {}
    while pos < len(lines):
        line_indent, text = lines[pos]
        if line_indent != indent or text.startswith("- ") or text == "-":
            break
        split = _split_key_value(text)
        if split is None:
            raise WorkflowValidationError(
                f"line {pos + 1}: not a 'key: value' mapping entry: {text!r}"
            )
        key_raw, value_raw = split
        key = _unquote(key_raw)
        if not key or key_raw[:1] in "[{&*":
            raise WorkflowValidationError(
                f"line {pos + 1}: unsupported mapping key: {key_raw!r}"
            )
        if key in result:
            raise WorkflowValidationError(
                f"line {pos + 1}: duplicate key {key!r} at one mapping level"
            )
        if value_raw.startswith(("[", "{", "&", "*")):
            raise WorkflowValidationError(
                f"line {pos + 1}: flow collections / anchors are not "
                f"supported by this validator: {text!r}"
            )
        if value_raw in ("|", "|-", "|+"):
            block, pos = _parse_literal_block(lines, pos + 1, indent)
            result[key] = block
            continue
        if value_raw.startswith(">"):
            raise WorkflowValidationError(
                f"line {pos + 1}: folded block scalars ('>') are not "
                f"supported by this validator: {text!r}"
            )
        if value_raw != "":
            result[key] = _unquote(value_raw)
            pos += 1
            continue
        # Empty value: nested block, or null when nothing follows.
        if pos + 1 < len(lines) and lines[pos + 1][0] > indent:
            value, pos = _parse_block(lines, pos + 1, lines[pos + 1][0])
            result[key] = value
        else:
            result[key] = None
            pos += 1
    return result, pos


def _parse_sequence(lines: list[tuple[int, str]], pos: int, indent: int) -> tuple[list, int]:
    result: list[object] = []
    while pos < len(lines):
        line_indent, text = lines[pos]
        if line_indent != indent or not (text.startswith("- ") or text == "-"):
            break
        item_text = text[1:].strip()
        if item_text == "":
            if pos + 1 < len(lines) and lines[pos + 1][0] > indent:
                value, pos = _parse_block(lines, pos + 1, lines[pos + 1][0])
                result.append(value)
            else:
                result.append(None)
                pos += 1
            continue
        split = _split_key_value(item_text)
        if split is None:
            if item_text.startswith(("[", "{", "&", "*")):
                raise WorkflowValidationError(
                    f"line {pos + 1}: flow collections / anchors are not "
                    f"supported by this validator: {text!r}"
                )
            result.append(_unquote(item_text))
            pos += 1
            continue
        # "- key: value" — a mapping whose first entry is on the dash line.
        # The item's continuation lines are the following lines that are
        # indented deeper than the dash, stopping at the next item (a
        # line at the dash indent or less). Only those lines belong to
        # this item; taking every deeper line in the file would merge
        # later items into this one.
        continuation: list[tuple[int, str]] = []
        for ln in lines[pos + 1 :]:
            if ln[0] <= indent:
                break
            continuation.append(ln)
        sub_lines = [(indent + 2, item_text)] + continuation
        mapping, _ = _parse_mapping(sub_lines, 0, indent + 2)
        result.append(mapping)
        pos += 1 + len(continuation)
    return result, pos


def _parse_literal_block(
    lines: list[tuple[int, str]], pos: int, parent_indent: int
) -> tuple[str, int]:
    """Collect an indented literal block scalar (``|``) as one string."""
    collected: list[str] = []
    while pos < len(lines) and lines[pos][0] > parent_indent:
        collected.append(lines[pos][1])
        pos += 1
    return "\n".join(collected) + ("\n" if collected else ""), pos


def parse_yaml_subset(text: str) -> dict:
    """Parse YAML in the accepted subset into plain dicts/lists/strings.

    Raises :class:`WorkflowValidationError` on tabs, on anything
    outside the subset, and when the top level is not a mapping.
    """
    if "\t" in text:
        raise WorkflowValidationError("tab characters are not valid YAML indentation")
    raw_lines: list[tuple[int, str]] = []
    for line in text.splitlines():
        if line.strip() == "" or line.strip() == "---" or line.strip() == "...":
            continue
        stripped = _strip_comment(line)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        raw_lines.append((indent, stripped.strip()))
    if not raw_lines:
        raise WorkflowValidationError("empty workflow file")
    value, _ = _parse_mapping(raw_lines, 0, raw_lines[0][0])
    if not isinstance(value, dict):
        raise WorkflowValidationError("top level of a workflow must be a mapping")
    return value


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def load_required_jobs(policy_path: str | Path) -> list[str]:
    """Read ``required_jobs`` from the example policy TOML file."""
    path = Path(policy_path)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise WorkflowValidationError(f"cannot read policy file {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise WorkflowValidationError(f"policy file {path} is not valid TOML: {exc}") from exc
    jobs = data.get("required_jobs")
    if not isinstance(jobs, list) or not jobs or not all(isinstance(j, str) for j in jobs):
        raise WorkflowValidationError(
            f"policy file {path} has no usable required_jobs list"
        )
    return list(jobs)


def _steps_of(job: object) -> list[dict]:
    if not isinstance(job, dict):
        return []
    steps = job.get("steps")
    return steps if isinstance(steps, list) else []


def _step_text(step: dict) -> str:
    parts = []
    for key in ("uses", "run", "name", "with"):
        value = step.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            parts.append(" ".join(f"{k}={v}" for k, v in value.items() if isinstance(v, str)))
    return "\n".join(parts)


def validate_workflow_text(text: str, required_jobs: list[str]) -> list[str]:
    """Validate workflow ``text`` against the T009 checks.

    Returns the list of failure messages (empty = PASS). A YAML parse
    failure is reported as a single failure, not raised.
    """
    errors: list[str] = []

    # --- 8/9. Raw-text bans (token / API / network install) -------------
    # Checked against comment-stripped text: the header comments of
    # ci.yml *mention* `github.token` / `secrets.*` in prose to say they
    # are forbidden, and that prose must not trip the ban. A token in
    # actual YAML (including inside a quoted scalar, which
    # _strip_comment honours) still trips it.
    code_text = "\n".join(_strip_comment(line) for line in text.splitlines())
    for token, why in _FORBIDDEN_TEXT:
        if token in code_text:
            errors.append(f"token-free: workflow {why}")
    for match in _FORBIDDEN_RUN_RE.finditer(code_text):
        errors.append(
            f"token-free: workflow invokes the gh CLI ({match.group(0).strip()!r})"
        )
    for match in _PIP_INSTALL_RE.finditer(code_text):
        args = match.group(1).strip()
        if "./" not in args and ".whl" not in args:
            errors.append(
                f"local-install: 'pip install {args}' does not install "
                "BenchReceipt from a local path (./... or a .whl)"
            )

    try:
        doc = parse_yaml_subset(text)
    except WorkflowValidationError as exc:
        return errors + [f"yaml-parse: {exc}"]

    # --- 2. Triggers -------------------------------------------------------
    on = doc.get("on")
    if isinstance(on, str):
        triggers = [on]
    elif isinstance(on, dict):
        triggers = list(on)
    elif isinstance(on, list):
        triggers = [str(t) for t in on]
    else:
        triggers = []
    for wanted in ("pull_request", "push"):
        if wanted not in triggers:
            errors.append(f"triggers: workflow does not trigger on {wanted}")

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append("jobs: workflow has no jobs mapping")
        return errors

    # --- 3. Matrix job ------------------------------------------------------
    test_job = jobs.get("test")
    if not isinstance(test_job, dict):
        errors.append("matrix: no job named 'test'")
        return errors
    strategy = test_job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    include = matrix.get("include") if isinstance(matrix, dict) else None
    matrix_jobs: list[str] = []
    if not isinstance(include, list) or not include:
        errors.append("matrix: test job has no strategy.matrix.include list")
    else:
        for cell in include:
            if not isinstance(cell, dict):
                errors.append(f"matrix: matrix cell is not a mapping: {cell!r}")
                continue
            for field in ("os", "python", "job_id"):
                if field not in cell:
                    errors.append(f"matrix: matrix cell missing {field!r}: {cell!r}")
            job_id = cell.get("job_id")
            if isinstance(job_id, str):
                matrix_jobs.append(job_id)
        if len(matrix_jobs) != len(set(matrix_jobs)):
            errors.append(f"matrix: duplicate job_id in matrix: {matrix_jobs!r}")
        if sorted(matrix_jobs) != sorted(required_jobs):
            errors.append(
                "matrix/policy: matrix job ids "
                f"{sorted(matrix_jobs)!r} do not equal policy required_jobs "
                f"{sorted(required_jobs)!r}"
            )
    if "matrix.os" not in str(test_job.get("runs-on", "")):
        errors.append("matrix: test job runs-on does not use ${{ matrix.os }}")

    # --- per-job steps ------------------------------------------------------
    test_steps = _steps_of(test_job)
    checkout_refs = [
        s for s in test_steps
        if isinstance(s.get("uses"), str) and s["uses"].startswith("actions/checkout@")
    ]
    if not checkout_refs:
        errors.append("checkout: test job has no actions/checkout step")
    for step in checkout_refs:
        ref = step.get("with", {}).get("ref", "") if isinstance(step.get("with"), dict) else ""
        if "github.event.pull_request.head.sha" not in str(ref):
            errors.append(
                "checkout: test job checkout ref does not select the PR "
                f"head SHA (github.event.pull_request.head.sha): {ref!r}"
            )
    if not any(
        isinstance(s.get("uses"), str) and s["uses"].startswith("actions/setup-python@")
        for s in test_steps
    ):
        errors.append("setup-python: test job has no actions/setup-python step")
    capture_steps = [
        s for s in test_steps
        if isinstance(s.get("run"), str) and "benchreceipt capture" in s["run"]
    ]
    if not capture_steps:
        errors.append("capture: test job has no 'benchreceipt capture' step")
    else:
        run = capture_steps[0]["run"]
        for flag in ("--job ${{ matrix.job_id }}", "--matrix", "--junit",
                     "-- python -m pytest"):
            if flag not in run:
                errors.append(f"capture: capture step is missing {flag!r}")
    upload_steps = [
        s for s in test_steps
        if isinstance(s.get("uses"), str) and s["uses"].startswith("actions/upload-artifact@")
    ]
    if not upload_steps:
        errors.append("upload: test job has no actions/upload-artifact step")
    else:
        step = upload_steps[0]
        with_ = step.get("with", {}) if isinstance(step.get("with"), dict) else {}
        name = str(with_.get("name", ""))
        path = str(with_.get("path", ""))
        if "matrix.job_id" not in name:
            errors.append(f"upload: artifact name does not contain matrix.job_id: {name!r}")
        if ".benchreceipt/evidence/${{ matrix.job_id }}" not in path:
            errors.append(
                "upload: artifact path is not "
                f".benchreceipt/evidence/${{{{ matrix.job_id }}}}: {path!r}"
            )

    # --- 7. Aggregate job ---------------------------------------------------
    verify_job = jobs.get("verify")
    if not isinstance(verify_job, dict):
        errors.append("aggregate: no job named 'verify'")
        return errors
    needs = verify_job.get("needs")
    needs_list = [needs] if isinstance(needs, str) else (needs if isinstance(needs, list) else [])
    if "test" not in needs_list:
        errors.append(f"aggregate: verify job does not need the test job (needs={needs_list!r})")
    verify_steps = _steps_of(verify_job)
    v_checkout = [
        s for s in verify_steps
        if isinstance(s.get("uses"), str) and s["uses"].startswith("actions/checkout@")
    ]
    for step in v_checkout:
        ref = step.get("with", {}).get("ref", "") if isinstance(step.get("with"), dict) else ""
        if "github.event.pull_request.head.sha" not in str(ref):
            errors.append(
                "checkout: verify job checkout ref does not select the PR "
                f"head SHA: {ref!r}"
            )
    download_steps: list[tuple[int, dict]] = [
        (i, s) for i, s in enumerate(verify_steps)
        if isinstance(s.get("uses"), str) and s["uses"].startswith("actions/download-artifact@")
    ]
    downloaded: dict[str, str] = {}
    for _, step in download_steps:
        with_ = step.get("with", {}) if isinstance(step.get("with"), dict) else {}
        downloaded[str(with_.get("name", ""))] = str(with_.get("path", ""))
    for job_id in required_jobs:
        artifact = f"benchreceipt-evidence-{job_id}"
        if artifact not in downloaded:
            errors.append(
                f"aggregate: verify job does not download artifact {artifact!r}"
            )
        elif downloaded[artifact] != f".benchreceipt/evidence/{job_id}":
            errors.append(
                "aggregate: download of "
                f"{artifact!r} goes to {downloaded[artifact]!r}, not "
                f".benchreceipt/evidence/{job_id}"
            )
    verify_steps_idx = [
        i for i, s in enumerate(verify_steps)
        if isinstance(s.get("run"), str) and "benchreceipt verify" in s["run"]
    ]
    if not verify_steps_idx:
        errors.append("aggregate: verify job has no 'benchreceipt verify' step")
    else:
        v_idx = verify_steps_idx[0]
        run = verify_steps[v_idx]["run"]
        for flag in ("--policy", "--evidence", "--expected-source-sha", "--out"):
            if flag not in run:
                errors.append(f"aggregate: verify step is missing {flag!r}")
        if "github.event.pull_request.head.sha" not in run:
            errors.append(
                "aggregate: verify step --expected-source-sha does not "
                "use github.event.pull_request.head.sha"
            )
        last_download = max((i for i, _ in download_steps), default=-1)
        if download_steps and v_idx < last_download:
            errors.append(
                "aggregate: verify step runs before all download-artifact "
                "steps have completed"
            )
    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 when the workflow passes, else 1."""
    parser = argparse.ArgumentParser(
        prog="validate_workflow_example",
        description=(
            "Validate the BenchReceipt GitHub Actions example workflow "
            "(P027-T009): structure, matrix/policy agreement, explicit "
            "pr_head checkout, capture/upload/aggregate steps, and the "
            "no-token / local-install rules."
        ),
    )
    parser.add_argument(
        "--workflow",
        default=str(DEFAULT_WORKFLOW),
        help="path to ci.yml (default: 02_source/examples/github-actions/ci.yml)",
    )
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY),
        help="path to the example policy TOML (default: 02_source/examples/benchreceipt.toml)",
    )
    args = parser.parse_args(argv)

    try:
        text = Path(args.workflow).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL: cannot read workflow file {args.workflow}: {exc}")
        return 1
    try:
        required_jobs = load_required_jobs(args.policy)
    except WorkflowValidationError as exc:
        print(f"FAIL: {exc}")
        return 1

    errors = validate_workflow_text(text, required_jobs)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"validate_workflow_example: {len(errors)} failure(s) in {args.workflow}")
        return 1
    print(
        "validate_workflow_example: PASS "
        f"({args.workflow}; {len(required_jobs)} matrix jobs, "
        "policy agreement + token-free + local-install checks OK)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
