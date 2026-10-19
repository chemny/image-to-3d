#!/usr/bin/env python3
"""Frozen repair sessions. Geometry protection and evidence integrity, not visual scoring."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil

import scene_build
import production_checks
from mesh_checks import mesh_report

VERSION = 1
DEFAULT_FROZEN = ('materials', 'variants', 'cameras', 'observations', 'references',
                  'quality_contract', 'checks', 'production_contract', 'coordinate_system',
                  'actions', 'asset_contract', 'vehicle_bindings')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _read(path):
    return json.loads(Path(path).read_text())


def _write(path, value):
    path = Path(path).resolve()
    _need(not path.exists(), 'output must be new: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return path


def _session(path):
    path = Path(path).resolve()
    if path.is_dir():
        path /= 'session.json'
    record = _read(path)
    _need(record.get('version') == VERSION, 'unsupported repair session')
    for name in ('baseline', 'contract'):
        p = path.parent / record[name]['path']
        _need(p.is_file() and sha(p) == record[name]['sha256'], 'stale frozen ' + name)
    for item in record.get('resources', []) + record.get('context', []):
        p = path.parent / item['snapshot']
        _need(p.is_file() and sha(p) == item['sha256'], 'stale resource snapshot')
    source = Path(record['contract']['source'])
    _need(source.is_file() and sha(source) == record['contract']['sha256'], 'repair contract source changed; new session required')
    return path, record, _read(path.parent / record['baseline']['path']), _read(path.parent / record['contract']['path'])


def _resources(spec, spec_path):
    base = Path(spec_path).resolve().parent
    rows = []
    for section in ('references', 'source_files'):
        items = spec.get(section, [])
        _need(isinstance(items, list), section + ' must be a list')
        for item in items:
            _need(isinstance(item, dict) and isinstance(item.get('path'), str), 'invalid resource path')
            p = (base / item['path']).resolve()
            _need(p.is_file() and sha(p) == item.get('sha256'), 'missing or stale resource: ' + str(p))
            rows.append({'path': str(p), 'sha256': item['sha256'], 'section': section})
    return rows


def _validate_contract(contract, spec):
    _need(contract.get('version', 1) == 1, 'unsupported repair contract')
    ids = {c['id'] for c in spec['components']}
    refs = {r['id'] for r in spec.get('references', [])}
    cameras = spec.get('cameras', {})
    if isinstance(cameras, list):
        cameras = {c['id']: c for c in cameras}
    editable = contract.get('editable_components', [])
    added = contract.get('allowed_added_components', [])
    for key, values in (('editable_components', editable), ('allowed_added_components', added)):
        _need(isinstance(values, list) and len(values) == len(set(values)) and all(isinstance(x, str) for x in values), 'unique ' + key + ' required')
    _need(set(editable) <= ids and not set(added) & ids, 'unknown editable or existing added component')
    params = contract.get('allowed_parameters', [])
    _need(isinstance(params, list) and len(params) == len(set(params)) and set(params) <= set(spec.get('parameters', {})), 'unknown allowed parameter')
    protected = contract.get('protected_components', [])
    _need(isinstance(protected, list), 'protected_components must be a list')
    pids = set()
    for rule in protected:
        _need(rule.get('id') in ids and rule['id'] not in pids and rule.get('mode') in ('exact', 'rigid'), 'invalid protected component')
        pids.add(rule['id'])
        _need(rule['id'] not in editable, 'editable and protected overlap')
        for key in ('allow_translation', 'allow_rotation'):
            _need(type(rule.get(key, False)) is bool, 'rigid allowance must be boolean')
    checks = contract.get('checks')
    _need(isinstance(checks, list) and checks, 'repair checks required')
    cids = set()
    visual_views = set()
    roles = set()
    for c in checks:
        _need(isinstance(c.get('id'), str) and c['id'] and c['id'] not in cids, 'unique repair check ID required')
        cids.add(c['id'])
        _need(c.get('method') in ('visual', 'numeric', 'functional'), 'unknown check method')
        _need(isinstance(c.get('component_ids'), list) and c['component_ids'] and set(c['component_ids']) <= ids | set(added), 'check needs actual components')
        if c['method'] == 'visual':
            _need(c.get('view_ids') and set(c['view_ids']) <= set(cameras), 'visual check needs declared cameras')
            visual_views.update(c['view_ids'])
            role = c.get('view_role')
            if role:
                roles.add(role)
    _need(len(visual_views) >= 2, 'original and revealing views required')
    resolved, _ = scene_build.prepared(spec)
    cams = resolved['cameras']
    if isinstance(cams, list):
        cams = {c['id']: c for c in cams}
    positions = {canonical(cams[v].get('position')) for v in visual_views}
    _need(len(positions) >= 2, 'distinct camera positions required; IDs alone do not reveal depth')
    # Roles are mandatory: a pair of arbitrary camera IDs cannot document coverage.
    _need('original' in roles and bool(roles & {'depth', 'connection'}), 'visual coverage needs original and depth/connection view_role')
    targets = contract.get('targets')
    _need(isinstance(targets, list) and targets, 'repair targets required')
    tids = set()
    for t in targets:
        _need(isinstance(t.get('id'), str) and t['id'] and t['id'] not in tids, 'unique target id required')
        tids.add(t['id'])
        _need(t.get('component_ids') and set(t['component_ids']) <= ids | set(added), 'target needs actual components')
        _need(t.get('reference_ids') and set(t['reference_ids']) <= refs, 'target needs registered reference')
        _need(all(isinstance(t.get(k), str) and t[k].strip() for k in ('problem', 'expected')), 'target problem/expected required')
        _need(t.get('check_ids') and set(t['check_ids']) <= cids, 'target check binding required')
        for target_component in t['component_ids']:
            _need(any(c['id'] in t['check_ids'] and c['method'] == 'visual' and target_component in c['component_ids'] for c in checks), 'target component lacks bound visual coverage: ' + target_component)
    rebind = contract.get('allow_rebind_observations', [])
    _need(isinstance(rebind, list) and len(rebind) == len(set(rebind)) and set(rebind) <= {o['id'] for o in spec.get('observations', [])}, 'unknown/duplicate observation rebinding authorization')
    for edge in contract.get('dependency_edges', []):
        _need(isinstance(edge, list) and len(edge) == 2 and set(edge) <= ids | set(added), 'invalid dependency edge')
    _need(type(contract.get('dependency_complete', False)) is bool, 'dependency_complete must be boolean')
    for c in contract.get('constraints', []):
        _need(c.get('id') in cids and c.get('kind') in ('distance', 'normal', 'topology', 'surface_gap', 'opening_clearance'), 'constraint must bind declared check and supported kind')
        _need(next(v for v in checks if v['id'] == c['id'])['method'] == 'numeric', 'geometry constraint must bind numeric check')


def init(spec_path, contract_path, out, diagnostic=False):
    spec_path, contract_path, out = map(lambda p: Path(p).resolve(), (spec_path, contract_path, out))
    _need(not out.exists(), 'session output must be new')
    spec, contract = _read(spec_path), _read(contract_path)
    if not diagnostic:
        from reference_admission import repair_preflight
        repair_preflight(spec_path,contract)
    scene_build.build(spec)
    _validate_contract(contract, spec)
    resources = _resources(spec, spec_path)
    out.mkdir(parents=True)
    shutil.copyfile(spec_path, out / 'baseline.json')
    shutil.copyfile(contract_path, out / 'contract.json')
    for i, item in enumerate(resources):
        destination = out / 'resources' / ('%04d-' % i + Path(item['path']).name)
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(item['path'], destination)
        item['snapshot'] = str(destination.relative_to(out))
    context = []
    operational_analysis = spec_path.parent / 'analysis.json'
    if operational_analysis.is_file():
        destination = out / 'context-analysis.json'
        shutil.copyfile(operational_analysis, destination)
        context.append({'path': str(operational_analysis), 'sha256': sha(operational_analysis), 'snapshot': destination.name})
    record = {'version': 1, 'diagnostic':bool(diagnostic),
              'baseline': {'path': 'baseline.json', 'sha256': sha(spec_path), 'source': str(spec_path)},
              'contract': {'path': 'contract.json', 'sha256': sha(contract_path), 'source': str(contract_path)},
              'resources': resources, 'context': context}
    p = _write(out / 'session.json', record)
    return {'passed': True, 'session_path': str(p), 'session_sha256': sha(p), 'contract_sha256': sha(contract_path),'production_eligible':not diagnostic}


def _world(spec):
    import numpy as np
    resolved, nodes = scene_build.prepared(spec)
    built = scene_build.build(spec)
    result = {}
    for component in built['components']:
        cid = component['id']
        # A matrix evaluates the same ancestor order as scene_build.landmark.
        matrix = np.eye(3)
        offset = np.zeros(3)
        cursor = cid
        while cursor is not None:
            n = nodes[cursor]
            rotation = np.array([scene_build.rotate(list(v), n.get('rotation', [0, 0, 0])) for v in np.eye(3)]).T
            matrix = rotation @ matrix
            offset = rotation @ offset + n.get('position', [0, 0, 0])
            cursor = n.get('parent')
        meshes = []
        for m in component['meshes']:
            points = np.array(m['positions']).reshape(-1, 3)
            normals = np.array(m['normals']).reshape(-1, 3)
            meshes.append({'points': points @ matrix.T + offset, 'normals': normals @ matrix.T, 'indices': m['indices'], 'mesh': m, 'matrix': matrix})
        result[cid] = {'node': nodes[cid], 'meshes': meshes, 'matrix': matrix, 'offset': offset}
    return resolved, nodes, built, result


def _same_geometry(a, b, rigid=None):
    import numpy as np
    if len(a['meshes']) != len(b['meshes']):
        return False
    for x, y in zip(a['meshes'], b['meshes']):
        if x['indices'] != y['indices'] or x['points'].shape != y['points'].shape or x['mesh'].get('uvs') != y['mesh'].get('uvs'):
            return False
    if not a['meshes']:
        rotation_same = np.allclose(a['matrix'], b['matrix'], atol=1e-9, rtol=0)
        translation_same = np.allclose(a['offset'], b['offset'], atol=1e-9, rtol=0)
        return (rotation_same or rigid and rigid.get('allow_rotation', False)) and (translation_same or rigid and rigid.get('allow_translation', False))
    p = np.vstack([m['points'] for m in a['meshes']])
    q = np.vstack([m['points'] for m in b['meshes']])
    np_before = np.vstack([m['normals'] for m in a['meshes']])
    np_after = np.vstack([m['normals'] for m in b['meshes']])
    if not rigid:
        return np.allclose(p, q, atol=1e-9, rtol=0) and np.allclose(np_before, np_after, atol=1e-9, rtol=0)
    pc, qc = p.mean(axis=0), q.mean(axis=0)
    pp, qq = p - pc, q - qc
    if rigid.get('allow_rotation', False):
        u, _, vt = np.linalg.svd(pp.T @ qq)
        correction = np.eye(3)
        correction[2, 2] = np.linalg.det(u @ vt)
        rotation = u @ correction @ vt
    else:
        rotation = np.eye(3)
    if not np.allclose(pp @ rotation, qq, atol=1e-9, rtol=0):
        return False
    if not np.allclose(np_before @ rotation, np_after, atol=1e-9, rtol=0):
        return False
    # Translation of the rigid frame, rather than centroid drift during rotation.
    translation = qc - pc @ rotation
    return rigid.get('allow_translation', False) or np.allclose(translation, 0, atol=1e-9, rtol=0)


def _constraints(spec, contract, nodes, built, world):
    import numpy as np
    rows = []
    components = {c['id']: c for c in built['components']}
    for c in contract.get('constraints', []):
        kind = c['kind']
        if kind in ('surface_gap', 'opening_clearance'):
            from surface_attachment import evaluate
            measured = evaluate(spec, [c])
            _need(not measured.get('errors'), 'surface check invalid: ' + '; '.join(measured.get('errors', [])))
            _need(len(measured.get('checks', [])) == 1, 'surface check result required')
            rows.append(measured['checks'][0])
            continue
        row = {'id': c['id'], 'kind': kind}
        if kind == 'distance':
            low, high = c.get('min'), c.get('max')
            _need(type(low) in (int, float) and type(high) in (int, float) and 0 <= low <= high and math.isfinite(high), 'invalid distance tolerance')
            points = [production_checks._point(spec, nodes, components, c[k]) for k in ('a', 'b')]
            value = math.dist(*points)
            row.update(value=value, passed=low <= value <= high, min=low, max=high)
        elif kind == 'normal':
            cid = c['component_id']
            _need(cid in world and world[cid]['meshes'], 'normal needs mesh component')
            mi, ti = c.get('mesh_index', 0), c['triangle_index']
            _need(type(mi) is int and 0 <= mi < len(world[cid]['meshes']), 'invalid normal mesh index')
            m = world[cid]['meshes'][mi]
            _need(type(ti) is int and 0 <= ti < len(m['indices']) // 3, 'invalid normal triangle')
            a, b, d = m['points'][m['indices'][3*ti:3*ti+3]]
            n = np.cross(b-a, d-a)
            direction = np.array(scene_build.vector(c['direction']), dtype=float)
            _need(np.linalg.norm(direction) > 0 and np.linalg.norm(n) > 0, 'normal direction must be nonzero')
            value = float(np.dot(n, direction)/(np.linalg.norm(n)*np.linalg.norm(direction)))
            threshold = c.get('min_dot')
            _need(type(threshold) in (int, float) and -1 <= threshold <= 1, 'invalid normal threshold')
            row.update(value=value, passed=value >= threshold, min_dot=threshold)
        else:
            cid = c['component_id']
            _need(cid in world and world[cid]['meshes'], 'topology needs mesh component')
            reports = []
            for m in world[cid]['meshes']:
                t = m['mesh']['topology_mesh']
                reports.append(mesh_report({'id': cid, 'positions': t['positions'], 'triangles': t['triangles'], 'contract': c['contract']}))
            row.update(passed=all(r['passed'] for r in reports), reports=reports)
        rows.append(row)
    return rows


def check(session_path, candidate_path, out=None):
    errors = []
    report = {'passed': False, 'errors': errors, 'changed_components': [], 'affected_components': [], 'required_checks': []}
    try:
        path, record, baseline, contract = _session(session_path)
        candidate_path = Path(candidate_path).resolve()
        candidate = _read(candidate_path)
        report['production_eligible']=not record.get('diagnostic',False)
        report.update(candidate_sha256=sha(candidate_path), session_sha256=sha(path), contract_sha256=record['contract']['sha256'])
        _validate_contract(contract, baseline)
        _resources(candidate, candidate_path)
        if baseline.get('quality_contract',{}).get('reference_standard')==2:
            name=baseline['reference_plan'];old_hash=next(r['sha256']for r in baseline['source_files']if r['path']==name)
            if sha(candidate_path.parent/candidate['reference_plan'])!=old_hash:
                from reference_admission import validate_rebinding
                meta=candidate_path.parent/'project.json';entry=_read(meta).get('reference_binding_review')if meta.is_file()else None
                validate_rebinding(candidate_path,path,entry,old_hash)
        old_sources = {r['path'] for r in baseline.get('source_files', [])}
        new_sources = [r['path'] for r in candidate.get('source_files', [])]
        _need(len(new_sources) == len(set(new_sources)), 'duplicate candidate source paths')
        _need(old_sources <= set(new_sources), 'candidate dropped source provenance')
        bs, bn, bb, bw = _world(baseline)
        cs, cn, cb, cw = _world(candidate)
        if baseline.get('quality_contract',{}).get('reference_standard')==2:
            plan=_read(candidate_path.parent/candidate['reference_plan'])
            if plan['task']['intent']=='technical_fix':
                def surface(node):
                    faces=[]
                    for mesh in node['meshes']:
                        vertices=[tuple(round(float(v),10)for v in row)for row in mesh['points']]
                        indices=mesh['indices']
                        faces.extend(tuple(sorted(vertices[i]for i in indices[j:j+3]))for j in range(0,len(indices),3))
                    return sorted(faces)
                for cid in contract['editable_components']:
                    _need(cid in cw and surface(bw[cid])==surface(cw[cid]),'technical_fix changed actual surface shape; admit a reference_match/design_change task instead: '+cid)
        frozen = set(DEFAULT_FROZEN) | set(contract.get('protected_sections', []))
        # Freeze unknown authoritative sections too. Identity and provenance may evolve.
        mutable = {'components', 'parameters', 'source_files', 'id', 'metadata'}
        frozen |= (set(baseline) | set(candidate)) - mutable
        rebound = set(contract.get('allow_rebind_observations', []))
        binding_keys = {'component_id', 'local_point', 'vertex_index', 'patch_id', 'uv', 'binding'}
        def fixed_observations(value):
            rows = copy.deepcopy(value)
            for row in rows or []:
                if row.get('id') in rebound:
                    if isinstance(row.get('binding'), dict):
                        extra = set(row['binding']) - (binding_keys - {'binding'})
                        _need(not extra, 'observation binding contains unknown fields')
                    for k in binding_keys:
                        row.pop(k, None)
            return rows
        for key in sorted(frozen):
            raw_before, raw_after = baseline.get(key), candidate.get(key)
            res_before, res_after = bs.get(key), cs.get(key)
            if key == 'observations':
                raw_before, raw_after = fixed_observations(raw_before), fixed_observations(raw_after)
                res_before, res_after = fixed_observations(res_before), fixed_observations(res_after)
            if raw_before != raw_after or res_before != res_after:
                errors.append('frozen section changed: ' + key)
        for key in set(baseline.get('parameters', {})) | set(candidate.get('parameters', {})):
            old, new = baseline.get('parameters', {}).get(key), candidate.get('parameters', {}).get(key)
            if old != new:
                if key not in contract.get('allowed_parameters', []) or old is None or new is None or {k:v for k,v in old.items() if k != 'value'} != {k:v for k,v in new.items() if k != 'value'}:
                    errors.append('unapproved parameter or bounds change: ' + key)
        editable = set(contract.get('editable_components', []))
        additions = set(contract.get('allowed_added_components', []))
        protection = {r['id']: r for r in contract.get('protected_components', [])}
        changed = []
        for cid in sorted(set(bw) | set(cw)):
            if cid not in bw:
                changed.append(cid)
                if cid not in additions:
                    errors.append('unapproved added component: ' + cid)
                continue
            if cid not in cw:
                changed.append(cid)
                errors.append('removed component: ' + cid)
                continue
            same = _same_geometry(bw[cid], cw[cid])
            declaration_changed = bn[cid] != cn[cid]
            if not same or declaration_changed:
                changed.append(cid)
                rule = protection.get(cid)
                if rule and rule['mode'] == 'rigid':
                    safe_node_keys = {'geometry', 'position', 'rotation', 'parent'}
                    old_other = {k:v for k,v in bn[cid].items() if k not in safe_node_keys}
                    new_other = {k:v for k,v in cn[cid].items() if k not in safe_node_keys}
                    if old_other != new_other or not _same_geometry(bw[cid], cw[cid], rule):
                        errors.append('rigid protection violated: ' + cid)
                elif cid not in editable:
                    errors.append('protected or unplanned component changed: ' + cid)
        rebuilt = {cid: c for cid, c in ((c['id'], c) for c in cb['components'])}
        for obs in cs.get('observations', []):
            binding = obs.get('binding', obs)
            cid = obs.get('component_id')
            if 'vertex_index' in binding or 'patch_id' in binding:
                actual_binding = {'component_id': cid, **{k:binding[k] for k in ('vertex_index','patch_id','uv') if k in binding}}
                production_checks._point(cs, cn, rebuilt, actual_binding)
                if cid in bw and cid in cw and obs['id'] not in rebound:
                    old_indices = [m['indices'] for m in bw[cid]['meshes']]
                    new_indices = [m['indices'] for m in cw[cid]['meshes']]
                    if old_indices != new_indices:
                        errors.append('topology changed; observation needs explicit rebinding authorization: ' + obs['id'])
            else:
                scene_build.landmark(cs, obs)
        affected = set(changed)
        if not contract.get('dependency_complete', False):
            affected = set(cw)
            report['dependency_mode'] = 'full-recheck'
        else:
            report['dependency_mode'] = 'declared-transitive'
            while True:
                expanded = affected | {b for a,b in contract.get('dependency_edges', []) if a in affected}
                if expanded == affected:
                    break
                affected = expanded
        required = [c['id'] for c in contract['checks'] if not contract.get('dependency_complete', False) or set(c['component_ids']) & affected or c.get('always', False)]
        # Visual targets remain required even if edits did not affect a declared dependency.
        required = sorted(set(required) | {x for t in contract['targets'] for x in t['check_ids']})
        rows = _constraints(cs, contract, cn, cb, cw)
        for row in rows:
            if not row['passed']:
                errors.append('constraint failed: ' + row['id'])
        report.update(changed_components=changed, affected_components=sorted(affected), required_checks=required, constraints=rows, passed=not errors)
    except (ValueError, KeyError, TypeError, IndexError, OSError, ImportError) as exc:
        errors.append(str(exc))
    if out is not None:
        _write(out, report)
    return report


def validate_review(session_path, candidate_path, review_path):
    return _validate_review_evidence(session_path, candidate_path, review_path, check(session_path, candidate_path))


def _validate_review_evidence(session_path, candidate_path, review_path, report):
    # Project gate supplies its content-keyed numeric result; all review, capture,
    # resource and artifact identities below are still checked on every call.
    errors = list(report['errors'])
    try:
        _need(report['passed'], 'candidate repair checks failed')
        path, record, baseline, contract = _session(session_path)
        review_path = Path(review_path).resolve()
        review = _read(review_path)
        for k in ('session_sha256', 'contract_sha256', 'candidate_sha256'):
            _need(review.get(k) == report[k], 'stale review ' + k)
        _need(review.get('version') == 1 and review.get('decision') == 'adopt', 'adoption review required')
        _need(isinstance(review.get('reviewer'), str) and review['reviewer'].strip(), 'reviewer required')
        results = review.get('results')
        _need(isinstance(results, list), 'review results required')
        by = {}
        for r in results:
            _need(r.get('id') not in by, 'duplicate review result')
            by[r['id']] = r
        checks = {c['id']: c for c in contract['checks']}
        for cid in report['required_checks']:
            r = by.get(cid, {})
            c = checks[cid]
            _need(r.get('verdict') == 'pass' and r.get('method') == c['method'], 'missing/failed review check: ' + cid)
            _need(isinstance(r.get('notes'), str) and r['notes'].strip(), 'specific review notes required: ' + cid)
            artifacts = r.get('artifacts')
            _need(isinstance(artifacts, list) and artifacts, 'review artifacts required: ' + cid)
            artifact_paths = set()
            for a in artifacts:
                _need(isinstance(a.get('path'), str) and a['path'], 'artifact path required')
                p = (review_path.parent / a['path']).resolve()
                _need(p.is_file() and sha(p) == a.get('sha256'), 'missing/stale review artifact')
                artifact_paths.add(str(p))
            if c['method'] == 'visual':
                from repair_capture import validate_receipt
                receipt_name = r.get('capture_report')
                _need(isinstance(receipt_name, str) and receipt_name, 'visual capture receipt required')
                receipt_path = (review_path.parent / receipt_name).resolve()
                receipt = validate_receipt(receipt_path, candidate_path, views=c['view_ids'])
                _need(receipt.get('passed'), 'invalid visual capture receipt: ' + '; '.join(receipt.get('errors', [])))
                raw = _read(receipt_path)
                captured_paths = {str((receipt_path.parent / a['path']).resolve()) for v in raw.get('views', []) if v['id'] in c['view_ids'] for a in v.get('artifacts', [])}
                _need(artifact_paths <= captured_paths, 'visual artifact is not verified capture evidence')
                for view in c['view_ids']:
                    view_paths = {str((receipt_path.parent / a['path']).resolve()) for v in raw.get('views', []) if v['id'] == view for a in v.get('artifacts', [])}
                    _need(bool(view_paths & artifact_paths), 'missing required view artifact: ' + view)
        if baseline.get('quality_contract',{}).get('reference_standard')==2 and not record.get('diagnostic',False):
            from shape_acceptance import validate_review as shape_review
            candidate=_read(candidate_path)
            shape_review(candidate_path,candidate,_read(Path(candidate_path).parent/candidate['reference_plan']),review,review_path)
        errors = []
    except (ValueError, KeyError, TypeError, IndexError, OSError, ImportError) as exc:
        errors.append(str(exc))
    return {'passed': not errors, 'errors': errors, 'candidate_sha256': report.get('candidate_sha256'), 'required_checks': report.get('required_checks', []),'production_eligible':report.get('production_eligible',False)}


def parameters(session_path, values_path, out):
    path, record, baseline, contract = _session(session_path)
    values = _read(values_path)
    _need(isinstance(values, dict) and values, 'numeric parameter values object required')
    candidate = copy.deepcopy(baseline)
    for key, value in values.items():
        _need(key in contract.get('allowed_parameters', []), 'parameter not allowed: ' + key)
        p = candidate['parameters'][key]
        _need(type(value) in (int, float) and math.isfinite(value) and p['min'] <= value <= p['max'], 'parameter outside frozen bounds: ' + key)
        p['value'] = value
    # Keep frozen relative resource identity and avoid silently breaking references.
    destination = Path(out).resolve()
    _need(destination.parent == Path(record['baseline']['source']).parent or not any(candidate.get(k) for k in ('references','source_files')), 'parameter output must share baseline source directory for frozen reference paths')
    scene_build.build(candidate)
    result = _write(out, candidate)
    return {'passed': True, 'candidate_path': str(result), 'candidate_sha256': sha(result)}


def status(session_path, candidate_path=None):
    path, record, baseline, contract = _session(session_path)
    return {'passed': True, 'session_path': str(path), 'session_sha256': sha(path), 'contract_sha256': record['contract']['sha256'], 'baseline_sha256': record['baseline']['sha256'], 'targets': contract['targets'], 'candidate': check(path, candidate_path) if candidate_path else None}


def restore(session_path, out):
    path, record, baseline, contract = _session(session_path)
    out = Path(out).resolve()
    _need(not out.exists(), 'restore output must be new')
    # Immutable bytes restore; this never restores source files over live resources.
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as f:
        f.write((path.parent / record['baseline']['path']).read_bytes())
    return {'passed': True, 'spec_path': str(out), 'sha256': sha(out), 'resource_base': str(Path(record['baseline']['source']).parent), 'note': 'Spec-only restore. Relative resources retain original base; live resources are never overwritten.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init'); p.add_argument('--spec', required=True); p.add_argument('--contract', required=True); p.add_argument('--out', required=True);p.add_argument('--diagnostic',action='store_true',help='Isolated software/legacy diagnostics only; cannot attach to production project')
    for cmd in ('check', 'review', 'status', 'parameters', 'restore'):
        p = sub.add_parser(cmd); p.add_argument('--session', required=True)
        if cmd in ('check','review'): p.add_argument('--candidate', required=True)
        if cmd == 'status': p.add_argument('--candidate')
        if cmd in ('check','parameters','restore'): p.add_argument('--out', required=cmd != 'check')
        if cmd == 'review': p.add_argument('--review', required=True)
        if cmd == 'parameters': p.add_argument('--values', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init': result = init(args.spec, args.contract, args.out,args.diagnostic)
        elif args.command == 'check': result = check(args.session, args.candidate, args.out)
        elif args.command == 'review': result = validate_review(args.session, args.candidate, args.review)
        elif args.command == 'parameters': result = parameters(args.session, args.values, args.out)
        elif args.command == 'restore': result = restore(args.session, args.out)
        else: result = status(args.session, args.candidate)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result = {'passed': False, 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] and not (args.command=='review' and result.get('production_eligible') is False) else 1


if __name__ == '__main__':
    raise SystemExit(main())
