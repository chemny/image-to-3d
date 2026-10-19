#!/usr/bin/env python3
"""Offline, fail-closed workflow gates. Evidence records a review, not proof of truth.

Evidence JSON: stage, verdict='pass', reviewer, rationale, spec_sha256,
resource_hashes ({spec-relative path: sha256} for every reference/source),
review_scope equal quality_contract.scope, acceptance='quality_passed',
artifacts ([{path: evidence-relative path, sha256}]), check_results
([{id, verdict:'pass', method, reviewer, scope, artifact_paths}]). Include
stage-level result id='stage:<stage>'. Required check results must cite artifacts. Visual checks require method='visual'.
No metric threshold automatically produces a visual verdict.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

STAGES = ('intake', 'references', 'spec', 'body', 'assembly', 'presentation', 'review', 'delivery')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_spec(path):
    path = Path(path).resolve()
    spec = read(path)
    import repair_project
    repair_project.policy(path)
    import shape_foundation
    shape_foundation.policy(path)
    require(spec.get('schema_version') == 1, 'unsupported schema_version')
    require(nonempty(spec.get('id')), 'missing id')
    require(spec.get('domain') in ('generic', 'vehicle'), 'invalid domain')
    axes = spec.get('coordinate_system', {})
    require(all(nonempty(axes.get(k)) for k in ('unit', 'up', 'forward')), 'coordinate_system incomplete')
    require(axes['up'].lstrip('+-') != axes['forward'].lstrip('+-'), 'up and forward axes must differ')
    resources = {}
    refs = {}
    for field in ('references', 'source_files'):
        require(isinstance(spec.get(field), list), f'{field} must be a list')
        for item in spec[field]:
            name = item.get('path')
            require(nonempty(name), f'{field}: missing path')
            require(not Path(name).is_absolute(), 'resource paths must be relative to spec')
            target = path.parent / name
            require(target.is_file(), f'missing resource: {name}')
            actual = digest(target)
            require(item.get('sha256') == actual, f'resource hash mismatch: {name}')
            require(name not in resources, f'duplicate resource: {name}')
            resources[name] = actual
            if field == 'references':
                rid = item.get('id')
                require(nonempty(rid) and rid not in refs, 'missing/duplicate reference id')
                require(item.get('origin') in ('original', 'generated', 'derived', 'synthetic'), 'reference origin must be explicit')
                require(isinstance(item.get('approved'), bool), 'reference approved must be boolean')
                if item['origin'] == 'synthetic':
                    require(spec.get('quality_contract', {}).get('scope') == 'synthetic-software-test', 'synthetic reference requires test-only scope')
                    require(item['approved'] is False, 'synthetic fixture cannot claim reference approval')
                refs[rid] = item
    for rid, ref in refs.items():
        conflicts = ref.get('conflicts_with', [])
        require(isinstance(conflicts, list) and all(x in refs and x != rid for x in conflicts), 'invalid reference conflict IDs')
        require(not (ref['approved'] and any(refs[x]['approved'] for x in conflicts)), 'conflicting references both approved')
    params = spec.get('parameters')
    require(isinstance(params, dict), 'parameters must be object')
    for key, p in params.items():
        require(nonempty(key), 'empty parameter id')
        values = [p.get(k) for k in ('min', 'value', 'max')]
        import math
        require(all(type(v) in (int, float) and math.isfinite(v) for v in values), f'invalid numeric parameter: {key}')
        require(values[0] <= values[1] <= values[2], f'parameter out of bounds: {key}')
    components = spec.get('components')
    require(isinstance(components, list), 'components must be list')
    ids = [c.get('id') for c in components]
    require(all(nonempty(x) for x in ids) and len(set(ids)) == len(ids), 'missing/duplicate component id')
    parents = {c['id']: c.get('parent') for c in components}
    for c in components:
        require(nonempty(c.get('role')), 'component role incomplete')
        if c.get('kind')=='assembly':
            require('geometry' not in c and 'material' not in c,'assembly cannot carry geometry/material')
        else:
            require(isinstance(c.get('geometry'),dict) and nonempty(c['geometry'].get('type')),'component role/geometry incomplete')
            require('material' in c,'component material missing')
        mapping = c.get('geometry',{}).get('parameters', {})
        require(isinstance(mapping, dict) and all(isinstance(x, str) and x in params for x in mapping.values()), 'unknown geometry parameter')
        parent = c.get('parent')
        require(parent is None or parent in parents, f'unknown parent: {parent}')
        seen = {c['id']}
        while parent is not None:
            require(parent not in seen, 'component parent cycle')
            seen.add(parent)
            parent = parents[parent]
    observations = spec.get('observations')
    require(isinstance(observations, list), 'observations must be list')
    obs_ids = set()
    for obs in observations:
        require(nonempty(obs.get('id')) and obs['id'] not in obs_ids, 'missing/duplicate observation id')
        obs_ids.add(obs['id'])
        require(obs.get('reference_id') in refs, 'unknown observation reference')
        require(nonempty(obs.get('feature')), 'observation feature missing')
        require(isinstance(obs.get('parameter_ids'), list) and all(x in params for x in obs['parameter_ids']), 'unknown observation parameter')
    checks = spec.get('checks')
    require(isinstance(checks, list), 'checks must be list')
    check_ids = set()
    for check in checks:
        require(nonempty(check.get('id')) and check['id'] not in check_ids, 'missing/duplicate check id')
        check_ids.add(check['id'])
        require(nonempty(check.get('kind')) and isinstance(check.get('required'), bool), 'check kind/required missing')
        require(check.get('stage', 'review') in STAGES, 'invalid check stage')
    quality = spec.get('quality_contract', {})
    require('foundation_standard' not in quality or (type(quality['foundation_standard'])==int and quality['foundation_standard']==1),'unsupported foundation standard')
    require('reference_standard' not in quality or (type(quality['reference_standard']) == int and quality['reference_standard'] in (1,2)), 'unsupported reference standard')
    if quality.get('reference_standard') in (1,2):
        from reference_set import validate as validate_reference_set
        validate_reference_set(path, 'intake')
    require('production_standard' not in quality or (type(quality['production_standard']) == int and quality['production_standard'] == 1), 'unsupported production standard')
    require(nonempty(quality.get('scope')) and isinstance(quality.get('limits'), dict), 'quality contract incomplete')
    from production_contract import validate as validate_production
    validate_production(spec)
    require(bool(spec.get("construction_plan")) == bool(spec.get("construction_receipt")), "construction plan and receipt must remain paired")
    if spec.get("construction_plan"):
        from construction_plan import validate as validate_construction
        result = validate_construction(path)
        require(result["ok"], "construction plan: " + "; ".join(result["errors"]))
    shape_foundation.contract(spec,strict=False)
    return spec, resources


def reference_fingerprint(spec):
    """Only reference approval and task scope may survive explicit implementation rebase."""
    value = {key: spec.get(key) for key in ('id', 'domain', 'references', 'quality_contract')}
    if spec.get('quality_contract', {}).get('reference_standard') in (1,2):
        value['reference_plan'] = spec.get('reference_plan')
        value['reference_evidence_sources'] = [r for r in spec.get('source_files', []) if r['path'] == spec.get('reference_plan')]
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_evidence(spec_path, evidence_path, stage, reused_reference_review=False):
    spec, resources = validate_spec(spec_path)
    if STAGES.index(stage) >= STAGES.index('references'):
        from reference_set import validate as validate_reference_set
        validate_reference_set(spec_path, 'references' if stage == 'references' else 'spec')
    if STAGES.index(stage)>=STAGES.index('spec'):
        from shape_foundation import contract
        contract(spec)
    if STAGES.index(stage) >= STAGES.index('spec') and spec.get('quality_contract', {}).get('production_standard') == 1:
        require(spec.get('production_contract') is not None, 'production contract required before spec approval')
    if STAGES.index(stage) >= STAGES.index('body') and spec.get('production_contract') is not None:
        from production_checks import evaluate
        require(evaluate(spec)['passed'], 'production geometry checks failed')
    if STAGES.index(stage) >= STAGES.index('body') and spec.get('construction_plan'):
        from construction_plan import validate as validate_construction
        result = validate_construction(spec_path, 'body')
        require(result['ok'], 'local construction review: ' + '; '.join(result['errors']))
    if STAGES.index(stage)>=STAGES.index('body'):
        import repair_project
        repair_project.gate(spec_path,True)
    epath = Path(evidence_path).resolve()
    e = read(epath)
    if STAGES.index(stage)>=STAGES.index('body'):
        from shape_foundation import enabled, gate
        if enabled(spec):gate(spec_path,True,e.get('foundation_review'))
    require(e.get('stage') == stage, 'evidence stage mismatch')
    require(e.get('verdict') == 'pass', 'explicit passing review required')
    require(e.get('acceptance') == 'quality_passed', 'baseline acceptance is not a quality pass')
    scope = spec['quality_contract']['scope']
    require(e.get('review_scope') == scope, 'explicit matching review scope required')
    require(nonempty(e.get('reviewer')) and nonempty(e.get('rationale')), 'reviewer and rationale required')
    if reused_reference_review:
        require(stage in ('intake', 'references'), 'only reference reviews may be reused')
        require(isinstance(e.get('resource_hashes'), dict), 'missing resource evidence')
        require(all(e['resource_hashes'].get(r['path']) == r['sha256'] for r in spec['references']), 'stale reference evidence')
    else:
        require(e.get('spec_sha256') == digest(spec_path), 'stale spec evidence')
        require(e.get('resource_hashes') == resources, 'stale/incomplete resource evidence')
    artifacts = e.get('artifacts')
    require(isinstance(artifacts, list) and artifacts, 'review artifacts required')
    artifact_paths = [a.get('path') for a in artifacts]
    require(len(artifact_paths) == len(set(artifact_paths)), 'duplicate artifact paths')
    for a in artifacts:
        require(nonempty(a.get('path')), 'artifact path missing')
        artifact = epath.parent / a['path']
        require(artifact.is_file() and digest(artifact) == a.get('sha256'), 'missing/stale artifact')
    results = e.get('check_results', [])
    require(isinstance(results, list), 'check_results must be list')
    result_ids = [r.get('id') for r in results]
    require(len(result_ids) == len(set(result_ids)), 'duplicate check results')
    by_id = {r.get('id'): r for r in results}
    def check_result(r, label):
        require(r.get('verdict') == 'pass' and nonempty(r.get('reviewer')) and nonempty(r.get('method')), f'required check missing: {label}')
        require(r.get('scope') == scope, f'check scope missing/mismatched: {label}')
        coverage = r.get('artifact_paths')
        require(isinstance(coverage, list) and coverage and all(x in artifact_paths for x in coverage), f'check artifact coverage missing: {label}')
    check_result(by_id.get('stage:' + stage, {}), 'stage:' + stage)
    for c in spec['checks']:
        if c['required'] and c.get('stage', 'review') == stage:
            r = by_id.get(c['id'], {})
            check_result(r, c['id'])
            if 'visual' in c['kind'].lower():
                require(r['method'] == 'visual', 'visual check cannot pass from numeric metrics alone')
    if STAGES.index(stage) >= STAGES.index('references'):
        require(spec['references'] and all(r['approved'] for r in spec['references']), 'approved references required')
    if STAGES.index(stage) >= STAGES.index('body'):
        require(spec['source_files'] and spec['components'], 'body requires sources and components')
    if stage in ('review', 'delivery'):
        require(any(c['required'] and 'visual' in c['kind'].lower() and STAGES.index(c.get('stage', 'review')) <= STAGES.index('review') for c in spec['checks']), 'required visual review must be declared')
    from production_contract import validate_evidence as validate_production_evidence
    from production_evidence import validate as validate_views
    validate_production_evidence(spec, e, stage)
    validate_views(spec, e, stage, epath)
    if STAGES.index(stage)>=STAGES.index('body') and spec.get('quality_contract',{}).get('reference_standard')==2:
        from shape_acceptance import validate_review as validate_shape_review
        validate_shape_review(spec_path,spec,read(Path(spec_path).parent/spec['reference_plan']),e,epath)
    if e.get("repair_record"):
        from repair_review import validate as validate_repair
        require(e["repair_record"] in artifact_paths, "repair record must be a hashed artifact")
        validate_repair(epath.parent / e["repair_record"], spec_path)
    return e


def status(state_path):
    state = read(state_path)
    require(state.get('schema_version') == 1, 'unsupported state schema')
    spec_path = Path(state['spec_path'])
    valid = []
    issues = []
    try:
        current_spec, _ = validate_spec(spec_path)
        require(not state.get('reference_standard') or current_spec.get('quality_contract', {}).get('reference_standard') == state['reference_standard'], 'reference policy removed or downgraded')
        require(not state.get('production_standard') or current_spec.get('quality_contract', {}).get('production_standard') == state['production_standard'], 'production policy removed or downgraded')
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'completed': [], 'next': STAGES[0], 'issues': [str(exc)], 'blocked': True}
    for stage in STAGES:
        record = state.get('stages', {}).get(stage)
        if not record:
            break
        try:
            require(digest(record['evidence_path']) == record['evidence_sha256'], 'evidence file changed')
            reused = record.get('reused_for_spec_sha256') is not None
            if reused:
                require(record['reused_for_spec_sha256'] == digest(spec_path), 'explicit rebase required for changed spec')
                require(record.get('reference_fingerprint') == reference_fingerprint(current_spec), 'reference approval/scope changed')
            validate_evidence(spec_path, record['evidence_path'], stage, reused)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            issues.append(f'{stage}: {exc}')
            break
        valid.append(stage)
    return {'completed': valid, 'next': STAGES[len(valid)] if len(valid) < len(STAGES) else None, 'issues': issues, 'blocked': bool(issues)}


def init(spec_path, state_path):
    spec, _ = validate_spec(spec_path)
    require(not Path(state_path).exists(), 'state already exists; use status/next to resume')
    save(state_path, {'schema_version': 1, 'spec_path': str(Path(spec_path).resolve()), 'stages': {}, 'reference_standard': spec.get('quality_contract', {}).get('reference_standard'), 'production_standard': spec.get('quality_contract', {}).get('production_standard'), 'foundation_standard':spec.get('quality_contract',{}).get('foundation_standard')})
    return status(state_path)


def mark(state_path, evidence_path):
    state = read(state_path)
    current = status(state_path)
    stage = current['next']
    require(not state.get('reference_standard') or read(state['spec_path']).get('quality_contract', {}).get('reference_standard') == state['reference_standard'], 'reference policy removed or downgraded')
    require(stage is not None, 'workflow already complete')
    require(not state.get('production_standard') or read(state['spec_path']).get('quality_contract', {}).get('production_standard') == state['production_standard'], 'production policy removed or downgraded')
    validate_evidence(state['spec_path'], evidence_path, stage)
    # Replacing stale evidence removes all downstream records; they must be reviewed again.
    state['stages'] = {s: state['stages'][s] for s in current['completed']}
    state['stages'][stage] = {'evidence_path': str(Path(evidence_path).resolve()), 'evidence_sha256': digest(evidence_path), 'reference_fingerprint': reference_fingerprint(read(state['spec_path']))}
    save(state_path, state)
    return status(state_path)


def rebase(state_path):
    """Explicitly preserve unchanged intake/reference approvals and archive later work.

    Never replays spec/body reviews. Changed references/scope cannot be rebased.
    Existing evidence files and their artifacts must remain intact.
    """
    state = read(state_path)
    spec, _ = validate_spec(state['spec_path'])
    require(not state.get('reference_standard') or spec.get('quality_contract', {}).get('reference_standard') == state['reference_standard'], 'reference policy removed or downgraded')
    fingerprint = reference_fingerprint(spec)
    preserved = {}
    for stage in ('intake', 'references'):
        record = state.get('stages', {}).get(stage)
        if not record:
            break
        require(record.get('reference_fingerprint') == fingerprint, 'reference or scope changed; new intake/reference review required')
        require(digest(record['evidence_path']) == record['evidence_sha256'], 'evidence file changed')
        validate_evidence(state['spec_path'], record['evidence_path'], stage, True)
        preserved[stage] = dict(record, reused_for_spec_sha256=digest(state['spec_path']))
    require(preserved, 'no reference reviews eligible for reuse')
    state.setdefault('archives', []).append({'reason': 'explicit implementation rebase', 'for_spec_sha256': digest(state['spec_path']), 'stages': state['stages']})
    state['stages'] = preserved
    save(state_path, state)
    return status(state_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init', help='Validate spec and initialize a new task; never overwrite state')
    p.add_argument('--spec', required=True); p.add_argument('--state', required=True)
    p = sub.add_parser('validate', help='Validate spec structure and current resource hashes')
    p.add_argument('--spec', required=True)
    for command in ('status', 'next'):
        p = sub.add_parser(command, help='Revalidate recorded evidence and report earliest incomplete/stale stage')
        p.add_argument('--state', required=True)
    p = sub.add_parser('rebase', help='Explicitly reuse unchanged reference approvals; archive and invalidate later stages')
    p.add_argument('--state', required=True)
    p = sub.add_parser('mark', help='Record explicit review evidence for the next stage')
    p.add_argument('--state', required=True); p.add_argument('--evidence', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'validate':
            _, resources = validate_spec(args.spec)
            result = {'valid': True, 'resources': resources}
        elif args.command == 'init':
            result = init(args.spec, args.state)
        elif args.command == 'rebase':
            result = rebase(args.state)
        elif args.command == 'mark':
            result = mark(args.state, args.evidence)
        else:
            result = status(args.state)
            if args.command == 'next':
                result['action'] = ('Resolve issues and submit fresh review evidence' if result['issues'] else 'Prepare explicit review evidence for next stage') if result['next'] else 'All stages have recorded passing reviews; no independent quality guarantee is implied'
        print(json.dumps(result, indent=2))
        return 1 if result.get('blocked') else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
