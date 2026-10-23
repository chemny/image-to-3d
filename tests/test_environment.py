import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import environment as e


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.libraries={'PIL':{'available':True,'version':'12.0','meets_minimum':True},'numpy':{'available':True,'version':'2.0','meets_minimum':True}}
        self.none={'node':None,'browser':None,'blender':None}

    def doctor(self,*args,**kwargs):
        with patch.object(e,'library_probe',return_value=copy.deepcopy(self.libraries)),patch.object(e,'tools',return_value=self.none):
            return e.doctor(*args,**kwargs)

    def test_core_without_optional_tools_passes(self):
        r=self.doctor();self.assertTrue(r['passed']);self.assertTrue(r['core_ready'])
        self.assertEqual(r['optional']['automation']['status'],'not_requested');self.assertEqual(r['mutations'],[])

    def test_missing_numpy_blocks_only_core(self):
        self.libraries['numpy']={'available':False};self.assertFalse(self.doctor()['core_ready'])

    def test_old_pillow_blocks_core(self):
        self.libraries['PIL']['meets_minimum']=False;self.assertFalse(self.doctor()['passed'])

    def test_old_python_does_not_claim_ready(self):
        with patch.object(e.sys,'version_info',(3,9,0)):self.assertFalse(self.doctor()['passed'])

    def test_missing_requested_automation_reports_core_independently(self):
        r=self.doctor(['automation']);self.assertTrue(r['core_ready']);self.assertFalse(r['passed']);self.assertEqual(r['optional']['blender']['status'],'not_requested')

    def test_missing_requested_blender_is_not_core_failure(self):
        r=self.doctor(['blender']);self.assertTrue(r['core_ready']);self.assertFalse(r['passed'])

    def test_unknown_capability_rejected(self):
        with self.assertRaises(ValueError):self.doctor(['anything'])

    def test_default_doctor_does_not_launch_optional_executables(self):
        with patch.object(e,'run',side_effect=AssertionError('unexpected optional launch')):self.assertTrue(self.doctor()['passed'])

    def test_explicit_blender_only_uses_version_probe(self):
        with patch.object(e,'run',return_value={'ok':True,'stdout':'Blender 4.5','stderr':''}) as run:
            r=self.doctor(['blender'],blender='C:\\Program Files\\Blender\\blender.exe');self.assertTrue(r['passed']);self.assertEqual(run.call_args.args[0],['C:\\Program Files\\Blender\\blender.exe','--version'])

    def test_invalid_blender_not_claimed_available(self):
        with patch.object(e,'run',return_value={'ok':True,'stdout':'some other executable'}):self.assertFalse(self.doctor(['blender'],blender='fake')['passed'])

    def test_windows_browser_path_with_spaces(self):
        env={'PROGRAMFILES':r'C:\Program Files'};expected=r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
        found=e.tools('Windows',env,which=lambda _:None,is_file=lambda p:str(p)==expected)
        self.assertEqual(found['browser'],expected)

    def test_windows_local_appdata_chrome(self):
        env={'LOCALAPPDATA':r'C:\Users\User Name\AppData\Local'};expected=str(e.candidates('Windows',env)['browser'][0])
        self.assertEqual(e.tools('Windows',env,which=lambda _:None,is_file=lambda p:str(p)==expected)['browser'],expected)

    def test_macos_application_paths(self):
        found=e.tools('Darwin',{},which=lambda _:None,is_file=lambda p:str(p) in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Blender.app/Contents/MacOS/Blender'])
        self.assertEqual(found['blender'],'/Applications/Blender.app/Contents/MacOS/Blender');self.assertIn('Google Chrome',found['browser'])

    def test_path_executables_preferred(self):
        found=e.tools('Darwin',{},which=lambda n:'/test/'+n,is_file=lambda p:str(p).startswith('/test/'))
        self.assertEqual(found['node'],'/test/node');self.assertEqual(found['browser'],'/test/google-chrome')

    def test_no_macos_path_guess_on_windows(self):
        paths=e.candidates('Windows',{'PROGRAMFILES':'C:\\Programs'})
        self.assertTrue(all('/Applications/' not in p for p in paths['browser']))

    def test_playwright_existing_package_directory(self):
        p=self.root/'tools with space';p.mkdir();(p/'index.mjs').write_text('export const chromium={};')
        self.assertEqual(e.playwright_entry(p),str((p/'index.mjs').resolve()))

    def test_playwright_missing_does_not_install(self):
        self.assertIsNone(e.playwright_entry(self.root/'missing'))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_optional_probe_uses_argument_lists_and_no_shell(self):
        with patch.object(e.subprocess,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout='ok';run.return_value.stderr=''
            e.run(['C:\\Program Files\\node.exe','--version'])
            self.assertEqual(run.call_args.args[0][0],'C:\\Program Files\\node.exe');self.assertNotIn('shell',run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs['env']['PYTHONUTF8'],'1')

    def test_probe_timeout_is_reported(self):
        with patch.object(e.subprocess,'run',side_effect=subprocess.TimeoutExpired('x',1)):
            self.assertFalse(e.run(['x'])['ok'])

    def test_corrupt_library_probe_does_not_claim_ready(self):
        with patch.object(e,'run',return_value={'ok':True,'stdout':'invalid'}):
            self.assertFalse(e.library_probe()['numpy']['available'])

    def test_installed_package_check(self):self.assertTrue(e.package_check()['complete'])

    def test_modified_bundled_vehicle_template_blocks_core(self):
        with patch.object(e,'CORE',self.root):
            template=self.root/'domains/vehicle/assets/locked-configurator-v1'
            template.mkdir(parents=True)
            (template/'template-lock.json').write_text(json.dumps({'immutable_files':{'index.html':'0'*64}}))
            (template/'index.html').write_text('modified')
            result=e.package_check()
        self.assertFalse(result['complete'])
        self.assertEqual(result['vehicle_template_invalid'],['index.html'])

    def test_failed_browser_first_use_preserves_failure_report(self):
        out=self.root/'failed-browser'
        env={'passed':True,'detected_tools':{'node':'node','browser':'browser'},
             'optional':{'automation':{'playwright_entry':'playwright'}}}
        with patch.object(e,'doctor',return_value=env),patch.object(e,'run',side_effect=[
            {'ok':True,'stdout':'{"passed":true}'}, {'ok':False,'error':'browser launch failed'}]):
            result=e.first_use(out,['automation'])
        self.assertFalse(result['passed'])
        self.assertIn('browser capture failed',result['error'])
        self.assertFalse(json.loads((out/'first-use-report.json').read_text())['passed'])

    def test_existing_smoke_output_refused_without_overwrite(self):
        p=self.root/'existing';p.mkdir();f=p/'keep';f.write_text('keep')
        with self.assertRaises(ValueError):e.first_use(p)
        self.assertEqual(f.read_text(),'keep')

    def test_smoke_refuses_to_write_into_skill(self):
        with self.assertRaises(ValueError):e.first_use(e.CORE/'never-created-smoke-fixture')
        self.assertFalse((e.CORE/'never-created-smoke-fixture').exists())

    def test_failed_environment_creates_no_output(self):
        self.libraries['numpy']['meets_minimum']=False;out=self.root/'not-created'
        with patch.object(e,'library_probe',return_value=self.libraries):r=e.first_use(out)
        self.assertFalse(r['passed']);self.assertFalse(out.exists())

    def test_real_core_smoke_no_node_or_blender(self):
        out=self.root/'First use 中文 with spaces'
        with patch.object(e,'tools',return_value=self.none):r=e.first_use(out)
        self.assertTrue(r['passed'],r);self.assertTrue(r['core']['glb_header_valid']);self.assertTrue((out/'preview/index.html').is_file());self.assertTrue((out/'sample.glb').is_file());self.assertEqual(r['optional']['automation'],'not_requested')
        self.assertEqual(json.loads((out/'first-use-report.json').read_text())['visual_review'],'not_performed')

    def test_cli_doctor_is_read_only_even_with_missing_optional(self):
        out=self.root/'unrequested'
        p=subprocess.run([sys.executable,'-B',str(e.CORE/'scripts/environment.py'),'doctor','--capability','automation','--node',str(out)],capture_output=True,text=True,env=e.child_env())
        self.assertEqual(p.returncode,1);data=json.loads(p.stdout);self.assertTrue(data['core_ready']);self.assertFalse(out.exists())

    def test_cli_first_use_requires_new_output(self):
        p=subprocess.run([sys.executable,'-B',str(e.CORE/'scripts/environment.py'),'first-use'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)

    def test_doctor_out_flag_cannot_write_a_report(self):
        out=self.root/'report.json'
        p=subprocess.run([sys.executable,'-B',str(e.CORE/'scripts/environment.py'),'doctor','--out',str(out)],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
