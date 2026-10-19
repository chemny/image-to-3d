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

class NewComparisonTests(unittest.TestCase):
 setUp=EvidenceTest.setUp
 save=EvidenceTest.save
 run_diff=EvidenceTest.run_diff
 def test_overlap_green(self):
  self.run_diff()
  with Image.open(self.p/'out/difference.png')as im:self.assertEqual(im.getpixel((0,1)),(35,175,95))
 def test_pixel_grid_coordinates_and_source_identity(self):
  grid(self.p/'a.png',self.p/'pixel',pixel_step=50);r=json.loads((self.p/'pixel/grid.json').read_text());self.assertEqual(r['grid_kind'],'pixel');self.assertEqual(r['pixel_step'],50);self.assertEqual(r['sha256'],sha(self.p/'a.png'));self.assertEqual(r['image']['sha256'],sha(self.p/'pixel/grid.png'))
 def test_metric_recomputation(self):
  from reference_evidence import validate_diff
  self.run_diff();self.assertTrue(validate_diff(self.p/'out/metrics.json')['passed'])
 def test_forged_metric_even_with_intact_images(self):
  from reference_evidence import validate_diff
  self.run_diff();p=self.p/'out/metrics.json';d=json.loads(p.read_text());d['iou']=1;p.write_text(json.dumps(d))
  with self.assertRaisesRegex(ValueError,'metrics'):validate_diff(p)
 def test_forged_image_even_with_refreshed_hash(self):
  from reference_evidence import validate_diff
  self.run_diff();p=self.p/'out/metrics.json';d=json.loads(p.read_text());Image.new('RGB',(2,2),'green').save(self.p/'out/difference.png');d['image']['sha256']=sha(self.p/'out/difference.png');p.write_text(json.dumps(d))
  with self.assertRaisesRegex(ValueError,'image does not match'):validate_diff(p)
