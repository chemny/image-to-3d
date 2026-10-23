#!/usr/bin/env python3
"""Audit reference usage and body-before-details evidence. Does not infer or fit geometry."""
import argparse
import hashlib
import json
import math
from pathlib import Path

VIEWS = ['front', 'rear', 'left', 'right', 'front-left', 'front-right', 'rear-left', 'rear-right', 'top']
DETAILS = ['hood-fender', 'fascia-lamp', 'roof-cabin', 'side-panels', 'rear-shoulder', 'wheel-arch']
REGIONS = ['hood-fender', 'front-face', 'roof-cabin', 'side-body', 'rear-shoulder', 'rear-face', 'wheel-arch']
STAGES = ['review', 'references', 'construction', 'details']

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def verify(base, ref):
    path = (base / ref['path']).resolve()
    if not path.is_file() or sha(path) != ref['sha256']:
        raise ValueError('missing or changed asset: ' + str(path))
    return path

def audit(task_path, stage):
    task_path = Path(task_path)
    base = task_path.parent
    task = json.loads(task_path.read_text())
    if task.get('schema_version') != 1:
        raise ValueError('unsupported schema_version')
    issues = []
    warnings = []
    rank = STAGES.index(stage)
    sources, boards = task.get('sources', []), task.get('boards', [])
    if not sources or not boards:
        issues.append('sources_and_boards_required')
    for ref in sources + boards:
        verify(base, ref)
    views = task.get('required_views', VIEWS)
    details = task.get('required_details', DETAILS)
    regions = task.get('required_regions', REGIONS)
    if any(not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) for ids in (views, details, regions)):
        raise ValueError('coverage must be nonempty and unique')
    if (views != VIEWS or details != DETAILS or regions != REGIONS) and not task.get('scope_override', {}).get('user_message'):
        issues.append('scope_override_requires_user_instruction')
    planned = task.get('coverage_plan', [])
    planned_ids = [a['id'] for a in planned]
    if len(planned_ids) != len(set(planned_ids)):
        issues.append('duplicate_coverage_id')
    if not set(views + details) <= set(planned_ids):
        issues.append('missing_planned_coverage')
    for entry in planned:
        if not entry.get('purpose'):
            issues.append('missing_reference_purpose:' + entry['id'])
    if rank >= 1:
        approval = task.get('approval', {})
        board_hashes = {b['sha256'] for b in boards}
        if approval.get('status') not in ('approved', 'explicitly_waived') or not approval.get('user_message'):
            issues.append('awaiting_user_reference_approval')
        elif set(approval.get('board_hashes', [])) != board_hashes:
            issues.append('approval_does_not_bind_current_boards')
        assets = task.get('assets', [])
        asset_ids = [a['id'] for a in assets]
        if len(asset_ids) != len(set(asset_ids)):
            issues.append('duplicate_asset_id')
        if len({a['sha256'] for a in assets}) != len(assets):
            issues.append('independent_references_reuse_same_pixels')
        if set(asset_ids) != set(views + details):
            issues.append('independent_reference_coverage_mismatch')
        for a in assets:
            path = verify(base, a)
            from PIL import Image
            with Image.open(path) as im:
                dimensions = list(im.size)
            if a.get('dimensions') != dimensions:
                issues.append('incorrect_native_dimensions:' + a['id'])
            if a.get('kind') != ('view' if a['id'] in views else 'detail'):
                issues.append('incorrect_reference_kind:' + a['id'])
            if a.get('origin') not in ('user_supplied', 'real', 'generated', 'inferred'):
                issues.append('missing_reference_origin:' + a['id'])
            usable = a.get('adequacy', {})
            if usable.get('status') not in ('accepted', 'accepted_limited') or not usable.get('reason'):
                issues.append('reference_not_usable:' + a['id'])
            if max(dimensions) < task.get('target_long_edge', 2048):
                warnings.append('below_native_resolution_target:' + a['id'])
                if usable.get('status') != 'accepted_limited' or not usable.get('impact'):
                    issues.append('resolution_limit_not_assessed:' + a['id'])
            if usable.get('status') == 'accepted_limited' and not usable.get('impact'):
                issues.append('reference_limit_not_assessed:' + a['id'])
    if rank >= 2:
        assets = {a['id']: a for a in task.get('assets', [])}
        constraints = task.get('constraints', [])
        covered, used = set(), set()
        observed_features = {}
        ids = [c['id'] for c in constraints]
        if len(ids) != len(set(ids)):
            issues.append('duplicate_constraint_id')
        for c in constraints:
            cid = c['id']
            declared = set(c.get('source_ids', []))
            observed = set()
            for obs in c.get('observations', []):
                rid = obs['reference_id']
                if rid not in assets or obs.get('reference_sha256') != assets[rid]['sha256']:
                    issues.append('observation_identity_mismatch:' + cid)
                    continue
                points = obs.get('points', [])
                if len(points) < 2 or any(not isinstance(p, list) or len(p) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in p) for p in points):
                    issues.append('invalid_normalized_observation:' + cid)
                    continue
                if not obs.get('feature_id') or not obs.get('control_targets'):
                    issues.append('observation_requires_semantic_mapping:' + cid)
                signature = (rid, json.dumps(points, sort_keys=True))
                prior = observed_features.get(signature)
                if prior and prior != obs.get('feature_id'):
                    issues.append('same_curve_labeled_as_different_feature:' + cid)
                observed_features[signature] = obs.get('feature_id')
                observed.add(rid)
            if not declared or observed != declared:
                issues.append('constraint_without_matching_observations:' + cid)
            if len(observed) < 2 or not observed.intersection(views):
                issues.append('constraint_requires_multiview_support:' + cid)
            if c.get('origin') not in ('observed', 'inferred'):
                issues.append('constraint_origin_required:' + cid)
            if c.get('origin') == 'inferred' and not c.get('uncertainty'):
                issues.append('inferred_constraint_requires_uncertainty:' + cid)
            if not c.get('construction_data'):
                issues.append('missing_surface_control_data:' + cid)
            else:
                control_path = verify(base, c['construction_data'])
                targets = c['construction_data'].get('targets', [])
                if not targets:
                    issues.append('surface_control_targets_required:' + cid)
                else:
                    control_data = json.loads(control_path.read_text())
                    if any(k not in control_data for k in targets):
                        issues.append('surface_control_target_missing:' + cid)
                    if any(not set(o.get('control_targets', [])).issubset(targets) for o in c.get('observations', [])):
                        issues.append('observation_target_outside_region:' + cid)
            covered.add(c.get('region'))
            used.update(observed)
        for region in set(regions) - covered:
            issues.append('unconstrained_region:' + region)
        for rid in set(views + details) - used:
            issues.append('unused_reference:' + rid)
        cameras = {c['view']: c for c in task.get('cameras', [])}
        for view in views:
            camera = cameras.get(view, {})
            if camera.get('status') != 'validated' or not camera.get('independent_evidence'):
                issues.append('camera_not_validated:' + view)
            else:
                verify(base, camera['independent_evidence'])
    if rank >= 3:
        review = task.get('body_review', {})
        if review.get('status') != 'passed':
            issues.append('body_not_passed')
        model = task.get('model')
        if not model:
            issues.append('current_model_required')
        else:
            verify(base, model)
            if review.get('model') != model:
                issues.append('body_review_model_mismatch')
        binding = hashlib.sha256(json.dumps({'constraints':task.get('constraints', []), 'cameras':task.get('cameras', []), 'assets':task.get('assets', [])}, sort_keys=True).encode()).hexdigest()
        if review.get('constraints_sha256') != binding:
            issues.append('body_review_constraint_binding_mismatch')
        outputs = review.get('outputs', {})
        for view in views:
            for suffix in ('gray', 'render', 'difference', 'landmark'):
                if view + '.' + suffix not in outputs:
                    issues.append('missing_body_evidence:' + view + '.' + suffix)
        if 'reflection-diagnostic' not in outputs:
            issues.append('missing_reflection_diagnostic')
        if not review.get('criteria', {}).get('calibrated') or not review.get('criteria', {}).get('basis'):
            issues.append('body_criteria_not_calibrated')
        for ref in outputs.values():
            verify(base, ref)
    return {'schema_version':1, 'stage':stage, 'record_sha256':sha(task_path), 'status':'needs_action' if issues else 'record_valid', 'may_advance':not issues, 'may_build_model':rank >= 1 and not issues, 'may_add_details':rank >= 3 and not issues, 'may_deliver':False, 'issues':sorted(set(issues)), 'warnings':sorted(set(warnings)), 'boundary':'records_and_identity_only_not_visual_judgment_or_automatic_modeling'}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check'])
    p.add_argument('--task', required=True, type=Path)
    p.add_argument('--stage', required=True, choices=STAGES)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    try:
        result = audit(a.task, a.stage)
    except (ValueError, KeyError, TypeError, OSError, ImportError) as e:
        result = {'stage':a.stage, 'status':'invalid_evidence', 'may_advance':False, 'may_build_model':False, 'may_add_details':False, 'may_deliver':False, 'issues':[str(e)]}
    if a.out:
        with a.out.open('x') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['may_advance'] else 2

if __name__ == '__main__':
    raise SystemExit(main())
