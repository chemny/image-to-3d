"""Internal .blend to GLB worker, opens preserved copy; never saves over original."""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--source-dir',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.open_mainfile(filepath=str(a.input));meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:raise ValueError('No mesh to export')
if bpy.data.libraries:raise ValueError('Linked libraries require an explicitly resolved self-contained copy before GLB export')
external_images=[]
for image in bpy.data.images:
 if image.type=='RENDER_RESULT' or image.packed_file:continue
 if image.source in ('MOVIE','SEQUENCE'):raise ValueError('Movie/sequence image requires a deliberate static-frame conversion')
 if image.source=='FILE':
  source=Path(bpy.path.abspath(image.filepath,start=str(a.source_dir))).resolve()
  if not source.is_file():raise ValueError('Missing external texture: '+str(source))
  external_images.append({'name':image.name,'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
  image.filepath=str(source);image.reload();image.pack()

source={'mesh_nodes':[{'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),'uv_layers':[u.name for u in o.data.uv_layers],'materials':[m.name if m else None for m in o.data.materials],'modifiers':[{'type':m.type,'name':m.name} for m in o.modifiers]} for o in meshes],
 'materials':[{'name':m.name,'node_types':[n.bl_idname for n in m.node_tree.nodes] if m.use_nodes else [],'review_required':any(n.type not in ('OUTPUT_MATERIAL','BSDF_PRINCIPLED','TEX_IMAGE','NORMAL_MAP','UV_MAP','TEX_COORD','MAPPING','VALUE','RGB','REROUTE') for n in m.node_tree.nodes) if m.use_nodes else True} for m in bpy.data.materials],
 'images':[{'name':i.name,'size':list(i.size),'packed':bool(i.packed_file),'filepath':i.filepath} for i in bpy.data.images if i.type!='RENDER_RESULT'],'animation_review':'not_verified','external_images_packed_into_derived_glb':external_images}
(a.out/'blend-inventory.json').write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n')
bpy.ops.export_scene.gltf(filepath=str(a.out/'model.glb'),export_format='GLB',export_apply=True)
