#!/usr/bin/env node
/**
 * Independent Node.js Oracle for P027 BenchReceipt (P027-T004).
 *
 * Implements PROJECT_BOOK §5 (matrix, identity, report integrity,
 * source-mutation, four-state aggregation) from the spec alone, in
 * Node.js 24 ESM. It does NOT import, call, or copy any Python
 * production module: the TOML parser, receipt checks, JUnit/LCOV
 * parsing, SHA-256 recomputation and status aggregation below are
 * written independently, sharing only the fixture files and the frozen
 * reason-code list (02_source/docs/REASON_CODES.md).
 *
 * FIX-R13b: the Oracle now mirrors production on the T013 P1 classes
 * the old implementation diverged on — a dependency-free well-formed
 * XML parser for JUnit (DOCTYPE rejection, CDATA-as-text, comment
 * exclusion, namespaced local names, self-closing elements, count
 * attributes), a full LCOV parser, symlink-resolving path containment,
 * run.v1/policy.v1 schema validation, a tomllib-faithful TOML parser
 * (duplicate keys rejected, trailing comments and string escapes),
 * per-report judging of EVERY JUnit report (F-01 mirror), and the
 * --expected-run-id / --expected-attempt pins. Still zero npm deps,
 * Node built-ins only (node:crypto, node:fs, node:path).
 *
 * CLI contract (frozen for T005–T008, extended by FIX-R13b with the
 * two run-identity pins):
 *   node oracle/verify.mjs --policy <toml> --expected-source-sha <sha>
 *                            --evidence <dir>
 *                            [--expected-run-id <id>]
 *                            [--expected-attempt <n>]
 * Prints the benchreceipt.result/v1 JSON to stdout. Process exit code
 * follows §5.6: BOUND_PASS 0, BOUND_FAIL 1, UNBOUND 2, INVALID 3,
 * INTERNAL_ERROR 4. A missing/invalid --expected-source-sha or an
 * invalid run pin is a CLI usage error (exit 3, stderr only), the
 * same as the Python CLI.
 */

import { createHash } from "node:crypto";
import { lstatSync, readdirSync, readFileSync, readlinkSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const STATUS_ORDER = ["INTERNAL_ERROR", "INVALID", "UNBOUND", "BOUND_FAIL", "BOUND_PASS"];

const REASON_STATUS = {
  SOURCE_SHA_MISMATCH: "UNBOUND",
  SOURCE_MODE_MISMATCH: "UNBOUND",
  TREE_SHA_MISMATCH: "UNBOUND",
  RUN_ID_MISMATCH: "UNBOUND",
  RUN_ATTEMPT_MISMATCH: "UNBOUND",
  WORKFLOW_MISMATCH: "UNBOUND",
  MATRIX_MISSING_JOB: "UNBOUND",
  MATRIX_DUPLICATE_JOB: "UNBOUND",
  MATRIX_UNEXPECTED_JOB: "UNBOUND",
  SOURCE_MUTATED_DURING_RUN: "UNBOUND",
  REPORT_MISSING: "UNBOUND",
  MISSING_FIELD: "UNBOUND",
  REPORT_HASH_MISMATCH: "INVALID",
  JUNIT_MALFORMED: "INVALID",
  JUNIT_SUMMARY_MISMATCH: "INVALID",
  LCOV_MALFORMED: "INVALID",
  INVALID_RECEIPT: "INVALID",
  INVALID_POLICY: "INVALID",
  INVALID_EVIDENCE: "INVALID",
  JUNIT_FAILED: "BOUND_FAIL",
  JUNIT_EMPTY: "BOUND_FAIL",
  EXIT_CODE_MISMATCH: "BOUND_FAIL",
  POLICY_MISMATCH: "BOUND_FAIL",
  INTERNAL_ERROR: "INTERNAL_ERROR",
};

const EXIT_BY_STATUS = {
  BOUND_PASS: 0,
  BOUND_FAIL: 1,
  UNBOUND: 2,
  INVALID: 3,
  INTERNAL_ERROR: 4,
};

// ---------------------------------------------------------------------------
// TOML parser (FIX-R13b, F-07): the subset .benchreceipt.toml uses,
// parsed the way tomllib parses it.
//
// - Duplicate keys (including via dotted keys) and duplicate section
//   headers are parse errors (INVALID_POLICY), never last-wins.
// - Trailing comments are stripped outside strings; `#` inside a
//   quoted string is data.
// - Basic strings process escapes exactly as TOML does (\b \t \n \f
//   \r \" \\ \uXXXX \UXXXXXXXX, plus the line-ending backslash in
//   multi-line strings); literal strings take no escapes.
// - Integers accept TOML forms (decimal with underscores, 0x/0o/0b,
//   optional sign); floats, datetimes and bare words are rejected.
// - Arrays (single- and multi-line, comments inside, trailing comma)
//   and inline tables are supported. Dotted keys create implicit
//   tables, as in tomllib.
// Anything else is a parse error (policy INVALID, fail-closed).
// ---------------------------------------------------------------------------

const _BARE_KEY_RE = /^[A-Za-z0-9_-]+/;

function _hasOwn(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function _safeSet(obj, key, value) {
  if (key === "__proto__") {
    Object.defineProperty(obj, key, { value, enumerable: true, writable: true, configurable: true });
  } else {
    obj[key] = value;
  }
}

export function parseToml(text) {
  if (typeof text !== "string") throw new Error("invalid TOML: input must be text");
  const definedTables = new Set();
  const root = {};
  let pos = 0;
  const len = text.length;
  const err = (msg) => { throw new Error(`invalid TOML: ${msg} (offset ${pos})`); };

  function skipWsInline() {
    let n = 0;
    while (pos < len && (text[pos] === " " || text[pos] === "\t")) { pos += 1; n += 1; }
    return n;
  }

  function skipWsAndComments() {
    for (;;) {
      while (pos < len && (text[pos] === " " || text[pos] === "\t" || text[pos] === "\n" || text[pos] === "\r")) pos += 1;
      if (text[pos] === "#") {
        while (pos < len && text[pos] !== "\n") pos += 1;
        continue;
      }
      return;
    }
  }

  function parseBasicString() {
    // text[pos] === '"'.
    let multiline = false;
    if (text.startsWith('"""', pos)) {
      multiline = true;
      pos += 3;
      if (text[pos] === "\n") pos += 1;
      else if (text.startsWith("\r\n", pos)) pos += 2;
    } else {
      pos += 1;
    }
    let out = "";
    for (;;) {
      if (pos >= len) err("unterminated string");
      const ch = text[pos];
      if (!multiline && ch === '"') { pos += 1; return out; }
      if (multiline && text.startsWith('"""', pos)) { pos += 3; return out; }
      if (ch === "\r") {
        if (!multiline) err("bare CR in string");
        if (text[pos + 1] === "\n") { out += "\n"; pos += 2; continue; }
        err("bare CR in string");
      }
      if (ch === "\\") {
        if (multiline) {
          let j = pos + 1;
          while (j < len && (text[j] === " " || text[j] === "\t")) j += 1;
          if (text[j] === "\n" || text.startsWith("\r\n", j)) {
            pos = text[j] === "\n" ? j + 1 : j + 2;
            while (pos < len && (text[pos] === " " || text[pos] === "\t" || text[pos] === "\n" || text[pos] === "\r")) pos += 1;
            continue;
          }
        }
        const e = text[pos + 1];
        const simple = { b: "\b", t: "\t", n: "\n", f: "\f", r: "\r", '"': '"', "\\": "\\" };
        if (e !== undefined && Object.prototype.hasOwnProperty.call(simple, e)) {
          out += simple[e];
          pos += 2;
          continue;
        }
        if (e === "u" || e === "U") {
          const n = e === "u" ? 4 : 8;
          const hex = text.slice(pos + 2, pos + 2 + n);
          if (hex.length !== n || !/^[0-9a-fA-F]+$/.test(hex)) err("bad unicode escape");
          const cp = Number.parseInt(hex, 16);
          if (cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) err("bad unicode escape");
          out += String.fromCodePoint(cp);
          pos += 2 + n;
          continue;
        }
        err(`invalid escape \\${e}`);
      }
      if (!multiline && ch === "\n") err("newline in string");
      if (ch < " " && ch !== "\t" && ch !== "\n") err("control character in string");
      out += ch;
      pos += 1;
    }
  }

  function parseLiteralString() {
    // text[pos] === '\''.
    let multiline = false;
    if (text.startsWith("'''", pos)) {
      multiline = true;
      pos += 3;
      if (text[pos] === "\n") pos += 1;
      else if (text.startsWith("\r\n", pos)) pos += 2;
    } else {
      pos += 1;
    }
    let out = "";
    for (;;) {
      if (pos >= len) err("unterminated string");
      const ch = text[pos];
      if (!multiline && ch === "'") { pos += 1; return out; }
      if (multiline && text.startsWith("'''", pos)) { pos += 3; return out; }
      if (ch === "\r") {
        if (!multiline) err("bare CR in string");
        if (text[pos + 1] === "\n") { out += "\n"; pos += 2; continue; }
        err("bare CR in string");
      }
      if (!multiline && ch === "\n") err("newline in string");
      if (ch < " " && ch !== "\t" && ch !== "\n") err("control character in string");
      out += ch;
      pos += 1;
    }
  }

  function parseKey() {
    const parts = [];
    for (;;) {
      skipWsInline();
      let part;
      if (text[pos] === '"') part = parseBasicString();
      else if (text[pos] === "'") part = parseLiteralString();
      else {
        const m = _BARE_KEY_RE.exec(text.slice(pos));
        if (!m) err("expected a key");
        part = m[0];
        pos += part.length;
      }
      if (part === "") err("empty key");
      parts.push(part);
      skipWsInline();
      if (text[pos] === ".") { pos += 1; continue; }
      return parts;
    }
  }

  function parseTomlInteger(tok) {
    let s = tok;
    let sign = 1;
    if (s[0] === "+" || s[0] === "-") {
      if (s[0] === "-") sign = -1;
      s = s.slice(1);
    }
    if (s === "") err(`invalid integer ${tok}`);
    let radix = 10;
    let digits = s;
    if (s.startsWith("0x")) { radix = 16; digits = s.slice(2); }
    else if (s.startsWith("0o")) { radix = 8; digits = s.slice(2); }
    else if (s.startsWith("0b")) { radix = 2; digits = s.slice(2); }
    if (digits === "" || digits.startsWith("_") || digits.endsWith("_") || digits.includes("__")) {
      err(`invalid integer ${tok}`);
    }
    if (radix === 10 && digits.length > 1 && digits.startsWith("0")) err(`invalid integer ${tok}`);
    const ok = radix === 10 ? /^[0-9_]+$/
      : radix === 16 ? /^[0-9a-fA-F_]+$/
      : radix === 8 ? /^[0-7_]+$/
      : /^[01_]+$/;
    if (!ok.test(digits)) err(`invalid integer ${tok}`);
    const val = Number.parseInt(digits.replace(/_/g, ""), radix);
    if (!Number.isFinite(val)) err(`integer out of range ${tok}`);
    return sign * val;
  }

  function parseValue() {
    skipWsInline();
    const ch = text[pos];
    if (ch === '"') return parseBasicString();
    if (ch === "'") return parseLiteralString();
    if (ch === "[") return parseArray();
    if (ch === "{") return parseInlineTable();
    const m = /^[^\s,\]}#]+/.exec(text.slice(pos));
    if (!m) err("expected a value");
    const tok = m[0];
    pos += tok.length;
    if (tok === "true") return true;
    if (tok === "false") return false;
    return parseTomlInteger(tok);
  }

  function parseArray() {
    pos += 1; // consume '['
    const items = [];
    for (;;) {
      skipWsAndComments();
      if (text[pos] === "]") { pos += 1; return items; }
      if (pos >= len) err("unterminated array");
      items.push(parseValue());
      skipWsAndComments();
      if (text[pos] === ",") { pos += 1; continue; }
      if (text[pos] === "]") { pos += 1; return items; }
      err("expected ',' or ']' in array");
    }
  }

  function assignDotted(table, parts, value) {
    let cur = table;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const part = parts[i];
      if (!_hasOwn(cur, part)) {
        _safeSet(cur, part, {});
      } else if (typeof cur[part] !== "object" || cur[part] === null || Array.isArray(cur[part])) {
        err(`key ${parts.join(".")} conflicts with a value`);
      }
      cur = cur[part];
    }
    const leaf = parts[parts.length - 1];
    if (_hasOwn(cur, leaf)) err(`duplicate key ${parts.join(".")}`);
    _safeSet(cur, leaf, value);
  }

  function parseInlineTable() {
    pos += 1; // consume '{'
    const obj = {};
    skipWsInline();
    if (text[pos] === "}") { pos += 1; return obj; }
    for (;;) {
      const parts = parseKey();
      skipWsInline();
      if (text[pos] !== "=") err("expected '=' in inline table");
      pos += 1;
      assignDotted(obj, parts, parseValue());
      skipWsInline();
      if (text[pos] === ",") { pos += 1; skipWsInline(); continue; }
      if (text[pos] === "}") { pos += 1; return obj; }
      err("expected ',' or '}' in inline table");
    }
  }

  let current = root;
  skipWsAndComments();
  while (pos < len) {
    if (text[pos] === "[") {
      if (text.startsWith("[[", pos)) err("array-of-tables headers are not supported");
      pos += 1;
      const parts = parseKey();
      skipWsInline();
      if (text[pos] !== "]") err("expected ']' after section header");
      pos += 1;
      let table = root;
      for (let i = 0; i < parts.length; i += 1) {
        const part = parts[i];
        const last = i === parts.length - 1;
        if (!_hasOwn(table, part)) {
          _safeSet(table, part, {});
        } else if (typeof table[part] !== "object" || table[part] === null || Array.isArray(table[part])) {
          err(`section ${parts.join(".")} conflicts with a value`);
        }
        table = table[part];
        if (last) {
          if (definedTables.has(table)) err(`duplicate section [${parts.join(".")}]`);
          definedTables.add(table);
        }
      }
      current = table;
      skipWsInline();
      if (pos < len && text[pos] !== "#" && text[pos] !== "\n" && text[pos] !== "\r") {
        err("unexpected content after section header");
      }
    } else {
      const parts = parseKey();
      skipWsInline();
      if (text[pos] !== "=") err("expected '=' after key");
      pos += 1;
      assignDotted(current, parts, parseValue());
      skipWsInline();
      if (pos < len && text[pos] !== "#" && text[pos] !== "\n" && text[pos] !== "\r") {
        err("unexpected content after value");
      }
    }
    skipWsAndComments();
  }
  return root;
}

// The old entry point: the policy file is parsed by parseToml now that
// multi-line arrays are handled natively (no pre-joining needed).
export function parsePolicyToml(text) {
  return parseToml(text);
}

// ---------------------------------------------------------------------------
// Minimal well-formedness XML parser (FIX-R13b, F-03/F-04).
//
// Node has no stdlib XML parser, so this is a small dependency-free
// parser written for exactly what JUnit needs, mirroring
// xml.etree.ElementTree's acceptance/rejection behaviour:
//
// - Any <!DOCTYPE / <!ENTITY declaration is rejected before parsing
//   (byte-level pre-scan, as in production's _DOCTYPE_RE/_ENTITY_RE).
// - Mismatched, unclosed or duplicate elements, duplicate attributes,
//   stray text after the root, a wrong root element, and an unbound
//   namespace prefix are all malformed — never silently counted.
// - Comments are skipped, CDATA sections are text (their content is
//   never counted as markup), processing instructions are skipped.
// - Element/attribute names use local-name matching, so a namespaced
//   <x:testcase> counts exactly like <testcase>; self-closing
//   <testcase/> / <failure/> / <error/> / <skipped/> are counted.
// - A present tests/failures/errors/skipped attribute on a <testsuite>
//   (or on a <testsuites> wrapper) must equal the counted value for
//   that element, exactly as production's _check_count_attrs does.
//   Nested <testsuite> attributes are not checked (production P2-10:
//   it counts their elements but never reads their attributes).
// - Attribute values are entity-decoded with XML line/attribute
//   normalisation; a count attribute must be all digits and equal the
//   counted value. A >4300-digit count attribute is malformed
//   (fail-closed; production's int() raises ValueError there, P2-06).
// ---------------------------------------------------------------------------

const _DOCTYPE_RE = /<!doctype/i;
const _ENTITY_RE = /<!entity/i;
const _COUNT_ATTRS = ["tests", "failures", "errors", "skipped"];
const _XML_NAME_START = /[A-Za-z_:_\u0080-\uFFFF]/;
const _XML_NAME_CHAR = /[A-Za-z0-9_.:\u0080-\uFFFF-]/;
const _XML_NS_URI = "http://www.w3.org/XML/1998/namespace";

function _localName(qname) {
  const i = qname.lastIndexOf(":");
  return i === -1 ? qname : qname.slice(i + 1);
}

function _prefixOf(qname) {
  const i = qname.indexOf(":");
  return i === -1 ? null : qname.slice(0, i);
}

function _decodeXmlEntities(raw) {
  let out = "";
  let i = 0;
  while (i < raw.length) {
    const amp = raw.indexOf("&", i);
    if (amp === -1) { out += raw.slice(i); break; }
    out += raw.slice(i, amp);
    const semi = raw.indexOf(";", amp + 1);
    if (semi === -1) throw new Error("unterminated entity reference");
    const body = raw.slice(amp + 1, semi);
    if (body === "amp") out += "&";
    else if (body === "lt") out += "<";
    else if (body === "gt") out += ">";
    else if (body === "quot") out += '"';
    else if (body === "apos") out += "'";
    else if (body.startsWith("#x") || body.startsWith("#X")) {
      const hex = body.slice(2);
      if (!/^[0-9a-fA-F]+$/.test(hex)) throw new Error(`bad character reference &${body};`);
      const cp = Number.parseInt(hex, 16);
      out += _xmlChar(cp);
    } else if (body.startsWith("#")) {
      const dec = body.slice(1);
      if (!/^[0-9]+$/.test(dec)) throw new Error(`bad character reference &${body};`);
      out += _xmlChar(Number.parseInt(dec, 10));
    } else {
      throw new Error(`undefined entity &${body};`);
    }
    i = semi + 1;
  }
  return out;
}

function _xmlChar(cp) {
  if (cp === 0x9 || cp === 0xA || cp === 0xD
    || (cp >= 0x20 && cp <= 0xD7FF)
    || (cp >= 0xE000 && cp <= 0xFFFD)
    || (cp >= 0x10000 && cp <= 0x10FFFF)) {
    return String.fromCodePoint(cp);
  }
  throw new Error("character reference is not a valid XML character");
}

function _validateXmlText(chunk) {
  if (chunk.includes("]]>")) throw new Error("']]>' is not allowed in character data");
  for (let i = 0; i < chunk.length; i += 1) {
    const c = chunk.charCodeAt(i);
    if ((c < 0x20 && c !== 0x9 && c !== 0xA && c !== 0xD) || c === 0xFFFE || c === 0xFFFF) {
      throw new Error("control character in character data");
    }
  }
  // Any '&' must start a valid entity / character reference.
  let i = 0;
  while (i < chunk.length) {
    const amp = chunk.indexOf("&", i);
    if (amp === -1) break;
    const semi = chunk.indexOf(";", amp + 1);
    if (semi === -1) throw new Error("unterminated entity reference");
    const body = chunk.slice(amp + 1, semi);
    const ok = body === "amp" || body === "lt" || body === "gt" || body === "quot" || body === "apos"
      || /^#[0-9]+$/.test(body) || /^#[xX][0-9a-fA-F]+$/.test(body);
    if (!ok) throw new Error(`undefined entity &${body};`);
    if (body.startsWith("#")) {
      const cp = body[1] === "x" || body[1] === "X"
        ? Number.parseInt(body.slice(2), 16) : Number.parseInt(body.slice(1), 10);
      _xmlChar(cp);
    }
    i = semi + 1;
  }
}

function parseXmlDocument(text) {
  // XML line-ending normalisation (CR LF / CR -> LF), as expat does.
  const src = text.replace(/\r\n?/g, "\n");
  const len = src.length;
  let pos = 0;
  const err = (msg) => { throw new Error(`malformed XML: ${msg}`); };
  if (src.charCodeAt(0) === 0xFEFF) pos = 1;

  function skipWs() {
    while (pos < len && (src[pos] === " " || src[pos] === "\t" || src[pos] === "\n")) pos += 1;
  }

  function parseComment() {
    // src[pos..] starts with "<!--".
    const end = src.indexOf("-->", pos + 4);
    if (end === -1) err("unterminated comment");
    if (src.slice(pos + 4, end).includes("--")) err("'--' is not allowed inside a comment");
    pos = end + 3;
  }

  function parsePI() {
    // src[pos..] starts with "<?".
    const end = src.indexOf("?>", pos + 2);
    if (end === -1) err("unterminated processing instruction");
    const body = src.slice(pos + 2, end);
    const target = (body.trim().split(/\s+/)[0] || "");
    if (/^xml$/i.test(target)) err("reserved processing-instruction target 'xml'");
    pos = end + 2;
  }

  function parseCdata() {
    // src[pos..] starts with "<![CDATA["; content is plain text.
    const end = src.indexOf("]]>", pos + 9);
    if (end === -1) err("unterminated CDATA section");
    pos = end + 3;
  }

  // Skip whitespace, comments and PIs (prolog / epilog / between
  // elements). Any other "<!" markup is rejected here; a DOCTYPE was
  // already rejected by the pre-scan.
  function skipMisc() {
    for (;;) {
      skipWs();
      if (src.startsWith("<!--", pos)) { parseComment(); continue; }
      if (src.startsWith("<?", pos)) { parsePI(); continue; }
      if (src.startsWith("<!", pos)) err("unexpected markup declaration");
      return;
    }
  }

  function parseName() {
    if (pos >= len || !_XML_NAME_START.test(src[pos])) err(`expected a name at offset ${pos}`);
    let name = src[pos];
    pos += 1;
    while (pos < len && _XML_NAME_CHAR.test(src[pos])) { name += src[pos]; pos += 1; }
    if (name.indexOf(":") !== name.lastIndexOf(":")) err(`invalid qualified name ${name}`);
    return name;
  }

  // Parse one element starting at "<" (not "</", not "<!" ). Returns
  // { qname, attrs: [{qname, value}], children: [...] }.
  // parentScope is a Map prefix -> uri for the enclosing elements.
  function parseNode(parentScope) {
    pos += 1; // consume '<'
    const qname = parseName();
    const attrs = [];
    const seenQ = new Set();
    let selfClosing = false;
    for (;;) {
      const hadWs = skipWsCount();
      if (src.startsWith("/>", pos)) { pos += 2; selfClosing = true; break; }
      if (src[pos] === ">") { pos += 1; break; }
      if (pos >= len) err("unterminated start tag");
      if (hadWs === 0) err("whitespace required between attributes");
      const aname = parseName();
      if (seenQ.has(aname)) err(`duplicate attribute ${aname}`);
      seenQ.add(aname);
      skipWsCount();
      if (src[pos] !== "=") err(`attribute ${aname} has no value`);
      pos += 1;
      skipWsCount();
      const quote = src[pos];
      if (quote !== '"' && quote !== "'") err(`attribute ${aname} value must be quoted`);
      pos += 1;
      const end = src.indexOf(quote, pos);
      if (end === -1) err(`unterminated attribute ${aname} value`);
      const raw = src.slice(pos, end);
      if (raw.includes("<")) err(`'<' is not allowed in attribute ${aname} value`);
      // Attribute-value normalisation: tab / newline become a space
      // (after entity decoding, as in XML); control chars rejected.
      let value = _decodeXmlEntities(raw).replace(/[\t\n]/g, " ");
      for (let i = 0; i < value.length; i += 1) {
        const c = value.charCodeAt(i);
        if ((c < 0x20 && c !== 0x9 && c !== 0xA && c !== 0xD) || c === 0xFFFE || c === 0xFFFF) {
          err(`control character in attribute ${aname} value`);
        }
      }
      attrs.push({ qname: aname, value });
      pos = end + 1;
    }

    // Namespace scope for this element: parent bindings plus this
    // element's own xmlns declarations.
    const scope = new Map(parentScope);
    for (const a of attrs) {
      if (a.qname === "xmlns") scope.set("", a.value);
      else if (a.qname.startsWith("xmlns:")) {
        const prefix = a.qname.slice("xmlns:".length);
        if (prefix === "xmlns") err("the 'xmlns' prefix must not be declared");
        if (a.value === "") err(`prefix ${prefix} must not be undeclared`);
        if (prefix === "xml" && a.value !== _XML_NS_URI) err("the 'xml' prefix must bind to its standard namespace");
        scope.set(prefix, a.value);
      }
    }
    const prefix = _prefixOf(qname);
    if (prefix !== null) {
      if (prefix === "xmlns") err("the 'xmlns' prefix must not be used as an element prefix");
      if (prefix !== "xml" && !scope.has(prefix)) err(`unbound namespace prefix ${prefix}`);
    }
    const expanded = new Set();
    for (const a of attrs) {
      if (a.qname === "xmlns" || a.qname.startsWith("xmlns:")) continue;
      const ap = _prefixOf(a.qname);
      if (ap !== null) {
        if (ap === "xmlns") err("the 'xmlns' prefix must not be used as an attribute prefix");
        if (ap !== "xml" && !scope.has(ap)) err(`unbound namespace prefix ${ap}`);
      }
      const uri = ap === null ? "" : ap === "xml" ? _XML_NS_URI : scope.get(ap);
      const key = `${uri}\u0000${_localName(a.qname)}`;
      if (expanded.has(key)) err(`duplicate attribute ${_localName(a.qname)}`);
      expanded.add(key);
    }

    const node = { qname, attrs, children: [] };
    if (selfClosing) return node;
    for (;;) {
      if (pos >= len) err(`unclosed element <${qname}>`);
      if (src[pos] === "<") {
        if (src.startsWith("</", pos)) {
          pos += 2;
          const closeName = parseName();
          skipWsCount();
          if (src[pos] !== ">") err("expected '>' in close tag");
          pos += 1;
          if (closeName !== qname) err(`mismatched close tag </${closeName}> for <${qname}>`);
          return node;
        }
        if (src.startsWith("<!--", pos)) { parseComment(); continue; }
        if (src.startsWith("<![CDATA[", pos)) { parseCdata(); continue; }
        if (src.startsWith("<?", pos)) { parsePI(); continue; }
        if (src.startsWith("<!", pos)) err("unexpected markup declaration in content");
        node.children.push(parseNode(scope));
        continue;
      }
      const next = src.indexOf("<", pos);
      const chunk = src.slice(pos, next === -1 ? len : next);
      _validateXmlText(chunk);
      pos = next === -1 ? len : next;
    }
  }

  function skipWsCount() {
    let n = 0;
    while (pos < len && (src[pos] === " " || src[pos] === "\t" || src[pos] === "\n")) { pos += 1; n += 1; }
    return n;
  }

  // Prolog: an XML declaration, if present, must be first (no leading
  // whitespace before it) and carry a version.
  if (src.startsWith("<?xml", pos) && (src[pos + 5] === " " || src[pos + 5] === "\t" || src[pos + 5] === "\n" || src[pos + 5] === "?")) {
    const end = src.indexOf("?>", pos + 2);
    if (end === -1) err("unterminated XML declaration");
    if (!/\bversion\s*=/.test(src.slice(pos + 2, end))) err("XML declaration has no version");
    pos = end + 2;
  }
  skipMisc();
  if (pos >= len || src[pos] !== "<" || src.startsWith("</", pos) || src.startsWith("<!", pos)) {
    err("no root element");
  }
  const root = parseNode(new Map());
  skipMisc();
  if (pos !== len) err("junk after document element");
  return root;
}

function _countSuite(suite) {
  const counted = { tests: 0, failures: 0, errors: 0, skipped: 0 };
  const stack = [...suite.children];
  while (stack.length) {
    const node = stack.pop();
    const name = _localName(node.qname);
    if (name === "testcase") counted.tests += 1;
    else if (name === "failure") counted.failures += 1;
    else if (name === "error") counted.errors += 1;
    else if (name === "skipped") counted.skipped += 1;
    for (const child of node.children) stack.push(child);
  }
  return counted;
}

function _countAttrEquals(raw, countedValue) {
  if (!/^[0-9]+$/.test(raw)) throw new Error(`non-integer count attribute: ${JSON.stringify(raw)}`);
  if (raw.length > 4300) throw new Error("count attribute exceeds integer conversion limit");
  const norm = raw.replace(/^0+/, "") || "0";
  const want = String(countedValue);
  return norm === want;
}

function _checkCountAttrs(elem, counted, where) {
  for (const attr of _COUNT_ATTRS) {
    const found = elem.attrs.find((a) => a.qname === attr);
    if (!found) continue;
    if (!_countAttrEquals(found.value, counted[attr])) {
      throw new Error(`JUnit ${where} ${attr} attribute (${found.value}) does not match counted ${attr} (${counted[attr]})`);
    }
  }
}

function parseJUnitCounts(text) {
  if (typeof text !== "string") throw new Error("JUnit input must be text");
  if (_DOCTYPE_RE.test(text) || _ENTITY_RE.test(text)) {
    throw new Error("JUnit XML contains a DOCTYPE or ENTITY declaration; DTD processing is disabled");
  }
  const root = parseXmlDocument(text);
  const rootName = _localName(root.qname);
  let suites;
  if (rootName === "testsuite") {
    suites = [root];
  } else if (rootName === "testsuites") {
    suites = root.children.filter((c) => _localName(c.qname) === "testsuite");
    if (suites.length === 0) throw new Error("JUnit <testsuites> contains no <testsuite>");
  } else {
    throw new Error(`JUnit root element is <${rootName}>, not <testsuite>`);
  }
  const total = { tests: 0, failures: 0, errors: 0, skipped: 0 };
  for (const suite of suites) {
    const counted = _countSuite(suite);
    _checkCountAttrs(suite, counted, "<testsuite>");
    total.tests += counted.tests;
    total.failures += counted.failures;
    total.errors += counted.errors;
    total.skipped += counted.skipped;
  }
  if (rootName === "testsuites") _checkCountAttrs(root, total, "<testsuites>");
  return total;
}

// The exported JUnit entry point: counted summary, or null when the
// report cannot be trusted as parsed (malformed XML, DOCTYPE, wrong
// root, count-attribute mismatch). Kept signature-compatible with the
// T004 minimal parser so existing callers/tests keep working.
export function parseJUnitMinimal(text) {
  try {
    return parseJUnitCounts(text);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// LCOV parser (FIX-R13b, F-02): mirrors benchreceipt.reports.lcov
// parse_lcov semantics exactly — same tags, same record structure,
// same summary cross-checks, same SF path rules. Any malformed
// record/tag/value raises; the verifier maps that to LCOV_MALFORMED.
// ---------------------------------------------------------------------------

const MAX_LCOV_BYTES = 1073741824;
const _LCOV_TAGS = new Set(["TN", "SF", "FN", "FNDA", "FNF", "FNH", "BRDA", "BRF", "BRH", "DA", "LF", "LH"]);
const _LCOV_DRIVE_RE = /^[A-Za-z]:/;

function _lcovDigitsToNumber(s) {
  const t = s.replace(/^0+/, "");
  if (t === "") return 0;
  if (t.length > 15) return Number.POSITIVE_INFINITY;
  return Number(t);
}

function _validateLcovSfPath(sf) {
  const bad = (msg) => { throw new Error(`LCOV SF path ${msg}: ${JSON.stringify(sf)}`); };
  if (!sf) bad("is empty");
  if (sf.startsWith("/") || sf.startsWith("\\")) bad("is absolute");
  if (_LCOV_DRIVE_RE.test(sf)) bad("is absolute");
  if (sf.includes("\\")) bad("contains a backslash");
  if (sf.includes("//")) bad("contains '//'");
  if (sf.endsWith("/")) bad("ends with '/'");
  if (sf.split("/").includes("..")) bad("escapes its directory");
}

function _parseLcovRecord(lines, recordNo) {
  const fail = (msg) => { throw new Error(`LCOV record ${recordNo}: ${msg}`); };
  const isInt = (s) => /^[0-9]+$/.test(s);
  let tnSeen = false;
  let sf = null;
  let fnCount = 0;
  let fndaHits = 0;
  let fndaSeen = false;
  let brdaCount = 0;
  let brdaHits = 0;
  const da = new Map();
  const summaries = new Map();
  for (const raw of lines) {
    const colon = raw.indexOf(":");
    if (colon === -1) fail(`line has no tag: ${JSON.stringify(raw)}`);
    const tag = raw.slice(0, colon);
    const value = raw.slice(colon + 1);
    if (!_LCOV_TAGS.has(tag)) fail(`unknown line tag: ${JSON.stringify(tag)}`);
    if (tag === "TN") {
      if (tnSeen || sf !== null) fail("TN appears more than once or after SF");
      tnSeen = true;
    } else if (tag === "SF") {
      if (sf !== null) fail("duplicate SF in one record");
      _validateLcovSfPath(value);
      sf = value;
    } else if (tag === "FN") {
      if (sf === null) fail("FN before SF");
      const comma = value.indexOf(",");
      const lineNo = comma === -1 ? value : value.slice(0, comma);
      const name = comma === -1 ? "" : value.slice(comma + 1);
      if (comma === -1 || name === "" || !isInt(lineNo) || _lcovDigitsToNumber(lineNo) < 1) {
        fail(`malformed FN line: ${JSON.stringify(raw)}`);
      }
      fnCount += 1;
    } else if (tag === "FNDA") {
      if (sf === null) fail("FNDA before SF");
      const comma = value.indexOf(",");
      const hits = comma === -1 ? value : value.slice(0, comma);
      const name = comma === -1 ? "" : value.slice(comma + 1);
      if (comma === -1 || name === "" || !isInt(hits)) {
        fail(`malformed FNDA line: ${JSON.stringify(raw)}`);
      }
      fndaSeen = true;
      if (_lcovDigitsToNumber(hits) > 0) fndaHits += 1;
    } else if (tag === "BRDA") {
      if (sf === null) fail("BRDA before SF");
      const parts = value.split(",");
      if (parts.length !== 4) fail(`malformed BRDA line: ${JSON.stringify(raw)}`);
      const [lineNo, _block, _branch, taken] = parts;
      if (!isInt(lineNo) || _lcovDigitsToNumber(lineNo) < 1) fail(`malformed BRDA line: ${JSON.stringify(raw)}`);
      if (taken !== "-" && !isInt(taken)) fail(`malformed BRDA line: ${JSON.stringify(raw)}`);
      brdaCount += 1;
      if (taken !== "-" && _lcovDigitsToNumber(taken) > 0) brdaHits += 1;
    } else if (tag === "DA") {
      if (sf === null) fail("DA before SF");
      const parts = value.split(",");
      if (parts.length !== 2) fail(`malformed DA line: ${JSON.stringify(raw)}`);
      const [lineNo, hits] = parts;
      if (!isInt(lineNo) || _lcovDigitsToNumber(lineNo) < 1) fail(`malformed DA line: ${JSON.stringify(raw)}`);
      if (!isInt(hits)) fail(`malformed DA line: ${JSON.stringify(raw)}`);
      const key = lineNo.replace(/^0+/, "") || "0";
      if (da.has(key)) fail(`duplicate DA line number: ${lineNo}`);
      da.set(key, _lcovDigitsToNumber(hits));
    } else {
      // FNF, FNH, BRF, BRH, LF, LH — summary lines.
      if (sf === null) fail(`${tag} before SF`);
      if (summaries.has(tag)) fail(`duplicate ${tag} in one record`);
      if (!isInt(value)) fail(`LCOV ${tag} value is not a non-negative integer: ${JSON.stringify(value)}`);
      summaries.set(tag, _lcovDigitsToNumber(value));
    }
  }
  if (sf === null) fail("record has no SF line");
  const linesFound = da.size;
  let linesHit = 0;
  for (const hits of da.values()) if (hits > 0) linesHit += 1;
  for (const [tag, derived] of [["LF", linesFound], ["LH", linesHit], ["FNF", fnCount], ["BRF", brdaCount], ["BRH", brdaHits]]) {
    if (summaries.has(tag) && summaries.get(tag) !== derived) {
      fail(`${tag} summary (${summaries.get(tag)}) does not match derived value (${derived})`);
    }
  }
  if (fndaSeen && summaries.has("FNH") && summaries.get("FNH") !== fndaHits) {
    fail(`FNH summary (${summaries.get("FNH")}) does not match derived value (${fndaHits})`);
  }
  return {
    source_file: sf,
    lines_found: linesFound,
    lines_hit: linesHit,
    functions_found: summaries.has("FNF") ? summaries.get("FNF") : fnCount,
    functions_hit: summaries.has("FNH") ? summaries.get("FNH") : (fndaSeen ? fndaHits : 0),
    branches_found: summaries.has("BRF") ? summaries.get("BRF") : brdaCount,
    branches_hit: summaries.has("BRH") ? summaries.get("BRH") : brdaHits,
  };
}

export function parseLcov(input) {
  let text;
  if (typeof input === "string") {
    if (input.length > MAX_LCOV_BYTES) throw new Error(`LCOV report exceeds size limit of ${MAX_LCOV_BYTES} bytes`);
    text = input;
  } else {
    const bytes = input instanceof Uint8Array ? input : Buffer.from(input);
    if (bytes.length > MAX_LCOV_BYTES) throw new Error(`LCOV report exceeds size limit of ${MAX_LCOV_BYTES} bytes`);
    if (bytes.includes(0)) throw new Error("LCOV report contains a NUL byte");
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      throw new Error("LCOV report is not valid UTF-8");
    }
  }
  if (text.includes("\0")) throw new Error("LCOV report contains a NUL byte");
  const records = [];
  let current = [];
  let openRecord = false;
  for (const rawLine of text.split("\n")) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line === "") continue;
    if (line === "end_of_record") {
      if (!openRecord) throw new Error("LCOV end_of_record with no open record");
      records.push(_parseLcovRecord(current, records.length + 1));
      current = [];
      openRecord = false;
      continue;
    }
    openRecord = true;
    current.push(line);
  }
  if (openRecord) throw new Error("LCOV record is not closed by end_of_record");
  if (records.length === 0) throw new Error("LCOV report contains no records");
  return {
    files: records.length,
    lines_found: records.reduce((n, r) => n + r.lines_found, 0),
    lines_hit: records.reduce((n, r) => n + r.lines_hit, 0),
    records,
  };
}

// ---------------------------------------------------------------------------
// Receipt / policy structural validation (FIX-R13b, F-06): mirrors the
// frozen JSON schemas benchreceipt.run/v1 and benchreceipt.policy/v1
// as the Python schema validator enforces them — required fields,
// additionalProperties: false, string lengths/patterns, integer
// ranges, enums, array/object bounds. A receipt failing any of these
// is INVALID_RECEIPT; a policy failing any is INVALID_POLICY.
//
// Pattern checks follow Python's re.search with ^...$ patterns: `$`
// also matches before trailing newlines, so trailing newlines are
// stripped before testing (the P2-05 behaviour — matching production
// exactly rather than being stricter than it).
// ---------------------------------------------------------------------------

const HEX40 = /^[0-9a-f]{40}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const JOB_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MATRIX_KEY_RE = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;
const REPORT_PATH_RE = /^(?!\/)(?!.*\/\/)(?!.*\/$)(?!^\.$)(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9._\-/]+$/;
const TIMESTAMP_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

function isPlainObject(v) {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isInt(v) {
  return typeof v === "number" && Number.isInteger(v);
}

function matchPattern(pattern, value) {
  // Python re.search(pattern, value) with a ^...$ pattern: matches
  // when the value, ignoring any trailing newlines, matches in full.
  const re = new RegExp(pattern.source ?? pattern);
  return re.test(value.replace(/\n+$/, ""));
}

function checkString(v, min, max, pattern) {
  if (typeof v !== "string" || v.length < min || v.length > max) return false;
  if (pattern && !matchPattern(pattern, v)) return false;
  return true;
}

function hasOnlyKeys(obj, allowed) {
  return Object.keys(obj).every((k) => allowed.includes(k));
}

function hasKeys(obj, required) {
  return required.every((k) => _hasOwn(obj, k));
}

function _checkSourceState(s) {
  if (!isPlainObject(s)) return "bad source_state";
  if (!hasOnlyKeys(s, ["dirty", "tracked_diff_sha256"])) return "extra source_state field";
  if (!hasKeys(s, ["dirty"])) return "missing source_state.dirty";
  if (typeof s.dirty !== "boolean") return "bad source_state.dirty";
  if (s.tracked_diff_sha256 !== undefined && !matchPattern(HEX64, s.tracked_diff_sha256)) return "bad source_state.tracked_diff_sha256";
  return null;
}

function receiptStructuralError(r) {
  if (!isPlainObject(r)) return "not an object";
  if (!hasOnlyKeys(r, ["schema", "job_id", "matrix", "git", "ci", "command", "runner", "reports",
    "junit", "source_state_before", "source_state_after", "started_at", "finished_at"])) {
    return "extra top-level field";
  }
  if (!hasKeys(r, ["schema", "job_id", "matrix", "git", "ci", "command", "runner", "reports"])) {
    return "missing required field";
  }
  if (r.schema !== "benchreceipt.run/v1") return "bad schema id";
  if (!checkString(r.job_id, 1, 128, JOB_ID_RE)) return "bad job_id";
  if (!isPlainObject(r.matrix)) return "bad matrix";
  const mKeys = Object.keys(r.matrix);
  if (mKeys.length < 1 || mKeys.length > 32) return "bad matrix size";
  for (const k of mKeys) {
    if (k.length > 64 || !matchPattern(MATRIX_KEY_RE, k)) return "bad matrix key";
    const v = r.matrix[k];
    if (typeof v !== "string" && typeof v !== "number" && typeof v !== "boolean") return "bad matrix value";
  }
  const g = r.git;
  if (!isPlainObject(g)) return "bad git";
  if (!hasOnlyKeys(g, ["head_sha", "tree_sha", "source_mode", "expected_source_sha", "dirty_before", "dirty_after", "head_sha_after", "tree_sha_after"])) {
    return "extra git field";
  }
  if (!hasKeys(g, ["head_sha", "tree_sha", "source_mode", "expected_source_sha", "dirty_before", "dirty_after"])) {
    return "missing git field";
  }
  if (!matchPattern(HEX40, g.head_sha) || !matchPattern(HEX40, g.tree_sha) || !matchPattern(HEX40, g.expected_source_sha)) {
    return "bad git sha";
  }
  if (g.head_sha_after !== undefined && !matchPattern(HEX40, g.head_sha_after)) return "bad git.head_sha_after";
  if (g.tree_sha_after !== undefined && !matchPattern(HEX40, g.tree_sha_after)) return "bad git.tree_sha_after";
  if (!["pr_head", "merge_commit", "event_sha", "explicit_sha"].includes(g.source_mode)) return "bad source_mode";
  if (typeof g.dirty_before !== "boolean" || typeof g.dirty_after !== "boolean") return "bad dirty flag";
  const c = r.ci;
  if (!isPlainObject(c)) return "bad ci";
  if (!hasOnlyKeys(c, ["provider", "run_id", "run_attempt", "workflow", "event_name", "workflow_ref", "workflow_sha"])) {
    return "extra ci field";
  }
  if (!hasKeys(c, ["provider", "run_id", "run_attempt", "workflow"])) return "missing ci field";
  if (!["github-actions", "generic"].includes(c.provider)) return "bad provider";
  if (!checkString(c.run_id, 1, 64)) return "bad run_id";
  if (!isInt(c.run_attempt) || c.run_attempt < 1 || c.run_attempt > 100000) return "bad run_attempt";
  if (!checkString(c.workflow, 1, 128)) return "bad workflow";
  if (c.event_name !== undefined && !checkString(c.event_name, 1, 64)) return "bad ci.event_name";
  if (c.workflow_ref !== undefined && !checkString(c.workflow_ref, 1, 512)) return "bad ci.workflow_ref";
  if (c.workflow_sha !== undefined && !matchPattern(HEX40, c.workflow_sha)) return "bad ci.workflow_sha";
  const cmd = r.command;
  if (!isPlainObject(cmd)) return "bad command";
  if (!hasOnlyKeys(cmd, ["argv_sha256", "display", "exit_code"])) return "extra command field";
  if (!hasKeys(cmd, ["argv_sha256", "display", "exit_code"])) return "missing command field";
  if (!matchPattern(HEX64, cmd.argv_sha256)) return "bad argv_sha256";
  if (!checkString(cmd.display, 1, 512)) return "bad display";
  if (!isInt(cmd.exit_code) || cmd.exit_code < -255 || cmd.exit_code > 255) return "bad exit_code";
  if (!isPlainObject(r.runner)) return "bad runner";
  if (!hasOnlyKeys(r.runner, ["os", "arch", "python"])) return "extra runner field";
  if (!hasKeys(r.runner, ["os", "arch", "python"])) return "missing runner field";
  for (const f of ["os", "arch", "python"]) {
    if (!checkString(r.runner[f], 1, 64)) return `bad runner.${f}`;
  }
  if (!Array.isArray(r.reports) || r.reports.length > 32) return "bad reports";
  for (const rep of r.reports) {
    if (!isPlainObject(rep)) return "bad report entry";
    if (!hasOnlyKeys(rep, ["kind", "path", "size_bytes", "sha256"])) return "extra report field";
    if (!hasKeys(rep, ["kind", "path", "size_bytes", "sha256"])) return "missing report field";
    if (!["junit", "lcov"].includes(rep.kind)) return "bad report kind";
    if (!checkString(rep.path, 1, 512, REPORT_PATH_RE)) return "bad report path";
    if (!isInt(rep.size_bytes) || rep.size_bytes < 0 || rep.size_bytes > 1073741824) return "bad report size";
    if (!matchPattern(HEX64, rep.sha256)) return "bad report sha256";
  }
  if (r.junit !== undefined) {
    if (!isPlainObject(r.junit)) return "bad junit";
    if (!hasOnlyKeys(r.junit, ["tests", "failures", "errors", "skipped"])) return "extra junit field";
    for (const f of ["tests", "failures", "errors", "skipped"]) {
      if (!isInt(r.junit[f]) || r.junit[f] < 0 || r.junit[f] > 100000000) return `bad junit.${f}`;
    }
  }
  if (r.source_state_before !== undefined) {
    const e = _checkSourceState(r.source_state_before);
    if (e) return e;
  }
  if (r.source_state_after !== undefined) {
    const e = _checkSourceState(r.source_state_after);
    if (e) return e;
  }
  if (r.started_at !== undefined && !matchPattern(TIMESTAMP_RE, r.started_at)) return "bad started_at";
  if (r.finished_at !== undefined && !matchPattern(TIMESTAMP_RE, r.finished_at)) return "bad finished_at";
  return null;
}

function policyError(p) {
  if (!isPlainObject(p)) return "policy is not an object";
  if (!hasOnlyKeys(p, ["schema_version", "source_mode", "expected_workflow", "required_jobs",
    "min_tests", "require_clean_source_after", "same_tree_across_jobs",
    "same_run_id", "same_run_attempt", "reports", "security"])) {
    return "extra policy field";
  }
  const required = ["schema_version", "source_mode", "expected_workflow", "required_jobs",
    "min_tests", "require_clean_source_after", "same_tree_across_jobs",
    "same_run_id", "same_run_attempt", "reports"];
  for (const f of required) {
    if (!_hasOwn(p, f)) return `missing ${f}`;
  }
  if (p.schema_version !== 1) return "bad schema_version";
  if (!["pr_head", "merge_commit", "event_sha", "explicit_sha"].includes(p.source_mode)) {
    return "bad source_mode";
  }
  if (!checkString(p.expected_workflow, 1, 128)) return "bad expected_workflow";
  if (!Array.isArray(p.required_jobs) || p.required_jobs.length < 1 || p.required_jobs.length > 128) {
    return "bad required_jobs";
  }
  for (const j of p.required_jobs) {
    if (!checkString(j, 1, 128, JOB_ID_RE)) return "bad required_jobs entry";
  }
  if (new Set(p.required_jobs).size !== p.required_jobs.length) return "duplicate required_jobs";
  if (!isInt(p.min_tests) || p.min_tests < 0 || p.min_tests > 100000000) return "bad min_tests";
  for (const f of ["require_clean_source_after", "same_tree_across_jobs", "same_run_id", "same_run_attempt"]) {
    if (typeof p[f] !== "boolean") return `bad ${f}`;
  }
  if (!isPlainObject(p.reports)) return "bad reports";
  if (!hasOnlyKeys(p.reports, ["junit", "lcov"])) return "extra reports field";
  for (const k of ["junit", "lcov"]) {
    if (!["required", "optional"].includes(p.reports[k])) return `bad reports.${k}`;
  }
  if (p.security !== undefined) {
    if (!isPlainObject(p.security)) return "bad security";
    if (!hasOnlyKeys(p.security, ["store_stdout", "store_stderr", "store_full_environment"])) {
      return "extra security field";
    }
    for (const f of ["store_stdout", "store_stderr", "store_full_environment"]) {
      if (p.security[f] !== undefined && typeof p.security[f] !== "boolean") return `bad security.${f}`;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Symlink-resolving path handling (FIX-R13b, F-05).
//
// path.resolve is lexical: it does NOT resolve symlinks. Production
// resolves them (Path.resolve / _is_within_root), so a report path
// that is a symlink to a file outside the job dir escapes the
// lexical check. resolveRealPath walks the path component by
// component, following symlinks (including dangling final targets,
// which realpathSync refuses), handling "." / ".." against the
// resolved prefix the way Path.resolve does, and failing on loops.
// ---------------------------------------------------------------------------

export function resolveRealPath(p) {
  const abs = p.startsWith("/") ? p : `${process.cwd()}/${p}`;
  let current = abs;
  const seen = new Set();
  for (let hop = 0; hop < 40; hop += 1) {
    const parts = current.split("/");
    const stack = [];
    let restarted = false;
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i];
      if (part === "" || part === ".") continue;
      if (part === "..") { stack.pop(); continue; }
      stack.push(part);
      const probe = `/${stack.join("/")}`;
      let st;
      try {
        st = lstatSync(probe);
      } catch {
        continue; // missing component: stays lexical, cannot hide a symlink
      }
      if (st.isSymbolicLink()) {
        const target = readlinkSync(probe);
        const dir = stack.slice(0, -1);
        const combined = target.startsWith("/")
          ? target
          : (dir.length ? `/${dir.join("/")}/${target}` : `/${target}`);
        const rest = parts.slice(i + 1).join("/");
        current = rest ? `${combined}/${rest}` : combined;
        restarted = true;
        break;
      }
    }
    if (!restarted) return stack.length ? `/${stack.join("/")}` : "/";
    if (seen.has(current)) throw new Error("symlink loop");
    seen.add(current);
  }
  throw new Error("too many symlink hops");
}

function isWithin(root, target) {
  if (target === root) return true;
  return target.startsWith(root === "/" ? "/" : `${root}/`);
}

function decodeUtf8Strict(bytes) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Core verification (same rules as benchreceipt.verify.evaluate).
// ---------------------------------------------------------------------------

function sha256File(path) {
  const data = readFileSync(path);
  return { size: data.length, sha256: createHash("sha256").update(data).digest("hex"), bytes: data };
}

function aggregateStatus(reasonCodes) {
  let worst = "BOUND_PASS";
  for (const code of reasonCodes) {
    const s = REASON_STATUS[code] || "INVALID";
    if (STATUS_ORDER.indexOf(s) < STATUS_ORDER.indexOf(worst)) worst = s;
  }
  return worst;
}

function sortedUnique(values) {
  return [...new Set(values)].sort();
}

function internalErrorResult() {
  return {
    schema: "benchreceipt.result/v1",
    status: "INTERNAL_ERROR",
    jobs_verified: 0,
    missing_jobs: [],
    unexpected_jobs: [],
    duplicate_jobs: [],
    reason_codes: ["INTERNAL_ERROR"],
    identity_mismatches: [],
    report_errors: [{ code: "INTERNAL_ERROR", message: "internal error during verification" }],
  };
}

export function evaluate(policy, expectedSourceSha, evidenceDir, options = {}) {
  const invalidResult = (codes, errors, mode) => ({
    schema: "benchreceipt.result/v1",
    status: "INVALID",
    jobs_verified: 0,
    missing_jobs: [],
    unexpected_jobs: [],
    duplicate_jobs: [],
    reason_codes: sortedUnique(codes),
    identity_mismatches: [],
    report_errors: [...errors].sort((a, b) =>
      (a.job_id || "").localeCompare(b.job_id || "") || a.code.localeCompare(b.code)),
    ...(mode !== undefined ? { expected_source_mode: mode } : {}),
  });

  // Run-identity pins are validated first, as in production's
  // _evaluate_inner: caller misuse (a non-string/empty run id, an
  // out-of-range attempt) is a verifier-side error, not a finding —
  // production's evaluate() converts it to an INTERNAL_ERROR result.
  const expectedRunId = options === null ? undefined : options.expectedRunId;
  const expectedAttempt = options === null ? undefined : options.expectedAttempt;
  if (expectedRunId !== undefined && expectedRunId !== null
    && (typeof expectedRunId !== "string" || expectedRunId === "")) {
    return internalErrorResult();
  }
  if (expectedAttempt !== undefined && expectedAttempt !== null
    && (typeof expectedAttempt !== "number" || !Number.isInteger(expectedAttempt)
      || expectedAttempt < 1 || expectedAttempt > 100000)) {
    return internalErrorResult();
  }

  const perr = policyError(policy);
  if (perr) {
    return invalidResult(["INVALID_POLICY"],
      [{ code: "INVALID_POLICY", message: "policy is not valid benchreceipt.policy/v1" }]);
  }
  const mode = policy.source_mode;
  if (typeof expectedSourceSha !== "string" || !HEX40.test(expectedSourceSha)) {
    return invalidResult(["INVALID_POLICY"],
      [{ code: "INVALID_POLICY", message: "policy is not valid benchreceipt.policy/v1" }], mode);
  }
  let evidenceStat;
  try {
    evidenceStat = statSync(evidenceDir);
  } catch {
    return invalidResult(["INVALID_EVIDENCE"],
      [{ code: "INVALID_EVIDENCE", message: "evidence directory is missing or unreadable" }], mode);
  }
  if (!evidenceStat.isDirectory()) {
    return invalidResult(["INVALID_EVIDENCE"],
      [{ code: "INVALID_EVIDENCE", message: "evidence directory is missing or unreadable" }], mode);
  }
  let evidenceReal;
  try {
    evidenceReal = resolveRealPath(evidenceDir);
  } catch {
    evidenceReal = resolve(evidenceDir);
  }

  const reasonCodes = new Set();
  const identityMismatches = [];
  let reportErrors = [];
  const receipts = [];
  // Job ids of receipts that exist but are invalid: present for the
  // matrix set comparison (the job is invalid, not missing), but never
  // verified and never a reference value. Mirrors verify.py.
  const invalidJobIds = [];

  let entries;
  try {
    entries = readdirSync(evidenceDir, { withFileTypes: true });
  } catch {
    return invalidResult(["INVALID_EVIDENCE"],
      [{ code: "INVALID_EVIDENCE", message: "evidence directory is missing or unreadable" }], mode);
  }
  const jobDirs = entries.filter((e) => e.isDirectory()).sort((a, b) => a.name.localeCompare(b.name));
  const invalidReceipt = (jobLabel) => {
    reasonCodes.add("INVALID_RECEIPT");
    reportErrors.push({ code: "INVALID_RECEIPT", message: "receipt is not valid benchreceipt.run/v1", job_id: jobLabel });
    invalidJobIds.push(jobLabel);
  };
  for (const dir of jobDirs) {
    const jobDir = join(evidenceDir, dir.name);
    const receiptPath = join(jobDir, "receipt.json");
    // FIX-R13b (F-05): a symlinked job dir or receipt.json is read
    // through its real path, and a real path escaping its root is an
    // invalid receipt — the Oracle reads nothing from outside the
    // evidence tree. (Production's raw verify reads symlinked
    // receipts straight through, P2-18; the Oracle fails closed here
    // by task direction. The bundle layer already refuses symlinks.)
    let jobReal;
    try {
      jobReal = resolveRealPath(jobDir);
    } catch {
      invalidReceipt(dir.name);
      continue;
    }
    if (!isWithin(evidenceReal, jobReal)) {
      invalidReceipt(dir.name);
      continue;
    }
    let receiptReal;
    try {
      receiptReal = resolveRealPath(receiptPath);
    } catch {
      invalidReceipt(dir.name);
      continue;
    }
    if (!isWithin(jobReal, receiptReal)) {
      invalidReceipt(dir.name);
      continue;
    }
    let data;
    try {
      data = JSON.parse(readFileSync(receiptPath, "utf-8"));
    } catch {
      invalidReceipt(dir.name);
      continue;
    }
    const err = receiptStructuralError(data);
    if (err) {
      reasonCodes.add("INVALID_RECEIPT");
      reportErrors.push({
        code: "INVALID_RECEIPT",
        message: "receipt is not valid benchreceipt.run/v1",
        job_id: typeof data.job_id === "string" ? data.job_id : dir.name,
      });
      invalidJobIds.push(typeof data.job_id === "string" ? data.job_id : dir.name);
      continue;
    }
    receipts.push({ jobDir, jobReal, data });
  }

  const requiredJobs = [...policy.required_jobs];
  const requiredSet = new Set(requiredJobs);
  const seenCounts = new Map();
  for (const { data } of receipts) {
    seenCounts.set(data.job_id, (seenCounts.get(data.job_id) || 0) + 1);
  }
  const present = [...new Set([...seenCounts.keys(), ...invalidJobIds])].sort();
  const presentSet = new Set(present);
  const missingJobs = requiredJobs.filter((j) => !presentSet.has(j)).sort();
  const unexpectedJobs = present.filter((j) => !requiredSet.has(j)).sort();
  const duplicateJobs = [...seenCounts.entries()].filter(([, c]) => c > 1).map(([j]) => j).sort();
  if (missingJobs.length) reasonCodes.add("MATRIX_MISSING_JOB");
  if (unexpectedJobs.length) reasonCodes.add("MATRIX_UNEXPECTED_JOB");
  if (duplicateJobs.length) reasonCodes.add("MATRIX_DUPLICATE_JOB");

  const firstByJob = new Map();
  for (const { data } of [...receipts].sort((a, b) => a.data.job_id.localeCompare(b.data.job_id))) {
    if (!firstByJob.has(data.job_id)) firstByJob.set(data.job_id, data);
  }
  const orderedIds = [...firstByJob.keys()].sort();
  let refTree = null;
  let refRun = null;
  let refAttempt = null;
  if (orderedIds.length) {
    const ref = firstByJob.get(orderedIds[0]);
    refTree = ref.git.tree_sha;
    refRun = ref.ci.run_id;
    refAttempt = ref.ci.run_attempt;
  }

  let jobsVerified = 0;
  const seenOnce = new Set();

  for (const { jobDir, jobReal, data: receipt } of receipts) {
    const jobId = receipt.job_id;
    let jobOk = true;
    const isDuplicateCopy = seenOnce.has(jobId);
    seenOnce.add(jobId);
    if (isDuplicateCopy) jobOk = false;

    const git = receipt.git;
    const ci = receipt.ci;

    if (git.head_sha !== expectedSourceSha) {
      reasonCodes.add("SOURCE_SHA_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "git.head_sha", expected: expectedSourceSha, actual: git.head_sha });
      jobOk = false;
    }
    if (git.source_mode !== policy.source_mode) {
      reasonCodes.add("SOURCE_MODE_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "git.source_mode", expected: policy.source_mode, actual: git.source_mode });
      jobOk = false;
    }
    if (ci.workflow !== policy.expected_workflow) {
      reasonCodes.add("WORKFLOW_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "ci.workflow", expected: policy.expected_workflow, actual: ci.workflow });
      jobOk = false;
    }
    if (policy.same_tree_across_jobs && git.tree_sha !== refTree) {
      reasonCodes.add("TREE_SHA_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "git.tree_sha", expected: refTree, actual: git.tree_sha });
      jobOk = false;
    }
    if (policy.same_run_id && ci.run_id !== refRun) {
      reasonCodes.add("RUN_ID_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "ci.run_id", expected: refRun, actual: ci.run_id });
      jobOk = false;
    }
    if (policy.same_run_attempt && ci.run_attempt !== refAttempt) {
      reasonCodes.add("RUN_ATTEMPT_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "ci.run_attempt", expected: refAttempt, actual: ci.run_attempt });
      jobOk = false;
    }
    // FIX-R13b (F-08): expected run identity from the CLI. Independent
    // of the cross-job checks above: when the caller pins an expected
    // run id / attempt, every job must match it, with the same
    // RUN_ID_MISMATCH / RUN_ATTEMPT_MISMATCH codes (UNBOUND); only the
    // `expected` value differs (the pinned value, not the first job's).
    if (expectedRunId !== undefined && expectedRunId !== null && ci.run_id !== expectedRunId) {
      reasonCodes.add("RUN_ID_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "ci.run_id", expected: expectedRunId, actual: ci.run_id });
      jobOk = false;
    }
    if (expectedAttempt !== undefined && expectedAttempt !== null && ci.run_attempt !== expectedAttempt) {
      reasonCodes.add("RUN_ATTEMPT_MISMATCH");
      identityMismatches.push({ job_id: jobId, field: "ci.run_attempt", expected: expectedAttempt, actual: ci.run_attempt });
      jobOk = false;
    }

    // After-identity check (spec v1.1.0, ADR-005, P0-01 fix; made
    // fail-closed in spec v1.2.0, ADR-007, P0-R1-01): a clean-tree
    // HEAD change leaves the porcelain digests identical and both
    // dirty flags False, so the dirty/digest checks below cannot see
    // it. Fail closed on inconsistency: the two after fields must
    // appear together, and a present after value that differs from
    // its before value is a mutation. When BOTH after fields are
    // absent the receipt cannot prove the run's HEAD/tree did not
    // change mid-run, so it is UNBOUND with MISSING_FIELD (ADR-007
    // overturns the ADR-005 decision 4 compat rule that judged such
    // receipts by the dirty/digest checks alone).
    let mutated = false;
    const afterHead = git.head_sha_after;
    const afterTree = git.tree_sha_after;
    if (afterHead === undefined && afterTree === undefined) {
      // No after-identity evidence at all: fail closed, do not fall
      // back to the dirty/digest checks (P0-R1-01). Message template
      // is byte-identical to the Python verifier (REASON_CODES.md).
      reasonCodes.add("MISSING_FIELD");
      reportErrors.push({ code: "MISSING_FIELD", message: "missing git.head_sha_after and git.tree_sha_after", job_id: jobId });
      jobOk = false;
    }
    if ((afterHead !== undefined) !== (afterTree !== undefined)) mutated = true;
    if (afterHead !== undefined && afterHead !== git.head_sha) mutated = true;
    if (afterTree !== undefined && afterTree !== git.tree_sha) mutated = true;
    const before = receipt.source_state_before;
    const after = receipt.source_state_after;
    if (isPlainObject(before) && isPlainObject(after)
      && typeof before.tracked_diff_sha256 === "string"
      && typeof after.tracked_diff_sha256 === "string"
      && before.tracked_diff_sha256 !== after.tracked_diff_sha256) {
      mutated = true;
    }
    if (git.dirty_before !== git.dirty_after) mutated = true;
    if (policy.require_clean_source_after && git.dirty_after === true) mutated = true;
    if (mutated) {
      reasonCodes.add("SOURCE_MUTATED_DURING_RUN");
      jobOk = false;
    }

    const reports = receipt.reports || [];
    const byKind = new Map();
    for (const rep of reports) {
      if (!byKind.has(rep.kind)) byKind.set(rep.kind, []);
      byKind.get(rep.kind).push(rep);
    }
    for (const kind of ["junit", "lcov"]) {
      if (policy.reports[kind] !== "required") continue;
      if (!byKind.has(kind)) {
        reasonCodes.add("REPORT_MISSING");
        reportErrors.push({ code: "REPORT_MISSING", message: `required ${kind} report missing`, job_id: jobId });
        jobOk = false;
      }
    }

    let junitPath = null;
    // FIX-R13b (F-01 mirror): EVERY parsed junit report in this job,
    // in receipt order — (report path, parsed counts or null when the
    // file was malformed). The old code kept only the LAST parsed
    // report, so a failing bound report was silently ignored when it
    // was not last. The summary checks below judge each entry.
    const junitReports = [];
    for (const rep of reports) {
      const rel = rep.path;
      const target = resolve(jobDir, rel);
      // FIX-R13b (F-05): resolve symlinks before the containment
      // check; a report whose real path escapes the job dir is a
      // digest mismatch, exactly as in production.
      let realTarget;
      try {
        realTarget = resolveRealPath(target);
      } catch {
        reasonCodes.add("REPORT_HASH_MISMATCH");
        reportErrors.push({ code: "REPORT_HASH_MISMATCH", message: `report digest mismatch: ${rel}`, job_id: jobId, path: rel });
        jobOk = false;
        continue;
      }
      if (!isWithin(jobReal, realTarget)) {
        reasonCodes.add("REPORT_HASH_MISMATCH");
        reportErrors.push({ code: "REPORT_HASH_MISMATCH", message: `report digest mismatch: ${rel}`, job_id: jobId, path: rel });
        jobOk = false;
        continue;
      }
      let file;
      try {
        file = sha256File(target);
      } catch {
        reasonCodes.add("REPORT_MISSING");
        reportErrors.push({ code: "REPORT_MISSING", message: `report file missing: ${rel}`, job_id: jobId, path: rel });
        jobOk = false;
        continue;
      }
      if (file.size !== rep.size_bytes || file.sha256 !== rep.sha256) {
        reasonCodes.add("REPORT_HASH_MISMATCH");
        reportErrors.push({ code: "REPORT_HASH_MISMATCH", message: `report digest mismatch: ${rel}`, job_id: jobId, path: rel });
        jobOk = false;
        continue;
      }
      if (rep.kind === "junit") {
        junitPath = rel;
        const jtext = decodeUtf8Strict(file.bytes);
        const parsed = jtext === null ? null : parseJUnitMinimal(jtext);
        junitReports.push({ path: rel, parsed });
        if (parsed === null) {
          reasonCodes.add("JUNIT_MALFORMED");
          reportErrors.push({ code: "JUNIT_MALFORMED", message: "JUnit XML is malformed", job_id: jobId, path: rel });
          jobOk = false;
        }
      } else if (rep.kind === "lcov") {
        // FIX-R13b (F-02): LCOV format + path validation (§5.4). A
        // malformed coverage file is INVALID, never passed on
        // presence + digest alone.
        try {
          parseLcov(file.bytes);
        } catch {
          reasonCodes.add("LCOV_MALFORMED");
          reportErrors.push({ code: "LCOV_MALFORMED", message: "LCOV report is malformed", job_id: jobId, path: rel });
          jobOk = false;
        }
      }
    }

    const summary = receipt.junit;
    if (policy.reports.junit === "required" && summary === undefined) {
      reasonCodes.add("MISSING_FIELD");
      reportErrors.push({ code: "MISSING_FIELD", message: "missing junit summary", job_id: jobId });
      jobOk = false;
    }

    let junitFailed = false;
    let junitTests = null;
    if (summary !== undefined) {
      junitTests = summary.tests;
      if (junitTests === 0) {
        reasonCodes.add("JUNIT_EMPTY");
        const e = { code: "JUNIT_EMPTY", message: "JUnit report has 0 tests", job_id: jobId };
        if (junitPath) e.path = junitPath;
        reportErrors.push(e);
        jobOk = false;
      } else if (summary.failures > 0 || summary.errors > 0) {
        junitFailed = true;
        reasonCodes.add("JUNIT_FAILED");
        const e = { code: "JUNIT_FAILED", message: `JUnit failed: ${summary.failures} failures, ${summary.errors} errors (tests=${summary.tests})`, job_id: jobId };
        if (junitPath) e.path = junitPath;
        reportErrors.push(e);
        jobOk = false;
      }
      if (junitTests > 0 && junitTests < policy.min_tests) {
        reasonCodes.add("POLICY_MISMATCH");
        const e = { code: "POLICY_MISMATCH", message: `JUnit tests ${junitTests} below policy min_tests ${policy.min_tests}`, job_id: jobId };
        if (junitPath) e.path = junitPath;
        reportErrors.push(e);
        jobOk = false;
      }
    }
    // FIX-R13b (F-01 mirror): judge EVERY parsed junit report, not
    // just the last one. A report counts as failing when its own
    // parsed counts show failures/errors > 0, and every parsed
    // report's counts must match the receipt summary (when one
    // exists) — order-independent, so a failing report can no longer
    // hide behind a passing report listed after it.
    const parsedReports = junitReports.filter((r) => r.parsed !== null);
    const summaryFailed = summary !== undefined && (summary.failures > 0 || summary.errors > 0);
    const summaryEmpty = summary !== undefined && summary.tests === 0;
    for (const { path: repPath, parsed } of parsedReports) {
      const pTests = parsed.tests;
      const pFailures = parsed.failures;
      const pErrors = parsed.errors;
      if (summary !== undefined) {
        if (pTests !== summary.tests || pFailures !== summary.failures || pErrors !== summary.errors) {
          reasonCodes.add("JUNIT_SUMMARY_MISMATCH");
          reportErrors.push({ code: "JUNIT_SUMMARY_MISMATCH", message: "JUnit summary does not match parsed report", job_id: jobId, path: repPath });
          jobOk = false;
        }
        // Judge the parsed report on its own merits too. The summary
        // already emitted JUNIT_FAILED / JUNIT_EMPTY for its own
        // counts; a per-report entry is added only when the summary
        // did not already flag the same failure, so one report never
        // yields the same finding twice — but junit_failed is set
        // from ANY failing parsed report, so the exit-code check sees
        // it too.
        if (pFailures > 0 || pErrors > 0) {
          junitFailed = true;
          if (!summaryFailed) {
            reasonCodes.add("JUNIT_FAILED");
            reportErrors.push({ code: "JUNIT_FAILED", message: `JUnit failed: ${pFailures} failures, ${pErrors} errors (tests=${pTests})`, job_id: jobId, path: repPath });
            jobOk = false;
          }
        } else if (pTests === 0 && !summaryEmpty) {
          reasonCodes.add("JUNIT_EMPTY");
          reportErrors.push({ code: "JUNIT_EMPTY", message: "JUnit report has 0 tests", job_id: jobId, path: repPath });
          jobOk = false;
        }
      } else {
        // No summary: judge the parsed report directly.
        if (pTests === 0) {
          reasonCodes.add("JUNIT_EMPTY");
          reportErrors.push({ code: "JUNIT_EMPTY", message: "JUnit report has 0 tests", job_id: jobId, path: repPath });
          jobOk = false;
        } else if (pFailures > 0 || pErrors > 0) {
          junitFailed = true;
          reasonCodes.add("JUNIT_FAILED");
          reportErrors.push({ code: "JUNIT_FAILED", message: `JUnit failed: ${pFailures} failures, ${pErrors} errors (tests=${pTests})`, job_id: jobId, path: repPath });
          jobOk = false;
        }
      }
      if (junitTests === null) junitTests = pTests;
    }

    const exitCode = receipt.command.exit_code;
    if (parsedReports.length > 0 && junitTests !== null && junitTests > 0) {
      const exitFailed = exitCode !== 0;
      if (exitFailed !== junitFailed) {
        reasonCodes.add("EXIT_CODE_MISMATCH");
        const message = exitFailed
          ? `command exit code ${exitCode} contradicts passing JUnit result`
          : "command exit code 0 contradicts failing JUnit result";
        reportErrors.push({ code: "EXIT_CODE_MISMATCH", message, job_id: jobId });
        jobOk = false;
      }
    }

    if (jobOk && requiredSet.has(jobId)) jobsVerified += 1;
  }

  identityMismatches.sort((a, b) =>
    a.job_id.localeCompare(b.job_id) || a.field.localeCompare(b.field));
  // Judging every report can otherwise report the same finding twice
  // when two receipt entries point at the same report file. Identical
  // (job, code, path, message) findings are one finding; distinct
  // paths still report separately. Mirrors verify.py.
  const seenErrors = new Set();
  const dedupedErrors = [];
  for (const err of reportErrors) {
    const key = `${err.job_id || ""}\0${err.code || ""}\0${err.path || ""}\0${err.message || ""}`;
    if (!seenErrors.has(key)) {
      seenErrors.add(key);
      dedupedErrors.push(err);
    }
  }
  reportErrors = dedupedErrors;
  reportErrors.sort((a, b) =>
    (a.job_id || "").localeCompare(b.job_id || "")
    || a.code.localeCompare(b.code)
    || (a.path || "").localeCompare(b.path || ""));

  const codes = sortedUnique([...reasonCodes]);
  return {
    schema: "benchreceipt.result/v1",
    status: aggregateStatus(codes),
    jobs_verified: jobsVerified,
    missing_jobs: missingJobs,
    unexpected_jobs: unexpectedJobs,
    duplicate_jobs: duplicateJobs,
    reason_codes: codes,
    identity_mismatches: identityMismatches,
    report_errors: reportErrors,
    expected_source_mode: mode,
  };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const FLAGS = ["--policy", "--expected-source-sha", "--evidence", "--expected-run-id", "--expected-attempt"];
  const KEY = {
    "--policy": "policy",
    "--expected-source-sha": "expectedSourceSha",
    "--evidence": "evidence",
    "--expected-run-id": "expectedRunId",
    "--expected-attempt": "expectedAttempt",
  };
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    let arg = argv[i];
    let value;
    const eq = arg.indexOf("=");
    if (arg.startsWith("--") && eq !== -1) {
      value = arg.slice(eq + 1);
      arg = arg.slice(0, eq);
    }
    if (!FLAGS.includes(arg)) continue;
    if (value === undefined) {
      value = argv[i + 1];
      i += 1;
    }
    out[KEY[arg]] = value;
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.policy || !args.evidence) {
    process.stderr.write(
      "usage: node oracle/verify.mjs --policy <toml> --expected-source-sha <sha> --evidence <dir> [--expected-run-id <id>] [--expected-attempt <n>]\n");
    process.exit(4);
  }
  // FIX-R13b (F-08): --expected-source-sha handling matches the
  // Python CLI: a missing or malformed SHA is a usage error (exit 3,
  // stderr only), never a pass and never an INTERNAL_ERROR.
  if (args.expectedSourceSha === undefined) {
    process.stderr.write(
      "oracle verify: error: --expected-source-sha is required (missing evidence identity must never pass)\n");
    process.exit(3);
  }
  if (!HEX40.test(args.expectedSourceSha)) {
    process.stderr.write(
      "oracle verify: error: --expected-source-sha must be a 40-character lowercase hex SHA\n");
    process.exit(3);
  }
  if (args.expectedRunId !== undefined && args.expectedRunId === "") {
    process.stderr.write("oracle verify: error: --expected-run-id must not be empty\n");
    process.exit(3);
  }
  let expectedAttempt;
  if (args.expectedAttempt !== undefined) {
    if (!/^-?\d+$/.test(args.expectedAttempt)) {
      process.stderr.write("oracle verify: error: --expected-attempt must be an integer in 1..100000\n");
      process.exit(3);
    }
    expectedAttempt = Number(args.expectedAttempt);
    if (!Number.isInteger(expectedAttempt) || expectedAttempt < 1 || expectedAttempt > 100000) {
      process.stderr.write("oracle verify: error: --expected-attempt must be an integer in 1..100000\n");
      process.exit(3);
    }
  }
  let policyText;
  try {
    policyText = readFileSync(args.policy, "utf-8");
  } catch (err) {
    const result = {
      schema: "benchreceipt.result/v1",
      status: "INVALID",
      jobs_verified: 0,
      missing_jobs: [],
      unexpected_jobs: [],
      duplicate_jobs: [],
      reason_codes: ["INVALID_POLICY"],
      identity_mismatches: [],
      report_errors: [{ code: "INVALID_POLICY", message: "policy is not valid benchreceipt.policy/v1" }],
    };
    process.stdout.write(JSON.stringify(result) + "\n");
    process.exit(3);
  }
  let policy;
  try {
    policy = parsePolicyToml(policyText);
  } catch {
    const result = {
      schema: "benchreceipt.result/v1",
      status: "INVALID",
      jobs_verified: 0,
      missing_jobs: [],
      unexpected_jobs: [],
      duplicate_jobs: [],
      reason_codes: ["INVALID_POLICY"],
      identity_mismatches: [],
      report_errors: [{ code: "INVALID_POLICY", message: "policy is not valid benchreceipt.policy/v1" }],
    };
    process.stdout.write(JSON.stringify(result) + "\n");
    process.exit(3);
  }
  let result;
  try {
    result = evaluate(policy, args.expectedSourceSha, args.evidence,
      { expectedRunId: args.expectedRunId, expectedAttempt });
  } catch (err) {
    process.stderr.write(`oracle internal error: ${err.message}\n`);
    process.exit(4);
  }
  process.stdout.write(JSON.stringify(result) + "\n");
  process.exit(EXIT_BY_STATUS[result.status]);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
