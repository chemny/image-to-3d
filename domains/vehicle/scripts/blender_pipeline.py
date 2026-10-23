#!/usr/bin/env python3
"""Versioned Blender jobs and evidence gates. Does not generate vehicle geometry itself."""
import argparse, base64, hashlib, html, json, shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def read(p):return json.loads(Path(p).read_text())
def write(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_artifacts(folder):
 result=read(folder/'result.json')
 for file,key in [('model.blend','blend_sha256'),('model.glb','glb_sha256')]:
  if digest(folder/file)!=result[key]:raise ValueError('Artifact changed after stage: '+file)
 return result

def run(a):
 params=read(a.params)
 if params.get('schema_version')!=1:raise ValueError('Expected schema_version 1')
 if a.depends and a.repair_of:raise ValueError('Choose depends or repair-of')
 if a.repair_of:
  verify_artifacts(a.repair_of)
  previous=read(a.repair_of/'review.json')
  if previous.get('result_sha256')!=digest(a.repair_of/'result.json'):raise ValueError('Repair review is stale')
  if previous.get('verdict')!='needs_revision':raise ValueError('Repair requires a needs_revision review')
  count=read(a.repair_of/'job.json').get('repair_count',0)+1
  budget=params.get('max_repair_rounds')
  if type(budget) is not int or budget<1:raise ValueError('Set a positive max_repair_rounds in task parameters before repair')
  previous_params=a.repair_of/'parameters.json'
  if previous_params.is_file():
   frozen=read(previous_params).get('max_repair_rounds')
   if frozen is not None and frozen!=budget:raise ValueError('Repair budget changed after the chain started')
  if count>budget:raise ValueError('Repair budget exhausted; report unresolved issues')
 else:count=0
 if a.depends:
  verify_artifacts(a.depends)
  prior=read(a.depends/'review.json')
  if prior.get('verdict')!='passed' or prior.get('result_sha256')!=digest(a.depends/'result.json'):raise ValueError('Dependency has no current passed review')
 parent=a.depends or a.repair_of
 if parent:
  result=read(parent/'result.json')
  if not a.input or digest(a.input) not in (result['blend_sha256'],result['glb_sha256']):raise ValueError('Input does not match reviewed parent artifact')
 if not a.script.is_file():raise ValueError('Stage script missing')
 if a.input and not a.input.is_file():raise ValueError('Input model missing')
 blender=a.blender or shutil.which('blender')
 if not blender and Path('/Applications/Blender.app/Contents/MacOS/Blender').is_file():blender='/Applications/Blender.app/Contents/MacOS/Blender'
 if not blender:raise ValueError('Blender executable not found')
 a.out.mkdir(parents=True,exist_ok=False)
 # Freeze exact inputs for reproducible stage runs.
 shutil.copy2(a.params,a.out/'parameters.json');shutil.copy2(a.script,a.out/'stage.py')
 manifest={'repair_count':count,'repair_of':str(a.repair_of.resolve()) if a.repair_of else None,'stage':a.stage,'state':'running','started_at':time.time(),'input':str(a.input.resolve()) if a.input else None,'input_sha256':digest(a.input) if a.input else None,'script_sha256':digest(a.script),'parameters_sha256':digest(a.params),'depends':str(a.depends.resolve()) if a.depends else None}
 write(a.out/'job.json',manifest)
 cmd=[blender,'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'blender_stage.py'),'--','--job',str(a.out.resolve())]
 try:
  with (a.out/'blender.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout)
  if r.returncode:raise RuntimeError('Blender failed; see blender.log')
  if a.input and digest(a.input)!=manifest['input_sha256']:raise RuntimeError('Source model changed during stage')
  result=read(a.out/'result.json')
  if not (a.out/'model.blend').is_file() or not (a.out/'model.glb').is_file() or result['mesh_count']==0:raise RuntimeError('Missing stage artifacts')
  manifest['state']='awaiting_review'
 except Exception as e:
  manifest.update(state='failed',error=str(e));raise
 finally:
  manifest['ended_at']=time.time();write(a.out/'job.json',manifest)
 return manifest

def review(a):
 job=read(a.job/'job.json')
 if job['state'] not in ('awaiting_review','passed','needs_revision'):raise ValueError('Job has not completed')
 evidence=[str(p.resolve()) for p in a.evidence]
 if not evidence or any(not Path(p).is_file() for p in evidence):raise ValueError('Existing visual evidence is required')
 result=verify_artifacts(a.job)
 if a.verdict=='passed' and result.get('checks',{}).get('missing_required_nodes'):raise ValueError('Required nodes missing')
 record={'verdict':a.verdict,'scope':a.scope,'reason':a.reason,'issues':a.issue,'evidence':evidence,'result_sha256':digest(a.job/'result.json'),'reviewed_at':time.time()}
 write(a.job/'review.json',record);job['state']=a.verdict;write(a.job/'job.json',job);return record

def compare(a):
 # HTML overlays preserve image bytes; no automatic camera registration or fidelity score.
 def uri(path):
  mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}.get(path.suffix.lower())
  if not mime:raise ValueError('Comparison supports PNG/JPEG')
  return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()
 ref,model=uri(a.reference),uri(a.render)
 page='''<!doctype html><meta charset="utf-8"><title>车辆模型对照</title><style>body{background:#191d23;color:#eee;font:16px system-ui;margin:32px}main{max-width:1200px;margin:auto}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}img{width:100%;display:block}.overlay{position:relative;background:#333;overflow:hidden}.overlay img{width:100%;height:100%;object-fit:contain}.overlay .model{position:absolute;inset:0;opacity:.5}label{display:inline-block;margin:12px}input{width:180px}p{color:#bbc4d0}</style><main><h1>车辆模型对照</h1><p>NOTE</p><div class="pair"><section><h3>参考 / 修改前</h3><img src="REF"></section><section><h3>当前渲染</h3><img src="MODEL"></section></div><h3>叠图检查</h3><p>只有相机、裁切及比例对齐后，重合情况才有意义。手动对齐仅用于观察，不计算高保真分数。</p><label>透明度 <input id="alpha" type="range" min="0" max="1" step=".01" value=".5"></label><label>缩放 <input id="scale" type="range" min=".2" max="3" step=".01" value="1"></label><label>水平 <input id="dx" type="range" min="-50" max="50" step=".1" value="0"></label><label>垂直 <input id="dy" type="range" min="-50" max="50" step=".1" value="0"></label><div class="overlay"><img src="REF"><img class="model" src="MODEL"></div></main><script>const el=document.querySelector('.model');function update(){el.style.opacity=document.querySelector('#alpha').value;el.style.transform=`translate(${document.querySelector('#dx').value}%,${document.querySelector('#dy').value}%) scale(${document.querySelector('#scale').value})`;}document.querySelectorAll('input').forEach(i=>i.addEventListener('input',update));</script>'''
 page=page.replace('NOTE',html.escape(a.note)).replace('REF',ref).replace('MODEL',model)
 with a.out.open('x') as f:f.write(page)
 return {'comparison':str(a.out.resolve())}

def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
 a=s.add_parser('run');a.add_argument('--params',type=Path,required=True);a.add_argument('--script',type=Path,required=True);a.add_argument('--input',type=Path);a.add_argument('--out',type=Path,required=True);a.add_argument('--stage',required=True);a.add_argument('--depends',type=Path);a.add_argument('--repair-of',type=Path);a.add_argument('--blender');a.add_argument('--timeout',type=int,default=600)
 a=s.add_parser('review');a.add_argument('--job',type=Path,required=True);a.add_argument('--verdict',choices=['passed','needs_revision'],required=True);a.add_argument('--scope',required=True);a.add_argument('--reason',required=True);a.add_argument('--evidence',type=Path,nargs='+',required=True);a.add_argument('--issue',action='append',default=[])
 a=s.add_parser('compare');a.add_argument('--reference',type=Path,required=True);a.add_argument('--render',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--note',default='请核对相机与参考来源；未知部位仍为推断。')
 a=p.parse_args();print(json.dumps(globals()[a.action](a),ensure_ascii=False))
if __name__=='__main__':main()
