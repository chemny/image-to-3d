#!/usr/bin/env python3
"""Bounded coarse geometry/camera initialization against traced visible edge arcs.

Calibration selects candidates; validation is evaluated only after selection.
Real parameterized mesh vertices are the sole 3D authority. No visual acceptance.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
import scene_build
from reconstruction import project, unit, cross, sub


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def full_geometry_identity(payload):
    """Identity of all native built geometry/asset state, including untraced parts."""
    return digest({key:payload.get(key) for key in
                   ('components','materials','actions','variants','asset_contract','vehicle_bindings')})


def need(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, label, positive=False):
    need(type(value) in (int, float) and math.isfinite(value) and (not positive or value > 0),
         label + ' must be finite' + (' and positive' if positive else ''))
    return value


def keys(value, allowed, label):
    need(isinstance(value, dict) and not set(value)-set(allowed), label + ' has unknown fields or is not an object')


def index(items, label):
    if isinstance(items, dict):
        need(all(isinstance(k, str) and k and isinstance(v, dict) for k,v in items.items()), label + ' invalid dictionary')
        return items
    need(isinstance(items, list), label + ' requires list or dictionary')
    need(all(isinstance(v, dict) and isinstance(v.get('id'), str) and v['id'] for v in items), label + ' missing IDs')
    result = {v['id']:v for v in items}
    need(len(result) == len(items), label + ' duplicate IDs')
    return result


def parameter_refs(value, path=()):
    if isinstance(value, dict):
        if 'param' in value:
            yield value, path
        else:
            for key, item in value.items():
                yield from parameter_refs(item, path+(key,))
    elif isinstance(value, list):
        for key, item in enumerate(value):
            yield from parameter_refs(item, path+(key,))


def camera(builder, parameters):
    """Yaw is +X from +Z; positive roll rotates camera up towards camera right."""
    keys(builder, ('projection','width','height','target','yaw_deg','elevation_deg','distance',
                   'roll_deg','fov_y_deg','ortho_height','near','far'), 'camera builder')
    b = scene_build.resolve(builder, parameters)
    need(b.get('projection') in ('perspective','orthographic'), 'unsupported camera projection')
    for name in ('width','height'):
        need(type(b.get(name)) is int and b[name] > 0, 'camera image dimension must be positive integer')
    target = scene_build.vector(b.get('target'))
    yaw = math.radians(number(b.get('yaw_deg'), 'yaw'))
    elevation = number(b.get('elevation_deg'), 'elevation')
    need(-90 < elevation < 90, 'camera elevation cannot reach a degenerate pole')
    elev = math.radians(elevation);distance = number(b.get('distance'), 'distance', True)
    roll = math.radians(number(b.get('roll_deg'), 'roll'))
    offset = [distance*math.cos(elev)*math.sin(yaw), distance*math.sin(elev), distance*math.cos(elev)*math.cos(yaw)]
    position = [a+b for a,b in zip(target, offset)]
    forward = unit(sub(target, position));right = unit(cross(forward, [0,1,0]));up = cross(right, forward)
    rolled = [a*math.cos(roll)+b*math.sin(roll) for a,b in zip(up, cross(forward, up))]
    near = number(b.get('near'), 'near', True);far = number(b.get('far'), 'far', True)
    need(far > near, 'camera far must exceed near')
    result = dict(type=b['projection'], width=b['width'], height=b['height'], position=position,
                  target=list(target), up=rolled, near=near, far=far)
    if b['projection'] == 'perspective':
        need('ortho_height' not in b, 'perspective builder cannot declare ortho_height')
        fov = number(b.get('fov_y_deg'), 'FOV', True);need(fov < 179, 'FOV must be below 179 degrees')
        result['fov_y_deg'] = fov
    else:
        need('fov_y_deg' not in b, 'orthographic builder cannot declare FOV')
        result['ortho_height'] = number(b.get('ortho_height'), 'orthographic height', True)
    return result


def _same_camera(actual, expected):
    # Missing up means the native projector's default world-Y up, projected into
    # its camera plane. Compare effective bases instead of arbitrary up magnitude.
    for name in ('type','width','height'):
        need(actual.get(name) == expected[name], 'input cameras must match initial builders: '+name)
    for name in ('position','target'):
        need(np.allclose(scene_build.vector(actual.get(name)), expected[name], rtol=0, atol=1e-9),
             'input cameras must match initial builders: '+name)
    for name in ('near','far','fov_y_deg','ortho_height'):
        if name in expected:
            need(type(actual.get(name)) in (int,float) and abs(actual[name]-expected[name]) <= 1e-9,
                 'input cameras must match initial builders: '+name)
    forward = unit(sub(actual['target'], actual['position']))
    aright = unit(cross(forward, actual.get('up', [0,1,0])))
    eright = unit(cross(forward, expected['up']))
    need(np.allclose(aright, eright, rtol=0, atol=1e-9), 'input cameras must match initial roll/up')


def _world(point, component_id, nodes):
    while component_id is not None:
        component = nodes[component_id]
        point = [a+b for a,b in zip(scene_build.rotate(point, component.get('rotation',[0,0,0])),
                                    component.get('position',[0,0,0]))]
        component_id = component.get('parent')
    return point


def _full_curves(payload, curves):
    nodes = index(payload['components'], 'built components');result = {}
    for curve in curves:
        points = []
        for binding in curve['bindings']:
            node = nodes[binding['component_id']]
            need(len(node['meshes']) == 1, 'explicit bound mesh requires one native mesh')
            pos = node['meshes'][0]['positions'];i = binding['vertex_index']
            points.append(_world(pos[i*3:i*3+3], node['id'], nodes))
        result[curve['id']] = points
    return result


def _sparse_curves(raw_nodes, curves, parameters):
    needed = set()
    for curve in curves:
        for binding in curve['bindings']:
            key = binding['component_id']
            while key is not None:
                needed.add(key);key = raw_nodes[key].get('parent')
    nodes = {key:{'id':key, 'parent':raw_nodes[key].get('parent'),
                  'position':scene_build.resolve(raw_nodes[key].get('position',[0,0,0]), parameters),
                  'rotation':scene_build.resolve(raw_nodes[key].get('rotation',[0,0,0]), parameters)} for key in needed}
    result = {}
    for curve in curves:
        points = []
        for binding in curve['bindings']:
            key = binding['component_id'];i = binding['vertex_index'];raw = raw_nodes[key]['geometry']['positions'][i*3:i*3+3]
            points.append(_world(scene_build.vector(scene_build.resolve(raw, parameters)), key, nodes))
        result[curve['id']] = points
    return result


def _nearest(pixel, projected, closed):
    points = np.asarray(projected, dtype=float)
    a = points if closed else points[:-1];b = np.roll(points,-1,axis=0) if closed else points[1:]
    d = b-a;denominator = np.sum(d*d,axis=1)
    need(np.all(denominator > 1e-20), 'projected edge curve contains a collapsed segment')
    t = np.clip(np.sum((np.asarray(pixel)-a)*d,axis=1)/denominator,0,1)
    hits = a+t[:,None]*d;dist2 = np.sum((hits-np.asarray(pixel))**2,axis=1);i = int(np.argmin(dist2))
    return hits[i], i, float(t[i])


def _protection(payload, protected):
    nodes = index(payload['components'], 'built components');result = {}
    for key in protected:
        chain=[];cursor=nodes[key].get('parent')
        while cursor is not None:
            c=nodes[cursor];chain.append({'id':cursor,'position':c.get('position',[0,0,0]),'rotation':c.get('rotation',[0,0,0])});cursor=c.get('parent')
        result[key] = digest({'component':nodes[key],'ancestor_transforms':chain})
    return result


def _resources(spec, curves, root):
    errors=[];hashes={};source_files={};refs=index(spec.get('references',[]),'references')
    if root is None:
        return False, ['resource_root missing; actual declared resources not verified'], hashes, source_files
    root=Path(root)
    if not root.is_dir():
        return False, ['resource_root must be an existing directory'], hashes, source_files
    from PIL import Image
    for rid in sorted({c['reference_id'] for c in curves}):
        ref=refs[rid]
        try:
            path=Path(root)/ref['path'];actual=hashlib.sha256(path.read_bytes()).hexdigest()
            need(actual == ref.get('sha256'), 'stale source image: '+rid)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                size=list(image.size)
            need(size == ref.get('image_size'), 'source image dimensions mismatch: '+rid)
            roi=ref.get('roi')
            if roi is not None:
                scene_build.vector(roi,4);rx,ry,rw,rh=roi
                need(rx>=0 and ry>=0 and rw>0 and rh>0 and rx+rw<=size[0] and ry+rh<=size[1],
                     'reference ROI outside actual source image: '+rid)
            hashes[rid]={'path':str(path.resolve()),'sha256':actual,'image_size':size}
            for curve in curves:
                if curve['reference_id'] != rid:continue
                for sample in curve['samples']:
                    x,y=sample['pixel'];need(0<=x<size[0] and 0<=y<size[1], 'sample outside source image: '+sample['id'])
                    if roi is not None:
                        need(rx<=x<=rx+rw and ry<=y<=ry+rh,'sample outside declared source ROI: '+sample['id'])
        except (ValueError,KeyError,OSError,TypeError) as exc:
            errors.append(str(exc))
    declared=spec.get('source_files',[])
    if not isinstance(declared,list):
        errors.append('source_files must be a list of declared path/hash objects')
        declared=[]
    seen_paths=set()
    for entry in declared:
        try:
            need(isinstance(entry,dict),'source_file must be a declared path/hash object')
            relative=entry.get('path');expected=entry.get('sha256')
            need(isinstance(relative,str) and relative.strip() and '\x00' not in relative
                 and '\\' not in relative and ':' not in relative and not Path(relative).is_absolute(),
                 'source_file requires a portable declared relative path')
            need(isinstance(expected,str) and re.fullmatch(r'[0-9a-f]{64}',expected) is not None,
                 'source_file requires a lowercase SHA256: '+relative)
            # Explicit resource_root grants read resolution for declared relative
            # parents used by existing bundles. No invented fallback search and no
            # path confinement claim: ../author.py is a legitimate native source.
            resolved=(root/relative).resolve(strict=True)
            need(resolved.is_file(),'source_file is not a regular file: '+relative)
            need(resolved not in seen_paths,'duplicate resolved source_file: '+relative)
            seen_paths.add(resolved)
            actual=hashlib.sha256(resolved.read_bytes()).hexdigest()
            source_files[relative]={'path':str(resolved),'sha256':actual,'declared_sha256':expected,
                                    'verified':actual==expected}
            need(actual==expected,'stale source_file: '+relative)
        except (ValueError,KeyError,OSError,TypeError,RuntimeError) as exc:
            errors.append(str(exc))
    return not errors,errors,hashes,source_files


def fit(spec, contract, resource_root=None, iterations=120):
    keys(contract, ('version','spec_identity','rationale','gauge','protected_component_ids','max_condition',
                    'reject_bound_hits','variable_ids','geometry_parameter_ids','camera_builders','curves','seeds'), 'joint contract')
    need(type(contract.get('version')) is int and contract['version']==1, 'joint contract version1 required')
    need(contract.get('spec_identity') == digest(spec), 'stale source spec identity')
    for name in ('rationale','gauge'):
        need(isinstance(contract.get(name),str) and contract[name].strip(), name+' required')
    need(type(iterations) is int and iterations>0, 'iterations must be positive integer')
    ids=contract.get('variable_ids');geom=contract.get('geometry_parameter_ids')
    for name,value in [('variable_ids',ids),('geometry_parameter_ids',geom),('protected_component_ids',contract.get('protected_component_ids'))]:
        need(isinstance(value,list) and all(isinstance(v,str) and v for v in value) and len(value)==len(set(value)), name+' requires unique IDs')
    need(ids and set(geom)<=set(ids), 'geometry IDs must be a subset of nonempty variable IDs')
    parameters=copy.deepcopy(spec.get('parameters',{}));lower=[];spans=[]
    for key in ids:
        need(key in parameters, 'unknown fitting parameter: '+key)
        p=parameters[key]
        vals=[number(p.get(k),'parameter '+key) for k in ('min','value','max')]
        need(vals[0]<vals[2] and vals[0]<=vals[1]<=vals[2], 'variable requires positive span and bounded value: '+key)
        lower.append(vals[0]);spans.append(vals[2]-vals[0])
    lower=np.asarray(lower);spans=np.asarray(spans)
    max_condition=number(contract.get('max_condition'),'max_condition',True)
    need(type(contract.get('reject_bound_hits')) is bool, 'reject_bound_hits must be boolean')
    nodes=index(spec.get('components',[]),'components');protected=contract['protected_component_ids']
    need(set(protected)<=set(nodes), 'unknown protected component')
    builders=contract.get('camera_builders');need(isinstance(builders,dict) and builders, 'camera builders required')
    cameras=index(spec.get('cameras',{}),'cameras');need(set(builders)<=set(cameras), 'unknown built camera')
    initial_cameras={key:camera(b,parameters) for key,b in builders.items()}
    for key,expected in initial_cameras.items():_same_camera(scene_build.resolve(cameras[key],parameters),expected)
    # Check parameter permissions on actual native expression paths, never on a
    # separate scoring/proxy parameter dictionary.
    links={key:[] for key in ids}
    for key,node in nodes.items():
        for reference,path in parameter_refs(node):
            pid=reference.get('param')
            if pid not in links:continue
            need(pid in geom and path and path[0] in ('geometry','position','rotation'),
                 'camera-only or forbidden component mutation: '+pid)
            if path[0]=='geometry':
                need(path[1:2]==('positions',), 'geometry variables require native mesh positions: '+pid)
            need(key not in protected, 'protected component parameter mutation: '+key)
            links[pid].append((key,path))
    for field,value in spec.items():
        if field in ('components','parameters','cameras'):continue
        need(not any(r.get('param') in ids for r,_ in parameter_refs(value)), 'variable affects forbidden field: '+field)
    for key,value in cameras.items():
        for reference,_ in parameter_refs(value):
            if reference.get('param') in ids:need(key in builders,'variable affects undeclared camera')
    builder_ids={r.get('param') for b in builders.values() for r,_ in parameter_refs(b)}
    for key in ids:
        need(bool(links[key]) if key in geom else key in builder_ids, 'parameter has no permitted actual effect: '+key)
    for key in protected:
        cursor=nodes[key].get('parent');seen=set()
        while cursor is not None:
            need(cursor in nodes and cursor not in seen,'cyclic or missing parent');seen.add(cursor)
            need(not any(r.get('param') in ids for field in ('position','rotation') for r,_ in parameter_refs(nodes[cursor].get(field))),
                 'protected ancestor transform mutation: '+key)
            cursor=nodes[cursor].get('parent')
    curves=contract.get('curves');need(isinstance(curves,list) and curves,'edge curves required')
    refs=index(spec.get('references',[]),'references');curve_ids=set();sample_ids=set();edge_cache={}
    for curve in curves:
        keys(curve,('id','camera_id','reference_id','bindings','closed','samples','max_error_px'),'curve')
        cid=curve.get('id');need(isinstance(cid,str) and cid and cid not in curve_ids,'unique curve ID required');curve_ids.add(cid)
        need(curve.get('camera_id') in builders and curve.get('reference_id') in refs,'curve needs declared camera and reference')
        size=refs[curve['reference_id']].get('image_size')
        cam=initial_cameras[curve['camera_id']]
        need(size==[cam['width'],cam['height']], 'camera/reference resolution mismatch')
        need(type(curve.get('closed')) is bool,'curve closed flag must be boolean')
        number(curve.get('max_error_px'),'max_error_px',True)
        bindings=curve.get('bindings');need(isinstance(bindings,list) and len(bindings)>=(3 if curve['closed'] else 2),'curve binding count')
        for binding in bindings:
            keys(binding,('component_id','vertex_index'),'binding');key=binding.get('component_id');i=binding.get('vertex_index')
            need(key in nodes and nodes[key].get('geometry',{}).get('type')=='mesh','curve binding requires actual explicit mesh')
            positions=nodes[key]['geometry'].get('positions',[])
            need(type(i) is int and 0<=i<len(positions)//3,'invalid native vertex index')
        need(len({(b['component_id'],b['vertex_index']) for b in bindings})==len(bindings),'duplicate curve binding')
        pairs=list(zip(bindings,bindings[1:]))+([(bindings[-1],bindings[0])] if curve['closed'] else [])
        for a,b in pairs:
            need(a['component_id']==b['component_id'],'curve consecutive bindings must share an actual triangle edge')
            key=a['component_id'];tri=nodes[key]['geometry'].get('triangles',[])
            edge=tuple(sorted((a['vertex_index'],b['vertex_index'])))
            if key not in edge_cache:
                need(isinstance(tri,list) and len(tri)%3==0 and all(type(i) is int for i in tri),'literal triangle indices required')
                edge_cache[key]={tuple(sorted(pair)) for k in range(0,len(tri),3) for pair in ((tri[k],tri[k+1]),(tri[k+1],tri[k+2]),(tri[k+2],tri[k]))}
            need(edge in edge_cache[key],'binding sequence is not an actual triangle edge')
        samples=curve.get('samples');need(isinstance(samples,list),'curve samples required');counts={'calibration':0,'validation':0}
        for sample in samples:
            keys(sample,('id','role','pixel','sigma_px'),'sample');sid=sample.get('id')
            need(isinstance(sid,str) and sid and sid not in sample_ids,'unique sample ID required');sample_ids.add(sid)
            need(sample.get('role') in counts,'sample role must be calibration or validation');counts[sample['role']]+=1
            scene_build.vector(sample.get('pixel'),2);number(sample.get('sigma_px'),'sigma_px',True)
        need(counts['calibration']>=4 and counts['validation']>=2,'each curve needs >=4 calibration and >=2 heldout samples')
    base=copy.deepcopy(spec)
    if isinstance(base['cameras'],dict):base['cameras'].update(initial_cameras)
    else:
        for entry in base['cameras']:
            if entry['id'] in initial_cameras:entry.update(initial_cameras[entry['id']])
    built_before=scene_build.build(base);protection_before=_protection(built_before,protected)
    sparse_initial=_sparse_curves(nodes,curves,parameters);full_initial=_full_curves(built_before,curves)
    need(all(np.allclose(full_initial[k],sparse_initial[k],rtol=0,atol=1e-9) for k in full_initial),'initial full/sparse native geometry mismatch')
    resources_verified,resource_errors,source_hashes,source_file_hashes=_resources(spec,curves,resource_root)
    evaluation_count=0
    def evaluate(x, role='calibration', details=False):
        nonlocal evaluation_count
        evaluation_count+=1
        current=copy.deepcopy(parameters)
        for key,value in zip(ids,lower+np.asarray(x)*spans):current[key]['value']=float(value)
        cams={key:camera(b,current) for key,b in builders.items()}
        worlds=_sparse_curves(nodes,curves,current);residual=[];rows=[]
        for curve in curves:
            polyline=[project(point,cams[curve['camera_id']]) for point in worlds[curve['id']]]
            for sample in curve['samples']:
                if sample['role']!=role:continue
                nearest,segment,t=_nearest(sample['pixel'],polyline,curve['closed'])
                delta=nearest-np.asarray(sample['pixel']);error=float(np.linalg.norm(delta))
                residual.extend((delta/sample['sigma_px']).tolist())
                if details:rows.append({'id':sample['id'],'curve_id':curve['id'],'role':role,'pixel':sample['pixel'],
                                        'nearest_pixel':nearest.tolist(),'segment_index':segment,'segment_fraction':t,
                                        'error_px':error,'sigma_px':sample['sigma_px'],'max_error_px':curve['max_error_px'],
                                        'passed':error<=curve['max_error_px']})
        return (np.asarray(residual),rows,worlds,cams) if details else np.asarray(residual)
    def jacobian(x,residual):
        columns=[]
        for i in range(len(ids)):
            lo=max(0.,float(x[i])-1e-5);hi=min(1.,float(x[i])+1e-5)
            left=x.copy();right=x.copy();left[i]=lo;right[i]=hi
            columns.append((evaluate(right)-evaluate(left))/(hi-lo))
        return np.stack(columns,axis=1)
    seeds=contract.get('seeds',[{key:parameters[key]['value'] for key in ids}])
    need(isinstance(seeds,list) and seeds,'nonempty seed list required');seed_reports=[];winner=None
    for seed_index,seed in enumerate(seeds):
        need(isinstance(seed,dict) and set(seed)==set(ids),'seed must specify every variable exactly')
        values=np.asarray([number(seed[k],'seed value') for k in ids]);x=(values-lower)/spans
        need(np.all((x>=0)&(x<=1)),'seed outside immutable bounds')
        try:
            residual=evaluate(x);score=float(np.dot(residual,residual));damping=1e-3;accepted=0
            initial=score
            for iteration in range(iterations):
                j=jacobian(x,residual);h=j.T@j;gradient=j.T@residual
                step=np.linalg.solve(h+damping*np.diag(np.maximum(np.diag(h),1.)), -gradient)
                trial=np.clip(x+step,0,1)
                if np.max(np.abs(trial-x))<1e-10:break
                try:
                    tr=evaluate(trial);ts=float(np.dot(tr,tr))
                except (ValueError,OverflowError,FloatingPointError):ts=math.inf
                if ts<score-1e-12:
                    x,residual,score=trial,tr,ts;accepted+=1;damping=max(1e-10,damping/3)
                else:damping=min(1e12,damping*10)
                if damping>=1e12:break
            seed_reports.append({'seed_index':seed_index,'initial_calibration_sse':initial,
                                 'final_calibration_sse':score,'accepted_steps':accepted,
                                 'values':dict(zip(ids,(lower+x*spans).tolist()))})
            if winner is None or score<winner[0]:winner=(score,x.copy(),seed_index)
        except (ValueError,OverflowError,np.linalg.LinAlgError) as exc:
            seed_reports.append({'seed_index':seed_index,'failed':str(exc)})
    need(winner is not None,'all calibration seeds failed')
    score,x,selected_seed=winner
    residual,calibration,worlds,cams=evaluate(x,details=True)
    # Nothing involving heldout data has participated in optimization or selection.
    _,validation,_,_=evaluate(x,role='validation',details=True)
    j=jacobian(x,residual);singular=np.linalg.svd(j,compute_uv=False)
    rank=int(np.linalg.matrix_rank(j));condition=float(singular[0]/singular[-1]) if rank==len(ids) and singular[-1]>0 else None
    candidate=copy.deepcopy(base)
    for key,value in zip(ids,lower+x*spans):candidate['parameters'][key]['value']=float(value)
    if isinstance(candidate['cameras'],dict):candidate['cameras'].update(cams)
    else:
        for entry in candidate['cameras']:
            if entry['id'] in cams:entry.update(cams[entry['id']])
    built_after=scene_build.build(candidate);full_after=_full_curves(built_after,curves)
    sparse_agrees=all(np.allclose(full_after[k],worlds[k],rtol=0,atol=1e-9) for k in worlds)
    protection_after=_protection(built_after,protected);protection_pass=protection_before==protection_after
    bound_hits=[key for key,value in zip(ids,x) if value<=1e-6 or value>=1-1e-6]
    errors=list(resource_errors)
    if not sparse_agrees:errors.append('final full/sparse native geometry mismatch')
    if not protection_pass:errors.append('protected actual geometry/transforms changed')
    if rank<len(ids):errors.append('calibration data Jacobian rank deficient')
    if condition is None or condition>max_condition:errors.append('calibration data condition exceeds declared maximum or is unidentifiable')
    if bound_hits and contract['reject_bound_hits']:errors.append('candidate hits immutable parameter boundary')
    for row in calibration+validation:
        if not row['passed']:errors.append('sample exceeds immutable error limit: '+row['id'])
    report={'version':1,'eligible_for_freeze':not errors,'errors':errors,'resources_verified':resources_verified,
            'visual_fidelity_accepted':False,'production_accepted':False,'selected_seed_index':selected_seed,
            'selection_basis':'calibration-only directed target-to-nearest actual mesh-edge polyline SSE',
            'initial_spec_sha256':digest(spec),'contract_sha256':digest(contract),'candidate_spec_sha256':digest(candidate),
            'initial_full_geometry_sha256':full_geometry_identity(built_before),
            'full_calibrated_geometry_sha256':full_geometry_identity(built_after),
            'source_images':source_hashes,'source_files':source_file_hashes,
            'camera_sha256':digest(cams),'actual_geometric_curves_sha256':digest(worlds),
            'initial_actual_geometric_curves_sha256':digest(full_initial),'calibration':calibration,'validation':validation,
            'calibration_sse':score,'seeds':seed_reports,'evaluation_count':evaluation_count,
            'data_jacobian':{'rank':rank,'variable_count':len(ids),'condition':condition,'max_condition':max_condition,
                             'singular_values':singular.tolist(),'basis':'calibration residual finite differences in normalized parameter ranges; no priors'},
            'bound_hits':bound_hits,'full_native_builds_verified':True,'sparse_matches_full':sparse_agrees,
            'protected_geometry_verified':protection_pass,'protected_geometry_hashes_before':protection_before,
            'protected_geometry_hashes_after':protection_after,'gauge':contract['gauge'],
            'scope':'directed visible traced samples only; not whole contour/Hausdorff, visibility proof, global identifiability or image reconstruction acceptance'}
    return {'spec':candidate,'report':report}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('spec','contract','out','report'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--resource-root');parser.add_argument('--iterations',type=int,default=120)
    args=parser.parse_args()
    try:
        outputs=[Path(args.out).resolve(),Path(args.report).resolve()];inputs={Path(args.spec).resolve(),Path(args.contract).resolve()}
        need(len(set(outputs))==2 and not any(p.exists() or p in inputs for p in outputs),'outputs must be distinct new files, never inputs')
        result=fit(json.loads(Path(args.spec).read_text()),json.loads(Path(args.contract).read_text()),args.resource_root,args.iterations)
        for path,value in zip(outputs,(result['spec'],result['report'])):
            with path.open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
        print(json.dumps({'eligible_for_freeze':result['report']['eligible_for_freeze'],'production_accepted':False}))
        return 0 if result['report']['eligible_for_freeze'] else 1
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'error':str(exc),'production_accepted':False}));return 2


if __name__=='__main__':raise SystemExit(main())
