import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from scene_build import build,emit_js,landmark,resolve,rotate,geometry
from mesh_checks import mesh_report


def fixture():
    return {'schema_version':1,'coordinate_system':{'unit':'m','up':'y','forward':'z'},'parameters':{'w':{'value':2,'min':1,'max':3}},
            'materials':{'paint':{'color':'#cccccc','roughness':.4,'metalness':.5}},
            'components':[{'id':'body','parent':None,'role':'body','position':[1,0,0],'rotation':[0,0,0],'material':'paint','geometry':{'type':'box','size':[{'param':'w'},1,1]}},
                          {'id':'door','parent':'body','role':'door','position':[1,0,0],'rotation':[0,0,0],'material':'paint','geometry':{'type':'box','size':[1,1,.1]}}],
            'actions':[{'id':'open-door','component_id':'door','axis':'y','angle':math.pi/2,'pivot':[.5,0,0]}]}

class SceneBuild(unittest.TestCase):
    def test_parameter_resolution(self):self.assertEqual(build(fixture())['components'][0]['meshes'][0]['positions'][0],1)
    def test_symmetric_parameter_control_points(self):
        params={'width':{'value':2,'min':1,'max':4}}
        control=[{'param':'width','scale':-.5,'offset':0},{'param':'width','scale':.5,'offset':0}]
        self.assertEqual(resolve(control,params),[-1,1])
        params['width']['value']=3
        self.assertEqual(resolve(control,params),[-1.5,1.5])
        self.assertEqual(resolve({'param':'width','offset':1},params),4)
    def test_invalid_parameter_reference_options(self):
        params={'w':{'value':2,'min':1,'max':3}}
        for ref in ({'param':'w','expression':'bad'}, {'param':'w','scale':float('nan')}, {'param':'w','offset':float('inf')}, {'param':'w','scale':True}):
            with self.assertRaises(ValueError):resolve(ref,params)
    def test_landmark_parent_transform(self):
        s=fixture();s['components'][0]['rotation']=[0,0,math.pi/2]
        p=landmark(s,{'component_id':'door','local_point':[1,0,0]})
        self.assertAlmostEqual(p[0],1);self.assertAlmostEqual(p[1],2)
    def test_mesh_vertex_binding(self):
        s=fixture();s['components'][0]['geometry']={'type':'mesh','positions':[0,0,0,1,0,0,0,1,0],'triangles':[0,1,2]}
        self.assertEqual(landmark(s,{'component_id':'body','vertex_index':1}),[2,0,0]);build(s)
    def test_all_geometry_types(self):
        for g in [{'type':'sphere','radius':1},{'type':'cylinder','radiusTop':.5,'radiusBottom':1,'height':2},{'type':'lathe','profile':[[.5,0],[1,1],[.5,2]],'closed':True}]:
            s=fixture();s['components'][0]['geometry']=g;self.assertGreater(len(build(s)['components'][0]['meshes'][0]['indices']),20)
    def test_bezier_binding(self):
        net=json.loads((Path(__file__).parents[1]/'examples/bezier-network-example.json').read_text());s=fixture();s['components'][0]['geometry']={'type':'bezier_network','network':net}
        self.assertEqual(len(build(s)['components'][0]['meshes']),2)
        p=landmark(s,{'component_id':'body','patch_id':'left','uv':[0,0]});self.assertEqual(p,[1,0,0])
    def test_sphere_is_index_closed(self):
        mesh=geometry({'type':'sphere','radius':1})[0]
        report=mesh_report({'id':'sphere','contract':'closed_shell','positions':mesh['positions'],'triangles':mesh['indices']})
        self.assertTrue(report['passed']);self.assertEqual(report['boundary_edges'],[])
    def test_generator_diagnostic_topology_closes(self):
        for g in ({'type':'box','size':[1,1,1]}, {'type':'cylinder','radiusTop':1,'radiusBottom':1,'height':1}, {'type':'lathe','profile':[[1,0],[.8,1]],'closed':True}):
            s=fixture();s['components'][0]['geometry']=g;s['components'][0]['topology_contract']='closed_shell'
            mesh=build(s)['components'][0]['meshes'][0]
            self.assertTrue(mesh['topology_report']['passed'])
            self.assertEqual(mesh['topology_mesh']['policy'],'generator_seam_weld')
            self.assertEqual(mesh['topology_mesh']['tolerance'],0)
            self.assertLess(len(mesh['topology_mesh']['positions']),len(mesh['positions']))
    def test_user_mesh_missing_face_rejected(self):
        s=fixture();s['components'][0]['geometry']={'type':'mesh','positions':[0,0,0,1,0,0,0,1,0,0,0,1], 'triangles':[0,2,1,0,1,3,0,3,2]}
        s['components'][0]['topology_contract']='closed_shell'
        with self.assertRaisesRegex(ValueError,'topology contract failed'):build(s)
        s['components'][0]['topology_contract']='open_patch'
        mesh=build(s)['components'][0]['meshes'][0]
        self.assertEqual(mesh['topology_mesh']['policy'],'preserve_indices')
        self.assertEqual(mesh['topology_mesh']['triangles'],s['components'][0]['geometry']['triangles'])
    def test_open_lathe_cannot_claim_closed(self):
        s=fixture();s['components'][0]['geometry']={'type':'lathe','profile':[[1,0],[1,1]],'closed':False};s['components'][0]['topology_contract']='closed_shell'
        with self.assertRaisesRegex(ValueError,'topology contract failed'):build(s)
    def test_unknown_geometry(self):
        s=fixture();s['components'][0]['geometry']={'type':'mystery'}
        with self.assertRaises(ValueError):build(s)
    def test_invalid_mesh_rejected(self):
        s=fixture();s['components'][0]['geometry']={'type':'mesh','positions':[0,0,0,0,0,0,0,0,0],'triangles':[0,1,2]}
        with self.assertRaises(ValueError):build(s)
    def test_missing_vehicle_bindings(self):
        s=fixture();s['vehicle_bindings']={}
        with self.assertRaises(ValueError):build(s)
    def test_cycle(self):
        s=fixture();s['components'][0]['parent']='door'
        with self.assertRaises(ValueError):build(s)
    def test_vehicle_runtime_bindings(self):
        vendor=Path(__file__).resolve().parents[1]/'assets/vendor/three.module.js'
        self.assertTrue(vendor.is_file(),'bundled Three vendor required for runtime tests')
        s=fixture();s['materials']['paint2']={'color':'#dddddd','roughness':.3,'metalness':.5}
        for i in range(3):
            key='light'+str(i);s['materials'][key]={'color':'#ffffff','emissive':'#ffffff','emissiveIntensity':1}
            s['components'].append({'id':key,'parent':'body','material':key,'geometry':{'type':'sphere','radius':.05}})
            s['components'].append({'id':'wheel'+str(i),'parent':'body','material':'paint2','geometry':{'type':'cylinder','radiusTop':.3,'radiusBottom':.3,'height':.2}})
        for key in ('right','hood','trunk'):
            s['components'].append({'id':key,'parent':'body','material':'paint','geometry':{'type':'box','size':[.1,.2,.3]}})
            s['actions'].append({'id':key,'component_id':key,'axis':'y','angle':1,'pivot':[0,0,0]})
        s['vehicle_bindings']={'paint':['paint','paint2'],'lights':['light0','light1','light2'],'wheels':[['wheel0'],['wheel1'],['wheel2']],
            'actions':{'left':['open-door'],'right':['right'],'hood':['hood'],'trunk':['trunk']}}
        with tempfile.TemporaryDirectory() as d:
            m=Path(d)/'model.mjs';m.write_text(emit_js(build(s)).replace("from 'three'",'from '+json.dumps(vendor.as_uri())))
            p=Path(d)/'test.mjs';p.write_text("""import {buildVehicle,buildScene} from './model.mjs';import assert from 'node:assert/strict';
const generic=buildScene();assert(generic.nodes.wheel0.visible);assert(!generic.nodes.wheel1.visible);assert(!generic.nodes.wheel2.visible);generic.setWheel(1);assert(generic.nodes.wheel1.visible);assert(!generic.nodes.wheel0.visible);
const c=buildVehicle();c.parts.hood.target=1;c.animate(-.001);assert.equal(c.parts.hood.value,0);assert.throws(()=>c.animate(NaN));assert.throws(()=>generic.animate(-.001));assert(c.nodes.wheel0.visible);assert(!c.nodes.wheel1.visible);c.paint.color.set('#ff0000');assert.equal(c.materials.paint.color.getHex(),0xff0000);assert.equal(c.materials.paint2.color.getHex(),0xff0000);
c.setWheel(2);assert(!c.nodes.wheel0.visible);assert(c.nodes.wheel2.visible);c.lights[0].emissiveIntensity=4;assert.equal(c.materials.light0.emissiveIntensity,4);
c.parts.hood.target=1;c.animate(.1);assert(c.parts.hood.value>0);JSON.stringify(c.root.toJSON());""")
            r=subprocess.run(['node',str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
    def test_runtime_pivot_and_three(self):
        vendor=Path(__file__).resolve().parents[1]/'assets/vendor/three.module.js'
        self.assertTrue(vendor.is_file(),'bundled Three vendor required for runtime tests')
        with tempfile.TemporaryDirectory() as d:
            model=Path(d)/'model.mjs';model.write_text(emit_js(build(fixture())).replace("from 'three'",'from '+json.dumps(vendor.as_uri())))
            script="""import {buildScene} from './model.mjs';import assert from 'node:assert/strict';
const s=buildScene();s.root.updateMatrixWorld(true);const door=s.nodes.door;const V=door.position.constructor;
let closed=door.getWorldPosition(new V());assert(Math.abs(closed.x-2)<1e-8);
s.setAction('open-door',1,{immediate:true});let opened=door.getWorldPosition(new V());assert(Math.abs(opened.x-1.5)<1e-8);assert(Math.abs(opened.z+.5)<1e-8);
s.setAction('open-door',0,{immediate:true});assert(door.getWorldPosition(new V()).distanceTo(closed)<1e-8);
assert(s.root.children.length===1);console.log('pivot and closure passed');"""
            test=Path(d)/'test.mjs';test.write_text(script);r=subprocess.run(['node',str(test)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
