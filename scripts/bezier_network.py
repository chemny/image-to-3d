#!/usr/bin/env python3
"""Explicit bicubic Bezier patch network; no automatic image-to-control-point solver.

control_points maps IDs to {position:[x,y,z],source:{...}}. Every patch declares
id, control_points (4 rows of 4 IDs, indexed [u][v]), segments:[nu,nv].
shared_edges=[{a:{patch,edge:'u0|u1|v0|v1'},b:{...},reverse:false,
continuity:'C0|G1|C1',tolerance:1e-7}]. Declared pairs must share control IDs,
possibly reversed. Matching subdivisions are required. Vertex arrays stay local
to each patch; seam sample positions are verified coincident to tolerance.
G1 diagnostic requires opposing cross-edge tangent directions at sampled points;
C1 additionally requires equal cross-edge derivatives (unit parameter domains).
G1/C1 require consistent normal orientation; reverse edge order alone does not
repair an oppositely wound patch. C0 reports orientation but does not enforce it.
This does not certify global self-intersection, curvature continuity, or outwardness.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from surface_model import javascript


def vec(v):return isinstance(v,list) and len(v)==3 and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v)
def sub(a,b):return [x-y for x,y in zip(a,b)]
def add(a,b):return [x+y for x,y in zip(a,b)]
def scale(a,s):return [x*s for x in a]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def norm(a):return math.sqrt(dot(a,a))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def basis(t):return [(1-t)**3,3*t*(1-t)**2,3*t*t*(1-t),t**3]
def derivative(t):return [-3*(1-t)**2,3*(1-t)**2-6*t*(1-t),6*t*(1-t)-3*t*t,3*t*t]


def evaluate(grid,u,v):
    bu,bv=basis(u),basis(v);du,dv=derivative(u),derivative(v)
    out=[[0.,0.,0.] for _ in range(3)]
    for i in range(4):
        for j in range(4):
            for k in range(3):
                out[0][k]+=grid[i][j][k]*bu[i]*bv[j]
                out[1][k]+=grid[i][j][k]*du[i]*bv[j]
                out[2][k]+=grid[i][j][k]*bu[i]*dv[j]
    n=cross(out[1],out[2]);size=norm(n)
    if size <= 1e-12*max(norm(out[1])*norm(out[2]),1e-12):raise ValueError('degenerate patch derivatives')
    return out[0],out[1],out[2],scale(n,1/size)


def edge_ids(p,edge):
    c=p['control_points']
    if edge=='u0':return c[0]
    if edge=='u1':return c[3]
    if edge=='v0':return [c[i][0] for i in range(4)]
    if edge=='v1':return [c[i][3] for i in range(4)]
    raise ValueError('invalid edge')


def edge_sample(grid,edge,t):
    u,v={'u0':(0,t),'u1':(1,t),'v0':(t,0),'v1':(t,1)}[edge]
    p,du,dv,n=evaluate(grid,u,v)
    # Inward cross-edge tangent; neighboring patches must oppose one another.
    inward=du if edge=='u0' else scale(du,-1) if edge=='u1' else dv if edge=='v0' else scale(dv,-1)
    along=dv if edge[0]=='u' else du
    return p,inward,along,n


def build_network(spec):
    points=spec['control_points'];patches=spec['patches'];by_id={};grids={}
    if not patches:raise ValueError('patches required')
    for key,p in points.items():
        if not vec(p.get('position')) or not p.get('source'):raise ValueError('finite position and source required: '+key)
    for p in patches:
        key=p['id'];ids=p['control_points'];segments=p.get('segments',[16,16])
        if key in by_id:raise ValueError('duplicate patch')
        if len(ids)!=4 or any(len(row)!=4 for row in ids):raise ValueError('4x4 control grid required')
        if len(segments)!=2 or any(not isinstance(x,int) or isinstance(x,bool) or not 2<=x<=256 for x in segments):raise ValueError('segments must be in [2,256]')
        try:grids[key]=[[points[name]['position'] for name in row] for row in ids]
        except KeyError as exc:raise ValueError('missing control point '+str(exc)) from exc
        by_id[key]=dict(p,segments=segments)
    seams=[]
    for seam in spec.get('shared_edges',[]):
        a,b=seam['a'],seam['b'];pa,pb=by_id[a['patch']],by_id[b['patch']]
        ia,ib=edge_ids(pa,a['edge']),edge_ids(pb,b['edge'])
        reverse=seam.get('reverse',False)
        if reverse:ib=ib[::-1]
        if ia!=ib:raise ValueError('shared edge must reference identical control IDs in matching order')
        na=pa['segments'][1 if a['edge'][0]=='u' else 0];nb=pb['segments'][1 if b['edge'][0]=='u' else 0]
        if na!=nb:raise ValueError('shared edge subdivisions must match')
        tol=seam.get('tolerance',1e-7);kind=seam.get('continuity','C0')
        if not isinstance(tol,(int,float)) or not math.isfinite(tol) or tol<0 or kind not in ('C0','G1','C1'):raise ValueError('invalid seam contract')
        max_gap=max_c1=max_g1=0.;opposing=True;normal_agreement=1.
        for i in range(na+1):
            t=i/na;p,da,along,an=edge_sample(grids[a['patch']],a['edge'],t)
            q,db,_,bn=edge_sample(grids[b['patch']],b['edge'],1-t if reverse else t)
            max_gap=max(max_gap,norm(sub(p,q)));max_c1=max(max_c1,norm(add(da,db)))
            # Remove edge-tangent components: general G1 permits parameter shear.
            tangent=scale(along,1/norm(along));ta=sub(da,scale(tangent,dot(da,tangent)));tb=sub(db,scale(tangent,dot(db,tangent)))
            max_g1=max(max_g1,norm(cross(ta,tb))/(norm(ta)*norm(tb)))
            opposing=opposing and dot(ta,tb)<0;normal_agreement=min(normal_agreement,dot(an,bn))
        passed=max_gap<=tol and (kind=='C0' or (opposing and max_g1<=tol and normal_agreement>0)) and (kind!='C1' or max_c1<=tol)
        record={'a':a,'b':b,'continuity':kind,'position_error':max_gap,'c1_error':max_c1,'g1_sine_error':max_g1,'normal_dot_min':normal_agreement,'orientation_consistent':normal_agreement>0,'passed':passed}
        seams.append(record)
        if not passed:raise ValueError('seam continuity failed: '+json.dumps(record))
    components=[];triangles=vertices=0
    for key,p in by_id.items():
        nu,nv=p['segments'];positions=[];normals=[];indices=[]
        for i in range(nu+1):
            for j in range(nv+1):
                position,_,_,n=evaluate(grids[key],i/nu,j/nv);positions.extend(position);normals.extend(n)
        for i in range(nu):
            for j in range(nv):
                a=i*(nv+1)+j;b=a+nv+1;c=a+1;d=b+1;indices.extend([a,b,c,b,d,c])
        vertices+=len(positions)//3;triangles+=len(indices)//3
        components.append({'id':key,'parent':None,'positions':positions,'normals':normals,'patches':[{'id':key,'indices':indices}]})
    return {'schema_version':1,'spec_sha256':hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest(),
            'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'explicit bicubic patches; supplied controls only; no image reconstruction claim',
            'boundary_storage':'independent patch vertices; declared seam positions checked at identical subdivisions',
            'vertex_count':vertices,'triangle_count':triangles,'seams':seams,'components':components}


def main():
    p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('--out',required=True);p.add_argument('--js');a=p.parse_args()
    try:
        mesh=build_network(json.loads(Path(a.spec).read_text()));Path(a.out).write_text(json.dumps(mesh))
        if a.js:Path(a.js).write_text(javascript(mesh))
        print(json.dumps({k:mesh[k] for k in ('vertex_count','triangle_count','seams')}));return 0
    except (ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'passed':False,'error':str(exc)}));return 1

if __name__=='__main__':raise SystemExit(main())
