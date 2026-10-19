#!/usr/bin/env python3
"""Explicit replay of an authorized local generator; read-only gates never execute it.

This is reproducibility evidence, not a sandbox or an image-fidelity certificate.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def contract(spec, root):
    root = Path(root).resolve()
    c = spec.get('external_geometry')
    need(isinstance(c, dict) and c.get('version') == 1, 'external geometry v1 contract required')
    ids = c.get('component_ids', [])
    nodes = {n['id']: n for n in spec['components']}
    need(ids and len(ids) == len(set(ids)) and set(ids) <= set(nodes), 'unique real external components required')
    need(all(nodes[k]['geometry']['type'] == 'mesh' for k in ids), 'external targets must be explicit meshes')
    resources = {r['path']: r['sha256'] for r in spec['source_files']}
    entries = [c['generator']] + c.get('inputs', [])
    need(c.get('inputs') and len({e['path'] for e in entries}) == len(entries), 'distinct generator/input resources required')
    paths = []
    for entry in entries:
        name = entry['path']
        p = (root / name).resolve()
        need(not Path(name).is_absolute() and p.is_relative_to(root) and p.is_file(), 'generator/input must be inside project')
        need(resources.get(name) == entry.get('sha256') == sha(p), 'stale or unregistered external resource: ' + name)
        paths.append(p)
    need(paths[0].suffix == '.py', 'only explicit local Python generator supported')
    links = c.get('parameter_components', {})
    need(links and set(links) <= set(spec['parameters']), 'external parameter bindings required')
    for key, selected in links.items():
        p = spec['parameters'][key]
        need(selected and len(selected) == len(set(selected)) and set(selected) <= set(ids), 'invalid external parameter component scope')
        need(all(type(p.get(k)) in (int, float) and math.isfinite(p[k]) for k in ('min', 'max', 'value')) and p['min'] < p['max'] and p['min'] <= p['value'] <= p['max'], 'external control must have finite variation range')
    need(set().union(*(set(v) for v in links.values())) == set(ids), 'every external component needs an effective control')
    tolerance = c.get('position_tolerance', 0)
    need(type(tolerance) in (int, float) and 0 <= tolerance <= 1e-7, 'external precision tolerance exceeds 1e-7 spec units')
    receipt = c.get('receipt')
    need(isinstance(receipt, str) and not Path(receipt).is_absolute() and (root / receipt).resolve().is_relative_to(root), 'project-local receipt required')
    return c, nodes, paths


def signature(spec, c):
    from scene_build import resolve
    nodes = {n['id']: n for n in spec['components']}
    return identity({'contract': c, 'parameters': {k: spec['parameters'][k] for k in c['parameter_components']},
                     'geometry': {k: resolve(nodes[k]['geometry'], spec['parameters']) for k in c['component_ids']}})


def mesh_set(result, ids):
    need(isinstance(result, dict) and result.get('version') == 1, 'generator output version1 required')
    out = result.get('geometries', {})
    need(isinstance(out, dict) and set(out) == set(ids), 'generator output component scope differs')
    for g in out.values():
        need(isinstance(g, dict) and g.get('type') == 'mesh', 'generator must output explicit mesh')
        need(set(g) <= {'type', 'positions', 'triangles', 'normals', 'uvs'}, 'unsupported generated mesh attribute')
        p, t = g.get('positions', []), g.get('triangles', [])
        need(p and len(p) % 3 == 0 and len(p) // 3 <= 300000, 'invalid generated vertex budget')
        need(all(type(x) in (int, float) and math.isfinite(x) for x in p), 'nonfinite generated vertices')
        need(t and len(t) % 3 == 0 and all(type(i) is int and 0 <= i < len(p) // 3 for i in t), 'invalid generated topology')
        for key, length in [('normals', len(p)), ('uvs', len(p) // 3 * 2)]:
            if key in g:
                need(len(g[key]) == length and all(type(x) in (int, float) and math.isfinite(x) for x in g[key]), 'invalid generated ' + key)
    return out


def same_geometry(actual, expected, tolerance):
    need(set(actual) == set(expected), 'generated mesh fields differ from compiled geometry')
    for k in actual:
        if k in ('positions', 'normals', 'uvs'):
            need(len(actual[k]) == len(expected[k]), 'generated mesh array length differs')
            limit = tolerance if k == 'positions' else 1e-9
            need(all(abs(a - b) <= limit for a, b in zip(actual[k], expected[k])), 'generated ' + k + ' differs from compiled geometry')
        else:
            need(actual[k] == expected[k], 'generated ' + k + ' differs from compiled geometry')


def replay(spec_path, allow_execution=False, output_path=None):
    need(allow_execution, 'generator execution requires explicit --allow-execution; inspect and authorize source first')
    p = Path(spec_path).resolve()
    spec = read(p)
    c, nodes, paths = contract(spec, p.parent)
    out = Path(output_path).resolve() if output_path else p.parent / c['receipt']
    need(out.is_relative_to(p.parent), 'replay output must remain inside project')
    need(not out.exists(), 'receipt exists; use a new receipt path for a new verification')
    from scene_build import resolve
    values = {k: spec['parameters'][k]['value'] for k in c['parameter_components']}

    def run(parameters):
        with tempfile.TemporaryDirectory(prefix='image-to-3d-replay-') as temp:
            work = Path(temp)
            # Only declared source/inputs are copied. This is isolation of inputs,
            # not OS security isolation; do not execute untrusted generators.
            script = work / 'generator.py'
            script.write_bytes(paths[0].read_bytes())
            inputs = []
            for index, source in enumerate(paths[1:]):
                dst = work / ('input-' + str(index) + source.suffix)
                dst.write_bytes(source.read_bytes())
                inputs.append(str(dst))
            request = work / 'request.json'
            request.write_text(json.dumps({'version': 1, 'parameters': parameters, 'inputs': inputs, 'component_ids': c['component_ids']}))
            output = work / 'output.json'
            env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'LANG') if k in os.environ}
            process = subprocess.run([sys.executable, '-I', str(script), '--input', str(request), '--out', str(output)], cwd=work,
                                     env=env, capture_output=True, timeout=60)
            need(process.returncode == 0, 'external generator failed: ' + process.stderr.decode(errors='replace')[:1000])
            need(output.is_file() and output.stat().st_size <= 256 * 1024 * 1024, 'missing/oversized generator output')
            result = mesh_set(read(output), c['component_ids'])
            # Recheck source bytes after execution, including attempted mutation.
            contract(spec, p.parent)
            need(script.read_bytes() == paths[0].read_bytes(), 'generator mutated its source copy')
            for dst, src in zip(inputs, paths[1:]):
                need(Path(dst).read_bytes() == src.read_bytes(), 'generator mutated a declared input copy')
            return result

    first, second = run(values), run(values)
    need(identity(first) == identity(second), 'external generator is nondeterministic')
    for cid in c['component_ids']:
        same_geometry(first[cid], resolve(nodes[cid]['geometry'], spec['parameters']), c['position_tolerance'])
    influence = {}
    for key, selected in c['parameter_components'].items():
        rule = spec['parameters'][key]
        proposed = dict(values)
        step = (rule['max'] - rule['min']) * .01
        proposed[key] = min(rule['max'], values[key] + step) if values[key] < rule['max'] else values[key] - step
        changed = run(proposed)
        affected = sorted(k for k in first if identity(first[k]) != identity(changed[k]))
        need(set(affected) == set(selected), 'control has no effect or unexpected scope: ' + key)
        influence[key] = affected
    report = {'version': 1, 'passed': True, 'identity': signature(spec, c), 'replay_runs': 2,
              'output_sha256': identity(first), 'component_ids': c['component_ids'], 'parameter_influence': influence,
              'scope': 'Deterministic authorized external generation only; reference, topology, connections and visual gates remain required.'}
    out.write_text(json.dumps(report, indent=2))
    return report


def readiness(spec, root):
    need(root is not None, 'external generator validation requires project resource root')
    c, nodes, paths = contract(spec, root)
    p = Path(root) / c['receipt']
    resources = {r['path']: r['sha256'] for r in spec['source_files']}
    need(p.is_file() and resources.get(c['receipt']) == sha(p), 'missing/stale external replay receipt')
    r = read(p)
    need(r.get('passed') is True and r.get('version') == 1 and r.get('replay_runs') == 2, 'successful double replay required')
    need(r.get('identity') == signature(spec, c), 'external controls/geometry changed since replay')
    need(r.get('component_ids') == c['component_ids'] and r.get('parameter_influence') == {k: sorted(v) for k, v in c['parameter_components'].items()}, 'external replay scope differs')
    return set(c['component_ids'])


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--spec', required=True)
    a.add_argument('--allow-execution', action='store_true')
    a.add_argument('--out', help='New project-local report; explicit adoption into the registered receipt is separate')
    x = a.parse_args()
    try:
        r = replay(x.spec, x.allow_execution, x.out)
        print(json.dumps({'passed': r['passed'], 'components': r['component_ids'], 'replay_runs': r['replay_runs']}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        print(json.dumps({'passed': False, 'error': str(e)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
