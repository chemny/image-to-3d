#!/usr/bin/env python3
"""Freeze optimization acceptance criteria and check evidence consistency.
Not a geometry optimizer or visual fidelity judge. Standard library only.
"""
import argparse, hashlib, json, math
from pathlib import Path

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_new(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

def point(value):
    if not isinstance(value, list) or len(value) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError('Expected finite [x, y] pixel point')
    return value

def validate_plan(p):
    if p.get('schema_version') != 1 or p.get('claim') not in ('asset_quality', 'reference_fidelity'):
        raise ValueError('Expected schema 1 and explicit claim')
    if p.get('coverage') not in ('selected_regions', 'whole_exterior', 'asset_quality') or not p.get('scope'):
        raise ValueError('Explicit coverage and scope required')
    if not p.get('baseline_model') or not p.get('required_checks'):
        raise ValueError('Baseline and protection checks required')
    views = p.get('views', {})
    for v in views.values():
        if v.get('alignment') not in ('validated', 'approximate', 'unregistered'):
            raise ValueError('Explicit view alignment required')
        if v['alignment'] == 'validated' and not v.get('alignment_evidence'):
            raise ValueError('Validated alignment needs evidence')
    critical = p.get('critical_features', {})
    if not critical or any(not vs or any(v not in views for v in vs) for vs in critical.values()):
        raise ValueError('Critical features require covered views')
    if p['coverage'] == 'whole_exterior':
        required = {'body_outline', 'roofline', 'windowline', 'wheels', 'lamps', 'feature_placement'}
        if not required <= set(critical) or not {'front', 'side', 'rear', 'quarter'} <= set(views):
            raise ValueError('Whole exterior lacks structural groups/views; choose supported regional scope')
    cal = p.get('calibration_points', [])
    val = p.get('validation_points', [])
    ids = [a['id'] for a in cal + val]
    if len(ids) != len(set(ids)):
        raise ValueError('Calibration/validation IDs must be unique')
    for a in cal + val:
        point(a['reference'])
        if a['view'] not in views or a['feature'] not in critical:
            raise ValueError('Unknown observation feature/view')
    for a in val:
        t, u = a.get('threshold_px'), a.get('uncertainty_px')
        if type(t) not in (int, float) or not math.isfinite(t) or t <= 0 or type(u) not in (int, float) or not math.isfinite(u) or u < 0 or u > t:
            raise ValueError('Task threshold must be finite, positive and no tighter than stated uncertainty')
        if not a.get('threshold_reason'):
            raise ValueError('Threshold needs task-specific rationale')
        regression = a.get('max_regression_px')
        if regression is not None and (type(regression) not in (int, float) or not math.isfinite(regression) or regression < 0):
            raise ValueError('Regression bound must be finite and nonnegative')
        for b in cal:
            if a['view'] == b['view'] and math.dist(a['reference'], b['reference']) < 1e-6:
                raise ValueError('Renamed calibration point is not independent validation')
    independent = set(p.get('independent_features', []))
    if not independent <= set(critical):
        raise ValueError('Unknown independent feature')
    if p['claim'] == 'reference_fidelity':
        if not p.get('references') or not independent:
            raise ValueError('Reference fidelity requires reference and independent features')
        if p['coverage'] == 'whole_exterior' and (len(independent) < 2 or len(views) < 2):
            raise ValueError('Whole exterior needs independent feature groups and multiple views')
        if not independent <= {a['feature'] for a in val}:
            raise ValueError('Independent feature lacks reserved validation points')

def seal(plan_path, out):
    plan_path, out = Path(plan_path), Path(out)
    if out.parent.resolve() != plan_path.parent.resolve():
        raise ValueError('Keep lock alongside plan for portable relative paths')
    p = json.loads(plan_path.read_text()); validate_plan(p)
    paths = [p['baseline_model']] + p.get('references', [])
    if p.get('original_model'): paths.append(p['original_model'])
    paths += p.get('baseline_comparison_evidence', [])
    paths += [v['alignment_evidence'] for v in p['views'].values() if v.get('alignment_evidence')]
    hashes = {s: digest(plan_path.parent / s) for s in paths}
    changed = bool(p.get('original_model') and hashes[p['original_model']] != hashes[p['baseline_model']])
    if changed and not p.get('baseline_comparison_evidence'):
        raise ValueError('Changed baseline needs comparison evidence; distinguish its contribution')
    lock = {'schema_version': 1, 'plan': p, 'plan_sha256': hashlib.sha256(canonical(p)).hexdigest(), 'source_hashes': hashes, 'baseline_changed': changed}
    write_new(out, lock)
    return lock

def evaluate(lock_path, record_path):
    lock_path = Path(lock_path); root = lock_path.parent
    lock = json.loads(lock_path.read_text()); record = json.loads(Path(record_path).read_text())
    p = lock['plan']; validate_plan(p)
    if hashlib.sha256(canonical(p)).hexdigest() != lock['plan_sha256'] or record.get('plan_sha256') != lock['plan_sha256']:
        raise ValueError('Plan/thresholds changed or review belongs to another plan')
    for path, h in lock['source_hashes'].items():
        if digest(root / path) != h: raise ValueError('Frozen source/evidence changed: ' + path)
    blockers, measurements = [], []
    def evidence(rows):
        if not rows: return False
        for row in rows:
            if digest(root / row['path']) != row['sha256']:
                raise ValueError('Review artifact changed: ' + row['path'])
        return True
    if not evidence([record['output_model']]): raise ValueError('Output model missing')
    for name in p['required_checks']:
        check = record.get('checks', {}).get(name, {})
        if check.get('verdict') != 'passed' or not evidence(check.get('evidence', [])):
            blockers.append('Required protection/asset check not passed: ' + name)
    visual = record.get('visual_reviews', [])
    for feature, views in p['critical_features'].items():
        for view in views:
            hits = [r for r in visual if r.get('view') == view and feature in r.get('features', [])]
            if not hits or any(r.get('verdict') != 'passed' or not evidence(r.get('evidence', [])) for r in hits):
                blockers.append('Critical feature unpassed: ' + feature + '/' + view)
    obs = record.get('observations', [])
    if len({r['id'] for r in obs}) != len(obs): raise ValueError('Duplicate observed IDs')
    reserved = {a['id']: a for a in p.get('validation_points', [])}
    calibrated = {a['id'] for a in p.get('calibration_points', [])}
    if any(r['id'] in calibrated for r in obs):
        raise ValueError('Calibration observations cannot be submitted as validation')
    if any(r['id'] not in reserved for r in obs): raise ValueError('Unreserved validation observation')
    reused = set(record.get('used_for_adjustment', []))
    if not reused <= set(reserved): raise ValueError('Unknown reused validation ID')
    independent_passed = set()
    for id, target in reserved.items():
        hits = [r for r in obs if r['id'] == id]
        if not hits:
            blockers.append('Reserved observation missing: ' + id); continue
        r = hits[0]; before, after = point(r['before']), point(r['after'])
        error = math.dist(after, target['reference']); prior = math.dist(before, target['reference'])
        aligned = p['views'][target['view']]['alignment'] == 'validated'
        valid = id not in reused and aligned and error <= target['threshold_px']
        measurements.append({'id': id, 'before_error_px': prior, 'after_error_px': error, 'threshold_px': target['threshold_px'], 'independent': id not in reused, 'within_threshold': error <= target['threshold_px']})
        if not valid: blockers.append('Validation unpassed/contaminated/unaligned: ' + id)
        if valid: independent_passed.add(target['feature'])
        # A task may declare a permissible regression separately from its absolute bound.
        if target.get('max_regression_px') is not None and error-prior > target['max_regression_px']:
            blockers.append('Validation regression exceeds task bound: ' + id)
    if p['claim'] == 'reference_fidelity' and not set(p['independent_features']) <= independent_passed:
        blockers.append('Independent critical feature coverage incomplete')
    return {'verdict': 'needs_revision' if blockers else 'consistent', 'scope': p['scope'], 'claim': p['claim'], 'baseline_changed': lock['baseline_changed'], 'blockers': blockers, 'measurements': measurements, 'limitations': ['Checks evidence identity and declared acceptance logic; does not judge image truth or mesh resemblance', 'Consistent bookkeeping requires actual visual review; not automatic high-fidelity certification']}

def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='action', required=True)
    a = sub.add_parser('seal'); a.add_argument('--plan', required=True, type=Path); a.add_argument('--out', required=True, type=Path)
    a = sub.add_parser('check'); a.add_argument('--lock', required=True, type=Path); a.add_argument('--record', required=True, type=Path); a.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = seal(args.plan, args.out) if args.action == 'seal' else evaluate(args.lock, args.record)
        if args.action == 'check': write_new(args.out, result)
        print(json.dumps({'verdict': result.get('verdict', 'sealed'), 'blockers': result.get('blockers', [])}, ensure_ascii=False))
        return 2 if result.get('verdict') == 'needs_revision' else 0
    except (ValueError, KeyError, TypeError, OSError) as e:
        parser.exit(1, str(e) + '\n')

if __name__ == '__main__': raise SystemExit(main())
