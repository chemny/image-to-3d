#!/usr/bin/env python3
"""Immutable-reference landmark projection evidence; not automatic visual approval."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import scene_build
from reconstruction import project


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def require(ok, message):
    if not ok: raise ValueError(message)
def finite(value): return type(value) in (int, float) and math.isfinite(value)
def load(path): return json.loads(Path(path).read_text())


def binding_for(feature, spec, camera_id, reference_id):
    require(('binding' in feature) != ('observation_id' in feature), 'exactly one binding or observation_id required')
    if 'observation_id' in feature:
        rows = [o for o in spec.get('observations', []) if o.get('id') == feature['observation_id']]
        require(len(rows) == 1, 'missing/duplicate observation binding')
        row = rows[0]
        require(row.get('camera_id') == camera_id, 'observation camera mismatch')
        require(row.get('reference_id') == reference_id, 'observation reference mismatch')
    else: row = feature['binding']
    b = row.get('binding', row)
    require('local_point' not in b and ('vertex_index' in b or 'patch_id' in b), 'real geometry vertex or patch binding required; arbitrary local_point forbidden')
    return row


def evaluate(annotations, spec_path, out, baseline_report=None):
    from PIL import Image, ImageDraw
    annotations, spec_path = Path(annotations).resolve(), Path(spec_path).resolve()
    a, spec = load(annotations), load(spec_path)
    require(a.get('schema_version') == 1, 'unsupported annotation schema')
    require(a.get('transform') == {'kind': 'identity'}, 'crop/resize unsupported: supply exact unwarped reference dimensions')
    source = (annotations.parent / a['image']['path']).resolve()
    require(sha(source) == a['image']['sha256'], 'stale reference image')
    refspec = (annotations.parent / a['reference_spec']['path']).resolve()
    require(sha(refspec) == a['reference_spec']['sha256'], 'stale annotation reference spec')
    reference_spec = load(refspec)
    reference_id = a.get('reference_id')
    require(isinstance(reference_id, str) and reference_id, 'explicit reference_id required')
    for bound_spec, bound_path in ((reference_spec, refspec), (spec, spec_path)):
        matches = [r for r in bound_spec.get('references', []) if r.get('id') == reference_id]
        require(len(matches) == 1, 'missing/duplicate spec reference')
        entry = matches[0]
        ref_image = (bound_path.parent / entry['path']).resolve()
        require(ref_image.is_file() and sha(ref_image) == entry.get('sha256') == sha(source), 'spec reference image identity mismatch')

    with Image.open(source) as original: image = original.convert('RGB')
    size = list(image.size)
    require(size == a['image']['size'], 'reference dimensions mismatch')
    camera_id = a['camera_id']
    camera = scene_build.resolve(spec['cameras'][camera_id], spec.get('parameters', {}))
    refcamera = scene_build.resolve(reference_spec['cameras'][camera_id], reference_spec.get('parameters', {}))
    require(digest(camera) == digest(refcamera) == a['camera_sha256'], 'camera identity mismatch; recalibration requires new annotations')
    require([camera['width'], camera['height']] == size, 'camera dimensions mismatch')
    scene_build.build(spec)
    require(isinstance(a.get('features'), list) and a['features'], 'nonempty features required')
    baseline = load(baseline_report) if baseline_report else None
    if baseline:
        require(baseline['annotations_sha256'] == sha(annotations), 'annotation/tolerance changed since baseline')
        require(baseline['image_sha256'] == sha(source) and baseline['camera_sha256'] == digest(camera), 'baseline identity mismatch')
        baseline_spec = Path(baseline['spec_path'])
        require(sha(baseline_spec) == baseline['spec_sha256'], 'stale baseline model')
    previous = {r['id']: r for r in baseline['features']} if baseline else {}
    draw = ImageDraw.Draw(image)
    w, h = size
    for i in range(1, 10):
        draw.line([(w*i/10, 0), (w*i/10, h)], fill=(190,190,190), width=1)
        draw.line([(0, h*i/10), (w, h*i/10)], fill=(190,190,190), width=1)
    rows, seen = [], set()
    for feature in a['features']:
        fid = feature.get('id')
        require(isinstance(fid, str) and fid and fid not in seen, 'unique feature IDs required')
        seen.add(fid)
        target = feature['target_px']
        require(isinstance(target, list) and len(target) == 2 and all(finite(x) for x in target), 'finite target coordinates required')
        require(0 <= target[0] < w and 0 <= target[1] < h, 'target outside image')
        for field in ('uncertainty_px', 'tolerance_px'):
            require(finite(feature.get(field)) and feature[field] >= 0, 'explicit nonnegative '+field+' required')
        require(feature['tolerance_px'] >= feature['uncertainty_px'], 'tolerance below declared uncertainty')
        row = {'id': fid, 'kind': feature['kind'], 'target_px': target, 'target_normalized': [target[0]/w, target[1]/h], 'uncertainty_px': feature['uncertainty_px'], 'tolerance_px': feature['tolerance_px']}
        x,y = target
        draw.ellipse((x-3,y-3,x+3,y+3), fill='blue'); draw.text((x+5,y+5),fid, fill='blue')
        if feature['kind'] == 'silhouette':
            require(not feature.get('protected') and 'binding' not in feature and 'observation_id' not in feature, 'view-dependent silhouette cannot be a fixed 3D binding/protected landmark')
            row.update(status='manual-review-required', passed=None)
        else:
            require(feature['kind'] == 'landmark', 'unsupported feature kind')
            b = binding_for(feature, spec, camera_id, reference_id)
            # Binding semantics cannot silently change in a candidate Spec.
            require(digest(b) == digest(binding_for(feature, reference_spec, camera_id, reference_id)), 'candidate changed observation binding')
            scene_build.landmark(reference_spec, b)  # Validate frozen reference binding too.
            binding = b.get('binding', b)
            if 'vertex_index' in binding:
                cg = next(c for c in spec['components'] if c['id'] == b['component_id'])['geometry']
                rg = next(c for c in reference_spec['components'] if c['id'] == b['component_id'])['geometry']
                require(len(cg['positions']) == len(rg['positions']) and cg['triangles'] == rg['triangles'], 'vertex topology changed; rebind annotations explicitly')
            world = scene_build.landmark(spec, b)
            predicted = project(world, camera)
            delta = [predicted[i]-target[i] for i in range(2)]
            error = math.hypot(*delta)
            protected = feature.get('protected', False)
            require(type(protected) is bool, 'protected must be boolean')
            allowance = feature.get('regression_allowance_px', 0)
            require(finite(allowance) and allowance >= 0, 'invalid regression allowance')
            regression = None
            if protected and baseline:
                require(fid in previous and finite(previous[fid].get('error_px')), 'protected feature missing from baseline')
                regression = error > previous[fid]['error_px'] + allowance + 1e-9
            row.update(world=world, binding=b, predicted_px=predicted, predicted_normalized=[predicted[0]/w,predicted[1]/h], delta_px=delta, error_px=error, error_image_diagonal=error/math.hypot(w,h), protected=protected, regression=regression, passed=error <= feature['tolerance_px'] and not regression, status='measured')
            draw.line([tuple(target), tuple(predicted)], fill='red', width=2)
            px,py = predicted; angle = math.atan2(py-y,px-x)
            if error > 1:
                draw.polygon([(px,py),(px-8*math.cos(angle-.4),py-8*math.sin(angle-.4)),(px-8*math.cos(angle+.4),py-8*math.sin(angle+.4))],fill='red')
            draw.ellipse((px-3,py-3,px+3,py+3),outline='red',width=2)
        rows.append(row)
    result = {'schema_version': 1, 'claim': 'model-bound-projection-only', 'annotations_path':str(annotations),'annotations_sha256':sha(annotations),'image_path':str(source),'image_sha256':sha(source),'spec_path':str(spec_path),'spec_sha256':sha(spec_path),'reference_id':reference_id,'camera_id':camera_id,'camera_sha256':digest(camera),'camera':camera,'reference_spec_sha256':sha(refspec),'baseline_report_sha256':sha(baseline_report) if baseline_report else None,'features':rows,'numeric_checks_passed':any(r['status']=='measured' for r in rows) and all(r['passed'] for r in rows if r['status']=='measured'),'manual_review_pending':any(r['passed'] is None for r in rows),'visual_pass':False,'limitations':['No automatic thickness, occlusion, semantic correspondence or surface correctness proof.','Targets and tolerances must be authored from reference before fitting; hashes detect changes, not honest authorship or time of declaration.','Silhouette points are view-dependent; only annotated for manual contour review.','Uncertainty is recorded, not silently added to tolerance.','No crop, resize, auto alignment or reference warping performed.']}
    out = Path(out);out.mkdir(parents=True,exist_ok=False)
    image.save(out/'anchor-overlay.png')
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('annotations','spec','out'):p.add_argument('--'+name,required=True)
    p.add_argument('--baseline-report');args=p.parse_args()
    try:
        r=evaluate(args.annotations,args.spec,args.out,args.baseline_report)
        print(json.dumps({'numeric_checks_passed':r['numeric_checks_passed'],'visual_pass':False,'report':str(Path(args.out)/'report.json')}))
    except (ValueError,KeyError,TypeError,OSError) as e:p.exit(2,str(e)+'\n')
if __name__=='__main__':main()
