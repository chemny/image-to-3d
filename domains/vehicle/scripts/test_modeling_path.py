"""Synthetic contract tests, not vehicle fidelity or automated modeling validation."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from modeling_path import VIEWS, DETAILS, REGIONS, audit, sha

class PathContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.path = self.base / 'task.json'
        self.evidence = self.base / 'evidence.json'
        self.evidence.write_text('{"fixture":"synthetic only"}')
        proof = {'path':'evidence.json', 'sha256':sha(self.evidence)}
        self.task = {'schema_version':1, 'sources':[proof], 'boards':[proof], 'target_long_edge':64,
                     'coverage_plan':[{'id':r,'purpose':'synthetic coverage'} for r in VIEWS + DETAILS],
                     'approval':{'status':'approved','user_message':'fixture approval','board_hashes':[proof['sha256']]},
                     'assets':[], 'constraints':[], 'cameras':[]}
        for i, rid in enumerate(VIEWS + DETAILS):
            path = self.base / (rid + '.png')
            Image.new('RGB', (64,64), (i*12,30,60)).save(path)
            self.task['assets'].append({'id':rid,'kind':'view' if rid in VIEWS else 'detail', 'origin':'generated',
                                       'path':path.name,'sha256':sha(path),'dimensions':[64,64],
                                       'adequacy':{'status':'accepted','reason':'synthetic fixture'}})
        images = {a['id']:a for a in self.task['assets']}
        for i, region in enumerate(REGIONS):
            ids = list(dict.fromkeys(['front-left',DETAILS[i % len(DETAILS)]] + (VIEWS if i == 0 else [])))
            self.task['constraints'].append({'id':'c'+str(i), 'region':region, 'origin':'observed','source_ids':ids,
                                            'observations':[{'reference_id':rid,'reference_sha256':images[rid]['sha256'], 'points':[[.1,.2],[.8,.9]],'feature_id':'fixture.feature','control_targets':['fixture']} for rid in ids],
                                            'construction_data':{**proof,'targets':['fixture']}})
        self.task['cameras'] = [{'view':v,'status':'validated','independent_evidence':proof} for v in VIEWS]
        self.task['model'] = proof
        binding = hashlib.sha256(json.dumps({k:self.task[k] for k in ('constraints','cameras','assets')}, sort_keys=True).encode()).hexdigest()
        self.task['body_review'] = {'status':'passed','model':proof,'constraints_sha256':binding,
                                   'criteria':{'calibrated':True,'basis':'synthetic only'},
                                   'outputs':{v+'.'+s:proof for v in VIEWS for s in ('gray','render','difference','landmark')}}
        self.task['body_review']['outputs']['reflection-diagnostic'] = proof

    def tearDown(self):
        self.tmp.cleanup()

    def run_stage(self, stage):
        self.path.write_text(json.dumps(self.task))
        return audit(self.path, stage)

    def test_review_never_authorizes_model(self):
        self.task['approval'] = {'status':'awaiting_review'}
        r = self.run_stage('review')
        self.assertTrue(r['may_advance'])
        self.assertFalse(r['may_build_model'])
        self.assertFalse(r['may_deliver'])

    def test_unapproved_and_stale_boards_block(self):
        self.task['approval']['status'] = 'awaiting_review'
        self.assertIn('awaiting_user_reference_approval',self.run_stage('references')['issues'])
        self.task['approval']['status'] = 'approved'
        self.task['approval']['board_hashes'] = ['0'*64]
        self.assertIn('approval_does_not_bind_current_boards',self.run_stage('references')['issues'])

    def test_changed_reference_rejected(self):
        (self.base / 'front.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.run_stage('references')

    def test_resolution_shortfall_requires_impact(self):
        self.task['target_long_edge'] = 2048
        self.assertFalse(self.run_stage('references')['may_advance'])
        for a in self.task['assets']:
            a['adequacy'] = {'status':'accepted_limited','reason':'fixture low resolution','impact':'coarse fixture only'}
        self.assertTrue(self.run_stage('references')['may_advance'])

    def test_unused_reference_blocks_construction(self):
        c = self.task['constraints'][0]
        c['source_ids'].remove('top')
        c['observations'] = [o for o in c['observations'] if o['reference_id'] != 'top']
        self.assertIn('unused_reference:top',self.run_stage('construction')['issues'])

    def test_missing_control_data_and_inferred_origin_block(self):
        c = self.task['constraints'][0]
        c.pop('construction_data')
        c['origin'] = 'inferred'
        r = self.run_stage('construction')
        self.assertIn('missing_surface_control_data:c0',r['issues'])
        self.assertIn('inferred_constraint_requires_uncertainty:c0',r['issues'])

    def test_details_block_without_body_and_current_binding(self):
        self.task['body_review']['status'] = 'needs_revision'
        self.assertFalse(self.run_stage('details')['may_add_details'])
        self.task['body_review']['status'] = 'passed'
        self.task['constraints'][0]['observations'][0]['points'][0] = [.2,.2]
        self.assertIn('body_review_constraint_binding_mismatch',self.run_stage('details')['issues'])

    def test_valid_body_allows_details_never_delivery(self):
        r = self.run_stage('details')
        self.assertTrue(r['may_add_details'], r['issues'])
        self.assertFalse(r['may_deliver'])

    def test_fake_dimensions_and_duplicate_pixels_rejected(self):
        self.task['assets'][0]['dimensions'] = [2048,2048]
        self.assertIn('incorrect_native_dimensions:front',self.run_stage('references')['issues'])
        self.task['assets'][0] = {**self.task['assets'][0], 'dimensions':[64,64], 'path':self.task['assets'][1]['path'], 'sha256':self.task['assets'][1]['sha256']}
        self.assertIn('independent_references_reuse_same_pixels',self.run_stage('references')['issues'])

    def test_semantic_mapping_and_control_targets_required(self):
        c = self.task['constraints'][0]
        c['observations'][0].pop('feature_id')
        self.assertIn('observation_requires_semantic_mapping:c0',self.run_stage('construction')['issues'])
        c['construction_data']['targets'] = ['does-not-exist']
        self.assertIn('surface_control_target_missing:c0',self.run_stage('construction')['issues'])

    def test_same_curve_cannot_be_relabeled(self):
        c = self.task['constraints'][1]
        c['observations'][0]['feature_id'] = 'unrelated.feature'
        self.assertIn('same_curve_labeled_as_different_feature:c1',self.run_stage('construction')['issues'])

if __name__ == '__main__':
    unittest.main()
