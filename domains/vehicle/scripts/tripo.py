#!/usr/bin/env python3
"""Tripo v3 multiview adapter. Prepare offline; submit once; query/download separately."""
import argparse,hashlib,json,os,re,struct,sys,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from meshy import read,write
API='https://openapi.tripo3d.ai/v3'
def api(path,body=None,content_type='application/json'):
 key=os.environ.get('TRIPO_API_KEY')
 if not key:raise ValueError('TRIPO_API_KEY is not configured')
 if body is not None and not isinstance(body,bytes):body=json.dumps(body).encode()
 req=Request(API+path,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':content_type})
 try:
  with urlopen(req,timeout=60) as r:data=json.load(r)
 except HTTPError as e:raise RuntimeError('Tripo HTTP '+str(e.code)+'; no retry performed') from None
 if data.get('code')!=0 or not isinstance(data.get('data'),dict):raise RuntimeError('Tripo rejected request or returned an invalid envelope; no retry performed')
 return data['data']
def prepare(views,out,texture=False,parts=False):
 if 'front' not in views or not 2<=len(views)<=4:raise ValueError('Provide front and at least one of left/back/right')
 if set(views)-{'front','left','back','right'}:raise ValueError('Invalid view')
 if texture and parts:raise ValueError('Parts generation cannot be combined with textures/PBR')
 images=[]
 for angle in ('front','left','back','right'):
  if angle not in views:continue
  path=Path(views[angle]).resolve();raw=path.read_bytes()
  if len(raw)>20*1024*1024:raise ValueError('Image exceeds 20 MB')
  if path.suffix.lower() not in ('.png','.jpg','.jpeg'):raise ValueError('Upload supports PNG/JPEG')
  if not(raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff')):raise ValueError('Invalid image signature')
  images.append({'angle':angle,'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
 out.mkdir(parents=True,exist_ok=False)
 write(out/'request.json',{'provider':'tripo','api_version':'v3','images':images,'parameters':{'model':'v3.1-20260211','texture':texture,'pbr':texture,'generate_parts':parts,'geometry_quality':'standard'}})
 return {'candidate':str(out),'views':[i['angle'] for i in images],'network_called':False}
def submit(folder,execute=False):
 if not execute:raise ValueError('Review request and budget authorization, then pass --execute')
 if not os.environ.get('TRIPO_API_KEY'):raise ValueError('TRIPO_API_KEY is not configured')
 plan=read(folder/'request.json')
 if plan.get('provider')!='tripo':raise ValueError('Not a Tripo candidate')
 images=[]
 for item in plan['images']:
  path=Path(item['path']);raw=path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Image changed after prepare')
  images.append((item,path,raw))
 record={'provider':'tripo','status':'UPLOADING','uploads':{}}
 marker=folder/'submission.json'
 with marker.open('x') as f:json.dump(record,f)
 for item,path,raw in images:
  boundary='tripo_'+uuid.uuid4().hex;mime='image/png' if path.suffix.lower()=='.png' else 'image/jpeg'
  body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{item["angle"]}{path.suffix.lower()}"\r\nContent-Type: {mime}\r\n\r\n').encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
  token=api('/files',body,'multipart/form-data; boundary='+boundary).get('file_token')
  if not isinstance(token,str) or not token:raise ValueError('Upload did not return a file token')
  record['uploads'][item['angle']]=token;write(marker,record)
 payload=dict(plan['parameters']);payload['inputs']=[{i['angle']:{'file_token':record['uploads'][i['angle']]}} for i,_,_ in images]
 record['status']='SUBMISSION_UNCERTAIN';write(marker,record)
 result=api('/generation/multiview-to-model',payload);task=result.get('task_id')
 if not isinstance(task,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',task):raise ValueError('No valid task ID returned; reconcile with provider before retrying')
 record.update(task_id=task,status='SUBMITTED');write(marker,record);return {'task_id':task}
def status(folder):
 task=read(folder/'submission.json').get('task_id','')
 if not re.fullmatch(r'[A-Za-z0-9_-]+',task):raise ValueError('No valid task ID; reconcile provider before resubmission')
 data=api('/tasks/'+task)
 if data.get('task_id')!=task:raise ValueError('Task ID mismatch')
 write(folder/'status.json',data)
 return {k:data.get(k) for k in ('task_id','status','progress','credits_consumed','error_code')}
def download(folder):
 data=read(folder/'status.json');task=read(folder/'submission.json').get('task_id')
 if data.get('task_id')!=task or data.get('status')!='success':raise ValueError('Matching task has not succeeded')
 url=data.get('output',{}).get('model_url','')
 if not isinstance(url,str) or not url.startswith('https://'):raise ValueError('No HTTPS model URL; refresh status or inspect output format')
 dest=folder/'model.glb';temp=folder/'model.glb.part'
 if dest.exists():raise ValueError('Model already downloaded; not overwriting')
 owned_temp=False
 try:
  # The asset request is deliberately credential-free.
  with temp.open('xb') as f:
   owned_temp=True
   with urlopen(url,timeout=60) as r:
    while True:
     chunk=r.read(1024*1024)
     if not chunk:break
     f.write(chunk)
  with temp.open('rb') as f:header=f.read(12)
  if len(header)!=12:raise ValueError('Incomplete GLB')
  magic,version,size=struct.unpack('<4sII',header)
  if magic!=b'glTF' or version!=2 or size!=temp.stat().st_size:raise ValueError('Output is not a valid complete GLB; inspect provider output')
  temp.replace(dest)
 except Exception:
  if owned_temp:temp.unlink(missing_ok=True)
  raise
 return {'model':str(dest),'bytes':dest.stat().st_size,'credits_consumed':data.get('credits_consumed')}
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
 a=s.add_parser('prepare')
 for v in ('front','left','back','right'):a.add_argument('--'+v)
 a.add_argument('--out',type=Path,required=True);a.add_argument('--texture',action='store_true');a.add_argument('--parts',action='store_true')
 for verb in ('submit','status','download'):
  a=s.add_parser(verb);a.add_argument('--candidate',type=Path,required=True)
  if verb=='submit':a.add_argument('--execute',action='store_true')
 a=p.parse_args()
 if a.action=='prepare':result=prepare({v:getattr(a,v) for v in ('front','left','back','right') if getattr(a,v)},a.out,a.texture,a.parts)
 elif a.action=='submit':result=submit(a.candidate,a.execute)
 elif a.action=='status':result=status(a.candidate)
 else:result=download(a.candidate)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('ERROR: '+(str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__),file=sys.stderr);sys.exit(1)
