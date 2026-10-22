import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import version_lifecycle as v


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ['live', 'old', 'shared', 'accepted', 'pending']:
            (self.root / name).mkdir()
            (self.root / name / 'model.bin').write_bytes(name.encode() * 10)
        (self.root / 'cases.js').write_text("load('live/model.bin')")
        (self.root / 'decision.json').write_text('{"retired":"old"}')
        self.record = {'path': 'decision.json', 'sha256': v.digest((self.root / 'decision.json').read_bytes())}
        self.data = {'version': 1, 'coverage_complete': True, 'scan_files': ['cases.js'],
                     'units': [self.unit('live', 'active', ['shared']), self.unit('old', 'retired'),
                               self.unit('shared', 'retired'), self.unit('accepted', 'accepted'),
                               self.unit('pending', 'working')]}
        self.ledger = self.root / 'ledger.json'
        self.save()

    def unit(self, name, status, deps=None):
        return {'id': name, 'path': name, 'status': status, 'dependencies': deps or [],
                'reason': 'superseded, inputs preserved', 'retirement_evidence': self.record}

    def save(self):
        self.ledger.write_text(json.dumps(self.data))

    def plan(self):
        self.save()
        return v.plan(self.root, self.ledger)

    def eligible(self):
        return [r['id'] for r in self.plan()['units'] if r['eligible']]

    def apply(self):
        p = self.plan(); f = self.root / 'plan.json'; v.write_new(f, p)
        return v.quarantine(self.root, f, p['plan_sha256'])

    def test_protected_and_shared_dependency(self):
        self.assertEqual(self.eligible(), ['old'])

    def test_unknown_protected(self):
        self.data['units'][1]['status'] = 'unknown'
        self.assertEqual(self.eligible(), [])

    def test_original_source_and_rollback_protected(self):
        for status in ['source', 'evidence', 'rollback']:
            self.data['units'][1]['status'] = status
            self.assertEqual(self.eligible(), [])

    def test_incomplete_coverage(self):
        self.data['coverage_complete'] = False
        self.assertEqual(self.eligible(), [])

    def test_direct_reference_even_if_retired(self):
        (self.root / 'cases.js').write_text("load('/outputs/old/model.bin')")
        self.assertEqual(self.eligible(), [])

    def test_explicit_protected_path(self):
        self.data['protected_paths'] = ['old/model.bin']
        self.assertEqual(self.eligible(), [])

    def test_missing_retirement_evidence(self):
        self.data['units'][1].pop('retirement_evidence')
        self.assertEqual(self.eligible(), [])

    def test_stale_evidence(self):
        (self.root / 'decision.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'stale retirement'):
            self.plan()

    def test_plan_read_only_and_space(self):
        before = (self.root / 'old/model.bin').read_bytes()
        p = self.plan()
        self.assertEqual(p['quarantine_bytes'], len(before))
        self.assertEqual(p['reclaimed_bytes'], 0)
        self.assertEqual((self.root / 'old/model.bin').read_bytes(), before)

    def test_quarantine_restore_and_idempotent_restore(self):
        original = v.snapshot(self.root / 'old')
        result = self.apply()
        self.assertFalse((self.root / 'old').exists())
        self.assertTrue((self.root / 'live/model.bin').exists())
        self.assertEqual(result['reclaimed_bytes'], 0)
        self.assertEqual(v.restore(self.root, result['transaction'])['restored'], 1)
        self.assertEqual(v.snapshot(self.root / 'old'), original)
        self.assertEqual(v.restore(self.root, result['transaction'])['restored'], 0)

    def test_restore_refuses_overwrite(self):
        result = self.apply()
        (self.root / 'old').mkdir()
        (self.root / 'old/new').write_text('new work')
        with self.assertRaisesRegex(ValueError, 'occupied'):
            v.restore(self.root, result['transaction'])
        self.assertEqual((self.root / 'old/new').read_text(), 'new work')

    def test_changed_quarantined_data(self):
        result = self.apply()
        (self.root / result['transaction'] / '0/model.bin').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'changed'):
            v.restore(self.root, result['transaction'])

    def test_stale_model_registry_and_ledger(self):
        for target in ['old/model.bin', 'cases.js', 'ledger.json']:
            p = self.plan(); f = self.root / 'plan-stale.json'; f.write_text(json.dumps(p))
            original = (self.root / target).read_bytes()
            (self.root / target).write_bytes(original + b' ')
            with self.assertRaises(ValueError):
                v.quarantine(self.root, f, p['plan_sha256'])
            (self.root / target).write_bytes(original)
        self.assertTrue((self.root / 'old').exists())

    def test_wrong_approval_and_edited_plan(self):
        p = self.plan(); f = self.root / 'plan.json'; f.write_text(json.dumps(p))
        with self.assertRaises(ValueError):
            v.quarantine(self.root, f, 'bad')
        p['units'][0]['eligible'] = True; f.write_text(json.dumps(p))
        with self.assertRaises(ValueError):
            v.quarantine(self.root, f, p['plan_sha256'])

    def test_symlink_escape_and_hardlink(self):
        (self.root / 'old/link').symlink_to('/tmp')
        with self.assertRaises(ValueError): self.plan()
        (self.root / 'old/link').unlink()
        os.link(self.root / 'old/model.bin', self.root / 'old/alias')
        with self.assertRaises(ValueError): self.plan()

    def test_path_traversal_overlap_duplicate_and_unknown_dependency(self):
        for mutate in [lambda: self.data['units'][1].update(path='../outside'),
                       lambda: self.data['units'][1].update(path='live/model.bin'),
                       lambda: self.data['units'][1].update(id='live'),
                       lambda: self.data['units'][1].update(dependencies=['missing'])]:
            original = json.loads(json.dumps(self.data)); mutate()
            with self.assertRaises(ValueError): self.plan()
            self.data = original

    def test_lock_blocks_simultaneous_cleanup(self):
        with v.lock(self.root):
            with self.assertRaises(FileExistsError): self.apply()
        self.assertTrue((self.root / 'old').exists())

    def test_record_container_and_its_dependencies_protected(self):
        (self.root / 'old/approval.json').write_text('external evidence')
        self.data['units'][2]['retirement_evidence'] = {'path': 'old/approval.json', 'sha256': v.digest(b'external evidence')}
        self.data['units'][1]['dependencies'] = ['shared']
        self.assertEqual(self.eligible(), [])

    def test_partial_transaction_recoverable(self):
        self.data['units'].append(self.unit('pending', 'retired'))
        self.data['units'] = [u for u in self.data['units'] if not (u['id'] == 'pending' and u['status'] == 'working')]
        original = Path.rename
        def fail_second(p, dest):
            if p.name == 'pending': raise OSError('simulated interruption')
            return original(p, dest)
        with patch.object(Path, 'rename', fail_second):
            with self.assertRaises(OSError): self.apply()
        tx = next((self.root / '.model-quarantine').iterdir())
        self.assertEqual(v.restore(self.root, str(tx.relative_to(self.root)))['restored'], 1)
        self.assertTrue((self.root / 'pending/model.bin').exists())

    def test_inventory_is_never_cleanup_authorization(self):
        result = v.inventory(self.root)
        self.assertEqual(result['eligible_bytes'], 0)
        self.assertTrue(all(not r['eligible'] for r in result['units']))
        self.assertTrue((self.root / 'old').exists())

    def test_inventory_explicit_scan_and_allocated_bytes(self):
        (self.root / 'cases.js').write_text("'/outputs/live/model.bin'")
        result = v.inventory(self.root, ['cases.js'])
        rows = {r['path']: r for r in result['units']}
        self.assertEqual(rows['live']['status'], 'referenced-review-required')
        self.assertFalse(rows['live']['eligible'])
        self.assertEqual(result['total_allocated_bytes'], sum(r['allocated_bytes'] for r in result['units']))

    def test_cli_refuses_existing_output_before_mutation(self):
        import subprocess
        p = self.plan(); f = self.root / 'plan.json'; f.write_text(json.dumps(p))
        out = self.root / 'result.json'; out.write_text('preserve')
        result = subprocess.run([__import__('sys').executable, v.__file__, 'quarantine',
                                 '--root', str(self.root), '--plan', str(f),
                                 '--approve-sha256', p['plan_sha256'], '--out', str(out)],
                                capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(out.read_text(), 'preserve')
        self.assertTrue((self.root / 'old/model.bin').exists())

    def test_empty_scan_claim_refused(self):
        self.data['scan_files'] = []
        with self.assertRaises(ValueError): self.plan()


if __name__ == '__main__': unittest.main()
