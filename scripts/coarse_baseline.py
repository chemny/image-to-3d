#!/usr/bin/env python3
"""Freeze an independently remeasured numeric coarse baseline; never visual adoption.

No optimizer is called. Identities detect stale/mismatched evidence, not hostile
forgery of both inputs and reports. The original pre-fit Spec is not an argument:
its identity and protected-before hashes are crosslinks, not re-derived provenance.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import coarse_initialization as core
import scene_build
from reconstruction import project


def full_geometry_identity(payload):
    return core.full_geometry_identity(payload)


def _equal(actual, expected, label):
    core.need(actual == expected, 'stale or inconsistent ' + label)


def _numeric(actual, expected, label):
    if expected is None:
        core.need(actual is None, 'inconsistent ' + label)
    elif isinstance(expected, (list, tuple)):
        core.need(isinstance(actual, (list, tuple)) and len(actual) == len(expected),
                  'inconsistent ' + label)
        for i, (a, b) in enumerate(zip(actual, expected)):
            _numeric(a, b, label + '[' + str(i) + ']')
    else:
        core.need(type(actual) in (int, float) and np.isfinite(actual)
                  and np.isclose(actual, expected, rtol=1e-7, atol=1e-8),
                  'inconsistent ' + label)


def _validate(candidate, contract):
    core.keys(contract, ('version', 'spec_identity', 'rationale', 'gauge',
                        'protected_component_ids', 'max_condition', 'reject_bound_hits',
                        'variable_ids', 'geometry_parameter_ids', 'camera_builders',
                        'curves', 'seeds'), 'joint contract')
    core.need(type(contract.get('version')) is int and contract['version'] == 1,
              'joint contract version 1 required')
    for key in ('spec_identity', 'rationale', 'gauge'):
        core.need(isinstance(contract.get(key), str) and contract[key].strip(), key + ' required')
    ids = contract.get('variable_ids'); geom = contract.get('geometry_parameter_ids')
    for label, value in (('variable_ids', ids), ('geometry_parameter_ids', geom),
                         ('protected_component_ids', contract.get('protected_component_ids'))):
        core.need(isinstance(value, list) and all(isinstance(x, str) and x for x in value)
                  and len(value) == len(set(value)), label + ' requires unique IDs')
    core.need(ids and set(geom) <= set(ids), 'nonempty variables and geometry subset required')
    core.number(contract.get('max_condition'), 'max_condition', True)
    core.need(type(contract.get('reject_bound_hits')) is bool, 'boundary rule required')
    parameters = candidate.get('parameters', {}); lower = []; spans = []
    for key in ids:
        core.need(key in parameters, 'unknown fitting parameter: ' + key)
        p = parameters[key]; vals = [core.number(p.get(k), 'parameter ' + key) for k in ('min', 'value', 'max')]
        core.need(vals[0] < vals[2] and vals[0] <= vals[1] <= vals[2], 'invalid immutable bounds: ' + key)
        lower.append(vals[0]); spans.append(vals[2] - vals[0])
    nodes = core.index(candidate.get('components', []), 'components')
    protected = contract['protected_component_ids']
    core.need(set(protected) <= set(nodes), 'unknown protected component')
    builders = contract.get('camera_builders'); cameras = core.index(candidate.get('cameras', {}), 'cameras')
    core.need(isinstance(builders, dict) and builders and set(builders) <= set(cameras), 'declared builders required')
    cams = {key: core.camera(b, parameters) for key, b in builders.items()}
    for key, cam in cams.items():
        core._same_camera(scene_build.resolve(cameras[key], parameters), cam)
    links = {key: [] for key in ids}
    for key, node in nodes.items():
        for ref, path in core.parameter_refs(node):
            pid = ref.get('param')
            if pid not in links: continue
            core.need(pid in geom and path and path[0] in ('geometry', 'position', 'rotation'),
                      'camera-only or forbidden component mutation: ' + pid)
            if path[0] == 'geometry':
                core.need(path[1:2] == ('positions',), 'geometry variable needs actual mesh positions')
            core.need(key not in protected, 'protected component parameter mutation')
            links[pid].append((key, path))
    for field, value in candidate.items():
        if field not in ('components', 'parameters', 'cameras'):
            core.need(not any(r.get('param') in ids for r, _ in core.parameter_refs(value)), 'variable affects forbidden field: ' + field)
    for key, value in cameras.items():
        for ref, _ in core.parameter_refs(value):
            if ref.get('param') in ids: core.need(key in builders, 'variable affects undeclared camera')
    builder_ids = {r.get('param') for b in builders.values() for r, _ in core.parameter_refs(b)}
    for key in ids:
        core.need(bool(links[key]) if key in geom else key in builder_ids, 'variable has no actual effect: ' + key)
    for key in protected:
        cursor = nodes[key].get('parent'); seen = set()
        while cursor is not None:
            core.need(cursor in nodes and cursor not in seen, 'cyclic or missing ancestor'); seen.add(cursor)
            core.need(not any(r.get('param') in ids for field in ('position', 'rotation')
                              for r, _ in core.parameter_refs(nodes[cursor].get(field))), 'protected ancestor mutation')
            cursor = nodes[cursor].get('parent')
    curves = contract.get('curves'); core.need(isinstance(curves, list) and curves, 'curves required')
    references = core.index(candidate.get('references', []), 'references'); cids = set(); sids = set()
    for curve in curves:
        core.keys(curve, ('id', 'camera_id', 'reference_id', 'bindings', 'closed', 'samples', 'max_error_px'), 'curve')
        cid = curve.get('id'); core.need(isinstance(cid, str) and cid and cid not in cids, 'unique curve IDs required'); cids.add(cid)
        core.need(curve.get('camera_id') in builders and curve.get('reference_id') in references, 'curve camera/reference missing')
        cam = cams[curve['camera_id']]
        core.need(references[curve['reference_id']].get('image_size') == [cam['width'], cam['height']], 'camera/reference size mismatch')
        core.need(type(curve.get('closed')) is bool, 'explicit closed flag required')
        core.number(curve.get('max_error_px'), 'max_error_px', True)
        bindings = curve.get('bindings')
        core.need(isinstance(bindings, list) and len(bindings) >= (3 if curve['closed'] else 2), 'curve binding count')
        for b in bindings:
            core.keys(b, ('component_id', 'vertex_index'), 'binding'); key = b.get('component_id'); i = b.get('vertex_index')
            core.need(key in nodes and nodes[key].get('geometry', {}).get('type') == 'mesh', 'binding needs real mesh')
            core.need(type(i) is int and 0 <= i < len(nodes[key]['geometry'].get('positions', [])) // 3, 'invalid mesh vertex')
        core.need(len({(b['component_id'], b['vertex_index']) for b in bindings}) == len(bindings), 'duplicate binding')
        pairs = list(zip(bindings, bindings[1:])) + ([(bindings[-1], bindings[0])] if curve['closed'] else [])
        for a, b in pairs:
            core.need(a['component_id'] == b['component_id'], 'curve needs actual shared triangle edges')
            tri = nodes[a['component_id']]['geometry']['triangles']
            edges = {tuple(sorted(e)) for k in range(0, len(tri), 3) for e in
                     ((tri[k], tri[k+1]), (tri[k+1], tri[k+2]), (tri[k+2], tri[k]))}
            core.need(tuple(sorted((a['vertex_index'], b['vertex_index']))) in edges, 'binding is not an actual triangle edge')
        counts = {'calibration': 0, 'validation': 0}; core.need(isinstance(curve.get('samples'), list), 'samples required')
        for sample in curve['samples']:
            core.keys(sample, ('id', 'role', 'pixel', 'sigma_px'), 'sample'); sid = sample.get('id')
            core.need(isinstance(sid, str) and sid and sid not in sids, 'unique sample IDs required'); sids.add(sid)
            core.need(sample.get('role') in counts, 'invalid sample role'); counts[sample['role']] += 1
            scene_build.vector(sample.get('pixel'), 2); core.number(sample.get('sigma_px'), 'sigma_px', True)
        core.need(counts['calibration'] >= 4 and counts['validation'] >= 2, 'each curve needs calibration and held-out coverage')
    return nodes, cams, np.asarray(lower), np.asarray(spans)


def verify(candidate, contract, fit_report, resource_root):
    """Remeasure current candidate, frozen targets/resources and calibration-only rank."""
    receipt = {'version': 1, 'passed': False, 'eligible_for_freeze': False,
               'visual_fidelity_accepted': False, 'production_accepted': False,
               'optimization_performed': False, 'heldout_used_for_optimization': False,
               'errors': [], 'scope': 'Numeric coarse baseline only; directed traced visible samples, no full contour/visibility/visual or production acceptance.',
               'provenance_limit': 'Initial Spec and protected-before identities are report/contract crosslinks; original input bytes are not independently supplied or cryptographically authenticated.'}
    try:
        core.need(isinstance(candidate, dict) and isinstance(contract, dict), 'candidate and contract objects required')
        core.need(isinstance(fit_report, dict) and type(fit_report.get('version')) is int and fit_report['version'] == 1, 'fit report version required')
        _equal(fit_report.get('candidate_spec_sha256'), core.digest(candidate), 'candidate identity')
        _equal(fit_report.get('contract_sha256'), core.digest(contract), 'contract identity')
        _equal(fit_report.get('initial_spec_sha256'), contract.get('spec_identity'), 'initial contract/spec crosslink')
        core.need(all(isinstance(fit_report.get(k), str) and re.fullmatch(r'[0-9a-f]{64}', fit_report[k])
                      for k in ('initial_spec_sha256', 'initial_full_geometry_sha256')),
                  'initial Spec/geometry identity crosslinks required')
        core.need(fit_report.get('visual_fidelity_accepted') is False and fit_report.get('production_accepted') is False,
                  'fit report cannot claim visual/production acceptance')
        nodes, cams, lower, spans = _validate(candidate, contract)
        payload = scene_build.build(candidate); curves = contract['curves']; full = core._full_curves(payload, curves)
        sparse = core._sparse_curves(nodes, curves, candidate['parameters'])
        core.need(all(np.allclose(full[k], sparse[k], rtol=0, atol=1e-9) for k in full), 'actual full/sparse curve mismatch')
        full_hash = full_geometry_identity(payload)
        _equal(fit_report.get('full_calibrated_geometry_sha256'), full_hash, 'full calibrated geometry')
        _equal(fit_report.get('actual_geometric_curves_sha256'), core.digest(sparse), 'actual curves')
        _equal(fit_report.get('camera_sha256'), core.digest(cams), 'camera builders')
        protection = core._protection(payload, contract['protected_component_ids'])
        _equal(fit_report.get('protected_geometry_hashes_after'), protection, 'current protected geometry')
        _equal(fit_report.get('protected_geometry_hashes_before'), protection, 'protected before/after geometry')
        verified, errors, images, sources = core._resources(candidate, curves, resource_root)
        core.need(verified, 'resource verification failed: ' + '; '.join(errors))
        _equal(fit_report.get('source_images'), images, 'source image identities')
        _equal(fit_report.get('source_files'), sources, 'source file identities')
        ids = contract['variable_ids']; x = np.asarray([(candidate['parameters'][k]['value']-lo)/span for k, lo, span in zip(ids, lower, spans)])
        def residual(at, role='calibration', details=False):
            params = copy.deepcopy(candidate['parameters'])
            for key, value in zip(ids, lower + at * spans): params[key]['value'] = float(value)
            current_cams = {key: core.camera(b, params) for key, b in contract['camera_builders'].items()}
            worlds = core._sparse_curves(nodes, curves, params); values = []; rows = []
            for curve in curves:
                polyline = [project(p, current_cams[curve['camera_id']]) for p in worlds[curve['id']]]
                for sample in curve['samples']:
                    if sample['role'] != role: continue
                    nearest, segment, t = core._nearest(sample['pixel'], polyline, curve['closed'])
                    delta = nearest - np.asarray(sample['pixel']); error = float(np.linalg.norm(delta)); values.extend((delta/sample['sigma_px']).tolist())
                    rows.append(dict(id=sample['id'], curve_id=curve['id'], role=role, pixel=sample['pixel'], nearest_pixel=nearest.tolist(),
                                     segment_index=segment, segment_fraction=t, error_px=error, sigma_px=sample['sigma_px'],
                                     max_error_px=curve['max_error_px'], passed=error <= curve['max_error_px']))
            return (np.asarray(values), rows) if details else np.asarray(values)
        calibration_residual, calibration = residual(x, details=True)
        _, validation = residual(x, 'validation', True)
        for name, rows in (('calibration', calibration), ('validation', validation)):
            declared = fit_report.get(name)
            core.need(isinstance(declared, list) and len(declared) == len(rows), 'missing ' + name + ' metrics')
            for actual, expected in zip(declared, rows):
                core.need(isinstance(actual, dict), 'sample metric must be an object')
                for key in ('id', 'curve_id', 'role', 'pixel', 'sigma_px', 'max_error_px', 'passed', 'segment_index'):
                    _equal(actual.get(key), expected[key], name + ' sample ' + key)
                for key in ('nearest_pixel', 'segment_fraction', 'error_px'):
                    _numeric(actual.get(key), expected[key], name + ' sample ' + key)
        columns = []
        for i in range(len(ids)):
            lo, hi = max(0., float(x[i])-1e-5), min(1., float(x[i])+1e-5)
            left, right = x.copy(), x.copy(); left[i] = lo; right[i] = hi
            columns.append((residual(right)-residual(left))/(hi-lo))
        j = np.stack(columns, axis=1); singular = np.linalg.svd(j, compute_uv=False); rank = int(np.linalg.matrix_rank(j))
        condition = float(singular[0]/singular[-1]) if rank == len(ids) and singular[-1] > 0 else None
        jr = fit_report.get('data_jacobian', {})
        core.need(isinstance(jr, dict), 'data Jacobian report must be an object')
        for key, expected in (('rank', rank), ('variable_count', len(ids)), ('max_condition', contract['max_condition'])):
            _equal(jr.get(key), expected, 'data Jacobian ' + key)
        _numeric(jr.get('condition'), condition, 'data Jacobian condition'); _numeric(jr.get('singular_values'), singular.tolist(), 'data Jacobian singular values')
        sse = float(np.dot(calibration_residual, calibration_residual)); _numeric(fit_report.get('calibration_sse'), sse, 'calibration SSE')
        bounds = [key for key, value in zip(ids, x) if value <= 1e-6 or value >= 1-1e-6]
        _equal(fit_report.get('bound_hits'), bounds, 'boundary hits')
        core.need(rank == len(ids) and condition is not None and condition <= contract['max_condition'], 'calibration-only data unobservable/ill-conditioned')
        core.need(not bounds or not contract['reject_bound_hits'], 'immutable boundary rule failed')
        core.need(all(row['passed'] for row in calibration+validation), 'remeasured calibration/held-out error exceeds immutable limits')
        core.need(fit_report.get('eligible_for_freeze') is True and fit_report.get('errors') == []
                  and fit_report.get('resources_verified') is True, 'fit report was not eligible')
        core.need(all(fit_report.get(k) is True for k in ('full_native_builds_verified', 'sparse_matches_full', 'protected_geometry_verified')), 'fit report native geometry checks incomplete')
        receipt.update(passed=True, eligible_for_freeze=True, candidate_spec_sha256=core.digest(candidate),
                       contract_sha256=core.digest(contract), fit_report_sha256=core.digest(fit_report),
                       initial_spec_sha256=contract['spec_identity'], full_calibrated_geometry_sha256=full_hash,
                       initial_full_geometry_sha256=fit_report['initial_full_geometry_sha256'],
                       actual_geometric_curves_sha256=core.digest(sparse), camera_sha256=core.digest(cams),
                       protected_geometry_hashes=protection, source_images=images, source_files=sources,
                       calibration=calibration, validation=validation, calibration_sse=sse,
                       data_jacobian=dict(rank=rank, variable_count=len(ids), condition=condition,
                                          max_condition=contract['max_condition'], singular_values=singular.tolist(),
                                          basis='calibration residual finite differences in normalized parameter ranges; no priors'), bound_hits=bounds)
    except (ValueError, KeyError, TypeError, OSError, IndexError, OverflowError, np.linalg.LinAlgError) as exc:
        receipt['errors'].append(str(exc))
    return receipt


def freeze(spec_path, contract_path, report_path, resource_root, out):
    inputs = [Path(p).resolve() for p in (spec_path, contract_path, report_path)]; destination = Path(out).resolve()
    core.need(not destination.exists(), 'freeze output must be a new directory')
    raw = [p.read_bytes() for p in inputs]; values = [json.loads(b) for b in raw]
    receipt = verify(*values, resource_root)
    core.need(receipt['passed'], 'numeric baseline verification failed: ' + '; '.join(receipt['errors']))
    destination.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, blob, source in zip(('spec.json', 'contract.json', 'fit-report.json'), raw, inputs):
        with (destination/name).open('xb') as stream: stream.write(blob)
        files[name] = {'sha256': hashlib.sha256(blob).hexdigest(), 'source_path': str(source)}
    receipt.update(frozen_files=files, resource_root=str(Path(resource_root).resolve()),
                   resources_copied=False, note='Numeric baseline archived only. Relative source resources retain original resource_root; no production adoption or repair/reference gate bypass.')
    with (destination/'verification-receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    return {'passed': True, 'out': str(destination), 'verification_receipt_sha256': hashlib.sha256((destination/'verification-receipt.json').read_bytes()).hexdigest(),
            'visual_fidelity_accepted': False, 'production_accepted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('spec', 'contract', 'fit-report', 'resource-root', 'out'): parser.add_argument('--'+key, required=True)
    args = parser.parse_args()
    try:
        result = freeze(args.spec, args.contract, args.fit_report, args.resource_root, args.out)
        print(json.dumps(result)); return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'passed': False, 'error': str(exc), 'production_accepted': False})); return 1


if __name__ == '__main__': raise SystemExit(main())
