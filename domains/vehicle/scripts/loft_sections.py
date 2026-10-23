"""Explicit section loft for Blender stages. Does not infer sections from images."""
import math

def geometry(plan):
    if plan.get('schema_version')!=1 or not plan.get('evidence'):raise ValueError('Section plan needs version and evidence')
    sections=plan.get('sections',[])
    if len(sections)<2:raise ValueError('At least two sections required')
    count=len(sections[0]['profile'])
    if count<3:raise ValueError('Profile needs at least three points')
    vertices=[];previous=-float('inf');winding=None
    for section in sections:
        x=section['station'];profile=section['profile']
        if not isinstance(x,(int,float)) or not math.isfinite(x) or x<=previous or len(profile)!=count:raise ValueError('Increasing finite stations and identical profile counts required')
        if len({tuple(p) for p in profile})!=count:raise ValueError('Duplicate profile point')
        if any(len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in p) for p in profile):raise ValueError('Finite profile coordinates required')
        area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(profile,profile[1:]+profile[:1]))
        if abs(area)<1e-9:raise ValueError('Degenerate profile')
        if winding is not None and area*winding<0:raise ValueError('Inconsistent profile winding')
        winding=area
        vertices.extend((x,y,z) for y,z in profile);previous=x
    faces=[(i*count+j,i*count+(j+1)%count,(i+1)*count+(j+1)%count,(i+1)*count+j) for i in range(len(sections)-1) for j in range(count)]
    if plan.get('caps',True):faces += [tuple(range(count-1,-1,-1)),tuple(range((len(sections)-1)*count,len(sections)*count))]
    return vertices,faces

def make_loft(plan):
    import bpy,bmesh
    name=plan.get('name','SectionLoft')
    if bpy.data.objects.get(name):raise ValueError('Refuse replacing existing object: '+name)
    vertices,faces=geometry(plan);data=bpy.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
    bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free()
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
    material=plan.get('material')
    if material:
        mat=bpy.data.materials.get(material)
        if not mat:raise ValueError('Create explicit material before loft: '+material)
        obj.data.materials.append(mat)
    for face in data.polygons:face.use_smooth=plan.get('smooth',True)
    return obj

if 'PARAMS' in globals():make_loft(PARAMS['loft'])
