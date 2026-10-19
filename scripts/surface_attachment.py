#!/usr/bin/env python3
"""Sampled surface attachment and declared aperture rays. Not a full collision solver."""
import math
import numpy as np
import scene_build
import production_checks

def need(v,msg):
 if not v:raise ValueError(msg)
def world_meshes(spec):
 payload=scene_build.build(spec);nodes={c['id']:c for c in payload['components']};out={}
 for key,node in nodes.items():
  meshes=[]
  for m in node['meshes']:
   p=np.array(m['positions'],dtype=float).reshape(-1,3);cursor=key
   while cursor is not None:
    c=nodes[cursor];r=np.array([scene_build.rotate(v,c['rotation'])for v in np.eye(3)]).T;p=p@r.T+np.array(c['position']);cursor=c.get('parent')
   meshes.append((p,np.array(m['indices'],dtype=int).reshape(-1,3)))
  out[key]=meshes
 return nodes,payload,out

def triangles(world,ids,faces=None):
 need(isinstance(ids,list) and ids and all(i in world for i in ids),'unknown/empty geometry IDs')
 if faces is None:
  ts=[p[ix] for k in ids for p,ix in world[k]]
 else:
  need(isinstance(faces,list) and faces,'host_faces must be nonempty');ts=[];seen=set()
  for face in faces:
   need(isinstance(face,dict) and set(face)=={'component_id','mesh_index','triangle_index'},'host face requires component/mesh/triangle indices')
   cid,mi,ti=face['component_id'],face['mesh_index'],face['triangle_index']
   need(isinstance(cid,str) and cid in ids,'host face outside declared hosts')
   need(type(mi)is int and 0<=mi<len(world[cid]),'invalid host mesh index')
   p,ix=world[cid][mi];need(type(ti)is int and 0<=ti<len(ix),'invalid host triangle index')
   key=(cid,mi,ti);need(key not in seen,'duplicate host face');seen.add(key)
   tri=p[ix[ti]];need(np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0]))>1e-12,'degenerate selected host face');ts.append(tri[None,:,:])
 need(ts,'no mesh surfaces');t=np.concatenate(ts);n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);valid=np.linalg.norm(n,axis=1)>1e-12;need(valid.any(),'degenerate host');return t[valid]

def closest(point,t):
 a,b,c=t[:,0],t[:,1],t[:,2];ab=b-a;ac=c-a;n=np.cross(ab,ac);nn=np.einsum('ij,ij->i',n,n);n=n/np.sqrt(nn)[:,None];signed=np.einsum('ij,ij->i',point-a,n);q=point-signed[:,None]*n
 v=q-a;d00=np.einsum('ij,ij->i',ab,ab);d01=np.einsum('ij,ij->i',ab,ac);d11=np.einsum('ij,ij->i',ac,ac);d20=np.einsum('ij,ij->i',v,ab);d21=np.einsum('ij,ij->i',v,ac);den=d00*d11-d01*d01
 u=(d11*d20-d01*d21)/den;v=(d00*d21-d01*d20)/den;inside=(u>=0)&(v>=0)&(u+v<=1)
 best=np.where(inside,signed*signed,np.inf)
 for e,f in [(a,b),(b,c),(c,a)]:
  ef=f-e;ratio=np.clip(np.einsum('ij,ij->i',point-e,ef)/np.einsum('ij,ij->i',ef,ef),0,1);qq=e+ratio[:,None]*ef;dd=np.einsum('ij,ij->i',point-qq,point-qq);best=np.minimum(best,dd)
 k=int(np.argmin(best));return math.sqrt(float(best[k])),float(signed[k])

def ray_hit(point,direction,t,clearance):
 d=np.array(direction,dtype=float);need(d.shape==(3,) and np.isfinite(d).all() and np.linalg.norm(d)>1e-12,'invalid ray direction');d/=np.linalg.norm(d)
 a,b,c=t[:,0],t[:,1],t[:,2];e1=b-a;e2=c-a;h=np.cross(np.broadcast_to(d,e2.shape),e2);det=np.einsum('ij,ij->i',e1,h);ok=abs(det)>1e-12;inv=np.divide(1.,det,out=np.zeros_like(det),where=ok);s=point-a;u=inv*np.einsum('ij,ij->i',s,h);q=np.cross(s,e1);v=inv*np.einsum('j,ij->i',d,q);dist=inv*np.einsum('ij,ij->i',e2,q);ok &= (u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)&(dist>=-1e-8)&(dist<=clearance)
 return float(dist[ok].min())if ok.any()else None

def evaluate(spec,checks):
 need(isinstance(checks,list) and checks,'surface checks must be nonempty')
 nodes,payload,world=world_meshes(spec);resolved,_=scene_build.prepared(spec);built={c['id']:c for c in payload['components']};rows=[]
 seen=set()
 for c in checks:
  need(isinstance(c,dict),'surface check must be an object');cid=c.get('id');need(isinstance(cid,str) and cid.strip() and cid not in seen,'surface check IDs must be unique');seen.add(cid)
  kind=c.get('kind');need(kind in ['surface_gap','opening_clearance'],'unsupported surface check');host=triangles(world,c['host_component_ids'],c.get('host_faces'))
  if kind=='surface_gap':
   lo,hi=c['min'],c['max'];need(all(type(x)in(int,float)and math.isfinite(x)for x in [lo,hi])and 0<=lo<=hi,'invalid gap tolerance');side=c.get('side','either');need(side in ['inside','outside','either'],'invalid attachment side')
   parts=c['component_ids'];need(isinstance(parts,list) and parts and all(isinstance(k,str) and k in world for k in parts),'unknown/empty part IDs')
   need(not set(parts)&set(c['host_component_ids']),'part cannot be its own host')
   if 'anchors' in c:
    need('samples' not in c,'choose explicit anchors or automatic samples, not both')
    anchors=c['anchors'];need(isinstance(anchors,list) and 3<=len(anchors)<=256,'root anchors must be 3..256 actual surface bindings')
    need(all(isinstance(a,dict) and a.get('component_id')in parts for a in anchors),'root anchor outside declared parts')
    need(set(a['component_id']for a in anchors)==set(parts),'each declared part needs root anchors')
    need(all(sum(a['component_id']==k for a in anchors)>=3 for k in parts),'each declared part needs at least three root anchors')
    signatures=[repr(sorted(a.items()))for a in anchors];need(len(set(signatures))==len(signatures),'duplicate root anchor')
    points=np.array([production_checks._point(resolved,nodes,built,a)for a in anchors]);sampling='explicit_root_anchors'
   else:
    count=c.get('samples',32);need(type(count)is int and 3<=count<=256,'samples must be 3..256')
    part=triangles(world,parts);points=np.concatenate([part.reshape(-1,3),part.mean(axis=1)]);points=points[np.linspace(0,len(points)-1,min(count,len(points)),dtype=int)];sampling='automatic_part_surface'
   measure=[closest(p,host)for p in points];samples=[]
   for i,(point,(d,sg))in enumerate(zip(points,measure)):
    reasons=[]
    if d<lo-1e-8:reasons.append('below_min_gap')
    if d>hi+1e-8:reasons.append('above_max_gap')
    if side!='either' and not (sg>=-1e-8 if side=='outside'else sg<=1e-8):reasons.append('wrong_normal_side')
    samples.append({'index':i,'point':point.tolist(),'gap':d,'normal_side_offset':sg,'passed':not reasons,'reasons':reasons})
   rows.append({'id':c['id'],'passed':all(s['passed']for s in samples),'sampling':sampling,'sampled':len(measure),'samples':samples,'failed_sample_indices':[s['index']for s in samples if not s['passed']],'host_face_count':len(host),'min_gap':min(d for d,_ in measure),'max_gap':max(d for d,_ in measure),'signed_range':[min(sg for _,sg in measure),max(sg for _,sg in measure)]})
  else:
   depth=c['clearance'];need(type(depth)in(int,float)and math.isfinite(depth)and depth>0,'positive clearance required');anchors=c['anchors'];need(isinstance(anchors,list)and anchors,'opening needs actual geometry anchors');hits=[]
   for a in anchors:
    p=production_checks._point(resolved,nodes,built,a);hits.append(ray_hit(np.array(p),c['direction'],host,depth))
   rows.append({'id':c['id'],'passed':all(x is None for x in hits),'rays':len(hits),'blocking_distances':hits})
 return {'passed':all(r['passed']for r in rows),'checks':rows,'errors':[r['id']for r in rows if not r['passed']],'scope':'Declared static surface samples and aperture rays only; no unsampled collision, full-opening or visual certificate.'}


def cut_projected_opening(positions,indices,polygon,projection='xy',depth_range=None):
 """Subtract a convex polygon from triangles in an axis projection; plain mesh only.
 Returns explicit positions/triangles. Callers must rebuild normals and any UVs.
 """
 need(projection in ['xy','xz','yz'],'invalid projection');axes={'xy':(0,1,2),'xz':(0,2,1),'yz':(1,2,0)}[projection];poly=np.array(polygon,dtype=float);need(poly.ndim==2 and poly.shape[1]==2 and len(poly)>=3 and np.isfinite(poly).all(),'invalid opening polygon')
 cross=lambda a,b:a[0]*b[1]-a[1]*b[0]
 area=sum(cross(a,b)for a,b in zip(poly,np.roll(poly,-1,axis=0)));need(abs(area)>1e-10,'zero-area opening')
 if area<0:poly=poly[::-1]
 turns=[cross(poly[(i+1)%len(poly)]-poly[i],poly[(i+2)%len(poly)]-poly[(i+1)%len(poly)])for i in range(len(poly))];need(min(turns)>=-1e-9,'opening must be convex')
 pts=np.array(positions,dtype=float).reshape(-1,3);faces=np.array(indices,dtype=int).reshape(-1,3);out=[];tris=[];lookup={};lo=poly.min(axis=0);hi=poly.max(axis=0)
 def emit(p):
  if len(p)<3:return
  ids=[]
  for x in p:
   key=tuple(np.round(x,10))
   if key not in lookup:lookup[key]=len(out);out.append(x.tolist())
   ids.append(lookup[key])
  for i in range(1,len(ids)-1):
   if len({ids[0],ids[i],ids[i+1]})==3:tris.extend([ids[0],ids[i],ids[i+1]])
 def clip(p,a,b,inside):
  result=[];edge=b-a
  for start,end in zip(p,p[1:]+p[:1]):
   ds=cross(edge,start[list(axes[:2])]-a);de=cross(edge,end[list(axes[:2])]-a);si=ds>=-1e-12 if inside else ds<=1e-12;ei=de>=-1e-12 if inside else de<=1e-12
   if si:result.append(start)
   if si!=ei and abs(ds-de)>1e-15:result.append(start+(end-start)*(ds/(ds-de)))
  return result
 for face in faces:
  triangle=pts[face];projected=triangle[:,list(axes[:2])]
  if (projected.max(axis=0)<lo).any()or(projected.min(axis=0)>hi).any()or(depth_range is not None and not (triangle[:,axes[2]].min()>=depth_range[0]and triangle[:,axes[2]].max()<=depth_range[1])):emit(list(triangle));continue
  remaining=list(triangle)
  for a,b in zip(poly,np.roll(poly,-1,axis=0)):
   if not remaining:break
   emit(clip(remaining,a,b,False));remaining=clip(remaining,a,b,True)
 return {'positions':[v for p in out for v in p],'triangles':tris,'scope':'Projected convex cut only; transition walls and back surfaces must be authored.'}
