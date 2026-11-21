"""T013 independent-review repro harness (reviewer-written, NOT part of product).

Runs each suspicious point as a minimal reproduction against the frozen
candidate code at cfede27 (working tree on branch t013-review is
byte-identical in 02_source/src). Uses the project .venv python.
Prints one line per repro: REPRO-ID, verdict, evidence.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
SRC = ROOT / "02_source"
sys.path.insert(0, str(SRC / "src"))
FIX = SRC / "fixtures" / "s0" / "n02-two-job-pr-head"
WORK = Path("/tmp/t013-repro/work")
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)

from benchreceipt.command import display_command, redact_argv  # noqa: E402
from benchreceipt.policy import load_policy, validate_policy, PolicyInvalid  # noqa: E402
from benchreceipt.schema import validate_against_schema, SchemaValidationError  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

HEAD = "a" * 40
TREE = "d" * 40

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
    """Copy n02 evidence (1 job by default) into dst; return (policy_dict, sha)."""
    shutil.copytree(FIX / "evidence", dst)
    for d in list(dst.iterdir()):
        if d.name not in jobs:
            shutil.rmtree(d)
    policy = load_policy(FIX / "policy.toml")
    policy["required_jobs"] = list(jobs)
    sha = json.loads((FIX / "expected.json").read_text())["expected_source_sha"]
    return policy, sha

def run_oracle(policy_path, sha, evidence):
    p = subprocess.run(["node", str(SRC / "oracle" / "verify.mjs"), "--policy", str(policy_path),
                        "--expected-source-sha", sha, "--evidence", str(evidence)],
                       capture_output=True, text=True, timeout=60)
    try:
        res = json.loads(p.stdout)
    except Exception:
        res = {"_stdout": p.stdout, "_stderr": p.stderr}
    return p.returncode, res

def write_policy(dst, text):
    pp = Path(dst) / "policy.toml"
    pp.write_text(text, encoding="utf-8")
    return pp

def n02_policy_text(**over):
    base = (FIX / "policy.toml").read_text()
    for k, v in over.items():
        base = base.replace(f"{k} = ", f"{k} = {v}  # REPLACED-ORIGINAL\n{ k} = ", 1) if False else base
    return base

print("== R1 redaction / path shortening ==")
for argv in [
    ["pytest", "--key", "hunter2-secret"],
    ["pytest", "--auth", "Bearer-abc123"],
    ["pytest", "--passwd", "hunter2"],
    ["pytest", "--passphrase", "hunter2"],
    ["pytest", "--private-key", "/home/sam/id.pem"],
    ["curl", "https://user:s3cret@example.com/x"],
    ["pytest", r"\\server\share\secret.txt"],
    ["pytest", "file:///home/sam/secret.txt"],
    ["pytest", "--config", "/home/sam/.config/x"],
    ["pytest", "--token", "abc123"],
    ["pytest", "--api-key=hunter2"],
]:
    print("R1", argv[1:], "->", repr(display_command(argv)))

print("== R8 schema pattern trailing newline ==")
r = json.loads((FIX / "evidence" / "unit-linux-py312" / "receipt.json").read_text())
r["git"]["head_sha"] = "a" * 40 + "\n"
try:
    validate_against_schema(r, "run")
    print("R8 head_sha 40hex+newline: SCHEMA-ACCEPTS (pattern $ matches before \\n)")
except SchemaValidationError as e:
    print("R8 head_sha 40hex+newline: schema rejects:", e.errors[:1])
r2 = json.loads((FIX / "evidence" / "unit-linux-py312" / "receipt.json").read_text())
r2["reports"][0]["path"] = "artifacts/junit.xml\n"
try:
    validate_against_schema(r2, "run")
    print("R8 report path +newline: SCHEMA-ACCEPTS")
except SchemaValidationError as e:
    print("R8 report path +newline: schema rejects:", e.errors[:1])

print("== R19 policy schema_version=true ==")
try:
    p = validate_policy({"schema_version": True, "source_mode": "pr_head",
        "expected_workflow": "CI", "required_jobs": ["unit-linux-py312"], "min_tests": 1,
        "require_clean_source_after": True, "same_tree_across_jobs": True,
        "same_run_id": True, "same_run_attempt": True,
        "reports": {"junit": "required", "lcov": "optional"}})
    print("R19 schema_version=true: ACCEPTED by validate_policy (True==1 const)")
except PolicyInvalid as e:
    print("R19 schema_version=true: rejected:", e)

print("== R25 invalid expected_source_sha label ==")
ev = WORK / "r25"; pol, _ = base_evidence(ev)
res = evaluate(pol, "NOT-A-SHA", ev)
print("R25 bad expected sha ->", res["status"], res["reason_codes"], res["report_errors"])

print("== R15 determine_source_mode ==")
from benchreceipt.ci_metadata import CIMetadata  # noqa: E402
from benchreceipt.capture import determine_source_mode  # noqa: E402
cases = [
    ("pr, HEAD==head", CIMetadata(event_name="pull_request", head_sha=HEAD, github_sha="b"*40), HEAD),
    ("pr, HEAD==merge", CIMetadata(event_name="pull_request", head_sha=HEAD, github_sha="b"*40), "b"*40),
    ("pr, HEAD==neither", CIMetadata(event_name="pull_request", head_sha=HEAD, github_sha="b"*40), "c"*40),
    ("pr, no github_sha", CIMetadata(event_name="pull_request", head_sha=HEAD, github_sha=None), "c"*40),
    ("push + github_sha", CIMetadata(event_name="push", github_sha="b"*40), HEAD),
    ("local", CIMetadata(), HEAD),
]
for name, ci, head in cases:
    print("R15", name, "->", determine_source_mode(ci, head))
