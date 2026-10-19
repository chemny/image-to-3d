import base64
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from asset_exchange import export_glb


def fixture():
    return {'schema_version':1,'spec_sha256':'fixture','materials':{'red':{'color':'#ff0000','roughness':.6,'metalness':.1}},
        'components':[{'id':'assembly','kind':'assembly','parent':None,'meshes':[],'material':None,'position':[1,2,3],'rotation':[0,0,0]},
        {'id':'door','kind':'part','parent':'assembly','position':[2,0,0],'rotation':[0,0,0],'material':'red','meshes':[{'positions':[0,0,0,1,0,0,0,1,0],'normals':[0,0,1]*3,'indices':[0,1,2],'uvs':[0,0,1,0,0,1]}]}],
        'actions':[{'id':'open','component_id':'door','axis':'y','angle':math.pi/2,'pivot':[0,0,0]}],
        'cameras':{'front':{'type':'perspective','position':[0,2,10],'target':[0,0,0],'width':800,'height':600,'fov_y_deg':40}}}


def parse(raw):
    magic,version,length=struct.unpack_from('<III',raw)
    assert (magic,version,length)==(0x46546c67,2,len(raw))
    n,t=struct.unpack_from('<II',raw,12);assert t==0x4e4f534a
    return json.loads(raw[20:20+n])


class ExchangeTests(unittest.TestCase):
    def test_structure(self):
        raw,m=export_glb(fixture());g=parse(raw)
        self.assertEqual(m['component_ids'],['assembly','door'])
        self.assertEqual(g['animations'][0]['name'],'open')
        self.assertEqual(g['materials'][0]['pbrMetallicRoughness']['baseColorFactor'],[1,0,0,1])
        self.assertEqual(g['cameras'][0]['perspective']['aspectRatio'],800/600)
        self.assertIn('TEXCOORD_0',g['meshes'][0]['primitives'][0]['attributes'])

    def test_texture_hash_and_uv(self):
        with tempfile.TemporaryDirectory() as td:
            f=fixture();raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF1sAAAAASUVORK5CYII=');Path(td,'map.png').write_bytes(raw)
            desc={'path':'map.png','sha256':hashlib.sha256(raw).hexdigest(),'color_space':'srgb'};f['materials']['red']['maps']={'map':desc}
            output,m=export_glb(f,resource_root=td);self.assertEqual(len(parse(output)['images']),1)
            desc['sha256']='bad'
            with self.assertRaisesRegex(ValueError,'SHA-256'):export_glb(f,resource_root=td)
            desc['sha256']=hashlib.sha256(raw).hexdigest();del f['components'][1]['meshes'][0]['uvs']
            with self.assertRaisesRegex(ValueError,'UV'):export_glb(f,resource_root=td)

    def test_variants(self):
        import copy
        f=fixture();second=copy.deepcopy(f['components'][1]);second['id']='alternate';f['components'].append(second)
        f['variants']=[{'id':'door-style','default':'a','options':{'a':['door'],'b':['alternate']}}]
        raw,m=export_glb(f);self.assertEqual(m['omitted_component_ids'],['alternate']);self.assertEqual(m['mesh_count'],1)
        raw,m=export_glb(f,include_all_variants=True);self.assertEqual(m['mesh_count'],2)
        self.assertFalse(next(n for n in parse(raw)['nodes'] if n['name']=='alternate')['extras']['default_visible'])

    def test_fail_closed(self):
        f=fixture();f['materials']['red']['customShader']='x'
        with self.assertRaisesRegex(ValueError,'unsupported'):export_glb(f)
        f=fixture();f['components'][1]['material_slots']={'body':'red','glass':'unknown'}
        with self.assertRaisesRegex(ValueError,'slots'):export_glb(f)

    @unittest.skipUnless(Path('/Applications/Blender.app/Contents/MacOS/Blender').exists(),'Blender not installed')
    def test_actual_blender_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td,'fixture.glb');f=fixture();f['components'][0]['rotation']=[.2,.3,.1]
            def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
            png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b'')
            Path(td,'texture.png').write_bytes(png)
            f['materials']['red']['maps']={'map':{'path':'texture.png','sha256':hashlib.sha256(png).hexdigest(),'color_space':'srgb'}}
            export_glb(f,out,resource_root=td)
            result=subprocess.run(['/Applications/Blender.app/Contents/MacOS/Blender','--background','--python',str(Path(__file__).resolve().parents[1]/'scripts/blender_asset_check.py'),'--','--glb',str(out),'--out',str(Path(td,'check.json'))],capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            check=json.loads(Path(td,'check.json').read_text());self.assertTrue(check['passed'],check)
            self.assertEqual(check['errors'],[])
            self.assertEqual(len(check['animations']),1)
            self.assertTrue(check['materials'][0]['uses_nodes'])
            self.assertTrue(check['materials'][0]['image_nodes'])
            self.assertTrue(check['animations'][0]['channels'])


if __name__=='__main__':unittest.main()
