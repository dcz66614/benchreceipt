/**
 * Oracle tests (P027-T004). Node built-in node:test only, no npm deps.
 *
 * Covers: the TOML parser on a real fixture policy, the CLI contract on
 * a control fixture (BOUND_PASS, exit 0) and on the spec §12.3 samples
 * (attempt mismatch -> UNBOUND + RUN_ATTEMPT_MISMATCH, exit 2; wrong
 * source SHA -> UNBOUND + SOURCE_SHA_MISMATCH), the JUnit minimal
 * parser (valid / empty / malformed), and the invalid-policy path.
 *
 * FIX-R13b adds: the TOML parser (duplicate keys rejected, trailing
 * comments, string escapes), the LCOV parser, the XML JUnit parser
 * (CDATA/comments/namespaces/self-closing/DOCTYPE/count attributes),
 * run.v1/policy.v1 schema validation, symlink-resolving path
 * containment, per-report judging of every JUnit report (F-01 mirror),
 * and the --expected-run-id / --expected-attempt pins. The
 * Python-side parity for the same corpus is pinned by
 * tests/test_oracle_parity_r13b.py (pytest, shells out to this CLI).
 *
 * FIX-R1 adds: both after fields absent fails closed with
 * ``MISSING_FIELD`` (UNBOUND, exit 2) — the R1 false-PASS shape and
 * the e7 legacy fixture, via ``evaluate()`` and the CLI.
 *
 * Run: node --test 02_source/oracle/*.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { evaluate, parseJUnitMinimal, parseLcov, parsePolicyToml, parseToml, resolveRealPath } from "./verify.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(HERE, "..", "fixtures", "s0");

function loadFixture(id) {
  const dir = join(FIXTURES, id);
  const policy = parsePolicyToml(readFileSync(join(dir, "policy.toml"), "utf-8"));
  const expected = JSON.parse(readFileSync(join(dir, "expected.json"), "utf-8"));
  return { dir, policy, expectedSha: expected.expected_source_sha };
}

function runCli(id) {
  const { dir, expectedSha } = loadFixture(id);
  const proc = spawnSync(
    process.execPath,
    [join(HERE, "verify.mjs"), "--policy", join(dir, "policy.toml"),
     "--expected-source-sha", expectedSha, "--evidence", join(dir, "evidence")],
    { encoding: "utf-8" },
  );
  return { proc, result: JSON.parse(proc.stdout) };
}

test("TOML parser reads a real fixture policy", () => {
  const { policy } = loadFixture("n02-two-job-pr-head");
  assert.equal(policy.schema_version, 1);
  assert.equal(policy.source_mode, "pr_head");
  assert.deepEqual(policy.required_jobs, ["unit-linux-py312", "unit-windows-py312"]);
  assert.equal(policy.reports.junit, "required");
  assert.equal(policy.reports.lcov, "optional");
  assert.equal(policy.security.store_stdout, false);
});

test("control fixture verifies BOUND_PASS via evaluate()", () => {
  const { dir, policy, expectedSha } = loadFixture("n02-two-job-pr-head");
  const result = evaluate(policy, expectedSha, join(dir, "evidence"));
  assert.equal(result.status, "BOUND_PASS");
  assert.equal(result.jobs_verified, 2);
  assert.deepEqual(result.reason_codes, []);
});

test("CLI contract: control fixture prints result JSON, exit 0", () => {
  const { proc, result } = runCli("n02-two-job-pr-head");
  assert.equal(proc.status, 0);
  assert.equal(result.schema, "benchreceipt.result/v1");
  assert.equal(result.status, "BOUND_PASS");
});

test("spec §12.3 sample B: mixed attempt -> UNBOUND + RUN_ATTEMPT_MISMATCH, exit 2", () => {
  const { proc, result } = runCli("c1-attempt-mismatch");
  assert.equal(proc.status, 2);
  assert.equal(result.status, "UNBOUND");
  assert.deepEqual(result.reason_codes, ["RUN_ATTEMPT_MISMATCH"]);
  assert.equal(result.jobs_verified, 1);
});

test("spec §12.3 sample C: wrong source SHA -> UNBOUND + SOURCE_SHA_MISMATCH", () => {
  const { proc, result } = runCli("a1-wrong-source-sha");
  assert.equal(result.status, "UNBOUND");
  assert.deepEqual(result.reason_codes, ["SOURCE_SHA_MISMATCH"]);
  assert.deepEqual(result.identity_mismatches, [{
    job_id: "unit-linux-py312",
    field: "git.head_sha",
    expected: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    actual: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  }]);
});

test("JUnit minimal parser: valid, empty, malformed", () => {
  const valid = readFileSync(
    join(FIXTURES, "n02-two-job-pr-head", "evidence", "unit-linux-py312", "artifacts", "junit.xml"), "utf-8");
  assert.deepEqual(parseJUnitMinimal(valid), { tests: 10, failures: 0, errors: 0, skipped: 0 });
  const empty = readFileSync(
    join(FIXTURES, "g2-junit-empty", "evidence", "unit-linux-py312", "artifacts", "junit.xml"), "utf-8");
  assert.deepEqual(parseJUnitMinimal(empty), { tests: 0, failures: 0, errors: 0, skipped: 0 });
  const malformed = readFileSync(
    join(FIXTURES, "g3-junit-malformed", "evidence", "unit-linux-py312", "artifacts", "junit.xml"), "utf-8");
  assert.equal(parseJUnitMinimal(malformed), null);
});

test("invalid policy -> INVALID result, no crash", () => {
  const result = evaluate({ schema_version: 99 }, "a".repeat(40), join(FIXTURES, "n02-two-job-pr-head", "evidence"));
  assert.equal(result.status, "INVALID");
  assert.deepEqual(result.reason_codes, ["INVALID_POLICY"]);
});

test("missing evidence directory -> INVALID, not PASS", () => {
  const { policy, expectedSha } = loadFixture("n02-two-job-pr-head");
  const result = evaluate(policy, expectedSha, join(FIXTURES, "does-not-exist"));
  assert.equal(result.status, "INVALID");
  assert.deepEqual(result.reason_codes, ["INVALID_EVIDENCE"]);
  assert.equal(result.jobs_verified, 0);
});

// ---------------------------------------------------------------------------
// FIX-R13b helpers: build a 1-job evidence dir from the n02 fixture.
// ---------------------------------------------------------------------------

function sha256Hex(data) {
  return createHash("sha256").update(data).digest("hex");
}

function junitXml(nTests = 10, nFail = 0, nErr = 0, nSkip = 0, testsAttr = null, extra = "") {
  const cases = [];
  for (let i = 0; i < nTests; i += 1) {
    let inner = "";
    if (i < nFail) inner = '<failure message="x">t</failure>';
    else if (i < nFail + nErr) inner = '<error message="x">t</error>';
    else if (i < nFail + nErr + nSkip) inner = "<skipped/>";
    cases.push(`<testcase classname="t" name="test_${i}">${inner}</testcase>`);
  }
  const ta = testsAttr === null ? nTests : testsAttr;
  return `<?xml version="1.0"?>\n<testsuite name="s" tests="${ta}" failures="${nFail}" errors="${nErr}" skipped="${nSkip}">${extra}${cases.join("")}</testsuite>\n`;
}

function baseEvidence(t) {
  const dir = mkdtempSync(join(tmpdir(), "r13b-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const ev = join(dir, "evidence");
  cpSync(join(FIXTURES, "n02-two-job-pr-head", "evidence"), ev, { recursive: true });
  rmSync(join(ev, "unit-windows-py312"), { recursive: true, force: true });
  const policy = parsePolicyToml(readFileSync(join(FIXTURES, "n02-two-job-pr-head", "policy.toml"), "utf-8"));
  policy.required_jobs = ["unit-linux-py312"];
  const expectedSha = JSON.parse(readFileSync(join(FIXTURES, "n02-two-job-pr-head", "expected.json"), "utf-8")).expected_source_sha;
  return { dir, ev, policy, expectedSha };
}

function writePolicyToml(dir, policy) {
  const lines = ["schema_version = 1", `source_mode = "${policy.source_mode}"`,
    `expected_workflow = "${policy.expected_workflow}"`,
    "required_jobs = [", policy.required_jobs.map((j) => `"${j}"`).join(", "), "]",
    `min_tests = ${policy.min_tests}`,
    `require_clean_source_after = ${policy.require_clean_source_after}`,
    `same_tree_across_jobs = ${policy.same_tree_across_jobs}`,
    `same_run_id = ${policy.same_run_id}`,
    `same_run_attempt = ${policy.same_run_attempt}`,
    "", "[reports]", `junit = "${policy.reports.junit}"`,
    `lcov = "${policy.reports.lcov}"`, "", "[security]",
    "store_stdout = false", "store_stderr = false", "store_full_environment = false"];
  const p = join(dir, "policy.toml");
  writeFileSync(p, `${lines.join("\n")}\n`, "utf-8");
  return p;
}

function patchReceipt(ev, job, fn) {
  const p = join(ev, job, "receipt.json");
  const rec = JSON.parse(readFileSync(p, "utf-8"));
  fn(rec);
  writeFileSync(p, `${JSON.stringify(rec, null, 2)}\n`, "utf-8");
  return rec;
}

function setJunit(ev, job, data, summary) {
  const jd = join(ev, job);
  writeFileSync(join(jd, "artifacts", "junit.xml"), data);
  patchReceipt(ev, job, (rec) => {
    rec.reports[0].size_bytes = Buffer.byteLength(data);
    rec.reports[0].sha256 = sha256Hex(data);
    if (summary) rec.junit = summary;
  });
}

function runOracleCli(policyPath, sha, evidence, extraArgs = []) {
  const proc = spawnSync(process.execPath,
    [join(HERE, "verify.mjs"), "--policy", policyPath,
     "--expected-source-sha", sha, "--evidence", evidence, ...extraArgs],
    { encoding: "utf-8" });
  let result = null;
  try { result = JSON.parse(proc.stdout); } catch { /* no JSON on usage errors */ }
  return { proc, result };
}

// ---------------------------------------------------------------------------
// FIX-R13b F-07: TOML parser.
// ---------------------------------------------------------------------------

test("F-07 TOML: duplicate keys are rejected", () => {
  const dup = 'schema_version = 1\nmin_tests = 5\nmin_tests = 0\n';
  assert.throws(() => parseToml(dup), /duplicate key/);
  const dupSection = '[reports]\njunit = "required"\n[reports]\nlcov = "optional"\n';
  assert.throws(() => parseToml(dupSection), /duplicate section/);
  const dupDotted = 'a.b = 1\na.b = 2\n';
  assert.throws(() => parseToml(dupDotted), /duplicate key/);
  const dupInSection = '[reports]\njunit = "required"\njunit = "optional"\n';
  assert.throws(() => parseToml(dupInSection), /duplicate key/);
});

test("F-07 TOML: trailing comments and string escapes match tomllib", () => {
  const text = 'min_tests = 1  # trailing comment\n'
    + 'expected_workflow = "CI\\"X" # another comment\n'
    + "literal = 'a#b not a comment'\n";
  const p = parseToml(text);
  assert.equal(p.min_tests, 1);
  assert.equal(p.expected_workflow, 'CI"X');
  assert.equal(p.literal, "a#b not a comment");
  assert.equal(parseToml('min_tests = 1_000\n').min_tests, 1000);
  assert.equal(parseToml('min_tests = 0x10\n').min_tests, 16);
  assert.deepEqual(parseToml('required_jobs = [\n  "a", # comment\n  "b",\n]\n').required_jobs, ["a", "b"]);
  assert.deepEqual(parseToml('reports = { junit = "required", lcov = "optional" }\n').reports,
    { junit: "required", lcov: "optional" });
  assert.throws(() => parseToml('x = "bad \\q escape"\n'), /invalid escape/);
});

// ---------------------------------------------------------------------------
// FIX-R13b F-02: LCOV parser.
// ---------------------------------------------------------------------------

test("F-02 LCOV: valid fixture parses; malformed inputs throw", () => {
  const good = readFileSync(
    join(FIXTURES, "n08-lcov-only", "evidence", "unit-linux-py312", "artifacts", "lcov.info"), "utf-8");
  assert.deepEqual(
    { files: parseLcov(good).files, lines_found: parseLcov(good).lines_found, lines_hit: parseLcov(good).lines_hit },
    { files: 1, lines_found: 2, lines_hit: 1 });
  assert.throws(() => parseLcov("TN:\nSF:src/foo.py\nDA:1,1\nBADTAG:zzz\nend_of_record\n"), /unknown line tag/);
  assert.throws(() => parseLcov("TN:\nSF:src/foo.py\nDA:1,1\n"), /not closed/);
  assert.throws(() => parseLcov("end_of_record\n"), /no open record/);
  assert.throws(() => parseLcov(""), /no records/);
  assert.throws(() => parseLcov("TN:\nSF:/abs/foo.py\nDA:1,1\nend_of_record\n"), /absolute/);
  assert.throws(() => parseLcov("TN:\nSF:src/../foo.py\nDA:1,1\nend_of_record\n"), /escapes/);
  assert.throws(() => parseLcov("TN:\nSF:src/foo.py\nDA:1,1\nDA:1,0\nend_of_record\n"), /duplicate DA/);
  assert.throws(() => parseLcov("TN:\nSF:src/foo.py\nDA:1,1\nLF:9\nend_of_record\n"), /LF summary/);
  assert.throws(() => parseLcov("TN:\nDA:1,1\nend_of_record\n"), /DA before SF/);
  assert.throws(() => parseLcov(Buffer.from("TN:\nSF:src/foo.py\nDA:1,1\nend_of_record\n\x00")), /NUL/);
});

test("F-02 evaluate: malformed LCOV is INVALID/LCOV_MALFORMED; valid LCOV passes", (t) => {
  const { ev, policy, expectedSha } = baseEvidence(t);
  policy.reports.lcov = "required";
  const jd = join(ev, "unit-linux-py312");
  const bad = Buffer.from("TN:\nSF:src/foo.py\nDA:1,1\nBADTAG:zzz\nend_of_record\n", "utf-8");
  writeFileSync(join(jd, "artifacts", "lcov.info"), bad);
  patchReceipt(ev, "unit-linux-py312", (rec) => {
    rec.reports.push({ kind: "lcov", path: "artifacts/lcov.info", size_bytes: bad.length, sha256: sha256Hex(bad) });
  });
  const r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "INVALID");
  assert.deepEqual(r.reason_codes, ["LCOV_MALFORMED"]);
  assert.equal(r.jobs_verified, 0);

  const good = readFileSync(join(FIXTURES, "n08-lcov-only", "evidence", "unit-linux-py312", "artifacts", "lcov.info"));
  writeFileSync(join(jd, "artifacts", "lcov.info"), good);
  patchReceipt(ev, "unit-linux-py312", (rec) => {
    const rep = rec.reports.find((x) => x.kind === "lcov");
    rep.size_bytes = good.length;
    rep.sha256 = sha256Hex(good);
  });
  const r2 = evaluate(policy, expectedSha, ev);
  assert.equal(r2.status, "BOUND_PASS");
  assert.equal(r2.jobs_verified, 1);
});

// ---------------------------------------------------------------------------
// FIX-R13b F-03/F-04: JUnit XML parser.
// ---------------------------------------------------------------------------

test("F-04 JUnit parser: CDATA/comments/namespaces/self-closing, malformed rejected", () => {
  assert.deepEqual(parseJUnitMinimal(junitXml(10, 0, 0, 0, null, "<testcase classname=\"t\" name=\"c\"><![CDATA[<failure/>]]></testcase>")), null,
    "extra CDATA testcase makes 11 tests vs tests=10 attr, so the attribute check rejects it");
  const cdata10 = '<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="0" errors="0" skipped="0">'
    + Array.from({ length: 9 }, (_, i) => `<testcase classname="t" name="test_${i}"></testcase>`).join("")
    + '<testcase classname="t" name="test_9"><![CDATA[<failure/>]]></testcase></testsuite>\n';
  assert.deepEqual(parseJUnitMinimal(cdata10), { tests: 10, failures: 0, errors: 0, skipped: 0 });
  const comment10 = junitXml(10, 0, 0, 0, null, "<!-- <failure> -->");
  assert.deepEqual(parseJUnitMinimal(comment10), { tests: 10, failures: 0, errors: 0, skipped: 0 });
  assert.deepEqual(parseJUnitMinimal(
    '<?xml version="1.0"?>\n<testsuite name="s" tests="1" failures="0" errors="0" skipped="0"><testcase/></testsuite>\n'),
    { tests: 1, failures: 0, errors: 0, skipped: 0 });
  assert.deepEqual(parseJUnitMinimal(
    '<testsuite xmlns:x="urn:x" tests="1"><x:testcase><x:failure/></x:testcase></testsuite>'),
    { tests: 1, failures: 1, errors: 0, skipped: 0 });
  assert.equal(parseJUnitMinimal(
    '<?xml version="1.0"?>\n<!DOCTYPE testsuite [<!ENTITY x "y">]>\n<testsuite tests="1"><testcase/></testsuite>\n'), null);
  assert.equal(parseJUnitMinimal('<testsuite tests="1"><testcase></testsuite>'), null);
  assert.equal(parseJUnitMinimal('<testsuite tests="1"><testcase></testcases></testsuite>'), null);
  assert.equal(parseJUnitMinimal('<testsuite tests="1"><testcase name="a" name="b"/></testsuite>'), null);
  assert.equal(parseJUnitMinimal('<testsuite tests="1"><x:testcase/></testsuite>'), null);
  assert.equal(parseJUnitMinimal('<testsuite tests="1"><testcase/></testsuite> trailing'), null);
  assert.equal(parseJUnitMinimal('<wrong tests="1"><testcase/></wrong>'), null);
  assert.equal(parseJUnitMinimal('this is not xml at all'), null);
  assert.equal(parseJUnitMinimal(junitXml(10, 0, 0, 0, 999)), null);
  assert.deepEqual(parseJUnitMinimal(
    '<testsuites tests="2" failures="0" errors="0" skipped="0"><testsuite tests="1"><testcase/></testsuite><testsuite tests="1"><testcase/></testsuite></testsuites>'),
    { tests: 2, failures: 0, errors: 0, skipped: 0 });
  assert.equal(parseJUnitMinimal(
    '<testsuites tests="99"><testsuite tests="1"><testcase/></testsuite></testsuites>'), null);
  // Nested testsuite attributes are not checked (production P2-10):
  // its testcases count, its own tests="99" is ignored.
  assert.deepEqual(parseJUnitMinimal(
    '<testsuite tests="1" failures="0" errors="0" skipped="0"><testsuite tests="99" failures="99"><testcase/></testsuite></testsuite>'),
    { tests: 1, failures: 0, errors: 0, skipped: 0 });
});

test("F-03/F-04 evaluate: attr mismatch malformed; CDATA/comment pass; self-closing failure fails", (t) => {
  const { ev, policy, expectedSha } = baseEvidence(t);
  setJunit(ev, "unit-linux-py312", junitXml(10, 0, 0, 0, 999));
  let r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "INVALID");
  assert.deepEqual(r.reason_codes, ["JUNIT_MALFORMED"]);

  const { ev: ev2, policy: pol2, expectedSha: sha2 } = baseEvidence(t);
  setJunit(ev2, "unit-linux-py312", junitXml(10, 0, 0, 0, null, "<!-- <failure> -->"));
  r = evaluate(pol2, sha2, ev2);
  assert.equal(r.status, "BOUND_PASS");

  const { ev: ev3, policy: pol3, expectedSha: sha3 } = baseEvidence(t);
  const cases = Array.from({ length: 9 }, (_, i) => `<testcase classname="t" name="test_${i}"></testcase>`).join("")
    + '<testcase classname="t" name="test_9"><failure/></testcase>';
  setJunit(ev3, "unit-linux-py312",
    `<?xml version="1.0"?>\n<testsuite name="s" tests="10" failures="1" errors="0" skipped="0">${cases}</testsuite>\n`,
    { tests: 10, failures: 1, errors: 0, skipped: 0 });
  r = evaluate(pol3, sha3, ev3);
  assert.equal(r.status, "BOUND_FAIL");
  assert.deepEqual(r.reason_codes, ["EXIT_CODE_MISMATCH", "JUNIT_FAILED"]);
});

// ---------------------------------------------------------------------------
// FIX-R13b F-05: symlink-resolving containment.
// ---------------------------------------------------------------------------

test("F-05 evaluate: symlinked report escaping the job dir is REPORT_HASH_MISMATCH", (t) => {
  const { dir, ev, policy, expectedSha } = baseEvidence(t);
  const jd = join(ev, "unit-linux-py312");
  const outside = join(dir, "outside.xml");
  const good = junitXml(10);
  writeFileSync(outside, good);
  const target = join(jd, "artifacts", "junit.xml");
  rmSync(target, { force: true });
  symlinkSync(outside, target);
  patchReceipt(ev, "unit-linux-py312", (rec) => {
    rec.reports[0].size_bytes = Buffer.byteLength(good);
    rec.reports[0].sha256 = sha256Hex(good);
  });
  const r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "INVALID");
  assert.deepEqual(r.reason_codes, ["REPORT_HASH_MISMATCH"]);
  assert.equal(r.jobs_verified, 0);
});

test("F-05 evaluate: symlink staying inside the job dir still verifies", (t) => {
  const { ev, policy, expectedSha } = baseEvidence(t);
  const jd = join(ev, "unit-linux-py312");
  const real = join(jd, "artifacts", "junit-real.xml");
  const good = junitXml(10);
  writeFileSync(real, good);
  const target = join(jd, "artifacts", "junit.xml");
  rmSync(target, { force: true });
  symlinkSync(real, target);
  patchReceipt(ev, "unit-linux-py312", (rec) => {
    rec.reports[0].size_bytes = Buffer.byteLength(good);
    rec.reports[0].sha256 = sha256Hex(good);
  });
  const r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "BOUND_PASS");
  assert.equal(r.jobs_verified, 1);
});

test("F-05 resolveRealPath follows symlinks and dangling targets", (t) => {
  const { dir } = baseEvidence(t);
  const real = join(dir, "real.txt");
  writeFileSync(real, "x");
  const link = join(dir, "link.txt");
  symlinkSync(real, link);
  assert.equal(resolveRealPath(link), real);
  const dangling = join(dir, "dangling.txt");
  symlinkSync(join(dir, "no-such.txt"), dangling);
  assert.equal(resolveRealPath(dangling), join(dir, "no-such.txt"));
});

// ---------------------------------------------------------------------------
// FIX-R13b F-06: run.v1 / policy.v1 schema validation.
// ---------------------------------------------------------------------------

test("F-06 evaluate: schema-invalid receipts are INVALID_RECEIPT", (t) => {
  const cases = [
    ["run_attempt 200000 + extra field", (rec) => { rec.ci.run_attempt = 200000; rec.extra_forged_field = "BOUND_PASS"; }, ["INVALID_RECEIPT"]],
    // An invalid receipt still counts as present under its own job
    // id, so a forged job_id also trips the matrix comparison —
    // exactly as production does (invalid receipts are present,
    // never missing, never verified).
    ["job_id with a space", (rec) => { rec.job_id = "bad job"; }, ["INVALID_RECEIPT", "MATRIX_MISSING_JOB", "MATRIX_UNEXPECTED_JOB"]],
    ["empty matrix", (rec) => { rec.matrix = {}; }, ["INVALID_RECEIPT"]],
    ["matrix value is an object", (rec) => { rec.matrix.os = { nested: true }; }, ["INVALID_RECEIPT"]],
    ["extra git field", (rec) => { rec.git.forged = true; }, ["INVALID_RECEIPT"]],
    ["bad provider enum", (rec) => { rec.ci.provider = "jenkins"; }, ["INVALID_RECEIPT"]],
    ["run_id too long", (rec) => { rec.ci.run_id = "x".repeat(65); }, ["INVALID_RECEIPT"]],
    ["display too long", (rec) => { rec.command.display = "x".repeat(513); }, ["INVALID_RECEIPT"]],
    ["size_bytes over 1 GiB", (rec) => { rec.reports[0].size_bytes = 1073741825; }, ["INVALID_RECEIPT"]],
    ["junit tests over max", (rec) => { rec.junit.tests = 100000001; }, ["INVALID_RECEIPT"]],
    ["report path with ..", (rec) => { rec.reports[0].path = "artifacts/../junit.xml"; }, ["INVALID_RECEIPT"]],
    ["missing runner.python", (rec) => { delete rec.runner.python; }, ["INVALID_RECEIPT"]],
    ["extra junit field", (rec) => { rec.junit.forged = 1; }, ["INVALID_RECEIPT"]],
    ["source_state extra field", (rec) => { rec.source_state_before.extra = 1; }, ["INVALID_RECEIPT"]],
    ["bad started_at", (rec) => { rec.started_at = "not-a-time"; }, ["INVALID_RECEIPT"]],
  ];
  for (const [name, mutate, expected] of cases) {
    const { ev, policy, expectedSha } = baseEvidence(t);
    patchReceipt(ev, "unit-linux-py312", mutate);
    const r = evaluate(policy, expectedSha, ev);
    assert.equal(r.status, "INVALID", name);
    assert.deepEqual(r.reason_codes, expected, name);
    assert.equal(r.jobs_verified, 0, name);
  }
});

test("F-06 evaluate: schema-invalid policies are INVALID_POLICY", (t) => {
  const { ev, expectedSha } = baseEvidence(t);
  const bad = [
    [{ ...baseEvidence(t).policy, required_jobs: [123] }, "required_jobs entry not a string"],
    [{ ...baseEvidence(t).policy, extra_key: 1 }, "extra top-level field"],
    [{ ...baseEvidence(t).policy, min_tests: -1 }, "min_tests below minimum"],
    [{ ...baseEvidence(t).policy, min_tests: true }, "min_tests is a bool, not an int"],
    [{ ...baseEvidence(t).policy, reports: { junit: "required", lcov: "optional", extra: "required" } }, "extra reports field"],
  ];
  for (const [policy, name] of bad) {
    const r = evaluate(policy, expectedSha, ev);
    assert.equal(r.status, "INVALID", name);
    assert.deepEqual(r.reason_codes, ["INVALID_POLICY"], name);
  }
});

// ---------------------------------------------------------------------------
// FIX-R13b F-01 mirror: every JUnit report is judged.
// ---------------------------------------------------------------------------

test("F-01 mirror evaluate: multi-JUnit gives the identical triple in both orders", (t) => {
  const build = (t2, failFirst) => {
    const { ev, policy, expectedSha } = baseEvidence(t2);
    const jd = join(ev, "unit-linux-py312");
    const failXml = junitXml(10, 2);
    const passXml = junitXml(10);
    writeFileSync(join(jd, "artifacts", "junit-fail.xml"), failXml);
    writeFileSync(join(jd, "artifacts", "junit.xml"), passXml);
    const failRep = { kind: "junit", path: "artifacts/junit-fail.xml", size_bytes: Buffer.byteLength(failXml), sha256: sha256Hex(failXml) };
    const passRep = { kind: "junit", path: "artifacts/junit.xml", size_bytes: Buffer.byteLength(passXml), sha256: sha256Hex(passXml) };
    patchReceipt(ev, "unit-linux-py312", (rec) => {
      rec.reports = failFirst ? [failRep, passRep] : [passRep, failRep];
      rec.junit = { tests: 10, failures: 0, errors: 0, skipped: 0 };
    });
    return { ev, policy, expectedSha };
  };
  const a = build(t, true);
  const b = build(t, false);
  const ra = evaluate(a.policy, a.expectedSha, a.ev);
  const rb = evaluate(b.policy, b.expectedSha, b.ev);
  assert.deepEqual(ra.reason_codes, ["EXIT_CODE_MISMATCH", "JUNIT_FAILED", "JUNIT_SUMMARY_MISMATCH"]);
  assert.deepEqual(rb.reason_codes, ["EXIT_CODE_MISMATCH", "JUNIT_FAILED", "JUNIT_SUMMARY_MISMATCH"]);
  assert.equal(ra.status, "INVALID");
  assert.equal(rb.status, "INVALID");
  assert.equal(ra.jobs_verified, 0);
  assert.equal(rb.jobs_verified, 0);
  // Same per-report findings in both orders (sorted by path).
  assert.deepEqual(ra.report_errors, rb.report_errors);

  const { ev, policy, expectedSha } = baseEvidence(t);
  const r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "BOUND_PASS");
  assert.equal(r.jobs_verified, 1);
});

// ---------------------------------------------------------------------------
// FIX-R13b F-08: --expected-run-id / --expected-attempt pins.
// ---------------------------------------------------------------------------

test("F-08 CLI: pinned wrong run is UNBOUND with both codes; correct pin passes", (t) => {
  const { dir, ev, policy, expectedSha } = baseEvidence(t);
  const pp = writePolicyToml(dir, policy);
  let run = runOracleCli(pp, expectedSha, ev, ["--expected-run-id", "WRONG-RUN", "--expected-attempt", "99"]);
  assert.equal(run.proc.status, 2);
  assert.equal(run.result.status, "UNBOUND");
  assert.deepEqual(run.result.reason_codes, ["RUN_ATTEMPT_MISMATCH", "RUN_ID_MISMATCH"]);
  assert.equal(run.result.jobs_verified, 0);
  run = runOracleCli(pp, expectedSha, ev, ["--expected-run-id", "9001", "--expected-attempt", "2"]);
  assert.equal(run.proc.status, 0);
  assert.equal(run.result.status, "BOUND_PASS");
  run = runOracleCli(pp, expectedSha, ev, ["--expected-run-id", "9001"]);
  assert.equal(run.result.status, "BOUND_PASS");
  run = runOracleCli(pp, expectedSha, ev, ["--expected-attempt", "99"]);
  assert.equal(run.result.status, "UNBOUND");
  assert.deepEqual(run.result.reason_codes, ["RUN_ATTEMPT_MISMATCH"]);
  // = form works too.
  run = runOracleCli(pp, expectedSha, ev, ["--expected-run-id=WRONG-RUN"]);
  assert.equal(run.result.status, "UNBOUND");
  assert.deepEqual(run.result.reason_codes, ["RUN_ID_MISMATCH"]);
});

test("F-08 CLI: invalid pins and SHAs are usage errors (exit 3, no result JSON)", (t) => {
  const { dir, ev, policy, expectedSha } = baseEvidence(t);
  const pp = writePolicyToml(dir, policy);
  for (const extra of [["--expected-attempt", "0"], ["--expected-attempt", "100001"],
    ["--expected-attempt", "abc"], ["--expected-run-id", ""]]) {
    const run = runOracleCli(pp, expectedSha, ev, extra);
    assert.equal(run.proc.status, 3, JSON.stringify(extra));
    assert.equal(run.result, null, JSON.stringify(extra));
    assert.match(run.proc.stderr, /expected-/);
  }
  let run = runOracleCli(pp, expectedSha, ev, []);
  assert.equal(run.proc.status, 0);
  run = spawnSync(process.execPath,
    [join(HERE, "verify.mjs"), "--policy", pp, "--evidence", ev], { encoding: "utf-8" });
  assert.equal(run.status, 3);
  assert.match(run.stderr, /expected-source-sha is required/);
  run = runOracleCli(pp, "not-a-sha", ev);
  assert.equal(run.proc.status, 3);
  assert.match(run.proc.stderr, /40-character lowercase hex/);
});

test("F-08 evaluate: invalid pin values are an INTERNAL_ERROR result, like production", (t) => {
  const { ev, policy, expectedSha } = baseEvidence(t);
  let r = evaluate(policy, expectedSha, ev, { expectedRunId: "", expectedAttempt: undefined });
  assert.equal(r.status, "INTERNAL_ERROR");
  assert.deepEqual(r.reason_codes, ["INTERNAL_ERROR"]);
  r = evaluate(policy, expectedSha, ev, { expectedAttempt: 0 });
  assert.equal(r.status, "INTERNAL_ERROR");
  r = evaluate(policy, expectedSha, ev, { expectedRunId: "WRONG-RUN", expectedAttempt: 99 });
  assert.equal(r.status, "UNBOUND");
  assert.deepEqual(r.reason_codes, ["RUN_ATTEMPT_MISMATCH", "RUN_ID_MISMATCH"]);
});

test("F-05 evaluate: symlinked receipt.json escaping the job dir is INVALID_RECEIPT", (t) => {
  const { dir, ev, policy, expectedSha } = baseEvidence(t);
  const jd = join(ev, "unit-linux-py312");
  const outside = join(dir, "outside-receipt.json");
  const recText = readFileSync(join(jd, "receipt.json"), "utf-8");
  writeFileSync(outside, recText);
  rmSync(join(jd, "receipt.json"), { force: true });
  symlinkSync(outside, join(jd, "receipt.json"));
  const r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "INVALID");
  assert.deepEqual(r.reason_codes, ["INVALID_RECEIPT"]);
  assert.equal(r.jobs_verified, 0);
});

// ---------------------------------------------------------------------------
// FIX-R1 (ADR-007, spec v1.2.0): both after fields absent fails closed.
// ---------------------------------------------------------------------------

test("FIX-R1 (ADR-007): both after fields absent fails closed with MISSING_FIELD", (t) => {
  const { dir, ev, policy, expectedSha } = baseEvidence(t);
  // Control first: the unmodified copy still passes.
  let r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "BOUND_PASS");
  // Delete both after fields (the R1 false-PASS shape).
  patchReceipt(ev, "unit-linux-py312", (rec) => {
    delete rec.git.head_sha_after;
    delete rec.git.tree_sha_after;
  });
  r = evaluate(policy, expectedSha, ev);
  assert.equal(r.status, "UNBOUND");
  assert.deepEqual(r.reason_codes, ["MISSING_FIELD"]);
  assert.deepEqual(r.report_errors, [{
    code: "MISSING_FIELD",
    message: "missing git.head_sha_after and git.tree_sha_after",
    job_id: "unit-linux-py312",
  }]);
  assert.equal(r.jobs_verified, 0);
  // Same verdict via the CLI (exit 2).
  const run = runOracleCli(writePolicyToml(dir, policy), expectedSha, ev);
  assert.equal(run.proc.status, 2);
  assert.equal(run.result.status, "UNBOUND");
  assert.deepEqual(run.result.reason_codes, ["MISSING_FIELD"]);
});

test("FIX-R1 (ADR-007): e7 legacy fixture is UNBOUND + MISSING_FIELD via evaluate() and CLI", () => {
  const { dir, policy, expectedSha } = loadFixture("e7-legacy-clean-checkout");
  const r = evaluate(policy, expectedSha, join(dir, "evidence"));
  assert.equal(r.status, "UNBOUND");
  assert.deepEqual(r.reason_codes, ["MISSING_FIELD"]);
  assert.equal(r.jobs_verified, 0);
  const { proc, result } = runCli("e7-legacy-clean-checkout");
  assert.equal(proc.status, 2);
  assert.equal(result.status, "UNBOUND");
  assert.deepEqual(result.reason_codes, ["MISSING_FIELD"]);
});
