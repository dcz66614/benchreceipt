"""Static HTML evidence-chain report renderer (P027-T010).

Renders a ``benchreceipt.result/v1`` verification dict as one
self-contained HTML file: inline CSS + inline JS only, no external
resources (no CDN, no remote fonts, no analytics, no network fetch of
any kind). The renderer reads ONLY the verification dict it is given;
it never re-runs verification and never reads receipts, bundles, or
policies.

Honest-display rule (interface gap, recorded for T013): the frozen
``benchreceipt.result/v1`` schema carries aggregate findings only —
status, jobs_verified, missing/unexpected/duplicate job ids,
reason codes, identity mismatches (job/field/expected/actual) and
report errors (code/message/job/path). It does NOT carry per-job
OS/runtime/run id/attempt/test counts, actual HEAD/tree SHAs for
passing jobs, or artifact SHA-256 digests and sizes. This renderer
therefore shows exactly what the result records, and labels every
field the result does not carry as "not recorded in this verification
result" instead of inventing a value. Per-job detail lives in the
per-job receipts and the bundle manifest, not in the result JSON.

Determinism: the same input dict renders byte-identical HTML. No
wall-clock timestamp is embedded (PROJECT_BOOK §9.1 asks for a
generation time in the top bar; determinism wins here, so the top bar
shows the tool version instead), and every list is sorted before
rendering. All user-controlled strings are passed through
:func:`html.escape`; nothing is ever interpolated raw.

Status is never colour-only: every status shows text + icon + colour
+ reason code(s) with their meaning in words (PROJECT_BOOK §9.2).
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import benchreceipt

__all__ = ["render_report"]

# ---------------------------------------------------------------------------
# Status metadata (PROJECT_BOOK §5.6, §9.2)
# ---------------------------------------------------------------------------

# status -> (icon, label, blurb). Colour comes from the CSS class
# "status-<lowercase status>"; the icon + text are always present so
# colour is never the only channel.
STATUS_META: dict[str, tuple[str, str, str]] = {
    "BOUND_PASS": (
        "\u2713",
        "BOUND_PASS — Bound and passing",
        "All required evidence is bound to the expected source and run, "
        "and the test reports passed.",
    ),
    "BOUND_FAIL": (
        "\u2717",
        "BOUND_FAIL — Bound but failing",
        "The evidence belongs to the expected source and run, but tests "
        "failed or a policy condition on the test result failed.",
    ),
    "UNBOUND": (
        "\u26a0",
        "UNBOUND — Not bound",
        "Identity, matrix, or report evidence is missing or inconsistent, "
        "so no passing conclusion can be drawn.",
    ),
    "INVALID": (
        "\u2a2f",
        "INVALID — Damaged input",
        "Input format, hash, or schema is damaged. Nothing in this "
        "result can be trusted as a pass.",
    ),
    "INTERNAL_ERROR": (
        "!",
        "INTERNAL_ERROR — Verifier failure",
        "The verifier itself hit an unexpected internal error. No "
        "finding in this result can be trusted.",
    ),
}

# ---------------------------------------------------------------------------
# Reason-code meanings (frozen vocabulary, 02_source/docs/REASON_CODES.md).
# status class + one-line meaning, shown in words next to every code so
# a code is never displayed bare.
# ---------------------------------------------------------------------------

REASON_MEANINGS: dict[str, tuple[str, str]] = {
    "SOURCE_SHA_MISMATCH": ("UNBOUND", "A job's git HEAD SHA differs from the expected source SHA (PR head / merge commit confusion)."),
    "SOURCE_MODE_MISMATCH": ("UNBOUND", "A job's git source mode differs from the policy source mode; PR head and merge SHA are never equivalent."),
    "TREE_SHA_MISMATCH": ("UNBOUND", "Jobs disagree on the git tree SHA while the policy requires one tree across jobs."),
    "RUN_ID_MISMATCH": ("UNBOUND", "Jobs disagree on the workflow run ID while the policy requires one run."),
    "RUN_ATTEMPT_MISMATCH": ("UNBOUND", "Jobs disagree on the run attempt while the policy requires one attempt."),
    "WORKFLOW_MISMATCH": ("UNBOUND", "A job's workflow name differs from the policy's expected workflow."),
    "MATRIX_MISSING_JOB": ("UNBOUND", "A required matrix job has no receipt in the bundle."),
    "MATRIX_DUPLICATE_JOB": ("UNBOUND", "A job ID appears in more than one receipt."),
    "MATRIX_UNEXPECTED_JOB": ("UNBOUND", "A receipt's job ID is not in the policy's required jobs."),
    "SOURCE_MUTATED_DURING_RUN": ("UNBOUND", "Tracked source changed during a job's run, or the source was dirty after the run when clean was required."),
    "REPORT_MISSING": ("UNBOUND", "A report listed by a receipt is absent, or a report kind the policy requires has no entry."),
    "MISSING_FIELD": ("UNBOUND", "A field the policy requires is absent, although the schema allows it to be optional (e.g. the JUnit summary)."),
    "REPORT_HASH_MISMATCH": ("INVALID", "A report file's recomputed size or SHA-256 differs from the receipt's recorded size / digest."),
    "JUNIT_MALFORMED": ("INVALID", "A JUnit report file cannot be parsed as XML."),
    "JUNIT_SUMMARY_MISMATCH": ("INVALID", "The parsed JUnit counts disagree with the receipt's JUnit summary."),
    "LCOV_MALFORMED": ("INVALID", "A LCOV report file cannot be parsed as valid LCOV."),
    "INTERNAL_ERROR": ("INTERNAL_ERROR", "The verifier itself hit an unexpected internal error — a verifier bug, not bad input."),
    "INVALID_RECEIPT": ("INVALID", "A receipt file is not JSON, or fails benchreceipt.run/v1 validation."),
    "INVALID_POLICY": ("INVALID", "The policy fails benchreceipt.policy/v1 validation."),
    "INVALID_EVIDENCE": ("INVALID", "The evidence directory is missing, not a directory, or unreadable."),
    "JUNIT_FAILED": ("BOUND_FAIL", "Evidence is bound, but the JUnit report has failures or errors."),
    "JUNIT_EMPTY": ("BOUND_FAIL", "Evidence is bound, but the JUnit report has 0 tests."),
    "EXIT_CODE_MISMATCH": ("BOUND_FAIL", "The command exit code contradicts the JUnit outcome."),
    "POLICY_MISMATCH": ("BOUND_FAIL", "Evidence is bound, but the JUnit test count is below the policy min_tests."),
}

_NOT_RECORDED = "not recorded in this verification result"

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  margin: 0 auto; max-width: 1100px; padding: 0 16px 32px;
  background: #ffffff; color: #111111; line-height: 1.5; }
h1 { font-size: 1.4rem; margin: 0; }
h2 { font-size: 1.15rem; border-bottom: 1px solid #999999; padding-bottom: 4px; }
h3 { font-size: 1rem; margin: 0.4em 0; }
code, .mono { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  overflow-wrap: anywhere; word-break: break-all; }
.topbar { padding: 16px; margin: 16px 0; border-radius: 8px; border: 2px solid; }
.topbar .status-line { font-size: 1.3rem; font-weight: 700; }
.topbar p { margin: 0.4em 0; }
.status-BOUND_PASS { background: #e6f4ea; border-color: #137333; color: #0b3d1e; }
.status-BOUND_FAIL { background: #fce8e6; border-color: #a50e0e; color: #5f0b0b; }
.status-UNBOUND { background: #fef7e0; border-color: #b06000; color: #4d2e00; }
.status-INVALID { background: #fce8e6; border-color: #7a0d0d; color: #5f0b0b; }
.status-INTERNAL_ERROR { background: #f1f3f4; border-color: #5f6368; color: #202124; }
.status-UNKNOWN { background: #f1f3f4; border-color: #5f6368; color: #202124; }
.tag { display: inline-block; font-weight: 700; font-size: 0.8rem;
  border: 1px solid currentColor; border-radius: 4px; padding: 0 6px; margin-right: 4px; }
.card { border: 1px solid #5f6368; border-radius: 8px; padding: 12px; margin: 8px 0; }
.job-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.job-card { border: 1px solid #5f6368; border-radius: 8px; padding: 12px; }
.job-card.missing { border-style: dashed; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #80868b; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f1f3f4; color: #202124; }
ul { margin: 0.4em 0; }
li { margin: 0.3em 0; }
a { color: #0b57d0; }
details { margin-top: 8px; }
summary { cursor: pointer; font-weight: 600; }
button.copy-btn { cursor: pointer; margin-left: 8px; }
.note { background: #f1f3f4; color: #202124; border-left: 4px solid #5f6368;
  padding: 8px 12px; margin: 8px 0; }
footer { border-top: 2px solid #5f6368; margin-top: 24px; padding-top: 12px; font-size: 0.95rem; }
@media (max-width: 400px) {
  body { padding: 0 8px 24px; }
  .job-grid { grid-template-columns: 1fr; }
  .topbar .status-line { font-size: 1.1rem; }
  table, thead, tbody, th, td, tr { display: block; width: 100%; }
  th { display: none; }
  td { border: none; border-bottom: 1px solid #dadce0; padding: 4px 0; }
  td::before { content: attr(data-label) ": "; font-weight: 700; }
}
@media (prefers-color-scheme: dark) {
  body { background: #202124; color: #e8eaed; }
  a { color: #8ab4f8; }
  th { background: #3c4043; color: #e8eaed; }
  .status-BOUND_PASS { background: #0d3b1e; border-color: #81c995; color: #ceead6; }
  .status-BOUND_FAIL { background: #3d0d0d; border-color: #f28b82; color: #fad2cf; }
  .status-UNBOUND { background: #3d2c00; border-color: #fdd663; color: #feefc3; }
  .status-INVALID { background: #3d0d0d; border-color: #f28b82; color: #fad2cf; }
  .status-INTERNAL_ERROR, .status-UNKNOWN { background: #3c4043; border-color: #9aa0a6; color: #e8eaed; }
  .card, .job-card { border-color: #9aa0a6; }
  .note { background: #3c4043; color: #e8eaed; }
}
"""

_JS = """
document.addEventListener("click", function (event) {
  var btn = event.target.closest ? event.target.closest("button.copy-btn") : null;
  if (!btn) { return; }
  var text = btn.getAttribute("data-text") || "";
  var done = function () { btn.textContent = "Copied"; };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, function () { btn.textContent = "Copy failed"; });
  } else { btn.textContent = "Copy unavailable"; }
});
"""


def _esc(value: Any) -> str:
    """HTML-escape any value (None becomes an empty string)."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _slug(job_id: str) -> str:
    """Deterministic anchor slug for a job id (safe for id/href)."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(job_id)).strip("-")
    return slug or "job"


def _job_anchor(job_id: str, taken: dict[str, str]) -> str:
    """Unique anchor id for a job id; first use keeps the plain slug."""
    base = _slug(job_id)
    if base not in taken:
        taken[base] = job_id
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    anchor = f"{base}-{n}"
    taken[anchor] = job_id
    return anchor


def _status_block(status: str) -> tuple[str, str, str]:
    """(icon, label, blurb) for a status; unknown statuses are labelled
    as unknown and never presented as a pass."""
    meta = STATUS_META.get(status)
    if meta is not None:
        return meta
    return ("?", f"{status} — Unknown status", "This status is not one of the five frozen BenchReceipt states; treat the result as untrusted.")


def _reason_meaning(code: str) -> tuple[str, str]:
    """(status class, meaning) for a reason code; unknown codes are
    labelled unknown rather than silently dropped."""
    return REASON_MEANINGS.get(code, ("UNKNOWN", "Unknown reason code — not in the frozen vocabulary; treat the finding as untrusted."))


def _sorted_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return sorted(value, key=lambda v: str(v))
    return []


def _mismatches(verification: dict) -> list[dict[str, Any]]:
    raw = verification.get("identity_mismatches")
    if not isinstance(raw, list):
        return []
    out = [m for m in raw if isinstance(m, dict)]
    out.sort(key=lambda m: (str(m.get("job_id", "")), str(m.get("field", ""))))
    return out


def _report_errors(verification: dict) -> list[dict[str, Any]]:
    raw = verification.get("report_errors")
    if not isinstance(raw, list):
        return []
    out = [e for e in raw if isinstance(e, dict)]
    out.sort(key=lambda e: (str(e.get("job_id", "")), str(e.get("code", "")), str(e.get("path", ""))))
    return out


def _all_job_ids(verification: dict) -> list[str]:
    """Every job id named anywhere in the result, sorted.

    The result schema names jobs only where something is wrong (or a
    job is missing/unexpected/duplicate); a passing job's id is not
    recorded in the result, so a fully-passing result yields an empty
    list here — see the module docstring.
    """
    ids: set[str] = set()
    for key in ("missing_jobs", "unexpected_jobs", "duplicate_jobs"):
        for job_id in _sorted_list(verification.get(key)):
            ids.add(str(job_id))
    for mismatch in _mismatches(verification):
        if mismatch.get("job_id") is not None:
            ids.add(str(mismatch["job_id"]))
    for err in _report_errors(verification):
        if err.get("job_id") is not None:
            ids.add(str(err["job_id"]))
    return sorted(ids)


def _render_topbar(verification: dict, status: str) -> str:
    icon, label, blurb = _status_block(status)
    cls = status.lower() if status in STATUS_META else "UNKNOWN"
    jobs_verified = verification.get("jobs_verified", 0)
    mode = verification.get("expected_source_mode")
    mode_text = _esc(mode) if mode is not None else _NOT_RECORDED
    codes = _sorted_list(verification.get("reason_codes"))
    codes_text = ", ".join(_esc(c) for c in codes) if codes else "none"
    return (
        f'<header class="topbar status-{cls}" role="banner">\n'
        f"<h1>BenchReceipt verification report</h1>\n"
        f'<p class="status-line"><span aria-hidden="true">{_esc(icon)}</span> '
        f"Status: {_esc(label)}</p>\n"
        f"<p>{_esc(blurb)}</p>\n"
        f"<p>Jobs verified: <strong>{_esc(jobs_verified)}</strong> &nbsp;|&nbsp; "
        f"Expected source mode: <strong>{mode_text}</strong> &nbsp;|&nbsp; "
        f"Reason codes: <strong>{codes_text}</strong></p>\n"
        "</header>\n"
    )


def _render_source_identity(verification: dict) -> str:
    mismatches = _mismatches(verification)
    by_field: dict[str, list[dict[str, Any]]] = {}
    for mismatch in mismatches:
        by_field.setdefault(str(mismatch.get("field", "")), []).append(mismatch)

    rows: list[str] = []

    def _field_rows(field: str, label: str) -> None:
        entries = by_field.get(field, [])
        if not entries:
            return
        expected_values = sorted({str(e["expected"]) for e in entries if e.get("expected") is not None})
        for entry in entries:
            rows.append(
                "<tr>"
                f'<td data-label="Field">{_esc(label)}</td>'
                f'<td data-label="Job">{_esc(entry.get("job_id", ""))}</td>'
                f'<td data-label="Expected" class="mono">{_esc(entry.get("expected", ""))}</td>'
                f'<td data-label="Actual" class="mono">{_esc(entry.get("actual", ""))}</td>'
                "</tr>"
            )
        if len(expected_values) == 1:
            rows.append(
                "<tr>"
                f'<td data-label="Field">{_esc(label)} (expected, all jobs)</td>'
                "<td data-label=\"Job\">—</td>"
                f'<td data-label="Expected" class="mono">{_esc(expected_values[0])}</td>'
                "<td data-label=\"Actual\">—</td>"
                "</tr>"
            )

    _field_rows("git.head_sha", "HEAD SHA")
    _field_rows("git.tree_sha", "Tree SHA")
    _field_rows("git.source_mode", "Source mode")
    _field_rows("ci.run_id", "Workflow run ID")
    _field_rows("ci.run_attempt", "Run attempt")
    _field_rows("ci.workflow", "Workflow")

    mode = verification.get("expected_source_mode")
    mode_line = (
        f"<p>Expected source mode: <strong>{_esc(mode)}</strong></p>"
        if mode is not None
        else f"<p>Expected source mode: {_NOT_RECORDED}.</p>"
    )
    expected_sha: list[str] = sorted(
        {str(e["expected"]) for e in by_field.get("git.head_sha", []) if e.get("expected") is not None}
    )
    if expected_sha:
        sha_line = "<p>Expected source SHA: " + ", ".join(
            f'<code>{_esc(s)}</code>' for s in expected_sha
        ) + "</p>"
    else:
        sha_line = (
            "<p>Expected source SHA: "
            f"{_NOT_RECORDED} — the verification result records the expected "
            "SHA only when a job mismatches it; see the per-job receipts "
            "for the checked-out HEAD.</p>"
        )
    if rows:
        table = (
            "<table>\n<thead><tr><th>Field</th><th>Job</th><th>Expected</th><th>Actual</th></tr></thead>\n"
            "<tbody>\n" + "".join(rows) + "</tbody>\n</table>\n"
        )
        note = (
            "<p class=\"note\">Only mismatching fields are listed: a field with no "
            "row matched the expected value for every checked job. Actual "
            "HEAD / tree SHAs for passing jobs are not carried by "
            "benchreceipt.result/v1.</p>"
        )
    else:
        table = ""
        note = (
            "<p class=\"note\">No identity mismatches recorded — every checked "
            "job matched the expected source, run, and workflow identity. "
            "Actual HEAD / tree SHAs are not carried by "
            "benchreceipt.result/v1 when they match; see the per-job "
            "receipts for the values.</p>"
        )
    return (
        '<section aria-labelledby="source-identity">\n'
        '<h2 id="source-identity">Source identity</h2>\n'
        f"{mode_line}\n{sha_line}\n{table}{note}"
        "</section>\n"
    )


def _render_job_grid(verification: dict) -> str:
    job_ids = _all_job_ids(verification)
    mismatches = _mismatches(verification)
    errors = _report_errors(verification)
    missing = set(str(j) for j in _sorted_list(verification.get("missing_jobs")))
    unexpected = set(str(j) for j in _sorted_list(verification.get("unexpected_jobs")))
    duplicate = set(str(j) for j in _sorted_list(verification.get("duplicate_jobs")))
    by_job_mismatch: dict[str, list[dict[str, Any]]] = {}
    for mismatch in mismatches:
        by_job_mismatch.setdefault(str(mismatch.get("job_id", "")), []).append(mismatch)
    by_job_error: dict[str, list[dict[str, Any]]] = {}
    for err in errors:
        by_job_error.setdefault(str(err.get("job_id", "")), []).append(err)

    taken: dict[str, str] = {}
    anchors = {job_id: _job_anchor(job_id, taken) for job_id in job_ids}

    intro = (
        "<p>One card per job named in this verification result "
        "(missing, unexpected, duplicate, mismatching, or with report "
        "errors). benchreceipt.result/v1 does not carry per-job OS, "
        "runtime, run ID, attempt, or test counts, so those fields are "
        "not shown here — see the per-job receipts for them. Click a "
        "card's heading to expand its recorded findings.</p>"
    )
    if not job_ids:
        jobs_verified = verification.get("jobs_verified", 0)
        return (
            '<section aria-labelledby="job-matrix">\n'
            '<h2 id="job-matrix">Job matrix</h2>\n'
            f"{intro}\n"
            "<p class=\"note\">No job is named in this result: there are no "
            "missing, unexpected, duplicate, mismatching, or erroring "
            f"jobs. Jobs verified: <strong>{_esc(jobs_verified)}</strong>. "
            "Per-job identities for the verified jobs are not recorded "
            "in the verification result.</p>\n"
            "</section>\n"
        )

    cards: list[str] = []
    for job_id in job_ids:
        anchor = anchors[job_id]
        tags: list[str] = []
        if job_id in missing:
            tags.append("MISSING")
        if job_id in unexpected:
            tags.append("UNEXPECTED")
        if job_id in duplicate:
            tags.append("DUPLICATE")
        if job_id in by_job_mismatch:
            tags.append("IDENTITY MISMATCH")
        if job_id in by_job_error:
            tags.append("REPORT ERROR")
        if not tags:
            tags.append("NAMED IN RESULT")
        tag_html = " ".join(f'<span class="tag">{_esc(t)}</span>' for t in tags)
        cls = "job-card missing" if job_id in missing else "job-card"
        body: list[str] = []
        if job_id in missing:
            body.append("<p>This required job has no receipt in the bundle.</p>")
        if job_id in unexpected:
            body.append("<p>This job's receipt is not in the policy's required jobs.</p>")
        if job_id in duplicate:
            body.append("<p>This job ID appears in more than one receipt.</p>")
        job_mismatches = by_job_mismatch.get(job_id, [])
        if job_mismatches:
            rows = "".join(
                "<tr>"
                f'<td data-label="Field">{_esc(m.get("field", ""))}</td>'
                f'<td data-label="Expected" class="mono">{_esc(m.get("expected", ""))}</td>'
                f'<td data-label="Actual" class="mono">{_esc(m.get("actual", ""))}</td>'
                "</tr>"
                for m in job_mismatches
            )
            body.append(
                "<h3>Identity mismatches</h3>\n<table>\n"
                "<thead><tr><th>Field</th><th>Expected</th><th>Actual</th></tr></thead>\n"
                f"<tbody>\n{rows}</tbody>\n</table>"
            )
        job_errors = by_job_error.get(job_id, [])
        if job_errors:
            items = "".join(
                "<li><strong>" + _esc(e.get("code", "")) + "</strong>: "
                + _esc(e.get("message", ""))
                + (f' <span class="mono">({_esc(e.get("path", ""))})</span>' if e.get("path") else "")
                + "</li>"
                for e in job_errors
            )
            body.append(f"<h3>Report errors</h3>\n<ul>\n{items}</ul>")
        if not body:
            body.append("<p>No per-job findings recorded for this job.</p>")
        cards.append(
            f'<article class="{cls}" id="job-{_esc(anchor)}" aria-label="Job {_esc(job_id)}">\n'
            f"<h3>{_esc(job_id)}</h3>\n"
            f"<p>{tag_html}</p>\n"
            "<details>\n<summary>Recorded findings</summary>\n"
            + "".join(body)
            + "</details>\n</article>\n"
        )
    return (
        '<section aria-labelledby="job-matrix">\n'
        '<h2 id="job-matrix">Job matrix</h2>\n'
        f"{intro}\n"
        '<div class="job-grid">\n' + "".join(cards) + "</div>\n</section>\n"
    )


def _render_anomalies(verification: dict) -> str:
    codes = _sorted_list(verification.get("reason_codes"))
    mismatches = _mismatches(verification)
    errors = _report_errors(verification)
    anchors: dict[str, str] = {}
    taken: dict[str, str] = {}
    for job_id in _all_job_ids(verification):
        anchors[job_id] = _job_anchor(job_id, taken)

    def _job_link(job_id: Any) -> str:
        job = str(job_id) if job_id is not None else ""
        if job and job in anchors:
            return f' <a href="#job-{_esc(anchors[job])}">locate job {_esc(job)}</a>'
        if job:
            return f" (job: {_esc(job)})"
        return ""

    items: list[str] = []
    # Matrix codes name jobs only via the job lists (there is no
    # per-job mismatch/error item for them), so the code item itself
    # carries the click-to-locate links to those job cards.
    matrix_links: dict[str, str] = {
        "MATRIX_MISSING_JOB": "missing_jobs",
        "MATRIX_UNEXPECTED_JOB": "unexpected_jobs",
        "MATRIX_DUPLICATE_JOB": "duplicate_jobs",
    }
    for code in codes:
        status_class, meaning = _reason_meaning(str(code))
        copy_text = f"{code}: {meaning}"
        links = ""
        list_key = matrix_links.get(str(code))
        if list_key is not None:
            for job_id in _sorted_list(verification.get(list_key)):
                links += _job_link(job_id)
        items.append(
            "<li>"
            f"<strong>{_esc(code)}</strong> "
            f'<span class="tag">{_esc(status_class)}</span> — {_esc(meaning)}'
            f"{links}"
            f'<button type="button" class="copy-btn" data-text="{_esc(copy_text)}">Copy summary</button>'
            "</li>"
        )
    for mismatch in mismatches:
        field = str(mismatch.get("field", ""))
        job = mismatch.get("job_id", "")
        text = (
            f"Identity mismatch: {field} for job {job} — expected "
            f"{mismatch.get('expected', '')}, actual {mismatch.get('actual', '')}"
        )
        items.append(
            "<li>"
            f"Identity mismatch: <code>{_esc(field)}</code> — expected "
            f'<code>{_esc(mismatch.get("expected", ""))}</code>, actual '
            f'<code>{_esc(mismatch.get("actual", ""))}</code>'
            f"{_job_link(job)}"
            f'<button type="button" class="copy-btn" data-text="{_esc(text)}">Copy summary</button>'
            "</li>"
        )
    for err in errors:
        code = str(err.get("code", ""))
        job = err.get("job_id", "")
        path = err.get("path")
        text = f"{code}: {err.get('message', '')}" + (f" ({path})" if path else "")
        items.append(
            "<li>"
            f"<strong>{_esc(code)}</strong>: {_esc(err.get('message', ''))}"
            + (f' <span class="mono">({_esc(path)})</span>' if path else "")
            + f"{_job_link(job)}"
            f'<button type="button" class="copy-btn" data-text="{_esc(text)}">Copy summary</button>'
            "</li>"
        )
    if not items:
        body = "<p>No anomalies recorded. No reason codes, identity mismatches, or report errors.</p>"
    else:
        body = "<ul>\n" + "".join(items) + "</ul>\n"
    return (
        '<section aria-labelledby="anomalies">\n'
        '<h2 id="anomalies">Anomalies — evidence chain, first inconsistency</h2>\n'
        "<p>Each item links to the job card it concerns (click-to-locate). "
        "Reason codes are shown with their meaning in words, not by "
        "colour alone.</p>\n"
        f"{body}</section>\n"
    )


def _render_artifacts(verification: dict) -> str:
    errors = _report_errors(verification)
    with_path = [e for e in errors if e.get("path")]
    if not with_path:
        return (
            '<section aria-labelledby="artifacts">\n'
            '<h2 id="artifacts">Artifacts</h2>\n'
            "<p>No artifact files are named in this verification result.</p>\n"
            "<p class=\"note\">benchreceipt.result/v1 does not carry artifact "
            "SHA-256 digests, sizes, or parse summaries; those are recorded "
            "in the per-job receipts and the bundle manifest "
            "(SHA256SUMS). Only artifacts with a recorded problem are "
            "named here, with their problem code and message.</p>\n"
            "</section>\n"
        )
    by_path: dict[str, list[dict[str, Any]]] = {}
    for err in with_path:
        by_path.setdefault(str(err["path"]), []).append(err)
    rows = ""
    for path in sorted(by_path):
        entries = by_path[path]
        codes = ", ".join(sorted({str(e.get("code", "")) for e in entries}))
        jobs = ", ".join(sorted({str(e.get("job_id", "")) for e in entries if e.get("job_id") is not None}))
        messages = "<br>".join(_esc(e.get("message", "")) for e in entries)
        rows += (
            "<tr>"
            f'<td data-label="File" class="mono">{_esc(path)}</td>'
            f"<td data-label=\"Problem codes\">{_esc(codes)}</td>"
            f"<td data-label=\"Jobs\">{_esc(jobs)}</td>"
            f"<td data-label=\"Detail\">{messages}</td>"
            "</tr>"
        )
    return (
        '<section aria-labelledby="artifacts">\n'
        '<h2 id="artifacts">Artifacts</h2>\n'
        "<p>Artifact files named by this verification result (only "
        "artifacts with a recorded problem are named here).</p>\n"
        "<table>\n<thead><tr><th>File</th><th>Problem codes</th><th>Jobs</th><th>Detail</th></tr></thead>\n"
        f"<tbody>\n{rows}</tbody>\n</table>\n"
        "<p class=\"note\">SHA-256 digests, sizes, and parse summaries are "
        "not carried by benchreceipt.result/v1; they are recorded in the "
        "per-job receipts and the bundle manifest (SHA256SUMS). A file "
        "with no row here had no problem recorded — that is not, by "
        "itself, a digest check; the digest check happened during "
        "verification and its outcome is the status above.</p>\n"
        "</section>\n"
    )


def _render_footer() -> str:
    version = getattr(benchreceipt, "__version__", "unknown")
    return (
        "<footer>\n"
        "<h2>What this tool can and cannot prove</h2>\n"
        "<p><strong>BenchReceipt can prove:</strong> whether the Git "
        "commit / tree, run environment, command summary, CI run and "
        "attempt, job and matrix, and report bytes collected in the "
        "current workspace satisfy the declared binding rules — and "
        "where the first inconsistency is, when they do not.</p>\n"
        "<p><strong>BenchReceipt cannot prove:</strong> that the test "
        "logic is correct, that test assertions are strong enough, that "
        "the code has no bugs, or that a workflow author did not "
        "maliciously forge environment variables or reports. SHA-256 "
        "detects accidental mix-ups and byte changes; it is not a "
        "cryptographic signature and does not authenticate a malicious "
        "runner. This report does not replace SLSA, in-toto, Sigstore, "
        "or GitHub Artifact Attestations.</p>\n"
        f"<p>BenchReceipt version: <strong>{_esc(version)}</strong> &nbsp;|&nbsp; "
        "Renderer: P027-T010 static HTML renderer (inline CSS/JS only, "
        "no external resources, no network requests). This page renders "
        "only the verification JSON; it does not re-run verification.</p>\n"
        "</footer>\n"
    )


def render_report(verification: dict, out_path: Path) -> None:
    """Render ``verification`` (a benchreceipt.result/v1 dict) to HTML.

    ``out_path`` is created (with parent directories) as a single
    self-contained HTML file. The output is deterministic: the same
    input dict always renders byte-identical HTML. Raises
    :class:`ValueError` if ``verification`` is not a dict or has no
    ``status``; every other missing optional field is rendered as
    "not recorded" rather than crashing.
    """
    if not isinstance(verification, dict):
        raise ValueError("verification result must be a dict")
    status = verification.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError("verification result has no status")

    icon, label, _blurb = _status_block(status)
    title = f"BenchReceipt verification report — {status}"
    parts = [
        "<!DOCTYPE html>\n",
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        f"<title>{_esc(title)}</title>\n",
        f"<style>\n{_CSS}\n</style>\n",
        "</head>\n<body>\n",
        _render_topbar(verification, status),
        "<main>\n",
        _render_source_identity(verification),
        _render_job_grid(verification),
        _render_anomalies(verification),
        _render_artifacts(verification),
        "</main>\n",
        _render_footer(),
        f"<script>\n{_JS}\n</script>\n",
        "</body>\n</html>\n",
    ]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts), encoding="utf-8")
