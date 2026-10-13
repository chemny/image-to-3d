"""Isolated contract tests; fixtures deliberately avoid domain-specific objects."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import production_contract as pc


def fixture():
    mesh = {'type': 'mesh', 'positions': [0, 0, 0, 1, 0, 0, 0, 1, 0], 'triangles': [0, 1, 2]}
    return {
        'coordinate_system': {'up': 'y', 'forward': 'z'},
        'references': [{'id': 'front'}],
        'components': [{'id': 'shell', 'geometry': copy.deepcopy(mesh)},
                       {'id': 'flap', 'geometry': copy.deepcopy(mesh)},
                       {'id': 'group', 'kind': 'assembly'}],
        'observations': [{'id': 'tip', 'component_id': 'shell', 'reference_id': 'front',
                          'binding': {'vertex_index': 0}}],
        'checks': [{'id': pc.COVERAGE, 'kind': 'visual', 'stage': 'body', 'required': True},
                   {'id': 'shape', 'kind': 'visual-detail', 'stage': 'review', 'required': True},
                   {'id': 'join', 'kind': 'numeric', 'stage': 'body', 'required': True}],
        'actions': [{'id': 'open', 'component_id': 'flap', 'axis': 'x', 'angle': 1, 'pivot': [0, 0, 0]}],
        'production_contract': {
            'version': 1, 'profiles': ['soft', 'hard', 'assembly', 'moving'],
            'features': [{'id': 'recess', 'reference_id': 'front', 'roi': [0, 0, 1, 1],
                          'provenance': 'observed', 'importance': 'critical', 'form_type': 'concavity',
                          'component_ids': ['shell'], 'method': {'type': 'sculpt', 'rationale': 'Depth changes silhouette'},
                          'check_ids': ['shape'], 'observation_ids': ['tip']}],
            'relations': [{'id': 'joint', 'type': 'hinge', 'component_ids': ['shell', 'flap'],
                           'check_ids': ['join'], 'rationale': 'Flap rotates around shell edge'}]}}


class ProductionContractTests(unittest.TestCase):
    def test_legacy_not_certified(self):
        report = pc.validate({})
        self.assertEqual(report['scope'], 'legacy')
        self.assertFalse(report['production_certified'])

    def test_valid_combinable_profiles_and_no_certification(self):
        report = pc.validate(fixture())
        self.assertEqual(report['feature_count'], 1)
        self.assertFalse(report['professional_quality_verified'])
        self.assertFalse(report['production_certified'])

    def test_mesh_binding_alternative(self):
        s = fixture()
        f = s['production_contract']['features'][0]
        del f['observation_ids']
        f['geometry_bindings'] = [{'component_id': 'shell', 'vertex_index': 2}]
        self.assertTrue(pc.validate(s)['passed'])

    def test_bad_contract_fields(self):
        for field, values in {'version': [True, 2, None], 'profiles': [[], ['other'], ['soft', 'soft'], 'soft'],
                              'features': [[], None], 'relations': [None, {}]}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    s = fixture(); s['production_contract'][field] = value
                    with self.assertRaises(ValueError): pc.validate(s)
        for value in (None, [], True):
            with self.assertRaises(ValueError): pc.validate({'production_contract': value})

    def test_bad_feature_fields(self):
        invalid = {'id': ['', None], 'reference_id': ['absent', []],
                   'roi': [[0, 0, float('nan'), 1], [0, 0, float('inf'), 1], [0, 0, 0, 1],
                           [-.1, 0, 1, 1], [0, 1, 1, 0], [False, 0, 1, 1], [0, 0, 1]],
                   'provenance': ['guess', []], 'importance': ['major'], 'form_type': ['convex'],
                   'component_ids': [['missing'], ['group'], [], ['shell', 'shell']],
                   'check_ids': [['missing'], []], 'method': [None, {}, {'type': 'sculpt', 'rationale': ''}],
                   'observation_ids': [['missing'], []]}
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    s = fixture(); s['production_contract']['features'][0][field] = value
                    with self.assertRaises(ValueError): pc.validate(s)

    def test_missing_fields(self):
        for field in ('id', 'reference_id', 'roi', 'provenance', 'importance', 'form_type',
                      'component_ids', 'check_ids', 'method', 'observation_ids'):
            with self.subTest(field=field):
                s = fixture(); del s['production_contract']['features'][0][field]
                with self.assertRaises(ValueError): pc.validate(s)

    def test_duplicate_ids(self):
        for field in ('components', 'references', 'observations', 'checks', 'actions'):
            s = fixture(); s[field].append(copy.deepcopy(s[field][0]))
            with self.subTest(field=field), self.assertRaises(ValueError): pc.validate(s)
        for field in ('features', 'relations'):
            s = fixture(); s['production_contract'][field] *= 2
            with self.subTest(field=field), self.assertRaises(ValueError): pc.validate(s)

    def test_critical_form_method_contradictions(self):
        for form, method in [('concavity', 'flat_patch'), ('concavity', 'painted_line'), ('branch', 'painted_line')]:
            s = fixture(); f = s['production_contract']['features'][0]
            f['form_type'] = form; f['method']['type'] = method
            with self.subTest(form=form, method=method), self.assertRaises(ValueError): pc.validate(s)

    def test_required_visual_and_coverage_cannot_be_bypassed(self):
        for field, value in [('required', False), ('required', 1), ('kind', 'numeric'), ('stage', 'review')]:
            s = fixture(); s['checks'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): pc.validate(s)
        for field, value in [('required', False), ('kind', 'numeric'), ('stage', 'delivery')]:
            s = fixture(); s['checks'][1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): pc.validate(s)

    def test_observation_must_refer_to_feature_and_reference(self):
        for field, value in [('component_id', 'flap'), ('component_id', 'group'), ('reference_id', 'other')]:
            s = fixture(); s['observations'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): pc.validate(s)
        s = fixture(); s['production_contract']['features'][0]['component_ids'].append('flap')
        with self.assertRaises(ValueError): pc.validate(s)

    def test_invalid_mesh_bindings(self):
        for binding in (None, {}, {'component_id': 'flap', 'vertex_index': 0},
                        {'component_id': 'group', 'vertex_index': 0},
                        *({'component_id': 'shell', 'vertex_index': i} for i in (-1, 3, True, 1.5))):
            s = fixture(); f = s['production_contract']['features'][0]
            del f['observation_ids']; f['geometry_bindings'] = [binding]
            with self.subTest(binding=binding), self.assertRaises(ValueError): pc.validate(s)
        for geometry in ({'type': 'box'}, {'type': 'mesh', 'positions': [0, 0, 0]},
                         {'type': 'mesh', 'positions': [float('inf')] * 9}):
            s = fixture(); f = s['production_contract']['features'][0]
            f['geometry_bindings'] = [{'component_id': 'shell', 'vertex_index': 0}]
            s['components'][0]['geometry'] = geometry
            with self.subTest(geometry=geometry), self.assertRaises(ValueError): pc.validate(s)

    def test_observations_need_actual_surface_binding(self):
        invalid = [None, {}, {'local_point': [0, 0, 0]}, {'vertex_index': 3},
                   {'vertex_index': -1}, {'vertex_index': True},
                   {'vertex_index': 0, 'local_point': [0, 0, 0]},
                   {'patch_id': 'absent', 'uv': [0.5, 0.5]}]
        for binding in invalid:
            s = fixture(); s['observations'][0]['binding'] = binding
            with self.subTest(binding=binding), self.assertRaises(ValueError): pc.validate(s)
        s = fixture(); del s['observations'][0]['binding']
        with self.assertRaises(ValueError): pc.validate(s)

    def test_vertex_bindings_require_actual_triangle_membership(self):
        for mode in ('observation', 'geometry'):
            for triangles in (None, [], [0, 1], [[0, 1, 2]], [0, 1, 4], [0, 1, -1],
                              [0, 1, True], [0, 1, 2.0], [0, 1, 2]):
                s = fixture(); f = s['production_contract']['features'][0]
                # Index 3 exists in positions but has no surface membership.
                s['components'][0]['geometry']['positions'].extend([0, 0, 1])
                s['components'][0]['geometry']['triangles'] = triangles
                if mode == 'observation':
                    s['observations'][0]['binding']['vertex_index'] = 3
                else:
                    del f['observation_ids']
                    f['geometry_bindings'] = [{'component_id': 'shell', 'vertex_index': 3}]
                with self.subTest(mode=mode, triangles=triangles), self.assertRaises(ValueError):
                    pc.validate(s)

    def test_parameters_and_parent_transforms_are_resolved(self):
        s = fixture()
        s['parameters'] = {'offset': {'value': 2, 'min': 0, 'max': 4}}
        s['components'][0]['parent'] = 'group'
        s['components'][2]['position'] = [{'param': 'offset'}, 0, 0]
        s['observations'][0]['binding']['vertex_index'] = {'param': 'offset'}
        self.assertTrue(pc.validate(s)['passed'])
        for mutation in ('bad_range', 'missing_parameter', 'bad_parent', 'cycle', 'nonfinite_transform'):
            bad = copy.deepcopy(s)
            if mutation == 'bad_range': bad['parameters']['offset']['value'] = 5
            elif mutation == 'missing_parameter': bad['components'][2]['position'][0] = {'param': 'absent'}
            elif mutation == 'bad_parent': bad['components'][0]['parent'] = 'absent'
            elif mutation == 'cycle': bad['components'][2]['parent'] = 'shell'
            else: bad['components'][2]['rotation'] = [0, float('nan'), 0]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): pc.validate(bad)

    def test_patch_observation_resolves_real_patch(self):
        s = fixture()
        points = {f'p{i}{j}': {'position': [i, j, 0]} for i in range(4) for j in range(4)}
        patch = {'id': 'surface', 'control_points': [[f'p{i}{j}' for j in range(4)] for i in range(4)]}
        s['components'][0]['geometry'] = {'type': 'bezier_network',
                                         'network': {'control_points': points, 'patches': [patch]}}
        s['observations'][0]['binding'] = {'patch_id': 'surface', 'uv': [0.5, 0.5]}
        self.assertTrue(pc.validate(s)['passed'])
        for binding in ({'patch_id': 'absent', 'uv': [0.5, 0.5]},
                        {'patch_id': 'surface', 'uv': [2, 0]},
                        {'patch_id': 'surface', 'uv': [float('nan'), 0]},
                        {'patch_id': 'surface'}):
            bad = copy.deepcopy(s); bad['observations'][0]['binding'] = binding
            with self.subTest(binding=binding), self.assertRaises(ValueError): pc.validate(bad)

    def test_relations(self):
        invalid = {'type': 'adjacent', 'component_ids': ['shell'], 'check_ids': ['absent'], 'rationale': ''}
        for field, value in invalid.items():
            s = fixture(); s['production_contract']['relations'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): pc.validate(s)
        for ids in (['shell', 'shell'], ['shell', 'group'], ['shell', 'absent']):
            s = fixture(); s['production_contract']['relations'][0]['component_ids'] = ids
            with self.assertRaises(ValueError): pc.validate(s)
        for field, value in [('component_id', 'other'), ('angle', 0), ('angle', float('nan')), ('pivot', []), ('axis', 'q')]:
            s = fixture(); s['actions'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): pc.validate(s)
        s = fixture(); s['actions'] = []
        with self.assertRaises(ValueError): pc.validate(s)

    def test_optional_relations_and_all_forms(self):
        for form in pc.FORMS:
            s = fixture(); s['production_contract']['relations'] = []
            s['production_contract']['profiles'] = ['soft', 'hard']
            s['production_contract']['features'][0]['form_type'] = form
            self.assertTrue(pc.validate(s)['passed'])

    def test_profiles_require_corresponding_relationships(self):
        for profiles in (['assembly'], ['moving'], ['assembly', 'moving']):
            s = fixture(); s['production_contract']['profiles'] = profiles
            self.assertTrue(pc.validate(s)['passed'])
            s['production_contract']['relations'] = []
            with self.subTest(profiles=profiles), self.assertRaises(ValueError): pc.validate(s)
        s = fixture(); s['production_contract']['profiles'] = ['assembly']
        s['production_contract']['relations'][0]['type'] = 'contact'; s['actions'] = []
        self.assertTrue(pc.validate(s)['passed'])
        s['production_contract']['profiles'] = ['moving']
        with self.assertRaises(ValueError): pc.validate(s)
        s['production_contract']['relations'][0]['type'] = 'hinge'
        with self.assertRaises(ValueError): pc.validate(s)
        for profiles in (['soft'], ['hard'], ['soft', 'hard']):
            s = fixture(); s['production_contract'].update(profiles=profiles, relations=[])
            s['actions'] = []
            report = pc.validate(s)
            self.assertTrue(report['passed'])
            self.assertFalse(report['production_certified'])

    def test_evidence_requires_visual_result_at_declared_stage(self):
        s = fixture()
        for stage, cid in [('body', pc.COVERAGE), ('review', 'shape')]:
            for method, verdict in [('numeric', 'pass'), ('visual', 'fail'), (None, 'pass')]:
                e = {'check_results': [{'id': cid, 'method': method, 'verdict': verdict}]}
                with self.subTest(stage=stage, method=method), self.assertRaises(ValueError): pc.validate_evidence(s, e, stage)
            with self.assertRaises(ValueError): pc.validate_evidence(s, {}, stage)
            e = {'check_results': [{'id': cid, 'method': 'visual', 'verdict': 'pass'}]}
            self.assertTrue(pc.validate_evidence(s, e, stage)['passed'])
        self.assertTrue(pc.validate_evidence(s, {}, 'references')['passed'])
        self.assertEqual(pc.validate_evidence({}, {}, 'body')['scope'], 'legacy')


if __name__ == '__main__':
    unittest.main()
