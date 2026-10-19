"""Synthetic geometry failure injection; no production models or image scoring."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

import model_repair
import scene_build
import surface_attachment as attachment
from surface_quality import inspect_geometry
import test_surface_attachment as attachment_fixture
import test_surface_quality as surface_fixture


class RootAttachmentRegressionTests(unittest.TestCase):
    def setUp(self):
        self.spec = attachment_fixture.SurfaceTests().spec()
        self.check = attachment_fixture.SurfaceTests().gap()
        # Triangle 0 is the actual mounting root. Triangle 1 is the projecting tip.
        self.spec['components'][1]['geometry'] = dict(type='mesh',
            positions=[-.1,-.1,.01, .1,-.1,.01, 0,.1,.01, 0,0,.5],
            triangles=[0,1,2, 0,3,1])
        self.check.pop('samples')
        self.check['anchors'] = [dict(component_id='part', vertex_index=i) for i in range(3)]

    def test_protruding_part_with_seated_root(self):
        self.assertTrue(attachment.evaluate(self.spec, [self.check])['passed'])
        automatic = copy.deepcopy(self.check); automatic.pop('anchors')
        self.assertFalse(attachment.evaluate(self.spec, [automatic])['passed'])

    def test_single_lifted_root_point_identified(self):
        self.spec['components'][1]['geometry']['positions'][8] = .1
        report = attachment.evaluate(self.spec, [self.check])
        self.assertFalse(report['passed'])
        row = report['checks'][0]
        self.assertEqual(row['failed_sample_indices'], [2])
        self.assertEqual(row['samples'][2]['reasons'], ['above_max_gap'])

    def test_buried_root_and_wrong_side(self):
        self.spec['components'][1]['position'] = [0,0,-.02]
        self.assertFalse(attachment.evaluate(self.spec, [self.check])['passed'])
        self.check['side'] = 'inside'
        self.assertTrue(attachment.evaluate(self.spec, [self.check])['passed'])

    def test_excessive_burial_not_accepted_as_attachment(self):
        self.spec['components'][1]['position'] = [0,0,-.5]
        self.check['side'] = 'inside'
        report = attachment.evaluate(self.spec, [self.check])
        self.assertFalse(report['passed'])
        self.assertGreater(report['checks'][0]['min_gap'], .4)

    def test_common_parent_rotation_and_translation_preserve_gap(self):
        self.spec['components'].append(dict(id='assembly', kind='assembly', position=[4,3,-1], rotation=[0,.7,1.1]))
        for part in self.spec['components'][:2]:
            part['parent'] = 'assembly'
        report = attachment.evaluate(self.spec, [self.check])
        self.assertTrue(report['passed'])
        self.assertAlmostEqual(report['checks'][0]['max_gap'], .01)

    def test_attachment_parent_motion_is_measured(self):
        self.spec['components'].append(dict(id='assembly', kind='assembly', position=[0,0,.5]))
        self.spec['components'][1]['parent'] = 'assembly'
        self.assertFalse(attachment.evaluate(self.spec, [self.check])['passed'])

    def test_nearby_unrelated_host_face_cannot_mask_gap(self):
        g = self.spec['components'][0]['geometry']
        g['positions'] += [v + (.01 if i % 3 == 2 else 0) for i,v in enumerate(g['positions'][:12])]
        g['triangles'] += [4,5,6,4,6,7]
        self.spec['components'][1]['position'] = [0,0,.05]
        # Shift the second host surface up to the floating attachment.
        for i in (14,17,20,23):
            g['positions'][i] = .06
        self.assertTrue(attachment.evaluate(self.spec, [self.check])['passed'])
        self.check['host_faces'] = [dict(component_id='host', mesh_index=0, triangle_index=i) for i in (0,1)]
        self.assertFalse(attachment.evaluate(self.spec, [self.check])['passed'])

    def test_incorrect_anchor_bindings_rejected(self):
        mutations = [lambda c:c.update(samples=32), lambda c:c.update(anchors=[]),
            lambda c:c['anchors'][0].update(component_id='host'),
            lambda c:c['anchors'][0].update(vertex_index=999),
            lambda c:c['anchors'][0].update(vertex_index=True),
            lambda c:c['anchors'].__setitem__(2, copy.deepcopy(c['anchors'][0])),
            lambda c:c.update(component_ids=['part','host'])]
        for change in mutations:
            with self.subTest(change=change):
                control = copy.deepcopy(self.check); change(control)
                with self.assertRaises(ValueError):
                    attachment.evaluate(self.spec, [control])

    def test_bad_host_selection_rejected(self):
        for faces in ([], [dict(component_id='part',mesh_index=0,triangle_index=0)],
                      [dict(component_id='host',mesh_index=99,triangle_index=0)],
                      [dict(component_id='host',mesh_index=0,triangle_index=99)],
                      [dict(component_id='host',mesh_index=False,triangle_index=0)]):
            with self.subTest(faces=faces):
                control = dict(self.check, host_faces=faces)
                with self.assertRaises(ValueError):
                    attachment.evaluate(self.spec, [control])

    def test_empty_checks_and_duplicate_ids_not_silent_pass(self):
        for checks in ([], [self.check,self.check]):
            with self.assertRaises(ValueError):
                attachment.evaluate(self.spec, checks)

    def test_gap_below_minimum_is_distinguished(self):
        self.check.update(min=.015, max=.02)
        row = attachment.evaluate(self.spec, [self.check])['checks'][0]
        self.assertEqual(row['samples'][0]['reasons'], ['below_min_gap'])

    def test_actual_repair_constraint_uses_root_bindings(self):
        self.spec.update(references=[dict(id='original',path='reference.bin',sha256='')],
            cameras={'front':dict(position=[0,0,5],target=[0,0,0]),'side':dict(position=[5,0,0],target=[0,0,0])})
        control = dict(version=1, targets=[dict(id='root',component_ids=['part'],reference_ids=['original'],
            problem='Mounting gap',expected='Root seated, tip free',check_ids=['front','side'])],
            editable_components=['part'], allowed_parameters=[], protected_components=[],
            checks=[dict(id='front',method='visual',component_ids=['part'],view_ids=['front'],view_role='original'),
                    dict(id='side',method='visual',component_ids=['part'],view_ids=['side'],view_role='depth'),
                    dict(id='gap',method='numeric',component_ids=['part','host'])], constraints=[self.check])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'reference.bin').write_bytes(b'fixture reference')
            self.spec['references'][0]['sha256'] = model_repair.sha(root/'reference.bin')
            (root/'source.json').write_text(json.dumps(self.spec)); (root/'repair.json').write_text(json.dumps(control))
            session = model_repair.init(root/'source.json', root/'repair.json',root/'session',diagnostic=True)['session_path']
            candidate = root/'candidate.json';candidate.write_text(json.dumps(self.spec))
            self.assertTrue(model_repair.check(session,candidate)['passed'])
            self.spec['components'][1]['position'] = [0,0,.2]
            candidate.write_text(json.dumps(self.spec))
            self.assertFalse(model_repair.check(session,candidate)['passed'])


class CurvatureDirectionRegressionTests(unittest.TestCase):
    def geometry(self):
        return surface_fixture.profile_geometry([[0,0,0],[1,0,0],[2,1,0],[3,1,0]])

    def contract(self, **bounds):
        return surface_fixture.contract(profile_checks=[dict(id='fold',vertex_indices=[0,1,2,3],**bounds)])

    def test_equal_curvature_magnitudes_do_not_hide_direction_reversal(self):
        self.assertTrue(inspect_geometry(self.geometry(),self.contract(max_curvature_jump=1e-9))['passed'])
        report = inspect_geometry(self.geometry(),self.contract(max_curvature_vector_jump=.1))
        self.assertFalse(report['passed'])
        self.assertIn('profile curvature vector jump exceeds authored bound: fold', report['errors'])

    def test_straight_surface_has_zero_vector_jump(self):
        geometry = surface_fixture.profile_geometry([[i,0,0] for i in range(4)])
        report = inspect_geometry(geometry,self.contract(max_curvature_vector_jump=0))
        self.assertTrue(report['passed'])

    def test_bound_is_opt_in_and_hard_design_edge_can_be_retained(self):
        report = inspect_geometry(self.geometry(),self.contract())
        self.assertTrue(report['passed'])
        self.assertFalse(report['metrics']['profile_checks'][0]['bound_declared'])
        self.assertTrue(inspect_geometry(self.geometry(),self.contract(max_curvature_vector_jump=3))['passed'])

    def test_rotation_preserves_metric_and_scale_changes_units(self):
        geometry = self.geometry()
        measure = lambda g:inspect_geometry(g,self.contract())['metrics']['profile_checks'][0]['max_measured_curvature_vector_jump']
        original = measure(geometry)
        positions = geometry['positions']
        points = [positions[i:i+3] for i in range(0,len(positions),3)]
        geometry['positions'] = [v for p in points for v in scene_build.rotate(p,[.3,.6,.7])]
        self.assertAlmostEqual(measure(geometry),original)
        geometry['positions'] = [10*v for v in geometry['positions']]
        self.assertAlmostEqual(measure(geometry),original/10)

    def test_invalid_bounds_and_short_profiles_rejected(self):
        for value in (-1,True,float('nan'),float('inf')):
            self.assertFalse(inspect_geometry(self.geometry(),self.contract(max_curvature_vector_jump=value))['passed'])
        control = self.contract(max_curvature_vector_jump=.1)
        control['profile_checks'][0]['vertex_indices'] = [0,1,2]
        self.assertFalse(inspect_geometry(self.geometry(),control)['passed'])

    def test_build_gate_uses_geometry_despite_smoothed_shading_normals(self):
        spec = attachment_fixture.SurfaceTests().spec()
        geometry = self.geometry();geometry['normals'] = [0,1,0]*(len(geometry['positions'])//3)
        spec['components'] = [dict(id='panel', material='m', geometry=geometry,
                                    surface_contract=self.contract(max_curvature_vector_jump=.1))]
        with self.assertRaisesRegex(ValueError,'surface contract failed'):
            scene_build.build(spec)


if __name__ == '__main__':
    unittest.main()
