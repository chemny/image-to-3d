import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bezier_network import build_network,evaluate
FIXTURE=Path(__file__).resolve().parents[1]/'examples/bezier-network-example.json'

class BezierNetwork(unittest.TestCase):
    def setUp(self):self.s=json.loads(FIXTURE.read_text())
    def test_smooth_shared_edge(self):
        m=build_network(self.s);self.assertEqual(m['vertex_count'],162);self.assertEqual(m['triangle_count'],256)
        self.assertLess(m['seams'][0]['c1_error'],1e-12)
        a,b=m['components'];self.assertEqual(a['positions'][-27:],b['positions'][:27])
    def test_analytic_derivatives(self):
        grid=[[self.s['control_points'][f'p{i}_{j}']['position'] for j in range(4)] for i in range(4)]
        p,du,dv,n=evaluate(grid,.4,.6)
        self.assertAlmostEqual(du[0],1);self.assertAlmostEqual(dv[1],-.06)
        self.assertAlmostEqual(sum(x*x for x in n),1)
    def test_mismatch_ids(self):
        self.s['patches'][1]['control_points'][0][0]='p4_0'
        with self.assertRaisesRegex(ValueError,'identical control'):build_network(self.s)
    def test_mismatch_subdivision(self):
        self.s['patches'][1]['segments'][1]=10
        with self.assertRaisesRegex(ValueError,'subdivisions'):build_network(self.s)
    def test_c1_failure(self):
        self.s['control_points']['p4_1']['position'][1]+=.2
        with self.assertRaisesRegex(ValueError,'continuity failed'):build_network(self.s)
    def test_g1_allows_different_speed(self):
        self.s['shared_edges'][0]['continuity']='G1'
        for j in range(4):self.s['control_points'][f'p4_{j}']['position'][0]=1.5
        self.assertTrue(build_network(self.s)['seams'][0]['passed'])
        self.s['shared_edges'][0]['continuity']='C1'
        with self.assertRaisesRegex(ValueError,'continuity failed'):build_network(self.s)
    def test_reverse_order(self):
        self.s['patches'][1]['control_points']=[row[::-1] for row in self.s['patches'][1]['control_points']]
        self.s['shared_edges'][0]['reverse']=True
        self.s['shared_edges'][0]['continuity']='C0'
        m=build_network(self.s)
        self.assertTrue(m['seams'][0]['passed'])
        self.assertFalse(m['seams'][0]['orientation_consistent'])
    def test_smooth_reverse_normals_rejected(self):
        self.s['patches'][1]['control_points']=[row[::-1] for row in self.s['patches'][1]['control_points']]
        self.s['shared_edges'][0]['reverse']=True
        for continuity in ('G1','C1'):
            self.s['shared_edges'][0]['continuity']=continuity
            with self.assertRaisesRegex(ValueError,'continuity failed'):build_network(self.s)
    def test_degenerate(self):
        for p in self.s['control_points'].values():p['position']=[0,0,0]
        with self.assertRaisesRegex(ValueError,'degenerate'):build_network(self.s)
    def test_missing_source(self):
        del self.s['control_points']['p0_0']['source']
        with self.assertRaisesRegex(ValueError,'source'):build_network(self.s)

if __name__=='__main__':unittest.main()
