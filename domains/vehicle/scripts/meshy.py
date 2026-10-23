#!/usr/bin/env python3
"""One-shot, resumable Meshy API adapter. No automatic paid retries."""
import argparse, base64, hashlib, json, os, struct, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
API='https://api.meshy.ai/openapi/v1/multi-image-to-3d'
def write(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def read(path): return json.loads(path.read_text())
def request(url,body=None,key=None):
    headers={'Content-Type':'application/json'}
    if key: headers['Authorization']='Bearer '+key
    try:
        with urlopen(Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=60) as r:return json.load(r)
    except HTTPError as e: raise RuntimeError('HTTP '+str(e.code)+'; no retry performed') from None

def prepare(images,out,texture=False):
    if not 1<=len(images)<=4:raise ValueError('Meshy accepts 1–4 separate images')
    records=[]
    for value in images:
        p=Path(value).resolve();raw=p.read_bytes()
        if p.suffix.lower() not in ('.png','.jpg','.jpeg'):raise ValueError('Use PNG/JPEG')
        if not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff')):raise ValueError('Invalid image signature')
        records.append({'path':str(p),'sha256':hashlib.sha256(raw).hexdigest()})
    out.mkdir(parents=True,exist_ok=False)
    write(out/'request.json',{'images':records,'parameters':{'ai_model':'meshy-7','should_texture':texture,'enable_pbr':texture,'should_remesh':False,'image_enhancement':False,'target_formats':['glb']}})
    return {'prepared':str(out),'image_count':len(records),'network_called':False}

def submit(folder,execute):
    if not execute:raise ValueError('Review request.json and authorized budget, then use --execute')
    key=os.environ.get('MESHY_API_KEY')
    if not key:raise ValueError('MESHY_API_KEY is not configured')
    plan=read(folder/'request.json');payload=dict(plan['parameters']);payload['image_urls']=[]
    for item in plan['images']:
        p=Path(item['path']);raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Input changed since prepare; create a new candidate')
        mime='image/png' if p.suffix.lower()=='.png' else 'image/jpeg'
        payload['image_urls'].append('data:'+mime+';base64,'+base64.b64encode(raw).decode())
    # Atomic exclusive create. An uncertain POST must never be automatically repeated.
    marker=folder/'submission.json'
    with marker.open('x') as f:json.dump({'status':'SUBMISSION_UNCERTAIN','message':'Check provider before any retry'},f)
    result=request(API,payload,key);task=result.get('result')
    if not isinstance(task,str) or not task:raise ValueError('No task ID returned; reconcile provider dashboard')
    write(marker,{'task_id':task,'status':'SUBMITTED'});return {'task_id':task}

def status(folder):
    key=os.environ.get('MESHY_API_KEY')
    if not key:raise ValueError('MESHY_API_KEY is not configured')
    task=read(folder/'submission.json').get('task_id')
    if not task:raise ValueError('Uncertain submission: reconcile with provider, do not resubmit')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+',task):raise ValueError('Invalid task ID')
    data=request(API+'/'+task,key=key);write(folder/'status.json',data)
    return {k:data.get(k) for k in ('id','status','progress')}

def download(folder):
    data=read(folder/'status.json')
    if data.get('status')!='SUCCEEDED':raise ValueError('Task has not succeeded')
    url=data.get('model_urls',{}).get('glb','')
    if not url.startswith('https://'):raise ValueError('Missing HTTPS GLB URL; refresh status')
    dest=folder/'model.glb'
    if dest.exists():raise ValueError('Model already downloaded; not overwriting')
    # Do not send API credentials to the asset host or print signed URLs.
    temp=folder/'model.glb.part'
    try:
        with urlopen(url,timeout=60) as r,temp.open('wb') as f:
            while True:
                chunk=r.read(1024*1024)
                if not chunk:break
                f.write(chunk)
        with temp.open('rb') as f: header=f.read(12)
        if len(header)!=12 or header[:4]!=b'glTF':raise ValueError('Downloaded file is not GLB')
        _,version,size=struct.unpack('<4sII',header)
        if version!=2 or size!=temp.stat().st_size:raise ValueError('Incomplete or unsupported GLB')
        temp.replace(dest)
    except Exception:
        temp.unlink(missing_ok=True);raise
    return {'model':str(dest),'bytes':dest.stat().st_size}

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare');a.add_argument('--images',nargs='+',required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--texture',action='store_true')
    for verb in ('submit','status','download'):
        a=sub.add_parser(verb);a.add_argument('--candidate',type=Path,required=True)
        if verb=='submit':a.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if a.action=='prepare':result=prepare(a.images,a.out,a.texture)
    elif a.action=='submit':result=submit(a.candidate,a.execute)
    elif a.action=='status':result=status(a.candidate)
    else:result=download(a.candidate)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:
        # Network exceptions can contain signed URLs; emit only local safe messages.
        message=str(e) if isinstance(e,(ValueError,RuntimeError,FileExistsError)) else type(e).__name__
        print('ERROR: '+message,file=sys.stderr);sys.exit(1)
