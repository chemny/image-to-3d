#!/usr/bin/env python3
"""Lossless GLB inventory, embedded texture extraction and explicit role binding.
No name/color based semantic segmentation. Uses glTF indices before Blender renames.
"""
import argparse, base64, hashlib, json, struct
from pathlib import Path

def sha256(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def read_glb(path):
    raw=Path(path).read_bytes()
    if len(raw)<20: raise ValueError('Truncated GLB')
    magic,version,length=struct.unpack_from('<III',raw)
    if magic!=0x46546c67 or version!=2 or length!=len(raw): raise ValueError('Expected valid GLB v2 length/header')
    offset=12; document=None; binary=b''
    while offset<len(raw):
        if offset+8>len(raw): raise ValueError('Truncated chunk header')
        size,kind=struct.unpack_from('<II',raw,offset); offset+=8
        if size%4 or offset+size>len(raw): raise ValueError('Invalid GLB chunk')
        chunk=raw[offset:offset+size]; offset+=size
        if kind==0x4e4f534a:
            if document is not None: raise ValueError('Duplicate JSON chunk')
            document=json.loads(chunk)
        elif kind==0x004e4942: binary=chunk
    if not document or document.get('asset',{}).get('version')!='2.0': raise ValueError('Missing glTF 2 JSON')
    # Portable template supports self-contained GLB, not remote/sidecar resources.
    for row in document.get('buffers',[])+document.get('images',[]):
        uri=row.get('uri','')
        if uri and not uri.startswith('data:'): raise ValueError('External resource: '+uri+'; pack into GLB first')
    return document,binary

def build(path,out,roles=None):
    doc,binary=read_glb(path); digest=sha256(path)
    bindings=[]; active=set()
    def walk(index):
        if index in active: raise ValueError('Cyclic scene nodes')
        if index in reachable:return
        if not 0<=index<len(doc.get('nodes',[])):raise ValueError('Invalid scene node')
        active.add(index);reachable.add(index)
        for child in doc['nodes'][index].get('children',[]): walk(child)
        active.remove(index)
    reachable=set()
    for i in doc.get('scenes',[{}])[doc.get('scene',0)].get('nodes',[]): walk(i)
    for ni,node in enumerate(doc.get('nodes',[])):
        if 'mesh' not in node: continue
        mi=node['mesh']
        for pi,primitive in enumerate(doc['meshes'][mi]['primitives']):
            acc=doc.get('accessors',[])
            positions=acc[primitive['attributes']['POSITION']]
            count=acc[primitive['indices']]['count'] if 'indices' in primitive else positions['count']
            mode=primitive.get('mode',4)
            bindings.append({'id':f'n{ni}:p{pi}','node_index':ni,'node_name':node.get('name',''),
                'mesh_index':mi,'primitive_index':pi,'material_index':primitive.get('material'),
                'vertices':positions['count'],'triangles':count//3 if mode==4 else None,'mode':mode,
                'bounds_min':positions.get('min'),'bounds_max':positions.get('max'),
                'uv_sets':[k for k in primitive['attributes'] if k.startswith('TEXCOORD_')],
                'active_scene':ni in reachable,'role':'unassigned','evidence':None})
    by_id={r['id']:r for r in bindings}
    roles=roles or {}
    for key,value in roles.get('roles',{}).items():
        if key not in by_id: raise ValueError('Unknown role target: '+key)
        if not value.get('role') or not value.get('evidence'): raise ValueError('Role needs evidence: '+key)
        by_id[key].update(role=value['role'],evidence=value['evidence'])
    protected=roles.get('protected_features',[])
    for feature in protected:
        if not feature.get('targets') or any(t not in by_id for t in feature['targets']): raise ValueError('Invalid protected feature targets')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);(out/'textures').mkdir()
    images=[]
    for i,im in enumerate(doc.get('images',[])):
        if 'bufferView' in im:
            view=doc['bufferViews'][im['bufferView']]
            if view.get('buffer',0)!=0:raise ValueError('Unsupported image buffer')
            start=view.get('byteOffset',0);data=binary[start:start+view['byteLength']]
            if len(data)!=view['byteLength']:raise ValueError('Truncated embedded image')
        else:
            uri=im['uri'];head,body=uri.split(',',1)
            if ';base64' not in head:raise ValueError('Expected base64 image')
            data=base64.b64decode(body)
        mime=im.get('mimeType') or im.get('uri','').split(';')[0].removeprefix('data:')
        suffix={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','image/ktx2':'.ktx2'}.get(mime,'.bin')
        rel=f'textures/image-{i}{suffix}';(out/rel).write_bytes(data)
        images.append({'index':i,'name':im.get('name'),'mime_type':mime,'path':rel,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
    manifest={'schema_version':2,'asset':{'id':roles.get('asset_id','glb-'+digest[:16]),'version':digest,'sha256':digest,'source':str(Path(path).resolve()),'bytes':Path(path).stat().st_size,'license':roles.get('license','not_supplied')},
        'coordinates':{'up':'+Y','units':'glTF meters; authored scale not verified','forward':roles.get('forward','unknown')},
        'nodes':doc.get('nodes',[]),'bindings':bindings,
        'materials':[{'index':i,'definition':m,'users':[b['id'] for b in bindings if b['material_index']==i]} for i,m in enumerate(doc.get('materials',[]))],
        'textures':doc.get('textures',[]),'images':images,'animations':[{'index':i,'name':v.get('name'),'channels':len(v.get('channels',[]))} for i,v in enumerate(doc.get('animations',[]))],
        'extensions_required':doc.get('extensionsRequired',[]),'protected_features':protected,
        'runtime_dependencies':roles.get('runtime_dependencies',[]),'limitations':roles.get('limitations',[]),
        'verdicts':{'structure':'inventoried','geometry':'not_reviewed','materials':'not_reviewed','visual':'not_reviewed'}}
    (out/'asset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (out/'gltf-source.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
    return manifest

def validate(manifest,config,model):
    if manifest.get('schema_version')!=2 or config.get('schema_version')!=2:raise ValueError('Expected schema v2')
    asset=manifest['asset']; identity=config['asset']
    if sha256(model)!=asset['sha256'] or identity.get('id')!=asset['id'] or identity.get('version')!=asset['version']:raise ValueError('Asset identity/version mismatch')
    targets={b['id']:b for b in manifest['bindings']}
    paint=config.get('paintTargets',[])
    if len(set(paint))!=len(paint):raise ValueError('Duplicate paint target')
    for t in paint:
        if t not in targets or targets[t]['role']!='paint' or not targets[t]['active_scene']:raise ValueError('Paint target is not reviewed active paint: '+t)
    protected={t for f in manifest['protected_features'] if not f.get('recolorable',False) for t in f['targets']}
    if protected.intersection(paint):raise ValueError('Paint overlaps protected fixed feature')
    for collection in ('paints','scenes','views','rims','interiors'):
        ids=[v['id'] for v in config.get(collection,[])]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate option id: '+collection)
    if manifest['runtime_dependencies']!=config.get('runtimeDependencies',[]):raise ValueError('Runtime dependencies not declared consistently')
    return {'verdict':'passed','scope':'asset hash, explicit roles and fixed feature protection; not visual fidelity','paint_targets':paint,'unassigned_targets':[b['id'] for b in targets.values() if b['role']=='unassigned']}

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('inspect');a.add_argument('--input',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--roles',type=Path)
    a=s.add_parser('validate');a.add_argument('--manifest',type=Path,required=True);a.add_argument('--config',type=Path,required=True);a.add_argument('--model',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.action=='inspect':
            m=build(a.input,a.out,json.loads(a.roles.read_text()) if a.roles else None);print(json.dumps({'asset':m['asset'],'bindings':len(m['bindings']),'images':len(m['images'])},ensure_ascii=False))
        else: print(json.dumps(validate(json.loads(a.manifest.read_text()),json.loads(a.config.read_text()),a.model),ensure_ascii=False))
    except (ValueError,KeyError,IndexError,OSError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
