#!/usr/bin/env python3
"""UI smoke check (P027-T010, PROJECT_BOOK §9, IMPLEMENTATION_PLAN §5 T010).

Renders static HTML reports from three genuine verification results
(n01 BOUND_PASS, g1 BOUND_FAIL, d1 UNBOUND) produced by the real
verifier on the frozen S0 fixtures, and checks each output is a
non-empty, self-contained HTML file with zero external-resource
references.

Screenshots: a headless render is attempted ONLY if a browser binary
exists on this machine (checked with ``shutil.which``). This VM has
no local browser (see 00_control/ENVIRONMENT.md), so the expected
outcome here is ``screenshots: NOT_TESTED (no browser on this VM)`` —
recorded honestly, never faked. No image files are fabricated.

Usage: python 02_source/scripts/ui_smoke.py [--out-dir DIR]
Exit 0 only if every report renders and every check passes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchreceipt.policy import load_policy  # noqa: E402
from benchreceipt.render.html import render_report  # noqa: E402
from benchreceipt.verify import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "02_source"
FIXTURES = SOURCE / "fixtures" / "s0"

CASES = (
    ("n01-single-pr-head", "report-n01.html", "BOUND_PASS"),
    ("g1-junit-failed", "report-g1.html", "BOUND_FAIL"),
    ("d1-matrix-missing", "report-d1.html", "UNBOUND"),
)

EXTERNAL_TOKENS = (b"http://", b"https://", b"//cdn", b"<link", b"<script src=", b"url(")

BROWSER_BINARIES = ("chromium", "chromium-browser", "google-chrome", "firefox")


def _verify_fixture(fid: str) -> dict:
    fdir = FIXTURES / fid
    sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]
    policy = load_policy(fdir / "policy.toml")
    return evaluate(policy, sha, fdir / "evidence")


def _check_external_refs(data: bytes) -> list[str]:
    return [token.decode() for token in EXTERNAL_TOKENS if token in data]


def main() -> int:
    parser = argparse.ArgumentParser(description="Render + smoke-check T010 HTML reports.")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="output directory for the sample reports (default: 03_evidence/screenshots)",
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "03_evidence" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    print("P027-T010 ui_smoke: rendering 3 fixture reports")
    for fid, filename, expected_status in CASES:
        result = _verify_fixture(fid)
        status = result["status"]
        out_path = out_dir / filename
        render_report(result, out_path)
        data = out_path.read_bytes()
        problems: list[str] = []
        if status != expected_status:
            problems.append(f"status {status} != expected {expected_status}")
        if not data:
            problems.append("output is empty")
        if b"<!DOCTYPE html>" not in data:
            problems.append("missing doctype")
        if status.encode() not in data:
            problems.append(f"status text {status} missing from HTML")
        bad_tokens = _check_external_refs(data)
        if bad_tokens:
            problems.append(f"external-resource tokens found: {bad_tokens}")
        if b"@media (max-width: 400px)" not in data:
            problems.append("narrow-screen CSS missing")
        if problems:
            failures.append(f"{filename}: " + "; ".join(problems))
            print(f"  FAIL {filename}: {'; '.join(problems)}")
        else:
            print(
                f"  ok {filename}: status={status} size={len(data)} bytes "
                f"external_refs=0"
            )

    found = [name for name in BROWSER_BINARIES if shutil.which(name)]
    if found:
        print(f"screenshots: browser binary found ({', '.join(found)}) — "
              "headless screenshot capture is NOT implemented by this "
              "script; screenshots remain NOT_TESTED by ui_smoke.py")
        print("screenshots: NOT_TESTED (no headless capture in ui_smoke.py)")
    else:
        print("screenshots: NOT_TESTED (no browser on this VM)")

    if failures:
        print(f"ui_smoke: FAIL ({len(failures)} problem(s))")
        return 1
    print("ui_smoke: PASS (3 reports rendered, 0 external refs, "
          "screenshots NOT_TESTED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
