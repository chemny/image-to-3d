"""Guard actual sampled mesh continuity, including interpolated cut points."""
import math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from surface_quality import inspect_geometry
import scene_build

def mesh_and_contract(binary=False):
 nx,nz=50,30
 def smooth(t):
  t=max(0,min(1,t));return t*t*t*(t*(t*6-15)+10)
 p=[]
 for j in range(nz+1):
  z=j/nz
  for i in range(nx+1):
   x=-1+2*i/nx;weight=float(.25<z<.75)if binary else smooth(z/.3)*smooth((1-z)/.3)
   p.extend([x,.04*math.exp(-((x-.2)/.3)**2)*weight,z])
 t=[]
 for j in range(nz):
  for i in range(nx):
   a=j*(nx+1)+i;b=a+1;c=a+nx+1;t.extend([a,c,b,b,c,c+1])
 edges={};samples=[]
 for k in range(0,len(t),3):
  tri=t[k:k+3]
  for a,b in zip(tri,tri[1:]+tri[:1]):
   edge=tuple(sorted((a,b)))
   if edge in edges:
    other=edges[edge];samples.append({'id':str(len(samples)),'a':[edge[0]]+[v for v in tri if v!=edge[0]],'b':[edge[0]]+[v for v in other if v!=edge[0]],'max_gap':1e-9,'max_angle_deg':15})
   else:edges[edge]=tri
 return {'type':'mesh','positions':p,'triangles':t},{'version':1,'topology':'open_patch','seam_samples':samples}
class LocalDeformationGuardTests(unittest.TestCase):
 def test_binary_vertex_selection_produces_measurable_normal_cliff(self):
  g,c=mesh_and_contract(True);r=inspect_geometry(g,c);self.assertFalse(r['passed']);self.assertGreater(max(v['angle_deg']for v in r['metrics']['seam_samples']),40)
 def test_continuous_support_preserves_declared_mesh_normal_turn_bound(self):
  g,c=mesh_and_contract();r=inspect_geometry(g,c);self.assertTrue(r['passed'],r['errors']);self.assertLess(max(v['angle_deg']for v in r['metrics']['seam_samples']),15)
 def test_actual_build_gate_rejects_cliff_despite_valid_shading_normals(self):
  g,c=mesh_and_contract(True);g['normals']=[0,1,0]*(len(g['positions'])//3)
  s={'coordinate_system':{'up':'+Y','forward':'+Z'},'parameters':{},'materials':{'m':{'color':'#ffffff'}},'components':[{'id':'host','material':'m','geometry':g,'surface_contract':c}]}
  self.assertRaisesRegex(ValueError,'surface contract failed',scene_build.build,s)
if __name__=='__main__':unittest.main()
