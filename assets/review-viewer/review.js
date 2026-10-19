import * as T from 'three';
let buildScene,sceneMetadata;
try{({buildScene,sceneMetadata}=await import('./model.js'));}catch(error){document.querySelector('#status').textContent='模型加载失败：'+error.message;throw error;}
const config=await fetch('./capture-config.json').then(r=>{if(!r.ok)throw Error('Missing capture config');return r.json()});
const model=buildScene(),canvas=document.querySelector('canvas');await model.ready;
const renderer=new T.WebGLRenderer({canvas,antialias:false,preserveDrawingBuffer:true});renderer.setPixelRatio(1);
const scene=new T.Scene();scene.add(model.root);scene.add(new T.HemisphereLight(0xffffff,0x555555,2));const light=new T.DirectionalLight(0xffffff,3);light.position.set(4,7,5);scene.add(light);
const gray=new T.MeshStandardMaterial({color:0x999999,roughness:.8,side:T.FrontSide});const mask=new T.MeshBasicMaterial({color:0xffffff,side:T.DoubleSide});
// Internal capture-only diagnostics; no product/menu controls are added.
const grazing=new T.MeshStandardMaterial({color:0x999999,roughness:.2,metalness:.15});
const zebra=new T.ShaderMaterial({vertexShader:`varying vec3 wp;varying vec3 wn;void main(){vec4 p=modelMatrix*vec4(position,1.);wp=p.xyz;wn=mat3(modelMatrix)*normal;gl_Position=projectionMatrix*viewMatrix*p;}`,
 fragmentShader:`varying vec3 wp;varying vec3 wn;void main(){vec3 r=reflect(normalize(wp-cameraPosition),normalize(wn));float phase=23.*atan(r.x,r.z)+7.*r.y;float v=sin(phase);float w=clamp(fwidth(phase)*.45,.015,.8);float band=smoothstep(-w,w,v);gl_FragColor=vec4(mix(vec3(.1),vec3(.93),band),1.);}`});
const originals=new Map();model.root.traverse(o=>{if(o.isMesh)originals.set(o,o.material)});
let camera,currentView,currentMode,currentPose;
function select(view,mode='beauty',pose='closed'){
 const c=config.cameras[view];if(!c)throw Error('Unknown camera '+view);if(!['beauty','gray','mask','zebra','grazing'].includes(mode)||!['closed','half','open'].includes(pose))throw Error('Invalid capture state');
 renderer.setSize(c.width,c.height,false);const aspect=c.width/c.height;
 camera=c.type==='orthographic'?new T.OrthographicCamera(-c.ortho_height*aspect/2,c.ortho_height*aspect/2,c.ortho_height/2,-c.ortho_height/2,c.near??.01,c.far??1000):new T.PerspectiveCamera(c.fov_y_deg,aspect,c.near??.01,c.far??1000);
 camera.position.fromArray(c.position);camera.up.fromArray(c.up??[0,1,0]);camera.lookAt(new T.Vector3(...c.target));camera.updateMatrixWorld();camera.updateProjectionMatrix();
 const amount={closed:0,half:.5,open:1}[pose];for(const id of Object.keys(model.parts??{}))model.setAction(id,amount,{immediate:true});
 originals.forEach((m,o)=>{o.material=mode==='gray'?gray:mode==='mask'?mask:mode==='zebra'?zebra:mode==='grazing'?grazing:m});
 scene.children.filter(o=>o.isHemisphereLight).forEach(o=>o.intensity=mode==='grazing'?.18:2);
 light.intensity=mode==='grazing'?4:3;light.position.set(...(mode==='grazing'?[-8,1.2,3]:[4,7,5]));
 renderer.toneMapping=['mask','zebra'].includes(mode)?T.NoToneMapping:T.ACESFilmicToneMapping;renderer.toneMappingExposure=1;scene.background=new T.Color(mode==='mask'?0x000000:0xeeeeee);
 model.root.updateMatrixWorld(true);renderer.render(scene,camera);currentView=view;currentMode=mode;currentPose=pose;
 document.querySelector('#status').textContent=`${view} · ${mode} · ${pose} · ${c.width} × ${c.height}`;
}
function capture(view,mode,pose){select(view,mode,pose);const connections=(config.connections??[]).filter(c=>!c.poses||c.poses.includes(pose)).map(c=>{const point=a=>model.nodes[a.component_id].localToWorld(new T.Vector3(...a.local_point));const distance=point(c.a).distanceTo(point(c.b));return{id:c.id,distance,max_distance:c.max_distance,passed:distance<=c.max_distance+1e-9}});return{connections,png:canvas.toDataURL('image/png'),view,mode,pose,width:canvas.width,height:canvas.height,landmarks:(config.landmarks??[]).map(p=>{const q=new T.Vector3(...p.world).project(camera);return{id:p.id,pixel:[(q.x+1)*canvas.width/2,(1-q.y)*canvas.height/2]}}),calls:renderer.info.render.calls,triangles:renderer.info.render.triangles};}
for(const id of Object.keys(config.cameras)){const option=document.createElement('option');option.value=id;option.textContent=id;document.querySelector('#view').append(option)}
for(const id of ['view','mode','pose'])document.querySelector('#'+id).onchange=()=>select(document.querySelector('#view').value,document.querySelector('#mode').value,document.querySelector('#pose').value);
const partSelect=document.querySelector('#part');
for(const [id,node] of Object.entries(model.nodes)){if(node.userData.kind==='assembly'||node.userData.kind==='part'){const option=document.createElement('option');option.value=id;option.textContent=id;partSelect.append(option);}}
const render=()=>{model.root.updateMatrixWorld(true);renderer.render(scene,camera)};
function beauty(){document.querySelector('#mode').value='beauty';select(currentView,'beauty',currentPose);}
partSelect.onchange=()=>{try{model.select(partSelect.value);document.querySelector('#status').textContent=JSON.stringify(model.describe(partSelect.value));}catch(e){document.querySelector('#status').textContent=e.message;}};
document.querySelector('#apply-color').onclick=()=>{try{beauty();model.setColor(partSelect.value,document.querySelector('#part-color').value);for(const o of model.nodes[partSelect.value].children)if(o.isMesh)originals.set(o,o.material);render();}catch(e){document.querySelector('#status').textContent=e.message;}};
document.querySelector('#explode').oninput=e=>{model.explode(Number(e.target.value));render();};
const payload=sceneMetadata??await fetch('./scene.json').then(r=>r.json());
for(const variant of payload.variants||[]){const label=document.createElement('label');label.textContent=variant.id+' ';const select=document.createElement('select');select.dataset.variant=variant.id;for(const name of Object.keys(variant.options)){const option=document.createElement('option');option.value=option.textContent=name;select.append(option);}select.value=variant.default;select.onchange=()=>{model.setVariant(variant.id,select.value);render();};label.append(select);document.querySelector('#variants').append(label);}
document.querySelector('#asset-reset').onclick=()=>{model.reset();model.root.traverse(o=>{if(o.isMesh)originals.set(o,o.material)});document.querySelector('#explode').value=0;for(const v of payload.variants||[])[...document.querySelectorAll('[data-variant]')].find(el=>el.dataset.variant===v.id).value=v.default;document.querySelector('#pose').value='closed';select(currentView,'beauty','closed');};
canvas.addEventListener('click',event=>{const rect=canvas.getBoundingClientRect();const ray=new T.Raycaster();ray.setFromCamera(new T.Vector2(2*(event.clientX-rect.left)/rect.width-1,1-2*(event.clientY-rect.top)/rect.height),camera);const hit=ray.intersectObject(model.root).find(h=>{let p=h.object;while(p){if(!p.visible)return false;p=p.parent;}return true;});if(hit){const id=model.getPart(hit.object);if(id){partSelect.value=id;partSelect.onchange();}}});
window.modelReview={ready:true,select,capture,model,renderer,scene,get camera(){return camera},config};select(Object.keys(config.cameras)[0]);
