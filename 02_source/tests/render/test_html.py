"""Renderer tests (P027-T010, PROJECT_BOOK §9, IMPLEMENTATION_PLAN §5 T010).

Fixtures are genuine ``benchreceipt.result/v1`` dicts produced by the
real verifier (:func:`benchreceipt.verify.evaluate`) on the frozen S0
fixtures — n01 (BOUND_PASS), g1 (BOUND_FAIL), d1 (UNBOUND, matrix
missing), a1 (UNBOUND, source SHA mismatch, the fixture that actually
carries SHA strings) — plus small synthetic dicts for the
INTERNAL_ERROR shape and the HTML-escaping probe. The renderer reads
only the verification dict; these tests assert exactly what the
result records, and assert that fields the result does not carry are
labelled "not recorded" rather than invented.

What result.v1 does NOT carry (so no test asserts it here): per-job
OS/runtime/run id/attempt/test counts, actual HEAD/tree SHAs for
passing jobs, and artifact SHA-256 digests/sizes. Those live in the
per-job receipts and the bundle manifest, not in the result JSON.
"""

from __future__ import annotations

import html as html_mod
import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from benchreceipt.policy import load_policy
from benchreceipt.render.html import (
    REASON_MEANINGS,
    STATUS_META,
    render_report,
)
from benchreceipt.verify import evaluate

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "s0"

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _StructureParser(HTMLParser):
    """Collects open/close tags; fails on mismatched or unclosed tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.seen: set[str] = set()
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.seen.add(tag)
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.seen.add(tag)

    def handle_endtag(self, tag: str) -> None:
        self.seen.add(tag)
        if tag in VOID_ELEMENTS:
            return
        if not self.stack:
            self.errors.append(f"closing </{tag}> with empty stack")
        elif self.stack[-1] != tag:
            self.errors.append(
                f"closing </{tag}> while <{self.stack[-1]}> is open"
            )
        else:
            self.stack.pop()


def _verify_fixture(fid: str) -> dict:
    """Run the real verifier on an S0 fixture; return its result dict."""
    fdir = FIXTURES / fid
    sha = json.loads((fdir / "expected.json").read_text())["expected_source_sha"]
    policy = load_policy(fdir / "policy.toml")
    return evaluate(policy, sha, fdir / "evidence")


def _render(result: dict, tmp_path: Path, name: str = "report.html") -> str:
    out = tmp_path / name
    render_report(result, out)
    return out.read_text(encoding="utf-8")


def _named_job_ids(result: dict) -> set[str]:
    """Job ids named anywhere in a result dict (re-derived here, not
    via the renderer, so the test is independent)."""
    ids: set[str] = set()
    for key in ("missing_jobs", "unexpected_jobs", "duplicate_jobs"):
        ids.update(str(j) for j in result.get(key) or [])
    for mismatch in result.get("identity_mismatches") or []:
        if mismatch.get("job_id") is not None:
            ids.add(str(mismatch["job_id"]))
    for err in result.get("report_errors") or []:
        if err.get("job_id") is not None:
            ids.add(str(err["job_id"]))
    return ids


def _internal_error_result() -> dict:
    return {
        "schema": "benchreceipt.result/v1",
        "status": "INTERNAL_ERROR",
        "jobs_verified": 0,
        "missing_jobs": [],
        "unexpected_jobs": [],
        "duplicate_jobs": [],
        "reason_codes": ["INTERNAL_ERROR"],
        "identity_mismatches": [],
        "report_errors": [
            {"code": "INTERNAL_ERROR", "message": "internal error during verification"}
        ],
    }


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fid", ["n01-single-pr-head", "g1-junit-failed", "d1-matrix-missing", "a1-wrong-source-sha"])
def test_html_structure_valid(fid: str, tmp_path: Path) -> None:
    result = _verify_fixture(fid)
    text = _render(result, tmp_path)
    assert text.startswith("<!DOCTYPE html>")
    parser = _StructureParser()
    parser.feed(text)
    parser.close()
    assert parser.errors == [], parser.errors
    assert parser.stack == [], f"unclosed tags: {parser.stack}"
    for tag in ("html", "head", "body", "main", "footer", "header", "section"):
        assert tag in parser.seen, f"<{tag}> missing"
    assert "<title>BenchReceipt verification report" in text


# ---------------------------------------------------------------------------
# Content per fixture
# ---------------------------------------------------------------------------


def test_n01_pass_renders_status_and_counts(tmp_path: Path) -> None:
    result = _verify_fixture("n01-single-pr-head")
    assert result["status"] == "BOUND_PASS"
    text = _render(result, tmp_path)
    assert "BOUND_PASS" in text
    assert STATUS_META["BOUND_PASS"][1] in text  # label text, not colour-only
    assert "Jobs verified:" in text and ">1<" in text
    assert "pr_head" in text  # expected source mode
    assert "No anomalies recorded" in text
    # A passing result names no job id: the report says so honestly
    # instead of inventing per-job detail.
    assert "No job is named in this result" in text
    assert "What this tool can and cannot prove" in text
    assert "cannot prove" in text


def test_g1_bound_fail_renders_job_and_reason(tmp_path: Path) -> None:
    result = _verify_fixture("g1-junit-failed")
    assert result["status"] == "BOUND_FAIL"
    text = _render(result, tmp_path)
    assert "BOUND_FAIL" in text
    assert STATUS_META["BOUND_FAIL"][1] in text
    assert "JUNIT_FAILED" in text
    # Reason code is shown with its meaning in words.
    assert html_mod.escape(REASON_MEANINGS["JUNIT_FAILED"][1]) in text
    assert "unit-linux-py312" in text
    assert "JUnit failed: 2 failures, 0 errors (tests=10)" in text
    assert "artifacts/junit.xml" in text
    # Click-to-locate: anomaly links to the job card.
    assert 'href="#job-unit-linux-py312"' in text
    assert 'id="job-unit-linux-py312"' in text


def test_d1_unbound_missing_job_with_click_to_locate(tmp_path: Path) -> None:
    result = _verify_fixture("d1-matrix-missing")
    assert result["status"] == "UNBOUND"
    text = _render(result, tmp_path)
    assert "UNBOUND" in text
    assert STATUS_META["UNBOUND"][1] in text
    assert "MATRIX_MISSING_JOB" in text
    assert html_mod.escape(REASON_MEANINGS["MATRIX_MISSING_JOB"][1]) in text
    assert "unit-windows-py312" in text  # the missing job id
    assert 'href="#job-unit-windows-py312"' in text
    assert 'id="job-unit-windows-py312"' in text
    assert "MISSING" in text


def test_a1_sha_strings_present(tmp_path: Path) -> None:
    # d1 carries no SHA; a1 is the S0 fixture whose result records SHAs
    # (inside identity_mismatches), so SHA coverage uses a1.
    result = _verify_fixture("a1-wrong-source-sha")
    assert result["status"] == "UNBOUND"
    text = _render(result, tmp_path)
    assert "SOURCE_SHA_MISMATCH" in text
    assert html_mod.escape(REASON_MEANINGS["SOURCE_SHA_MISMATCH"][1]) in text
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in text  # expected
    assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in text  # actual
    assert "Expected source SHA" in text
    assert "HEAD SHA" in text


@pytest.mark.parametrize("fid", ["n01-single-pr-head", "g1-junit-failed", "d1-matrix-missing", "a1-wrong-source-sha"])
def test_all_named_job_ids_present(fid: str, tmp_path: Path) -> None:
    result = _verify_fixture(fid)
    text = _render(result, tmp_path)
    for job_id in _named_job_ids(result):
        assert job_id in text, f"job id {job_id} missing from report for {fid}"
        assert f'href="#job-{job_id}"' in text or f'id="job-{job_id}"' in text


def test_internal_error_shape_renders(tmp_path: Path) -> None:
    result = _internal_error_result()
    text = _render(result, tmp_path)
    assert "INTERNAL_ERROR" in text
    assert STATUS_META["INTERNAL_ERROR"][1] in text
    assert html_mod.escape(REASON_MEANINGS["INTERNAL_ERROR"][1]) in text
    assert "Jobs verified:" in text and ">0<" in text
    # INTERNAL_ERROR results carry no expected_source_mode.
    assert "not recorded in this verification result" in text


# ---------------------------------------------------------------------------
# Self-containment, determinism, escaping, narrow screen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fid", ["n01-single-pr-head", "g1-junit-failed", "d1-matrix-missing"])
def test_no_external_resources(fid: str, tmp_path: Path) -> None:
    result = _verify_fixture(fid)
    out = tmp_path / "report.html"
    render_report(result, out)
    data = out.read_bytes()
    for token in (b"http://", b"https://", b"//cdn", b"<link", b"<script src=", b"url("):
        assert token not in data, f"external-resource token {token!r} in report"
    # No remote fetch of any kind.
    assert b"fetch(" not in data
    assert b"XMLHttpRequest" not in data


def test_determinism_same_input_identical_bytes(tmp_path: Path) -> None:
    result = _verify_fixture("g1-junit-failed")
    first = tmp_path / "first.html"
    second = tmp_path / "second.html"
    render_report(result, first)
    render_report(result, second)
    assert first.read_bytes() == second.read_bytes()
    # Key insertion order of the input dict must not change the output.
    reordered = dict(reversed(list(result.items())))
    third = tmp_path / "third.html"
    render_report(reordered, third)
    assert first.read_bytes() == third.read_bytes()


def test_html_escaping_probe(tmp_path: Path) -> None:
    payload_job = '<script>alert("x")</script>'
    payload_msg = '<img src=x onerror=alert(1)> forged report'
    result = {
        "schema": "benchreceipt.result/v1",
        "status": "UNBOUND",
        "jobs_verified": 0,
        "missing_jobs": [payload_job],
        "unexpected_jobs": [],
        "duplicate_jobs": [],
        "reason_codes": ["MATRIX_MISSING_JOB"],
        "identity_mismatches": [],
        "report_errors": [
            {"code": "REPORT_MISSING", "message": payload_msg, "job_id": payload_job,
             "path": "artifacts/<evil>.xml"}
        ],
        "expected_source_mode": "pr_head",
    }
    out = tmp_path / "report.html"
    render_report(result, out)
    data = out.read_bytes()
    # The payload must never appear as markup.
    assert b"<script>alert" not in data
    assert b"<img src=x" not in data
    # ... but must appear escaped, so the finding is still readable.
    assert b"&lt;script&gt;alert" in data
    assert b"&lt;img src=x" in data
    assert b"artifacts/&lt;evil&gt;.xml" in data
    # The escaped page still parses cleanly.
    parser = _StructureParser()
    parser.feed(out.read_text(encoding="utf-8"))
    parser.close()
    assert parser.errors == []
    assert parser.stack == []


def test_narrow_screen_css_present(tmp_path: Path) -> None:
    result = _verify_fixture("n01-single-pr-head")
    text = _render(result, tmp_path)
    assert "@media (max-width: 400px)" in text
    narrow = text.split("@media (max-width: 400px)", 1)[1]
    assert "grid-template-columns: 1fr" in narrow  # single-column job grid


def test_renderer_rejects_bad_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        render_report({}, tmp_path / "r.html")
    with pytest.raises(ValueError):
        render_report("not a dict", tmp_path / "r.html")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        render_report({"schema": "benchreceipt.result/v1"}, tmp_path / "r.html")


# ---------------------------------------------------------------------------
# CLI end-to-end: report never corrupts the verification JSON
# ---------------------------------------------------------------------------


def test_cli_report_end_to_end(tmp_path: Path) -> None:
    result_path = tmp_path / "verification.json"
    proc = subprocess.run(
        [sys.executable, "-m", "benchreceipt", "verify",
         "--policy", str(FIXTURES / "n01-single-pr-head" / "policy.toml"),
         "--evidence", str(FIXTURES / "n01-single-pr-head" / "evidence"),
         "--expected-source-sha", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
         "--out", str(result_path)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    before = result_path.read_bytes()

    html_path = tmp_path / "report.html"
    proc = subprocess.run(
        [sys.executable, "-m", "benchreceipt", "report",
         "--input", str(result_path), "--html", str(html_path)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = html_path.read_text(encoding="utf-8")
    assert "BOUND_PASS" in html
    assert "P027-T010" in html
    # The verification JSON is byte-identical after rendering.
    assert result_path.read_bytes() == before

    # Invalid input still exits 3.
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "benchreceipt", "report",
         "--input", str(bad), "--html", str(tmp_path / "r.html")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 3
