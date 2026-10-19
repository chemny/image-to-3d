import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import surface_attachment as sa
class SurfaceTests(unittest.TestCase):
 def spec(self):return {'schema_version':1,'coordinate_system':{'up':'y','forward':'z','unit':'m'},'parameters':{},'materials':{'m':{'color':'#ffffff'}},'components':[{'id':'host','material':'m','geometry':{'type':'mesh','positions':[-1,-1,0,1,-1,0,1,1,0,-1,1,0],'triangles':[0,1,2,0,2,3]}},{'id':'part','material':'m','geometry':{'type':'mesh','positions':[-.1,-.1,.01,.1,-.1,.01,0,.1,.01],'triangles':[0,1,2]}}]}
 def gap(self):return {'id':'gap','kind':'surface_gap','component_ids':['part'],'host_component_ids':['host'],'min':0,'max':.02,'samples':12,'side':'outside'}
 def ray(self):return {'id':'hole','kind':'opening_clearance','anchors':[{'component_id':'part','vertex_index':2}],'host_component_ids':['host'],'direction':[0,0,-1],'clearance':.1}
 def test_attached_and_floating(self):
  s=self.spec();self.assertTrue(sa.evaluate(s,[self.gap()])['passed']);s['components'][1]['position']=[0,0,.2];self.assertFalse(sa.evaluate(s,[self.gap()])['passed'])
 def test_signed_penetration(self):
  s=self.spec();s['components'][1]['position']=[0,0,-.02];self.assertFalse(sa.evaluate(s,[self.gap()])['passed'])
 def test_parent_transform(self):
  s=self.spec();s['components']+=[{'id':'parent','kind':'assembly','position':[0,0,.5]}];s['components'][1]['parent']='parent';self.assertFalse(sa.evaluate(s,[self.gap()])['passed'])
 def test_real_opening_vs_black_overlay(self):
  s=self.spec();self.assertFalse(sa.evaluate(s,[self.ray()])['passed']);g=s['components'][0]['geometry'];cut=sa.cut_projected_opening(g['positions'],g['triangles'],[[-.2,-.2],[.2,-.2],[.2,.2],[-.2,.2]]);g.update({k:cut[k]for k in ['positions','triangles']});self.assertTrue(sa.evaluate(s,[self.ray()])['passed'])
 def test_cut_conserves_expected_area(self):
  s=self.spec()['components'][0]['geometry'];g=sa.cut_projected_opening(s['positions'],s['triangles'],[[-.5,-.5],[.5,-.5],[.5,.5],[-.5,.5]]);import numpy as np;p=np.array(g['positions']).reshape(-1,3);t=p[np.array(g['triangles']).reshape(-1,3)];area=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1).sum()/2;self.assertAlmostEqual(area,3,places=8)
 def test_bad_polygon_and_limits_rejected(self):
  g=self.spec()['components'][0]['geometry'];self.assertRaises(ValueError,sa.cut_projected_opening,g['positions'],g['triangles'],[[0,0],[1,0],[.2,.2],[1,1],[0,1]]);c=self.gap();c['max']=-1;self.assertRaises(ValueError,sa.evaluate,self.spec(),[c])
if __name__=='__main__':unittest.main()
