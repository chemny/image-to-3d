import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mesh_checks import check, mesh_report
FIXTURE=Path(__file__).resolve().parents[1]/'examples/assembly-check-example.json'

class MeshChecks(unittest.TestCase):
    def setUp(self):self.data=json.loads(FIXTURE.read_text())
    def test_valid_closed_part_and_sampled_hinge(self):
        r=check(self.data);self.assertTrue(r['passed']);self.assertEqual(len(r['assembly']['samples']),3)
    def test_missing_face_closed_fails(self):
        self.data['meshes'][0]['triangles']=self.data['meshes'][0]['triangles'][:-3]
        r=check(self.data);self.assertFalse(r['passed']);self.assertEqual(len(r['meshes'][0]['boundary_edges']),3)
    def test_open_patch_allows_boundary(self):
        m=self.data['meshes'][0];m['triangles']=m['triangles'][:3];m['contract']='open_patch'
        self.assertTrue(mesh_report(m)['passed'])
    def test_reversed_face(self):
        t=self.data['meshes'][0]['triangles'];t[:3]=reversed(t[:3]);r=check(self.data)
        self.assertFalse(r['passed']);self.assertTrue(r['meshes'][0]['inconsistent_edges'])
    def test_anchor_drift_on_opening(self):
        c=self.data['assembly']['connections'][0];c['a']['point']=[1,0,0];c['b']['point']=[1,0,0]
        r=check(self.data);self.assertFalse(r['passed']);self.assertTrue(r['assembly']['samples'][0]['passed']);self.assertFalse(r['assembly']['samples'][-1]['passed'])
    def test_wrong_parent(self):
        self.data['assembly']['nodes'][1]['parent']=None
        self.assertFalse(check(self.data)['passed'])
    def test_bad_index(self):
        self.data['meshes'][0]['triangles'][0]=99
        self.assertFalse(check(self.data)['passed'])
    def test_nonfinite(self):
        self.data['meshes'][0]['positions'][0]=float('nan')
        self.assertFalse(check(self.data)['passed'])
    def test_degenerate(self):
        self.data['meshes'][0]['triangles'][:3]=[0,0,1]
        self.assertFalse(check(self.data)['passed'])
    def test_nonmanifold(self):
        self.data['meshes'][0]['triangles'] += self.data['meshes'][0]['triangles'][:3]
        self.assertTrue(check(self.data)['meshes'][0]['nonmanifold_edges'])
    def test_cycle(self):
        self.data['assembly']['nodes'][0]['parent']='door'
        self.assertFalse(check(self.data)['passed'])
    def test_cli_failure_exit(self):
        self.data['meshes'][0]['triangles']=[]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text(json.dumps(self.data))
            r=subprocess.run([sys.executable,str(FIXTURE.parents[1]/'scripts/mesh_checks.py'),str(p)],capture_output=True,text=True)
            self.assertEqual(r.returncode,1);self.assertFalse(json.loads(r.stdout)['passed'])

if __name__=='__main__':unittest.main()
