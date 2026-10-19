import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from adoption_check import evaluate

class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / 'asset').write_bytes(b'evidence')
        a = {'path': 'asset', 'sha256': hashlib.sha256(b'evidence').hexdigest()}
        self.r = {'baseline': a, 'candidate': a, 'same_conditions': True,
                  'required_regions': ['edge'], 'regions': [dict(id='edge', verdict='improved', reason='Observed smoother edge', before=a, after=a)]}
    def test_improved(self):
        self.assertEqual(evaluate(self.r,self.base)['decision'],'adopt')
    def test_unchanged(self):
        self.r['regions'][0]['verdict']='unchanged'
        self.assertEqual(evaluate(self.r,self.base)['decision'],'adopt')
    def test_regressed(self):
        self.r['regions'][0]['verdict']='regressed'
        self.assertEqual(evaluate(self.r,self.base)['decision'],'retain-baseline')
    def test_uncertain(self):
        self.r['regions'][0]['verdict']='uncertain'
        self.assertEqual(evaluate(self.r,self.base)['decision'],'pending')
    def test_missing_region(self):
        self.r['required_regions'].append('roof')
        self.assertEqual(evaluate(self.r,self.base)['decision'],'invalid')
    def test_stale_artifact(self):
        (self.base/'asset').write_bytes(b'changed')
        self.assertEqual(evaluate(self.r,self.base)['decision'],'invalid')
    def test_duplicate(self):
        self.r['regions'].append(copy.deepcopy(self.r['regions'][0]))
        self.assertEqual(evaluate(self.r,self.base)['decision'],'invalid')
    def test_unmatched_conditions(self):
        self.r['same_conditions']=False
        self.assertEqual(evaluate(self.r,self.base)['decision'],'invalid')
    def test_missing_artifact(self):
        (self.base/'asset').unlink()
        self.assertEqual(evaluate(self.r,self.base)['decision'],'invalid')
    def test_invalid_verdict(self):
        self.r['regions'][0]['verdict']='pass'
        self.assertEqual(evaluate(self.r,self.base)['decision'],'invalid')
