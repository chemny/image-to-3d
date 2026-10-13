"""Validate declared feature/relationship coverage; never certify visual quality.

Independent standard-library implementation. Call on resolved scene parameters.
A method name or vertex association is a semantic contract, not geometric proof.
Workflow remains responsible for artifact hashes, reviewers, verdicts and stage order.
"""
import math
import scene_build

PROFILES = ('soft', 'hard', 'assembly', 'moving')
FORMS = ('volume', 'concavity', 'branch', 'thickness', 'layer', 'curve', 'surface_detail')
RELATIONS = ('contact', 'gap', 'overlap', 'wrap', 'fusion', 'hinge')
COVERAGE = 'production-feature-coverage'


def require(condition, message):
    if not condition:
        raise ValueError('production contract: ' + message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def names(value, label, allowed=None, minimum=1):
    require(isinstance(value, list) and len(value) >= minimum, label + ' must be a list of sufficient length')
    require(all(text(x) for x in value), label + ' needs nonempty string IDs')
    require(len(set(value)) == len(value), label + ' contains duplicate IDs')
    if allowed is not None:
        require(all(x in allowed for x in value), label + ' has unknown value or target')
    return value


def index(value, label):
    require(isinstance(value, list), label + ' must be a list')
    result = {}
    for row in value:
        require(isinstance(row, dict) and text(row.get('id')), label + ' needs object entries with IDs')
        require(row['id'] not in result, label + ' contains duplicate IDs')
        result[row['id']] = row
    return result


def visual(check):
    return isinstance(check.get('kind'), str) and 'visual' in check['kind'].lower()


def vertex(binding, parts):
    require(isinstance(binding, dict), 'geometry binding must be an object')
    cid = binding.get('component_id')
    require(text(cid) and cid in parts, 'geometry binding needs a real part')
    geometry = parts[cid]['geometry']
    require(geometry.get('type') == 'mesh', 'vertex binding requires explicit mesh geometry')
    positions = geometry.get('positions')
    require(isinstance(positions, list) and len(positions) >= 9 and len(positions) % 3 == 0
            and all(number(x) for x in positions), 'vertex binding requires finite mesh positions')
    vi = binding.get('vertex_index')
    require(type(vi) is int and 0 <= vi < len(positions) // 3, 'vertex_index outside actual mesh range')
    triangles = geometry.get('triangles')
    require(isinstance(triangles, list) and len(triangles) >= 3 and len(triangles) % 3 == 0
            and all(type(i) is int and 0 <= i < len(positions) // 3 for i in triangles),
            'vertex binding requires valid triangle index triples')
    require(vi in triangles, 'vertex binding cannot target an isolated vertex outside triangles')
    return cid


def observation_binding(spec, observation, parts):
    """Resolve an actual surface association, including parameters and ancestors."""
    binding = observation.get('binding', observation)
    require(isinstance(binding, dict) and 'local_point' not in binding
            and sum(k in binding for k in ('vertex_index', 'patch_id')) == 1,
            'observation requires an actual vertex or patch binding, not local_point')
    cid = observation['component_id']
    if 'vertex_index' in binding:
        vertex({'component_id': cid, 'vertex_index': binding['vertex_index']}, parts)
    else:
        require(parts[cid]['geometry'].get('type') == 'bezier_network',
                'patch binding requires Bezier network geometry')
        require(text(binding.get('patch_id')), 'patch binding needs patch_id')
    try:
        point = scene_build.landmark(spec, observation)
    except (ValueError, KeyError, TypeError, IndexError, StopIteration, OverflowError) as exc:
        raise ValueError('production contract: invalid observation surface binding: ' + str(exc)) from exc
    require(isinstance(point, list) and len(point) == 3 and all(number(x) for x in point),
            'observation binding must resolve to a finite world point')


def validate(spec):
    """Return a scoped report, or ValueError for a malformed opt-in v1 contract."""
    require(isinstance(spec, dict), 'Spec must be an object')
    if 'production_contract' not in spec:
        return {'passed': True, 'scope': 'legacy', 'production_certified': False,
                'professional_quality_verified': False,
                'limitations': ['No production contract; legacy validation is not production certification.']}
    contract = spec['production_contract']
    require(isinstance(contract, dict), 'production_contract must be an object')
    require(type(contract.get('version')) is int and contract['version'] == 1, 'unsupported version')
    profiles = names(contract.get('profiles'), 'profiles', PROFILES)
    # Use the scene authority so bad parameters, cycles and invalid parent transforms
    # cannot hide behind otherwise plausible feature metadata.
    try:
        spec, _ = scene_build.prepared(spec)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as exc:
        raise ValueError('production contract: invalid scene parameters or transforms: ' + str(exc)) from exc
    contract = spec['production_contract']
    nodes = index(spec.get('components'), 'components')
    parts = {cid: c for cid, c in nodes.items() if c.get('kind', 'part') == 'part'
             and isinstance(c.get('geometry'), dict) and text(c['geometry'].get('type'))}
    refs = index(spec.get('references'), 'references')
    observations = index(spec.get('observations', []), 'observations')
    checks = index(spec.get('checks'), 'checks')
    required = {cid: c for cid, c in checks.items() if c.get('required') is True}
    coverage = required.get(COVERAGE, {})
    require(visual(coverage) and coverage.get('stage') == 'body',
            'required visual body check production-feature-coverage must be declared')
    features = index(contract.get('features'), 'features')
    require(bool(features), 'features must not be empty')
    for fid, feature in features.items():
        label = 'feature ' + fid
        reference = feature.get('reference_id')
        require(text(reference) and reference in refs, label + ' has unknown reference')
        roi = feature.get('roi')
        require(isinstance(roi, list) and len(roi) == 4 and all(number(x) and 0 <= x <= 1 for x in roi)
                and roi[0] < roi[2] and roi[1] < roi[3], label + ' requires normalized nonzero ROI [x0,y0,x1,y1]')
        require(feature.get('provenance') in ('observed', 'inferred'), label + ' invalid provenance')
        require(feature.get('importance') in ('critical', 'important', 'supporting'), label + ' invalid importance')
        require(feature.get('form_type') in FORMS, label + ' invalid form_type')
        component_ids = names(feature.get('component_ids'), label + ' component_ids', parts)
        check_ids = names(feature.get('check_ids'), label + ' check_ids', required)
        if feature['importance'] in ('critical', 'important'):
            require(any(visual(required[c]) and required[c].get('stage', 'review') in ('body', 'review')
                        for c in check_ids), label + ' needs required visual body/review check')
        method = feature.get('method')
        require(isinstance(method, dict) and text(method.get('type')) and text(method.get('rationale')),
                label + ' needs method type and rationale')
        if feature['importance'] == 'critical':
            forbidden = {'concavity': ('flat_patch', 'painted_line'), 'branch': ('painted_line',)}
            require(method['type'].strip().lower() not in forbidden.get(feature['form_type'], ()),
                    label + ' method contradicts critical volumetric form')
        bound = set()
        if 'observation_ids' in feature:
            for oid in names(feature['observation_ids'], label + ' observation_ids', observations):
                obs = observations[oid]
                cid = obs.get('component_id')
                require(text(cid) and cid in component_ids, label + ' observation must reference its geometry part')
                require(obs.get('reference_id') == reference, label + ' observation reference mismatch')
                observation_binding(spec, obs, parts)
                bound.add(cid)
        if 'geometry_bindings' in feature:
            bindings = feature['geometry_bindings']
            require(isinstance(bindings, list) and bool(bindings), label + ' geometry_bindings must be nonempty')
            for binding in bindings:
                cid = vertex(binding, parts)
                require(cid in component_ids, label + ' binding component outside feature')
                bound.add(cid)
        require(bound == set(component_ids), label + ' every component needs observation or mesh vertex binding')
    relations = index(contract.get('relations'), 'relations')
    require('assembly' not in profiles or bool(relations),
            'assembly profile requires at least one declared relation')
    require('moving' not in profiles or any(r.get('type') == 'hinge' for r in relations.values()),
            'moving profile requires at least one hinge relation with an actual action')
    actions = index(spec.get('actions', []), 'actions')
    for rid, relation in relations.items():
        label = 'relation ' + rid
        require(relation.get('type') in RELATIONS, label + ' invalid type')
        cids = names(relation.get('component_ids'), label + ' component_ids', parts, 2)
        names(relation.get('check_ids'), label + ' check_ids', required)
        require(text(relation.get('rationale')), label + ' rationale required')
        if relation['type'] == 'hinge':
            matches = [a for a in actions.values() if a.get('component_id') in cids]
            require(any(a.get('axis') in ('x', 'y', 'z') and number(a.get('angle')) and a['angle'] != 0
                        and isinstance(a.get('pivot'), list) and len(a['pivot']) == 3
                        and all(number(x) for x in a['pivot']) for a in matches),
                    label + ' hinge requires a matching real action with axis, angle and pivot')
    return {'passed': True, 'scope': 'production-contract-v1', 'profiles': profiles,
            'feature_count': len(features), 'relation_count': len(relations),
            'production_certified': False, 'professional_quality_verified': False,
            'limitations': ['Declared semantics and bindings only; no geometric or visual fidelity proof.',
                            'Soft/hard profiles select construction rules; material softness/hardness is not measured.',
                            'Feature omission requires independent visual coverage review.']}


def validate_evidence(spec, evidence, stage):
    """Additional evidence guard; workflow must validate artifacts and acceptance."""
    report = validate(spec)
    if report['scope'] == 'legacy':
        return report
    require(isinstance(evidence, dict), 'evidence must be an object')
    results = index(evidence.get('check_results', []), 'check_results')
    checks = index(spec['checks'], 'checks')
    ids = {COVERAGE} if stage == 'body' else set()
    for feature in spec['production_contract']['features']:
        if feature['importance'] in ('critical', 'important'):
            ids.update(cid for cid in feature['check_ids'] if visual(checks[cid])
                       and checks[cid].get('stage', 'review') == stage)
    for cid in ids:
        require(cid in results and results[cid].get('method') == 'visual'
                and results[cid].get('verdict') == 'pass',
                'required passing visual evidence missing: ' + cid)
    return report
