"""Interactive core setup + existing doctor/first-use. No optional installer."""
import sys
sys.dont_write_bytecode = True
import argparse
import json
import os
from pathlib import Path
import platform
import uuid
import environment as envcheck

CORE = Path(__file__).resolve().parents[1]
REQUIREMENTS = {'PIL':'Pillow>=9','numpy':'numpy>=1.24'}


def default_data_dir(system=None, environ=None, home=None):
    system = system or platform.system()
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    return (Path(environ.get('LOCALAPPDATA', home/'AppData/Local'))/'image-to-3d'
            if system == 'Windows' else home/'.local/share/image-to-3d')


def interpreter(directory, system=None):
    return Path(directory)/('Scripts/python.exe' if (system or platform.system()) == 'Windows' else 'bin/python')


def arguments(capabilities=(), **tools):
    result = []
    for capability in capabilities:
        if capability not in ['automation','blender']:raise ValueError('Unknown optional capability')
        result += ['--capability', capability]
    for name in ['node','playwright_module','browser','blender']:
        if tools.get(name):result += ['--'+name.replace('_','-'),str(tools[name])]
    return result


def execute(command, timeout=60):
    return envcheck.run([str(x) for x in command], timeout=timeout)


def diagnose(python, flags):
    result = execute([python,'-B','-X','utf8',CORE/'scripts/environment.py','doctor',*flags])
    try:
        data = json.loads(result.get('stdout',''))
        if not isinstance(data,dict) or 'core_ready' not in data:raise ValueError('invalid doctor report')
        return data
    except (ValueError,TypeError) as error:
        raise ValueError('Environment diagnosis failed: '+str(result)) from error


def approve(plan):
    print('Required dependency installation plan:')
    print(json.dumps(plan,ensure_ascii=True,indent=2))
    print('Only the named managed environment is changed. No global pip/PATH changes.')
    if not sys.stdin.isatty():
        print('No interactive terminal: installation was not approved. Run in a terminal.')
        return False
    try:return input('Type INSTALL to proceed; Enter cancels: ').strip() == 'INSTALL'
    except EOFError:return False


def setup(data_dir=None, check_only=False, capabilities=(), **tools):
    root = Path(data_dir or default_data_dir()).expanduser().resolve()
    if root == CORE or root.is_relative_to(CORE):raise ValueError('Data directory must be outside the installed Skill')
    venv = root/'venv';marker = root/'environment-owner.json';python = Path(sys.executable)
    if venv.is_symlink() or marker.is_symlink():raise ValueError('Refusing a linked managed environment or marker')
    if marker.exists():
        try:owner = json.loads(marker.read_text(encoding='utf-8'))
        except (ValueError,OSError) as error:raise ValueError('Invalid environment ownership marker') from error
        if owner.get('skill') != 'image-to-3d' or owner.get('venv') != str(venv):raise ValueError('Environment ownership mismatch')
    elif venv.exists():raise ValueError('Existing unowned venv: choose another --data-dir; nothing was overwritten')
    if venv.exists():
        python = interpreter(venv)
        if not python.is_file():raise ValueError('Managed venv is incomplete; preserve it and choose another --data-dir')
    flags = arguments(capabilities, **tools)
    diagnostic = diagnose(python, flags)
    report = {'operation':'check-only' if check_only else 'setup','passed':False,
              'python':str(python),'data_dir':str(root),'environment':diagnostic,
              'optional_installation':False,'changes':[],
              'platform_limit':'Windows launchers have no real-machine execution evidence unless independently recorded.'}
    if check_only:
        report['passed'] = diagnostic['passed'];return report
    if not diagnostic.get('package',{}).get('complete') or not diagnostic.get('python',{}).get('meets_minimum'):
        report['error'] = 'Incomplete Skill or unsupported Python; no library installation attempted'
        return report
    if not diagnostic['core_ready']:
        packages = ([requirement for name,requirement in REQUIREMENTS.items()
                     if not diagnostic['libraries'].get(name,{}).get('meets_minimum')]
                    if venv.exists() else list(REQUIREMENTS.values()))
        target = interpreter(venv)
        commands = ([] if venv.exists() else [[sys.executable,'-B','-X','utf8','-m','venv',str(venv)]])
        commands += [[str(target),'-B','-X','utf8','-m','pip','--isolated','install',
                      '--only-binary=:all:','--no-cache-dir','--disable-pip-version-check','--index-url','https://pypi.org/simple',*packages]]
        plan = {'source':'https://pypi.org/simple','packages':packages,'environment':str(venv),
                'new_environment':not venv.exists(),'commands':commands,
                'note':'A new isolated venv needs both core libraries even if one exists in system Python. '
                       'No Node/Playwright/Blender installation. Failed partial files are retained.'}
        if not approve(plan):
            report['error'] = 'Installation declined; no files or dependencies changed';return report
        root.mkdir(parents=True,exist_ok=True)
        if not marker.exists():
            with marker.open('x',encoding='utf-8') as stream:json.dump({'skill':'image-to-3d','venv':str(venv)},stream)
            report['changes'].append(str(marker))
        for command in commands:
            print('Running: '+json.dumps(command,ensure_ascii=True),flush=True)
            result = execute(command, timeout=300)
            report.setdefault('installation_steps',[]).append({'command':command,'result':result})
            if not result['ok']:
                report['error'] = 'Installation failed; partial managed environment retained. No automatic retry/elevation.'
                with (root/('setup-failure-'+uuid.uuid4().hex+'.json')).open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
                return report
        python = target;report['python'] = str(python);report['changes'].append(str(venv))
        diagnostic = diagnose(python,flags);report['environment'] = diagnostic
    if not diagnostic['passed']:
        report['error'] = ('Core requirements remain unavailable after installation; preserve the failure and choose a supported interpreter.'
                           if not diagnostic['core_ready'] else
                           'Requested capability unavailable. Optional tools were not installed; core readiness is reported separately.')
        return report
    root.mkdir(parents=True,exist_ok=True)
    out = root/('first-use-'+uuid.uuid4().hex)
    print('First-use output: '+str(out),flush=True)
    result = execute([python,'-B','-X','utf8',CORE/'scripts/environment.py','first-use','--out',out,*flags],timeout=300)
    first_report = out/'first-use-report.json'
    if first_report.is_file():
        first = json.loads(first_report.read_text(encoding='utf-8'))
        report['passed'] = bool(result['ok'] and first.get('passed'))
        report['first_use_report'] = str(first_report)
        report['changes'].append(str(out))
    else:
        report['error'] = 'First-use failed before creating its report'
    if not report['passed']:report['process'] = result
    report['host_skill_loading'] = 'Agent discovery must be confirmed separately; synthetic smoke is not visual fidelity certification.'
    # Keep failure/success receipts outside the installed Skill, never overwrite.
    receipt = (out if out.is_dir() else root)/('setup-report-'+uuid.uuid4().hex+'.json')
    with receipt.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=True,indent=2)
    report['setup_report'] = str(receipt)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--capability',action='append',default=[],choices=['automation','blender'])
    for name in ['node','playwright-module','browser','blender']:parser.add_argument('--'+name)
    args = parser.parse_args(argv)
    try:
        result = setup(args.data_dir,args.check_only,args.capability,node=args.node,
                       playwright_module=args.playwright_module,browser=args.browser,blender=args.blender)
    except (OSError,ValueError,KeyError) as error:result={'passed':False,'error':str(error)}
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
