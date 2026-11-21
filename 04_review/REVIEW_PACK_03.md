# REVIEW_PACK_03 — Bundle / report / CLI

Frozen candidate: `cfede2711bc54567b918b1f85654c2dd42c30943` (see `REVIEW_INDEX.md`).

| Path | SHA-256 | Lines | Role |
|---|---|---|---|
| `02_source/src/benchreceipt/bundle.py` | `ce557f6f4ca79497be3b66ce4196ce9c7bae5b7036dc68327cabe118d0af0168` | 788 | bundle build/verify + SHA256SUMS.txt manifest |
| `02_source/src/benchreceipt/render/html.py` | `66704da5fad44da9d15d4edef7a5580446926e1d9f92f0e50b5259ec2c9fcf63` | 693 | HTML report renderer (escapes all values) |
| `02_source/src/benchreceipt/cli.py` | `5bea320be24286a240dd3072e893dcb24311c9f5e973618099d10e13aa510328` | 380 | CLI: verify/report/bundle subcommands, exit codes |
| `02_source/src/benchreceipt/__main__.py` | `30819d5b2ec5058171bac68f863dfb03f1d6b8858116dcca4d2eb15ea08bb278` | 13 | python -m benchreceipt entry point |
| `02_source/src/benchreceipt/__init__.py` | `9d8176dea0c1b4985de66baf505b201ae43f766f2d58fcb6c6484ef7ee1f158c` | 10 | package init |
| `02_source/src/benchreceipt/render/__init__.py` | `ddec99272b71a4193baecf2c0422118733cc3dc63e27cefa6a2895aad603489d` | 5 | render package init |
| `02_source/src/benchreceipt/reports/__init__.py` | `73c8c07bffb35e8d59420d00de6911bdaf94bff086c337bf299d630daba03527` | 10 | reports package init |

## What this pack covers

`bundle` packages an evidence tree into a portable directory with
a single manifest (`SHA256SUMS.txt`: `<sha256> <size> <rel-path>`
per file) and verifies it. `render/html.py` turns a verification
result into a self-contained HTML report. `cli.py` wires the three
subcommands (`verify`, `report`, `bundle`) and maps statuses to
process exit codes.

## Review questions

1. **Manifest trust.** `verify_bundle` re-reads every file and
   recomputes size + SHA-256; it never trusts the manifest or a
   receipt's stored digest. Confirm: missing file, hash mismatch,
   size mismatch, extra unlisted file, and malformed manifest all
   yield `ok=False`. Confirm a tampered manifest that *lists* a
   tampered file with its new hash is still caught by the receipt
   cross-check (`_check_receipt_reports` re-hashes report files
   against the receipt's recorded digests).
2. **Path containment.** `_validate_rel_posix` (inlined below)
   rejects absolute paths, drive letters, `..`/`.` segments,
   empty segments, trailing slashes, backslashes, NUL. Confirm
   every manifest entry, receipt report path, and bundle walk
   entry passes through it (or `_is_within_root` on resolved
   paths), in both `build_bundle` and `verify_bundle`. Is there
   a path that passes validation but escapes the root after
   resolution (e.g. via a symlink inside the bundle)?
3. **Symlinks.** Any symlink anywhere in the source tree refuses
   the build; any symlink in a bundle is a
   `BUNDLE_UNSUPPORTED_SYMLINK` problem, never followed. Confirm
   symlinked *directories* are also refused (not just files) and
   that `os.walk(..., followlinks=False)` plus the explicit
   directory check covers the case where a symlink appears
   mid-walk. Confirm `verify_bundle` never follows a symlink
   when resolving a report path (`target.is_symlink()` check in
   `_check_receipt_reports`).
4. **Size / count limits.** 1 GiB per file, 10,000 files,
   10 GiB total. Confirm the limits are enforced at build time
   (raise `BundleError`) and at verify time
   (`BUNDLE_LIMIT_EXCEEDED`, over-limit file not hashed). Check
   the total-bytes accounting: is the running total updated
   before or after the copy, and can a bundle just over the limit
   slip through on an off-by-one?
5. **Build atomicity.** `build_bundle` refuses a non-empty
   `out_dir`, refuses `out_dir` inside / containing
   `evidence_dir`, and refuses an evidence tree that already
   contains a root `SHA256SUMS.txt`. A failed build removes the
   half-written output (`shutil.rmtree`). Confirm no failure
   path leaves a half-bundle that a later `verify_bundle` could
   mistake for real, and that the copied bytes are re-hashed
   after copy (manifest describes the bundle on disk).
6. **HTML escaping.** `render/html.py` must escape every value
   taken from a verification result (job ids, reason codes,
   messages, paths) before interpolating into HTML. Confirm there
   is no unescaped interpolation (stored-XSS via a crafted job
   id / report path / JUnit message), no external resource
   reference (offline report), and that the report never embeds
   a full argv, secret, or absolute user path.
7. **CLI exit codes.** `cli.py` maps BOUND_PASS→0,
   BOUND_FAIL→1, UNBOUND→2, INVALID→3, INTERNAL_ERROR→4
   (via `verify.status_to_exit_code`). Confirm no subcommand
   returns 0 on a non-pass, that `--expected-run-id` /
   `--expected-attempt` are validated (empty run id, attempt
   outside 1..100000 → error, not silently ignored), and that
   `report` refuses to render a result it cannot parse rather
   than rendering a pass.
8. **Console script.** `pyproject.toml` declares
   `benchreceipt = "benchreceipt.cli:main"` (FIX-P1-01). Confirm
   `cli.main` returns an int usable as a process exit code and
   that the documented bare `benchreceipt capture/verify`
   steps in `examples/github-actions/ci.yml` match the parser
   (`build_parser`) exactly.

## Inlined source (verbatim — do not paraphrase)

### `bundle.py` — `_validate_rel_posix` + `_safe_join`

```python
def _validate_rel_posix(rel: str) -> str | None:
    """Return an error reason if ``rel`` is not a safe relative POSIX path.

    Rejects: empty, absolute (leading ``/`` or a Windows drive ``C:``),
    ``.`` / ``..`` segments, empty segments (``//``), trailing slash,
    backslashes, NUL. Returns None when the path is safe.
    """
    if not rel:
        return "empty relative path"
    if rel.startswith("/") or rel.startswith("\\"):
        return f"absolute path {rel!r}"
    if len(rel) >= 2 and rel[1] == ":" and rel[0].isalpha():
        return f"absolute (drive-letter) path {rel!r}"
    if "\\" in rel:
        return f"backslash in path {rel!r}"
    if "\x00" in rel:
        return f"NUL byte in path {rel!r}"
    if rel in (".", ".."):
        return f"unsafe path {rel!r}"
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return f"unsafe path {rel!r}"
    return None


def _safe_join(root: Path, rel: str) -> Path:
    """Join ``rel`` onto ``root`` after validation; raise BundleError."""
    reason = _validate_rel_posix(rel)
    if reason is not None:
        raise BundleError(f"unsafe bundle path: {reason}")
    target = root / rel
    if not _is_within_root(root, target):
        raise BundleError(f"path escapes bundle root: {rel!r}")
    return target
```

### `bundle.py` — `_parse_manifest`

```python
def _parse_manifest(
    manifest_bytes: bytes,
) -> tuple[dict[str, tuple[str, int]], list[BundleProblem]]:
    """Parse ``SHA256SUMS.txt`` bytes.

    Returns ``(entries, problems)`` where ``entries`` maps a safe
    relative POSIX path to ``(sha256, size_bytes)``. Malformed lines,
    duplicate entries, unsafe paths, and an entry naming the manifest
    itself are reported as problems (never raised, never silently
    skipped) so a tampered manifest is fail-closed, not fatal.
    """
    entries: dict[str, tuple[str, int]] = {}
    problems: list[BundleProblem] = []
    try:
        text = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(
            BundleProblem(
                CODE_MANIFEST_MALFORMED,
                MANIFEST_NAME,
                "manifest is not valid UTF-8",
            )
        )
        return entries, problems
    if "\r" in text:
        problems.append(
            BundleProblem(
                CODE_MANIFEST_MALFORMED,
                MANIFEST_NAME,
                "manifest contains CR characters (expected LF line endings)",
            )
        )
    for lineno, line in enumerate(text.split("\n"), start=1):
        if lineno == len(text.split("\n")) and line == "":
            continue  # trailing newline after the last entry
        if line == "":
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    f"manifest line {lineno} is empty",
                )
            )
            continue
        match = _MANIFEST_LINE_RE.match(line)
        if not match:
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    f"manifest line {lineno} does not match "
                    "'<sha256> <size> <relative-path>'",
                )
            )
            continue
        digest, size_text, rel = match.groups()
        if rel == MANIFEST_NAME:
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    "manifest lists itself; the manifest is never a listed file",
                )
            )
            continue
        reason = _validate_rel_posix(rel)
        if reason is not None:
            problems.append(
                BundleProblem(
                    CODE_PATH_ESCAPE,
                    rel,
                    f"manifest entry has an unsafe path: {reason}",
                )
            )
            continue
        if rel in entries:
            problems.append(
                BundleProblem(
                    CODE_MANIFEST_MALFORMED,
                    MANIFEST_NAME,
                    f"manifest lists {rel!r} more than once",
                )
            )
            continue
        entries[rel] = (digest, int(size_text))
    return entries, problems
```
