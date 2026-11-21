"""``python -m benchreceipt`` entry point (P027-T008).

Dispatches to the full CLI in :mod:`benchreceipt.cli` (``capture`` /
``verify`` / ``report`` / ``bundle``). The provisional T003 dispatcher
lived here before T008 replaced it.
"""

from __future__ import annotations

from benchreceipt.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
