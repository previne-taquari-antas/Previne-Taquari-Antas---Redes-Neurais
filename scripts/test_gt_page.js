// Smoke real inline JS without Leaflet CDN or network.
// Exercises full startup and switching to both municipalities with DOM+Leaflet stubs.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('pesquisas/gt-risco-vida.html','utf8');
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
assert(scripts.length,'no inline scripts');
const code=scripts[scripts.length-1][1];
new vm.Script(code,{filename:'gt-risco-vida.inline.js'});
const els={};
function node(){return {style:{},textContent:'',innerHTML:'',children:[],addEventListener(){},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=[...items]}};}
function elem(id){return els[id]||(els[id]={...node(),
  value:id==='cidade'?'santa_tereza':id==='politica'?'exploratoria':id==='cota'?'13.4':undefined,
  checked:true,style:{},textContent:'',innerHTML:'',addEventListener(){}
});}
const geo={addTo(){return this},on(){return this},bindPopup(){return this},bindTooltip(){return this},getBounds(){return bounds}};
const bounds={extend(){return this},isValid(){return true},pad(){return this}};
const L={
  map(){return {setView(){return this},fitBounds(){return this},removeLayer(){return this}}},
  tileLayer(){return {...geo}},imageOverlay(){return {...geo}},layerGroup(){return {addTo(){return this},clearLayers(){}}},
  polyline(){return {...geo}},circleMarker(){return {...geo}},latLngBounds(){return {...bounds}}
};
const context={L,document:{getElementById:elem,createElement:()=>node(),createTextNode:text=>({textContent:String(text)})},console,Number,Math,Set,Map,Error,JSON,Array};
vm.runInNewContext(code,context,{timeout:20000,filename:'gt-risco-vida.inline.js'});
// Async mudaCidade triggers until its first await, all data inline so immediate.
assert(/Santa Tereza/.test(elem('resumo').innerHTML),'Santa Tereza not rendered');
assert(/Exemplo ilustrativo/.test(elem('visaoDestino').textContent),'Initial Santa Tereza route example is not visible');
assert(/Origem/.test(elem('visaoDestino').textContent),'Initial route must identify an example origin');
assert(/Centro de Santa Tereza/.test(elem('altosMapa').textContent),'Center elevated-road overlay not described');
assert(/trechos elevados candidatos/.test(elem('altosMapa').textContent),'Center candidate street counts missing');
assert(vm.runInNewContext("trechosElevados(d,13.4).some(x=>x.mid[0]>=-29.171&&x.mid[0]<=-29.163&&x.mid[1]>=-51.743&&x.mid[1]<=-51.728)",context,{timeout:20000}),
  'Center lacks candidate elevated-road segments');
assert(/565/.test(elem('resumo').innerHTML),'No 565 points in Santa Tereza summary');
elem('cidade').value='mucum';
vm.runInNewContext("mudaCidade()",context,{timeout:20000});
assert(/Muçum/.test(elem('resumo').innerHTML),'Muçum not rendered');
assert(/1937/.test(elem('resumo').innerHTML),'No 1937 points in Muçum summary');
assert(/Muçum/.test(elem('visaoResumo').textContent),'Floating map summary not rendered');
assert(/Exemplo ilustrativo/.test(elem('visaoDestino').textContent),'Muçum must open with an example, not an empty map');
vm.runInNewContext("exemploRota()",context,{timeout:20000});
assert(/Origem/.test(elem('visaoDestino').textContent),'Sample nearest high street route not displayed');
const mucRoute=vm.runInNewContext(`(()=>{const f=Object.fromEntries(d.meta.casas_campos.map((k,i)=>[k,i]));for(const x of d.casas){const y=rotaParaTerrenoAlto(d,x,f,13,0);if(y.rota)return y.rota;}return null})()`,context,{timeout:20000});
assert(mucRoute&&mucRoute.metros>0,'Muçum has no high-road path');
assert(mucRoute.cotaSaida>=15,'Muçum destination does not meet HAND +2 m criterion');

elem('cidade').value='santa_tereza';
vm.runInNewContext("mudaCidade()",context,{timeout:20000});
vm.runInNewContext("selecionada=388;rede(18.9,'exploratoria')",context,{timeout:20000});
assert(/já está na mancha simulada/.test(elem('visaoDestino').textContent),'Flooded origin should not suggest a route');
assert(/Não há cenário anterior/.test(elem('visaoDestino').textContent),'Origin 388 should explain when conservative road data cannot prove a path');
const stRoute=vm.runInNewContext(`(()=>{const f=Object.fromEntries(d.meta.casas_campos.map((k,i)=>[k,i]));for(const x of d.casas){const y=rotaParaTerrenoAlto(d,x,f,13.4,0);if(y.rota)return y.rota;}return null})()`,context,{timeout:20000});
assert(stRoute&&stRoute.cotaSaida>=15.4,'Santa Tereza destination is not elevated enough');
const stEdges=vm.runInNewContext('d.edges',context);
assert(stRoute.arestas.every(idx=>{let e=stEdges[idx];return e[3]===0&&e[4]>13.4;}),'Route crosses flooded, unknown or bridge segments');
// O bloqueio de rotas deve prevalecer sobre a aparência da camada de ruas.
for (const [city, level] of [['santa_tereza', 13.4], ['mucum', 13]]) {
 elem('cidade').value=city;
 vm.runInNewContext("mudaCidade()",context,{timeout:20000});
 const audit=vm.runInNewContext(`(()=>{
  const f=Object.fromEntries(d.meta.casas_campos.map((k,i)=>[k,i]));
  const found=d.casas.find(home=>saidaMaisProxima(d,home,f,${level}).classe==='com_folga'&&saidaMaisProxima(d,home,f,${level}).rota?.metros>=40);
  if(!found)return {ok:false,cause:'no_com_folga'};
  const good=saidaMaisProxima(d,found,f,${level});
  const unknown=found.slice();unknown[f.cota_alaga]=null;
  const missingBlocked=saidaMaisProxima(d,unknown,f,${level}).rota===null;
  const far=found.slice();far[f.lat]=Number(far[f.lat])+.02;
  const farResult=saidaMaisProxima(d,far,f,${level});
  const farBlocked=farResult.rota===null&&/60 m/.test(farResult.causa);
  const edgesValid=good.rota.arestas.every(i=>{
   const e=d.edges[i];
   return !e[3]&&e[4]!==null&&e[4]>${level}+1&&d.cota_no[e[0]]>${level}+1&&d.cota_no[e[1]]>${level}+1;
  });
  const sampleMargin=d.casas.find(h=>saidaMaisProxima(d,h,f,${level}).classe==='pendente_margem');
  const marginBlocked=sampleMargin?saidaMaisProxima(d,sampleMargin,f,${level}).rota===null:false;
  return {ok:true,missingBlocked,farBlocked,edgesValid,marginBlocked};
 })()`,context,{timeout:20000});
 assert(audit.ok&&audit.missingBlocked&&audit.farBlocked&&audit.edgesValid&&audit.marginBlocked,
  city+' failed conservative route guards: '+JSON.stringify(audit));
}
console.log('OK GT map: both cities, visible route examples, no unknown origins, no long snaps, no missing/elevated road violations');
