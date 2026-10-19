"""Check recorded version continuity and browser handoff; never mutate models/registry.

This verifies artifact identity and evidence consistency, not image quality or the
truth/completeness of an author's observations. See presentation-delivery.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from adoption_check import evaluate as adoption_evaluate


def evaluate(report, base, phase='resume'):
    base = Path(base)
    errors = []

    def require(ok, message):
        if not ok:
            errors.append(message)

    def artifact(item, label):
        if not isinstance(item, dict):
            errors.append(label + ': missing artifact'); return None
        try:
            p = (base / item['path']).resolve()
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            require(digest == item['sha256'], label + ': stale hash')
            return p
        except (KeyError, TypeError, OSError):
            errors.append(label + ': missing artifact'); return None

    def read_evidence(item, label):
        p = artifact(item, label)
        try:
            value = json.loads(p.read_text()) if p else None
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, OSError):
            errors.append(label + ': invalid JSON object'); return {}

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def target(value):
        require(isinstance(value, dict) and all(nonempty(value.get(k)) for k in
                ('case_id', 'source', 'page_url', 'model_url')), 'invalid target')
        value = value if isinstance(value, dict) else {}
        for key in ('page_url', 'model_url'):
            try:
                require(urlsplit(value.get(key, '')).scheme in ('http', 'https'), key + ': absolute HTTP URL required')
            except ValueError:
                errors.append(key + ': invalid URL')
        return value

    def observed(item, expected, asset, registry, label):
        capture = read_evidence(item, label)
        require(capture.get('target') == expected, label + ': wrong case/source/URL')
        # Digest captured from the resource response, using the same bytes as asset.
        require(capture.get('asset_sha256') == (asset or {}).get('sha256'), label + ': loaded asset mismatch')
        require(capture.get('registry_sha256') == (registry or {}).get('sha256'), label + ': registry mismatch')
        require(capture.get('ready') is True, label + ': model not ready')
        require(capture.get('errors') == [], label + ': browser errors/missing error log')
        artifact(capture.get('screenshot'), label + ': screenshot')
        return capture

    if not isinstance(report, dict):
        return {'passed': False, 'errors': ['report must be an object']}
    require(report.get('version') == 1, 'unsupported record version')
    require(phase in ('resume', 'delivery'), 'unsupported phase')
    production = report.get('production', {})
    production = production if isinstance(production, dict) else {}
    production_target = target(production.get('target'))
    production_asset = production.get('asset')
    artifact(production_asset, 'production asset')
    artifact(production.get('registry'), 'production registry snapshot')
    observed(production.get('observation'), production_target, production_asset,
             production.get('registry'), 'production browser observation')
    baseline = report.get('baseline')
    artifact(baseline, 'construction baseline')
    require(nonempty(report.get('baseline_reason')), 'missing baseline choice reason')

    # Reuse the project inventory; this tool cannot discover unrecorded samples.
    inventory = read_evidence(report.get('inventory'), 'accepted work inventory')
    work = inventory.get('accepted_work')
    require(isinstance(work, list), 'inventory.accepted_work must be a list (empty allowed)')
    work = work if isinstance(work, list) else []
    ids = [w.get('id') if isinstance(w, dict) else None for w in work]
    require(all(nonempty(x) for x in ids) and len(set(x for x in ids if isinstance(x, str))) == len(ids), 'invalid/duplicate work IDs')
    dispositions = report.get('inheritance')
    require(isinstance(dispositions, list), 'inheritance must be a list')
    dispositions = dispositions if isinstance(dispositions, list) else []
    dispositions = [d for d in dispositions if isinstance(d, dict)]
    dids = [d.get('id') for d in dispositions]
    require(all(nonempty(x) for x in dids) and len(set(x for x in dids if isinstance(x, str))) == len(dids)
            and set(x for x in dids if isinstance(x, str)) == set(x for x in ids if isinstance(x, str)), 'accepted work coverage mismatch')
    sources = set()
    if isinstance(production_asset, dict):
        sources.add(production_asset.get('sha256'))
    for w in work:
        if not isinstance(w, dict):
            errors.append('invalid accepted work'); continue
        artifact(w.get('asset'), str(w.get('id')) + ': sample')
        artifact(w.get('acceptance'), str(w.get('id')) + ': acceptance record')
        if isinstance(w.get('asset'), dict):
            sources.add(w['asset'].get('sha256'))
    require(isinstance(baseline, dict) and baseline.get('sha256') in sources, 'baseline is not production or an inventoried accepted sample')
    for d in dispositions:
        require(d.get('status') in ('inherited', 'deferred', 'superseded'), str(d.get('id')) + ': invalid inheritance status')
        require(nonempty(d.get('reason')), str(d.get('id')) + ': missing inheritance reason')
        if phase == 'delivery' and d.get('status') == 'inherited':
            evidence = read_evidence(d.get('evidence'), str(d.get('id')) + ': inheritance evidence')
            candidate = report.get('candidate', {})
            require(isinstance(candidate, dict) and evidence.get('candidate_sha256') == candidate.get('sha256'), 'inheritance evidence bound to wrong candidate')
            require(evidence.get('work_id') == d.get('id') and evidence.get('passed') is True, 'inheritance not verified')
    if phase == 'delivery':
        candidate = report.get('candidate')
        artifact(candidate, 'candidate')
        review = read_evidence(report.get('adoption_review'), 'adoption review')
        review_path = (base / report['adoption_review']['path']).resolve() if isinstance(report.get('adoption_review'), dict) and 'path' in report['adoption_review'] else base / '_missing'
        result = adoption_evaluate(review, review_path.parent)
        require(result['decision'] == 'adopt', 'existing adoption review does not allow adoption')
        require(isinstance(candidate, dict) and review.get('candidate', {}).get('sha256') == candidate.get('sha256'), 'adoption candidate mismatch')
        require(isinstance(baseline, dict) and review.get('baseline', {}).get('sha256') == baseline.get('sha256'), 'adoption baseline mismatch')
        installed = report.get('installed', {})
        installed = installed if isinstance(installed, dict) else {}
        installed_target = target(installed.get('target'))
        require(all(installed_target.get(k) == production_target.get(k) for k in ('case_id', 'source')), 'installed wrong case/source')
        artifact(installed.get('registry'), 'installed registry')
        capture = observed(installed.get('observation'), installed_target, candidate,
                           installed.get('registry'), 'installed browser observation')
        required = report.get('required_operations')
        require(isinstance(required, list) and all(nonempty(k) for k in required), 'required_operations must be a list')
        required = required if isinstance(required, list) else []
        checks = capture.get('checks', {})
        checks = checks if isinstance(checks, dict) else {}
        for key in set(['switch_return', 'reset'] + [k for k in required if isinstance(k, str)]):
            require(checks.get(key) is True, 'operation not passed: ' + key)
        require(nonempty(installed.get('rollback')), 'missing rollback location')
    return {'passed': not errors, 'phase': phase, 'errors': errors,
            'deferred': [d.get('id') for d in dispositions if d.get('status') == 'deferred'],
            'scope': 'Recorded identity/continuity check only; no browser execution, visual certification or registration mutation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--phase', choices=('resume', 'delivery'), default='resume')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(json.loads(args.record.read_text()), args.record.resolve().parent, args.phase)
    except (ValueError, OSError, TypeError, KeyError) as error:
        result = {'passed': False, 'errors': [str(error)]}
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        # Evidence is append-only; choose a fresh result path.
        with args.out.open('x') as handle:
            handle.write(output + '\n')
    print(output)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
