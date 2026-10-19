import json,sys,tempfile,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import repair_project as rp,workflow,project
class RepairProjectTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)/'project';self.root.mkdir();(self.root/'ref.bin').write_bytes(b'software reference fixture');(self.root/'source.py').write_text('x=1')
  self.spec={'schema_version':1,'id':'toy','domain':'generic','coordinate_system':{'up':'y','forward':'z','unit':'m'},'references':[{'id':'ref','path':'ref.bin','sha256':rp.sha(self.root/'ref.bin'),'origin':'synthetic','approved':False,'provenance':'software-only fixture','image_size':[16,16]}],'source_files':[{'path':'source.py','sha256':rp.sha(self.root/'source.py')}],'parameters':{'x':{'value':0,'min':-1,'max':1}},'materials':{'m':{'color':'#ffffff'}},'components':[{'id':'body','role':'body','material':'m','position':[{'param':'x'},0,0],'geometry':{'type':'box','size':[1,1,1]}},{'id':'button','role':'button','material':'m','geometry':{'type':'box','size':[.1,.1,.1]}}],'cameras':{'front':{'type':'orthographic','position':[0,0,3],'target':[0,0,0],'width':16,'height':16,'ortho_height':3},'side':{'type':'orthographic','position':[3,0,0],'target':[0,0,0],'width':16,'height':16,'ortho_height':3}},'observations':[],'checks':[],'quality_contract':{'scope':'synthetic-software-test','limits':{}}}
  rp.save(self.root/'spec.json',self.spec);rp.save(self.root/'analysis.json',{'references':[{'id':'ref','origin':'synthetic','image_size':[16,16]}],'feature_inventory':[{'reference_id':'ref','feature':'body-shape','component_id':'body','required':False,'visibility':'visible'}],'inferences':[]});rp.save(self.root/'project.json',{'schema_version':1,'builds':[],'history':[]});workflow.init(self.root/'spec.json',self.root/'state.json')
  from common_reference_fixture import admit
  self.spec,self.plan=admit(self.root,self.spec,['body'],['button'])
  self.contract={'version':1,'editable_components':['body'],'allowed_parameters':['x'],'protected_components':[{'id':'button','mode':'exact'}],'targets':[{'id':'shape','component_ids':['body'],'reference_ids':['ref'],'problem':'software test','expected':'software test','check_ids':['outline','depth']}],'checks':[{'id':'outline','method':'visual','component_ids':['body'],'view_ids':['front'],'view_role':'original'},{'id':'depth','method':'visual','component_ids':['body'],'view_ids':['side'],'view_role':'depth'}]};rp.save(self.root/'contract.json',self.contract);rp.start(self.root,self.root/'contract.json',self.root/'session')
 def test_attachment_and_numeric_gate(self):self.assertTrue(rp.gate(self.root/'spec.json')['passed'])
 def test_frozen_reference_plan_cannot_relax_goal_or_tolerance(self):
  self.plan['task']['goal']='a weaker goal';rp.save(self.root/'reference-plan-v2.json',self.plan);self.assertRaisesRegex(ValueError,'frozen reference admission changed',rp.gate,self.root/'spec.json')
 def test_reference_admission_pin_cannot_be_removed_from_metadata(self):
  m=rp.read(self.root/'project.json');m.pop('reference_admission_sha256');rp.save(self.root/'project.json',m);self.assertRaisesRegex(ValueError,'admission removed',rp.policy,self.root/'spec.json')
 def test_no_visual_approval_from_numeric_pass(self):self.assertRaisesRegex(ValueError,'visual review',rp.gate,self.root/'spec.json',True)
 def test_policy_removal_rejected(self):m=rp.read(self.root/'project.json');del m['repair_session'];rp.save(self.root/'project.json',m);self.assertRaisesRegex(ValueError,'removed',workflow.validate_spec,self.root/'spec.json')
 def test_missing_metadata_not_bypass(self):
  (self.root/'project.json').unlink();self.assertRaisesRegex(ValueError,'metadata missing',workflow.validate_spec,self.root/'spec.json')
 def test_changed_protected_part_rejected(self):s=copy.deepcopy(self.spec);s['components'][1]['position']=[1,0,0];rp.save(self.root/'spec.json',s);self.assertRaisesRegex(ValueError,'constraints failed',rp.gate,self.root/'spec.json')
 def test_body_gate_rejects_missing_repair_review(self):self.assertRaisesRegex(ValueError,'visual review',workflow.validate_evidence,self.root/'spec.json',self.root/'does-not-exist.json','body')
 def test_stale_source_not_hidden_by_cache(self):rp.gate(self.root/'spec.json');(self.root/'source.py').write_text('x=2');self.assertRaisesRegex(ValueError,'stale',rp.gate,self.root/'spec.json')
 def test_restore_uses_frozen_operational_analysis(self):
  old=(self.root/'analysis.json').read_bytes();rp.save(self.root/'analysis.json',{'feature_inventory':[{'component_id':'unknown'}]});out=self.root.parent/'restored-analysis';rp.restore_project(self.root,out);self.assertEqual((out/'analysis.json').read_bytes(),old);project.validate(out)
 def test_restore_forks_valid_baseline(self):
  s=copy.deepcopy(self.spec);s['parameters']['x']['value']=.3;rp.save(self.root/'spec.json',s);out=self.root.parent/'restore';r=rp.restore_project(self.root,out);self.assertTrue(r['passed']);workflow.validate_spec(out/'spec.json');self.assertEqual(rp.read(out/'spec.json')['parameters']['x']['value'],0);self.assertEqual(rp.read(self.root/'spec.json')['parameters']['x']['value'],.3);self.assertFalse(rp.read(out/'state.json')['stages']);self.assertRaisesRegex(ValueError,'exists',rp.restore_project,self.root,out)
 def test_cached_geometry_does_not_skip_review_evidence_validation(self):
  from unittest.mock import patch
  review=self.root/'review.json';rp.save(review,{'version':1});meta=rp.read(self.root/'project.json');meta['repair_review']={'path':'review.json','sha256':rp.sha(review),'candidate_sha256':rp.sha(self.root/'spec.json')};rp.save(self.root/'project.json',meta)
  with patch('shape_acceptance.validate_review',return_value={'numeric_passed':True})as shape_review,patch.object(rp.model_repair,'check',wraps=rp.model_repair.check)as check,patch.object(rp.model_repair,'_validate_review_evidence',return_value={'passed':True,'errors':[]})as verify:
   rp.gate(self.root/'spec.json',True);rp.gate(self.root/'spec.json',True);self.assertEqual(check.call_count,1);self.assertEqual(verify.call_count,2);self.assertEqual(shape_review.call_count,2)
  with patch.object(rp.model_repair,'_validate_review_evidence',return_value={'passed':False,'errors':['stale receipt']}):self.assertRaisesRegex(ValueError,'stale receipt',rp.gate,self.root/'spec.json',True)
 def test_context_tamper_not_hidden_by_cache(self):
  rp.gate(self.root/'spec.json');f=self.root/'session/session.json';record=rp.read(f);snapshot=f.parent/record['context'][0]['snapshot'];snapshot.write_text('tampered');self.assertRaises(ValueError,rp.gate,self.root/'spec.json')
 def test_archive_preserves_original_bytes_without_rewriting_approval(self):
  from unittest.mock import patch
  artifact=self.root/'image.png';artifact.write_bytes(b'image');review=self.root/'review.json';rp.save(review,{'results':[{'artifacts':[{'path':'image.png','sha256':rp.sha(artifact)}]}]});meta=rp.read(self.root/'project.json');meta['repair_review']={'path':'review.json'};rp.save(self.root/'project.json',meta)
  with patch.object(rp,'gate',return_value={'passed':True}):r=rp.archive_evidence(self.root,self.root/'archive')
  manifest=rp.read(Path(r['path'])/'inventory.json');self.assertTrue(any(x['role']=='frozen-baseline'for x in manifest['files']))
  for x in manifest['files']:self.assertEqual(rp.sha(Path(r['path'])/x['path']),x['sha256'])
  original=next(x for x in manifest['files']if x['role']=='accepted-review');self.assertEqual((Path(r['path'])/original['path']).read_bytes(),review.read_bytes())
if __name__=='__main__':unittest.main()
