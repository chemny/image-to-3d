#!/usr/bin/env python3
"""Local mesh topology and declared anchor checks; not exhaustive collision testing.

Input meshes: [{id, contract:'open_patch'|'closed_shell', positions:[x,y,z,...],
triangles:[a,b,c,...]}]. Topology uses indices: coincident unwelded vertices are NOT
silently merged. Each independent part declares its own closure contract.
Assembly nodes: [{id,parent,kind:'fixed'|'moving',translation:[x,y,z],
rotation:{axis:'x'|'y'|'z',degrees:0}}]. Local points rotate then translate.
Connections: {id,a:{node,point},b:{node,point},max_distance}. Optional ownership
rules: {node,required_parent,required_kind}. Poses: {id,angles:{node:degrees}}.
Coordinates/distances use the caller's declared unit. Axis is parent-local;
rotations are around node origin. Provide hinge-local frames explicitly.
"""
import argparse
import json
import math
from pathlib import Path


def finite_vector(v,n):
    return isinstance(v,list) and len(v)==n and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v)


def mesh_report(mesh):
    errors=[];p=mesh.get('positions',[]);t=mesh.get('triangles',[]);edges={};degenerate=[]
    contract=mesh.get('contract')
    if contract not in ('open_patch','closed_shell'):errors.append('unknown closure contract')
    if not isinstance(p,list) or len(p)%3 or not finite_vector(p,len(p)) or len(p)<9:
        return {'id':mesh.get('id'),'passed':False,'errors':['invalid finite position array']}
    if not isinstance(t,list) or len(t)%3 or not t or any(not isinstance(i,int) or isinstance(i,bool) or not 0<=i<len(p)//3 for i in t):
        return {'id':mesh.get('id'),'passed':False,'errors':['invalid triangle indices']}
    scale=max(max(p[i::3])-min(p[i::3]) for i in range(3));area_eps=max(scale**2*1e-12,1e-24)
    for k in range(0,len(t),3):
        a,b,c=t[k:k+3];u=[p[3*b+i]-p[3*a+i] for i in range(3)];v=[p[3*c+i]-p[3*a+i] for i in range(3)]
        cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if math.sqrt(sum(x*x for x in cross))<=area_eps:degenerate.append(k//3)
        for x,y in ((a,b),(b,c),(c,a)):edges.setdefault(tuple(sorted((x,y))),[]).append((x,y,k//3))
    boundary=[list(e) for e,uses in edges.items() if len(uses)==1]
    nonmanifold=[list(e) for e,uses in edges.items() if len(uses)>2]
    inconsistent=[list(e) for e,uses in edges.items() if len(uses)==2 and uses[0][:2]==uses[1][:2]]
    if degenerate:errors.append('degenerate triangles')
    if nonmanifold:errors.append('nonmanifold edges')
    if inconsistent:errors.append('inconsistent adjacent winding')
    if contract=='closed_shell' and boundary:errors.append('closed shell has boundary edges')
    # Winding consistency does not determine global outwardness; orientation has no
    # semantic inside/outside without an explicit target or signed-volume contract.
    return {'id':mesh.get('id'),'contract':contract,'passed':not errors,'errors':errors,
            'boundary_edges':boundary,'nonmanifold_edges':nonmanifold,'inconsistent_edges':inconsistent,
            'degenerate_triangles':degenerate,'outward_orientation_checked':False}


def rotate(p,axis,degrees):
    a=math.radians(degrees);c=math.cos(a);s=math.sin(a);x,y,z=p
    if axis=='x':return [x,c*y-s*z,s*y+c*z]
    if axis=='y':return [c*x+s*z,y,-s*x+c*z]
    if axis=='z':return [c*x-s*y,s*x+c*y,z]
    raise ValueError('rotation axis must be x/y/z')


def assembly_report(assembly):
    errors=[];nodes={};samples=[]
    try:
        for n in assembly.get('nodes',[]):
            if n['id'] in nodes:raise ValueError('duplicate node id')
            if n.get('kind') not in ('fixed','moving'):raise ValueError('node kind required')
            if not finite_vector(n.get('translation',[0,0,0]),3):raise ValueError('invalid node translation')
            r=n.get('rotation',{'axis':'y','degrees':0})
            if r.get('axis') not in ('x','y','z') or not isinstance(r.get('degrees'),(int,float)) or not math.isfinite(r['degrees']):raise ValueError('invalid node rotation')
            nodes[n['id']]=n
        for key in nodes:
            cursor=key;seen=set()
            while cursor is not None:
                if cursor in seen or cursor not in nodes:raise ValueError('cyclic or missing parent')
                seen.add(cursor);cursor=nodes[cursor].get('parent')
        for rule in assembly.get('ownership',[]):
            n=nodes[rule['node']]
            if 'required_parent' in rule and n.get('parent')!=rule['required_parent']:errors.append('parent mismatch: '+rule['node'])
            if 'required_kind' in rule and n['kind']!=rule['required_kind']:errors.append('kind mismatch: '+rule['node'])
        def world(anchor,angles):
            p=anchor['point'];key=anchor['node']
            if not finite_vector(p,3):raise ValueError('invalid anchor point')
            while key is not None:
                n=nodes[key];r=n.get('rotation',{'axis':'y','degrees':0});deg=angles.get(key,r['degrees'])
                if not isinstance(deg,(int,float)) or not math.isfinite(deg):raise ValueError('invalid sampled angle')
                p=rotate(p,r['axis'],deg);p=[a+b for a,b in zip(p,n.get('translation',[0,0,0]))];key=n.get('parent')
            return p
        poses=assembly.get('poses',[{'id':'rest','angles':{}}])
        if not poses:raise ValueError('at least one pose required')
        for pose in poses:
            angles=pose.get('angles',{})
            for key in angles:
                if key not in nodes or nodes[key]['kind']!='moving':raise ValueError('sampled angle on absent or fixed node')
            for connection in assembly.get('connections',[]):
                tol=connection['max_distance']
                if not isinstance(tol,(int,float)) or not math.isfinite(tol) or tol<0:raise ValueError('invalid distance tolerance')
                a=world(connection['a'],angles);b=world(connection['b'],angles);d=math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
                ok=d<=tol+1e-12;samples.append({'pose':pose['id'],'connection':connection['id'],'distance':d,'passed':ok})
                if not ok:errors.append('anchor separation: '+pose['id']+'/'+connection['id'])
    except (ValueError,KeyError,TypeError) as exc:errors.append(str(exc))
    return {'passed':not errors,'errors':errors,'samples':samples,'collision_checked':False,
            'scope':'declared ownership and anchors at explicit sampled poses only; no continuous sweep/collision guarantee'}


def check(data):
    reports=[mesh_report(m) for m in data.get('meshes',[])]
    assembly=assembly_report(data.get('assembly',{}))
    if not reports and not data.get('assembly',{}).get('nodes'):return {'passed':False,'errors':['no meshes or assembly nodes supplied']}
    return {'passed':all(m['passed'] for m in reports) and assembly['passed'],'meshes':reports,'assembly':assembly,
            'scope':'per-part index topology and declared anchor checks, not full physical assembly validation'}


def main():
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--out');a=p.parse_args()
    result=check(json.loads(Path(a.input).read_text()));text=json.dumps(result,indent=2)
    if a.out:Path(a.out).write_text(text)
    print(text);return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
