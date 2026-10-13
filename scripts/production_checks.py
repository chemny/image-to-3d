#!/usr/bin/env python3
"""Sampled static geometry measurements, using the rendered scene authority.

Distances are in Spec coordinate_system.unit after component/ancestor transforms.
Mirror checks compare bound positions only, not normals, winding or topology.
"""
import math

import scene_build


SCOPE = ('Declared sampled static geometry only, in world coordinates and Spec units; '
         'no full thickness, collision, topology, winding, animation or visual certificate')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value, name):
    _require(type(value) in (int, float) and math.isfinite(value),
             name + ' must be finite numeric')
    return value


def _keys(value, expected, name):
    _require(isinstance(value, dict) and set(value) == set(expected),
             name + ' requires exactly: ' + ', '.join(sorted(expected)))


def _point(spec, nodes, built, binding):
    _require(isinstance(binding, dict), 'geometry binding must be an object')
    if 'vertex_index' in binding:
        _keys(binding, ('component_id', 'vertex_index'), 'vertex binding')
    else:
        _keys(binding, ('component_id', 'patch_id', 'uv'), 'patch binding')
    key = binding['component_id']
    _require(isinstance(key, str) and key in nodes, 'unknown binding component')
    meshes = built[key]['meshes']
    _require(bool(meshes), 'binding must reference actual geometry')
    if 'patch_id' in binding:
        _require(nodes[key]['geometry']['type'] == 'bezier_network',
                 'patch binding requires Bezier network')
        _require(isinstance(binding['patch_id'], str), 'patch_id must be a string')
        point = scene_build.landmark(spec, binding)
    else:
        _require(len(meshes) == 1, 'vertex binding requires a single mesh; use patch binding')
        index = binding['vertex_index']
        positions = meshes[0]['positions']
        _require(type(index) is int and 0 <= index < len(positions) // 3,
                 'invalid geometry vertex index')
        _require(index in meshes[0]['indices'], 'vertex must belong to an actual triangle')
        point = positions[index * 3:index * 3 + 3]
        cursor = key
        while cursor is not None:
            node = nodes[cursor]
            point = [a + b for a, b in zip(
                scene_build.rotate(point, node.get('rotation', [0, 0, 0])),
                node.get('position', [0, 0, 0]))]
            cursor = node.get('parent')
    _require(all(math.isfinite(v) for v in point), 'nonfinite world geometry point')
    return point


def evaluate(spec):
    """Return measured pass/fail; reject malformed or unsupported declarations.

    Zero declarations give checked=0 and an empty checks list. The vacuous gate
    result is never a universal geometry pass or production certificate.
    """
    contract = spec.get('production_contract', {})
    _require(isinstance(contract, dict), 'production_contract must be an object')
    checks = contract.get('geometry_checks', [])
    _require(isinstance(checks, list), 'geometry_checks must be a list')
    if not checks:
        return {'passed': True, 'checked': 0, 'checks': [], 'scope': SCOPE}
    declarations = spec.get('checks', [])
    _require(isinstance(declarations, list), 'Spec.checks must be a list')
    ids = set()
    for check in checks:
        _require(isinstance(check, dict), 'geometry check must be an object')
        kind = check.get('kind')
        if kind == 'distance':
            _keys(check, ('id', 'kind', 'a', 'b', 'min', 'max'), 'distance check')
            low, high = _number(check['min'], 'min'), _number(check['max'], 'max')
            _require(0 <= low <= high, 'distance limits require 0 <= min <= max')
        elif kind == 'mirror':
            _keys(check, ('id', 'kind', 'pairs', 'axis', 'plane', 'tolerance'), 'mirror check')
            _require(check['axis'] in ('x', 'y', 'z'), 'mirror axis must be x/y/z')
            _number(check['plane'], 'plane')
            _require(_number(check['tolerance'], 'tolerance') >= 0, 'negative mirror tolerance')
            _require(isinstance(check['pairs'], list) and bool(check['pairs']),
                     'mirror pairs must be nonempty')
            for pair in check['pairs']:
                _keys(pair, ('a', 'b'), 'mirror pair')
        else:
            raise ValueError('unsupported geometry check kind: ' + str(kind))
        identifier = check['id']
        _require(isinstance(identifier, str) and bool(identifier) and identifier not in ids,
                 'unique geometry check ID required')
        ids.add(identifier)
        matches = [d for d in declarations if isinstance(d, dict) and d.get('id') == identifier]
        _require(len(matches) == 1 and matches[0].get('required') is True
                 and matches[0].get('kind') == 'numeric'
                 and matches[0].get('stage') in ('body', 'assembly'),
                 'geometry check ID must bind one required numeric body/assembly Spec.checks entry')
    # Build first: invalid triangles, unsupported geometry and topology contracts
    # cannot be bypassed by naming plausible-looking landmark coordinates.
    payload = scene_build.build(spec)
    resolved, nodes = scene_build.prepared(spec)
    built = {c['id']: c for c in payload['components']}
    rows = []
    for check in checks:
        row = {'id': check['id'], 'kind': check['kind'], 'unit': resolved['coordinate_system'].get('unit')}
        if check['kind'] == 'distance':
            points = [_point(resolved, nodes, built, check[k]) for k in ('a', 'b')]
            distance = math.dist(*points)
            _require(math.isfinite(distance), 'nonfinite measured distance')
            row.update(distance=distance, min=check['min'], max=check['max'],
                       passed=check['min'] <= distance <= check['max'])
        else:
            axis = ('x', 'y', 'z').index(check['axis'])
            errors = []
            for pair in check['pairs']:
                a, b = [_point(resolved, nodes, built, pair[k]) for k in ('a', 'b')]
                a[axis] = 2 * check['plane'] - a[axis]
                error = math.dist(a, b)
                _require(math.isfinite(error), 'nonfinite mirror error')
                errors.append(error)
            row.update(axis=check['axis'], plane=check['plane'], tolerance=check['tolerance'],
                       pair_errors=errors, max_error=max(errors),
                       passed=all(error <= check['tolerance'] for error in errors))
        rows.append(row)
    return {'passed': all(row['passed'] for row in rows), 'checked': len(rows),
            'checks': rows, 'scope': SCOPE}
