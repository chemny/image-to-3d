// IDs refer to original glTF node / primitive indices, never fuzzy node names.
export function collectBindings(gltf) {
  const rows=[];
  gltf.scene.traverse(o=>{if(!o.isMesh)return;const a=gltf.parser.associations.get(o)||{};let n=o;
    while(n&&gltf.parser.associations.get(n)?.nodes===undefined)n=n.parent;
    const ni=n?gltf.parser.associations.get(n).nodes:undefined;
    if(ni===undefined||a.primitives===undefined)throw Error('无法获取网格的 glTF 绑定标识');
    rows.push({id:`n${ni}:p${a.primitives}`,object:o,node_index:ni,primitive_index:a.primitives,source_material:a.materials??gltf.parser.associations.get(o.material)?.materials});
  });return rows;
}
export function snapshotMaterial(m) {
  const result={type:m.type,name:m.name,pigment:m.userData.pigment?.toArray()};
  for(const k of ['color','emissive'])result[k]=m[k]?.toArray();
  for(const k of ['roughness','metalness','opacity','transparent','transmission','ior','thickness','alphaTest','side','depthWrite','emissiveIntensity'])result[k]=m[k];
  for(const k of ['map','normalMap','roughnessMap','metalnessMap','emissiveMap','alphaMap','aoMap'])result[k]=m[k]?.uuid??null;
  return result;
}
export function bindPaint(rows,config) {
  const targets=new Set(config.paintTargets);const bindings=[];
  if(targets.size!==config.paintTargets.length)throw Error('重复车漆绑定');
  if(targets.size&&config.paintMaterials.length)throw Error('不要混用索引和旧材质名绑定');
  const legacy=new Set(config.paintMaterials);
  // Ambiguous old shared material is rejected. Explicit index binding permits clone isolation.
  for(const name of legacy){const matches=rows.filter(r=>r.object.material.name===name);if(matches.length!==1)throw Error('旧材质绑定缺失或共享，请改用 paintTargets：'+name);targets.add(matches[0].id);}
  for(const id of targets){const hits=rows.filter(r=>r.id===id);if(hits.length!==1)throw Error('车漆目标缺失或不唯一：'+id);const r=hits[0];if(Array.isArray(r.object.material))throw Error('需导出独立 glTF primitive');
    const original=r.object.material;const material=original.clone();r.object.material=material;
    const color=original.color.clone();bindings.push({id,material,setColor(value){material.color.set(value);},restore(){material.color.copy(color);}});
  }
  return bindings;
}
