"""Render a fixed-seat 2:1 panorama from a prepared Blender cabin; no source edits."""
import bpy,argparse,sys,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--eye',type=float,nargs=3,required=True);p.add_argument('--width',type=int,default=2048);p.add_argument('--samples',type=int,default=32);p.add_argument('--fill',type=float,default=0);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
if a.out.exists():raise ValueError('Output exists; use a new path')
if a.width<256 or a.width%2:raise ValueError('Width must be even and at least 256')
bpy.ops.wm.open_mainfile(filepath=str(a.input.resolve()));scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=a.samples;scene.cycles.use_denoising=True
bpy.ops.object.camera_add(location=a.eye);cam=bpy.context.object;cam.rotation_euler=(math.pi/2,0,-math.pi/2);cam.data.type='PANO';cam.data.panorama_type='EQUIRECTANGULAR';cam.data.clip_start=.01;scene.camera=cam
if a.fill>0:
 d=bpy.data.lights.new('PanoramaFill','POINT');d.energy=a.fill;d.shadow_soft_size=.3;o=bpy.data.objects.new('PanoramaFill',d);scene.collection.objects.link(o);o.location=(a.eye[0],a.eye[1],a.eye[2]+.12)
scene.render.resolution_x=a.width;scene.render.resolution_y=a.width//2;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';a.out.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(a.out.resolve());bpy.ops.render.render(write_still=True);print('PANORAMA_DONE',str(a.out))
