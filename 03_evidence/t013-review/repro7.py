import json, shutil, subprocess, sys
from pathlib import Path
ROOT = Path("/home/hatch/workspace/p027-benchreceipt"); SRC = ROOT/"02_source"
sys.path.insert(0, str(SRC/"src"))
FIX = SRC/"fixtures"/"s0"/"n02-two-job-pr-head"
WORK = Path("/tmp/t013-repro/work7"); shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
from benchreceipt.policy import load_policy
from benchreceipt.verify import evaluate
def base_evidence(dst, jobs=("unit-linux-py312",)):
    shutil.copytree(FIX/"evidence", dst)
    for d in list(dst.iterdir()):
        if d.name not in jobs: shutil.rmtree(d)
    policy = load_policy(FIX/"policy.toml"); policy["required_jobs"]=list(jobs)
    sha = json.loads((FIX/"expected.json").read_text())["expected_source_sha"]
    return policy, sha
print("== P2-O symlinked receipt.json read through by verify ==")
ev = WORK/"r-o"; pol, sha = base_evidence(ev)
jd = ev/"unit-linux-py312"
real = WORK/"real-receipt.json"
shutil.copy(jd/"receipt.json", real)
(jd/"receipt.json").unlink(); (jd/"receipt.json").symlink_to(real)
v = evaluate(pol, sha, ev)
print("P2-O symlinked receipt.json ->", v["status"], sorted(v["reason_codes"]))
print("== P2-S whitespace --expected-run-id accepted as pin ==")
ev = WORK/"r-s"; pol, sha = base_evidence(ev)
v = evaluate(pol, sha, ev, expected_run_id=" ", expected_attempt=2)
print("P2-S expected_run_id=' ' ->", v["status"], sorted(v["reason_codes"]),
      "(accepted as a pin; every job mismatches -> UNBOUND, fail-closed)")
