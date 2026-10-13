import copy
import json
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from surface_model import build, point, values, javascript
from fit_surface import fit
FIXTURE=Path(__file__).resolve().parents[1]/'examples/synthetic-surface-spec.json'

class SurfaceTests(unittest.TestCase):
    def setUp(self): self.spec=json.loads(FIXTURE.read_text())
    def test_shared_boundary(self):
        c=build(self.spec)['components'][0];a,b=c['patches'];shared=set(a['indices'])&set(b['indices'])
        self.assertEqual(len(shared),13)
        for i in shared:
            n=c['normals'][3*i:3*i+3];self.assertAlmostEqual(sum(v*v for v in n),1,places=8)
    def test_fit_independent_synthetic(self):
        result=fit(self.spec,['height','nose_drop'],60)
        self.assertLess(result['final_score'],result['initial_score']*.0001)
        self.assertAlmostEqual(result['spec']['parameters']['height']['value'],1.2,places=3)
        self.assertAlmostEqual(result['spec']['parameters']['nose_drop']['value'],.3,places=3)
        self.assertTrue(all('candidate_spec_sha256' in x for x in result['iterations']))
    def test_protected_rollback(self):
        s=copy.deepcopy(self.spec);s['observations'][0]['protected']=True;s['observations'][0]['target']=[0,.9]
        result=fit(s,['height'],8)
        self.assertEqual(result['spec']['parameters']['height']['value'],.9)
        self.assertTrue(any(x['reason']=='protected_regression' for x in result['iterations']))
    def test_invalid_geometry(self):
        s=copy.deepcopy(self.spec);s['parameters']['width']={'value':0,'min':0,'max':1}
        with self.assertRaises(ValueError):build(s)
    def test_lathe(self):
        s=copy.deepcopy(self.spec);s['domain']='generic';s['components'][0]['geometry']={'type':'lathe','segments':[12,12]}
        c=build(s)['components'][0]
        self.assertEqual(len(c['positions']),13*13*3)
        self.assertAlmostEqual(c['positions'][0],c['positions'][12*3])
        self.assertIn("from 'three'",javascript(build(s)))
    def test_winding_matches_normals(self):
        c=build(self.spec)['components'][0];p=c['positions']
        for patch in c['patches']:
            for k in range(0,len(patch['indices']),3):
                a,b,d=patch['indices'][k:k+3]
                u=[p[3*b+i]-p[3*a+i] for i in range(3)];v=[p[3*d+i]-p[3*a+i] for i in range(3)]
                cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                self.assertGreater(sum(cross[i]*c['normals'][3*a+i] for i in range(3)),0)
    def test_bad_observation(self):
        self.spec['observations'][0]['target']=[]
        with self.assertRaises(ValueError):fit(self.spec)
    def test_parent_cycle(self):
        self.spec['components'][0]['parent']='body'
        with self.assertRaises(ValueError):build(self.spec)
    def test_heldout_does_not_drive_fit(self):
        a=fit(self.spec,['height','nose_drop'],60)
        changed=copy.deepcopy(self.spec)
        changed['observations'][-1]['target']=[1000,-5000]
        b=fit(changed,['height','nose_drop'],60)
        self.assertEqual(a['spec']['parameters'],b['spec']['parameters'])
        self.assertEqual(a['final_score'],b['final_score'])
        self.assertGreater(b['heldout_final_errors']['heldout-side'],1000)
        self.assertFalse(b['heldout_used_for_search'])
    def test_heldout_cannot_protect(self):
        self.spec['observations'][-1]['protected']=True
        with self.assertRaises(ValueError):fit(self.spec)
    def test_bounds(self):
        self.spec['parameters']['height']['value']=100
        with self.assertRaises(ValueError):build(self.spec)

if __name__=='__main__':unittest.main()
