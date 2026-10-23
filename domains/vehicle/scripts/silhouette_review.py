#!/usr/bin/env python3
"""Freeze aligned foreground masks and review projected outlines.
Requires existing Pillow/numpy. Does not infer masks, camera registration or car fidelity.
"""
import argparse,json,hashlib,math
from pathlib import Path
import numpy as np
from PIL import Image

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def write_new(p,v):
    with Path(p).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def mask(path,mode):
    with Image.open(path) as im:
        if mode=='alpha':
            if 'A' not in im.getbands():raise ValueError('Explicit alpha required; opaque RGB is not a foreground mask')
            return np.asarray(im.getchannel('A'))>=128
        if mode=='binary':
            if im.mode!='L':raise ValueError('Binary mask must be grayscale L')
            a=np.asarray(im)
            if not np.isin(a,[0,255]).all():raise ValueError('Binary mask needs explicit 0/255 pixels')
            return a==255
        raise ValueError('Expected alpha or binary mask mode')
def boundary(a):
    inside=np.zeros_like(a);inside[1:-1,1:-1]=a[1:-1,1:-1]&a[1:-1,:-2]&a[1:-1,2:]&a[:-2,1:-1]&a[2:,1:-1]
    return np.argwhere(a&~inside).astype(float)
def nearest(a,b):
    out=[]
    for i in range(0,len(a),64):out.extend(np.sqrt(np.min(np.sum((a[i:i+64,None]-b[None])**2,axis=2),axis=1)).tolist())
    return out
def metrics(reference,candidate):
    if reference.shape!=candidate.shape:raise ValueError('Mask dimensions differ; do not auto-resize/re-register')
    union=int((reference|candidate).sum());intersection=int((reference&candidate).sum())
    if not candidate.any():return {'iou':0.,'boundary_p95_px':None,'candidate_empty':True}
    a,b=boundary(reference),boundary(candidate);dist=nearest(a,b)+nearest(b,a)
    return {'iou':intersection/union,'boundary_p95_px':float(np.percentile(dist,95)),'candidate_empty':False}
def freeze(spec_path,out):
    spec_path,out=Path(spec_path),Path(out);root=spec_path.parent
    if root.resolve()!=out.parent.resolve():raise ValueError('Keep lock beside spec')
    s=json.loads(spec_path.read_text())
    if s.get('schema_version')!=1 or s.get('claim')!='projected_outline' or not s.get('scope') or not s.get('baseline_model'):raise ValueError('Explicit projected-outline scope and baseline required')
    rows=s.get('views',[])
    if not rows or len({r['id'] for r in rows})!=len(rows):raise ValueError('Nonempty unique view IDs required')
    hashes={s['baseline_model']:sha(root/s['baseline_model'])}
    for r in rows:
        if r.get('role') not in ['calibration','validation'] or r.get('origin') not in ['real','generated','inferred','user_supplied'] or not r.get('alignment_evidence') or not r.get('threshold_reason'):raise ValueError('View role, provenance, alignment evidence and threshold reason required')
        low,high,u=r.get('minimum_iou'),r.get('maximum_boundary_p95_px'),r.get('uncertainty_px')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in [low,high,u]) or not 0<low<=1 or not 0<=u<=high:raise ValueError('Finite task thresholds consistent with uncertainty required')
        name=Path(r['candidate_filename'])
        if name.is_absolute() or len(name.parts)!=1:raise ValueError('Candidate filename must be one local filename')
        a,b=mask(root/r['reference'],r['mask_mode']),mask(root/r['baseline'],r['mask_mode'])
        if not a.any() or a.all():raise ValueError('Reference mask must have both foreground and background')
        if a.shape!=b.shape:raise ValueError('Baseline/reference dimensions differ')
        for p in [r['reference'],r['baseline'],r['alignment_evidence']]:hashes[p]=sha(root/p)
    result={'schema_version':1,'spec':s,'spec_sha256':hashlib.sha256(canonical(s)).hexdigest(),'source_hashes':hashes};write_new(out,result);return result
def check(lock_path,candidate_dir,model,render_record,used_for_adjustment=()):
    lock_path=Path(lock_path);root=lock_path.parent;l=json.loads(lock_path.read_text());s=l['spec'];directory=Path(candidate_dir);record=json.loads(Path(render_record).read_text())
    if hashlib.sha256(canonical(s)).hexdigest()!=l['spec_sha256']:raise ValueError('Frozen specification changed')
    for p,h in l['source_hashes'].items():
        if sha(root/p)!=h:raise ValueError('Frozen source changed: '+p)
    if record.get('model_sha256')!=sha(model):raise ValueError('Render record belongs to another model')
    known={r['id'] for r in s['views']}
    if not set(used_for_adjustment)<=known:raise ValueError('Unknown reused view')
    blockers=[];rows=[]
    for r in s['views']:
        p=directory/r['candidate_filename'];v=record.get('views',{}).get(r['id'],{})
        if v.get('sha256')!=sha(p) or v.get('alignment_sha256')!=sha(root/r['alignment_evidence']):raise ValueError('Render file/camera evidence mismatch: '+r['id'])
        reference=mask(root/r['reference'],r['mask_mode']);before=metrics(reference,mask(root/r['baseline'],r['mask_mode']));after=metrics(reference,mask(p,r['mask_mode']));passed=after['iou']>=r['minimum_iou'] and after['boundary_p95_px'] is not None and after['boundary_p95_px']<=r['maximum_boundary_p95_px'];independent=r['role']=='validation' and r['id'] not in used_for_adjustment
        if not passed:blockers.append('Projected outline unpassed: '+r['id'])
        if r['role']=='validation' and not independent:blockers.append('Validation view used for adjustment: '+r['id'])
        rows.append({'view':r['id'],'role':r['role'],'origin':r['origin'],'before':before,'after':after,'within_threshold':passed,'independent':independent})
    independent=[r for r in rows if r['role']=='validation']
    return {'verdict':'needs_revision' if blockers else 'passed','claim':'projected_outline','scope':s['scope'],'blockers':blockers,'measurements':rows,'independent_validation_passed':bool(independent) and all(r['independent'] and r['within_threshold'] for r in independent),'model_sha256':sha(model),'spec_sha256':l['spec_sha256'],'limitations':['Mask overlap is not vehicle similarity or feature/surface fidelity','Alpha/binary masks and registration are supplied evidence, not automatically inferred','Generated benchmark results do not prove real-photo reconstruction','Averages cannot override a failed view; reused views cannot prove independence']}
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True);f=sub.add_parser('freeze');f.add_argument('--spec',required=True);f.add_argument('--out',required=True);c=sub.add_parser('check');c.add_argument('--lock',required=True);c.add_argument('--candidate-dir',required=True);c.add_argument('--model',required=True);c.add_argument('--render-record',required=True);c.add_argument('--used-for-adjustment',action='append',default=[]);c.add_argument('--out',required=True);a=p.parse_args()
    try:
        result=freeze(a.spec,a.out) if a.action=='freeze' else check(a.lock,a.candidate_dir,a.model,a.render_record,a.used_for_adjustment)
        if a.action=='check':write_new(a.out,result)
        print(json.dumps({'verdict':result.get('verdict','frozen'),'blockers':result.get('blockers',[])},ensure_ascii=False));return 2 if result.get('verdict')=='needs_revision' else 0
    except (ValueError,OSError,KeyError,TypeError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':raise SystemExit(main())
