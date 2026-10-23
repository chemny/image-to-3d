#!/usr/bin/env node
// Focused browser regressions: async import cancellation and remembered interiors.
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,x,i,all)=>{if(x.startsWith('--'))a.push([x.slice(2),all[i+1]]);return a;},[]));
if(!args.url||!args.out||!process.env.PLAYWRIGHT_MODULE)throw Error('Use --url URL --out NEW_DIR and PLAYWRIGHT_MODULE; optional --chrome');
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);const browser=await chromium.launch({headless:true,...(args.chrome?{executablePath:args.chrome}:{})});const out=path.resolve(args.out);await fs.mkdir(out);const rows=[];
const ready=page=>page.waitForFunction(()=>window.vehicleConfigurator?.getState().ready);const get=p=>p.evaluate(()=>vehicleConfigurator.exportSelection());
try{
 const context=await browser.newContext(),page=await context.newPage();await page.goto(args.url);await ready(page);const c=await (await page.request.get(new URL('config.json',args.url).href)).json();if(c.interiors.length<2)throw Error('Regression fixture requires at least two interior IDs');
 const saved=await get(page);saved.interior_id=c.interiors.at(-1).id;await page.evaluate(v=>vehicleConfigurator.importSelection(v),saved);await page.locator('#interior').click();await page.waitForFunction(id=>vehicleConfigurator.getState().interior_id===id,saved.interior_id);assert.equal((await get(page)).interior_id,saved.interior_id);assert(await page.locator(`#interiors button[data-id="${saved.interior_id}"]`).getAttribute('aria-pressed')==='true');rows.push({name:'Exterior saved selection remembers interior ID and active choice',verdict:'passed'});
 // Test a below-floor camera is rejected without OrbitControls silently clamping it.
 const prior=await get(page);const invalid=structuredClone(prior);invalid.camera.position[1]=invalid.camera.target[1]-2;const error=await page.evaluate(async v=>{try{await vehicleConfigurator.importSelection(v);return null;}catch(e){return e.message;}},invalid);assert(error?.includes('观察角度'));assert.deepEqual(await get(page),prior);rows.push({name:'Out-of-orbit-angle camera rejected atomically',verdict:'passed'});await context.close();
 for(const action of ['newer-import','newer-scene-click']){
  const ctx=await browser.newContext(),q=await ctx.newPage();let release;const gate=new Promise(r=>release=r);const imageURL=new URL(c.interiors[0].panorama,args.url).href;await q.route(imageURL,async route=>{await gate;await route.continue();});await q.goto(args.url);await ready(q);
  const base=await get(q),slow=structuredClone(base);slow.mode='interior';slow.interior_id=c.interiors[0].id;if(c.paints.length)slow.paint_id=c.paints[0].id;
  const request=q.waitForRequest(imageURL);await q.evaluate(v=>{window.slowImport=vehicleConfigurator.importSelection(v).then(()=>({ok:true})).catch(e=>({ok:false,error:e.message}));},slow);await request;
  let expected;
  if(action==='newer-import'){const next=structuredClone(base);next.scene_id=c.scenes.at(-1).id;if(c.paints.length)next.paint_id=c.paints.at(-1).id;await q.evaluate(v=>vehicleConfigurator.importSelection(v),next);expected=await get(q);}
  else{await q.locator('#scenes button').last().click();expected=await get(q);}
  release();const result=await q.evaluate(()=>window.slowImport);assert(!result.ok&&result.error.includes('替代'));assert.deepEqual(await get(q),expected);rows.push({name:action+' cancels delayed panorama import before mutations',verdict:'passed'});await ctx.close();
 }
 // Cross-viewport import preserves the selected IDs and target, adjusts distance for aspect.
 const ctx=await browser.newContext({viewport:{width:1280,height:900}}),q=await ctx.newPage();await q.goto(args.url);await ready(q);const old=await get(q);await q.setViewportSize({width:390,height:844});await q.waitForTimeout(200);const restored=await q.evaluate(v=>vehicleConfigurator.importSelection(v),old);assert.equal(restored.scene_id,old.scene_id);assert.equal(restored.view_id,old.view_id);assert.deepEqual(restored.camera.target,old.camera.target);assert.notEqual(restored.camera.aspect,old.camera.aspect);await q.screenshot({path:path.join(out,'cross-viewport.png'),fullPage:true});rows.push({name:'Cross-viewport selection import keeps options and target',verdict:'passed'});await ctx.close();
}catch(e){rows.push({name:'failure',verdict:'failed',error:e.stack});process.exitCode=1;}
finally{await browser.close();await fs.writeFile(path.join(out,'recovery-validation.json'),JSON.stringify({verdict:process.exitCode?'failed':'passed',checks:rows},null,2));console.log(JSON.stringify(rows));}
