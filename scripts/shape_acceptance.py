#!/usr/bin/env python3
"""Locked-camera, actual-geometry feature checks. Numeric constraints never certify beauty."""
import argparse
import copy
import json
import math
from pathlib import Path
import scene_build as scene
from reference_admission import need, identity
from reconstruction import project

def camera_identity(spec,cid,cal):
    if cal.get('method')=='geometry-curves':
        curves=cal.get('geometry_curves',[])
        need(curves and all(c.get('camera_id')==cid for c in curves),'camera curve scope missing/mismatched')
        prepared=scene.prepared(spec);nodes=prepared[1];edge_cache={}
        for c in curves:
            bindings=c['bindings'];pairs=list(zip(bindings,bindings[1:]))+([(bindings[-1],bindings[0])] if c['closed'] else [])
            for a,b in pairs:
                key=a['component_id'];need(key==b['component_id'],'calibrated curve no longer follows one mesh edge')
                if key not in edge_cache:
                    g=nodes[key]['geometry'];need(g['type']=='mesh','calibrated curve must remain an actual mesh')
                    tri=g['triangles'];edge_cache[key]={tuple(sorted(pair)) for i in range(0,len(tri),3) for pair in ((tri[i],tri[i+1]),(tri[i+1],tri[i+2]),(tri[i+2],tri[i]))}
                need(tuple(sorted((a['vertex_index'],b['vertex_index']))) in edge_cache[key],'calibrated curve triangle edge removed; lock invalid')
        world={c['id']:points(spec,c['bindings'],prepared) for c in curves}
        refs={r['id']:r['sha256'] for r in spec['references'] if r['id'] in {c['reference_id'] for c in curves}}
        return identity({'camera':scene.resolve(spec['cameras'][cid],spec['parameters']),
            'curves':curves,'world':world,'references':refs,
            'limits':{k:cal.get(k) for k in ('method','rationale','uncertainty','max_error_px','initialization_contract_sha256')}})
    ids=cal.get('calibration_ids',[])+cal.get('validation_ids',[])
    observations=[o for o in spec['observations'] if o['id'] in ids]
    bindings=[dict(o.get('binding',o),component_id=o['component_id']) for o in observations]
    # A camera lock belongs to the actual anchor geometry, including ancestors.
    # Keeping vertex IDs while moving their mesh must invalidate the lock.
    world=points(spec,bindings)
    refs={r['id']:r['sha256'] for r in spec['references'] if r['id']==cal.get('reference_id')}
    return identity({'camera':scene.resolve(spec['cameras'][cid],spec['parameters']), 'anchors':observations, 'anchor_world':world, 'references':refs,
        'limits':{k:cal.get(k) for k in ('max_error_px','uncertainty','method','rationale','calibration_ids','validation_ids')}})

def lock_curves(spec,plan,cid,contract,fit_report,resource_root):
    """Reverify a numeric coarse baseline, then lock only its declared edge scope."""
    from coarse_baseline import verify
    from coarse_initialization import digest
    result=verify(spec,contract,fit_report,resource_root)
    need(result['passed'],'coarse baseline verification failed: '+', '.join(result['errors']))
    need(cid in spec['cameras'] and cid in plan.get('calibrations',{}),'camera calibration draft required')
    cal=plan['calibrations'][cid]
    need(cal.get('method')=='geometry-curves','geometry-curves method required')
    need(all(isinstance(cal.get(k),str) and cal[k].strip() for k in ('rationale','uncertainty','reviewer')),'camera curve rationale/uncertainty/reviewer required')
    curves=[copy.deepcopy(c) for c in contract['curves'] if c['camera_id']==cid]
    need(curves and {c['reference_id'] for c in curves}=={cal.get('reference_id')},'camera curve reference mismatch')
    need(all(c['max_error_px']==cal.get('max_error_px') for c in curves),'camera curve tolerance mismatch')
    cal.update(geometry_curves=curves,initialization_contract_sha256=digest(contract))
    cal.update(status='locked',identity=camera_identity(spec,cid,cal))
    return {'passed':True,'camera_id':cid,'scope':'verified traced actual edges only; not full shape or visual acceptance','reference_match_passed':False}

def points(spec,bindings,prepared=None):
    # Resolve the component tree once per batch, not once for every sampled vertex.
    resolved,nodes=prepared or scene.prepared(spec);out=[]
    for b in bindings:
        c=nodes[b['component_id']];g=c['geometry']
        if 'vertex_index' in b:
            need(g['type']=='mesh','vertex binding requires mesh');i=b['vertex_index'];p=g['positions']
            need(type(i)==int and 0<=i<len(p)//3,'invalid feature vertex');v=p[3*i:3*i+3]
        elif 'patch_id' in b:
            net=g['network'];patch=next(x for x in net['patches'] if x['id']==b['patch_id']);uv=scene.vector(b['uv'],2)
            need(all(0<=x<=1 for x in uv),'invalid feature UV')
            grid=[[net['control_points'][k]['position'] for k in row] for row in patch['control_points']];v=scene.evaluate(grid,*uv)[0]
        else:raise ValueError('feature must bind actual mesh or patch geometry')
        key=c['id']
        while key is not None:
            c=nodes[key];v=[a+d for a,d in zip(scene.rotate(v,c.get('rotation',[0,0,0])),c.get('position',[0,0,0]))];key=c.get('parent')
        out.append(v)
    return out

def lock(spec,plan,cid):
    # A successful projection cannot validate orphaned/non-renderable anchors.
    scene.build(spec)
    need(cid in spec['cameras'],'unknown camera')
    need(cid in plan.get('calibrations',{}),'camera calibration draft missing: '+str(cid)+'; declare reference, dispersed calibration/held-out anchors, tolerance and uncertainty before locking')
    cal=plan['calibrations'][cid]
    need(all(isinstance(cal.get(k),str) and cal[k].strip() for k in ('method','rationale','uncertainty','reviewer')), 'camera calibration rationale/uncertainty/reviewer required')
    need(cal['method'] in ('landmarks','known-camera'), 'unsupported calibration method')
    need(type(cal.get('max_error_px')) in (int,float) and math.isfinite(cal['max_error_px']) and cal['max_error_px']>0,'camera tolerance required')
    ref=next(r for r in spec['references'] if r['id']==cal['reference_id']);camera=scene.resolve(spec['cameras'][cid],spec['parameters'])
    need([camera['width'],camera['height']]==ref['image_size'],'camera must match reference resolution')
    obs={o['id']:o for o in spec['observations']};a=cal.get('calibration_ids',[]);b=cal.get('validation_ids',[])
    need(len(a)>=4 and len(b)>=2 and len(set(a+b))==len(a+b), 'camera requires distinct calibration and held-out anchors (at least 4 + 2)')
    selected=[obs[i] for i in a+b]
    need(all(o['camera_id']==cid and o['reference_id']==ref['id'] for o in selected),'camera anchors must use matching reference/view')
    need(all(obs[i]['role']=='calibration' for i in a) and all(obs[i]['role']=='validation' for i in b),'held-out anchor role changed')
    xy=[o['target'] for o in selected]
    need(all(max(v[j] for v in xy)-min(v[j] for v in xy)>=.15*ref['image_size'][j] for j in (0,1)), 'camera anchors are too concentrated')
    bindings=[dict(o.get('binding',o),component_id=o['component_id']) for o in selected]
    world=points(spec,bindings);errors=[math.dist(project(v,camera),o['target']) for v,o in zip(world,selected)]
    need(all(e<=cal['max_error_px'] for e in errors),'camera calibration or held-out error exceeds declared tolerance')
    cal.update(status='locked',identity=camera_identity(spec,cid,cal),errors_px=dict(zip(a+b,errors)))
    return {'passed':True,'camera_id':cid,'max_error_px':max(errors),'scope':'declared correspondences; reviewer must confirm semantic reliability and non-degenerate anchor layout'}

def segment_distance(p,a,b):
    d=[y-x for x,y in zip(a,b)];den=sum(x*x for x in d);t=0 if den==0 else max(0,min(1,sum((x-y)*z for x,y,z in zip(p,a,d))/den))
    return math.dist(p,[x+t*y for x,y in zip(a,d)])

def curve_error(a,b):
    need(len(a)>=2 and len(b)>=2,'curve requires at least two samples')
    # Densify both polylines: sparse endpoints cannot hide a bowed or absent middle.
    def dense(poly):
        out=[]
        for x,y in zip(poly,poly[1:]):
            count=max(32,min(1000,math.ceil(math.dist(x,y)/2)))
            out.extend([[v+(w-v)*i/count for v,w in zip(x,y)] for i in range(count)])
        return out+[poly[-1]]
    def directed(x,y):return max(min(segment_distance(p,u,v) for u,v in zip(y,y[1:])) for p in dense(x))
    return max(directed(a,b),directed(b,a))

def fit_camera(spec,plan,cid,parameter_ids,iterations=80):
    """Camera-only coordinate fit: build geometry once, never optimize held-out targets."""
    from reconstruction import bounds,matrix_rank
    bounds(spec,parameter_ids);need(type(iterations)==int and iterations>0,'positive fit iterations required')
    need(cid in spec['cameras'] and cid in plan.get('calibrations',{}),'camera calibration draft required before fit')
    selected=set(parameter_ids)
    def links(value):
        if isinstance(value,dict):return ({value['param']}if 'param'in value else set()).union(*(links(v)for v in value.values()))
        if isinstance(value,list):return set().union(*(links(v)for v in value))
        return set()
    need(not selected & links({k:spec.get(k)for k in ('components','materials','actions','connections')}),'camera fit parameters must not alter geometry/materials/actions')
    need(not any(selected & links(c)for key,c in spec['cameras'].items()if key!=cid),'camera fit cannot change other views; use separate camera parameters')
    cal=plan['calibrations'][cid];obs={o['id']:o for o in spec['observations']};a=cal.get('calibration_ids',[]);b=cal.get('validation_ids',[])
    need(len(a)>=4 and len(b)>=2 and len(set(a+b))==len(a+b),'camera fit requires distinct calibration and held-out anchor sets')
    rows=[obs[k]for k in a+b]
    need(all(o['camera_id']==cid and o['reference_id']==cal['reference_id'] for o in rows),'camera fit anchors must use matching reference/view')
    need(all(obs[i]['role']=='calibration'for i in a)and all(obs[i]['role']=='validation'for i in b),'camera fit anchor roles inconsistent')
    need(selected<=set().union(*(set(obs[i].get('parameter_ids',[]))for i in a)),'camera parameter has no calibration observation binding')
    need(all(type(o.get('sigma_px'))in(int,float)and math.isfinite(o['sigma_px'])and o['sigma_px']>0 for o in rows),'positive fit uncertainty required')
    scene.build(spec);world=points(spec,[dict(o.get('binding',o),component_id=o['component_id'])for o in rows]);anchors=dict(zip(a+b,world));parameters=copy.deepcopy(spec['parameters'])
    def projections(params,ids):
        camera=scene.resolve(spec['cameras'][cid],params)
        return {k:project(anchors[k],camera)for k in ids}
    base=projections(parameters,a);columns=[]
    for name in parameter_ids:
        p=parameters[name];span=p['max']-p['min'];delta=max(span*1e-4,1e-7);other=copy.deepcopy(parameters)
        value=min(p['max'],p['value']+delta)
        if value==p['value']:value=max(p['min'],p['value']-delta)
        need(value!=p['value'],'camera parameter has no fitting range: '+name);other[name]['value']=value;projected=projections(other,a)
        columns.append([(projected[k][j]-base[k][j])*span/(value-p['value'])/obs[k]['sigma_px']for k in a for j in (0,1)])
    rank=matrix_rank(list(zip(*columns)));need(rank==len(parameter_ids),'camera parameters are locally unobservable; change anchors or reduce degrees of freedom')
    def score(params):
        values=projections(params,a)
        return sum((math.dist(values[k],obs[k]['target'])/obs[k]['sigma_px'])**2 for k in a)/len(a)
    initial=current=score(parameters);steps={k:(parameters[k]['max']-parameters[k]['min'])/8 for k in parameter_ids};evaluations=1
    for _ in range(iterations):
        improved=False
        for name in parameter_ids:
            for direction in (-1,1):
                proposed=copy.deepcopy(parameters);p=proposed[name];value=max(p['min'],min(p['max'],p['value']+steps[name]*direction))
                if value==p['value']:continue
                p['value']=value;evaluations+=1
                try:objective=score(proposed)
                except ValueError:continue
                if objective<current-1e-12:parameters,current=proposed,objective;improved=True
        if not improved:steps={k:v/2 for k,v in steps.items()}
        if max(steps.values())<1e-8:break
    # Held-out targets are accessed only after all candidate search/selection.
    projected=projections(parameters,a+b)
    errors={k:math.dist(projected[k],obs[k]['target'])for k in a+b}
    candidate=copy.deepcopy(spec);candidate['parameters']=parameters
    return {'fit_complete':True,'spec':candidate,'parameter_values':{k:parameters[k]['value']for k in parameter_ids},'initial_objective':initial,'final_objective':current,'errors_px':errors,'jacobian_rank':rank,'evaluations':evaluations,'geometry_builds':1,'reference_match_passed':False,'scope':'camera-only bounded calibration; inspect held-out residuals and semantic reliability before locking'}

def evaluate(spec,plan):
    rows=[];pending=[];prepared=scene.prepared(spec)
    features=[f for r in plan['critical_components'] for f in r['features']]
    need(len({f['id'] for f in features})==len(features),'feature IDs must be globally unique')
    for f in features:
        if f['kind']=='visual':pending.append(f['id']);continue
        actual=points(spec,f['bindings'],prepared);kind=f['kind']
        if kind in ('point','curve'):
            cid=f['camera_id'];cal=plan['calibrations'][cid]
            need(cal.get('status')=='locked' and cal.get('identity')==camera_identity(spec,cid,cal),'stale/unlocked camera')
            camera=scene.resolve(spec['cameras'][cid],spec['parameters']);actual=[project(p,camera) for p in actual];dim=2;units='px'
        else:dim=3;units='m'
        extra={}
        if kind=='smooth_join':
            from reconstruction import cross,sub,unit,dot
            need(len(actual)==6,'smooth join requires two actual adjacent surface sample triangles')
            n1=unit(cross(sub(actual[1],actual[0]),sub(actual[2],actual[0])));n2=unit(cross(sub(actual[4],actual[3]),sub(actual[5],actual[3])))
            error=math.degrees(math.acos(max(-1,min(1,dot(n1,n2)))));units='degrees'
            max_gap=f.get('max_gap');need(type(max_gap) in (int,float) and math.isfinite(max_gap) and max_gap>0,'smooth join requires separate positive positional gap tolerance')
            extra={'gap':math.dist(actual[0],actual[3]),'max_gap':max_gap}
        elif kind=='connection':
            need(len(actual)==2,'connection requires two bound points');error=math.dist(*actual)
        else:
            target=f.get('target');need(isinstance(target,list) and target and all(isinstance(p,list) and len(p)==dim and all(type(v) in (int,float) and math.isfinite(v) for v in p) for p in target),'finite target coordinates required')
            if kind in ('curve','section'):error=curve_error(actual,target)
            else:
                need(len(actual)==len(target),'point target/binding count mismatch');error=max(math.dist(a,b) for a,b in zip(actual,target))
        tolerance=f['max_error'];need(type(tolerance) in (int,float) and math.isfinite(tolerance) and tolerance>0,'invalid feature tolerance')
        rows.append({'id':f['id'],'kind':kind,'error':error,'units':units,'tolerance':tolerance,'passed':error<=tolerance and extra.get('gap',0)<=extra.get('max_gap',0),'severity':f['severity'],**extra})
    return {'numeric_passed':all(r['passed'] for r in rows),'reference_match_passed':False,'features':rows,'visual_pending':pending,
        'scope':'declared geometric constraints only; no global average, no automatic visual adoption'}

def validate_review(spec_path,spec,plan,evidence,epath):
    report=evaluate(spec,plan);need(report['numeric_passed'],'reference shape constraints failed: '+', '.join(r['id'] for r in report['features'] if not r['passed']))
    review=evidence.get('shape_review',{});need(review.get('intent')==plan['task']['intent'],'shape review intent differs from admitted goal')
    need(review.get('technical_verdict')=='pass','separate technical acceptance required')
    need(review.get('reference_verdict')=='pass','reference acceptance required; local improvement cannot substitute')
    receipt=review.get('capture_receipt');need(isinstance(receipt,str),'shape review requires current actual capture receipt')
    artifacts={a['path']:a['sha256'] for a in evidence.get('artifacts',[])};need(receipt in artifacts,'capture receipt must be hashed review artifact')
    # Use the existing browser/spec/resource verification, including exact current candidate identity.
    from repair_capture import validate_receipt
    captured=validate_receipt(Path(epath).parent/receipt, spec_path)['views']
    rows={r['id']:r for r in review.get('features',[])}
    for region in plan['critical_components']:
        for f in region['features']:
            r=rows.get(f['id'],{});need(r.get('verdict')=='pass' and isinstance(r.get('notes'),str) and r['notes'].strip(),'per-feature shape review missing: '+f['id'])
            need(r.get('camera_ids') and all(c in captured for c in r['camera_ids']),'feature review lacks matching current captured views')
            need(f.get('camera_id') is None or f['camera_id'] in r['camera_ids'],'feature must include its reference-matched captured camera')
            need(set(f.get('review_camera_ids',[]))<=set(r['camera_ids']),'manual feature omitted required context/depth camera')
            need(set(r.get('reference_ids',[]))==set(f['reference_ids']),'feature review must compare authoritative references')
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['check','lock-camera','lock-curves','fit-camera']);ap.add_argument('--spec',required=True);ap.add_argument('--camera');ap.add_argument('--out');ap.add_argument('--parameters',nargs='+');ap.add_argument('--iterations',type=int,default=80);ap.add_argument('--contract');ap.add_argument('--fit-report');ap.add_argument('--resource-root');a=ap.parse_args()
    try:
        p=Path(a.spec).resolve();spec=json.loads(p.read_text());q=p.parent/spec['reference_plan'];plan=json.loads(q.read_text())
        need(plan.get('version')==2,'reference admission v2 required')
        if a.command=='fit-camera':
            need(a.out and not Path(a.out).exists(),'camera fit requires new --out report')
            result=fit_camera(spec,plan,a.camera,a.parameters,a.iterations)
            from workflow import digest
            result['input_file_sha256']=digest(p);Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({k:v for k,v in result.items()if k!='spec'},ensure_ascii=False,indent=2));return 0
        elif a.command in ('lock-camera','lock-curves'):
            if a.command=='lock-curves':
                need(a.contract and a.fit_report and a.resource_root,'curve lock needs contract, fit-report and resource-root')
                result=lock_curves(spec,plan,a.camera,json.loads(Path(a.contract).read_text()),json.loads(Path(a.fit_report).read_text()),a.resource_root)
            else:result=lock(spec,plan,a.camera)
            need(a.out,'write lock to a new plan with --out; do not silently modify frozen scope');need(not Path(a.out).exists(),'lock output exists');Path(a.out).write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
        else:result=evaluate(spec,plan)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('passed',result.get('numeric_passed')) else 1
    except (ValueError,OSError,KeyError,TypeError,StopIteration) as e:print(json.dumps({'passed':False,'error':str(e)},ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())
