"""Lossless presentation transport. Never decimates, quantizes or edits materials."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil

DEFAULT_BUDGET = 50_000_000
LAYOUT = 'delivery-layout.json'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encoded_json(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')

def local_file(root,name):
    root=Path(root).resolve();p=(root/name).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        raise ValueError('Missing or unsafe delivery resource: '+str(name))
    return p

def metadata(payload):
    keys=('id','parent','kind','role','selectable','material','material_slots','explode_vector')
    return {'schema_version':1,'spec_sha256':payload.get('spec_sha256'),
            'asset_contract':payload.get('asset_contract'),
            'components':[{**{k:c[k] for k in keys if k in c},'mesh_count':len(c.get('meshes',[]))} for c in payload['components']],
            'variants':payload.get('variants',[]),'actions':payload.get('actions',[])}

# This helper is also safe inside the locked geometry factory: no DOM, fetch,
# dynamic import or third-party module. Transport IO belongs to the generated
# top-level loader; locked factories embed compressed bytes instead of fetching.
JS_DECODE = '''async function decodeModelBytes(bytes,descriptor){
 if(!['gzip','identity'].includes(descriptor.encoding))throw Error('Unsupported model encoding');
 if(typeof crypto==='undefined'||!crypto.subtle)throw Error('Model integrity verification requires a secure context');
 if(typeof DecompressionStream!=='function'&&descriptor.encoding==='gzip')throw Error('Model gzip decompression is unavailable in this browser');
 const sha=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',value)),b=>b.toString(16).padStart(2,'0')).join('');
 if(bytes.byteLength!==descriptor.encoded_bytes||await sha(bytes)!==descriptor.encoded_sha256)throw Error('Model transport integrity mismatch');
 const raw=descriptor.encoding==='gzip'?await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer():bytes;
 if(raw.byteLength!==descriptor.decoded_bytes||await sha(raw)!==descriptor.decoded_sha256)throw Error('Decoded model integrity mismatch');
 return JSON.parse(new TextDecoder().decode(raw));
}
'''

def write_runtime(root,payload,runtime_text=None,locked=False,budget_bytes=DEFAULT_BUDGET,runtime_name='model.js'):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if Path(runtime_name).name!=runtime_name or Path(runtime_name).suffix not in ('.js','.mjs'):raise ValueError('Runtime entry must be a local JS module')
    if isinstance(budget_bytes,bool) or not isinstance(budget_bytes,int) or budget_bytes<=0:
        raise ValueError('delivery_profile.budget_bytes must be a positive integer')
    runtime_text=runtime_text or (Path(__file__).resolve().parents[1]/'assets/scene-runtime.mjs').read_text()
    raw=encoded_json(payload);packed=gzip.compress(raw,compresslevel=6,mtime=0)
    encoding='gzip' if len(packed)<len(raw) else 'identity';transport=packed if encoding=='gzip' else raw
    assert (gzip.decompress(transport) if encoding=='gzip' else transport)==raw
    descriptor={'encoding':encoding,'encoded_bytes':len(transport),'encoded_sha256':digest(transport),
                'decoded_bytes':len(raw),'decoded_sha256':digest(raw)}
    prefix="import * as THREE from 'three';\n"+JS_DECODE
    if locked:
        value=base64.b64encode(transport).decode('ascii')
        prefix+='const descriptor='+json.dumps(descriptor,separators=(',',':'))+';\n'
        prefix+='const data=await decodeModelBytes(Uint8Array.from(atob('+json.dumps(value)+'),c=>c.charCodeAt(0)),descriptor);\n'
        storage='embedded-base64';data_files=[]
    else:
        name='model-data.json.gz' if encoding=='gzip' else 'model-data.json'
        (root/name).write_bytes(transport);descriptor['path']=name
        prefix+='const descriptor='+json.dumps(descriptor,separators=(',',':'))+';\n'
        prefix+="const response=await fetch(new URL(descriptor.path,import.meta.url));if(!response.ok)throw Error('Model resource load failed: '+response.status);\n"
        prefix+='const data=await decodeModelBytes(await response.arrayBuffer(),descriptor);\n'
        storage='external';data_files=[name]
    meta=metadata(payload)
    prefix+='export const sceneMetadata='+encoded_json(meta).decode()+';\n'
    (root/runtime_name).write_text(prefix+runtime_text,encoding='utf-8')
    (root/'scene-meta.json').write_bytes(encoded_json(meta))
    # The complete payload remains in the project/rebuild sources, never in UI metadata.
    layout={'schema_version':1,'entry':runtime_name,'storage':storage,'data':descriptor,'metadata':'scene-meta.json',
            'runtime_files':[runtime_name,'scene-meta.json',*data_files],
            'budget_bytes':budget_bytes,'lossless':True}
    layout['runtime_hashes']={name:digest((root/name).read_bytes()) for name in layout['runtime_files']}
    (root/LAYOUT).write_text(json.dumps(layout,indent=2)+'\n')
    return report(root,payload=payload)

def read_payload(root):
    root=Path(root)
    if not(root/LAYOUT).exists():
        return json.loads(local_file(root,'scene.json').read_text())
    layout=json.loads(local_file(root,LAYOUT).read_text());d=layout['data']
    if layout.get('schema_version')!=1:raise ValueError('Unsupported delivery layout')
    for name in (layout.get('entry','model.js'),layout['metadata']):
        if digest(local_file(root,name).read_bytes())!=layout.get('runtime_hashes',{}).get(name):raise ValueError('Runtime resource hash mismatch: '+name)
    if layout['storage']=='external':
        transport=local_file(root,d['path']).read_bytes()
    elif layout['storage']=='embedded-base64':
        source=local_file(root,layout.get('entry','model.js')).read_text();marker='Uint8Array.from(atob('
        start=source.index(marker)+len(marker);literal,_=json.JSONDecoder().raw_decode(source[start:])
        transport=base64.b64decode(literal,validate=True)
    else:raise ValueError('Unsupported delivery storage')
    if len(transport)!=d['encoded_bytes'] or digest(transport)!=d['encoded_sha256']:
        raise ValueError('Model transport integrity mismatch')
    if d['encoding'] not in ('gzip','identity'):raise ValueError('Unsupported delivery encoding')
    try:raw=gzip.decompress(transport) if d['encoding']=='gzip' else transport
    except (OSError,EOFError) as exc:raise ValueError('Corrupt compressed model') from exc
    if len(raw)!=d['decoded_bytes'] or digest(raw)!=d['decoded_sha256']:
        raise ValueError('Decoded model integrity mismatch')
    return json.loads(raw)

def report(root,payload=None):
    root=Path(root);layout=json.loads(local_file(root,LAYOUT).read_text());decoded=read_payload(root)
    if payload is not None and payload!=decoded:raise ValueError('Packing input differs from decoded model')
    payload=decoded
    if metadata(payload)!=json.loads(local_file(root,layout['metadata']).read_text()):
        raise ValueError('Scene metadata differs from model')
    textures={}
    for material in payload.get('materials',{}).values():
        for texture in material.get('maps',{}).values():
            name=texture['path'];f=local_file(root,name);h=digest(f.read_bytes())
            if texture.get('sha256') and texture['sha256']!=h:raise ValueError('Texture hash mismatch: '+name)
            textures[name]={'bytes':f.stat().st_size,'sha256':h}
    names=set(layout['runtime_files'])|set(textures)|{LAYOUT}
    names|={f.name for f in root.iterdir() if f.is_file() and (f.suffix in ('.js','.mjs','.css','.html') or f.name in ('capture-config.json','vehicle.json','config.json'))}
    sizes={name:local_file(root,name).stat().st_size for name in sorted(names)}
    total=sum(sizes.values());budget=layout['budget_bytes']
    result={'schema_version':1,'lossless':True,'decoded_data_bytes':layout['data']['decoded_bytes'],
            'encoded_data_bytes':layout['data']['encoded_bytes'],'presentation_asset_bytes':total,
            'budget_bytes':budget,'within_budget':total<=budget,'files':sizes,'textures':textures,
            'triangles':sum(len(m['indices'])//3 for c in payload['components'] for m in c.get('meshes',[])),
            'scope':'model runtime, data, metadata and dedicated textures; excludes shared engine, reference images, engineering sources and native exchange assets',
            'warnings':[] if total<=budget else ['Lossless delivery exceeds budget; preserve quality and discuss alternatives. No automatic decimation.'],
            'runtime_validation':'not performed by this packing report; browser checks and visual comparison required'}
    (root/'delivery-size.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def pack_glb(path):
    path=Path(path);raw=path.read_bytes();packed=gzip.compress(raw,compresslevel=6,mtime=0)
    assert gzip.decompress(packed)==raw
    target=path.with_suffix(path.suffix+'.gz');target.write_bytes(packed)
    return {'source':path.name,'transport':target.name,'encoding':'gzip','decoded_sha256':digest(raw),
            'encoded_sha256':digest(packed),'decoded_bytes':len(raw),'encoded_bytes':len(packed),
            'scope':'lossless transport companion; canonical GLB retained for consumers/Blender'}

def migrate(source,out,budget_bytes=DEFAULT_BUDGET):
    source=Path(source).resolve();out=Path(out).resolve()
    if out.exists() or out.is_relative_to(source):raise ValueError('Migration requires a new independent output directory')
    manifest=json.loads(local_file(source,'bundle-manifest.json').read_text())
    if manifest.get('mode')!='generic-review':raise ValueError('Legacy migration only supports native generic-review bundles; other adapters need explicit integration')
    for name,h in manifest['files'].items():
        if digest(local_file(source,name).read_bytes())!=h:raise ValueError('Stale legacy bundle: '+name)
    text=local_file(source,'model.js').read_text();prefix="import * as THREE from 'three';\nconst data="
    if not text.startswith(prefix):raise ValueError('Unknown legacy emitter; do not guess or execute source')
    payload,end=json.JSONDecoder().raw_decode(text[len(prefix):]);tail=text[len(prefix)+end:]
    if not tail.startswith(';\nexport function buildScene'):raise ValueError('Unsupported legacy runtime layout')
    shutil.copytree(source,out)
    engineering=out/'engineering';engineering.mkdir(exist_ok=True)
    for name in ['scene.json','spec.json']:
        if(out/name).exists():shutil.move(out/name,engineering/name)
    result=write_runtime(out,payload,tail[2:],budget_bytes=budget_bytes)
    viewer=out/'review.js'
    if viewer.exists():
        s=viewer.read_text().replace("import {buildScene} from './model.js';","import {buildScene,sceneMetadata} from './model.js';")
        s=s.replace("const payload=await fetch('./scene.json').then(r=>r.json());",'const payload=sceneMetadata;')
        viewer.write_text(s)
    index=out/'index.html'
    if index.exists():index.write_text(index.read_text().replace('./spec.json','./engineering/spec.json'))
    manifest['delivery_layout']=LAYOUT;manifest['files']={f.relative_to(out).as_posix():digest(f.read_bytes()) for f in sorted(out.rglob('*')) if f.is_file() and f.name!='bundle-manifest.json'}
    (out/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('check');c.add_argument('--bundle',required=True)
    c=sub.add_parser('migrate');c.add_argument('--source',required=True);c.add_argument('--out',required=True);c.add_argument('--budget-bytes',type=int,default=DEFAULT_BUDGET)
    a=p.parse_args()
    try:result=report(a.bundle) if a.cmd=='check' else migrate(a.source,a.out,a.budget_bytes)
    except (ValueError,OSError,KeyError) as exc:p.exit(1,str(exc)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
