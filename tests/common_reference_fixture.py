"""Synthetic gate fixture, never image-reconstruction evidence."""
from pathlib import Path
from PIL import Image
import reference_set,reference_admission,project,shape_acceptance

def admit(root,spec,affected,protected):
    root=Path(root)
    for r in spec['references']:
        # Replace old opaque software bytes with a real image for source checks.
        path=root/'test-reference.png';Image.new('RGB',tuple(r['image_size']),'yellow').save(path)
        r.update(path=path.name,sha256=project.sha(path),origin='original',approved=True,provenance='Fabricated original input for isolated software tests; not a photograph or real visual acceptance')
    project.save(root/'spec.json',spec)
    reference_admission.prepare(root,'repair','technical_fix','Synthetic integration test; no visual acceptance claim',affected,protected)
    spec=project.read(root/'spec.json');plan=project.read(root/'reference-plan-v2.json');rid=spec['references'][0]['id'];w,h=spec['references'][0]['image_size']
    artifact=root/'test-review.txt';artifact.write_text('Software fixture only, not an actual visual review.')
    a={'path':artifact.name,'sha256':project.sha(artifact)};spec['source_files'].append(a.copy())
    plan.update(status='ready',strategy='reuse',reuse_reason='Synthetic integration fixture',required_views=[{'id':'test-view','reference_ids':[rid]}],sources=[{'reference_id':rid,'source_identity':'synthetic integration input','purpose':'fixture','view':{'orientation':'front','projection':'known'},'parent_reference_ids':[]}])
    plan['critical_components']=[{'id':cid,'component_ids':[cid],'coverage':{k:[rid]for k in ('outline','volume','connection')},'uncertainties':['Software fixture does not certify shape'],
        'blocking_unknowns':[],'authority':{'reference_ids':[rid],'revision':'fixture','reason':'synthetic'},'observation_ids':[],
        'manual_constraints':[{'kind':'connection-review','component_id':cid,'reference_ids':[rid],'uncertainty':'synthetic','rationale':'integration fixture','artifact':a.copy()}],
        'evidence':[{'purpose':k,'reference_id':rid,'roi':[0,0,w,h],'visibility':'visible','usable':True,'claim':'fixture','limitation':'no actual photo judgment'}for k in ('outline','volume','connection')],
        'features':[{'id':cid+'-feature','kind':'visual','component_ids':[cid],'reference_ids':[rid],'criterion':'software fixture','severity':'critical','manual_reason':'testing review mechanics only','review_camera_ids':[next(iter(spec['cameras']))]}]}for cid in affected]
    plan['consistency_review']={'verdict':'pass','method':'visual','reviewer':'synthetic fixture','rationale':'tests evidence mechanics only','reference_hashes':{r['id']:r['sha256']for r in spec['references']},'artifacts':[a.copy()]}
    project.save(root/'reference-plan-v2.json',plan)
    for x in spec['source_files']:
        if x['path']=='reference-plan-v2.json':x['sha256']=project.sha(root/x['path'])
    project.save(root/'spec.json',spec)
    analysis=project.read(root/'analysis.json')
    for r in analysis['references']:r['origin']='original'
    project.save(root/'analysis.json',analysis)
    return spec,plan
