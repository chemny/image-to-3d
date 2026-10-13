#!/usr/bin/env python3
"""Reference coverage/provenance gates; validates evidence identities, not visual truth."""
import argparse
import json
from pathlib import Path
from workflow import read, digest, require, nonempty


def template():
    return {'version':1,'status':'pending','strategy':'generate','reuse_reason':'',
            'required_views':[],'critical_components':[],'sources':[],
            'unresolved_conflicts':[], 'consistency_review':{'verdict':'pending','method':'visual','reviewer':'','rationale':'','reference_hashes':{},'artifacts':[]}}


def validate(spec_path, stage='references'):
    spec_path=Path(spec_path).resolve();spec=read(spec_path)
    if spec.get('quality_contract',{}).get('reference_standard') != 1:
        return {'passed':True,'certified':False,'scope':'legacy; reference standard not assessed'}
    base=spec_path.parent;name=spec.get('reference_plan')
    require(nonempty(name) and not Path(name).is_absolute(),'reference_plan relative path required')
    resources={r['path']:r['sha256'] for r in spec.get('source_files',[])}
    def artifact(item):
        require(isinstance(item,dict) and nonempty(item.get('path')),'reference evidence artifact missing')
        path=item['path'];require(not Path(path).is_absolute(),'evidence paths must be spec-relative')
        require(resources.get(path)==item.get('sha256') and item.get('sha256')==digest(base/path),'reference evidence must be current and source-hashed: '+path)
    require(resources.get(name)==digest(base/name),'reference plan must be current and source-hashed')
    plan=read(base/name);require(plan.get('version')==1,'unsupported reference plan')
    if stage=='intake':
        return {'passed':True,'certified':False,'scope':'draft reference plan registered'}
    require(plan.get('status')=='ready','reference plan pending')
    require(plan.get('strategy') in ('generate','reuse'),'reference strategy required')
    if plan['strategy']=='reuse':require(nonempty(plan.get('reuse_reason')),'document sufficient-reference reuse reason')
    require(plan.get('unresolved_conflicts')==[],'unresolved reference conflicts')
    refs={r['id']:r for r in spec['references']};require(refs,'references required')
    if plan['strategy']=='generate':
        require(any(r.get('origin')=='generated' for r in refs.values()),'generate strategy requires generated supplemental references; otherwise document sufficient reuse')
    from PIL import Image
    for rid,r in refs.items():
        require(r.get('sha256')==digest(base/r['path']),'reference resource stale: '+rid)
        with Image.open(base/r['path']) as im:
            require(r.get('image_size')==list(im.size),'reference dimensions mismatch: '+rid);im.verify()
        require(r.get('approved') is True,'reference pending approval: '+rid)
        require(not r.get('conflicts_with'),'reference conflict must be resolved: '+rid)
    sources=plan.get('sources',[]);require(isinstance(sources,list),'sources must be list')
    require(len(sources)==len(refs) and {s.get('reference_id') for s in sources}==set(refs),'source identities must cover every reference exactly once')
    for s in sources:
        rid=s['reference_id'];r=refs[rid]
        require(nonempty(s.get('source_identity')) and nonempty(s.get('purpose')),'reference source identity/purpose missing')
        require(all(nonempty(s.get('view',{}).get(k)) for k in ('orientation','projection')),'reference orientation/projection missing')
        parents=s.get('parent_reference_ids',[])
        require(isinstance(parents,list) and all(p in refs and p!=rid for p in parents),'invalid reference parents')
        if r['origin'] in ('generated','derived'):
            require(parents,'generated/derived reference requires parent identity')
            require(r.get('source_reference_ids') == parents,'reference parent identities must match source_reference_ids')
        if r['origin']=='generated':
            a=s.get('approval',{});require(a.get('actor')=='user' and a.get('decision')=='approved' and a.get('reference_sha256')==r['sha256'],'generated reference requires matching user approval')
            artifact(a.get('evidence'))
    parents_by_id={s['reference_id']:s.get('parent_reference_ids',[]) for s in sources}
    def check_ancestry(rid,trail):
        require(rid not in trail,'reference provenance parent cycle')
        for parent in parents_by_id[rid]:check_ancestry(parent,trail | {rid})
    for rid in refs:check_ancestry(rid,set())
    views=plan.get('required_views',[]);require(isinstance(views,list) and views,'required view coverage missing')
    def coverage(ids):
        require(isinstance(ids,list) and ids and len(set(ids))==len(ids) and all(i in refs for i in ids),'missing/invalid reference coverage')
    require(all(nonempty(v.get('id')) for v in views) and len({v['id'] for v in views})==len(views),'view IDs missing/duplicate')
    for v in views:coverage(v.get('reference_ids'))
    parts=plan.get('critical_components',[]);require(isinstance(parts,list) and parts,'critical component coverage missing')
    require(all(nonempty(c.get('id')) for c in parts) and len({c['id'] for c in parts})==len(parts),'critical component IDs missing/duplicate')
    comps={c['id'] for c in spec['components']};obs={o['id']:o for o in spec['observations']}
    manual_count=0
    for c in parts:
        for kind in ('outline','volume','connection'):coverage(c.get('coverage',{}).get(kind))
        require(isinstance(c.get('uncertainties'),list) and all(nonempty(u) for u in c['uncertainties']),'explicit uncertainties list required (empty means none declared)')
        if stage!='references':
            require(c.get('component_ids') and all(i in comps for i in c['component_ids']),'coverage must bind real component IDs')
            observation_ids=c.get('observation_ids',[]);manual=c.get('manual_constraints',[])
            require(isinstance(observation_ids,list) and isinstance(manual,list),'observation_ids/manual_constraints must be lists')
            require(observation_ids or manual,'coverage requires real observations or explicit manual constraints')
            require(all(i in obs for i in observation_ids),'coverage must bind real observation IDs')
            require(all(obs[i].get('component_id') in c['component_ids'] for i in observation_ids),'observation must bind its covered component')
            covered={i for ids in c['coverage'].values() for i in ids}
            require(all(obs[i]['reference_id'] in covered for i in observation_ids),'bound observation outside component reference coverage')
            for constraint in manual:
                require(isinstance(constraint,dict),'manual constraint must be an object')
                require(constraint.get('kind') in ('silhouette','section','connection-review'),'invalid manual constraint kind')
                require(constraint.get('component_id') in c['component_ids'],'manual constraint must bind its covered component')
                ids=constraint.get('reference_ids');coverage(ids)
                require(set(ids)<=covered,'manual constraint outside component reference coverage')
                require(nonempty(constraint.get('uncertainty')) and nonempty(constraint.get('rationale')),'manual constraint uncertainty/rationale required')
                artifact(constraint.get('artifact'))
                manual_count+=1
    review=plan.get('consistency_review',{})
    require(review.get('verdict')=='pass' and review.get('method')=='visual' and nonempty(review.get('reviewer')) and nonempty(review.get('rationale')),'explicit visual consistency review required')
    require(review.get('reference_hashes')=={k:r['sha256'] for k,r in refs.items()},'stale/incomplete consistency review reference identities')
    require(review.get('artifacts'),'visual consistency review artifacts required')
    for a in review['artifacts']:artifact(a)
    return {'passed':True,'certified':False,'stage':stage,'views':len(views),'critical_components':len(parts),'manual_constraints':manual_count,'manual_review_required':bool(manual_count),'scope':'coverage, provenance and evidence identity; visual truth is not automatically certified'}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--spec',required=True);ap.add_argument('--stage',choices=['intake','references','spec'],default='references');a=ap.parse_args()
    try: print(json.dumps(validate(a.spec,a.stage),ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps({'passed':False,'error':str(e)},ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())
