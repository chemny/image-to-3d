import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import project,reference_admission as admission,reference_set,shape_acceptance as shape,scene_build,workflow,repair_project
from common_reference_fixture import admit

class CommonAdmissionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
  Image.new('RGB',(100,100),'yellow').save(self.base/'input.png');self.root=self.base/'task';project.init(self.base/'input.png','generic',self.root)
  self.spec=project.read(self.root/'spec.json');self.spec.update(parameters={},components=[{'id':'body','role':'shell','material':'m','geometry':{'type':'mesh','positions':[-1,-1,0,1,-1,0,1,1,0,-1,1,0,0,-1,0,0,1,0],'triangles':[0,4,5,0,5,3,4,1,2,4,2,5]}}],materials={'m':{'color':'#ffffff'}},cameras={'front':{'type':'orthographic','position':[0,0,3],'target':[0,0,0],'width':100,'height':100,'ortho_height':3},'depth':{'type':'orthographic','position':[3,0,3],'target':[0,0,0],'width':100,'height':100,'ortho_height':3}},observations=[])
  frame=copy.deepcopy(self.spec['components'][0]);frame['id']='frame';self.spec['components'].append(frame)
  self.spec,self.plan=admit(self.root,self.spec,['body'],['frame'])
 def save(self):
  project.save(self.root/'reference-plan-v2.json',self.plan)
  for r in self.spec['source_files']:
   if r['path']=='reference-plan-v2.json':r['sha256']=project.sha(self.root/r['path'])
  project.save(self.root/'spec.json',self.spec)
 def camera(self):
  from reconstruction import project as proj
  bindings=[{'component_id':'frame','vertex_index':i}for i in range(6)];points=shape.points(self.spec,bindings)
  self.spec['observations']=[{'id':'a'+str(i),'component_id':'frame','binding':bindings[i],'camera_id':'front','reference_id':'original','target':proj(p,self.spec['cameras']['front']),'role':'calibration' if i<4 else 'validation','parameter_ids':[],'sigma_px':1}for i,p in enumerate(points)]
  self.plan['calibrations']={'front':{'reference_id':'original','method':'known-camera','rationale':'synthetic camera verification only','uncertainty':'no photo ambiguity assessed','reviewer':'fixture','max_error_px':.1,'calibration_ids':['a0','a1','a2','a3'],'validation_ids':['a4','a5']}}
  shape.lock(self.spec,self.plan,'front')
 def feature(self):
  self.camera();r=self.plan['critical_components'][0];r['features']=[{'id':'edge','kind':'curve','component_ids':['body'],'bindings':[{'component_id':'body','vertex_index':0},{'component_id':'body','vertex_index':1}],'camera_id':'front','reference_ids':['original'],'target':[[16.6666666667,83.3333333333],[83.3333333333,83.3333333333]],'max_error':1,'criterion':'bottom edge','severity':'critical'}];return r['features'][0]
 def test_default_new_projects_are_v2_pending(self):
  root=self.base/'new';project.init(self.base/'input.png','generic',root);s=project.read(root/'spec.json');self.assertEqual(s['quality_contract']['reference_standard'],2)
  self.assertRaisesRegex(ValueError,'pending',reference_set.validate,root/'spec.json')
 def test_diagnostic_build_cannot_skip_reference_preparation(self):
  self.plan['status']='pending';self.save();self.assertRaisesRegex(ValueError,'pending',project.gate_build,self.root,True)
 def test_common_create_and_repair_admission(self):
  self.assertTrue(reference_set.validate(self.root/'spec.json','spec')['passed'])
  self.plan['task']['mode']='create';self.save();self.assertTrue(reference_set.validate(self.root/'spec.json','spec')['passed'])
 def test_missing_roi_rejected(self):
  self.plan['critical_components'][0]['evidence'][0]['roi']=[-1,0,100,100];self.save();self.assertRaisesRegex(ValueError,'ROI',reference_set.validate,self.root/'spec.json')
 def test_uncertainty_that_blocks_feature_not_passed(self):
  self.plan['critical_components'][0]['blocking_unknowns']=['unknown joint'];self.save();self.assertRaisesRegex(ValueError,'gap',reference_set.validate,self.root/'spec.json')
 def test_feature_uses_only_active_authority(self):
  self.plan['critical_components'][0]['features'][0]['reference_ids']=['old-revision'];self.save();self.assertRaisesRegex(ValueError,'authoritative',reference_set.validate,self.root/'spec.json')
 def test_uncovered_affected_part_rejected(self):
  self.spec['components'].append({'id':'other'});self.plan['task']['affected_component_ids'].append('other');self.save();self.assertRaisesRegex(ValueError,'every affected',reference_set.validate,self.root/'spec.json','spec')
 def test_free_points_cannot_score_shape(self):
  f=self.feature();f['bindings'][0]={'component_id':'body','local_point':[0,0,0]};self.save();self.assertRaisesRegex(ValueError,'free scoring',reference_set.validate,self.root/'spec.json','spec')
 def test_locked_camera_and_target_changes_rejected(self):
  self.feature();self.save();reference_set.validate(self.root/'spec.json','spec');self.spec['cameras']['front']['position'][0]=1;self.save();self.assertRaisesRegex(ValueError,'after lock',reference_set.validate,self.root/'spec.json','spec')
 def test_heldout_camera_anchor_never_silently_accepted(self):
  self.camera();self.spec['observations'][-1]['target'][0]+=5;self.assertRaisesRegex(ValueError,'held-out',shape.lock,self.spec,self.plan,'front')
 def test_locked_camera_identity_tracks_actual_anchor_mesh(self):
  self.feature();old=self.plan['calibrations']['front']['identity']
  self.spec['components'][1]['geometry']['positions'][0]+=.01
  self.assertNotEqual(old,shape.camera_identity(self.spec,'front',self.plan['calibrations']['front']))
  self.assertRaisesRegex(ValueError,'stale/unlocked',shape.evaluate,self.spec,self.plan)
 def test_camera_lock_rejects_unrenderable_unused_mesh_anchors(self):
  self.camera();self.spec['components'][1]['geometry']['triangles']=[0,1,2]
  self.assertRaisesRegex(ValueError,'undefined mesh vertex normal',shape.lock,self.spec,self.plan,'front')
 def test_locked_camera_identity_tracks_anchor_parent_transform(self):
  self.feature();old=self.plan['calibrations']['front']['identity']
  self.spec['components'].append({'id':'anchor-parent','kind':'assembly','position':[.01,0,0]})
  self.spec['components'][1]['parent']='anchor-parent'
  self.assertNotEqual(old,shape.camera_identity(self.spec,'front',self.plan['calibrations']['front']))
 def test_unrelated_body_edit_preserves_camera_anchor_identity(self):
  self.feature();old=self.plan['calibrations']['front']['identity']
  self.spec['components'][0]['geometry']['positions'][0]+=.01
  self.assertEqual(old,shape.camera_identity(self.spec,'front',self.plan['calibrations']['front']))
 def fit_setup(self):
  self.camera();self.spec['parameters']={'cx':{'value':.2,'min':-.5,'max':.5}};self.spec['cameras']['front']['position'][0]={'param':'cx'};self.spec['cameras']['front']['target'][0]={'param':'cx'}
  for o in self.spec['observations']:o['parameter_ids']=['cx']
 def test_camera_fit_builds_geometry_once_and_keeps_it_unchanged(self):
  self.fit_setup()
  with patch.object(scene_build,'build',wraps=scene_build.build)as build:r=shape.fit_camera(self.spec,self.plan,'front',['cx'],60)
  self.assertEqual(build.call_count,1);self.assertAlmostEqual(r['parameter_values']['cx'],0,places=5);self.assertLess(r['final_objective'],1e-7);self.assertEqual(r['spec']['components'],self.spec['components']);self.assertEqual(self.spec['parameters']['cx']['value'],.2)
 def test_camera_fit_does_not_use_heldout_targets_in_selection(self):
  self.fit_setup();first=shape.fit_camera(self.spec,self.plan,'front',['cx'],40)
  for o in self.spec['observations']:
   if o['role']=='validation':o['target'][0]+=1000
  second=shape.fit_camera(self.spec,self.plan,'front',['cx'],40);self.assertEqual(first['parameter_values'],second['parameter_values']);self.assertGreater(second['errors_px']['a5'],999)
 def test_camera_fit_cannot_move_geometry(self):
  self.fit_setup();self.spec['components'][0]['position']=[{'param':'cx'},0,0];self.assertRaisesRegex(ValueError,'must not alter geometry',shape.fit_camera,self.spec,self.plan,'front',['cx'])
 def test_camera_fit_rejects_unobservable_parameter(self):
  self.fit_setup();self.spec['parameters']['unused']={'value':0,'min':-1,'max':1}
  for o in self.spec['observations']:o['parameter_ids'].append('unused')
  self.assertRaisesRegex(ValueError,'unobservable',shape.fit_camera,self.spec,self.plan,'front',['cx','unused'])
 def test_concentrated_camera_anchors_rejected(self):
  self.camera()
  for o in self.spec['observations']:o['target']=[50,50]
  self.assertRaisesRegex(ValueError,'concentrated',shape.lock,self.spec,self.plan,'front')
 def test_actual_geometry_movement_causes_feature_failure(self):
  self.feature();self.assertTrue(shape.evaluate(self.spec,self.plan)['numeric_passed']);self.spec['components'][0]['geometry']['positions'][1]+=.2;self.assertFalse(shape.evaluate(self.spec,self.plan)['numeric_passed'])
 def test_curve_interior_bow_not_hidden_by_correct_endpoints(self):
  self.assertGreater(shape.curve_error([[0,0],[10,0]],[[0,0],[5,4],[10,0]]),3)
 def test_section_and_connection_measure_actual_geometry(self):
  f=self.feature();f.update(kind='section',target=[[-1,-1,0],[1,-1,0]],max_error=.01);self.assertTrue(shape.evaluate(self.spec,self.plan)['numeric_passed'])
  f.update(kind='connection',max_error=.1);self.assertFalse(shape.evaluate(self.spec,self.plan)['numeric_passed'])
 def test_smooth_join_detects_angle_and_position_separately(self):
  f=self.feature();f.update(kind='smooth_join',bindings=[{'component_id':'body','vertex_index':i}for i in (0,1,2,0,1,2)],max_error=3,max_gap=.01)
  self.assertTrue(shape.evaluate(self.spec,self.plan)['numeric_passed'])
  self.spec['components'][0]['geometry']['positions'] += [-1,-1,.02,1,-1,.02,1,1,.5]
  f['bindings'][3:]=[{'component_id':'body','vertex_index':i}for i in (6,7,8)]
  row=shape.evaluate(self.spec,self.plan)['features'][0];self.assertFalse(row['passed']);self.assertGreater(row['error'],3);self.assertGreater(row['gap'],.01)
 def test_numeric_result_never_adopts_reference_match(self):
  self.feature();r=shape.evaluate(self.spec,self.plan);self.assertTrue(r['numeric_passed']);self.assertFalse(r['reference_match_passed'])
 def test_legacy_start_and_attach_cannot_bypass(self):
  self.spec['quality_contract'].pop('reference_standard');self.save();self.assertRaisesRegex(ValueError,'common reference',admission.repair_preflight,self.root/'spec.json',{})
 def test_no_geometry_edit_before_freeze(self):
  self.spec['components'][0]['position']=[1,0,0];self.save();self.assertRaisesRegex(ValueError,'before repair',admission.repair_preflight,self.root/'spec.json',{'editable_components':['body'],'protected_components':[{'id':'frame','mode':'exact'}]})
 def test_contract_scope_cannot_expand_admission(self):
  self.assertRaisesRegex(ValueError,'affected scope',admission.repair_preflight,self.root/'spec.json',{'editable_components':['body','extra']})
 def test_prepare_keeps_baseline_and_clears_old_approval(self):
  with self.assertRaisesRegex(ValueError,'exists'):admission.prepare(self.root,'repair','reference_match','another task')
  self.assertEqual(project.read(self.root/'state.json')['stages'],{})
 def test_missing_capture_never_replaced_by_manual_pass(self):
  self.feature();self.assertRaisesRegex(ValueError,'current actual capture',shape.validate_review,self.root/'spec.json',self.spec,self.plan,{'shape_review':{'intent':'technical_fix','technical_verdict':'pass','reference_verdict':'pass'},'artifacts':[]},self.root/'evidence.json')
 def test_every_feature_review_required(self):
  self.feature();e={'shape_review':{'intent':'technical_fix','technical_verdict':'pass','reference_verdict':'pass','capture_receipt':'receipt.json','features':[]},'artifacts':[{'path':'receipt.json','sha256':'test'}]}
  with patch('repair_capture.validate_receipt',return_value={'views':['front']}):self.assertRaisesRegex(ValueError,'per-feature',shape.validate_review,self.root/'spec.json',self.spec,self.plan,e,self.root/'evidence.json')
 def session(self):
  self.feature();self.save()
  c={'version':1,'editable_components':['body'],'allowed_parameters':[],'protected_components':[{'id':'frame','mode':'exact'}],'allow_feature_rebinding':True,
   'targets':[{'id':'shape','component_ids':['body'],'reference_ids':['original'],'problem':'software fixture','expected':'fixed edge','check_ids':['outline','depth']}],
   'checks':[{'id':'outline','method':'visual','component_ids':['body'],'view_ids':['front'],'view_role':'original'},{'id':'depth','method':'visual','component_ids':['body'],'view_ids':['depth'],'view_role':'depth'}]}
  project.save(self.root/'contract.json',c);return repair_project.start(self.root,self.root/'contract.json',self.root/'session')['session_path']
 def test_raw_session_freezes_reference_target_and_goal(self):
  import model_repair
  session=self.session();self.plan['task']['goal']='weaker';self.save();r=model_repair.check(session,self.root/'spec.json');self.assertFalse(r['passed']);self.assertIn('beyond geometry bindings',';'.join(r['errors']))
 def test_technical_fix_cannot_move_actual_surface(self):
  import model_repair
  session=self.session();self.spec['components'][0]['geometry']['positions'][1]+=.1;self.save();r=model_repair.check(session,self.root/'spec.json');self.assertFalse(r['passed']);self.assertIn('technical_fix changed actual surface',';'.join(r['errors']))
 def test_raw_init_legacy_requires_explicit_diagnostics(self):
  import model_repair
  self.spec['quality_contract'].pop('reference_standard');self.save();project.save(self.root/'contract.json',{})
  self.assertRaisesRegex(ValueError,'common reference',model_repair.init,self.root/'spec.json',self.root/'contract.json',self.root/'legacy')
 def test_topology_rebind_preserves_targets_and_requires_current_evidence(self):
  import model_repair
  session=self.session();old_hash=project.sha(self.root/'reference-plan-v2.json');old=copy.deepcopy(self.plan['critical_components'][0]['features'][0]['bindings'])
  g=self.spec['components'][0]['geometry'];g['positions'][:6]=g['positions'][3:6]+g['positions'][:3];g['triangles']=[1 if i==0 else 0 if i==1 else i for i in g['triangles']]
  bindings=self.plan['critical_components'][0]['features'][0]['bindings'];bindings[0]['vertex_index']=1;bindings[1]['vertex_index']=0;self.save()
  artifact={'path':'test-review.txt','sha256':project.sha(self.root/'test-review.txt')}
  receipt={'version':1,'baseline_plan_sha256':old_hash,'current_plan_sha256':project.sha(self.root/'reference-plan-v2.json'),'features':[{'id':'edge','old_bindings':old,'new_bindings':bindings,'verdict':'pass','method':'semantic-review','reviewer':'software fixture','notes':'same semantic edge after vertex reorder; software mechanism only','geometry_sha256':admission.identity(scene_build.resolve(self.spec['components'],self.spec['parameters'])),'artifacts':[artifact]}]}
  project.save(self.root/'rebind.json',receipt);entry={'path':'rebind.json','sha256':project.sha(self.root/'rebind.json')};self.spec['source_files'].append(entry);self.save();meta=project.read(self.root/'project.json');meta['reference_binding_review']=entry;project.save(self.root/'project.json',meta)
  self.assertTrue(model_repair.check(session,self.root/'spec.json')['passed']);self.assertTrue(repair_project.policy(self.root/'spec.json'))
  receipt['features'][0]['geometry_sha256']='stale';project.save(self.root/'rebind.json',receipt);entry['sha256']=project.sha(self.root/'rebind.json');self.save();meta['reference_binding_review']=entry;project.save(self.root/'project.json',meta)
  self.assertFalse(model_repair.check(session,self.root/'spec.json')['passed'])

if __name__=='__main__':unittest.main()
