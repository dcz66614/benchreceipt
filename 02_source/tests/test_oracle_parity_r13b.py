"""FIX-R13b Oracle parity test (P027-T013 F-02–F-08 + F-01 mirror).

Builds each case from the frozen n02 fixture, runs production
``benchreceipt.verify.evaluate`` and the Node Oracle CLI on the same
evidence, and asserts the two return the IDENTICAL verdict: same
status, same reason codes, same jobs_verified, same report errors
(code/job/path/message) and same identity mismatches. A mismatch is
an Oracle fidelity regression, not a test tolerance issue.

Cases come from the T013 reviewer's repro scripts (repro2.py R2–R4,
repro3.py R24/R5/R7a/R16, repro4.py R4a3/R4g/R6a) plus new cases of
the same shape (more LCOV/JUnit/schema/TOML/pin variants).

Run: python -m pytest tests/test_oracle_parity_r13b.py -q
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ORACLE = ROOT / "oracle" / "verify.mjs"
FIX = ROOT / "fixtures" / "s0" / "n02-two-job-pr-head"


def junit_xml(n_tests=10, n_fail=0, n_err=0, n_skip=0, tests_attr=None, extra=""):
    cases = []
    for i in range(n_tests):
        inner = ""
        if i < n_fail:
            inner = '<failure message="x">t</failure>'
        elif i < n_fail + n_err:
            inner = '<error message="x">t</error>'
        elif i < n_fail + n_err + n_skip:
            inner = "<skipped/>"
        cases.append(f'<testcase classname="t" name="test_{i}">{inner}</testcase>')
    ta = tests_attr if tests_attr is not None else n_tests
    return (
        f'<?xml version="1.0"?>\n<testsuite name="s" tests="{ta}" failures="{n_fail}" '
        f'errors="{n_err}" skipped="{n_skip}">{extra}{"".join(cases)}</testsuite>\n'
    ).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Case:
    """One parity case: a 1-job evidence dir + policy + expected SHA."""

    def __init__(self, tmp_path: Path, *, lcov_required: bool = False):
        import shutil

        self.root = tmp_path
        self.ev = tmp_path / "evidence"
        shutil.copytree(FIX / "evidence", self.ev)
        for child in list(self.ev.iterdir()):
            if child.name != "unit-linux-py312":
                shutil.rmtree(child)
        self.policy = load_policy(FIX / "policy.toml")
        self.policy["required_jobs"] = ["unit-linux-py312"]
        if lcov_required:
            self.policy["reports"]["lcov"] = "required"
        self.sha = json.loads((FIX / "expected.json").read_text())["expected_source_sha"]
        self.job = self.ev / "unit-linux-py312"
        self.extra_oracle_args: list[str] = []
        self.expected_run_id: str | None = None
        self.expected_attempt: int | None = None

    def write_policy_file(self) -> Path:
        lines = [
            "schema_version = 1",
            f'source_mode = "{self.policy["source_mode"]}"',
            f'expected_workflow = "{self.policy["expected_workflow"]}"',
            "required_jobs = [",
            ", ".join(f'"{j}"' for j in self.policy["required_jobs"]),
            "]",
            f'min_tests = {self.policy["min_tests"]}',
            f'require_clean_source_after = {str(self.policy["require_clean_source_after"]).lower()}',
            f'same_tree_across_jobs = {str(self.policy["same_tree_across_jobs"]).lower()}',
            f'same_run_id = {str(self.policy["same_run_id"]).lower()}',
            f'same_run_attempt = {str(self.policy["same_run_attempt"]).lower()}',
            "",
            "[reports]",
            f'junit = "{self.policy["reports"]["junit"]}"',
            f'lcov = "{self.policy["reports"]["lcov"]}"',
            "",
            "[security]",
            "store_stdout = false",
            "store_stderr = false",
            "store_full_environment = false",
        ]
        path = self.root / "policy.toml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def patch_receipt(self, fn):
        path = self.job / "receipt.json"
        rec = json.loads(path.read_text())
        fn(rec)
        path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return rec

    def set_junit(self, data: bytes, summary=None):
        (self.job / "artifacts" / "junit.xml").write_bytes(data)

        def _patch(rec):
            rec["reports"][0]["size_bytes"] = len(data)
            rec["reports"][0]["sha256"] = sha256_hex(data)
            if summary is not None:
                rec["junit"] = summary

        self.patch_receipt(_patch)

    def add_lcov(self, data: bytes):
        (self.job / "artifacts" / "lcov.info").write_bytes(data)

        def _patch(rec):
            rec["reports"].append(
                {"kind": "lcov", "path": "artifacts/lcov.info",
                 "size_bytes": len(data), "sha256": sha256_hex(data)}
            )

        self.patch_receipt(_patch)

    def run_both(self):
        py = evaluate(
            self.policy, self.sha, self.ev,
            expected_run_id=self.expected_run_id,
            expected_attempt=self.expected_attempt,
        )
        cmd = [
            "node", str(ORACLE), "--policy", str(self.write_policy_file()),
            "--expected-source-sha", self.sha, "--evidence", str(self.ev),
        ]
        if self.expected_run_id is not None:
            cmd += ["--expected-run-id", self.expected_run_id]
        if self.expected_attempt is not None:
            cmd += ["--expected-attempt", str(self.expected_attempt)]
        cmd += self.extra_oracle_args
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert proc.stdout.strip(), f"oracle no output: {proc.stderr}"
        ora = json.loads(proc.stdout)
        return py, ora, proc.returncode


def assert_parity(py, ora, rc, name):
    assert py["status"] == ora["status"], f"{name}: status PY {py['status']} vs ORA {ora['status']}"
    assert sorted(py["reason_codes"]) == sorted(ora["reason_codes"]), (
        f"{name}: codes PY {sorted(py['reason_codes'])} vs ORA {sorted(ora['reason_codes'])}"
    )
    assert py["jobs_verified"] == ora["jobs_verified"], (
        f"{name}: jobs PY {py['jobs_verified']} vs ORA {ora['jobs_verified']}"
    )
    py_errs = sorted(
        (e.get("code"), e.get("job_id", ""), e.get("path", ""), e.get("message", ""))
        for e in py["report_errors"]
    )
    ora_errs = sorted(
        (e.get("code"), e.get("job_id", ""), e.get("path", ""), e.get("message", ""))
        for e in ora["report_errors"]
    )
    assert py_errs == ora_errs, f"{name}: report_errors PY {py_errs} vs ORA {ora_errs}"
    py_ids = sorted(
        (m["job_id"], m["field"], str(m["expected"]), str(m["actual"]))
        for m in py["identity_mismatches"]
    )
    ora_ids = sorted(
        (m["job_id"], m["field"], str(m["expected"]), str(m["actual"]))
        for m in ora["identity_mismatches"]
    )
    assert py_ids == ora_ids, f"{name}: identity PY {py_ids} vs ORA {ora_ids}"
    expected_exit = {"BOUND_PASS": 0, "BOUND_FAIL": 1, "UNBOUND": 2, "INVALID": 3, "INTERNAL_ERROR": 4}[py["status"]]
    assert rc == expected_exit, f"{name}: oracle exit {rc} vs {expected_exit} for {py['status']}"


# --- F-02: LCOV ------------------------------------------------------------

def test_parity_r2_malformed_lcov(tmp_path):
    c = Case(tmp_path, lcov_required=True)
    c.add_lcov(b"TN:\nSF:src/foo.py\nDA:1,1\nBADTAG:zzz\nend_of_record\n")
    assert_parity(*c.run_both(), "R2-malformed-lcov")


def test_parity_lcov_valid_control(tmp_path):
    c = Case(tmp_path, lcov_required=True)
    good = (ROOT / "fixtures" / "s0" / "n08-lcov-only" / "evidence"
            / "unit-linux-py312" / "artifacts" / "lcov.info").read_bytes()
    c.add_lcov(good)
    assert_parity(*c.run_both(), "lcov-valid-control")


@pytest.mark.parametrize("name,data", [
    ("missing-end-of-record", b"TN:\nSF:src/foo.py\nDA:1,1\n"),
    ("end-of-record-no-open", b"end_of_record\n"),
    ("no-records", b""),
    ("absolute-sf", b"TN:\nSF:/abs/foo.py\nDA:1,1\nend_of_record\n"),
    ("dotdot-sf", b"TN:\nSF:src/../foo.py\nDA:1,1\nend_of_record\n"),
    ("duplicate-da", b"TN:\nSF:src/foo.py\nDA:1,1\nDA:1,0\nend_of_record\n"),
    ("lf-mismatch", b"TN:\nSF:src/foo.py\nDA:1,1\nLF:9\nend_of_record\n"),
    ("da-before-sf", b"TN:\nDA:1,1\nend_of_record\n"),
    ("record-no-sf", b"TN:\nDA:1,1\nend_of_record\n"),
    ("unknown-tag-lh", b"TN:\nSF:src/foo.py\nDA:1,1\nLH:1\nWAT:1\nend_of_record\n"),
])
def test_parity_lcov_malformed_variants(tmp_path, name, data):
    c = Case(tmp_path, lcov_required=True)
    c.add_lcov(data)
    assert_parity(*c.run_both(), f"lcov-{name}")


# --- F-03/F-04: JUnit ------------------------------------------------------

def test_parity_r3_attr_mismatch(tmp_path):
    c = Case(tmp_path)
    c.set_junit(junit_xml(10, tests_attr=999))
    assert_parity(*c.run_both(), "R3-attr-mismatch")


@pytest.mark.parametrize("name,data,summary", [
    ("attr-failures-mismatch",
     junit_xml(10, n_fail=0).replace(b'failures="0"', b'failures="3"', 1), None),
    ("attr-skipped-mismatch",
     junit_xml(10, n_skip=2).replace(b'skipped="2"', b'skipped="0"', 1), None),
    ("attr-non-integer",
     b'<?xml version="1.0"?>\n<testsuite name="s" tests="ten" failures="0" errors="0" skipped="0">'
     + b'<testcase classname="t" name="t0"/></testsuite>\n', None),
    ("testsuites-wrapper-attr-mismatch",
     b'<?xml version="1.0"?>\n<testsuites tests="99" failures="0" errors="0" skipped="0">'
     b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="t" name="t0"/>'
     b'</testsuite></testsuites>\n', {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}),
    ("wrong-root",
     b'<?xml version="1.0"?>\n<wrong tests="1"><testcase/></wrong>\n', None),
    ("mismatched-close",
     b'<?xml version="1.0"?>\n<testsuite tests="1"><testcase></testcases></testsuite>\n', None),
    ("duplicate-attr",
     b'<?xml version="1.0"?>\n<testsuite tests="1"><testcase name="a" name="b"/></testsuite>\n', None),
    ("unbound-prefix",
     b'<?xml version="1.0"?>\n<testsuite tests="1"><x:testcase/></testsuite>\n', None),
    ("junk-after-root",
     b'<?xml version="1.0"?>\n<testsuite tests="1"><testcase/></testsuite> trailing\n', None),
    ("empty-testsuites",
     b'<?xml version="1.0"?>\n<testsuites tests="0"></testsuites>\n', None),
    ("nested-suite-attrs-ignored",
     b'<?xml version="1.0"?>\n<testsuite name="outer" tests="1" failures="0" errors="0" skipped="0">'
     b'<testsuite name="inner" tests="99" failures="99" errors="0" skipped="0">'
     b'<testcase classname="t" name="t0"/></testsuite></testsuite>\n',
     {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}),
])
def test_parity_junit_variants(tmp_path, name, data, summary):
    c = Case(tmp_path)
    c.set_junit(data, summary)
    assert_parity(*c.run_both(), f"junit-{name}")


@pytest.mark.parametrize("name,data", [
    ("R4a-cdata-failure",
     junit_xml(10, extra='<testcase classname="t" name="c"><![CDATA[<failure/>]]></testcase>')),
    ("R4b-comment-failure", junit_xml(10, extra="<!-- <failure> -->")),
    ("R4c-bare-testcase-selfclose",
     b'<?xml version="1.0"?>\n<testsuite name="s" tests="1" failures="0" errors="0" skipped="0"><testcase/></testsuite>\n'),
    ("R4d-unclosed-testcase",
     b'<?xml version="1.0"?>\n<testsuite name="s" tests="1" failures="0" errors="0" skipped="0"><testcase></testsuite>\n'),
    ("R4e-doctype",
     b'<?xml version="1.0"?>\n<!DOCTYPE testsuite [<!ENTITY x "y">]>\n<testsuite name="s" tests="10" failures="0" errors="0" skipped="0">'
     + b'<testcase classname="t" name="t0"/>' * 10 + b'</testsuite>\n'),
    ("R4f-namespaced-testcase",
     b'<?xml version="1.0"?>\n<testsuite xmlns:x="urn:x" name="s" tests="1" failures="0" errors="0" skipped="0"><x:testcase classname="t" name="t0"/></testsuite>\n'),
])
def test_parity_r4_variants(tmp_path, name, data):
    c = Case(tmp_path)
    summary = {"tests": 1, "failures": 0, "errors": 0, "skipped": 0} if name in (
        "R4c-bare-testcase-selfclose", "R4d-unclosed-testcase", "R4f-namespaced-testcase") else None
    c.set_junit(data, summary)
    assert_parity(*c.run_both(), name)


def test_parity_r4a2_cdata(tmp_path):
    c = Case(tmp_path)
    cases = "".join(f'<testcase classname="t" name="test_{i}"></testcase>' for i in range(9))
    cases += '<testcase classname="t" name="test_9"><![CDATA[<failure/>]]></testcase>'
    data = (b'<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="0" errors="0" skipped="0">'
            + cases.encode() + b'</testsuite>\n')
    c.set_junit(data)
    assert_parity(*c.run_both(), "R4a2-cdata-failure")


def test_parity_r4b2_comment(tmp_path):
    c = Case(tmp_path)
    c.set_junit(junit_xml(10, extra="<!-- <failure> -->"))
    assert_parity(*c.run_both(), "R4b2-comment-failure")


def test_parity_r4a3_cdata_space(tmp_path):
    c = Case(tmp_path)
    cases = "".join(f'<testcase classname="t" name="test_{i}"></testcase>' for i in range(9))
    cases += '<testcase classname="t" name="test_9"><![CDATA[<failure >oops</failure>]]></testcase>'
    data = (b'<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="0" errors="0" skipped="0">'
            + cases.encode() + b'</testsuite>\n')
    c.set_junit(data)
    assert_parity(*c.run_both(), "R4a3-cdata-failure-space")


def test_parity_r4g_selfclosing_failure(tmp_path):
    c = Case(tmp_path)
    cases = "".join(f'<testcase classname="t" name="test_{i}"></testcase>' for i in range(9))
    cases += '<testcase classname="t" name="test_9"><failure/></testcase>'
    data = (b'<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="1" errors="0" skipped="0">'
            + cases.encode() + b'</testsuite>\n')
    c.set_junit(data, summary={"tests": 10, "failures": 1, "errors": 0, "skipped": 0})
    assert_parity(*c.run_both(), "R4g-selfclosing-failure")


# --- F-01 mirror: multi-JUnit ---------------------------------------------

def _multi_junit_case(tmp_path, fail_first: bool):
    c = Case(tmp_path)
    fail_xml = junit_xml(10, n_fail=2)
    pass_xml = junit_xml(10)
    (c.job / "artifacts" / "junit-fail.xml").write_bytes(fail_xml)
    (c.job / "artifacts" / "junit.xml").write_bytes(pass_xml)
    fail_rep = {"kind": "junit", "path": "artifacts/junit-fail.xml",
                "size_bytes": len(fail_xml), "sha256": sha256_hex(fail_xml)}
    pass_rep = {"kind": "junit", "path": "artifacts/junit.xml",
                "size_bytes": len(pass_xml), "sha256": sha256_hex(pass_xml)}

    def _patch(rec):
        rec["reports"] = [fail_rep, pass_rep] if fail_first else [pass_rep, fail_rep]
        rec["junit"] = {"tests": 10, "failures": 0, "errors": 0, "skipped": 0}

    c.patch_receipt(_patch)
    return c


def test_parity_r24_multi_junit_first_fails(tmp_path):
    c = _multi_junit_case(tmp_path, fail_first=True)
    py, ora, rc = c.run_both()
    assert sorted(py["reason_codes"]) == ["EXIT_CODE_MISMATCH", "JUNIT_FAILED", "JUNIT_SUMMARY_MISMATCH"]
    assert_parity(py, ora, rc, "R24-multi-junit-first-fails")


def test_parity_r24b_multi_junit_order_swapped(tmp_path):
    c = _multi_junit_case(tmp_path, fail_first=False)
    py, ora, rc = c.run_both()
    assert sorted(py["reason_codes"]) == ["EXIT_CODE_MISMATCH", "JUNIT_FAILED", "JUNIT_SUMMARY_MISMATCH"]
    assert_parity(py, ora, rc, "R24b-order-swapped")


def test_parity_multi_junit_all_passing_control(tmp_path):
    c = Case(tmp_path)
    pass_xml = junit_xml(10)
    (c.job / "artifacts" / "junit-2.xml").write_bytes(pass_xml)
    rep2 = {"kind": "junit", "path": "artifacts/junit-2.xml",
            "size_bytes": len(pass_xml), "sha256": sha256_hex(pass_xml)}
    c.patch_receipt(lambda rec: rec["reports"].append(rep2))
    assert_parity(*c.run_both(), "multi-junit-all-passing")


def test_parity_multi_junit_failing_second_with_exit_1(tmp_path):
    c = _multi_junit_case(tmp_path, fail_first=False)
    c.patch_receipt(lambda rec: (rec.__setitem__("junit", {"tests": 10, "failures": 2, "errors": 0, "skipped": 0}),
                                 rec["command"].__setitem__("exit_code", 1)))
    assert_parity(*c.run_both(), "multi-junit-failing-second-exit-1")


# --- F-05: symlinks ---------------------------------------------------------

def test_parity_r5_symlink_escape(tmp_path):
    c = Case(tmp_path)
    outside = tmp_path / "outside.xml"
    good = junit_xml(10)
    outside.write_bytes(good)
    (c.job / "artifacts" / "junit.xml").unlink()
    (c.job / "artifacts" / "junit.xml").symlink_to(outside)
    c.patch_receipt(lambda rec: (rec["reports"][0].__setitem__("size_bytes", len(good)),
                                 rec["reports"][0].__setitem__("sha256", sha256_hex(good))))
    assert_parity(*c.run_both(), "R5-symlink-escape")


def test_parity_symlink_inside_job_dir(tmp_path):
    c = Case(tmp_path)
    good = junit_xml(10)
    (c.job / "artifacts" / "junit-real.xml").write_bytes(good)
    (c.job / "artifacts" / "junit.xml").unlink()
    (c.job / "artifacts" / "junit.xml").symlink_to(c.job / "artifacts" / "junit-real.xml")
    c.patch_receipt(lambda rec: (rec["reports"][0].__setitem__("size_bytes", len(good)),
                                 rec["reports"][0].__setitem__("sha256", sha256_hex(good))))
    assert_parity(*c.run_both(), "symlink-inside-job-dir")


def test_parity_symlink_dangling_outside(tmp_path):
    c = Case(tmp_path)
    good = junit_xml(10)
    (c.job / "artifacts" / "junit.xml").unlink()
    (c.job / "artifacts" / "junit.xml").symlink_to(tmp_path / "no-such.xml")
    c.patch_receipt(lambda rec: (rec["reports"][0].__setitem__("size_bytes", len(good)),
                                 rec["reports"][0].__setitem__("sha256", sha256_hex(good))))
    assert_parity(*c.run_both(), "symlink-dangling-outside")


# --- F-06: receipt schema ---------------------------------------------------

@pytest.mark.parametrize("name,mutate", [
    ("run_attempt-200000+extra-field",
     lambda rec: (rec["ci"].__setitem__("run_attempt", 200000),
                  rec.__setitem__("extra_forged_field", "BOUND_PASS"))),
    ("job_id-space", lambda rec: rec.__setitem__("job_id", "bad job")),
    ("empty-matrix", lambda rec: rec.__setitem__("matrix", {})),
    ("matrix-value-object", lambda rec: rec["matrix"].__setitem__("os", {"nested": True})),
    ("extra-git-field", lambda rec: rec["git"].__setitem__("forged", True)),
    ("bad-provider", lambda rec: rec["ci"].__setitem__("provider", "jenkins")),
    ("run_id-too-long", lambda rec: rec["ci"].__setitem__("run_id", "x" * 65)),
    ("display-too-long", lambda rec: rec["command"].__setitem__("display", "x" * 513)),
    ("size-over-1gib", lambda rec: rec["reports"][0].__setitem__("size_bytes", 1073741825)),
    ("junit-tests-over-max", lambda rec: rec["junit"].__setitem__("tests", 100000001)),
    ("report-path-dotdot", lambda rec: rec["reports"][0].__setitem__("path", "artifacts/../junit.xml")),
    ("missing-runner-python", lambda rec: rec["runner"].pop("python")),
    ("extra-junit-field", lambda rec: rec["junit"].__setitem__("forged", 1)),
    ("source-state-extra", lambda rec: rec["source_state_before"].__setitem__("extra", 1)),
    ("bad-started-at", lambda rec: rec.__setitem__("started_at", "not-a-time")),
    ("run_attempt-zero", lambda rec: rec["ci"].__setitem__("run_attempt", 0)),
    ("exit-code-over-max", lambda rec: rec["command"].__setitem__("exit_code", 256)),
    ("reports-33-items", lambda rec: rec.__setitem__("reports", rec["reports"] * 33)),
])
def test_parity_receipt_schema(tmp_path, name, mutate):
    c = Case(tmp_path)
    c.patch_receipt(mutate)
    assert_parity(*c.run_both(), f"receipt-schema-{name}")


# --- F-07: TOML / policy text ----------------------------------------------

def _oracle_cli_raw(policy_text: str, tmp_path: Path, ev: Path, sha: str):
    pdir = tmp_path / "pol"
    pdir.mkdir(exist_ok=True)
    pp = pdir / "policy.toml"
    pp.write_text(policy_text, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(ORACLE), "--policy", str(pp),
         "--expected-source-sha", sha, "--evidence", str(ev)],
        capture_output=True, text=True, timeout=60)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"_stdout": proc.stdout, "_stderr": proc.stderr}


def test_parity_r6a_dup_min_tests(tmp_path):
    c = Case(tmp_path)
    text = (FIX / "policy.toml").read_text().replace("min_tests = 1", "min_tests = 5\nmin_tests = 0", 1)
    with pytest.raises(Exception):
        load_policy_text(text)
    rc, ora = _oracle_cli_raw(text, tmp_path, c.ev, c.sha)
    assert rc == 3 and ora.get("status") == "INVALID" and ora.get("reason_codes") == ["INVALID_POLICY"], ora


def load_policy_text(text: str):
    import tempfile
    from benchreceipt.policy import load_policy as _lp

    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        name = fh.name
    try:
        return _lp(Path(name))
    finally:
        Path(name).unlink(missing_ok=True)


def test_parity_r6b_trailing_comment(tmp_path):
    c = Case(tmp_path)
    text = (FIX / "policy.toml").read_text().replace("min_tests = 1", "min_tests = 1  # trailing comment", 1)
    py_policy = load_policy_text(text)
    assert py_policy["min_tests"] == 1
    rc, ora = _oracle_cli_raw(text, tmp_path, c.ev, c.sha)
    assert ora.get("status") != "INVALID" or ora.get("reason_codes") != ["INVALID_POLICY"], ora
    # Full verdict parity: same evidence, policy accepted on both sides.
    py = evaluate(py_policy, c.sha, c.ev)
    assert py["status"] == ora["status"]
    assert sorted(py["reason_codes"]) == sorted(ora["reason_codes"])


def test_parity_r6c_escaped_quote(tmp_path):
    c = Case(tmp_path)
    text = (FIX / "policy.toml").read_text().replace('expected_workflow = "CI"', 'expected_workflow = "CI\\"X"', 1)
    py_policy = load_policy_text(text)
    assert py_policy["expected_workflow"] == 'CI"X'
    rc, ora = _oracle_cli_raw(text, tmp_path, c.ev, c.sha)
    py = evaluate(py_policy, c.sha, c.ev)
    # The raw n02 policy requires both jobs but the case evidence has
    # one, so the matrix finding joins the workflow finding on both.
    assert py["status"] == ora["status"] == "UNBOUND"
    assert sorted(py["reason_codes"]) == sorted(ora["reason_codes"]) == ["MATRIX_MISSING_JOB", "WORKFLOW_MISMATCH"]


def test_parity_r7b_required_jobs_int(tmp_path):
    c = Case(tmp_path)
    text = (FIX / "policy.toml").read_text().replace('"unit-linux-py312"', "123", 1)
    with pytest.raises(Exception):
        load_policy_text(text)
    rc, ora = _oracle_cli_raw(text, tmp_path, c.ev, c.sha)
    assert rc == 3 and ora.get("status") == "INVALID" and ora.get("reason_codes") == ["INVALID_POLICY"], ora


def test_parity_policy_unknown_key(tmp_path):
    c = Case(tmp_path)
    text = (FIX / "policy.toml").read_text() + "\nexpected_source_sha = \"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"\n"
    with pytest.raises(Exception):
        load_policy_text(text)
    rc, ora = _oracle_cli_raw(text, tmp_path, c.ev, c.sha)
    assert rc == 3 and ora.get("status") == "INVALID" and ora.get("reason_codes") == ["INVALID_POLICY"], ora


# --- F-08: run pins ---------------------------------------------------------

def test_parity_r16_pin_wrong_run(tmp_path):
    c = Case(tmp_path)
    c.expected_run_id = "WRONG-RUN"
    c.expected_attempt = 99
    assert_parity(*c.run_both(), "R16-pin-wrong-run")


def test_parity_pin_correct(tmp_path):
    c = Case(tmp_path)
    c.expected_run_id = "9001"
    c.expected_attempt = 2
    assert_parity(*c.run_both(), "pin-correct")


def test_parity_pin_only_attempt_wrong(tmp_path):
    c = Case(tmp_path)
    c.expected_attempt = 99
    assert_parity(*c.run_both(), "pin-only-attempt-wrong")


def test_parity_pin_only_run_id_wrong(tmp_path):
    c = Case(tmp_path)
    c.expected_run_id = "WRONG-RUN"
    assert_parity(*c.run_both(), "pin-only-run-id-wrong")


def test_parity_control_bound_pass(tmp_path):
    c = Case(tmp_path)
    assert_parity(*c.run_both(), "control-bound-pass")
