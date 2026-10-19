#!/usr/bin/env python3
"""Coarse-to-fine fitting of actual whole-form parameters. Standard library search."""
import copy,json,argparse
from pathlib import Path
import reconstruction as rec
import scene_build as scene
import shape_foundation as foundation

def fit(spec,iterations=60):
    foundation.contract(spec);foundation.need(foundation.evaluate(spec)['construction_ready'],'fitting requires native regenerable whole-form controls');f=spec['foundation'];groups=f['fit_groups'];foundation.need(groups,'declare coarse-to-fine fit groups')
    rows=list(rec.checked_observations(spec));cal=[o for o in rows if o['role']=='calibration'];val=[o for o in rows if o['role']=='validation']
    foundation.need(len({o['camera_id']for o in cal})>=2 and len(val)>=2,'multi-view calibration and held-out observations required')
    foundation.view_diversity(spec,sorted({o['camera_id']for o in cal}))
    for o in rows:
        b=o.get('binding',o);foundation.need('vertex_index'in b or 'patch_id'in b,'fit observations must bind actual surface geometry')
        foundation.need(type(o.get('tolerance_px'))in (int,float)and o['tolerance_px']>0,'predeclared per-feature fit tolerance required')
    params=[p for g in groups for p in g['parameter_ids']]
    rec.bounds(spec,params);sensitivity=rec.analyze(spec,params)
    foundation.need(not sensitivity['rank_deficient']and not sensitivity['unobserved_parameters'],'whole-form parameters locally unobservable')
    cam_identity=foundation.digest(scene.resolve(spec['cameras'],spec['parameters']))
    initial=scene.prepared(spec)[1];allowed=set(f['primary_components'])
    vertex_components={o['component_id']for o in rows if 'vertex_index'in o.get('binding',o)}
    def topology(nodes):return foundation.digest({cid:{'type':nodes[cid]['geometry']['type'],'count':len(nodes[cid]['geometry'].get('positions',[])),'triangles':nodes[cid]['geometry'].get('triangles',[])}for cid in vertex_components})
    initial_topology=topology(initial)
    changed=True
    while changed:
        before=len(allowed)
        for a,b in f['dependency_edges']:
            if a in allowed:allowed.add(b)
        changed=len(allowed)!=before
    def protected_identity(s):
        _,nodes=scene.prepared(s);result={}
        for cid in set(initial)-allowed:
            c=nodes[cid];chain=[];key=cid
            while key is not None:
                n=nodes[key];chain.append({k:n.get(k)for k in ('id','parent','position','rotation')});key=n.get('parent')
            result[cid]={'node':c,'chain':chain}
        return foundation.digest(result)
    protected=protected_identity(spec)
    def guard(s):
        foundation.need(topology(scene.prepared(s)[1])==initial_topology,'fit changed bound vertex topology; reannotate in a new session')
        foundation.need(foundation.digest(scene.resolve(s['cameras'],s['parameters']))==cam_identity,'fit may not absorb geometry error into camera')
        foundation.need(protected_identity(s)==protected,'fit changed protected actual components')
        foundation.need(foundation.evaluate(s)['numeric_passed'],'whole-form construction constraints failed')
    controls={c['id']:c for c in f['controls']};curve_defs=f.get('fit_curves',[]);curve_ids=set()
    for c in curve_defs:
        foundation.need(c.get('id')and c['id']not in curve_ids and c['id']not in {o['id']for o in rows},'unique curve observation ID required');curve_ids.add(c['id'])
        foundation.need(c.get('control_id')in controls and c.get('role')in ('calibration','validation')and c.get('camera_id')in spec['cameras'],'curve must bind real controls and a camera')
        foundation.need(c.get('reference_id')in controls[c['control_id']]['reference_ids'],'curve authority differs from control')
        target=c.get('target_px');foundation.need(isinstance(target,list)and len(target)>=2 and all(isinstance(v,list)and len(v)==2 and all(type(x)in(int,float)and __import__('math').isfinite(x)for x in v)for v in target),'finite source curve required')
        ref=next(r for r in spec['references']if r['id']==c['reference_id']);w,h=ref['image_size'];foundation.need(all(0<=x<=w and 0<=y<=h for x,y in target),'curve outside source image')
        foundation.need(type(c.get('sigma_px'))in(int,float)and c['sigma_px']>0 and type(c.get('tolerance_px'))in(int,float)and c['tolerance_px']>0,'curve uncertainty and tolerance required')
    def predict(s,role=None):
        out=rec.predictions(s,role);prepared=scene.prepared(s)
        from shape_acceptance import curve_error
        for c in curve_defs:
            if role is not None and c['role']!=role:continue
            world=foundation.points(s,controls[c['control_id']]['bindings'],prepared);cam=scene.resolve(s['cameras'][c['camera_id']],s['parameters']);pixels=[rec.project(p,cam)for p in world]
            error=curve_error(pixels,c['target_px']);out[c['id']]={'error_px':error,'normalized_error':error/c['sigma_px'],'predicted_curve':pixels,'target_curve':c['target_px']}
        return out
    current=copy.deepcopy(spec);reports=[]
    for group in groups:
        r=rec.fit(current,group['parameter_ids'],iterations,candidate_guard=guard,predictor=predict);current=r.pop('spec');reports.append({'level':group['level'],**r})
    # Held-out observations are reported after search, not used to choose a candidate.
    final=predict(current);limits={o['id']:o['tolerance_px']for o in rows+curve_defs}
    passed=foundation.evaluate(current)['numeric_passed']and all(x['error_px']<=limits[k]for k,x in final.items())
    return {'spec':current,'input_identity':foundation.geometry_identity(spec),'final_identity':foundation.geometry_identity(current),'numeric_passed':passed,'visual_pass':False,'groups':reports,'observations':final,'observability':sensitivity,'stopping_reason':'numeric criteria met; visual review still required'if passed else 'needs diagnosis of correspondence, camera, constraints or representation; do not enter detail','scope':'bounded coordinate search on actual native geometry; no global optimum or physical truth guarantee'}

def main():
    a=argparse.ArgumentParser();a.add_argument('--spec',required=True);a.add_argument('--out',required=True);a.add_argument('--iterations',type=int,default=60);x=a.parse_args()
    try:
        r=fit(foundation.read(x.spec),x.iterations);r['input_spec_sha256']=foundation.sha(x.spec);r['input_file_sha256']=foundation.sha(x.spec);r['diagnostic']=True
        with Path(x.out).open('x')as f:json.dump(r,f,indent=2)
        print(json.dumps({'numeric_passed':r['numeric_passed'],'visual_pass':False,'report':x.out}));return 0 if r['numeric_passed']else 1
    except (ValueError,KeyError,TypeError,OSError)as e:print(json.dumps({'error':str(e)}));return 2
if __name__=='__main__':raise SystemExit(main())
