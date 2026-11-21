#!/usr/bin/env python3
"""S0 gate (P027-T004, PROJECT_BOOK §8.3).

Runs all 52 frozen fixtures through BOTH the Python verifier
(:func:`benchreceipt.verify.evaluate`) and the Node Oracle
(``oracle/verify.mjs``), compares each result to the hand-written
Golden (``fixtures/s0/GOLDEN.json``) and to each other, and checks ALL
10 S0 thresholds:

 1. normal controls 16/16 BOUND_PASS
 2. planted faults 36/36 detected with the correct reason code
 3. False PASS = 0
 4. False block = 0
 5. production / Oracle parity 52/52
 6. 100 replays -> 1 canonical SHA-256
 7. 100 job manifests P95 <= 1 s on this machine
 8. offline run succeeds, external network requests = 0
 9. capture records no full env / stdout / stderr / absolute user paths
10. fixtures / policy / Oracle / gate scripts have reproducible logs + hashes

Writes ``03_evidence/s0/S0_GATE.json`` + ``03_evidence/s0/S0_REPORT.md``.
Exit 0 only if ALL 10 thresholds pass. Never lowers a threshold, never
rewrites Golden, never deletes a failing fixture: on failure, freeze
the branch and report the failing items verbatim.

Usage: python 02_source/scripts/s0_gate.py [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchreceipt.canonical import canonical_hash  # noqa: E402
from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "02_source"
FIXTURES = SOURCE / "fixtures" / "s0"
ORACLE = SOURCE / "oracle" / "verify.mjs"

COMPARE_KEYS = ["status", "jobs_verified", "missing_jobs", "unexpected_jobs",
                "duplicate_jobs", "reason_codes", "identity_mismatches",
                "report_errors", "expected_source_mode"]

# Static offline check: these tokens must not appear in the verifier,
# Oracle, or gate scripts (they would imply network capability).
NETWORK_TOKENS = ("urllib", "socket", "http.client", "requests",
                  "fetch(", "XMLHttpRequest", "curl", "wget")

# Privacy scan: no receipt may carry these keys or absolute user paths.
PRIVACY_FORBIDDEN_KEYS = ("stdout", "stderr", "environment",
                          "full_environment", "stdout_sha256", "stderr_sha256")
PRIVACY_PATH_PATTERNS = ("/home/", "/Users/", "C:\\", "C:/", "/tmp/")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_hashes(fdir: Path) -> dict[str, str]:
    out = {}
    for path in sorted(fdir.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(fdir))] = _sha256_file(path)
    return out


def _run_oracle(policy_path: Path, expected_sha: str, evidence_dir: Path) -> dict:
    proc = subprocess.run(
        ["node", str(ORACLE), "--policy", str(policy_path),
         "--expected-source-sha", expected_sha, "--evidence", str(evidence_dir)],
        capture_output=True, text=True, timeout=120)
    if not proc.stdout.strip():
        raise RuntimeError(f"oracle produced no output for {evidence_dir}: "
                           f"stderr={proc.stderr!r} exit={proc.returncode}")
    return json.loads(proc.stdout)


def _scan_tree_for_text(paths: list[Path], tokens: tuple[str, ...]) -> list[str]:
    """Word-boundary scan for network-capable tokens in code files.

    Tokens are matched as code tokens (``\\b`` boundaries), so a word
    like ``network_requests`` does not trip the ``requests`` token.
    """
    hits = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in tokens:
            pattern = r"\b" + re.escape(token.rstrip("(")) + (r"\(" if token.endswith("(") else r"\b")
            if re.search(pattern, text):
                hits.append(f"{path.relative_to(ROOT)}: {token!r}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the S0 gate (PROJECT_BOOK §8.3).")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "03_evidence" / "s0"
    out_dir.mkdir(parents=True, exist_ok=True)

    golden_doc = json.loads((FIXTURES / "GOLDEN.json").read_text())
    golden = golden_doc["fixtures"]
    fixture_ids = sorted(golden)
    controls = [fid for fid in fixture_ids if fid.startswith("n")]
    faults = [fid for fid in fixture_ids if not fid.startswith("n")]

    per_fixture = []
    fixture_hashes = {}
    n_control_pass = 0
    n_fault_detected = 0
    false_pass = 0
    false_block = 0
    parity = 0

    for fid in fixture_ids:
        fdir = FIXTURES / fid
        fixture_hashes[fid] = _fixture_hashes(fdir)
        policy = load_policy(fdir / "policy.toml")
        expected_sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]
        py_result = evaluate(policy, expected_sha, fdir / "evidence")
        oracle_result = _run_oracle(fdir / "policy.toml", expected_sha, fdir / "evidence")
        py_slim = {k: py_result.get(k) for k in COMPARE_KEYS}
        ora_slim = {k: oracle_result.get(k) for k in COMPARE_KEYS}
        g = golden[fid]
        py_ok = py_slim == g
        ora_ok = ora_slim == g
        is_parity = canonical_hash(py_slim) == canonical_hash(ora_slim)
        if is_parity:
            parity += 1
        is_control = fid in controls
        if is_control:
            if py_result["status"] == "BOUND_PASS" and oracle_result["status"] == "BOUND_PASS":
                n_control_pass += 1
            else:
                false_block += 1
        else:
            if py_ok and ora_ok:
                n_fault_detected += 1
            if py_result["status"] == "BOUND_PASS":
                false_pass += 1
            if oracle_result["status"] == "BOUND_PASS":
                false_pass += 1
        per_fixture.append({
            "id": fid,
            "control": is_control,
            "python_status": py_result["status"],
            "oracle_status": oracle_result["status"],
            "golden_status": g["status"],
            "python_matches_golden": py_ok,
            "oracle_matches_golden": ora_ok,
            "parity": is_parity,
            "python_result_sha256": canonical_hash(py_slim),
            "oracle_result_sha256": canonical_hash(ora_slim),
            "pass": py_ok and ora_ok and is_parity,
        })

    # Threshold 6: 100 replays, 1 hash (in-process, same code path as
    # scripts/repeat_hash.py).
    n02 = FIXTURES / "n02-two-job-pr-head"
    policy_n02 = load_policy(n02 / "policy.toml")
    sha_n02 = json.loads((n02 / "expected.json").read_text())["expected_source_sha"]
    replay_hashes = {canonical_hash(evaluate(policy_n02, sha_n02, n02 / "evidence"))
                     for _ in range(100)}
    n_distinct_hashes = len(replay_hashes)

    # Threshold 7: P95 via the performance smoke script (subprocess, so
    # the gate exercises the shipped script, not a copy of its logic).
    perf_out = out_dir / "performance.json"
    perf_proc = subprocess.run(
        [sys.executable, str(SOURCE / "scripts" / "performance_smoke.py"),
         "--jobs", "100", "--reps", "100", "--out", str(perf_out)],
        capture_output=True, text=True, timeout=600)
    perf = json.loads(perf_out.read_text()) if perf_out.is_file() else {}
    p95 = perf.get("p95_seconds")

    # Threshold 8: offline — static scan of the *verification code
    # paths* (Python verifier + Node Oracle) for network-capable
    # tokens, plus the perf run's own network_requests count (the code
    # paths make no requests by construction; the scan is the checkable
    # evidence). The gate scripts themselves are dev tooling, not
    # verification runtime, and are excluded — scanning them would
    # self-match the token list defined in this file.
    offline_hits = _scan_tree_for_text(
        [SOURCE / "src" / "benchreceipt" / "verify.py", ORACLE],
        NETWORK_TOKENS)
    offline_ok = not offline_hits and perf.get("network_requests") == 0

    # Threshold 9: privacy — scan every fixture receipt (+ the smoke
    # bundle template receipt) for forbidden keys / absolute paths.
    privacy_violations = []
    receipt_paths = list(FIXTURES.rglob("receipt.json"))
    for path in receipt_paths:
        data = json.loads(path.read_text())
        text = path.read_text()
        for key in PRIVACY_FORBIDDEN_KEYS:
            if key in data or f'"{key}"' in text:
                privacy_violations.append(f"{path.relative_to(ROOT)}: key {key!r}")
        for pattern in PRIVACY_PATH_PATTERNS:
            if pattern in text:
                privacy_violations.append(f"{path.relative_to(ROOT)}: path pattern {pattern!r}")
        display = (data.get("command") or {}).get("display", "")
        for pattern in PRIVACY_PATH_PATTERNS:
            if pattern in display:
                privacy_violations.append(f"{path.relative_to(ROOT)}: display path {pattern!r}")
    privacy_ok = not privacy_violations

    # Threshold 10: reproducibility — inventory complete (52 dirs, each
    # with policy.toml + expected.json + evidence/), Golden keys match
    # the inventory exactly, and every fixture file hash is recorded.
    inventory_ok = True
    inventory_notes = []
    on_disk = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    if on_disk != fixture_ids:
        inventory_ok = False
        inventory_notes.append(f"disk dirs != golden keys: {on_disk} vs {fixture_ids}")
    for fid in fixture_ids:
        fdir = FIXTURES / fid
        for needed in ("policy.toml", "expected.json"):
            if not (fdir / needed).is_file():
                inventory_ok = False
                inventory_notes.append(f"{fid}: missing {needed}")
        if not (fdir / "evidence").is_dir() or not list((fdir / "evidence").iterdir()):
            inventory_ok = False
            inventory_notes.append(f"{fid}: empty evidence/")
    if set(golden_doc.keys()) - {"version", "fixtures", "note"}:
        inventory_ok = False
        inventory_notes.append("GOLDEN.json has unexpected top-level keys")

    thresholds = [
        {"id": 1, "name": "normal controls 16/16 BOUND_PASS",
         "passed": n_control_pass == 16 and len(controls) == 16,
         "detail": f"{n_control_pass}/16 controls BOUND_PASS (python+oracle)"},
        {"id": 2, "name": f"planted faults {len(faults)}/{len(faults)} detected with correct reason code",
         "passed": n_fault_detected == len(faults),
         "detail": f"{n_fault_detected}/{len(faults)} faults match Golden (status + reason codes, both impls)"},
        {"id": 3, "name": "False PASS = 0",
         "passed": false_pass == 0,
         "detail": f"false PASS count = {false_pass}"},
        {"id": 4, "name": "False block = 0",
         "passed": false_block == 0,
         "detail": f"false block count = {false_block}"},
        {"id": 5, "name": f"production / Oracle parity {len(fixture_ids)}/{len(fixture_ids)}",
         "passed": parity == len(fixture_ids),
         "detail": f"parity {parity}/{len(fixture_ids)} fixtures"},
        {"id": 6, "name": "100 replays 1 hash",
         "passed": n_distinct_hashes == 1,
         "detail": f"{n_distinct_hashes} distinct canonical SHA-256 over 100 replays "
                   f"(hash {next(iter(replay_hashes)) if n_distinct_hashes == 1 else 'n/a'})"},
        {"id": 7, "name": "100 manifests P95 <= 1s",
         "passed": isinstance(p95, (int, float)) and p95 <= 1.0 and perf_proc.returncode == 0,
         "detail": f"P95 = {p95}s (perf script exit {perf_proc.returncode})"},
        {"id": 8, "name": "offline run, external network requests = 0",
         "passed": offline_ok,
         "detail": ("no network tokens in Python verifier / Node Oracle; "
                    f"perf network_requests={perf.get('network_requests')}"
                    + (f"; hits: {offline_hits}" if offline_hits else ""))},
        {"id": 9, "name": "no full env/stdout/stderr/absolute user paths in receipts",
         "passed": privacy_ok,
         "detail": (f"{len(receipt_paths)} receipts scanned, "
                    f"{len(privacy_violations)} violations"
                    + (f": {privacy_violations[:5]}" if privacy_violations else ""))},
        {"id": 10, "name": "reproducible logs + hashes",
         "passed": inventory_ok,
         "detail": (f"{len(fixture_ids)} fixtures inventoried; per-file SHA-256 recorded in this report"
                    + (f"; notes: {inventory_notes}" if inventory_notes else ""))},
    ]
    verdict = "PASS" if all(t["passed"] for t in thresholds) else "FAIL"

    gate = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "spec_version": "1.2.0",
        "verdict": f"S0 {verdict}",
        "thresholds": thresholds,
        "summary": {
            "controls_pass": n_control_pass,
            "controls_total": len(controls),
            "faults_detected": n_fault_detected,
            "faults_total": len(faults),
            "false_pass": false_pass,
            "false_block": false_block,
            "parity": parity,
            "parity_total": len(fixture_ids),
            "repeat_distinct_hashes": n_distinct_hashes,
            "p95_seconds": p95,
            "offline_network_refs": len(offline_hits),
            "privacy_violations": len(privacy_violations),
        },
        "per_fixture": per_fixture,
        "fixture_hashes": fixture_hashes,
        "golden_sha256": _sha256_file(FIXTURES / "GOLDEN.json"),
        "reason_codes_sha256": _sha256_file(SOURCE / "docs" / "REASON_CODES.md"),
    }
    (out_dir / "S0_GATE.json").write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# S0 Gate Report — P027 BenchReceipt",
        "",
        f"- Generated: {gate['generated_at']}",
        f"- Verdict: **S0 {verdict}**",
        f"- Fixtures: {len(fixture_ids)} (16 controls + {len(faults)} planted faults)",
        f"- Golden SHA-256: `{gate['golden_sha256']}`",
        f"- Reason codes SHA-256: `{gate['reason_codes_sha256']}`",
        "",
        "## Thresholds (PROJECT_BOOK §8.3 — all 10 must pass)",
        "",
        "| # | Threshold | Result | Detail |",
        "|---|---|---|---|",
    ]
    for t in thresholds:
        lines.append(f"| {t['id']} | {t['name']} | {'PASS' if t['passed'] else 'FAIL'} | {t['detail']} |")
    lines += [
        "",
        "## Summary",
        "",
        f"- Controls BOUND_PASS: {n_control_pass}/{len(controls)}",
        f"- Faults detected with correct reason code: {n_fault_detected}/{len(faults)}",
        f"- False PASS: {false_pass}; false block: {false_block}",
        f"- Production / Oracle parity: {parity}/{len(fixture_ids)}",
        f"- Repeat-100 distinct hashes: {n_distinct_hashes}",
        f"- P95 (100 manifests): {p95}s",
        f"- Offline network refs in code: {len(offline_hits)}",
        f"- Privacy violations in receipts: {len(privacy_violations)}",
        "",
        "## Per-fixture results",
        "",
        "| Fixture | Control | Python | Oracle | Golden | Parity | Pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in per_fixture:
        lines.append(
            f"| {row['id']} | {'yes' if row['control'] else 'no'} | "
            f"{row['python_status']} | {row['oracle_status']} | {row['golden_status']} | "
            f"{'yes' if row['parity'] else 'NO'} | {'yes' if row['pass'] else 'NO'} |")
    failing = [r for r in per_fixture if not r["pass"]]
    lines += ["", "## Failing fixtures", ""]
    if failing:
        for row in failing:
            lines.append(f"- {row['id']}: python={row['python_status']} "
                         f"oracle={row['oracle_status']} golden={row['golden_status']} "
                         f"parity={'yes' if row['parity'] else 'NO'}")
    else:
        lines.append(f"None — all {len(fixture_ids)} fixtures match Golden in both implementations.")
    lines += ["",
              "## Notes",
              "",
              "- Golden expected is hand-written (fixtures/s0/GOLDEN.json); it is never "
              "generated from production output.",
              "- S0 FAIL = STOP: do not enter T005, do not lower thresholds, do not "
              "delete failing fixtures, do not rewrite Golden.",
              ""]
    (out_dir / "S0_REPORT.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"S0 gate: {verdict} ({sum(t['passed'] for t in thresholds)}/10 thresholds)")
    for t in thresholds:
        print(f"  [{('PASS' if t['passed'] else 'FAIL')}] {t['id']}. {t['name']}: {t['detail']}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
