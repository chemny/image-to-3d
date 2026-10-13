export function buildScene() {
  const root=new THREE.Group();root.name='spec-model';
  const materials={},nodes={},parts={},definitions={},pending=[];
  const variants={},overrides={};let explodeAmount=0,selected=null;
  const allowed=['color','roughness','metalness','clearcoat','transmission','opacity','emissive','emissiveIntensity'];
  for(const [id,definition] of Object.entries(data.materials)){
    const options={};for(const key of allowed)if(definition[key]!==undefined)options[key]=definition[key];
    if(options.opacity!==undefined&&options.opacity<1)options.transparent=true;
    materials[id]=new THREE.MeshPhysicalMaterial(options);materials[id].name=id;
    for(const [slot,map] of Object.entries(definition.maps||{})){
      pending.push(new Promise((resolve,reject)=>new THREE.TextureLoader().load(new URL(map.path,import.meta.url).href,texture=>{texture.flipY=false;texture.colorSpace=map.color_space==='srgb'?THREE.SRGBColorSpace:THREE.NoColorSpace;materials[id][slot]=texture;materials[id].needsUpdate=true;resolve();},undefined,reject)));
    }
  }
  for(const c of data.components){
    definitions[c.id]=c;const group=new THREE.Group();group.userData.component_id=c.id;group.userData.kind=c.kind||'part';group.name=c.id;group.position.fromArray(c.position);group.rotation.set(...c.rotation,'XYZ');nodes[c.id]=group;
    for(const mesh of c.meshes){
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(mesh.positions,3));geometry.setAttribute('normal',new THREE.Float32BufferAttribute(mesh.normals,3));if(mesh.uvs){geometry.setAttribute('uv',new THREE.Float32BufferAttribute(mesh.uvs,2));geometry.setAttribute('uv1',new THREE.Float32BufferAttribute(mesh.uvs,2));}geometry.setIndex(mesh.indices);geometry.computeBoundingSphere();
      const object=new THREE.Mesh(geometry,materials[c.material]);object.name=(data.vehicle_bindings?.lights.includes(c.material)?'light-':'')+c.id+(mesh.id?':'+mesh.id:'');object.castShadow=true;object.receiveShadow=true;group.add(object);
    }
  }
  const actionsByComponent=new Map(data.actions.map(a=>[a.component_id,a]));
  for(const c of data.components){
    const parent=c.parent?nodes[c.parent]:root,group=nodes[c.id],a=actionsByComponent.get(c.id);
    if(a){const pivot=new THREE.Group();pivot.name='pivot:'+a.id;pivot.position.fromArray(a.pivot);group.position.sub(pivot.position);parent.add(pivot);pivot.add(group);parts[a.id]={group:pivot,axis:a.axis,angle:a.angle,value:0,target:0};}
    else parent.add(group);
  }
  function setAction(id,value,options={}){const p=parts[id];if(!p||!Number.isFinite(value)||value<0||value>1)throw new Error('Invalid action');p.target=value;if(options.immediate){p.value=value;p.group.rotation[p.axis]=p.angle*value;}root.updateMatrixWorld(true);}
  function animate(dt){if(!Number.isFinite(dt)||dt<0)throw new Error('Invalid timestep');for(const p of Object.values(parts)){p.value+=(p.target-p.value)*(1-Math.exp(-Math.min(dt,.1)*10));if(Math.abs(p.target-p.value)<1e-5)p.value=p.target;p.group.rotation[p.axis]=p.angle*p.value;}}
  function setWheel(index){const bindings=data.vehicle_bindings;if(!bindings)throw new Error('Wheel bindings required');if(!Number.isInteger(index)||index<0||index>=bindings.wheels.length)throw new Error('Invalid wheel variant');bindings.wheels.forEach((ids,i)=>ids.forEach(id=>nodes[id].visible=i===index));}
  if(data.vehicle_bindings)setWheel(0);
  const rest=new Map(Object.entries(nodes).map(([id,n])=>[id,n.position.clone()]));
  const variantDefs=new Map((data.variants||[]).map(v=>[v.id,v]));
  function setVariant(id,option){const v=variantDefs.get(id);if(!v||!Object.hasOwn(v.options,option))throw new Error('Unknown asset variant');for(const [name,ids] of Object.entries(v.options))for(const key of ids)nodes[key].visible=name===option;variants[id]=option;root.updateMatrixWorld(true);}
  for(const v of data.variants||[])setVariant(v.id,v.default);
  function getPart(object){for(let n=object;n;n=n.parent)if(!n.visible)return null;while(object&&object!==root){const id=object.userData.component_id;if(id&&definitions[id].selectable!==false)return id;object=object.parent;}return null;}
  function select(id){if(id!==null&&(!nodes[id]||definitions[id].selectable===false))throw new Error('Unselectable component');selected=id;return id===null?null:describe(id);}
  function describe(id){const c=definitions[id];if(!c)throw new Error('Unknown component');return {id,parent:c.parent,kind:c.kind,material:c.material,material_slots:c.material_slots||{},children:data.components.filter(x=>x.parent===id).map(x=>x.id)};}
  function setMaterial(id,slot){const c=definitions[id];if(!c||!c.meshes.length)throw new Error('Material target must be a part');const materialId=c.material_slots?.[slot]||(slot===c.material?slot:null);if(!materialId||!materials[materialId])throw new Error('Undeclared material slot');for(const obj of nodes[id].children)if(obj.isMesh){if(obj.userData.localMaterial)obj.material.dispose();obj.userData.localMaterial=false;obj.material=materials[materialId];}overrides[id]=materialId;}
  function setColor(id,value){const c=definitions[id];if(!c||!c.meshes.length||!/^#[0-9a-fA-F]{6}$/.test(value))throw new Error('Invalid scoped color');for(const obj of nodes[id].children)if(obj.isMesh){if(!obj.userData.localMaterial){obj.material=obj.material.clone();obj.userData.localMaterial=true;}obj.material.color.set(value);}overrides[id]={color:value};}
  function explode(amount){if(!Number.isFinite(amount)||amount<0||amount>1)throw new Error('Explode amount must be 0..1');explodeAmount=amount;for(const [id,node] of Object.entries(nodes))node.position.copy(rest.get(id)).addScaledVector(new THREE.Vector3(...(definitions[id].explode_vector||[0,0,0])),amount);root.updateMatrixWorld(true);}
  function reset(){explode(0);for(const id of Object.keys(parts))setAction(id,0,{immediate:true});for(const v of data.variants||[])setVariant(v.id,v.default);for(const c of data.components)for(const obj of nodes[c.id].children)if(obj.isMesh){if(obj.userData.localMaterial)obj.material.dispose();obj.material=materials[c.material];obj.userData.localMaterial=false;}for(const k of Object.keys(overrides))delete overrides[k];selected=null;}
  function snapshot(){root.updateMatrixWorld(true);return {spec_sha256:data.spec_sha256,selected,variants:{...variants},materials:structuredClone(overrides),explode:explodeAmount,actions:Object.fromEntries(Object.entries(parts).map(([id,p])=>[id,p.value])),bounds:(()=>{const b=new THREE.Box3().setFromObject(root);return {min:b.min.toArray(),max:b.max.toArray()};})()};}
  const ready=Promise.all(pending);ready.catch(()=>{});
  const result={root,parts,materials,nodes,animate,setAction,setWheel,cameras:data.cameras||{},ready,getPart,select,describe,setMaterial,setColor,setVariant,replacePart:setVariant,explode,reset,snapshot,assetContract:data.asset_contract||null};
  root.userData.spec_sha256=data.spec_sha256;Object.defineProperty(root,'modelRuntime',{value:result});return result;
}
export function buildModel(){return buildScene().root;}
export function buildVehicle(){
  const bindings=data.vehicle_bindings;if(!bindings)throw new Error('Vehicle bindings required');
  const scene=buildScene();
  const paint={color:{set(value){for(const id of bindings.paint)scene.materials[id].color.set(value);return this;}}};
  // The locked viewer may receive its first RAF timestamp just before its
  // initialization performance.now(). Treat that finite negative delta as zero.
  function animate(dt){if(!Number.isFinite(dt))throw new Error('Invalid timestep');scene.animate(Math.max(0,dt));}
  return {...scene,paint,lights:bindings.lights.map(id=>scene.materials[id]),animate};
}
