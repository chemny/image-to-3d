import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import scene_assembly as a

class SceneAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.spec={'coordinate_system':{'up':'y','forward':'z'},'parameters':{},'materials':{'m':{'color':'#888888'}},
                   'components':[{'id':name,'parent':None,'role':'body','material':'m','geometry':{'type':'box','size':[1,1,1]},'position':[x,0,0]} for name,x in [('body',0),('door',1)]],
                   'connections':[{'id':'hinge','a':{'component_id':'body','local_point':[.5,0,0]},'b':{'component_id':'door','local_point':[-.5,0,0]},'max_distance':.001}]}
    def test_actual_model_anchor(self):
        self.assertEqual(a.validate(self.spec)['connections'][0]['closed_distance'],0)
    def test_static_without_connections(self):
        del self.spec['connections'];self.assertTrue(a.validate(self.spec)['valid'])
    def test_bad_binding(self):
        self.spec['connections'][0]['a']['component_id']='missing'
        with self.assertRaisesRegex(ValueError,'unknown connection'):a.validate(self.spec)
    def test_actual_transform_misalignment(self):
        self.spec['components'][1]['position'][0]=2
        with self.assertRaisesRegex(ValueError,'exceeds threshold'):a.validate(self.spec)
    def test_threshold_rejected(self):
        for v in (-1,float('inf'),float('nan')):
            self.spec['connections'][0]['max_distance']=v
            with self.assertRaisesRegex(ValueError,'max_distance|nonfinite scalar'):a.validate(self.spec)
    def test_action_requires_connection(self):
        self.spec['actions']=[{'id':'door','component_id':'door','axis':'y','angle':1,'pivot':[.5,0,0]}]
        self.spec['connections']=[]
        with self.assertRaisesRegex(ValueError,'needs declared connection'):a.validate(self.spec)
    def test_action_returns_runtime_requirement(self):
        self.spec['actions']=[{'id':'door','component_id':'door','axis':'y','angle':1,'pivot':[.5,0,0]}]
        self.assertTrue(a.validate(self.spec)['runtime_poses_required'])
    def test_parameter_anchor_follows_model(self):
        self.spec['parameters']={'hinge':{'value':.5,'min':0,'max':2}}
        self.spec['components'][0]['position']=[{'param':'hinge'},0,0]
        self.spec['components'][1]['position']=[0,0,0]
        self.spec['connections'][0]['a']['local_point']=[0,0,0]
        self.spec['connections'][0]['b']['local_point']=[{'param':'hinge'},0,0]
        self.assertEqual(a.validate(self.spec)['connections'][0]['closed_distance'],0)
        self.spec['parameters']['hinge']['value']=1.2
        self.assertEqual(a.validate(self.spec)['connections'][0]['b']['local_point'],[1.2,0,0])
        self.assertEqual(a.validate(self.spec)['connections'][0]['closed_distance'],0)

    def test_anchor_parameter_bounds_rejected(self):
        self.spec['parameters']={'hinge':{'value':3,'min':0,'max':2}}
        self.spec['connections'][0]['a']['local_point']=[{'param':'hinge'},0,0]
        with self.assertRaises(ValueError):a.validate(self.spec)

    def test_invalid_pose(self):
        self.spec['connections'][0]['poses']=['invented']
        with self.assertRaisesRegex(ValueError,'poses'):a.validate(self.spec)

if __name__=='__main__':unittest.main()
