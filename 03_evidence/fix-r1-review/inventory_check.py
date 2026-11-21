#!/usr/bin/env python3
"""FIX-R1 review: 34 key files inventory at frozen commit 66502f6 vs T013 (cfede271).
Reads REVIEW_INDEX.md table, maps migrated schema paths, hashes files at HEAD."""
import hashlib, re, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
idx = (root/"04_review"/"REVIEW_INDEX.md").read_text()
rows=[]
for m in re.finditer(r"\| `([^`]+)` \| `([0-9a-f]{64})` \| (\d+) \| (\d+) \| (yes|no) \|", idx):
    rows.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), m.group(5)))
print(f"T013 inventory rows: {len(rows)}  key=yes: {sum(1 for r in rows if r[4]=='yes')}")
def newpath(p):
    return p.replace("02_source/schemas/", "02_source/src/benchreceipt/schemas/")
def gitblob(commit, path):
    r = subprocess.run(["git","show",f"{commit}:{path}"], cwd=root, capture_output=True)
    return r.stdout if r.returncode==0 else None
out=[]
for (p, oldsha, oldlines, pack, key) in rows:
    np = newpath(p)
    data = gitblob("66502f6", np)
    if data is None:
        out.append((p, np, "MISSING", oldsha, oldlines, pack, key)); continue
    sha = hashlib.sha256(data).hexdigest()
    lines = len(data.decode('utf-8', 'replace').splitlines())
    olddata = gitblob("cfede2711bc54567b918b1f85654c2dd42c30943", p)
    oldsha_now = hashlib.sha256(olddata).hexdigest() if olddata is not None else "?"
    status = "UNCHANGED" if sha==oldsha else ("MOVED+CHANGED" if np!=p else "CHANGED")
    # verify T013 sha matches cfede271 blob
    t013_ok = "OK" if oldsha_now==oldsha else f"MISMATCH(cfede271 blob={oldsha_now[:12]})"
    out.append((p, np, status, sha, lines, pack, key, oldlines, t013_ok))
print(f"{'path':55} {'newpath?':12} {'status':14} {'lines':>5} {'oldlines':>8}  sha-prefix  t013")
for o in out:
    p,np,st,sha,lines,pack,key,oldlines,t013 = o if len(o)==9 else (*o, "", "")
    moved = "MOVED" if np!=p else "-"
    print(f"{p:55} {moved:12} {st:14} {lines:>5} {oldlines:>8}  {sha[:12] if sha!='MISSING' else 'MISSING':12} {t013}")
print()
print("SUMMARY: unchanged=%d changed=%d moved+changed=%d missing=%d" % (
    sum(1 for o in out if o[2]=="UNCHANGED"), sum(1 for o in out if o[2]=="CHANGED"),
    sum(1 for o in out if o[2]=="MOVED+CHANGED"), sum(1 for o in out if o[2]=="MISSING")))
print("key files: %d" % sum(1 for o in out if o[6]=='yes'))
# full table to file
with open(root/"03_evidence/fix-r1-review/inventory_table.md","w") as f:
    f.write("# FIX-R1 inventory: T013 34 key files vs frozen 66502f6\n\n")
    f.write("| T013 path | New path (66502f6) | Status vs cfede271 | SHA-256 (66502f6) | Lines 66502f6 | Lines T013 | Pack | Key |\n|---|---|---|---|---|---|---|---|\n")
    for o in out:
        p,np,st,sha,lines,pack,key,oldlines,t013 = o
        f.write(f"| `{p}` | `{np}` | {st} | `{sha}` | {lines} | {oldlines} | {pack} | {key} |\n")
print("wrote inventory_table.md")
