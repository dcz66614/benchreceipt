#!/usr/bin/env python3
"""Freeze a P027 BenchReceipt release (P027-T014).

Builds the frozen release artifacts deterministically from one frozen
commit and writes the release manifest:

  05_release/source.zip          - the 02_source tree at <commit>, file-by-file
  05_release/dist.zip            - wheel + sdist + LICENSE + INSTALL.txt
  05_release/benchreceipt-<short>.bundle - git bundle of <commit>
  05_release/SHA256SUMS.txt      - SHA-256 of every released file except the
                                   manifest itself (see below)
  05_release/RELEASE_MANIFEST.json - commit, counts, bytes, SHA-256, gate results

Two subcommands (run in this order):

    python scripts/freeze_release.py build --commit <sha>
    # ... write 05_release/FREEZE_REPORT.md ...
    python scripts/freeze_release.py manifest --commit <sha> \\
        --pytest-passed 827 --oracle-passed 24 --oracle-total 24

``build`` builds everything twice into two scratch dirs and compares
SHA-256: the freeze is only accepted when both builds are byte-identical
(wheel, repacked sdist, source.zip, bundle). ``manifest`` then writes
SHA256SUMS.txt + RELEASE_MANIFEST.json from the built artifacts.

Why the manifest names the *source-freeze* commit, not the release
commit: RELEASE_MANIFEST.json is itself committed in the release commit,
so its ``frozen_commit`` field can never equal that commit's own hash
(the hash is a fixed point of its own content — uncomputable). The
manifest therefore names the commit whose tree was frozen and verified
(``--commit``), and ``verify_release.py`` enforces that the release
commit's 02_source tree is identical to that commit's tree. The release
commit hash itself is recorded in FREEZE_REPORT.md's git log section
by the coordinator at merge time. This is documented in FREEZE_REPORT.md.

Build dependencies (pinned, hash-checked, downloaded once from PyPI
into the work dir and reused): setuptools 80.9.0, wheel 0.45.1,
build 1.2.2, pyproject_hooks 1.2.0, packaging 25.0. The system
setuptools (68.1.2) cannot parse PEP 621 ``license = "MIT"`` and the
project .venv has no setuptools at all, so the pinned toolchain is
required. Only the *build* may touch the network (pip download of the
pinned wheels); the produced dist installs with ``--no-index``.

Usage (from 02_source):
    python scripts/freeze_release.py build [--commit HEAD] [--out-dir ../05_release]
    python scripts/freeze_release.py manifest [--commit HEAD] [--pytest-passed N]
        [--oracle-passed N] [--oracle-total N] [--s0-gate ../03_evidence/s0/S0_GATE.json]
Exit 0 only when the build is deterministic and the manifest matches
the artifacts on disk.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Pinned build toolchain (PyPI wheels, SHA-256 checked on download).
BUILD_DEPS = {
    "setuptools-80.9.0-py3-none-any.whl":
        "062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922",
    "wheel-0.45.1-py3-none-any.whl":
        "708e7481cc80179af0e556bbf0cc00b8444c7321e2700b8d8580231d13017248",
    "build-1.2.2-py3-none-any.whl":
        "277ccc71619d98afdd841a0e96ac9fe1593b823af481d3b0cea748e8894e0613",
    "pyproject_hooks-1.2.0-py3-none-any.whl":
        "9e5c6bfa8dcc30091c74b0cf803c81fdd29d94f01992a7707bc97babb1141913",
    "packaging-25.0-py3-none-any.whl":
        "29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484",
}
BUILD_DEP_VERSIONS = {
    "setuptools": "80.9.0",
    "wheel": "0.45.1",
    "build": "1.2.2",
    "pyproject_hooks": "1.2.0",
    "packaging": "25.0",
}

FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
RELEASE_ID = "r1"

INSTALL_TXT = """BenchReceipt 0.1.0 — offline install
==================================

This dist.zip contains a prebuilt wheel and an sdist. No network access
is needed to install the wheel:

    python -m venv benchreceipt-venv
    benchreceipt-venv/bin/python -m pip install --no-index \\
        benchreceipt-0.1.0-py3-none-any.whl
    benchreceipt-venv/bin/benchreceipt --help

The wheel has zero runtime dependencies (Python 3.12 standard library
only). The sdist (benchreceipt-0.1.0.tar.gz) needs a PEP 517 builder
(setuptools >= 77, for the PEP 621 `license = "MIT"` spelling); install
it the same way with --no-build-isolation when a new-enough setuptools
is present, or with build isolation when network access is available.
"""


def _run(cmd, *, cwd=None, env=None, log=None) -> subprocess.CompletedProcess:
    if log is not None:
        log.append(" ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed (exit {proc.returncode}): {' '.join(str(c) for c in cmd)}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str, log=None) -> str:
    return _run(["git", "-C", str(root), *args], log=log).stdout


def _deterministic_zip(entries: dict[str, bytes], out_path: Path) -> None:
    """Write a zip with fixed timestamps, sorted names, fixed perms."""
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            zf.writestr(info, entries[name])


def _build_source_zip(root: Path, commit: str, out_path: Path, log) -> dict:
    """source.zip from the frozen commit's 02_source tree (git blobs)."""
    listing = _git(root, "ls-tree", "-r", "--format=%(objectmode) %(objecttype) %(objectname)%x09%(path)",
                   commit, "--", "02_source", log=log)
    entries: dict[str, bytes] = {}
    total_bytes = 0
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        mode, _otype, blob = meta.split()
        if mode == "160000":
            raise RuntimeError(f"submodule in frozen tree, unsupported: {path}")
        rel = path[len("02_source/"):]
        data = subprocess.run(["git", "-C", str(root), "cat-file", "blob", blob],
                              capture_output=True, check=True).stdout
        entries[rel] = data
        total_bytes += len(data)
    _deterministic_zip(entries, out_path)
    return {"files": len(entries), "bytes": total_bytes,
            "sha256": _sha256_file(out_path),
            "zip_bytes": out_path.stat().st_size}


def _ensure_build_deps(work: Path, log) -> Path:
    """Download (once) + unpack the pinned build toolchain. Returns buildenv dir."""
    deps_dir = work / "build-deps"
    env_dir = work / "buildenv"
    deps_dir.mkdir(parents=True, exist_ok=True)
    for filename, expected in BUILD_DEPS.items():
        wheel_path = deps_dir / filename
        if wheel_path.exists():
            actual = _sha256_file(wheel_path)
            if actual != expected:
                raise RuntimeError(
                    f"cached build dep hash mismatch: {filename}: "
                    f"got {actual}, want {expected} — delete {wheel_path} and re-run")
        else:
            name = filename.split("-")[0]
            _run([sys.executable, "-m", "pip", "download", "--no-deps", "-d",
                  str(deps_dir), f"{name}=={BUILD_DEP_VERSIONS[name]}"], log=log)
            actual = _sha256_file(wheel_path)
            if actual != expected:
                raise RuntimeError(
                    f"downloaded build dep hash mismatch: {filename}: "
                    f"got {actual}, want {expected}")
    if env_dir.exists():
        shutil.rmtree(env_dir)
    env_dir.mkdir(parents=True)
    for filename in BUILD_DEPS:
        with zipfile.ZipFile(deps_dir / filename) as zf:
            zf.extractall(env_dir)
    return env_dir


def _repack_sdist_deterministic(sdist: Path, epoch: int) -> bytes:
    """Repack an sdist tar.gz with fixed mtimes/owners/sorting/gzip header.

    ``python -m build`` leaves wall-clock mtimes on generated files
    (PKG-INFO, setup.cfg), so the raw sdist is not byte-reproducible.
    Content is unchanged; only archive metadata is normalised.
    """
    members = []
    with tarfile.open(sdist, "r:gz") as tf:
        for member in tf.getmembers():
            data = tf.extractfile(member).read() if member.isfile() else None
            members.append((member, data))
    members.sort(key=lambda md: md[0].name)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for member, data in members:
            member.mtime = epoch
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            # The source sdist is PAX format: each member carries the
            # original float mtime in pax_headers, which tarfile writes
            # back in preference to .mtime. Clear it, or the repack
            # keeps the wall-clock build time (found 2026-11-18: the
            # first repack still differed run-to-run for this reason).
            member.pax_headers = {}
            tf.addfile(member, io.BytesIO(data) if data is not None else None)
    raw = buf.getvalue()
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", compresslevel=9,
                       mtime=epoch, fileobj=out) as gz:
        gz.write(raw)
    return out.getvalue()


def _build_dist(root: Path, commit: str, work: Path, epoch: int, log) -> dict:
    """Build wheel + sdist from a scratch export; return dist.zip entries + info."""
    export = work / "export"
    if export.exists():
        shutil.rmtree(export)
    export.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(root), "archive", commit, "02_source"],
                          capture_output=True, check=True)
    proc2 = subprocess.run(["tar", "-x", "-C", str(export)], input=archive.stdout,
                           capture_output=True)
    if proc2.returncode != 0:
        raise RuntimeError(f"tar extract failed: {proc2.stderr.decode()}")
    src = export / "02_source"
    _run(["find", ".", "-exec", "touch", "-h", "-d", f"@{epoch}", "{}", "+"],
         cwd=src, log=log)
    buildenv = _ensure_build_deps(work, log)
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    env["PYTHONPATH"] = str(buildenv) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    outdir = work / "dist-out"
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    _run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(outdir), "."],
         cwd=src, env=env, log=log)
    wheels = sorted(outdir.glob("*.whl"))
    sdists = sorted(outdir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(f"expected 1 wheel + 1 sdist, got {wheels} {sdists}")
    wheel, sdist = wheels[0], sdists[0]
    sdist_bytes = _repack_sdist_deterministic(sdist, epoch)
    license_bytes = (src / "LICENSE").read_bytes()
    entries = {
        wheel.name: wheel.read_bytes(),
        sdist.name: sdist_bytes,
        "LICENSE": license_bytes,
        "INSTALL.txt": INSTALL_TXT.encode(),
    }
    return {"entries": entries, "wheel": wheel.name, "sdist": sdist.name,
            "wheel_sha256": _sha256_bytes(entries[wheel.name]),
            "sdist_sha256": _sha256_bytes(entries[sdist.name])}


def _build_bundle(root: Path, commit: str, out_path: Path, log, bundle_ref: str | None) -> str:
    """Create + verify a bundle of the frozen commit.

    ``git bundle create`` refuses a bare SHA ("Refusing to create empty
    bundle") — it needs a ref to advertise. Bundle the ref that points
    at the frozen commit (default: auto-detect a branch, preferring
    ``t014``). Returns the ref used.
    """
    if bundle_ref is None:
        refs = _git(root, "for-each-ref", "--format=%(refname)",
                    "--points-at", commit, log=log).split()
        branches = [r for r in refs if r.startswith("refs/heads/")]
        if "refs/heads/t014" in branches:
            bundle_ref = "refs/heads/t014"
        elif branches:
            bundle_ref = branches[0]
        elif refs:
            bundle_ref = refs[0]
    tmp_ref = None
    if bundle_ref is None:
        # No ref points at the frozen commit (e.g. re-running after the
        # release commit moved the branch): use a temporary ref, removed
        # again after bundling, so the freeze stays re-runnable.
        tmp_ref = f"refs/heads/freeze-tmp-{commit[:12]}"
        _run(["git", "-C", str(root), "update-ref", tmp_ref, commit], log=log)
        bundle_ref = tmp_ref
    try:
        if out_path.exists():
            out_path.unlink()
        # pack.threads=1: multi-threaded delta search is not
        # byte-reproducible run-to-run; single-threaded packing is
        # (verified 2026-11-18: two builds byte-identical).
        _run(["git", "-c", "pack.threads=1", "-C", str(root), "bundle",
              "create", str(out_path), bundle_ref], log=log)
        _run(["git", "-C", str(root), "bundle", "verify", str(out_path)], log=log)
    finally:
        if tmp_ref is not None:
            subprocess.run(["git", "-C", str(root), "update-ref", "-d", tmp_ref],
                           capture_output=True)
    return bundle_ref


def cmd_build(args) -> int:
    root = Path(args.repo).resolve()
    out_dir = Path(args.out_dir).resolve()
    work = Path(args.work_dir).resolve()
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", args.commit],
                            capture_output=True, text=True, check=True).stdout.strip()
    log: list[str] = []
    # Freeze must come from a committed tree: no uncommitted changes under 02_source.
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "02_source"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        print(f"FAIL: 02_source has uncommitted changes; commit them first:\n{dirty}")
        return 1
    epoch = int(subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct", commit],
                               capture_output=True, text=True, check=True).stdout.strip())
    short = commit[:12]
    bundle_name = f"benchreceipt-{short}.bundle"
    results = {}
    for label in ("run1", "run2"):
        run_work = work / label
        if run_work.exists():
            shutil.rmtree(run_work)
        run_work.mkdir(parents=True)
        run_out = run_work / "out"
        run_out.mkdir()
        src_info = _build_source_zip(root, commit, run_out / "source.zip", log)
        dist_info = _build_dist(root, commit, run_work, epoch, log)
        dist_path = run_out / "dist.zip"
        _deterministic_zip(dist_info["entries"], dist_path)
        _build_bundle(root, commit, run_out / bundle_name, log, args.bundle_ref)
        results[label] = {
            "source.zip": _sha256_file(run_out / "source.zip"),
            "dist.zip": _sha256_file(dist_path),
            bundle_name: _sha256_file(run_out / bundle_name),
            "source_info": src_info,
            "dist_info": {k: v for k, v in dist_info.items() if k != "entries"},
        }
    for name in ("source.zip", "dist.zip", bundle_name):
        if results["run1"][name] != results["run2"][name]:
            print(f"FAIL: non-deterministic build: {name} differs between runs\n"
                  f"  run1: {results['run1'][name]}\n  run2: {results['run2'][name]}")
            return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("source.zip", "dist.zip", bundle_name):
        shutil.copyfile(work / "run1" / "out" / name, out_dir / name)
    build_log = Path(args.build_log).resolve() if args.build_log else None
    if build_log:
        build_log.parent.mkdir(parents=True, exist_ok=True)
        build_log.write_text(
            "freeze build log (P027-T014)\n"
            f"commit: {commit}\n"
            f"epoch: {epoch}\n"
            f"source.zip: {results['run1']['source.zip']}\n"
            f"dist.zip: {results['run1']['dist.zip']}\n"
            f"{bundle_name}: {results['run1'][bundle_name]}\n"
            "commands:\n" + "\n".join(f"  $ {c}" for c in log) + "\n",
            encoding="utf-8")
    print(f"OK: deterministic build from {commit}")
    print(f"  source.zip: {results['run1']['source_info']['files']} files, "
          f"{results['run1']['source_info']['bytes']} source bytes, "
          f"sha256={results['run1']['source.zip']}")
    print(f"  dist.zip: wheel={results['run1']['dist_info']['wheel']} "
          f"sdist={results['run1']['dist_info']['sdist']} "
          f"sha256={results['run1']['dist.zip']}")
    print(f"  {bundle_name}: sha256={results['run1'][bundle_name]}")
    return 0


def _load_s0(s0_path: Path) -> dict:
    data = json.loads(s0_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    repeat_hash = None
    for t in data["thresholds"]:
        if t["id"] == 6:
            m = re.search(r"hash ([0-9a-f]{64})", t["detail"])
            repeat_hash = m.group(1) if m else None
    if data.get("verdict") != "S0 PASS":
        raise RuntimeError(f"S0 gate verdict is not S0 PASS: {data.get('verdict')}")
    if repeat_hash is None:
        raise RuntimeError("could not extract repeat-100 hash from S0 threshold 6 detail")
    return {"verdict": data["verdict"], "spec_version": data.get("spec_version"),
            "golden_sha256": data["golden_sha256"],
            "reason_codes_sha256": data["reason_codes_sha256"],
            "repeat_hash": repeat_hash,
            "controls_pass": summary["controls_pass"], "controls_total": summary["controls_total"],
            "faults_detected": summary["faults_detected"], "faults_total": summary["faults_total"],
            "parity": summary["parity"], "parity_total": summary["parity_total"],
            "false_pass": summary["false_pass"], "false_block": summary["false_block"],
            "repeat_distinct_hashes": summary["repeat_distinct_hashes"],
            "p95_seconds": summary["p95_seconds"],
            "privacy_violations": summary["privacy_violations"],
            "offline_network_refs": summary["offline_network_refs"],
            "generated_at": data["generated_at"]}


def cmd_manifest(args) -> int:
    root = Path(args.repo).resolve()
    out_dir = Path(args.out_dir).resolve()
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", args.commit],
                            capture_output=True, text=True, check=True).stdout.strip()
    short = commit[:12]
    bundle_name = f"benchreceipt-{short}.bundle"
    expected = ["source.zip", "dist.zip", bundle_name]
    for name in expected:
        if not (out_dir / name).exists():
            print(f"FAIL: missing artifact {name} in {out_dir} — run `build` first")
            return 1
    freeze_report = out_dir / "FREEZE_REPORT.md"
    if not freeze_report.exists():
        print("FAIL: FREEZE_REPORT.md missing in out dir — write it before `manifest`")
        return 1
    s0 = _load_s0(Path(args.s0_gate).resolve())
    # SHA256SUMS.txt: every released file except itself and the manifest
    # (listing the manifest would be self-referential; the manifest lists
    # SHA256SUMS.txt's hash instead).
    sums_entries = ["source.zip", "dist.zip", bundle_name, "FREEZE_REPORT.md"]
    gitkeep = out_dir / ".gitkeep"
    if gitkeep.exists():
        sums_entries.append(".gitkeep")
    sums_lines = []
    for name in sorted(sums_entries):
        sums_lines.append(f"{_sha256_file(out_dir / name)}  {name}\n")
    sums_path = out_dir / "SHA256SUMS.txt"
    sums_path.write_text("".join(sums_lines), encoding="utf-8")

    def _info(name: str) -> dict:
        p = out_dir / name
        return {"file": name, "bytes": p.stat().st_size, "sha256": _sha256_file(p)}

    source_info = _build_source_zip_info(root, commit)
    manifest_files = []
    for name in sorted(sums_entries) + ["SHA256SUMS.txt"]:
        manifest_files.append(_info(name))
    build = {
        "python": sys.version.split()[0],
        "git": subprocess.run(["git", "--version"], capture_output=True, text=True,
                              check=True).stdout.strip(),
        "node": subprocess.run(["node", "--version"], capture_output=True, text=True,
                               check=True).stdout.strip(),
        "setuptools": BUILD_DEP_VERSIONS["setuptools"],
        "wheel": BUILD_DEP_VERSIONS["wheel"],
        "build": BUILD_DEP_VERSIONS["build"],
        "packaging": BUILD_DEP_VERSIONS["packaging"],
    }
    manifest = {
        "project": "P027 BenchReceipt",
        "spec_version": s0["spec_version"],
        "release_id": RELEASE_ID,
        "frozen_commit": commit,
        "frozen_commit_short": short,
        "freeze_date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("frozen_commit is the commit whose tree was frozen and verified; "
                 "the release commit that adds 05_release/* sits on top of it. "
                 "A manifest naming its own commit is uncomputable (hash fixed "
                 "point); see FREEZE_REPORT.md."),
        "source_zip": {**_info("source.zip"), **source_info},
        "dist_zip": _info("dist.zip"),
        "bundle": _info(bundle_name),
        "sha256sums": _info("SHA256SUMS.txt"),
        "freeze_report": _info("FREEZE_REPORT.md"),
        "files": manifest_files,
        "gates": {
            "pytest_passed": args.pytest_passed,
            "pytest_failed": 0,
            "oracle_tests_passed": args.oracle_passed,
            "oracle_tests_total": args.oracle_total,
            "s0_verdict": s0["verdict"],
            "s0_controls": f"{s0['controls_pass']}/{s0['controls_total']}",
            "s0_faults": f"{s0['faults_detected']}/{s0['faults_total']}",
            "s0_parity": f"{s0['parity']}/{s0['parity_total']}",
            "s0_false_pass": s0["false_pass"],
            "s0_false_block": s0["false_block"],
            "s0_repeat_distinct_hashes": s0["repeat_distinct_hashes"],
            "s0_repeat_hash": s0["repeat_hash"],
            "s0_golden_sha256": s0["golden_sha256"],
            "s0_reason_codes_sha256": s0["reason_codes_sha256"],
            "s0_p95_seconds": s0["p95_seconds"],
            "s0_privacy_violations": s0["privacy_violations"],
            "s0_offline_network_refs": s0["offline_network_refs"],
            "s0_generated_at": s0["generated_at"],
        },
        "build": build,
    }
    manifest_path = out_dir / "RELEASE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n",
                             encoding="utf-8")
    print(f"OK: manifest written for {commit}")
    print(f"  source.zip sha256={manifest['source_zip']['sha256']}")
    print(f"  dist.zip sha256={manifest['dist_zip']['sha256']}")
    print(f"  {bundle_name} sha256={manifest['bundle']['sha256']}")
    return 0


def _build_source_zip_info(root: Path, commit: str) -> dict:
    """File/byte counts of the frozen 02_source tree (no zip written)."""
    listing = _git(root, "ls-tree", "-r", "--format=%(objectname)%x09%(path)",
                   commit, "--", "02_source")
    total = 0
    count = 0
    for line in listing.splitlines():
        blob, path = line.split("\t", 1)
        size = int(subprocess.run(
            ["git", "-C", str(root), "cat-file", "-s", blob],
            capture_output=True, text=True, check=True).stdout.strip())
        total += size
        count += 1
    return {"source_files": count, "source_bytes": total}


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a BenchReceipt release.")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--commit", default="HEAD")
    sub = parser.add_subparsers(dest="command", required=True)
    p_build = sub.add_parser("build")
    p_build.add_argument("--work-dir", default=None)
    p_build.add_argument("--build-log", default=None)
    p_build.add_argument("--bundle-ref", default=None,
                         help="ref to bundle (default: auto-detect a branch pointing at --commit)")
    p_build.set_defaults(func=cmd_build)
    p_man = sub.add_parser("manifest")
    p_man.add_argument("--pytest-passed", type=int, required=True)
    p_man.add_argument("--oracle-passed", type=int, required=True)
    p_man.add_argument("--oracle-total", type=int, required=True)
    p_man.add_argument("--s0-gate", default=None)
    p_man.set_defaults(func=cmd_manifest)
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    if args.out_dir is None:
        args.out_dir = str(root / "05_release")
    if getattr(args, "work_dir", None) is None and args.command == "build":
        args.work_dir = str(root / ".tmp" / "t014-freeze" / "run")
    if getattr(args, "s0_gate", None) is None and args.command == "manifest":
        args.s0_gate = str(root / "03_evidence" / "s0" / "S0_GATE.json")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
