import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from version_handoff import evaluate


class VersionHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.old = self.write('old.bin', b'production')
        self.sample = self.write('sample.bin', b'accepted shape')
        self.new = self.write('new.bin', b'shape plus detail')
        self.registry = self.write('registry-before.js', b'old URL')
        self.registry_after = self.write('registry-after.js', b'new URL')
        self.image = self.write('capture.png', b'fixture capture bytes')
        acceptance = self.write('acceptance.json', {'note': 'User accepted direction; not certification'})
        self.inventory = {'accepted_work': [{'id': 'shape', 'asset': self.sample, 'acceptance': acceptance}]}
        target = dict(case_id='toy', source='chatgpt', page_url='http://localhost/cases/?case=toy', model_url='http://localhost/old/model.js')
        installed = dict(target, model_url='http://localhost/new/model.js')
        obs = dict(target=target, asset_sha256=self.old['sha256'], registry_sha256=self.registry['sha256'], ready=True, errors=[], screenshot=self.image)
        after = dict(target=installed, asset_sha256=self.new['sha256'], registry_sha256=self.registry_after['sha256'], ready=True, errors=[], screenshot=self.image,
                     checks={'switch_return': True, 'reset': True, 'recolor_protection': True, 'orbit': True})
        adoption = dict(baseline=self.sample, candidate=self.new, same_conditions=True, required_regions=['detail'],
                        regions=[dict(id='detail', verdict='improved', reason='Fixture observation', before=self.image, after=self.image)])
        self.report = dict(version=1, production=dict(target=target, asset=self.old, registry=self.registry, observation=self.write('before.json', obs)),
                           inventory=self.write('inventory.json', self.inventory), baseline=self.sample, baseline_reason='Continue accepted shape sample',
                           inheritance=[dict(id='shape', status='inherited', reason='Retained shape in candidate', evidence=self.write('inheritance.json',
                                            dict(work_id='shape', candidate_sha256=self.new['sha256'], passed=True)))],
                           candidate=self.new, adoption_review=self.write('adoption.json', adoption),
                           installed=dict(target=installed, registry=self.registry_after, observation=self.write('after.json', after), rollback='old/model.js'),
                           required_operations=['recolor_protection', 'orbit'])

    def write(self, name, value):
        p = self.base / name
        p.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
        return dict(path=name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())

    def change_json(self, section, filename, mutate):
        value = json.loads((self.base / section['path']).read_text())
        mutate(value)
        return self.write(filename, value)

    def check(self, phase='delivery'):
        return evaluate(self.report, self.base, phase)

    def test_resume_and_delivery(self):
        self.assertTrue(self.check('resume')['passed'])
        self.assertTrue(self.check()['passed'])

    def test_uninstalled_sample_not_mistaken_for_production(self):
        self.report['production']['observation'] = self.report['installed']['observation']
        self.assertFalse(self.check('resume')['passed'])

    def test_wrong_source(self):
        self.report['installed']['target']['source'] = 'claude'
        self.assertFalse(self.check()['passed'])

    def test_stale_registry(self):
        (self.base / self.registry_after['path']).write_bytes(b'changed registration')
        self.assertFalse(self.check()['passed'])

    def test_current_resource_changed(self):
        (self.base / self.old['path']).write_bytes(b'changed production')
        self.assertFalse(self.check('resume')['passed'])

    def test_missing_inherited_work(self):
        self.report['inheritance'] = []
        self.assertFalse(self.check('resume')['passed'])

    def test_duplicate_inherited_work(self):
        self.report['inheritance'] *= 2
        self.assertFalse(self.check()['passed'])

    def test_unknown_baseline(self):
        self.report['baseline'] = self.new
        self.assertFalse(self.check('resume')['passed'])

    def test_explicit_deferral_is_reported_not_forced_merge(self):
        self.report['baseline'] = self.old
        self.report['baseline_reason'] = 'Minimal production fix, sample remains isolated'
        self.report['inheritance'][0].update(status='deferred', reason='Shape sample not part of this repair')
        result = self.check('resume')
        self.assertTrue(result['passed'])
        self.assertEqual(result['deferred'], ['shape'])

    def test_wrong_candidate_in_inheritance_evidence(self):
        self.report['inheritance'][0]['evidence'] = self.write('bad-inherit.json', dict(work_id='shape', candidate_sha256=self.old['sha256'], passed=True))
        self.assertFalse(self.check()['passed'])

    def test_stale_adoption_evidence(self):
        (self.base / 'capture.png').write_bytes(b'changed image')
        self.assertFalse(self.check()['passed'])

    def test_regressed_or_uncertain_not_delivered(self):
        for verdict in ('regressed', 'uncertain'):
            with self.subTest(verdict=verdict):
                self.report['adoption_review'] = self.change_json(self.report['adoption_review'], 'review-' + verdict + '.json',
                    lambda r: r['regions'][0].update(verdict=verdict))
                self.assertFalse(self.check()['passed'])

    def test_adoption_for_another_candidate(self):
        self.report['adoption_review'] = self.change_json(self.report['adoption_review'], 'wrong-adopt.json', lambda r: r.update(candidate=self.old))
        self.assertFalse(self.check()['passed'])

    def test_actual_loaded_old_model(self):
        self.report['installed']['observation'] = self.change_json(self.report['installed']['observation'], 'old-loaded.json', lambda r: r.update(asset_sha256=self.old['sha256']))
        self.assertFalse(self.check()['passed'])

    def test_missing_function_or_navigation(self):
        for operation in ('switch_return', 'reset', 'recolor_protection', 'orbit'):
            with self.subTest(operation=operation):
                saved = copy.deepcopy(self.report['installed']['observation'])
                self.report['installed']['observation'] = self.change_json(saved, 'fail-' + operation + '.json', lambda r: r['checks'].update({operation: False}))
                self.assertFalse(self.check()['passed'])
                self.report['installed']['observation'] = saved

    def test_browser_not_ready_or_has_errors(self):
        self.report['installed']['observation'] = self.change_json(self.report['installed']['observation'], 'errors.json', lambda r: r.update(ready=False, errors=['load failed']))
        self.assertFalse(self.check()['passed'])

    def test_missing_rollback(self):
        self.report['installed'].pop('rollback')
        self.assertFalse(self.check()['passed'])

    def test_no_prior_samples(self):
        self.report['inventory'] = self.write('empty-inventory.json', {'accepted_work': []})
        self.report['inheritance'] = []
        self.report['baseline'] = self.old
        self.assertTrue(self.check('resume')['passed'])

    def test_cli_is_read_only_except_new_result(self):
        record = self.write('record.json', self.report)
        before = {p.name: p.read_bytes() for p in self.base.iterdir()}
        script = Path(__file__).resolve().parents[1] / 'scripts/version_handoff.py'
        result = subprocess.run([sys.executable, str(script), str(self.base / record['path']), '--phase', 'delivery', '--out', str(self.base / 'result.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        for name, content in before.items():
            self.assertEqual((self.base / name).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
