#!/usr/bin/env python3
"""Isolated image/model tasks and offline web bundles; never rewrites original assets."""
import argparse,json,shutil,hashlib
from pathlib import Path
from asset_manifest import sha256,read_glb
ROOT=Path(__file__).resolve().parents[1]
IMAGE_EXT={'.png','.jpg','.jpeg','.webp'}
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
 a=s.add_parser('init');a.add_argument('--image',type=Path,action='append',default=[]);a.add_argument('--model',type=Path);a.add_argument('--out',type=Path,required=True);a.add_argument('--name',default='车辆选配器')
 a=s.add_parser('reference');a.add_argument('--project',type=Path,required=True);a.add_argument('--image',type=Path,required=True);a.add_argument('--angle',required=True);a.add_argument('--origin',choices=['real','generated','inferred','user_supplied'],required=True);a.add_argument('--note',required=True)
 a=s.add_parser('web');a.add_argument('--out',type=Path,required=True);a.add_argument('--model',type=Path);a.add_argument('--manifest',type=Path);a.add_argument('--config',type=Path);a.add_argument('--runtime-dir',type=Path);a.add_argument('--resource-dir',type=Path)
 a=p.parse_args()
 try:
  if a.action=='init':
   if not a.image and not a.model:p.error('Supply --model and/or one or more --image')
   for image in a.image:
    if not image.is_file() or image.suffix.lower() not in IMAGE_EXT:p.error('Missing or unsupported image: '+str(image))
   if a.model:
    if not a.model.is_file() or a.model.suffix.lower() not in ('.glb','.blend'):p.error('Use GLB or .blend; convert other formats with their actual importer')
    if a.model.suffix.lower()=='.glb':read_glb(a.model)
   a.out.mkdir(parents=True,exist_ok=False)
   for d in ('input','references','candidates','review','master'):(a.out/d).mkdir()
   inputs=[];refs=[]
   for i,image in enumerate(a.image):
    rel=Path('input')/(('source' if i==0 else 'source-'+str(i+1))+image.suffix.lower());shutil.copy2(image,a.out/rel)
    row={'path':str(rel),'sha256':sha256(image),'original_path':str(image.resolve()),'kind':'image'};inputs.append(row)
    refs.append({**row,'angle':'unknown','origin':'user_supplied','note':'User input; angle, configuration consistency and license require review','consistency':'not_reviewed'})
   modelpath=None
   if a.model:
    modelpath=Path('input')/('source'+a.model.suffix.lower());shutil.copy2(a.model,a.out/modelpath)
    inputs.append({'path':str(modelpath),'sha256':sha256(a.model),'original_path':str(a.model.resolve()),'kind':'model'})
   data={'schema_version':2,'name':a.name,'input_kind':'model' if a.model else 'images','inputs':inputs,'source':refs[0]['path'] if refs else str(modelpath),'source_model':str(modelpath) if modelpath else None,'references':refs,'candidates':[],'selected_candidate':None,'stages':{k:'pending' for k in ('multiview','candidates','geometry_review','blender','interior','web','validation')},'limits':{'max_paid_candidates':2,'max_repair_rounds':None},'limitations':['Image hidden regions are inferred'] if a.image else []}
   write(a.out/'project.json',data)
  elif a.action=='reference':
   if not a.image.is_file() or a.image.suffix.lower() not in IMAGE_EXT:p.error('Missing or unsupported image')
   data=json.loads((a.project/'project.json').read_text());idx=len(data.get('references',[]))+1;rel=Path('references')/(f'ref-{idx}'+a.image.suffix.lower())
   dest=a.project/rel
   if dest.exists():p.error('Reference destination already exists')
   shutil.copy2(a.image,dest);data.setdefault('references',[]).append({'path':str(rel),'sha256':sha256(dest),'angle':a.angle,'origin':a.origin,'note':a.note,'consistency':'not_reviewed'});write(a.project/'project.json',data)
  else:
   if a.model:read_glb(a.model)
   manifest=json.loads(a.manifest.read_text()) if a.manifest else None
   config=json.loads(a.config.read_text()) if a.config else json.loads((ROOT/'assets/web/config.json').read_text())
   if a.model:
    digest=sha256(a.model);config['asset']={'id':manifest['asset']['id'] if manifest else 'glb-'+digest[:16],'version':digest}
    config['model']='./model.glb'
   if manifest and not a.model:p.error('--manifest requires --model')
   if manifest:
    from asset_manifest import validate
    validate(manifest,config,a.model)
   dependencies=config.get('runtimeDependencies',[])
   resource_files={}
   if dependencies and not a.runtime_dir:p.error('Runtime dependencies require --runtime-dir')
   for dependency in dependencies:
    files=dependency.get('files',[])
    if not files or dependency['module'].removeprefix('./') not in [r['path'] for r in files]:p.error('Runtime module must be in hashed file list')
    for row in files:
     rel=Path(row['path'])
     if rel.is_absolute() or '..' in rel.parts or str(rel) in ('asset-manifest.json','bundle-manifest.json','model.glb') or (ROOT/'assets/web'/rel).exists() or str(rel).startswith('vendor/'):p.error('Unsafe runtime path')
     src=(a.runtime_dir/rel).resolve()
     if not src.is_relative_to(a.runtime_dir.resolve()) or sha256(src)!=row['sha256']:p.error('Runtime dependency missing/hash mismatch')
     resource_files[rel]=src
   for item in config.get('interiors',[])+config.get('referenceGallery',[]):
    panorama=item.get('panorama',item.get('image',''))
    if not isinstance(panorama,str) or not panorama.startswith('./'):p.error('Image resource must be a local ./ path')
    rel=Path(panorama.removeprefix('./'))
    if rel.is_absolute() or '..' in rel.parts or rel.suffix.lower() not in IMAGE_EXT or (ROOT/'assets/web'/rel).exists():p.error('Unsafe image resource path')
    if not a.resource_dir:p.error('Image resources require --resource-dir')
    src=(a.resource_dir/rel).resolve()
    if not src.is_relative_to(a.resource_dir.resolve()) or not src.is_file():p.error('Missing image resource: '+panorama)
    if rel in resource_files and sha256(resource_files[rel])!=sha256(src):p.error('Conflicting resource: '+panorama)
    resource_files[rel]=src
   config['bundleManifest']='./bundle-manifest.json'
   resource_hashes={str(rel):sha256(src) for rel,src in resource_files.items()}
   shutil.copytree(ROOT/'assets/web',a.out)
   for rel,src in resource_files.items():
    (a.out/rel).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,a.out/rel)
   if a.model:shutil.copy2(a.model,a.out/'model.glb')
   if manifest:
    # Texture extraction is for review; GLB stays byte-identical with embedded images.
    shutil.copy2(a.manifest,a.out/'asset-manifest.json');config['assetManifest']='./asset-manifest.json'
   config['asset'].pop('config_version',None)
   config['asset']['config_version']=hashlib.sha256(json.dumps({'config':config,'manifest_sha256':sha256(a.manifest) if a.manifest else None,'resource_sha256':resource_hashes},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
   write(a.out/'config.json',config)
   bundle={'schema_version':1,'asset':config['asset'],'files':{str(f.relative_to(a.out)):sha256(f) for f in a.out.rglob('*') if f.is_file()}}
   write(a.out/'bundle-manifest.json',bundle)
  print(a.out.resolve() if hasattr(a,'out') else a.project.resolve())
 except (ValueError,KeyError,OSError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
