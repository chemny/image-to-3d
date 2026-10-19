#!/usr/bin/env python3
"""Reference-authored continuous surfaces -> real meshes. No image inference or CAD certification."""
import argparse,hashlib,json,math
from pathlib import Path
from scene_build import normmesh
from mesh_checks import mesh_report


def need(ok,msg):
    if not ok:raise ValueError(msg)
def number(x,label,positive=False):
    need(type(x)in(int,float)and math.isfinite(x)and(not positive or x>0),label+' must be finite'+(' and positive'if positive else''));return x
def vector(x,n,label):
    need(isinstance(x,list)and len(x)==n,label+' vector size');return [number(v,label)for v in x]
def keys(p,names,label):need(isinstance(p,dict)and not set(p)-set(names),label+' unknown fields')
def add(a,b):return [x+y for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def scale(a,s):return [x*s for x in a]
def length(a):return math.sqrt(sum(x*x for x in a))

class CubicProfile:
    """Natural or clamped cubic scalar spline. Values are never silently clamped."""
    def __init__(self,knots,values,end_slopes=None):
        need(len(knots)==len(values)and len(knots)>=2,'profile needs at least two matching knots/values')
        self.x=[number(x,'knot')for x in knots];self.y=[number(x,'value')for x in values];n=len(knots)
        h=[b-a for a,b in zip(self.x,self.x[1:])];need(min(h)>0,'profile knots must strictly increase')
        lo=[0.]*n;di=[0.]*n;up=[0.]*n;rhs=[0.]*n
        for i in range(1,n-1):lo[i]=h[i-1];di[i]=2*(h[i-1]+h[i]);up[i]=h[i];rhs[i]=6*((self.y[i+1]-self.y[i])/h[i]-(self.y[i]-self.y[i-1])/h[i-1])
        if end_slopes is None:di[0]=di[-1]=1
        else:
            slopes=vector(list(end_slopes),2,'end slopes');di[0]=2*h[0];up[0]=h[0];rhs[0]=6*((self.y[1]-self.y[0])/h[0]-slopes[0]);lo[-1]=h[-1];di[-1]=2*h[-1];rhs[-1]=6*(slopes[1]-(self.y[-1]-self.y[-2])/h[-1])
        for i in range(1,n):factor=lo[i]/di[i-1];di[i]-=factor*up[i-1];rhs[i]-=factor*rhs[i-1]
        m=[0.]*n;m[-1]=rhs[-1]/di[-1]
        for i in range(n-2,-1,-1):m[i]=(rhs[i]-up[i]*m[i+1])/di[i]
        self.m=m
    def __call__(self,t,derivative=0):
        number(t,'profile position');need(self.x[0]-1e-12<=t<=self.x[-1]+1e-12,'profile extrapolation forbidden');need(derivative in (0,1,2),'profile derivative unsupported')
        i=min(len(self.x)-2,next((i for i in range(len(self.x)-1)if t<=self.x[i+1]),len(self.x)-2));h=self.x[i+1]-self.x[i];a=(self.x[i+1]-t)/h;b=1-a;y0,y1=self.y[i:i+2];m0,m1=self.m[i:i+2]
        if derivative==2:return a*m0+b*m1
        if derivative==1:return (y1-y0)/h+h*((1-3*a*a)*m0+(3*b*b-1)*m1)/6
        return a*y0+b*y1+((a**3-a)*m0+(b**3-b)*m1)*h*h/6
    def minimum(self):
        """Exact scalar cubic interval minima, including interior stationary points."""
        values=list(self.y)
        for i in range(len(self.x)-1):
            h=self.x[i+1]-self.x[i];a=(self.m[i+1]-self.m[i])/(2*h);b=self.m[i];c=self(self.x[i],1)
            roots=[]
            if abs(a)<1e-14:
                if abs(b)>1e-14:roots=[-c/b]
            elif b*b-4*a*c>=0:
                root=math.sqrt(b*b-4*a*c);roots=[(-b-root)/(2*a),(-b+root)/(2*a)]
            values.extend(self(self.x[i]+t)for t in roots if 0<t<h)
        return min(values)

def adaptive_parameters(fn,start,end,tolerance,max_depth=12,max_count=4096):
    number(tolerance,'max_chord_error',True);out=[start];worst=0
    def visit(a,b,depth):
        nonlocal worst
        p,q=fn(a),fn(b);error=max(length(sub(fn(a+(b-a)*u),add(scale(p,1-u),scale(q,u))))for u in (.25,.5,.75))
        if error>tolerance:
            need(depth<max_depth,'adaptive sampling depth exhausted; simplify or revise surface');mid=(a+b)/2;visit(a,mid,depth+1);visit(mid,b,depth+1)
        else:worst=max(worst,error);out.append(b);need(len(out)<=max_count,'adaptive sampling budget exhausted')
    visit(start,end,0);return out,worst

def ring_mesh(rings,lower=None,upper=None):
    n=len(rings[0]);need(n>=3 and all(len(r)==n for r in rings),'ring correspondence mismatch');p=[x for r in rings for q in r for x in q];tri=[]
    for j in range(len(rings)-1):
        for i in range(n):a=j*n+i;b=j*n+(i+1)%n;c=a+n;d=b+n;tri.extend([a,c,b,b,c,d])
    if lower is not None:
        k=len(p)//3;p.extend(lower)
        for i in range(n):tri.extend([k,i,(i+1)%n])
    if upper is not None:
        k=len(p)//3;p.extend(upper);s=(len(rings)-1)*n
        for i in range(n):tri.extend([k,s+(i+1)%n,s+i])
    return p,tri

def smooth_loft(p):
    keys(p,('sections','radial_segments','max_chord_error','cap_depths','cap_segments','end_slopes'),'smooth_loft')
    sec=p.get('sections');need(isinstance(sec,list)and 2<=len(sec)<=256,'loft sections required');centers=[];radii=[]
    for s in sec:keys(s,('center','radii'),'section');centers.append(vector(s.get('center'),3,'center'));radii.append(vector(s.get('radii'),2,'radii'))
    need(all(min(r)>0 for r in radii),'loft radii must be positive');knots=[c[1]for c in centers];need(all(b>a for a,b in zip(knots,knots[1:])),'loft Y must strictly increase')
    n=p.get('radial_segments',48);need(type(n)==int and 8<=n<=256,'radial_segments 8..256');tol=number(p.get('max_chord_error',.001),'max_chord_error',True)
    caps=p.get('cap_depths');slopes=p.get('end_slopes')
    if caps is not None:caps=vector(caps,2,'cap depths');need(min(caps)>0,'rounded cap depths must be positive');need(slopes is None,'rounded caps set zero end slopes; conflicting slopes rejected');slopes=[0,0]
    profile=[CubicProfile(knots,[c[0]for c in centers],slopes),CubicProfile(knots,[c[2]for c in centers],slopes),CubicProfile(knots,[r[0]for r in radii],slopes),CubicProfile(knots,[r[1]for r in radii],slopes)]
    need(min(f.minimum()for f in profile[2:])>0,'spline overshoots positive radius; add sections or change boundary conditions')
    def check(t):
        value=[f(t)for f in profile];need(min(value[2:])>0,'spline overshoots positive radius; add sections or change boundary conditions');return value
    def sample(t):
        x,z,rx,rz=check(t);return [x-rx,z-rz,x+rx,z+rz]
    ts=[];error=0
    for a,b in zip(knots,knots[1:]):part,e=adaptive_parameters(sample,a,b,tol);ts.extend(part[:-1]);error=max(error,e)
    ts.append(knots[-1]);rings=[]
    capn=p.get('cap_segments',12);need(type(capn)==int and 3<=capn<=128,'cap_segments 3..128')
    def ellipse(x,y,z,rx,rz):return [[x+rx*math.cos(2*math.pi*i/n),y,z+rz*math.sin(2*math.pi*i/n)]for i in range(n)]
    if caps:
        c=centers[0];r=radii[0]
        for i in range(1,capn):a=(1-i/capn)*math.pi/2;rings.append(ellipse(c[0],c[1]-caps[0]*math.sin(a),c[2],r[0]*math.cos(a),r[1]*math.cos(a)))
    for t in ts:x,z,rx,rz=check(t);rings.append(ellipse(x,t,z,rx,rz))
    if caps:
        c=centers[-1];r=radii[-1]
        for i in range(1,capn):a=i/capn*math.pi/2;rings.append(ellipse(c[0],c[1]+caps[1]*math.sin(a),c[2],r[0]*math.cos(a),r[1]*math.cos(a)))
    lower=centers[0].copy();upper=centers[-1].copy()
    if caps:lower[1]-=caps[0];upper[1]+=caps[1]
    pos,tri=ring_mesh(rings,lower,upper)
    return pos,tri,'closed_shell',{'profile_continuity':'C2 within authored scalar splines','rounded_caps':bool(caps),'sampled_profile_chord_error':error,'sampled_sections':len(ts),'radial_segments':n,'cap_join':'G1 analytic at zero-slope elliptical join; mesh is sampled'if caps else'designed flat cap, hard rim'}

def periodic_radius(outline):
    outline=[vector(q,2,'outline point')for q in outline];need(len(outline)>=3,'outline needs >=3 points');theta=[math.atan2(z,x)for x,z in outline];r=[math.hypot(*q)for q in outline];need(min(r)>1e-10,'outline touches origin');x=[theta[0]]
    for i in range(1,len(theta)):
        delta=(theta[i]-theta[i-1])%(2*math.pi);need(1e-10<delta<math.pi,'outline must be star-shaped angular order');x.append(x[-1]+delta)
    end=(theta[0]-theta[-1])%(2*math.pi);need(1e-10<end<math.pi and abs(x[-1]+end-x[0]-2*math.pi)<1e-8,'outline must wind once');x.append(x[0]+2*math.pi);r.append(r[0]);n=len(r)-1
    h=[x[i+1]-x[i]for i in range(n)];d=[(r[i+1]-r[i])/h[i]for i in range(n)];m=[]
    for i in range(n):a,b=d[i-1],d[i];ha,hb=h[i-1],h[i];m.append(0 if a*b<=0 else 3*(ha+hb)/((2*hb+ha)/a+(hb+2*ha)/b))
    m.append(m[0])
    def radius(t):
        t=x[0]+(t-x[0])%(2*math.pi);i=min(n-1,next(j for j in range(n)if t<=x[j+1]));u=(t-x[i])/h[i]
        return (2*u**3-3*u*u+1)*r[i]+(u**3-2*u*u+u)*h[i]*m[i]+(-2*u**3+3*u*u)*r[i+1]+(u**3-u*u)*h[i]*m[i+1]
    return radius,x[0],min(r)

def rounded_outline(p):
    keys(p,('outline','rings','edge_width','angular_segments','profile_segments','edge_segments','center_y','join_slope'),'rounded_outline');rad,start,minrad=periodic_radius(p.get('outline',[]));rings=p.get('rings');need(isinstance(rings,list)and len(rings)>=2,'thickness rings required');fractions=[];heights=[]
    for r in rings:keys(r,('fraction','half_thickness'),'ring');fractions.append(number(r['fraction'],'fraction'));heights.append(number(r['half_thickness'],'half thickness',True))
    slope=number(p.get('join_slope',0),'join_slope');need(slope<=0,'join_slope must be nonpositive for upper outward profile')
    need(fractions[0]==0 and fractions[-1]==1,'rings must cover 0..1');height=CubicProfile(fractions,heights,[0,slope]);width=number(p.get('edge_width'),'edge_width',True);need(width<minrad,'edge_width consumes outline interior')
    need(height.minimum()>0,'thickness spline crosses zero between authored rings')
    na=p.get('angular_segments',64);np=p.get('profile_segments',12);ne=p.get('edge_segments',10);cy=number(p.get('center_y',0),'center_y')
    need(type(na)==int and 12<=na<=512 and type(np)==int and 2<=np<=128 and type(ne)==int and 3<=ne<=128,'invalid rounded outline sampling')
    angles=[start+2*math.pi*i/na for i in range(na)];base=[];positions=[];tri=[];rolls=[]
    for a in angles:
        radius=rad(a);lo,hi=0,math.pi/2-1e-6
        # Match actual d(height)/d(radius), including varying perimeter radius.
        for _ in range(50):
            alpha=(lo+hi)/2;inner=radius-width+width*math.sin(alpha)
            if heights[-1]*math.sin(alpha)/(width*math.cos(alpha)**2)<-slope/inner:lo=alpha
            else:hi=alpha
        alpha=(lo+hi)/2;rolls.append((radius-width+width*math.sin(alpha),alpha,heights[-1]/math.cos(alpha)))
    # Top and bottom radial interiors share the exact rolled perimeter ring.
    for sign in (1,-1):
        pole=len(positions)//3;positions.extend([0,cy+sign*height(0),0]);rows=[]
        for j in range(1,np+1):
            q=j/np;h=height(q);need(h>0,'thickness spline crosses zero');row=[]
            for a,(inner,_,_) in zip(angles,rolls):r=inner*q;row.append(len(positions)//3);positions.extend([r*math.cos(a),cy+sign*h,r*math.sin(a)])
            rows.append(row)
        for i in range(na):tri.extend([pole,rows[0][(i+1)%na],rows[0][i]]if sign>0 else[pole,rows[0][i],rows[0][(i+1)%na]])
        for a,b in zip(rows,rows[1:]):
            for i in range(na):j=(i+1)%na;tri.extend([a[i],a[j],b[i],a[j],b[j],b[i]]if sign>0 else[a[i],b[i],a[j],a[j],b[i],b[j]])
        base.append(rows[-1])
    edge=[base[0]]
    for j in range(1,2*ne):
        row=[]
        for a,(_,alpha,depth) in zip(angles,rolls):phi=alpha+(math.pi-2*alpha)*j/(2*ne);r=rad(a)-width+width*math.sin(phi);row.append(len(positions)//3);positions.extend([r*math.cos(a),cy+depth*math.cos(phi),r*math.sin(a)])
        edge.append(row)
    edge.append(base[1])
    for a,b in zip(edge,edge[1:]):
        for i in range(na):j=(i+1)%na;tri.extend([a[i],a[j],b[i],a[j],b[j],b[i]])
    return positions,tri,'closed_shell',{'profile_continuity':'C2 thickness; C1 periodic shape-preserving perimeter','edge':'continuous elliptical roll with matched authored end slope, no straight side-wall strip','edge_width':width,'join_slope':slope,'midplane_outline_preserved':True,'limitations':['Star-shaped radial profiles only, not arbitrary holes or geodesic constant-radius bevels.','G1 profile join is analytic before sampling; no global G2 guarantee.']}

def spline_vectors(points):
    points=[vector(q,3,'curve point')for q in points];need(len(points)>=2,'curve points required');t=[i/(len(points)-1)for i in range(len(points))];f=[CubicProfile(t,[p[k]for p in points])for k in range(3)];return lambda u:[g(u)for g in f]
def grid_mesh(fn,nu,nv):
    need(type(nu)==int and type(nv)==int and 2<=nu<=256 and 2<=nv<=256,'grid segments 2..256');pos=[x for j in range(nv+1)for i in range(nu+1)for x in fn(i/nu,j/nv)];tri=[]
    for j in range(nv):
        for i in range(nu):a=j*(nu+1)+i;b=a+1;c=a+nu+1;tri.extend([a,b,c,b,c+1,c])
    return pos,tri

def blend_strip(p):
    keys(p,('a','b','a_inward','b_inward','segments'),'blend_strip');fields=[spline_vectors(p[k])for k in ('a','b','a_inward','b_inward')];segments=p.get('segments',[32,16]);need(len(segments)==2,'strip segments required')
    def sample(u,v):
        a,b,da,db=[f(u)for f in fields];return add(add(scale(a,2*v**3-3*v*v+1),scale(b,-2*v**3+3*v*v)),add(scale(da,v**3-2*v*v+v),scale(db,-(v**3-v*v))))
    pos,tri=grid_mesh(sample,*segments);return pos,tri,'open_patch',{'cross_profile':'cubic Hermite with explicit inward derivatives','continuity':'authored boundary/tangent conditions, neighbors checked separately'}

def corner_patch(p):
    keys(p,('boundaries','cross_derivatives','continuity','tolerance','segments'),'corner_patch');bounds=p.get('boundaries',{});need(set(bounds)=={'u0','u1','v0','v1'},'four cubic boundaries required');bounds={k:[vector(q,3,'boundary')for q in v]for k,v in bounds.items()};need(all(len(v)==4 for v in bounds.values()),'cubic boundary needs four controls');tol=number(p.get('tolerance',1e-8),'tolerance',True);grid=[[None]*4 for _ in range(4)]
    def assign(i,j,q):
        if grid[i][j]is not None:need(length(sub(grid[i][j],q))<=tol,'incompatible corner boundary/tangent conditions')
        else:grid[i][j]=q
    for j in range(4):assign(0,j,bounds['u0'][j]);assign(3,j,bounds['u1'][j])
    for i in range(4):assign(i,0,bounds['v0'][i]);assign(i,3,bounds['v1'][i])
    mode=p.get('continuity','position');need(mode in ('position','tangent'),'corner continuity unsupported');cross=p.get('cross_derivatives')
    if mode=='tangent':
        need(isinstance(cross,dict)and set(cross)==set(bounds),'tangent mode needs four inward derivative control fields')
        for edge,rows in cross.items():
            need(len(rows)==4,'four derivative controls required')
            for k,d in enumerate(rows):
                d=vector(d,3,'cross derivative');q=add(bounds[edge][k],scale(d,1/3));i,j={'u0':(1,k),'u1':(2,k),'v0':(k,1),'v1':(k,2)}[edge];assign(i,j,q)
    else:
        need(cross is None,'derivative fields require tangent mode')
        # Bicubic Coons control net; boundary interpolation alone does not certify G1.
        for i in (1,2):
            for j in (1,2):
                u,v=i/3,j/3;bilinear=add(add(scale(grid[0][0],(1-u)*(1-v)),scale(grid[3][0],u*(1-v))),add(scale(grid[0][3],(1-u)*v),scale(grid[3][3],u*v)))
                grid[i][j]=sub(add(add(scale(bounds['v0'][i],1-v),scale(bounds['v1'][i],v)),add(scale(bounds['u0'][j],1-u),scale(bounds['u1'][j],u))),bilinear)
    from bezier_network import evaluate
    seg=p.get('segments',[16,16]);pos,tri=grid_mesh(lambda u,v:evaluate(grid,u,v)[0],*seg)
    return pos,tri,'open_patch',{'continuity':mode,'control_net':grid,'limitations':['Compatible bicubic four-boundary patch only; sampled mesh, no arbitrary junction/G2 solver.']}

def rounded_corner(p):
    keys(p,('center','radii','octant','segments'),'rounded_corner');c=vector(p.get('center',[0,0,0]),3,'center');r=vector(p.get('radii',[1,1,1]),3,'radii');sign=p.get('octant',[1,1,1]);need(min(r)>0 and len(sign)==3 and all(v in (-1,1)for v in sign),'positive radii and signed octant required');n=p.get('segments',16);need(type(n)==int and 3<=n<=128,'corner segments 3..128');pos=[];rows=[];tri=[]
    for i in range(n+1):
        row=[]
        for j in range(n-i+1):
            q=[i/n,j/n,(n-i-j)/n];s=length(q);row.append(len(pos)//3);pos.extend([c[k]+sign[k]*r[k]*q[k]/s for k in range(3)])
        rows.append(row)
    for i in range(n):
        for j in range(n-i):
            a=rows[i][j];b=rows[i+1][j];d=rows[i][j+1];tri.extend([a,b,d])
            if j<n-i-1:tri.extend([b,rows[i+1][j+1],d])
    if sign[0]*sign[1]*sign[2]<0:tri=[q for k in range(0,len(tri),3)for q in (tri[k],tri[k+2],tri[k+1])]
    return pos,tri,'open_patch',{'surface':'ellipsoid octant','continuity':'G1 with compatible adjacent elliptic-cylinder extrusions; not G2','limitations':['Orthogonal three-plane node only; no automatic attachment or trimming.']}

METHODS={'smooth_loft':smooth_loft,'rounded_outline':rounded_outline,'blend_strip':blend_strip,'corner_patch':corner_patch,'rounded_corner':rounded_corner}
def compile_surface(recipe):
    keys(recipe,('version','component_id','source','rationale','method','parameters'),'surface recipe');need(type(recipe.get('version'))==int and recipe['version']==1,'surface recipe version1 required');need(all(isinstance(recipe.get(k),str)and recipe[k].strip()for k in ('component_id','rationale')),'component/rationale required');source=recipe.get('source',{});keys(source,('reference_id','roi','evidence_path'),'source');need(isinstance(source.get('reference_id'),str)and source['reference_id'].strip(),'source reference required');roi=vector(source.get('roi'),4,'source ROI');need(min(roi[:2])>=0 and min(roi[2:])>0,'ROI requires xy/width/height');method=recipe.get('method');need(method in METHODS,'unsupported surface method')
    pos,tri,contract,details=METHODS[method](recipe.get('parameters',{}));need(len(pos)//3<=300000,'surface vertex budget exceeded');mesh=normmesh(pos,tri);quality=mesh_report({'id':recipe['component_id'],'contract':contract,'positions':pos,'triangles':tri});need(quality['passed'],'invalid surface topology: '+str(quality['errors']))
    return {'geometry':{'type':'mesh','positions':pos,'triangles':tri,'normals':mesh['normals']},'report':{'version':1,'method':method,'contract':contract,'source':source,'parameters_hash':hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),'topology':quality,'vertex_count':len(pos)//3,'triangle_count':len(tri)//3,'construction':details,'visual_certified':False,'scope':'authored parametric geometry; reference likeness and assembled continuity require review'}}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('recipe');ap.add_argument('--out',required=True);ap.add_argument('--report',required=True);a=ap.parse_args()
    try:
        need(Path(a.out).resolve()!=Path(a.report).resolve(),'output and report paths must differ')
        need(not Path(a.out).exists()and not Path(a.report).exists(),'output exists; preserve baseline');r=compile_surface(json.loads(Path(a.recipe).read_text()))
        for path,value in ((a.out,r['geometry']),(a.report,r['report'])):Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(r['report'],ensure_ascii=False));return 0
    except(ValueError,OSError,KeyError,TypeError)as e:print(json.dumps({'passed':False,'error':str(e)},ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())
