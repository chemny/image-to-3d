import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'workflow.py'
spec = importlib.util.spec_from_file_location('workflow', MODULE)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('ref.png', 'build.py', 'capture.png'):
            (self.root / name).write_text(name)
        self.specpath = self.root / 'spec.json'
        self.state = self.root / 'state.json'
        self.spec = {'schema_version': 1, 'id': 'test', 'domain': 'generic',
                     'coordinate_system': {'unit': 'm', 'up': 'y', 'forward': 'z'},
                     'references': [{'id': 'front', 'path': 'ref.png', 'sha256': w.digest(self.root / 'ref.png'), 'origin': 'original', 'approved': True}],
                     'source_files': [{'path': 'build.py', 'sha256': w.digest(self.root / 'build.py')}],
                     'parameters': {'width': {'value': 1, 'min': .5, 'max': 2}},
                     'components': [{'id': 'body', 'parent': None, 'role': 'body', 'geometry': {'type': 'patch'}, 'material': 'paint'}],
                     'observations': [{'id': 'width', 'reference_id': 'front', 'feature': 'width', 'parameter_ids': ['width']}],
                     'checks': [{'id': 'shape', 'kind': 'visual', 'required': True}],
                     'quality_contract': {'scope': 'display', 'limits': {}}}
        self.write_spec()

    def write_spec(self):
        w.save(self.specpath, self.spec)

    def evidence(self, stage):
        _, resources = w.validate_spec(self.specpath)
        path = self.root / (stage + '-evidence.json')
        w.save(path, {'stage': stage, 'verdict': 'pass', 'reviewer': 'test-fixture-reviewer', 'rationale': 'Synthetic fixture; tests gate mechanics only',
                      'spec_sha256': w.digest(self.specpath), 'resource_hashes': resources,
                      'acceptance': 'quality_passed', 'review_scope': self.spec['quality_contract']['scope'],
                      'artifacts': [{'path': 'capture.png', 'sha256': w.digest(self.root / 'capture.png')}],
                      'check_results': [{'id': 'shape', 'verdict': 'pass', 'method': 'visual', 'reviewer': 'fixture', 'scope': self.spec['quality_contract']['scope'], 'artifact_paths': ['capture.png']},
                                        {'id': 'stage:' + stage, 'verdict': 'pass', 'method': 'fixture-review', 'reviewer': 'fixture', 'scope': self.spec['quality_contract']['scope'], 'artifact_paths': ['capture.png']}]})
        return path

    def advance(self, until):
        w.init(self.specpath, self.state)
        for stage in w.STAGES:
            w.mark(self.state, self.evidence(stage))
            if stage == until:
                break

    def test_complete_and_resume(self):
        self.advance('delivery')
        self.assertIsNone(w.status(self.state)['next'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            w.init(self.specpath, self.state)

    def test_cannot_skip_stage(self):
        w.init(self.specpath, self.state)
        with self.assertRaisesRegex(ValueError, 'stage mismatch'):
            w.mark(self.state, self.evidence('body'))

    def test_changed_source_invalidates_all(self):
        self.advance('body')
        (self.root / 'build.py').write_text('changed geometry')
        result = w.status(self.state)
        self.assertTrue(result['blocked'])
        self.assertFalse(result['completed'])
        self.assertIn('resource hash mismatch', result['issues'][0])

    def test_spec_change_requires_fresh_evidence(self):
        self.advance('body')
        self.spec['parameters']['width']['value'] = 1.1
        self.write_spec()
        self.assertEqual(w.status(self.state)['next'], 'intake')
        w.mark(self.state, self.evidence('intake'))
        self.assertEqual(list(w.read(self.state)['stages']), ['intake'])

    def test_mutated_artifact_invalidates_review(self):
        self.advance('spec')
        (self.root / 'capture.png').write_text('different capture')
        self.assertIn('artifact', w.status(self.state)['issues'][0])

    def test_modified_evidence_not_silently_trusted(self):
        self.advance('intake')
        path = self.root / 'intake-evidence.json'
        data = w.read(path); data['rationale'] = 'edited'
        w.save(path, data)
        self.assertIn('evidence file changed', w.status(self.state)['issues'][0])

    def test_numeric_score_cannot_pass_visual(self):
        self.advance('presentation')
        path = self.evidence('review')
        data = w.read(path); data['check_results'][0]['method'] = 'numeric'; data['score'] = 1
        w.save(path, data)
        with self.assertRaisesRegex(ValueError, 'numeric metrics'):
            w.mark(self.state, path)

    def test_cannot_omit_visual_contract(self):
        self.spec['checks'] = []
        self.write_spec(); self.advance('presentation')
        with self.assertRaisesRegex(ValueError, 'visual review'):
            w.mark(self.state, self.evidence('review'))

    def test_unapproved_reference_blocks(self):
        self.spec['references'][0]['approved'] = False
        self.write_spec(); self.advance('intake')
        with self.assertRaisesRegex(ValueError, 'approved references'):
            w.mark(self.state, self.evidence('references'))

    def test_parent_cycle(self):
        self.spec['components'][0]['parent'] = 'body'; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'cycle'):
            w.validate_spec(self.specpath)

    def test_unknown_parameter(self):
        self.spec['observations'][0]['parameter_ids'] = ['missing']; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'unknown observation parameter'):
            w.validate_spec(self.specpath)

    def test_unknown_geometry_parameter(self):
        self.spec['components'][0]['geometry']['parameters'] = {'width': 'missing'}
        self.write_spec()
        with self.assertRaisesRegex(ValueError, 'unknown geometry parameter'):
            w.validate_spec(self.specpath)

    def test_parameter_rebase_preserves_reference_reviews(self):
        self.advance('body')
        self.spec['parameters']['width']['value'] = 1.2; self.write_spec()
        self.assertTrue(w.status(self.state)['blocked'])
        result = w.rebase(self.state)
        self.assertEqual(result['completed'], ['intake', 'references'])
        self.assertEqual(result['next'], 'spec')
        self.assertIn('body', w.read(self.state)['archives'][0]['stages'])
        w.mark(self.state, self.evidence('spec'))
        self.assertEqual(w.status(self.state)['next'], 'body')

    def test_source_rebase_invalidates_body(self):
        self.advance('body')
        (self.root / 'build.py').write_text('new implementation')
        self.spec['source_files'][0]['sha256'] = w.digest(self.root / 'build.py'); self.write_spec()
        result = w.rebase(self.state)
        self.assertEqual(result['completed'], ['intake', 'references'])
        self.assertNotIn('body', w.read(self.state)['stages'])

    def test_reference_change_cannot_reuse_approval(self):
        self.advance('body')
        (self.root / 'ref.png').write_text('different approved target')
        self.spec['references'][0]['sha256'] = w.digest(self.root / 'ref.png'); self.write_spec()
        with self.assertRaisesRegex(ValueError, 'new intake/reference review'):
            w.rebase(self.state)

    def test_scope_change_cannot_reuse_approval(self):
        self.advance('body')
        self.spec['quality_contract']['scope'] = 'different target'; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'new intake/reference review'):
            w.rebase(self.state)

    def test_rebased_evidence_still_checks_artifacts(self):
        self.advance('body')
        self.spec['parameters']['width']['value'] = 1.2; self.write_spec()
        w.rebase(self.state)
        (self.root / 'capture.png').write_text('changed proof')
        self.assertTrue(w.status(self.state)['blocked'])

    def test_baseline_acceptance_is_not_quality_pass(self):
        w.init(self.specpath, self.state)
        path = self.evidence('intake'); data = w.read(path)
        data['acceptance'] = 'baseline_accepted'; w.save(path, data)
        with self.assertRaisesRegex(ValueError, 'baseline acceptance'):
            w.mark(self.state, path)

    def test_vacuous_checks_block_stage(self):
        w.init(self.specpath, self.state)
        path = self.evidence('intake'); data = w.read(path)
        data['check_results'] = []; w.save(path, data)
        with self.assertRaisesRegex(ValueError, 'required check missing'):
            w.mark(self.state, path)

    def test_check_must_cite_artifact(self):
        w.init(self.specpath, self.state)
        path = self.evidence('intake'); data = w.read(path)
        data['check_results'][1]['artifact_paths'] = ['nonexistent.png']; w.save(path, data)
        with self.assertRaisesRegex(ValueError, 'artifact coverage'):
            w.mark(self.state, path)

    def test_explicit_review_scope_required(self):
        w.init(self.specpath, self.state)
        path = self.evidence('intake'); data = w.read(path)
        data['review_scope'] = 'unrelated task'; w.save(path, data)
        with self.assertRaisesRegex(ValueError, 'review scope'):
            w.mark(self.state, path)

    def test_nonfinite_parameter_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            self.spec['parameters']['width']['max'] = value; self.write_spec()
            with self.assertRaisesRegex(ValueError, 'numeric parameter'):
                w.validate_spec(self.specpath)

    def test_conflicting_approved_references_rejected(self):
        (self.root / 'other.png').write_text('conflicting view')
        self.spec['references'].append({'id': 'other', 'path': 'other.png', 'sha256': w.digest(self.root / 'other.png'), 'origin': 'generated', 'approved': True})
        self.spec['references'][0]['conflicts_with'] = ['other']; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'conflicting references'):
            w.validate_spec(self.specpath)

    def test_reference_changed_after_approval(self):
        self.advance('references')
        (self.root / 'ref.png').write_text('unreviewed replacement')
        self.assertTrue(w.status(self.state)['blocked'])

    def test_synthetic_fixture_is_test_only_and_unapproved(self):
        self.spec['references'][0]['origin'] = 'synthetic'; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'test-only scope'):
            w.validate_spec(self.specpath)
        self.spec['quality_contract']['scope'] = 'synthetic-software-test'
        self.spec['references'][0]['approved'] = False; self.write_spec()
        w.validate_spec(self.specpath)
        self.advance('intake')
        with self.assertRaisesRegex(ValueError, 'approved references'):
            w.mark(self.state, self.evidence('references'))

    def test_parameter_out_of_bounds(self):
        self.spec['parameters']['width']['value'] = 7; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'out of bounds'):
            w.validate_spec(self.specpath)

    def test_incomplete_source_binding_rejected(self):
        w.init(self.specpath, self.state)
        path = self.evidence('intake'); data = w.read(path)
        del data['resource_hashes']['build.py']; w.save(path, data)
        with self.assertRaisesRegex(ValueError, 'resource evidence'):
            w.mark(self.state, path)

    def test_missing_artifact_rejected(self):
        w.init(self.specpath, self.state)
        path = self.evidence('intake'); data = w.read(path)
        data['artifacts'] = []; w.save(path, data)
        with self.assertRaisesRegex(ValueError, 'artifacts required'):
            w.mark(self.state, path)


if __name__ == '__main__':
    unittest.main()
