#!/usr/bin/env python3
"""Analytic bicubic derivatives/curvature for supplied native surfaces; not photo recovery."""
import math
import scene_build as scene
from bezier_network import basis,derivative,evaluate

def sample(grid,u,v):
    p,du,dv,n=evaluate(grid,u,v);bu,bv=basis(u),basis(v);d1u,d1v=derivative(u),derivative(v)
    d2=lambda t:[6*(1-t),18*t-12,6-18*t,6*t]
    d2u,d2v=d2(u),d2(v)
    def total(a,b):return[sum(grid[i][j][k]*a[i]*b[j]for i in range(4)for j in range(4))for k in range(3)]
    duu,duv,dvv=total(d2u,bv),total(d1u,d1v),total(bu,d2v)
    dot=lambda a,b:sum(x*y for x,y in zip(a,b))
    E,F,G=dot(du,du),dot(du,dv),dot(dv,dv);L,M,N=dot(n,duu),dot(n,duv),dot(n,dvv);den=E*G-F*F
    if den<=1e-20:raise ValueError('degenerate fundamental form')
    H=(E*N+G*L-2*F*M)/(2*den);K=(L*N-M*M)/den;root=math.sqrt(max(0,H*H-K));ks=[H-root,H+root]
    return {'position':p,'du':du,'dv':dv,'normal':n,'duu':duu,'duv':duv,'dvv':dvv,'mean_curvature':H,'gaussian_curvature':K,'principal_curvatures':ks,'principal_radius_magnitudes':[None if abs(k)<1e-12 else 1/abs(k)for k in ks],'scope':'analytic supplied Bezier patch at UV; curvature sign follows patch orientation, not recovered physical truth'}

def report(spec):
    resolved,nodes=scene.prepared(spec);rows=[];unsupported=[]
    for cid in spec['foundation']['primary_components']:
        g=nodes[cid]['geometry']
        if g['type']!='bezier_network':unsupported.append({'component_id':cid,'reason':'No analytic patch identity; use declared mesh curves/sections, do not invent CAD curvature.'});continue
        net=g['network']
        for patch in net['patches']:
            grid=[[net['control_points'][k]['position']for k in row]for row in patch['control_points']]
            for u in (.1,.5,.9):
                for v in (.1,.5,.9):rows.append({'component_id':cid,'patch_id':patch['id'],'uv':[u,v],**sample(grid,u,v)})
    return {'samples':rows,'unsupported':unsupported,'visual_pass':False,'scope':'local component units; rigid transforms preserve curvature. Sampling does not certify entire patch continuity or self-intersection.'}
