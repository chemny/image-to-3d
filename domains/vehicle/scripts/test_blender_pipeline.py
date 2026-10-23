"""Offline integrity/gate tests; actual Blender case tests belong in task outputs."""
import argparse,json,tempfile,unittest
from pathlib import Path
import blender_pipeline as p
class IntegrityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  for n in ('model.blend','model.glb'):(self.root/n).write_bytes(n.encode())
  p.write(self.root/'result.json',{'blend_sha256':p.digest(self.root/'model.blend'),'glb_sha256':p.digest(self.root/'model.glb'),'checks':{'missing_required_nodes':[]}})
  p.write(self.root/'job.json',{'state':'awaiting_review'})
  self.evidence=self.root/'image.png';self.evidence.write_bytes(b'fixture')
 def tearDown(self):self.tmp.cleanup()
 def args(self):return argparse.Namespace(job=self.root,verdict='passed',scope='fixture',reason='test only',issue=[],evidence=[self.evidence])
 def test_mutated_model_rejected(self):
  (self.root/'model.glb').write_bytes(b'changed')
  with self.assertRaises(ValueError):p.review(self.args())
  self.assertFalse((self.root/'review.json').exists())
 def test_failed_job_cannot_pass(self):
  p.write(self.root/'job.json',{'state':'failed'})
  with self.assertRaises(ValueError):p.review(self.args())
 def test_missing_node_cannot_pass(self):
  r=p.read(self.root/'result.json');r['checks']['missing_required_nodes']=['Door'];p.write(self.root/'result.json',r)
  with self.assertRaises(ValueError):p.review(self.args())
 def test_review_records_exact_result(self):
  p.review(self.args());self.assertEqual(p.read(self.root/'review.json')['result_sha256'],p.digest(self.root/'result.json'))
 def test_missing_evidence_rejected(self):
  a=self.args();a.evidence=[self.root/'missing.png']
  with self.assertRaises(ValueError):p.review(a)
if __name__=='__main__':unittest.main()
