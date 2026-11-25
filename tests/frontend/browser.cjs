/* Deterministic interaction tests: data snapshots are fixtures, not live validation. */
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright':'playwright');
const root=path.resolve(process.env.SITE_ROOT||path.join(__dirname,'../..'));
const leaflet=process.env.LEAFLET_DIR||path.join(__dirname,'node_modules/leaflet/dist');
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'};
const server=http.createServer((req,res)=>{const file=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0]));if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.statusCode=404;return res.end();}res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});const results=[];
try{for(const width of [390,1440])for(const city of ['santa_tereza','mucum'])for(const variant of ['','_usuario']){
 const page=await browser.newPage({viewport:{width,height:900},hasTouch:width===390});const errors=[];page.on('pageerror',e=>errors.push(e.message));let online=false;
 await page.route('**/*',async route=>{const u=route.request().url();if(u.includes('/leaflet.js'))return route.fulfill({path:path.join(leaflet,'leaflet.js'),contentType:'text/javascript'});if(u.includes('/leaflet.css'))return route.fulfill({path:path.join(leaflet,'leaflet.css'),contentType:'text/css'});
 if(/previsao_ao_vivo(?:_mucum)?\.json/.test(u)){if(!online)return route.abort();const name=city==='mucum'?'previsao_ao_vivo_mucum.json':'previsao_ao_vivo.json';const data=JSON.parse(fs.readFileSync(path.join(__dirname,name)));data.consultado_em=new Date().toISOString();return route.fulfill({json:data});}
 if(/contornos.*\.json/.test(u))return route.fulfill({json:{type:'FeatureCollection',features:[]}});
 if(u.startsWith(origin))return route.continue();return route.abort();});
 console.log('START',width,city,variant); const start=Date.now();await page.goto(origin+'/'+city+'_previsao_inundacao'+variant+'.html');await page.waitForFunction(()=>typeof liveRetryDelay!=='undefined'&&liveRetryDelay>5000,{timeout:20000});online=true;await page.waitForFunction(()=>typeof liveMode!=='undefined'&&liveMode,{timeout:20000});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false,'page overflow');
 // Native input events share the same binding as touch and keyboard manipulation.
 const control=page.locator('#bankfull');await control.evaluate(e=>{e.value='250';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));});
 assert.equal(await page.evaluate(()=>bankfull),250);assert.equal(await control.getAttribute('aria-valuetext'),'2,5 m');
 for(const view of ['selected','both']){const button=page.locator('[data-city-view="'+view+'"]');if(width===390)await button.tap();else await button.click();}
 const link=page.locator('[data-forecast-city-link]').filter({hasText:city==='mucum'?'Santa Tereza':'Muçum'});if(await link.count())assert.ok((await link.first().getAttribute('href')).includes(variant+'.html'));
 assert.deepEqual(errors,[]);results.push({page:city+variant,width,readyMs:Date.now()-start,heapBytes:await page.evaluate(()=>performance.memory?.usedJSHeapSize||null)});await page.close();
}
for(const city of ['santa_tereza','mucum']){
 const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=route.request().url();if(u.includes('/leaflet.js'))return route.fulfill({path:path.join(leaflet,'leaflet.js'),contentType:'text/javascript'});if(u.includes('/leaflet.css'))return route.fulfill({path:path.join(leaflet,'leaflet.css'),contentType:'text/css'});if(u.includes('contornos_previa_visual_leve.json'))return route.fulfill({json:{type:'FeatureCollection',metadata:{status:'previa_visual_legada_nao_validada',preview_only:true,usable_for_building_risk:false,backwater_hydrodynamic_calibration:false},features:[{type:'Feature',properties:{nivel_m:10},geometry:{type:'Polygon',coordinates:[[[-51.75,-29.19],[-51.70,-29.19],[-51.70,-29.15],[-51.75,-29.19]]]}}]}});if(u.startsWith(origin))return route.continue();return route.abort();});
 await page.goto(origin+'/'+city+'_painel_evacuacao.html');
 const slider=page.locator(city==='santa_tereza'?'#quickSld':'#sld');
 await slider.scrollIntoViewIfNeeded();const box=await slider.boundingBox();assert.ok(box&&box.width>80,'touch slider reachable');
 const before=Number(await slider.inputValue());await page.touchscreen.tap(box.x+box.width*.65,box.y+box.height/2);await page.waitForTimeout(100);
 assert.notEqual(Number(await slider.inputValue()),before,'native touch changes ruler');
 if(city==='santa_tereza') {await page.locator('#quickPlay').tap();const level=Number(await slider.inputValue());await page.waitForTimeout(800);assert.notEqual(Number(await slider.inputValue()),level,'animation advances water level');await page.locator('#quickPlay').tap();}
 assert.deepEqual(errors,[]);results.push({page:city+'_painel_evacuacao',width:390,touch:true});await page.close();
}
fs.writeFileSync(process.env.BROWSER_REPORT||'/tmp/previne-browser-report.json',JSON.stringify(results,null,2));console.log('PASS',results.length,'forecast scenarios: mobile/desktop, offline recovery, range binding, city controls and JS errors');
}finally{await browser.close();server.close();}})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
