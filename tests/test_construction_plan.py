import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import construction_plan as cp
from PIL import Image

class ConstructionPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name)
        Image.new('RGB',(100,100)).save(self.d/'ref.png')
        self.spec={'components':[{'id':'part','geometry':{'type':'box'}},{'id':'fixed','geometry':{'type':'box'}}], 'references':[{'id':'ref','path':'ref.png','sha256':cp.file_hash(self.d/'ref.png'),'image_size':[100,100]}], 'cameras':[{'id':'front'},{'id':'side'}], 'materials':[], 'parameters':[], 'observations':[]}
        recipe={'version':1,'component_id':'part','source':{'reference_id':'ref','roi':[0,0,100,100]},'rationale':'tapered solid','method':'loft','parameters':{'sections':[{'center':[0,0,0],'radii':[1,1]},{'center':[0,1,0],'radii':[0.5,0.5]}],'radial_segments':16}}
        self.spec.update(schema_version=1,id='fixture',domain='generic',coordinate_system={'unit':'m','up':'Y','forward':'Z'},source_files=[],parameters={},checks=[],quality_contract={'scope':'synthetic-software-test','limits':{}})
        self.spec['references'][0].update(origin='synthetic',approved=False)
        for c in self.spec['components']: c.update(role='part',material='fixture')
        self.plan={'version':1,'protected_components':['fixed'],'protected_views':['front','side'],'parts':[{'id':'shape','component_id':'part','recipe':recipe,'outline':'taper','thickness':'round','root':'flat base','method_rationale':'section controlled','parameter_links':[{'feature':'root thickness','parameter_path':['sections',0,'radii',0]}],'local_checks':[{'view':v,'aspects':['outline','volume','connection'],'status':'pending'} for v in ['front','side']]}]}
    def write(self):
        (self.d/'spec.json').write_text(json.dumps(self.spec)); (self.d/'plan.json').write_text(json.dumps(self.plan))
    def apply(self):
        self.write(); return cp.apply(self.d/'spec.json',self.d/'plan.json',self.d/'candidate.json')
    def mutate(self,fn):
        p=self.d/'candidate.json'; s=json.loads(p.read_text()); fn(s); p.write_text(json.dumps(s)); return cp.validate(p)
    def test_apply_and_pending_body(self):
        self.assertTrue(self.apply()['ok']); self.assertFalse(cp.validate(self.d/'candidate.json','body')['ok'])
    def test_stale_geometry(self):
        self.apply(); self.assertFalse(self.mutate(lambda s:s['components'][0]['geometry']['positions'].__setitem__(0,12))['ok'])
    def test_protected_component(self):
        self.apply(); self.assertFalse(self.mutate(lambda s:s['components'][1].update(position=[1,0,0]))['ok'])
    def test_protected_camera(self):
        self.apply(); self.assertFalse(self.mutate(lambda s:s['cameras'][0].update(zoom=2))['ok'])
    def test_recipe_tampering(self):
        self.apply(); p=self.d/'candidate.construction-plan.json'; v=json.loads(p.read_text()); v['parts'][0]['recipe']['parameters']['sections'][0]['radii'][0]=2; p.write_text(json.dumps(v)); self.assertFalse(cp.validate(self.d/'candidate.json')['ok'])
    def test_wrong_reference(self):
        self.plan['parts'][0]['recipe']['source']['reference_id']='unknown'; self.assertRaises(ValueError,self.apply)
    def test_wrong_roi(self):
        self.plan['parts'][0]['recipe']['source']['roi']=[99,0,2,3]; self.assertRaises(ValueError,self.apply)
    def test_duplicate_part(self):
        self.plan['parts'].append(copy.deepcopy(self.plan['parts'][0])); self.assertRaises(ValueError,self.apply)
    def test_fake_parameter(self):
        self.plan['parts'][0]['parameter_links'][0]['parameter_path']=['missing']; self.assertRaises(ValueError,self.apply)
    def test_no_silent_observation_reuse(self):
        self.spec['observations']=[{'id':'point','component_id':'part','binding':{'vertex_index':0}}]; self.assertRaises(ValueError,self.apply)
    def test_explicit_invalidation(self):
        self.spec['observations']=[{'id':'point','component_id':'part','binding':{'vertex_index':0}}]; self.plan['invalidated_observation_ids']=['point']; self.assertTrue(self.apply()['ok']); self.assertEqual(json.loads((self.d/'candidate.json').read_text())['observations'],[])
    def test_no_overwrite(self):
        self.apply(); self.assertRaises(ValueError,cp.apply,self.d/'spec.json',self.d/'plan.json',self.d/'candidate.json')
    def test_pass_evidence_identity(self):
        for check in self.plan['parts'][0]['local_checks']:
            check.update(status='pass',reviewer='fixture reviewer',notes='software fixture only',evidence={'path':'ref.png','sha256':cp.file_hash(self.d/'ref.png'),'geometry_sha256':cp.digest(cp.compile_geometry(self.plan['parts'][0]['recipe'])),'camera_sha256':cp.digest(next(c for c in self.spec['cameras'] if c['id']==check['view']))})
        self.assertTrue(self.apply()['ok']); self.assertTrue(cp.validate(self.d/'candidate.json','body')['ok'])
        self.assertFalse(cp.validate(self.d/'candidate.json','body')['visual_certified'])
    def test_workflow_hook(self):
        import workflow
        self.apply(); workflow.validate_spec(self.d/'candidate.json')
        self.mutate(lambda s:s['components'][0]['geometry']['positions'].__setitem__(0,12))
        with self.assertRaisesRegex(ValueError,'construction plan'):
            workflow.validate_spec(self.d/'candidate.json')
    def test_relocated_plan(self):
        import shutil
        self.apply(); out=self.d/'relocated'; out.mkdir()
        spec=json.loads((self.d/'candidate.json').read_text())
        mapping={}
        for i,item in enumerate(spec['references']+spec['source_files']):
            old=item['path']; new=f'{i}-'+Path(old).name; shutil.copy(self.d/old,out/new); mapping[old]=new; item['path']=new
        spec['construction_plan']=mapping[spec['construction_plan']]
        spec['construction_receipt']['baseline']['path']=mapping[spec['construction_receipt']['baseline']['path']]
        (out/'spec.json').write_text(json.dumps(spec))
        self.assertTrue(cp.validate(out/'spec.json')['ok'])
    def test_required_visual_check_cannot_disappear(self):
        self.apply(); self.assertFalse(self.mutate(lambda s:s.update(checks=[]))['ok'])
    def test_missing_plan_source_registration(self):
        self.apply(); self.assertFalse(self.mutate(lambda s:s.update(source_files=[]))['ok'])
    def test_declared_image_dimensions(self):
        self.spec['references'][0]['image_size']=[200,200]
        self.assertRaises(ValueError,self.apply)
    def test_canonical_camera_dict(self):
        self.spec['cameras']={c['id']:{'position':[0,0,3]} for c in self.spec['cameras']}
        self.assertTrue(self.apply()['ok'])
    def test_recipe_transform(self):
        self.plan['parts'][0]['transform']={'position':[1,2,3],'rotation':[0,0,0.2],'scale':[1,2,1]}
        self.assertTrue(self.apply()['ok'])
        s=json.loads((self.d/'candidate.json').read_text());self.assertEqual(s['components'][0]['position'],[1,2,3])
        self.assertFalse(self.mutate(lambda s:s['components'][0].update(position=[0,0,0]))['ok'])
    def test_transform_reject_negative_scale(self):
        self.plan['parts'][0]['transform']={'scale':[-1,1,1]}; self.assertRaises(ValueError,self.apply)
    def test_material_relocation_preserves_identity(self):
        self.spec['materials']={'a':{'color':'#fff','maps':{'baseColor':{'path':'ref.png','sha256':cp.file_hash(self.d/'ref.png')}}}}
        self.apply()
        (self.d/'relocated-ref.png').write_bytes((self.d/'ref.png').read_bytes())
        self.assertTrue(self.mutate(lambda s:s['materials']['a']['maps']['baseColor'].update(path='relocated-ref.png'))['ok'])
        self.assertFalse(self.mutate(lambda s:s['materials']['a']['maps']['baseColor'].update(sha256='changed'))['ok'])
    def test_stale_compiler(self):
        self.apply(); self.assertFalse(self.mutate(lambda s:s['construction_receipt'].update(compiler_sha256='fake'))['ok'])

if __name__=='__main__': unittest.main()
