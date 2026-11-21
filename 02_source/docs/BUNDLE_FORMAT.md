# Bundle format — P027 BenchReceipt v1.0.0 (frozen by P027-T006)

Portable evidence bundle: a directory produced by
`benchreceipt.bundle.build_bundle` from a `.benchreceipt/evidence` tree
(PROJECT_BOOK §6.1), verifiable offline by
`benchreceipt.bundle.verify_bundle`.

## Layout

```text
<bundle-root>/
  SHA256SUMS.txt                 # the manifest (this file only)
  <job-id>/
    receipt.json                 # benchreceipt.run/v1
    artifacts/
      junit.xml                  # report bytes, as captured
      lcov.info
  <job-id>/...
```

The job subdirectories are copied verbatim from the evidence tree:
same relative paths, same bytes. The manifest itself is never a listed
file (it cannot hash itself).

## Manifest: `SHA256SUMS.txt` (single-file format — the T006 decision)

One line per bundled file, sorted by POSIX relative path, LF line
endings, one trailing newline per line:

```text
<sha256-hex> <size-bytes-decimal> <relative-posix-path>
```

Example:

```text
4d3c8f9a…  2048  unit-linux-py312/artifacts/junit.xml
9f2e1b77…  512   unit-linux-py312/receipt.json
```

- Fields are separated by exactly **one** ASCII space; the path is the
  remainder of the line after the second space, so paths may contain
  spaces but never a newline.
- `sha256-hex` is the lowercase hex SHA-256 of the file's exact bytes.
- `size-bytes-decimal` is the file's byte count. Sizes live in this
  column: there is **no companion `MANIFEST.json`** — one manifest
  file means the size and hash records cannot drift out of sync.
- The format is deliberately **not** byte-compatible with stock
  `sha256sum -c` output (which has no size column). Verify bundles
  with `benchreceipt.bundle.verify_bundle`, not `sha256sum`.

`build_bundle` returns the manifest summary:

```json
{"files": 3, "total_bytes": 2560,
 "sha256": "<sha256 of the SHA256SUMS.txt bytes>",
 "out_dir": "<bundle dir>", "manifest": "SHA256SUMS.txt"}
```

## Verification (`verify_bundle`)

Re-reads every file, recomputes size + SHA-256, and checks:

1. Every manifest entry exists on disk with matching size and hash.
2. No extra file is present on disk that the manifest does not list.
3. The manifest itself is well-formed (UTF-8, LF, one entry per path,
   no self-listing, no unsafe paths).
4. Every job receipt's recorded report hashes (`reports[].sha256` /
   `size_bytes`, relative to the job dir) match freshly recomputed
   digests of the actual report bytes (PROJECT_BOOK §5.4: re-read +
   recompute at verify time).

`ok` is true only when zero problems are found. A tampered bundle
(one byte changed, one file deleted or added) is a result with
problems, never an exception; only an input that is not a bundle dir
at all (missing / not a directory / no `SHA256SUMS.txt`) raises
`BundleError`.

## Problem codes

| Code | Meaning |
|---|---|
| `BUNDLE_MISSING_FILE` | File listed in the manifest is absent from the bundle. |
| `BUNDLE_HASH_MISMATCH` | Recomputed SHA-256 differs from the manifest entry. |
| `BUNDLE_SIZE_MISMATCH` | Actual byte count differs from the manifest entry. |
| `BUNDLE_EXTRA_FILE` | File present on disk but not listed in the manifest. |
| `BUNDLE_PATH_ESCAPE` | Manifest entry is absolute, contains `..` / backslash / drive letter, or otherwise escapes the bundle root. |
| `BUNDLE_UNSUPPORTED_SYMLINK` | A symlink was found in the bundle; symlinks are never followed. |
| `BUNDLE_MANIFEST_MALFORMED` | Manifest line unparsable, duplicate entry, non-UTF-8 / CR line endings, or the manifest listing itself. |
| `BUNDLE_LIMIT_EXCEEDED` | A file exceeds 1 GiB, or the bundle exceeds 10,000 files / 10 GiB total. |
| `REPORT_MISSING` | (reused frozen verifier code) A report a receipt lists is absent. |
| `REPORT_HASH_MISMATCH` | (reused frozen verifier code) A receipt's recorded report size/hash disagrees with the recomputed values, or the report path escapes the job dir. |
| `INVALID_RECEIPT` | (reused frozen verifier code) A job receipt is not JSON, not an object, or has a malformed `reports` list. |

`BUNDLE_*` codes are bundle-module codes; they do not collide with the
frozen verifier vocabulary in `docs/REASON_CODES.md` (the three reused
codes above keep the same meaning there as here).

## Path safety (PROJECT_BOOK §11.2)

- All paths in the bundle are relative POSIX paths, normalised and
  contained in the bundle root.
- `..` segments, absolute paths (`/…` or `C:…`), backslashes, NUL
  bytes, empty segments and trailing slashes are rejected.
- Symlinks are unsupported everywhere: `build_bundle` refuses to copy
  a tree containing one (`BundleError`); `verify_bundle` reports one
  and never follows it — including a symlink pointing at
  `/etc/passwd` or any other outside target.

## Size limits

| Limit | Value | Source |
|---|---:|---|
| Per-file size | 1 GiB | Frozen schema (`run.v1.json` `size_bytes` max; ADR-001 decision 5; same as `capture` / `reports` limits) |
| Files per bundle | 10,000 | Bundle-level cap (this task) |
| Total bundle size | 10 GiB | Bundle-level cap (this task) |

A build that exceeds a limit raises `BundleError` and leaves no
half-written bundle behind. A verify that finds an over-limit file
reports `BUNDLE_LIMIT_EXCEEDED` and does not hash that file.

## What a bundle does NOT prove

Same honesty boundary as the receipt (PROJECT_BOOK §0.3, §11.2): the
SHA-256 manifest detects accidental mix-ups, stale artifacts and byte
damage. It is not a signature; a malicious runner can forge an entire
bundle. No signing, no TEE, no remote attestation in v1.
