#!/usr/bin/env python3
"""Reproducible software experiment, never a photographic acceptance shortcut."""
import argparse
import hashlib
import json
from pathlib import Path
from workflow import validate_spec
from surface_model import build, javascript
from fit_surface import fit


def run(spec_path, output, parameters):
    spec, resources = validate_spec(spec_path)
    if spec['quality_contract']['scope'] != 'synthetic-software-test':
        raise ValueError('This runner is test-only; real reconstruction needs an explicit camera/build adapter')
    # Resolve and compute before creating an output directory; input failures leave no partial bundle.
    result = fit(spec, parameters)
    before, after = build(spec), build(result['spec'])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    files = {'before.mesh.json': before, 'after.mesh.json': after, 'fit.json': result}
    for name, value in files.items():
        (output / name).write_text(json.dumps(value, indent=2) + '\n')
    for name, mesh in [('before.mjs', before), ('after.mjs', after)]:
        (output / name).write_text(javascript(mesh))
    report = {
        'scope': 'synthetic-software-test', 'photographic_acceptance': False,
        'input_spec_sha256': hashlib.sha256(Path(spec_path).read_bytes()).hexdigest(),
        'resources': resources, 'heldout_used_for_search': result['heldout_used_for_search'],
        'initial_objective': result['initial_score'], 'final_objective': result['final_score'],
        'heldout_initial_errors': result['heldout_initial_errors'],
        'heldout_final_errors': result['heldout_final_errors'],
        'artifacts': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())},
        'limits': ['Open analytic surface only', 'No browser-render or photo-fidelity acceptance',
                   'Does not advance workflow gates', 'fit.json embeds a diagnostic spec; rebase resource paths before reuse'],
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('spec'); p.add_argument('--out', required=True)
    p.add_argument('--parameters', nargs='+', required=True)
    a = p.parse_args()
    print(json.dumps(run(a.spec, a.out, a.parameters), indent=2))
