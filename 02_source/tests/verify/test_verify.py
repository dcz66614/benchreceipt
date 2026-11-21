"""Verification-engine tests (P027-T008, PROJECT_BOOK §5.6).

Covers, at the :func:`benchreceipt.verify.evaluate` level:

- the four-state decision table (BOUND_PASS / BOUND_FAIL / UNBOUND /
  INVALID) plus the INTERNAL_ERROR path, each with its §5.6 exit code;
- one triggering sample for EVERY reason code in the frozen vocabulary
  (24 codes: the 22 from T004 plus LCOV_MALFORMED and INTERNAL_ERROR,
  ratified in ADR-003). S0 fixtures supply 19 of them; the remaining
  five (JUNIT_SUMMARY_MISMATCH, LCOV_MALFORMED, INVALID_POLICY,
  INVALID_EVIDENCE, INTERNAL_ERROR) are synthetic cases built from
  fixture copies, because no S0 fixture plants them;
- the frozen vocabulary itself (code set in verify.py matches
  docs/REASON_CODES.md, and every code maps to one of the five states);
- the jobs_verified counting rule (REASON_CODES.md): a duplicate's
  second copy counts 0, an unexpected job counts 0, a missing job
  counts 0;
- missing evidence can never PASS (empty evidence dir -> UNBOUND,
  missing evidence dir -> INVALID);
- every result validates against benchreceipt.result/v1;
- evaluate_with_policy_path() agrees with evaluate(), and the CLI
  --expected-run-id / --expected-attempt pins have real semantics.

S0 fixtures are read-only here: synthetic cases always copy a fixture
into tmp_path first and mutate the copy.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from benchreceipt.policy import load_policy
from benchreceipt.schema import validate_against_schema
from benchreceipt.verify import (
    EXIT_CODES,
    REASON_CODES,
    REASON_STATUS,
    _internal_error_result,
    evaluate,
    evaluate_with_policy_path,
    status_to_exit_code,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "s0"
REASON_CODES_MD = ROOT / "docs" / "REASON_CODES.md"

# Fixture -> the reason code it plants (one per code, from GOLDEN.json).
# 19 of the 24 frozen codes are planted by an S0 fixture; the other five
# have synthetic tests below.
FIXTURE_FOR_CODE = {
    "SOURCE_SHA_MISMATCH": "a1-wrong-source-sha",
    "SOURCE_MODE_MISMATCH": "a4-mode-mismatch-only",
    "TREE_SHA_MISMATCH": "b1-tree-mismatch",
    "RUN_ID_MISMATCH": "c2-run-id-mismatch",
    "RUN_ATTEMPT_MISMATCH": "c1-attempt-mismatch",
    "WORKFLOW_MISMATCH": "h1-workflow-mismatch",
    "MATRIX_MISSING_JOB": "d1-matrix-missing",
    "MATRIX_DUPLICATE_JOB": "d2-matrix-duplicate",
    "MATRIX_UNEXPECTED_JOB": "d3-matrix-unexpected",
    "SOURCE_MUTATED_DURING_RUN": "e1-clean-to-dirty",
    "REPORT_MISSING": "f1-report-file-missing",
    "MISSING_FIELD": "h2-junit-summary-missing",
    "REPORT_HASH_MISMATCH": "f2-report-hash-mismatch",
    "JUNIT_MALFORMED": "g3-junit-malformed",
    "INVALID_RECEIPT": "h4-missing-command",
    "JUNIT_FAILED": "g1-junit-failed",
    "JUNIT_EMPTY": "g2-junit-empty",
    "EXIT_CODE_MISMATCH": "g4-exit-code-contradiction",
    "POLICY_MISMATCH": "h3-below-min-tests",
}

# Four-state decision table: fixture -> (expected status, exit code).
DECISION_TABLE = [
    ("n01-single-pr-head", "BOUND_PASS", 0),
    ("g1-junit-failed", "BOUND_FAIL", 1),
    ("d1-matrix-missing", "UNBOUND", 2),
    ("f2-report-hash-mismatch", "INVALID", 3),
]


def _load_fixture(fid: str):
    fdir = FIXTURES / fid
    policy = load_policy(fdir / "policy.toml")
    expected_sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]
    return fdir, policy, expected_sha


def _refresh_report_entry(receipt_path: Path, kind: str, data: bytes) -> None:
    """Rewrite a receipt's recorded size + SHA-256 for one report kind,
    so only the report *content* (not its digest) is under test."""
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for entry in receipt["reports"]:
        if entry["kind"] == kind:
            entry["size_bytes"] = len(data)
            entry["sha256"] = hashlib.sha256(data).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


# ---------------------------------------------------------------------------
# Four-state decision table + exit codes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fid,status,exit_code", DECISION_TABLE)
def test_decision_table(fid: str, status: str, exit_code: int):
    fdir, policy, expected_sha = _load_fixture(fid)
    result = evaluate(policy, expected_sha, fdir / "evidence")
    assert result["status"] == status
    assert status_to_exit_code(result["status"]) == exit_code
    validate_against_schema(result, "result")


def test_exit_code_mapping_is_frozen():
    assert EXIT_CODES == {
        "BOUND_PASS": 0,
        "BOUND_FAIL": 1,
        "UNBOUND": 2,
        "INVALID": 3,
        "INTERNAL_ERROR": 4,
    }
    # An unknown status is a verifier bug: fail closed to 4, never 0.
    assert status_to_exit_code("BOGUS_STATUS") == 4


def test_internal_error_via_forced_exception(monkeypatch):
    """An unexpected internal exception becomes an INTERNAL_ERROR
    result (exit 4), never a raise and never a pass."""
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated verifier bug")

    monkeypatch.setattr("benchreceipt.verify.validate_policy", _boom)
    result = evaluate(policy, expected_sha, fdir / "evidence")
    assert result["status"] == "INTERNAL_ERROR"
    assert result["reason_codes"] == ["INTERNAL_ERROR"]
    assert result["jobs_verified"] == 0
    assert status_to_exit_code(result["status"]) == 4
    validate_against_schema(result, "result")


def test_internal_error_result_shape_is_fixed():
    result = _internal_error_result()
    assert result == {
        "schema": "benchreceipt.result/v1",
        "status": "INTERNAL_ERROR",
        "jobs_verified": 0,
        "missing_jobs": [],
        "unexpected_jobs": [],
        "duplicate_jobs": [],
        "reason_codes": ["INTERNAL_ERROR"],
        "identity_mismatches": [],
        "report_errors": [
            {"code": "INTERNAL_ERROR",
             "message": "internal error during verification"}
        ],
    }
    validate_against_schema(result, "result")


# ---------------------------------------------------------------------------
# One triggering sample per reason code (19 S0 fixtures)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code,fid", sorted(FIXTURE_FOR_CODE.items()))
def test_each_reason_code_has_a_triggering_sample(code: str, fid: str):
    fdir, policy, expected_sha = _load_fixture(fid)
    result = evaluate(policy, expected_sha, fdir / "evidence")
    assert code in result["reason_codes"], f"{fid} did not emit {code}: {result}"
    assert result["status"] == REASON_STATUS[code], (
        f"{fid}: {code} must aggregate to {REASON_STATUS[code]}, "
        f"got {result['status']}"
    )
    assert result["status"] != "BOUND_PASS", f"{fid} must not PASS"
    validate_against_schema(result, "result")


def test_golden_agrees_on_all_fixture_codes():
    """The samples above are the codes Golden expects for those
    fixtures — the test table and the hand-written Golden cannot drift
    apart silently."""
    golden = json.loads((FIXTURES / "GOLDEN.json").read_text())["fixtures"]
    for code, fid in FIXTURE_FOR_CODE.items():
        assert code in golden[fid]["reason_codes"], f"Golden lacks {code} for {fid}"


# ---------------------------------------------------------------------------
# Synthetic samples for the five codes no S0 fixture plants
# ---------------------------------------------------------------------------


def test_junit_summary_mismatch_synthetic(tmp_path: Path):
    """Parsed JUnit counts disagree with the receipt summary: the XML
    itself is valid (attributes match the counted elements), but the
    receipt summary still claims failures=0."""
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    evidence = tmp_path / "evidence"
    shutil.copytree(fdir / "evidence", evidence)
    junit_path = evidence / "unit-linux-py312" / "artifacts" / "junit.xml"
    doctored = junit_path.read_bytes().replace(
        b'tests="10" failures="0"',
        b'tests="10" failures="1"',
    ).replace(
        b'<testcase classname="t" name="test_0"></testcase>',
        b'<testcase classname="t" name="test_0">'
        b'<failure message="boom"></failure></testcase>',
    )
    junit_path.write_bytes(doctored)
    _refresh_report_entry(
        evidence / "unit-linux-py312" / "receipt.json", "junit", doctored
    )
    result = evaluate(policy, expected_sha, evidence)
    assert result["status"] == "INVALID"
    # FIX-R13a (F-01): the parsed report is now judged on its own
    # merits as well as against the summary — a parsed report with
    # failures is JUNIT_FAILED, and an exit code of 0 contradicts it
    # (EXIT_CODE_MISMATCH) — in addition to the summary disagreement.
    assert result["reason_codes"] == [
        "EXIT_CODE_MISMATCH", "JUNIT_FAILED", "JUNIT_SUMMARY_MISMATCH",
    ]
    assert result["jobs_verified"] == 0
    validate_against_schema(result, "result")


# ---------------------------------------------------------------------------
# FIX-R13a (F-01): every junit report in a job is judged, not just the last
# ---------------------------------------------------------------------------


def _junit_xml_bytes(n_tests: int = 10, n_fail: int = 0, n_err: int = 0) -> bytes:
    """Green/failing JUnit bytes whose count attributes match the counted
    elements, so only the *counts* (not malformedness) are under test."""
    cases = []
    for i in range(n_tests):
        inner = ""
        if i < n_fail:
            inner = '<failure message="x">t</failure>'
        elif i < n_fail + n_err:
            inner = '<error message="x">t</error>'
        cases.append(f'<testcase classname="t" name="test_{i}">{inner}</testcase>')
    return (
        f'<?xml version="1.0"?>\n<testsuite name="s" tests="{n_tests}" '
        f'failures="{n_fail}" errors="{n_err}" skipped="0">'
        f"{''.join(cases)}</testsuite>\n"
    ).encode()


def _two_junit_evidence(
    tmp_path: Path, fail_first: bool, fail_second: bool
) -> tuple[dict, str, Path]:
    """1-job evidence with two junit reports — one failing (10 tests,
    2 failures), one passing (10 tests, 0 failures), or both passing —
    and a receipt summary matching the PASSING report (10,0,0,0).

    ``fail_first`` / ``fail_second`` select which listed report fails;
    the summary always claims the passing counts, so any failing
    report disagrees with it.
    """
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    evidence = tmp_path / "evidence"
    shutil.copytree(fdir / "evidence", evidence)
    job_dir = evidence / "unit-linux-py312"
    fail_xml = _junit_xml_bytes(10, n_fail=2)
    pass_xml = _junit_xml_bytes(10)
    # The two entries keep fixed paths; which one FAILS is what varies,
    # so the failing report occupies position 0 in one case and
    # position 1 in the other. File bytes always match the receipt
    # digests for their entry.
    first = fail_xml if fail_first else pass_xml
    second = fail_xml if fail_second else pass_xml
    (job_dir / "artifacts" / "junit-fail.xml").write_bytes(first)
    (job_dir / "artifacts" / "junit.xml").write_bytes(second)
    receipt = json.loads((job_dir / "receipt.json").read_text())
    receipt["reports"] = [
        {"kind": "junit", "path": "artifacts/junit-fail.xml",
         "size_bytes": len(first),
         "sha256": hashlib.sha256(first).hexdigest()},
        {"kind": "junit", "path": "artifacts/junit.xml",
         "size_bytes": len(second),
         "sha256": hashlib.sha256(second).hexdigest()},
    ]
    receipt["junit"] = {"tests": 10, "failures": 0, "errors": 0, "skipped": 0}
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    return policy, expected_sha, evidence


@pytest.mark.parametrize("fail_first,fail_second", [(True, False), (False, True)])
def test_multi_junit_failing_report_never_passes(
    tmp_path: Path, fail_first: bool, fail_second: bool
):
    """FIX-R13a (F-01, repro3 R24): a failing junit report is judged
    whichever position it occupies in reports[] — the verdict is
    order-independent, and the job never verifies."""
    policy, expected_sha, evidence = _two_junit_evidence(
        tmp_path, fail_first, fail_second
    )
    result = evaluate(policy, expected_sha, evidence)
    assert result["status"] == "INVALID"
    assert "JUNIT_FAILED" in result["reason_codes"]
    assert "JUNIT_SUMMARY_MISMATCH" in result["reason_codes"]
    assert "EXIT_CODE_MISMATCH" in result["reason_codes"]
    assert result["jobs_verified"] == 0
    validate_against_schema(result, "result")


def test_multi_junit_all_passing_still_passes(tmp_path: Path):
    """Control for F-01: two passing junit reports with a matching
    summary still verify BOUND_PASS — judging every report does not
    invent failures."""
    policy, expected_sha, evidence = _two_junit_evidence(
        tmp_path, fail_first=False, fail_second=False
    )
    result = evaluate(policy, expected_sha, evidence)
    assert result["status"] == "BOUND_PASS"
    assert result["reason_codes"] == []
    assert result["jobs_verified"] == 1
    validate_against_schema(result, "result")


@pytest.mark.parametrize("fail_first,fail_second", [(True, False), (False, True)])
def test_multi_junit_verdict_is_order_independent(
    tmp_path: Path, fail_first: bool, fail_second: bool
):
    """F-01: the two report orders produce the identical verdict —
    the same status and the same reason codes (T013: the old code
    passed one order and failed the other)."""
    policy, expected_sha, evidence_a = _two_junit_evidence(
        tmp_path / "a", fail_first=True, fail_second=False
    )
    _policy, _sha, evidence_b = _two_junit_evidence(
        tmp_path / "b", fail_first=False, fail_second=True
    )
    result_a = evaluate(policy, expected_sha, evidence_a)
    result_b = evaluate(policy, expected_sha, evidence_b)
    assert result_a["status"] == result_b["status"]
    assert result_a["reason_codes"] == result_b["reason_codes"]


def test_lcov_malformed_synthetic(tmp_path: Path):
    """A LCOV report whose bytes cannot be parsed (absolute SF path)
    is INVALID / LCOV_MALFORMED, never passed on presence + digest."""
    fdir, policy, expected_sha = _load_fixture("n13-junit-plus-lcov")
    evidence = tmp_path / "evidence"
    shutil.copytree(fdir / "evidence", evidence)
    doctored = b"SF:/abs/path.py\nend_of_record\n"
    # n13 has two jobs; corrupt the LCOV report in both, so neither
    # verifies (corrupting one would leave jobs_verified == 1).
    for job_dir in sorted(evidence.iterdir()):
        lcov_path = job_dir / "artifacts" / "lcov.info"
        lcov_path.write_bytes(doctored)
        _refresh_report_entry(job_dir / "receipt.json", "lcov", doctored)
    result = evaluate(policy, expected_sha, evidence)
    assert result["status"] == "INVALID"
    assert "LCOV_MALFORMED" in result["reason_codes"]
    assert result["jobs_verified"] == 0
    assert len([e for e in result["report_errors"] if e["code"] == "LCOV_MALFORMED"]) == 2
    validate_against_schema(result, "result")


def test_invalid_policy_synthetic(tmp_path: Path):
    fdir, _policy, expected_sha = _load_fixture("n01-single-pr-head")
    result = evaluate({}, expected_sha, fdir / "evidence")
    assert result["status"] == "INVALID"
    assert result["reason_codes"] == ["INVALID_POLICY"]
    assert result["jobs_verified"] == 0
    assert "expected_source_mode" not in result
    validate_against_schema(result, "result")


def test_invalid_policy_via_policy_path(tmp_path: Path):
    bad_policy = tmp_path / "bad.toml"
    bad_policy.write_text("source_mode = 42\n", encoding="utf-8")
    fdir, _policy, expected_sha = _load_fixture("n01-single-pr-head")
    result = evaluate_with_policy_path(bad_policy, expected_sha, fdir / "evidence")
    assert result["status"] == "INVALID"
    assert result["reason_codes"] == ["INVALID_POLICY"]
    validate_against_schema(result, "result")


def test_invalid_policy_missing_file_via_policy_path(tmp_path: Path):
    fdir, _policy, expected_sha = _load_fixture("n01-single-pr-head")
    result = evaluate_with_policy_path(
        tmp_path / "no-such-policy.toml", expected_sha, fdir / "evidence"
    )
    assert result["status"] == "INVALID"
    assert result["reason_codes"] == ["INVALID_POLICY"]
    validate_against_schema(result, "result")


def test_invalid_evidence_synthetic(tmp_path: Path):
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    result = evaluate(policy, expected_sha, tmp_path / "no-such-evidence")
    assert result["status"] == "INVALID"
    assert result["reason_codes"] == ["INVALID_EVIDENCE"]
    assert result["jobs_verified"] == 0
    validate_against_schema(result, "result")


def test_internal_error_via_policy_path(monkeypatch):
    """An unexpected failure while loading the policy is INTERNAL_ERROR,
    not a raise and not a pass."""
    fdir, _policy, expected_sha = _load_fixture("n01-single-pr-head")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated loader bug")

    monkeypatch.setattr("benchreceipt.verify.load_policy", _boom)
    result = evaluate_with_policy_path(
        fdir / "policy.toml", expected_sha, fdir / "evidence"
    )
    assert result["status"] == "INTERNAL_ERROR"
    assert result["reason_codes"] == ["INTERNAL_ERROR"]
    validate_against_schema(result, "result")


# ---------------------------------------------------------------------------
# Vocabulary enforcement
# ---------------------------------------------------------------------------


def test_vocabulary_matches_reason_codes_doc():
    """verify.py's frozen set is exactly the code table in
    docs/REASON_CODES.md (ADR-003: 24 codes)."""
    text = REASON_CODES_MD.read_text(encoding="utf-8")
    doc_codes = set(re.findall(r"^\| `([A-Z][A-Z0-9_]*)` \|", text, flags=re.M))
    assert doc_codes == set(REASON_CODES), (
        f"doc {sorted(doc_codes)} != code {sorted(REASON_CODES)}"
    )
    assert len(REASON_CODES) == 24
    assert set(REASON_STATUS) == set(REASON_CODES)
    assert set(REASON_STATUS.values()) <= {
        "BOUND_PASS", "BOUND_FAIL", "UNBOUND", "INVALID", "INTERNAL_ERROR",
    }


def test_every_code_maps_to_a_status_class():
    for code, status in REASON_STATUS.items():
        assert status in EXIT_CODES, f"{code} has unknown status {status}"


# ---------------------------------------------------------------------------
# jobs_verified counting rule + missing evidence never passes
# ---------------------------------------------------------------------------


def test_jobs_verified_counting_rule():
    """REASON_CODES.md: a duplicate's second copy counts 0, an
    unexpected job counts 0, a missing job counts 0."""
    # d2: two required jobs, one of them duplicated -> the first copy of
    # the duplicated job and the other job verify (2), the second copy 0.
    fdir, policy, sha = _load_fixture("d2-matrix-duplicate")
    assert evaluate(policy, sha, fdir / "evidence")["jobs_verified"] == 2
    # d3: two required jobs verify (2); the unexpected job counts 0.
    fdir, policy, sha = _load_fixture("d3-matrix-unexpected")
    assert evaluate(policy, sha, fdir / "evidence")["jobs_verified"] == 2
    # d4: one required job verifies; the missing one and the unexpected
    # one both count 0.
    fdir, policy, sha = _load_fixture("d4-missing-plus-unexpected")
    assert evaluate(policy, sha, fdir / "evidence")["jobs_verified"] == 1


def test_empty_evidence_dir_is_unbound_never_pass(tmp_path: Path):
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    empty = tmp_path / "evidence"
    empty.mkdir()
    result = evaluate(policy, expected_sha, empty)
    assert result["status"] == "UNBOUND"
    assert result["reason_codes"] == ["MATRIX_MISSING_JOB"]
    assert result["jobs_verified"] == 0
    validate_against_schema(result, "result")


def test_missing_evidence_dir_is_invalid_never_pass(tmp_path: Path):
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    result = evaluate(policy, expected_sha, tmp_path / "absent")
    assert result["status"] == "INVALID"
    assert result["reason_codes"] == ["INVALID_EVIDENCE"]
    assert result["jobs_verified"] == 0


# ---------------------------------------------------------------------------
# evaluate_with_policy_path + expected run/attempt pins
# ---------------------------------------------------------------------------


def test_evaluate_with_policy_path_agrees_with_evaluate():
    fdir, policy, expected_sha = _load_fixture("n02-two-job-pr-head")
    via_path = evaluate_with_policy_path(
        fdir / "policy.toml", expected_sha, fdir / "evidence"
    )
    direct = evaluate(policy, expected_sha, fdir / "evidence")
    assert via_path == direct
    assert via_path["status"] == "BOUND_PASS"


def test_expected_run_id_pin():
    # n01's only job: run_id "9001", attempt 2.
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    ok = evaluate(policy, expected_sha, fdir / "evidence", expected_run_id="9001")
    assert ok["status"] == "BOUND_PASS"
    wrong = evaluate(policy, expected_sha, fdir / "evidence", expected_run_id="9002")
    assert wrong["status"] == "UNBOUND"
    assert wrong["reason_codes"] == ["RUN_ID_MISMATCH"]
    assert wrong["identity_mismatches"] == [
        {"job_id": "unit-linux-py312", "field": "ci.run_id",
         "expected": "9002", "actual": "9001"}
    ]
    assert wrong["jobs_verified"] == 0


def test_expected_attempt_pin():
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    ok = evaluate(policy, expected_sha, fdir / "evidence", expected_attempt=2)
    assert ok["status"] == "BOUND_PASS"
    wrong = evaluate(policy, expected_sha, fdir / "evidence", expected_attempt=1)
    assert wrong["status"] == "UNBOUND"
    assert wrong["reason_codes"] == ["RUN_ATTEMPT_MISMATCH"]
    assert wrong["jobs_verified"] == 0


def test_expected_pin_validation_is_internal_error():
    fdir, policy, expected_sha = _load_fixture("n01-single-pr-head")
    assert evaluate(
        policy, expected_sha, fdir / "evidence", expected_attempt=0
    )["status"] == "INTERNAL_ERROR"
    assert evaluate(
        policy, expected_sha, fdir / "evidence", expected_run_id=""
    )["status"] == "INTERNAL_ERROR"
