// Portable saved selections contain no credentials or asset bytes.
export function normalizeConfig(c) {
  const v={...c};v.schema_version??=1;v.paintTargets??=[];v.paintMaterials??=[];
  for(const key of ['paints','rims','interiors'])v[key]=(v[key]||[]).map((x,i)=>({...x,id:x.id||`${key}-${i}`}));
  v.doors??=[];v.runtimeDependencies??=[];v.referenceGallery??=[];
  if(!Array.isArray(v.referenceGallery)||v.referenceGallery.some(x=>typeof x.image!=='string'||!/^\.\/[^?#]+\.(png|jpe?g)$/i.test(x.image)||x.image.includes('..')||typeof x.label!=='string'))throw Error('参考图库配置无效');
  v.scenes??=[{id:'studio',label:'柔光展厅',background:'#e4e1db',floor:'#d6d2c9',exposure:1},{id:'cool',label:'冷色展厅',background:'#dbe3e8',floor:'#c0cbd1',exposure:.9}];
  v.views??=[{id:'quarter',label:'斜前',direction:[1.2,.45,1.8]},{id:'front',label:'前',direction:[0,.2,1]},{id:'rear',label:'后',direction:[0,.2,-1]},{id:'left',label:'左侧',direction:[1,.2,0]},{id:'right',label:'右侧',direction:[-1,.2,0]}];
  if(!v.asset?.id||!v.asset?.version)throw Error('配置缺少资产身份和版本，请用 project.py web 创建资源包');
  for(const key of ['paints','rims','interiors','scenes','views']){
    const ids=v[key].map(x=>x.id);if(ids.some(x=>typeof x!=='string'||!x)||new Set(ids).size!==ids.length)throw Error('选项 ID 无效或重复：'+key);
  }
  if(v.originalPaintId!==undefined&&!v.paints.some(x=>x.id===v.originalPaintId))throw Error('原材质展示 ID 无效');
  if(!v.scenes.length||!v.views.length)throw Error('场景和视角不能为空');
  for(const x of v.paints)if(!/^#[0-9a-f]{6}$/i.test(x.color))throw Error('车漆颜色格式错误');
  for(const x of v.views)if(!vector(x.direction)||Math.hypot(...x.direction)===0)throw Error('视角方向无效');
  for(const x of v.scenes)if(!/^#[0-9a-f]{6}$/i.test(x.background)||!/^#[0-9a-f]{6}$/i.test(x.floor)||!Number.isFinite(x.exposure)||x.exposure<=0||x.exposure>5)throw Error('场景设置无效');
  for(const x of v.scenes){for(const key of ['hemi','keyPower'])if(x[key]!==undefined&&(!Number.isFinite(x[key])||x[key]<0||x[key]>20))throw Error('灯光强度无效');for(const key of ['keyColor','fillColor'])if(x[key]!==undefined&&!/^#[0-9a-f]{6}$/i.test(x[key]))throw Error('灯光颜色无效');}
  if(new Set(v.doors.map(d=>d.node)).size!==v.doors.length)throw Error('重复门轴绑定');
  const rimNodes=v.rims.flatMap(r=>r.nodes||[]);if(new Set(rimNodes).size!==rimNodes.length)throw Error('轮毂组选项重复绑定节点');
  return v;
}
function vector(v){return Array.isArray(v)&&v.length===3&&v.every(x=>typeof x==='number'&&Number.isFinite(x)&&Math.abs(x)<=1e7);}
export function validateSelection(input,c,capabilities) {
  if(!input||input.schema_version!==2)throw Error('不支持的配置版本；旧的无版本导出需人工迁移');
  if(input.asset?.id!==c.asset.id||input.asset?.version!==c.asset.version||input.asset?.config_version!==c.asset.config_version)throw Error('配置属于其他模型或资产版本');
  const option=(key,id,nullable=false)=>{if(id===null&&nullable)return;if(typeof id!=='string'||!c[key].some(x=>x.id===id))throw Error('不支持的选项：'+key);};
  option('paints',input.paint_id,true);if(input.paint_id!==null&&!capabilities.paint)throw Error('当前资产未启用换色');
  option('scenes',input.scene_id);option('views',input.view_id);
  option('rims',input.rim_id,true);if(c.rims.length&&input.rim_id===null)throw Error('缺少轮毂选项');
  option('interiors',input.interior_id,true);
  if(!['exterior','interior'].includes(input.mode)||input.mode==='interior'&&input.interior_id===null)throw Error('显示模式无效');
  const doors=input.doors;if(!doors||typeof doors!=='object'||Array.isArray(doors))throw Error('车门配置无效');
  if(Object.keys(doors).length!==c.doors.length||c.doors.some(d=>typeof doors[d.node]!=='boolean'))throw Error('车门选项不兼容');
  if(!input.camera||!vector(input.camera.position)||!vector(input.camera.target)||Math.hypot(...input.camera.position.map((x,i)=>x-input.camera.target[i]))<1e-6)throw Error('相机状态无效');
  if(!Number.isFinite(input.camera.aspect)||input.camera.aspect<=0||input.camera.aspect>100)throw Error('相机视口无效');
  if(typeof input.auto_rotate!=='boolean'||!Number.isFinite(input.panorama?.yaw)||!Number.isFinite(input.panorama?.pitch)||Math.abs(input.panorama.pitch)>1.4)throw Error('环绕或全景状态无效');
  if(input.mode==='interior'&&input.auto_rotate)throw Error('内饰模式不能自动环绕');
  return JSON.parse(JSON.stringify({schema_version:2,asset:c.asset,paint_id:input.paint_id,scene_id:input.scene_id,view_id:input.view_id,rim_id:input.rim_id,interior_id:input.interior_id,mode:input.mode,doors,camera:input.camera,auto_rotate:input.auto_rotate,panorama:input.panorama}));
}
