import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_coarse_initialization import fixture
import coarse_initialization as ci
import shape_acceptance as shape
class CurveCameraLockTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);s,self.contract=fixture(self.root);r=ci.fit(s,self.contract,self.root,40);self.spec,self.report=r['spec'],r['report'];self.cid=self.contract['curves'][0]['camera_id'];c=self.contract['curves'][0];self.plan={'calibrations':{self.cid:{'method':'geometry-curves','reference_id':c['reference_id'],'rationale':'synthetic camera baseline','uncertainty':'synthetic mechanism only','reviewer':'fixture','max_error_px':c['max_error_px']}}}
 def lock(self):return shape.lock_curves(self.spec,self.plan,self.cid,self.contract,self.report,self.root)
 def test_reverified_curve_baseline_locks_actual_geometry(self):
  self.assertTrue(self.lock()['passed']);cal=self.plan['calibrations'][self.cid];self.assertEqual(cal['identity'],shape.camera_identity(self.spec,self.cid,cal))
 def test_stale_curve_geometry_invalidates_lock(self):
  self.lock();cal=self.plan['calibrations'][self.cid];old=cal['identity'];b=self.contract['curves'][0]['bindings'][0];c=next(x for x in self.spec['components']if x['id']==b['component_id']);c.setdefault('position',[0,0,0])[0]+=.01;self.assertNotEqual(old,shape.camera_identity(self.spec,self.cid,cal))
 def test_reference_target_edit_invalidates_lock(self):
  self.lock();cal=self.plan['calibrations'][self.cid];old=cal['identity'];cal['geometry_curves'][0]['samples'][0]['pixel'][0]+=.01;self.assertNotEqual(old,shape.camera_identity(self.spec,self.cid,cal))
 def test_removing_calibrated_actual_edge_invalidates_lock(self):
  self.lock();cal=self.plan['calibrations'][self.cid];b=self.contract['curves'][0]['bindings'][0];c=next(x for x in self.spec['components']if x['id']==b['component_id']);c['geometry']['triangles']=[0,2,3]
  self.assertRaisesRegex(ValueError,'edge removed',shape.camera_identity,self.spec,self.cid,cal)
 def test_unrelated_component_does_not_stale_calibrated_curve(self):
  self.lock();cal=self.plan['calibrations'][self.cid];old=cal['identity'];self.spec['components'].append({'id':'other','kind':'assembly','position':[.1,0,0]});self.assertEqual(old,shape.camera_identity(self.spec,self.cid,cal))
 def test_curve_lock_rejects_forged_fit_pass(self):
  self.report['full_calibrated_geometry_sha256']='0'*64;self.assertRaisesRegex(ValueError,'verification failed',self.lock)
 def test_curve_lock_cannot_change_original_tolerance(self):
  self.plan['calibrations'][self.cid]['max_error_px']*=2;self.assertRaisesRegex(ValueError,'tolerance mismatch',self.lock)
if __name__=='__main__':unittest.main()
