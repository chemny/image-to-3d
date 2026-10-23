"""Core-first environment diagnosis and synthetic first-use checks. No installer.

Default diagnosis never installs tools, launches a GUI, writes files or contacts
external sites. First-use writes only a new explicit output directory. Optional
browser/Blender execution requires an explicit --capability selection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import re
import shutil
import struct
import subprocess
import sys

CORE = Path(__file__).resolve().parents[1]


def child_env():
    return dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')


def run(command, timeout=30):
    try:
        p = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout, env=child_env())
        return {'ok':p.returncode == 0, 'returncode':p.returncode,
                'stdout':p.stdout.strip(), 'stderr':p.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'ok':False, 'error':str(e)}


def candidates(system, env):
    """Platform paths only; callers can test Windows discovery on other systems."""
    result = {'browser':[], 'blender':[]}
    if system == 'Darwin':
        result['browser'] = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                             '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
        result['blender'] = ['/Applications/Blender.app/Contents/MacOS/Blender']
    elif system == 'Windows':
        for key in ['PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA']:
            if env.get(key):
                base = PureWindowsPath(env[key])
                result['browser'] += [str(base/'Google/Chrome/Application/chrome.exe'),
                                      str(base/'Microsoft/Edge/Application/msedge.exe')]
        # Blender's versioned installation directory is discovered separately.
    return result


def tools(system=None, env=None, which=None, is_file=None):
    system = system or platform.system();env = os.environ if env is None else env
    which = which or shutil.which;is_file = is_file or (lambda p: Path(p).is_file())
    paths = candidates(system, env)
    def first(items):
        return next((str(p) for p in items if p and is_file(p)), None)
    browser = first([which(x) for x in ['google-chrome','chromium','chrome','msedge']] + paths['browser'])
    blender = first([which('blender')] + paths['blender'])
    if system == 'Windows' and blender is None:
        base = Path(env.get('PROGRAMFILES',''))/'Blender Foundation'
        if env.get('PROGRAMFILES') and base.is_dir():
            blender = first(sorted(base.glob('Blender*/blender.exe')))
    return {'node':which('node'), 'browser':browser, 'blender':blender}


def library_probe():
    # Import into a child with UTF-8/no-bytecode, not into the diagnostic process.
    code = '''import importlib,json
r={}
for name in ['PIL','numpy']:
 try:
  m=importlib.import_module(name);r[name]={'available':True,'version':m.__version__}
 except Exception as e:r[name]={'available':False,'error':str(e)}
print(json.dumps(r))'''
    result = run([sys.executable,'-B','-X','utf8','-c',code])
    if not result['ok']:
        return {n:{'available':False,'error':result.get('error',result.get('stderr'))} for n in ['PIL','numpy']}
    try:
        data = json.loads(result['stdout'])
        for name, minimum in [('PIL',(9,0)),('numpy',(1,24))]:
            item = data[name];match = re.match(r'^(\d+)\.(\d+)',item.get('version',''))
            item['meets_minimum'] = bool(item.get('available') and match and tuple(map(int,match.groups())) >= minimum)
        return data
    except (ValueError, KeyError, TypeError):
        return {n:{'available':False,'error':'invalid library probe'} for n in ['PIL','numpy']}


def playwright_entry(value):
    if not value:return None
    p = Path(value).expanduser().resolve()
    if p.is_file():return str(p)
    if p.is_dir():
        # Use files that the existing capture.mjs can import; never npm install.
        for name in ['index.mjs','index.js']:
            if (p/name).is_file():return str(p/name)
    return None


def package_check():
    required = ['SKILL.md','requirements.txt','install.command','install.cmd','scripts/setup_skill.py','scripts/project.py','scripts/scene_build.py',
                'assets/review-viewer/index.html','assets/review-viewer/review.js',
                'assets/vendor/three.module.js','assets/vendor/three.core.js',
                'examples/assets/toy.json','domains/vehicle/scripts/locked_configurator.py']
    missing = [name for name in required if not (CORE/name).is_file()]
    template = CORE/'domains/vehicle/assets/locked-configurator-v1'
    invalid = []
    try:
        lock = json.loads((template/'template-lock.json').read_text(encoding='utf-8'))
        for name, digest in lock['immutable_files'].items():
            p = template/name
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                invalid.append(name)
    except (OSError, ValueError, KeyError, TypeError):
        invalid.append('template-lock.json')
    return {'complete':not missing and not invalid,'missing':missing,
            'vehicle_template_invalid':invalid,
            'vehicle_module_bundled':not any(n.startswith('domains/') for n in missing) and not invalid}


def doctor(capabilities=(), node=None, playwright_module=None, browser=None, blender=None):
    capabilities = list(dict.fromkeys(capabilities))
    if any(c not in ['automation','blender'] for c in capabilities):raise ValueError('unknown optional capability')
    system = platform.system();found = tools();libs = library_probe();package = package_check()
    core_ready = sys.version_info >= (3,10) and package['complete'] and all(x.get('meets_minimum') for x in libs.values())
    detected = {'node':str(node) if node else found['node'],
                'browser':str(browser) if browser else found['browser'],
                'blender':str(blender) if blender else found['blender']}
    optional = {c:{'requested':c in capabilities,'status':'not_requested','passed':None} for c in ['automation','blender']}
    if 'automation' in capabilities:
        entry = playwright_entry(playwright_module)
        n = detected['node'];nr = run([n,'--version']) if n else {'ok':False,'error':'Node.js not found'}
        version = re.match(r'^v?(\d+)',nr.get('stdout',''))
        nr['meets_minimum'] = bool(nr['ok'] and version and int(version.group(1)) >= 18)
        module = {'ok':False,'error':'Supply --playwright-module with an existing index.mjs or package directory'}
        if n and nr['meets_minimum'] and entry:
            code = "import {pathToFileURL} from 'node:url';const m=await import(pathToFileURL(process.argv[1]).href);if(!m.chromium?.launch)throw Error('chromium.launch unavailable');console.log(JSON.stringify({browser:m.chromium.executablePath()}));"
            module = run([n,'--input-type=module','-e',code,entry])
            if module['ok'] and not browser:
                try:
                    default = json.loads(module['stdout'])['browser']
                    if Path(default).is_file():detected['browser'] = default
                except (ValueError, KeyError):module['ok'] = False
        executable = detected['browser']
        ready = nr['meets_minimum'] and module['ok'] and bool(executable and Path(executable).is_file())
        optional['automation'] = {'requested':True,'status':'dependencies_available_unverified' if ready else 'missing_or_invalid',
                                  'passed':bool(ready),'node_probe':nr,'module_probe':module,'playwright_entry':entry,
                                  'note':'No browser launched; first-use --capability automation verifies actual WebGL capture.'}
    if 'blender' in capabilities:
        path = detected['blender'];probe = run([path,'--version']) if path else {'ok':False,'error':'Blender not found'}
        ready = probe['ok'] and 'Blender' in probe.get('stdout','')
        optional['blender'] = {'requested':True,'status':'dependencies_available_unverified' if ready else 'missing_or_invalid',
                              'passed':bool(ready),'version_probe':probe,'note':'Version check only; no import certified.'}
    return {'schema_version':1,'operation':'doctor','system':system,'python':{'executable':sys.executable,
            'version':platform.python_version(),'meets_minimum':sys.version_info >= (3,10)},
            'libraries':libs,'package':package,'detected_tools':detected,'optional':optional,
            'core_ready':bool(core_ready),'requested_capabilities_ready':all(optional[c]['passed'] for c in capabilities),
            'passed':bool(core_ready and all(optional[c]['passed'] for c in capabilities)),
            'host_skill_loading':'requires Agent confirmation; not proven by this CLI',
            'platform_validation':'This run reports the actual OS only; simulated path tests do not certify another OS.',
            'mutations':[],'installed_dependencies':False}


def first_use(out, capabilities=(), **options):
    out = Path(out).expanduser().resolve()
    if out.exists():raise ValueError('Output exists; choose a new directory')
    if out.is_relative_to(CORE):raise ValueError('First-use output must be outside the installed Skill')
    env = doctor(capabilities, **options)
    if not env['passed']:
        return {'passed':False,'operation':'first-use','environment':env,'output_created':False}
    out.mkdir(parents=True,exist_ok=False)
    report = {'passed':False,'operation':'first-use','environment':env,'output':str(out),
              'scope':'Synthetic software smoke only; no reference fidelity or production adoption.',
              'visual_review':'not_performed','optional':{c:'not_requested' for c in ['automation','blender']}}
    try:
        # Run UTF-8 child so the same command works with Windows legacy locales.
        core_script = r'''
import sys,json,shutil,hashlib,struct
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from PIL import Image
from scene_build import build
from lightweight_delivery import write_runtime,read_payload
from asset_exchange import export_glb
root=Path(sys.argv[1]);out=Path(sys.argv[2]);preview=out/'preview'
Image.new('RGB',(32,32),(64,128,192)).save(out/'synthetic-input.png')
with Image.open(out/'synthetic-input.png') as im:assert im.size==(32,32)
spec=json.loads((root/'examples/assets/toy.json').read_text(encoding='utf-8'));payload=build(spec)
shutil.copytree(root/'assets/review-viewer',preview);shutil.copytree(root/'assets/vendor',preview/'vendor')
write_runtime(preview,payload);assert read_payload(preview)==payload
cameras=payload['cameras'];assert cameras
(preview/'capture-config.json').write_text(json.dumps({'cameras':cameras,'landmarks':[],'connections':[]}),encoding='utf-8')
manifest={'spec_sha256':hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest(),'diagnostic':True,'mode':'installation-smoke','files':{p.relative_to(preview).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in preview.rglob('*') if p.is_file()}}
(preview/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
export_glb(payload,out/'sample.glb',resource_root=root)
raw=(out/'sample.glb').read_bytes();assert struct.unpack_from('<III',raw) == (0x46546c67,2,len(raw))
print(json.dumps({'passed':True,'components':len(payload['components']),'image_roundtrip':True,'lossless_payload_roundtrip':True,'glb_header_valid':True}))
'''
        proc = run([sys.executable,'-B','-X','utf8','-c',core_script,str(CORE),str(out)], timeout=60)
        if not proc['ok']:raise ValueError('core smoke failed: '+str(proc))
        report['core'] = json.loads(proc['stdout'])
        if 'automation' in capabilities:
            tools_ = env['detected_tools'];entry = env['optional']['automation']['playwright_entry']
            command = [tools_['node'],str(CORE/'scripts/capture.mjs'),'--bundle',str(out/'preview'),
                       '--out',str(out/'capture'),'--playwright-module',entry,'--browser',tools_['browser'],
                       '--poses','closed','--modes','beauty']
            result = run(command,timeout=90)
            capture = json.loads((out/'capture/capture-report.json').read_text(encoding='utf-8')) if (out/'capture/capture-report.json').is_file() else {}
            if not result['ok'] or not capture.get('passed') or not capture.get('captures'):raise ValueError('browser capture failed: '+str(result))
            report['optional']['automation'] = 'actual_webgl_capture_passed'
        if 'blender' in capabilities:
            command = [env['detected_tools']['blender'],'--background','--factory-startup','--python-exit-code','1',
                       '--python',str(CORE/'scripts/blender_asset_check.py'),'--','--glb',str(out/'sample.glb'),
                       '--manifest',str(out/'sample.glb.manifest.json'),'--out',str(out/'blender-report.json')]
            result = run(command,timeout=120)
            actual = json.loads((out/'blender-report.json').read_text(encoding='utf-8')) if (out/'blender-report.json').is_file() else {}
            if not result['ok'] or not actual.get('passed') or not actual.get('mesh_count'):raise ValueError('Blender import failed: '+str(result))
            report['optional']['blender'] = 'actual_import_passed'
        report['passed'] = True
        report['manual_preview'] = {'directory':str(out/'preview'),'command':[sys.executable,'-m','http.server','--bind','127.0.0.1','--directory',str(out/'preview')],
                                    'note':'Start manually with an available port; check WebGL, color/action controls in your browser. Does not open a server automatically.'}
    except (OSError, ValueError, KeyError, struct.error) as e:
        report['error'] = str(e)
    with (out/'first-use-report.json').open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=True,indent=2)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['doctor','first-use'])
    parser.add_argument('--out',type=Path)
    parser.add_argument('--capability',action='append',default=[],choices=['automation','blender'])
    for name in ['node','playwright-module','browser','blender']:parser.add_argument('--'+name)
    args = parser.parse_args(argv)
    if args.action=='first-use' and args.out is None:parser.error('first-use requires a new --out directory')
    if args.action=='doctor' and args.out is not None:parser.error('doctor is read-only; use stdout redirection for a report')
    options = {'node':args.node,'playwright_module':args.playwright_module,'browser':args.browser,'blender':args.blender}
    try:
        result = doctor(args.capability,**options) if args.action=='doctor' else first_use(args.out,args.capability,**options)
    except (OSError,ValueError) as e:result={'passed':False,'error':str(e)}
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
