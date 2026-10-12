"""Bounded subprocess execution with disk-backed logs and tree termination."""
import os
from pathlib import Path
import signal
import subprocess
import time


def run(argv, directory, label, timeout=30, env=None, max_bytes=2_000_000):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    outpath, errpath = directory / f'{label}.stdout', directory / f'{label}.stderr'
    result = {'argv': list(map(str, argv)), 'timeout': False, 'output_limit': False,
              'stdout_file': str(outpath), 'stderr_file': str(errpath), 'returncode': None}
    start = time.monotonic()
    try:
        with outpath.open('wb') as out, errpath.open('wb') as err:
            process = subprocess.Popen(result['argv'], stdout=out, stderr=err, cwd=directory,
                                       env=env, start_new_session=(os.name != 'nt'))
            while process.poll() is None:
                result['timeout'] = time.monotonic() - start > timeout
                result['output_limit'] = outpath.stat().st_size + errpath.stat().st_size > max_bytes
                if result['timeout'] or result['output_limit']:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                        if process.poll() is None:
                            process.kill()
                    else:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                    break
                time.sleep(.02)
            result['returncode'] = process.wait()
    except OSError as exc:
        result['infrastructure_error'] = str(exc)
    for key, path in [('stdout', outpath), ('stderr', errpath)]:
        with path.open('rb') as stream:
            result[key] = stream.read(max_bytes).decode('utf-8', errors='replace')
    result['output_limit'] |= outpath.stat().st_size + errpath.stat().st_size > max_bytes
    result['seconds'] = round(time.monotonic() - start, 4)
    return result


def status(result, phase):
    if result.get('infrastructure_error'): return 'INFRASTRUCTURE_ERROR'
    if result['timeout']: return phase + '_TIMEOUT'
    if result['output_limit']: return 'OUTPUT_LIMIT'
    if result['returncode'] != 0:
        if phase == 'COMPILE' and (result['returncode'] < 0 or result['returncode'] >= 0x80000000):
            return 'COMPILER_CRASH'
        return phase + '_ERROR'
    return 'PASS'
