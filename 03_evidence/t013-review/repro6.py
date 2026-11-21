import hashlib, json, shutil, subprocess, sys
from pathlib import Path
ROOT = Path("/home/hatch/workspace/p027-benchreceipt"); SRC = ROOT/"02_source"
sys.path.insert(0, str(SRC/"src"))
FIX = SRC/"fixtures"/"s0"/"n02-two-job-pr-head"
WORK = Path("/tmp/t013-repro/work6"); shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
from benchreceipt.policy import load_policy
from benchreceipt.verify import evaluate
from benchreceipt.schema import validate_against_schema, SchemaValidationError
from benchreceipt.command import display_command

def base_evidence(dst, jobs=("unit-linux-py312",)):
    shutil.copytree(FIX/"evidence", dst)
    for d in list(dst.iterdir()):
        if d.name not in jobs: shutil.rmtree(d)
    policy = load_policy(FIX/"policy.toml"); policy["required_jobs"]=list(jobs)
    sha = json.loads((FIX/"expected.json").read_text())["expected_source_sha"]
    return policy, sha

print("== R13b fallback result itself schema-valid? ==")
ev = WORK/"r13"; pol, sha = base_evidence(ev)
for i in range(130):
    d = ev/f"extra-job-{i:03d}"; d.mkdir(parents=True, exist_ok=True)
    (d/"receipt.json").write_text("{not json", encoding="utf-8")
v = evaluate(pol, sha, ev)
print("R13b status:", v["status"], "unexpected_jobs:", len(v["unexpected_jobs"]),
      "missing:", v["missing_jobs"], "report_errors:", len(v["report_errors"]))
try:
    validate_against_schema(v, "result"); print("R13b fallback result: SCHEMA-VALID")
except SchemaValidationError as e:
    print("R13b fallback result: SCHEMA-INVALID:", e.errors[:3])
# CLI on the same evidence
out = WORK/"r13-out.json"
p = subprocess.run([".venv/bin/python","-m","benchreceipt","verify","--policy",str(FIX/"policy.toml"),
  "--evidence",str(ev),"--expected-source-sha",sha,"--out",str(out)],
  capture_output=True, text=True, cwd=str(ROOT), timeout=60,
  env={"PATH":"/usr/bin:/bin","TMPDIR":str(ROOT/".tmp")})
print("R13b CLI verify exit:", p.returncode, "out file written:", out.exists(), p.stdout.strip()[:160], p.stderr.strip()[:160])

print("== R9c capture with giant-int JUnit attr ==")
import tempfile
from benchreceipt.capture import capture as do_capture
tmp = Path(tempfile.mkdtemp(prefix="t013-r9c-", dir="/tmp/t013-repro"))
repo = tmp/"repo"; repo.mkdir()
def run(cmd, cwd): subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
run(["git","init","-q","-b","main"], repo)
run(["git","config","user.email","r9c@example.invalid"], repo); run(["git","config","user.name","r9c"], repo)
(repo/"test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
(repo/".gitignore").write_text(".benchreceipt/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
run(["git","add","."], repo); run(["git","commit","-qm","x"], repo)
huge = ('<?xml version="1.0"?>\n<testsuite name="s" tests="' + "9"*5000 +
        '" failures="0" errors="0" skipped="0"><testcase classname="t" name="t0"/></testsuite>\n')
writer = ("import sys; open('.benchreceipt/out/junit.xml','w').write(sys.argv[1])")
try:
    res = do_capture(job_id="unit-linux-py312", matrix={"os":"ubuntu-latest","python":"3.12"},
        argv=[sys.executable,"-c",writer,huge], junit_path=".benchreceipt/out/junit.xml",
        repo_path=repo, cwd=repo)
    print("R9c capture huge-attr junit -> receipt written, junit key present:", "junit" in res.receipt)
except ValueError as e:
    print("R9c capture huge-attr junit -> ValueError propagates (not CaptureError):", type(e).__name__, str(e)[:90])
except Exception as e:
    print("R9c capture huge-attr junit ->", type(e).__name__, str(e)[:120])

print("== R1c truncation happens AFTER redaction (no secret tail leak) ==")
long_argv = ["pytest", "--token", "SECRETVALUE123"] + ["pad"*40]*30
d = display_command(long_argv)
print("R1c display len:", len(d), "contains SECRETVALUE123:", "SECRETVALUE123" in d, "->", repr(d[:60]))
print("== static greps ==")
import re
ora = (SRC/"oracle"/"verify.mjs").read_text()
print("R29 oracle REASON_STATUS has LCOV_MALFORMED:", "LCOV_MALFORMED" in ora.split("const EXIT_BY_STATUS")[0],
      "| has INTERNAL_ERROR code:", '"INTERNAL_ERROR"' in ora.split("const EXIT_BY_STATUS")[0],
      "| STATUS_ORDER:", re.search(r"const STATUS_ORDER = (\[.*?\]);", ora).group(1))
print("R29 oracle mentions lcov parse:", "parseLcov" in ora, "| 'lcov' occurrences:", ora.count("lcov"))
print("R30 command SECRET_HINTS:", re.search(r"SECRET_HINTS = (\(.*?\))", (SRC/"src"/"benchreceipt"/"command.py").read_text()).group(1))
print("R30 privacy_scan SECRET_KEY_RE covers passwd/pwd/auth-token/private-key:",
      all(s in (SRC/"scripts"/"privacy_scan.py").read_text() for s in ["passwd","pwd","auth","private"]))
print("R31 _flag_name defined, uses:", (SRC/"src"/"benchreceipt"/"command.py").read_text().count("_flag_name"),
      "| junit_file_ok uses in verify.py:", (SRC/"src"/"benchreceipt"/"verify.py").read_text().count("junit_file_ok"))
print("R31 __init__ docstring stale:", "NOT_VERIFIED" in (SRC/"src"/"benchreceipt"/"__init__.py").read_text())
print("R27 s0_gate invokes offline_check.py:", "offline_check" in (SRC/"scripts"/"s0_gate.py").read_text(),
      "| performance_smoke network_requests literal:", re.search(r'"network_requests": (\d+)', (SRC/"scripts"/"performance_smoke.py").read_text()).group(1))
print("R29b oracle parseArgs flags:", re.findall(r'argv\[i\] === "(--[a-z-]+)"', ora))
