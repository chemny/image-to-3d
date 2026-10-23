#!/usr/bin/env python3
"""Evidence-bound decision gate, NOT a renderer or a mesh optimizer."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def verify(base, item):
    p = base / item['path']
    if sha(p) != item['sha256']:
        raise ValueError(f'changed evidence: {p}')
    return p


def assess(plan, record, base, plan_hash):
    if record['plan_sha256'] != plan_hash:
        raise ValueError('plan identity mismatch')
    verify(base, record['model'])
    missing, failed, values = [], [], {}
    if record.get('alignment') != 'validated':
        missing.append('camera_alignment')
    for spec in plan['checks']:
        key = spec['id']
        entry = record.get('checks', {}).get(key)
        if not spec['calibrated']:
            missing.append(key + ':threshold_calibration')
        if not entry or 'value' not in entry or not entry.get('evidence'):
            missing.append(key)
            continue
        value = entry['value']
        if not finite(value):
            raise ValueError(f'nonfinite or nonnumeric measurement: {key}')
        for evidence in entry['evidence']:
            verify(base, evidence)
        if spec['kind'] in ('visual', 'protection', 'functional') and value not in (0, 1):
            raise ValueError(f'nonbinary verdict: {key}')
        values[key] = value
        if (spec['op'] == 'max' and value > spec['limit']) or (spec['op'] == 'min' and value < spec['limit']):
            failed.append(key)
    # Max violation, not an average that can hide a failed critical item.
    loss = max([0.0] + [max(0.0, (values[s['id']] - s['limit']) * (1 if s['op'] == 'max' else -1)) / max(abs(s['limit']), s['uncertainty'], 1e-9) for s in plan['checks'] if s['id'] in values])
    return {'missing': missing, 'failed': failed, 'values': values, 'loss': None if missing else loss}


def decide(plan_path, record):
    base, digest = plan_path.parent, sha(plan_path)
    plan = json.loads(plan_path.read_text())
    refs, checks, budget = plan['references'], plan['checks'], plan['budget']
    if not refs or not checks:
        raise ValueError('empty reference/check coverage')
    for ref in refs:
        verify(base, ref)
    kinds = {s['kind'] for s in checks}
    if not {'silhouette', 'landmark', 'visual', 'protection', 'functional'} <= kinds:
        raise ValueError('missing mandatory check categories')
    if len({s['id'] for s in checks}) != len(checks):
        raise ValueError('duplicate check id')
    for s in checks:
        if s['op'] not in ('min', 'max') or not s['reason'] or type(s['calibrated']) is not bool:
            raise ValueError('invalid threshold specification')
        if not all(finite(s[k]) for k in ('limit', 'uncertainty', 'max_regression')) or s['uncertainty'] < 0 or s['max_regression'] < 0:
            raise ValueError('invalid numeric threshold')
        if s['kind'] in ('visual', 'protection', 'functional') and (s['op'] != 'min' or s['limit'] != 1 or s['uncertainty'] != 0):
            raise ValueError('binary critical gates must require 1')
    n = record['round']
    if type(n) is not int or n < 1:
        raise ValueError('invalid round')
    if any(type(budget[k]) is not int or budget[k] < 1 for k in ('max_rounds', 'stagnation_rounds')) or not finite(budget['min_improvement']) or budget['min_improvement'] <= 0:
        raise ValueError('invalid budget')
    history = record.get('history', [])
    if len(history) != n - 1 or n > budget['max_rounds']:
        raise ValueError('noncontinuous history or budget exceeded')
    old_records, past = [], []
    for i, ref in enumerate(history, 1):
        r = json.loads(verify(base, ref).read_text())
        if r['round'] != i or r.get('history', []) != history[:i-1]:
            raise ValueError('history chain mismatch')
        old_records.append(r)
        past.append(assess(plan, r, base, digest))
    current = assess(plan, record, base, digest)
    result = {'schema_version': 1, 'plan_sha256': digest, 'round': n, 'model': record['model'], **current, 'claim': 'target_conformance', 'execution': 'decision_only'}
    def finish(action, reasons):
        return dict(result, action=action, reasons=reasons, deliverable=action == 'passed')
    best = record.get('previous_best')
    if best:
        if best not in history:
            raise ValueError('best must reference an immutable prior round')
        b = past[history.index(best)]
        if b['missing']:
            raise ValueError('best round has incomplete measurements')
        regressions = [s['id'] for s in checks if s['id'] in current['values'] and (current['values'][s['id']] - b['values'][s['id']]) * (1 if s['op'] == 'max' else -1) > s['max_regression']]
    else:
        regressions = []
        if any(not p['missing'] for p in past):
            raise ValueError('measured history requires explicit best checkpoint')
    if regressions:
        result['restore'] = best
        return finish('blocked' if n >= budget['max_rounds'] else 'rollback', ['regression:' + x for x in regressions])
    if not current['missing'] and not current['failed']:
        return finish('passed', ['all frozen checks and evidence passed'])
    if n >= budget['max_rounds']:
        return finish('blocked', ['budget_exhausted'] + current['missing'] + current['failed'])
    if current['missing']:
        return finish('calibrate', current['missing'])
    span = budget['stagnation_rounds']
    tail = past[-span:]
    if len(tail) == span and all(not p['missing'] for p in tail):
        losses = [p['loss'] for p in tail] + [current['loss']]
        if all(a-b < budget['min_improvement'] for a, b in zip(losses, losses[1:])):
            return finish('change_method', ['no measurable improvement'] + current['failed'])
    return finish('repair', current['failed'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'record', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        result = decide(args.plan, json.loads(args.record.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'action': 'blocked', 'deliverable': False, 'reasons': [str(exc)], 'execution': 'decision_only'}
    with args.out.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result['action'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
