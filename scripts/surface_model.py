#!/usr/bin/env python3
"""Small, explicit parametric surface experiment, not a complete reconstruction engine.

Component geometry.type: patch_network or lathe. geometry.parameters maps semantic
names to top-level parameter IDs (omitting mapping uses identical names). Geometry
segments=[nu,nv], optional split_rows partitions a shared vertex grid into named
patches. Patch coordinates u in [-1,1], v in [0,1]; lathe u,v in [0,1].
Patch semantics: width is HALF width, length longitudinal extent, height crown;
nose_drop, shoulder_drop lower crown and sides, taper narrows nose. This graph
surface cannot represent undercuts or a complete vehicle. Lathe radius + bulge
sin(pi*v) creates an open rotational shell. Normals use consistent derivatives.
JSON output exposes shared indices; JS factory returns a Three.Group of meshes.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def values(spec):
    result = {}
    for key, item in spec['parameters'].items():
        v, lo, hi = item['value'], item['min'], item['max']
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (v, lo, hi)) or not lo <= v <= hi:
            raise ValueError('invalid parameter bounds: ' + key)
        result[key] = v
    return result


def point(geometry, params, u, v):
    mapping = geometry.get('parameters', {})
    def p(name, default):
        if name in mapping and mapping[name] not in params: raise ValueError('unknown parameter mapping: '+mapping[name])
        return params.get(mapping.get(name, name), default)
    if geometry['type'] == 'patch_network':
        w, length = p('width', 1), p('length', 2)
        taper = p('taper', .1)
        if w <= 0 or length <= 0 or not 0 <= taper < .9:
            raise ValueError('patch width/length must be positive; taper in [0,.9)')
        return [u*w*(1-taper*v*v), p('height', 1)-p('nose_drop', .2)*v*v-p('shoulder_drop', .15)*u*u,
                length*(.5-v)]
    if geometry['type'] == 'lathe':
        r = p('radius', .5)+p('bulge', .1)*math.sin(math.pi*v)
        if r <= 0 or p('height', 1) <= 0:
            raise ValueError('lathe radius and height must remain positive')
        return [r*math.cos(2*math.pi*u), p('height', 1)*v, r*math.sin(2*math.pi*u)]
    raise ValueError('unsupported geometry: '+geometry['type'])


def normal(geometry, params, u, v):
    e = 1e-5
    def delta(a, b): return [x-y for x,y in zip(a,b)]
    du = delta(point(geometry,params,u+e,v),point(geometry,params,u-e,v))
    dv = delta(point(geometry,params,u,v+e),point(geometry,params,u,v-e))
    n = [du[1]*dv[2]-du[2]*dv[1],du[2]*dv[0]-du[0]*dv[2],du[0]*dv[1]-du[1]*dv[0]]
    if geometry['type'] == 'lathe': n = [-x for x in n]
    length = math.sqrt(sum(x*x for x in n))
    if length < 1e-14: raise ValueError('degenerate surface derivative')
    return [x/length for x in n]


def build(spec):
    params = values(spec)
    output = {'schema_version':1,'spec_sha256':digest(spec),'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope':'parametric open surface experiment; no photographic fidelity claim','components':[]}
    ids=[c['id'] for c in spec['components']]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate component ID')
    parents={c['id']:c.get('parent') for c in spec['components']}
    for key in ids:
        visited=set();cursor=key
        while cursor is not None:
            if cursor in visited or cursor not in parents: raise ValueError('cyclic or missing parent')
            visited.add(cursor);cursor=parents[cursor]
    for component in spec['components']:
        g = component['geometry']; nu,nv = g.get('segments',[24,24])
        if not all(isinstance(x,int) and 2 <= x <= 256 for x in (nu,nv)): raise ValueError('segments must be integers in [2,256]')
        positions=[]; normals=[]
        for j in range(nv+1):
            for i in range(nu+1):
                u = i/nu if g['type']=='lathe' else -1+2*i/nu
                positions.extend(point(g,params,u,j/nv)); normals.extend(normal(g,params,u,j/nv))
        splits = sorted(set([0,nv]+g.get('split_rows',[nv//2])))
        if any(not isinstance(x,int) or not 0 <= x <= nv for x in splits): raise ValueError('invalid split row')
        patches=[]
        for lo,hi in zip(splits,splits[1:]):
            indices=[]
            for j in range(lo,hi):
                for i in range(nu):
                    a=j*(nu+1)+i;b=a+1;c=a+nu+1;d=c+1
                    indices.extend([a,c,b,b,c,d] if g['type']=='lathe' else [a,b,c,b,d,c])
            patches.append({'id':component['id']+':'+str(lo),'indices':indices})
        output['components'].append({'id':component['id'],'parent':component.get('parent'),'positions':positions,'normals':normals,'patches':patches})
    return output


def javascript(mesh):
    return "import * as THREE from 'three';\nconst data="+json.dumps(mesh,separators=(',',':'))+";\n"+'''export function buildModel(material = new THREE.MeshStandardMaterial({color:0x9ca5ac,roughness:.4,side:THREE.DoubleSide})) {
  const root=new THREE.Group(); const groups=new Map();
  for (const c of data.components) { const group=new THREE.Group();group.name=c.id;groups.set(c.id,group);
    for(const p of c.patches){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(c.positions,3));g.setAttribute('normal',new THREE.Float32BufferAttribute(c.normals,3));g.setIndex(p.indices);g.computeBoundingSphere();const m=new THREE.Mesh(g,material);m.name=p.id;group.add(m);}
  }
  for(const c of data.components){const parent=c.parent?groups.get(c.parent):root;if(!parent)throw new Error('Missing parent '+c.parent);parent.add(groups.get(c.id));}return root;
}
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('spec');parser.add_argument('--out',required=True);parser.add_argument('--js')
    args=parser.parse_args();mesh=build(json.loads(Path(args.spec).read_text()));Path(args.out).write_text(json.dumps(mesh))
    if args.js: Path(args.js).write_text(javascript(mesh))
    print(json.dumps({'spec_sha256':mesh['spec_sha256'],'components':len(mesh['components'])}))

if __name__=='__main__': main()
