'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const nodes=new Map();
const element=()=>({innerHTML:'',textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},addEventListener(k,v){this[k]=v;}});
const q=s=>{if(!nodes.has(s))nodes.set(s,element());return nodes.get(s);};
let retry,calls=0,fail=true;
const root={...element(),querySelector:q,getAttribute:()=>'/feed.json',appendChild:x=>{retry=x;}};
const data={location:'santa_tereza',events:[{difficulty:null,model_count:2}],horizons:[{hours:24,probability_percent:87}],summary:{event_count:0,model_card_event_count:0},source_quality:{probability:{state:'stale',age_hours:null}}};
const context={document:{querySelector:()=>root,createElement:element},PrevineSiteRuntime:{fetchResource:async()=>{calls++;await new Promise(r=>setImmediate(r));if(fail)throw Error('offline');return{ok:true,json:async()=>data};}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/js/research_patterns_dashboard.js'),'utf8'),context);
async function settled(){for(let i=0;i<30&&root.attrs['aria-busy'];i++)await new Promise(r=>setImmediate(r));assert.equal(root.attrs['aria-busy'],undefined);}
(async()=>{
 await settled();assert.equal(retry.hidden,false);assert.equal(q('.pattern-updated').textContent,'Falha ao carregar');
 fail=false;const request=retry.click();retry.click();await request;assert.equal(calls,2);assert.equal(retry.hidden,true);
 assert.ok(!q('#pattern-models').innerHTML.includes('87'),'stale score must not leak through heading');
 assert.match(q('#pattern-kpis').innerHTML,/idade desconhecida/);
 assert.match(q('#pattern-kpis').innerHTML,/<strong>0<\/strong>/,'explicit zero count retained');
 assert.match(q('#pattern-events').innerHTML,/Dificuldade do evento: —/);
 data.source_quality.probability.state='fresh';await retry.click();assert.match(q('#pattern-models').innerHTML,/87%/);
 data.events[0].difficulty=0;data.horizons[0].probability_percent=0;await retry.click();assert.match(q('#pattern-events').innerHTML,/Dificuldade do evento: 0%/);assert.match(q('#pattern-models').innerHTML,/0%/);
 data.source_quality={};await retry.click();assert.ok(!q('#pattern-models').innerHTML.includes('0% exp.'));assert.match(q('#pattern-source').innerHTML,/não informada/);
 data.location='mucum';data.horizons[0].probability_percent=12;await retry.click();assert.match(q('#pattern-models').innerHTML,/12%/,'logistic score is separate from Santa Tereza GEFS freshness');
 data.location='invalid';await retry.click();assert.equal(retry.hidden,false);
 console.log('OK research patterns: failure/retry, request lock, stale/unknown/fresh GEFS, null versus zero, explicit counts and independent Muçum score');
})().catch(e=>{console.error(e);process.exitCode=1;});
