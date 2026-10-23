#!/usr/bin/env python3
"""Build/check the approved immutable UI; case data and geometry stay separate."""
import argparse,hashlib,json,re,shutil,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]/'assets/locked-configurator-v1'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def adapter_errors(source):
 """Conservative lexical check; labels/comments are data, never page access."""
 tokens=[];code=[];i=0
 while i<len(source):
  if source.startswith('//',i):
   end=source.find('\n',i);i=len(source) if end<0 else end;continue
  if source.startswith('/*',i):
   end=source.find('*/',i+2)
   if end<0:return ['Unterminated adapter comment']
   i=end+2;continue
  c=source[i]
  if c=='`':return ['Template literals require adapter review; interpolation is not silently ignored']
  if c in ('"',"'"):
   quote=c;j=i+1;value=''
   while j<len(source) and source[j]!=quote:
    if source[j]=='\\':
     if j+1>=len(source):return ['Unterminated adapter string']
     value+=source[j:j+2];j+=2
    else:value+=source[j];j+=1
   if j>=len(source):return ['Unterminated adapter string']
   tokens.append(('string',value));code.append(' ');i=j+1;continue
  m=re.match(r'[A-Za-z_$][A-Za-z0-9_$]*',source[i:])
  if m:
   value=m.group();tokens.append(('word',value));code.append(value+' ');i+=len(value)
  else:
   if not c.isspace():tokens.append(('punct',c))
   code.append(c);i+=1
 executable=''.join(code);errors=[]
 for pattern in [r'\bdocument\b',r'\bwindow\b',r'\bglobalThis\b',r'\beval\s*\(',r'\bFunction\s*\(',r'\bimport\s*\(',r'\bfetch\s*\(']:
  if re.search(pattern,executable):errors.append('Geometry adapter must not access page/inject code: '+pattern)
 for n,token in enumerate(tokens[:-1]):
  if token in [('word','from'),('word','import')] and tokens[n+1][0]=='string':
   mod=tokens[n+1][1]
   if mod!='three':errors.append('Unreviewed geometry module: '+mod)
 return errors

def check(root):
 lock=json.loads((BASE/'template-lock.json').read_text());errors=[]
 for name,expected in lock['immutable_files'].items():
  if not (BASE/name).is_file() or digest(BASE/name)!=expected:errors.append('Canonical template changed without approved version: '+name)
  if not (root/name).is_file() or digest(root/name)!=expected:errors.append('Immutable UI mismatch: '+name)
 if not (root/'template-lock.json').is_file() or (root/'template-lock.json').read_bytes()!=(BASE/'template-lock.json').read_bytes():errors.append('Case lock differs from canonical lock')
 try:
  c=json.loads((root/'vehicle.json').read_text())
  for k in ['asset','title','brand','edition','headline','subtitle','panelTitle','note','referenceBase']:assert isinstance(c[k],str) and c[k],k
  assert len(c['paints'])==6 and len(c['rims'])==3 and len(c['scenes'])==3 and len(c['views'])==8,'default option counts'
  for row in c['paints']:assert len(row)==2 and re.fullmatch(r'#[0-9a-fA-F]{6}',row[1]),'paint'
  for row in c['scenes']:assert len(row)==2 and re.fullmatch(r'#[0-9a-fA-F]{6}',row[1]),'scene'
  def plain(v):
   if isinstance(v,str):assert '<' not in v and '>' not in v,'HTML is not allowed in case values'
   elif isinstance(v,list):
    for i in v:plain(i)
   elif isinstance(v,dict):
    for i in v.values():plain(i)
  plain(c)
  assert set(c['partBindings'])=={'left','right','hood','trunk'},'part bindings'
 except Exception as e:errors.append('Invalid case data: '+str(e))
 try:
  source=(root/'model.js').read_text()
  errors.extend(adapter_errors(source))
 except Exception as e:errors.append('Missing geometry adapter: '+str(e))
 return {'passed':not errors,'template_id':lock['template_id'],'errors':errors,'scope':'static template/data/adapter check; browser visual and functional tests required separately'}
def main():
 a=argparse.ArgumentParser();a.add_argument('action',choices=['build','check']);a.add_argument('--out',required=True,type=Path);a.add_argument('--config',type=Path);a.add_argument('--model',type=Path);args=a.parse_args()
 if args.action=='build':
  if args.out.exists():sys.exit('Output exists: build to a new version directory')
  if not args.config or not args.model:sys.exit('--config and --model required')
  shutil.copytree(BASE,args.out);shutil.copy2(args.config,args.out/'vehicle.json');shutil.copy2(args.model,args.out/'model.js')
 result=check(args.out);print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['passed'] else 2)
if __name__=='__main__':main()
