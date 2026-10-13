"""Validate opt-in asset metadata, not image fidelity or resource file contents.

Call with a resolved Spec (scene_build.prepared) when numeric parameters are used.
Legacy Specs retain their existing scene validation; this module does not certify them.
"""
import math
import re
from pathlib import PurePosixPath


def _require(condition, message):
    if not condition:
        raise ValueError('asset contract: ' + message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value, length=3):
    return isinstance(value, list) and len(value) == length and all(_number(x) for x in value)


def _names(value, label, allowed=None, nonempty=False):
    _require(isinstance(value, list), label + ' must be a list')
    _require(all(_text(x) for x in value), label + ' needs nonempty strings')
    _require(len(set(value)) == len(value), label + ' has duplicate IDs')
    _require(not nonempty or bool(value), label + ' must not be empty')
    if allowed is not None:
        _require(all(x in allowed for x in value), label + ' has unknown target or value')
    return value


def validate(spec):
    """Return a scoped report; reject malformed v1 contracts with ValueError.

    ``passed`` means declared structure is consistent. Actual texture bytes,
    runtime behavior, export, and visual acceptance require separate evidence.
    """
    _require(isinstance(spec, dict), 'Spec must be an object')
    if 'asset_contract' not in spec:
        return {'passed': True, 'scope': 'legacy', 'professional_quality_verified': False,
                'limitations': ['No asset contract declared; legacy scene checks still required.']}
    contract = spec['asset_contract']
    _require(isinstance(contract, dict), 'asset_contract must be an object')
    _require(type(contract.get('version')) is int and contract['version'] == 1, 'unsupported version')
    for field, allowed in (
        ('object_class', ('generic', 'car', 'bicycle', 'motorcycle', 'toy')),
        ('intended_use', ('display', 'configurator', 'disassembly', 'animation')),
        ('units_source', ('relative', 'measured', 'inferred')),
    ):
        _require(contract.get(field) in allowed, 'invalid ' + field)
    _require(_text(contract.get('source_notes')), 'source_notes must state reference/inference evidence')
    operations = _names(contract.get('required_operations'), 'required_operations',
                        ('select', 'material', 'variant', 'explode', 'action'))
    _names(contract.get('delivery_targets'), 'delivery_targets', ('threejs', 'glb', 'blender'), True)
    components = spec.get('components')
    _require(isinstance(components, list) and bool(components), 'components must be nonempty')
    nodes = {}
    for c in components:
        _require(isinstance(c, dict) and _text(c.get('id')), 'component needs an ID')
        _require(c['id'] not in nodes, 'duplicate component ID: ' + c['id'])
        nodes[c['id']] = c
    _names(contract.get('required_components'), 'required_components', nodes, True)
    materials = spec.get('materials')
    _require(isinstance(materials, dict) and bool(materials), 'materials must be a nonempty object')
    for mid, material in materials.items():
        _require(_text(mid) and isinstance(material, dict), 'invalid material')
        _require(isinstance(material.get('color'), str) and
                 re.fullmatch(r'#[0-9a-fA-F]{6}', material['color']), 'material color must be hex')
        for field in ('roughness', 'metalness', 'opacity', 'transmission', 'clearcoat'):
            if field in material:
                _require(_number(material[field]) and 0 <= material[field] <= 1, 'invalid material ' + field)
        if 'emissive' in material:
            _require(isinstance(material['emissive'], str) and
                     re.fullmatch(r'#[0-9a-fA-F]{6}', material['emissive']), 'invalid emissive color')
        if 'emissiveIntensity' in material:
            _require(_number(material['emissiveIntensity']) and material['emissiveIntensity'] >= 0,
                     'invalid emissive intensity')
        source = material.get('source')
        _require(isinstance(source, dict) and source.get('kind') in
                 ('reference-inferred', 'measured', 'designed') and _text(source.get('note')),
                 'material ' + mid + ' needs explicit source kind and note')
        maps = material.get('maps', {})
        _require(isinstance(maps, dict), 'material maps must be an object')
        for channel, texture in maps.items():
            _require(channel in ('map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap'),
                     'unsupported texture channel')
            _require(isinstance(texture, dict), 'texture metadata must be an object')
            path = texture.get('path')
            _require(_text(path), 'texture path required')
            _require(not PurePosixPath(path).is_absolute() and
                     not any(p in ('', '.', '..') for p in path.split('/')) and
                     not any(ch in path for ch in ('\\', ':', '\x00', '?', '#')),
                     'texture path must be relative to resource root without traversal')
            _require(isinstance(texture.get('sha256'), str) and
                     re.fullmatch(r'[0-9a-fA-F]{64}', texture['sha256']), 'texture sha256 required')
            expected = 'srgb' if channel in ('map', 'emissiveMap') else 'linear'
            _require(texture.get('color_space') == expected, channel + ' color_space must be ' + expected)

    for cid, c in nodes.items():
        _require(_text(c.get('role')), cid + ' needs a semantic role')
        kind = c.get('kind', 'part')
        _require(kind in ('part', 'assembly'), cid + ' invalid kind')
        if 'selectable' in c:
            _require(type(c['selectable']) is bool, cid + ' selectable must be boolean')
        if 'explode_vector' in c:
            _require(_vector(c['explode_vector']), cid + ' explode_vector must be finite xyz')
        for field in ('position', 'rotation'):
            if field in c:
                _require(_vector(c[field]), cid + ' invalid ' + field)
        parent = c.get('parent')
        _require(parent is None or (_text(parent) and parent in nodes), cid + ' missing parent')
        slots = c.get('material_slots', {})
        _require(isinstance(slots, dict) and all(_text(k) and _text(v) and v in materials
                                                for k, v in slots.items()), cid + ' invalid material_slots')
        if kind == 'assembly':
            _require(c.get('geometry') is None and c.get('material') is None and not slots,
                     cid + ' assembly cannot carry geometry/material; use child parts')
        else:
            _require(_text(c.get('material')) and c['material'] in materials, cid + ' missing material')
            geometry = c.get('geometry')
            _require(isinstance(geometry, dict) and _text(geometry.get('type')), cid + ' part needs geometry')
            mapped = any(materials[m].get('maps') for m in {c['material'], *slots.values()})
            if mapped:
                _require(geometry['type'] in ('mesh', 'torus', 'tube'),
                         cid + ' textured geometry needs explicit mesh UVs or torus/tube generated UVs')
            if (mapped and geometry['type'] == 'mesh') or 'uvs' in geometry or 'normals' in geometry:
                _require(geometry['type'] == 'mesh', cid + ' supplied UV/normals require explicit mesh')
                positions = geometry.get('positions')
                _require(isinstance(positions, list) and len(positions) >= 9 and len(positions) % 3 == 0
                         and all(_number(x) for x in positions), cid + ' invalid mesh positions')
                if mapped or 'uvs' in geometry:
                    _require(_vector(geometry.get('uvs'), len(positions) // 3 * 2), cid + ' UV count must match vertices')
                if 'normals' in geometry:
                    normals = geometry['normals']
                    _require(_vector(normals, len(positions)), cid + ' normal count must match vertices')
                    _require(all(sum(x*x for x in normals[i:i+3]) > 0 for i in range(0, len(normals), 3)),
                             cid + ' zero normal')
        visited = set()
        cursor = cid
        while cursor is not None:
            _require(cursor in nodes and cursor not in visited, cid + ' cyclic or missing parent')
            visited.add(cursor)
            cursor = nodes[cursor].get('parent')
            _require(cursor is None or _text(cursor), cid + ' invalid parent ID')

    variants = spec.get('variants', [])
    _require(isinstance(variants, list), 'variants must be a list')
    variant_ids, claimed = set(), set()
    for variant in variants:
        _require(isinstance(variant, dict) and _text(variant.get('id')), 'variant needs ID')
        _require(variant['id'] not in variant_ids, 'duplicate variant ID')
        variant_ids.add(variant['id'])
        options = variant.get('options')
        _require(isinstance(options, dict) and len(options) >= 2 and all(_text(k) for k in options),
                 'variant needs at least two named options')
        _require(_text(variant.get('default')) and variant['default'] in options, 'variant default missing')
        for roots in options.values():
            for root in _names(roots, 'variant option', nodes, True):
                subtree = set()
                for cid in nodes:
                    cursor = cid
                    while cursor is not None:
                        if cursor == root:
                            subtree.add(cid)
                            break
                        cursor = nodes[cursor].get('parent')
                _require(not subtree.intersection(claimed), 'variant subtrees overlap or are nested')
                claimed.update(subtree)

    actions = spec.get('actions', [])
    _require(isinstance(actions, list), 'actions must be a list')
    action_ids, action_targets = set(), set()
    for action in actions:
        _require(isinstance(action, dict) and _text(action.get('id')), 'action needs ID')
        target = action.get('component_id')
        _require(_text(target) and target in nodes, 'action target missing')
        _require(action['id'] not in action_ids and target not in action_targets, 'duplicate action ID/target')
        _require(action.get('axis') in ('x', 'y', 'z') and _number(action.get('angle')) and
                 action['angle'] != 0 and _vector(action.get('pivot')), 'invalid action axis/angle/pivot')
        action_ids.add(action['id'])
        action_targets.add(target)
    targets = {
        'select': [cid for cid, c in nodes.items() if c.get('selectable') is True],
        'material': [cid for cid, c in nodes.items() if c.get('kind', 'part') == 'part' and c.get('material_slots')],
        'variant': sorted(variant_ids),
        'explode': [cid for cid, c in nodes.items() if any(c.get('explode_vector', [0, 0, 0]))],
        'action': sorted(action_ids),
    }
    for operation in operations:
        _require(bool(targets[operation]), 'required operation has no target: ' + operation)
    return {'passed': True, 'scope': 'asset-contract-v1', 'professional_quality_verified': False,
            'operation_targets': targets, 'component_count': len(nodes),
            'limitations': ['Structural metadata only; texture bytes, visual fidelity, runtime and exports require acceptance evidence.']}
