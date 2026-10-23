"""Ray-project a supplied star-shaped patch onto evaluated Blender geometry.
The target is read-only. Semantic region, ray plane and offset are task inputs.
"""
def conform_patch(target,boundary_origins,direction,offset=.005,rings=16):
    import bpy,math
    from mathutils import Vector
    n=len(boundary_origins)
    if target.type!='MESH' or not 3<=n<=4096 or not isinstance(rings,int) or not 1<=rings<=64 or not math.isfinite(offset) or offset<=0:raise ValueError('Invalid patch target or sampling parameters')
    origins=[Vector(p) for p in boundary_origins];ray=Vector(direction)
    if ray.length==0 or any(not math.isfinite(v) for p in origins+[ray] for v in p):raise ValueError('Finite nonzero projection rays required')
    ray.normalize();center=sum(origins,Vector())/n
    evaluated=target.evaluated_get(bpy.context.evaluated_depsgraph_get());matrix=evaluated.matrix_world;inverse=matrix.inverted();normal_matrix=inverse.transposed().to_3x3();local_ray=(inverse.to_3x3()@ray).normalized()
    def hit(origin):
        ok,point,normal,_=evaluated.ray_cast(inverse@origin,local_ray)
        if not ok:raise ValueError('Patch ray missed actual target; revise boundary before continuing')
        world=matrix@point;normal=(normal_matrix@normal).normalized()
        if normal.dot(ray)>0:normal.negate()
        return tuple(world+normal*offset)
    vertices=[hit(center)]
    for k in range(1,rings+1):vertices.extend(hit(center+(p-center)*(k/rings)) for p in origins)
    faces=[(0,1+j,1+(j+1)%n) for j in range(n)]
    for k in range(rings-1):
        a=1+k*n;b=a+n
        faces.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
    return vertices,faces
