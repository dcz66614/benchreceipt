#!/usr/bin/env python3
"""Apply the FIX-R1 (spec v1.2.0, ADR-007) edits to the two spec DOCX
files, mirroring the MD edits in 01_spec/*.md exactly.

Run-level replacement first (preserves bold/lead-in runs); if a target
spans runs, the whole paragraph is rewritten into its first run.
New sections (§8.6 / §11.2) and the new §8.1 table row are inserted
with python-docx; originals are backed up by the caller before running.
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2] / "01_spec"


def replace_in_paragraph(p, pairs):
    # Single pass per pair: str.replace already replaces every
    # occurrence, so no loop is needed (a loop would spin forever
    # when the replacement text still contains the old text).
    for old, new in pairs:
        if old in p.text:
            done = False
            for r in p.runs:
                if old in r.text:
                    r.text = r.text.replace(old, new)
                    done = True
            if not done:
                # Spans runs: rewrite whole paragraph into first run.
                first = p.runs[0]
                first.text = p.text.replace(old, new)
                for r in p.runs[1:]:
                    r.text = ""


def replace_everywhere(doc, pairs):
    for p in doc.paragraphs:
        replace_in_paragraph(p, pairs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    replace_in_paragraph(p, pairs)


def insert_section_before(anchor_para, items):
    """Insert items (text, style) directly before anchor_para, in order.

    Each insert goes immediately before the anchor, so inserting in
    forward order yields the items in order before the anchor.
    """
    for text, style in items:
        anchor_para.insert_paragraph_before(text, style=style)


BOOK_86 = [
    ("8.6 v1.2.0 修订记录（ADR-007，2026-11-18）", "Heading 3"),
    ("原因：终审 R1 发现 P0-R1-01——删掉 git.head_sha_after / git.tree_sha_after 两个可选字段后，e5/e6 的收据在 Python 验证器与 Node Oracle 下均由 UNBOUND 变为 BOUND_PASS（评审方 wheel 脚本与夹具反例两路复现）。根因是 ADR-005 决策 4 保留的旧版兼容规则：两个 after 字段都缺失时退回 dirty/digest 判定，而 clean-tree HEAD 变化对 dirty/digest 不可见。上一轮修复工人证明 e7（按原设计：e5 删掉两个 after 字段）与现有控制夹具 n01 的输入逐字段相同，而 Golden 要求 n01→BOUND_PASS、e7→UNBOUND——verify 是输入的确定性函数，两者不可能输出不同；协调员裁决采用方案 A。",
     "List Bullet"),
    ("变更：benchreceipt.run/v1 的两个 after 字段保持可选（旧格式收据仍可解析，得 UNBOUND 而非 INVALID），只改 description 文字；verify（Python 与 Node Oracle 同步）改为 fail-closed：两个 after 字段都缺失 → UNBOUND + MISSING_FIELD（复用已冻结的 UNBOUND 类 reason code），该 job jobs_verified 为 0，CLI exit 2；只出现其一仍按原有规则判 SOURCE_MUTATED_DURING_RUN。S0 fixtures 增加 e7（legacy clean checkout）与 e8（legacy empty commit），冻结集 50 → 52，植入异常 34 → 36，parity 50/50 → 52/52；同时 builder 给其余 50 个夹具补上 after 字段（值与 before 一致，e5/e6 保持原样），既有 Golden 值未改动。推翻 ADR-005 决策 4。",
     "List Bullet"),
    ("范围：本次修订是唯一获批的规格变更；其余内容仍以 v1.1.0 为准。",
     "List Bullet"),
]

PLAN_112 = [
    ("11.2 v1.2.0 修订记录（ADR-007，2026-11-18）", "Heading 3"),
    ("原因：终审 R1 发现 P0-R1-01——删掉 git.head_sha_after / git.tree_sha_after 两个可选字段后，e5/e6 的收据在 Python 验证器与 Node Oracle 下均由 UNBOUND 变为 BOUND_PASS。根因是 ADR-005 决策 4 保留的旧版兼容规则。e7（按原设计：e5 删掉两个 after 字段）与现有控制夹具 n01 的输入逐字段相同，Golden 却要求 n01→BOUND_PASS、e7→UNBOUND，verify 作为输入的确定性函数不可能输出不同；协调员裁决采用方案 A（放弃“其余 50 个夹具 byte-identical”的旧约束，builder 给全部现有夹具补上 after 字段）。",
     "List Bullet"),
    ("变更：benchreceipt.run/v1 的两个 after 字段保持可选（旧格式收据仍可解析，得 UNBOUND 而非 INVALID），只改 description 文字；verify（Python 与 Node Oracle 同步）改为 fail-closed：两个 after 字段都缺失 → UNBOUND + MISSING_FIELD（复用已冻结的 UNBOUND 类 reason code），该 job jobs_verified 为 0，CLI exit 2；只出现其一仍按原有规则判 SOURCE_MUTATED_DURING_RUN。S0 fixtures 增加 e7/e8，冻结集 50 → 52，植入异常 34 → 36，parity 50/50 → 52/52；其余 50 个夹具重生成时只增加两个 after 字段（值与 before 一致），e5/e6 保持原样；既有 Golden 值未改动。推翻 ADR-005 决策 4。",
     "List Bullet"),
    ("范围：本次修订是唯一获批的规格变更；其余内容仍以 v1.1.0 为准。",
     "List Bullet"),
]


def update_book():
    doc = Document(str(ROOT / "PROJECT_BOOK.docx"))
    # Frontmatter + frozen-values tables (cells).
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text for c in row.cells]
            if cells == ["spec_version", "1.1.0"]:
                replace_in_paragraph(row.cells[1].paragraphs[0], [("1.1.0", "1.2.0")])
            if cells == ["规格版本", "1.1.0"]:
                replace_in_paragraph(row.cells[1].paragraphs[0], [("1.1.0", "1.2.0")])
            if cells == ["FR-07", "检查必需矩阵 job 完整性、重复项和混合身份", "P0", "50 组 S0 fixtures"]:
                replace_in_paragraph(row.cells[3].paragraphs[0], [("50 组", "52 组")])
            if cells[0] == "clean-tree HEAD 变化 / 空提交（e5–e6，v1.1.0 新增）":
                pass  # row insert handled below (table index 9)
            if cells == ["**合计**", "**50**", "**16 正常 + 34 植入异常**"]:
                replace_in_paragraph(row.cells[1].paragraphs[0], [("**50**", "**52**")])
                replace_in_paragraph(row.cells[2].paragraphs[0],
                                     [("**16 正常 + 34 植入异常**", "**16 正常 + 36 植入异常**")])
            if cells == ["植入异常正确检出", "34/34", "S0 Golden"]:
                replace_in_paragraph(row.cells[1].paragraphs[0], [("34/34", "36/36")])
            if cells == ["Production / Oracle parity", "50/50", "Python vs Node"]:
                replace_in_paragraph(row.cells[1].paragraphs[0], [("50/50", "52/52")])
    # §8.1 table: insert legacy row after the e5–e6 row (table index 9).
    table = doc.tables[9]
    e56 = table.rows[10]
    assert e56.cells[0].text.startswith("clean-tree HEAD"), e56.cells[0].text
    new_row = table.add_row()
    tbl = table._tbl
    tbl.remove(new_row._tr)
    e56._tr.addnext(new_row._tr)
    new_row.cells[0].text = "legacy 形状无 after 字段（e7–e8，v1.2.0 新增）"
    new_row.cells[1].text = "2"
    new_row.cells[2].text = "2/2 检出"
    # Body paragraphs.
    for p in doc.paragraphs:
        t = p.text
        if t.startswith("git_head_sha_after / git_tree_sha_after（v1.1.0"):
            replace_in_paragraph(p, [("（见 §5.5）。",
                "（见 §5.5）。v1.2.0 起两个 after 字段都缺失的收据一律 fail-closed 为 UNBOUND + MISSING_FIELD，不得以 dirty/digest 规则通过。")])
        elif t.startswith("v1.1.0（ADR-005，P0-01 修复）："):
            replace_in_paragraph(p, [(
                "两个 after 字段都缺失的收据（v1.1.0 之前写入）仍按旧的 dirty/digest 规则判定。",
                "v1.2.0（ADR-007，P0-R1-01 修复，推翻 ADR-005 决策 4 的旧兼容规则）：两个 after 字段都缺失的收据无法证明运行中 HEAD/tree 未变化，不得 BOUND_PASS：verify 一律记录 MISSING_FIELD（UNBOUND，exit 2），该 job jobs_verified 为 0。两个字段仍保持可选（旧格式收据仍可解析，得 UNBOUND 而非 INVALID），只出现其一时仍按原有规则判定为 SOURCE_MUTATED_DURING_RUN。终审 R1 证实：删掉 e5/e6 的两个 after 字段后，旧 verifier 会把它们误判为 BOUND_PASS；而 e7（legacy clean checkout）与 n01（正常控制）的收据在删字段后逐字段相同，verify 作为输入的确定性函数不可能输出不同——因此旧兼容规则不可保留，方案 A（builder 给全部现有夹具补上 after 字段）是唯一自洽的修复。")])
        elif t == "8.1 50 组合成 fixtures":
            replace_in_paragraph(p, [("50 组合成", "52 组合成")])
        elif t == "植入异常 34/34 检出且 reason code 正确。":
            replace_in_paragraph(p, [("34/34", "36/36")])
        elif t == "生产 / Oracle parity = 50/50。":
            replace_in_paragraph(p, [("50/50", "52/52")])
        elif t == "50 个冻结 S0 fixtures（e5/e6 由 v1.1.0 / ADR-005 增加）。":
            replace_in_paragraph(p, [("50 个冻结 S0 fixtures（e5/e6 由 v1.1.0 / ADR-005 增加）。",
                "52 个冻结 S0 fixtures（e5/e6 由 v1.1.0 / ADR-005 增加；e7/e8 由 v1.2.0 / ADR-007 增加）。")])
        elif t == "S0 的 50/50 结果。":
            replace_in_paragraph(p, [("50/50", "52/52")])
    # Insert §8.6 before the "## 9" heading (first Heading 1/2 after §8.5).
    paras = doc.paragraphs
    anchor = None
    for i, p in enumerate(paras):
        if p.text.startswith("8.5 v1.1.0"):
            # §8.5's last bullet is the 范围 bullet; find the next heading.
            for q in paras[i:]:
                if q.style.name.startswith("Heading") and q.text.startswith("9."):
                    anchor = q
                    break
            break
    assert anchor is not None
    insert_section_before(anchor, BOOK_86)
    doc.save(str(ROOT / "PROJECT_BOOK.docx"))
    print("PROJECT_BOOK.docx updated")


def update_plan():
    doc = Document(str(ROOT / "IMPLEMENTATION_PLAN.docx"))
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text for c in row.cells]
            if cells == ["spec_version", "1.1.0"]:
                replace_in_paragraph(row.cells[1].paragraphs[0], [("1.1.0", "1.2.0")])
            if cells[3:] == ["50 fixtures、Oracle、parity、zero false PASS、100 hash 全通过"]:
                replace_in_paragraph(row.cells[3].paragraphs[0], [("50 fixtures", "52 fixtures")])
            if cells[2:] == ["capture 原型、50 fixtures、Oracle、S0 gate"]:
                replace_in_paragraph(row.cells[2].paragraphs[0], [("50 fixtures", "52 fixtures")])
            if cells == ["`fixtures/s0/`", "50 immutable fixtures", "T004"]:
                replace_in_paragraph(row.cells[1].paragraphs[0], [("50 immutable", "52 immutable")])
    for p in doc.paragraphs:
        t = p.text
        if t == "规格版本： v1.1.0":
            replace_in_paragraph(p, [("1.1.0", "1.2.0")])
        elif t == "权威需求： PROJECT_BOOK.md v1.1.0":
            replace_in_paragraph(p, [("v1.1.0", "v1.2.0")])
        elif t.startswith("S0 固定 50 组案例"):
            replace_in_paragraph(p, [("50 组案例：16 正常 + 34 植入异常；生产/Oracle parity 50/50",
                                      "52 组案例：16 正常 + 36 植入异常；生产/Oracle parity 52/52")])
        elif "T004 50 Fixtures" in t:
            replace_in_paragraph(p, [("T004 50 Fixtures", "T004 52 Fixtures")])
        elif t.startswith("T004 — 50 Fixtures"):
            replace_in_paragraph(p, [("T004 — 50 Fixtures", "T004 — 52 Fixtures")])
        elif t.startswith("目标： 建立 50 个冻结合成案例"):
            replace_in_paragraph(p, [("建立 50 个冻结", "建立 52 个冻结")])
        elif t.startswith("证据： 50 fixture inventory"):
            replace_in_paragraph(p, [("50 fixture inventory、16 controls、34 planted anomalies、50/50 parity",
                                      "52 fixture inventory、16 controls、36 planted anomalies、52/52 parity")])
        elif t.startswith("Golden：50 个 S0 fixtures"):
            replace_in_paragraph(p, [("Golden：50 个", "Golden：52 个")])
        elif t.startswith("50 个 S0 fixture 在 S0 PASS 后冻结"):
            replace_in_paragraph(p, [(
                "50 个 S0 fixture 在 S0 PASS 后冻结（e5/e6 由 v1.1.0 / ADR-005 在 S0 PASS 后增加，冻结集 48 → 50；既有 fixture 与 Golden 值未改动）。",
                "52 个 S0 fixture 在 S0 PASS 后冻结（e5/e6 由 v1.1.0 / ADR-005 在 S0 PASS 后增加，冻结集 48 → 50；e7/e8 由 v1.2.0 / ADR-007 在 S0 PASS 后增加，冻结集 50 → 52；既有 fixture 与 Golden 值未改动）。")])
        elif t == "[ ] S0 50/50、parity 50/50、false PASS 0、false block 0。":
            replace_in_paragraph(p, [("S0 50/50、parity 50/50", "S0 52/52、parity 52/52")])
    paras = doc.paragraphs
    anchor = None
    for i, p in enumerate(paras):
        if p.text.startswith("11.1 v1.1.0"):
            for q in paras[i:]:
                if q.style.name.startswith("Heading") and q.text.startswith("12."):
                    anchor = q
                    break
            break
    assert anchor is not None
    insert_section_before(anchor, PLAN_112)
    doc.save(str(ROOT / "IMPLEMENTATION_PLAN.docx"))
    print("IMPLEMENTATION_PLAN.docx updated")


if __name__ == "__main__":
    update_book()
    update_plan()
