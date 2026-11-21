"""Command-line interface for BenchReceipt (P027-T008).

PROJECT_BOOK §6.4 contract::

    benchreceipt capture --job <id> --matrix k=v,... [--junit <path>]
        [--lcov <path>] [--source-mode explicit_sha --expected-sha <40-hex>]
        -- <command> [args...]
    benchreceipt verify --policy <toml> --evidence <dir>
        --expected-source-sha <40-hex>
        [--expected-run-id <id>] [--expected-attempt <n>] --out <json>
    benchreceipt report --input <verification.json> --html <path>
    benchreceipt bundle --evidence <dir> --out <dir>
    benchreceipt bundle --verify <dir>

Exit codes (PROJECT_BOOK §5.6): BOUND_PASS 0, BOUND_FAIL 1, UNBOUND 2,
INVALID 3, INTERNAL_ERROR 4. Missing evidence, a parse failure, an
unreadable input, or an unknown field never degrades to PASS: the
verifier returns UNBOUND or INVALID for those, and this CLI maps the
status straight through. A missing ``--expected-source-sha`` is
INVALID (exit 3), never a pass — so the flag is deliberately *not*
marked required by argparse (argparse would exit 2); it is checked
here and rejected with exit 3.

- ``capture`` delegates to :mod:`benchreceipt.capture` (its own
  argument parser owns the ``--job`` / ``--matrix`` / ``--`` contract);
  the process exit code is the wrapped command's exit code, and a
  failure receipt is still written when the command fails.
- ``verify`` loads the policy with :func:`benchreceipt.policy.load_policy`,
  calls :func:`benchreceipt.verify.evaluate_with_policy_path`, writes
  the result JSON (validated against ``benchreceipt.result/v1``) to
  ``--out``, and exits per §5.6.
- ``report`` renders a validated ``benchreceipt.result/v1`` input to
  a single self-contained HTML evidence-chain page via
  :mod:`benchreceipt.render.html`. It exits 0 on valid input and 3 on
  invalid input or a rendering failure. It never re-runs verification
  and never touches the verification JSON.
- ``bundle`` delegates to :mod:`benchreceipt.bundle`: build mode
  (``--evidence`` + ``--out``) copies an evidence tree and writes the
  manifest; verify mode (``--verify``) re-checks a bundle dir. A
  bundle that fails integrity verification exits 3 (hash damage is
  INVALID per §5.6); a structurally unusable bundle input exits 3 as
  well.

Any unexpected internal exception is caught at the top level, reported
as one short line on stderr, and exits 4 (INTERNAL_ERROR) — never a
traceback-as-pass and never exit 0. Usage errors from argparse exit 2,
as usual.

Standard library only. Offline by construction.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

from benchreceipt.bundle import BundleError, build_bundle, verify_bundle
from benchreceipt.render.html import render_report
from benchreceipt.schema import SchemaValidationError, validate_against_schema
from benchreceipt.verify import (
    evaluate_with_policy_path,
    status_to_exit_code,
)

__all__ = ["build_parser", "main"]

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_ATTEMPT = 100000


def _short(text: str, limit: int = 200) -> str:
    """One short single-line form of an error message for stderr."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the whole ``benchreceipt`` program.

    The ``capture`` subcommand is listed here for ``--help`` only: its
    arguments are parsed by :mod:`benchreceipt.capture` (see
    :func:`main`, which hands ``capture`` off before this parser runs).
    """
    parser = argparse.ArgumentParser(
        prog="benchreceipt",
        description=(
            "Local-first CI test-evidence binding: capture per-job "
            "receipts, verify them against a policy, and report the "
            "binding verdict."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    subparsers.add_parser(
        "capture",
        help="wrap a test command and write a benchreceipt.run/v1 receipt",
        description=(
            "Wrap an explicit test command and write a "
            "benchreceipt.run/v1 receipt. See "
            "`benchreceipt capture --help` for the flags."
        ),
    )

    p_verify = subparsers.add_parser(
        "verify",
        help="verify an evidence bundle against a policy",
        description=(
            "Verify an evidence bundle against a policy and an expected "
            "source SHA. Writes a benchreceipt.result/v1 JSON file and "
            "exits 0 (BOUND_PASS), 1 (BOUND_FAIL), 2 (UNBOUND), "
            "3 (INVALID) or 4 (INTERNAL_ERROR)."
        ),
    )
    p_verify.add_argument("--policy", required=True, help="policy TOML file (.benchreceipt.toml)")
    p_verify.add_argument("--evidence", required=True, help="evidence directory (one subdir per job)")
    p_verify.add_argument(
        "--expected-source-sha",
        default=None,
        metavar="SHA",
        help="40-hex source SHA every job's git.head_sha must equal (required; missing/invalid -> exit 3)",
    )
    p_verify.add_argument(
        "--expected-run-id",
        default=None,
        metavar="ID",
        help="optional: run id every job's ci.run_id must equal",
    )
    p_verify.add_argument(
        "--expected-attempt",
        default=None,
        type=int,
        metavar="N",
        help="optional: run attempt (1..100000) every job's ci.run_attempt must equal",
    )
    p_verify.add_argument("--out", required=True, help="output path for the verification result JSON")

    p_report = subparsers.add_parser(
        "report",
        help="render a verification result as self-contained HTML",
        description=(
            "Render a benchreceipt.result/v1 JSON file as a single "
            "self-contained HTML evidence-chain page (inline CSS/JS "
            "only, no external resources). The renderer reads only the "
            "verification JSON; it never re-runs verification."
        ),
    )
    p_report.add_argument("--input", required=True, help="verification result JSON file")
    p_report.add_argument("--html", required=True, help="output path for the HTML page")

    p_bundle = subparsers.add_parser(
        "bundle",
        help="build or verify a portable evidence bundle",
        description=(
            "Build a portable evidence bundle (`--evidence <dir> "
            "--out <dir>`) or verify one (`--verify <dir>`)."
        ),
    )
    p_bundle.add_argument("--evidence", default=None, help="evidence directory to bundle (build mode)")
    p_bundle.add_argument("--out", default=None, help="output directory for the bundle (build mode)")
    p_bundle.add_argument("--verify", default=None, metavar="DIR", help="bundle directory to verify (verify mode)")

    return parser


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def _cmd_verify(args: argparse.Namespace) -> int:
    """Run the ``verify`` subcommand. Returns the §5.6 exit code."""
    sha = args.expected_source_sha
    if sha is None:
        print(
            "benchreceipt verify: error: --expected-source-sha is required "
            "(missing evidence identity must never pass)",
            file=sys.stderr,
        )
        return 3
    if not _SHA40_RE.match(sha):
        print(
            "benchreceipt verify: error: --expected-source-sha must be a "
            "40-character lowercase hex SHA",
            file=sys.stderr,
        )
        return 3
    if args.expected_run_id is not None and not args.expected_run_id:
        print(
            "benchreceipt verify: error: --expected-run-id must not be empty",
            file=sys.stderr,
        )
        return 3
    if args.expected_attempt is not None and not 1 <= args.expected_attempt <= _MAX_ATTEMPT:
        print(
            "benchreceipt verify: error: --expected-attempt must be an "
            f"integer in 1..{_MAX_ATTEMPT}",
            file=sys.stderr,
        )
        return 3

    result = evaluate_with_policy_path(
        args.policy,
        sha,
        args.evidence,
        expected_run_id=args.expected_run_id,
        expected_attempt=args.expected_attempt,
    )
    try:
        validate_against_schema(result, "result")
    except SchemaValidationError:
        # The verifier produced a result outside its own frozen schema:
        # a verifier bug, never a finding to write out as a pass.
        print(
            "benchreceipt verify: error: internal error: verification "
            "result failed benchreceipt.result/v1 validation",
            file=sys.stderr,
        )
        return 4

    out_path = Path(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(
            f"benchreceipt verify: error: cannot write {args.out}: {_short(exc)}",
            file=sys.stderr,
        )
        return 4

    status = result["status"]
    codes = ",".join(result["reason_codes"]) or "-"
    print(
        f"benchreceipt verify: status={status} "
        f"jobs_verified={result['jobs_verified']} "
        f"reason_codes={codes} out={out_path}"
    )
    return status_to_exit_code(status)


# ---------------------------------------------------------------------------
# report (P027-T010 static HTML renderer)
# ---------------------------------------------------------------------------


def _cmd_report(args: argparse.Namespace) -> int:
    """Run the ``report`` subcommand. Exit 0 on valid input, 3 on
    invalid input or a rendering failure. The verification JSON is
    only read, never modified: a rendering failure leaves it intact."""
    input_path = Path(args.input)
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(
            f"benchreceipt report: error: cannot read verification result "
            f"{args.input}: {_short(exc)}",
            file=sys.stderr,
        )
        return 3
    try:
        validate_against_schema(data, "result")
    except SchemaValidationError as exc:
        print(
            "benchreceipt report: error: input is not a valid "
            f"benchreceipt.result/v1: {_short(exc)}",
            file=sys.stderr,
        )
        return 3

    html_path = Path(args.html)
    try:
        render_report(data, html_path)
    except (ValueError, OSError) as exc:
        print(
            f"benchreceipt report: error: cannot render {args.html}: {_short(exc)}",
            file=sys.stderr,
        )
        return 3
    print(f"benchreceipt report: status={data['status']} html={html_path}")
    return 0


# ---------------------------------------------------------------------------
# bundle
# ---------------------------------------------------------------------------


def _cmd_bundle(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Run the ``bundle`` subcommand (build or verify mode)."""
    if args.verify is not None:
        if args.evidence is not None or args.out is not None:
            parser.error("--verify cannot be combined with --evidence/--out")
        try:
            result = verify_bundle(args.verify)
        except BundleError as exc:
            print(f"benchreceipt bundle: error: {_short(exc)}", file=sys.stderr)
            return 3
        if result.ok:
            print(
                f"benchreceipt bundle: ok: {result.files_checked} files "
                f"checked, {result.manifest_files} manifest entries"
            )
            return 0
        for problem in result.problems:
            print(
                f"benchreceipt bundle: {problem['code']}: "
                f"{problem['path']}: {problem['message']}",
                file=sys.stderr,
            )
        return 3
    if args.evidence is None or args.out is None:
        parser.error(
            "bundle needs --evidence <dir> --out <dir> to build, "
            "or --verify <dir> to verify"
        )
    try:
        summary = build_bundle(args.evidence, args.out)
    except BundleError as exc:
        print(f"benchreceipt bundle: error: {_short(exc)}", file=sys.stderr)
        return 3
    print(
        f"benchreceipt bundle: built {summary['files']} files, "
        f"{summary['total_bytes']} bytes, "
        f"manifest sha256={summary['sha256']}, out={summary['out_dir']}"
    )
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """``benchreceipt`` entry point. Returns a process exit code.

    ``capture`` is handed to :mod:`benchreceipt.capture` before this
    module's own parser runs, because that module owns the ``--job`` /
    ``--matrix`` / ``--`` contract. Every other subcommand is parsed
    here. An unexpected internal exception anywhere returns 4
    (INTERNAL_ERROR); argparse usage errors raise ``SystemExit`` (2)
    and are not caught.
    """
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        if raw and raw[0] == "capture":
            from benchreceipt.capture import main as capture_main

            return capture_main(raw[1:])
        parser = build_parser()
        args = parser.parse_args(raw)
        if args.command == "verify":
            return _cmd_verify(args)
        if args.command == "report":
            return _cmd_report(args)
        if args.command == "bundle":
            return _cmd_bundle(args, parser)
        parser.error("no subcommand given")
    except Exception as exc:  # noqa: BLE001 — top-level fail-closed guard
        print(
            f"benchreceipt: internal error: {type(exc).__name__}: {_short(exc)}",
            file=sys.stderr,
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
