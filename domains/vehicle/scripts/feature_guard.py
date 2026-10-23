#!/usr/bin/env python3
"""Freeze vertex-domain constraints and audit topology-preserving GLB edits.
Requires existing numpy. Selectors/feature identity are explicit task evidence,
not automatic segmentation. Local positions are compared with unchanged nodes.
"""
import argparse,hashlib,json,math,re
from pathlib import Path
import numpy as np
from asset_manifest import read_glb,sha256

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def write_new(p,v):
    with Path(p).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
class Asset:
    def __init__(self,p):self.j,self.b=read_glb(p)
    def arr(self,i):
        a=self.j['accessors'][i]
        if a.get('sparse') or a.get('normalized'):raise ValueError('Sparse/normalized attributes need an explicit adapter')
        view=self.j['bufferViews'][a['bufferView']]
        if view.get('buffer',0)!=0:raise ValueError('Multiple buffers need adaptation')
        dtype=np.dtype({5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]);width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];stride=view.get('byteStride',dtype.itemsize*width)
        if stride<dtype.itemsize*width:raise ValueError('Invalid stride')
        return np.ndarray((a['count'],width),dtype=dtype,buffer=self.b,offset=view.get('byteOffset',0)+a.get('byteOffset',0),strides=(stride,dtype.itemsize)).copy()
    def primitives(self):
        return {f'n{i}:p{k}':p for i,n in enumerate(self.j['nodes']) if 'mesh' in n for k,p in enumerate(self.j['meshes'][n['mesh']]['primitives'])}
    def image_hashes(self):
        return [hashlib.sha256(self.b[(v:=self.j['bufferViews'][im['bufferView']]).get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]).hexdigest() if 'bufferView' in im else im.get('uri') for im in self.j.get('images',[])]
def indices(values,count):
    if not isinstance(values,list) or not values or any(type(i)!=int or i<0 or i>=count for i in values) or len(set(values))!=len(values):raise ValueError('Nonempty distinct in-range vertex indices required')
    return values
def freeze(baseline,spec_path,out):
    spec_path=Path(spec_path);out=Path(out)
    if spec_path.parent.resolve()!=out.parent.resolve():raise ValueError('Keep lock beside spec')
    spec=json.loads(spec_path.read_text());a=Asset(baseline);pr=a.primitives()
    if spec.get('schema_version')!=1 or spec.get('baseline_sha256')!=sha256(baseline) or not spec.get('evidence'):raise ValueError('Version, current source identity and feature evidence required')
    if not spec.get('allowed_changes'):raise ValueError('Explicit allowed bindings required')
    for id,c in spec['allowed_changes'].items():
        if id not in pr or type(c.get('max_displacement')) not in (int,float) or not math.isfinite(c['max_displacement']) or c['max_displacement']<0:raise ValueError('Unknown allowed binding or invalid displacement')
        if c.get('indices') is not None:indices(c['indices'],len(a.arr(pr[id]['attributes']['POSITION'])))
    features=spec.get('fixed_regions',[])
    if len({f['id'] for f in features})!=len(features):raise ValueError('Unique fixed feature IDs required')
    for f in features:
        if f['binding'] not in pr or not f.get('evidence'):raise ValueError('Feature binding and identification evidence required')
        indices(f['indices'],len(a.arr(pr[f['binding']]['attributes']['POSITION'])))
        if type(f.get('tolerance',0)) not in (int,float) or not math.isfinite(f.get('tolerance',0)) or f.get('tolerance',0)<0:raise ValueError('Finite nonnegative tolerance required')
    for r in spec.get('clearances',[]):
        if r['moving_binding'] not in pr or r['fixed_region'] not in {f['id'] for f in features}:raise ValueError('Unknown clearance relation')
        if not r.get('evidence') or type(r.get('minimum')) not in (int,float) or not math.isfinite(r['minimum']) or r['minimum']<0 or not r.get('axes') or any(type(x)!=int or x not in [0,1,2] for x in r['axes']):raise ValueError('Explicit measured relation required')
    for r in spec.get('centroid_relations',[]):
        if r['a'] not in pr or r['b'] not in pr or not r.get('axes') or any(x not in [0,1,2] for x in r['axes']) or type(r.get('maximum')) not in (int,float) or not math.isfinite(r['maximum']) or r['maximum']<0:raise ValueError('Invalid centroid relation')
    path=str(Path(baseline).resolve());lock={'schema_version':1,'baseline':path,'baseline_sha256':sha256(baseline),'spec':spec,'spec_sha256':hashlib.sha256(canonical(spec)).hexdigest()};write_new(out,lock);return lock
def check(lock_path,candidate):
    lock=json.loads(Path(lock_path).read_text());spec=lock['spec']
    if hashlib.sha256(canonical(spec)).hexdigest()!=lock['spec_sha256'] or sha256(lock['baseline'])!=lock['baseline_sha256']:raise ValueError('Frozen source/constraints changed')
    a,b=Asset(lock['baseline']),Asset(candidate);pa,pb=a.primitives(),b.primitives();fail=[];measure=[]
    if a.j['nodes']!=b.j['nodes']:raise ValueError('Node transforms/indices changed; this guard needs identical binding layout')
    if set(pa)!=set(pb):raise ValueError('Binding layout changed; use remapped/rebuild review')
    for key in ['materials','textures','samplers','animations','skins']:
        if a.j.get(key)!=b.j.get(key):fail.append('Protected definitions changed: '+key)
    if a.image_hashes()!=b.image_hashes():fail.append('Images changed')
    positions={};changed=0
    for id,p in pa.items():
        q=pb[id];attr=p['attributes'];other=q['attributes']
        if p.get('material')!=q.get('material') or p.get('mode',4)!=q.get('mode',4) or set(attr)!=set(other):raise ValueError('Primitive layout changed: '+id)
        ia=a.arr(p['indices']) if 'indices' in p else None;ib=b.arr(q['indices']) if 'indices' in q else None
        if not np.array_equal(ia,ib):fail.append('Topology changed: '+id)
        x,y=a.arr(attr['POSITION']),b.arr(other['POSITION'])
        if x.shape!=y.shape:raise ValueError('Vertex identity lost: '+id)
        if not np.isfinite(y).all():raise ValueError('Nonfinite geometry')
        positions[id]=y;d=np.linalg.norm(y.astype(float)-x,axis=1);allowed=spec['allowed_changes'].get(id);changed+=int((d>0).sum())
        if not allowed and d.max()>0:fail.append('Non-target positions changed: '+id)
        if allowed:
            if d.max()>allowed['max_displacement']:fail.append('Displacement exceeded: '+id)
            if allowed.get('indices') is not None:
                mask=np.ones(len(d),bool);mask[allowed['indices']]=False
                if (d[mask]>0).any():fail.append('Outside allowed domain changed: '+id)
        for key,index in attr.items():
            v,w=a.arr(index),b.arr(other[key])
            if key!='POSITION' and (key!='NORMAL' or not allowed) and not np.array_equal(v,w):fail.append('Protected attribute changed: '+id+'/'+key)
            if key=='NORMAL' and allowed and allowed.get('indices') is not None:
                if not np.array_equal(v[mask],w[mask]):fail.append('Outside allowed normal domain changed: '+id)
            if key=='NORMAL' and (not np.isfinite(w).all() or np.max(abs(np.linalg.norm(w,axis=1)-1))>1e-4):fail.append('Invalid unit normals: '+id)
    regions={}
    for f in spec.get('fixed_regions',[]):
        id=f['binding'];ix=f['indices'];old=a.arr(pa[id]['attributes']['POSITION'])[ix];new=positions[id][ix];d=float(np.linalg.norm(new-old,axis=1).max());regions[f['id']]=new
        measure.append({'feature':f['id'],'max_displacement':d,'vertices':len(ix)})
        if d>f.get('tolerance',0):fail.append('Fixed feature moved: '+f['id'])
        if 'NORMAL' in pa[id]['attributes']:
            old_n=a.arr(pa[id]['attributes']['NORMAL'])[ix];new_n=b.arr(pb[id]['attributes']['NORMAL'])[ix]
            if not np.array_equal(old_n,new_n):fail.append('Fixed feature normals changed: '+f['id'])
    for r in spec.get('clearances',[]):
        x=positions[r['moving_binding']][:,r['axes']];y=regions[r['fixed_region']][:,r['axes']];distance=float('inf')
        for start in range(0,len(x),128):distance=min(distance,float(np.linalg.norm(x[start:start+128,None]-y[None],axis=2).min()))
        measure.append({'relation':r['id'],'sampled_vertex_clearance':distance,'minimum':r['minimum']})
        if distance<r['minimum']:fail.append('Feature clearance violated: '+r['id'])
    for r in spec.get('centroid_relations',[]):
        distance=float(np.linalg.norm((positions[r['a']].mean(0)-positions[r['b']].mean(0))[r['axes']]))
        measure.append({'relation':r['id'],'centroid_distance':distance,'maximum':r['maximum']})
        if distance>r['maximum']:fail.append('Assembly relation violated: '+r['id'])
    return {'verdict':'needs_revision' if fail else 'passed','blockers':fail,'measurements':measure,'candidate_sha256':sha256(candidate),'spec_sha256':lock['spec_sha256'],'changed_vertex_instances':changed,'limitations':['Local attributes with unchanged node transforms only','Manual vertex identity/regions are not automatic semantic recognition','Sampled vertex clearance is not surface intersection proof','Separate visual and reference-fidelity review required']}
def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True);f=s.add_parser('freeze');f.add_argument('--baseline',required=True);f.add_argument('--spec',required=True);f.add_argument('--out',required=True);c=s.add_parser('check');c.add_argument('--lock',required=True);c.add_argument('--candidate',required=True);c.add_argument('--out',required=True);args=p.parse_args()
    try:
        result=freeze(args.baseline,args.spec,args.out) if args.action=='freeze' else check(args.lock,args.candidate)
        if args.action=='check':write_new(args.out,result)
        print(json.dumps({'verdict':result.get('verdict','frozen'),'blockers':result.get('blockers',[])},ensure_ascii=False));return 2 if result.get('verdict')=='needs_revision' else 0
    except (ValueError,KeyError,OSError,TypeError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':raise SystemExit(main())
