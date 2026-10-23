"""Behavior checks for source preservation, explicit roles and GLB rejection."""
import argparse,json,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
from asset_manifest import build,read_glb,sha256,validate
ROOT=Path(__file__).resolve().parents[1]
def fixture(path):
 d={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0,1]}],'nodes':[{'name':'Body','mesh':0},{'name':'Sensor','mesh':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':0},'material':0}]}],'accessors':[{'count':3,'type':'VEC3','componentType':5126,'min':[0,0,0],'max':[1,1,0]}],'materials':[{'name':'Shared','pbrMetallicRoughness':{'baseColorFactor':[1,0,0,1]}}]}
 j=json.dumps(d).encode();j+=b' '*((-len(j))%4);path.write_bytes(struct.pack('<III',0x46546c67,2,20+len(j))+struct.pack('<II',len(j),0x4e4f534a)+j)
class Assets(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.model=self.root/'source.glb';fixture(self.model)
 def tearDown(self):self.tmp.cleanup()
 def test_preserve_and_shared_users(self):
  h=sha256(self.model);m=build(self.model,self.root/'review',{'roles':{'n0:p0':{'role':'paint','evidence':'fixture'}}});self.assertEqual(sha256(self.model),h);self.assertEqual(m['materials'][0]['users'],['n0:p0','n1:p0']);self.assertEqual(m['bindings'][1]['role'],'unassigned')
 def test_protected_overlap_rejected(self):
  m=build(self.model,self.root/'review',{'roles':{'n0:p0':{'role':'paint','evidence':'fixture'}},'protected_features':[{'targets':['n0:p0']}]});c={'schema_version':2,'asset':m['asset'],'paintTargets':['n0:p0']}
  with self.assertRaises(ValueError):validate(m,c,self.model)
 def test_role_needs_evidence(self):
  with self.assertRaises(ValueError):build(self.model,self.root/'review',{'roles':{'n0:p0':{'role':'paint'}}})
 def test_corrupt_glb_rejected_before_web_creation(self):
  self.model.write_bytes(b'not glb');out=self.root/'web';r=subprocess.run([sys.executable,str(ROOT/'scripts/project.py'),'web','--model',str(self.model),'--out',str(out)],capture_output=True);self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
 def test_multi_input_hash_and_originals(self):
  images=[self.root/'a.png',self.root/'b.png']
  for i,p in enumerate(images):p.write_bytes(bytes([i]))
  out=self.root/'task';cmd=[sys.executable,str(ROOT/'scripts/project.py'),'init','--model',str(self.model),'--image',str(images[0]),'--image',str(images[1]),'--out',str(out)]
  subprocess.run(cmd,check=True,capture_output=True);d=json.loads((out/'project.json').read_text());self.assertEqual(len(d['inputs']),3);self.assertEqual(d['source'],'input/source.png');self.assertEqual(d['source_model'],'input/source.glb');self.assertEqual(d['references'][0]['origin'],'user_supplied');self.assertEqual(sha256(out/'input/source.glb'),sha256(self.model));self.assertEqual(images[1].read_bytes(),b'\x01')
  r=subprocess.run(cmd,capture_output=True);self.assertNotEqual(r.returncode,0)
 def test_runtime_cannot_overwrite_template(self):
  runtime=self.root/'runtime';runtime.mkdir();file=runtime/'selection.js';file.write_text('bad')
  config={'schema_version':2,'asset':{},'runtimeDependencies':[{'module':'./selection.js','files':[{'path':'selection.js','sha256':sha256(file)}]}]};c=self.root/'config.json';c.write_text(json.dumps(config));out=self.root/'web'
  r=subprocess.run([sys.executable,str(ROOT/'scripts/project.py'),'web','--model',str(self.model),'--config',str(c),'--runtime-dir',str(runtime),'--out',str(out)],capture_output=True);self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
 def test_missing_panorama_rejected_before_output(self):
  config={'schema_version':2,'asset':{},'interiors':[{'id':'test','panorama':'./absent.png'}]};c=self.root/'config.json';c.write_text(json.dumps(config));out=self.root/'web'
  r=subprocess.run([sys.executable,str(ROOT/'scripts/project.py'),'web','--model',str(self.model),'--config',str(c),'--resource-dir',str(self.root),'--out',str(out)],capture_output=True);self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
 def test_reference_gallery_paths(self):
  for image in ['./missing.png','./../outside.png']:
   c=self.root/'gallery.json';c.write_text(json.dumps({'referenceGallery':[{'image':image,'label':'Reference'}]}));out=self.root/'gallery-web'
   r=subprocess.run([sys.executable,str(ROOT/'scripts/project.py'),'web','--model',str(self.model),'--config',str(c),'--resource-dir',str(self.root),'--out',str(out)],capture_output=True)
   self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
 def test_bundle_hashes_match_actual_files(self):
  out=self.root/'web';subprocess.run([sys.executable,str(ROOT/'scripts/project.py'),'web','--model',str(self.model),'--out',str(out)],check=True,capture_output=True);bundle=json.loads((out/'bundle-manifest.json').read_text());self.assertEqual(bundle['files']['config.json'],sha256(out/'config.json'));self.assertEqual(bundle['files']['model.glb'],sha256(self.model))
 def test_version_mismatch_rejected(self):
  m=build(self.model,self.root/'review');c={'schema_version':2,'asset':{'id':m['asset']['id'],'version':'wrong'}}
  with self.assertRaises(ValueError):validate(m,c,self.model)
if __name__=='__main__':unittest.main()
