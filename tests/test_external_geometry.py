"""Replay provenance/control tests, not evidence of photographic fidelity."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import external_geometry as e,shape_foundation as f
from test_shape_foundation import fixture

SOURCE='''import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--out');a=p.parse_args()
r=json.loads(Path(a.input).read_text());g=json.loads(Path(r['inputs'][0]).read_text())
g['positions'][4]=r['parameters']['depth']
Path(a.out).write_text(json.dumps({'version':1,'geometries':{'shell':g}}))
'''
class ReplayTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.s=fixture();self.s['parameters']['depth']={'value':.2,'min':.1,'max':.5}
  g={'type':'mesh','positions':[0,0,0,1,.2,0,1,0,1,0,0,1],'triangles':[0,1,2,0,2,3]}
  self.s['components'][0]['geometry']=g;self.s['observations']=[]
  self.s['foundation']['controls']=[{'id':kind,'kind':kind,'bindings':[{'component_id':'shell','vertex_index':i}for i in range(4)],'reference_ids':['original'],'parameter_ids':['depth'],'rationale':'Synthetic actual surface test'}for kind in ('curve','section')]
  self.write_source(SOURCE);(self.root/'input.json').write_text(json.dumps(g))
  self.s['external_geometry']={'version':1,'component_ids':['shell'],'generator':{'path':'generator.py','sha256':e.sha(self.root/'generator.py')},'inputs':[{'path':'input.json','sha256':e.sha(self.root/'input.json')}],'parameter_components':{'depth':['shell']},'position_tolerance':1e-7,'receipt':'receipt.json'}
  self.s['source_files']=[copy.deepcopy(self.s['external_geometry'][k])for k in ('generator',)]+copy.deepcopy(self.s['external_geometry']['inputs']);self.save()
 def write_source(self,text):
  (self.root/'generator.py').write_text(text)
  if hasattr(self,'s')and self.s.get('external_geometry'):
   self.s['external_geometry']['generator']['sha256']=e.sha(self.root/'generator.py')
   self.s['source_files'][0]['sha256']=e.sha(self.root/'generator.py');self.save()
 def save(self):(self.root/'spec.json').write_text(json.dumps(self.s))
 def accept(self):
  r=e.replay(self.root/'spec.json',True);self.s['source_files'].append({'path':'receipt.json','sha256':e.sha(self.root/'receipt.json')});self.save();return r
 def test_positive_replay_and_foundation(self):
  r=self.accept();self.assertTrue(r['passed']);self.assertEqual(r['parameter_influence'],{'depth':['shell']});self.assertEqual(e.readiness(self.s,self.root),{'shell'});self.assertTrue(f.evaluate(self.s,self.root)['construction_ready']);self.assertFalse(f.evaluate(self.s,self.root)['visual_pass'])
 def test_no_implicit_execution(self):
  with patch.object(e.subprocess,'run',side_effect=AssertionError('must not execute')):
   with self.assertRaisesRegex(ValueError,'allow-execution'):e.replay(self.root/'spec.json')
   self.assertFalse(f.evaluate(self.s,self.root)['construction_ready'])
 def test_readiness_never_executes(self):
  self.accept()
  with patch.object(e.subprocess,'run',side_effect=AssertionError('must not execute')):self.assertTrue(f.evaluate(self.s,self.root)['construction_ready'])
 def test_missing_root_fails_closed(self):self.accept();self.assertFalse(f.evaluate(self.s)['construction_ready'])
 def test_changed_source_rejected(self):
  self.accept();(self.root/'generator.py').write_text(SOURCE+'\n# new')
  with self.assertRaisesRegex(ValueError,'stale'):e.readiness(self.s,self.root)
 def test_changed_input_rejected(self):
  self.accept();(self.root/'input.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'stale'):e.readiness(self.s,self.root)
 def test_changed_geometry_rejected(self):
  self.accept();self.s['components'][0]['geometry']['positions'][4]=.3
  with self.assertRaisesRegex(ValueError,'changed'):e.readiness(self.s,self.root)
 def test_changed_parameter_rejected(self):
  self.accept();self.s['parameters']['depth']['value']=.3
  with self.assertRaisesRegex(ValueError,'changed'):e.readiness(self.s,self.root)
 def test_wrong_compiled_geometry_rejected(self):
  self.s['components'][0]['geometry']['positions'][4]=.3;self.save()
  with self.assertRaisesRegex(ValueError,'differs'):e.replay(self.root/'spec.json',True)
 def test_dead_parameter_rejected(self):
  self.write_source(SOURCE.replace("r['parameters']['depth']",'.2'))
  with self.assertRaisesRegex(ValueError,'no effect'):e.replay(self.root/'spec.json',True)
 def test_nondeterminism_rejected(self):
  self.write_source(SOURCE.replace("r['parameters']['depth']","__import__('random').random()"))
  with self.assertRaisesRegex(ValueError,'nondeterministic'):e.replay(self.root/'spec.json',True)
 def test_mutated_input_rejected(self):
  self.write_source(SOURCE+"\nPath(r['inputs'][0]).write_text('{}')")
  with self.assertRaisesRegex(ValueError,'mutated'):e.replay(self.root/'spec.json',True)
 def test_nonfinite_output_rejected(self):
  self.write_source(SOURCE.replace("r['parameters']['depth']","float('nan')"))
  with self.assertRaisesRegex(ValueError,'nonfinite'):e.replay(self.root/'spec.json',True)
 def test_nonfinite_parameter_rejected(self):
  self.s['parameters']['depth']['max']=float('inf')
  with self.assertRaisesRegex(ValueError,'finite'):e.contract(self.s,self.root)
 def test_precision_ceiling(self):
  self.s['external_geometry']['position_tolerance']=.01
  with self.assertRaisesRegex(ValueError,'precision'):e.contract(self.s,self.root)
 def test_path_escape_rejected(self):
  self.s['external_geometry']['inputs'][0]['path']='../escape.json'
  with self.assertRaisesRegex(ValueError,'inside'):e.contract(self.s,self.root)
 def test_receipt_hash_required(self):
  e.replay(self.root/'spec.json',True)
  with self.assertRaisesRegex(ValueError,'receipt'):e.readiness(self.s,self.root)
 def test_new_report_without_overwriting_registered_receipt(self):
  self.accept();old=(self.root/'receipt.json').read_bytes();e.replay(self.root/'spec.json',True,self.root/'second.json');self.assertEqual((self.root/'receipt.json').read_bytes(),old)
 def test_contract_changes_foundation_identity(self):
  before=f.geometry_identity(self.s);self.s['external_geometry']['position_tolerance']=0;self.assertNotEqual(before,f.geometry_identity(self.s))
 def test_invalid_triangle_rejected(self):
  g=copy.deepcopy(self.s['components'][0]['geometry']);g['triangles'][0]=50
  with self.assertRaisesRegex(ValueError,'topology'):e.mesh_set({'version':1,'geometries':{'shell':g}},['shell'])
 def test_receipt_scope_mismatch(self):
  self.accept();p=self.root/'receipt.json';r=e.read(p);r['parameter_influence']={};p.write_text(json.dumps(r));self.s['source_files'][-1]['sha256']=e.sha(p)
  with self.assertRaisesRegex(ValueError,'scope'):e.readiness(self.s,self.root)
 def test_project_foundation_check_uses_resource_root(self):
  import subprocess
  self.accept();(self.root/'project.json').write_text(json.dumps({'schema_version':1,'spec':'spec.json','state':'state.json'}));(self.root/'state.json').write_text('{}')
  tool=Path(__file__).resolve().parents[1]/'scripts'/'project.py'
  r=subprocess.run([sys.executable,str(tool),'foundation-check','--project',str(self.root)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertTrue(json.loads(r.stdout)['construction_ready'])
 def test_uncontrolled_component_refused(self):
  self.s['components'].append(dict(self.s['components'][0],id='extra'));self.s['external_geometry']['component_ids'].append('extra')
  with self.assertRaisesRegex(ValueError,'every external component'):e.contract(self.s,self.root)
 def test_report_cannot_escape_project(self):
  with self.assertRaisesRegex(ValueError,'inside project'):e.replay(self.root/'spec.json',True,self.root.parent/'escape.json')
 def test_existing_report_is_not_overwritten(self):
  self.accept();old=(self.root/'receipt.json').read_bytes()
  with self.assertRaisesRegex(ValueError,'exists'):e.replay(self.root/'spec.json',True)
  self.assertEqual((self.root/'receipt.json').read_bytes(),old)
if __name__=='__main__':unittest.main()
