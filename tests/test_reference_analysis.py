import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import reference_analysis as r

class ReferenceAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.spec={'references':[{'id':'a','origin':'original','image_size':[100,100]}],
                   'components':[{'id':'body'}], 'parameters':{'width':{},'unused':{}},
                   'observations':[{'id':'one','reference_id':'a','component_id':'body','feature':'edge','parameter_ids':['width'],
                                    'local_point':[0,0,0],'roi':[10,10,30,30],'target':[20,20],'role':'calibration'}],
                   'feature_inventory':[{'reference_id':'a','component_id':'body','feature':'edge','visibility':'visible','required':True}]}
    def test_valid_reports_unobserved(self):
        self.assertEqual(r.validate(self.spec)['unobserved_parameters'],['unused'])
        self.assertFalse(r.validate(self.spec)['visual_pass'])
    def test_missing_feature_rejected(self):
        self.spec['feature_inventory'].append({'reference_id':'a','component_id':'body','feature':'wheel','visibility':'visible','required':True})
        with self.assertRaisesRegex(ValueError,'no observation'):r.validate(self.spec)
    def test_generated_requires_provenance(self):
        self.spec['references'].append({'id':'b','origin':'generated','image_size':[100,100]})
        with self.assertRaisesRegex(ValueError,'source IDs'):r.validate(self.spec)
    def test_generated_preserves_identity(self):
        self.spec['references'].append({'id':'b','origin':'generated','image_size':[100,100],'source_reference_ids':['a'],'provenance':'approved design hypothesis'})
        r.validate(self.spec)
    def test_hidden_needs_inference(self):
        self.spec['feature_inventory'].append({'reference_id':'a','component_id':'body','feature':'back','visibility':'hidden','required':True})
        with self.assertRaisesRegex(ValueError,'explicit inference'):r.validate(self.spec)
        self.spec['inferences']=[{'reference_id':'a','component_id':'body','feature':'back','rationale':'symmetry hypothesis','confidence':.3}]
        self.assertEqual(r.validate(self.spec)['inferred_features'],1)
    def test_roi_target_mismatch(self):
        self.spec['observations'][0]['target']=[90,90]
        with self.assertRaisesRegex(ValueError,'outside ROI'):r.validate(self.spec)
    def test_unknown_component(self):
        self.spec['observations'][0]['component_id']='missing'
        with self.assertRaisesRegex(ValueError,'unknown observation'):r.validate(self.spec)
    def test_missing_binding(self):
        del self.spec['observations'][0]['local_point']
        with self.assertRaisesRegex(ValueError,'landmark binding'):r.validate(self.spec)
    def test_separate_analysis_cannot_relabel_generated_as_original(self):
        analysis={'references':[{'id':'a','origin':'generated'}]}
        with self.assertRaisesRegex(ValueError,'reference identity'):r.validate(analysis,self.spec)
    def test_separate_analysis_api(self):
        self.assertTrue(r.validate({'feature_inventory':self.spec['feature_inventory']},self.spec)['valid'])
    def test_analysis_cannot_replace_fitting_observations(self):
        changed=copy.deepcopy(self.spec['observations']); changed[0]['target']=[25,25]
        with self.assertRaisesRegex(ValueError,'match model spec exactly'):
            r.validate({'observations':changed},self.spec)

    def test_synthetic_is_unapproved_test_fixture_only(self):
        self.spec['references'][0].update(origin='synthetic',approved=False,provenance='software fixture generated from known geometry')
        with self.assertRaisesRegex(ValueError,'test-only scope'):r.validate(self.spec)
        self.spec['quality_contract']={'scope':'synthetic-software-test'}
        self.assertTrue(r.validate(self.spec)['valid'])
        self.spec['references'][0]['approved']=True
        with self.assertRaisesRegex(ValueError,'no approval'):r.validate(self.spec)

    def test_synthetic_requires_provenance(self):
        self.spec['references'][0].update(origin='synthetic',approved=False)
        self.spec['quality_contract']={'scope':'synthetic-software-test'}
        with self.assertRaisesRegex(ValueError,'fixture provenance'):r.validate(self.spec)

    def test_reference_cycle(self):
        self.spec['references'][0].update(origin='derived',source_reference_ids=['b'],provenance='crop')
        self.spec['references'].append({'id':'b','origin':'generated','image_size':[100,100],'source_reference_ids':['a'],'provenance':'generated'})
        with self.assertRaisesRegex(ValueError,'cycle'):r.validate(self.spec)

if __name__=='__main__':unittest.main()
