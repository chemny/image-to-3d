#!/usr/bin/env python3
"""Preflight actual model-bound assembly anchors. Animated poses require runtime checks."""
import math
import scene_build


def require(ok,message):
    if not ok: raise ValueError(message)


def validate(spec):
    scene_build.build(spec)
    nodes={c['id'] for c in spec.get('components',[])}
    rows=[];ids=set();connected=set()
    connections=scene_build.resolve(spec.get('connections',[]),spec.get('parameters',{}))
    require(isinstance(connections,list),'connections must be list')
    for c in connections:
        require(isinstance(c.get('id'),str) and c['id'] and c['id'] not in ids,'unique connection ID required');ids.add(c['id'])
        limit=c.get('max_distance')
        require(type(limit) in (int,float) and math.isfinite(limit) and limit>=0,'finite nonnegative max_distance required')
        poses=c.get('poses',['closed','half','open'])
        require(isinstance(poses,list) and poses and len(set(poses))==len(poses) and set(poses)<={'closed','half','open'},'invalid connection poses')
        endpoints=[]
        for key in ('a','b'):
            e=c.get(key,{})
            require(e.get('component_id') in nodes,'unknown connection component')
            p=e.get('local_point')
            require(isinstance(p,list) and len(p)==3 and all(type(v) in (int,float) and math.isfinite(v) for v in p),'finite local anchor required')
            endpoints.append(scene_build.landmark(spec,{'component_id':e['component_id'],'local_point':p}))
            connected.add(e['component_id'])
        require(c['a']['component_id']!=c['b']['component_id'],'connection must join distinct components')
        distance=math.dist(*endpoints)
        require(distance<=limit,'closed connection exceeds threshold: '+c['id'])
        rows.append({'id':c['id'],'a':c['a'],'b':c['b'],'max_distance':limit,'poses':poses,'closed_distance':distance})
    for action in spec.get('actions',[]):
        require(action['component_id'] in connected,'active component needs declared connection: '+action['component_id'])
    return {'valid':True,'connections':rows,'runtime_poses_required':bool(spec.get('actions')),
            'scope':'closed model anchors only; runtime localToWorld pose checks still required','visual_pass':False}
