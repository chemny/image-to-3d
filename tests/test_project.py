import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import project as p


def fixture(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(256,256),'white');ImageDraw.Draw(im).rectangle((80,85,175,170),fill='gray');im.save(root/'fixture.png')
    task=root/'task';p.init(root/'fixture.png','generic',task)
    s=p.read(task/'spec.json');s['quality_contract']['scope']='synthetic-software-test'
    s['references'][0].update(origin='synthetic',approved=False,provenance='Programmatically created software fixture, not a photograph or accepted design')
    s['parameters']={'x':{'value':0,'min':-.5,'max':.5}}
    s['materials']={'shell':{'color':'#99aabc','roughness':.5,'metalness':.2},'trim':{'color':'#333333','roughness':.8,'metalness':0}}
    s['components']=[{'id':'body','parent':None,'role':'shell','material':'shell','position':[{'param':'x'},.4,0],'geometry':{'type':'box','size':[1.2,.8,.8]},'topology_contract':'closed_shell'},
        {'id':'lid','parent':'body','role':'lid','material':'trim','position':[0,.42,0],'geometry':{'type':'box','size':[1.2,.04,.8]},'topology_contract':'closed_shell'}]
    s['actions']=[{'id':'lid-open','component_id':'lid','axis':'x','angle':-1.2,'pivot':[0,.4,-.4]}]
    s['connections']=[{'id':'lid-hinge','a':{'component_id':'lid','local_point':[0,-.02,-.4]},'b':{'component_id':'body','local_point':[0,.4,-.4]},'max_distance':.00001}]
    s['cameras']={'front':{'type':'orthographic','width':256,'height':256,'position':[0,.4,5],'target':[0,.4,0],'up':[0,1,0],'ortho_height':4},'oblique':{'type':'perspective','width':256,'height':256,'position':[3,2,4],'target':[0,.4,0],'up':[0,1,0],'fov_y_deg':40}}
    s['observations']=[{'id':'center','reference_id':'original','feature':'center','component_id':'body','parameter_ids':['x'],'local_point':[0,0,0],'camera_id':'front','target':[140.8,128],'roi':[0,0,256,256],'role':'calibration','sigma_px':1},
         {'id':'held','reference_id':'original','feature':'corner','component_id':'body','parameter_ids':['x'],'local_point':[.6,.4,.4],'camera_id':'front','target':[179.2,102.4],'roi':[0,0,256,256],'role':'validation','sigma_px':1}]
    analysis={'references':[{'id':'original','origin':'synthetic','image_size':[256,256]}],'feature_inventory':[{'reference_id':'original','feature':o['feature'],'component_id':'body','required':True,'visibility':'visible'} for o in s['observations']],'inferences':[]}
    p.save(task/'analysis.json',analysis);p.save(task/'spec.json',s);p.refresh(task);return task

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.task=fixture(self.root)
    def test_unreviewed_production_build_refused(self):
        with self.assertRaisesRegex(ValueError,'Spec review'):p.build_project(self.task,self.root/'prod')
    def test_full_diagnostic_fit_build_chain(self):
        self.assertTrue(p.validate(self.task)['passed']);before=self.root/'before';p.build_project(self.task,before,True)
        fit=self.root/'fit.json';p.fit_project(self.task,fit,['x'],30,True);r=p.read(fit);self.assertLess(r['final_objective'],.01)
        p.adopt(self.task,fit);self.assertAlmostEqual(p.read(self.task/'spec.json')['parameters']['x']['value'],.2,places=3)
        after=self.root/'after';p.build_project(self.task,after,True)
        self.assertNotEqual(p.sha(before/'model.js'),p.sha(after/'model.js'))
        with self.assertRaisesRegex(ValueError,'Delivery review'):p.export(self.task,after,self.root/'export')
    def test_analysis_changes_invalidate_input(self):
        with (self.task/'analysis.json').open('a') as f:f.write(' ')
        with self.assertRaisesRegex(ValueError,'resource hash'):p.validate(self.task)
    def test_old_fit_cannot_overwrite_new_spec(self):
        out=self.root/'fit.json';p.fit_project(self.task,out,['x'],5,True)
        s=p.read(self.task/'spec.json');s['parameters']['x']['value']=.3;p.save(self.task/'spec.json',s)
        with self.assertRaisesRegex(ValueError,'stale spec'):p.adopt(self.task,out)
    def test_template_cannot_pass_without_review(self):
        out=self.root/'review.json';p.review_template(self.task,out)
        with self.assertRaisesRegex(ValueError,'passing review'):p.workflow.mark(self.task/'state.json',out)
    def test_adopt_does_not_change_targets_or_bounds(self):
        out=self.root/'fit.json';p.fit_project(self.task,out,['x'],5,True)
        data=p.read(out);data['spec']['observations'][0]['target']=[0,0];p.save(out,data);before=p.sha(self.task/'spec.json')
        with self.assertRaisesRegex(ValueError,'non-parameter'):p.adopt(self.task,out)
        self.assertEqual(before,p.sha(self.task/'spec.json'))
    def test_failed_rebase_restores_exact_spec_bytes(self):
        out=self.root/'fit.json';p.fit_project(self.task,out,['x'],5,True)
        state=p.read(self.task/'state.json');state['stages']={'intake':{'evidence_path':'missing'}};p.save(self.task/'state.json',state)
        before=(self.task/'spec.json').read_bytes()
        with self.assertRaises(ValueError):p.adopt(self.task,out)
        self.assertEqual(before,(self.task/'spec.json').read_bytes())
    def test_export_archives_artifacts_and_relocates_inputs(self):
        from unittest.mock import patch
        bundle=self.root/'bundle';p.build_project(self.task,bundle,True)
        m=p.read(bundle/'bundle-manifest.json');m['diagnostic']=False;p.save(bundle/'bundle-manifest.json',m)
        evidence=self.task/'review-fixture.json';p.save(evidence,{'artifacts':[{'path':'analysis.json','sha256':p.sha(self.task/'analysis.json')}]})
        state=p.read(self.task/'state.json');state['stages']={'intake':{'evidence_path':str(evidence)}};p.save(self.task/'state.json',state)
        # Isolate exporter mechanics from stage judgment; this fixture is never actual approval.
        with patch.object(p.workflow,'status',return_value={'blocked':False,'next':None}):p.export(self.task,bundle,self.root/'export')
        dest=self.root/'export';self.assertTrue((dest/'reviews/intake/review.json').exists())
        p.workflow.validate_spec(dest/'rebuild/spec.json')
        self.assertEqual(p.read(dest/'bundle-manifest.json')['files'],p.bundle_hashes(dest))
        import subprocess
        proc=subprocess.run([sys.executable,str(dest/'rebuild/toolchain/scripts/project.py'),'validate','--project',str(dest/'rebuild')],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertTrue((dest/'rebuild/toolchain/assets/scene-runtime.mjs').is_file())

if __name__=='__main__':unittest.main()
