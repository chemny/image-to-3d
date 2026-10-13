import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from experiment_bundle import run


class IntegrationTests(unittest.TestCase):
    def test_real_fixture_contract_build_fit_export(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'bundle'
            result = run(ROOT / 'examples/synthetic-surface-spec.json', out, ['height', 'nose_drop'])
            self.assertFalse(result['photographic_acceptance'])
            self.assertFalse(result['heldout_used_for_search'])
            self.assertLess(result['final_objective'], result['initial_objective'] * .001)
            self.assertIn('after.mjs', result['artifacts'])
            mesh = json.loads((out / 'after.mesh.json').read_text())
            self.assertEqual(len(mesh['components']), 1)
            with self.assertRaises(FileExistsError):
                run(ROOT / 'examples/synthetic-surface-spec.json', out, ['height'])


if __name__ == '__main__': unittest.main()
