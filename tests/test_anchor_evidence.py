import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import anchor_evidence as a

class AnchorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        Image.new('RGB',(100,100),'white').save(self.root/'ref.png')
        self.camera={'type':'orthographic','width':100,'height':100,'position':[0,0,5],'target':[0,0,0],'ortho_height':10}
        self.spec={'coordinate_system':{'up':'y','forward':'z'},'parameters':{},'materials':{'m':{'color':'#ffffff'}},'components':[{'id':'part','material':'m','position':[0,0,0],'geometry':{'type':'mesh','positions':[0,0,0,1,0,0,0,1,0],'triangles':[0,1,2]}}],'cameras':{'front':self.camera}}
        self.spec['references']=[{'id':'original','path':'ref.png','sha256':a.sha(self.root/'ref.png')}]
        self.write('base.json',self.spec)
        self.annotation={'schema_version':1,'reference_id':'original','transform':{'kind':'identity'},'reference_spec':{'path':'base.json','sha256':a.sha(self.root/'base.json')},'image':{'path':'ref.png','sha256':a.sha(self.root/'ref.png'),'size':[100,100]},'camera_id':'front','camera_sha256':a.digest(self.camera),'features':[{'id':'tip','kind':'landmark','target_px':[50,50],'uncertainty_px':.5,'tolerance_px':2,'protected':True,'regression_allowance_px':0,'binding':{'component_id':'part','binding':{'vertex_index':0}}}]}
    def tearDown(self):self.tmp.cleanup()
    def write(self,name,value):
        p=self.root/name;p.write_text(json.dumps(value));return p
    def run_case(self,spec=None,annotation=None,out='out',baseline=None):
        return a.evaluate(self.write('annotation.json',annotation or self.annotation),self.write('candidate.json',spec or self.spec),self.root/out,baseline)
    def test_arbitrary_same_size_image_rejected(self):
        Image.new('RGB',(100,100),'green').save(self.root/'other.png')
        self.annotation['image']['path']='other.png';self.annotation['image']['sha256']=a.sha(self.root/'other.png')
        with self.assertRaisesRegex(ValueError,'reference image identity'):self.run_case()
    def test_observation_wrong_reference_rejected(self):
        self.spec['observations']=[{'id':'o','reference_id':'other','camera_id':'front','component_id':'part','binding':{'vertex_index':0}}]
        self.write('base.json',self.spec);self.annotation['reference_spec']['sha256']=a.sha(self.root/'base.json')
        del self.annotation['features'][0]['binding'];self.annotation['features'][0]['observation_id']='o'
        with self.assertRaisesRegex(ValueError,'observation reference'):self.run_case()
    def test_candidate_reference_changed_rejected(self):
        s=copy.deepcopy(self.spec);s['references'][0]['sha256']='bad'
        with self.assertRaisesRegex(ValueError,'reference image identity'):self.run_case(s)
    def test_real_geometry_direction_and_normalized(self):
        s=copy.deepcopy(self.spec);s['components'][0]['position']=[1,1,0]
        r=self.run_case(s);f=r['features'][0]
        self.assertEqual(f['delta_px'],[10,-10]);self.assertEqual(f['predicted_normalized'],[.6,.4]);self.assertFalse(r['numeric_checks_passed'])
        self.assertTrue((self.root/'out/anchor-overlay.png').is_file())
    def test_actual_vertex_drives_measurement(self):
        s=copy.deepcopy(self.spec);s['components'][0]['geometry']['positions'][0]=.5
        self.assertEqual(self.run_case(s)['features'][0]['predicted_px'],[55,50])
    def test_invalid_binding(self):
        self.annotation['features'][0]['binding']['binding']['vertex_index']=99
        with self.assertRaisesRegex(ValueError,'vertex'):self.run_case()
    def test_fake_point_rejected(self):
        self.annotation['features'][0]['binding']['binding']={'local_point':[0,0,0]}
        with self.assertRaisesRegex(ValueError,'arbitrary'):self.run_case()
    def test_camera_change(self):
        s=copy.deepcopy(self.spec);s['cameras']['front']['width']=200
        with self.assertRaisesRegex(ValueError,'camera identity'):self.run_case(s)
    def test_camera_dimensions_mismatch(self):
        self.camera['width']=200;self.write('base.json',self.spec)
        self.annotation['reference_spec']['sha256']=a.sha(self.root/'base.json');self.annotation['camera_sha256']=a.digest(self.camera)
        with self.assertRaisesRegex(ValueError,'dimensions'):self.run_case()
    def test_stale_reference(self):
        Image.new('RGB',(100,100),'red').save(self.root/'ref.png')
        with self.assertRaisesRegex(ValueError,'stale reference'):self.run_case()
    def test_stale_spec(self):
        self.write('base.json',{})
        with self.assertRaisesRegex(ValueError,'stale annotation'):self.run_case()
    def test_transform_rejected(self):
        self.annotation['transform']={'kind':'resize'}
        with self.assertRaisesRegex(ValueError,'unsupported'):self.run_case()
    def test_silhouette_cannot_claim_point_pass(self):
        self.annotation['features']=[{'id':'edge','kind':'silhouette','target_px':[30,40],'uncertainty_px':1,'tolerance_px':2}]
        r=self.run_case();self.assertFalse(r['numeric_checks_passed']);self.assertTrue(r['manual_review_pending']);self.assertIsNone(r['features'][0]['passed'])
    def test_regression_preserves_declared_tolerances(self):
        self.run_case(out='baseline')
        # Preserve immutable baseline spec rather than overwriting candidate.json.
        report=self.root/'baseline/report.json';d=a.load(report);self.write('frozen.json',self.spec);d['spec_path']=str(self.root/'frozen.json');self.write('baseline/report.json',d)
        s=copy.deepcopy(self.spec);s['components'][0]['position']=[.1,0,0]
        r=self.run_case(s,out='next',baseline=report)
        self.assertTrue(r['features'][0]['regression']);self.assertFalse(r['numeric_checks_passed'])
    def test_changed_tolerance_cannot_compare(self):
        self.run_case(out='baseline');self.annotation['features'][0]['tolerance_px']=99
        with self.assertRaisesRegex(ValueError,'tolerance changed'):self.run_case(out='next',baseline=self.root/'baseline/report.json')

if __name__=='__main__':unittest.main()
