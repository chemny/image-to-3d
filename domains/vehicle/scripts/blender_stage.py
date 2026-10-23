"""Internal Blender worker. Stage script receives PARAMS, JOB_DIR and bpy."""
import argparse, hashlib, json, math, runpy, sys
from pathlib import Path
import bpy
from mathutils import Vector,Euler
p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);job=a.job
params=json.loads((job/'parameters.json').read_text());manifest=json.loads((job/'job.json').read_text())
if manifest['input']:
 path=manifest['input']
 if path.lower().endswith('.blend'):bpy.ops.wm.open_mainfile(filepath=path)
 else:bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=path)
else:bpy.ops.wm.read_factory_settings(use_empty=True)
def fingerprints():
 result={}
 for o in bpy.context.scene.objects:
  if o.type!='MESH':continue
  payload={'vertices':[list(v.co) for v in o.data.vertices],'polygons':[list(p.vertices) for p in o.data.polygons],'transform':[list(row) for row in o.matrix_world],'materials':[m.name if m else None for m in o.data.materials],'material_indices':[p.material_index for p in o.data.polygons],'uv_layers':{u.name:[list(d.uv) for d in u.data] for u in o.data.uv_layers}}
  result[o.name]=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
 return result
def material_fingerprints():
 result={}
 for m in bpy.data.materials:
  nodes=[]
  if m.use_nodes:
   for n in m.node_tree.nodes:
    inputs=[]
    for socket in n.inputs:
     if not hasattr(socket,'default_value'):continue
     v=socket.default_value
     if isinstance(v,(int,float,str,bool)):inputs.append((socket.name,v))
     elif hasattr(v,'__len__'):
      try:inputs.append((socket.name,list(v)))
      except TypeError:pass
    nodes.append({'name':n.name,'type':n.type,'inputs':inputs,'image':n.image.name if n.type=='TEX_IMAGE' and n.image else None})
  payload={'diffuse':list(m.diffuse_color),'use_nodes':m.use_nodes,'nodes':nodes,'links':[(l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name) for l in m.node_tree.links] if m.use_nodes else []}
  result[m.name]=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
 return result
def image_fingerprints():
 result={}
 for i in bpy.data.images:
  if i.type=='RENDER_RESULT':continue
  payload={'size':list(i.size),'source':i.source,'filepath':i.filepath,'colorspace':i.colorspace_settings.name,'bytes':hashlib.sha256(i.packed_file.data).hexdigest() if i.packed_file else None}
  # Hash current pixels as well: a script can change decoded content without repacking.
  if i.has_data:
   from array import array
   pixels=array('f',[0.0])*len(i.pixels);i.pixels.foreach_get(pixels);payload['pixels']=hashlib.sha256(pixels.tobytes()).hexdigest()
  result[i.name]=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
 return result
before=fingerprints();before_materials=material_fingerprints();before_images=image_fingerprints()
runpy.run_path(str(job/'stage.py'),init_globals={'PARAMS':params,'JOB_DIR':job,'bpy':bpy})
bpy.context.view_layer.update();after=fingerprints()
after_materials=material_fingerprints();after_images=image_fingerprints()
changed_materials=sorted(k for k in before_materials.keys()|after_materials.keys() if before_materials.get(k)!=after_materials.get(k))
changed_images=sorted(k for k in before_images.keys()|after_images.keys() if before_images.get(k)!=after_images.get(k))
for key,changed_assets in [('allowed_material_names',changed_materials),('allowed_image_names',changed_images)]:
 allowed_assets=params.get(key)
 if allowed_assets is not None and any(k not in allowed_assets for k in changed_assets):raise ValueError('Unexpected protected asset changes: '+key+' '+repr(changed_assets))
changed=sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))
allowed=params.get('allowed_change_prefixes')
if allowed is not None:
 unexpected=[k for k in changed if not any(k.startswith(p) for p in allowed)]
 if unexpected:raise ValueError('Unexpected mesh changes: '+repr(unexpected[:20]))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:raise ValueError('No mesh output')
points=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
lo=Vector([min(p[i] for p in points) for i in range(3)]);hi=Vector([max(p[i] for p in points) for i in range(3)])
if not all(math.isfinite(v) for o in meshes for vtx in o.data.vertices for v in vtx.co):raise ValueError('Nonfinite geometry')
required=params.get('required_nodes',[]);missing=[n for n in required if bpy.data.objects.get(n) is None]
result={'stage':manifest['stage'],'mesh_count':len(meshes),'dimensions':list(hi-lo),'changed_meshes':changed,'changed_materials':changed_materials,'changed_images':changed_images,'unchanged_mesh_count':sum(before.get(k)==after.get(k) for k in before if k in after),'checks':{'missing_required_nodes':missing},'visual_verdict':'not_reviewed','previews':[],'cameras':[]}
# Save asset before adding review cameras/lights or hiding variant meshes.
bpy.ops.wm.save_as_mainfile(filepath=str(job/'model.blend'))
bpy.ops.export_scene.gltf(filepath=str(job/'model.glb'),export_format='GLB',export_apply=True)
result['blend_sha256']=hashlib.sha256((job/'model.blend').read_bytes()).hexdigest();result['glb_sha256']=hashlib.sha256((job/'model.glb').read_bytes()).hexdigest()
scene=bpy.context.scene
for o in scene.objects:
 if o.type in ('LIGHT','CAMERA'):o.hide_render=True
 for prefix in params.get('preview_hide_prefixes',[]):
  if o.name.startswith(prefix):
   o.hide_render=True
   for child in o.children_recursive:child.hide_render=True
world=bpy.data.worlds.new('PipelineReviewWorld');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.3,.3,.3,1);scene.world=world
scene.render.engine='CYCLES';scene.cycles.samples=params.get('samples',8);scene.cycles.use_denoising=True
scene.render.resolution_x=params.get('resolution',[800,600])[0];scene.render.resolution_y=params.get('resolution',[800,600])[1];scene.render.resolution_percentage=100
for loc,power,size in [((3,4,7),1700,6),((-4,-3,5),1200,5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.rotation_euler=((hi+lo)/2-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add();cam=bpy.context.object;scene.camera=cam
clay=bpy.data.materials.new('PipelineClay');clay.diffuse_color=(.5,.5,.5,1)
for view in params.get('views',[]):
 name=view['name']
 if not name.replace('_','').replace('-','').isalnum():raise ValueError('Unsafe preview name')
 cam.location=view['position'];cam.rotation_euler=Euler(tuple(view['rotation_euler']),'XYZ') if 'rotation_euler' in view else (Vector(view['target'])-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type=view.get('type','ORTHO');cam.data.ortho_scale=view.get('scale',7);cam.data.lens=view.get('lens',50);cam.data.sensor_fit=view.get('sensor_fit','AUTO');cam.data.sensor_width=view.get('sensor_width',36)
 scene.view_layers[0].material_override=clay if view.get('clay',False) else None
 result['cameras'].append({'name':name,'position':list(cam.location),'rotation_euler':list(cam.rotation_euler),'type':cam.data.type,'sensor_fit':cam.data.sensor_fit,'sensor_width':cam.data.sensor_width,'lens':cam.data.lens,'ortho_scale':cam.data.ortho_scale})
 dest=job/(name+'.png');scene.render.filepath=str(dest);bpy.ops.render.render(write_still=True);result['previews'].append(str(dest))
(job/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('PIPELINE_STAGE_DONE',manifest['stage'])
