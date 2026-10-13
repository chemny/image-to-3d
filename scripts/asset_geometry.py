"""Deterministic UV-aware torus and transported-frame tube, not photo reconstruction."""
import math

def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def unit(v):
    n=math.sqrt(sum(x*x for x in v))
    if n<1e-10:raise ValueError('degenerate tube tangent/frame')
    return [x/n for x in v]
def swept_geometry(g):
    from scene_build import normmesh,vector,segments
    p=[];uv=[];normals=[];tri=[]
    n=segments(g,'radialSegments',24)
    if g['type']=='torus':
        r=g.get('radius');tube=g.get('tube')
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in (r,tube)) or not 0<tube<r:raise ValueError('torus radius must exceed positive tube')
        steps=segments(g,'tubularSegments',48)
        rings=[]
        for j in range(steps+1):
            a=2*math.pi*(j%steps)/steps
            rings.append(([r*math.cos(a),r*math.sin(a),0],[math.cos(a),math.sin(a),0],[0,0,1],tube))
    else:
        pts=g.get('points',[]);radius=g.get('radius')
        if len(pts)<2 or type(radius) not in (int,float) or not math.isfinite(radius) or radius<=0:raise ValueError('tube requires points and positive radius')
        for v in pts:vector(v)
        if any(math.dist(a,b)<1e-9 for a,b in zip(pts,pts[1:])):raise ValueError('duplicate tube centerline point')
        rings=[];previous=None;steps=len(pts)-1
        for j,pt in enumerate(pts):
            a=pts[max(j-1,0)];b=pts[min(j+1,steps)];t=unit([y-x for x,y in zip(a,b)])
            if previous is None:
                axis=min(([1,0,0],[0,1,0],[0,0,1]),key=lambda v:abs(sum(x*y for x,y in zip(v,t))))
                normal=unit(cross(t,axis))
            else:
                dot=sum(x*y for x,y in zip(previous,t));normal=unit([x-dot*y for x,y in zip(previous,t)])
            binormal=cross(t,normal);previous=normal;rings.append((pt,normal,binormal,radius))
    for j,(center,a,b,r) in enumerate(rings):
        for i in range(n+1):
            angle=2*math.pi*(i%n)/n;normal=[math.cos(angle)*x+math.sin(angle)*y for x,y in zip(a,b)]
            p.extend([x+r*y for x,y in zip(center,normal)]);normals.extend(normal);uv.extend([i/n,j/steps])
    for j in range(steps):
        for i in range(n):
            a=j*(n+1)+i;b=a+1;c=a+n+1;d=c+1
            tri.extend([a,b,c,b,d,c])
    # Select winding against authored outward normals, consistently per surface.
    a,b,c=tri[:3];ab=[p[3*b+k]-p[3*a+k] for k in range(3)];ac=[p[3*c+k]-p[3*a+k] for k in range(3)]
    if sum(x*y for x,y in zip(cross(ab,ac),normals[3*a:3*a+3]))<0:
        for k in range(0,len(tri),3):tri[k+1],tri[k+2]=tri[k+2],tri[k+1]
    if g['type']=='tube' and g.get('closed',True):
        for row,sign in ((0,-1),(steps,1)):
            tangent=unit([b-a for a,b in zip(g['points'][max(0,row-1)],g['points'][min(steps,row+1)])]);out=[sign*x for x in tangent]
            center=len(p)//3;p.extend(rings[row][0]);normals.extend(out);uv.extend([.5,.5]);rim=len(p)//3
            for i in range(n):
                idx=(row*(n+1)+i)*3;p.extend(p[idx:idx+3]);normals.extend(out);a=2*math.pi*i/n;uv.extend([.5+.5*math.cos(a),.5+.5*math.sin(a)])
            for i in range(n):
                ids=[center,rim+i,rim+(i+1)%n];a,b,c=ids
                ab=[p[3*b+k]-p[3*a+k] for k in range(3)];ac=[p[3*c+k]-p[3*a+k] for k in range(3)]
                if sum(x*y for x,y in zip(cross(ab,ac),out))<0:ids[1],ids[2]=ids[2],ids[1]
                tri.extend(ids)
    mesh=normmesh(p,tri);mesh.update(normals=normals,uvs=uv);return mesh
