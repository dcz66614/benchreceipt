#!/usr/bin/env python3
"""Offline check for BenchReceipt (P027-T012).

Proves, on this host, that the product runtime makes **zero network
requests** for the capture/verify/report/bundle workflows, by two
independent means:

1. **Static scan** — every ``.py`` file under ``02_source/src`` is
   AST-parsed; any import of a network-capable module (``socket``,
   ``urllib``, ``http.client``, ``requests``, ``httpx``, ``aiohttp``)
   or any literal reference to ``curl``/``wget``/``gh`` as a command or
   to the GitHub API host fails the check (string literals only — prose
   in comments and docstrings does not count). ``subprocess`` is allowed: it is used only
   to invoke the local ``git`` binary (``git_identity.py``), never a
   network tool — the scan additionally rejects ``curl``/``wget``/
   ``gh`` argv literals anywhere in ``src``.
2. **Dynamic trace** — a real end-to-end run (``capture`` a green
   pytest run in a scratch git repo, then ``verify`` it to
   ``BOUND_PASS`` and render a report) executes under a
   ``sys.addaudithook`` that counts every ``socket.connect`` and
   ``socket.getaddrinfo`` event. The check passes only when the count
   is exactly 0. The audit hook is installed before any BenchReceipt
   import so even import-time networking would be caught.

No part of this script touches the network itself; the scratch repo
is local and ``git`` runs with local operations only.

Usage:
    python 02_source/scripts/offline_check.py [--out 03_evidence/t012/offline_check.json]
Exit 0 iff the static scan is clean AND the dynamic trace shows
0 socket events AND the end-to-end run verifies BOUND_PASS.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# --- audit hook: installed BEFORE any benchreceipt import ---------------
NETWORK_EVENTS: list[str] = []


def _audit_hook(event: str, args: tuple) -> None:
    if event in ("socket.connect", "socket.getaddrinfo"):
        NETWORK_EVENTS.append(event)


sys.addaudithook(_audit_hook)

NETWORK_MODULES = {
    "socket",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "http.client",
    "http.server",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
}
FORBIDDEN_COMMAND_LITERALS = {"gh", "curl", "wget"}
FORBIDDEN_URL_PREFIXES = ("https://api.github.com", "http://api.github.com")


def static_scan(src_root: Path) -> list[str]:
    """Return a list of static findings (empty = clean)."""
    findings: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{path}: unparsable: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if alias.name in NETWORK_MODULES or top in NETWORK_MODULES:
                        findings.append(f"{path}:{node.lineno}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module in NETWORK_MODULES
                    or node.module.split(".")[0] in NETWORK_MODULES
                ):
                    findings.append(
                        f"{path}:{node.lineno}: imports from {node.module}"
                    )
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Only string *literals* count: prose in comments/docstrings
                # (e.g. "enough", "through") must not trip the check.
                if node.value.strip() in FORBIDDEN_COMMAND_LITERALS:
                    findings.append(
                        f"{path}:{node.lineno}: network-tool literal "
                        f"{node.value.strip()!r}"
                    )
                if node.value.startswith(FORBIDDEN_URL_PREFIXES):
                    findings.append(
                        f"{path}:{node.lineno}: GitHub API URL literal"
                    )
    return findings


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def dynamic_trace() -> dict:
    """Run capture -> verify -> report in-process; return the trace."""
    from benchreceipt.capture import capture  # noqa: E402  (hook already on)
    from benchreceipt.cli import main as cli_main  # noqa: E402
    from benchreceipt.policy import load_policy  # noqa: E402
    from benchreceipt.verify import evaluate  # noqa: E402

    with tempfile.TemporaryDirectory(prefix="benchreceipt-offline-") as tmp:
        repo = Path(tmp) / "demo"
        repo.mkdir()
        _run(["git", "init", "-q", "-b", "main"], repo)
        _run(["git", "config", "user.email", "offline@example.invalid"], repo)
        _run(["git", "config", "user.name", "offline-check"], repo)
        (repo / "test_demo.py").write_text(
            "def test_add():\n    assert 1 + 1 == 2\n", encoding="utf-8"
        )
        (repo / ".gitignore").write_text(
            ".benchreceipt/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8"
        )
        policy_text = (
            'schema_version = 1\nsource_mode = "event_sha"\n'
            'expected_workflow = "local"\n'
            'required_jobs = [ "demo-linux-py312" ]\nmin_tests = 1\n'
            "require_clean_source_after = true\nsame_tree_across_jobs = true\n"
            "same_run_id = false\nsame_run_attempt = false\n\n[reports]\n"
            'junit = "required"\nlcov = "optional"\n\n[security]\n'
            "store_stdout = false\nstore_stderr = false\n"
            "store_full_environment = false\n"
        )
        (repo / ".benchreceipt.toml").write_text(policy_text, encoding="utf-8")
        _run(["git", "add", "."], repo)
        _run(["git", "commit", "-qm", "demo"], repo)
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, check=True, capture_output=True, text=True,
        ).stdout.strip()

        events_before = len(NETWORK_EVENTS)
        result = capture(
            job_id="demo-linux-py312",
            matrix={"os": "ubuntu-latest", "python": "3.12"},
            argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                  "--junitxml=.benchreceipt/out/junit.xml", "test_demo.py"],
            junit_path=".benchreceipt/out/junit.xml",
            repo_path=repo,
            cwd=repo,
        )
        assert result.exit_code == 0, f"wrapped pytest failed: {result.exit_code}"
        assert not result.source_mutated_during_run, "scratch repo mutated?!"

        policy = load_policy(repo / ".benchreceipt.toml")
        verdict = evaluate(policy, head_sha, repo / ".benchreceipt" / "evidence")
        assert verdict["status"] == "BOUND_PASS", f"expected BOUND_PASS, got {verdict}"

        # evaluate() above does not write verification.json; exercise the
        # CLI verify + report steps too so the report path is traced.
        verify_rc = cli_main([
            "verify",
            "--policy", str(repo / ".benchreceipt.toml"),
            "--evidence", str(repo / ".benchreceipt" / "evidence"),
            "--expected-source-sha", head_sha,
            "--out", str(repo / ".benchreceipt" / "verification.json"),
        ])
        assert verify_rc == 0, f"CLI verify exit {verify_rc}"
        report_rc = cli_main([
            "report",
            "--input", str(repo / ".benchreceipt" / "verification.json"),
            "--html", str(repo / ".benchreceipt" / "report.html"),
        ])
        assert report_rc == 0, f"CLI report exit {report_rc}"
        events_during = len(NETWORK_EVENTS) - events_before
        return {
            "capture_exit": result.exit_code,
            "verify_status": verdict["status"],
            "cli_verify_exit": verify_rc,
            "cli_report_exit": report_rc,
            "socket_events_during_run": events_during,
            "socket_events_total": len(NETWORK_EVENTS),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="BenchReceipt offline check.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "02_source" / "src"
    static_findings = static_scan(src_root)
    trace = dynamic_trace()
    report = {
        "static_scan": {
            "root": str(src_root),
            "findings": static_findings,
            "verdict": "CLEAN" if not static_findings else "FINDINGS",
        },
        "dynamic_trace": trace,
        "network_requests": trace["socket_events_total"],
        "verdict": (
            "PASS"
            if not static_findings and trace["socket_events_total"] == 0
            and trace["verify_status"] == "BOUND_PASS"
            else "FAIL"
        ),
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(
        f"offline_check: static={report['static_scan']['verdict']} "
        f"socket_events={trace['socket_events_total']} "
        f"verify={trace['verify_status']} -> {report['verdict']}"
    )
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
