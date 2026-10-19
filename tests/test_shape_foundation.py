"""Numerical/gate fixtures only; none is photographic likeness certification."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import shape_foundation as f,foundation_fit,scene_build as scene,reconstruction as rec

def fixture():
    net={'control_points':{},'patches':[{'id':'shell','control_points':[[f'p{i}{j}'for j in range(4)]for i in range(4)],'segments':[8,8]}],'shared_edges':[]}
    for i in range(4):
        for j in range(4):net['control_points'][f'p{i}{j}']={'position':[(-.6+.4*i),{'param':'crown'}if i in(1,2)else 0,(.6-.4*j)],'source':{'reference_id':'original','claim':'synthetic control'}}
    s={'schema_version':1,'id':'generic-shell-fixture','domain':'generic','coordinate_system':{'unit':'m','up':'y','forward':'z'},'quality_contract':{'scope':'synthetic-software-test','foundation_standard':1,'limits':{}},'references':[{'id':'original','origin':'synthetic','approved':False,'image_size':[256,256]}],'source_files':[],
        'parameters':{'scale':{'value':1,'min':1,'max':1},'crown':{'value':.1,'min':.01,'max':.5}},'components':[{'id':'shell','role':'body','parent':None,'material':'paint','geometry':{'type':'bezier_network','network':net}}],
        'materials':{'paint':{'color':'#eeee00','metalness':0,'roughness':.3}},'cameras':{'side':{'type':'orthographic','width':256,'height':256,'position':[0,1,5],'target':[0,0,0],'ortho_height':2,'near':.01,'far':100},'quarter':{'type':'perspective','width':256,'height':256,'position':[3,2,4],'target':[0,0,0],'fov_y_deg':35,'near':.01,'far':100}},'observations':[],'checks':[]}
    b=lambda u,v:{'component_id':'shell','patch_id':'shell','uv':[u,v]}
    s['foundation']=f.template();s['foundation'].update(primary_components=['shell'],required_views=['side','quarter'],required_features=['outline','internal','volume','surface'],feature_definitions=[{'id':k,'kind':k,'criterion':'synthetic whole form check only','reference_ids':['original'],'view_ids':['side','quarter']}for k in ['outline','internal','volume','surface']],controls=[{'id':'roof-curve','kind':'curve','bindings':[b(i/8,.5)for i in range(9)],'reference_ids':['original'],'parameter_ids':['crown'],'rationale':'known synthetic arch','max_turn_deg':30},{'id':'cross-section','kind':'section','bindings':[b(.5,i/4)for i in range(5)],'reference_ids':['original'],'parameter_ids':['crown'],'rationale':'known synthetic section'}],fit_groups=[{'level':'curves','parameter_ids':['crown']}],scale_gauge={'parameter_id':'scale','reason':'fixed synthetic unit basis'})
    target=copy.deepcopy(s);target['parameters']['crown']['value']=.32
    for cid in s['cameras']:
        for i,u in enumerate([.15,.4,.65,.85]):
            binding=b(u,.5);world=f.points(target,[binding])[0]
            s['observations'].append({'id':cid+str(i),'reference_id':'original','feature':'curve sample','camera_id':cid,'component_id':'shell','patch_id':'shell','uv':[u,.5],'roi':[0,0,256,256],'parameter_ids':['crown'],'role':'validation'if i==3 else 'calibration','target':rec.project(world,s['cameras'][cid]),'sigma_px':1,'tolerance_px':.1})
    return s

class FoundationTests(unittest.TestCase):
    def setUp(self):self.s=fixture()
    def test_native_controls_and_build_agree(self):
        self.assertTrue(f.evaluate(self.s)['numeric_passed']);self.assertFalse(f.evaluate(self.s)['visual_pass']);self.assertTrue(scene.build(self.s)['components'])
    def test_control_parameters_change_actual_surface(self):
        before=f.evaluate(self.s);self.s['parameters']['crown']['value']=.3;after=f.evaluate(self.s)
        self.assertNotEqual(before['foundation_identity'],after['foundation_identity']);self.assertNotEqual(before['rows'][0]['world_points'],after['rows'][0]['world_points'])
    def test_fixed_gauge(self):
        self.s['parameters']['scale']['max']=2
        with self.assertRaisesRegex(ValueError,'gauge'):f.contract(self.s)
    def test_disconnected_scoring_points_rejected(self):
        self.s['foundation']['controls'][0]['bindings'][0]={'component_id':'shell','local_point':[0,0,0]}
        with self.assertRaisesRegex(ValueError,'real primary'):f.evaluate(self.s)
    def test_missing_primary_coverage(self):
        self.s['components'].append({'id':'other','role':'body','material':'paint','geometry':{'type':'box','size':[1,1,1]}});self.s['foundation']['primary_components'].append('other')
        with self.assertRaisesRegex(ValueError,'every primary'):f.contract(self.s)
    def test_duplicate_views_are_not_depth_validation(self):
        self.s['cameras']['quarter']['position']=self.s['cameras']['side']['position'][:]
        with self.assertRaisesRegex(ValueError,'different directions'):f.contract(self.s)
    def test_wrong_surface_shape_not_hidden_by_valid_build(self):
        self.s['foundation']['controls'][0]['max_turn_deg']=1
        self.assertTrue(scene.build(self.s));self.assertFalse(f.evaluate(self.s)['numeric_passed'])
    def test_structure_relation_failure(self):
        bs=[self.s['foundation']['controls'][0]['bindings'][i]for i in (0,-1)]
        self.s['foundation']['relations']=[{'id':'span','bindings':bs,'min':.2,'max':.3}]
        self.assertFalse(f.evaluate(self.s)['numeric_passed'])
    def test_missing_internal_check_rejected(self):
        self.s['foundation']['feature_definitions'][1]['kind']='outline'
        with self.assertRaisesRegex(ValueError,'internal'):f.contract(self.s)
    def test_dependency_cycle_rejected(self):
        self.s['components'].append({'id':'trim','role':'trim','material':'paint','geometry':{'type':'box','size':[1,1,1]}});self.s['foundation']['dependency_edges']=[['shell','trim'],['trim','shell']]
        with self.assertRaisesRegex(ValueError,'cycle'):f.contract(self.s)
    def test_coarse_to_fine_order(self):
        self.s['foundation']['fit_groups']=[{'level':'sections','parameter_ids':['crown']},{'level':'proportion','parameter_ids':['scale']}]
        with self.assertRaisesRegex(ValueError,'coarse to fine'):f.contract(self.s)
    def test_fit_recovers_actual_arch(self):
        r=foundation_fit.fit(self.s,50);self.assertTrue(r['numeric_passed']);self.assertAlmostEqual(r['spec']['parameters']['crown']['value'],.32,places=3);self.assertFalse(r['visual_pass'])
    def test_held_out_target_does_not_select_fit(self):
        a=foundation_fit.fit(self.s,35);other=copy.deepcopy(self.s)
        for o in other['observations']:
            if o['role']=='validation':o['target']=[0,0]
        b=foundation_fit.fit(other,35);self.assertEqual(a['spec']['parameters'],b['spec']['parameters']);self.assertFalse(b['numeric_passed'])
    def test_camera_parameter_absorption_rejected(self):
        self.s['cameras']['side']['position'][0]={'param':'crown'}
        r=foundation_fit.fit(self.s,10);self.assertFalse(r['numeric_passed']);self.assertEqual(r['spec']['parameters']['crown']['value'],.1)
    def test_single_view_fit_refused(self):
        self.s['observations']=[o for o in self.s['observations']if o['camera_id']=='side']
        with self.assertRaisesRegex(ValueError,'multi-view'):foundation_fit.fit(self.s)
    def test_unobserved_parameter_refused(self):
        for o in self.s['observations']:o['parameter_ids']=[]
        with self.assertRaisesRegex(ValueError,'unobservable'):foundation_fit.fit(self.s)
    def test_missing_tolerance_refused(self):
        del self.s['observations'][0]['tolerance_px']
        with self.assertRaisesRegex(ValueError,'tolerance'):foundation_fit.fit(self.s)
    def test_detail_requires_foundation_review(self):
        with tempfile.TemporaryDirectory()as root:
            p=Path(root)/'spec.json';self.s['foundation']['phase']='detail';p.write_text(json.dumps(self.s))
            with self.assertRaisesRegex(ValueError,'acceptance required'):f.gate(p)
    def test_policy_downgrade_refused(self):
        with tempfile.TemporaryDirectory()as root:
            p=Path(root)/'spec.json';self.s['quality_contract'].pop('foundation_standard');p.write_text(json.dumps(self.s));(p.parent/'project.json').write_text(json.dumps({'foundation_standard':1}))
            with self.assertRaisesRegex(ValueError,'downgraded'):f.policy(p)
    def test_primary_change_invalidates_identity_but_trim_does_not(self):
        before=f.geometry_identity(self.s);self.s['components'].append({'id':'trim','role':'trim','material':'paint','geometry':{'type':'box','size':[.1,.1,.1]}});self.assertEqual(before,f.geometry_identity(self.s));self.s['components'][0]['position']=[0,.01,0];self.assertNotEqual(before,f.geometry_identity(self.s))
    def test_parent_motion_invalidates_identity(self):
        self.s['components'].append({'id':'parent','kind':'assembly','role':'assembly','position':[0,0,0]});self.s['components'][0]['parent']='parent';before=f.geometry_identity(self.s);self.s['components'][1]['position'][0]=.1;self.assertNotEqual(before,f.geometry_identity(self.s))
    def test_native_seam_failure_propagates(self):
        self.s['components'][0]['geometry']['network']['shared_edges']=[{'a':{'patch':'shell','edge':'u0'},'b':{'patch':'shell','edge':'u1'},'continuity':'C1'}]
        with self.assertRaisesRegex(ValueError,'shared edge'):f.evaluate(self.s)
if __name__=='__main__':unittest.main()

class DifferentialTests(unittest.TestCase):
    def test_plane_curvature_is_zero(self):
        from surface_differentials import sample
        g=[[[i/3,0,j/3]for j in range(4)]for i in range(4)]
        r=sample(g,.3,.7);self.assertAlmostEqual(r['mean_curvature'],0);self.assertEqual(r['principal_radius_magnitudes'],[None,None])
    def test_known_parabolic_cylinder(self):
        from surface_differentials import sample
        # x=u, y=u^2 in cubic Bernstein coefficients, z=v.
        ys=[0,0,1/3,1];g=[[[i/3,ys[i],j/3]for j in range(4)]for i in range(4)]
        r=sample(g,.5,.4);ks=sorted(abs(k)for k in r['principal_curvatures']);self.assertAlmostEqual(ks[0],0,places=10);self.assertAlmostEqual(ks[1],2/(2**1.5),places=10)
    def test_invalid_flattened_patch_refused(self):
        from surface_differentials import sample
        with self.assertRaisesRegex(ValueError,'degenerate'):sample([[[0,0,0]for j in range(4)]for i in range(4)],.5,.5)

class RecipeFoundationTests(unittest.TestCase):
 def setUp(self):
  self.s=fixture();self.s['parameters']['crown']={'value':.3,'min':.2,'max':.4}
  recipe={'version':1,'component_id':'shell','source':{'reference_id':'original','roi':[0,0,256,256]},'rationale':'Synthetic rounded continuous shell; not photo reconstruction','method':'smooth_loft','parameters':{'sections':[{'center':[0,-.3,0],'radii':[.2,.2]},{'center':[0,0,0],'radii':[{'param':'crown'},.25]},{'center':[0,.3,0],'radii':[.2,.2]}],'radial_segments':16,'max_chord_error':.02,'cap_depths':[.1,.1]}}
  self.s['components'][0]['geometry']={'type':'form_recipe','recipe':recipe};g=scene.prepared(self.s)[1]['shell']['geometry'];n=len(g['positions'])//3
  self.s['foundation']['controls']=[{'id':'outline','kind':'curve','bindings':[{'component_id':'shell','vertex_index':i}for i in [0,n//4,n//2,3*n//4]],'reference_ids':['original'],'parameter_ids':['crown'],'rationale':'Actual generated outline samples'},{'id':'section','kind':'section','bindings':[{'component_id':'shell','vertex_index':i}for i in [1,2,3,4]],'reference_ids':['original'],'parameter_ids':['crown'],'rationale':'Actual generated section samples'}]
  self.s['observations']=[]
 def test_recipe_is_regenerated_not_a_scoring_proxy(self):
  r=f.evaluate(self.s);self.assertTrue(r['construction_ready']);self.assertTrue(r['numeric_passed']);before=scene.build(self.s)
  self.s['parameters']['crown']['value']=.36;after=scene.build(self.s);self.assertNotEqual(before,after);self.assertNotEqual(r['foundation_identity'],f.geometry_identity(self.s))
 def test_recipe_unsupported_method_rejected(self):
  self.s['components'][0]['geometry']['recipe']['method']='pretend-mesh'
  with self.assertRaisesRegex(ValueError,'unsupported'):scene.build(self.s)
 def test_recipe_identity_rejected(self):
  self.s['components'][0]['geometry']['recipe']['component_id']='unrelated'
  with self.assertRaisesRegex(ValueError,'identity'):scene.build(self.s)
 def test_recipe_source_roi_rejected(self):
  self.s['components'][0]['geometry']['recipe']['source']['roi']=[0,0,1000,1000]
  with self.assertRaisesRegex(ValueError,'ROI'):scene.build(self.s)
 def test_recipe_landmark_comes_from_actual_generated_mesh(self):
  o={'component_id':'shell','vertex_index':2};p=scene.landmark(self.s,o);self.assertEqual(p,f.points(self.s,[o])[0])
 def test_legacy_sampled_mesh_not_promoted_to_generator(self):
  self.s['components'][0]['geometry']=scene.prepared(self.s)[1]['shell']['geometry']
  r=f.evaluate(self.s);self.assertTrue(r['numeric_passed']);self.assertFalse(r['construction_ready'])

class DirectionRegressionTests(unittest.TestCase):
 def test_same_orthographic_direction_different_distance_rejected(self):
  s=fixture();s['cameras']['quarter']=copy.deepcopy(s['cameras']['side']);s['cameras']['quarter']['position']=[0,2,10]
  with self.assertRaisesRegex(ValueError,'different directions'):f.evaluate(s)
 def test_opposite_parallel_axes_not_independent_depth(self):
  s=fixture();s['cameras']['quarter']=copy.deepcopy(s['cameras']['side']);s['cameras']['quarter']['position']=[0,-1,-5]
  with self.assertRaisesRegex(ValueError,'different directions'):f.evaluate(s)
 def test_whole_form_fixture_faces_upper_camera(self):
  s=fixture();d=f.evaluate(s)['differentials'];self.assertTrue(all(x['normal'][1]>0 for x in d['samples']))

class RecipeFittingTests(unittest.TestCase):
 setUp=RecipeFoundationTests.setUp
 def test_closed_nonvehicle_recipe_fit_recovers_actual_radius(self):
  self.s['components'][0]['geometry']['recipe']['method']='loft'
  p=self.s['components'][0]['geometry']['recipe']['parameters']
  p.pop('max_chord_error');p.pop('cap_depths')
  # Representation changed before this new synthetic task: bind the new actual rings explicitly.
  for control,indices in zip(self.s['foundation']['controls'],[[0,16,32,47],[16,18,20,22]]):control['bindings']=[{'component_id':'shell','vertex_index':i}for i in indices]
  truth=copy.deepcopy(self.s);truth['parameters']['crown']['value']=.36
  self.s['observations']=[]
  for cid in self.s['cameras']:
   for i,vertex in enumerate([16,18,20,22]):
    world=scene.landmark(truth,{'component_id':'shell','vertex_index':vertex})
    self.s['observations'].append({'id':cid+str(i),'reference_id':'original','feature':'actual ring point','component_id':'shell','camera_id':cid,'vertex_index':vertex,'parameter_ids':['crown'],'target':rec.project(world,self.s['cameras'][cid]),'roi':[0,0,256,256],'role':'validation'if i==3 else 'calibration','sigma_px':1,'tolerance_px':.1})
  result=foundation_fit.fit(self.s,45);self.assertTrue(result['numeric_passed']);self.assertAlmostEqual(result['spec']['parameters']['crown']['value'],.36,places=3);self.assertNotEqual(scene.build(self.s),scene.build(result['spec']))

class CurveFittingTests(unittest.TestCase):
 def test_actual_curves_participate_with_landmarks(self):
  s=fixture();truth=copy.deepcopy(s);truth['parameters']['crown']['value']=.32;control=s['foundation']['controls'][0]
  s['foundation']['fit_curves']=[{'id':'arch-'+cid,'control_id':control['id'],'reference_id':'original','camera_id':cid,'target_px':[rec.project(p,s['cameras'][cid])for p in f.points(truth,control['bindings'])],'role':'calibration','sigma_px':1,'tolerance_px':.1}for cid in s['cameras']]
  r=foundation_fit.fit(s,40);self.assertTrue(r['numeric_passed']);self.assertIn('arch-side',r['observations']);self.assertLess(r['observations']['arch-side']['error_px'],.1)
 def test_validation_curve_never_selects_candidate(self):
  s=fixture();control=s['foundation']['controls'][0];s['foundation']['fit_curves']=[{'id':'held-curve','control_id':control['id'],'reference_id':'original','camera_id':'side','target_px':[[0,0],[1,1]],'role':'validation','sigma_px':1,'tolerance_px':.1}]
  a=foundation_fit.fit(s,25);s['foundation']['fit_curves'][0]['target_px']=[[255,255],[254,254]];b=foundation_fit.fit(s,25)
  self.assertEqual(a['spec']['parameters'],b['spec']['parameters']);self.assertFalse(a['numeric_passed']);self.assertFalse(b['numeric_passed'])
