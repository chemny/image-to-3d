"""Offline adapter contract tests; no provider requests or credits used."""
import io, os, struct, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import tripo

class AdapterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.image=self.root/'front.png';self.image.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
  self.folder=self.root/'candidate'
  tripo.prepare({'front':self.image,'left':self.image},self.folder)
  self.env=patch.dict(os.environ,{'TRIPO_API_KEY':'test-only'});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def submitted(self):tripo.write(self.folder/'submission.json',{'task_id':'task-1'})
 def ready(self):
  self.submitted();tripo.write(self.folder/'status.json',{'task_id':'task-1','status':'success','credits_consumed':10,'output':{'model_url':'https://example.com/model.glb'}})
 def test_prepare_guards(self):
  for views in ({'left':self.image,'back':self.image},{'front':self.image}):
   with self.assertRaises(ValueError):tripo.prepare(views,self.root/'invalid')
  with self.assertRaises(ValueError):tripo.prepare({'front':self.image,'left':self.image},self.root/'invalid',True,True)
 def test_submit_payload_and_duplicate_guard(self):
  with patch.object(tripo,'api',side_effect=[{'file_token':'a'},{'file_token':'b'},{'task_id':'task-1'}]) as api:
   self.assertEqual(tripo.submit(self.folder,True),{'task_id':'task-1'})
   payload=api.call_args_list[-1].args[1]
   self.assertEqual(payload['inputs'],[{'front':{'file_token':'a'}},{'left':{'file_token':'b'}}])
   self.assertFalse(payload['texture']);self.assertFalse(payload['pbr'])
   self.assertIn(b'name="file"',api.call_args_list[0].args[1])
   with self.assertRaises(FileExistsError):tripo.submit(self.folder,True)
   self.assertEqual(api.call_count,3)
 def test_uncertain_submit_blocks_retry(self):
  with patch.object(tripo,'api',side_effect=[{'file_token':'a'},{'file_token':'b'},TimeoutError()]) as api:
   with self.assertRaises(TimeoutError):tripo.submit(self.folder,True)
   self.assertEqual(tripo.read(self.folder/'submission.json')['status'],'SUBMISSION_UNCERTAIN')
   with self.assertRaises(FileExistsError):tripo.submit(self.folder,True)
   self.assertEqual(api.call_count,3)
 def test_changed_image_blocks_network(self):
  self.image.write_bytes(b'changed')
  with patch.object(tripo,'api') as api:
   with self.assertRaises(ValueError):tripo.submit(self.folder,True)
   api.assert_not_called()
  self.assertFalse((self.folder/'submission.json').exists())
 def test_missing_key(self):
  with patch.dict(os.environ,{},clear=True),patch.object(tripo,'api') as api:
   with self.assertRaises(ValueError):tripo.submit(self.folder,True)
   api.assert_not_called()
 def test_status_identity(self):
  self.submitted()
  with patch.object(tripo,'api',return_value={'task_id':'other','status':'success'}):
   with self.assertRaises(ValueError):tripo.status(self.folder)
  with patch.object(tripo,'api',return_value={'task_id':'task-1','status':'success','credits_consumed':10}):
   self.assertEqual(tripo.status(self.folder)['credits_consumed'],10)
 def test_valid_download(self):
  self.ready();raw=struct.pack('<4sII',b'glTF',2,24)+struct.pack('<II',4,0x4E4F534A)+b'{}  '
  with patch.object(tripo,'urlopen',return_value=io.BytesIO(raw)) as get:
   tripo.download(self.folder)
   get.assert_called_once_with('https://example.com/model.glb',timeout=60)
  self.assertEqual((self.folder/'model.glb').read_bytes(),raw)
 def test_invalid_download_cleanup(self):
  self.ready()
  with patch.object(tripo,'urlopen',return_value=io.BytesIO(b'error')):
   with self.assertRaises(ValueError):tripo.download(self.folder)
  self.assertFalse((self.folder/'model.glb.part').exists());self.assertFalse((self.folder/'model.glb').exists())
 def test_existing_partial_preserved(self):
  self.ready();temp=self.folder/'model.glb.part';temp.write_bytes(b'existing')
  with patch.object(tripo,'urlopen') as get:
   with self.assertRaises(FileExistsError):tripo.download(self.folder)
   get.assert_not_called()
  self.assertEqual(temp.read_bytes(),b'existing')

if __name__=='__main__':unittest.main()
