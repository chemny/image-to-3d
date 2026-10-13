"""Synthetic software tests; no image reconstruction or fidelity acceptance."""
import os
import functools
import http.server
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scene_build import build, emit_js
from asset_contract import validate

NAMES = ('car-wheel', 'bicycle', 'motorcycle', 'toy')
# Run identical behavioral assertions in Node and in a real browser module.
CHECKS = r'''
export async function check(THREE, buildScene, data, name) {
  let checks=0;
  const ok=(value,message)=>{checks++;if(!value)throw Error(name+': '+message);};
  const near=(a,b,message)=>ok(a.length===b.length&&a.every((x,i)=>Math.abs(x-b[i])<1e-8),message);
  const scene=buildScene();await scene.ready;
  const mesh=id=>scene.nodes[id].children.find(o=>o.isMesh);
  const world=()=>{scene.root.updateMatrixWorld(true);return Object.fromEntries(Object.entries(scene.nodes).map(([id,n])=>[id,n.matrixWorld.elements.slice()]));};
  const initial=world();
  const visible=id=>{let n=scene.nodes[id];while(n){if(!n.visible)return false;n=n.parent;}return true;};
  for(const c of data.components) {
    ok(scene.nodes[c.id].userData.component_id===c.id,'stable component ID');
    if(c.kind==='assembly')ok(!mesh(c.id),'assembly must contain no own mesh');
    else {
      ok(scene.getPart(mesh(c.id))===(visible(c.id)?c.id:null),'clicked mesh resolves nearest selectable part '+c.id);
      const target=mesh(c.id),g=target.geometry;
      const a=new THREE.Vector3().fromBufferAttribute(g.attributes.position,g.index.getX(0));
      const b=new THREE.Vector3().fromBufferAttribute(g.attributes.position,g.index.getX(1));
      const d=new THREE.Vector3().fromBufferAttribute(g.attributes.position,g.index.getX(2));
      const point=a.clone().add(b).add(d).multiplyScalar(1/3);
      const normal=b.clone().sub(a).cross(d.clone().sub(a)).normalize();
      const origin=point.clone().addScaledVector(normal,.02).applyMatrix4(target.matrixWorld);
      const direction=point.applyMatrix4(target.matrixWorld).sub(origin).normalize();
      const hits=new THREE.Raycaster(origin,direction).intersectObject(target,false);
      ok(hits.length>0&&scene.getPart(hits[0].object)===(visible(c.id)?c.id:null),'raycast hit resolves clicked part '+c.id);
      ok(scene.select(c.id).id===c.id,'selection '+c.id);
      for(const m of c.meshes) {
        ok(m.positions.length===m.normals.length,'normal vertex count');
        if(m.uvs)ok(m.uvs.length===m.positions.length/3*2,'UV vertex count');
      }
    }
  }
  // A material shared by multiple parts must be cloned for scoped color edits.
  const editable=data.components.find(c=>c.kind==='part'&&data.components.some(other=>other.id!==c.id&&other.material===c.material));
  const colors=Object.fromEntries(data.components.filter(c=>c.kind==='part').map(c=>[c.id,mesh(c.id).material.color.getHexString()]));
  scene.setColor(editable.id,'#123456');
  ok(mesh(editable.id).material.color.getHexString()==='123456','target recolor');
  for(const [id,color] of Object.entries(colors))if(id!==editable.id)ok(mesh(id).material.color.getHexString()===color,'color isolated from '+id);
  ok(scene.materials[editable.material].color.getHexString()===colors[editable.id],'shared material unchanged');
  scene.setMaterial(editable.id,'accent');
  ok(mesh(editable.id).material===scene.materials.accent,'named material slot assigned');
  for(const [id,color] of Object.entries(colors))if(id!==editable.id)ok(mesh(id).material.color.getHexString()===color,'slot isolated from '+id);
  for(const variant of data.variants) {
    const subtree=root=>data.components.filter(c=>{let n=scene.nodes[c.id];while(n){if(n===scene.nodes[root])return true;n=n.parent;}return false;});
    for(const option of Object.keys(variant.options)) {
      scene.setVariant(variant.id,option);
      for(const [key,roots] of Object.entries(variant.options))for(const root of roots)for(const c of subtree(root))ok(visible(c.id)===(key===option),'variant effective subtree visibility '+c.id);
      if(name==='car-wheel') {
        ok(visible('tyre')&&visible('hub'),'rim replacement retains tyre and hub');
        near(world().tyre,initial.tyre,'rim replacement retains tyre transform');
      }
    }
  }
  scene.reset();
  scene.explode(1);const exploded=world();
  ok(data.components.some(c=>c.explode_vector.some(Boolean)&&exploded[c.id].some((x,i)=>Math.abs(x-initial[c.id][i])>1e-8)),'explode moves an actual world transform');
  scene.explode(0);
  for(const [id,m] of Object.entries(world()))near(m,initial[id],'explode zero restores '+id);
  for(const action of data.actions) {
    scene.reset();const def=data.components.find(c=>c.id===action.component_id);
    scene.setAction(action.id,1,{immediate:true});
    ok(Math.abs(scene.parts[action.id].group.rotation[action.axis]-action.angle)<1e-10,'action endpoint rotation');
    const parent=def.parent?scene.nodes[def.parent]:scene.root;
    parent.updateWorldMatrix(true,false);
    const axis={x:new THREE.Vector3(1,0,0),y:new THREE.Vector3(0,1,0),z:new THREE.Vector3(0,0,1)}[action.axis];
    const p=new THREE.Vector3(...action.pivot);
    const expected=new THREE.Vector3(...def.position).sub(p).applyAxisAngle(axis,action.angle).add(p).applyMatrix4(parent.matrixWorld);
    scene.root.updateMatrixWorld(true);
    near(scene.nodes[def.id].getWorldPosition(new THREE.Vector3()).toArray(),expected.toArray(),'action pivot world endpoint');
    if(name==='toy') {
      near(world().body,initial.body,'toy body fixed during arm hinge');
      ok(world().hand.some((x,i)=>Math.abs(x-initial.hand[i])>1e-8),'hand follows arm hinge');
    }
    scene.explode(1);scene.reset();
    for(const [id,m] of Object.entries(world()))near(m,initial[id],'combined action/explode reset '+id);
    scene.setAction(action.id,1);for(let i=0;i<180;i++)scene.animate(1/60);
    ok(scene.snapshot().actions[action.id]===1,'animated endpoint converges exactly');
    scene.setAction(action.id,0,{immediate:true});
  }
  scene.reset();
  const snap=scene.snapshot();ok(snap.explode===0&&snap.selected===null,'reset state');
  for(const [id,color] of Object.entries(colors))ok(mesh(id).material.color.getHexString()===color,'reset material '+id);
  for(const v of data.variants)ok(snap.variants[v.id]===v.default,'reset variant');
  return {name,checks,components:data.components.length,scene};
}
'''


class AssetRuntime(unittest.TestCase):
    def write_modules(self, directory, browser=False):
        vendor = ROOT / 'assets/vendor/three.module.js'
        target = './vendor/three.module.js' if browser else vendor.as_uri()
        if browser:
            (directory / 'vendor').symlink_to(vendor.parent, target_is_directory=True)
        imports = [f"import * as THREE from {json.dumps(target)};", "import {check} from './checks.mjs';"]
        runs = []
        for i, name in enumerate(NAMES):
            spec = json.loads((ROOT / 'examples/assets' / (name + '.json')).read_text())
            payload = build(spec)
            (directory / (name + '.mjs')).write_text(emit_js(payload).replace("from 'three'", 'from ' + json.dumps(target)))
            imports.append(f"import {{buildScene as build{i}}} from './{name}.mjs';")
            runs.append(f"results.push(await check(THREE,build{i},{json.dumps(payload)},'{name}'));")
        (directory / 'checks.mjs').write_text(CHECKS)
        return '\n'.join(imports) + '\nconst results=[];\n' + '\n'.join(runs)

    def test_fixture_scope_and_contract(self):
        for name in NAMES:
            with self.subTest(asset=name):
                spec = json.loads((ROOT / 'examples/assets' / (name + '.json')).read_text())
                self.assertEqual(spec['quality_contract']['scope'], 'synthetic-software-test')
                self.assertIn('DEVELOPMENT fixture', spec['asset_contract']['source_notes'])
                self.assertTrue(all(m['source']['kind'] == 'designed' for m in spec['materials'].values()))
                self.assertTrue(validate(spec)['passed'])
                payload = build(spec)
                self.assertEqual(len(payload['components']), len(spec['components']))
                for c in payload['components']:
                    if c['kind'] == 'part':
                        self.assertTrue(c['meshes'])

    @unittest.skipUnless(shutil.which('node'), 'Node is unavailable; runtime checks not executed')
    def test_node_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            script = self.write_modules(directory)
            script += "\nconsole.log(JSON.stringify(results.map(({scene,...report})=>report)));\n"
            (directory / 'test.mjs').write_text(script)
            result = subprocess.run(['node', str(directory / 'test.mjs')], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            reports = json.loads(result.stdout)
            self.assertEqual(len(reports), len(NAMES))
            self.assertTrue(all(r['checks'] > 30 for r in reports))
            print('Node asset runtime:', result.stdout.strip())

    def test_browser_runtime(self):
        chrome = next((p for p in [os.environ.get('CHROME_EXECUTABLE'), shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')] if p and Path(p).exists()), None)
        if not chrome:
            self.skipTest('Chrome unavailable; browser runtime and WebGL not executed')
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            script = self.write_modules(directory, browser=True)
            script += r'''
const renderer=new THREE.WebGLRenderer({antialias:false});renderer.setSize(128,128);
const camera=new THREE.PerspectiveCamera(45,1,.01,100);camera.position.set(4,3,5);camera.lookAt(0,1,0);
for(const {scene} of results){const stage=new THREE.Scene();stage.add(scene.root,new THREE.HemisphereLight(0xffffff,0x444444,3));renderer.render(stage,camera);}
if(renderer.info.render.calls===0)throw Error('No draw calls');
document.body.textContent='ASSET_RUNTIME_PASS '+JSON.stringify(results.map(({scene,...report})=>report));renderer.dispose();
'''
            # Keep module imports top-level and expose any asynchronous assertion error in DOM.
            lines = script.splitlines()
            import_lines = [line for line in lines if line.startswith('import ')]
            body = [line for line in lines if not line.startswith('import ')]
            (directory / 'browser.mjs').write_text('\n'.join(import_lines) + '\ntry {\n' + '\n'.join(body) + "\n} catch(error) {document.body.textContent='ASSET_RUNTIME_FAIL '+error.stack;}\n")
            (directory / 'index.html').write_text('<!doctype html><body>RUNNING<script type="module" src="browser.mjs"></script></body>')
            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *args):
                    pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=temp))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                # Some macOS Chrome builds print DOM then keep background processes alive.
                # Observe the explicit browser result, then close our own temporary instance.
                with (directory / 'chrome.out').open('w') as stdout, (directory / 'chrome.err').open('w') as stderr:
                    process = subprocess.Popen([chrome, '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--user-data-dir=' + str(directory / 'profile'), '--timeout=10000', '--dump-dom', f'http://127.0.0.1:{server.server_port}/index.html'], stdout=stdout, stderr=stderr)
                    try:
                        deadline = time.monotonic() + 30
                        while time.monotonic() < deadline:
                            output = (directory / 'chrome.out').read_text()
                            if 'ASSET_RUNTIME_PASS' in output or 'ASSET_RUNTIME_FAIL' in output or process.poll() is not None:
                                break
                            time.sleep(.1)
                        errors = (directory / 'chrome.err').read_text()
                        self.assertIn('ASSET_RUNTIME_PASS', output, output + errors[-3000:])
                        self.assertNotIn('ASSET_RUNTIME_FAIL', output)
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                print('Browser asset runtime: all four fixtures passed; WebGL draw calls verified.')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
