"""Require regional multi-view review records; records do not prove visual truth."""

def validate(spec, evidence, stage, evidence_path=None):
    contract=spec.get('production_contract')
    if contract is None or stage not in ('body','review'):
        return
    def need(ok,msg):
        if not ok: raise ValueError(msg)
    review=evidence.get('production_review',{})
    need(review.get('reviewer_role') in ('author','independent'), 'declare production reviewer role')
    need(isinstance(review.get('execution_reference'),str) and review['execution_reference'].strip(), 'review execution reference required; role alone is not independent proof')
    need(review.get('coverage_verdict')=='pass','reference feature coverage review required')
    rows=review.get('features');need(isinstance(rows,list),'regional visual review required')
    ids=[r.get('id') for r in rows];need(len(set(ids))==len(ids),'duplicate feature reviews')
    indexed={r['id']:r for r in rows};known={f['id'] for f in contract['features']}
    need(set(ids)<=known,'unknown reviewed feature')
    artifacts={a['path'] for a in evidence.get('artifacts',[])}
    import json,math,hashlib
    from pathlib import Path
    from PIL import Image
    from scene_build import resolve
    need(evidence_path is not None,'evidence path required for capture verification')
    base=Path(evidence_path).resolve().parent
    capture_name=review.get('capture_report')
    need(capture_name in artifacts,'capture report must be hashed evidence artifact')
    capture_path=base/capture_name
    capture=json.loads(capture_path.read_text())
    need(capture.get('passed') is True and capture.get('spec_sha256')==evidence.get('spec_sha256'),'capture report failed or stale')
    cameras=resolve(spec.get('cameras',{}),spec.get('parameters',{}))
    need(capture.get('cameras')==cameras,'capture camera settings differ')
    captures=capture.get('captures',[])

    for f in contract['features']:
        if f['importance']=='supporting':continue
        row=indexed.get(f['id'],{});need(row.get('verdict')=='pass','regional visual failure/missing: '+f['id'])
        need(isinstance(row.get('rationale'),str) and row['rationale'].strip(),'feature rationale required')
        views=row.get('views');need(isinstance(views,list) and views,'feature views required')
        angles=[];viewpaths=[]
        for v in views:
            cid=v.get('camera_id');need(cid in cameras,'view camera missing')
            need(v.get('artifact_path') in artifacts,'view artifact missing')
            imagepath=(base/v['artifact_path']).resolve()
            actual=hashlib.sha256(imagepath.read_bytes()).hexdigest()
            matches=[c for c in captures if c.get('view')==cid and c.get('mode') in ('gray','beauty') and (capture_path.parent/c.get('file','')).resolve()==imagepath and c.get('sha256')==actual]
            need(bool(matches),'view is not bound to matching captured image')
            with Image.open(imagepath) as im: im.verify()
            angles.append(cid);viewpaths.append(v['artifact_path'])
        if f['form_type']!='surface_detail':
            need(len(set(angles))>=2 and len(set(viewpaths))>=2,'volume needs two distinct camera records and artifacts')
            import json
            directions=[]
            for c in angles:
                cam=cameras[c];d=[a-b for a,b in zip(cam['position'],cam['target'])];length=math.sqrt(sum(x*x for x in d))
                need(length>0,'invalid capture camera direction');directions.append([x/length for x in d])
            need(any(math.dist(directions[0],d)>1e-6 for d in directions[1:]),'duplicated camera directions cannot establish depth')
    # Immutable source/resource/artifact hashes are checked by workflow before this.
