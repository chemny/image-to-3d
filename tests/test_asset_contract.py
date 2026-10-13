"""Contract boundary regression tests; not image reconstruction benchmarks."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from asset_contract import validate


def fixture():
    """A non-vehicle assembly with replaceable handles and an opening lid."""
    return {
        'schema_version': 1,
        'asset_contract': {'version': 1, 'object_class': 'generic', 'intended_use': 'configurator',
                           'units_source': 'relative', 'required_components': ['product', 'lid'],
                           'required_operations': ['select', 'material', 'variant', 'explode', 'action'],
                           'delivery_targets': ['threejs', 'glb'],
                           'source_notes': 'Visible shell from supplied front photo; hidden hinges designed.'},
        'materials': {'plastic': {'color': '#ddccbb', 'roughness': .5,
                                  'source': {'kind': 'reference-inferred', 'note': 'Diffuse photo, no measurement.'}},
                      'alternate': {'color': '#aabbcc', 'source': {'kind': 'designed', 'note': 'Authored blue option.'}}},
        'components': [
            {'id': 'product', 'kind': 'assembly', 'role': 'whole-product'},
            {'id': 'lid', 'parent': 'product', 'role': 'lid', 'selectable': True,
             'explode_vector': [0, 1, 0], 'material': 'plastic',
             'material_slots': {'body': 'plastic', 'blue': 'alternate'},
             'geometry': {'type': 'box', 'size': [1, .1, 1]}},
            {'id': 'handle-a', 'kind': 'assembly', 'parent': 'product', 'role': 'handle-option'},
            {'id': 'grip-a', 'parent': 'handle-a', 'role': 'grip', 'material': 'plastic',
             'geometry': {'type': 'box', 'size': [1, .1, .1]}},
            {'id': 'handle-b', 'parent': 'product', 'role': 'handle-option', 'material': 'plastic',
             'geometry': {'type': 'box', 'size': [.5, .1, .1]}},
        ],
        'variants': [{'id': 'handle', 'options': {'wide': ['handle-a'], 'narrow': ['handle-b']}, 'default': 'wide'}],
        'actions': [{'id': 'open-lid', 'component_id': 'lid', 'axis': 'x', 'angle': 1.2, 'pivot': [0, 0, .5]}],
    }


class AssetContract(unittest.TestCase):
    def test_legacy_explicitly_unverified(self):
        report = validate({'schema_version': 1})
        self.assertTrue(report['passed'])
        self.assertEqual(report['scope'], 'legacy')
        self.assertFalse(report['professional_quality_verified'])

    def test_declared_targets_and_no_input_mutation(self):
        spec = fixture()
        before = copy.deepcopy(spec)
        report = validate(spec)
        self.assertEqual(spec, before)
        self.assertEqual(report['scope'], 'asset-contract-v1')
        self.assertEqual(report['operation_targets']['select'], ['lid'])
        self.assertEqual(report['operation_targets']['material'], ['lid'])
        self.assertFalse(report['professional_quality_verified'])

    def test_order_independent_hierarchy(self):
        spec = fixture()
        spec['components'].reverse()
        self.assertTrue(validate(spec)['passed'])

    def test_opt_in_requires_complete_evidence(self):
        for field in ('version', 'object_class', 'intended_use', 'units_source', 'required_components',
                      'required_operations', 'delivery_targets', 'source_notes'):
            spec = fixture()
            del spec['asset_contract'][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(spec)
        for source in (None, {}, {'kind': 'measured', 'note': ' '}):
            spec = fixture()
            spec['materials']['plastic']['source'] = source
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate(spec)

    def test_missing_required_component_and_operation(self):
        spec = fixture()
        spec['asset_contract']['required_components'].append('missing')
        with self.assertRaises(ValueError): validate(spec)
        for operation in ('select', 'material', 'variant', 'explode', 'action'):
            spec = fixture()
            spec['asset_contract']['required_operations'] = [operation]
            if operation == 'select': spec['components'][1]['selectable'] = False
            if operation == 'material': spec['components'][1]['material_slots'] = {}
            if operation == 'variant': spec['variants'] = []
            if operation == 'explode': spec['components'][1]['explode_vector'] = [0, 0, 0]
            if operation == 'action': spec['actions'] = []
            with self.subTest(operation=operation), self.assertRaises(ValueError): validate(spec)

    def test_display_does_not_require_interactivity(self):
        spec = fixture()
        spec['asset_contract']['intended_use'] = 'display'
        spec['asset_contract']['required_operations'] = []
        spec['actions'] = []
        spec['variants'] = []
        self.assertTrue(validate(spec)['passed'])

    def test_hierarchy_dangling_cycle_duplicate_and_bad_role(self):
        for mode in ('dangling', 'cycle', 'duplicate', 'role', 'bad-parent'):
            spec = fixture()
            if mode == 'dangling': spec['components'][0]['parent'] = 'missing'
            if mode == 'cycle': spec['components'][0]['parent'] = 'grip-a'
            if mode == 'duplicate': spec['components'].append(copy.deepcopy(spec['components'][0]))
            if mode == 'role': spec['components'][0]['role'] = ''
            if mode == 'bad-parent': spec['components'][2]['parent'] = []
            with self.subTest(mode=mode), self.assertRaises(ValueError): validate(spec)

    def test_assembly_is_transform_only(self):
        for field, value in (('geometry', {'type': 'box'}), ('material', 'plastic'),
                             ('material_slots', {'body': 'plastic'})):
            spec = fixture()
            spec['components'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate(spec)

    def test_slot_must_reference_authored_material(self):
        spec = fixture()
        spec['components'][1]['material_slots']['blue'] = 'missing'
        with self.assertRaises(ValueError): validate(spec)

    def test_variant_subtree_overlap_not_just_duplicate_root(self):
        for roots in (['grip-a'], ['product'], ['handle-a', 'grip-a']):
            spec = fixture()
            spec['variants'][0]['options']['narrow'] = roots
            with self.subTest(roots=roots), self.assertRaises(ValueError): validate(spec)
        spec = fixture()
        spec['variants'].append({'id': 'second', 'options': {'a': ['grip-a'], 'b': ['lid']}, 'default': 'a'})
        with self.assertRaises(ValueError): validate(spec)

    def test_variant_default_ids_and_options(self):
        for field, value in (('default', 'missing'), ('options', {'a': []}), ('id', '')):
            spec = fixture()
            spec['variants'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate(spec)
        spec = fixture()
        spec['variants'].append(copy.deepcopy(spec['variants'][0]))
        with self.assertRaises(ValueError): validate(spec)

    def test_action_target_and_numeric_types(self):
        for field, value in (('component_id', 'missing'), ('angle', True), ('angle', float('nan')),
                             ('pivot', [0, 0]), ('axis', 'w')):
            spec = fixture()
            spec['actions'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): validate(spec)

    def test_texture_requires_explicit_uvs_and_metadata(self):
        spec = fixture()
        spec['materials']['alternate']['maps'] = {
            'map': {'path': 'textures/blue.png', 'sha256': 'a' * 64, 'color_space': 'srgb'}}
        with self.assertRaises(ValueError): validate(spec)
        spec['components'][1]['geometry'] = {'type': 'mesh', 'positions': [0, 0, 0, 1, 0, 0, 0, 1, 0],
                                             'triangles': [0, 1, 2], 'uvs': [0, 0, 1, 0, 0, 1]}
        self.assertTrue(validate(spec)['passed'])
        for field, value in (('path', '../blue.png'), ('path', '/blue.png'), ('path', 'https://host/a.png'),
                             ('path', 'a\\b.png'), ('path', 'a//b.png'), ('sha256', 'not-a-hash'),
                             ('color_space', 'linear')):
            broken = copy.deepcopy(spec)
            broken['materials']['alternate']['maps']['map'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): validate(broken)
        spec['components'][1]['geometry']['uvs'].pop()
        with self.assertRaises(ValueError): validate(spec)

    def test_data_map_color_space_and_nonfinite_material(self):
        spec = fixture()
        spec['materials']['plastic']['maps'] = {
            'normalMap': {'path': 'normal.png', 'sha256': 'b' * 64, 'color_space': 'srgb'}}
        with self.assertRaisesRegex(ValueError, 'linear'): validate(spec)
        for value in (True, float('inf'), -.1, 1.1):
            spec = fixture()
            spec['materials']['plastic']['roughness'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): validate(spec)

    def test_generated_uv_geometry_can_carry_maps(self):
        for kind in ('torus', 'tube'):
            spec = fixture()
            spec['materials']['alternate']['maps'] = {
                'map': {'path': 'blue.png', 'sha256': 'c' * 64, 'color_space': 'srgb'}}
            spec['components'][1]['geometry'] = {'type': kind}
            # Dimensions/topology are independently enforced by the geometry builder.
            with self.subTest(kind=kind): self.assertTrue(validate(spec)['passed'])

    def test_schema_failure_is_value_error(self):
        for field, value in (('asset_contract', None), ('components', [{}]), ('materials', []),
                             ('variants', [None]), ('actions', 'open')):
            spec = fixture()
            spec[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate(spec)


if __name__ == '__main__':
    unittest.main()
