import contextlib
import copy
import io
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import setup_skill as s


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=(Path(self.tmp.name)/'App data 中文 with spaces').resolve()
        self.good={'passed':True,'core_ready':True,'package':{'complete':True},'python':{'meets_minimum':True},'libraries':{'PIL':{'meets_minimum':True},'numpy':{'meets_minimum':True}}}
        self.bad=copy.deepcopy(self.good);self.bad['passed']=self.bad['core_ready']=False;self.bad['libraries']['numpy']['meets_minimum']=False

    def owned(self):
        venv=self.root/'venv';python=s.interpreter(venv);python.parent.mkdir(parents=True);python.write_text('synthetic test interpreter')
        (self.root/'environment-owner.json').write_text(json.dumps({'skill':'image-to-3d','venv':str(venv)}));return python

    def fake_execute(self,command,timeout=60):
        args=[str(x)for x in command]
        if 'first-use'in args:
            out=Path(args[args.index('--out')+1]);out.mkdir(parents=True)
            (out/'first-use-report.json').write_text('{"passed":true}')
        return {'ok':True,'stdout':'{}','stderr':''}

    def quiet(self,*args,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):return s.setup(*args,**kwargs)

    def test_missing_core_check_only_never_prompts_or_writes(self):
        with patch.object(s,'diagnose',return_value=self.bad),patch.object(s,'approve',side_effect=AssertionError('prompt')):
            self.assertFalse(self.quiet(self.root,True)['passed'])
        self.assertFalse(self.root.exists())

    def test_healthy_check_only_never_runs_first_use(self):
        with patch.object(s,'diagnose',return_value=self.good),patch.object(s,'execute',side_effect=AssertionError('mutation')):
            self.assertTrue(self.quiet(self.root,True)['passed'])
        self.assertFalse(self.root.exists())

    def test_decline_changes_nothing(self):
        with patch.object(s,'diagnose',return_value=self.bad),patch.object(s,'approve',return_value=False),patch.object(s,'execute')as execute:
            result=self.quiet(self.root)
        self.assertFalse(result['passed']);execute.assert_not_called();self.assertFalse(self.root.exists())

    def test_no_tty_is_not_approval(self):
        with patch.object(s.sys.stdin,'isatty',return_value=False),patch('builtins.input',side_effect=AssertionError('input')),contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(s.approve({'packages':['numpy']}))

    def test_enter_is_not_approval(self):
        with patch.object(s.sys.stdin,'isatty',return_value=True),patch('builtins.input',return_value=''),contextlib.redirect_stdout(io.StringIO()):self.assertFalse(s.approve({}))

    def test_install_confirmation_is_explicit(self):
        with patch.object(s.sys.stdin,'isatty',return_value=True),patch('builtins.input',return_value='INSTALL'),contextlib.redirect_stdout(io.StringIO()):self.assertTrue(s.approve({}))

    def test_fresh_isolated_environment_installs_both_core_libraries_only(self):
        with patch.object(s,'diagnose',side_effect=[self.bad,self.good]),patch.object(s,'approve',return_value=True)as approve,patch.object(s,'execute',side_effect=self.fake_execute)as execute:
            result=self.quiet(self.root)
        self.assertTrue(result['passed']);self.assertEqual(approve.call_args.args[0]['packages'],['Pillow>=9','numpy>=1.24'])
        commands=[list(map(str,c.args[0]))for c in execute.call_args_list];self.assertIn('venv',commands[0]);self.assertEqual(commands[1][0],str(s.interpreter(self.root/'venv')));self.assertIn('--only-binary=:all:',commands[1]);self.assertIn('https://pypi.org/simple',commands[1]);self.assertNotIn('playwright',str(commands));self.assertTrue(Path(result['first_use_report']).is_file())

    def test_owned_environment_repairs_only_missing_core_package(self):
        python=self.owned()
        with patch.object(s,'diagnose',side_effect=[self.bad,self.good]),patch.object(s,'approve',return_value=True)as approve,patch.object(s,'execute',side_effect=self.fake_execute)as execute:
            self.assertTrue(self.quiet(self.root)['passed'])
        self.assertEqual(approve.call_args.args[0]['packages'],['numpy>=1.24']);self.assertEqual(len(execute.call_args_list),2);self.assertEqual(execute.call_args_list[0].args[0][0],str(python))

    def test_healthy_system_python_does_not_create_venv_or_prompt(self):
        with patch.object(s,'diagnose',return_value=self.good),patch.object(s,'approve',side_effect=AssertionError('prompt')),patch.object(s,'execute',side_effect=self.fake_execute):result=self.quiet(self.root)
        self.assertTrue(result['passed']);self.assertFalse((self.root/'venv').exists());self.assertFalse((self.root/'environment-owner.json').exists())

    def test_existing_healthy_managed_interpreter_is_reused(self):
        python=self.owned()
        with patch.object(s,'diagnose',return_value=self.good)as diagnose,patch.object(s,'execute',side_effect=self.fake_execute):result=self.quiet(self.root)
        self.assertTrue(result['passed']);self.assertEqual(diagnose.call_args.args[0],python)

    def test_unowned_venv_is_never_overwritten(self):
        (self.root/'venv').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'unowned'):self.quiet(self.root)

    def test_mismatched_owner_rejected(self):
        self.owned();(self.root/'environment-owner.json').write_text('{"skill":"other","venv":"wrong"}')
        with self.assertRaisesRegex(ValueError,'mismatch'):self.quiet(self.root)

    def test_corrupt_marker_rejected(self):
        self.owned();(self.root/'environment-owner.json').write_text('invalid')
        with self.assertRaisesRegex(ValueError,'Invalid'):self.quiet(self.root)

    def test_incomplete_managed_environment_not_recreated(self):
        python=self.owned();python.unlink()
        with self.assertRaisesRegex(ValueError,'incomplete'):self.quiet(self.root)

    @unittest.skipUnless(os.name == 'posix','symlink fixture requires a POSIX host')
    def test_linked_venv_refused(self):
        self.root.mkdir();(self.root/'venv').symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'linked'):self.quiet(self.root)

    def test_inside_skill_output_refused(self):
        out=s.CORE/'must-not-create-setup-test'
        with self.assertRaises(ValueError):self.quiet(out)
        self.assertFalse(out.exists())

    def test_missing_package_files_never_attempts_install(self):
        data=copy.deepcopy(self.bad);data['package']['complete']=False
        with patch.object(s,'diagnose',return_value=data),patch.object(s,'approve',side_effect=AssertionError('prompt')):self.assertFalse(self.quiet(self.root)['passed'])
        self.assertFalse(self.root.exists())

    def test_old_python_never_attempts_library_install(self):
        data=copy.deepcopy(self.bad);data['python']['meets_minimum']=False
        with patch.object(s,'diagnose',return_value=data),patch.object(s,'approve',side_effect=AssertionError('prompt')):self.assertFalse(self.quiet(self.root)['passed'])

    def test_failed_venv_creation_keeps_receipt_and_does_not_run_pip(self):
        with patch.object(s,'diagnose',return_value=self.bad),patch.object(s,'approve',return_value=True),patch.object(s,'execute',return_value={'ok':False,'error':'venv unavailable'})as execute:result=self.quiet(self.root)
        self.assertFalse(result['passed']);self.assertEqual(execute.call_count,1);self.assertEqual(len(list(self.root.glob('setup-failure-*.json'))),1)

    def test_failed_pip_keeps_managed_marker_and_no_first_use(self):
        self.owned()
        with patch.object(s,'diagnose',return_value=self.bad),patch.object(s,'approve',return_value=True),patch.object(s,'execute',return_value={'ok':False,'error':'network unavailable'})as execute:result=self.quiet(self.root)
        self.assertFalse(result['passed']);self.assertEqual(execute.call_count,1);self.assertTrue((self.root/'environment-owner.json').exists())

    def test_missing_optional_does_not_install_it(self):
        data=copy.deepcopy(self.good);data['passed']=False
        with patch.object(s,'diagnose',return_value=data),patch.object(s,'approve',side_effect=AssertionError('optional install')),patch.object(s,'execute')as execute:result=self.quiet(self.root,capabilities=['automation'])
        self.assertFalse(result['passed']);self.assertTrue(result['environment']['core_ready']);self.assertFalse(result['optional_installation']);execute.assert_not_called();self.assertFalse(self.root.exists())

    def test_optional_parameters_preserve_spaces_as_arguments(self):
        flags=s.arguments(['automation','blender'],node=r'C:\Program Files\node.exe',playwright_module=r'C:\tools 中文\playwright',blender=r'C:\Program Files\Blender\blender.exe')
        self.assertIn(r'C:\Program Files\node.exe',flags);self.assertEqual(flags.count('--capability'),2)

    def test_unknown_optional_capability_refused(self):
        with self.assertRaises(ValueError):s.arguments(['unknown'])

    def test_bad_diagnostic_output_cannot_pass(self):
        with patch.object(s,'execute',return_value={'ok':False,'stdout':'not json'}):
            with self.assertRaises(ValueError):s.diagnose('python',[])

    def test_first_use_failure_is_reported(self):
        with patch.object(s,'diagnose',return_value=self.good),patch.object(s,'execute',return_value={'ok':False,'error':'smoke failed'}):result=self.quiet(self.root)
        self.assertFalse(result['passed']);self.assertTrue(Path(result['setup_report']).is_file())

    def test_windows_managed_path_layout(self):
        self.assertEqual(s.interpreter(Path('user data'),'Windows'),Path('user data/Scripts/python.exe'))

    def test_windows_local_appdata_preferred(self):
        self.assertEqual(s.default_data_dir('Windows',{'LOCALAPPDATA':'User App Data'},'HOME'),Path('User App Data/image-to-3d'))

    def test_mac_managed_default_does_not_write_inside_skill(self):
        self.assertEqual(s.default_data_dir('Darwin',{},'/home/user'),Path('/home/user/.local/share/image-to-3d'))

    @unittest.skipUnless(platform.system() == 'Darwin','macOS launcher execution only')
    def test_real_readonly_launcher_with_explicit_python(self):
        env=dict(os.environ,IMAGE_TO_3D_PYTHON=sys.executable,PYTHONDONTWRITEBYTECODE='1')
        p=subprocess.run(['/bin/bash',str(s.CORE/'install.command'),'--check-only','--data-dir',str(self.root)],capture_output=True,text=True,env=env)
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue(json.loads(p.stdout)['passed']);self.assertFalse(self.root.exists())

    @unittest.skipUnless(platform.system() == 'Darwin','macOS launcher execution only')
    def test_mac_launcher_forwards_paths_with_spaces(self):
        program=Path(self.tmp.name)/'fake python with spaces';program.write_text('#!/bin/bash\nif [[ "$2" == "-c" ]]; then exit 0; fi\nprintf "%s\\n" "$@"\n');program.chmod(0o755)
        p=subprocess.run(['/bin/bash',str(s.CORE/'install.command'),'--data-dir',str(self.root),'--capability','automation'],env=dict(os.environ,IMAGE_TO_3D_PYTHON=str(program)),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn(str(self.root),p.stdout.splitlines());self.assertIn('--capability',p.stdout.splitlines())

    @unittest.skipUnless(platform.system() == 'Darwin','macOS launcher execution only')
    def test_invalid_explicit_python_does_not_bootstrap(self):
        p=subprocess.run(['/bin/bash',str(s.CORE/'install.command'),'--data-dir',str(self.root)],env=dict(os.environ,IMAGE_TO_3D_PYTHON=str(self.root/'missing')),capture_output=True,text=True)
        self.assertEqual(p.returncode,2);self.assertFalse(self.root.exists())

    def test_real_first_use_with_current_environment_no_install(self):
        result=self.quiet(self.root)
        self.assertTrue(result['passed'],result);self.assertTrue(Path(result['first_use_report']).is_file());self.assertNotIn('installation_steps',result);self.assertFalse((self.root/'venv').exists())


if __name__=='__main__':unittest.main()
