"""P027 FIX-R1 POST-FIX repro: fixture-deletion variant, fixed working tree.

For e5-clean-tree-head-change and e6-empty-commit-mid-run:
  - control: verify the original evidence dir as-is (expect UNBOUND).
  - legacy: copy evidence, delete git.head_sha_after + git.tree_sha_after
    from receipt.json (all other fields untouched), verify again.
Runs BOTH the Python verify CLI (frozen src via PYTHONPATH, repo .venv)
and the Node Oracle (frozen oracle/verify.mjs), records status /
reason_codes / jobs_verified / exit code for each.
Writes per-run JSON logs under 03_evidence/fix-r1-repro/ and prints a
one-line summary per run. No production code is modified.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
FROZEN = ROOT / ".tmp" / "fix-r1-tmp" / "fixed-tree"   # FIX-R1 working tree (fixed code)
SCRATCH = ROOT / ".tmp" / "fix-r1-tmp" / "post-fix-repro"
EVID = ROOT / "03_evidence" / "fix-r1" / "post-fix-fixture-repro"
VENV_PY = ROOT / ".venv" / "bin" / "python"
EXPECTED_SHA = "a" * 40
CASES = ["e5-clean-tree-head-change", "e6-empty-commit-mid-run"]

env = dict(os.environ)
env["PYTHONPATH"] = str(FROZEN / "src")


def run(cmd, logname):
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (EVID / logname).write_text(
        "$ " + " ".join(str(c) for c in cmd) + "\n"
        f"exit={p.returncode}\n--- stdout ---\n{p.stdout}--- stderr ---\n{p.stderr}"
    )
    return p


def parse_result(stdout, out_json):
    """Result JSON: Python CLI writes --out file; Oracle prints to stdout."""
    if out_json is not None:
        return json.loads(Path(out_json).read_text())
    return json.loads(stdout)


def main():
    summary = []
    for case in CASES:
        fixture = FROZEN / "fixtures" / "s0" / case
        policy = fixture / "policy.toml"
        for variant in ("orig", "legacy"):
            ev_dir = SCRATCH / f"{case}-{variant}" / "evidence"
            if ev_dir.exists():
                shutil.rmtree(ev_dir.parent)
            shutil.copytree(fixture / "evidence", ev_dir)
            if variant == "legacy":
                receipt = ev_dir / "unit-linux-py312" / "receipt.json"
                data = json.loads(receipt.read_text())
                removed = {k: data["git"].pop(k) for k in
                           ("head_sha_after", "tree_sha_after")}
                assert "head_sha_after" not in data["git"]
                assert "tree_sha_after" not in data["git"]
                receipt.write_text(json.dumps(data, sort_keys=True) + "\n")
                (EVID / f"{case}-legacy.removed-fields.json").write_text(
                    json.dumps(removed, indent=1, sort_keys=True) + "\n")
            # --- Python CLI ---
            out_json = EVID / f"{case}-{variant}.python-result.json"
            p = run([str(VENV_PY), "-m", "benchreceipt", "verify",
                     "--policy", str(policy),
                     "--evidence", str(ev_dir),
                     "--expected-source-sha", EXPECTED_SHA,
                     "--out", str(out_json)],
                    f"{case}-{variant}.python-cli.log")
            res = parse_result(p.stdout, out_json)
            summary.append({"case": case, "variant": variant, "impl": "python-cli",
                            "status": res["status"],
                            "reason_codes": res["reason_codes"],
                            "jobs_verified": res["jobs_verified"],
                            "exit": p.returncode})
            # --- Node Oracle ---
            p = run(["node", str(FROZEN / "oracle" / "verify.mjs"),
                     "--policy", str(policy),
                     "--expected-source-sha", EXPECTED_SHA,
                     "--evidence", str(ev_dir)],
                    f"{case}-{variant}.oracle.log")
            res = parse_result(p.stdout, None)
            summary.append({"case": case, "variant": variant, "impl": "oracle",
                            "status": res["status"],
                            "reason_codes": res["reason_codes"],
                            "jobs_verified": res["jobs_verified"],
                            "exit": p.returncode})
    (EVID / "fixture-legacy.summary.json").write_text(
        json.dumps(summary, indent=1) + "\n")
    for row in summary:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
