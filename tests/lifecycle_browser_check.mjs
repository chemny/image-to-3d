// Explicit configured browser harness. No installs or production project paths.
import {createRequire} from 'node:module';
const [playwrightPath, browserPath, url, mode] = process.argv.slice(2);
const {chromium} = createRequire(import.meta.url)(playwrightPath);
const browser = await chromium.launch({executablePath:browserPath,headless:true});
try {
  const page=await browser.newPage(),requests=[],errors=[];
  page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));
  const response=await page.goto(url,{waitUntil:'networkidle'});
  if(response.status()!==200||errors.length)throw Error('page failed: '+JSON.stringify(errors));
  if(mode==='retired') {
    if(await page.locator('body').getAttribute('data-retired')!=='true')throw Error('missing retirement notice');
    if(requests.some(u=>u.endsWith('/model.bin')))throw Error('retired page still loads payload');
    if(await page.locator('a').getAttribute('href')!=='/active/')throw Error('wrong current link');
  } else {
    if(!await page.evaluate(()=>window.modelLoaded===true))throw Error('original entry did not load its model');
    if(!requests.some(u=>u.endsWith('/model.bin')))throw Error('original request not restored');
  }
  process.stdout.write(JSON.stringify({mode,passed:true,requests,errors}));
} finally {await browser.close()}
