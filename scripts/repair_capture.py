#!/usr/bin/env python3
"""Fixed-camera repair evidence. Receipts verify identity, never visual quality."""
import argparse,hashlib,json,os
from pathlib import Path
from scene_build import resolve

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(v,msg):
 if not v:raise ValueError(msg)
def resources(spec_path):
 p=Path(spec_path).resolve();s=read(p);out={}
 for r in s.get('references',[])+s.get('source_files',[]):
  f=(p.parent/r['path']).resolve();require(f.is_file() and sha(f)==r['sha256'],'stale declared resource: '+r['path']);out[str(f)]=r['sha256']
 return out

def create(spec_path,bundle_path,capture_report_path,out):
 p,b,report,out=map(lambda x:Path(x).resolve(),[spec_path,bundle_path,capture_report_path,out]);require(not out.exists(),'Receipt output exists')
 s=read(p);m=read(b/'bundle-manifest.json');c=read(report);h=sha(p)
 require(m['spec_sha256']==h and c['spec_sha256']==h,'Capture/bundle Spec mismatch')
 require(c.get('passed') is True and not c.get('errors'),'Capture failed')
 require(c['bundle_manifest_sha256']==sha(b/'bundle-manifest.json'),'Capture manifest mismatch')
 require(m['source_resources']=={r['path']:r['sha256'] for r in s.get('references',[])+s.get('source_files',[])},'Source identity mismatch')
 cams=resolve(s['cameras'],s.get('parameters',{}));views={}
 for row in c['captures']:
  v=row['view'];require(v in cams and c['cameras'][v]==cams[v],'Capture camera mismatch')
  f=(report.parent/row['file']).resolve();require(f.is_relative_to(report.parent) and f.is_file() and sha(f)==row['sha256'],'Stale/missing capture')
  views.setdefault(v,{'id':v,'camera_sha256':digest(cams[v]),'artifacts':[]})['artifacts'].append({'path':os.path.relpath(f,out.parent),'sha256':row['sha256'],'mode':row['mode'],'pose':row.get('pose','closed')})
 require(bool(views),'Empty capture report')
 receipt={'version':1,'candidate_sha256':h,'bundle_manifest_sha256':sha(b/'bundle-manifest.json'),'bundle_manifest_path':os.path.relpath(b/'bundle-manifest.json',out.parent),'resource_hashes':resources(p),'capture_report_path':os.path.relpath(report,out.parent),'capture_report_sha256':sha(report),'views':list(views.values()),'scope':'Rendered source/camera/artifact identity only. Visual review is separate.'}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');validate_receipt(out,p);return receipt

def validate_receipt(receipt_path,candidate_path,views=None):
 p,q=Path(receipt_path).resolve(),Path(candidate_path).resolve();r,s=read(p),read(q)
 require(r.get('version')==1 and r.get('candidate_sha256')==sha(q),'Stale capture candidate')
 require(r.get('resource_hashes')==resources(q),'Stale capture resources')
 mf=(p.parent/r['bundle_manifest_path']).resolve();require(mf.is_file() and sha(mf)==r['bundle_manifest_sha256'],'Stale capture bundle manifest')
 m=read(mf);require(m['spec_sha256']==sha(q),'Bundle candidate differs')
 require(m.get('source_resources')=={x['path']:x['sha256']for x in s.get('references',[])+s.get('source_files',[])},'Bundle resources differ')
 for name,h in m['files'].items():
  f=(mf.parent/name).resolve();require(f.is_relative_to(mf.parent)and f.is_file()and sha(f)==h,'Stale capture bundle file: '+name)
 report=(p.parent/r['capture_report_path']).resolve();require(report.is_file()and sha(report)==r['capture_report_sha256'],'Stale capture report')
 c=read(report);require(c.get('passed')is True and not c.get('errors')and c['spec_sha256']==sha(q)and c['bundle_manifest_sha256']==sha(mf),'Invalid source capture report')
 cams=resolve(s['cameras'],s.get('parameters',{}));seen=set();artifacts=[]
 for v in r.get('views',[]):
  name=v['id'];require(name in cams and name not in seen,'Unknown/duplicate receipt camera');seen.add(name)
  require(v['camera_sha256']==digest(cams[name])and c['cameras'][name]==cams[name],'Receipt camera mismatch')
  require(bool(v.get('artifacts')),'Camera has no images')
  for a in v['artifacts']:
   f=(p.parent/a['path']).resolve();require(f.is_file()and sha(f)==a['sha256'],'Stale receipt image')
   matches=[row for row in c['captures']if row['view']==name and (report.parent/row['file']).resolve()==f and row['sha256']==a['sha256']and row['mode']==a.get('mode')and row.get('pose','closed')==a.get('pose')]
   require(len(matches)==1,'Receipt artifact not uniquely bound to rendered view');artifacts.append(str(f))
 require(seen and (views is None or set(views)<=seen),'Required views not captured')
 return {'passed':True,'views':sorted(seen),'artifacts':artifacts,'candidate_sha256':sha(q),'scope':r['scope']}

def main():
 a=argparse.ArgumentParser(description=__doc__);sub=a.add_subparsers(dest='cmd',required=True)
 c=sub.add_parser('create');c.add_argument('--spec',required=True);c.add_argument('--bundle',required=True);c.add_argument('--capture-report',required=True);c.add_argument('--out',required=True)
 c=sub.add_parser('validate');c.add_argument('--receipt',required=True);c.add_argument('--spec',required=True);c.add_argument('--views',nargs='+')
 x=a.parse_args()
 try:r=create(x.spec,x.bundle,x.capture_report,x.out)if x.cmd=='create'else validate_receipt(x.receipt,x.spec,x.views);print(json.dumps(r,ensure_ascii=False,indent=2));return 0
 except (ValueError,KeyError,OSError,TypeError)as e:print(json.dumps({'error':str(e)}));return 2
if __name__=='__main__':raise SystemExit(main())
