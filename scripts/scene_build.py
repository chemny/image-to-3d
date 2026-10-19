#!/usr/bin/env python3
"""Spec geometry authority and self-contained Three.js factory. +Y up,+Z forward.
Explicit supported geometry only; no inferred primitive fallback. local_point is
in component coordinates; mesh vertex and Bezier bindings use built geometry.
Vehicle adapter requires vehicle_bindings with actual paint/lights/wheels/actions.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from bezier_network import build_network, evaluate
from mesh_checks import mesh_report


def resolve(value,parameters):
    if isinstance(value,dict):
        if 'param' in value:
            if not set(value)<= {'param','scale','offset'} or value['param'] not in parameters:raise ValueError('invalid parameter reference')
            p=parameters[value['param']];v=p['value']
            if not isinstance(v,(int,float)) or not math.isfinite(v) or not p['min']<=v<=p['max']:raise ValueError('invalid parameter value/bounds')
            scale=value.get('scale',1);offset=value.get('offset',0)
            if any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in (scale,offset)):raise ValueError('finite parameter scale/offset required')
            result=v*scale+offset
            if not math.isfinite(result):raise ValueError('nonfinite resolved parameter')
            return result
        return {k:resolve(v,parameters) for k,v in value.items()}
    if isinstance(value,list):return [resolve(v,parameters) for v in value]
    if isinstance(value,float) and not math.isfinite(value):raise ValueError('nonfinite scalar')
    return value


def vector(v,n=3):
    if not isinstance(v,list) or len(v)!=n or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in v):raise ValueError('finite vector required')
    return v


def rotate(v,r):
    # Three Euler XYZ = Rx Ry Rz on a column vector.
    x,y,z=v
    for axis,a in ((2,r[2]),(1,r[1]),(0,r[0])):
        c,s=math.cos(a),math.sin(a)
        if axis==2:x,y=c*x-s*y,s*x+c*y
        elif axis==1:x,z=c*x+s*z,-s*x+c*z
        else:y,z=c*y-s*z,s*y+c*z
    return [x,y,z]


def normmesh(positions,indices):
    vector(positions,len(positions));n=len(positions)//3
    if not positions or len(positions)%3 or not indices or len(indices)%3 or any(type(i)!=int or not 0<=i<n for i in indices):raise ValueError('invalid mesh arrays')
    normals=[0.]*len(positions)
    for k in range(0,len(indices),3):
        a,b,c=indices[k:k+3];u=[positions[3*b+i]-positions[3*a+i] for i in range(3)];v=[positions[3*c+i]-positions[3*a+i] for i in range(3)]
        w=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if sum(x*x for x in w)<1e-24:raise ValueError('degenerate mesh triangle')
        for j in (a,b,c):
            for i in range(3):normals[j*3+i]+=w[i]
    for j in range(n):
        size=math.sqrt(sum(x*x for x in normals[j*3:j*3+3]))
        if size<1e-15:raise ValueError('undefined mesh vertex normal')
        normals[j*3:j*3+3]=[x/size for x in normals[j*3:j*3+3]]
    return {'positions':positions,'normals':normals,'indices':indices}


def segments(g,key,default):
    v=g.get(key,default)
    if type(v)!=int or not 3<=v<=256:raise ValueError('segment count must be integer 3..256')
    return v


def _geometry(g):
    kind=g.get('type');p=[];t=[]
    if kind=='form_recipe':
        from form_construction import compile_recipe
        return _geometry(compile_recipe(g['recipe'])['geometry'])
    if kind=='mesh':
        mesh=normmesh(g['positions'],g['triangles'])
        if 'uvs' in g:
            vector(g['uvs'],len(mesh['positions'])//3*2);mesh['uvs']=g['uvs']
        if 'normals' in g:
            vector(g['normals'],len(mesh['positions']))
            if any(abs(sum(v*v for v in g['normals'][i:i+3])-1)>1e-3 for i in range(0,len(g['normals']),3)):raise ValueError('unit normals required')
            mesh['normals']=g['normals']
        return [mesh]
    if kind in ('torus','tube'):
        from asset_geometry import swept_geometry
        return [swept_geometry(g)]
    if kind=='bezier_network':
        network=build_network(g['network'])
        return [{'id':c['id'],'positions':c['positions'],'normals':c['normals'],'indices':c['patches'][0]['indices']} for c in network['components']]
    if kind=='box':
        size=vector(g['size'])
        if min(size)<=0:raise ValueError('positive box size required')
        # Independent face vertices retain hard normals.
        faces=[[(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)],[(-1,-1,1),(-1,1,1),(-1,1,-1),(-1,-1,-1)],
               [(-1,1,-1),(-1,1,1),(1,1,1),(1,1,-1)],[(-1,-1,1),(-1,-1,-1),(1,-1,-1),(1,-1,1)],
               [(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)],[(1,-1,-1),(-1,-1,-1),(-1,1,-1),(1,1,-1)]]
        for face in faces:
            offset=len(p)//3
            for v in face:p.extend([v[i]*size[i]/2 for i in range(3)])
            t.extend([offset,offset+1,offset+2,offset,offset+2,offset+3])
    elif kind=='sphere':
        radius=g['radius'];nu=segments(g,'widthSegments',24);nv=segments(g,'heightSegments',16)
        if radius<=0:raise ValueError('positive sphere radius required')
        p=[0,radius,0]
        for j in range(1,nv):
            phi=math.pi*j/nv
            for i in range(nu):
                theta=2*math.pi*i/nu;p.extend([radius*math.sin(phi)*math.cos(theta),radius*math.cos(phi),radius*math.sin(phi)*math.sin(theta)])
        bottom=len(p)//3;p.extend([0,-radius,0])
        for i in range(nu):t.extend([0,1+(i+1)%nu,1+i])
        for j in range(nv-2):
            for i in range(nu):
                a=1+j*nu+i;b=1+j*nu+(i+1)%nu;c=a+nu;d=b+nu;t.extend([a,b,c,b,d,c])
        for i in range(nu):t.extend([bottom,1+(nv-2)*nu+i,1+(nv-2)*nu+(i+1)%nu])
    elif kind in ('cylinder','lathe'):
        nu=segments(g,'radialSegments' if kind=='cylinder' else 'segments',24)
        if kind=='cylinder':
            h=g['height'];rb=g['radiusBottom'];rt=g['radiusTop']
            if h<=0 or min(rb,rt)<=0:raise ValueError('positive cylinder dimensions required')
            profile=[[rb,-h/2],[rt,h/2]]
        else:
            profile=g['profile']
            if len(profile)<2 or any(len(v)!=2 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v) or v[0]<=0 for v in profile):raise ValueError('lathe profile needs positive radii')
            if any(b[1]<=a[1] for a,b in zip(profile,profile[1:])):raise ValueError('lathe profile y must increase')
        for r,y in profile:
            for i in range(nu):a=2*math.pi*i/nu;p.extend([r*math.cos(a),y,r*math.sin(a)])
        for j in range(len(profile)-1):
            for i in range(nu):
                a=j*nu+i;b=j*nu+(i+1)%nu;c=a+nu;d=b+nu;t.extend([a,c,b,b,c,d])
        if kind=='cylinder' or g.get('closed',False):
            for row,bottom in ((0,True),(len(profile)-1,False)):
                center=len(p)//3;p.extend([0,profile[row][1],0])
                # Duplicate rim for hard cap normals.
                rim=len(p)//3
                for i in range(nu):p.extend(p[(row*nu+i)*3:(row*nu+i)*3+3])
                for i in range(nu):a=rim+i;b=rim+(i+1)%nu;t.extend([center,a,b] if bottom else [center,b,a])
    else:raise ValueError('unsupported geometry type: '+str(kind))
    return [normmesh(p,t)]


def geometry(g):
    """Keep render normals intact; attach explicit topology-only seam mapping.

    Only trusted built-in face/cap generators are welded, using EXACT position
    equality (tolerance zero). User mesh indices are never silently changed.
    """
    meshes=_geometry(g)
    for mesh in meshes:
        if g['type'] in ('box','cylinder','torus','tube') or (g['type']=='lathe' and g.get('closed',False)):
            points=[];lookup={};mapping=[]
            for i in range(0,len(mesh['positions']),3):
                point=tuple(mesh['positions'][i:i+3])
                if point not in lookup:lookup[point]=len(points)//3;points.extend(point)
                mapping.append(lookup[point])
            topology={'positions':points,'triangles':[mapping[i] for i in mesh['indices']],
                      'policy':'generator_seam_weld','tolerance':0,'render_to_topology':mapping}
        else:
            topology={'positions':list(mesh['positions']),'triangles':list(mesh['indices']),
                      'policy':'preserve_indices','tolerance':0}
        mesh['topology_mesh']=topology
    return meshes


def prepared(spec):
    for key,p in spec.get('parameters',{}).items():
        if not all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) for k in ('value','min','max')) or not p['min']<=p['value']<=p['max']:raise ValueError('invalid parameter '+key)
    s=resolve(spec,spec.get('parameters',{}));axis=s.get('coordinate_system',{})
    if axis.get('up') not in ('y','+Y') or axis.get('forward') not in ('z','+Z'):raise ValueError('explicit conversion to +Y up/+Z forward required')
    nodes={}
    for c in s['components']:
        if c['id'] in nodes:raise ValueError('duplicate component')
        vector(c.get('position',[0,0,0]));vector(c.get('rotation',[0,0,0]))
        if c.get('geometry',{}).get('type')=='form_recipe':
            from form_construction import compile_recipe
            recipe=c['geometry']['recipe']
            if recipe.get('component_id')!=c['id']:raise ValueError('recipe component identity mismatch')
            refs={r['id']:r for r in s.get('references',[])};source=recipe.get('source',{});ref=refs.get(source.get('reference_id'))
            if not ref:raise ValueError('recipe reference missing')
            x,y,w,h=source['roi'];iw,ih=ref['image_size']
            if not (0<=x<x+w<=iw and 0<=y<y+h<=ih):raise ValueError('recipe ROI outside source')
            compiled=compile_recipe(recipe);c['_construction_recipe']=recipe;c['geometry']=compiled['geometry']
        nodes[c['id']]=c
    for key in nodes:
        seen=set();cursor=key
        while cursor is not None:
            if cursor in seen or cursor not in nodes:raise ValueError('cyclic or missing parent')
            seen.add(cursor);cursor=nodes[cursor].get('parent')
    return s,nodes


def landmark(spec,observation):
    s,nodes=prepared(spec);o=resolve(observation,spec.get('parameters',{}))
    try:
        c=nodes[o['component_id']];binding=o.get('binding',o)
        if sum(k in binding for k in ('local_point','vertex_index','patch_id'))!=1:raise ValueError('exactly one landmark binding required')
        if 'local_point' in binding:p=vector(binding['local_point'])
        elif 'vertex_index' in binding:
            if c['geometry']['type']!='mesh':raise ValueError('vertex binding requires explicit mesh')
            i=binding['vertex_index'];positions=c['geometry']['positions']
            if type(i)!=int or not 0<=i<len(positions)//3:raise ValueError('invalid landmark vertex')
            p=positions[3*i:3*i+3]
        else:
            net=c['geometry']['network'];patch=next(x for x in net['patches'] if x['id']==binding['patch_id']);u,v=vector(binding['uv'],2)
            if not 0<=u<=1 or not 0<=v<=1:raise ValueError('uv outside patch')
            grid=[[net['control_points'][k]['position'] for k in row] for row in patch['control_points']];p=evaluate(grid,u,v)[0]
        key=c['id']
        while key is not None:
            c=nodes[key];p=[a+b for a,b in zip(rotate(p,c.get('rotation',[0,0,0])),c.get('position',[0,0,0]))];key=c.get('parent')
        return p
    except (KeyError,StopIteration,TypeError) as exc:raise ValueError('invalid landmark binding: '+str(exc)) from exc


def build(spec):
    try:return _build(spec)
    except (KeyError,TypeError,OverflowError) as exc:raise ValueError('invalid scene spec: '+str(exc)) from exc


def _build(spec):
    from asset_contract import validate as validate_asset
    s,nodes=prepared(spec);validate_asset(s);materials=s.get('materials',{})
    if not materials:raise ValueError('materials required')
    for key,m in materials.items():
        if not isinstance(m.get('color'),str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',m['color']):raise ValueError('material hex color required')
        if 'emissive' in m and (not isinstance(m['emissive'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',m['emissive'])):raise ValueError('emissive hex color required')
        if 'emissiveIntensity' in m and (not isinstance(m['emissiveIntensity'],(int,float)) or not math.isfinite(m['emissiveIntensity']) or m['emissiveIntensity']<0):raise ValueError('invalid emissive intensity')
        for k in ('roughness','metalness','opacity','transmission','clearcoat'):
            if k in m and not 0<=m[k]<=1:raise ValueError('material property outside [0,1]')
    components=[]
    for c in nodes.values():
        assembly=c.get('kind')=='assembly'
        if not assembly and c.get('material') not in materials:raise ValueError('missing component material')
        meshes=[] if assembly else geometry(c['geometry'])
        surface_contract=c.get('surface_contract')
        surface_report=None
        if surface_contract is not None:
            if assembly or c['geometry'].get('type')!='mesh':
                raise ValueError('surface contract requires one explicit authored mesh: '+c['id'])
            from surface_quality import inspect_geometry
            surface_report=inspect_geometry(c['geometry'],surface_contract)
            if not surface_report['passed']:
                raise ValueError('surface contract failed: '+c['id']+': '+', '.join(surface_report['errors']))
        if not assembly and materials[c['material']].get('maps') and any('uvs' not in mesh for mesh in meshes):raise ValueError('textured component needs authored UVs: '+c['id'])
        contract=c.get('topology_contract')
        for mesh in meshes:
            if contract is not None:
                report=mesh_report({'id':c['id']+':'+mesh.get('id','mesh'),'contract':contract,
                                    'positions':mesh['topology_mesh']['positions'],'triangles':mesh['topology_mesh']['triangles']})
                mesh['topology_report']=report
                if not report['passed']:raise ValueError('topology contract failed: '+c['id']+': '+', '.join(report['errors']))
        components.append({'id':c['id'],'parent':c.get('parent'),'role':c.get('role',''),'material':c.get('material'),
                           'kind':c.get('kind','part'),'selectable':c.get('selectable',True),'explode_vector':c.get('explode_vector',[0,0,0]),'material_slots':c.get('material_slots',{}),
                           'position':c.get('position',[0,0,0]),'rotation':c.get('rotation',[0,0,0]),'meshes':meshes,'topology_contract':contract,
                           **({'surface_report':surface_report} if surface_report is not None else {})})
    actions=s.get('actions',[]);aids=set();used=set()
    for a in actions:
        if a['id'] in aids or a['component_id'] in used or a['component_id'] not in nodes:raise ValueError('duplicate or missing action component')
        if a['axis'] not in ('x','y','z') or not isinstance(a['angle'],(int,float)) or not math.isfinite(a['angle']) or a['angle']==0:raise ValueError('invalid action')
        vector(a['pivot']);aids.add(a['id']);used.add(a['component_id'])
    bindings=s.get('vehicle_bindings')
    if bindings is not None:
        if not bindings.get('paint') or any(k not in materials for k in bindings['paint']):raise ValueError('vehicle paint binding missing')
        if len(bindings.get('lights',[]))!=3 or len(set(bindings['lights']))!=3 or any(k not in materials or not materials[k].get('emissive') or materials[k]['emissive']=='#000000' for k in bindings['lights']):raise ValueError('locked adapter requires three real emissive light materials')
        wheels=bindings.get('wheels',[])
        if len(wheels)!=3 or any(not v or any(k not in nodes for k in v) for v in wheels) or len(set(k for v in wheels for k in v))!=sum(map(len,wheels)):raise ValueError('three distinct real wheel variant groups required')
        groups=bindings.get('actions',{})
        if set(groups)!={'left','right','hood','trunk'} or any(not v or any(k not in aids for k in v) for v in groups.values()):raise ValueError('vehicle action bindings missing')
        if len(set(k for v in groups.values() for k in v))!=sum(map(len,groups.values())):raise ValueError('vehicle action groups must be disjoint')
        variant_of={k:i for i,v in enumerate(wheels) for k in v}
        for key,variant in variant_of.items():
            parent=nodes[key].get('parent')
            while parent is not None:
                if parent in variant_of and variant_of[parent]!=variant:raise ValueError('cross-variant wheel ancestry')
                parent=nodes[parent].get('parent')
        used_materials={c['material'] for c in components}
        if any(k not in used_materials for k in bindings['paint']+bindings['lights']):raise ValueError('bound material is unused')
    return {'schema_version':1,'spec_sha256':hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest(),
            'asset_contract':s.get('asset_contract'),'variants':s.get('variants',[]),
            'components':components,'materials':materials,'actions':actions,'vehicle_bindings':bindings,'cameras':s.get('cameras',{}),
            'scope':'explicit geometry/spec construction; no image-fidelity acceptance implied'}


def emit_js(payload):
    """Legacy standalone adapter for API compatibility; production writes via lightweight_delivery."""
    runtime=Path(__file__).resolve().parents[1]/'assets/scene-runtime.mjs'
    return "import * as THREE from 'three';\nconst data="+json.dumps(payload,separators=(',',':'))+";\n"+runtime.read_text()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('spec');parser.add_argument('--out',required=True);parser.add_argument('--js',required=True);a=parser.parse_args()
    try:
        if Path(a.out).resolve()==Path(a.js).resolve():raise ValueError('JSON and JS outputs must be distinct')
        for name in (a.out,a.js):
            if Path(name).exists() or Path(name).resolve()==Path(a.spec).resolve():raise ValueError('output must be a new file')
        spec=json.loads(Path(a.spec).read_text());payload=build(spec);Path(a.out).write_text(json.dumps(payload))
        from lightweight_delivery import write_runtime
        write_runtime(Path(a.js).parent,payload,budget_bytes=spec.get('delivery_profile',{}).get('budget_bytes',50_000_000),runtime_name=Path(a.js).name)
        print(json.dumps({'passed':True,'components':len(payload['components']),'spec_sha256':payload['spec_sha256']}));return 0
    except (ValueError,OSError) as exc:print(json.dumps({'passed':False,'error':str(exc)}));return 1

if __name__=='__main__':raise SystemExit(main())
