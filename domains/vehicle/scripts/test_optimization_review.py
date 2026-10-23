import copy, json, tempfile, unittest
from pathlib import Path
from optimization_review import seal, evaluate, digest

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        for name, content in [('model.glb', b'synthetic asset identity A'), ('output.glb', b'synthetic asset identity B'), ('ref.png', b'reference identity'), ('view.png', b'visual evidence identity'), ('camera.json', b'camera review identity')]:
            (self.root / name).write_bytes(content)
        self.plan = {'schema_version': 1, 'claim': 'reference_fidelity', 'coverage': 'selected_regions', 'scope': 'roof and window observation logic only', 'baseline_model': 'model.glb', 'original_model': 'model.glb', 'references': ['ref.png'], 'views': {'side': {'alignment': 'validated', 'alignment_evidence': 'camera.json'}}, 'critical_features': {'roofline': ['side'], 'windowline': ['side']}, 'independent_features': ['roofline', 'windowline'], 'required_checks': ['uv'], 'calibration_points': [{'id': 'wheel-cal', 'feature': 'roofline', 'view': 'side', 'reference': [0, 0]}], 'validation_points': [{'id': 'roof', 'feature': 'roofline', 'view': 'side', 'reference': [20, 20], 'threshold_px': 5, 'uncertainty_px': 2, 'threshold_reason': 'Synthetic test contract'}, {'id': 'window', 'feature': 'windowline', 'view': 'side', 'reference': [60, 20], 'threshold_px': 5, 'uncertainty_px': 2, 'threshold_reason': 'Synthetic test contract'}]}
        self.evidence = {'path': 'view.png', 'sha256': digest(self.root/'view.png')}

    def tearDown(self): self.temp.cleanup()

    def setup_record(self, plan=None):
        p = plan or self.plan; self.planpath = self.root/'plan.json'; self.lockpath = self.root/'lock.json'; self.recordpath = self.root/'record.json'
        self.planpath.write_text(json.dumps(p)); lock = seal(self.planpath, self.lockpath)
        return {'plan_sha256': lock['plan_sha256'], 'output_model': {'path': 'output.glb', 'sha256': digest(self.root/'output.glb')}, 'checks': {'uv': {'verdict': 'passed', 'evidence': [self.evidence]}}, 'visual_reviews': [{'view': 'side', 'features': ['roofline', 'windowline'], 'verdict': 'passed', 'evidence': [self.evidence]}], 'observations': [{'id': 'roof', 'before': [30, 20], 'after': [22, 20]}, {'id': 'window', 'before': [70, 20], 'after': [62, 20]}]}

    def run_record(self, r):
        self.recordpath.write_text(json.dumps(r)); return evaluate(self.lockpath, self.recordpath)

    def test_valid_regional_record_is_consistent_not_fidelity_certified(self):
        result = self.run_record(self.setup_record()); self.assertEqual(result['verdict'], 'consistent'); self.assertIn('not automatic', result['limitations'][1])

    def test_single_bad_critical_point_blocks_even_if_average_improves(self):
        r = self.setup_record(); r['observations'][1]['after'] = [80, 20]
        result = self.run_record(r); self.assertEqual(result['verdict'], 'needs_revision'); self.assertEqual(result['measurements'][1]['after_error_px'], 20)

    def test_using_validation_for_adjustment_removes_independent_status(self):
        r = self.setup_record(); r['used_for_adjustment'] = ['roof']; result = self.run_record(r)
        self.assertEqual(result['verdict'], 'needs_revision'); self.assertFalse(result['measurements'][0]['independent'])

    def test_renamed_calibration_point_rejected(self):
        p = copy.deepcopy(self.plan); p['validation_points'][0]['reference'] = [0, 0]
        with self.assertRaises(ValueError): self.setup_record(p)

    def test_missing_reserved_observation_blocks(self):
        r = self.setup_record(); r['observations'].pop(); self.assertEqual(self.run_record(r)['verdict'], 'needs_revision')

    def test_visual_regression_blocks_numerical_pass(self):
        r = self.setup_record(); r['visual_reviews'][0]['verdict'] = 'needs_revision'; self.assertEqual(self.run_record(r)['verdict'], 'needs_revision')

    def test_changed_source_rejected(self):
        r = self.setup_record(); (self.root/'ref.png').write_bytes(b'changed source')
        with self.assertRaises(ValueError): self.run_record(r)

    def test_changed_review_image_rejected(self):
        r = self.setup_record(); (self.root/'view.png').write_bytes(b'changed evidence')
        with self.assertRaises(ValueError): self.run_record(r)

    def test_loosened_threshold_after_seal_rejected(self):
        r = self.setup_record(); lock = json.loads(self.lockpath.read_text()); lock['plan']['validation_points'][0]['threshold_px'] = 999; self.lockpath.write_text(json.dumps(lock))
        with self.assertRaises(ValueError): self.run_record(r)

    def test_unregistered_camera_cannot_certify_pixel_fit(self):
        p = copy.deepcopy(self.plan); p['views']['side']['alignment'] = 'approximate'; r = self.setup_record(p)
        self.assertEqual(self.run_record(r)['verdict'], 'needs_revision')

    def test_baseline_swap_needs_comparison_evidence(self):
        p = copy.deepcopy(self.plan); p['original_model'] = 'output.glb'
        with self.assertRaises(ValueError): self.setup_record(p)

    def test_partial_feature_coverage_cannot_claim_whole_exterior(self):
        p = copy.deepcopy(self.plan); p['coverage'] = 'whole_exterior'
        with self.assertRaises(ValueError): self.setup_record(p)

    def test_asset_only_quality_does_not_require_photos(self):
        p = copy.deepcopy(self.plan); p.update(claim='asset_quality', coverage='asset_quality', references=[], independent_features=[], calibration_points=[], validation_points=[])
        r = self.setup_record(p); r['observations'] = []; self.assertEqual(self.run_record(r)['verdict'], 'consistent')

    def test_protected_check_failure_blocks_other_passes(self):
        r = self.setup_record(); r['checks']['uv']['verdict'] = 'needs_revision'; self.assertEqual(self.run_record(r)['verdict'], 'needs_revision')

    def test_existing_lock_not_overwritten(self):
        self.setup_record()
        with self.assertRaises(FileExistsError): seal(self.planpath, self.lockpath)

if __name__ == '__main__': unittest.main()
