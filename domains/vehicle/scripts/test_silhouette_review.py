from pathlib import Path
import tempfile,json,unittest
import numpy as np
from PIL import Image
from silhouette_review import freeze,check,metrics,mask,sha
class Silhouettes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name);self.a=np.zeros((32,40),bool);self.a[8:24,10:30]=True;self.write('ref.png',self.a);self.write('before.png',np.roll(self.a,6,axis=1));self.write('after.png',self.a);(self.p/'model.glb').write_bytes(b'identity fixture');(self.p/'camera.json').write_text('{}');self.spec={'schema_version':1,'claim':'projected_outline','scope':'Fixture outline only','baseline_model':'model.glb','views':[{'id':'reserved','role':'validation','origin':'generated','alignment_evidence':'camera.json','reference':'ref.png','baseline':'before.png','candidate_filename':'after.png','mask_mode':'alpha','minimum_iou':.9,'maximum_boundary_p95_px':2,'uncertainty_px':1,'threshold_reason':'Explicit fixture bounds'}]}
    def tearDown(self):self.tmp.cleanup()
    def write(self,name,a):
        v=np.zeros((*a.shape,4),np.uint8);v[:,:,3]=a*255;Image.fromarray(v).save(self.p/name)
    def run_case(self,reused=()):
        (self.p/'spec.json').write_text(json.dumps(self.spec));freeze(self.p/'spec.json',self.p/'lock.json');(self.p/'render.json').write_text(json.dumps({'model_sha256':sha(self.p/'model.glb'),'views':{'reserved':{'sha256':sha(self.p/'after.png'),'alignment_sha256':sha(self.p/'camera.json')}}}));return check(self.p/'lock.json',self.p,self.p/'model.glb',self.p/'render.json',reused)
    def test_aligned_improvement_passes_only_outline_scope(self):
        r=self.run_case();self.assertEqual(r['verdict'],'passed');self.assertEqual(r['claim'],'projected_outline');self.assertGreater(r['measurements'][0]['after']['iou'],r['measurements'][0]['before']['iou'])
    def test_shifted_view_fails_without_auto_registration(self):
        self.write('after.png',np.roll(self.a,5,axis=1));self.assertEqual(self.run_case()['verdict'],'needs_revision')
    def test_empty_candidate_fails_with_finite_json(self):
        self.write('after.png',np.zeros_like(self.a));r=self.run_case();self.assertEqual(r['verdict'],'needs_revision');json.dumps(r,allow_nan=False)
    def test_reused_validation_view_cannot_pass_independent_gate(self):self.assertEqual(self.run_case(['reserved'])['verdict'],'needs_revision')
    def test_opaque_rgb_refused(self):
        Image.new('RGB',(40,32)).save(self.p/'rgb.png')
        with self.assertRaises(ValueError):mask(self.p/'rgb.png','alpha')
    def test_full_alpha_reference_refused(self):
        self.write('ref.png',np.ones_like(self.a))
        with self.assertRaises(ValueError):self.run_case()
    def test_mask_size_mismatch_refused(self):
        self.write('after.png',np.ones((12,12),bool))
        with self.assertRaises(ValueError):self.run_case()
    def test_changed_frozen_camera_refused(self):
        self.run_case();(self.p/'camera.json').write_text('{"modified":true}')
        with self.assertRaises(ValueError):check(self.p/'lock.json',self.p,self.p/'model.glb',self.p/'render.json')
    def test_render_not_bound_to_model_refused(self):
        self.run_case();(self.p/'model.glb').write_bytes(b'other')
        with self.assertRaises(ValueError):check(self.p/'lock.json',self.p,self.p/'model.glb',self.p/'render.json')
    def test_render_camera_mismatch_refused(self):
        self.run_case();r=json.loads((self.p/'render.json').read_text());r['views']['reserved']['alignment_sha256']='other';(self.p/'render.json').write_text(json.dumps(r))
        with self.assertRaises(ValueError):check(self.p/'lock.json',self.p,self.p/'model.glb',self.p/'render.json')
    def test_invalid_threshold_or_noise_rejected(self):
        self.spec['views'][0]['uncertainty_px']=3
        with self.assertRaises(ValueError):self.run_case()
    def test_symmetric_boundary_distance_detects_missing_shape(self):
        b=self.a.copy();b[16:,:]=False;r=metrics(self.a,b);self.assertLess(r['iou'],1);self.assertGreater(r['boundary_p95_px'],2)
if __name__=='__main__':unittest.main()
