import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from form_construction import compile_recipe
from scene_build import geometry


def recipe(method='loft'):
    return {'version':1,'component_id':'test','source':{'reference_id':'original','roi':[10,20,100,150]},
            'rationale':'Measured outline and authored thickness, hidden depth inferred.', 'method':method,
            'parameters':({'sections':[{'center':[0,0,0],'radii':[1,.5]}, {'center':[.2,1,.1],'radii':[.8,.4]}, {'center':[.3,2,.4],'radii':[.1,.1]}],'radial_segments':32} if method=='loft' else
                          {'outline':[[math.cos(i*math.pi/4)*(1 if i%2==0 else .65),math.sin(i*math.pi/4)*(1 if i%2==0 else .65)] for i in range(8)],'rings':[{'fraction':0,'half_thickness':.4},{'fraction':.6,'half_thickness':.3},{'fraction':1,'half_thickness':.08}]})}


class FormConstructionTests(unittest.TestCase):
    def test_methods_watertight_and_renderer_compatible(self):
        for method in ('loft','thick_outline'):
            result=compile_recipe(recipe(method));g=result['geometry'];report=result['report']
            self.assertTrue(report['topology']['passed']);self.assertEqual(report['topology']['boundary_edges'],[])
            self.assertGreater(report['signed_volume'],0)
            loaded=geometry(g)[0];self.assertEqual(loaded['indices'],g['triangles'])
            for i in range(0,len(g['normals']),3):self.assertAlmostEqual(sum(x*x for x in g['normals'][i:i+3]),1)
            self.assertFalse(report['visual_accuracy_checked'])

    def test_loft_actual_cross_sections(self):
        r=recipe();g=compile_recipe(r)['geometry'];n=32
        for row,s in enumerate(r['parameters']['sections']):
            pts=[g['positions'][3*i:3*i+3] for i in range(row*n,(row+1)*n)]
            self.assertTrue(all(p[1]==s['center'][1] for p in pts))
            self.assertAlmostEqual(max(p[0] for p in pts)-min(p[0] for p in pts),2*s['radii'][0])
            self.assertAlmostEqual(max(p[2] for p in pts)-min(p[2] for p in pts),2*s['radii'][1])

    def test_loft_radius_changes_real_mesh(self):
        a=recipe();b=copy.deepcopy(a);b['parameters']['sections'][1]['radii'][0]*=2
        ga=compile_recipe(a);gb=compile_recipe(b)
        self.assertNotEqual(ga['geometry']['positions'],gb['geometry']['positions'])
        self.assertEqual(ga['geometry']['triangles'],gb['geometry']['triangles'])
        self.assertGreater(gb['report']['signed_volume'],ga['report']['signed_volume'])

    def test_thickness_changes_volume_not_outline(self):
        a=recipe('thick_outline');b=copy.deepcopy(a)
        for ring in b['parameters']['rings']:ring['half_thickness']*=2
        ga=compile_recipe(a);gb=compile_recipe(b)
        for axis in (0,2):self.assertEqual(ga['geometry']['positions'][axis::3],gb['geometry']['positions'][axis::3])
        self.assertAlmostEqual(gb['report']['signed_volume'],2*ga['report']['signed_volume'])

    def test_top_bottom_normals_outward(self):
        g=compile_recipe(recipe('thick_outline'))['geometry'];n=8;bottom=1+2*n
        self.assertGreater(g['normals'][1],.99);self.assertLess(g['normals'][bottom*3+1],-.99)

    def test_deterministic_identity(self):
        a=recipe();b=dict(reversed(list(a.items())))
        self.assertEqual(compile_recipe(a),compile_recipe(b))
        b=copy.deepcopy(a);b['source']['reference_id']='other'
        self.assertNotEqual(compile_recipe(a)['report']['recipe_sha256'],compile_recipe(b)['report']['recipe_sha256'])

    def test_loft_invalid_sections(self):
        for value in (0,-1,float('nan'),True):
            r=recipe();r['parameters']['sections'][0]['radii'][0]=value
            with self.assertRaises(ValueError):compile_recipe(r)
        r=recipe();r['parameters']['sections'][1]['center'][1]=0
        with self.assertRaisesRegex(ValueError,'strictly increase'):compile_recipe(r)
        r=recipe();r['parameters']['frame']=[1,0,0]
        with self.assertRaisesRegex(ValueError,'unknown'):compile_recipe(r)

    def test_outline_invalid_order_and_origin(self):
        for outline in ([[1,0],[0,-1],[-1,0],[0,1]],[[1,0],[2,0],[0,1],[-1,-1]],[[0,0],[1,0],[0,1]],[[1,0],[0,1],[-1,0],[0,-1]]*2):
            r=recipe('thick_outline');r['parameters']['outline']=outline
            with self.assertRaises(ValueError):compile_recipe(r)

    def test_ring_invalid(self):
        for fraction in (.6,-1,2,float('inf')):
            r=recipe('thick_outline');r['parameters']['rings'][2]['fraction']=fraction
            with self.assertRaises(ValueError):compile_recipe(r)
        r=recipe('thick_outline');r['parameters']['rings'][2]['half_thickness']=0
        with self.assertRaises(ValueError):compile_recipe(r)

    def test_metadata_required(self):
        for key in ('source','rationale','component_id','parameters'):
            r=recipe();del r[key]
            with self.assertRaises(ValueError):compile_recipe(r)
        r=recipe();r['source']['roi']=[0,0,-1,3]
        with self.assertRaises(ValueError):compile_recipe(r)
        r=recipe();r['method']='sphere'
        with self.assertRaises(ValueError):compile_recipe(r)

    def test_inner_ellipse_preserves_boundary_and_softens_interior_notch(self):
        a=recipe('thick_outline');b=copy.deepcopy(a)
        b['parameters'].update(inner_outline_ellipse=[1,1],outline_influence_power=3)
        ga=compile_recipe(a);gb=compile_recipe(b);pa=ga['geometry']['positions'];pb=gb['geometry']['positions']
        n=len(a['parameters']['outline'])
        # Outer ring exact; inner notch receives more radial volume.
        self.assertEqual(pa[3*(1+n):3*(1+2*n)],pb[3*(1+n):3*(1+2*n)])
        self.assertGreater(math.hypot(pb[6],pb[8]),math.hypot(pa[6],pa[8]))
        self.assertTrue(gb['report']['topology']['passed'])
        self.assertEqual(ga['geometry']['triangles'],gb['geometry']['triangles'])
        for invalid in (0,-1,float('nan')):
            b['parameters']['outline_influence_power']=invalid
            with self.assertRaises(ValueError):compile_recipe(b)
        b['parameters']['outline_influence_power']=3;b['parameters']['inner_outline_ellipse']=[0,1]
        with self.assertRaises(ValueError):compile_recipe(b)

    def test_inner_ellipse_overlap_rejected(self):
        r=recipe('thick_outline');r['parameters'].update(inner_outline_ellipse=[10,10],outline_influence_power=3)
        with self.assertRaisesRegex(ValueError,'overlapping'):compile_recipe(r)

    def test_cli(self):
        script=Path(__file__).resolve().parents[1]/'scripts/form_construction.py'
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);(d/'recipe.json').write_text(json.dumps(recipe()))
            args=[sys.executable,str(script),str(d/'recipe.json'),'--out',str(d/'mesh.json'),'--report',str(d/'report.json')]
            subprocess.run(args,check=True,capture_output=True)
            self.assertEqual(json.loads((d/'mesh.json').read_text())['type'],'mesh')
            self.assertEqual(json.loads((d/'report.json').read_text())['component_id'],'test')
            args[-1]=str(d/'recipe.json');self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
