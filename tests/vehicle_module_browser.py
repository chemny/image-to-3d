"""Explicit browser integration using relocated Skill and temporary synthetic assets."""
import argparse
import functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
from pathlib import Path
import subprocess
import threading
from test_vehicle_module import VehicleModuleTests


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['node','playwright','browser','out']:p.add_argument('--'+key,required=True)
    a=p.parse_args();out=Path(a.out).resolve()
    if out.exists():p.error('output exists; choose a new evidence file')
    VehicleModuleTests.setUpClass();test=VehicleModuleTests();server=None
    try:
        work=test.build_fixture('browser-fixture')
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        handler=functools.partial(Quiet,directory=str(work/'web'))
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url='http://127.0.0.1:'+str(server.server_port)+'/'
        code=r'''
const{chromium}=require(process.argv[1]),assert=require('assert');
(async()=>{const b=await chromium.launch({executablePath:process.argv[2],headless:true});try{
 const p=await b.newPage({viewport:{width:1500,height:960}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(process.argv[3]);await p.waitForFunction(()=>window.review&&document.querySelector('#loading').hidden);
 assert.equal(await p.locator('#paints button').count(),6);assert.equal(await p.locator('#wheels button').count(),3);
 for(let i=0;i<6;i++){await p.locator('#paints button').nth(i).click();assert.equal(await p.evaluate(()=>review.getState().paint),i);}
 for(let i=0;i<3;i++){await p.locator('#wheels button').nth(i).click();assert.equal(await p.evaluate(()=>review.getState().rim),i);await p.locator('#backgrounds button').nth(i).click();assert.equal(await p.evaluate(()=>review.getState().scene),i);}
 for(let i=0;i<4;i++){await p.locator('#actions button').nth(i).click();const on=await p.evaluate(()=>review.getState().parts);assert(Object.values(on).some(x=>x===1));await p.locator('#actions button').nth(i).click();assert(Object.values(await p.evaluate(()=>review.getState().parts)).every(x=>x===0));}
 const saved=await p.evaluate(()=>review.getState());await p.locator('#paints button').nth(0).click();await p.evaluate(s=>review.restore(s),saved);assert.equal(await p.evaluate(()=>review.getState().paint),saved.paint);
 await p.locator('#references').click();assert(await p.locator('dialog').evaluate(x=>x.open));await p.locator('#reference-image').evaluate(x=>x.decode());await p.locator('#close-reference').click();
 const calls=await p.evaluate(()=>{review.renderer.render(review.scene,review.camera);return review.renderer.info.render.calls});assert(calls>0);
 await p.setViewportSize({width:390,height:844});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,syntheticOnly:true,relocatedModule:true,paints:6,wheels:3,scenes:3,actionGroups:4,restore:true,references:true,mobile:true,webglDrawCalls:calls,errors}));
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
'''
        result=subprocess.run([a.node,'-e',code,a.playwright,a.browser,url],check=True,capture_output=True,text=True)
        report=json.loads(result.stdout);out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
        print(json.dumps(report,ensure_ascii=False))
    finally:
        if server:server.shutdown();server.server_close()
        VehicleModuleTests.tmp.cleanup()


if __name__=='__main__':main()
