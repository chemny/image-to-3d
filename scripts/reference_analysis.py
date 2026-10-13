#!/usr/bin/env python3
"""Validate explicit image analysis records; does not invent observations or inspect pixels.

Reference records additionally need image_size:[width,height]. Generated/derived
references need source_reference_ids and provenance. Feature inventory entries:
{reference_id,feature,component_id,required:boolean,visibility:visible|occluded|hidden}.
Observations need roi:[x,y,width,height], target and binding to real component.
Hidden features require an inference record {reference_id,feature,component_id,
rationale,confidence:0..1}; these do not establish hidden ground truth.
"""
import argparse
import json
import math
from pathlib import Path
import sys


def require(ok, message):
    if not ok: raise ValueError(message)


def finite(values):
    return all(type(x) in (int,float) and math.isfinite(x) for x in values)


def validate(analysis, spec=None):
    """Accept a complete spec, or explicit analysis records plus an authoritative spec."""
    if spec is not None:
        merged = dict(spec)
        originals = {r['id']: r for r in spec.get('references', [])}
        extras = {r['id']: r for r in analysis.get('references', [])}
        require(set(extras) <= set(originals), 'analysis reference not in spec')
        for rid, record in extras.items():
            for key in ('origin', 'path', 'sha256', 'approved'):
                if key in record:
                    require(record[key] == originals[rid].get(key), 'analysis cannot change reference identity: ' + key)
        merged['references'] = [dict(r, **extras.get(r['id'], {})) for r in originals.values()]
        if 'observations' in analysis:
            require(analysis['observations'] == spec.get('observations', []), 'analysis observations must match model spec exactly')
        for key in ('feature_inventory', 'observations', 'inferences'):
            if key in analysis: merged[key] = analysis[key]
        spec = merged
    else:
        spec = analysis
    return _validate(spec)


def _validate(spec):
    references = spec.get('references', [])
    refs = {r['id']:r for r in references}
    require(len(refs)==len(references) and refs, 'unique references required')
    for r in references:
        require(r.get('origin') in ('original','generated','derived','synthetic'), 'explicit photographic/design reference origin required')
        size=r.get('image_size')
        require(isinstance(size,list) and len(size)==2 and finite(size) and min(size)>0, 'image_size required')
        if r['origin']=='synthetic':
            require(spec.get('quality_contract', {}).get('scope') == 'synthetic-software-test' and r.get('approved') is False, 'synthetic reference requires test-only scope and no approval')
            require(isinstance(r.get('provenance'), str) and r['provenance'].strip(), 'synthetic fixture provenance required')
            require(not r.get('source_reference_ids'), 'synthetic fixture must not imply reference measurement provenance')
        if r['origin'] in ('generated', 'derived'):
            sources=r.get('source_reference_ids')
            require(isinstance(sources,list) and sources and all(x in refs and x!=r['id'] for x in sources), 'generated/derived reference source IDs required')
            require(isinstance(r.get('provenance'),str) and r['provenance'].strip(), 'generated/derived provenance required')
    def walk(rid, seen):
        require(rid not in seen,'reference provenance cycle')
        for other in refs[rid].get('source_reference_ids',[]): walk(other,seen|{rid})
    for rid in refs: walk(rid,set())
    components={c['id'] for c in spec.get('components',[])}
    parameters=set(spec.get('parameters',{}))
    observations=spec.get('observations',[])
    covered=set(); observed_params=set(); seen=set()
    for o in observations:
        require(o.get('id') not in seen and isinstance(o.get('id'),str),'unique observation ID required'); seen.add(o['id'])
        require(o.get('reference_id') in refs and o.get('component_id') in components,'unknown observation reference/component')
        require(isinstance(o.get('parameter_ids'),list) and set(o['parameter_ids']) <= parameters,'unknown observation parameters')
        require(o['parameter_ids'] or o.get('fixed') is True,'observation needs parameter binding or explicit fixed feature')
        bindings=int('local_point' in o)+int('vertex_index' in o)+int('patch_id' in o or 'uv' in o)
        require(bindings==1,'one model landmark binding required')
        if 'local_point' in o: require(isinstance(o['local_point'],list) and len(o['local_point'])==3,'local point must have three coordinates')
        if 'vertex_index' in o: require(type(o['vertex_index']) is int and o['vertex_index']>=0,'invalid vertex index')
        if 'patch_id' in o or 'uv' in o: require('patch_id' in o and isinstance(o.get('uv'),list) and len(o['uv'])==2 and finite(o['uv']) and all(0<=v<=1 for v in o['uv']),'patch binding incomplete')
        roi=o.get('roi'); target=o.get('target'); width,height=refs[o['reference_id']]['image_size']
        require(isinstance(roi,list) and len(roi)==4 and finite(roi),'explicit image ROI required')
        x,y,w,h=roi
        require(x>=0 and y>=0 and w>0 and h>0 and x+w<=width and y+h<=height,'ROI outside image')
        require(isinstance(target,list) and len(target)==2 and finite(target) and x<=target[0]<=x+w and y<=target[1]<=y+h,'target outside ROI')
        require(o.get('role') in ('calibration','validation'),'explicit observation role required')
        covered.add((o['reference_id'],o.get('feature'),o['component_id'])); observed_params.update(o['parameter_ids'])
    inventory=spec.get('feature_inventory')
    require(isinstance(inventory,list) and inventory,'feature inventory required')
    inferred=set()
    for i in spec.get('inferences',[]):
        require(i.get('reference_id') in refs and i.get('component_id') in components,'unknown inference reference/component')
        require(isinstance(i.get('rationale'),str) and i['rationale'].strip(),'inference rationale required')
        require(finite([i.get('confidence')]) and 0<=i['confidence']<=1,'inference confidence required')
        inferred.add((i['reference_id'],i.get('feature'),i['component_id']))
    inventory_keys=set()
    for f in inventory:
        require(f.get('reference_id') in refs and f.get('component_id') in components,'unknown inventory reference/component')
        key=(f['reference_id'],f.get('feature'),f['component_id'])
        require(isinstance(f.get('feature'),str) and f['feature'] and key not in inventory_keys,'missing/duplicate inventory feature')
        inventory_keys.add(key)
        require(type(f.get('required')) is bool and f.get('visibility') in ('visible','hidden','occluded'),'feature visibility/required must be explicit')
        if f['visibility'] != 'visible':
            require(key not in covered,'hidden/occluded feature cannot be treated as measured ground truth')
        if f['required']:
            if f['visibility']=='visible': require(key in covered,'required visible feature has no observation: '+f['feature'])
            else:
                require(key in inferred,'hidden/occluded feature needs explicit inference: '+f['feature'])
                require(key not in covered,'hidden/occluded feature cannot be treated as measured ground truth')
    require(covered <= inventory_keys,'observation missing from feature inventory')
    return {'valid':True,'observations':len(observations),'declared_features':len(inventory),'unobserved_parameters':sorted(parameters-observed_params),
            'inferred_features':len(inferred),'visual_pass':False,
            'limits':['checks declared inventory coverage only; cannot detect features omitted from the inventory','generated views and hidden inferences are design hypotheses, not physical measurements']}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('command',choices=['validate']); p.add_argument('spec')
    args=p.parse_args()
    try:
        print(json.dumps(validate(json.loads(Path(args.spec).read_text())),indent=2));return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'error':str(exc)}),file=sys.stderr);return 2


if __name__=='__main__': sys.exit(main())
