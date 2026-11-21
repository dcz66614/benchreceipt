"""Skeleton smoke test (P027-T001).

Only proves the package imports and the test harness runs. Real tests
arrive with T002 (schema/canonical) and later tasks. This test must never
be used as evidence for any product behaviour.
"""

from benchreceipt import __version__


def test_package_imports():
    assert __version__ == "0.1.0"
