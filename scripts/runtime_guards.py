"""Read-only guards for captured runtime data and declared release dependencies.

No browser, renderer, model modification, registry mutation or publication.
Capture authenticity and dependency completeness remain the caller's responsibility.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


def vector(value, length=None):
    if not isinstance(value, list) or not value or (length is not None and len(value) != length):
        raise ValueError('invalid numeric vector')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError('nonfinite/nonnumeric vector')
    return value


def tolerance(value):
    vector([value])
    if value < 0:
        raise ValueError('negative tolerance')
    return value


def close(a, b, limit):
    vector(a); vector(b, len(a))
    return max(abs(x-y) for x, y in zip(a, b)) <= limit


def names(values):
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values) or len(set(values)) != len(values):
        raise ValueError('empty/duplicate/invalid IDs')
    return values


def temporal(contract, sequences):
    """Compare world-space invariants within each fixed-state sequence, not camera pixels."""
    required = names(contract['sequences'])
    keys = names(contract['invariants'])
    limit = tolerance(contract['tolerance'])
    if not isinstance(sequences, list):
        raise ValueError('sequences must be a list')
    ids = names([s['id'] for s in sequences])
    if set(ids) != set(required):
        raise ValueError('sequence coverage mismatch')
    errors = []
    for seq in sequences:
        frames = seq['frames']
        if not isinstance(frames, list) or len(frames) < 2:
            raise ValueError('sequence needs at least two frames')
        previous = -math.inf
        for frame in frames:
            stamp = vector([frame['time']])[0]
            if stamp <= previous:
                raise ValueError('timestamps must increase')
            previous = stamp
            for key, minimum in contract.get('minimums', {}).items():
                vector([minimum])
                if key not in keys:
                    raise ValueError('minimum requires declared invariant')
                if any(v < minimum for v in vector(frame['invariants'][key])):
                    errors.append(seq['id'] + ': insufficient separation ' + key)
            for key in keys:
                if not close(frames[0]['invariants'][key], frame['invariants'][key], limit):
                    errors.append(seq['id'] + ': unstable ' + key)
        # Camera motion is deliberately not an invariant. Visual flicker still needs review.
    return {'passed': not errors, 'errors': errors}


def _snapshot(snapshot):
    vertices = snapshot['vertices']
    if not isinstance(vertices, list) or not vertices:
        raise ValueError('missing actual vertices')
    for v in vertices:
        vector(v, 3)
    actual = [min(v[i] for v in vertices) for i in range(3)] + [max(v[i] for v in vertices) for i in range(3)]
    vector(snapshot['root_matrix'], 16)
    if snapshot['root_matrix'][3:16:4] != [0, 0, 0, 1]:
        raise ValueError('root must be an affine column-major matrix')
    bounds = vector(snapshot['normalization_bounds'], 6)
    if any(bounds[i] > bounds[i+3] for i in range(3)):
        raise ValueError('invalid normalization bounds')
    return actual


def scale(contract, baseline, candidate):
    """Bounds from supplied actual vertices; protected anchors transformed by actual root."""
    limit = tolerance(contract['tolerance'])
    delta = tolerance(contract['max_bounds_delta'])
    errors = []
    a, b = _snapshot(baseline), _snapshot(candidate)
    for label, snap, measured in [('baseline', baseline, a), ('candidate', candidate, b)]:
        if not close(vector(snap['accessor_bounds'], 6), measured, limit):
            errors.append(label + ': accessor bounds do not match vertices')
    if not close(a, b, delta):
        errors.append('actual bounds exceed permitted local edit')
    for key in ['root_matrix', 'normalization_bounds', 'camera']:
        if not close(baseline[key], candidate[key], limit):
            errors.append('protected runtime state changed: ' + key)
    def world(snap, name):
        index = snap['anchors'][name]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(snap['vertices']):
            raise ValueError('invalid anchor index')
        v = snap['vertices'][index];m = snap['root_matrix']
        return [sum(m[i+4*j]*v[j] for j in range(3))+m[i+12] for i in range(3)]
    for name in names(contract['anchors']):
        if not close(world(baseline, name), world(candidate, name), limit):
            errors.append('protected world anchor changed: ' + name)
    return {'passed': not errors, 'errors': errors, 'measured_bounds': b}


def bundle(root, expected, required, packaged):
    """Declared closure only. Bind shared runtime bytes even when the model is unchanged."""
    root = Path(root).resolve()
    names(required); names(packaged)
    if not isinstance(expected, dict) or not expected:
        raise ValueError('missing frozen resource hashes')
    errors = []
    for name in set(required) | set(expected) | set(packaged):
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('resource path escape')
        p = root / rel
        if not p.resolve().is_relative_to(root) or any(root.joinpath(*rel.parts[:i]).is_symlink() for i in range(1, len(rel.parts)+1)):
            raise ValueError('resource symlink/escape')
        if name not in packaged:
            errors.append('required resource excluded from package: ' + name)
        if name not in expected:
            errors.append('required resource lacks frozen hash: ' + name)
        if not p.is_file():
            errors.append('missing resource: ' + name)
        elif hashlib.sha256(p.read_bytes()).hexdigest() != expected.get(name):
            errors.append('resource identity changed: ' + name)
    return {'passed': not errors, 'errors': errors}


def rollback_preview(current, before, adopted, scope):
    """Return a merged registry projection, refusing concurrent edits. Never writes it."""
    names(scope)
    if not all(isinstance(x, dict) for x in [current, before, adopted]):
        raise ValueError('registries must be objects keyed by stable case/source ID')
    result = copy.deepcopy(current)
    for key in scope:
        if key not in before and key not in adopted:
            raise ValueError('unknown rollback target')
        if (key in current) != (key in adopted) or current.get(key) != adopted.get(key):
            raise ValueError('rollback conflict: ' + key)
        if key in before:
            result[key] = copy.deepcopy(before[key])
        else:
            result.pop(key, None)
    return {'passed': True, 'registry': result}


def evaluate(data, root):
    try:
        if type(data['version']) is not int or data['version'] != 1:
            raise ValueError('unsupported version')
        kind = data['kind']
        if kind == 'temporal':
            return temporal(data['contract'], data['sequences'])
        if kind == 'scale':
            return scale(data['contract'], data['baseline'], data['candidate'])
        if kind == 'bundle':
            return bundle(root, data['expected'], data['required'], data['packaged'])
        if kind == 'rollback':
            return rollback_preview(data['current'], data['before'], data['adopted'], data['scope'])
        raise ValueError('unsupported check kind')
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError) as e:
        return {'passed': False, 'errors': ['invalid evidence: ' + str(e)]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(json.loads(args.record.read_text()), args.record.resolve().parent)
    except (ValueError, OSError) as e:
        result = {'passed': False, 'errors': [str(e)]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    raise SystemExit(0 if result['passed'] else 1)
