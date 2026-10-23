#!/usr/bin/env python3
"""Rebuild the accepted page from bundled final assets, never historical iterations."""
from pathlib import Path
import argparse,subprocess,sys
case=Path(__file__).resolve().parent
root=case.parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists():p.error('Output must be a new directory')
f=case/'final'
if not (f/'model.glb').is_file():p.error('Reference assets are optional and not included in the public core. Obtain the authorized case archive or use scripts/project.py with your own model.')
subprocess.run([sys.executable,str(root/'scripts/project.py'),'web','--out',str(a.out.resolve()),'--model',str(f/'model.glb'),'--manifest',str(f/'asset-manifest.json'),'--config',str(f/'config.json'),'--runtime-dir',str(f),'--resource-dir',str(f)],check=True)
