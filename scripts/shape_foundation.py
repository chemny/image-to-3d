#!/usr/bin/env python3
"""Shared whole-form controls and fail-closed acceptance. No image-to-3D truth claim."""
import argparse, copy, hashlib, json, math, os
from pathlib import Path
import scene_build as scene
from shape_acceptance import points

def need(ok,msg):
    if not ok:raise ValueError(msg)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def template():
    return {'version':1,'level':'global','phase':'foundation','primary_components':[], 'controls':[], 'relations':[], 'dependency_edges':[], 'required_views':[], 'required_features':[], 'feature_definitions':[], 'fit_groups':[], 'scale_gauge':{'parameter_id':'','reason':''}}

def enabled(spec):return spec.get('quality_contract',{}).get('foundation_standard')==1

def policy(path):
    p=Path(path);s=read(p)
    for name in ('project.json','state.json'):
        q=p.parent/name
        if q.is_file()and read(q).get('foundation_standard')==1:
            need(enabled(s),'foundation policy cannot be removed or downgraded')
    return enabled(s)

def view_diversity(spec,ids):
    cams=scene.resolve(spec['cameras'],spec['parameters']);directions=[]
    for cid in ids:
        c=cams[cid];v=[a-b for a,b in zip(c['position'],c['target'])];length=math.sqrt(sum(x*x for x in v));need(length>1e-12,'degenerate foundation camera')
        directions.append([x/length for x in v])
    # Parallel and opposite viewing axes do not provide an independent depth direction.
    need(any(abs(sum(x*y for x,y in zip(a,b)))<1-1e-8 for i,a in enumerate(directions)for b in directions[i+1:]),'foundation views must reveal different directions, not different distances along one axis')
    return True

def contract(spec,strict=True):
    if not enabled(spec):return {'required':False}
    f=spec.get('foundation');need(isinstance(f,dict)and f.get('version')==1,'foundation v1 declaration required')
    need(f.get('level')in ('global','region','detail','technical'),'explicit repair level required')
    need(f.get('phase')in ('foundation','detail'),'foundation phase invalid')
    if not strict:return {'required':True,'level':f['level'],'phase':f['phase']}
    nodes={c['id']:c for c in spec['components']};refs={r['id']:r for r in spec['references']}
    ids=f.get('primary_components',[])
    need(ids and len(ids)==len(set(ids))and set(ids)<=set(nodes),'actual primary components required')
    views=f.get('required_views',[])
    need(len(views)>=2 and len(views)==len(set(views))and set(views)<=set(spec['cameras']),'at least two foundation views required')
    cams=scene.resolve(spec['cameras'],spec['parameters'])
    view_diversity(spec,views)
    controls=f.get('controls',[]);seen=set();covered=set()
    for c in controls:
        need(c.get('id')and c['id']not in seen,'unique control IDs required');seen.add(c['id'])
        need(c.get('kind')in ('curve','section'),'unknown control kind')
        bs=c.get('bindings',[]);need(len(bs)>=(4 if c['kind']=='curve'else 3),'control needs distributed surface samples')
        need(all(b.get('component_id')in ids and ('vertex_index'in b)^('patch_id'in b)for b in bs),'control must bind real primary surface')
        covered.update(b['component_id']for b in bs)
        need(c.get('reference_ids')and set(c['reference_ids'])<=set(refs),'control reference authority required')
        need(isinstance(c.get('rationale'),str)and c['rationale'].strip(),'control rationale required')
        need(set(c.get('parameter_ids',[]))<=set(spec['parameters']),'control parameter unknown')
    need(covered==set(ids),'controls must cover every primary component')
    for edge in f.get('dependency_edges',[]):need(len(edge)==2 and set(edge)<=set(nodes)and edge[0]!=edge[1],'invalid dependency edge')
    edges=f.get('dependency_edges',[])
    def visit(k,path):
        need(k not in path,'foundation dependency cycle')
        for a,b in edges:
            if a==k:visit(b,path|{k})
    for k in nodes:visit(k,set())
    groups=f.get('fit_groups',[]);used=set();order={'proportion':0,'curves':1,'sections':2}
    need([order.get(g.get('level'),99)for g in groups]==sorted(order.get(g.get('level'),99)for g in groups),'fit groups must proceed coarse to fine')
    for g in groups:
        ps=g.get('parameter_ids',[])
        need(g.get('level')in order and ps and len(ps)==len(set(ps))and not used&set(ps)and set(ps)<=set(spec['parameters']),'invalid fit parameter groups');used.update(ps)
    gauge=f.get('scale_gauge',{});gid=gauge.get('parameter_id');need(gid in spec['parameters']and gauge.get('reason'),'fixed scale gauge required')
    gp=spec['parameters'][gid];need(gp['min']==gp['value']==gp['max']and gid not in used,'scale gauge must be fixed and excluded from fit')
    need(f.get('required_features')and len(f['required_features'])==len(set(f['required_features'])),'required whole-form features must be declared')
    definitions=f.get('feature_definitions',[])
    need(len(definitions)==len(f['required_features']) and {v.get('id')for v in definitions}==set(f['required_features']),'whole-form feature definitions required')
    need({'outline','internal','volume','surface'}<={v.get('kind')for v in definitions},'whole-form review must cover outline, internal features, volume and surface')
    for v in definitions:need(v.get('criterion') and v.get('reference_ids') and set(v['reference_ids'])<=set(refs) and v.get('view_ids') and set(v['view_ids'])<=set(views),'whole-form feature authority and views required')
    for rel in f.get('relations',[]):
        need(rel.get('id')and len(rel.get('bindings',[]))==2 and all(b.get('component_id')in ids for b in rel['bindings']),'actual structure relation endpoints required')
        need(all(type(rel.get(k))in (float,int)and math.isfinite(rel[k])for k in ('min','max'))and 0<=rel['min']<=rel['max'],'relation bounds invalid')
    return {'required':True,'level':f['level'],'phase':f['phase'],'controls':len(controls)}

def geometry_identity(spec):
    f=spec['foundation'];resolved,nodes=scene.prepared(spec);selected={}
    for cid in f['primary_components']:
        chain=[];key=cid
        while key is not None:
            c=nodes[key];chain.append({k:c.get(k)for k in ('id','parent','position','rotation')});key=c.get('parent')
        selected[cid]={'geometry':nodes[cid]['geometry'],'generator':nodes[cid].get('_construction_recipe'),'transforms':chain}
    # Appearance/attachments may evolve, but primary geometry, authority and cameras may not silently drift.
    data={'foundation':{k:v for k,v in f.items()if k!='phase'},'primary':selected,'references':spec['references'],'cameras':resolved['cameras'],'observations':resolved.get('observations',[]),'quality':spec['quality_contract']}
    if spec.get('external_geometry'):data['external_geometry']=spec['external_geometry']
    return digest(data)

def evaluate(spec,resource_root=None):
    d=contract(spec)
    if not d['required']:return {'required':False,'numeric_passed':False,'visual_pass':False}
    scene.build(spec);prepared=scene.prepared(spec);rows=[];errors=[]
    for c in spec['foundation']['controls']:
        for b in c['bindings']:
            g=prepared[1][b['component_id']]['geometry']
            if 'vertex_index'in b:need(b['vertex_index']in g.get('triangles',g.get('indices',[])),'orphan control vertex')
        ps=points(spec,c['bindings'],prepared);angles=[]
        for a,b,z in zip(ps,ps[1:],ps[2:]):
            v=[y-x for x,y in zip(a,b)];w=[y-x for x,y in zip(b,z)];nv=math.dist(a,b);nw=math.dist(b,z)
            need(nv>1e-12 and nw>1e-12,'degenerate control samples')
            angles.append(math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(v,w))/(nv*nw))))))
        limit=c.get('max_turn_deg');passed=True
        if limit is not None:
            need(type(limit)in (int,float)and 0<limit<=180,'turn limit invalid');passed=max(angles,default=0)<=limit
        if not passed:errors.append(c['id']+': curve turn exceeds declaration')
        rows.append({'id':c['id'],'world_points':ps,'max_turn_deg':max(angles,default=0),'passed':passed,'scope':'declared samples only; no global curvature/self-intersection proof'})
    for rel in spec['foundation'].get('relations',[]):
        a,b=points(spec,rel['bindings'],prepared);distance=math.dist(a,b);ok=rel['min']<=distance<=rel['max']
        rows.append({'id':rel['id'],'distance':distance,'passed':ok})
        if not ok:errors.append(rel['id']+': structure relation outside bounds')
    from surface_differentials import report as differentials
    analytic=differentials(spec)
    external=set();external_error=None
    if spec.get('external_geometry'):
        try:
            from external_geometry import readiness
            external=readiness(spec,resource_root)
        except (ValueError,OSError,KeyError,TypeError) as error:
            external_error=str(error)
    missing=[cid for cid in spec['foundation']['primary_components']if prepared[1][cid]['geometry']['type']!='bezier_network'and '_construction_recipe'not in prepared[1][cid]and cid not in external]
    # Native Bezier and deterministic form recipes regenerate actual geometry. Legacy sampled meshes remain diagnostic.
    return {'construction_ready':not missing and not external_error,'construction_blockers':[cid+': sampled mesh has no verified whole-form control generator'for cid in missing]+([external_error]if external_error else []),'verified_external_components':sorted(external),'differentials':analytic,'required':True,'numeric_passed':not errors,'visual_pass':False,'errors':errors,'rows':rows,'foundation_identity':geometry_identity(spec)}

def artifact(base,item):
    need(isinstance(item,dict)and isinstance(item.get('path'),str)and not Path(item['path']).is_absolute(),'relative evidence path required')
    p=(base/item['path']).resolve();need(p.is_file()and sha(p)==item.get('sha256'),'missing/stale foundation artifact: '+str(p));return p

def validate_review(spec_path,entry):
    p=Path(spec_path).resolve();s=read(p);contract(s)
    from repair_capture import resources
    resources(p)
    rp=artifact(p.parent,entry);r=read(rp);base=rp.parent
    bp=artifact(base,r['baseline_spec']);bs=read(bp)
    need(enabled(bs)and r.get('foundation_identity')==geometry_identity(bs)==geometry_identity(s),'whole-form baseline changed; revalidate before detail')
    measured=evaluate(s,p.parent)
    need(measured['construction_ready'],'primary meshes lack regenerable whole-form controls; reconstruct before acceptance')
    need(measured['numeric_passed'],'whole-form numeric checks failed')
    need(r.get('technical_verdict')=='pass'and r.get('reference_verdict')=='pass'and r.get('reviewer')and r.get('notes'),'separate technical/reference whole-form verdicts required')
    from repair_capture import validate_receipt
    receipt=artifact(base,r['capture_receipt']);capture=validate_receipt(receipt,bp,bs['foundation']['required_views'])
    if bs.get('quality_contract',{}).get('reference_standard')==2:
        from reference_set import validate
        from shape_acceptance import evaluate as shape_check
        validate(bp,'spec');need(shape_check(bs,read(bp.parent/bs['reference_plan']))['numeric_passed'],'reference feature checks failed')
    raw_receipt=read(receipt)
    for cid in bs['foundation']['required_views']:
        modes={a['mode']for v in raw_receipt['views']if v['id']==cid for a in v['artifacts']if a.get('pose')=='closed'}
        need({'beauty','mask'}<=modes,'whole-form review requires actual appearance and mask for every view')
    results=r.get('results',[]);need(len(results)==len({x.get('id')for x in results}),'duplicate foundation results')
    need({x.get('id')for x in results}==set(bs['foundation']['required_features']),'whole-form features not fully reviewed')
    defs={v['id']:v for v in bs['foundation']['feature_definitions']}
    for row in results:
        need(set(defs[row['id']]['view_ids'])<=set(row.get('view_ids',[])),'whole-form feature omitted required views')
        need(row.get('verdict')=='pass'and row.get('notes')and row.get('view_ids')and set(row['view_ids'])<=set(capture['views']),'whole-form feature failed or lacks captured views')
    grids=r.get('grids',[]);need(grids,'reference pixel grids required')
    refs={x['id']:x for x in bs['references']};covered=set()
    for item in grids:
        gp=artifact(base,item);g=read(gp);rid=item.get('reference_id');need(rid in refs and g.get('sha256')==refs[rid]['sha256']and g.get('grid_kind')=='pixel','grid must bind an authoritative source pixel image')
        need(sha(g['source'])==g['sha256'],'grid source changed');artifact(gp.parent,g['image']);covered.add(rid)
    # Require a validated projection difference for every reference-matched view.
    diffs=r.get('comparisons',[]);need(diffs,'reference/model comparisons required');views=set()
    for item in diffs:
        dp=artifact(base,item)
        from reference_evidence import validate_diff
        validate_diff(dp)
        d=read(dp);cid=item.get('camera_id');need(cid in bs['foundation']['required_views'],'comparison camera outside foundation views')
        need(d.get('spec_sha256')==sha(bp)and d.get('reference_id')in covered,'comparison candidate/source identity mismatch')
        need(d.get('camera_id')==cid,'comparison camera mismatch')
        alignment=artifact(dp.parent,d['alignment']);a=read(alignment)
        need(a['camera_sha256']==sha(dp.parent/d['camera']['path']),'comparison camera identity mismatch')
        from reference_evidence import verify_alignment
        verify_alignment(dp.parent/d['reference_mask']['path'],dp.parent/d['candidate_mask']['path'],alignment)
        need(read(dp.parent/d['camera']['path'])==scene.resolve(bs['cameras'][cid],bs['parameters']),'comparison camera differs from captured view')
        # Matching opaque mask source must be an image in the validated browser receipt.
        maskpath=(dp.parent/d['candidate_mask']['path']).resolve()
        cp=read(receipt);reportpath=(receipt.parent/cp['capture_report_path']).resolve();cr=read(reportpath)
        owner=[v for v in cr['captures']if v['view']==cid and v['mode']=='mask'and v.get('pose','closed')=='closed']
        need(len(owner)==1,'one closed captured mask per comparison required');row=owner[0]
        raw=(reportpath.parent/row['file']).resolve()
        from PIL import Image
        with Image.open(raw)as im:expected=im.convert('L');expected_bytes=expected.tobytes();expected_size=expected.size
        with Image.open(maskpath)as im:need(im.mode=='L'and im.size==expected_size and im.tobytes()==expected_bytes,'comparison mask differs from actual captured pixels')
        mf=(receipt.parent/cp['bundle_manifest_path']).resolve()
        need((dp.parent/d['model']['path']).resolve()==mf.parent/'model.js','comparison model differs from captured bundle')
        rid=d['reference_id'];need(a.get('reference_image_sha256')==refs[rid]['sha256'],'comparison source image mismatch')
        artifact(dp.parent,d['image']);views.add(cid)
    need(set(bs['foundation']['required_views'])<=views,'every foundation view needs a comparison')
    return {'passed':True,'foundation_identity':r['foundation_identity'],'scope':'authored whole-form review with current numerical and capture identity checks; not automatic shape recognition'}

def gate(spec_path,review=False,entry=None):
    p=Path(spec_path);s=read(p)
    if not policy(p):return {'required':False,'legacy':True}
    contract(s)
    if review or s['foundation']['phase']=='detail':
        if entry is None:
            meta=read(p.parent/'project.json')if (p.parent/'project.json').is_file()else{};entry=meta.get('foundation_review')
        need(entry,'whole-form acceptance required before detail or adoption')
        return validate_review(p,entry)
    result=evaluate(s,p.parent)
    need(result['construction_ready'],'primary meshes lack regenerable whole-form controls; reconstruct before formal construction')
    return result

def attach(root,review):
    p=Path(root).resolve()/'spec.json';review=Path(review).resolve();entry={'path':os.path.relpath(review,p.parent),'sha256':sha(review)};result=validate_review(p,entry)
    m=read(p.parent/'project.json');m['foundation_review']=entry;(p.parent/'project.json').write_text(json.dumps(m,indent=2)+'\n');return result

def main():
    a=argparse.ArgumentParser();a.add_argument('command',choices=['check','identity','review']);a.add_argument('--spec',required=True);a.add_argument('--review');a.add_argument('--out',required=True);x=a.parse_args()
    try:
        p=Path(x.spec);s=read(p);r=evaluate(s,p.parent)if x.command=='check'else {'foundation_identity':geometry_identity(s)}if x.command=='identity'else validate_review(p,{'path':os.path.relpath(x.review,p.parent),'sha256':sha(x.review)})
        with Path(x.out).open('x')as f:json.dump(r,f,indent=2)
        print(json.dumps({'report':x.out,'visual_pass':False}));return 0
    except (ValueError,KeyError,OSError,TypeError)as e:print(json.dumps({'error':str(e)}));return 2
if __name__=='__main__':raise SystemExit(main())


def archive(root,destination):
    """Preserve exact evidence bytes and path inventory; do not transplant approvals."""
    root=Path(root).resolve();p=root/'spec.json'
    if not enabled(read(p)):return None
    gate(p,True);entry=read(root/'project.json')['foundation_review'];dest=Path(destination);dest.mkdir(exist_ok=False,parents=True);seen=set();inventory=[]
    def add(q,role):
        q=Path(q).resolve()
        if q in seen:return
        seen.add(q);need(q.is_file(),'missing foundation archive input');name='files/'+sha(q)+'-'+q.name;target=dest/name;target.parent.mkdir(exist_ok=True);target.write_bytes(q.read_bytes());inventory.append({'role':role,'original_path':str(q),'path':name,'sha256':sha(target)})
        if q.suffix!='.json':return
        d=read(q)
        if not isinstance(d,dict):return
        for k in ('baseline_spec','capture_receipt','reference_mask','candidate_mask','alignment','camera','model','image'):
            v=d.get(k)
            if isinstance(v,dict)and v.get('path'):add(q.parent/v['path'],k)
            elif isinstance(v,str)and k in ('camera','model'):add(q.parent/v,k)
        for k in ('bundle_manifest_path','capture_report_path'):
            if isinstance(d.get(k),str):add(q.parent/d[k],k)
        for k in (('grids','comparisons','references','source_files')if role=='baseline_spec'else ('grids','comparisons')):
            for v in d.get(k,[]):
                if isinstance(v,dict)and v.get('path'):add(q.parent/v['path'],k)
        for v in d.get('captures',[]):
            add(q.parent/v['file'],'rendered-image')
            if v.get('binary_mask_file'):add(q.parent/v['binary_mask_file'],'binary-mask')
        if isinstance(d.get('files'),dict):
            for name in d['files']:add(q.parent/name,'bundle-file')
        if isinstance(d.get('source'),str)and isinstance(d.get('sha256'),str):add(q.parent/d['source'],'grid-source')
    add(root/entry['path'],'whole-form-review')
    (dest/'inventory.json').write_text(json.dumps({'version':1,'files':inventory,'scope':'Original evidence bytes and provenance, not portable approval replay. Relocated rebuild remains unapproved.'},indent=2)+'\n');return {'path':str(dest),'files':len(inventory)}
