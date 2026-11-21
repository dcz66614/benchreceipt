"""T013 repro part 2: redaction with neutral values + oracle divergences."""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path
ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
SRC = ROOT / "02_source"
sys.path.insert(0, str(SRC / "src"))
FIX = SRC / "fixtures" / "s0" / "n02-two-job-pr-head"
WORK = Path("/tmp/t013-repro/work2")
shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
from benchreceipt.command import display_command  # noqa: E402
from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

print("== R1b redaction, neutral values ==")
for argv in [
    ["pytest", "--key", "hunter2"],
    ["pytest", "--auth", "abc123"],
    ["pytest", "--passwd", "hunter2"],
    ["pytest", "--passphrase", "hunter2"],
    ["pytest", "--private-key", "MIIEvAIBADANBgkqhkiG9w0BAQEFAASC"],
    ["pytest", "--credential", "hunter2"],
    ["pytest", r"\\server\share\file.txt"],
    ["pytest", "file:///home/sam/file.txt"],
    ["pytest", "/home/sam/file.txt"],
    ["pytest", "prefix:/home/sam/file.txt"],
    ["pytest", "--api-key=hunter2"],
    ["pytest", "--token=hunter2"],
]:
    print("R1b", argv[1:], "->", repr(display_command(argv)))

def junit_xml(n_tests=10, n_fail=0, n_err=0, n_skip=0, tests_attr=None, extra="", raw_cases=None):
    if raw_cases is not None:
        body = raw_cases
    else:
        cases = []
        for i in range(n_tests):
            inner = ""
            if i < n_fail: inner = '<failure message="x">t</failure>'
            elif i < n_fail + n_err: inner = '<error message="x">t</error>'
            elif i < n_fail + n_err + n_skip: inner = "<skipped/>"
            cases.append(f'<testcase classname="t" name="test_{i}">{inner}</testcase>')
        body = "".join(cases)
    ta = tests_attr if tests_attr is not None else n_tests
    return (f'<?xml version="1.0"?>\n<testsuite name="s" tests="{ta}" failures="{n_fail}" '
            f'errors="{n_err}" skipped="{n_skip}">{extra}{body}</testsuite>\n').encode()

def base_evidence(dst, jobs=("unit-linux-py312",), lcov_required=False):
    shutil.copytree(FIX / "evidence", dst)
    for d in list(dst.iterdir()):
        if d.name not in jobs:
            shutil.rmtree(d)
    policy = load_policy(FIX / "policy.toml")
    policy["required_jobs"] = list(jobs)
    if lcov_required:
        policy["reports"]["lcov"] = "required"
    sha = json.loads((FIX / "expected.json").read_text())["expected_source_sha"]
    return policy, sha

def write_policy_file(dst, policy):
    # hand-write TOML matching the policy dict (subset the oracle can parse)
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
    Path(dst).mkdir(parents=True, exist_ok=True)
    pp = Path(dst) / "policy.toml"; pp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pp

def run_oracle(policy_path, sha, evidence, extra_args=None):
    cmd = ["node", str(SRC / "oracle" / "verify.mjs"), "--policy", str(policy_path),
           "--expected-source-sha", sha, "--evidence", str(evidence)] + (extra_args or [])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    try: res = json.loads(p.stdout)
    except Exception: res = {"_stdout": p.stdout, "_stderr": p.stderr}
    return p.returncode, res

def both(name, evdir, policy, sha):
    py = evaluate(policy, sha, evdir)
    pp = write_policy_file(evdir.parent / (evdir.name + "-pol"), policy)
    rc, ora = run_oracle(pp, sha, evdir)
    print(f"{name}: PY {py['status']} {sorted(py['reason_codes'])} jobs={py['jobs_verified']} | "
          f"ORA exit={rc} {ora.get('status')} {sorted(ora.get('reason_codes', []))} jobs={ora.get('jobs_verified')}")
    return py, ora

def patch_junit(evdir, job, data):
    jd = Path(evdir) / job
    (jd / "artifacts" / "junit.xml").write_bytes(data)
    rec = json.loads((jd / "receipt.json").read_text())
    rec["reports"][0]["size_bytes"] = len(data)
    rec["reports"][0]["sha256"] = hashlib.sha256(data).hexdigest()
    (jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rec

print("== R2 oracle: malformed LCOV (policy lcov required) ==")
ev = WORK / "r2"; pol, sha = base_evidence(ev, lcov_required=True)
jd = ev / "unit-linux-py312"
lcov_bad = b"TN:\nSF:src/foo.py\nDA:1,1\nBADTAG:zzz\nend_of_record\n"
(jd / "artifacts" / "lcov.info").write_bytes(lcov_bad)
rec = json.loads((jd / "receipt.json").read_text())
rec["reports"].append({"kind": "lcov", "path": "artifacts/lcov.info",
                       "size_bytes": len(lcov_bad), "sha256": hashlib.sha256(lcov_bad).hexdigest()})
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
both("R2-malformed-lcov", ev, pol, sha)

print("== R3 oracle: JUnit count-attr mismatch ==")
ev = WORK / "r3"; pol, sha = base_evidence(ev)
patch_junit(ev, "unit-linux-py312", junit_xml(10, tests_attr=999))
both("R3-attr-mismatch", ev, pol, sha)

print("== R4 oracle: JUnit regex gaps ==")
for name, data in [
    ("R4a-cdata-failure", junit_xml(10, extra="<testcase classname=\"t\" name=\"c\"><![CDATA[<failure/>]]></testcase>")),
    ("R4b-comment-failure", junit_xml(10, extra="<!-- <failure> -->")),
    ("R4c-bare-testcase-selfclose", b'<?xml version="1.0"?>\n<testsuite name="s" tests="1" failures="0" errors="0" skipped="0"><testcase/></testsuite>\n'),
    ("R4d-unclosed-testcase", b'<?xml version="1.0"?>\n<testsuite name="s" tests="1" failures="0" errors="0" skipped="0"><testcase></testsuite>\n'),
    ("R4e-doctype", b'<?xml version="1.0"?>\n<!DOCTYPE testsuite [<!ENTITY x "y">]>\n<testsuite name="s" tests="10" failures="0" errors="0" skipped="0">' + b'<testcase classname="t" name="t0"/>'*10 + b'</testsuite>\n'),
    ("R4f-namespaced-testcase", b'<?xml version="1.0"?>\n<testsuite xmlns:x="urn:x" name="s" tests="1" failures="0" errors="0" skipped="0"><x:testcase classname="t" name="t0"/></testsuite>\n'),
]:
    ev = WORK / name.lower(); pol, sha = base_evidence(ev)
    rec = patch_junit(ev, "unit-linux-py312", data)
    # receipt summary stays (10,0,0,0) except R4c/d/f where file has 1 test: fix summary to match file truth
    if name in ("R4c-bare-testcase-selfclose", "R4d-unclosed-testcase", "R4f-namespaced-testcase"):
        rec["junit"] = {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}
        (ev / "unit-linux-py312" / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    both(name, ev, pol, sha)
