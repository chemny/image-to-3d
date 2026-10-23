#!/usr/bin/env node
// Actual browser/GPU behavior. Requires an existing Playwright installation; installs nothing.
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,x,i,all)=>{if(x.startsWith('--'))a.push([x.slice(2),all[i+1]]);return a;},[]));
if(!args.url||!args.out||!process.env.PLAYWRIGHT_MODULE)throw Error('Use --url http://127.0.0.1:PORT/path --out NEW_DIR and PLAYWRIGHT_MODULE=/existing/playwright/index.mjs; optional --chrome existing executable');
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);const out=path.resolve(args.out);await fs.mkdir(out,{recursive:false});
const report={schema_version:2,url:args.url,checks:[],errors:[],not_verified:['Physical mobile device performance','Real vehicle reconstruction fidelity','Interior panorama seam quality'],started_at:new Date().toISOString()};
const browser=await chromium.launch({headless:true,...(args.chrome?{executablePath:args.chrome}:{})});const context=await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:true});const page=await context.newPage();
page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))report.errors.push(m.text());});
const check=(name,evidence)=>report.checks.push({name,verdict:'passed',evidence});
const get=()=>page.evaluate(()=>vehicleConfigurator.exportSelection());
const ready=()=>page.waitForFunction(()=>window.vehicleConfigurator?.getState().ready,{},{timeout:90000});
const click=async s=>{await page.locator(s).click();await page.waitForTimeout(150);};
const near=(a,b)=>{assert.equal(a.length,b.length);a.forEach((v,i)=>assert(Math.abs(v-b[i])<1e-5,`Camera ${v} != ${b[i]}`));};
const compare=(a,b)=>{near(a.camera.position,b.camera.position);near(a.camera.target,b.camera.target);const x=structuredClone(a),y=structuredClone(b);delete x.camera;delete y.camera;assert.deepEqual(x,y);};
try{
 const t=Date.now();await page.goto(args.url);await ready();report.load_ms=Date.now()-t;check('Asset actually decoded/rendered',await page.evaluate(()=>vehicleConfigurator.performance()));
 const before=await page.evaluate(()=>vehicleConfigurator.inventory());await fs.writeFile(path.join(out,'materials-before.json'),JSON.stringify(before,null,2));
 assert(before.length>0);const paintIDs=before.filter(x=>x.paint).map(x=>x.id);
 const swatches=page.locator('#paints .swatch');const paintCount=await swatches.count();
 for(let i=0;i<paintCount;i++){
  await swatches.nth(i).click();await page.waitForTimeout(100);
  const after=await page.evaluate(()=>vehicleConfigurator.inventory());
  assert.deepEqual(after.filter(x=>!x.paint),before.filter(x=>!x.paint),'Fixed role material changed during paint');
  assert.deepEqual(after.map(x=>x.id),before.map(x=>x.id),'Feature bindings disappeared');
  if(i===paintCount-1)await page.screenshot({path:path.join(out,'paint.png')});
 }
 if(paintCount){const after=await page.evaluate(()=>vehicleConfigurator.inventory());assert(after.filter(x=>x.paint).some(x=>JSON.stringify(x.material)!==JSON.stringify(before.find(b=>b.id===x.id).material)),'Paint did not affect material');check('Every paint works; fixed materials and features preserved',{paint_count:paintCount,paint_ids:paintIDs,fixed_count:before.length-paintIDs.length});}
 else check('Paint controls hidden when no role binding',!(await page.locator('#paint-section').isVisible()));
 const views=await page.locator('#views button').count();for(let i=0;i<views;i++){await page.locator('#views button').nth(i).click();await page.waitForFunction(()=>!vehicleConfigurator.getState().view_transition);const v=await get();assert(v.camera.position.every(Number.isFinite));}check('All view presets',views);
 const scenes=await page.locator('#scenes button').count();for(let i=0;i<scenes;i++)await page.locator('#scenes button').nth(i).click();check('All scene presets',scenes);
 const rims=await page.locator('#rims button').count();for(let i=0;i<rims;i++){await page.locator('#rims button').nth(i).click();assert((await get()).rim_id!==null);}check('Available rim choices',rims);
 const doors=await page.locator('#doors button').count();for(let i=0;i<doors;i++)await page.locator('#doors button').nth(i).click();if(doors)assert(Object.values((await get()).doors).every(Boolean));check('Available door controls',doors);
 const interiors=await page.locator('#interiors button').count();for(let i=0;i<interiors;i++){await page.locator('#interiors button').nth(i).click();const expected=await page.locator('#interiors button').nth(i).getAttribute('data-id');await page.waitForFunction(id=>vehicleConfigurator.getState().interior_id===id,expected);assert.equal((await get()).mode,'interior');}check('Available interiors',interiors);
 // Mouse rotation and wheel zoom exercise OrbitControls on an exterior view.
 await click('#exterior');const canvas=page.locator('canvas'),box=await canvas.boundingBox();let camera=(await get()).camera.position;
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.6);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.6,{steps:10});await page.mouse.up();await page.waitForTimeout(900);assert.notDeepEqual((await get()).camera.position,camera);check('Drag rotates actual camera',true);
 camera=(await get()).camera.position;await page.mouse.wheel(0,-180);await page.waitForTimeout(900);assert.notDeepEqual((await get()).camera.position,camera);check('Wheel zoom changes actual camera',true);
 await click('#rotate');const rotateA=(await get()).camera.position;await page.waitForTimeout(800);assert.notDeepEqual((await get()).camera.position,rotateA);await click('#rotate');await page.waitForTimeout(900);check('360 auto orbit starts and stops',true);
 await click('#reset');await page.locator('#views button').last().click();await page.waitForFunction(()=>!vehicleConfigurator.getState().view_transition);
 if(interiors){await page.locator('#interiors button').last().click();await page.waitForFunction(()=>vehicleConfigurator.getState().view==='interior');}
 const download=page.waitForEvent('download');await click('#export');const file=await download;await file.saveAs(path.join(out,'vehicle-configuration.json'));const saved=JSON.parse(await fs.readFile(path.join(out,'vehicle-configuration.json'),'utf8'));compare(await get(),saved);check('Downloaded JSON is real current selection','vehicle-configuration.json');
 await click('#save');await click('#reset');await page.locator('#import-file').setInputFiles(path.join(out,'vehicle-configuration.json'));await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('JSON 配置已恢复'));compare(await get(),saved);check('Real file input restores downloaded JSON',true);
 await page.reload();await ready();compare(await get(),saved);check('Reload restores localStorage for exact asset version',true);
 await click('#reset');await click('#restore');await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('本地配置已恢复'));compare(await get(),saved);check('Explicit restore button',true);
 const invalids=[{...saved,schema_version:999},{...saved,asset:{...saved.asset,version:'other'}},{...saved,asset:{...saved.asset,config_version:'other-config'}},{...saved,scene_id:'missing'},{...saved,camera:{...saved.camera,position:[null,0,0]}},{...saved,doors:{rogue:true}}];
 for(const item of invalids){const previous=await get();const error=await page.evaluate(async v=>{try{await vehicleConfigurator.importSelection(v);return null;}catch(e){return e.message;}},item);assert(error);compare(await get(),previous);}check('Invalid schema/version/options/camera/doors rejected atomically',invalids.length);
 await page.locator('#import-file').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{broken')});await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('导入失败'));check('Malformed JSON explains failure',true);
 const pngEvent=page.waitForEvent('download');await click('#png');const png=await pngEvent;await png.saveAs(path.join(out,'vehicle-preview.png'));const bytes=await fs.readFile(path.join(out,'vehicle-preview.png'));assert.deepEqual([...bytes.subarray(0,8)],[137,80,78,71,13,10,26,10]);assert(bytes.length>5000);const nonblank=await page.evaluate(async encoded=>{const im=await createImageBitmap(await (await fetch('data:image/png;base64,'+encoded)).blob());const c=document.createElement('canvas');c.width=32;c.height=32;const ctx=c.getContext('2d');ctx.drawImage(im,0,0,32,32);const pixels=ctx.getImageData(0,0,32,32).data;return new Set(Array.from({length:1024},(_,i)=>[...pixels.slice(i*4,i*4+4)].join(','))).size>10;},bytes.toString('base64'));assert(nonblank,'PNG is blank');check('Actual PNG download',{bytes:bytes.length,width:bytes.readUInt32BE(16),height:bytes.readUInt32BE(20)});
 await click('#exterior');await click('#reset');await page.screenshot({path:path.join(out,'desktop.png')});
 report.render=await page.evaluate(()=>vehicleConfigurator.performance());report.frame_sample=await page.evaluate(async()=>{let start=performance.now(),frames=0;await new Promise(resolve=>{const step=()=>{if(++frames>=40)resolve();else requestAnimationFrame(step);};requestAnimationFrame(step);});return {frames,elapsed_ms:performance.now()-start};});
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);await click('#reset');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'narrow.png'),fullPage:true});check('390 x 844 layout without horizontal overflow','narrow.png; desktop simulation');
 await fs.writeFile(path.join(out,'materials-after.json'),JSON.stringify(await page.evaluate(()=>vehicleConfigurator.inventory()),null,2));
 assert.deepEqual(report.errors,[]);report.verdict='passed';
}catch(e){report.verdict='failed';report.failure=e.stack;process.exitCode=1;await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});}
finally{report.ended_at=new Date().toISOString();await fs.writeFile(path.join(out,'browser-validation.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({verdict:report.verdict,checks:report.checks.length,failure:report.failure,out}));}
