"""Blender CLI: fit a bounded camera to supplied 3D/2D correspondences.
Manual correspondences are required. Reprojection error is not vehicle fidelity.
"""
import argparse,hashlib,html,json,math,shutil,sys
from pathlib import Path
import bpy,numpy as np
from mathutils import Vector,Euler

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--anchors',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--render',action='store_true');p.add_argument('--max-iterations',type=int,default=80);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
 if a.out.exists():raise ValueError('Use a new camera-fit output directory')
 if not 1<=a.max_iterations<=200:raise ValueError('Iteration budget must be 1..200')
 data=json.loads(a.anchors.read_text());source_sha=sha(a.model)
 if data.get('schema_version')!=1 or data.get('asset_sha256')!=source_sha:raise ValueError('Stale or missing model identity in anchors')
 if data.get('reference_sha256')!=sha(a.reference):raise ValueError('Stale or missing reference identity in anchors')
 if data.get('reference_origin') not in ['real','generated','inferred','user_supplied']:raise ValueError('Declare reference provenance')
 anchors=data.get('anchors',[])
 if len(anchors)<6 or any(not x.get('id') or not x.get('evidence') for x in anchors) or len({x['id'] for x in anchors})!=len(anchors):raise ValueError('Need at least six unique, evidenced correspondences')
 points=np.array([v['world'] for v in anchors],dtype=float);observed=np.array([v['pixel'] for v in anchors],dtype=float)
 if points.shape!=(len(anchors),3) or observed.shape!=(len(anchors),2) or not np.isfinite(points).all() or not np.isfinite(observed).all():raise ValueError('Invalid finite anchor coordinates')
 if np.linalg.matrix_rank(points-points.mean(0))<2 or np.linalg.matrix_rank(observed-observed.mean(0))<2:raise ValueError('Collinear anchors cannot constrain camera')
 if a.model.suffix.lower()=='.blend':bpy.ops.wm.open_mainfile(filepath=str(a.model.resolve()))
 elif a.model.suffix.lower()=='.glb':bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(a.model.resolve()))
 else:raise ValueError('GLB or .blend model required')
 image=bpy.data.images.load(str(a.reference.resolve()));source_w,source_h=image.size
 roi=data.get('reference_roi',[0,0,source_w,source_h])
 if len(roi)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or int(v)!=v for v in roi):raise ValueError('Integer reference ROI required')
 rx,ry,w,h=roi
 if rx<0 or ry<0 or w<=0 or h<=0 or rx+w>source_w or ry+h>source_h:raise ValueError('Reference ROI outside image')
 source_observed=observed.copy();observed-=np.array([rx,ry])
 if any(not (0<=v[0]<=w and 0<=v[1]<=h) for v in observed):raise ValueError('Image pixel anchors out of ROI bounds')
 review_anchors=data.get('validation_anchors',[])
 if any(not v.get('id') or not v.get('evidence') for v in review_anchors) or len({v['id'] for v in anchors+review_anchors})!=len(anchors+review_anchors):raise ValueError('Validation anchors require distinct evidenced IDs')
 review_points=np.array([v['world'] for v in review_anchors],dtype=float).reshape((-1,3));review_observed=np.array([v['pixel'] for v in review_anchors],dtype=float).reshape((-1,2))-np.array([rx,ry])
 if not np.isfinite(review_points).all() or not np.isfinite(review_observed).all() or any(not (0<=v[0]<=w and 0<=v[1]<=h) for v in review_observed):raise ValueError('Invalid validation anchors')
 if any(np.linalg.norm(v-p)<1e-8 for v in review_points for p in points) or (len(review_points)>1 and any(np.linalg.norm(v-p)<1e-8 for i,v in enumerate(review_points) for p in review_points[i+1:])):raise ValueError('Validation points must be held out, not renamed fit points')
 threshold=data.get('max_anchor_error_px');review_threshold=data.get('max_validation_error_px',threshold)
 if any(v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or v<0) for v in [threshold,review_threshold]):raise ValueError('Finite nonnegative error thresholds required')
 initial=data['camera'];kind=initial.get('type','PERSP')
 if kind not in ('PERSP','ORTHO'):raise ValueError('PERSP or ORTHO required')
 center=np.array(initial['target'],dtype=float);eye=np.array(initial['position'],dtype=float);distance=np.linalg.norm(eye-center)
 if not np.isfinite(center).all() or not np.isfinite(eye).all() or distance<=0:raise ValueError('Invalid initial camera')
 rotation=(Vector(center)-Vector(eye)).to_track_quat('-Z','Y').to_euler();angle=np.array(rotation)
 if kind=='ORTHO':
  if initial.get('ortho_scale',0)<=0:raise ValueError('Positive ortho_scale required')
  x=np.concatenate([angle,[0,0,math.log(initial['ortho_scale'])]])
 else:
  if not 10<=initial.get('lens',50)<=300:raise ValueError('Lens outside 10..300 mm')
  x=np.concatenate([angle,eye,[math.log(initial.get('lens',50))]])
 sensor_width=36.;weights=np.repeat(np.sqrt([v.get('weight',1) for v in anchors]),2)
 if not np.isfinite(weights).all() or (weights<=0).any():raise ValueError('Positive finite weights required')
 def pose(params):
  matrix=np.array(Euler(tuple(params[:3]),'XYZ').to_matrix())
  if kind=='ORTHO':
   target=center+matrix[:,0]*params[3]+matrix[:,1]*params[4];position=target+matrix[:,2]*distance;extent=math.exp(float(params[5]))
  else:position=params[3:6];extent=math.exp(float(params[6]));target=position-matrix[:,2]*distance
  return matrix,position,target,extent
 def project(params,coordinates=None):
  matrix,position,target,extent=pose(params);local=((points if coordinates is None else coordinates)-position)@matrix
  if kind=='ORTHO':px=local[:,:2]*(w/extent)
  else:
   if (local[:,2]>=-1e-4).any():raise ValueError('Anchor behind perspective camera')
   px=local[:,:2]*(w*extent/sensor_width)/(-local[:,2,None])
  return np.column_stack((px[:,0]+w/2,h/2-px[:,1]))
 def residual(params):return (project(params)-observed).ravel()*weights
 before=project(x);r=residual(x);cost=float(r@r);damping=1e-3;iterations=0;accepted=0;rank=0
 eps=np.array([1e-5]*3+[max(distance,1)*1e-5]*(len(x)-4)+[1e-5])
 for iteration in range(a.max_iterations):
  iterations=iteration+1;columns=[]
  for j in range(len(x)):
   v=x.copy();v[j]+=eps[j];columns.append((residual(v)-r)/eps[j])
  J=np.column_stack(columns);rank=int(np.linalg.matrix_rank(J,tol=1e-6))
  scale=np.maximum(np.linalg.norm(J,axis=0),1e-9);N=J/scale
  delta=np.linalg.lstsq(N.T@N+damping*np.eye(len(x)),-N.T@r,rcond=None)[0]/scale
  candidate=x+delta
  if np.linalg.norm(candidate[:3]-angle)>math.pi or (np.linalg.norm(candidate[3:5]) if kind=='ORTHO' else np.linalg.norm(candidate[3:6]-eye))>distance*2:
   damping=min(damping*10,1e12);continue
  candidate[-1]=np.clip(candidate[-1],math.log(.01 if kind=='ORTHO' else 10),math.log(distance*100 if kind=='ORTHO' else 300))
  try:new_r=residual(candidate);new_cost=float(new_r@new_r)
  except (ValueError,OverflowError):new_cost=float('inf')
  if new_cost<cost:
   improvement=cost-new_cost;x=candidate;r=new_r;cost=new_cost;accepted+=1;damping=max(damping/3,1e-9)
   if improvement<1e-8 or np.linalg.norm(delta)<1e-8:break
  else:damping=min(damping*10,1e12)
  if damping>=1e12:break
 fitted=project(x);matrix,position,target,extent=pose(x);errors=np.linalg.norm(fitted-observed,axis=1);before_errors=np.linalg.norm(before-observed,axis=1)
 bounds_points=np.array([list(o.matrix_world@Vector(c)) for o in bpy.context.scene.objects if o.type=='MESH' for c in o.bound_box])
 # Report conservative bounding-box coverage; fitting sparse anchors may still clip body ends.
 try:bounds_projected=project(x,bounds_points);coverage={'method':'projected object bounding-box corners; not silhouette','min':bounds_projected.min(0).tolist(),'max':bounds_projected.max(0).tolist(),'within_frame':bool((bounds_projected[:,0]>=0).all() and (bounds_projected[:,0]<=w).all() and (bounds_projected[:,1]>=0).all() and (bounds_projected[:,1]<=h).all())}
 except ValueError:coverage={'method':'projected bounding boxes','within_frame':False,'reason':'some bbox corners behind camera'}
 review_projected=project(x,review_points) if len(review_points) else np.empty((0,2));review_errors=np.linalg.norm(review_projected-review_observed,axis=1)
 review_rows=[{'id':v['id'],'observed':review_observed[i].tolist(),'source_pixel':v['pixel'],'projected':review_projected[i].tolist(),'error_px':float(review_errors[i]),'evidence':v['evidence']} for i,v in enumerate(review_anchors)]
 a.out.mkdir(parents=True,exist_ok=False);shutil.copy2(a.anchors,a.out/'anchors.json');refname='reference'+a.reference.suffix.lower();shutil.copy2(a.reference,a.out/refname)
 camera={'type':kind,'position':position.tolist(),'target':target.tolist(),'rotation_euler':x[:3].tolist(),'sensor_width':sensor_width,'sensor_fit':'HORIZONTAL','resolution':[w,h],('ortho_scale' if kind=='ORTHO' else 'lens'):extent}
 within=bool(threshold is not None and errors.max()<=threshold and rank==len(x) and coverage['within_frame'] and (not len(review_errors) or review_threshold is not None and review_errors.max()<=review_threshold))
 report={'schema_version':1,'scope':'camera alignment of supplied correspondences only; not geometry similarity','verdict':'aligned' if within else 'needs_review','reference_origin':data['reference_origin'],'reference_roi':roi,'pixel_frame':'ROI-relative; source_pixel retains original full image pixels','validation_anchors':review_rows,'validation_scope':'held out of optimization; independent manually selected points','validation_threshold_px':review_threshold,'validation_rmse_px':float(np.sqrt(np.mean(review_errors**2))) if len(review_errors) else None,'validation_max_error_px':float(review_errors.max()) if len(review_errors) else None,'model_sha256':source_sha,'reference_sha256':sha(a.reference),'anchor_sha256':sha(a.anchors),'coordinate_system':'Blender world, +Z up; pixels top-left','iterations':iterations,'accepted_steps':accepted,'jacobian_rank':rank,'parameter_count':len(x),'frame_coverage':coverage,'camera':camera,'initial_camera':initial,'before_rmse_px':float(np.sqrt(np.mean(before_errors**2))),'rmse_px':float(np.sqrt(np.mean(errors**2))),'max_error_px':float(errors.max()),'task_threshold_px':threshold,'anchors':[{'id':v['id'],'observed':observed[i].tolist(),'source_pixel':v['pixel'],'projected':fitted[i].tolist(),'initial_projected':before[i].tolist(),'error_px':float(errors[i]),'evidence':v['evidence']} for i,v in enumerate(anchors)],'limitations':['Manual anchor uncertainty and model feature mismatch are included in residual','Generated reference is design guidance, not measured hidden geometry','Image reconstruction and geometric fidelity are not certified']}
 (a.out/'camera-fit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 view={'name':'reference_fit','position':camera['position'],'target':camera['target'],'rotation_euler':camera['rotation_euler'],'type':kind,'sensor_width':sensor_width,'sensor_fit':'HORIZONTAL','clay':True,'fit_report_sha256':sha(a.out/'camera-fit.json')}
 view['scale' if kind=='ORTHO' else 'lens']=extent
 (a.out/'pipeline-view.json').write_text(json.dumps({'resolution':[w,h],'view':view},ensure_ascii=False,indent=2)+'\n')
 svg=[]
 for row in report['anchors']+report['validation_anchors']:
  u,v=row['observed'];x1,y1=row['projected'];label=html.escape(row['id']);color='#50b9ff' if row in report['validation_anchors'] else '#2dca85';svg.append(f'<line x1="{u}" y1="{v}" x2="{x1}" y2="{y1}" stroke="#ffb15c" stroke-width="2"/><circle cx="{u}" cy="{v}" r="6" fill="{color}"/><circle cx="{x1}" cy="{y1}" r="6" fill="none" stroke="#f44" stroke-width="2"/><text x="{u+10}" y="{v-10}" fill="white" stroke="#222" stroke-width=".5" font-size="18">{label}</text>')
 page=f'<!doctype html><meta charset="utf-8"><title>人工锚点相机拟合</title><style>body{{font:16px system-ui;background:#202831;color:white;margin:24px}}main{{max-width:1400px;margin:auto}}.image{{position:relative}}svg{{width:100%;display:block}}a{{color:#9ed7e7}}</style><main><h1>人工锚点相机拟合</h1><p>绿点：拟合标注；蓝点：未参与拟合的复核点；红圈：模型投影。RMSE {report["before_rmse_px"]:.2f} → {report["rmse_px"]:.2f} 像素，只说明锚点对齐，不是车型准确率。来源：{html.escape(data["reference_origin"])}</p><div class="image"><svg viewBox="0 0 {w} {h}"><image x="{-rx}" y="{-ry}" width="{source_w}" height="{source_h}" href="{refname}"/>{"".join(svg)}</svg></div><p><a href="camera-fit.json">相机和每点误差</a></p></main>'
 (a.out/'comparison.html').write_text(page)
 if a.render:
  scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=4;scene.cycles.use_denoising=True;scene.render.resolution_x=w;scene.render.resolution_y=h;scene.render.resolution_percentage=50
  world=bpy.data.worlds.new('CameraFitReview');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.3,.3,.3,1);scene.world=world
  for o in scene.objects:
   if o.type in ('CAMERA','LIGHT'):o.hide_render=True
  for loc in [center+np.array([4,3,7]),center+np.array([-4,-3,5])]:
   bpy.ops.object.light_add(type='AREA',location=loc);lamp=bpy.context.object;lamp.data.energy=1400;lamp.data.size=6;lamp.rotation_euler=(Vector(center)-lamp.location).to_track_quat('-Z','Y').to_euler()
  bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type=kind;cam.data.sensor_fit='HORIZONTAL';cam.data.sensor_width=sensor_width;scene.camera=cam
  clay=bpy.data.materials.new('FitClay');clay.diffuse_color=(.5,.5,.5,1);scene.view_layers[0].material_override=clay
  for label,params in [('initial',np.concatenate([angle,[0,0,math.log(initial['ortho_scale'])]]) if kind=='ORTHO' else np.concatenate([angle,eye,[math.log(initial.get('lens',50))]])),('fitted',x)]:
   R,loc,_,extent=pose(params);cam.location=loc;cam.rotation_euler=Euler(tuple(params[:3]),'XYZ')
   if kind=='ORTHO':cam.data.ortho_scale=extent
   else:cam.data.lens=extent
   scene.render.filepath=str((a.out/(label+'-clay.png')).resolve());bpy.ops.render.render(write_still=True)
 if sha(a.model)!=source_sha:raise RuntimeError('Source model changed')
 print('CAMERA_FIT',json.dumps({'verdict':report['verdict'],'rmse_px':report['rmse_px'],'rank':rank,'out':str(a.out.resolve())}))
if __name__=='__main__':main()
