#!/usr/bin/env python3
"""Performance smoke: verify N job manifests, report P95 (P027-T004).

Builds a synthetic evidence bundle with ``--jobs`` jobs (copies of the
frozen ``n02`` control receipt with distinct job ids, plus a matching
policy), runs :func:`benchreceipt.verify.evaluate` ``--reps`` times,
and reports the P95 wall time of one full-bundle verification.
PROJECT_BOOK §8.3 threshold 7 requires P95 <= 1 s on this machine.

Hardware is recorded from the live machine (platform, CPU count,
Python version, RAM) alongside the timings so the number is anchored
to an environment, not floating. The bundle is built under TMPDIR (or
``--workdir``); nothing here touches the network.

Usage:
    python 02_source/scripts/performance_smoke.py [--jobs 100] [--reps 100]
        [--out 03_evidence/s0/performance.json]
Exit 0 iff P95 <= 1 s.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

P95_LIMIT_SECONDS = 1.0


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    # Nearest-rank P95.
    index = max(0, int(-(-95 * len(ordered) // 100)) - 1)
    return ordered[index]


def _hardware() -> dict:
    mem_total_kib = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_total_kib = int(line.split()[1])
                break
    except OSError:
        pass
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "mem_total_kib": mem_total_kib,
        "source": "00_control/ENVIRONMENT.md (T001: Ubuntu 24.04.5, 4 vCPU, "
                  "7.7 GiB RAM, Python 3.12.3, Node v24.22.1)",
    }


def build_bundle(workdir: Path, n_jobs: int) -> tuple[Path, dict, str]:
    """Build a synthetic N-job bundle; return (evidence_dir, policy, sha)."""
    base = Path(__file__).resolve().parents[2]
    template_dir = base / "02_source" / "fixtures" / "s0" / "n02-two-job-pr-head"
    template = json.loads(
        (template_dir / "evidence" / "unit-linux-py312" / "receipt.json").read_text())
    expected_sha = json.loads((template_dir / "expected.json").read_text())["expected_source_sha"]
    if workdir.exists():
        shutil.rmtree(workdir)
    evidence_dir = workdir / "evidence"
    evidence_dir.mkdir(parents=True)
    job_ids = [f"perf-job-{i:03d}" for i in range(n_jobs)]
    for job_id in job_ids:
        receipt = json.loads(json.dumps(template))
        receipt["job_id"] = job_id
        receipt["matrix"] = {"os": "ubuntu-latest", "python": "3.12"}
        job_dir = evidence_dir / job_id
        (job_dir / "artifacts").mkdir(parents=True)
        (job_dir / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        junit_src = template_dir / "evidence" / "unit-linux-py312" / "artifacts" / "junit.xml"
        shutil.copyfile(junit_src, job_dir / "artifacts" / "junit.xml")
    policy_text = (
        "schema_version = 1\n"
        'source_mode = "pr_head"\n'
        'expected_workflow = "CI"\n'
        "required_jobs = [\n"
        + ",\n".join(f'  "{j}"' for j in job_ids)
        + "\n]\n"
        "min_tests = 1\n"
        "require_clean_source_after = true\n"
        "same_tree_across_jobs = true\n"
        "same_run_id = true\n"
        "same_run_attempt = true\n"
        "\n[reports]\n"
        'junit = "required"\n'
        'lcov = "optional"\n'
        "\n[security]\n"
        "store_stdout = false\n"
        "store_stderr = false\n"
        "store_full_environment = false\n"
    )
    policy_path = workdir / "policy.toml"
    policy_path.write_text(policy_text, encoding="utf-8")
    policy = load_policy(policy_path)
    return evidence_dir, policy, expected_sha


def main() -> int:
    parser = argparse.ArgumentParser(description="P95 verification performance smoke.")
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--reps", type=int, default=100)
    parser.add_argument("--out", default=None)
    parser.add_argument("--workdir", default=None)
    args = parser.parse_args()

    tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))
    workdir = Path(args.workdir) if args.workdir else tmpdir / "benchreceipt-perf-smoke"
    evidence_dir, policy, expected_sha = build_bundle(workdir, args.jobs)

    samples: list[float] = []
    last_status = None
    for _ in range(args.reps):
        start = time.perf_counter()
        result = evaluate(policy, expected_sha, evidence_dir)
        samples.append(time.perf_counter() - start)
        last_status = result["status"]
    assert last_status == "BOUND_PASS", f"perf bundle must PASS, got {last_status}"
    p95 = _p95(samples)
    report = {
        "jobs": args.jobs,
        "reps": args.reps,
        "status": last_status,
        "p50_seconds": statistics.median(samples),
        "p95_seconds": p95,
        "max_seconds": max(samples),
        "mean_seconds": sum(samples) / len(samples),
        "limit_seconds": P95_LIMIT_SECONDS,
        "verdict": "PASS" if p95 <= P95_LIMIT_SECONDS else "FAIL",
        "hardware": _hardware(),
        "network_requests": 0,
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"performance_smoke: {args.jobs} jobs x {args.reps} reps: "
          f"P95={p95:.4f}s (limit {P95_LIMIT_SECONDS}s) -> {report['verdict']}")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0 if p95 <= P95_LIMIT_SECONDS else 1


if __name__ == "__main__":
    raise SystemExit(main())
