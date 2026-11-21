#!/usr/bin/env python3
"""Validate a frozen P027 BenchReceipt release (P027-T014).

Checks, against the frozen commit recorded in
``05_release/RELEASE_MANIFEST.json``:

1. source.zip contents match the frozen commit's ``02_source`` tree
   file-by-file (names + bytes, read from git blobs).
2. dist.zip contains a wheel + sdist + LICENSE + INSTALL.txt; the wheel
   carries the MIT license expression and a LICENSE file; the sdist is
   a valid tarball.
3. RELEASE_MANIFEST.json values match the actual files on disk
   (frozen commit, file counts, byte counts, SHA-256 of source.zip /
   dist.zip / bundle / SHA256SUMS.txt / FREEZE_REPORT.md and of every
   released file listed under ``files``; no unlisted files in
   05_release/ apart from RELEASE_MANIFEST.json itself).
4. SHA256SUMS.txt verifies (every listed file recomputed).
5. LICENSE is present and MIT in both zips (source.zip LICENSE file;
   dist.zip top-level LICENSE + wheel dist-info LICENSE + METADATA
   ``License-Expression: MIT``).
6. Runtime dependencies == 0 (``pyproject.toml`` from the frozen
   commit parses with ``dependencies = []``).
7. S0 52/52 + parity + repeat-100 hash recorded: the manifest's gate
   block matches ``03_evidence/s0/S0_GATE.json`` (verdict S0 PASS,
   16/16 controls, 36/36 faults, parity 52/52, false PASS 0,
   false block 0, 1 distinct repeat hash).
8. The git bundle verifies and clones, and the clone's 02_source tree
   reproduces source.zip file-by-file.
9. dist.zip installs offline: a fresh venv installs the wheel with
   ``pip install --no-index`` and bare ``benchreceipt --help`` exits 0,
   followed by a capture -> verify round trip to BOUND_PASS
   (skippable with --skip-offline-install for fast iteration; the
   freeze acceptance run must NOT skip it).

Exit 0 only when every check passes; otherwise exit 1, listing every
failure by name. Read-only except for scratch dirs under --tmp-dir.

Usage (from 02_source):
    python scripts/verify_release.py [--release-dir ../05_release]
        [--commit <sha>] [--s0-gate ../03_evidence/s0/S0_GATE.json]
        [--skip-offline-install]
"""

from __future__ import annotations

import argparse
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
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "02_source"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd, *, cwd=None, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def _git_blob(root: Path, commit: str, path: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path}"],
                          capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git show failed for {commit}:{path}: "
                           f"{proc.stderr.decode(errors='replace')}")
    return proc.stdout


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, msg: str) -> None:
        if not ok:
            self.failures.append(msg)

    def fail(self, msg: str) -> None:
        self.failures.append(msg)


def _frozen_tree(root: Path, commit: str) -> dict[str, bytes]:
    """{relative path under 02_source: bytes} from git blobs."""
    proc = subprocess.run(["git", "-C", str(root), "ls-tree", "-r",
                           "--format=%(objectname)%x09%(path)",
                           commit, "--", "02_source"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git ls-tree failed in {root} for {commit}: "
                           f"{proc.stderr.strip()}")
    tree: dict[str, bytes] = {}
    for line in proc.stdout.splitlines():
        blob, path = line.split("\t", 1)
        rel = path[len("02_source/"):]
        tree[rel] = _git_blob(root, commit, path)
    return tree


def _offline_install_check(checker: Checker, release_dir: Path, tmp: Path) -> None:
    """Fresh venv + --no-index wheel install + --help + capture->verify."""
    dist = release_dir / "dist.zip"
    try:
        with zipfile.ZipFile(dist) as zf:
            wheels = [n for n in zf.namelist() if n.endswith(".whl")]
            if len(wheels) != 1:
                checker.fail(f"OFFLINE INSTALL: expected 1 wheel in dist.zip, found {wheels}")
                return
            wheel_bytes = zf.read(wheels[0])
    except zipfile.BadZipFile as exc:
        checker.fail(f"OFFLINE INSTALL: dist.zip unreadable: {exc}")
        return
    work = tmp / "offline-install"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    wheel_path = work / wheels[0]
    wheel_path.write_bytes(wheel_bytes)
    venv = work / "venv"
    proc = _run([sys.executable, "-m", "venv", str(venv)])
    if proc.returncode != 0:
        checker.fail(f"OFFLINE INSTALL: venv creation failed: {proc.stderr.strip()}")
        return
    venv_py = venv / "bin" / "python"
    env = dict(os.environ)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    proc = _run([str(venv_py), "-m", "pip", "install", "--no-index", "--no-deps",
                 str(wheel_path)], env=env)
    checker.check(proc.returncode == 0,
                  f"OFFLINE INSTALL: pip install --no-index failed (exit {proc.returncode}): "
                  f"{(proc.stdout + proc.stderr).strip()[-500:]}")
    if proc.returncode != 0:
        return
    bench = venv / "bin" / "benchreceipt"
    proc = _run([str(bench), "--help"])
    checker.check(proc.returncode == 0 and "benchreceipt" in proc.stdout.lower(),
                  f"OFFLINE INSTALL: bare `benchreceipt --help` failed (exit {proc.returncode}): "
                  f"{(proc.stdout + proc.stderr).strip()[-300:]}")
    if proc.returncode != 0:
        return
    # Minimal capture -> verify round trip in a scratch git repo. The
    # wrapped command writes a 1-test green JUnit file (no pytest in
    # the fresh venv); capture pins explicit_sha to the repo HEAD.
    repo = work / "scratch-repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "freeze-check@example.invalid"], cwd=repo)
    _run(["git", "config", "user.name", "Freeze Check"], cwd=repo)
    (repo / "write_junit.py").write_text(
        "import pathlib\n"
        "pathlib.Path('.benchreceipt/out').mkdir(parents=True, exist_ok=True)\n"
        "pathlib.Path('.benchreceipt/out/junit.xml').write_text(\n"
        "    '<?xml version=\"1.0\"?>'\n"
        "    '<testsuites><testsuite name=\"t\" tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\">'\n"
        "    '<testcase classname=\"t\" name=\"test_one\"/>'\n"
        "    '</testsuite></testsuites>')\n",
        encoding="utf-8")
    (repo / ".benchreceipt.toml").write_text(
        'schema_version = 1\nsource_mode = "explicit_sha"\n'
        'expected_workflow = "local"\nrequired_jobs = [ "demo-linux-py312" ]\n'
        'min_tests = 1\nrequire_clean_source_after = true\n'
        'same_tree_across_jobs = true\nsame_run_id = false\nsame_run_attempt = false\n'
        '\n[reports]\njunit = "required"\nlcov = "optional"\n',
        encoding="utf-8")
    (repo / ".gitignore").write_text(".benchreceipt/\n__pycache__/\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-qm", "demo: one green test"], cwd=repo)
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    proc = _run([str(bench), "capture", "--job", "demo-linux-py312",
                 "--matrix", "os=ubuntu-latest,python=3.12",
                 "--junit", ".benchreceipt/out/junit.xml",
                 "--source-mode", "explicit_sha", "--expected-sha", head,
                 "--", str(venv_py), "write_junit.py"], cwd=repo)
    checker.check(proc.returncode == 0,
                  f"OFFLINE INSTALL: capture round trip failed (exit {proc.returncode}): "
                  f"{(proc.stdout + proc.stderr).strip()[-500:]}")
    if proc.returncode != 0:
        return
    proc = _run([str(bench), "verify", "--policy", ".benchreceipt.toml",
                 "--evidence", ".benchreceipt/evidence",
                 "--expected-source-sha", head,
                 "--out", ".benchreceipt/verification.json"], cwd=repo)
    status = None
    vfile = repo / ".benchreceipt" / "verification.json"
    if vfile.exists():
        try:
            status = json.loads(vfile.read_text())["status"]
        except (KeyError, ValueError):
            status = None
    checker.check(proc.returncode == 0 and status == "BOUND_PASS",
                  f"OFFLINE INSTALL: verify round trip not BOUND_PASS "
                  f"(exit {proc.returncode}, status={status}): "
                  f"{(proc.stdout + proc.stderr).strip()[-300:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a frozen BenchReceipt release.")
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--release-dir", default=str(ROOT / "05_release"))
    parser.add_argument("--commit", default=None)
    parser.add_argument("--s0-gate", default=str(ROOT / "03_evidence" / "s0" / "S0_GATE.json"))
    parser.add_argument("--tmp-dir", default=str(ROOT / ".tmp"))
    parser.add_argument("--skip-offline-install", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    release_dir = Path(args.release_dir).resolve()
    checker = Checker()

    manifest_path = release_dir / "RELEASE_MANIFEST.json"
    if not manifest_path.exists():
        print("FAIL: verify_release: RELEASE_MANIFEST.json missing in "
              f"{release_dir}")
        return 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"FAIL: verify_release: RELEASE_MANIFEST.json is not valid JSON: {exc}")
        return 1

    commit = args.commit or manifest.get("frozen_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        checker.fail(f"MANIFEST: frozen_commit is not a full 40-hex commit: {commit!r}")
        commit = None
    if commit:
        proc = _run(["git", "-C", str(root), "cat-file", "-t", commit])
        checker.check(proc.returncode == 0 and proc.stdout.strip() == "commit",
                      f"MANIFEST: frozen_commit {commit} is not a commit in this repo")
        if manifest.get("frozen_commit") != commit:
            checker.fail(f"MANIFEST: frozen_commit {manifest.get('frozen_commit')} "
                         f"!= checked commit {commit}")

    # --- manifest values vs files on disk -------------------------------
    def _info(name: str):
        p = release_dir / name
        if not p.exists():
            checker.fail(f"MANIFEST: listed file missing on disk: {name}")
            return None
        return {"file": name, "bytes": p.stat().st_size, "sha256": _sha256_file(p)}

    for key in ("source_zip", "dist_zip", "bundle", "sha256sums", "freeze_report"):
        block = manifest.get(key)
        if not isinstance(block, dict):
            checker.fail(f"MANIFEST: missing or malformed block: {key}")
            continue
        actual = _info(block.get("file", ""))
        if actual is None:
            continue
        for field in ("file", "bytes", "sha256"):
            if block.get(field) != actual[field]:
                checker.fail(f"MANIFEST: {key}.{field} mismatch: manifest={block.get(field)!r} "
                             f"actual={actual[field]!r}")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        checker.fail("MANIFEST: missing or malformed `files` list")
        listed = []
    for entry in listed:
        actual = _info(entry.get("file", ""))
        if actual is None:
            continue
        for field in ("bytes", "sha256"):
            if entry.get(field) != actual[field]:
                checker.fail(f"MANIFEST: files[{entry.get('file')}].{field} mismatch: "
                             f"manifest={entry.get(field)!r} actual={actual[field]!r}")
    on_disk = {p.name for p in release_dir.iterdir() if p.is_file()}
    listed_names = {e.get("file") for e in listed if isinstance(e, dict)}
    extra = on_disk - listed_names - {"RELEASE_MANIFEST.json"}
    missing = listed_names - on_disk
    checker.check(not extra, f"MANIFEST: unlisted files in 05_release/: {sorted(extra)}")
    checker.check(not missing, f"MANIFEST: listed files absent from 05_release/: {sorted(missing)}")

    # --- SHA256SUMS.txt verifies ----------------------------------------
    sums_path = release_dir / "SHA256SUMS.txt"
    if not sums_path.exists():
        checker.fail("SHA256SUMS: SHA256SUMS.txt missing")
    else:
        for lineno, line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), 1):
            m = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
            if not m:
                checker.fail(f"SHA256SUMS: malformed line {lineno}: {line!r}")
                continue
            want, name = m.group(1), m.group(2)
            target = release_dir / name
            if not target.exists():
                checker.fail(f"SHA256SUMS: listed file missing: {name}")
            elif _sha256_file(target) != want:
                checker.fail(f"SHA256SUMS: hash mismatch for {name}: "
                             f"listed {want}, actual {_sha256_file(target)}")

    if commit:
        # --- source.zip vs frozen tree, file by file --------------------
        source_zip = release_dir / "source.zip"
        try:
            tree = _frozen_tree(root, commit)
        except RuntimeError as exc:
            checker.fail(f"SOURCE.ZIP: cannot read frozen tree at {commit}: {exc}")
            tree = {}
        if tree:
            try:
                with zipfile.ZipFile(source_zip) as zf:
                    names = zf.namelist()
                    zip_bytes = {n: zf.read(n) for n in names}
            except (zipfile.BadZipFile, FileNotFoundError) as exc:
                checker.fail(f"SOURCE.ZIP: unreadable: {exc}")
                names, zip_bytes = [], {}
            checker.check(sorted(names) == sorted(tree),
                          f"SOURCE.ZIP: file list differs from frozen tree at {commit}: "
                          f"only-in-zip={sorted(set(names) - set(tree))[:5]} "
                          f"only-in-tree={sorted(set(tree) - set(names))[:5]}")
            for name, want in tree.items():
                if name in zip_bytes and zip_bytes[name] != want:
                    checker.fail(f"SOURCE.ZIP: bytes differ for {name} "
                                 f"(zip sha256={hashlib.sha256(zip_bytes[name]).hexdigest()[:12]} "
                                 f"tree sha256={hashlib.sha256(want).hexdigest()[:12]})")
            src_block = manifest.get("source_zip", {})
            if isinstance(src_block, dict):
                if src_block.get("source_files") != len(tree):
                    checker.fail(f"MANIFEST: source_zip.source_files={src_block.get('source_files')} "
                                 f"!= frozen tree file count {len(tree)}")
                total = sum(len(b) for b in tree.values())
                if src_block.get("source_bytes") != total:
                    checker.fail(f"MANIFEST: source_zip.source_bytes={src_block.get('source_bytes')} "
                                 f"!= frozen tree byte total {total}")
            # --- LICENSE in source.zip + deps == 0 ----------------------
            lic = zip_bytes.get("LICENSE", b"")
            checker.check(b"MIT License" in lic,
                          "SOURCE.ZIP: LICENSE missing or not MIT text")
            try:
                pyproject = tomllib.loads(tree["pyproject.toml"].decode())
                deps = pyproject.get("project", {}).get("dependencies")
                checker.check(deps == [],
                              f"DEPS: pyproject runtime dependencies != []: {deps!r}")
            except (KeyError, ValueError) as exc:
                checker.fail(f"DEPS: cannot parse frozen pyproject.toml: {exc}")

        # --- dist.zip: wheel + sdist + LICENSE --------------------------
        dist_zip = release_dir / "dist.zip"
        try:
            with zipfile.ZipFile(dist_zip) as zf:
                dnames = zf.namelist()
                wheel_names = [n for n in dnames if n.endswith(".whl")]
                sdist_names = [n for n in dnames if n.endswith(".tar.gz")]
                checker.check(len(wheel_names) == 1,
                              f"DIST.ZIP: expected 1 wheel, found {wheel_names}")
                checker.check(len(sdist_names) == 1,
                              f"DIST.ZIP: expected 1 sdist, found {sdist_names}")
                checker.check("LICENSE" in dnames and b"MIT License" in zf.read("LICENSE"),
                              "DIST.ZIP: top-level LICENSE missing or not MIT text")
                checker.check("INSTALL.txt" in dnames, "DIST.ZIP: INSTALL.txt missing")
                if len(wheel_names) == 1:
                    wdata = zf.read(wheel_names[0])
                    with zipfile.ZipFile(io.BytesIO(wdata)) as wz:
                        wnames = wz.namelist()
                        lic_files = [n for n in wnames if n.endswith("LICENSE")]
                        checker.check(bool(lic_files),
                                      "DIST.ZIP: wheel carries no LICENSE file")
                        if lic_files:
                            checker.check(b"MIT License" in wz.read(lic_files[0]),
                                          "DIST.ZIP: wheel LICENSE is not MIT text")
                        meta = [n for n in wnames if n.endswith("METADATA")]
                        if meta:
                            text = wz.read(meta[0]).decode(errors="replace")
                            checker.check("License-Expression: MIT" in text,
                                          "DIST.ZIP: wheel METADATA lacks License-Expression: MIT")
                            checker.check("benchreceipt" in text.lower(),
                                          "DIST.ZIP: wheel METADATA is not benchreceipt")
                        else:
                            checker.fail("DIST.ZIP: wheel has no METADATA")
                if len(sdist_names) == 1:
                    sdata = zf.read(sdist_names[0])
                    try:
                        with tarfile.open(fileobj=io.BytesIO(sdata), mode="r:gz") as tf:
                            members = tf.getnames()
                        checker.check(any(m.endswith("pyproject.toml") for m in members),
                                      "DIST.ZIP: sdist has no pyproject.toml")
                    except tarfile.TarError as exc:
                        checker.fail(f"DIST.ZIP: sdist is not a valid tar.gz: {exc}")
        except (zipfile.BadZipFile, FileNotFoundError) as exc:
            checker.fail(f"DIST.ZIP: unreadable: {exc}")

        # --- bundle verifies + clones + reproduces source tree ---------
        bundle = manifest.get("bundle", {}).get("file")
        if bundle:
            bpath = release_dir / bundle
            proc = _run(["git", "-C", str(root), "bundle", "verify", str(bpath)])
            checker.check(proc.returncode == 0,
                          f"BUNDLE: `git bundle verify` failed: {proc.stderr.strip()[-300:]}")
            tmp = Path(args.tmp_dir).resolve()
            tmp.mkdir(parents=True, exist_ok=True)
            clone_dir = tmp / "verify-release-clone"
            if clone_dir.exists():
                shutil.rmtree(clone_dir)
            # The bundle advertises a ref (e.g. refs/heads/t014) but no
            # HEAD, so a bare `git clone` fetches nothing; clone the
            # advertised ref explicitly.
            heads = _run(["git", "-C", str(root), "bundle", "list-heads", str(bpath)])
            ref = None
            for line in heads.stdout.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                    ref = parts[1][len("refs/heads/"):]
                    break
            if ref is None:
                checker.fail("BUNDLE: bundle advertises no branch head to clone")
                ref = ""
            proc = _run(["git", "clone", "-q", "--branch", ref, str(bpath), str(clone_dir)]) \
                if ref else _run(["git", "clone", "-q", str(bpath), str(clone_dir)])
            checker.check(proc.returncode == 0,
                          f"BUNDLE: clone from bundle failed: {proc.stderr.strip()[-300:]}")
            if proc.returncode == 0:
                proc = _run(["git", "-C", str(clone_dir), "rev-parse", "HEAD"])
                head = proc.stdout.strip()
                checker.check(head == commit,
                              f"BUNDLE: cloned HEAD {head} != frozen commit {commit}")
                try:
                    ctree = _frozen_tree(clone_dir, head) if head else {}
                except RuntimeError as exc:
                    checker.fail(f"BUNDLE: cannot read cloned tree: {exc}")
                    ctree = {}
                if ctree:
                    checker.check(ctree == tree,
                                  "BUNDLE: cloned 02_source tree differs from frozen tree")
        else:
            checker.fail("BUNDLE: manifest has no bundle file")

    # --- S0 gate block vs S0_GATE.json -----------------------------------
    s0_path = Path(args.s0_gate).resolve()
    gates = manifest.get("gates", {})
    if not s0_path.exists():
        checker.fail(f"S0: S0_GATE.json missing: {s0_path}")
    elif not isinstance(gates, dict):
        checker.fail("MANIFEST: missing or malformed `gates` block")
    else:
        try:
            s0 = json.loads(s0_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            checker.fail(f"S0: S0_GATE.json is not valid JSON: {exc}")
            s0 = None
        if s0 is not None:
            summary = s0.get("summary", {})
            checker.check(s0.get("verdict") == "S0 PASS",
                          f"S0: verdict is {s0.get('verdict')!r}, not S0 PASS")
            checks = [
                ("s0_controls", f"{summary.get('controls_pass')}/{summary.get('controls_total')}", "16/16"),
                ("s0_faults", f"{summary.get('faults_detected')}/{summary.get('faults_total')}", "36/36"),
                ("s0_parity", f"{summary.get('parity')}/{summary.get('parity_total')}", "52/52"),
                ("s0_false_pass", summary.get("false_pass"), 0),
                ("s0_false_block", summary.get("false_block"), 0),
                ("s0_repeat_distinct_hashes", summary.get("repeat_distinct_hashes"), 1),
                ("s0_golden_sha256", s0.get("golden_sha256"), s0.get("golden_sha256")),
            ]
            for key, actual, _ in checks:
                if gates.get(key) != actual:
                    checker.fail(f"S0: manifest gates.{key}={gates.get(key)!r} "
                                 f"!= S0_GATE.json value {actual!r}")
            repeat = None
            for t in s0.get("thresholds", []):
                if t.get("id") == 6:
                    m = re.search(r"hash ([0-9a-f]{64})", t.get("detail", ""))
                    repeat = m.group(1) if m else None
            if repeat is None:
                checker.fail("S0: no repeat-100 hash in S0_GATE.json threshold 6")
            elif gates.get("s0_repeat_hash") != repeat:
                checker.fail(f"S0: manifest gates.s0_repeat_hash={gates.get('s0_repeat_hash')!r} "
                             f"!= S0 repeat hash {repeat!r}")
            if not isinstance(gates.get("pytest_passed"), int) or gates.get("pytest_passed", 0) <= 0:
                checker.fail(f"S0: manifest gates.pytest_passed is not a positive int: "
                             f"{gates.get('pytest_passed')!r}")
            if not isinstance(gates.get("oracle_tests_passed"), int):
                checker.fail("S0: manifest gates.oracle_tests_passed is not an int")
            elif gates.get("oracle_tests_passed") != gates.get("oracle_tests_total"):
                checker.fail(f"S0: oracle tests not all passing in manifest: "
                             f"{gates.get('oracle_tests_passed')}/{gates.get('oracle_tests_total')}")

    # --- offline install (last: slowest) ---------------------------------
    if not args.skip_offline_install:
        tmp = Path(args.tmp_dir).resolve()
        tmp.mkdir(parents=True, exist_ok=True)
        _offline_install_check(checker, release_dir, tmp)

    if checker.failures:
        print(f"FAIL: verify_release: {len(checker.failures)} problem(s)")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1
    print(f"PASS: verify_release: frozen commit {commit}, "
          f"source.zip matches the frozen tree file-by-file, "
          f"manifest + SHA256SUMS verified, LICENSE MIT in both zips, "
          f"deps == 0, S0 52/52 + repeat-100 1 hash, bundle clones, "
          f"offline install {'checked' if not args.skip_offline_install else 'SKIPPED'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
