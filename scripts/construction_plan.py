#!/usr/bin/env python3
"""Compile reference-backed form recipes; validate provenance, geometry and local reviews.
Checks establish consistency, never visual correctness or physical reconstruction truth.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def compiler_hash():
    import form_construction
    return file_hash(form_construction.__file__)


def compile_geometry(recipe):
    from form_construction import compile_recipe
    return compile_recipe(recipe)['geometry']


def _index(items, label):
    if isinstance(items, dict):
        if any(not isinstance(k,str) or not k or not isinstance(v,dict) for k,v in items.items()):
            raise ValueError(f'{label}: invalid keyed objects')
        return items
    ids = [x.get('id') for x in items]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError(f'{label}: missing/duplicate IDs')
    return dict(zip(ids, items))


def apply_transform(component, part):
    transform = part.get('transform', {})
    if not isinstance(transform,dict) or set(transform)-{'position','rotation','scale'}:
        raise ValueError('invalid construction transform fields')
    for key, vector in transform.items():
        if not isinstance(vector,list) or len(vector)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector):
            raise ValueError('transform requires finite numeric XYZ')
        if key=='scale' and min(vector)<=0:
            raise ValueError('transform scale must be positive')
        component[key]=copy.deepcopy(vector)

def normalized_materials(materials):
    materials=copy.deepcopy(materials)
    values=materials.values() if isinstance(materials,dict) else materials
    for material in values:
        for texture in material.get('maps',{}).values():
            texture.pop('path',None)
    return materials

def _check_plan(spec, plan, directory, stage):
    if plan.get('version') != 1 or not plan.get('parts'):
        raise ValueError('construction plan requires version 1 and parts')
    components = _index(spec.get('components', []), 'components')
    refs = _index(spec.get('references', []), 'references')
    _index(plan['parts'], 'parts')
    cameras = _index(spec.get('cameras', []), 'cameras')
    targets = [p.get('component_id') for p in plan['parts']]
    if len(targets) != len(set(targets)):
        raise ValueError('duplicate component recipes')
    for cid in plan.get('protected_components', []):
        if cid not in components or cid in targets:
            raise ValueError('protected component unknown or targeted')
    if not plan.get('protected_views') or any(v not in cameras for v in plan['protected_views']):
        raise ValueError('protected_views must name known cameras')
    for part in plan['parts']:
        cid = part['component_id']
        if cid not in components:
            raise ValueError(f'unknown component {cid}')
        for field in ('outline', 'thickness', 'root', 'method_rationale'):
            if not isinstance(part.get(field), str) or not part[field].strip():
                raise ValueError(f'{cid}: missing {field}')
        apply_transform({},part)
        recipe = part.get('recipe', {})
        if recipe.get('component_id') != cid:
            raise ValueError('recipe component mismatch')
        source = recipe.get('source', {})
        rid = source.get('reference_id')
        if rid not in refs:
            raise ValueError('unknown recipe reference')
        ref = refs[rid]
        source_path = directory / ref['path']
        if file_hash(source_path) != ref.get('sha256'):
            raise ValueError('stale reference image')
        size, roi = ref.get('image_size', []), source.get('roi', [])
        from PIL import Image
        with Image.open(source_path) as image:
            if list(image.size) != size:
                raise ValueError('reference declared dimensions mismatch actual image')
        if len(size) != 2 or len(roi) != 4 or any(not isinstance(v, (float, int)) or isinstance(v,bool) or not math.isfinite(v) for v in roi):
            raise ValueError('invalid reference size/ROI')
        x,y,w,h = roi
        if min(x,y) < 0 or min(w,h) <= 0 or x+w > size[0] or y+h > size[1]:
            raise ValueError('ROI outside image')
        links = part.get('parameter_links', [])
        if not links:
            raise ValueError('missing actual parameter links')
        for link in links:
            if not link.get('feature') or not isinstance(link.get('parameter_path'), list) or not link['parameter_path']:
                raise ValueError('invalid parameter link')
            value = recipe.get('parameters', {})
            try:
                for key in link['parameter_path']:
                    value = value[key]
            except (KeyError, IndexError, TypeError):
                raise ValueError('parameter link does not resolve')
        compile_geometry(recipe)
        checks = part.get('local_checks', [])
        if len({c.get('view') for c in checks}) < 2:
            raise ValueError('at least two distinct local review views required')
        for check in checks:
            if check.get('view') not in cameras or set(check.get('aspects', [])) != {'outline','volume','connection'}:
                raise ValueError('local review needs known view and all three aspects')
            if check.get('status') not in ('pending','pass','fail'):
                raise ValueError('invalid local review status')
            if stage == 'body' and check['status'] != 'pass':
                raise ValueError('local visual review not passed')
            if check['status'] in ('pass','fail'):
                evidence = check.get('evidence', {})
                if not check.get('reviewer') or not check.get('notes'):
                    raise ValueError('local visual review requires reviewer and notes')
                if evidence.get('geometry_sha256') != digest(compile_geometry(recipe)):
                    raise ValueError('local visual evidence geometry stale')
                if part.get('transform') and evidence.get('transform_sha256') != digest(part['transform']):
                    raise ValueError('local visual evidence transform stale')
                if evidence.get('camera_sha256') != digest(cameras[check['view']]):
                    raise ValueError('local visual evidence camera stale')
                if file_hash(directory / evidence['path']) != evidence.get('sha256'):
                    raise ValueError('local visual evidence artifact stale')
    return targets


def apply(spec_path, plan_path, out):
    spec_path, out = Path(spec_path).resolve(), Path(out).resolve()
    if out.parent != spec_path.parent:
        raise ValueError('output must share spec directory; copy project first to retain source paths')
    if out.exists():
        raise ValueError('refusing to overwrite output')
    spec, plan = read(spec_path), read(plan_path)
    targets = _check_plan(spec, plan, spec_path.parent, 'spec')
    observations = spec.get('observations', [])
    stale = {o['id'] for o in observations if o.get('component_id') in targets}
    invalidated = set(plan.get('invalidated_observation_ids', []))
    if stale != invalidated:
        raise ValueError('changed topology observations must be explicitly invalidated, no retained vertex bindings')
    result = copy.deepcopy(spec)
    result['observations'] = [o for o in observations if o['id'] not in stale]
    by_id = {c['id']:c for c in result['components']}
    for part in plan['parts']:
        by_id[part['component_id']]['geometry'] = compile_geometry(part['recipe'])
        apply_transform(by_id[part['component_id']],part)
    baseline_path = out.with_suffix('.construction-baseline.json')
    plan_out = out.with_suffix('.construction-plan.json')
    if baseline_path.exists() or plan_out.exists():
        raise ValueError('refusing to overwrite construction snapshots')
    for part in plan['parts']:
        check = {'id':'form:'+part['id'],'kind':'visual','required':True,'stage':'body'}
        result.setdefault('checks', [])[:] = [c for c in result.get('checks', []) if c['id'] != check['id']]
        result['checks'].append(check)
    result['construction_plan'] = plan_out.name
    result['construction_receipt'] = {'version':1, 'baseline':{'path':baseline_path.name,'sha256':file_hash(spec_path)},'plan_sha256':digest(plan),'compiler_sha256':compiler_hash(),'invalidated_observation_ids':sorted(stale)}
    sources = result.setdefault('source_files', [])
    baseline_path.write_bytes(spec_path.read_bytes())
    plan_out.write_text(json.dumps(plan, indent=2)+'\n')
    for path in (baseline_path, plan_out):
        sources.append({'path':path.name,'sha256':file_hash(path)})
    for part in plan['parts']:
        for check in part['local_checks']:
            if check.get('evidence'):
                artifact = check['evidence']
                if artifact['path'] not in {s['path'] for s in result.get('references', []) + sources}:
                    sources.append({'path':artifact['path'],'sha256':artifact['sha256']})
    out.write_text(json.dumps(result, indent=2)+'\n')
    report = validate(out)
    if not report['ok']:
        raise ValueError('; '.join(report['errors']))
    return report


def validate(spec_path, stage='spec'):
    errors = []
    try:
        if stage not in ('spec','body'):
            raise ValueError('stage must be spec or body')
        path = Path(spec_path).resolve()
        spec = read(path)
        plan = read(path.parent / spec['construction_plan'])
        targets = _check_plan(spec, plan, path.parent, stage)
        receipt = spec['construction_receipt']
        if receipt['compiler_sha256'] != compiler_hash() or receipt['plan_sha256'] != digest(plan):
            raise ValueError('stale compiler/plan receipt; reapply from baseline')
        baseline_path = path.parent / receipt['baseline']['path']
        if file_hash(baseline_path) != receipt['baseline']['sha256']:
            raise ValueError('baseline stale')
        registered = {s['path']:s['sha256'] for s in spec.get('source_files',[]) + spec.get('references',[])}
        for resource in (spec['construction_plan'], receipt['baseline']['path']):
            if registered.get(resource) != file_hash(path.parent/resource):
                raise ValueError('construction resource missing or stale in source_files')
        for part in plan['parts']:
            expected_check = {'id':'form:'+part['id'],'kind':'visual','required':True,'stage':'body'}
            if expected_check not in spec.get('checks',[]):
                raise ValueError('required body visual check missing')
            for check in part['local_checks']:
                if check.get('evidence') and registered.get(check['evidence']['path']) != check['evidence']['sha256']:
                    raise ValueError('local evidence not registered in source_files')
        baseline = read(baseline_path)
        old, current = _index(baseline['components'],'baseline components'), _index(spec['components'],'components')
        if set(old) != set(current):
            raise ValueError('component inventory changed')
        recipes = {p['component_id']:p['recipe'] for p in plan['parts']}
        parts = {p['component_id']:p for p in plan['parts']}
        for cid, component in current.items():
            expected = copy.deepcopy(old[cid])
            if cid in targets:
                expected['geometry'] = compile_geometry(recipes[cid])
                apply_transform(expected,parts[cid])
            if digest(expected) != digest(component):
                raise ValueError(f'{cid}: compiled geometry mismatch or protected component modified')
        for key in ('cameras','parameters'):
            if digest(spec.get(key)) != digest(baseline.get(key)):
                raise ValueError(f'protected {key} modified')
        if digest(normalized_materials(spec.get('materials',{}))) != digest(normalized_materials(baseline.get('materials',{}))):
            raise ValueError('protected materials modified')
        material_values=spec.get('materials',{})
        material_values=material_values.values() if isinstance(material_values,dict) else material_values
        for material in material_values:
            for texture in material.get('maps',{}).values():
                if file_hash(path.parent/texture['path']) != texture.get('sha256'):
                    raise ValueError('material texture source changed')
        normalize_refs = lambda refs: [{k:v for k,v in r.items() if k != 'path'} for r in refs]
        if digest(normalize_refs(spec.get('references',[]))) != digest(normalize_refs(baseline.get('references',[]))):
            raise ValueError('protected reference identity modified')
        invalid = sorted(o['id'] for o in baseline.get('observations',[]) if o.get('component_id') in targets)
        if sorted(receipt['invalidated_observation_ids']) != invalid or sorted(plan.get('invalidated_observation_ids',[])) != invalid:
            raise ValueError('invalid observation invalidation record')
        expected_obs = [o for o in baseline.get('observations',[]) if o['id'] not in invalid]
        if digest(spec.get('observations',[])) != digest(expected_obs):
            raise ValueError('observations altered or stale binding retained')
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        errors.append(str(exc))
    return {'ok':not errors,'errors':errors,'stage':stage,'visual_certified':False,'scope':'recipe/provenance consistency; human local review remains required'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('apply'); a.add_argument('--spec',required=True); a.add_argument('--plan',required=True); a.add_argument('--out',required=True)
    v=sub.add_parser('check'); v.add_argument('--spec',required=True); v.add_argument('--stage',choices=['spec','body'],default='spec')
    args=parser.parse_args()
    try:
        result = apply(args.spec,args.plan,args.out) if args.command=='apply' else validate(args.spec,args.stage)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        result={'ok':False,'errors':[str(exc)]}
    print(json.dumps(result,indent=2)); return 0 if result['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
