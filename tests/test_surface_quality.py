import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from surface_quality import inspect_geometry


def triangle(points=None):
    return {'type': 'mesh', 'positions': points or [0,0,0, 1,0,0, .5,math.sqrt(3)/2,0],
            'triangles': [0,1,2]}


def contract(**kwargs):
    return dict(version=1, topology='open_patch', **kwargs)


def seam_geometry(gap=0, fold=0):
    # Two disconnected patches meet at their origins. Their authored winding agrees.
    angle = math.radians(fold)
    return {'type': 'mesh', 'positions': [0,0,0, 1,0,0, 0,1,0,
                                        gap,0,0, gap,-math.cos(angle),-math.sin(angle), gap+1,0,0],
            'triangles': [0,1,2, 3,4,5]}


def seam_contract(max_gap=.001, max_angle_deg=1):
    return contract(seam_samples=[{'id': 'join', 'a': [0,1,2], 'b': [3,4,5],
                                  'max_gap': max_gap, 'max_angle_deg': max_angle_deg}])


def profile_geometry(points):
    # A triangulated strip; every profile segment is an actual boundary edge.
    count = len(points)
    all_points = points + [[p[0], p[1], 1] for p in points]
    triangles = []
    for i in range(count-1):
        triangles.extend([i,i+1,count+i, i+1,count+i+1,count+i])
    return {'type': 'mesh', 'positions': [x for p in all_points for x in p], 'triangles': triangles}


class SurfaceQualityTests(unittest.TestCase):
    def test_authored_bounds_reject_added_tip(self):
        c=contract(bounds={'min':[0,0,0],'max':[1,1,0],'tolerance':1e-9})
        self.assertTrue(inspect_geometry(triangle(),c)['passed'])
        g=triangle();g['positions'][7]=1.05
        self.assertFalse(inspect_geometry(g,c)['passed'])
        self.assertIn('geometry exceeds authored bounds',inspect_geometry(g,c)['errors'])

    def test_invalid_bounds_are_not_silently_ignored(self):
        for bounds in ({'min':[0,0,0],'max':[1,1,1]}, {'min':[0,0,0],'max':[-1,1,1],'tolerance':0}, {'min':[0,0,0],'max':[1,1,1],'tolerance':True}):
            self.assertFalse(inspect_geometry(triangle(),contract(bounds=bounds))['passed'])
    def test_equilateral_quality_and_scope(self):
        report = inspect_geometry(triangle(), contract(min_triangle_quality=.99))
        self.assertTrue(report['passed'], report['errors'])
        self.assertAlmostEqual(report['metrics']['triangle_quality']['minimum'], 1)
        self.assertFalse(report['checks']['global_G2_certified'])
        self.assertFalse(report['checks']['global_self_intersection_checked'])
        self.assertEqual(report['basis']['curvature_unit'], 'inverse input coordinate unit')

    def test_closed_tetrahedron(self):
        geometry = {'type': 'mesh', 'positions': [0,0,0, 1,0,0, 0,1,0, 0,0,1],
                    'triangles': [0,2,1, 0,1,3, 0,3,2, 1,2,3]}
        report = inspect_geometry(geometry, {'version': 1, 'topology': 'closed_shell'})
        self.assertTrue(report['passed'], report['errors'])
        geometry['triangles'] = geometry['triangles'][:-3]
        self.assertIn('topology: closed shell has boundary edges',
                      inspect_geometry(geometry, {'version': 1, 'topology': 'closed_shell'})['errors'])

    def test_winding_and_nonmanifold_rejected(self):
        geometry = {'type': 'mesh', 'positions': [0,0,0, 1,0,0, 0,1,0, 1,1,0],
                    'triangles': [0,1,2, 1,2,3]}
        self.assertIn('topology: inconsistent adjacent winding', inspect_geometry(geometry, contract())['errors'])
        geometry['triangles'].extend([2,1,0])
        self.assertIn('topology: nonmanifold edges', inspect_geometry(geometry, contract())['errors'])

    def test_sliver_bound_not_universal(self):
        geometry = triangle([0,0,0, 1,0,0, .5,.00001,0])
        self.assertTrue(inspect_geometry(geometry, contract())['passed'])
        report = inspect_geometry(geometry, contract(min_triangle_quality=.1))
        self.assertFalse(report['passed'])
        self.assertEqual(report['metrics']['triangle_quality']['failed_triangle_indices'], [0])

    def test_degenerate_and_invalid_geometry(self):
        for geometry in (triangle([0,0,0, 1,0,0, 2,0,0]),
                         {'type': 'mesh', 'positions': [], 'triangles': []},
                         {'type': 'box', 'positions': [0]*9, 'triangles': [0,1,2]},
                         {'type': 'mesh', 'positions': [0,0,0, 1,0,0, 0,float('nan'),0], 'triangles': [0,1,2]},
                         {'type': 'mesh', 'positions': [0,0,0, 1,0,0, 0,1,0], 'triangles': [0,1,True]}):
            with self.subTest(geometry=geometry):
                self.assertFalse(inspect_geometry(geometry, contract())['passed'])

    def test_unused_vertex_rejected(self):
        geometry = triangle(); geometry['positions'].extend([2,2,2])
        self.assertFalse(inspect_geometry(geometry, contract())['passed'])

    def test_seam_flat_gap_and_fold(self):
        report = inspect_geometry(seam_geometry(), seam_contract())
        self.assertTrue(report['passed'], report['errors'])
        self.assertEqual(report['metrics']['seam_samples'][0]['angle_deg'], 0)
        gap = inspect_geometry(seam_geometry(gap=.1), seam_contract())
        self.assertFalse(gap['passed'])
        self.assertAlmostEqual(gap['metrics']['seam_samples'][0]['gap'], .1)
        fold = inspect_geometry(seam_geometry(fold=35), seam_contract())
        self.assertFalse(fold['passed'])
        self.assertAlmostEqual(fold['metrics']['seam_samples'][0]['angle_deg'], 35)

    def test_shading_normals_cannot_hide_fold(self):
        geometry = seam_geometry(fold=60)
        geometry['normals'] = [0,0,1]*6
        report = inspect_geometry(geometry, seam_contract())
        self.assertFalse(report['passed'])
        self.assertAlmostEqual(report['metrics']['seam_samples'][0]['angle_deg'], 60)

    def test_seam_order_uses_actual_triangle_winding(self):
        controls = seam_contract(); controls['seam_samples'][0]['b'] = [3,5,4]
        self.assertTrue(inspect_geometry(seam_geometry(), controls)['passed'])
        geometry = seam_geometry(); geometry['triangles'][3:] = [3,5,4]
        report = inspect_geometry(geometry, controls)
        self.assertFalse(report['passed'])
        self.assertEqual(report['metrics']['seam_samples'][0]['angle_deg'], 180)

    def test_seam_requires_real_triangles_and_bounds(self):
        for mutator in (lambda s: s.update(a=[0,1,3]), lambda s: s.update(a=[0,0,2]),
                        lambda s: s.pop('max_gap'), lambda s: s.update(max_angle_deg=181),
                        lambda s: s.update(max_gap=-1)):
            controls = seam_contract(); mutator(controls['seam_samples'][0])
            self.assertFalse(inspect_geometry(seam_geometry(), controls)['passed'])

    def test_linear_profile(self):
        geometry = profile_geometry([[i,0,0] for i in range(4)])
        controls = contract(profile_checks=[{'id': 'profile', 'vertex_indices': [0,1,2,3],
                                            'max_turn_deg': 0, 'max_curvature_jump': 0}])
        report = inspect_geometry(geometry, controls)
        self.assertTrue(report['passed'], report['errors'])
        self.assertEqual(report['metrics']['profile_checks'][0]['discrete_curvatures'], [0,0])

    def test_circle_constant_curvature_and_scale(self):
        points = [[2*math.cos(i*.1), 2*math.sin(i*.1), 0] for i in range(6)]
        geometry = profile_geometry(points)
        controls = contract(profile_checks=[{'id': 'arc', 'vertex_indices': list(range(6)),
                                            'max_turn_deg': 6, 'max_curvature_jump': 1e-12}])
        report = inspect_geometry(geometry, controls)
        self.assertTrue(report['passed'], report['errors'])
        values = report['metrics']['profile_checks'][0]['discrete_curvatures']
        for value in values:
            self.assertAlmostEqual(value, .5)
        geometry['positions'] = [v*10 for v in geometry['positions']]
        scaled = inspect_geometry(geometry, controls)['metrics']['profile_checks'][0]
        for value in scaled['discrete_curvatures']:
            self.assertAlmostEqual(value, .05)

    def test_profile_kink_curvature_jump(self):
        geometry = profile_geometry([[0,0,0], [1,0,0], [2,0,0], [2,1,0]])
        controls = contract(profile_checks=[{'id': 'crease', 'vertex_indices': [0,1,2,3],
                                            'max_turn_deg': 10, 'max_curvature_jump': .1}])
        report = inspect_geometry(geometry, controls)
        self.assertFalse(report['passed'])
        sample = report['metrics']['profile_checks'][0]
        self.assertEqual(sample['turn_angles_deg'], [0,90])
        self.assertAlmostEqual(sample['max_measured_curvature_jump'], math.sqrt(2))

    def test_profile_without_bound_is_informational(self):
        geometry = profile_geometry([[0,0,0], [1,0,0], [1,1,0]])
        report = inspect_geometry(geometry, contract(profile_checks=[{'id': 'corner', 'vertex_indices': [0,1,2]}]))
        self.assertTrue(report['passed'], report['errors'])
        self.assertFalse(report['metrics']['profile_checks'][0]['bound_declared'])
        self.assertIsNone(report['metrics']['profile_checks'][0]['max_measured_curvature_jump'])

    def test_curvature_direction_reversal_reported_separately(self):
        geometry = profile_geometry([[0,0,0], [1,0,0], [2,1,0], [3,1,0]])
        report = inspect_geometry(geometry, contract(profile_checks=[{'id': 's', 'vertex_indices': [0,1,2,3]}]))
        sample = report['metrics']['profile_checks'][0]
        self.assertTrue(report['passed'])
        self.assertAlmostEqual(sample['curvature_jumps'][0], 0)
        self.assertGreater(sample['curvature_vector_jumps_informational'][0], 1)

    def test_invalid_profiles(self):
        geometry = profile_geometry([[i,0,0] for i in range(4)])
        for sample in ({'id': 'short', 'vertex_indices': [0,1]},
                       {'id': 'short', 'vertex_indices': [0,1,2], 'max_curvature_jump': 1},
                       {'id': 'fake', 'vertex_indices': [0,2,3]},
                       {'id': 'duplicate', 'vertex_indices': [0,1,0]},
                       {'id': 'bad', 'vertex_indices': [0,1,2], 'max_turn_deg': True}):
            self.assertFalse(inspect_geometry(geometry, contract(profile_checks=[sample]))['passed'])

    def test_contract_and_optional_array_validation(self):
        for controls in ({}, {'version': True, 'topology': 'open_patch'},
                         contract(seam_samples=[]), contract(profile_checks=[]),
                         contract(min_triangle_quality=1.1), contract(min_triangle_quality=float('nan')),
                         contract(unknown=1)):
            self.assertFalse(inspect_geometry(triangle(), controls)['passed'])
        controls = seam_contract(); controls['seam_samples'] *= 2
        self.assertFalse(inspect_geometry(seam_geometry(), controls)['passed'])

    def test_cli_new_report_and_failure_exit(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/surface_quality.py'
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d/'geometry.json').write_text(json.dumps(seam_geometry(fold=60)))
            (d/'contract.json').write_text(json.dumps(seam_contract()))
            command = [sys.executable, str(script), '--geometry', str(d/'geometry.json'),
                       '--contract', str(d/'contract.json'), '--out', str(d/'report.json')]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = (d/'report.json').read_text()
            self.assertFalse(json.loads(report)['passed'])
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual((d/'report.json').read_text(), report)


if __name__ == '__main__':
    unittest.main()
