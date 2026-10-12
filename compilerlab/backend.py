"""Compiler adapters and evidence collection. A mismatch is a candidate finding."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import time

from . import __version__, emit, ir
from .process import run, status

ROOT = Path(__file__).resolve().parents[1]
GPU_WORKER = Path(__file__).with_name('gpu_worker.py')


def auto_compiler():
    for name in ('g++', 'clang++'):
        if shutil.which(name): return [shutil.which(name)]
    zig = ROOT / '.tools/zig-x86_64-windows-0.14.1/zig.exe'
    return [str(zig), 'c++'] if zig.is_file() else None


def default_profiles():
    compiler = auto_compiler()
    if compiler:
        return [{'name': f'host-{opt}', 'backend': 'cpp', 'command': compiler, 'flags': [f'-{opt}']} for opt in ('O0', 'O2')]
    return [{'name': 'model-only', 'backend': 'model', 'command': [], 'flags': []}]


def environment():
    env = os.environ.copy()
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    temp = cache / 'tmp'
    temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp),
               ZIG_GLOBAL_CACHE_DIR=str(cache / 'zig-global'), ZIG_LOCAL_CACHE_DIR=str(cache / 'zig-local'))
    return env


def normalize(profile):
    p = dict(profile)
    for key in ('command', 'flags'):
        if isinstance(p.get(key), list): p[key] = list(p[key])
    if p.get('backend') not in ('model', 'cpp', 'cuda', 'ptx-jit', 'ptx-cubin', 'ptx-direct'):
        raise ValueError('Unknown backend')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', p.get('name', '')):
        raise ValueError('Profile name must be a safe identifier')
    for key in ('command', 'flags'):
        p.setdefault(key, [])
        if not isinstance(p[key], list) or not all(isinstance(x, str) for x in p[key]):
            raise ValueError(f'{key} must be an argument array')
    p.setdefault('arch', 'sm_75')
    if p['arch'] != 'auto' and not re.fullmatch(r'sm_[0-9]{2,3}', p['arch']):
        raise ValueError('Expected auto or an architecture such as sm_75')
    p.setdefault('repeat', 2)
    p.setdefault('compile_timeout', 180)
    p.setdefault('run_timeout', 30)
    if type(p['repeat']) is not int or not 1 <= p['repeat'] <= 10:
        raise ValueError('repeat must be 1..10')
    for key in ('compile_timeout', 'run_timeout'):
        if not isinstance(p[key], (int, float)) or not 0 < p[key] <= 600:
            raise ValueError('Timeout must be in (0,600]')
    if p.get('fault') not in (None, 'shift-sign', 'drop-last'):
        raise ValueError('Unknown injected fault')
    if p.get('sanitizer') not in (None, 'memcheck', 'racecheck', 'initcheck', 'synccheck'):
        raise ValueError('Unknown sanitizer')
    if p.get('sanitizer') and p['backend'] in ('cpp', 'model'):
        raise ValueError('Compute Sanitizer requires a GPU backend')
    if p['backend'] not in ('model', 'ptx-direct') and not p['command']:
        p['command'] = auto_compiler() or ['g++'] if p['backend'] == 'cpp' else ['nvcc']
    if p['command']:
        p['command'][0] = shutil.which(p['command'][0]) or p['command'][0]
    # This stamp becomes part of the job identity and is checked on resume.
    if p['command'] and Path(p['command'][0]).is_file():
        with Path(p['command'][0]).open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()
        if p.get('compiler_sha256') and p['compiler_sha256'] != actual:
            raise ValueError('Compiler binary changed since the campaign was created')
        p['compiler_sha256'] = actual
    return p


def compare(expected, output):
    try:
        values = [int(x) for x in output.split()]
        if len(values) != len(expected) or any(not 0 <= x <= ir.MASK for x in values):
            raise ValueError()
    except ValueError:
        return {'status': 'PROTOCOL_ERROR'}
    diff = [{'index': i, 'expected': x, 'actual': y} for i, (x, y) in enumerate(zip(expected, values)) if x != y]
    return {'status': 'WRONG_RESULT' if diff else 'PASS', 'actual': values, 'differences': diff}


def execute(case, profile, directory):
    ir.validate(case)
    p = dict(profile)
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    env = environment()
    backend = p['backend']
    fault = p.get('fault')
    expected = ir.reference(case)
    report = {'schema': 2, 'engine': __version__, 'case_sha256': ir.digest(case), 'profile': p,
              'platform': platform.platform(), 'host_arch': platform.machine(), 'python': sys.version,
              'synthetic': bool(fault), 'expected': expected, 'steps': [], 'executions': [],
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    start = time.monotonic()
    (folder / 'case.json').write_text(json.dumps(case, indent=2), encoding='utf-8')
    (folder / 'profile.json').write_text(json.dumps(p, indent=2), encoding='utf-8')
    (folder / 'program.cpp').write_text(emit.source(case, fault=fault), encoding='utf-8')
    (folder / 'program.cu').write_text(emit.source(case, cuda=True, fault=fault), encoding='utf-8')
    (folder / 'kernel.cu').write_text(emit.source(case, cuda=True, fault=fault, device_only=True), encoding='utf-8')
    if case.get('kind', 'map') == 'map':
        (folder / 'reference.ptx').write_text(emit.ptx(case), encoding='utf-8')

    def finish(code, **extra):
        report.update(status=code, seconds=round(time.monotonic() - start, 4), **extra)
        report['artifacts'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in folder.iterdir() if path.is_file() and path.name != 'report.json'}
        report['finding_signature'] = ir.digest({'status': code, 'case': report['case_sha256'], 'profile': p})
        (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report

    if backend == 'model':
        actual = list(expected)
        if fault:
            # Explicit model fault support for machines without any native toolchain.
            altered = dict(case)
            if fault == 'drop-last':
                altered['ops'] = case['ops'][:-1]
                actual = ir.reference(altered)
            else:
                actual = []
                for initial in case['inputs']:
                    x = initial
                    for op, k in case['ops']:
                        if op == 'shr' and k and x & 0x80000000:
                            x = ((x >> k) | (ir.MASK << (32-k))) & ir.MASK
                        else:
                            x = ir.reference({'schema': 1, 'ops': [[op,k]], 'inputs':[x]})[0]
                    actual.append(x)
                if case.get('kind') == 'reduce': actual = [sum(actual) & ir.MASK]
        result = compare(expected, '\n'.join(map(str, actual)))
        return finish(result.pop('status'), **result, verification_scope='harness-model-only')

    if backend != 'cpp':
        probe = run([sys.executable, str(GPU_WORKER), '--probe'], folder, 'gpu-probe', 15, env)
        report['steps'].append(probe)
        if status(probe, 'PROBE') != 'PASS':
            return finish('SKIP_GPU_UNAVAILABLE')
        try: report['gpu'] = json.loads(probe['stdout'])
        except ValueError: return finish('PROTOCOL_ERROR')
        cc = report['gpu']['compute_capability']
        if p['arch'] == 'auto':
            # Hand-authored PTX uses a conservative ISA 7.0 target; nvcc can target the device directly.
            p['arch'] = 'sm_75' if backend == 'ptx-direct' else f'sm_{cc[0]*10+cc[1]}'
        if int(p['arch'][3:]) > cc[0]*10 + cc[1]:
            return finish('SKIP_UNSUPPORTED_ARCHITECTURE')
        if backend == 'ptx-cubin' and int(p['arch'][3:])//10 != cc[0]:
            return finish('SKIP_UNSUPPORTED_ARCHITECTURE')
    if backend == 'ptx-direct' and (case.get('kind') == 'reduce' or fault):
        return finish('SKIP_UNSUPPORTED_CASE')
    command = p['command']
    if backend != 'ptx-direct' and (not command or not shutil.which(command[0])):
        return finish('SKIP_TOOLCHAIN_UNAVAILABLE')
    if command:
        version = run(command + ['--version'], folder, 'compiler-version', 15, env)
        report['steps'].append(version)
    sanitizer = None
    if p.get('sanitizer'):
        sanitizer = shutil.which('compute-sanitizer')
        if not sanitizer: return finish('SKIP_SANITIZER_UNAVAILABLE')

    binary = folder / ('program.exe' if os.name == 'nt' else 'program')
    module = folder / 'kernel.ptx'
    build_commands = []
    if backend == 'cpp':
        extra = ['-fno-exceptions', '-fno-rtti', '-nostdlib++'] if Path(command[0]).stem == 'zig' else []
        build_commands.append(command + ['-std=c++17', *p['flags'], *extra, str(folder / 'program.cpp'), '-o', str(binary)])
        launch = [str(binary)]
    elif backend == 'cuda':
        build_commands.append(command + ['-std=c++17', f'-arch={p["arch"]}', *p['flags'], str(folder / 'program.cu'), '-o', str(binary)])
        launch = [str(binary)]
    elif backend in ('ptx-jit', 'ptx-cubin'):
        build_commands.append(command + ['-std=c++17', '--ptx', f'-arch={p["arch"]}', *p['flags'], str(folder / 'kernel.cu'), '-o', str(module)])
        if backend == 'ptx-cubin':
            ptxas = p.get('ptxas') or str(Path(command[0]).with_name('ptxas.exe' if os.name == 'nt' else 'ptxas'))
            ptxas = shutil.which(ptxas) or shutil.which('ptxas')
            if not ptxas: return finish('SKIP_TOOLCHAIN_UNAVAILABLE')
            cubin = folder / 'kernel.cubin'
            build_commands.append([ptxas, f'-arch={p["arch"]}', str(module), '-o', str(cubin)])
            module = cubin
        launch = [sys.executable, str(GPU_WORKER), str(module), str(folder / 'case.json')]
    else:
        module.write_text(emit.ptx(case, p['arch']), encoding='utf-8')
        launch = [sys.executable, str(GPU_WORKER), str(module), str(folder / 'case.json')]
    for i, argv in enumerate(build_commands):
        build = run(argv, folder, f'build-{i}', p['compile_timeout'], env)
        report['steps'].append(build)
        code = status(build, 'COMPILE')
        if code != 'PASS': return finish(code)
    if sanitizer:
        launch = [sanitizer, '--tool', p['sanitizer'], '--error-exitcode', '86', '--target-processes', 'all', *launch]
    observations = []
    for iteration in range(p['repeat']):
        execution = run(launch, folder, f'run-{iteration}', p['run_timeout'], env)
        report['executions'].append(execution)
        code = status(execution, 'EXECUTION')
        if sanitizer and execution['returncode'] == 86: code = 'SANITIZER_FINDING'
        observation = compare(expected, execution['stdout']) if code == 'PASS' else {'status': code}
        observations.append(observation)
    if any(o != observations[0] for o in observations[1:]):
        return finish('FLAKY_RESULT', observations=observations)
    result = observations[0]
    return finish(result.pop('status'), **result, verification_scope='native-execution')
