#!/usr/bin/env python3
"""FIX-R1 independent review: legacy-shape repro (my own script, fresh).

For S0 fixtures e5-clean-tree-head-change and e6-empty-commit-mid-run:
  - orig: verify the fixture evidence dir as-is via the Python CLI
    (benchreceipt verify, frozen source via PYTHONPATH) and via the
    Node Oracle (oracle/verify.mjs). Expect UNBOUND +
    SOURCE_MUTATED_DURING_RUN, jobs_verified 0, exit 2.
  - legacy: copy the evidence dir to scratch, delete BOTH
    git.head_sha_after / git.tree_sha_after from the receipt (nothing
    else touched), verify the copy is still run.v1 schema-valid, then
    verify with both implementations. Expect UNBOUND + MISSING_FIELD,
    jobs_verified 0, exit 2 (P0-R1-01 closed).
Writes per-run JSON logs under 03_evidence/fix-r1-review/p0-fixture-repro/
and prints one summary JSON line per cell. Read-only w.r.t. production
code, fixtures, Golden: only scratch copies under TMPDIR are modified.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/hatch/workspace/p027-benchreceipt")
OUT = ROOT / "03_evidence" / "fix-r1-review" / "p0-fixture-repro"
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(os.environ["TMPDIR"]) / "p0-fixture-repro"
VENV_PY = ROOT / ".venv" / "bin" / "python"
CASES = ["e5-clean-tree-head-change", "e6-empty-commit-mid-run"]
EXPECTED_SHA = "a" * 40

env = dict(os.environ)
env["PYTHONPATH"] = str(ROOT / "02_source" / "src")


def run_cli(policy, sha, evidence, tag):
    out_json = SCRATCH / f"{tag}.python-result.json"
    p = subprocess.run(
        [str(VENV_PY), "-m", "benchreceipt", "verify",
         "--policy", str(policy), "--expected-source-sha", sha,
         "--evidence", str(evidence), "--out", str(out_json)],
        capture_output=True, text=True, env=env)
    (OUT / f"{tag}.python-cli.log").write_text(
        f"$ benchreceipt verify --policy {policy} --evidence {evidence}\n"
        f"exit={p.returncode}\n--- stdout ---\n{p.stdout}--- stderr ---\n{p.stderr}")
    return p.returncode, json.loads(out_json.read_text())


def run_oracle(policy, sha, evidence, tag):
    p = subprocess.run(
        ["node", str(ROOT / "02_source" / "oracle" / "verify.mjs"),
         "--policy", str(policy), "--expected-source-sha", sha,
         "--evidence", str(evidence)],
        capture_output=True, text=True)
    (OUT / f"{tag}.oracle.log").write_text(
        f"$ node oracle/verify.mjs --policy {policy} --evidence {evidence}\n"
        f"exit={p.returncode}\n--- stdout ---\n{p.stdout}--- stderr ---\n{p.stderr}")
    return p.returncode, json.loads(p.stdout)


def main():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    rows = []
    for case in CASES:
        fdir = ROOT / "02_source" / "fixtures" / "s0" / case
        policy = fdir / "policy.toml"
        for variant in ("orig", "legacy"):
            ev = SCRATCH / case / variant
            shutil.copytree(fdir / "evidence", ev)
            receipt_path = ev / "unit-linux-py312" / "receipt.json"
            data = json.loads(receipt_path.read_text())
            if variant == "legacy":
                removed = {k: data["git"].pop(k, None)
                           for k in ("head_sha_after", "tree_sha_after")}
                (OUT / f"{case}-legacy.removed-fields.json").write_text(
                    json.dumps(removed, indent=2, sort_keys=True) + "\n")
                # legacy shape must still validate against run.v1
                check = subprocess.run(
                    [str(VENV_PY), "-c",
                     "import json,sys; from benchreceipt.schema import validate_against_schema;"
                     " validate_against_schema(json.load(open(sys.argv[1])), 'run'); print('schema-valid')",
                     str(receipt_path)],
                    capture_output=True, text=True, env=env)
                assert check.returncode == 0, check.stderr
                receipt_path.write_text(
                    json.dumps(data, indent=2, sort_keys=True) + "\n")
            tag = f"{case}-{variant}"
            py_exit, py = run_cli(policy, EXPECTED_SHA, ev, tag)
            or_exit, orc = run_oracle(policy, EXPECTED_SHA, ev, tag)
            row = {"case": case, "variant": variant,
                   "python": {"status": py["status"], "reason_codes": py["reason_codes"],
                              "jobs_verified": py["jobs_verified"], "exit": py_exit},
                   "oracle": {"status": orc["status"], "reason_codes": orc["reason_codes"],
                              "jobs_verified": orc["jobs_verified"], "exit": or_exit}}
            rows.append(row)
            print(json.dumps(row, sort_keys=True))
            if variant == "orig":
                assert py["status"] == "UNBOUND" and py["reason_codes"] == ["SOURCE_MUTATED_DURING_RUN"] and py["jobs_verified"] == 0 and py_exit == 2
                assert orc["status"] == "UNBOUND" and orc["reason_codes"] == ["SOURCE_MUTATED_DURING_RUN"] and orc["jobs_verified"] == 0 and or_exit == 2
            else:
                assert py["status"] == "UNBOUND" and py["reason_codes"] == ["MISSING_FIELD"] and py["jobs_verified"] == 0 and py_exit == 2
                assert orc["status"] == "UNBOUND" and orc["reason_codes"] == ["MISSING_FIELD"] and orc["jobs_verified"] == 0 and or_exit == 2
    (OUT / "fixture-legacy.summary.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n")
    print("P0-FIXTURE-REPRO: 4/4 orig UNBOUND+SOURCE_MUTATED_DURING_RUN; "
          "4/4 legacy UNBOUND+MISSING_FIELD (Python CLI + Oracle, exit 2)")


if __name__ == "__main__":
    main()
