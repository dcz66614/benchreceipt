"""Report parsers for BenchReceipt (P027-T005).

``reports/junit.py`` parses JUnit XML and ``reports/lcov.py`` parses LCOV
coverage files, both into small standardised summaries. The verifier
(``benchreceipt.verify``) calls these instead of trusting any summary a
receipt carries; the parsers are the ground truth for report content.

Both modules are standard library only, make no network access, and
read nothing outside the single file they are given.
"""
