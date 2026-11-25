'use strict';
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
function node(){return {textContent:'',innerHTML:'',value:'4',style:{},children:[],events:{},attrs:{},appendChild(x){this.children.push(x);},addEventListener(k,v){this.events[k]=v;},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}};}
const nodes=new Map();const el=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
let ready,fail=false,invalid=false,requests=[];
const data={generated_at_utc:'2026-10-20T12:00:00Z',stations:{stz:{station_name:'Santa Tereza',coordinates:{latitude:-29,longitude:-51}},muc:{station_name:'Muçum',station_code:'86510000',coordinates:{latitude:-29.16,longitude:-51.86},live_horizons:[{model:'<img onerror=bad>',quality_status:'<b>test</b>',hours:4}]},bad:{coordinates:{latitude:'',longitude:0}},infinite:{coordinates:{latitude:Infinity,longitude:0}}}};
const context={console:{warn(){}},document:{getElementById:el,createElement:node,querySelector:()=>el('dot'),addEventListener:(type,fn)=>{if(type==='DOMContentLoaded')ready=fn;}},setTimeout,clearTimeout,AbortController,fetch:async url=>{
 requests.push(url);
 await new Promise(r=>setImmediate(r));
 if(fail||url.startsWith('https:'))throw new Error('network failure');
 const body=url.includes('research_basin')?(invalid?{stations:[]}:data):{};
 return {ok:true,status:200,text:async()=>JSON.stringify(body)};
}};
context.window=context;
// Keep toast timers out of the test's lifetime; fetch timeouts use real timers.
context.window.setTimeout=(fn,ms)=>{const timer=setTimeout(fn,ms);timer.unref();return timer;};
vm.createContext(context);
for(const file of ['site_runtime.js','ai_lab_brasil.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/js',file),'utf8'),context);
async function settled(){for(let i=0;i<100&&el('refresh-feed').disabled;i++)await new Promise(r=>setImmediate(r));assert.equal(el('refresh-feed').disabled,false);}
(async()=>{
 ready();assert.equal(el('refresh-feed').disabled,true);
 el('refresh-feed').events.click();await settled();
 assert.equal(requests.filter(x=>x.includes('research_basin')).length,1,'double refresh must not duplicate requests');
 assert.equal(el('kpi-stations').textContent,'2','invalid coordinates excluded, stations available without Leaflet');
 assert.match(el('map-status').textContent,/biblioteca/);
 el('station-search').value='mucum';el('station-search-button').events.click();
 assert.equal(el('station-name').textContent,'Muçum');
 const html=el('model-table-body').children.at(-1).innerHTML;assert.ok(html.includes('&lt;img'));assert.ok(html.includes('&lt;b&gt;'));
 const before=requests.length;await el('refresh-feed').events.click();await settled();
 assert.equal(el('station-name').textContent,'Muçum','keep selection on refresh');
 assert.ok(requests.length>=before+7,'refresh all sections, with local fallback after remote failure');
 invalid=true;await el('refresh-feed').events.click();await settled();
 assert.equal(el('station-name').textContent,'Muçum');assert.match(el('hero-status-note').textContent,/Mantidos/);
 fail=true;await el('refresh-feed').events.click();await settled();
 assert.equal(el('shadow-package-status').textContent,'consulta indisponível');
 assert.equal(el('auto-training-status').textContent,'consulta indisponível');
 assert.equal(el('refresh-feed').attrs['aria-busy'],undefined);
 console.log('OK AI Lab: accent search without map, valid coordinates, refresh lock, all panels, fallback, preserved selection/data, truthful errors and escaped model text');
})().catch(e=>{console.error(e);process.exitCode=1;});
