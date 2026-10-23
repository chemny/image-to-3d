#!/usr/bin/env python3
"""Strict evidence wrapper around fidelity_loop. Does not judge pixels or edit meshes."""
import argparse, hashlib, json
from pathlib import Path
from fidelity_loop import decide

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def write(p,obj):
    with p.open('x') as f: json.dump(obj,f,ensure_ascii=False,indent=2); f.write('\n')
def verify(base,ref):
    p=(base/ref['path']).resolve()
    if not p.is_file() or sha(p)!=ref['sha256']: raise ValueError('missing or changed evidence: '+str(p))
    return p

def seal(plan_path,lock_path):
    plan=read(plan_path);base=plan_path.parent
    views=plan['required_views']; features=plan['required_features']
    if len(views)!=len(set(views)) or len(features)!=len(set(features)) or not views or not features: raise ValueError('empty or duplicate coverage')
    ids={s['id'] for s in plan['checks']}
    required={f'{v}.{kind}' for v in views for kind in ('silhouette','landmark','visual')}
    required|={f'feature.{f}' for f in features}|{'protection','functional'}
    if not required<=ids: raise ValueError('missing required checks: '+','.join(sorted(required-ids)))
    expected={f'{v}.{k}':k for v in views for k in ('silhouette','landmark','visual')}
    expected.update({f'feature.{f}':'visual' for f in features});expected.update(protection='protection',functional='functional')
    if len(ids)!=len(plan['checks']):raise ValueError('duplicate check ids')
    for spec in plan['checks']:
        if spec['id'] in expected and spec['kind']!=expected[spec['id']]:raise ValueError('incorrect check kind: '+spec['id'])
    for ref in plan['references']: verify(base,ref)
    lock={'schema':1,'plan':{'path':str(plan_path.resolve()),'sha256':sha(plan_path)},'required_views':views,'required_features':features}
    write(lock_path,lock);return lock

def check(lock_path,record_path):
    lock=read(lock_path);plan_path=verify(lock_path.parent,lock['plan']);plan=read(plan_path);base=plan_path.parent;r=read(record_path)
    # Existing decision engine enforces immutable history, regression and stagnation.
    decision=decide(plan_path,r)
    pending=[];capture=r.get('capture')
    if not capture: pending.append('capture_manifest')
    else:
        m=read(verify(base,capture))
        if m.get('model')!=r['model']: raise ValueError('capture/model identity mismatch')
        if m.get('plan_sha256')!=sha(plan_path): raise ValueError('capture/plan identity mismatch')
        for asset in m['inputs']:verify(base,asset)
        if not m.get('live_inputs'):raise ValueError('capture omits live asset bindings')
        for asset in m['live_inputs']:verify(base,asset)
        if r['model'] not in m['inputs']:raise ValueError('capture inputs omit current model')
        files=m.get('outputs',{})
        for v in lock['required_views']:
            for kind in ('render','gray','difference','alignment'):
                key=v+'.'+kind
                if key not in files:pending.append(key)
            align=files.get(v+'.alignment')
            if align:
                a=read(verify(base,align))
                if a.get('status')!='validated':pending.append(v+'.validated_alignment')
                if not isinstance(a.get('independent_validation'),dict):pending.append(v+'.independent_alignment_evidence')
                else:verify(base,a['independent_validation'])
        for f in lock['required_features']:
            if 'feature.'+f not in files:pending.append('feature.'+f+'.evidence')
        for ref in files.values():verify(base,ref)
        captured={(x['path'],x['sha256']) for x in files.values()}
        for key,entry in r.get('checks',{}).items():
            for evidence in entry.get('evidence',[]):
                if (evidence['path'],evidence['sha256']) not in captured:
                    raise ValueError('measurement evidence not bound to capture: '+key)
    if pending and decision['action']!='blocked':
        decision.update(action='calibrate',deliverable=False)
        decision['reasons']=sorted(set(decision['reasons']+pending))
    action=decision['action']
    decision['may_deliver']=action=='passed'
    decision['may_end_as_complete']=action=='passed'
    decision['next_step']={'passed':'deliver_verified_bundle','calibrate':'complete_alignment_and_evidence_then_recheck','repair':'repair_failed_features_then_capture_and_recheck','rollback':'restore_best_checkpoint_then_capture_and_recheck','change_method':'change_geometry_method_without_resetting_plan_or_budget','blocked':'report_specific_blocker_and_preserve_best_candidate'}[action]
    decision['execution']='evidence_gate_only_not_automatic_mesh_repair'
    return decision

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['seal','check','authorize-delivery']);ap.add_argument('--plan',type=Path);ap.add_argument('--lock',required=True,type=Path);ap.add_argument('--record',type=Path);ap.add_argument('--out',type=Path);a=ap.parse_args()
    try:
        if a.action=='seal': result=seal(a.plan,a.lock);code=0
        else:
            result=check(a.lock,a.record);code=0 if result['may_deliver'] else 2
            # No certificate is issued for calibrate/repair/rollback/change_method.
            if a.action=='authorize-delivery':
                if code: result['certificate_issued']=False
                else:result['certificate_issued']=True;result['record_sha256']=sha(a.record)
            if a.out:write(a.out,result)
    except (ValueError,KeyError,TypeError,OSError) as e:
        result={'action':'repair_evidence','may_deliver':False,'may_end_as_complete':False,'next_step':'restore_or_recapture_matching_evidence','reasons':[str(e)]};code=2
        if a.out and not a.out.exists():write(a.out,result)
    print(json.dumps(result,ensure_ascii=False,indent=2));return code
if __name__=='__main__':raise SystemExit(main())
