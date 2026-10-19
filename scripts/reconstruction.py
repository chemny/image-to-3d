#!/usr/bin/env python3
"""Model-bound calibration/parameter fitting; numerical agreement is not visual acceptance.

Python standard library only. Uses scene_build as the geometry/transform authority.
Validation observations never enter the objective or candidate selection.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys

import scene_build


def require(ok, message):
    if not ok:
        raise ValueError(message)


def dot(a, b): return sum(x*y for x, y in zip(a, b))
def sub(a, b): return [x-y for x, y in zip(a, b)]
def cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def unit(a):
    length = math.sqrt(dot(a, a))
    require(length > 1e-12, 'degenerate camera position/target/up')
    return [x/length for x in a]


def project(point, camera):
    """Project a world point to top-left pixel coordinates, rejecting invalid depth."""
    width, height = camera['width'], camera['height']
    require(width > 0 and height > 0, 'invalid image dimensions')
    forward = unit(sub(camera['target'], camera['position']))
    right = unit(cross(forward, camera.get('up', [0, 1, 0])))
    up = cross(right, forward)
    delta = sub(point, camera['position'])
    depth = dot(delta, forward)
    require(camera.get('near', .01) < depth < camera.get('far', 1000), 'landmark behind camera or outside depth range')
    x, y = dot(delta, right), dot(delta, up)
    if camera['type'] == 'perspective':
        fov = camera['fov_y_deg']
        require(0 < fov < 179, 'invalid perspective FOV')
        scale = height / (2*math.tan(math.radians(fov)/2)*depth)
    elif camera['type'] == 'orthographic':
        require(camera['ortho_height'] > 0, 'invalid orthographic height')
        scale = height / camera['ortho_height']
    else:
        raise ValueError('unsupported camera type')
    result = [width/2 + x*scale, height/2 - y*scale]
    require(all(math.isfinite(v) for v in result), 'nonfinite projection')
    return result


def checked_observations(spec):
    seen = set()
    for o in spec['observations']:
        require(o.get('id') not in seen and isinstance(o.get('id'), str), 'duplicate/missing observation ID')
        seen.add(o['id'])
        require(o.get('role') in ('calibration', 'validation'), 'observation role must be explicit')
        require(not (o.get('protected') and o['role'] == 'validation'), 'validation cannot protect or select candidates')
        require(o.get('camera_id') in spec['cameras'], 'unknown camera')
        require(isinstance(o.get('target'), list) and len(o['target']) == 2 and all(type(x) in (int,float) and math.isfinite(x) for x in o['target']), 'explicit finite pixel target required')
        require(type(o.get('sigma_px')) in (int,float) and math.isfinite(o['sigma_px']) and o['sigma_px'] > 0, 'positive sigma_px required')
        require(isinstance(o.get('parameter_ids'), list) and all(p in spec['parameters'] for p in o['parameter_ids']), 'unknown observation parameter')
        yield o


def predictions(spec, role=None):
    require(role in (None, 'calibration', 'validation'), 'invalid prediction role')
    scene_build.build(spec)  # Reject invalid geometry; never substitute independent point labels.
    result = {}
    for o in checked_observations(spec):
        if role is not None and o['role'] != role:
            continue
        camera = scene_build.resolve(spec['cameras'][o['camera_id']], spec['parameters'])
        p = project(scene_build.landmark(spec, o), camera)
        error = math.dist(p, o['target'])
        result[o['id']] = {'predicted': p, 'target': o['target'], 'error_px': error,
                           'normalized_error': error/o['sigma_px']}
    return result


def objective(rows):
    require(bool(rows), 'calibration observations required')
    return sum(r['normalized_error']**2 for r in rows.values())/len(rows)


def bounds(spec, ids):
    require(isinstance(ids, list) and ids and len(ids) == len(set(ids)), 'unique parameter IDs required')
    for name in ids:
        require(name in spec['parameters'], 'unknown fitting parameter: '+name)
        p = spec['parameters'][name]
        vals = [p.get(k) for k in ('min','value','max')]
        require(all(type(v) in (int,float) and math.isfinite(v) for v in vals) and vals[0] <= vals[1] <= vals[2], 'invalid parameter bounds: '+name)


def matrix_rank(rows, tolerance=1e-7):
    a = [list(row) for row in rows]
    if not a: return 0
    rank = 0
    for col in range(len(a[0])):
        pivot = max(range(rank, len(a)), key=lambda i: abs(a[i][col]), default=None)
        if pivot is None or abs(a[pivot][col]) < tolerance: continue
        a[rank], a[pivot] = a[pivot], a[rank]
        scale = a[rank][col]; a[rank] = [v/scale for v in a[rank]]
        for i in range(rank+1, len(a)):
            scale = a[i][col]; a[i] = [v-scale*q for v,q in zip(a[i], a[rank])]
        rank += 1
        if rank == len(a): break
    return rank


def analyze(spec, parameter_ids=None):
    ids = parameter_ids or list(spec['parameters'])
    bounds(spec, ids)
    base = predictions(spec, 'calibration')
    require(base, 'calibration observations required')
    declared = {p for o in checked_observations(spec) if o['role'] == 'calibration' for p in o['parameter_ids']}
    sensitivity, columns, failures = {}, [], []
    for name in ids:
        p = spec['parameters'][name]; span = p['max']-p['min']
        delta = max(span*1e-4, 1e-7)
        candidate = copy.deepcopy(spec)
        value = min(p['max'], p['value']+delta)
        if value == p['value']: value = max(p['min'], p['value']-delta)
        if value == p['value']:
            column = [0.]*(len(base)*2)
        else:
            candidate['parameters'][name]['value'] = value
            try:
                rows = predictions(candidate, 'calibration')
                column = [(rows[k]['predicted'][j]-base[k]['predicted'][j])/(value-p['value'])*span for k in base for j in (0,1)]
            except (ValueError, KeyError, TypeError) as exc:
                failures.append({'parameter': name, 'reason': str(exc)}); column = [0.]*(len(base)*2)
        sensitivity[name] = math.sqrt(sum(v*v for v in column))
        columns.append(column)
    rank = matrix_rank(list(zip(*columns)))
    return {'calibration': base, 'validation': predictions(spec, 'validation'), 'unobserved_parameters': sorted(set(ids)-declared),
            'sensitivity_px_per_range': sensitivity, 'insensitive_parameters': [p for p in ids if sensitivity[p] < 1e-5],
            'jacobian_rank': rank, 'rank_deficient': rank < len(ids), 'failures': failures,
            'scope': 'local finite-difference diagnostic only; rank is not global identifiability or visual acceptance'}


def fit(spec, parameter_ids, iterations=60, candidate_guard=None, predictor=None):
    bounds(spec, parameter_ids)
    require(type(iterations) is int and iterations > 0, 'iterations must be positive integer')
    observed = {p for o in checked_observations(spec) if o['role']=='calibration' for p in o['parameter_ids']}
    require(set(parameter_ids) <= observed, 'fitting parameter has no calibration observation binding')
    current = copy.deepcopy(spec)
    predict = predictor or predictions
    initial_rows = predict(current, 'calibration'); initial = objective(initial_rows)
    require(all(type(o.get('protection_tolerance_px', .01)) in (int,float) and math.isfinite(o.get('protection_tolerance_px', .01)) and o.get('protection_tolerance_px', .01) >= 0 for o in checked_observations(spec) if o.get('protected')), 'invalid protection tolerance')
    protected = {o['id']: initial_rows[o['id']]['error_px'] + o.get('protection_tolerance_px', .01) for o in checked_observations(spec) if o.get('protected')}
    require(all(math.isfinite(v) and v >= 0 for v in protected.values()), 'invalid protection tolerance')
    score = initial; steps = {p: (spec['parameters'][p]['max']-spec['parameters'][p]['min'])/8 for p in parameter_ids}
    journal = []; accepted = 0
    for iteration in range(iterations):
        improved = False
        for name in parameter_ids:
            for direction in (-1,1):
                candidate = copy.deepcopy(current); p = candidate['parameters'][name]
                value = max(p['min'], min(p['max'], p['value']+direction*steps[name]))
                if value == p['value']: continue
                p['value'] = value
                try:
                    if candidate_guard is not None:candidate_guard(candidate)
                    rows = predict(candidate, 'calibration')
                    if any(rows[k]['error_px'] > limit for k,limit in protected.items()):
                        journal.append({'iteration':iteration,'parameter':name,'value':value,'accepted':False,'reason':'protected landmark regression'}); continue
                    candidate_score = objective(rows)
                    take = candidate_score < score-1e-12
                    journal.append({'iteration':iteration,'parameter':name,'value':value,'objective':candidate_score,'accepted':take})
                    if take: current,score = candidate,candidate_score; improved=True; accepted+=1
                except (ValueError, KeyError, TypeError) as exc:
                    journal.append({'iteration':iteration,'parameter':name,'value':value,'accepted':False,'reason':str(exc)})
        if not improved:
            steps = {p:s/2 for p,s in steps.items()}
        if max(steps.values()) < 1e-8: break
    # Held-out points are computed only after search, never used for choosing candidates.
    return {'spec':current, 'initial_objective':initial, 'final_objective':score,
            'calibration':predict(current,'calibration'), 'validation':predict(current,'validation'),
            'journal':journal,'accepted_steps':accepted,
            'limits':['bounded coordinate search; no global-optimum guarantee','pixel targets must be supplied by observation','no visual quality pass or automatic calibration certification']}


def main():
    p=argparse.ArgumentParser(description=__doc__); subp=p.add_subparsers(dest='cmd',required=True)
    for cmd in ('analyze','inspect','fit'):
        q=subp.add_parser(cmd); q.add_argument('spec'); q.add_argument('--parameters',nargs='+'); q.add_argument('--out',required=True)
        if cmd=='fit': q.add_argument('--iterations',type=int,default=60)
    args=p.parse_args()
    try:
        spec=json.loads(Path(args.spec).read_text())
        report=fit(spec,args.parameters or list(spec['parameters']),args.iterations) if args.cmd=='fit' else analyze(spec,args.parameters)
        Path(args.out).write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'report':args.out,'visual_pass':False})); return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'error':str(exc)}),file=sys.stderr); return 2


if __name__=='__main__': sys.exit(main())
