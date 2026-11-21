"""Wheel-content regression test for T014-F1 (P027-T014-FIX).

T014-F1: the released wheel/sdist shipped no ``schemas/``, so an
offline-installed ``benchreceipt`` could print ``--help`` but
``capture``/``verify``/``report`` failed with exit 4 (``schema
directory not found``). Root cause: ``pyproject.toml`` had no
``[tool.setuptools.package-data]``, although
``schema.py::_schemas_dir()`` documents a packaged Layout 2
(``schemas/`` shipped as package data next to the module).

Why the stanza alone was not sufficient (verified 2026-11-18):
setuptools resolves package-data globs relative to the package
directory (``src/benchreceipt/``) and silently drops globs that
match nothing, so the finding's literal ``["schemas/*.json"]``
stanza did nothing while the schemas lived at ``02_source/schemas/``
(outside the package); ``["../schemas/*.json"]`` also matched
nothing, and ``["../../schemas/*.json"]`` only landed the files in
the sdist and in ``build/lib`` outside the package, where
``install_lib`` never picks them up for the wheel. The fix is
therefore the stanza *plus* the schemas living inside the package
at ``src/benchreceipt/schemas/`` (byte-identical move; frozen
schema contents unchanged), which is exactly what this test pins:
the built wheel must contain ``benchreceipt/schemas/*.json`` for
every schema file the product loads.

The test builds real wheels (``python -m build --no-isolation``)
from scratch copies of the source tree, using the pinned offline
build toolchain cached by ``scripts/freeze_release.py`` (the five
wheels under ``.tmp/t014-freeze/piptest/`` / ``run/run1/build-deps/``).
The project venv has no setuptools/build, so without that cache the
test fails closed with an explicit message instead of skipping.
No network is used anywhere: the build runs ``--no-isolation`` with
``PYTHONPATH`` pointed at the unpacked toolchain.

Negative control (runs on every invocation, not just once by hand):
the same tree is built a second time with the
``[tool.setuptools.package-data]`` stanza removed, and the test
asserts that wheel contains *no* schemas. If the stanza ever
regresses, the first test fails; if this test itself ever stopped
catching the defect, the negative control would fail first.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from benchreceipt.schema import SCHEMA_FILES

SRC_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SRC_ROOT.parent

# Files the wheel build needs (nothing else is copied into the scratch
# tree, so the build cannot be confused by stale build/ or __pycache__).
_TREE_FILES = ("pyproject.toml", "README.md", "LICENSE")
_TREE_DIRS = ("src",)

# The five pinned build-toolchain wheels (freeze_release.py BUILD_DEPS).
_TOOLCHAIN_WHEELS = (
    "setuptools-",
    "wheel-",
    "build-",
    "pyproject_hooks-",
    "packaging-",
)

# Cache locations where freeze_release.py leaves the pinned toolchain
# wheels (first hit wins per wheel name).
_TOOLCHAIN_CACHE_DIRS = (
    REPO_ROOT / ".tmp" / "t014-freeze" / "piptest",
    REPO_ROOT / ".tmp" / "t014-freeze" / "run" / "run1" / "build-deps",
    REPO_ROOT / ".tmp" / "t014-freeze" / "run" / "run2" / "build-deps",
)


def _schema_files() -> list[Path]:
    """Frozen schema files, enumerated from the schemas dir (never hardcoded)."""
    schemas_dir = SRC_ROOT / "src" / "benchreceipt" / "schemas"
    files = sorted(schemas_dir.glob("*.json"))
    assert files, f"no schema JSON files found in {schemas_dir}"
    return files


def _unpack_toolchain(dest: Path) -> Path:
    """Unpack the pinned offline build toolchain into ``dest``; return it.

    Fail closed (no skip) when a toolchain wheel is missing: a wheel
    test that cannot build proves nothing.
    """
    missing: list[str] = []
    found: dict[str, Path] = {}
    for prefix in _TOOLCHAIN_WHEELS:
        for cache in _TOOLCHAIN_CACHE_DIRS:
            matches = sorted(cache.glob(prefix + "*.whl")) if cache.is_dir() else []
            if matches:
                found[prefix] = matches[0]
                break
        else:
            missing.append(prefix.rstrip("-"))
    if missing:
        pytest.fail(
            "offline wheel-build toolchain missing: "
            + ", ".join(missing)
            + "; run `python scripts/freeze_release.py build` once "
            "(it downloads + hash-checks the pinned wheels into "
            ".tmp/t014-freeze/) and re-run this test"
        )
    dest.mkdir(parents=True, exist_ok=True)
    for wheel in found.values():
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(dest)
    return dest


def _copy_source_tree(dest: Path) -> Path:
    """Copy the minimal buildable tree (pyproject + README + LICENSE + src/)."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in _TREE_FILES:
        shutil.copy2(SRC_ROOT / name, dest / name)
    for name in _TREE_DIRS:
        shutil.copytree(
            SRC_ROOT / name,
            dest / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
        )
    return dest


def _strip_package_data_stanza(pyproject: Path) -> None:
    """Remove the [tool.setuptools.package-data] section (negative control).

    If the tree already has no stanza (the true pre-fix state), there
    is nothing to strip: the copied tree is already the broken control.
    """
    text = pyproject.read_text(encoding="utf-8")
    stripped, n = re.subn(
        r"^\[tool\.setuptools\.package-data\]\n(?:^(?!\[).*\n?)*",
        "",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        return
    assert "[tool.setuptools.package-data]" not in stripped
    pyproject.write_text(stripped, encoding="utf-8")


def _build_wheel(src_dir: Path, buildenv: Path, out_dir: Path) -> Path:
    """Build one wheel with the real (freeze-script) build command, offline."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(buildenv) + (
        ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["TMPDIR"] = str(out_dir.parent)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation",
         "--outdir", str(out_dir), "."],
        cwd=src_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"wheel build failed (exit {proc.returncode}) in {src_dir}:\n"
            f"--- stdout ---\n{proc.stdout[-2000:]}\n"
            f"--- stderr ---\n{proc.stderr[-2000:]}"
        )
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected 1 wheel in {out_dir}, got {wheels}"
    return wheels[0]


def _wheel_members(wheel: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


@pytest.fixture(scope="module")
def built_wheels(tmp_path_factory):
    """Build the fixed wheel and the stanza-less (pre-fix) wheel once."""
    work = tmp_path_factory.mktemp("wheel-contents")
    buildenv = _unpack_toolchain(work / "buildenv")
    fixed_src = _copy_source_tree(work / "fixed-src")
    fixed_wheel = _build_wheel(fixed_src, buildenv, work / "fixed-out")
    broken_src = _copy_source_tree(work / "broken-src")
    _strip_package_data_stanza(broken_src / "pyproject.toml")
    broken_wheel = _build_wheel(broken_src, buildenv, work / "broken-out")
    return {
        "work": work,
        "fixed": fixed_wheel,
        "broken": broken_wheel,
    }


def test_wheel_contains_every_loaded_schema(built_wheels):
    """The fixed wheel ships benchreceipt/schemas/*.json, byte-identical."""
    schema_files = _schema_files()
    # Cross-check: every file the product loads (SCHEMA_FILES values)
    # is among the enumerated files — the dir listing cannot go stale.
    loaded = set(SCHEMA_FILES.values())
    enumerated = {p.name for p in schema_files}
    assert loaded <= enumerated, (
        f"schema.py loads {sorted(loaded - enumerated)} "
        "not present in src/benchreceipt/schemas/"
    )
    members = _wheel_members(built_wheels["fixed"])
    missing = []
    for schema_file in schema_files:
        member = f"benchreceipt/schemas/{schema_file.name}"
        if member not in members:
            missing.append(member)
            continue
        got = hashlib.sha256(members[member]).hexdigest()
        want = hashlib.sha256(schema_file.read_bytes()).hexdigest()
        assert got == want, f"wheel member {member} differs from source ({got} != {want})"
    assert not missing, f"fixed wheel is missing packaged schemas: {missing}"


def test_wheel_without_package_data_contains_no_schemas(built_wheels):
    """Negative control: without the stanza the wheel ships no schemas.

    This is the T014-F1 defect itself. If this assertion ever stops
    failing on a stanza-less build, the positive test above has lost
    its power to catch the regression.
    """
    schema_files = _schema_files()
    members = _wheel_members(built_wheels["broken"])
    present = [
        f"benchreceipt/schemas/{p.name}"
        for p in schema_files
        if f"benchreceipt/schemas/{p.name}" in members
    ]
    assert not present, (
        "stanza-less wheel unexpectedly contains schemas "
        f"{present} — negative control broken, the positive test "
        "would no longer catch T014-F1"
    )


def test_schemas_dir_resolves_in_packaged_layout(built_wheels):
    """_schemas_dir() finds Layout 2 in a simulated installed wheel.

    The fixed wheel is unpacked to a directory with no ``schemas/``
    next to it (so the repo/editable Layout 1 cannot fire), and
    ``benchreceipt`` is imported from the unpacked wheel in a
    subprocess whose PYTHONPATH holds only that directory.
    """
    work = built_wheels["work"]
    unpacked = work / "unpacked"
    with zipfile.ZipFile(built_wheels["fixed"]) as zf:
        zf.extractall(unpacked)
    empty_cwd = work / "empty-cwd"
    empty_cwd.mkdir(exist_ok=True)
    probe = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "import benchreceipt\n"
        "from benchreceipt.schema import _schemas_dir, load_schema\n"
        "unpacked = Path(sys.argv[1])\n"
        "assert Path(benchreceipt.__file__).is_relative_to(unpacked), "
        "benchreceipt.__file__\n"
        "found = _schemas_dir()\n"
        "assert found == unpacked / 'benchreceipt' / 'schemas', found\n"
        "for name in ('run', 'policy', 'result'):\n"
        "    schema = load_schema(name)\n"
        "    assert schema['$id'].startswith('https://benchreceipt.example/schemas/'), schema\n"
        "print(json.dumps({'schemas_dir': str(found), 'module': benchreceipt.__file__}))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(unpacked)
    env.pop("PYTHONHOME", None)
    proc = subprocess.run(
        [sys.executable, "-c", probe, str(unpacked)],
        cwd=empty_cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"packaged-layout probe failed (exit {proc.returncode}):\n"
        f"--- stdout ---\n{proc.stdout[-2000:]}\n"
        f"--- stderr ---\n{proc.stderr[-2000:]}"
    )
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["schemas_dir"] == str(unpacked / "benchreceipt" / "schemas")
