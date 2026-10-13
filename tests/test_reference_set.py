"""Synthetic fixtures test gate mechanics, never certify actual image semantics."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import project
import workflow
import reference_set as gate

class ReferenceSetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);Image.new('RGB',(32,24),'yellow').save(self.base/'input.png')
        self.root=self.base/'task';project.init(self.base/'input.png','generic',self.root)
        self.path=self.root/'spec.json';self.spec=project.read(self.path)
        self.spec['references'][0]['approved']=True
        self.plan=gate.template();self.plan.update(status='ready',strategy='reuse',reuse_reason='Synthetic unit test fixture only')
        self.plan['required_views']=[{'id':'front','reference_ids':['original']}]
        self.plan['critical_components']=[{'id':'body','coverage':{k:['original'] for k in ('outline','volume','connection')},'component_ids':['body'],'observation_ids':['center'],'uncertainties':['Back is inferred']}]
        self.plan['sources']=[{'reference_id':'original','source_identity':'synthetic unit-test input identity','purpose':'gate fixture','parent_reference_ids':[],'view':{'orientation':'front','projection':'estimated'}}]
        (self.root/'review.txt').write_text('Synthetic review fixture; no real reference judged.')
        self.spec['source_files'].append({'path':'review.txt','sha256':project.sha(self.root/'review.txt')})
        self.plan['consistency_review']={'verdict':'pass','method':'visual','reviewer':'test fixture','rationale':'Synthetic gate test','reference_hashes':{'original':self.spec['references'][0]['sha256']},'artifacts':[{'path':'review.txt','sha256':project.sha(self.root/'review.txt')}]}
        self.save()
    def save(self):
        project.save(self.root/'reference-plan.json',self.plan)
        for r in self.spec['source_files']:
            if r['path']=='reference-plan.json':r['sha256']=project.sha(self.root/r['path'])
        project.save(self.path,self.spec)
    def test_positive_reference_coverage(self):self.assertTrue(gate.validate(self.path)['passed'])
    def test_pending_does_not_break_intake(self):
        self.plan['status']='pending';self.save()
        self.assertTrue(gate.validate(self.path,'intake')['passed'])
        self.assertFalse(workflow.status(self.root/'state.json')['blocked'])
        with self.assertRaisesRegex(ValueError,'pending'):gate.validate(self.path)
    def test_generate_requires_supplement(self):
        self.plan['strategy']='generate';self.save()
        with self.assertRaisesRegex(ValueError,'supplemental'):gate.validate(self.path)
    def test_wrong_component_binding(self):
        self.spec['components']=[{'id':'body'},{'id':'other'}];self.spec['observations']=[{'id':'center','reference_id':'original','component_id':'other'}];self.save()
        with self.assertRaisesRegex(ValueError,'covered component'):gate.validate(self.path,'spec')
    def test_workflow_enforces_pending_reference_stage(self):
        self.plan['status']='pending';self.save()
        with self.assertRaisesRegex(ValueError,'reference plan pending'):
            workflow.validate_evidence(self.path,self.root/'nonexistent.json','references')
    def test_missing_view(self):
        self.plan['required_views'][0]['reference_ids']=[];self.save()
        with self.assertRaisesRegex(ValueError,'coverage'):gate.validate(self.path)
    def test_missing_volume(self):
        del self.plan['critical_components'][0]['coverage']['volume'];self.save()
        with self.assertRaisesRegex(ValueError,'coverage'):gate.validate(self.path)
    def test_dimensions(self):
        self.spec['references'][0]['image_size']=[1,1];self.save()
        with self.assertRaisesRegex(ValueError,'dimensions'):gate.validate(self.path)
    def test_stale_resource(self):
        Image.new('RGB',(32,24),'red').save(self.root/self.spec['references'][0]['path'])
        with self.assertRaisesRegex(ValueError,'stale'):gate.validate(self.path)
    def test_stale_plan(self):
        with (self.root/'reference-plan.json').open('a') as f:f.write(' ')
        with self.assertRaisesRegex(ValueError,'source-hashed'):gate.validate(self.path)
    def test_plan_change_changes_reuse_fingerprint(self):
        old=workflow.reference_fingerprint(self.spec);self.plan['reuse_reason']='changed scope';self.save()
        self.assertNotEqual(old,workflow.reference_fingerprint(self.spec))
    def test_policy_pinned(self):
        del self.spec['quality_contract']['reference_standard'];self.save()
        self.assertIn('reference policy',workflow.status(self.root/'state.json')['issues'][0])
    def test_legacy_compatible_not_certified(self):
        del self.spec['quality_contract']['reference_standard'];self.save()
        self.assertFalse(gate.validate(self.path)['certified'])
    def test_visual_artifact_stale(self):
        (self.root/'review.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError,'source-hashed'):gate.validate(self.path)
    def test_conflict(self):
        self.plan['unresolved_conflicts']=['inconsistent crest'];self.save()
        with self.assertRaisesRegex(ValueError,'conflicts'):gate.validate(self.path)
    def test_spec_bindings(self):
        with self.assertRaisesRegex(ValueError,'component'):gate.validate(self.path,'spec')
        self.spec['components']=[{'id':'body'}];self.spec['observations']=[{'id':'center','reference_id':'original','component_id':'body'}];self.save()
        self.assertTrue(gate.validate(self.path,'spec')['passed'])
    def manual_fixture(self):
        self.spec['components']=[{'id':'body'}]
        part=self.plan['critical_components'][0];part['observation_ids']=[]
        part['manual_constraints']=[{'kind':'silhouette','component_id':'body','reference_ids':['original'],'uncertainty':'View-dependent silhouette, no fixed 3D correspondence','rationale':'Review matching camera outline','artifact':{'path':'review.txt','sha256':project.sha(self.root/'review.txt')}}]
        self.save();return part['manual_constraints'][0]
    def test_manual_constraint_is_explicit_review_not_certification(self):
        self.manual_fixture();result=gate.validate(self.path,'spec')
        self.assertEqual(result['manual_constraints'],1);self.assertTrue(result['manual_review_required']);self.assertFalse(result['certified'])
    def test_manual_unbound_rejected(self):
        c=self.manual_fixture();c['component_id']='missing';self.save()
        with self.assertRaisesRegex(ValueError,'covered component'):gate.validate(self.path,'spec')
    def test_manual_stale_artifact_rejected(self):
        c=self.manual_fixture();c['artifact']['sha256']='stale';self.save()
        with self.assertRaisesRegex(ValueError,'source-hashed'):gate.validate(self.path,'spec')
    def test_manual_unknown_reference_rejected(self):
        c=self.manual_fixture();c['reference_ids']=['missing'];self.save()
        with self.assertRaisesRegex(ValueError,'coverage'):gate.validate(self.path,'spec')
    def test_manual_does_not_hide_invalid_observations(self):
        self.manual_fixture();self.plan['critical_components'][0]['observation_ids']=['fake'];self.save()
        with self.assertRaisesRegex(ValueError,'observation IDs'):gate.validate(self.path,'spec')
    def test_missing_both_constraint_types_rejected(self):
        self.manual_fixture();self.plan['critical_components'][0]['manual_constraints']=[];self.save()
        with self.assertRaisesRegex(ValueError,'explicit manual'):gate.validate(self.path,'spec')
    def test_export_relocates_manual_artifact_and_preserves_policies(self):
        from test_project import fixture
        from unittest.mock import patch
        task=fixture(self.base/'export-case');spec=project.read(task/'spec.json')
        spec['references'][0].update(origin='original',approved=True)
        analysis=project.read(task/'analysis.json');analysis['references'][0]['origin']='original';project.save(task/'analysis.json',analysis)
        (task/'manual.txt').write_text('Synthetic outline review artifact for exporter test only')
        spec['source_files'].append({'path':'manual.txt','sha256':project.sha(task/'manual.txt')})
        plan=copy.deepcopy(self.plan)
        plan['critical_components'][0].update(observation_ids=[],manual_constraints=[{'kind':'silhouette','component_id':'body','reference_ids':['original'],'uncertainty':'Synthetic view-dependent outline','rationale':'Exporter fixture','artifact':{'path':'manual.txt','sha256':project.sha(task/'manual.txt')}}])
        plan['consistency_review'].update(reference_hashes={'original':spec['references'][0]['sha256']},artifacts=[{'path':'manual.txt','sha256':project.sha(task/'manual.txt')}])
        project.save(task/'reference-plan.json',plan);project.save(task/'spec.json',spec);project.refresh(task)
        self.assertTrue(gate.validate(task/'spec.json','spec')['manual_review_required'])
        bundle=self.base/'export-bundle';project.build_project(task,bundle,True)
        manifest=project.read(bundle/'bundle-manifest.json');manifest['diagnostic']=False;project.save(bundle/'bundle-manifest.json',manifest)
        # Tests relocation mechanics only; this mock is never a real acceptance.
        destination=self.base/'exported'
        with patch.object(workflow,'status',return_value={'blocked':False,'next':None}):project.export(task,bundle,destination)
        rebuilt=destination/'rebuild'
        result=gate.validate(rebuilt/'spec.json','spec');self.assertEqual(result['manual_constraints'],1)
        meta=project.read(rebuilt/'project.json');self.assertEqual(meta['reference_standard'],1);self.assertEqual(meta['production_standard'],1)
        current=project.next_step(rebuilt);self.assertTrue(current['reference_standard']['required']);self.assertTrue(current['production_standard']['required'])
    def test_generated_approval_identity(self):
        r=copy.deepcopy(self.spec['references'][0]);r.update(id='back',origin='generated',path='references/back.png',source_reference_ids=['original'])
        Image.new('RGB',(32,24),'orange').save(self.root/r['path']);r['sha256']=project.sha(self.root/r['path']);self.spec['references'].append(r)
        s=copy.deepcopy(self.plan['sources'][0]);s.update(reference_id='back',parent_reference_ids=['original']);self.plan['sources'].append(s)
        self.plan['consistency_review']['reference_hashes']['back']=r['sha256'];self.save()
        with self.assertRaisesRegex(ValueError,'user approval'):gate.validate(self.path)
        s['approval']={'actor':'user','decision':'approved','reference_sha256':r['sha256'],'evidence':{'path':'review.txt','sha256':project.sha(self.root/'review.txt')}};self.save()
        self.assertTrue(gate.validate(self.path)['passed'])
        s['approval']['reference_sha256']='wrong';self.save()
        with self.assertRaisesRegex(ValueError,'user approval'):gate.validate(self.path)

if __name__=='__main__':unittest.main()
