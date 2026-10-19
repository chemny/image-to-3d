import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import repair_capture as rc
class CaptureReceiptTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.r=Path(self.t.name);self.b=self.r/'bundle';self.b.mkdir();self.c=self.r/'capture';self.c.mkdir();self.p=self.r/'spec.json'
  self.spec={'parameters':{},'references':[],'source_files':[],'cameras':{'front':{'position':[0,0,3],'target':[0,0,0],'width':4,'height':4,'type':'orthographic','ortho_height':2}}};self.write(self.p,self.spec);(self.b/'model.js').write_text('synthetic bundle fixture, no render claim');self.write(self.b/'bundle-manifest.json',{'spec_sha256':rc.sha(self.p),'source_resources':{},'files':{'model.js':rc.sha(self.b/'model.js')}})
  from PIL import Image
  Image.new('RGB',(4,4),'white').save(self.c/'front.png')
  self.report={'passed':True,'errors':[],'spec_sha256':rc.sha(self.p),'bundle_manifest_sha256':rc.sha(self.b/'bundle-manifest.json'),'cameras':self.spec['cameras'],'captures':[{'view':'front','file':'front.png','sha256':rc.sha(self.c/'front.png'),'mode':'beauty','pose':'closed'}]};self.write(self.c/'capture-report.json',self.report);self.receipt=self.r/'receipt.json'
 def write(self,p,v):p.write_text(json.dumps(v))
 def create(self):return rc.create(self.p,self.b,self.c/'capture-report.json',self.receipt)
 def test_valid_identity(self):self.create();self.assertTrue(rc.validate_receipt(self.receipt,self.p,['front'])['passed'])
 def test_output_not_overwritten(self):self.create();old=self.receipt.read_bytes();self.assertRaisesRegex(ValueError,'exists',self.create);self.assertEqual(old,self.receipt.read_bytes())
 def test_candidate_drift(self):self.create();self.spec['cameras']['front']['position'][0]=1;self.write(self.p,self.spec);self.assertRaisesRegex(ValueError,'candidate',rc.validate_receipt,self.receipt,self.p)
 def test_image_drift(self):self.create();(self.c/'front.png').write_bytes(b'changed');self.assertRaisesRegex(ValueError,'image',rc.validate_receipt,self.receipt,self.p)
 def test_bundle_drift(self):self.create();(self.b/'model.js').write_text('changed');self.assertRaisesRegex(ValueError,'bundle file',rc.validate_receipt,self.receipt,self.p)
 def test_missing_requested_view(self):self.create();self.assertRaisesRegex(ValueError,'Required views',rc.validate_receipt,self.receipt,self.p,['side'])
 def test_capture_camera_mismatch(self):self.report['cameras']=copy.deepcopy(self.spec['cameras']);self.report['cameras']['front']['position'][0]=1;self.write(self.c/'capture-report.json',self.report);self.assertRaisesRegex(ValueError,'camera',self.create)
 def test_forged_artifact_view_binding(self):self.create();r=rc.read(self.receipt);r['views'][0]['artifacts'][0]['mode']='mask';self.write(self.receipt,r);self.assertRaisesRegex(ValueError,'not uniquely bound',rc.validate_receipt,self.receipt,self.p)
 def test_resource_drift(self):
  f=self.r/'source.py';f.write_text('x=1');self.spec['source_files']=[{'path':'source.py','sha256':rc.sha(f)}];self.write(self.p,self.spec);m=rc.read(self.b/'bundle-manifest.json');m.update(spec_sha256=rc.sha(self.p),source_resources={'source.py':rc.sha(f)});self.write(self.b/'bundle-manifest.json',m);self.report.update(spec_sha256=rc.sha(self.p),bundle_manifest_sha256=rc.sha(self.b/'bundle-manifest.json'));self.write(self.c/'capture-report.json',self.report);self.create();f.write_text('x=2');self.assertRaisesRegex(ValueError,'resource',rc.validate_receipt,self.receipt,self.p)
if __name__=='__main__':unittest.main()
