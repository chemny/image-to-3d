#!/usr/bin/env python3
"""Single local entry: image intake, authored Spec, build, fit, capture, review, export.
Agent supplies image semantics/control network and explicit reviews; no invented geometry.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import workflow

CORE = Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def save(p, value):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def require(ok,msg):
    if not ok: raise ValueError(msg)
def load(root):
    root=Path(root).resolve();meta=read(root/'project.json')
    require(meta['schema_version']==1,'unsupported project')
    return root,meta,root/'spec.json'
def bundle_hashes(root):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='bundle-manifest.json'}
def new_dir(path):
    p=Path(path).resolve();require(not p.exists(),'Output exists; use a new version directory');p.mkdir(parents=True);return p

def init(image,domain,out,object_class=None,intended_use='display',targets=None):
    from PIL import Image
    image=Path(image).resolve();require(image.is_file(),'input image missing')
    with Image.open(image) as im: size=list(im.size);im.verify()
    root=new_dir(out);(root/'references').mkdir();copy=root/'references'/('original'+image.suffix.lower());shutil.copy2(image,copy)
    ref={'id':'original','path':copy.relative_to(root).as_posix(),'sha256':sha(copy),'origin':'original','approved':False,'image_size':size}
    analysis={'references':[{'id':'original','origin':'original','image_size':size}],'feature_inventory':[],'inferences':[]}
    save(root/'analysis.json',analysis)
    from reference_set import template
    save(root/'reference-plan.json',template())
    sources=[{'path':'reference-plan.json','sha256':sha(root/'reference-plan.json')},{'path':'analysis.json','sha256':sha(root/'analysis.json')}]
    for folder in ('scripts','assets'):
        for p in sorted((CORE/folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts: sources.append({'path':os.path.relpath(p,root),'sha256':sha(p)})
    spec={'schema_version':1,'id':root.name,'domain':domain,'coordinate_system':{'unit':'m','up':'y','forward':'z'},'references':[ref],
          'source_files':sources,'parameters':{},'components':[],'materials':{},'cameras':{},'observations':[],
          'checks':[{'id':'reference-shape','kind':'visual','required':True,'stage':'body'},{'id':'assembly-motion','kind':'visual','required':True,'stage':'assembly'},{'id':'final-appearance','kind':'visual','required':True,'stage':'review'}],
          'reference_plan':'reference-plan.json',
          'quality_contract':{'reference_standard':1,'production_standard':1,'scope':'browser-display','limits':{},'assumptions':['Hidden geometry remains inferred until evidence/approval is recorded']}}
    if object_class:
        spec['asset_contract']={'version':1,'object_class':object_class,'intended_use':intended_use,'units_source':'inferred','required_components':[], 'required_operations':['select'],'delivery_targets':targets or ['threejs'],'source_notes':'Author observations and hidden assumptions from the input before validation.'}
        spec['variants']=[]
        spec['checks'].append({'id':'asset-behavior','kind':'runtime','required':True,'stage':'assembly'})
    save(root/'spec.json',spec);save(root/'project.json',{'schema_version':1,'spec':'spec.json','state':'state.json','analysis':'analysis.json','builds':[],'history':[], 'reference_standard':1, 'production_standard':1})
    workflow.init(root/'spec.json',root/'state.json');return next_step(root)

def next_step(root):
    root,meta,p=load(root);s=workflow.status(root/'state.json');s['project']=str(root)
    s['reference_standard']={'required':meta.get('reference_standard') == 1,'plan':read(p).get('reference_plan'),'check':'project.py reference-check --project '+str(root)}
    s['production_standard']={'required':meta.get('production_standard') == 1,'declared':bool(read(p).get('production_contract')),'guide':'references/production-standard.md'}
    messages={'intake':'Read original image; fill feature_inventory/inferences in analysis.json and draft quality limits in spec.json.',
        'references':'Resolve reference coverage/provenance, confirm generated design if needed, explicitly approve chosen references.',
        'spec':'Bind observations to real components/control points, define cameras, geometry, materials, actions and protected features.',
        'body':'Build diagnostic preview, inspect fixed cameras/gray/masks, calibrate with fit where observations support it.',
        'assembly':'Verify actual split parts/hinges/interiors in closed, half and open poses using captures plus mesh checks.',
        'presentation':'Verify materials, actual emissive surfaces, reference-appropriate light and delivery adapter.',
        'review':'Inspect captured model against references and functional evidence; record failures and repair before passing.',
        'delivery':'Recheck hashes, capture provenance and intended runtime; mark delivery then export immutable bundle.'}
    s['action']=messages.get(s['next'],'All recorded gates passed; export a matching non-diagnostic bundle.')
    s['commands']={'validate':f'project.py validate --project {root}','refresh':f'project.py refresh-inputs --project {root}','review':f'project.py mark --project {root} --evidence REVIEW.json'}
    return s

def refresh(root):
    root,meta,p=load(root);spec=read(p);changed=[]
    for kind in ('references','source_files'):
        for item in spec[kind]:
            actual=sha(p.parent/item['path'])
            if actual!=item['sha256']:
                changed.append(item['path']);item['sha256']=actual
                if kind=='references': item['approved']=False
    meta['history'].append({'operation':'refresh-inputs','changed':changed,'previous_spec_sha256':sha(p)})
    save(p,spec);save(root/'project.json',meta)
    return {'changed':changed,'state':next_step(root),'note':'Hashes updated, no approvals granted. Rebase only if references/scope remain eligible.'}

def validate(root):
    from reference_analysis import validate as validate_analysis
    from scene_build import build
    root,meta,p=load(root);spec,_=workflow.validate_spec(p)
    require(spec['quality_contract']['scope']=='synthetic-software-test' or bool(spec['quality_contract']['limits']),'Define task quality limits before reconstruction')
    if meta.get('reference_standard') == 1:
        require(spec.get('quality_contract',{}).get('reference_standard') == 1, 'project reference policy cannot be downgraded')
    if meta.get('production_standard') == 1:
        require(spec.get('quality_contract',{}).get('production_standard') == 1, 'project production policy cannot be downgraded')
    analysis=validate_analysis(read(root/'analysis.json'),spec)
    if isinstance(analysis,dict):require(analysis.get('passed',analysis.get('valid',True)),str(analysis))
    payload=build(spec)
    for m in payload['materials'].values():
        for texture in m.get('maps',{}).values():
            path=(root/texture['path']).resolve()
            require(path.is_relative_to(root) and path.is_file(),'texture must exist inside project')
            require(sha(path)==texture['sha256'],'texture changed: '+texture['path'])
    from scene_assembly import validate as validate_assembly
    validate_assembly(spec)
    require(spec.get('cameras'),'fixed cameras required for rendering/review')
    from reconstruction import project as project_point
    from scene_build import resolve
    for camera in spec['cameras'].values():
        c=resolve(camera,spec['parameters']);project_point(c['target'],c)
    return {'passed':True,'scope':'schema, geometry and authored analysis consistency; not visual acceptance','analysis':analysis,'components':len(spec['components'])}

def gate_build(root,diagnostic):
    s=workflow.status(root/'state.json')
    if not diagnostic:require(not s['blocked'] and 'spec' in s['completed'],'Spec review must pass before production build; --diagnostic isolates unaccepted work')
    return s

def build_project(root,out,diagnostic=False,vehicle_config=None,vehicle_skill=None):
    from scene_build import build,emit_js,resolve,landmark
    root,meta,p=load(root);validate(root);gate=gate_build(root,diagnostic);spec=read(p);payload=build(spec)
    # All generated page dependencies are versioned; no mutation of current page.
    dest=Path(out).resolve();require(not dest.exists(),'Output exists; use a new version directory')
    if vehicle_config:
        skill=Path(vehicle_skill).resolve() if vehicle_skill else Path.home()/'.agents/skills/vehicle-configurator'
        require((skill/'scripts/locked_configurator.py').is_file(),'vehicle delivery skill missing; use --vehicle-skill')
        cfg=read(vehicle_config);bindings=spec.get('vehicle_bindings',{})
        require(cfg.get('partBindings')==bindings.get('actions'),'vehicle config partBindings differ from actual model actions')
        # Validate strictly in Python and runtime factory; factory itself must be standalone.
        code=emit_js(payload)
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            model=Path(temp)/'model.js';model.write_text(code)
            proc=subprocess.run([sys.executable,str(skill/'scripts/locked_configurator.py'),'build','--out',str(dest),'--config',str(Path(vehicle_config).resolve()),'--model',str(model)],capture_output=True,text=True)
            require(proc.returncode==0,'Locked template build failed: '+proc.stdout+proc.stderr)
        mode='locked-vehicle'
    else:
        shutil.copytree(CORE/'assets/review-viewer',dest);shutil.copytree(CORE/'assets/vendor',dest/'vendor');(dest/'model.js').write_text(emit_js(payload));mode='generic-review'
    # Material resources get stable bundle-local paths; original Spec remains editable.
    for material in payload['materials'].values():
        for texture in material.get('maps',{}).values():
            source=root/texture['path'];relative='textures/'+texture['sha256']+source.suffix.lower()
            target=dest/relative;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target);texture['path']=relative
    (dest/'model.js').write_text(emit_js(payload))
    save(dest/'spec.json',spec);save(dest/'scene.json',payload)
    save(dest/'capture-config.json',{'cameras':resolve(spec['cameras'],spec['parameters']),'landmarks':[{'id':o['id'],'world':landmark(spec,o)} for o in spec['observations']], 'scope':spec['quality_contract']['scope'],'connections':resolve(spec.get('connections',[]),spec['parameters'])})
    refdir=dest/'references';refdir.mkdir(exist_ok=True)
    for r in spec['references']:
        require(r['id'].replace('-','').replace('_','').isalnum(),'reference ID must be filename safe')
        source=p.parent/r['path'];shutil.copy2(source,refdir/(r['id']+source.suffix.lower()))
    if vehicle_config:
        cfg=read(vehicle_config)
        require(cfg.get('referenceBase')=='./references/','locked referenceBase must be ./references/')
        names={x['id']+Path(x['path']).suffix.lower() for x in spec['references']}
        required={v[3]+'.png' for v in cfg['views']}|{f'd0{i}-{n}.png' for i,n in enumerate(['front','lamp','roof','wheel','rear','door'],1)}
        require(required<=names,'Missing actual locked-page references: '+str(sorted(required-names)))
    manifest={'schema_version':1,'spec_sha256':sha(p),'diagnostic':diagnostic,'mode':mode,'quality_scope':spec['quality_contract']['scope'],'source_resources':{x['path']:x['sha256'] for x in spec['references']+spec['source_files']},'files':bundle_hashes(dest)}
    save(dest/'bundle-manifest.json',manifest);meta['builds'].append({'path':str(dest),'manifest_sha256':sha(dest/'bundle-manifest.json'),'spec_sha256':sha(p),'diagnostic':diagnostic});save(root/'project.json',meta)
    return {'built':str(dest),'mode':mode,'diagnostic':diagnostic,'gate':gate,'capture':'capture.mjs for generic review; locked page uses existing validate_locked_layout and functional tools'}

def fit_project(root,out,params,iterations,diagnostic=False):
    from reconstruction import fit
    root,meta,p=load(root);validate(root);gate_build(root,diagnostic);require(not Path(out).exists(),'Fit report exists')
    result=fit(read(p),params,iterations);result['input_file_sha256']=sha(p);result['diagnostic']=diagnostic;save(out,result)
    return {'fit_report':str(Path(out).resolve()),'input_file_sha256':sha(p),'next':'Inspect residuals and candidate captures. adopt only a suitable candidate; this is not a passing review.'}

def adopt(root,report,repair_record=None):
    root,meta,p=load(root);r=read(report);require(r.get('input_file_sha256')==sha(p),'fit report belongs to a different/stale spec')
    original,_=workflow.validate_spec(p);candidate=r['spec']
    require({k:v for k,v in candidate.items() if k!='parameters'}=={k:v for k,v in original.items() if k!='parameters'},'fit candidate changed non-parameter input')
    require(set(candidate['parameters'])==set(original['parameters']),'fit parameter set changed')
    for key,item in candidate['parameters'].items():
        require({k:v for k,v in item.items() if k!='value'}=={k:v for k,v in original['parameters'][key].items() if k!='value'},'fit changed parameter bounds/meaning')
    if original.get('production_contract'):
        require(repair_record, 'production adoption requires --repair-record')
        import repair_review
        repair_review.validate(repair_record)
        record=read(repair_record); base=Path(repair_record).resolve().parent
        require(record['decision']=='adopt' and record['before']['sha256']==sha(p), 'repair record not approved for current baseline')
        require(read(base/record['after']['spec_path'])==candidate, 'repair record does not match fit candidate')
    from scene_build import build
    build(candidate)
    archive=root/'history'/('spec-'+sha(p)+'.json');archive.parent.mkdir(exist_ok=True);shutil.copy2(p,archive);save(p,candidate)
    s=read(root/'state.json')
    try:
        if s['stages']:workflow.rebase(root/'state.json')
    except Exception:
        shutil.copy2(archive,p)
        raise
    return next_step(root)

def review_template(root,out):
    root,meta,p=load(root);spec,resources=workflow.validate_spec(p);stage=workflow.status(root/'state.json')['next']
    require(stage is not None,'all stages already reviewed');require(not Path(out).exists(),'review file exists')
    checks=[{'id':'stage:'+stage,'kind':'visual'}]+[c for c in spec['checks'] if c['required'] and c.get('stage','review')==stage]
    review={'stage':stage,'verdict':'pending','acceptance':'not_assessed','reviewer':'','rationale':'',
            'review_scope':spec['quality_contract']['scope'],'spec_sha256':sha(p),'resource_hashes':resources,'artifacts':[],
            'check_results':[{'id':c['id'],'verdict':'pending','method':'visual' if 'visual' in c['kind'] else c['kind'],'reviewer':'','scope':spec['quality_contract']['scope'],'artifact_paths':[]} for c in checks]}
    if spec.get('production_contract') and stage in ('body','review'):
        review['production_review']={'reviewer_role':'author','execution_reference':'','coverage_verdict':'pending','capture_report':'','features':[{'id':f['id'],'verdict':'pending','rationale':'','views':[]} for f in spec['production_contract']['features'] if f['importance']!='supporting']}
    save(out,review);return {'review_template':str(Path(out).resolve()),'stage':stage,'instruction':'Inspect actual artifacts, record hashes and judgments; template itself cannot pass.'}

def compare(root,capture_dir,view,reference_mask,alignment,out):
    from reference_evidence import diff
    root,meta,p=load(root);capture_dir=Path(capture_dir).resolve();report=read(capture_dir/'capture-report.json')
    require(report.get('spec_sha256')==sha(p),'capture belongs to a stale/different spec')
    matches=[c for c in report['captures'] if c['view']==view and c['pose']=='closed' and c['mode']=='mask']
    require(len(matches)==1,'exactly one closed mask capture required')
    c=matches[0];require('binary_mask_file' in c,'Use project.py capture to prepare explicit binary masks')
    candidate=capture_dir/c['binary_mask_file'];require(sha(candidate)==c['binary_mask_sha256'],'capture changed')
    # Explicit registration evidence remains required; never assert camera correctness from file existence.
    return diff(reference_mask,candidate,alignment,out)

def capture(root,bundle,out,playwright_module,browser=None):
    from PIL import Image
    root,meta,p=load(root);bundle=Path(bundle).resolve();manifest=read(bundle/'bundle-manifest.json')
    require(manifest['mode']=='generic-review','Capture the same Spec through generic-review; locked UI has its separate functional/layout checks')
    require(manifest['spec_sha256']==sha(p),'Build is stale; rebuild current Spec')
    cmd=['node',str(CORE/'scripts/capture.mjs'),'--bundle',str(bundle),'--out',str(Path(out).resolve()),'--playwright-module',str(Path(playwright_module).resolve())]
    if browser:cmd+=['--browser',browser]
    result=subprocess.run(cmd,capture_output=True,text=True)
    require(result.returncode==0,'Capture failed: '+result.stdout+result.stderr)
    out=Path(out);report=read(out/'capture-report.json');report['spec_sha256']=sha(p)
    for row in report['captures']:
        if row['mode']=='mask':
            with Image.open(out/row['file']) as im:
                im=im.convert('L');values=set(im.getdata())
                require(values<={0,255},'Mask render is not binary; do not silently threshold')
                name=Path(row['file']).stem+'-binary.png';im.save(out/name)
            row['binary_mask_file']=name;row['binary_mask_sha256']=sha(out/name)
    save(out/'capture-report.json',report);return {'captured':str(out.resolve()),'images':len(report['captures']),'scope':'Actual WebGL, unreviewed visual evidence'}

def checked_bundle(root,bundle):
    root,meta,p=load(root);bundle=Path(bundle).resolve();m=read(bundle/'bundle-manifest.json')
    require(m['spec_sha256']==sha(p),'bundle spec is stale')
    require(m['files']==bundle_hashes(bundle),'bundle files changed')
    return root,p,bundle,m

def asset_check(root,bundle,out,playwright_module,browser=None):
    root,p,bundle,m=checked_bundle(root,bundle)
    require(m['mode']=='generic-review','Asset audit requires generic review bundle of the same Spec')
    cmd=['node',str(CORE/'scripts/asset_check.mjs'),'--bundle',str(bundle),'--out',str(Path(out).resolve()),'--playwright-module',str(Path(playwright_module).resolve())]
    if browser:cmd+=['--browser',browser]
    proc=subprocess.run(cmd,capture_output=True,text=True)
    require(proc.returncode==0,'Asset audit failed: '+proc.stdout+proc.stderr)
    report=read(Path(out)/'asset-report.json');report['spec_file_sha256']=sha(p)
    save(Path(out)/'asset-report.json',report)
    return report

def exchange(root,bundle,out,blender=None):
    from asset_exchange import export_glb
    root,p,bundle,m=checked_bundle(root,bundle);dest=new_dir(out)
    payload=read(bundle/'scene.json');report=export_glb(payload,dest/'model.glb',resource_root=bundle)
    if blender:
        cmd=[blender,'--background','--python',str(CORE/'scripts/blender_asset_check.py'),'--','--glb',str(dest/'model.glb'),'--out',str(dest/'blender-report.json')]
        proc=subprocess.run(cmd,capture_output=True,text=True)
        require(proc.returncode==0,'Blender import check failed: '+proc.stdout+proc.stderr)
        require(read(dest/'blender-report.json')['passed'],'Blender import failed')
    receipt={'passed':True,'scope':'asset exchange; not visual acceptance','spec_file_sha256':sha(p),'bundle_manifest_sha256':sha(bundle/'bundle-manifest.json'),'blender_verified':bool(blender),'files':bundle_hashes(dest)}
    save(dest/'exchange-report.json',receipt)
    return receipt

def delivery_assets(p,bundle,asset_report,exchange_dir):
    spec=read(p);contract=spec.get('asset_contract')
    if not contract:return []
    require(asset_report,'Asset contract delivery requires --asset-report')
    audit_path=Path(asset_report).resolve();audit=read(audit_path)
    require(audit.get('passed') and audit.get('spec_file_sha256')==sha(p),'asset audit failed or stale')
    require(all(audit.get('performed',{}).get(op) for op in contract['required_operations']),'asset operations untested')
    require(audit.get('bundle_manifest_sha256')==sha(bundle/'bundle-manifest.json'),'audit bundle differs')
    files=[(audit_path,'asset-evidence/asset-report.json')]
    for item in audit.get('screenshots',[]):
        source=(audit_path.parent/item['file']).resolve()
        require(source.is_relative_to(audit_path.parent) and sha(source)==item['sha256'],'asset screenshot changed')
        files.append((source,'asset-evidence/'+item['file']))
    if any(t in contract['delivery_targets'] for t in ('glb','blender')):
        require(exchange_dir,'GLB/Blender target requires --exchange-dir');folder=Path(exchange_dir).resolve();receipt=read(folder/'exchange-report.json')
        require(receipt.get('passed') and receipt.get('spec_file_sha256')==sha(p),'exchange failed or stale')
        require(receipt.get('bundle_manifest_sha256')==sha(bundle/'bundle-manifest.json'),'exchange bundle differs')
        if 'blender' in contract['delivery_targets']:require(receipt.get('blender_verified'),'Blender target not actually imported')
        actual={k:v for k,v in bundle_hashes(folder).items() if k!='exchange-report.json'}
        require(actual==receipt['files'],'exchange files changed')
        files.extend((folder/name,'exchange/'+name) for name in actual)
        files.append((folder/'exchange-report.json','exchange/exchange-report.json'))
    return files

def export(root,bundle,out,asset_report=None,exchange_dir=None):
    root,meta,p=load(root);s=workflow.status(root/'state.json');require(not s['blocked'] and s['next'] is None,'Delivery review not passed')
    bundle=Path(bundle).resolve();m=read(bundle/'bundle-manifest.json')
    require(not m['diagnostic'],'diagnostic bundle cannot be delivered')
    require(m['spec_sha256']==sha(p),'bundle spec is stale')
    require(m['files']==bundle_hashes(bundle),'bundle files changed')
    assets=delivery_assets(p,bundle,asset_report,exchange_dir)
    dest=Path(out).resolve();require(not dest.exists(),'Output exists');shutil.copytree(bundle,dest)
    for source,name in assets:
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    state=read(root/'state.json');archived={}
    for stage,entry in state['stages'].items():
        ep=Path(entry['evidence_path']);e=read(ep);target=dest/'reviews'/stage/'review.json';target.parent.mkdir(parents=True);shutil.copy2(ep,target)
        artifacts=[]
        for a in e['artifacts']:
            source=(ep.parent/a['path']).resolve();name=sha(source)+'-'+source.name
            ap=target.parent/name;shutil.copy2(source,ap);artifacts.append({'original_path':a['path'],'archived':ap.relative_to(dest).as_posix(),'sha256':sha(ap)})
        archived[stage]={'review':target.relative_to(dest).as_posix(),'original_sha256':sha(ep),'artifacts':artifacts}
    save(dest/'delivery-evidence.json',{'state':state,'project':meta,'archived_reviews':archived,'source_bundle_manifest_sha256':sha(bundle/'bundle-manifest.json'),'scope':'Recorded passing evidence; no new visual judgment implied'})
    # Portable input map; preserve the exact reviewed Spec alongside the relocated rebuild copy.
    spec=read(p);rebuild=dest/'rebuild';rebuild.mkdir();save(rebuild/'reviewed-spec.json',spec)
    for folder in ('scripts','assets'):
        shutil.copytree(CORE/folder,rebuild/'toolchain'/folder,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(CORE/'LICENSE',rebuild/'toolchain/LICENSE')
    relocated={}
    for field in ('references','source_files'):
        for index,item in enumerate(spec[field]):
            old_path=item['path']
            source=(p.parent/item['path']).resolve();name='resources/'+field+'-'+str(index)+'-'+sha(source)+'-'+source.name
            if source.is_relative_to(CORE) and source.relative_to(CORE).parts[0] in ('scripts','assets'):
                item['path']='toolchain/'+source.relative_to(CORE).as_posix();relocated[old_path]=item['path'];continue
            target=rebuild/name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target);item['path']=name;relocated[old_path]=name
    if spec.get('reference_plan'):
        spec['reference_plan']=relocated[spec['reference_plan']]
        plan_path=rebuild/spec['reference_plan']; plan=read(plan_path)
        artifacts=list(plan.get('consistency_review',{}).get('artifacts',[]))
        artifacts += [m['artifact'] for c in plan.get('critical_components',[]) for m in c.get('manual_constraints',[])]
        artifacts += [x['approval']['evidence'] for x in plan.get('sources',[]) if x.get('approval',{}).get('evidence')]
        for a in artifacts:
            require(a['path'] in relocated,'reference evidence not source-hashed')
            a['path']=relocated[a['path']]
        save(plan_path,plan)
        for item in spec['source_files']:
            if item['path']==spec['reference_plan']:item['sha256']=sha(plan_path)
    if spec.get('construction_plan'):
        from construction_plan import digest as construction_digest
        spec['construction_plan']=relocated[spec['construction_plan']]
        receipt=spec['construction_receipt']
        receipt['baseline']['path']=relocated[receipt['baseline']['path']]
        plan_path=rebuild/spec['construction_plan']; plan=read(plan_path)
        for part in plan['parts']:
            for check in part['local_checks']:
                if check.get('evidence'):
                    check['evidence']['path']=relocated[check['evidence']['path']]
        save(plan_path,plan)
        receipt['plan_sha256']=construction_digest(plan)
        for item in spec['source_files']:
            if item['path']==spec['construction_plan']:item['sha256']=sha(plan_path)
    for material in spec['materials'].values():
        for texture in material.get('maps',{}).values():
            source=(p.parent/texture['path']).resolve();require(sha(source)==texture['sha256'],'texture changed')
            name='resources/texture-'+sha(source)+source.suffix.lower();shutil.copy2(source,rebuild/name);texture['path']=name
    save(rebuild/'spec.json',spec)
    shutil.copy2(root/'analysis.json',rebuild/'analysis.json')
    save(rebuild/'project.json',{'schema_version':1,'spec':'spec.json','state':'state.json','analysis':'analysis.json','builds':[],'history':[{'operation':'relocated-rebuild-copy','source_spec_sha256':sha(p)}], **{key:spec['quality_contract'][key] for key in ('reference_standard','production_standard') if key in spec.get('quality_contract',{})}})
    workflow.init(rebuild/'spec.json',rebuild/'state.json')
    (rebuild/'README.md').write_text('Rebuild in a new directory with: python3 toolchain/scripts/project.py build --project . --out ../NEW_PREVIEW --diagnostic\nRelocated inputs intentionally have a fresh unapproved state. Original passing evidence is preserved in the parent delivery.\n')
    m.update(source_bundle_manifest_sha256=sha(bundle/'bundle-manifest.json'),files=bundle_hashes(dest))
    save(dest/'bundle-manifest.json',m)
    return {'exported':str(dest)}

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('init');p.add_argument('--image',required=True);p.add_argument('--domain',choices=['generic','vehicle'],default='generic');p.add_argument('--out',required=True);p.add_argument('--object-class',choices=['generic','car','bicycle','motorcycle','toy']);p.add_argument('--use',dest='intended_use',choices=['display','configurator','disassembly','animation'],default='display');p.add_argument('--targets',nargs='+',choices=['threejs','glb','blender'])
    for cmd in ['next','validate','refresh-inputs','rebase','mark','build','fit','adopt','export','review-template','compare','capture','asset-check','exchange','production-check','repair-check','reference-check']:
        p=sub.add_parser(cmd);p.add_argument('--project',required=True)
        if cmd=='reference-check':p.add_argument('--stage',choices=['references','spec'],default='references')
        if cmd=='repair-check':p.add_argument('--record',required=True)
        if cmd=='mark':p.add_argument('--evidence',required=True)
        if cmd in ('build','fit','export','review-template','compare','capture','asset-check','exchange'):p.add_argument('--out',required=True)
        if cmd in ('build','fit'):p.add_argument('--diagnostic',action='store_true')
        if cmd=='build':p.add_argument('--vehicle-config');p.add_argument('--vehicle-skill')
        if cmd=='fit':p.add_argument('--parameters',nargs='+',required=True);p.add_argument('--iterations',type=int,default=80)
        if cmd=='adopt':p.add_argument('--report',required=True);p.add_argument('--repair-record')
        if cmd=='export':p.add_argument('--bundle',required=True);p.add_argument('--asset-report');p.add_argument('--exchange-dir')
        if cmd=='exchange':p.add_argument('--bundle',required=True);p.add_argument('--blender')
        if cmd in ('capture','asset-check'):p.add_argument('--bundle',required=True);p.add_argument('--playwright-module',required=True);p.add_argument('--browser')
        if cmd=='compare':
            for flag in ('capture-dir','view','reference-mask','alignment'):p.add_argument('--'+flag,required=True)
    a=ap.parse_args()
    try:
        if a.cmd=='init':r=init(a.image,a.domain,a.out,a.object_class,a.intended_use,a.targets)
        elif a.cmd=='next':r=next_step(a.project)
        elif a.cmd=='reference-check':
            from reference_set import validate as check_references
            _,meta,p=load(a.project)
            require(meta.get('reference_standard') != 1 or read(p).get('quality_contract',{}).get('reference_standard') == 1, 'project reference policy cannot be downgraded')
            r=check_references(p,a.stage)
        elif a.cmd=='production-check':
            import production_contract, production_checks
            _,_,p=load(a.project); spec,_=workflow.validate_spec(p)
            r={'contract':production_contract.validate(spec),'geometry':production_checks.evaluate(spec)}
            r['blocked']=not spec.get('production_contract') or not r['geometry']['passed']
        elif a.cmd=='repair-check':
            import repair_review
            _,_,p=load(a.project);r=repair_review.validate(a.record,p)
        elif a.cmd=='validate':r=validate(a.project)
        elif a.cmd=='refresh-inputs':r=refresh(a.project)
        elif a.cmd=='rebase':r=workflow.rebase(Path(a.project)/'state.json')
        elif a.cmd=='mark':r=workflow.mark(Path(a.project)/'state.json',a.evidence)
        elif a.cmd=='build':r=build_project(a.project,a.out,a.diagnostic,a.vehicle_config,a.vehicle_skill)
        elif a.cmd=='fit':r=fit_project(a.project,a.out,a.parameters,a.iterations,a.diagnostic)
        elif a.cmd=='adopt':r=adopt(a.project,a.report,a.repair_record)
        elif a.cmd=='review-template':r=review_template(a.project,a.out)
        elif a.cmd=='compare':r=compare(a.project,a.capture_dir,a.view,a.reference_mask,a.alignment,a.out)
        elif a.cmd=='capture':r=capture(a.project,a.bundle,a.out,a.playwright_module,a.browser)
        elif a.cmd=='asset-check':r=asset_check(a.project,a.bundle,a.out,a.playwright_module,a.browser)
        elif a.cmd=='exchange':r=exchange(a.project,a.bundle,a.out,a.blender)
        else:r=export(a.project,a.bundle,a.out,a.asset_report,a.exchange_dir)
        print(json.dumps(r,ensure_ascii=False,indent=2));return 1 if isinstance(r,dict) and r.get('blocked') else 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
