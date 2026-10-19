#!/usr/bin/env python3
"""Project integration for frozen, explicitly reviewed repair sessions."""
import hashlib,json,os,shutil
from pathlib import Path
import model_repair

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def policy(spec_path):
 p=Path(spec_path).resolve();m=p.parent/'project.json';st=p.parent/'state.json'
 state=read(st)if st.is_file()else{}
 if not m.is_file():
  need(not state.get('repair_mode_version'),'repair project metadata missing while state declares policy')
  return None
 meta=read(m)
 version=meta.get('repair_mode_version');session=meta.get('repair_session')
 if state.get('repair_mode_version'):
  need(version==state['repair_mode_version'] and session==state.get('repair_session'),'repair policy removed or downgraded')
 if state.get('reference_admission_sha256'):
  need(meta.get('reference_admission_sha256')==state['reference_admission_sha256'],'frozen reference admission removed')
  spec=read(p);need(spec.get('quality_contract',{}).get('reference_standard')==2,'frozen reference admission changed; start a new scoped session')
  if sha(p.parent/spec['reference_plan'])!=state['reference_admission_sha256']:
   from reference_admission import validate_rebinding
   validate_rebinding(p,(p.parent/session).resolve(),meta.get('reference_binding_review'),state['reference_admission_sha256'])
 if version is None and session is None:return None
 need(version==1 and isinstance(session,str)and session,'invalid repair policy')
 f=(p.parent/session).resolve();need(f.is_file(),'repair session missing');return f

def attach(root,session):
 root=Path(root).resolve();f=Path(session).resolve();model_repair.status(f)
 from reference_admission import repair_preflight
 record=read(f);admission=repair_preflight(root/'spec.json',read(f.parent/record['contract']['path']))
 need(not record.get('diagnostic',False),'Diagnostic repair sessions cannot attach to production workflow')
 need(model_repair.check(f,root/'spec.json')['passed'],'attached repair session does not match current project')
 m=read(root/'project.json');s=read(root/'state.json');need(not m.get('repair_session'),'Project already has repair session; fork a new project to change frozen targets')
 rel=os.path.relpath(f,root);m.update(repair_mode_version=1,repair_session=rel,reference_admission_sha256=admission['plan_sha256']);s.update(repair_mode_version=1,repair_session=rel,reference_admission_sha256=admission['plan_sha256']);save(root/'project.json',m);save(root/'state.json',s);return {'attached':str(f),'repair_mode_version':1}
def start(root,contract,out):
 from reference_admission import repair_preflight
 root=Path(root).resolve();need(policy(root/'spec.json')is None,'Project already has repair policy');repair_preflight(root/'spec.json',read(contract));r=model_repair.init(root/'spec.json',contract,out);attach(root,r['session_path']);return r

def audit(root,out=None):
 p=Path(root).resolve()/'spec.json';f=policy(p);need(f,'Project has no repair session');return model_repair.check(f,p,out)
def accept(root,review):
 root=Path(root).resolve();p=root/'spec.json';f=policy(p);need(f,'Project has no repair session');review=Path(review).resolve();r=model_repair.validate_review(f,p,review);need(r['passed'],'Repair review failed: '+'; '.join(r['errors']))
 if read(p).get('quality_contract',{}).get('reference_standard')==2:
  from shape_acceptance import validate_review as shape_review
  spec=read(p);shape_review(p,spec,read(p.parent/spec['reference_plan']),read(review),review)
 m=read(root/'project.json');m['repair_review']={'path':os.path.relpath(review,root),'sha256':sha(review),'candidate_sha256':sha(p)};save(root/'project.json',m);return r

_CACHE={}
def gate(spec_path,review=False):
 p=Path(spec_path).resolve();f=policy(p)
 if f is None:return {'attached':False,'passed':True}
 # Numeric geometry cache is process-local and keyed by exact current resources.
 s=read(p);res=[]
 for x in s.get('references',[])+s.get('source_files',[]):
  q=(p.parent/x['path']).resolve();need(q.is_file()and sha(q)==x['sha256'],'stale repair resource: '+x['path']);res.append((str(q),x['sha256']))
 raw=read(f);contract=f.parent/raw['contract']['path'];source=Path(raw['contract']['source']);need(source.is_file()and sha(source)==raw['contract']['sha256'],'repair contract changed')
 snapshot=[(str((f.parent/v['snapshot']).resolve()),sha(f.parent/v['snapshot']))for v in raw.get('resources',[])+raw.get('context',[])]
 key=(str(p),sha(p),sha(f),sha(contract),sha(f.parent/raw['baseline']['path']),tuple(res),tuple(snapshot))
 if key not in _CACHE:
  r=model_repair.check(f,p);need(r['passed'],'Repair constraints failed: '+'; '.join(r['errors']));_CACHE[key]=r
 r=_CACHE[key]
 if review:
  entry=read(p.parent/'project.json').get('repair_review');need(isinstance(entry,dict),'Repair visual review is required before body acceptance/export')
  rp=(p.parent/entry['path']).resolve();need(rp.is_file()and sha(rp)==entry['sha256']and entry['candidate_sha256']==sha(p),'stale repair review')
  # Always validate evidence identity; geometry cache never substitutes visual evidence.
  reviewed=model_repair._validate_review_evidence(f,p,rp,r);need(reviewed['passed'],'Repair review failed: '+'; '.join(reviewed['errors']))
  if s.get('quality_contract',{}).get('reference_standard')==2:
   from shape_acceptance import validate_review as shape_review
   shape_review(p,s,read(p.parent/s['reference_plan']),read(rp),rp)
 return {'attached':True,**r}

def restore_project(root,out):
 """Fork immutable baseline+resources into a NEW rebuild project; no live mutation."""
 root=Path(root).resolve();f=policy(root/'spec.json');need(f,'No repair session');_,record,base,contract=model_repair._session(f);dest=Path(out).resolve();need(not dest.exists(),'Restore destination exists')
 oldbase=Path(record['baseline']['source']).parent
 frozen_analysis=next((f.parent/x['snapshot']for x in record.get('resources',[])+record.get('context',[])if Path(x['path']).resolve()==(oldbase/'analysis.json').resolve()),None)
 need(frozen_analysis is not None,'Frozen operational analysis missing; use an existing exported rebuild baseline')
 need(not base.get('construction_plan'),'Nested construction-plan relocation requires project export')
 dest.mkdir(parents=True)
 save(dest/'reviewed-baseline.json',base);mapping={}
 for i,item in enumerate(record.get('resources',[])):
  original=Path(item['path']);name='resources/'+str(i)+'-'+original.name;target=dest/name;target.parent.mkdir(exist_ok=True);shutil.copy2(f.parent/item['snapshot'],target);mapping[str(original)]=name
 oldbase=Path(record['baseline']['source']).parent
 for section in ['references','source_files']:
  for item in base.get(section,[]):item['path']=mapping[str((oldbase/item['path']).resolve())]
 if base.get('reference_plan'):
  base['reference_plan']=mapping[str((oldbase/base['reference_plan']).resolve())];pp=dest/base['reference_plan'];plan=read(pp)
  artifacts=list(plan.get('consistency_review',{}).get('artifacts',[]))+[c['artifact']for r in plan.get('critical_components',[])for c in r.get('manual_constraints',[])]+[x['approval']['evidence']for x in plan.get('sources',[])if x.get('approval',{}).get('evidence')]
  if plan.get('task',{}).get('baseline'):artifacts.append(plan['task']['baseline'])
  for a in artifacts:
   key=str((oldbase/a['path']).resolve());need(key in mapping,'Frozen reference evidence missing');a['path']=mapping[key]
  save(pp,plan)
  for item in base['source_files']:
   if item['path']==base['reference_plan']:item['sha256']=sha(pp)
 for material in base.get('materials',{}).values():
  for texture in material.get('maps',{}).values():
   q=str((oldbase/texture['path']).resolve());need(q in mapping,'Texture must be a frozen declared resource');texture['path']=mapping[q]
 save(dest/'spec.json',base)
 analysis=read(frozen_analysis);save(dest/'analysis.json',analysis)
 save(dest/'project.json',{'schema_version':1,'spec':'spec.json','state':'state.json','analysis':'analysis.json','builds':[],'history':[{'operation':'restored-frozen-repair-baseline','session_sha256':sha(f),'approvals':'cleared'}],**{k:base['quality_contract'][k]for k in ('reference_standard','production_standard','foundation_standard')if k in base.get('quality_contract',{})}})
 import workflow
 workflow.init(dest/'spec.json',dest/'state.json')
 import project
 project.validate(dest)
 return {'passed':True,'project':str(dest),'note':'Frozen model+resources forked. Original review remains historical; new state is unapproved. Current project and live page untouched.'}

def archive_evidence(root,destination):
 """Archive original evidence bytes and provenance; never transplant approvals."""
 root=Path(root).resolve();f=policy(root/'spec.json')
 if f is None:return None
 gate(root/'spec.json',True)
 dest=Path(destination).resolve();need(not dest.exists(),'Repair evidence archive exists');dest.mkdir(parents=True)
 inventory=[];seen=set()
 def add(path,role):
  p=Path(path).resolve();need(p.is_file(),'Repair archive input missing: '+str(p))
  if str(p)in seen:return
  seen.add(str(p));name='files/'+sha(p)+'-'+p.name;target=dest/name;target.parent.mkdir(exist_ok=True);shutil.copy2(p,target)
  inventory.append({'role':role,'original_path':str(p),'path':name,'sha256':sha(target)})
 record=read(f);add(f,'session');add(f.parent/record['baseline']['path'],'frozen-baseline');add(f.parent/record['contract']['path'],'frozen-contract')
 for item in record.get('resources',[])+record.get('context',[]):add(f.parent/item['snapshot'],'frozen-input')
 m=read(root/'project.json');review=(root/m['repair_review']['path']).resolve();add(review,'accepted-review')
 for result in read(review)['results']:
  for item in result.get('artifacts',[]):add(review.parent/item['path'],'review-artifact')
  if result.get('capture_report'):
   receipt=(review.parent/result['capture_report']).resolve();add(receipt,'capture-receipt');r=read(receipt)
   add(receipt.parent/r['capture_report_path'],'browser-capture-report');add(receipt.parent/r['bundle_manifest_path'],'source-bundle-manifest')
   for view in r['views']:
    for item in view['artifacts']:add(receipt.parent/item['path'],'captured-image')
 save(dest/'inventory.json',{'version':1,'candidate_sha256':sha(root/'spec.json'),'files':inventory,'scope':'Original evidence bytes and path map for historical audit. Paths inside original receipts are preserved; this archive does not transplant a current approval to relocated inputs.'})
 return {'path':str(dest),'files':len(inventory),'candidate_sha256':sha(root/'spec.json')}
