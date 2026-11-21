import subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, "02_source/src")
from benchreceipt.capture import capture as do_capture, CaptureError
tmp = Path(tempfile.mkdtemp(prefix="t013-r9c2-", dir="/tmp/t013-repro"))
repo = tmp/"repo"; repo.mkdir()
def run(cmd, cwd): subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
run(["git","init","-q","-b","main"], repo)
run(["git","config","user.email","r9c@example.invalid"], repo); run(["git","config","user.name","r9c"], repo)
(repo/"test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
(repo/".gitignore").write_text(".benchreceipt/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
run(["git","add","."], repo); run(["git","commit","-qm","x"], repo)
huge = ('<?xml version="1.0"?>\n<testsuite name="s" tests="' + "9"*5000 +
        '" failures="0" errors="0" skipped="0"><testcase classname="t" name="t0"/></testsuite>\n')
writer = "import sys,pathlib; pathlib.Path('.benchreceipt/out').mkdir(parents=True, exist_ok=True); open('.benchreceipt/out/junit.xml','w').write(sys.argv[1])"
try:
    res = do_capture(job_id="unit-linux-py312", matrix={"os":"ubuntu-latest","python":"3.12"},
        argv=[sys.executable,"-c",writer,huge], junit_path=".benchreceipt/out/junit.xml",
        repo_path=repo, cwd=repo)
    print("R9c capture huge-attr junit -> receipt written, junit key present:", "junit" in res.receipt)
except CaptureError as e:
    print("R9c capture huge-attr junit -> CaptureError (clean):", str(e)[:120])
except ValueError as e:
    print("R9c capture huge-attr junit -> ValueError propagates (not CaptureError):", type(e).__name__, str(e)[:100])
except Exception as e:
    print("R9c capture huge-attr junit ->", type(e).__name__, str(e)[:120])
# CLI-level: same via benchreceipt capture
p = subprocess.run([sys.executable,"-m","benchreceipt","capture","--job","unit-linux-py312",
  "--matrix","os=ubuntu-latest,python=3.12","--junit",".benchreceipt/out/junit.xml","--",
  sys.executable,"-c",writer,huge], cwd=repo, capture_output=True, text=True, timeout=60)
print("R9c CLI capture exit:", p.returncode, "| stderr:", p.stderr.strip()[:200])
