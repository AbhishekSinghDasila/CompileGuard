"""Campaign orchestration, repeatable reduction, and regression replay."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import threading
import time
import traceback

from . import backend, ir, report
from .store import Store


def engine_hash():
    return ir.digest({p.name: p.read_text(encoding='utf-8') for p in Path(__file__).parent.glob('*.py')})


def verify_bundle(directory):
    folder = Path(directory).resolve()
    manifest = folder / 'report.json'
    if not manifest.exists():
        raise ValueError('Replay requires a report.json artifact manifest')
    previous = json.loads(manifest.read_text())
    for name, expected in previous.get('artifacts', {}).items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise ValueError(f'Missing or invalid artifact: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Artifact checksum mismatch: {name}')
    case = json.loads((folder / 'case.json').read_text())
    if previous.get('case_sha256') != ir.digest(case):
        raise ValueError('Case identity mismatch')
    return True


def campaign(directory, profiles=None, count=16, seed=1, jobs=2, resume=False, metamorphic=True):
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / 'manifest.json'
    if resume:
        manifest = json.loads(manifest_path.read_text())
        if manifest['engine_hash'] != engine_hash():
            raise ValueError('Engine changed: start a new campaign instead of mixing results')
        profiles = [backend.normalize(p) for p in manifest['profiles']]
    else:
        if manifest_path.exists():
            raise ValueError('Campaign already exists; use --resume or a new output directory')
        profiles = [backend.normalize(p) for p in (profiles or backend.default_profiles())]
        if not profiles or len({p['name'] for p in profiles}) != len(profiles):
            raise ValueError('Profiles must be nonempty with unique names')
        if not 1 <= count <= 100000 or not 1 <= jobs <= 32:
            raise ValueError('Expected 1..100000 seeds and 1..32 workers')
        manifest = {'schema': 1, 'engine_hash': engine_hash(), 'profiles': profiles, 'count': count,
                    'seed': seed, 'metamorphic': metamorphic}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    store = Store(folder / 'results.sqlite')
    # Idempotently populate on resume too, including an interrupted initial enqueue.
    cases = list(ir.boundary_cases())
    for s in range(manifest['seed'], manifest['seed'] + manifest['count']):
        case = ir.generate(s, count=1 + s % 20, kind='reduce' if s % 5 == 0 else 'map')
        cases.append(case)
        if manifest['metamorphic'] and s < manifest['seed'] + 3:
            cases.extend(ir.transform(case, name) for name in ('identity', 'xor-pair', 'inverse-add'))
    for case in cases:
        for p in profiles:
            store.add({'case_id': ir.digest(case), 'case': case, 'profile': p, 'engine_hash': manifest['engine_hash']})

    def worker():
        while job := store.claim():
            attempt = folder / 'artifacts' / job['id'][:20] / job['owner'][:12]
            stop = threading.Event()
            def renew():
                while not stop.wait(10): store.heartbeat(job)
            heartbeat = threading.Thread(target=renew, daemon=True)
            heartbeat.start()
            try:
                result = backend.execute(job['payload']['case'], job['payload']['profile'], attempt)
            except Exception as error:
                attempt.mkdir(parents=True, exist_ok=True)
                result = {'status': 'INFRASTRUCTURE_ERROR', 'error': str(error), 'traceback': traceback.format_exc()}
                (attempt / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            finally:
                stop.set()
                heartbeat.join()
            store.finish(job, result, attempt)
            print(f"{job['id'][:8]} {job['payload']['profile']['name']}: {result['status']}", flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(worker) for _ in range(jobs)]
        for future in futures: future.result()
    return report.render(store, folder)


def reduce_failure(case, profile, directory, budget=120):
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    p = backend.normalize(profile)
    p['repeat'] = max(3, p['repeat'])
    evaluations, cache = [], {}
    def check(candidate):
        key = ir.digest(candidate)
        if key in cache: return cache[key]
        if len(evaluations) >= budget: raise StopIteration()
        result = backend.execute(candidate, p, folder / 'attempts' / f'{len(evaluations):04d}')
        observations = {'case_sha256': key, 'status': result['status'], 'ops': len(candidate['ops']), 'inputs': len(candidate['inputs'])}
        evaluations.append(observations)
        cache[key] = result['status'] == 'WRONG_RESULT'
        return cache[key]
    candidate = copy.deepcopy(ir.validate(case))
    if not check(candidate):
        raise ValueError('Reduction requires a repeatable WRONG_RESULT, not another failure class')
    exhausted = False
    try:
        changed = True
        while changed:
            changed = False
            for field in ('ops', 'inputs'):
                for index in range(len(candidate[field])):
                    trial = copy.deepcopy(candidate)
                    del trial[field][index]
                    if not trial['inputs']: continue
                    if check(trial):
                        candidate, changed = trial, True
                        break
                if changed: break
    except StopIteration:
        exhausted = True
    (folder / 'case.json').write_text(json.dumps(candidate, indent=2), encoding='utf-8')
    (folder / 'profile.json').write_text(json.dumps(p, indent=2), encoding='utf-8')
    result = {'status': 'REDUCED', 'budget_exhausted': exhausted, 'one_minimal_under_deletion': not exhausted,
              'before': {'ops':len(case['ops']), 'inputs':len(case['inputs'])},
              'after': {'ops':len(candidate['ops']), 'inputs':len(candidate['inputs'])}, 'evaluations':evaluations}
    (folder / 'reduction.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    final = backend.execute(candidate, p, folder / 'final')
    if final['status'] != 'WRONG_RESULT':
        result['status'] = 'FLAKY_RESULT'
        result['one_minimal_under_deletion'] = False
        (folder / 'reduction.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return candidate, result


def regress(corpus, profiles, directory):
    entries = sorted(Path(corpus).glob('*.json'))
    if not entries: raise ValueError('No regression entries found')
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for entry_path in entries:
        entry = json.loads(entry_path.read_text())
        ir.validate(entry['case'])
        if entry['expected'] != ir.reference(entry['case']):
            raise ValueError('Saved regression expectation disagrees with current specification')
        for p in profiles:
            clean = backend.normalize(p)
            clean.pop('fault', None)
            result = backend.execute(entry['case'], clean, folder / entry_path.stem / clean['name'])
            results.append({'entry': entry_path.name, 'profile': clean['name'], 'status': result['status']})
    (folder / 'regression.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    return results


def demo(directory, count=16, jobs=2):
    folder = Path(directory).resolve()
    profiles = backend.default_profiles()
    summary = campaign(folder / 'campaign', profiles, count=count, jobs=jobs,
                       resume=(folder / 'campaign/manifest.json').exists())
    buggy = dict(profiles[-1], name='synthetic-shift-sign', fault='shift-sign')
    reduced, reduction = reduce_failure(ir.fault_case(), buggy, folder / 'reduction')
    if reduction['status'] != 'REDUCED': raise ValueError('Synthetic fault was not stable')
    corpus = folder / 'corpus'
    corpus.mkdir(exist_ok=True)
    entry = {'schema': 1, 'case': reduced, 'expected': ir.reference(reduced), 'synthetic': True,
             'description': 'Logical right shift must not sign-extend unsigned values.'}
    (corpus / 'unsigned-shift.json').write_text(json.dumps(entry, indent=2), encoding='utf-8')
    regressions = regress(corpus, profiles, folder / 'regression')
    result = {'campaign': summary, 'reduction': reduction, 'regression': regressions,
              'scope': 'native C++' if profiles[0]['backend'] == 'cpp' else 'model only'}
    (folder / 'demo.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result
