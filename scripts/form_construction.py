#!/usr/bin/env python3
"""Deterministic authored form recipes -> explicit scene_build meshes.

No image inference: source records attribution, not a claim of measured truth.
Lofts have parallel XZ sections and strictly increasing Y. Thick outlines are
star-shaped radial polygons in XZ; positive half-thickness creates a closed side
wall. Normals are shared/smooth at rims and caps. Neither method guarantees a
visually accurate shape, tangent continuity, or collision-free assembly.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from scene_build import normmesh
from mesh_checks import mesh_report


def _number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
        raise ValueError(label+' must be finite')
    if positive and value <= 0:
        raise ValueError(label+' must be positive')
    return value


def _vector(value, size, label):
    if not isinstance(value,list) or len(value)!=size:
        raise ValueError(label+' vector size')
    return [_number(v,label) for v in value]


def _keys(value, allowed, label):
    if not isinstance(value,dict) or set(value)-set(allowed):
        raise ValueError(label+' has unknown fields or is not an object')


def _loft(p):
    _keys(p,('sections','radial_segments'),'loft parameters')
    sections=p.get('sections');n=p.get('radial_segments',32)
    if type(n)!=int or not 8<=n<=128:raise ValueError('radial_segments must be integer 8..128')
    if not isinstance(sections,list) or not 2<=len(sections)<=256:raise ValueError('need 2..256 sections')
    vertices=[];indices=[];centers=[]
    for section in sections:
        _keys(section,('center','radii'),'section')
        c=_vector(section.get('center'),3,'center');r=_vector(section.get('radii'),2,'radii')
        if min(r)<=0:raise ValueError('radii must be positive')
        if centers and c[1]<=centers[-1][1]:raise ValueError('section Y must strictly increase')
        centers.append(c)
        for i in range(n):
            angle=2*math.pi*i/n
            vertices.extend([c[0]+r[0]*math.cos(angle),c[1],c[2]+r[1]*math.sin(angle)])
    for j in range(len(sections)-1):
        for i in range(n):
            a=j*n+i;b=j*n+(i+1)%n;d=b+n;c=a+n
            indices.extend([a,c,b,b,c,d])
    for j,bottom in ((0,True),(len(sections)-1,False)):
        k=len(vertices)//3;vertices.extend(centers[j])
        for i in range(n):
            a=j*n+i;b=j*n+(i+1)%n
            indices.extend([k,a,b] if bottom else [k,b,a])
    return vertices,indices,{'section_count':len(sections),'radial_segments':n}


def _thick_outline(p):
    _keys(p,('outline','rings','center_y','inner_outline_ellipse','outline_influence_power'),'thick_outline parameters')
    outline=p.get('outline');rings=p.get('rings');cy=_number(p.get('center_y',0),'center_y')
    if not isinstance(outline,list) or not 3<=len(outline)<=512:raise ValueError('outline needs 3..512 points')
    outline=[_vector(v,2,'outline') for v in outline]
    # Every directed edge must sweep strictly between 0 and pi around origin.
    # With one complete angular turn this makes a simple radial/star polygon;
    # negative or zero winding, duplicate rays and multi-turn order are rejected.
    angles=[math.atan2(z,x) for x,z in outline];total=0
    for i,(x,z) in enumerate(outline):
        if math.hypot(x,z)<=1e-12:raise ValueError('outline cannot touch origin')
        delta=(angles[(i+1)%len(angles)]-angles[i])%(2*math.pi)
        if not 1e-10<delta<math.pi-1e-10:raise ValueError('outline requires increasing polar angles and gaps below pi')
        total+=delta
    if abs(total-2*math.pi)>1e-8:raise ValueError('outline must wind exactly once')
    if not isinstance(rings,list) or not 2<=len(rings)<=128:raise ValueError('need 2..128 thickness rings')
    previous=-1
    for ring in rings:
        _keys(ring,('fraction','half_thickness'),'ring')
        f=_number(ring.get('fraction'),'fraction');_number(ring.get('half_thickness'),'half_thickness',True)
        if not 0<=f<=1 or f<=previous:raise ValueError('ring fractions must strictly increase in 0..1')
        previous=f
    if rings[0]['fraction']!=0 or rings[-1]['fraction']!=1:raise ValueError('rings must span fraction 0 to 1')
    ellipse=p.get('inner_outline_ellipse')
    power=_number(p.get('outline_influence_power',1),'outline_influence_power')
    if power<1:raise ValueError('outline_influence_power must be at least 1')
    if ellipse is not None:
        ellipse=_vector(ellipse,2,'inner_outline_ellipse')
        if min(ellipse)<=0:raise ValueError('inner ellipse radii must be positive')
    elif 'outline_influence_power' in p:
        raise ValueError('outline_influence_power requires inner_outline_ellipse')
    if ellipse is not None:
        for x,z in outline:
            factor=1/math.sqrt((x/ellipse[0])**2+(z/ellipse[1])**2)
            previous_radius=0
            for ring in rings[1:]:
                f=ring['fraction'];influence=f**power
                radius=f*((1-influence)*factor+influence)
                if radius<=previous_radius:raise ValueError('inner ellipse causes overlapping radial rings')
                previous_radius=radius
    vertices=[];indices=[];n=len(outline);sides=[]
    for sign in (1,-1):
        center=len(vertices)//3;vertices.extend([0,cy+sign*rings[0]['half_thickness'],0]);rows=[]
        for ring in rings[1:]:
            row=len(vertices)//3;rows.append(row)
            for x,z in outline:
                f=ring['fraction'];px,pz=x,z
                if ellipse is not None:
                    # Intersection on the SAME ray retains strict polar order.
                    # Interior convex profile fades into exact authored perimeter.
                    factor=1/math.sqrt((x/ellipse[0])**2+(z/ellipse[1])**2)
                    influence=f**power
                    blend=(1-influence)*factor+influence
                    px,pz=x*blend,z*blend
                vertices.extend([px*f,cy+sign*ring['half_thickness'],pz*f])
        # XZ positive angular order points down; reverse for top.
        tris=[]
        for i in range(n):tris.extend([center,rows[0]+(i+1)%n,rows[0]+i])
        for r0,r1 in zip(rows,rows[1:]):
            for i in range(n):
                a=r0+i;b=r0+(i+1)%n;c=r1+i;d=r1+(i+1)%n
                tris.extend([a,b,c,b,d,c])
        if sign<0:
            for k in range(0,len(tris),3):tris[k+1],tris[k+2]=tris[k+2],tris[k+1]
        indices.extend(tris);sides.append(rows[-1])
    upper,lower=sides
    for i in range(n):
        a=upper+i;b=upper+(i+1)%n;c=lower+i;d=lower+(i+1)%n
        indices.extend([a,b,c,b,d,c])
    return vertices,indices,{'outline_count':n,'ring_count':len(rings)}


def compile_recipe(recipe):
    """Return {geometry, report}; reject unsupported/degenerate recipes."""
    _keys(recipe,('version','component_id','source','rationale','method','parameters'),'recipe')
    if type(recipe.get('version'))!=int or recipe['version']!=1:raise ValueError('recipe version must be 1')
    for key in ('component_id','rationale'):
        if not isinstance(recipe.get(key),str) or not recipe[key].strip():raise ValueError(key+' required')
    source=recipe.get('source');_keys(source,('reference_id','roi','evidence_path'),'source')
    if not isinstance(source.get('reference_id'),str) or not source['reference_id'].strip():raise ValueError('source reference_id required')
    roi=_vector(source.get('roi'),4,'source roi')
    if min(roi[:2])<0 or min(roi[2:])<=0:raise ValueError('ROI requires nonnegative x/y and positive width/height')
    if 'evidence_path' in source and (not isinstance(source['evidence_path'],str) or not source['evidence_path'].strip()):raise ValueError('invalid evidence_path')
    method=recipe.get('method')
    if method not in ('loft','thick_outline'):raise ValueError('unsupported construction method')
    positions,triangles,details=(_loft if method=='loft' else _thick_outline)(recipe.get('parameters'))
    mesh=normmesh(positions,triangles)
    checked=mesh_report({'id':recipe['component_id'],'contract':'closed_shell','positions':positions,'triangles':triangles})
    if not checked['passed']:raise ValueError('invalid generated topology: '+str(checked['errors']))
    volume=0
    for i in range(0,len(triangles),3):
        a,b,c=[positions[k*3:k*3+3] for k in triangles[i:i+3]]
        volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    if not math.isfinite(volume) or volume<=0:raise ValueError('generated shell must have positive signed volume')
    canonical=json.dumps(recipe,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return {'geometry':{'type':'mesh','positions':positions,'triangles':triangles,'normals':mesh['normals']},
            'report':{'version':1,'component_id':recipe['component_id'],'method':method,
                      'recipe_sha256':hashlib.sha256(canonical).hexdigest(),'source':source,
                      'topology':checked,'signed_volume':volume,'vertex_count':len(positions)//3,
                      'triangle_count':len(triangles)//3,'construction':details,
                      'visual_accuracy_checked':False,'source_image_verified':False,
                      'limitations':['Authored parameters; no image inference or camera fitting.',
                          'Piecewise linear sections/rings; shared smooth normals do not guarantee tangent continuity.',
                          'No assembly collision test. Source image existence and ROI bounds require reference contract validation.']}}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('recipe');parser.add_argument('--out',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    try:
        result=compile_recipe(json.loads(Path(args.recipe).read_text()))
        if Path(args.out).resolve()==Path(args.report).resolve():raise ValueError('output and report paths must differ')
        if Path(args.recipe).resolve() in (Path(args.out).resolve(),Path(args.report).resolve()):raise ValueError('cannot overwrite recipe input')
        for name,key in ((args.out,'geometry'),(args.report,'report')):
            Path(name).write_text(json.dumps(result[key],indent=2,allow_nan=False)+'\n')
        print(json.dumps({'component_id':result['report']['component_id'],'triangles':result['report']['triangle_count'],'visual_accuracy_checked':False}));return 0
    except (ValueError,TypeError,KeyError,OSError) as exc:
        parser.exit(1,str(exc)+'\n')

if __name__=='__main__':raise SystemExit(main())
