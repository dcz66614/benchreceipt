#!/usr/bin/env python3
"""Replay the canonical verification result N times (P027-T004).

Runs :func:`benchreceipt.verify.evaluate` on one frozen fixture
(default ``n02-two-job-pr-head``) ``--runs`` times, canonical-hashes
each result with :func:`benchreceipt.canonical.canonical_hash`, and
reports the number of distinct hashes. PROJECT_BOOK §8.3 threshold 6
requires exactly 1 distinct hash over 100 replays.

Usage:
    python 02_source/scripts/repeat_hash.py [--runs 100]
        [--fixture n02-two-job-pr-head] [--fixtures-dir DIR]
Exit 0 iff the distinct-hash count is 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchreceipt.canonical import canonical_hash  # noqa: E402
from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay verification and count distinct result hashes.")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--fixture", default="n02-two-job-pr-head")
    parser.add_argument("--fixtures-dir", default=None)
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[2]
    fixtures_dir = Path(args.fixtures_dir) if args.fixtures_dir else (
        base / "02_source" / "fixtures" / "s0")
    fdir = fixtures_dir / args.fixture
    policy = load_policy(fdir / "policy.toml")
    expected_sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]

    hashes: list[str] = []
    for _ in range(args.runs):
        result = evaluate(policy, expected_sha, fdir / "evidence")
        hashes.append(canonical_hash(result))
    distinct = sorted(set(hashes))
    report = {
        "fixture": args.fixture,
        "runs": args.runs,
        "distinct_hashes": len(distinct),
        "hash": distinct[0] if len(distinct) == 1 else None,
        "hashes": distinct,
        "verdict": "PASS" if len(distinct) == 1 else "FAIL",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"repeat_hash: {args.runs} replays of {args.fixture}: "
          f"{len(distinct)} distinct SHA-256 -> {report['verdict']}")
    return 0 if len(distinct) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
