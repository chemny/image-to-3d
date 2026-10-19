#!/usr/bin/env python3
"""Shared create/repair admission. Coverage is an authored claim, not recovered truth."""
import hashlib
import json
import math
from pathlib import Path

def need(ok, message):
    if not ok: raise ValueError(message)

def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def template():
    from reference_set import template as legacy
    p = legacy()
    p.update(version=2, strategy='reuse', task={'mode':'create','intent':'reference_match','goal':'',
        'affected_component_ids':[], 'protected_component_ids':[], 'baseline':None}, calibrations={})
    return p

def validate(spec, plan, stage, base):
    task=plan.get('task',{}); parts=plan.get('critical_components',[])
    need(task.get('mode') in ('create','repair'), 'task mode must be create or repair')
    need(task.get('intent') in ('reference_match','design_change','technical_fix'), 'explicit task intent required')
    need(isinstance(task.get('goal'),str) and task['goal'].strip(), 'task goal required; improvement is not reference acceptance')
    affected=task.get('affected_component_ids'); protected=task.get('protected_component_ids')
    need(isinstance(affected,list) and isinstance(protected,list) and not set(affected)&set(protected), 'affected/protected scope invalid')
    components={c['id'] for c in spec['components']}; refs={r['id']:r for r in spec['references']}
    if task['mode']=='repair':
        baseline=task.get('baseline',{}) or {}
        q=(base/baseline.get('path','')).resolve()
        from workflow import digest
        need(q.is_file() and digest(q)==baseline.get('sha256'), 'repair requires immutable baseline identity')
        need(not Path(baseline['path']).is_absolute() and any(x['path']==baseline['path'] and x['sha256']==baseline['sha256'] for x in spec['source_files']), 'repair baseline must be spec-relative and source-hashed')
        need(affected and set(affected+protected)<=components, 'repair scope must bind actual components')
    covered=set();feature_ids=[]
    for part in parts:
        ids=part.get('component_ids',[]); covered.update(ids)
        need(isinstance(part.get('blocking_unknowns'),list) and not part['blocking_unknowns'], 'critical reference gap: '+part['id'])
        authority=part.get('authority',{})
        need(authority.get('reference_ids') and set(authority['reference_ids'])<=set(refs) and
             isinstance(authority.get('revision'),str) and authority['revision'] and isinstance(authority.get('reason'),str) and authority['reason'],
             'per-region authoritative reference/revision/reason required: '+part['id'])
        entries=part.get('evidence',[])
        for purpose in ('outline','volume','connection'):
            selected=[e for e in entries if e.get('purpose')==purpose]
            need(selected, 'usable region evidence required: '+part['id']+'/'+purpose)
            for e in selected:
                rid=e.get('reference_id'); roi=e.get('roi'); r=refs.get(rid,{})
                need(rid in part['coverage'][purpose], 'region evidence outside declared coverage')
                need(isinstance(roi,list) and len(roi)==4 and all(type(x) in (int,float) and math.isfinite(x) for x in roi), 'finite source-pixel ROI required')
                w,h=r['image_size'];x0,y0,x1,y1=roi
                need(0<=x0<x1<=w and 0<=y0<y1<=h, 'ROI outside reference image')
                need(e.get('usable') is True and e.get('visibility') in ('visible','approved-inference') and
                     all(isinstance(e.get(k),str) and e[k].strip() for k in ('claim','limitation')), 'explicit usable evidence/visibility/claim/limitation required')
                need(e['visibility']!='approved-inference' or r['origin']=='generated', 'inference must use approved generated design reference')
        features=part.get('features',[])
        need(features and len({f.get('id') for f in features})==len(features), 'critical identity features required')
        for f in features:
            feature_ids.append(f.get('id'))
            need(isinstance(f.get('id'),str) and f['id'] and f.get('kind') in ('point','curve','section','connection','smooth_join','visual'), 'unknown shape feature')
            need(f.get('reference_ids') and set(f['reference_ids'])<=set(authority['reference_ids']), 'feature must use authoritative region references')
            need(f.get('component_ids') and set(f['component_ids'])<=set(ids), 'feature must bind its region components')
            need(f.get('criterion') and f.get('severity') in ('critical','supporting'), 'feature criterion/severity required')
            if f['kind']=='visual':
                need(isinstance(f.get('manual_reason'),str) and f['manual_reason'].strip(),'manual visual feature requires an explicit measurement limitation')
                if stage=='spec':need(f.get('review_camera_ids') and set(f['review_camera_ids'])<=set(spec['cameras']),'manual feature needs real review cameras')
            if stage=='spec' and f['kind']!='visual':
                need(f.get('bindings') and all(b.get('component_id') in f['component_ids'] for b in f['bindings']), 'numeric feature needs actual geometry bindings')
                need(all(sum(k in b for k in ('vertex_index','patch_id'))==1 for b in f['bindings']), 'shape bindings require mesh vertices or patch coordinates; free scoring points forbidden')
                need(type(f.get('max_error')) in (int,float) and math.isfinite(f['max_error']) and f['max_error']>0, 'predeclared finite feature tolerance required')
    need(len(set(feature_ids))==len(feature_ids),'feature IDs must be globally unique')
    if task['mode']=='repair':need(set(affected)<=covered, 'critical regions must cover every affected component')
    if stage=='spec':
        from shape_acceptance import camera_identity
        for part in parts:
            for f in part['features']:
                if f['kind'] in ('point','curve') or (f['kind']=='visual' and task['intent']!='technical_fix'):
                    cid=f.get('camera_id'); cal=plan.get('calibrations',{}).get(cid,{})
                    need(cal.get('status')=='locked' and cal.get('reference_id') in f['reference_ids'], 'feature camera must be calibrated and locked: '+str(cid))
                    need(cal.get('identity')==camera_identity(spec,cid,cal), 'camera/anchor/reference changed after lock: '+str(cid))
    return {'task_mode':task['mode'],'intent':task['intent'],'critical_regions':len(parts),'manual_review_required':True,'scope':'authored reference admission; no automatic visual certification'}

def repair_preflight(spec_path, contract):
    from workflow import read, digest
    from reference_set import validate as validate_set
    p=Path(spec_path).resolve();spec=read(p)
    need(spec.get('quality_contract',{}).get('reference_standard')==2,
         'New repairs require common reference admission v2; prepare reference plan before freezing or editing')
    validate_set(p,'spec');plan=read(p.parent/spec['reference_plan']);task=plan['task']
    need(task['mode']=='repair', 'repair task scope must be declared before freezing')
    if task['intent']!='technical_fix':
        import shape_foundation
        need(shape_foundation.enabled(spec),'New shape repairs require foundation-prepare before freezing')
        shape_foundation.contract(spec)
        if spec['foundation']['phase']=='detail':shape_foundation.gate(p)
    need(set(contract.get('editable_components',[]))==set(task['affected_component_ids']), 'repair contract differs from admitted affected scope')
    need({x['id'] for x in contract.get('protected_components',[])}==set(task['protected_component_ids']), 'repair protected scope differs from admission')
    baseline=task['baseline'];raw=read(p.parent/baseline['path'])
    # Admission can add evidence/observations, but may not quietly edit geometry before freeze.
    from scene_build import resolve
    need(identity(resolve({k:raw.get(k) for k in ('components','materials','actions')},raw['parameters']))==
         identity(resolve({k:spec.get(k) for k in ('components','materials','actions')},spec['parameters'])), 'geometry changed before repair admission baseline freeze')
    return {'passed':True,'plan_sha256':digest(p.parent/spec['reference_plan'])}

def validate_rebinding(spec_path,session_path,entry,frozen_hash):
    """Explicit semantic remap after topology change; goals/targets/cameras stay frozen."""
    import copy
    import model_repair
    from workflow import read,digest
    from scene_build import resolve
    p=Path(spec_path).resolve();spec=read(p);f,record,baseline,contract=model_repair._session(session_path)
    need(contract.get('allow_feature_rebinding') is True,'frozen reference admission changed; explicit topology remap authorization required')
    old_path=(Path(record['baseline']['source']).parent/baseline['reference_plan']).resolve()
    item=next((x for x in record['resources']if Path(x['path']).resolve()==old_path),None)
    need(item is not None and item['sha256']==frozen_hash,'frozen admission snapshot missing')
    old=read(f.parent/item['snapshot']);current=read(p.parent/spec['reference_plan'])
    def stripped(plan):
        plan=copy.deepcopy(plan)
        for region in plan['critical_components']:
            for feature in region['features']:feature.pop('bindings',None)
        return plan
    need(identity(stripped(old))==identity(stripped(current)),'frozen reference admission changed beyond geometry bindings')
    need(isinstance(entry,dict) and entry.get('path'),'topology remap review receipt missing')
    def artifact(a):
        need(isinstance(a,dict) and isinstance(a.get('path'),str) and not Path(a['path']).is_absolute(),'remap artifact must be spec-relative')
        need(any(x['path']==a['path'] and x['sha256']==a.get('sha256')for x in spec['source_files']) and digest(p.parent/a['path'])==a.get('sha256'),'remap evidence must be current and source-hashed')
    artifact(entry);review=read(p.parent/entry['path'])
    need(review.get('version')==1 and review.get('baseline_plan_sha256')==frozen_hash and review.get('current_plan_sha256')==digest(p.parent/spec['reference_plan']),'stale topology remap plan identity')
    before={v['id']:v for r in old['critical_components']for v in r['features']};after={v['id']:v for r in current['critical_components']for v in r['features']}
    changes={k for k in before if before[k].get('bindings')!=after[k].get('bindings')}
    rows=review.get('features',[]);need(changes and len(rows)==len(changes) and {r.get('id')for r in rows}==changes,'remap must cover exactly every changed feature binding')
    bc={c['id']:c for c in baseline['components']};cc={c['id']:c for c in spec['components']}
    def topology(c):
        g=c['geometry']
        return identity({'type':g['type'],'count':len(g.get('positions',[])),'indices':g.get('indices',g.get('triangles')),'patches':g.get('network',{}).get('patches')})
    geometry=identity(resolve(spec['components'],spec['parameters']))
    for row in rows:
        k=row['id'];need(before[k]['kind']!='visual' and row.get('old_bindings')==before[k]['bindings'] and row.get('new_bindings')==after[k]['bindings'],'remap old/new semantic feature mismatch')
        need(any(topology(bc[c])!=topology(cc[c])for c in before[k]['component_ids']),'rebinding requires actual topology change; repositioning is not reannotation')
        need(row.get('verdict')=='pass' and row.get('method')=='semantic-review' and row.get('reviewer') and row.get('notes') and row.get('geometry_sha256')==geometry,'explicit current geometry semantic remap review required')
        need(row.get('artifacts'),'semantic remap artifacts required')
        for a in row['artifacts']:artifact(a)
    return {'passed':True,'remapped_features':sorted(changes),'scope':'explicit binding/identity review, no target change or visual certification'}

def prepare(root,mode,intent,goal,affected=None,protected=None):
    """Explicitly migrate an un-attached working project; never grant approvals."""
    import shutil
    from workflow import read,digest,save
    root=Path(root).resolve();p=root/'spec.json';spec=read(p);meta=read(root/'project.json');state=read(root/'state.json')
    need(not meta.get('repair_session') and not state.get('repair_session'), 'Frozen repair already attached; fork a working project before changing reference scope')
    q=root/'reference-plan-v2.json';baseline=root/'reference-baseline-v2.json'
    need(not q.exists() and not baseline.exists(), 'Reference preparation exists; review current draft rather than overwrite')
    need(mode in ('create','repair') and intent in ('reference_match','design_change','technical_fix') and goal.strip(), 'explicit mode/intent/goal required')
    if mode=='repair':shutil.copy2(p,baseline)
    plan=template();plan['task'].update(mode=mode,intent=intent,goal=goal,affected_component_ids=affected or [],protected_component_ids=protected or [],baseline={'path':baseline.name,'sha256':digest(baseline)} if mode=='repair' else None)
    save(q,plan);spec['reference_plan']=q.name;spec['quality_contract']['reference_standard']=2
    spec['source_files'].append({'path':q.name,'sha256':digest(q)})
    if mode=='repair':spec['source_files'].append({'path':baseline.name,'sha256':digest(baseline)})
    if intent!='technical_fix':
        from shape_foundation import template as foundation_template
        spec['quality_contract']['foundation_standard']=1
        spec.setdefault('foundation',foundation_template());meta['foundation_standard']=1;state['foundation_standard']=1
    old_stages=state.get('stages',{});state.update(reference_standard=2,stages={});meta['reference_standard']=2
    meta.setdefault('history',[]).append({'operation':'prepare-common-reference-v2','archived_stages':old_stages,'approvals':'not transferred'})
    save(p,spec);save(root/'project.json',meta);save(root/'state.json',state)
    return {'passed':True,'ready':False,'plan':str(q),'next':'Author coverage/ROI/authority/features, resolve critical gaps, calibrate cameras, then reference-check. No approval granted.'}

def main():
    import argparse
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',required=True);ap.add_argument('--mode',choices=['create','repair'],required=True);ap.add_argument('--intent',choices=['reference_match','design_change','technical_fix'],required=True);ap.add_argument('--goal',required=True);ap.add_argument('--affected',nargs='*');ap.add_argument('--protected',nargs='*');a=ap.parse_args()
    try:print(json.dumps(prepare(a.project,a.mode,a.intent,a.goal,a.affected,a.protected),ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps({'passed':False,'error':str(e)},ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())
