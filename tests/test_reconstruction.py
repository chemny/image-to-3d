import copy
import math
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import reconstruction as r

class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.camera={'type':'orthographic','width':100,'height':100,'position':[0,0,5],'target':[0,0,0],'up':[0,1,0],'ortho_height':10}
        self.spec={'coordinate_system':{'up':'y','forward':'z','unit':'m'},
                   'parameters':{'x':{'value':0,'min':-2,'max':2}},
                   'materials':{'paint':{'color':'#aaaaaa','roughness':.5,'metalness':0}},
                   'components':[{'id':'body','parent':None,'role':'body','material':'paint','position':[{'param':'x'},0,0], 'geometry':{'type':'box','size':[1,1,1]}}],
                   'cameras':{'front':self.camera},
                   'observations':[{'id':'o','reference_id':'ref','feature':'center','component_id':'body','local_point':[0,0,0],'camera_id':'front','target':[60,50],'role':'calibration','sigma_px':1,'parameter_ids':['x']}]}
    def test_orthographic_projection(self):
        self.assertEqual(r.project([1,1,0],self.camera),[60,40])
    def test_perspective_projection(self):
        cam=dict(self.camera,type='perspective',fov_y_deg=90)
        self.assertAlmostEqual(r.project([1,1,0],cam)[0],60)
        self.assertAlmostEqual(r.project([1,1,0],cam)[1],40)
    def test_invalid_depth(self):
        with self.assertRaisesRegex(ValueError,'behind camera'):r.project([0,0,6],self.camera)
    def test_actual_model_transform_drives_prediction(self):
        self.spec['parameters']['x']['value']=1
        self.assertEqual(r.predictions(self.spec)['o']['predicted'],[60,50])
    def test_fit_model_position(self):
        report=r.fit(self.spec,['x'],20)
        self.assertLess(report['final_objective'],1e-6)
        self.assertAlmostEqual(report['spec']['parameters']['x']['value'],1)
        self.assertEqual(self.spec['parameters']['x']['value'],0)
    def test_fit_camera_parameter(self):
        self.spec['components'][0]['position']=[0,0,0]
        self.spec['cameras']['front']['position']=[{'param':'x'},0,5]
        self.spec['cameras']['front']['target']=[{'param':'x'},0,0]
        report=r.fit(self.spec,['x'],20)
        self.assertAlmostEqual(report['spec']['parameters']['x']['value'],-1)
    def test_validation_targets_do_not_select_fit(self):
        a=r.fit(self.spec,['x'],15)
        obs=dict(self.spec['observations'][0],id='held',role='validation',target=[0,0])
        self.spec['observations'].append(obs)
        b=r.fit(self.spec,['x'],15)
        self.assertEqual(a['spec']['parameters'],b['spec']['parameters'])
        self.assertEqual(a['journal'],b['journal'])
    def test_validation_cannot_be_protected(self):
        self.spec['observations'].append(dict(self.spec['observations'][0],id='held',role='validation',protected=True))
        with self.assertRaisesRegex(ValueError,'validation cannot'):r.fit(self.spec,['x'])
    def test_protected_feature_blocks_regression(self):
        self.spec['observations'].append(dict(self.spec['observations'][0],id='protected',target=[50,50],protected=True,protection_tolerance_px=0))
        report=r.fit(self.spec,['x'],15)
        self.assertEqual(report['spec']['parameters']['x']['value'],0)
        self.assertTrue(any(j.get('reason')=='protected landmark regression' for j in report['journal']))
    def test_bounds_respected(self):
        self.spec['parameters']['x']['max']=.5
        report=r.fit(self.spec,['x'],20)
        self.assertLessEqual(report['spec']['parameters']['x']['value'],.5)
        self.assertGreater(report['final_objective'],1)
    def test_degeneracy_and_unobserved_report(self):
        self.spec['parameters']['unused']={'value':0,'min':-1,'max':1}
        report=r.analyze(self.spec)
        self.assertEqual(report['unobserved_parameters'],['unused'])
        self.assertIn('unused',report['insensitive_parameters'])
        self.assertTrue(report['rank_deficient'])
    def test_unknown_geometry_rejected(self):
        self.spec['components'][0]['geometry']['type']='invented'
        with self.assertRaises(ValueError):r.predictions(self.spec)
    def test_invalid_geometry_candidates_rejected_and_logged(self):
        self.spec['parameters']['x']={'value':.5,'min':-1,'max':1}
        self.spec['components'][0]['geometry']['size']=[{'param':'x'},1,1]
        self.spec['observations'][0]['target']=[40,50]
        result=r.fit(self.spec,['x'],15)
        self.assertGreater(result['spec']['parameters']['x']['value'],0)
        self.assertTrue(any('reason' in row for row in result['journal']))

    def test_missing_target_never_synthesized(self):
        del self.spec['observations'][0]['target']
        with self.assertRaisesRegex(ValueError,'pixel target'):r.fit(self.spec,['x'])
    def test_parent_transform_applies(self):
        parent=copy.deepcopy(self.spec['components'][0]);parent.update(id='parent',position=[1,0,0])
        self.spec['components'][0]['parent']='parent';self.spec['components'].append(parent)
        self.assertEqual(r.predictions(self.spec)['o']['predicted'],[60,50])

if __name__=='__main__':unittest.main()
