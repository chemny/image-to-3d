import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from PIL import Image
import coarse_initialization as ci
from reconstruction import project
import scene_build


def fixture(directory):
    image=Path(directory)/'reference.png';Image.new('RGB',(300,300),'white').save(image)
    parameters={'width':{'min':.3,'value':.45,'max':1.1},'shift':{'min':-.5,'value':-.1,'max':.5}}
    builder={'projection':'orthographic','width':300,'height':300,'target':[{'param':'shift'},0,0],
             'yaw_deg':0,'elevation_deg':0,'distance':5,'roll_deg':0,'ortho_height':2.5,'near':.01,'far':100}
    spec={'schema_version':1,'id':'independent-outline-fixture','domain':'generic',
          'coordinate_system':{'up':'+Y','forward':'+Z','unit':'m'},'parameters':parameters,
          'materials':{'body':{'color':'#f0c038'}},'components':[
              {'id':'plate','geometry':{'type':'mesh','positions':[
                  {'param':'width','scale':-1},-.5,0, {'param':'width'},-.5,0,
                  {'param':'width'},.5,0, {'param':'width','scale':-1},.5,0],
                  'triangles':[0,1,2,0,2,3]},'material':'body'},
              {'id':'protected','geometry':{'type':'box','size':[.1,.1,.1]},'material':'body','position':[-1,0,0]}],
          'cameras':{'view':ci.camera(builder,parameters)},'references':[
              {'id':'source','path':'reference.png','image_size':[300,300],
               'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'origin':'synthetic','approved':False}]}
    truth=copy.deepcopy(parameters);truth['width']['value']=.7;truth['shift']['value']=.1
    camera=ci.camera(builder,truth)
    points=[[-.7,0,0],[.7,0,0],[0,.5,0],[0,-.5,0],[-.7,.2,0],[.7,-.2,0]]
    curve={'id':'outer','camera_id':'view','reference_id':'source','closed':True,
           'bindings':[{'component_id':'plate','vertex_index':i} for i in range(4)],
           'samples':[{'id':'sample-'+str(i),'role':'calibration' if i<4 else 'validation',
                       'pixel':project(point,camera),'sigma_px':1} for i,point in enumerate(points)],'max_error_px':.1}
    contract={'version':1,'spec_identity':ci.digest(spec),'rationale':'Synthetic authored outline test; no photograph accuracy.',
              'gauge':'Fixed orthographic scale, axis orientation and object height; width and translation free.',
              'protected_component_ids':['protected'],'max_condition':1e5,'reject_bound_hits':True,
              'variable_ids':['width','shift'],'geometry_parameter_ids':['width'],
              'camera_builders':{'view':builder},'curves':[curve],
              'seeds':[{'width':.45,'shift':-.1},{'width':.9,'shift':.3}]}
    return spec,contract


class CoarseInitializationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.spec,self.contract=fixture(self.root)

    def fit(self,spec=None,contract=None,root=True):
        return ci.fit(spec or self.spec,contract or self.contract,self.root if root else None,iterations=40)

    def amend(self,callback):
        callback(self.spec);self.contract['spec_identity']=ci.digest(self.spec)

    def test_joint_native_effect_and_scope(self):
        result=self.fit();report=result['report'];candidate=result['spec']
        self.assertTrue(report['eligible_for_freeze'],report['errors'])
        self.assertAlmostEqual(candidate['parameters']['width']['value'],.7,places=5)
        self.assertAlmostEqual(candidate['parameters']['shift']['value'],.1,places=5)
        before=scene_build.build(self.spec)['components'][0]['meshes'][0]['positions']
        after=scene_build.build(candidate)['components'][0]['meshes'][0]['positions']
        self.assertNotEqual(before,after)
        self.assertTrue(report['sparse_matches_full']);self.assertTrue(report['protected_geometry_verified'])
        self.assertEqual(report['data_jacobian']['rank'],2)
        self.assertFalse(report['production_accepted']);self.assertFalse(report['visual_fidelity_accepted'])
        self.assertTrue(report['resources_verified']);self.assertEqual(len(report['calibration']),4)
        self.assertEqual(len(report['validation']),2)

    def test_full_native_identity_matches_actual_build_and_untraced_parts(self):
        result=self.fit();report=result['report']
        before=scene_build.build(self.spec);after=scene_build.build(result['spec'])
        self.assertEqual(report['initial_full_geometry_sha256'],ci.full_geometry_identity(before))
        self.assertEqual(report['full_calibrated_geometry_sha256'],ci.full_geometry_identity(after))
        self.assertNotEqual(report['initial_full_geometry_sha256'],report['full_calibrated_geometry_sha256'])
        changed=copy.deepcopy(after)
        changed['components'][1]['meshes'][0]['positions'][0]+=.02
        self.assertNotEqual(ci.full_geometry_identity(changed),ci.full_geometry_identity(after))
        camera_only=copy.deepcopy(after);camera_only['cameras']['view']['position'][0]+=.1
        self.assertEqual(ci.full_geometry_identity(camera_only),ci.full_geometry_identity(after))

    def test_heldout_cannot_change_winner_or_parameters(self):
        a=self.fit();changed=copy.deepcopy(self.contract)
        for sample in changed['curves'][0]['samples']:
            if sample['role']=='validation':sample['pixel']=[25,25]
        b=self.fit(contract=changed)
        self.assertEqual(a['spec'],b['spec'])
        self.assertEqual(a['report']['selected_seed_index'],b['report']['selected_seed_index'])
        self.assertEqual(a['report']['seeds'],b['report']['seeds'])
        self.assertFalse(b['report']['eligible_for_freeze'])
        self.assertTrue(any('sample exceeds' in e for e in b['report']['errors']))

    def test_missing_resource_root_diagnostic(self):
        result=self.fit(root=False)
        self.assertFalse(result['report']['resources_verified'])
        self.assertFalse(result['report']['eligible_for_freeze'])
        self.assertAlmostEqual(result['spec']['parameters']['width']['value'],.7,places=5)

    def test_stale_spec_and_image(self):
        bad=copy.deepcopy(self.spec);bad['id']='changed'
        with self.assertRaisesRegex(ValueError,'stale source spec'):self.fit(spec=bad)
        (self.root/'reference.png').write_bytes(b'changed image bytes')
        result=self.fit();self.assertFalse(result['report']['eligible_for_freeze'])
        self.assertTrue(any('stale source image' in e for e in result['report']['errors']))

    def test_wrong_mesh_edge_rejected(self):
        # Edge 1->3 is not in either triangle.
        bad=copy.deepcopy(self.contract);bad['curves'][0]['bindings']=[{'component_id':'plate','vertex_index':i} for i in [0,1,3]]
        with self.assertRaisesRegex(ValueError,'actual triangle edge'):self.fit(contract=bad)

    def test_protected_geometry_parameter_rejected(self):
        self.contract['protected_component_ids'].append('plate')
        with self.assertRaisesRegex(ValueError,'protected component'):self.fit()

    def test_camera_only_geometry_parameter_rejected(self):
        self.amend(lambda s:s['components'][1].update(position=[{'param':'shift'},0,0]))
        with self.assertRaisesRegex(ValueError,'camera-only'):self.fit()

    def test_protected_ancestor_transform_rejected(self):
        def change(s):
            s['components'].append({'id':'parent','kind':'assembly','position':[{'param':'width'},0,0]})
            s['components'][1]['parent']='parent'
        self.amend(change)
        with self.assertRaisesRegex(ValueError,'protected ancestor'):self.fit()

    def test_material_action_and_undeclared_camera_rejected(self):
        for field in ('material','action','camera'):
            spec=copy.deepcopy(self.spec);contract=copy.deepcopy(self.contract)
            if field=='material':spec['materials']['body']['roughness']={'param':'width'}
            if field=='action':spec['actions']=[{'pivot':[{'param':'width'},0,0]}]
            if field=='camera':spec['cameras']['extra']=dict(spec['cameras']['view'],ortho_height={'param':'shift'})
            contract['spec_identity']=ci.digest(spec)
            with self.subTest(field=field),self.assertRaises(ValueError):self.fit(spec,contract)

    def test_rank_deficient_data_remains_diagnostic(self):
        # Two identical camera translations make an unfixed gauge.
        self.spec['parameters']['shift2']={'min':-.5,'value':0,'max':.5}
        builder=self.contract['camera_builders']['view'];builder['target'][1]={'param':'shift2','scale':0}
        self.contract['variable_ids'].append('shift2')
        for seed in self.contract['seeds']:seed['shift2']=0
        self.contract['spec_identity']=ci.digest(self.spec)
        result=self.fit()
        self.assertFalse(result['report']['eligible_for_freeze'])
        self.assertLess(result['report']['data_jacobian']['rank'],3)
        self.assertIsNone(result['report']['data_jacobian']['condition'])

    def test_numerical_failure_candidate_retained(self):
        contract=copy.deepcopy(self.contract)
        for sample in contract['curves'][0]['samples']:
            if sample['role']=='calibration':sample['pixel'][1]+=10
        result=self.fit(contract=contract)
        self.assertIn('spec',result);self.assertFalse(result['report']['eligible_for_freeze'])

    def test_bound_hit_rule(self):
        self.amend(lambda s:s['parameters']['width'].update(max=.7))
        self.contract['seeds']=[{'width':.45,'shift':-.1}]
        result=self.fit();self.assertIn('width',result['report']['bound_hits'])
        self.assertFalse(result['report']['eligible_for_freeze'])

    def test_initial_camera_mismatch_rejected(self):
        self.amend(lambda s:s['cameras']['view'].update(up=[1,0,0]))
        with self.assertRaisesRegex(ValueError,'roll/up'):self.fit()

    def test_roll_builder_matches_native_projection(self):
        builder=copy.deepcopy(self.contract['camera_builders']['view'])
        builder.update(target=[0,0,0],roll_deg=90)
        camera=ci.camera(builder,self.spec['parameters'])
        self.assertAlmostEqual(camera['up'][0],1)
        self.assertAlmostEqual(project([1,0,0],camera)[0],150)
        self.assertAlmostEqual(project([1,0,0],camera)[1],30)
        builder.update(projection='perspective',fov_y_deg=35);del builder['ortho_height']
        camera=ci.camera(builder,self.spec['parameters']);pixel=project([1,0,0],camera)
        self.assertAlmostEqual(pixel[0],150);self.assertLess(pixel[1],150)

    def test_perspective_joint_width_distance_fixed_height_gauge(self):
        self.spec['parameters']['distance']={'min':3,'value':5,'max':8}
        builder=self.contract['camera_builders']['view']
        builder.update(projection='perspective',target=[0,0,0],distance={'param':'distance'},fov_y_deg=45)
        del builder['ortho_height']
        self.spec['cameras']['view']=ci.camera(builder,self.spec['parameters'])
        truth=copy.deepcopy(self.spec['parameters']);truth['distance']['value']=6
        target_camera=ci.camera(builder,truth)
        points=[[-.7,0,0],[.7,0,0],[0,.5,0],[0,-.5,0],[-.7,.2,0],[.7,-.2,0]]
        for sample,point in zip(self.contract['curves'][0]['samples'],points):sample['pixel']=project(point,target_camera)
        self.contract.update(variable_ids=['width','distance'],seeds=[{'width':.45,'distance':5}],spec_identity=ci.digest(self.spec))
        result=self.fit();self.assertTrue(result['report']['eligible_for_freeze'],result['report']['errors'])
        self.assertAlmostEqual(result['spec']['parameters']['width']['value'],.7,places=5)
        self.assertAlmostEqual(result['spec']['parameters']['distance']['value'],6,places=5)

    def test_unlinked_geometry_parameter_rejected(self):
        self.spec['parameters']['unused']={'min':0,'value':.5,'max':1}
        self.contract['variable_ids'].append('unused');self.contract['geometry_parameter_ids'].append('unused')
        for seed in self.contract['seeds']:seed['unused']=.5
        self.contract['spec_identity']=ci.digest(self.spec)
        with self.assertRaisesRegex(ValueError,'no permitted actual effect'):self.fit()

    def test_sparse_parent_rotation_agrees_with_full_native_geometry(self):
        def change(s):
            s['components'].append({'id':'parent','kind':'assembly','position':[.2,.1,0],'rotation':[0,0,.2]})
            s['components'][0]['parent']='parent'
        self.amend(change)
        result=self.fit()
        self.assertTrue(result['report']['sparse_matches_full'])

    def test_source_pixel_and_resolution_requirements(self):
        for mutation in (lambda c:c['curves'][0]['samples'][0].update(pixel=[300,50]),
                         lambda c:c['camera_builders']['view'].update(width=301)):
            c=copy.deepcopy(self.contract);mutation(c)
            if c['camera_builders']['view']['width']==301:
                with self.assertRaises(ValueError):self.fit(contract=c)
            else:
                self.assertFalse(self.fit(contract=c)['report']['eligible_for_freeze'])

    def test_actual_reference_roi_bounds(self):
        self.amend(lambda s:s['references'][0].update(roi=[290,0,20,30]))
        report=self.fit()['report'];self.assertFalse(report['resources_verified'])
        self.assertTrue(any('ROI outside' in e for e in report['errors']))

    def source(self,path,sha256=None):
        if sha256 is None:sha256=hashlib.sha256((self.root/path).read_bytes()).hexdigest()
        self.amend(lambda s:s.update(source_files=[{'path':path,'sha256':sha256}]))

    def test_declared_source_files_verified_and_reported(self):
        (self.root/'author.txt').write_text('actual native author resource')
        self.source('author.txt')
        report=self.fit()['report']
        self.assertTrue(report['eligible_for_freeze'],report['errors'])
        self.assertTrue(report['source_files']['author.txt']['verified'])
        self.assertEqual(report['source_files']['author.txt']['path'],str((self.root/'author.txt').resolve()))

    def test_stale_source_file_cannot_freeze_even_when_curves_fit(self):
        (self.root/'author.txt').write_text('actual native author resource')
        self.source('author.txt','0'*64)
        result=self.fit();report=result['report']
        self.assertFalse(report['eligible_for_freeze']);self.assertFalse(report['resources_verified'])
        self.assertTrue(all(r['passed'] for r in report['calibration']+report['validation']))
        self.assertTrue(any('stale source_file' in e for e in report['errors']))
        self.assertFalse(report['source_files']['author.txt']['verified'])

    def test_missing_source_file_rejected(self):
        self.source('missing.txt','0'*64)
        report=self.fit()['report'];self.assertFalse(report['resources_verified'])
        self.assertFalse(report['eligible_for_freeze'])

    def test_unsafe_or_invalid_source_declarations_rejected(self):
        for path,sha in [('/absolute/file.txt','0'*64),('https://example.com/file','0'*64),
                         ('C:\\file.txt','0'*64),('bad\x00name','0'*64),('','0'*64),
                         ('reference.png','not-a-hash'),('.', '0'*64)]:
            with self.subTest(path=path):
                self.source(path,sha);report=self.fit()['report']
                self.assertFalse(report['resources_verified']);self.assertFalse(report['eligible_for_freeze'])

    def test_legitimate_declared_parent_source_path_allowed(self):
        # Exact source identity, rather than a blanket ban on relative parents.
        child=self.root/'project';child.mkdir()
        (self.root/'author.txt').write_text('parent author source')
        (child/'reference.png').write_bytes((self.root/'reference.png').read_bytes())
        self.source('../author.txt',hashlib.sha256((self.root/'author.txt').read_bytes()).hexdigest())
        report=ci.fit(self.spec,self.contract,child,iterations=40)['report']
        self.assertTrue(report['resources_verified'],report['errors'])
        self.assertTrue(report['source_files']['../author.txt']['verified'])

    def test_duplicate_source_aliases_and_nonlist_rejected(self):
        sha=hashlib.sha256((self.root/'reference.png').read_bytes()).hexdigest()
        self.amend(lambda s:s.update(source_files=[{'path':'reference.png','sha256':sha},
                                                  {'path':'./reference.png','sha256':sha}]))
        self.assertFalse(self.fit()['report']['eligible_for_freeze'])
        self.amend(lambda s:s.update(source_files={'reference.png':sha}))
        self.assertFalse(self.fit()['report']['resources_verified'])

    def test_complete_bounded_seeds_and_sample_roles(self):
        for mutation in (lambda c:c.update(seeds=[{'width':.4}]),
                         lambda c:c.update(seeds=[{'width':2,'shift':0}]),
                         lambda c:c['curves'][0]['samples'][-1].update(role='calibration')):
            contract=copy.deepcopy(self.contract);mutation(contract)
            with self.assertRaises(ValueError):self.fit(contract=contract)

    def test_cli_new_outputs_and_protection(self):
        (self.root/'spec.json').write_text(json.dumps(self.spec));(self.root/'contract.json').write_text(json.dumps(self.contract))
        script=Path(ci.__file__)
        cmd=[sys.executable,str(script),'--spec',str(self.root/'spec.json'),'--contract',str(self.root/'contract.json'),
             '--out',str(self.root/'candidate.json'),'--report',str(self.root/'report.json'),'--resource-root',str(self.root),'--iterations','30']
        first=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stdout+first.stderr)
        original=(self.root/'candidate.json').read_bytes()
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        self.assertEqual((self.root/'candidate.json').read_bytes(),original)
        cmd[cmd.index('--report')+1]=str(self.root/'spec.json')
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)


if __name__=='__main__':unittest.main()
