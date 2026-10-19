"""Validate recorded visual adoption evidence; does not judge images or mutate assets."""
import argparse
import hashlib
import json
from pathlib import Path


def evaluate(report, base):
    errors = []
    def artifact(item, label):
        try:
            path = (base / item['path']).resolve()
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != item['sha256']:
                errors.append(label + ': stale hash')
        except (KeyError, TypeError, OSError):
            errors.append(label + ': missing artifact')
    artifact(report.get('baseline'), 'baseline')
    artifact(report.get('candidate'), 'candidate')
    required = report.get('required_regions', [])
    regions = report.get('regions', [])
    if not isinstance(required, list) or not required or any(not isinstance(x, str) or not x for x in required):
        errors.append('required_regions must be nonempty IDs')
        required = []
    if len(set(required)) != len(required):
        errors.append('duplicate required region')
    if not isinstance(regions, list):
        errors.append('regions must be a list')
        regions = []
    ids, verdicts = [], []
    for r in regions:
        if not isinstance(r, dict):
            errors.append('invalid region'); continue
        rid = r.get('id')
        if not isinstance(rid, str):
            errors.append('invalid region ID'); continue
        ids.append(rid)
        verdict = r.get('verdict')
        verdicts.append(verdict)
        if verdict not in ('improved', 'unchanged', 'regressed', 'uncertain'):
            errors.append(rid + ': invalid verdict')
        if not isinstance(r.get('reason'), str) or not r['reason'].strip():
            errors.append(rid + ': missing observation')
        artifact(r.get('before'), rid + ': before')
        artifact(r.get('after'), rid + ': after')
    if len(set(ids)) != len(ids) or set(ids) != set(required):
        errors.append('region coverage mismatch or duplicates')
    if report.get('same_conditions') is not True:
        errors.append('comparable capture conditions not confirmed')
    decision = ('invalid' if errors else 'retain-baseline' if 'regressed' in verdicts
                else 'pending' if 'uncertain' in verdicts else 'adopt')
    return {'decision': decision, 'errors': errors,
            'regressed': [r['id'] for r in regions if isinstance(r, dict) and r.get('verdict') == 'regressed'],
            'uncertain': [r['id'] for r in regions if isinstance(r, dict) and r.get('verdict') == 'uncertain'],
            'scope': 'Recorded adoption review only; not automatic image assessment or formal certification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.review.read_text()), args.review.resolve().parent)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(output + '\n')
    print(output)
    return 0 if result['decision'] == 'adopt' else 1


if __name__ == '__main__':
    raise SystemExit(main())
