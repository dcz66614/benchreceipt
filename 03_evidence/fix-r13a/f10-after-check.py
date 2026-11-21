"""FIX-R13a F-10 smoke check: explicit_sha capture path (mirrors repro5 R11,
but with the new --source-mode explicit_sha --expected-sha flags)."""
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
sys.path.insert(0, str(ROOT / "02_source" / "src"))
from benchreceipt.capture import capture as do_capture, CaptureError, determine_source_mode
from benchreceipt.ci_metadata import collect_ci_metadata
from benchreceipt.policy import load_policy
from benchreceipt.verify import evaluate

# --- determine_source_mode unit behaviour ---
ci = collect_ci_metadata({})
head = "a" * 40
print("explicit pin:", determine_source_mode(ci, head, "b" * 40))
for bad in ["NOT-A-SHA", "A" * 40, "b" * 39, "b" * 40 + "\n", "", 123]:
    try:
        determine_source_mode(ci, head, bad)
        print("BAD SHA ACCEPTED (bug):", repr(bad))
    except ValueError as e:
        print("malformed pin rejected:", repr(bad)[:20], "->", e)
print("no pin (unchanged):", determine_source_mode(ci, head))

# --- real capture with the pin ---
tmp = Path(tempfile.mkdtemp(prefix="fix-r13a-f10-", dir="/tmp"))
repo = tmp / "repo"
repo.mkdir()

def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)

run(["git", "init", "-q", "-b", "main"], repo)
run(["git", "config", "user.email", "f10@example.invalid"], repo)
run(["git", "config", "user.name", "f10"], repo)
(repo / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
(repo / ".gitignore").write_text(".benchreceipt/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
run(["git", "add", "."], repo)
run(["git", "commit", "-qm", "x"], repo)
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

res = do_capture(
    job_id="unit-linux-py312", matrix={"os": "ubuntu-latest", "python": "3.12"},
    argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
          "--junitxml=.benchreceipt/out/junit.xml", "test_x.py"],
    junit_path=".benchreceipt/out/junit.xml", repo_path=repo, cwd=repo,
    source_mode="explicit_sha", expected_sha=head,
)
print("pinned capture source_mode =", res.receipt["git"]["source_mode"],
      "expected_source_sha =", res.receipt["git"]["expected_source_sha"][:12] + "...",
      "head_sha =", res.receipt["git"]["head_sha"][:12] + "...")

pol_text = ('schema_version = 1\nsource_mode = "explicit_sha"\nexpected_workflow = "local"\n'
            'required_jobs = [ "unit-linux-py312" ]\nmin_tests = 1\nrequire_clean_source_after = true\n'
            "same_tree_across_jobs = true\nsame_run_id = false\nsame_run_attempt = false\n\n[reports]\n"
            'junit = "required"\nlcov = "optional"\n\n[security]\nstore_stdout = false\nstore_stderr = false\nstore_full_environment = false\n')
(tmp / "policy.toml").write_text(pol_text, encoding="utf-8")
pol = load_policy(tmp / "policy.toml")
v = evaluate(pol, head, repo / ".benchreceipt" / "evidence")
print("verify pinned receipt vs explicit_sha policy ->", v["status"], sorted(v["reason_codes"]), "jobs =", v["jobs_verified"])

# --- fail-closed: pin differs from HEAD -> receipt is honest, verify fails ---
# NOTE: the policy file lives OUTSIDE the repo here (tmp/policy.toml) so the
# repo stays clean; in the first draft it was written inside the repo, which
# correctly flagged SOURCE_MUTATED_DURING_RUN via require_clean_after instead.
other = "c" * 40
pol2 = pol
res2 = do_capture(
    job_id="unit-linux-py312", matrix={"os": "ubuntu-latest", "python": "3.12"},
    argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
          "--junitxml=.benchreceipt/out/junit.xml", "test_x.py"],
    junit_path=".benchreceipt/out/junit.xml", repo_path=repo, cwd=repo,
    source_mode="explicit_sha", expected_sha=other,
)
print("wrong-pin capture: mode =", res2.receipt["git"]["source_mode"],
      "head_sha =", res2.receipt["git"]["head_sha"][:12] + "...",
      "expected =", res2.receipt["git"]["expected_source_sha"][:12] + "...")
v2 = evaluate(pol2, other, repo / ".benchreceipt" / "evidence")
print("verify wrong-pin receipt vs explicit_sha policy (expected=pinned c*40) ->", v2["status"], sorted(v2["reason_codes"]))
v2b = evaluate(pol2, head, repo / ".benchreceipt" / "evidence")
print("verify wrong-pin receipt vs explicit_sha policy (expected=real head) ->", v2b["status"], sorted(v2b["reason_codes"]),
      "(correct: tests did run on head; the pin only records intent)")

# --- fail-closed: malformed / incomplete pins ---
for kwargs in [
    {"source_mode": "explicit_sha", "expected_sha": "NOT-A-SHA"},
    {"source_mode": "explicit_sha"},
    {"expected_sha": head},
    {"source_mode": "pr_head", "expected_sha": head},
]:
    try:
        do_capture(job_id="unit-linux-py312", matrix={"os": "ubuntu-latest"},
                   argv=[sys.executable, "-c", "pass"], repo_path=repo, cwd=repo, **kwargs)
        print("PIN ACCEPTED (bug):", kwargs)
    except CaptureError as e:
        print("pin rejected:", kwargs, "->", e)
