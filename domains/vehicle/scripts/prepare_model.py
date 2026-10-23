#!/usr/bin/env python3
"""Preserve GLB/.blend source and create an inspectable asset package. No semantic guesses."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
from asset_manifest import build,sha256,read_glb
ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--blender');p.add_argument('--timeout',type=int,default=180);a=p.parse_args()
 try:
  if not a.input.is_file() or a.input.suffix.lower() not in ('.glb','.blend'):raise ValueError('Input must be GLB or .blend')
  if a.input.suffix.lower()=='.glb':read_glb(a.input)
  blender=a.blender or shutil.which('blender') or ('/Applications/Blender.app/Contents/MacOS/Blender' if Path('/Applications/Blender.app/Contents/MacOS/Blender').is_file() else None)
  if a.input.suffix.lower()=='.blend' and not blender:raise ValueError('Blender required for .blend export')
  a.out.mkdir(parents=True,exist_ok=False);(a.out/'input').mkdir();source=a.out/'input'/('source'+a.input.suffix.lower());shutil.copy2(a.input,source);before=sha256(a.input)
  record={'schema_version':2,'source':str(a.input.resolve()),'source_sha256':before,'mode':'lossless_glb' if source.suffix=='.glb' else 'blender_export','state':'running','limitations':[]}
  try:
   if source.suffix=='.glb':shutil.copy2(source,a.out/'model.glb')
   else:
    cmd=[blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(ROOT/'prepare_model_blender.py'),'--','--input',str(source.resolve()),'--out',str(a.out.resolve()),'--source-dir',str(a.input.resolve().parent)]
    with (a.out/'blender.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout)
    if r.returncode:raise RuntimeError('Blender export failed; inspect blender.log')
    record['limitations']=['glTF supports a subset of Blender shader/animation features; review browser appearance, unsupported nodes and evaluated modifiers','Derived GLB indices must be reviewed afresh; do not reuse source indices by assumption']
   if sha256(a.input)!=before or sha256(source)!=before:raise RuntimeError('Source hash changed')
   manifest=build(a.out/'model.glb',a.out/'inventory');record.update(state='awaiting_review',model_sha256=manifest['asset']['sha256'],inventory='inventory/asset-manifest.json',original_preserved=True)
  except Exception as e:record.update(state='failed',error=str(e));raise
  finally:(a.out/'preparation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(record,ensure_ascii=False))
 except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
