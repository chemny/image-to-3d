#!/usr/bin/env python3
"""Run with Blender --background --python THIS -- --glb FILE --out REPORT."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def main():
    import bpy
    from mathutils import Vector
    p=argparse.ArgumentParser();p.add_argument('--glb',required=True);p.add_argument('--out',required=True);p.add_argument('--manifest');a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    dest=Path(a.out)
    if dest.exists():raise ValueError('report must be a new file')
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        result=bpy.ops.import_scene.gltf(filepath=str(Path(a.glb).resolve()))
        if 'FINISHED' not in result:raise ValueError('Blender glTF importer did not finish')
        bpy.context.scene.frame_set(0);bpy.context.view_layer.update()
        objects=list(bpy.context.scene.objects);meshes=[o for o in objects if o.type=='MESH'];cameras=[o for o in objects if o.type=='CAMERA']
        # Convert Blender world coordinates (X,Y,Z) back to glTF (X,Z,-Y).
        def bounds(obj):
            points=[obj.matrix_world@v.co for v in obj.data.vertices]
            points=[(v.x,v.z,-v.y) for v in points]
            return {'min':[min(v[i] for v in points) for i in range(3)],'max':[max(v[i] for v in points) for i in range(3)]}
        world=[bounds(o) for o in meshes]
        total={'min':[min(b['min'][i] for b in world) for i in range(3)],'max':[max(b['max'][i] for b in world) for i in range(3)]} if world else None
        components={o.get('component_id'):o for o in objects if o.get('component_id')}
        material_ids=sorted({m.get('material_id',m.name) for m in bpy.data.materials})
        animations=[]
        for ac in bpy.data.actions:
            curves=list(ac.fcurves) if hasattr(ac,'fcurves') else []
            if hasattr(ac,'layers'):
                for layer in ac.layers:
                    for strip in layer.strips:
                        if hasattr(strip,'channelbags'):
                            for bag in strip.channelbags:curves.extend(bag.fcurves)
            animations.append({'name':ac.name,'frame_range':list(ac.frame_range),
                'channels':[{'data_path':fc.data_path,'array_index':fc.array_index,'keyframes':[list(k.co) for k in fc.keyframe_points]} for fc in curves]})
        report={'passed':True,'blender_version':bpy.app.version_string,'glb_sha256':hashlib.sha256(Path(a.glb).read_bytes()).hexdigest(),
            'import_result':sorted(result),'mesh_count':len(meshes),'component_ids':sorted(components),'material_ids':material_ids,'camera_count':len(cameras),
            'animations':animations,'world_bounds_gltf':total,
            'objects':[{'name':o.name,'type':o.type,'component_id':o.get('component_id'),'owner_component_id':o.get('owner_component_id'),'parent':o.parent.name if o.parent else None,
                'vertices':len(o.data.vertices) if o.type=='MESH' else None,'bounds_gltf':bounds(o) if o.type=='MESH' else None} for o in objects],
            'materials':[{'name':m.name,'uses_nodes':m.use_nodes,'image_nodes':[n.image.name for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image] if m.node_tree else []} for m in bpy.data.materials],
            'cameras':[{'name':o.name,'type':o.data.type,'clip_start':o.data.clip_start,'clip_end':o.data.clip_end} for o in cameras],
            'limitations':['Actual import validates structure and bounds; visual fidelity and interaction scripts are not certified.']}
        manifest=Path(a.manifest) if a.manifest else Path(a.glb+'.manifest.json')
        errors=[]
        if manifest.exists():
            expected=json.loads(manifest.read_text());report['manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
            for k in ('glb_sha256','mesh_count','camera_count'):
                if report[k]!=expected[k]:errors.append(k+' mismatch')
            if sorted(report['component_ids'])!=sorted(expected['component_ids']):errors.append('component IDs mismatch')
            # Blender prunes unused materials; expected manifest explicitly lists used materials.
            if not set(expected.get('used_material_ids',expected['material_ids'])).issubset(material_ids):errors.append('material IDs missing')
            imported_names=[ac['name'] for ac in animations if any('rotation' in c['data_path'] and len(c['keyframes'])>=2 for c in ac['channels'])]
            for name in expected['animation_names']:
                if not any(n==name or n.startswith(name+'_') or n.startswith(name+'.') for n in imported_names):errors.append('animation missing: '+name)
            for mid in expected.get('textured_material_ids',[]):
                material=next((m for m in bpy.data.materials if m.get('material_id',m.name)==mid),None)
                if material is None or not material.node_tree or not any(n.type=='TEX_IMAGE' and n.image and n.image.size[0]>0 for n in material.node_tree.nodes):errors.append('texture import missing: '+mid)
            if expected.get('world_bounds_gltf'):
                if total is None or any(abs(total[k][i]-expected['world_bounds_gltf'][k][i])>1e-4 for k in ('min','max') for i in range(3)):errors.append('world bounds mismatch')
        else:errors.append('expected manifest missing')
        report['errors']=errors;report['passed']=not errors
    except Exception as exc:report={'passed':False,'error':str(exc)}
    dest.write_text(json.dumps(report,indent=2));print(json.dumps(report))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
