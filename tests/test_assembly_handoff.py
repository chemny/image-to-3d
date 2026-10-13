import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

s = importlib.util.spec_from_file_location('handoff', Path(__file__).resolve().parents[1] / 'scripts' / 'assembly_handoff.py')
h = importlib.util.module_from_spec(s); s.loader.exec_module(h)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('source.json', 'contract.json', 'front.js', 'rear.js'):
            (self.root / name).write_text(name)
        self.plan = self.root / 'plan.json'; self.manifest = self.root / 'manifest.json'; self.receipt = self.root / 'receipt.json'
        self.data = {'root': str(self.root), 'inputs': ['source.json'], 'contracts': ['contract.json'],
                     'review_paths': ['.'], 'metadata_paths': ['plan.json', 'manifest.json', 'receipt.json'],
                     'tasks': [{'id': 'front', 'writes': ['front.js']}, {'id': 'rear', 'writes': ['rear.js']}]}

    def start(self):
        self.plan.write_text(json.dumps(self.data)); h.init(self.plan, self.manifest)

    def receipt_for(self, path='front.js'):
        (self.root / path).write_text('changed ' + path)
        self.receipt.write_text(json.dumps({'task_id': 'front', 'manifest_sha256': h.sha(self.manifest), 'changed_paths': [path], 'artifacts': {path: h.sha(self.root / path)}}))

    def test_valid_claim_and_receipt(self):
        self.start(); self.assertEqual(h.claim(self.manifest, 'front')['task']['writes'], ['front.js'])
        self.receipt_for(); self.assertTrue(h.check(self.manifest, self.receipt)['valid'])

    def test_overlap_rejected(self):
        self.data['tasks'][1]['writes'] = ['front.js']
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.start()
        self.assertFalse(self.manifest.exists())

    def test_traversal_rejected(self):
        self.data['tasks'][0]['writes'] = ['../front.js']
        with self.assertRaisesRegex(ValueError, 'traversal'):
            self.start()

    def test_absolute_rejected(self):
        self.data['tasks'][0]['writes'] = [str(self.root / 'front.js')]
        with self.assertRaisesRegex(ValueError, 'traversal'):
            self.start()

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'escape').symlink_to(outside, target_is_directory=True)
            self.data['tasks'][0]['writes'] = ['escape/model.js']
            with self.assertRaisesRegex(ValueError, 'symlink'):
                self.start()

    def test_input_drift_rejected(self):
        self.start(); self.receipt_for(); (self.root / 'source.json').write_text('new source')
        with self.assertRaisesRegex(ValueError, 'stale/missing inputs'):
            h.check(self.manifest, self.receipt)

    def test_contract_drift_rejected(self):
        self.start(); (self.root / 'contract.json').write_text('new boundary')
        with self.assertRaisesRegex(ValueError, 'stale/missing contracts'):
            h.claim(self.manifest, 'front')

    def test_unauthorized_receipt_rejected(self):
        self.start(); self.receipt_for('rear.js')
        with self.assertRaisesRegex(ValueError, 'receipt does not match'):
            h.check(self.manifest, self.receipt)

    def test_missing_output_rejected(self):
        self.start(); self.receipt_for(); (self.root / 'front.js').unlink()
        with self.assertRaisesRegex(ValueError, 'missing/stale artifact'):
            h.check(self.manifest, self.receipt)

    def test_modified_output_rejected(self):
        self.start(); self.receipt_for(); (self.root / 'front.js').write_text('unreviewed edit')
        with self.assertRaisesRegex(ValueError, 'missing/stale artifact'):
            h.check(self.manifest, self.receipt)

    def test_stale_manifest_rejected(self):
        self.start(); self.receipt_for()
        with self.manifest.open('a') as f: f.write(' ')
        with self.assertRaisesRegex(ValueError, 'stale manifest'):
            h.check(self.manifest, self.receipt)

    def test_writable_contract_rejected(self):
        self.data['tasks'][0]['writes'] = ['contract.json']
        with self.assertRaisesRegex(ValueError, 'cannot be writable'):
            self.start()

    def test_underreported_changes_rejected(self):
        self.data['tasks'][0]['writes'].append('extra.js')
        self.start(); self.receipt_for()
        (self.root / 'extra.js').write_text('hidden')
        with self.assertRaisesRegex(ValueError, 'actual task changes'):
            h.check(self.manifest, self.receipt)

    def test_unknown_file_modification_rejected(self):
        (self.root / 'unowned.js').write_text('before')
        self.start(); self.receipt_for(); (self.root / 'unowned.js').write_text('after')
        with self.assertRaisesRegex(ValueError, 'undeclared file changes'):
            h.check(self.manifest, self.receipt)

    def test_unknown_new_file_rejected(self):
        self.start(); self.receipt_for(); (self.root / 'hidden.js').write_text('new')
        with self.assertRaisesRegex(ValueError, 'undeclared file changes'):
            h.check(self.manifest, self.receipt)

    def test_unknown_deletion_rejected(self):
        (self.root / 'unowned.js').write_text('before')
        self.start(); self.receipt_for(); (self.root / 'unowned.js').unlink()
        with self.assertRaisesRegex(ValueError, 'undeclared file changes'):
            h.check(self.manifest, self.receipt)

    def test_parallel_changes_reported_unreviewed(self):
        self.start(); self.receipt_for(); (self.root / 'rear.js').write_text('other task')
        self.assertEqual(h.check(self.manifest, self.receipt)['unreviewed_tasks'], ['rear'])

    def test_explicit_deletion_receipt(self):
        self.start(); self.receipt_for(); (self.root / 'front.js').unlink()
        receipt = h.read(self.receipt); receipt['artifacts']['front.js'] = None
        self.receipt.write_text(json.dumps(receipt))
        self.assertTrue(h.check(self.manifest, self.receipt)['valid'])

    def make_parallel_receipts(self):
        self.data['metadata_paths'].append('rear-receipt.json')
        self.start(); self.receipt_for()
        (self.root / 'rear.js').write_text('rear changed')
        rear = self.root / 'rear-receipt.json'
        rear.write_text(json.dumps({'task_id': 'rear', 'manifest_sha256': h.sha(self.manifest),
                                   'changed_paths': ['rear.js'], 'artifacts': {'rear.js': h.sha(self.root / 'rear.js')}}))
        return rear

    def test_all_receipts_complete(self):
        rear = self.make_parallel_receipts()
        self.assertTrue(h.check_all(self.manifest, [self.receipt, rear])['integration_ready'])

    def test_all_receipts_missing_task(self):
        self.make_parallel_receipts()
        with self.assertRaisesRegex(ValueError, 'missing task receipts'):
            h.check_all(self.manifest, [self.receipt])

    def test_all_receipts_duplicate_task(self):
        rear = self.make_parallel_receipts()
        with self.assertRaisesRegex(ValueError, 'duplicate task'):
            h.check_all(self.manifest, [self.receipt, rear, self.receipt])

    def test_all_receipts_source_drift(self):
        rear = self.make_parallel_receipts()
        (self.root / 'source.json').write_text('drift')
        with self.assertRaisesRegex(ValueError, 'stale/missing inputs'):
            h.check_all(self.manifest, [self.receipt, rear])

    def test_nested_write_ownership_rejected(self):
        self.data['tasks'][0]['writes'] = ['nested']
        self.data['tasks'][1]['writes'] = ['nested/file.js']
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.start()


if __name__ == '__main__':
    unittest.main()
