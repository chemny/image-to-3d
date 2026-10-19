#!/usr/bin/env python3
"""Inspect explicit mesh topology and authored local surface samples.

All measurements come from positions and triangle winding, never shading normals.
Distance uses the input coordinate unit; discrete profile curvature uses its inverse.
Local samples cannot certify a whole surface's G2 continuity or self-intersection.
"""
import argparse
import json
import math
from pathlib import Path

from mesh_checks import mesh_report


def _number(value, label, low=0, high=None):
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or value < low or (high is not None and value > high)):
        raise ValueError(label + ' must be a finite number in the declared range')
    return value


def _keys(value, allowed, label):
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    unknown = set(value) - set(allowed)
    if unknown:
        raise ValueError(label + ' has unknown fields: ' + ', '.join(sorted(unknown)))


def _indices(value, count, label, minimum=3, exact=None):
    if (not isinstance(value, list) or len(value) < minimum
            or (exact is not None and len(value) != exact)
            or any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < count for i in value)
            or len(set(value)) != len(value)):
        raise ValueError(label + ' requires distinct valid vertex indices')
    return value


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _length(a):
    return math.sqrt(_dot(a, a))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _angle(a, b):
    denominator = _length(a) * _length(b)
    if denominator <= 0:
        raise ValueError('sample contains a zero length direction or triangle normal')
    return math.degrees(math.acos(max(-1, min(1, _dot(a, b) / denominator))))


def inspect_geometry(geometry, contract):
    """Return measurable checks. A pass covers only supplied contracts and samples."""
    result = {
        'passed': False, 'errors': [],
        'scope': 'index topology and explicit sampled triangle normals/polyline curvature only',
        'basis': {
            'positions': 'actual input vertex coordinates',
            'normals': 'cross products of actual triangle winding; shading normals ignored',
            'distance_unit': 'input coordinate unit', 'angle_unit': 'degrees',
            'curvature_unit': 'inverse input coordinate unit',
            'curvature_definition': 'unsigned magnitude: 2*sin(turn_angle/2)/mean(adjacent segment lengths)',
            'curvature_jump_definition': 'absolute difference of adjacent unsigned discrete curvatures',
        },
        'checks': {'global_G2_certified': False, 'global_self_intersection_checked': False,
                   'reference_likeness_checked': False, 'outward_orientation_checked': False},
        'metrics': {'seam_samples': [], 'profile_checks': []},
    }
    errors = result['errors']
    try:
        _keys(contract, ('version', 'topology', 'seam_samples', 'profile_checks', 'min_triangle_quality', 'bounds'), 'contract')
        if type(contract.get('version')) is not int or contract['version'] != 1:
            raise ValueError('contract version must be 1')
        if contract.get('topology') not in ('open_patch', 'closed_shell'):
            raise ValueError('contract topology must be open_patch or closed_shell')
        if not isinstance(geometry, dict) or geometry.get('type') != 'mesh':
            raise ValueError('geometry must be an explicit mesh')
        topology = mesh_report(dict(geometry, id='surface', contract=contract['topology']))
        result['topology'] = topology
        errors.extend('topology: ' + error for error in topology['errors'])
        if 'invalid finite position array' in topology['errors'] or 'invalid triangle indices' in topology['errors']:
            return result
        positions = geometry['positions']; triangles = geometry['triangles']
        points = [positions[i:i+3] for i in range(0, len(positions), 3)]
        count = len(points)
        if 'bounds' in contract:
            bounds=contract['bounds'];_keys(bounds,('min','max','tolerance'),'bounds')
            low,high=bounds.get('min'),bounds.get('max')
            if not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3:
                raise ValueError('bounds require min/max XYZ vectors')
            if any(type(v)not in(int,float)or not math.isfinite(v)for v in low+high)or any(a>b for a,b in zip(low,high)):
                raise ValueError('bounds must be finite and ordered')
            tolerance=_number(bounds.get('tolerance'),'bounds tolerance')
            actual_low=[min(p[k]for p in points)for k in range(3)];actual_high=[max(p[k]for p in points)for k in range(3)]
            passed=all(a>=l-tolerance and b<=h+tolerance for a,b,l,h in zip(actual_low,actual_high,low,high))
            result['metrics']['bounds']={'actual_min':actual_low,'actual_max':actual_high,'declared':bounds,'passed':passed,'scope':'component-local vertex bounds, not silhouette or attachment certificate'}
            if not passed:errors.append('geometry exceeds authored bounds')
        unused = sorted(set(range(count)) - set(triangles))
        result['metrics']['unused_vertex_indices'] = unused
        if unused:
            errors.append('topology: unused vertices have no surface neighborhood')
        triangle_map = {}; qualities = []
        for offset in range(0, len(triangles), 3):
            tri = triangles[offset:offset+3]
            a, b, c = [points[index] for index in tri]
            cross = _cross(_sub(b, a), _sub(c, a))
            edge_sq = sum(_dot(_sub(x, y), _sub(x, y)) for x, y in ((a,b), (b,c), (c,a)))
            quality = 2 * math.sqrt(3) * _length(cross) / edge_sq if edge_sq else 0
            qualities.append(quality)
            triangle_map.setdefault(tuple(sorted(tri)), []).append((offset//3, cross))
        quality_metrics = {'definition': '4*sqrt(3)*triangle_area/sum(edge_length_squared)',
                           'minimum': min(qualities), 'maximum': max(qualities),
                           'triangle_count': len(qualities), 'bound_declared': 'min_triangle_quality' in contract}
        result['metrics']['triangle_quality'] = quality_metrics
        if 'min_triangle_quality' in contract:
            bound = _number(contract['min_triangle_quality'], 'min_triangle_quality', high=1)
            failed = [i for i, q in enumerate(qualities) if q < bound]
            quality_metrics.update(min_allowed=bound, failed_triangle_indices=failed, passed=not failed)
            if failed:
                errors.append('triangle quality below authored minimum')
        for name in ('seam_samples', 'profile_checks'):
            if name in contract and (not isinstance(contract[name], list) or not contract[name]):
                raise ValueError(name + ' must be a nonempty array when supplied')
        seen = set()
        for sample in contract.get('seam_samples', []):
            _keys(sample, ('id', 'a', 'b', 'max_gap', 'max_angle_deg'), 'seam sample')
            key = sample.get('id')
            if not isinstance(key, str) or not key.strip() or key in seen:
                raise ValueError('seam sample id must be nonempty and unique')
            seen.add(key)
            aa = _indices(sample.get('a'), count, 'seam a', exact=3)
            bb = _indices(sample.get('b'), count, 'seam b', exact=3)
            gap_bound = _number(sample.get('max_gap'), 'max_gap')
            angle_bound = _number(sample.get('max_angle_deg'), 'max_angle_deg', high=180)
            neighborhoods = []
            for indices in (aa, bb):
                matches = triangle_map.get(tuple(sorted(indices)), [])
                if len(matches) != 1:
                    raise ValueError('seam sample ' + key + ' must identify an actual unique mesh triangle')
                neighborhoods.append(matches[0])
            gap = _length(_sub(points[aa[0]], points[bb[0]]))
            angle = _angle(neighborhoods[0][1], neighborhoods[1][1])
            passed = gap <= gap_bound and angle <= angle_bound
            result['metrics']['seam_samples'].append({
                'id': key, 'a': aa, 'b': bb,
                'triangle_indices': [item[0] for item in neighborhoods],
                'gap': gap, 'angle_deg': angle, 'max_gap': gap_bound,
                'max_angle_deg': angle_bound, 'passed': passed})
            if gap > gap_bound:
                errors.append('seam gap exceeds authored bound: ' + key)
            if angle > angle_bound:
                errors.append('seam triangle-normal angle exceeds authored bound: ' + key)
        seen = set()
        mesh_edges = {tuple(sorted(edge)) for offset in range(0, len(triangles), 3)
                      for edge in ((triangles[offset], triangles[offset+1]),
                                   (triangles[offset+1], triangles[offset+2]),
                                   (triangles[offset+2], triangles[offset]))}
        for sample in contract.get('profile_checks', []):
            _keys(sample, ('id', 'vertex_indices', 'max_turn_deg', 'max_curvature_jump', 'max_curvature_vector_jump'), 'profile check')
            key = sample.get('id')
            if not isinstance(key, str) or not key.strip() or key in seen:
                raise ValueError('profile check id must be nonempty and unique')
            seen.add(key)
            indices = _indices(sample.get('vertex_indices'), count, 'profile vertex_indices')
            if any(tuple(sorted(pair)) not in mesh_edges for pair in zip(indices, indices[1:])):
                raise ValueError('profile ' + key + ' must follow actual mesh edges')
            turn_bound = (_number(sample['max_turn_deg'], 'max_turn_deg', high=180)
                          if 'max_turn_deg' in sample else None)
            curvature_bound = (_number(sample['max_curvature_jump'], 'max_curvature_jump')
                               if 'max_curvature_jump' in sample else None)
            vector_bound = (_number(sample['max_curvature_vector_jump'], 'max_curvature_vector_jump')
                            if 'max_curvature_vector_jump' in sample else None)
            if (curvature_bound is not None or vector_bound is not None) and len(indices) < 4:
                raise ValueError('curvature jump requires at least four profile vertices')
            directions = [_sub(points[b], points[a]) for a, b in zip(indices, indices[1:])]
            lengths = [_length(v) for v in directions]
            if any(length <= 0 for length in lengths):
                raise ValueError('profile ' + key + ' contains zero length segments')
            turns = [_angle(a, b) for a, b in zip(directions, directions[1:])]
            curvature = [2 * math.sin(math.radians(turn)/2) / ((lengths[i]+lengths[i+1])/2)
                         for i, turn in enumerate(turns)]
            unit_directions = [[value/length for value in direction]
                               for direction, length in zip(directions, lengths)]
            curvature_vectors = [[value / ((lengths[i]+lengths[i+1])/2)
                                  for value in _sub(b, a)]
                                 for i, (a, b) in enumerate(zip(unit_directions, unit_directions[1:]))]
            vector_jumps = [_length(_sub(a, b)) for a, b in zip(curvature_vectors, curvature_vectors[1:])]
            jumps = [abs(a-b) for a, b in zip(curvature, curvature[1:])]
            peak_turn = max(turns); peak_jump = max(jumps) if jumps else None
            peak_vector_jump = max(vector_jumps) if vector_jumps else None
            passed = ((turn_bound is None or peak_turn <= turn_bound)
                      and (curvature_bound is None or peak_jump <= curvature_bound)
                      and (vector_bound is None or peak_vector_jump <= vector_bound))
            measurement = {'id': key, 'vertex_indices': indices, 'segment_lengths': lengths,
                           'turn_angles_deg': turns, 'discrete_curvatures': curvature,
                           'curvature_jumps': jumps, 'max_measured_turn_deg': peak_turn,
                           'curvature_vectors': curvature_vectors,
                           'curvature_vector_jumps_informational': vector_jumps,
                           'max_measured_curvature_vector_jump': peak_vector_jump,
                           'max_measured_curvature_jump': peak_jump,
                           'bound_declared': turn_bound is not None or curvature_bound is not None or vector_bound is not None,
                           'passed': passed}
            if turn_bound is not None:
                measurement['max_turn_deg'] = turn_bound
            if curvature_bound is not None:
                measurement['max_curvature_jump'] = curvature_bound
            if vector_bound is not None:
                measurement['max_curvature_vector_jump'] = vector_bound
                measurement['curvature_vector_jumps'] = vector_jumps
            result['metrics']['profile_checks'].append(measurement)
            if turn_bound is not None and peak_turn > turn_bound:
                errors.append('profile turn exceeds authored bound: ' + key)
            if curvature_bound is not None and peak_jump > curvature_bound:
                errors.append('profile curvature jump exceeds authored bound: ' + key)
            if vector_bound is not None and peak_vector_jump > vector_bound:
                errors.append('profile curvature vector jump exceeds authored bound: ' + key)
        result['passed'] = not errors
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        errors.append(str(exc))
        result['passed'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', required=True)
    parser.add_argument('--contract', required=True)
    parser.add_argument('--out', required=True, help='new report file; existing paths are refused')
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        parser.error('--out must be a new file')
    geometry = json.loads(Path(args.geometry).read_text())
    contract = json.loads(Path(args.contract).read_text())
    result = inspect_geometry(geometry, contract)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'errors': result['errors'], 'report': str(output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
