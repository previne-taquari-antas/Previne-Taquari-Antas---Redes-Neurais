'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..');
(async()=>{
 for(const city of ['santa_tereza','mucum'])for(const variant of ['', '_usuario']){
  const html=fs.readFileSync(path.join(root,city+'_previsao_inundacao'+variant+'.html'),'utf8');
  const code=html.slice(html.indexOf('let liveEntering=false;'),html.indexOf('function exitLive(){'));
  const nodes=new Map();let retry,attempts=0,rendered=0,recovered=0,intervals=0;
  const ctx={window:{PREVINE_PUBLIC:{failed:()=>{},recovered:()=>recovered++}},document:{getElementById:id=>{if(!nodes.has(id))nodes.set(id,{style:{},setAttribute(){}});return nodes.get(id)},body:{classList:{add(){}}}},
   fetchLiveJson:async()=>{if(++attempts===1)throw Error('network');return {modo:'ao_vivo',gerado_em:new Date().toISOString()};},
   setTimeout:(fn,delay)=>{assert.equal(delay,5000);retry=fn;return 1;},clearTimeout(){},setInterval:()=>++intervals,clearInterval(){},liveTimer:null,liveMode:false,liveData:null,playing:false,liveIdx:0,
   prepareLiveData(){},updateTelemetryMarkers(){},activeLiveData(){return null},semHorizontes:()=>true,liveNowCm:()=>200,renderLiveStep:()=>rendered++};
  vm.createContext(ctx);vm.runInContext(code,ctx);await ctx.enterLive();assert.equal(attempts,1);assert.equal(typeof retry,'function');assert.equal(intervals,0);
  await retry();assert.equal(attempts,2);assert.equal(recovered,1);assert.equal(rendered,1);assert.equal(intervals,1);assert.equal(ctx.liveMode,true);
 }
 const modulePath=require.resolve('../assets/js/live_feed.js');delete require.cache[modulePath];const feed=require(modulePath);
 const now=new Date(),old=new Date(Date.now()-86400000);let apiCalls=0;
 const originalFetch=global.fetch;
 global.fetch=async url=>({ok:true,status:200,json:async()=>{
  if(url.includes('api.github')){apiCalls++;return {content:Buffer.from(JSON.stringify({consultado_em:now.toISOString()})).toString('base64')};}
  return {consultado_em:old.toISOString()};
 }});
 const result=await feed.fetchLive('previsao_ao_vivo.json');assert.equal(result.consultado_em,now.toISOString());assert.equal(apiCalls,1);
 await feed.fetchLive('previsao_ao_vivo.json');assert.equal(apiCalls,1,'stale CDN must not cause API request storm');
 assert.equal(feed.pickNewest([{},[],{consultado_em:'invalid'}]),null);
 assert.equal(feed.needsRefresh({consultado_em:now.toISOString(),telemetria_ultima_em:old.toISOString()}),true,'new publication does not make old telemetry current');
 global.fetch=originalFetch;
 const runtime=require('../assets/js/site_runtime.js');let handler;const primary={on:(event,fn)=>handler=fn,off(){}};const fallback={addTo:m=>m.layers.add(fallback)};
 const map={layers:new Set([primary]),hasLayer(layer){return this.layers.has(layer)},removeLayer(layer){this.layers.delete(layer)},on(){}};
 runtime.installTileFallback(map,primary,fallback);handler();assert.ok(map.hasLayer(primary));handler();handler();assert.ok(map.hasLayer(fallback));assert.ok(!map.hasLayer(primary));
 global.fetch=async(url,options)=>({ok:true,status:200,text:()=>new Promise((resolve,reject)=>{options.signal.addEventListener('abort',()=>reject(Error('aborted')));})});
 await assert.rejects(runtime.fetchResource('slow',{timeoutMs:20}),/aborted/);global.fetch=originalFetch;
 console.log('OK: retry→success on four pages; stale HTTP 200→fresh API; cooldown; invalid JSON schema; stale telemetry; satellite fallback; body timeout');
})().catch(error=>{console.error(error);process.exitCode=1;});
