// Local QA capture, no package installation, no external sites.
import fs from 'node:fs';import path from 'node:path';import http from 'node:http';import crypto from 'node:crypto';import {pathToFileURL} from 'node:url';
const a=Object.fromEntries(process.argv.slice(2).reduce((r,v,i,all)=>{if(v.startsWith('--'))r.push([v.slice(2),all[i+1]]);return r},[]));
if(!a.bundle||!a.out||!a['playwright-module'])throw Error('--bundle --out --playwright-module required; optional --browser --poses closed,half,open');
const root=fs.realpathSync(a.bundle),out=path.resolve(a.out);if(fs.existsSync(out))throw Error('Capture output exists');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'bundle-manifest.json')));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function integrity(){for(const[n,h]of Object.entries(manifest.files)){const f=fs.realpathSync(path.join(root,n));if(!f.startsWith(root+path.sep)||sha(fs.readFileSync(f))!==h)throw Error('Stale bundle: '+n)}}integrity();
const server=http.createServer((req,res)=>{try{const n=decodeURIComponent(new URL(req.url,'http://localhost').pathname);const f=fs.realpathSync(path.join(root,n==='/'?'index.html':n));if(!f.startsWith(root+path.sep)){res.writeHead(403).end();return}res.setHeader('Content-Type',({'.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.html':'text/html','.png':'image/png','.css':'text/css'})[path.extname(f)]??'application/octet-stream');res.end(fs.readFileSync(f))}catch{res.writeHead(404).end()}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{
 const {chromium}=await import(pathToFileURL(path.resolve(a['playwright-module'])).href);browser=await chromium.launch({headless:true,...(a.browser?{executablePath:a.browser}:{}),args:['--enable-unsafe-swiftshader']});
 const p=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],requests=[];p.on('response',r=>requests.push({path:new URL(r.url()).pathname,bytes:Number(r.headers()['content-length'])||null}));p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`)});
 await p.goto(`http://127.0.0.1:${server.address().port}/`,{waitUntil:'networkidle'});await p.waitForFunction(()=>window.modelReview?.ready,{timeout:30000});
 const result=await p.evaluate(async()=>{
 const m=modelReview.model,d=(await import('./model.js')).sceneMetadata??await fetch('./scene.json').then(r=>r.json()),checks=[],errors=[];
 const check=(name,fn)=>{try{fn();checks.push({name,passed:true})}catch(e){checks.push({name,passed:false,error:e.message});errors.push(name+': '+e.message)}};
 const assert=(v,msg)=>{if(!v)throw Error(msg)};
 await m.ready;m.reset();m.root.updateMatrixWorld(true);
 const matrix=()=>Object.fromEntries(Object.entries(m.nodes).map(([id,n])=>[id,[...n.matrixWorld.elements]]));const baseline=matrix();
 for(const c of d.components){
  check('component:'+c.id,()=>assert(m.nodes[c.id]&&m.nodes[c.id].name===c.id,'missing identity'));
  if(c.selectable!==false)check('select:'+c.id,()=>assert(m.select(c.id).id===c.id,'selection failed'));
  if(c.mesh_count??c.meshes?.length){check('material-isolation:'+c.id,()=>{const before=Object.fromEntries(Object.entries(m.materials).map(([id,x])=>[id,x.color.getHex()]));m.setColor(c.id,'#123456');assert(m.nodes[c.id].children.filter(x=>x.isMesh).every(x=>x.material.color.getHex()===0x123456),'target not changed');assert(Object.entries(m.materials).every(([id,x])=>x.color.getHex()===before[id]),'shared material changed');m.reset();});
   for(const [slot,id] of Object.entries(c.material_slots||{}))check('material-slot:'+c.id+':'+slot,()=>{m.setMaterial(c.id,slot);assert(m.nodes[c.id].children.filter(x=>x.isMesh).every(x=>x.material===m.materials[id]),'wrong slot');m.reset();});
  }
 }
 for(const v of d.variants||[])for(const name of Object.keys(v.options))check('variant:'+v.id+':'+name,()=>{m.setVariant(v.id,name);for(const [opt,ids]of Object.entries(v.options))for(const id of ids)assert(m.nodes[id].visible===(opt===name),'wrong variant visibility');m.reset();});
 const movers=d.components.filter(c=>(c.explode_vector||[]).some(x=>x!==0));
 if(movers.length)check('explode-reset',()=>{m.explode(1);assert(movers.some(c=>m.nodes[c.id].matrixWorld.elements.some((x,i)=>Math.abs(x-baseline[c.id][i])>1e-7)),'no movement');m.reset();});
 for(const a of d.actions||[])check('action:'+a.id,()=>{m.setAction(a.id,.5,{immediate:true});assert(Math.abs(m.parts[a.id].group.rotation[a.axis]-a.angle*.5)<1e-7,'half pose');m.setAction(a.id,1,{immediate:true});assert(Math.abs(m.parts[a.id].group.rotation[a.axis]-a.angle)<1e-7,'open pose');m.reset();});
 check('world-transform-restored',()=>{m.root.updateMatrixWorld(true);const after=matrix();assert(Object.keys(baseline).every(id=>after[id].every((x,i)=>Math.abs(x-baseline[id][i])<1e-7)),'reset drift');});
 const performed={select:checks.some(c=>c.name.startsWith('select:')),material:checks.some(c=>c.name.startsWith('material-slot:')),variant:checks.some(c=>c.name.startsWith('variant:')),explode:checks.some(c=>c.name==='explode-reset'),action:checks.some(c=>c.name.startsWith('action:'))};
 for(const op of d.asset_contract?.required_operations||[])check('required:'+op,()=>assert(performed[op],'operation untested'));
 return {passed:errors.length===0,checks,errors,performed,scope:'browser runtime behavior only',visual_acceptance:false,spec_sha256:d.spec_sha256};
 });
 if(manifest.delivery_layout){const layout=JSON.parse(fs.readFileSync(path.join(root,manifest.delivery_layout)));const full=requests.filter(r=>r.path==='/'+layout.data.path).length;const duplicates=requests.filter(r=>r.path==='/scene.json'||r.path==='/engineering/scene.json');result.delivery_network={storage:layout.storage,full_geometry_requests:full,requests,duplicate_geometry_requests:duplicates.length};if((layout.storage==='external'&&full!==1)||duplicates.length){result.passed=false;result.errors.push('Duplicate or missing geometry network load');}}
 fs.mkdirSync(out,{recursive:true});
 const screenshots=[];for(const [name,amount] of [['assembled',0],['exploded',1]]){await p.evaluate(amount=>{modelReview.model.explode(amount);modelReview.renderer.render(modelReview.scene,modelReview.camera)},amount);const f=name+'.png';await p.screenshot({path:path.join(out,f),fullPage:true});screenshots.push({file:f,sha256:sha(fs.readFileSync(path.join(out,f)))});}
 integrity();result.errors.push(...errors);result.passed&&=errors.length===0;result.bundle_manifest_sha256=sha(fs.readFileSync(path.join(root,'bundle-manifest.json')));result.screenshots=screenshots;
 fs.writeFileSync(path.join(out,'asset-report.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({passed:result.passed,checks:result.checks.length,errors:result.errors}));if(!result.passed)process.exitCode=2;
}finally{if(browser)await browser.close();server.close()}
