import copy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from production_checks import evaluate


def binding(component, index=0):
    return {'component_id': component, 'vertex_index': index}


def fixture():
    mesh = {'type': 'mesh', 'positions': [1, 0, 0, 1, 1, 0, 1, 0, 1], 'triangles': [0, 1, 2]}
    return {'coordinate_system': {'unit': 'm', 'up': 'y', 'forward': 'z'},
            'materials': {'solid': {'color': '#cccccc'}},
            'components': [
                {'id': 'left', 'material': 'solid', 'geometry': copy.deepcopy(mesh)},
                {'id': 'right', 'material': 'solid', 'geometry': copy.deepcopy(mesh)}],
            'checks': [{'id': 'attachment', 'kind': 'numeric', 'required': True, 'stage': 'assembly'}],
            'production_contract': {'geometry_checks': [
                {'id': 'attachment', 'kind': 'distance', 'a': binding('left'),
                 'b': binding('right'), 'min': 0, 'max': .001}]}}


def check(spec):
    return spec['production_contract']['geometry_checks'][0]


class ProductionChecks(unittest.TestCase):
    def test_distance_attached_and_detached(self):
        spec = fixture()
        report = evaluate(spec)
        self.assertTrue(report['passed'])
        self.assertEqual(report['checked'], 1)
        self.assertEqual(report['checks'][0]['distance'], 0)
        spec['components'][1]['position'] = [.02, 0, 0]
        report = evaluate(spec)
        self.assertFalse(report['passed'])
        self.assertAlmostEqual(report['checks'][0]['distance'], .02)

    def test_distance_minimum_and_closed_interval(self):
        spec = fixture()
        check(spec).update(min=1, max=2)
        self.assertFalse(evaluate(spec)['passed'])
        for distance in (1, 2):
            spec['components'][1]['position'] = [distance, 0, 0]
            self.assertTrue(evaluate(spec)['passed'])

    def test_parent_rotation_and_translation_are_world_space(self):
        spec = fixture()
        spec['components'].append({'id': 'parent', 'kind': 'assembly',
                                   'rotation': [0, 0, math.pi / 2], 'position': [3, 4, 0]})
        spec['components'][0].update(parent='parent', position=[1, 0, 0])
        spec['components'][1]['position'] = [2, 6, 0]
        self.assertTrue(evaluate(spec)['passed'])
        spec['components'][0]['position'] = [2, 0, 0]
        self.assertFalse(evaluate(spec)['passed'])

    def test_generated_mesh_binding_uses_built_vertices(self):
        spec = fixture()
        for part in spec['components']:
            part['geometry'] = {'type': 'box', 'size': [2, 2, 2]}
        self.assertTrue(evaluate(spec)['passed'])
        spec['components'][1]['geometry']['size'][0] = 4
        self.assertFalse(evaluate(spec)['passed'])

    def test_bezier_patch_binding_and_uv_changes(self):
        spec = fixture()
        network = json.loads((Path(__file__).resolve().parents[1] / 'examples/bezier-network-example.json').read_text())
        for part in spec['components']:
            part['geometry'] = {'type': 'bezier_network', 'network': copy.deepcopy(network)}
        for key, component in (('a', 'left'), ('b', 'right')):
            check(spec)[key] = {'component_id': component, 'patch_id': 'left', 'uv': [.2, .3]}
        self.assertTrue(evaluate(spec)['passed'])
        check(spec)['b']['uv'] = [.8, .3]
        self.assertFalse(evaluate(spec)['passed'])
        check(spec)['b']['uv'] = [2, .3]
        with self.assertRaises(ValueError): evaluate(spec)
        check(spec)['b']['uv'] = [0, 0]
        check(spec)['b']['patch_id'] = 'missing'
        with self.assertRaises(ValueError): evaluate(spec)

    def mirror(self):
        spec = fixture()
        for index in (0, 3, 6):
            spec['components'][1]['geometry']['positions'][index] *= -1
        spec['production_contract']['geometry_checks'] = [{
            'id': 'attachment', 'kind': 'mirror', 'axis': 'x', 'plane': 0, 'tolerance': 1e-10,
            'pairs': [{'a': binding('left', i), 'b': binding('right', i)} for i in range(3)]}]
        return spec

    def test_mirror_samples_not_rotation(self):
        spec = self.mirror()
        self.assertTrue(evaluate(spec)['passed'])
        # A half-turn agrees at one point, but is not a reflection for all samples.
        spec['components'][1]['geometry'] = copy.deepcopy(spec['components'][0]['geometry'])
        spec['components'][1]['rotation'] = [0, math.pi, 0]
        self.assertFalse(evaluate(spec)['passed'])

    def test_mirror_does_not_certify_winding(self):
        spec = self.mirror()
        before = evaluate(spec)
        spec['components'][1]['geometry']['triangles'] = [0, 2, 1]
        after = evaluate(spec)
        self.assertTrue(before['passed'] and after['passed'])
        self.assertIn('winding', after['scope'])
        self.assertIn('no full thickness', after['scope'])

    def test_nonzero_mirror_plane_all_axes(self):
        for axis in range(3):
            spec = self.mirror()
            positions = spec['components'][0]['geometry']['positions']
            reflected = list(positions)
            for i in range(axis, len(positions), 3): reflected[i] = 4 - positions[i]
            spec['components'][1]['geometry']['positions'] = reflected
            check(spec).update(axis='xyz'[axis], plane=2)
            self.assertTrue(evaluate(spec)['passed'])

    def test_reject_dangling_bindings(self):
        for endpoint in (binding('missing'), binding('left', -1), binding('left', 3),
                         binding('left', True), binding('left', 1.0),
                         {'component_id': 'left', 'patch_id': 'fake', 'uv': [0, 0]}):
            spec = fixture()
            check(spec)['a'] = endpoint
            with self.assertRaises(ValueError): evaluate(spec)

    def test_free_points_and_extra_fields_cannot_counterfeit_geometry(self):
        for endpoint in ({'component_id': 'left', 'local_point': [0, 0, 0]},
                         {**binding('left'), 'local_point': [0, 0, 0]},
                         {'component_id': 'left', 'binding': {'vertex_index': 0}}):
            spec = fixture()
            check(spec)['a'] = endpoint
            with self.assertRaises(ValueError): evaluate(spec)

    def test_check_id_must_bind_required_numeric_body_or_assembly(self):
        for update in ({'kind': 'visual'}, {'required': False}, {'stage': 'review'}, {'id': 'other'}):
            spec = fixture()
            spec['checks'][0].update(update)
            with self.assertRaises(ValueError): evaluate(spec)
        spec = fixture()
        spec['checks'][0]['stage'] = 'body'
        self.assertTrue(evaluate(spec)['passed'])
        spec['checks'].append(copy.deepcopy(spec['checks'][0]))
        with self.assertRaises(ValueError): evaluate(spec)

    def test_reject_bad_limits_nan_infinity_and_boolean(self):
        for low, high in ((-1, 1), (2, 1), (0, -1), (float('nan'), 1),
                          (0, float('inf')), (True, 1), ('0', 1)):
            spec = fixture()
            check(spec).update(min=low, max=high)
            with self.assertRaises(ValueError): evaluate(spec)
        for update in ({'pairs': []}, {'tolerance': -1}, {'tolerance': float('nan')},
                       {'plane': float('inf')}, {'plane': True}, {'axis': 'w'}):
            spec = self.mirror()
            check(spec).update(update)
            with self.assertRaises(ValueError): evaluate(spec)

    def test_invalid_mesh_is_not_a_valid_measurement(self):
        spec = fixture()
        spec['components'][0]['geometry']['triangles'] = [0, 0, 0]
        with self.assertRaises(ValueError): evaluate(spec)
        spec = fixture()
        spec['components'][0]['geometry']['positions'][0] = float('nan')
        with self.assertRaises(ValueError): evaluate(spec)

    def test_unknown_kind_duplicate_id_and_extra_keys_rejected(self):
        spec = fixture()
        check(spec)['kind'] = 'full_collision_certificate'
        with self.assertRaisesRegex(ValueError, 'unsupported'): evaluate(spec)
        spec = fixture()
        check(spec)['trust_me'] = True
        with self.assertRaises(ValueError): evaluate(spec)
        spec = fixture()
        spec['production_contract']['geometry_checks'].append(copy.deepcopy(check(spec)))
        with self.assertRaises(ValueError): evaluate(spec)

    def test_optional_empty_reports_zero_not_geometry_certificate(self):
        for contract in ({}, {'geometry_checks': []}):
            spec = fixture()
            spec['production_contract'] = contract
            report = evaluate(spec)
            self.assertEqual(report['checked'], 0)
            self.assertEqual(report['checks'], [])
            self.assertIn('sampled static', report['scope'])
        spec.pop('production_contract')
        self.assertEqual(evaluate(spec)['checked'], 0)


if __name__ == '__main__':
    unittest.main()
