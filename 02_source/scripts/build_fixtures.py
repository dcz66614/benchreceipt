#!/usr/bin/env python3
"""Build the 52 frozen S0 fixtures (P027-T004, PROJECT_BOOK §8.1; e5/e6
added by ADR-005, spec v1.1.0; e7/e8 added by ADR-007, spec v1.2.0).

Deterministic generator for ``02_source/fixtures/s0/<id>/``. Each fixture
holds ``policy.toml``, ``expected.json`` (the expected source SHA) and
``evidence/<job-dir>/receipt.json`` + ``artifacts/`` with real bytes whose
SHA-256 matches the receipt — except for the fixtures that *intentionally*
plant a mismatch, listed in ``INTENTIONAL`` below.

Every receipt is validated against ``benchreceipt.run/v1`` with the frozen
T002 validator before it is written, EXCEPT the one intentionally
schema-invalid fixture (``h4-missing-command``), which is the point of
that fixture: the verifier must return INVALID, not crash. The Golden
expected results are NOT produced here — they are hand-written in
``fixtures/s0/GOLDEN.json`` from the frozen rules (docs/REASON_CODES.md),
and the gate checks the implementations against them.

Re-running this script rebuilds the fixtures byte-identically (fixed SHAs,
fixed timestamps, fixed digests; no wall-clock or randomness anywhere).

Usage: python 02_source/scripts/build_fixtures.py [--root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchreceipt.canonical import canonical_hash  # noqa: E402
from benchreceipt.schema import SchemaValidationError, validate_against_schema  # noqa: E402

# --- Fixed synthetic identities (40-hex SHAs, never real commits) --------
HEAD = "a" * 40          # PR head SHA
MERGE = "b" * 40         # merge commit SHA
OTHER = "c" * 40         # an unrelated explicit SHA
TREE1 = "d" * 40
TREE2 = "e" * 40
RUN1 = "9001"
RUN2 = "9002"

CLEAN_DIGEST = hashlib.sha256(b"").hexdigest()
DIRTY1_DIGEST = hashlib.sha256(b"M  src/a.py\n").hexdigest()
DIRTY2_DIGEST = hashlib.sha256(b"M  src/b.py\n").hexdigest()

ARGV_SHA = canonical_hash(["python", "-m", "pytest", "-q"])
DISPLAY = "python -m pytest -q"

# Fixtures whose receipt / artifact deliberately does NOT match the
# "valid + consistent" invariant, and why. The S0 tests allow exactly
# these exceptions and no others.
INTENTIONAL = {
    "f1-report-missing": "receipt lists artifacts/junit.xml but the file is absent",
    "f2-report-hash-mismatch": "junit bytes tampered after the receipt hash was computed",
    "f3-lcov-required-missing": "policy requires lcov but the receipt has no lcov entry",
    "f4-report-size-lie": "receipt size_bytes is 7 larger than the real file",
    "h4-missing-command": "receipt omits the required `command` object (schema-invalid)",
}


def junit_xml(n_tests: int, n_failures: int = 0, n_errors: int = 0,
              n_skipped: int = 0) -> bytes:
    """Minimal well-formed JUnit XML with exactly the given counts."""
    cases = []
    for i in range(n_tests):
        inner = ""
        if i < n_failures:
            inner = '<failure message="assert failed">traceback</failure>'
        elif i < n_failures + n_errors:
            inner = '<error message="boom">traceback</error>'
        elif i < n_failures + n_errors + n_skipped:
            inner = "<skipped/>"
        cases.append(f'<testcase classname="t" name="test_{i}">{inner}</testcase>')
    body = "".join(cases)
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuite name="suite" tests="{n_tests}" failures="{n_failures}" '
        f'errors="{n_errors}" skipped="{n_skipped}">{body}</testsuite>\n'
    ).encode("utf-8")


LCOV_BYTES = (
    b"TN:\nSF:src/foo.py\nFN:1,foo\nFNF:1\nFNH:1\n"
    b"DA:1,1\nDA:2,0\nLF:2\nLH:1\nend_of_record\n"
)

MALFORMED_XML = b"this is not xml at all\njust some plain text\n"


def policy_toml(source_mode: str, required_jobs: list[str],
                expected_workflow: str = "CI", min_tests: int = 1,
                require_clean: bool = True, same_tree: bool = True,
                same_run_id: bool = True, same_attempt: bool = True,
                junit: str = "required", lcov: str = "optional") -> str:
    jobs = ",\n".join(f'  "{j}"' for j in required_jobs)
    return (
        "schema_version = 1\n"
        f'source_mode = "{source_mode}"\n'
        f'expected_workflow = "{expected_workflow}"\n'
        "required_jobs = [\n"
        f"{jobs}\n"
        "]\n"
        f"min_tests = {min_tests}\n"
        f"require_clean_source_after = {'true' if require_clean else 'false'}\n"
        f"same_tree_across_jobs = {'true' if same_tree else 'false'}\n"
        f"same_run_id = {'true' if same_run_id else 'false'}\n"
        f"same_run_attempt = {'true' if same_attempt else 'false'}\n"
        "\n[reports]\n"
        f'junit = "{junit}"\n'
        f'lcov = "{lcov}"\n'
        "\n[security]\n"
        "store_stdout = false\n"
        "store_stderr = false\n"
        "store_full_environment = false\n"
    )


def make_receipt(job_id: str, matrix: dict, head: str, tree: str,
                 mode: str, expected_sha: str, run_id: str, attempt: int,
                 workflow: str = "CI", exit_code: int = 0,
                 junit_counts: tuple[int, int, int, int] | None = (10, 0, 0, 0),
                 junit_bytes: bytes | None = None,
                 include_lcov: bool = False, include_junit_file: bool = True,
                 dirty_before: bool = False, dirty_after: bool = False,
                 digest_before: str = CLEAN_DIGEST,
                 digest_after: str = CLEAN_DIGEST,
                 head_after: str | None = None,
                 tree_after: str | None = None,
                 omit_after: bool = False,
                 provider: str = "github-actions",
                 event_name: str | None = "pull_request",
                 extra: dict | None = None,
                 tamper_junit: bool = False,
                 size_lie: int = 0,
                 junit_report: bool = True) -> tuple[dict, dict[str, bytes]]:
    """Build (receipt_dict, artifacts_dict) for one job.

    ``junit_counts`` is the receipt summary (tests, failures, errors,
    skipped); ``junit_bytes`` overrides the artifact bytes (default:
    XML generated from the summary counts). ``tamper_junit`` rewrites
    one byte of the artifact after the receipt hash is computed (f2).
    ``size_lie`` inflates the receipt's junit ``size_bytes`` (f4).
    ``include_junit_file=False`` lists the report but writes no file (f1).
    ``junit_report=False`` omits the JUnit report entirely (n08, LCOV-only).
    ``junit_counts=None`` with ``junit_report=True`` keeps the report file
    but omits the receipt summary (h2). ``head_after`` / ``tree_after``
    (spec v1.1.0, ADR-005) set the optional ``git.head_sha_after`` /
    ``git.tree_sha_after`` fields; when omitted they DEFAULT to the
    before values (spec v1.2.0, ADR-007, scheme A): the builder
    simulates current capture output, which always records after
    identity, so every generated fixture carries after fields equal
    to its before values unless it plants an after anomaly (e5/e6)
    or is a legacy-shape fixture (``omit_after=True``: e7/e8, whose
    receipts carry neither after field and must fail closed with
    MISSING_FIELD). ``omit_after`` is the ONLY way to generate a
    receipt without after fields.
    """
    if junit_bytes is None and junit_counts is not None:
        junit_bytes = junit_xml(*junit_counts)
    if junit_bytes is None and junit_report:
        junit_bytes = junit_xml(10, 0, 0, 0)
    reports: list[dict] = []
    artifacts: dict[str, bytes] = {}
    if junit_report:
        data = junit_bytes
        assert data is not None
        entry = {"kind": "junit", "path": "artifacts/junit.xml",
                 "size_bytes": len(data) + size_lie,
                 "sha256": hashlib.sha256(data).hexdigest()}
        reports.append(entry)
        if include_junit_file:
            stored = data
            if tamper_junit:
                # Same length, one byte inside a test name: the XML stays
                # well-formed with identical counts, so only the digest
                # differs (a pure hash mismatch, not a parse failure).
                stored = data.replace(b'name="test_0"', b'name="test_Z"', 1)
                assert stored != data and len(stored) == len(data)
            artifacts["artifacts/junit.xml"] = stored
    if include_lcov:
        reports.append({"kind": "lcov", "path": "artifacts/lcov.info",
                        "size_bytes": len(LCOV_BYTES),
                        "sha256": hashlib.sha256(LCOV_BYTES).hexdigest()})
        artifacts["artifacts/lcov.info"] = LCOV_BYTES
    receipt: dict = {
        "schema": "benchreceipt.run/v1",
        "job_id": job_id,
        "matrix": matrix,
        "git": {
            "head_sha": head,
            "tree_sha": tree,
            "source_mode": mode,
            "expected_source_sha": expected_sha,
            "dirty_before": dirty_before,
            "dirty_after": dirty_after,
        },
        "ci": {
            "provider": provider,
            "run_id": run_id,
            "run_attempt": attempt,
            "workflow": workflow,
        },
        "command": {
            "argv_sha256": ARGV_SHA,
            "display": DISPLAY,
            "exit_code": exit_code,
        },
        "runner": {"os": "Linux", "arch": "x86_64", "python": "3.12.3"},
        "reports": reports,
        "started_at": "2026-11-17T07:00:00Z",
        "finished_at": "2026-11-17T07:00:05Z",
        "source_state_before": {"dirty": dirty_before, "tracked_diff_sha256": digest_before},
        "source_state_after": {"dirty": dirty_after, "tracked_diff_sha256": digest_after},
    }
    if not omit_after:
        # Scheme A (ADR-007): default after == before (current capture
        # always records after identity); explicit values plant an
        # after anomaly (e5/e6).
        receipt["git"]["head_sha_after"] = (
            head_after if head_after is not None else head)
        receipt["git"]["tree_sha_after"] = (
            tree_after if tree_after is not None else tree)
    if event_name is not None:
        receipt["ci"]["event_name"] = event_name
    if junit_counts is not None:
        tests, failures, errors, skipped = junit_counts
        receipt["junit"] = {"tests": tests, "failures": failures,
                            "errors": errors, "skipped": skipped}
    if extra:
        receipt.update(extra)
    return receipt, artifacts


def write_fixture(root: Path, fid: str, policy: str, expected_sha: str,
                  jobs: list[tuple[str, dict, dict[str, bytes]]],
                  validate: bool = True) -> None:
    """Write one fixture dir. ``jobs`` = [(dirname, receipt, artifacts)]."""
    fdir = root / fid
    if fdir.exists():
        import shutil
        shutil.rmtree(fdir)
    (fdir / "evidence").mkdir(parents=True)
    (fdir / "policy.toml").write_text(policy, encoding="utf-8")
    (fdir / "expected.json").write_text(
        json.dumps({"expected_source_sha": expected_sha}, indent=2) + "\n",
        encoding="utf-8")
    for dirname, receipt, artifacts in jobs:
        jdir = fdir / "evidence" / dirname
        jdir.mkdir(parents=True)
        if validate:
            try:
                validate_against_schema(receipt, "run")
            except SchemaValidationError as exc:
                raise SystemExit(f"fixture {fid}: receipt for {dirname} "
                                 f"fails run.v1: {exc}") from exc
        (jdir / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for rel, data in artifacts.items():
            target = jdir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


LINUX312 = {"os": "ubuntu-latest", "python": "3.12"}
WIN312 = {"os": "windows-latest", "python": "3.12"}
LINUX313 = {"os": "ubuntu-latest", "python": "3.13"}
MACOS312 = {"os": "macos-latest", "python": "3.12"}

LINUX_JOB = "unit-linux-py312"
WIN_JOB = "unit-windows-py312"
LINUX313_JOB = "unit-linux-py313"
MACOS_JOB = "unit-macos-py312"


def std_job(job_id, matrix, **kw):
    """A clean passing job with PR-head defaults."""
    return make_receipt(job_id, matrix, HEAD, TREE1, "pr_head", HEAD,
                        RUN1, 2, **kw)


def build(root: Path) -> list[str]:
    ids: list[str] = []

    def add(fid, policy, expected_sha, jobs, validate=True):
        write_fixture(root, fid, policy, expected_sha, jobs, validate=validate)
        ids.append(fid)

    # ---- 16 normal controls (all BOUND_PASS) ---------------------------
    add("n01-single-pr-head",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312))])
    add("n02-two-job-pr-head",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312))])
    add("n03-three-job-pr-head",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB, LINUX313_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312)),
         ("unit-linux-py313", *std_job(LINUX313_JOB, LINUX313))])
    add("n04-single-merge-commit",
        policy_toml("merge_commit", [LINUX_JOB]), MERGE,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, MERGE, TREE1, "merge_commit", MERGE, RUN1, 2))])
    add("n05-two-job-merge-commit",
        policy_toml("merge_commit", [LINUX_JOB, WIN_JOB]), MERGE,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, MERGE, TREE1, "merge_commit", MERGE, RUN1, 2)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, MERGE, TREE1, "merge_commit", MERGE, RUN1, 2))])
    add("n06-single-event-sha",
        policy_toml("event_sha", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "event_sha", HEAD, RUN1, 2,
            event_name="push"))])
    add("n07-single-explicit-sha",
        policy_toml("explicit_sha", [LINUX_JOB]), OTHER,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, OTHER, TREE1, "explicit_sha", OTHER, RUN1, 2,
            provider="generic", event_name=None))])
    add("n08-lcov-only",
        policy_toml("pr_head", [LINUX_JOB], junit="optional", lcov="required"), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "pr_head", HEAD, RUN1, 2,
            junit_counts=None, junit_report=False, include_lcov=True))])
    add("n09-skipped-still-pass",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312,
                                        junit_counts=(10, 0, 0, 1)))])
    add("n10-different-trees-allowed",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB], same_tree=False), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, HEAD, TREE2, "pr_head", HEAD, RUN1, 2))])
    add("n11-different-attempts-allowed",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB], same_attempt=False), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, HEAD, TREE1, "pr_head", HEAD, RUN1, 1))])
    add("n12-min-tests-boundary",
        policy_toml("pr_head", [LINUX_JOB], min_tests=5), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312,
                                        junit_counts=(5, 0, 0, 0)))])
    add("n13-junit-plus-lcov",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB], lcov="required"), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312, include_lcov=True)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312, include_lcov=True))])
    # n14: optional §5.1 fields present (workflow_ref/workflow_sha).
    receipt14, arts14 = std_job(LINUX_JOB, LINUX312)
    receipt14["ci"]["workflow_ref"] = "acme/repo/.github/workflows/ci.yml@refs/pull/1/merge"
    receipt14["ci"]["workflow_sha"] = HEAD
    add("n14-optional-fields-present",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", receipt14, arts14)])
    add("n15-three-job-merge-commit",
        policy_toml("merge_commit", [LINUX_JOB, WIN_JOB, LINUX313_JOB]), MERGE,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, MERGE, TREE1, "merge_commit", MERGE, RUN1, 2)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, MERGE, TREE1, "merge_commit", MERGE, RUN1, 2)),
         ("unit-linux-py313", *make_receipt(
            LINUX313_JOB, LINUX313, MERGE, TREE1, "merge_commit", MERGE, RUN1, 2))])
    add("n16-py313-single",
        policy_toml("pr_head", [LINUX313_JOB]), HEAD,
        [("unit-linux-py313", *std_job(LINUX313_JOB, LINUX313))])

    # ---- (a) wrong source SHA / head-merge confusion --------------------
    add("a1-wrong-source-sha",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, MERGE, TREE1, "pr_head", HEAD, RUN1, 2))])
    add("a2-one-job-wrong-sha",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, MERGE, TREE1, "pr_head", HEAD, RUN1, 2))])
    add("a3-merge-expected-head-found",
        policy_toml("merge_commit", [LINUX_JOB]), MERGE,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "merge_commit", MERGE, RUN1, 2))])
    add("a4-mode-mismatch-only",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "merge_commit", HEAD, RUN1, 2))])

    # ---- (b) tree SHA mixing ---------------------------------------------
    add("b1-tree-mismatch",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, HEAD, TREE2, "pr_head", HEAD, RUN1, 2))])
    add("b2-three-job-one-tree-differs",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB, LINUX313_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312)),
         ("unit-linux-py313", *make_receipt(
            LINUX313_JOB, LINUX313, HEAD, TREE2, "pr_head", HEAD, RUN1, 2))])
    add("b3-tree-mismatch-reversed",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE2, "pr_head", HEAD, RUN1, 2)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312))])
    add("b4-two-trees-differ",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB, LINUX313_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, HEAD, TREE2, "pr_head", HEAD, RUN1, 2)),
         ("unit-linux-py313", *make_receipt(
            LINUX313_JOB, LINUX313, HEAD, TREE2, "pr_head", HEAD, RUN1, 2))])

    # ---- (c) run ID / attempt mixing --------------------------------------
    add("c1-attempt-mismatch",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, HEAD, TREE1, "pr_head", HEAD, RUN1, 1))])
    add("c2-run-id-mismatch",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, HEAD, TREE1, "pr_head", HEAD, RUN2, 2))])
    add("c3-run-and-attempt-mismatch",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *make_receipt(
            WIN_JOB, WIN312, HEAD, TREE1, "pr_head", HEAD, RUN2, 1))])
    add("c4-three-job-one-attempt-differs",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB, LINUX313_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312)),
         ("unit-linux-py313", *make_receipt(
            LINUX313_JOB, LINUX313, HEAD, TREE1, "pr_head", HEAD, RUN1, 3))])

    # ---- (d) matrix missing / duplicate / unexpected ----------------------
    add("d1-matrix-missing",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312))])
    add("d2-matrix-duplicate",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-linux-py312-dup", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312))])
    add("d3-matrix-unexpected",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *std_job(WIN_JOB, WIN312)),
         ("unit-macos-py312", *std_job(MACOS_JOB, MACOS312))])
    add("d4-missing-plus-unexpected",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-macos-py312", *std_job(MACOS_JOB, MACOS312))])

    # ---- (e) source dirty before -> after ----------------------------------
    add("e1-clean-to-dirty",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, dirty_before=False, dirty_after=True,
            digest_before=CLEAN_DIGEST, digest_after=DIRTY1_DIGEST))])
    add("e2-one-job-mutated",
        policy_toml("pr_head", [LINUX_JOB, WIN_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312)),
         ("unit-windows-py312", *std_job(
            WIN_JOB, WIN312, dirty_before=False, dirty_after=True,
            digest_before=CLEAN_DIGEST, digest_after=DIRTY2_DIGEST))])
    add("e3-started-dirty-stayed-dirty",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, dirty_before=True, dirty_after=True,
            digest_before=DIRTY1_DIGEST, digest_after=DIRTY1_DIGEST))])
    add("e4-digest-changed-flags-clean",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, dirty_before=False, dirty_after=False,
            digest_before=CLEAN_DIGEST, digest_after=DIRTY1_DIGEST))])
    # ---- (e) clean-tree HEAD change (ADR-005 / P0-01, spec v1.1.0) -------
    # e5: `git checkout <other-commit>` mid-run — clean tree both sides,
    # HEAD and tree both move (after: MERGE head, TREE2). The porcelain
    # digests are identical (empty) and both dirty flags are False, so
    # only the after fields can catch this.
    add("e5-clean-tree-head-change",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, dirty_before=False, dirty_after=False,
            digest_before=CLEAN_DIGEST, digest_after=CLEAN_DIGEST,
            head_after=MERGE, tree_after=TREE2))])
    # e6: `git commit --allow-empty` mid-run — HEAD moves, tree is
    # byte-identical, so only head_sha_after can catch this.
    add("e6-empty-commit-mid-run",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, dirty_before=False, dirty_after=False,
            digest_before=CLEAN_DIGEST, digest_after=CLEAN_DIGEST,
            head_after=OTHER, tree_after=TREE1))])
    # ---- (e) legacy shape, no after fields (ADR-007 / P0-R1-01, spec v1.2.0)
    # e7/e8 are the R1 false-PASS scenarios with the after evidence
    # REMOVED: the receipts carry neither after field, so nothing in
    # them can prove the run's HEAD/tree did not change mid-run and
    # verify must fail closed (UNBOUND + MISSING_FIELD, jobs 0).
    # NOTE: the two receipts are byte-identical by design — without
    # after fields the clean-checkout scenario (e7) and the
    # empty-commit scenario (e8) are indistinguishable, which is
    # exactly why both must fail closed. The scenario each fixture
    # represents lives in its id (and in GOLDEN's hand-written
    # entries), not in the receipt bytes.
    # e7: `git checkout <other-commit>` mid-run — clean tree both
    # sides, HEAD aaaa→bbbb, tree dddd→eeee, identical empty
    # porcelain digests, both dirty flags False.
    add("e7-legacy-clean-checkout",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, dirty_before=False, dirty_after=False,
            digest_before=CLEAN_DIGEST, digest_after=CLEAN_DIGEST,
            omit_after=True))])
    # e8: `git commit --allow-empty` mid-run — HEAD aaaa→cccc, tree
    # unchanged (dddd), otherwise identical to e7.
    add("e8-legacy-empty-commit",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, dirty_before=False, dirty_after=False,
            digest_before=CLEAN_DIGEST, digest_after=CLEAN_DIGEST,
            omit_after=True))])

    # ---- (f) report missing / hash mismatch --------------------------------
    add("f1-report-file-missing",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "pr_head", HEAD, RUN1, 2,
            include_junit_file=False))])
    add("f2-report-hash-mismatch",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "pr_head", HEAD, RUN1, 2,
            tamper_junit=True))])
    add("f3-lcov-required-missing",
        policy_toml("pr_head", [LINUX_JOB], lcov="required"), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312))])
    add("f4-report-size-lie",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "pr_head", HEAD, RUN1, 2,
            size_lie=7))])

    # ---- (g) JUnit failed / empty / malformed / exit contradiction ---------
    add("g1-junit-failed",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, exit_code=1, junit_counts=(10, 2, 0, 0)))])
    add("g2-junit-empty",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, junit_counts=(0, 0, 0, 0)))])
    add("g3-junit-malformed",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "pr_head", HEAD, RUN1, 2,
            junit_bytes=MALFORMED_XML))])
    add("g4-exit-code-contradiction",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *std_job(LINUX_JOB, LINUX312, exit_code=1))])

    # ---- (h) argv/policy mismatch or missing critical field ----------------
    add("h1-workflow-mismatch",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "pr_head", HEAD, RUN1, 2,
            workflow="OtherCI"))])
    add("h2-junit-summary-missing",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", *make_receipt(
            LINUX_JOB, LINUX312, HEAD, TREE1, "pr_head", HEAD, RUN1, 2,
            junit_counts=None))])
    add("h3-below-min-tests",
        policy_toml("pr_head", [LINUX_JOB], min_tests=5), HEAD,
        [("unit-linux-py312", *std_job(
            LINUX_JOB, LINUX312, junit_counts=(3, 0, 0, 0)))])
    # h4: receipt omits the required `command` object — intentionally
    # schema-invalid; the verifier must answer INVALID, not crash.
    receipt_h4, arts_h4 = std_job(LINUX_JOB, LINUX312)
    del receipt_h4["command"]
    add("h4-missing-command",
        policy_toml("pr_head", [LINUX_JOB]), HEAD,
        [("unit-linux-py312", receipt_h4, arts_h4)], validate=False)

    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the 52 S0 fixtures.")
    parser.add_argument("--root", default=None,
                        help="fixtures/s0 directory (default: relative to repo)")
    args = parser.parse_args()
    root = Path(args.root) if args.root else (
        Path(__file__).resolve().parents[1] / "fixtures" / "s0")
    ids = build(root)
    print(f"built {len(ids)} fixtures in {root}")
    for fid in ids:
        print(f"  {fid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
