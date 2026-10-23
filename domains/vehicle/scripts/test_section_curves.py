import math,unittest
from section_curves import densify
class Sections(unittest.TestCase):
    def plan(self):
        return {'schema_version':1,'evidence':'Explicit shared profiles','sections':[{'station':x,'profile':[[-w,0],[w,0],[w,h],[-w,h]]} for x,w,h in [(0,1,1),(1,1.5,2),(3,1.1,1.7),(4,1.3,1.8)]]}
    def test_control_sections_exact_and_step_bounded(self):
        p=self.plan();q=densify(p,.19)
        for s in p['sections']:self.assertIn(s,q['sections'])
        self.assertLessEqual(max(b['station']-a['station'] for a,b in zip(q['sections'],q['sections'][1:])),.19000001)
    def test_each_coordinate_stays_within_local_control_bounds(self):
        p=self.plan();q=densify(p,.025)
        for s in q['sections']:
            for a,b in zip(p['sections'],p['sections'][1:]):
                if a['station']<=s['station']<=b['station']:
                    for point,pa,pb in zip(s['profile'],a['profile'],b['profile']):
                        for v,va,vb in zip(point,pa,pb):self.assertGreaterEqual(v,min(va,vb)-1e-12);self.assertLessEqual(v,max(va,vb)+1e-12)
    def test_input_not_mutated_and_symmetry_retained(self):
        p=self.plan();before=repr(p);q=densify(p,.1);self.assertEqual(repr(p),before)
        for s in q['sections']:self.assertAlmostEqual(s['profile'][0][0],-s['profile'][1][0])
    def test_two_controls_are_linear(self):
        p=self.plan();p['sections']=p['sections'][:2];q=densify(p,.25);self.assertAlmostEqual(q['sections'][2]['profile'][2][1],1.5)
    def test_invalid_step_and_sampling_budget_rejected(self):
        for step in [0,-1,float('nan'),float('inf'),True,.000001]:
            with self.assertRaises(ValueError):densify(self.plan(),step)
    def test_mismatched_topology_rejected(self):
        p=self.plan();p['sections'][1]['profile'].pop()
        with self.assertRaises(ValueError):densify(p,.1)
if __name__=='__main__':unittest.main()
