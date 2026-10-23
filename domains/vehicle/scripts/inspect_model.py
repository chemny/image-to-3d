"""blender --background --factory-startup --python inspect_model.py -- --input model.glb --out review [--render]"""
import argparse,json,sys,math,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--render',action='store_true');p.add_argument('--save-blend',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
source_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest()
if a.input.suffix.lower() not in ('.glb','.blend'):raise ValueError('Only GLB and .blend supported')
if a.out.exists():raise ValueError('Use a new review directory')
if a.input.suffix.lower()=='.blend':bpy.ops.wm.open_mainfile(filepath=str(a.input.resolve()))
else:
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(a.input.resolve()))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:raise ValueError('Model has no meshes')
points=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
lo=Vector(tuple(min(v[i] for v in points) for i in range(3)));hi=Vector(tuple(max(v[i] for v in points) for i in range(3)));center=(lo+hi)/2
report={'source':str(a.input.resolve()),'source_sha256':source_sha256,'coordinates':{'up':'+Z','scale':'authored units not verified'},'mesh_count':len(meshes),'bounds_min':list(lo),'bounds_max':list(hi),'dimensions':list(hi-lo),'objects':[],'visual_verdict':'not_reviewed'}
for o in bpy.context.scene.objects:
 row={'name':o.name,'type':o.type,'parent':o.parent.name if o.parent else None}
 if o.type=='MESH':
  o.data.calc_loop_triangles();row.update(vertices=len(o.data.vertices),triangles=len(o.data.loop_triangles),materials=[m.name if m else None for m in o.data.materials],uv_layers=[u.name for u in o.data.uv_layers],material_slot_faces={str(i):sum(p.material_index==i for p in o.data.polygons) for i in range(len(o.data.materials))})
 report['objects'].append(row)
report['materials']=[]
for m in bpy.data.materials:
 nodes=[]
 if m.use_nodes:
  for n in m.node_tree.nodes:
   values={}
   for socket in n.inputs:
    if hasattr(socket,'default_value'):
     value=socket.default_value
     if isinstance(value,(int,float,str,bool)):values[socket.name]=value
     elif hasattr(value,'__len__'):
      try:values[socket.name]=list(value)
      except TypeError:pass
   nodes.append({'name':n.name,'type':n.type,'image':n.image.name if n.type=='TEX_IMAGE' and n.image else None,'inputs':values})
 report['materials'].append({'name':m.name,'diffuse_color':list(m.diffuse_color),'nodes':nodes,'links':[{'from':l.from_node.name+'.'+l.from_socket.name,'to':l.to_node.name+'.'+l.to_socket.name} for l in m.node_tree.links] if m.use_nodes else []})
report['images']=[{'name':i.name,'size':list(i.size),'filepath':i.filepath,'color_space':i.colorspace_settings.name,'packed_sha256':hashlib.sha256(i.packed_file.data).hexdigest() if i.packed_file else None} for i in bpy.data.images]
a.out.mkdir(parents=True);
if a.save_blend:bpy.ops.wm.save_as_mainfile(filepath=str((a.out/'imported-baseline.blend').resolve()))
(a.out/'inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
if a.render:
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=8;scene.cycles.use_denoising=True
 scene.render.resolution_x=640;scene.render.resolution_y=480;scene.render.resolution_percentage=100
 # Use an override material so references reveal geometry, not photographed detail.
 clay=bpy.data.materials.new('ReviewClay');clay.diffuse_color=(.45,.45,.45,1);scene.view_layers[0].material_override=clay
 world=bpy.data.worlds.new('ReviewWorld');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.5,.5,.5,1);scene.world=world
 radius=max((hi-lo).length,1)*1.1
 bpy.ops.object.camera_add();cam=bpy.context.object;scene.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=max(hi-lo)*1.5
 for label,vec in [('plus_x',(1,0,.05)),('minus_x',(-1,0,.05)),('plus_y',(0,1,.05)),('minus_y',(0,-1,.05)),('diagonal',(1,1,.5)),('top',(0,0,1))]:
  cam.location=center+Vector(vec).normalized()*radius;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str((a.out/(label+'.png')).resolve());bpy.ops.render.render(write_still=True)
if hashlib.sha256(a.input.read_bytes()).hexdigest()!=source_sha256:raise RuntimeError('Source changed')
print('INSPECTION_DONE',str(a.out.resolve()))
