"""Run tests, execute the native demo, and open its dashboard."""
import os
from pathlib import Path
import subprocess
import sys
import time
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compilerlab.backend import auto_compiler


def main():
    os.chdir(ROOT)
    if not auto_compiler():
        if os.name == 'nt':
            from bootstrap import install
            install()
        else:
            print('Install GCC or Clang, then rerun. The GPU toolkit is not required.')
            return 2
    temp = ROOT / '.cache' / 'tmp'
    temp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    tests = subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],env=env)
    if tests.returncode: return tests.returncode
    folder = ROOT / 'runs' / time.strftime('demo-%Y%m%d-%H%M%S')
    result = subprocess.run([sys.executable,'verifylab.py','demo','--count','24','--jobs','2','--out',str(folder)],env=env)
    if result.returncode == 0:
        webbrowser.open((folder/'campaign/index.html').as_uri())
        print('Completed. Read STUDY_GUIDE.md and the saved evidence at', folder)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
