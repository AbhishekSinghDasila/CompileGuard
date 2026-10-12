import argparse
import json
from pathlib import Path
import sys
from . import backend, engine, ir
from .process import run


def exit_code(statuses):
    statuses = list(statuses)
    if any(s != 'PASS' and not s.startswith('SKIP') for s in statuses): return 1
    return 2 if any(s.startswith('SKIP') for s in statuses) else 0


def profiles(path):
    return json.loads(Path(path).read_text())['profiles'] if path else backend.default_profiles()


def main(argv=None):
    parser = argparse.ArgumentParser(description='End-to-end compiler verification with persistent evidence')
    sub = parser.add_subparsers(dest='command', required=True)
    doctor = sub.add_parser('doctor', help='Inspect compiler and GPU availability')
    doctor.add_argument('--out', type=Path, default=Path('runs/doctor'))
    demo = sub.add_parser('demo', help='Campaign, native fault detection, reduction and corrected regression')
    demo.add_argument('--out', type=Path, default=Path('runs/demo-v2'))
    demo.add_argument('--count', type=int, default=16)
    demo.add_argument('--jobs', type=int, default=2)
    campaign = sub.add_parser('campaign', help='Run or resume a leased compiler matrix')
    campaign.add_argument('--matrix')
    campaign.add_argument('--count', type=int, default=16)
    campaign.add_argument('--seed', type=int, default=1)
    campaign.add_argument('--jobs', type=int, default=2)
    campaign.add_argument('--out', type=Path, default=Path('runs/campaign'))
    campaign.add_argument('--resume', action='store_true')
    single = sub.add_parser('run', help='Generate or replay a case')
    single.add_argument('--case', type=Path)
    single.add_argument('--seed', type=int, default=42)
    single.add_argument('--kind', choices=('map', 'reduce'), default='map')
    single.add_argument('--backend', choices=('model','cpp','cuda','ptx-jit','ptx-cubin','ptx-direct'), default='cpp')
    single.add_argument('--compiler')
    single.add_argument('--profile', type=Path)
    single.add_argument('--out', type=Path, default=Path('runs/single'))
    replay = sub.add_parser('replay', help='Replay an artifact directory with its recorded profile')
    replay.add_argument('artifact', type=Path)
    replay.add_argument('--out', type=Path, default=Path('runs/replay'))
    reduction = sub.add_parser('reduce', help='Minimize a repeatable wrong result using its saved profile')
    reduction.add_argument('artifact', type=Path)
    reduction.add_argument('--budget', type=int, default=120)
    reduction.add_argument('--out', type=Path, default=Path('runs/reduction'))
    regression = sub.add_parser('regress', help='Execute saved expectations against corrected profiles')
    regression.add_argument('corpus', type=Path)
    regression.add_argument('--matrix')
    regression.add_argument('--out', type=Path, default=Path('runs/regression'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            result = {'compiler': backend.auto_compiler(), 'profiles': backend.default_profiles()}
            gpu = run([sys.executable, str(backend.GPU_WORKER), '--probe'], args.out, 'gpu', 15, backend.environment())
            result['gpu_probe'] = gpu
            print(json.dumps(result, indent=2))
            return 0
        if args.command == 'demo':
            result = engine.demo(args.out, args.count, args.jobs)
            print(json.dumps({k:v for k,v in result.items() if k != 'reduction'}, indent=2))
            print(f"Dashboard: {(args.out / 'campaign/index.html').resolve()}")
            return exit_code([*result['campaign']['counts'], *(r['status'] for r in result['regression'])])
        if args.command == 'campaign':
            result = engine.campaign(args.out, profiles(args.matrix), args.count, args.seed, args.jobs, args.resume)
            print(json.dumps(result, indent=2))
            return exit_code(result['counts'])
        if args.command == 'regress':
            result = engine.regress(args.corpus, profiles(args.matrix), args.out)
            print(json.dumps(result, indent=2))
            return exit_code(r['status'] for r in result)
        if args.command in ('replay', 'reduce'):
            engine.verify_bundle(args.artifact)
            case = json.loads((args.artifact / 'case.json').read_text())
            p = json.loads((args.artifact / 'profile.json').read_text())
            if args.command == 'reduce':
                _, result = engine.reduce_failure(case, p, args.out, args.budget)
                print(json.dumps(result, indent=2))
                return 0 if result['status'] == 'REDUCED' else 1
        else:
            case = json.loads(args.case.read_text()) if args.case else ir.generate(args.seed, kind=args.kind)
            p = json.loads(args.profile.read_text()) if args.profile else {'name':'single','backend':args.backend,'flags':['-O2']}
            if args.compiler: p['command'] = [args.compiler]
        result = backend.execute(case, backend.normalize(p), args.out)
        print(f"{result['status']}: {(args.out / 'report.json').resolve()}")
        return exit_code([result['status']])
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
