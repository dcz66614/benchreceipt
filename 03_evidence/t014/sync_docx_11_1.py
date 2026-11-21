#!/usr/bin/env python3
"""Sync PROJECT_BOOK.docx §11.1 redaction bullet to the widened F-09 list.

T014 doc follow-up: the MD (§11.1) was updated from the old
token/password/secret/api-key wording to the widened SECRET_HINTS list
(FIX-R13a / F-09, matching 02_source/src/benchreceipt/command.py).
This script applies the identical replacement to the DOCX paragraph
(index 262, verified by inspection) using run-level replacement so
formatting survives, and fails loudly if the paragraph does not contain
the old wording. Not a spec change: no SPEC_VERSION bump.

Usage (from the repo root, project .venv):
    ../.venv/bin/python 03_evidence/t014/sync_docx_11_1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
DOCX = ROOT / "01_spec" / "PROJECT_BOOK.docx"

OLD = "命令参数默认只保存 argv digest 与安全显示串；检测 token/password/secret/api-key 参数并脱敏。"
NEW = ("命令参数默认只保存 argv digest 与安全显示串；检测含 "
       "token/password/secret/api-key/apikey/api_key/key/auth/passwd/pwd/passphrase/credential/private-key/private_key "
       "的参数并脱敏（与 `command.py` 的 `SECRET_HINTS` 一致，FIX-R13a / F-09）。")


def replace_in_para(p, old, new) -> bool:
    for r in p.runs:
        if old in r.text:
            r.text = r.text.replace(old, new)
            return True
    if old in p.text:  # spans runs: rebuild on first run's formatting
        p.runs[0].text = p.text.replace(old, new)
        for r in p.runs[1:]:
            r.text = ""
        return True
    return False


def main() -> int:
    doc = Document(str(DOCX))
    hits = [i for i, p in enumerate(doc.paragraphs) if OLD in p.text]
    if len(hits) != 1:
        print(f"FAIL: expected exactly 1 paragraph with the old wording, found {len(hits)}: {hits}")
        return 1
    idx = hits[0]
    if not replace_in_para(doc.paragraphs[idx], OLD, NEW):
        print(f"FAIL: could not replace in paragraph {idx}")
        return 1
    if OLD in doc.paragraphs[idx].text or NEW not in doc.paragraphs[idx].text:
        print(f"FAIL: post-replacement check failed for paragraph {idx}")
        return 1
    doc.save(str(DOCX))
    print(f"OK: paragraph {idx} updated in {DOCX.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
