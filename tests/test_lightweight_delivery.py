from pathlib import Path
import tempfile
import unittest
import sys
import json
import gzip
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import lightweight_delivery as ld
from scene_build import build,emit_js

class LightweightDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.spec=json.loads((Path(__file__).resolve().parents[1]/'examples/assets/toy.json').read_text())
        self.payload=build(self.spec)
    def test_external_transport_identical(self):
        r=ld.write_runtime(self.root,self.payload)
        self.assertEqual(ld.read_payload(self.root),self.payload);self.assertTrue(r['within_budget'])
        self.assertFalse((self.root/'scene.json').exists())
        text=(self.root/'model.js').read_text();self.assertNotIn('const data={',text);self.assertIn('sceneMetadata',text)
        meta=json.loads((self.root/'scene-meta.json').read_text());self.assertTrue(all('meshes' not in c for c in meta['components']))
    def test_locked_factory_still_passes_original_validator(self):
        ld.write_runtime(self.root,self.payload,locked=True)
        self.assertEqual(ld.read_payload(self.root),self.payload)
        import importlib.util
        module_path=Path(__file__).resolve().parents[1]/'domains/vehicle/scripts/locked_configurator.py'
        spec=importlib.util.spec_from_file_location('locked_factory',module_path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        self.assertEqual(m.adapter_errors((self.root/'model.js').read_text()),[])
    def test_tamper_and_wrong_decoded_hash_rejected(self):
        ld.write_runtime(self.root,self.payload);layout=json.loads((self.root/ld.LAYOUT).read_text());p=self.root/layout['data']['path'];p.write_bytes(p.read_bytes()+b'x')
        with self.assertRaisesRegex(ValueError,'transport integrity'):ld.read_payload(self.root)
        ld.write_runtime(self.root,self.payload);layout=json.loads((self.root/ld.LAYOUT).read_text());layout['data']['decoded_sha256']='0'*64;(self.root/ld.LAYOUT).write_text(json.dumps(layout))
        with self.assertRaisesRegex(ValueError,'Decoded model'):ld.read_payload(self.root)
    def test_metadata_drift_rejected(self):
        ld.write_runtime(self.root,self.payload);(self.root/'scene-meta.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'metadata differs|hash mismatch'):ld.report(self.root)
    def test_budget_is_reported_not_decimated(self):
        r=ld.write_runtime(self.root,self.payload,budget_bytes=1);self.assertFalse(r['within_budget']);self.assertTrue(r['warnings']);self.assertEqual(ld.read_payload(self.root),self.payload)
        for value in [True,0,-1,'50']:
            with self.assertRaises(ValueError):ld.write_runtime(self.root,self.payload,budget_bytes=value)
    def test_legacy_read_supported(self):
        (self.root/'scene.json').write_text(json.dumps(self.payload));self.assertEqual(ld.read_payload(self.root),self.payload)
    def test_texture_hash_and_unique_file_accounting(self):
        f=self.root/'textures/a.png';f.parent.mkdir();f.write_bytes(b'not-rendered-unit-test-texture');h=ld.digest(f.read_bytes())
        for material in self.payload['materials'].values():material['maps']={'map':{'path':'textures/a.png','sha256':h,'color_space':'srgb'}}
        r=ld.write_runtime(self.root,self.payload);self.assertEqual(len(r['textures']),1);f.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Texture hash'):ld.report(self.root)
    def test_glb_transport_preserves_canonical(self):
        f=self.root/'test.glb';raw=b'GLB-unchanged'*10000;f.write_bytes(raw);r=ld.pack_glb(f)
        self.assertEqual(f.read_bytes(),raw);self.assertEqual(gzip.decompress((self.root/r['transport']).read_bytes()),raw)
    def test_unsafe_resource_path_rejected(self):
        ld.write_runtime(self.root,self.payload);layout=json.loads((self.root/ld.LAYOUT).read_text());layout['data']['path']='../outside';(self.root/ld.LAYOUT).write_text(json.dumps(layout))
        with self.assertRaisesRegex(ValueError,'unsafe'):ld.read_payload(self.root)
    def test_migrate_only_new_directory_and_preserve_runtime(self):
        old=self.root/'old';old.mkdir();text=emit_js(self.payload);(old/'model.js').write_text(text);(old/'scene.json').write_text(json.dumps(self.payload));(old/'spec.json').write_text(json.dumps(self.spec));(old/'review.js').write_text("import {buildScene} from './model.js';\nconst payload=await fetch('./scene.json').then(r=>r.json());")
        files={f.name:ld.digest(f.read_bytes()) for f in old.iterdir()};(old/'bundle-manifest.json').write_text(json.dumps({'mode':'generic-review','files':files}))
        new=self.root/'new';ld.migrate(old,new);self.assertEqual(ld.read_payload(new),self.payload);self.assertEqual((old/'model.js').read_text(),text);self.assertTrue((new/'engineering/spec.json').is_file());self.assertFalse((new/'scene.json').exists());self.assertNotIn('fetch(', (new/'review.js').read_text())
        with self.assertRaises(ValueError):ld.migrate(old,new)
    def test_custom_entry_name(self):
        ld.write_runtime(self.root,self.payload,runtime_name='custom.mjs');self.assertTrue((self.root/'custom.mjs').exists());self.assertEqual(ld.read_payload(self.root),self.payload)

if __name__=='__main__':unittest.main()
