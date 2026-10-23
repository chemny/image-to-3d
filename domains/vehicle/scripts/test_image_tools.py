import base64,hashlib,json,tempfile,unittest
from pathlib import Path
from reference_pack import build
from loft_sections import geometry

class ImageTools(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.image=self.root/'a.png';self.image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jHGoAAAAASUVORK5CYII='));self.spec={'schema_version':1,'sources':[{'id':'a','path':'a.png','sha256':hashlib.sha256(self.image.read_bytes()).hexdigest(),'origin':'user_supplied'}],'views':[{'id':'front','source_id':'a','consistency':'accepted','configuration_group':'v','projection':'unknown','evidence':'fixture','configuration':{'sensor':{'value':'low','evidence':'fixture'}}}]}
 def tearDown(self):self.tmp.cleanup()
 def execute(self):
  p=self.root/'spec.json';p.write_text(json.dumps(self.spec));return build(p,self.root/'out')
 def test_preserve_source(self):
  r=self.execute();self.assertEqual((self.root/'out/sources/a.png').read_bytes(),self.image.read_bytes());self.assertEqual(r['views'][0]['roi'],[0,0,1,1])
 def test_stale_rejected_before_creation(self):
  self.spec['sources'][0]['sha256']='bad'
  with self.assertRaises(ValueError):self.execute()
  self.assertFalse((self.root/'out').exists())
 def test_bad_roi_rejected(self):
  self.spec['views'][0]['roi']=[0,0,2,1]
  with self.assertRaises(ValueError):self.execute()
  self.assertFalse((self.root/'out').exists())
 def test_accepted_conflict_rejected(self):
  v={**self.spec['views'][0],'id':'side','configuration':{'sensor':{'value':'high','evidence':'fixture'}}};self.spec['views'].append(v)
  with self.assertRaises(ValueError):self.execute()
 def test_excluded_conflict_retained(self):
  v={**self.spec['views'][0],'id':'side','consistency':'excluded','configuration':{'sensor':{'value':'high','evidence':'fixture'}}};self.spec['views'].append(v);self.assertEqual(len(self.execute()['views']),2)
 def test_no_overwrite(self):
  self.execute()
  with self.assertRaises(ValueError):self.execute()
 def test_loft_closed_topology(self):
  p={'schema_version':1,'evidence':'fixture','sections':[{'station':x,'profile':[[0,0],[1,0],[1,1],[0,1]]} for x in [0,2]]};vs,fs=geometry(p);self.assertEqual((len(vs),len(fs)),(8,6));edges={}
  for f in fs:
   for a,b in zip(f,f[1:]+f[:1]):key=tuple(sorted([a,b]));edges[key]=edges.get(key,0)+1
  self.assertTrue(all(n==2 for n in edges.values()))
 def test_station_and_profile_errors(self):
  for sections in [[{'station':1,'profile':[[0,0],[1,0],[0,1]]},{'station':0,'profile':[[0,0],[1,0],[0,1]]}],[{'station':0,'profile':[[0,0],[1,0],[0,1]]},{'station':1,'profile':[[0,0],[1,0],[0,1],[0,1]]}]]:
   with self.assertRaises(ValueError):geometry({'schema_version':1,'evidence':'fixture','sections':sections})
 def test_opposite_profile_winding_rejected(self):
  p=[[0,0],[1,0],[0,1]]
  with self.assertRaises(ValueError):geometry({'schema_version':1,'evidence':'fixture','sections':[{'station':0,'profile':p},{'station':1,'profile':list(reversed(p))}]})
if __name__=='__main__':unittest.main()
