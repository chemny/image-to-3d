#!/usr/bin/env python3
"""Bounded coordinate descent on explicit independent 2-D landmarks.
Observation: component_id, uv, target, projection={matrix:[[...],[...]],offset:[...]},
role=calibration or validation; optional protected=true for calibration controls only,
tolerance (world projected units). Validation measurements are held out of search. Cameras remain frozen.
Input targets MUST be supplied; this tool does not derive targets from candidates.
Synthetic experiments cannot establish image reconstruction performance.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from surface_model import build, digest, point, values


def errors(spec, role=None):
    params=values(spec);components={c['id']:c for c in spec['components']};result={}
    for obs in spec['observations']:
        if obs.get('role') not in ('calibration','validation'): raise ValueError('explicit calibration or validation observation role required')
        if obs.get('protected') and obs['role']=='validation': raise ValueError('heldout validation cannot constrain search')
        if role is not None and obs['role'] != role: continue
        if obs['id'] in result: raise ValueError('duplicate observation ID')
        uv=obs['uv']; target=obs['target']
        if len(uv)!=2 or len(target)!=2 or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in uv+target):
            raise ValueError('uv and target must be finite 2D vectors')
        g=components[obs['component_id']]['geometry']
        if not (0 <= uv[1] <= 1 and (0 if g['type']=='lathe' else -1) <= uv[0] <= 1):
            raise ValueError('observation outside parameter domain')
        p=point(g,params,*uv)
        projection=obs['projection']; matrix=projection['matrix'];offset=projection.get('offset',[0,0])
        if len(matrix)!=2 or any(len(row)!=3 for row in matrix) or len(offset)!=2: raise ValueError('projection must be explicit 2x3 matrix and 2D offset')
        if not all(isinstance(x,(float,int)) and math.isfinite(x) for row in matrix for x in row) or not all(math.isfinite(x) for x in offset):
            raise ValueError('projection must be finite')
        xy=[sum(a*b for a,b in zip(row,p))+offset[i] for i,row in enumerate(matrix)]
        result[obs['id']]=sum((a-b)**2 for a,b in zip(xy,obs['target']))**.5
    return result


def fit(spec, parameter_ids=None, max_iterations=80):
    if not isinstance(max_iterations,int) or max_iterations < 1: raise ValueError('iterations must be positive')
    current=copy.deepcopy(spec); build(current); errors(current); initial=errors(current,'calibration')
    if not initial: raise ValueError('calibration landmarks required')
    ids=parameter_ids or list(current['parameters'])
    if not ids or len(ids)!=len(set(ids)) or any(k not in current['parameters'] for k in ids):
        raise ValueError('unique known fit parameters required')
    steps={k:(current['parameters'][k]['max']-current['parameters'][k]['min'])/8 for k in ids}
    protected={o['id']:max(initial[o['id']],o.get('tolerance',0)) for o in current['observations'] if o.get('protected') and o['role']=='calibration'}
    def score(err): return sum(v*v for v in err.values())/len(err)
    current_score=score(initial);journal=[]
    for iteration in range(max_iterations):
        improved=False
        for key in ids:
            for direction in (-1,1):
                candidate=copy.deepcopy(current);p=candidate['parameters'][key];p['value']=max(p['min'],min(p['max'],p['value']+direction*steps[key]))
                item={'iteration':iteration,'parameter':key,'direction':direction,'candidate_spec_sha256':digest(candidate),
                      'base_spec_sha256':digest(current),'value':p['value']}
                try:
                    build(candidate);err=errors(candidate,'calibration');value=score(err)
                    regress=[k for k,limit in protected.items() if err[k]>limit+1e-10]
                    accepted=value<current_score-1e-14 and not regress
                    item.update(score=value,accepted=accepted,protected_regressions=regress,
                                reason='improved' if accepted else ('protected_regression' if regress else 'no_improvement'))
                    if accepted: current=candidate;current_score=value;improved=True
                except (ValueError,KeyError,OverflowError) as exc:
                    item.update(accepted=False,reason='invalid_geometry',error=str(exc))
                journal.append(item)
        if not improved:
            steps={k:v/2 for k,v in steps.items()}
            if max(steps.values(),default=0)<1e-6: break
    return {'scope':'landmark parameter fit; cameras frozen; no photographic fidelity claim',
            'initial_spec_sha256':digest(spec),'final_spec_sha256':digest(current),
            'implementation_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('surface_model.py')]},
            'initial_score':score(initial),'final_score':current_score,'initial_errors':initial,'final_errors':errors(current,'calibration'),
            'heldout_initial_errors':errors(spec,'validation'),'heldout_final_errors':errors(current,'validation'),
            'objective_role':'calibration','heldout_used_for_search':False,
            'iterations':journal,'spec':current}


def main():
    p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('--out',required=True);p.add_argument('--parameters',nargs='+');p.add_argument('--iterations',type=int,default=80)
    a=p.parse_args();result=fit(json.loads(Path(a.spec).read_text()),a.parameters,a.iterations);Path(a.out).write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ['initial_score','final_score','final_spec_sha256']}))

if __name__=='__main__':main()
