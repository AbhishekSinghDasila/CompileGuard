import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from compilerlab import backend, emit, engine, ir
from compilerlab.cli import exit_code
from compilerlab.process import run, status
from compilerlab.store import Store


class SemanticsTests(unittest.TestCase):
    def test_exhaustive_small_inputs(self):
        # Independent scalar functions over a bounded input domain, with 32-bit edges.
        functions = {'add': lambda x,k:(x+k)%2**32, 'sub':lambda x,k:(x-k)%2**32,
                     'mul':lambda x,k:(x*k)%2**32, 'xor':lambda x,k:x^k,
                     'and':lambda x,k:x&k, 'or':lambda x,k:x|k,
                     'shl':lambda x,k:(x*2**k)%2**32, 'shr':lambda x,k:x//2**k}
        for op, function in functions.items():
            constants = [0,1,7,31] if op in ('shr','shl') else [0,1,255,ir.MASK]
            for k in constants:
                inputs = list(range(256)) + [ir.MASK, 0x80000000]
                case = {'schema':1,'ops':[[op,k]],'inputs':inputs}
                self.assertEqual(ir.reference(case), [function(x,k) for x in inputs])

    def test_metamorphic_relations_and_reduction(self):
        for seed in range(50):
            case = ir.generate(seed, kind='reduce' if seed%2 else 'map')
            self.assertEqual(case, ir.generate(seed, kind=case['kind']))
            for name in ('identity','xor-pair','inverse-add'):
                self.assertEqual(ir.reference(case), ir.reference(ir.transform(case,name)))

    def test_invalid_cases(self):
        for case in [{'schema':1,'ops':[],'inputs':[]},
                     {'schema':1,'ops':[['shr',32]],'inputs':[0]},
                     {'schema':1,'ops':[['unknown',1]],'inputs':[0]},
                     {'schema':1,'ops':[],'inputs':[True]},
                     {'schema':1,'ops':[],'inputs':[-1]},
                     {'schema':1,'ops':[],'inputs':[0],'kind':'bad'}]:
            with self.assertRaises(ValueError): ir.validate(case)

    def test_ptx_rejects_unsupported_kind(self):
        with self.assertRaises(ValueError): emit.ptx(ir.generate(1,kind='reduce'))
        text = emit.ptx(ir.fault_case())
        self.assertIn('shr.u32', text)
        self.assertIn('setp.ge.u32', text)

    def test_cuda_barriers_are_outside_conditional(self):
        text = emit.source(ir.generate(1,kind='reduce'), cuda=True, device_only=True)
        self.assertIn('if (t < stride) partial[t] += partial[t + stride];\n        __syncthreads();',text)


class ProcessTests(unittest.TestCase):
    def test_compiler_crash_is_distinct(self):
        result={'returncode':3221225477,'timeout':False,'output_limit':False}
        self.assertEqual(status(result,'COMPILE'),'COMPILER_CRASH')

    def test_timeout_and_output_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run([sys.executable,'-c','import time; time.sleep(10)'],folder,'timeout',.1)
            self.assertEqual(status(result,'EXECUTION'),'EXECUTION_TIMEOUT')
            result = run([sys.executable,'-c','print("x"*50000)'],folder,'large',10,max_bytes=1000)
            self.assertEqual(status(result,'EXECUTION'),'OUTPUT_LIMIT')

    def test_launch_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run(['missing-compilerlab-command'],folder,'missing')
            self.assertEqual(status(result,'COMPILE'),'INFRASTRUCTURE_ERROR')

    def test_exit_codes_never_hide_skips(self):
        self.assertEqual(exit_code(['PASS']),0)
        self.assertEqual(exit_code(['PASS','SKIP_GPU_UNAVAILABLE']),2)
        self.assertEqual(exit_code(['SKIP_GPU_UNAVAILABLE','WRONG_RESULT']),1)


class QueueTests(unittest.TestCase):
    def test_idempotency_and_stale_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder)/'db.sqlite')
            identity = store.add({'test':1})
            self.assertEqual(store.add({'test':1}), identity)
            old = store.claim()
            self.assertIsNone(store.claim())
            with store.connect() as db: db.execute('UPDATE jobs SET lease=0')
            new = store.claim()
            self.assertNotEqual(old['owner'],new['owner'])
            self.assertFalse(store.finish(old,{'status':'PASS'},folder))
            self.assertTrue(store.heartbeat(new))
            self.assertTrue(store.finish(new,{'status':'PASS'},folder))
            self.assertFalse(store.heartbeat(new))
            self.assertIsNone(store.claim())

    def test_parallel_claims_are_unique(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'db.sqlite')
            for i in range(20):store.add({'n':i})
            with ThreadPoolExecutor(max_workers=4) as pool:
                claims=list(pool.map(lambda _:store.claim(),range(20)))
            self.assertEqual(len({j['id'] for j in claims}),20)

    def test_crash_retry_exhaustion_is_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'db.sqlite')
            store.add({'n':1})
            store.claim()
            with store.connect() as db:db.execute('UPDATE jobs SET lease=0,attempts=3')
            self.assertIsNone(store.claim())
            self.assertEqual(store.rows()[0]['report']['status'],'INFRASTRUCTURE_ERROR')


class WorkflowTests(unittest.TestCase):
    def test_interrupted_enqueue_is_recovered(self):
        with tempfile.TemporaryDirectory() as folder:
            engine.campaign(folder,[{'name':'model','backend':'model'}],count=1)
            store=Store(Path(folder)/'results.sqlite')
            with store.connect() as db:db.execute('DELETE FROM jobs WHERE id=(SELECT id FROM jobs LIMIT 1)')
            result=engine.campaign(folder,resume=True)
            self.assertEqual(result['jobs'],13)
            self.assertEqual(result['counts'],{'PASS':13})

    def test_artifact_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            backend.execute(ir.generate(1),backend.normalize({'name':'model','backend':'model'}),folder)
            self.assertTrue(engine.verify_bundle(folder))
            (Path(folder)/'program.cpp').write_text('tampered')
            with self.assertRaises(ValueError):engine.verify_bundle(folder)

    def test_reducer_rejects_nonfailure(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                engine.reduce_failure(ir.fault_case(),{'name':'model','backend':'model'},folder)

    def test_saved_expectation_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            corpus=Path(folder)/'corpus';corpus.mkdir()
            (corpus/'bad.json').write_text(json.dumps({'case':ir.fault_case(),'expected':[0]}))
            with self.assertRaises(ValueError):
                engine.regress(corpus,[{'name':'model','backend':'model'}],Path(folder)/'out')

    def test_invalid_profile_is_rejected(self):
        for profile in [{'name':'../bad','backend':'model'},
                        {'name':'bad','backend':'model','flags':'-O2'},
                        {'name':'bad','backend':'model','repeat':0},
                        {'name':'bad','backend':'model','arch':'--bad'},
                        {'name':'bad','backend':'model','sanitizer':'memcheck'}]:
            with self.assertRaises(ValueError):backend.normalize(profile)

    def test_normalizing_does_not_mutate_caller(self):
        profile={'name':'x','backend':'cpp','command':['g++'],'flags':['-O2']}
        original=copy.deepcopy(profile)
        backend.normalize(profile)
        self.assertEqual(profile,original)

    def test_gpu_unavailable_is_a_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            p=backend.normalize({'name':'gpu','backend':'cuda','command':['missing-nvcc']})
            failed={'returncode':3,'timeout':False,'output_limit':False,'stderr':'No GPU','stdout':''}
            with patch.object(backend,'run',return_value=failed):
                result=backend.execute(ir.generate(1),p,folder)
            self.assertEqual(result['status'],'SKIP_GPU_UNAVAILABLE')

    def test_repeated_disagreement_becomes_flaky(self):
        with tempfile.TemporaryDirectory() as folder:
            p=backend.normalize({'name':'fake','backend':'cpp','command':['missing-test-command']})
            calls=iter(['0','1'])
            def fake_run(argv,*args,**kwargs):
                value='version' if '--version' in argv else ('' if '-o' in argv else next(calls))
                return {'returncode':0,'stdout':value,'stderr':'','timeout':False,'output_limit':False}
            with patch.object(backend.shutil,'which',return_value='fake'),patch.object(backend,'run',side_effect=fake_run):
                result=backend.execute({'schema':1,'ops':[],'inputs':[0]},p,folder)
            self.assertEqual(result['status'],'FLAKY_RESULT')

    def test_campaign_resume_does_not_repeat_completed_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            profiles=[{'name':'model','backend':'model'}]
            first=engine.campaign(folder,profiles,count=1,jobs=2)
            with patch.object(backend,'execute',side_effect=AssertionError('Should not rerun')):
                second=engine.campaign(folder,resume=True)
            self.assertEqual(first,second)
            self.assertEqual(first['native_passes'],0)
            self.assertEqual(first['counts'],{'PASS':13})

    def test_reduction_and_corrected_regression(self):
        with tempfile.TemporaryDirectory() as folder:
            p={'name':'fault','backend':'model','fault':'shift-sign'}
            small, report=engine.reduce_failure(ir.fault_case(),p,Path(folder)/'reduce')
            self.assertEqual(report['after'],{'ops':1,'inputs':1})
            self.assertTrue(report['one_minimal_under_deletion'])
            corpus=Path(folder)/'corpus';corpus.mkdir()
            (corpus/'test.json').write_text(json.dumps({'case':small,'expected':ir.reference(small)}))
            results=engine.regress(corpus,[p],Path(folder)/'regression')
            self.assertEqual(results[0]['status'],'PASS')

    def test_reduction_budget_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            _, report=engine.reduce_failure(ir.fault_case(),{'name':'fault','backend':'model','fault':'shift-sign'},folder,budget=1)
            self.assertTrue(report['budget_exhausted'])
            self.assertFalse(report['one_minimal_under_deletion'])

    def test_missing_toolchain(self):
        with tempfile.TemporaryDirectory() as folder:
            p=backend.normalize({'name':'missing','backend':'cpp','command':['missing-test-compiler']})
            result=backend.execute(ir.generate(2),p,folder)
            self.assertEqual(result['status'],'SKIP_TOOLCHAIN_UNAVAILABLE')

    def test_protocol_and_semantic_disagreements(self):
        self.assertEqual(backend.compare([1],'1 2')['status'],'PROTOCOL_ERROR')
        self.assertEqual(backend.compare([1],'bad')['status'],'PROTOCOL_ERROR')
        self.assertEqual(backend.compare([1],'4294967296')['status'],'PROTOCOL_ERROR')
        self.assertEqual(backend.compare([1],'0')['status'],'WRONG_RESULT')

    def test_compiler_change_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'compiler';executable.write_bytes(b'first')
            p=backend.normalize({'name':'fake','backend':'cpp','command':[str(executable)]})
            executable.write_bytes(b'second')
            with self.assertRaises(ValueError):backend.normalize(p)


if __name__=='__main__':unittest.main()
