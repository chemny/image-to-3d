#!/usr/bin/env python3
"""Freeze manually reviewed image regions without modifying source image pixels."""
import argparse, hashlib, html, json, math, shutil, struct
from pathlib import Path

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dimensions(p):
    data=p.read_bytes()
    if data[:8]==b'\x89PNG\r\n\x1a\n' and data[12:16]==b'IHDR': return list(struct.unpack('>II',data[16:24]))
    if data[:2]==b'\xff\xd8':
        i=2
        while i<len(data):
            if data[i]!=255: raise ValueError('Malformed JPEG')
            while data[i]==255:i+=1
            marker=data[i];i+=1
            if marker in [0xd8,0xd9] or 0xd0<=marker<=0xd7:continue
            n=struct.unpack('>H',data[i:i+2])[0]
            if marker in [0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf]:
                height,width=struct.unpack('>HH',data[i+3:i+7]);return [width,height]
            if n<2:break
            i+=n
    raise ValueError('Use readable PNG/JPEG references')

def build(spec_path,out):
    if out.exists():raise ValueError('Use a new reference-pack directory')
    spec=json.loads(spec_path.read_text())
    if spec.get('schema_version')!=1:raise ValueError('Expected schema_version 1')
    sources={};views=[];configurations={}
    for row in spec.get('sources',[]):
        key=row['id'];p=(spec_path.parent/row['path']).resolve()
        if key in sources or not key or row.get('origin') not in ['real','generated','inferred','user_supplied']:raise ValueError('Unique source ID and provenance required')
        if sha(p)!=row.get('sha256'):raise ValueError('Stale source hash: '+key)
        sources[key]={**row,'original_path':str(p),'size':dimensions(p),'path':'sources/'+key+p.suffix.lower()}
        if not key.replace('-','').replace('_','').isalnum():raise ValueError('Unsafe source ID')
    for row in spec.get('views',[]):
        source=sources[row['source_id']];w,h=source['size'];roi=row.get('roi',[0,0,w,h])
        if len(roi)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or int(v)!=v for v in roi):raise ValueError('Integer ROI required')
        x,y,rw,rh=roi
        if x<0 or y<0 or rw<=0 or rh<=0 or x+rw>w or y+rh>h:raise ValueError('ROI outside image')
        if row.get('consistency') not in ['accepted','excluded','needs_review'] or not row.get('evidence'):raise ValueError('Explicit review and evidence required')
        if row.get('projection') not in ['perspective','approx_orthographic','unknown']:raise ValueError('Declare projection uncertainty')
        if row.get('consistency')=='accepted':
            group=row.get('configuration_group')
            if not group:raise ValueError('Accepted views require configuration_group')
            known=configurations.setdefault(group,{})
            for feature,observation in row.get('configuration',{}).items():
                value=observation['value']
                if not observation.get('evidence'):raise ValueError('Feature observation needs evidence')
                if feature in known and known[feature]!=value:raise ValueError('Conflicting accepted views: '+feature)
                known[feature]=value
        views.append({**row,'roi':roi,'source_sha256':source['sha256'],'source_origin':source['origin']})
    if not views or len({v['id'] for v in views})!=len(views):raise ValueError('Unique reviewed views required')
    out.mkdir(parents=True);(out/'sources').mkdir()
    for source in sources.values():shutil.copy2(source['original_path'],out/source['path'])
    pack={'schema_version':1,'spec_sha256':sha(spec_path),'sources':list(sources.values()),'views':views,'limitations':['ROIs and consistency are manual declarations, not automatic recognition','Board labels do not prove original photograph provenance','Approximate orthographic views are not engineering measurements']}
    (out/'reference-pack.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n');shutil.copy2(spec_path,out/'spec.json')
    cards=[]
    for v in views:
        source=sources[v['source_id']];w,h=source['size'];x,y,rw,rh=v['roi']
        cards.append(f'<article><h2>{html.escape(v["id"])}</h2><p>{html.escape(v["consistency"])} · {html.escape(v["source_origin"])} · {html.escape(v["projection"])}</p><svg viewBox="{x} {y} {rw} {rh}" role="img"><image width="{w}" height="{h}" href="{html.escape(source["path"],quote=True)}"/></svg><p>{html.escape(v["evidence"])}</p></article>')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>参考图逐视角复核</title><style>body{font:16px/1.6 system-ui;background:#f3f2ec;color:#222;margin:24px}main{max-width:1300px;margin:auto}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,350px),1fr));gap:20px}article{background:white;padding:20px;border-radius:12px}svg{width:100%;display:block}h2{font-size:21px}</style><main><h1>参考图逐视角复核</h1><p>保留原图字节；分区只改变显示范围。accepted 表示允许用于当前任务，不是来源或形状真实性认证。</p><section>'+''.join(cards)+'</section></main>')
    return pack

def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:pack=build(a.spec,a.out);print(json.dumps({'views':len(pack['views']),'out':str(a.out.resolve())}))
    except (OSError,ValueError,KeyError,struct.error) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
