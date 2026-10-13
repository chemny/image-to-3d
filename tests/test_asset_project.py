import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_project import fixture
import project as p
from scene_build import build

class AssetProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.task=fixture(self.root)
        spec=p.read(self.task/'spec.json');asset=p.read(p.CORE/'examples/assets/toy.json')
        for k in ('components','materials','parameters','actions','variants','asset_contract','cameras'):spec[k]=asset[k]
        spec['observations']=[];spec['connections']=[{'id':'arm-anchor','a':{'component_id':'arm','local_point':[0,0,0]},'b':{'component_id':'toy','local_point':[.55,1.3,0]},'max_distance':1e-7}];spec['asset_contract']['delivery_targets']=['threejs','glb']
        p.save(self.task/'analysis.json',{'references':[{'id':'original','origin':'synthetic','image_size':[256,256]}],'feature_inventory':[{'reference_id':'original','feature':'designed fixture','component_id':'toy','required':True,'visibility':'hidden'}],'inferences':[{'reference_id':'original','feature':'designed fixture','component_id':'toy','rationale':'Synthetic software fixture; no reconstruction claim','confidence':0}]})
        p.save(self.task/'spec.json',spec);p.refresh(self.task)
        self.bundle=self.root/'bundle';p.build_project(self.task,self.bundle,True)
    def audit(self):
        path=self.root/'audit.json';s=p.read(self.task/'spec.json')
        p.save(path,{'passed':True,'spec_file_sha256':p.sha(self.task/'spec.json'),'bundle_manifest_sha256':p.sha(self.bundle/'bundle-manifest.json'),'performed':{k:True for k in s['asset_contract']['required_operations']},'screenshots':[]})
        return path
    def test_exchange_and_required_delivery_proof(self):
        with self.assertRaisesRegex(ValueError,'asset-report'):p.delivery_assets(self.task/'spec.json',self.bundle,None,None)
        folder=self.root/'exchange';r=p.exchange(self.task,self.bundle,folder);self.assertTrue(r['passed']);self.assertTrue((folder/'model.glb').is_file())
        files=p.delivery_assets(self.task/'spec.json',self.bundle,self.audit(),folder);self.assertTrue(any(n.endswith('model.glb') for _,n in files))
        (folder/'model.glb').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'exchange files changed'):p.delivery_assets(self.task/'spec.json',self.bundle,self.audit(),folder)
    def test_stale_audit_refused(self):
        path=self.audit();report=p.read(path);report['spec_file_sha256']='wrong';p.save(path,report)
        with self.assertRaisesRegex(ValueError,'stale'):p.delivery_assets(self.task/'spec.json',self.bundle,path,None)
    def test_mutated_bundle_refused(self):
        (self.bundle/'model.js').write_text('changed')
        with self.assertRaisesRegex(ValueError,'bundle files changed'):p.exchange(self.task,self.bundle,self.root/'bad')
    def test_blender_not_faked(self):
        folder=self.root/'exchange';p.exchange(self.task,self.bundle,folder)
        spec=p.read(self.task/'spec.json');spec['asset_contract']['delivery_targets'].append('blender');p.save(self.task/'spec.json',spec)
        receipt=p.read(folder/'exchange-report.json');receipt['spec_file_sha256']=p.sha(self.task/'spec.json');p.save(folder/'exchange-report.json',receipt)
        with self.assertRaisesRegex(ValueError,'not actually imported'):p.delivery_assets(self.task/'spec.json',self.bundle,self.audit(),folder)
    def test_relative_texture_and_uv_required(self):
        spec=p.read(self.task/'spec.json');part=next(c for c in spec['components'] if c.get('kind')!='assembly');mat=spec['materials'][part['material']]
        mat['maps']={'map':{'path':'references/original.png','sha256':p.sha(self.task/'references/original.png'),'color_space':'srgb'}}
        # Existing box has no authored UV: must reject instead of silently ignoring texture.
        with self.assertRaises(ValueError):build(spec)
    def test_init_contract_is_explicitly_incomplete(self):
        t=self.root/'new';p.init(self.root/'fixture.png','generic',t,'bicycle','configurator',['threejs','glb'])
        spec=p.read(t/'spec.json');self.assertEqual(spec['asset_contract']['object_class'],'bicycle');self.assertEqual(spec['asset_contract']['required_components'],[])
        with self.assertRaises(ValueError):p.validate(t)

if __name__=='__main__':unittest.main()
