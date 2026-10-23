"""Migration regressions use synthetic assets and an isolated copy, never user models."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

CORE=Path(__file__).resolve().parents[1]


def config():
    return {'asset':'synthetic-test','title':'Synthetic fixture','brand':'Fixture','edition':'TEST',
            'headline':'Fixture','subtitle':'Fixture','panelTitle':'Fixture','note':'Synthetic test only',
            'referenceBase':'./references/','cameraTarget':[0,.5,0],'cameraScale':1,
            'paints':[['p'+str(i),'#445566'] for i in range(6)],'rims':[['a'],['b'],['c']],
            'scenes':[['s'+str(i),'#eeeeee'] for i in range(3)],
            'views':[['front-left' if i==0 else 'v'+str(i),'View '+str(i),[5,3,5],'ref'+str(i)] for i in range(8)],
            'partBindings':{k:[k+'-open' if k!='hood' else 'lid-open'] for k in ['left','right','hood','trunk']}}


class VehicleModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.base=Path(cls.tmp.name);cls.core=cls.base/'relocated Skill 中文'
        shutil.copytree(CORE,cls.core,ignore=shutil.ignore_patterns('__pycache__','.git'))
        cls.env=dict(os.environ,PYTHONPATH=str(cls.core/'scripts')+os.pathsep+str(cls.core/'tests'),
                     HOME=str(cls.base/'empty-home'),PYTHONDONTWRITEBYTECODE='1')

    def run_tool(self,tool,*args):
        return subprocess.run([sys.executable,str(self.core/'scripts/vehicle.py'),tool,*map(str,args)],
                              env=self.env,cwd=self.base,capture_output=True,text=True)

    def test_relocated_module_needs_no_sibling_skill(self):
        for tool in ['asset_manifest','project','prepare_model','feature_guard','locked_configurator','image_reconstruction']:
            p=self.run_tool(tool,'--help');self.assertEqual(p.returncode,0,p.stderr)
        self.assertFalse((self.core/'domains/vehicle/SKILL.md').exists())

    def test_module_dispatch_cannot_escape(self):
        p=self.run_tool('../../outside','--help');self.assertNotEqual(p.returncode,0)

    def test_template_and_vendors_preserved(self):
        base=self.core/'domains/vehicle/assets/locked-configurator-v1'
        lock=json.loads((base/'template-lock.json').read_text())
        for name,h in lock['immutable_files'].items():
            self.assertEqual(hashlib.sha256((base/name).read_bytes()).hexdigest(),h)

    def test_all_dispatch_targets_packaged(self):
        sys.path.insert(0,str(CORE/'scripts'))
        try:
            from vehicle import TOOLS
            for name in TOOLS:self.assertTrue((self.core/'domains/vehicle/scripts'/(name+'.py')).is_file())
        finally:sys.path.pop(0)

    def build_fixture(self,folder):
        work=self.base/folder;work.mkdir();cfg=work/'vehicle.json';cfg.write_text(json.dumps(config()))
        script='''from pathlib import Path
import json,sys,shutil
from test_project import fixture
from project import build_project
base=Path(sys.argv[1]);task=fixture(base);p=task/'spec.json';s=json.loads(p.read_text());cfg=json.loads((base/'vehicle.json').read_text())
for i in range(3):
 key='light'+str(i);s['materials'][key]={'color':'#ffffff','emissive':'#ffffff','roughness':.5,'metalness':0}
 s['components'].append({'id':key,'role':'lamp','parent':'body','material':key,'geometry':{'type':'box','size':[.05,.05,.05]},'position':[i*.1,.1,.1]})
 key='wheel'+str(i);s['components'].append({'id':key,'role':'wheel','parent':'body','material':'trim','geometry':{'type':'box','size':[.1,.1,.1]},'position':[i*.1,0,0]})
for i,key in enumerate(['left','right','trunk']):
 s['components'].append({'id':key,'role':'panel','parent':'body','material':'shell','geometry':{'type':'box','size':[.1,.1,.1]},'position':[i*.1,.2,0]})
 s['actions'].append({'id':key+'-open','component_id':key,'axis':'y','angle':.8,'pivot':[0,0,0]})
 s['connections'].append({'id':key+'-connection','a':{'component_id':key,'local_point':[0,0,0]},'b':{'component_id':'body','local_point':[i*.1,.2,0]},'max_distance':.000001})
s['vehicle_bindings']={'paint':['shell'],'lights':['light0','light1','light2'],'wheels':[['wheel0'],['wheel1'],['wheel2']],'actions':cfg['partBindings']}
reference=s['references'][0]
for id in [v[3] for v in cfg['views']]+['d01-front','d02-lamp','d03-roof','d04-wheel','d05-rear','d06-door']:
 rel='references/'+id+'.png';shutil.copy2(task/reference['path'],task/rel)
 s['references'].append(dict(reference,id=id,path=rel))
p.write_text(json.dumps(s))
print(json.dumps(build_project(task,base/'web',True,base/'vehicle.json')))
'''
        result=subprocess.run([sys.executable,'-c',script,str(work)],env=self.env,cwd=self.base,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return work

    def test_top_level_build_defaults_to_embedded_template(self):
        work=self.build_fixture('build-case');result=json.loads((work/'web/bundle-manifest.json').read_text())
        self.assertEqual(result['mode'],'locked-vehicle')
        self.assertTrue((work/'web/delivery-layout.json').is_file())
        check=self.run_tool('locked_configurator','check','--out',work/'web')
        self.assertEqual(check.returncode,0,check.stdout+check.stderr)

    def test_tampered_template_rejected(self):
        # A case edit must not bypass the unchanged canonical template lock.
        work=self.build_fixture('tamper-case');(work/'web/style.css').write_text('changed')
        check=self.run_tool('locked_configurator','check','--out',work/'web')
        self.assertNotEqual(check.returncode,0)

    def test_corrupt_model_does_not_create_output(self):
        work=self.base/'corrupt';work.mkdir();model=work/'bad.glb';model.write_bytes(b'corrupt');out=work/'output'
        result=self.run_tool('project','web','--model',model,'--out',out)
        self.assertNotEqual(result.returncode,0);self.assertFalse(out.exists())

    def test_original_vehicle_regressions_run_without_global_imports(self):
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(self.core/'domains/vehicle/scripts'),'-p','test_*.py'],env=self.env,cwd=self.base,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
