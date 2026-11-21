# P027 BenchReceipt — Environment Facts (T001)

Measured live on this VM in this session. Do NOT copy historical values —
every number below is the raw output of a command run for T001.

- **Measured:** 2026-11-17 ~07:05–07:15 GMT
- **Workspace real path:** `/home/hatch/workspace/p027-benchreceipt`
- **OS:** Ubuntu 24.04.5 LTS (Noble Numbat), `hatch-image 0.1.46`
- **Kernel / arch:** Linux 7.0.0-44-generic x86_64

## Raw command output

### `python3 --version` (exit 0)

```text
Python 3.12.3
```

### `python3 -c "import sys,platform; print(sys.version); print(platform.platform()); print(platform.machine())"` (exit 0)

```text
3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
Linux-7.0.0-44-generic-x86_64-with-glibc2.39
x86_64
```

Python patch version locked for this project: **3.12.3**. Binary: `/usr/bin/python3`.

### `node --version` / `npm --version` (exit 0)

```text
v24.22.1
10.9.4
```

Node patch version locked for the Oracle: **v24.22.1**. Binaries:
`/usr/bin/node`, `/opt/hatch-image/bin/npm`.

### `git --version` (exit 0)

```text
git version 2.43.0
```

### `uname -a` (exit 0)

```text
Linux htch-runtime 7.0.0-44-generic #1 SMP PREEMPT_DYNAMIC Fri Nov  6 01:23:31 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

### CPU — `nproc` + `/proc/cpuinfo` (exit 0)

```text
4
model name	: AMD EPYC 9D25 126-Core Processor
```

4 vCPU visible to this VM.

### RAM — `free -h` (exit 0)

```text
               total        used        free      shared  buff/cache   available
Mem:           7.7Gi       7.1Gi       168Mi        92Mi       851Mi       662Mi
Swap:          1.0Gi       451Mi       572Mi
```

**Memory is tight: only 168 MiB free at measurement time.** Keep commands
light; full pytest runs must set `TMPDIR` to a persistent-disk directory
under the work dir (e.g. `/home/hatch/workspace/p027-benchreceipt/.tmp`),
because `/tmp` is a small tmpfs (see below).

### Disk — `df -h .` and `df -h /tmp` (exit 0)

```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/mapper/rv  150G   23G  127G  16% /home/hatch

Filesystem      Size  Used Avail Use% Mounted on
tmpfs           512M   40M  473M   8% /tmp
```

127 GiB free on the persistent disk; `/tmp` is a 512 MiB tmpfs — do not use
it for pytest caches or large intermediates.

### `/etc/os-release` (exit 0)

```text
PRETTY_NAME="Ubuntu 24.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.5 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo
IMAGE_ID="hatch-image"
IMAGE_VERSION="0.1.46"
```

## pytest availability

System `python3` has **no pytest** (`/usr/bin/python3: No module named pytest`).

A project-local venv was created for T001 and pytest installed into it:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest --version
```

```text
pytest 9.2.0
Python 3.12.3
```

- venv: `/home/hatch/workspace/p027-benchreceipt/.venv` (git-ignored, not part of the deliverable)
- pytest **9.2.0** installed from PyPI in this session; pinned in
  `02_source/requirements-dev.lock` as `pytest==9.2.0`.
- `python3 -m pytest --collect-only -q` run from the venv after the
  skeleton was created: see acceptance log in the T001 handoff report.
  System-python pytest remains NOT installed; all test commands in this
  project must use `.venv/bin/python -m pytest` (or an equivalent venv).

## Editable install validation (T001)

`pip install -e 02_source` in the venv validates `pyproject.toml`:

- First attempt FAILED (setuptools/PEP 639): the
  `License :: OSI Approved :: MIT License` classifier conflicts with
  `license = "MIT"` as a license expression. Fixed by removing that one
  classifier line from `02_source/pyproject.toml`; the MIT license itself
  is unchanged.
- After the fix: install succeeds; `import benchreceipt` resolves to
  `02_source/src/benchreceipt/__init__.py`, `__version__ == "0.1.0"`.
- `.venv/bin/python -m pytest --collect-only -q 02_source/tests`:
  `1 test collected in 0.01s` (exit 0).
- `.venv/bin/python -m pytest -q 02_source/tests`:
  `1 passed in 0.01s` (exit 0) — skeleton smoke test only, not product
  evidence.

## Browser availability

No local browser binary on this VM:

```text
$ which chromium chromium-browser google-chrome firefox
(no output — none found; no chromium/firefox binary in /usr/bin)
```

Browser availability on this VM: **NOT_TESTED / not installed**. UI
screenshots and browser checks (T010/T012) must use the main agent's
browser or be recorded as NOT_TESTED on this VM — do not claim a local
browser check passed.

## Network restrictions

- Dev installs are allowed: `curl -sI https://pypi.org` returned
  `HTTP/1.1 200 OK` (via the VM proxy) in this session, and `pip install
  pytest` succeeded from PyPI.
- **Product runtime must be offline**: BenchReceipt itself makes no
  network requests, calls no GitHub API, and needs no OAuth/API key/LLM.
  That property is NOT_VERIFIED yet — it is proven by the offline checks
  in T011/T012, not by this file.

## Platforms not tested in this session

- Windows: **NOT_TESTED** (no Windows host available; Sam's PC is OFF).
- macOS: **NOT_TESTED**.
- Do not claim cross-platform pass until T012 records a real run.

## Gate result

- Python 3.12.3 — VERIFIED live. Node v24.22.1 — VERIFIED live.
- Git 2.43.0 — VERIFIED live. pytest 9.2.0 in project venv — VERIFIED live.
- Environment gate for T001: **PASS**. T002 may proceed on this toolchain.
