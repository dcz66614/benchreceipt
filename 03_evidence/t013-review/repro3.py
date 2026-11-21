"""T013 repro part 3: CDATA/comment fixed, multi-junit, symlink, TOML, receipt validation."""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path
ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
SRC = ROOT / "02_source"
sys.path.insert(0, str(SRC / "src"))
FIX = SRC / "fixtures" / "s0" / "n02-two-job-pr-head"
WORK = Path("/tmp/t013-repro/work3")
shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

def junit_xml(n_tests=10, n_fail=0, n_err=0, n_skip=0, tests_attr=None, extra=""):
    cases = []
    for i in range(n_tests):
        inner = ""
        if i < n_fail: inner = '<failure message="x">t</failure>'
        elif i < n_fail + n_err: inner = '<error message="x">t</error>'
        elif i < n_fail + n_err + n_skip: inner = "<skipped/>"
        cases.append(f'<testcase classname="t" name="test_{i}">{inner}</testcase>')
    ta = tests_attr if tests_attr is not None else n_tests
    return (f'<?xml version="1.0"?>\n<testsuite name="s" tests="{ta}" failures="{n_fail}" '
            f'errors="{n_err}" skipped="{n_skip}">{extra}{"".join(cases)}</testsuite>\n').encode()

def base_evidence(dst, jobs=("unit-linux-py312",)):
    shutil.copytree(FIX / "evidence", dst)
    for d in list(dst.iterdir()):
        if d.name not in jobs: shutil.rmtree(d)
    policy = load_policy(FIX / "policy.toml")
    policy["required_jobs"] = list(jobs)
    sha = json.loads((FIX / "expected.json").read_text())["expected_source_sha"]
    return policy, sha

def write_policy_file(dst, policy):
    Path(dst).mkdir(parents=True, exist_ok=True)
    lines = ["schema_version = 1", f'source_mode = "{policy["source_mode"]}"',
             f'expected_workflow = "{policy["expected_workflow"]}"',
             "required_jobs = [", ", ".join(f'"{j}"' for j in policy["required_jobs"]), "]",
             f'min_tests = {policy["min_tests"]}',
             f'require_clean_source_after = {str(policy["require_clean_source_after"]).lower()}',
             f'same_tree_across_jobs = {str(policy["same_tree_across_jobs"]).lower()}',
             f'same_run_id = {str(policy["same_run_id"]).lower()}',
             f'same_run_attempt = {str(policy["same_run_attempt"]).lower()}',
             "", "[reports]", f'junit = "{policy["reports"]["junit"]}"',
             f'lcov = "{policy["reports"]["lcov"]}"', "", "[security]",
             "store_stdout = false", "store_stderr = false", "store_full_environment = false"]
    pp = Path(dst) / "policy.toml"; pp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pp

def run_oracle(policy_path, sha, evidence, extra_args=None):
    cmd = ["node", str(SRC / "oracle" / "verify.mjs"), "--policy", str(policy_path),
           "--expected-source-sha", sha, "--evidence", str(evidence)] + (extra_args or [])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    try: res = json.loads(p.stdout)
    except Exception: res = {"_stdout": p.stdout[:200], "_stderr": p.stderr[:200]}
    return p.returncode, res

def both(name, evdir, policy, sha, extra_args=None):
    py = evaluate(policy, sha, evdir)
    pp = write_policy_file(evdir.parent / (evdir.name + "-pol"), policy)
    rc, ora = run_oracle(pp, sha, evdir, extra_args)
    print(f"{name}: PY {py['status']} {sorted(py['reason_codes'])} jobs={py['jobs_verified']} | "
          f"ORA exit={rc} {ora.get('status')} {sorted(ora.get('reason_codes', []))} jobs={ora.get('jobs_verified')}")
    return py, ora

def set_junit(evdir, job, data, summary=None):
    jd = Path(evdir) / job
    (jd / "artifacts" / "junit.xml").write_bytes(data)
    rec = json.loads((jd / "receipt.json").read_text())
    rec["reports"][0]["size_bytes"] = len(data)
    rec["reports"][0]["sha256"] = hashlib.sha256(data).hexdigest()
    if summary is not None: rec["junit"] = summary
    (jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec

print("== R4a2 CDATA failure, attrs match production counts ==")
ev = WORK / "r4a2"; pol, sha = base_evidence(ev)
cases = "".join(f'<testcase classname="t" name="test_{i}"></testcase>' for i in range(9))
cases += '<testcase classname="t" name="test_9"><![CDATA[<failure/>]]></testcase>'
data = (b'<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="0" errors="0" skipped="0">'
        + cases.encode() + b'</testsuite>\n')
set_junit(ev, "unit-linux-py312", data)
both("R4a2-cdata-failure", ev, pol, sha)

print("== R4b2 comment failure, attrs match production counts ==")
ev = WORK / "r4b2"; pol, sha = base_evidence(ev)
set_junit(ev, "unit-linux-py312", junit_xml(10, extra="<!-- <failure> -->"))
both("R4b2-comment-failure", ev, pol, sha)

print("== R24 multi-junit: first report failing, second passing, summary matches second ==")
ev = WORK / "r24"; pol, sha = base_evidence(ev)
jd = ev / "unit-linux-py312"
fail_xml = junit_xml(10, n_fail=2)
pass_xml = junit_xml(10)
(jd / "artifacts" / "junit-fail.xml").write_bytes(fail_xml)
(jd / "artifacts" / "junit.xml").write_bytes(pass_xml)
rec = json.loads((jd / "receipt.json").read_text())
rec["reports"] = [
    {"kind": "junit", "path": "artifacts/junit-fail.xml", "size_bytes": len(fail_xml), "sha256": hashlib.sha256(fail_xml).hexdigest()},
    {"kind": "junit", "path": "artifacts/junit.xml", "size_bytes": len(pass_xml), "sha256": hashlib.sha256(pass_xml).hexdigest()},
]
rec["junit"] = {"tests": 10, "failures": 0, "errors": 0, "skipped": 0}
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
both("R24-multi-junit-first-fails", ev, pol, sha)
print("R24 note: same input with report order swapped (passing first, failing second):")
ev = WORK / "r24b"; pol, sha = base_evidence(ev)
jd = ev / "unit-linux-py312"
(jd / "artifacts" / "junit-fail.xml").write_bytes(fail_xml)
(jd / "artifacts" / "junit.xml").write_bytes(pass_xml)
rec = json.loads((jd / "receipt.json").read_text())
rec["reports"] = [
    {"kind": "junit", "path": "artifacts/junit.xml", "size_bytes": len(pass_xml), "sha256": hashlib.sha256(pass_xml).hexdigest()},
    {"kind": "junit", "path": "artifacts/junit-fail.xml", "size_bytes": len(fail_xml), "sha256": hashlib.sha256(fail_xml).hexdigest()},
]
rec["junit"] = {"tests": 10, "failures": 0, "errors": 0, "skipped": 0}
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
both("R24b-order-swapped", ev, pol, sha)

print("== R5 oracle: report-path symlink escape ==")
ev = WORK / "r5"; pol, sha = base_evidence(ev)
jd = ev / "unit-linux-py312"
outside = WORK / "outside.xml"
good = junit_xml(10)
outside.write_bytes(good)
(jd / "artifacts" / "junit.xml").unlink()
(jd / "artifacts" / "junit.xml").symlink_to(outside)
rec = json.loads((jd / "receipt.json").read_text())
rec["reports"][0]["size_bytes"] = len(good)
rec["reports"][0]["sha256"] = hashlib.sha256(good).hexdigest()
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
both("R5-symlink-escape", ev, pol, sha)

print("== R6 oracle TOML divergences (raw policy text, oracle CLI only) ==")
pol_text_dup = (FIX / "policy.toml").read_text().replace("min_tests = 1", "min_tests = 5\nmin_tests = 0", 1)
pp = WORK / "r6-pol-dup"; pp.mkdir(parents=True, exist_ok=True)
(pp / "policy.toml").write_text(pol_text_dup, encoding="utf-8")
ev = WORK / "r6"; pol, sha = base_evidence(ev)
# python side: load_policy on the dup file
from benchreceipt.policy import load_policy as lp  # noqa: E402
try:
    lp(pp / "policy.toml"); print("R6a dup min_tests: PY ACCEPTS (unexpected)")
except Exception as e:
    print("R6a dup min_tests: PY rejects:", type(e).__name__)
rc, ora = run_oracle(pp / "policy.toml", sha, ev)
print(f"R6a dup min_tests: ORA exit={rc} {ora.get('status')} {ora.get('reason_codes')}")
pol_text_comment = (FIX / "policy.toml").read_text().replace("min_tests = 1", "min_tests = 1  # trailing comment", 1)
(pp / "policy.toml").write_text(pol_text_comment, encoding="utf-8")
try:
    lp(pp / "policy.toml"); print("R6b trailing comment: PY ACCEPTS")
except Exception as e:
    print("R6b trailing comment: PY rejects:", type(e).__name__)
rc, ora = run_oracle(pp / "policy.toml", sha, ev)
print(f"R6b trailing comment: ORA exit={rc} {ora.get('status')} {ora.get('reason_codes')}")

print("== R7 oracle receipt-validation weakness ==")
ev = WORK / "r7"; pol, sha = base_evidence(ev)
jd = ev / "unit-linux-py312"
rec = json.loads((jd / "receipt.json").read_text())
rec["ci"]["run_attempt"] = 200000
rec["extra_forged_field"] = "BOUND_PASS"
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
both("R7a-run_attempt-200000+extra-field", ev, pol, sha)
# required_jobs=[123] policy: python INVALID_POLICY vs oracle
ev = WORK / "r7b"; pol, sha = base_evidence(ev)
pp = WORK / "r7b-pol"; pp.mkdir(parents=True, exist_ok=True)
txt = (FIX / "policy.toml").read_text().replace('"unit-linux-py312"', "123", 1)
(pp / "policy.toml").write_text(txt, encoding="utf-8")
try:
    lp(pp / "policy.toml"); print("R7b required_jobs=[123]: PY ACCEPTS (unexpected)")
except Exception as e:
    print("R7b required_jobs=[123]: PY rejects:", type(e).__name__)
rc, ora = run_oracle(pp / "policy.toml", sha, ev)
print(f"R7b required_jobs=[123]: ORA exit={rc} {ora.get('status')} {ora.get('reason_codes')} missing={ora.get('missing_jobs')}")

print("== R16 oracle ignores --expected-run-id pin ==")
ev = WORK / "r16"; pol, sha = base_evidence(ev)
pp = write_policy_file(ev.parent / "r16-pol", pol)
rc, ora = run_oracle(pp, sha, ev, extra_args=["--expected-run-id", "WRONG-RUN", "--expected-attempt", "99"])
print(f"R16 oracle --expected-run-id WRONG-RUN: exit={rc} {ora.get('status')} {ora.get('reason_codes')}")
py = evaluate(pol, sha, ev, expected_run_id="WRONG-RUN", expected_attempt=99)
print(f"R16 python --expected-run-id WRONG-RUN: {py['status']} {sorted(py['reason_codes'])}")
