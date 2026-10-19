import copy
import itertools
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from surface_construction import CubicProfile, compile_surface, periodic_radius
from form_construction import compile_recipe

def recipe(method, parameters):
    return dict(version=1, component_id='sample', source=dict(reference_id='original', roi=[0,0,100,100]), rationale='Authored boundary fixture', method=method, parameters=parameters)

def outline():
    return [[(1+.07*math.cos(3*a))*math.cos(a), (1+.07*math.cos(3*a))*math.sin(a)] for a in [i*math.pi/16 for i in range(32)]]

class SurfaceConstructionTests(unittest.TestCase):
    def test_spline_knots_and_C2(self):
        f=CubicProfile([0,.3,.8,1],[1,1.2,.9,1.1],[0,0])
        for x,y in zip(f.x,f.y):self.assertAlmostEqual(f(x),y)
        self.assertAlmostEqual(f(0,1),0);self.assertAlmostEqual(f(1,1),0)
        for x in f.x[1:-1]:
            for d in (0,1,2):self.assertAlmostEqual(f(x-1e-8,d),f(x+1e-8,d),places=5)
        with self.assertRaises(ValueError):f(-.1)

    def test_between_knot_radius_failure_is_not_hidden_by_sampling(self):
        f=CubicProfile([0,1],[1,1],[-10,10])
        self.assertLess(f.minimum(),0)
        p=dict(sections=[dict(center=[0,y,0],radii=[1,1])for y in [0,1]],end_slopes=[-10,10],max_chord_error=100)
        with self.assertRaisesRegex(ValueError,'overshoots'):compile_surface(recipe('smooth_loft',p))

    def test_nonzero_outline_slope_matches_roll_without_flat_lip(self):
        from surface_quality import inspect_geometry
        p=dict(outline=outline(),rings=[dict(fraction=0,half_thickness=.18),dict(fraction=.75,half_thickness=.13),dict(fraction=1,half_thickness=.05)],edge_width=.045,join_slope=-.4,angular_segments=64,profile_segments=48,edge_segments=24)
        g=compile_surface(recipe('rounded_outline',p))['geometry'];na=64;np=48;start=2+2*np*na
        report=inspect_geometry(g,dict(version=1,topology='closed_shell',profile_checks=[dict(id='join',vertex_indices=[1+(np-2)*na,1+(np-1)*na,start,start+na],max_turn_deg=12)]))
        self.assertTrue(report['passed'],report['errors'])
        with self.assertRaises(ValueError):compile_surface(recipe('rounded_outline',dict(p,join_slope=.1)))

    def test_cli_preserves_files_and_distinct_artifacts(self):
        import subprocess,tempfile
        with tempfile.TemporaryDirectory()as directory:
            d=Path(directory);src=d/'recipe.json';src.write_text(__import__('json').dumps(recipe('rounded_corner',dict(segments=4))))
            script=Path(__file__).resolve().parents[1]/'scripts/surface_construction.py'
            cmd=[sys.executable,str(script),str(src),'--out',str(d/'geometry.json'),'--report',str(d/'geometry.json')]
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertFalse((d/'geometry.json').exists())
            cmd[-1]=str(d/'report.json');self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            original=(d/'geometry.json').read_bytes();self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(original,(d/'geometry.json').read_bytes())

    def test_smooth_loft_closed_rounded_caps(self):
        p=dict(sections=[dict(center=[0,y,0],radii=[r,r*.8]) for y,r in [(0,.7),(.5,.9),(1,.6)]],cap_depths=[.2,.3],max_chord_error=.002)
        result=compile_surface(recipe('smooth_loft',p));self.assertTrue(result['report']['topology']['passed'])
        self.assertEqual(result['report']['contract'],'closed_shell')
        self.assertGreater(result['report']['construction']['sampled_sections'],3)
        self.assertLessEqual(result['report']['construction']['sampled_profile_chord_error'],.002)
        with self.assertRaises(ValueError):compile_surface(recipe('smooth_loft',dict(p,end_slopes=[0,0])))

    def test_outline_shared_closed_roll_and_actual_perimeter(self):
        p=dict(outline=outline(),rings=[dict(fraction=0,half_thickness=.15),dict(fraction=1,half_thickness=.07)],edge_width=.12,angular_segments=64,profile_segments=8,edge_segments=10)
        result=compile_surface(recipe('rounded_outline',p));self.assertTrue(result['report']['topology']['passed'])
        g=result['geometry'];points=list(zip(*[iter(g['positions'])]*3));mid=[q for q in points if abs(q[1])<1e-10]
        self.assertEqual(len(mid),64)
        rad,_,_=periodic_radius(p['outline'])
        for x,y,z in mid:self.assertAlmostEqual(math.hypot(x,z),rad(math.atan2(z,x)))
        # The roll must have interior levels, not a flat vertical closure with smooth shading.
        self.assertGreater(len({round(q[1],6)for q in points if .9<math.hypot(q[0],q[2])<1.1}),10)
        with self.assertRaises(ValueError):compile_surface(recipe('rounded_outline',dict(p,edge_width=2)))

    def test_shape_preserving_periodic_outline(self):
        points=outline();rad,_,_=periodic_radius(points)
        for x,z in points:self.assertAlmostEqual(rad(math.atan2(z,x)),math.hypot(x,z))
        for i in range(100):self.assertAlmostEqual(rad(i*.1),rad(i*.1+2*math.pi))
        with self.assertRaises(ValueError):periodic_radius(list(reversed(points)))

    def test_blend_boundaries_and_derivatives(self):
        p=dict(a=[[0,0,0],[1,0,0]],b=[[0,1,0],[1,1,0]],a_inward=[[0,1,1],[0,1,1]],b_inward=[[0,-1,1],[0,-1,1]],segments=[8,64])
        r=compile_surface(recipe('blend_strip',p));g=r['geometry']['positions'];pt=lambda i,j:g[3*(j*9+i):3*(j*9+i)+3]
        for i in range(9):
            self.assertEqual(pt(i,0),[i/8,0,0]);self.assertEqual(pt(i,64),[i/8,1,0])
        self.assertGreater(pt(4,1)[2],0);self.assertGreater(pt(4,63)[2],0)

    def test_corner_boundary_and_tangent_compatibility(self):
        b=dict(u0=[[0,j/3,0]for j in range(4)],u1=[[1,j/3,0]for j in range(4)],v0=[[i/3,0,0]for i in range(4)],v1=[[i/3,1,0]for i in range(4)])
        d=dict(u0=[[1,0,0]]*4,u1=[[-1,0,0]]*4,v0=[[0,1,0]]*4,v1=[[0,-1,0]]*4)
        p=dict(boundaries=b,cross_derivatives=d,continuity='tangent')
        r=compile_surface(recipe('corner_patch',p));self.assertTrue(r['report']['topology']['passed'])
        self.assertTrue(all(z==0 for z in r['geometry']['positions'][2::3]))
        bad=copy.deepcopy(p);bad['cross_derivatives']['u0'][0][2]=.1
        with self.assertRaises(ValueError):compile_surface(recipe('corner_patch',bad))
        bad=copy.deepcopy(b);bad['v0'][0][2]=.1
        with self.assertRaises(ValueError):compile_surface(recipe('corner_patch',dict(boundaries=bad)))

    def test_octant_triangle_winding_is_outward(self):
        for sign in itertools.product((-1,1),repeat=3):
            r=compile_surface(recipe('rounded_corner',dict(octant=list(sign),segments=8)))
            g=r['geometry'];ps=[g['positions'][i:i+3]for i in range(0,len(g['positions']),3)]
            for k in range(0,len(g['triangles']),3):
                a,b,c=[ps[i]for i in g['triangles'][k:k+3]];u=[b[i]-a[i]for i in range(3)];v=[c[i]-a[i]for i in range(3)];n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                self.assertGreater(sum(n[i]*(a[i]+b[i]+c[i])for i in range(3)),0)

    def test_main_compiler_routes_new_methods(self):
        r=compile_recipe(recipe('rounded_corner',dict(segments=6)))
        self.assertEqual(r['report']['contract'],'open_patch');self.assertFalse(r['report']['visual_accuracy_checked'])

    def test_scene_build_enforces_actual_surface_contract(self):
        from scene_build import build
        from test_scene_build import fixture
        s=fixture();c=s['components'][0]
        c['geometry']=dict(type='mesh',positions=[0,0,0,1,0,0,1,1,0,2,1,0],triangles=[0,1,2,1,3,2])
        c['surface_contract']=dict(version=1,topology='open_patch',profile_checks=[dict(id='edge',vertex_indices=[0,1,2,3],max_turn_deg=30)])
        with self.assertRaisesRegex(ValueError,'surface contract failed'):build(s)
        c['surface_contract']['profile_checks'][0]['max_turn_deg']=100
        self.assertTrue(build(s)['components'][0]['surface_report']['passed'])

if __name__=='__main__':unittest.main()
