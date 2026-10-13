#!/usr/bin/env python3
"""Dependency-free, strict scene_build payload -> glTF 2.0 binary exchange."""
import argparse
import copy
import hashlib
import json
import math
import re
import struct
from pathlib import Path

LIMITATIONS = [
    'Variant options are all present; extras.default_visible is metadata, not standard glTF visibility. Generic importers may display every option.',
    'Selection, explode controls, variant switching and runtime scripts are metadata, not executable glTF behavior.',
    'Actions are independent one-second pivot rotation clips; runtime easing is not exported.',
    'No inferred UVs, texture baking, custom shaders or automatic texture channel packing.',
    'Coordinates are +Y up / +Z forward; Blender imports into its +Z-up convention.',
]


def digest(b):
    return hashlib.sha256(b).hexdigest()


def vec(v, n=3):
    if not isinstance(v, list) or len(v) != n or any(type(x) not in (int, float) or not math.isfinite(x) for x in v):
        raise ValueError('finite vector required')
    return v


def quat(r):
    x,y,z=[v/2 for v in vec(r)]
    a,b,c=math.cos(x),math.cos(y),math.cos(z)
    d,e,f=math.sin(x),math.sin(y),math.sin(z)
    return [d*b*c+a*e*f,a*e*c-d*b*f,a*b*f+d*e*c,a*b*c-d*e*f]


def color(s):
    if not isinstance(s,str) or not re.fullmatch('#[0-9a-fA-F]{6}',s):
        raise ValueError('hex color required')
    rgb=[int(s[i:i+2],16)/255 for i in (1,3,5)]
    return [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]


def scalar(m,k,default):
    v=m.get(k,default)
    if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1:
        raise ValueError('invalid scalar '+k)
    return v


def camera_rotation(position,target,up):
    def unit(v):
        n=math.sqrt(sum(x*x for x in v))
        if n<1e-10: raise ValueError('degenerate camera direction/up')
        return [x/n for x in v]
    def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    z=unit([a-b for a,b in zip(position,target)]);x=unit(cross(up,z));y=cross(z,x)
    # Column-major affine transform: cameras look along local -Z.
    return [x[0],x[1],x[2],0,y[0],y[1],y[2],0,z[0],z[1],z[2],0,*position,1]


def encode_glb(payload, resource_root):
    if payload.get('schema_version')!=1:raise ValueError('unsupported payload version')
    blob=bytearray();g={'asset':{'version':'2.0','generator':'image-three-core asset_exchange'},'scene':0,'scenes':[{'nodes':[]}],
        'nodes':[],'meshes':[],'materials':[],'bufferViews':[],'accessors':[],
        'extras':{'spec_sha256':payload.get('spec_sha256'),'asset_contract':payload.get('asset_contract'),
                  'variants':payload.get('_variant_metadata',payload.get('variants',[])),'variant_mode':payload.get('_variant_mode','all-options-inspection'),'vehicle_bindings':payload.get('_vehicle_metadata',payload.get('vehicle_bindings')),'limitations':payload.get('_limitations',LIMITATIONS)}}
    resources=[];root=Path(resource_root).resolve();extensions=set()
    def view(raw,target=None):
        while len(blob)%4:blob.append(0)
        b={'buffer':0,'byteOffset':len(blob),'byteLength':len(raw)}
        if target:b['target']=target
        blob.extend(raw);g['bufferViews'].append(b);return len(g['bufferViews'])-1
    def accessor(values,width,indices=False,bounds=False):
        if not values or len(values)%width:raise ValueError('invalid accessor length')
        if indices:
            if any(type(x)!=int or x<0 for x in values):raise ValueError('invalid indices')
        else:vec(values,len(values))
        a={'bufferView':view(struct.pack('<'+('I' if indices else 'f')*len(values),*values),34963 if indices else 34962),
           'componentType':5125 if indices else 5126,'count':len(values)//width,'type':{1:'SCALAR',2:'VEC2',3:'VEC3',4:'VEC4'}[width]}
        if bounds:a.update(min=[min(values[i::width]) for i in range(width)],max=[max(values[i::width]) for i in range(width)])
        g['accessors'].append(a);return len(g['accessors'])-1
    textures={}
    def texture(desc,key):
        if not isinstance(desc,dict) or set(desc)-{'path','sha256','color_space'}:raise ValueError('unsupported texture descriptor')
        expected_space='srgb' if key in ('map','emissiveMap') else 'linear'
        if desc.get('color_space')!=expected_space:raise ValueError('texture color_space mismatch: '+key)
        p=(root/desc['path']).resolve()
        if not p.is_relative_to(root):raise ValueError('texture escapes resource root')
        raw=p.read_bytes();sha=digest(raw)
        if desc.get('sha256')!=sha:raise ValueError('texture SHA-256 mismatch: '+desc['path'])
        mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
        if mime is None:raise ValueError('only PNG/JPEG images supported')
        if sha not in textures:
            images=g.setdefault('images',[]);images.append({'bufferView':view(raw),'mimeType':mime,'name':p.name,'extras':{'sha256':sha,'source_path':desc['path']}})
            ts=g.setdefault('textures',[]);ts.append({'source':len(images)-1});textures[sha]=len(ts)-1
            resources.append({'path':desc['path'],'sha256':sha,'bytes':len(raw)})
        return {'index':textures[sha]}
    material_ids={}
    for mid,m in payload['materials'].items():
        allowed={'color','roughness','metalness','opacity','clearcoat','transmission','emissive','emissiveIntensity','maps','source'}
        if set(m)-allowed:raise ValueError('unsupported material properties: '+str(sorted(set(m)-allowed)))
        pbr={'baseColorFactor':color(m['color'])+[scalar(m,'opacity',1)],'metallicFactor':scalar(m,'metalness',0),'roughnessFactor':scalar(m,'roughness',1)}
        out={'name':mid,'pbrMetallicRoughness':pbr,'extras':{'material_id':mid,'source':m.get('source')}}
        if pbr['baseColorFactor'][3]<1:out['alphaMode']='BLEND'
        if 'emissive' in m:out['emissiveFactor']=color(m['emissive'])
        strength=m.get('emissiveIntensity',1)
        if type(strength) not in (int,float) or not math.isfinite(strength) or strength<0:raise ValueError('invalid emissive intensity')
        if strength!=1:
            ext='KHR_materials_emissive_strength';extensions.add(ext);out.setdefault('extensions',{})[ext]={'emissiveStrength':strength}
        for k,ext,factor in [('clearcoat','KHR_materials_clearcoat','clearcoatFactor'),('transmission','KHR_materials_transmission','transmissionFactor')]:
            if scalar(m,k,0):extensions.add(ext);out.setdefault('extensions',{})[ext]={factor:m[k]}
        maps=m.get('maps',{})
        if set(maps)-{'map','normalMap','roughnessMap','metalnessMap','aoMap','emissiveMap'}:raise ValueError('unsupported texture map')
        rm,mm=maps.get('roughnessMap'),maps.get('metalnessMap')
        if rm or mm:
            if not rm or not mm or rm!=mm:raise ValueError('roughnessMap and metalnessMap must use identical packed G/B image descriptors')
            pbr['metallicRoughnessTexture']=texture(rm,'roughnessMap')
        for k,target in [('map','baseColorTexture'),('normalMap','normalTexture'),('aoMap','occlusionTexture'),('emissiveMap','emissiveTexture')]:
            if k in maps:(pbr if k=='map' else out)[target]=texture(maps[k],k)
        material_ids[mid]=len(g['materials']);g['materials'].append(out)
    components=payload['components'];ids={c['id']:c for c in components}
    if len(ids)!=len(components):raise ValueError('duplicate component id')
    memberships={}
    variants=list(payload.get('variants',[]))
    if not variants and payload.get('vehicle_bindings',{}):
        wheels=payload['vehicle_bindings'].get('wheels',[])
        if wheels:variants=[{'id':'legacy-wheels','options':{str(i):v for i,v in enumerate(wheels)},'default':'0'}]
    g['extras']['variants']=payload.get('_variant_metadata',variants)
    for variant in variants:
        if variant['default'] not in variant['options']:raise ValueError('missing variant default')
        for option,roots in variant['options'].items():
            if not roots:raise ValueError('empty variant option')
            for cid in roots:
                if cid not in ids or cid in memberships:raise ValueError('invalid variant component')
                memberships[cid]={'set':variant['id'],'option':option,'default_visible':option==variant['default']}
    if len({a['id'] for a in payload.get('actions',[])})!=len(payload.get('actions',[])):raise ValueError('duplicate action IDs')
    actions={a['component_id']:a for a in payload.get('actions',[])}
    if len(actions)!=len(payload.get('actions',[])) or any(k not in ids for k in actions):raise ValueError('invalid action components')
    nodes={};attachment={};pivots={};used_materials=set();world_points=[]
    for c in components:
        cid=c['id'];seen={cid};parent=c.get('parent')
        while parent is not None:
            if parent not in ids or parent in seen:raise ValueError('invalid hierarchy')
            seen.add(parent);parent=ids[parent].get('parent')
        if 'scale' in c or 'matrix' in c:raise ValueError('payload scale/matrix unsupported')
        membership=[memberships[k] for k in seen if k in memberships]
        extras={k:c[k] for k in ('role','kind','selectable','explode_vector','material_slots') if k in c}
        extras.update(component_id=cid,default_visible=all(v['default_visible'] for v in membership),variant_memberships=membership)
        node={'name':cid,'translation':vec(c.get('position',[0,0,0]))[:],'rotation':quat(c.get('rotation',[0,0,0])),'extras':extras,'children':[]}
        nodes[cid]=len(g['nodes']);g['nodes'].append(node);attachment[cid]=nodes[cid]
        a=actions.get(cid)
        if a:
            if a['axis'] not in ('x','y','z') or type(a['angle']) not in (int,float) or not math.isfinite(a['angle']) or not a['angle']:raise ValueError('invalid action')
            pivot=vec(a['pivot']);node['translation']=[x-y for x,y in zip(node['translation'],pivot)]
            pivots[a['id']]=len(g['nodes']);attachment[cid]=len(g['nodes'])
            g['nodes'].append({'name':'pivot:'+a['id'],'translation':pivot,'children':[nodes[cid]],'extras':{'action_id':a['id']}})
        if c.get('kind','part')=='assembly' and c['meshes']:raise ValueError('assembly has geometry')
        for mi,mesh in enumerate(c['meshes']):
            if set(mesh)-{'id','positions','normals','indices','uvs','topology_mesh','topology_report','material','material_slot'}:raise ValueError('unsupported mesh attributes')
            pos=mesh['positions'];n=len(pos)//3;normals=mesh['normals'];indices=mesh['indices']
            if len(pos)%3 or len(normals)!=len(pos) or len(indices)%3 or any(type(i)!=int or not 0<=i<n for i in indices):raise ValueError('invalid mesh')
            for i in range(0,len(pos),3):
                point=pos[i:i+3];cursor=cid
                while cursor is not None:
                    parent_component=ids[cursor];r=parent_component.get('rotation',[0,0,0]);x,y,z=point
                    for axis,angle in ((2,r[2]),(1,r[1]),(0,r[0])):
                        co,si=math.cos(angle),math.sin(angle)
                        if axis==2:x,y=co*x-si*y,si*x+co*y
                        elif axis==1:x,z=co*x+si*z,-si*x+co*z
                        else:y,z=co*y-si*z,si*y+co*z
                    point=[v+t for v,t in zip((x,y,z),parent_component.get('position',[0,0,0]))];cursor=parent_component.get('parent')
                world_points.append(point)
            material=mesh.get('material',c.get('material'))
            if 'material_slot' in mesh:material=c.get('material_slots',{})[mesh['material_slot']]
            slots=c.get('material_slots',{})
            if any(v not in material_ids for v in slots.values()):raise ValueError('material slots reference unknown material')
            # Slots are authorized alternatives, not simultaneous polygon assignments.
            # The canonical primary material is exported; alternatives remain metadata.
            if material not in material_ids:raise ValueError('unknown material')
            used_materials.add(material)
            attr={'POSITION':accessor(pos,3,bounds=True),'NORMAL':accessor(normals,3)}
            if 'uvs' in mesh:
                if len(mesh['uvs'])!=n*2:raise ValueError('UV vertex count mismatch')
                attr['TEXCOORD_0']=accessor(mesh['uvs'],2)
            elif payload['materials'][material].get('maps'):raise ValueError('textured geometry requires supplied UVs')
            meshidx=len(g['meshes']);g['meshes'].append({'name':cid+':'+str(mesh.get('id',mi)),'primitives':[{'attributes':attr,'indices':accessor(indices,1,True),'material':material_ids[material]}]})
            node['children'].append(len(g['nodes']));g['nodes'].append({'name':cid+':mesh:'+str(mi),'mesh':meshidx,'extras':{'owner_component_id':cid,'default_visible':extras['default_visible']}})
    for c in components:
        parent=c.get('parent');(g['nodes'][nodes[parent]]['children'] if parent else g['scenes'][0]['nodes']).append(attachment[c['id']])
    for cid,a in actions.items():
        # Subdivide large rotations so quaternion interpolation cannot take a shorter path.
        count=max(1,math.ceil(abs(a['angle'])/(math.pi/2)));times=[i/count for i in range(count+1)];rotations=[]
        for t in times:
            q=[0.,0.,0.,math.cos(a['angle']*t/2)];q['xyz'.index(a['axis'])]=math.sin(a['angle']*t/2);rotations.extend(q)
        inp=accessor(times,1,bounds=True);out=accessor(rotations,4)
        # Animation buffers must not use vertex/index targets.
        for idx in (inp,out):g['bufferViews'][g['accessors'][idx]['bufferView']].pop('target',None)
        g.setdefault('animations',[]).append({'name':a['id'],'samplers':[{'input':inp,'output':out,'interpolation':'LINEAR'}],
            'channels':[{'sampler':0,'target':{'node':pivots[a['id']],'path':'rotation'}}],'extras':{'component_id':cid,'angle':a['angle'],'axis':a['axis']}})
    for name,c in payload.get('cameras',{}).items():
        if set(c)-{'type','width','height','position','target','up','fov_y_deg','ortho_height','near','far'}:raise ValueError('unsupported camera fields')
        if not all(type(c.get(k)) in (int,float) and math.isfinite(c[k]) and c[k]>0 for k in ('width','height')):raise ValueError('positive camera dimensions required')
        kind=c.get('type','perspective');near=c.get('near',.01);far=c.get('far',1000)
        if not 0<near<far:raise ValueError('invalid camera clipping')
        if kind=='perspective':
            fov=c['fov_y_deg'];aspect=c['width']/c['height']
            if not 0<fov<180 or aspect<=0:raise ValueError('invalid perspective camera')
            camera={'name':name,'type':kind,'perspective':{'yfov':math.radians(fov),'aspectRatio':aspect,'znear':near,'zfar':far}}
        elif kind=='orthographic':
            if all(k in c for k in ('left','right','top','bottom')):
                if abs(c['left']+c['right'])>1e-9 or abs(c['top']+c['bottom'])>1e-9:raise ValueError('off-center orthographic camera unsupported')
                xmag=c['right'];ymag=c['top']
            else:
                ymag=c['ortho_height']/2;xmag=ymag*c['width']/c['height']
            if min(xmag,ymag)<=0:raise ValueError('invalid orthographic extent')
            camera={'name':name,'type':kind,'orthographic':{'xmag':xmag,'ymag':ymag,'znear':near,'zfar':far}}
        else:raise ValueError('unsupported camera type')
        cams=g.setdefault('cameras',[]);cams.append(camera);g['scenes'][0]['nodes'].append(len(g['nodes']))
        g['nodes'].append({'name':'camera:'+name,'camera':len(cams)-1,'matrix':camera_rotation(vec(c['position']),vec(c.get('target',[0,0,0])),vec(c.get('up',[0,1,0])))})
    if extensions:g['extensionsUsed']=sorted(extensions);g['extensionsRequired']=sorted(extensions)
    while len(blob)%4:blob.append(0)
    g['buffers']=[{'byteLength':len(blob)}]
    js=json.dumps(g,separators=(',',':'),allow_nan=False).encode();js+=b' '*((-len(js))%4)
    raw=struct.pack('<III',0x46546c67,2,12+8+len(js)+8+len(blob))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(blob),0x004e4942)+blob
    manifest={'passed':True,'glb_sha256':digest(raw),'spec_sha256':payload.get('spec_sha256'),'component_ids':list(ids),'mesh_count':len(g['meshes']),
        'material_ids':list(material_ids),'used_material_ids':sorted(used_materials),'world_bounds_gltf':{'min':[min(v[i] for v in world_points) for i in range(3)],'max':[max(v[i] for v in world_points) for i in range(3)]} if world_points else None,'camera_count':len(g.get('cameras',[])),'animation_names':[a['name'] for a in g.get('animations',[])],
        'resources':resources,'textured_material_ids':sorted(k for k in used_materials if payload['materials'][k].get('maps')),'limitations':LIMITATIONS}
    return raw,manifest


def export_glb(payload, out=None, resource_root='.', include_all_variants=False):
    """Write new files and return manifest; without out return (bytes, manifest)."""
    original=payload
    payload=copy.deepcopy(payload)
    if payload.get('asset_contract') and payload['asset_contract'].get('version')!=1:raise ValueError('unsupported asset contract version')
    if (payload.get('asset_contract') or {}).get('version')==1:
        if any(not isinstance(m.get('source'),dict) or m['source'].get('kind') not in ('reference-inferred','measured','designed') for m in payload['materials'].values()):raise ValueError('asset materials require explicit provenance source')
    omitted=[]
    if not include_all_variants:
        hidden=set()
        variants=payload.get('variants',[])
        if not variants and payload.get('vehicle_bindings'):
            wheels=payload['vehicle_bindings'].get('wheels',[])
            if wheels:variants=[{'id':'legacy-wheels','options':{str(i):v for i,v in enumerate(wheels)},'default':'0'}]
        component_ids={c['id'] for c in payload['components']};variant_roots=set()
        for v in variants:
            for option_roots in v['options'].values():
                if not option_roots or any(k not in component_ids or k in variant_roots for k in option_roots):raise ValueError('invalid variant component')
                variant_roots.update(option_roots)
            if v['default'] not in v['options']:raise ValueError('missing variant default')
            for option,ids in v['options'].items():
                if option!=v['default']:hidden.update(ids)
        changed=True
        while changed:
            before=len(hidden)
            hidden.update(c['id'] for c in payload['components'] if c.get('parent') in hidden)
            changed=len(hidden)!=before
        omitted=sorted(hidden)
        payload['components']=[c for c in payload['components'] if c['id'] not in hidden]
        payload['actions']=[a for a in payload.get('actions',[]) if a['component_id'] not in hidden]
        payload['_vehicle_metadata']=payload.get('vehicle_bindings');payload['_variant_metadata']=variants;payload['_variant_mode']='default-visible';payload['variants']=[];payload['vehicle_bindings']=None
    if not include_all_variants:payload['_limitations']=[v for v in LIMITATIONS if not v.startswith('Variant options')]+['Nondefault variant geometry is omitted; use --all-variants for an inspection GLB with every option.']
    raw,report=encode_glb(payload,resource_root)
    report.update(variant_mode='all-options-inspection' if include_all_variants else 'default-visible',
                  omitted_component_ids=omitted,variant_definitions=original.get('variants',[]))
    if not include_all_variants:
        report['limitations']=[v for v in LIMITATIONS if not v.startswith('Variant options')]+['Nondefault variant geometry is omitted; use --all-variants for an inspection GLB with every option.']
    if out is None:return raw,report
    output=Path(out);manifest=Path(str(output)+'.manifest.json')
    if output.exists() or manifest.exists():raise ValueError('outputs must be new files')
    output.write_bytes(raw);manifest.write_text(json.dumps(report,indent=2))
    return dict(report,glb_path=str(output.resolve()),manifest_path=str(manifest.resolve()))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('payload');p.add_argument('--out',required=True);p.add_argument('--resource-root',required=True);p.add_argument('--manifest');p.add_argument('--all-variants',action='store_true');a=p.parse_args()
    try:
        output=Path(a.out);manifest=Path(a.manifest) if a.manifest else Path(str(output)+'.manifest.json')
        if output.resolve()==manifest.resolve() or output.exists() or manifest.exists():raise ValueError('outputs must be distinct new files')
        raw,report=export_glb(json.loads(Path(a.payload).read_text()),resource_root=a.resource_root,include_all_variants=a.all_variants)
        output.write_bytes(raw);manifest.write_text(json.dumps(report,indent=2));print(json.dumps(report));return 0
    except (ValueError,KeyError,TypeError,OSError,struct.error) as exc:print(json.dumps({'passed':False,'error':str(exc)}));return 1


if __name__=='__main__':raise SystemExit(main())
