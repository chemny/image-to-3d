import unittest,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reference_evidence import diff,grid,sha
from PIL import Image
class EvidenceTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
  for name,values in [('a',[0,255,255,0]),('b',[0,0,255,255])]:
   im=Image.new('L',(2,2));im.putdata(values);im.save(self.p/(name+'.png'))
  (self.p/'camera.json').write_text('{}');(self.p/'model.js').write_text('test fixture')
  self.meta={'status':'validated','camera':'camera.json','model':'model.js','camera_sha256':sha(self.p/'camera.json'),'model_sha256':sha(self.p/'model.js'),'reference_mask_sha256':sha(self.p/'a.png'),'candidate_mask_sha256':sha(self.p/'b.png')};self.save()
 def save(self):(self.p/'alignment.json').write_text(json.dumps(self.meta))
 def run_diff(self):return diff(self.p/'a.png',self.p/'b.png',self.p/'alignment.json',self.p/'out')
 def test_red_blue(self):
  r=self.run_diff();self.assertEqual(r['excess_pixels'],1);self.assertEqual(r['missing_pixels'],1);self.assertAlmostEqual(r['iou'],1/3)
  with Image.open(self.p/'out/difference.png') as im:self.assertEqual(im.getpixel((1,0)),(35,95,230));self.assertEqual(im.getpixel((1,1)),(230,45,45))
 def test_stale_model(self):
  (self.p/'model.js').write_text('changed')
  with self.assertRaises(ValueError):self.run_diff()
 def test_unregistered(self):
  self.meta['status']='approximate';self.save()
  with self.assertRaises(ValueError):self.run_diff()
 def test_no_silent_resize(self):
  Image.new('L',(3,3)).save(self.p/'b.png');self.meta['candidate_mask_sha256']=sha(self.p/'b.png');self.save()
  with self.assertRaises(ValueError):self.run_diff()
 def test_grid_not_geometry(self):
  grid(self.p/'a.png',self.p/'grid',2,2);r=json.loads((self.p/'grid/grid.json').read_text());self.assertEqual(len(r['cells']),4);self.assertTrue(all(x['review']=='pending' for x in r['cells']))
if __name__=='__main__':unittest.main()
