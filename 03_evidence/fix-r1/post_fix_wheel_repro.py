"""Post-fix wheel probe (FIX-R1): the reviewer R1 probe with FIXED expectations.

Same probe (real capture + benchreceipt.verify.evaluate from the installed
wheel, both after fields deleted), but the legacy shape must now be UNBOUND
+ MISSING_FIELD (jobs_verified 0), not BOUND_PASS. The original receipts
must still be UNBOUND + SOURCE_MUTATED_DURING_RUN.
"""
from pathlib import Path
import os, json, subprocess, tempfile, sys, hashlib
from benchreceipt.capture import capture
from benchreceipt.verify import evaluate
from benchreceipt.schema import validate_against_schema

P = {
 "schema_version":1, "source_mode":"event_sha", "expected_workflow":"local",
 "required_jobs":["unit-linux-py312"],"min_tests":1,"require_clean_source_after":True,
 "same_tree_across_jobs":True,"same_run_id":True,"same_run_attempt":True,
 "reports":{"junit":"required","lcov":"optional"}
}
XML = '<testsuites><testsuite name="s" tests="1" failures="0" errors="0" skipped="0"><testcase name="ok" classname="s"/></testsuite></testsuites>'

def git(repo,*args):
 p=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,check=True)
 return p.stdout.strip()

with tempfile.TemporaryDirectory(prefix='p027_repro_') as d:
 for case in ('clean_checkout','empty_commit'):
  repo=Path(d)/case; repo.mkdir()
  git(repo,'init','-q');git(repo,'config','user.email','audit@example.invalid');git(repo,'config','user.name','Audit')
  (repo/'app.py').write_text('VALUE = 1\n');git(repo,'add','.');git(repo,'commit','-qm','base')
  first=git(repo,'rev-parse','HEAD')
  if case == 'clean_checkout':
   (repo/'app.py').write_text('VALUE = 2\n');git(repo,'add','.');git(repo,'commit','-qm','next')
   new=git(repo,'rev-parse','HEAD');git(repo,'checkout','-q',first)
   action="subprocess.run(['git','checkout','-q',"+repr(new)+"],check=True)"
  else:
   action="subprocess.run(['git','commit','-q','--allow-empty','-m','changed during run'],check=True)"
  cmd="import subprocess; " + action + "; open('junit.xml','w').write("+repr(XML)+")"
  result=capture(job_id='unit-linux-py312',matrix={'os':'ubuntu-latest','python':'3.12'},argv=[sys.executable,'-c',cmd],repo_path=repo,cwd=repo,junit_path='junit.xml',env={})
  original=evaluate(P,first,repo/'.benchreceipt'/'evidence')
  file=repo/'.benchreceipt'/'evidence'/'unit-linux-py312'/'receipt.json'
  data=json.loads(file.read_text())
  after=(data['git'].get('head_sha_after'),data['git'].get('tree_sha_after'))
  for k in ('head_sha_after','tree_sha_after'):
   data['git'].pop(k,None)
  validate_against_schema(data,'run')
  file.write_text(json.dumps(data,sort_keys=True)+'\n')
  legacy=evaluate(P,first,repo/'.benchreceipt'/'evidence')
  print(json.dumps({'case':case,'actual_final_head':git(repo,'rev-parse','HEAD'), 'original_expected_source_sha':first,'was_mutated_during_run':result.source_mutated_during_run, 'original_status':original['status'],'original_reason_codes':original['reason_codes'],'recorded_after_sha':after[0], 'legacy_shape_schema_valid':True,'no_after_status':legacy['status'],'no_after_reason_codes':legacy['reason_codes'],'no_after_jobs_verified':legacy['jobs_verified'], 'receipt_sha256':hashlib.sha256(file.read_bytes()).hexdigest()},sort_keys=True))
  assert original['status']=='UNBOUND' and 'SOURCE_MUTATED_DURING_RUN' in original['reason_codes']
  assert legacy['status']=='UNBOUND' and legacy['reason_codes']==['MISSING_FIELD'] and legacy['jobs_verified']==0
print('POST_FIX_WHEEL_REPRO: 2/2 ORIGINAL FIXES PASS; 2/2 LEGACY-SHAPE FAIL-CLOSED (UNBOUND + MISSING_FIELD)')
