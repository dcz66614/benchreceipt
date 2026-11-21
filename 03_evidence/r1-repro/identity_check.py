from pathlib import Path
import subprocess, zipfile,hashlib,collections
root=Path('/mnt/data/p027_r1_audit')
z=zipfile.ZipFile('/mnt/data/source.zip')
files={x.filename:x for x in z.infolist() if not x.is_dir()}
repo=root/'repo'
tracked=subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only','HEAD','02_source'],text=True).splitlines()
expected={p.removeprefix('02_source/') for p in tracked}
missing=sorted(expected-files.keys())
extra=sorted(files.keys()-expected)
changed=[]
for name in sorted(expected&files.keys()):
 if (repo/'02_source'/name).read_bytes()!=z.read(name):changed.append(name)
print('source zip counts',len(files),sum(i.file_size for i in files.values()))
print('repo tracked files',len(expected),'missing',len(missing),'extra',len(extra),'content_mismatch',len(changed))
print('missing examples',missing[:15]);print('extra examples',extra[:15]);print('changed examples',changed[:15])
print('frozen commit',subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip())
print('frozen tree',subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD^{tree}'],text=True).strip())
print('git clean',subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip())
